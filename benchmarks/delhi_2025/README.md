# Delhi Assembly Election 2025 — PopScale Benchmark

## What this measures

Whether PopScale's synthetic population can predict a real electoral outcome
more accurately than pre-election polling averages.

## Ground truth

| Party    | Actual vote share | Pre-election polls |
|----------|:-----------------:|:-----------------:|
| BJP      | **47.5%**         | ~38%              |
| AAP      | 29.0%             | ~38%              |
| Congress | 6.3%              | ~8%               |
| Others   | 17.2%             | ~16%              |

Polls almost universally predicted a close BJP–AAP race or AAP advantage.
BJP won decisively by 18 percentage points. Poll MAE ≈ 9.8pp.

## Pass criteria

1. **Winner correct** — PopScale predicts BJP as plurality winner
2. **Beats polls** — PopScale MAE < 9.8pp (poll baseline)

## Running

```bash
# Dry run — no API calls, just prints config
cd PopScale
python benchmarks/delhi_2025/delhi_2025_benchmark.py --dry-run

# Live run — 500 personas, ~$8–12 cost
python benchmarks/delhi_2025/delhi_2025_benchmark.py

# Smaller run for iteration (faster, less accurate)
python benchmarks/delhi_2025/delhi_2025_benchmark.py --n 200

# Re-analyse existing results
python benchmarks/delhi_2025/delhi_2025_benchmark.py --results-file results/delhi_2025_<run_id>.json
```

## Study design

- **State**: Delhi (97.5% urban, 32M population)
- **Stratification**: Religion (Hindu 81.7% / Muslim 12.8% / Sikh 4.0%) × Income (low / middle / high)
- **Domain**: Political
- **Scenario context**: Pre-election facts — Kejriwal excise case, AAP incumbency, BJP national momentum, Congress solo contest
- **Options**: BJP / AAP / Congress / Other/NOTA

## Results directory

Saved to `results/delhi_2025_<run_id>.json` after each live run.
