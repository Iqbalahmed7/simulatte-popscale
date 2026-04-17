"""distributions — option probability distributions with confidence intervals.

For choice scenarios: counts per option and Wilson score 95% confidence intervals.
Wilson score intervals are used instead of the normal approximation because they
remain valid at small N and are never out of [0, 1].

For open-ended scenarios: sentiment distribution from emotional_valence
and a summary of the confidence / valence spread.

Design principles:
  - No external dependencies (pure Python math)
  - Wilson CI valid at any N ≥ 1
  - All proportions are 0-1; percentages are for display only
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Optional

from ..schema.population_response import PopulationResponse
from ..scenario.model import Scenario
from .segmentation import _map_to_option


# ── Wilson score confidence interval ─────────────────────────────────────────

def _wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score confidence interval for a proportion k/n.

    Returns (lower, upper), both in [0, 1].
    Falls back to (0, 1) when n == 0.
    """
    if n == 0:
        return 0.0, 1.0
    p_hat = k / n
    z2 = z * z
    denominator = 1.0 + z2 / n
    centre = (p_hat + z2 / (2 * n)) / denominator
    margin = (z * math.sqrt(p_hat * (1 - p_hat) / n + z2 / (4 * n * n))) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)


# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class OptionResult:
    """Distribution statistics for a single scenario option.

    Attributes:
        option:         The option text.
        option_index:   Index in scenario.options.
        count:          Number of personas who chose this option.
        proportion:     Point estimate (0-1).
        ci_lower:       Lower bound of 95% Wilson CI.
        ci_upper:       Upper bound of 95% Wilson CI.
        avg_confidence: Mean decision confidence among choosers (0-1).
        avg_valence:    Mean emotional valence among choosers (-1 to +1).
    """
    option: str
    option_index: int
    count: int
    proportion: float
    ci_lower: float
    ci_upper: float
    avg_confidence: float
    avg_valence: float


@dataclass
class SentimentBand:
    """Sentiment statistics for open-ended scenario distributions."""
    label: str               # "positive" | "neutral" | "negative"
    count: int
    proportion: float
    ci_lower: float
    ci_upper: float
    avg_valence: float


@dataclass
class DistributionResult:
    """Full distributional summary of a population run.

    Attributes:
        is_choice_scenario: True if the scenario had defined options.
        n_total:            Total responses analysed.
        n_unclassified:     Responses not mapped to any option (choice only).
        options:            Per-option statistics (choice scenarios only).
        sentiment:          Sentiment band statistics (open-ended only).
        median_confidence:  Median decision confidence across all responses.
        median_valence:     Median emotional valence across all responses.
        mean_confidence:    Mean decision confidence.
        mean_valence:       Mean emotional valence.
        leading_option:     Option with highest proportion (choice only).
    """
    is_choice_scenario: bool
    n_total: int
    n_unclassified: int
    options: list[OptionResult]
    sentiment: list[SentimentBand]
    median_confidence: float
    median_valence: float
    mean_confidence: float
    mean_valence: float
    leading_option: Optional[OptionResult]   # choice only


# ── Public API ────────────────────────────────────────────────────────────────

def compute_distributions(
    responses: list[PopulationResponse],
    scenario: Scenario,
) -> DistributionResult:
    """Compute option probability distributions with 95% Wilson CIs.

    Args:
        responses: All PopulationResponse objects from a population run.
        scenario:  The Scenario that was simulated.

    Returns:
        DistributionResult with per-option proportions and confidence intervals.
    """
    n_total = len(responses)
    is_choice = scenario.is_choice_scenario()

    # Aggregate confidence and valence across all responses
    all_conf    = [r.confidence for r in responses]
    all_valence = [r.emotional_valence for r in responses]
    median_conf    = statistics.median(all_conf)    if all_conf    else 0.0
    median_valence = statistics.median(all_valence) if all_valence else 0.0
    mean_conf      = sum(all_conf)    / n_total if n_total else 0.0
    mean_valence   = sum(all_valence) / n_total if n_total else 0.0

    if is_choice:
        options, n_unclassified = _choice_distributions(responses, scenario.options, n_total)
        leading = max(options, key=lambda o: o.proportion) if options else None
        sentiment: list[SentimentBand] = []
    else:
        options = []
        n_unclassified = 0
        leading = None
        sentiment = _sentiment_distributions(responses, n_total)

    return DistributionResult(
        is_choice_scenario=is_choice,
        n_total=n_total,
        n_unclassified=n_unclassified,
        options=options,
        sentiment=sentiment,
        median_confidence=round(median_conf, 3),
        median_valence=round(median_valence, 3),
        mean_confidence=round(mean_conf, 3),
        mean_valence=round(mean_valence, 3),
        leading_option=leading,
    )


# ── Internal builders ─────────────────────────────────────────────────────────

def _choice_distributions(
    responses: list[PopulationResponse],
    options: list[str],
    n_total: int,
) -> tuple[list[OptionResult], int]:
    """Build per-option OptionResult objects and count unclassified."""
    # Map each response to an option index
    mapped: dict[int, list[PopulationResponse]] = {i: [] for i in range(len(options))}
    n_unclassified = 0

    for r in responses:
        idx = _map_to_option(r.decision, options)
        if idx is not None:
            mapped[idx].append(r)
        else:
            n_unclassified += 1

    results = []
    for i, opt in enumerate(options):
        members = mapped[i]
        k = len(members)
        proportion = k / n_total if n_total else 0.0
        ci_lower, ci_upper = _wilson_ci(k, n_total)

        avg_conf = sum(r.confidence for r in members) / k if k else 0.0
        avg_val  = sum(r.emotional_valence for r in members) / k if k else 0.0

        results.append(OptionResult(
            option=opt,
            option_index=i,
            count=k,
            proportion=round(proportion, 4),
            ci_lower=round(ci_lower, 4),
            ci_upper=round(ci_upper, 4),
            avg_confidence=round(avg_conf, 3),
            avg_valence=round(avg_val, 3),
        ))

    return results, n_unclassified


def _sentiment_distributions(
    responses: list[PopulationResponse],
    n_total: int,
) -> list[SentimentBand]:
    """Segment open-ended responses into positive / neutral / negative bands."""
    bands = [
        ("positive", [r for r in responses if r.emotional_valence > 0.2]),
        ("neutral",  [r for r in responses if -0.2 <= r.emotional_valence <= 0.2]),
        ("negative", [r for r in responses if r.emotional_valence < -0.2]),
    ]
    results = []
    for label, members in bands:
        k = len(members)
        proportion = k / n_total if n_total else 0.0
        ci_lower, ci_upper = _wilson_ci(k, n_total)
        avg_val = sum(r.emotional_valence for r in members) / k if k else 0.0
        results.append(SentimentBand(
            label=label,
            count=k,
            proportion=round(proportion, 4),
            ci_lower=round(ci_lower, 4),
            ci_upper=round(ci_upper, 4),
            avg_valence=round(avg_val, 3),
        ))
    return results
