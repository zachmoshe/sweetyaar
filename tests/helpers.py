from __future__ import annotations

import glob
import pathlib
import shutil
import subprocess
import time

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def find_platformio(root: pathlib.Path = ROOT) -> pathlib.Path | None:
    for base in (root, *root.parents):
        candidate = base / ".venv" / "bin" / "pio"
        if candidate.exists():
            return candidate
    found = shutil.which("pio")
    return pathlib.Path(found) if found else None


def serial_ports() -> list[str]:
    patterns = [
        "/dev/cu.usbserial*",
        "/dev/cu.SLAB_USBtoUART*",
        "/dev/cu.wchusbserial*",
        "/dev/cu.usbmodem*",
    ]
    ports: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        for port in sorted(glob.glob(pattern)):
            if port not in seen:
                seen.add(port)
                ports.append(port)
    return ports


def require_usb_serial() -> str:
    ports = serial_ports()
    if not ports:
        pytest.skip("No ESP32 USB serial device found.")
    return ports[0]


def reset_esp32_via_serial(port: str, boot_wait_sec: float = 4.0) -> None:
    try:
        import serial
    except ImportError:
        pytest.skip("pyserial is not installed; cannot reset ESP32 over USB serial.")

    try:
        with serial.Serial(port, 115200, timeout=0.2) as ser:
            # ESP32 dev boards wire RTS to EN/reset and DTR to GPIO0/boot.
            # Keep GPIO0 high, pulse EN low, then let the app firmware boot.
            ser.dtr = False
            ser.rts = True
            time.sleep(0.1)
            ser.rts = False
            time.sleep(0.1)
            ser.dtr = False
    except serial.SerialException as exc:
        pytest.skip(f"Could not reset ESP32 on {port}: {exc}")

    time.sleep(boot_wait_sec)


def run_command(
    cmd: list[str | pathlib.Path],
    *,
    cwd: pathlib.Path = ROOT,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(part) for part in cmd],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=check,
    )


def run_checked(cmd: list[str | pathlib.Path], *, cwd: pathlib.Path = ROOT) -> subprocess.CompletedProcess[str]:
    return run_command(cmd, cwd=cwd, check=True)
