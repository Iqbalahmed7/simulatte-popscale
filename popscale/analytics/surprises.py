"""surprises — detect population findings that contradict the behavioral prior.

A surprise is a finding where the actual decision distribution deviates materially
from what the population's behavioral profile would predict.

Prior estimation logic (mirrors domain/framing._estimate_prior but works from
PopulationResponse fields — no PersonaRecord required at this stage):

    prior_score = risk_map[risk_appetite]      # primary driver
                + trust_modifier[trust_anchor]  # secondary
    → "high" (score ≥ 0.60), "medium", or "low" (score ≤ 0.35)

Prior-to-option mapping for choice scenarios:
    high   → option index 0 (most forward/progressive option)
    medium → option index middle
    low    → option index last (most conservative option)

Surprise threshold: |actual % - expected %| ≥ 15 percentage points.

Severity scale:
    notable         — 15–24pp deviation
    striking        — 25–39pp deviation
    counterintuitive — ≥ 40pp deviation

Design principle: surprises are a qualitative finding layer, not a statistical
hypothesis test. They flag things worth investigating, not formal inferences.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..schema.population_response import PopulationResponse
from ..scenario.model import Scenario
from .distributions import DistributionResult, OptionResult
from .segmentation import SegmentationResult, _map_to_option


# ── Thresholds ────────────────────────────────────────────────────────────────

_SURPRISE_THRESHOLD_PP = 15.0   # minimum pp deviation to flag

_SEVERITY_MAP = [
    (40.0, "counterintuitive"),
    (25.0, "striking"),
    (15.0, "notable"),
]


def _severity(deviation_pp: float) -> str:
    for threshold, label in _SEVERITY_MAP:
        if deviation_pp >= threshold:
            return label
    return "notable"


# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class SurpriseFinding:
    """A single surprise finding.

    Attributes:
        finding_type:  Category of surprise.
        description:   Human-readable explanation.
        actual_pct:    Observed percentage (0-100).
        expected_pct:  Prior-predicted percentage (0-100).
        deviation_pp:  |actual - expected| in percentage points.
        severity:      "notable" | "striking" | "counterintuitive"
    """
    finding_type: str
    description: str
    actual_pct: float
    expected_pct: float
    deviation_pp: float
    severity: str


@dataclass
class SurpriseResult:
    """Surprise analysis for a population run.

    Attributes:
        findings:       All surprise findings, sorted by severity.
        has_surprises:  True if any findings exist.
        prior_distribution: Expected % per option from behavioral prior.
        actual_distribution: Observed % per option.
    """
    findings: list[SurpriseFinding]
    has_surprises: bool
    prior_distribution: dict[str, float]   # option label → expected %
    actual_distribution: dict[str, float]  # option label → actual %


# ── Prior estimation ──────────────────────────────────────────────────────────

def _response_prior(response: PopulationResponse) -> str:
    """Estimate behavioral prior from PopulationResponse fields.

    Mirrors domain/framing._estimate_prior() but uses response fields
    instead of PersonaRecord (analytics layer has no access to PersonaRecord).
    """
    risk_map = {"low": 0.2, "medium": 0.5, "high": 0.8}
    risk_score = risk_map.get(response.risk_appetite, 0.5)

    trust_modifier = {
        "authority": +0.05,
        "self":      +0.00,
        "peer":      +0.00,
        "family":    -0.05,
    }.get(response.trust_anchor, 0.0)

    score = min(1.0, max(0.0, risk_score + trust_modifier))

    if score >= 0.60:
        return "high"
    if score <= 0.35:
        return "low"
    return "medium"


def _prior_to_option_index(prior: str, n_options: int) -> int:
    """Map a behavioral prior (high/medium/low) to a scenario option index.

    Convention:
        high   → option 0 (most forward/progressive/open)
        medium → option middle
        low    → option last (most conservative/resistant)
    """
    if prior == "high":
        return 0
    if prior == "low":
        return n_options - 1
    return n_options // 2  # middle


# ── Public API ────────────────────────────────────────────────────────────────

def detect_surprises(
    responses: list[PopulationResponse],
    scenario: Scenario,
    segmentation: SegmentationResult,
    distributions: DistributionResult,
) -> SurpriseResult:
    """Detect findings where actual decisions contradict the behavioral prior.

    Args:
        responses:     All PopulationResponse objects from a population run.
        scenario:      The Scenario that was simulated.
        segmentation:  Pre-computed segmentation result.
        distributions: Pre-computed distribution result.

    Returns:
        SurpriseResult with flagged findings sorted by severity.
    """
    if not responses or not distributions.is_choice_scenario:
        return SurpriseResult(
            findings=[],
            has_surprises=False,
            prior_distribution={},
            actual_distribution={},
        )

    n = len(responses)
    n_options = len(scenario.options)

    # ── Compute prior distribution ────────────────────────────────────────
    # Count how many personas' priors point to each option
    prior_counts: dict[int, int] = {i: 0 for i in range(n_options)}
    for r in responses:
        prior = _response_prior(r)
        idx = _prior_to_option_index(prior, n_options)
        prior_counts[idx] += 1

    prior_pct: dict[str, float] = {
        _option_key(i, scenario.options): round(prior_counts[i] / n * 100, 1)
        for i in range(n_options)
    }

    # ── Compute actual distribution ───────────────────────────────────────
    actual_pct: dict[str, float] = {}
    option_results_by_idx: dict[int, OptionResult] = {
        o.option_index: o for o in distributions.options
    }
    for i in range(n_options):
        opt_res = option_results_by_idx.get(i)
        pct = round(opt_res.proportion * 100, 1) if opt_res else 0.0
        actual_pct[_option_key(i, scenario.options)] = pct

    # ── Detect surprises ──────────────────────────────────────────────────
    findings: list[SurpriseFinding] = []

    for i in range(n_options):
        key = _option_key(i, scenario.options)
        actual = actual_pct.get(key, 0.0)
        expected = prior_pct.get(key, 0.0)
        deviation = abs(actual - expected)

        if deviation < _SURPRISE_THRESHOLD_PP:
            continue

        opt_label = scenario.options[i][:50]

        if actual > expected:
            finding_type = "larger_than_expected"
            description = (
                f'"{opt_label}" attracted {actual:.0f}% of respondents, '
                f'{deviation:.0f}pp more than the behavioral prior predicted ({expected:.0f}%). '
                f'This option resonated beyond its expected audience.'
            )
        else:
            finding_type = "smaller_than_expected"
            description = (
                f'"{opt_label}" attracted only {actual:.0f}% of respondents, '
                f'{deviation:.0f}pp below the behavioral prior ({expected:.0f}%). '
                f'Expected adopters showed more resistance than their profile suggested.'
            )

        findings.append(SurpriseFinding(
            finding_type=finding_type,
            description=description,
            actual_pct=actual,
            expected_pct=expected,
            deviation_pp=round(deviation, 1),
            severity=_severity(deviation),
        ))

    # ── Unexpected winner check ───────────────────────────────────────────
    if distributions.options:
        actual_winner_idx = max(
            range(n_options),
            key=lambda i: option_results_by_idx.get(i, _null_option()).proportion,
        )
        prior_winner_idx = max(prior_counts, key=prior_counts.__getitem__)

        if actual_winner_idx != prior_winner_idx and n_options > 1:
            actual_opt = scenario.options[actual_winner_idx][:50]
            prior_opt  = scenario.options[prior_winner_idx][:50]
            actual_pct_winner = round(
                option_results_by_idx.get(actual_winner_idx, _null_option()).proportion * 100, 1
            )
            prior_pct_winner = round(prior_pct.get(
                _option_key(prior_winner_idx, scenario.options), 0.0
            ), 1)
            deviation = abs(actual_pct_winner - prior_pct_winner)

            # Only flag if there's also a material pp deviation
            if deviation >= _SURPRISE_THRESHOLD_PP:
                findings.append(SurpriseFinding(
                    finding_type="unexpected_winner",
                    description=(
                        f'The prior predicted "{prior_opt}" would win '
                        f'({prior_pct_winner:.0f}% expected), but '
                        f'"{actual_opt}" emerged as the actual leader '
                        f'({actual_pct_winner:.0f}%). '
                        f'The population responded differently than their profile suggested.'
                    ),
                    actual_pct=actual_pct_winner,
                    expected_pct=prior_pct_winner,
                    deviation_pp=round(deviation, 1),
                    severity=_severity(deviation),
                ))

    # Sort by deviation descending (most surprising first)
    findings.sort(key=lambda f: f.deviation_pp, reverse=True)

    return SurpriseResult(
        findings=findings,
        has_surprises=bool(findings),
        prior_distribution=prior_pct,
        actual_distribution=actual_pct,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _option_key(idx: int, options: list[str]) -> str:
    label = options[idx][:30] if idx < len(options) else f"option_{idx}"
    return f"opt{idx}:{label}"


class _null_option:
    """Placeholder when an option has no results."""
    proportion = 0.0
    count = 0
    avg_confidence = 0.0
    avg_valence = 0.0
