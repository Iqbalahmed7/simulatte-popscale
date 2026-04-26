"""
Tests for confidence interval bootstrap functions.

Covers:
1. Perfect agreement (zero-width CI)
2. High variance (wide CI)
3. Format output
4. Default parameter behavior
"""

import pytest
from popscale.calibration.confidence import bootstrap_ci, format_with_ci


class TestBootstrapCI:
    """Test suite for bootstrap_ci function."""

    def test_perfect_agreement_gives_zero_width_ci(self):
        """All 3 ensemble runs identical → CI is a point (zero width)."""
        ensemble = [
            {"A": 55.0, "B": 45.0},
            {"A": 55.0, "B": 45.0},
            {"A": 55.0, "B": 45.0},
        ]

        result = bootstrap_ci(ensemble, confidence=0.90, n_bootstrap=1000)

        # Point estimate should be exactly 55 and 45
        assert abs(result["A"][0] - 55.0) < 1e-9
        assert abs(result["B"][0] - 45.0) < 1e-9

        # CI bounds should be equal to point estimate (zero width)
        assert abs(result["A"][1] - result["A"][0]) < 1e-9
        assert abs(result["A"][2] - result["A"][0]) < 1e-9

        assert abs(result["B"][1] - result["B"][0]) < 1e-9
        assert abs(result["B"][2] - result["B"][0]) < 1e-9

    def test_high_variance_gives_wide_ci(self):
        """High variance across runs → wider CI than low-variance case."""
        # High variance run
        high_var = [
            {"A": 40.0, "B": 60.0},
            {"A": 60.0, "B": 40.0},
            {"A": 50.0, "B": 50.0},
        ]

        # Low variance run
        low_var = [
            {"A": 49.0, "B": 51.0},
            {"A": 51.0, "B": 49.0},
            {"A": 50.0, "B": 50.0},
        ]

        high_var_result = bootstrap_ci(high_var, confidence=0.90, n_bootstrap=1000)
        low_var_result = bootstrap_ci(low_var, confidence=0.90, n_bootstrap=1000)

        # High variance CI width should be larger
        high_var_width = high_var_result["A"][2] - high_var_result["A"][1]
        low_var_width = low_var_result["A"][2] - low_var_result["A"][1]

        assert high_var_width > low_var_width, (
            f"High variance width {high_var_width} should exceed "
            f"low variance width {low_var_width}"
        )

        # Point estimates should be close to 50
        assert abs(high_var_result["A"][0] - 50.0) < 1.0
        assert abs(low_var_result["A"][0] - 50.0) < 1.0

    def test_bootstrap_default_params(self):
        """bootstrap_ci works with default confidence and n_bootstrap."""
        ensemble = [
            {"Party1": 30, "Party2": 70},
            {"Party1": 35, "Party2": 65},
            {"Party1": 32, "Party2": 68},
        ]

        # Call with only required argument
        result = bootstrap_ci(ensemble)

        # Should have both parties
        assert set(result.keys()) == {"Party1", "Party2"}

        # Each party should have (point_est, lower, upper)
        for party, ci_tuple in result.items():
            assert len(ci_tuple) == 3
            point_est, lower, upper = ci_tuple
            # CI should be well-formed: lower <= point_est <= upper
            assert lower <= point_est + 1e-6, f"{party}: lower > point_est"
            assert point_est <= upper + 1e-6, f"{party}: point_est > upper"

    def test_format_with_ci(self):
        """format_with_ci produces readable output."""
        predictions = {"A": 55.0, "B": 45.0}
        ci = {
            "A": (55.0, 52.0, 58.0),
            "B": (45.0, 42.0, 48.0),
        }

        output = format_with_ci(predictions, ci)

        # Should have newline-separated entries
        lines = output.split("\n")
        assert len(lines) == 2

        # Check format: "PARTY: XX.X% [lower, upper]"
        assert "A: 55.0% [52.0, 58.0]" in output
        assert "B: 45.0% [42.0, 48.0]" in output

    def test_bootstrap_ci_validates_confidence_bounds(self):
        """bootstrap_ci rejects confidence outside (0, 1)."""
        ensemble = [{"A": 50}] * 3

        with pytest.raises(ValueError, match="confidence must be in"):
            bootstrap_ci(ensemble, confidence=0.0)

        with pytest.raises(ValueError, match="confidence must be in"):
            bootstrap_ci(ensemble, confidence=1.0)

        with pytest.raises(ValueError, match="confidence must be in"):
            bootstrap_ci(ensemble, confidence=1.5)

    def test_bootstrap_ci_rejects_empty_ensemble(self):
        """bootstrap_ci raises on empty input."""
        with pytest.raises(ValueError, match="cannot be empty"):
            bootstrap_ci([])

    def test_bootstrap_ci_rejects_inconsistent_keys(self):
        """bootstrap_ci raises if ensemble dicts have different keys."""
        ensemble = [
            {"A": 50, "B": 50},
            {"A": 50, "B": 50},
            {"A": 60},  # Missing "B"
        ]

        with pytest.raises(ValueError, match="Inconsistent party keys"):
            bootstrap_ci(ensemble)

    def test_bootstrap_ci_rejects_nan(self):
        """bootstrap_ci raises on NaN values."""
        ensemble = [
            {"A": 50, "B": 50},
            {"A": 50, "B": 50},
            {"A": float("nan"), "B": 50},  # NaN for A
        ]

        with pytest.raises(ValueError, match="NaN or inf"):
            bootstrap_ci(ensemble)

    def test_format_with_ci_rejects_empty_ci(self):
        """format_with_ci raises on empty CI dict."""
        with pytest.raises(ValueError, match="cannot be empty"):
            format_with_ci({"A": 50}, {})

    def test_format_with_ci_rejects_mismatched_keys(self):
        """format_with_ci raises if predictions and ci have different keys."""
        predictions = {"A": 50, "B": 50}
        ci = {"A": (50, 48, 52)}  # Missing "B"

        with pytest.raises(ValueError, match="matching keys"):
            format_with_ci(predictions, ci)

    def test_bootstrap_ci_ci_bounds_validity(self):
        """CI bounds are always lower <= point_estimate <= upper."""
        ensemble = [
            {"TMC": 35, "BJP": 40, "Left": 20, "Others": 5},
            {"TMC": 40, "BJP": 35, "Left": 20, "Others": 5},
            {"TMC": 38, "BJP": 37, "Left": 20, "Others": 5},
        ]

        result = bootstrap_ci(ensemble, confidence=0.90, n_bootstrap=500)

        for party, (point_est, lower, upper) in result.items():
            assert lower <= point_est + 1e-6, (
                f"{party}: lower={lower} > point_est={point_est}"
            )
            assert point_est <= upper + 1e-6, (
                f"{party}: point_est={point_est} > upper={upper}"
            )
