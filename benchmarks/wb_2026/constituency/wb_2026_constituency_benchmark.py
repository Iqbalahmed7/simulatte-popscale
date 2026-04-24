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
import fcntl
import json
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

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
from .cluster_definitions import CLUSTERS, SWING_CLUSTER_IDS  # noqa: E402
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


def build_cluster_request(cluster: dict) -> NiobeStudyRequest:
    """Build a NiobeStudyRequest for a single cluster."""
    full_context = BASE_SCENARIO_CONTEXT + "\n\n" + cluster["context_note"]
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


async def run_cluster(cluster: dict) -> dict:
    """Run simulation for a single cluster. Returns result dict."""
    logger.info("Running cluster: %s (%d personas, %d seats)",
                cluster["name"], cluster["n_personas"], cluster["n_seats"])
    request = build_cluster_request(cluster)
    result = await run_niobe_study(request)
    shares = extract_vote_shares(result)
    waivers, penalty = _extract_guardrails(result)
    logger.info("  %s → TMC %.1f%% BJP %.1f%% Left %.1f%% Other %.1f%%",
                cluster["id"],
                shares["TMC"] * 100, shares["BJP"] * 100,
                shares["Left-Congress"] * 100, shares["Others"] * 100)
    return {
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


async def run_cluster_ensemble(cluster: dict, n_runs: int = N_ENSEMBLE_RUNS) -> dict:
    """Run a swing cluster n_runs times and average vote shares for stability.

    Reduces random sampling noise by √n_runs without changing pool calibration.
    Used for the 4 kingmaker clusters where every percentage point matters.
    """
    logger.info("Ensemble ×%d starting: %s (%d personas/run, %d seats)",
                n_runs, cluster["name"], cluster["n_personas"], cluster["n_seats"])
    parties = ["TMC", "BJP", "Left-Congress", "Others"]
    all_shares: list[dict[str, float]] = []
    all_waivers: list[dict] = []
    max_penalty = 0.0

    for i in range(n_runs):
        logger.info("  [%s] ensemble run %d/%d", cluster["id"], i + 1, n_runs)
        request = build_cluster_request(cluster)
        result = await run_niobe_study(request)
        shares = extract_vote_shares(result)
        waivers, penalty = _extract_guardrails(result)
        all_waivers.extend(waivers)
        max_penalty = max(max_penalty, penalty)
        all_shares.append(shares)
        logger.info("    run %d → TMC %.1f%% BJP %.1f%% Left %.1f%% Other %.1f%%",
                    i + 1, shares["TMC"] * 100, shares["BJP"] * 100,
                    shares["Left-Congress"] * 100, shares["Others"] * 100)

    # Average across runs then re-normalise
    avg = {p: sum(s[p] for s in all_shares) / n_runs for p in parties}
    total = sum(avg.values())
    avg = {p: round(v / total, 4) for p, v in avg.items()}

    logger.info("  %s ensemble avg → TMC %.1f%% BJP %.1f%% Left %.1f%% Other %.1f%%",
                cluster["id"],
                avg["TMC"] * 100, avg["BJP"] * 100,
                avg["Left-Congress"] * 100, avg["Others"] * 100)

    return {
        "id": cluster["id"],
        "name": cluster["name"],
        "n_seats": cluster["n_seats"],
        "n_personas": cluster["n_personas"] * n_runs,   # total personas run
        "tmc_2021":    cluster["tmc_2021"],
        "bjp_2021":    cluster["bjp_2021"],
        "left_2021":   cluster["left_2021"],
        "others_2021": cluster["others_2021"],
        "sim_tmc":    avg["TMC"],
        "sim_bjp":    avg["BJP"],
        "sim_left":   avg["Left-Congress"],
        "sim_others": avg["Others"],
        "swing_notes": cluster["swing_notes"],
        "key_seats":   cluster["key_seats"],
        "marginal_seats_2021": cluster.get("marginal_seats_2021"),
        "ensemble_runs": n_runs,
        "ensemble_detail": all_shares,
        "gate_waivers": all_waivers,
        "confidence_penalty": max_penalty,
    }


async def run_all_clusters(cluster_ids: list[str] | None = None) -> dict:
    """Run all (or selected) clusters and produce consolidated results."""
    target_clusters = CLUSTERS
    if cluster_ids:
        target_clusters = [c for c in CLUSTERS if c["id"] in cluster_ids]
        if not target_clusters:
            raise ValueError(f"Unknown cluster IDs: {cluster_ids}")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    partial_path = Path(os.getenv("SIMULATTE_PARTIAL_DIR", "/tmp/wb_reruns")) / f"{run_id}.partial.json"
    partial_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Starting WB 2026 constituency run | id=%s | clusters=%d | total_personas=%d",
                run_id, len(target_clusters),
                sum(c["n_personas"] for c in target_clusters))

    # Run clusters sequentially to manage API rate limits.
    # Swing clusters use ensemble averaging (3 independent runs).
    cluster_results = []
    for cluster in target_clusters:
        if cluster["id"] in SWING_CLUSTER_IDS:
            cr = await run_cluster_ensemble(cluster, n_runs=N_ENSEMBLE_RUNS)
        else:
            cr = await run_cluster(cluster)
        cluster_results.append(cr)
        _write_partial_results(
            partial_path,
            run_id=run_id,
            cluster_results=cluster_results,
            status="in_progress",
            is_partial=True,
        )

    confidence_penalty = _aggregate_confidence_penalty(cluster_results)
    seat_result = compute_seat_predictions(
        cluster_results,
        use_cube_law=True,
        confidence_penalty=confidence_penalty,
        is_partial=False,
    )
    _write_partial_results(
        partial_path,
        run_id=run_id,
        cluster_results=cluster_results,
        status="completed",
        is_partial=False,
    )

    return {
        "run_id": run_id,
        "run_date": datetime.now(timezone.utc).isoformat(),
        "n_clusters": len(cluster_results),
        "total_personas": sum(c["n_personas"] for c in cluster_results),
        "total_seats": 294,
        "cluster_results": cluster_results,
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
    partial_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


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
    p.add_argument("--results-file", type=str, metavar="PATH",
                   help="Load existing JSON results file")
    p.add_argument("--seat-model-only", type=str, metavar="PATH",
                   help="Re-run seat model on existing results file")
    p.add_argument("--cost-trace", type=str, default=None,
                   help="Dump per-call cost CSV to this path at end of run")
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
        if args.results_file:
            load_and_display(Path(args.results_file))
            return

        if args.seat_model_only:
            load_and_display(Path(args.seat_model_only))
            return

        if args.dry_run:
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
        results = await run_all_clusters(cluster_ids)

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
    finally:
        try:
            _dump_cost_trace()
        finally:
            signal.signal(signal.SIGINT, prior_sigint)
            signal.signal(signal.SIGTERM, prior_sigterm)


if __name__ == "__main__":
    asyncio.run(main())
