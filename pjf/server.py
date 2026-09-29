"""Small local server: serves the page and stores marks in marks.json.

Only listens on 127.0.0.1. On GitHub Pages there is no server, so the page
detects that and shows read-only.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import config, state

MARKS = {"hide", "interesting", "applied"}
KEY = re.compile(r"^[0-9a-f]{16}$")


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body: bytes, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, code=200):
        self._send(code, json.dumps(data).encode(), "application/json")

    def _local_host(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def do_GET(self):
        if not self._local_host():
            return self._send(403, b"forbidden", "text/plain")
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            try:
                return self._send(200, config.PAGE_FILE.read_bytes(), "text/html; charset=utf-8")
            except FileNotFoundError:
                return self._send(404, b"No page yet. Run: python pjf.py run", "text/plain")
        if path == "/api/marks":
            return self._json(state.load(config.MARKS_FILE, {}))
        self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if not self._local_host() or urlparse(self.path).path != "/api/marks":
            return self._send(404, b"not found", "text/plain")
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            return self._send(415, b"json only", "text/plain")
        try:
            length = min(int(self.headers.get("Content-Length") or 0), 10_000)
            req = json.loads(self.rfile.read(length) or b"{}")
            key, mark = req.get("key", ""), req.get("mark")
        except (ValueError, AttributeError):
            return self._send(400, b"bad request", "text/plain")
        if not KEY.match(str(key)) or (mark is not None and mark not in MARKS):
            return self._send(400, b"bad key or mark", "text/plain")
        marks = state.load(config.MARKS_FILE, {})
        if mark is None:
            marks.pop(key, None)
        else:
            marks[key] = {"mark": mark, "date": dt.date.today().isoformat()}
        state.save(config.MARKS_FILE, marks)
        self._json(marks)

    def log_message(self, *args):  # keep the console quiet
        pass


def make_server(port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(port=8765, open_browser=True):
    httpd = make_server(port)
    url = f"http://127.0.0.1:{port}/"
    print(f"Serving {url}  (marks are saved to marks.json). Ctrl+C to stop.")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        httpd.server_close()
