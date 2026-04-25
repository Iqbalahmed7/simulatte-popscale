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

# ── PopScale imports ───────────────────────────────────────────────────────────
from ..scenario.model import Scenario
from ..schema.social_simulation_result import SocialSimulationResult

# ── PG availability ────────────────────────────────────────────────────────────
# PG (Persona Generator) lives in a separate repo/package.  When running inside
# the simulatte-engine on Railway, PG is not installed — and that's fine because
# most population builds never call run_social_scenario().  All PG imports are
# deferred to _ensure_pg() so the module loads cleanly in all environments.

_pg_loaded: bool = False

# ── Stub types (used when PG is not available) ────────────────────────────────
# These keep `from popscale.social.social_runner import SocialSimulationLevel`
# working at import time even when PG is absent (e.g. Railway engine container).
# They are replaced by the real PG enums at the bottom of this module.

import enum as _enum

class SocialSimulationLevel(_enum.Enum):  # noqa: E302
    ISOLATED  = "isolated"
    LOW       = "low"
    MODERATE  = "moderate"
    HIGH      = "high"
    SATURATED = "saturated"

class SocialNetwork:  # noqa: E302  # stub — replaced by PG version when available
    pass


def _ensure_pg() -> None:
    """Resolve PG's src/ package onto sys.path.

    Called lazily the first time any social-simulation function is invoked.
    Tries two locations in order:
      1. $PG_ROOT env-var — production override.  Set this on Railway if PG is
         cloned to a known path, e.g. PG_ROOT=/app/persona_generator
      2. Sibling "Persona Generator" directory relative to this file's repo
         root — works in local mono-repo development.

    Raises RuntimeError if PG cannot be found or imported.
    """
    global _pg_loaded
    if _pg_loaded:
        return

    import os

    # Option 1: pip-installed simulatte-persona-generator (production Railway)
    try:
        import src.social.loop_orchestrator  # noqa: F401
        _pg_loaded = True
        logger.debug("PG loaded from pip-installed package")
        return
    except ImportError:
        pass

    # Option 2: explicit env-var override
    pg_root_env = os.environ.get("PG_ROOT")
    candidate: Optional[Path] = Path(pg_root_env) if pg_root_env else None

    # Option 3: sibling directory (local dev mono-repo)
    if candidate is None or not candidate.exists():
        candidate = Path(__file__).parents[3] / "Persona Generator"

    if not candidate.exists():
        raise RuntimeError(
            "Persona Generator (PG) is not available in this environment. "
            "Social simulation requires PG. "
            "Set PG_ROOT=/path/to/persona-generator or install simulatte-persona-generator."
        )

    pg_root_str = str(candidate)
    if pg_root_str not in sys.path:
        sys.path.insert(0, pg_root_str)

    try:
        import src.social.loop_orchestrator  # noqa: F401
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            f"PG root found at {pg_root_str} but src.social is not importable: {exc}"
        ) from exc

    _pg_loaded = True
    logger.debug("PG loaded from %s", pg_root_str)


# ── Re-exported network builders (lazy) ───────────────────────────────────────

def build_full_mesh(persona_ids: list[str]) -> Any:
    """Build a fully-connected social network. Requires PG."""
    _ensure_pg()
    from src.social.network_builder import build_full_mesh as _build_full_mesh
    return _build_full_mesh(persona_ids)


def build_random_encounter(
    persona_ids: list[str],
    k: int = 3,
    seed: Optional[int] = None,
) -> Any:
    """Build a random k-regular encounter network. Requires PG."""
    _ensure_pg()
    from src.social.network_builder import build_random_encounter as _build_random_encounter
    return _build_random_encounter(persona_ids, k=k, seed=seed)


def build_directed_graph(edges: list[tuple[str, str]]) -> Any:
    """Build a directed influence graph from explicit edge pairs. Requires PG."""
    _ensure_pg()
    from src.social.network_builder import build_directed_graph as _build_directed_graph
    return _build_directed_graph(edges)


# SocialSimulationLevel and SocialNetwork are exposed as lazy properties
# so callers can do:  from popscale.social.social_runner import SocialSimulationLevel
# This is only safe to access after _ensure_pg() has run (or after import succeeds).

def _get_social_level_cls() -> Any:
    _ensure_pg()
    from src.social.schema import SocialSimulationLevel
    return SocialSimulationLevel


def _get_social_network_cls() -> Any:
    _ensure_pg()
    from src.social.schema import SocialNetwork
    return SocialNetwork


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
    personas: list[Any],
    stimuli: list[str],
    network: Any,
    level: Any,
    *,
    tier: Any = None,
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
                     Defaults to SimulationTier.DEEP if not provided.
        run_id:      Optional PopScale run identifier. Auto-generated if None.
        session_id:  Optional PG session ID. Auto-generated if None.
        cohort_id:   Optional PG cohort ID. Auto-generated if None.
        llm_client:  Optional Anthropic client. PG creates one if None.

    Returns:
        SocialSimulationResult with updated personas, full trace, and metadata.

    Raises:
        ValueError: If personas list is empty or stimuli list is empty.
        RuntimeError: If PG is not available in this environment.
    """
    # Resolve PG imports (raises RuntimeError if PG is unavailable)
    _ensure_pg()

    from src.social.loop_orchestrator import run_social_loop
    from src.experiment.session import SimulationTier
    from src.schema.persona import PersonaRecord  # noqa: F401 — used for runtime validation

    if tier is None:
        tier = SimulationTier.DEEP

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
