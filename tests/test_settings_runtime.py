"""Execute the production settings branch, SD persistence and runtime rules natively."""

from __future__ import annotations

import pathlib
import re
import shutil

import pytest

from helpers import run_checked


def function_source(source: str, name: str) -> str:
    match = re.search(rf"^[\w:]+ {name}\([^;]*?\) \{{", source, re.MULTILINE)
    assert match, f"Missing production function: {name}"
    return source[match.start():source.index("\n}", match.end()) + 2]


@pytest.fixture(scope="module")
def settings_runtime_exe(repo_root: pathlib.Path, tmp_path_factory) -> pathlib.Path:
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("A C++ compiler is required for firmware settings tests.")
    json_include = next((
        base / "firmware/esp32/.pio/libdeps/sweetyaar/ArduinoJson/src"
        for base in (repo_root, *repo_root.parents)
        if (base / "firmware/esp32/.pio/libdeps/sweetyaar/ArduinoJson/src/ArduinoJson.h").exists()
    ), None)
    assert json_include, "Run make build to install ArduinoJson."
    src = repo_root / "firmware/esp32/src"
    main = (src / "main.cpp").read_text()
    catalog = (src / "ContentCatalog.cpp").read_text()
    build = tmp_path_factory.mktemp("settings_runtime")

    # Compile the actual handler and its runtime helpers, not a reimplementation
    # of their policy. Only hardware/transport boundaries are stubbed. Extracting
    # them avoids pulling the ESP32 audio/Bluetooth stack into a host executable.
    functions = [function_source(main, name) for name in (
        "readSleepSeconds", "parseBedtimeTimeString", "isKnownTheme",
        "applyActiveThemeFallback", "bedtimeAutomaticActive", "bedtimeRuntimeActive",
        "clearExpiredBedtimeOverride", "pollBedtimeMode", "bedtimeEffectiveSongTheme",
        "effectiveVolumePct", "applyEffectiveVolume", "applyVolume",
    )]
    declarations = "\n".join(function.split("{", 1)[0].strip() + ";" for function in functions)
    branch = main[main.index('    if (op == "setConfig") {'):
                  main.index('    if (op == "setTheme") {')]
    boot = main[main.index("    activeTheme = parentConfig.defaultTheme();"):
                main.index("    // The production /CE circuit")]
    (build / "settings_production.inc").write_text(
        declarations + "\n" + "\n".join(functions) +
        "\nnamespace ContentCatalog {\n" +
        function_source(catalog, "formatTimeOfDay") + "\n" +
        function_source(catalog, "updateSdConfig") + "\n}\n" +
        'void saveSettings(JsonDocument& doc) {\nString op = "setConfig";\n'
        'uint32_t requestId = 1;\n' + branch + "}\n" +
        "void applyBootDefaults() {\n" + boot + "}\n"
    )
    exe = build / "settings_runtime_test"
    run_checked([
        compiler, "-std=c++17", "-Wall", "-Wextra",
        "-I", repo_root / "tests/json_file_stubs",
        "-I", repo_root / "tests/native_stubs",
        "-I", src, "-I", json_include, "-I", build,
        src / "JsonFile.cpp", src / "ParentConfig.cpp", src / "BedtimeMode.cpp",
        repo_root / "tests/settings_runtime_native_test.cpp", "-o", exe,
    ])
    return exe


@pytest.mark.parametrize("scenario", [
    "defaults", "unrelated", "bedtime_cap", "bedtime_theme", "bedtime_schedule",
    "bedtime_disabled", "unchanged_bedtime", "failed_save", "boot_defaults",
])
def test_settings_preserve_runtime(settings_runtime_exe: pathlib.Path, scenario: str) -> None:
    result = run_checked([settings_runtime_exe, scenario])
    assert "settings runtime test passed" in result.stdout
