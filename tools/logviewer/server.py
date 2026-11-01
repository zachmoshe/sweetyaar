#!/usr/bin/env python3
"""Local log viewer: serves the merged history of every log in a folder, or
of every upload the parent app sent to the cloud (picked in the page).

  server.py [--dir devlogs] [--port 8010] [--project sweetyaar]

Files are re-read when they change, so a new `make fetch-logs` shows up on the
next page load. Data comes from history.Library. The cloud is read as the
logs-viewer service account, with tokens from the gcloud CLI's login (see
"Sending logs to the cloud" in docs/logging-and-debugging.md).
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

import coredump  # noqa: E402
import history  # noqa: E402
import notes  # noqa: E402

STATIC = HERE / "static"
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8"}


def handler_for(folder: history.Library, cloud=None, annotations: notes.Notes | None = None,
                decoder: coredump.Decoder | None = None) -> type:
    """|cloud| returns the cloud library, created on first use; |annotations|
    holds the developer's notes (both sources); |decoder| decodes core dumps."""
    def library_for(query: dict) -> history.Library:
        if query.get("source", ["folder"])[0] != "cloud":
            return folder
        if cloud is None:
            raise LookupError("No cloud source configured")
        return cloud()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            url = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(url.query)
            try:
                if url.path.startswith("/api/"):
                    library = library_for(query)
                    if query.get("reload"):
                        library.refresh(force=True)
                if url.path in ("/api/core", "/api/core/decode"):
                    self.send_core(library, query, decode=url.path.endswith("decode"))
                elif url.path == "/api/notes":
                    self.send_json(annotations.get(query.get("device", [""])[0]) if annotations else [])
                elif url.path == "/api/devices":
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

        def do_PUT(self) -> None:  # noqa: N802
            url = urllib.parse.urlparse(self.path)
            device = urllib.parse.parse_qs(url.query).get("device", [""])[0]
            if url.path != "/api/notes" or not annotations or not device:
                self.send_error(404)
                return
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"[]")
                if not isinstance(body, list):
                    raise ValueError("expected a list of notes")
                self.send_json(annotations.put(device, body))
            except ValueError as error:
                self.send_json({"error": str(error)}, status=400)

        def send_core(self, library: history.Library, query: dict, decode: bool) -> None:
            device, boot = query.get("id", [""])[0], int(query.get("boot", ["-1"])[0])
            found = library.core(device, boot)
            if found is None:
                self.send_json({"error": "No complete core dump at that boot"}, status=404)
                return
            data, firmware = found
            if decode:
                try:
                    if decoder is None:
                        raise coredump.DecodeError("No core dump decoder configured")
                    self.send_json({"firmware": firmware, "text": decoder.decode(data, firmware)})
                except coredump.DecodeError as error:
                    self.send_json({"error": str(error)}, status=422)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition",
                             f'attachment; filename="devlog-{device.replace(":", "").lower()}-boot{boot}-core.bin"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

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
    parser.add_argument("--project", default="sweetyaar", help="GCP project of the logs API")
    args = parser.parse_args()
    library = history.Library(args.dir.resolve())
    library.refresh()
    cloud_library = []

    def cloud() -> history.Library:
        if not cloud_library:
            cloud_library.append(history.Library(history.CloudSource(args.project)))
        return cloud_library[0]

    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(
        library, cloud, notes.Notes(args.dir.resolve()),
        coredump.Decoder(lambda: history.CloudSource(args.project).token()[0])))
    print(f"SweetYaar log viewer on http://localhost:{args.port}/ reading {library.directory} (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
