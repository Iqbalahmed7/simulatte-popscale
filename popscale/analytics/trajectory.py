"""trajectory — influence and drift analytics for social simulation runs.

Analyses PG's SocialSimulationTrace to surface:

  1. InfluenceStats — who transmitted/received the most influence,
     network density, mean gated importance scores.

  2. DriftSummary — how many tendency shifts occurred, which persona
     fields drifted most, how many personas changed.

  3. TrajectoryResult — composite of the above, ready for report assembly.

No external dependencies beyond the standard library.
"""

from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── PG path setup ─────────────────────────────────────────────────────────────
_PG_ROOT = Path(__file__).parents[3] / "Persona Generator"
if str(_PG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PG_ROOT))

from src.social.schema import SocialSimulationTrace  # noqa: E402


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class InfluenceHub:
    """A persona that is a notable transmitter or receiver in the network."""
    persona_id: str
    events_transmitted: int
    events_received: int
    importance_transmitted: float
    importance_received: float


@dataclass
class InfluenceStats:
    """Summary of influence flow across the population.

    Attributes:
        total_influence_events:       Total events across all turns.
        mean_events_transmitted:      Average per-persona transmission count.
        mean_events_received:         Average per-persona reception count.
        mean_importance_transmitted:  Population-avg gated importance (out).
        mean_importance_received:     Population-avg gated importance (in).
        network_density:              actual_events / max_possible_events.
        top_transmitters:             Top-3 personas by events transmitted.
        top_receivers:                Top-3 personas by events received.
        n_personas:                   Population size (for density normalisation).
    """
    total_influence_events: int
    mean_events_transmitted: float
    mean_events_received: float
    mean_importance_transmitted: float
    mean_importance_received: float
    network_density: float
    top_transmitters: list[InfluenceHub]
    top_receivers: list[InfluenceHub]
    n_personas: int


@dataclass
class DriftEntry:
    """A single tendency field that shifted during the social loop."""
    field: str
    shift_count: int


@dataclass
class DriftSummary:
    """Summary of tendency drift observed in the social simulation.

    Attributes:
        total_shifts:         Total TendencyShiftRecord count.
        personas_shifted:     Number of distinct personas that experienced drift.
        most_drifted_fields:  Top fields by shift count (field, count pairs).
        has_drift:            True if any drift occurred.
    """
    total_shifts: int
    personas_shifted: int
    most_drifted_fields: list[DriftEntry]
    has_drift: bool


@dataclass
class TrajectoryResult:
    """Full trajectory analytics for a social simulation run.

    Attributes:
        influence: Influence flow statistics.
        drift:     Tendency drift summary.
    """
    influence: InfluenceStats
    drift: DriftSummary


# ── Public API ────────────────────────────────────────────────────────────────

def analyse_trajectory(
    trace: SocialSimulationTrace,
    n_personas: int,
) -> TrajectoryResult:
    """Analyse a SocialSimulationTrace and return trajectory statistics.

    Args:
        trace:       PG's SocialSimulationTrace from run_social_loop().
        n_personas:  Population size (used for network density calculation).

    Returns:
        TrajectoryResult with influence stats and drift summary.
    """
    influence = _compute_influence_stats(trace, n_personas)
    drift      = _compute_drift_summary(trace)
    return TrajectoryResult(influence=influence, drift=drift)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _compute_influence_stats(
    trace: SocialSimulationTrace,
    n_personas: int,
) -> InfluenceStats:
    vectors = trace.influence_vectors  # dict[str, InfluenceVector]

    if not vectors:
        return InfluenceStats(
            total_influence_events=0,
            mean_events_transmitted=0.0,
            mean_events_received=0.0,
            mean_importance_transmitted=0.0,
            mean_importance_received=0.0,
            network_density=0.0,
            top_transmitters=[],
            top_receivers=[],
            n_personas=n_personas,
        )

    n = len(vectors)

    total_tx   = sum(v.total_events_transmitted for v in vectors.values())
    total_rx   = sum(v.total_events_received for v in vectors.values())
    mean_tx    = total_tx / n
    mean_rx    = total_rx / n

    # Mean gated importance — ignore personas with 0 events (avoid skew)
    tx_importances = [
        v.mean_gated_importance_transmitted
        for v in vectors.values()
        if v.total_events_transmitted > 0
    ]
    rx_importances = [
        v.mean_gated_importance_received
        for v in vectors.values()
        if v.total_events_received > 0
    ]
    mean_imp_tx = sum(tx_importances) / len(tx_importances) if tx_importances else 0.0
    mean_imp_rx = sum(rx_importances) / len(rx_importances) if rx_importances else 0.0

    # Network density: max possible edges in a directed graph = n*(n-1)
    max_possible = max(n * (n - 1), 1)
    density = min(trace.total_influence_events / max_possible, 1.0)

    # Build hub objects sorted by events
    hubs: list[InfluenceHub] = [
        InfluenceHub(
            persona_id=pid,
            events_transmitted=v.total_events_transmitted,
            events_received=v.total_events_received,
            importance_transmitted=v.mean_gated_importance_transmitted,
            importance_received=v.mean_gated_importance_received,
        )
        for pid, v in vectors.items()
    ]

    top_transmitters = sorted(hubs, key=lambda h: h.events_transmitted, reverse=True)[:3]
    top_receivers    = sorted(hubs, key=lambda h: h.events_received,    reverse=True)[:3]

    return InfluenceStats(
        total_influence_events=trace.total_influence_events,
        mean_events_transmitted=round(mean_tx, 2),
        mean_events_received=round(mean_rx, 2),
        mean_importance_transmitted=round(mean_imp_tx, 4),
        mean_importance_received=round(mean_imp_rx, 4),
        network_density=round(density, 4),
        top_transmitters=top_transmitters,
        top_receivers=top_receivers,
        n_personas=n_personas,
    )


def _compute_drift_summary(trace: SocialSimulationTrace) -> DriftSummary:
    shifts = trace.tendency_shift_log

    if not shifts:
        return DriftSummary(
            total_shifts=0,
            personas_shifted=0,
            most_drifted_fields=[],
            has_drift=False,
        )

    personas_shifted = len({s.persona_id for s in shifts})

    # Count shifts by tendency field
    field_counts: Counter[str] = Counter(s.tendency_field for s in shifts)
    most_drifted_fields = [
        DriftEntry(field=f, shift_count=c)
        for f, c in field_counts.most_common(5)
    ]

    return DriftSummary(
        total_shifts=len(shifts),
        personas_shifted=personas_shifted,
        most_drifted_fields=most_drifted_fields,
        has_drift=True,
    )
