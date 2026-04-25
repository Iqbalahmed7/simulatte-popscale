"""Append-only JSONL event emitter for run observability."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _default_runs_root() -> Path:
    return Path(
        Path.home()
        / ".simulatte"
        / "runs"
    )


@dataclass
class RunEventEmitter:
    run_id: str
    runs_root: Path | None = None

    def __post_init__(self) -> None:
        self.runs_root = (self.runs_root or _default_runs_root()).resolve()
        self.run_dir = self.runs_root / self.run_id
        self.events_path = self.run_dir / "events.jsonl"
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def emit(self, event_type: str, **payload: Any) -> dict[str, Any]:
        event: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "unix_ts": time.time(),
            "type": event_type,
            "run_id": self.run_id,
        }
        event.update(payload)
        with self.events_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=True) + "\n")
        return event


def read_events(
    run_id: str,
    *,
    since: float | None = None,
    runs_root: Path | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    root = (runs_root or _default_runs_root()).resolve()
    events_path = root / run_id / "events.jsonl"
    if not events_path.exists():
        return []
    out: list[dict[str, Any]] = []
    threshold = since if since is not None else float("-inf")
    with events_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            if float(event.get("unix_ts", 0.0)) <= threshold:
                continue
            out.append(event)
    if limit is not None:
        out = out[-limit:]
    return out


def list_runs(*, runs_root: Path | None = None, days: int = 30) -> list[dict[str, Any]]:
    root = (runs_root or _default_runs_root()).resolve()
    if not root.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows: list[dict[str, Any]] = []
    for run_dir in sorted(root.iterdir()):
        if not run_dir.is_dir():
            continue
        events_path = run_dir / "events.jsonl"
        if not events_path.exists():
            continue
        mtime = datetime.fromtimestamp(events_path.stat().st_mtime, tz=timezone.utc)
        if mtime < cutoff:
            continue
        events = read_events(run_dir.name, runs_root=root, limit=50)
        status = "RUNNING"
        if events:
            if events[-1]["type"] == "run_completed":
                status = "COMPLETED"
            elif events[-1]["type"] == "error":
                status = "FAILED"
        rows.append(
            {
                "run_id": run_dir.name,
                "status": status,
                "updated_at": mtime.isoformat(),
                "event_count": len(events),
            }
        )
    rows.sort(key=lambda r: r["updated_at"], reverse=True)
    return rows
