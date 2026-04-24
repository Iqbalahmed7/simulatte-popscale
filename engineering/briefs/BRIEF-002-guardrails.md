# BRIEF-002 · Bounded Retry + Streaming + Concurrency Guardrails

**Sprint:** 1 / Tasks S1.2 + S1.3  
**Assignee:** Codex (GPT-5.3 medium, escalate to 5.4 high if first delivery scores <14/20)  
**Timebox:** 3 working days (24h agent time). Stop at 1.5× (36h) if blocked and report.  
**Branch name:** `sprint1/brief-002-guardrails`

---

## Context (read first, in order)

1. `popscale/benchmarks/wb_2026/engineering/VISION.md`
2. `popscale/benchmarks/wb_2026/engineering/ARCHITECTURE.md` (especially §4 caching and §9 invariants)
3. `popscale/benchmarks/wb_2026/engineering/SPRINT_PLAN.md` (§ Sprint 1 / S1.2 and S1.3)
4. `popscale/benchmarks/wb_2026/ENGINE_CAPACITY_NOTE.md`
5. `popscale/engineering/briefs/README.md`

---

## Mission

Install three safety rails so the engine can never again enter the $100+ non-terminating failure mode that occurred on April 23.

1. **Bounded gate-retry** — `assemble_cohort` currently retries indefinitely on gate failures. Cap at 3, emit waiver, continue.
2. **Streaming partial results** — if a run is killed mid-flight, we currently lose everything. Write partial JSON after every N=5 personas so kills still produce usable data.
3. **Concurrency guardrail** — prevent accidental parallel runs (April 23 had 6 processes of the same cluster running, causing 6000+ rate-limit retries and $30 of pure burn).

---

## Workspace

Your root: `/Users/admin/Documents/Simulatte Projects/simulatte-workspace/`

---

## Global constraints (non-negotiable)

- **Python 3.14**, async/await throughout
- **No new Python dependencies** — stdlib only (`asyncio`, `os`, `fcntl`, `json`, `warnings`, `logging`, `signal`, `subprocess`)
- **ClusterResult JSON schema unchanged** unless explicitly version-bumped (see S1.2c below)
- **Must coexist with Brief-001's changes** — Cursor is instrumenting the same files (`niobe/runner.py` and `persona-generator/src/generation/*`). You edit different sections / different functions. If you see a conflict during integration, raise it rather than overwriting.
- **No changes to LLM call sites** — those are Brief-001's territory

---

## Files in scope

### Create (new files)

```
persona-generator/src/generation/gate_waiver.py
popscale/scripts/kill_prior_runs.py
persona-generator/tests/test_bounded_retry.py
niobe/tests/test_concurrency_guardrail.py
popscale/tests/test_pid_lock.py
```

### Modify (existing files)

```
persona-generator/src/generation/cohort_assembler.py
persona-generator/src/schema/validators.py
niobe/niobe/runner.py
popscale/benchmarks/wb_2026/constituency/wb_2026_constituency_benchmark.py
popscale/benchmarks/wb_2026/constituency/seat_model.py
```

---

## Task S1.2 — Bounded gate-retry + streaming

### S1.2a. Bounded gate retry

**Files:** `persona-generator/src/generation/cohort_assembler.py`, `persona-generator/src/schema/validators.py`, new `persona-generator/src/generation/gate_waiver.py`

**Create `gate_waiver.py`:**

```python
from dataclasses import dataclass
from typing import Literal
import time

@dataclass(frozen=True)
class GateWaiver:
    gate_id: Literal["G6", "G7", "G8", "G9", "G10", "G11"]
    attempts_made: int
    final_failure_reason: str
    confidence_penalty: float   # 0.1 per gate waived
    timestamp: float

    def to_dict(self) -> dict:
        return {
            "gate_id": self.gate_id,
            "attempts_made": self.attempts_made,
            "final_failure_reason": self.final_failure_reason,
            "confidence_penalty": self.confidence_penalty,
            "timestamp": self.timestamp,
        }

def cumulative_penalty(waivers: list[GateWaiver]) -> float:
    """Sum of waivers, capped at 0.5."""
    return min(0.5, sum(w.confidence_penalty for w in waivers))
```

**In `cohort_assembler.py`:**

- Add module-level constant: `MAX_GATE_RETRIES = int(os.getenv("SIMULATTE_MAX_GATE_RETRIES", "3"))`
- Find the current gate-retry loop in `assemble_cohort` (or wherever gates are checked post-generation)
- Change from unbounded retry to:

```python
attempts = 0
waivers: list[GateWaiver] = []
while True:
    gate_result = run_cohort_gates(cohort)
    if gate_result.passed:
        break
    attempts += 1
    if attempts >= MAX_GATE_RETRIES:
        # Emit waivers for each failing gate, continue with this cohort
        for failure in gate_result.failures:
            waivers.append(GateWaiver(
                gate_id=failure.gate_id,
                attempts_made=attempts,
                final_failure_reason=failure.message,
                confidence_penalty=0.1,
                timestamp=time.time(),
            ))
            logger.warning("Gate waiver emitted: %s after %d attempts — %s",
                           failure.gate_id, attempts, failure.message)
        break
    # Otherwise regenerate the failing personas and retry
    cohort = regenerate_failing(cohort, gate_result)
```

- Attach `waivers` to the cohort object so downstream code (seat model) can read it
- If the cohort class is a dataclass/Pydantic model, add `waivers: list[GateWaiver] = field(default_factory=list)`

### S1.2b. Streaming per-persona writes

**Files:** `persona-generator/src/generation/cohort_assembler.py`, `niobe/niobe/runner.py`

Currently `assemble_cohort` returns the full cohort at the end. Add a streaming variant that yields personas as they're written:

```python
async def assemble_cohort_streaming(
    spec: PopulationSpec,
    *,
    on_persona_written: Callable[[Persona, int], None] | None = None,
) -> AsyncIterator[Persona]:
    """Yields personas as they're generated. Callback invoked after each."""
    async for persona in _generate_personas(spec):
        if on_persona_written:
            on_persona_written(persona, index)
        yield persona
```

Keep the existing `assemble_cohort(...) -> list[Persona]` for backwards compat; implement it as `[p async for p in assemble_cohort_streaming(spec)]`.

**In `niobe/runner.py`:**

Update `run_niobe_study` to use the streaming version:

```python
partial_path = output_dir / f"{run_id}.partial.json"
personas_so_far = []

async for persona in assemble_cohort_streaming(spec):
    personas_so_far.append(persona)
    if len(personas_so_far) % 5 == 0:
        # Write partial snapshot
        _write_partial_json(partial_path, personas_so_far, status="in_progress")

# Final write happens as normal at end of function
```

On SIGTERM/SIGINT, the partial file should already be on disk (register a signal handler in `run_niobe_study` that does one final flush).

### S1.2c. Seat model accepts partial cohorts + confidence penalty

**File:** `popscale/benchmarks/wb_2026/constituency/seat_model.py`

Modify `compute_seat_predictions` signature:

```python
def compute_seat_predictions(
    cluster_breakdown: list[dict],
    *,
    confidence_penalty: float = 0.0,  # NEW kwarg
    is_partial: bool = False,          # NEW kwarg
) -> dict:
    # ... existing logic ...
    
    # Widen confidence band by (1 + penalty)
    if confidence_penalty > 0:
        confidence_range_seats = round(confidence_range * (1 + confidence_penalty))
    
    result = {
        "schema_version": "2.0" if (confidence_penalty > 0 or is_partial) else "1.0",
        # ... existing fields ...
        "confidence_range_seats": confidence_range_seats,
        "is_partial": is_partial,
        "gate_waivers": [w.to_dict() for w in all_waivers] if all_waivers else [],
    }
    return result
```

**Schema version rule:**
- Clean runs with no waivers and no partials → `schema_version: "1.0"` (unchanged behavior)
- Any waiver OR is_partial=True → `schema_version: "2.0"`

Downstream code that reads the JSON should not break — new fields are additive only.

---

## Task S1.3 — Concurrency guardrails

### S1.3a. Shared concurrency semaphore

**File:** `niobe/niobe/runner.py`

At module top:

```python
import asyncio
import os

_MAX_CONCURRENT_LLM = int(os.getenv("SIMULATTE_MAX_CONCURRENT_LLM", "20"))
_llm_semaphore: asyncio.Semaphore | None = None

def _get_llm_semaphore() -> asyncio.Semaphore:
    global _llm_semaphore
    if _llm_semaphore is None:
        _llm_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_LLM)
    return _llm_semaphore
```

Create a helper decorator that downstream callers can use:

```python
def with_llm_semaphore(func):
    """Wrap an async LLM-calling function with the shared semaphore."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        async with _get_llm_semaphore():
            return await func(*args, **kwargs)
    return wrapper
```

Apply the semaphore inside `run_niobe_study` around any `await` chain that calls out to `persona-generator` or LLM-heavy operations. Concretely: any `gather()` call that launches N parallel persona generations should hold the semaphore per-task.

**Do not** add the semaphore inside `persona-generator` itself. Keep it at the Niobe orchestration layer.

### S1.3b. PID-file lock

**File:** `popscale/benchmarks/wb_2026/constituency/wb_2026_constituency_benchmark.py`

At benchmark startup (before any LLM call):

```python
import fcntl, os, signal, atexit
from pathlib import Path

PID_DIR = Path("/tmp/simulatte_runs")

def acquire_pid_lock(cluster_id: str) -> Path:
    PID_DIR.mkdir(parents=True, exist_ok=True)
    pid_path = PID_DIR / f"{cluster_id}.pid"
    
    if pid_path.exists():
        existing_pid = int(pid_path.read_text().strip())
        try:
            os.kill(existing_pid, 0)  # signal 0 = existence check, doesn't kill
            print(f"❌ ERROR: Cluster '{cluster_id}' already running as PID {existing_pid}")
            print(f"   Kill it first: kill -9 {existing_pid}")
            print(f"   Or clean up: python3 popscale/scripts/kill_prior_runs.py --cluster {cluster_id}")
            raise SystemExit(1)
        except ProcessLookupError:
            # PID file is stale, safe to overwrite
            pass
    
    pid_path.write_text(str(os.getpid()))
    
    # Clean up on exit
    def cleanup():
        try:
            if pid_path.exists() and pid_path.read_text().strip() == str(os.getpid()):
                pid_path.unlink()
        except Exception:
            pass
    
    atexit.register(cleanup)
    signal.signal(signal.SIGTERM, lambda *_: (cleanup(), sys.exit(1)))
    signal.signal(signal.SIGINT, lambda *_: (cleanup(), sys.exit(130)))
    return pid_path
```

Call `acquire_pid_lock(cluster_id)` at the top of the benchmark's main function.

### S1.3c. `kill_prior_runs.py` utility

**File:** `popscale/scripts/kill_prior_runs.py`

```python
"""Kill all running PopScale benchmark processes and clean orphan PID files.

Usage:
    python3 popscale/scripts/kill_prior_runs.py              # kill everything
    python3 popscale/scripts/kill_prior_runs.py --cluster murshidabad  # one cluster
"""
import argparse, os, signal, subprocess, sys
from pathlib import Path

PID_DIR = Path("/tmp/simulatte_runs")

def find_benchmark_pids(cluster_filter: str | None = None) -> list[int]:
    """Use ps to find running benchmark processes. No psutil dep."""
    result = subprocess.run(["ps", "-eo", "pid,command"], capture_output=True, text=True)
    pids = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.strip().split(maxsplit=1)
        if len(parts) != 2:
            continue
        pid_str, cmd = parts
        if "wb_2026_constituency_benchmark" not in cmd:
            continue
        if cluster_filter and f"--cluster {cluster_filter}" not in cmd:
            continue
        try:
            pids.append(int(pid_str))
        except ValueError:
            pass
    return pids

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cluster", default=None, help="Kill only one cluster's run")
    args = ap.parse_args()
    
    pids = find_benchmark_pids(args.cluster)
    print(f"Found {len(pids)} matching benchmark processes")
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
            print(f"  ✓ Killed PID {pid}")
        except ProcessLookupError:
            print(f"  - PID {pid} already gone")
    
    # Clean PID files
    if PID_DIR.exists():
        for pid_file in PID_DIR.glob("*.pid"):
            if args.cluster and pid_file.stem != args.cluster:
                continue
            pid_file.unlink()
            print(f"  ✓ Removed stale PID file {pid_file.name}")

if __name__ == "__main__":
    main()
```

---

## Acceptance criteria

- [ ] `SIMULATTE_MAX_GATE_RETRIES=2 python3 -m benchmarks.wb_2026.constituency.wb_2026_constituency_benchmark --cluster <demographically-narrow-cluster>` completes with gate waivers emitted (check log output and result JSON's `gate_waivers` field)
- [ ] A cluster run killed mid-generation produces a valid `<run_id>.partial.json` containing all personas written so far
- [ ] Two simultaneous launches of the same cluster: second one prints a clear error pointing to the PID and exits with code 1
- [ ] `python3 popscale/scripts/kill_prior_runs.py` cleans all active benchmark processes + PID files
- [ ] `python3 popscale/scripts/kill_prior_runs.py --cluster matua_belt` kills only matua_belt
- [ ] Concurrency semaphore observably caps parallel LLM calls at 20 (test with asyncio.gather of 100 mock calls)
- [ ] Existing Murshidabad run still completes successfully with unchanged result JSON (schema_version stays "1.0" for clean run)
- [ ] Result JSON bumps to `schema_version: "2.0"` when any waiver or partial is present
- [ ] All new tests pass: `pytest persona-generator/tests/test_bounded_retry.py niobe/tests/test_concurrency_guardrail.py popscale/tests/test_pid_lock.py -v`
- [ ] Existing test suite still passes

---

## Anti-goals (do NOT do these)

- ❌ Do not add cost tracing — Brief-001's task
- ❌ Do not refactor identity_constructor — Sprint 2 (S2.1)
- ❌ Do not add persona caching — Sprint 3 (S3.1)
- ❌ Do not touch the seat model math (cube-law logic) — only add `confidence_penalty` and `is_partial` kwargs
- ❌ Do not use `psutil` or any non-stdlib module — use `subprocess.run(['ps', ...])` for process listing
- ❌ Do not change the semaphore default of 20 unless you have a measured reason

---

## Deliverable format

Paste into coordinator chat. Branch: `sprint1/brief-002-guardrails`. Do NOT commit to main.

```
# BRIEF-002 S1.2+S1.3 DELIVERY

## Summary
<one paragraph>

## Architecture decisions
<non-obvious choices, especially around partial-write semantics and semaphore scope>

## Files changed (existing)
- path/to/file.py  +N -M lines
- ...

## Files created (new)
- path/to/new/file.py  N lines (brief description)
- ...

## Unified diff
<full diff including full text of new files>

## Test output
$ pytest persona-generator/tests/test_bounded_retry.py niobe/tests/test_concurrency_guardrail.py popscale/tests/test_pid_lock.py -v
<output>

$ pytest persona-generator/tests/ niobe/tests/ popscale/tests/  # regression
<output>

## Verification runs

# Test 1: PID lock
$ python3 -m benchmarks.wb_2026.constituency.wb_2026_constituency_benchmark --cluster kolkata_urban &
$ sleep 3
$ python3 -m benchmarks.wb_2026.constituency.wb_2026_constituency_benchmark --cluster kolkata_urban
<expected: error about existing PID>

# Test 2: Kill utility
$ python3 popscale/scripts/kill_prior_runs.py
<expected: cleans up>

# Test 3: Bounded retry (env var)
$ SIMULATTE_MAX_GATE_RETRIES=1 pytest persona-generator/tests/test_bounded_retry.py -v
<output>

# Test 4: Partial write
$ python3 -m benchmarks.wb_2026.constituency.wb_2026_constituency_benchmark --cluster burdwan_industrial &
$ sleep 60
$ kill -TERM <pid>
$ ls -la /tmp/wb_reruns/*.partial.json
<expected: file exists with in_progress status>

## Scope questions raised (with your chosen resolution)

## Deviations from brief (with rationale)

## Timebox actual
```

Expect a rated verdict within 1–2 exchanges. Rubric: Correctness / Code Quality / Test Coverage / Adherence, each /5. Total /20.
