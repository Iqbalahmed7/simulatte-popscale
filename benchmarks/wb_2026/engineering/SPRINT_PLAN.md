# PopScale Engine — Sprint Plan

**Program:** Population engine productionisation  
**Duration:** 6 sprints × 2 weeks = 12 weeks  
**Kicked off:** Post WB 2026 publication (April 23, 2026)  
**Owner:** Simulatte engineering

---

## Program objectives

1. Eliminate unbounded-cost failure modes (no more $30+ black holes)
2. Cut marginal cost per cluster by 5× (from $15–25 to $3–5)
3. Port the engine across Indian states with minimal rework
4. Enable live sensitivity testing against news events

---

## Sprint 1 (Weeks 1–2) · "Stop the bleeding"

**Goal:** No more $30+ non-terminating runs. Every cluster completes or fails fast with usable partial output.

### S1.1 — Cost observability instrumentation
- **Effort:** 3 days
- **Files:** `Persona Generator/src/generation/identity_constructor.py`, `life_story_generator.py`, `attribute_filler.py`, `Niobe/niobe/runner.py`
- **Tasks:**
  - Wrap every `await llm_client.*` call with a counter tagged by `(persona_id, phase, sub_step)`
  - Emit structured log line per persona: `persona_cost_summary(persona_id=X, phase=identity, calls=N, tokens=T, duration=D)`
  - Add `--cost-trace` CLI flag to benchmark runner that dumps per-persona cost CSV
- **Exit:** Run one Matua cluster with `--cost-trace`, produce a CSV showing exactly where the 950 calls/persona come from.

### S1.2 — Bounded gate-retry + streaming results
- **Effort:** 2 days
- **Files:** `Persona Generator/src/generation/cohort_assembler.py`, `schema/validators.py`
- **Tasks:**
  - `MAX_GATE_RETRIES = 3` env-configurable constant in `cohort_assembler`
  - After 3 failed attempts, accept cohort as-is, emit `GateWaiver` warning, continue
  - Modify `cohort_assembler.assemble` to yield each persona as it's written
  - `seat_model.compute_seat_predictions` accepts partial cohort with `confidence_penalty` flag
- **Exit:** A Matua run killed at 80% produces a valid (confidence-penalised) result JSON instead of losing everything.

### S1.3 — Concurrency guardrail
- **Effort:** 1 day
- **Files:** `Niobe/niobe/runner.py`, `PopScale/benchmarks/*/wb_2026_constituency_benchmark.py`
- **Tasks:**
  - Add `asyncio.Semaphore(20)` at top of `run_niobe_study` shared across all sub-operations
  - PID-file lock in benchmark runner: refuse to launch if another instance of the same cluster is running
  - `kill_prior_runs.py` utility to clean orphaned benchmark processes
- **Exit:** Impossible to accidentally launch two parallel runs of the same cluster.

### S1.4 — Sprint close: WB 2026 manifesto sensitivity re-run
- **Effort:** 1 day
- **Tasks:**
  - Run all 5 swing clusters with manifesto injection at $75 ceiling (now feasible post-S1.1/S1.2)
  - Produce the actual sensitivity result we couldn't get on April 23
  - Close out post-election disclosure note with real data
- **Exit:** WB 2026 sensitivity matrix landed.

---

## Sprint 2 (Weeks 3–4) · "Consolidate IdentityConstructor"

**Goal:** Cut mean calls-per-persona from ~950 observed to <50. The single biggest cost lever.

### S2.1 — Identity synthesis consolidation
- **Effort:** 5 days
- **Files:** `Persona Generator/src/generation/identity_constructor.py` (heavy refactor)
- **Current:** 8 sequential LLM calls
- **Target:** 2 structured LLM calls using Anthropic JSON mode
  - Call 1: `IdentityCore` (demographics + life story → worldview, psych_insights, value_orientation)
  - Call 2: `IdentityBehavior` (core + context → behaviour_tendencies, trust_anchor, risk_appetite)
- **Tasks:**
  - Define two Pydantic schemas for structured outputs
  - Consolidate 8 prompts into 2 using explicit schema prompting
  - Validation layer retries ONCE if schema doesn't parse (not 5+)
  - Port 8 existing test fixtures to new 2-call structure
- **Exit:** Per-persona identity cost drops from 8 calls to 2. Matua persona generation drops from ~40 min to ~10 min.

### S2.2 — AttributeFiller retry audit
- **Effort:** 2 days
- **Files:** `src/generation/attribute_filler.py`
- **Tasks:**
  - Using S1.1 cost trace data, identify which attributes trigger retry loops
  - Cap AttributeFiller retries at 2 per attribute (hard ceiling)
  - Fallback: if attribute fails both attempts, use default from anchor
- **Exit:** AttributeFiller can never be the source of a runaway run.

### S2.3 — Regression tests on all 10 WB clusters
- **Effort:** 2 days
- **Tasks:**
  - Run each of 10 WB clusters at baseline (n=40, ensemble=1)
  - Compare vote shares pre/post-consolidation
  - Any cluster with >3pp vote-share drift → investigate before landing
- **Exit:** Identity consolidation PR merges. Per-cluster cost drops 3×. All 10 clusters directionally consistent.

---

## Sprint 3 (Weeks 5–6) · "Persona pool caching"

**Goal:** Ensemble runs become nearly free. State-level caching foundation laid.

### S3.1 — Cluster-level persona cache
- **Effort:** 3 days
- **Files:** New module `Persona Generator/src/cache/persona_pool_cache.py`; `Niobe/niobe/runner.py`
- **Tasks:**
  - Cache key = `sha256(cluster_id + population_spec_canonical_json)` (excludes scenario context)
  - On-disk JSON cache at `~/.simulatte/persona_cache/<cluster_id>/<hash>.json`
  - `run_niobe_study` checks cache → hit means skip population build, go straight to scenario
  - `--no-cache` flag for forced regeneration
  - LRU eviction at 500MB cache size
- **Exit:** Second ensemble run costs ~1/5 of the first. 3-run ensemble drops from 3× to 1.4×.

### S3.2 — State-level pool seeding
- **Effort:** 4 days
- **Files:** New module `Persona Generator/src/cache/state_pool.py`
- **Tasks:**
  - `generate_state_pool(state='west_bengal', n=500)` — generates 500 Bengal personas once
  - Stratification across all 10 cluster dimensions simultaneously
  - Cluster-sampling layer: given cluster_id, sample the 40 most-matching personas
  - Integration test: sampled distributions match cluster demographics
- **Exit:** `generate_state_pool('west_bengal')` runs once at ~$25, enabling every subsequent WB study at ~$5/cluster.

### S3.3 — Migration + validation
- **Effort:** 2 days
- **Tasks:**
  - Migrate WB 2026 benchmark to use state pool
  - Re-run all 10 clusters off the cached pool
  - Compare to S2.3 regression baseline — within ±2pp
- **Exit:** Full 10-cluster sensitivity study <$15 end-to-end after initial pool build.

---

## Sprint 4 (Weeks 7–8) · "Batch inference + convergence"

**Goal:** Cost-aware workflows. 50% reduction on non-interactive sensitivity studies.

### S4.1 — Message Batches API integration
- **Effort:** 4 days
- **Files:** `Niobe/niobe/runner.py`, new `Niobe/niobe/batch_runner.py`
- **Tasks:**
  - `async def run_niobe_study_batch(request, max_wait_hours=1)` using Anthropic Message Batches API
  - Queue all persona generation in a single batch submission
  - Poll every 60s, parse results when complete
  - CLI flag `--batch` on benchmark runner
  - Fallback to streaming if batch exceeds max_wait
- **Exit:** Post-election gap analysis at 50% cost, 1-hour latency.

### S4.2 — Convergence-aware ensembles
- **Effort:** 2 days
- **Files:** `PopScale/benchmarks/*/wb_2026_constituency_benchmark.py`
- **Tasks:**
  - After ensemble run 2, compute seat-prediction delta from run 1
  - If delta <2 seats across all 4 parties → skip run 3, return average of 1+2
  - Log convergence decision in results JSON
- **Exit:** Ensemble cost drops 33% in typical cases.

### S4.3 — TN/Kerala 2026 pre-study dry-run
- **Effort:** 3 days
- **Tasks:**
  - Build Tamil Nadu and Kerala cluster_definitions (10 clusters each)
  - Generate both state pools
  - Baseline forecast for each state as end-to-end test of new engine
- **Exit:** 3-state election coverage live at <$100 total.

---

## Sprint 5 (Weeks 9–10) · "Incremental updates + live sensitivity"

**Goal:** Engine reactive to news events in real time.

### S5.1 — Attribute-level incremental mutation
- **Effort:** 5 days
- **Files:** `Persona Generator/src/generation/mutator.py` (new), schema extensions
- **Tasks:**
  - `mutate_pool(pool_id, event_context, affected_attributes=['political_lean','news_salience','grievance_stack'])`
  - Single LLM call per persona, not full regeneration
  - Writes mutated snapshot with `parent_pool_id` reference
  - Scenario runner supports "run on snapshot S"
- **Exit:** $0.50/cluster incremental update vs $5 regeneration.

### S5.2 — Event ingestion pipeline
- **Effort:** 3 days
- **Files:** New `Simulatte/event_ingest/` module
- **Tasks:**
  - Structured "political event" format (type, date, affected_demographics, salience_score)
  - CLI: `ingest_event event.yaml` → identifies affected clusters → triggers mutate_pool → re-scores
  - Webhook endpoint (phase 2, out of sprint)
- **Exit:** Manifesto drops, coalition breaks → one command to updated forecast.

### S5.3 — Live sensitivity dashboard
- **Effort:** 2 days
- **Files:** Extension to White Rabbit dashboard
- **Tasks:**
  - New view: "sensitivity ladder" — base forecast + per-event deltas + compound current forecast
  - Lineage: forecast was X before event Y, now X+Δ
  - Per-cluster drill-down
- **Exit:** React to real news event in <15 min with updated forecast + audit trail.

---

## Sprint 6 (Weeks 11–12) · "Cross-election reuse + production hardening"

**Goal:** Engine becomes a library of reusable regional models, not bespoke-per-state.

### S6.1 — Regional pool templates
- **Effort:** 5 days
- **Files:** New `Persona Generator/src/regions/` with templates per Indian state
- **Tasks:**
  - Extract structural scaffolding (demographic anchor + life story base) from WB pool
  - Parameterised regional overlays (caste composition, language, party landscape)
  - Generate Karnataka pool using WB scaffolding + Karnataka overlay; validate against 2023 Karnataka election
  - Document template-creation workflow
- **Exit:** State-pool generation drops from "greenfield" to "instantiate template + calibrate".

### S6.2 — Production monitoring + alerting
- **Effort:** 3 days
- **Files:** New `Niobe/niobe/monitoring.py`
- **Tasks:**
  - Per-run telemetry: cost, duration, cache-hit-rate, gate-waiver count, convergence iterations
  - Anomaly detection: alerts at 2× baseline cost or duration
  - Daily cost dashboard across all running studies
  - Pre-flight cost estimate: refuses to launch if >$50 without override
- **Exit:** Never again unknowingly blow through $50. Operator gets real telemetry.

### S6.3 — Documentation + handoff
- **Effort:** 2 days
- **Tasks:**
  - Engine capacity user guide (what engine can/can't do, cost envelopes)
  - Election study playbook (how to run a new state study end-to-end)
  - Calibration pair library index (WB 2026, TN 2026, Kerala 2026 baseline pools)
- **Exit:** Engine is production asset. Any engineer can run a state election study solo.

---

## Economics

| Sprint | Eng weeks | What it unlocks |
|---|---|---|
| 1 | 2 | No more unbounded cost runs. WB 2026 sensitivity landed. |
| 2 | 2 | Per-cluster cost drops 3× (from $15–25 to $5–10). |
| 3 | 2 | Ensemble cost drops 3×. Full 10-cluster study at <$15. |
| 4 | 2 | +1 state/week capability. 3-state coverage at <$100. |
| 5 | 2 | Engine becomes reactive to news. Live sensitivity. |
| 6 | 2 | Cross-state reusability. Production infrastructure. |

**Total: 12 engineer-weeks. WB 2026 overrun recovered in 1 sprint of program value.**

---

## Milestones

| End of | External deliverable |
|---|---|
| Sprint 1 | Post-election calibration report with full 5-cluster WB sensitivity data |
| Sprint 2 | Ready for TN/Kerala studies at reasonable economics |
| Sprint 4 | 3-state coverage — Bengal, TN, Kerala |
| Sprint 5 | Can react to election-day news in real time |
| Sprint 6 | Engine is a sellable capability, not a research artifact |

---

## Commitment model

Each sprint is exit-criteria gated. If Sprint 1 doesn't ship S1.1 diagnostic, S1.2 bounded retry, AND a successful WB manifesto re-run on budget, Sprint 2 doesn't start. No engineering debt into vapourware.

Sprint 1 is the only one that matters for closing the WB 2026 story. Sprints 2–6 build the path from "we did Bengal" to "we run election infrastructure for every Indian state".
