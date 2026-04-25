# BRIEF-008 — Cost & Progress Dashboard MVP

| Field | Value |
|---|---|
| Sprint | Construct Phase 2 / Phase 0 |
| Owner | **Cursor** |
| Estimate | 2 days |
| Branch | `phase-0/brief-008-cost-dashboard` |
| Status | 🟢 Open |
| Depends on | BRIEF-001 (cost observability) — already shipped, instrumentation in place |
| Blocks | nothing |

---

## Background

Run 7 was monitored by `tail -f /tmp/manifesto_run7.log | grep` at 1am. That is not how a production research platform handles a $400 study.

We need a live web view that shows what's running, what's been spent, and what's about to fail — so the operator (currently Iqbal, eventually a customer) sees state at a glance.

This is the MVP. Polished dashboards are Phase 4. Today's goal: a single page that updates every 5 seconds and tells you everything you'd otherwise have to grep for.

---

## Goal

Ship a single-page web UI at `https://construct.simulatte.io/runs/{run_id}` (or local `http://localhost:8765/runs/{run_id}`) that displays, for any active or completed run:

- Run progress (clusters done / total, ensembles done / total)
- Money spent and burn rate
- API call rate (requests/min)
- Last error (if any)
- Estimated time + cost remaining
- Live tail of structured log events (last 50)

---

## Files in scope

```
simulatte-workspace/popscale/
├── popscale/
│   ├── observability/
│   │   ├── emitter.py             # NEW — append events to runs/{run_id}/events.jsonl
│   │   └── server.py              # NEW — FastAPI/Flask server reading events.jsonl
│   └── benchmarks/wb_2026/constituency/
│       └── wb_2026_constituency_benchmark.py    # call emitter at key checkpoints
└── construct-dashboard/
    ├── README.md                  # NEW — how to run locally + deploy
    ├── package.json               # OR keep server-rendered HTML
    ├── src/
    │   └── ui/                    # static HTML + JS, no SPA framework needed
    └── tests/
```

---

## Acceptance criteria

1. **Event emission** — the benchmark emits structured events at key checkpoints:
   ```jsonl
   {"ts":"...","type":"run_started","run_id":"...","cluster_total":5,"budget_usd":90}
   {"ts":"...","type":"cluster_started","cluster_id":"murshidabad",...}
   {"ts":"...","type":"ensemble_started","cluster_id":"...","ensemble_idx":1}
   {"ts":"...","type":"api_call","cost_usd":0.0023,"model":"haiku","cache_hit":true}
   {"ts":"...","type":"ensemble_completed","cluster_id":"...","ensemble_idx":1,"result":{...}}
   {"ts":"...","type":"cluster_completed","cluster_id":"...","ensemble_avg":{...}}
   {"ts":"...","type":"error","level":"WARNING","msg":"...","persona":"..."}
   {"ts":"...","type":"run_completed","total_cost_usd":87.40,"duration_s":9420}
   ```
   Stored as JSONL at `runs/{run_id}/events.jsonl` (append-only).

2. **Server** — a single binary (Python) serves:
   - `GET /` → list of runs (last 30 days)
   - `GET /runs/{run_id}` → live page for one run
   - `GET /runs/{run_id}/events?since=ts` → SSE stream OR JSON poll endpoint of new events

3. **UI** — single HTML page that polls or streams events:
   - **Top bar:** run_id, status pill (RUNNING / COMPLETED / FAILED), elapsed, ETA
   - **Progress bar:** clusters done / total
   - **Money widget:** `$ spent / $ budget`, with color: green <70%, yellow 70-90%, red >90%
   - **Burn rate:** $ per minute, calculated from last 5 min
   - **API rate:** requests/min
   - **Cluster grid:** small card per cluster, with ensemble-level subprogress
   - **Last error pill:** clickable, expands to show stack trace
   - **Live log tail:** last 50 events, color-coded by type

4. **No-build front-end** — plain HTML + a single JS file (no React/Next/Webpack). Use server-side rendering of the shell + client-side fetch polling for updates.

5. **Refresh cadence** — UI polls `events?since=` every 5 seconds. SSE is nice-to-have, polling is acceptable.

6. **Local-first** — works locally with `python -m popscale.observability.server`. Cloud deployment (Vercel / Railway) deferred.

7. **Tests** — basic integration test: emit 100 events to a fixture file; assert the server returns them via the polling endpoint with correct since-filter.

---

## Implementation notes

- Use **Pico.css** or **Simple.css** for instant nice-looking UI without configuration.
- Use **Server-Sent Events** if you want live push without polling overhead — but a 5-second poll is fine for MVP.
- Storage: JSONL flat files are simpler than SQLite for now. If we hit scaling problems later, migrate.
- Money widget color thresholds reference `--budget-ceiling`. If no ceiling is set, just show absolute spend with no color logic.
- The "last error" pill should be deduplicated — if the same error fires 100 times (say, JSON parse fallback), show "100× JSON parse failed (most recent at 01:06:20)".

---

## Deliverable format

- Summary of approach (1 paragraph)
- Screenshot of the UI mid-run (use the WB 2026 events.jsonl as a fixture if needed; replay it)
- Screenshot of UI for a completed run
- Local-run instructions (one-liner to start the server + tail a live run)
- Performance: dashboard refreshes within 5s of a real event with <100ms latency on the polling endpoint

---

## Out-of-scope

- Authentication (single-user local only for MVP)
- Cloud deployment (later — when we have customer-facing runs)
- Historical analytics across many runs (Phase 4)
- Alerts / notifications (BRIEF-004 owns push; dashboard reflects state, doesn't notify)
- Multi-tenant features

---

## Reference

- `PRINCIPLES.md` P3, P4, P9
- `CORE_SPEC.md` §6 (observability contract — fields to emit)
- BRIEF-001 (already-shipped cost instrumentation; this brief consumes its output)
