# Construct Dashboard MVP

Local run dashboard for Simulatte benchmark events.

## Run locally

```bash
python -m popscale.observability.server --host 127.0.0.1 --port 8765
```

Open:

- `http://localhost:8765/` for run list
- `http://localhost:8765/runs/{run_id}` for a live run page

## Event source

Events are read from:

`~/.simulatte/runs/{run_id}/events.jsonl`

Written by `RunEventEmitter` in `popscale.observability.emitter`.

## Live run + dashboard (example)

Terminal 1:

```bash
python -m popscale.observability.server
```

Terminal 2:

```bash
python -m benchmarks.wb_2026.constituency.wb_2026_constituency_benchmark --manifesto both --budget-ceiling 75 --cost-trace /tmp/trace.csv
```

Then browse to:

`http://localhost:8765/runs/{run_id}`
