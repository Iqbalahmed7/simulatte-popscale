from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_POPSCALE_ROOT = Path(__file__).resolve().parents[4]
if str(_POPSCALE_ROOT) not in sys.path:
    sys.path.insert(0, str(_POPSCALE_ROOT))

from benchmarks.wb_2026.constituency import wb_2026_constituency_benchmark as bench


class _FakeMonitor:
    buffer_usd = 10.0

    def __init__(self) -> None:
        self._halt = False

    async def preflight_check(self, *, run_id: str | None = None) -> float:
        return 99.0

    async def start_background_monitor(self) -> None:
        return None

    async def stop_background_monitor(self) -> None:
        return None

    def update_progress(self, **_: object) -> None:
        return None

    def is_halt_requested(self) -> bool:
        return self._halt

    def halt_snapshot(self) -> dict:
        return {"reason": "halted in test"}


def _cluster(cluster_id: str, swing: bool) -> dict:
    return {
        "id": cluster_id,
        "name": cluster_id,
        "n_seats": 1,
        "n_personas": 1,
        "domain": "POLITICAL",
        "context_note": "note",
        "tmc_2021": 0.5,
        "bjp_2021": 0.3,
        "left_2021": 0.1,
        "others_2021": 0.1,
        "swing_notes": "swing" if swing else "stable",
        "key_seats": [],
    }


def _result_for_cluster(cluster_id: str) -> dict:
    return {
        "id": cluster_id,
        "name": cluster_id,
        "n_seats": 1,
        "n_personas": 1,
        "tmc_2021": 0.5,
        "bjp_2021": 0.3,
        "left_2021": 0.1,
        "others_2021": 0.1,
        "sim_tmc": 0.51,
        "sim_bjp": 0.29,
        "sim_left": 0.1,
        "sim_others": 0.1,
        "swing_notes": "stable",
        "key_seats": [],
        "ensemble_runs": 1,
        "ensemble_runs_complete": 1,
        "ensemble_runs_total": 1,
        "is_partial": False,
        "gate_waivers": [],
        "confidence_penalty": 0.0,
    }


def test_resume_skips_completed_clusters(monkeypatch, tmp_path: Path):
    c1 = _cluster("a_complete", swing=False)
    c2 = _cluster("b_pending", swing=False)
    monkeypatch.setattr(bench, "CLUSTERS", [c1, c2])
    monkeypatch.setattr(bench, "SWING_CLUSTER_IDS", set())
    monkeypatch.setattr(bench, "get_credit_monitor", lambda: _FakeMonitor())

    calls: list[str] = []

    async def _fake_run_cluster(cluster: dict, manifesto: str | None = None, emitter=None) -> dict:
        _ = manifesto
        _ = emitter
        calls.append(cluster["id"])
        return _result_for_cluster(cluster["id"])

    monkeypatch.setattr(bench, "run_cluster", _fake_run_cluster)
    monkeypatch.setenv("SIMULATTE_PARTIAL_DIR", str(tmp_path))

    partial = {
        "run_id": "resume_test_1",
        "is_partial": True,
        "cluster_results": [_result_for_cluster("a_complete")],
    }
    resume_path = tmp_path / "resume.json"
    resume_path.write_text(json.dumps(partial), encoding="utf-8")

    results = asyncio.run(bench.run_all_clusters(resume_from=resume_path))

    assert calls == ["b_pending"]
    assert [row["id"] for row in results["cluster_results"]] == ["a_complete", "b_pending"]


def test_resume_from_ensemble_partial_only_runs_remaining(monkeypatch, tmp_path: Path):
    swing = _cluster("swing_cluster", swing=True)
    monkeypatch.setattr(bench, "CLUSTERS", [swing])
    monkeypatch.setattr(bench, "SWING_CLUSTER_IDS", {"swing_cluster"})
    monkeypatch.setattr(bench, "get_credit_monitor", lambda: _FakeMonitor())
    monkeypatch.setenv("SIMULATTE_PARTIAL_DIR", str(tmp_path))

    run_calls = {"n": 0}

    async def _fake_run_niobe_study(_request):
        run_calls["n"] += 1
        decision = "TMC (Trinamool Congress — Mamata Banerjee)"
        return SimpleNamespace(
            simulation=SimpleNamespace(responses=[SimpleNamespace(decision=decision)]),
            cohort=SimpleNamespace(gate_waivers=[], confidence_penalty=0.0),
        )

    monkeypatch.setattr(bench, "run_niobe_study", _fake_run_niobe_study)

    partial = {
        "run_id": "resume_test_2",
        "is_partial": True,
        "cluster_results": [
            {
                "id": "swing_cluster",
                "name": "swing_cluster",
                "n_seats": 1,
                "n_personas": 2,
                "tmc_2021": 0.5,
                "bjp_2021": 0.3,
                "left_2021": 0.1,
                "others_2021": 0.1,
                "sim_tmc": 0.6,
                "sim_bjp": 0.2,
                "sim_left": 0.1,
                "sim_others": 0.1,
                "swing_notes": "swing",
                "key_seats": [],
                "ensemble_runs": 3,
                "ensemble_runs_complete": 2,
                "ensemble_runs_total": 3,
                "ensemble_runs_data": [
                    {"run_index": 1, "shares": {"TMC": 0.6, "BJP": 0.2, "Left-Congress": 0.1, "Others": 0.1}},
                    {"run_index": 2, "shares": {"TMC": 0.6, "BJP": 0.2, "Left-Congress": 0.1, "Others": 0.1}},
                ],
                "is_partial": True,
                "gate_waivers": [],
                "confidence_penalty": 0.0,
            }
        ],
    }
    resume_path = tmp_path / "resume_ensemble.json"
    resume_path.write_text(json.dumps(partial), encoding="utf-8")

    results = asyncio.run(bench.run_all_clusters(resume_from=resume_path))

    assert run_calls["n"] == 1
    row = results["cluster_results"][0]
    assert row["ensemble_runs_complete"] == 3
    assert row["ensemble_runs_total"] == 3
    assert row["is_partial"] is False


# ── BRIEF-014 new tests ───────────────────────────────────────────────────────

def test_concurrent_cluster_execution(monkeypatch, tmp_path: Path):
    """3 mock clusters run concurrently via asyncio.gather; all complete."""
    c1 = _cluster("alpha", swing=False)
    c2 = _cluster("beta", swing=False)
    c3 = _cluster("gamma", swing=False)
    monkeypatch.setattr(bench, "CLUSTERS", [c1, c2, c3])
    monkeypatch.setattr(bench, "SWING_CLUSTER_IDS", set())
    monkeypatch.setattr(bench, "get_credit_monitor", lambda: _FakeMonitor())
    monkeypatch.setenv("SIMULATTE_PARTIAL_DIR", str(tmp_path))

    started_at: dict[str, float] = {}
    import time as _time

    async def _fake_run_cluster(cluster: dict, manifesto=None, emitter=None) -> dict:
        started_at[cluster["id"]] = _time.monotonic()
        # Yield control so all 3 can start before any finishes
        await asyncio.sleep(0)
        return _result_for_cluster(cluster["id"])

    monkeypatch.setattr(bench, "run_cluster", _fake_run_cluster)

    results = asyncio.run(
        bench.run_all_clusters(cluster_concurrency=3, ensemble_concurrency=3)
    )

    completed_ids = {r["id"] for r in results["cluster_results"]}
    assert completed_ids == {"alpha", "beta", "gamma"}
    # All 3 should have started (concurrency > 1 means they all got the semaphore)
    assert len(started_at) == 3


def test_concurrent_partial_write_atomicity(monkeypatch, tmp_path: Path):
    """5 concurrent writers to the per-cluster directory don't corrupt each other."""
    pdir = tmp_path / "run_xyz.partial"
    pdir.mkdir()
    bench._write_manifest(pdir, "run_xyz", 5)

    async def _write_all() -> None:
        tasks = []
        for i in range(5):
            cluster_id = f"cluster_{i}"
            row = _result_for_cluster(cluster_id)
            # Wrap the sync write in a coroutine so gather can run them
            async def _w(cid: str = cluster_id, r: dict = row) -> None:
                bench._write_cluster_subfile(pdir, cid, r)
                await asyncio.sleep(0)  # yield to simulate interleaving
            tasks.append(_w())
        await asyncio.gather(*tasks)

    asyncio.run(_write_all())

    # All 5 sub-files should be present and parseable
    written = sorted(pdir.glob("cluster_*.json"))
    assert len(written) == 5
    for p in written:
        data = json.loads(p.read_text(encoding="utf-8"))
        assert "id" in data

    # Manifest should still be intact
    manifest = json.loads((pdir / "_manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_id"] == "run_xyz"
    assert manifest["total_clusters"] == 5


def test_failure_isolation(monkeypatch, tmp_path: Path):
    """One cluster raises an exception; the other two still produce results.

    The run completes without raising because the two good clusters are marked
    complete. Failed clusters are surfaced in result["failed_clusters"], and
    their sub-files are absent from the partial directory while the good
    clusters' sub-files are present.
    """
    c1 = _cluster("good_1", swing=False)
    c2 = _cluster("bad_one", swing=False)
    c3 = _cluster("good_2", swing=False)
    monkeypatch.setattr(bench, "CLUSTERS", [c1, c2, c3])
    monkeypatch.setattr(bench, "SWING_CLUSTER_IDS", set())
    monkeypatch.setattr(bench, "get_credit_monitor", lambda: _FakeMonitor())
    monkeypatch.setenv("SIMULATTE_PARTIAL_DIR", str(tmp_path))

    # Stub compute_seat_predictions so we don't need real seat data for 2 clusters
    monkeypatch.setattr(bench, "compute_seat_predictions", lambda *a, **kw: {
        "schema_version": "2.0",
        "seat_predictions": {"TMC": 0, "BJP": 0, "Left-Congress": 0, "Others": 0},
        "cluster_breakdown": [],
        "swing_analysis": [],
        "total_marginal_seats": 0,
        "confidence_range_seats": 5,
        "tmc_majority": False,
        "is_partial": False,
        "gate_waivers": [],
    })

    async def _fake_run_cluster(cluster: dict, manifesto=None, emitter=None) -> dict:
        if cluster["id"] == "bad_one":
            raise RuntimeError("simulated cluster failure")
        return _result_for_cluster(cluster["id"])

    monkeypatch.setattr(bench, "run_cluster", _fake_run_cluster)

    # run_all_clusters should complete without raising: good_1 and good_2 are
    # complete; bad_one's failure is isolated and recorded in failed_clusters.
    results = asyncio.run(
        bench.run_all_clusters(cluster_concurrency=3, ensemble_concurrency=3)
    )

    # Both good clusters are in the results
    completed_ids = {r["id"] for r in results["cluster_results"]}
    assert "good_1" in completed_ids
    assert "good_2" in completed_ids
    assert "bad_one" not in completed_ids

    # Failed cluster is surfaced in the result dict
    assert results.get("failed_clusters") == ["bad_one"]

    # Per-cluster sub-files exist for the good clusters in the partial directory
    partial_dirs = list(tmp_path.glob("*.partial"))
    assert partial_dirs, "Expected at least one partial directory"
    pdir = partial_dirs[0]
    written_ids = {p.stem.replace("cluster_", "") for p in pdir.glob("cluster_*.json")}
    assert "good_1" in written_ids
    assert "good_2" in written_ids


def test_partial_writes_are_atomic(monkeypatch, tmp_path: Path):
    partial_path = tmp_path / "atomic.partial.json"
    original = {"run_id": "old", "status": "in_progress", "cluster_results": []}
    partial_path.write_text(json.dumps(original), encoding="utf-8")

    monkeypatch.setattr(bench, "compute_seat_predictions", lambda *args, **kwargs: {
        "schema_version": "2.0",
        "seat_predictions": {"TMC": 0, "BJP": 0, "Left-Congress": 0, "Others": 0},
        "cluster_breakdown": [],
        "swing_analysis": [],
        "total_marginal_seats": 0,
        "confidence_range_seats": 5,
        "tmc_majority": False,
        "is_partial": True,
        "gate_waivers": [],
    })

    def _explode_replace(_src: Path, _dst: Path) -> None:
        raise OSError("simulated crash before replace")

    monkeypatch.setattr(bench.os, "replace", _explode_replace)

    with pytest.raises(OSError):
        bench._write_partial_results(
            partial_path,
            run_id="new",
            cluster_results=[],
            status="in_progress",
            is_partial=True,
        )

    persisted = json.loads(partial_path.read_text(encoding="utf-8"))
    assert persisted == original
