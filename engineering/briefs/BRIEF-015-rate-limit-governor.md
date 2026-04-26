# BRIEF-015 — Rate Limit Governor

| Field | Value |
|---|---|
| Sprint | Construct Phase 2 / Phase 1 |
| Owner | **Haiku** (Opus orchestrating, executes via Agent) |
| Estimate | 1 day |
| Branch | `phase-1/brief-015-rate-governor` |
| Status | 🟢 Open |
| Depends on | — (can run before or after BRIEF-014) |
| Blocks | Phase 1 acceptance |

---

## Why Haiku owns this

Token bucket is a textbook algorithm with well-defined behavior. The integration site is a single point: every Anthropic API call goes through `api_call_with_retry` in `persona-generator/src/utils/retry.py`. The brief specifies the exact contract; Haiku implements it. No subjective design calls needed.

---

## Goal

Prevent the parallel execution of BRIEF-014 from hitting Anthropic 429s under load. Ship a token-bucket governor that:
- Stays at 80% of known rate limits
- Backs off cleanly on 429s with exponential delay
- Tracks both RPM (requests/min) and TPM (tokens/min) windows
- Surfaces current headroom to the dashboard

---

## Files in scope

```
persona-generator/src/utils/
├── rate_governor.py            # NEW — token bucket implementation
└── retry.py                     # MODIFIED — every call goes through governor.acquire()

persona-generator/tests/
└── test_rate_governor.py        # NEW

popscale/popscale/observability/
└── emitter.py                   # emit governor_state events for dashboard
```

---

## Acceptance criteria

### 1. Token-bucket implementation

`rate_governor.py` exposes:

```python
class RateGovernor:
    def __init__(self, rpm_limit: int, tpm_limit: int, target_pct: float = 0.80):
        """target_pct: stay at 80% of declared limits as headroom."""
    
    async def acquire(self, estimated_tokens: int) -> None:
        """Block until enough budget is available. Tracks both RPM and TPM."""
    
    def record_response(self, actual_tokens: int) -> None:
        """Reconcile estimated vs actual after the call."""
    
    def state(self) -> RateGovernorState:
        """Current usage / limits — for observability."""
```

### 2. Defaults from environment

- `SIMULATTE_RPM_LIMIT` (default 4000 — Anthropic Tier 4)
- `SIMULATTE_TPM_LIMIT` (default 800000)
- `SIMULATTE_RATE_TARGET_PCT` (default 0.80)

### 3. Integration in `retry.py`

Every API call:
1. `estimated_tokens = estimate(messages, max_tokens)` — simple heuristic, doesn't need to be exact
2. `await governor.acquire(estimated_tokens)`
3. Make the API call
4. `governor.record_response(response.usage.input_tokens + response.usage.output_tokens)`

### 4. 429 handling

When a 429 is returned despite the governor:
- Read `Retry-After` header if present
- Exponential backoff: 1s, 2s, 4s, 8s (max 5 retries)
- After backoff, reduce the governor's effective `target_pct` by 10% for the next 60 seconds (adaptive)
- Log WARNING; emit `rate_limit_hit` event

### 5. Tests in `test_rate_governor.py`

- `test_acquire_blocks_when_rpm_at_target` — when 80% of RPM is used, next acquire waits
- `test_acquire_blocks_when_tpm_at_target` — same for TPM
- `test_record_response_credits_back_unused_tokens` — over-estimated tokens get credited
- `test_429_response_triggers_backoff` — when retry.py sees a 429, governor target reduces
- `test_state_reflects_current_usage` — `state()` returns sane values
- `test_concurrent_acquire_serializes` — 100 concurrent acquires complete without race

### 6. Observability

Emit `governor_state` events to `events.jsonl` every 10 seconds:
```json
{"ts":"...","type":"governor_state","rpm_used":3200,"rpm_limit":4000,"tpm_used":640000,"tpm_limit":800000,"target_pct":0.80,"throttle_active":false}
```

Dashboard surfaces a "headroom" widget showing `rpm_used / rpm_limit` and `tpm_used / tpm_limit` as bars.

### 7. Performance smoke test

Run the BRIEF-014 5-cluster concurrent benchmark with the governor active:
- Zero unexpected 429s in logs
- Total wall clock ≤ 3 hours
- `governor_state` events show headroom never exceeds 85%

---

## Implementation notes

- Use a sliding 60-second window. Implementation: a `collections.deque` of `(timestamp, tokens)` tuples; on every acquire, evict entries older than 60s, sum the rest.
- `asyncio.Semaphore` is NOT enough — we need both RPM (count-based) and TPM (token-weighted) tracking. The acquire method needs to wait on whichever is more constrained.
- Token estimation: `len(message_text) / 4` is fine as a rough heuristic. Anthropic's actual token count is reconciled in `record_response`.
- Use `time.monotonic()` for timestamps, not wall clock.

---

## Out-of-scope

- Per-model rate limits (we use both Haiku and Sonnet — single shared bucket is fine for Phase 1; segregate in Phase 4 if needed)
- Distributed governor across multiple machines (Phase 4)
- ML-driven adaptive concurrency (Phase 4)

---

## Reference

- Anthropic rate limit docs: organisation tier defaults
- BRIEF-014 (parallel execution — this brief is what makes BRIEF-014 safe)
- `CORE_SPEC.md` §3.2 (latency target — governor enables it without 429 storms)
