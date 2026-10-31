"""The log viewer's merge of overlapping fetches and its HTTP API (tools/logviewer)."""

from __future__ import annotations

import json
import pathlib
import sys
import threading
import urllib.request

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/logviewer"))
sys.path.insert(0, str(ROOT / "tests"))

import devlog_fixture  # noqa: E402
import history  # noqa: E402
import server  # noqa: E402

DEVICE = "AA:BB:CC:00:11:22"


@pytest.fixture()
def library(tmp_path: pathlib.Path) -> history.Library:
    devlog_fixture.write_demo(tmp_path)
    return history.Library(tmp_path)


def test_overlapping_fetches_merge_without_duplicates(library: history.Library) -> None:
    story = devlog_fixture.demo_story()
    device = library.device(DEVICE)
    assert device["summary"]["snapshots"] == 2
    assert len(device["records"]) == len(story.entries)
    assert [boot["boot"] for boot in device["boots"]] == [1, 2, 3, 4, 5]
    assert device["summary"]["name"] == "Renamed Yaar"  # the newest name record wins
    assert device["summary"]["firmware"] == ["1.1.0", "1.2.0"]  # updated over BLE after boot 2
    assert device["summary"]["installs"] == 1
    assert [boot["firmware"] for boot in device["boots"]] == ["1.1.0", "1.1.0", "1.2.0", "1.2.0", "1.2.0"]


def test_wrapped_fetch_keeps_older_history_from_earlier_fetches(tmp_path: pathlib.Path) -> None:
    story = devlog_fixture.demo_story()
    device_id = devlog_fixture.DEMO_DEVICE
    full = devlog_fixture.image(story.entries, device_id, 384)
    wrapped = devlog_fixture.image(story.entries, device_id, 2)  # only the newest sector survives
    (tmp_path / f"devlog-{device_id.hex()}-20261103-180000.bin").write_bytes(full)
    (tmp_path / f"devlog-{device_id.hex()}-20261104-210000.bin").write_bytes(wrapped)
    device = history.Library(tmp_path).device(DEVICE)
    assert len(device["records"]) == len(story.entries)

    alone = tmp_path / "alone"
    alone.mkdir()
    (alone / f"devlog-{device_id.hex()}-20261104-210000.bin").write_bytes(wrapped)
    partial = history.Library(alone).device(DEVICE)
    assert len(partial["records"]) < len(story.entries)
    assert partial["boots"][0]["startOverwritten"]


def test_boots_time_and_crash(library: history.Library) -> None:
    boots = {boot["boot"]: boot for boot in library.device(DEVICE)["boots"]}
    assert [boots[number]["reset"] for number in range(1, 6)] == \
        ["power-on", "deep-sleep", "deep-sleep", "panic", "power-on"]
    # Boot 1 is dated by the app's clock sync at +3 min; boot 2 by BOOT's epoch.
    assert boots[1]["timeKnown"] and boots[2]["timeKnown"] and not boots[4]["timeKnown"]
    start = history.dt.datetime.fromtimestamp(boots[2]["realStart"], history.dt.timezone.utc)
    assert start.strftime("%Y-%m-%d %H:%M:%S") == "2026-11-03 11:30:00"  # local wall time
    # The panic is reported by boot 4, so boot 3 is the one that crashed.
    assert boots[3]["crashedInto"] == 4 and boots[4]["crash"]["task"] == "loopTask"
    assert boots[4]["realStart"] == pytest.approx(boots[3]["realStart"] + boots[3]["duration"]
                                                  + history.UNKNOWN_TIME_GAP_S)
    assert boots[1]["sleep"] and boots[2]["sleep"] and not boots[3]["sleep"]


def test_intervals_telemetry_and_drain(library: history.Library) -> None:
    device = library.device(DEVICE)
    kinds = [(interval["lane"], interval["kind"]) for interval in device["intervals"]]
    assert kinds.count(("state", "playing_song")) == 9  # eight in boot 1, one cut short by the crash
    assert kinds.count(("state", "playing_animal")) == 5
    assert ("state", "bt_streaming") in kinds and ("classic", "Classic BT") in kinds
    assert kinds.count(("ble", "BLE app")) == 2
    streaming = next(i for i in device["intervals"] if i["kind"] == "bt_streaming")
    assert streaming["xa1"] - streaming["xa0"] == pytest.approx(3635)
    summary = device["summary"]
    assert summary["btHours"] == pytest.approx(3635 / 3600, abs=0.01)
    assert summary["songsStarted"] == 9  # from WAV_PLAYING, including the one the crash cut short
    assert summary["animalsStarted"] == 5
    assert summary["drain"]["playing"]["mvPerHour"] > summary["drain"]["idle"]["mvPerHour"] > 0
    assert any(point["charger"] == 4 for point in device["telemetry"])


def test_repeated_condition_is_shown_with_its_record(library: history.Library) -> None:
    device = library.device(DEVICE)
    repeated = next(record for record in device["records"] if record[4] == "REPEATED")
    assert repeated[5] == "power" and repeated[6] == "error"  # as CHARGER_I2C_READ_FAILED
    assert "CHARGER_I2C_READ_FAILED from 5000ms repeated 594 more times" in repeated[7]
    assert repeated[8] == [["×594 more", "info"]]
    [span] = device["repeats"]
    assert span["area"] == "power" and span["xa1"] - span["xa0"] == pytest.approx(594)


def test_levels() -> None:
    assert history.level_of("CRASH", "[Crash] task=x") == "error"
    assert history.level_of("BATTERY_ADC_INVALID", "[Battery] Invalid raw ADC=78mV") == "warn"
    assert history.level_of("BLE_CONNECT", "[BLE] CONNECT conn=1") == "info"
    # An argument named fail_reason is not a failure; the decoded result decides.
    text = "[BLE] AUTH conn=0 peer=80:A9:97:27:E9:02 success=1 fail_reason=0x00 mode=0x09"
    assert history.level_of("BLE_AUTH", text, [["paired", "ok"]]) == "info"
    assert history.level_of("BLE_AUTH", text, [["pairing failed", "bad"]]) == "error"


def test_http_api(library: history.Library) -> None:
    httpd = server.http.server.ThreadingHTTPServer(("127.0.0.1", 0), server.handler_for(library))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        devices = json.load(urllib.request.urlopen(base + "/api/devices"))["devices"]
        assert [device["device"] for device in devices] == [DEVICE, "AA:BB:CC:00:99:88"]
        detail = json.load(urllib.request.urlopen(base + "/api/device?id=" + DEVICE))
        assert detail["records"][0][4] == "BOOT"
        stats = json.load(urllib.request.urlopen(base + "/api/stats"))
        assert stats["totals"]["boots"] == 6
        page = urllib.request.urlopen(base + "/").read().decode()
        assert "<title>SweetYaar Logs</title>" in page
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(base + "/../history.py")
    finally:
        httpd.shutdown()


def test_reinstall_of_the_same_version_counts_as_an_installation(tmp_path: pathlib.Path) -> None:
    story = devlog_fixture.Story()
    story.start("power-on", 1, 0)
    story.slot = "app1"  # an update over BLE writes the other slot
    story.start("software", 3, 0)
    story.start("deep-sleep", 8, 2)
    device_id = bytes.fromhex("aabbcc000001")
    (tmp_path / f"devlog-{device_id.hex()}-20261104-120000.bin").write_bytes(
        devlog_fixture.image(story.entries, device_id, 8))
    summary = history.Library(tmp_path).device("AA:BB:CC:00:00:01")["summary"]
    assert summary["firmware"] == ["1.1.0"] and summary["installs"] == 1


def test_badges_translate_codes_and_bits() -> None:
    import decoders

    def texts(name: str, args: list) -> list[str]:
        return [text for text, _ in decoders.badges(name, args)]

    # The bench board without a battery or thermistor (real values).
    assert texts("CHARGER_REGISTERS", ["UNKNOWN", 0xE1, 0x40, 0x40, "VALID_INPUT"]) == [
        "done or disabled", "no thermistor", "input power good", "battery undervoltage",
        "event: input current limit"]
    assert texts("TELEMETRY", [0, 0, 0, 0x0104, 0x80, 75, 24112, 21492, 23164]) == [
        "no battery reading", "charger unknown", "no thermistor", "battery undervoltage"]
    assert texts("TELEMETRY", [3950, 1, 4, 0, 0x0B, 60, 1, 1, 1]) == [
        "battery good", "charging", "playing a WAV", "phone connected", "app connected", "SD card not ready"]
    assert texts("BLE_DISCONNECT", [1, 0x08, 0]) == ["timeout"]
    assert texts("CRASH", ["loopTask", 28]) == ["bad read address"]
    assert texts("BOOT", [3, 0, "deep-sleep", 8, 2]) == ["deep-sleep wake", "woken by movement"]
    assert texts("BOOT", [4, 2, "panic", 4, 0]) == ["crash", "2 bad resets in a row"]
    assert texts("BOOT", [11, 0, "power-on", 1, 0]) == ["cold start"]
    assert texts("SLEEP_WAKE", [0, 0]) == ["cold start"]
    assert texts("SLEEP_WAKE", [3, 0]) == ["woken by charger"]
    assert texts("LOG_DROPPED", [0, 12, 0, 0, 0]) == ["12 lost (no erased sector)"]
    assert texts("TELEMETRY", ["changed"]) == []  # never breaks on unexpected arguments


def test_badge_decoders_match_the_catalog() -> None:
    import decoders

    catalog = history.devlog.load_catalog()
    names = {name: fmt for name, fmt in catalog.events.values()}
    for name, (needed, _) in decoders.DECODERS.items():
        assert name in names, name
        assert len(history.devlog.SPEC.findall(names[name])) >= needed, name
