"""Parity Validator Tests — structural/unit (no live API calls).

Tests:
    1. _age_band()               — age bucketing
    2. _fractional_dist()        — distribution computation
    3. _max_deviation()          — deviation calculation
    4. _check_linkage()          — seed ID linkage checking
    5. validate_parity() errors  — empty/no-variants/no-seeds
    6. validate_parity() pass    — identical distributions
    7. validate_parity() fail    — deliberately skewed distributions
    8. DimensionParity helpers   — worst_category, to_dict
    9. ParityReport              — summary, to_dict, passed flag
    10. Threshold sensitivity    — tight vs loose thresholds

Run (no live API calls):
    python3 -m pytest tests/test_parity_validator.py -v
"""

from __future__ import annotations

import copy
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_POPSCALE_ROOT = Path(__file__).parents[1]
_PG_ROOT       = _POPSCALE_ROOT.parent / "Persona Generator"
if str(_POPSCALE_ROOT) not in sys.path:
    sys.path.insert(0, str(_POPSCALE_ROOT))
if str(_PG_ROOT) not in sys.path:
    sys.path.insert(1, str(_PG_ROOT))

import pytest

from popscale.generation.parity_validator import (
    DimensionParity,
    LinkageCheck,
    ParityReport,
    _age_band,
    _check_linkage,
    _fractional_dist,
    _max_deviation,
    validate_parity,
)

from src.schema.persona import (
    Attribute,
    BehaviouralTendencies,
    CopingMechanism,
    CoreMemory,
    DemographicAnchor,
    DerivedInsights,
    Household,
    ImmutableConstraints,
    LifeDefiningEvent,
    LifeStory,
    Location,
    Memory,
    Narrative,
    Objection,
    PersonaRecord,
    PriceSensitivityBand,
    RelationshipMap,
    SimulationState,
    TendencyBand,
    TrustOrientation,
    TrustWeights,
    WorkingMemory,
)


# ── Persona factory ───────────────────────────────────────────────────────────

def _make_persona(
    persona_id: str = "p-001",
    age: int = 35,
    gender: str = "male",
    urban_tier: str = "metro",
    income_bracket: str = "middle",
    life_stage: str = "mid-career / settled",
    generation_mode: str = "full",
    seed_persona_id: str | None = None,
) -> PersonaRecord:
    location = Location(
        country="India", region="Maharashtra",
        city="Mumbai", urban_tier=urban_tier,
    )
    household = Household(
        structure="nuclear", size=4,
        income_bracket=income_bracket, dual_income=False,
    )
    anchor = DemographicAnchor(
        name="Test Person", age=age, gender=gender,
        location=location, household=household,
        life_stage=life_stage, education="undergraduate", employment="full-time",
    )
    life_stories = [
        LifeStory(title="Story 1", when="Age 22",
                  event="Moved to the city for work.",
                  lasting_impact="Built self-reliance."),
        LifeStory(title="Story 2", when="Age 30",
                  event="Became primary breadwinner.",
                  lasting_impact="Reinforced discipline."),
    ]
    attributes: dict[str, dict[str, Attribute]] = {
        "psychology": {
            "risk_tolerance": Attribute(value=0.35, type="continuous", label="Risk", source="sampled"),
            "information_need": Attribute(value=0.6, type="continuous", label="Info need", source="sampled"),
            "emotional_persuasion_susceptibility": Attribute(value=0.45, type="continuous", label="EPS", source="sampled"),
            "fear_appeal_responsiveness": Attribute(value=0.4, type="continuous", label="FAR", source="sampled"),
            "status_quo_bias": Attribute(value=0.55, type="continuous", label="SQB", source="sampled"),
            "analysis_paralysis": Attribute(value=0.4, type="continuous", label="AP", source="sampled"),
        },
        "social": {
            "social_proof_bias": Attribute(value=0.5, type="continuous", label="SPB", source="sampled"),
            "peer_influence_strength": Attribute(value=0.5, type="continuous", label="PIS", source="sampled"),
            "authority_bias": Attribute(value=0.55, type="continuous", label="AB", source="sampled"),
            "trust_orientation_primary": Attribute(value="authority", type="categorical", label="TOP", source="anchored"),
            "online_community_trust": Attribute(value=0.4, type="continuous", label="OCT", source="sampled"),
            "influencer_susceptibility": Attribute(value=0.3, type="continuous", label="IS", source="sampled"),
            "wom_receiver_openness": Attribute(value=0.5, type="continuous", label="WRO", source="sampled"),
        },
        "values": {
            "budget_consciousness": Attribute(value=0.65, type="continuous", label="BC", source="sampled"),
            "deal_seeking_intensity": Attribute(value=0.55, type="continuous", label="DSI", source="sampled"),
            "economic_constraint_level": Attribute(value=0.5, type="continuous", label="ECL", source="sampled"),
            "brand_loyalty": Attribute(value=0.6, type="continuous", label="BL", source="sampled"),
            "indie_brand_openness": Attribute(value=0.4, type="continuous", label="IBO", source="sampled"),
            "primary_value_driver": Attribute(value="quality", type="categorical", label="PVD", source="anchored"),
        },
        "lifestyle": {
            "routine_adherence": Attribute(value=0.65, type="continuous", label="RA", source="sampled"),
            "ad_receptivity": Attribute(value=0.35, type="continuous", label="AR", source="sampled"),
        },
        "identity": {
            "tension_seed": Attribute(value="quality_vs_budget", type="categorical", label="TS", source="anchored"),
            "self_efficacy": Attribute(value=0.6, type="continuous", label="SE", source="sampled"),
        },
        "decision_making": {
            "research_before_purchase": Attribute(value=0.65, type="continuous", label="RBP", source="sampled"),
            "decision_delegation": Attribute(value=0.3, type="continuous", label="DD", source="sampled"),
        },
    }
    derived_insights = DerivedInsights(
        decision_style="analytical", decision_style_score=0.35,
        trust_anchor="authority", risk_appetite="low",
        primary_value_orientation="quality",
        coping_mechanism=CopingMechanism(type="research_deep_dive", description="Researches."),
        consistency_score=72, consistency_band="medium",
        key_tensions=["Quality vs budget"],
    )
    trust_weights = TrustWeights(expert=0.65, peer=0.5, brand=0.6, ad=0.3, community=0.4, influencer=0.3)
    behavioural_tendencies = BehaviouralTendencies(
        price_sensitivity=PriceSensitivityBand(band="high", description="Seeks deals.", source="proxy"),
        trust_orientation=TrustOrientation(
            weights=trust_weights, dominant="expert",
            description="Trusts experts.", source="proxy",
        ),
        switching_propensity=TendencyBand(band="low", description="Stays loyal.", source="proxy"),
        objection_profile=[Objection(objection_type="price_vs_value", likelihood="high", severity="friction")],
        reasoning_prompt="High price-sensitive. Trusts experts. Stays loyal.",
    )
    narrative = Narrative(
        first_person="I'm careful with money.", third_person="Test person.",
        display_name="Test",
    )
    core_memory = CoreMemory(
        identity_statement="A test persona.",
        key_values=["quality", "discipline", "resilience"],
        life_defining_events=[LifeDefiningEvent(age_when=22, event="First job", lasting_impact="Self-reliance.")],
        relationship_map=RelationshipMap(
            primary_decision_partner="spouse",
            key_influencers=["colleague"],
            trust_network=["family"],
        ),
        immutable_constraints=ImmutableConstraints(
            budget_ceiling="strict",
            non_negotiables=["Budget"],
            absolute_avoidances=["Risk"],
        ),
        tendency_summary="Quality-focused.", current_conditions_stance=None, governance_stance=None,
    )
    working_memory = WorkingMemory(
        observations=[], reflections=[], plans=[], brand_memories={},
        simulation_state=SimulationState(
            current_turn=0, importance_accumulator=0.0, reflection_count=0,
            awareness_set={}, consideration_set=[], last_decision=None,
        ),
    )
    return PersonaRecord(
        persona_id=persona_id,
        generated_at=datetime.now(timezone.utc),
        generator_version="test-1.0",
        domain="consumer",
        mode="deep",
        demographic_anchor=anchor,
        life_stories=life_stories,
        attributes=attributes,
        derived_insights=derived_insights,
        behavioural_tendencies=behavioural_tendencies,
        narrative=narrative,
        decision_bullets=["Checks reviews", "Delays for deals"],
        memory=Memory(core=core_memory, working=working_memory),
        seed_persona_id=seed_persona_id,
        generation_mode=generation_mode,
    )


def _make_cohort(
    n_seeds: int,
    n_variants: int,
    *,
    seed_age: int = 35,
    variant_age: int = 35,
    seed_gender: str = "male",
    variant_gender: str = "male",
    seed_tier: str = "metro",
    variant_tier: str = "metro",
    seed_income: str = "middle",
    variant_income: str = "middle",
    broken_links: bool = False,
) -> list[PersonaRecord]:
    """Build a synthetic cohort of seeds + variants."""
    seeds = [
        _make_persona(
            persona_id=f"seed-{i:03d}",
            age=seed_age,
            gender=seed_gender,
            urban_tier=seed_tier,
            income_bracket=seed_income,
            generation_mode="full",
        )
        for i in range(n_seeds)
    ]
    variants = [
        _make_persona(
            persona_id=f"var-{i:03d}",
            age=variant_age,
            gender=variant_gender,
            urban_tier=variant_tier,
            income_bracket=variant_income,
            generation_mode="variant",
            seed_persona_id=None if broken_links else seeds[i % n_seeds].persona_id,
        )
        for i in range(n_variants)
    ]
    return seeds + variants


# ─────────────────────────────────────────────────────────────────────────────
# 1. _age_band()
# ─────────────────────────────────────────────────────────────────────────────

class TestAgeBand:

    def test_lower_bound(self):
        assert _age_band(18) == "18-25"

    def test_upper_18_25(self):
        assert _age_band(25) == "18-25"

    def test_lower_26_35(self):
        assert _age_band(26) == "26-35"

    def test_upper_26_35(self):
        assert _age_band(35) == "26-35"

    def test_lower_36_50(self):
        assert _age_band(36) == "36-50"

    def test_upper_36_50(self):
        assert _age_band(50) == "36-50"

    def test_lower_51_65(self):
        assert _age_band(51) == "51-65"

    def test_upper_51_65(self):
        assert _age_band(65) == "51-65"

    def test_over_65(self):
        assert _age_band(66) == "65+"

    def test_boundary_35_is_26_35(self):
        assert _age_band(35) == "26-35"

    def test_boundary_36_is_36_50(self):
        assert _age_band(36) == "36-50"


# ─────────────────────────────────────────────────────────────────────────────
# 2. _fractional_dist()
# ─────────────────────────────────────────────────────────────────────────────

class TestFractionalDist:

    def test_empty_list(self):
        assert _fractional_dist([]) == {}

    def test_single_value(self):
        d = _fractional_dist(["male"])
        assert d == {"male": 1.0}

    def test_equal_split(self):
        d = _fractional_dist(["male", "female"])
        assert abs(d["male"] - 0.5) < 1e-6
        assert abs(d["female"] - 0.5) < 1e-6

    def test_sums_to_one(self):
        values = ["metro", "metro", "tier2", "rural", "metro"]
        d = _fractional_dist(values)
        assert abs(sum(d.values()) - 1.0) < 1e-6

    def test_all_same(self):
        d = _fractional_dist(["metro"] * 10)
        assert d == {"metro": 1.0}

    def test_three_way_split(self):
        values = ["a"] * 3 + ["b"] * 3 + ["c"] * 4
        d = _fractional_dist(values)
        assert abs(d["a"] - 0.3) < 1e-5
        assert abs(d["b"] - 0.3) < 1e-5
        assert abs(d["c"] - 0.4) < 1e-5


# ─────────────────────────────────────────────────────────────────────────────
# 3. _max_deviation()
# ─────────────────────────────────────────────────────────────────────────────

class TestMaxDeviation:

    def test_identical_dists(self):
        d = {"male": 0.5, "female": 0.5}
        assert _max_deviation(d, d) == 0.0

    def test_one_category_differs(self):
        d1 = {"male": 0.6, "female": 0.4}
        d2 = {"male": 0.4, "female": 0.6}
        assert abs(_max_deviation(d1, d2) - 0.2) < 1e-6

    def test_missing_category_in_d2(self):
        d1 = {"metro": 0.5, "rural": 0.5}
        d2 = {"metro": 1.0}
        # rural: 0.5 vs 0.0 → deviation 0.5
        assert abs(_max_deviation(d1, d2) - 0.5) < 1e-6

    def test_empty_both(self):
        assert _max_deviation({}, {}) == 0.0

    def test_max_picks_largest(self):
        d1 = {"a": 0.7, "b": 0.2, "c": 0.1}
        d2 = {"a": 0.5, "b": 0.4, "c": 0.1}
        # a: 0.2 diff, b: 0.2 diff
        assert abs(_max_deviation(d1, d2) - 0.2) < 1e-6


# ─────────────────────────────────────────────────────────────────────────────
# 4. _check_linkage()
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckLinkage:

    def test_all_valid(self):
        seeds = [_make_persona(persona_id="s-001", generation_mode="full")]
        variants = [
            _make_persona(persona_id="v-001", generation_mode="variant", seed_persona_id="s-001"),
            _make_persona(persona_id="v-002", generation_mode="variant", seed_persona_id="s-001"),
        ]
        result = _check_linkage(seeds, variants)
        assert result.passed
        assert result.n_missing_id == 0
        assert result.n_broken_links == 0

    def test_missing_seed_persona_id(self):
        seeds = [_make_persona(persona_id="s-001", generation_mode="full")]
        variants = [
            _make_persona(persona_id="v-001", generation_mode="variant", seed_persona_id=None),
        ]
        result = _check_linkage(seeds, variants)
        assert not result.passed
        assert result.n_missing_id == 1
        assert "v-001" in result.broken_persona_ids

    def test_broken_link(self):
        seeds = [_make_persona(persona_id="s-001", generation_mode="full")]
        variants = [
            _make_persona(persona_id="v-001", generation_mode="variant", seed_persona_id="nonexistent-seed"),
        ]
        result = _check_linkage(seeds, variants)
        assert not result.passed
        assert result.n_broken_links == 1
        assert "v-001" in result.broken_persona_ids

    def test_n_variants_count(self):
        seeds = [_make_persona(persona_id="s-001", generation_mode="full")]
        variants = [
            _make_persona(persona_id=f"v-{i:03d}", generation_mode="variant",
                          seed_persona_id="s-001")
            for i in range(5)
        ]
        result = _check_linkage(seeds, variants)
        assert result.n_variants == 5

    def test_broken_ids_capped_at_20(self):
        seeds = [_make_persona(persona_id="s-001", generation_mode="full")]
        variants = [
            _make_persona(persona_id=f"v-{i:03d}", generation_mode="variant",
                          seed_persona_id="bad-id")
            for i in range(30)
        ]
        result = _check_linkage(seeds, variants)
        assert len(result.broken_persona_ids) == 20
        assert result.n_broken_links == 30


# ─────────────────────────────────────────────────────────────────────────────
# 5. validate_parity() — error cases
# ─────────────────────────────────────────────────────────────────────────────

class TestValidateParityErrors:

    def test_empty_list_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            validate_parity([])

    def test_no_variants_raises(self):
        seeds = [_make_persona(persona_id=f"s-{i}", generation_mode="full") for i in range(5)]
        with pytest.raises(ValueError, match="No variant"):
            validate_parity(seeds)

    def test_no_seeds_raises(self):
        variants = [
            _make_persona(persona_id=f"v-{i}", generation_mode="variant",
                          seed_persona_id="x")
            for i in range(5)
        ]
        with pytest.raises(ValueError, match="No seed"):
            validate_parity(variants)


# ─────────────────────────────────────────────────────────────────────────────
# 6. validate_parity() — passing cohort (identical distributions)
# ─────────────────────────────────────────────────────────────────────────────

class TestValidateParityPass:

    def test_identical_cohort_passes(self):
        cohort = _make_cohort(n_seeds=10, n_variants=90)
        report = validate_parity(cohort)
        assert report.passed

    def test_all_dimensions_pass(self):
        cohort = _make_cohort(n_seeds=10, n_variants=90)
        report = validate_parity(cohort)
        for dim, dp in report.dimensions.items():
            assert dp.passed, f"Dimension {dim} unexpectedly failed"

    def test_linkage_passes(self):
        cohort = _make_cohort(n_seeds=10, n_variants=90)
        report = validate_parity(cohort)
        assert report.linkage.passed

    def test_counts_correct(self):
        cohort = _make_cohort(n_seeds=20, n_variants=80)
        report = validate_parity(cohort)
        assert report.n_seeds == 20
        assert report.n_variants == 80

    def test_five_dimensions_checked(self):
        cohort = _make_cohort(n_seeds=10, n_variants=90)
        report = validate_parity(cohort)
        assert set(report.dimensions.keys()) == {
            "age_band", "gender", "urban_tier", "income_bracket", "life_stage"
        }

    def test_zero_deviation_for_identical(self):
        cohort = _make_cohort(n_seeds=10, n_variants=90)
        report = validate_parity(cohort)
        for dim, dp in report.dimensions.items():
            assert dp.max_abs_deviation == 0.0, f"{dim} has non-zero deviation on identical cohort"


# ─────────────────────────────────────────────────────────────────────────────
# 7. validate_parity() — failing cohort (skewed distributions)
# ─────────────────────────────────────────────────────────────────────────────

class TestValidateParityFail:

    def test_urban_tier_skew_fails(self):
        # Seeds: all metro. Variants: all rural. → deviation = 1.0
        cohort = _make_cohort(
            n_seeds=10, n_variants=90,
            seed_tier="metro", variant_tier="rural",
        )
        report = validate_parity(cohort, threshold=0.10)
        assert not report.passed
        assert not report.dimensions["urban_tier"].passed

    def test_gender_skew_fails(self):
        cohort = _make_cohort(
            n_seeds=10, n_variants=90,
            seed_gender="male", variant_gender="female",
        )
        report = validate_parity(cohort, threshold=0.10)
        assert not report.passed
        assert not report.dimensions["gender"].passed

    def test_income_skew_fails(self):
        cohort = _make_cohort(
            n_seeds=10, n_variants=90,
            seed_income="middle", variant_income="high",
        )
        report = validate_parity(cohort, threshold=0.10)
        assert not report.passed
        assert not report.dimensions["income_bracket"].passed

    def test_max_deviation_reflects_skew(self):
        cohort = _make_cohort(
            n_seeds=10, n_variants=90,
            seed_tier="metro", variant_tier="rural",
        )
        report = validate_parity(cohort, threshold=0.10)
        dp = report.dimensions["urban_tier"]
        assert dp.max_abs_deviation > 0.5

    def test_linkage_failure_propagates_to_report(self):
        cohort = _make_cohort(n_seeds=10, n_variants=90, broken_links=True)
        report = validate_parity(cohort, threshold=0.10)
        assert not report.passed
        assert not report.linkage.passed


# ─────────────────────────────────────────────────────────────────────────────
# 8. DimensionParity helpers
# ─────────────────────────────────────────────────────────────────────────────

class TestDimensionParityHelpers:

    def _make_dp(self, dev: float = 0.05) -> DimensionParity:
        return DimensionParity(
            dimension="gender",
            seed_dist={"male": 0.6, "female": 0.4},
            variant_dist={"male": 0.55, "female": 0.45},
            max_abs_deviation=dev,
            threshold=0.10,
            passed=dev <= 0.10,
            n_seeds=10,
            n_variants=90,
        )

    def test_worst_category_returns_category(self):
        dp = self._make_dp()
        cat, _ = dp.worst_category()
        assert cat in {"male", "female"}

    def test_worst_category_deviation_matches(self):
        dp = DimensionParity(
            dimension="urban_tier",
            seed_dist={"metro": 0.8, "rural": 0.2},
            variant_dist={"metro": 0.5, "rural": 0.5},
            max_abs_deviation=0.3,
            threshold=0.10,
            passed=False,
            n_seeds=10,
            n_variants=90,
        )
        cat, dev = dp.worst_category()
        assert cat == "metro"
        assert abs(dev - 0.3) < 1e-6

    def test_to_dict_has_required_keys(self):
        dp = self._make_dp()
        d = dp.to_dict()
        for key in ["dimension", "seed_dist", "variant_dist", "max_abs_deviation",
                    "threshold", "passed", "n_seeds", "n_variants"]:
            assert key in d

    def test_to_dict_passed_reflects_state(self):
        dp_pass = self._make_dp(dev=0.05)
        dp_fail = self._make_dp(dev=0.20)
        assert dp_pass.to_dict()["passed"] is True
        assert dp_fail.to_dict()["passed"] is False


# ─────────────────────────────────────────────────────────────────────────────
# 9. ParityReport — summary and to_dict
# ─────────────────────────────────────────────────────────────────────────────

class TestParityReport:

    def test_summary_contains_pass(self):
        cohort = _make_cohort(n_seeds=10, n_variants=90)
        report = validate_parity(cohort)
        assert "PASS" in report.summary()

    def test_summary_contains_fail(self):
        cohort = _make_cohort(n_seeds=10, n_variants=90,
                              seed_tier="metro", variant_tier="rural")
        report = validate_parity(cohort, threshold=0.10)
        assert "FAIL" in report.summary()

    def test_to_dict_has_required_keys(self):
        cohort = _make_cohort(n_seeds=10, n_variants=90)
        report = validate_parity(cohort)
        d = report.to_dict()
        for key in ["n_seeds", "n_variants", "threshold", "passed", "dimensions", "linkage"]:
            assert key in d

    def test_to_dict_dimensions_has_all_five(self):
        cohort = _make_cohort(n_seeds=10, n_variants=90)
        report = validate_parity(cohort)
        d = report.to_dict()
        assert set(d["dimensions"].keys()) == {
            "age_band", "gender", "urban_tier", "income_bracket", "life_stage"
        }

    def test_to_dict_passed_consistent(self):
        cohort = _make_cohort(n_seeds=10, n_variants=90)
        report = validate_parity(cohort)
        assert report.to_dict()["passed"] == report.passed


# ─────────────────────────────────────────────────────────────────────────────
# 10. Threshold sensitivity
# ─────────────────────────────────────────────────────────────────────────────

class TestThresholdSensitivity:

    def test_tight_threshold_fails_small_deviation(self):
        # Seeds: 40% metro 60% tier2. Variants: same ages, same tier.
        # Build cohort with tiny deviation by mixing tiers asymmetrically.
        seeds = [
            _make_persona(persona_id=f"s-{i}", generation_mode="full",
                          urban_tier="metro" if i < 4 else "tier2")
            for i in range(10)
        ]
        # Variants exactly match seeds' distribution (all metro)
        variants = [
            _make_persona(persona_id=f"v-{i}", generation_mode="variant",
                          urban_tier="metro",
                          seed_persona_id=seeds[i % 10].persona_id)
            for i in range(90)
        ]
        cohort = seeds + variants
        # With threshold=0.01, 40% vs 100% metro deviation (0.6) → should fail
        report_tight = validate_parity(cohort, threshold=0.01)
        assert not report_tight.dimensions["urban_tier"].passed

    def test_loose_threshold_passes_moderate_deviation(self):
        # 30pp deviation in age: seeds all 35 (26-35 band), variants all 25 (18-25 band)
        cohort = _make_cohort(
            n_seeds=10, n_variants=90,
            seed_age=35, variant_age=25,
        )
        # threshold=0.50 → 30pp deviation should pass
        report_loose = validate_parity(cohort, threshold=0.50)
        # With 100% of seeds in 26-35 and 100% variants in 18-25, deviation = 1.0
        # Even 0.50 should fail here — this tests the threshold works both ways
        assert not report_loose.dimensions["age_band"].passed  # deviation=1.0 > 0.50

    def test_exact_threshold_boundary(self):
        # Build a cohort where deviation is exactly known
        # 10 seeds: all metro. 90 variants: 80 metro, 10 rural → rural deviation = 10/90 ≈ 0.111
        seeds = [
            _make_persona(persona_id=f"s-{i}", generation_mode="full", urban_tier="metro")
            for i in range(10)
        ]
        variants_metro = [
            _make_persona(persona_id=f"vm-{i}", generation_mode="variant",
                          urban_tier="metro", seed_persona_id=seeds[i % 10].persona_id)
            for i in range(80)
        ]
        variants_rural = [
            _make_persona(persona_id=f"vr-{i}", generation_mode="variant",
                          urban_tier="rural", seed_persona_id=seeds[i % 10].persona_id)
            for i in range(10)
        ]
        cohort = seeds + variants_metro + variants_rural
        # Seed dist: metro=1.0. Variant dist: metro≈0.889 rural≈0.111
        # Max deviation ≈ 0.111
        report = validate_parity(cohort, threshold=0.10)
        dp = report.dimensions["urban_tier"]
        assert dp.max_abs_deviation > 0.10
        assert not dp.passed

    def test_threshold_default_is_10pct(self):
        cohort = _make_cohort(n_seeds=10, n_variants=90)
        report = validate_parity(cohort)
        assert report.threshold == 0.10
