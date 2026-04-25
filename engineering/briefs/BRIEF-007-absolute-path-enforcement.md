# BRIEF-007 — Absolute Path Enforcement

| Field | Value |
|---|---|
| Sprint | Construct Phase 2 / Phase 0 |
| Owner | **Cursor** |
| Estimate | 0.5 day |
| Branch | `phase-0/brief-007-absolute-path-enforcement` |
| Status | 🟢 Open |
| Depends on | BRIEF-006 (validator framework) — coordinate but can ship independently |
| Blocks | nothing |

---

## Background

`CORE_SPEC.md` §4.1 declares: *"Hard rule: All paths in Scenario must be absolute. Pre-flight validator rejects relative paths."*

BRIEF-006 introduces the validator. This brief makes the rule **enforced everywhere paths cross a boundary** — so even programmatic use of the engine (not just CLI) cannot pass a relative path.

The Run 7 sensitivity bug was a relative path. We never want a relative path to reach the file-loading layer again.

---

## Goal

Add path-normalization at every boundary where a file path enters the engine. Reject relative paths with a clear error. Provide a CI test that catches regressions.

---

## Files in scope

```
simulatte-workspace/popscale/
├── popscale/
│   ├── scenario/
│   │   ├── model.py                          # Scenario.__post_init__: normalize paths
│   │   └── tests/test_scenario_paths.py      # NEW
│   ├── integration/
│   │   └── run_scenario.py                   # validate any path inputs
│   └── benchmarks/wb_2026/constituency/
│       └── wb_2026_constituency_benchmark.py # CLI args go through Path.resolve()
└── persona-generator/
    └── src/                                   # any path inputs in PG also normalized
```

---

## Acceptance criteria

1. **Boundary normalization** — every place a file/directory path enters the engine from outside (CLI args, function parameters, config files), the path is:
   - Rejected if relative (with `ValueError("path must be absolute, got: X — try Path(X).resolve()")`)
   - Normalized via `Path(p).resolve()` on the way in (collapses `..`, follows symlinks)

2. **Scenario class** — `Scenario` (or its dataclass equivalent) gains a `__post_init__` that normalizes path fields. Any field declared as `AbsolutePath` (a NewType or `pathlib.Path` with constraint) is enforced.

3. **CLI hardening** — every `argparse` argument that takes a path uses a custom `type=AbsolutePath` action that resolves and validates immediately.

4. **Linting / CI** — add a `pytest` integration test that:
   - Constructs a Scenario with a relative path → asserts ValueError
   - Constructs a Scenario with an absolute path → succeeds
   - Calls the benchmark CLI with `--sensitivity-baseline relative/path.json` → asserts non-zero exit with clear message

5. **Backward compatibility** — existing absolute paths everywhere continue to work without change. Only relative paths are rejected.

6. **Tests** in `test_scenario_paths.py`:
   - Relative path rejected with helpful error
   - Absolute path normalized (e.g., `/x/y/../z` becomes `/x/z`)
   - Path with `~` expanded to absolute home-relative form
   - Symlink resolution

---

## Implementation notes

- Define `AbsolutePath = NewType('AbsolutePath', Path)` and a constructor:
  ```python
  def make_absolute_path(p: str | Path) -> AbsolutePath:
      path = Path(p).expanduser()
      if not path.is_absolute():
          raise ValueError(f"path must be absolute, got: {p!r} — try Path(p).resolve()")
      return AbsolutePath(path.resolve())
  ```
- The error message must always suggest the fix. P3: fail loud, but help.
- For argparse:
  ```python
  parser.add_argument('--sensitivity-baseline', type=make_absolute_path, ...)
  ```
- Don't aggressively rewrite all internal paths. Boundaries only — once a path is inside the engine, it stays a `Path` and is trusted.

---

## Deliverable format

- Summary of approach (1 paragraph)
- List of every entry point that now enforces absolute paths (table)
- Sample error message when a relative path is passed
- Test output (pass/fail counts)
- A `git grep` showing no remaining `.json` or `.csv` literal relative-path strings in CLI defaults

---

## Out-of-scope

- Refactoring internal path handling (only boundaries matter).
- Documenting paths in user-facing docs (covered separately).

---

## Reference

- `PRINCIPLES.md` P3
- `CORE_SPEC.md` §4.1
- BRIEF-006 (the validator that calls into this enforcement)
