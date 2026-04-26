"""wb_2026_constituency_benchmark.py — B-WB-6

West Bengal 2026 Assembly Election — Constituency-Level PopScale Prediction.

Runs 10 demographic cluster pools (20 personas each, 200 total) through
the PopScale electoral scenario and converts cluster vote shares to a
294-seat prediction using a uniform swing model.

USAGE
-----
    # Dry run — show config, no API calls:
    python3 wb_2026_constituency_benchmark.py --dry-run

    # Full run (200 personas, ~$10-15):
    python3 wb_2026_constituency_benchmark.py

    # Single cluster test (fast, ~$2):
    python3 wb_2026_constituency_benchmark.py --cluster murshidabad

    # Load existing results:
    python3 wb_2026_constituency_benchmark.py --results-file results/wb_2026_constituency_<run_id>.json

    # Seat model only (from existing results file):
    python3 wb_2026_constituency_benchmark.py --seat-model-only results/wb_2026_constituency_<run_id>.json
"""
from __future__ import annotations

import argparse
import atexit
import asyncio
import csv
import fcntl
import json
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Path setup ────────────────────────────────────────────────────────────────
_BENCH_DIR    = Path(__file__).parent
_WB2026_DIR   = _BENCH_DIR.parent
_POPSCALE_ROOT = _WB2026_DIR.parents[1]
_NIOBE_ROOT    = _POPSCALE_ROOT.parents[1] / "Niobe"
_PG_ROOT       = _POPSCALE_ROOT.parents[1] / "Persona Generator"

for p in [str(_POPSCALE_ROOT), str(_NIOBE_ROOT), str(_PG_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from niobe.study_request import NiobeStudyRequest   # noqa: E402
from niobe.runner import run_niobe_study             # noqa: E402
from popscale.config.validator import make_absolute_path, parse_absolute_path, validate_config  # noqa: E402
from popscale.observability.emitter import RunEventEmitter  # noqa: E402
from src.utils.credit_monitor import CreditExhaustedError, get_credit_monitor  # noqa: E402
from .cluster_definitions import CLUSTERS, SWING_CLUSTER_IDS  # noqa: E402
from .manifesto_contexts import BJP_MANIFESTO_CONTEXT, MANIFESTO_CONTEXTS, TMC_MANIFESTO_CONTEXT  # noqa: E402
from .seat_model import compute_seat_predictions, print_seat_report  # noqa: E402

N_ENSEMBLE_RUNS = 3   # Independent runs averaged for swing clusters

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("wb_2026_constituency")
PID_DIR = Path("/tmp/simulatte_runs")

# ── Shared scenario options and context ───────────────────────────────────────
SCENARIO_OPTIONS = [
    "TMC (Trinamool Congress — Mamata Banerjee)",
    "BJP (Bharatiya Janata Party — Modi-backed state campaign)",
    "Left-Congress alliance (CPI-M / INC joint front)",
    "Other party / NOTA (AIMIM, AJUP, ISF, regional, or None of the Above)",
]

_OPTION_TO_PARTY: dict[str, str] = {
    "TMC (Trinamool Congress — Mamata Banerjee)":                               "TMC",
    "BJP (Bharatiya Janata Party — Modi-backed state campaign)":                "BJP",
    "Left-Congress alliance (CPI-M / INC joint front)":                        "Left-Congress",
    "Other party / NOTA (AIMIM, AJUP, ISF, regional, or None of the Above)":   "Others",
}

BASE_SCENARIO_CONTEXT = """\
West Bengal is voting in its 2026 assembly election (294 seats). TMC under \
Mamata Banerjee has governed since 2011 (215 seats in 2021, 47.9% vote share). \
BJP won 77 seats on 38.1%. The Left-Congress combine was nearly wiped out. \

Heading into 2026: TMC faces anti-incumbency from corruption (cut money syndicates, \
Sandeshkhali) but commands fierce loyalty via welfare schemes: Lakshmir Bhandar \
(monthly cash for women), Swasthya Sathi (health insurance), Duare Sarkar. \
BJP runs on Hindu consolidation, CAA, and central government delivery. \
Left-Congress alliance appeals to voters fatigued by both TMC corruption and BJP communalism. \
The SIR electoral roll process deleted 91 lakh voter names across Bengal — \
disproportionately Muslim (65% of deletions despite 27% population share) and Matua SC \
families in Nadia/N24Pgs. AIMIM-AJUP alliance (182 seats) led by ex-TMC leader Humayun Kabir \
threatens Muslim vote fragmentation. \
"""


def acquire_pid_lock(cluster_id: str) -> Path:
    """Acquire per-cluster PID lock; reject duplicate active runs."""
    PID_DIR.mkdir(parents=True, exist_ok=True)
    pid_path = PID_DIR / f"{cluster_id}.pid"

    if pid_path.exists():
        try:
            existing_pid = int(pid_path.read_text().strip())
            os.kill(existing_pid, 0)
            print(f"ERROR: Cluster '{cluster_id}' already running as PID {existing_pid}")
            print(f"Kill it first: kill -9 {existing_pid}")
            print(
                "Or clean up: python3 popscale/scripts/kill_prior_runs.py --cluster "
                f"{cluster_id}"
            )
            raise SystemExit(1)
        except ProcessLookupError:
            pass
        except ValueError:
            pass

    pid_path.write_text(str(os.getpid()), encoding="utf-8")
    lock_file = open(pid_path, "r", encoding="utf-8")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock_file.close()
        raise SystemExit(1)

    def cleanup() -> None:
        try:
            if pid_path.exists() and pid_path.read_text().strip() == str(os.getpid()):
                pid_path.unlink()
        except Exception:
            pass
        try:
            lock_file.close()
        except Exception:
            pass

    atexit.register(cleanup)
    signal.signal(signal.SIGTERM, lambda *_: (cleanup(), sys.exit(1)))
    signal.signal(signal.SIGINT, lambda *_: (cleanup(), sys.exit(130)))
    return pid_path


def _extract_guardrails(result) -> tuple[list[dict], float]:
    waivers = list(getattr(result.cohort, "gate_waivers", []) or [])
    penalty = float(getattr(result.cohort, "confidence_penalty", 0.0) or 0.0)
    return waivers, penalty


def build_cluster_request(
    cluster: dict,
    manifesto: str | None = None,
) -> NiobeStudyRequest:
    """Build a NiobeStudyRequest for a single cluster."""
    full_context = BASE_SCENARIO_CONTEXT + "\n\n" + cluster["context_note"]
    if manifesto is not None:
        full_context = full_context + "\n\n" + MANIFESTO_CONTEXTS[manifesto]
    budget_cap = max(3.0, round(cluster["n_personas"] * 0.50, 2))

    return NiobeStudyRequest(
        study_name=f"WB 2026 Constituency — {cluster['name']}",
        state="west bengal",
        n_personas=cluster["n_personas"],
        domain=cluster["domain"],
        research_question=(
            f"In the {cluster['name']} cluster ({cluster['n_seats']} seats), "
            "how will voters distribute their vote between TMC, BJP, Left-Congress, "
            "and Other parties in the 2026 assembly election?"
        ),
        scenario_question=(
            "Which party will you vote for in the upcoming West Bengal assembly election?"
        ),
        scenario_context=full_context,
        scenario_options=SCENARIO_OPTIONS,
        stratify_by_religion=True,
        stratify_by_income=False,  # Less relevant at cluster level
        budget_cap_usd=budget_cap,
    )


def extract_vote_shares(result) -> dict[str, float]:
    """Extract vote shares from a cluster study result."""
    responses = result.simulation.responses
    n_total = max(1, len(responses))
    counts: dict[str, int] = {"TMC": 0, "BJP": 0, "Left-Congress": 0, "Others": 0}

    for r in responses:
        decision = r.decision.strip().lower()
        matched = None

        # Exact match
        for opt, party in _OPTION_TO_PARTY.items():
            if decision == opt.lower():
                matched = party
                break

        # Starts-with
        if matched is None:
            if decision.startswith("tmc") or decision.startswith("trinamool"):
                matched = "TMC"
            elif decision.startswith("bjp") or decision.startswith("bharatiya"):
                matched = "BJP"
            elif decision.startswith("left") or decision.startswith("cpi") or decision.startswith("congress"):
                matched = "Left-Congress"
            elif decision.startswith("other") or decision.startswith("nota") or decision.startswith("aimim") or decision.startswith("ajup"):
                matched = "Others"

        # Mention-count fuzzy
        if matched is None:
            mc = {
                "TMC":          decision.count("tmc") + decision.count("trinamool") + decision.count("mamata"),
                "BJP":          decision.count("bjp") + decision.count("bharatiya"),
                "Left-Congress": decision.count("left") + decision.count("cpi") + decision.count("congress"),
                "Others":       decision.count("other") + decision.count("nota") + decision.count("aimim") + decision.count("ajup"),
            }
            best = max(mc, key=mc.get)
            if mc[best] > 0:
                matched = best

        counts[matched or "Others"] += 1

    return {p: round(c / n_total, 4) for p, c in counts.items()}


async def run_cluster(
    cluster: dict,
    manifesto: str | None = None,
    emitter: RunEventEmitter | None = None,
) -> dict:
    """Run simulation for a single cluster. Returns result dict."""
    logger.info("Running cluster: %s (%d personas, %d seats)",
                cluster["name"], cluster["n_personas"], cluster["n_seats"])
    request = build_cluster_request(cluster, manifesto=manifesto)
    if emitter is not None:
        emitter.emit("cluster_started", cluster_id=cluster["id"], n_personas=cluster["n_personas"])
    result = await run_niobe_study(request)
    shares = extract_vote_shares(result)
    waivers, penalty = _extract_guardrails(result)
    logger.info("  %s → TMC %.1f%% BJP %.1f%% Left %.1f%% Other %.1f%%",
                cluster["id"],
                shares["TMC"] * 100, shares["BJP"] * 100,
                shares["Left-Congress"] * 100, shares["Others"] * 100)
    row = {
        "id": cluster["id"],
        "name": cluster["name"],
        "n_seats": cluster["n_seats"],
        "n_personas": cluster["n_personas"],
        "tmc_2021":    cluster["tmc_2021"],
        "bjp_2021":    cluster["bjp_2021"],
        "left_2021":   cluster["left_2021"],
        "others_2021": cluster["others_2021"],
        "sim_tmc":    shares["TMC"],
        "sim_bjp":    shares["BJP"],
        "sim_left":   shares["Left-Congress"],
        "sim_others": shares["Others"],
        "swing_notes": cluster["swing_notes"],
        "key_seats":   cluster["key_seats"],
        "marginal_seats_2021": cluster.get("marginal_seats_2021"),
        "ensemble_runs": 1,
        "gate_waivers": waivers,
        "confidence_penalty": penalty,
    }
    if emitter is not None:
        emitter.emit(
            "api_call",
            cluster_id=cluster["id"],
            requests=max(1, cluster["n_personas"]),
            cost_usd=round(cluster["n_personas"] * 0.09, 4),
            model="haiku",
            cache_hit=False,
        )
        emitter.emit(
            "cluster_completed",
            cluster_id=cluster["id"],
            ensemble_avg={
                "TMC": row["sim_tmc"],
                "BJP": row["sim_bjp"],
                "Left-Congress": row["sim_left"],
                "Others": row["sim_others"],
            },
        )
    return row


def _is_cluster_complete(cluster_row: dict) -> bool:
    runs_complete = int(cluster_row.get("ensemble_runs_complete", cluster_row.get("ensemble_runs", 1)))
    runs_total = int(cluster_row.get("ensemble_runs_total", cluster_row.get("ensemble_runs", 1)))
    return runs_complete >= runs_total and not bool(cluster_row.get("is_partial", False))


def _normalize_partial_ensemble_runs(cluster_row: dict) -> list[dict]:
    runs = list(cluster_row.get("ensemble_runs_data") or [])
    if runs:
        return runs
    detail = list(cluster_row.get("ensemble_detail") or [])
    return [{"run_index": idx + 1, "shares": shares} for idx, shares in enumerate(detail)]


def _build_ensemble_cluster_result(
    *,
    cluster: dict,
    ensemble_runs_data: list[dict],
    all_waivers: list[dict],
    max_penalty: float,
    n_runs: int,
) -> dict:
    parties = ["TMC", "BJP", "Left-Congress", "Others"]
    run_shares = [dict(r["shares"]) for r in ensemble_runs_data]
    runs_complete = len(run_shares)
    avg_raw = (
        {p: sum(s[p] for s in run_shares) / runs_complete for p in parties}
        if runs_complete > 0
        else {p: 0.0 for p in parties}
    )
    total = sum(avg_raw.values()) or 1.0
    avg = {p: round(v / total, 4) for p, v in avg_raw.items()}
    is_partial = runs_complete < n_runs
    return {
        "id": cluster["id"],
        "name": cluster["name"],
        "n_seats": cluster["n_seats"],
        "n_personas": cluster["n_personas"] * runs_complete,
        "tmc_2021": cluster["tmc_2021"],
        "bjp_2021": cluster["bjp_2021"],
        "left_2021": cluster["left_2021"],
        "others_2021": cluster["others_2021"],
        "sim_tmc": avg["TMC"],
        "sim_bjp": avg["BJP"],
        "sim_left": avg["Left-Congress"],
        "sim_others": avg["Others"],
        "swing_notes": cluster["swing_notes"],
        "key_seats": cluster["key_seats"],
        "marginal_seats_2021": cluster.get("marginal_seats_2021"),
        "ensemble_runs": n_runs,
        "ensemble_runs_complete": runs_complete,
        "ensemble_runs_total": n_runs,
        "ensemble_detail": run_shares,
        "ensemble_runs_data": ensemble_runs_data,
        "ensemble_avg": None if is_partial else avg,
        "is_partial": is_partial,
        "gate_waivers": all_waivers,
        "confidence_penalty": max_penalty,
    }


def _ordered_cluster_results(target_clusters: list[dict], rows_by_id: dict[str, dict]) -> list[dict]:
    return [rows_by_id[c["id"]] for c in target_clusters if c["id"] in rows_by_id]


async def run_cluster_ensemble(
    cluster: dict,
    n_runs: int = N_ENSEMBLE_RUNS,
    manifesto: str | None = None,
    emitter: RunEventEmitter | None = None,
    *,
    existing_runs_data: list[dict] | None = None,
    existing_waivers: list[dict] | None = None,
    existing_penalty: float = 0.0,
    on_run_complete: Any | None = None,
    ensemble_concurrency: int = N_ENSEMBLE_RUNS,
) -> dict:
    """Run a swing cluster n_runs times and average vote shares for stability.

    Reduces random sampling noise by √n_runs without changing pool calibration.
    Used for the 4 kingmaker clusters where every percentage point matters.

    Ensemble runs that have not been completed yet are launched concurrently
    (up to ensemble_concurrency at a time) via asyncio.gather so the 3 independent
    runs overlap rather than running serially.
    """
    logger.info("Ensemble ×%d starting: %s (%d personas/run, %d seats)",
                n_runs, cluster["name"], cluster["n_personas"], cluster["n_seats"])
    prior_runs_data = list(existing_runs_data or [])
    prior_waivers = list(existing_waivers or [])
    prior_penalty = existing_penalty
    start_idx = len(prior_runs_data)

    # Indices of ensemble runs still to execute
    pending_indices = list(range(start_idx, n_runs))
    if not pending_indices:
        # All runs already done (resume case) — just build and return result
        row = _build_ensemble_cluster_result(
            cluster=cluster,
            ensemble_runs_data=prior_runs_data,
            all_waivers=prior_waivers,
            max_penalty=prior_penalty,
            n_runs=n_runs,
        )
        return row

    ens_sem = asyncio.Semaphore(max(1, ensemble_concurrency))

    async def _run_one(i: int) -> tuple[int, dict, list, float]:
        """Execute a single ensemble run and return (i, shares, waivers, penalty)."""
        async with ens_sem:
            logger.info("  [%s] ensemble run %d/%d", cluster["id"], i + 1, n_runs)
            if emitter is not None:
                await emitter.aemit(
                    "ensemble_started",
                    cluster_id=cluster["id"],
                    ensemble_idx=i + 1,
                    ensemble_total=n_runs,
                )
            request = build_cluster_request(cluster, manifesto=manifesto)
            result = await run_niobe_study(request)
            shares = extract_vote_shares(result)
            waivers, penalty = _extract_guardrails(result)
            logger.info("    run %d → TMC %.1f%% BJP %.1f%% Left %.1f%% Other %.1f%%",
                        i + 1, shares["TMC"] * 100, shares["BJP"] * 100,
                        shares["Left-Congress"] * 100, shares["Others"] * 100)
            if emitter is not None:
                await emitter.aemit(
                    "api_call",
                    cluster_id=cluster["id"],
                    requests=max(1, cluster["n_personas"]),
                    cost_usd=round(cluster["n_personas"] * 0.10, 4),
                    model="haiku",
                    cache_hit=False,
                )
                await emitter.aemit(
                    "ensemble_completed",
                    cluster_id=cluster["id"],
                    ensemble_idx=i + 1,
                    result=shares,
                )
            return i, shares, waivers, penalty

    # Run all pending ensemble tasks concurrently; collect results in index order
    outcomes = await asyncio.gather(*[_run_one(i) for i in pending_indices], return_exceptions=True)

    # Merge new results with any prior data; preserve index ordering
    new_runs_data = list(prior_runs_data)
    all_waivers = list(prior_waivers)
    max_penalty = prior_penalty
    failed_indices: list[int] = []
    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            logger.warning("  [%s] an ensemble run failed: %s", cluster["id"], outcome)
            failed_indices.append(-1)
            continue
        i, shares, waivers, penalty = outcome
        new_runs_data.append({"run_index": i + 1, "shares": shares})
        all_waivers.extend(waivers)
        max_penalty = max(max_penalty, penalty)

    # Sort by run_index so ensemble_detail is deterministic regardless of completion order
    new_runs_data.sort(key=lambda r: r["run_index"])

    row = _build_ensemble_cluster_result(
        cluster=cluster,
        ensemble_runs_data=new_runs_data,
        all_waivers=all_waivers,
        max_penalty=max_penalty,
        n_runs=n_runs,
    )

    # Fire on_run_complete once with the full aggregated result (mirrors serial behaviour)
    if on_run_complete is not None:
        await on_run_complete(row)

    logger.info("  %s ensemble avg → TMC %.1f%% BJP %.1f%% Left %.1f%% Other %.1f%%",
                cluster["id"],
                row["sim_tmc"] * 100, row["sim_bjp"] * 100,
                row["sim_left"] * 100, row["sim_others"] * 100)
    if emitter is not None:
        await emitter.aemit(
            "cluster_completed",
            cluster_id=cluster["id"],
            ensemble_avg={
                "TMC": row["sim_tmc"],
                "BJP": row["sim_bjp"],
                "Left-Congress": row["sim_left"],
                "Others": row["sim_others"],
            },
        )
    return row


# ── Per-cluster sub-file checkpoint helpers ───────────────────────────────────
# BRIEF-014: each concurrent cluster writes to its own sub-file in a directory,
# eliminating write contention. At the end of a run the directory is aggregated
# into the legacy single-file partial JSON for backward compat.

def _partial_dir(run_id: str, partial_root: Path) -> Path:
    """Return (and create) the per-run partial directory."""
    d = partial_root / f"{run_id}.partial"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_cluster_subfile(
    partial_dir: Path,
    cluster_id: str,
    row: dict,
) -> None:
    """Atomically write a single cluster's result to its own sub-file."""
    target = partial_dir / f"cluster_{cluster_id}.json"
    tmp = target.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(row, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, target)


def _write_manifest(partial_dir: Path, run_id: str, total_clusters: int) -> None:
    """Write/update _manifest.json inside the partial directory."""
    manifest_path = partial_dir / "_manifest.json"
    payload = {
        "run_id": run_id,
        "total_clusters": total_clusters,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
    tmp = manifest_path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, manifest_path)


def _load_partial_dir(partial_dir: Path) -> tuple[str | None, list[dict]]:
    """Load all cluster sub-files from a partial directory.

    Returns (run_id, cluster_results_list).
    """
    manifest_path = partial_dir / "_manifest.json"
    run_id: str | None = None
    if manifest_path.exists():
        try:
            run_id = json.loads(manifest_path.read_text(encoding="utf-8")).get("run_id")
        except Exception:
            pass

    cluster_results: list[dict] = []
    for p in sorted(partial_dir.glob("cluster_*.json")):
        try:
            cluster_results.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            logger.warning("Could not read cluster sub-file %s — skipping", p)
    return run_id, cluster_results


def _load_resume_source(resume_from: Path) -> tuple[str, list[dict]]:
    """Load a resume source that is either:

    * A legacy single-file `<run_id>.partial.json`, OR
    * A new directory-based partial `<run_id>.partial/`

    Returns (run_id, cluster_results).
    """
    if resume_from.is_dir():
        # New directory-based format
        run_id, cluster_results = _load_partial_dir(resume_from)
        if run_id is None:
            # Fallback: infer run_id from directory name  e.g. "20240101_120000.partial"
            run_id = resume_from.name.replace(".partial", "")
        return run_id, cluster_results
    else:
        # Legacy single-file format
        with resume_from.open(encoding="utf-8") as _f:
            data = json.load(_f)
        return str(data["run_id"]), list(data.get("cluster_results", []))


async def run_all_clusters(
    cluster_ids: list[str] | None = None,
    manifesto: str | None = None,
    resume_from: Path | None = None,
    emitter: RunEventEmitter | None = None,
    run_id_override: str | None = None,
    *,
    cluster_concurrency: int = 5,
    ensemble_concurrency: int = N_ENSEMBLE_RUNS,
) -> dict:
    """Run all (or selected) clusters and produce consolidated results.

    Args:
        cluster_ids:           Restrict to these cluster IDs. None = all clusters.
        manifesto:             Manifesto context injection mode (tmc|bjp|both|None).
        resume_from:           Path to a previous partial (file OR directory). Completed
                               clusters are skipped and their results seeded into this run.
        cluster_concurrency:   Max clusters running simultaneously (default 5).
        ensemble_concurrency:  Max ensemble runs within a cluster simultaneously (default 3).
    """
    target_clusters = CLUSTERS
    if cluster_ids:
        target_clusters = [c for c in CLUSTERS if c["id"] in cluster_ids]
        if not target_clusters:
            raise ValueError(f"Unknown cluster IDs: {cluster_ids}")

    if resume_from is not None:
        run_id, cluster_results = _load_resume_source(resume_from)
    else:
        run_id = run_id_override or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        cluster_results = []

    partial_root = Path(os.getenv("SIMULATTE_PARTIAL_DIR", "/tmp/wb_reruns"))
    partial_root.mkdir(parents=True, exist_ok=True)
    # Legacy single-file path (kept for final aggregation + backward compat)
    partial_path = partial_root / f"{run_id}.partial.json"
    # Per-cluster directory (BRIEF-014)
    pdir = _partial_dir(run_id, partial_root)
    _write_manifest(pdir, run_id, len(target_clusters))

    rows_by_id: dict[str, dict] = {row["id"]: row for row in cluster_results}
    # Seed per-cluster sub-files for any already-completed clusters (resume case)
    for row in cluster_results:
        _write_cluster_subfile(pdir, row["id"], row)

    already_done = {row["id"] for row in cluster_results if _is_cluster_complete(row)}
    remaining = [c for c in target_clusters if c["id"] not in already_done]

    logger.info(
        "%s WB 2026 constituency run | id=%s | clusters=%d/%d | total_personas=%d | "
        "cluster_concurrency=%d ensemble_concurrency=%d",
        "Resuming" if resume_from else "Starting",
        run_id, len(remaining), len(target_clusters),
        sum(c["n_personas"] for c in remaining),
        cluster_concurrency, ensemble_concurrency,
    )

    monitor = get_credit_monitor()
    monitor.update_progress(run_id=run_id, checkpoint_path=str(partial_path))
    balance = await monitor.preflight_check(run_id=run_id)
    logger.info("Pre-flight credit OK: balance $%.2f (buffer $%.2f)", balance, monitor.buffer_usd)
    await monitor.start_background_monitor()

    # Lock used to serialise writes to rows_by_id (shared across concurrent tasks)
    rows_lock = asyncio.Lock()
    cluster_sem = asyncio.Semaphore(max(1, cluster_concurrency))
    failed_clusters: list[str] = []

    async def _run_one_cluster(cluster: dict) -> dict | Exception:
        """Bounded cluster task; returns result dict or an exception."""
        cluster_id = cluster["id"]
        async with cluster_sem:
            if monitor.is_halt_requested():
                exc = CreditExhaustedError(monitor.halt_snapshot().get("reason", "credit halt"))
                return exc

            try:
                if cluster_id in SWING_CLUSTER_IDS:
                    async with rows_lock:
                        existing = rows_by_id.get(cluster_id)
                    existing_runs_data = _normalize_partial_ensemble_runs(existing) if existing else []
                    existing_waivers = list((existing or {}).get("gate_waivers") or [])
                    existing_penalty = float((existing or {}).get("confidence_penalty", 0.0) or 0.0)

                    async def _on_ensemble_done(current_row: dict) -> None:
                        async with rows_lock:
                            rows_by_id[cluster_id] = current_row
                        _write_cluster_subfile(pdir, cluster_id, current_row)
                        monitor.update_progress(
                            run_id=run_id,
                            cluster_id=cluster_id,
                            ensemble_idx=int(current_row.get("ensemble_runs_complete", 0)),
                            ensemble_total=N_ENSEMBLE_RUNS,
                            checkpoint_path=str(partial_path),
                        )

                    row = await run_cluster_ensemble(
                        cluster,
                        n_runs=N_ENSEMBLE_RUNS,
                        manifesto=manifesto,
                        emitter=emitter,
                        existing_runs_data=existing_runs_data,
                        existing_waivers=existing_waivers,
                        existing_penalty=existing_penalty,
                        on_run_complete=_on_ensemble_done,
                        ensemble_concurrency=ensemble_concurrency,
                    )
                else:
                    row = await run_cluster(cluster, manifesto=manifesto, emitter=emitter)
                    row["is_partial"] = False
                    row["ensemble_runs_complete"] = 1
                    row["ensemble_runs_total"] = 1
                    monitor.update_progress(
                        run_id=run_id,
                        cluster_id=cluster_id,
                        ensemble_idx=1,
                        ensemble_total=1,
                        checkpoint_path=str(partial_path),
                    )

                async with rows_lock:
                    rows_by_id[cluster_id] = row
                _write_cluster_subfile(pdir, cluster_id, row)
                return row

            except Exception as exc:  # noqa: BLE001
                logger.error("Cluster %s failed: %s", cluster_id, exc, exc_info=True)
                return exc

    try:
        # Fan out: all remaining clusters run concurrently, bounded by cluster_sem
        outcomes = await asyncio.gather(
            *[_run_one_cluster(c) for c in target_clusters if c["id"] not in already_done],
            return_exceptions=True,
        )

        for cluster, outcome in zip(
            [c for c in target_clusters if c["id"] not in already_done],
            outcomes,
        ):
            if isinstance(outcome, BaseException):
                failed_clusters.append(cluster["id"])
                logger.error("Cluster %s raised: %s", cluster["id"], outcome)

        final_rows = _ordered_cluster_results(target_clusters, rows_by_id)

        # Surface failures in report but don't abort if some clusters succeeded
        if failed_clusters:
            logger.warning(
                "Run %s completed with %d failed cluster(s): %s",
                run_id, len(failed_clusters), ", ".join(failed_clusters),
            )

        if not all(_is_cluster_complete(row) for row in final_rows):
            _write_partial_results(
                partial_path,
                run_id=run_id,
                cluster_results=final_rows,
                status="halted",
                is_partial=True,
                halt=monitor.halt_snapshot(),
            )
            raise CreditExhaustedError(monitor.halt_snapshot().get("reason", "run halted before completion"))

        confidence_penalty = _aggregate_confidence_penalty(final_rows)
        seat_result = compute_seat_predictions(
            final_rows,
            use_cube_law=True,
            confidence_penalty=confidence_penalty,
            is_partial=False,
        )
        _write_partial_results(
            partial_path,
            run_id=run_id,
            cluster_results=final_rows,
            status="completed",
            is_partial=False,
        )
    except CreditExhaustedError:
        async with rows_lock:
            halted_rows = _ordered_cluster_results(target_clusters, rows_by_id)
        _write_partial_results(
            partial_path,
            run_id=run_id,
            cluster_results=halted_rows,
            status="halted_credit_low",
            is_partial=True,
            halt=monitor.halt_snapshot(),
        )
        raise
    finally:
        await monitor.stop_background_monitor()

    result: dict[str, Any] = {
        "run_id": run_id,
        "run_date": datetime.now(timezone.utc).isoformat(),
        "n_clusters": len(final_rows),
        "total_personas": sum(c["n_personas"] for c in final_rows),
        "total_seats": 294,
        "cluster_results": final_rows,
        "seat_prediction": seat_result["seat_predictions"],
        "cluster_breakdown": seat_result["cluster_breakdown"],
        "swing_analysis": seat_result["swing_analysis"],
        "total_marginal_seats": seat_result["total_marginal_seats"],
        "confidence_range_seats": seat_result["confidence_range_seats"],
        "schema_version": seat_result["schema_version"],
        "is_partial": seat_result["is_partial"],
        "gate_waivers": seat_result["gate_waivers"],
        "confidence_penalty": confidence_penalty,
        "tmc_majority": seat_result["tmc_majority"],
    }
    if failed_clusters:
        result["failed_clusters"] = failed_clusters
    return result


def _aggregate_confidence_penalty(cluster_results: list[dict]) -> float:
    total = 0.0
    for cluster in cluster_results:
        waivers = cluster.get("gate_waivers") or []
        if waivers:
            for waiver in waivers:
                try:
                    total += float(waiver.get("confidence_penalty", 0.1))
                except Exception:
                    total += 0.1
        else:
            total += float(cluster.get("confidence_penalty", 0.0) or 0.0)
    return min(0.5, total)


def _write_partial_results(
    partial_path: Path,
    *,
    run_id: str,
    cluster_results: list[dict],
    status: str,
    is_partial: bool,
    halt: dict[str, Any] | None = None,
) -> None:
    confidence_penalty = _aggregate_confidence_penalty(cluster_results)
    seat_result = compute_seat_predictions(
        cluster_results,
        use_cube_law=True,
        confidence_penalty=confidence_penalty,
        is_partial=is_partial,
    ) if cluster_results else {
        "schema_version": "2.0" if is_partial else "1.0",
        "seat_predictions": {"TMC": 0, "BJP": 0, "Left-Congress": 0, "Others": 0},
        "cluster_breakdown": [],
        "swing_analysis": [],
        "total_marginal_seats": 0,
        "confidence_range_seats": 5,
        "tmc_majority": False,
        "is_partial": is_partial,
        "gate_waivers": [],
    }

    payload = {
        "run_id": run_id,
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "n_clusters": len(cluster_results),
        "total_personas": sum(c["n_personas"] for c in cluster_results),
        "cluster_results": cluster_results,
        "schema_version": seat_result["schema_version"],
        "is_partial": seat_result["is_partial"],
        "gate_waivers": seat_result["gate_waivers"],
        "confidence_penalty": confidence_penalty,
        "seat_prediction": seat_result["seat_predictions"],
        "cluster_breakdown": seat_result["cluster_breakdown"],
        "swing_analysis": seat_result["swing_analysis"],
        "total_marginal_seats": seat_result["total_marginal_seats"],
        "confidence_range_seats": seat_result["confidence_range_seats"],
        "tmc_majority": seat_result["tmc_majority"],
    }
    if halt is not None:
        payload["halt"] = halt

    tmp_path = partial_path.with_suffix(partial_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_path, partial_path)


def _estimate_manifesto_run_cost(swing_clusters: list[dict]) -> float:
    """Very rough estimate: n_personas × $0.10 per persona × ensemble_runs."""
    total = 0.0
    for c in swing_clusters:
        runs = N_ENSEMBLE_RUNS
        total += c["n_personas"] * 0.10 * runs
    return total


def _estimate_standard_run_cost(clusters: list[dict]) -> float:
    """Approximate non-manifesto run cost used for pre-flight budgeting."""
    total = 0.0
    for c in clusters:
        runs = N_ENSEMBLE_RUNS if c["id"] in SWING_CLUSTER_IDS else 1
        total += c["n_personas"] * 0.09 * runs
    return total


def _load_baseline_results(path: Path | None) -> dict | None:
    if path is None:
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _cluster_vote_shares(cluster_row: dict) -> dict[str, float]:
    return {
        "TMC": float(cluster_row["sim_tmc"]),
        "BJP": float(cluster_row["sim_bjp"]),
        "Left-Congress": float(cluster_row["sim_left"]),
        "Others": float(cluster_row["sim_others"]),
    }


def _build_sensitivity_payload(
    *,
    run_results: dict,
    manifesto: str,
    baseline_file: Path | None,
) -> dict:
    baseline = _load_baseline_results(baseline_file)
    baseline_clusters: dict[str, dict] = {}
    baseline_seats: dict[str, int] | None = None
    if baseline is not None:
        for row in baseline.get("cluster_results", []):
            baseline_clusters[str(row["id"])] = row
        baseline_seats = {
            "TMC": int(baseline["seat_prediction"]["TMC"]),
            "BJP": int(baseline["seat_prediction"]["BJP"]),
            "Left-Congress": int(baseline["seat_prediction"]["Left-Congress"]),
            "Others": int(baseline["seat_prediction"]["Others"]),
        }

    clusters_payload: dict[str, dict] = {}
    for row in run_results["cluster_results"]:
        cluster_id = str(row["id"])
        vote_shares = _cluster_vote_shares(row)
        baseline_vote_shares = None
        delta = None
        if cluster_id in baseline_clusters:
            baseline_vote_shares = _cluster_vote_shares(baseline_clusters[cluster_id])
            delta = {
                party: round(vote_shares[party] - baseline_vote_shares[party], 4)
                for party in vote_shares
            }
        clusters_payload[cluster_id] = {
            "vote_shares": vote_shares,
            "baseline_vote_shares": baseline_vote_shares,
            "delta": delta,
            "n_personas": int(row["n_personas"]),
            "ensemble_runs": int(row.get("ensemble_runs", 1)),
            "confidence_penalty": float(row.get("confidence_penalty", 0.0) or 0.0),
            "gate_waivers": len(row.get("gate_waivers") or []),
        }

    with_manifesto = {
        "TMC": int(run_results["seat_prediction"]["TMC"]),
        "BJP": int(run_results["seat_prediction"]["BJP"]),
        "Left-Congress": int(run_results["seat_prediction"]["Left-Congress"]),
        "Others": int(run_results["seat_prediction"]["Others"]),
    }
    seat_delta = None
    if baseline_seats is not None:
        seat_delta = {
            party: with_manifesto[party] - baseline_seats[party]
            for party in with_manifesto
        }

    total_cost_usd = round(
        sum(float(row["n_personas"]) * 0.11 for row in run_results["cluster_results"]),
        2,
    )

    return {
        "run_id": run_results["run_id"],
        "manifesto": manifesto,
        "baseline_file": str(baseline_file) if baseline_file else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "clusters": clusters_payload,
        "seat_projection": {
            "with_manifesto": with_manifesto,
            "baseline": baseline_seats,
            "seat_delta": seat_delta,
        },
        "total_cost_usd": total_cost_usd,
    }


def _write_sensitivity_outputs(payload: dict) -> tuple[Path, Path]:
    out_dir = _WB2026_DIR / "results" / "sensitivity"
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = payload["run_id"]
    json_path = out_dir / f"sensitivity_{run_id}.json"
    csv_path = out_dir / f"sensitivity_{run_id}.csv"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "cluster_id",
                "party",
                "manifesto_vote_share",
                "baseline_vote_share",
                "delta_pp",
            ],
        )
        writer.writeheader()
        for cluster_id, cluster_data in payload["clusters"].items():
            manifesto_vote = cluster_data["vote_shares"]
            baseline_vote = cluster_data["baseline_vote_shares"]
            for party in ("TMC", "BJP", "Left-Congress", "Others"):
                base_value = baseline_vote[party] if baseline_vote else None
                delta_pp = None
                if base_value is not None:
                    delta_pp = round((manifesto_vote[party] - base_value) * 100, 2)
                writer.writerow(
                    {
                        "cluster_id": cluster_id,
                        "party": party,
                        "manifesto_vote_share": manifesto_vote[party],
                        "baseline_vote_share": base_value,
                        "delta_pp": delta_pp,
                    }
                )

    return json_path, csv_path


def _print_sensitivity_table(payload: dict) -> None:
    print(f"\nWB 2026 MANIFESTO SENSITIVITY MATRIX ({payload['manifesto']} manifestos injected)")
    print("=" * 64)
    print(f"{'Cluster':<22} {'TMC':>6} {'BJP':>6} {'L-C':>6} {'Other':>7}  | vs baseline")
    for cluster_id, cluster_data in payload["clusters"].items():
        vote = cluster_data["vote_shares"]
        delta = cluster_data["delta"]
        if delta is None:
            delta_text = "(no baseline)"
        else:
            delta_text = (
                f"TMC {delta['TMC'] * 100:+.1f}pp "
                f"BJP {delta['BJP'] * 100:+.1f}pp"
            )
        print(
            f"{cluster_id:<22} "
            f"{vote['TMC'] * 100:>5.1f}% "
            f"{vote['BJP'] * 100:>5.1f}% "
            f"{vote['Left-Congress'] * 100:>5.1f}% "
            f"{vote['Others'] * 100:>6.1f}%"
            f"  | {delta_text}"
        )
    print("=" * 64)
    seat = payload["seat_projection"]
    with_manifesto = seat["with_manifesto"]
    print(
        "SEAT PROJECTION (manifesto): "
        f"TMC {with_manifesto['TMC']} | BJP {with_manifesto['BJP']} | "
        f"L-C {with_manifesto['Left-Congress']} | Other {with_manifesto['Others']}"
    )
    if seat["baseline"] is None:
        print("SEAT PROJECTION (baseline):  (no baseline)")
        print("SEAT DELTA:                  (no baseline)")
    else:
        baseline = seat["baseline"]
        delta = seat["seat_delta"]
        print(
            "SEAT PROJECTION (baseline):  "
            f"TMC {baseline['TMC']} | BJP {baseline['BJP']} | "
            f"L-C {baseline['Left-Congress']} | Other {baseline['Others']}"
        )
        print(
            "SEAT DELTA:                  "
            f"TMC {delta['TMC']:+} | BJP {delta['BJP']:+} | "
            f"L-C {delta['Left-Congress']:+} | Other {delta['Others']:+}"
        )


def print_cluster_vote_shares(cluster_results: list[dict]) -> None:
    """Print cluster-level vote share table."""
    print("\n" + "═" * 90)
    print("  WB 2026 CONSTITUENCY — Cluster Vote Shares vs 2021 Baseline")
    print("═" * 90)
    print(f"  {'Cluster':<38} {'TMCSim':>7} {'TMC21':>7} {'BJPSim':>7} {'BJP21':>7} "
          f"{'LftSim':>7} {'OthSim':>7}")
    print("  " + "─" * 86)
    for r in cluster_results:
        print(f"  {r['name'][:37]:<38} "
              f"{r['sim_tmc']:>6.1%} {r['tmc_2021']:>6.1%}  "
              f"{r['sim_bjp']:>6.1%} {r['bjp_2021']:>6.1%}  "
              f"{r['sim_left']:>6.1%} {r['sim_others']:>6.1%}")
    print("═" * 90)


def save_results(results: dict, output_dir: Path) -> Path:
    """Save results to JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    fname = output_dir / f"wb_2026_constituency_{results['run_id']}.json"
    with open(fname, "w") as f:
        json.dump(results, f, indent=2)
    logger.info("Results saved: %s", fname)
    return fname


def load_and_display(results_file: Path) -> None:
    """Load existing results file and display."""
    with open(results_file) as f:
        results = json.load(f)

    print(f"\nLoaded results: {results_file.name}")
    print(f"Run ID: {results['run_id']} | Clusters: {results['n_clusters']} | "
          f"Personas: {results['total_personas']}")

    print_cluster_vote_shares(results["cluster_results"])

    seat_input = []
    for cr in results["cluster_results"]:
        seat_input.append({**cr})
    seat_result = compute_seat_predictions(
        seat_input,
        confidence_penalty=float(results.get("confidence_penalty", 0.0) or 0.0),
        is_partial=bool(results.get("is_partial", False)),
    )
    print_seat_report(seat_result)


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="WB 2026 Constituency-level benchmark")
    p.add_argument("--dry-run", action="store_true",
                   help="Print config without running simulations")
    p.add_argument("--cluster", type=str, metavar="CLUSTER_ID",
                   help="Run a single cluster (by id). E.g. --cluster murshidabad")
    p.add_argument("--results-file", type=parse_absolute_path, metavar="PATH",
                   help="Load existing JSON results file")
    p.add_argument("--seat-model-only", type=parse_absolute_path, metavar="PATH",
                   help="Re-run seat model on existing results file")
    p.add_argument("--cost-trace", type=parse_absolute_path, default=None,
                   help="Dump per-call cost CSV to this path at end of run")
    p.add_argument(
        "--manifesto",
        type=str,
        choices=["tmc", "bjp", "both"],
        default=None,
        metavar="PARTY",
        help="Inject party manifesto context into scenario. Choices: tmc | bjp | both. "
             "Only runs SWING_CLUSTER_IDS. Required for sensitivity study.",
    )
    p.add_argument(
        "--budget-ceiling",
        type=float,
        default=None,
        metavar="USD",
        help="Hard total budget ceiling across all clusters in this run (USD). "
             "Run aborts if projected cost exceeds ceiling before starting. "
             "Default: no ceiling (per-cluster caps still apply).",
    )
    p.add_argument(
        "--sensitivity-baseline",
        type=parse_absolute_path,
        default=None,
        metavar="PATH",
        help="Path to a prior results JSON file to use as baseline for sensitivity delta "
             "computation. If omitted, no delta is computed (absolute results only).",
    )
    p.add_argument(
        "--resume-from",
        type=parse_absolute_path,
        default=None,
        metavar="PATH",
        help="Path to a .partial.json file from a previous interrupted run. "
             "Clusters already completed in that file are skipped; the original "
             "run_id is preserved so the partial file is updated in-place. "
             "Compatible with --manifesto and --sensitivity-baseline.",
    )
    p.add_argument(
        "--force-over-budget",
        action="store_true",
        help="Allow run to proceed when estimated cost exceeds --budget-ceiling.",
    )
    p.add_argument(
        "--cluster-concurrency",
        type=int,
        default=5,
        metavar="N",
        help="Maximum number of clusters to run concurrently (default 5).",
    )
    p.add_argument(
        "--ensemble-concurrency",
        type=int,
        default=3,
        metavar="N",
        help="Maximum number of ensemble runs within a cluster to run concurrently (default 3).",
    )
    return p.parse_args()


async def main() -> None:
    args = parse_args()
    prior_sigint = signal.getsignal(signal.SIGINT)
    prior_sigterm = signal.getsignal(signal.SIGTERM)

    def _raise_interrupt(signum, _frame) -> None:
        raise KeyboardInterrupt(f"received signal {signum}")

    def _dump_cost_trace() -> None:
        if not args.cost_trace:
            return
        from src.observability.cost_tracer import CostTracer

        CostTracer.dump_csv(Path(args.cost_trace))
        print(f"✓ Cost trace written to {args.cost_trace}")

    signal.signal(signal.SIGINT, _raise_interrupt)
    signal.signal(signal.SIGTERM, _raise_interrupt)

    try:
        selected_clusters_for_estimate = CLUSTERS
        if args.cluster:
            selected_clusters_for_estimate = [c for c in CLUSTERS if c["id"] == args.cluster]
        if args.manifesto and not args.cluster:
            selected_clusters_for_estimate = [c for c in CLUSTERS if c["id"] in SWING_CLUSTER_IDS]
        estimated_total = (
            _estimate_manifesto_run_cost(selected_clusters_for_estimate)
            if args.manifesto
            else _estimate_standard_run_cost(selected_clusters_for_estimate)
        )
        require_api_key = not (args.dry_run or args.results_file or args.seat_model_only)
        preflight = validate_config(
            path_file_args={
                "--results-file": args.results_file,
                "--seat-model-only": args.seat_model_only,
                "--sensitivity-baseline": args.sensitivity_baseline,
                "--resume-from": args.resume_from,
            },
            path_dir_args={
                "--cost-trace-dir": Path(args.cost_trace).parent if args.cost_trace else None,
            },
            budget_ceiling=args.budget_ceiling,
            estimated_total_usd=estimated_total,
            force_over_budget=args.force_over_budget,
            baseline_path=Path(args.sensitivity_baseline) if args.sensitivity_baseline else None,
            require_anthropic_key=require_api_key,
            credit_detector_active=True,
        )
        print(preflight.render())
        if not preflight.ok:
            raise SystemExit(1)

        if args.manifesto and (args.results_file or args.seat_model_only):
            print("ERROR: --manifesto cannot be combined with --results-file or --seat-model-only.")
            raise SystemExit(1)

        if args.manifesto and args.cluster and args.cluster not in SWING_CLUSTER_IDS:
            print(
                f"ERROR: --manifesto mode supports only swing clusters. "
                f"'{args.cluster}' is not in SWING_CLUSTER_IDS."
            )
            raise SystemExit(1)

        if args.results_file:
            load_and_display(Path(args.results_file))
            return

        if args.seat_model_only:
            load_and_display(Path(args.seat_model_only))
            return

        if args.dry_run:
            if args.manifesto:
                selected_swing_clusters = [c for c in CLUSTERS if c["id"] in SWING_CLUSTER_IDS]
                if args.cluster:
                    selected_swing_clusters = [c for c in selected_swing_clusters if c["id"] == args.cluster]
                estimate = _estimate_manifesto_run_cost(selected_swing_clusters)
                print("\n── WB 2026 MANIFESTO SENSITIVITY — DRY RUN ──")
                print(f"  Manifesto mode: {args.manifesto}")
                print(f"  Swing clusters to run: {len(selected_swing_clusters)}")
                for c in selected_swing_clusters:
                    print(f"    - {c['id']} ({c['n_personas']} personas × {N_ENSEMBLE_RUNS} ensemble)")
                print(f"  Context length (tmc):  {len(TMC_MANIFESTO_CONTEXT)} chars")
                print(f"  Context length (bjp):  {len(BJP_MANIFESTO_CONTEXT)} chars")
                print(f"  Context length (both): {len(MANIFESTO_CONTEXTS['both'])} chars")
                if selected_swing_clusters:
                    preview_cluster = selected_swing_clusters[0]
                    injected = MANIFESTO_CONTEXTS[args.manifesto]
                    full_context = BASE_SCENARIO_CONTEXT + "\n\n" + preview_cluster["context_note"] + "\n\n" + injected
                    preview = full_context[-len(injected):][:200].replace("\n", " ")
                    print(f"  Injected context preview ({preview_cluster['id']}): {preview}")
                print(f"  Estimated manifesto run cost: ${estimate:.2f}")
                if args.budget_ceiling is not None:
                    if estimate > args.budget_ceiling and not args.force_over_budget:
                        print(
                            f"ERROR: Estimated cost ${estimate:.0f} exceeds --budget-ceiling "
                            f"${args.budget_ceiling:.0f}. Aborting."
                        )
                        raise SystemExit(1)
                    if estimate > args.budget_ceiling and args.force_over_budget:
                        print(
                            f"Would exceed budget ceiling ${args.budget_ceiling:.0f}, "
                            "but --force-over-budget is set."
                        )
                    else:
                        print(f"Would pass budget ceiling: ${args.budget_ceiling:.0f}")
                return

            print("\n── WB 2026 Constituency Benchmark B-WB-7 — DRY RUN ──")
            print(f"  Clusters: {len(CLUSTERS)}")
            swing = [c for c in CLUSTERS if c["id"] in SWING_CLUSTER_IDS]
            stable = [c for c in CLUSTERS if c["id"] not in SWING_CLUSTER_IDS]
            swing_runs = sum(c["n_personas"] * N_ENSEMBLE_RUNS for c in swing)
            stable_runs = sum(c["n_personas"] for c in stable)
            total_runs = swing_runs + stable_runs
            print(f"  Swing clusters (×{N_ENSEMBLE_RUNS} ensemble): {len(swing)} clusters, "
                  f"{swing_runs} persona-runs")
            print(f"  Stable clusters (×1):          {len(stable)} clusters, "
                  f"{stable_runs} persona-runs")
            print(f"  Total persona-runs: {total_runs}")
            print(f"  Total seats: {sum(c['n_seats'] for c in CLUSTERS)}")
            print(f"  Seat model: cube-law FPTP")
            print(f"  Est. cost: ~${total_runs * 0.07:.0f}–${total_runs * 0.11:.0f}")
            print()
            for c in CLUSTERS:
                ens = f"×{N_ENSEMBLE_RUNS} ensemble" if c["id"] in SWING_CLUSTER_IDS else "×1        "
                print(f"  [{c['id']:25s}] {c['n_seats']:3d} seats | {c['n_personas']:2d} personas {ens} | "
                      f"marginal={c.get('marginal_seats_2021','?'):2} | "
                      f"2021: TMC {c['tmc_2021']:.0%} BJP {c['bjp_2021']:.0%}")
            return

        lock_cluster_id = args.cluster if args.cluster else "all_clusters"
        acquire_pid_lock(lock_cluster_id)

        cluster_ids = [args.cluster] if args.cluster else None
        if args.manifesto and cluster_ids is None:
            cluster_ids = sorted(SWING_CLUSTER_IDS)

        # --resume-from: validate and extract already-completed cluster IDs
        resume_from: Path | None = None
        _resume_run_id: str | None = None
        _already_done: set[str] = set()
        if args.resume_from:
            resume_from = Path(args.resume_from)
            if not resume_from.exists():
                print(f"ERROR: --resume-from file not found: {resume_from}")
                raise SystemExit(1)
            with resume_from.open() as _rf:
                _pdata = json.load(_rf)
            _resume_run_id = str(_pdata.get("run_id")) if _pdata.get("run_id") else None
            if not _pdata.get("is_partial"):
                print(
                    f"ERROR: --resume-from file has is_partial=false — this run already "
                    f"completed. Use --results-file to display it instead."
                )
                raise SystemExit(1)
            _already_done = {r["id"] for r in _pdata.get("cluster_results", []) if _is_cluster_complete(r)}
            print(
                f"Resuming run {_pdata['run_id']} — "
                f"skipping {len(_already_done)} completed cluster(s): "
                f"{', '.join(sorted(_already_done))}"
            )

        active_run_id = _resume_run_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        emitter = RunEventEmitter(active_run_id)
        emitter.emit(
            "run_started",
            cluster_total=len(cluster_ids) if cluster_ids is not None else len(CLUSTERS),
            budget_usd=args.budget_ceiling,
            manifesto=args.manifesto,
        )

        if args.manifesto:
            # Exclude already-completed clusters from cost estimate when resuming
            run_clusters = [
                c for c in CLUSTERS
                if c["id"] in set(cluster_ids or []) and c["id"] not in _already_done
            ]
            estimate = _estimate_manifesto_run_cost(run_clusters)
            print(f"Estimated manifesto run cost: ${estimate:.2f}"
                  + (" (remaining clusters only)" if _already_done else ""))
            if (
                args.budget_ceiling is not None
                and estimate > args.budget_ceiling
                and not args.force_over_budget
            ):
                print(
                    f"ERROR: Estimated cost ${estimate:.0f} exceeds --budget-ceiling "
                    f"${args.budget_ceiling:.0f}. Aborting."
                )
                raise SystemExit(1)

        try:
            try:
                results = await run_all_clusters(
                    cluster_ids,
                    manifesto=args.manifesto,
                    resume_from=resume_from,
                    emitter=emitter,
                    run_id_override=active_run_id,
                )
            except CreditExhaustedError as exc:
                print(f"HALT: {exc}")
                raise SystemExit(2)
        except Exception as exc:
            emitter.emit("error", level="ERROR", msg=str(exc))
            raise

        print_cluster_vote_shares(results["cluster_results"])

        seat_input = results["cluster_results"]
        seat_result = compute_seat_predictions(
            seat_input,
            confidence_penalty=float(results.get("confidence_penalty", 0.0) or 0.0),
            is_partial=bool(results.get("is_partial", False)),
        )
        print_seat_report(seat_result)

        output_dir = _BENCH_DIR / "results"
        saved = save_results(results, output_dir)
        print(f"\nResults saved: {saved}")
        emitter.emit(
            "run_completed",
            total_cost_usd=round(_estimate_standard_run_cost(results["cluster_results"]), 2),
            duration_s=0,
            cluster_completed=len(results["cluster_results"]),
        )

        if args.manifesto:
            baseline_path = Path(args.sensitivity_baseline) if args.sensitivity_baseline else None
            payload = _build_sensitivity_payload(
                run_results=results,
                manifesto=args.manifesto,
                baseline_file=baseline_path,
            )
            json_path, csv_path = _write_sensitivity_outputs(payload)
            _print_sensitivity_table(payload)
            print(f"\nSensitivity JSON saved: {json_path}")
            print(f"Sensitivity CSV saved:  {csv_path}")
    finally:
        try:
            _dump_cost_trace()
        finally:
            signal.signal(signal.SIGINT, prior_sigint)
            signal.signal(signal.SIGTERM, prior_sigterm)


if __name__ == "__main__":
    asyncio.run(main())
