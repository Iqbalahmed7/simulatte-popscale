"""
bias_decomposition.py — BRIEF-020: Bias decomposition for calibration.

API
---
    report = decompose_bias(backtest_result, persona_data_path)

Slices BacktestResult.per_unit_errors along four axes:
  1. Demographic   — any categorical attribute on personas (e.g. religion, caste)
  2. Region        — cluster_id (unit_id in BacktestResult)
  3. Confidence    — "high_conf" (≥0.60) vs "low_conf" (<0.60) persona decisions
  4. Unit-level    — top-10 largest per-unit errors

Uses metrics.mae_vote_share under the hood for slice-level MAE.

Persona data format (JSON)
--------------------------
The file at persona_data_path must contain a list of persona records:

    [
        {
            "persona_id": "p001",
            "cluster_id": "murshidabad",
            "confidence": 0.72,
            "religion": "muslim",
            "caste": "obc",
            ...
        },
        ...
    ]

Fields `cluster_id` and `confidence` are the minimum required for decomposition.
Any additional string fields (e.g. religion, caste, gender) become demographic axes.
Records missing `cluster_id` are skipped.  Missing `confidence` defaults to 0.0.

If persona_data_path does not exist or the file is empty / contains no usable
records, all demographic / confidence decompositions return empty dicts and
`largest_errors` falls back to per_unit_errors from the BacktestResult directly.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .harness import BacktestResult
from .metrics import mae_vote_share

logger = logging.getLogger(__name__)

# Confidence threshold separating high from low confidence bands
_HIGH_CONF_THRESHOLD = 0.60

# Axes to skip when collecting demographic dimensions from persona records
_NON_DEMOGRAPHIC_KEYS = frozenset(
    {"persona_id", "cluster_id", "confidence", "decision", "reasoning_trace",
     "gut_reaction", "key_drivers", "objections", "what_would_change_mind",
     "emotional_valence"}
)


# ---------------------------------------------------------------------------
# BiasReport dataclass
# ---------------------------------------------------------------------------

@dataclass
class BiasReport:
    """Structured decomposition of backcasting error across multiple axes.

    All MAE values are in percentage points (0-100 scale), matching
    BacktestResult.per_unit_errors.
    """

    overall_mae: float
    """Copied from BacktestResult.overall_mae."""

    by_demographic: dict[str, dict[str, float]]
    """{axis: {cell_value: mae_pp}}  e.g. {"religion": {"hindu": 1.2, "muslim": 4.5}}"""

    by_region: dict[str, float]
    """{cluster_id: mae_pp}  — directly from BacktestResult.per_unit_errors."""

    by_confidence_band: dict[str, float]
    """{"high_conf": mae_pp, "low_conf": mae_pp}  split at 0.60 threshold."""

    largest_errors: list[tuple[str, float]]
    """Top-10 (unit_id, mae_pp) tuples sorted largest first."""

    recommendations: list[str]
    """Human-readable next-step suggestions derived from the decomposition."""

    def to_markdown(self) -> str:
        """Render the report as a Markdown string with tables."""
        lines: list[str] = []

        lines.append("# Bias Decomposition Report\n")
        lines.append(f"**Overall MAE:** {self.overall_mae:.2f} pp\n")

        # --- by_region ---
        lines.append("## Error by Region (Cluster)\n")
        if self.by_region:
            lines.append("| Cluster | MAE (pp) |")
            lines.append("|---------|---------|")
            for cluster_id, mae in sorted(
                self.by_region.items(), key=lambda x: x[1], reverse=True
            ):
                lines.append(f"| {cluster_id} | {mae:.2f} |")
        else:
            lines.append("_No region data available._")
        lines.append("")

        # --- by_demographic ---
        lines.append("## Error by Demographic\n")
        if self.by_demographic:
            for axis, cells in sorted(self.by_demographic.items()):
                lines.append(f"### {axis.capitalize()}\n")
                lines.append("| Cell | MAE (pp) |")
                lines.append("|------|---------|")
                for cell, mae in sorted(cells.items(), key=lambda x: x[1], reverse=True):
                    lines.append(f"| {cell} | {mae:.2f} |")
                lines.append("")
        else:
            lines.append("_No demographic data available._\n")

        # --- by_confidence_band ---
        lines.append("## Error by Confidence Band\n")
        if self.by_confidence_band:
            lines.append("| Band | MAE (pp) |")
            lines.append("|------|---------|")
            high = self.by_confidence_band.get("high_conf")
            low = self.by_confidence_band.get("low_conf")
            if high is not None:
                lines.append(f"| high_conf (≥{_HIGH_CONF_THRESHOLD:.0%}) | {high:.2f} |")
            if low is not None:
                lines.append(f"| low_conf (<{_HIGH_CONF_THRESHOLD:.0%}) | {low:.2f} |")
        else:
            lines.append("_No confidence data available._")
        lines.append("")

        # --- largest_errors ---
        lines.append("## Largest Unit-Level Errors (Top 10)\n")
        if self.largest_errors:
            lines.append("| Unit | MAE (pp) |")
            lines.append("|------|---------|")
            for unit_id, mae in self.largest_errors:
                lines.append(f"| {unit_id} | {mae:.2f} |")
        else:
            lines.append("_No unit errors available._")
        lines.append("")

        # --- recommendations ---
        lines.append("## Recommendations\n")
        if self.recommendations:
            for rec in self.recommendations:
                lines.append(f"- {rec}")
        else:
            lines.append("_No recommendations generated._")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Persona data loading
# ---------------------------------------------------------------------------

def _load_persona_records(persona_data_path: Path) -> list[dict]:
    """Load persona records from a JSON file.

    Returns an empty list on any error (missing file, bad JSON, wrong shape).
    """
    if not persona_data_path.exists():
        logger.warning(
            "bias_decomposition: persona_data_path not found: %s — "
            "demographic/confidence decompositions will be empty.",
            persona_data_path,
        )
        return []

    try:
        with persona_data_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(
            "bias_decomposition: could not parse %s (%s) — "
            "demographic/confidence decompositions will be empty.",
            persona_data_path,
            exc,
        )
        return []

    if not isinstance(data, list):
        logger.warning(
            "bias_decomposition: %s top-level value is %s, expected list — "
            "demographic/confidence decompositions will be empty.",
            persona_data_path,
            type(data).__name__,
        )
        return []

    return [r for r in data if isinstance(r, dict) and r.get("cluster_id")]


# ---------------------------------------------------------------------------
# Decomposition helpers
# ---------------------------------------------------------------------------

def _decompose_by_region(per_unit_errors: dict[str, float]) -> dict[str, float]:
    """Region decomposition is just per_unit_errors — cluster_id IS the unit."""
    return dict(per_unit_errors)


def _decompose_by_demographic(
    per_unit_errors: dict[str, float],
    persona_records: list[dict],
) -> dict[str, dict[str, float]]:
    """Slice per_unit_errors by demographic axes present in persona_records.

    Strategy:
    - Collect all string-valued fields that are not in _NON_DEMOGRAPHIC_KEYS.
    - For each axis and cell value, gather the MAEs of clusters that contain
      personas with that cell value (weighted by persona count, not seat count).
    - Return {axis: {cell: mean_mae}} — missing cells produce 0.0 entries only
      when there is at least one persona in that cell.
    """
    if not persona_records:
        return {}

    # Discover demographic axes from all records
    axes: set[str] = set()
    for record in persona_records:
        for key, val in record.items():
            if key not in _NON_DEMOGRAPHIC_KEYS and isinstance(val, str):
                axes.add(key)

    if not axes:
        return {}

    result: dict[str, dict[str, float]] = {}

    for axis in sorted(axes):
        # Build {cell_value: [mae, ...]} where mae comes from the cluster_id of
        # each persona that carries this cell value
        cell_maes: dict[str, list[float]] = {}
        for record in persona_records:
            cell_val = record.get(axis)
            if not isinstance(cell_val, str) or not cell_val:
                continue
            cluster_id = record["cluster_id"]
            mae = per_unit_errors.get(cluster_id)
            if mae is None:
                continue
            cell_maes.setdefault(cell_val, []).append(mae)

        if not cell_maes:
            continue

        result[axis] = {
            cell: sum(maes) / len(maes)
            for cell, maes in cell_maes.items()
        }

    return result


def _decompose_by_confidence_band(
    per_unit_errors: dict[str, float],
    persona_records: list[dict],
) -> dict[str, float]:
    """Split per_unit_errors into high/low confidence bands.

    A cluster is assigned to a band based on the *mean* confidence of its
    personas.  Clusters with no associated personas are excluded.

    Threshold: confidence ≥ HIGH_CONF_THRESHOLD → "high_conf", else "low_conf".
    """
    if not persona_records:
        return {}

    # Compute mean confidence per cluster
    cluster_conf_sum: dict[str, float] = {}
    cluster_conf_count: dict[str, int] = {}
    for record in persona_records:
        cluster_id = record["cluster_id"]
        conf = float(record.get("confidence") or 0.0)
        cluster_conf_sum[cluster_id] = cluster_conf_sum.get(cluster_id, 0.0) + conf
        cluster_conf_count[cluster_id] = cluster_conf_count.get(cluster_id, 0) + 1

    high_maes: list[float] = []
    low_maes: list[float] = []

    for cluster_id, mae in per_unit_errors.items():
        count = cluster_conf_count.get(cluster_id, 0)
        if count == 0:
            continue
        mean_conf = cluster_conf_sum[cluster_id] / count
        if mean_conf >= _HIGH_CONF_THRESHOLD:
            high_maes.append(mae)
        else:
            low_maes.append(mae)

    bands: dict[str, float] = {}
    if high_maes:
        bands["high_conf"] = sum(high_maes) / len(high_maes)
    if low_maes:
        bands["low_conf"] = sum(low_maes) / len(low_maes)
    return bands


def _top_unit_errors(
    per_unit_errors: dict[str, float],
    n: int = 10,
) -> list[tuple[str, float]]:
    """Return top-N (unit_id, mae) tuples sorted by mae descending."""
    return sorted(per_unit_errors.items(), key=lambda x: x[1], reverse=True)[:n]


# ---------------------------------------------------------------------------
# Recommendation generation
# ---------------------------------------------------------------------------

def _generate_recommendations(
    overall_mae: float,
    by_demographic: dict[str, dict[str, float]],
    by_confidence_band: dict[str, float],
    largest_errors: list[tuple[str, float]],
) -> list[str]:
    """Generate human-readable recommendations from decomposition results."""
    recs: list[str] = []

    # Demographic outliers — flag axes where max cell > 2× min cell (or > 3pp spread)
    for axis, cells in by_demographic.items():
        if len(cells) < 2:
            continue
        sorted_cells = sorted(cells.items(), key=lambda x: x[1], reverse=True)
        worst_cell, worst_mae = sorted_cells[0]
        best_cell, best_mae = sorted_cells[-1]
        spread = worst_mae - best_mae
        if spread >= 2.0:
            recs.append(
                f"{axis.capitalize()} '{worst_cell}' shows {worst_mae:.1f}pp MAE "
                f"vs '{best_cell}' {best_mae:.1f}pp "
                f"(spread {spread:.1f}pp) — investigate {worst_cell} priors"
            )

    # Confidence band gap
    high_conf = by_confidence_band.get("high_conf")
    low_conf = by_confidence_band.get("low_conf")
    if high_conf is not None and low_conf is not None:
        conf_gap = low_conf - high_conf
        if conf_gap > 0:
            recs.append(
                f"Low-confidence predictions (<{_HIGH_CONF_THRESHOLD:.0%}) average "
                f"{low_conf:.1f}pp MAE vs high-confidence {high_conf:.1f}pp "
                f"— consider flagging these for re-run"
            )
    elif low_conf is not None and high_conf is None:
        recs.append(
            f"All clusters fall below {_HIGH_CONF_THRESHOLD:.0%} confidence "
            f"(avg MAE {low_conf:.1f}pp) — review persona confidence calibration"
        )

    # Worst unit-level cluster
    if largest_errors:
        worst_unit, worst_unit_mae = largest_errors[0]
        if worst_unit_mae > overall_mae * 1.5:
            recs.append(
                f"Cluster '{worst_unit}' has the largest error at {worst_unit_mae:.1f}pp "
                f"({worst_unit_mae / overall_mae:.1f}× overall MAE) "
                f"— prioritise for next calibration iteration"
            )

    # Overall MAE health
    if overall_mae < 3.0:
        recs.append(
            f"Overall MAE {overall_mae:.2f}pp is within the <3pp target — "
            "no urgent recalibration needed"
        )
    elif overall_mae < 8.0:
        recs.append(
            f"Overall MAE {overall_mae:.2f}pp exceeds the 3pp target — "
            "calibration loop (BRIEF-021) recommended"
        )
    else:
        recs.append(
            f"Overall MAE {overall_mae:.2f}pp is high — systematic prior review required "
            "before the next benchmark run"
        )

    return recs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def decompose_bias(
    backtest: BacktestResult,
    persona_data_path: Path,
) -> BiasReport:
    """Decompose backcasting error into demographic, regional, and confidence slices.

    This is a pure analysis function — it never re-runs the engine.

    Args:
        backtest: Completed BacktestResult from harness.backcast().
        persona_data_path: Path to a JSON file containing persona records.
            Each record must have at minimum a "cluster_id" string field.
            Optional fields: "confidence" (float 0-1), plus any demographic
            string fields (e.g. "religion", "caste", "gender").

    Returns:
        BiasReport with overall_mae, by_demographic, by_region,
        by_confidence_band, largest_errors, and recommendations.
    """
    persona_records = _load_persona_records(persona_data_path)

    by_region = _decompose_by_region(backtest.per_unit_errors)

    by_demographic = _decompose_by_demographic(
        backtest.per_unit_errors, persona_records
    )

    by_confidence_band = _decompose_by_confidence_band(
        backtest.per_unit_errors, persona_records
    )

    largest_errors = _top_unit_errors(backtest.per_unit_errors)

    recommendations = _generate_recommendations(
        overall_mae=backtest.overall_mae,
        by_demographic=by_demographic,
        by_confidence_band=by_confidence_band,
        largest_errors=largest_errors,
    )

    return BiasReport(
        overall_mae=backtest.overall_mae,
        by_demographic=by_demographic,
        by_region=by_region,
        by_confidence_band=by_confidence_band,
        largest_errors=largest_errors,
        recommendations=recommendations,
    )
