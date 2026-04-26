# BRIEF-013 — Structured Outputs Migration

| Field | Value |
|---|---|
| Sprint | Construct Phase 2 / Phase 1 |
| Owner | **Sonnet** (Opus executes) |
| Estimate | 1.5 days |
| Branch | `phase-1/brief-013-structured-outputs` |
| Status | 🟢 Open |
| Depends on | — |
| Blocks | Phase 1 acceptance |

---

## Why Sonnet owns this

Schema design is reasoning-heavy: each cognition stage has a distinct output shape, and getting the schema wrong cascades into silent data corruption downstream. Sonnet picks the right shapes; the migration once shapes are set is mechanical but the design step isn't.

---

## Goal

Replace ad-hoc JSON parsing in `perceive()`, `decide()`, and `reflect()` with Anthropic's tool-use / structured outputs API. Eliminates the JSON parse failures we saw in WB Run 7 (Ramesh Chamar, Mohammad Iqbal — both went to fallback responses because the model wrapped JSON in markdown fences).

Estimated impact:
- Fallback rate: ~2% → <0.1%
- Retry cost saved: ~5%
- Cleaner data, no regex brittleness

---

## Files in scope

```
persona-generator/src/cognition/
├── perceive.py        # _parse_perceive_response() → use structured output
├── decide.py          # JSON parsing logic → structured output
└── reflect.py         # JSON parsing logic → structured output

persona-generator/src/utils/
└── structured.py      # NEW — shared helpers for tool-use response extraction

persona-generator/src/schema/
└── cognition_outputs.py   # NEW — Pydantic schemas matching tool definitions
```

---

## Acceptance criteria

1. **Schema definition** — `src/schema/cognition_outputs.py` defines:
   ```python
   class PerceiveOutput(BaseModel):
       content: str
       importance: int  # 1-10
       emotional_valence: float  # -1.0 to 1.0
   
   class DecideOutput(BaseModel):
       gut_reaction: str
       information_processing: str
       constraint_check: str
       social_signal_check: str
       final_decision: str
       confidence: int  # 0-100
       key_drivers: list[str]
       objections: list[str]
       what_would_change_mind: str
       follow_up_action: str
       implied_purchase: bool
   
   class ReflectOutput(BaseModel):
       summary: str
       value_shifts: list[str]
       importance: int
   ```

2. **Tool-use migration** — each stage emits a tool definition matching its schema and invokes the API with `tools=[...]` + `tool_choice={"type": "tool", "name": "..."}`:
   ```python
   response = await client.messages.create(
       model=...,
       tools=[{"name": "emit_perception", "input_schema": PerceiveOutput.model_json_schema()}],
       tool_choice={"type": "tool", "name": "emit_perception"},
       messages=messages,
   )
   parsed = response.content[0].input  # already a dict matching schema
   ```

3. **Fallback path retained** — if for any reason the API returns text instead of tool use (rare), fall back to the existing JSON parser. Don't delete the regex fallback; just make it the second line of defense.

4. **No semantic regression** — Phase 0 `test_credit_monitor.py`, validator tests, scenario tests, observability tests all still 21/21 green. Plus add new tests:
   - `test_perceive_uses_structured_output`
   - `test_decide_uses_structured_output`  
   - `test_reflect_uses_structured_output`
   - `test_falls_back_to_text_parser_on_unusual_response`

5. **Measurement on real run** — run a 1-cluster murshidabad backcast. Expected:
   - Zero JSON parse fallback warnings in log
   - All ensemble runs complete without retry storms
   - Cost: marginal improvement (~5% from saved retries)

---

## Implementation notes

- Anthropic's tool use returns a `ToolUseBlock` in `response.content`. Extract via `response.content[0].input`.
- Model still needs `tier` (Haiku for `perceive`, Sonnet for `decide`/`reflect`) — that's BRIEF-011's job. Don't conflate.
- Pydantic V2 is what's already in the project; use `model_json_schema()`.
- Tool definitions are static — define once at module level, don't re-construct per call.

---

## Validation procedure

```bash
# Run the same 1-cluster benchmark
python3 -m benchmarks.wb_2026.constituency.wb_2026_constituency_benchmark \
  --manifesto both --cluster murshidabad --budget-ceiling 50 \
  --sensitivity-baseline <ABSOLUTE>

# Check log for fallback warnings
grep "JSON parse failed\|fallback" /tmp/run.log
# expected: zero matches (or only on truly malformed responses)

# Run new schema tests
python3 -m pytest tests/test_structured_outputs.py -v
```

---

## Out-of-scope

- Migrating Niobe internals to structured outputs (different module, separate brief if needed)
- Schema versioning (Phase 4)
- Generated TypeScript types from schemas (Phase 3 frontend work)

---

## Reference

- Anthropic tool use docs: `https://docs.anthropic.com/.../tool-use`
- WB Run 7 errors that motivated this: `/tmp/manifesto_run7.log` lines 01:05:48 (Ramesh) and 01:06:20 (Mohammad)
- `CORE_SPEC.md` §3.3 ("JSON parse fallback rate <0.1%")
- `PRINCIPLES.md` P3 (fail loud — invalid output should error, not silently fall back to mush)
