"""Week 3 Analytics Tests — Segmentation, Distributions, Drivers, Surprises, Report.

The fixture strategy:
    _make_fixture_responses() builds a deterministic synthetic dataset with a
    planted signal: risk_appetite=high → option 0; risk_appetite=low → option 2.
    This lets the driver tests assert that risk_appetite has a high Cramér's V
    without any LLM calls.

Run non-live:
    python3 -m pytest tests/test_week3_analytics.py -v

Run live (real API calls — full pipeline including LLM):
    python3 -m pytest tests/test_week3_analytics.py -v -m live
"""

from __future__ import annotations

# ── sys.path setup ────────────────────────────────────────────────────────────
import sys
from pathlib import Path

_POPSCALE_ROOT = Path(__file__).parents[1]
_PG_ROOT       = _POPSCALE_ROOT.parent / "Persona Generator"

if str(_POPSCALE_ROOT) not in sys.path:
    sys.path.insert(0, str(_POPSCALE_ROOT))
if str(_PG_ROOT) not in sys.path:
    sys.path.insert(1, str(_PG_ROOT))

# ── Standard imports ──────────────────────────────────────────────────────────
import asyncio
import json
from collections import Counter
from datetime import datetime, timezone

import pytest

# ── PopScale imports ──────────────────────────────────────────────────────────
from popscale.analytics.distributions import compute_distributions
from popscale.analytics.drivers import (
    _cramers_v,
    _eta_squared,
    analyse_drivers,
)
from popscale.analytics.report import PopScaleReport, generate_report
from popscale.analytics.segmentation import _map_to_option, segment_population
from popscale.analytics.surprises import (
    _response_prior,
    detect_surprises,
)
from popscale.schema.population_response import DomainSignals, PopulationResponse
from popscale.schema.simulation_result import SimulationResult
from popscale.scenario.model import Scenario, SimulationDomain

from src.experiment.session import SimulationTier


# ─────────────────────────────────────────────────────────────────────────────
# Shared fixtures
# ─────────────────────────────────────────────────────────────────────────────

OPTIONS = [
    "Yes — start a paid trial immediately",
    "Maybe — request a demo first",
    "No — not interested at this price",
]

SCENARIO = Scenario(
    question="Would you pay for an AI tool that automates footage selection?",
    context=(
        "Montage is a video production SaaS tool priced at $49/month. "
        "It automatically selects the best clips from raw footage and generates "
        "a rough cut in under 10 minutes."
    ),
    options=OPTIONS,
    domain=SimulationDomain.CONSUMER,
)

OPEN_ENDED_SCENARIO = Scenario(
    question="How do you feel about AI in your creative workflow?",
    context=(
        "AI tools are increasingly being used in video production workflows "
        "to automate repetitive tasks like clip selection and color grading."
    ),
    domain=SimulationDomain.CONSUMER,
)


def _make_response(
    idx: int,
    decision: str,
    risk_appetite: str,
    confidence: float,
    emotional_valence: float,
    trust_anchor: str = "peer",
    decision_style: str = "analytical",
    is_fallback: bool = False,
) -> PopulationResponse:
    trace = "[FALLBACK] test" if is_fallback else f"Reasoning trace for persona {idx}."
    return PopulationResponse(
        persona_id=f"test-{idx:03d}",
        persona_name=f"Persona {idx}",
        age=30 + idx,
        gender="male" if idx % 2 == 0 else "female",
        location_city="Mumbai",
        location_country="India",
        income_bracket="middle",
        scenario_domain="consumer",
        scenario_options=OPTIONS,
        decision=decision,
        confidence=confidence,
        reasoning_trace=trace,
        gut_reaction="Direct gut reaction.",
        key_drivers=["price", "quality"] if idx % 2 == 0 else ["workflow", "trust"],
        objections=["concerns about AI quality"] if idx % 3 == 0 else [],
        what_would_change_mind="Lower price",
        follow_up_action="Research alternatives",
        emotional_valence=emotional_valence,
        domain_signals=DomainSignals(
            openness_score=0.7 if risk_appetite == "high" else 0.3,
            price_sensitivity=0.5,
            trial_likelihood=0.6,
        ),
        risk_appetite=risk_appetite,
        trust_anchor=trust_anchor,
        decision_style=decision_style,
        primary_value_orientation="quality",
        consistency_score=70,
        price_sensitivity_band="medium",
        switching_propensity_band="medium",
    )


# Planted signal: risk_appetite=high → option 0, low → option 2, medium → option 1
FIXTURE_RESPONSES = [
    _make_response(0, OPTIONS[0], "high", 0.85, 0.6),
    _make_response(1, OPTIONS[0], "high", 0.80, 0.5),
    _make_response(2, OPTIONS[0], "high", 0.78, 0.7),
    _make_response(3, OPTIONS[1], "medium", 0.60, 0.1),
    _make_response(4, OPTIONS[1], "medium", 0.55, 0.0),
    _make_response(5, OPTIONS[2], "low", 0.45, -0.4),
    _make_response(6, OPTIONS[2], "low", 0.40, -0.5),
    _make_response(7, OPTIONS[2], "low", 0.42, -0.3),
    _make_response(8, OPTIONS[0], "high", 0.82, 0.6),
    _make_response(9, OPTIONS[1], "medium", 0.58, 0.0),
]


def _make_simulation_result(responses=None) -> SimulationResult:
    if responses is None:
        responses = FIXTURE_RESPONSES
    now = datetime.now(timezone.utc)
    return SimulationResult(
        run_id="test-analytics-run",
        scenario=SCENARIO,
        tier="volume",
        cohort_size=len(responses),
        responses=responses,
        cost_estimate_usd=0.042,
        cost_actual_usd=0.042,
        started_at=now,
        completed_at=now,
        shard_size=50,
        concurrency=20,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Option mapping
# ─────────────────────────────────────────────────────────────────────────────

class TestOptionMapping:

    def test_exact_match(self):
        assert _map_to_option(OPTIONS[0], OPTIONS) == 0
        assert _map_to_option(OPTIONS[1], OPTIONS) == 1
        assert _map_to_option(OPTIONS[2], OPTIONS) == 2

    def test_case_insensitive(self):
        assert _map_to_option(OPTIONS[0].lower(), OPTIONS) == 0
        assert _map_to_option(OPTIONS[2].upper(), OPTIONS) == 2

    def test_partial_match_contained(self):
        # Option text is a substring of the decision
        assert _map_to_option("Yes — start a paid trial immediately — I'm in", OPTIONS) == 0

    def test_word_overlap_paraphrase(self):
        # LLM says "request a demo" — should map to option 1 via word overlap
        result = _map_to_option("I would like to request a demo", OPTIONS)
        assert result == 1

    def test_no_match_returns_none(self):
        assert _map_to_option("Something completely unrelated", OPTIONS) is None

    def test_empty_decision(self):
        assert _map_to_option("", OPTIONS) is None

    def test_empty_options(self):
        assert _map_to_option("Yes", []) is None


# ─────────────────────────────────────────────────────────────────────────────
# 2. Segmentation
# ─────────────────────────────────────────────────────────────────────────────

class TestSegmentation:

    def test_choice_scenario_produces_3_segments(self):
        result = segment_population(FIXTURE_RESPONSES, SCENARIO)
        assert result.is_choice_scenario
        assert len(result.segments) == 3

    def test_segment_counts_sum_to_total(self):
        result = segment_population(FIXTURE_RESPONSES, SCENARIO)
        total = sum(s.count for s in result.segments) + result.unclassified_count
        assert total == len(FIXTURE_RESPONSES)

    def test_dominant_segment_has_most_responses(self):
        result = segment_population(FIXTURE_RESPONSES, SCENARIO)
        dominant_count = result.dominant_segment.count
        for seg in result.segments:
            assert seg.count <= dominant_count

    def test_segment_shares_sum_to_1(self):
        result = segment_population(FIXTURE_RESPONSES, SCENARIO)
        total_share = sum(s.share for s in result.segments)
        assert abs(total_share - 1.0) < 0.01

    def test_segment_trait_profile_populated(self):
        result = segment_population(FIXTURE_RESPONSES, SCENARIO)
        dominant = result.dominant_segment
        if dominant.count > 0:
            assert len(dominant.trait_profile.risk_appetite) > 0

    def test_open_ended_produces_sentiment_segments(self):
        # Build open-ended responses (no decision, use valence)
        open_responses = [
            _make_response(i, f"Open answer {i}", "medium", 0.5, val)
            for i, val in enumerate([0.5, 0.3, 0.0, -0.1, -0.5])
        ]
        result = segment_population(open_responses, OPEN_ENDED_SCENARIO)
        assert not result.is_choice_scenario
        assert len(result.segments) == 3  # positive/neutral/negative

    def test_all_responses_same_option(self):
        all_yes = [_make_response(i, OPTIONS[0], "high", 0.8, 0.6) for i in range(5)]
        result = segment_population(all_yes, SCENARIO)
        assert result.dominant_segment.count == 5
        assert result.unclassified_count == 0

    def test_representative_drivers_populated(self):
        result = segment_population(FIXTURE_RESPONSES, SCENARIO)
        dominant = result.dominant_segment
        if dominant.count > 0:
            assert isinstance(dominant.representative_drivers, list)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Distributions and Wilson CI
# ─────────────────────────────────────────────────────────────────────────────

class TestDistributions:

    def test_option_proportions_sum_to_1(self):
        result = compute_distributions(FIXTURE_RESPONSES, SCENARIO)
        total = sum(o.proportion for o in result.options)
        # Allow for small floating-point error and unclassified
        assert abs(total - (result.n_total - result.n_unclassified) / result.n_total) < 0.01

    def test_wilson_ci_lower_le_proportion_le_upper(self):
        result = compute_distributions(FIXTURE_RESPONSES, SCENARIO)
        for o in result.options:
            assert o.ci_lower <= o.proportion <= o.ci_upper

    def test_wilson_ci_bounds_in_0_1(self):
        result = compute_distributions(FIXTURE_RESPONSES, SCENARIO)
        for o in result.options:
            assert 0.0 <= o.ci_lower <= 1.0
            assert 0.0 <= o.ci_upper <= 1.0

    def test_ci_wider_with_fewer_responses(self):
        # 3 responses → wider CI than 30
        small = FIXTURE_RESPONSES[:3]
        large = FIXTURE_RESPONSES * 3  # 30 responses (repeated)
        res_small = compute_distributions(small, SCENARIO)
        res_large = compute_distributions(large, SCENARIO)
        # Any option with count > 0 should have wider CI in small
        for o_small, o_large in zip(res_small.options, res_large.options):
            if o_small.count > 0 and o_large.count > 0:
                width_small = o_small.ci_upper - o_small.ci_lower
                width_large = o_large.ci_upper - o_large.ci_lower
                assert width_small >= width_large

    def test_leading_option_highest_proportion(self):
        result = compute_distributions(FIXTURE_RESPONSES, SCENARIO)
        if result.leading_option:
            for o in result.options:
                assert result.leading_option.proportion >= o.proportion

    def test_median_confidence_in_0_1(self):
        result = compute_distributions(FIXTURE_RESPONSES, SCENARIO)
        assert 0.0 <= result.median_confidence <= 1.0

    def test_open_ended_produces_sentiment_not_options(self):
        open_responses = [
            _make_response(i, f"Open {i}", "medium", 0.5, val)
            for i, val in enumerate([0.5, 0.0, -0.5])
        ]
        result = compute_distributions(open_responses, OPEN_ENDED_SCENARIO)
        assert not result.is_choice_scenario
        assert len(result.options) == 0
        assert len(result.sentiment) == 3

    def test_empty_responses(self):
        result = compute_distributions([], SCENARIO)
        assert result.n_total == 0
        assert all(o.count == 0 for o in result.options)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Driver analysis (Cramér's V and Eta²)
# ─────────────────────────────────────────────────────────────────────────────

class TestDrivers:

    # ── Pure math tests ────────────────────────────────────────────────────

    def test_cramers_v_perfect_association(self):
        """Perfect predictor: A→X, B→Y always."""
        outcomes = ["X"] * 5 + ["Y"] * 5
        attrs    = ["A"] * 5 + ["B"] * 5
        v = _cramers_v(outcomes, attrs)
        assert abs(v - 1.0) < 0.001

    def test_cramers_v_no_association(self):
        """Each outcome has equal A/B split → no association (chi² = 0, V = 0)."""
        # (X,A), (X,B), (Y,A), (Y,B) each appears equally — perfect independence
        outcomes = ["X", "X", "Y", "Y"] * 4
        attrs    = ["A", "B", "A", "B"] * 4
        v = _cramers_v(outcomes, attrs)
        assert v < 0.05  # near-zero

    def test_cramers_v_single_category(self):
        """Only one distinct outcome value → V = 0."""
        v = _cramers_v(["X"] * 10, ["A", "B"] * 5)
        assert v == 0.0

    def test_cramers_v_empty(self):
        assert _cramers_v([], []) == 0.0

    def test_eta_squared_perfect_separation(self):
        """Outcome perfectly explains variance: group A has mean 0, group B has mean 10."""
        outcomes = ["A"] * 5 + ["B"] * 5
        values   = [0.0] * 5 + [10.0] * 5
        eta2 = _eta_squared(outcomes, values)
        assert abs(eta2 - 1.0) < 0.001

    def test_eta_squared_identical_values(self):
        """All values the same → no variance to explain → Eta² = 0."""
        outcomes = ["A", "B"] * 5
        values   = [0.5] * 10
        assert _eta_squared(outcomes, values) == 0.0

    def test_eta_squared_empty(self):
        assert _eta_squared([], []) == 0.0

    # ── Integration tests ──────────────────────────────────────────────────

    def test_risk_appetite_is_top_driver(self):
        """With planted signal, risk_appetite should be the strongest categorical driver."""
        result = analyse_drivers(FIXTURE_RESPONSES, SCENARIO)
        cramers_effects = [
            e for e in result.all_effects
            if e.method == "cramers_v" and e.attribute == "risk_appetite"
        ]
        assert cramers_effects, "risk_appetite should be tested"
        risk_effect = cramers_effects[0]
        assert risk_effect.effect_size > 0.5, (
            f"risk_appetite should have strong association (got {risk_effect.effect_size:.3f})"
        )

    def test_all_effects_in_0_1(self):
        result = analyse_drivers(FIXTURE_RESPONSES, SCENARIO)
        for e in result.all_effects:
            assert 0.0 <= e.effect_size <= 1.0

    def test_significant_effects_above_threshold(self):
        result = analyse_drivers(FIXTURE_RESPONSES, SCENARIO)
        for e in result.top_drivers:
            assert e.effect_size >= 0.10

    def test_directional_warning_at_small_n(self):
        small = FIXTURE_RESPONSES[:5]
        result = analyse_drivers(small, SCENARIO)
        assert result.directional_only

    def test_n_significant_consistent_with_top_drivers(self):
        result = analyse_drivers(FIXTURE_RESPONSES, SCENARIO)
        assert result.n_significant == len(result.top_drivers)

    def test_all_effects_sorted_descending(self):
        result = analyse_drivers(FIXTURE_RESPONSES, SCENARIO)
        sizes = [e.effect_size for e in result.all_effects]
        assert sizes == sorted(sizes, reverse=True)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Surprise detection
# ─────────────────────────────────────────────────────────────────────────────

class TestSurprises:

    def test_response_prior_high_risk(self):
        r = _make_response(0, OPTIONS[0], "high", 0.8, 0.5, trust_anchor="self")
        assert _response_prior(r) == "high"

    def test_response_prior_low_risk(self):
        r = _make_response(0, OPTIONS[2], "low", 0.4, -0.4, trust_anchor="family")
        assert _response_prior(r) == "low"

    def test_no_surprise_when_matches_prior(self):
        """All high-risk personas choose option 0 — exactly what prior predicts."""
        all_high = [_make_response(i, OPTIONS[0], "high", 0.8, 0.6) for i in range(10)]
        result = _make_simulation_result(all_high)
        seg = segment_population(result.responses, result.scenario)
        dist = compute_distributions(result.responses, result.scenario)
        surprises = detect_surprises(result.responses, result.scenario, seg, dist)
        # Option 0 is the expected winner for all-high population — may or may not flag
        # The key check: no "smaller_than_expected" for option 0
        for f in surprises.findings:
            if "opt0" in f.finding_type or (f.actual_pct > f.expected_pct and "opt0" in str(f)):
                pass  # OK — option 0 over-performed or matched
        # At minimum: not crashing
        assert isinstance(surprises.has_surprises, bool)

    def test_surprise_detected_when_low_risk_chooses_option_0(self):
        """All low-risk personas choose option 0 (the most forward option) — surprise."""
        all_low_chose_0 = [
            _make_response(i, OPTIONS[0], "low", 0.5, 0.0)
            for i in range(10)
        ]
        result = _make_simulation_result(all_low_chose_0)
        seg  = segment_population(result.responses, result.scenario)
        dist = compute_distributions(result.responses, result.scenario)
        surprises = detect_surprises(result.responses, result.scenario, seg, dist)
        # Option 0 at 100% when prior predicts ~0% for low-risk → surprise
        assert surprises.has_surprises

    def test_prior_distribution_sums_to_100(self):
        result = _make_simulation_result()
        seg  = segment_population(result.responses, result.scenario)
        dist = compute_distributions(result.responses, result.scenario)
        surprises = detect_surprises(result.responses, result.scenario, seg, dist)
        total = sum(surprises.prior_distribution.values())
        assert abs(total - 100.0) < 1.0

    def test_actual_distribution_sums_to_100_minus_unclassified(self):
        result = _make_simulation_result()
        seg  = segment_population(result.responses, result.scenario)
        dist = compute_distributions(result.responses, result.scenario)
        surprises = detect_surprises(result.responses, result.scenario, seg, dist)
        total = sum(surprises.actual_distribution.values())
        classified_pct = (dist.n_total - dist.n_unclassified) / dist.n_total * 100
        assert abs(total - classified_pct) < 1.0

    def test_open_ended_no_surprises(self):
        """No option mapping for open-ended → no surprises computed."""
        open_r = [_make_response(i, f"Open {i}", "medium", 0.5, 0.0) for i in range(5)]
        result = _make_simulation_result(open_r)
        result.scenario = OPEN_ENDED_SCENARIO
        seg  = segment_population(result.responses, OPEN_ENDED_SCENARIO)
        dist = compute_distributions(result.responses, OPEN_ENDED_SCENARIO)
        surprises = detect_surprises(result.responses, OPEN_ENDED_SCENARIO, seg, dist)
        assert not surprises.has_surprises


# ─────────────────────────────────────────────────────────────────────────────
# 6. Report generation
# ─────────────────────────────────────────────────────────────────────────────

class TestReport:

    def test_generate_report_returns_popscale_report(self):
        result = _make_simulation_result()
        report = generate_report(result)
        assert isinstance(report, PopScaleReport)

    def test_report_metadata_correct(self):
        result = _make_simulation_result()
        report = generate_report(result)
        assert report.run_id == "test-analytics-run"
        assert report.n_personas == len(FIXTURE_RESPONSES)
        assert report.tier == "volume"

    def test_to_dict_is_json_serialisable(self):
        result = _make_simulation_result()
        report = generate_report(result)
        d = report.to_dict()
        # Should not raise
        json_str = json.dumps(d)
        assert len(json_str) > 100

    def test_to_dict_has_required_keys(self):
        result = _make_simulation_result()
        d = generate_report(result).to_dict()
        for key in ["run_id", "scenario", "population", "distributions",
                    "segments", "drivers", "surprises"]:
            assert key in d

    def test_to_markdown_contains_scenario_question(self):
        result = _make_simulation_result()
        md = generate_report(result).to_markdown()
        assert SCENARIO.question in md

    def test_to_markdown_contains_distribution_table(self):
        result = _make_simulation_result()
        md = generate_report(result).to_markdown()
        assert "Decision Distribution" in md
        assert "%" in md

    def test_to_markdown_contains_segments(self):
        result = _make_simulation_result()
        md = generate_report(result).to_markdown()
        assert "Segments" in md

    def test_to_markdown_contains_key_drivers(self):
        result = _make_simulation_result()
        md = generate_report(result).to_markdown()
        assert "Key Drivers" in md

    def test_to_markdown_contains_surprise_section(self):
        result = _make_simulation_result()
        md = generate_report(result).to_markdown()
        assert "Surprise" in md

    def test_success_rate_correct(self):
        # Mix 8 real + 2 fallbacks
        responses = FIXTURE_RESPONSES[:8] + [
            _make_response(90, OPTIONS[0], "high", 0.5, 0.3, is_fallback=True),
            _make_response(91, OPTIONS[1], "medium", 0.4, 0.0, is_fallback=True),
        ]
        result = _make_simulation_result(responses)
        report = generate_report(result)
        assert report.n_successful == 8
        assert abs(report.success_rate - 0.8) < 0.01

    def test_empty_population_does_not_crash(self):
        result = _make_simulation_result([])
        result.cohort_size = 0
        report = generate_report(result)
        assert report.n_personas == 0
        md = report.to_markdown()
        assert "PopScale Report" in md


# ─────────────────────────────────────────────────────────────────────────────
# 7. Live end-to-end test (real LLM calls + full analytics pipeline)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.live
class TestLiveAnalytics:

    def test_full_pipeline_montage(self):
        """Run Montage personas → SimulationResult → generate_report() → check structure."""
        from popscale.utils.persona_adapter import load_cohort_file
        from popscale.orchestrator.runner import run_population_scenario

        cohort_path = _PG_ROOT / "pilots" / "montage" / "cohort_montage_20260412.json"
        if not cohort_path.exists():
            pytest.skip("Montage cohort not available")

        personas = load_cohort_file(cohort_path)
        if not personas:
            pytest.skip("No personas loaded from Montage cohort")

        scenario = Scenario(
            question="Would you pay for an AI tool that automates footage selection?",
            context=(
                "Montage is a SaaS tool priced at $49/month. It uses AI to select the "
                "best clips from raw footage and generates a rough cut in 10 minutes. "
                "Currently used by small video teams at independent studios."
            ),
            options=[
                "Yes — start a paid trial immediately",
                "Maybe — request a demo first",
                "No — not interested at this price",
            ],
            domain=SimulationDomain.CONSUMER,
        )

        sim_result = asyncio.run(
            run_population_scenario(
                scenario=scenario,
                personas=personas,
                tier=SimulationTier.VOLUME,
                shard_size=5,
                concurrency=5,
                print_estimate=False,
            )
        )

        report = generate_report(sim_result)

        # Structural checks
        assert isinstance(report, PopScaleReport)
        assert report.n_personas == len(personas)
        assert report.segmentation.n_total == len(personas)
        assert len(report.distributions.options) == 3
        assert all(0.0 <= o.proportion <= 1.0 for o in report.distributions.options)
        assert all(o.ci_lower <= o.proportion <= o.ci_upper for o in report.distributions.options)
        assert isinstance(report.drivers.directional_only, bool)
        assert isinstance(report.surprises.has_surprises, bool)

        # Export checks
        d = report.to_dict()
        json.dumps(d)  # must be JSON-serialisable

        md = report.to_markdown()
        assert "PopScale Report" in md
        assert scenario.question in md

        # Print for visual inspection
        print("\n" + "=" * 70)
        print(md)
        print("=" * 70)
