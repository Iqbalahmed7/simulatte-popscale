"""environment — simulation environment presets for PopScale.

SimulationEnvironment bundles:
  - scenario_environment dict  →  injected into Scenario.environment
  - calibration_state          →  passed to calibrator.get_profile()
  - default_population_kwargs  →  defaults for PopulationSpec construction

Named presets encode real-world conditions for common study contexts:
  - West Bengal political research (2026)
  - India national policy research
  - India urban consumer research
  - India rural economy research

Usage::

    from popscale.environment import WEST_BENGAL_POLITICAL_2026, apply_environment

    scenario = Scenario(
        question="Will you vote for the incumbent party?",
        context="State elections are scheduled for next month.",
        domain=SimulationDomain.POLITICAL,
    )
    scenario = apply_environment(scenario, WEST_BENGAL_POLITICAL_2026)
    # scenario.environment now reflects Bengal political conditions

    # Also build a matching PopulationSpec:
    from popscale.environment import build_population_spec
    spec = build_population_spec(
        env=WEST_BENGAL_POLITICAL_2026,
        n_personas=500,
        domain="policy",
        business_problem="How will Bengal voters respond to fuel price rises?",
        stratify_by_religion=True,
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .scenario.model import Scenario
from .calibration.population_spec import PopulationSpec


# ── SimulationEnvironment ─────────────────────────────────────────────────────

@dataclass
class SimulationEnvironment:
    """A named, reusable environment preset for PopScale simulations.

    Attributes:
        name:                  Short identifier (e.g. "west_bengal_political_2026").
        description:           Human-readable description of what this preset encodes.
        region:                Geographic/cultural region label (for display).
        calibration_state:     State code for get_profile() (e.g. "west_bengal").
        scenario_environment:  Dict for Scenario.environment — passed directly into
                               Scenario's domain renderer (region, economic_sentiment, etc.).
        default_spec_kwargs:   Default keyword args merged into PopulationSpec when
                               build_population_spec() is called with this env.
        event_tags:            Tags that match relevant events in an EventTimeline
                               (used for filtering stimuli by environment).
    """
    name: str
    description: str
    region: str
    calibration_state: str
    scenario_environment: dict[str, Any] = field(default_factory=dict)
    default_spec_kwargs: dict[str, Any]  = field(default_factory=dict)
    event_tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name":               self.name,
            "description":        self.description,
            "region":             self.region,
            "calibration_state":  self.calibration_state,
            "scenario_environment": self.scenario_environment,
            "default_spec_kwargs":  self.default_spec_kwargs,
            "event_tags":           self.event_tags,
        }


# ── Public helpers ─────────────────────────────────────────────────────────────

def apply_environment(scenario: Scenario, env: SimulationEnvironment) -> Scenario:
    """Return a new Scenario with environment preset applied.

    The preset's scenario_environment dict is merged into the existing
    scenario.environment — preset values do NOT overwrite caller-set values.
    The caller's explicit environment settings always win.

    Args:
        scenario: The original Scenario.
        env:      The SimulationEnvironment preset to apply.

    Returns:
        A new Scenario with merged environment dict.
    """
    merged = {**env.scenario_environment, **scenario.environment}
    return scenario.model_copy(update={"environment": merged})


def build_population_spec(
    env: SimulationEnvironment,
    n_personas: int,
    domain: str,
    business_problem: str,
    **overrides: Any,
) -> PopulationSpec:
    """Build a demographically calibrated PopulationSpec from an environment preset.

    The preset's default_spec_kwargs provide sensible defaults for the state,
    age range, urban/rural split, and stratification. All can be overridden.

    Args:
        env:              SimulationEnvironment preset.
        n_personas:       Total persona count.
        domain:           PG domain key (e.g. "policy", "consumer").
        business_problem: Research question for this cohort.
        **overrides:      Override any default_spec_kwargs or PopulationSpec field.

    Returns:
        PopulationSpec ready for calibrate().
    """
    kwargs = {
        "state":    env.calibration_state,
        **env.default_spec_kwargs,
        **overrides,
    }
    return PopulationSpec(
        n_personas=n_personas,
        domain=domain,
        business_problem=business_problem,
        **kwargs,
    )


# ── Named presets ─────────────────────────────────────────────────────────────

WEST_BENGAL_POLITICAL_2026 = SimulationEnvironment(
    name="west_bengal_political_2026",
    description=(
        "West Bengal state election environment (2026). Competitive three-way contest "
        "between TMC, BJP, and Left-Congress alliance. High Muslim minority sensitivity, "
        "fuel price protests, rural economic stress, strong media polarisation."
    ),
    region="West Bengal, India",
    calibration_state="west_bengal",
    scenario_environment={
        "region":               "West Bengal, India",
        "cultural_context":     "Bengali, post-Left, multicultural with significant Muslim minority",
        "economic_sentiment":   "stressed — fuel and food prices elevated",
        "regulatory_climate":   "state election campaign — heightened political sensitivity",
        "public_trust_level":   "polarised — high partisan identity, low cross-party trust",
        "media_landscape":      "fragmented — Bengali TV, WhatsApp chains, opposition newspapers",
    },
    default_spec_kwargs={
        "age_min":              18,
        "age_max":              70,
        "stratify_by_religion": True,
        "stratify_by_income":   False,
        "sarvam_enabled":       True,
    },
    event_tags=["bengal", "wb", "political", "election"],
)

INDIA_NATIONAL_POLICY = SimulationEnvironment(
    name="india_national_policy",
    description=(
        "India national policy environment. Mixed urban/rural population, high income "
        "inequality, central government communication context. Suitable for central "
        "ministry research, national scheme launches, tax/subsidy policy."
    ),
    region="India (National)",
    calibration_state="india",
    scenario_environment={
        "region":               "India (National)",
        "cultural_context":     "diverse — Hindi belt dominant but regional variation high",
        "economic_sentiment":   "cautiously optimistic — urban growth, rural lag",
        "regulatory_climate":   "active — multiple reform programmes underway",
        "public_trust_level":   "moderate — central govt trust above state average",
        "media_landscape":      "national news channels, regional press, social media",
    },
    default_spec_kwargs={
        "age_min":              18,
        "age_max":              65,
        "stratify_by_religion": False,
        "stratify_by_income":   True,
        "sarvam_enabled":       True,
    },
    event_tags=["india", "national", "policy"],
)

INDIA_URBAN_CONSUMER = SimulationEnvironment(
    name="india_urban_consumer",
    description=(
        "India urban consumer environment. Tier-1 and Tier-2 city residents, "
        "aspirational middle class, digital-first. Suitable for D2C, SaaS, "
        "FMCG premium launches, fintech, edtech research."
    ),
    region="Urban India",
    calibration_state="india",
    scenario_environment={
        "region":               "Urban India",
        "cultural_context":     "aspirational urban — English-comfortable, digital native",
        "economic_sentiment":   "optimistic — jobs market recovering, consumption up",
        "market_conditions":    "competitive — category growth attracting new entrants",
        "competitive_intensity": "high",
        "media_landscape":      "Instagram, YouTube, OTT, influencer-driven",
    },
    default_spec_kwargs={
        "age_min":              20,
        "age_max":              50,
        "urban_only":           True,
        "stratify_by_religion": False,
        "stratify_by_income":   True,
        "sarvam_enabled":       True,
    },
    event_tags=["india", "urban", "consumer"],
)

INDIA_RURAL_ECONOMY = SimulationEnvironment(
    name="india_rural_economy",
    description=(
        "India rural economy environment. Agricultural household majority, "
        "MGNREGA-dependent workers, crop-price sensitive, low digital penetration. "
        "Suitable for agri-input companies, rural FMCG, govt welfare scheme research."
    ),
    region="Rural India",
    calibration_state="india",
    scenario_environment={
        "region":               "Rural India",
        "cultural_context":     "agrarian — caste and kinship networks dominant, traditional",
        "economic_sentiment":   "stressed — monsoon dependency, input cost squeeze",
        "market_conditions":    "constrained — price-sensitive, low brand loyalty",
        "competitive_intensity": "low",
        "media_landscape":      "local radio, vernacular print, feature phones dominant",
    },
    default_spec_kwargs={
        "age_min":              18,
        "age_max":              60,
        "rural_only":           True,
        "stratify_by_religion": False,
        "stratify_by_income":   False,
        "sarvam_enabled":       True,
    },
    event_tags=["india", "rural", "agrarian"],
)

MAHARASHTRA_CONSUMER = SimulationEnvironment(
    name="maharashtra_consumer",
    description=(
        "Maharashtra consumer market environment. Mumbai metro + Pune tech hub + "
        "semi-urban Maharashtra. Diverse income, strong Marathi identity, "
        "active consumer market. Suitable for premium and mass consumer products."
    ),
    region="Maharashtra, India",
    calibration_state="maharashtra",
    scenario_environment={
        "region":               "Maharashtra, India",
        "cultural_context":     "Marathi — urban-sophisticated in Mumbai, traditional outside",
        "economic_sentiment":   "positive — industrial and services economy healthy",
        "market_conditions":    "competitive — well-penetrated market",
        "competitive_intensity": "high",
        "media_landscape":      "Marathi press, Hindi nationals, digital-first young adults",
    },
    default_spec_kwargs={
        "age_min":              20,
        "age_max":              55,
        "stratify_by_religion": False,
        "stratify_by_income":   True,
        "sarvam_enabled":       True,
    },
    event_tags=["maharashtra", "consumer", "mumbai"],
)


# ── USA presets ───────────────────────────────────────────────────────────────

US_CONSUMER_2026 = SimulationEnvironment(
    name="us_consumer_2026",
    description=(
        "United States consumer market environment (2026). Broad national sample, "
        "inflation-sensitive middle class, high digital penetration, brand-aware. "
        "Suitable for CPG, SaaS, fintech, media, and D2C product research."
    ),
    region="United States",
    calibration_state="united_states",
    scenario_environment={
        "region":               "United States",
        "cultural_context":     "American — individualistic, brand-aware, digital-first",
        "economic_sentiment":   "cautious — inflation fatigue, rates elevated, job market resilient",
        "market_conditions":    "competitive — high consumer choice, brand switching common",
        "competitive_intensity": "high",
        "media_landscape":      "social media dominant — YouTube, TikTok, Instagram, podcasts",
    },
    default_spec_kwargs={
        "age_min":              18,
        "age_max":              65,
        "stratify_by_religion": False,
        "stratify_by_income":   True,
    },
    event_tags=["us", "usa", "consumer", "national"],
)

US_POLITICAL_2026 = SimulationEnvironment(
    name="us_political_2026",
    description=(
        "United States political environment (2026 midterm cycle). Highly polarised "
        "electorate, strong partisan identity, economic anxiety. Suitable for policy "
        "polling, political messaging research, and public opinion studies."
    ),
    region="United States",
    calibration_state="united_states",
    scenario_environment={
        "region":               "United States",
        "cultural_context":     "American — deeply polarised partisan landscape, identity-driven voting",
        "economic_sentiment":   "anxious — inflation, housing costs, debt ceiling concerns",
        "regulatory_climate":   "midterm cycle — heightened political sensitivity",
        "public_trust_level":   "low — institutional trust at historic lows",
        "media_landscape":      "fragmented — partisan cable news, podcasts, X/Twitter, local TV",
    },
    default_spec_kwargs={
        "age_min":              18,
        "age_max":              80,
        "stratify_by_religion": False,
        "stratify_by_income":   True,
    },
    event_tags=["us", "usa", "political", "election", "midterm"],
)

US_URBAN_CONSUMER = SimulationEnvironment(
    name="us_urban_consumer",
    description=(
        "United States urban consumer environment. Major metro residents (NYC, LA, "
        "Chicago, Houston, Phoenix, etc.), higher education and income, digitally "
        "sophisticated. Suitable for premium brands, tech products, fintech, wellness."
    ),
    region="Urban United States",
    calibration_state="united_states",
    scenario_environment={
        "region":               "Urban United States",
        "cultural_context":     "metro American — diverse, educated, brand-discriminating",
        "economic_sentiment":   "optimistic but cost-conscious — high income, high cost of living",
        "market_conditions":    "saturated — high competition, strong brand loyalty in categories",
        "competitive_intensity": "very high",
        "media_landscape":      "streaming, social media, podcasts, influencer-driven",
    },
    default_spec_kwargs={
        "age_min":              22,
        "age_max":              55,
        "urban_only":           True,
        "stratify_by_religion": False,
        "stratify_by_income":   True,
    },
    event_tags=["us", "usa", "urban", "consumer"],
)


# ── UK presets ────────────────────────────────────────────────────────────────

UK_CONSUMER_2026 = SimulationEnvironment(
    name="uk_consumer_2026",
    description=(
        "United Kingdom consumer market environment (2026). Post-Brexit, cost-of-living "
        "pressured households, NHS-dominant healthcare, digital-capable. Suitable for "
        "CPG, retail, fintech, SaaS, and media research targeting UK audiences."
    ),
    region="United Kingdom",
    calibration_state="united_kingdom",
    scenario_environment={
        "region":               "United Kingdom",
        "cultural_context":     "British — pragmatic, value-conscious, BBC/NHS shaped",
        "economic_sentiment":   "stressed — cost of living crisis, energy prices, mortgage pressures",
        "market_conditions":    "price-sensitive — consumers trading down, private label growing",
        "competitive_intensity": "high",
        "media_landscape":      "BBC, ITV, Sky, national press, social media (TikTok, Instagram)",
    },
    default_spec_kwargs={
        "age_min":              18,
        "age_max":              70,
        "stratify_by_religion": False,
        "stratify_by_income":   True,
    },
    event_tags=["uk", "britain", "consumer"],
)

UK_POLITICAL_2026 = SimulationEnvironment(
    name="uk_political_2026",
    description=(
        "United Kingdom political environment (2026). Labour-led government, "
        "post-Brexit adjustment, NHS and cost-of-living as dominant issues. "
        "Suitable for policy polling, public service research, and political messaging."
    ),
    region="United Kingdom",
    calibration_state="united_kingdom",
    scenario_environment={
        "region":               "United Kingdom",
        "cultural_context":     "British — class-aware, regional identity (England/Scotland/Wales/NI)",
        "economic_sentiment":   "pressured — inflation receding but household budgets squeezed",
        "regulatory_climate":   "reforming — new Labour government, public service investment agenda",
        "public_trust_level":   "moderate — recovering from Tory trust deficit",
        "media_landscape":      "BBC, Sky News, national broadsheets, growing podcast audience",
    },
    default_spec_kwargs={
        "age_min":              18,
        "age_max":              80,
        "stratify_by_religion": False,
        "stratify_by_income":   True,
    },
    event_tags=["uk", "britain", "political", "policy"],
)


# ── Europe presets ────────────────────────────────────────────────────────────

EUROPE_CONSUMER_2026 = SimulationEnvironment(
    name="europe_consumer_2026",
    description=(
        "Pan-European consumer environment (2026). EU aggregate for cross-market "
        "consumer research. Use country-specific presets (france_consumer_2026, etc.) "
        "for single-market studies. Suitable for pan-EU brand launches and policy impact."
    ),
    region="Europe",
    calibration_state="united_kingdom",   # default profile; override per-run
    scenario_environment={
        "region":               "Europe",
        "cultural_context":     "European — diverse by country; sustainability-aware, quality-driven",
        "economic_sentiment":   "cautious — energy transition costs, ageing demographics",
        "market_conditions":    "competitive — strong local brands, EU regulatory baseline",
        "competitive_intensity": "high",
        "media_landscape":      "national TV, social media, pan-EU streaming platforms",
    },
    default_spec_kwargs={
        "age_min":              18,
        "age_max":              65,
        "stratify_by_religion": False,
        "stratify_by_income":   True,
    },
    event_tags=["europe", "eu", "consumer"],
)

FRANCE_CONSUMER_2026 = SimulationEnvironment(
    name="france_consumer_2026",
    description=(
        "France consumer market environment (2026). Secular republic, strong state, "
        "quality-conscious consumers, pension reform controversy backdrop. Suitable "
        "for FMCG, luxury, retail, and public opinion research in France."
    ),
    region="France",
    calibration_state="france",
    scenario_environment={
        "region":               "France",
        "cultural_context":     "French — secular, quality-focused, strong state identity, café culture",
        "economic_sentiment":   "cautious — inflation subdued, growth sluggish, social unrest episodic",
        "market_conditions":    "consolidated — large retail chains, local champion brands strong",
        "competitive_intensity": "moderate",
        "media_landscape":      "TF1, M6, Le Monde, BFM TV, growing YouTube/TikTok",
    },
    default_spec_kwargs={
        "age_min":              18,
        "age_max":              70,
        "stratify_by_religion": False,
        "stratify_by_income":   True,
    },
    event_tags=["france", "fr", "consumer", "europe"],
)

UK_AND_EU_POLICY = SimulationEnvironment(
    name="uk_and_eu_policy",
    description=(
        "UK and EU combined policy environment. Cross-market government/NGO research "
        "covering democratic nations with welfare states, ageing populations, and "
        "energy transition pressures. Suitable for think-tank and policy institute work."
    ),
    region="Western Europe",
    calibration_state="united_kingdom",
    scenario_environment={
        "region":               "Western Europe",
        "cultural_context":     "Northern European — rights-aware, institutionally trusting, pluralistic",
        "economic_sentiment":   "cautious — energy costs, fiscal consolidation, slow growth",
        "regulatory_climate":   "active — climate, AI, digital market regulation accelerating",
        "public_trust_level":   "moderate — declining in some markets, stable in Nordics",
        "media_landscape":      "national broadcasters, quality press, social media",
    },
    default_spec_kwargs={
        "age_min":              18,
        "age_max":              75,
        "stratify_by_religion": False,
        "stratify_by_income":   True,
    },
    event_tags=["europe", "uk", "eu", "policy"],
)


# ── Registry ───────────────────────────────────────────────────────────────────

_PRESET_REGISTRY: dict[str, SimulationEnvironment] = {
    env.name: env
    for env in [
        # India
        WEST_BENGAL_POLITICAL_2026,
        INDIA_NATIONAL_POLICY,
        INDIA_URBAN_CONSUMER,
        INDIA_RURAL_ECONOMY,
        MAHARASHTRA_CONSUMER,
        # USA
        US_CONSUMER_2026,
        US_POLITICAL_2026,
        US_URBAN_CONSUMER,
        # UK
        UK_CONSUMER_2026,
        UK_POLITICAL_2026,
        # Europe
        EUROPE_CONSUMER_2026,
        FRANCE_CONSUMER_2026,
        UK_AND_EU_POLICY,
    ]
}


def get_preset(name: str) -> SimulationEnvironment:
    """Retrieve a named SimulationEnvironment preset.

    Args:
        name: The preset name (e.g. "west_bengal_political_2026").

    Returns:
        SimulationEnvironment preset.

    Raises:
        KeyError: If the preset is not registered.
    """
    if name not in _PRESET_REGISTRY:
        raise KeyError(
            f"No environment preset named '{name}'. "
            f"Available: {', '.join(sorted(_PRESET_REGISTRY))}."
        )
    return _PRESET_REGISTRY[name]


def list_presets() -> list[str]:
    """Return all registered preset names."""
    return sorted(_PRESET_REGISTRY)
