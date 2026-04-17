"""social_report — assemble analytics into a structured SocialReport.

generate_social_report() runs trajectory analytics on a SocialSimulationResult
and returns a SocialReport with dict and markdown export methods.

Design: mirrors report.py's structure — thin assembly, all computation in
analytics modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..schema.social_simulation_result import SocialSimulationResult
from .trajectory import DriftSummary, InfluenceStats, TrajectoryResult, analyse_trajectory


# ── SocialReport ──────────────────────────────────────────────────────────────

@dataclass
class SocialReport:
    """Structured report for a PopScale social simulation run.

    Attributes:
        run_id:             Run identifier from SocialSimulationResult.
        generated_at:       UTC timestamp of report generation.
        scenario_question:  The question posed.
        scenario_domain:    Domain string.
        scenario_stimuli:   Stimuli broadcast during the run.
        n_personas:         Population size.
        social_level:       SocialSimulationLevel used.
        network_topology:   NetworkTopology used.
        tier:               Simulation tier.
        duration_seconds:   Wall-clock time for the run.
        total_influence_events: Influence events across all turns.
        total_tendency_shifts:  Tendency shifts across all turns.
        trajectory:         Full trajectory analysis.
    """
    run_id: str
    generated_at: datetime
    scenario_question: str
    scenario_domain: str
    scenario_stimuli: list[str]
    n_personas: int
    social_level: str
    network_topology: str
    tier: str
    duration_seconds: float
    total_influence_events: int
    total_tendency_shifts: int
    trajectory: TrajectoryResult

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable report dict."""
        inf = self.trajectory.influence
        drift = self.trajectory.drift
        return {
            "run_id":       self.run_id,
            "generated_at": self.generated_at.isoformat(),
            "scenario": {
                "question": self.scenario_question,
                "domain":   self.scenario_domain,
                "stimuli":  self.scenario_stimuli,
            },
            "run": {
                "n_personas":    self.n_personas,
                "social_level":  self.social_level,
                "topology":      self.network_topology,
                "tier":          self.tier,
                "duration_s":    round(self.duration_seconds, 2),
            },
            "influence": {
                "total_events":             inf.total_influence_events,
                "network_density":          inf.network_density,
                "mean_events_transmitted":  inf.mean_events_transmitted,
                "mean_events_received":     inf.mean_events_received,
                "mean_importance_tx":       inf.mean_importance_transmitted,
                "mean_importance_rx":       inf.mean_importance_received,
                "top_transmitters": [
                    {
                        "persona_id": h.persona_id,
                        "events_transmitted": h.events_transmitted,
                        "importance_transmitted": h.importance_transmitted,
                    }
                    for h in inf.top_transmitters
                ],
                "top_receivers": [
                    {
                        "persona_id": h.persona_id,
                        "events_received": h.events_received,
                        "importance_received": h.importance_received,
                    }
                    for h in inf.top_receivers
                ],
            },
            "drift": {
                "total_shifts":      drift.total_shifts,
                "personas_shifted":  drift.personas_shifted,
                "has_drift":         drift.has_drift,
                "most_drifted_fields": [
                    {"field": e.field, "shift_count": e.shift_count}
                    for e in drift.most_drifted_fields
                ],
            },
        }

    def to_markdown(self) -> str:
        """Human-readable markdown report for a social simulation run."""
        lines: list[str] = []
        inf   = self.trajectory.influence
        drift = self.trajectory.drift

        domain_label = self.scenario_domain.replace("_", " ").title()

        lines += [
            f"# PopScale Social Report — {domain_label} Scenario",
            "",
            f"**Run ID**: `{self.run_id}`  ",
            f"**Generated**: {self.generated_at.strftime('%Y-%m-%d %H:%M UTC')}  ",
            f"**Tier**: {self.tier.upper()}  ",
            f"**Duration**: {self.duration_seconds:.1f}s",
            "",
            "---",
            "",
            "## Scenario",
            "",
            f"> {self.scenario_question}",
            "",
        ]

        if self.scenario_stimuli:
            lines += ["**Stimuli broadcast:**", ""]
            for s in self.scenario_stimuli:
                lines.append(f"- {s[:200]}")
            lines.append("")

        lines += [
            "---",
            "",
            "## Run Configuration",
            "",
            f"| | |",
            f"|---|---|",
            f"| Personas | {self.n_personas} |",
            f"| Social level | {self.social_level.upper()} |",
            f"| Network topology | {self.network_topology.replace('_', ' ').title()} |",
            f"| Tier | {self.tier.upper()} |",
            "",
        ]

        # ── Influence ─────────────────────────────────────────────────────
        lines += [
            "---",
            "",
            "## Influence Flow",
            "",
            f"| Metric | Value |",
            f"|--------|------:|",
            f"| Total influence events | {inf.total_influence_events} |",
            f"| Network density | {inf.network_density:.2%} |",
            f"| Avg events transmitted / persona | {inf.mean_events_transmitted:.1f} |",
            f"| Avg events received / persona | {inf.mean_events_received:.1f} |",
            f"| Avg gated importance (tx) | {inf.mean_importance_transmitted:.3f} |",
            f"| Avg gated importance (rx) | {inf.mean_importance_received:.3f} |",
            "",
        ]

        if inf.top_transmitters:
            lines += ["**Top influence transmitters:**", ""]
            for h in inf.top_transmitters:
                lines.append(
                    f"- `{h.persona_id}` — {h.events_transmitted} events "
                    f"(importance: {h.importance_transmitted:.3f})"
                )
            lines.append("")

        if inf.top_receivers:
            lines += ["**Top influence receivers:**", ""]
            for h in inf.top_receivers:
                lines.append(
                    f"- `{h.persona_id}` — {h.events_received} events "
                    f"(importance: {h.importance_received:.3f})"
                )
            lines.append("")

        # ── Drift ─────────────────────────────────────────────────────────
        lines += [
            "---",
            "",
            "## Tendency Drift",
            "",
        ]

        if drift.has_drift:
            lines += [
                f"**{drift.total_shifts}** tendency shift(s) across "
                f"**{drift.personas_shifted}** persona(s).",
                "",
            ]
            if drift.most_drifted_fields:
                lines += [
                    "| Field | Shifts |",
                    "|-------|-------:|",
                ]
                for e in drift.most_drifted_fields:
                    lines.append(f"| {e.field} | {e.shift_count} |")
                lines.append("")
        else:
            lines += [
                "*No tendency drift detected. This is expected at LOW or MODERATE "
                "social simulation levels, or when influence events do not "
                "exceed persona conviction thresholds.*",
                "",
            ]

        # ── Footer ────────────────────────────────────────────────────────
        lines += [
            "---",
            "",
            f"*Generated by PopScale Social · run `{self.run_id}` · "
            f"{self.scenario_domain.upper()} domain · "
            f"{self.social_level.upper()} social level*",
        ]

        return "\n".join(lines)


# ── Public API ────────────────────────────────────────────────────────────────

def generate_social_report(result: SocialSimulationResult) -> SocialReport:
    """Run trajectory analytics and return a SocialReport.

    Args:
        result: A completed SocialSimulationResult from run_social_scenario().

    Returns:
        SocialReport with full analytics, dict export, and markdown export.
    """
    trajectory = analyse_trajectory(result.trace, result.cohort_size)

    return SocialReport(
        run_id=result.run_id,
        generated_at=datetime.now(timezone.utc),
        scenario_question=result.scenario_question,
        scenario_domain=result.scenario_domain,
        scenario_stimuli=result.scenario_stimuli,
        n_personas=result.cohort_size,
        social_level=result.social_level,
        network_topology=result.network_topology,
        tier=result.tier,
        duration_seconds=result.duration_seconds,
        total_influence_events=result.total_influence_events,
        total_tendency_shifts=result.total_tendency_shifts,
        trajectory=trajectory,
    )
