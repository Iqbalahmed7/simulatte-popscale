"""report — assemble analytics results into a structured PopScaleReport.

generate_report() orchestrates the full analytics pipeline:
    segmentation → distributions → drivers → surprises → report

Output formats:
    .to_dict()     — JSON-serialisable dict for API and storage
    .to_markdown() — Human-readable report for Slack, Notion, email

Design principle: the report is a thin assembly layer. All computation
happens in the four analytics modules. report.py only formats.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..scenario.model import Scenario
from ..schema.simulation_result import SimulationResult
from .distributions import DistributionResult, compute_distributions
from .drivers import DriverAnalysisResult, analyse_drivers
from .segmentation import SegmentationResult, segment_population
from .surprises import SurpriseResult, detect_surprises


# ── PopScaleReport ────────────────────────────────────────────────────────────

@dataclass
class PopScaleReport:
    """Structured analytical report for a PopScale population run.

    Attributes:
        run_id:         Run identifier from SimulationResult.
        generated_at:   UTC timestamp of report generation.
        scenario:       The Scenario that was simulated.
        n_personas:     Total personas in the population.
        n_successful:   Personas that completed the full cognitive loop.
        tier:           Simulation tier used.
        cost_usd:       Estimated simulation cost.
        segmentation:   Decision segment profiles.
        distributions:  Option probability distributions with CIs.
        drivers:        Key driver effect size analysis.
        surprises:      Surprising findings vs. behavioral prior.
    """
    run_id: str
    generated_at: datetime
    scenario: Scenario
    n_personas: int
    n_successful: int
    tier: str
    cost_usd: float
    segmentation: SegmentationResult
    distributions: DistributionResult
    drivers: DriverAnalysisResult
    surprises: SurpriseResult

    @property
    def success_rate(self) -> float:
        return self.n_successful / self.n_personas if self.n_personas else 0.0

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable report dict."""
        return {
            "run_id":        self.run_id,
            "generated_at":  self.generated_at.isoformat(),
            "scenario": {
                "domain":   self.scenario.domain.value,
                "question": self.scenario.question,
                "options":  self.scenario.options,
            },
            "population": {
                "n_personas":   self.n_personas,
                "n_successful": self.n_successful,
                "success_rate": round(self.success_rate, 4),
                "tier":         self.tier,
                "cost_usd":     round(self.cost_usd, 4),
            },
            "distributions": _distributions_dict(self.distributions),
            "segments":      _segments_dict(self.segmentation),
            "drivers":       _drivers_dict(self.drivers),
            "surprises":     _surprises_dict(self.surprises),
        }

    def to_markdown(self) -> str:
        """Human-readable markdown report."""
        lines: list[str] = []

        # ── Header ──────────────────────────────────────────────────────
        domain_label = self.scenario.domain.value.title()
        lines += [
            f"# PopScale Report — {domain_label} Scenario",
            "",
            f"**Run ID**: `{self.run_id}`  ",
            f"**Generated**: {self.generated_at.strftime('%Y-%m-%d %H:%M UTC')}  ",
            f"**Tier**: {self.tier.upper()}  ",
            f"**Cost**: ~${self.cost_usd:.4f}",
            "",
            "---",
            "",
            "## Scenario",
            "",
            f"> {self.scenario.question}",
            "",
        ]
        if self.scenario.context:
            lines += [f"{self.scenario.context[:300]}{'…' if len(self.scenario.context) > 300 else ''}", ""]

        lines += [
            "---",
            "",
            "## Population",
            "",
            f"| | |",
            f"|---|---|",
            f"| Personas | {self.n_personas} |",
            f"| Completed cognitive loop | {self.n_successful} ({self.success_rate:.0%}) |",
            f"| Unclassified responses | {self.distributions.n_unclassified} |",
            "",
        ]

        # ── Decision distribution ────────────────────────────────────────
        lines += ["---", "", "## Decision Distribution", ""]

        if self.distributions.is_choice_scenario:
            lines += [
                "| Option | Count | % | 95% CI |",
                "|--------|------:|--:|--------|",
            ]
            for opt in self.distributions.options:
                bar = _bar(opt.proportion)
                ci = f"{opt.ci_lower:.0%} – {opt.ci_upper:.0%}"
                lines.append(
                    f"| {opt.option[:55]} | {opt.count} | {opt.proportion:.0%} {bar} | {ci} |"
                )
            lines.append("")
            if self.distributions.leading_option:
                lo = self.distributions.leading_option
                lines += [
                    f"**Leading option**: {lo.option[:60]} ({lo.proportion:.0%}, "
                    f"avg confidence {lo.avg_confidence:.0%})",
                    "",
                ]
        else:
            lines += [
                "| Sentiment | Count | % | 95% CI |",
                "|-----------|------:|--:|--------|",
            ]
            for band in self.distributions.sentiment:
                bar = _bar(band.proportion)
                ci = f"{band.ci_lower:.0%} – {band.ci_upper:.0%}"
                lines.append(
                    f"| {band.label.title()} | {band.count} | {band.proportion:.0%} {bar} | {ci} |"
                )
            lines.append("")

        lines += [
            f"*Median confidence: {self.distributions.median_confidence:.0%} · "
            f"Median emotional valence: {self.distributions.median_valence:+.2f}*",
            "",
        ]

        # ── Segments ─────────────────────────────────────────────────────
        lines += ["---", "", "## Segments", ""]
        for i, seg in enumerate(self.segmentation.segments, 1):
            if seg.count == 0:
                continue
            lines += [
                f"### {i}. {seg.label} — {seg.count} persona{'s' if seg.count != 1 else ''} ({seg.share:.0%})",
                "",
                f"- Avg confidence: {seg.avg_confidence:.0%}",
                f"- Avg emotional valence: {seg.avg_emotional_valence:+.2f}",
            ]
            # Trait profile — show dominant value for each trait
            tp = seg.trait_profile
            for attr_name, counts in [
                ("Risk appetite", tp.risk_appetite),
                ("Trust anchor",  tp.trust_anchor),
                ("Decision style", tp.decision_style),
            ]:
                if counts:
                    dominant = max(counts, key=counts.__getitem__)
                    lines.append(f"- {attr_name}: {dominant} ({counts[dominant]}/{seg.count})")
            if seg.representative_drivers:
                drivers_str = ", ".join(seg.representative_drivers)
                lines.append(f"- Top drivers: {drivers_str}")
            lines.append("")

        # ── Key drivers ───────────────────────────────────────────────────
        lines += ["---", "", "## Key Drivers", ""]

        if self.drivers.directional_only:
            lines += [
                f"> ⚠️ **Directional only** — N={self.drivers.n_personas} "
                f"(reliable driver analysis requires N ≥ 30)",
                "",
            ]

        if self.drivers.top_drivers:
            lines += [
                "| Attribute | Effect Size | Method | Interpretation |",
                "|-----------|------------:|--------|----------------|",
            ]
            for d in self.drivers.top_drivers:
                method_label = "Cramér's V" if d.method == "cramers_v" else "Eta²"
                lines.append(
                    f"| {d.attribute} | {d.effect_size:.3f} | {method_label} | {d.interpretation} |"
                )
            lines.append("")
        else:
            lines += ["*No attributes reached the significance threshold (≥ 0.10).*", ""]

        if self.drivers.n_significant == 0 and not self.drivers.directional_only:
            lines += [
                "*This may indicate that outcomes are driven by scenario-specific reasoning "
                "rather than stable persona traits — a finding in itself.*",
                "",
            ]

        # ── Surprises ─────────────────────────────────────────────────────
        lines += ["---", "", "## Surprise Findings", ""]

        if self.surprises.has_surprises:
            for i, finding in enumerate(self.surprises.findings, 1):
                severity_icon = {"counterintuitive": "🔴", "striking": "🟠", "notable": "🟡"}.get(
                    finding.severity, "🟡"
                )
                lines += [
                    f"### {i}. {severity_icon} {finding.finding_type.replace('_', ' ').title()} "
                    f"({finding.severity})",
                    "",
                    finding.description,
                    "",
                    f"*Actual: {finding.actual_pct:.0f}% · Expected: {finding.expected_pct:.0f}% "
                    f"· Deviation: {finding.deviation_pp:.0f}pp*",
                    "",
                ]
        else:
            lines += [
                "*No surprises detected — the population responded broadly as the "
                "behavioral prior predicted.*",
                "",
            ]

        # ── Prior vs actual comparison table ──────────────────────────────
        if self.surprises.prior_distribution:
            lines += ["**Prior vs. actual distribution:**", ""]
            lines += ["| Option | Prior (expected) | Actual |", "|--------|-----------------|--------|"]
            for key in sorted(self.surprises.prior_distribution):
                prior_pct = self.surprises.prior_distribution.get(key, 0.0)
                actual_pct = self.surprises.actual_distribution.get(key, 0.0)
                opt_label = key.split(":", 1)[1] if ":" in key else key
                lines.append(f"| {opt_label[:40]} | {prior_pct:.0f}% | {actual_pct:.0f}% |")
            lines.append("")

        # ── Footer ────────────────────────────────────────────────────────
        lines += [
            "---",
            "",
            f"*Generated by PopScale · run `{self.run_id}` · "
            f"{self.scenario.domain.value.upper()} domain · "
            f"{self.tier.upper()} tier*",
        ]

        return "\n".join(lines)


# ── Public API ────────────────────────────────────────────────────────────────

def generate_report(result: SimulationResult) -> PopScaleReport:
    """Run the full analytics pipeline and return a PopScaleReport.

    Orchestrates: segmentation → distributions → drivers → surprises.

    Args:
        result: A completed SimulationResult from run_population_scenario().

    Returns:
        PopScaleReport with full analytics, dict export, and markdown export.
    """
    responses = result.responses
    scenario  = result.scenario

    segmentation  = segment_population(responses, scenario)
    distributions = compute_distributions(responses, scenario)
    drivers       = analyse_drivers(responses, scenario)
    surprises     = detect_surprises(responses, scenario, segmentation, distributions)

    return PopScaleReport(
        run_id=result.run_id,
        generated_at=datetime.now(timezone.utc),
        scenario=scenario,
        n_personas=result.cohort_size,
        n_successful=result.success_count,
        tier=result.tier,
        cost_usd=result.cost_actual_usd,
        segmentation=segmentation,
        distributions=distributions,
        drivers=drivers,
        surprises=surprises,
    )


# ── Formatters ────────────────────────────────────────────────────────────────

def _bar(proportion: float, width: int = 10) -> str:
    """ASCII progress bar for proportion display."""
    filled = round(proportion * width)
    return "█" * filled + "░" * (width - filled)


def _distributions_dict(d: DistributionResult) -> dict:
    out: dict = {
        "is_choice_scenario": d.is_choice_scenario,
        "n_total": d.n_total,
        "n_unclassified": d.n_unclassified,
        "median_confidence": d.median_confidence,
        "median_valence": d.median_valence,
        "mean_confidence": d.mean_confidence,
        "mean_valence": d.mean_valence,
    }
    if d.is_choice_scenario:
        out["options"] = [
            {
                "option": o.option,
                "count": o.count,
                "proportion": o.proportion,
                "ci_lower": o.ci_lower,
                "ci_upper": o.ci_upper,
                "avg_confidence": o.avg_confidence,
            }
            for o in d.options
        ]
    else:
        out["sentiment"] = [
            {"label": s.label, "count": s.count, "proportion": s.proportion,
             "ci_lower": s.ci_lower, "ci_upper": s.ci_upper}
            for s in d.sentiment
        ]
    return out


def _segments_dict(s: SegmentationResult) -> dict:
    return {
        "is_choice_scenario": s.is_choice_scenario,
        "n_total": s.n_total,
        "unclassified_count": s.unclassified_count,
        "dominant_segment": s.dominant_segment.label if s.dominant_segment else None,
        "segments": [
            {
                "label": seg.label,
                "option_index": seg.option_index,
                "count": seg.count,
                "share": seg.share,
                "avg_confidence": seg.avg_confidence,
                "avg_emotional_valence": seg.avg_emotional_valence,
                "representative_drivers": seg.representative_drivers,
                "trait_profile": {
                    "risk_appetite": seg.trait_profile.risk_appetite,
                    "trust_anchor":  seg.trait_profile.trust_anchor,
                    "decision_style": seg.trait_profile.decision_style,
                },
            }
            for seg in s.segments
        ],
    }


def _drivers_dict(d: DriverAnalysisResult) -> dict:
    return {
        "n_personas": d.n_personas,
        "n_tested": d.n_tested,
        "n_significant": d.n_significant,
        "directional_only": d.directional_only,
        "top_drivers": [
            {
                "attribute": e.attribute,
                "effect_size": e.effect_size,
                "method": e.method,
                "interpretation": e.interpretation,
            }
            for e in d.top_drivers
        ],
    }


def _surprises_dict(s: SurpriseResult) -> dict:
    return {
        "has_surprises": s.has_surprises,
        "n_findings": len(s.findings),
        "prior_distribution": s.prior_distribution,
        "actual_distribution": s.actual_distribution,
        "findings": [
            {
                "type": f.finding_type,
                "description": f.description,
                "actual_pct": f.actual_pct,
                "expected_pct": f.expected_pct,
                "deviation_pp": f.deviation_pp,
                "severity": f.severity,
            }
            for f in s.findings
        ],
    }
