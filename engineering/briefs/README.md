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
| [BRIEF-009](./BRIEF-009-phase-0-acceptance.md) | C2.P0 | Phase 0 forced-failure acceptance run | **Cursor or Codex** | 🟢 Open |

**Sprint 1** (BRIEF-001 through 003) closed 2026-04-25 with the WB 2026 manifesto sensitivity rerun delivered.
**Construct Phase 2 / Phase 0** (BRIEF-004 through 008) opens 2026-04-25. Each brief on its own branch: `phase-0/brief-NNN-<slug>` off `main`. Briefs are parallel-safe and can ship in any order.

Phase 2 orientation docs (read these first): [`construct_phase_2/README.md`](../construct_phase_2/README.md) → PRINCIPLES → CONSTRUCT_PHASE_2 → CORE_SPEC → GROUND_TRUTH_REGISTRY.

---

## Where to send deliverables

Paste the full deliverable (all sections from your brief's "Deliverable format") into the coordinator chat. Coordinator reviews, rates, and issues a verdict.
