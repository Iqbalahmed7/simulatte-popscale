"""
Ground truth schemas for election calibration datasets.

All datasets conform to a canonical Pydantic v2 schema for normalized access.
"""

from pydantic import BaseModel
from typing import Optional


class GroundTruthUnit(BaseModel):
    """Single unit (county, constituency, etc.) election outcome."""

    unit_id: str
    """Unique identifier: county FIPS, constituency code, etc."""

    unit_name: str
    """Human-readable name: county name, constituency name."""

    outcomes: dict[str, float]
    """Vote share by party_id, as percentage (0-100 scale).

    Example:
        {"trump_pct": 45.2, "harris_pct": 52.1, "other_pct": 2.7}
    """

    winner: str
    """party_id of the winning party."""

    margin_pct: float
    """Winner's margin as percentage (0-100 scale).

    Computed as winner_vote_pct - runner_up_vote_pct.
    """

    turnout_pct: Optional[float] = None
    """Voter turnout as percentage (0-100), if available."""

    demographic_enrichment: Optional[dict] = None
    """Optional demographic context joined from census/survey data.

    Schema varies by election but may include:
        - age_dist: {age_range: pct, ...}
        - income_dist: {income_bracket: pct, ...}
        - education_dist: {education_level: pct, ...}
        - religion_dist: {religion: pct, ...}
        - urban_rural: {"urban": pct, "rural": pct}
    """

    metadata: Optional[dict] = None
    """Arbitrary metadata dict for source-specific fields."""


class GroundTruth(BaseModel):
    """Complete election dataset at canonical granularity."""

    election_id: str
    """Canonical ID: 'us_2024_pres', 'wb_2021_assembly', etc."""

    date: str
    """ISO 8601 date string (YYYY-MM-DD)."""

    granularity: str
    """Spatial granularity: 'county', 'constituency', 'ward'."""

    units: list[GroundTruthUnit]
    """All units in this election."""
