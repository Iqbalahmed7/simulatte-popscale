# BRIEF-022 — Confidence Intervals

| Field | Value |
|---|---|
| Sprint | Phase 3 |
| Owner | **Haiku** (statistical, well-specified) |
| Estimate | 0.5 day |
| Branch | `phase-3/brief-022-confidence-intervals` |
| Depends on | BRIEF-019 |

## What to build

Replace single-number predictions with calibrated probability distributions. Per `CONSTRUCT_PHASE_2.md` Phase 3E.

## Files

```
popscale/calibration/
├── confidence.py         # NEW — bootstrap CIs from ensemble runs
└── tests/test_confidence.py
```

## API

```python
def bootstrap_ci(
    ensemble_results: list[dict[str, float]],   # 3 ensemble runs' vote shares
    confidence: float = 0.90,
    n_bootstrap: int = 1000,
) -> dict[str, tuple[float, float, float]]:
    """For each party, return (point_estimate, lower_ci, upper_ci) at the given confidence."""
```

Plus:
- `format_with_ci(predictions: dict, ci: dict) -> str` — pretty print "TMC: 65.0% [62.1, 67.9]"
- Integration into BacktestResult: optional `confidence_intervals` field

## Acceptance

1. Uses numpy's percentile-based bootstrap (1000 resamples is fine; not a hot path).
2. CI bounds are reasonable: with 3 ensemble runs, CI width should reflect actual ensemble variance.
3. Integration: BacktestResult.from_ensemble(...) supports CI computation.
4. 4 tests:
   - `test_perfect_agreement_gives_zero_width_ci` — all 3 runs identical → CI is a point
   - `test_high_variance_gives_wide_ci`
   - `test_format_with_ci`
   - `test_bootstrap_default_params`

## Constraints

- Use `numpy` (already a dep). No scipy.
- No I/O in the math functions; pure.
