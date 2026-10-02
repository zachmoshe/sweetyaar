"""Exercise enrollment timing, ownership and authorization without a radio."""
import shutil
import re

import pytest

from helpers import run_checked


def test_pairing_gestures_and_identity(repo_root, tmp_path):
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("A C++ compiler is required.")
    src = repo_root / "firmware/esp32/src"
    led_source = (src / "StatusLed.cpp").read_text()
    start = led_source.index("void StatusLed::service(")
    (tmp_path / "status_led_service_under_test.inc").write_text(
        led_source[start:led_source.index("\n}", start) + 2])
    exe = tmp_path / "pairing_policy"
    run_checked([compiler, "-std=c++17", "-Wall", "-Wextra", "-I", src, "-I", tmp_path,
                 repo_root / "tests/pairing_policy_native_test.cpp",
                 src / "StatusLedPolicy.cpp", "-o", exe])
    assert "pairing policy tests passed" in run_checked([exe]).stdout


def test_ble_authorization_and_takeover(repo_root, tmp_path):
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("A C++ compiler is required.")
    src = repo_root / "firmware/esp32/src"
    header = (src / "BLEParentService.h").read_text()
    header = re.sub(r"^#(?:include|pragma).*\n", "", header, flags=re.MULTILINE)
    header = header.replace("private:", "public:")
    source = (src / "BLEParentService.cpp").read_text()
    # Execute all production transport/security methods. Only begin() (GATT
    # registration) and the radio/NVS boundaries are replaced by host stubs.
    (tmp_path / "ble_service_under_test.inc").write_text(
        '#include "Config.h"\n' + header + "\n" +
        source[source.index("void BLEParentService::updateVolume"):])
    exe = tmp_path / "ble_access"
    run_checked([compiler, "-std=c++17", "-Wall", "-Wextra", "-I", src,
                 "-I", tmp_path, repo_root / "tests/ble_access_native_test.cpp",
                 src / "ChargerStatus.cpp", "-o", exe])
    assert "BLE authorization and takeover tests passed" in run_checked([exe]).stdout


def test_bond_store_migration_and_reset(repo_root, tmp_path):
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("A C++ compiler is required.")
    src = repo_root / "firmware/esp32/src"
    header = (src / "BluetoothAccess.h").read_text()
    header = re.sub(r"^#(?:include|pragma).*\n", "", header, flags=re.MULTILINE)
    source = (src / "BluetoothAccess.cpp").read_text()
    source = re.sub(r"^#include.*\n", "", source, flags=re.MULTILINE)
    (tmp_path / "approvals_under_test.inc").write_text(
        '#include "PairingPolicy.h"\n#include "BleIdentity.h"\n' + header + "\n" + source)
    exe = tmp_path / "approvals"
    run_checked([compiler, "-std=c++17", "-Wall", "-Wextra", "-I", src, "-I", tmp_path,
                 repo_root / "tests/bluetooth_approvals_native_test.cpp", "-o", exe])
    assert "Bluetooth bond migration and reset tests passed" in run_checked([exe]).stdout


def test_classic_pairing_and_audio_admission(repo_root, tmp_path):
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("A C++ compiler is required.")
    header = (repo_root / "firmware/esp32/src/ApprovedA2DPSink.h").read_text()
    header = re.sub(r"^#(?:include|pragma).*\n", "", header, flags=re.MULTILINE)
    adapter = (repo_root / "firmware/esp32/src/ClassicBluetooth.cpp").read_text()
    adapter = re.sub(r"^#include.*\n", "", adapter, flags=re.MULTILINE)
    declarations = (repo_root / "firmware/esp32/src/ClassicBluetooth.h").read_text()
    declarations = re.sub(r"^#(?:include|pragma).*\n", "", declarations, flags=re.MULTILINE)
    (tmp_path / "classic_adapter_under_test.inc").write_text(declarations + "\n" + adapter)
    (tmp_path / "classic_access_under_test.inc").write_text(header)
    exe = tmp_path / "classic_access"
    run_checked([compiler, "-std=c++17", "-Wall", "-Wextra", "-I", tmp_path,
                 repo_root / "tests/classic_access_native_test.cpp", "-o", exe])
    assert "Classic authorization tests passed" in run_checked([exe]).stdout
