# BRIEF-014 — Parallel Cluster Execution

| Field | Value |
|---|---|
| Sprint | Construct Phase 2 / Phase 1 |
| Owner | **Sonnet** (Opus executes) |
| Estimate | 2 days |
| Branch | `phase-1/brief-014-parallel-clusters` |
| Status | 🟢 Open |
| Depends on | BRIEF-005 (per-ensemble partial writes) merged ✓ |
| Blocks | Phase 1 acceptance |

---

## Why Sonnet owns this

Concurrency is subtle. Race conditions on the partial-JSON checkpoint, semaphore tuning, error propagation across `asyncio.gather`, and rate-limit interaction (BRIEF-015) all need careful design. A wrong implementation can corrupt checkpoints or deadlock. Sonnet only.

---

## Goal

Run the N clusters of a benchmark concurrently (default N up to 5) instead of serially. WB 2026 5-cluster study runtime: 12 hours → ~2.5 hours.

Within each cluster, the 3 ensemble runs can also run concurrently — additional 3× speedup *inside* each cluster.

Combined target: **8–10× wall clock improvement** (theoretical 15×, capped by Anthropic rate limits which is BRIEF-015's problem).

---

## Files in scope

```
popscale/benchmarks/wb_2026/constituency/
└── wb_2026_constituency_benchmark.py    # main loop becomes asyncio.gather

popscale/popscale/integration/
└── run_scenario.py                       # already has run_scenario_batch() with semaphore
                                          # — verify it's used or extend pattern

popscale/popscale/observability/
└── emitter.py                            # event emission must be thread-safe under
                                          # concurrent cluster runs
```

---

## Acceptance criteria

1. **Cluster-level parallelism** — replace the existing serial `for cluster in clusters` loop with:
   ```python
   sem = asyncio.Semaphore(args.cluster_concurrency or 5)
   async def _run(c):
       async with sem:
           return await run_cluster(c)
   results = await asyncio.gather(*[_run(c) for c in clusters])
   ```

2. **Within-cluster ensemble parallelism** — the 3 ensemble runs of a cluster also run concurrently:
   ```python
   ensemble_results = await asyncio.gather(*[
       run_ensemble(cluster, idx) for idx in range(3)
   ])
   ```

3. **Configurable concurrency** — new CLI flags:
   - `--cluster-concurrency N` (default 5)
   - `--ensemble-concurrency N` (default 3)
   The validator must reject combinations that exceed Anthropic's known rate limits given the cost estimate.

4. **Atomic partial writes** — BRIEF-005 already made writes atomic via temp+fsync+rename. Verify under concurrent execution: 5 clusters writing to the same partial JSON simultaneously must not corrupt it. Either:
   - Each cluster has its own partial sub-file, merged at end
   - OR a single partial JSON guarded by `asyncio.Lock`
   Pick one, document the choice.

5. **Failure isolation** — if one cluster crashes, the others continue. Use `asyncio.gather(..., return_exceptions=True)` and surface failed clusters in the report without aborting the whole run.

6. **Observability** — `events.jsonl` must remain monotonic (event timestamps strictly increasing). Use a single async writer task or `aiofiles` with locking.

7. **Performance measurement** — run the full 5-cluster WB 2026 benchmark with concurrency=5 and measure wall clock. Target: **<3 hours** (vs 12 hours serial).

8. **Cost neutrality** — concurrency does not change total cost. Verify total spend ≈ same as serial run.

9. **Phase 0 tests stay green.**

---

## Implementation notes

- The Persona Generator's `run_loop` is already `async`. Niobe's runner is also async. No blocking calls to wrap — just concurrency at the orchestration layer.
- Anthropic rate limits at Tier 4 are roughly: 4000 RPM, 800k TPM. With 5 clusters × 60 personas × ~6 calls each = 1800 calls running concurrently, peak RPM could spike. **BRIEF-015's rate governor handles this** — coordinate.
- `run_scenario_batch` in `popscale/integration/run_scenario.py` already exists with concurrency=20 default. Reuse where possible; don't duplicate.
- For the within-cluster ensemble parallelism: ensemble outputs must merge correctly into `ensemble_avg`. Since they're independent, just `asyncio.gather` and average at the end. No tricky state.

---

## Concurrent partial-write design

**Recommendation: per-cluster sub-file.**

```
/tmp/wb_reruns/<run_id>.partial/
├── _manifest.json              # run_id, total clusters, last_updated
├── cluster_murshidabad.json    # written atomically by cluster's writer
├── cluster_jungle_mahal.json
└── ...
```

At the end of the run: aggregate all cluster files into the final `<run_id>.partial.json` and `<run_id>.json`.

Rationale: zero contention between clusters during execution. Aggregation happens once at the end with no concurrency.

For backward compat: `--resume-from` accepts both the legacy single-file partial AND the new directory-based partial. Auto-detect.

---

## Validation procedure

```bash
# Single cluster sanity
python3 -m benchmarks.wb_2026.constituency.wb_2026_constituency_benchmark \
  --manifesto both --cluster murshidabad --budget-ceiling 50 \
  --sensitivity-baseline <ABSOLUTE> --ensemble-concurrency 3
# expected: ~6 min wall clock (vs ~50 min serial), same final ensemble_avg

# Full 5-cluster
python3 -m benchmarks.wb_2026.constituency.wb_2026_constituency_benchmark \
  --manifesto both --budget-ceiling 200 \
  --sensitivity-baseline <ABSOLUTE> \
  --cluster-concurrency 5 --ensemble-concurrency 3
# expected: <3 hr wall clock, total cost ≈ same as serial (~$80–100 post BRIEF-011/012)
```

---

## Out-of-scope

- Multi-machine distribution (Phase 4)
- Cluster work-stealing across machines (Phase 4)
- Adaptive concurrency (auto-tune based on rate-limit headroom) — that's BRIEF-015's territory

---

## Reference

- `CORE_SPEC.md` §3.2 (latency targets)
- `PRINCIPLES.md` P7 (speed serves iteration, not impatience — explains why we want this)
- BRIEF-005 (per-ensemble partial writes — required for safe concurrent checkpointing)
- BRIEF-015 (rate governor — coordinates with this)
