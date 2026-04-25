# Construct Phase 2 — Engine Rebuild

**Status:** Active · **Started:** 2026-04-25 · **Target completion:** 2026-07-18 (12 weeks)
**Coordinator:** Opus · **Engineering:** Cursor + Codex · **Owner:** Iqbal

---

## Why this phase exists

Sprint 1 (cost observability + guardrails + manifesto sensitivity) closed on 2026-04-25 with one production-grade study delivered — but at a true cost of **$430 across 7 launch attempts**, against a brief of $25. The WB 2026 sensitivity rerun proved Simulatte's reasoning depth is best-in-class. It also proved the surrounding system cannot yet support that depth at any meaningful scale.

Phase 2 closes that gap. The bet is no longer "deeper reasoning beats simpler simulation" — that hypothesis is now testable. The bet is **"deeper reasoning beats simpler simulation _on calibrated point predictions_"**, scored against ground truth.

If we cannot beat Aaru's published 2024 US benchmark on the same target by Week 10, the strategic hypothesis is wrong and we replan. Everything in this document is in service of running enough backcasts to know.

---

## The priority stack

```
1. PREDICTION QUALITY     ← the new #1, needs calibration infra
2. RELIABILITY            ← prerequisite for #1 (cannot backcast on a system that crashes)
3. COST                   ← enables enough backcasts to prove #1
4. SPEED                  ← enables iteration cycles on #1
5. SCALE                  ← falls out of 2/3/4
```

Every task below maps to one of these.

---

## PHASE 0 — Stop the Bleeding (Week 1)

**Goal:** Never lose another $400 to a preventable bug.

| ID | Task | Owner | Days | Priority | Acceptance |
|---|---|---|---|---|---|
| P0.1 | Credit exhaustion detector | Codex | 1 | RELIABILITY | Pre-flight balance check; halt on `<$10` buffer; write checkpoint; push notify |
| P0.2 | Per-ensemble partial writes | Codex | 1 | RELIABILITY | Disk write after every ensemble run; resume granularity = 1 ensemble |
| P0.3 | Pre-flight config validator | Cursor | 0.5 | RELIABILITY | `validate_config()` runs before any API call; absolute path enforcement; budget covers ALL layers |
| P0.4 | Absolute path enforcement | Cursor | 0.5 | RELIABILITY | All baseline/result paths normalised to absolute; CI test catches regressions |
| P0.5 | Cost dashboard MVP | Cursor | 2 | RELIABILITY | Live web view: clusters done/total, $ spent, burn rate, last error. Refreshes every 5s |

**Gate:** Reproduce a forced-crash scenario; engine recovers automatically with <$10 of work lost. Ship a 1-cluster backcast on 2021 WB that completes start-to-finish without intervention.

---

## PHASE 1 — Cost Architecture Overhaul (Weeks 2–3)

**Goal:** $430/study → ~$45–90 (5–10× reduction).

### 1A — Model tier migration

| Stage | Current | Target | Rationale |
|---|---|---|---|
| Persona attribute generation | Sonnet | **Haiku** | Structured slot-fill, low reasoning load |
| Cohort assembly + validation gates | Sonnet | **Haiku** | Logic checks, not reasoning |
| Stimulus perception (`perceive`) | Haiku | **Haiku** ✓ | Already correct |
| Memory writes / accumulation | Haiku | **Haiku** ✓ | Already correct |
| Reflection synthesis | Sonnet | **Sonnet** ✓ | Genuine cross-memory reasoning |
| Final `decide()` | Sonnet | **Sonnet** ✓ | Most consequential call — keep premium |

Estimated saving: **65–75%**.

### 1B — Prompt cache discipline

- Persona core memory cached per persona
- **Manifesto context cached across all 60 personas in a cluster** (biggest win)
- Domain framing cached per cluster
- Scenario templates cached globally

Estimated additional saving: **15–25%**.

### 1C — Structured outputs

Replace JSON parsing with Anthropic structured outputs API for `decide()`, `perceive()`, reflection. Eliminates the Ramesh Chamar / Mohammad Iqbal style failures.

Saves ~5% in retries + drops fallback rate from ~2% to <0.1%.

**Gate:** 5-cluster manifesto sensitivity completes for **<$90 total**, fallback rate <0.5%, no JSON parse retries.

---

## PHASE 2 — Speed + Concurrency (Weeks 4–5)

**Goal:** 5-cluster runtime: 12 hours → 2.5 hours.

| Task | Days | Win |
|---|---|---|
| Parallel cluster execution (`asyncio.gather` + semaphore) | 3 | 5× wall clock |
| Within-cluster ensemble parallelism (3 ensembles concurrent) | 2 | Additional 3× |
| Rate limit governor (token-bucket, RPM/TPM aware) | 2 | Stays under 80% of Anthropic limits, no 429s |
| Distributed checkpoint coordination | 2 | Multiple clusters can checkpoint without race conditions |

Theoretical: 12–15× speedup. Practical (after rate-limit cap): **8–10×**.

**Gate:** 5-cluster study completes in **<3 hours**, $90 budget intact, zero 429s.

---

## PHASE 3 — Prediction Quality (Weeks 6–10) — THE BIG ONE

**Goal:** Match or beat Aaru on a known benchmark. This justifies the entire approach.

### 3A — Backcasting harness (Week 6)

`backcast(election_id, engine_config) → error_report`

Runs full Simulatte pipeline against historical election with inputs frozen at time T, outputs predicted distributions, scores against `ground_truth[election_id]`.

Required ground truth: see `GROUND_TRUTH_REGISTRY.md`.

### 3B — Calibration metrics (Week 7)

| Metric | Target |
|---|---|
| Brier score | <0.15 |
| MAE on vote share | <3 percentage points |
| Seat error | <8% of total |
| Directional accuracy | >90% |
| Demographic decomposition error | <5pp on any single cell |

### 3C — Bias decomposition system (Weeks 7–8)

When backcasts fail, system surfaces *where*: demographic miscalibration, regional systematic bias, issue salience errors, variance/confidence miscalibration. **You need to know where you are wrong, not just that you are wrong.**

### 3D — Calibration training loop (Weeks 8–9)

**Approach 1 — persona prior recalibration:** Adjust attribute distributions in persona-generator based on backcast error. Ships in 1 week.

**Approach 2 — decision model fine-tuning:** Construct calibration pairs from backcast errors, fine-tune Haiku/Sonnet decision model on `(persona, scenario, ground_truth_choice)`. 2–3 weeks. Compounds.

Run both in parallel.

### 3E — Confidence intervals, not point estimates (Week 10)

Replace single-number outputs with calibrated probability distributions.

**Gate:** Beat Aaru's published 2024 US accuracy by ≥1pp MAE on the same target. OR: get within 5pp on 2021 WB at the cluster level. Either result is publishable.

---

## PHASE 4 — Production Hardening (Weeks 11–12)

**Goal:** Run 50-cluster studies without a single human intervention.

| Task | Days | What |
|---|---|---|
| Variance signal automation | 2 | Flag clusters where ensemble spread >10pp; auto-recommend additional runs |
| Auto-retry with exponential backoff | 1 | Replace silent loop on 400/429/500 with smart backoff + alert |
| Observability stack | 3 | Structured logs → Datadog/equivalent; alerts on error rate, burn rate, latency p99 |
| CI/CD test suite | 2 | Mock Anthropic responses; full-pipeline 1-cluster test; block regressions |
| Disaster recovery runbook | 1 | Every failure mode documented with recovery procedure |
| Customer report templates | 1 | Auto-generated DOCX/PPTX with sensitivity tables, confidence bounds, methodology appendix |

**Gate:** 50-cluster study completes with zero human intervention, in <8 hours, total cost <$500.

---

## Resource & sequencing

| Week | Cursor | Codex | Coordinator (Opus) |
|---|---|---|---|
| 1 | Cost dashboard, validators | Credit detector, partial writes | Verify Phase 0 acceptance |
| 2-3 | Tier migration, structured outputs | Cache discipline, JSON cleanup | Cost benchmark |
| 4-5 | Parallel execution | Rate governor | Speed benchmark |
| 6-7 | Backcast harness | Metrics framework | Define success criteria |
| 8-9 | Bias decomposition UI | Calibration training (both approaches) | Run experiments |
| 10 | Confidence interval framework | Final calibration | Compare vs Aaru |
| 11-12 | Observability + tests | Hardening + DR | 50-cluster acceptance run |

Total engineering: ~60 person-days. Calendar: **12 weeks**.

---

## Budget

| Item | Cost |
|---|---|
| Phase 3 backcasts (~30 runs × ~$90 each post-Phase-1) | $2,700 |
| Phase 4 acceptance runs | $1,000 |
| Iteration / failure buffer | $1,500 |
| **Total API spend** | **~$5,200** |

This pays for itself if it prevents two more $430 disasters.

---

## What success looks like at Week 12

> *Simulatte 50-cluster WB 2026 sensitivity study. 3,000 synthetic voters, 5 manifesto conditions, full demographic decomposition. Total runtime: 8 hours. Total cost: $480. Predicted vote share with 90% confidence intervals. Backcast accuracy on 2021 WB: MAE 2.4pp, directional accuracy 93%. Beats published Aaru benchmark on 2024 US (MAE 3.1 vs 4.4).*

That sentence is what closes seed rounds and wins enterprise contracts.

---

## What we explicitly are NOT doing in Phase 2

- Adding new domains beyond political (no consumer/healthcare/finance until prediction quality is proven)
- Building a customer-facing SaaS (back-office orchestration only until Week 12 acceptance)
- Pursuing model fine-tuning beyond decision-layer Haiku/Sonnet (no custom embedding models, no LoRA on persona generator)
- Replacing Anthropic with multi-vendor (one provider until cost + reliability are owned)

These are deferred to Construct Phase 3.

---

## Documents in this phase

| File | Purpose |
|---|---|
| `CONSTRUCT_PHASE_2.md` | This roadmap |
| `CORE_SPEC.md` | Engine spec — architecture, data contracts, performance budgets |
| `GROUND_TRUTH_REGISTRY.md` | Calibration datasets — what we score against |
| `PRINCIPLES.md` | What we believe and why; the bets |
| `briefs/BRIEF-004` through `BRIEF-N` | Individual engineering tickets |

Read all four before opening any brief.
