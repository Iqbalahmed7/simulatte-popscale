"""Week 6 Event Timeline Tests — Temporal event injection and impact analytics.

Tests:
    1. SimulationEvent construction, validation, and stimulus formatting
    2. EventMagnitude classification
    3. EventTimeline queries (round, category, magnitude, tags)
    4. measure_event_impact() — option shifts, dominant shift, sentiment delta
    5. build_impact_timeline() — ordering and highest_impact
    6. EventImpactTimeline.to_dict() and to_markdown() structure

Run all (no live API calls needed):
    python3 -m pytest tests/test_week6_events.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

_POPSCALE_ROOT = Path(__file__).parents[1]
if str(_POPSCALE_ROOT) not in sys.path:
    sys.path.insert(0, str(_POPSCALE_ROOT))

import pytest

from popscale.scenario.events import (
    EventCategory,
    EventMagnitude,
    EventTimeline,
    SimulationEvent,
)
from popscale.analytics.event_impact import (
    EventImpactRecord,
    EventImpactTimeline,
    build_impact_timeline,
    measure_event_impact,
)


# ── Shared fixtures ───────────────────────────────────────────────────────────

def _make_event(
    round: int = 1,
    category: EventCategory = EventCategory.ECONOMIC,
    description: str = "Fuel prices rise 40%.",
    magnitude: float = 0.7,
    tags: list[str] | None = None,
) -> SimulationEvent:
    return SimulationEvent(
        round=round,
        category=category,
        description=description,
        magnitude=magnitude,
        tags=tags or [],
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. SimulationEvent — construction and validation
# ─────────────────────────────────────────────────────────────────────────────

class TestSimulationEvent:

    def test_basic_construction(self):
        e = _make_event()
        assert e.round == 1
        assert e.category == EventCategory.ECONOMIC
        assert e.magnitude == 0.7

    def test_magnitude_out_of_range_raises(self):
        with pytest.raises(ValueError, match="magnitude"):
            SimulationEvent(round=1, category=EventCategory.POLICY,
                            description="test", magnitude=1.5)

    def test_negative_round_raises(self):
        with pytest.raises(ValueError, match="round"):
            SimulationEvent(round=-1, category=EventCategory.POLICY,
                            description="test")

    def test_empty_description_raises(self):
        with pytest.raises(ValueError, match="description"):
            SimulationEvent(round=1, category=EventCategory.POLICY, description="   ")

    def test_magnitude_zero_allowed(self):
        e = SimulationEvent(round=0, category=EventCategory.SOCIAL,
                            description="Low-key community meeting.", magnitude=0.0)
        assert e.magnitude == 0.0

    def test_magnitude_one_allowed(self):
        e = SimulationEvent(round=2, category=EventCategory.NATURAL,
                            description="Severe cyclone landfall.", magnitude=1.0)
        assert e.magnitude == 1.0

    def test_to_dict_keys(self):
        e = _make_event()
        d = e.to_dict()
        for key in ("round", "category", "description", "magnitude",
                    "magnitude_label", "tags", "source"):
            assert key in d

    def test_to_stimulus_contains_category(self):
        e = _make_event(category=EventCategory.POLICY, description="New tax law passed.")
        stimulus = e.to_stimulus()
        assert "POLICY" in stimulus

    def test_to_stimulus_contains_description(self):
        e = _make_event(description="Fuel prices rise 40%.")
        stimulus = e.to_stimulus()
        assert "Fuel prices rise 40%." in stimulus

    def test_to_stimulus_contains_source_when_set(self):
        e = SimulationEvent(round=1, category=EventCategory.INFORMATION,
                            description="Breaking news.", source="Reuters")
        assert "[Reuters]" in e.to_stimulus()

    def test_to_stimulus_no_source_suffix_when_none(self):
        e = _make_event()
        assert "[" not in e.to_stimulus().split("]", 2)[-1]  # no trailing [source]

    def test_tags_stored(self):
        e = _make_event(tags=["bengal", "fuel"])
        assert "bengal" in e.tags
        assert "fuel" in e.tags


# ─────────────────────────────────────────────────────────────────────────────
# 2. EventMagnitude classification
# ─────────────────────────────────────────────────────────────────────────────

class TestEventMagnitude:

    def test_minor(self):
        assert EventMagnitude.from_score(0.1) == EventMagnitude.MINOR

    def test_moderate(self):
        assert EventMagnitude.from_score(0.45) == EventMagnitude.MODERATE

    def test_major(self):
        assert EventMagnitude.from_score(0.65) == EventMagnitude.MAJOR

    def test_critical(self):
        assert EventMagnitude.from_score(0.95) == EventMagnitude.CRITICAL

    def test_boundary_moderate(self):
        assert EventMagnitude.from_score(0.30) == EventMagnitude.MODERATE

    def test_boundary_critical(self):
        assert EventMagnitude.from_score(0.80) == EventMagnitude.CRITICAL

    def test_magnitude_label_property(self):
        e = _make_event(magnitude=0.9)
        assert e.magnitude_label == EventMagnitude.CRITICAL


# ─────────────────────────────────────────────────────────────────────────────
# 3. EventTimeline queries
# ─────────────────────────────────────────────────────────────────────────────

class TestEventTimeline:

    def _make_timeline(self) -> EventTimeline:
        return EventTimeline(
            name="Test Timeline",
            events=[
                SimulationEvent(round=1, category=EventCategory.ECONOMIC,
                                description="Fuel prices spike.", magnitude=0.7,
                                tags=["fuel", "bengal"]),
                SimulationEvent(round=1, category=EventCategory.POLICY,
                                description="Subsidy rollback announced.", magnitude=0.5,
                                tags=["policy"]),
                SimulationEvent(round=2, category=EventCategory.POLITICAL,
                                description="Opposition calls for strike.", magnitude=0.6,
                                tags=["politics", "bengal"]),
                SimulationEvent(round=3, category=EventCategory.SOCIAL,
                                description="Mass protest in Kolkata.", magnitude=0.85,
                                tags=["protest"]),
            ],
        )

    def test_n_events(self):
        tl = self._make_timeline()
        assert tl.n_events == 4

    def test_n_rounds(self):
        tl = self._make_timeline()
        assert tl.n_rounds == 3

    def test_max_round(self):
        tl = self._make_timeline()
        assert tl.max_round == 3

    def test_events_for_round(self):
        tl = self._make_timeline()
        r1 = tl.events_for_round(1)
        assert len(r1) == 2
        assert all(e.round == 1 for e in r1)

    def test_events_for_round_empty(self):
        tl = self._make_timeline()
        assert tl.events_for_round(99) == []

    def test_stimuli_for_round_returns_strings(self):
        tl = self._make_timeline()
        stimuli = tl.stimuli_for_round(1)
        assert len(stimuli) == 2
        assert all(isinstance(s, str) for s in stimuli)

    def test_events_by_category(self):
        tl = self._make_timeline()
        economic = tl.events_by_category(EventCategory.ECONOMIC)
        assert len(economic) == 1
        assert economic[0].category == EventCategory.ECONOMIC

    def test_events_above_magnitude(self):
        tl = self._make_timeline()
        major = tl.events_above_magnitude(0.7)
        assert len(major) == 2  # 0.7 and 0.85

    def test_events_with_tag(self):
        tl = self._make_timeline()
        bengal = tl.events_with_tag("bengal")
        assert len(bengal) == 2

    def test_events_with_tag_case_insensitive(self):
        tl = self._make_timeline()
        bengal = tl.events_with_tag("BENGAL")
        assert len(bengal) == 2

    def test_all_stimuli_count(self):
        tl = self._make_timeline()
        assert len(tl.all_stimuli()) == 4

    def test_empty_timeline(self):
        tl = EventTimeline()
        assert tl.n_events == 0
        assert tl.n_rounds == 0
        assert tl.max_round == 0
        assert tl.all_stimuli() == []

    def test_events_sorted_by_round(self):
        # Insert in reverse order — should be sorted after __post_init__
        tl = EventTimeline(events=[
            SimulationEvent(round=3, category=EventCategory.SOCIAL, description="Late event."),
            SimulationEvent(round=1, category=EventCategory.ECONOMIC, description="Early event."),
        ])
        assert tl.events[0].round == 1
        assert tl.events[-1].round == 3

    def test_summary_contains_name(self):
        tl = self._make_timeline()
        assert "Test Timeline" in tl.summary()

    def test_to_dict_structure(self):
        tl = self._make_timeline()
        d = tl.to_dict()
        assert "name" in d
        assert "n_events" in d
        assert "events" in d
        assert len(d["events"]) == 4


# ─────────────────────────────────────────────────────────────────────────────
# 4. measure_event_impact
# ─────────────────────────────────────────────────────────────────────────────

class TestMeasureEventImpact:

    OPTIONS = ["Yes", "Maybe", "No"]

    def test_returns_event_impact_record(self):
        event = _make_event()
        record = measure_event_impact(
            event=event,
            outcomes_before=["Yes", "Yes", "Maybe"],
            outcomes_after=["No", "No", "No"],
            options=self.OPTIONS,
        )
        assert isinstance(record, EventImpactRecord)

    def test_option_shifts_count_matches_options(self):
        event = _make_event()
        record = measure_event_impact(
            event=event,
            outcomes_before=["Yes", "Yes", "Maybe"],
            outcomes_after=["No", "No", "No"],
            options=self.OPTIONS,
        )
        assert len(record.option_shifts) == 3

    def test_dominant_shift_is_largest(self):
        event = _make_event()
        record = measure_event_impact(
            event=event,
            outcomes_before=["Yes", "Yes", "Yes", "Yes"],
            outcomes_after=["No", "No", "No", "No"],
            options=self.OPTIONS,
        )
        assert record.dominant_shift is not None
        for s in record.option_shifts:
            assert abs(record.dominant_shift.share_delta) >= abs(s.share_delta)

    def test_no_before_all_after_yes_shift(self):
        event = _make_event()
        record = measure_event_impact(
            event=event,
            outcomes_before=["No"] * 10,
            outcomes_after=["Yes"] * 10,
            options=self.OPTIONS,
        )
        yes_shift = next(s for s in record.option_shifts if s.option == "Yes")
        assert yes_shift.share_delta > 0
        assert yes_shift.direction == "increase"

    def test_no_change_gives_unchanged_direction(self):
        event = _make_event()
        outcomes = ["Yes", "No", "Maybe"]
        record = measure_event_impact(
            event=event,
            outcomes_before=outcomes,
            outcomes_after=outcomes,
            options=self.OPTIONS,
        )
        for s in record.option_shifts:
            assert s.direction == "unchanged"

    def test_sentiment_delta_computed_when_valences_provided(self):
        event = _make_event()
        record = measure_event_impact(
            event=event,
            outcomes_before=["Yes"],
            outcomes_after=["No"],
            options=self.OPTIONS,
            valences_before=[0.5, 0.6],
            valences_after=[-0.3, -0.1],
        )
        assert record.net_sentiment_delta is not None
        assert record.net_sentiment_delta < 0  # sentiment dropped

    def test_sentiment_delta_none_without_valences(self):
        event = _make_event()
        record = measure_event_impact(
            event=event,
            outcomes_before=["Yes"],
            outcomes_after=["No"],
            options=self.OPTIONS,
        )
        assert record.net_sentiment_delta is None

    def test_max_shift_pp_positive(self):
        event = _make_event()
        record = measure_event_impact(
            event=event,
            outcomes_before=["Yes", "Yes", "Yes"],
            outcomes_after=["No", "No", "No"],
            options=self.OPTIONS,
        )
        assert record.max_shift_pp > 0

    def test_event_preserved_in_record(self):
        event = _make_event(description="Special event.")
        record = measure_event_impact(
            event=event,
            outcomes_before=["Yes"],
            outcomes_after=["No"],
            options=self.OPTIONS,
        )
        assert record.event.description == "Special event."

    def test_to_dict_keys(self):
        event = _make_event()
        record = measure_event_impact(
            event=event,
            outcomes_before=["Yes"],
            outcomes_after=["No"],
            options=self.OPTIONS,
        )
        d = record.to_dict()
        for key in ("event", "n_before", "n_after", "max_shift_pp",
                    "dominant_shift", "option_shifts"):
            assert key in d


# ─────────────────────────────────────────────────────────────────────────────
# 5. build_impact_timeline
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildImpactTimeline:

    OPTIONS = ["Yes", "Maybe", "No"]

    def _make_record(self, round: int) -> EventImpactRecord:
        event = _make_event(round=round, magnitude=round * 0.2)
        return measure_event_impact(
            event=event,
            outcomes_before=["Yes", "Maybe"],
            outcomes_after=["No", "No"],
            options=self.OPTIONS,
        )

    def test_returns_impact_timeline(self):
        records = [self._make_record(1), self._make_record(2)]
        tl = build_impact_timeline(records)
        assert isinstance(tl, EventImpactTimeline)

    def test_total_events_count(self):
        records = [self._make_record(i) for i in range(1, 4)]
        tl = build_impact_timeline(records)
        assert tl.total_events == 3

    def test_sorted_by_round(self):
        records = [self._make_record(3), self._make_record(1), self._make_record(2)]
        tl = build_impact_timeline(records)
        rounds = [r.event.round for r in tl.records]
        assert rounds == sorted(rounds)

    def test_highest_impact_has_largest_shift(self):
        records = [self._make_record(1), self._make_record(3)]
        tl = build_impact_timeline(records)
        hi = tl.highest_impact
        assert hi is not None
        for r in tl.records:
            assert hi.max_shift_pp >= r.max_shift_pp

    def test_empty_timeline_highest_impact_none(self):
        tl = EventImpactTimeline()
        assert tl.highest_impact is None

    def test_to_dict_structure(self):
        records = [self._make_record(1)]
        tl = build_impact_timeline(records)
        d = tl.to_dict()
        assert "total_events" in d
        assert "records" in d
        assert "highest_impact_event" in d

    def test_to_markdown_is_string(self):
        records = [self._make_record(1), self._make_record(2)]
        tl = build_impact_timeline(records)
        md = tl.to_markdown()
        assert isinstance(md, str)
        assert "Event Impact Timeline" in md

    def test_empty_timeline_markdown(self):
        tl = EventImpactTimeline()
        md = tl.to_markdown()
        assert "No event impact" in md
