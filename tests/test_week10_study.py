"""Week 10 Study Runner Tests — structural/unit (no live API calls).

Tests:
    1. StudyConfig — construction, defaults, validation
    2. StudyResult — properties, summary, to_dict()
    3. run_study imports and signature
    4. StudyConfig × environment preset integration
    5. StudyConfig × EventTimeline integration
    6. StudyConfig × social settings

Run all (no live API calls):
    python3 -m pytest tests/test_week10_study.py -v
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

_POPSCALE_ROOT = Path(__file__).parents[1]
_PG_ROOT       = _POPSCALE_ROOT.parent / "Persona Generator"
if str(_POPSCALE_ROOT) not in sys.path:
    sys.path.insert(0, str(_POPSCALE_ROOT))
if str(_PG_ROOT) not in sys.path:
    sys.path.insert(1, str(_PG_ROOT))

import pytest

from popscale.study.study_runner import StudyConfig, StudyResult, run_study, run_study_sync
from popscale.scenario.model import Scenario, SimulationDomain
from popscale.calibration.population_spec import PopulationSpec
from popscale.environment import WEST_BENGAL_POLITICAL_2026, INDIA_URBAN_CONSUMER
from popscale.scenario.events import EventCategory, EventTimeline, SimulationEvent
from popscale.social.social_runner import SocialSimulationLevel


# ── Shared fixtures ───────────────────────────────────────────────────────────

def _make_scenario() -> Scenario:
    return Scenario(
        question="Will you vote for the incumbent TMC party in the upcoming election?",
        context=(
            "West Bengal state elections are due in 2026. The TMC government has been "
            "in power since 2011. Fuel prices have risen 40%. The BJP and Left-Congress "
            "alliance are mounting strong challenges across different demographics."
        ),
        options=["Yes, TMC", "BJP", "Left-Congress alliance", "Undecided / abstain"],
        domain=SimulationDomain.POLITICAL,
    )


def _make_spec(n: int = 50) -> PopulationSpec:
    return PopulationSpec(
        state="west_bengal",
        n_personas=n,
        domain="policy",
        business_problem="West Bengal electoral sentiment study.",
        stratify_by_religion=True,
    )


def _make_config(**kwargs) -> StudyConfig:
    defaults = dict(
        spec=_make_spec(),
        scenario=_make_scenario(),
        environment=WEST_BENGAL_POLITICAL_2026,
        run_id="st-test001",
    )
    defaults.update(kwargs)
    return StudyConfig(**defaults)


def _make_study_result(config: StudyConfig) -> StudyResult:
    """Build a mock StudyResult for testing properties."""
    from popscale.generation.calibrated_generator import CohortGenerationResult, SegmentGenerationResult
    from popscale.calibration.calibrator import calibrate
    from popscale.schema.simulation_result import SimulationResult, ShardRecord

    now = datetime.now(timezone.utc)
    spec = config.spec
    segments = calibrate(spec)

    # Mock cohort
    cohort = CohortGenerationResult(
        run_id="cg-test",
        spec=spec,
        segments=segments,
        segment_results=[
            SegmentGenerationResult(
                segment=segments[0],
                count_requested=50,
                count_delivered=50,
                cost_usd=0.25,
                personas=[],
            )
        ],
        personas=[],
        total_requested=50,
        total_delivered=50,
        total_cost_usd=0.25,
        started_at=now,
        completed_at=now,
    )

    # Mock simulation result
    sim = SimulationResult(
        run_id="sim-test",
        scenario=config.scenario,
        tier="volume",
        cohort_size=50,
        responses=[],
        cost_estimate_usd=0.25,
        cost_actual_usd=0.25,
        started_at=now,
        completed_at=now,
        shard_size=50,
        concurrency=20,
        shards=[],
        circuit_breaker_trips=0,
    )

    # Mock report (simple object)
    mock_report = MagicMock()
    mock_report.to_dict.return_value = {"run_id": "report-test"}
    mock_report.to_markdown.return_value = "# Report"

    return StudyResult(
        run_id="st-test001",
        config=config,
        cohort=cohort,
        simulation=sim,
        report=mock_report,
        started_at=now,
        completed_at=now,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. StudyConfig — construction and defaults
# ─────────────────────────────────────────────────────────────────────────────

class TestStudyConfig:

    def test_basic_construction(self):
        config = _make_config()
        assert config.spec.state == "west_bengal"
        assert config.scenario.domain == SimulationDomain.POLITICAL

    def test_default_use_cache_true(self):
        config = _make_config()
        assert config.use_cache is True

    def test_default_run_social_false(self):
        config = _make_config()
        assert config.run_social is False

    def test_default_social_level_moderate(self):
        config = _make_config()
        assert config.social_level == SocialSimulationLevel.MODERATE

    def test_default_generation_tier_volume(self):
        config = _make_config()
        assert config.generation_tier == "volume"

    def test_default_shard_size_50(self):
        config = _make_config()
        assert config.shard_size == 50

    def test_environment_optional(self):
        config = StudyConfig(spec=_make_spec(), scenario=_make_scenario())
        assert config.environment is None

    def test_timeline_optional(self):
        config = _make_config()
        assert config.timeline is None

    def test_with_environment_preset(self):
        config = _make_config(environment=WEST_BENGAL_POLITICAL_2026)
        assert config.environment is not None
        assert config.environment.name == "west_bengal_political_2026"

    def test_with_timeline(self):
        tl = EventTimeline(events=[
            SimulationEvent(round=1, category=EventCategory.POLITICAL,
                            description="Election rally held in Kolkata.", magnitude=0.6),
        ])
        config = _make_config(timeline=tl)
        assert config.timeline is not None
        assert config.timeline.n_events == 1

    def test_social_settings_configurable(self):
        config = _make_config(
            run_social=True,
            social_level=SocialSimulationLevel.HIGH,
            social_topology="full_mesh",
            social_k=5,
        )
        assert config.run_social is True
        assert config.social_level == SocialSimulationLevel.HIGH
        assert config.social_topology == "full_mesh"
        assert config.social_k == 5

    def test_budget_cap_optional(self):
        config = _make_config(budget_cap_usd=50.0)
        assert config.budget_cap_usd == 50.0

    def test_cache_path_optional(self):
        config = _make_config(cache_path=Path("/tmp/test_cache.json"))
        assert config.cache_path == Path("/tmp/test_cache.json")


# ─────────────────────────────────────────────────────────────────────────────
# 2. StudyResult — properties and methods
# ─────────────────────────────────────────────────────────────────────────────

class TestStudyResult:

    def test_duration_seconds_non_negative(self):
        config = _make_config()
        result = _make_study_result(config)
        assert result.duration_seconds >= 0.0

    def test_total_cost_usd_sums_cohort_and_sim(self):
        config = _make_config()
        result = _make_study_result(config)
        assert abs(result.total_cost_usd - 0.50) < 0.001  # 0.25 gen + 0.25 sim

    def test_n_personas_equals_delivered(self):
        config = _make_config()
        result = _make_study_result(config)
        assert result.n_personas == 50

    def test_summary_contains_run_id(self):
        config = _make_config()
        result = _make_study_result(config)
        assert "st-test001" in result.summary()

    def test_summary_contains_cost(self):
        config = _make_config()
        result = _make_study_result(config)
        assert "$" in result.summary()

    def test_to_dict_required_keys(self):
        config = _make_config()
        result = _make_study_result(config)
        d = result.to_dict()
        for key in ("run_id", "started_at", "completed_at", "n_personas",
                    "total_cost_usd", "cohort", "simulation", "report"):
            assert key in d

    def test_to_dict_cohort_segment_breakdown(self):
        config = _make_config()
        result = _make_study_result(config)
        d = result.to_dict()
        assert "segments" in d["cohort"]
        assert len(d["cohort"]["segments"]) >= 1

    def test_social_result_none_when_not_run(self):
        config = _make_config(run_social=False)
        result = _make_study_result(config)
        assert result.social_result is None
        assert result.social_report is None

    def test_to_dict_social_none_when_not_run(self):
        config = _make_config(run_social=False)
        result = _make_study_result(config)
        d = result.to_dict()
        assert d["social"] is None


# ─────────────────────────────────────────────────────────────────────────────
# 3. Module interface
# ─────────────────────────────────────────────────────────────────────────────

class TestStudyRunnerInterface:

    def test_run_study_is_coroutine(self):
        import asyncio
        assert asyncio.iscoroutinefunction(run_study)

    def test_run_study_sync_is_callable(self):
        assert callable(run_study_sync)

    def test_run_study_signature(self):
        import inspect
        sig = inspect.signature(run_study)
        assert "config" in sig.parameters

    def test_study_config_importable(self):
        from popscale.study.study_runner import StudyConfig
        assert StudyConfig is not None

    def test_study_result_importable(self):
        from popscale.study.study_runner import StudyResult
        assert StudyResult is not None


# ─────────────────────────────────────────────────────────────────────────────
# 4. Environment preset integration
# ─────────────────────────────────────────────────────────────────────────────

class TestEnvironmentIntegration:

    def test_environment_applied_to_scenario(self):
        """apply_environment() called during run_study enriches the scenario."""
        from popscale.environment import apply_environment
        config = _make_config(environment=WEST_BENGAL_POLITICAL_2026)
        enriched = apply_environment(config.scenario, config.environment)
        assert "West Bengal" in enriched.environment.get("region", "")

    def test_no_environment_scenario_unchanged(self):
        config = StudyConfig(spec=_make_spec(), scenario=_make_scenario())
        original_env = dict(config.scenario.environment)
        assert config.scenario.environment == original_env

    def test_urban_consumer_preset_urban_only(self):
        from popscale.environment import build_population_spec
        spec = build_population_spec(
            env=INDIA_URBAN_CONSUMER,
            n_personas=50,
            domain="consumer",
            business_problem="Test.",
        )
        assert spec.urban_only is True


# ─────────────────────────────────────────────────────────────────────────────
# 5. EventTimeline integration
# ─────────────────────────────────────────────────────────────────────────────

class TestTimelineIntegration:

    def _make_timeline(self) -> EventTimeline:
        return EventTimeline(events=[
            SimulationEvent(round=0, category=EventCategory.ECONOMIC,
                            description="Fuel prices spike 40%.", magnitude=0.8,
                            tags=["bengal", "fuel"]),
            SimulationEvent(round=1, category=EventCategory.POLITICAL,
                            description="TMC rally in Kolkata draws 100K.", magnitude=0.7,
                            tags=["bengal", "political"]),
        ])

    def test_timeline_stimuli_available_for_social(self):
        tl = self._make_timeline()
        config = _make_config(timeline=tl, run_social=True)
        # Stimuli for social loop = all timeline events as stimulus strings
        stimuli = config.timeline.all_stimuli()
        assert len(stimuli) == 2
        assert all(isinstance(s, str) for s in stimuli)

    def test_timeline_events_tagged_for_bengal(self):
        tl = self._make_timeline()
        bengal_events = tl.events_with_tag("bengal")
        assert len(bengal_events) == 2

    def test_timeline_round_0_stimuli(self):
        tl = self._make_timeline()
        r0 = tl.stimuli_for_round(0)
        assert len(r0) == 1
        assert "Fuel" in r0[0]

    def test_config_with_timeline_and_environment(self):
        tl = self._make_timeline()
        config = _make_config(
            environment=WEST_BENGAL_POLITICAL_2026,
            timeline=tl,
            run_social=True,
        )
        assert config.environment.calibration_state == "west_bengal"
        assert config.timeline.n_events == 2
        assert config.run_social is True


# ─────────────────────────────────────────────────────────────────────────────
# 6. West Bengal study config — end-to-end structural check
# ─────────────────────────────────────────────────────────────────────────────

class TestWestBengalStudyConfig:

    def test_wb_study_config_construction(self):
        """Full West Bengal study config should construct without error."""
        config = StudyConfig(
            spec=PopulationSpec(
                state="west_bengal",
                n_personas=500,
                domain="policy",
                business_problem=(
                    "West Bengal electoral sentiment: fuel prices, TMC incumbency, "
                    "BJP challenge, Muslim voter dynamics."
                ),
                stratify_by_religion=True,
                age_min=18,
                age_max=70,
            ),
            scenario=_make_scenario(),
            environment=WEST_BENGAL_POLITICAL_2026,
            timeline=EventTimeline(events=[
                SimulationEvent(
                    round=0,
                    category=EventCategory.ECONOMIC,
                    description="Fuel prices rise 40% following global oil shock.",
                    magnitude=0.8,
                    tags=["fuel", "bengal"],
                ),
                SimulationEvent(
                    round=1,
                    category=EventCategory.POLITICAL,
                    description="BJP national leader holds rally in North Bengal.",
                    magnitude=0.75,
                    tags=["bjp", "bengal"],
                ),
            ]),
            run_social=True,
            social_level=SocialSimulationLevel.MODERATE,
            social_topology="random_encounter",
            social_k=3,
            social_seed=42,
            generation_tier="volume",
            budget_cap_usd=30.0,
            use_cache=True,
            shard_size=50,
            concurrency=20,
            run_id="wb-study-2026",
        )
        assert config.spec.n_personas == 500
        assert config.environment.name == "west_bengal_political_2026"
        assert config.timeline.n_events == 2
        assert config.run_social is True
        assert config.budget_cap_usd == 30.0

    def test_wb_spec_calibration_matches_demographics(self):
        """Calibrating a 500-persona WB spec gives correct proportions."""
        from popscale.calibration.calibrator import calibrate
        spec = PopulationSpec(
            state="west_bengal", n_personas=500,
            domain="policy", business_problem="Test.",
            stratify_by_religion=True,
        )
        segments = calibrate(spec)
        assert sum(s.count for s in segments) == 500
        hindu = next(s for s in segments if "Hindu" in s.label)
        muslim = next(s for s in segments if "Muslim" in s.label)
        assert hindu.count > muslim.count
        assert muslim.count >= 100  # ≥20% of 500
