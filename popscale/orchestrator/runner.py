"""runner — fan-out orchestrator for population-scale PopScale simulations.

The Week 1 run_scenario_batch() handles small populations with bounded concurrency.
This module extends that to 500+ personas with:

  1. Shard-based fan-out: splits personas into batches of `shard_size` (default 50)
     to keep each async gather bounded and predictable.

  2. Circuit breaker: if the fallback rate in any shard exceeds
     `circuit_breaker_threshold` (default 10%), the runner pauses with
     exponential backoff before continuing. This absorbs transient API rate-limit
     bursts without cascading failures across the full population.

  3. Streaming callback: `on_shard_complete` is called after each shard with its
     partial results, so callers can start processing early without waiting for
     the full run to finish.

  4. Budget cap: if `budget_cap_usd` is set and the pre-run estimate exceeds it,
     the run is refused before any API calls are made.

  5. Cost tracking: returns cost estimate and actuals in SimulationResult.
     Actuals use the estimator's benchmark values until token-level tracking
     is wired in (Week 4).

Usage::

    import asyncio
    from popscale.orchestrator.runner import run_population_scenario
    from popscale.scenario.model import Scenario, SimulationDomain
    from popscale.utils.persona_adapter import load_cohort_file

    personas = load_cohort_file("/path/to/cohort.json")
    scenario = Scenario(
        question="Will you try the new subscription plan?",
        context="...",
        domain=SimulationDomain.CONSUMER,
    )

    result = asyncio.run(
        run_population_scenario(scenario=scenario, personas=personas)
    )
    print(result.summary())
"""

from __future__ import annotations

import asyncio
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ── Persona Generator imports ──────────────────────────────────────────────
_PG_ROOT = Path(__file__).parents[3] / "Persona Generator"
if str(_PG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PG_ROOT))

from src.schema.persona import PersonaRecord        # noqa: E402  (PG)
from src.experiment.session import SimulationTier   # noqa: E402  (PG)

# ── PopScale imports ──────────────────────────────────────────────────────
from ..scenario.model import Scenario                                    # noqa: E402
from ..schema.population_response import PopulationResponse              # noqa: E402
from ..cache.response_cache import ResponseCache                         # noqa: E402
from ..schema.simulation_result import ShardRecord, SimulationResult    # noqa: E402
from ..integration.run_scenario import run_scenario_batch                # noqa: E402
from .cost import SimulationCostEstimate, estimate_simulation_cost       # noqa: E402


# ── Sentinel for budget refusal ───────────────────────────────────────────────

class BudgetExceededError(RuntimeError):
    """Raised when the pre-run cost estimate exceeds the configured budget cap."""


# ── Circuit breaker defaults ──────────────────────────────────────────────────

_DEFAULT_CIRCUIT_BREAKER_THRESHOLD = 0.10   # 10% fallback rate trips the breaker
_DEFAULT_BACKOFF_BASE_SECONDS       = 10.0  # 10s → 20s → 40s ... per trip
_DEFAULT_MAX_BACKOFF_SECONDS        = 120.0 # cap at 2 minutes per wait


# ── Public entry point ────────────────────────────────────────────────────────

async def run_population_scenario(
    scenario: Scenario,
    personas: list[PersonaRecord],
    tier: SimulationTier = SimulationTier.VOLUME,
    *,
    shard_size: int = 50,
    concurrency: int = 20,
    budget_cap_usd: Optional[float] = None,
    run_id: Optional[str] = None,
    on_shard_complete: Optional[Callable[[list[PopulationResponse]], None]] = None,
    circuit_breaker_threshold: float = _DEFAULT_CIRCUIT_BREAKER_THRESHOLD,
    print_estimate: bool = True,
    llm_client: Any = None,
    cache: Optional[ResponseCache] = None,
) -> SimulationResult:
    """Run a PopScale Scenario against a population of personas at scale.

    Personas are sharded into batches of `shard_size` and each shard is run
    concurrently (bounded by `concurrency`). Shards themselves are processed
    sequentially so the circuit breaker can pause between them without
    abandoning in-flight work.

    Args:
        scenario:                    The PopScale Scenario to simulate.
        personas:                    List of PersonaRecord objects (already generated).
        tier:                        Simulation tier. Default VOLUME for population runs.
        shard_size:                  Personas per shard (affects parallelism granularity).
                                     50 is safe for Anthropic's concurrent-request limits.
        concurrency:                 Max simultaneous LLM calls within a shard.
        budget_cap_usd:              If set, refuse the run if estimate exceeds this cap.
        run_id:                      Optional run identifier. Generated if not provided.
        on_shard_complete:           Optional sync or async callback called after each
                                     shard completes with that shard's responses. Use for
                                     streaming / early processing.
        circuit_breaker_threshold:   Fallback rate (0-1) above which the circuit breaker
                                     trips and applies exponential backoff before the
                                     next shard. Default: 0.10 (10%).
        print_estimate:              If True, print the cost estimate before running.
        llm_client:                  Optional Anthropic client. None = PG creates one.
        cache:                       Optional ResponseCache. Personas with a cached
                                     (persona_id, scenario) result skip the LLM call.

    Returns:
        SimulationResult with all responses, cost, timing, and shard diagnostics.

    Raises:
        BudgetExceededError:  If cost estimate exceeds `budget_cap_usd`.
        ValueError:           If personas list is empty.
    """
    if not personas:
        raise ValueError("personas list is empty — nothing to simulate.")

    run_id = run_id or f"ps-{uuid.uuid4().hex[:8]}"
    started_at = datetime.now(timezone.utc)

    # ── 1. Cost estimate ──────────────────────────────────────────────────
    cost_estimate = estimate_simulation_cost(
        count=len(personas),
        tier=tier,
        n_stimuli=1,  # one Scenario = one stimulus pass
    )

    if print_estimate:
        print(cost_estimate.formatted())

    if budget_cap_usd is not None and cost_estimate.sim_cost_usd > budget_cap_usd:
        raise BudgetExceededError(
            f"Estimated cost ${cost_estimate.sim_cost_usd:.4f} exceeds budget cap "
            f"${budget_cap_usd:.2f}. Increase budget_cap_usd or reduce cohort size."
        )

    # ── 2. Shard the population ───────────────────────────────────────────
    shards = _make_shards(personas, shard_size)
    total_shards = len(shards)

    logger.info(
        "run_population_scenario | run=%s | personas=%d | shards=%d×%d | tier=%s",
        run_id, len(personas), total_shards, shard_size, tier.value,
    )

    # ── 3. Fan-out loop ───────────────────────────────────────────────────
    all_responses: list[PopulationResponse] = []
    shard_records: list[ShardRecord] = []
    circuit_breaker_trips = 0
    consecutive_trips = 0
    backoff_seconds = _DEFAULT_BACKOFF_BASE_SECONDS

    cache_hits_total = 0

    for i, shard in enumerate(shards):
        logger.info(
            "  shard %d/%d — %d personas…", i + 1, total_shards, len(shard)
        )

        # ── Cache check: split shard into hits and misses ─────────────────
        cached_responses: list[PopulationResponse] = []
        uncached_personas: list[PersonaRecord] = []

        if cache is not None:
            for persona in shard:
                key = ResponseCache.make_key(persona.persona_id, scenario)
                hit = cache.get(key)
                if hit is not None:
                    cached_responses.append(hit)
                    cache_hits_total += 1
                    logger.debug("  cache hit: %s", persona.persona_id)
                else:
                    uncached_personas.append(persona)
        else:
            uncached_personas = list(shard)

        # ── Run LLM only for uncached personas ───────────────────────────
        if uncached_personas:
            live_responses = await run_scenario_batch(
                scenario=scenario,
                personas=uncached_personas,
                tier=tier,
                llm_client=llm_client,
                run_id=run_id,
                concurrency=min(concurrency, len(uncached_personas)),
            )
            # Store new results in cache
            if cache is not None:
                for persona, resp in zip(uncached_personas, live_responses):
                    cache.put(ResponseCache.make_key(persona.persona_id, scenario), resp)
        else:
            live_responses = []

        shard_responses = cached_responses + live_responses

        # ── Detect fallbacks ──────────────────────────────────────────────
        fallback_count = sum(
            1 for r in shard_responses
            if r.reasoning_trace.startswith("[FALLBACK]")
        )
        fallback_rate = fallback_count / max(len(shard_responses), 1)

        # ── Circuit breaker ───────────────────────────────────────────────
        cb_tripped = fallback_rate > circuit_breaker_threshold
        if cb_tripped:
            circuit_breaker_trips += 1
            consecutive_trips += 1
            wait = min(backoff_seconds * (2 ** (consecutive_trips - 1)), _DEFAULT_MAX_BACKOFF_SECONDS)
            logger.warning(
                "  ⚡ Circuit breaker tripped (fallback_rate=%.0f%%, threshold=%.0f%%) — "
                "waiting %.0fs before next shard (trip #%d)",
                fallback_rate * 100, circuit_breaker_threshold * 100,
                wait, circuit_breaker_trips,
            )
            if i < total_shards - 1:  # no point sleeping after the last shard
                await asyncio.sleep(wait)
        else:
            consecutive_trips = 0  # reset on clean shard

        shard_records.append(ShardRecord(
            shard_index=i,
            shard_size=len(shard),
            responses_collected=len(shard_responses),
            fallback_count=fallback_count,
            circuit_breaker_tripped=cb_tripped,
            backoff_seconds=wait if cb_tripped and i < total_shards - 1 else 0.0,
        ))

        all_responses.extend(shard_responses)

        # ── Streaming callback ────────────────────────────────────────────
        if on_shard_complete is not None:
            if asyncio.iscoroutinefunction(on_shard_complete):
                await on_shard_complete(shard_responses)
            else:
                on_shard_complete(shard_responses)

        logger.info(
            "  shard %d/%d done — %d responses (fallbacks: %d / %.0f%%)",
            i + 1, total_shards, len(shard_responses),
            fallback_count, fallback_rate * 100,
        )

    # ── 4. Build result ───────────────────────────────────────────────────
    completed_at = datetime.now(timezone.utc)

    result = SimulationResult(
        run_id=run_id,
        scenario=scenario,
        tier=cost_estimate.tier,
        cohort_size=len(personas),
        responses=all_responses,
        cost_estimate_usd=cost_estimate.sim_cost_usd,
        cost_actual_usd=cost_estimate.sim_cost_usd,  # actuals = estimate until Week 4 token tracking
        started_at=started_at,
        completed_at=completed_at,
        shard_size=shard_size,
        concurrency=concurrency,
        shards=shard_records,
        circuit_breaker_trips=circuit_breaker_trips,
    )

    if cache is not None and cache_hits_total > 0:
        logger.info("Cache: %d hits / %d total (%.0f%%)",
                    cache_hits_total, len(personas),
                    cache_hits_total / len(personas) * 100)
        cache.save()

    logger.info("run_population_scenario complete: %s", result.summary())
    print(f"[PopScale] {result.summary()}")

    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_shards(
    personas: list[PersonaRecord], shard_size: int
) -> list[list[PersonaRecord]]:
    """Split personas into shards of at most `shard_size`."""
    return [
        personas[i : i + shard_size]
        for i in range(0, len(personas), shard_size)
    ]
