"""calibrator — convert a PopulationSpec into PG-ready persona segments.

The calibrator reads demographic profile data and produces a list of
PersonaSegment objects, each with a count and anchor_overrides dict that
PG's PersonaGenerationBrief can consume directly.

Stratification logic:
  - religion: splits n_personas proportionally by hindu / muslim / other.
    "other" aggregates all non-hindu, non-muslim faiths.
    NOTE: Religion stratification is India-specific. For profiles where
    supports_religion_stratification=False (USA, UK, Europe), stratify_by_religion
    is silently treated as False and income stratification is used instead.
  - income: splits proportionally by low / middle / high bands.
  - combined: religion × income cross-stratification (use sparingly —
    small N leads to tiny segments below min_segment_size).

Usage::

    from popscale.calibration.calibrator import calibrate, PersonaSegment
    from popscale.calibration.population_spec import PopulationSpec

    spec = PopulationSpec(
        state="west_bengal",
        n_personas=100,
        domain="policy",
        business_problem="...",
        stratify_by_religion=True,
    )
    segments = calibrate(spec)
    for seg in segments:
        print(seg.label, seg.count, seg.anchor_overrides)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

from .profiles import DemographicProfile, get_profile
from .population_spec import PopulationSpec


# ── PersonaSegment ─────────────────────────────────────────────────────────────

@dataclass
class PersonaSegment:
    """A single demographic segment for persona generation.

    Attributes:
        count:            Number of personas to generate in this segment.
        domain:           PG domain key for persona pool (e.g. "bengal_jungle_mahal").
                          Defaults to "general" if not specified.
        anchor_overrides: Dict to pass as `anchor_overrides` in PG brief.
        label:            Human-readable description (e.g. "Hindu, middle income").
        proportion:       This segment's share of the total population (0–1).
    """
    count: int
    anchor_overrides: dict
    label: str
    domain: str = "general"
    proportion: float = 0.0


# ── Public API ─────────────────────────────────────────────────────────────────

def calibrate(spec: PopulationSpec) -> list[PersonaSegment]:
    """Produce demographically calibrated persona segments from a PopulationSpec.

    Segments respect stratification flags. If both stratify_by_religion and
    stratify_by_income are False, returns a single segment with the full
    cohort and base overrides.

    Args:
        spec: PopulationSpec describing the desired population.

    Returns:
        List of PersonaSegment objects whose counts sum to spec.n_personas.

    Raises:
        KeyError: If spec.state is not in the profile library.
    """
    profile = get_profile(spec.state)
    base_overrides = _build_base_overrides(spec, profile)

    # Religion stratification is India-specific. For non-India geographies,
    # the Hindu/Muslim/Other buckets and PG anchor overrides are not meaningful.
    # Fall back to income stratification with a logged notice.
    effective_religion = spec.stratify_by_religion and profile.supports_religion_stratification
    if spec.stratify_by_religion and not profile.supports_religion_stratification:
        logger.info(
            "calibrate | '%s' does not support religion stratification — "
            "using income stratification instead.",
            profile.state,
        )

    if effective_religion and spec.stratify_by_income:
        segments = _stratify_religion_income(spec, profile, base_overrides)
    elif effective_religion:
        segments = _stratify_religion(spec, profile, base_overrides)
    elif spec.stratify_by_income:
        segments = _stratify_income(spec, profile, base_overrides)
    else:
        segments = [PersonaSegment(
            count=spec.n_personas,
            domain=spec.domain,
            anchor_overrides=base_overrides,
            label=f"{profile.state} — general population",
            proportion=1.0,
        )]

    # Merge tiny segments and fix rounding so counts sum exactly to n_personas
    segments = _merge_tiny(segments, spec.min_segment_size, base_overrides, profile)
    segments = _fix_rounding(segments, spec.n_personas, base_overrides, profile)
    return segments


def build_cohort_breakdown(spec: PopulationSpec) -> dict:
    """Return a human-readable dict describing how the cohort will be split.

    Useful for pre-run cost review without actually generating personas.
    """
    segments = calibrate(spec)
    profile  = get_profile(spec.state)
    return {
        "state": profile.state,
        "total_personas": spec.n_personas,
        "domain": spec.domain,
        "age_range": f"{spec.age_min}–{spec.age_max}",
        "urban_filter": "urban only" if spec.urban_only
                        else "rural only" if spec.rural_only else "mixed",
        "stratification": {
            "religion": spec.stratify_by_religion,
            "income":   spec.stratify_by_income,
        },
        "segments": [
            {"label": s.label, "count": s.count, "proportion": round(s.proportion, 3)}
            for s in segments
        ],
    }


# ── Internal helpers ───────────────────────────────────────────────────────────

def _build_base_overrides(spec: PopulationSpec, profile: DemographicProfile) -> dict:
    """Build the anchor_overrides dict common to all segments."""
    overrides: dict = {
        "location": profile.pg_location,  # PG routes by location string to the correct pool
        "age_min":  spec.age_min,
        "age_max":  spec.age_max,
    }

    # Urban/rural hint — PG doesn't have a direct rural_only override,
    # so we add a tag note in the extra_overrides for the brief system.
    if spec.urban_only:
        overrides["location_type_hint"] = "urban"
    elif spec.rural_only:
        overrides["location_type_hint"] = "rural"

    # Merge caller-supplied extra overrides (may override any key above)
    overrides.update(spec.extra_overrides)
    return overrides


def _stratify_religion(
    spec: PopulationSpec,
    profile: DemographicProfile,
    base_overrides: dict,
) -> list[PersonaSegment]:
    """Split cohort proportionally by religion."""
    rel = profile.religious_composition

    # Collapse to three buckets: hindu / muslim / other
    hindu_pct   = rel.get("hindu", 0.0)
    muslim_pct  = rel.get("muslim", 0.0)
    other_pct   = 1.0 - hindu_pct - muslim_pct

    buckets = [
        ("Hindu",  hindu_pct,  {"religiosity": "hindu"}),
        ("Muslim", muslim_pct, {"religiosity": "muslim"}),
        ("Other",  other_pct,  {}),
    ]

    return _proportional_segments(
        buckets=buckets,
        n_total=spec.n_personas,
        base_overrides=base_overrides,
    )


def _stratify_income(
    spec: PopulationSpec,
    profile: DemographicProfile,
    base_overrides: dict,
) -> list[PersonaSegment]:
    """Split cohort proportionally by income band."""
    inc = profile.income_bands

    buckets = [
        ("Low income",    inc.get("low",    0.4), {"income_band": "low"}),
        ("Middle income", inc.get("middle", 0.4), {"income_band": "middle"}),
        ("High income",   inc.get("high",   0.2), {"income_band": "high"}),
    ]

    return _proportional_segments(
        buckets=buckets,
        n_total=spec.n_personas,
        base_overrides=base_overrides,
    )


def _stratify_religion_income(
    spec: PopulationSpec,
    profile: DemographicProfile,
    base_overrides: dict,
) -> list[PersonaSegment]:
    """Cross-stratify by religion × income. Produces up to 9 segments."""
    rel = profile.religious_composition
    inc = profile.income_bands

    hindu_pct   = rel.get("hindu",  0.0)
    muslim_pct  = rel.get("muslim", 0.0)
    other_pct   = 1.0 - hindu_pct - muslim_pct

    religion_buckets = [
        ("Hindu",  hindu_pct,  {"religiosity": "hindu"}),
        ("Muslim", muslim_pct, {"religiosity": "muslim"}),
        ("Other",  other_pct,  {}),
    ]
    income_buckets = [
        ("low income",    inc.get("low",    0.4), {"income_band": "low"}),
        ("middle income", inc.get("middle", 0.4), {"income_band": "middle"}),
        ("high income",   inc.get("high",   0.2), {"income_band": "high"}),
    ]

    segments: list[PersonaSegment] = []
    for rel_label, rel_pct, rel_overrides in religion_buckets:
        for inc_label, inc_pct, inc_overrides in income_buckets:
            combined_pct  = rel_pct * inc_pct
            combined_count = max(round(combined_pct * spec.n_personas), 0)
            overrides = {**base_overrides, **rel_overrides, **inc_overrides}
            segments.append(PersonaSegment(
                count=combined_count,
                anchor_overrides=overrides,
                label=f"{rel_label}, {inc_label} — {profile.state}",
                proportion=round(combined_pct, 4),
            ))

    return segments


def _proportional_segments(
    buckets: list[tuple[str, float, dict]],
    n_total: int,
    base_overrides: dict,
) -> list[PersonaSegment]:
    """Convert (label, proportion, extra_overrides) buckets into PersonaSegments."""
    segments: list[PersonaSegment] = []
    for label, pct, extra in buckets:
        count = max(round(pct * n_total), 0)
        overrides = {**base_overrides, **extra}
        segments.append(PersonaSegment(
            count=count,
            anchor_overrides=overrides,
            label=label,
            proportion=round(pct, 4),
        ))
    return segments


def _merge_tiny(
    segments: list[PersonaSegment],
    min_size: int,
    base_overrides: dict,
    profile: DemographicProfile,
) -> list[PersonaSegment]:
    """Merge segments below min_size into an 'Other' remainder bucket."""
    keep: list[PersonaSegment]   = []
    absorbed_count = 0

    for seg in segments:
        if seg.count >= min_size:
            keep.append(seg)
        else:
            absorbed_count += seg.count

    if absorbed_count > 0:
        keep.append(PersonaSegment(
            count=absorbed_count,
            anchor_overrides=base_overrides,
            label=f"Other — {profile.state}",
            proportion=round(absorbed_count / max(sum(s.count for s in segments), 1), 4),
        ))

    return keep if keep else segments  # never return empty list


def _fix_rounding(
    segments: list[PersonaSegment],
    target: int,
    base_overrides: dict,
    profile: DemographicProfile,
) -> list[PersonaSegment]:
    """Ensure segment counts sum exactly to target by adjusting the largest segment."""
    if not segments:
        return segments

    current_total = sum(s.count for s in segments)
    diff = target - current_total

    if diff == 0:
        return segments

    # Adjust the segment with the largest count
    largest_idx = max(range(len(segments)), key=lambda i: segments[i].count)
    segments[largest_idx] = PersonaSegment(
        count=max(segments[largest_idx].count + diff, 1),
        anchor_overrides=segments[largest_idx].anchor_overrides,
        label=segments[largest_idx].label,
        proportion=segments[largest_idx].proportion,
    )
    return segments
