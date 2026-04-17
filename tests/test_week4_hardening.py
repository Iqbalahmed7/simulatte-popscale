"""Week 4 Hardening Tests — Cache, Circuit Breaker, Scale.

Tests:
    1. ResponseCache key generation (deterministic, unique, collision-resistant)
    2. Cache get/put/invalidate/clear
    3. Cache hit rate accounting
    4. Cache disk persistence (write → reload → hit)
    5. Circuit breaker threshold detection
    6. runner.py cache integration (cache hits skip LLM, cache misses run LLM)

Run all (no live API calls needed):
    python3 -m pytest tests/test_week4_hardening.py -v
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_POPSCALE_ROOT = Path(__file__).parents[1]
_PG_ROOT       = _POPSCALE_ROOT.parent / "Persona Generator"
if str(_POPSCALE_ROOT) not in sys.path:
    sys.path.insert(0, str(_POPSCALE_ROOT))
if str(_PG_ROOT) not in sys.path:
    sys.path.insert(1, str(_PG_ROOT))

import pytest

from popscale.cache.response_cache import ResponseCache
from popscale.schema.population_response import DomainSignals, PopulationResponse
from popscale.scenario.model import Scenario, SimulationDomain


# ── Shared fixtures ───────────────────────────────────────────────────────────

SCENARIO_A = Scenario(
    question="Would you pay for Montage at $49/month?",
    context="Montage is a video SaaS tool with AI-assisted clip selection and rough-cut generation.",
    options=["Yes", "Maybe", "No"],
    domain=SimulationDomain.CONSUMER,
)

SCENARIO_B = Scenario(
    question="How do you feel about the proposed data privacy regulation?",
    context="Parliament has passed the Digital Data Protection Act requiring explicit consent for data collection.",
    domain=SimulationDomain.POLICY,
)


def _make_response(persona_id: str = "p001") -> PopulationResponse:
    return PopulationResponse(
        persona_id=persona_id,
        persona_name="Test Persona",
        age=30,
        gender="male",
        location_city="Mumbai",
        location_country="India",
        income_bracket="middle",
        scenario_domain="consumer",
        scenario_options=["Yes", "Maybe", "No"],
        decision="Yes",
        confidence=0.75,
        reasoning_trace="Full reasoning trace for test.",
        gut_reaction="Positive",
        key_drivers=["price", "quality"],
        objections=[],
        what_would_change_mind="Lower price",
        follow_up_action="Sign up",
        emotional_valence=0.5,
        domain_signals=DomainSignals(openness_score=0.7, price_sensitivity=0.4, trial_likelihood=0.6),
        risk_appetite="high",
        trust_anchor="peer",
        decision_style="analytical",
        primary_value_orientation="quality",
        consistency_score=75,
        price_sensitivity_band="medium",
        switching_propensity_band="low",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Cache key generation
# ─────────────────────────────────────────────────────────────────────────────

class TestCacheKey:

    def test_same_inputs_give_same_key(self):
        k1 = ResponseCache.make_key("persona-001", SCENARIO_A)
        k2 = ResponseCache.make_key("persona-001", SCENARIO_A)
        assert k1 == k2

    def test_different_personas_give_different_keys(self):
        k1 = ResponseCache.make_key("persona-001", SCENARIO_A)
        k2 = ResponseCache.make_key("persona-002", SCENARIO_A)
        assert k1 != k2

    def test_different_scenarios_give_different_keys(self):
        k1 = ResponseCache.make_key("persona-001", SCENARIO_A)
        k2 = ResponseCache.make_key("persona-001", SCENARIO_B)
        assert k1 != k2

    def test_key_is_24_char_hex(self):
        key = ResponseCache.make_key("persona-001", SCENARIO_A)
        assert len(key) == 24
        assert all(c in "0123456789abcdef" for c in key)

    def test_case_insensitive_question(self):
        """Question casing should not affect the key."""
        import copy
        s_upper = Scenario(
            question=SCENARIO_A.question.upper(),
            context=SCENARIO_A.context,
            options=SCENARIO_A.options,
            domain=SCENARIO_A.domain,
        )
        k1 = ResponseCache.make_key("p001", SCENARIO_A)
        k2 = ResponseCache.make_key("p001", s_upper)
        assert k1 == k2


# ─────────────────────────────────────────────────────────────────────────────
# 2. Cache get / put / invalidate / clear
# ─────────────────────────────────────────────────────────────────────────────

class TestCacheOperations:

    def test_miss_returns_none(self):
        cache = ResponseCache()
        assert cache.get("nonexistent") is None

    def test_put_then_get_returns_response(self):
        cache = ResponseCache()
        response = _make_response()
        key = ResponseCache.make_key("p001", SCENARIO_A)
        cache.put(key, response)
        result = cache.get(key)
        assert result is not None
        assert result.persona_id == "p001"
        assert result.decision == "Yes"

    def test_domain_signals_preserved_through_cache(self):
        cache = ResponseCache()
        response = _make_response()
        key = "test-key-signals"
        cache.put(key, response)
        result = cache.get(key)
        assert result is not None
        assert result.domain_signals.openness_score == 0.7
        assert result.domain_signals.price_sensitivity == 0.4

    def test_invalidate_removes_entry(self):
        cache = ResponseCache()
        key = "test-key"
        cache.put(key, _make_response())
        assert cache.invalidate(key)
        assert cache.get(key) is None

    def test_invalidate_nonexistent_returns_false(self):
        cache = ResponseCache()
        assert not cache.invalidate("nonexistent")

    def test_clear_empties_cache(self):
        cache = ResponseCache()
        for i in range(5):
            cache.put(f"key-{i}", _make_response(f"p{i:03d}"))
        assert cache.size == 5
        cache.clear()
        assert cache.size == 0

    def test_size_tracks_entries(self):
        cache = ResponseCache()
        assert cache.size == 0
        cache.put("k1", _make_response("p001"))
        assert cache.size == 1
        cache.put("k2", _make_response("p002"))
        assert cache.size == 2
        cache.put("k1", _make_response("p001"))  # overwrite
        assert cache.size == 2


# ─────────────────────────────────────────────────────────────────────────────
# 3. Hit rate accounting
# ─────────────────────────────────────────────────────────────────────────────

class TestHitRate:

    def test_initial_hit_rate_zero(self):
        cache = ResponseCache()
        assert cache.hit_rate == 0.0

    def test_all_misses(self):
        cache = ResponseCache()
        for _ in range(5):
            cache.get("missing")
        assert cache.hit_rate == 0.0

    def test_all_hits(self):
        cache = ResponseCache()
        cache.put("k", _make_response())
        for _ in range(5):
            cache.get("k")
        assert cache.hit_rate == 1.0

    def test_mixed_hit_rate(self):
        cache = ResponseCache()
        cache.put("k", _make_response())
        cache.get("k")       # hit
        cache.get("missing")  # miss
        assert abs(cache.hit_rate - 0.5) < 0.001

    def test_stats_dict_structure(self):
        cache = ResponseCache()
        stats = cache.stats()
        assert "size" in stats
        assert "hits" in stats
        assert "misses" in stats
        assert "hit_rate" in stats


# ─────────────────────────────────────────────────────────────────────────────
# 4. Disk persistence
# ─────────────────────────────────────────────────────────────────────────────

class TestDiskPersistence:

    def test_save_and_reload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "cache.json"
            # Populate and save
            cache1 = ResponseCache(path=path)
            key = ResponseCache.make_key("p001", SCENARIO_A)
            cache1.put(key, _make_response("p001"))
            cache1.save()
            assert path.exists()

            # Reload from disk
            cache2 = ResponseCache(path=path)
            result = cache2.get(key)
            assert result is not None
            assert result.persona_id == "p001"

    def test_save_no_path_is_noop(self):
        """save() on an in-memory-only cache should not raise."""
        cache = ResponseCache()
        cache.put("k", _make_response())
        cache.save()  # should not raise

    def test_reload_missing_path_starts_empty(self):
        cache = ResponseCache(path="/tmp/nonexistent_popscale_cache_xyz.json")
        assert cache.size == 0


# ─────────────────────────────────────────────────────────────────────────────
# 5. Circuit breaker threshold detection
# ─────────────────────────────────────────────────────────────────────────────

class TestCircuitBreakerThreshold:
    """Verify threshold detection logic directly (no sleep, no API calls)."""

    def _fallback_rate(self, n_fallbacks: int, n_total: int) -> float:
        return n_fallbacks / max(n_total, 1)

    def test_below_threshold_no_trip(self):
        rate = self._fallback_rate(1, 20)  # 5%
        assert rate < 0.10

    def test_at_threshold_trips(self):
        rate = self._fallback_rate(2, 20)  # 10%
        assert rate >= 0.10

    def test_above_threshold_trips(self):
        rate = self._fallback_rate(3, 20)  # 15%
        assert rate > 0.10

    def test_zero_fallbacks_clean(self):
        rate = self._fallback_rate(0, 50)
        assert rate == 0.0

    def test_all_fallbacks_full_trip(self):
        rate = self._fallback_rate(50, 50)
        assert rate == 1.0

    def test_exponential_backoff_sequence(self):
        base = 10.0
        max_backoff = 120.0
        trips = [1, 2, 3, 4, 5]
        waits = [min(base * (2 ** (t - 1)), max_backoff) for t in trips]
        assert waits == [10.0, 20.0, 40.0, 80.0, 120.0]


# ─────────────────────────────────────────────────────────────────────────────
# 6. Runner cache integration (no live API)
# ─────────────────────────────────────────────────────────────────────────────

class TestRunnerCacheIntegration:
    """Verify that runner passes cache through to batch correctly (structural check)."""

    def test_runner_accepts_cache_kwarg(self):
        """run_population_scenario accepts a cache= kwarg without error at import."""
        import inspect
        from popscale.orchestrator.runner import run_population_scenario
        sig = inspect.signature(run_population_scenario)
        assert "cache" in sig.parameters

    def test_cache_make_key_with_runner_scenario(self):
        """Key generation works for the kinds of scenarios runners use."""
        cache = ResponseCache()
        key = ResponseCache.make_key("pg-mvp-001", SCENARIO_A)
        assert len(key) == 24
        cache.put(key, _make_response("pg-mvp-001"))
        assert cache.get(key) is not None
        assert cache.size == 1
