"""Exercise the on-flash diagnostic log on the host and check its event catalog."""

from __future__ import annotations

import pathlib
import re
import shutil

import pytest

from helpers import run_checked

SRC = pathlib.Path(__file__).resolve().parents[1] / "firmware/esp32/src"


def catalog() -> tuple[dict[str, int], dict[str, str]]:
    text = (SRC / "DevLogEvents.h").read_text()
    ids = {name: int(value, 16) for name, value in re.findall(r"#define DEVLOG_ID_(\w+) (0x[0-9A-F]+)", text)}
    formats = dict(re.findall(r'#define DEVLOG_FMT_(\w+) ("(?:[^"\\]|\\.)*")', text))
    return ids, formats


def test_devlog_ring_and_macros(repo_root: pathlib.Path, tmp_path: pathlib.Path) -> None:
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("A C++ compiler is required.")
    exe = tmp_path / "devlog"
    run_checked([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", SRC, "-I", repo_root / "tests",
                 repo_root / "tests/devlog_native_test.cpp", SRC / "DevLogRing.cpp", "-o", exe])
    assert "devlog tests passed" in run_checked([exe]).stdout


def test_event_catalog_ids_are_unique_and_complete() -> None:
    ids, formats = catalog()
    assert ids.keys() == formats.keys()
    values = list(ids.values())
    assert len(values) == len(set(values)), "event IDs must never be reused"
    assert all(0 < value <= 0xFFFF for value in values)
    used = set()
    for path in [*SRC.glob("*.cpp"), *SRC.glob("*.h")]:
        if path.name == "DevLog.h":
            continue  # macro definitions and usage comments
        used.update(re.findall(r"\bDLOG(?:_DETAIL|_STORE)?\((\w+)", path.read_text()))
    assert used - ids.keys() == set()


def test_repeating_events_are_listed_conditions_only() -> None:
    text = (SRC / "DevLogEvents.h").read_text()
    listing = re.search(r"#define DEVLOG_REPEATING_EVENTS((?:.*\\\n)*.*)", text).group(1)
    listed = set(re.findall(r"DEVLOG_ID_(\w+)", listing))
    ids, _ = catalog()
    assert listed and listed <= ids.keys()
    # Log, boot, crash, telemetry, usage and time events (0x00xx) and every
    # Bluetooth or update event stay one record per occurrence.
    assert not {name for name in listed if ids[name] < 0x0100}
    assert not {name for name in listed if name.startswith(("BLE_", "BT_", "OTA_"))}


def enum_names(header: str, enum: str) -> list[str]:
    body = re.search(rf"enum class {enum} \{{(.*?)\}};", header, re.S).group(1)
    return [re.sub(r"//.*", "", line).strip().rstrip(",") for line in body.splitlines()
            if re.sub(r"//.*", "", line).strip()]


def test_numeric_state_machine_names_match_firmware() -> None:
    header = (SRC / "StateMachine.h").read_text()
    source = (SRC / "StateMachine.cpp").read_text()
    events = (SRC / "DevLogEvents.h").read_text()
    for enum, function, listing in (("State", "stateToString", "SM_STATE"),
                                    ("Event", "eventToString", "SM_EVENT")):
        body = source[source.index(f"const char* {function}("):]
        body = body[:body.index("\n}")]
        names = dict(re.findall(rf"case {enum}::(\w+):\s*return \"([^\"]+)\"", body))
        expected = [names[value] for value in enum_names(header, enum)]
        stored = re.search(rf'#define DEVLOG_ENUM_{listing} "([^"]*)"', events).group(1).split(",")
        assert stored == expected
