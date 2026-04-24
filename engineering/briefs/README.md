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
| [BRIEF-001](./BRIEF-001-cost-observability.md) | S1.1 | Cost observability instrumentation | **Cursor** | 🟢 Open |
| [BRIEF-002](./BRIEF-002-guardrails.md) | S1.2+S1.3 | Bounded retry + streaming + concurrency guardrail | **Codex** (GPT-5.3 medium) | 🟢 Open |

Both briefs are independent. Different files, no merge conflicts expected. Work in parallel.

After both are accepted, **BRIEF-003** (Sprint 1 closer: WB 2026 manifesto sensitivity re-run) will be released.

---

## Where to send deliverables

Paste the full deliverable (all sections from your brief's "Deliverable format") into the coordinator chat. Coordinator reviews, rates, and issues a verdict.
