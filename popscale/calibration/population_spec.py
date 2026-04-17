"""population_spec — specification for a calibrated persona population.

PopulationSpec captures what demographic slice you want to simulate.
The calibrator converts it into PG-compatible anchor_override dicts.

Usage::

    from popscale.calibration.population_spec import PopulationSpec

    spec = PopulationSpec(
        state="west_bengal",
        n_personas=500,
        domain="policy",
        business_problem="How do West Bengal voters respond to fuel subsidy cuts?",
        age_min=25,
        age_max=60,
        stratify_by_religion=True,
        stratify_by_income=False,
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PopulationSpec:
    """Specification for a demographically calibrated persona population.

    Attributes:
        state:               State code or name (e.g. "west_bengal", "india").
                             Passed to get_profile() for demographic grounding.
        n_personas:          Total number of personas to generate.
        domain:              PG domain key (e.g. "policy", "consumer", "cpg").
        business_problem:    Research question for the cohort.
        age_min:             Minimum persona age. Default 18.
        age_max:             Maximum persona age. Default 65.
        urban_only:          If True, restrict to urban archetypes.
        rural_only:          If True, restrict to rural archetypes.
        stratify_by_religion: If True, split personas proportionally by
                              the state's religious composition (hindu/muslim/other).
        stratify_by_income:  If True, split personas proportionally by
                              the state's income bands (low/middle/high).
        extra_overrides:     Additional anchor_overrides merged into every segment.
        sarvam_enabled:      Pass sarvam_enabled=True to PG brief (India cultural
                             enrichment). Recommended for Indian state studies.
        client:              Optional client/brand name for PG brief.
        persona_id_prefix:   Prefix for generated persona IDs.
        min_segment_size:    Minimum personas per segment when stratifying.
                             Segments below this threshold are merged into "other".
    """
    state: str
    n_personas: int
    domain: str
    business_problem: str
    age_min: int = 18
    age_max: int = 65
    urban_only: bool = False
    rural_only: bool = False
    stratify_by_religion: bool = False
    stratify_by_income: bool = False
    extra_overrides: dict = field(default_factory=dict)
    sarvam_enabled: bool = False
    client: str = "PopScale"
    persona_id_prefix: str = "ps"
    min_segment_size: int = 5

    def __post_init__(self) -> None:
        if self.n_personas < 1:
            raise ValueError(f"n_personas must be >= 1, got {self.n_personas}")
        if self.age_min < 0 or self.age_max > 120:
            raise ValueError(f"age range must be 0–120, got {self.age_min}–{self.age_max}")
        if self.age_min >= self.age_max:
            raise ValueError(f"age_min must be < age_max, got {self.age_min} >= {self.age_max}")
        if self.urban_only and self.rural_only:
            raise ValueError("urban_only and rural_only cannot both be True")
        if self.min_segment_size < 1:
            raise ValueError(f"min_segment_size must be >= 1, got {self.min_segment_size}")

    def summary(self) -> str:
        parts = [
            f"state={self.state}",
            f"n={self.n_personas}",
            f"age={self.age_min}–{self.age_max}",
        ]
        if self.urban_only:
            parts.append("urban_only")
        if self.rural_only:
            parts.append("rural_only")
        if self.stratify_by_religion:
            parts.append("stratify:religion")
        if self.stratify_by_income:
            parts.append("stratify:income")
        return f"PopulationSpec({', '.join(parts)})"
