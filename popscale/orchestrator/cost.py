"""Simulation cost estimator for PopScale population runs.

PopScale personas are already generated — this estimator covers only the
simulation phase (perceive → reflect → decide per persona per stimulus).
Generation cost is handled by the Persona Generator's own CostEstimator.

The PG's CostEstimator is reused directly:
  - `est.sim_total` gives the simulation-phase cost
  - `est.gen_total` is ignored (personas already exist)

Usage::

    from popscale.orchestrator.cost import estimate_simulation_cost
    from src.experiment.session import SimulationTier

    est = estimate_simulation_cost(count=500, tier=SimulationTier.VOLUME)
    print(est.formatted())
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# ── Persona Generator imports ──────────────────────────────────────────────
_PG_ROOT = Path(__file__).parents[3] / "Persona Generator"
if str(_PG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PG_ROOT))

from src.orchestrator.cost_estimator import CostEstimator  # noqa: E402  (PG)
from src.experiment.session import SimulationTier           # noqa: E402  (PG)


# ── Tier mapping ──────────────────────────────────────────────────────────────

_TIER_STR: dict[SimulationTier, Literal["deep", "signal", "volume"]] = {
    SimulationTier.DEEP:   "deep",
    SimulationTier.SIGNAL: "signal",
    SimulationTier.VOLUME: "volume",
}


# ── SimulationCostEstimate ────────────────────────────────────────────────────

@dataclass
class SimulationCostEstimate:
    """Pre-run cost estimate for a PopScale population simulation.

    Generation cost is excluded — personas are assumed to already exist.

    Attributes:
        count:           Number of personas.
        tier:            Tier string ("deep" | "signal" | "volume").
        n_stimuli:       Number of stimuli per scenario (1 for a single Scenario).
        sim_cost_usd:    Simulation phase cost in USD.
        per_persona_usd: Cost per persona.
        est_time_range:  Human-readable time estimate ("~3–5 min").
    """
    count: int
    tier: str
    n_stimuli: int
    sim_cost_usd: float
    per_persona_usd: float
    est_time_range: str

    def formatted(self) -> str:
        """Console-ready pre-run cost summary."""
        w = 58

        def box_line(text: str = "") -> str:
            return f"║  {text:<{w - 4}}║"

        lines = [
            "╔" + "═" * (w - 2) + "╗",
            box_line("POPSCALE — SIMULATION COST ESTIMATE"),
            "╠" + "═" * (w - 2) + "╣",
            box_line(f"Personas:   {self.count:,}"),
            box_line(f"Tier:       {self.tier.upper()}"),
            box_line(f"Stimuli:    {self.n_stimuli}  (1 Scenario = 1 stimulus)"),
            "╠" + "═" * (w - 2) + "╣",
            box_line(f"  {'Simulation cost (estimate)':<38}  ${self.sim_cost_usd:>7.4f}"),
            box_line(f"  {'Per persona':<38}  ${self.per_persona_usd:>7.5f}"),
            box_line(f"  {'Estimated run time':<38}  {self.est_time_range}"),
            "╚" + "═" * (w - 2) + "╝",
        ]
        return "\n".join(lines)


# ── Public API ────────────────────────────────────────────────────────────────

def estimate_simulation_cost(
    count: int,
    tier: SimulationTier = SimulationTier.VOLUME,
    n_stimuli: int = 1,
) -> SimulationCostEstimate:
    """Estimate the simulation cost for a PopScale population run.

    Uses the Persona Generator's CostEstimator for the simulation phase only.
    Generation cost is excluded (personas already exist in the cohort).

    The time estimate uses PG benchmark data:
        ~3 min per stimulus per 100 personas at VOLUME tier (concurrent).
    Tier cost ratios: VOLUME=1×, SIGNAL≈2×, DEEP≈4× (due to Sonnet reflect/decide).

    Args:
        count:     Number of personas in the population.
        tier:      SimulationTier to use. Defaults to VOLUME.
        n_stimuli: Stimuli per scenario. Almost always 1 for a single Scenario.

    Returns:
        SimulationCostEstimate with cost and time breakdown.
    """
    tier_str = _TIER_STR[tier]

    # CostEstimator with count=count for sim math; sim_total is the sim-only cost.
    # gen_total will also be computed but we deliberately ignore it here.
    estimator = CostEstimator(
        count=count,
        tier=tier_str,
        n_stimuli=n_stimuli,
        has_decision_scenario=True,  # PopScale always provides a decision scenario
        has_corpus=False,
        run_domain_extraction=False,
    )
    est = estimator.compute()

    # Time estimate: simulation-only (exclude generation time from PG's combined estimate)
    time_str = _sim_only_time(count, n_stimuli)

    return SimulationCostEstimate(
        count=count,
        tier=tier_str,
        n_stimuli=n_stimuli,
        sim_cost_usd=round(est.sim_total, 4),
        per_persona_usd=round(est.sim_total / max(count, 1), 6),
        est_time_range=time_str,
    )


def _sim_only_time(count: int, n_stimuli: int) -> str:
    """Estimate simulation-only run time, excluding generation.

    Source: PG benchmark — ~3 min per stimulus per 100 personas (concurrent).
    Applies a [0.7×, 1.3×] range to account for API latency variance.
    """
    per_stim_per_100_s = 3 * 60  # 3 minutes
    factor = max(count / 100, 0.1)
    sim_min_s = max(int(n_stimuli * per_stim_per_100_s * factor * 0.7), 30)
    sim_max_s = max(int(n_stimuli * per_stim_per_100_s * factor * 1.3), 60)
    lo = sim_min_s // 60
    hi = sim_max_s // 60
    if lo < 1:
        return f"~{sim_max_s}s"
    if lo == hi:
        return f"~{lo} min"
    return f"~{lo}–{hi} min"
