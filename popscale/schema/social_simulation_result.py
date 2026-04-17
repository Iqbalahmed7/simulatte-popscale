"""social_simulation_result — result schema for PopScale social runs.

Wraps PG's (personas_after, SocialSimulationTrace) tuple in a richer
PopScale-native container that carries the original personas, scenario,
timing, and cost alongside the trace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Imported at runtime in social_runner; kept here as TYPE_CHECKING only
    # to avoid circular imports at import time.
    pass


@dataclass
class SocialSimulationResult:
    """Output of run_social_scenario().

    Attributes:
        run_id:            Unique identifier for this run.
        scenario_question: The question posed (from Scenario.question).
        scenario_domain:   Domain string (from Scenario.domain.value).
        scenario_stimuli:  Stimuli passed to run_social_loop().
        tier:              Simulation tier used (DEEP / VOLUME / etc.).
        cohort_size:       Number of personas in the population.
        personas_before:   Original PersonaRecord list (pre-social-loop).
        personas_after:    Updated PersonaRecord list (post-social-loop).
        trace:             PG's SocialSimulationTrace (raw output).
        network_topology:  Topology enum value string.
        social_level:      SocialSimulationLevel enum value string.
        started_at:        UTC datetime when the run began.
        completed_at:      UTC datetime when the run finished.
    """

    run_id: str
    scenario_question: str
    scenario_domain: str
    scenario_stimuli: list[str]
    tier: str
    cohort_size: int
    personas_before: list[Any]    # list[PersonaRecord] — Any to avoid PG import at module level
    personas_after:  list[Any]    # list[PersonaRecord]
    trace:           Any          # SocialSimulationTrace
    network_topology: str
    social_level: str
    started_at:  datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def duration_seconds(self) -> float:
        return (self.completed_at - self.started_at).total_seconds()

    @property
    def total_influence_events(self) -> int:
        return self.trace.total_influence_events

    @property
    def total_tendency_shifts(self) -> int:
        return len(self.trace.tendency_shift_log)

    def summary(self) -> str:
        return (
            f"SocialRun {self.run_id} | {self.cohort_size} personas | "
            f"level={self.social_level} | topology={self.network_topology} | "
            f"influence_events={self.total_influence_events} | "
            f"tendency_shifts={self.total_tendency_shifts} | "
            f"duration={self.duration_seconds:.1f}s"
        )
