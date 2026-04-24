# BRIEF-001 · Cost Observability Instrumentation

**Sprint:** 1 / Task S1.1  
**Assignee:** Cursor (automatic tier)  
**Timebox:** 3 working days (24h agent time). Stop at 1.5× (36h) if blocked and report.  
**Branch name:** `sprint1/brief-001-cost-observability`

---

## Context (read first, in order)

1. `popscale/benchmarks/wb_2026/engineering/VISION.md`
2. `popscale/benchmarks/wb_2026/engineering/ARCHITECTURE.md`
3. `popscale/benchmarks/wb_2026/engineering/SPRINT_PLAN.md` (§ Sprint 1 / S1.1)
4. `popscale/benchmarks/wb_2026/ENGINE_CAPACITY_NOTE.md`
5. `popscale/engineering/briefs/README.md`

---

## Mission

On April 23, a single cluster run made ~950 LLM calls per persona against an expected ~13, burning ~$100 in unexplained compute. We have zero visibility into which phase, which sub-step, or which persona consumed what.

**Your job: add per-persona LLM call observability to the engine.** Every LLM call gets a structured record tagged with persona_id, phase, sub-step, tokens, duration, and cost. Dumped to CSV on demand.

This is the diagnostic foundation. Sprint 2 (consolidating IdentityConstructor from 8 calls to 2) cannot start without this data.

---

## Workspace

Your root: `/Users/admin/Documents/Simulatte Projects/simulatte-workspace/`

Three folders accessible:
- `popscale/` — benchmark layer
- `persona-generator/` — core persona synthesis (where most of your work lands)
- `niobe/` — orchestration

---

## Global constraints (non-negotiable)

- **Python 3.14**, async/await throughout
- **Claude Haiku 4.5** for volume tier — no model changes
- **No new Python dependencies** — stdlib only (`contextvars`, `dataclasses`, `time`, `logging`, `csv`, `pathlib`, `functools`)
- **persona_id stability across cache hits** (ARCHITECTURE §9.1) — do not touch any code path that assigns persona IDs
- **No breaking changes to any public API** — add optional parameters, never remove or rename
- **No changes to LLM retry logic, concurrency, gate retries** — that's Brief-002

---

## Files in scope

### Create (new files)

```
persona-generator/src/observability/__init__.py
persona-generator/src/observability/cost_tracer.py
persona-generator/tests/test_cost_tracer.py
```

### Modify (existing files)

```
persona-generator/src/generation/identity_constructor.py
persona-generator/src/generation/life_story_generator.py
persona-generator/src/generation/attribute_filler.py
niobe/niobe/runner.py
popscale/benchmarks/wb_2026/constituency/wb_2026_constituency_benchmark.py
```

Anything outside this list → raise a scope question in your deliverable.

---

## Detailed task list

### 1. Build `CostTracer` primitive

**File:** `persona-generator/src/observability/cost_tracer.py`

Required public API:

```python
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Literal
from pathlib import Path
import time, csv, logging

PhaseType = Literal[
    "life_story",
    "identity_core",        # worldview + psych + value_orientation (Sprint 2 consolidation target)
    "identity_behavior",    # behavior + trust + risk + values_alignment
    "attribute_fill",
    "scenario_perceive",
    "scenario_accumulate",
    "scenario_decide",
    "other",
]

@dataclass(frozen=True)
class LLMCallRecord:
    persona_id: str
    phase: str
    sub_step: str          # free-form e.g. "worldview" or "trust_anchor"
    input_tokens: int
    output_tokens: int
    duration_ms: int
    timestamp: float
    model: str
    status: Literal["ok", "retry", "fail"]

@dataclass
class PersonaCostSummary:
    persona_id: str
    total_calls: int
    total_input_tokens: int
    total_output_tokens: int
    total_duration_ms: int
    by_phase: dict[str, dict]  # phase -> {calls, input_tokens, output_tokens, duration_ms}
    estimated_cost_usd: float

class CostTracer:
    """Thread-safe, async-aware cost tracer using contextvars."""
    
    _records: list[LLMCallRecord] = []
    _persona_id: ContextVar[str] = ContextVar("persona_id", default="unknown")
    _phase: ContextVar[str] = ContextVar("phase", default="other")
    
    @classmethod
    def start_persona(cls, persona_id: str) -> None: ...
    @classmethod
    def set_phase(cls, phase: PhaseType) -> None: ...
    @classmethod
    def current_persona_id(cls) -> str: ...
    @classmethod
    def current_phase(cls) -> str: ...
    @classmethod
    def record(cls, rec: LLMCallRecord) -> None: ...
    @classmethod
    def finish_persona(cls, persona_id: str) -> PersonaCostSummary: ...
    @classmethod
    def all_records(cls) -> list[LLMCallRecord]: ...
    @classmethod
    def dump_csv(cls, path: Path) -> None: ...
    @classmethod
    def reset(cls) -> None: ...  # for tests
```

### Key implementation notes

- Use `contextvars.ContextVar` (not `threading.local`) — engine uses `asyncio.gather`, and contextvars correctly propagate across `asyncio.create_task` boundaries
- `_records` is a module-level list; append is GIL-protected in CPython but use an `asyncio.Lock` if you want safety against future contention
- `estimated_cost_usd` math: Haiku 4.5 pricing is **$1.00 per 1M input tokens, $5.00 per 1M output tokens**
- `dump_csv` writes headers: `persona_id, phase, sub_step, input_tokens, output_tokens, duration_ms, timestamp, model, status`

### 2. Instrument `identity_constructor.py`

**File:** `persona-generator/src/generation/identity_constructor.py`

The file has 8 `await llm_client.*` call sites. Wrap each one with a timing+recording block:

```python
# Example pattern — apply to every await site
from src.observability.cost_tracer import CostTracer, LLMCallRecord
import time

async def _worldview_step(self, ...):
    CostTracer.set_phase("identity_core")
    start = time.monotonic()
    status = "ok"
    try:
        response = await self._llm_client.messages.create(...)
    except Exception:
        status = "fail"
        raise
    finally:
        CostTracer.record(LLMCallRecord(
            persona_id=CostTracer.current_persona_id(),
            phase="identity_core",
            sub_step="worldview",
            input_tokens=response.usage.input_tokens if status == "ok" else 0,
            output_tokens=response.usage.output_tokens if status == "ok" else 0,
            duration_ms=int((time.monotonic() - start) * 1000),
            timestamp=time.time(),
            model=self._llm_client.model_name if hasattr(self._llm_client, "model_name") else "unknown",
            status=status,
        ))
    # ... rest of function unchanged
```

**DO NOT** change the LLM call logic, retries, or control flow. You are only observing.

Sub-step labels to use (one per distinct LLM call in the file, roughly):
`worldview`, `psych_insights`, `value_orientation`, `behavior_tendencies`, `trust_anchor`, `risk_appetite`, `values_alignment`, `constraint_check`

Exact phase labels per sub_step:
- `identity_core` → worldview, psych_insights, value_orientation
- `identity_behavior` → behavior_tendencies, trust_anchor, risk_appetite, values_alignment
- `other` → constraint_check (and any fallbacks)

### 3. Instrument `life_story_generator.py`

One LLM call in this file. Wrap it with:
- `phase="life_story"`
- `sub_step="generate"`

### 4. Instrument `attribute_filler.py`

Multiple LLM calls in a batch loop. Wrap each one:
- `phase="attribute_fill"`
- `sub_step=<attribute_name>` (the specific attribute being filled)

### 5. Hook into Niobe runner

**File:** `niobe/niobe/runner.py`

At the beginning of each persona generation:

```python
from src.observability.cost_tracer import CostTracer

# inside run_niobe_study, before building each persona
CostTracer.start_persona(persona_id)

# after each persona finishes
summary = CostTracer.finish_persona(persona_id)
logger.info("persona_cost_summary: %s", summary)  # structured logging
```

Also hook phase transitions for scenario running:
- Before `scenario.perceive()` — `CostTracer.set_phase("scenario_perceive")`
- Before `scenario.accumulate()` — `CostTracer.set_phase("scenario_accumulate")`
- Before `scenario.decide()` — `CostTracer.set_phase("scenario_decide")`

Find the exact call sites by searching for these method names in the codebase.

### 6. Add `--cost-trace` CLI flag

**File:** `popscale/benchmarks/wb_2026/constituency/wb_2026_constituency_benchmark.py`

```python
# In argparse section
parser.add_argument("--cost-trace", type=str, default=None,
                    help="Dump per-call cost CSV to this path at end of run")
```

At the end of the benchmark's main function (in a `try/finally`):

```python
finally:
    if args.cost_trace:
        from src.observability.cost_tracer import CostTracer
        CostTracer.dump_csv(Path(args.cost_trace))
        print(f"✓ Cost trace written to {args.cost_trace}")
```

Handle SIGINT/SIGTERM gracefully — dump partial CSV before exit.

### 7. Tests

**File:** `persona-generator/tests/test_cost_tracer.py`

Test cases:
- **Concurrency safety:** 10 concurrent `asyncio.gather` tasks, each starts a persona, records 5 calls, finishes — verify no cross-contamination
- **CSV round-trip:** record 100 calls, dump CSV, read back with `csv.DictReader`, compare to originals
- **Summary math:** feed known records, verify `PersonaCostSummary.estimated_cost_usd` matches Haiku pricing
- **ContextVar propagation:** nested async call inside `start_persona` scope sees the correct persona_id
- **Reset:** `CostTracer.reset()` clears state between tests

---

## Acceptance criteria

- [ ] Running `python3 -m benchmarks.wb_2026.constituency.wb_2026_constituency_benchmark --cluster kolkata_urban --cost-trace /tmp/trace.csv` produces a CSV with ≥50 rows (one per LLM call)
- [ ] CSV columns exactly: `persona_id, phase, sub_step, input_tokens, output_tokens, duration_ms, timestamp, model, status`
- [ ] Every row has a non-"unknown" persona_id
- [ ] ≥90% of rows have a specific phase (not "other")
- [ ] When run is Ctrl-C'd mid-flight, CSV contains all records captured up to that point
- [ ] Zero behavioural change when `--cost-trace` is NOT set
- [ ] Performance regression <5% on a Murshidabad baseline
- [ ] All new tests pass: `pytest persona-generator/tests/test_cost_tracer.py -v`
- [ ] Existing test suite still passes

---

## Anti-goals (do NOT do these)

- ❌ Do not change LLM retry logic — Brief-002
- ❌ Do not add concurrency semaphores — Brief-002
- ❌ Do not refactor identity_constructor to consolidate calls — Sprint 2 (S2.1)
- ❌ Do not touch persona_id assignment logic
- ❌ Do not add new dependencies

---

## Deliverable format

Paste into the coordinator chat. Branch: `sprint1/brief-001-cost-observability`. Do NOT commit to main.

```
# BRIEF-001 S1.1 DELIVERY

## Summary
<one paragraph>

## Architecture decisions
<non-obvious choices, especially around contextvar scope and async safety>

## Files changed (existing)
- path/to/file.py  +N -M lines
- ...

## Files created (new)
- path/to/new/file.py  N lines (brief description)
- ...

## Unified diff
<full diff including full text of new files>

## Test output
$ pytest persona-generator/tests/test_cost_tracer.py -v
<output>

$ pytest persona-generator/tests/ niobe/tests/ popscale/tests/  # existing test regression
<output>

## Verification run
$ python3 -m benchmarks.wb_2026.constituency.wb_2026_constituency_benchmark --cluster kolkata_urban --cost-trace /tmp/verify.csv
<output>

## CSV sample (first 20 rows of /tmp/verify.csv)
<rows>

## Phase/persona coverage stats
<% of rows with specific phase, top 5 sub_steps by count, mean calls per persona>

## Scope questions raised (with your chosen resolution)
<any ambiguity encountered>

## Deviations from brief (with rationale)
<any deviation and why>

## Timebox actual
<hours taken>
```

Expect a rated verdict within 1–2 exchanges. Rubric: Correctness / Code Quality / Test Coverage / Adherence, each /5. Total /20.
