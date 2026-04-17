"""events — temporal event injection for PopScale simulations.

Models a timeline of discrete events (policy changes, news shocks, economic
shifts) that can be injected between simulation rounds or used to build
stimulus lists for social runs.

Key types:

    EventCategory  — enum of event types (ECONOMIC, POLICY, SOCIAL, etc.)
    SimulationEvent — a single event with timing, magnitude, and stimulus text
    EventTimeline   — ordered list of events with query helpers

Usage::

    from popscale.scenario.events import (
        EventCategory, SimulationEvent, EventTimeline
    )

    timeline = EventTimeline(events=[
        SimulationEvent(
            round=1,
            category=EventCategory.ECONOMIC,
            description="Fuel prices rise 40% following global oil shock.",
            magnitude=0.8,
        ),
        SimulationEvent(
            round=2,
            category=EventCategory.POLICY,
            description="Government announces fuel subsidy rollback.",
            magnitude=0.6,
        ),
    ])

    # Get stimulus strings for the social runner
    stimuli = timeline.stimuli_for_round(1)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ── Enums ─────────────────────────────────────────────────────────────────────

class EventCategory(str, Enum):
    """Category of a simulation event."""
    ECONOMIC    = "economic"     # Price changes, jobs, income shocks
    POLICY      = "policy"       # Government decisions, laws, regulations
    SOCIAL      = "social"       # Protests, cultural shifts, community events
    INFORMATION = "information"  # News, misinformation, media framing
    NATURAL     = "natural"      # Weather, disasters, climate events
    POLITICAL   = "political"    # Elections, party moves, leadership changes
    TECHNOLOGY  = "technology"   # Platform changes, infrastructure, AI


class EventMagnitude(str, Enum):
    """Qualitative magnitude label for event severity."""
    MINOR    = "minor"      # 0.0 – 0.29
    MODERATE = "moderate"   # 0.30 – 0.59
    MAJOR    = "major"      # 0.60 – 0.79
    CRITICAL = "critical"   # 0.80 – 1.0

    @staticmethod
    def from_score(score: float) -> "EventMagnitude":
        if score >= 0.80:
            return EventMagnitude.CRITICAL
        if score >= 0.60:
            return EventMagnitude.MAJOR
        if score >= 0.30:
            return EventMagnitude.MODERATE
        return EventMagnitude.MINOR


# ── Core event model ──────────────────────────────────────────────────────────

@dataclass
class SimulationEvent:
    """A discrete event injected into the simulation timeline.

    Attributes:
        round:       The simulation round at which this event fires.
                     Round 0 = before any LLM calls (pre-stimulus).
                     Round 1+ = between social loop turns or scenario batches.
        category:    The type of event (economic, policy, social, etc.).
        description: Human-readable description of the event. This string is
                     used directly as a stimulus in social loops or as context
                     enrichment in scenario prompts.
        magnitude:   Float 0–1 representing event severity. Use EventMagnitude
                     helpers for qualitative interpretation.
        tags:        Optional free-form tags for filtering (e.g. ["bengal",
                     "fuel", "subsidy"]).
        source:      Optional provenance label (e.g. "Reuters", "government
                     gazette", "simulated").
    """
    round: int
    category: EventCategory
    description: str
    magnitude: float = 0.5
    tags: list[str] = field(default_factory=list)
    source: Optional[str] = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.magnitude <= 1.0:
            raise ValueError(f"magnitude must be 0–1, got {self.magnitude}")
        if self.round < 0:
            raise ValueError(f"round must be >= 0, got {self.round}")
        if not self.description.strip():
            raise ValueError("description must not be empty")

    @property
    def magnitude_label(self) -> EventMagnitude:
        return EventMagnitude.from_score(self.magnitude)

    def to_stimulus(self) -> str:
        """Format the event as a stimulus string for PG's social loop."""
        label = self.magnitude_label.value.upper()
        source_suffix = f" [{self.source}]" if self.source else ""
        return f"[{self.category.value.upper()} | {label}] {self.description}{source_suffix}"

    def to_dict(self) -> dict:
        return {
            "round":       self.round,
            "category":    self.category.value,
            "description": self.description,
            "magnitude":   self.magnitude,
            "magnitude_label": self.magnitude_label.value,
            "tags":        self.tags,
            "source":      self.source,
        }


# ── EventTimeline ─────────────────────────────────────────────────────────────

@dataclass
class EventTimeline:
    """An ordered sequence of SimulationEvents.

    Events are always stored sorted by (round, category, description) for
    deterministic ordering.

    Attributes:
        events: All events in the timeline.
        name:   Optional label for the timeline (e.g. "West Bengal 2026").
    """
    events: list[SimulationEvent] = field(default_factory=list)
    name: Optional[str] = None

    def __post_init__(self) -> None:
        # Sort for determinism
        self.events = sorted(
            self.events,
            key=lambda e: (e.round, e.category.value, e.description),
        )

    # ── Query helpers ─────────────────────────────────────────────────────

    def events_for_round(self, round_number: int) -> list[SimulationEvent]:
        """Return all events scheduled for a specific round."""
        return [e for e in self.events if e.round == round_number]

    def stimuli_for_round(self, round_number: int) -> list[str]:
        """Return formatted stimulus strings for all events in a round."""
        return [e.to_stimulus() for e in self.events_for_round(round_number)]

    def events_by_category(self, category: EventCategory) -> list[SimulationEvent]:
        """Filter events by category."""
        return [e for e in self.events if e.category == category]

    def events_above_magnitude(self, threshold: float) -> list[SimulationEvent]:
        """Return events with magnitude >= threshold."""
        return [e for e in self.events if e.magnitude >= threshold]

    def events_with_tag(self, tag: str) -> list[SimulationEvent]:
        """Return events that have a specific tag (case-insensitive)."""
        tag_lower = tag.lower()
        return [e for e in self.events if tag_lower in [t.lower() for t in e.tags]]

    def all_stimuli(self) -> list[str]:
        """Return all events as stimulus strings (across all rounds)."""
        return [e.to_stimulus() for e in self.events]

    @property
    def n_events(self) -> int:
        return len(self.events)

    @property
    def n_rounds(self) -> int:
        """Number of distinct rounds that have events."""
        return len({e.round for e in self.events})

    @property
    def max_round(self) -> int:
        return max((e.round for e in self.events), default=0)

    def summary(self) -> str:
        label = f"'{self.name}' " if self.name else ""
        return (
            f"EventTimeline {label}| {self.n_events} events across "
            f"{self.n_rounds} round(s) | max_round={self.max_round}"
        )

    def to_dict(self) -> dict:
        return {
            "name":     self.name,
            "n_events": self.n_events,
            "events":   [e.to_dict() for e in self.events],
        }
