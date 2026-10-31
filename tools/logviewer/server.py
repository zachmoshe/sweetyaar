#!/usr/bin/env python3
"""Local log viewer: serves the merged history of every fetched log in a folder.

  server.py [--dir devlogs] [--port 8010]

Files are re-read when they change, so a new `make fetch-logs` shows up on the
next page load. Data comes from history.Library; a cloud source can later
provide the same snapshots.
"""

from __future__ import annotations

import argparse
import http.server
import json
import pathlib
import sys
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import history  # noqa: E402

STATIC = HERE / "static"
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8"}


def handler_for(library: history.Library) -> type:
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            url = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(url.query)
            try:
                if url.path == "/api/devices":
                    self.send_json({"directory": str(library.directory), "devices": library.devices()})
                elif url.path == "/api/device":
                    device = library.device(query.get("id", [""])[0])
                    self.send_json(device) if device else self.send_error(404, "Unknown device")
                elif url.path == "/api/stats":
                    self.send_json(library.stats())
                else:
                    self.send_static(url.path)
            except Exception as error:  # show decoding problems instead of a dropped connection
                self.send_json({"error": f"{type(error).__name__}: {error}"}, status=500)
                raise

        def send_json(self, value, status: int = 200) -> None:
            body = json.dumps(value, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def send_static(self, path: str) -> None:
            name = "index.html" if path in ("", "/") else path.lstrip("/")
            file = (STATIC / name).resolve()
            if STATIC not in file.parents or not file.is_file():
                self.send_error(404)
                return
            body = file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", TYPES.get(file.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            if args and str(args[1])[0] in "45":
                super().log_message(format, *args)

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", type=pathlib.Path, default=history.devlog.DEFAULT_DIR)
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()
    library = history.Library(args.dir.resolve())
    library.refresh()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(library))
    print(f"SweetYaar log viewer on http://localhost:{args.port}/ reading {library.directory} (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
