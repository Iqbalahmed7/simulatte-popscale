# Simulatte Engine — Core Spec Sheet

**Version:** 2.0 (Construct Phase 2 target state) · **Last updated:** 2026-04-25

This is the single source of truth for what the engine is, what it does, what it costs, and how it fails. If anything in this document conflicts with code, the code is wrong and must be fixed.

---

## 1. System architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          ORCHESTRATION                          │
│   PopScale (benchmark drivers) ↔ Niobe (population studies)     │
└──────────────────────┬──────────────────────────────────────────┘
                       │
        ┌──────────────┴──────────────┐
        │                             │
        ▼                             ▼
┌──────────────────┐         ┌────────────────────┐
│ Persona Generator │         │  Domain Framing    │
│ (cohort assembly  │         │  (translates       │
│  + cognitive loop) │         │   persona into    │
│                   │         │   domain language) │
└──────────────────┘         └────────────────────┘
        │                             │
        └──────────────┬──────────────┘
                       │
                       ▼
            ┌──────────────────────┐
            │   Anthropic API      │
            │   (Sonnet + Haiku)   │
            └──────────────────────┘
```

### 1.1 Component responsibilities

| Component | Responsibility | Repo |
|---|---|---|
| **PopScale** | Benchmark scenarios, sensitivity testing, seat models, scoring | `simulatte-popscale` |
| **Niobe** | Population studies, cohort orchestration, multi-stage research lifecycle | `simulatte-niobe` |
| **Persona Generator** | Persona attributes, memory, cognitive loop (`perceive → accumulate → reflect → decide`) | `simulatte-persona-generator` |
| **Engine** | Bundles all three for production deployment | `simulatte-engine` (Railway) |

### 1.2 Cognitive loop contract (Persona Generator)

```
run_loop(stimulus, persona, decision_scenario, tier) →
  (updated_persona, LoopResult)

LoopResult:
  - observations: list[Observation]
  - reflections: list[Reflection] (if threshold met)
  - decided: bool
  - decision: DecisionOutput | None
```

This contract does not change in Phase 2.

---

## 2. Model tiering policy (post-Phase-1)

| Stage | Model | Max tokens | Why |
|---|---|---|---|
| Persona attribute generation | `claude-haiku-4-5-20251001` | 2048 | Structured slot-fill |
| Cohort assembly + gates | `claude-haiku-4-5-20251001` | 2048 | Logic checks |
| `perceive()` | `claude-haiku-4-5-20251001` | 2048 | Already correct |
| Memory writes | `claude-haiku-4-5-20251001` | 2048 | Already correct |
| `reflect()` | `claude-sonnet-4-6-20251015` | 4096 | Cross-memory reasoning |
| `decide()` | `claude-sonnet-4-6-20251015` | 4096 | Most consequential — keep premium |

**Rule:** No `decide()` call may be downgraded to Haiku without an A/B test showing parity on a backcast benchmark.

---

## 3. Performance budgets

### 3.1 Cost (per study)

| Study size | Pre-Phase-1 actual | Post-Phase-1 target | Post-Phase-2 stretch |
|---|---|---|---|
| 1 cluster, 60 personas, 3 ensemble runs | $90–150 | $20–25 | $15 |
| 5 clusters | $430+ | $90 | $75 |
| 50 clusters (10× scale) | unrunnable | $900 | $500 |

### 3.2 Latency (wall clock)

| Study size | Pre-Phase-2 | Post-Phase-2 |
|---|---|---|
| 1 cluster | 60–90 min | 15–25 min |
| 5 clusters | 6–12 hrs | 2–3 hrs |
| 50 clusters | unrunnable | <8 hrs |

### 3.3 Reliability

| Metric | Pre-Phase-2 | Post-Phase-2 target |
|---|---|---|
| Successful run rate (no manual restart) | ~14% (1/7 attempts) | >95% |
| JSON parse fallback rate | ~2% | <0.1% |
| Mean time to recovery from crash | manual, ~12 hrs | <5 min |
| Max work lost on crash | 1 cluster (~$50–150) | 1 ensemble (~$5–15) |

---

## 4. Data contracts

### 4.1 Scenario (PopScale → Niobe)

```python
Scenario:
  domain: SimulationDomain  # POLITICAL, CONSUMER, etc.
  question: str
  options: list[str]        # decision choices
  context: str              # base scenario context
  manifesto: str | None     # optional injected manifesto
  sensitivity_baseline: AbsolutePath | None  # for swing calc
```

**Hard rule:** All paths in `Scenario` must be absolute. Pre-flight validator rejects relative paths.

### 4.2 PopulationResponse (per persona)

```python
PopulationResponse:
  persona_id: str
  decision: str
  confidence: float           # 0.0–1.0
  reasoning_trace: str
  gut_reaction: str
  key_drivers: list[str]
  objections: list[str]
  what_would_change_mind: str
  emotional_valence: float    # -1.0–1.0
  domain_signals: DomainSignals
  # demographic columns
  age, gender, location, income_bracket, ...
```

### 4.3 Cluster result

```python
ClusterResult:
  cluster_id: str
  ensemble_runs: list[EnsembleRun]   # 3 runs typical
  ensemble_avg: VoteShare
  ensemble_variance: float           # std dev across runs
  high_variance_flag: bool           # True if variance >10pp
  responses: list[PopulationResponse]
  cost_usd: float
  duration_seconds: float
```

Variance flag is computed automatically (Phase 4 task).

### 4.4 Backcast result (Phase 3)

```python
BacktestResult:
  election_id: str               # e.g. "us_2024_pres", "wb_2021_assembly"
  ground_truth: dict[str, float] # actual results
  predicted: dict[str, float]    # simulated results
  brier_score: float
  mae_vote_share: float
  seat_error_pct: float
  directional_accuracy: float
  demographic_decomposition: dict # error by demographic cell
```

---

## 5. Failure mode contracts

The system must handle these explicitly. Each has an owner and a runbook entry.

| Failure | Detection | Action | Recovery |
|---|---|---|---|
| Credit balance <$10 | Pre-call balance check | Halt; checkpoint; push notify | Manual top-up; resume |
| HTTP 400 (bad request) | Single retry with stricter prompt | If still fails, fallback response | Logged; no retry storm |
| HTTP 429 (rate limit) | Token bucket detects | Exponential backoff, max 5 retries | Auto |
| HTTP 500 (server error) | Per-call exception | Exponential backoff, max 3 retries | Auto |
| JSON parse failure | Schema validation post-decode | One stricter retry; then fallback | Logged |
| Process crash | Heartbeat absent >5 min | External monitor restarts | Resume from last ensemble |
| Anthropic outage | Health check fails | Halt all clusters; checkpoint; notify | Manual resume |

**Inviolable rule:** Every failure mode either auto-recovers or halts cleanly with a checkpoint. **No silent retry loops. No silent budget burn.**

---

## 6. Observability contract

Every run must emit, in real time, to a structured log + dashboard:

| Field | Cadence |
|---|---|
| `run_id` | once at start |
| `cluster_id`, `ensemble_run_id` | per ensemble |
| `personas_done / personas_total` | per persona |
| `cost_usd_spent` | per API call |
| `cost_usd_estimated_remaining` | per persona |
| `api_calls_per_minute` | rolling 60s |
| `error_count`, `last_error` | on error |
| `cache_hit_rate` | rolling 60s |

Dashboard URL convention: `https://construct.simulatte.io/runs/{run_id}`

---

## 7. Versioning + compatibility

- Spec version follows `MAJOR.MINOR` (this is 2.0)
- Breaking changes to data contracts (Section 4) require a MAJOR bump
- New fields, new failure modes, new observability fields are MINOR
- Code that consumes a `ClusterResult` must tolerate unknown fields

---

## 8. Out of scope for Construct Phase 2

| Item | Reason | Defer to |
|---|---|---|
| Multi-vendor LLM routing (OpenAI / Gemini) | One provider until cost + reliability owned | Phase 3 |
| Custom embedding models | Prediction quality first | Phase 3 |
| LoRA fine-tuning of persona generator | Decision-layer fine-tuning is enough | Phase 3 |
| Customer SaaS UI | Back-office orchestration only | Phase 3 |
| Non-political domains (consumer, healthcare, finance) | Prove prediction first | Phase 3 |

---

## 9. Glossary

- **Cluster** — A grouped subset of the target population (e.g. "Murshidabad Muslim Heartland") simulated as one unit
- **Ensemble run** — One full pass of N personas through the cognitive loop on a scenario; averaged with sibling runs to reduce variance
- **Backcast** — Running the engine on a historical scenario where ground truth is known, scoring the prediction
- **Manifesto injection** — Appending policy text to the scenario context to test sensitivity to specific policy platforms
- **Tier** — `DEEP` / `SIGNAL` / `VOLUME` — controls how much cognitive depth is invested per persona (DEEP = full reflection; VOLUME = perceive + decide only)
- **Fallback response** — Degraded output when cognitive loop fails; uses persona priors instead of full reasoning
