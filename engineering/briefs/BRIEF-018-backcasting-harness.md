# BRIEF-018 — Backcasting Harness (Phase 3 keystone)

| Field | Value |
|---|---|
| Sprint | Construct Phase 2 / Phase 3 |
| Owner | **Sonnet** |
| Estimate | 2 days |
| Branch | `phase-3/brief-018-backcasting-harness` |
| Status | 🟢 Open |
| Depends on | BRIEF-017 (loaders, merged) |
| Blocks | 020, 021 |

## Why Sonnet

This is the strategic linchpin. It's the brief that *uses* BRIEF-017's ground truth to actually score Simulatte's predictions and produce calibration error metrics. Needs judgment about how to bridge the existing benchmark output schema to the GroundTruth schema, how to handle missing data, how to fairly compare. Mechanical execution would miss subtle semantic drift.

## Goal

Build `backcast(election_id, engine_config) → BacktestResult` — the function that turns "we ran the engine on X election" into "our MAE was Y on this calibration target."

## Files in scope

```
popscale/calibration/
├── harness.py            # NEW — backcast() entry point
├── scoring.py            # NEW — engine output ↔ ground truth matching
├── tests/test_harness.py # NEW
```

## API

```python
@dataclass
class BacktestResult:
    election_id: str
    engine_run_id: str
    ground_truth: dict[str, dict[str, float]]   # {unit: {party: pct}}
    predicted: dict[str, dict[str, float]]      # same shape
    overall_mae: float                          # mean absolute error in pp
    per_unit_errors: dict[str, float]
    directional_accuracy: float                 # % units where winner predicted right
    coverage_pct: float                          # % of ground-truth units we predicted
    metadata: dict                               # tier, run_date, cluster_count, etc.

async def backcast(
    election_id: str,
    engine_config: dict | None = None,
    use_existing_run: str | None = None,   # path to a saved run JSON; if set, skip running engine
) -> BacktestResult:
    """Run the Simulatte engine on inputs frozen at the election date,
    score against load_ground_truth(election_id).
    """
```

## Acceptance criteria

1. **`backcast("wb_2021_assembly", use_existing_run=".../wb_2026_constituency_20260426_074948.json")`** — works against the existing WB 2026 run as a sanity test (compares 2026 predictions to 2021 ground truth — semantically wrong but a plumbing check).

2. **Mismatched-cluster handling** — if engine outputs cluster-level results and ground truth is constituency-level, use `aggregate_to_clusters()` to match granularity. Document which side gets aggregated.

3. **Missing-unit graceful** — if ground truth has 294 units but engine ran 5 clusters, report `coverage_pct = 5/294` and compute MAE only over predicted units. Do not fail.

4. **Tests** in `tests/test_harness.py` (4 tests):
   - `test_backcast_with_stub_engine_output_and_stub_gt` — mock both, verify MAE calculated correctly
   - `test_backcast_handles_partial_coverage` — engine predicts 5 clusters, GT has 294 units
   - `test_backcast_directional_accuracy` — engine predicts winner X, GT has winner Y → 0%; same → 100%
   - `test_backcast_raises_on_unknown_election` — invalid election_id

5. **No new dependencies.** Use existing `popscale.calibration.loaders` + `pandas` + stdlib.

6. **All previous tests stay green:** 24 popscale + 30 PG.

## Implementation notes

- The engine's vote share output is in `cluster_results[i].ensemble_avg = {"TMC": 0.65, "BJP": 0.28, ...}` (decimal 0-1). Ground truth is in 0-100 percentage. Normalize to one scale before MAE.
- Party name mapping: engine uses "TMC" / "BJP" / "Left-Congress" / "Others"; GT may use different keys. Build a small mapping in scoring.py and document.
- For US elections: party keys are "trump_pct" / "harris_pct" — no overlap with WB. The harness needs to be schema-aware per election_id.

## Out of scope

- Running the engine for real money in the harness (use_existing_run is the primary path; live running comes in BRIEF-021)
- Confidence intervals (BRIEF-022)
- Bias decomposition (BRIEF-020)

## Reference

- `engineering/construct_phase_2/CONSTRUCT_PHASE_2.md` Phase 3A
- `popscale/calibration/loaders.py` and `enrichment.py` (BRIEF-017 outputs)
- `engineering/construct_phase_2/PRINCIPLES.md` P1 (the bet this brief tests)
