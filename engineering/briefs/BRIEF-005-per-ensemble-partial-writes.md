# BRIEF-005 — Per-Ensemble Partial Writes

| Field | Value |
|---|---|
| Sprint | Construct Phase 2 / Phase 0 |
| Owner | **Codex** |
| Estimate | 1 day |
| Branch | `phase-0/brief-005-per-ensemble-partial-writes` |
| Status | 🟢 Open |
| Depends on | — |
| Blocks | nothing (parallel-safe) |

---

## Background

The current `--resume-from` mechanism writes a partial JSON only after **all 3 ensemble runs of a cluster** complete. When Run 6 died mid-way through presidency_suburbs ensemble 1/3, that work was unrecoverable — Run 7 had to restart presidency_suburbs from scratch, costing another ~$50 of duplicated computation.

For a cluster that costs ~$150, losing 1/3 to a crash is a $50 waste. We can shrink that to ~$15.

---

## Goal

Reduce the maximum work-loss-on-crash from "1 cluster" to "1 ensemble run" by writing partial checkpoints after every single ensemble run completes — not waiting for all three.

`--resume-from` must be able to skip *both* fully-completed clusters AND partially-completed clusters where some-but-not-all ensemble runs are done.

---

## Files in scope

```
simulatte-workspace/popscale/
├── benchmarks/wb_2026/constituency/
│   ├── wb_2026_constituency_benchmark.py    # main loop + checkpoint logic
│   └── tests/test_resume.py                 # NEW or extended
└── popscale/integration/
    └── run_scenario.py                      # not changed; for reference
```

Out of scope: changing the underlying `ensemble_runs` data model; changing how ensemble averaging is computed.

---

## Acceptance criteria

1. **Granularity** — after every ensemble run completes (even mid-cluster), the partial JSON is updated on disk with that ensemble's results.

2. **Resume semantics** — `--resume-from <partial>` skips:
   - Clusters where all ensemble runs are complete (existing behavior)
   - **NEW:** within an in-progress cluster, the ensemble runs that are already complete; resumes from the next incomplete ensemble

3. **Atomicity** — partial writes are atomic (write to `.partial.tmp`, fsync, rename). Crash mid-write must not corrupt the partial file.

4. **Schema** — the partial JSON now records per-ensemble status:
   ```json
   {
     "run_id": "20260424_130450",
     "is_partial": true,
     "updated_at": "...",
     "cluster_results": [
       {
         "cluster_id": "presidency_suburbs",
         "is_partial": true,
         "ensemble_runs_complete": 2,
         "ensemble_runs_total": 3,
         "ensemble_runs": [ {...run1...}, {...run2...} ],
         "ensemble_avg": null   // only computed when complete
       },
       ...
     ]
   }
   ```

5. **Tests** — `test_resume.py` covers:
   - Resume from cluster-complete partial (existing behavior, regression test)
   - **NEW:** Resume from ensemble-partial — verifies that completed ensembles are skipped and remaining ones run
   - Atomicity test (simulate crash mid-write; verify file is either old or new, never corrupt)

6. **Backward compatibility** — old partial files (no per-ensemble field) still resume correctly using the old "skip whole completed clusters only" path.

---

## Implementation notes

- Atomicity in Python: write to `path + ".tmp"`, `os.fsync(fd)`, then `os.replace(tmp, final)` — `replace` is atomic on POSIX.
- The cluster loop currently does `for run_idx in range(3): result = await run_ensemble(...)`. After each result, append to `cluster.ensemble_runs` and call `_save_partial()`.
- `ensemble_avg` is computed lazily — only when all 3 runs are done. Until then it stays `null` and `is_partial: true` on the cluster.
- Don't introduce a new file format. Extend the existing JSON schema additively.
- Lock file is unnecessary if we control single-writer access; if not, use `fcntl.flock` on the partial.

---

## Deliverable format

PR description should include:
- Summary of approach (1 paragraph)
- Updated partial JSON schema example (before/after)
- Test output showing the 3 scenarios (resume cluster-complete, resume ensemble-partial, atomicity test)
- A simulated crash test: kill -9 mid-write; verify file integrity
- Cost saved analysis: "$X work-at-risk before, $Y after, for typical cluster size"

---

## Out-of-scope clarifications

- Auto-resume on crash is NOT in this brief. The user still triggers resume manually with `--resume-from`. (Auto-resume is post-Phase-0.)
- This brief does NOT change the credit detector's checkpoint-on-halt behavior — but the credit detector (BRIEF-004) calls into the same `_save_partial()` function this brief enhances.

---

## Reference

- `PRINCIPLES.md` P3, P9
- `CORE_SPEC.md` §3.3 (reliability — "Max work lost on crash: 1 ensemble (~$5–15)")
- Existing partial: `/tmp/wb_reruns/20260424_130450.partial.json`
