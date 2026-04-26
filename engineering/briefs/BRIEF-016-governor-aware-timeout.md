# BRIEF-016 — Governor-Aware Timeout Coordination

| Field | Value |
|---|---|
| Sprint | Construct Phase 2 / Phase 1.5 (follow-up) |
| Owner | **Sonnet** |
| Estimate | 0.5 day |
| Branch | `phase-1/brief-016-governor-timeout` |
| Status | 🟢 Open |
| Depends on | BRIEFs 014 + 015 (both merged) |
| Blocks | re-enabling default `--ensemble-concurrency > 1` |

---

## Why this exists

Phase 1 acceptance run (`PHASE_1_ACCEPTANCE_REPORT.md`) revealed: with `--ensemble-concurrency 3`, 3 ensembles × 40 personas burst into the rate governor simultaneously. `acquire()` queues calls indefinitely; `calibrated_generator`'s outer `asyncio.wait_for(timeout=600)` fires while the call is still queued. Result: spurious "skipped" sub-batches even though the underlying API calls eventually succeed.

We worked around it by setting `--ensemble-concurrency` default to 1. This brief restores the 3× speedup safely.

---

## Goal

Make `RateGovernor.acquire()` timeout-aware so the outer `wait_for` is no longer needed. The governor itself raises a clean exception when the requested budget can't be acquired in time, instead of blocking forever.

---

## Files in scope

```
persona-generator/src/utils/
├── rate_governor.py       # add wait_budget_seconds parameter to acquire()
└── retry.py               # propagate timeout from caller
tests/
└── test_rate_governor.py  # +2 tests for timeout behavior

popscale/popscale/generation/
└── calibrated_generator.py    # remove the 600s wait_for or raise it to 1800s
```

---

## API change

```python
class RateGovernor:
    async def acquire(
        self,
        estimated_tokens: int,
        wait_budget_seconds: float | None = None,  # NEW
    ) -> None:
        """Block until enough RPM/TPM budget is available.
        
        Args:
            estimated_tokens: token cost of the upcoming call.
            wait_budget_seconds: if provided, raise GovernorTimeout
                after this many seconds of queue blocking. If None,
                blocks indefinitely (existing behavior).
        
        Raises:
            GovernorTimeout: budget couldn't be acquired in time.
        """
```

`api_call_with_retry` accepts a new optional `governor_timeout` parameter that gets passed to `acquire()`.

---

## Acceptance criteria

1. **New exception class** `GovernorTimeout(RuntimeError)` distinct from `CreditExhaustedError`.

2. **`acquire(wait_budget_seconds=N)`** raises `GovernorTimeout` if more than N seconds elapse without acquiring. Otherwise behaves identically to current implementation.

3. **`calibrated_generator.py`**: remove the inner `asyncio.wait_for(..., 600)` wrapper around the API call. Instead, pass `governor_timeout=600` (configurable via env `SIMULATTE_GOVERNOR_TIMEOUT_S`) into the API call layer. When the governor times out, log it and skip the sub-batch — same behavior as the old wait_for, but now the underlying request doesn't keep running orphaned.

4. **Tests** in `test_rate_governor.py`:
   - `test_acquire_raises_timeout_when_budget_exceeded` — fill the bucket, set 1s timeout, verify `GovernorTimeout` raised
   - `test_acquire_succeeds_within_budget` — short queue, completes before timeout
   - All 10 existing tests still pass

5. **Re-enable ensemble parallelism**: change benchmark default `--ensemble-concurrency` from 1 back to 3, with a comment referencing this brief. Add to PR description: "verified by 1-cluster murshidabad smoke test."

---

## Implementation notes

- Use `asyncio.timeout()` (3.11+) or `asyncio.wait_for()` around the internal `acquire` body. Pick whichever is cleaner.
- The outer caller (`calibrated_generator`) should catch `GovernorTimeout` and treat it like the old timeout: log the skip, continue. Don't propagate as a fatal error.
- Token reconciliation (`record_response`) should NOT be called when the call timed out — there's no response to record.

---

## Validation procedure

1. Run unit tests: `pytest -q tests/test_rate_governor.py` — expect 12/12 (10 + 2 new).
2. Run a 1-cluster smoke test with `--ensemble-concurrency 3 --cluster murshidabad --budget-ceiling 30`. Expect:
   - No 600s timeouts
   - Ensemble 1, 2, 3 complete (in any order)
   - Total wall clock <20 min (vs 51 min serial baseline)
3. If anything goes wrong: revert default to 1, file findings, halt.

---

## Out of scope

- Multi-tier governor (segregating Haiku vs Sonnet bandwidth) — Phase 4
- Adaptive concurrency — Phase 4
- Dashboard widget for "current queue depth" — Phase 4

---

## Reference

- `PHASE_1_ACCEPTANCE_REPORT.md` (the failure that motivated this)
- BRIEF-014, BRIEF-015 (the two integrating systems)
- `PRINCIPLES.md` P3 (fail loud, recover silent — the governor should fail with a clear exception, not a deadlock + outer timeout)
