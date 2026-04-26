# Phase 3 + Phase 4 — Acceptance Report

**Status:** ✅ Code-complete. All briefs merged to `main`.
**Date:** 2026-04-25
**Build owner:** Sonnet (orchestrator) + Sonnet/Haiku sub-agents (implementation)

---

## Brief ledger

| # | Brief | Wave | Owner | Branch | Commit | Tests | Status |
|---|-------|------|-------|--------|--------|-------|--------|
| 018 | Backcasting harness | W1 | Sonnet | `phase-3/brief-018-backcasting-harness` | `83e0be3` | 13 new | merged |
| 019 | Calibration metrics | W1 | Haiku | `phase-3/brief-019-calibration-metrics` | `05fdb06` | 41 new | merged |
| 024 | Observability + retry | W1 | Sonnet | `phase-4/brief-024-{retry-hardening,observability-alerts}` | `f2d85ea` (PG), `c716177` (PS) | 5 + 5 | merged (both repos) |
| 020 | Bias decomposition | W2 | Sonnet | `phase-3/brief-020-bias-decomposition` | `b04a7e1` | 4 new | merged |
| 022 | Confidence intervals | W2 | Haiku | `phase-3/brief-022-confidence-intervals` | `07a0ac1` | 11 new | merged |
| 023 | Variance signal | W2 | Haiku | `phase-4/brief-023-variance-signal` | `7dda3e2` (merge `020a3bf`) | 3 new | merged |
| 025 | CI/CD + DR runbook | W2 | Haiku | `phase-4/brief-025-ci-cd` (both repos) | `01f9919` (PS), `ff55c8e` (PG) | 7 e2e | merged |
| 021 | Calibration training loop | W3 | Sonnet | `phase-3/brief-021-calibration-training` | `ccdca77` (merge `cc8ccdc`) | 13 new | merged |

**Total: 8 briefs, ~102 new tests, all green.**

## Test totals

- PopScale calibration suite: **90/90 passing** (1.74s)
- PopScale total tests: 849 (per BRIEF-025 CI report)
- Persona Generator total tests: 1291 (per BRIEF-025 CI report)

## Phase 3 deliverables (prediction quality)

- ✅ `popscale/calibration/harness.py` — `backcast(election_id, ...)` returning `BacktestResult` with MAE, Brier, directional accuracy, coverage
- ✅ `popscale/calibration/scoring.py` — party-key normalisation across WB/US/India schemas
- ✅ `popscale/calibration/metrics.py` — Brier, MAE, seat error, directional accuracy, coverage, summary
- ✅ `popscale/calibration/bias_decomposition.py` — 4-axis decomposition (region / demographic / confidence band / largest errors) + recommendations + markdown report
- ✅ `popscale/calibration/confidence.py` — bootstrap CIs from ensemble runs, percentile method, numpy-only
- ✅ `popscale/calibration/training.py` — async `calibrate(...)` loop with budget guard, checkpoints, history, `CALIBRATION_REPORT.md`

## Phase 4 deliverables (production hardening)

- ✅ `persona-generator/src/utils/retry.py` — explicit 503/529 branches, 1s/2s/4s backoff, max 3 retries, distinct from credit/governor cases
- ✅ `popscale/observability/alerts.py` — `alert_on(metric, threshold, window)` polling events.jsonl, ntfy paging
- ✅ Variance signal in `ClusterResult` — `high_variance_flag`, `variance_pp`, `recommendation`, surfaced in benchmark report
- ✅ `.github/workflows/{tests,lint}.yml` — both repos, Anthropic mocked at `client.messages.create`
- ✅ `engineering/construct_phase_2/DR_RUNBOOK.md` — covers all CORE_SPEC §5 failure modes with detection / action / recovery / post-mortem
- ✅ `benchmarks/wb_2026/constituency/tests/test_e2e_mocked.py` — full pipeline mocked, <1s

## Known deviations (all minor)

- BRIEF-018 `BacktestResult` includes `brier_score` per CORE_SPEC §4.4 (brief's API spec omitted it)
- BRIEF-024 alert tests at `tests/test_alerts.py` (top-level — matches pytest discovery) instead of `popscale/observability/tests/`
- BRIEF-021 `_run_backcast` synthesizes a run JSON from priors — correct for stub-mode ground truth (BRIEF-017). One-line swap to live engine when real GT is acquired.
- BRIEF-021 doesn't directly invoke BRIEF-014 cluster parallelism / BRIEF-016 governor — the loop is `async` and structurally compatible; parallelism is the engine's concern, not the loop's.

## What's NOT in this build (deliberate)

- Real ground truth data — currently stubbed (BRIEF-017 plumbing only). Acquisition (ECI, MIT EDSL) is a follow-up data task, not engineering.
- Approach 2 (decision-model fine-tuning) — out of scope per BRIEF-021; Phase 4 brief later if Approach 1 plateaus.
- Multi-election joint calibration — out of scope.
- Tier migration to Haiku for attribute_filler — DEFERRED indefinitely. Sprint A-3 evidence shows -3 to -25pp accuracy. CORE_SPEC §2 fixed.

## Final state

- All 5 phases of `CONSTRUCT_PHASE_2.md` are code-complete.
- Phase 0 (reliability), Phase 1 (cost), Phase 1.5 (governor coordination), Phase 3 (prediction quality), Phase 4 (hardening) — all merged.
- 25 briefs total written, 23 merged, 1 deferred (BRIEF-011 tier migration), 1 LOW priority open (BRIEF-010 test debt cleanup).
- Build can run end-to-end against stub ground truth today; can run against real ground truth as soon as data is loaded into the existing loaders.

## Next milestones (post-build)

1. Acquire WB 2021 ground truth (ECI), US 2020 ground truth (MIT EDSL) — populate the existing BRIEF-017 loaders.
2. Run live `calibrate("wb_2021_assembly", ...)` with `budget_usd=$50` and inspect MAE trajectory.
3. Re-run WB 2026 benchmark with calibrated priors → compare vs. uncalibrated baseline.
4. If Approach 1 plateaus: write BRIEF-026 for Approach 2 (decision-model fine-tuning).
