"""popscale/observability/alerts.py — BRIEF-024 alert polling for events.jsonl.

Provides alert_on(metric, threshold, window) which reads a rolling window of
events from events.jsonl and fires an ntfy push notification when the metric
crosses the threshold.

Supported metrics:
  - "error_rate"    — fraction of events with type=="error" in window (fires when > threshold)
  - "burn_rate"     — ratio of cost_usd_spent to cost_usd_estimated in window (fires when > threshold)
  - "p99_latency_s" — 99th-percentile duration_seconds in window (fires when > threshold)

Usage:
    from popscale.observability.alerts import alert_on

    fired = alert_on("error_rate", threshold=0.05, window=300)
    fired = alert_on("burn_rate", threshold=2.0, window=300)
    fired = alert_on("p99_latency_s", threshold=30.0, window=300)
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

import httpx

from popscale.observability.emitter import _default_runs_root, read_events

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ntfy config — same env vars as BRIEF-004 CreditMonitor
# ---------------------------------------------------------------------------
_NTFY_TOPIC = os.getenv("SIMULATTE_NTFY_TOPIC", "")
_NTFY_BASE_URL = os.getenv("SIMULATTE_NTFY_BASE_URL", "https://ntfy.sh").rstrip("/")


def _fire_ntfy(title: str, message: str) -> None:
    """POST a push notification via ntfy. No-op when topic not configured."""
    if not _NTFY_TOPIC:
        logger.warning(
            "alert_on: ntfy topic not set; skipping notification. "
            "Set SIMULATTE_NTFY_TOPIC."
        )
        return
    url = f"{_NTFY_BASE_URL}/{_NTFY_TOPIC}"
    try:
        with httpx.Client(timeout=10.0) as client:
            client.post(url, content=message.encode("utf-8"), headers={"Title": title})
    except Exception as exc:
        logger.warning("alert_on: failed to send ntfy notification: %s", exc)


# ---------------------------------------------------------------------------
# Metric computers
# ---------------------------------------------------------------------------

def _error_rate(events: list[dict[str, Any]]) -> float:
    """Fraction of events whose type is 'error'."""
    if not events:
        return 0.0
    return sum(1 for e in events if e.get("type") == "error") / len(events)


def _burn_rate(events: list[dict[str, Any]]) -> float:
    """Ratio of actual cost_usd_spent to cost_usd_estimated across window events.

    Returns 0.0 when no estimate is present (cannot compute ratio).
    """
    total_spent = sum(float(e["cost_usd_spent"]) for e in events if "cost_usd_spent" in e)
    total_estimated = sum(float(e["cost_usd_estimated"]) for e in events if "cost_usd_estimated" in e)
    if total_estimated == 0.0:
        return 0.0
    return total_spent / total_estimated


def _p99_latency(events: list[dict[str, Any]]) -> float:
    """99th-percentile of duration_seconds across window events."""
    durations = sorted(float(e["duration_seconds"]) for e in events if "duration_seconds" in e)
    if not durations:
        return 0.0
    idx = max(0, int(len(durations) * 0.99) - 1)
    return durations[idx]


_METRIC_FNS = {
    "error_rate": _error_rate,
    "burn_rate": _burn_rate,
    "p99_latency_s": _p99_latency,
}

_METRIC_LABELS = {
    "error_rate": "Error rate",
    "burn_rate": "Burn rate",
    "p99_latency_s": "p99 latency (s)",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def alert_on(
    metric: str,
    threshold: float,
    window: float,
    *,
    run_id: str | None = None,
    runs_root: Path | None = None,
) -> bool:
    """Poll events.jsonl over a rolling window and fire ntfy if threshold crossed.

    Args:
        metric:     One of "error_rate", "burn_rate", "p99_latency_s".
        threshold:  Fires when computed value > threshold.
        window:     Rolling window in seconds (e.g. 300 = last 5 min).
        run_id:     Specific run to inspect. When None, scans all runs under
                    runs_root and aggregates events.
        runs_root:  Override default ~/.simulatte/runs directory.

    Returns:
        True if the alert fired (threshold was crossed), False otherwise.
    """
    if metric not in _METRIC_FNS:
        raise ValueError(f"Unknown metric '{metric}'. Choose from: {list(_METRIC_FNS)}")

    since = time.time() - window
    events = _collect_events(run_id=run_id, since=since, runs_root=runs_root)

    value = _METRIC_FNS[metric](events)
    fired = value > threshold

    if fired:
        label = _METRIC_LABELS[metric]
        title = f"Simulatte alert: {label} threshold crossed"
        message = (
            f"{label} = {value:.4f} exceeded threshold {threshold}\n"
            f"window={window}s  events_in_window={len(events)}\n"
            f"run_id={run_id or 'all'}"
        )
        logger.warning("alert_on[%s]: %s", metric, message)
        _fire_ntfy(title=title, message=message)

    return fired


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _collect_events(
    *,
    run_id: str | None,
    since: float,
    runs_root: Path | None,
) -> list[dict[str, Any]]:
    """Collect windowed events from one run or all runs."""
    if run_id is not None:
        return read_events(run_id, since=since, runs_root=runs_root)

    root = (runs_root or _default_runs_root()).resolve()
    if not root.exists():
        return []
    all_events: list[dict[str, Any]] = []
    for run_dir in root.iterdir():
        if run_dir.is_dir():
            all_events.extend(read_events(run_dir.name, since=since, runs_root=root))
    return all_events
