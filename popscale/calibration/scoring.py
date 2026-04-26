"""
scoring.py — Engine output <-> ground truth matching and metric calculation.

Responsibilities:
- Normalise engine vote shares (decimal 0-1) to percentage (0-100) scale
- Map engine party keys to ground-truth party keys per election schema
- Compute MAE, Brier score, directional accuracy over matched unit pairs

Party key mappings
------------------
WB elections (wb_2021_assembly):
  Engine key     | GT key
  ---------------+----------
  TMC            | tmc_pct
  BJP            | bjp_pct
  Left-Congress  | left_congress_pct  (engine combines Left + Congress into one bloc)
  Others         | others_pct

  Note: GT has separate left_pct and congress_pct; we sum them into
  left_congress_pct before comparison because the engine treats them as one
  bloc ("Left-Congress" alliance slate). This is documented here so callers
  know the GT is pre-processed before scoring.

US elections (us_2024_pres):
  Engine key     | GT key
  ---------------+----------
  trump_pct      | trump_pct    (passthrough)
  harris_pct     | harris_pct
  other_pct      | other_pct

India Lok Sabha (india_2024_ls, india_2019_ls):
  Engine key     | GT key
  ---------------+----------
  BJP            | bjp_pct
  Congress       | congress_pct
  Regional       | regional_pct
  Others         | others_pct
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Party key mappings per election schema
# ---------------------------------------------------------------------------

_WB_ENGINE_TO_GT: dict[str, str] = {
    "TMC": "tmc_pct",
    "BJP": "bjp_pct",
    "Left-Congress": "left_congress_pct",
    "Others": "others_pct",
    # sim_* keys from saved WB run JSON
    "sim_tmc": "tmc_pct",
    "sim_bjp": "bjp_pct",
    "sim_left": "left_congress_pct",
    "sim_others": "others_pct",
}

_US_ENGINE_TO_GT: dict[str, str] = {
    "trump_pct": "trump_pct",
    "harris_pct": "harris_pct",
    "other_pct": "other_pct",
    "Trump": "trump_pct",
    "Harris": "harris_pct",
    "Others": "other_pct",
}

_INDIA_LS_ENGINE_TO_GT: dict[str, str] = {
    "BJP": "bjp_pct",
    "Congress": "congress_pct",
    "Regional": "regional_pct",
    "Others": "others_pct",
}

_ELECTION_MAPS: dict[str, dict[str, str]] = {
    "wb_2021_assembly": _WB_ENGINE_TO_GT,
    "us_2024_pres": _US_ENGINE_TO_GT,
    "india_2024_ls": _INDIA_LS_ENGINE_TO_GT,
    "india_2019_ls": _INDIA_LS_ENGINE_TO_GT,
}


def get_party_map(election_id: str) -> dict[str, str]:
    """Return engine_key -> gt_key mapping for the given election."""
    if election_id not in _ELECTION_MAPS:
        raise ValueError(
            f"No party map for election_id '{election_id}'. "
            f"Registered: {list(_ELECTION_MAPS.keys())}"
        )
    return _ELECTION_MAPS[election_id]


# ---------------------------------------------------------------------------
# GT normalisation
# ---------------------------------------------------------------------------

def normalise_gt_outcomes(
    outcomes: dict[str, float],
    election_id: str,
) -> dict[str, float]:
    """Pre-process raw GT outcomes into the canonical comparison form.

    For WB elections: merges left_pct + congress_pct -> left_congress_pct.
    Returns a new dict; does not mutate the input.
    """
    if election_id == "wb_2021_assembly":
        normalised = dict(outcomes)
        left = normalised.pop("left_pct", 0.0)
        congress = normalised.pop("congress_pct", 0.0)
        normalised["left_congress_pct"] = left + congress
        return normalised

    return dict(outcomes)


# ---------------------------------------------------------------------------
# Engine output normalisation
# ---------------------------------------------------------------------------

def normalise_engine_shares(
    raw_shares: dict[str, float],
    election_id: str,
) -> dict[str, float]:
    """Convert engine vote shares to percentage scale mapped to GT keys.

    Engine shares are decimal (0-1); GT is percentage (0-100).
    Returns {gt_party_key: pct_0_to_100}.
    """
    party_map = get_party_map(election_id)
    result: dict[str, float] = {}
    for engine_key, value in raw_shares.items():
        gt_key = party_map.get(engine_key)
        if gt_key is None:
            continue
        # Detect scale: values > 1.5 are already percentages
        pct_value = value if value > 1.5 else value * 100.0
        if gt_key in result:
            result[gt_key] += pct_value
        else:
            result[gt_key] = pct_value
    return result


# ---------------------------------------------------------------------------
# Scoring metrics
# ---------------------------------------------------------------------------

def compute_mae(
    predicted: dict[str, dict[str, float]],
    ground_truth: dict[str, dict[str, float]],
) -> tuple[float, dict[str, float]]:
    """Compute overall MAE and per-unit errors.

    Both dicts: {unit_id: {party_key: pct_0_to_100}}.
    Only units present in both dicts are scored.

    Returns:
        (overall_mae_pp, {unit_id: unit_mae_pp})
    """
    per_unit: dict[str, float] = {}

    for unit_id, pred_shares in predicted.items():
        gt_shares = ground_truth.get(unit_id)
        if gt_shares is None:
            continue

        shared_parties = set(pred_shares.keys()) & set(gt_shares.keys())
        if not shared_parties:
            continue

        unit_errors = [abs(pred_shares[p] - gt_shares[p]) for p in shared_parties]
        per_unit[unit_id] = sum(unit_errors) / len(unit_errors)

    if not per_unit:
        return 0.0, {}

    overall = sum(per_unit.values()) / len(per_unit)
    return overall, per_unit


def compute_brier(
    predicted: dict[str, dict[str, float]],
    ground_truth: dict[str, dict[str, float]],
) -> float:
    """Compute mean Brier score over predicted units (lower is better).

    Brier per unit: mean of (pred_pct/100 - gt_pct/100)^2 across shared parties.
    """
    unit_scores: list[float] = []

    for unit_id, pred_shares in predicted.items():
        gt_shares = ground_truth.get(unit_id)
        if gt_shares is None:
            continue

        shared_parties = set(pred_shares.keys()) & set(gt_shares.keys())
        if not shared_parties:
            continue

        brier_terms = [
            (pred_shares[p] / 100.0 - gt_shares[p] / 100.0) ** 2
            for p in shared_parties
        ]
        unit_scores.append(sum(brier_terms) / len(brier_terms))

    if not unit_scores:
        return 0.0

    return sum(unit_scores) / len(unit_scores)


def compute_directional_accuracy(
    predicted: dict[str, dict[str, float]],
    ground_truth: dict[str, dict[str, float]],
) -> float:
    """Fraction of units where predicted winner matches GT winner (0.0-1.0)."""
    correct = 0
    total = 0

    for unit_id, pred_shares in predicted.items():
        gt_shares = ground_truth.get(unit_id)
        if gt_shares is None or not gt_shares or not pred_shares:
            continue

        pred_winner = max(pred_shares, key=pred_shares.__getitem__)
        gt_winner = max(gt_shares, key=gt_shares.__getitem__)

        if pred_winner == gt_winner:
            correct += 1
        total += 1

    if total == 0:
        return 0.0

    return correct / total
