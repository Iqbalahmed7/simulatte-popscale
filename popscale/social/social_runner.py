"""social_runner — PopScale adapter for PG's run_social_loop().

This module provides `run_social_scenario()`, a thin orchestration layer that:

  1. Accepts a PopScale Scenario + personas + social configuration.
  2. Calls PG's `run_social_loop()` with those inputs.
  3. Returns a `SocialSimulationResult` — a PopScale-native container
     wrapping PG's (personas_after, SocialSimulationTrace) output.

Network builders are re-exported here for convenience so callers only
need to import from popscale.social.

Usage::

    import asyncio
    from popscale.social.social_runner import (
        run_social_scenario,
        build_full_mesh,
        build_random_encounter,
        build_directed_graph,
    )
    from popscale.scenario.model import Scenario, SimulationDomain

    scenario = Scenario(
        question="Will you join the protest march?",
        context="...",
        domain=SimulationDomain.POLICY,
    )

    network = build_random_encounter(
        persona_ids=[p.persona_id for p in personas],
        k=3,
        seed=42,
    )

    result = asyncio.run(
        run_social_scenario(
            scenario=scenario,
            personas=personas,
            stimuli=["Rising fuel prices have caused nationwide protests."],
            network=network,
            level=SocialSimulationLevel.MODERATE,
        )
    )
    print(result.summary())
"""

from __future__ import annotations

import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── PG path setup ─────────────────────────────────────────────────────────────
_PG_ROOT = Path(__file__).parents[3] / "Persona Generator"
if str(_PG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PG_ROOT))

from src.social.loop_orchestrator import run_social_loop          # noqa: E402
from src.social.network_builder import (                          # noqa: E402
    build_directed_graph,
    build_full_mesh,
    build_random_encounter,
)
from src.social.schema import (                                   # noqa: E402
    SocialNetwork,
    SocialSimulationLevel,
)
from src.experiment.session import SimulationTier                 # noqa: E402
from src.schema.persona import PersonaRecord                      # noqa: E402

# ── PopScale imports ──────────────────────────────────────────────────────────
from ..scenario.model import Scenario                             # noqa: E402
from ..schema.social_simulation_result import SocialSimulationResult  # noqa: E402

# Re-export PG primitives for caller convenience
__all__ = [
    "run_social_scenario",
    "build_full_mesh",
    "build_random_encounter",
    "build_directed_graph",
    "SocialSimulationLevel",
    "SocialNetwork",
]


async def run_social_scenario(
    scenario: Scenario,
    personas: list[PersonaRecord],
    stimuli: list[str],
    network: SocialNetwork,
    level: SocialSimulationLevel,
    *,
    tier: SimulationTier = SimulationTier.DEEP,
    run_id: Optional[str] = None,
    session_id: Optional[str] = None,
    cohort_id: Optional[str] = None,
    llm_client: Any = None,
) -> SocialSimulationResult:
    """Run a PopScale Scenario through PG's social simulation loop.

    Args:
        scenario:    The PopScale Scenario being studied.
        personas:    Population of PersonaRecord objects (already generated).
        stimuli:     List of stimulus strings broadcast to all personas each
                     turn (e.g. news headlines, policy announcements).
        network:     SocialNetwork defining who can influence whom.
        level:       SocialSimulationLevel controlling interaction density.
        tier:        Simulation tier (DEEP recommended; VOLUME for cheap runs).
        run_id:      Optional PopScale run identifier. Auto-generated if None.
        session_id:  Optional PG session ID. Auto-generated if None.
        cohort_id:   Optional PG cohort ID. Auto-generated if None.
        llm_client:  Optional Anthropic client. PG creates one if None.

    Returns:
        SocialSimulationResult with updated personas, full trace, and metadata.

    Raises:
        ValueError: If personas list is empty or stimuli list is empty.
    """
    if not personas:
        raise ValueError("personas list is empty — nothing to simulate.")
    if not stimuli:
        raise ValueError("stimuli list is empty — social loop needs at least one stimulus.")

    run_id     = run_id    or f"ss-{uuid.uuid4().hex[:8]}"
    session_id = session_id or f"ses-{uuid.uuid4().hex[:8]}"
    cohort_id  = cohort_id  or f"coh-{uuid.uuid4().hex[:8]}"

    # Build decision_scenarios list from the scenario question.
    # PG uses this to ask each persona a structured decision at the end.
    decision_scenarios = [scenario.question]
    if scenario.options:
        decision_scenarios = [
            f"{scenario.question} Options: {', '.join(scenario.options)}"
        ]

    logger.info(
        "run_social_scenario | run=%s | personas=%d | level=%s | topology=%s | stimuli=%d",
        run_id, len(personas), level.value, network.topology.value, len(stimuli),
    )

    started_at = datetime.now(timezone.utc)

    personas_after, trace = await run_social_loop(
        personas=personas,
        stimuli=stimuli,
        network=network,
        level=level,
        session_id=session_id,
        cohort_id=cohort_id,
        decision_scenarios=decision_scenarios,
        llm_client=llm_client,
        tier=tier,
    )

    completed_at = datetime.now(timezone.utc)

    result = SocialSimulationResult(
        run_id=run_id,
        scenario_question=scenario.question,
        scenario_domain=scenario.domain.value,
        scenario_stimuli=stimuli,
        tier=tier.value,
        cohort_size=len(personas),
        personas_before=personas,
        personas_after=personas_after,
        trace=trace,
        network_topology=trace.network_topology.value,
        social_level=trace.social_simulation_level.value,
        started_at=started_at,
        completed_at=completed_at,
    )

    logger.info("run_social_scenario complete: %s", result.summary())
    return result
