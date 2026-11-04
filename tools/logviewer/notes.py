"""Notes the developer writes on a device's timeline ("speaker disconnected
here"). They never come from the toy. Every viewer, local or the SweetYaar
Admin app on Cloud Run, keeps them in one JSON object in the admin resources
bucket (BUCKET, OBJECT), as the sweetyaar-admin service account, so there is
one set of notes for the folder and the cloud logs alike.

A note is {"id", "text", "start", "end"}; start and end (end is null for a
moment) are {"boot", "ms"}: the toy's boot number and uptime, which stay
put when later fetches move estimated wall times.
"""

from __future__ import annotations

import json
import os
import pathlib
import threading
import urllib.error
import urllib.parse
import urllib.request

BUCKET = "sweetyaar-admin-resources"
OBJECT = "logs-viewer/annotations.json"
MAX_TEXT = 2000
MAX_NOTES = 500  # per device
SAVE_ATTEMPTS = 3


class Conflict(Exception):
    """The notes changed since they were read."""


class BucketStore:
    """The notes object, written only over the generation it was read at."""

    def __init__(self, token, bucket: str = BUCKET, name: str = OBJECT, fetch=urllib.request.urlopen):
        """|token| returns a sweetyaar-admin access token."""
        self.token, self.bucket, self.name, self.fetch = token, bucket, name, fetch
        self.label = f"gs://{bucket}/{name}"

    def load(self) -> tuple[dict, int]:
        """The notes and their generation (0: no object yet)."""
        name = urllib.parse.quote(self.name, safe="")
        try:
            with self.fetch(self._request(f"https://storage.googleapis.com/storage/v1/b/{self.bucket}/o/{name}"
                                          "?alt=media"), timeout=30) as response:
                return json.loads(response.read() or b"{}"), int(response.headers["x-goog-generation"])
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return {}, 0
            raise

    def save(self, everything: dict, generation: int) -> None:
        query = urllib.parse.urlencode({"uploadType": "media", "name": self.name, "ifGenerationMatch": generation})
        body = (json.dumps(everything, indent=1, ensure_ascii=False) + "\n").encode()
        request = self._request(f"https://storage.googleapis.com/upload/storage/v1/b/{self.bucket}/o?{query}",
                                body, {"Content-Type": "application/json"})
        try:
            with self.fetch(request, timeout=30):
                pass
        except urllib.error.HTTPError as error:
            if error.code == 412:
                raise Conflict() from None
            raise

    def _request(self, url: str, data: bytes | None = None, headers: dict | None = None) -> urllib.request.Request:
        return urllib.request.Request(url, data=data, method="POST" if data is not None else "GET",
                                      headers={"Authorization": f"Bearer {self.token()}", **(headers or {})})


class FileStore:
    """A local file, for tests."""

    def __init__(self, path: str | pathlib.Path):
        self.path = pathlib.Path(path)
        self.label = str(self.path)

    def load(self) -> tuple[dict, int]:
        try:
            return json.loads(self.path.read_text()), int(self.path.stat().st_mtime_ns)
        except FileNotFoundError:
            return {}, 0

    def save(self, everything: dict, generation: int) -> None:
        if self.load()[1] != generation:
            raise Conflict()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(everything, indent=1, ensure_ascii=False) + "\n")
        os.replace(temporary, self.path)


class Notes:
    def __init__(self, store: BucketStore | FileStore):
        self.store = store
        self._lock = threading.Lock()

    def get(self, device: str) -> list[dict]:
        return self.store.load()[0].get(device, [])

    def put(self, device: str, notes: list) -> list[dict]:
        """Replaces the device's notes; raises ValueError on a malformed one.
        Another viewer's save in between is kept: the change is applied again
        to what it wrote."""
        clean = [check(note) for note in notes]
        if len(clean) > MAX_NOTES:
            raise ValueError(f"at most {MAX_NOTES} notes per device")
        with self._lock:
            for attempt in range(SAVE_ATTEMPTS):
                everything, generation = self.store.load()
                if clean:
                    everything[device] = clean
                else:
                    everything.pop(device, None)
                try:
                    self.store.save(everything, generation)
                    return clean
                except Conflict:
                    if attempt == SAVE_ATTEMPTS - 1:
                        raise RuntimeError("the notes kept changing while saving; try again") from None
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
