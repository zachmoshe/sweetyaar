"""Logs API upload rules (cloud/logs_api/uploads.py), without Firestore."""

from __future__ import annotations

import datetime as dt
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "cloud/logs_api"))

import devlog  # noqa: E402
import uploads  # noqa: E402
from test_devlog_ble import DEVICE, header  # noqa: E402

ID = DEVICE.hex()
NOW = dt.datetime(2026, 11, 1, 12, tzinfo=dt.timezone.utc)


def sector(sequence: int, fill: int = 0, boot: int = 1, device: bytes = DEVICE) -> bytes:
    data = bytearray(b"\xff" * devlog.SECTOR_SIZE)
    data[:24] = header(sequence, boot, device)
    data[24:24 + 40 + fill] = bytes([sequence & 0xFF]) * (40 + fill)
    return bytes(data)


def body(*sequences: int) -> bytes:
    return b"".join(sector(sequence) for sequence in sequences)


def upload(device, tail, sectors, open_seq=None, replaces=None, now=NOW):
    return uploads.plan_upload(device, tail, sectors, open_seq=open_seq, replaces=replaces, now=now, app="t")


def test_split_validates_sectors() -> None:
    assert [s for s, _ in uploads.split_sectors(body(3, 4, 9), ID)] == [3, 4, 9]
    for bad, status in [(b"", 400), (body(1)[:-1], 400), (body(2, 1), 400), (body(1, 1), 400),
                        (sector(1, device=bytes(6)), 400), (b"\xff" * 4096, 400),
                        (body(*range(1, 66)), 413)]:
        with pytest.raises(uploads.UploadError) as error:
            uploads.split_sectors(bad, ID)
        assert error.value.status == status
    with pytest.raises(uploads.UploadError):
        uploads.parse_device("24:0a:c4:01:02:03")


def test_first_upload_then_append_and_replace_open_sector() -> None:
    plan = upload(None, b"", uploads.split_sectors(body(5, 6, 7), ID), open_seq=7)
    assert (plan.device.history, plan.device.seq, plan.device.open, plan.accepted) == (1, 7, True, 3)
    assert plan.chunks == {0: body(5, 6, 7)}
    # The open sector grew; one new sector after it.
    grown = sector(7, fill=100)
    plan = upload(plan.device, plan.chunks[0], [(7, grown), (8, sector(8))])
    assert plan.chunks == {0: body(5, 6) + grown + sector(8)}
    assert (plan.device.seq, plan.device.open, plan.accepted) == (8, False, 2)
    # A retry or a second phone: nothing changes.
    again = upload(plan.device, plan.chunks[0], [(6, sector(6)), (7, grown), (8, sector(8))])
    assert again.chunks == {} and again.accepted == 0 and again.device.seq == 8


def test_saved_chunk_reads_like_a_devlog_file() -> None:
    plan = upload(None, b"", uploads.split_sectors(body(1, 2, 4), ID))
    log = devlog.read_log(plan.chunks[0], devlog.load_catalog())
    assert [s.sequence for s in log.sectors] == [1, 2, 4]
    assert any("2 -> 4" in problem for problem in log.problems)  # the missing sector
    doc = uploads.chunk_doc(plan.chunks[0], NOW)
    assert (doc["first_seq"], doc["last_seq"], doc["sectors"]) == (1, 4, 3)


def test_chunks_roll_over() -> None:
    device, tail = None, b""
    chunks = {}
    for first in range(1, 401, 50):
        plan = upload(device, tail, uploads.split_sectors(body(*range(first, first + 50)), ID))
        chunks.update(plan.chunks)
        device, tail = plan.device, plan.chunks[plan.device.chunk]
    assert device.chunk == 2 and device.seq == 400
    assert [len(chunks[n]) // 4096 for n in (0, 1, 2)] == [192, 192, 16]
    assert devlog.header_sequence(chunks[1][:24]) == 193


def test_new_history() -> None:
    first = upload(None, b"", uploads.split_sectors(body(40, 41), ID))
    # The toy's partition started again: the app names the history it replaces.
    restarted = upload(first.device, first.chunks[0], [(1, sector(1, boot=1)), (2, sector(2))], replaces=1)
    assert (restarted.device.history, restarted.device.seq, restarted.device.chunk) == (2, 2, 0)
    assert restarted.chunks == {0: body(1, 2)}
    # Retrying that request later changes nothing.
    retry = upload(restarted.device, restarted.chunks[0], [(1, sector(1)), (2, sector(2))], replaces=1)
    assert retry.device.history == 2 and retry.accepted == 0
    # A different header at the newest stored sequence also means a new history.
    other = upload(restarted.device, restarted.chunks[0], [(2, sector(2, boot=9))])
    assert other.device.history == 3 and other.chunks == {0: sector(2, boot=9)}


def test_daily_cap() -> None:
    device = uploads.Device(cap_day="2026-11-01", cap_count=uploads.DAILY_SECTOR_CAP - 1)
    with pytest.raises(uploads.UploadError) as error:
        upload(device, b"", uploads.split_sectors(body(1, 2), ID))
    assert error.value.status == 429
    next_day = upload(device, b"", uploads.split_sectors(body(1, 2), ID), now=NOW + dt.timedelta(days=1))
    assert next_day.device.cap_count == 2


def test_device_document_round_trip() -> None:
    plan = upload(None, b"", uploads.split_sectors(body(5), ID), open_seq=5)
    doc = plan.device.to_doc()
    assert uploads.Device.from_doc({**doc, "unknown": 1}) == plan.device
    public = plan.device.public()
    assert public == {"history": 1, "seq": 5, "open": True, "header": header(5).hex(),
                      "last_upload": NOW.isoformat()}


def test_upload_days_once_per_day() -> None:
    first = upload(None, b"", uploads.split_sectors(body(1), ID))
    again = upload(first.device, first.chunks[0], uploads.split_sectors(body(2), ID), now=NOW + dt.timedelta(hours=1))
    later = upload(again.device, again.chunks[0], uploads.split_sectors(body(3), ID), now=NOW + dt.timedelta(days=2))
    assert first.device.upload_days == ["2026-11-01"]
    assert later.device.upload_days == ["2026-11-01", "2026-11-03"]
    assert first.device.upload_days == ["2026-11-01"]  # the earlier state is not changed
