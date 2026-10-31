#!/usr/bin/env python3
"""Fetch the toy's on-flash diagnostic log over the debugger and print it.

  devlog.py fetch [--port /dev/cu.usbserial-XXXX] save the log partition
  devlog.py parse [devlogs/<file>.bin]            decode it to text

The byte layout is specified in docs/logging-and-debugging.md and
firmware/esp32/src/DevLogFormat.h; event texts come from DevLogEvents.h.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import os
import pathlib
import re
import struct
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
EVENTS_HEADER = ROOT / "firmware/esp32/src/DevLogEvents.h"
DEFAULT_DIR = ROOT / "devlogs"

SECTOR_SIZE = 4096
FORMAT_VERSION = 1
SECTOR_HEADER_SIZE = 24
RECORD_HEADER_SIZE = 7
RECORD_OVERHEAD = RECORD_HEADER_SIZE + 1
MAX_PAYLOAD = 240
ERASED = 0xFF
TRUNCATED_FLAG = 0x80
ARG_UNSIGNED, ARG_SIGNED, ARG_STRING, ARG_FLOAT, ARG_BYTES = 1, 2, 3, 4, 5

PARTITION_TABLE_OFFSET = 0x8000
PARTITION_TABLE_SIZE = 0xC00
LOG_LABELS = ("logs", "spiffs")  # BLE-updated toys keep the old label
SLOWER_BAUDS = (460800, 230400, 115200)  # stepped through when bytes get lost


def crc8(data: bytes, crc: int = 0) -> int:
    """CRC-8, polynomial 0x07, initial value 0 (as DevLogFormat.h)."""
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


# --- Event catalog ----------------------------------------------------------

@dataclasses.dataclass
class Catalog:
    events: dict[int, tuple[str, str]]  # ID -> (name, format)
    enums: dict[str, list[str] | dict[int, str]]  # {EVENT} names an event ID

    def name(self, event_id: int) -> str:
        return self.events.get(event_id, (f"0x{event_id:04X}", ""))[0]

    def id(self, name: str) -> int:
        return next(event_id for event_id, (event_name, _) in self.events.items() if event_name == name)


def load_catalog(path: pathlib.Path = EVENTS_HEADER) -> Catalog:
    text = path.read_text()
    ids = {name: int(value, 16) for name, value in re.findall(r"#define DEVLOG_ID_(\w+) (0x[0-9A-Fa-f]+)", text)}
    formats = {name: c_string(literal)
               for name, literal in re.findall(r'#define DEVLOG_FMT_(\w+) ("(?:[^"\\]|\\.)*")', text)}
    enums: dict = {name: c_string(literal).split(",")
                   for name, literal in re.findall(r'#define DEVLOG_ENUM_(\w+) ("(?:[^"\\]|\\.)*")', text)}
    enums["EVENT"] = {event_id: name for name, event_id in ids.items()}
    return Catalog({event_id: (name, formats.get(name, "")) for name, event_id in ids.items()}, enums)


def c_string(literal: str) -> str:
    return re.sub(r'\\(["\\])', r"\1", literal[1:-1])


# --- Reading the ring -------------------------------------------------------

@dataclasses.dataclass
class Sector:
    index: int
    sequence: int
    boot: int
    device: bytes


@dataclasses.dataclass
class Record:
    sector: Sector
    offset: int
    event_id: int
    ms: int
    args: list
    truncated: bool
    boot: int = 0


@dataclasses.dataclass
class Log:
    sector_count: int
    sectors: list[Sector]
    records: list[Record]
    problems: list[str]


def decode_args(payload: bytes) -> tuple[list, bool]:
    if not payload:
        return [], False
    count = payload[0] & ~TRUNCATED_FLAG
    truncated = bool(payload[0] & TRUNCATED_FLAG)
    pos = 1 + (count + 1) // 2
    args: list = []
    for index in range(count):
        if pos > len(payload):
            break
        kind = (payload[1 + index // 2] >> (4 * (index % 2))) & 0x0F
        if kind == 0:  # not written: packing stopped here
            break
        if kind in (ARG_UNSIGNED, ARG_SIGNED):
            value = shift = 0
            while True:
                if pos >= len(payload):
                    raise ValueError("varint runs past the payload")
                byte = payload[pos]
                pos += 1
                value |= (byte & 0x7F) << shift
                shift += 7
                if not byte & 0x80:
                    break
            if kind == ARG_SIGNED:
                value = (value >> 1) ^ -(value & 1)
            args.append(value)
        elif kind in (ARG_STRING, ARG_BYTES):
            length = payload[pos]
            raw = payload[pos + 1:pos + 1 + length]
            if len(raw) != length:
                raise ValueError("string runs past the payload")
            pos += 1 + length
            args.append(raw.decode("utf-8", "replace") if kind == ARG_STRING else bytes(raw))
        elif kind == ARG_FLOAT:
            if pos + 4 > len(payload):
                raise ValueError("float runs past the payload")
            args.append(struct.unpack_from("<f", payload, pos)[0])
            pos += 4
        else:
            raise ValueError(f"unknown argument type {kind}")
    return args, truncated


def read_log(data: bytes, catalog: Catalog) -> Log:
    problems: list[str] = []
    sectors: list[Sector] = []
    for index in range(len(data) // SECTOR_SIZE):
        header = data[index * SECTOR_SIZE:index * SECTOR_SIZE + SECTOR_HEADER_SIZE]
        if header[:4] != b"SYLG":
            continue
        if crc8(header[:23]) != header[23]:
            problems.append(f"sector {index}: header CRC mismatch; skipped")
            continue
        if header[4] != FORMAT_VERSION or header[5] != SECTOR_HEADER_SIZE:
            problems.append(f"sector {index}: format version {header[4]} is not supported; skipped")
            continue
        sequence, boot = struct.unpack_from("<II", header, 8)
        sectors.append(Sector(index, sequence, boot, bytes(header[16:22])))
    sectors.sort(key=lambda sector: sector.sequence)

    boot_event = catalog.id("BOOT")
    records: list[Record] = []
    boot = None
    previous = None
    for sector in sectors:
        if previous is not None and sector.sequence != previous.sequence + 1:
            problems.append(f"sequence gap before sector {sector.index}: "
                            f"{previous.sequence} -> {sector.sequence}")
            boot = None
        previous = sector
        if boot is None:
            boot = sector.boot
        base = sector.index * SECTOR_SIZE
        offset = SECTOR_HEADER_SIZE
        while offset + RECORD_OVERHEAD <= SECTOR_SIZE:
            length = data[base + offset]
            if length == ERASED:
                if any(byte != ERASED for byte in data[base + offset:base + SECTOR_SIZE]):
                    problems.append(f"sector {sector.index}: unreadable bytes at {offset} (torn write)")
                break
            total = RECORD_OVERHEAD + length
            raw = data[base + offset:base + offset + total]
            if length > MAX_PAYLOAD or offset + total > SECTOR_SIZE or crc8(raw[:-1]) != raw[-1]:
                problems.append(f"sector {sector.index}: bad record at {offset} (torn write); rest of sector skipped")
                break
            event_id, ms = struct.unpack_from("<HI", raw, 1)
            try:
                args, truncated = decode_args(raw[RECORD_HEADER_SIZE:-1])
            except ValueError as error:
                problems.append(f"sector {sector.index}: record at {offset}: {error}")
                args, truncated = [], True
            if event_id == boot_event and args and isinstance(args[0], int):
                boot = args[0]
            records.append(Record(sector, offset, event_id, ms, args, truncated, boot))
            offset += total
    return Log(len(data) // SECTOR_SIZE, sectors, records, problems)


# --- Text -------------------------------------------------------------------

SPEC = re.compile(r"%(?P<flags>[-+ #0]*)(?P<width>\d*)(?:\.(?P<precision>\d+))?(?:hh|h|ll|l|z|j|t)?"
                  r"(?P<conv>[diouxXcsfFeEgG%])|\{(?P<name>\w+)\}")


def render(fmt: str, args: list, enums: dict) -> str:
    """printf-style formatting of a stored record, tolerant of missing or extra arguments."""
    out: list[str] = []
    position = 0
    used = 0
    for match in SPEC.finditer(fmt):
        out.append(fmt[position:match.start()])
        position = match.end()
        if match["conv"] == "%":
            out.append("%")
            continue
        if used >= len(args):
            out.append("?")
            continue
        value = args[used]
        used += 1
        out.append(render_value(match, value, enums))
    out.append(fmt[position:])
    if used < len(args):
        out.append(" +" + " ".join(describe(value) for value in args[used:]))
    return "".join(out)


def render_value(match: re.Match, value, enums: dict) -> str:
    name = match["name"]
    if name:
        if isinstance(value, bytes):
            return f"<{len(value)} bytes>"
        names = enums.get(name)
        if isinstance(names, dict) and isinstance(value, int):
            return names.get(value, f"0x{value:04X}")
        if names is not None and isinstance(value, int):
            return names[value] if 0 <= value < len(names) else f"{name}({value})"
        return describe(value)
    spec = "%" + match["flags"] + match["width"] + (f".{match['precision']}" if match["precision"] else "")
    conv = match["conv"]
    if conv in "diouxXc" and isinstance(value, float):
        value = int(value)
    if conv in "diu" and isinstance(value, int):
        return (spec + "d") % value
    if conv in "oxX" and isinstance(value, int):
        return (spec + conv) % (value & 0xFFFFFFFF if value < 0 else value)
    if conv == "c" and isinstance(value, int):
        return chr(value & 0xFF)
    if conv in "fFeEgG" and isinstance(value, (int, float)):
        return (spec + conv) % value
    if conv == "s" and isinstance(value, str):
        return (spec + "s") % printable(value)
    return describe(value)


def printable(text: str) -> str:
    return "".join(ch if ch.isprintable() else f"\\x{ord(ch):02x}" for ch in text)


def describe(value) -> str:
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    if isinstance(value, str):
        return f'"{printable(value)}"'
    return str(value)


def record_text(record: Record, catalog: Catalog) -> str:
    if record.event_id in catalog.events:
        text = render(catalog.events[record.event_id][1], record.args, catalog.enums)
    else:
        text = f"[Unknown event 0x{record.event_id:04X}] " + " ".join(describe(value) for value in record.args)
    return text + (" [truncated]" if record.truncated else "")


def uptime(ms: int) -> str:
    seconds, millis = divmod(ms, 1000)
    hours, seconds = divmod(seconds, 3600)
    return f"+{hours}:{seconds // 60:02d}:{seconds % 60:02d}.{millis:03d}"


def wall_times(boot_records: list[Record], catalog: Catalog, tz_minutes: int | None) -> tuple[list, int | None]:
    """Local wall time per record of one boot, from the boot's time anchors."""
    sync, retained, boot_event = (catalog.id(name) for name in ("TIME_SYNC", "CLOCK_RETAINED", "BOOT"))
    for record in boot_records:
        if record.event_id == retained and record.args:
            tz_minutes = record.args[0]
    anchors = []  # (ms, local seconds)
    for record in boot_records:
        if record.event_id == sync and len(record.args) >= 2:
            tz_minutes = record.args[1]
            anchors.append((record.ms, record.args[0] + record.args[1] * 60))
        elif record.event_id == boot_event and len(record.args) >= 9 and record.args[8]:
            anchors.append((record.ms, record.args[8] + (tz_minutes or 0) * 60))
    times = []
    for record in boot_records:
        earlier = [anchor for anchor in anchors if anchor[0] <= record.ms]
        anchor = earlier[-1] if earlier else (anchors[0] if anchors else None)
        if anchor is None:
            times.append(None)
            continue
        local = anchor[1] + (record.ms - anchor[0]) / 1000
        times.append(dt.datetime.fromtimestamp(local, dt.timezone.utc).replace(tzinfo=None))
    return times, tz_minutes


@dataclasses.dataclass
class CoreDump:
    boot: int
    size: int
    data: bytearray
    received: int = 0


def dump(log: Log, catalog: Catalog, out=sys.stdout, boots: int | None = None, chunks: bool = False,
         show_ids: bool = False, core_dir: pathlib.Path | None = None, core_stem: str = "devlog") -> list[pathlib.Path]:
    """Prints the log; returns the core dump files it wrote."""
    write = lambda line="": print(line, file=out)  # noqa: E731
    devices = sorted({sector.device for sector in log.sectors})
    used = len(log.sectors)
    if used:
        write(f"Device {', '.join(device.hex(':').upper() for device in devices)}: "
              f"{used} sectors, sequence {log.sectors[0].sequence}-"
              f"{log.sectors[-1].sequence}, {len(log.records)} records")
        if log.sectors[0].sequence > 1:
            write(f"Sectors before sequence {log.sectors[0].sequence} were overwritten on the toy "
                  "before they were fetched.")
    else:
        write(f"No log sectors in {log.sector_count} sectors (empty or not a SweetYaar log).")
    for problem in log.problems:
        write(f"! {problem}")

    segments: list[list[Record]] = []
    for record in log.records:
        if segments and segments[-1][-1].boot == record.boot:
            segments[-1].append(record)
        else:
            segments.append([record])
    if boots is not None:
        segments = segments[-boots:] if boots > 0 else []

    names = {name: catalog.id(name) for name in ("BOOT", "COREDUMP_BEGIN", "COREDUMP_CHUNK", "COREDUMP_END")}
    written: list[pathlib.Path] = []
    tz_minutes = None
    core = None
    for segment in segments:
        write()
        first = segment[0]
        if first.event_id != names["BOOT"]:
            write(f"--- Boot {first.boot} (its start was overwritten) ---")
        else:
            write(f"--- Boot {first.boot} ---")
        times, tz_minutes = wall_times(segment, catalog, tz_minutes)
        hidden = 0
        for record, wall in zip(segment, times):
            event = record.event_id
            if event == names["COREDUMP_BEGIN"] and record.args:
                core = CoreDump(record.boot, record.args[0], bytearray(record.args[0]))
            elif event == names["COREDUMP_CHUNK"] and core is not None and len(record.args) >= 2:
                offset, chunk = record.args[0], record.args[1]
                if isinstance(chunk, bytes) and offset + len(chunk) <= core.size:
                    core.data[offset:offset + len(chunk)] = chunk
                    core.received += len(chunk)
                if not chunks:
                    hidden += 1
                    continue
            text = record_text(record, catalog)
            if show_ids:
                text = f"{catalog.name(event)}: {text}"
            stamp = wall.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] if wall else "-".ljust(23)
            if hidden and event != names["COREDUMP_CHUNK"]:
                write(f"{'':23}  {'':13}  ({hidden} core dump chunks)")
                hidden = 0
            write(f"{stamp}  {uptime(record.ms):>13}  {text}")
            if event == names["COREDUMP_END"] and core is not None:
                if core.received == core.size and core_dir is not None:
                    core_dir.mkdir(parents=True, exist_ok=True)
                    path = core_dir / f"{core_stem}-boot{core.boot}-core.bin"
                    path.write_bytes(bytes(core.data))
                    written.append(path)
                    write(f"{'':23}  {'':13}  Core dump saved: {path}")
                elif core.received != core.size:
                    write(f"{'':23}  {'':13}  Core dump incomplete: {core.received} of {core.size} bytes")
                core = None
    if written:
        write()
        write("Decode a core dump with the ELF of the firmware that crashed (fw= in its BOOT line):")
        write("  esp-coredump --chip esp32 info_corefile --core-format raw --core <core.bin> <firmware.elf>")
    return written


# --- Fetching over the debugger ---------------------------------------------

def parse_partition_table(table: bytes) -> dict[str, tuple[int, int, int, int]]:
    """label -> (type, subtype, offset, size)."""
    partitions = {}
    for start in range(0, len(table) - 31, 32):
        entry = table[start:start + 32]
        if entry[:2] != b"\xAA\x50":
            break
        kind, subtype, offset, size = struct.unpack_from("<BBII", entry, 2)
        label = entry[12:28].split(b"\0", 1)[0].decode("ascii", "replace")
        partitions[label] = (kind, subtype, offset, size)
    return partitions


class Reader:
    """Reads flash in pieces and reconnects when the toy drops out.

    While awake the firmware enables the BQ25186 charger's 40-second host
    watchdog, which power-cycles the toy when I2C traffic stops. In download
    mode nothing talks to the charger, so about 40 seconds into a read the
    toy loses power and reboots. The reader then reconnects, which puts the
    toy back into download mode, and continues where it stopped.

    A failure well before the watchdog can fire means the debugger loses
    bytes at this speed (its CH340C does at 460800), so the reader continues
    at the next slower speed instead.
    """

    CHUNK = 0x10000
    RETRIES = 6
    WATCHDOG_S = 30  # earlier failures are the link's speed, not the watchdog

    def __init__(self, port: str | None, baud: int):
        self.port, self.baud, self.esp, self.connected_at = port, baud, None, 0.0

    def connect(self) -> None:
        from esptool import connect_esp
        from esptool.cmds import attach_flash, run_stub
        from esptool.logger import log

        log.set_verbosity("silent")  # errors still raise; progress is printed here
        print(f"Connecting to {self.port or 'the first ESP found'} at {self.baud} baud", flush=True)
        esp = connect_esp(self.port)  # without a port, the first ESP found, as the esptool CLI
        self.port = esp._port.port
        esp = run_stub(esp)
        if self.baud:
            esp.change_baud(self.baud)
        attach_flash(esp)
        self.esp = esp
        self.connected_at = time.monotonic()

    def close(self, reset: bool) -> None:
        if self.esp is None:
            return
        try:
            if reset:
                from esptool.cmds import reset_chip
                reset_chip(self.esp, "hard-reset")  # the toy boots normally again
        except Exception:  # noqa: BLE001 - closing after a failure
            pass
        try:
            self.esp._port.close()
        except Exception:  # noqa: BLE001
            pass
        self.esp = None

    def read(self, offset: int, size: int, label: str = "") -> bytes:
        from esptool.cmds import read_flash
        from esptool.util import FatalError
        from serial import SerialException

        data = bytearray()
        failures = 0
        while len(data) < size:
            length = min(self.CHUNK, size - len(data))
            try:
                if self.esp is None:
                    self.connect()
                data += read_flash(self.esp, offset + len(data), length, no_progress=True)
                failures = 0
            except (FatalError, SerialException, OSError) as error:
                failures += 1
                early = self.esp is not None and time.monotonic() - self.connected_at < self.WATCHDOG_S
                self.close(reset=False)
                if failures > self.RETRIES:
                    raise FatalError(f"{label} read stopped at {len(data) // 1024} KiB: {error}") from error
                slower = [baud for baud in SLOWER_BAUDS if baud < self.baud]
                if early and slower:
                    print(f"\nLost bytes at {self.baud} baud ({str(error).strip()}); continuing at {slower[0]}.",
                          flush=True)
                    self.baud = slower[0]
                else:
                    print(f"\nThe toy dropped out at {len(data) // 1024} KiB ({str(error).strip()}); continuing. "
                          "Expected about every 40 s: the charger watchdog power-cycles it in download mode.",
                          flush=True)
                time.sleep(1.5)  # let the power-cycle finish before resetting into download mode
                continue
            if label:
                print(f"\r{label}: {100 * len(data) // size}% ({len(data) // 1024} of {size // 1024} KiB)",
                      end="", flush=True)
        if label:
            print(flush=True)
        return bytes(data)


# --- Saved logs ---------------------------------------------------------------
#
# One file per device history: the sectors that hold records, in sequence
# order, without the erased rest of the partition. Every fetch adds the new
# sectors and the one still being written, and the file is renamed to the
# time of that fetch. read_log() reads it like a partition image.

def header_sequence(header: bytes) -> int | None:
    """The sector's sequence number, or None when it holds no valid header."""
    if (len(header) < SECTOR_HEADER_SIZE or header[:4] != b"SYLG" or crc8(header[:23]) != header[23] or
            header[4] != FORMAT_VERSION or header[5] != SECTOR_HEADER_SIZE):
        return None
    return struct.unpack_from("<I", header, 8)[0]


def sector_map(data: bytes) -> dict[int, bytes]:
    """The sectors with a valid header, by sequence number."""
    sectors = {}
    for start in range(0, len(data) - SECTOR_SIZE + 1, SECTOR_SIZE):
        sequence = header_sequence(data[start:start + SECTOR_HEADER_SIZE])
        if sequence is not None:
            sectors[sequence] = bytes(data[start:start + SECTOR_SIZE])
    return sectors


def saved_logs(directory: pathlib.Path, device: bytes) -> list[pathlib.Path]:
    return sorted(path for path in directory.glob(f"devlog-{device.hex()}-*.bin")
                  if not path.name.endswith(("-core.bin", "-coredump-partition.bin")))


@dataclasses.dataclass
class Archive:
    """The saved file a fetch adds to: the device's file with the newest sector.
    |known| holds the header of every sector in any of the device's files."""
    path: pathlib.Path | None
    sectors: dict[int, bytes]
    known: dict[int, bytes] = dataclasses.field(default_factory=dict)

    @property
    def newest(self) -> int | None:
        return max(self.sectors, default=None)


def load_archive(directory: pathlib.Path, device: bytes) -> Archive:
    best = Archive(None, {})
    known: dict[int, bytes] = {}
    for path in saved_logs(directory, device):
        sectors = sector_map(path.read_bytes())
        known.update((sequence, sector[:SECTOR_HEADER_SIZE]) for sequence, sector in sectors.items())
        if sectors and (best.newest is None or max(sectors) > best.newest):
            best = Archive(path, sectors)
    best.known = known
    return best


def same_history(archive: Archive, headers: dict[int, bytes]) -> bool:
    """Whether the toy's sectors (sequence -> header) continue the saved file.

    An erased partition starts again at sequence 1, so a toy whose newest
    sector is older than the file's, or whose header for a saved sequence
    differs, holds a new history.
    """
    if archive.newest is None or not headers or max(headers) < archive.newest:
        return False
    return all(archive.sectors[sequence][:SECTOR_HEADER_SIZE] == header
               for sequence, header in headers.items() if sequence in archive.sectors)


def sectors_to_fetch(archive: Archive, headers: dict[int, bytes]) -> list[int]:
    """Sequences to read: all of them for a new history; otherwise the new
    sectors and the one that was still being written at the previous fetch."""
    if not same_history(archive, headers):
        return sorted(headers)
    return sorted(sequence for sequence, header in headers.items()
                  if archive.known.get(sequence) != header or sequence >= archive.newest)


def used_length(sector: bytes) -> int:
    return len(sector.rstrip(bytes([ERASED])))


def contains(sectors: dict[int, bytes], older: dict[int, bytes]) -> bool:
    """Whether |sectors| holds everything in |older| (a sector may have grown since)."""
    return all(sequence in sectors and sectors[sequence][:used_length(sector)] == sector[:used_length(sector)]
               for sequence, sector in older.items())


def write_atomic(path: pathlib.Path, data: bytes) -> None:
    temporary = path.with_name(path.name + ".part")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def save_archive(directory: pathlib.Path, device: bytes, archive: Archive, headers: dict[int, bytes],
                 fetched: dict[int, bytes], when: dt.datetime,
                 capacity: int) -> tuple[list[pathlib.Path], list[pathlib.Path]]:
    """Adds the fetched sectors to the device's file; returns (written, removed).

    The file is renamed to this fetch's time. A file holds at most |capacity|
    sectors (one partition): when the toy's ring has gone around since the file
    began, the oldest |capacity| sectors stay in the earlier file under its
    name and the rest start a new one. A new history starts a new file and
    keeps the old one. Afterwards every other file of this device whose
    sectors are all in the written files is removed.
    """
    continues = same_history(archive, headers)
    merged = dict(archive.sectors) if continues else {}
    # Sectors older than this file belong to the device's earlier file.
    first = min(archive.sectors) if continues else 0
    merged.update((sequence, sector) for sequence, sector in fetched.items() if sequence >= first)
    if not merged:
        return [], []
    ordered = [merged[sequence] for sequence in sorted(merged)]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"devlog-{device.hex()}-{when:%Y%m%d-%H%M%S}.bin"
    written = []
    if continues and len(ordered) > capacity:
        write_atomic(archive.path, b"".join(ordered[:capacity]))
        written.append(archive.path)
        ordered = ordered[capacity:]
    write_atomic(path, b"".join(ordered))
    written.append(path)
    kept: dict[int, bytes] = {}
    for written_path in written:
        kept.update(sector_map(written_path.read_bytes()))
    removed = []
    for other in saved_logs(directory, device):
        if other not in written and contains(kept, sector_map(other.read_bytes())):
            other.unlink()
            removed.append(other)
    return written, removed


def report_saved(written: list[pathlib.Path], removed: list[pathlib.Path]) -> None:
    for path in written:
        print(f"Saved {path} ({path.stat().st_size // SECTOR_SIZE} sectors)")
    if removed:
        print(f"Removed {len(removed)} older file(s) of this device; their sectors are in the saved file: "
              + ", ".join(path.name for path in removed))


def fetch(port: str | None, out_dir: pathlib.Path, baud: int) -> pathlib.Path:
    started = dt.datetime.now()
    reader = Reader(port, baud)
    try:
        reader.connect()
        mac = bytes(reader.esp.read_mac())
        partitions = parse_partition_table(reader.read(PARTITION_TABLE_OFFSET, PARTITION_TABLE_SIZE))
        label = next((name for name in LOG_LABELS if name in partitions), None)
        if label is None:
            raise SystemExit(f"No log partition ({' or '.join(LOG_LABELS)}) in the partition table: "
                             f"{', '.join(partitions) or 'none'}")
        _, _, offset, size = partitions[label]
        print(f"Device {mac.hex(':').upper()}: reading partition {label} ({size // 1024} KiB at 0x{offset:X})")
        log = reader.read(offset, size, f"Partition {label}")
        core = None
        if "coredump" in partitions:
            _, _, core_offset, core_size = partitions["coredump"]
            core = reader.read(core_offset, core_size, "Partition coredump")
    finally:
        reader.close(reset=True)

    sectors = sector_map(log)
    headers = {sequence: sector[:SECTOR_HEADER_SIZE] for sequence, sector in sectors.items()}
    written, removed = save_archive(out_dir, mac, load_archive(out_dir, mac), headers, sectors, started,
                                    len(log) // SECTOR_SIZE)
    print(f"Read in {(dt.datetime.now() - started).total_seconds():.0f} s")
    report_saved(written, removed)
    if not written:
        raise SystemExit("The log partition holds no sectors yet; nothing saved.")
    path = written[-1]
    stem = path.stem
    if core and any(byte != ERASED for byte in core[:SECTOR_SIZE]):
        core_path = out_dir / f"{stem}-coredump-partition.bin"
        core_path.write_bytes(core)
        print(f"A core dump not yet copied into the log is in its partition: saved {core_path}")
    return path


def newest_log(directory: pathlib.Path) -> pathlib.Path:
    logs = sorted(path for path in directory.glob("devlog-*.bin")
                  if not path.name.endswith(("-core.bin", "-coredump-partition.bin")))
    if not logs:
        raise SystemExit(f"No fetched logs in {directory}; run make fetch-logs first.")
    return max(logs, key=lambda path: path.stat().st_mtime)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    fetch_parser = commands.add_parser("fetch", help="read the log partition over the debugger")
    fetch_parser.add_argument("--port", help="default: the first ESP esptool finds")
    fetch_parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_DIR)
    # Reads drop bytes through the CH340C debugger at 460800 (make flash's
    # speed); 115200 is the dependable default.
    fetch_parser.add_argument("--baud", type=int, default=230400)
    dump_parser = commands.add_parser("parse", help="print a fetched log as text")
    dump_parser.add_argument("log", type=pathlib.Path, nargs="?", help="default: newest fetched log in --dir")
    dump_parser.add_argument("--dir", type=pathlib.Path, default=DEFAULT_DIR)
    dump_parser.add_argument("--boots", type=int, help="only the last N boots")
    dump_parser.add_argument("--ids", action="store_true", help="prefix each line with its event name")
    dump_parser.add_argument("--chunks", action="store_true", help="print every core dump chunk record")
    dump_parser.add_argument("--events", type=pathlib.Path, default=EVENTS_HEADER)
    args = parser.parse_args(argv)

    if args.command == "fetch":
        from esptool.util import FatalError

        try:
            path = fetch(args.port, args.out, args.baud)
        except FatalError as error:
            print(f"Fetch failed: {error}", file=sys.stderr)
            print("Check the debugger cable, its contacts and its power.", file=sys.stderr)
            return 1
        print(f"Print it with: make parse-logs {path}")
        return 0
    path = args.log or newest_log(args.dir)
    data = path.read_bytes()
    if len(data) % SECTOR_SIZE:
        print(f"! {path} is not a whole number of 4 KiB sectors; reading {len(data) // SECTOR_SIZE}", file=sys.stderr)
    catalog = load_catalog(args.events)
    print(f"Log {path}")
    stem = path.stem
    try:
        dump(read_log(data, catalog), catalog, boots=args.boots, chunks=args.chunks, show_ids=args.ids,
             core_dir=path.parent, core_stem=stem)
    except BrokenPipeError:
        sys.stderr.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
