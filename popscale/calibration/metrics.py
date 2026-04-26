"""
Calibration metrics for election prediction accuracy.

Implements pure-function metrics for comparing predicted vs. actual election outcomes
across vote share, seats, and directional accuracy dimensions. All metrics are
dimensionless or expressed as percentages.
"""

import math
from typing import Optional


def brier_score(predicted: dict[str, float], actual: dict[str, float]) -> float:
    """
    Multi-class Brier score: mean squared error over (pred_pct, actual_pct) pairs.

    The Brier score measures the mean squared difference between predicted and actual
    vote shares across all parties. Perfect predictions yield 0.0; maximum error (e.g.,
    all parties swapped) yields ~1.0 or higher.

    Args:
        predicted: Dict of {party_id: vote_share_pct} where shares sum to ~100.
        actual: Dict of {party_id: vote_share_pct} with same keys, sums to ~100.

    Returns:
        Float, mean squared error in percentage points squared.
        Typically in range [0, 1] for well-behaved inputs.

    Raises:
        ValueError: If keys don't match, any value is NaN, or lists are empty.

    Examples:
        >>> brier_score({"A": 50, "B": 50}, {"A": 50, "B": 50})
        0.0
        >>> brier_score({"A": 60, "B": 40}, {"A": 50, "B": 50})
        0.02  # (10^2 + 10^2) / 2 / 100
    """
    _validate_vote_dicts(predicted, actual)

    # Normalize to 0-1 scale for computation
    pred_norm = {k: v / 100.0 for k, v in predicted.items()}
    actual_norm = {k: v / 100.0 for k, v in actual.items()}

    squared_diffs = sum((pred_norm[k] - actual_norm[k]) ** 2 for k in pred_norm)
    return squared_diffs / len(pred_norm)


def mae_vote_share(predicted: dict[str, float], actual: dict[str, float]) -> float:
    """
    Mean absolute error in vote share across parties.

    Measures the average absolute deviation (in percentage points) of predicted
    vote share from actual vote share, aggregated across all parties.

    Args:
        predicted: Dict of {party_id: vote_share_pct}.
        actual: Dict of {party_id: vote_share_pct} with same keys.

    Returns:
        Float, mean absolute error in percentage points.

    Raises:
        ValueError: If keys don't match, any value is NaN, or lists are empty.

    Examples:
        >>> mae_vote_share({"A": 50, "B": 50}, {"A": 50, "B": 50})
        0.0
        >>> mae_vote_share({"A": 55, "B": 45}, {"A": 50, "B": 50})
        5.0
    """
    _validate_vote_dicts(predicted, actual)

    abs_diffs = sum(abs(predicted[k] - actual[k]) for k in predicted)
    return abs_diffs / len(predicted)


def seat_error_pct(
    predicted_seats: dict[str, int], actual_seats: dict[str, int]
) -> float:
    """
    Seat error as a percentage of total seats.

    Computes the sum of absolute seat count errors, divided by the total number of
    seats, expressed as a percentage.

    Args:
        predicted_seats: Dict of {party_id: seat_count}.
        actual_seats: Dict of {party_id: seat_count} with same keys.

    Returns:
        Float, percentage of total seats that differ.
        Range: [0, 100] for typical cases.

    Raises:
        ValueError: If keys don't match, any value is NaN, total seats is 0,
                    or if counts are not integers.

    Examples:
        >>> seat_error_pct({"A": 200, "B": 100}, {"A": 200, "B": 100})
        0.0
        >>> seat_error_pct({"A": 210, "B": 90}, {"A": 200, "B": 100})
        20.0  # (10 + 10) / 300 * 100
    """
    _validate_seat_dicts(predicted_seats, actual_seats)

    total_seats = sum(actual_seats.values())
    if total_seats == 0:
        raise ValueError("Total seats must be > 0")

    absolute_error = sum(
        abs(predicted_seats[k] - actual_seats[k]) for k in predicted_seats
    )
    return (absolute_error / total_seats) * 100.0


def directional_accuracy(
    predictions: list[tuple[dict[str, float], dict[str, float]]]
) -> float:
    """
    Fraction of units where argmax(predicted) == argmax(actual).

    Measures how often the predicted winner (highest vote share) matches the actual
    winner, regardless of margin. Useful for tracking directional forecasting skill.

    Args:
        predictions: List of (predicted_votes, actual_votes) tuples, where each
                     votes dict is {party_id: vote_share_pct}.

    Returns:
        Float in [0, 1], the fraction of units where predicted and actual winners match.

    Raises:
        ValueError: If list is empty, any dict is empty, or contains NaN values.

    Examples:
        >>> directional_accuracy([
        ...     ({"A": 55, "B": 45}, {"A": 52, "B": 48}),
        ...     ({"A": 40, "B": 60}, {"A": 50, "B": 50}),
        ... ])
        0.5  # First correct, second wrong
    """
    if not predictions:
        raise ValueError("predictions list cannot be empty")

    correct = 0
    for pred, actual in predictions:
        if not pred or not actual:
            raise ValueError("Vote dicts cannot be empty")

        # Validate for NaN in both dicts
        _validate_for_nan(pred)
        _validate_for_nan(actual)

        pred_winner = max(pred, key=pred.get)
        actual_winner = max(actual, key=actual.get)

        if pred_winner == actual_winner:
            correct += 1

    return correct / len(predictions)


def coverage(predicted_units: set[str], gt_units: set[str]) -> float:
    """
    Fraction of ground truth units covered by predictions.

    Measures what percentage of the ground truth units (e.g., counties, constituencies)
    have corresponding predictions. Useful for tracking backcast completeness.

    Args:
        predicted_units: Set of unit_ids in predictions.
        gt_units: Set of unit_ids in ground truth.

    Returns:
        Float in [0, 100], percentage of ground truth units covered.

    Raises:
        ValueError: If gt_units is empty.

    Examples:
        >>> coverage({"A", "B", "C"}, {"A", "B", "C"})
        100.0
        >>> coverage({"A", "B"}, {"A", "B", "C"})
        66.666...
    """
    if not gt_units:
        raise ValueError("gt_units cannot be empty")

    intersection = predicted_units & gt_units
    return (len(intersection) / len(gt_units)) * 100.0


def summary(backtest_result: dict) -> dict:
    """
    Compute all calibration metrics and check against targets.

    Aggregates Brier, MAE, seat error, directional accuracy, and coverage
    from a backtest result dictionary. Returns a summary dict with all metrics
    and a boolean flag indicating whether targets are met.

    Target thresholds (from CORE_SPEC.md §3.B):
    - Brier <0.15
    - MAE vote share <3 percentage points
    - Seat error <8% of total
    - Directional accuracy >90%
    - Coverage 100% (or missing units flagged)

    Args:
        backtest_result: Dict with keys:
            - "units": list of dicts with "predicted_outcomes", "actual_outcomes",
                       "predicted_seats", "actual_seats", "unit_id"
            - "granularity": str (e.g., "county", "constituency")

    Returns:
        Dict with keys:
            - "brier": float
            - "mae_pp": float (mean absolute error in percentage points)
            - "seat_error_pct": float
            - "directional_accuracy": float in [0, 1]
            - "coverage_pct": float in [0, 100]
            - "passes_target": bool, True if all targets met

    Raises:
        ValueError: If backtest_result malformed or missing required fields.

    Examples:
        >>> result = {
        ...     "units": [
        ...         {
        ...             "unit_id": "001",
        ...             "predicted_outcomes": {"A": 55, "B": 45},
        ...             "actual_outcomes": {"A": 50, "B": 50},
        ...             "predicted_seats": {"A": 200, "B": 100},
        ...             "actual_seats": {"A": 200, "B": 100},
        ...         }
        ...     ]
        ... }
        >>> summary(result)
        {
            "brier": 0.005,
            "mae_pp": 5.0,
            "seat_error_pct": 0.0,
            "directional_accuracy": 1.0,
            "coverage_pct": 100.0,
            "passes_target": True,
        }
    """
    if not isinstance(backtest_result, dict):
        raise ValueError("backtest_result must be a dict")

    if "units" not in backtest_result:
        raise ValueError("backtest_result must contain 'units' key")

    units = backtest_result["units"]
    if not units:
        raise ValueError("units list cannot be empty")

    # Aggregate metrics across all units
    brier_scores = []
    mae_scores = []
    predictions_for_directional = []
    predicted_unit_ids = set()
    actual_unit_ids = set()
    all_predicted_seats = {}
    all_actual_seats = {}

    for unit in units:
        # Validate unit structure
        required_keys = [
            "unit_id",
            "predicted_outcomes",
            "actual_outcomes",
            "predicted_seats",
            "actual_seats",
        ]
        for key in required_keys:
            if key not in unit:
                raise ValueError(f"Unit missing required key: {key}")

        unit_id = unit["unit_id"]
        pred_outcomes = unit["predicted_outcomes"]
        actual_outcomes = unit["actual_outcomes"]
        pred_seats = unit["predicted_seats"]
        actual_seats = unit["actual_seats"]

        # Accumulate for directional accuracy
        predictions_for_directional.append((pred_outcomes, actual_outcomes))

        # Accumulate unit ids
        predicted_unit_ids.add(unit_id)
        actual_unit_ids.add(unit_id)

        # Compute metric for this unit
        try:
            brier_scores.append(brier_score(pred_outcomes, actual_outcomes))
            mae_scores.append(mae_vote_share(pred_outcomes, actual_outcomes))

            # Aggregate seats (sum across units)
            for party, seats in pred_seats.items():
                all_predicted_seats[party] = all_predicted_seats.get(party, 0) + seats
            for party, seats in actual_seats.items():
                all_actual_seats[party] = all_actual_seats.get(party, 0) + seats
        except ValueError as e:
            raise ValueError(f"Error processing unit {unit_id}: {e}")

    # Compute aggregate metrics
    mean_brier = sum(brier_scores) / len(brier_scores) if brier_scores else 0.0
    mean_mae = sum(mae_scores) / len(mae_scores) if mae_scores else 0.0

    try:
        seat_err = (
            seat_error_pct(all_predicted_seats, all_actual_seats)
            if all_predicted_seats
            else 0.0
        )
    except ValueError as e:
        raise ValueError(f"Error computing seat error: {e}")

    try:
        directional = directional_accuracy(predictions_for_directional)
    except ValueError as e:
        raise ValueError(f"Error computing directional accuracy: {e}")

    try:
        cov = coverage(predicted_unit_ids, actual_unit_ids)
    except ValueError as e:
        raise ValueError(f"Error computing coverage: {e}")

    # Check targets
    passes = (
        mean_brier < 0.15
        and mean_mae < 3.0
        and seat_err < 8.0
        and directional > 0.90
        and cov >= 100.0 - 1e-6  # Allow tiny floating point tolerance
    )

    return {
        "brier": mean_brier,
        "mae_pp": mean_mae,
        "seat_error_pct": seat_err,
        "directional_accuracy": directional,
        "coverage_pct": cov,
        "passes_target": passes,
    }


# ============================================================================
# Validation Helpers
# ============================================================================


def _validate_vote_dicts(predicted: dict, actual: dict) -> None:
    """Validate that vote dicts have matching keys and no NaN values."""
    if not isinstance(predicted, dict) or not isinstance(actual, dict):
        raise ValueError("predicted and actual must be dicts")

    if not predicted or not actual:
        raise ValueError("Vote dicts cannot be empty")

    if set(predicted.keys()) != set(actual.keys()):
        raise ValueError(
            f"predicted and actual keys must match. "
            f"Got {set(predicted.keys())} vs {set(actual.keys())}"
        )

    _validate_for_nan(predicted)
    _validate_for_nan(actual)


def _validate_seat_dicts(predicted: dict, actual: dict) -> None:
    """Validate that seat dicts have matching keys and no NaN values."""
    if not isinstance(predicted, dict) or not isinstance(actual, dict):
        raise ValueError("predicted and actual must be dicts")

    if not predicted or not actual:
        raise ValueError("Seat dicts cannot be empty")

    if set(predicted.keys()) != set(actual.keys()):
        raise ValueError(
            f"predicted and actual keys must match. "
            f"Got {set(predicted.keys())} vs {set(actual.keys())}"
        )

    # Check all values are integers
    for party, seats in predicted.items():
        if not isinstance(seats, int):
            raise ValueError(f"predicted seats must be integers, got {type(seats)} for {party}")

    for party, seats in actual.items():
        if not isinstance(seats, int):
            raise ValueError(f"actual seats must be integers, got {type(seats)} for {party}")

    _validate_for_nan(predicted)
    _validate_for_nan(actual)


def _validate_for_nan(values: dict) -> None:
    """Check that no values are NaN."""
    for key, val in values.items():
        try:
            # Check if value is NaN (works for floats and numeric types)
            if math.isnan(val):
                raise ValueError(f"Value for {key} is NaN")
        except (TypeError, ValueError) as e:
            # Re-raise ValueError (which is our NaN error)
            if "is NaN" in str(e):
                raise
            # Otherwise, silently pass for non-numeric types
