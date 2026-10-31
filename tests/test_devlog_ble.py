"""Log fetch over BLE: the firmware's sender on the host, and the Mac script against a fake toy."""

from __future__ import annotations

import asyncio
import datetime as dt
import pathlib
import shutil
import struct
import sys

import pytest

from helpers import run_checked

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "firmware/esp32/src"
sys.path.insert(0, str(ROOT / "tools"))

import devlog  # noqa: E402
import devlog_ble  # noqa: E402

SECTOR = devlog.SECTOR_SIZE
DEVICE = bytes.fromhex("240ac4010203")


def test_transfer_sender(repo_root: pathlib.Path, tmp_path: pathlib.Path) -> None:
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("A C++ compiler is required.")
    exe = tmp_path / "transfer"
    run_checked([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", SRC,
                 repo_root / "tests/devlog_transfer_native_test.cpp", SRC / "DevLogTransfer.cpp", "-o", exe])
    assert "devlog transfer tests passed" in run_checked([exe]).stdout


def header(sequence: int, boot: int = 1, device: bytes = DEVICE) -> bytes:
    head = b"SYLG" + bytes([devlog.FORMAT_VERSION, devlog.SECTOR_HEADER_SIZE]) + b"\xff\xff"
    head += struct.pack("<II", sequence, boot) + device + b"\xff"
    return head + bytes([devlog.crc8(head)])


def partition(sequences: dict[int, int], count: int = 16, fill: int = 0) -> bytearray:
    """Sectors at the given indices with headers and recognizable contents."""
    image = bytearray(b"\xff" * (count * SECTOR))
    for index, sequence in sequences.items():
        start = index * SECTOR
        image[start:start + 24] = header(sequence)
        image[start + 24:start + 64] = bytes([(sequence + fill) & 0xFF]) * 40
    return image


def headers_of(image: bytes) -> bytes:
    return b"".join(image[i:i + 24] for i in range(0, len(image), SECTOR))


class FakeToy:
    """Answers read requests like DevLogTransfer.cpp, optionally losing packets."""

    def __init__(self, log: bytearray, core: bytes = b"", payload: int = 200, lose: tuple[int, ...] = ()):
        self.log, self.core, self.payload = log, core, payload
        self.lose = set(lose)  # packet numbers to drop, counted over the whole fetch
        self.sent = 0
        self.requests: list[tuple[int, int, int]] = []
        self.link = devlog_ble.Link(self.request)
        self.on_request = None  # hook: change the log between requests

    def region(self, region: int) -> bytes:
        if region == devlog_ble.REGION_INFO:
            return (bytes([devlog_ble.INFO_FORMAT]) + DEVICE + bytes([24]) +
                    struct.pack("<III", SECTOR, len(self.log), len(self.core)))
        if region == devlog_ble.REGION_HEADERS:
            return headers_of(self.log)
        return bytes(self.log) if region == devlog_ble.REGION_LOG else self.core

    async def request(self, data: bytes) -> None:
        command, region, offset, length = struct.unpack("<BBII", data)
        assert command == devlog_ble.READ_LOG
        self.requests.append((region, offset, length))
        if self.on_request:
            self.on_request(self)
        source = self.region(region)
        end = min(offset + length, len(source))
        if offset >= end:
            self.deliver(struct.pack("<BI", region, offset))
        while offset < end:
            body = source[offset:min(end, offset + self.payload)]
            self.deliver(struct.pack("<BI", region, offset) + body)
            offset += len(body)

    def deliver(self, packet: bytes) -> None:
        self.sent += 1
        if self.sent not in self.lose:
            self.link.on_packet(None, bytearray(packet))


def fetch(toy: FakeToy, out: pathlib.Path, full: bool = False) -> devlog_ble.Result:
    return asyncio.run(devlog_ble.read_log(toy.link, out, full, progress=lambda _: None))


def fetch_and_save(toy: FakeToy, out: pathlib.Path, minute: int, full: bool = False):
    result = fetch(toy, out, full)
    written, removed = devlog_ble.save(result, out, dt.datetime(2026, 10, 31, 18, minute, 0))
    return result, written, removed


def sectors_in(image: bytes, *sequences: int) -> bytes:
    """The sectors of a partition image with these sequences, in that order."""
    by_sequence = devlog.sector_map(image)
    return b"".join(by_sequence[sequence] for sequence in sequences)


def saved(out: pathlib.Path, device: bytes = DEVICE) -> list[pathlib.Path]:
    return devlog.saved_logs(out, device)


def log_reads(toy: FakeToy) -> list[tuple[int, int, int]]:
    return [request for request in toy.requests if request[0] == devlog_ble.REGION_LOG]


def test_first_fetch_saves_only_sectors_with_headers(tmp_path: pathlib.Path) -> None:
    toy = FakeToy(partition({0: 1, 1: 2, 2: 3}))
    result, written, removed = fetch_and_save(toy, tmp_path, 0)
    assert sorted(result.fetched) == [1, 2, 3] and result.core is None and removed == []
    assert [path.name for path in written] == [f"devlog-{DEVICE.hex()}-20261031-180000.bin"]
    assert written[0].read_bytes() == sectors_in(toy.log, 1, 2, 3)  # 12 KiB, no erased sectors
    assert log_reads(toy) == [(devlog_ble.REGION_LOG, 0, 3 * SECTOR)]


def test_later_fetch_appends_to_the_one_file(tmp_path: pathlib.Path) -> None:
    fetch_and_save(FakeToy(partition({0: 1, 1: 2, 2: 3})), tmp_path, 0)
    # Sector 3 was being written and grew; 4 and 5 are new; 1 and 2 are unchanged.
    now = partition({0: 1, 1: 2, 2: 3, 3: 4, 4: 5})
    now[2 * SECTOR + 100] = 0x42
    toy = FakeToy(now)
    result, written, removed = fetch_and_save(toy, tmp_path, 5)
    assert sorted(result.fetched) == [3, 4, 5]
    assert log_reads(toy) == [(devlog_ble.REGION_LOG, 2 * SECTOR, 3 * SECTOR)]
    assert saved(tmp_path) == written and written[0].name.endswith("20261031-180500.bin")
    assert written[0].read_bytes() == sectors_in(now, 1, 2, 3, 4, 5)
    assert [path.name for path in removed] == [f"devlog-{DEVICE.hex()}-20261031-180000.bin"]
    # --full reads everything again and still leaves one file.
    toy = FakeToy(now)
    result, written, _ = fetch_and_save(toy, tmp_path, 10, full=True)
    assert sorted(result.fetched) == [1, 2, 3, 4, 5] and saved(tmp_path) == written


def test_whole_partition_files_are_replaced_and_other_devices_kept(tmp_path: pathlib.Path) -> None:
    older = partition({0: 1, 1: 2})
    newer = partition({0: 1, 1: 2, 2: 3})
    newer[SECTOR + 200] = 0x11  # sector 2 grew after the older fetch
    for name, image in (("20261030-120000", older), ("20261031-170000", newer)):
        (tmp_path / f"devlog-{DEVICE.hex()}-{name}.bin").write_bytes(bytes(image))
    other = tmp_path / "devlog-aabbcc001122-20261031-170000.bin"
    other.write_bytes(bytes(partition({0: 1})))
    toy = FakeToy(partition({0: 1, 1: 2, 2: 3, 3: 4}))
    toy.log[SECTOR + 200] = 0x11
    result, written, removed = fetch_and_save(toy, tmp_path, 0)
    assert sorted(result.fetched) == [3, 4]  # the old images' newest sector and the new one
    assert written[0].read_bytes() == sectors_in(toy.log, 1, 2, 3, 4)
    assert len(removed) == 2 and saved(tmp_path) == written and other.exists()


def test_a_new_history_starts_a_new_file_and_keeps_the_old(tmp_path: pathlib.Path) -> None:
    fetch_and_save(FakeToy(partition({0: 1, 1: 2, 2: 3, 3: 4}, fill=7)), tmp_path, 0)
    now = partition({0: 1, 1: 2})  # erased: same headers as before, different records
    result, written, removed = fetch_and_save(FakeToy(now), tmp_path, 5)
    assert sorted(result.fetched) == [1, 2] and removed == []
    assert written[0].read_bytes() == sectors_in(now, 1, 2)
    assert len(saved(tmp_path)) == 2


def test_a_file_holds_at_most_one_partition(tmp_path: pathlib.Path) -> None:
    first = partition({0: 1, 1: 2, 2: 3, 3: 4}, count=4)
    _, (archive,), _ = fetch_and_save(FakeToy(first), tmp_path, 0)
    # The ring went around: sectors 0 and 1 now hold 5 and 6, and 4 grew.
    now = partition({0: 5, 1: 6, 2: 3, 3: 4}, count=4)
    now[3 * SECTOR + 300] = 0x22
    toy = FakeToy(now)
    result, written, removed = fetch_and_save(toy, tmp_path, 5)
    assert sorted(result.fetched) == [4, 5, 6] and removed == []
    assert written[0] == archive and archive.read_bytes() == sectors_in(first, 1, 2, 3) + sectors_in(now, 4)
    assert written[1].read_bytes() == sectors_in(now, 5, 6)
    # The next fetch adds to the newer file only and reads nothing already saved.
    later = partition({0: 5, 1: 6, 2: 7, 3: 4}, count=4)
    later[3 * SECTOR + 300] = 0x22
    toy = FakeToy(later)
    result, written, removed = fetch_and_save(toy, tmp_path, 10)
    assert sorted(result.fetched) == [6, 7]
    assert written[0].read_bytes() == sectors_in(later, 5, 6, 7)
    assert [path.name for path in removed] == [f"devlog-{DEVICE.hex()}-20261031-180500.bin"]
    assert saved(tmp_path) == sorted([archive, written[0]])


def test_debugger_fetch_adds_to_the_same_file(tmp_path: pathlib.Path) -> None:
    fetch_and_save(FakeToy(partition({0: 1, 1: 2})), tmp_path, 0)
    image = partition({0: 1, 1: 2, 2: 3})
    sectors = devlog.sector_map(image)
    headers = {sequence: sector[:24] for sequence, sector in sectors.items()}
    written, removed = devlog.save_archive(tmp_path, DEVICE, devlog.load_archive(tmp_path, DEVICE), headers,
                                           sectors, dt.datetime(2026, 10, 31, 19, 0, 0), 16)
    assert written[0].read_bytes() == sectors_in(image, 1, 2, 3) and len(removed) == 1


def test_lost_packets_are_asked_for_again(tmp_path: pathlib.Path) -> None:
    now = partition({index: index + 1 for index in range(6)})
    toy = FakeToy(now, payload=300, lose=(5, 30, 31, 60))
    result = fetch(toy, tmp_path)
    assert b"".join(result.fetched[sequence] for sequence in range(1, 7)) == bytes(now[:6 * SECTOR])
    assert len(log_reads(toy)) > 1 and all(r[1] + r[2] == 6 * SECTOR for r in log_reads(toy))


def test_sectors_opened_during_the_fetch_are_read(tmp_path: pathlib.Path) -> None:
    toy = FakeToy(partition({0: 1, 1: 2}))

    def open_sector(fake: FakeToy) -> None:
        if fake.requests[-1][0] == devlog_ble.REGION_LOG and fake.log[2 * SECTOR] != ord("S"):
            fake.log[:] = partition({0: 1, 1: 2, 2: 3})

    toy.on_request = open_sector
    result = fetch(toy, tmp_path)
    assert sorted(result.fetched) == [1, 2, 3] and result.fetched[3] == sectors_in(toy.log, 3)


def test_core_dump_and_unreadable_regions(tmp_path: pathlib.Path) -> None:
    toy = FakeToy(partition({0: 1}), core=bytes(range(256)) * 3)
    _, written, _ = fetch_and_save(toy, tmp_path, 0)
    core = tmp_path / f"{written[0].stem}-coredump-partition.bin"
    assert core.read_bytes() == bytes(range(256)) * 3
    assert saved(tmp_path) == written  # the core dump is not taken for a log

    class Failing(FakeToy):
        def region(self, region: int) -> bytes:
            return b"" if region == devlog_ble.REGION_LOG else super().region(region)

    with pytest.raises(devlog_ble.ReadError, match="could not read"):
        fetch(Failing(partition({0: 1})), tmp_path / "other")


def test_saved_file_reads_like_a_partition(tmp_path: pathlib.Path) -> None:
    import io

    _, written, _ = fetch_and_save(FakeToy(partition({3: 7, 4: 8, 5: 9})), tmp_path, 0)
    catalog = devlog.load_catalog()
    log = devlog.read_log(written[0].read_bytes(), catalog)
    assert [sector.sequence for sector in log.sectors] == [7, 8, 9]
    out = io.StringIO()
    devlog.dump(log, catalog, out=out)
    assert "3 sectors, sequence 7-9" in out.getvalue()
    assert "Sectors before sequence 7 were overwritten" in out.getvalue()


def test_runs_keep_the_requested_order() -> None:
    assert devlog_ble.runs([5, 6, 7, 0, 1, 3]) == [(5, 3), (0, 2), (3, 1)]
    assert devlog_ble.runs([]) == []
