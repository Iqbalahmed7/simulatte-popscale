"""Week 7 Calibration Tests — India demographic profiles, PopulationSpec, Calibrator.

Tests:
    1. DemographicProfile — data integrity and accessors
    2. get_profile() — direct lookup, aliases, KeyError
    3. PopulationSpec — validation
    4. calibrate() — counts sum to n_personas for all stratification modes
    5. Religious stratification — proportions, Muslim religiosity override
    6. Income stratification — proportions
    7. Combined stratification — cross product
    8. Tiny segment merging
    9. build_cohort_breakdown() — structure
    10. West Bengal specific — profile values

Run all (no live API calls needed):
    python3 -m pytest tests/test_week7_calibration.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

_POPSCALE_ROOT = Path(__file__).parents[1]
if str(_POPSCALE_ROOT) not in sys.path:
    sys.path.insert(0, str(_POPSCALE_ROOT))

import pytest

from popscale.calibration.profiles import (
    DemographicProfile,
    get_profile,
    list_states,
    list_profiles,
)
from popscale.calibration.population_spec import PopulationSpec
from popscale.calibration.calibrator import (
    PersonaSegment,
    build_cohort_breakdown,
    calibrate,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _spec(
    state: str = "west_bengal",
    n: int = 100,
    religion: bool = False,
    income: bool = False,
    **kwargs,
) -> PopulationSpec:
    return PopulationSpec(
        state=state,
        n_personas=n,
        domain="policy",
        business_problem="Test business problem.",
        stratify_by_religion=religion,
        stratify_by_income=income,
        **kwargs,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. DemographicProfile — data integrity
# ─────────────────────────────────────────────────────────────────────────────

class TestDemographicProfile:

    def test_all_profiles_have_required_fields(self):
        for p in list_profiles():
            assert p.state
            assert p.state_code
            assert p.population_m > 0
            assert 0.0 <= p.urban_pct <= 1.0
            assert p.median_age > 0
            assert 0.0 <= p.literacy_rate <= 1.0

    def test_income_bands_sum_to_one(self):
        for p in list_profiles():
            total = sum(p.income_bands.values())
            assert abs(total - 1.0) < 0.01, f"{p.state}: income bands sum={total}"

    def test_religious_composition_sum_to_one(self):
        for p in list_profiles():
            total = sum(p.religious_composition.values())
            assert abs(total - 1.0) < 0.01, f"{p.state}: religion sum={total}"

    def test_rural_pct_complement_of_urban(self):
        p = get_profile("west_bengal")
        assert abs(p.rural_pct + p.urban_pct - 1.0) < 0.001

    def test_dominant_religion_returns_string(self):
        p = get_profile("west_bengal")
        assert isinstance(p.dominant_religion(), str)
        assert p.dominant_religion() == "hindu"  # WB: 70.5%

    def test_to_dict_has_required_keys(self):
        p = get_profile("west_bengal")
        d = p.to_dict()
        for key in ("state", "state_code", "urban_pct", "rural_pct",
                    "income_bands", "religious_composition", "region"):
            assert key in d

    def test_list_states_returns_sorted_list(self):
        states = list_states()
        assert states == sorted(states)
        assert "west_bengal" in states

    def test_list_profiles_count_matches_list_states(self):
        assert len(list_profiles()) == len(list_states())


# ─────────────────────────────────────────────────────────────────────────────
# 2. get_profile() — lookup and aliases
# ─────────────────────────────────────────────────────────────────────────────

class TestGetProfile:

    def test_direct_lookup_west_bengal(self):
        p = get_profile("west_bengal")
        assert p.state_code == "west_bengal"

    def test_lookup_case_insensitive(self):
        p = get_profile("West_Bengal")
        assert p.state_code == "west_bengal"

    def test_lookup_with_spaces(self):
        p = get_profile("West Bengal")
        assert p.state_code == "west_bengal"

    def test_alias_wb(self):
        assert get_profile("wb").state_code == "west_bengal"

    def test_alias_bengal(self):
        assert get_profile("bengal").state_code == "west_bengal"

    def test_alias_mumbai(self):
        assert get_profile("mumbai").state_code == "maharashtra"

    def test_alias_india(self):
        assert get_profile("india").state_code == "india"

    def test_alias_national(self):
        assert get_profile("national").state_code == "india"

    def test_alias_bangalore(self):
        assert get_profile("bangalore").state_code == "karnataka"

    def test_unknown_state_raises_key_error(self):
        with pytest.raises(KeyError, match="No demographic profile"):
            get_profile("atlantis")

    def test_all_state_codes_look_up_correctly(self):
        for code in list_states():
            p = get_profile(code)
            assert p.state_code == code


# ─────────────────────────────────────────────────────────────────────────────
# 3. PopulationSpec — validation
# ─────────────────────────────────────────────────────────────────────────────

class TestPopulationSpec:

    def test_basic_construction(self):
        spec = _spec()
        assert spec.state == "west_bengal"
        assert spec.n_personas == 100

    def test_zero_personas_raises(self):
        with pytest.raises(ValueError, match="n_personas"):
            PopulationSpec(state="west_bengal", n_personas=0,
                           domain="policy", business_problem="test")

    def test_age_min_ge_max_raises(self):
        with pytest.raises(ValueError, match="age_min"):
            PopulationSpec(state="west_bengal", n_personas=10,
                           domain="policy", business_problem="test",
                           age_min=50, age_max=30)

    def test_age_min_eq_max_raises(self):
        with pytest.raises(ValueError, match="age_min"):
            PopulationSpec(state="west_bengal", n_personas=10,
                           domain="policy", business_problem="test",
                           age_min=30, age_max=30)

    def test_both_urban_rural_only_raises(self):
        with pytest.raises(ValueError, match="urban_only"):
            PopulationSpec(state="west_bengal", n_personas=10,
                           domain="policy", business_problem="test",
                           urban_only=True, rural_only=True)

    def test_summary_contains_state(self):
        spec = _spec()
        assert "west_bengal" in spec.summary()

    def test_summary_contains_n_personas(self):
        spec = _spec(n=200)
        assert "200" in spec.summary()

    def test_sarvam_enabled_default_false(self):
        # Default is False — callers must opt in. India presets set it True explicitly.
        spec = _spec()
        assert spec.sarvam_enabled is False


# ─────────────────────────────────────────────────────────────────────────────
# 4. calibrate() — counts sum correctly
# ─────────────────────────────────────────────────────────────────────────────

class TestCalibrateCountSums:

    def _total(self, segments: list[PersonaSegment]) -> int:
        return sum(s.count for s in segments)

    def test_no_stratification_sums_to_n(self):
        spec = _spec(n=100)
        segs = calibrate(spec)
        assert self._total(segs) == 100

    def test_religion_stratification_sums_to_n(self):
        spec = _spec(n=200, religion=True)
        segs = calibrate(spec)
        assert self._total(segs) == 200

    def test_income_stratification_sums_to_n(self):
        spec = _spec(n=150, income=True)
        segs = calibrate(spec)
        assert self._total(segs) == 150

    def test_combined_stratification_sums_to_n(self):
        spec = _spec(n=300, religion=True, income=True)
        segs = calibrate(spec)
        assert self._total(segs) == 300

    def test_odd_n_still_exact(self):
        spec = _spec(n=97, religion=True)
        segs = calibrate(spec)
        assert self._total(segs) == 97

    def test_small_n_with_religion(self):
        spec = _spec(n=10, religion=True)
        segs = calibrate(spec)
        assert self._total(segs) == 10

    def test_single_persona(self):
        spec = _spec(n=1)
        segs = calibrate(spec)
        assert self._total(segs) == 1

    def test_returns_list_of_persona_segments(self):
        segs = calibrate(_spec(n=50))
        assert all(isinstance(s, PersonaSegment) for s in segs)

    def test_no_zero_count_segments_after_calibration(self):
        """No segment should have 0 personas after merging."""
        spec = _spec(n=100, religion=True, income=True)
        segs = calibrate(spec)
        assert all(s.count > 0 for s in segs)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Religious stratification — West Bengal proportions
# ─────────────────────────────────────────────────────────────────────────────

class TestReligiousStratification:

    def test_segments_reflect_wb_proportions(self):
        spec = _spec(n=1000, religion=True, min_segment_size=1)
        segs = calibrate(spec)
        # WB: Hindu 70.5%, Muslim 27%, Other ~2.5%
        # At N=1000, Hindu ~705, Muslim ~270, Other ~25
        hindu_seg  = next(s for s in segs if "Hindu" in s.label)
        muslim_seg = next(s for s in segs if "Muslim" in s.label)
        assert hindu_seg.count  > muslim_seg.count
        assert muslim_seg.count > 100  # ≥ 27% of 1000

    def test_muslim_segment_has_religiosity_override(self):
        spec = _spec(n=100, religion=True, min_segment_size=1)
        segs = calibrate(spec)
        muslim_seg = next((s for s in segs if "Muslim" in s.label), None)
        if muslim_seg:
            assert muslim_seg.anchor_overrides.get("religiosity") == "muslim"

    def test_hindu_segment_no_religiosity_override(self):
        spec = _spec(n=100, religion=True, min_segment_size=1)
        segs = calibrate(spec)
        hindu_seg = next((s for s in segs if "Hindu" in s.label), None)
        if hindu_seg:
            assert "religiosity" not in hindu_seg.anchor_overrides

    def test_all_segments_have_location_india(self):
        spec = _spec(n=100, religion=True)
        segs = calibrate(spec)
        for s in segs:
            assert s.anchor_overrides.get("location") == "India"

    def test_all_segments_have_age_overrides(self):
        spec = _spec(n=100, religion=True, age_min=25, age_max=55)
        segs = calibrate(spec)
        for s in segs:
            assert s.anchor_overrides.get("age_min") == 25
            assert s.anchor_overrides.get("age_max") == 55


# ─────────────────────────────────────────────────────────────────────────────
# 6. Income stratification
# ─────────────────────────────────────────────────────────────────────────────

class TestIncomeStratification:

    def test_three_income_segments_for_wb(self):
        spec = _spec(n=200, income=True, min_segment_size=1)
        segs = calibrate(spec)
        labels = [s.label for s in segs]
        assert any("Low" in l or "low" in l for l in labels)
        assert any("Middle" in l or "middle" in l for l in labels)
        assert any("High" in l or "high" in l for l in labels)

    def test_low_income_is_largest_for_wb(self):
        # WB: low=55%, middle=38%, high=7%
        spec = _spec(n=1000, income=True, min_segment_size=1)
        segs = calibrate(spec)
        low_seg  = next(s for s in segs if "Low" in s.label or "low" in s.label)
        high_seg = next(s for s in segs if "High" in s.label or "high" in s.label)
        assert low_seg.count > high_seg.count

    def test_extra_overrides_merged(self):
        spec = _spec(n=100, income=True,
                     extra_overrides={"pool_index": 3})
        segs = calibrate(spec)
        for s in segs:
            assert s.anchor_overrides.get("pool_index") == 3


# ─────────────────────────────────────────────────────────────────────────────
# 7. Combined stratification
# ─────────────────────────────────────────────────────────────────────────────

class TestCombinedStratification:

    def test_produces_multiple_segments(self):
        spec = _spec(n=500, religion=True, income=True, min_segment_size=1)
        segs = calibrate(spec)
        assert len(segs) >= 3  # at least 3 non-tiny segments

    def test_segments_sum_exactly(self):
        for n in [100, 250, 333, 500]:
            spec = _spec(n=n, religion=True, income=True)
            segs = calibrate(spec)
            assert sum(s.count for s in segs) == n, f"N={n}: got {sum(s.count for s in segs)}"


# ─────────────────────────────────────────────────────────────────────────────
# 8. Tiny segment merging
# ─────────────────────────────────────────────────────────────────────────────

class TestTinySegmentMerging:

    def test_tiny_segments_absorbed(self):
        # min_segment_size=50 with n=100 and religion should collapse "Other"
        spec = _spec(n=100, religion=True, min_segment_size=50)
        segs = calibrate(spec)
        for s in segs:
            assert s.count >= 1  # no zero-count segments

    def test_no_tiny_segments_below_min_size(self):
        # At n=1000 with min_segment_size=5, all kept segments ≥ 5
        spec = _spec(n=1000, religion=True, min_segment_size=5)
        segs = calibrate(spec)
        non_other = [s for s in segs if "Other" not in s.label]
        for s in non_other:
            assert s.count >= 5


# ─────────────────────────────────────────────────────────────────────────────
# 9. build_cohort_breakdown()
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildCohortBreakdown:

    def test_returns_dict(self):
        spec = _spec(n=100)
        d = build_cohort_breakdown(spec)
        assert isinstance(d, dict)

    def test_required_keys(self):
        spec = _spec(n=100)
        d = build_cohort_breakdown(spec)
        for key in ("state", "total_personas", "domain", "age_range",
                    "stratification", "segments"):
            assert key in d

    def test_total_personas_matches_spec(self):
        spec = _spec(n=250)
        d = build_cohort_breakdown(spec)
        assert d["total_personas"] == 250

    def test_segments_count_in_breakdown(self):
        spec = _spec(n=100, religion=True)
        d = build_cohort_breakdown(spec)
        assert len(d["segments"]) >= 1
        total_from_breakdown = sum(s["count"] for s in d["segments"])
        assert total_from_breakdown == 100

    def test_breakdown_reflects_stratification_flags(self):
        spec = _spec(n=100, religion=True, income=False)
        d = build_cohort_breakdown(spec)
        assert d["stratification"]["religion"] is True
        assert d["stratification"]["income"] is False


# ─────────────────────────────────────────────────────────────────────────────
# 10. West Bengal specific profile verification
# ─────────────────────────────────────────────────────────────────────────────

class TestWestBengalProfile:

    def test_urban_pct_approximately_32(self):
        p = get_profile("west_bengal")
        assert 0.30 <= p.urban_pct <= 0.35

    def test_muslim_population_approximately_27_pct(self):
        p = get_profile("west_bengal")
        assert 0.25 <= p.religious_composition["muslim"] <= 0.30

    def test_hindu_is_dominant_religion(self):
        p = get_profile("west_bengal")
        assert p.dominant_religion() == "hindu"

    def test_primary_language_bengali(self):
        p = get_profile("west_bengal")
        assert p.primary_language == "Bengali"

    def test_region_is_east(self):
        p = get_profile("west_bengal")
        assert p.region == "east"

    def test_low_income_is_majority(self):
        p = get_profile("west_bengal")
        assert p.income_bands["low"] >= 0.50

    def test_has_politically_competitive_tag(self):
        p = get_profile("west_bengal")
        assert "politically_competitive" in p.tags

    def test_literacy_above_70_pct(self):
        p = get_profile("west_bengal")
        assert p.literacy_rate >= 0.70
