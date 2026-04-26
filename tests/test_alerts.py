"""tests/test_alerts.py — BRIEF-024 alert threshold tests for alert_on()."""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from popscale.observability.alerts import alert_on


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_events(run_dir: Path, events: list[dict]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    now = time.time()
    with (run_dir / "events.jsonl").open("w", encoding="utf-8") as f:
        for i, ev in enumerate(events):
            ev.setdefault("unix_ts", now - i)
            ev.setdefault("run_id", run_dir.name)
            f.write(json.dumps(ev) + "\n")


# ---------------------------------------------------------------------------
# error_rate tests
# ---------------------------------------------------------------------------

def test_error_rate_fires_above_threshold(tmp_path):
    """alert_on fires when error fraction exceeds threshold (5%)."""
    run_dir = tmp_path / "run-001"
    events = [{"type": "error"}] * 6 + [{"type": "api_call"}] * 94  # 6% error rate
    _write_events(run_dir, events)

    with patch("popscale.observability.alerts._fire_ntfy") as mock_ntfy:
        fired = alert_on("error_rate", threshold=0.05, window=300, run_id="run-001", runs_root=tmp_path)

    assert fired is True
    mock_ntfy.assert_called_once()
    title = mock_ntfy.call_args.kwargs.get("title", "")
    assert "Error rate" in title or "error_rate" in title


def test_error_rate_does_not_fire_below_threshold(tmp_path):
    """alert_on returns False when error rate is below threshold."""
    run_dir = tmp_path / "run-002"
    events = [{"type": "error"}] * 3 + [{"type": "api_call"}] * 97  # 3% error rate
    _write_events(run_dir, events)

    with patch("popscale.observability.alerts._fire_ntfy") as mock_ntfy:
        fired = alert_on("error_rate", threshold=0.05, window=300, run_id="run-002", runs_root=tmp_path)

    assert fired is False
    mock_ntfy.assert_not_called()


# ---------------------------------------------------------------------------
# burn_rate tests
# ---------------------------------------------------------------------------

def test_burn_rate_fires_above_threshold(tmp_path):
    """alert_on fires when burn rate (actual/estimated) exceeds 2x threshold."""
    run_dir = tmp_path / "run-003"
    events = [
        {"type": "api_call", "cost_usd_spent": 0.10, "cost_usd_estimated": 0.04},  # 2.5x
        {"type": "api_call", "cost_usd_spent": 0.08, "cost_usd_estimated": 0.03},  # ~2.67x
    ]
    _write_events(run_dir, events)

    with patch("popscale.observability.alerts._fire_ntfy") as mock_ntfy:
        fired = alert_on("burn_rate", threshold=2.0, window=300, run_id="run-003", runs_root=tmp_path)

    assert fired is True
    mock_ntfy.assert_called_once()


def test_burn_rate_does_not_fire_below_threshold(tmp_path):
    """alert_on returns False when burn rate is at or below threshold."""
    run_dir = tmp_path / "run-004"
    events = [
        {"type": "api_call", "cost_usd_spent": 0.05, "cost_usd_estimated": 0.04},  # 1.25x
        {"type": "api_call", "cost_usd_spent": 0.06, "cost_usd_estimated": 0.05},  # 1.2x
    ]
    _write_events(run_dir, events)

    with patch("popscale.observability.alerts._fire_ntfy") as mock_ntfy:
        fired = alert_on("burn_rate", threshold=2.0, window=300, run_id="run-004", runs_root=tmp_path)

    assert fired is False
    mock_ntfy.assert_not_called()


# ---------------------------------------------------------------------------
# Unknown metric guard
# ---------------------------------------------------------------------------

def test_alert_on_raises_for_unknown_metric(tmp_path):
    """alert_on raises ValueError for unrecognised metric names."""
    with pytest.raises(ValueError, match="Unknown metric"):
        alert_on("made_up_metric", threshold=1.0, window=60, runs_root=tmp_path)
