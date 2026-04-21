# ADR-001: Treat the Persona Generator as an External Dependency, Not a Sub-Package

**Status**: Accepted  
**Date**: 2026-04-18 (reconstructed from codebase)  
**Deciders**: Simulatte Tech Lead  

---

## Context

PopScale needs to run Persona Generator (PG) cognitive loops, use PG's `PersonaRecord` schema, call `invoke_persona_generator()`, and access PG's `DerivedInsightsComputer` and `TendencyEstimator` in the VariantGenerator. There are two broad approaches to structuring this dependency:

**Option A — Copy PG modules into PopScale**: Vendor PG's `src/` into `popscale/pg/` and import from there. PopScale becomes self-contained.

**Option B — Import PG directly via sys.path**: Keep PG as a sibling directory and add it to `sys.path` at runtime. PopScale imports from `src.*` (PG's own namespace convention).

**Option C — Install PG as a proper pip package**: Publish PG to PyPI or a private registry; list it as a dependency in `pyproject.toml`.

---

## Decision

**Option B** was chosen: import PG via `sys.path` manipulation at module import time. Each module that needs PG resolves `../Persona Generator` relative to its own `__file__` and inserts it into `sys.path`.

The platform copy (`simulatte-platform/popscale/`) centralises this in a single `_pg_bridge.py` module that is imported in `__init__.py` and supports `PG_ROOT` environment variable override as well as a sibling-directory convention for deployed environments.

---

## Rationale

1. **PG is under active parallel development.** Vendoring would require constant re-syncing and would create a painful merge surface. Direct import means PG and PopScale always run against the same live codebase.

2. **PG is not packaged for distribution.** Option C requires PG to have a stable `pyproject.toml`, semantic versioning, and a release process. At the time of this decision, PG is an internal research tool evolving rapidly.

3. **The `src.*` namespace is PG's convention.** PG's own tests and modules use `from src.X import Y`. PopScale must use the same namespace to avoid requiring changes inside PG.

4. **No circular imports.** PopScale imports from PG but PG never imports from PopScale. The dependency is strictly one-directional.

---

## Consequences

### Positive
- PopScale always has access to the latest PG version without a release cycle.
- No vendoring maintenance burden.
- The `_pg_bridge.py` pattern in the platform copy is clean and supports CI/CD via `PG_ROOT`.

### Negative
- **Scattered `sys.path` mutations** in every module that needs PG (standalone repo pattern). If PG is not present at the expected relative path, the error appears deep inside a module import rather than at package initialisation.
- **No version pinning.** A breaking change in PG silently breaks PopScale with no easy rollback. There is no `requirements-pg.txt` or lockfile.
- **Not installable standalone.** `pip install populatte-popscale` would not work because PG is not listed as an installable dependency.
- **IDE support is degraded.** Type checkers cannot follow `sys.path.insert()` to resolve `src.*` imports; all PG-sourced types appear as `Any` or are unresolved.

### Mitigations
- The `_pg_bridge.py` module (platform copy) centralises the path resolution and provides clear error messages when PG is not found.
- Integration tests (`test_week1_integration.py` through `test_week10_study.py`) serve as compatibility gates — a breaking PG change will surface in test failures.
- The `SPEC_SEEDED_GENERATION.md` section "Integration Points" documents that Niobe and PopScale callers are unchanged when PG changes internally.

---

## Notes

When PG is stabilised and versioned, **Option C** (proper pip packaging) should be revisited. The `_pg_bridge.py` approach is designed to make that transition easy: swap `sys.path.insert()` for `import pg_package` in one place without touching any other module.
