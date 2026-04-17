"""variant_generator — expand a seed PersonaRecord into N demographic variants.

Given a deep/full-pipeline seed persona, produces N lightweight variants by:

  1. Demographic variation     — age ±5, city rotation, life-stage update
  2. Attribute perturbation     — Gaussian noise on continuous attrs (σ=0.08)
  3. DerivedInsights recompute  — deterministic, from perturbed attributes
  4. TendencyEstimator recompute— deterministic, from perturbed attributes + insights
  5. Narrative regeneration     — 1 Haiku call per variant (name + narratives)
  6. CoreMemory assembly        — identity_statement + key_values rebuilt;
                                   cultural stances inherited from seed
  7. PersonaRecord construction — seed_persona_id set; generation_mode="variant"

LLM cost: exactly 1 Haiku call per variant (~$0.004 each at current pricing).
Total for 9,800 variants: ~$39 vs ~$2,450 for full-pipeline at Sonnet prices.

Usage::

    import asyncio
    from popscale.generation.variant_generator import VariantGenerator
    from popscale.calibration.calibrator import PersonaSegment

    generator = VariantGenerator(llm_client=client)
    variants = asyncio.run(generator.expand(
        seed=seed_persona,
        n=49,
        segment=segment,
        domain="policy",
        persona_id_prefix="wb-v",
        random_seed=42,
    ))
"""

from __future__ import annotations

import asyncio
import copy
import logging
import random
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── PG path setup ─────────────────────────────────────────────────────────────
_PG_ROOT = Path(__file__).parents[4] / "Persona Generator"
if str(_PG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PG_ROOT))

from src.generation.derived_insights import DerivedInsightsComputer      # noqa: E402
from src.generation.tendency_estimator import TendencyEstimator          # noqa: E402
from src.schema.persona import (                                          # noqa: E402
    Attribute,
    BehaviouralTendencies,
    CoreMemory,
    DemographicAnchor,
    DerivedInsights,
    Household,
    LifeDefiningEvent,
    LifeStory,
    Location,
    Memory,
    Narrative,
    PersonaRecord,
    RelationshipMap,
    ImmutableConstraints,
    SimulationState,
    WorkingMemory,
)

from ..calibration.calibrator import PersonaSegment                       # noqa: E402
from ..utils.persona_adapter import adapt_persona_dict                    # noqa: E402

# ── Model constants ───────────────────────────────────────────────────────────
_HAIKU_MODEL = "claude-haiku-4-5-20251001"
_GENERATOR_VERSION = "variant-1.0"

# Noise sigma for continuous attribute perturbation
_ATTR_NOISE_SIGMA = 0.08

# Probability of re-sampling a categorical attribute
_CATEGORICAL_RESAMPLE_RATE = 0.05

# Identity-defining attributes to preserve (no perturbation)
_PRESERVE_ATTRS: frozenset[str] = frozenset({
    "tension_seed",
    "trust_orientation_primary",
    "religion",
    "political_lean",
    "caste",
    "language_primary",
})

# Life-stage thresholds
_LIFE_STAGE_MAP: list[tuple[int, int, str]] = [
    (18, 25, "early career / student"),
    (26, 35, "young adult / establishing"),
    (36, 45, "mid-career / settled"),
    (46, 55, "mid-life / peak earning"),
    (56, 100, "late career / pre-retirement"),
]

# City pools per urban tier (India defaults; extended externally via register)
_CITY_POOL: dict[str, list[str]] = {
    "metro":  ["Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai", "Kolkata", "Pune", "Ahmedabad"],
    "tier2":  ["Jaipur", "Lucknow", "Kanpur", "Nagpur", "Indore", "Bhopal", "Coimbatore", "Surat", "Patna", "Vadodara"],
    "tier3":  ["Agra", "Varanasi", "Meerut", "Rajkot", "Jodhpur", "Raipur", "Kota", "Guwahati", "Amritsar", "Jabalpur"],
    "rural":  ["Village in rural district", "Small town", "Rural block headquarters"],
}


# ── Name fragment pools for Indian names (by gender) ─────────────────────────

_FIRST_NAMES_MALE = [
    "Rahul", "Amit", "Vijay", "Pradeep", "Ravi", "Suresh", "Mahesh", "Anil",
    "Rakesh", "Sanjay", "Deepak", "Rajesh", "Ashok", "Naveen", "Mohan",
    "Dinesh", "Pankaj", "Vikas", "Santosh", "Ramesh", "Ajay", "Arvind",
    "Sunil", "Nitin", "Vivek", "Manish", "Rohit", "Gaurav", "Ankit", "Akash",
]
_FIRST_NAMES_FEMALE = [
    "Priya", "Sunita", "Anita", "Kavita", "Meena", "Rekha", "Pooja", "Neha",
    "Asha", "Geeta", "Shweta", "Divya", "Seema", "Usha", "Vandana",
    "Anjali", "Nisha", "Preeti", "Rani", "Savita", "Mamta", "Archana",
    "Reena", "Sonal", "Kiran", "Sapna", "Swati", "Pallavi", "Ritu", "Smita",
]
_LAST_NAMES = [
    "Kumar", "Singh", "Sharma", "Verma", "Gupta", "Patel", "Joshi", "Mishra",
    "Yadav", "Tiwari", "Pandey", "Chauhan", "Rao", "Nair", "Iyer",
    "Reddy", "Patil", "Desai", "Shah", "Mehta", "Jain", "Srivastava",
    "Chaudhary", "Thakur", "Dubey", "Tripathi", "Agarwal", "Bansal", "Saxena",
]


# ── VariantGenerator ──────────────────────────────────────────────────────────

class VariantGenerator:
    """Expands a single seed PersonaRecord into N demographic variants.

    Each variant:
    - Shares the seed's core psychological profile (tension_seed, trust_anchor,
      decision_style, political_lean, etc.)
    - Differs in: age, name, city, household composition, and attribute noise
    - Has a freshly generated narrative (Haiku) reflecting the new demographics
    - Has seed_persona_id set to the seed's persona_id

    Attributes:
        llm_client:  Anthropic client for narrative generation.
        model:       Model ID for variant narrative generation. Default: Haiku.
    """

    def __init__(
        self,
        llm_client: Any,
        *,
        model: str = _HAIKU_MODEL,
    ) -> None:
        self.llm_client = llm_client
        self.model = model
        self._insights_computer = DerivedInsightsComputer()
        self._tendency_estimator = TendencyEstimator()

    # ── Public API ────────────────────────────────────────────────────────────

    async def expand(
        self,
        seed: PersonaRecord,
        n: int,
        segment: PersonaSegment,
        domain: str,
        *,
        persona_id_prefix: str = "var",
        random_seed: Optional[int] = None,
        max_concurrent: int = 20,
    ) -> list[PersonaRecord]:
        """Expand seed into n variant PersonaRecords.

        Args:
            seed:              The seed persona to expand from.
            n:                 Number of variants to produce.
            segment:           The demographic segment anchoring this batch.
            domain:            Domain string (e.g. "policy", "consumer").
            persona_id_prefix: Prefix for variant persona IDs.
            random_seed:       Seed the RNG for reproducible output.
            max_concurrent:    Max concurrent Haiku calls (default 20).

        Returns:
            List of n PersonaRecord variants.
        """
        rng = random.Random(random_seed)
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _build(idx: int) -> PersonaRecord:
            async with semaphore:
                return await self._build_one_variant(
                    seed=seed,
                    segment=segment,
                    domain=domain,
                    persona_id=f"{persona_id_prefix}-{idx}",
                    rng=rng,
                )

        return list(await asyncio.gather(*[_build(i) for i in range(n)]))

    # ── Per-variant pipeline ──────────────────────────────────────────────────

    async def _build_one_variant(
        self,
        seed: PersonaRecord,
        segment: PersonaSegment,
        domain: str,
        persona_id: str,
        rng: random.Random,
    ) -> PersonaRecord:
        """Build a single variant PersonaRecord from a seed."""

        # Step 1 — Demographic variation
        new_anchor = self._vary_demographics(seed.demographic_anchor, segment, rng)

        # Step 2 — Attribute perturbation
        new_attrs = self._perturb_attributes(seed.attributes, rng)

        # Step 3 — DerivedInsights recomputation
        new_insights = self._insights_computer.compute(new_attrs, new_anchor)

        # Step 4 — TendencyEstimator recomputation
        new_tendencies = self._tendency_estimator.estimate(new_attrs, new_insights)

        # Step 5 — Life stories (inherit from seed, adjust "when" ages)
        new_life_stories = self._adjust_life_stories(seed.life_stories, new_anchor.age, rng)

        # Step 6 — Narrative regeneration (1 Haiku call — returns name + narratives)
        name, narrative = await self._regenerate_narrative(
            anchor=new_anchor,
            insights=new_insights,
            life_stories=new_life_stories,
            tendencies=new_tendencies,
            rng=rng,
        )
        new_anchor = _replace_name(new_anchor, name)

        # Step 7 — CoreMemory assembly
        new_core_memory = self._assemble_core_memory(
            seed=seed,
            anchor=new_anchor,
            insights=new_insights,
            tendencies=new_tendencies,
            attributes=new_attrs,
        )

        # Step 8 — WorkingMemory (fresh, same as a newly generated persona)
        new_working_memory = WorkingMemory(
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

        # Step 9 — Decision bullets (inherit from seed — reflect the seed's profile)
        decision_bullets = list(seed.decision_bullets)

        return PersonaRecord(
            persona_id=persona_id,
            generated_at=datetime.now(timezone.utc),
            generator_version=_GENERATOR_VERSION,
            domain=domain,
            mode=seed.mode,
            demographic_anchor=new_anchor,
            life_stories=new_life_stories,
            attributes=new_attrs,
            derived_insights=new_insights,
            behavioural_tendencies=new_tendencies,
            narrative=narrative,
            decision_bullets=decision_bullets,
            memory=Memory(core=new_core_memory, working=new_working_memory),
            seed_persona_id=seed.persona_id,
            generation_mode="variant",
        )

    # ── Step 1: Demographic variation ─────────────────────────────────────────

    def _vary_demographics(
        self,
        anchor: DemographicAnchor,
        segment: PersonaSegment,
        rng: random.Random,
    ) -> DemographicAnchor:
        """Vary age and city; keep gender, education, employment, household structure."""
        # Age: ±5 years, clamped to [18, 80]
        age_delta = rng.randint(-5, 5)
        new_age = max(18, min(80, anchor.age + age_delta))

        # Life stage from new age
        new_life_stage = _age_to_life_stage(new_age)

        # City: rotate to a different city of the same urban tier
        new_city = _rotate_city(anchor.location.city, anchor.location.urban_tier, rng)

        new_location = Location(
            country=anchor.location.country,
            region=anchor.location.region,
            city=new_city,
            urban_tier=anchor.location.urban_tier,
        )

        # Household size: ±1, clamped to [1, 8]
        size_delta = rng.choice([-1, 0, 0, 1])  # bias toward no change
        new_size = max(1, min(8, anchor.household.size + size_delta))

        new_household = Household(
            structure=anchor.household.structure,
            size=new_size,
            income_bracket=anchor.household.income_bracket,
            dual_income=anchor.household.dual_income,
        )

        # Name: will be set after narrative call; placeholder for now
        return DemographicAnchor(
            name=anchor.name,       # temporary — overwritten in step 6
            age=new_age,
            gender=anchor.gender,
            location=new_location,
            household=new_household,
            life_stage=new_life_stage,
            education=anchor.education,
            employment=anchor.employment,
            worldview=anchor.worldview,
        )

    # ── Step 2: Attribute perturbation ────────────────────────────────────────

    def _perturb_attributes(
        self,
        attributes: dict[str, dict[str, Attribute]],
        rng: random.Random,
    ) -> dict[str, dict[str, Attribute]]:
        """Add controlled Gaussian noise to continuous attributes.

        Preserves identity-defining categorical attributes unchanged.
        Identity-defining continuous attributes get half the noise.
        """
        result: dict[str, dict[str, Attribute]] = {}
        for category, cat_attrs in attributes.items():
            result[category] = {}
            for name, attr in cat_attrs.items():
                result[category][name] = self._perturb_one(name, attr, rng)
        return result

    @staticmethod
    def _perturb_one(name: str, attr: Attribute, rng: random.Random) -> Attribute:
        if name in _PRESERVE_ATTRS:
            return attr  # identity-defining — no perturbation

        if attr.type == "continuous":
            noise = rng.gauss(0.0, _ATTR_NOISE_SIGMA)
            new_val = float(attr.value) + noise
            new_val = max(0.0, min(1.0, new_val))
            return Attribute(
                value=round(new_val, 6),
                type="continuous",
                label=attr.label,
                source=attr.source,
            )
        else:
            # Categorical: very rarely resample (identity-preserving)
            if rng.random() < _CATEGORICAL_RESAMPLE_RATE and name not in _PRESERVE_ATTRS:
                # Just return a copy — we don't have a valid value set per attr,
                # so we keep the value but mark source as "estimated"
                return Attribute(
                    value=attr.value,
                    type="categorical",
                    label=attr.label,
                    source="inferred",
                )
            return attr

    # ── Step 3 & 4: Insights + Tendencies recomputed by callers ──────────────
    # DerivedInsightsComputer.compute() and TendencyEstimator.estimate() are
    # called directly in _build_one_variant — they are stateless.

    # ── Step 5: Life story adjustment ────────────────────────────────────────

    @staticmethod
    def _adjust_life_stories(
        stories: list[LifeStory],
        new_age: int,
        rng: random.Random,
    ) -> list[LifeStory]:
        """Keep life stories from seed. Keep exactly 2 (drop 3rd if present).

        The story content is preserved — the variant shares the same
        psychological type as the seed. The narrative call will provide
        the age-appropriate first-person voice.
        """
        # Keep 2 stories (required minimum)
        selected = stories[:2]
        return list(selected)

    # ── Step 6: Narrative regeneration ───────────────────────────────────────

    async def _regenerate_narrative(
        self,
        anchor: DemographicAnchor,
        insights: DerivedInsights,
        life_stories: list[LifeStory],
        tendencies: BehaviouralTendencies,
        rng: random.Random,
    ) -> tuple[str, Narrative]:
        """Generate name + narrative for a variant via a single Haiku call.

        Returns (name, Narrative) where name is a culturally appropriate
        first name + last name for the anchor's demographics.
        """
        # Pick a plausible name pool based on gender
        if anchor.gender == "male":
            first_pool = _FIRST_NAMES_MALE
        elif anchor.gender == "female":
            first_pool = _FIRST_NAMES_FEMALE
        else:
            first_pool = _FIRST_NAMES_MALE + _FIRST_NAMES_FEMALE

        first_name = rng.choice(first_pool)
        last_name = rng.choice(_LAST_NAMES)
        candidate_name = f"{first_name} {last_name}"

        # Build compact profile for Haiku
        demo_line = (
            f"{anchor.age}-year-old {anchor.gender}, {anchor.location.city} "
            f"({anchor.location.urban_tier}), {anchor.life_stage}, "
            f"{anchor.education} education, {anchor.employment}"
        )
        tension = insights.key_tensions[0] if insights.key_tensions else "internal tension"
        ls_ref = ""
        if life_stories:
            ls = life_stories[0]
            ls_ref = f'Life anchor: "{ls.title} — {ls.lasting_impact}"'

        system = (
            "You are writing persona narrative fragments. Be specific and concrete. "
            "No generic statements. Match the exact demographics and psychology given."
        )

        user = (
            f"Demographics: {demo_line}\n"
            f"Decision style: {insights.decision_style}, value: {insights.primary_value_orientation}\n"
            f"Key tension: {tension}\n"
            f"Trust anchor: {insights.trust_anchor}\n"
            f"{ls_ref}\n"
            f"Tendency: {tendencies.reasoning_prompt[:120]}\n\n"
            f"Name for this persona: {candidate_name}\n\n"
            "Write three outputs separated by '---':\n"
            "1. Name (use the name provided above, or a culturally similar one if needed)\n"
            "2. First-person narrative (80-120 words). Specific to their profile.\n"
            "3. Third-person narrative (120-160 words). Analytical — explain why they behave as they do.\n\n"
            "Format:\nNAME: {name}\n---\n{first_person}\n---\n{third_person}"
        )

        try:
            if hasattr(self.llm_client, 'complete'):
                raw = await self.llm_client.complete(
                    system=system,
                    messages=[{"role": "user", "content": user}],
                    max_tokens=512,
                    model=self.model,
                )
            else:
                response = await self.llm_client.messages.create(
                    model=self.model,
                    max_tokens=512,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                raw = response.content[0].text.strip()

            name, first_person, third_person = _parse_narrative_response(
                raw, candidate_name, demo_line
            )
        except Exception as e:
            logger.warning("Narrative generation failed for variant: %s", e)
            # Fallback: use seed narrative with demographic adjustments
            name = candidate_name
            first_person = (
                f"I'm {anchor.name}, {anchor.age}, based in {anchor.location.city}. "
                f"I navigate life driven by {insights.primary_value_orientation} "
                f"and often find myself caught between {tension}."
            )
            third_person = (
                f"{anchor.name} is a {anchor.age}-year-old from {anchor.location.city}. "
                f"Their decision style is {insights.decision_style}, anchored in trust of "
                f"their {insights.trust_anchor}. The tension between {tension} shapes how "
                f"they approach choices — particularly around {insights.primary_value_orientation}."
            )

        display_name = name.split()[0] if " " in name else name
        return name, Narrative(
            first_person=first_person,
            third_person=third_person,
            display_name=display_name,
        )

    # ── Step 7: CoreMemory assembly ───────────────────────────────────────────

    def _assemble_core_memory(
        self,
        seed: PersonaRecord,
        anchor: DemographicAnchor,
        insights: DerivedInsights,
        tendencies: BehaviouralTendencies,
        attributes: dict[str, dict[str, Attribute]],
    ) -> CoreMemory:
        """Build CoreMemory for a variant.

        Inherits cultural stances from seed (population-level, not individual).
        Rebuilds identity_statement and key_values from perturbed attributes.
        """
        seed_core = seed.memory.core

        # Identity statement: update to reflect new demographics
        identity_statement = (
            f"A {anchor.age}-year-old {anchor.gender} from {anchor.location.city}, "
            f"{anchor.life_stage}, with a {insights.decision_style} decision style "
            f"anchored in {insights.primary_value_orientation} values."
        )

        # Key values: derive from insights + tendency (3 values)
        key_values = _derive_key_values(insights, tendencies)

        # Life-defining events: inherit from seed (same psychological type)
        life_defining_events = list(seed_core.life_defining_events)

        # Relationship map: inherit from seed
        relationship_map = seed_core.relationship_map

        # Immutable constraints: rebuild from attributes
        immutable_constraints = _build_immutable_constraints(attributes)

        # Tendency summary: from new behavioural tendencies
        tendency_summary = tendencies.reasoning_prompt[:200]

        return CoreMemory(
            identity_statement=identity_statement,
            key_values=key_values,
            life_defining_events=life_defining_events,
            relationship_map=relationship_map,
            immutable_constraints=immutable_constraints,
            tendency_summary=tendency_summary,
            # Cultural stances: inherit from seed (population-level anchors)
            current_conditions_stance=seed_core.current_conditions_stance,
            media_trust_stance=seed_core.media_trust_stance,
            gender_norms_stance=seed_core.gender_norms_stance,
            governance_stance=seed_core.governance_stance,
            cultural_context=seed_core.cultural_context,
            inc_stance=seed_core.inc_stance,
        )


# ── Helper functions ──────────────────────────────────────────────────────────

def _age_to_life_stage(age: int) -> str:
    for min_age, max_age, stage in _LIFE_STAGE_MAP:
        if min_age <= age <= max_age:
            return stage
    return "adult"


def _rotate_city(current_city: str, urban_tier: str, rng: random.Random) -> str:
    pool = _CITY_POOL.get(urban_tier, [current_city])
    alternatives = [c for c in pool if c != current_city]
    if not alternatives:
        return current_city
    return rng.choice(alternatives)


def _replace_name(anchor: DemographicAnchor, new_name: str) -> DemographicAnchor:
    """Return a copy of DemographicAnchor with the name replaced."""
    return DemographicAnchor(
        name=new_name,
        age=anchor.age,
        gender=anchor.gender,
        location=anchor.location,
        household=anchor.household,
        life_stage=anchor.life_stage,
        education=anchor.education,
        employment=anchor.employment,
        worldview=anchor.worldview,
    )


def _derive_key_values(
    insights: DerivedInsights,
    tendencies: BehaviouralTendencies,
) -> list[str]:
    """Derive 3–4 key values from insights and tendencies."""
    values: list[str] = []

    # Value orientation
    _VALUE_LABELS: dict[str, str] = {
        "price": "value for money and budget discipline",
        "quality": "quality and reliability in every decision",
        "brand": "trusted brands as a signal of reliability",
        "convenience": "convenience and time efficiency",
        "features": "functionality and feature depth",
    }
    values.append(_VALUE_LABELS.get(insights.primary_value_orientation, "careful decision-making"))

    # Trust anchor
    _TRUST_LABELS: dict[str, str] = {
        "self": "self-reliance and independent judgment",
        "peer": "trusted advice from family and friends",
        "authority": "guidance from credible experts and authorities",
        "family": "family consensus and collective wisdom",
    }
    values.append(_TRUST_LABELS.get(insights.trust_anchor, "grounded relationships"))

    # Coping / core tension
    coping_type = insights.coping_mechanism.type if insights.coping_mechanism else None
    _COPING_LABELS: dict[str, str] = {
        "routine_control": "predictability and structured routines",
        "social_validation": "community belonging and social acceptance",
        "research_deep_dive": "thorough research before committing",
        "denial": "optimism in the face of uncertainty",
        "optimism_bias": "hope and forward momentum",
    }
    if coping_type:
        values.append(_COPING_LABELS.get(coping_type, "stability and consistency"))
    else:
        values.append("stability and consistency")

    # Switching propensity label
    if tendencies.switching_propensity.band == "low":
        values.append("loyalty to proven choices")
    elif tendencies.switching_propensity.band == "high":
        values.append("openness to new options")

    # Ensure 3–5 items
    while len(values) < 3:
        values.append("resilience and consistency")
    return values[:5]


def _build_immutable_constraints(
    attributes: dict[str, dict[str, Attribute]],
) -> ImmutableConstraints:
    """Build ImmutableConstraints from attribute profile."""
    non_negotiables: list[str] = []
    absolute_avoidances: list[str] = []
    budget_ceiling: str | None = None

    # Flat attribute lookup
    flat: dict[str, Attribute] = {}
    for cat_attrs in attributes.values():
        flat.update(cat_attrs)

    budget_c = flat.get("budget_consciousness")
    if budget_c and budget_c.type == "continuous" and float(budget_c.value) > 0.75:
        non_negotiables.append("Stays within budget — never overspends on discretionary items")
        budget_ceiling = "strict"

    brand_l = flat.get("brand_loyalty")
    if brand_l and brand_l.type == "continuous" and float(brand_l.value) > 0.8:
        non_negotiables.append("Trusts established brands over unknowns")

    risk_t = flat.get("risk_tolerance")
    if risk_t and risk_t.type == "continuous" and float(risk_t.value) < 0.25:
        absolute_avoidances.append("Major financial risk or untested choices")

    if not non_negotiables:
        non_negotiables.append("Maintains personal values in all decisions")
    if not absolute_avoidances:
        absolute_avoidances.append("Choices that violate core beliefs")

    return ImmutableConstraints(
        budget_ceiling=budget_ceiling,
        non_negotiables=non_negotiables,
        absolute_avoidances=absolute_avoidances,
    )


def _parse_narrative_response(
    raw: str,
    fallback_name: str,
    demo_line: str,
) -> tuple[str, str, str]:
    """Parse the structured NAME / first_person / third_person response.

    Returns (name, first_person, third_person). Falls back gracefully.
    """
    parts = raw.split("---")
    if len(parts) < 3:
        # Try newline splitting as fallback
        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        name = fallback_name
        first_person = " ".join(lines[:3]) if lines else f"I am {fallback_name}."
        third_person = " ".join(lines[3:6]) if len(lines) > 3 else f"{fallback_name} navigates life carefully."
        return name, first_person, third_person

    name_part = parts[0].strip()
    first_part = parts[1].strip()
    third_part = parts[2].strip()

    # Extract name from "NAME: ..." prefix
    if name_part.upper().startswith("NAME:"):
        name = name_part[5:].strip()
    else:
        name = fallback_name

    if not name:
        name = fallback_name

    return name, first_part or f"I am {name}.", third_part or f"{name} navigates life carefully."
