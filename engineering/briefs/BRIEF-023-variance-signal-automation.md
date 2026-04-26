# BRIEF-023 — Variance Signal Automation

| Field | Value |
|---|---|
| Sprint | Phase 4 hardening |
| Owner | **Haiku** |
| Estimate | 0.5 day |
| Branch | `phase-4/brief-023-variance-signal` |

## What

Automate the high-variance flagging from `CONSTRUCT_PHASE_2.md` Phase 4: ensemble runs with vote-share spread >10pp get a `high_variance: true` flag and a "consider rerunning" recommendation in the cluster result.

## Files

```
popscale/integration/run_scenario.py    # add variance flag to ClusterResult
benchmarks/wb_2026/constituency/wb_2026_constituency_benchmark.py    # surface in report
tests/test_variance_signal.py           # NEW
```

## API

Add to ClusterResult:
```python
high_variance_flag: bool = False
variance_pp: float = 0.0
recommendation: str = ""   # "stable" | "rerun_recommended_high_variance" etc.
```

## Acceptance

1. After ensemble averaging, compute per-party stddev across 3 runs. If max >= 10pp, set flag True.
2. Final report's per-cluster table shows variance column.
3. 3 tests: low variance, high variance, edge case (NaN handling).

## Constraints

- Math is `statistics.stdev` from stdlib.
- No new deps.
