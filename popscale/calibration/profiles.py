"""profiles — demographic calibration profiles for India, USA, and Europe.

Provides census-grounded demographic snapshots used by the PopScale calibrator
to weight anchor_overrides when generating persona cohorts that reflect actual
population distributions.

Data sources (India):
  - Census of India 2011 (most recent full census available)
  - NFHS-5 (2019-21) for health/literacy updates
  - World Bank India estimates 2022 for income bands

Data sources (USA):
  - US Census Bureau 2020 decennial census + 2022 ACS estimates
  - Pew Research Center 2023 for religious composition
  - World Bank / BLS 2022 for income bands

Data sources (UK / Europe):
  - Office for National Statistics (ONS) Census 2021
  - Eurostat 2022 for EU country demographics
  - Pew Research Center 2023 for religious composition

pg_location routing:
  - India states → pg_location="India"   → PG _INDIA_GENERAL_POOL
  - USA profiles → pg_location="United States" → PG _US_GENERAL_POOL
  - UK profile   → pg_location="United Kingdom" → PG _UK_GENERAL_POOL
  - EU countries → pg_location=<country name>   → PG _DOMAIN_POOLS routing
    NOTE: EU routing in PG is via domain pool keys (e.g. "france_general"),
    not the standard location-string path. pool_key anchor override may be
    needed for EU geographies in a future PG update.

Usage::

    from popscale.calibration.profiles import get_profile, list_states

    profile = get_profile("west_bengal")
    print(profile.pg_location)   # "India"
    print(profile.urban_pct)     # 0.319

    profile_us = get_profile("united_states")
    print(profile_us.pg_location)  # "United States"
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ── DemographicProfile ────────────────────────────────────────────────────────

@dataclass
class DemographicProfile:
    """Demographic snapshot of a geography for persona calibration.

    All proportions are floats in [0, 1] that sum to 1.0 within their group.

    Attributes:
        state:                  Human-readable geography name.
        state_code:             Short slug (used as lookup key).
        pg_location:            Location string to pass to Persona Generator's
                                anchor_overrides. PG uses this to route to the
                                correct persona pool (e.g. "India", "United States",
                                "United Kingdom").
        population_m:           Approximate population in millions (latest est.).
        urban_pct:              Fraction of population living in urban areas.
        rural_pct:              1 - urban_pct.
        median_age:             Population median age in years.
        literacy_rate:          Adult literacy rate (fraction, age 15+).
        income_bands:           Proportion in low / middle / high income bands.
                                Keys: "low", "middle", "high".
        religious_composition:  Population share by religion. Keys vary by region.
                                India: "hindu", "muslim", "christian", "sikh", etc.
                                USA:   "protestant", "catholic", "unaffiliated", "other"
                                EU:    "christian", "unaffiliated", "muslim", "other"
        primary_language:       Dominant language.
        languages:              Other widely spoken languages.
        region:                 Broad geographic region label.
        supports_religion_stratification: If False, stratify_by_religion is a no-op
                                for this profile (income stratification used instead).
                                Set False for non-India geographies where Hindu/Muslim
                                stratification anchors are not meaningful.
        tags:                   Free-form tags for additional context.
        notes:                  Optional methodology note.
    """
    state: str
    state_code: str
    pg_location: str
    population_m: float
    urban_pct: float
    median_age: float
    literacy_rate: float
    income_bands: dict[str, float]
    religious_composition: dict[str, float]
    primary_language: str
    languages: list[str]
    region: str
    supports_religion_stratification: bool = True
    tags: list[str] = field(default_factory=list)
    notes: str = ""

    @property
    def rural_pct(self) -> float:
        return round(1.0 - self.urban_pct, 4)

    def dominant_religion(self) -> str:
        return max(self.religious_composition, key=self.religious_composition.__getitem__)

    def to_dict(self) -> dict:
        return {
            "state":       self.state,
            "state_code":  self.state_code,
            "pg_location": self.pg_location,
            "population_m": self.population_m,
            "urban_pct":   self.urban_pct,
            "rural_pct":   self.rural_pct,
            "median_age":  self.median_age,
            "literacy_rate": self.literacy_rate,
            "income_bands": self.income_bands,
            "religious_composition": self.religious_composition,
            "primary_language": self.primary_language,
            "languages":   self.languages,
            "region":      self.region,
            "supports_religion_stratification": self.supports_religion_stratification,
            "tags":        self.tags,
        }


# ── India state profiles ──────────────────────────────────────────────────────

_PROFILES: dict[str, DemographicProfile] = {

    # ── West Bengal ───────────────────────────────────────────────────────────
    "west_bengal": DemographicProfile(
        state="West Bengal",
        state_code="west_bengal",
        pg_location="India",
        population_m=98.0,
        urban_pct=0.319,
        median_age=27.0,
        literacy_rate=0.771,
        income_bands={"low": 0.55, "middle": 0.38, "high": 0.07},
        religious_composition={
            "hindu": 0.705, "muslim": 0.270, "christian": 0.006,
            "buddhist": 0.003, "sikh": 0.001, "jain": 0.001, "other": 0.014,
        },
        primary_language="Bengali",
        languages=["Hindi", "Urdu", "Santali", "Nepali"],
        region="east",
        tags=[
            "politically_competitive", "left_legacy", "industrial_decline",
            "high_muslim_minority", "border_state", "riverine",
        ],
        notes="Census 2011 base; urban/religious from census; income bands from NFHS-5 wealth index.",
    ),

    # ── Maharashtra ───────────────────────────────────────────────────────────
    "maharashtra": DemographicProfile(
        state="Maharashtra",
        state_code="maharashtra",
        pg_location="India",
        population_m=124.0,
        urban_pct=0.452,
        median_age=29.0,
        literacy_rate=0.824,
        income_bands={"low": 0.38, "middle": 0.47, "high": 0.15},
        religious_composition={
            "hindu": 0.797, "muslim": 0.115, "buddhist": 0.059,
            "christian": 0.009, "jain": 0.012, "sikh": 0.002, "other": 0.006,
        },
        primary_language="Marathi",
        languages=["Hindi", "Urdu", "Gujarati", "Tamil"],
        region="west",
        tags=["urban_heavy", "industrial", "financial_hub", "diverse_economy"],
        notes="Includes Mumbai Metro Region in urban_pct.",
    ),

    # ── Uttar Pradesh ─────────────────────────────────────────────────────────
    "uttar_pradesh": DemographicProfile(
        state="Uttar Pradesh",
        state_code="uttar_pradesh",
        pg_location="India",
        population_m=237.0,
        urban_pct=0.222,
        median_age=24.0,
        literacy_rate=0.675,
        income_bands={"low": 0.65, "middle": 0.30, "high": 0.05},
        religious_composition={
            "hindu": 0.795, "muslim": 0.194, "sikh": 0.005,
            "christian": 0.001, "buddhist": 0.001, "jain": 0.001, "other": 0.003,
        },
        primary_language="Hindi",
        languages=["Urdu", "Bhojpuri", "Awadhi"],
        region="north",
        tags=["most_populous", "agrarian", "politically_pivotal", "hindi_belt"],
    ),

    # ── Bihar ─────────────────────────────────────────────────────────────────
    "bihar": DemographicProfile(
        state="Bihar",
        state_code="bihar",
        pg_location="India",
        population_m=128.0,
        urban_pct=0.115,
        median_age=22.0,
        literacy_rate=0.617,
        income_bands={"low": 0.73, "middle": 0.24, "high": 0.03},
        religious_composition={
            "hindu": 0.827, "muslim": 0.168, "christian": 0.001,
            "sikh": 0.001, "buddhist": 0.001, "jain": 0.000, "other": 0.002,
        },
        primary_language="Hindi",
        languages=["Maithili", "Bhojpuri", "Magahi", "Urdu"],
        region="east",
        tags=["agrarian", "low_income", "high_migration", "young_population"],
    ),

    # ── Tamil Nadu ────────────────────────────────────────────────────────────
    "tamil_nadu": DemographicProfile(
        state="Tamil Nadu",
        state_code="tamil_nadu",
        pg_location="India",
        population_m=78.0,
        urban_pct=0.482,
        median_age=32.0,
        literacy_rate=0.807,
        income_bands={"low": 0.35, "middle": 0.50, "high": 0.15},
        religious_composition={
            "hindu": 0.877, "muslim": 0.057, "christian": 0.062,
            "jain": 0.001, "sikh": 0.000, "buddhist": 0.000, "other": 0.003,
        },
        primary_language="Tamil",
        languages=["Telugu", "Kannada", "Urdu"],
        region="south",
        tags=["industrialised", "high_literacy", "dravidian_politics", "auto_hub"],
    ),

    # ── Karnataka ─────────────────────────────────────────────────────────────
    "karnataka": DemographicProfile(
        state="Karnataka",
        state_code="karnataka",
        pg_location="India",
        population_m=68.0,
        urban_pct=0.387,
        median_age=29.0,
        literacy_rate=0.757,
        income_bands={"low": 0.40, "middle": 0.44, "high": 0.16},
        religious_composition={
            "hindu": 0.840, "muslim": 0.128, "christian": 0.019,
            "jain": 0.007, "buddhist": 0.001, "sikh": 0.000, "other": 0.005,
        },
        primary_language="Kannada",
        languages=["Telugu", "Tamil", "Urdu", "Hindi", "Tulu"],
        region="south",
        tags=["tech_hub", "bangalore", "startup_ecosystem", "mixed_economy"],
    ),

    # ── Rajasthan ─────────────────────────────────────────────────────────────
    "rajasthan": DemographicProfile(
        state="Rajasthan",
        state_code="rajasthan",
        pg_location="India",
        population_m=83.0,
        urban_pct=0.249,
        median_age=25.0,
        literacy_rate=0.663,
        income_bands={"low": 0.58, "middle": 0.35, "high": 0.07},
        religious_composition={
            "hindu": 0.882, "muslim": 0.095, "sikh": 0.014,
            "jain": 0.006, "christian": 0.001, "buddhist": 0.000, "other": 0.002,
        },
        primary_language="Rajasthani",
        languages=["Hindi", "Urdu", "Punjabi"],
        region="north",
        tags=["desert_state", "agrarian", "tourism", "conservative"],
    ),

    # ── Delhi (NCT) ───────────────────────────────────────────────────────────
    "delhi": DemographicProfile(
        state="Delhi (NCT)",
        state_code="delhi",
        pg_location="India",
        population_m=32.0,
        urban_pct=0.975,
        median_age=28.0,
        literacy_rate=0.862,
        income_bands={"low": 0.28, "middle": 0.50, "high": 0.22},
        religious_composition={
            "hindu": 0.817, "muslim": 0.128, "sikh": 0.040,
            "jain": 0.007, "christian": 0.004, "buddhist": 0.001, "other": 0.003,
        },
        primary_language="Hindi",
        languages=["Punjabi", "Urdu", "Bengali", "Tamil"],
        region="north",
        tags=["urban_only", "capital", "high_income", "migrant_population"],
    ),

    # ── Gujarat ───────────────────────────────────────────────────────────────
    "gujarat": DemographicProfile(
        state="Gujarat",
        state_code="gujarat",
        pg_location="India",
        population_m=63.0,
        urban_pct=0.426,
        median_age=27.0,
        literacy_rate=0.789,
        income_bands={"low": 0.37, "middle": 0.47, "high": 0.16},
        religious_composition={
            "hindu": 0.886, "muslim": 0.097, "jain": 0.010,
            "christian": 0.002, "sikh": 0.001, "buddhist": 0.000, "other": 0.004,
        },
        primary_language="Gujarati",
        languages=["Hindi", "Sindhi", "Marathi", "Urdu"],
        region="west",
        tags=["business_community", "diamond_trade", "petrochem", "bjp_stronghold", "diaspora"],
        notes="Census 2011; strong Jain merchant community; high remittance inflows from diaspora.",
    ),

    # ── Kerala ────────────────────────────────────────────────────────────────
    "kerala": DemographicProfile(
        state="Kerala",
        state_code="kerala",
        pg_location="India",
        population_m=35.0,
        urban_pct=0.477,
        median_age=32.0,
        literacy_rate=0.944,
        income_bands={"low": 0.28, "middle": 0.50, "high": 0.22},
        religious_composition={
            "hindu": 0.547, "muslim": 0.266, "christian": 0.184,
            "sikh": 0.000, "jain": 0.001, "buddhist": 0.001, "other": 0.001,
        },
        primary_language="Malayalam",
        languages=["Tamil", "Tulu", "Konkani", "Hindi"],
        region="south",
        tags=["highest_literacy", "high_remittance", "leftist_politics", "religious_pluralism", "health_outcomes"],
        notes="Highest literacy rate in India; large Gulf NRI population; strong communist party history.",
    ),

    # ── Punjab ────────────────────────────────────────────────────────────────
    "punjab": DemographicProfile(
        state="Punjab",
        state_code="punjab",
        pg_location="India",
        population_m=30.0,
        urban_pct=0.375,
        median_age=27.0,
        literacy_rate=0.757,
        income_bands={"low": 0.35, "middle": 0.50, "high": 0.15},
        religious_composition={
            "sikh": 0.577, "hindu": 0.385, "muslim": 0.019,
            "christian": 0.013, "buddhist": 0.002, "jain": 0.001, "other": 0.003,
        },
        primary_language="Punjabi",
        languages=["Hindi", "Urdu", "Dogri"],
        region="north",
        tags=["sikh_majority", "agrarian", "green_revolution", "high_nri", "drug_crisis"],
        notes="Only Sikh-majority state; agriculturally prosperous but facing farm distress and youth emigration.",
    ),

    # ── Telangana ─────────────────────────────────────────────────────────────
    "telangana": DemographicProfile(
        state="Telangana",
        state_code="telangana",
        pg_location="India",
        population_m=38.0,
        urban_pct=0.389,
        median_age=27.0,
        literacy_rate=0.665,
        income_bands={"low": 0.43, "middle": 0.44, "high": 0.13},
        religious_composition={
            "hindu": 0.851, "muslim": 0.127, "christian": 0.013,
            "sikh": 0.000, "buddhist": 0.003, "jain": 0.001, "other": 0.005,
        },
        primary_language="Telugu",
        languages=["Urdu", "Hindi", "Marathi"],
        region="south",
        tags=["newest_state", "hyderabad_tech_hub", "pharma", "politically_fluid"],
        notes="Formed 2014; Hyderabad is a major IT and pharma hub; Telangana Rashtra Samithi history.",
    ),

    # ── Andhra Pradesh ────────────────────────────────────────────────────────
    "andhra_pradesh": DemographicProfile(
        state="Andhra Pradesh",
        state_code="andhra_pradesh",
        pg_location="India",
        population_m=50.0,
        urban_pct=0.296,
        median_age=28.0,
        literacy_rate=0.672,
        income_bands={"low": 0.48, "middle": 0.42, "high": 0.10},
        religious_composition={
            "hindu": 0.908, "muslim": 0.091, "christian": 0.006,
            "sikh": 0.000, "buddhist": 0.001, "jain": 0.000, "other": 0.002,
        },
        primary_language="Telugu",
        languages=["Urdu", "Tamil", "Kannada", "Hindi"],
        region="south",
        tags=["post_bifurcation", "agrarian", "spice_hub", "coastal", "politically_volatile"],
        notes="Post-2014 bifurcation state (excluding Hyderabad); predominantly rural and agricultural.",
    ),

    # ── Madhya Pradesh ────────────────────────────────────────────────────────
    "madhya_pradesh": DemographicProfile(
        state="Madhya Pradesh",
        state_code="madhya_pradesh",
        pg_location="India",
        population_m=85.0,
        urban_pct=0.276,
        median_age=24.0,
        literacy_rate=0.700,
        income_bands={"low": 0.60, "middle": 0.32, "high": 0.08},
        religious_composition={
            "hindu": 0.909, "muslim": 0.066, "christian": 0.009,
            "sikh": 0.001, "jain": 0.005, "buddhist": 0.003, "other": 0.007,
        },
        primary_language="Hindi",
        languages=["Gondi", "Bundeli", "Malvi", "Urdu"],
        region="central",
        tags=["large_tribal_population", "agrarian", "hindi_belt", "landlocked", "mineral_rich"],
        notes="Largest state by area; significant Adivasi (tribal) population (~21%); BJP stronghold.",
    ),

    # ── Odisha ────────────────────────────────────────────────────────────────
    "odisha": DemographicProfile(
        state="Odisha",
        state_code="odisha",
        pg_location="India",
        population_m=46.0,
        urban_pct=0.167,
        median_age=26.0,
        literacy_rate=0.729,
        income_bands={"low": 0.62, "middle": 0.31, "high": 0.07},
        religious_composition={
            "hindu": 0.936, "christian": 0.028, "muslim": 0.022,
            "sikh": 0.000, "buddhist": 0.001, "jain": 0.000, "other": 0.013,
        },
        primary_language="Odia",
        languages=["Telugu", "Hindi", "Santali", "Bengali"],
        region="east",
        tags=["mineral_rich", "tribal_belt", "low_development", "coastal", "cyclone_prone"],
        notes="One of India's poorest states; rich in iron ore and coal; significant Adivasi population (~23%).",
    ),

    # ── Assam ─────────────────────────────────────────────────────────────────
    "assam": DemographicProfile(
        state="Assam",
        state_code="assam",
        pg_location="India",
        population_m=35.0,
        urban_pct=0.141,
        median_age=25.0,
        literacy_rate=0.728,
        income_bands={"low": 0.60, "middle": 0.32, "high": 0.08},
        religious_composition={
            "hindu": 0.615, "muslim": 0.342, "christian": 0.038,
            "sikh": 0.000, "buddhist": 0.000, "jain": 0.000, "other": 0.005,
        },
        primary_language="Assamese",
        languages=["Bengali", "Bodo", "Hindi", "Dimasa", "Karbi"],
        region="northeast",
        tags=["high_muslim_minority", "immigration_sensitive", "tea_economy", "NRC_issue", "border_state"],
        notes="NRC (National Register of Citizens) a highly charged political issue; significant Bengali and Bangladeshi migrant community.",
    ),

    # ── Jharkhand ─────────────────────────────────────────────────────────────
    "jharkhand": DemographicProfile(
        state="Jharkhand",
        state_code="jharkhand",
        pg_location="India",
        population_m=38.0,
        urban_pct=0.241,
        median_age=23.0,
        literacy_rate=0.668,
        income_bands={"low": 0.65, "middle": 0.29, "high": 0.06},
        religious_composition={
            "hindu": 0.678, "muslim": 0.145, "christian": 0.043,
            "sikh": 0.000, "buddhist": 0.000, "jain": 0.000, "other": 0.134,
        },
        primary_language="Hindi",
        languages=["Santali", "Bengali", "Odia", "Mundari", "Urdu"],
        region="east",
        tags=["mineral_rich", "tribal_belt", "low_development", "high_christian_tribal", "mining_displacement"],
        notes="Formed 2000 from Bihar; ~26% Adivasi population; significant Christian tribal communities; major coal/iron reserves.",
    ),

    # ── Chhattisgarh ──────────────────────────────────────────────────────────
    "chhattisgarh": DemographicProfile(
        state="Chhattisgarh",
        state_code="chhattisgarh",
        pg_location="India",
        population_m=29.0,
        urban_pct=0.232,
        median_age=23.0,
        literacy_rate=0.710,
        income_bands={"low": 0.63, "middle": 0.30, "high": 0.07},
        religious_composition={
            "hindu": 0.933, "christian": 0.022, "muslim": 0.020,
            "sikh": 0.000, "buddhist": 0.001, "jain": 0.001, "other": 0.023,
        },
        primary_language="Chhattisgarhi",
        languages=["Hindi", "Gondi", "Halbi", "Odia"],
        region="central",
        tags=["tribal_belt", "naxal_affected", "mineral_rich", "forest_cover", "low_urbanisation"],
        notes="Formed 2000 from MP; ~32% Adivasi population; historically Naxal-affected districts; rice bowl of central India.",
    ),

    # ── Uttarakhand ───────────────────────────────────────────────────────────
    "uttarakhand": DemographicProfile(
        state="Uttarakhand",
        state_code="uttarakhand",
        pg_location="India",
        population_m=11.0,
        urban_pct=0.302,
        median_age=26.0,
        literacy_rate=0.788,
        income_bands={"low": 0.50, "middle": 0.38, "high": 0.12},
        religious_composition={
            "hindu": 0.832, "muslim": 0.140, "sikh": 0.024,
            "christian": 0.004, "buddhist": 0.000, "jain": 0.000, "other": 0.000,
        },
        primary_language="Hindi",
        languages=["Garhwali", "Kumaoni", "Urdu"],
        region="north",
        tags=["hill_state", "tourism_pilgrimage", "army_recruitment", "himalayan", "migration_heavy"],
        notes="Census 2011. Formed 2000 from UP; major pilgrimage destinations (Char Dham); high out-migration to plains cities.",
    ),

    # ── Himachal Pradesh ──────────────────────────────────────────────────────
    "himachal_pradesh": DemographicProfile(
        state="Himachal Pradesh",
        state_code="himachal_pradesh",
        pg_location="India",
        population_m=7.0,
        urban_pct=0.100,
        median_age=26.0,
        literacy_rate=0.838,
        income_bands={"low": 0.40, "middle": 0.48, "high": 0.12},
        religious_composition={
            "hindu": 0.952, "muslim": 0.022, "sikh": 0.012,
            "buddhist": 0.012, "christian": 0.002, "jain": 0.000, "other": 0.000,
        },
        primary_language="Hindi",
        languages=["Pahari", "Punjabi", "Tibetan"],
        region="north",
        tags=["hill_state", "apple_economy", "tourism", "high_literacy", "hydropower", "army_recruitment"],
        notes="Census 2011. Most rural state in India (90%); high literacy; apple and tourism economy; Buddhist communities in Lahaul-Spiti.",
    ),

    # ── Haryana ───────────────────────────────────────────────────────────────
    "haryana": DemographicProfile(
        state="Haryana",
        state_code="haryana",
        pg_location="India",
        population_m=29.0,
        urban_pct=0.349,
        median_age=25.0,
        literacy_rate=0.766,
        income_bands={"low": 0.45, "middle": 0.42, "high": 0.13},
        religious_composition={
            "hindu": 0.875, "muslim": 0.070, "sikh": 0.049,
            "christian": 0.002, "jain": 0.001, "buddhist": 0.001, "other": 0.002,
        },
        primary_language="Hindi",
        languages=["Haryanvi", "Punjabi", "Urdu"],
        region="north",
        tags=["ncr_belt", "agrarian", "green_revolution", "high_sex_ratio_imbalance", "automotive_hub"],
        notes="Census 2011. Borders Delhi NCR; major automotive (Maruti, Hero) and IT belt; low female-to-male sex ratio.",
    ),

    # ── Goa ───────────────────────────────────────────────────────────────────
    "goa": DemographicProfile(
        state="Goa",
        state_code="goa",
        pg_location="India",
        population_m=1.6,
        urban_pct=0.622,
        median_age=31.0,
        literacy_rate=0.887,
        income_bands={"low": 0.25, "middle": 0.52, "high": 0.23},
        religious_composition={
            "hindu": 0.661, "christian": 0.251, "muslim": 0.083,
            "sikh": 0.001, "jain": 0.001, "buddhist": 0.000, "other": 0.003,
        },
        primary_language="Konkani",
        languages=["Marathi", "Portuguese", "Hindi", "English"],
        region="west",
        tags=["tourism_economy", "high_income", "christian_minority", "portuguese_heritage", "coastal", "liberal"],
        notes="Census 2011. Smallest state by area; highest per-capita income among Indian states; significant Portuguese-Catholic cultural influence.",
    ),

    # ── Jammu & Kashmir ───────────────────────────────────────────────────────
    "jammu_kashmir": DemographicProfile(
        state="Jammu & Kashmir",
        state_code="jammu_kashmir",
        pg_location="India",
        population_m=13.0,
        urban_pct=0.272,
        median_age=24.0,
        literacy_rate=0.687,
        income_bands={"low": 0.55, "middle": 0.36, "high": 0.09},
        religious_composition={
            "muslim": 0.683, "hindu": 0.284, "sikh": 0.020,
            "buddhist": 0.009, "christian": 0.002, "jain": 0.000, "other": 0.002,
        },
        primary_language="Kashmiri",
        languages=["Urdu", "Dogri", "Hindi", "Pahari", "Gojri"],
        region="north",
        tags=["muslim_majority", "conflict_sensitive", "tourism", "horticulture", "politically_charged", "border_state"],
        notes=(
            "Census 2011 (pre-bifurcation). Reorganised in 2019 into J&K UT and Ladakh UT. "
            "This profile covers the combined former state. Muslim majority in Kashmir Valley; "
            "Hindu majority in Jammu division. Politically sensitive — handle with care."
        ),
    ),

    # ── India National (aggregate) ────────────────────────────────────────────
    "india": DemographicProfile(
        state="India (National)",
        state_code="india",
        pg_location="India",
        population_m=1400.0,
        urban_pct=0.355,
        median_age=28.0,
        literacy_rate=0.745,
        income_bands={"low": 0.52, "middle": 0.38, "high": 0.10},
        religious_composition={
            "hindu": 0.797, "muslim": 0.148, "christian": 0.023,
            "sikh": 0.017, "buddhist": 0.007, "jain": 0.004, "other": 0.004,
        },
        primary_language="Hindi",
        languages=["Bengali", "Tamil", "Telugu", "Marathi", "Gujarati",
                   "Urdu", "Kannada", "Malayalam", "Odia", "Punjabi"],
        region="national",
        tags=["national_aggregate", "diverse", "mixed_urban_rural"],
        notes="Weighted national aggregate — use state profiles for precision.",
    ),


    # ══════════════════════════════════════════════════════════════════════════
    # USA PROFILES
    # pg_location="United States" → PG routes to _US_GENERAL_POOL
    # Source: US Census Bureau 2020/2022 ACS; Pew 2023 religious data;
    #         BLS/World Bank 2022 income bands
    # Income bands: low = below 150% federal poverty line / bottom 30%,
    #               middle = 30–80th percentile, high = top 20%
    # ══════════════════════════════════════════════════════════════════════════

    # ── United States National ────────────────────────────────────────────────
    "united_states": DemographicProfile(
        state="United States",
        state_code="united_states",
        pg_location="United States",
        population_m=335.0,
        urban_pct=0.830,
        median_age=38.9,
        literacy_rate=0.990,
        income_bands={"low": 0.30, "middle": 0.50, "high": 0.20},
        religious_composition={
            "protestant": 0.40, "catholic": 0.21, "unaffiliated": 0.28,
            "muslim": 0.01, "jewish": 0.02, "other": 0.08,
        },
        primary_language="English",
        languages=["Spanish", "Chinese", "Tagalog", "Vietnamese", "French"],
        region="north_america",
        supports_religion_stratification=False,
        tags=["national_aggregate", "diverse", "high_income", "polarised"],
        notes=(
            "US national aggregate. Income bands: low=bottom 30%, middle=30–80th pct, "
            "high=top 20%. Religion: Pew 2023. stratify_by_religion uses income fallback."
        ),
    ),

    # ── US Northeast ──────────────────────────────────────────────────────────
    "us_northeast": DemographicProfile(
        state="US Northeast",
        state_code="us_northeast",
        pg_location="United States",
        population_m=57.0,
        urban_pct=0.870,
        median_age=40.0,
        literacy_rate=0.990,
        income_bands={"low": 0.24, "middle": 0.48, "high": 0.28},
        religious_composition={
            "catholic": 0.32, "protestant": 0.26, "unaffiliated": 0.32,
            "jewish": 0.04, "muslim": 0.02, "other": 0.04,
        },
        primary_language="English",
        languages=["Spanish", "Chinese", "Italian", "Portuguese", "French"],
        region="us_northeast",
        supports_religion_stratification=False,
        tags=["high_income", "highly_educated", "urban_dense", "liberal_leaning"],
        notes="NY, NJ, PA, CT, MA, VT, NH, ME, RI aggregate.",
    ),

    # ── US South ──────────────────────────────────────────────────────────────
    "us_south": DemographicProfile(
        state="US South",
        state_code="us_south",
        pg_location="United States",
        population_m=130.0,
        urban_pct=0.740,
        median_age=37.0,
        literacy_rate=0.985,
        income_bands={"low": 0.35, "middle": 0.49, "high": 0.16},
        religious_composition={
            "protestant": 0.58, "catholic": 0.14, "unaffiliated": 0.20,
            "muslim": 0.01, "jewish": 0.01, "other": 0.06,
        },
        primary_language="English",
        languages=["Spanish", "Creole", "Vietnamese", "Tagalog"],
        region="us_south",
        supports_religion_stratification=False,
        tags=["evangelical_heavy", "conservative_leaning", "fast_growing", "mixed_urban_rural"],
        notes="TX, FL, GA, NC, VA, SC, TN, AL, MS, LA, AR, KY, OK, WV, MD, DE aggregate.",
    ),

    # ── US Midwest ────────────────────────────────────────────────────────────
    "us_midwest": DemographicProfile(
        state="US Midwest",
        state_code="us_midwest",
        pg_location="United States",
        population_m=69.0,
        urban_pct=0.780,
        median_age=39.0,
        literacy_rate=0.988,
        income_bands={"low": 0.28, "middle": 0.53, "high": 0.19},
        religious_composition={
            "protestant": 0.48, "catholic": 0.22, "unaffiliated": 0.24,
            "muslim": 0.01, "jewish": 0.01, "other": 0.04,
        },
        primary_language="English",
        languages=["Spanish", "German", "Polish", "Somali"],
        region="us_midwest",
        supports_religion_stratification=False,
        tags=["rust_belt", "manufacturing", "middle_america", "swing_state_heavy"],
        notes="IL, OH, MI, MN, WI, IN, MO, IA, KS, NE, SD, ND aggregate.",
    ),

    # ── US West ───────────────────────────────────────────────────────────────
    "us_west": DemographicProfile(
        state="US West",
        state_code="us_west",
        pg_location="United States",
        population_m=79.0,
        urban_pct=0.910,
        median_age=37.0,
        literacy_rate=0.990,
        income_bands={"low": 0.27, "middle": 0.49, "high": 0.24},
        religious_composition={
            "protestant": 0.30, "catholic": 0.22, "unaffiliated": 0.36,
            "muslim": 0.01, "buddhist": 0.02, "other": 0.09,
        },
        primary_language="English",
        languages=["Spanish", "Chinese", "Tagalog", "Korean", "Vietnamese"],
        region="us_west",
        supports_religion_stratification=False,
        tags=["tech_hub", "high_income", "liberal_leaning", "diverse", "urban_dense"],
        notes="CA, WA, OR, CO, AZ, NV, NM, UT, MT, ID, WY, AK, HI aggregate.",
    ),

    # ── California ────────────────────────────────────────────────────────────
    "california": DemographicProfile(
        state="California",
        state_code="california",
        pg_location="United States",
        population_m=39.0,
        urban_pct=0.950,
        median_age=37.0,
        literacy_rate=0.990,
        income_bands={"low": 0.26, "middle": 0.48, "high": 0.26},
        religious_composition={
            "protestant": 0.28, "catholic": 0.28, "unaffiliated": 0.31,
            "muslim": 0.01, "jewish": 0.02, "buddhist": 0.02, "other": 0.08,
        },
        primary_language="English",
        languages=["Spanish", "Chinese", "Tagalog", "Vietnamese", "Korean"],
        region="us_west",
        supports_religion_stratification=False,
        tags=["tech_hub", "diverse", "high_cost", "progressive", "largest_state_economy"],
        notes="Most populous US state; income bands include high Bay Area COLA.",
    ),

    # ── Texas ─────────────────────────────────────────────────────────────────
    "texas": DemographicProfile(
        state="Texas",
        state_code="texas",
        pg_location="United States",
        population_m=30.0,
        urban_pct=0.850,
        median_age=35.0,
        literacy_rate=0.988,
        income_bands={"low": 0.32, "middle": 0.50, "high": 0.18},
        religious_composition={
            "protestant": 0.46, "catholic": 0.23, "unaffiliated": 0.22,
            "muslim": 0.01, "jewish": 0.01, "other": 0.07,
        },
        primary_language="English",
        languages=["Spanish", "Vietnamese", "Chinese", "Tagalog"],
        region="us_south",
        supports_religion_stratification=False,
        tags=["fast_growing", "energy", "diverse_economy", "political_battleground", "hispanic_heavy"],
        notes="Second most populous US state; significant Hispanic population (~40%).",
    ),

    # ── New York ──────────────────────────────────────────────────────────────
    "new_york": DemographicProfile(
        state="New York",
        state_code="new_york",
        pg_location="United States",
        population_m=19.5,
        urban_pct=0.880,
        median_age=38.0,
        literacy_rate=0.990,
        income_bands={"low": 0.26, "middle": 0.46, "high": 0.28},
        religious_composition={
            "catholic": 0.31, "protestant": 0.24, "unaffiliated": 0.30,
            "jewish": 0.06, "muslim": 0.03, "other": 0.06,
        },
        primary_language="English",
        languages=["Spanish", "Chinese", "Yiddish", "Russian", "Bengali"],
        region="us_northeast",
        supports_religion_stratification=False,
        tags=["financial_hub", "cultural_centre", "high_income", "diverse", "urban"],
        notes="NYC dominates; significant income disparity between NYC metro and upstate.",
    ),

    # ── Florida ───────────────────────────────────────────────────────────────
    "florida": DemographicProfile(
        state="Florida",
        state_code="florida",
        pg_location="United States",
        population_m=22.0,
        urban_pct=0.910,
        median_age=42.0,
        literacy_rate=0.987,
        income_bands={"low": 0.31, "middle": 0.50, "high": 0.19},
        religious_composition={
            "protestant": 0.44, "catholic": 0.22, "unaffiliated": 0.23,
            "jewish": 0.03, "muslim": 0.01, "other": 0.07,
        },
        primary_language="English",
        languages=["Spanish", "Haitian Creole", "Portuguese", "French"],
        region="us_south",
        supports_religion_stratification=False,
        tags=["retirement_heavy", "tourism", "hispanic_heavy", "political_swing_state", "warm_climate"],
        notes="Oldest median age of key US states; large Cuban and Puerto Rican populations.",
    ),


    # ── Illinois ──────────────────────────────────────────────────────────────
    "illinois": DemographicProfile(
        state="Illinois",
        state_code="illinois",
        pg_location="United States",
        population_m=12.6,
        urban_pct=0.880,
        median_age=38.0,
        literacy_rate=0.989,
        income_bands={"low": 0.28, "middle": 0.51, "high": 0.21},
        religious_composition={
            "protestant": 0.34, "catholic": 0.28, "unaffiliated": 0.28,
            "muslim": 0.02, "jewish": 0.02, "other": 0.06,
        },
        primary_language="English",
        languages=["Spanish", "Polish", "Chinese", "Tagalog", "Hindi"],
        region="us_midwest",
        supports_religion_stratification=False,
        tags=["chicago_metro", "financial_hub", "diverse", "rust_belt", "swing_state"],
        notes="Chicago dominates; significant Polish and Hispanic communities; high income disparity between metro and downstate.",
    ),

    # ── Pennsylvania ──────────────────────────────────────────────────────────
    "pennsylvania": DemographicProfile(
        state="Pennsylvania",
        state_code="pennsylvania",
        pg_location="United States",
        population_m=13.0,
        urban_pct=0.790,
        median_age=40.0,
        literacy_rate=0.988,
        income_bands={"low": 0.28, "middle": 0.52, "high": 0.20},
        religious_composition={
            "protestant": 0.40, "catholic": 0.28, "unaffiliated": 0.24,
            "jewish": 0.03, "muslim": 0.01, "other": 0.04,
        },
        primary_language="English",
        languages=["Spanish", "Chinese", "Italian", "German", "Vietnamese"],
        region="us_northeast",
        supports_religion_stratification=False,
        tags=["swing_state", "philadelphia", "pittsburgh", "rust_belt", "older_population"],
        notes="Critical swing state; Philadelphia and Pittsburgh are dominant metros; strong Catholic tradition.",
    ),

    # ── Ohio ──────────────────────────────────────────────────────────────────
    "ohio": DemographicProfile(
        state="Ohio",
        state_code="ohio",
        pg_location="United States",
        population_m=11.8,
        urban_pct=0.780,
        median_age=39.0,
        literacy_rate=0.988,
        income_bands={"low": 0.30, "middle": 0.52, "high": 0.18},
        religious_composition={
            "protestant": 0.50, "catholic": 0.18, "unaffiliated": 0.24,
            "muslim": 0.01, "jewish": 0.01, "other": 0.06,
        },
        primary_language="English",
        languages=["Spanish", "Somali", "Chinese", "Arabic"],
        region="us_midwest",
        supports_religion_stratification=False,
        tags=["swing_state", "columbus_growth", "manufacturing", "middle_america", "working_class"],
        notes="Classic swing state; Columbus is fastest-growing Midwest city; strong Evangelical Protestant base.",
    ),

    # ── Georgia ───────────────────────────────────────────────────────────────
    "georgia": DemographicProfile(
        state="Georgia",
        state_code="georgia",
        pg_location="United States",
        population_m=10.9,
        urban_pct=0.750,
        median_age=36.0,
        literacy_rate=0.987,
        income_bands={"low": 0.33, "middle": 0.49, "high": 0.18},
        religious_composition={
            "protestant": 0.55, "catholic": 0.10, "unaffiliated": 0.22,
            "muslim": 0.02, "jewish": 0.01, "other": 0.10,
        },
        primary_language="English",
        languages=["Spanish", "Korean", "Vietnamese", "Amharic", "Chinese"],
        region="us_south",
        supports_religion_stratification=False,
        tags=["atlanta_hub", "diverse_south", "fast_growing", "evangelical", "black_voter_power", "swing_state"],
        notes="Atlanta is a major Black cultural and business hub; rapidly diversifying; evangelical Christianity dominant outside metro.",
    ),

    # ── North Carolina ────────────────────────────────────────────────────────
    "north_carolina": DemographicProfile(
        state="North Carolina",
        state_code="north_carolina",
        pg_location="United States",
        population_m=10.6,
        urban_pct=0.660,
        median_age=38.0,
        literacy_rate=0.988,
        income_bands={"low": 0.32, "middle": 0.51, "high": 0.17},
        religious_composition={
            "protestant": 0.55, "catholic": 0.09, "unaffiliated": 0.25,
            "muslim": 0.01, "jewish": 0.01, "other": 0.09,
        },
        primary_language="English",
        languages=["Spanish", "Chinese", "Vietnamese", "Korean"],
        region="us_south",
        supports_religion_stratification=False,
        tags=["research_triangle", "tech_growth", "charlotte_finance", "evangelical", "fast_growing", "swing_state"],
        notes="Research Triangle (Raleigh-Durham) is a major tech/biotech hub; Charlotte is a banking centre; mixed urban-rural population.",
    ),

    # ── Washington ────────────────────────────────────────────────────────────
    "washington": DemographicProfile(
        state="Washington",
        state_code="washington",
        pg_location="United States",
        population_m=7.8,
        urban_pct=0.840,
        median_age=37.0,
        literacy_rate=0.991,
        income_bands={"low": 0.23, "middle": 0.48, "high": 0.29},
        religious_composition={
            "protestant": 0.25, "catholic": 0.17, "unaffiliated": 0.44,
            "buddhist": 0.02, "muslim": 0.01, "other": 0.11,
        },
        primary_language="English",
        languages=["Spanish", "Chinese", "Vietnamese", "Tagalog", "Korean"],
        region="us_west",
        supports_religion_stratification=False,
        tags=["seattle_tech", "amazon_microsoft", "highly_educated", "progressive", "high_income", "unaffiliated_heavy"],
        notes="Seattle is a global tech hub (Amazon, Microsoft, Boeing); highest unaffiliated rate in US; strong Asian-American community.",
    ),

    # ── Colorado ──────────────────────────────────────────────────────────────
    "colorado": DemographicProfile(
        state="Colorado",
        state_code="colorado",
        pg_location="United States",
        population_m=5.9,
        urban_pct=0.860,
        median_age=36.0,
        literacy_rate=0.991,
        income_bands={"low": 0.24, "middle": 0.49, "high": 0.27},
        religious_composition={
            "protestant": 0.30, "catholic": 0.18, "unaffiliated": 0.40,
            "muslim": 0.01, "jewish": 0.02, "other": 0.09,
        },
        primary_language="English",
        languages=["Spanish", "Vietnamese", "Chinese", "Somali"],
        region="us_west",
        supports_religion_stratification=False,
        tags=["denver_growth", "outdoor_lifestyle", "tech_hub", "educated", "progressive", "fast_growing"],
        notes="Denver metro is one of the fastest-growing US cities; outdoor lifestyle strongly influences consumer behavior.",
    ),

    # ── Arizona ───────────────────────────────────────────────────────────────
    "arizona": DemographicProfile(
        state="Arizona",
        state_code="arizona",
        pg_location="United States",
        population_m=7.4,
        urban_pct=0.900,
        median_age=37.0,
        literacy_rate=0.988,
        income_bands={"low": 0.31, "middle": 0.50, "high": 0.19},
        religious_composition={
            "protestant": 0.36, "catholic": 0.21, "unaffiliated": 0.31,
            "mormon": 0.04, "muslim": 0.01, "other": 0.07,
        },
        primary_language="English",
        languages=["Spanish", "Navajo", "Chinese", "Tagalog"],
        region="us_west",
        supports_religion_stratification=False,
        tags=["phoenix_growth", "retirement_sunbelt", "hispanic_heavy", "swing_state", "suburban_sprawl"],
        notes="Phoenix is among the fastest-growing US metros; large Hispanic and Native American populations; significant retirement community.",
    ),

    # ── Michigan ──────────────────────────────────────────────────────────────
    "michigan": DemographicProfile(
        state="Michigan",
        state_code="michigan",
        pg_location="United States",
        population_m=10.1,
        urban_pct=0.740,
        median_age=40.0,
        literacy_rate=0.988,
        income_bands={"low": 0.30, "middle": 0.51, "high": 0.19},
        religious_composition={
            "protestant": 0.44, "catholic": 0.20, "unaffiliated": 0.26,
            "muslim": 0.03, "jewish": 0.01, "other": 0.06,
        },
        primary_language="English",
        languages=["Spanish", "Arabic", "Hindi", "Chinese"],
        region="us_midwest",
        supports_religion_stratification=False,
        tags=["auto_industry", "detroit_decline_revival", "dearborn_arab_community", "swing_state", "rust_belt"],
        notes="Auto industry hub; Dearborn has the largest Arab-American community in the US; strong UAW union history.",
    ),

    # ── New Jersey ────────────────────────────────────────────────────────────
    "new_jersey": DemographicProfile(
        state="New Jersey",
        state_code="new_jersey",
        pg_location="United States",
        population_m=9.3,
        urban_pct=0.940,
        median_age=40.0,
        literacy_rate=0.991,
        income_bands={"low": 0.21, "middle": 0.47, "high": 0.32},
        religious_composition={
            "catholic": 0.34, "protestant": 0.24, "unaffiliated": 0.25,
            "jewish": 0.06, "muslim": 0.03, "hindu": 0.02, "other": 0.06,
        },
        primary_language="English",
        languages=["Spanish", "Hindi", "Portuguese", "Chinese", "Tagalog"],
        region="us_northeast",
        supports_religion_stratification=False,
        tags=["high_income", "densely_populated", "nyc_suburb", "diverse", "pharmaceutical_hub", "high_education"],
        notes="Highest median household income of all US states; densely populated NYC suburb; large South Asian community (Edison corridor).",
    ),

    # ── Massachusetts ─────────────────────────────────────────────────────────
    "massachusetts": DemographicProfile(
        state="Massachusetts",
        state_code="massachusetts",
        pg_location="United States",
        population_m=7.0,
        urban_pct=0.920,
        median_age=39.0,
        literacy_rate=0.993,
        income_bands={"low": 0.22, "middle": 0.46, "high": 0.32},
        religious_composition={
            "catholic": 0.34, "protestant": 0.21, "unaffiliated": 0.35,
            "jewish": 0.03, "muslim": 0.01, "other": 0.06,
        },
        primary_language="English",
        languages=["Spanish", "Portuguese", "Chinese", "Vietnamese", "Haitian Creole"],
        region="us_northeast",
        supports_religion_stratification=False,
        tags=["boston_innovation", "universities", "biotech", "high_education", "progressive", "high_income"],
        notes="Boston is a global hub for education, biotech, and finance; highest educational attainment rates in US.",
    ),

    # ── Virginia ──────────────────────────────────────────────────────────────
    "virginia": DemographicProfile(
        state="Virginia",
        state_code="virginia",
        pg_location="United States",
        population_m=8.7,
        urban_pct=0.760,
        median_age=38.0,
        literacy_rate=0.991,
        income_bands={"low": 0.24, "middle": 0.49, "high": 0.27},
        religious_composition={
            "protestant": 0.44, "catholic": 0.14, "unaffiliated": 0.28,
            "muslim": 0.02, "jewish": 0.02, "other": 0.10,
        },
        primary_language="English",
        languages=["Spanish", "Korean", "Vietnamese", "Tagalog", "Hindi"],
        region="us_south",
        supports_religion_stratification=False,
        tags=["dc_suburbs", "federal_workforce", "tech_corridor", "diverse", "swing_state", "high_income"],
        notes="Northern Virginia (NoVA) is a major tech and federal contractor hub; rapidly diversifying; DC suburbs dominate demographically.",
    ),


    # ══════════════════════════════════════════════════════════════════════════
    # UK PROFILE
    # pg_location="United Kingdom" → PG routes to _UK_GENERAL_POOL
    # Source: ONS Census 2021; Pew 2023 religious data; ONS income quintiles 2022
    # ══════════════════════════════════════════════════════════════════════════

    "united_kingdom": DemographicProfile(
        state="United Kingdom",
        state_code="united_kingdom",
        pg_location="United Kingdom",
        population_m=67.0,
        urban_pct=0.840,
        median_age=40.0,
        literacy_rate=0.990,
        income_bands={"low": 0.28, "middle": 0.50, "high": 0.22},
        religious_composition={
            "christian": 0.46, "unaffiliated": 0.37, "muslim": 0.06,
            "hindu": 0.02, "sikh": 0.01, "jewish": 0.01, "other": 0.07,
        },
        primary_language="English",
        languages=["Polish", "Punjabi", "Urdu", "Bengali", "Gujarati", "Welsh"],
        region="western_europe",
        supports_religion_stratification=False,
        tags=["post_brexit", "diverse_cities", "nhs_dominant", "polarised_by_age_and_region"],
        notes=(
            "ONS Census 2021. England, Scotland, Wales, Northern Ireland combined. "
            "stratify_by_religion uses income fallback for UK geographies."
        ),
    ),


    # ══════════════════════════════════════════════════════════════════════════
    # EUROPE PROFILES
    # pg_location=<country name> — PG has dedicated pools for these countries
    # accessed via _DOMAIN_POOLS (france_general, spain_general, etc.)
    # IMPORTANT: location-string routing may not apply; use pool_key anchor
    # override for direct pool access if standard location routing fails.
    # Source: Eurostat 2022; Pew 2023 religious data
    # ══════════════════════════════════════════════════════════════════════════

    "france": DemographicProfile(
        state="France",
        state_code="france",
        pg_location="France",
        population_m=68.0,
        urban_pct=0.810,
        median_age=42.0,
        literacy_rate=0.990,
        income_bands={"low": 0.27, "middle": 0.53, "high": 0.20},
        religious_composition={
            "christian": 0.41, "unaffiliated": 0.45, "muslim": 0.09,
            "jewish": 0.01, "other": 0.04,
        },
        primary_language="French",
        languages=["Arabic", "Portuguese", "Spanish", "Occitan", "Alsatian"],
        region="western_europe",
        supports_religion_stratification=False,
        tags=["secular_republic", "welfare_state", "polarised", "suburban_rural_divide"],
        notes="Eurostat 2022. PG routing via _FRANCE_GENERAL_POOL (domain pool key).",
    ),

    "germany": DemographicProfile(
        state="Germany",
        state_code="germany",
        pg_location="Germany",
        population_m=84.0,
        urban_pct=0.770,
        median_age=45.0,
        literacy_rate=0.990,
        income_bands={"low": 0.25, "middle": 0.55, "high": 0.20},
        religious_composition={
            "christian": 0.52, "unaffiliated": 0.38, "muslim": 0.07,
            "other": 0.03,
        },
        primary_language="German",
        languages=["Turkish", "Arabic", "Russian", "Polish", "Kurdish"],
        region="western_europe",
        supports_religion_stratification=False,
        tags=["industrial_powerhouse", "ageing", "high_wages", "eu_anchor", "east_west_divide"],
        notes=(
            "Eurostat 2022. PG does not have a dedicated _GERMANY_GENERAL_POOL in v1.0; "
            "generation may fall back to default pool. PG update needed for full support."
        ),
    ),

    "spain": DemographicProfile(
        state="Spain",
        state_code="spain",
        pg_location="Spain",
        population_m=47.0,
        urban_pct=0.810,
        median_age=44.0,
        literacy_rate=0.990,
        income_bands={"low": 0.29, "middle": 0.52, "high": 0.19},
        religious_composition={
            "christian": 0.60, "unaffiliated": 0.32, "muslim": 0.04,
            "other": 0.04,
        },
        primary_language="Spanish",
        languages=["Catalan", "Galician", "Basque", "Arabic"],
        region="southern_europe",
        supports_religion_stratification=False,
        tags=["regional_identity", "youth_unemployment", "tourism", "catholic_heritage"],
        notes="Eurostat 2022. PG routing via _SPAIN_GENERAL_POOL (domain pool key).",
    ),

    "italy": DemographicProfile(
        state="Italy",
        state_code="italy",
        pg_location="Italy",
        population_m=59.0,
        urban_pct=0.710,
        median_age=47.0,
        literacy_rate=0.990,
        income_bands={"low": 0.31, "middle": 0.50, "high": 0.19},
        religious_composition={
            "christian": 0.66, "unaffiliated": 0.28, "muslim": 0.04,
            "other": 0.02,
        },
        primary_language="Italian",
        languages=["Arabic", "Romanian", "Albanian", "German"],
        region="southern_europe",
        supports_religion_stratification=False,
        tags=["ageing", "north_south_divide", "catholic_heritage", "political_instability"],
        notes="Eurostat 2022. PG routing via _ITALY_GENERAL_POOL (domain pool key).",
    ),

    "netherlands": DemographicProfile(
        state="Netherlands",
        state_code="netherlands",
        pg_location="Netherlands",
        population_m=18.0,
        urban_pct=0.930,
        median_age=43.0,
        literacy_rate=0.990,
        income_bands={"low": 0.22, "middle": 0.55, "high": 0.23},
        religious_composition={
            "christian": 0.37, "unaffiliated": 0.51, "muslim": 0.07,
            "other": 0.05,
        },
        primary_language="Dutch",
        languages=["English", "Arabic", "Turkish", "Moroccan Arabic"],
        region="western_europe",
        supports_religion_stratification=False,
        tags=["highly_urbanised", "progressive", "trade_hub", "high_income", "digital_first"],
        notes="Eurostat 2022. PG routing via _NETHERLANDS_GENERAL_POOL (domain pool key).",
    ),

    "poland": DemographicProfile(
        state="Poland",
        state_code="poland",
        pg_location="Poland",
        population_m=37.0,
        urban_pct=0.600,
        median_age=42.0,
        literacy_rate=0.990,
        income_bands={"low": 0.30, "middle": 0.55, "high": 0.15},
        religious_composition={
            "christian": 0.86, "unaffiliated": 0.12, "other": 0.02,
        },
        primary_language="Polish",
        languages=["English", "German", "Russian", "Ukrainian"],
        region="eastern_europe",
        supports_religion_stratification=False,
        tags=["catholic_majority", "fast_growing_economy", "urban_rural_divide", "eu_beneficiary"],
        notes="Eurostat 2022. PG routing via _POLAND_GENERAL_POOL (domain pool key).",
    ),

    "sweden": DemographicProfile(
        state="Sweden",
        state_code="sweden",
        pg_location="Sweden",
        population_m=10.5,
        urban_pct=0.880,
        median_age=41.0,
        literacy_rate=0.990,
        income_bands={"low": 0.20, "middle": 0.57, "high": 0.23},
        religious_composition={
            "christian": 0.57, "unaffiliated": 0.31, "muslim": 0.08,
            "other": 0.04,
        },
        primary_language="Swedish",
        languages=["English", "Arabic", "Somali", "Finnish", "Persian"],
        region="northern_europe",
        supports_religion_stratification=False,
        tags=["high_welfare", "progressive", "immigration_debate", "digital_leader"],
        notes="Eurostat 2022. PG routing via _SWEDEN_GENERAL_POOL (domain pool key).",
    ),
}


# ── Public API ────────────────────────────────────────────────────────────────

def get_profile(state: str) -> DemographicProfile:
    """Return the DemographicProfile for a given geography.

    Args:
        state: Geography code (e.g. "west_bengal", "united_states", "france")
               or common alias (e.g. "West Bengal", "US", "USA", "UK").
               Case-insensitive.

    Returns:
        DemographicProfile for the requested geography.

    Raises:
        KeyError: If the geography is not in the profile library.
    """
    key = state.strip().lower().replace(" ", "_").replace("-", "_")

    # Direct lookup
    if key in _PROFILES:
        return _PROFILES[key]

    # Fuzzy alias lookup
    _ALIASES: dict[str, str] = {
        # India aliases
        "wb": "west_bengal",
        "bengal": "west_bengal",
        "wbengal": "west_bengal",
        "mh": "maharashtra",
        "bombay": "maharashtra",
        "mumbai": "maharashtra",
        "up": "uttar_pradesh",
        "br": "bihar",
        "tn": "tamil_nadu",
        "madras": "tamil_nadu",
        "ka": "karnataka",
        "bangalore": "karnataka",
        "bengaluru": "karnataka",
        "rj": "rajasthan",
        "dl": "delhi",
        "ncr": "delhi",
        "national": "india",
        "ind": "india",
        "gj": "gujarat",
        "gujrat": "gujarat",
        "kl": "kerala",
        "kerela": "kerala",
        "pb": "punjab",
        "tg": "telangana",
        "hyderabad": "telangana",
        "ap": "andhra_pradesh",
        "andhra": "andhra_pradesh",
        "mp": "madhya_pradesh",
        "od": "odisha",
        "orissa": "odisha",
        "as": "assam",
        "jh": "jharkhand",
        "cg": "chhattisgarh",
        "chattisgarh": "chhattisgarh",
        "uk": "uttarakhand",
        "uttrakhand": "uttarakhand",
        "hp": "himachal_pradesh",
        "himachal": "himachal_pradesh",
        "hr": "haryana",
        "ga": "goa",
        "jk": "jammu_kashmir",
        "j&k": "jammu_kashmir",
        "kashmir": "jammu_kashmir",
        "jammu": "jammu_kashmir",
        # USA aliases
        "us": "united_states",
        "usa": "united_states",
        "america": "united_states",
        "northeast": "us_northeast",
        "us_ne": "us_northeast",
        "south": "us_south",
        "us_s": "us_south",
        "midwest": "us_midwest",
        "us_mw": "us_midwest",
        "west": "us_west",
        "us_w": "us_west",
        "ca": "california",
        "tx": "texas",
        "ny": "new_york",
        "fl": "florida",
        "il": "illinois",
        "chicago": "illinois",
        "pa": "pennsylvania",
        "philly": "pennsylvania",
        "philadelphia": "pennsylvania",
        "oh": "ohio",
        "columbus": "ohio",
        "ga": "georgia",
        "atlanta": "georgia",
        "nc": "north_carolina",
        "charlotte": "north_carolina",
        "wa": "washington",
        "seattle": "washington",
        "co": "colorado",
        "denver": "colorado",
        "az": "arizona",
        "phoenix": "arizona",
        "mi": "michigan",
        "detroit": "michigan",
        "nj": "new_jersey",
        "ma": "massachusetts",
        "boston": "massachusetts",
        "va": "virginia",
        # UK aliases
        "uk": "united_kingdom",
        "britain": "united_kingdom",
        "england": "united_kingdom",
        "great_britain": "united_kingdom",
        # EU aliases
        "de": "germany",
        "fr": "france",
        "es": "spain",
        "it": "italy",
        "nl": "netherlands",
        "pl": "poland",
        "se": "sweden",
    }
    if key in _ALIASES:
        return _PROFILES[_ALIASES[key]]

    raise KeyError(
        f"No demographic profile found for '{state}'. "
        f"Available: {', '.join(sorted(_PROFILES))}. "
        f"Common aliases: us, usa, uk, de, fr, es, it, nl, pl, se, "
        f"wb, up, tn, dl, ind."
    )


def list_states() -> list[str]:
    """Return all available geography codes."""
    return sorted(_PROFILES)


def list_profiles() -> list[DemographicProfile]:
    """Return all DemographicProfile objects."""
    return list(_PROFILES.values())
