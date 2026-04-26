"""
Tests for BRIEF-021: calibration training loop (training.py).

Acceptance criteria:
  1. test_smoke_perfect_input — perfect priors → 0 iterations, immediate convergence
  2. test_basic_convergence — imperfect priors → loop runs iterations, MAE tracked
  3. test_budget_halt — budget_usd=0 triggers RuntimeError; very small budget halts loop
  4. test_load_priors_flat_form — load_priors handles flat JSON
  5. test_load_priors_nested_form — load_priors handles nested {"cells": {...}} JSON
  6. test_load_priors_missing_file — FileNotFoundError on missing file
  7. test_checkpoint_round_trip — checkpoint write + load round-trips correctly
  8. test_apply_adjustment_rule_shifts_high_mae_cells — adjustment rule moves over-predicted priors
  9. test_apply_adjustment_rule_leaves_low_mae_cells — cells below threshold untouched
  10. test_calibration_result_fields — CalibrationResult carries all required fields
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from popscale.calibration.training import (
    CalibrationResult,
    IterationRecord,
    _apply_adjustment_rule,
    _write_checkpoint,
    load_latest_checkpoint,
    load_priors,
    save_priors,
    calibrate,
)
from popscale.calibration.bias_decomposition import BiasReport
from popscale.calibration.harness import BacktestResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_backtest_result(
    mae: float = 5.0,
    run_id: str = "test_run",
    election_id: str = "wb_2021_assembly",
) -> BacktestResult:
    """Build a minimal BacktestResult with controlled MAE."""
    unit_preds = {"unit_a": {"tmc_pct": 50.0, "bjp_pct": 30.0, "others_pct": 20.0}}
    unit_gt = {"unit_a": {"tmc_pct": 50.0 - mae, "bjp_pct": 30.0, "others_pct": 20.0 + mae}}
    return BacktestResult(
        election_id=election_id,
        engine_run_id=run_id,
        ground_truth=unit_gt,
        predicted=unit_preds,
        overall_mae=mae,
        per_unit_errors={"unit_a": mae},
        brier_score=0.01,
        directional_accuracy=1.0,
        coverage_pct=1.0,
        metadata={},
    )


def _make_bias_report_with_high_mae(
    axis: str = "religion",
    cell_value: str = "muslim",
    cell_mae: float = 6.0,
    overall_mae: float = 5.0,
) -> BiasReport:
    return BiasReport(
        overall_mae=overall_mae,
        by_demographic={axis: {cell_value: cell_mae}},
        by_region={"unit_a": overall_mae},
        by_confidence_band={"high_conf": overall_mae},
        largest_errors=[("unit_a", overall_mae)],
        recommendations=[],
    )


def _make_bias_report_empty(overall_mae: float = 1.0) -> BiasReport:
    return BiasReport(
        overall_mae=overall_mae,
        by_demographic={},
        by_region={},
        by_confidence_band={},
        largest_errors=[],
        recommendations=[],
    )


# ---------------------------------------------------------------------------
# Unit tests — load_priors
# ---------------------------------------------------------------------------

def test_load_priors_flat_form(tmp_path):
    priors_file = tmp_path / "priors.json"
    data = {"religion:muslim:tmc_pct": 48.2, "religion:hindu:bjp_pct": 35.0}
    priors_file.write_text(json.dumps(data))

    result = load_priors(priors_file)
    assert result["religion:muslim:tmc_pct"] == pytest.approx(48.2)
    assert result["religion:hindu:bjp_pct"] == pytest.approx(35.0)


def test_load_priors_nested_form(tmp_path):
    priors_file = tmp_path / "priors.json"
    data = {"cells": {"religion:muslim:tmc_pct": 48.2, "religion:hindu:bjp_pct": 35.0}}
    priors_file.write_text(json.dumps(data))

    result = load_priors(priors_file)
    assert result["religion:muslim:tmc_pct"] == pytest.approx(48.2)


def test_load_priors_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_priors(tmp_path / "does_not_exist.json")


# ---------------------------------------------------------------------------
# Unit tests — checkpoint round-trip
# ---------------------------------------------------------------------------

def test_checkpoint_round_trip(tmp_path):
    cp_dir = tmp_path / "checkpoints"
    priors = {"religion:muslim:tmc_pct": 42.0, "religion:hindu:bjp_pct": 31.0}

    _write_checkpoint(iteration=3, priors=priors, mae=4.5, checkpoint_dir=cp_dir)

    result = load_latest_checkpoint(cp_dir)
    assert result is not None
    iteration, loaded_priors, loaded_mae = result
    assert iteration == 3
    assert loaded_mae == pytest.approx(4.5)
    assert loaded_priors["religion:muslim:tmc_pct"] == pytest.approx(42.0)


def test_checkpoint_no_checkpoints_returns_none(tmp_path):
    result = load_latest_checkpoint(tmp_path / "empty_dir")
    assert result is None


# ---------------------------------------------------------------------------
# Unit tests — adjustment rule
# ---------------------------------------------------------------------------

def test_apply_adjustment_rule_shifts_high_mae_cells():
    """Cells with MAE > 2pp should have their leading prior shifted down."""
    priors = {
        "religion:muslim:tmc_pct": 60.0,
        "religion:muslim:bjp_pct": 25.0,
        "religion:muslim:others_pct": 15.0,
    }
    bias_report = _make_bias_report_with_high_mae(
        axis="religion", cell_value="muslim", cell_mae=8.0
    )

    updated, changes = _apply_adjustment_rule(priors, bias_report)

    # tmc_pct was highest → should be reduced
    assert updated["religion:muslim:tmc_pct"] < priors["religion:muslim:tmc_pct"]
    assert len(changes) == 1
    assert changes[0]["cell"] == "religion:muslim"
    assert changes[0]["delta"] < 0  # moved downward
    # adjustment = 8.0 * 0.25 = 2.0pp
    assert updated["religion:muslim:tmc_pct"] == pytest.approx(60.0 - 2.0)


def test_apply_adjustment_rule_leaves_low_mae_cells():
    """Cells with MAE ≤ 2pp should not be adjusted."""
    priors = {"religion:hindu:tmc_pct": 40.0, "religion:hindu:bjp_pct": 45.0}
    # MAE = 1.5pp — below trigger threshold
    bias_report = BiasReport(
        overall_mae=1.5,
        by_demographic={"religion": {"hindu": 1.5}},
        by_region={},
        by_confidence_band={},
        largest_errors=[],
        recommendations=[],
    )

    updated, changes = _apply_adjustment_rule(priors, bias_report)

    assert updated == priors
    assert changes == []


def test_apply_adjustment_rule_respects_floor():
    """Prior should never go below _MIN_PRIOR_PCT (0.5%)."""
    priors = {"religion:muslim:tmc_pct": 0.8}
    bias_report = _make_bias_report_with_high_mae(
        axis="religion", cell_value="muslim", cell_mae=20.0
    )
    # adjustment = 20.0 * 0.25 = 5.0; 0.8 - 5.0 = -4.2 → clamped to 0.5
    updated, changes = _apply_adjustment_rule(priors, bias_report)
    assert updated["religion:muslim:tmc_pct"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Integration tests — calibrate()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_smoke_perfect_input(tmp_path):
    """Perfect priors (MAE already ≤ target) → convergence='converged', 0 iterations."""
    priors_file = tmp_path / "priors.json"
    priors_data = {"popscale_shares:tmc_pct": 48.0}
    priors_file.write_text(json.dumps(priors_data))

    # Mock _run_backcast to return MAE = 1.0 (below target of 3.0)
    perfect_backtest = _make_backtest_result(mae=1.0)

    with patch(
        "popscale.calibration.training._run_backcast",
        new=AsyncMock(return_value=perfect_backtest),
    ):
        result = await calibrate(
            target_election_id="wb_2021_assembly",
            starting_priors_path=priors_file,
            max_iterations=5,
            target_mae_pp=3.0,
            budget_usd=100.0,
            output_dir=tmp_path / "output",
        )

    assert result.convergence == "converged"
    assert result.iterations_run == 0
    assert result.mae_history == [pytest.approx(1.0)]
    assert (tmp_path / "output" / "CALIBRATION_REPORT.md").exists()
    assert (tmp_path / "output" / "calibration_history.jsonl").exists()


@pytest.mark.asyncio
async def test_basic_convergence(tmp_path):
    """Loop runs iterations, MAE decreases, terminates at max_iterations."""
    priors_file = tmp_path / "priors.json"
    priors_data = {
        "religion:muslim:tmc_pct": 48.0,
        "religion:muslim:bjp_pct": 30.0,
    }
    priors_file.write_text(json.dumps(priors_data))

    # First call (iteration 0): MAE = 8.0 (above target)
    # Subsequent calls: MAE = 5.0 (still above target → loop runs all iterations)
    call_count = 0

    async def mock_run_backcast(priors, election_id, iteration, tmp_dir):
        nonlocal call_count
        call_count += 1
        mae = 8.0 if call_count == 1 else 5.0
        return _make_backtest_result(mae=mae, run_id=f"run_{call_count}")

    bias_report_high = _make_bias_report_with_high_mae(
        axis="religion", cell_value="muslim", cell_mae=6.0, overall_mae=5.0
    )

    with patch("popscale.calibration.training._run_backcast", new=mock_run_backcast), \
         patch("popscale.calibration.training.decompose_bias", return_value=bias_report_high):
        result = await calibrate(
            target_election_id="wb_2021_assembly",
            starting_priors_path=priors_file,
            max_iterations=3,
            target_mae_pp=3.0,
            budget_usd=100.0,
            output_dir=tmp_path / "output",
        )

    # Should have run 3 iterations (none converged since 5.0 > 3.0)
    assert result.convergence == "max_iterations"
    assert result.iterations_run == 3
    # mae_history has entry for each backcast: initial + 3 iterations = 4 entries
    assert len(result.mae_history) == 4
    # Audit log should have 4 entries
    audit_lines = (tmp_path / "output" / "calibration_history.jsonl").read_text().strip().splitlines()
    assert len(audit_lines) == 4
    # Report written
    assert (tmp_path / "output" / "CALIBRATION_REPORT.md").exists()


@pytest.mark.asyncio
async def test_budget_halt_zero_raises():
    """budget_usd=0 raises RuntimeError immediately — never starts engine."""
    with tempfile.TemporaryDirectory() as tmpdir:
        priors_file = Path(tmpdir) / "priors.json"
        priors_file.write_text(json.dumps({"tmc_pct": 48.0}))

        with pytest.raises(RuntimeError, match="budget_usd must be positive"):
            await calibrate(
                target_election_id="wb_2021_assembly",
                starting_priors_path=priors_file,
                budget_usd=0.0,
            )


@pytest.mark.asyncio
async def test_budget_halt_mid_loop(tmp_path):
    """When cost_per_iteration_usd + accumulated spend > budget_usd, halt mid-loop."""
    priors_file = tmp_path / "priors.json"
    priors_file.write_text(json.dumps({"religion:muslim:tmc_pct": 48.0}))

    # MAE = 8.0 so loop won't converge early
    backtest_high = _make_backtest_result(mae=8.0)
    bias_report = _make_bias_report_empty(overall_mae=8.0)

    with patch(
        "popscale.calibration.training._run_backcast",
        new=AsyncMock(return_value=backtest_high),
    ), patch("popscale.calibration.training.decompose_bias", return_value=bias_report):
        result = await calibrate(
            target_election_id="wb_2021_assembly",
            starting_priors_path=priors_file,
            max_iterations=10,
            target_mae_pp=1.0,
            budget_usd=5.0,
            output_dir=tmp_path / "output",
            cost_per_iteration_usd=6.0,  # each iteration costs $6 > $5 budget
        )

    # First iteration projected cost = $6 > $5 budget → halts before iteration 1
    assert result.convergence == "budget_halt"
    assert result.iterations_run == 0  # no adjustment iterations ran


@pytest.mark.asyncio
async def test_calibration_result_fields(tmp_path):
    """CalibrationResult carries all required fields per spec."""
    priors_file = tmp_path / "priors.json"
    priors_file.write_text(json.dumps({"tmc_pct": 50.0}))

    perfect = _make_backtest_result(mae=0.5)
    with patch(
        "popscale.calibration.training._run_backcast",
        new=AsyncMock(return_value=perfect),
    ):
        result = await calibrate(
            target_election_id="wb_2021_assembly",
            starting_priors_path=priors_file,
            max_iterations=5,
            target_mae_pp=3.0,
            budget_usd=50.0,
            output_dir=tmp_path / "output",
        )

    # All required CalibrationResult fields present
    assert isinstance(result.mae_history, list)
    assert isinstance(result.final_priors, dict)
    assert isinstance(result.total_cost_usd, float)
    assert result.convergence in {"converged", "max_iterations", "budget_halt", "zero_iterations"}
    assert isinstance(result.iterations_run, int)
    assert isinstance(result.history, list)
    assert result.report_path is not None and result.report_path.exists()
