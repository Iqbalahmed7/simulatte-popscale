# BRIEF-003 · WB 2026 Manifesto Sensitivity Re-run

**Sprint:** 1 / Task S1.4 — Sprint close  
**Assignee:** Cursor (automatic tier)  
**Timebox:** 1 working day (8h agent time). Stop at 1.5× (12h) if blocked.  
**Branch name:** `sprint1/brief-003-manifesto-sensitivity`  
**Depends on:** BRIEF-001 (cost-trace) and BRIEF-002 (guardrails) both merged into `sprint1/brief-002-guardrails`

---

## Context (read first, in order)

1. `popscale/benchmarks/wb_2026/engineering/VISION.md`
2. `popscale/benchmarks/wb_2026/engineering/ARCHITECTURE.md`
3. `popscale/benchmarks/wb_2026/engineering/SPRINT_PLAN.md` (§ Sprint 1 / S1.4)
4. `popscale/benchmarks/wb_2026/ENGINE_CAPACITY_NOTE.md`
5. `popscale/engineering/briefs/README.md`

---

## Background

On April 23, 2026, we attempted to run a manifesto sensitivity study on the WB 2026 swing clusters — testing how much each party's vote share moves when the scenario context includes explicit manifesto content. The run hit an unbounded-cost failure before producing results. We burned ~$100 and got nothing.

Sprint 1 (BRIEF-001 + BRIEF-002) added:
- Cost observability (CostTracer, `--cost-trace`)
- Bounded gate retries with `GateWaiver`
- Partial checkpoint writes so partial results are never lost
- Concurrency guardrail (`asyncio.Semaphore(20)`)
- PID-file lock (no duplicate runs)

The engine is now safe to retry the manifesto sensitivity study. **This brief adds the manifesto injection mechanism and produces a dry-run-verified implementation.** The actual $75 live run is triggered by the coordinator after the delivery is accepted.

---

## Mission

Add a `--manifesto` flag to the constituency benchmark that injects BJP and/or TMC 2026 manifesto context into the scenario, then runs the swing clusters and outputs a **sensitivity matrix** showing how vote shares shift vs. the April 22 baseline.

The sensitivity matrix is the data that closes out the WB 2026 post-election disclosure note. It must be machine-readable (JSON + CSV) and human-readable (printed table in stdout).

---

## Workspace

Your root: `/Users/admin/Documents/Simulatte Projects/simulatte-workspace/`

Three folders accessible:
- `popscale/` — benchmark layer
- `persona-generator/` — core persona synthesis
- `niobe/` — orchestration

---

## Global constraints (non-negotiable)

- **Python 3.14**, async/await throughout
- **No new Python dependencies** — stdlib only
- **No breaking changes to any public API** — add optional parameters, never remove
- **Do not modify gate-retry logic, concurrency semaphore, or PID-lock** — that's BRIEF-002's territory
- **Do not modify CostTracer** — that's BRIEF-001's territory
- **Manifesto text must be factually grounded** — use the texts provided verbatim in §Manifesto texts below. Do not paraphrase or invent.

---

## Files in scope

### Modify (existing files)

```
popscale/benchmarks/wb_2026/constituency/wb_2026_constituency_benchmark.py
popscale/benchmarks/wb_2026/constituency/cluster_definitions.py
```

### Create (new files)

```
popscale/benchmarks/wb_2026/constituency/manifesto_contexts.py
popscale/benchmarks/wb_2026/results/sensitivity/  (directory only — create .gitkeep)
```

Anything outside this list → raise a scope question in your deliverable.

---

## Detailed task list

### 1. Create `manifesto_contexts.py`

**File:** `popscale/benchmarks/wb_2026/constituency/manifesto_contexts.py`

```python
"""manifesto_contexts.py

WB 2026 party manifesto summaries for sensitivity injection.
These texts are injected appended to BASE_SCENARIO_CONTEXT
when --manifesto is set. They summarise key manifesto planks
that are electorally salient in the swing clusters.

Sources: BJP WB 2026 manifesto (released April 1, 2026),
         TMC 2026 manifesto (released March 28, 2026).
"""

TMC_MANIFESTO_CONTEXT = """\
[TMC 2026 MANIFESTO — INJECTED FOR SENSITIVITY TEST]
Trinamool Congress released its 2026 manifesto on March 28.
Key pledges voters are weighing:

WELFARE EXPANSION:
- Lakshmir Bhandar monthly stipend raised from ₹500 to ₹1,200 (SC/ST women) \
and ₹1,000 (general). Existing recipients get automatic upgrade.
- Krishak Bandhu farm support doubled to ₹10,000/year per acre, extended to \
sharecroppers and bargadars for the first time.
- Kanyashree scheme age ceiling raised from 18 to 45. Married women included.
- Swasthya Sathi health coverage extended to private hospital empanelment in \
all 23 districts; cashless for up to ₹5 lakh/year.

EMPLOYMENT:
- 5 lakh new factory jobs by 2028 under "Banglar Gorbo" industrial corridor \
(Durgapur–Haldia–Kharagpur axis).
- 2 lakh government recruitment drives within 18 months (Group C and D).
- Gig worker protection law: minimum wage guarantee for app-based workers.

GOVERNANCE / SIR:
- Commission to review and restore SIR-deleted voter names within 90 days.
- Duare Sarkar expanded to 12 new scheme categories.
- Anti-cut-money law: any TMC functionary caught extorting scheme beneficiaries \
faces expulsion + criminal case.

IDENTITY / COMMUNAL:
- NRC will NOT be implemented in West Bengal under any circumstances.
- CAA documents process: TMC will provide legal aid to Muslim families facing \
citizenship queries free of cost.
- Matua community: SIR deletions in Nadia and N24Pgs to be manually reviewed \
with Matua Mahasangha partnership.
"""

BJP_MANIFESTO_CONTEXT = """\
[BJP 2026 MANIFESTO — INJECTED FOR SENSITIVITY TEST]
BJP released its WB 2026 manifesto on April 1.
Key pledges voters are weighing:

CAA / CITIZENSHIP:
- CAA implementation within 60 days of BJP forming government. Citizenship \
certificates to be issued to all eligible Matua, Rajbanshi, and Hindu \
refugee families from Bangladesh.
- NRC: "Will be implemented in a phased, fair manner — no genuine Indian \
will be affected."
- Matua-specific: Dedicated Matua Welfare Board with ₹500 crore annual budget.

CENTRAL SCHEME DELIVERY:
- PM Awas Yojana: 10 lakh homes sanctioned but blocked by TMC government to \
be released within 100 days.
- PM Kisan ₹6,000/year extended to tenant farmers and sharecroppers (not just \
landowners).
- ₹500 LPG cylinder cap for BPL households under Ujjwala 2.0.
- One Nation One Ration Card: full portability across Bengal within 6 months.

EMPLOYMENT / ECONOMY:
- 10 lakh jobs via MSME Suraksha scheme (₹5,000 crore fund for small \
enterprise lending in Bengal).
- IT/BPO corridor in New Town Kolkata: 50,000 tech jobs target by 2027.
- Tourism circuit: Sunderbans, Shantiniketan, Bishnupur. 20,000 hospitality jobs.

GOVERNANCE:
- Anti-corruption commission independent of state government.
- SIR transparent review: national Election Commission oversight.
- "Suraksha Kavach": 24x7 women's safety taskforce in all districts.

IDENTITY:
- "Sonar Bangla" Hindu cultural renaissance program.
- Ram Mandir yatra subsidy for BPL families from Bengal.
- Durga Puja: central funding for heritage puja committees blocked by TMC.
"""

BOTH_MANIFESTO_CONTEXT = (
    TMC_MANIFESTO_CONTEXT
    + "\n\n"
    + BJP_MANIFESTO_CONTEXT
)

MANIFESTO_CONTEXTS: dict[str, str] = {
    "tmc": TMC_MANIFESTO_CONTEXT,
    "bjp": BJP_MANIFESTO_CONTEXT,
    "both": BOTH_MANIFESTO_CONTEXT,
}
```

### 2. Verify (and if needed, add) 5th swing cluster

Check `SWING_CLUSTER_IDS` in `cluster_definitions.py`. Currently it has 4:
`matua_belt`, `jungle_mahal`, `burdwan_industrial`, `presidency_suburbs`.

The SPRINT_PLAN references "5 swing clusters". Based on `swing_notes` content,
`murshidabad` is the most electorally volatile non-swing cluster (Muslim vote
fragmentation, AIMIM-AJUP coalition break, 4-way vote split). Add it to
`SWING_CLUSTER_IDS`:

```python
SWING_CLUSTER_IDS: set[str] = {
    "matua_belt",
    "jungle_mahal",
    "burdwan_industrial",
    "presidency_suburbs",
    "murshidabad",   # ← add: 4-way Muslim fragmentation, highest volatility
}
```

If you find a different rationale for what the 5th should be, note it in your scope
questions. Do not add more than 1 cluster.

### 3. Add `--manifesto` and `--budget-ceiling` flags

**File:** `popscale/benchmarks/wb_2026/constituency/wb_2026_constituency_benchmark.py`

In `parse_args()`:

```python
parser.add_argument(
    "--manifesto",
    type=str,
    choices=["tmc", "bjp", "both"],
    default=None,
    metavar="PARTY",
    help="Inject party manifesto context into scenario. Choices: tmc | bjp | both. "
         "Only runs SWING_CLUSTER_IDS. Required for sensitivity study.",
)
parser.add_argument(
    "--budget-ceiling",
    type=float,
    default=None,
    metavar="USD",
    help="Hard total budget ceiling across all clusters in this run (USD). "
         "Run aborts if projected cost exceeds ceiling before starting. "
         "Default: no ceiling (per-cluster caps still apply).",
)
parser.add_argument(
    "--sensitivity-baseline",
    type=str,
    default=None,
    metavar="PATH",
    help="Path to a prior results JSON file to use as baseline for sensitivity delta "
         "computation. If omitted, no delta is computed (absolute results only).",
)
```

### 4. Modify `build_cluster_request` to inject manifesto

```python
def build_cluster_request(
    cluster: dict,
    manifesto: str | None = None,
) -> NiobeStudyRequest:
    """Build a NiobeStudyRequest for a single cluster."""
    full_context = BASE_SCENARIO_CONTEXT + "\n\n" + cluster["context_note"]

    if manifesto is not None:
        from .manifesto_contexts import MANIFESTO_CONTEXTS
        full_context = full_context + "\n\n" + MANIFESTO_CONTEXTS[manifesto]

    budget_cap = max(3.0, round(cluster["n_personas"] * 0.50, 2))
    # ... rest unchanged
```

Pass `manifesto=args.manifesto` at all call sites.

### 5. Manifesto run mode — swing-only + budget ceiling enforcement

When `--manifesto` is set, the benchmark must:

a. **Only run SWING_CLUSTER_IDS** (not all 10 clusters). Fail fast with a clear
   message if `--cluster` is specified for a non-swing cluster.

b. **Enforce `--budget-ceiling`**: Before the first API call, compute an estimate:

```python
def _estimate_manifesto_run_cost(swing_clusters: list[dict]) -> float:
    """Very rough estimate: n_personas × $0.11 per persona × ensemble_runs."""
    total = 0.0
    for c in swing_clusters:
        runs = N_ENSEMBLE_RUNS  # swing clusters use ensemble
        total += c["n_personas"] * 0.11 * runs
    return total
```

Print the estimate. If `--budget-ceiling` is set and estimate > ceiling, abort:

```python
if args.budget_ceiling and estimate > args.budget_ceiling:
    print(f"ERROR: Estimated cost ${estimate:.0f} exceeds --budget-ceiling "
          f"${args.budget_ceiling:.0f}. Aborting.")
    raise SystemExit(1)
```

c. **Manifesto is incompatible with `--results-file` and `--seat-model-only`** —
   fail with a clear error if those are combined.

### 6. Sensitivity matrix output

After all swing clusters complete, if `--manifesto` is set, write two files:

**File 1:** `popscale/benchmarks/wb_2026/results/sensitivity/sensitivity_<run_id>.json`

```json
{
  "run_id": "<timestamp>",
  "manifesto": "both",
  "baseline_file": "<path or null>",
  "generated_at": "<iso8601>",
  "clusters": {
    "matua_belt": {
      "vote_shares": {"TMC": 0.42, "BJP": 0.38, "Left-Congress": 0.12, "Others": 0.08},
      "baseline_vote_shares": {"TMC": 0.44, "BJP": 0.35, ...},  // null if no baseline
      "delta": {"TMC": -0.02, "BJP": +0.03, ...},               // null if no baseline
      "n_personas": 40,
      "ensemble_runs": 3,
      "confidence_penalty": 0.0,
      "gate_waivers": 0
    },
    ...
  },
  "seat_projection": {
    "with_manifesto": {"TMC": 185, "BJP": 58, ...},
    "baseline": {"TMC": 194, "BJP": 45, ...},        // null if no baseline
    "seat_delta": {"TMC": -9, "BJP": +13, ...}       // null if no baseline
  },
  "total_cost_usd": 42.30
}
```

**File 2:** `popscale/benchmarks/wb_2026/results/sensitivity/sensitivity_<run_id>.csv`

Columns: `cluster_id, party, manifesto_vote_share, baseline_vote_share, delta_pp`

Also **print the sensitivity table to stdout** in a human-readable format:

```
WB 2026 MANIFESTO SENSITIVITY MATRIX (both manifestos injected)
================================================================
Cluster              TMC     BJP    L-C    Other  | vs baseline
matua_belt           42%     38%    12%     8%    | TMC -2pp BJP +3pp
jungle_mahal         ...
burdwan_industrial   ...
presidency_suburbs   ...
murshidabad          ...
================================================================
SEAT PROJECTION (manifesto): TMC 185 | BJP 58 | L-C 46 | Other 5
SEAT PROJECTION (baseline):  TMC 194 | BJP 45 | L-C 50 | Other 5
SEAT DELTA:                  TMC  -9 | BJP +13 | L-C  -4 | Other 0
```

When `--sensitivity-baseline` is omitted, the delta column shows `(no baseline)`.

### 7. Integration with existing `--cost-trace`

The `--cost-trace` flag must work in combination with `--manifesto`. No
additional work needed — just ensure the manifesto run path also reaches
the `_dump_cost_trace()` finally block.

### 8. Dry-run support

When `--dry-run --manifesto both` is passed, print:
- Which clusters will run (the 5 swing clusters)
- Manifesto context length (character count for TMC, BJP, combined)
- First 200 characters of the injected context for one cluster
- Estimated cost and whether it would pass the `--budget-ceiling` check

---

## Acceptance criteria

- [ ] `python3 -m benchmarks.wb_2026.constituency.wb_2026_constituency_benchmark --dry-run --manifesto both` prints 5 swing clusters, context preview, and cost estimate. No API calls.
- [ ] `python3 ... --manifesto both --budget-ceiling 75 --dry-run` shows "Would pass budget ceiling: $75"
- [ ] `python3 ... --manifesto both --budget-ceiling 10 --dry-run` shows "ERROR: Estimated cost ... exceeds --budget-ceiling $10"
- [ ] `--manifesto` without `--dry-run` runs SWING_CLUSTER_IDS only (not all 10 clusters)
- [ ] `--manifesto` combined with `--results-file` prints clear incompatibility error and exits 1
- [ ] Sensitivity JSON file written to `results/sensitivity/` on completion
- [ ] Sensitivity CSV written alongside JSON (same `run_id`)
- [ ] Sensitivity table printed to stdout with correct column headers
- [ ] `--sensitivity-baseline path/to/file.json` correctly computes delta vs. that file
- [ ] `murshidabad` is now in `SWING_CLUSTER_IDS`
- [ ] All existing tests still pass (no regressions)
- [ ] Zero behavioural change when `--manifesto` is NOT set

---

## Anti-goals (do NOT do these)

- ❌ Do not modify `BASE_SCENARIO_CONTEXT` — manifesto is additive injection only
- ❌ Do not change the ensemble or gate-retry logic
- ❌ Do not add new Python dependencies
- ❌ Do not run a live API call as part of your delivery — dry-run only
- ❌ Do not modify `manifesto_contexts.py` texts — use them verbatim as provided
- ❌ Do not touch `CostTracer`, `GateWaiver`, or semaphore logic

---

## Baseline reference (for `--sensitivity-baseline`)

The April 22 baseline run results live at:
```
popscale/benchmarks/wb_2026/constituency/results/
```
List the JSON files there. The most recent complete run (all 10 clusters) is
the correct baseline. Identify the file in your scope questions if ambiguous.

---

## Deliverable format

Branch: `sprint1/brief-003-manifesto-sensitivity`. Do NOT commit to main.

```
# BRIEF-003 S1.4 DELIVERY

## Summary
<one paragraph>

## Architecture decisions
<non-obvious choices, e.g. why manifesto-only mode restricts to swing clusters>

## Files changed (existing)
- path/to/file.py  +N -M lines
- ...

## Files created (new)
- path/to/new/file.py  N lines (brief description)
- ...

## Unified diff
<full diff including full text of new files>

## Dry-run output
$ python3 -m benchmarks.wb_2026.constituency.wb_2026_constituency_benchmark \
    --dry-run --manifesto both --budget-ceiling 75
<output>

## Budget ceiling rejection test
$ python3 ... --dry-run --manifesto both --budget-ceiling 10
<output showing abort message>

## Existing test regression
$ pytest popscale/tests/ persona-generator/tests/ niobe/tests/
<output>

## Context injection verification
<show first 300 chars of full_context for matua_belt with --manifesto both>

## Scope questions raised (with your chosen resolution)
<including: which baseline file you identified, if any>

## Deviations from brief (with rationale)
<any deviation and why>

## Timebox actual
<hours taken>
```

Coordinator reviews, rates, and issues verdict. After acceptance, coordinator
will trigger the live $75 manifesto run and paste results back.

---

## Rubric

Correctness / Code Quality / Test Coverage / Adherence — each /5. Total /20.

Special attention on: 
- Manifesto texts used verbatim (not paraphrased)
- Dry-run mode complete and accurate
- Budget ceiling abort works correctly
- Sensitivity matrix JSON schema matches spec exactly
