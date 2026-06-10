from __future__ import annotations

import shutil
import sys

import pytest

from helpers import find_platformio, require_ble_advertisement, require_usb_serial, reset_esp32_via_serial, run_command


pytestmark = pytest.mark.hardware


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


def test_real_device_dual_mode_stability(pytestconfig: pytest.Config, repo_root) -> None:
    """Stress-test BLE + Classic BT dual-mode stability over 10 iterations.

    Runs 5 ble-first and 5 bt-first connection sequences with audio streaming
    to reproduce the real-world usage pattern.  Any firmware crash fails the test.
    Requires: blueutil, pyserial, USB serial connection to the device.
    """
    serial_port = require_usb_serial()

    if not shutil.which("blueutil"):
        pytest.skip("blueutil not found (brew install blueutil).")

    bt_address  = pytestconfig.getoption("--bt-address")
    device_name = pytestconfig.getoption("--device-name")

    cmd = [
        sys.executable,
        repo_root / "tools" / "bt_stress_test.py",
        "--iterations", "10",
        "--sequence", "both",
        "--bt-address", bt_address,
        "--device-name", device_name,
        "--serial-port", serial_port,
        "--bt-hold-seconds", "6",
        "--no-color",
        "--quiet",
    ]
    result = run_command(cmd, check=False)

    if result.returncode != 0 and "No USB serial port found" in result.stdout:
        pytest.skip("No USB serial port found.")
    if result.returncode != 0 and "blueutil not found" in result.stdout:
        pytest.skip("blueutil not found.")

    if result.returncode != 0:
        pytest.fail(
            f"Dual-mode stability test detected firmware crashes.\n\n{result.stdout}"
        )

    assert "Summary" in result.stdout


def test_real_device_bedtime_activation(pytestconfig: pytest.Config, repo_root) -> None:
    """Verify that syncing the device time inside/outside the configured bedtime window
    causes the firmware to report the expected bedtime.active state."""
    serial_port = require_usb_serial()
    device_name = pytestconfig.getoption("--device-name")
    require_ble_advertisement(repo_root, device_name, serial_port)

    result = run_command([
        sys.executable,
        repo_root / "tools" / "ble_gatt_probe.py",
        "--name",
        device_name,
        "--bedtime-activation-test",
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
    if result.returncode != 0 and "Bedtime is disabled" in result.stdout:
        pytest.skip("Bedtime is disabled on device; enable it in the parent app to run this test.")
    if result.returncode != 0:
        pytest.fail(result.stdout)
    assert "Bedtime activation test passed." in result.stdout
