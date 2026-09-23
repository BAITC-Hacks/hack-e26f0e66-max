#!/usr/bin/env python3
"""Serve the standalone interface.

A plain `http.server` — no framework and no new dependency. It serves `web/`
at `/` and the pipeline's results at `/data/`, so the page can fetch
`data/web_data.json` and offer the exports as direct downloads.

    python web/serve.py                # serves and opens a browser
    python web/serve.py --port 8080 --no-browser
"""

from __future__ import annotations

import argparse
import functools
import http.server
import socket
import socketserver
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

WEB = ROOT / "web"


class Handler(http.server.SimpleHTTPRequestHandler):
    """Serves `web/`, with `/data/...` mapped onto the outputs folder."""

    out_dir = ROOT / "output_files"

    def translate_path(self, path: str) -> str:
        clean = path.split("?", 1)[0].split("#", 1)[0]
        if clean.startswith("/data/"):
            rel = clean[len("/data/"):].lstrip("/")
            # Resolve and confine: a served path must stay inside out_dir.
            target = (self.out_dir / rel).resolve()
            try:
                target.relative_to(self.out_dir.resolve())
            except ValueError:
                return str(self.out_dir)
            return str(target)
        return super().translate_path(path)

    def end_headers(self):
        # Results change on every run; a cached web_data.json would show stale
        # numbers with no clue why.
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass                      # the launcher prints what matters


def free_port(preferred: int) -> int:
    """Use `preferred` if it is free, otherwise let the OS pick one."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def prepare() -> tuple[bool, str]:
    """Vendor vis-network and confirm the data file is there."""
    try:
        from moneygraph.webexport import vendor_assets

        vendor_assets(WEB)
    except Exception as exc:
        return False, f"could not vendor vis-network: {type(exc).__name__}: {exc}"
    data = Handler.out_dir / "web_data.json"
    if not data.exists():
        return False, (f"{data} not found — run the pipeline first:\n"
                       f"    ./agent_run.sh")
    return True, ""


def main() -> int:
    ap = argparse.ArgumentParser(description="Money Graph — standalone interface")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()

    ok, problem = prepare()
    if not ok:
        print(problem, file=sys.stderr)
        return 2

    port = free_port(a.port)
    handler = functools.partial(Handler, directory=str(WEB))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((a.host, port), handler) as httpd:
        url = f"http://{a.host}:{port}/"
        print(f"Money Graph — standalone interface on {url}")
        print("Ctrl+C to stop.")
        if not a.no_browser:
            threading.Timer(0.6, lambda: webbrowser.open(url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
