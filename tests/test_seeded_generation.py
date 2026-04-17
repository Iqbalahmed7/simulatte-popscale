"""Seeded Generation Tests — Phase 2 (no live API calls).

Tests:
    1. seed_calibrator — distribute_seeds() distribution logic
    2. seed_calibrator — SeedSegment.variant_count_for_seed()
    3. seed_calibrator — exact total constraint
    4. seed_calibrator — edge cases
    5. seeded_calibrated_generator — module imports and signature
    6. study_runner — StudyConfig new fields
    7. study_runner — estimate_study_cost() seeded mode
    8. NiobeStudyRequest — seeded fields + validation
    9. NiobeStudyRequest — generation_cost_estimate()
    10. Niobe runner — StudyConfig assembled with seeded fields

Run all (no live API calls):
    python3 -m pytest tests/test_seeded_generation.py -v
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

_POPSCALE_ROOT = Path(__file__).parents[1]
_PG_ROOT       = _POPSCALE_ROOT.parent / "Persona Generator"
_NIOBE_ROOT    = _POPSCALE_ROOT.parent / "Niobe"
if str(_POPSCALE_ROOT) not in sys.path:
    sys.path.insert(0, str(_POPSCALE_ROOT))
if str(_PG_ROOT) not in sys.path:
    sys.path.insert(1, str(_PG_ROOT))
if str(_NIOBE_ROOT) not in sys.path:
    sys.path.insert(2, str(_NIOBE_ROOT))

import pytest

from popscale.calibration.calibrator import PersonaSegment, calibrate
from popscale.calibration.population_spec import PopulationSpec
from popscale.generation.seed_calibrator import SeedSegment, distribute_seeds, _correct_total
from popscale.generation.seeded_calibrated_generator import (
    run_seeded_generation,
    run_seeded_generation_sync,
)
from popscale.study.study_runner import StudyConfig, estimate_study_cost


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_spec(n: int = 1000, religion: bool = False) -> PopulationSpec:
    return PopulationSpec(
        state="west_bengal",
        n_personas=n,
        domain="policy",
        business_problem="Seeded generation test.",
        stratify_by_religion=religion,
    )


def _manual_segments(counts: list[int], labels: list[str]) -> list[PersonaSegment]:
    """Build minimal PersonaSegment list from explicit counts."""
    total = sum(counts)
    segments = []
    for count, label in zip(counts, labels):
        segments.append(PersonaSegment(
            count=count,
            anchor_overrides={},
            label=label,
            proportion=count / total,
        ))
    return segments


# ─────────────────────────────────────────────────────────────────────────────
# 1. distribute_seeds() — basic distribution
# ─────────────────────────────────────────────────────────────────────────────

class TestDistributeSeeds:

    def test_total_seeds_equals_seed_count(self):
        segments = _manual_segments([480, 280, 240], ["hindu", "muslim", "other"])
        seed_segs = distribute_seeds(segments, seed_count=20)
        assert sum(ss.seed_count for ss in seed_segs) == 20

    def test_total_personas_matches_segments(self):
        segments = _manual_segments([480, 280, 240], ["hindu", "muslim", "other"])
        seed_segs = distribute_seeds(segments, seed_count=20)
        for ss in seed_segs:
            assert ss.seed_count + ss.variant_count == ss.segment.count

    def test_each_segment_has_at_least_one_seed(self):
        segments = _manual_segments([800, 150, 50], ["A", "B", "C"])
        seed_segs = distribute_seeds(segments, seed_count=10)
        for ss in seed_segs:
            assert ss.seed_count >= 1

    def test_proportional_distribution(self):
        # Equal segments → roughly equal seeds
        segments = _manual_segments([500, 500], ["A", "B"])
        seed_segs = distribute_seeds(segments, seed_count=100)
        # Each gets ~50 seeds (±1 for rounding)
        for ss in seed_segs:
            assert 49 <= ss.seed_count <= 51

    def test_large_seed_count(self):
        segments = _manual_segments([600, 400], ["A", "B"])
        seed_segs = distribute_seeds(segments, seed_count=500)
        assert sum(ss.seed_count for ss in seed_segs) == 500

    def test_seed_count_equals_n_personas_minus_1(self):
        # Edge: 1 variant total
        segments = _manual_segments([100], ["only"])
        seed_segs = distribute_seeds(segments, seed_count=99)
        assert sum(ss.seed_count for ss in seed_segs) == 99
        assert sum(ss.variant_count for ss in seed_segs) == 1

    def test_error_if_seed_count_less_than_segments(self):
        segments = _manual_segments([300, 400, 300], ["A", "B", "C"])
        with pytest.raises(ValueError, match="seed_count.*must be.*segments"):
            distribute_seeds(segments, seed_count=2)

    def test_error_if_seed_count_exceeds_n_personas(self):
        segments = _manual_segments([100, 200], ["A", "B"])
        with pytest.raises(ValueError, match="cannot exceed n_personas"):
            distribute_seeds(segments, seed_count=400)

    def test_error_if_segments_empty(self):
        with pytest.raises(ValueError, match="non-empty"):
            distribute_seeds([], seed_count=10)


# ─────────────────────────────────────────────────────────────────────────────
# 2. SeedSegment.variant_count_for_seed()
# ─────────────────────────────────────────────────────────────────────────────

class TestSeedSegmentVariantCount:

    def _make_seed_segment(
        self, seed_count: int, variant_count: int
    ) -> SeedSegment:
        seg = PersonaSegment(
            count=seed_count + variant_count,
            anchor_overrides={},
            label="test",
            proportion=0.5,
        )
        vps = variant_count // seed_count if seed_count else 0
        extra = variant_count % seed_count if seed_count else 0
        return SeedSegment(
            segment=seg,
            seed_count=seed_count,
            variant_count=variant_count,
            variants_per_seed=vps,
            extra_seeds=extra,
            label="test",
            proportion=0.5,
        )

    def test_seeds_with_extra_get_one_more(self):
        # 3 seeds, 10 variants: 3,3,4 (floor=3, extra=1)
        ss = self._make_seed_segment(seed_count=3, variant_count=10)
        assert ss.variant_count_for_seed(0) == 4  # extra seed
        assert ss.variant_count_for_seed(1) == 3
        assert ss.variant_count_for_seed(2) == 3

    def test_even_split(self):
        ss = self._make_seed_segment(seed_count=5, variant_count=50)
        for i in range(5):
            assert ss.variant_count_for_seed(i) == 10

    def test_total_variants_sums_correctly(self):
        ss = self._make_seed_segment(seed_count=7, variant_count=100)
        total = sum(ss.variant_count_for_seed(i) for i in range(ss.seed_count))
        assert total == 100

    def test_no_variants_returns_zero(self):
        ss = self._make_seed_segment(seed_count=10, variant_count=0)
        for i in range(10):
            assert ss.variant_count_for_seed(i) == 0

    def test_total_count_property(self):
        ss = self._make_seed_segment(seed_count=5, variant_count=45)
        assert ss.total_count == 50


# ─────────────────────────────────────────────────────────────────────────────
# 3. distribute_seeds() — exact total constraint
# ─────────────────────────────────────────────────────────────────────────────

class TestDistributeSeedsExactTotal:

    def test_sum_always_equals_seed_count(self):
        """Test many combinations to ensure sum constraint is always met."""
        test_cases = [
            ([500, 300, 200], 10),
            ([333, 333, 334], 15),
            ([100, 900], 7),
            ([250, 250, 250, 250], 100),
            ([800, 150, 50], 50),
            ([400, 300, 200, 100], 200),
        ]
        for counts, seed_count in test_cases:
            segments = _manual_segments(counts, [str(i) for i in range(len(counts))])
            seed_segs = distribute_seeds(segments, seed_count=seed_count)
            total = sum(ss.seed_count for ss in seed_segs)
            assert total == seed_count, (
                f"counts={counts} seed_count={seed_count}: got {total}"
            )

    def test_seeds_plus_variants_equals_segment_count(self):
        """Every segment: seeds + variants = segment.count."""
        segments = _manual_segments([480, 280, 240], ["hindu", "muslim", "other"])
        seed_segs = distribute_seeds(segments, seed_count=40)
        for ss in seed_segs:
            assert ss.seed_count + ss.variant_count == ss.segment.count

    def test_with_real_calibrate_output(self):
        spec = _make_spec(n=1000, religion=True)
        segments = calibrate(spec)
        seed_segs = distribute_seeds(segments, seed_count=50)
        assert sum(ss.seed_count for ss in seed_segs) == 50


# ─────────────────────────────────────────────────────────────────────────────
# 4. seed_calibrator — edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestDistributeSeedsEdgeCases:

    def test_single_segment(self):
        segments = _manual_segments([1000], ["all"])
        seed_segs = distribute_seeds(segments, seed_count=100)
        assert len(seed_segs) == 1
        assert seed_segs[0].seed_count == 100
        assert seed_segs[0].variant_count == 900

    def test_minimum_one_seed_per_segment(self):
        # Very skewed: 99% in one segment, 1% in another
        segments = _manual_segments([990, 10], ["big", "small"])
        seed_segs = distribute_seeds(segments, seed_count=5)
        for ss in seed_segs:
            assert ss.seed_count >= 1

    def test_extra_seeds_within_seed_count(self):
        segments = _manual_segments([700, 300], ["A", "B"])
        seed_segs = distribute_seeds(segments, seed_count=20)
        for ss in seed_segs:
            assert ss.extra_seeds < ss.seed_count

    def test_correct_total_helper_increments(self):
        segs = _manual_segments([500, 500], ["A", "B"])
        raw = [9, 9]
        corrected = _correct_total(raw, 20, segs)
        assert sum(corrected) == 20

    def test_correct_total_helper_decrements(self):
        segs = _manual_segments([500, 500], ["A", "B"])
        raw = [11, 11]
        corrected = _correct_total(raw, 20, segs)
        assert sum(corrected) == 20


# ─────────────────────────────────────────────────────────────────────────────
# 5. seeded_calibrated_generator — module imports and signature
# ─────────────────────────────────────────────────────────────────────────────

class TestSeededGeneratorInterface:

    def test_run_seeded_generation_is_coroutine(self):
        import asyncio
        assert asyncio.iscoroutinefunction(run_seeded_generation)

    def test_run_seeded_generation_sync_exists(self):
        assert callable(run_seeded_generation_sync)

    def test_raises_on_seed_count_ge_n_personas(self):
        spec = _make_spec(n=100)
        with pytest.raises(ValueError, match="seed_count.*must be.*n_personas"):
            import asyncio
            asyncio.run(run_seeded_generation(spec, seed_count=100))

    def test_raises_on_seed_count_equal_n_personas(self):
        spec = _make_spec(n=100)
        with pytest.raises(ValueError, match="seed_count.*must be.*n_personas"):
            import asyncio
            asyncio.run(run_seeded_generation(spec, seed_count=100))


# ─────────────────────────────────────────────────────────────────────────────
# 6. StudyConfig — new seeded generation fields
# ─────────────────────────────────────────────────────────────────────────────

class TestStudyConfigSeededFields:

    def _make_minimal_config(self) -> StudyConfig:
        from popscale.scenario.model import Scenario, SimulationDomain
        spec = _make_spec(n=100)
        scenario = Scenario(
            question="Will you support this policy?",
            context="This is a test scenario for unit tests.",
            options=["A", "B"],
            domain=SimulationDomain.POLICY,
        )
        return StudyConfig(spec=spec, scenario=scenario)

    def test_use_seeded_generation_defaults_false(self):
        config = self._make_minimal_config()
        assert config.use_seeded_generation is False

    def test_seed_count_defaults_200(self):
        config = self._make_minimal_config()
        assert config.seed_count == 200

    def test_seed_tier_defaults_deep(self):
        config = self._make_minimal_config()
        assert config.seed_tier == "deep"

    def test_can_enable_seeded_generation(self):
        config = self._make_minimal_config()
        config.use_seeded_generation = True
        config.seed_count = 50
        assert config.use_seeded_generation is True
        assert config.seed_count == 50


# ─────────────────────────────────────────────────────────────────────────────
# 7. estimate_study_cost() — seeded mode
# ─────────────────────────────────────────────────────────────────────────────

class TestEstimateStudyCostSeeded:

    def _make_config(self, n: int, seeded: bool, seeds: int = 200) -> StudyConfig:
        from popscale.scenario.model import Scenario, SimulationDomain
        spec = _make_spec(n=n)
        scenario = Scenario(
            question="Will you support this policy?",
            context="This is a test scenario for unit tests.",
            options=["A", "B"],
            domain=SimulationDomain.POLICY,
        )
        return StudyConfig(
            spec=spec,
            scenario=scenario,
            use_seeded_generation=seeded,
            seed_count=seeds,
        )

    def test_seeded_cheaper_than_standard_for_large_n(self):
        standard = estimate_study_cost(self._make_config(10000, seeded=False))
        seeded   = estimate_study_cost(self._make_config(10000, seeded=True, seeds=200))
        assert seeded < standard

    def test_seeded_cost_formula(self):
        config = self._make_config(10000, seeded=True, seeds=200)
        cost = estimate_study_cost(config)
        # seeds: 200 × 0.25 = $50, variants: 9800 × 0.004 = $39.20, sim: 10000 × 0.04 = $400
        expected = 200 * 0.25 + 9800 * 0.004 + 10000 * 0.04
        assert abs(cost - expected) < 0.01

    def test_standard_cost_unchanged(self):
        config = self._make_config(1000, seeded=False)
        cost = estimate_study_cost(config)
        # volume gen: 0.06, volume sim: 0.04 → 0.10 × 1000 = $100
        expected = 1000 * (0.06 + 0.04)
        assert abs(cost - expected) < 0.01

    def test_seeded_savings_above_90pct_for_10k(self):
        standard = estimate_study_cost(self._make_config(10000, seeded=False))
        seeded   = estimate_study_cost(self._make_config(10000, seeded=True, seeds=200))
        savings_pct = (1 - seeded / standard) * 100
        # Generation savings are ~97%, but simulation costs the same, so overall
        # savings depend on sim:gen ratio. For large populations, expect >50%.
        # (10k × $0.10 standard gen vs 200 × $0.25 + 9800 × $0.004 seeded gen)
        assert savings_pct > 50


# ─────────────────────────────────────────────────────────────────────────────
# 8. NiobeStudyRequest — seeded fields + validation
# ─────────────────────────────────────────────────────────────────────────────

class TestNiobeStudyRequestSeeded:

    def _make_request(self, **kwargs) -> "NiobeStudyRequest":
        from niobe.study_request import NiobeStudyRequest
        defaults = dict(
            study_name="Test Study",
            state="west_bengal",
            n_personas=1000,
            domain="policy",
            research_question="What is the research question?",
            scenario_question="Will you vote for the incumbent?",
            scenario_context="Election is coming up next month in the state.",
        )
        defaults.update(kwargs)
        return NiobeStudyRequest(**defaults)

    def test_defaults_use_seeded_generation_false(self):
        req = self._make_request()
        assert req.use_seeded_generation is False

    def test_defaults_seed_count_200(self):
        req = self._make_request()
        assert req.seed_count == 200

    def test_defaults_seed_tier_deep(self):
        req = self._make_request()
        assert req.seed_tier == "deep"

    def test_can_enable_seeded_generation(self):
        req = self._make_request(use_seeded_generation=True, seed_count=100)
        assert req.use_seeded_generation is True
        assert req.seed_count == 100

    def test_raises_if_seed_count_gt_n_personas(self):
        from niobe.study_request import NiobeStudyRequest
        with pytest.raises(ValueError, match="seed_count.*must be.*n_personas"):
            self._make_request(use_seeded_generation=True, seed_count=1001, n_personas=1000)

    def test_raises_if_seed_count_zero(self):
        from niobe.study_request import NiobeStudyRequest
        with pytest.raises(ValueError, match="seed_count must be"):
            self._make_request(use_seeded_generation=True, seed_count=0)

    def test_raises_on_invalid_seed_tier(self):
        from niobe.study_request import NiobeStudyRequest
        with pytest.raises(ValueError, match="seed_tier must be"):
            self._make_request(use_seeded_generation=True, seed_tier="ultra")

    def test_summary_includes_seeded_flag(self):
        req = self._make_request(use_seeded_generation=True, seed_count=150)
        assert "seeded=true" in req.summary()

    def test_summary_no_seeded_flag_when_disabled(self):
        req = self._make_request()
        assert "seeded" not in req.summary()


# ─────────────────────────────────────────────────────────────────────────────
# 9. NiobeStudyRequest.generation_cost_estimate()
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerationCostEstimate:

    def _make_request(self, **kwargs):
        from niobe.study_request import NiobeStudyRequest
        defaults = dict(
            study_name="Test Study", state="west_bengal", n_personas=10000,
            domain="policy", research_question="What is the research question?",
            scenario_question="Will you vote for the incumbent?",
            scenario_context="Election is coming up next month in the state.",
        )
        defaults.update(kwargs)
        return NiobeStudyRequest(**defaults)

    def test_standard_mode_returns_mode_standard(self):
        req = self._make_request()
        est = req.generation_cost_estimate()
        assert est["mode"] == "standard"

    def test_seeded_mode_returns_mode_seeded(self):
        req = self._make_request(use_seeded_generation=True)
        est = req.generation_cost_estimate()
        assert est["mode"] == "seeded"

    def test_seeded_total_less_than_standard(self):
        req = self._make_request(use_seeded_generation=True, seed_count=200)
        est = req.generation_cost_estimate()
        assert est["total_cost"] < est["standard_cost"]

    def test_seeded_savings_pct_positive(self):
        req = self._make_request(use_seeded_generation=True, seed_count=200)
        est = req.generation_cost_estimate()
        assert est["savings_pct"] > 0

    def test_standard_savings_pct_zero(self):
        req = self._make_request()
        est = req.generation_cost_estimate()
        assert est["savings_pct"] == 0.0

    def test_seeded_formula(self):
        req = self._make_request(use_seeded_generation=True, seed_count=200, n_personas=10000)
        est = req.generation_cost_estimate()
        expected_seed = 200 * 0.30
        expected_variant = 9800 * 0.004
        expected_total = expected_seed + expected_variant
        assert abs(est["seed_cost"] - expected_seed) < 0.01
        assert abs(est["variant_cost"] - expected_variant) < 0.01
        assert abs(est["total_cost"] - expected_total) < 0.01


# ─────────────────────────────────────────────────────────────────────────────
# 10. Niobe runner — StudyConfig assembled with seeded fields
# ─────────────────────────────────────────────────────────────────────────────

class TestNiobeRunnerSeededWiring:

    def _make_request(self, **kwargs):
        from niobe.study_request import NiobeStudyRequest
        defaults = dict(
            study_name="Test Study", state="west_bengal", n_personas=1000,
            domain="policy", research_question="What is the research question?",
            scenario_question="Will you vote for the incumbent?",
            scenario_context="Election is coming up next month in the state.",
        )
        defaults.update(kwargs)
        return NiobeStudyRequest(**defaults)

    def _build_config(self, request) -> StudyConfig:
        from niobe.runner import _build_study_config
        return _build_study_config(request)

    def test_seeded_false_passes_through(self):
        req = self._make_request()
        config = self._build_config(req)
        assert config.use_seeded_generation is False

    def test_seeded_true_passes_through(self):
        req = self._make_request(use_seeded_generation=True, seed_count=100)
        config = self._build_config(req)
        assert config.use_seeded_generation is True
        assert config.seed_count == 100

    def test_seed_tier_passes_through(self):
        req = self._make_request(use_seeded_generation=True, seed_tier="signal")
        config = self._build_config(req)
        assert config.seed_tier == "signal"

    def test_default_seed_count_passes_through(self):
        req = self._make_request(use_seeded_generation=True)
        config = self._build_config(req)
        assert config.seed_count == 200
