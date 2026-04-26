"""
Tests for calibration metrics.

Covers all metric functions with perfect predictions, worst-case errors, and
representative use cases.
"""

import pytest
from popscale.calibration.metrics import (
    brier_score,
    mae_vote_share,
    seat_error_pct,
    directional_accuracy,
    coverage,
    summary,
)


class TestBrierScore:
    """Test brier_score() implementation."""

    def test_brier_perfect_prediction(self):
        """Perfect prediction should yield 0.0."""
        predicted = {"A": 50.0, "B": 50.0}
        actual = {"A": 50.0, "B": 50.0}
        assert brier_score(predicted, actual) == 0.0

    def test_brier_max_error(self):
        """Maximum error case: all mass on wrong party."""
        predicted = {"A": 100.0, "B": 0.0}
        actual = {"A": 0.0, "B": 100.0}
        # (1.0 - 0.0)^2 + (0.0 - 1.0)^2 = 1 + 1 = 2
        # mean = 2 / 2 = 1.0
        assert brier_score(predicted, actual) == 1.0

    def test_brier_moderate_error(self):
        """Moderate error: 10pp off on each party."""
        predicted = {"A": 60.0, "B": 40.0}
        actual = {"A": 50.0, "B": 50.0}
        # (0.6 - 0.5)^2 + (0.4 - 0.5)^2 = 0.01 + 0.01 = 0.02
        # mean = 0.02 / 2 = 0.01
        assert abs(brier_score(predicted, actual) - 0.01) < 1e-9

    def test_brier_multiparty(self):
        """Three-party case."""
        predicted = {"A": 40.0, "B": 40.0, "C": 20.0}
        actual = {"A": 45.0, "B": 35.0, "C": 20.0}
        # (0.4 - 0.45)^2 + (0.4 - 0.35)^2 + (0.2 - 0.2)^2
        # = 0.0025 + 0.0025 + 0
        # = 0.005 / 3 = 0.001666...
        result = brier_score(predicted, actual)
        assert abs(result - 0.005 / 3) < 1e-9

    def test_brier_key_mismatch(self):
        """Should raise ValueError if keys don't match."""
        predicted = {"A": 50.0, "B": 50.0}
        actual = {"A": 50.0, "C": 50.0}
        with pytest.raises(ValueError, match="keys must match"):
            brier_score(predicted, actual)

    def test_brier_empty_dict(self):
        """Should raise ValueError for empty dicts."""
        with pytest.raises(ValueError, match="cannot be empty"):
            brier_score({}, {})

    def test_brier_nan_value(self):
        """Should raise ValueError for NaN values."""
        predicted = {"A": float("nan"), "B": 50.0}
        actual = {"A": 50.0, "B": 50.0}
        with pytest.raises(ValueError, match="NaN"):
            brier_score(predicted, actual)


class TestMAEVoteShare:
    """Test mae_vote_share() implementation."""

    def test_mae_perfect_prediction(self):
        """Perfect prediction should yield 0.0."""
        predicted = {"A": 50.0, "B": 50.0}
        actual = {"A": 50.0, "B": 50.0}
        assert mae_vote_share(predicted, actual) == 0.0

    def test_mae_simple_case(self):
        """Simple two-party case with known error."""
        predicted = {"A": 55.0, "B": 45.0}
        actual = {"A": 50.0, "B": 50.0}
        # |55-50| + |45-50| = 5 + 5 = 10
        # mean = 10 / 2 = 5.0
        assert mae_vote_share(predicted, actual) == 5.0

    def test_mae_asymmetric_error(self):
        """Different errors for different parties."""
        predicted = {"A": 60.0, "B": 40.0}
        actual = {"A": 50.0, "B": 50.0}
        # |60-50| + |40-50| = 10 + 10 = 20
        # mean = 20 / 2 = 10.0
        assert mae_vote_share(predicted, actual) == 10.0

    def test_mae_multiparty(self):
        """Three-party case."""
        predicted = {"A": 40.0, "B": 40.0, "C": 20.0}
        actual = {"A": 45.0, "B": 35.0, "C": 20.0}
        # |40-45| + |40-35| + |20-20| = 5 + 5 + 0 = 10
        # mean = 10 / 3 = 3.333...
        result = mae_vote_share(predicted, actual)
        assert abs(result - 10.0 / 3) < 1e-9

    def test_mae_key_mismatch(self):
        """Should raise ValueError if keys don't match."""
        predicted = {"A": 50.0, "B": 50.0}
        actual = {"A": 50.0, "C": 50.0}
        with pytest.raises(ValueError, match="keys must match"):
            mae_vote_share(predicted, actual)

    def test_mae_empty_dict(self):
        """Should raise ValueError for empty dicts."""
        with pytest.raises(ValueError, match="cannot be empty"):
            mae_vote_share({}, {})


class TestSeatError:
    """Test seat_error_pct() implementation."""

    def test_seat_error_perfect_prediction(self):
        """Perfect seat prediction should yield 0.0%."""
        predicted = {"A": 200, "B": 100}
        actual = {"A": 200, "B": 100}
        assert seat_error_pct(predicted, actual) == 0.0

    def test_seat_error_basic(self):
        """Basic case: 10 seats off on each party."""
        predicted = {"A": 210, "B": 90}
        actual = {"A": 200, "B": 100}
        # |210-200| + |90-100| = 10 + 10 = 20
        # total = 300
        # error_pct = 20 / 300 * 100 = 6.666...
        result = seat_error_pct(predicted, actual)
        assert abs(result - 20.0 / 3) < 1e-9

    def test_seat_error_maximum(self):
        """Maximum error: all seats flipped."""
        predicted = {"A": 0, "B": 300}
        actual = {"A": 300, "B": 0}
        # |0-300| + |300-0| = 300 + 300 = 600
        # error_pct = 600 / 300 * 100 = 200%
        assert seat_error_pct(predicted, actual) == 200.0

    def test_seat_error_zero_total(self):
        """Should raise ValueError if total seats is 0."""
        predicted = {"A": 0, "B": 0}
        actual = {"A": 0, "B": 0}
        with pytest.raises(ValueError, match="Total seats must be > 0"):
            seat_error_pct(predicted, actual)

    def test_seat_error_non_integer(self):
        """Should raise ValueError for non-integer seat counts."""
        predicted = {"A": 200.5, "B": 100}
        actual = {"A": 200, "B": 100}
        with pytest.raises(ValueError, match="integers"):
            seat_error_pct(predicted, actual)

    def test_seat_error_key_mismatch(self):
        """Should raise ValueError if keys don't match."""
        predicted = {"A": 200, "B": 100}
        actual = {"A": 200, "C": 100}
        with pytest.raises(ValueError, match="keys must match"):
            seat_error_pct(predicted, actual)

    def test_seat_error_empty_dict(self):
        """Should raise ValueError for empty dicts."""
        with pytest.raises(ValueError, match="cannot be empty"):
            seat_error_pct({}, {})


class TestDirectionalAccuracy:
    """Test directional_accuracy() implementation."""

    def test_directional_accuracy_all_correct(self):
        """All units predict correct winner should yield 1.0."""
        predictions = [
            ({"A": 55, "B": 45}, {"A": 52, "B": 48}),
            ({"A": 40, "B": 60}, {"A": 45, "B": 55}),
            ({"A": 70, "B": 30}, {"A": 65, "B": 35}),
        ]
        assert directional_accuracy(predictions) == 1.0

    def test_directional_accuracy_all_wrong(self):
        """All units predict wrong winner should yield 0.0."""
        predictions = [
            ({"A": 55, "B": 45}, {"A": 45, "B": 55}),
            ({"A": 40, "B": 60}, {"A": 60, "B": 40}),
        ]
        assert directional_accuracy(predictions) == 0.0

    def test_directional_accuracy_mixed(self):
        """Mix of correct and incorrect should yield 0.5."""
        predictions = [
            ({"A": 55, "B": 45}, {"A": 52, "B": 48}),  # Correct
            ({"A": 40, "B": 60}, {"A": 50, "B": 50}),  # Wrong
        ]
        assert directional_accuracy(predictions) == 0.5

    def test_directional_accuracy_multiparty(self):
        """Multi-party case: pick argmax correctly."""
        predictions = [
            ({"A": 40, "B": 50, "C": 10}, {"A": 35, "B": 55, "C": 10}),  # B wins both
            ({"A": 40, "B": 30, "C": 30}, {"A": 50, "B": 25, "C": 25}),  # A wins both
        ]
        assert directional_accuracy(predictions) == 1.0

    def test_directional_accuracy_empty_list(self):
        """Should raise ValueError for empty list."""
        with pytest.raises(ValueError, match="cannot be empty"):
            directional_accuracy([])

    def test_directional_accuracy_empty_dict(self):
        """Should raise ValueError for empty vote dicts."""
        predictions = [({"A": 50}, {})]
        with pytest.raises(ValueError, match="cannot be empty"):
            directional_accuracy(predictions)

    def test_directional_accuracy_nan_value(self):
        """Should raise ValueError for NaN values."""
        predictions = [({"A": float("nan"), "B": 50.0}, {"A": 50.0, "B": 50.0})]
        with pytest.raises(ValueError, match="NaN"):
            directional_accuracy(predictions)


class TestCoverage:
    """Test coverage() implementation."""

    def test_coverage_full(self):
        """All units covered should yield 100%."""
        predicted = {"A", "B", "C"}
        gt = {"A", "B", "C"}
        assert coverage(predicted, gt) == 100.0

    def test_coverage_partial(self):
        """Two of three units covered should yield 66.67%."""
        predicted = {"A", "B"}
        gt = {"A", "B", "C"}
        result = coverage(predicted, gt)
        assert abs(result - 66.66666666666666) < 1e-9

    def test_coverage_zero(self):
        """No units covered should yield 0%."""
        predicted = {"X", "Y"}
        gt = {"A", "B", "C"}
        assert coverage(predicted, gt) == 0.0

    def test_coverage_superset(self):
        """Extra predictions don't affect coverage."""
        predicted = {"A", "B", "C", "D", "E"}
        gt = {"A", "B", "C"}
        assert coverage(predicted, gt) == 100.0

    def test_coverage_empty_gt(self):
        """Should raise ValueError for empty ground truth."""
        predicted = {"A", "B"}
        gt = set()
        with pytest.raises(ValueError, match="cannot be empty"):
            coverage(predicted, gt)


class TestSummary:
    """Test summary() function."""

    def test_summary_passes_when_under_targets(self):
        """All metrics under targets should have passes_target=True."""
        backtest_result = {
            "units": [
                {
                    "unit_id": "001",
                    "predicted_outcomes": {"A": 51, "B": 49},
                    "actual_outcomes": {"A": 50, "B": 50},
                    "predicted_seats": {"A": 200, "B": 100},
                    "actual_seats": {"A": 200, "B": 100},
                }
            ]
        }
        result = summary(backtest_result)

        assert result["brier"] < 0.15
        assert result["mae_pp"] < 3.0
        assert result["seat_error_pct"] < 8.0
        assert result["directional_accuracy"] > 0.90
        assert result["coverage_pct"] >= 100.0
        assert result["passes_target"] is True

    def test_summary_fails_when_over_targets(self):
        """At least one metric over target should have passes_target=False."""
        backtest_result = {
            "units": [
                {
                    "unit_id": "001",
                    "predicted_outcomes": {"A": 70, "B": 30},
                    "actual_outcomes": {"A": 50, "B": 50},
                    "predicted_seats": {"A": 250, "B": 50},
                    "actual_seats": {"A": 200, "B": 100},
                }
            ]
        }
        result = summary(backtest_result)

        # MAE should be way over target (20pp)
        assert result["mae_pp"] >= 3.0
        assert result["passes_target"] is False

    def test_summary_multiple_units(self):
        """Aggregate metrics across multiple units."""
        backtest_result = {
            "units": [
                {
                    "unit_id": "001",
                    "predicted_outcomes": {"A": 51, "B": 49},
                    "actual_outcomes": {"A": 50, "B": 50},
                    "predicted_seats": {"A": 100, "B": 50},
                    "actual_seats": {"A": 100, "B": 50},
                },
                {
                    "unit_id": "002",
                    "predicted_outcomes": {"A": 49, "B": 51},
                    "actual_outcomes": {"A": 50, "B": 50},
                    "predicted_seats": {"A": 100, "B": 50},
                    "actual_seats": {"A": 100, "B": 50},
                },
            ]
        }
        result = summary(backtest_result)

        # MAE: (|51-50| + |49-50| + |49-50| + |51-50|) / 4 / 2 = 1.0
        assert result["mae_pp"] == 1.0

        # Unit 001: predicts A wins (51 > 49), actual A wins (50 = 50, max picks A first alphabetically)
        # Unit 002: predicts B wins (51 > 49), actual A wins (50 = 50, max picks A first alphabetically)
        # Directional accuracy: 1/2 = 0.5
        assert result["directional_accuracy"] == 0.5

        # All units covered
        assert result["coverage_pct"] == 100.0

        # Seat error: (0 + 0 + 0 + 0) / 300 * 100 = 0
        assert result["seat_error_pct"] == 0.0

    def test_summary_missing_units_key(self):
        """Should raise ValueError if 'units' key missing."""
        backtest_result = {"granularity": "county"}
        with pytest.raises(ValueError, match="must contain 'units'"):
            summary(backtest_result)

    def test_summary_empty_units(self):
        """Should raise ValueError for empty units list."""
        backtest_result = {"units": []}
        with pytest.raises(ValueError, match="cannot be empty"):
            summary(backtest_result)

    def test_summary_missing_unit_field(self):
        """Should raise ValueError if unit missing required field."""
        backtest_result = {
            "units": [
                {
                    "unit_id": "001",
                    "predicted_outcomes": {"A": 51, "B": 49},
                    # Missing actual_outcomes, etc.
                }
            ]
        }
        with pytest.raises(ValueError, match="missing required key"):
            summary(backtest_result)

    def test_summary_not_a_dict(self):
        """Should raise ValueError if input is not a dict."""
        with pytest.raises(ValueError, match="must be a dict"):
            summary([])

    def test_summary_coverage_tracking(self):
        """Coverage should reflect which units are in predictions."""
        backtest_result = {
            "units": [
                {
                    "unit_id": "001",
                    "predicted_outcomes": {"A": 50, "B": 50},
                    "actual_outcomes": {"A": 50, "B": 50},
                    "predicted_seats": {"A": 100, "B": 100},
                    "actual_seats": {"A": 100, "B": 100},
                },
                {
                    "unit_id": "002",
                    "predicted_outcomes": {"A": 50, "B": 50},
                    "actual_outcomes": {"A": 50, "B": 50},
                    "predicted_seats": {"A": 100, "B": 100},
                    "actual_seats": {"A": 100, "B": 100},
                },
            ]
        }
        result = summary(backtest_result)

        # Both units present, so coverage is 100%
        assert result["coverage_pct"] == 100.0

    def test_summary_all_metrics_present(self):
        """Result dict should have all required keys."""
        backtest_result = {
            "units": [
                {
                    "unit_id": "001",
                    "predicted_outcomes": {"A": 50, "B": 50},
                    "actual_outcomes": {"A": 50, "B": 50},
                    "predicted_seats": {"A": 100, "B": 100},
                    "actual_seats": {"A": 100, "B": 100},
                }
            ]
        }
        result = summary(backtest_result)

        assert "brier" in result
        assert "mae_pp" in result
        assert "seat_error_pct" in result
        assert "directional_accuracy" in result
        assert "coverage_pct" in result
        assert "passes_target" in result

        # All numeric results
        assert isinstance(result["brier"], float)
        assert isinstance(result["mae_pp"], float)
        assert isinstance(result["seat_error_pct"], float)
        assert isinstance(result["directional_accuracy"], float)
        assert isinstance(result["coverage_pct"], float)
        assert isinstance(result["passes_target"], bool)
