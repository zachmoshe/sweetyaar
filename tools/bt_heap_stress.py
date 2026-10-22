#!/usr/bin/env python3
"""
BT heap stress test for SweetYaar.

Automates connect/play/disconnect cycles and reports heap measurements
captured from the serial port at each stage.

Usage:
    .venv/bin/python tools/bt_heap_stress.py [--cycles N] [--port /dev/cu.xxx]

Prerequisites:
    brew install blueutil
    SweetYaar must be paired and set as macOS audio output before running.
    The serial monitor must not be running (port is opened exclusively).
"""

import argparse
import math
import os
import re
import struct
import subprocess
import sys
import tempfile
import threading
import time
import wave

try:
    import serial
except ImportError:
    print("pyserial not found. Install with: .venv/bin/pip install pyserial")
    sys.exit(1)

# ── config ────────────────────────────────────────────────────────────────────
BT_ADDR       = "F8:B3:B7:E1:59:32"   # SweetYaar Classic BT address
BAUD          = 115200
CONNECT_WAIT  = 5.0    # seconds after blueutil --connect before assuming A2DP up
AUDIO_SECS    = 15.0   # how long to stream audio per "play" cycle
DISCONNECT_SETTLE = 0.5
COOLDOWN_WAIT = 3.5    # 1.5 s device cooldown + buffer for the check log line
CYCLE_GAP     = 2.0    # pause between cycles

# Patterns to extract from serial output
PATTERNS = {
    "connected":    re.compile(r"\[BT\] Connected \(free=(\d+) largest=(\d+)"),
    "pausing":      re.compile(r"\[BT\] Pausing new connections.*free=(\d+) largest=(\d+)"),
    "post_session": re.compile(r"\[BT\] Post-session heap: free=(\d+) largest=(\d+)"),
    "accepting":    re.compile(r"\[BT\] Accepting approved connections.*free=(\d+) largest=(\d+)"),
    "restart":      re.compile(r"\[BT\] Heap too low after BT session; restarting \((\d+)/(\d+)\)"),
}


# ── serial reader ─────────────────────────────────────────────────────────────
class SerialReader:
    def __init__(self, port, baud):
        self._ser = serial.Serial(port, baud, timeout=0.1)
        self._lines: list[tuple[float, str]] = []
        self._lock = threading.Lock()
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop:
            try:
                raw = self._ser.readline()
                if raw:
                    line = raw.decode(errors="replace").rstrip()
                    ts = time.monotonic()
                    with self._lock:
                        self._lines.append((ts, line))
                    print(f"    {line}")
            except Exception:
                if not self._stop:
                    time.sleep(0.05)

    def lines_since(self, t0: float) -> list[tuple[float, str]]:
        with self._lock:
            return [(t, l) for t, l in self._lines if t >= t0]

    def stop(self):
        self._stop = True
        try:
            self._ser.close()
        except Exception:
            pass


# ── audio ─────────────────────────────────────────────────────────────────────
def make_tone_wav(path: str, duration_s: float = 30.0, hz: float = 440.0):
    """Write a mono 44.1 kHz 16-bit sine-wave WAV."""
    rate = 44100
    n = int(duration_s * rate)
    with wave.open(path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        chunk = 4096
        for start in range(0, n, chunk):
            end = min(start + chunk, n)
            frames = b"".join(
                struct.pack("<h", int(16000 * math.sin(2 * math.pi * hz * i / rate)))
                for i in range(start, end)
            )
            f.writeframes(frames)


# ── BT control ───────────────────────────────────────────────────────────────
def bt_connect():
    try:
        subprocess.run(["blueutil", "--connect", BT_ADDR],
                       capture_output=True, timeout=30)
    except subprocess.TimeoutExpired:
        print("  (blueutil connect timed out — device may still connect)")

def bt_disconnect():
    try:
        subprocess.run(["blueutil", "--disconnect", BT_ADDR],
                       capture_output=True, timeout=30)
    except subprocess.TimeoutExpired:
        print("  (blueutil disconnect timed out)")


# ── parse heap from serial lines ──────────────────────────────────────────────
MIN_PATTERN = re.compile(r"min=(\d+)")


def parse_heap(lines: list[tuple[float, str]]) -> dict[str, tuple[int, int]]:
    results: dict[str, tuple[int, int]] = {}
    for _, line in lines:
        m = MIN_PATTERN.search(line)
        if m:
            low = int(m.group(1))
            results["min"] = (min(low, results.get("min", (low,))[0]), 0)
        for key, pat in PATTERNS.items():
            if key not in results:
                m = pat.search(line)
                if m:
                    results[key] = (int(m.group(1)), int(m.group(2)))
    return results


# ── single cycle ─────────────────────────────────────────────────────────────
def run_cycle(reader: SerialReader, wav_path: str, play: bool, num: int) -> dict:
    label = "WITH audio" if play else "idle (no audio)"
    print(f"\n{'─'*60}")
    print(f"  Cycle {num}: {label}")
    print(f"{'─'*60}")

    t0 = time.monotonic()

    print("  → connecting...")
    bt_connect()
    time.sleep(CONNECT_WAIT)

    audio_proc = None
    if play:
        print("  → playing audio...")
        audio_proc = subprocess.Popen(["afplay", wav_path], stderr=subprocess.DEVNULL)
        time.sleep(AUDIO_SECS)

    print("  → disconnecting...")
    if audio_proc:
        audio_proc.terminate()
        audio_proc.wait()
        time.sleep(DISCONNECT_SETTLE)
    bt_disconnect()

    print("  → waiting for post-session check...")
    time.sleep(COOLDOWN_WAIT)

    heap = parse_heap(reader.lines_since(t0))

    def fmt(key):
        if key not in heap:
            return "—"
        f, l = heap[key]
        return f"free={f:,}  largest={l:,}"

    print(f"\n  connected:    {fmt('connected')}")
    print(f"  pausing:      {fmt('pausing')}")
    print(f"  post_session: {fmt('post_session')}")
    if "min" in heap:
        print(f"  low point since boot: {heap['min'][0]:,}")
    if "restart" in heap:
        print("  *** RESTART triggered by the post-session heap check")

    return heap


# ── summary table ─────────────────────────────────────────────────────────────
def print_summary(results: list[tuple[bool, dict]]):
    print(f"\n{'='*90}")
    print("SUMMARY")
    print(f"{'='*90}")

    def cell(h, k, width=26):
        if k not in h:
            return "—".rjust(width)
        f, l = h[k]
        return f"f={f:,} l={l:,}".rjust(width)

    header = f"{'#':>3}  {'type':<12}  {'connected':>26}  {'post_session':>26}  {'restart'}"
    print(header)
    print("-" * len(header))
    for i, (play, h) in enumerate(results):
        restart = "YES ⚠" if "restart" in h else ""
        row = (f"{i+1:>3}  "
               f"{'audio' if play else 'idle':<12}  "
               f"{cell(h,'connected')}  "
               f"{cell(h,'post_session')}  "
               f"{restart}")
        print(row)

    # Aggregate stats
    connected_free   = [h["connected"][0]    for _, h in results if "connected"    in h]
    connected_lrg    = [h["connected"][1]    for _, h in results if "connected"    in h]
    post_free        = [h["post_session"][0] for _, h in results if "post_session" in h]
    post_lrg         = [h["post_session"][1] for _, h in results if "post_session" in h]

    print()
    def stat(label, vals):
        if not vals:
            return
        print(f"  {label:<30}  min={min(vals):>7,}  max={max(vals):>7,}  avg={sum(vals)//len(vals):>7,}")

    print("Aggregates:")
    stat("connected free",        connected_free)
    stat("connected largest",     connected_lrg)
    stat("post_session free",     post_free)
    stat("post_session largest",  post_lrg)

    lows = [h["min"][0] for _, h in results if "min" in h]
    if lows:
        print(f"  {'low point since boot':<30}  {min(lows):>7,}")

    restarts = sum(1 for _, h in results if "restart" in h)
    print(f"\n  Restarts triggered: {restarts}/{len(results)}")


# ── main ──────────────────────────────────────────────────────────────────────
def find_port():
    import glob
    ports = sorted(glob.glob("/dev/cu.usbserial-*"))
    return ports[0] if ports else None

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", type=int, default=8,
                    help="Total cycles (alternates idle/audio, default 8)")
    ap.add_argument("--port",   default=None,
                    help="Serial port (auto-detected if omitted)")
    ap.add_argument("--audio-secs", type=float, default=AUDIO_SECS,
                    help=f"Seconds of audio per play cycle (default {AUDIO_SECS})")
    args = ap.parse_args()

    port = args.port or find_port()
    if not port:
        print("No serial port found. Use --port /dev/cu.xxx")
        sys.exit(1)

    print(f"Port:        {port}")
    print(f"BT address:  {BT_ADDR}")
    print(f"Cycles:      {args.cycles}  (alternating idle / audio)")
    print(f"Audio secs:  {args.audio_secs}")
    print("\nMake sure SweetYaar is set as the macOS audio output.\n")

    wav = tempfile.mktemp(suffix=".wav")
    print(f"Generating tone WAV ({args.audio_secs + 5:.0f}s)...")
    make_tone_wav(wav, duration_s=args.audio_secs + 5)

    reader = SerialReader(port, BAUD)
    time.sleep(0.5)

    results: list[tuple[bool, dict]] = []
    try:
        for i in range(args.cycles):
            play = (i % 2 == 1)   # 0=idle, 1=audio, 2=idle, 3=audio …
            heap = run_cycle(reader, wav, play, i + 1)
            results.append((play, heap))
            time.sleep(CYCLE_GAP)
    except KeyboardInterrupt:
        print("\n\nInterrupted.")
    finally:
        reader.stop()
        try:
            os.unlink(wav)
        except OSError:
            pass

    if results:
        print_summary(results)


if __name__ == "__main__":
    main()
