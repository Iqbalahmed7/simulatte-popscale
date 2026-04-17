"""Week 2 Integration Tests — Population Orchestrator.

Tests:
    1. Cost estimation math (simulation-only, all tiers)
    2. Shard logic (_make_shards covers all split cases)
    3. SimulationResult derived properties
    4. Circuit breaker detection (fallback rate threshold)
    5. BudgetExceededError raised before API calls
    6. LIVE: run_population_scenario with Montage personas (5 agents)

Run all except live:
    cd "/Users/admin/Documents/Simulatte Projects/PopScale"
    python3 -m pytest tests/test_week2_orchestration.py -v

Run live tests (real API calls):
    python3 -m pytest tests/test_week2_orchestration.py -v -m live
"""

from __future__ import annotations

# ── sys.path — must be first ──────────────────────────────────────────────────
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
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

# ── PopScale imports ──────────────────────────────────────────────────────────
from popscale.orchestrator.cost import (
    SimulationCostEstimate,
    estimate_simulation_cost,
)
from popscale.orchestrator.runner import (
    BudgetExceededError,
    _make_shards,
    run_population_scenario,
)
from popscale.schema.simulation_result import ShardRecord, SimulationResult
from popscale.scenario.model import Scenario, SimulationDomain

# ── PG imports ────────────────────────────────────────────────────────────────
from src.experiment.session import SimulationTier


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_montage_personas():
    """Load Montage v1.0 personas via adapter (5 personas)."""
    from popscale.utils.persona_adapter import load_cohort_file
    cohort_path = _PG_ROOT / "pilots" / "montage" / "cohort_montage_20260412.json"
    if not cohort_path.exists():
        return []
    return load_cohort_file(cohort_path)


def _make_simulation_result(
    n_responses: int = 10,
    n_fallbacks: int = 0,
    duration_s: float = 5.0,
    cb_trips: int = 0,
) -> SimulationResult:
    """Build a minimal SimulationResult for property tests."""
    from popscale.schema.population_response import PopulationResponse, DomainSignals

    def _make_response(idx: int, is_fallback: bool) -> PopulationResponse:
        trace = "[FALLBACK] test" if is_fallback else "Full reasoning trace."
        return PopulationResponse(
            persona_id=f"test-{idx:03d}",
            persona_name=f"Test Persona {idx}",
            age=30,
            gender="male",
            location_city="Delhi",
            location_country="India",
            income_bracket="middle",
            scenario_domain="consumer",
            scenario_options=["Option A", "Option B"],
            decision="Option A",
            confidence=0.72,
            reasoning_trace=trace,
            gut_reaction="Positive",
            key_drivers=["price", "quality"],
            objections=[],
            what_would_change_mind="Better price",
            follow_up_action="Research more",
            emotional_valence=0.4,
            domain_signals=DomainSignals(openness_score=0.6),
            risk_appetite="medium",
            trust_anchor="peer",
            decision_style="analytical",
            primary_value_orientation="pragmatism",
            consistency_score=72,
            price_sensitivity_band="medium",
            switching_propensity_band="low",
        )

    responses = [_make_response(i, i < n_fallbacks) for i in range(n_responses)]

    now = datetime.now(timezone.utc)
    from datetime import timedelta
    started = datetime(now.year, now.month, now.day, 10, 0, 0, tzinfo=timezone.utc)
    completed = datetime(now.year, now.month, now.day, 10, 0, int(duration_s), tzinfo=timezone.utc)

    scenario = Scenario(
        question="Should we launch the new pricing tier?",
        context="A consumer scenario with sufficient context for validation.",
        domain=SimulationDomain.CONSUMER,
    )

    return SimulationResult(
        run_id="test-run-001",
        scenario=scenario,
        tier="volume",
        cohort_size=n_responses,
        responses=responses,
        cost_estimate_usd=0.0042,
        cost_actual_usd=0.0042,
        started_at=started,
        completed_at=completed,
        shard_size=50,
        concurrency=20,
        circuit_breaker_trips=cb_trips,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Cost estimation
# ─────────────────────────────────────────────────────────────────────────────

class TestCostEstimation:

    def test_returns_simulation_cost_estimate(self):
        est = estimate_simulation_cost(count=100, tier=SimulationTier.VOLUME)
        assert isinstance(est, SimulationCostEstimate)

    def test_volume_cheaper_than_signal(self):
        vol = estimate_simulation_cost(100, SimulationTier.VOLUME)
        sig = estimate_simulation_cost(100, SimulationTier.SIGNAL)
        assert vol.sim_cost_usd < sig.sim_cost_usd

    def test_signal_cheaper_than_deep(self):
        sig = estimate_simulation_cost(100, SimulationTier.SIGNAL)
        deep = estimate_simulation_cost(100, SimulationTier.DEEP)
        assert sig.sim_cost_usd < deep.sim_cost_usd

    def test_cost_scales_with_count(self):
        est_100 = estimate_simulation_cost(100, SimulationTier.VOLUME)
        est_500 = estimate_simulation_cost(500, SimulationTier.VOLUME)
        # 500 should cost roughly 5× more (within 20% tolerance)
        ratio = est_500.sim_cost_usd / est_100.sim_cost_usd
        assert 4.0 <= ratio <= 6.0

    def test_per_persona_cost_is_consistent(self):
        est = estimate_simulation_cost(count=200, tier=SimulationTier.VOLUME)
        assert abs(est.per_persona_usd - est.sim_cost_usd / 200) < 0.000001

    def test_formatted_output_contains_key_fields(self):
        est = estimate_simulation_cost(count=50, tier=SimulationTier.SIGNAL)
        formatted = est.formatted()
        assert "SIGNAL" in formatted
        assert "50" in formatted
        assert "$" in formatted

    def test_zero_cost_for_zero_personas(self):
        est = estimate_simulation_cost(count=0, tier=SimulationTier.VOLUME)
        assert est.sim_cost_usd == 0.0

    def test_time_estimate_present(self):
        est = estimate_simulation_cost(count=100, tier=SimulationTier.VOLUME)
        assert "min" in est.est_time_range or "s" in est.est_time_range

    def test_500_personas_under_5_dollars_volume(self):
        """500-persona VOLUME run should cost under $5 (simulation only, ~$0.005/persona)."""
        est = estimate_simulation_cost(count=500, tier=SimulationTier.VOLUME)
        assert est.sim_cost_usd < 5.00
        assert est.per_persona_usd < 0.01  # under 1 cent per persona


# ─────────────────────────────────────────────────────────────────────────────
# 2. Shard logic
# ─────────────────────────────────────────────────────────────────────────────

class TestShardLogic:

    def _dummy_personas(self, n: int) -> list:
        return [object() for _ in range(n)]

    def test_exact_multiple(self):
        shards = _make_shards(self._dummy_personas(100), shard_size=50)
        assert len(shards) == 2
        assert all(len(s) == 50 for s in shards)

    def test_partial_last_shard(self):
        shards = _make_shards(self._dummy_personas(105), shard_size=50)
        assert len(shards) == 3
        assert len(shards[-1]) == 5

    def test_smaller_than_shard_size(self):
        shards = _make_shards(self._dummy_personas(10), shard_size=50)
        assert len(shards) == 1
        assert len(shards[0]) == 10

    def test_exactly_one(self):
        shards = _make_shards(self._dummy_personas(1), shard_size=50)
        assert len(shards) == 1
        assert len(shards[0]) == 1

    def test_shard_size_one(self):
        shards = _make_shards(self._dummy_personas(5), shard_size=1)
        assert len(shards) == 5
        assert all(len(s) == 1 for s in shards)

    def test_preserves_order(self):
        personas = list(range(7))
        shards = _make_shards(personas, shard_size=3)  # type: ignore[arg-type]
        flat = [x for s in shards for x in s]
        assert flat == personas


# ─────────────────────────────────────────────────────────────────────────────
# 3. SimulationResult properties
# ─────────────────────────────────────────────────────────────────────────────

class TestSimulationResult:

    def test_success_count(self):
        result = _make_simulation_result(n_responses=10, n_fallbacks=2)
        assert result.success_count == 8
        assert result.fallback_count == 2

    def test_success_rate_zero_fallbacks(self):
        result = _make_simulation_result(n_responses=10, n_fallbacks=0)
        assert result.success_rate == 1.0

    def test_success_rate_all_fallbacks(self):
        result = _make_simulation_result(n_responses=5, n_fallbacks=5)
        assert result.success_rate == 0.0

    def test_success_rate_partial(self):
        result = _make_simulation_result(n_responses=10, n_fallbacks=3)
        assert abs(result.success_rate - 0.7) < 0.0001

    def test_duration_seconds(self):
        result = _make_simulation_result(duration_s=42.0)
        assert abs(result.duration_seconds - 42.0) < 1.0

    def test_responses_delivered(self):
        result = _make_simulation_result(n_responses=7)
        assert result.responses_delivered == 7

    def test_summary_contains_key_info(self):
        result = _make_simulation_result(n_responses=10, n_fallbacks=1)
        summary = result.summary()
        assert "test-run-001" in summary
        assert "10/10" in summary
        assert "90.0%" in summary

    def test_to_dict_keys(self):
        result = _make_simulation_result(n_responses=5)
        d = result.to_dict()
        for key in ["run_id", "tier", "cohort_size", "success_rate",
                    "cost_estimate_usd", "duration_seconds"]:
            assert key in d

    def test_circuit_breaker_trips_tracked(self):
        result = _make_simulation_result(cb_trips=3)
        assert result.circuit_breaker_trips == 3


# ─────────────────────────────────────────────────────────────────────────────
# 4. Circuit breaker detection
# ─────────────────────────────────────────────────────────────────────────────

class TestCircuitBreakerDetection:

    def test_shard_record_fallback_rate(self):
        rec = ShardRecord(
            shard_index=0,
            shard_size=50,
            responses_collected=50,
            fallback_count=6,
            circuit_breaker_tripped=True,
        )
        assert abs(rec.fallback_rate - 0.12) < 0.001

    def test_shard_record_clean(self):
        rec = ShardRecord(
            shard_index=0,
            shard_size=50,
            responses_collected=50,
            fallback_count=0,
            circuit_breaker_tripped=False,
        )
        assert rec.fallback_rate == 0.0
        assert not rec.circuit_breaker_tripped

    def test_shard_record_zero_responses(self):
        rec = ShardRecord(
            shard_index=0,
            shard_size=50,
            responses_collected=0,
            fallback_count=0,
        )
        assert rec.fallback_rate == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# 5. Budget cap
# ─────────────────────────────────────────────────────────────────────────────

class TestBudgetCap:

    def test_budget_exceeded_raises(self):
        """Budget cap of $0.0001 is always exceeded — no API calls made."""
        personas = _load_montage_personas()
        if not personas:
            pytest.skip("Montage cohort not available")

        scenario = Scenario(
            question="Which subscription plan would you choose?",
            context="A fintech app offers three plans with different features and prices.",
            options=["Free", "Standard ($5/mo)", "Premium ($15/mo)"],
            domain=SimulationDomain.CONSUMER,
        )

        with pytest.raises(BudgetExceededError):
            asyncio.run(
                run_population_scenario(
                    scenario=scenario,
                    personas=personas,
                    budget_cap_usd=0.0001,  # tiny cap — always exceeded
                    print_estimate=False,
                )
            )

    def test_empty_personas_raises_value_error(self):
        scenario = Scenario(
            question="Which option do you prefer?",
            context="A simple consumer choice with adequate context.",
            domain=SimulationDomain.CONSUMER,
        )
        with pytest.raises(ValueError, match="empty"):
            asyncio.run(
                run_population_scenario(
                    scenario=scenario,
                    personas=[],
                    print_estimate=False,
                )
            )


# ─────────────────────────────────────────────────────────────────────────────
# 6. Live end-to-end tests (real API calls)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.live
class TestLivePopulationOrchestration:
    """Live tests — make actual LLM calls. Run with -m live flag."""

    def test_run_population_scenario_montage(self):
        """Run all 5 Montage personas through the consumer scenario."""
        personas = _load_montage_personas()
        if not personas:
            pytest.skip("Montage cohort not available")

        scenario = Scenario(
            question="Would you pay for an AI tool that automates the most tedious "
                     "parts of your video editing workflow?",
            context=(
                "A new SaaS tool called Montage automatically selects the best clips "
                "from raw footage, generates a rough cut in under 10 minutes, and "
                "logs every decision for team review. Priced at $49/month. "
                "Currently used by video teams at 3 mid-size studios."
            ),
            options=[
                "Yes — start a paid trial immediately",
                "Maybe — request a demo first",
                "No — not interested at this price",
            ],
            domain=SimulationDomain.CONSUMER,
            environment={"region": "US", "market_conditions": "SaaS growth"},
        )

        result = asyncio.run(
            run_population_scenario(
                scenario=scenario,
                personas=personas,
                tier=SimulationTier.VOLUME,
                shard_size=5,       # 5 personas → 1 shard (all at once)
                concurrency=5,
                print_estimate=True,
            )
        )

        # Basic structural checks
        assert result.responses_delivered == len(personas)
        assert result.cohort_size == len(personas)
        assert result.tier == "volume"
        assert result.duration_seconds > 0

        # Each response must be valid
        for r in result.responses:
            assert r.persona_name != ""
            assert r.decision != ""
            assert 0.0 <= r.confidence <= 1.0
            assert r.scenario_domain == "consumer"
            assert r.domain_signals is not None

        # Cost estimate must be a small positive number
        assert result.cost_estimate_usd > 0.0
        assert result.cost_estimate_usd < 1.0  # 5 personas VOLUME << $1

        print(f"\n[live] {result.summary()}")
        print("[live] Decision distribution:")
        from collections import Counter
        decisions = Counter(r.decision[:40] for r in result.responses)
        for dec, count in decisions.most_common():
            print(f"  {count}× {dec!r}")

    def test_streaming_callback_invoked(self):
        """Streaming callback is called after each shard."""
        personas = _load_montage_personas()
        if not personas:
            pytest.skip("Montage cohort not available")

        shard_results: list[list] = []

        def on_shard(responses):
            shard_results.append(responses)

        scenario = Scenario(
            question="How likely are you to recommend Montage to a colleague?",
            context=(
                "Montage is a video production SaaS tool with AI-assisted clip selection "
                "and automatic rough-cut generation. You have been using it for 2 weeks."
            ),
            domain=SimulationDomain.CONSUMER,
        )

        asyncio.run(
            run_population_scenario(
                scenario=scenario,
                personas=personas,
                tier=SimulationTier.VOLUME,
                shard_size=3,          # 5 personas → 2 shards (3+2)
                concurrency=3,
                on_shard_complete=on_shard,
                print_estimate=False,
            )
        )

        # Callback should have been called once per shard
        assert len(shard_results) == 2      # ceil(5/3) = 2 shards
        assert len(shard_results[0]) == 3   # first shard: 3
        assert len(shard_results[1]) == 2   # second shard: 2
        print(f"\n[live] Streaming: {len(shard_results)} shards received by callback")
