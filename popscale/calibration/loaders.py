"""
Ground truth dataset loaders for election calibration.

Main entry point: load_ground_truth(election_id) -> GroundTruth
"""

import pandas as pd
from pathlib import Path
from .schemas import GroundTruth, GroundTruthUnit


_DATA_DIR = Path(__file__).parent / "ground_truth"


def load_ground_truth(election_id: str) -> GroundTruth:
    """Load a registered ground truth dataset by ID.

    Args:
        election_id: One of 'us_2024_pres', 'wb_2021_assembly',
                     'india_2024_ls', 'india_2019_ls'

    Returns:
        GroundTruth object with normalized schema

    Raises:
        ValueError: if election_id is unknown
        FileNotFoundError: if dataset CSV not found
    """
    loaders = {
        "us_2024_pres": _load_us_2024_pres,
        "wb_2021_assembly": _load_wb_2021_assembly,
        "india_2024_ls": _load_india_2024_ls,
        "india_2019_ls": _load_india_2019_ls,
    }

    if election_id not in loaders:
        raise ValueError(
            f"Unknown election_id: {election_id}. "
            f"Valid options: {list(loaders.keys())}"
        )

    return loaders[election_id]()


def _load_us_2024_pres() -> GroundTruth:
    """Load US 2024 presidential election (county-level)."""
    csv_path = _DATA_DIR / "us_2024_pres" / "results_county.csv"

    if not csv_path.exists():
        raise FileNotFoundError(f"Dataset not found: {csv_path}")

    df = pd.read_csv(csv_path)

    units = []
    for _, row in df.iterrows():
        outcomes = {
            "trump_pct": row["trump_pct"],
            "harris_pct": row["harris_pct"],
            "other_pct": row["other_pct"],
        }

        # Determine winner
        vote_max = max(
            ("trump_pct", row["trump_pct"]),
            ("harris_pct", row["harris_pct"]),
            ("other_pct", row["other_pct"]),
            key=lambda x: x[1],
        )
        winner = vote_max[0].replace("_pct", "_pct")  # Keep as is
        if vote_max[0] == "trump_pct":
            winner = "trump"
        elif vote_max[0] == "harris_pct":
            winner = "harris"
        else:
            winner = "other"

        # Calculate margin
        sorted_votes = sorted(
            [row["trump_pct"], row["harris_pct"], row["other_pct"]], reverse=True
        )
        margin_pct = sorted_votes[0] - sorted_votes[1]

        unit = GroundTruthUnit(
            unit_id=str(row["county_fips"]),
            unit_name=row["county_name"],
            outcomes=outcomes,
            winner=winner,
            margin_pct=margin_pct,
            turnout_pct=row.get("turnout_pct"),
            metadata={"state_abbr": row.get("state_abbr")},
        )
        units.append(unit)

    return GroundTruth(
        election_id="us_2024_pres",
        date="2024-11-05",
        granularity="county",
        units=units,
    )


def _load_wb_2021_assembly() -> GroundTruth:
    """Load West Bengal 2021 assembly election (constituency-level)."""
    csv_path = _DATA_DIR / "wb_2021_assembly" / "results_constituency.csv"

    if not csv_path.exists():
        raise FileNotFoundError(f"Dataset not found: {csv_path}")

    df = pd.read_csv(csv_path)

    units = []
    for _, row in df.iterrows():
        outcomes = {
            "tmc_pct": row["tmc_pct"],
            "bjp_pct": row["bjp_pct"],
            "left_pct": row["left_pct"],
            "congress_pct": row["congress_pct"],
            "others_pct": row["others_pct"],
        }

        # Winner from dataset
        winner_map = {
            "TMC": "tmc",
            "BJP": "bjp",
            "Left": "left",
            "Congress": "congress",
            "Others": "others",
        }
        winner = winner_map.get(row["winner"], row["winner"].lower())

        # Calculate margin
        vote_vals = [
            row["tmc_pct"],
            row["bjp_pct"],
            row["left_pct"],
            row["congress_pct"],
            row["others_pct"],
        ]
        sorted_votes = sorted(vote_vals, reverse=True)
        margin_pct = sorted_votes[0] - sorted_votes[1]

        unit = GroundTruthUnit(
            unit_id=row["constituency_code"],
            unit_name=row["constituency_name"],
            outcomes=outcomes,
            winner=winner,
            margin_pct=margin_pct,
        )
        units.append(unit)

    return GroundTruth(
        election_id="wb_2021_assembly",
        date="2021-04-27",
        granularity="constituency",
        units=units,
    )


def _load_india_2024_ls() -> GroundTruth:
    """Load India 2024 Lok Sabha election (constituency-level)."""
    csv_path = _DATA_DIR / "india_2024_ls" / "results_constituency.csv"

    if not csv_path.exists():
        raise FileNotFoundError(f"Dataset not found: {csv_path}")

    df = pd.read_csv(csv_path)

    units = []
    for _, row in df.iterrows():
        outcomes = {
            "bjp_pct": row["bjp_pct"],
            "congress_pct": row["congress_pct"],
            "regional_pct": row["regional_pct"],
            "others_pct": row["others_pct"],
        }

        # Winner from dataset
        winner_map = {
            "BJP": "bjp",
            "Congress": "congress",
            "Regional": "regional",
            "Others": "others",
        }
        winner = winner_map.get(row["winner"], row["winner"].lower())

        # Calculate margin
        vote_vals = [
            row["bjp_pct"],
            row["congress_pct"],
            row["regional_pct"],
            row["others_pct"],
        ]
        sorted_votes = sorted(vote_vals, reverse=True)
        margin_pct = sorted_votes[0] - sorted_votes[1]

        unit = GroundTruthUnit(
            unit_id=row["constituency_code"],
            unit_name=row["constituency_name"],
            outcomes=outcomes,
            winner=winner,
            margin_pct=margin_pct,
            metadata={"state": row.get("state")},
        )
        units.append(unit)

    return GroundTruth(
        election_id="india_2024_ls",
        date="2024-06-04",
        granularity="constituency",
        units=units,
    )


def _load_india_2019_ls() -> GroundTruth:
    """Load India 2019 Lok Sabha election (constituency-level)."""
    csv_path = _DATA_DIR / "india_2019_ls" / "results_constituency.csv"

    if not csv_path.exists():
        raise FileNotFoundError(f"Dataset not found: {csv_path}")

    df = pd.read_csv(csv_path)

    units = []
    for _, row in df.iterrows():
        outcomes = {
            "bjp_pct": row["bjp_pct"],
            "congress_pct": row["congress_pct"],
            "regional_pct": row["regional_pct"],
            "others_pct": row["others_pct"],
        }

        # Winner from dataset
        winner_map = {
            "BJP": "bjp",
            "Congress": "congress",
            "Regional": "regional",
            "Others": "others",
        }
        winner = winner_map.get(row["winner"], row["winner"].lower())

        # Calculate margin
        vote_vals = [
            row["bjp_pct"],
            row["congress_pct"],
            row["regional_pct"],
            row["others_pct"],
        ]
        sorted_votes = sorted(vote_vals, reverse=True)
        margin_pct = sorted_votes[0] - sorted_votes[1]

        unit = GroundTruthUnit(
            unit_id=row["constituency_code"],
            unit_name=row["constituency_name"],
            outcomes=outcomes,
            winner=winner,
            margin_pct=margin_pct,
            metadata={"state": row.get("state")},
        )
        units.append(unit)

    return GroundTruth(
        election_id="india_2019_ls",
        date="2019-05-23",
        granularity="constituency",
        units=units,
    )
