"""segmentation — group a population by decision outcome and profile each segment.

For choice scenarios: personas are mapped to their chosen option (fuzzy string
match handles LLM paraphrasing). Each segment is profiled by trait distribution,
average confidence, emotional valence, and most common key drivers.

For open-ended scenarios: personas are binned by emotional_valence into
positive / neutral / negative sentiment segments.

Design principles:
  - No LLM calls — deterministic from PopulationResponse fields
  - Works at any N (including small pilot cohorts)
  - unclassified_count tracks decisions that couldn't be mapped to any option
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Optional

from ..schema.population_response import PopulationResponse
from ..scenario.model import Scenario


# ── Option mapping ────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Lowercase, remove punctuation, collapse whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.lower())).strip()


def _map_to_option(decision: str, options: list[str]) -> Optional[int]:
    """Map a free-text LLM decision to the index of the nearest scenario option.

    Strategy (in priority order):
      1. Exact match after normalisation
      2. Option text is a substring of the decision (or vice versa)
      3. Best Jaccard word overlap above a minimum threshold

    Returns None if no option matches well enough (unclassified).
    """
    dec_norm = _normalize(decision)
    dec_words = set(dec_norm.split())

    # 1 — Exact normalised match
    for i, opt in enumerate(options):
        if _normalize(opt) == dec_norm:
            return i

    # 2 — Containment (option in decision, or decision in option)
    for i, opt in enumerate(options):
        opt_norm = _normalize(opt)
        if opt_norm and opt_norm in dec_norm:
            return i
        if dec_norm and dec_norm in opt_norm:
            return i

    # 3 — Best Jaccard word overlap (threshold 0.15 — loose, catches paraphrasing)
    best_score = 0.0
    best_idx: Optional[int] = None
    for i, opt in enumerate(options):
        opt_words = set(_normalize(opt).split())
        union = dec_words | opt_words
        if not union:
            continue
        jaccard = len(dec_words & opt_words) / len(union)
        if jaccard > best_score:
            best_score = jaccard
            best_idx = i

    return best_idx if best_score >= 0.15 else None


# ── Segment dataclasses ───────────────────────────────────────────────────────

@dataclass
class SegmentTraitProfile:
    """Trait distribution summary for a segment."""
    risk_appetite: dict[str, int]       = field(default_factory=dict)
    trust_anchor: dict[str, int]        = field(default_factory=dict)
    decision_style: dict[str, int]      = field(default_factory=dict)
    price_sensitivity: dict[str, int]   = field(default_factory=dict)
    switching_propensity: dict[str, int] = field(default_factory=dict)


@dataclass
class Segment:
    """A single decision segment within the population.

    Attributes:
        label:              Human-readable name (option text or valence label).
        option_index:       Index into scenario.options, or None for open-ended.
        count:              Number of personas in this segment.
        share:              Fraction of total population (0-1).
        trait_profile:      Distribution of categorical traits within segment.
        avg_confidence:     Mean decision confidence (0-1).
        avg_emotional_valence: Mean emotional valence (-1 to +1).
        representative_drivers: Top 3 most-cited key_drivers in this segment.
    """
    label: str
    option_index: Optional[int]
    count: int
    share: float
    trait_profile: SegmentTraitProfile
    avg_confidence: float
    avg_emotional_valence: float
    representative_drivers: list[str]


@dataclass
class SegmentationResult:
    """Full segmentation of a population run.

    Attributes:
        segments:           All segments, sorted by count descending.
        is_choice_scenario: True if the scenario had defined options.
        dominant_segment:   The segment with the highest count.
        unclassified_count: Responses that couldn't be mapped to any option.
        n_total:            Total responses analysed.
    """
    segments: list[Segment]
    is_choice_scenario: bool
    dominant_segment: Segment
    unclassified_count: int
    n_total: int


# ── Public API ────────────────────────────────────────────────────────────────

def segment_population(
    responses: list[PopulationResponse],
    scenario: Scenario,
) -> SegmentationResult:
    """Segment a population by decision outcome and profile each segment.

    Args:
        responses: All PopulationResponse objects from a population run.
        scenario:  The Scenario that was simulated.

    Returns:
        SegmentationResult with one Segment per distinct decision outcome.
    """
    n_total = len(responses)
    is_choice = scenario.is_choice_scenario()

    if is_choice:
        segments = _segment_choice(responses, scenario.options, n_total)
    else:
        segments = _segment_open_ended(responses, n_total)

    # Sort by count descending
    segments.sort(key=lambda s: s.count, reverse=True)

    unclassified = sum(
        1 for r in responses
        if is_choice and _map_to_option(r.decision, scenario.options) is None
    )

    dominant = segments[0] if segments else _empty_segment("(no responses)")

    return SegmentationResult(
        segments=segments,
        is_choice_scenario=is_choice,
        dominant_segment=dominant,
        unclassified_count=unclassified,
        n_total=n_total,
    )


# ── Internal builders ─────────────────────────────────────────────────────────

def _segment_choice(
    responses: list[PopulationResponse],
    options: list[str],
    n_total: int,
) -> list[Segment]:
    """Group by mapped option index."""
    buckets: dict[int, list[PopulationResponse]] = defaultdict(list)
    for r in responses:
        idx = _map_to_option(r.decision, options)
        if idx is not None:
            buckets[idx].append(r)

    segments = []
    for i, opt in enumerate(options):
        members = buckets.get(i, [])
        label = opt[:70] + ("…" if len(opt) > 70 else "")
        segments.append(_build_segment(label, i, members, n_total))

    return segments


def _segment_open_ended(
    responses: list[PopulationResponse],
    n_total: int,
) -> list[Segment]:
    """Group by emotional valence band for open-ended scenarios."""
    positive = [r for r in responses if r.emotional_valence > 0.2]
    neutral  = [r for r in responses if -0.2 <= r.emotional_valence <= 0.2]
    negative = [r for r in responses if r.emotional_valence < -0.2]

    return [
        _build_segment("Positive sentiment",  None, positive, n_total),
        _build_segment("Neutral / mixed",     None, neutral,  n_total),
        _build_segment("Negative sentiment",  None, negative, n_total),
    ]


def _build_segment(
    label: str,
    option_index: Optional[int],
    members: list[PopulationResponse],
    n_total: int,
) -> Segment:
    """Construct a Segment from a list of member responses."""
    count = len(members)
    share = count / n_total if n_total > 0 else 0.0

    if not members:
        return Segment(
            label=label,
            option_index=option_index,
            count=0,
            share=0.0,
            trait_profile=SegmentTraitProfile(),
            avg_confidence=0.0,
            avg_emotional_valence=0.0,
            representative_drivers=[],
        )

    # Trait distributions
    profile = SegmentTraitProfile(
        risk_appetite=dict(Counter(r.risk_appetite for r in members)),
        trust_anchor=dict(Counter(r.trust_anchor for r in members)),
        decision_style=dict(Counter(r.decision_style for r in members)),
        price_sensitivity=dict(Counter(r.price_sensitivity_band for r in members)),
        switching_propensity=dict(Counter(r.switching_propensity_band for r in members)),
    )

    avg_conf = sum(r.confidence for r in members) / count
    avg_valence = sum(r.emotional_valence for r in members) / count

    # Representative drivers: flatten all key_drivers lists, pick top 3
    all_drivers: list[str] = []
    for r in members:
        all_drivers.extend(r.key_drivers)
    top_drivers = [d for d, _ in Counter(all_drivers).most_common(3)]

    return Segment(
        label=label,
        option_index=option_index,
        count=count,
        share=round(share, 4),
        trait_profile=profile,
        avg_confidence=round(avg_conf, 3),
        avg_emotional_valence=round(avg_valence, 3),
        representative_drivers=top_drivers,
    )


def _empty_segment(label: str) -> Segment:
    return Segment(
        label=label,
        option_index=None,
        count=0,
        share=0.0,
        trait_profile=SegmentTraitProfile(),
        avg_confidence=0.0,
        avg_emotional_valence=0.0,
        representative_drivers=[],
    )
