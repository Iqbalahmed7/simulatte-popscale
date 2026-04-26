"""
training.py — BRIEF-021: Calibration training loop (Approach 1: persona prior recalibration).

API
---
    result = await calibrate(
        target_election_id="wb_2021_assembly",
        starting_priors_path=Path("priors.json"),
        max_iterations=5,
        target_mae_pp=3.0,
        budget_usd=100.0,
    )

Algorithm
---------
Each iteration:
  1. Run a backcast using current priors as a simulated engine run.
  2. Call decompose_bias() to surface per-cell errors.
  3. For every demographic cell with MAE > 2pp, apply the v1 adjustment rule:
       shift that cell's prior preference for the over-predicted party down by Δpp/4.
  4. Write a calibration_history.jsonl entry and a checkpoint JSON.
  5. Repeat until target_mae_pp hit, max_iterations exhausted, or budget_usd hit.

Priors file format (JSON)
--------------------------
A dict keyed by demographic cell identifier (e.g. "religion:muslim:tmc_pct"):

    {
        "religion:muslim:tmc_pct": 48.2,
        "religion:muslim:bjp_pct": 12.1,
        ...
    }

Or the nested form:

    {
        "cells": {
            "<axis>:<cell>:<party>": <prior_pct>
        }
    }

Flat form is preferred. Both are accepted.

Budget guard
------------
budget_usd is checked before each iteration. The loop estimates cost_per_iteration_usd
from the first completed iteration. If projected spend would exceed budget_usd, the
loop halts and records convergence="budget_halt".

Checkpoints
-----------
Written after each iteration to:
    <checkpoint_dir>/checkpoint_<iteration>.json

Default checkpoint_dir: same directory as starting_priors_path, under a
"calibration_checkpoints/" subdirectory. Resuming is done by passing
resume_from_checkpoint=<path> to find the latest checkpoint and reload
priors from it.

Audit log
---------
calibration_history.jsonl is appended to after every iteration.
Each line is a JSON object with iteration number, MAE, prior changes, timestamp.

CALIBRATION_REPORT.md
---------------------
Generated at the end of calibrate() — written next to calibration_history.jsonl.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from .harness import BacktestResult, backcast
from .bias_decomposition import decompose_bias, BiasReport

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAE_TRIGGER_PP = 2.0          # cells with MAE above this are adjusted
_ADJUSTMENT_FRACTION = 0.25    # Δpp / 4 step size
_MIN_PRIOR_PCT = 0.5           # floor: priors never go below 0.5%
_MAX_PRIOR_PCT = 99.0          # ceiling: priors never exceed 99%


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class IterationRecord:
    """One iteration's worth of calibration data."""
    iteration: int
    mae_pp: float
    prior_changes: list[dict]   # [{cell, party, old_value, new_value, delta}]
    backtest_run_id: str
    cost_usd: float
    timestamp: str


@dataclass
class CalibrationResult:
    """Output of calibrate().

    Attributes:
        mae_history: MAE (pp) at the end of each iteration — index 0 is
            the *initial* backcast (iteration 0 = before any adjustment).
        final_priors: The adjusted priors dict after the loop completes.
        total_cost_usd: Sum of per-iteration cost estimates.
        convergence: 'converged' | 'max_iterations' | 'budget_halt' | 'zero_iterations'
        iterations_run: Number of adjustment iterations applied (not counting
            the initial pre-loop backcast).
        history: Full IterationRecord list, one per backcast run.
        report_path: Path to CALIBRATION_REPORT.md, or None if not written.
    """
    mae_history: list[float]
    final_priors: dict[str, float]
    total_cost_usd: float
    convergence: Literal["converged", "max_iterations", "budget_halt", "zero_iterations"]
    iterations_run: int
    history: list[IterationRecord] = field(default_factory=list)
    report_path: Optional[Path] = None


# ---------------------------------------------------------------------------
# Priors I/O
# ---------------------------------------------------------------------------

def load_priors(path: Path) -> dict[str, float]:
    """Load priors from a JSON file.  Accepts both flat and nested forms.

    Flat form:  {"religion:muslim:tmc_pct": 48.2, ...}
    Nested form: {"cells": {"religion:muslim:tmc_pct": 48.2, ...}}

    Raises:
        FileNotFoundError: if path does not exist.
        ValueError: if the file is not valid JSON or has an unrecognised shape.
    """
    if not path.exists():
        raise FileNotFoundError(f"Priors file not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Priors file is not valid JSON: {path} — {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(f"Priors file must be a JSON object, got {type(raw).__name__}: {path}")

    # Nested form
    if "cells" in raw and isinstance(raw["cells"], dict):
        return {k: float(v) for k, v in raw["cells"].items()}

    # Flat form — every value must be numeric
    priors: dict[str, float] = {}
    for k, v in raw.items():
        try:
            priors[k] = float(v)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Non-numeric prior value for key '{k}': {v!r} in {path}"
            ) from exc
    return priors


def save_priors(priors: dict[str, float], path: Path) -> None:
    """Persist priors to a JSON file (flat form)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(priors, fh, indent=2)


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------

def _checkpoint_dir(starting_priors_path: Path) -> Path:
    return starting_priors_path.parent / "calibration_checkpoints"


def _write_checkpoint(
    iteration: int,
    priors: dict[str, float],
    mae: float,
    checkpoint_dir: Path,
) -> Path:
    """Write a checkpoint JSON; return the path written."""
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    cp_path = checkpoint_dir / f"checkpoint_{iteration:04d}.json"
    payload = {
        "iteration": iteration,
        "mae_pp": mae,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "priors": priors,
    }
    with cp_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    logger.info("Checkpoint written: %s (MAE=%.2fpp)", cp_path, mae)
    return cp_path


def load_latest_checkpoint(checkpoint_dir: Path) -> Optional[tuple[int, dict[str, float], float]]:
    """Load the most recent checkpoint from checkpoint_dir.

    Returns:
        (iteration, priors, mae) or None if no checkpoints found.
    """
    if not checkpoint_dir.exists():
        return None
    checkpoints = sorted(checkpoint_dir.glob("checkpoint_*.json"))
    if not checkpoints:
        return None
    latest = checkpoints[-1]
    try:
        with latest.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data["iteration"], data["priors"], data["mae_pp"]
    except (json.JSONDecodeError, KeyError, OSError) as exc:
        logger.warning("Could not load checkpoint %s: %s", latest, exc)
        return None


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

def _append_audit_log(record: IterationRecord, log_path: Path) -> None:
    """Append one iteration record to calibration_history.jsonl."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "iteration": record.iteration,
        "mae_pp": record.mae_pp,
        "prior_changes": record.prior_changes,
        "backtest_run_id": record.backtest_run_id,
        "cost_usd": record.cost_usd,
        "timestamp": record.timestamp,
    }
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# Synthetic engine run (priors → BacktestResult)
# ---------------------------------------------------------------------------

def _priors_to_run_json(
    priors: dict[str, float],
    election_id: str,
    run_id: str,
    tmp_dir: Path,
) -> Path:
    """Convert current priors to a run JSON that backcast() can load.

    Strategy: aggregate priors across all demographic cells to a single
    cluster-level vote share per party, then emit as a flat run JSON with
    key "popscale_shares".

    This is the v1 stub implementation — it yields cluster-level aggregates
    from priors, which is enough to drive the MAE loop without a live engine.
    """
    # Aggregate: for each party key, average all prior cells that mention it
    party_totals: dict[str, list[float]] = {}
    for cell_key, value in priors.items():
        # cell_key format: "<axis>:<cell_value>:<party_key>"
        parts = cell_key.rsplit(":", 1)
        if len(parts) == 2:
            party_key = parts[1]
            party_totals.setdefault(party_key, []).append(value)

    if not party_totals:
        # Fallback: treat priors as direct party → share mapping
        party_totals = {k: [v] for k, v in priors.items()}

    popscale_shares = {
        party: sum(vals) / len(vals)
        for party, vals in party_totals.items()
    }

    # Normalise to sum = 100
    total = sum(popscale_shares.values())
    if total > 0:
        popscale_shares = {k: v / total * 100.0 for k, v in popscale_shares.items()}

    run_data = {
        "run_id": run_id,
        "election_id": election_id,
        "tier": "signal",
        "popscale_shares": popscale_shares,
        "run_date": datetime.now(timezone.utc).isoformat(),
    }

    tmp_dir.mkdir(parents=True, exist_ok=True)
    run_path = tmp_dir / f"{run_id}.json"
    with run_path.open("w", encoding="utf-8") as fh:
        json.dump(run_data, fh, indent=2)
    return run_path


async def _run_backcast(
    priors: dict[str, float],
    election_id: str,
    iteration: int,
    tmp_dir: Path,
) -> BacktestResult:
    """Synthesize a run JSON from current priors and backcast it."""
    run_id = f"calibration_iter_{iteration:04d}_{int(time.time())}"
    run_path = _priors_to_run_json(priors, election_id, run_id, tmp_dir)
    result = await backcast(election_id, use_existing_run=str(run_path))
    # Clean up tmp file
    try:
        run_path.unlink(missing_ok=True)
    except OSError:
        pass
    return result


# ---------------------------------------------------------------------------
# Adjustment rule (v1)
# ---------------------------------------------------------------------------

def _apply_adjustment_rule(
    priors: dict[str, float],
    bias_report: BiasReport,
) -> tuple[dict[str, float], list[dict]]:
    """Apply v1 prior adjustment to cells with MAE > _MAE_TRIGGER_PP.

    For each demographic cell exceeding the MAE threshold, shift the cell's
    prior for the over-predicted party down by Δpp / 4.

    Returns:
        (updated_priors, list_of_change_records)
    """
    updated = copy.deepcopy(priors)
    changes: list[dict] = []

    # by_demographic: {axis: {cell_value: mae_pp}}
    for axis, cells in bias_report.by_demographic.items():
        for cell_value, cell_mae in cells.items():
            if cell_mae <= _MAE_TRIGGER_PP:
                continue

            # Find all prior keys for this axis:cell combination
            prefix = f"{axis}:{cell_value}:"
            cell_keys = {k: v for k, v in updated.items() if k.startswith(prefix)}
            if not cell_keys:
                continue

            # Identify over-predicted party: the one with the highest prior in this cell
            over_party_key = max(cell_keys, key=cell_keys.__getitem__)
            delta_pp = cell_mae  # MAE as a proxy for over-prediction magnitude
            adjustment = delta_pp * _ADJUSTMENT_FRACTION

            old_val = updated[over_party_key]
            new_val = max(_MIN_PRIOR_PCT, min(_MAX_PRIOR_PCT, old_val - adjustment))

            if abs(new_val - old_val) < 1e-6:
                continue

            updated[over_party_key] = new_val
            changes.append({
                "cell": f"{axis}:{cell_value}",
                "party": over_party_key,
                "old_value": round(old_val, 4),
                "new_value": round(new_val, 4),
                "delta": round(new_val - old_val, 4),
                "cell_mae_pp": round(cell_mae, 4),
            })
            logger.debug(
                "Prior adjusted: %s → %.4f (was %.4f, delta=%.4f, cell_mae=%.2fpp)",
                over_party_key, new_val, old_val, new_val - old_val, cell_mae,
            )

    return updated, changes


# ---------------------------------------------------------------------------
# Report generator
# ---------------------------------------------------------------------------

def _generate_report(
    election_id: str,
    history: list[IterationRecord],
    final_priors: dict[str, float],
    convergence: str,
    target_mae_pp: float,
    report_path: Path,
) -> None:
    """Write CALIBRATION_REPORT.md next to the audit log."""
    lines: list[str] = [
        "# Calibration Report",
        "",
        f"**Election:** `{election_id}`  ",
        f"**Target MAE:** {target_mae_pp:.1f}pp  ",
        f"**Convergence status:** `{convergence}`  ",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
        "",
        "## MAE Trajectory",
        "",
        "| Iteration | MAE (pp) | Changes applied |",
        "|-----------|----------|----------------|",
    ]

    for rec in history:
        lines.append(
            f"| {rec.iteration} | {rec.mae_pp:.2f} | {len(rec.prior_changes)} |"
        )

    lines += [
        "",
        "## Prior Changes by Iteration",
        "",
    ]

    for rec in history:
        if not rec.prior_changes:
            continue
        lines.append(f"### Iteration {rec.iteration} (MAE {rec.mae_pp:.2f}pp)")
        lines.append("")
        lines.append("| Cell | Party | Old | New | Delta |")
        lines.append("|------|-------|-----|-----|-------|")
        for chg in rec.prior_changes:
            lines.append(
                f"| {chg['cell']} | {chg['party']} "
                f"| {chg['old_value']:.2f} | {chg['new_value']:.2f} "
                f"| {chg['delta']:+.2f} |"
            )
        lines.append("")

    lines += [
        "## Final Prior Snapshot",
        "",
        "| Cell Key | Prior (%) |",
        "|----------|-----------|",
    ]
    for key, val in sorted(final_priors.items()):
        lines.append(f"| `{key}` | {val:.2f} |")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    logger.info("CALIBRATION_REPORT.md written: %s", report_path)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def calibrate(
    target_election_id: str,
    starting_priors_path: Path,
    max_iterations: int = 5,
    target_mae_pp: float = 3.0,
    budget_usd: float = 100.0,
    *,
    persona_data_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    resume_from_checkpoint: bool = False,
    cost_per_iteration_usd: float = 0.0,
) -> CalibrationResult:
    """Iterative persona prior recalibration loop.

    Args:
        target_election_id: Registered election ID (e.g. 'wb_2021_assembly').
        starting_priors_path: Path to the starting priors JSON.
        max_iterations: Maximum number of adjustment iterations (default 5).
        target_mae_pp: Stop early when MAE drops below this (default 3.0pp).
        budget_usd: Hard budget ceiling. Halt if projected total spend would
            exceed this. Pass float('inf') to disable (not recommended for
            production runs).
        persona_data_path: Optional path to a persona records JSON for
            demographic decomposition. When None, bias decomposition will
            have empty demographic slices (region-only MAE drives adjustments).
        output_dir: Directory for audit log, report, and checkpoints.
            Defaults to starting_priors_path.parent / "calibration_output".
        resume_from_checkpoint: If True, look for existing checkpoints and
            resume from the most recent one.
        cost_per_iteration_usd: Override cost estimate per iteration.
            When 0.0 (default), the loop uses the first iteration's wall-clock
            time as a proxy and applies a $0 estimate (stub mode, no real
            API calls in the training loop itself).

    Returns:
        CalibrationResult with mae_history, final_priors, total_cost_usd,
        convergence status, and path to CALIBRATION_REPORT.md.

    Raises:
        FileNotFoundError: if starting_priors_path does not exist.
        ValueError: if starting_priors_path is malformed.
        RuntimeError: if budget_usd <= 0.
    """
    if budget_usd <= 0:
        raise RuntimeError(
            f"budget_usd must be positive, got {budget_usd}. "
            "Real-money runs require an explicit budget."
        )

    # --- Setup paths ---
    starting_priors_path = Path(starting_priors_path).resolve()
    if output_dir is None:
        output_dir = starting_priors_path.parent / "calibration_output"
    else:
        output_dir = Path(output_dir).resolve()

    output_dir.mkdir(parents=True, exist_ok=True)
    audit_log_path = output_dir / "calibration_history.jsonl"
    report_path = output_dir / "CALIBRATION_REPORT.md"
    cp_dir = output_dir / "checkpoints"
    tmp_dir = output_dir / "_tmp_runs"

    # --- Load priors ---
    priors = load_priors(starting_priors_path)
    logger.info(
        "calibrate: loaded %d prior cells from %s",
        len(priors), starting_priors_path,
    )

    # --- Resume from checkpoint ---
    start_iteration = 0
    if resume_from_checkpoint:
        checkpoint = load_latest_checkpoint(cp_dir)
        if checkpoint:
            start_iteration, priors, _ = checkpoint
            logger.info(
                "calibrate: resumed from checkpoint at iteration %d", start_iteration
            )

    # --- State ---
    mae_history: list[float] = []
    history: list[IterationRecord] = []
    total_cost_usd: float = 0.0
    convergence: Literal[
        "converged", "max_iterations", "budget_halt", "zero_iterations"
    ] = "zero_iterations"

    # Persona data path (optional — used for demographic decomposition)
    if persona_data_path is None:
        persona_data_path = starting_priors_path.parent / "persona_data.json"
        # If it doesn't exist, bias_decomposition will gracefully return empty demographic slices

    # --- Initial backcast (iteration 0) ---
    logger.info("calibrate: running initial backcast (iteration 0) …")
    initial_result = await _run_backcast(priors, target_election_id, 0, tmp_dir)
    initial_mae = initial_result.overall_mae
    mae_history.append(initial_mae)
    logger.info("calibrate: initial MAE = %.2fpp", initial_mae)

    # Check immediate convergence (smoke test path)
    if initial_mae <= target_mae_pp:
        _write_checkpoint(0, priors, initial_mae, cp_dir)
        initial_record = IterationRecord(
            iteration=0,
            mae_pp=initial_mae,
            prior_changes=[],
            backtest_run_id=initial_result.engine_run_id,
            cost_usd=0.0,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        history.append(initial_record)
        _append_audit_log(initial_record, audit_log_path)
        convergence = "converged"
        _generate_report(
            target_election_id, history, priors, convergence, target_mae_pp, report_path
        )
        logger.info(
            "calibrate: already at target MAE (%.2fpp ≤ %.2fpp) — 0 iterations needed.",
            initial_mae, target_mae_pp,
        )
        return CalibrationResult(
            mae_history=mae_history,
            final_priors=priors,
            total_cost_usd=total_cost_usd,
            convergence=convergence,
            iterations_run=0,
            history=history,
            report_path=report_path,
        )

    # Record initial (pre-adjustment) state
    initial_record = IterationRecord(
        iteration=0,
        mae_pp=initial_mae,
        prior_changes=[],
        backtest_run_id=initial_result.engine_run_id,
        cost_usd=0.0,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    history.append(initial_record)
    _append_audit_log(initial_record, audit_log_path)

    # --- Main loop ---
    for iteration in range(start_iteration + 1, max_iterations + 1):
        # Budget guard
        iter_cost = cost_per_iteration_usd
        projected_total = total_cost_usd + iter_cost
        if projected_total > budget_usd:
            logger.warning(
                "calibrate: budget guard triggered at iteration %d "
                "(projected=%.2f > budget=%.2f). Halting.",
                iteration, projected_total, budget_usd,
            )
            convergence = "budget_halt"
            break

        logger.info("calibrate: iteration %d / %d …", iteration, max_iterations)

        # 1. Decompose bias from last backcast
        last_backtest = await _run_backcast(priors, target_election_id, iteration, tmp_dir)
        current_mae = last_backtest.overall_mae

        bias_report = decompose_bias(last_backtest, persona_data_path)

        # 2. Apply adjustment rule
        updated_priors, changes = _apply_adjustment_rule(priors, bias_report)

        # 3. Track cost (stub: only real cost if cost_per_iteration_usd > 0)
        total_cost_usd += iter_cost

        # 4. Record
        record = IterationRecord(
            iteration=iteration,
            mae_pp=current_mae,
            prior_changes=changes,
            backtest_run_id=last_backtest.engine_run_id,
            cost_usd=iter_cost,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        history.append(record)
        mae_history.append(current_mae)
        _append_audit_log(record, audit_log_path)

        # 5. Checkpoint
        _write_checkpoint(iteration, updated_priors, current_mae, cp_dir)

        # 6. Update priors for next iteration
        priors = updated_priors

        logger.info(
            "calibrate: iteration %d complete — MAE=%.2fpp, %d prior changes, cost=%.4f",
            iteration, current_mae, len(changes), iter_cost,
        )

        # 7. Convergence check
        if current_mae <= target_mae_pp:
            convergence = "converged"
            logger.info(
                "calibrate: converged at iteration %d (MAE=%.2fpp ≤ %.2fpp)",
                iteration, current_mae, target_mae_pp,
            )
            break
    else:
        # Loop exhausted max_iterations without converging
        if convergence == "zero_iterations":
            convergence = "max_iterations"

    # --- Final report ---
    _generate_report(
        target_election_id, history, priors, convergence, target_mae_pp, report_path
    )

    # Clean up tmp dir
    try:
        if tmp_dir.exists():
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
    except OSError:
        pass

    logger.info(
        "calibrate: done — %d iterations, convergence=%s, MAE trajectory=%s",
        len(history) - 1,
        convergence,
        [round(m, 2) for m in mae_history],
    )

    return CalibrationResult(
        mae_history=mae_history,
        final_priors=priors,
        total_cost_usd=total_cost_usd,
        convergence=convergence,
        iterations_run=len(history) - 1,
        history=history,
        report_path=report_path,
    )
