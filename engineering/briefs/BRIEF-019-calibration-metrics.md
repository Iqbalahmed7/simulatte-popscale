# BRIEF-019 — Calibration Metrics

| Field | Value |
|---|---|
| Sprint | Phase 3 |
| Owner | **Haiku** (textbook math, well-specified) |
| Estimate | 0.5 day |
| Branch | `phase-3/brief-019-calibration-metrics` |
| Depends on | BRIEF-017 (schemas) |

## What to build

`popscale/calibration/metrics.py` with pure-function implementations of:

```python
def brier_score(predicted: dict[str, float], actual: dict[str, float]) -> float:
    """Multi-class Brier: mean squared error over (pred_pct, actual_pct) pairs.
    Both inputs are dicts {party: vote_share_pct} with same keys."""

def mae_vote_share(predicted: dict, actual: dict) -> float:
    """Mean absolute error in percentage points across parties."""

def seat_error_pct(predicted_seats: dict[str, int], actual_seats: dict[str, int]) -> float:
    """|predicted - actual| / total_seats × 100."""

def directional_accuracy(predictions: list[tuple[dict, dict]]) -> float:
    """Across N units, % where argmax(predicted) == argmax(actual)."""

def coverage(predicted_units: set[str], gt_units: set[str]) -> float:
    """|intersection| / |gt_units| × 100."""
```

Plus a `summary(backtest_result) -> dict` that calls each metric and returns:
```python
{
    "brier": 0.14,
    "mae_pp": 2.4,
    "seat_error_pct": 5.2,
    "directional_accuracy": 0.93,
    "coverage_pct": 100.0,
    "passes_target": True,  # vs CORE_SPEC.md §3.B targets
}
```

## Targets (from CORE_SPEC.md §3.B / CONSTRUCT_PHASE_2.md Phase 3B)

- Brier <0.15
- MAE vote share <3pp
- Seat error <8% of total
- Directional accuracy >90%
- Demographic decomposition error <5pp on any single cell (deferred — that's BRIEF-020)

## Tests

`tests/test_metrics.py`, 6 tests:
- `test_brier_perfect_prediction` → 0.0
- `test_brier_max_error` → 1.0 (or close)
- `test_mae_simple` — known case
- `test_directional_accuracy_all_correct` → 1.0
- `test_seat_error_basic`
- `test_summary_passes_when_under_targets`

## Constraints

- Pure functions, no I/O
- No new deps (math + statistics stdlib OK)
- All inputs validated (raise ValueError on shape mismatch, NaN, etc.)
