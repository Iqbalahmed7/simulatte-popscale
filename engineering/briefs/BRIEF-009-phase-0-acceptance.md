# BRIEF-009 — Phase 0 Acceptance Run

| Field | Value |
|---|---|
| Sprint | Construct Phase 2 / Phase 0 closer |
| Owner | **Cursor or Codex** (whoever's free) |
| Estimate | 0.5 day |
| Branch | `phase-0/brief-009-acceptance` |
| Status | 🟢 Open |
| Depends on | BRIEFs 004–008 (all merged to main) |
| Blocks | Phase 1 launch |

---

## Background

BRIEFs 004–008 are merged. Five engineering deliverables that are *supposed* to make Phase 0's safety net real. We don't yet know they actually work end-to-end on a real run.

This brief is the **forced-failure suite**. We deliberately try to break the system in three ways the WB Run 1–7 disaster patterns predicted, and verify each one fails loud + recovers clean as the spec demands.

If all three pass, Phase 0 is closed and we open Phase 1 (cost overhaul). If any fails, we don't proceed — we fix.

---

## Goal

Run three end-to-end forced-failure scenarios against the merged Phase 0 code. For each, capture:
- What was tried
- What the system did
- Whether the behavior matched `CORE_SPEC.md` §5 contracts

Deliver a single Markdown report (`engineering/construct_phase_2/PHASE_0_ACCEPTANCE_REPORT.md`) with screenshots / log excerpts as evidence.

---

## Pre-check gate (REVISED 2026-04-26)

**Original strict gate was too broad.** Full popscale + persona-generator suites have 21 + collection-error pre-existing failures in modules unrelated to Phase 0 (`test_seeded_generation.py`, `test_week5_social.py`, `test_geographies.py`, `test_week7_calibration.py`, sklearn dev dep missing). These are tracked separately in BRIEF-010 (test debt cleanup). They do **not** block Phase 0 acceptance.

**Revised pre-check gate — must be green to proceed:**

```bash
# popscale Phase 0 modules
cd "/Users/admin/Documents/Simulatte Projects/PopScale"
python3 -m pytest -q \
  popscale/config/tests/ \
  popscale/scenario/tests/ \
  popscale/observability/tests/ \
  benchmarks/wb_2026/constituency/tests/ \
  --no-header --tb=no
# Expected: 13 passed (BRIEFs 005, 006, 007, 008)

# persona-generator credit detector
cd "/Users/admin/Documents/Simulatte Projects/Persona Generator"
python3 -m pytest -q tests/test_credit_monitor.py --no-header --tb=no
# Expected: 5 passed (BRIEF-004)
```

**If those 18 tests are green, proceed to A/B/C/D regardless of unrelated suite state.** Document the 21 pre-existing failures + sklearn missing in the report's "known baseline" section, then proceed.

If any of the 18 Phase 0 tests fail, halt and report — that *would* be a regression.

---

## The three tests

### Test A — Pre-flight rejects relative path

**Setup:** Run the WB constituency benchmark with a relative `--sensitivity-baseline` flag.

```bash
cd /Users/admin/Documents/Simulatte\ Projects/simulatte-workspace/popscale
python -m benchmarks.wb_2026.constituency.wb_2026_constituency_benchmark \
  --manifesto both \
  --sensitivity-baseline results/wb_2026_constituency_20260422_034351.json \
  --budget-ceiling 25
```

**Expected behavior:**
- Pre-flight prints a clear ❌ block listing the relative-path violation
- Process exits non-zero
- Zero API calls made
- Helpful error suggests the absolute-path fix

**Pass criteria:** All four bullets above ✓.

---

### Test B — Credit-low halts cleanly with checkpoint

**Setup:** Force the credit detector to trip mid-run by setting an absurdly high buffer.

```bash
cd /Users/admin/Documents/Simulatte\ Projects/simulatte-workspace/popscale
SIMULATTE_CREDIT_BUFFER_USD=99999 \
SIMULATTE_NTFY_TOPIC=simulatte-test-acceptance \
python -m benchmarks.wb_2026.constituency.wb_2026_constituency_benchmark \
  --manifesto both \
  --sensitivity-baseline /Users/admin/Documents/Simulatte\ Projects/PopScale/benchmarks/wb_2026/constituency/results/wb_2026_constituency_20260422_034351.json \
  --budget-ceiling 25
```

**Expected behavior:**
- Pre-flight detects balance < $99,999 and refuses to start (since buffer exceeds any real balance)
- OR: if pre-flight skips on absurd values, start and trip mid-run
- ntfy topic receives a notification (subscribe to `simulatte-test-acceptance` on https://ntfy.sh to verify)
- Partial checkpoint written to disk before halt
- Process exits with `SystemExit(2)`

**Pass criteria:** Halt happens cleanly, checkpoint exists, no silent burn, notification fired.

---

### Test C — Crash mid-ensemble, resume from partial

**Setup:** Run a 1-cluster job, kill it mid-ensemble-2, then resume.

```bash
# Step 1 — start a 1-cluster job, capture PID
nohup python -m benchmarks.wb_2026.constituency.wb_2026_constituency_benchmark \
  --manifesto both \
  --clusters murshidabad \
  --sensitivity-baseline <ABSOLUTE_PATH> \
  --budget-ceiling 50 \
  > /tmp/acceptance_test_c.log 2>&1 &
echo $! > /tmp/acceptance_test_c.pid

# Step 2 — wait until log shows "ensemble run 2/3"
# (run a watch loop or grep)

# Step 3 — kill -9 the process
kill -9 $(cat /tmp/acceptance_test_c.pid)

# Step 4 — verify partial JSON shows ensemble_runs_complete: 1
cat /tmp/wb_reruns/<run_id>.partial.json | jq '.cluster_results[0]'

# Step 5 — resume
python -m benchmarks.wb_2026.constituency.wb_2026_constituency_benchmark \
  --manifesto both \
  --clusters murshidabad \
  --resume-from /tmp/wb_reruns/<run_id>.partial.json \
  --sensitivity-baseline <ABSOLUTE_PATH> \
  --budget-ceiling 50
```

**Expected behavior:**
- Step 4: partial file has `is_partial: true`, `ensemble_runs_complete: 1`, one ensemble's data persisted
- Step 5: log message `Resuming ... ensemble runs already complete: 1/3`
- Resume runs only ensembles 2 and 3 (not 1 again)
- Final result has all 3 ensembles + ensemble_avg

**Pass criteria:** Resume skips completed ensemble 1, runs 2+3 only, no duplicated work.

---

### Test D (bonus) — Dashboard shows live state

**Setup:** During Test C, open the dashboard.

```bash
python -m popscale.observability.server &
# Open http://localhost:8765/runs/<run_id>
```

**Expected behavior:**
- UI shows progress, $ spent, burn rate, API rate, error pill (empty), live log tail
- Updates within 5s of each new event

**Pass criteria:** Dashboard reflects reality without manual `tail -f`.

---

## Cost budget

This test should cost **under $30**. Tests A and B are zero-cost (rejected before any API call OR halted near-immediately). Test C runs ~1 ensemble + ~2 ensembles after resume = ~$15–25 worth of one cluster.

**Hard ceiling: $30 total.** If costs exceed this, halt and report.

---

## Deliverable

`engineering/construct_phase_2/PHASE_0_ACCEPTANCE_REPORT.md` with sections:

1. **Test A — Pre-flight rejects relative path** — pass/fail, command, output excerpt
2. **Test B — Credit-low halts cleanly** — pass/fail, command, log excerpt, screenshot of ntfy notification
3. **Test C — Resume from partial** — pass/fail, partial JSON contents (key fields), resume log excerpt
4. **Test D — Dashboard live** — pass/fail, screenshot
5. **Total cost spent**: $X
6. **Verdict** — Phase 0 closed / blocked / partial pass

If all 4 tests pass: open a PR titled "Phase 0 acceptance — closed."

---

## Out-of-scope

- Performance benchmarking (Phase 2 territory)
- Multi-cluster runs (Test C is single-cluster only — keeps cost down)
- Calibration accuracy testing (Phase 3 territory)

---

## After this

When this brief is accepted:

1. `engineering/construct_phase_2/README.md` status board updates Phase 0 → ✅ Done
2. Open Phase 1 briefs (BRIEF-010 through BRIEF-014: tier migration, prompt cache, structured outputs, etc.)
3. Coordinator triggers a real $90 1-cluster acceptance run on 2021 WB to baseline pre-Phase-1 cost numbers

---

## Reference

- `CONSTRUCT_PHASE_2.md` §Phase 0 acceptance gate
- `CORE_SPEC.md` §5 (failure mode contracts — every test maps to a row)
- `PRINCIPLES.md` P3 (this brief is the proof of P3)
