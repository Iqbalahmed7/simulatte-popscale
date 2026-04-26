"""
Confidence intervals from ensemble results.

Implements bootstrap-based confidence intervals for multi-party vote share
predictions derived from ensemble model runs. All inputs and outputs are
in percentage (0–100) to match the calibration module's scale convention.
"""

import numpy as np
from typing import Optional


def bootstrap_ci(
    ensemble_results: list[dict[str, float]],
    confidence: float = 0.90,
    n_bootstrap: int = 1000,
) -> dict[str, tuple[float, float, float]]:
    """
    Compute bootstrap confidence intervals for each party from ensemble runs.

    For each party, resamples the ensemble runs (with replacement) n_bootstrap
    times, computes the sample mean for each resample, then extracts percentiles
    to form the confidence interval bounds. Returns a point estimate (mean across
    ensemble runs) and lower/upper bounds at the specified confidence level.

    Args:
        ensemble_results: List of dicts, each mapping {party_id: vote_share_pct}.
            Typically 3 ensemble runs, each with the same party keys.
            All vote shares in [0, 100] percentage scale.

        confidence: Confidence level (default 0.90 for 90% CI).
            Must be in (0, 1). Bounds are at percentiles
            (1 - confidence) / 2 and 1 - (1 - confidence) / 2.

        n_bootstrap: Number of bootstrap resamples (default 1000).
            Higher values give more stable percentile estimates.

    Returns:
        Dict mapping each party_id to (point_estimate, lower_ci, upper_ci).
        - point_estimate: Mean vote share across ensemble runs, in [0, 100].
        - lower_ci, upper_ci: Percentile-based bounds, in [0, 100].

    Raises:
        ValueError: If ensemble_results is empty, has inconsistent party keys,
                    or contains NaN/inf values. Also if confidence not in (0, 1).

    Examples:
        >>> result = bootstrap_ci(
        ...     [{"A": 50, "B": 50}, {"A": 50, "B": 50}, {"A": 50, "B": 50}],
        ...     confidence=0.90
        ... )
        >>> result["A"]  # Point estimate 50, zero-width CI
        (50.0, 50.0, 50.0)

        >>> result = bootstrap_ci(
        ...     [{"A": 45, "B": 55}, {"A": 55, "B": 45}, {"A": 50, "B": 50}],
        ...     confidence=0.90
        ... )
        >>> # A has wider CI due to variance across runs
        >>> result["A"][0]  # Point estimate ~50
        50.0
    """
    if not ensemble_results:
        raise ValueError("ensemble_results cannot be empty")

    if not isinstance(confidence, (int, float)) or confidence <= 0 or confidence >= 1:
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")

    # Validate all dicts have same keys and no NaN/inf
    if not all(isinstance(d, dict) for d in ensemble_results):
        raise ValueError("All ensemble_results entries must be dicts")

    party_keys = set(ensemble_results[0].keys())
    if not party_keys:
        raise ValueError("ensemble_results dicts cannot be empty")

    for i, result_dict in enumerate(ensemble_results):
        if set(result_dict.keys()) != party_keys:
            raise ValueError(
                f"Inconsistent party keys at index {i}: "
                f"expected {party_keys}, got {set(result_dict.keys())}"
            )

        for party, value in result_dict.items():
            if not isinstance(value, (int, float)):
                raise ValueError(f"Vote share for {party} must be numeric, got {type(value)}")
            if np.isnan(value) or np.isinf(value):
                raise ValueError(f"Vote share for {party} is NaN or inf: {value}")

    # Convert to numpy array for efficient resampling
    # Shape: (n_ensemble, n_parties) — rows are runs, columns are parties
    ensemble_array = np.array(
        [
            [ensemble_results[i][party] for party in sorted(party_keys)]
            for i in range(len(ensemble_results))
        ],
        dtype=np.float64,
    )

    # Bootstrap: resample rows (with replacement) and compute column means
    rng = np.random.default_rng(seed=None)
    bootstrap_means = np.zeros((n_bootstrap, len(party_keys)))

    for b in range(n_bootstrap):
        # Resample row indices with replacement
        indices = rng.choice(len(ensemble_results), size=len(ensemble_results), replace=True)
        bootstrap_means[b] = ensemble_array[indices].mean(axis=0)

    # Compute percentiles for CI bounds
    alpha = 1 - confidence
    lower_percentile = alpha / 2 * 100  # e.g., 5 for 90% CI
    upper_percentile = (1 - alpha / 2) * 100  # e.g., 95 for 90% CI

    lower_bounds = np.percentile(bootstrap_means, lower_percentile, axis=0)
    upper_bounds = np.percentile(bootstrap_means, upper_percentile, axis=0)

    # Compute point estimate (mean across ensemble runs)
    point_estimates = ensemble_array.mean(axis=0)

    # Format output: {party_id: (point_estimate, lower_ci, upper_ci)}
    sorted_parties = sorted(party_keys)
    result = {}
    for i, party in enumerate(sorted_parties):
        result[party] = (
            float(point_estimates[i]),
            float(lower_bounds[i]),
            float(upper_bounds[i]),
        )

    return result


def format_with_ci(
    predictions: dict[str, float],
    ci: dict[str, tuple[float, float, float]],
) -> str:
    """
    Format predictions with confidence intervals as human-readable strings.

    Pairs each party's point estimate with its CI bounds in "party: XX% [lower, upper]"
    format. Useful for reports and logs.

    Args:
        predictions: Dict mapping {party_id: vote_share_pct}.
            Used for display order (iteration order in Python 3.7+).

        ci: Dict mapping {party_id: (point_estimate, lower_ci, upper_ci)}.
            point_estimate should match predictions[party_id] or be close to it.

    Returns:
        String with lines like "TMC: 50.0% [47.5, 52.3]" for each party.

    Raises:
        ValueError: If ci is empty or predictions/ci have inconsistent keys.

    Examples:
        >>> predictions = {"A": 55, "B": 45}
        >>> ci = {"A": (55.0, 52.0, 58.0), "B": (45.0, 42.0, 48.0)}
        >>> print(format_with_ci(predictions, ci))
        A: 55.0% [52.0, 58.0]
        B: 45.0% [42.0, 48.0]
    """
    if not ci:
        raise ValueError("ci dict cannot be empty")

    if set(predictions.keys()) != set(ci.keys()):
        raise ValueError(
            f"predictions and ci must have matching keys. "
            f"Got {set(predictions.keys())} vs {set(ci.keys())}"
        )

    lines = []
    for party in predictions.keys():
        point_est, lower, upper = ci[party]
        lines.append(f"{party}: {point_est:.1f}% [{lower:.1f}, {upper:.1f}]")

    return "\n".join(lines)
