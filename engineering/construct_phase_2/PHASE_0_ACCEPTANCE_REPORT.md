# Phase 0 Acceptance Report (BRIEF-009)

Date: 2026-04-26  
Owner: Codex  
Paths used:
- `/Users/admin/Documents/Simulatte Projects/PopScale`
- `/Users/admin/Documents/Simulatte Projects/Persona Generator`

## Revised pre-check gate (2026-04-26)

### PopScale (Phase 0 modules only)
- Command:
  - `python3 -m pytest -q popscale/config/tests/ popscale/scenario/tests/ popscale/observability/tests/ benchmarks/wb_2026/constituency/tests/ --no-header --tb=no`
- Observed:
  - `13 passed in 4.48s`
- Verdict: **PASS**

### Persona Generator (credit monitor only)
- Command:
  - `python3 -m pytest -q tests/test_credit_monitor.py --no-header --tb=no`
- Observed:
  - `5 passed in 0.55s`
- Verdict: **PASS**

Gate result: **18/18 green — proceed to forced-failure tests.**

---

## Known baseline (non-blocking, tracked in BRIEF-010)

These failures are pre-existing and outside Phase 0 scope; recorded verbatim per revised brief:

- `ERROR tests/test_onboarding_workflow.py` with `ModuleNotFoundError: No module named 'sklearn'` (Persona Generator full suite collection)
- `FAILED tests/test_geographies.py::TestPgLocationRouting::test_india_profiles_route_to_india`
- `FAILED tests/test_seeded_generation.py::TestNiobeStudyRequestSeeded::test_defaults_use_seeded_generation_false`
- `FAILED tests/test_seeded_generation.py::TestNiobeStudyRequestSeeded::test_defaults_seed_count_200`
- `FAILED tests/test_seeded_generation.py::TestNiobeStudyRequestSeeded::test_defaults_seed_tier_deep`
- `FAILED tests/test_seeded_generation.py::TestNiobeStudyRequestSeeded::test_can_enable_seeded_generation`
- `FAILED tests/test_seeded_generation.py::TestNiobeStudyRequestSeeded::test_raises_if_seed_count_gt_n_personas`
- `FAILED tests/test_seeded_generation.py::TestNiobeStudyRequestSeeded::test_raises_if_seed_count_zero`
- `FAILED tests/test_seeded_generation.py::TestNiobeStudyRequestSeeded::test_raises_on_invalid_seed_tier`
- `FAILED tests/test_seeded_generation.py::TestNiobeStudyRequestSeeded::test_summary_includes_seeded_flag`
- `FAILED tests/test_seeded_generation.py::TestGenerationCostEstimate::test_standard_mode_returns_mode_standard`
- `FAILED tests/test_seeded_generation.py::TestGenerationCostEstimate::test_seeded_mode_returns_mode_seeded`
- `FAILED tests/test_seeded_generation.py::TestGenerationCostEstimate::test_seeded_total_less_than_standard`
- `FAILED tests/test_seeded_generation.py::TestGenerationCostEstimate::test_seeded_savings_pct_positive`
- `FAILED tests/test_seeded_generation.py::TestGenerationCostEstimate::test_standard_savings_pct_zero`
- `FAILED tests/test_seeded_generation.py::TestGenerationCostEstimate::test_seeded_formula`
- `FAILED tests/test_seeded_generation.py::TestNiobeRunnerSeededWiring::test_seeded_true_passes_through`
- `FAILED tests/test_seeded_generation.py::TestNiobeRunnerSeededWiring::test_seed_tier_passes_through`
- `FAILED tests/test_seeded_generation.py::TestNiobeRunnerSeededWiring::test_default_seed_count_passes_through`
- `FAILED tests/test_week5_social.py::TestSocialRunnerModule::test_build_full_mesh_returns_network`
- `FAILED tests/test_week5_social.py::TestSocialRunnerModule::test_build_random_encounter_returns_network`
- `FAILED tests/test_week7_calibration.py::TestReligiousStratification::test_hindu_segment_no_religiosity_override`

---

## Test A — Pre-flight rejects relative path

- Command:
  - `python3 -m benchmarks.wb_2026.constituency.wb_2026_constituency_benchmark --manifesto both --sensitivity-baseline results/wb_2026_constituency_20260422_034351.json --budget-ceiling 25`
- Observed behavior:
  - CLI rejected relative path before run start.
  - Exit code: `2`.
  - Error included fix guidance: `try Path(p).resolve()`.
- Output excerpt:
  - `error: argument --sensitivity-baseline: path must be absolute, got: 'results/...json' — try Path(p).resolve()`
- Verdict: **PASS**
- Notes:
  - No benchmark execution started; zero API spend for this test.

## Test B — Credit-low halts cleanly with checkpoint

- Command (brief-specified):
  - `SIMULATTE_CREDIT_BUFFER_USD=99999 SIMULATTE_NTFY_TOPIC=simulatte-test-acceptance python3 -m benchmarks.wb_2026.constituency.wb_2026_constituency_benchmark --manifesto both --sensitivity-baseline /Users/admin/Documents/Simulatte Projects/PopScale/benchmarks/wb_2026/constituency/results/wb_2026_constituency_20260422_034351.json --budget-ceiling 25`
- Observed behavior:
  - Run halted at pre-flight budget check first (`Estimated cost $73.50 exceeds --budget-ceiling $25.00`), so credit-low path did not execute.
  - Exit code: `1`.
- Follow-up command (to isolate credit-low path):
  - same command with `--budget-ceiling 200`
- Follow-up observed behavior:
  - Pre-flight passed, then run aborted before clusters with:
  - `RuntimeError: Anthropic API key missing for credit monitor (set ANTHROPIC_ADMIN_API_KEY or ANTHROPIC_API_KEY).`
  - No `SystemExit(2)` credit-low halt, no checkpoint evidence from this run.
- Verdict: **FAIL**
- Notes:
  - Failure is loud (not silent), but does not satisfy BRIEF-009 pass criteria for credit-low contract validation.
  - Per instruction, stopped after first failing test; C and D not run.

## Test C — Resume from partial

- Command: Not run (stopped after Test B failure).
- Verdict: **BLOCKED (NOT RUN)**.

## Test D — Dashboard live (bonus)

- Command: Not run (stopped after Test B failure).
- Verdict: **BLOCKED (NOT RUN)**.

---

## Total cost spent

`$0.00` observed (A/B aborted before any cluster simulation/API work began).

## Verdict

**Phase 0 acceptance — blocked on Test B (credit-low halt path not validated).**
