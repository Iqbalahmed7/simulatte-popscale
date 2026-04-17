"""drivers — key driver analysis for PopScale population runs.

Identifies which PersonaRecord attributes most strongly predict decision outcome,
using effect size statistics:
  - Cramér's V  — for categorical predictors vs. categorical outcome
  - Eta²        — for continuous predictors vs. categorical outcome (one-way ANOVA)

Both statistics are implemented in pure Python with no external dependencies.

Effect size interpretation (Cohen's conventions adapted for Cramér's V):
  < 0.10  — negligible  (below report threshold)
  0.10–0.29 — small
  0.30–0.49 — medium
  ≥ 0.50  — strong

Only effects ≥ 0.10 are reported as significant. This guards against false
precision at small N (< 50). Results at N < 30 are annotated as directional only.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Literal

from ..schema.population_response import PopulationResponse
from ..scenario.model import Scenario
from .segmentation import _map_to_option


# ── Effect size thresholds ────────────────────────────────────────────────────

_SIGNIFICANT_THRESHOLD = 0.10
_DIRECTIONAL_N_WARNING = 30

_EFFECT_LABELS = [
    (0.50, "strong"),
    (0.30, "medium"),
    (0.10, "small"),
    (0.00, "negligible"),
]


def _effect_label(v: float) -> str:
    for threshold, label in _EFFECT_LABELS:
        if v >= threshold:
            return label
    return "negligible"


# ── Pure Python stats ─────────────────────────────────────────────────────────

def _cramers_v(outcomes: list[str], attrs: list[str]) -> float:
    """Cramér's V — association between two categorical variables.

    Ranges 0 (no association) to 1 (perfect association).
    Returns 0.0 if either variable has fewer than 2 distinct values.
    """
    n = len(outcomes)
    if n < 2:
        return 0.0

    outcome_vals = sorted(set(outcomes))
    attr_vals    = sorted(set(attrs))
    k = len(outcome_vals)   # number of outcome categories
    r = len(attr_vals)      # number of attribute categories

    if k < 2 or r < 2:
        return 0.0

    row_counts = Counter(outcomes)
    col_counts = Counter(attrs)
    cell_counts = Counter(zip(outcomes, attrs))

    chi2 = 0.0
    for ov in outcome_vals:
        for av in attr_vals:
            observed = cell_counts.get((ov, av), 0)
            expected = row_counts[ov] * col_counts[av] / n
            if expected > 0:
                chi2 += (observed - expected) ** 2 / expected

    min_dim = min(k, r) - 1
    if min_dim <= 0 or n <= 0:
        return 0.0

    v = math.sqrt(chi2 / (n * min_dim))
    return round(min(v, 1.0), 4)


def _eta_squared(outcomes: list[str], values: list[float]) -> float:
    """Eta² — proportion of variance in a continuous variable explained by outcome.

    One-way ANOVA approach: eta² = SS_between / SS_total.
    Ranges 0 (no association) to 1 (outcome perfectly predicts value).
    """
    n = len(values)
    if n < 2 or len(set(outcomes)) < 2:
        return 0.0

    overall_mean = sum(values) / n

    # Group by outcome
    groups: dict[str, list[float]] = defaultdict(list)
    for o, v in zip(outcomes, values):
        groups[o].append(v)

    ss_between = sum(
        len(g) * ((sum(g) / len(g)) - overall_mean) ** 2
        for g in groups.values() if g
    )
    ss_total = sum((v - overall_mean) ** 2 for v in values)

    if ss_total == 0.0:
        return 0.0

    return round(min(ss_between / ss_total, 1.0), 4)


# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class DriverEffect:
    """Effect size of one attribute on decision outcome.

    Attributes:
        attribute:    Name of the PopulationResponse attribute tested.
        effect_size:  Cramér's V or Eta² value (0-1).
        method:       "cramers_v" | "eta_squared"
        significant:  True if effect_size >= 0.10.
        interpretation: "negligible" | "small" | "medium" | "strong"
    """
    attribute: str
    effect_size: float
    method: Literal["cramers_v", "eta_squared"]
    significant: bool
    interpretation: str


@dataclass
class DriverAnalysisResult:
    """Key driver analysis for a population run.

    Attributes:
        top_drivers:      Significant effects sorted by effect size descending.
        all_effects:      All attributes tested (including non-significant).
        n_significant:    Count of significant effects.
        n_tested:         Total attributes tested.
        directional_only: True if N < 30 (results are directional, not reliable).
        n_personas:       Population size used for analysis.
    """
    top_drivers: list[DriverEffect]
    all_effects: list[DriverEffect]
    n_significant: int
    n_tested: int
    directional_only: bool
    n_personas: int


# ── Public API ────────────────────────────────────────────────────────────────

def analyse_drivers(
    responses: list[PopulationResponse],
    scenario: Scenario,
) -> DriverAnalysisResult:
    """Compute effect sizes for all persona attributes against decision outcome.

    Categorical attributes are tested with Cramér's V.
    Continuous attributes are tested with Eta².
    Only effects ≥ 0.10 are marked significant.

    Args:
        responses: All PopulationResponse objects from a population run.
        scenario:  The Scenario that was simulated.

    Returns:
        DriverAnalysisResult ranked by effect size.
    """
    n = len(responses)
    if n == 0:
        return DriverAnalysisResult(
            top_drivers=[], all_effects=[], n_significant=0,
            n_tested=0, directional_only=True, n_personas=0,
        )

    # Map each response to a canonical outcome label
    if scenario.is_choice_scenario():
        outcomes = [
            _option_label(r.decision, scenario.options)
            for r in responses
        ]
    else:
        outcomes = [_valence_label(r.emotional_valence) for r in responses]

    # Define which attributes to test and how
    categorical_attrs = {
        "risk_appetite":          [r.risk_appetite          for r in responses],
        "trust_anchor":           [r.trust_anchor           for r in responses],
        "decision_style":         [r.decision_style         for r in responses],
        "price_sensitivity":      [r.price_sensitivity_band for r in responses],
        "switching_propensity":   [r.switching_propensity_band for r in responses],
        "primary_value_orientation": [r.primary_value_orientation for r in responses],
    }

    continuous_attrs = {
        "confidence":             [r.confidence             for r in responses],
        "emotional_valence":      [r.emotional_valence      for r in responses],
        "consistency_score":      [float(r.consistency_score) for r in responses],
        "openness_score":         [r.domain_signals.openness_score for r in responses],
    }

    all_effects: list[DriverEffect] = []

    for attr, values in categorical_attrs.items():
        v = _cramers_v(outcomes, values)
        all_effects.append(DriverEffect(
            attribute=attr,
            effect_size=v,
            method="cramers_v",
            significant=v >= _SIGNIFICANT_THRESHOLD,
            interpretation=_effect_label(v),
        ))

    for attr, values in continuous_attrs.items():
        v = _eta_squared(outcomes, values)
        all_effects.append(DriverEffect(
            attribute=attr,
            effect_size=v,
            method="eta_squared",
            significant=v >= _SIGNIFICANT_THRESHOLD,
            interpretation=_effect_label(v),
        ))

    # Sort by effect size descending
    all_effects.sort(key=lambda e: e.effect_size, reverse=True)
    top_drivers = [e for e in all_effects if e.significant]

    return DriverAnalysisResult(
        top_drivers=top_drivers,
        all_effects=all_effects,
        n_significant=len(top_drivers),
        n_tested=len(all_effects),
        directional_only=n < _DIRECTIONAL_N_WARNING,
        n_personas=n,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _option_label(decision: str, options: list[str]) -> str:
    """Return a canonical label for this decision."""
    idx = _map_to_option(decision, options)
    if idx is not None:
        return f"opt_{idx}"
    return "unclassified"


def _valence_label(valence: float) -> str:
    if valence > 0.2:
        return "positive"
    if valence < -0.2:
        return "negative"
    return "neutral"
