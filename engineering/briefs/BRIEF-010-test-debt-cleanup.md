# BRIEF-010 — Test Debt Cleanup

| Field | Value |
|---|---|
| Sprint | Construct Phase 2 / cleanup track (parallel to Phase 1) |
| Owner | **Codex** (or Cursor — flexible) |
| Estimate | 1–1.5 days |
| Branch | `cleanup/brief-010-test-debt` |
| Status | 🟢 Open · LOW priority (does not block Phase 1) |
| Depends on | nothing |
| Blocks | nothing |

---

## Background

Phase 0's BRIEF-009 acceptance run uncovered pre-existing technical debt in the test suite that's been hiding under the surface for some time. None of it relates to Phase 0 work — these are failures from earlier sprints that nobody had time to chase down. We're tracking them now as a single cleanup brief so they don't accumulate further and don't keep blocking future acceptance runs.

This is **not urgent**. Phase 1 (cost overhaul) can run in parallel. The risk we're managing is "test suite credibility erodes if it has 21 known-red tests forever."

---

## What's broken (as of 2026-04-26 baseline)

### A) persona-generator: sklearn missing

```
ModuleNotFoundError: No module named 'sklearn'
```

Some test fixture imports `sklearn`. Fix is one of:
1. Add `scikit-learn` to dev dependencies in `pyproject.toml` / `requirements-dev.txt`
2. Mark the affected test(s) `pytest.mark.skipif(not has_sklearn)` if sklearn isn't actually needed
3. Refactor to remove the sklearn dependency if it crept in accidentally

### B) popscale: 21 failing tests across 4 files

| File | Failures | Likely cause |
|---|---|---|
| `tests/test_seeded_generation.py` | 17 | NiobeStudyRequest schema drift (defaults changed?), seeded-mode cost estimate refactor |
| `tests/test_week5_social.py` | 2 | `build_full_mesh` / `build_random_encounter` social network helpers — API drift |
| `tests/test_geographies.py` | 1 | `test_india_profiles_route_to_india` — likely profile registry change |
| `tests/test_week7_calibration.py` | 1 | `test_hindu_segment_no_religiosity_override` — calibration logic change |

Full failure list: see `engineering/construct_phase_2/PHASE_0_ACCEPTANCE_REPORT.md` baseline section once written.

---

## Goal

For each failing test, do **one** of:

1. **Fix** — if the test is correct and the code regressed, fix the code
2. **Update** — if the code is correct and the test is stale (e.g., NiobeStudyRequest defaults legitimately changed), update the test to match
3. **Delete** — if the test is testing a feature that no longer exists, delete the test
4. **Skip with reason** — if the test should run but blockers exist (env-dependent), mark `@pytest.mark.skip(reason="...")` with a tracking issue

Document the disposition for each test in the PR description.

---

## Acceptance criteria

1. After this brief: `python3 -m pytest -q` returns 0 failures (or only justifiable skips with reasons) in both popscale and persona-generator.
2. Each fixed test has a 1-line note in the commit message explaining what was wrong.
3. No fix removes test coverage silently — if a test is deleted, the PR description explains why.
4. CI test commands documented in `engineering/construct_phase_2/CORE_SPEC.md` §10 (new section).

---

## Out-of-scope

- Adding new tests for uncovered code — that's per-feature, not cleanup
- Performance / flakiness optimisation
- Refactoring the test architecture (use what's there)

---

## Why this is low priority

These tests have been red for some time without breaking production. They're warnings, not bombs. Phase 1 (cost overhaul) is far more valuable per engineer-day. We do this when there's slack, or when one of the failing modules is touched by Phase 1 work and we're already in there.

**If a Phase 1 brief touches one of the affected files, fold the relevant fix into that brief instead of doing it standalone.**

---

## Reference

- BRIEF-009 acceptance report (will document the baseline)
- `PRINCIPLES.md` P10 (leave artifacts, not dependencies — including a clean test suite)
