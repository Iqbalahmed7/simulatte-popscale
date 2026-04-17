"""Week 5 Social Simulation Tests — Structural and Analytics (no live API).

Tests:
    1. SocialSimulationResult dataclass — structure and properties
    2. analyse_trajectory() — influence stats with mock trace
    3. analyse_trajectory() — drift summary with tendency shift records
    4. generate_social_report() — report structure and export methods
    5. social_runner module — imports, re-exports, and signature

Run all (no live API calls needed):
    python3 -m pytest tests/test_week5_social.py -v
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

_POPSCALE_ROOT = Path(__file__).parents[1]
_PG_ROOT       = _POPSCALE_ROOT.parent / "Persona Generator"
if str(_POPSCALE_ROOT) not in sys.path:
    sys.path.insert(0, str(_POPSCALE_ROOT))
if str(_PG_ROOT) not in sys.path:
    sys.path.insert(1, str(_PG_ROOT))

import pytest

# PopScale imports
from popscale.schema.social_simulation_result import SocialSimulationResult
from popscale.analytics.trajectory import (
    analyse_trajectory,
    InfluenceStats,
    DriftSummary,
    TrajectoryResult,
)
from popscale.analytics.social_report import generate_social_report, SocialReport

# PG imports (for building mock trace objects)
from src.social.schema import (
    SocialSimulationLevel,
    SocialSimulationTrace,
    NetworkTopology,
    InfluenceVector,
    TendencyShiftRecord,
)


# ── Mock helpers ──────────────────────────────────────────────────────────────

def _make_trace(
    *,
    n_personas: int = 5,
    events_per_persona: int = 3,
    include_shifts: bool = False,
    level: SocialSimulationLevel = SocialSimulationLevel.MODERATE,
    topology: NetworkTopology = NetworkTopology.RANDOM_ENCOUNTER,
) -> SocialSimulationTrace:
    """Build a minimal SocialSimulationTrace for testing."""
    persona_ids = [f"p{i:03d}" for i in range(n_personas)]

    influence_vectors: dict[str, InfluenceVector] = {}
    for i, pid in enumerate(persona_ids):
        influence_vectors[pid] = InfluenceVector(
            persona_id=pid,
            total_events_transmitted=events_per_persona + i,  # vary slightly
            total_events_received=events_per_persona,
            mean_gated_importance_transmitted=0.6 + i * 0.01,
            mean_gated_importance_received=0.55,
        )

    shifts: list[TendencyShiftRecord] = []
    if include_shifts:
        shifts = [
            TendencyShiftRecord(
                record_id=str(uuid.uuid4()),
                persona_id=f"p{i:03d}",
                session_id="ses-test",
                turn_triggered=2,
                tendency_field="trust_orientation.description",
                description_before="Skeptical of institutions",
                description_after="Cautiously trusting of local institutions",
                source_social_reflection_ids=[str(uuid.uuid4()) for _ in range(3)],
                social_simulation_level=level,
            )
            for i in range(2)  # 2 personas shift
        ] + [
            TendencyShiftRecord(
                record_id=str(uuid.uuid4()),
                persona_id="p000",
                session_id="ses-test",
                turn_triggered=3,
                tendency_field="risk_appetite.description",
                description_before="Risk averse",
                description_after="Somewhat risk tolerant",
                source_social_reflection_ids=[str(uuid.uuid4()) for _ in range(3)],
                social_simulation_level=level,
            )
        ]

    total_events = sum(
        v.total_events_transmitted for v in influence_vectors.values()
    )

    return SocialSimulationTrace(
        trace_id=str(uuid.uuid4()),
        session_id="ses-test",
        cohort_id="coh-test",
        social_simulation_level=level,
        network_topology=topology,
        total_turns=3,
        total_influence_events=total_events,
        influence_vectors=influence_vectors,
        tendency_shift_log=shifts,
        validity_gate_results={},
    )


def _make_social_result(trace: SocialSimulationTrace) -> SocialSimulationResult:
    now = datetime.now(timezone.utc)
    return SocialSimulationResult(
        run_id="ss-test001",
        scenario_question="Will you join the protest?",
        scenario_domain="policy",
        scenario_stimuli=["Fuel prices rose 40% overnight."],
        tier="deep",
        cohort_size=trace.total_influence_events,  # dummy; trace is what matters
        personas_before=[],
        personas_after=[],
        trace=trace,
        network_topology=trace.network_topology.value,
        social_level=trace.social_simulation_level.value,
        started_at=now,
        completed_at=now,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. SocialSimulationResult
# ─────────────────────────────────────────────────────────────────────────────

class TestSocialSimulationResult:

    def test_properties_computed_correctly(self):
        trace = _make_trace(n_personas=3, events_per_persona=2, include_shifts=True)
        result = _make_social_result(trace)
        assert result.total_tendency_shifts == 3
        assert result.total_influence_events == trace.total_influence_events

    def test_duration_seconds_non_negative(self):
        trace = _make_trace()
        result = _make_social_result(trace)
        assert result.duration_seconds >= 0.0

    def test_summary_contains_key_fields(self):
        trace = _make_trace()
        result = _make_social_result(trace)
        s = result.summary()
        assert "ss-test001" in s
        assert "moderate" in s
        assert "random_encounter" in s

    def test_no_shifts_gives_zero_drift_count(self):
        trace = _make_trace(include_shifts=False)
        result = _make_social_result(trace)
        assert result.total_tendency_shifts == 0


# ─────────────────────────────────────────────────────────────────────────────
# 2. analyse_trajectory — influence stats
# ─────────────────────────────────────────────────────────────────────────────

class TestInfluenceStats:

    def test_returns_trajectory_result(self):
        trace = _make_trace(n_personas=5)
        result = analyse_trajectory(trace, n_personas=5)
        assert isinstance(result, TrajectoryResult)
        assert isinstance(result.influence, InfluenceStats)
        assert isinstance(result.drift, DriftSummary)

    def test_total_events_matches_trace(self):
        trace = _make_trace(n_personas=5, events_per_persona=4)
        result = analyse_trajectory(trace, n_personas=5)
        assert result.influence.total_influence_events == trace.total_influence_events

    def test_top_transmitters_at_most_3(self):
        trace = _make_trace(n_personas=10, events_per_persona=2)
        result = analyse_trajectory(trace, n_personas=10)
        assert len(result.influence.top_transmitters) <= 3

    def test_top_receivers_at_most_3(self):
        trace = _make_trace(n_personas=10, events_per_persona=2)
        result = analyse_trajectory(trace, n_personas=10)
        assert len(result.influence.top_receivers) <= 3

    def test_top_transmitter_has_most_events(self):
        trace = _make_trace(n_personas=5, events_per_persona=2)
        result = analyse_trajectory(trace, n_personas=5)
        txs = result.influence.top_transmitters
        if len(txs) >= 2:
            assert txs[0].events_transmitted >= txs[1].events_transmitted

    def test_network_density_between_0_and_1(self):
        trace = _make_trace(n_personas=5, events_per_persona=3)
        result = analyse_trajectory(trace, n_personas=5)
        assert 0.0 <= result.influence.network_density <= 1.0

    def test_empty_trace_gives_zero_stats(self):
        trace = SocialSimulationTrace(
            trace_id=str(uuid.uuid4()),
            session_id="ses-empty",
            cohort_id="coh-empty",
            social_simulation_level=SocialSimulationLevel.ISOLATED,
            network_topology=NetworkTopology.FULL_MESH,
            total_turns=0,
            total_influence_events=0,
            influence_vectors={},
            tendency_shift_log=[],
            validity_gate_results={},
        )
        result = analyse_trajectory(trace, n_personas=3)
        assert result.influence.total_influence_events == 0
        assert result.influence.network_density == 0.0
        assert result.influence.top_transmitters == []

    def test_mean_events_transmitted_positive(self):
        trace = _make_trace(n_personas=4, events_per_persona=5)
        result = analyse_trajectory(trace, n_personas=4)
        assert result.influence.mean_events_transmitted > 0.0

    def test_importance_values_are_floats(self):
        trace = _make_trace(n_personas=4)
        result = analyse_trajectory(trace, n_personas=4)
        assert isinstance(result.influence.mean_importance_transmitted, float)
        assert isinstance(result.influence.mean_importance_received, float)


# ─────────────────────────────────────────────────────────────────────────────
# 3. analyse_trajectory — drift summary
# ─────────────────────────────────────────────────────────────────────────────

class TestDriftSummary:

    def test_no_shifts_no_drift(self):
        trace = _make_trace(include_shifts=False)
        result = analyse_trajectory(trace, n_personas=5)
        assert not result.drift.has_drift
        assert result.drift.total_shifts == 0
        assert result.drift.personas_shifted == 0
        assert result.drift.most_drifted_fields == []

    def test_shifts_detected(self):
        trace = _make_trace(n_personas=5, include_shifts=True)
        result = analyse_trajectory(trace, n_personas=5)
        assert result.drift.has_drift
        assert result.drift.total_shifts == 3

    def test_personas_shifted_count(self):
        trace = _make_trace(n_personas=5, include_shifts=True)
        result = analyse_trajectory(trace, n_personas=5)
        # p000 gets 2 shifts (trust + risk), p001 gets 1 shift
        assert result.drift.personas_shifted == 2

    def test_most_drifted_fields_sorted_by_count(self):
        trace = _make_trace(n_personas=5, include_shifts=True)
        result = analyse_trajectory(trace, n_personas=5)
        fields = result.drift.most_drifted_fields
        assert len(fields) >= 1
        if len(fields) >= 2:
            assert fields[0].shift_count >= fields[1].shift_count

    def test_most_drifted_fields_at_most_5(self):
        trace = _make_trace(n_personas=5, include_shifts=True)
        result = analyse_trajectory(trace, n_personas=5)
        assert len(result.drift.most_drifted_fields) <= 5

    def test_trust_orientation_field_detected(self):
        trace = _make_trace(n_personas=5, include_shifts=True)
        result = analyse_trajectory(trace, n_personas=5)
        fields = [e.field for e in result.drift.most_drifted_fields]
        assert "trust_orientation.description" in fields


# ─────────────────────────────────────────────────────────────────────────────
# 4. generate_social_report
# ─────────────────────────────────────────────────────────────────────────────

class TestSocialReport:

    def _make_report(self, include_shifts: bool = False) -> SocialReport:
        trace  = _make_trace(n_personas=5, include_shifts=include_shifts)
        result = _make_social_result(trace)
        return generate_social_report(result)

    def test_returns_social_report(self):
        assert isinstance(self._make_report(), SocialReport)

    def test_to_dict_structure(self):
        report = self._make_report()
        d = report.to_dict()
        assert "run_id" in d
        assert "scenario" in d
        assert "run" in d
        assert "influence" in d
        assert "drift" in d

    def test_to_dict_influence_keys(self):
        report = self._make_report()
        inf = report.to_dict()["influence"]
        for key in ("total_events", "network_density", "mean_events_transmitted",
                    "mean_events_received", "top_transmitters", "top_receivers"):
            assert key in inf

    def test_to_dict_drift_keys(self):
        report = self._make_report()
        drift = report.to_dict()["drift"]
        for key in ("total_shifts", "personas_shifted", "has_drift", "most_drifted_fields"):
            assert key in drift

    def test_to_markdown_is_string(self):
        report = self._make_report()
        md = report.to_markdown()
        assert isinstance(md, str)
        assert len(md) > 100

    def test_markdown_contains_run_id(self):
        report = self._make_report()
        assert "ss-test001" in report.to_markdown()

    def test_markdown_contains_scenario_question(self):
        report = self._make_report()
        assert "Will you join the protest?" in report.to_markdown()

    def test_markdown_drift_section_no_shifts(self):
        report = self._make_report(include_shifts=False)
        md = report.to_markdown()
        assert "No tendency drift detected" in md

    def test_markdown_drift_section_with_shifts(self):
        report = self._make_report(include_shifts=True)
        md = report.to_markdown()
        assert "tendency shift" in md.lower()

    def test_report_run_id_matches_result(self):
        report = self._make_report()
        assert report.run_id == "ss-test001"

    def test_report_social_level_preserved(self):
        report = self._make_report()
        assert report.social_level == "moderate"

    def test_report_network_topology_preserved(self):
        report = self._make_report()
        assert report.network_topology == "random_encounter"


# ─────────────────────────────────────────────────────────────────────────────
# 5. social_runner module — imports and signature
# ─────────────────────────────────────────────────────────────────────────────

class TestSocialRunnerModule:

    def test_run_social_scenario_importable(self):
        from popscale.social.social_runner import run_social_scenario
        assert callable(run_social_scenario)

    def test_network_builders_re_exported(self):
        from popscale.social.social_runner import (
            build_full_mesh,
            build_random_encounter,
            build_directed_graph,
        )
        assert callable(build_full_mesh)
        assert callable(build_random_encounter)
        assert callable(build_directed_graph)

    def test_social_simulation_level_re_exported(self):
        from popscale.social.social_runner import SocialSimulationLevel
        assert SocialSimulationLevel.MODERATE.value == "moderate"

    def test_run_social_scenario_signature(self):
        import inspect
        from popscale.social.social_runner import run_social_scenario
        sig = inspect.signature(run_social_scenario)
        for param in ("scenario", "personas", "stimuli", "network", "level"):
            assert param in sig.parameters, f"Missing param: {param}"
        for kwarg in ("tier", "run_id", "llm_client"):
            assert kwarg in sig.parameters, f"Missing kwarg: {kwarg}"

    def test_run_social_scenario_is_coroutine(self):
        import asyncio
        import inspect
        from popscale.social.social_runner import run_social_scenario
        assert asyncio.iscoroutinefunction(run_social_scenario)

    def test_build_full_mesh_returns_network(self):
        from popscale.social.social_runner import build_full_mesh, SocialNetwork
        network = build_full_mesh(["p001", "p002", "p003"])
        assert isinstance(network, SocialNetwork)
        # Full mesh: n*(n-1) directed edges = 6 for 3 personas
        assert len(network.edges) == 6

    def test_build_random_encounter_returns_network(self):
        from popscale.social.social_runner import build_random_encounter, SocialNetwork
        network = build_random_encounter(["p001", "p002", "p003", "p004"], k=2, seed=42)
        assert isinstance(network, SocialNetwork)

    def test_build_random_encounter_deterministic_with_seed(self):
        from popscale.social.social_runner import build_random_encounter
        n1 = build_random_encounter(["a", "b", "c", "d"], k=2, seed=99)
        n2 = build_random_encounter(["a", "b", "c", "d"], k=2, seed=99)
        edges1 = {(e.source_id, e.target_id) for e in n1.edges}
        edges2 = {(e.source_id, e.target_id) for e in n2.edges}
        assert edges1 == edges2
