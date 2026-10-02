#!/usr/bin/env python3
"""Opt-in tests against an actual SweetYaar; run on macOS from Terminal.

Never collected by pytest. --approved acknowledges approval for THIS run.
Physical buttons and a second central cannot be simulated by another process
on the same Mac. Scenarios wait for real firmware events and fail on timeout.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import struct
import sys
import threading
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
SERVICE = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
VOLUME = "a1b2c3d4-e5f6-7890-abcd-ef1234567891"
STATUS = "a1b2c3d4-e5f6-7890-abcd-ef1234567894"
NOTICE = "a1b2c3d4-e5f6-7890-abcd-ef1234567899"
ACCESS = "a1b2c3d4-e5f6-7890-abcd-ef12345678a1"


def log(message):
    print(f"{datetime.now(timezone.utc).isoformat()} {message}", flush=True)


def classic_reconnect_evidence(lines):
    connected = next((i for i, line in enumerate(lines) if
                      "A2DP_CONNECTION" in line and "pairing=closed decision=connected" in line), None)
    # Opening some serial adapters resets the board even with DTR/RTS low.
    # In that case boot replaces the explicit disconnect as the session boundary.
    if connected is None or not any("[BT] Disconnected" in line or "[Boot] Ready." in line
                                    for line in lines[:connected]):
        raise AssertionError("Missing session boundary or closed-window Classic reconnect")
    if any("[Pairing] Open" in line or "JUST_WORKS_REQUEST decision=allow" in line for line in lines):
        raise AssertionError("Reconnect required fresh pairing")
    return lines[connected]


class SerialTrace:
    def __init__(self, port, path):
        import serial
        self.lines = []
        self.times = []
        self.file = path.open("w")
        self.port = serial.Serial(port=None, baudrate=115200, timeout=0.2, exclusive=True)
        self.port.dtr = False
        self.port.rts = False
        self.port.port = port
        self.port.open()
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self.read, daemon=True)
        self.thread.start()

    def read(self):
        while not self.stopped.is_set():
            try:
                data = self.port.readline()
            except Exception as error:
                if not self.stopped.is_set():
                    log(f"SERIAL ERROR {error}")
                return
            if data:
                line = data.decode("utf-8", errors="replace").strip()
                self.times.append(time.monotonic())
                self.lines.append(line)
                self.file.write(f"{datetime.now(timezone.utc).isoformat()} {line}\n")
                self.file.flush()
                log(f"DEVICE {line}")

    def reset(self):
        self.port.rts = True
        time.sleep(0.1)
        self.port.rts = False

    async def wait(self, text, start=0, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for line in self.lines[start:]:
                if text in line:
                    return line
            await asyncio.sleep(0.1)
        raise TimeoutError(f"No firmware event {text!r} within {timeout}s")

    def close(self):
        self.stopped.set()
        self.thread.join(timeout=1)
        self.port.close()
        self.file.close()


class DeviceTest:
    def __init__(self, args, directory):
        self.args = args
        self.directory = directory
        self.trace = None
        self.address = args.ble_address
        self.results = []

    def passed(self, name, evidence):
        self.results.append({"name": name, "status": "passed", "evidence": evidence})
        log(f"PASS {name}: {evidence}")

    async def command(self, *args, timeout=30):
        log("COMMAND " + " ".join(args))
        process = await asyncio.create_subprocess_exec(
            *args, cwd=ROOT, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        try:
            output, _ = await asyncio.wait_for(process.communicate(), timeout)
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            raise TimeoutError(f"Command timed out: {args[0]}")
        text = output.decode(errors="replace").strip()
        if text:
            log(text)
        if process.returncode:
            raise RuntimeError(f"{args[0]} exited {process.returncode}: {text}")
        return text

    async def find_ble(self):
        from bleak import BleakScanner
        if self.address:
            device = await BleakScanner.find_device_by_address(self.address, timeout=15)
        else:
            devices = await BleakScanner.discover(timeout=8, return_adv=True)
            matches = [dev for dev, adv in devices.values()
                       if SERVICE in [uuid.lower() for uuid in adv.service_uuids]]
            if len(matches) != 1:
                raise RuntimeError(f"Expected one SweetYaar advertisement, found {len(matches)}; use --ble-address")
            device = matches[0]
        if device is None:
            raise RuntimeError("SweetYaar BLE advertisement not found")
        self.address = device.address
        log(f"TARGET BLE {device.name} {device.address}")
        return device

    async def access(self, client):
        deadline = time.monotonic() + 35
        previous = None
        pairing_read_started = False
        while time.monotonic() < deadline:
            value = bytes(await asyncio.wait_for(client.read_gatt_char(ACCESS), 10))
            if value != previous:
                log(f"ACCESS {value.hex()}")
                previous = value
            if value != b"\x01":
                return value
            if not pairing_read_started:
                # Match the app: an encrypted read initiates security from the
                # client. Its result alone cannot authorize the controller.
                pairing_read_started = True
                try:
                    await asyncio.wait_for(client.read_gatt_char(STATUS), 25)
                except Exception as error:
                    log(f"PAIRING PROBE {type(error).__name__}: {error}")
                continue
            await asyncio.sleep(0.25)
        raise TimeoutError("BLE authentication did not finish")

    async def check_ble(self, expected):
        from bleak import BleakClient
        device = await self.find_ble()
        async with BleakClient(device, timeout=20) as client:
            value = await self.access(client)
            if value != bytes([expected]):
                raise AssertionError(f"Expected access={expected}, received {value.hex()}")
            if expected == 2:
                status = bytes(await asyncio.wait_for(client.read_gatt_char(STATUS), 10))
                volume = bytes(await asyncio.wait_for(client.read_gatt_char(VOLUME), 10))
                self.passed("BLE approved access", f"access=2, status={status!r}, volume={volume.hex()}")
                if self.args.hold_seconds:
                    log(f"OBSERVE: keeping the approved BLE remote connected for {self.args.hold_seconds}s")
                    await asyncio.sleep(self.args.hold_seconds)
                    if not client.is_connected:
                        raise AssertionError("BLE disconnected during observation")
            else:
                self.passed("BLE unapproved rejection", "public access=0 (pairing required)")
                try:
                    await asyncio.wait_for(client.read_gatt_char(VOLUME), 8)
                except asyncio.TimeoutError:
                    raise AssertionError("Protected read timed out; rejection was not confirmed")
                except Exception as error:
                    log(f"Protected read rejected: {type(error).__name__}: {error}")
                    evidence = f"access=0; protected read failed: {type(error).__name__}: {error}"
                else:
                    raise AssertionError("Unapproved client read protected volume")
                self.passed("BLE protected read blocked", evidence)

    async def reboot(self):
        start = len(self.trace.lines)
        self.trace.reset()
        await self.trace.wait("[Boot] Ready.", start, timeout=25)
        await self.trace.wait("[Access] Bonds ready", start, timeout=15)
        lines = self.trace.lines[start:]
        if any("[Pairing] Open" in line for line in lines):
            raise AssertionError("Pairing unexpectedly opened at boot")
        gate = next((line for line in lines if "SCAN_MODE" in line and "discoverable=0" in line), None)
        if not gate:
            raise AssertionError("Missing closed-pairing boot scan-mode evidence")
        self.passed("Boot with pairing closed", gate)

    async def wait_pairing(self):
        start = len(self.trace.lines)
        log("WAITING: hold both toy buttons for 3 seconds, then release both.")
        opened = await self.trace.wait("[Pairing] Open for 60 seconds", start, timeout=180)
        self.passed("Physical pairing gesture", opened)
        # Ignore connection attempts made while waiting for the gesture.
        # Enrollment assertions must start at the actual open event.
        return self.trace.lines.index(opened, start)

    async def pairing_timeout(self, start):
        closed = await self.trace.wait("[Pairing] Closed;", start, timeout=70)
        opened_index = next(i for i in range(start, len(self.trace.lines))
                            if "[Pairing] Open for 60 seconds" in self.trace.lines[i])
        closed_index = next(i for i in range(opened_index, len(self.trace.lines))
                            if "[Pairing] Closed;" in self.trace.lines[i])
        duration = self.trace.times[closed_index] - self.trace.times[opened_index]
        if not 58 <= duration <= 62:
            raise AssertionError(f"Pairing window lasted {duration:.2f}s, expected 60s")
        self.passed("Pairing window closes after enrollment", f"{duration:.2f}s; {closed}")

    async def audio(self, address):
        switch = shutil.which("SwitchAudioSource")
        if not switch:
            raise RuntimeError("SwitchAudioSource is required for the Classic audio test")
        original = json.loads(await self.command(switch, "-c", "-f", "json"))
        deadline = time.monotonic() + 15
        target = None
        while time.monotonic() < deadline:
            output = await self.command(switch, "-a", "-t", "output", "-f", "json")
            devices = [json.loads(line) for line in output.splitlines() if line.strip()]
            normalized = address.lower().replace(":", "").replace("-", "")
            matches = [dev for dev in devices if normalized in
                       dev.get("uid", "").lower().replace(":", "").replace("-", "")]
            if not matches:
                matches = [dev for dev in devices if "sweetyaar" in dev.get("name", "").lower()]
            if len(matches) == 1:
                target = matches[0]
                break
            await asyncio.sleep(1)
        if target is None:
            raise AssertionError("SweetYaar audio output not available")
        tone = self.directory / "quiet-test-tone.wav"
        with wave.open(str(tone), "wb") as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(44100)
            frames = bytearray()
            for i in range(44100 * 5):
                envelope = min(1, i / 4410, (44100 * 5 - i) / 4410)
                value = int(32767 * 0.03 * envelope * math.sin(2 * math.pi * 440 * i / 44100))
                frames.extend(struct.pack("<hh", value, value))
            wav.writeframes(frames)
        player = self.directory / "device-tone"
        await self.command("/usr/bin/xcrun", "swiftc", str(ROOT / "tools/device_tone.swift"),
                           "-o", str(player), timeout=60)
        start = len(self.trace.lines)
        await self.command(str(player), str(tone), target["uid"], timeout=15)
        evidence = await self.trace.wait("Audio state: STARTED", start, timeout=5)
        current = json.loads(await self.command(switch, "-c", "-f", "json"))
        if current["uid"] != original["uid"]:
            raise AssertionError("Mac default audio output changed during targeted tone playback")
        self.passed("Classic audio transport", f"output={target['name']}; {evidence}; Mac default output unchanged")

    async def classic(self):
        from bleak import BleakClient
        address = self.args.classic_address
        if not address:
            raise ValueError("Use --classic-address from this board's boot log")
        blueutil = shutil.which("blueutil")
        if not blueutil:
            raise RuntimeError("blueutil is required")
        if self.args.already_paired:
            await self.reboot()
            start = len(self.trace.lines)
        else:
            start = await self.wait_pairing()
        try:
            if not self.args.already_paired:
                await self.command(blueutil, "--pair", address, timeout=45)
            await self.command(blueutil, "--connect", address, timeout=30)
            await self.trace.wait("[BT] Connected", start, timeout=15)
            self.passed("Classic approved connection" if self.args.already_paired else "Classic enrollment",
                        "Host connect succeeded and firmware reports Connected")
            async with BleakClient(await self.find_ble(), timeout=20) as client:
                if await self.access(client) != b"\x02":
                    raise AssertionError("BLE access failed while Classic connected")
                status = bytes(await client.read_gatt_char(STATUS))
                if status != b"BT connected":
                    raise AssertionError(f"Expected BT status, received {status!r}")
                volume = bytes(await client.read_gatt_char(VOLUME))
                await client.write_gatt_char(VOLUME, bytes([20 if volume != b"\x14" else 30]), response=True)
                await asyncio.sleep(0.5)
                after = bytes(await client.read_gatt_char(VOLUME))
                if after != volume:
                    raise AssertionError("BLE volume control changed during Classic mode")
                self.passed("Classic and BLE coexistence", "BLE status is BT mode; volume write ignored")
                await self.audio(address)
                if not self.args.already_paired:
                    await self.pairing_timeout(start)
            await self.command(blueutil, "--disconnect", address)
            await asyncio.sleep(3)
            reconnect = len(self.trace.lines)
            await self.command(blueutil, "--connect", address)
            await self.trace.wait("[BT] Connected", reconnect, timeout=15)
            self.passed("Classic approved reconnect outside window", "Connected after pairing closed")
        finally:
            await self.command(blueutil, "--disconnect", address)

    async def takeover(self):
        from bleak import BleakClient
        notice = asyncio.Event()
        disconnected = asyncio.Event()
        def receive(_sender, value):
            log(f"NOTICE {bytes(value)!r}")
            if json.loads(bytes(value)).get("type") == "takeover":
                notice.set()
        async with BleakClient(await self.find_ble(), timeout=20,
                               disconnected_callback=lambda _: disconnected.set()) as client:
            if await self.access(client) != b"\x02":
                raise AssertionError("Mac is not the approved controller")
            await client.start_notify(NOTICE, receive)
            pairing_start = await self.wait_pairing() if self.args.pair_second else None
            log("WAITING: connect the second phone/tablet in the SweetYaar app.")
            await asyncio.wait_for(notice.wait(), 180)
            await asyncio.wait_for(disconnected.wait(), 5)
            self.passed("BLE takeover notice and disconnect", "Received takeover indication, then disconnected")
        await self.check_ble(2)
        self.passed("Previous controller can take back control", "Mac reconnected with approved access")
        if pairing_start is not None:
            await self.pairing_timeout(pairing_start)

    async def external_takeover(self):
        await self.reboot()
        start = len(self.trace.lines)
        previous = 65535
        for attempt in range(2):
            log("WAITING: connect the first approved phone/tablet." if attempt == 0 else
                "WAITING: connect the second approved phone/tablet; leave the first connected. Do not open pairing.")
            outcome = await self.trace.wait("AUTH conn=", start, timeout=180)
            if not all(value in outcome for value in
                       ("[BLE]", "success=1", "bonded_before=1", "new_keys=0", "pairing=closed", "decision=accept")):
                raise AssertionError(f"Expected a saved BLE approval outside pairing: {outcome}")
            auth_index = self.trace.lines.index(outcome, start)
            control = await self.trace.wait("CONTROL authenticated_conn=", auth_index, timeout=5)
            match = re.search(r"authenticated_conn=(\d+) owner=(\d+) previous=(\d+)", control)
            if not match:
                raise AssertionError(f"Invalid controller event: {control}")
            connection, owner, old_owner = map(int, match.groups())
            if connection != owner or old_owner != previous or owner == previous:
                raise AssertionError(f"Expected new controller replacing {previous}: {control}")
            if attempt:
                retired = await self.trace.wait(f"DISCONNECT conn={previous} ", auth_index, timeout=5)
                if "was_controller=0" not in retired:
                    raise AssertionError(f"Previous controller was not retired: {retired}")
                self.passed("External approved BLE takeover outside pairing", f"{control}; {retired}")
            else:
                self.passed("External approved BLE reconnect after reboot", outcome)
            previous = owner
            start = self.trace.lines.index(control, auth_index) + 1
        if any("[Pairing] Open" in line for line in self.trace.lines):
            raise AssertionError("Pairing opened during the closed-window takeover test")

    async def run(self):
        if self.args.flash:
            await self.command("make", "flash", f"PIO_ENV={self.args.pio_env}",
                               f"SERIAL_PORT={self.args.port}", timeout=180)
            self.passed("Firmware flashed", self.args.pio_env)
        self.trace = SerialTrace(self.args.port, self.directory / "serial.log")
        scenario = self.args.scenario
        try:
            if scenario == "boot":
                await self.reboot()
                await self.check_ble(self.args.expected_access)
            elif scenario == "ble-pair":
                start = await self.wait_pairing()
                await self.check_ble(2)
                await self.pairing_timeout(start)
                await self.check_ble(2)
                self.passed("BLE reconnect outside pairing window", "Authenticated after closed event")
                await self.reboot()
                await self.check_ble(2)
                self.passed("BLE approval survives reboot", "Authenticated with boot pairing closed")
            elif scenario == "ble-reconnect":
                for attempt in range(3):
                    await self.check_ble(2)
                    if attempt < 2:
                        await asyncio.sleep(2)
                self.passed("Repeated BLE reconnect", "Three approved sessions without rebooting or opening pairing")
            elif scenario == "external-pair":
                # Isolate phone/tablet enrollment before testing overlap. This
                # runner owns serial only and never opens a Mac BLE connection.
                await self.reboot()
                start = await self.wait_pairing()
                log("WAITING: connect the phone/tablet through the SweetYaar app and accept its pairing request.")
                outcome = await self.trace.wait("AUTH conn=", start, timeout=70)
                if "[BLE]" not in outcome or "success=1" not in outcome or "decision=accept" not in outcome:
                    raise AssertionError(f"External device authentication failed: {outcome}")
                self.passed("External BLE enrollment", outcome)
                await self.pairing_timeout(start)
            elif scenario == "external-classic":
                await self.reboot()
                start = await self.wait_pairing()
                log("WAITING: pair from a phone's Bluetooth audio settings. Verify that no comparison code is requested.")
                request = await self.trace.wait("JUST_WORKS_REQUEST decision=allow", start, timeout=70)
                outcome = await self.trace.wait("AUTH_COMPLETE", start, timeout=70)
                if "code=0x00" not in outcome or "decision=accept" not in outcome:
                    raise AssertionError(f"External Classic authentication failed: {outcome}")
                await self.trace.wait("[BT] Connected", start, timeout=20)
                self.passed("External Classic Just Works enrollment", f"{request}; {outcome}; audio profile connected")
                await self.pairing_timeout(start)
            elif scenario == "external-classic-reconnect":
                start = len(self.trace.lines)
                log("WAITING: disconnect the toy on the just-paired phone, then reconnect without pressing the toy buttons.")
                await self.trace.wait("[BT] Connected", start, timeout=180)
                evidence = classic_reconnect_evidence(self.trace.lines[start:])
                self.passed("External Just Works bond reconnect", evidence)
            elif scenario == "classic":
                await self.classic()
            elif scenario == "classic-denied":
                if not self.args.classic_address:
                    raise ValueError("Use --classic-address from the boot log")
                await self.reboot()
                gate = next((line for line in reversed(self.trace.lines) if "SCAN_MODE" in line), None)
                if not gate or "connectable=0 discoverable=0" not in gate:
                    raise AssertionError("This check needs no Classic bonds and pairing closed")
                blueutil = shutil.which("blueutil")
                if not blueutil:
                    raise RuntimeError("blueutil is required")
                try:
                    await self.command(blueutil, "--connect", self.args.classic_address, timeout=30)
                except (RuntimeError, TimeoutError) as error:
                    state = await self.command(blueutil, "--is-connected", self.args.classic_address)
                    if state != "0":
                        raise AssertionError("Classic connected despite closed admission")
                    self.passed("Classic connection unavailable with pairing closed", f"{gate}; {error}; connected=0")
                else:
                    await self.command(blueutil, "--disconnect", self.args.classic_address)
                    raise AssertionError("Unexpected Classic connection with no approved devices")
            elif scenario == "takeover":
                await self.takeover()
            elif scenario == "external-takeover":
                await self.external_takeover()
            elif scenario == "reset":
                start = len(self.trace.lines)
                log("WAITING: hold BOTH buttons for 13 seconds, then release both; this clears saved pairings.")
                await self.trace.wait("[Pairing] All bonds cleared", start, timeout=180)
                cleared = len(self.trace.lines)
                await asyncio.sleep(4)
                if any("[Pairing] Open" in line for line in self.trace.lines[cleared:]):
                    raise AssertionError("Pairing reopened during the same reset hold")
                self.passed("Physical bond reset", "Bonds cleared; no new pairing window afterward")
                await self.check_revoked()
                await self.reboot()
                if not any("[Access] Bonds ready classic=0 ble=0 pairing=closed" in line
                           for line in self.trace.lines[cleared:]):
                    raise AssertionError("Reset did not persist empty bond stores for both transports")
                self.passed("Reset persistence for both transports", "Boot loaded classic=0, ble=0, pairing=closed")
                await self.check_revoked()
        finally:
            self.trace.close()
            # Prefer the actual device failure over a later host symptom (for
            # example a BLE reconnect returning Idle after a crash/reboot).
            crashes = [line for line in self.trace.lines if
                       any(word in line for word in ("Guru Meditation", "Brownout", "CORRUPT HEAP", "abort() was called", "assert failed:"))]
            if crashes:
                raise AssertionError(f"Device crashed: {crashes}")

    async def check_revoked(self):
        try:
            await self.check_ble(0)
        except Exception as error:
            # macOS may refuse a formerly bonded link before exposing GATT.
            # This proves loss of the old bond, not the public rejection UI.
            if "Peer removed pairing information" not in str(error):
                raise
            self.passed("Revoked Mac bond refused", str(error))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approved", action="store_true", help="explicit user approval was obtained for this run")
    parser.add_argument("--flash", action="store_true", help="build and upload before testing (preserves NVS)")
    parser.add_argument("--pio-env", required=True, choices=["sweetyaar", "sweetyaar-generic"])
    parser.add_argument("--port", required=True)
    parser.add_argument("--scenario", choices=["boot", "ble-pair", "ble-reconnect", "external-pair", "external-classic", "external-classic-reconnect", "external-takeover", "classic", "classic-denied", "takeover", "reset"], default="boot")
    parser.add_argument("--expected-access", type=int, choices=[0, 2], default=0)
    parser.add_argument("--hold-seconds", type=int, choices=range(0, 61), default=0,
                        metavar="0..60", help="keep each approved BLE check connected for LED observation")
    parser.add_argument("--ble-address")
    parser.add_argument("--classic-address")
    parser.add_argument("--already-paired", action="store_true", help="classic: test saved approval after reboot without opening pairing")
    parser.add_argument("--pair-second", action="store_true", help="takeover: wait for a physical pairing window to enroll the second device")
    parser.add_argument("--log-dir", type=Path)
    args = parser.parse_args()
    if not args.approved:
        parser.error("Get explicit user approval before flashing or interacting with the device; then use --approved.")
    directory = args.log_dir or ROOT / "tools/bt_smoke_logs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    directory.mkdir(parents=True, exist_ok=True)
    test = DeviceTest(args, directory)
    binary = ROOT / "firmware/esp32/.pio/build" / args.pio_env / "firmware.bin"
    log(f"SCENARIO {args.scenario}; evidence directory {directory}")
    success = False
    try:
        asyncio.run(test.run())
        success = True
    except Exception as error:
        test.results.append({"name": args.scenario, "status": "failed", "error": f"{type(error).__name__}: {error}"})
        log(f"FAIL {type(error).__name__}: {error}")
    finally:
        report = {"scenario": args.scenario, "success": success, "board": args.pio_env,
                  "port": args.port, "ble_address": test.address,
                  "built_firmware_sha256": hashlib.sha256(binary.read_bytes()).hexdigest() if binary.exists() else None,
                  "results": test.results,
                  "limits": ["Only this scenario was tested, not every flow.",
                             "LED appearance, button feel and audible audio quality require human observation.",
                             "Two independent devices are required for takeover/source contention."]}
        (directory / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
