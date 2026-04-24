"""Kill PopScale benchmark processes and clean orphaned PID files.

Usage:
    python3 popscale/scripts/kill_prior_runs.py
    python3 popscale/scripts/kill_prior_runs.py --cluster murshidabad
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
from pathlib import Path

PID_DIR = Path("/tmp/simulatte_runs")


def find_benchmark_pids(cluster_filter: str | None = None) -> list[int]:
    """Use `ps` output to find running WB benchmark processes."""
    result = subprocess.run(
        ["ps", "-eo", "pid,command"],
        check=False,
        capture_output=True,
        text=True,
    )
    pids: list[int] = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.strip().split(maxsplit=1)
        if len(parts) != 2:
            continue
        pid_str, cmd = parts
        if "wb_2026_constituency_benchmark" not in cmd:
            continue
        if cluster_filter and f"--cluster {cluster_filter}" not in cmd:
            continue
        try:
            pids.append(int(pid_str))
        except ValueError:
            continue
    return pids


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster", default=None, help="Kill only one cluster run")
    args = parser.parse_args()

    pids = find_benchmark_pids(args.cluster)
    print(f"Found {len(pids)} matching benchmark processes")
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
            print(f"  Killed PID {pid}")
        except ProcessLookupError:
            print(f"  PID {pid} already gone")

    if PID_DIR.exists():
        for pid_file in PID_DIR.glob("*.pid"):
            if args.cluster and pid_file.stem != args.cluster:
                continue
            pid_file.unlink(missing_ok=True)
            print(f"  Removed stale PID file {pid_file.name}")


if __name__ == "__main__":
    main()
