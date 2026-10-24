#!/usr/bin/env python3
"""
Update a SweetYaar over BLE from a Mac, using the same protocol as the parent app.

Run from macOS Terminal (it needs Bluetooth permission). The Mac must already
be an approved remote for the toy.

    .venv/bin/python tools/ota_update.py --image firmware/esp32/.pio/build/sweetyaar/firmware.bin
    .venv/bin/python tools/ota_update.py --manifest app/public/firmware/manifest.json

Options --cancel-at and --pause-at exercise cancellation and resume.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import pathlib
import struct
import sys
import time
import zlib

from bleak import BleakClient, BleakScanner

SERVICE = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
FIRMWARE = "a1b2c3d4-e5f6-7890-abcd-ef12345678a2"
CONTROL = "a1b2c3d4-e5f6-7890-abcd-ef12345678a3"
DATA = "a1b2c3d4-e5f6-7890-abcd-ef12345678a4"
STATUS = "a1b2c3d4-e5f6-7890-abcd-ef12345678a5"
STATES = ["idle", "ready", "receiving", "verifying", "installing", "failed"]
ERRORS = ["none", "battery low", "not ready", "bad request", "no memory", "flash", "decompress",
          "invalid image", "checksum", "size", "wrong mode"]
WINDOW = 16 * 1024  # bytes in flight beyond the last acknowledged offset


def parse_status(raw: bytes) -> dict:
    fmt, state, error, _, received, total, tag, mtu = struct.unpack("<BBBBII4sH", bytes(raw[:18]))
    return {"state": STATES[state] if state < len(STATES) else state,
            "error": ERRORS[error] if error < len(ERRORS) else error,
            "received": received, "total": total, "tag": tag, "mtu": mtu}


def load_image(args) -> tuple[bytes, bytes, int, int]:
    """Returns (encoded stream, image SHA-256, encoding, image size)."""
    if args.manifest:
        manifest_path = pathlib.Path(args.manifest)
        manifest = json.loads(manifest_path.read_text())
        entry = manifest["images"][args.board]
        encoded = (manifest_path.parent / entry["file"]).read_bytes()
        assert hashlib.sha256(encoded).hexdigest() == entry["fileSha256"], "file checksum"
        image = zlib.decompress(encoded)
        print(f"manifest {manifest['version']}: {manifest['notes']}")
    else:
        image = pathlib.Path(args.image).read_bytes()
        encoded = image if args.raw else zlib.compress(image, 9)
    return encoded, hashlib.sha256(image).digest(), (0 if args.raw else 1), len(image)


class Device:
    def __init__(self, name: str):
        self.name = name
        self.client: BleakClient | None = None
        self.status: dict = {}
        self.status_event = asyncio.Event()

    async def connect(self, attempts: int = 40) -> dict:
        for attempt in range(attempts):
            device = await BleakScanner.find_device_by_filter(
                lambda d, adv: SERVICE in [u.lower() for u in adv.service_uuids] or d.name == self.name,
                timeout=5)
            if device:
                try:
                    self.client = BleakClient(device, timeout=20)
                    await self.client.connect()
                    info = json.loads(bytes(await self.client.read_gatt_char(FIRMWARE)).decode())
                    await self.client.start_notify(STATUS, self.on_status)
                    self.status = parse_status(await self.client.read_gatt_char(STATUS))
                    return info
                except Exception as error:  # reconnect races the toy's restart
                    print(f"  connect attempt {attempt + 1} failed: {error}")
                    # Stay connected briefly: a Service Changed indication makes
                    # macOS rediscover, so the next connection sees the new table.
                    await asyncio.sleep(3)
                    await self.disconnect()
            await asyncio.sleep(1)
        raise SystemExit("could not connect to SweetYaar")

    def on_status(self, _sender, data: bytearray):
        self.status = parse_status(data)
        self.status_event.set()

    async def control(self, payload: bytes):
        await self.client.write_gatt_char(CONTROL, payload, response=True)

    async def wait_disconnect(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.client.is_connected:
                return True
            await asyncio.sleep(0.2)
        return False

    async def disconnect(self):
        if self.client:
            try:
                await self.client.disconnect()
            except Exception:
                pass


async def send_image(dev: Device, encoded: bytes, chunk: int, pause_at: float | None,
                     cancel_at: float | None) -> str:
    peripheral = dev.client._backend._peripheral
    offset = dev.status["received"]
    started = time.monotonic()
    last_progress = (offset, started)
    next_report = started + 5
    while True:
        acked = dev.status["received"]
        if dev.status["state"] == "failed":
            return f"failed: {dev.status['error']}"
        if acked >= len(encoded):
            break
        fraction = acked / len(encoded)
        if cancel_at is not None and fraction >= cancel_at:
            await dev.control(bytes([4]))
            return "cancelled"
        if pause_at is not None and fraction >= pause_at:
            print(f"  pausing at {fraction:.0%}: disconnecting for 15 s")
            await dev.disconnect()
            await asyncio.sleep(15)
            return "paused"
        if acked != last_progress[0]:
            last_progress = (acked, time.monotonic())
        elif time.monotonic() - last_progress[1] > 2:
            offset = acked  # lost chunk: resend from the device's offset
            last_progress = (acked, time.monotonic())
        if offset < len(encoded) and offset - acked < WINDOW:
            while not peripheral.canSendWriteWithoutResponse():
                if not dev.client.is_connected:
                    raise ConnectionError("link dropped")
                await asyncio.sleep(0.0005)
            payload = encoded[offset:offset + chunk]
            await dev.client.write_gatt_char(DATA, struct.pack("<I", offset) + payload, response=False)
            offset += len(payload)
        else:
            dev.status_event.clear()
            try:
                await asyncio.wait_for(dev.status_event.wait(), 0.5)
            except asyncio.TimeoutError:
                dev.status = parse_status(await dev.client.read_gatt_char(STATUS))
        if time.monotonic() >= next_report:
            next_report += 5
            elapsed = time.monotonic() - started
            print(f"  {acked}/{len(encoded)} B ({acked / len(encoded):.0%}) {acked / 1024 / max(elapsed, 0.1):.1f} KiB/s")
    print(f"  sent in {time.monotonic() - started:.1f} s")
    return "sent"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--image", help="firmware.bin to install")
    source.add_argument("--manifest", help="release manifest.json (uses its compressed image)")
    parser.add_argument("--board", default="sweetyaar")
    parser.add_argument("--raw", action="store_true", help="send uncompressed (--image only)")
    parser.add_argument("--name", default="SweetYaar")
    parser.add_argument("--pause-at", type=float, help="disconnect once at this fraction, then resume")
    parser.add_argument("--cancel-at", type=float, help="cancel at this fraction")
    parser.add_argument("--enter-only", action="store_true",
                        help="enter update mode, confirm it, then disconnect (tests the idle timeout)")
    args = parser.parse_args()

    encoded, sha, encoding, image_size = load_image(args)
    print(f"image {image_size} B, sending {len(encoded)} B ({'raw' if encoding == 0 else 'zlib'})")
    dev = Device(args.name)
    total_started = time.monotonic()
    info = await dev.connect()
    print(f"connected: {info}, status {dev.status}")
    if info.get("board") != args.board:
        raise SystemExit(f"device board {info.get('board')} != {args.board}")
    if info.get("mode") != "update":
        await dev.control(bytes([1]))
        if not await dev.wait_disconnect(5):
            dev.status = parse_status(await dev.client.read_gatt_char(STATUS))
            raise SystemExit(f"device refused update mode: {dev.status['error']}")
        print(f"  restarting into update mode ({time.monotonic() - total_started:.1f} s)")
        await dev.disconnect()
        info = await dev.connect()
        print(f"reconnected: {info}")
    if args.enter_only:
        await dev.disconnect()
        print("left the toy in update mode; it should restart normal firmware after 2 minutes")
        return 0 if info.get("mode") == "update" else 1
    begin = bytes([2, encoding]) + struct.pack("<II", len(encoded), image_size) + sha
    pause_at = args.pause_at
    while True:
        await dev.control(begin)
        dev.status = parse_status(await dev.client.read_gatt_char(STATUS))
        print(f"  begin: {dev.status}")
        chunk = max(20, min(508, dev.status["mtu"] - 3 - 4))
        try:
            result = await send_image(dev, encoded, chunk, pause_at, args.cancel_at)
        except Exception as error:  # link dropped: reconnect and resume
            print(f"  transfer interrupted: {error}")
            await dev.disconnect()
            result = "paused"
        if result != "paused":
            break
        pause_at = None
        info = await dev.connect()
        print(f"resumed after pause: {info}, status {dev.status}")
        if info.get("mode") != "update":
            # Power loss, cancel or the 2-minute timeout: the old firmware runs.
            print(f"toy restarted normal firmware {info.get('version')}; the update did not finish")
            await dev.disconnect()
            return 1
    if result != "sent":
        print(f"update {result}")
        await dev.wait_disconnect(5)
        await dev.disconnect()
        return 1
    await dev.control(bytes([3]))
    await asyncio.sleep(0.5)
    if dev.client.is_connected:
        try:
            dev.status = parse_status(await dev.client.read_gatt_char(STATUS))
        except Exception:
            pass
    print(f"  finish: {dev.status}")
    if dev.status["state"] == "failed":
        return 1
    await dev.wait_disconnect(10)
    await dev.disconnect()
    info = await dev.connect()
    print(f"after restart: {info} (total {time.monotonic() - total_started:.1f} s)")
    await dev.disconnect()
    return 0 if info.get("mode") == "normal" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
