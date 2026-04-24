"""seat_model.py — B-WB-6

Uniform swing seat model for West Bengal 2026.

Converts per-cluster simulated vote shares into seat count predictions
using a uniform swing model applied to each cluster's 2021 baseline.

MODEL ASSUMPTIONS (declared)
──────────────────────────────
1. Uniform swing within cluster: every seat in the cluster shifts by
   the same delta as the cluster-level simulation vs 2021 baseline.
2. Seat winner = party with highest projected vote share in each seat.
3. Since we don't have seat-by-seat 2021 data for all 294 seats, we use
   a simplified model:
   - Base seat share per party: proportional to 2021 vote share within cluster
   - Swing effect: shifts seat share in proportion to vote share swing
   - Marginal buffer: ±5pp seat-share uncertainty acknowledged

This is a first-order approximation. Seat-level calibration with ECI data
will improve accuracy in future iterations.

KNOWN LIMITATIONS
──────────────────
- FPTP cube-law effects are not modelled (reality would amplify majority swings)
- Does not model candidate effects or local incumbency
- Left vote share is partly "transferred" through NOTA/Other in FPTP reality
"""
from __future__ import annotations

import math


def compute_seat_predictions(
    cluster_results: list[dict],
    use_cube_law: bool = True,
    *,
    confidence_penalty: float = 0.0,
    is_partial: bool = False,
) -> dict:
    """Convert cluster vote shares to seat predictions.

    Args:
        cluster_results: List of dicts, each with keys:
            - id, name, n_seats
            - tmc_2021, bjp_2021, left_2021, others_2021 (baselines)
            - sim_tmc, sim_bjp, sim_left, sim_others (simulated shares)
            - marginal_seats_2021 (optional): actual ECI marginal seat count
        use_cube_law: Apply FPTP cube-law amplification (default True).
            In FPTP systems seats scale ~cubically with vote share ratios.
            Corrects the systematic undercount of the leading party.

    Returns:
        dict with:
            - seat_predictions: {TMC, BJP, Left-Congress, Others} seat counts
            - cluster_breakdown: per-cluster seat allocation
            - swing_analysis: per-cluster swing magnitudes
            - confidence_range: ±seat range based on marginal seat count
    """
    parties = ["TMC", "BJP", "Left-Congress", "Others"]
    total_seats = {p: 0 for p in parties}
    cluster_breakdown = []
    swing_analysis = []

    for r in cluster_results:
        n = r["n_seats"]
        baseline = {
            "TMC": r["tmc_2021"],
            "BJP": r["bjp_2021"],
            "Left-Congress": r["left_2021"],
            "Others": r["others_2021"],
        }
        simulated = {
            "TMC": r.get("sim_tmc", r["tmc_2021"]),
            "BJP": r.get("sim_bjp", r["bjp_2021"]),
            "Left-Congress": r.get("sim_left", r["left_2021"]),
            "Others": r.get("sim_others", r["others_2021"]),
        }

        # Normalise simulated shares to sum to 1.0
        sim_total = sum(simulated.values())
        if sim_total > 0:
            simulated = {p: v / sim_total for p, v in simulated.items()}

        # Compute swing per party
        swings = {p: simulated[p] - baseline[p] for p in parties}

        # Uniform swing seat model:
        # Each party's projected vote share = baseline + swing
        projected_shares = {}
        for p in parties:
            proj = baseline[p] + swings[p]
            projected_shares[p] = max(0.0, proj)

        # Re-normalise projected vote shares
        proj_total = sum(projected_shares.values())
        if proj_total > 0:
            projected_shares = {p: v / proj_total for p, v in projected_shares.items()}

        # Convert vote shares → seat shares.
        # Cube-law (default): in FPTP systems seats scale ~cubically with vote ratio,
        # amplifying the leading party. Linear is a lower bound; cube-law is more realistic.
        if use_cube_law:
            cube = {p: projected_shares[p] ** 3 for p in parties}
            cube_total = sum(cube.values())
            seat_shares = (
                {p: cube[p] / cube_total for p in parties}
                if cube_total > 0 else projected_shares
            )
        else:
            seat_shares = projected_shares

        raw_seats = {p: seat_shares[p] * n for p in parties}

        # Round to integers preserving total using largest-remainder method
        floor_seats = {p: math.floor(v) for p, v in raw_seats.items()}
        remainder = {p: raw_seats[p] - floor_seats[p] for p in parties}
        allocated = sum(floor_seats.values())
        seats_to_distribute = n - allocated

        # Distribute remaining seats to parties with largest remainders
        sorted_by_remainder = sorted(parties, key=lambda p: remainder[p], reverse=True)
        final_seats = dict(floor_seats)
        for i in range(int(seats_to_distribute)):
            final_seats[sorted_by_remainder[i]] += 1

        # Add to totals
        for p in parties:
            total_seats[p] += final_seats[p]

        # Marginal seats: use actual 2021 ECI data if provided,
        # otherwise estimate from projected vote-share margin.
        if r.get("marginal_seats_2021") is not None:
            marginal_seat_count = r["marginal_seats_2021"]
        else:
            sorted_proj = sorted(projected_shares.values(), reverse=True)
            margin = sorted_proj[0] - sorted_proj[1] if len(sorted_proj) > 1 else sorted_proj[0]
            marginal_seat_count = max(1, round(n * max(0, 0.15 - margin) / 0.15))

        cluster_breakdown.append({
            "id": r["id"],
            "name": r["name"],
            "n_seats": n,
            "seats": final_seats,
            "projected_vote_shares": {p: round(projected_shares[p], 3) for p in parties},
            "seat_shares": {p: round(seat_shares[p], 3) for p in parties},
            "swing": {p: round(swings[p], 3) for p in parties},
            "marginal_seats": marginal_seat_count,
            "ensemble_runs": r.get("ensemble_runs", 1),
        })

        swing_analysis.append({
            "cluster": r["name"],
            "tmc_swing": round(swings["TMC"], 3),
            "bjp_swing": round(swings["BJP"], 3),
            "left_swing": round(swings["Left-Congress"], 3),
        })

    # Confidence range: ±half of total marginal seats
    total_marginal = sum(c["marginal_seats"] for c in cluster_breakdown)
    confidence_range = max(5, total_marginal // 2)
    confidence_range_seats = confidence_range
    if confidence_penalty > 0:
        confidence_range_seats = round(confidence_range * (1 + confidence_penalty))

    all_waivers: list[dict] = []
    for row in cluster_results:
        waivers = row.get("gate_waivers") or []
        if isinstance(waivers, list):
            all_waivers.extend(waivers)

    schema_version = "2.0" if (confidence_penalty > 0 or is_partial or all_waivers) else "1.0"

    return {
        "schema_version": schema_version,
        "seat_predictions": total_seats,
        "cluster_breakdown": cluster_breakdown,
        "swing_analysis": swing_analysis,
        "total_marginal_seats": total_marginal,
        "confidence_range_seats": confidence_range_seats,
        "is_partial": is_partial,
        "gate_waivers": all_waivers,
        "majority_threshold": 148,
        "tmc_majority": total_seats["TMC"] >= 148,
        "seat_model": "cube_law" if use_cube_law else "linear",
    }


def print_seat_report(result: dict) -> None:
    """Print a formatted seat prediction report."""
    preds = result["seat_predictions"]
    print("\n" + "═" * 72)
    print("  WB 2026 CONSTITUENCY PREDICTION — Seat Count")
    print("═" * 72)
    print(f"  Majority threshold: 148 of 294 seats")
    print()
    print(f"  {'Party':<22} {'Seats':>8} {'±Range':>8} {'Majority?':>10}")
    print("  " + "─" * 52)
    cr = result["confidence_range_seats"]
    for party, seats in sorted(preds.items(), key=lambda x: -x[1]):
        maj = "✓ MAJORITY" if party == "TMC" and result["tmc_majority"] else ""
        print(f"  {party:<22} {seats:>8}   ±{cr:<6} {maj:>10}")
    print()
    print(f"  Marginal seats (high uncertainty): {result['total_marginal_seats']}")
    print(f"  TMC majority: {'YES' if result['tmc_majority'] else 'NO'}")
    print()

    print("  Cluster breakdown:")
    print(f"  {'Cluster':<38} {'TMC':>5} {'BJP':>5} {'Left':>5} {'Swng(T)':>8}")
    print("  " + "─" * 65)
    for c in result["cluster_breakdown"]:
        seats = c["seats"]
        swing_t = c["swing"]["TMC"]
        swing_str = f"{swing_t:+.1%}"
        print(f"  {c['name'][:37]:<38} {seats['TMC']:>5} {seats['BJP']:>5} "
              f"{seats['Left-Congress']:>5} {swing_str:>8}")
    print("═" * 72)
