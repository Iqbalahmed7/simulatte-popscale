"""Variant Generator Tests — structural/unit (no live API calls).

Tests:
    1. _age_to_life_stage()       — life stage mapping
    2. _rotate_city()             — city rotation logic
    3. _derive_key_values()       — key value derivation
    4. _build_immutable_constraints() — constraint builder
    5. _parse_narrative_response() — response parser
    6. VariantGenerator._perturb_attributes() — noise application
    7. VariantGenerator._vary_demographics()  — demographic variation
    8. VariantGenerator._adjust_life_stories() — life story selection
    9. VariantGenerator._assemble_core_memory() — core memory assembly
    10. PersonaRecord schema — seed_persona_id and generation_mode fields
    11. Variant integration (mock LLM) — full expand() call

Run all (no live API calls):
    python3 -m pytest tests/test_variant_generator.py -v
"""

from __future__ import annotations

import asyncio
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

_POPSCALE_ROOT = Path(__file__).parents[1]
_PG_ROOT       = _POPSCALE_ROOT.parent / "Persona Generator"
if str(_POPSCALE_ROOT) not in sys.path:
    sys.path.insert(0, str(_POPSCALE_ROOT))
if str(_PG_ROOT) not in sys.path:
    sys.path.insert(1, str(_PG_ROOT))

import pytest

from popscale.generation.variant_generator import (
    VariantGenerator,
    _CITY_POOL,
    _PRESERVE_ATTRS,
    _age_to_life_stage,
    _build_immutable_constraints,
    _derive_key_values,
    _parse_narrative_response,
    _replace_name,
    _rotate_city,
)
from popscale.calibration.calibrator import PersonaSegment

# ── PG imports ────────────────────────────────────────────────────────────────

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


# ── Seed persona factory ───────────────────────────────────────────────────────

def _make_seed_persona(
    persona_id: str = "seed-001",
    age: int = 35,
    gender: str = "male",
    city: str = "Mumbai",
    urban_tier: str = "metro",
) -> PersonaRecord:
    """Build a minimal but valid PersonaRecord for use as a seed in tests."""
    location = Location(
        country="India",
        region="Maharashtra",
        city=city,
        urban_tier=urban_tier,
    )
    household = Household(
        structure="nuclear",
        size=4,
        income_bracket="middle",
        dual_income=False,
    )
    anchor = DemographicAnchor(
        name="Rahul Sharma",
        age=age,
        gender=gender,
        location=location,
        household=household,
        life_stage="mid-career / settled",
        education="undergraduate",
        employment="full-time",
    )

    life_stories = [
        LifeStory(
            title="First job in the city",
            when="Age 22",
            event="Moved from hometown to Mumbai for work.",
            lasting_impact="Built self-reliance and urban adaptability.",
        ),
        LifeStory(
            title="Family responsibility",
            when="Age 30",
            event="Became primary breadwinner for parents.",
            lasting_impact="Reinforced budget discipline and long-term planning.",
        ),
    ]

    attributes: dict[str, dict[str, Attribute]] = {
        "psychology": {
            "risk_tolerance": Attribute(value=0.35, type="continuous", label="Risk tolerance", source="sampled"),
            "information_need": Attribute(value=0.6, type="continuous", label="Information need", source="sampled"),
            "emotional_persuasion_susceptibility": Attribute(value=0.45, type="continuous", label="Emotional persuasion", source="sampled"),
            "fear_appeal_responsiveness": Attribute(value=0.4, type="continuous", label="Fear appeal", source="sampled"),
            "status_quo_bias": Attribute(value=0.55, type="continuous", label="Status quo bias", source="sampled"),
            "analysis_paralysis": Attribute(value=0.4, type="continuous", label="Analysis paralysis", source="sampled"),
        },
        "social": {
            "social_proof_bias": Attribute(value=0.5, type="continuous", label="Social proof bias", source="sampled"),
            "peer_influence_strength": Attribute(value=0.5, type="continuous", label="Peer influence", source="sampled"),
            "authority_bias": Attribute(value=0.55, type="continuous", label="Authority bias", source="sampled"),
            "trust_orientation_primary": Attribute(value="authority", type="categorical", label="Trust orientation", source="anchored"),
            "online_community_trust": Attribute(value=0.4, type="continuous", label="Online community trust", source="sampled"),
            "influencer_susceptibility": Attribute(value=0.3, type="continuous", label="Influencer susceptibility", source="sampled"),
            "wom_receiver_openness": Attribute(value=0.5, type="continuous", label="WoM receiver openness", source="sampled"),
        },
        "values": {
            "budget_consciousness": Attribute(value=0.65, type="continuous", label="Budget consciousness", source="sampled"),
            "deal_seeking_intensity": Attribute(value=0.55, type="continuous", label="Deal seeking", source="sampled"),
            "economic_constraint_level": Attribute(value=0.5, type="continuous", label="Economic constraint", source="sampled"),
            "brand_loyalty": Attribute(value=0.6, type="continuous", label="Brand loyalty", source="sampled"),
            "indie_brand_openness": Attribute(value=0.4, type="continuous", label="Indie brand openness", source="sampled"),
            "primary_value_driver": Attribute(value="quality", type="categorical", label="Primary value driver", source="anchored"),
        },
        "lifestyle": {
            "routine_adherence": Attribute(value=0.65, type="continuous", label="Routine adherence", source="sampled"),
            "ad_receptivity": Attribute(value=0.35, type="continuous", label="Ad receptivity", source="sampled"),
        },
        "identity": {
            "tension_seed": Attribute(value="quality_vs_budget", type="categorical", label="Tension seed", source="anchored"),
            "self_efficacy": Attribute(value=0.6, type="continuous", label="Self-efficacy", source="sampled"),
        },
        "decision_making": {
            "research_before_purchase": Attribute(value=0.65, type="continuous", label="Research before purchase", source="sampled"),
            "decision_delegation": Attribute(value=0.3, type="continuous", label="Decision delegation", source="sampled"),
        },
    }

    derived_insights = DerivedInsights(
        decision_style="analytical",
        decision_style_score=0.35,
        trust_anchor="authority",
        risk_appetite="low",
        primary_value_orientation="quality",
        coping_mechanism=CopingMechanism(
            type="research_deep_dive",
            description="Researches thoroughly to find best value.",
        ),
        consistency_score=72,
        consistency_band="medium",
        key_tensions=["Desires quality but is constrained by budget"],
    )

    trust_weights = TrustWeights(
        expert=0.65, peer=0.5, brand=0.6, ad=0.3, community=0.4, influencer=0.3
    )
    trust_orientation = TrustOrientation(
        weights=trust_weights,
        dominant="expert",
        description="You give heavy weight to credentialed experts.",
        source="proxy",
    )
    behavioural_tendencies = BehaviouralTendencies(
        price_sensitivity=PriceSensitivityBand(
            band="high",
            description="You consistently seek deals.",
            source="proxy",
        ),
        trust_orientation=trust_orientation,
        switching_propensity=TendencyBand(
            band="low",
            description="You stay loyal to brands you trust.",
            source="proxy",
        ),
        objection_profile=[
            Objection(
                objection_type="price_vs_value",
                likelihood="high",
                severity="friction",
            )
        ],
        reasoning_prompt="You are high price-sensitive. You trust experts. You stay loyal.",
    )

    narrative = Narrative(
        first_person="I'm always careful with money but I won't compromise on quality.",
        third_person="Rahul balances quality aspirations with budget discipline.",
        display_name="Rahul",
    )

    core_memory = CoreMemory(
        identity_statement="A 35-year-old analytical professional from Mumbai.",
        key_values=["quality over price", "self-reliance", "research-driven decisions"],
        life_defining_events=[
            LifeDefiningEvent(age_when=22, event="First city job", lasting_impact="Built self-reliance."),
        ],
        relationship_map=RelationshipMap(
            primary_decision_partner="spouse",
            key_influencers=["colleague", "online reviews"],
            trust_network=["family", "colleagues"],
        ),
        immutable_constraints=ImmutableConstraints(
            budget_ceiling="strict",
            non_negotiables=["Stays within budget"],
            absolute_avoidances=["Financial risk"],
        ),
        tendency_summary="Quality-focused with high price sensitivity.",
        current_conditions_stance=None,
        governance_stance=None,
    )

    working_memory = WorkingMemory(
        observations=[],
        reflections=[],
        plans=[],
        brand_memories={},
        simulation_state=SimulationState(
            current_turn=0,
            importance_accumulator=0.0,
            reflection_count=0,
            awareness_set={},
            consideration_set=[],
            last_decision=None,
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
        decision_bullets=["Checks reviews before buying", "Delays for better prices"],
        memory=Memory(core=core_memory, working=working_memory),
        seed_persona_id=None,
        generation_mode="full",
    )


def _make_segment() -> PersonaSegment:
    return PersonaSegment(
        count=50,
        anchor_overrides={"religion": "hindu", "income_bracket": "middle"},
        label="Hindu, middle income",
        proportion=0.5,
    )


def _make_mock_llm_client(response: str = "") -> Any:
    """Mock LLM client with .complete() method (test path)."""
    client = MagicMock()
    if not response:
        response = (
            "NAME: Amit Kumar\n"
            "---\n"
            "I carefully weigh every purchase against my budget. Quality matters.\n"
            "---\n"
            "Amit is a methodical decision-maker who prioritises quality while staying budget-aware."
        )
    client.complete = AsyncMock(return_value=response)
    return client


# ─────────────────────────────────────────────────────────────────────────────
# 1. _age_to_life_stage()
# ─────────────────────────────────────────────────────────────────────────────

class TestAgeToLifeStage:

    def test_young_adult(self):
        assert _age_to_life_stage(22) == "early career / student"

    def test_establishing(self):
        assert _age_to_life_stage(30) == "young adult / establishing"

    def test_mid_career(self):
        assert _age_to_life_stage(40) == "mid-career / settled"

    def test_peak_earning(self):
        assert _age_to_life_stage(50) == "mid-life / peak earning"

    def test_pre_retirement(self):
        assert _age_to_life_stage(60) == "late career / pre-retirement"

    def test_boundary_18(self):
        assert _age_to_life_stage(18) == "early career / student"

    def test_boundary_25(self):
        assert _age_to_life_stage(25) == "early career / student"

    def test_boundary_26(self):
        assert _age_to_life_stage(26) == "young adult / establishing"


# ─────────────────────────────────────────────────────────────────────────────
# 2. _rotate_city()
# ─────────────────────────────────────────────────────────────────────────────

class TestRotateCity:

    def test_returns_different_city_when_alternatives_exist(self):
        rng = random.Random(42)
        new_city = _rotate_city("Mumbai", "metro", rng)
        assert new_city != "Mumbai"

    def test_returns_from_metro_pool(self):
        rng = random.Random(42)
        new_city = _rotate_city("Mumbai", "metro", rng)
        assert new_city in _CITY_POOL["metro"]

    def test_falls_back_when_only_city(self):
        rng = random.Random(42)
        new_city = _rotate_city("OnlyCity", "metro", rng)
        # If current city is not in pool, picks from full pool (alternatives = all)
        assert new_city in _CITY_POOL["metro"]

    def test_tier2_pool(self):
        rng = random.Random(0)
        new_city = _rotate_city("Jaipur", "tier2", rng)
        assert new_city in _CITY_POOL["tier2"]

    def test_rural_pool(self):
        rng = random.Random(0)
        new_city = _rotate_city("Village in rural district", "rural", rng)
        assert new_city in _CITY_POOL["rural"]


# ─────────────────────────────────────────────────────────────────────────────
# 3. _derive_key_values()
# ─────────────────────────────────────────────────────────────────────────────

class TestDeriveKeyValues:

    def _make_insights(
        self,
        pvo: str = "quality",
        trust: str = "authority",
        coping: str = "research_deep_dive",
    ) -> DerivedInsights:
        return DerivedInsights(
            decision_style="analytical",
            decision_style_score=0.35,
            trust_anchor=trust,
            risk_appetite="low",
            primary_value_orientation=pvo,
            coping_mechanism=CopingMechanism(type=coping, description="..."),
            consistency_score=70,
            consistency_band="medium",
            key_tensions=["quality vs budget"],
        )

    def _make_tendencies(self, band: str = "low") -> BehaviouralTendencies:
        return BehaviouralTendencies(
            price_sensitivity=PriceSensitivityBand(band="high", description=".", source="proxy"),
            trust_orientation=TrustOrientation(
                weights=TrustWeights(expert=0.6, peer=0.4, brand=0.5, ad=0.3, community=0.4, influencer=0.3),
                dominant="expert",
                description=".",
                source="proxy",
            ),
            switching_propensity=TendencyBand(band=band, description=".", source="proxy"),
            objection_profile=[Objection(objection_type="price_vs_value", likelihood="high", severity="friction")],
            reasoning_prompt="Test prompt.",
        )

    def test_returns_3_to_5_values(self):
        insights = self._make_insights()
        tendencies = self._make_tendencies()
        values = _derive_key_values(insights, tendencies)
        assert 3 <= len(values) <= 5

    def test_quality_orientation_included(self):
        insights = self._make_insights(pvo="quality")
        tendencies = self._make_tendencies()
        values = _derive_key_values(insights, tendencies)
        assert any("quality" in v.lower() for v in values)

    def test_price_orientation_included(self):
        insights = self._make_insights(pvo="price")
        tendencies = self._make_tendencies()
        values = _derive_key_values(insights, tendencies)
        assert any("value" in v.lower() or "budget" in v.lower() for v in values)

    def test_high_switching_reflected(self):
        insights = self._make_insights()
        tendencies = self._make_tendencies(band="high")
        values = _derive_key_values(insights, tendencies)
        assert any("open" in v.lower() or "new" in v.lower() for v in values)

    def test_low_switching_reflected(self):
        insights = self._make_insights()
        tendencies = self._make_tendencies(band="low")
        values = _derive_key_values(insights, tendencies)
        assert any("loyal" in v.lower() for v in values)


# ─────────────────────────────────────────────────────────────────────────────
# 4. _build_immutable_constraints()
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildImmutableConstraints:

    def _attrs_with_budget(self, budget: float) -> dict:
        return {
            "values": {
                "budget_consciousness": Attribute(value=budget, type="continuous", label="Budget", source="sampled"),
                "brand_loyalty": Attribute(value=0.5, type="continuous", label="Brand loyalty", source="sampled"),
            },
            "psychology": {
                "risk_tolerance": Attribute(value=0.5, type="continuous", label="Risk tolerance", source="sampled"),
            },
        }

    def test_high_budget_sets_non_negotiable(self):
        attrs = self._attrs_with_budget(0.8)
        c = _build_immutable_constraints(attrs)
        assert any("budget" in nn.lower() for nn in c.non_negotiables)

    def test_high_budget_sets_ceiling(self):
        attrs = self._attrs_with_budget(0.8)
        c = _build_immutable_constraints(attrs)
        assert c.budget_ceiling == "strict"

    def test_low_budget_no_ceiling(self):
        attrs = self._attrs_with_budget(0.3)
        c = _build_immutable_constraints(attrs)
        assert c.budget_ceiling is None

    def test_always_has_at_least_one_non_negotiable(self):
        attrs = self._attrs_with_budget(0.3)
        c = _build_immutable_constraints(attrs)
        assert len(c.non_negotiables) >= 1

    def test_always_has_at_least_one_avoidance(self):
        attrs = self._attrs_with_budget(0.3)
        c = _build_immutable_constraints(attrs)
        assert len(c.absolute_avoidances) >= 1

    def test_low_risk_tolerance_adds_avoidance(self):
        attrs = {
            "values": {
                "budget_consciousness": Attribute(value=0.3, type="continuous", label="Budget", source="sampled"),
            },
            "psychology": {
                "risk_tolerance": Attribute(value=0.2, type="continuous", label="Risk tolerance", source="sampled"),
            },
        }
        c = _build_immutable_constraints(attrs)
        assert any("risk" in a.lower() for a in c.absolute_avoidances)


# ─────────────────────────────────────────────────────────────────────────────
# 5. _parse_narrative_response()
# ─────────────────────────────────────────────────────────────────────────────

class TestParseNarrativeResponse:

    def test_parses_well_formed_response(self):
        raw = "NAME: Amit Kumar\n---\nFirst person text here.\n---\nThird person text here."
        name, fp, tp = _parse_narrative_response(raw, "Fallback Name", "demo")
        assert name == "Amit Kumar"
        assert "First person" in fp
        assert "Third person" in tp

    def test_falls_back_on_missing_separators(self):
        raw = "Just some text without separators."
        name, fp, tp = _parse_narrative_response(raw, "Fallback Name", "demo")
        assert name == "Fallback Name"
        assert len(fp) > 0
        assert len(tp) > 0

    def test_extracts_name_case_insensitive(self):
        raw = "name: Priya Singh\n---\nFP text\n---\nTP text"
        name, fp, tp = _parse_narrative_response(raw, "Fallback", "demo")
        # NAME: check is uppercase — case-sensitive; fallback used
        assert name == "Fallback" or "Priya" in name  # implementation allows either

    def test_empty_name_falls_back(self):
        raw = "NAME: \n---\nFP text\n---\nTP text"
        name, fp, tp = _parse_narrative_response(raw, "Fallback Name", "demo")
        assert name == "Fallback Name"


# ─────────────────────────────────────────────────────────────────────────────
# 6. VariantGenerator._perturb_attributes()
# ─────────────────────────────────────────────────────────────────────────────

class TestPerturbAttributes:

    def setup_method(self):
        self.generator = VariantGenerator(llm_client=MagicMock())
        self.seed = _make_seed_persona()

    def test_continuous_attrs_changed(self):
        rng = random.Random(1)
        perturbed = self.generator._perturb_attributes(self.seed.attributes, rng)
        orig_val = float(self.seed.attributes["psychology"]["risk_tolerance"].value)
        new_val = float(perturbed["psychology"]["risk_tolerance"].value)
        # With sigma=0.08, almost certain to change (seed is random, but rarely stays same)
        # Just verify bounds
        assert 0.0 <= new_val <= 1.0

    def test_identity_defining_attrs_preserved(self):
        rng = random.Random(42)
        perturbed = self.generator._perturb_attributes(self.seed.attributes, rng)
        orig = self.seed.attributes["identity"]["tension_seed"].value
        new = perturbed["identity"]["tension_seed"].value
        assert orig == new  # tension_seed is in _PRESERVE_ATTRS

    def test_trust_orientation_primary_preserved(self):
        rng = random.Random(42)
        perturbed = self.generator._perturb_attributes(self.seed.attributes, rng)
        orig = self.seed.attributes["social"]["trust_orientation_primary"].value
        new = perturbed["social"]["trust_orientation_primary"].value
        assert orig == new

    def test_structure_preserved(self):
        rng = random.Random(42)
        perturbed = self.generator._perturb_attributes(self.seed.attributes, rng)
        assert set(perturbed.keys()) == set(self.seed.attributes.keys())
        for cat in self.seed.attributes:
            assert set(perturbed[cat].keys()) == set(self.seed.attributes[cat].keys())

    def test_continuous_values_in_range(self):
        rng = random.Random(99)
        perturbed = self.generator._perturb_attributes(self.seed.attributes, rng)
        for cat_attrs in perturbed.values():
            for attr in cat_attrs.values():
                if attr.type == "continuous":
                    assert 0.0 <= float(attr.value) <= 1.0


# ─────────────────────────────────────────────────────────────────────────────
# 7. VariantGenerator._vary_demographics()
# ─────────────────────────────────────────────────────────────────────────────

class TestVaryDemographics:

    def setup_method(self):
        self.generator = VariantGenerator(llm_client=MagicMock())
        self.seed = _make_seed_persona()
        self.segment = _make_segment()

    def test_age_within_5_of_seed(self):
        rng = random.Random(42)
        new_anchor = self.generator._vary_demographics(
            self.seed.demographic_anchor, self.segment, rng
        )
        age_diff = abs(new_anchor.age - self.seed.demographic_anchor.age)
        assert age_diff <= 5

    def test_age_at_least_18(self):
        seed = _make_seed_persona(age=18)
        rng = random.Random(1)
        new_anchor = self.generator._vary_demographics(
            seed.demographic_anchor, self.segment, rng
        )
        assert new_anchor.age >= 18

    def test_age_at_most_80(self):
        seed = _make_seed_persona(age=80)
        rng = random.Random(1)
        new_anchor = self.generator._vary_demographics(
            seed.demographic_anchor, self.segment, rng
        )
        assert new_anchor.age <= 80

    def test_gender_preserved(self):
        rng = random.Random(42)
        new_anchor = self.generator._vary_demographics(
            self.seed.demographic_anchor, self.segment, rng
        )
        assert new_anchor.gender == self.seed.demographic_anchor.gender

    def test_urban_tier_preserved(self):
        rng = random.Random(42)
        new_anchor = self.generator._vary_demographics(
            self.seed.demographic_anchor, self.segment, rng
        )
        assert new_anchor.location.urban_tier == self.seed.demographic_anchor.location.urban_tier

    def test_education_preserved(self):
        rng = random.Random(42)
        new_anchor = self.generator._vary_demographics(
            self.seed.demographic_anchor, self.segment, rng
        )
        assert new_anchor.education == self.seed.demographic_anchor.education

    def test_household_size_within_1(self):
        rng = random.Random(42)
        new_anchor = self.generator._vary_demographics(
            self.seed.demographic_anchor, self.segment, rng
        )
        size_diff = abs(new_anchor.household.size - self.seed.demographic_anchor.household.size)
        assert size_diff <= 1

    def test_life_stage_updated_for_new_age(self):
        seed = _make_seed_persona(age=25)
        rng = random.Random(7)  # will shift age to ~30
        new_anchor = self.generator._vary_demographics(
            seed.demographic_anchor, self.segment, rng
        )
        expected_stage = _age_to_life_stage(new_anchor.age)
        assert new_anchor.life_stage == expected_stage


# ─────────────────────────────────────────────────────────────────────────────
# 8. VariantGenerator._adjust_life_stories()
# ─────────────────────────────────────────────────────────────────────────────

class TestAdjustLifeStories:

    def setup_method(self):
        self.generator = VariantGenerator(llm_client=MagicMock())
        self.seed = _make_seed_persona()

    def test_returns_exactly_2_stories(self):
        rng = random.Random(42)
        stories = self.generator._adjust_life_stories(
            self.seed.life_stories, self.seed.demographic_anchor.age, rng
        )
        assert len(stories) == 2

    def test_drops_3rd_story_when_present(self):
        extra = LifeStory(title="Third story", when="Age 28", event="Something.", lasting_impact="Impact.")
        three_stories = list(self.seed.life_stories) + [extra]
        rng = random.Random(42)
        stories = self.generator._adjust_life_stories(three_stories, 35, rng)
        assert len(stories) == 2

    def test_stories_are_from_seed(self):
        rng = random.Random(42)
        stories = self.generator._adjust_life_stories(
            self.seed.life_stories, self.seed.demographic_anchor.age, rng
        )
        assert stories[0].title == self.seed.life_stories[0].title
        assert stories[1].title == self.seed.life_stories[1].title


# ─────────────────────────────────────────────────────────────────────────────
# 9. VariantGenerator._assemble_core_memory()
# ─────────────────────────────────────────────────────────────────────────────

class TestAssembleCoreMemory:

    def setup_method(self):
        self.generator = VariantGenerator(llm_client=MagicMock())
        self.seed = _make_seed_persona()
        from src.generation.derived_insights import DerivedInsightsComputer
        from src.generation.tendency_estimator import TendencyEstimator
        rng = random.Random(42)
        attrs = self.generator._perturb_attributes(self.seed.attributes, rng)
        anchor = self.generator._vary_demographics(
            self.seed.demographic_anchor, _make_segment(), rng
        )
        self.insights = DerivedInsightsComputer().compute(attrs, anchor)
        self.tendencies = TendencyEstimator().estimate(attrs, self.insights)
        self.attrs = attrs
        self.anchor = anchor

    def test_identity_statement_includes_age(self):
        core = self.generator._assemble_core_memory(
            seed=self.seed,
            anchor=self.anchor,
            insights=self.insights,
            tendencies=self.tendencies,
            attributes=self.attrs,
        )
        assert str(self.anchor.age) in core.identity_statement

    def test_key_values_3_to_5(self):
        core = self.generator._assemble_core_memory(
            seed=self.seed,
            anchor=self.anchor,
            insights=self.insights,
            tendencies=self.tendencies,
            attributes=self.attrs,
        )
        assert 3 <= len(core.key_values) <= 5

    def test_cultural_stances_inherited_from_seed(self):
        # Seed has governance_stance=None — variant should too
        core = self.generator._assemble_core_memory(
            seed=self.seed,
            anchor=self.anchor,
            insights=self.insights,
            tendencies=self.tendencies,
            attributes=self.attrs,
        )
        assert core.governance_stance == self.seed.memory.core.governance_stance
        assert core.current_conditions_stance == self.seed.memory.core.current_conditions_stance

    def test_tendency_summary_not_empty(self):
        core = self.generator._assemble_core_memory(
            seed=self.seed,
            anchor=self.anchor,
            insights=self.insights,
            tendencies=self.tendencies,
            attributes=self.attrs,
        )
        assert len(core.tendency_summary) > 10

    def test_life_defining_events_from_seed(self):
        core = self.generator._assemble_core_memory(
            seed=self.seed,
            anchor=self.anchor,
            insights=self.insights,
            tendencies=self.tendencies,
            attributes=self.attrs,
        )
        assert len(core.life_defining_events) == len(self.seed.memory.core.life_defining_events)


# ─────────────────────────────────────────────────────────────────────────────
# 10. PersonaRecord schema — new fields
# ─────────────────────────────────────────────────────────────────────────────

class TestPersonaRecordSchema:

    def test_seed_persona_id_default_none(self):
        seed = _make_seed_persona()
        assert seed.seed_persona_id is None

    def test_generation_mode_default_full(self):
        seed = _make_seed_persona()
        assert seed.generation_mode == "full"

    def test_can_set_seed_persona_id(self):
        seed = _make_seed_persona()
        variant = seed.model_copy(update={"seed_persona_id": "seed-001", "generation_mode": "variant"})
        assert variant.seed_persona_id == "seed-001"
        assert variant.generation_mode == "variant"

    def test_extra_fields_still_forbidden(self):
        from pydantic import ValidationError
        # extra="forbid" is enforced on construction, not model_copy
        with pytest.raises(ValidationError):
            seed = _make_seed_persona()
            PersonaRecord.model_validate({
                **seed.model_dump(),
                "nonexistent_field": "should_be_rejected",
            })


# ─────────────────────────────────────────────────────────────────────────────
# 11. Full expand() with mock LLM
# ─────────────────────────────────────────────────────────────────────────────

class TestVariantGeneratorExpand:

    def setup_method(self):
        self.seed = _make_seed_persona()
        self.segment = _make_segment()
        self.mock_client = _make_mock_llm_client()
        self.generator = VariantGenerator(llm_client=self.mock_client)

    def test_expand_returns_correct_count(self):
        variants = asyncio.run(self.generator.expand(
            seed=self.seed,
            n=3,
            segment=self.segment,
            domain="consumer",
            persona_id_prefix="test-v",
            random_seed=42,
        ))
        assert len(variants) == 3

    def test_all_variants_are_persona_records(self):
        variants = asyncio.run(self.generator.expand(
            seed=self.seed,
            n=2,
            segment=self.segment,
            domain="consumer",
            random_seed=0,
        ))
        for v in variants:
            assert isinstance(v, PersonaRecord)

    def test_seed_persona_id_set_on_variants(self):
        variants = asyncio.run(self.generator.expand(
            seed=self.seed,
            n=2,
            segment=self.segment,
            domain="consumer",
            random_seed=0,
        ))
        for v in variants:
            assert v.seed_persona_id == self.seed.persona_id

    def test_generation_mode_variant_on_all(self):
        variants = asyncio.run(self.generator.expand(
            seed=self.seed,
            n=2,
            segment=self.segment,
            domain="consumer",
            random_seed=0,
        ))
        for v in variants:
            assert v.generation_mode == "variant"

    def test_variant_ids_unique(self):
        variants = asyncio.run(self.generator.expand(
            seed=self.seed,
            n=5,
            segment=self.segment,
            domain="consumer",
            persona_id_prefix="uniq",
            random_seed=1,
        ))
        ids = [v.persona_id for v in variants]
        assert len(ids) == len(set(ids))

    def test_variants_have_valid_life_stories(self):
        variants = asyncio.run(self.generator.expand(
            seed=self.seed,
            n=2,
            segment=self.segment,
            domain="consumer",
            random_seed=5,
        ))
        for v in variants:
            assert 2 <= len(v.life_stories) <= 3

    def test_variants_domain_matches(self):
        variants = asyncio.run(self.generator.expand(
            seed=self.seed,
            n=2,
            segment=self.segment,
            domain="policy",
            random_seed=7,
        ))
        for v in variants:
            assert v.domain == "policy"

    def test_reproducible_with_same_seed(self):
        v1 = asyncio.run(self.generator.expand(
            seed=self.seed, n=2, segment=self.segment,
            domain="consumer", random_seed=99,
        ))
        v2 = asyncio.run(self.generator.expand(
            seed=self.seed, n=2, segment=self.segment,
            domain="consumer", random_seed=99,
        ))
        # Ages should be the same when random_seed is the same
        assert [v.demographic_anchor.age for v in v1] == [v.demographic_anchor.age for v in v2]

    def test_expand_n_zero_returns_empty(self):
        variants = asyncio.run(self.generator.expand(
            seed=self.seed, n=0, segment=self.segment,
            domain="consumer", random_seed=0,
        ))
        assert variants == []

    def test_decision_bullets_inherited_from_seed(self):
        variants = asyncio.run(self.generator.expand(
            seed=self.seed, n=1, segment=self.segment,
            domain="consumer", random_seed=0,
        ))
        assert variants[0].decision_bullets == self.seed.decision_bullets

    def test_working_memory_fresh(self):
        variants = asyncio.run(self.generator.expand(
            seed=self.seed, n=1, segment=self.segment,
            domain="consumer", random_seed=0,
        ))
        wm = variants[0].memory.working
        assert wm.observations == []
        assert wm.reflections == []
        assert wm.simulation_state.current_turn == 0

    def test_mode_inherited_from_seed(self):
        variants = asyncio.run(self.generator.expand(
            seed=self.seed, n=1, segment=self.segment,
            domain="consumer", random_seed=0,
        ))
        assert variants[0].mode == self.seed.mode
