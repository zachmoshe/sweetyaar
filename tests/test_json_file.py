from __future__ import annotations

import pathlib
import shutil

import pytest

from helpers import run_checked


def test_json_file_save_and_load_failures(repo_root: pathlib.Path, tmp_path: pathlib.Path) -> None:
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("A C++ compiler is required for JSON-file tests.")
    # Reuse the pinned dependency installed by PlatformIO in this checkout or
    # its parent checkout; no substitute JSON implementation in the test.
    json_include = next((
        base / "firmware/esp32/.pio/libdeps/sweetyaar/ArduinoJson/src"
        for base in (repo_root, *repo_root.parents)
        if (base / "firmware/esp32/.pio/libdeps/sweetyaar/ArduinoJson/src/ArduinoJson.h").exists()
    ), None)
    if json_include is None:
        pytest.skip("Run make build to install the pinned ArduinoJson dependency.")

    exe = tmp_path / "json_file_native_test"
    run_checked([
        compiler, "-std=c++17", "-Wall", "-Wextra",
        "-I", repo_root / "tests/json_file_stubs",
        "-I", repo_root / "tests/native_stubs",
        "-I", repo_root / "firmware/esp32/src",
        "-I", json_include,
        repo_root / "firmware/esp32/src/JsonFile.cpp",
        repo_root / "firmware/esp32/src/ParentConfig.cpp",
        repo_root / "tests/json_file_native_test.cpp",
        "-o", exe,
    ])
    result = run_checked([exe])
    assert "JSON file failure/recovery-policy tests passed" in result.stdout
