"""Week 9 Calibrated Generation Tests — structural/unit (no live PG calls).

Tests:
    1. _split_count() — sub-batching logic
    2. _deserialise_personas() — handles empty list, bad dicts
    3. CohortGenerationResult — properties and summary
    4. SegmentGenerationResult — structure
    5. run_calibrated_generation_sync imports and signature
    6. Integration with calibrate() — correct segment counts fed to briefs

Run all (no live API calls):
    python3 -m pytest tests/test_week9_generation.py -v
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_POPSCALE_ROOT = Path(__file__).parents[1]
_PG_ROOT       = _POPSCALE_ROOT.parent / "Persona Generator"
if str(_POPSCALE_ROOT) not in sys.path:
    sys.path.insert(0, str(_POPSCALE_ROOT))
if str(_PG_ROOT) not in sys.path:
    sys.path.insert(1, str(_PG_ROOT))

import pytest

from popscale.generation.calibrated_generator import (
    CohortGenerationResult,
    SegmentGenerationResult,
    _deserialise_personas,
    _split_count,
    run_calibrated_generation,
    run_calibrated_generation_sync,
)
from popscale.calibration.calibrator import PersonaSegment, calibrate
from popscale.calibration.population_spec import PopulationSpec


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_spec(n: int = 100, religion: bool = False) -> PopulationSpec:
    return PopulationSpec(
        state="west_bengal",
        n_personas=n,
        domain="policy",
        business_problem="Test study.",
        stratify_by_religion=religion,
    )


def _make_cohort_result(n_delivered: int = 100) -> CohortGenerationResult:
    spec = _make_spec(n=100)
    segments = calibrate(spec)
    now = datetime.now(timezone.utc)
    seg_results = [
        SegmentGenerationResult(
            segment=segments[0],
            count_requested=n_delivered,
            count_delivered=n_delivered,
            cost_usd=0.50,
            personas=[],
        )
    ]
    return CohortGenerationResult(
        run_id="cg-test001",
        spec=spec,
        segments=segments,
        segment_results=seg_results,
        personas=[],
        total_requested=n_delivered,
        total_delivered=n_delivered,
        total_cost_usd=0.50,
        started_at=now,
        completed_at=now,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. _split_count — sub-batching
# ─────────────────────────────────────────────────────────────────────────────

class TestSplitCount:

    def test_under_limit_returns_single(self):
        assert _split_count(100, 500) == [100]

    def test_exactly_limit_returns_single(self):
        assert _split_count(500, 500) == [500]

    def test_over_limit_splits(self):
        batches = _split_count(700, 500)
        assert batches == [500, 200]

    def test_double_limit(self):
        batches = _split_count(1000, 500)
        assert batches == [500, 500]

    def test_triple_limit(self):
        batches = _split_count(1500, 500)
        assert batches == [500, 500, 500]

    def test_odd_splits(self):
        batches = _split_count(1250, 500)
        assert batches == [500, 500, 250]

    def test_sum_equals_total(self):
        for n in [1, 99, 500, 501, 999, 1000, 1234, 5000]:
            assert sum(_split_count(n, 500)) == n

    def test_single_persona(self):
        assert _split_count(1, 500) == [1]

    def test_no_batch_exceeds_max(self):
        for n in [100, 500, 750, 1001, 2000]:
            for b in _split_count(n, 500):
                assert b <= 500


# ─────────────────────────────────────────────────────────────────────────────
# 2. _deserialise_personas — empty and bad dicts
# ─────────────────────────────────────────────────────────────────────────────

class TestDeserialisePersonas:

    def test_empty_list_returns_empty(self):
        result = _deserialise_personas([])
        assert result == []

    def test_invalid_dict_skipped_with_warning(self):
        # A completely invalid dict should be skipped, not raise
        result = _deserialise_personas([{"not": "a persona"}])
        assert isinstance(result, list)
        # Invalid entry silently skipped
        assert len(result) == 0


# ─────────────────────────────────────────────────────────────────────────────
# 3. CohortGenerationResult — properties
# ─────────────────────────────────────────────────────────────────────────────

class TestCohortGenerationResult:

    def test_duration_seconds_non_negative(self):
        r = _make_cohort_result()
        assert r.duration_seconds >= 0.0

    def test_delivery_rate_one_when_all_delivered(self):
        r = _make_cohort_result(n_delivered=100)
        assert abs(r.delivery_rate - 1.0) < 0.001

    def test_delivery_rate_zero_when_none(self):
        r = _make_cohort_result(n_delivered=100)
        r = CohortGenerationResult(
            run_id="r", spec=r.spec, segments=r.segments,
            segment_results=r.segment_results, personas=[],
            total_requested=100, total_delivered=0,
            total_cost_usd=0.0, started_at=r.started_at, completed_at=r.completed_at,
        )
        assert r.delivery_rate == 0.0

    def test_cost_per_persona_computed(self):
        r = _make_cohort_result(n_delivered=100)
        assert abs(r.cost_per_persona - 0.005) < 0.001

    def test_summary_contains_run_id(self):
        r = _make_cohort_result()
        assert "cg-test001" in r.summary()

    def test_summary_contains_cost(self):
        r = _make_cohort_result()
        assert "$" in r.summary()

    def test_segment_breakdown_is_list_of_dicts(self):
        r = _make_cohort_result()
        breakdown = r.segment_breakdown()
        assert isinstance(breakdown, list)
        for entry in breakdown:
            for key in ("label", "requested", "delivered", "cost_usd", "proportion"):
                assert key in entry


# ─────────────────────────────────────────────────────────────────────────────
# 4. SegmentGenerationResult — structure
# ─────────────────────────────────────────────────────────────────────────────

class TestSegmentGenerationResult:

    def test_construction(self):
        spec = _make_spec()
        segments = calibrate(spec)
        sr = SegmentGenerationResult(
            segment=segments[0],
            count_requested=100,
            count_delivered=95,
            cost_usd=0.47,
            personas=[],
            warnings=["5 personas quarantined"],
        )
        assert sr.count_requested == 100
        assert sr.count_delivered == 95
        assert len(sr.warnings) == 1

    def test_empty_warnings_default(self):
        spec = _make_spec()
        segments = calibrate(spec)
        sr = SegmentGenerationResult(
            segment=segments[0],
            count_requested=50,
            count_delivered=50,
            cost_usd=0.25,
            personas=[],
        )
        assert sr.warnings == []

    def test_empty_quality_summary_default(self):
        spec = _make_spec()
        segments = calibrate(spec)
        sr = SegmentGenerationResult(
            segment=segments[0],
            count_requested=50,
            count_delivered=50,
            cost_usd=0.25,
            personas=[],
        )
        assert sr.quality_summary == {}


# ─────────────────────────────────────────────────────────────────────────────
# 5. Module-level imports and signature
# ─────────────────────────────────────────────────────────────────────────────

class TestModuleInterface:

    def test_run_calibrated_generation_is_coroutine(self):
        import asyncio
        assert asyncio.iscoroutinefunction(run_calibrated_generation)

    def test_run_calibrated_generation_sync_is_callable(self):
        assert callable(run_calibrated_generation_sync)

    def test_run_calibrated_generation_signature(self):
        import inspect
        sig = inspect.signature(run_calibrated_generation)
        assert "spec" in sig.parameters
        assert "run_id" in sig.parameters
        assert "tier_override" in sig.parameters
        assert "on_segment_complete" in sig.parameters

    def test_cohort_generation_result_importable(self):
        from popscale.generation.calibrated_generator import CohortGenerationResult
        assert CohortGenerationResult is not None

    def test_segment_generation_result_importable(self):
        from popscale.generation.calibrated_generator import SegmentGenerationResult
        assert SegmentGenerationResult is not None


# ─────────────────────────────────────────────────────────────────────────────
# 6. Integration with calibrate() — segment math
# ─────────────────────────────────────────────────────────────────────────────

class TestCalibrationIntegration:

    def test_calibrate_produces_segments_summing_to_n(self):
        spec = _make_spec(n=500, religion=True)
        segments = calibrate(spec)
        assert sum(s.count for s in segments) == 500

    def test_split_count_matches_segment_count(self):
        """Verify that sub-batch math is exact for each segment."""
        spec = _make_spec(n=1200, religion=True)
        segments = calibrate(spec)
        for seg in segments:
            batches = _split_count(seg.count, 500)
            assert sum(batches) == seg.count
            assert all(b <= 500 for b in batches)

    def test_no_empty_segments_reach_generator(self):
        """calibrate() should never return a zero-count segment for n ≥ 10."""
        spec = _make_spec(n=100, religion=True)
        segments = calibrate(spec)
        assert all(s.count > 0 for s in segments)

    def test_large_n_sub_batches_correctly(self):
        """At N=1500, Hindu segment (~70%) = ~1050 → needs 3 batches."""
        spec = _make_spec(n=1500, religion=True)
        segments = calibrate(spec)
        hindu_seg = next(s for s in segments if "Hindu" in s.label)
        batches = _split_count(hindu_seg.count, 500)
        assert len(batches) >= 2
        assert sum(batches) == hindu_seg.count

    def test_anchor_overrides_preserved_per_segment(self):
        spec = _make_spec(n=100, religion=True)
        segments = calibrate(spec)
        muslim_seg = next((s for s in segments if "Muslim" in s.label), None)
        if muslim_seg:
            assert muslim_seg.anchor_overrides.get("religiosity") == "muslim"
            assert muslim_seg.anchor_overrides.get("location") == "India"
