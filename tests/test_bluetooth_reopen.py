"""Exercise the production Classic reconnect cooldown without a radio."""

import re
import shutil

import pytest

from helpers import run_checked, run_command
from test_catalog_pagination import production_function
from test_settings_runtime import function_source


@pytest.fixture(scope="module")
def bluetooth_reopen_exe(repo_root, tmp_path_factory):
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("A C++ compiler is required for Bluetooth cooldown tests.")
    src = repo_root / "firmware/esp32/src"
    main = (src / "main.cpp").read_text()
    build = tmp_path_factory.mktemp("bluetooth_reopen")
    (build / "bluetooth_reopen.inc").write_text("\n".join(
        function_source(main, name) for name in (
            "scheduleBluetoothReopen", "reopenBluetoothForPairing", "pollBluetoothReopen",
        )
    ))
    constants = []
    for name in ("BT_REOPEN_DELAY_MS", "RTC_HEAP_RESTART_MAGIC", "MAX_HEAP_RESTARTS"):
        declaration = re.search(rf"^(?:static )?const(?:expr)? uint32_t {name} = [^;]+;", main, re.MULTILINE)
        assert declaration, f"Missing production constant: {name}"
        constants.append(declaration.group())
    (build / "bluetooth_reopen_constants.inc").write_text("\n".join(constants))
    adapter = (src / "ClassicBluetooth.cpp").read_text()
    (build / "classic_scan_access.inc").write_text(function_source(adapter, "ClassicBluetooth::setAccess"))
    # Remove the class indentation so the shared extractor can read the inline
    # method. Run the real access refresh, not a mock that assumes it reopens.
    sink = "\n".join(line[4:] if line.startswith("    ") else line
                     for line in (src / "ApprovedA2DPSink.h").read_text().splitlines())
    (build / "classic_refresh_access.inc").write_text(production_function(sink, "refreshAccess"))
    exe = build / "bluetooth_reopen"
    run_checked([
        compiler, "-std=c++17", "-Wall", "-Wextra",
        "-I", build, "-I", repo_root / "tests/native_stubs", "-I", src,
        src / "StateMachine.cpp", repo_root / "tests/bluetooth_reopen_native_test.cpp",
        "-o", exe,
    ])
    return exe


@pytest.mark.parametrize("scenario", ["idle", "song", "short-animal"])
def test_classic_reconnect_after_disconnect_cooldown(bluetooth_reopen_exe, scenario):
    result = run_command([bluetooth_reopen_exe, scenario], check=False)
    assert result.returncode == 0, result.stdout
