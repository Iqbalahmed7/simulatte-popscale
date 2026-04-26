# BRIEF-012 — Prompt Cache Discipline

| Field | Value |
|---|---|
| Sprint | Construct Phase 2 / Phase 1 |
| Owner | **Haiku** (Opus orchestrating, executes via Agent) |
| Estimate | 1 day |
| Branch | `phase-1/brief-012-prompt-cache` |
| Status | 🟢 Open |
| Depends on | BRIEF-011 (model tiers stable) — soft dep, can run in parallel |
| Blocks | Phase 1 acceptance |

---

## Why Haiku owns this

The work is mechanical: for each cacheable block, add `cache_control: {"type": "ephemeral"}` to its dict in the API call payload. The decision of *what* is cacheable is already made (this brief). The decision of *where* to apply is grep-able. Haiku executes faster and cheaper than Sonnet for this kind of repetitive transformation.

---

## Goal

Apply Anthropic prompt caching to four stable content blocks that currently pay full price every call. Estimated saving: **15–25%** on top of BRIEF-011 tier migration.

---

## Cache targets (the only four)

| Block | Cached when | Stable across | Win |
|---|---|---|---|
| **Persona core memory** | every persona call | all calls for one persona | already partly cached in `perceive.py` — extend to `decide()`, `reflect()` |
| **Manifesto context** | every persona in a cluster | all 60 personas × 3 ensembles in same cluster | massive (block is 1500+ tokens; gets read 180 times/cluster currently) |
| **Domain framing** | every persona in a cluster | all 60 personas | same pattern as manifesto |
| **Scenario templates** | every call | global, never changes | small per-call; cumulative still useful |

Anything else: do not cache. Per-persona dynamic context (stimulus, decision_scenario specifics) is NOT cacheable.

---

## Files in scope

```
persona-generator/src/cognition/
├── perceive.py        # already has cache_control on system_blocks — extend pattern
├── reflect.py         # add cache_control to core memory block
└── decide.py          # add cache_control to core memory block + scenario templates

popscale/popscale/scenario/
└── renderer.py        # manifesto + domain framing assembly — emit them as
                       # separate cacheable system blocks
```

---

## Acceptance criteria

1. **Persona core memory** — cached in `decide()` and `reflect()` system_blocks, same pattern as current `perceive.py`:
   ```python
   system_blocks = [
       {"type": "text", "text": persona_block, "cache_control": {"type": "ephemeral"}}
   ]
   ```

2. **Manifesto + domain framing** — emitted as separate cacheable system blocks (not concatenated into the user message). When `--manifesto both` is in play, the manifesto text is a stable block reused across every persona in the cluster. Same for domain framing.

3. **Scenario templates** — the static template strings (e.g. `_PERCEIVE_USER_TEMPLATE`) become cached system blocks; only the dynamic `{stimulus}` interpolation lives in the user message.

4. **Cache hit rate measurement** — emit `cache_hit_rate` to the observability events.jsonl per API call. Target after this brief: **>60% cache hit rate** on a 1-cluster manifesto run.

5. **Cost measurement** — run the same 1-cluster murshidabad benchmark used in BRIEF-011 acceptance, measure cost. Target: **15–25% additional reduction** on top of BRIEF-011's gain.

6. **No correctness regression** — Phase 0 tests stay 21/21 green.

---

## Implementation notes

- Anthropic's cache TTL is 5 minutes. As long as the next persona in the same cluster runs within 5 min, cache hits.
- Within-cluster parallelism (BRIEF-014) will push more requests inside the 5-min window — cache hit rate should *improve* with parallelism.
- `cache_control` only applies to system messages, not user messages. Move stable content INTO system from user where currently inlined.
- Cache key is hash of the entire content block. Even one character drift breaks the cache. Be careful with f-strings that interpolate dynamic values into would-be-cached blocks.

---

## Validation procedure

```bash
# Pre-cache baseline (after BRIEF-011 merged)
python3 -m benchmarks.wb_2026.constituency.wb_2026_constituency_benchmark \
  --manifesto both --cluster murshidabad --budget-ceiling 50 \
  --sensitivity-baseline <ABSOLUTE>
# capture cost from logs

# Post-cache: same command after BRIEF-012 merged
# capture cost — should be 15–25% lower

# Verify cache hit rate from events.jsonl
python3 scripts/cache_hit_rate.py runs/<run_id>
# expect: >60%
```

---

## Out-of-scope

- Multi-turn conversation caching (we don't do conversations)
- Cross-cluster caching (each cluster has different manifesto context after BRIEF-011 + 012, so no leverage)
- Persistent caching beyond Anthropic's built-in TTL (Phase 4)

---

## Reference

- Anthropic prompt caching docs (current pattern in `perceive.py:99` is the template)
- `CORE_SPEC.md` §3.1 (cost target)
- `PRINCIPLES.md` P5 (don't reinvent — use Anthropic's built-in)
