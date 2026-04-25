# BRIEF-006 — Pre-flight Config Validator

| Field | Value |
|---|---|
| Sprint | Construct Phase 2 / Phase 0 |
| Owner | **Cursor** |
| Estimate | 0.5 day |
| Branch | `phase-0/brief-006-preflight-validator` |
| Status | 🟢 Open |
| Depends on | — |
| Blocks | nothing (parallel-safe) |

---

## Background

The WB 2026 manifesto study printed a sensitivity table with corrupted Swng(T) values because the `--sensitivity-baseline` was a relative path:

```
FileNotFoundError: 'results/wb_2026_constituency_20260422_034351.json'
```

The benchmark caught the error and silently fell back to an internal default — producing a table that looked correct but wasn't. **This is exactly the silent-degraded-behavior failure mode `PRINCIPLES.md` P3 forbids.**

We need a 30-second pre-flight check that catches every class of bug like this *before* a single API call burns a single dollar.

---

## Goal

Add a `validate_config()` step that runs at the very start of any benchmark execution. It checks every input path, environment variable, and budget setting. If any check fails, the run **refuses to start** — no API calls, no partial state.

---

## Files in scope

```
simulatte-workspace/popscale/
├── popscale/
│   ├── config/
│   │   ├── __init__.py
│   │   ├── validator.py                # NEW — validate_config()
│   │   └── tests/
│   │       └── test_validator.py       # NEW
└── benchmarks/wb_2026/constituency/
    └── wb_2026_constituency_benchmark.py    # call validator first thing in main()
```

---

## Acceptance criteria

1. **Path validation**
   - Every CLI flag that takes a file path (e.g. `--sensitivity-baseline`, `--resume-from`, `--config`) is validated:
     - File exists
     - Path is absolute (relative paths rejected with helpful error suggesting absolute form)
     - Path is readable
   - Every CLI flag that takes a directory (e.g. `--output-dir`) is validated:
     - Directory exists OR can be created
     - Directory is writable

2. **Environment variable validation**
   - `ANTHROPIC_API_KEY` set and non-empty
   - `SIMULATTE_NTFY_TOPIC` set if credit detector active (BRIEF-004 dependency — soft-required)
   - Any required env var documented in `CORE_SPEC.md` is present

3. **Budget consistency check**
   - If `--budget-ceiling` is set, validate that it covers all layers (PopScale scoring + Niobe synthesis + Persona Generator). Print a breakdown showing the estimated per-layer share so the user sees what's covered.
   - If the estimated cost exceeds `--budget-ceiling`, refuse to start unless `--force-over-budget` is passed.

4. **Schema check on baseline file** — if `--sensitivity-baseline` is given, load the file and verify it has the expected keys (`cluster_results`, `run_id`, etc.). Reject if malformed.

5. **Output formatting** — when validation succeeds, print a green ✅ block summarizing the validated config. When it fails, print a red ❌ block listing every failure (don't bail at first error — collect all failures so user fixes once).

6. **Tests**
   - Each validation rule has a unit test for both pass and fail cases
   - Integration test: simulate the bad WB 2026 invocation (relative baseline path) — verify the validator catches it before any API call

---

## Implementation notes

- Use `pathlib.Path` for all path checks. `Path.is_absolute()` is built in.
- For "directory writable" — `os.access(path, os.W_OK)` or attempt to create a sentinel file.
- For schema check on baseline JSON — use `pydantic` or just `json.load + assert keys`. Don't import the full benchmark schema; keep this validator lightweight.
- Estimated-cost breakdown: a static lookup table is fine for now (e.g., "Niobe persona generation: ~$X/cluster, scoring: ~$Y/cluster"). Better numbers come from telemetry in BRIEF-008.
- Print a banner identifier so users see immediately that pre-flight ran:
  ```
  ╔══════════════════════════════════════════╗
  ║  Simulatte pre-flight check              ║
  ╚══════════════════════════════════════════╝
  ✅ All paths absolute and readable
  ✅ ANTHROPIC_API_KEY set
  ⚠️  SIMULATTE_NTFY_TOPIC unset — push notifications disabled
  ✅ Budget ceiling $90 covers estimated $72
  ───
  Estimated cost breakdown:
    Niobe persona gen     ~$45  (62%)
    PopScale scoring      ~$22  (31%)
    Reflection + decide   ~$5   (7%)
  ───
  ```

---

## Deliverable format

- Summary of approach (1 paragraph)
- List of validation rules implemented (table)
- Sample output for both success and failure cases
- Test output (pass/fail counts)

---

## Out-of-scope

- Live cost tracking during the run — that's BRIEF-008 (dashboard).
- Ground truth file validation — that comes in Phase 3 with the calibration framework.
- Runtime validation (the system already does input type checks); this brief is purely about the preflight gate.

---

## Reference

- `PRINCIPLES.md` P3, P4
- `CORE_SPEC.md` §4.1 ("Hard rule: All paths in Scenario must be absolute")
- The bug this prevents: `FileNotFoundError` on `results/wb_2026_constituency_20260422_034351.json` in Run 7 sensitivity computation
