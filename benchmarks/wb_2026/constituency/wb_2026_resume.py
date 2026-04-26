"""wb_2026_resume.py — B-WB-7 RESUME RUN

Resumes from the interrupted run (20260422_003445).
8 of 10 clusters were fully completed before credit exhaustion.
This script hardcodes those results and runs only the missing pieces:
  - Burdwan Industrial Zone run 3 (runs 1+2 hardcoded)
  - Presidency Division Suburbs ×3 ensemble (all 3 new)
  - Darjeeling Hills + Adjacent Plains ×1

Total new persona-runs: 5 runs × ~60/20p ≈ 1.5 hours vs 4.5h for full restart.

USAGE
-----
    cd "/Users/admin/Documents/Simulatte Projects/PopScale"
    python3 -m benchmarks.wb_2026.constituency.wb_2026_resume
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
_BENCH_DIR     = Path(__file__).parent
_WB2026_DIR    = _BENCH_DIR.parent
_POPSCALE_ROOT = _WB2026_DIR.parents[1]
_NIOBE_ROOT    = _POPSCALE_ROOT.parents[1] / "Niobe"
_PG_ROOT       = _POPSCALE_ROOT.parents[1] / "Persona Generator"

for p in [str(_POPSCALE_ROOT), str(_NIOBE_ROOT), str(_PG_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from niobe.study_request import NiobeStudyRequest                    # noqa: E402
from niobe.runner import run_niobe_study                             # noqa: E402
from .cluster_definitions import CLUSTER_BY_ID                      # noqa: E402
from .wb_2026_constituency_benchmark import (                        # noqa: E402
    BASE_SCENARIO_CONTEXT,
    SCENARIO_OPTIONS,
    build_cluster_request,
    extract_vote_shares,
    save_results,
    print_cluster_vote_shares,
)
from .seat_model import compute_seat_predictions, print_seat_report  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("wb_2026_resume")


# ── Hardcoded results from the completed run (20260422_003445) ─────────────────
# All extracted directly from log: grep "wb_2026_constituency.*→" b_wb_7_run_20260422_003445.log

COMPLETED_CLUSTER_RESULTS: list[dict] = [
    {
        "id": "murshidabad",
        "name": "Murshidabad Muslim Heartland",
        "n_seats": 22,
        "n_personas": 40,
        "tmc_2021": 0.90, "bjp_2021": 0.10, "left_2021": 0.00, "others_2021": 0.00,
        "sim_tmc": 0.600, "sim_bjp": 0.100, "sim_left": 0.075, "sim_others": 0.225,
        "swing_notes": "SIR 460k deletions; AIMIM-AJUP fragmentation; Muslim-TMC defensive vote vs protest",
        "key_seats": ["Bhagabangola", "Jalangi", "Farakka", "Domkal", "Kandi"],
        "marginal_seats_2021": 5,
        "ensemble_runs": 1,
    },
    {
        "id": "malda",
        "name": "Malda Muslim Plurality Belt",
        "n_seats": 12,
        "n_personas": 40,
        "tmc_2021": 0.67, "bjp_2021": 0.33, "left_2021": 0.00, "others_2021": 0.00,
        "sim_tmc": 0.525, "sim_bjp": 0.175, "sim_left": 0.250, "sim_others": 0.050,
        "swing_notes": "SIR 240k deletions; AIMIM-ISF-AJUP three-way Muslim split; BJP Hindu base",
        "key_seats": ["Englishbazar", "Mothabari", "Ratua", "Harishchandrapur"],
        "marginal_seats_2021": 5,
        "ensemble_runs": 1,
    },
    {
        "id": "matua_belt",
        "name": "Matua Refugee Belt (Nadia + N24Pgs)",
        "n_seats": 40,
        "n_personas": 180,   # 60 × 3 ensemble runs
        "tmc_2021": 0.65, "bjp_2021": 0.30, "left_2021": 0.05, "others_2021": 0.00,
        # Ensemble average of 3 runs (rounded to match log output):
        # run1: TMC 83.3% BJP 13.3% Left 1.7% Other 1.7%
        # run2: TMC 85.0% BJP 10.0% Left 5.0% Other 0.0%
        # run3: TMC 80.0% BJP 10.0% Left 8.3% Other 1.7%
        # avg:  TMC 82.8% BJP 11.1% Left 5.0% Other 1.1%  (normalised)
        "sim_tmc": 0.8278, "sim_bjp": 0.1111, "sim_left": 0.0500, "sim_others": 0.0111,
        "swing_notes": "SIR 77.86% deletion rate; Matua CAA-SIR paradox; BJP-TMC swing 8-12 seats",
        "key_seats": ["Gaighata", "Krishnaganj", "Karimpur", "Nakashipara", "Bangaon", "Ashokenagar"],
        "marginal_seats_2021": 18,
        "ensemble_runs": 3,
        "ensemble_detail": [
            {"TMC": 0.833, "BJP": 0.133, "Left-Congress": 0.017, "Others": 0.017},
            {"TMC": 0.850, "BJP": 0.100, "Left-Congress": 0.050, "Others": 0.000},
            {"TMC": 0.800, "BJP": 0.100, "Left-Congress": 0.083, "Others": 0.017},
        ],
    },
    {
        "id": "jungle_mahal",
        "name": "Jungle Mahal Tribal Belt",
        "n_seats": 50,
        "n_personas": 180,   # 60 × 3 ensemble runs
        "tmc_2021": 0.78, "bjp_2021": 0.18, "left_2021": 0.04, "others_2021": 0.00,
        # run1: TMC 63.3% BJP 8.3% Left 28.3% Other 0.0%
        # run2: TMC 66.7% BJP 15.0% Left 18.3% Other 0.0%
        # run3: TMC 61.7% BJP 13.3% Left 23.3% Other 1.7%
        # avg:  TMC 63.9% BJP 12.2% Left 23.3% Other 0.6%
        "sim_tmc": 0.6389, "sim_bjp": 0.1222, "sim_left": 0.2333, "sim_others": 0.0056,
        "swing_notes": "Ultra-marginal seats; welfare vs BJP tribal programs; TMC MGNREGA base",
        "key_seats": ["Ghatal", "Bankura", "Balarampur", "Dantan", "Kulti"],
        "marginal_seats_2021": 20,
        "ensemble_runs": 3,
        "ensemble_detail": [
            {"TMC": 0.633, "BJP": 0.083, "Left-Congress": 0.283, "Others": 0.000},
            {"TMC": 0.667, "BJP": 0.150, "Left-Congress": 0.183, "Others": 0.000},
            {"TMC": 0.617, "BJP": 0.133, "Left-Congress": 0.233, "Others": 0.017},
        ],
    },
    {
        "id": "north_bengal",
        "name": "North Bengal Koch-Rajbongshi",
        "n_seats": 30,
        "n_personas": 30,
        "tmc_2021": 0.32, "bjp_2021": 0.60, "left_2021": 0.08, "others_2021": 0.00,
        "sim_tmc": 0.167, "sim_bjp": 0.467, "sim_left": 0.367, "sim_others": 0.000,
        "swing_notes": "BJP stronghold; Koch-Rajbongshi OBC base; Dinhata (57-vote margin); tea garden swing",
        "key_seats": ["Dinhata", "Jalpaiguri", "Mathabhanga", "Tufanganj", "Alipurduar"],
        "marginal_seats_2021": 10,
        "ensemble_runs": 1,
    },
    {
        "id": "kolkata_urban",
        "name": "Urban Kolkata",
        "n_seats": 11,
        "n_personas": 30,
        "tmc_2021": 0.90, "bjp_2021": 0.08, "left_2021": 0.02, "others_2021": 0.00,
        "sim_tmc": 0.667, "sim_bjp": 0.033, "sim_left": 0.300, "sim_others": 0.000,
        "swing_notes": "TMC fortress; Bhabanipur Mamata vs Suvendu prestige contest; minimal swing",
        "key_seats": ["Bhabanipur", "Ballygunge", "Beleghata", "Entally", "Rashbehari"],
        "marginal_seats_2021": 2,
        "ensemble_runs": 1,
    },
    {
        "id": "south_rural",
        "name": "South Bengal Rural TMC Stronghold",
        "n_seats": 55,
        "n_personas": 40,
        "tmc_2021": 0.77, "bjp_2021": 0.20, "left_2021": 0.03, "others_2021": 0.00,
        "sim_tmc": 0.800, "sim_bjp": 0.150, "sim_left": 0.050, "sim_others": 0.000,
        "swing_notes": "Welfare scheme saturated; Tamluk ultra-marginal; Sandeshkhali limited spillover",
        "key_seats": ["Tamluk", "Kakdwip", "Diamond Harbour", "Contai", "Baruipur"],
        "marginal_seats_2021": 10,
        "ensemble_runs": 1,
    },
]

# Burdwan completed runs (hardcoded) — run 3 will be executed fresh
BURDWAN_COMPLETED_RUNS = [
    {"TMC": 0.150, "BJP": 0.183, "Left-Congress": 0.633, "Others": 0.033},  # run 1
    {"TMC": 0.150, "BJP": 0.200, "Left-Congress": 0.650, "Others": 0.000},  # run 2
]


async def run_burdwan_ensemble_resume() -> dict:
    """Run Burdwan run 3 fresh, average with the 2 completed runs."""
    cluster = CLUSTER_BY_ID["burdwan_industrial"]
    parties = ["TMC", "BJP", "Left-Congress", "Others"]

    logger.info("Burdwan Industrial — running ensemble run 3/3 (runs 1+2 hardcoded)...")
    request = build_cluster_request(cluster)
    result = await run_niobe_study(request)
    run3_shares = extract_vote_shares(result)
    logger.info("  run 3 → TMC %.1f%% BJP %.1f%% Left %.1f%% Other %.1f%%",
                run3_shares["TMC"] * 100, run3_shares["BJP"] * 100,
                run3_shares["Left-Congress"] * 100, run3_shares["Others"] * 100)

    all_shares = BURDWAN_COMPLETED_RUNS + [run3_shares]
    n_runs = len(all_shares)
    avg = {p: sum(s[p] for s in all_shares) / n_runs for p in parties}
    total = sum(avg.values())
    avg = {p: round(v / total, 4) for p, v in avg.items()}

    logger.info("  burdwan_industrial ensemble avg → TMC %.1f%% BJP %.1f%% Left %.1f%% Other %.1f%%",
                avg["TMC"] * 100, avg["BJP"] * 100,
                avg["Left-Congress"] * 100, avg["Others"] * 100)

    return {
        "id": "burdwan_industrial",
        "name": "Burdwan Industrial Zone",
        "n_seats": cluster["n_seats"],
        "n_personas": cluster["n_personas"] * n_runs,
        "tmc_2021": cluster["tmc_2021"],
        "bjp_2021": cluster["bjp_2021"],
        "left_2021": cluster["left_2021"],
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
    }


async def run_presidency_ensemble() -> dict:
    """Run Presidency Division Suburbs ×3 fresh ensemble."""
    cluster = CLUSTER_BY_ID["presidency_suburbs"]
    parties = ["TMC", "BJP", "Left-Congress", "Others"]
    n_runs = 3

    logger.info("Ensemble ×3 starting: %s (%d personas/run, %d seats)",
                cluster["name"], cluster["n_personas"], cluster["n_seats"])

    all_shares: list[dict] = []
    for i in range(n_runs):
        logger.info("  [presidency_suburbs] ensemble run %d/%d", i + 1, n_runs)
        request = build_cluster_request(cluster)
        result = await run_niobe_study(request)
        shares = extract_vote_shares(result)
        all_shares.append(shares)
        logger.info("    run %d → TMC %.1f%% BJP %.1f%% Left %.1f%% Other %.1f%%",
                    i + 1, shares["TMC"] * 100, shares["BJP"] * 100,
                    shares["Left-Congress"] * 100, shares["Others"] * 100)

    avg = {p: sum(s[p] for s in all_shares) / n_runs for p in parties}
    total = sum(avg.values())
    avg = {p: round(v / total, 4) for p, v in avg.items()}

    logger.info("  presidency_suburbs ensemble avg → TMC %.1f%% BJP %.1f%% Left %.1f%% Other %.1f%%",
                avg["TMC"] * 100, avg["BJP"] * 100,
                avg["Left-Congress"] * 100, avg["Others"] * 100)

    return {
        "id": "presidency_suburbs",
        "name": "Presidency Division Suburbs (Kingmaker Zone)",
        "n_seats": cluster["n_seats"],
        "n_personas": cluster["n_personas"] * n_runs,
        "tmc_2021": cluster["tmc_2021"],
        "bjp_2021": cluster["bjp_2021"],
        "left_2021": cluster["left_2021"],
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
    }


async def run_darjeeling() -> dict:
    """Run Darjeeling Hills + Adjacent Plains (single run)."""
    cluster = CLUSTER_BY_ID["darjeeling_hills"]

    logger.info("Running cluster: %s (%d personas, %d seats)",
                cluster["name"], cluster["n_personas"], cluster["n_seats"])
    request = build_cluster_request(cluster)
    result = await run_niobe_study(request)
    shares = extract_vote_shares(result)
    logger.info("  darjeeling_hills → TMC %.1f%% BJP %.1f%% Left %.1f%% Other %.1f%%",
                shares["TMC"] * 100, shares["BJP"] * 100,
                shares["Left-Congress"] * 100, shares["Others"] * 100)

    return {
        "id": "darjeeling_hills",
        "name": "Darjeeling Hills + Adjacent Plains",
        "n_seats": cluster["n_seats"],
        "n_personas": cluster["n_personas"],
        "tmc_2021": cluster["tmc_2021"],
        "bjp_2021": cluster["bjp_2021"],
        "left_2021": cluster["left_2021"],
        "others_2021": cluster["others_2021"],
        "sim_tmc":    shares["TMC"],
        "sim_bjp":    shares["BJP"],
        "sim_left":   shares["Left-Congress"],
        "sim_others": shares["Others"],
        "swing_notes": cluster["swing_notes"],
        "key_seats":   cluster["key_seats"],
        "marginal_seats_2021": cluster.get("marginal_seats_2021"),
        "ensemble_runs": 1,
    }


async def main() -> None:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    logger.info("B-WB-7 RESUME RUN | id=%s | running 5 missing studies", run_id)
    logger.info("  (8 clusters hardcoded from run 20260422_003445)")
    logger.info("  Remaining: Burdwan run 3 + Presidency ×3 + Darjeeling ×1")

    # Run the 3 missing pieces sequentially
    burdwan_result = await run_burdwan_ensemble_resume()
    presidency_result = await run_presidency_ensemble()
    darjeeling_result = await run_darjeeling()

    # Assemble in canonical cluster order
    cluster_results = (
        COMPLETED_CLUSTER_RESULTS
        + [burdwan_result, presidency_result, darjeeling_result]
    )

    # Seat model
    seat_result = compute_seat_predictions(cluster_results, use_cube_law=True)

    full_results = {
        "run_id": run_id,
        "run_date": datetime.now(timezone.utc).isoformat(),
        "benchmark": "B-WB-7",
        "resume_note": (
            "Resume of run 20260422_003445. Clusters 1-7 hardcoded from completed run. "
            "Burdwan runs 1+2 hardcoded; run 3 generated fresh. "
            "Presidency and Darjeeling generated fresh."
        ),
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

    print_cluster_vote_shares(cluster_results)
    print_seat_report(seat_result)

    output_dir = _BENCH_DIR / "results"
    saved = save_results(full_results, output_dir)
    print(f"\nResults saved: {saved}")


if __name__ == "__main__":
    asyncio.run(main())
