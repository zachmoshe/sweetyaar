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
    assert device["summary"]["lastSector"] == max(device["snapshots"][-1]["sequence"])
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
        assert len(stats["devices"]) == 2 and sum(stats["firmware"].values()) <= 2
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


def drop_sector(image: bytes, sequence: int) -> bytes:
    """The image without the sector holding |sequence| (as if it was overwritten first)."""
    data = bytearray(image)
    for start in range(0, len(data), devlog_fixture.devlog.SECTOR_SIZE):
        if devlog_fixture.devlog.header_sequence(data[start:start + 24]) == sequence:
            data[start:start + devlog_fixture.devlog.SECTOR_SIZE] = b"\xff" * devlog_fixture.devlog.SECTOR_SIZE
    return bytes(data)


def demo_image() -> bytes:
    return devlog_fixture.image(devlog_fixture.demo_story().entries, devlog_fixture.DEMO_DEVICE, 384)


def test_missing_sectors_are_marked_where_the_log_resumes(tmp_path: pathlib.Path) -> None:
    story = devlog_fixture.Story()
    story.start("power-on", 1, 0)
    for ms in range(2000, 2000 + 1500 * 100, 100):
        story.add("HEAP", "loop", 60000, 40000, 30000, at=ms)
    image = devlog_fixture.image(story.entries, devlog_fixture.DEMO_DEVICE, 384)
    sequences = sorted(devlog_fixture.devlog.sector_map(image))
    assert len(sequences) >= 3
    (tmp_path / f"devlog-{devlog_fixture.DEMO_DEVICE.hex()}-20261104-120000.bin").write_bytes(
        drop_sector(image, sequences[1]))
    records = history.Library(tmp_path).device(DEVICE)["records"]
    markers = [index for index, record in enumerate(records) if record[4] == "MISSING_SECTORS"]
    assert len(markers) == 1
    assert "Missing 1 sector here" in records[markers[0]][7] and records[markers[0]][6] == "warn"
    # It sits right before the first record of the sector after the gap.
    assert records[markers[0] + 1][:4] == records[markers[0]][:4]
    # A later fetch that holds the sector closes the gap.
    (tmp_path / f"devlog-{devlog_fixture.DEMO_DEVICE.hex()}-20261105-120000.bin").write_bytes(image)
    records = history.Library(tmp_path).device(DEVICE)["records"]
    assert not any(record[4] == "MISSING_SECTORS" for record in records)


class FakeDoc:
    def __init__(self, doc_id: str, data: dict):
        self.id, self._data = doc_id, data

    def get(self, field: str):
        return self._data[field]

    def to_dict(self) -> dict:
        return dict(self._data)


class FakeCollection:
    def __init__(self, docs: dict, children: dict | None = None):
        self.docs, self.children = docs, children or {}
        self.streams = 0

    def stream(self):
        self.streams += 1
        return [FakeDoc(doc_id, data) for doc_id, data in self.docs.items()]

    def document(self, doc_id: str):
        return self.children[doc_id]


class FakeDocument:
    def __init__(self, chunks: FakeCollection):
        self._chunks = chunks

    def collection(self, name: str) -> FakeCollection:
        assert name == "chunks"
        return self._chunks


class FakeFirestore:
    def __init__(self, devices: FakeCollection):
        self.devices = devices

    def collection(self, name: str) -> FakeCollection:
        assert name == "devices"
        return self.devices


def test_cloud_source_reads_chunks_as_one_history() -> None:
    import datetime as dt
    image = demo_image()
    sectors = devlog_fixture.devlog.sector_map(image)
    ordered = b"".join(sectors[sequence] for sequence in sorted(sectors))
    when = dt.datetime(2026, 11, 1, 12, tzinfo=dt.timezone.utc)
    half = (len(sectors) // 2) * devlog_fixture.devlog.SECTOR_SIZE
    chunks = FakeCollection({"001-0001": {"data": ordered[half:], "updated": when},
                             "001-0000": {"data": ordered[:half], "updated": when}})
    device_id = devlog_fixture.DEMO_DEVICE.hex()
    devices = FakeCollection({device_id: {"last_upload": when, "history": 1}},
                             {device_id: FakeDocument(chunks)})
    source = history.CloudSource("test")
    source._client = FakeFirestore(devices)
    library = history.Library(source)
    cloud = library.device(DEVICE)
    assert cloud["snapshots"][0]["file"] == f"cloud {device_id} history 1"
    assert len(cloud["records"]) == len(devlog_fixture.demo_story().entries)
    # Listed at most every LIST_INTERVAL_S unless forced; chunks only re-read after an upload.
    library.devices()
    assert devices.streams == 1 and chunks.streams == 1
    library.refresh(force=True)
    assert devices.streams == 2 and chunks.streams == 1


def test_http_api_picks_the_source(library: history.Library, tmp_path: pathlib.Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    cloud = history.Library(empty)
    httpd = server.http.server.ThreadingHTTPServer(("127.0.0.1", 0), server.handler_for(library, lambda: cloud))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        assert len(json.load(urllib.request.urlopen(base + "/api/devices?source=folder"))["devices"]) == 2
        assert json.load(urllib.request.urlopen(base + "/api/devices?source=cloud&reload=1"))["devices"] == []
    finally:
        httpd.shutdown()


def test_fleet_analytics() -> None:
    import datetime as dt
    import fleet
    day = 86400.0
    today = dt.date(2026, 11, 2)
    now = dt.datetime(2026, 11, 2, 12, tzinfo=dt.timezone.utc).timestamp()

    def boot(number, firmware, start, hours=1.0, abnormal=False):
        return {"boot": number, "firmware": firmware, "realStart": start, "timeKnown": True,
                "duration": hours * 3600, "abnormal": abnormal}

    def device(name, boots, telemetry=()):
        return {"summary": {"device": name}, "boots": boots, "relativeTime": False,
                "telemetry": [{"boot": b, "minFree": v} for b, v in telemetry]}

    old, new = now - 10 * day, now - 3 * day
    devices = [
        # Updated to 1.2.0 eight days ago; the reset reported by boot 3 happened on 1.2.0.
        device("A", [boot(1, "1.1.0", old, 10), boot(2, "1.2.0", now - 8 * day, 5),
                     boot(3, None, now - 3600, abnormal=True)], [(1, 9000), (1, 8000), (2, 12000), (3, 11000)]),
        device("B", [boot(1, "1.1.0", new, 2, abnormal=True)], [(1, 7000)]),
    ]
    stats = fleet.analytics(devices, {"A": ["2026-11-02", "2026-10-20"], "B": ["2026-10-31"]}, today, now)
    assert stats["uploads"]["windows"] == {"1": 1, "7": 2, "30": 2}
    assert stats["uploads"]["devices"][-1] == 1 and stats["uploads"]["devices"][-3] == 1
    assert stats["crashRate"] == [
        {"version": "1.1.0", "awakeHours": 12.0, "abnormal": 1, "per100h": 8.33},
        {"version": "1.2.0", "awakeHours": 6.0, "abnormal": 1, "per100h": 16.67}]
    assert stats["memory"] == [{"version": "1.1.0", "boots": 2, "p5": 7000},
                               {"version": "1.2.0", "boots": 2, "p5": 11000}]
    assert stats["recentAbnormal"] == ["A"]  # B's reset was three days ago
    # Panics lose the clock: C's undated reset follows a dated boot, so its
    # placement is a lower bound; D's precedes every dated boot.
    undated = [device("C", [boot(1, "1.1.0", now - 7200), {**boot(2, "1.1.0", now - 3000, abnormal=True), "timeKnown": False}]),
               device("D", [{**boot(1, "1.1.0", now - 7200, abnormal=True), "timeKnown": False}, boot(2, "1.1.0", now - 3600)])]
    assert fleet.analytics(undated, {}, today, now)["recentAbnormal"] == ["C"]
    adoption = stats["adoption"]
    assert adoption["versions"] == ["1.1.0", "1.2.0"]
    assert adoption["counts"][-12] == [0, 0] and adoption["counts"][-11] == [1, 0]  # A from its first boot
    assert adoption["counts"][-1] == [1, 1]  # A on 1.2.0, B on 1.1.0


def test_notes_are_kept_per_device(library: history.Library, tmp_path: pathlib.Path) -> None:
    import notes
    store = notes.Notes(tmp_path / "logs")
    httpd = server.http.server.ThreadingHTTPServer(("127.0.0.1", 0), server.handler_for(library, None, store))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}/api/notes?device={DEVICE}"

    def put(body) -> tuple[int, object]:
        request = urllib.request.Request(base, data=json.dumps(body).encode(), method="PUT",
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    try:
        assert json.load(urllib.request.urlopen(base)) == []
        # A range drawn right to left is stored left to right.
        status, saved = put([{"id": "a", "text": "speaker off", "start": {"boot": 3, "ms": 9000},
                              "end": {"boot": 2, "ms": 100}},
                             {"id": "b", "text": "bad cable", "start": {"boot": 4, "ms": 0}, "end": None}])
        assert status == 200
        assert saved[0]["start"] == {"boot": 2, "ms": 100} and saved[0]["end"] == {"boot": 3, "ms": 9000}
        assert json.load(urllib.request.urlopen(base)) == saved
        assert notes.Notes(tmp_path / "logs").get("other") == []
        assert put([{"id": "c", "text": " ", "start": {"boot": 1, "ms": 0}}])[0] == 400
        assert put([{"id": "c", "text": "x", "start": {"boot": "1", "ms": 0}}])[0] == 400
        assert json.load(urllib.request.urlopen(base)) == saved  # nothing changed
        assert put([]) == (200, [])
        assert json.loads((tmp_path / "logs" / notes.FILE).read_text()) == {}
    finally:
        httpd.shutdown()


def test_core_dumps_are_reassembled_served_and_decoded(library: history.Library, tmp_path: pathlib.Path) -> None:
    import gzip
    import io
    import subprocess
    import coredump
    expected = bytes(i % 251 for i in range(600))
    device = library.device(DEVICE)
    [core] = device["coreDumps"]
    crashed = next(boot for boot in device["boots"] if boot["boot"] == core["boot"] - 1)
    assert core["size"] == 600 and core["complete"] and core["firmware"] == crashed["firmware"]
    assert library.core(DEVICE, core["boot"]) == (expected, core["firmware"])
    assert library.core(DEVICE, 99) is None

    downloads, runs = [], []

    def fetch(request, timeout):
        downloads.append(request.full_url)
        assert request.headers["Authorization"] == "Bearer token"
        if "9.9.9" in request.full_url:
            raise urllib.error.HTTPError(request.full_url, 404, "not found", {}, None)
        return io.BytesIO(gzip.compress(b"\x7fELF fake"))

    def run(command, **kwargs):
        runs.append(command)
        assert pathlib.Path(command[-1]).read_bytes() == b"\x7fELF fake"
        assert pathlib.Path(command[command.index("--core") + 1]).read_bytes() == expected
        return subprocess.CompletedProcess(command, 0, "#0  0x400d2a10 in loop () at src/main.cpp:1\n", "")

    decoder = coredump.Decoder(lambda: "token", cache=tmp_path / "elfs", fetch=fetch, run=run)
    httpd = server.http.server.ThreadingHTTPServer(("127.0.0.1", 0), server.handler_for(library, None, None, decoder))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    query = f"?id={DEVICE}&boot={core['boot']}"
    try:
        assert urllib.request.urlopen(base + "/api/core" + query).read() == expected
        decoded = json.load(urllib.request.urlopen(base + "/api/core/decode" + query))
        assert decoded["text"].startswith("#0  0x400d2a10 in loop ()")
        json.load(urllib.request.urlopen(base + "/api/core/decode" + query))
        assert len(downloads) == 1 and len(runs) == 1  # the ELF is cached, and so is the report
        assert (tmp_path / "elfs/sweetyaar" / core["firmware"] / "firmware.elf").read_bytes() == b"\x7fELF fake"
        with pytest.raises(urllib.error.HTTPError) as missing:
            urllib.request.urlopen(base + f"/api/core?id={DEVICE}&boot=99")
        assert missing.value.code == 404
    finally:
        httpd.shutdown()
    with pytest.raises(coredump.DecodeError, match="No ELF of 9.9.9"):
        decoder.decode(expected, "9.9.9")
    with pytest.raises(coredump.DecodeError, match="does not say which firmware"):
        decoder.decode(expected, None)
