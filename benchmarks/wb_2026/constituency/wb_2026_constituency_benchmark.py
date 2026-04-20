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
import asyncio
import json
import logging
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
from .cluster_definitions import CLUSTERS            # noqa: E402
from .seat_model import compute_seat_predictions, print_seat_report  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("wb_2026_constituency")

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
    }


async def run_all_clusters(cluster_ids: list[str] | None = None) -> dict:
    """Run all (or selected) clusters and produce consolidated results."""
    target_clusters = CLUSTERS
    if cluster_ids:
        target_clusters = [c for c in CLUSTERS if c["id"] in cluster_ids]
        if not target_clusters:
            raise ValueError(f"Unknown cluster IDs: {cluster_ids}")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    logger.info("Starting WB 2026 constituency run | id=%s | clusters=%d | total_personas=%d",
                run_id, len(target_clusters),
                sum(c["n_personas"] for c in target_clusters))

    # Run clusters sequentially to manage API rate limits
    cluster_results = []
    for cluster in target_clusters:
        cr = await run_cluster(cluster)
        cluster_results.append(cr)

    seat_result = compute_seat_predictions(cluster_results)

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
        "tmc_majority": seat_result["tmc_majority"],
    }


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
    seat_result = compute_seat_predictions(seat_input)
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
    return p.parse_args()


async def main() -> None:
    args = parse_args()

    if args.results_file:
        load_and_display(Path(args.results_file))
        return

    if args.seat_model_only:
        load_and_display(Path(args.seat_model_only))
        return

    if args.dry_run:
        print("\n── WB 2026 Constituency Benchmark — DRY RUN ──")
        print(f"  Clusters: {len(CLUSTERS)}")
        total_p = sum(c["n_personas"] for c in CLUSTERS)
        print(f"  Total personas: {total_p}")
        print(f"  Total seats: {sum(c['n_seats'] for c in CLUSTERS)}")
        print(f"  Est. cost: ~${total_p * 0.05:.0f}–${total_p * 0.08:.0f}")
        print()
        for c in CLUSTERS:
            print(f"  [{c['id']:25s}] {c['n_seats']:3d} seats | {c['n_personas']:2d} personas | "
                  f"2021: TMC {c['tmc_2021']:.0%} BJP {c['bjp_2021']:.0%} Left {c['left_2021']:.0%}")
        return

    cluster_ids = [args.cluster] if args.cluster else None
    results = await run_all_clusters(cluster_ids)

    print_cluster_vote_shares(results["cluster_results"])

    seat_input = results["cluster_results"]
    seat_result = compute_seat_predictions(seat_input)
    print_seat_report(seat_result)

    output_dir = _BENCH_DIR / "results"
    saved = save_results(results, output_dir)
    print(f"\nResults saved: {saved}")


if __name__ == "__main__":
    asyncio.run(main())
