# BRIEF-024 — Observability Stack + Auto-Retry Hardening

| Field | Value |
|---|---|
| Sprint | Phase 4 |
| Owner | **Sonnet** |
| Estimate | 1.5 days |
| Branch | `phase-4/brief-024-observability-stack` |

## What

Per `CONSTRUCT_PHASE_2.md` Phase 4 §"Observability stack" + §"Auto-retry with exponential backoff":

1. **Structured logging**: every benchmark run emits to `runs/{run_id}/events.jsonl` (already done in BRIEF-008) AND to a JSON-line schema documented in CORE_SPEC.md §6.

2. **Alerts**: a single function `popscale.observability.alerts.alert_on(metric, threshold, window)` that pages via the existing ntfy channel when:
   - error rate > 5% in last 5 min
   - burn rate > 2× pre-flight estimate
   - p99 latency > 30s

3. **Auto-retry hardening**: `api_call_with_retry` already handles 400/429/credit. Add explicit handling for 503 (service unavailable) and 529 (overloaded) with exponential backoff. Distinct from credit/governor cases.

## Files

```
persona-generator/src/utils/retry.py            # add 503/529 cases
popscale/observability/alerts.py                # NEW
popscale/observability/tests/test_alerts.py     # NEW
```

## Acceptance

1. 503 + 529 explicit branches, exponential 1s/2s/4s backoff, max 3 retries.
2. `alert_on(...)` polls events.jsonl in a rolling window and fires ntfy when threshold crosses.
3. Tests: 5 (3 retry behaviors + 2 alert thresholds).

## Constraints

- Single file added per repo
- ntfy mechanism already exists (BRIEF-004), reuse
