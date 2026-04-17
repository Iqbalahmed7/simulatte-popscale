"""Week 8 Environment Tests — SimulationEnvironment presets and renderer integration.

Tests:
    1. SimulationEnvironment — structure and to_dict()
    2. apply_environment() — merges scenario_environment; caller values win
    3. build_population_spec() — produces valid PopulationSpec from preset
    4. get_preset() / list_presets() — registry
    5. Named presets — West Bengal and others, data validity
    6. Renderer integration — environment summary appears in rendered strings

Run all (no live API calls needed):
    python3 -m pytest tests/test_week8_environment.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

_POPSCALE_ROOT = Path(__file__).parents[1]
if str(_POPSCALE_ROOT) not in sys.path:
    sys.path.insert(0, str(_POPSCALE_ROOT))

import pytest

from popscale.environment import (
    SimulationEnvironment,
    WEST_BENGAL_POLITICAL_2026,
    INDIA_NATIONAL_POLICY,
    INDIA_URBAN_CONSUMER,
    INDIA_RURAL_ECONOMY,
    MAHARASHTRA_CONSUMER,
    apply_environment,
    build_population_spec,
    get_preset,
    list_presets,
)
from popscale.scenario.model import Scenario, SimulationDomain
from popscale.scenario.renderer import render_stimulus, render_decision_scenario
from popscale.calibration.population_spec import PopulationSpec


# ── Shared fixtures ───────────────────────────────────────────────────────────

BASE_SCENARIO = Scenario(
    question="Will you vote for the incumbent party in the upcoming election?",
    context=(
        "State elections are scheduled for next month. Fuel prices have risen 40% "
        "and the opposition is campaigning on economic relief. You will need to "
        "decide which party best represents your interests."
    ),
    options=["Yes, incumbent", "No, opposition", "Undecided"],
    domain=SimulationDomain.POLITICAL,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. SimulationEnvironment — structure
# ─────────────────────────────────────────────────────────────────────────────

class TestSimulationEnvironmentStructure:

    def test_preset_has_name(self):
        assert WEST_BENGAL_POLITICAL_2026.name == "west_bengal_political_2026"

    def test_preset_has_description(self):
        assert len(WEST_BENGAL_POLITICAL_2026.description) > 20

    def test_preset_has_region(self):
        assert WEST_BENGAL_POLITICAL_2026.region

    def test_preset_has_calibration_state(self):
        assert WEST_BENGAL_POLITICAL_2026.calibration_state == "west_bengal"

    def test_preset_has_scenario_environment(self):
        assert isinstance(WEST_BENGAL_POLITICAL_2026.scenario_environment, dict)
        assert len(WEST_BENGAL_POLITICAL_2026.scenario_environment) > 0

    def test_preset_has_event_tags(self):
        assert isinstance(WEST_BENGAL_POLITICAL_2026.event_tags, list)
        assert "bengal" in WEST_BENGAL_POLITICAL_2026.event_tags

    def test_to_dict_keys(self):
        d = WEST_BENGAL_POLITICAL_2026.to_dict()
        for key in ("name", "description", "region", "calibration_state",
                    "scenario_environment", "default_spec_kwargs", "event_tags"):
            assert key in d

    def test_all_presets_have_valid_calibration_state(self):
        from popscale.calibration.profiles import get_profile
        for name in list_presets():
            preset = get_preset(name)
            # Should not raise
            profile = get_profile(preset.calibration_state)
            assert profile is not None

    def test_all_presets_have_region(self):
        for name in list_presets():
            preset = get_preset(name)
            assert preset.region


# ─────────────────────────────────────────────────────────────────────────────
# 2. apply_environment()
# ─────────────────────────────────────────────────────────────────────────────

class TestApplyEnvironment:

    def test_returns_new_scenario(self):
        enriched = apply_environment(BASE_SCENARIO, WEST_BENGAL_POLITICAL_2026)
        assert enriched is not BASE_SCENARIO

    def test_original_scenario_unchanged(self):
        original_env = dict(BASE_SCENARIO.environment)
        apply_environment(BASE_SCENARIO, WEST_BENGAL_POLITICAL_2026)
        assert BASE_SCENARIO.environment == original_env

    def test_scenario_environment_set_from_preset(self):
        enriched = apply_environment(BASE_SCENARIO, WEST_BENGAL_POLITICAL_2026)
        assert "region" in enriched.environment
        assert "West Bengal" in enriched.environment["region"]

    def test_caller_values_win_over_preset(self):
        # If caller already set 'region', preset should not override it
        scenario_with_env = BASE_SCENARIO.model_copy(
            update={"environment": {"region": "CALLER_SET_REGION"}}
        )
        enriched = apply_environment(scenario_with_env, WEST_BENGAL_POLITICAL_2026)
        assert enriched.environment["region"] == "CALLER_SET_REGION"

    def test_preset_keys_added_when_not_in_caller(self):
        enriched = apply_environment(BASE_SCENARIO, WEST_BENGAL_POLITICAL_2026)
        assert "economic_sentiment" in enriched.environment
        assert "public_trust_level" in enriched.environment

    def test_scenario_question_preserved(self):
        enriched = apply_environment(BASE_SCENARIO, WEST_BENGAL_POLITICAL_2026)
        assert enriched.question == BASE_SCENARIO.question

    def test_scenario_options_preserved(self):
        enriched = apply_environment(BASE_SCENARIO, WEST_BENGAL_POLITICAL_2026)
        assert enriched.options == BASE_SCENARIO.options

    def test_urban_consumer_preset(self):
        enriched = apply_environment(BASE_SCENARIO, INDIA_URBAN_CONSUMER)
        assert "Urban India" in enriched.environment.get("region", "")

    def test_rural_economy_preset(self):
        enriched = apply_environment(BASE_SCENARIO, INDIA_RURAL_ECONOMY)
        assert "Rural India" in enriched.environment.get("region", "")


# ─────────────────────────────────────────────────────────────────────────────
# 3. build_population_spec()
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildPopulationSpec:

    def test_returns_population_spec(self):
        spec = build_population_spec(
            env=WEST_BENGAL_POLITICAL_2026,
            n_personas=100,
            domain="policy",
            business_problem="Test research.",
        )
        assert isinstance(spec, PopulationSpec)

    def test_state_set_from_env(self):
        spec = build_population_spec(
            env=WEST_BENGAL_POLITICAL_2026,
            n_personas=50,
            domain="policy",
            business_problem="Test.",
        )
        assert spec.state == "west_bengal"

    def test_n_personas_set_correctly(self):
        spec = build_population_spec(
            env=WEST_BENGAL_POLITICAL_2026,
            n_personas=200,
            domain="policy",
            business_problem="Test.",
        )
        assert spec.n_personas == 200

    def test_default_spec_kwargs_applied(self):
        # WB preset sets stratify_by_religion=True by default
        spec = build_population_spec(
            env=WEST_BENGAL_POLITICAL_2026,
            n_personas=50,
            domain="policy",
            business_problem="Test.",
        )
        assert spec.stratify_by_religion is True

    def test_override_default_kwarg(self):
        spec = build_population_spec(
            env=WEST_BENGAL_POLITICAL_2026,
            n_personas=50,
            domain="policy",
            business_problem="Test.",
            stratify_by_religion=False,   # override preset default
        )
        assert spec.stratify_by_religion is False

    def test_urban_only_for_urban_consumer_preset(self):
        spec = build_population_spec(
            env=INDIA_URBAN_CONSUMER,
            n_personas=100,
            domain="consumer",
            business_problem="Test.",
        )
        assert spec.urban_only is True

    def test_rural_only_for_rural_economy_preset(self):
        spec = build_population_spec(
            env=INDIA_RURAL_ECONOMY,
            n_personas=100,
            domain="consumer",
            business_problem="Test.",
        )
        assert spec.rural_only is True

    def test_sarvam_enabled_true_for_india_preset(self):
        # India presets explicitly set sarvam_enabled=True in default_spec_kwargs.
        spec = build_population_spec(
            env=INDIA_NATIONAL_POLICY,
            n_personas=50,
            domain="policy",
            business_problem="Test.",
        )
        assert spec.sarvam_enabled is True


# ─────────────────────────────────────────────────────────────────────────────
# 4. get_preset() / list_presets()
# ─────────────────────────────────────────────────────────────────────────────

class TestRegistry:

    def test_list_presets_returns_sorted_list(self):
        names = list_presets()
        assert names == sorted(names)

    def test_list_presets_contains_wb(self):
        assert "west_bengal_political_2026" in list_presets()

    def test_list_presets_contains_india_national(self):
        assert "india_national_policy" in list_presets()

    def test_list_presets_has_india_presets(self):
        # Validates India presets exist (geography expansion adds US/UK/EU presets too)
        india_presets = [p for p in list_presets() if any(
            k in p for k in ["india", "west_bengal", "maharashtra"]
        )]
        assert len(india_presets) >= 5

    def test_get_preset_by_name(self):
        preset = get_preset("west_bengal_political_2026")
        assert preset.name == "west_bengal_political_2026"

    def test_get_preset_unknown_raises(self):
        with pytest.raises(KeyError, match="No environment preset"):
            get_preset("atlantis_consumer_2099")

    def test_get_preset_all_names_resolve(self):
        for name in list_presets():
            preset = get_preset(name)
            assert preset.name == name


# ─────────────────────────────────────────────────────────────────────────────
# 5. Named presets — data validity
# ─────────────────────────────────────────────────────────────────────────────

class TestNamedPresets:

    def test_wb_preset_has_cultural_context(self):
        env = WEST_BENGAL_POLITICAL_2026.scenario_environment
        assert "cultural_context" in env
        assert "Bengali" in env["cultural_context"]

    def test_wb_preset_has_stressed_economic_sentiment(self):
        env = WEST_BENGAL_POLITICAL_2026.scenario_environment
        assert "economic_sentiment" in env
        assert "stressed" in env["economic_sentiment"].lower()

    def test_india_national_has_income_stratification(self):
        assert INDIA_NATIONAL_POLICY.default_spec_kwargs.get("stratify_by_income") is True

    def test_india_urban_has_urban_only(self):
        assert INDIA_URBAN_CONSUMER.default_spec_kwargs.get("urban_only") is True

    def test_india_rural_has_rural_only(self):
        assert INDIA_RURAL_ECONOMY.default_spec_kwargs.get("rural_only") is True

    def test_maharashtra_calibration_state(self):
        assert MAHARASHTRA_CONSUMER.calibration_state == "maharashtra"

    def test_no_preset_sets_conflicting_urban_rural(self):
        for name in list_presets():
            preset = get_preset(name)
            kwargs = preset.default_spec_kwargs
            assert not (kwargs.get("urban_only") and kwargs.get("rural_only")), \
                f"{name}: both urban_only and rural_only set"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Renderer integration
# ─────────────────────────────────────────────────────────────────────────────

class TestRendererIntegration:

    def test_render_stimulus_without_env_no_env_section(self):
        stimulus = render_stimulus(BASE_SCENARIO)
        # Should not contain "Environment:" line since no env set
        # (base scenario has empty environment)
        assert "POLITICAL SCENARIO" in stimulus

    def test_render_stimulus_with_env_contains_region(self):
        enriched = apply_environment(BASE_SCENARIO, WEST_BENGAL_POLITICAL_2026)
        stimulus = render_stimulus(enriched)
        assert "West Bengal" in stimulus

    def test_render_stimulus_with_env_contains_environment_section(self):
        enriched = apply_environment(BASE_SCENARIO, WEST_BENGAL_POLITICAL_2026)
        stimulus = render_stimulus(enriched)
        assert "Environment:" in stimulus

    def test_render_decision_with_env_contains_context(self):
        enriched = apply_environment(BASE_SCENARIO, WEST_BENGAL_POLITICAL_2026)
        decision = render_decision_scenario(enriched)
        assert "Context:" in decision

    def test_render_decision_with_env_contains_region(self):
        enriched = apply_environment(BASE_SCENARIO, WEST_BENGAL_POLITICAL_2026)
        decision = render_decision_scenario(enriched)
        assert "West Bengal" in decision

    def test_render_stimulus_national_policy(self):
        national_scenario = Scenario(
            question="Do you support the new national data privacy regulation?",
            context=(
                "The Digital Data Protection Act requires explicit consent for all "
                "data collection. It applies to companies with >10k Indian users. "
                "Implementation starts in 3 months."
            ),
            domain=SimulationDomain.POLICY,
        )
        enriched = apply_environment(national_scenario, INDIA_NATIONAL_POLICY)
        stimulus = render_stimulus(enriched)
        assert "India" in stimulus

    def test_environment_summary_in_rendered_output(self):
        enriched = apply_environment(BASE_SCENARIO, WEST_BENGAL_POLITICAL_2026)
        # environment_summary() should include the preset's key-value pairs
        summary = enriched.environment_summary()
        assert summary != "No specific environmental context provided."
        assert len(summary) > 10

    def test_decision_scenario_contains_question(self):
        enriched = apply_environment(BASE_SCENARIO, WEST_BENGAL_POLITICAL_2026)
        decision = render_decision_scenario(enriched)
        assert "incumbent party" in decision

    def test_decision_scenario_contains_options(self):
        enriched = apply_environment(BASE_SCENARIO, WEST_BENGAL_POLITICAL_2026)
        decision = render_decision_scenario(enriched)
        assert "Yes, incumbent" in decision
        assert "No, opposition" in decision
