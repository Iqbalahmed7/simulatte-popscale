# BRIEF-011 — Haiku Tier Migration (the big cost lever)

| Field | Value |
|---|---|
| Sprint | Construct Phase 2 / Phase 1 |
| Owner | **Sonnet** (Opus orchestrating) |
| Estimate | 2 days |
| Branch | `phase-1/brief-011-haiku-tier-migration` |
| Status | 🟢 Open |
| Depends on | Phase 0 closed ✓ |
| Blocks | Phase 1 acceptance |

---

## Why Sonnet (not Haiku) owns this

This is **the** cost-critical decision of Phase 1. Done wrong, persona reasoning quality silently degrades and the moat erodes — exactly the failure mode `PRINCIPLES.md` P1 forbids. Done right, the $430 study becomes ~$130. Needs Sonnet's judgment to classify each call site as "safe-to-downgrade synthesis" vs "must-stay-Sonnet reasoning."

---

## Goal

Migrate all "shallow" LLM call sites from Sonnet → Haiku per `CORE_SPEC.md` §2 model tier table:

| Stage | Currently | Target | Status |
|---|---|---|---|
| Persona attribute generation | Sonnet | **Haiku** | migrate |
| Cohort assembly + validation gates | Sonnet | **Haiku** | migrate |
| `perceive()` | Haiku | Haiku | ✓ no change |
| Memory writes | Haiku | Haiku | ✓ no change |
| `reflect()` | Sonnet | Sonnet | ✓ no change |
| `decide()` | Sonnet | Sonnet | ✓ no change |

Estimated saving: **65–75%** of total spend.

---

## Files in scope

```
persona-generator/
├── src/cohort/                     # cohort assembly — switch to Haiku
├── src/synthesis/                  # persona slot-fill — switch to Haiku
├── src/cognition/perceive.py       # ✓ already Haiku
├── src/cognition/reflect.py        # ✓ Sonnet stays
├── src/cognition/decide.py         # ✓ Sonnet stays
└── tests/                          # add A/B comparison tests

popscale/
├── popscale/generation/calibrated_generator.py   # may have model overrides
└── niobe/runner.py                 # study runner — verify tier routing
```

---

## Acceptance criteria

1. **Audit:** every `claude.messages.create(model=...)` and `client.messages.create(model=...)` call has been catalogued. Output a table in the PR description: file, line, current model, target model, justification.

2. **Migration:** all call sites in the §2 "Haiku" rows are switched. No call site changed without explicit table justification.

3. **A/B quality test:** run a 1-cluster murshidabad backcast (40 personas) with old config (all-Sonnet) AND new config (mixed). Compare:
   - Vote share variance ≤ 2pp between configs
   - Persona reasoning trace richness (qualitative — spot-check 5 personas) — no obvious quality drop
   - JSON parse fallback rate doesn't increase

4. **Cost measurement:** measure actual cost of the 1-cluster run before/after. Target: **≥60% cost reduction** observed.

5. **No regression:** existing Phase 0 module tests stay 21/21 green.

6. **Inviolable rule from `CORE_SPEC.md`:** `decide()` must NOT be downgraded under any circumstances. If anyone proposes it, refuse and escalate to coordinator.

---

## Implementation notes

- `_HAIKU_MODEL = "claude-haiku-4-5-20251001"` already defined in `perceive.py` — use the same constant
- `_SONNET_MODEL = "claude-sonnet-4-6-20251015"` — define in shared module if not already
- Model tier should be parametrised, not hardcoded. Pattern:
  ```python
  from src.config.models import HAIKU, SONNET
  response = await client.messages.create(model=HAIKU, ...)
  ```
- This makes future tier changes a one-line edit instead of a multi-file refactor.

---

## Quality validation procedure

Before merging:

```bash
# Baseline: all-Sonnet run
SIMULATTE_FORCE_TIER=all_sonnet python3 -m benchmarks.wb_2026.constituency.wb_2026_constituency_benchmark \
  --manifesto both --cluster murshidabad --budget-ceiling 50 \
  --sensitivity-baseline <ABSOLUTE>

# New: mixed tier
python3 -m benchmarks.wb_2026.constituency.wb_2026_constituency_benchmark \
  --manifesto both --cluster murshidabad --budget-ceiling 50 \
  --sensitivity-baseline <ABSOLUTE>

# Compare
python3 scripts/compare_runs.py runs/<old_id> runs/<new_id>
# expect: vote_share_diff < 2pp, cost_diff > 60%
```

If `vote_share_diff >= 2pp`: investigate which Haiku-migrated call introduced the drift, revert that one, retest.

---

## Out-of-scope

- Prompt cache discipline (BRIEF-012)
- Structured outputs migration (BRIEF-013)
- Fine-tuning Haiku for our use case (Phase 3)

---

## Reference

- `CORE_SPEC.md` §2 (model tiering policy — the canonical truth)
- `PRINCIPLES.md` P1 (reasoning depth is the moat — protect it)
- `PRINCIPLES.md` P4 (cost is engineering — actually measure it)
