# Population Engine — Capacity & Fix Roadmap

**Status:** Post-WB 2026 technical note  
**Author:** Simulatte engineering  
**Date:** 23 April 2026  
**Purpose:** Document engine capacity limits surfaced during the WB 2026 manifesto sensitivity testing, and the prioritised path to fix them before the next state election study (Tamil Nadu / Kerala 2026).

---

## 1. What we learned on April 23

Attempting a manifesto + stress-test sensitivity re-run on 5 swing clusters (Matua Belt, Burdwan, Jungle Mahal, Presidency, Darjeeling) revealed the engine cannot reliably complete these runs within budget at current configuration. Specifically:

- **Murshidabad** (40 personas, ensemble=1) completed in ~13 min at ~$3–5. This is the engine operating well.
- **Matua Belt** (60 personas, ensemble=3): failed 3 times across 4+ hours of compute and ~$75 spent, never producing a result JSON. The failure mode is not a crash — the engine keeps making progress, just too slowly to reach the voting phase within reasonable wall-clock and cost.

## 2. Root cause (real, not assumed)

The engine's cost per cluster is dominated by **persona generation throughput**, not by gate-retry loops (gates are skipped via `--skip-gates`). The per-persona cost structure:

```
Per persona:
  LifeStoryGenerator       1 LLM call
  IdentityConstructor      8 LLM calls  ← the bulk
  AttributeFiller          2–4 LLM calls
  ConstraintChecker        0 calls (validation only)
  ------------------------------------
  Total                    11–13 calls per persona
```

Observed actual: **~950 LLM calls per persona in the Matua runs** — ~70× the formula count. This means each persona triggers substantial retries or validation loops inside one of the four phases, most likely IdentityConstructor or AttributeFiller.

## 3. Engine capacity today (empirical)

| Cluster profile | n_personas | Ensemble | Cost | Wall-clock | Success rate |
|---|---|---|---|---|---|
| Small, homogeneous (Murshidabad) | 40 | 1 | $3–5 | 12–15 min | 100% |
| Small, diverse (Kolkata) | 20–30 | 1 | $4–7 | 8–12 min | 100% |
| Medium mixed (Burdwan) | 40 | 1 | $10–15 | 15–25 min | ~80% |
| Large (Matua, Jungle Mahal) | 60 | 3 | $30+ (often non-terminating) | 40–60+ min | 0% today |

**Reliable cluster capacity: ~40 personas, single ensemble.** Anything larger becomes high-risk.

## 4. Fix roadmap, prioritised

### Tier 1 — Immediate (pre-next-election, 1–2 weeks)

**F1. Per-persona cost profiling and consolidation**  
**Effort:** 3–5 days  
**Impact:** 40–60% cost reduction per persona

Instrument IdentityConstructor and AttributeFiller to log actual LLM call count per persona. The 11–13 formula count is ~70× lower than observed; identify whether the excess comes from:
- Internal validation retries
- Structured-output schema rejection loops
- Sub-call chains (e.g., worldview → psych → behaviour → value as 4 sequential calls when they could be one structured call)

Consolidate the 8-call IdentityConstructor into 2–3 structured calls using strict JSON schema output. Target: reduce mean calls per persona from ~950 observed to <50.

**F2. Persona pool caching across ensemble runs**  
**Effort:** 2–3 days  
**Impact:** 3× cost reduction on any ensemble workflow

Today, a 3-run ensemble regenerates the entire 60-persona Bengal pool 3×. With caching:
- Run 1: generate 60 personas ($X)
- Run 2–3: reuse the same 60 personas, only re-run the voting/scenario phase ($0.3X each)
- Total ensemble cost: 1.6× single run instead of 3×

Implementation: add a persona-pool hash key (cluster_id + population_spec_hash) and a local JSON cache. Invalidate only when demographics change, not when scenario context changes.

**F3. Streaming partial results**  
**Effort:** 2–3 days  
**Impact:** Prevents $25+ sunk-cost losses on timeout kills

Today, if a run is killed at 85% completion, the JSON is never written and all compute is lost. Change the seat-model aggregation to write a partial JSON after each ensemble run completes, and after each persona votes (even if other personas haven't finished yet). This means partial data is always harvestable, turning $25 burns into $20 of usable data.

### Tier 2 — Medium term (6–8 weeks, post-next-election)

**F4. Consolidated state-level persona pool**  
**Effort:** 2–3 weeks  
**Impact:** 80% cost reduction on multi-cluster studies

Generate 500 Bengal personas once, stratified on all 10 cluster dimensions. For any subsequent cluster run, sample the relevant 40 from the pool instead of regenerating. A 10-cluster election study goes from ~$80–150 today to **~$15** after the initial pool build.

This changes the economics of calibration entirely. Post-election gap analysis becomes cheap. Sensitivity testing (manifestos, anti-incumbency, nationalism, policy shocks) becomes cheap. Iterative hypothesis testing becomes feasible.

**F5. Batch Inference via Anthropic Message Batches API**  
**Effort:** 1 week  
**Impact:** 50% cost reduction with 1-hour latency tradeoff

For non-interactive sensitivity studies where results in <1 hour aren't required, route persona generation and voting through the Message Batches API. 50% cost reduction, 24-hour max latency. Appropriate for bulk re-runs and post-event calibration work; not for real-time use.

**F6. Convergence-aware ensembles**  
**Effort:** 1 week  
**Impact:** 33% ensemble cost reduction

Today, ensembles always run 3× regardless of whether the first two runs agreed. Add a convergence check: if runs 1 and 2 produce seat predictions within ±1 seat of each other, skip run 3. In practice this will terminate most ensembles at 2 runs.

**F7. Concurrency safety**  
**Effort:** 1 day  
**Impact:** Prevents rate-limit cascades

Explicit semaphore cap on concurrent LLM calls per process, and a check that prevents accidentally launching parallel runs of the same cluster (which on April 23 caused 6,000+ 429 retries and ~$30 of wasted compute). Defensive engineering, not performance.

### Tier 3 — Strategic (quarter-long, post Tamil Nadu / Kerala 2026)

**F8. Cross-election persona reuse and calibration**  
**Effort:** 4–6 weeks  
**Impact:** Each additional election study costs 5× less than the first

A voter in rural Bengal isn't identical to a voter in rural Tamil Nadu, but the structural scaffolding (demographic anchor → life story → identity → attributes) can be shared across India-wide studies with targeted regional overlays. This unlocks a library of reusable, calibrated regional pools — the path from "every election study is a greenfield build" to "every election study is a delta on existing infrastructure."

**F9. Incremental persona updates**  
**Effort:** 3–4 weeks  
**Impact:** Real-time sensitivity testing

When a new political event lands (a manifesto drops, a coalition breaks, a scandal surfaces), today we regenerate the affected cluster. A future version mutates only the relevant attributes (political lean, news salience, grievance stack) on the existing pool — a <$1 incremental update per cluster instead of a $5 regeneration. Makes the engine reactive to live news.

## 5. Decision framework

| Horizon | What it buys | Cost | When to do |
|---|---|---|---|
| **Tier 1 (F1+F2+F3)** | 10-cluster study goes from $80–150 → $30, with no failures | 1–2 weeks of eng | Before next election study |
| **Tier 2 (F4+F5+F6+F7)** | Marginal study cost drops to ~$15, safe under pressure | 6–8 weeks | Post-next-election |
| **Tier 3 (F8+F9)** | India-wide election coverage + real-time sensitivity | 1 quarter | After 2–3 state studies establish the pattern |

## 6. Recommendation

**Do Tier 1 before any more election studies.** The April 23 burn (~$100 on failed sensitivity testing) is a one-time tax on not having these fixes — but the same failure mode will recur on every subsequent study until F1–F3 land.

Tier 2 pays back its own cost within 1–2 election studies.

Tier 3 is the difference between Simulatte-as-bespoke-studies and Simulatte-as-election-infrastructure.

---

## Appendix: Matua-specific finding (for regression testing)

The Matua Belt cluster (40-seat Hindu SC refugee belt) consistently fails to complete under:
- n_personas ≥ 40 AND
- Dense context injection (3+ context variables beyond baseline demographics)

Murshidabad, with the same n_personas=40 but a lighter context load, completes reliably. This suggests the per-persona cost scales non-linearly with context density. F1 (call-count consolidation) should fix this as a side effect; regression test should verify by running Matua at n=40 with full manifesto + stress injection and confirming <$10 completion.
