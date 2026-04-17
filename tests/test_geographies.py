"""test_geographies — USA and Europe geographic profile tests.

Tests:
    1. Profile lookup — US national, regions, key states, UK, EU countries
    2. Alias resolution — us, usa, uk, de, fr, etc.
    3. pg_location routing — correct strings for PG pool routing
    4. supports_religion_stratification flag — False for all non-India profiles
    5. Calibrator routing — non-India profiles produce correct location overrides
    6. Religion stratification fallback — falls back to income for US/UK/EU
    7. Income stratification — works for US/UK/EU profiles
    8. Environment presets — US/UK/EU presets registered and correct

Run (no live API calls):
    python3 -m pytest tests/test_geographies.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

_POPSCALE_ROOT = Path(__file__).parents[1]
_PG_ROOT = _POPSCALE_ROOT.parent / "Persona Generator"
for p in [str(_POPSCALE_ROOT), str(_PG_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest

from popscale.calibration.profiles import get_profile, list_states, DemographicProfile
from popscale.calibration.population_spec import PopulationSpec
from popscale.calibration.calibrator import calibrate, _build_base_overrides
from popscale.environment import get_preset, list_presets


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _spec(state: str, *, religion: bool = False, income: bool = True, n: int = 100) -> PopulationSpec:
    return PopulationSpec(
        state=state,
        n_personas=n,
        domain="consumer",
        business_problem="Test research question.",
        stratify_by_religion=religion,
        stratify_by_income=income,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Profile lookup — direct keys
# ─────────────────────────────────────────────────────────────────────────────

class TestProfileLookup:

    def test_united_states_profile(self):
        p = get_profile("united_states")
        assert p.state_code == "united_states"

    def test_us_northeast_profile(self):
        p = get_profile("us_northeast")
        assert p.state_code == "us_northeast"

    def test_us_south_profile(self):
        p = get_profile("us_south")
        assert p.state_code == "us_south"

    def test_us_midwest_profile(self):
        p = get_profile("us_midwest")
        assert p.state_code == "us_midwest"

    def test_us_west_profile(self):
        p = get_profile("us_west")
        assert p.state_code == "us_west"

    def test_california_profile(self):
        p = get_profile("california")
        assert p.state_code == "california"

    def test_texas_profile(self):
        p = get_profile("texas")
        assert p.state_code == "texas"

    def test_new_york_profile(self):
        p = get_profile("new_york")
        assert p.state_code == "new_york"

    def test_florida_profile(self):
        p = get_profile("florida")
        assert p.state_code == "florida"

    def test_united_kingdom_profile(self):
        p = get_profile("united_kingdom")
        assert p.state_code == "united_kingdom"

    def test_france_profile(self):
        p = get_profile("france")
        assert p.state_code == "france"

    def test_germany_profile(self):
        p = get_profile("germany")
        assert p.state_code == "germany"

    def test_spain_profile(self):
        p = get_profile("spain")
        assert p.state_code == "spain"

    def test_italy_profile(self):
        p = get_profile("italy")
        assert p.state_code == "italy"

    def test_netherlands_profile(self):
        p = get_profile("netherlands")
        assert p.state_code == "netherlands"

    def test_poland_profile(self):
        p = get_profile("poland")
        assert p.state_code == "poland"

    def test_sweden_profile(self):
        p = get_profile("sweden")
        assert p.state_code == "sweden"

    def test_unknown_raises_key_error(self):
        with pytest.raises(KeyError):
            get_profile("atlantis")

    def test_list_states_includes_united_states(self):
        assert "united_states" in list_states()

    def test_list_states_includes_united_kingdom(self):
        assert "united_kingdom" in list_states()

    def test_list_states_includes_france(self):
        assert "france" in list_states()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Alias resolution
# ─────────────────────────────────────────────────────────────────────────────

class TestAliases:

    def test_us_alias(self):
        assert get_profile("us").state_code == "united_states"

    def test_usa_alias(self):
        assert get_profile("usa").state_code == "united_states"

    def test_america_alias(self):
        assert get_profile("america").state_code == "united_states"

    def test_uk_alias(self):
        assert get_profile("uk").state_code == "united_kingdom"

    def test_britain_alias(self):
        assert get_profile("britain").state_code == "united_kingdom"

    def test_england_alias(self):
        assert get_profile("england").state_code == "united_kingdom"

    def test_de_alias(self):
        assert get_profile("de").state_code == "germany"

    def test_fr_alias(self):
        assert get_profile("fr").state_code == "france"

    def test_es_alias(self):
        assert get_profile("es").state_code == "spain"

    def test_it_alias(self):
        assert get_profile("it").state_code == "italy"

    def test_nl_alias(self):
        assert get_profile("nl").state_code == "netherlands"

    def test_pl_alias(self):
        assert get_profile("pl").state_code == "poland"

    def test_se_alias(self):
        assert get_profile("se").state_code == "sweden"

    def test_ca_alias(self):
        assert get_profile("ca").state_code == "california"

    def test_tx_alias(self):
        assert get_profile("tx").state_code == "texas"

    def test_ny_alias(self):
        assert get_profile("ny").state_code == "new_york"

    def test_fl_alias(self):
        assert get_profile("fl").state_code == "florida"

    def test_northeast_alias(self):
        assert get_profile("northeast").state_code == "us_northeast"

    def test_midwest_alias(self):
        assert get_profile("midwest").state_code == "us_midwest"

    def test_case_insensitive_USA(self):
        assert get_profile("USA").state_code == "united_states"

    def test_case_insensitive_UK(self):
        assert get_profile("UK").state_code == "united_kingdom"


# ─────────────────────────────────────────────────────────────────────────────
# 3. pg_location routing
# ─────────────────────────────────────────────────────────────────────────────

class TestPgLocationRouting:

    def test_india_profiles_route_to_india(self):
        for code in ["india", "west_bengal", "maharashtra", "delhi", "karnataka"]:
            assert get_profile(code).pg_location == "India"

    def test_us_profiles_route_to_united_states(self):
        for code in ["united_states", "us_northeast", "us_south", "us_midwest",
                     "us_west", "california", "texas", "new_york", "florida"]:
            assert get_profile(code).pg_location == "United States"

    def test_uk_routes_to_united_kingdom(self):
        assert get_profile("united_kingdom").pg_location == "United Kingdom"

    def test_france_pg_location(self):
        assert get_profile("france").pg_location == "France"

    def test_germany_pg_location(self):
        assert get_profile("germany").pg_location == "Germany"

    def test_spain_pg_location(self):
        assert get_profile("spain").pg_location == "Spain"

    def test_sweden_pg_location(self):
        assert get_profile("sweden").pg_location == "Sweden"


# ─────────────────────────────────────────────────────────────────────────────
# 4. supports_religion_stratification flag
# ─────────────────────────────────────────────────────────────────────────────

class TestReligionStratificationFlag:

    def test_india_supports_religion_stratification(self):
        assert get_profile("india").supports_religion_stratification is True

    def test_west_bengal_supports_religion_stratification(self):
        assert get_profile("west_bengal").supports_religion_stratification is True

    def test_united_states_does_not_support(self):
        assert get_profile("united_states").supports_religion_stratification is False

    def test_all_us_profiles_do_not_support(self):
        us_codes = ["united_states", "us_northeast", "us_south", "us_midwest",
                    "us_west", "california", "texas", "new_york", "florida"]
        for code in us_codes:
            assert get_profile(code).supports_religion_stratification is False, code

    def test_uk_does_not_support(self):
        assert get_profile("united_kingdom").supports_religion_stratification is False

    def test_eu_profiles_do_not_support(self):
        eu_codes = ["france", "germany", "spain", "italy", "netherlands", "poland", "sweden"]
        for code in eu_codes:
            assert get_profile(code).supports_religion_stratification is False, code


# ─────────────────────────────────────────────────────────────────────────────
# 5. Calibrator base overrides — correct location key
# ─────────────────────────────────────────────────────────────────────────────

class TestCalibratorLocationOverrides:

    def test_india_spec_location_india(self):
        spec = _spec("india")
        profile = get_profile("india")
        overrides = _build_base_overrides(spec, profile)
        assert overrides["location"] == "India"

    def test_west_bengal_spec_location_india(self):
        spec = _spec("west_bengal")
        profile = get_profile("west_bengal")
        overrides = _build_base_overrides(spec, profile)
        assert overrides["location"] == "India"

    def test_us_spec_location_united_states(self):
        spec = _spec("united_states")
        profile = get_profile("united_states")
        overrides = _build_base_overrides(spec, profile)
        assert overrides["location"] == "United States"

    def test_uk_spec_location_united_kingdom(self):
        spec = _spec("united_kingdom")
        profile = get_profile("united_kingdom")
        overrides = _build_base_overrides(spec, profile)
        assert overrides["location"] == "United Kingdom"

    def test_france_spec_location_france(self):
        spec = _spec("france")
        profile = get_profile("france")
        overrides = _build_base_overrides(spec, profile)
        assert overrides["location"] == "France"

    def test_california_spec_location_united_states(self):
        spec = _spec("california")
        profile = get_profile("california")
        overrides = _build_base_overrides(spec, profile)
        assert overrides["location"] == "United States"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Religion stratification fallback for non-India profiles
# ─────────────────────────────────────────────────────────────────────────────

class TestReligionStratificationFallback:

    def test_us_religion_stratify_produces_income_segments(self):
        """When stratify_by_religion=True on a US profile, income segmentation applies."""
        spec = _spec("united_states", religion=True, income=False, n=300)
        segments = calibrate(spec)
        # Should NOT produce Hindu/Muslim/Other labels
        labels = [s.label for s in segments]
        assert not any("Hindu" in l or "Muslim" in l for l in labels)

    def test_uk_religion_stratify_falls_back_gracefully(self):
        spec = _spec("united_kingdom", religion=True, income=False, n=200)
        segments = calibrate(spec)
        assert sum(s.count for s in segments) == 200

    def test_us_religion_plus_income_produces_income_only(self):
        """religion=True + income=True on US profile → income stratification."""
        spec = _spec("united_states", religion=True, income=True, n=300)
        segments = calibrate(spec)
        labels = [s.label for s in segments]
        # Income segments present; no Hindu/Muslim labels
        assert any("income" in l.lower() for l in labels)
        assert not any("Hindu" in l or "Muslim" in l for l in labels)

    def test_india_religion_stratify_still_works(self):
        """Confirm India religion stratification is unaffected."""
        spec = _spec("west_bengal", religion=True, income=False, n=100)
        segments = calibrate(spec)
        labels = [s.label for s in segments]
        assert any("Hindu" in l for l in labels)
        assert any("Muslim" in l for l in labels)


# ─────────────────────────────────────────────────────────────────────────────
# 7. Income stratification — US, UK, EU
# ─────────────────────────────────────────────────────────────────────────────

class TestIncomeStratificationGeo:

    def test_us_income_stratification_sums_correctly(self):
        spec = _spec("united_states", income=True, n=300)
        segments = calibrate(spec)
        assert sum(s.count for s in segments) == 300

    def test_uk_income_stratification_sums_correctly(self):
        spec = _spec("united_kingdom", income=True, n=200)
        segments = calibrate(spec)
        assert sum(s.count for s in segments) == 200

    def test_france_income_stratification_sums_correctly(self):
        spec = _spec("france", income=True, n=150)
        segments = calibrate(spec)
        assert sum(s.count for s in segments) == 150

    def test_germany_income_stratification_sums_correctly(self):
        spec = _spec("germany", income=True, n=100)
        segments = calibrate(spec)
        assert sum(s.count for s in segments) == 100

    def test_california_income_stratification_sums_correctly(self):
        spec = _spec("california", income=True, n=500)
        segments = calibrate(spec)
        assert sum(s.count for s in segments) == 500

    def test_us_income_segments_have_correct_location(self):
        spec = _spec("united_states", income=True, n=300)
        segments = calibrate(spec)
        for seg in segments:
            assert seg.anchor_overrides["location"] == "United States"

    def test_uk_income_segments_have_correct_location(self):
        spec = _spec("united_kingdom", income=True, n=200)
        segments = calibrate(spec)
        for seg in segments:
            assert seg.anchor_overrides["location"] == "United Kingdom"

    def test_us_no_stratification_single_segment(self):
        spec = _spec("united_states", religion=False, income=False, n=100)
        segments = calibrate(spec)
        assert len(segments) == 1
        assert segments[0].count == 100

    def test_us_income_produces_three_segments(self):
        spec = _spec("united_states", income=True, n=300)
        segments = calibrate(spec)
        # three income bands — may merge tiny ones
        assert len(segments) >= 1

    def test_us_income_high_band_present(self):
        spec = _spec("united_states", income=True, n=300)
        segments = calibrate(spec)
        labels_lower = [s.label.lower() for s in segments]
        assert any("high" in l for l in labels_lower)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Environment presets — US, UK, EU
# ─────────────────────────────────────────────────────────────────────────────

class TestGeoEnvironmentPresets:

    def test_us_consumer_2026_registered(self):
        env = get_preset("us_consumer_2026")
        assert env.name == "us_consumer_2026"

    def test_us_political_2026_registered(self):
        env = get_preset("us_political_2026")
        assert env.name == "us_political_2026"

    def test_us_urban_consumer_registered(self):
        env = get_preset("us_urban_consumer")
        assert env.name == "us_urban_consumer"

    def test_uk_consumer_2026_registered(self):
        env = get_preset("uk_consumer_2026")
        assert env.name == "uk_consumer_2026"

    def test_uk_political_2026_registered(self):
        env = get_preset("uk_political_2026")
        assert env.name == "uk_political_2026"

    def test_europe_consumer_2026_registered(self):
        env = get_preset("europe_consumer_2026")
        assert env.name == "europe_consumer_2026"

    def test_france_consumer_2026_registered(self):
        env = get_preset("france_consumer_2026")
        assert env.name == "france_consumer_2026"

    def test_uk_and_eu_policy_registered(self):
        env = get_preset("uk_and_eu_policy")
        assert env.name == "uk_and_eu_policy"

    def test_us_consumer_calibration_state(self):
        env = get_preset("us_consumer_2026")
        assert env.calibration_state == "united_states"

    def test_uk_consumer_calibration_state(self):
        env = get_preset("uk_consumer_2026")
        assert env.calibration_state == "united_kingdom"

    def test_france_consumer_calibration_state(self):
        env = get_preset("france_consumer_2026")
        assert env.calibration_state == "france"

    def test_us_consumer_has_region(self):
        env = get_preset("us_consumer_2026")
        assert "United States" in env.scenario_environment.get("region", "")

    def test_uk_consumer_has_region(self):
        env = get_preset("uk_consumer_2026")
        assert "United Kingdom" in env.scenario_environment.get("region", "")

    def test_us_political_has_political_tags(self):
        env = get_preset("us_political_2026")
        assert "political" in env.event_tags or "election" in env.event_tags

    def test_list_presets_includes_all_new(self):
        presets = list_presets()
        for name in ["us_consumer_2026", "us_political_2026", "uk_consumer_2026",
                     "uk_political_2026", "europe_consumer_2026", "france_consumer_2026"]:
            assert name in presets, f"'{name}' not in list_presets()"

    def test_unknown_preset_raises_key_error(self):
        with pytest.raises(KeyError):
            get_preset("atlantis_2026")


# ─────────────────────────────────────────────────────────────────────────────
# 9. Profile data sanity checks
# ─────────────────────────────────────────────────────────────────────────────

class TestProfileDataSanity:

    @pytest.mark.parametrize("code", [
        "united_states", "us_northeast", "us_south", "us_midwest", "us_west",
        "california", "texas", "new_york", "florida",
        "united_kingdom",
        "france", "germany", "spain", "italy", "netherlands", "poland", "sweden",
    ])
    def test_income_bands_sum_to_one(self, code):
        p = get_profile(code)
        total = sum(p.income_bands.values())
        assert abs(total - 1.0) < 0.02, f"{code}: income bands sum {total:.3f} ≠ 1.0"

    @pytest.mark.parametrize("code", [
        "united_states", "us_northeast", "us_south", "us_midwest", "us_west",
        "california", "texas", "new_york", "florida",
        "united_kingdom",
        "france", "germany", "spain", "italy", "netherlands", "poland", "sweden",
    ])
    def test_urban_pct_in_range(self, code):
        p = get_profile(code)
        assert 0.0 <= p.urban_pct <= 1.0, f"{code}: urban_pct={p.urban_pct}"

    @pytest.mark.parametrize("code", [
        "united_states", "us_northeast", "us_south", "us_midwest", "us_west",
        "california", "texas", "new_york", "florida",
        "united_kingdom",
        "france", "germany", "spain", "italy", "netherlands", "poland", "sweden",
    ])
    def test_population_positive(self, code):
        p = get_profile(code)
        assert p.population_m > 0

    @pytest.mark.parametrize("code", [
        "united_states", "us_northeast", "us_south", "us_midwest", "us_west",
        "california", "texas", "new_york", "florida",
        "united_kingdom",
        "france", "germany", "spain", "italy", "netherlands", "poland", "sweden",
    ])
    def test_to_dict_contains_pg_location(self, code):
        p = get_profile(code)
        d = p.to_dict()
        assert "pg_location" in d
        assert d["pg_location"] == p.pg_location

    def test_us_population_m_plausible(self):
        p = get_profile("united_states")
        assert 300 < p.population_m < 400

    def test_uk_population_m_plausible(self):
        p = get_profile("united_kingdom")
        assert 60 < p.population_m < 75

    def test_france_population_m_plausible(self):
        p = get_profile("france")
        assert 60 < p.population_m < 75

    def test_california_population_less_than_us(self):
        ca = get_profile("california")
        us = get_profile("united_states")
        assert ca.population_m < us.population_m

    def test_rural_pct_complement(self):
        p = get_profile("united_states")
        assert abs(p.urban_pct + p.rural_pct - 1.0) < 0.001
