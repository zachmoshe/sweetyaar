#!/usr/bin/env python3
"""Fetch the toy's diagnostic log over BLE from a Mac, without the debugger.

Run from macOS Terminal (it needs Bluetooth permission). The Mac must already
be an approved remote for the toy.

    .venv/bin/python tools/devlog_ble.py [--out devlogs] [--full]

The toy restarts into update mode (blinking yellow), sends only the sectors
that are not saved yet (and the one still being written), and restarts its
normal firmware. They are added to the device's saved file, as `devlog.py
fetch` does, so `make parse-logs` and the viewer read it as is.
The protocol is in docs/logging-and-debugging.md ("Fetching the log over BLE").
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import datetime as dt
import pathlib
import struct
import sys
import time

import devlog

LOG_DATA = "a1b2c3d4-e5f6-7890-abcd-ef12345678a6"
ENTER_UPDATE_MODE, CANCEL, READ_LOG = 1, 4, 5
ENTER_FOR_LOG_READ = 1
REGION_INFO, REGION_HEADERS, REGION_LOG, REGION_CORE_DUMP = range(4)
PACKET_HEADER = 5
INFO_FORMAT, INFO_SIZE = 1, 20
STALL_S = 2.0       # no expected packet for this long: ask again from there
ATTEMPTS = 8        # requests in a row without progress before giving up
RECHECK_ROUNDS = 2  # header re-reads for sectors opened during the fetch


class ReadError(Exception):
    pass


@dataclasses.dataclass
class Info:
    device: bytes
    header_size: int
    sector_size: int
    log_size: int
    core_size: int


def parse_info(raw: bytes) -> Info:
    if len(raw) < INFO_SIZE or raw[0] != INFO_FORMAT:
        raise ReadError(f"unsupported log info format {raw[:1].hex() or 'empty'}")
    header_size = raw[7]
    sector_size, log_size, core_size = struct.unpack_from("<III", raw, 8)
    return Info(bytes(raw[1:7]), header_size, sector_size, log_size, core_size)


def runs(sectors: list[int]) -> list[tuple[int, int]]:
    """Groups sectors with consecutive indices, in the given order: (first, count)."""
    grouped: list[tuple[int, int]] = []
    for index in sectors:
        if grouped and grouped[-1][0] + grouped[-1][1] == index:
            grouped[-1] = (grouped[-1][0], grouped[-1][1] + 1)
        else:
            grouped.append((index, 1))
    return grouped


class Link:
    """Sends read requests and receives the toy's log packets."""

    def __init__(self, request):
        self.request = request  # async callable taking the request bytes
        self.packets: asyncio.Queue[bytes] = asyncio.Queue()
        self.received = 0

    def on_packet(self, _sender, data: bytearray) -> None:
        self.packets.put_nowait(bytes(data))

    async def read(self, region: int, offset: int, length: int) -> bytes:
        """Reads a byte range, asking again from the first missing byte after a loss."""
        data = bytearray()
        failures = 0
        while len(data) < length:
            await self.request(struct.pack("<BBII", READ_LOG, region, offset + len(data), length - len(data)))
            progressed = False
            while len(data) < length:
                try:
                    packet = await asyncio.wait_for(self.packets.get(), STALL_S)
                except asyncio.TimeoutError:
                    break
                if len(packet) < PACKET_HEADER:
                    continue
                packet_region, packet_offset = struct.unpack_from("<BI", packet)
                expected = offset + len(data)
                if packet_region != region or packet_offset != expected:
                    # Before the first expected packet these are left over
                    # from an earlier request; after it, one was lost.
                    if progressed and packet_region == region and packet_offset > expected:
                        break
                    continue
                body = packet[PACKET_HEADER:]
                if not body:
                    raise ReadError(f"the toy could not read region {region} at offset {packet_offset}")
                data += body[:length - len(data)]
                self.received += len(body)
                progressed = True
            failures = 0 if progressed else failures + 1
            if failures > ATTEMPTS:
                raise ReadError(f"no data for region {region} at offset {offset + len(data)}")
        return bytes(data)


@dataclasses.dataclass
class Result:
    info: Info
    archive: devlog.Archive
    headers: dict[int, bytes]   # every sector the toy holds: sequence -> header
    fetched: dict[int, bytes]   # sequence -> sector read now
    core: bytes | None


async def read_log(link: Link, out_dir: pathlib.Path, full: bool = False, progress=print) -> Result:
    info = parse_info(await link.read(REGION_INFO, 0, INFO_SIZE))
    if (info.header_size, info.sector_size) != (devlog.SECTOR_HEADER_SIZE, devlog.SECTOR_SIZE):
        raise ReadError(f"unsupported sector layout {info.header_size}/{info.sector_size}")
    count = info.log_size // info.sector_size
    if count == 0:
        raise ReadError("the toy has no log partition")
    archive = devlog.Archive(None, {}) if full else devlog.load_archive(out_dir, info.device)

    async def read_headers() -> dict[int, tuple[int, bytes]]:
        """sequence -> (sector index, header) for every sector with a valid header."""
        raw = await link.read(REGION_HEADERS, 0, count * info.header_size)
        found = {}
        for index in range(count):
            header = raw[index * info.header_size:(index + 1) * info.header_size]
            sequence = devlog.header_sequence(header)
            if sequence is not None:
                found[sequence] = (index, header)
        return found

    located = await read_headers()
    headers = {sequence: header for sequence, (_, header) in located.items()}
    wanted = devlog.sectors_to_fetch(archive, headers)
    progress(f"Device {info.device.hex(':').upper()}: {len(wanted)} of {len(headers)} sectors to read"
             + (f", the rest are in {archive.path.name}" if archive.path and len(wanted) < len(headers) else ""))
    fetched: dict[int, bytes] = {}

    async def fetch_sectors(sequences: list[int]) -> None:
        # Oldest first, so the sector being written comes last.
        order = {located[sequence][0]: sequence for sequence in sequences}
        for first, length in runs([located[sequence][0] for sequence in sequences]):
            start = first * info.sector_size
            data = await link.read(REGION_LOG, start, length * info.sector_size)
            for offset in range(length):
                fetched[order[first + offset]] = data[offset * info.sector_size:(offset + 1) * info.sector_size]
            progress(f"  {len(fetched)} sectors read ({link.received // 1024} KiB)")

    await fetch_sectors(wanted)
    # Sectors opened while reading (the toy keeps logging in update mode).
    for _ in range(RECHECK_ROUNDS):
        latest = await read_headers()
        opened = sorted(sequence for sequence in latest if sequence not in headers)
        located.update(latest)
        if not opened:
            break
        headers.update((sequence, latest[sequence][1]) for sequence in opened)
        await fetch_sectors(opened)

    core = await link.read(REGION_CORE_DUMP, 0, info.core_size) if info.core_size else None
    return Result(info, archive, headers, fetched, core)


def save(result: Result, out_dir: pathlib.Path, started: dt.datetime) -> tuple[list[pathlib.Path], list[pathlib.Path]]:
    info = result.info
    written, removed = devlog.save_archive(out_dir, info.device, result.archive, result.headers, result.fetched,
                                           started, info.log_size // info.sector_size)
    if result.core and written:
        core_path = out_dir / f"{written[-1].stem}-coredump-partition.bin"
        core_path.write_bytes(result.core)
        print(f"A core dump not yet copied into the log was waiting: saved {core_path}")
    return written, removed


async def fetch(name: str, out_dir: pathlib.Path, full: bool) -> pathlib.Path:
    from ota_update import STATUS, Device, parse_status

    started = dt.datetime.now()
    clock = time.monotonic()
    dev = Device(name)
    info = await dev.connect()
    if dev.client.services.get_characteristic(LOG_DATA) is None:
        await dev.disconnect()
        raise SystemExit(f"Firmware {info.get('version')} cannot send its log over BLE (or this Mac "
                         "still has the toy's older GATT table cached; try once more). "
                         "Use make fetch-logs with the debugger.")
    entered = False
    if info.get("mode") != "update":
        print("Restarting the toy into update mode (blinking yellow)")
        await dev.control(bytes([ENTER_UPDATE_MODE, ENTER_FOR_LOG_READ]))
        if not await dev.wait_disconnect(5):
            status = parse_status(await dev.client.read_gatt_char(STATUS))
            await dev.disconnect()
            raise SystemExit(f"The toy refused update mode: {status['error']}")
        entered = True
        await dev.disconnect()
        info = await dev.connect()
        if info.get("mode") != "update":
            await dev.disconnect()
            raise SystemExit(f"The toy restarted in {info.get('mode')} mode instead of update mode.")
    try:
        link = Link(dev.control)
        await dev.client.start_notify(LOG_DATA, link.on_packet)
        read_started = time.monotonic()
        result = await read_log(link, out_dir, full)
        seconds = time.monotonic() - read_started
        print(f"Read {link.received // 1024} KiB in {seconds:.0f} s "
              f"({link.received / 1024 / max(seconds, 0.1):.1f} KiB/s)")
    finally:
        if entered and dev.client.is_connected:
            print("Restarting the toy's normal firmware")
            try:
                await dev.control(bytes([CANCEL]))
                await dev.wait_disconnect(5)
            except Exception:  # noqa: BLE001 - it returns by itself after 2 minutes idle
                pass
        await dev.disconnect()
    written, removed = save(result, out_dir, started)
    devlog.report_saved(written, removed)
    print(f"{len(result.fetched)} sectors read ({time.monotonic() - clock:.0f} s in all)")
    if not written:
        raise SystemExit("The toy's log holds no sectors yet; nothing saved.")
    return written[-1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=pathlib.Path, default=devlog.DEFAULT_DIR)
    parser.add_argument("--name", default="SweetYaar", help="advertised name, if the service is not seen")
    parser.add_argument("--full", action="store_true",
                        help="read every sector the toy holds, even those already saved")
    args = parser.parse_args(argv)
    try:
        path = asyncio.run(fetch(args.name, args.out, args.full))
    except ReadError as error:
        print(f"Fetch failed: {error}", file=sys.stderr)
        return 1
    print(f"Print it with: make parse-logs {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
