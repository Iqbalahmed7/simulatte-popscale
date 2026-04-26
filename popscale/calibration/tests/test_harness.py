"""
Tests for the backcasting harness (BRIEF-018).

Acceptance criteria:
  1. test_backcast_with_stub_engine_output_and_stub_gt
  2. test_backcast_handles_partial_coverage
  3. test_backcast_directional_accuracy
  4. test_backcast_raises_on_unknown_election
"""

from __future__ import annotations

import json
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from popscale.calibration.harness import backcast, BacktestResult
from popscale.calibration.scoring import (
    normalise_engine_shares,
    normalise_gt_outcomes,
    compute_mae,
    compute_brier,
    compute_directional_accuracy,
)
from popscale.calibration.schemas import GroundTruth, GroundTruthUnit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gt(units: list[GroundTruthUnit], election_id: str = "wb_2021_assembly") -> GroundTruth:
    return GroundTruth(
        election_id=election_id,
        date="2021-04-27",
        granularity="constituency",
        units=units,
    )


def _wb_unit(unit_id: str, tmc: float, bjp: float, left: float = 0.0, congress: float = 0.0, others: float = 0.0) -> GroundTruthUnit:
    """Build a WB constituency GroundTruthUnit (pct values, 0-100 scale)."""
    outcomes = {
        "tmc_pct": tmc,
        "bjp_pct": bjp,
        "left_pct": left,
        "congress_pct": congress,
        "others_pct": others,
    }
    winner_key = max(outcomes, key=outcomes.__getitem__).replace("_pct", "")
    margin = sorted(outcomes.values(), reverse=True)[0] - sorted(outcomes.values(), reverse=True)[1]
    return GroundTruthUnit(
        unit_id=unit_id,
        unit_name=f"Constituency {unit_id}",
        outcomes=outcomes,
        winner=winner_key,
        margin_pct=margin,
    )


def _wb_run_json(clusters: list[dict], run_id: str = "test_run") -> dict:
    """Build a minimal WB constituency run JSON."""
    return {
        "run_id": run_id,
        "run_date": "2026-04-26T00:00:00+00:00",
        "n_clusters": len(clusters),
        "total_personas": 100,
        "cluster_results": clusters,
    }


def _cluster(cluster_id: str, tmc: float, bjp: float, left_congress: float, others: float = 0.0) -> dict:
    """Build a cluster dict using ensemble_detail format (decimal 0-1)."""
    return {
        "id": cluster_id,
        "n_seats": 10,
        "ensemble_detail": [
            {"TMC": tmc, "BJP": bjp, "Left-Congress": left_congress, "Others": others},
            {"TMC": tmc, "BJP": bjp, "Left-Congress": left_congress, "Others": others},
            {"TMC": tmc, "BJP": bjp, "Left-Congress": left_congress, "Others": others},
        ],
        "ensemble_runs": 3,
    }


# ---------------------------------------------------------------------------
# Test 1: stub engine output + stub GT → verify MAE calculated correctly
# ---------------------------------------------------------------------------

class TestBackcastStubEngineStubbedGT:

    def test_backcast_with_stub_engine_output_and_stub_gt(self, tmp_path):
        """
        Acceptance criterion 1: mock both engine output and GT, verify MAE.

        Setup:
          - GT has 2 cluster-like units: 'cluster_a' and 'cluster_b'
          - Engine predicted TMC=0.70/BJP=0.20/LC=0.10 for both (decimal)
          - GT has TMC=80/BJP=10/LC+congress=10 for cluster_a
                   TMC=60/BJP=30/LC+congress=10 for cluster_b
          - Expected MAE for cluster_a: |70-80| + |20-10| + |10-10| / 3 = 20/3 ≈ 6.67pp
          - Expected MAE for cluster_b: |70-60| + |20-30| + |10-10| / 3 = 20/3 ≈ 6.67pp
          - Overall MAE: 6.67pp
        """
        # Build run JSON with 2 clusters
        run_json = _wb_run_json([
            _cluster("cluster_a", tmc=0.70, bjp=0.20, left_congress=0.10),
            _cluster("cluster_b", tmc=0.70, bjp=0.20, left_congress=0.10),
        ])

        run_file = tmp_path / "test_run.json"
        run_file.write_text(json.dumps(run_json))

        # Build stub GT with matching unit_ids
        gt_units = [
            GroundTruthUnit(
                unit_id="cluster_a",
                unit_name="Cluster A",
                outcomes={"tmc_pct": 80.0, "bjp_pct": 10.0, "left_pct": 5.0, "congress_pct": 5.0, "others_pct": 0.0},
                winner="tmc",
                margin_pct=70.0,
            ),
            GroundTruthUnit(
                unit_id="cluster_b",
                unit_name="Cluster B",
                outcomes={"tmc_pct": 60.0, "bjp_pct": 30.0, "left_pct": 5.0, "congress_pct": 5.0, "others_pct": 0.0},
                winner="tmc",
                margin_pct=30.0,
            ),
        ]
        stub_gt = _make_gt(gt_units)

        with patch("popscale.calibration.harness.load_ground_truth", return_value=stub_gt):
            result = asyncio.run(
                backcast("wb_2021_assembly", use_existing_run=str(run_file))
            )

        assert isinstance(result, BacktestResult)
        assert result.election_id == "wb_2021_assembly"
        assert result.engine_run_id == "test_run"

        # Both units covered
        assert result.coverage_pct == pytest.approx(1.0)

        # MAE: each unit has 4 shared keys (tmc_pct, bjp_pct, left_congress_pct, others_pct)
        # cluster_a: |70-80| + |20-10| + |10-10| + |0-0| = 10+10+0+0 = 20 / 4 = 5.0
        # cluster_b: |70-60| + |20-30| + |10-10| + |0-0| = 10+10+0+0 = 20 / 4 = 5.0
        assert result.overall_mae == pytest.approx(5.0, abs=0.01)

        # Directional accuracy: engine predicts TMC winner for both → correct for cluster_a
        # cluster_b GT winner is also tmc (60 > 30) → should be 100%
        assert result.directional_accuracy == pytest.approx(1.0)

        # Brier should be positive
        assert result.brier_score >= 0.0

        # per_unit_errors present
        assert "cluster_a" in result.per_unit_errors
        assert "cluster_b" in result.per_unit_errors
        assert result.per_unit_errors["cluster_a"] == pytest.approx(5.0, abs=0.01)


# ---------------------------------------------------------------------------
# Test 2: partial coverage — engine predicts 2 clusters, GT has 294+ units
# ---------------------------------------------------------------------------

class TestBackcastPartialCoverage:

    def test_backcast_handles_partial_coverage(self, tmp_path):
        """
        Acceptance criterion 3: engine predicts N clusters, GT has M >> N units.

        coverage_pct = N/M, MAE computed only over predicted units, no failure.
        """
        # Run with 2 clusters
        run_json = _wb_run_json([
            _cluster("murshidabad", tmc=0.65, bjp=0.20, left_congress=0.15),
            _cluster("matua_belt", tmc=0.70, bjp=0.25, left_congress=0.05),
        ])
        run_file = tmp_path / "partial_run.json"
        run_file.write_text(json.dumps(run_json))

        # GT has 294 constituency-level units (matching GT structure)
        # Only 2 of these will match cluster IDs
        gt_units = []
        # Two units that match the cluster IDs
        gt_units.append(GroundTruthUnit(
            unit_id="murshidabad",
            unit_name="Murshidabad Cluster",
            outcomes={"tmc_pct": 70.0, "bjp_pct": 18.0, "left_pct": 8.0, "congress_pct": 4.0, "others_pct": 0.0},
            winner="tmc", margin_pct=52.0,
        ))
        gt_units.append(GroundTruthUnit(
            unit_id="matua_belt",
            unit_name="Matua Belt Cluster",
            outcomes={"tmc_pct": 65.0, "bjp_pct": 28.0, "left_pct": 5.0, "congress_pct": 2.0, "others_pct": 0.0},
            winner="tmc", margin_pct=37.0,
        ))
        # 292 other constituency-level units with non-matching IDs
        for i in range(292):
            gt_units.append(GroundTruthUnit(
                unit_id=f"constituency_{i:04d}",
                unit_name=f"Constituency {i}",
                outcomes={"tmc_pct": 55.0, "bjp_pct": 35.0, "left_pct": 5.0, "congress_pct": 3.0, "others_pct": 2.0},
                winner="tmc", margin_pct=20.0,
            ))

        stub_gt = _make_gt(gt_units)

        with patch("popscale.calibration.harness.load_ground_truth", return_value=stub_gt):
            result = asyncio.run(
                backcast("wb_2021_assembly", use_existing_run=str(run_file))
            )

        assert isinstance(result, BacktestResult)

        # Coverage: 2 predicted, 294 total GT units
        assert result.coverage_pct == pytest.approx(2 / 294, abs=0.001)

        # MAE computed only over the 2 matched units — no KeyError, no crash
        assert isinstance(result.overall_mae, float)
        assert result.overall_mae >= 0.0

        # per_unit_errors only for the 2 covered units
        assert len(result.per_unit_errors) == 2
        assert "murshidabad" in result.per_unit_errors
        assert "matua_belt" in result.per_unit_errors

        # predicted and ground_truth dicts only contain matched units
        assert len(result.predicted) == 2
        assert len(result.ground_truth) == 2


# ---------------------------------------------------------------------------
# Test 3: directional accuracy
# ---------------------------------------------------------------------------

class TestBackcastDirectionalAccuracy:

    def test_backcast_directional_accuracy_correct(self, tmp_path):
        """Engine predicts TMC winner, GT has TMC winner → 100% directional accuracy."""
        run_json = _wb_run_json([
            _cluster("unit_x", tmc=0.70, bjp=0.20, left_congress=0.10),
        ])
        run_file = tmp_path / "dir_correct.json"
        run_file.write_text(json.dumps(run_json))

        stub_gt = _make_gt([
            GroundTruthUnit(
                unit_id="unit_x",
                unit_name="Unit X",
                outcomes={"tmc_pct": 65.0, "bjp_pct": 25.0, "left_pct": 5.0, "congress_pct": 3.0, "others_pct": 2.0},
                winner="tmc", margin_pct=40.0,
            )
        ])

        with patch("popscale.calibration.harness.load_ground_truth", return_value=stub_gt):
            result = asyncio.run(
                backcast("wb_2021_assembly", use_existing_run=str(run_file))
            )

        assert result.directional_accuracy == pytest.approx(1.0)

    def test_backcast_directional_accuracy_wrong(self, tmp_path):
        """Engine predicts TMC winner, GT has BJP winner → 0% directional accuracy."""
        # TMC=0.40, BJP=0.50 → engine predicts BJP as winner
        # GT: tmc=65 > bjp=25 → GT winner is tmc
        # So engine winner (bjp) != GT winner (tmc) → directional accuracy = 0%
        run_json = _wb_run_json([
            _cluster("unit_y", tmc=0.40, bjp=0.50, left_congress=0.10),
        ])
        run_file = tmp_path / "dir_wrong.json"
        run_file.write_text(json.dumps(run_json))

        stub_gt = _make_gt([
            GroundTruthUnit(
                unit_id="unit_y",
                unit_name="Unit Y",
                outcomes={"tmc_pct": 65.0, "bjp_pct": 25.0, "left_pct": 5.0, "congress_pct": 3.0, "others_pct": 2.0},
                winner="tmc", margin_pct=40.0,
            )
        ])

        with patch("popscale.calibration.harness.load_ground_truth", return_value=stub_gt):
            result = asyncio.run(
                backcast("wb_2021_assembly", use_existing_run=str(run_file))
            )

        assert result.directional_accuracy == pytest.approx(0.0)

    def test_backcast_directional_accuracy_mixed(self, tmp_path):
        """2 units: engine correct on 1, wrong on 1 → 50% directional accuracy."""
        run_json = _wb_run_json([
            _cluster("unit_correct", tmc=0.70, bjp=0.20, left_congress=0.10),
            _cluster("unit_wrong", tmc=0.40, bjp=0.50, left_congress=0.10),
        ])
        run_file = tmp_path / "dir_mixed.json"
        run_file.write_text(json.dumps(run_json))

        stub_gt = _make_gt([
            GroundTruthUnit(
                unit_id="unit_correct",
                unit_name="Unit Correct",
                outcomes={"tmc_pct": 65.0, "bjp_pct": 25.0, "left_pct": 5.0, "congress_pct": 3.0, "others_pct": 2.0},
                winner="tmc", margin_pct=40.0,
            ),
            GroundTruthUnit(
                unit_id="unit_wrong",
                unit_name="Unit Wrong",
                outcomes={"tmc_pct": 65.0, "bjp_pct": 25.0, "left_pct": 5.0, "congress_pct": 3.0, "others_pct": 2.0},
                winner="tmc", margin_pct=40.0,
            ),
        ])

        with patch("popscale.calibration.harness.load_ground_truth", return_value=stub_gt):
            result = asyncio.run(
                backcast("wb_2021_assembly", use_existing_run=str(run_file))
            )

        assert result.directional_accuracy == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Test 4: unknown election_id raises ValueError
# ---------------------------------------------------------------------------

class TestBackcastRaisesOnUnknownElection:

    def test_backcast_raises_on_unknown_election(self, tmp_path):
        """Invalid election_id must raise ValueError, not silently return empty result."""
        # Create a minimal valid run JSON so we don't fail on file loading first
        run_json = _wb_run_json([_cluster("c1", 0.5, 0.3, 0.2)])
        run_file = tmp_path / "dummy.json"
        run_file.write_text(json.dumps(run_json))

        with pytest.raises(ValueError, match="Unknown election_id"):
            asyncio.run(
                backcast("totally_invalid_election_2099", use_existing_run=str(run_file))
            )


# ---------------------------------------------------------------------------
# Scoring unit tests (separate from harness integration)
# ---------------------------------------------------------------------------

class TestScoringFunctions:

    def test_normalise_gt_outcomes_wb_merges_left_congress(self):
        """WB GT normalisation: left_pct + congress_pct → left_congress_pct."""
        outcomes = {
            "tmc_pct": 60.0,
            "bjp_pct": 20.0,
            "left_pct": 8.0,
            "congress_pct": 7.0,
            "others_pct": 5.0,
        }
        result = normalise_gt_outcomes(outcomes, "wb_2021_assembly")
        assert "left_congress_pct" in result
        assert result["left_congress_pct"] == pytest.approx(15.0)
        assert "left_pct" not in result
        assert "congress_pct" not in result

    def test_normalise_engine_shares_decimal_to_pct(self):
        """Engine decimal (0-1) shares should be converted to percentage."""
        shares = {"TMC": 0.65, "BJP": 0.25, "Left-Congress": 0.10, "Others": 0.0}
        result = normalise_engine_shares(shares, "wb_2021_assembly")
        assert result["tmc_pct"] == pytest.approx(65.0)
        assert result["bjp_pct"] == pytest.approx(25.0)
        assert result["left_congress_pct"] == pytest.approx(10.0)

    def test_normalise_engine_shares_already_pct(self):
        """Engine shares already in pct (>1.5) should not be doubled."""
        shares = {"TMC": 65.0, "BJP": 25.0, "Left-Congress": 10.0, "Others": 0.0}
        result = normalise_engine_shares(shares, "wb_2021_assembly")
        assert result["tmc_pct"] == pytest.approx(65.0)

    def test_compute_mae_basic(self):
        """MAE: |pred - gt| averaged over parties, then over units."""
        predicted = {"u1": {"tmc_pct": 70.0, "bjp_pct": 30.0}}
        gt = {"u1": {"tmc_pct": 60.0, "bjp_pct": 40.0}}
        overall, per_unit = compute_mae(predicted, gt)
        # u1: (|70-60| + |30-40|) / 2 = 20/2 = 10
        assert overall == pytest.approx(10.0)
        assert per_unit["u1"] == pytest.approx(10.0)

    def test_compute_mae_no_overlap(self):
        """MAE returns 0.0 when predicted and GT have no common units."""
        predicted = {"unit_a": {"tmc_pct": 70.0}}
        gt = {"unit_b": {"tmc_pct": 60.0}}
        overall, per_unit = compute_mae(predicted, gt)
        assert overall == pytest.approx(0.0)
        assert per_unit == {}

    def test_compute_directional_accuracy_full(self):
        """All units predicted correctly → 1.0."""
        predicted = {
            "u1": {"tmc_pct": 70.0, "bjp_pct": 30.0},
            "u2": {"tmc_pct": 55.0, "bjp_pct": 45.0},
        }
        gt = {
            "u1": {"tmc_pct": 65.0, "bjp_pct": 35.0},  # tmc wins in both
            "u2": {"tmc_pct": 52.0, "bjp_pct": 48.0},
        }
        assert compute_directional_accuracy(predicted, gt) == pytest.approx(1.0)

    def test_compute_directional_accuracy_none(self):
        """All units predicted wrong → 0.0."""
        predicted = {
            "u1": {"tmc_pct": 30.0, "bjp_pct": 70.0},  # engine: bjp wins
        }
        gt = {
            "u1": {"tmc_pct": 65.0, "bjp_pct": 35.0},  # gt: tmc wins
        }
        assert compute_directional_accuracy(predicted, gt) == pytest.approx(0.0)
