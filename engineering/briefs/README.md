# Engineering Briefs — PopScale Engine Rebuild

**For:** Cursor & Codex coding agents  
**Coordinator:** Opus (project manager, reviewer)

---

## Your workspace

Open this folder in your IDE / working directory:

```
/Users/admin/Documents/Simulatte Projects/simulatte-workspace/
```

From there you see three subfolders (each is a symlink to the real repo — edit freely, changes flow through):

```
simulatte-workspace/
├── popscale/           → the benchmarks, scenarios, seat model
├── persona-generator/  → the core persona synthesis engine
└── niobe/              → the orchestration layer
```

Full read/write on all three.

---

## Orientation — read these first, every time

Before picking up any brief, read in this order:

1. `popscale/benchmarks/wb_2026/engineering/VISION.md` — why we're rebuilding
2. `popscale/benchmarks/wb_2026/engineering/ARCHITECTURE.md` — target system architecture
3. `popscale/benchmarks/wb_2026/engineering/SPRINT_PLAN.md` — 6-sprint program
4. `popscale/benchmarks/wb_2026/ENGINE_CAPACITY_NOTE.md` — what we learned on April 23

---

## Operating rhythm

1. Read your brief fully before writing any code.
2. Ask clarifying questions IN YOUR DELIVERABLE — do not block on them. Make the best call and note it.
3. Work within the `files in scope` allow-list. Anything beyond requires explicit scope expansion via the coordinator.
4. Timebox is firm. If you exceed 1.5× the estimate, stop and report what's blocking.
5. Do not commit to main. Branch name convention: `sprint1/<brief-id>-<slug>`.

---

## Review protocol

Every delivery is rated on four 1–5 dimensions (total /20):

- **Correctness** — acceptance criteria met, edge cases handled
- **Code quality** — clean, idiomatic, readable
- **Test coverage** — unit + integration, edge cases
- **Adherence to brief** — stayed in scope, raised scope questions rather than drift

Three possible verdicts: ✅ Accept · 🔧 Accept with fixes · ❌ Reject.

---

## Current briefs

| Brief | Sprint | Task | Assignee | Status |
|---|---|---|---|---|
| [BRIEF-001](./BRIEF-001-cost-observability.md) | S1.1 | Cost observability instrumentation | **Cursor** | ✅ Accepted |
| [BRIEF-002](./BRIEF-002-guardrails.md) | S1.2+S1.3 | Bounded retry + streaming + concurrency guardrail | **Codex** | ✅ Accepted |
| [BRIEF-003](./BRIEF-003-manifesto-sensitivity.md) | S1.4 | Manifesto sensitivity re-run (Sprint 1 closer) | **Cursor** | ✅ Accepted |
| [BRIEF-004](./BRIEF-004-credit-detector.md) | C2.P0 | Credit exhaustion detector | **Codex** | ✅ Merged |
| [BRIEF-005](./BRIEF-005-per-ensemble-partial-writes.md) | C2.P0 | Per-ensemble partial writes | **Codex** | ✅ Merged |
| [BRIEF-006](./BRIEF-006-preflight-config-validator.md) | C2.P0 | Pre-flight config validator | **Cursor** | ✅ Merged |
| [BRIEF-007](./BRIEF-007-absolute-path-enforcement.md) | C2.P0 | Absolute path enforcement | **Cursor** | ✅ Merged |
| [BRIEF-008](./BRIEF-008-cost-dashboard-mvp.md) | C2.P0 | Cost & progress dashboard MVP | **Cursor** | ✅ Merged |
| [BRIEF-009](./BRIEF-009-phase-0-acceptance.md) | C2.P0 | Phase 0 forced-failure acceptance run | **Opus** (post-handoff) | ✅ Accepted — all 4 tests PASS |
| [BRIEF-004A](./BRIEF-004A-credit-detector-graceful-degrade.md) | C2.P0 patch | Credit detector: graceful degrade + test affordance | **Codex** | ✅ Merged |
| [BRIEF-010](./BRIEF-010-test-debt-cleanup.md) | Cleanup | Pre-existing test debt: 21 popscale failures + sklearn dep | flexible | 🟢 Open · LOW priority |
| [BRIEF-011](./BRIEF-011-haiku-tier-migration.md) | C2.P1 | Haiku tier migration (cost-critical) | Sonnet | 🔴 **DEFERRED to Phase 3** — Sprint A-3 evidence shows -3 to -25pp accuracy drop |
| [BRIEF-012](./BRIEF-012-prompt-cache-discipline.md) | C2.P1 | Prompt cache discipline | **Haiku** | 🟢 Open |
| [BRIEF-013](./BRIEF-013-structured-outputs.md) | C2.P1 | Structured outputs migration | **Sonnet** | 🟢 Open |
| [BRIEF-014](./BRIEF-014-parallel-cluster-execution.md) | C2.P1 | Parallel cluster + ensemble execution | **Sonnet** | 🟢 Open |
| [BRIEF-015](./BRIEF-015-rate-limit-governor.md) | C2.P1 | Rate-limit governor (token bucket) | **Haiku** | 🟢 Open |

**Phase 1 model allocation rationale**: Sonnet owns work that needs judgment (BRIEF-011 cost/quality tradeoffs, BRIEF-013 schema design, BRIEF-014 concurrency correctness). Haiku owns mechanical work with well-specified contracts (BRIEF-012 cache_control insertion, BRIEF-015 textbook token-bucket algorithm). Opus orchestrates and reviews.

**Sprint 1** (BRIEF-001 through 003) closed 2026-04-25 with the WB 2026 manifesto sensitivity rerun delivered.
**Construct Phase 2 / Phase 0** (BRIEF-004 through 008) opens 2026-04-25. Each brief on its own branch: `phase-0/brief-NNN-<slug>` off `main`. Briefs are parallel-safe and can ship in any order.

Phase 2 orientation docs (read these first): [`construct_phase_2/README.md`](../construct_phase_2/README.md) → PRINCIPLES → CONSTRUCT_PHASE_2 → CORE_SPEC → GROUND_TRUTH_REGISTRY.

---

## Where to send deliverables

Paste the full deliverable (all sections from your brief's "Deliverable format") into the coordinator chat. Coordinator reviews, rates, and issues a verdict.
