"""
harness.py — backcasting entry point for Phase 3 calibration.

Main API
--------
    result = await backcast("wb_2021_assembly", use_existing_run="path/to/run.json")

The function loads ground truth via BRIEF-017 loaders, extracts engine predictions
from a saved run JSON (or runs the engine live — live running deferred to BRIEF-021),
normalises both sides to a common scale and party-key space, then scores.

Aggregation direction
---------------------
When engine output is cluster-level and GT is constituency-level (WB case), the
GT is aggregated *up* to cluster granularity via aggregate_to_clusters().  The
engine never disaggregates; we always aggregate the finer-grained side.

Coverage
--------
If the engine produced N clusters but GT has M units (N << M), coverage_pct is
N/M and MAE is computed only over the N predicted units.  The harness does not
fail — it reports what it has.

Scale convention
----------------
All scores in BacktestResult.ground_truth and .predicted are in percentage
(0–100), matching GroundTruthUnit.outcomes.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .loaders import load_ground_truth
from .scoring import (
    normalise_gt_outcomes,
    normalise_engine_shares,
    compute_mae,
    compute_brier,
    compute_directional_accuracy,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class BacktestResult:
    """Output of backcast().  All vote shares in percentage (0-100)."""

    election_id: str
    engine_run_id: str

    # {unit_id: {party_key: pct}}  — canonical comparison form, 0-100 scale
    ground_truth: dict[str, dict[str, float]]
    predicted: dict[str, dict[str, float]]

    overall_mae: float
    """Mean absolute error in percentage points, averaged over predicted units."""

    per_unit_errors: dict[str, float]
    """MAE per predicted unit (percentage points)."""

    brier_score: float
    """Mean Brier score over predicted units (lower is better)."""

    directional_accuracy: float
    """Fraction of units where winner was predicted correctly (0.0–1.0)."""

    coverage_pct: float
    """Fraction of GT units covered by engine predictions (0.0–1.0)."""

    metadata: dict = field(default_factory=dict)
    """Tier, run_date, cluster_count, gt_unit_count, etc."""


# ---------------------------------------------------------------------------
# Run JSON parsers
# ---------------------------------------------------------------------------

def _parse_wb_constituency_run(
    run_data: dict,
    election_id: str,
) -> tuple[str, dict[str, dict[str, float]]]:
    """Parse a WB constituency benchmark run JSON into engine predictions.

    Returns:
        (run_id, {cluster_id: {gt_party_key: pct_0_to_100}})

    The WB run JSON has a 'cluster_results' list where each entry has fields:
        id, sim_tmc, sim_bjp, sim_left, sim_others  (decimal 0-1)
    or 'ensemble_detail' list of {TMC, BJP, Left-Congress, Others} dicts.

    We prefer ensemble_detail averaged if available, else fall back to sim_* fields.
    """
    run_id = run_data.get("run_id", "unknown")

    cluster_results = run_data.get("cluster_results", [])
    if not cluster_results:
        raise ValueError("Run JSON has no 'cluster_results' key or it is empty.")

    predictions: dict[str, dict[str, float]] = {}

    for cluster in cluster_results:
        cluster_id = cluster.get("id") or cluster.get("cluster_id")
        if not cluster_id:
            logger.warning("Cluster entry missing 'id' — skipping: %s", cluster)
            continue

        # Prefer ensemble_detail (average of 3 runs) when available
        ensemble_detail = cluster.get("ensemble_detail")
        if ensemble_detail:
            raw_shares = _average_ensemble_detail(ensemble_detail)
        else:
            # Fall back to pre-averaged sim_* fields
            raw_shares = {
                k: v for k, v in cluster.items()
                if k.startswith("sim_")
            }
            if not raw_shares:
                logger.warning(
                    "Cluster '%s' has no ensemble_detail or sim_* fields — skipping.",
                    cluster_id,
                )
                continue

        normalised = normalise_engine_shares(raw_shares, election_id)
        if normalised:
            predictions[cluster_id] = normalised

    return run_id, predictions


def _average_ensemble_detail(
    ensemble_detail: list[dict[str, float]],
) -> dict[str, float]:
    """Average vote shares across ensemble runs.  Input is decimal 0-1."""
    if not ensemble_detail:
        return {}

    keys = set(ensemble_detail[0].keys())
    averaged: dict[str, float] = {}
    for key in keys:
        vals = [run[key] for run in ensemble_detail if key in run]
        averaged[key] = sum(vals) / len(vals) if vals else 0.0
    return averaged


def _parse_simple_run(
    run_data: dict,
    election_id: str,
) -> tuple[str, dict[str, dict[str, float]]]:
    """Parse a simple flat run JSON (e.g. Delhi benchmark format).

    Expected keys: run_id, popscale_shares: {PartyName: pct_0_to_100}
    The unit_id is set to 'overall' for flat single-unit runs.
    """
    run_id = run_data.get("run_id", "unknown")
    popscale_shares = run_data.get("popscale_shares", {})
    if not popscale_shares:
        raise ValueError("Run JSON has no 'popscale_shares' key or it is empty.")

    normalised = normalise_engine_shares(popscale_shares, election_id)
    return run_id, {"overall": normalised}


def _load_run_json(run_path: str) -> dict:
    """Load and parse a run JSON file.  Raises FileNotFoundError if missing."""
    path = Path(run_path)
    if not path.exists():
        raise FileNotFoundError(f"Run JSON not found: {run_path}")
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _extract_predictions(
    run_data: dict,
    election_id: str,
) -> tuple[str, dict[str, dict[str, float]]]:
    """Dispatch to the correct parser based on run JSON shape."""
    if "cluster_results" in run_data:
        return _parse_wb_constituency_run(run_data, election_id)
    elif "popscale_shares" in run_data:
        return _parse_simple_run(run_data, election_id)
    else:
        raise ValueError(
            "Unrecognised run JSON format — expected 'cluster_results' or "
            f"'popscale_shares' key.  Top-level keys: {list(run_data.keys())}"
        )


# ---------------------------------------------------------------------------
# Ground truth → comparison dict
# ---------------------------------------------------------------------------

def _gt_to_comparison_dict(
    gt,
    election_id: str,
    predicted_unit_ids: set[str],
) -> dict[str, dict[str, float]]:
    """Convert GroundTruth to {unit_id: {party_key: pct}} comparison form.

    For WB elections the GT has 294 constituencies.  When the engine ran 5
    clusters, we build the GT dict keyed by cluster_id, using the cluster's
    aggregate outcomes if a cluster_mapping is available, otherwise keyed by
    constituency_code (partial overlap only).

    Strategy:
    - If predicted units look like cluster IDs (short strings, e.g. 'murshidabad'),
      attempt to aggregate GT to clusters using the embedded mapping.
    - Otherwise use constituency codes directly (for future per-constituency runs).
    """
    # Normalise all GT units first
    gt_dict: dict[str, dict[str, float]] = {}
    for unit in gt.units:
        normalised = normalise_gt_outcomes(unit.outcomes, election_id)
        gt_dict[unit.unit_id] = normalised

    # Check if predicted units are cluster IDs (not in gt_dict)
    # If so, try to aggregate GT to cluster level
    cluster_ids = predicted_unit_ids - gt_dict.keys()
    if cluster_ids:
        # Some or all predicted units are cluster IDs — try aggregation
        gt_dict = _aggregate_gt_to_cluster_ids(
            gt, gt_dict, election_id, predicted_unit_ids
        )

    return gt_dict


def _aggregate_gt_to_cluster_ids(
    gt,
    gt_dict_by_constituency: dict[str, dict[str, float]],
    election_id: str,
    predicted_unit_ids: set[str],
) -> dict[str, dict[str, float]]:
    """Aggregate constituency-level GT to cluster-level using a heuristic mapping.

    For WB elections, the cluster→constituency mapping CSV lives at:
        popscale/calibration/ground_truth/wb_2021_assembly/cluster_mapping.csv

    If that file exists, use aggregate_to_clusters(). Otherwise fall back to
    returning the constituency-level dict (low coverage, but no error).
    """
    from pathlib import Path as _Path
    from .enrichment import aggregate_to_clusters

    mapping_csv = (
        _Path(__file__).parent
        / "ground_truth"
        / election_id
        / "cluster_mapping.csv"
    )

    if mapping_csv.exists():
        logger.debug(
            "Aggregating %d GT units to clusters via %s",
            len(gt.units),
            mapping_csv,
        )
        try:
            cluster_gt = aggregate_to_clusters(gt, mapping_csv)
            # cluster_gt is {cluster_id: {party_key: pct}}
            # Merge with constituency-level dict (constituency codes take precedence
            # when both are present, but in practice they use disjoint keys)
            merged = dict(gt_dict_by_constituency)
            merged.update(cluster_gt)
            return merged
        except Exception as exc:
            logger.warning(
                "aggregate_to_clusters() failed (%s); falling back to "
                "constituency-level GT dict (coverage will be low).",
                exc,
            )

    # No mapping file — return constituency dict; caller handles low coverage
    return gt_dict_by_constituency


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def backcast(
    election_id: str,
    engine_config: dict | None = None,
    use_existing_run: str | None = None,
) -> BacktestResult:
    """Run the backcasting harness.

    Args:
        election_id: Registered election ID, e.g. 'wb_2021_assembly'.
        engine_config: Engine configuration for live runs (not used until
            BRIEF-021 — pass None for now).
        use_existing_run: Path to a saved run JSON.  When provided, the engine
            is not re-run.  This is the primary path for Phase 3 calibration.

    Returns:
        BacktestResult with scoring metrics.

    Raises:
        ValueError: if election_id is unknown or run JSON is malformed.
        FileNotFoundError: if use_existing_run path does not exist.
    """
    # 1. Load ground truth (raises ValueError on unknown election_id)
    gt = load_ground_truth(election_id)
    gt_unit_count = len(gt.units)
    logger.info(
        "backcast: loaded GT for '%s' — %d units (%s granularity)",
        election_id,
        gt_unit_count,
        gt.granularity,
    )

    # 2. Load engine predictions
    if use_existing_run is not None:
        run_data = _load_run_json(use_existing_run)
        run_id, predictions = _extract_predictions(run_data, election_id)
        run_metadata = {
            "source": "existing_run",
            "run_path": str(use_existing_run),
            "run_date": run_data.get("run_date") or run_data.get("timestamp"),
            "n_clusters": run_data.get("n_clusters"),
            "total_personas": run_data.get("total_personas") or run_data.get("n_personas"),
            "tier": run_data.get("tier", "unknown"),
        }
    else:
        # Live run — deferred to BRIEF-021
        raise NotImplementedError(
            "Live engine runs not yet wired (BRIEF-021). "
            "Pass use_existing_run= to use a saved run JSON."
        )

    predicted_unit_ids = set(predictions.keys())
    logger.info(
        "backcast: engine run '%s' produced %d predicted units",
        run_id,
        len(predicted_unit_ids),
    )

    # 3. Build GT comparison dict at correct granularity
    gt_comparison = _gt_to_comparison_dict(gt, election_id, predicted_unit_ids)

    # 4. Coverage
    gt_comparison_ids = set(gt_comparison.keys())
    covered = predicted_unit_ids & gt_comparison_ids
    coverage_pct = len(covered) / gt_unit_count if gt_unit_count > 0 else 0.0
    logger.info(
        "backcast: coverage %d/%d units (%.1f%%)",
        len(covered),
        gt_unit_count,
        coverage_pct * 100,
    )

    # 5. Filter to matched units only for scoring
    pred_matched = {uid: predictions[uid] for uid in covered}
    gt_matched = {uid: gt_comparison[uid] for uid in covered}

    # 6. Compute metrics
    overall_mae, per_unit_errors = compute_mae(pred_matched, gt_matched)
    brier = compute_brier(pred_matched, gt_matched)
    dir_acc = compute_directional_accuracy(pred_matched, gt_matched)

    logger.info(
        "backcast: MAE=%.2fpp  Brier=%.4f  DirAcc=%.1f%%  Coverage=%.1f%%",
        overall_mae,
        brier,
        dir_acc * 100,
        coverage_pct * 100,
    )

    return BacktestResult(
        election_id=election_id,
        engine_run_id=run_id,
        ground_truth=gt_matched,
        predicted=pred_matched,
        overall_mae=overall_mae,
        per_unit_errors=per_unit_errors,
        brier_score=brier,
        directional_accuracy=dir_acc,
        coverage_pct=coverage_pct,
        metadata={
            "gt_unit_count": gt_unit_count,
            "predicted_unit_count": len(predicted_unit_ids),
            "covered_unit_count": len(covered),
            "backcast_timestamp": datetime.now(timezone.utc).isoformat(),
            **run_metadata,
        },
    )
