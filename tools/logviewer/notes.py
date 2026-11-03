"""Notes the developer writes on a device's timeline ("speaker disconnected
here"). They never come from the toy, and they are the developer's own: one
file per user, outside the repository (DEFAULT_FILE), for the folder and the
cloud logs alike.

A note is {"id", "text", "start", "end"}; start and end (end is null for a
moment) are {"boot", "ms"}: the toy's boot number and uptime, which stay
put when later fetches move estimated wall times.
"""

from __future__ import annotations

import json
import os
import pathlib
import threading

FILE = "annotations.json"
# Per-user data (XDG), not a cache: cleaning caches must not delete notes.
DEFAULT_FILE = (pathlib.Path(os.environ.get("XDG_DATA_HOME") or pathlib.Path.home() / ".local/share")
                / "sweetyaar" / "logviewer" / FILE)
MAX_TEXT = 2000
MAX_NOTES = 500  # per device


class Notes:
    def __init__(self, path: str | pathlib.Path = DEFAULT_FILE):
        self.path = pathlib.Path(path)
        self._lock = threading.Lock()

    def _load(self) -> dict:
        try:
            return json.loads(self.path.read_text())
        except FileNotFoundError:
            return {}

    def get(self, device: str) -> list[dict]:
        with self._lock:
            return self._load().get(device, [])

    def put(self, device: str, notes: list) -> list[dict]:
        """Replaces the device's notes; raises ValueError on a malformed one."""
        clean = [check(note) for note in notes]
        if len(clean) > MAX_NOTES:
            raise ValueError(f"at most {MAX_NOTES} notes per device")
        with self._lock:
            everything = self._load()
            if clean:
                everything[device] = clean
            else:
                everything.pop(device, None)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(everything, indent=1, ensure_ascii=False) + "\n")
            os.replace(temporary, self.path)
        return clean


def point(value) -> dict:
    if (not isinstance(value, dict) or not all(isinstance(value.get(key), int) and not isinstance(value.get(key), bool)
                                               for key in ("boot", "ms"))):
        raise ValueError("a note's start and end are {boot, ms}")
    return {"boot": value["boot"], "ms": value["ms"]}


def check(note) -> dict:
    if not isinstance(note, dict) or not isinstance(note.get("id"), str) or not note["id"]:
        raise ValueError("a note needs an id")
    text = note.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
        raise ValueError(f"a note's text is 1-{MAX_TEXT} characters")
    start = point(note.get("start"))
    end = point(note["end"]) if note.get("end") is not None else None
    if end and (end["boot"], end["ms"]) < (start["boot"], start["ms"]):
        start, end = end, start
    return {"id": note["id"][:40], "text": text, "start": start, "end": end}
