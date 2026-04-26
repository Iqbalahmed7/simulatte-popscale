# BRIEF-020 — Bias Decomposition

| Field | Value |
|---|---|
| Sprint | Phase 3 |
| Owner | **Sonnet** |
| Estimate | 1 day |
| Branch | `phase-3/brief-020-bias-decomposition` |
| Depends on | BRIEFs 018, 019 |

## Why Sonnet

When backcasts fail, we need to know **where** they fail — not just total MAE. This requires careful slicing: by demographic cell, by region, by issue salience, by confidence band. Sonnet picks the right cuts; mechanical decomposition would miss the questions that matter.

## Goal

`decompose_bias(backtest_result, persona_data) → BiasReport` — surfaces demographic / regional / category-level errors so we know which calibration knobs to turn.

## API

```python
@dataclass
class BiasReport:
    overall_mae: float
    by_demographic: dict[str, dict[str, float]]   # {axis: {cell: mae}}, e.g. {"religion": {"hindu": 1.2, "muslim": 4.5}}
    by_region: dict[str, float]                    # {cluster_id: mae}
    by_confidence_band: dict[str, float]           # {"high_conf": 1.1, "low_conf": 4.8}
    largest_errors: list[tuple[str, float]]        # top-10 unit-level errors
    recommendations: list[str]                     # human-readable next-step suggestions

def decompose_bias(
    backtest: BacktestResult,
    persona_data_path: Path,    # where the personas + their demographics are
) -> BiasReport: ...
```

## Acceptance

1. Operates on the existing WB 2026 run output as a smoke test (decomposition over 5 clusters, even if errors are uninformative against 2021 GT).
2. Produces a Markdown rendering: `BiasReport.to_markdown()` — tables + recommendations.
3. `recommendations` field includes generated text like:
   - "Muslim demographic shows 4.5pp MAE vs Hindu 1.2pp — investigate Murshidabad CAA priors"
   - "Low-confidence predictions (<60%) average 4.8pp MAE — consider flagging these for re-run"
4. 4 tests covering each decomposition axis.

## Constraints

- Stays a pure analysis function. No engine re-runs.
- Uses BRIEF-019 metrics under the hood for each slice.

## Out of scope

- Auto-fixing the bias (that's BRIEF-021's calibration loop)
- Visualization beyond markdown tables (Phase 4)
