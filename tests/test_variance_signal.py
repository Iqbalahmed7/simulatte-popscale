"""test_variance_signal.py — BRIEF-023 variance signal automation tests.

Tests the high-variance flagging in cluster ensemble results.
"""
import statistics
from unittest import TestCase


def compute_max_variance_pp(ensemble_runs: list[dict]) -> float:
    """Compute the maximum standard deviation across all parties in ensemble runs.

    Args:
        ensemble_runs: List of dicts with 'shares' key containing party vote shares.
                      Each shares dict maps party name to float vote share (0.0-1.0).

    Returns:
        Maximum party stddev in percentage points. Returns 0.0 if fewer than 2 runs.
    """
    if len(ensemble_runs) < 2:
        return 0.0

    parties = set()
    for run_data in ensemble_runs:
        shares = run_data.get("shares", {})
        parties.update(shares.keys())

    max_pp = 0.0
    for party in parties:
        values = []
        for run_data in ensemble_runs:
            shares = run_data.get("shares", {})
            val = shares.get(party, 0.0)
            if val is not None:
                values.append(val)

        if len(values) >= 2:
            try:
                stddev = statistics.stdev(values)
                # Convert to percentage points (0.50 vote share = 50pp)
                pp = stddev * 100.0
                max_pp = max(max_pp, pp)
            except (ValueError, TypeError):
                # stdev raises ValueError if all values identical
                pass

    return max_pp


class TestVarianceSignal(TestCase):
    """BRIEF-023 variance signal tests."""

    def test_low_variance_ensemble(self):
        """Low variance (all runs similar) should not flag."""
        # 3 runs with vote shares stable across all parties
        ensemble_runs = [
            {
                "run_index": 1,
                "shares": {"TMC": 0.50, "BJP": 0.30, "Left-Congress": 0.15, "Others": 0.05},
            },
            {
                "run_index": 2,
                "shares": {"TMC": 0.51, "BJP": 0.29, "Left-Congress": 0.15, "Others": 0.05},
            },
            {
                "run_index": 3,
                "shares": {"TMC": 0.49, "BJP": 0.31, "Left-Congress": 0.15, "Others": 0.05},
            },
        ]

        max_variance_pp = compute_max_variance_pp(ensemble_runs)

        # Stddev of [0.50, 0.51, 0.49] = ~0.01 = ~1 pp (well below 10pp threshold)
        self.assertLess(max_variance_pp, 10.0)
        # Should be false when max variance < 10pp
        high_variance_flag = max_variance_pp >= 10.0
        self.assertFalse(high_variance_flag)

    def test_high_variance_ensemble(self):
        """High variance (spread >10pp) should flag."""
        # 3 runs with wide variation in one party
        ensemble_runs = [
            {
                "run_index": 1,
                "shares": {"TMC": 0.45, "BJP": 0.35, "Left-Congress": 0.15, "Others": 0.05},
            },
            {
                "run_index": 2,
                "shares": {"TMC": 0.55, "BJP": 0.25, "Left-Congress": 0.15, "Others": 0.05},
            },
            {
                "run_index": 3,
                "shares": {"TMC": 0.50, "BJP": 0.30, "Left-Congress": 0.15, "Others": 0.05},
            },
        ]

        max_variance_pp = compute_max_variance_pp(ensemble_runs)

        # Stddev of [0.45, 0.55, 0.50] = ~0.0471 ≈ 4.71pp for TMC
        # Stddev of [0.35, 0.25, 0.30] = ~0.0471 ≈ 4.71pp for BJP
        # (This is low variance; let's use a more extreme example)

        # Actually test the high variance case:
        ensemble_runs = [
            {
                "run_index": 1,
                "shares": {"TMC": 0.30, "BJP": 0.40, "Left-Congress": 0.20, "Others": 0.10},
            },
            {
                "run_index": 2,
                "shares": {"TMC": 0.60, "BJP": 0.20, "Left-Congress": 0.15, "Others": 0.05},
            },
            {
                "run_index": 3,
                "shares": {"TMC": 0.40, "BJP": 0.35, "Left-Congress": 0.20, "Others": 0.05},
            },
        ]

        max_variance_pp = compute_max_variance_pp(ensemble_runs)

        # Stddev of [0.30, 0.60, 0.40] = ~0.1247 ≈ 12.47pp for TMC (exceeds 10pp)
        self.assertGreaterEqual(max_variance_pp, 10.0)
        # Should be true when max variance >= 10pp
        high_variance_flag = max_variance_pp >= 10.0
        self.assertTrue(high_variance_flag)

    def test_nan_edge_case(self):
        """NaN/None values should be skipped gracefully."""
        # Ensemble with None/NaN values should not crash
        ensemble_runs = [
            {
                "run_index": 1,
                "shares": {"TMC": 0.50, "BJP": None, "Left-Congress": 0.25, "Others": 0.25},
            },
            {
                "run_index": 2,
                "shares": {"TMC": 0.52, "BJP": 0.23, "Left-Congress": 0.25, "Others": None},
            },
            {
                "run_index": 3,
                "shares": {"TMC": None, "BJP": 0.24, "Left-Congress": 0.26, "Others": 0.25},
            },
        ]

        # Should not raise an exception
        max_variance_pp = compute_max_variance_pp(ensemble_runs)

        # Should return a valid number (not NaN)
        self.assertIsInstance(max_variance_pp, float)
        self.assertFalse(max_variance_pp != max_variance_pp)  # Check not NaN


if __name__ == "__main__":
    import unittest
    unittest.main()
