# PopScale — Agent Cold-Start Guide

## What Is PopScale?

PopScale is the **population-scale simulation orchestration layer** for the Simulatte platform. It bridges the Persona Generator (PG) — which builds rich, psychologically coherent individual synthetic personas — with population-level research studies that need hundreds or thousands of personas responding to structured scenarios.

PopScale does **not** re-implement the cognitive loop, social simulation, memory, or tier routing. Those live entirely in the Persona Generator and are imported directly. PopScale's job is:

1. **Demographic calibration** — translate a `PopulationSpec` (geography, stratification flags) into census-weighted persona segments using profiles sourced from the Census of India, US Census Bureau, ONS, and Eurostat.
2. **Cohort generation** — drive PG's `invoke_persona_generator` for each segment; optionally use seeded generation (1 deep seed + N Haiku variants) for large populations at ~97% cost reduction.
3. **Scenario orchestration** — fan-out a `Scenario` across the cohort with sharding, concurrency control, a circuit breaker, and an optional response cache.
4. **Analytics** — segmentation, Wilson-CI option distributions, Cramér's V / Eta² driver analysis, surprise detection, and Markdown/JSON report generation.
5. **Social simulation** — pass-through adapter to PG's `run_social_loop()` with PopScale-native network builders.
6. **Study runner** — single-call `run_study()` entry point chaining all phases.

**Authoritative source**: `/Users/admin/Documents/Simulatte Projects/PopScale/`  
(A copy exists at `simulatte-platform/popscale/` with a `pyproject.toml` and a `_pg_bridge.py` centralised path resolver, but fewer files.)

---

## Repository Layout

```
PopScale/
├── CLAUDE.md                     ← this file
├── SPEC_SEEDED_GENERATION.md     ← design spec for the seeded generation feature
├── requirements.txt              ← anthropic, pydantic, numpy, pytest
├── pytest.ini                    ← asyncio_mode=auto, live marker
├── conftest.py                   ← sys.path setup (PopScale root + PG root)
│
├── popscale/                     ← main package
│   ├── __init__.py               ← full public API with module-level docstring
│   ├── environment.py            ← SimulationEnvironment presets + registry
│   │
│   ├── calibration/              ← DEMOGRAPHIC LAYER
│   │   ├── population_spec.py    ← PopulationSpec dataclass (validated)
│   │   ├── profiles.py           ← DemographicProfile + _PROFILES dict (India/USA/UK/EU)
│   │   └── calibrator.py        ← calibrate() → list[PersonaSegment]
│   │
│   ├── generation/               ← COHORT GENERATION
│   │   ├── calibrated_generator.py      ← run_calibrated_generation() — full PG pipeline
│   │   ├── seeded_calibrated_generator.py ← run_seeded_generation() — seed + variant
│   │   ├── variant_generator.py         ← VariantGenerator — 1 Haiku call per variant
│   │   ├── seed_calibrator.py           ← distribute_seeds() — proportional seed plans
│   │   └── parity_validator.py          ← validate_parity() — demographic drift check
│   │
│   ├── scenario/                 ← SCENARIO MODEL
│   │   ├── model.py              ← Scenario, ScenarioBundle, SimulationDomain (Pydantic)
│   │   ├── renderer.py           ← render_stimulus(), render_decision_scenario()
│   │   └── events.py             ← EventTimeline, SimulationEvent, EventCategory
│   │
│   ├── integration/              ← PG SEAM
│   │   └── run_scenario.py       ← run_scenario(), run_scenario_batch() — PG cognitive loop
│   │
│   ├── orchestrator/             ← POPULATION ORCHESTRATOR
│   │   ├── runner.py             ← run_population_scenario() — sharding + circuit breaker
│   │   └── cost.py               ← estimate_simulation_cost() — SimulationCostEstimate
│   │
│   ├── analytics/                ← ANALYTICS
│   │   ├── report.py             ← PopScaleReport, generate_report()
│   │   ├── distributions.py      ← compute_distributions() — Wilson CI
│   │   ├── drivers.py            ← analyse_drivers() — Cramér's V, Eta²
│   │   ├── segmentation.py       ← segment_population()
│   │   ├── surprises.py          ← detect_surprises()
│   │   ├── trajectory.py         ← multi-wave trajectory analysis
│   │   ├── event_impact.py       ← before/after event impact measurement
│   │   └── social_report.py      ← generate_social_report()
│   │
│   ├── social/                   ← SOCIAL SIMULATION
│   │   └── social_runner.py      ← run_social_scenario() — PG run_social_loop() adapter
│   │
│   ├── study/                    ← STUDY RUNNER
│   │   ├── study_runner.py       ← run_study(), run_study_sync(), StudyConfig, StudyResult
│   │   └── persistence.py        ← save_study_result(), list_saved_runs()
│   │
│   ├── domain/
│   │   └── framing.py            ← frame_persona_for_domain() — domain-specific prompt framing
│   │
│   ├── schema/                   ← DATA SCHEMAS
│   │   ├── population_response.py  ← PopulationResponse, DomainSignals, from_decision_output()
│   │   ├── simulation_result.py    ← SimulationResult, ShardRecord
│   │   └── social_simulation_result.py ← SocialSimulationResult
│   │
│   ├── cache/
│   │   └── response_cache.py     ← ResponseCache — in-memory + disk JSON cache
│   │
│   └── utils/
│       └── persona_adapter.py    ← adapt_persona_dict(), load_cohort_file() — v1.0 migration
│
├── tests/                        ← test suite (15 test files)
│   ├── conftest.py               ← sys.path setup
│   ├── test_week1_integration.py
│   ├── test_week2_orchestration.py
│   ├── test_week3_analytics.py
│   ├── test_week4_hardening.py
│   ├── test_week5_social.py
│   ├── test_week6_events.py
│   ├── test_week7_calibration.py
│   ├── test_week8_environment.py
│   ├── test_week9_generation.py
│   ├── test_week10_study.py
│   ├── test_geographies.py
│   ├── test_parity_validator.py
│   ├── test_seeded_generation.py
│   └── test_variant_generator.py
│
└── benchmarks/
    ├── delhi_2025/               ← Delhi 2025 benchmark results (6 runs)
    └── us_2024_swing/            ← US 2024 swing state benchmark results (7 runs)
```

---

## Key Data Flows

### Standard Study Run (end to end)

```
StudyConfig(spec, scenario, environment?, timeline?, run_social?)
    │
    ▼  run_study()  [study/study_runner.py]
    │
    ├─ 0. Budget pre-flight: estimate_study_cost(config) → abort if > budget_cap_usd
    │
    ├─ 1. Cohort generation
    │      PopulationSpec → calibrate() → list[PersonaSegment]
    │      Each segment → PersonaGenerationBrief → invoke_persona_generator() (PG)
    │      → list[PersonaRecord]
    │      Seeded mode: run_seeded_generation() → seeds via PG + variants via VariantGenerator
    │      → CohortGenerationResult
    │
    ├─ 2. Environment enrichment
    │      apply_environment(scenario, env) → merged Scenario with preset context
    │
    ├─ 3. Scenario simulation
    │      run_population_scenario(scenario, personas, tier, ...)
    │        ├─ Split personas into shards of shard_size (default 50)
    │        ├─ Per shard: cache check → run_scenario_batch() → ResponseCache.put()
    │        │   run_scenario_batch → run_scenario() per persona
    │        │   run_scenario: render_stimulus → frame_persona_for_domain → run_loop() (PG)
    │        │   run_loop: perceive → accumulate → reflect → decide → PopulationResponse
    │        ├─ Circuit breaker: if fallback_rate > 10% → exponential backoff
    │        └─ → SimulationResult
    │
    ├─ 4. Analytics
    │      generate_report(simulation)
    │        segment_population → distributions → drivers → surprises
    │        → PopScaleReport
    │
    ├─ 5. Social simulation (optional)
    │      build network (random_encounter or full_mesh)
    │      run_social_scenario → PG run_social_loop() → SocialSimulationResult
    │      generate_social_report() → SocialReport
    │
    └─ 6. Persistence (if output_dir set)
           {run_id}_study.json + {run_id}_report.md
           → StudyResult
```

### Seeded Generation Flow

```
PopulationSpec(n_personas=10_000)
    │
    ▼  distribute_seeds(segments, seed_count=200)
    │  → SeedSegment per demographic segment (proportional seed assignment)
    │
    ├─ Pass 1: generate seeds (full PG pipeline, deep tier)
    │    invoke_persona_generator(count=seed_count, anchor_overrides=...) per segment
    │    → list[PersonaRecord]  (generation_mode="full")
    │
    └─ Pass 2: expand variants (Haiku, 1 call per variant)
         VariantGenerator.expand(seed, n=49, segment, domain)
           → vary_demographics (age±5, city rotation)
           → perturb_attributes (Gaussian noise σ=0.08, preserve identity attrs)
           → DerivedInsightsComputer.compute()         [deterministic]
           → TendencyEstimator.estimate()              [deterministic]
           → regenerate_narrative()                    [1 Haiku call]
           → assemble_core_memory()                    [deterministic]
         → list[PersonaRecord]  (generation_mode="variant", seed_persona_id=seed.persona_id)
```

---

## Configuration Points

### PopulationSpec (calibration/population_spec.py)
| Field | Default | Notes |
|---|---|---|
| `state` | required | Geography code: `"west_bengal"`, `"united_states"`, `"france"`, etc. |
| `n_personas` | required | Total personas; must be ≥ 1 |
| `domain` | required | PG domain key: `"policy"`, `"consumer"`, `"cpg"` |
| `business_problem` | required | Research question for cohort brief |
| `age_min` / `age_max` | 18 / 65 | Persona age range |
| `urban_only` / `rural_only` | False | Mutually exclusive location filters |
| `stratify_by_religion` | False | India-only: splits by Hindu/Muslim/Other proportions |
| `stratify_by_income` | False | Splits by low/middle/high income bands |
| `extra_overrides` | {} | Additional anchor_overrides merged into every segment |
| `sarvam_enabled` | False | India cultural enrichment via PG Sarvam pipeline |
| `client` | "PopScale" | Client name in PG brief |
| `persona_id_prefix` | "ps" | Prefix for generated persona IDs |
| `min_segment_size` | 5 | Segments below this are merged into "Other" |

### StudyConfig (study/study_runner.py)
| Field | Default | Notes |
|---|---|---|
| `environment` | None | `SimulationEnvironment` preset (enriches scenario context) |
| `timeline` | None | `EventTimeline` for temporal event injection |
| `run_social` | False | Enable social simulation phase |
| `social_level` | MODERATE | `SocialSimulationLevel` enum |
| `social_topology` | "random_encounter" | Also "full_mesh" |
| `social_k` | 3 | k-value for random_encounter network |
| `generation_tier` | "volume" | PG tier: "volume" / "signal" / "deep" |
| `simulation_tier` | VOLUME | `SimulationTier` enum |
| `use_seeded_generation` | False | Enable seed+variant pipeline |
| `seed_count` | 200 | Number of deep seed personas |
| `seed_tier` | "deep" | PG tier for seeds |
| `budget_cap_usd` | None | Pre-flight cost guard |
| `use_cache` | True | ResponseCache enabled |
| `cache_path` | None | Disk path for cache (in-memory only if None) |
| `shard_size` | 50 | Personas per simulation shard |
| `concurrency` | 20 | Max concurrent LLM calls per shard |
| `output_dir` | None | Auto-save results to disk if set |

### Environment Presets (environment.py)
Named presets available via `get_preset(name)`:

| Preset name | Geography | Domain |
|---|---|---|
| `west_bengal_political_2026` | West Bengal | Political |
| `india_national_policy` | India | Policy |
| `india_urban_consumer` | Urban India | Consumer |
| `india_rural_economy` | Rural India | Consumer/Policy |
| `maharashtra_consumer` | Maharashtra | Consumer |
| `us_consumer_2026` | United States | Consumer |
| `us_political_2026` | United States | Political |
| `us_urban_consumer` | Urban US | Consumer |
| `uk_consumer_2026` | United Kingdom | Consumer |
| `uk_political_2026` | United Kingdom | Political |
| `europe_consumer_2026` | Europe (pan-EU) | Consumer |
| `france_consumer_2026` | France | Consumer |
| `uk_and_eu_policy` | Western Europe | Policy |

### Geography Profile Library (calibration/profiles.py)
46 profiles across India (23 states), USA (15 states/regions), UK, and 7 EU/Middle East countries. Lookup via `get_profile("west_bengal")` with alias support (`"wb"`, `"bengal"`, `"us"`, `"uae"`, etc.).

### Circuit Breaker (orchestrator/runner.py)
| Constant | Value |
|---|---|
| `_DEFAULT_CIRCUIT_BREAKER_THRESHOLD` | 10% fallback rate |
| `_DEFAULT_BACKOFF_BASE_SECONDS` | 10s (doubles per consecutive trip) |
| `_DEFAULT_MAX_BACKOFF_SECONDS` | 120s |

### PG Integration Constants (generation/calibrated_generator.py)
| Constant | Value | Notes |
|---|---|---|
| `_PG_MAX_PER_BRIEF` | 10 | Max personas per PG brief (timeout safety) |
| `_MAX_CONCURRENT_PG_CALLS` | 3 | Max simultaneous PG invocations |
| `_PG_BRIEF_TIMEOUT_S` | 600.0 | Per-brief timeout (10 min) |

### Variant Generator (generation/variant_generator.py)
| Constant | Value |
|---|---|
| `_HAIKU_MODEL` | `"claude-haiku-4-5-20251001"` |
| `_ATTR_NOISE_SIGMA` | 0.08 (Gaussian noise on continuous attrs) |
| `_CATEGORICAL_RESAMPLE_RATE` | 0.05 |
| `_PRESERVE_ATTRS` | `tension_seed`, `trust_orientation_primary`, `religion`, `political_lean`, `caste`, `language_primary` |

---

## Development Setup

```bash
# Prerequisites
# 1. Python 3.11+ (codebase uses __pycache__ with cpython-314, meaning 3.14 dev is in use)
# 2. Persona Generator must be present as a sibling directory:
#    ../Persona Generator/   (or set PG_ROOT env var)

cd "/Users/admin/Documents/Simulatte Projects/PopScale"

# Install dependencies
pip install -r requirements.txt

# Run all non-live tests (no LLM calls)
python -m pytest tests/ -m "not live" -v

# Run all tests including live LLM calls (requires ANTHROPIC_API_KEY)
python -m pytest tests/ -v

# Run a specific test file
python -m pytest tests/test_week7_calibration.py -v

# Run benchmarks (not part of standard test suite)
python benchmarks/delhi_2025/delhi_2025_benchmark.py
python benchmarks/us_2024_swing/us_2024_swing_benchmark.py

# Quick smoke test from Python REPL
python3 -c "
from popscale import PopulationSpec, calibrate, list_states
print(list_states()[:5])
spec = PopulationSpec(state='west_bengal', n_personas=10, domain='policy', business_problem='test')
segs = calibrate(spec)
print(segs)
"
```

### Path Wiring

The standalone repo (`/PopScale/`) uses per-file `sys.path.insert()` hacks to find the Persona Generator. These are guarded with `if str(_PG_ROOT) not in sys.path` but they do add `../Persona Generator` to `sys.path` at import time. The platform copy (`simulatte-platform/popscale/`) replaces all these with a single `_pg_bridge.py` module imported in `__init__.py`.

Two `conftest.py` files exist: one at the repo root and one in `tests/`. Both inject the same paths. The `pytest.ini` sets `pythonpath = .` which means the `tests/` conftest duplication is largely redundant for pytest runs.

---

## Integration with Other Simulatte Products

### Persona Generator (PG)
PopScale is a **client** of PG. It imports from `src.*` (PG's namespace) and calls:
- `invoke_persona_generator(brief)` — generates a batch of PersonaRecords
- `run_loop(stimulus, persona, decision_scenario, tier)` — runs the cognitive loop
- `run_social_loop(...)` — runs multi-turn social network simulation
- `CostEstimator` — for simulation phase cost estimation
- `PersonaRecord`, `DemographicAnchor`, `Attribute`, etc. — PG schema types
- `DerivedInsightsComputer`, `TendencyEstimator` — used in VariantGenerator

**Never modify PG from PopScale.** The seam is `integration/run_scenario.py` and `generation/calibrated_generator.py`.

### Niobe
Niobe is the primary downstream consumer of PopScale. It calls `run_study()` directly from `popscale.study.study_runner`. The typical Niobe usage pattern:
- Constructs a `StudyConfig` from a `NiobeStudyRequest`
- Sets `use_seeded_generation=True` for `n_personas >= 500`
- Uses `budget_cap_usd` to guard against runaway costs
- Reads `StudyResult.report.to_dict()` and `StudyResult.report.to_markdown()` for output

### Morpheus (Research Brain)
Morpheus calls PopScale as part of the Simulatte research pipeline for population-level hypothesis validation. It passes structured scenario bundles (`ScenarioBundle`) and uses the analytics output (`PopScaleReport`) to compare segment responses against research hypotheses.

### White Rabbit Dashboard
Receives `StudyResult.to_dict()` JSON for visualisation. The `{run_id}_study.json` and `{run_id}_report.md` files written by `save_study_result()` are the canonical interchange format.

### SENTINEL Testing Agent
Sentinel tests PopScale in Ring 2–4 of its 7-ring testing architecture. It exercises `calibrate()`, `run_study()`, and the analytics layer via non-live (mocked) tests in `test_week1_integration.py` through `test_week10_study.py`.

---

## Sharp Edges

1. **The `_ALIASES` dict in `get_profile()` has a duplicate key collision**: `"ga"` maps to both `"goa"` and `"georgia"` (in that order), and `"uk"` maps to both `"uttarakhand"` and `"united_kingdom"`. Python dicts keep the last assignment, so `"ga"` resolves to `"georgia"` and `"uk"` resolves to `"united_kingdom"`. The first definitions are silently clobbered. Use explicit codes (`"goa"`, `"uttarakhand"`) to avoid surprises.

2. **`run_study_sync()` and `run_calibrated_generation_sync()` must not be called from inside an active asyncio event loop.** They use `asyncio.run()` internally. In Jupyter notebooks (which have a running loop), always use `await run_study(config)` directly.

3. **`_PG_MAX_PER_BRIEF = 10` in `calibrated_generator.py`** caps each PG brief at 10 personas. A 500-persona cohort produces 50 briefs. Each runs within `_PG_BRIEF_TIMEOUT_S = 600s`. For large stratified cohorts this means up to `3 concurrent × many sequential` PG invocations — expect generation to take 10–30 minutes for n=500+.

4. **Seeded generation's `object.__setattr__` hack**: `seeded_calibrated_generator.py` annotates the `CohortGenerationResult` dataclass with `_seeded_metadata` via `object.__setattr__()` after construction because `CohortGenerationResult` has no `metadata` field. This works but is not type-safe and silently drops if the result is copied or rebuilt. Callers must access `result._seeded_metadata` directly.

5. **`apply_environment()` merge order**: `{**env.scenario_environment, **scenario.environment}` — caller-set values win. But if you rely on a preset providing defaults, setting any environment key in your Scenario will override only that key. Passing `environment={}` to Scenario means presets provide all context. Passing `environment={"region": "custom"}` will override only region but inherit the rest from the preset.

6. **Cost actuals equal estimates until token tracking lands**: `SimulationResult.cost_actual_usd` is set to `cost_estimate_usd` in `runner.py` (see the comment: "actuals = estimate until Week 4 token tracking"). Do not rely on `cost_actual_usd` for accurate billing; it is a per-tier-per-persona estimate.

7. **`ResponseCache` key includes scenario context verbatim**: changing even a single character in `scenario.context` invalidates all cache entries for that scenario. When iterating on context wording during a study, disable cache (`use_cache=False`) or the study will re-run all personas from scratch.

8. **Wilson CI in `distributions.py` uses `z=1.96` (95%) hardcoded**: there is no way to request a different confidence level through the public API. All CI widths in reports are 95% Wilson intervals regardless of study size.

9. **Variant city pool is India-specific**: `_CITY_POOL` in `variant_generator.py` contains only Indian metros, tier-2, and tier-3 cities. For non-India geographies (`us_west`, `united_kingdom`, etc.), `_rotate_city()` falls back to `current_city` because `urban_tier` values like `"metro"` still hit the India pool. Non-India variant personas will have Indian city names unless `_CITY_POOL` is extended.

10. **`stratify_by_religion` is silently downgraded for non-India profiles**: if `supports_religion_stratification=False` on a `DemographicProfile` (all USA, UK, Europe profiles), the calibrator logs an INFO-level message and substitutes income stratification. The caller gets no exception — only a log line. Check logs if your non-India cohort appears income-stratified when you expected religion stratification.

11. **Dual `conftest.py` files**: both `conftest.py` (repo root) and `tests/conftest.py` perform identical `sys.path` mutations. This is safe but redundant. The root conftest handles pytest collection at the repo level; the tests-level conftest handles direct test runs inside `tests/`. Do not remove either without verifying your pytest invocation context.

12. **`_pg_bridge.py` only exists in the platform copy**: the standalone repo (`/PopScale/`) uses per-module `sys.path.insert()` patterns instead. If you copy modules from the platform copy to the standalone repo without adjusting paths, imports will fail silently when PG is not at the expected relative location.
