"""study_runner — unified study entry point for PopScale.

run_study() chains the full PopScale pipeline in a single call:

    1. Calibrated generation  — PopulationSpec → PersonaRecords via PG
    2. Environment enrichment — apply SimulationEnvironment preset to Scenario
    3. Scenario simulation    — run_population_scenario() with caching
    4. Analytics              — generate_report() → PopScaleReport
    5. Social loop (optional) — run_social_scenario() → SocialReport
    6. Event impact (optional)— measure_event_impact() per EventTimeline round

This is the primary integration point for Niobe and other consumers that
want a single-call interface to the full Simulatte stack.

Usage::

    import asyncio
    from popscale.study.study_runner import StudyConfig, run_study
    from popscale.scenario.model import Scenario, SimulationDomain
    from popscale.calibration.population_spec import PopulationSpec
    from popscale.environment import WEST_BENGAL_POLITICAL_2026

    config = StudyConfig(
        spec=PopulationSpec(
            state="west_bengal",
            n_personas=500,
            domain="policy",
            business_problem="Bengal election sentiment: fuel prices and TMC incumbency.",
            stratify_by_religion=True,
        ),
        scenario=Scenario(
            question="Will you vote for the incumbent TMC party?",
            context="...",
            options=["Yes, TMC", "BJP", "Left-Congress", "Undecided"],
            domain=SimulationDomain.POLITICAL,
        ),
        environment=WEST_BENGAL_POLITICAL_2026,
        use_cache=True,
    )

    result = asyncio.run(run_study(config))
    print(result.report.to_markdown())
"""

from __future__ import annotations

import asyncio
import logging
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class BudgetExceededError(Exception):
    """Raised when the estimated study cost exceeds the configured budget cap."""


class GenerationFailedError(Exception):
    """Raised when PG's orchestrator fails to generate any personas.

    This wraps unhandled exceptions from invoke_persona_generator so callers
    (e.g. Niobe) can catch PG orchestrator failures distinctly from other errors
    and return a structured failure rather than crashing the study.
    """

logger = logging.getLogger(__name__)

_PG_ROOT = Path(__file__).parents[4] / "Persona Generator"
if str(_PG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PG_ROOT))

from src.experiment.session import SimulationTier                    # noqa: E402

from ..analytics.report import PopScaleReport, generate_report       # noqa: E402
from ..analytics.social_report import SocialReport, generate_social_report  # noqa: E402
from ..cache.response_cache import ResponseCache                     # noqa: E402
from ..calibration.population_spec import PopulationSpec             # noqa: E402
from ..environment import SimulationEnvironment, apply_environment   # noqa: E402
from ..generation.calibrated_generator import (                      # noqa: E402
    CohortGenerationResult,
    run_calibrated_generation,
)
from ..generation.seeded_calibrated_generator import (               # noqa: E402
    run_seeded_generation,
)
from ..orchestrator.runner import run_population_scenario            # noqa: E402
from ..scenario.events import EventTimeline                          # noqa: E402
from ..scenario.model import Scenario                                # noqa: E402
from ..schema.simulation_result import SimulationResult              # noqa: E402
from ..schema.social_simulation_result import SocialSimulationResult # noqa: E402
from ..social.social_runner import (                                 # noqa: E402
    SocialSimulationLevel,
    SocialNetwork,
    build_random_encounter,
    run_social_scenario,
)
from .persistence import save_study_result                           # noqa: E402


# ── StudyConfig ───────────────────────────────────────────────────────────────

@dataclass
class StudyConfig:
    """Full configuration for a PopScale research study.

    Attributes:
        spec:               Demographic specification for cohort generation.
        scenario:           The Scenario all personas respond to.
        environment:        Optional environment preset. Applied to scenario before
                            simulation — enriches prompts with regional/cultural context.
        timeline:           Optional EventTimeline for temporal event injection.
                            Events are used as social stimuli if run_social=True.
        run_social:         If True, run a social simulation after the main sim.
        social_level:       Social simulation level. Default MODERATE.
        social_topology:    Network topology. "random_encounter" or "full_mesh".
        social_k:           k-value for random_encounter topology.
        social_seed:        Seed for deterministic random_encounter networks.
        generation_tier:    PG tier for persona generation. Default "volume".
        simulation_tier:    PopScale tier for scenario simulation. Default VOLUME.
        budget_cap_usd:     If set, abort if simulation cost estimate exceeds this.
        use_cache:          If True, wire a ResponseCache to skip re-running personas.
        cache_path:         Path for disk-backed cache. In-memory only if None.
        shard_size:         Shard size for run_population_scenario(). Default 50.
        concurrency:        Max concurrent LLM calls per shard. Default 20.
        run_id:             Optional study identifier. Auto-generated if None.
        llm_client:         Optional Anthropic client. PG/PopScale creates one if None.
    """
    spec: PopulationSpec
    scenario: Scenario

    environment: Optional[SimulationEnvironment] = None
    timeline: Optional[EventTimeline] = None

    run_social: bool = False
    social_level: SocialSimulationLevel = SocialSimulationLevel.MODERATE
    social_topology: str = "random_encounter"
    social_k: int = 3
    social_seed: Optional[int] = None

    generation_tier: str = "volume"
    simulation_tier: SimulationTier = SimulationTier.VOLUME

    # Seeded generation — generates seed_count deep personas then expands the rest
    # via VariantGenerator (1 Haiku call per variant). ~97% cheaper than standard
    # for large populations. Only meaningful when spec.n_personas >> seed_count.
    use_seeded_generation: bool = False
    seed_count: int = 200
    seed_tier: str = "deep"

    budget_cap_usd: Optional[float] = None
    use_cache: bool = True
    cache_path: Optional[Path] = None
    output_dir: Optional[Path] = None

    shard_size: int = 50
    concurrency: int = 20

    run_id: Optional[str] = None
    llm_client: Any = None


# ── StudyResult ───────────────────────────────────────────────────────────────

@dataclass
class StudyResult:
    """Complete output from run_study().

    Attributes:
        run_id:         Study identifier.
        config:         The StudyConfig used.
        cohort:         Calibrated generation result (personas + cost).
        simulation:     Scenario simulation result.
        report:         Full analytics report.
        social_result:  Social simulation result (if run_social=True).
        social_report:  Social analytics report (if run_social=True).
        started_at:     UTC start timestamp.
        completed_at:   UTC completion timestamp.
    """
    run_id: str
    config: StudyConfig
    cohort: CohortGenerationResult
    simulation: SimulationResult
    report: PopScaleReport
    social_result: Optional[SocialSimulationResult] = None
    social_report: Optional[SocialReport] = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def duration_seconds(self) -> float:
        return (self.completed_at - self.started_at).total_seconds()

    @property
    def total_cost_usd(self) -> float:
        return self.cohort.total_cost_usd + self.simulation.cost_actual_usd

    @property
    def n_personas(self) -> int:
        return self.cohort.total_delivered

    def summary(self) -> str:
        social_note = (
            f" | social_events={self.social_result.total_influence_events}"
            if self.social_result else ""
        )
        return (
            f"Study {self.run_id} | {self.n_personas} personas | "
            f"gen ${self.cohort.total_cost_usd:.4f} + sim ${self.simulation.cost_actual_usd:.4f} "
            f"= ${self.total_cost_usd:.4f} total | "
            f"{self.duration_seconds:.1f}s{social_note}"
        )

    def to_dict(self) -> dict:
        return {
            "run_id":         self.run_id,
            "started_at":     self.started_at.isoformat(),
            "completed_at":   self.completed_at.isoformat(),
            "duration_s":     round(self.duration_seconds, 2),
            "n_personas":     self.n_personas,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "cohort": {
                "delivered":      self.cohort.total_delivered,
                "requested":      self.cohort.total_requested,
                "cost_usd":       round(self.cohort.total_cost_usd, 4),
                "segments":       self.cohort.segment_breakdown(),
            },
            "simulation": {
                "run_id":         self.simulation.run_id,
                "cost_usd":       round(self.simulation.cost_actual_usd, 4),
                "circuit_breaker_trips": self.simulation.circuit_breaker_trips,
            },
            "report":   self.report.to_dict(),
            "social":   self.social_report.to_dict() if self.social_report else None,
        }


# ── Cost estimation ───────────────────────────────────────────────────────────
# Conservative per-persona cost estimates used for pre-flight budget checks.
# These are upper-bound estimates; actuals depend on model, prompt length, and caching.

_GEN_COST_PER_PERSONA: dict[str, float] = {
    "volume":   0.06,
    "standard": 0.12,
    "deep":     0.25,
}
_SIM_COST_PER_PERSONA: dict[str, float] = {
    "volume":   0.04,
    "standard": 0.10,
    "deep":     0.18,
}


def estimate_study_cost(config: StudyConfig) -> float:
    """Return a conservative upper-bound cost estimate (USD) for a study config.

    For seeded mode: seed_cost + variant_cost + simulation_cost.
    For standard mode: (gen_rate + sim_rate) × n_personas.

    Args:
        config: The StudyConfig to estimate.

    Returns:
        Estimated total cost in USD.
    """
    sim_rate = _SIM_COST_PER_PERSONA.get(config.simulation_tier.name.lower(), 0.04)
    sim_cost = config.spec.n_personas * sim_rate

    if config.use_seeded_generation:
        seed_gen_rate = _GEN_COST_PER_PERSONA.get(config.seed_tier, 0.25)
        seed_cost = config.seed_count * seed_gen_rate
        variant_cost = max(0, config.spec.n_personas - config.seed_count) * 0.004
        return seed_cost + variant_cost + sim_cost

    gen_rate = _GEN_COST_PER_PERSONA.get(config.generation_tier, 0.06)
    return config.spec.n_personas * (gen_rate + sim_rate)


# ── Public entry point ────────────────────────────────────────────────────────

async def run_study(config: StudyConfig) -> StudyResult:
    """Run a complete PopScale research study from config to report.

    Pipeline:
        1. Generate personas via run_calibrated_generation()
        2. Apply environment preset to scenario
        3. Run run_population_scenario() with cache
        4. Generate analytics report
        5. Optionally run social simulation
        6. Return StudyResult

    Args:
        config: Full study configuration.

    Returns:
        StudyResult containing cohort, simulation, and report.

    Raises:
        ValueError: If cohort generation delivers 0 personas.
        BudgetExceededError: If simulation estimate exceeds config.budget_cap_usd.
    """
    run_id     = config.run_id or f"st-{uuid.uuid4().hex[:8]}"
    started_at = datetime.now(timezone.utc)

    logger.info(
        "run_study | run=%s | state=%s | n=%d | scenario=%s",
        run_id, config.spec.state, config.spec.n_personas,
        config.scenario.question[:60],
    )

    # ── 0. Budget pre-flight ───────────────────────────────────────────────
    if config.budget_cap_usd is not None:
        estimate = estimate_study_cost(config)
        logger.info(
            "  Budget check: estimated $%.2f vs cap $%.2f",
            estimate, config.budget_cap_usd,
        )
        if estimate > config.budget_cap_usd:
            raise BudgetExceededError(
                f"Estimated cost ${estimate:.2f} exceeds budget cap "
                f"${config.budget_cap_usd:.2f} for {config.spec.n_personas} personas "
                f"(tier={config.generation_tier}). "
                f"Reduce n_personas, lower the tier, or raise budget_cap_usd."
            )

    # ── 1. Generate cohort ─────────────────────────────────────────────────
    try:
        if config.use_seeded_generation:
            logger.info(
                "  Phase 1 (seeded): %d seeds + %d variants…",
                config.seed_count,
                max(0, config.spec.n_personas - config.seed_count),
            )
            cohort = await run_seeded_generation(
                config.spec,
                seed_count=config.seed_count,
                seed_tier=config.seed_tier,
                run_id=f"{run_id}-gen",
                llm_client=config.llm_client,
            )
        else:
            logger.info("  Phase 1: generating %d personas…", config.spec.n_personas)
            cohort = await run_calibrated_generation(
                config.spec,
                run_id=f"{run_id}-gen",
                tier_override=config.generation_tier,
                llm_client=config.llm_client,
            )
    except Exception as exc:
        raise GenerationFailedError(
            f"PG orchestrator failed for run {run_id} "
            f"({config.spec.state}, n={config.spec.n_personas}): "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    if cohort.total_delivered == 0:
        raise GenerationFailedError(
            f"Cohort generation delivered 0 personas for run {run_id}. "
            "Check PG configuration and anchor_overrides."
        )

    logger.info("  Phase 1 done: %d personas generated.", cohort.total_delivered)

    # ── 2. Enrich scenario with environment ────────────────────────────────
    scenario = config.scenario
    if config.environment is not None:
        scenario = apply_environment(scenario, config.environment)
        logger.info("  Applied environment: %s", config.environment.name)

    # ── 3. Wire cache ──────────────────────────────────────────────────────
    cache: Optional[ResponseCache] = None
    if config.use_cache:
        cache = ResponseCache(path=config.cache_path)
        logger.info("  Cache: %s", "disk-backed" if config.cache_path else "in-memory")

    # ── 4. Run scenario simulation ─────────────────────────────────────────
    logger.info("  Phase 2: running scenario simulation…")
    simulation = await run_population_scenario(
        scenario=scenario,
        personas=cohort.personas,
        tier=config.simulation_tier,
        run_id=f"{run_id}-sim",
        shard_size=config.shard_size,
        concurrency=config.concurrency,
        budget_cap_usd=config.budget_cap_usd,
        cache=cache,
        llm_client=config.llm_client,
        print_estimate=True,
    )
    logger.info("  Phase 2 done: %d responses collected.", len(simulation.responses))

    # ── 5. Analytics report ────────────────────────────────────────────────
    logger.info("  Phase 3: generating analytics report…")
    report = generate_report(simulation)
    logger.info("  Phase 3 done.")

    # ── 6. Optional social simulation ─────────────────────────────────────
    social_result: Optional[SocialSimulationResult] = None
    social_report: Optional[SocialReport] = None

    if config.run_social:
        logger.info("  Phase 4: running social simulation (level=%s)…",
                    config.social_level.value)

        # Build network from delivered personas
        persona_ids = [p.persona_id for p in cohort.personas]
        if config.social_topology == "full_mesh":
            from ..social.social_runner import build_full_mesh
            network: SocialNetwork = build_full_mesh(persona_ids)
        else:
            network = build_random_encounter(
                persona_ids,
                k=config.social_k,
                seed=config.social_seed,
            )

        # Stimuli: from EventTimeline if provided, else from scenario context
        if config.timeline is not None:
            stimuli = config.timeline.all_stimuli()
        else:
            stimuli = [scenario.question]

        social_result = await run_social_scenario(
            scenario=scenario,
            personas=cohort.personas,
            stimuli=stimuli,
            network=network,
            level=config.social_level,
            run_id=f"{run_id}-social",
            llm_client=config.llm_client,
        )
        social_report = generate_social_report(social_result)
        logger.info("  Phase 4 done: %d influence events.", social_result.total_influence_events)

    completed_at = datetime.now(timezone.utc)

    result = StudyResult(
        run_id=run_id,
        config=config,
        cohort=cohort,
        simulation=simulation,
        report=report,
        social_result=social_result,
        social_report=social_report,
        started_at=started_at,
        completed_at=completed_at,
    )

    logger.info("run_study complete: %s", result.summary())

    # ── 7. Persist to disk (if output_dir configured) ──────────────────────
    if config.output_dir is not None:
        save_study_result(result, config.output_dir)

    return result


def run_study_sync(config: StudyConfig) -> StudyResult:
    """Synchronous wrapper around run_study(). Do not call from an active event loop."""
    return asyncio.run(run_study(config))
