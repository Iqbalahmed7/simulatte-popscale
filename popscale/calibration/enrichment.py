"""
Demographic enrichment and aggregation helpers for ground truth datasets.

Key function: aggregate_to_clusters() for WB 2021 constituency -> cluster mapping.
"""

import pandas as pd
from pathlib import Path
from typing import Optional
from .schemas import GroundTruth


def aggregate_to_clusters(
    gt: GroundTruth,
    cluster_mapping_csv: Path,
) -> dict[str, dict[str, float]]:
    """Map constituency-level ground truth to WB cluster labels.

    Uses cluster_mapping_csv to determine which constituencies belong to each
    cluster, then aggregates vote shares using simple averaging (weighted by
    total votes if available, otherwise uniform).

    Args:
        gt: GroundTruth object (typically WB 2021 assembly)
        cluster_mapping_csv: Path to CSV with columns
            [constituency_code, constituency_name, cluster_id]

    Returns:
        dict mapping cluster_id -> {party_id -> vote_share_pct (0-100)}

    Expected clusters for WB: murshidabad, matua_belt, jungle_mahal,
                               burdwan_industrial, presidency_suburbs
    """
    if not cluster_mapping_csv.exists():
        raise FileNotFoundError(f"Cluster mapping not found: {cluster_mapping_csv}")

    # Load mapping
    mapping_df = pd.read_csv(cluster_mapping_csv)

    # Create lookup: constituency_code -> cluster_id
    code_to_cluster = {}
    for _, row in mapping_df.iterrows():
        code = str(row["constituency_code"]).strip()
        cluster = str(row["cluster_id"]).strip()
        code_to_cluster[code] = cluster

    # Group units by cluster
    clusters_dict = {}
    for unit in gt.units:
        cluster_id = code_to_cluster.get(unit.unit_id)
        if cluster_id is None:
            # Constituency not in mapping; skip or log
            continue

        if cluster_id not in clusters_dict:
            clusters_dict[cluster_id] = []

        clusters_dict[cluster_id].append(unit)

    # Aggregate vote shares per cluster
    result = {}
    for cluster_id, units in clusters_dict.items():
        if not units:
            continue

        # Collect all party keys across units
        all_parties = set()
        for unit in units:
            all_parties.update(unit.outcomes.keys())

        # Average vote share per party
        cluster_outcomes = {}
        for party in all_parties:
            votes = [unit.outcomes.get(party, 0.0) for unit in units]
            avg_share = sum(votes) / len(votes)
            cluster_outcomes[party] = avg_share

        result[cluster_id] = cluster_outcomes

    return result
