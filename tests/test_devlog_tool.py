"""Decode a log image written by the firmware's own ring and macros (tools/devlog.py)."""

from __future__ import annotations

import io
import pathlib
import shutil
import struct
import sys

import pytest

from helpers import run_checked

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "firmware/esp32/src"
sys.path.insert(0, str(ROOT / "tools"))

import devlog  # noqa: E402


@pytest.fixture(scope="module")
def image(tmp_path_factory: pytest.TempPathFactory) -> dict[str, pathlib.Path]:
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("A C++ compiler is required.")
    directory = tmp_path_factory.mktemp("devlog")
    exe = directory / "writer"
    run_checked([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", SRC, "-I", ROOT / "tests",
                 ROOT / "tests/devlog_image_writer.cpp", SRC / "DevLogRing.cpp", "-o", exe])
    paths = {"log": directory / "devlog-test.bin", "serial": directory / "serial.txt",
             "core": directory / "expected-core.bin"}
    run_checked([exe, paths["log"], paths["serial"], paths["core"]])
    return paths


def decoded(path: pathlib.Path, **options) -> tuple[str, list[pathlib.Path]]:
    catalog = devlog.load_catalog()
    out = io.StringIO()
    cores = devlog.dump(devlog.read_log(path.read_bytes(), catalog), catalog, out=out,
                        core_dir=path.parent, core_stem=path.stem, **options)
    return out.getvalue(), cores


def test_decoder_prints_what_the_firmware_printed(image: dict[str, pathlib.Path]) -> None:
    text, _ = decoded(image["log"])
    lines = text.splitlines()
    for line in image["serial"].read_text().splitlines():
        assert any(decoded_line.endswith("  " + line) for decoded_line in lines), line


def test_wrapped_ring_boots_and_wall_time(image: dict[str, pathlib.Path]) -> None:
    text, _ = decoded(image["log"])
    assert "Device 24:0A:C4:01:02:03: 6 of 6 sectors in use" in text or "5 of 6 sectors" in text
    assert "The ring has wrapped" in text
    assert "--- Boot 1 (its start was overwritten) ---" in text
    assert "[Log] Boot 1 " not in text
    # The time sync at +0:33:20 dates the earlier records of the same boot.
    assert "2026-01-01 01:51:49.000   +0:25:09.000  [Telemetry] battery=3900mV state=1 charger=2 " \
           "cond=0x0003 activity=0x81 vol=50% free=62499 largest=40000 min=30000" in text
    assert "2026-01-01 02:00:00.000   +0:33:20.000  [Bedtime] Time synced epoch=1767225600 tzOffsetMin=120" in text
    # Boot 2 has no clock; boot 3 takes it from BOOT's epoch and CLOCK_RETAINED.
    assert f"--- Boot 2 ---\n{'-':23}  {'+0:00:00.100':>13}  [Log] Boot 2 streak=1 reset=PANIC(4)" in text
    assert "2026-01-01 03:00:00.000   +0:00:00.100  [Log] Boot 3 streak=0 reset=DEEPSLEEP(8)" in text
    assert "2026-01-01 03:00:02.500   +0:00:02.600  [Boot] Ready. (2500ms)" in text


def test_numeric_names_unknown_events_and_torn_write(image: dict[str, pathlib.Path]) -> None:
    text, _ = decoded(image["log"])
    assert "[SM] playing_song → idle" in text
    assert "[SM] State=playing_song Event=SM_EVENT(99)" in text
    assert "[Unknown event 0x7FFF] 42" in text
    assert "torn write" in text
    assert decoded(image["log"], show_ids=True)[0].count("BOOT_READY: [Boot] Ready.") == 1


def test_core_dump_is_reassembled(image: dict[str, pathlib.Path]) -> None:
    text, cores = decoded(image["log"])
    assert "(3 core dump chunks)" in text
    assert [core.name for core in cores] == ["devlog-test-boot2-core.bin"]
    assert cores[0].read_bytes() == image["core"].read_bytes()
    chunked, _ = decoded(image["log"], chunks=True)
    assert chunked.count("[Crash] Core dump offset=") == 3


def test_last_boots_only(image: dict[str, pathlib.Path]) -> None:
    text, _ = decoded(image["log"], boots=1)
    assert "--- Boot 3 ---" in text and "--- Boot 2 ---" not in text


def test_render_is_tolerant_of_catalog_changes() -> None:
    assert devlog.render("a=%u b=%u", [1], {}) == "a=1 b=?"
    assert devlog.render("a=%u", [1, "x", 2.5], {}) == 'a=1 +"x" 2.5'
    assert devlog.render("%08lX %d%% %.2f %-4s|", [0x1234, -5, 1.0, "ab"], {}) == "00001234 -5% 1.00 ab  |"
    assert devlog.render("%X", [-1], {}) == "FFFFFFFF"


def test_partition_table_finds_old_and_new_labels() -> None:
    def entry(label: str, kind: int, subtype: int, offset: int, size: int) -> bytes:
        return b"\xAA\x50" + struct.pack("<BBII", kind, subtype, offset, size) + label.encode().ljust(16, b"\0") + b"\0" * 4
    table = entry("nvs", 1, 2, 0x9000, 0x5000) + entry("spiffs", 1, 0x82, 0x670000, 0x180000) + b"\xEB\xEB" + b"\xFF" * 30
    assert devlog.parse_partition_table(table) == {"nvs": (1, 2, 0x9000, 0x5000), "spiffs": (1, 0x82, 0x670000, 0x180000)}
