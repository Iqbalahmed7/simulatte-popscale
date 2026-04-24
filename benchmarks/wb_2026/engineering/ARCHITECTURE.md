# PopScale Engine — Architecture Reference

**Purpose:** Target architecture for the engine post-Sprint-6. Use this as the reference during the rebuild. Current architecture sections describe what exists today and is being refactored away.

---

## 1. System overview

The engine is a three-layer stack:

```
┌──────────────────────────────────────────────────────────────┐
│  PopScale (benchmarks, scenarios, seat models)               │  ← Application layer
│    wb_2026_constituency_benchmark.py                         │
│    seat_model.py                                             │
├──────────────────────────────────────────────────────────────┤
│  Niobe (study orchestration, caching, telemetry)             │  ← Orchestration layer
│    runner.py, batch_runner.py, monitoring.py                 │
├──────────────────────────────────────────────────────────────┤
│  Persona Generator (population synthesis)                    │  ← Engine core
│    cohort_assembler, identity_constructor, attribute_filler  │
│    cache/persona_pool_cache, cache/state_pool                │
│    generation/mutator, regions/*                             │
└──────────────────────────────────────────────────────────────┘
            │
            ▼
┌──────────────────────────────────────────────────────────────┐
│  LLM provider (Anthropic Claude — streaming + batch)         │  ← External
└──────────────────────────────────────────────────────────────┘
```

Each layer has a single contract with the layer below. No cross-layer coupling.

---

## 2. Data flow — single cluster run

```
Benchmark request:
  ClusterRequest(id, demographics, scenario_context, n_personas, ensemble_runs)
      │
      ▼
┌────────────────────────────────────┐
│ Niobe.run_niobe_study              │
│                                    │
│  1. Check state pool cache         │  ← S3.1 / S3.2
│     Hit? → sample subset           │
│     Miss? → generate fresh         │
│                                    │
│  2. Generate/sample personas       │
│     (PG layer — details below)     │
│                                    │
│  3. Stream scenario voting         │
│     Each persona → vote + reason   │
│     Write partial JSON per N done  │  ← S1.2 streaming
│                                    │
│  4. Aggregate to vote shares       │
│     Compute seat model             │
│     Emit convergence signal        │  ← S4.2
│                                    │
│  5. Persist result + telemetry     │  ← S6.2
└────────────────────────────────────┘
      │
      ▼
Result: ClusterResult JSON + cost telemetry + cache artefacts
```

---

## 3. Persona Generator — internals (target state post-S2.1)

**Per-persona pipeline (target ~2–3 LLM calls):**

```
DemographicAnchor(age, gender, location, caste, religion, income_band)
    [deterministic, 0 LLM calls]
        │
        ▼
LifeStoryGenerator(anchor)
    [1 LLM call — structured JSON output]
        │
        ▼
IdentityCore(anchor, life_story)
    Output: {worldview, psych_insights, value_orientation}
    [1 LLM call — consolidated from 3 today]  ← S2.1
        │
        ▼
IdentityBehavior(anchor, life_story, identity_core, scenario_context)
    Output: {behaviour_tendencies, trust_anchor, risk_appetite, values_alignment}
    [1 LLM call — consolidated from 5 today]  ← S2.1
        │
        ▼
AttributeFiller(persona, spec.required_attributes)
    [0–1 LLM calls per attribute, hard cap at 2 retries]  ← S2.2
        │
        ▼
ConstraintChecker(persona)
    [deterministic validation, 0 LLM calls]
        │
        ▼
Persona (complete) → written to cohort
```

**Target call count per persona:** 3 calls + 0–1 retries = typical 3–4 calls  
**Current call count per persona:** 8–13 formula, ~950 observed  
**Post-S2.1 improvement: 300× per-persona cost reduction**

---

## 4. Caching architecture

Three cache layers, each with a distinct invalidation key:

### 4.1 Cluster persona cache (S3.1)

- **Key:** `sha256(cluster_id + population_spec_canonical_json)`
- **Stores:** Complete cohort (40 personas) with all attributes
- **Invalidates when:** cluster demographics change (spec changes)
- **Does NOT invalidate when:** scenario context changes, event context changes
- **Location:** `~/.simulatte/persona_cache/clusters/<cluster_id>/<hash>.json`
- **Lifetime:** LRU at 500MB; typical cluster hash valid for weeks

### 4.2 State pool cache (S3.2)

- **Key:** `sha256(state + population_spec_canonical_json + n)`
- **Stores:** 500-persona master pool for an entire state
- **Invalidates when:** state demographics model changes (~yearly)
- **Sampled from:** cluster-level requests pull 40 most-matching personas from the 500-pool
- **Location:** `~/.simulatte/persona_cache/states/<state>/<hash>.json`
- **Lifetime:** essentially permanent within a calibration epoch

### 4.3 Snapshot cache — event mutations (S5.1)

- **Key:** `sha256(parent_pool_id + event_sequence)`
- **Stores:** Mutated copy of parent pool with event-affected attributes changed
- **Parent lineage:** every snapshot references its parent; deep chains allowed
- **Location:** `~/.simulatte/persona_cache/snapshots/<parent_id>/<event_hash>.json`
- **Lifetime:** LRU at 200MB; typically 5–10 snapshots per active study

---

## 5. Orchestration layer — Niobe

### 5.1 Entry points

- `run_niobe_study(request) → ClusterResult` — single cluster, streaming
- `run_niobe_study_batch(request, max_wait_hours=1) → ClusterResult` — single cluster, batch API (S4.1)
- `run_ensemble(request, n_runs=3) → EnsembleResult` — multi-run with convergence (S4.2)
- `mutate_and_run(parent_pool_id, event, scenario) → ClusterResult` — event-driven (S5.1)

### 5.2 Concurrency model

- Single shared `asyncio.Semaphore(20)` across all LLM operations per process (S1.3)
- PID-file lock prevents duplicate cluster runs (S1.3)
- Per-cluster runs are serial by default; user explicitly opts into parallel via `--parallel` flag with an explicit rate-limit budget

### 5.3 Telemetry

Every run emits a `RunTelemetry` record:

```python
{
  "run_id": str,
  "cluster_id": str,
  "started_at": iso8601,
  "ended_at": iso8601,
  "duration_sec": int,
  "cost_usd": float,
  "llm_calls": int,
  "cache_hit_rate": float,       # S3 caches hit ratio
  "gate_waivers": int,           # S1.2 waivers emitted
  "convergence_iterations": int, # S4.2 ensemble count
  "cost_per_persona_mean": float,
  "cost_per_persona_p99": float,
  "error": str | None
}
```

Dashboard surfaces aggregate telemetry across all runs (S6.2).

---

## 6. Scenario layer — what PopScale provides

PopScale consumes the cohort and runs scenarios. Scenarios are the election-specific logic (or survey, or product, etc.).

```
Scenario contract:
  class ElectoralScenario:
      options: list[str]              # "TMC", "BJP", ...
      context: str                    # base prompt context
      party_resolver: dict[str, str]  # option_text → party_key

  async def run_voter(persona, scenario) -> VoteRecord:
      # perceive → accumulate → decide loop
      # emits 1 LLM call per stage = 3 calls per persona
      return VoteRecord(party, confidence, reasoning)
```

**Target: 3 LLM calls per persona in scenario phase (unchanged).**

The seat model (cube-law FPTP) is deterministic math post-aggregation.

---

## 7. Event ingestion (S5.2)

```
PoliticalEvent:
  id: str
  type: Literal["manifesto", "coalition_break", "scandal", "rally", "policy"]
  date: datetime
  affected_demographics: list[str]   # e.g. ["muslim", "urban_poor"]
  affected_clusters: list[str]       # resolved via mapping table
  salience_score: float              # 0.0–1.0
  text: str                          # raw event description

Pipeline:
  ingest_event(event.yaml)
      → identify_affected_clusters(event)
      → for each cluster:
          mutate_pool(cluster.cache_key, event, attributes=[...])
          → scenario.run(mutated_pool)
          → emit updated ClusterResult + lineage pointer
```

Result: "forecast was X before event Y, now X+Δ" — available in the sensitivity dashboard (S5.3).

---

## 8. Regional templates (S6.1)

Each Indian state has a template defining:

```
RegionTemplate:
  state: str
  language: list[str]
  caste_composition_model: dict[str, float]
  party_landscape: list[Party]
  welfare_schemes: list[Scheme]
  cluster_definitions: list[ClusterDef]   # 10 typical clusters per state
  seat_count: int
  election_schedule_model: str            # FPTP / bicameral / etc.
```

Template instantiation:

```python
bengal = load_region_template("west_bengal")
wb_pool = generate_state_pool(bengal, n=500)  # S3.2
wb_clusters = bengal.cluster_definitions
# ready to run any WB election study
```

Adding a new state: create template + run calibration pair against most recent election. Target: 1 day per new state after template system is live.

---

## 9. Key invariants (must not break during refactor)

1. **Every persona has a stable ID** across runs. Cache hits MUST produce bit-identical personas.
2. **Cache misses are never silent.** Telemetry records every cache hit/miss.
3. **Gate waivers are visible.** A cohort that passed only after waivers emits `confidence_penalty` in results.
4. **Ensemble runs are auditable.** Convergence decisions are logged (which runs skipped and why).
5. **Cost caps are honored.** Pre-flight estimate > $50 requires explicit override (S6.2).
6. **Lineage is preserved.** Every mutated snapshot references its parent — infinite undo capability.

---

## 10. Testing strategy

### 10.1 Unit tests

- `persona_generator/tests/` — per-component unit tests
- `niobe/tests/` — orchestration logic
- `popscale/tests/` — seat model math, scenario aggregation

### 10.2 Integration tests

- `test_full_cluster_run.py` — single cluster end-to-end, mocked LLM
- `test_ensemble_convergence.py` — verify 2-vs-3 run decisions
- `test_cache_invalidation.py` — verify cache keys are stable across equivalent specs

### 10.3 Regression benchmarks

- **WB 2026 baseline regression** — all 10 clusters, compare to locked April 21 vote shares, tolerance ±3pp
- **TN 2023 / Karnataka 2023 back-tests** — out-of-sample validation
- Run on every PR that touches the engine core

### 10.4 Cost benchmarks

- `benchmark_cluster_costs.py` — measure cost per cluster across the 10 WB clusters, alert on >20% regression
- Run weekly on main branch, persist to time series

---

## 11. Deployment topology

```
Local dev:
  Engineer's machine → direct LLM calls → local JSON caches

CI:
  GitHub Actions → mocked LLM (recorded responses) → validates logic, not economics

Production studies:
  Dedicated Railway worker → LLM (real) → Postgres for run telemetry
  Results S3-backed for long-term archival
  White Rabbit dashboard reads from Postgres
```

---

## 12. Engine capacity (target state post-Sprint-6)

| Operation | Cost | Duration |
|---|---|---|
| Single-cluster baseline forecast (from cached state pool) | $3–5 | 5–8 min |
| Full 10-cluster election forecast | $15–25 | 30–45 min |
| 3-run ensemble on a swing cluster | $5–8 | 10–15 min |
| Event-driven mutation + re-forecast single cluster | $0.50 | 2 min |
| Full event-driven re-forecast (10 clusters) | $5 | 15 min |
| New state template + calibration | $25–40 (one time) | 2–4 hours |

**Target envelope:** the engine can run a 10-cluster state election study every day of the election cycle at total cost <$50/day, with live event ingestion ≤2 min latency.
