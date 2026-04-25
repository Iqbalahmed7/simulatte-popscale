from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.request import urlopen

from popscale.observability.emitter import RunEventEmitter
from popscale.observability.server import ThreadingHTTPServer, make_handler


def test_events_endpoint_since_filter(tmp_path: Path) -> None:
    run_id = "run-test-001"
    emitter = RunEventEmitter(run_id=run_id, runs_root=tmp_path)
    for i in range(100):
        emitter.emit("api_call", seq=i, cost_usd=0.001)

    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(tmp_path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        with urlopen(f"http://{host}:{port}/runs/{run_id}/events?since=0") as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        assert len(payload["events"]) == 100
        cutoff = payload["events"][59]["unix_ts"]
        with urlopen(f"http://{host}:{port}/runs/{run_id}/events?since={cutoff}") as resp:
            payload2 = json.loads(resp.read().decode("utf-8"))
        assert len(payload2["events"]) == 40
        assert payload2["events"][0]["seq"] == 60
    finally:
        server.shutdown()
        server.server_close()
