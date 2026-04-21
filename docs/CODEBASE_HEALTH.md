# PopScale — Codebase Health Report

**Date**: 2026-04-18  
**Scope**: `/Users/admin/Documents/Simulatte Projects/PopScale/` (authoritative source)  
**Reviewer**: Sentinel automated health sweep  
**Python runtime in use**: CPython 3.14 (dev) — `__pycache__` files confirm `cpython-314`

---

## Executive Summary

PopScale is a well-structured, purpose-built library with clear module boundaries and good internal documentation. The docstring quality is high throughout. The seeded generation architecture (seed + Haiku variant expansion) is a technically sound design that delivers ~97% cost reduction for large cohort runs.

The main health concerns are: (1) two silent alias collisions in the geography lookup dict that return wrong profiles for `"ga"` and `"uk"`; (2) a metadata attachment pattern that bypasses the type system; (3) cost actuals that equal estimates (acknowledged as a TODO); (4) a variant city pool that only covers India; and (5) import-time `sys.path` mutations scattered across every module rather than centralised. None of these are logic bugs in the simulation or statistical models.

The test suite covers the public API comprehensively in 15 files organised by development sprint. However, all tests that touch LLM calls are gated behind the `live` marker, meaning the standard `pytest -m "not live"` run exercises only the deterministic layers.

---

## Findings

### 🔴 HIGH

#### H-1 — Duplicate alias keys in `get_profile()` cause wrong geography lookups
**File**: `popscale/calibration/profiles.py`, lines 1395–1501  
**Detail**: The `_ALIASES` local dict is constructed with literal duplicate keys:
- `"ga"` is defined as `"goa"` (line ~1437) then overwritten as `"georgia"` (line ~1465). Callers of `get_profile("ga")` always receive the Georgia (US) profile, never Goa.
- `"uk"` is defined as `"uttarakhand"` (line ~1432) then overwritten as `"united_kingdom"` (line ~1481). Callers of `get_profile("uk")` always receive the United Kingdom profile, never Uttarakhand.

The Uttarakhand collision is particularly problematic because `"uk"` is a natural short code for Uttarakhand in Indian research contexts. Any study that used `state="uk"` intending Uttarakhand instead ran against the UK demographic profile.

**Fix**: Remove the first (overwritten) alias definition for each collision. Use `"ga_india"` as an alias for Goa if needed, and `"ua"` or `"utt"` for Uttarakhand. This is a safe cosmetic fix (alias string change only — no simulation logic).

---

### 🟠 MEDIUM

#### M-1 — `object.__setattr__` hack attaches untyped metadata to a frozen dataclass
**File**: `popscale/generation/seeded_calibrated_generator.py`, lines 315–321  
**Detail**: After constructing a `CohortGenerationResult`, the seeded generator attaches a `_seeded_metadata` dict via `object.__setattr__(result, "_seeded_metadata", {...})`. This bypasses the dataclass field system, is invisible to type checkers, and is lost if the result is copied with `dataclasses.replace()` or reconstructed from `to_dict()`. Callers must know to access `result._seeded_metadata` directly.  
**Recommendation**: Add an optional `metadata: dict = field(default_factory=dict)` field to `CohortGenerationResult` in `calibrated_generator.py`. Populate it in the seeded path. This is a schema addition, not a logic change.

#### M-2 — Variant city pool is India-only; non-India variants receive Indian city names
**File**: `popscale/generation/variant_generator.py`, lines 107–112  
**Detail**: `_CITY_POOL` contains only Indian cities. For non-India `PersonaRecord` objects (US, UK, EU profiles), `_rotate_city()` cannot find alternatives in the pool and silently returns the seed's original city. This means non-India variant personas either keep the seed's city or get an Indian city name depending on how `urban_tier` matches the pool keys.  
**Recommendation**: Extend `_CITY_POOL` with US, UK, and EU city pools keyed to the same `urban_tier` values. This is a data addition, not a logic change.

#### M-3 — `sys.path` mutations at module import time scattered across every module
**File**: All modules in `orchestrator/`, `generation/`, `integration/`, `social/`, `schema/`, `utils/`  
**Detail**: Every module that imports from PG performs `sys.path.insert(0, str(_PG_ROOT))` at module level. This is idempotent (guarded by `if str(_PG_ROOT) not in sys.path`) but means: (a) the path is inserted on every import of any PopScale module; (b) if PG is not found, the import error happens at a surprising line inside the submodule, not at the package entry point; (c) it makes the dependency on the Persona Generator invisible at package level.

The `simulatte-platform/popscale/` copy already solves this with `_pg_bridge.py` imported once in `__init__.py`. That solution should be backported.  
**Recommendation**: Document in CLAUDE.md (done). Backport `_pg_bridge.py` to the standalone repo when doing a planned refactor.

#### M-4 — Cost actuals equal cost estimates for all simulation runs
**File**: `popscale/orchestrator/runner.py`, line 277  
**Detail**: `cost_actual_usd=cost_estimate.sim_cost_usd` — actuals are explicitly set equal to the pre-run estimate. The comment says "actuals = estimate until Week 4 token tracking". This affects `StudyResult.total_cost_usd` and any cost reporting downstream.  
**Recommendation**: Track this as a known limitation in monitoring dashboards. Do not use `cost_actual_usd` for billing reconciliation until token-level tracking is implemented.

#### M-5 — `load_cohort_file()` imports `logging` inside the function body
**File**: `popscale/utils/persona_adapter.py`, lines 291–292  
**Detail**: `import logging` and `logger = logging.getLogger(__name__)` appear inside `load_cohort_file()` rather than at module level. The module-level `_PG_ROOT` sys.path block also appears before `from src.schema.persona import PersonaRecord`, which means the logger is not available at the module scope for `adapt_persona_dict()` (which also calls `logger.warning`).  
**Status**: `adapt_persona_dict()` actually uses the module-level `logger` defined at the bottom of the sys.path block — `load_cohort_file()` just defines a redundant local one. This is confusing but not a bug.  
**Fix**: Move `import logging` and `logger = logging.getLogger(__name__)` out of `load_cohort_file()` to module scope. Low-risk cosmetic fix applied (see Changes Applied section).

---

### 🟡 LOW

#### L-1 — `_ALIASES` dict is constructed as a local variable inside `get_profile()` on every call
**File**: `popscale/calibration/profiles.py`, line 1395  
**Detail**: The `_ALIASES` dict (with ~80 entries) is recreated on every call to `get_profile()`. For hot paths (called per-segment during calibration), this creates unnecessary allocation. Since it is purely static data, it should be a module-level constant.  
**Recommendation**: Move `_ALIASES` to module scope. Low-risk refactor — no logic change.

#### L-2 — `Optional` import retained after `from __future__ import annotations` makes it unnecessary
**File**: Multiple files (`calibration/calibrator.py`, `calibration/population_spec.py`, etc.)  
**Detail**: Several files import `Optional` from `typing` but use `from __future__ import annotations` at the top, which makes all annotations strings and renders `Optional` unnecessary for annotation purposes. `Optional[str]` in annotations can simply be written as `str | None` (PEP 604).  
**Recommendation**: Replace `Optional[X]` with `X | None` in annotations as a quality pass. The import of `Optional` can then be removed. Do not apply until all files in the package are updated together to avoid partial inconsistency.

#### L-3 — Fallback response uses `import dataclasses` inside the function
**File**: `popscale/integration/run_scenario.py`, lines 100–101  
**Detail**: The `run_scenario()` function imports `dataclasses` inside the except/timeout handler rather than at module level. This is a common anti-pattern that adds latency on the error path and hides the dependency.  
**Fix**: Move `import dataclasses` to module scope. Low-risk cosmetic fix applied (see Changes Applied section).

#### L-4 — `_fallback_response()` imports from sibling modules inside the function body
**File**: `popscale/integration/run_scenario.py`, lines 184–186  
**Detail**: `from ..domain.framing import _estimate_prior, SEGMENT_LABELS` and `from ..schema.population_response import DomainSignals, _extract_domain_signals` are imported inside `_fallback_response()`. These are circular-import avoidance patterns but the actual circular dependency does not exist here.  
**Recommendation**: Move to module-level imports. Low-risk cosmetic fix (not applied — requires verifying no circular import).

#### L-5 — `_parse_narrative_response` uses bare variable name `l` (shadows built-in)
**File**: `popscale/generation/variant_generator.py`, line 701  
**Detail**: `lines = [l.strip() for l in raw.split("\n") if l.strip()]` — `l` is a single-character name that is easy to misread and is a shadow of the `l` in other comprehensions. PEP 8 discourages single-character names except for loop indices.  
**Fix**: Rename `l` to `line`. Applied (see Changes Applied).

#### L-6 — `ScenarioBundle.shared_context` docstring has a minor inaccuracy
**File**: `popscale/scenario/model.py`, line 170  
**Detail**: The docstring says "Prepended to each scenario's own context." but the implementation in `renderer.py` may not actually prepend it — this needs verification. Mark as documentation debt.

#### L-7 — Benchmark result JSON files committed to repo
**File**: `benchmarks/delhi_2025/results/` (6 files), `benchmarks/us_2024_swing/results/` (7 files)  
**Detail**: Benchmark run results (JSON) are committed. This is fine for reproducibility but means the repo will slowly accumulate large binary-ish result files. Recommend adding `benchmarks/*/results/*.json` to `.gitignore` and storing benchmark baselines separately.

#### L-8 — `__pycache__` directories are not gitignored
**File**: `.gitignore`  
**Detail**: `__pycache__/` directories are present in the tracked file tree based on the directory listing. Standard Python `.gitignore` should exclude these. Not a functional issue.

---

### 🔵 INFO

#### I-1 — Two copies of the codebase (standalone vs. platform) with diverging features
The standalone `/PopScale/` repo has `seeded_calibrated_generator.py`, `variant_generator.py`, `parity_validator.py`, `seed_calibrator.py`, `benchmarks/`, and `SPEC_SEEDED_GENERATION.md` that are absent from `simulatte-platform/popscale/`. The platform copy has `_pg_bridge.py` which improves the path resolution story. These two should be kept in sync or merged.

#### I-2 — Test files named `test_weekN_*` encode sprint history
The 10 weekly test files are named after development sprints (Week 1–10). This is fine for traceability but makes it harder to find tests by feature. Consider adding a `tests/README.md` mapping test files to features.

#### I-3 — No `pyproject.toml` in the standalone repo
The standalone repo has `requirements.txt` but no `pyproject.toml`. The platform copy has a `pyproject.toml`. For installability and reproducible builds, the standalone repo should adopt `pyproject.toml`.

#### I-4 — Cost estimates in `study_runner.py` are hardcoded at file scope
**File**: `popscale/study/study_runner.py`, lines 244–253  
`_GEN_COST_PER_PERSONA` and `_SIM_COST_PER_PERSONA` are hardcoded dicts. These will drift from PG's `CostEstimator` as pricing changes. The simulation cost estimate already delegates to `CostEstimator`; the generation estimate should too.

#### I-5 — `numpy` is listed as a dependency but not imported in any source file
`requirements.txt` lists `numpy>=2.0.0` but a codebase search finds no `import numpy` in `popscale/`. All statistical calculations (Wilson CI, Cramér's V, Eta²) are implemented in pure Python. If numpy is a transitive dependency (via PG), it should be removed from PopScale's own `requirements.txt` to keep the dependency footprint minimal.

---

## What Is Working Well

- **Docstring quality**: Every public module, class, and function has a docstring. Module-level docstrings include usage examples. This is well above the median for Python libraries.
- **Defensive programming**: `calibrate()`, `run_study()`, and `run_population_scenario()` all validate inputs eagerly and raise descriptive exceptions. The circuit breaker and fallback response patterns ensure large population runs never silently lose personas.
- **Pure Python analytics**: Cramér's V, Eta², Wilson CI, and the segmentation logic are all implemented without numpy/scipy. This makes the analytics layer zero-dependency and easily testable.
- **Seeded generation architecture**: The two-pass seed + variant design is well-specified (see `SPEC_SEEDED_GENERATION.md`) and the implementation closely matches the spec. The parity validator gives an automated quality gate.
- **Separation of concerns**: PopScale does not re-implement anything that belongs to the Persona Generator. The seam between the two systems is narrow and explicit: `integration/run_scenario.py` + `generation/calibrated_generator.py`.
- **Geography coverage**: 46 demographic profiles with census-sourced data, organised into India/USA/UK/Europe regions with explicit data source attribution. The alias system supports natural lookup (city names, abbreviations).
- **Schema design**: `PopulationResponse` and `SimulationResult` are flat dataclasses that are easy to serialise. The `to_dict()` / `to_markdown()` pattern on `PopScaleReport` is consistent and consumer-friendly.
- **Test marker discipline**: The `live` marker correctly gates all LLM-calling tests. The standard `pytest -m "not live"` run is fast and deterministic.

---

## Robustness Score Table

| Dimension | Score | Notes |
|---|---|---|
| **Documentation** | 9/10 | Excellent docstrings; missing only inline comments on complex statistical code |
| **Error handling** | 8/10 | Fallback responses, circuit breaker, budget guards — all present; cost actuals are estimates |
| **Type annotations** | 7/10 | `from __future__ import annotations` used; some `Any` types and missing return annotations in private helpers |
| **Test coverage** | 7/10 | 15 test files; good breadth but depth of non-live tests is limited (mocked PG responses) |
| **Dependency hygiene** | 6/10 | Scattered `sys.path` hacks; numpy listed but unused; no `pyproject.toml` in standalone |
| **Geographic correctness** | 8/10 | Census-sourced profiles with data citations; alias collision for `"ga"` / `"uk"` is the main gap |
| **API stability** | 8/10 | `__all__` in `__init__.py` is explicit and complete; internal `_` naming is consistent |
| **Performance** | 7/10 | `_ALIASES` rebuilt per call; sharding + semaphore design is appropriate for scale |
| **Security** | 9/10 | No credentials in code; no file writes outside of configured `output_dir` and `cache_path` |
| **Overall** | **7.7/10** | Solid foundation; main gaps are tooling/hygiene rather than correctness |

---

## Recommended Next Actions

### Immediate (before next production run)
1. **Fix the `"ga"` and `"uk"` alias collisions** (H-1). Any study run with `state="ga"` or `state="uk"` that intended Goa or Uttarakhand used wrong demographic data.

### Short-term (next sprint)
2. Add `metadata: dict` field to `CohortGenerationResult` and remove the `object.__setattr__` hack (M-1).
3. Backport `_pg_bridge.py` from the platform copy to the standalone repo (M-3).
4. Move `_ALIASES` to module scope in `profiles.py` (L-1).
5. Add `pyproject.toml` to the standalone repo (I-3).
6. Remove `numpy` from `requirements.txt` or add a comment explaining the transitive dependency (I-5).

### Medium-term
7. Extend `_CITY_POOL` with US/UK/EU city data for non-India variant generation (M-2).
8. Implement token-level cost tracking to replace estimate-equals-actual (M-4).
9. Migrate `Optional[X]` annotations to `X | None` (L-2).
10. Add `benchmarks/*/results/*.json` to `.gitignore` (L-7).
