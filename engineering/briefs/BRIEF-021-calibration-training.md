# BRIEF-021 — Calibration Training Loop (Approach 1: Persona Prior Recalibration)

| Field | Value |
|---|---|
| Sprint | Phase 3 |
| Owner | **Sonnet** |
| Estimate | 2 days |
| Branch | `phase-3/brief-021-calibration-training` |
| Depends on | BRIEFs 018, 019, 020 |

## Why Sonnet

The training loop is where the strategic bet plays out. Each iteration adjusts persona attribute distributions based on backcast errors and re-runs to measure improvement. Wrong design here means we either overfit to one election or fail to converge. Sonnet only.

## Goal

Implement Approach 1 from `CONSTRUCT_PHASE_2.md` Phase 3D: persona prior recalibration. Approach 2 (decision-model fine-tuning) is its own brief later.

## API

```python
async def calibrate(
    target_election_id: str,
    starting_priors_path: Path,        # current persona attribute distributions
    max_iterations: int = 5,
    target_mae_pp: float = 3.0,
    budget_usd: float = 100.0,
) -> CalibrationResult:
    """Iterative loop:
    1. Run engine with current priors → BacktestResult
    2. decompose_bias() → BiasReport
    3. Adjust priors based on largest demographic errors
    4. Repeat until target_mae_pp hit or max_iterations / budget exhausted.
    """
```

`CalibrationResult` carries: history of MAE per iteration, final priors, total cost, convergence status.

## Adjustment rule (v1, simple)

For each demographic cell with MAE > 2pp:
- If cell over-predicts party X by Δpp, **shift** that cell's prior preference for X down by `Δpp / 4` (gentle 25% step).
- Log every change to `calibration_history.jsonl` for auditability.

This is intentionally a simple gradient-descent-like rule. No ML magic. We can swap in something fancier in Phase 4.

## Acceptance

1. Runs on the WB 2021 ground truth with the existing persona priors. Show MAE trajectory over 5 iterations.
2. Smoke test: feed in ground truth as the prediction (perfect input) → calibration converges immediately, 0 iterations needed.
3. Budget guard: if total spend approaches budget_usd, halt with checkpoint.
4. Produces a `CALIBRATION_REPORT.md` artifact with iteration-by-iteration MAE + which priors changed.
5. 3 tests.

## Constraints

- Real-money runs gated by `budget_usd` parameter — never auto-spend more than approved.
- Each iteration writes a checkpoint so we can resume if interrupted.
- Uses BRIEF-014 cluster parallelism + BRIEF-016 governor for safe execution.

## Out of scope

- Decision-model fine-tuning (separate, deeper brief in Phase 4 if Approach 1 plateaus)
- Multi-election joint calibration
