"""Upload rules of the logs API, without Firestore, so host tests can run them.

A toy's uploads are kept per history (a history restarts when the toy's log
partition starts again) in chunks of at most CHUNK_SECTORS whole sectors, in
sequence order: a chunk's bytes are exactly a devlog file, which devlog.py and
the viewer read. See "Sending logs to the cloud" in docs/logging-and-debugging.md.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import re

import devlog

SECTOR_SIZE = devlog.SECTOR_SIZE
HEADER_SIZE = devlog.SECTOR_HEADER_SIZE
CHUNK_SECTORS = 192        # 768 KiB: under Firestore's 1 MiB document limit
MAX_UPLOAD_SECTORS = 64    # per request
DAILY_SECTOR_CAP = 800     # per toy and UTC day: two full rings
UPLOAD_DAYS_KEPT = 400     # UTC days with an upload, for the viewer's fleet charts
DEVICE_PATTERN = re.compile(r"[0-9a-f]{12}")


class UploadError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def parse_device(text: str) -> str:
    """The toy's ID: its factory MAC (eFuse), 12 lowercase hex digits."""
    if not DEVICE_PATTERN.fullmatch(text):
        raise UploadError(404, "unknown device ID")
    return text


def split_sectors(body: bytes, device: str) -> list[tuple[int, bytes]]:
    """Whole sectors of this toy in rising sequence order: [(sequence, sector)]."""
    if not body or len(body) % SECTOR_SIZE:
        raise UploadError(400, "the body must be whole 4096-byte sectors")
    if len(body) > MAX_UPLOAD_SECTORS * SECTOR_SIZE:
        raise UploadError(413, f"at most {MAX_UPLOAD_SECTORS} sectors per upload")
    sectors = []
    for start in range(0, len(body), SECTOR_SIZE):
        sector = body[start:start + SECTOR_SIZE]
        sequence = devlog.header_sequence(sector[:HEADER_SIZE])
        if sequence is None:
            raise UploadError(400, f"sector {len(sectors)} has no valid header")
        if sector[16:22].hex() != device:
            raise UploadError(400, f"sector {len(sectors)} belongs to another device")
        if sectors and sequence <= sectors[-1][0]:
            raise UploadError(400, "sectors must be in rising sequence order")
        sectors.append((sequence, bytes(sector)))
    return sectors


def chunk_id(history: int, chunk: int) -> str:
    return f"{history:03d}-{chunk:04d}"


@dataclasses.dataclass
class Device:
    """The toy's document: where its uploads stand."""
    history: int = 1
    seq: int | None = None          # newest stored sequence
    header: bytes | None = None     # that sector's header
    open: bool = False              # it was still being written when uploaded
    chunk: int = 0                  # the chunk holding it
    first_upload: dt.datetime | None = None
    last_upload: dt.datetime | None = None
    cap_day: str = ""
    cap_count: int = 0
    app: str = ""
    upload_days: list[str] = dataclasses.field(default_factory=list)  # ISO, oldest first

    @classmethod
    def from_doc(cls, doc: dict) -> Device:
        names = {field.name for field in dataclasses.fields(cls)}
        return cls(**{key: value for key, value in doc.items() if key in names})

    def to_doc(self) -> dict:
        return dataclasses.asdict(self)

    def public(self) -> dict:
        """The answer to GET .../latest and to an upload."""
        return {
            "history": self.history,
            "seq": self.seq,
            "open": self.open,
            "header": self.header.hex() if self.header else None,
            "last_upload": self.last_upload.isoformat() if self.last_upload else None,
        }


@dataclasses.dataclass
class Plan:
    device: Device
    chunks: dict[int, bytes]  # chunk number (in device.history) -> its new bytes
    accepted: int


def plan_upload(device: Device | None, tail: bytes, sectors: list[tuple[int, bytes]], *,
                open_seq: int | None, replaces: int | None, now: dt.datetime, app: str) -> Plan:
    """Merges uploaded sectors into the toy's last chunk (|tail|).

    Sectors older than the newest stored one are already stored (another
    phone, or a retry) and skipped. The newest one is replaced when it grew.
    When the toy's log no longer continues the stored history, the app names
    that history in |replaces|; a retry after the new one began then changes
    nothing. A different header at the newest stored sequence also starts a
    new history.
    """
    state = dataclasses.replace(device) if device else Device()
    data = bytearray(tail if device else b"")
    if device and state.seq is not None:
        stored = dict(sectors).get(state.seq)
        differs = stored is not None and stored[:HEADER_SIZE] != state.header
        if differs or (replaces == state.history and stored is None):
            state = dataclasses.replace(state, history=state.history + 1, seq=None, header=None,
                                        open=False, chunk=0)
            data = bytearray()

    day = now.date().isoformat()
    if state.cap_day != day:
        state.cap_day, state.cap_count = day, 0
    if state.cap_count + len(sectors) > DAILY_SECTOR_CAP:
        raise UploadError(429, "daily upload limit reached for this toy")

    chunks: dict[int, bytes] = {}
    dirty = False
    accepted = 0
    for sequence, sector in sectors:
        if state.seq is not None and sequence < state.seq:
            continue
        if sequence == state.seq:
            if bytes(data[-SECTOR_SIZE:]) == sector:
                continue
            data[-SECTOR_SIZE:] = sector
        else:
            if len(data) >= CHUNK_SECTORS * SECTOR_SIZE:
                chunks[state.chunk] = bytes(data)
                state.chunk += 1
                data = bytearray()
            data += sector
            state.seq, state.header = sequence, sector[:HEADER_SIZE]
        dirty = True
        accepted += 1
    if dirty:
        chunks[state.chunk] = bytes(data)
    if accepted:
        state.open = open_seq is not None and open_seq == state.seq
    state.cap_count += len(sectors)
    state.first_upload = state.first_upload or now
    state.last_upload = now
    if not state.upload_days or state.upload_days[-1] != day:
        state.upload_days = [*state.upload_days, day][-UPLOAD_DAYS_KEPT:]
    state.app = app[:40]
    return Plan(state, chunks, accepted)


def chunk_doc(data: bytes, now: dt.datetime) -> dict:
    return {
        "data": data,
        "first_seq": devlog.header_sequence(data[:HEADER_SIZE]),
        "last_seq": devlog.header_sequence(data[-SECTOR_SIZE:][:HEADER_SIZE]),
        "sectors": len(data) // SECTOR_SIZE,
        "updated": now,
    }
