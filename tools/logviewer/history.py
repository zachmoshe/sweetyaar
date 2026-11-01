"""Merge fetched log snapshots into one history per device, for the viewer.

Snapshots come from a source: the devlog files in a folder (FolderSource), or
the uploads the parent app sent to the logs API (CloudSource, Firestore).
Snapshots of one device can overlap. A record is
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
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import devlog  # noqa: E402

import decoders  # noqa: E402
import fleet  # noqa: E402

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
    sequence: int = 0  # of the sector that holds it


@dataclasses.dataclass
class Snapshot:
    name: str  # the file, or the cloud history
    device: str
    fetched: str
    records: int
    sectors: int
    sequence: tuple[int, int] | None
    problems: list[str]


def read_snapshot(path: pathlib.Path, catalog: devlog.Catalog) -> tuple[Snapshot, list[Item]]:
    match = FILE_TIME.search(path.name)
    fetched = (dt.datetime.strptime(match.group(2), "%Y%m%d-%H%M%S") if match
               else dt.datetime.fromtimestamp(path.stat().st_mtime)).isoformat(timespec="seconds")
    return read_snapshot_data(path.name, path.read_bytes(), fetched, catalog)


def read_snapshot_data(name: str, data: bytes, fetched: str,
                       catalog: devlog.Catalog) -> tuple[Snapshot, list[Item]]:
    log = devlog.read_log(data, catalog)
    devices = collections.Counter(sector.device.hex(":").upper() for sector in log.sectors)
    device = devices.most_common(1)[0][0] if devices else "unknown"
    seen: collections.Counter = collections.Counter()
    items = []
    for position, record in enumerate(log.records):
        key = (record.boot, record.ms, record.event_id, repr(record.args))
        seen[key] += 1
        items.append(Item(record.boot, record.ms, record.event_id, record.args, record.truncated,
                          (record.boot, record.ms, position, seen[key]), record.sector.sequence))
    sequence = (log.sectors[0].sequence, log.sectors[-1].sequence) if log.sectors else None
    return Snapshot(name, device, fetched, len(items), len(log.sectors), sequence, log.problems), items


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


class FolderSource:
    """The devlog files in a folder; a file is read again when it changes."""

    def __init__(self, directory: str | pathlib.Path):
        self.directory = pathlib.Path(directory)
        self.label = str(self.directory)

    def listing(self, force: bool = False) -> dict:
        paths = sorted(path for path in self.directory.glob("devlog-*.bin")
                       if not path.name.endswith(("-core.bin", "-coredump-partition.bin")))
        return {path: (path.stat().st_mtime, path.stat().st_size) for path in paths}

    def read(self, path: pathlib.Path, catalog: devlog.Catalog) -> list:
        return [read_snapshot(path, catalog)]

    def upload_days(self, devices: list[dict]) -> dict[str, list[str]]:
        """The days each device was fetched, local time."""
        return {data["summary"]["device"]: sorted({snap["fetched"][:10] for snap in data["snapshots"]})
                for data in devices}


class CloudSource:
    """What the parent app uploaded to the logs API: Firestore, read-only.

    Reads as the logs-viewer service account, with tokens from the gcloud
    CLI's login; application-default credentials are not used (see "Sending
    logs to the cloud" in docs/logging-and-debugging.md). A toy's chunks are read
    again only when its last upload changed; the list of toys at most every
    LIST_INTERVAL_S seconds unless Reload asks.
    """

    LIST_INTERVAL_S = 30
    TOKEN_LIFETIME = dt.timedelta(minutes=50)  # gcloud's tokens last an hour

    def __init__(self, project: str):
        self.project = project
        self.viewer = f"logs-viewer@{project}.iam.gserviceaccount.com"
        self.label = f"Cloud: Firestore in {project}"
        self._client = None
        self._listing: dict = {}
        self._days: dict[str, list[str]] = {}
        self._listed_at = float("-inf")

    def token(self, request=None, scopes=None) -> tuple[str, dt.datetime]:
        """A logs-viewer access token and its expiry (naive UTC), from gcloud."""
        result = subprocess.run(["gcloud", "auth", "print-access-token",
                                 f"--impersonate-service-account={self.viewer}"],
                                capture_output=True, text=True, timeout=60)
        lines = result.stdout.split()
        if result.returncode or not lines:
            reason = (result.stderr.strip().splitlines() or ["no output"])[-1]
            raise RuntimeError(f"gcloud could not get a {self.viewer} token: {reason}")
        return lines[-1], dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) + self.TOKEN_LIFETIME

    def client(self):
        if self._client is None:
            # Only the cloud source needs these.
            from google.cloud import firestore
            from google.oauth2 import credentials
            self._client = firestore.Client(project=self.project, credentials=credentials.Credentials(
                token=None, refresh_handler=self.token))
        return self._client

    def listing(self, force: bool = False) -> dict:
        if force or time.monotonic() - self._listed_at >= self.LIST_INTERVAL_S:
            docs = [doc.to_dict() | {"id": doc.id} for doc in self.client().collection("devices").stream()]
            self._listing = {doc["id"]: (str(doc.get("last_upload")), doc.get("history")) for doc in docs}
            # UTC days. Documents from before the API recorded them have only
            # their first and last upload.
            self._days = {doc["id"]: doc.get("upload_days") or sorted(
                {when.date().isoformat() for when in (doc.get("first_upload"), doc.get("last_upload")) if when})
                for doc in docs}
            self._listed_at = time.monotonic()
        return self._listing

    def upload_days(self, devices: list[dict]) -> dict[str, list[str]]:
        """The days each toy uploaded (UTC), by the viewer's device ID."""
        return {":".join(device[i:i + 2] for i in range(0, 12, 2)).upper(): days
                for device, days in self._days.items()}

    def read(self, device: str, catalog: devlog.Catalog) -> list:
        """One snapshot per history: its chunks joined are a devlog file."""
        histories: dict[str, list] = collections.defaultdict(list)
        chunks = self.client().collection("devices").document(device).collection("chunks").stream()
        for chunk in sorted(chunks, key=lambda chunk: chunk.id):
            histories[chunk.id.split("-")[0]].append(chunk.to_dict())
        snapshots = []
        for number, parts in sorted(histories.items()):
            updated = max(part["updated"] for part in parts)
            fetched = updated.astimezone().replace(tzinfo=None).isoformat(timespec="seconds")
            data = b"".join(part["data"] for part in parts)
            snapshots.append(read_snapshot_data(f"cloud {device} history {int(number)}", data, fetched, catalog))
        return snapshots


class Library:
    """All snapshots of a source, merged per device and re-read when they change."""

    def __init__(self, source: str | pathlib.Path | FolderSource | CloudSource,
                 events: str | pathlib.Path = devlog.EVENTS_HEADER):
        self.source = source if isinstance(source, (FolderSource, CloudSource)) else FolderSource(source)
        self.directory = self.source.label
        self.events = pathlib.Path(events)
        self._cache: dict = {}
        self._devices: dict[str, dict] = {}
        self._cores: dict[str, dict[int, bytes]] = {}
        self._signature: tuple = ()
        self._lock = threading.Lock()

    def refresh(self, force: bool = False) -> None:
        with self._lock:
            self._refresh(force)

    def _refresh(self, force: bool) -> None:
        catalog = devlog.load_catalog(self.events)
        listing = self.source.listing(force)
        signature = tuple(sorted(listing.items(), key=lambda item: str(item[0])))
        signature += ((self.events, self.events.stat().st_mtime, 0),)
        if signature == self._signature:
            return
        self._signature = signature
        loaded = {}
        for key, stamp in listing.items():
            cached = self._cache.get(key)
            loaded[key] = cached if cached and cached[0] == stamp else (stamp, self.source.read(key, catalog))
        self._cache = loaded
        by_device: dict[str, list] = collections.defaultdict(list)
        for _, snapshots in loaded.values():
            for snapshot, items in snapshots:
                by_device[snapshot.device].append((snapshot, items))
        self._devices = {device: build_device(device, entries, catalog) for device, entries in by_device.items()}
        self._cores = {device: data.pop("coreData") for device, data in self._devices.items()}

    def devices(self) -> list[dict]:
        self.refresh()
        return [device["summary"] for device in sorted(self._devices.values(),
                                                       key=lambda device: device["summary"]["lastFetched"],
                                                       reverse=True)]

    def device(self, device_id: str) -> dict | None:
        self.refresh()
        return self._devices.get(device_id)

    def core(self, device_id: str, boot: int) -> tuple[bytes, str | None] | None:
        """A complete core dump copied at |boot| and the firmware that crashed."""
        self.refresh()
        data = self._cores.get(device_id, {}).get(boot)
        if data is None:
            return None
        info = next(core for core in self._devices[device_id]["coreDumps"] if core["boot"] == boot)
        return data, info["firmware"]

    def stats(self) -> dict:
        devices = self.devices()
        firmware = collections.Counter(summary["firmware"][-1] for summary in devices if summary["firmware"])
        datas = [self._devices[summary["device"]] for summary in devices]
        now = dt.datetime.now()
        fleet_stats = fleet.analytics(datas, self.source.upload_days(datas), now.date(), epoch(now))
        return {"devices": devices, "firmware": dict(firmware), "fleet": fleet_stats,
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

    # Sectors missing between those kept (overwritten on the toy before they
    # were fetched or uploaded): a marker where the log resumes.
    kept = sorted({item.sequence for item in items})
    missing_before = {after: after - before - 1 for before, after in zip(kept, kept[1:]) if after - before > 1}

    records, telemetry, usage, intervals, repeats = [], [], [], [], []
    stored: dict[tuple, list] = {}  # (boot, event ID, ms) -> record, for REPEATED
    open_state: dict[int, tuple] = {}
    open_ble: dict[tuple, tuple] = {}
    open_bt: dict[int, tuple] = {}
    for item in items:
        name = catalog.name(item.event_id)
        text = devlog.record_text(item, catalog)
        real, awake_x = x(item.boot, item.ms)
        missing = missing_before.pop(item.sequence, 0)
        if missing:
            records.append([real, awake_x, item.boot, item.ms, "MISSING_SECTORS", "log", "warn",
                            f"[Log] Missing {missing} sector{'s' if missing > 1 else ''} here; "
                            "the log before this point is not continuous", []])
        index = len(records)
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
    cores = core_dumps(items, catalog)
    versions = dict(zip(order, fleet.boot_versions([boots[number] for number in order])))
    previous = dict(zip(order[1:], order))
    return {"summary": summary, "relativeTime": relative,
            # The dump is copied at the boot after the crash: the firmware that
            # crashed is the one the boot before ran.
            "coreDumps": [{"boot": boot, "size": core["size"], "complete": core["received"] == core["size"],
                           "firmware": versions.get(previous.get(boot, boot))}
                          for boot, core in cores.items()],
            "coreData": {boot: bytes(core["data"]) for boot, core in cores.items()
                         if core["received"] == core["size"]},
            "boots": [boots[number] for number in order], "records": records, "telemetry": telemetry,
            "usage": usage, "intervals": intervals, "repeats": repeats, "areas": AREAS,
            "snapshots": [snapshot_json(snapshot) for snapshot, _ in entries]}


def core_dumps(items: list, catalog) -> dict[int, dict]:
    """The core dumps copied into the log (COREDUMP_BEGIN, _CHUNK, _END), by boot."""
    cores: dict[int, dict] = {}
    for item in items:
        name = catalog.name(item.event_id)
        if name == "COREDUMP_BEGIN" and item.args:
            cores[item.boot] = {"size": item.args[0], "data": bytearray(item.args[0]), "received": 0}
        elif name == "COREDUMP_CHUNK" and item.boot in cores and len(item.args) >= 2:
            core, (offset, chunk) = cores[item.boot], item.args[:2]
            if isinstance(chunk, bytes) and offset + len(chunk) <= core["size"]:
                core["data"][offset:offset + len(chunk)] = chunk
                core["received"] += len(chunk)
    return cores


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
    name = next((item.args[0] for item in reversed(items)
                 if catalog.name(item.event_id) in NAME_EVENTS and item.args), None)
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
        "lastSector": max((item.sequence for item in items), default=None),  # the newest sector's sequence
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
    return {"file": snapshot.name, "fetched": snapshot.fetched, "records": snapshot.records,
            "sectors": snapshot.sectors, "sequence": snapshot.sequence, "problems": snapshot.problems}
