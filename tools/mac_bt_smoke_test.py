#!/usr/bin/env python3
import argparse
import datetime as dt
import glob
import json
import os
import pathlib
import shutil
import subprocess
import sys
import threading
import time


import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "tools" / "bt_smoke_logs"
MIN_FREE_HEAP_BYTES = 12_000
TOOL_DIRS = [
    pathlib.Path("/opt/homebrew/bin"),
    pathlib.Path("/usr/local/bin"),
    pathlib.Path("/usr/bin"),
    pathlib.Path("/bin"),
]


def find_platformio():
    for base in (ROOT, *ROOT.parents):
        candidate = base / ".venv" / "bin" / "pio"
        if candidate.exists():
            return candidate
    found = shutil.which("pio")
    return pathlib.Path(found) if found else None


PIO = find_platformio()


def run(cmd, check=True):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run([str(c) for c in cmd], check=check, text=True,
                          capture_output=False, cwd=ROOT)


def capture(cmd, check=False):
    try:
        return subprocess.run([str(c) for c in cmd], check=check, text=True,
                              capture_output=True, cwd=ROOT)
    except FileNotFoundError:
        return None


def first_existing_tool(names):
    for name in names:
        path = shutil.which(name)
        if path:
            return path
        for tool_dir in TOOL_DIRS:
            candidate = tool_dir / name
            if candidate.exists() and os.access(candidate, os.X_OK):
                return str(candidate)
    return None


def find_serial_port(explicit):
    if explicit:
        return explicit

    patterns = [
        "/dev/cu.usbserial*",
        "/dev/cu.SLAB_USBtoUART*",
        "/dev/cu.wchusbserial*",
        "/dev/cu.usbmodem*",
    ]
    candidates = []
    for pattern in patterns:
        candidates.extend(glob.glob(pattern))
    candidates = sorted(set(candidates))
    if not candidates:
        return None
    return candidates[0]


def start_serial_capture(port, baud, log_path, stop_event):
    try:
        import serial
    except ImportError:
        print("pyserial is missing; serial capture disabled.", flush=True)
        return None

    def worker():
        try:
            with serial.Serial(port, baud, timeout=0.2) as ser, open(log_path, "a", encoding="utf-8") as out:
                out.write(f"# serial {port} @ {baud}\n")
                out.flush()
                while not stop_event.is_set():
                    raw = ser.readline()
                    if not raw:
                        continue
                    line = raw.decode("utf-8", errors="replace").rstrip()
                    stamped = f"{dt.datetime.now().isoformat(timespec='milliseconds')} {line}"
                    print(stamped, flush=True)
                    out.write(stamped + "\n")
                    out.flush()
        except Exception as exc:
            print(f"Serial capture stopped: {exc}", flush=True)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread


def find_blueutil_address(device_name):
    blueutil = first_existing_tool(["blueutil"])
    if not blueutil:
        return None

    result = capture([blueutil, "--paired", "--format", "json"])
    if not result or result.returncode != 0:
        return None

    try:
        devices = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    wanted = device_name.lower()
    for dev in devices:
        name = str(dev.get("name", "")).lower()
        if name == wanted:
            return dev.get("address")
    for dev in devices:
        name = str(dev.get("name", "")).lower()
        if wanted in name:
            return dev.get("address")
    return None


def connect_with_blueutil(address):
    blueutil = first_existing_tool(["blueutil"])
    if not blueutil:
        print("blueutil not installed; cannot automate Bluetooth connect.", flush=True)
        print("Install with: brew install blueutil", flush=True)
        return False
    if not address:
        print("No Bluetooth address provided/found. Pair once manually or pass --bt-address.", flush=True)
        return False

    capture([blueutil, "--disconnect", address])
    result = capture([blueutil, "--connect", address])
    if result and result.returncode == 0:
        print(f"Requested Bluetooth connect to {address}", flush=True)
        return True
    print("blueutil connect failed.", flush=True)
    if result:
        print(result.stderr.strip(), flush=True)
    return False


def route_audio(device_name):
    switcher = first_existing_tool(["SwitchAudioSource", "switchaudiosource"])
    if not switcher:
        print("SwitchAudioSource not installed; cannot automate output routing.", flush=True)
        print("Install with: brew install switchaudio-osx", flush=True)
        return False

    output_name = find_audio_output(device_name)
    if not output_name:
        print(f"Could not find an output device matching {device_name!r}. Refusing to play test tone on Mac speakers.", flush=True)
        return False

    result = capture([switcher, "-t", "output", "-s", output_name])
    if result and result.returncode == 0:
        current = current_audio_output()
        if current and output_name.lower() in current.lower():
            print(f"Audio output routed to {current}", flush=True)
            return True
        print(f"SwitchAudioSource returned success, but current output is {current!r}.", flush=True)
        return False
    print(f"Could not route audio to {output_name}. Refusing to play test tone on Mac speakers.", flush=True)
    return False


def audio_outputs():
    switcher = first_existing_tool(["SwitchAudioSource", "switchaudiosource"])
    if not switcher:
        return []
    result = capture([switcher, "-t", "output", "-a"])
    if not result:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def list_audio_outputs(device_name):
    outputs = audio_outputs()
    print("Available macOS output devices:", flush=True)
    for output in outputs:
        marker = "  *" if device_name.lower() in output.lower() else "   "
        print(f"{marker} {output}", flush=True)


def find_audio_output(device_name):
    outputs = audio_outputs()
    print("Available macOS output devices:", flush=True)
    for output in outputs:
        marker = "  *" if device_name.lower() in output.lower() else "   "
        print(f"{marker} {output}", flush=True)

    wanted = device_name.lower()
    for output in outputs:
        if output.lower() == wanted:
            return output
    for output in outputs:
        if wanted in output.lower():
            print(f"Using matched output device: {output}", flush=True)
            return output
    return None


def current_audio_output():
    switcher = first_existing_tool(["SwitchAudioSource", "switchaudiosource"])
    if not switcher:
        return None
    result = capture([switcher, "-t", "output", "-c"])
    if not result or result.returncode != 0:
        return None
    return result.stdout.strip()


def play_sine(duration, frequency, volume):
    script = ROOT / "tools" / "play_sine.py"
    run([sys.executable, script, "--duration", duration, "--frequency", frequency, "--volume", volume])


def start_ble_background(device_name, hold_seconds):
    cmd = [
        sys.executable,
        str(ROOT / "tools" / "ble_gatt_probe.py"),
        "--name", device_name,
        "--control-smoke-test",
        "--hold-open-seconds", str(int(hold_seconds)),
        "--timeout", "15",
    ]
    print("+", " ".join(cmd), flush=True)
    return subprocess.Popen(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def check_heap_in_log(log_path):
    """Return the minimum free= heap value seen in the serial log, or None."""
    pattern = re.compile(r'free=(\d+)')
    min_seen = None
    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                for m in pattern.finditer(line):
                    val = int(m.group(1))
                    if min_seen is None or val < min_seen:
                        min_seen = val
    except FileNotFoundError:
        pass
    return min_seen


def main():
    parser = argparse.ArgumentParser(
        description="Build/upload BT debug firmware, capture serial logs, and optionally connect/play from macOS.")
    parser.add_argument("--env", default="btdebug", help="PlatformIO environment to build/upload.")
    parser.add_argument("--skip-upload", action="store_true")
    parser.add_argument("--serial-port")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--device-name", default="SweetYaar")
    parser.add_argument("--bt-address", help="Classic Bluetooth MAC address. If omitted, blueutil paired list is searched.")
    parser.add_argument("--duration", type=float, default=20.0)
    parser.add_argument("--sine-duration", type=float, default=8.0)
    parser.add_argument("--frequency", type=float, default=440.0)
    parser.add_argument("--volume", type=float, default=0.25)
    parser.add_argument("--no-connect", action="store_true")
    parser.add_argument("--no-audio", action="store_true")
    parser.add_argument("--concurrent-ble", action="store_true",
                        help="Hold a BLE connection open during the Classic BT A2DP test")
    args = parser.parse_args()

    if PIO is None:
        raise SystemExit("PlatformIO not found. Expected .venv/bin/pio in this repo or a parent checkout.")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"bt-smoke-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.log"

    if not args.skip_upload:
        run([PIO, "run", "-e", args.env, "-t", "upload"])
        time.sleep(2.0)

    port = find_serial_port(args.serial_port)
    stop_event = threading.Event()
    if port:
        start_serial_capture(port, args.baud, log_path, stop_event)
        time.sleep(2.0)
    else:
        print("No serial port found; continuing without firmware log capture.", flush=True)

    ble_proc = None
    if args.concurrent_ble:
        ble_proc = start_ble_background(args.device_name, hold_seconds=args.duration + 15)
        print("Waiting 3s for BLE background connection...", flush=True)
        time.sleep(3.0)
        if ble_proc.poll() is not None:
            ble_out, _ = ble_proc.communicate(timeout=5)
            print("--- BLE background output ---\n" + ble_out + "\n---", flush=True)
            raise SystemExit("BLE background process exited before Classic BT test started.")

    try:
        if not args.no_connect:
            address = args.bt_address or find_blueutil_address(args.device_name)
            connect_with_blueutil(address)
            time.sleep(5.0)
        if not args.no_audio:
            if not route_audio(args.device_name):
                print("Skipping sine playback because SweetYaar is not the selected output.", flush=True)
                args.no_audio = True
            else:
                time.sleep(1.0)
                play_sine(args.sine_duration, args.frequency, args.volume)
        remaining = max(0.0, args.duration - args.sine_duration)
        time.sleep(remaining)
    finally:
        if ble_proc is not None:
            ble_proc.terminate()
            try:
                ble_out, _ = ble_proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                ble_proc.kill()
                ble_out, _ = ble_proc.communicate()
            print("--- BLE background output ---", flush=True)
            print(ble_out, flush=True)
        stop_event.set()
        time.sleep(0.5)

    if args.concurrent_ble and port:
        min_heap = check_heap_in_log(log_path)
        if min_heap is not None:
            print(f"Heap check: min free={min_heap} bytes (threshold={MIN_FREE_HEAP_BYTES})", flush=True)
            if min_heap < MIN_FREE_HEAP_BYTES:
                raise SystemExit(
                    f"Heap critically low during concurrent BLE+A2DP: {min_heap} bytes (< {MIN_FREE_HEAP_BYTES})")
        else:
            print("Heap check: no free= values found in serial log.", flush=True)

    print(f"Log file: {log_path}", flush=True)


if __name__ == "__main__":
    main()
