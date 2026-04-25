"""Minimal no-build dashboard server for run events."""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .emitter import list_runs, read_events


def _json_response(handler: BaseHTTPRequestHandler, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _html_page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css">
  <style>
    .pill {{ padding: .2rem .6rem; border-radius: 999px; font-size: .8rem; }}
    .status-running {{ background: #ffec99; }}
    .status-completed {{ background: #c3fae8; }}
    .status-failed {{ background: #ffc9c9; }}
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    pre {{ max-height: 320px; overflow: auto; }}
  </style>
</head>
<body>
<main class="container">
{body}
</main>
</body>
</html>"""


def _run_list_html(runs: list[dict[str, Any]]) -> str:
    rows = []
    for run in runs:
        status_class = f"status-{run['status'].lower()}"
        rows.append(
            f"<tr><td><a href='/runs/{run['run_id']}'>{run['run_id']}</a></td>"
            f"<td><span class='pill {status_class}'>{run['status']}</span></td>"
            f"<td>{run['updated_at']}</td><td>{run['event_count']}</td></tr>"
        )
    table = "".join(rows) if rows else "<tr><td colspan='4'>No runs found</td></tr>"
    return _html_page(
        "Simulatte Runs",
        (
            "<h2>Simulatte Runs (last 30 days)</h2>"
            "<table><thead><tr><th>Run</th><th>Status</th><th>Updated</th><th>Events</th></tr></thead>"
            f"<tbody>{table}</tbody></table>"
        ),
    )


def _run_dashboard_html(run_id: str) -> str:
    return _html_page(
        f"Run {run_id}",
        f"""
<h2>Run {run_id}</h2>
<article>
  <div id="topbar" class="mono">Loading...</div>
  <progress id="progress" value="0" max="100"></progress>
  <div class="grid">
    <article><header>Money</header><div id="money">-</div></article>
    <article><header>Burn Rate</header><div id="burn">-</div></article>
    <article><header>API Rate</header><div id="api-rate">-</div></article>
    <article><header>Last Error</header><div id="last-error">-</div></article>
  </div>
  <h4>Cluster Progress</h4>
  <pre id="cluster-grid"></pre>
  <h4>Live Event Tail (last 50)</h4>
  <pre id="tail"></pre>
</article>
<script>
let since = 0;
let events = [];
const runId = {json.dumps(run_id)};

function moneyColor(spent, budget) {{
  if (!budget) return "inherit";
  const ratio = spent / budget;
  if (ratio > 0.9) return "#c92a2a";
  if (ratio > 0.7) return "#e67700";
  return "#2b8a3e";
}}

function render() {{
  if (events.length === 0) return;
  const last = events[events.length - 1];
  const status = (last.type === "run_completed") ? "COMPLETED" : (last.type === "error" ? "FAILED" : "RUNNING");
  const started = events.find(e => e.type === "run_started");
  const clustersStarted = events.filter(e => e.type === "cluster_started");
  const clustersDone = events.filter(e => e.type === "cluster_completed");
  const apiCalls = events.filter(e => e.type === "api_call");
  const errs = events.filter(e => e.type === "error");
  const elapsedSec = started ? Math.max(0, last.unix_ts - started.unix_ts) : 0;
  const spent = apiCalls.reduce((a,e) => a + (e.cost_usd || 0), 0);
  const budget = started ? started.budget_usd : null;
  const rpm = elapsedSec > 0 ? (apiCalls.length / elapsedSec) * 60 : 0;
  const burn = elapsedSec > 0 ? (spent / elapsedSec) * 60 : 0;
  const progress = started && started.cluster_total ? (clustersDone.length / started.cluster_total) * 100 : 0;
  const etaMin = burn > 0 && budget ? Math.max(0, (budget - spent) / burn) : null;
  const topbar = `status=${{status}} | elapsed=${{elapsedSec.toFixed(0)}}s | eta=${{etaMin === null ? "-" : etaMin.toFixed(1) + "m"}}`;
  document.getElementById("topbar").textContent = topbar;
  document.getElementById("progress").value = progress;
  const moneyEl = document.getElementById("money");
  moneyEl.textContent = `$${{spent.toFixed(2)}} / ${{budget ? "$" + budget.toFixed(2) : "(no budget ceiling)"}}`;
  moneyEl.style.color = moneyColor(spent, budget);
  document.getElementById("burn").textContent = `$${{burn.toFixed(2)}}/min`;
  document.getElementById("api-rate").textContent = `${{rpm.toFixed(1)}} req/min`;
  document.getElementById("last-error").textContent = errs.length ? errs[errs.length - 1].msg : "None";
  const clusterLines = [];
  const byCluster = {{}};
  for (const c of clustersStarted) byCluster[c.cluster_id] = {{started:true, ensemblesDone:0}};
  for (const e of events.filter(e => e.type === "ensemble_completed")) {{
    byCluster[e.cluster_id] = byCluster[e.cluster_id] || {{started:true, ensemblesDone:0}};
    byCluster[e.cluster_id].ensemblesDone += 1;
  }}
  for (const c of clustersDone) {{
    byCluster[c.cluster_id] = byCluster[c.cluster_id] || {{}};
    byCluster[c.cluster_id].done = true;
  }}
  for (const [cid, state] of Object.entries(byCluster)) {{
    clusterLines.push(`${{cid}} :: ensembles=${{state.ensemblesDone || 0}} completed=${{state.done ? "yes" : "no"}}`);
  }}
  document.getElementById("cluster-grid").textContent = clusterLines.join("\\n") || "(no clusters yet)";
  const tail = events.slice(-50).map(e => `${{e.ts}}  ${{e.type}}  ${{JSON.stringify(e)}}`).join("\\n");
  document.getElementById("tail").textContent = tail;
}}

async function poll() {{
  const q = encodeURIComponent(String(since));
  const res = await fetch(`/runs/${{runId}}/events?since=${{q}}`);
  if (!res.ok) return;
  const payload = await res.json();
  for (const ev of payload.events) {{
    events.push(ev);
    since = Math.max(since, ev.unix_ts || 0);
  }}
  render();
}}

poll();
setInterval(poll, 5000);
</script>
""",
    )


def make_handler(runs_root: Path):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/":
                html = _run_list_html(list_runs(runs_root=runs_root))
                body = html.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if path.startswith("/runs/") and path.endswith("/events"):
                parts = path.strip("/").split("/")
                run_id = parts[1]
                query = parse_qs(parsed.query)
                since = float(query.get("since", ["0"])[0] or 0)
                events = read_events(run_id, since=since, runs_root=runs_root, limit=5000)
                _json_response(self, {"events": events})
                return

            if path.startswith("/runs/"):
                run_id = path.strip("/").split("/")[1]
                html = _run_dashboard_html(run_id)
                body = html.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()

        def log_message(self, fmt: str, *args: Any) -> None:
            return

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulatte observability dashboard server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--runs-root", type=Path, default=None)
    args = parser.parse_args()

    runs_root = (args.runs_root or (Path.home() / ".simulatte" / "runs")).resolve()
    runs_root.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(runs_root))
    print(f"Serving dashboard on http://{args.host}:{args.port}")
    print(f"Runs root: {runs_root}")
    server.serve_forever()


if __name__ == "__main__":
    main()

