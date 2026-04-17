"""event_impact — per-event impact analytics for temporal simulations.

Measures how simulation outcomes shift as events are introduced across rounds.
Works with before/after SimulationResult or SocialSimulationResult snapshots
taken before and after each event fires.

Key types:

    EventImpactRecord   — impact of a single event on outcome distributions
    EventImpactTimeline — ordered impact records for the full timeline

Usage::

    from popscale.analytics.event_impact import (
        measure_event_impact,
        EventImpactRecord,
        EventImpactTimeline,
    )

    # After running pre-event and post-event batches:
    impact = measure_event_impact(
        event=event,
        outcomes_before=["Yes", "Maybe", "No", "Yes"],
        outcomes_after=["No", "No", "Maybe", "No"],
        options=["Yes", "Maybe", "No"],
    )
    print(impact.dominant_shift)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..scenario.events import SimulationEvent


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class OptionShift:
    """Change in vote share for a single option before/after an event."""
    option: str
    share_before: float     # 0–1
    share_after:  float     # 0–1
    share_delta:  float     # after - before (signed)
    direction:    str       # "increase" | "decrease" | "unchanged"


@dataclass
class EventImpactRecord:
    """Impact of a single SimulationEvent on outcome distributions.

    Attributes:
        event:              The event that was injected.
        n_before:           Sample count before the event.
        n_after:            Sample count after the event.
        option_shifts:      Per-option share changes.
        dominant_shift:     The option with the largest absolute shift, or
                            None if no options were tracked.
        max_shift_pp:       Largest absolute shift in percentage points.
        net_sentiment_delta: Change in mean emotional valence (optional).
    """
    event: SimulationEvent
    n_before: int
    n_after: int
    option_shifts: list[OptionShift]
    dominant_shift: Optional[OptionShift]
    max_shift_pp: float
    net_sentiment_delta: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "event": self.event.to_dict(),
            "n_before": self.n_before,
            "n_after": self.n_after,
            "max_shift_pp": round(self.max_shift_pp, 2),
            "dominant_shift": {
                "option": self.dominant_shift.option,
                "share_before": round(self.dominant_shift.share_before, 4),
                "share_after": round(self.dominant_shift.share_after, 4),
                "share_delta": round(self.dominant_shift.share_delta, 4),
                "direction": self.dominant_shift.direction,
            } if self.dominant_shift else None,
            "net_sentiment_delta": (
                round(self.net_sentiment_delta, 4)
                if self.net_sentiment_delta is not None else None
            ),
            "option_shifts": [
                {
                    "option": s.option,
                    "share_before": round(s.share_before, 4),
                    "share_after": round(s.share_after, 4),
                    "share_delta": round(s.share_delta, 4),
                    "direction": s.direction,
                }
                for s in self.option_shifts
            ],
        }


@dataclass
class EventImpactTimeline:
    """Ordered impact records across the full event timeline.

    Attributes:
        records:          Impact records sorted by event round.
        total_events:     Number of events analysed.
        highest_impact:   The EventImpactRecord with the largest max_shift_pp.
    """
    records: list[EventImpactRecord] = field(default_factory=list)

    @property
    def total_events(self) -> int:
        return len(self.records)

    @property
    def highest_impact(self) -> Optional[EventImpactRecord]:
        if not self.records:
            return None
        return max(self.records, key=lambda r: r.max_shift_pp)

    def to_dict(self) -> dict:
        return {
            "total_events": self.total_events,
            "highest_impact_event": (
                self.highest_impact.event.description
                if self.highest_impact else None
            ),
            "records": [r.to_dict() for r in self.records],
        }

    def to_markdown(self) -> str:
        """Human-readable summary of event impacts."""
        if not self.records:
            return "*No event impact records to display.*"

        lines: list[str] = [
            "## Event Impact Timeline",
            "",
            f"*{self.total_events} event(s) analysed.*",
            "",
        ]

        for rec in self.records:
            ev = rec.event
            mag_bar = "█" * round(ev.magnitude * 5) + "░" * (5 - round(ev.magnitude * 5))
            lines += [
                f"### Round {ev.round} — {ev.category.value.title()} | {mag_bar}",
                "",
                f"> {ev.description}",
                "",
            ]
            if rec.dominant_shift:
                ds = rec.dominant_shift
                sign = "+" if ds.share_delta >= 0 else ""
                lines.append(
                    f"**Largest shift**: {ds.option} "
                    f"({sign}{ds.share_delta:.0%} pp, {ds.direction})"
                )
            lines += [
                "",
                f"| Option | Before | After | Δ |",
                f"|--------|------:|------:|--:|",
            ]
            for s in rec.option_shifts:
                sign = "+" if s.share_delta >= 0 else ""
                lines.append(
                    f"| {s.option[:40]} | {s.share_before:.0%} | {s.share_after:.0%} "
                    f"| {sign}{s.share_delta:.0%} |"
                )
            lines.append("")

        return "\n".join(lines)


# ── Public API ────────────────────────────────────────────────────────────────

def measure_event_impact(
    event: SimulationEvent,
    outcomes_before: list[str],
    outcomes_after: list[str],
    options: list[str],
    valences_before: Optional[list[float]] = None,
    valences_after: Optional[list[float]] = None,
) -> EventImpactRecord:
    """Measure the impact of a single event on outcome distributions.

    Args:
        event:           The SimulationEvent being evaluated.
        outcomes_before: Decision strings from the pre-event run.
        outcomes_after:  Decision strings from the post-event run.
        options:         Scenario options list (for share normalisation).
        valences_before: Optional emotional valence scores before (for sentiment delta).
        valences_after:  Optional emotional valence scores after.

    Returns:
        EventImpactRecord with per-option shifts and dominant shift.
    """
    n_before = max(len(outcomes_before), 1)
    n_after  = max(len(outcomes_after), 1)

    # Compute share distributions
    before_counts = {opt: 0 for opt in options}
    after_counts  = {opt: 0 for opt in options}

    for outcome in outcomes_before:
        matched = _match_option(outcome, options)
        if matched:
            before_counts[matched] += 1

    for outcome in outcomes_after:
        matched = _match_option(outcome, options)
        if matched:
            after_counts[matched] += 1

    shifts: list[OptionShift] = []
    for opt in options:
        sb = before_counts[opt] / n_before
        sa = after_counts[opt]  / n_after
        delta = sa - sb
        direction = "increase" if delta > 0.005 else "decrease" if delta < -0.005 else "unchanged"
        shifts.append(OptionShift(
            option=opt,
            share_before=sb,
            share_after=sa,
            share_delta=delta,
            direction=direction,
        ))

    dominant = max(shifts, key=lambda s: abs(s.share_delta)) if shifts else None
    max_pp   = abs(dominant.share_delta) * 100 if dominant else 0.0

    # Sentiment delta
    sentiment_delta: Optional[float] = None
    if valences_before and valences_after:
        mean_before = sum(valences_before) / len(valences_before)
        mean_after  = sum(valences_after)  / len(valences_after)
        sentiment_delta = round(mean_after - mean_before, 4)

    return EventImpactRecord(
        event=event,
        n_before=len(outcomes_before),
        n_after=len(outcomes_after),
        option_shifts=shifts,
        dominant_shift=dominant,
        max_shift_pp=round(max_pp, 2),
        net_sentiment_delta=sentiment_delta,
    )


def build_impact_timeline(records: list[EventImpactRecord]) -> EventImpactTimeline:
    """Build an EventImpactTimeline from a list of impact records.

    Records are sorted by event round for display.
    """
    sorted_records = sorted(records, key=lambda r: r.event.round)
    return EventImpactTimeline(records=sorted_records)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _match_option(outcome: str, options: list[str]) -> Optional[str]:
    """Match an outcome string to one of the scenario options.

    Priority: exact → containment → None (unclassified).
    """
    outcome_lower = outcome.strip().lower()
    # Exact match
    for opt in options:
        if outcome_lower == opt.strip().lower():
            return opt
    # Containment
    for opt in options:
        if opt.strip().lower() in outcome_lower or outcome_lower in opt.strip().lower():
            return opt
    return None
