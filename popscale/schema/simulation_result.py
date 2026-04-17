"""SimulationResult — container for a full PopScale population run.

Every call to run_population_scenario() returns a SimulationResult.
It aggregates all PopulationResponse objects from the population and
carries run metadata (timing, cost, tier, circuit breaker activity).

The analytics layer (Week 3) consumes SimulationResult.responses to
produce segmentation, distributions, driver analysis, and reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from ..scenario.model import Scenario
from .population_response import PopulationResponse


# ── Shard record ──────────────────────────────────────────────────────────────

@dataclass
class ShardRecord:
    """Diagnostic record for a single shard within a population run.

    Shards are processed sequentially by the runner. Each shard runs its
    personas concurrently (bounded by the concurrency parameter).
    """
    shard_index: int
    shard_size: int
    responses_collected: int
    fallback_count: int
    circuit_breaker_tripped: bool = False
    backoff_seconds: float = 0.0

    @property
    def fallback_rate(self) -> float:
        if self.responses_collected == 0:
            return 0.0
        return self.fallback_count / self.responses_collected


# ── SimulationResult ──────────────────────────────────────────────────────────

@dataclass
class SimulationResult:
    """Full results from running a PopScale Scenario against a population.

    Produced by: orchestrator.runner.run_population_scenario()
    Consumed by: analytics layer (Week 3+)

    Attributes:
        run_id:                Unique run identifier (uuid4 hex prefix).
        scenario:              The Scenario that was simulated.
        tier:                  Simulation tier used ("deep" | "signal" | "volume").
        cohort_size:           Number of personas submitted.
        responses:             All PopulationResponse objects, including fallbacks.
        cost_estimate_usd:     Pre-run cost estimate in USD.
        cost_actual_usd:       Post-run cost actuals (estimated from token budgets).
        started_at:            UTC timestamp when run began.
        completed_at:          UTC timestamp when run finished.
        shard_size:            Personas per shard (affects parallelism granularity).
        concurrency:           Max simultaneous LLM calls per shard.
        shards:                Per-shard diagnostic records.
        circuit_breaker_trips: Total number of circuit breaker activations.
    """

    # ── Identity ──────────────────────────────────────────────────────────
    run_id: str
    scenario: Scenario
    tier: str                    # "deep" | "signal" | "volume"

    # ── Population ────────────────────────────────────────────────────────
    cohort_size: int             # Personas submitted (may > len(responses) if aborted)
    responses: list[PopulationResponse]

    # ── Cost ─────────────────────────────────────────────────────────────
    cost_estimate_usd: float
    cost_actual_usd: float       # Estimate used as actual until token tracking lands (Week 4)

    # ── Timing ───────────────────────────────────────────────────────────
    started_at: datetime
    completed_at: datetime

    # ── Run configuration ─────────────────────────────────────────────────
    shard_size: int = 50
    concurrency: int = 20

    # ── Shard diagnostics ─────────────────────────────────────────────────
    shards: list[ShardRecord] = field(default_factory=list)
    circuit_breaker_trips: int = 0

    # ── Derived properties ────────────────────────────────────────────────

    @property
    def duration_seconds(self) -> float:
        return (self.completed_at - self.started_at).total_seconds()

    @property
    def responses_delivered(self) -> int:
        return len(self.responses)

    @property
    def success_count(self) -> int:
        """Responses where the full cognitive loop completed (no fallback)."""
        return sum(
            1 for r in self.responses
            if not r.reasoning_trace.startswith("[FALLBACK]")
        )

    @property
    def fallback_count(self) -> int:
        """Responses where the cognitive loop failed and a fallback was used."""
        return sum(
            1 for r in self.responses
            if r.reasoning_trace.startswith("[FALLBACK]")
        )

    @property
    def success_rate(self) -> float:
        if not self.responses:
            return 0.0
        return self.success_count / len(self.responses)

    @property
    def personas_per_second(self) -> float:
        dur = self.duration_seconds
        if dur <= 0:
            return 0.0
        return self.responses_delivered / dur

    def summary(self) -> str:
        """One-line summary for logging and console output."""
        return (
            f"SimulationResult | run={self.run_id} | "
            f"{self.responses_delivered}/{self.cohort_size} responses | "
            f"success={self.success_rate:.1%} | "
            f"est=${self.cost_estimate_usd:.4f} | "
            f"duration={self.duration_seconds:.1f}s | "
            f"tier={self.tier.upper()} | "
            f"cb_trips={self.circuit_breaker_trips}"
        )

    def to_dict(self) -> dict:
        """Serialisable summary dict for logging and export."""
        return {
            "run_id": self.run_id,
            "scenario_domain": self.scenario.domain.value,
            "scenario_question": self.scenario.question[:120],
            "tier": self.tier,
            "cohort_size": self.cohort_size,
            "responses_delivered": self.responses_delivered,
            "success_count": self.success_count,
            "fallback_count": self.fallback_count,
            "success_rate": round(self.success_rate, 4),
            "cost_estimate_usd": round(self.cost_estimate_usd, 4),
            "cost_actual_usd": round(self.cost_actual_usd, 4),
            "duration_seconds": round(self.duration_seconds, 2),
            "personas_per_second": round(self.personas_per_second, 2),
            "circuit_breaker_trips": self.circuit_breaker_trips,
            "shard_size": self.shard_size,
            "shard_count": len(self.shards),
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
        }
