"""Synthetic flash-log images in format version 1, for viewer tests and demos.

  python tests/devlog_fixture.py <folder>   writes overlapping demo fetches

The encoder mirrors DevLogFormat.h and DevLogRing: records fill 4 KiB
sectors, sectors take increasing sequence numbers, and a ring of N sectors
keeps only the newest N - 1 (one stays erased).
"""

from __future__ import annotations

import datetime as dt
import pathlib
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import devlog  # noqa: E402

CATALOG = devlog.load_catalog()
IDS = {name: event_id for event_id, (name, _) in CATALOG.events.items()}


def varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def pack(args: tuple) -> bytes:
    types, values = [], bytearray()
    for value in args:
        if isinstance(value, bool) or (isinstance(value, int) and value >= 0):
            types.append(devlog.ARG_UNSIGNED)
            values += varint(int(value))
        elif isinstance(value, int):
            types.append(devlog.ARG_SIGNED)
            values += varint(((value << 1) ^ (value >> 63)) & ((1 << 64) - 1))
        elif isinstance(value, float):
            types.append(devlog.ARG_FLOAT)
            values += struct.pack("<f", value)
        elif isinstance(value, str):
            raw = value.encode()[:63]
            types.append(devlog.ARG_STRING)
            values += bytes([len(raw)]) + raw
        else:
            types.append(devlog.ARG_BYTES)
            values += bytes([len(value)]) + bytes(value)
    nibbles = bytearray((len(types) + 1) // 2)
    for index, kind in enumerate(types):
        nibbles[index // 2] |= kind << (4 * (index % 2))
    return bytes([len(types)]) + bytes(nibbles) + bytes(values)


def record(name: str, ms: int, *args) -> bytes:
    payload = pack(args)
    body = bytes([len(payload)]) + struct.pack("<HI", IDS[name], ms) + payload
    return body + bytes([devlog.crc8(body)])


def image(entries: list[tuple[int, bytes]], device: bytes, sectors: int) -> bytes:
    """entries: (boot, encoded record). Returns a ring of `sectors` sectors."""
    filled: list[tuple[int, bytearray]] = []
    for boot, encoded in entries:
        if not filled or len(filled[-1][1]) + len(encoded) > devlog.SECTOR_SIZE:
            filled.append((boot, bytearray()))
            filled[-1][1].extend(b"\xFF" * devlog.SECTOR_HEADER_SIZE)
        filled[-1][1].extend(encoded)
    flash = bytearray(b"\xFF" * (sectors * devlog.SECTOR_SIZE))
    kept = filled[-(sectors - 1):]
    first_sequence = len(filled) - len(kept) + 1
    for offset, (boot, data) in enumerate(kept):
        sequence = first_sequence + offset
        header = b"SYLG" + bytes([devlog.FORMAT_VERSION, devlog.SECTOR_HEADER_SIZE]) + b"\xFF\xFF"
        header += struct.pack("<II", sequence, boot) + device + b"\xFF"
        data[:devlog.SECTOR_HEADER_SIZE] = header + bytes([devlog.crc8(header)])
        start = ((sequence - 1) % sectors) * devlog.SECTOR_SIZE
        flash[start:start + len(data)] = data
    return bytes(flash)


class Story:
    """Builds the records of consecutive boots of one toy."""

    def __init__(self) -> None:
        self.entries: list[tuple[int, bytes]] = []
        self.boot = 0
        self.ms = 0
        self.name = "Yaaruli"
        self.firmware = "1.1.0"
        self.slot = "app0"

    def add(self, name: str, *args, at: int | None = None) -> None:
        if at is not None:
            self.ms = at
        self.entries.append((self.boot, record(name, self.ms, *args)))

    def start(self, reset: str, code: int, wake: int, epoch: int = 0, streak: int = 0,
              tz: int | None = None, crash: bool = False) -> None:
        """BOOT and the boot lines that follow it; tz means the RTC clock was kept."""
        self.boot += 1
        self.add("BOOT", self.boot, streak, reset, code, wake, self.firmware, "sweetyaar", self.slot, epoch, at=110)
        if crash:
            self.add("CRASH", "loopTask", 28, 0x400D2A10, 0, 6, 0, 0x400D2A10, 0x400D31C4, 0x400E0012,
                     0, 0, 0, 0, 0, at=112)
            self.add("COREDUMP_BEGIN", 600, at=113)
            for offset in range(0, 600, 224):
                chunk = bytes((offset + i) % 251 for i in range(min(224, 600 - offset)))
                self.add("COREDUMP_CHUNK", offset, chunk, at=114 + offset // 224)
            self.add("COREDUMP_END", 600, 3, at=118)
        self.add("SLEEP_WAKE", wake, 1 if wake == 2 else 0, at=120)
        if wake != 2:  # detail record: not stored after a deep-sleep wake
            self.add("DEVICE_NAME", self.name, at=125)
        self.add("CLOCK_RETAINED", tz, at=130) if tz is not None else self.add("CLOCK_UNKNOWN", at=130)
        self.add("BOOT_READY", 1950, at=1950)


def demo_story() -> Story:
    """Three days of a toy: an app session, songs, Bluetooth audio, a crash and charging."""
    story = Story()
    tz = 120
    local = lambda day, hour, minute=0: int(dt.datetime(2026, 11, day, hour, minute, tzinfo=dt.timezone.utc)  # noqa: E731
                                              .timestamp()) - tz * 60
    battery = 4120.0

    def telemetry(ms: int, playing: bool, charging: bool = False, ble: bool = False, bt: bool = False) -> None:
        activity = (1 if playing else 0) | (2 if bt else 0) | (4 if bt and playing else 0) | (8 if ble else 0) | 0x80
        story.add("TELEMETRY", int(battery), 1, 4 if charging else 1, 0, activity, 60, 61000 - (9000 if bt else 0),
                  48000 - (12000 if bt else 0), 30000 - (8000 if bt else 0), at=ms)

    # Day 1, 08:00: cold boot, the parent app sets the clock, songs by button.
    story.start("power-on", 1, 0)
    telemetry(2000, False)
    story.add("BLE_CONNECT", 1, 0x7C, 0x1A, 0x22, 0x01, 0x02, 0x03, 1, "closed", "bonded", at=180_000)
    story.add("BLE_CONTROL", 1, 1, 0, 52000, 40000, at=181_000)
    story.add("TIME_SYNC", local(3, 8, 3), tz, at=181_500)
    story.add("BLE_CONFIG_COMMAND", "getConfig", 1, at=182_000)
    story.add("BLE_DISCONNECT", 1, 0x13, 1, at=360_000)
    ms = 400_000
    for song in range(8):
        story.add("SM_EVENT", 0, 1, at=ms)
        story.add("SM_TRANSITION", 0, 1, at=ms)
        story.add("WAV_PLAYING", f"/songs/children-songs/song{song:02d}.wav", at=ms + 15)
        for minute in range(0, 4):
            if (ms + minute * 60_000) % 300_000 < 60_000:
                battery -= 5.5
                telemetry(ms + minute * 60_000 + 1, True)
        ms += 230_000
        story.add("SM_EVENT", 1, 6, at=ms)
        story.add("SM_TRANSITION", 1, 0, at=ms)
        ms += 20_000
    for _ in range(3):
        ms += 300_000
        battery -= 1.5
        telemetry(ms, False)
    story.add("USAGE", ms // 1000, 8, 0, 0, 8, 0, 8 * 230, 0, 2, at=ms + 10)
    story.add("SLEEP_ENTER", 600, 39, at=ms + 600_000)

    # Day 1, 11:30: woken by movement, an hour of Bluetooth audio from a phone.
    story.start("deep-sleep", 8, 2, epoch=local(3, 11, 30), tz=tz)
    telemetry(2000, False)
    story.add("BT_CONNECTED", 42000, 30000, at=60_000)
    story.add("SM_TRANSITION", 0, 3, at=65_000)
    story.add("BT_AUDIO_STATE", "STARTED", at=65_010)
    for step in range(12):
        battery -= 6.5
        telemetry(70_000 + step * 300_000, True, bt=True)
    story.add("BT_AUDIO_STATE", "SUSPENDED", at=3_700_000)
    story.add("SM_TRANSITION", 3, 0, at=3_700_000)
    story.add("BT_DISCONNECTED", at=3_720_000)
    story.add("BT_POST_SESSION_HEAP", 50000, 44000, 21000, at=3_721_000)
    story.add("USAGE", 3723, 0, 0, 0, 0, 0, 0, 3635, 0, at=3_723_000)
    # The parent app installs 1.2.0 before the toy sleeps.
    story.add("OTA_BEGIN", 1, 1_050_000, 1_960_000, 0, 0, 52000, at=3_800_000)
    story.add("OTA_FINISH", 0, 2, at=4_100_000)
    story.add("SLEEP_ENTER", 600, 39, at=4_330_000)
    story.firmware, story.slot = "1.2.0", "app1"

    # Day 1, 17:00: animals, then a crash during playback.
    story.start("deep-sleep", 8, 2, epoch=local(3, 17, 0), tz=tz)
    story.add("OTA_CONFIRMED", "1.2.0", at=1_900)
    telemetry(2000, False)
    ms = 30_000
    for animal in range(5):
        story.add("SM_EVENT", 0, 2, at=ms)
        story.add("SM_TRANSITION", 0, 2, at=ms)
        story.add("WAV_PLAYING", f"/animals/animal{animal}.wav", at=ms + 12)
        ms += 6_000
        story.add("SM_TRANSITION", 2, 0, at=ms)
        ms += 40_000
    story.add("SM_TRANSITION", 0, 1, at=ms)
    story.add("WAV_PLAYING", "/songs/children-songs/song03.wav", at=ms + 15)
    story.add("WAV_READ_FAILED", at=ms + 61_000)

    # Panic reset: crash summary and core dump copy, clock lost.
    story.start("panic", 4, 0, streak=1, crash=True)
    telemetry(2000, False)
    # The charger stops answering: stored once, then counted until sleep.
    story.add("CHARGER_I2C_READ_FAILED", 0x00, at=5_000)
    story.add("BOOT_STABLE", 4, 60, at=60_000)
    story.add("REPEATED", IDS["CHARGER_I2C_READ_FAILED"], 5_000, 594, 599_000, at=599_100)
    story.add("SLEEP_ENTER", 600, 39, at=600_000)

    # Day 2, 19:00: charging overnight, the app connects and syncs the clock.
    story.start("power-on", 1, 0)
    story.add("CHARGER_STATUS", "UNKNOWN", "CHARGING", at=2_100)
    for step in range(24):
        battery = min(4180.0, battery + 22)
        telemetry(2_000 + step * 300_000, False, charging=True, ble=step == 2)
    story.add("BLE_CONNECT", 2, 0x7C, 0x1A, 0x22, 0x01, 0x02, 0x03, 1, "closed", "bonded", at=600_000)
    story.add("TIME_SYNC", local(4, 19, 10), tz, at=601_000)
    story.add("BLE_NAME_SET", "Renamed Yaar", at=650_000)
    story.add("BT_NAME_SET", "Renamed Yaar", at=650_010)
    story.add("BLE_DISCONNECT", 2, 0x13, 1, at=700_000)
    story.add("CHARGER_STATUS", "19:58", "FINISHED", at=7_100_000)
    story.add("USAGE", 7200, 0, 0, 0, 0, 0, 0, 0, 3, at=7_200_000)
    return story


DEMO_DEVICE = bytes.fromhex("aabbcc001122")


def write_demo(folder: pathlib.Path, sectors: int = 384) -> list[pathlib.Path]:
    """Two overlapping fetches of one toy, plus a second toy."""
    story = demo_story()
    folder.mkdir(parents=True, exist_ok=True)
    boot3_end = max(index for index, (boot, _) in enumerate(story.entries) if boot == 3) + 1
    paths = []
    for stamp, entries in (("20261103-180000", story.entries[:boot3_end]), ("20261104-210000", story.entries)):
        path = folder / f"devlog-{DEMO_DEVICE.hex()}-{stamp}.bin"
        path.write_bytes(image(entries, DEMO_DEVICE, sectors))
        paths.append(path)
    other = Story()
    other.start("power-on", 1, 0)
    other.add("TELEMETRY", 3950, 1, 3, 0, 0x80, 75, 60000, 50000, 31000, at=2000)
    path = folder / "devlog-aabbcc009988-20261104-120000.bin"
    path.write_bytes(image(other.entries, bytes.fromhex("aabbcc009988"), sectors))
    paths.append(path)
    return paths


if __name__ == "__main__":
    for written in write_demo(pathlib.Path(sys.argv[1])):
        print(written)
