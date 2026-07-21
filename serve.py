"""
Serve the Ripple live frontend AND launch runs from the browser.

This replaces `python -m http.server` for the interactive demo: it serves
outputs/frontend/ (index.html + the live events.json) and adds two endpoints:

  POST /run     body {"initiative": "...", "sector": "...", "org_size": "..."}
                -> launches one swarm in a background thread (409 if one is
                   already running). events.json updates live as it streams.
  GET  /status  -> {"running": bool, "error": str|null, "initiative": str|null}

So you can type the initiative straight into the page and watch the
negotiation play out. Part A still works standalone via `python run_ripple.py`.

Usage:
    python serve.py            # serves on http://localhost:8000
    python serve.py --port 9000
"""

import argparse
import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import run_ripple

STATE_LOCK = threading.Lock()
STATE = {"running": False, "error": None, "initiative": None}


def _launch(initiative, sector, org_size, frontend_url):
    """Run the swarm; keep STATE in sync so the UI can reflect progress/errors."""
    try:
        run_ripple.run_swarm(initiative, sector, org_size, frontend_url)
        err = None
    except Exception as exc:  # surface any failure to the browser
        err = str(exc)
        print(f"[serve] run failed: {err}")
    with STATE_LOCK:
        STATE["running"] = False
        STATE["error"] = err


class Handler(SimpleHTTPRequestHandler):
    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.split("?")[0] == "/status":
            with STATE_LOCK:
                return self._json(200, dict(STATE))
        return super().do_GET()

    def do_POST(self):
        if self.path.split("?")[0] != "/run":
            return self._json(404, {"error": "not found"})

        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json(400, {"error": "invalid JSON"})

        initiative = (payload.get("initiative") or "").strip()
        if not initiative:
            return self._json(400, {"error": "initiative is required"})

        err = run_ripple.preconditions_ok()
        if err:
            return self._json(400, {"error": err})

        with STATE_LOCK:
            if STATE["running"]:
                return self._json(409, {"error": "a run is already in progress"})
            STATE.update(running=True, error=None, initiative=initiative)

        sector = (payload.get("sector") or "").strip() or None
        org_size = (payload.get("org_size") or "").strip() or None
        frontend_url = payload.get("frontend_url") or f"http://localhost:{self.server.server_address[1]}"

        threading.Thread(
            target=_launch, args=(initiative, sector, org_size, frontend_url), daemon=True
        ).start()
        return self._json(202, {"ok": True, "initiative": initiative})

    def log_message(self, fmt, *args):  # quieter: skip the chatty file-serve logs
        msg = fmt % args
        if "/run" in msg or "/status" in msg:
            print(f"[serve] {msg}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Serve the Ripple frontend + launch runs.")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    handler = partial(Handler, directory=str(run_ripple.FRONTEND_DIR))
    server = ThreadingHTTPServer(("0.0.0.0", args.port), handler)
    url = f"http://localhost:{args.port}"
    print(f"Ripple frontend + control server on {url}")
    print(f"  serving:  {run_ripple.FRONTEND_DIR}")
    print("  open the page, type an initiative, hit Run.  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
