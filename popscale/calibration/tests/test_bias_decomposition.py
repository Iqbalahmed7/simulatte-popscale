"""
Tests for BRIEF-020: bias_decomposition.py

Four tests covering each decomposition axis:
  1. by_region         — per-unit MAE passthrough
  2. by_demographic    — sliced by religion axis
  3. by_confidence_band — high/low split at 0.60 threshold
  4. largest_errors + recommendations — top-N and generated text
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from popscale.calibration.bias_decomposition import (
    BiasReport,
    decompose_bias,
    _HIGH_CONF_THRESHOLD,
)
from popscale.calibration.harness import BacktestResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_backtest(per_unit_errors: dict[str, float]) -> BacktestResult:
    """Build a minimal BacktestResult from a per_unit_errors dict."""
    overall_mae = (
        sum(per_unit_errors.values()) / len(per_unit_errors)
        if per_unit_errors else 0.0
    )
    # Dummy ground_truth / predicted — not used by decompose_bias
    units = {uid: {"tmc_pct": 50.0, "bjp_pct": 50.0} for uid in per_unit_errors}
    return BacktestResult(
        election_id="wb_2021_assembly",
        engine_run_id="test_run",
        ground_truth=units,
        predicted=units,
        overall_mae=overall_mae,
        per_unit_errors=per_unit_errors,
        brier_score=0.0,
        directional_accuracy=1.0,
        coverage_pct=1.0,
        metadata={},
    )


def _persona_file(records: list[dict], tmp_path: Path) -> Path:
    """Write persona records to a temp JSON file and return the path."""
    p = tmp_path / "personas.json"
    p.write_text(json.dumps(records), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Test 1: by_region decomposition
# ---------------------------------------------------------------------------

def test_by_region_matches_per_unit_errors(tmp_path):
    """by_region should be a direct copy of BacktestResult.per_unit_errors."""
    errors = {"murshidabad": 4.5, "malda": 2.1, "kolkata_urban": 1.0}
    bt = _make_backtest(errors)
    # No persona data — we test region axis in isolation
    report = decompose_bias(bt, tmp_path / "nonexistent_personas.json")

    assert isinstance(report, BiasReport)
    assert report.by_region == errors
    assert report.overall_mae == pytest.approx(bt.overall_mae)


# ---------------------------------------------------------------------------
# Test 2: by_demographic decomposition (religion axis)
# ---------------------------------------------------------------------------

def test_by_demographic_religion_axis(tmp_path):
    """Personas with different religion values should produce separate MAE cells."""
    errors = {
        "murshidabad": 4.5,   # mostly muslim personas
        "malda": 3.0,          # mixed
        "kolkata_urban": 1.2,  # mostly hindu
    }
    bt = _make_backtest(errors)

    personas = [
        # murshidabad — muslim
        {"persona_id": "p1", "cluster_id": "murshidabad", "confidence": 0.7, "religion": "muslim"},
        {"persona_id": "p2", "cluster_id": "murshidabad", "confidence": 0.65, "religion": "muslim"},
        # malda — mixed
        {"persona_id": "p3", "cluster_id": "malda", "confidence": 0.55, "religion": "muslim"},
        {"persona_id": "p4", "cluster_id": "malda", "confidence": 0.5, "religion": "hindu"},
        # kolkata_urban — hindu
        {"persona_id": "p5", "cluster_id": "kolkata_urban", "confidence": 0.8, "religion": "hindu"},
        {"persona_id": "p6", "cluster_id": "kolkata_urban", "confidence": 0.75, "religion": "hindu"},
    ]

    report = decompose_bias(bt, _persona_file(personas, tmp_path))

    assert "religion" in report.by_demographic

    religion = report.by_demographic["religion"]
    assert "muslim" in religion
    assert "hindu" in religion

    # muslim cells: 2 personas in murshidabad (4.5 each) + 1 in malda (3.0)
    # aggregated per-persona: [4.5, 4.5, 3.0] → mean = 4.0
    expected_muslim = (4.5 + 4.5 + 3.0) / 3
    assert religion["muslim"] == pytest.approx(expected_muslim)

    # hindu cells: 1 persona in malda (3.0) + 2 in kolkata_urban (1.2 each)
    # aggregated per-persona: [3.0, 1.2, 1.2] → mean = 1.8
    expected_hindu = (3.0 + 1.2 + 1.2) / 3
    assert religion["hindu"] == pytest.approx(expected_hindu)

    # Muslim should have higher MAE than Hindu
    assert religion["muslim"] > religion["hindu"]


# ---------------------------------------------------------------------------
# Test 3: by_confidence_band decomposition
# ---------------------------------------------------------------------------

def test_by_confidence_band_split(tmp_path):
    """Clusters with mean confidence >= 0.60 go to high_conf, others to low_conf."""
    errors = {
        "high_cluster_a": 1.5,   # mean conf will be > 0.60
        "high_cluster_b": 2.0,   # mean conf will be > 0.60
        "low_cluster_c": 5.5,    # mean conf will be < 0.60
    }
    bt = _make_backtest(errors)

    personas = [
        # high_cluster_a — high confidence
        {"persona_id": "a1", "cluster_id": "high_cluster_a", "confidence": 0.80},
        {"persona_id": "a2", "cluster_id": "high_cluster_a", "confidence": 0.75},
        # high_cluster_b — high confidence
        {"persona_id": "b1", "cluster_id": "high_cluster_b", "confidence": 0.70},
        {"persona_id": "b2", "cluster_id": "high_cluster_b", "confidence": 0.65},
        # low_cluster_c — low confidence
        {"persona_id": "c1", "cluster_id": "low_cluster_c", "confidence": 0.40},
        {"persona_id": "c2", "cluster_id": "low_cluster_c", "confidence": 0.35},
    ]

    report = decompose_bias(bt, _persona_file(personas, tmp_path))

    assert "high_conf" in report.by_confidence_band
    assert "low_conf" in report.by_confidence_band

    expected_high = (1.5 + 2.0) / 2
    expected_low = 5.5

    assert report.by_confidence_band["high_conf"] == pytest.approx(expected_high)
    assert report.by_confidence_band["low_conf"] == pytest.approx(expected_low)

    # Low confidence clusters should have higher MAE than high confidence
    assert report.by_confidence_band["low_conf"] > report.by_confidence_band["high_conf"]


# ---------------------------------------------------------------------------
# Test 4: largest_errors, recommendations, and to_markdown
# ---------------------------------------------------------------------------

def test_largest_errors_and_recommendations(tmp_path):
    """Top-10 unit errors sorted descending; recommendations mention worst cluster."""
    # Create 12 clusters so top-10 truncation is tested
    errors = {f"cluster_{i:02d}": float(i) for i in range(1, 13)}
    bt = _make_backtest(errors)

    # Persona data with religion so recommendations can fire demographic rec
    personas = [
        {"persona_id": "x1", "cluster_id": "cluster_12", "confidence": 0.30, "religion": "tribal"},
        {"persona_id": "x2", "cluster_id": "cluster_12", "confidence": 0.35, "religion": "tribal"},
        {"persona_id": "x3", "cluster_id": "cluster_01", "confidence": 0.80, "religion": "hindu"},
        {"persona_id": "x4", "cluster_id": "cluster_01", "confidence": 0.85, "religion": "hindu"},
    ]

    report = decompose_bias(bt, _persona_file(personas, tmp_path))

    # largest_errors — exactly 10 entries
    assert len(report.largest_errors) == 10

    # Sorted descending
    maes = [mae for _, mae in report.largest_errors]
    assert maes == sorted(maes, reverse=True)

    # cluster_12 (mae=12.0) must be first
    assert report.largest_errors[0][0] == "cluster_12"
    assert report.largest_errors[0][1] == pytest.approx(12.0)

    # cluster_03 (mae=3.0) must be cut off (only top 10 of 12 clusters survive,
    # so cluster_01 and cluster_02 are excluded)
    top_10_ids = {uid for uid, _ in report.largest_errors}
    assert "cluster_01" not in top_10_ids
    assert "cluster_02" not in top_10_ids

    # Recommendations — non-empty and contain actionable text
    assert len(report.recommendations) > 0

    # to_markdown renders without error and contains expected sections
    md = report.to_markdown()
    assert "# Bias Decomposition Report" in md
    assert "## Error by Region" in md
    assert "## Error by Confidence Band" in md
    assert "## Largest Unit-Level Errors" in md
    assert "## Recommendations" in md
    assert "cluster_12" in md
