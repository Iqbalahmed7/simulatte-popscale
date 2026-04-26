# BRIEF-004A — Credit Detector: Graceful Degradation + Test Affordance

| Field | Value |
|---|---|
| Sprint | Construct Phase 2 / Phase 0 patch |
| Owner | **Codex** (original author of BRIEF-004) |
| Estimate | 0.5–1 day |
| Branch | `phase-0/brief-004a-credit-graceful-degrade` |
| Status | 🟢 Open · BLOCKS BRIEF-009 closure |
| Depends on | BRIEF-004 (already merged) |
| Blocks | BRIEF-009 acceptance run |

---

## Background

BRIEF-009 acceptance Test B uncovered a real failure mode in the credit monitor:

```
RuntimeError: Anthropic API key missing for credit monitor
(set ANTHROPIC_ADMIN_API_KEY or ANTHROPIC_API_KEY).
```

**Two distinct problems:**

1. **The credit-balance endpoint requires an Admin API key.** Most Simulatte deployments will only have a regular API key (`ANTHROPIC_API_KEY`). Right now the credit monitor crashes hard when balance polling can't run, killing the entire pipeline.

2. **No way to test the credit-low halt path** without real API access. Future BRIEF-009-style acceptance runs will keep getting blocked unless we add a test affordance.

This is a P3 violation in the wrong direction: the system is failing **too loud**. A missing optional capability (balance polling) shouldn't kill the run when an alternative safety mechanism (in-pipeline 400-credit error detection) is in place.

---

## Goal

Make the credit monitor **gracefully degrade** when balance polling can't work, so:
- The run still proceeds with the 400-error detection safety net
- The user gets a clear warning about what's degraded
- Future tests can simulate the credit-low path without real API access

---

## Files in scope

```
simulatte-workspace/persona-generator/
├── src/utils/credit_monitor.py           # graceful degradation + test affordance
├── src/utils/retry.py                    # ensure 400-credit detection still works when monitor degraded
└── tests/test_credit_monitor.py          # 2 new tests
```

---

## Acceptance criteria

### 1. Graceful degradation when balance polling fails

When `ANTHROPIC_ADMIN_API_KEY` AND `ANTHROPIC_API_KEY` are both missing, OR when the balance endpoint returns 401/403/404, the credit monitor must:

- ✅ Log a single clear WARNING:
  ```
  WARNING credit_monitor: balance polling unavailable
  ([reason]) — relying on 400-credit-retry detection only.
  Set ANTHROPIC_ADMIN_API_KEY for proactive balance monitoring.
  ```
- ✅ Skip preflight balance check (don't refuse to start)
- ✅ Keep the in-pipeline 400-credit detection active in `retry.py`
- ✅ Set the validator field `credit_detector_active=False` so observers know
- ❌ NOT raise `RuntimeError` mid-pipeline

The pipeline proceeds. If credits actually run out mid-run, the 400-error retry detector still catches it and halts cleanly (the existing path).

### 2. Test affordance: force credit-low halt

Add an env var `SIMULATTE_TEST_FORCE_CREDIT_LOW=true` that:
- Skips real balance polling entirely
- Treats balance as `0.0` for testing purposes
- Causes the preflight check to refuse start AND the in-flight monitor to immediately set `halt_requested = True`
- Logs a clear `INFO test_force_credit_low active — credit-low path simulated for testing`

This lets BRIEF-009 Test B verify the credit-low halt contract without needing real API access.

### 3. Distinguish failure modes in the warning

The warning must specify *why* polling failed:
- `(no API key in env)` — neither var set
- `(403 from balance endpoint — admin key required)` — regular key not authorized for admin endpoint
- `(network error: <details>)` — transient

This helps users decide what to fix.

### 4. New tests

`tests/test_credit_monitor.py` gains:

- `test_degrades_gracefully_when_no_api_key` — both env vars missing → warning logged, no exception, monitor active=False, run can proceed
- `test_degrades_gracefully_on_403_from_balance_endpoint` — mock the API call returning 403, same expectations
- `test_force_credit_low_env_triggers_halt` — `SIMULATTE_TEST_FORCE_CREDIT_LOW=true` → preflight refuses and `halt_requested` set

All 5 existing tests must continue to pass.

---

## Implementation notes

- The 400-credit detection in `retry.py` is independent of balance polling. It works by inspecting failed API responses, which doesn't require any extra auth. Confirm this path is unchanged.
- For `test_force_credit_low_env_triggers_halt`, the monitor should still emit a notification through the same ntfy path as a real credit-low event, so the notification path is also exercised.
- The warning should fire **once** at startup, not on every API call. Use a flag.

---

## Deliverable format

PR description includes:
- Summary of approach (1 paragraph)
- Sample log output for each degraded scenario (3 cases from §3)
- Test output (8 tests pass: 5 original + 3 new)
- Confirmation that 400-credit detection still works in degraded mode (manual verification log)

---

## Out-of-scope

- Refactoring the credit monitor's polling cadence (Phase 4)
- Adding telemetry for "how often does graceful degradation happen in practice" (Phase 4)
- Switching to a different balance-polling endpoint that doesn't require admin (Anthropic doesn't offer one — confirmed)

---

## After this lands

1. Merge to `main` in persona-generator
2. Cursor reruns BRIEF-009 with:
   - `--budget-ceiling 100` (high enough to clear validator)
   - `SIMULATTE_TEST_FORCE_CREDIT_LOW=true` for Test B
3. Tests B/C/D should now complete
4. Phase 0 closes

---

## Reference

- BRIEF-004 (the original implementation)
- `PHASE_0_ACCEPTANCE_REPORT.md` Test B failure
- `PRINCIPLES.md` P3 (fail loud OR recover silent — *don't fail fragile*)
- `CORE_SPEC.md` §5 (failure mode contract — credit balance row)
