# BRIEF-004 — Credit Exhaustion Detector

| Field | Value |
|---|---|
| Sprint | Construct Phase 2 / Phase 0 |
| Owner | **Codex** |
| Estimate | 1 day |
| Branch | `phase-0/brief-004-credit-detector` |
| Status | 🟢 Open |
| Depends on | — |
| Blocks | nothing (parallel-safe) |

---

## Background

Run 6 of the WB 2026 manifesto sensitivity died at 23:54:31 with `BadRequestError: 400 — credit balance too low`. The retry mechanism silently looped on the 400 with no alert until the asyncio task was killed. By that point, ~$59 of useful work was lost (1 of 3 ensemble runs of presidency_suburbs that had completed but never been checkpointed).

This is a **silent failure** in violation of `PRINCIPLES.md` P3. The system must detect credit exhaustion explicitly, halt cleanly, write a checkpoint, and notify.

---

## Goal

Before every API call (or every batch of N), check the Anthropic credit balance. If balance is below a configurable buffer (default $10), halt the run, write the latest checkpoint, and emit a push notification.

No retry storms on 400 credit errors. No silent burns. No surprise crashes.

---

## Files in scope

```
simulatte-workspace/
├── persona-generator/
│   ├── src/utils/retry.py                    # api_call_with_retry — add 400-credit detection
│   ├── src/utils/credit_monitor.py           # NEW — balance polling + buffer logic
│   └── tests/test_credit_monitor.py          # NEW
└── popscale/
    └── benchmarks/wb_2026/constituency/
        └── wb_2026_constituency_benchmark.py # honor halt signal between clusters
```

Out of scope: changing the retry policy for non-credit 400s; rewriting the cognitive loop.

---

## Acceptance criteria

1. **Pre-flight check** — at the start of any benchmark run, fetch current Anthropic credit balance via the org API. If `balance_usd < BUFFER_USD` (default $10), refuse to start; print clear message; exit non-zero.

2. **In-flight monitor** — poll balance every N API calls (default N=200) on a background task. If balance crosses below `BUFFER_USD`, set a `halt_requested` flag.

3. **Halt-aware execution** — between every ensemble run (and ideally every persona batch), the benchmark checks `halt_requested`. If set: write the current partial checkpoint, log the halt reason with current balance, send push notification, exit cleanly.

4. **400 credit detection** — `api_call_with_retry` distinguishes `400 credit balance too low` from other 400s. On credit-400, it does NOT retry. It sets `halt_requested = True` and re-raises a typed `CreditExhaustedError`.

5. **Configurable** — `BUFFER_USD`, poll interval, push-notification target are all environment-variable overridable. Defaults documented in CORE_SPEC.

6. **Notification** — on halt, send a push notification (Pushover, ntfy.sh, or simple webhook — your choice; document which). Message must include: balance, run_id, last completed cluster/ensemble, checkpoint path.

7. **Tests** — `test_credit_monitor.py` covers: pre-flight rejection, mid-run trip, 400-credit detection, halt signal honored.

---

## Implementation notes

- Anthropic provides credit balance via the Admin API (`GET /v1/organizations/usage`). Confirm the exact endpoint with the SDK; if not available in `anthropic` Python SDK directly, use `httpx` against the REST endpoint.
- The credit monitor task should use a lightweight `asyncio.create_task` running in the background. Cancel cleanly on shutdown.
- For the push notification, **ntfy.sh** is recommended for zero-setup. Subscribe topic name in env var `SIMULATTE_NTFY_TOPIC`.
- Use `CreditExhaustedError(Exception)` — typed exception, never re-raised as a generic 400.
- The halt signal is process-local; it does not need to coordinate across processes.

---

## Deliverable format

PR description should include:
- Summary of approach (1 paragraph)
- New env vars and defaults (table)
- Test output showing the 4 scenarios (pre-flight reject, mid-run trip, 400-credit detection, halt-honored)
- Demo screenshot of the push notification firing in a forced-credit-low test
- Any open questions raised in the deliverable, not blocking on them

---

## Out-of-scope clarifications

- This brief does NOT cover automatic resume after credit top-up (that's BRIEF-005's territory — "resume from partial").
- This brief does NOT change the budget ceiling logic in PopScale's CLI (that's BRIEF-006's pre-flight validator).
- The dashboard surfacing of balance is BRIEF-008.

---

## Reference

- `PRINCIPLES.md` P3, P4
- `CORE_SPEC.md` §5 (failure mode contract — first row "Credit balance <$10")
- Run 6 failure log: `/tmp/manifesto_run6.log` (search for "credit balance too low")
