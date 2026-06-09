#!/usr/bin/env python3
"""
bt_stress_test.py — BLE + Classic BT dual-mode stability stress tester.

Runs N iterations of a chosen connection sequence and reports crash rate,
graceful-restart rate, and heap statistics.  Designed to be run after
flashing new firmware to quickly assess dual-mode stability.

Sequences
---------
  ble-first   Connect BLE first, then Classic BT A2DP, then disconnect BT.
              Tests the concurrent-memory crash (hci_hal_h4.c assert).
  bt-first    Connect Classic BT first, stream briefly, disconnect BT.
              Tests the post-disconnect graceful restart (heap leak path).
  both        Alternates: even iterations = ble-first, odd = bt-first.

Outcomes per iteration
----------------------
  crash-at-bt-connect   Bluedroid asserted inside host_recv_pkt_cb at BT connect.
  crash-other           Any other firmware panic / abort.
  graceful-restart      Our low-heap guard fired esp_restart() cleanly.
  bt-connect-failed     blueutil could not connect Classic BT within timeout.
  ble-connect-failed    ble_gatt_probe could not connect BLE within timeout.
  timeout               Iteration did not complete within the per-iteration limit.
  clean                 No crash, no restart (rare — only possible before leak).

Example
-------
  python tools/bt_stress_test.py --iterations 20 --sequence ble-first
  python tools/bt_stress_test.py --iterations 10 --sequence both \\
      --bt-address 40-22-d8-3d-8a-22 --device-name SweetYaar
"""

from __future__ import annotations

import argparse
import glob
import pathlib
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

ROOT = pathlib.Path(__file__).resolve().parents[1]
BLE_PROBE = ROOT / "tools" / "ble_gatt_probe.py"

# ---------------------------------------------------------------------------
# Patterns matched against serial output
# ---------------------------------------------------------------------------
_RE_CRASH        = re.compile(r"assert failed|abort\(\)|Guru Meditation|LoadProhibited|StoreProhibited|ILLEGAL_INSTRUCTION")
_RE_HCI_CRASH    = re.compile(r"host_recv_pkt_cb")
_RE_REBOOT       = re.compile(r"=== SweetYaar Boot ===")
_RE_BT_CONNECTED = re.compile(r"\[BT\] Connected")
_RE_BT_DISC      = re.compile(r"\[BT\] Disconnected")
_RE_GRACEFUL     = re.compile(r"Restarting cleanly")
_RE_HEAP         = re.compile(r"free=(\d+)")
_RE_AUDIO_STARTED = re.compile(r"\[BT\] Audio state: STARTED")


# ---------------------------------------------------------------------------
# Outcome
# ---------------------------------------------------------------------------
class Outcome(Enum):
    CRASH_AT_BT_CONNECT = "crash-at-bt-connect"
    CRASH_OTHER         = "crash-other"
    GRACEFUL_RESTART    = "graceful-restart"
    BT_CONNECT_FAILED   = "bt-connect-failed"
    BLE_CONNECT_FAILED  = "ble-connect-failed"
    TIMEOUT             = "timeout"
    CLEAN               = "clean"


_OUTCOME_COLOR = {
    Outcome.CRASH_AT_BT_CONNECT: "\033[91m",  # red
    Outcome.CRASH_OTHER:         "\033[91m",
    Outcome.GRACEFUL_RESTART:    "\033[93m",  # yellow
    Outcome.BT_CONNECT_FAILED:   "\033[95m",  # magenta
    Outcome.BLE_CONNECT_FAILED:  "\033[95m",
    Outcome.TIMEOUT:             "\033[95m",
    Outcome.CLEAN:               "\033[92m",  # green
}
_RESET = "\033[0m"


@dataclass
class IterResult:
    n: int
    sequence: str
    outcome: Outcome
    bt_connected: bool = False
    ble_connected: bool = False
    heap_at_bt_connect: Optional[int] = None
    min_heap: Optional[int] = None
    duration_s: float = 0.0
    crash_detail: str = ""
    reboot_seen: bool = False  # reboot detected during/after outcome
    audio_streamed: bool = False  # audio was routed and played during BT hold


# ---------------------------------------------------------------------------
# Serial monitor
# ---------------------------------------------------------------------------
class SerialMonitor:
    """Reads from a serial port in a background thread.

    All lines are stored as (timestamp, text) pairs and can be queried
    by pattern or by timestamp window.
    """

    def __init__(self, port: str, baud: int = 115200) -> None:
        self.port = port
        self.baud = baud
        self._lines: list[tuple[float, str]] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._ser = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        import serial  # type: ignore
        self._ser = serial.Serial(self.port, self.baud, timeout=0.2)
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        if self._ser:
            try:
                self._ser.close()
            except Exception:
                pass

    def reset_esp32(self) -> None:
        """Pulse RTS to reset the ESP32 (works on most dev boards)."""
        self._ser.dtr = False
        self._ser.rts = True
        time.sleep(0.1)
        self._ser.rts = False
        time.sleep(0.1)
        self._ser.dtr = False

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                raw = self._ser.readline()
            except Exception:
                break
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").rstrip()
            with self._lock:
                self._lines.append((time.monotonic(), line))

    def since(self, ts: float) -> list[tuple[float, str]]:
        with self._lock:
            return [(t, l) for t, l in self._lines if t >= ts]

    def wait_for(
        self,
        pattern: re.Pattern,
        timeout: float,
        since_ts: Optional[float] = None,
    ) -> Optional[tuple[float, str]]:
        """Block until a line matching *pattern* appears, or timeout."""
        deadline = time.monotonic() + timeout
        start = since_ts if since_ts is not None else time.monotonic()
        while time.monotonic() < deadline:
            for ts, line in self.since(start):
                if pattern.search(line):
                    return ts, line
            time.sleep(0.05)
        return None

    def wait_for_any(
        self,
        patterns: list[re.Pattern],
        timeout: float,
        since_ts: Optional[float] = None,
    ) -> Optional[tuple[float, str, re.Pattern]]:
        """Block until any pattern matches; returns (ts, line, matched_pattern)."""
        deadline = time.monotonic() + timeout
        start = since_ts if since_ts is not None else time.monotonic()
        while time.monotonic() < deadline:
            for ts, line in self.since(start):
                for pat in patterns:
                    if pat.search(line):
                        return ts, line, pat
            time.sleep(0.05)
        return None

    def min_heap_since(self, ts: float) -> Optional[int]:
        vals = []
        for _, line in self.since(ts):
            for m in _RE_HEAP.finditer(line):
                vals.append(int(m.group(1)))
        return min(vals) if vals else None

    def heap_at_first_match(self, pattern: re.Pattern, ts: float) -> Optional[int]:
        """Return the free= value on the first line matching pattern after ts."""
        for _, line in self.since(ts):
            if pattern.search(line):
                m = _RE_HEAP.search(line)
                if m:
                    return int(m.group(1))
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def find_serial_port(explicit: Optional[str]) -> Optional[str]:
    if explicit:
        return explicit
    for pattern in ["/dev/cu.usbserial*", "/dev/cu.SLAB_USBtoUART*",
                    "/dev/cu.wchusbserial*", "/dev/cu.usbmodem*"]:
        hits = sorted(glob.glob(pattern))
        if hits:
            return hits[0]
    return None


def blueutil() -> Optional[str]:
    return shutil.which("blueutil")


def bt_connect(address: str) -> bool:
    tool = blueutil()
    if not tool:
        return False
    # Disconnect first so macOS doesn't skip if it thinks it's already connected
    try:
        subprocess.run([tool, "--disconnect", address],
                       capture_output=True, timeout=5)
    except subprocess.TimeoutExpired:
        pass
    time.sleep(0.5)
    r = subprocess.run([tool, "--connect", address],
                       capture_output=True, text=True, timeout=10)
    return r.returncode == 0


def bt_disconnect(address: str) -> None:
    tool = blueutil()
    if not tool:
        return
    try:
        subprocess.run([tool, "--disconnect", address],
                       capture_output=True, timeout=8)
    except subprocess.TimeoutExpired:
        pass  # device may have already rebooted — that's fine


def start_ble_background(device_name: str, hold_seconds: float) -> subprocess.Popen:
    cmd = [
        sys.executable, str(BLE_PROBE),
        "--name", device_name,
        "--hold-open-seconds", str(int(hold_seconds)),
        "--timeout", "15",
    ]
    return subprocess.Popen(
        cmd, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )


def ble_wait_connected(proc: subprocess.Popen, timeout: float) -> bool:
    """Read the BLE probe stdout until 'Connected: True' appears or timeout."""
    deadline = time.monotonic() + timeout
    buf = ""
    while time.monotonic() < deadline:
        # Non-blocking readline: check if process exited
        if proc.poll() is not None:
            return False
        try:
            import select
            r, _, _ = select.select([proc.stdout], [], [], 0.2)
            if r:
                chunk = proc.stdout.read(256)
                if chunk:
                    buf += chunk
                    if "Connected: True" in buf:
                        return True
                    if "No matching BLE advertisement" in buf or "Error" in buf:
                        return False
        except Exception:
            time.sleep(0.2)
    return False


def kill_ble(proc: Optional[subprocess.Popen]) -> str:
    """Terminate BLE probe and return its stdout."""
    if proc is None:
        return ""
    proc.terminate()
    try:
        out, _ = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate()
    return out or ""


def switch_audio_source() -> Optional[str]:
    """Return path to SwitchAudioSource if available."""
    return shutil.which("SwitchAudioSource")


def start_audio_stream(device_name: str, verbose: bool) -> Optional[subprocess.Popen]:
    """Route macOS audio output to device_name and start playing a looping tone.

    Returns the afplay subprocess, or None if routing/playback could not be started.
    The caller is responsible for calling stop_audio_stream() when done.
    """
    # Route macOS audio output to the BT device
    routed = False
    sas = switch_audio_source()
    if sas:
        try:
            r = subprocess.run([sas, "-s", device_name, "-t", "output"],
                               capture_output=True, timeout=5)
            routed = r.returncode == 0
        except Exception:
            pass

    if not routed:
        # Fallback: osascript (works without SwitchAudioSource but is flaky)
        script = (
            f'tell application "System Events" to tell process "SystemUIServer" to '
            f'set value of pop up button 1 of menu bar item "Volume" of menu bar 1 to "{device_name}"'
        )
        try:
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
            routed = True  # best-effort, can't reliably detect success
        except Exception:
            pass

    if not routed:
        _vprint(verbose, "(audio route failed, continuing without audio) ", end="")

    # Play a looping system sound — anything that produces a continuous audio stream
    sound = "/System/Library/Sounds/Purr.aiff"
    try:
        proc = subprocess.Popen(
            ["bash", "-c", f"while true; do afplay '{sound}'; done"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return proc
    except Exception:
        return None


def stop_audio_stream(proc: Optional[subprocess.Popen]) -> None:
    if proc is None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()


# ---------------------------------------------------------------------------
# Single iteration
# ---------------------------------------------------------------------------
def run_ble_first(
    n: int, mon: SerialMonitor, bt_address: str, device_name: str,
    bt_hold_s: float, verbose: bool, play_audio: bool = True,
) -> IterResult:
    """Connect BLE, then Classic BT; watch for crash or graceful restart."""
    res = IterResult(n=n, sequence="ble-first", outcome=Outcome.TIMEOUT)
    t0 = time.monotonic()
    iter_start = t0

    # -- 1. Reset and wait for boot ------------------------------------------
    _vprint(verbose, f"  reset ... ", end="")
    mon.reset_esp32()
    if not mon.wait_for(_RE_REBOOT, timeout=10, since_ts=t0):
        _vprint(verbose, "TIMEOUT (no boot)")
        res.duration_s = time.monotonic() - iter_start
        return res
    boot_ts = time.monotonic()
    _vprint(verbose, "booted ", end="")
    time.sleep(1.5)  # let BT/BLE stack finish init

    # -- 2. Connect BLE (background) -----------------------------------------
    ble_proc = start_ble_background(device_name, hold_seconds=bt_hold_s + 30)
    _vprint(verbose, "→ BLE connecting ... ", end="")
    if not ble_wait_connected(ble_proc, timeout=12):
        kill_ble(ble_proc)
        res.outcome = Outcome.BLE_CONNECT_FAILED
        _vprint(verbose, "BLE FAILED")
        res.duration_s = time.monotonic() - iter_start
        return res
    res.ble_connected = True
    ble_ts = time.monotonic()
    _vprint(verbose, "BLE✓ ", end="")
    time.sleep(1.0)  # let BLE stack settle

    # -- 3. Connect Classic BT -----------------------------------------------
    _vprint(verbose, "→ BT connecting ... ", end="")
    bt_ok = bt_connect(bt_address)
    if not bt_ok:
        kill_ble(ble_proc)
        res.outcome = Outcome.BT_CONNECT_FAILED
        _vprint(verbose, "BT FAILED")
        res.duration_s = time.monotonic() - iter_start
        return res
    bt_req_ts = time.monotonic()

    # -- 4. Wait for BT connected OR crash -----------------------------------
    hit = mon.wait_for_any(
        [_RE_BT_CONNECTED, _RE_CRASH, _RE_GRACEFUL],
        timeout=15, since_ts=bt_req_ts,
    )
    if hit is None:
        kill_ble(ble_proc)
        bt_disconnect(bt_address)
        res.outcome = Outcome.TIMEOUT
        _vprint(verbose, "TIMEOUT(BT-wait)")
        res.duration_s = time.monotonic() - iter_start
        return res

    _, matched_line, matched_pat = hit

    if matched_pat is _RE_CRASH:
        res.bt_connected = False
        res.outcome = (
            Outcome.CRASH_AT_BT_CONNECT
            if _RE_HCI_CRASH.search(matched_line) or
               mon.wait_for(_RE_HCI_CRASH, timeout=1, since_ts=bt_req_ts)
            else Outcome.CRASH_OTHER
        )
        res.crash_detail = matched_line.strip()
        kill_ble(ble_proc)
        _vprint(verbose, f"CRASH ← {res.outcome.value}")
        res.min_heap = mon.min_heap_since(boot_ts)
        res.duration_s = time.monotonic() - iter_start
        return res

    if matched_pat is _RE_GRACEFUL:
        res.outcome = Outcome.GRACEFUL_RESTART
        kill_ble(ble_proc)
        _vprint(verbose, "graceful-restart(early)")
        res.min_heap = mon.min_heap_since(boot_ts)
        res.duration_s = time.monotonic() - iter_start
        return res

    # BT connected OK
    res.bt_connected = True
    res.heap_at_bt_connect = mon.heap_at_first_match(_RE_BT_CONNECTED, bt_req_ts)
    _vprint(verbose,
            f"BT✓(free={res.heap_at_bt_connect or '?'}) ", end="")

    # -- 5. Stream audio during hold (real-world simulation) ------------------
    audio_proc = None
    if play_audio:
        _vprint(verbose, "→ audio ... ", end="")
        # Wait briefly for A2DP to be ready before routing audio
        mon.wait_for(_RE_AUDIO_STARTED, timeout=3, since_ts=bt_req_ts)
        audio_proc = start_audio_stream(device_name, verbose)
        if audio_proc:
            res.audio_streamed = True
            _vprint(verbose, "♪ ", end="")

    # -- 6. Hold BT; also watch for early crash/restart during the hold -------
    # Watch from BT-connected time so we catch events that fire before disconnect.
    watch_ts = time.monotonic()
    early = mon.wait_for_any(
        [_RE_GRACEFUL, _RE_CRASH],
        timeout=bt_hold_s, since_ts=watch_ts,
    )
    if early:
        _, ol, op = early
        if op is _RE_GRACEFUL:
            res.outcome = Outcome.GRACEFUL_RESTART
            _vprint(verbose, "→ early graceful-restart")
        else:
            res.outcome = (Outcome.CRASH_AT_BT_CONNECT if _RE_HCI_CRASH.search(ol)
                           else Outcome.CRASH_OTHER)
            res.crash_detail = ol.strip()
            _vprint(verbose, f"→ early CRASH ← {res.outcome.value}")
        stop_audio_stream(audio_proc)
        kill_ble(ble_proc)
        bt_disconnect(bt_address)
        res.min_heap = mon.min_heap_since(boot_ts)
        res.reboot_seen = mon.wait_for(_RE_REBOOT, timeout=10, since_ts=watch_ts) is not None
        res.duration_s = time.monotonic() - iter_start
        return res

    # Normal path: stop audio, disconnect BT, watch for outcome.
    stop_audio_stream(audio_proc)
    _vprint(verbose, "→ BT disconnect ... ", end="")
    disc_ts = time.monotonic()  # before bt_disconnect so we catch fast restarts
    bt_disconnect(bt_address)

    # -- 6. Wait for graceful restart or crash (firmware restarts ~1.5s after BT disc)
    outcome_hit = mon.wait_for_any(
        [_RE_GRACEFUL, _RE_CRASH],
        timeout=12, since_ts=disc_ts,
    )
    if outcome_hit:
        _, ol, op = outcome_hit
        if op is _RE_GRACEFUL:
            res.outcome = Outcome.GRACEFUL_RESTART
            _vprint(verbose, "graceful-restart")
        else:
            res.outcome = (
                Outcome.CRASH_AT_BT_CONNECT
                if _RE_HCI_CRASH.search(ol)
                else Outcome.CRASH_OTHER
            )
            res.crash_detail = ol.strip()
            _vprint(verbose, f"CRASH ← {res.outcome.value}")
    else:
        # No crash, no graceful restart — device still running on near-zero heap
        res.outcome = Outcome.CLEAN
        _vprint(verbose, "clean(no-restart?)")

    kill_ble(ble_proc)
    res.min_heap = mon.min_heap_since(boot_ts)
    res.reboot_seen = mon.wait_for(_RE_REBOOT, timeout=10, since_ts=disc_ts) is not None
    res.duration_s = time.monotonic() - iter_start
    return res


def run_bt_first(
    n: int, mon: SerialMonitor, bt_address: str, device_name: str,
    bt_hold_s: float, verbose: bool, play_audio: bool = True,
) -> IterResult:
    """Connect Classic BT first, then BLE, then disconnect BT; watch outcome."""
    res = IterResult(n=n, sequence="bt-first", outcome=Outcome.TIMEOUT)
    t0 = time.monotonic()
    iter_start = t0

    # -- 1. Reset and wait for boot ------------------------------------------
    _vprint(verbose, "  reset ... ", end="")
    mon.reset_esp32()
    if not mon.wait_for(_RE_REBOOT, timeout=10, since_ts=t0):
        _vprint(verbose, "TIMEOUT (no boot)")
        res.duration_s = time.monotonic() - iter_start
        return res
    boot_ts = time.monotonic()
    _vprint(verbose, "booted ", end="")
    time.sleep(1.5)

    # -- 2. Connect Classic BT -----------------------------------------------
    _vprint(verbose, "→ BT connecting ... ", end="")
    bt_ok = bt_connect(bt_address)
    if not bt_ok:
        res.outcome = Outcome.BT_CONNECT_FAILED
        _vprint(verbose, "BT FAILED")
        res.duration_s = time.monotonic() - iter_start
        return res
    bt_req_ts = time.monotonic()

    # Wait for BT connected or crash
    hit = mon.wait_for_any(
        [_RE_BT_CONNECTED, _RE_CRASH, _RE_GRACEFUL],
        timeout=15, since_ts=bt_req_ts,
    )
    if hit is None:
        bt_disconnect(bt_address)
        res.outcome = Outcome.TIMEOUT
        _vprint(verbose, "TIMEOUT(BT-wait)")
        res.duration_s = time.monotonic() - iter_start
        return res

    _, matched_line, matched_pat = hit

    if matched_pat is _RE_CRASH:
        res.outcome = (
            Outcome.CRASH_AT_BT_CONNECT
            if _RE_HCI_CRASH.search(matched_line)
            else Outcome.CRASH_OTHER
        )
        res.crash_detail = matched_line.strip()
        _vprint(verbose, f"CRASH ← {res.outcome.value}")
        res.min_heap = mon.min_heap_since(boot_ts)
        res.duration_s = time.monotonic() - iter_start
        return res

    if matched_pat is _RE_GRACEFUL:
        res.outcome = Outcome.GRACEFUL_RESTART
        _vprint(verbose, "graceful-restart(early)")
        res.min_heap = mon.min_heap_since(boot_ts)
        res.duration_s = time.monotonic() - iter_start
        return res

    res.bt_connected = True
    res.heap_at_bt_connect = mon.heap_at_first_match(_RE_BT_CONNECTED, bt_req_ts)
    _vprint(verbose, f"BT✓(free={res.heap_at_bt_connect or '?'}) ", end="")

    # -- 3. Stream audio (real-world simulation) ------------------------------
    audio_proc = None
    if play_audio:
        _vprint(verbose, "→ audio ... ", end="")
        mon.wait_for(_RE_AUDIO_STARTED, timeout=3, since_ts=bt_req_ts)
        audio_proc = start_audio_stream(device_name, verbose)
        if audio_proc:
            res.audio_streamed = True
            _vprint(verbose, "♪ ", end="")

    # -- 4. Connect BLE while BT streaming -----------------------------------
    _vprint(verbose, "→ BLE connecting ... ", end="")
    ble_proc = start_ble_background(device_name, hold_seconds=bt_hold_s + 30)
    ble_connected = ble_wait_connected(ble_proc, timeout=12)
    if ble_connected:
        res.ble_connected = True
        _vprint(verbose, "BLE✓ ", end="")
    else:
        _vprint(verbose, "(BLE failed, continuing) ", end="")

    # -- 5. Hold BT; watch for early crash/restart ----------------------------
    watch_ts = time.monotonic()
    early = mon.wait_for_any(
        [_RE_GRACEFUL, _RE_CRASH],
        timeout=bt_hold_s, since_ts=watch_ts,
    )
    if early:
        _, ol, op = early
        if op is _RE_GRACEFUL:
            res.outcome = Outcome.GRACEFUL_RESTART
            _vprint(verbose, "→ early graceful-restart")
        else:
            res.outcome = (Outcome.CRASH_AT_BT_CONNECT if _RE_HCI_CRASH.search(ol)
                           else Outcome.CRASH_OTHER)
            res.crash_detail = ol.strip()
            _vprint(verbose, f"→ early CRASH ← {res.outcome.value}")
        stop_audio_stream(audio_proc)
        kill_ble(ble_proc)
        bt_disconnect(bt_address)
        res.min_heap = mon.min_heap_since(boot_ts)
        res.reboot_seen = mon.wait_for(_RE_REBOOT, timeout=10, since_ts=watch_ts) is not None
        res.duration_s = time.monotonic() - iter_start
        return res

    stop_audio_stream(audio_proc)
    _vprint(verbose, "→ BT disconnect ... ", end="")
    disc_ts = time.monotonic()
    bt_disconnect(bt_address)

    # -- 5. Wait for graceful restart or crash --------------------------------
    outcome_hit = mon.wait_for_any(
        [_RE_GRACEFUL, _RE_CRASH],
        timeout=12, since_ts=disc_ts,
    )
    if outcome_hit:
        _, ol, op = outcome_hit
        if op is _RE_GRACEFUL:
            res.outcome = Outcome.GRACEFUL_RESTART
            _vprint(verbose, "graceful-restart")
        else:
            res.outcome = (
                Outcome.CRASH_AT_BT_CONNECT if _RE_HCI_CRASH.search(ol)
                else Outcome.CRASH_OTHER
            )
            res.crash_detail = ol.strip()
            _vprint(verbose, f"CRASH ← {res.outcome.value}")
    else:
        res.outcome = Outcome.CLEAN
        _vprint(verbose, "clean(no-restart?)")

    kill_ble(ble_proc)
    res.min_heap = mon.min_heap_since(boot_ts)
    res.reboot_seen = mon.wait_for(_RE_REBOOT, timeout=10, since_ts=disc_ts) is not None
    res.duration_s = time.monotonic() - iter_start
    return res


# ---------------------------------------------------------------------------
# Wait for reboot between iterations
# ---------------------------------------------------------------------------
def wait_for_reboot(mon: SerialMonitor, timeout: float = 20) -> bool:
    """Block until the next '=== SweetYaar Boot ===' or timeout."""
    return mon.wait_for(_RE_REBOOT, timeout=timeout) is not None


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
def print_summary(results: list[IterResult], use_color: bool) -> None:
    total = len(results)
    if total == 0:
        return

    def pct(n: int) -> str:
        return f"{n}/{total} ({100 * n // total}%)"

    counts: dict[Outcome, int] = {o: 0 for o in Outcome}
    for r in results:
        counts[r.outcome] += 1

    bt_conn      = sum(1 for r in results if r.bt_connected)
    ble_conn     = sum(1 for r in results if r.ble_connected)
    audio_str_ct = sum(1 for r in results if r.audio_streamed)

    heap_at_bt = [r.heap_at_bt_connect for r in results if r.heap_at_bt_connect]
    min_heaps  = [r.min_heap for r in results if r.min_heap]

    def color(o: Outcome, text: str) -> str:
        if not use_color:
            return text
        return _OUTCOME_COLOR.get(o, "") + text + _RESET

    seqs = sorted({r.sequence for r in results})
    seq_str = " + ".join(seqs) if len(seqs) > 1 else seqs[0]

    print(f"\n{'='*60}")
    print(f"  Summary — {total} iterations, sequence: {seq_str}")
    print(f"{'='*60}")
    print(f"  BT connected:           {pct(bt_conn)}")
    print(f"  BLE connected:          {pct(ble_conn)}")
    if audio_str_ct > 0:
        print(f"  Audio streamed:         {pct(audio_str_ct)}")
    print()
    for o in Outcome:
        c = counts[o]
        if c > 0 or o in (Outcome.CRASH_AT_BT_CONNECT, Outcome.GRACEFUL_RESTART):
            print(f"  {color(o, f'{o.value:<28}')}  {pct(c)}")
    print()
    if heap_at_bt:
        print(f"  Heap at BT connect:  avg={sum(heap_at_bt)//len(heap_at_bt):,}  "
              f"min={min(heap_at_bt):,}  max={max(heap_at_bt):,} bytes")
    if min_heaps:
        print(f"  Min heap seen:       avg={sum(min_heaps)//len(min_heaps):,}  "
              f"min={min(min_heaps):,}  max={max(min_heaps):,} bytes")
    print(f"  Avg iteration time:  {sum(r.duration_s for r in results)/total:.1f}s")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# Progress line
# ---------------------------------------------------------------------------
def _vprint(verbose: bool, msg: str, end: str = "\n", flush: bool = True) -> None:
    if verbose:
        print(msg, end=end, flush=flush)


def print_iter_header(n: int, total: int, sequence: str, use_color: bool) -> None:
    tag = f"[{n:>{len(str(total))}}/{total}] {sequence}"
    print(tag, end="", flush=True)


def print_iter_result(res: IterResult, use_color: bool) -> None:
    label = res.outcome.value
    if use_color:
        label = _OUTCOME_COLOR.get(res.outcome, "") + label + _RESET
    heap_str = ""
    if res.heap_at_bt_connect:
        heap_str += f"  heap@BT={res.heap_at_bt_connect:,}"
    if res.min_heap:
        heap_str += f"  min={res.min_heap:,}"
    print(f"  → {label}{heap_str}  ({res.duration_s:.1f}s)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="BLE + Classic BT dual-mode stability stress tester",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--iterations", "-n", type=int, default=10,
                        help="Number of iterations (default: 10)")
    parser.add_argument("--sequence", choices=["ble-first", "bt-first", "both"],
                        default="ble-first",
                        help="Connection sequence to test (default: ble-first)")
    parser.add_argument("--bt-address",
                        default="40-22-D8-3D-8A-22",
                        help="Classic BT MAC address of the device")
    parser.add_argument("--device-name", default="SweetYaar",
                        help="BLE advertisement name of the device")
    parser.add_argument("--serial-port",
                        help="Serial port (auto-detected if omitted)")
    parser.add_argument("--bt-hold-seconds", type=float, default=6.0,
                        help="Seconds to hold BT A2DP connected per iteration (default: 6)")
    parser.add_argument("--no-audio", action="store_true",
                        help="Disable audio streaming during BT hold (default: audio ON)")
    parser.add_argument("--no-color", action="store_true",
                        help="Disable ANSI colour output")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="Suppress per-step progress (show only result lines)")
    args = parser.parse_args()

    use_color  = not args.no_color and sys.stdout.isatty()
    verbose    = not args.quiet
    play_audio = not args.no_audio

    # Check prerequisites
    if not blueutil():
        print("ERROR: blueutil not found. Install with: brew install blueutil", file=sys.stderr)
        return 1
    try:
        import serial  # noqa: F401
    except ImportError:
        print("ERROR: pyserial not installed.", file=sys.stderr)
        return 1

    port = find_serial_port(args.serial_port)
    if not port:
        print("ERROR: No USB serial port found. Connect the ESP32 and try again.",
              file=sys.stderr)
        return 1

    if play_audio and not switch_audio_source():
        print("WARNING: SwitchAudioSource not found. Audio routing may fail.", file=sys.stderr)
        print("         Install with: brew install switchaudio-osx", file=sys.stderr)
        print("         Or run with --no-audio to disable streaming.", file=sys.stderr)
        print()

    audio_str = "audio=ON (real-world)" if play_audio else "audio=OFF"
    print(f"Device : {args.device_name}  BT={args.bt_address}  serial={port}")
    print(f"Plan   : {args.iterations} × {args.sequence}  (BT hold={args.bt_hold_seconds:.0f}s/iter  {audio_str})")
    print()

    mon = SerialMonitor(port)
    mon.start()

    results: list[IterResult] = []

    try:
        for i in range(1, args.iterations + 1):
            if args.sequence == "both":
                seq = "ble-first" if i % 2 == 1 else "bt-first"
            else:
                seq = args.sequence

            print_iter_header(i, args.iterations, seq, use_color)
            if verbose:
                print()  # newline so step progress appears below header

            if seq == "ble-first":
                res = run_ble_first(i, mon, args.bt_address, args.device_name,
                                    args.bt_hold_seconds, verbose, play_audio)
            else:
                res = run_bt_first(i, mon, args.bt_address, args.device_name,
                                   args.bt_hold_seconds, verbose, play_audio)

            results.append(res)

            if not verbose:
                # Print result on same line as header
                print_iter_result(res, use_color)
            else:
                # Verbose already printed steps; add a summary line
                label = res.outcome.value
                if use_color:
                    label = _OUTCOME_COLOR.get(res.outcome, "") + label + _RESET
                heap_str = ""
                if res.heap_at_bt_connect:
                    heap_str += f"  heap@BT={res.heap_at_bt_connect:,}"
                if res.min_heap:
                    heap_str += f"  min={res.min_heap:,}"
                print(f"  ↳ {label}{heap_str}  ({res.duration_s:.1f}s)\n")

            # After every iteration the device reboots (crash or graceful restart).
            # If the runner already detected the reboot, just wait for init;
            # otherwise poll for it now.
            if i < args.iterations:
                if res.reboot_seen:
                    time.sleep(2)
                else:
                    reboot_seen = wait_for_reboot(mon, timeout=20)
                    if not reboot_seen:
                        print(f"  WARNING: no reboot after iteration {i} — "
                              "waiting 5s and continuing.")
                        time.sleep(5)
                    else:
                        time.sleep(2)

    except KeyboardInterrupt:
        print("\n[interrupted]")
    finally:
        mon.stop()

    print_summary(results, use_color)
    crash_count = sum(
        1 for r in results
        if r.outcome in (Outcome.CRASH_AT_BT_CONNECT, Outcome.CRASH_OTHER)
    )
    return 1 if crash_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
