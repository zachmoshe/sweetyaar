"""Fleet analytics for the viewer's All devices panel.

Built from every device's merged history (history.build_device) and the days
it uploaded (or, for the log folder, was fetched). Wall times are the toy's
local time stored as if UTC, as everywhere in the viewer; boots whose time is
unknown are left out of anything dated.
"""

from __future__ import annotations

import collections
import datetime as dt
import math
import re

WINDOW_DAYS = 30               # upload and adoption charts
RECENT_PROBLEM_S = 48 * 3600   # abnormal reset marked on the device's row
LATEST_VERSIONS = 5            # crash rate and memory charts


def version_key(version: str) -> tuple:
    return tuple(int(number) for number in re.findall(r"\d+", version or ""))


def boot_versions(boots: list[dict]) -> list[str | None]:
    """Each boot's firmware; a boot whose BOOT record was overwritten takes the
    version around it."""
    known = [boot["firmware"] for boot in boots]
    first = next((version for version in known if version), None)
    result, current = [], first
    for version in known:
        current = version or current
        result.append(current)
    return result


def boot_date(boot: dict, relative: bool) -> dt.date | None:
    if relative or not boot.get("timeKnown") or boot.get("realStart") is None:
        return None
    return dt.datetime.fromtimestamp(boot["realStart"], dt.timezone.utc).date()


def percentile(values: list[float], share: float) -> float:
    """Nearest rank: the smallest value with at least |share| of them at or below it."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(share * len(ordered)) - 1)]


def analytics(devices: list[dict], upload_days: dict[str, list[str]], today: dt.date, now: float) -> dict:
    """|devices|: build_device results; |upload_days|: device -> ISO dates;
    |now|: local wall time as if UTC, in seconds."""
    days = [today - dt.timedelta(days=offset) for offset in range(WINDOW_DAYS - 1, -1, -1)]
    awake: dict[str, float] = collections.Counter()
    abnormal: dict[str, int] = collections.Counter()
    low_water: dict[str, list[int]] = collections.defaultdict(list)
    dated: dict[str, list[tuple[dt.date, str]]] = {}
    recent = []
    for data in devices:
        device = data["summary"]["device"]
        boots = data["boots"]
        versions = boot_versions(boots)
        by_boot = dict(zip((boot["boot"] for boot in boots), versions))
        first_dated = next((index for index, boot in enumerate(boots) if boot.get("timeKnown")), None)
        for index, (boot, version) in enumerate(zip(boots, versions)):
            if version:
                awake[version] += boot["duration"] / 3600
            if boot["abnormal"]:
                # The version that was running when it reset: the boot before.
                crashed = versions[index - 1] if index else version
                if crashed:
                    abnormal[crashed] += 1
                # A panic loses the clock. An undated boot after a dated one is
                # placed right after its predecessor, so its time is a lower
                # bound: within the window means certainly recent.
                start = boot.get("realStart")
                if (not data["relativeTime"] and start is not None and first_dated is not None
                        and index >= first_dated and now - start <= RECENT_PROBLEM_S):
                    recent.append(device)
        lowest: dict[int, int] = {}
        for point in data["telemetry"]:
            if point["minFree"]:
                lowest[point["boot"]] = min(point["minFree"], lowest.get(point["boot"], point["minFree"]))
        for boot, value in lowest.items():
            if by_boot.get(boot):
                low_water[by_boot[boot]].append(value)
        dated[device] = sorted(((day, version) for boot, version in zip(boots, versions)
                                if version and (day := boot_date(boot, data["relativeTime"]))),
                               key=lambda run: run[0])  # stable: boot order within a day

    seen = {device: {dt.date.fromisoformat(day) for day in dates} for device, dates in upload_days.items()}
    uploads = {
        "days": [day.isoformat() for day in days],
        "devices": [sum(1 for dates in seen.values() if day in dates) for day in days],
        "windows": {str(span): sum(1 for dates in seen.values()
                                   if any(today - dt.timedelta(days=span - 1) <= day <= today for day in dates))
                    for span in (1, 7, 30)},
    }

    latest = sorted(set(awake) | set(abnormal), key=version_key)[-LATEST_VERSIONS:]
    crash_rate = [{"version": version, "awakeHours": round(awake[version], 1), "abnormal": abnormal[version],
                   "per100h": round(abnormal[version] / awake[version] * 100, 2) if awake[version] else None}
                  for version in latest]
    memory = [{"version": version, "boots": len(low_water[version]),
               "p5": percentile(low_water[version], 0.05)}
              for version in sorted(low_water, key=version_key)[-LATEST_VERSIONS:]]

    # A device counts from its first dated boot, on the version it ran last
    # that day or before.
    adoption_versions = sorted({version for runs in dated.values() for _, version in runs}, key=version_key)
    adoption = []
    for day in days:
        counts = collections.Counter()
        for runs in dated.values():
            current = None
            for run_day, version in runs:
                if run_day > day:
                    break
                current = version
            if current:
                counts[current] += 1
        adoption.append([counts[version] for version in adoption_versions])
    return {"uploads": uploads, "crashRate": crash_rate, "memory": memory,
            "adoption": {"days": uploads["days"], "versions": adoption_versions, "counts": adoption},
            "recentAbnormal": sorted(set(recent))}
