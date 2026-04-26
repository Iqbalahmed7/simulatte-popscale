"""run_scenario — end-to-end integration between PopScale and Persona Generator.

This module is the seam between the two systems:
  - PopScale provides: Scenario (structured, domain-aware)
  - Persona Generator provides: run_loop() (cognitive loop), PersonaRecord

The flow:
    Scenario → render_stimulus() → str
    Scenario → render_decision_scenario() → str
    frame_persona_for_domain() → domain framing block appended to decision_scenario
    run_loop(stimulus, persona, decision_scenario, tier) → (PersonaRecord, LoopResult)
    from_decision_output(loop_result.decision, ...) → PopulationResponse

Tier selection: always defer to the caller. Default is VOLUME for population runs.
PopScale never re-implements tier routing — that belongs to the Persona Generator.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Persona Generator imports ──────────────────────────────────────────────
# PG root in sys.path → PG modules importable as `src.X` (PG's convention).
_PG_ROOT = Path(__file__).parents[3] / "Persona Generator"
if str(_PG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PG_ROOT))

from src.cognition.loop import run_loop, LoopResult          # noqa: E402  (PG)
from src.schema.persona import PersonaRecord                  # noqa: E402  (PG)
from src.experiment.session import SimulationTier             # noqa: E402  (PG)

# ── PopScale imports ──────────────────────────────────────────────────────
from ..scenario.model import Scenario, SimulationDomain        # noqa: E402
from ..scenario.renderer import render_stimulus, render_decision_scenario  # noqa: E402
from ..domain.framing import frame_persona_for_domain          # noqa: E402
from ..schema.population_response import (                     # noqa: E402
    PopulationResponse,
    from_decision_output,
)


async def run_scenario(
    scenario: Scenario,
    persona: PersonaRecord,
    tier: SimulationTier = SimulationTier.VOLUME,
    llm_client: Any = None,
    run_id: Optional[str] = None,
    manifesto_context: Optional[str] = None,
) -> PopulationResponse:
    """Run a single persona against a PopScale Scenario.

    Args:
        scenario: The structured PopScale scenario.
        persona:  A PersonaRecord from the Persona Generator.
        tier:     Simulation tier (DEEP/SIGNAL/VOLUME). Defaults to VOLUME for
                  population runs. Caller can override for quality-critical runs.
        llm_client: Optional Anthropic client. If None, the Persona Generator
                    creates one internally.
        run_id:   Optional run identifier for tracing across a population batch.
        manifesto_context: Optional cached system block for manifesto sensitivity
                          injection (PopScale Scenario-level context).

    Returns:
        A PopulationResponse. Never raises — returns a degraded response on
        LLM failure using the Persona Generator's own error handling.
    """
    # Step 1: Render scenario into Persona Generator input formats
    stimulus = render_stimulus(scenario)
    decision_scenario_base = render_decision_scenario(scenario)

    # Step 2: Generate domain framing (persona-specific, domain-aware language)
    # This translates the persona's domain-neutral attributes into domain language
    # It stays in decision_scenario, not emitted as separate system block,
    # because it's persona-specific and varies per persona (not cacheable across cluster)
    domain_framing = frame_persona_for_domain(persona, scenario.domain)
    decision_scenario = decision_scenario_base + domain_framing

    # Step 3: Run through the Persona Generator's cognitive loop
    # run_loop handles perceive → accumulate → (reflect) → decide internally
    # It also manages memory writes, importance accumulation, and reflection triggers
    # manifesto_context is optionally passed as a separate cacheable system block
    try:
        updated_persona, loop_result = await asyncio.wait_for(
            run_loop(
                stimulus=stimulus,
                persona=persona,
                decision_scenario=decision_scenario,
                llm_client=llm_client,
                tier=tier,
                manifesto_context=manifesto_context,
            ),
            timeout=90.0,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "run_loop timed out after 90s for persona %s (scenario: %r) — using fallback",
            persona.demographic_anchor.name,
            scenario.question[:60],
        )
        resp = _fallback_response(persona, scenario, run_id)
        import dataclasses
        resp = dataclasses.replace(resp, reasoning_trace="[TIMEOUT] run_loop exceeded 90s — fallback response used.")
        return resp
    except Exception as e:
        logger.error(
            "run_loop failed for persona %s (scenario: %r): %s",
            persona.demographic_anchor.name,
            scenario.question[:60],
            e,
        )
        # Return a minimal degraded response — don't crash the population batch
        return _fallback_response(persona, scenario, run_id)

    # Step 4: Validate that decide() ran (it runs when decision_scenario is provided)
    if not loop_result.decided or loop_result.decision is None:
        logger.warning(
            "decide() did not run for persona %s — reflection threshold not met "
            "or no decision_scenario provided. Returning degraded response.",
            persona.demographic_anchor.name,
        )
        return _fallback_response(persona, scenario, run_id)

    # Step 5: Wrap DecisionOutput as PopulationResponse
    return from_decision_output(
        decision=loop_result.decision,
        persona=updated_persona,
        domain=scenario.domain,
        scenario_options=scenario.options,
        run_id=run_id,
    )


async def run_scenario_batch(
    scenario: Scenario,
    personas: list[PersonaRecord],
    tier: SimulationTier = SimulationTier.VOLUME,
    llm_client: Any = None,
    run_id: Optional[str] = None,
    concurrency: int = 20,
    manifesto_context: Optional[str] = None,
) -> list[PopulationResponse]:
    """Run a scenario against a list of personas with controlled concurrency.

    Uses asyncio.Semaphore to bound concurrent LLM calls — prevents rate limit
    errors when running large populations. Default concurrency is 20 concurrent
    calls, which is well within Anthropic's API limits at Haiku tier.

    Args:
        concurrency: Max simultaneous LLM calls. Set lower if hitting rate limits.
        manifesto_context: Optional cached system block for manifesto sensitivity
                          injection (same for all personas in batch).

    Returns:
        List of PopulationResponse in the same order as input personas.
        Failed personas return degraded responses, never None.
    """
    semaphore = asyncio.Semaphore(concurrency)

    async def _bounded_run(persona: PersonaRecord, idx: int) -> PopulationResponse:
        async with semaphore:
            logger.debug(
                "run_scenario_batch: persona %d/%d — %s",
                idx + 1, len(personas), persona.demographic_anchor.name,
            )
            return await run_scenario(
                scenario=scenario,
                persona=persona,
                tier=tier,
                llm_client=llm_client,
                run_id=run_id,
                manifesto_context=manifesto_context,
            )

    tasks = [_bounded_run(p, i) for i, p in enumerate(personas)]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    return list(results)


def _fallback_response(
    persona: PersonaRecord,
    scenario: Scenario,
    run_id: Optional[str],
) -> PopulationResponse:
    """Construct a minimal valid response when the cognitive loop fails.

    For POLITICAL domain: uses political_lean as the vote prior (conservative/
    lean_conservative → first option, lean_progressive/progressive → last option,
    moderate → 50/50 split via persona_id hash). Falls back to risk_appetite if
    political_lean unavailable.

    For other domains: uses risk_appetite (high → first option, low → last).

    Not accurate — but valid, so it never silently drops a persona from the
    population batch.
    """
    from ..domain.framing import _estimate_prior, SEGMENT_LABELS
    from ..schema.population_response import DomainSignals, _extract_domain_signals
    from ..scenario.model import SimulationDomain as _SD

    anchor = persona.demographic_anchor
    di = persona.derived_insights
    bt = persona.behavioural_tendencies

    prior = _estimate_prior(persona)

    # Fix: for POLITICAL domain, use political_lean as the prior signal instead of
    # risk_appetite. risk_appetite maps most US personas to "medium" → options[1]
    # (Harris for binary US election), producing a systematic Harris fallback bias.
    # political_lean gives a more accurate proxy for vote intent.
    if scenario.domain == _SD.POLITICAL:
        try:
            from src.memory.core_memory import _get_political_lean
            lean = _get_political_lean(persona)
            _lean_prior_map = {
                # US archetypes
                "conservative":      "high",
                "lean_conservative": "high",
                "moderate":          "medium",
                "lean_progressive":  "low",
                "progressive":       "low",
                # India/Bengal archetypes
                "bjp_supporter":     "high",
                "bjp_lean":          "high",
                "neutral":           "medium",
                "opposition_lean":   "low",
                "opposition":        "low",
                "left_lean":         "third",   # maps to 3rd option (Left-Congress)
            }
            if lean and lean in _lean_prior_map:
                prior = _lean_prior_map[lean]
        except Exception:
            pass  # keep risk_appetite-based prior if PG unavailable

    confidence_map = {"high": 0.55, "medium": 0.4, "low": 0.3, "third": 0.5}
    confidence = confidence_map.get(prior, 0.4)

    if scenario.options:
        if len(scenario.options) == 2 and prior == "medium":
            # Binary scenarios: split moderates ~50/50 by persona_id hash
            idx = hash(persona.persona_id) % 2
            decision = scenario.options[idx]
        elif prior == "third" and len(scenario.options) >= 3:
            # left_lean → always 3rd option (index 2 = Left-Congress in Bengal)
            decision = scenario.options[2]
        else:
            decision_map = {
                "high":   scenario.options[0],
                "medium": scenario.options[len(scenario.options) // 2],
                "low":    scenario.options[-1],
                "third":  scenario.options[min(2, len(scenario.options) - 1)],
            }
            decision = decision_map.get(prior, scenario.options[len(scenario.options) // 2])
    else:
        decision_map = {
            "high":   "generally supportive",
            "medium": "uncertain / no clear position",
            "low":    "skeptical / cautious",
            "third":  "leaning towards a third alternative",
        }
        decision = decision_map.get(prior, "uncertain / no clear position")

    # SEGMENT_LABELS only has high/medium/low — map "third" to "medium" for display
    segment_prior_key = prior if prior in ("high", "medium", "low") else "medium"
    segment_label = SEGMENT_LABELS[scenario.domain][segment_prior_key]
    domain_signals = _extract_domain_signals(persona, scenario.domain)

    logger.warning(
        "Using fallback response for persona %s (prior=%s, decision=%r)",
        anchor.name, prior, decision,
    )

    return PopulationResponse(
        persona_id=persona.persona_id,
        persona_name=anchor.name,
        age=anchor.age,
        gender=anchor.gender,
        location_city=anchor.location.city,
        location_country=anchor.location.country,
        income_bracket=anchor.household.income_bracket,
        scenario_domain=scenario.domain.value,
        scenario_options=scenario.options,
        decision=decision,
        confidence=confidence,
        reasoning_trace=f"[FALLBACK] Based on prior segment '{segment_label}'.",
        gut_reaction="[FALLBACK — cognitive loop did not complete]",
        key_drivers=["prior behavioral profile"],
        objections=[],
        what_would_change_mind="[unavailable — fallback response]",
        follow_up_action="[unavailable — fallback response]",
        emotional_valence=(confidence - 0.5) * 2.0,
        domain_signals=domain_signals,
        risk_appetite=di.risk_appetite,
        trust_anchor=di.trust_anchor,
        decision_style=di.decision_style,
        primary_value_orientation=di.primary_value_orientation,
        consistency_score=di.consistency_score,
        price_sensitivity_band=bt.price_sensitivity.band,
        switching_propensity_band=bt.switching_propensity.band,
        run_id=run_id,
    )
