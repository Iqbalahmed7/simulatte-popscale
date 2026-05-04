"""render_wb_per_ac.py

Per-AC West Bengal maps + parliament hemicycle charts for WB 2026 post-mortem
deck slides 3 (predicted) and 4 (actual).

Outputs to engineering/maps/:
  - wb_predicted_per_ac.png
  - wb_actual_per_ac.png
  - wb_predicted_hemicycle.png
  - wb_actual_hemicycle.png

NOTE: actual per-AC winners are estimates. ECI per-AC results aren't yet
published; we distribute the cluster-level totals across constituencies using
deterministic seeded sampling, weighted toward plausible sub-regions
(Muslim-belt north → TMC; urban → BJP; etc.). Replace with real ECI data when
available.
"""
from __future__ import annotations

import math
import random
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SHP = ROOT / "maps-master" / "assembly-constituencies" / "India_AC.shp"
OUT = ROOT / "engineering" / "maps"
OUT.mkdir(parents=True, exist_ok=True)

# Brand + party colors
BG = "#050505"
PARCHMENT = "#E9E6DF"
SIGNAL = "#A8FF3E"
DIM = "#3A3A38"

C_TMC = "#3FA34D"   # green (party convention)
C_BJP = "#F4A02C"   # orange
C_INDI = "#C44545"  # red
C_OTH = "#8A8A8A"   # grey

PARTY_COLOR = {"TMC": C_TMC, "BJP": C_BJP, "INDI": C_INDI, "OTH": C_OTH}

# District -> cluster mapping (matches render_wb_cluster_maps.py)
DISTRICT_TO_CLUSTER = {
    "MURSHIDABAD": "murshidabad",
    "MALDAH": "malda",
    "NADIA": "matua_belt",
    "NORTH 24 PARGANAS": "presidency_suburbs",
    "BANKURA": "jungle_mahal",
    "PURULIYA": "jungle_mahal",
    "PASCHIM MEDINAPUR": "jungle_mahal",
    "KOCH BIHAR": "north_bengal",
    "JALPAIGURI": "north_bengal",
    "UTTAR DINAJPUR": "north_bengal",
    "DAKSHIN DINAJPUR *": "north_bengal",
    "KOLKATA": "kolkata_urban",
    "SOUTH 24 PARGANAS": "south_rural",
    "PURBA MEDINAPUR": "south_rural",
    "HAORA": "south_rural",
    "HUGLI": "south_rural",
    "BARDDHAMAN": "burdwan_industrial",
    "BIRBHUM": "burdwan_industrial",
    "DARJILING": "darjeeling_hills",
}

# ── PREDICTED (model output: TMC sweep, BJP fringe in Darjeeling/N.Bengal) ──
# 294 / TMC 194, BJP 45, INDI 50, OTH 5
# Cluster sizes from shapefile (district→cluster mapping above):
#   south_rural 81, jungle_mahal 40, burdwan_industrial 36, north_bengal 36,
#   presidency_suburbs 33, murshidabad 22, matua_belt 17, malda 12,
#   kolkata_urban 11, darjeeling_hills 6  (sum = 294)
# Headline totals must match: TMC 194, BJP 45, INDI 50, OTH 5
PREDICTED = {
    "murshidabad":        {"TMC": 19, "BJP": 1,  "INDI": 2,  "OTH": 0},  # 22
    "malda":              {"TMC": 7,  "BJP": 1,  "INDI": 4,  "OTH": 0},  # 12
    "matua_belt":         {"TMC": 12, "BJP": 3,  "INDI": 2,  "OTH": 0},  # 17
    "presidency_suburbs": {"TMC": 22, "BJP": 6,  "INDI": 5,  "OTH": 0},  # 33
    "jungle_mahal":       {"TMC": 26, "BJP": 8,  "INDI": 6,  "OTH": 0},  # 40
    "south_rural":        {"TMC": 58, "BJP": 11, "INDI": 12, "OTH": 0},  # 81
    "kolkata_urban":      {"TMC": 7,  "BJP": 1,  "INDI": 3,  "OTH": 0},  # 11
    "burdwan_industrial": {"TMC": 24, "BJP": 6,  "INDI": 6,  "OTH": 0},  # 36
    "north_bengal":       {"TMC": 18, "BJP": 6,  "INDI": 8,  "OTH": 4},  # 36
    "darjeeling_hills":   {"TMC": 1,  "BJP": 2,  "INDI": 2,  "OTH": 1},  #  6
}
# Verify: TMC=19+7+12+22+26+58+7+24+18+1=194 ✓
#         BJP=1+1+3+6+8+11+1+6+6+2=45 ✓
#         INDI=2+4+2+5+6+12+3+6+8+2=50 ✓
#         OTH=0+0+0+0+0+0+0+0+4+1=5 ✓

# ── ACTUAL (cluster estimates per task spec) ──
# 294 / BJP 203, TMC 84, INDI 6, OTH 1
ACTUAL = {
    "murshidabad":        {"TMC": 13, "BJP": 7,  "INDI": 2, "OTH": 0},  # 22
    "malda":              {"TMC": 4,  "BJP": 6,  "INDI": 2, "OTH": 0},  # 12
    "matua_belt":         {"TMC": 3,  "BJP": 14, "INDI": 0, "OTH": 0},  # 17
    "presidency_suburbs": {"TMC": 8,  "BJP": 25, "INDI": 0, "OTH": 0},  # 33
    "jungle_mahal":       {"TMC": 10, "BJP": 30, "INDI": 0, "OTH": 0},  # 40
    "south_rural":        {"TMC": 26, "BJP": 54, "INDI": 1, "OTH": 0},  # 81
    "kolkata_urban":      {"TMC": 4,  "BJP": 7,  "INDI": 0, "OTH": 0},  # 11
    "burdwan_industrial": {"TMC": 9,  "BJP": 26, "INDI": 1, "OTH": 0},  # 36
    "north_bengal":       {"TMC": 5,  "BJP": 31, "INDI": 0, "OTH": 0},  # 36
    "darjeeling_hills":   {"TMC": 2,  "BJP": 3,  "INDI": 0, "OTH": 1},  #  6
}
# Verify: TMC=13+4+3+8+10+26+4+9+5+2=84 ✓
#         BJP=7+6+14+25+30+54+7+26+31+3=203 ✓
#         INDI=2+2+0+0+0+1+0+1+0+0=6 ✓
#         OTH=0+0+0+0+0+0+0+0+0+1=1 ✓


def assign_winners(wb: gpd.GeoDataFrame, totals: dict, seed: int) -> dict[int, str]:
    """Map AC_NO -> winner string, by sampling within each cluster.

    Northern/Muslim-belt ACs (lower latitude index inverted) bias toward TMC;
    urban-Kolkata ACs bias toward BJP. Implemented as a simple latitude-based
    score for diverse-looking output.
    """
    rng = random.Random(seed)
    winners: dict[int, str] = {}
    # group by cluster
    for cluster, counts in totals.items():
        sub = wb[wb["cluster"] == cluster].copy()
        if len(sub) == 0:
            continue
        # sort by centroid y (north → south) for muslim-belt bias
        sub["cy"] = sub.geometry.centroid.y
        # build pool
        pool = []
        for party, n in counts.items():
            pool.extend([party] * n)
        # pad/truncate to match AC count
        while len(pool) < len(sub):
            pool.append("BJP")
        pool = pool[: len(sub)]
        rng.shuffle(pool)
        # bias: in muslim-belt clusters, the highest-y (northernmost) ACs go TMC
        if cluster in {"murshidabad", "malda"}:
            order = sub.sort_values("cy", ascending=False).index.tolist()
            tmc_first = sorted(pool, key=lambda p: 0 if p == "TMC" else 1)
            for idx, party in zip(order, tmc_first):
                winners[int(sub.loc[idx, "AC_NO"])] = party
        elif cluster == "kolkata_urban":
            # central-urban ACs bias BJP
            order = sub.sort_values("cy").index.tolist()
            bjp_first = sorted(pool, key=lambda p: 0 if p == "BJP" else 1)
            for idx, party in zip(order, bjp_first):
                winners[int(sub.loc[idx, "AC_NO"])] = party
        else:
            for idx, party in zip(sub.index.tolist(), pool):
                winners[int(sub.loc[idx, "AC_NO"])] = party
    return winners


def render_map(wb: gpd.GeoDataFrame, winners: dict[int, str], out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 10), dpi=160)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    colors = []
    for _, row in wb.iterrows():
        winner = winners.get(int(row["AC_NO"]), "OTH")
        colors.append(PARTY_COLOR[winner])
    wb.plot(ax=ax, color=colors, edgecolor=BG, linewidth=0.35)
    ax.set_axis_off()
    ax.set_aspect("equal")
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
    fig.savefig(out_path, dpi=160, facecolor=BG, edgecolor="none",
                bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    print(f"  wrote {out_path.name}")


def render_hemicycle(seat_counts: dict[str, int], out_path: Path,
                     order=("TMC", "BJP", "INDI", "OTH")) -> None:
    """Parliament-style hemicycle. 294 dots in 7 concentric rows."""
    total = sum(seat_counts.values())
    assert total == 294, total
    rows = 7
    # distribute seats across rows so density is roughly even
    # row radii (innermost → outermost)
    radii = np.linspace(0.45, 1.0, rows)
    # seats per row proportional to arc length (r * pi)
    weights = radii / radii.sum()
    per_row = np.round(weights * total).astype(int)
    # adjust to exact total
    diff = total - per_row.sum()
    per_row[-1] += diff
    # build flat list of (radius, theta) seat positions, ordered by angle
    seats = []
    for r, n in zip(radii, per_row):
        # angles 180° → 0° (left to right)
        thetas = np.linspace(math.pi, 0, n)
        for t in thetas:
            seats.append((r, t))
    # sort all seats by angle (left → right)
    seats.sort(key=lambda s: -s[1])
    # build party sequence (left wing usually opposition, but here we go
    # ordered: TMC, BJP, INDI, OTH so the dominant block is contiguous)
    seq = []
    for party in order:
        seq.extend([party] * seat_counts[party])
    # fig
    fig, ax = plt.subplots(figsize=(10, 5.5), dpi=160)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    for (r, t), party in zip(seats, seq):
        x = r * math.cos(t)
        y = r * math.sin(t)
        ax.scatter(x, y, s=110, color=PARTY_COLOR[party], edgecolors=BG, linewidths=0.6)
    ax.set_xlim(-1.15, 1.15)
    ax.set_ylim(-0.1, 1.15)
    ax.set_aspect("equal")
    ax.set_axis_off()
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
    fig.savefig(out_path, dpi=160, facecolor=BG, edgecolor="none",
                bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    print(f"  wrote {out_path.name}")


def main():
    print(f"Loading shapefile: {SHP}")
    gdf = gpd.read_file(SHP)
    wb = gdf[gdf["ST_NAME"] == "WEST BENGAL"].copy()
    wb["cluster"] = wb["DIST_NAME"].map(DISTRICT_TO_CLUSTER)
    wb = wb.dropna(subset=["cluster"])
    wb["geometry"] = wb["geometry"].simplify(tolerance=0.002, preserve_topology=True)
    print(f"WB ACs: {len(wb)}")

    pred_winners = assign_winners(wb, PREDICTED, seed=42)
    actual_winners = assign_winners(wb, ACTUAL, seed=137)

    # sanity check totals
    def tally(w):
        from collections import Counter
        return Counter(w.values())
    print("predicted tally:", tally(pred_winners))
    print("actual tally   :", tally(actual_winners))

    render_map(wb, pred_winners, OUT / "wb_predicted_per_ac.png")
    render_map(wb, actual_winners, OUT / "wb_actual_per_ac.png")

    # hemicycle totals
    pred_totals = {"TMC": 194, "BJP": 45, "INDI": 50, "OTH": 5}
    actual_totals = {"TMC": 84, "BJP": 203, "INDI": 6, "OTH": 1}
    render_hemicycle(pred_totals, OUT / "wb_predicted_hemicycle.png",
                     order=("INDI", "OTH", "BJP", "TMC"))
    render_hemicycle(actual_totals, OUT / "wb_actual_hemicycle.png",
                     order=("TMC", "INDI", "OTH", "BJP"))
    print("done")


if __name__ == "__main__":
    main()
