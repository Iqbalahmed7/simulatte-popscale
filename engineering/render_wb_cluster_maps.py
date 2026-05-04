"""render_wb_cluster_maps.py

Render real West Bengal cluster maps from the India_AC shapefile, dissolved
to the 10 wb_2026 cluster polygons used in the post-mortem deck.

Outputs PNGs into engineering/maps/:
  - wb_predicted_map.png  (9 TMC-predicted clusters bright; Darjeeling dim)
  - wb_actual_map.png     (Murshidabad bright; 9 others dim)
  - wb_cluster_<id>.png   (one per cluster, target highlighted in SIGNAL green)
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch
from matplotlib.path import Path as MplPath

ROOT = Path(__file__).resolve().parents[1]
SHP = ROOT / "maps-master" / "assembly-constituencies" / "India_AC.shp"
OUT = ROOT / "engineering" / "maps"
OUT.mkdir(parents=True, exist_ok=True)

# Brand colours
PARCHMENT = "#E9E6DF"
SIGNAL = "#A8FF3E"
BG = "#050505"
DIM_ALPHA = 0.12

# District -> cluster mapping (district names as in shapefile, uppercase)
# Districts in shapefile: BANKURA, BARDDHAMAN, BIRBHUM, DAKSHIN DINAJPUR *,
# DARJILING, HAORA, HUGLI, JALPAIGURI, KOCH BIHAR, KOLKATA, MALDAH,
# MURSHIDABAD, NADIA, NORTH 24 PARGANAS, PASCHIM MEDINAPUR, PURBA MEDINAPUR,
# PURULIYA, SOUTH 24 PARGANAS, UTTAR DINAJPUR
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

# TMC predicted winners (everything except darjeeling_hills)
PREDICTED_TMC = {
    "matua_belt", "presidency_suburbs", "jungle_mahal", "south_rural",
    "kolkata_urban", "burdwan_industrial", "north_bengal", "murshidabad",
    "malda",
}
ACTUAL_TMC = {"murshidabad"}


def load_clusters() -> gpd.GeoDataFrame:
    print(f"Loading shapefile: {SHP}")
    gdf = gpd.read_file(SHP)
    wb = gdf[gdf["ST_NAME"] == "WEST BENGAL"].copy()
    print(f"WB rows: {len(wb)}")

    # Map districts -> clusters
    wb["cluster"] = wb["DIST_NAME"].map(DISTRICT_TO_CLUSTER)
    missing = wb[wb["cluster"].isna()]
    if len(missing):
        print(f"WARN unmapped districts: {missing['DIST_NAME'].unique().tolist()}")
        wb = wb.dropna(subset=["cluster"])

    # Simplify to keep file size sane
    wb["geometry"] = wb["geometry"].simplify(tolerance=0.003, preserve_topology=True)

    # Dissolve into 10 cluster polygons
    clusters = wb.dissolve(by="cluster")
    clusters = clusters.reset_index()
    print(f"Clusters: {clusters['cluster'].tolist()}")
    return clusters


def render_map(clusters: gpd.GeoDataFrame, fills: dict[str, tuple[str, float]],
               out_path: Path, highlight: str | None = None) -> None:
    """Render WB map. fills: cluster_id -> (color, alpha). highlight overrides fill."""
    fig, ax = plt.subplots(figsize=(10, 10), dpi=160)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)

    for _, row in clusters.iterrows():
        cid = row["cluster"]
        if highlight and cid == highlight:
            color, alpha = SIGNAL, 1.0
        else:
            color, alpha = fills.get(cid, (PARCHMENT, DIM_ALPHA))
        gpd.GeoSeries([row.geometry]).plot(
            ax=ax, facecolor=color, edgecolor=BG, linewidth=0.6, alpha=alpha,
        )

    ax.set_axis_off()
    ax.set_aspect("equal")
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
    fig.savefig(out_path, dpi=160, facecolor=BG, edgecolor="none",
                bbox_inches="tight", pad_inches=0.1)
    plt.close(fig)
    print(f"  wrote {out_path.name}")


def main():
    clusters = load_clusters()

    # Hero maps
    pred_fills = {cid: (PARCHMENT, 1.0) for cid in PREDICTED_TMC}
    pred_fills["darjeeling_hills"] = (PARCHMENT, DIM_ALPHA)
    render_map(clusters, pred_fills, OUT / "wb_predicted_map.png")

    act_fills = {cid: (PARCHMENT, DIM_ALPHA) for cid in DISTRICT_TO_CLUSTER.values()}
    for cid in ACTUAL_TMC:
        act_fills[cid] = (PARCHMENT, 1.0)
    render_map(clusters, act_fills, OUT / "wb_actual_map.png")

    # Per-cluster mini maps (highlight target in SIGNAL)
    for cid in clusters["cluster"].unique():
        dim = {c: (PARCHMENT, DIM_ALPHA) for c in clusters["cluster"].unique()}
        render_map(clusters, dim, OUT / f"wb_cluster_{cid}.png", highlight=cid)

    print("done")


if __name__ == "__main__":
    main()
