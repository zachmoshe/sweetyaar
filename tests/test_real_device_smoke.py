from __future__ import annotations

import sys

import pytest

from helpers import find_platformio, require_usb_serial, reset_esp32_via_serial, run_command


pytestmark = pytest.mark.hardware


def require_ble_advertisement(repo_root, device_name: str, serial_port: str) -> None:
    reset_esp32_via_serial(serial_port)
    result = run_command([
        sys.executable,
        repo_root / "tools" / "ble_gatt_probe.py",
        "--name",
        device_name,
        "--timeout",
        "10",
    ], check=False)
    if result.returncode == 2 and "No matching BLE advertisement found." in result.stdout:
        pytest.skip(f"No BLE advertisement found for {device_name}.")
    if result.returncode != 0:
        pytest.skip(result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "BLE preflight failed.")


def test_real_device_ble_config_round_trip(pytestconfig: pytest.Config, repo_root) -> None:
    serial_port = require_usb_serial()
    reset_esp32_via_serial(serial_port)

    device_name = pytestconfig.getoption("--device-name")
    result = run_command([
        sys.executable,
        repo_root / "tools" / "ble_gatt_probe.py",
        "--name",
        device_name,
        "--control-smoke-test",
        "--config-api-test",
        "--config-round-trip-test",
    ], check=False)
    if result.returncode == 2 and "No matching BLE advertisement found." in result.stdout:
        pytest.skip(f"No BLE advertisement found for {device_name}.")
    if result.returncode != 0 and (
        "BleakBluetoothNotAvailableError" in result.stdout or
        "Bluetooth is unsupported" in result.stdout
    ):
        pytest.skip("Backend process cannot access macOS Bluetooth; run the BLE probe through Terminal.app.")
    if result.returncode != 0:
        pytest.fail(result.stdout)
    assert "Config round-trip persisted and restored all config fields." in result.stdout


def test_real_device_ble_reconnects_after_disconnect(pytestconfig: pytest.Config, repo_root) -> None:
    serial_port = require_usb_serial()
    reset_esp32_via_serial(serial_port)

    device_name = pytestconfig.getoption("--device-name")
    result = run_command([
        sys.executable,
        repo_root / "tools" / "ble_gatt_probe.py",
        "--name",
        device_name,
        "--reconnect-test",
        "--timeout",
        "15",
    ], check=False)
    if result.returncode == 2 and "No matching BLE advertisement found." in result.stdout:
        pytest.skip(f"No BLE advertisement found for {device_name}.")
    if result.returncode != 0 and (
        "BleakBluetoothNotAvailableError" in result.stdout or
        "Bluetooth is unsupported" in result.stdout
    ):
        pytest.skip("Backend process cannot access macOS Bluetooth; run the BLE probe through Terminal.app.")
    if result.returncode != 0:
        pytest.fail(result.stdout)
    assert "BLE reconnect test passed." in result.stdout


def test_real_device_dual_mode_concurrent(pytestconfig: pytest.Config, repo_root) -> None:
    serial_port = require_usb_serial()
    if not find_platformio(repo_root):
        pytest.skip("PlatformIO not found; expected .venv/bin/pio in this repo or a parent checkout.")

    bt_address = pytestconfig.getoption("--bt-address")
    device_name = pytestconfig.getoption("--device-name")
    require_ble_advertisement(repo_root, device_name, serial_port)
    result = run_command([
        sys.executable,
        repo_root / "tools" / "mac_bt_smoke_test.py",
        "--env",
        "esp32dev",
        "--bt-address",
        bt_address,
        "--device-name",
        device_name,
        "--skip-upload",
        "--concurrent-ble",
    ], check=False)
    skip_markers = [
        "No serial port found",
        "No Bluetooth address provided/found",
        "blueutil connect failed",
        "Could not find an output device matching",
        "PlatformIO not found",
        "BLE background process exited before",
    ]
    if result.returncode != 0 and any(marker in result.stdout for marker in skip_markers):
        pytest.skip(result.stdout.strip().splitlines()[-1])
    if result.returncode != 0:
        pytest.fail(f"Concurrent BLE+A2DP test failed:\n{result.stdout}")
    assert "Audio output routed" in result.stdout or "A2DP" in result.stdout


def test_real_device_classic_bt_audio_smoke(pytestconfig: pytest.Config, repo_root) -> None:
    serial_port = require_usb_serial()
    if not find_platformio(repo_root):
        pytest.skip("PlatformIO not found; expected .venv/bin/pio in this repo or a parent checkout.")

    bt_address = pytestconfig.getoption("--bt-address")
    device_name = pytestconfig.getoption("--device-name")
    require_ble_advertisement(repo_root, device_name, serial_port)
    result = run_command([
        sys.executable,
        repo_root / "tools" / "mac_bt_smoke_test.py",
        "--env",
        "esp32dev",
        "--bt-address",
        bt_address,
        "--device-name",
        device_name,
    ], check=False)
    skip_markers = [
        "No serial port found",
        "No Bluetooth address provided/found",
        "blueutil connect failed",
        "Could not find an output device matching",
        "PlatformIO not found",
    ]
    if result.returncode != 0 and any(marker in result.stdout for marker in skip_markers):
        pytest.skip(result.stdout.strip().splitlines()[-1])
    if result.returncode != 0:
        pytest.fail(result.stdout)
    assert "A2DP" in result.stdout or "Audio output routed" in result.stdout
