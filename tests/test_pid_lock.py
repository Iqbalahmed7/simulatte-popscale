from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

from benchmarks.wb_2026.constituency import wb_2026_constituency_benchmark as bench


def test_acquire_pid_lock_blocks_duplicate_active_process(monkeypatch, tmp_path):
    monkeypatch.setattr(bench, "PID_DIR", tmp_path)
    pid_path = tmp_path / "murshidabad.pid"
    pid_path.write_text("99999", encoding="utf-8")

    monkeypatch.setattr(bench.os, "kill", lambda *_: None)

    try:
        bench.acquire_pid_lock("murshidabad")
        assert False, "Expected SystemExit for duplicate active PID lock"
    except SystemExit as exc:
        assert exc.code == 1


def test_acquire_pid_lock_overwrites_stale_pid(monkeypatch, tmp_path):
    monkeypatch.setattr(bench, "PID_DIR", tmp_path)
    pid_path = tmp_path / "kolkata_urban.pid"
    pid_path.write_text("123456", encoding="utf-8")

    def _kill(pid: int, sig: int):
        raise ProcessLookupError(pid)

    monkeypatch.setattr(bench.os, "kill", _kill)

    locked = bench.acquire_pid_lock("kolkata_urban")
    assert locked.exists()
    assert int(locked.read_text().strip()) == bench.os.getpid()


def test_find_benchmark_pids_filters_cluster(monkeypatch):
    script_path = Path(__file__).parents[1] / "scripts" / "kill_prior_runs.py"
    spec = importlib.util.spec_from_file_location("kill_prior_runs", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    fake_stdout = "\n".join([
        "PID COMMAND",
        "101 python3 -m benchmarks.wb_2026.constituency.wb_2026_constituency_benchmark --cluster matua_belt",
        "202 python3 -m benchmarks.wb_2026.constituency.wb_2026_constituency_benchmark --cluster murshidabad",
        "303 python3 something_else.py",
    ])

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_, **__: subprocess.CompletedProcess(args=[], returncode=0, stdout=fake_stdout, stderr=""),
    )

    assert module.find_benchmark_pids(None) == [101, 202]
    assert module.find_benchmark_pids("matua_belt") == [101]
