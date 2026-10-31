"""Merge fetched log snapshots into one history per device, for the viewer.

Every fetch is a full copy of the ring, so snapshots overlap. A record is
identified by its content: boot number, milliseconds since boot, event ID and
arguments (plus an occurrence count for identical records in the same
millisecond). The boot number lives in the log itself, so it survives power
loss, resets and flashing; it restarts only if the partition is erased.
"""

from __future__ import annotations

import collections
import dataclasses
import datetime as dt
import pathlib
import re
import sys
import threading

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import devlog  # noqa: E402

import decoders  # noqa: E402

AREAS = ["log", "main", "ble", "classic", "power", "playback", "ota"]
AREA_BY_HIGH_BYTE = dict(enumerate(AREAS))
ABNORMAL_RESETS = {"panic", "interrupt-watchdog", "task-watchdog", "watchdog", "brownout"}
SM_STATES = ["idle", "playing_song", "playing_animal", "bt_streaming", "killswitch"]
CHARGER_CHARGING = 4
UNKNOWN_TIME_GAP_S = 60     # placement of a boot whose wall time is unknown
AWAKE_GAP_S = 5             # visual gap between boots on the awake-time axis
FILE_TIME = re.compile(r"devlog-([0-9a-f]{12})-(\d{8}-\d{6})")
# Whole words only: argument names such as fail_reason= are not errors.
ERROR_WORDS = re.compile(r"\b(fail|failed|failure|error|crash|crashed|panic|corrupt|corrupted|out of memory|refused|"
                         r"mismatch)\b", re.I)
WARN_WORDS = re.compile(r"\b(warn|warning|invalid|ignored|ignoring|timeout|timed out|dropped|low|unavailable|aborted|"
                        r"lost|rollback|cannot)\b", re.I)


@dataclasses.dataclass
class Item:
    """One merged record; event_id, args, ms and truncated suit devlog's helpers."""
    boot: int
    ms: int
    event_id: int
    args: list
    truncated: bool
    order: tuple


@dataclasses.dataclass
class Snapshot:
    path: pathlib.Path
    device: str
    fetched: str
    records: int
    sectors: int
    sequence: tuple[int, int] | None
    problems: list[str]


def read_snapshot(path: pathlib.Path, catalog: devlog.Catalog) -> tuple[Snapshot, list[Item]]:
    log = devlog.read_log(path.read_bytes(), catalog)
    devices = collections.Counter(sector.device.hex(":").upper() for sector in log.sectors)
    device = devices.most_common(1)[0][0] if devices else "unknown"
    match = FILE_TIME.search(path.name)
    fetched = (dt.datetime.strptime(match.group(2), "%Y%m%d-%H%M%S") if match
               else dt.datetime.fromtimestamp(path.stat().st_mtime)).isoformat(timespec="seconds")
    seen: collections.Counter = collections.Counter()
    items = []
    for position, record in enumerate(log.records):
        key = (record.boot, record.ms, record.event_id, repr(record.args))
        seen[key] += 1
        items.append(Item(record.boot, record.ms, record.event_id, record.args, record.truncated,
                          (record.boot, record.ms, position, seen[key])))
    sequence = (log.sectors[0].sequence, log.sectors[-1].sequence) if log.sectors else None
    return Snapshot(path, device, fetched, len(items), len(log.sectors), sequence, log.problems), items


def merge(item_lists: list[list[Item]]) -> list[Item]:
    merged: dict[tuple, Item] = {}
    for items in item_lists:
        for item in items:
            key = (item.boot, item.ms, item.event_id, repr(item.args), item.order[3])
            merged.setdefault(key, item)
    return sorted(merged.values(), key=lambda item: item.order[:3])


def level_of(name: str, text: str, badges: list | None = None) -> str:
    if any(tone == "bad" for _, tone in badges or []):  # e.g. a BLE_AUTH with success=0
        return "error"
    if name in ("CRASH", "COREDUMP_BEGIN") or ERROR_WORDS.search(text) or text.startswith("[ERR"):
        return "error"
    if name in ("LOG_DROPPED", "LOG_SUPPRESSED") or WARN_WORDS.search(text) or text.startswith("[WARN"):
        return "warn"
    return "info"


def epoch(value: dt.datetime) -> float:
    return value.replace(tzinfo=dt.timezone.utc).timestamp()


class Library:
    """All snapshots in a folder, re-read when files change."""

    def __init__(self, directory: str | pathlib.Path, events: str | pathlib.Path = devlog.EVENTS_HEADER):
        self.directory = pathlib.Path(directory)
        self.events = pathlib.Path(events)
        self._cache: dict[pathlib.Path, tuple[tuple, Snapshot, list[Item]]] = {}
        self._devices: dict[str, dict] = {}
        self._signature: tuple = ()
        self._lock = threading.Lock()

    def refresh(self) -> None:
        with self._lock:
            self._refresh()

    def _refresh(self) -> None:
        catalog = devlog.load_catalog(self.events)
        paths = sorted(path for path in self.directory.glob("devlog-*.bin")
                       if not path.name.endswith(("-core.bin", "-coredump-partition.bin")))
        signature = tuple((path, path.stat().st_mtime, path.stat().st_size) for path in paths)
        signature += ((self.events, self.events.stat().st_mtime, 0),)
        if signature == self._signature:
            return
        self._signature = signature
        loaded = {}
        for path in paths:
            stamp = (path.stat().st_mtime, path.stat().st_size)
            cached = self._cache.get(path)
            loaded[path] = cached if cached and cached[0] == stamp else (stamp, *read_snapshot(path, catalog))
        self._cache = loaded
        by_device: dict[str, list] = collections.defaultdict(list)
        for _, snapshot, items in loaded.values():
            by_device[snapshot.device].append((snapshot, items))
        self._devices = {device: build_device(device, entries, catalog) for device, entries in by_device.items()}

    def devices(self) -> list[dict]:
        self.refresh()
        return [device["summary"] for device in sorted(self._devices.values(),
                                                       key=lambda device: device["summary"]["lastFetched"],
                                                       reverse=True)]

    def device(self, device_id: str) -> dict | None:
        self.refresh()
        return self._devices.get(device_id)

    def stats(self) -> dict:
        devices = self.devices()
        totals = collections.Counter()
        for summary in devices:
            for key in ("boots", "abnormalResets", "crashes", "awakeHours", "localHours", "btHours",
                        "songsStarted", "animalsStarted", "records"):
                totals[key] += summary[key]
        firmware = collections.Counter(summary["firmware"][-1] for summary in devices if summary["firmware"])
        return {"devices": devices, "totals": dict(totals), "firmware": dict(firmware),
                "directory": str(self.directory)}


def build_device(device: str, entries: list, catalog: devlog.Catalog) -> dict:
    entries.sort(key=lambda entry: entry[0].fetched)
    items = merge([items for _, items in entries])
    ids = {name: event_id for event_id, (name, _) in catalog.events.items()}

    # Boots and their wall-clock anchors.
    boots: dict[int, dict] = {}
    boot_items: dict[int, list[Item]] = collections.defaultdict(list)
    for item in items:
        boot_items[item.boot].append(item)
    tz = None
    for number, group in boot_items.items():
        times, tz = devlog.wall_times(group, catalog, tz)
        first = group[0]
        boot = {"boot": number, "startMs": first.ms, "endMs": group[-1].ms, "records": len(group),
                "startOverwritten": first.event_id != ids["BOOT"], "reset": None, "resetCode": None,
                "wake": None, "firmware": None, "slot": None, "streak": 0, "stable": False,
                "crash": None, "sleep": False, "timeKnown": any(times)}
        for item, wall in zip(group, times):
            item.wall = epoch(wall) if wall else None
        if not boot["startOverwritten"] and len(first.args) >= 8:
            boot.update(reset=first.args[2], resetCode=first.args[3], wake=first.args[4],
                        firmware=first.args[5], slot=first.args[7], streak=first.args[1])
        for item in group:
            name = catalog.name(item.event_id)
            if name == "BOOT_STABLE":
                boot["stable"] = True
            elif name == "SLEEP_ENTER":
                boot["sleep"] = True
            elif name == "CRASH" and item.args:
                boot["crash"] = {"task": item.args[0], "cause": item.args[1] if len(item.args) > 1 else None,
                                 "pc": item.args[2] if len(item.args) > 2 else None}
        boots[number] = boot

    # Real-time axis: anchored boots at their wall time, the others placed
    # after (or before) their neighbors. Awake axis: boots back to back.
    order = list(boots)
    for number in order:
        group, boot = boot_items[number], boots[number]
        anchored = next((item for item in group if item.wall is not None), None)
        boot["realStart"] = anchored.wall - (anchored.ms - boot["startMs"]) / 1000 if anchored else None
        boot["duration"] = max(0.001, (boot["endMs"] - boot["startMs"]) / 1000)
    known = [index for index, number in enumerate(order) if boots[order[index]]["realStart"] is not None]
    relative = not known
    if relative:
        position = 0.0
        for number in order:
            boots[number]["realStart"] = position
            position += boots[number]["duration"] + UNKNOWN_TIME_GAP_S
    else:
        for index in range(known[0] + 1, len(order)):
            boot = boots[order[index]]
            if boot["realStart"] is None:
                previous = boots[order[index - 1]]
                boot["realStart"] = previous["realStart"] + previous["duration"] + UNKNOWN_TIME_GAP_S
        for index in range(known[0] - 1, -1, -1):
            boot, following = boots[order[index]], boots[order[index + 1]]
            boot["realStart"] = following["realStart"] - UNKNOWN_TIME_GAP_S - boot["duration"]
    awake = 0.0
    for number in order:
        boot = boots[number]
        boot["awakeStart"] = awake
        awake += boot["duration"] + AWAKE_GAP_S

    def x(item_boot: int, ms: int) -> tuple[float, float]:
        boot = boots[item_boot]
        offset = (ms - boot["startMs"]) / 1000
        return round(boot["realStart"] + offset, 3), round(boot["awakeStart"] + offset, 3)

    # A crash is reported by the next boot; mark the boot that crashed.
    for index, number in enumerate(order):
        boot = boots[number]
        boot["abnormal"] = (boot["reset"] or "") in ABNORMAL_RESETS
        if boot["abnormal"] and index > 0:
            boots[order[index - 1]]["crashedInto"] = number

    records, telemetry, usage, intervals, repeats = [], [], [], [], []
    stored: dict[tuple, list] = {}  # (boot, event ID, ms) -> record, for REPEATED
    open_state: dict[int, tuple] = {}
    open_ble: dict[tuple, tuple] = {}
    open_bt: dict[int, tuple] = {}
    for index, item in enumerate(items):
        name = catalog.name(item.event_id)
        text = devlog.record_text(item, catalog)
        real, awake_x = x(item.boot, item.ms)
        area = AREA_BY_HIGH_BYTE.get(item.event_id >> 8, "log")
        badges = decoders.badges(name, item.args)
        level = level_of(name, text, badges)
        args = item.args
        if name == "REPEATED" and len(args) >= 4 and all(isinstance(arg, int) for arg in args[:4]):
            # Shown with the stored record it repeats: same area and level,
            # and a span from that record to the last repeat.
            original = stored.get((item.boot, args[0], args[1]))
            area = AREA_BY_HIGH_BYTE.get(args[0] >> 8, "log")
            level = original[6] if original else "warn"
            first_real, first_awake = x(item.boot, args[1])
            last_real, last_awake = x(item.boot, args[3])
            repeats.append({"area": area, "level": level, "x0": first_real, "x1": last_real,
                            "xa0": first_awake, "xa1": last_awake, "record": index})
        record = [real, awake_x, item.boot, item.ms, name, area, level, text, badges]
        records.append(record)
        stored[(item.boot, item.event_id, item.ms)] = record
        if name == "TELEMETRY" and len(args) >= 9:
            telemetry.append({"x": real, "xa": awake_x, "boot": item.boot, "battery": args[0] or None,
                              "batteryState": args[1], "charger": args[2], "conditions": args[3],
                              "activity": args[4], "volume": args[5], "free": args[6], "largest": args[7],
                              "minFree": args[8]})
        elif name == "USAGE" and len(args) >= 9:
            usage.append({"x": real, "xa": awake_x, "boot": item.boot, "interval": args[0], "songButton": args[1],
                          "animalButton": args[2], "bothButtons": args[3], "songs": args[4], "animals": args[5],
                          "localSeconds": args[6], "btSeconds": args[7], "appControls": args[8]})
        elif name == "SM_TRANSITION" and len(args) >= 2:
            close(intervals, open_state.pop(item.boot, None), real, awake_x)
            state = SM_STATES[args[1]] if args[1] < len(SM_STATES) else f"state{args[1]}"
            if state != "idle":
                open_state[item.boot] = ("state", state, real, awake_x, index)
        elif name == "BLE_CONNECT" and args:
            open_ble[(item.boot, args[0])] = ("ble", "BLE app", real, awake_x, index)
        elif name == "BLE_DISCONNECT" and args:
            close(intervals, open_ble.pop((item.boot, args[0]), None), real, awake_x)
        elif name == "BT_CONNECTED":
            open_bt[item.boot] = ("classic", "Classic BT", real, awake_x, index)
        elif name == "BT_DISCONNECTED":
            close(intervals, open_bt.pop(item.boot, None), real, awake_x)
    for pending in (open_state, open_ble, open_bt):
        for key, interval in pending.items():
            boot = boots[key[0] if isinstance(key, tuple) else key]
            end_real, end_awake = x(boot["boot"], boot["endMs"])
            close(intervals, interval, end_real, end_awake)

    playing = [interval for interval in intervals if interval["lane"] == "state"
               and interval["kind"] in ("playing_song", "playing_animal", "bt_streaming")]
    drain = battery_drain(telemetry, playing)
    summary = summarize(device, entries, boots, order, items, playing, drain, records, catalog)
    return {"summary": summary, "relativeTime": relative,
            "boots": [boots[number] for number in order], "records": records, "telemetry": telemetry,
            "usage": usage, "intervals": intervals, "repeats": repeats, "areas": AREAS,
            "snapshots": [snapshot_json(snapshot) for snapshot, _ in entries]}


def close(intervals: list, interval: tuple | None, real: float, awake: float) -> None:
    if interval is None:
        return
    lane, kind, start_real, start_awake, index = interval
    intervals.append({"lane": lane, "kind": kind, "x0": start_real, "x1": real,
                      "xa0": start_awake, "xa1": awake, "record": index})


def battery_drain(telemetry: list[dict], playing: list[dict]) -> dict:
    """mV per hour between telemetry samples of one boot while not charging,
    split by how much of the interval was spent playing."""
    totals = {"playing": [0.0, 0.0], "idle": [0.0, 0.0]}  # mV dropped, hours
    for first, second in zip(telemetry, telemetry[1:]):
        if first["boot"] != second["boot"] or not first["battery"] or not second["battery"]:
            continue
        if CHARGER_CHARGING in (first["charger"], second["charger"]):
            continue
        hours = (second["xa"] - first["xa"]) / 3600
        if hours < 0.05:
            continue
        busy = sum(max(0.0, min(second["xa"], interval["xa1"]) - max(first["xa"], interval["xa0"]))
                   for interval in playing) / 3600
        share = busy / hours
        if share >= 0.8 or share <= 0.2:
            bucket = totals["playing" if share >= 0.8 else "idle"]
            bucket[0] += first["battery"] - second["battery"]
            bucket[1] += hours
    return {kind: {"mvPerHour": round(dropped / hours, 1) if hours else None, "hours": round(hours, 2)}
            for kind, (dropped, hours) in totals.items()}


NAME_EVENTS = ("DEVICE_NAME", "BT_NAME_SET", "BLE_NAME_SET")


def summarize(device: str, entries: list, boots: dict, order: list, items: list, playing: list,
              drain: dict, records: list, catalog) -> dict:
    firmware = []
    for number in order:
        version = boots[number]["firmware"]
        if version and (not firmware or firmware[-1] != version):
            firmware.append(version)
    # An installation changes the version or, for an update over BLE, the app
    # slot (so a reinstall of the same version counts). A wired flash of the
    # same version into the same slot cannot be told apart.
    builds = [(boots[number]["firmware"], boots[number]["slot"]) for number in order if boots[number]["firmware"]]
    installs = sum(1 for previous, current in zip(builds, builds[1:]) if previous != current)
    known = [boots[number]["realStart"] for number in order if boots[number]["timeKnown"]]
    # Stored at cold boots (DEVICE_NAME) and when renamed; the newest wins.
    name = next((item.args[0] for record, item in zip(reversed(records), reversed(items))
                 if record[4] in NAME_EVENTS and item.args), None)
    # From the playback records themselves, not USAGE: USAGE is stored hourly
    # and at deep sleep, so a boot that ends otherwise (power cut, flashing, a
    # fetch, a restart) loses its counters.
    def seconds(*kinds: str) -> float:
        return sum(interval["xa1"] - interval["xa0"] for interval in playing if interval["kind"] in kinds)
    played = [str(item.args[0]) for item in items
              if item.args and catalog.name(item.event_id) == "WAV_PLAYING"]
    return {
        "device": device,
        "name": name,
        "snapshots": len(entries),
        "lastFetched": entries[-1][0].fetched,
        "boots": len(order),
        "firstBoot": order[0] if order else None,
        "lastBoot": order[-1] if order else None,
        "abnormalResets": sum(1 for number in order if boots[number]["abnormal"]),
        "crashes": sum(1 for number in order if boots[number]["crash"]),
        "awakeHours": round(sum(boots[number]["duration"] for number in order) / 3600, 2),
        "localHours": round(seconds("playing_song", "playing_animal") / 3600, 2),
        "btHours": round(seconds("bt_streaming") / 3600, 2),
        "songsStarted": sum(1 for path in played if path.startswith("/songs/")),
        "animalsStarted": sum(1 for path in played if path.startswith("/animals/")),
        "records": len(records),
        "firmware": firmware,
        "installs": installs,
        "firstTime": min(known) if known else None,
        "lastTime": max(known) if known else None,
        "drain": drain,
        "warnings": sum(1 for record in records if record[6] == "warn"),
        "errors": sum(1 for record in records if record[6] == "error"),
    }


def snapshot_json(snapshot: Snapshot) -> dict:
    return {"file": snapshot.path.name, "fetched": snapshot.fetched, "records": snapshot.records,
            "sectors": snapshot.sectors, "sequence": snapshot.sequence, "problems": snapshot.problems}
