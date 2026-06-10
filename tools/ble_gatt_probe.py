#!/usr/bin/env python3
import argparse
import asyncio
import json
from datetime import datetime
from typing import Any

from bleak import BleakClient, BleakScanner

VOLUME_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567891"
KILLSWITCH_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567892"
THEME_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567893"
STATUS_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567894"
CONFIG_COMMAND_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567897"
CONFIG_RESPONSE_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567898"
COMMAND_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567896"
THEMES_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567895"


def find_characteristic(services: Any, uuid: str) -> bool:
    target = uuid.lower()
    for service in services:
        for characteristic in service.characteristics:
            if characteristic.uuid.lower() == target:
                return True
    return False


def preview(text: str, limit: int = 220) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def local_time_payload() -> dict[str, int]:
    now = datetime.now().astimezone()
    offset = now.utcoffset()
    return {
        "epochSec": int(now.timestamp()),
        "tzOffsetMin": int(offset.total_seconds() // 60) if offset else 0,
    }


def _epoch_for_local_minute(minute_of_day: int, tz_offset_min: int) -> dict[str, int]:
    """Return a syncTime payload whose local time-of-day is exactly minute_of_day."""
    from datetime import timezone, timedelta
    tz = timezone(timedelta(minutes=tz_offset_min))
    local_midnight = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    target = local_midnight + timedelta(minutes=minute_of_day)
    return {"epochSec": int(target.timestamp()), "tzOffsetMin": tz_offset_min}


def _pick_inside_outside_minutes(start_minutes: int, end_minutes: int) -> tuple[int, int]:
    """Return (inside_minute, outside_minute) for a bedtime window."""
    day = 24 * 60
    inside = (start_minutes + 30) % day
    if start_minutes > end_minutes:  # crosses midnight
        gap = start_minutes - end_minutes
        outside = (end_minutes + gap // 2) % day
    else:
        gap = day - end_minutes + start_minutes
        outside = (end_minutes + gap // 2) % day
    return inside, outside


async def write_json(client: BleakClient, char_uuid: str, payload: dict[str, Any]) -> None:
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    try:
        await client.write_gatt_char(char_uuid, data, response=True)
    except Exception:
        await client.write_gatt_char(char_uuid, data, response=False)


async def write_bytes(client: BleakClient, char_uuid: str, data: bytes) -> None:
    try:
        await client.write_gatt_char(char_uuid, data, response=True)
    except Exception:
        await client.write_gatt_char(char_uuid, data, response=False)


async def config_request(
    client: BleakClient,
    request: dict[str, Any],
    command_uuid: str,
    response_uuid: str,
    timeout: float,
) -> dict[str, Any]:
    request_id = request["id"]
    await write_json(client, command_uuid, request)

    deadline = asyncio.get_running_loop().time() + timeout
    last_text = ""
    last_parse_error = ""
    stale = []

    while asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.1)
        raw = await client.read_gatt_char(response_uuid)
        text = raw.decode("utf-8", errors="replace")
        last_text = text
        try:
            response = json.loads(text or "{}")
        except json.JSONDecodeError as exc:
            last_parse_error = str(exc)
            continue

        if not isinstance(response, dict):
            stale.append(f"non-object:{type(response).__name__}")
            continue
        if response.get("id") != request_id:
            stale.append(f"id={response.get('id')}")
            continue
        if not response.get("ok", False):
            raise RuntimeError(f"{request['op']} rejected: {response.get('error', 'unknown error')}")
        return response

    print(f"Timed out waiting for {request['op']} id={request_id}")
    print(f"  last response length: {len(last_text)}")
    print(f"  last parse error: {last_parse_error or '-'}")
    print(f"  stale responses: {', '.join(stale[-8:]) if stale else '-'}")
    print(f"  last response preview: {preview(last_text)!r}")
    raise TimeoutError(request["op"])


async def run_config_api_suite(
    client: BleakClient,
    command_uuid: str,
    response_uuid: str,
    timeout: float,
    theme: str | None,
    start_id: int = 1,
) -> int:
    next_id = start_id

    async def request(op: str, **extra: Any) -> dict[str, Any]:
        nonlocal next_id
        payload = {"id": next_id, "op": op, **extra}
        next_id += 1
        print(f"\n-> {op} {extra if extra else ''}")
        response = await config_request(client, payload, command_uuid, response_uuid, timeout)
        compact = json.dumps(response, separators=(",", ":"), sort_keys=True)
        print(f"<- {op} ok, {len(compact)} bytes")
        print(preview(compact, 500))
        return response

    config = await request("getConfig")
    print(f"Device: {config.get('deviceName')} defaultTheme={config.get('defaultTheme')}")
    synced = await request("syncTime", **local_time_payload())
    bedtime = synced.get("bedtime") if isinstance(synced.get("bedtime"), dict) else {}
    if bedtime.get("timeKnown") is not True:
        raise RuntimeError("syncTime did not mark bedtime timeKnown=true")
    if bedtime.get("enabled") is not False:
        runtime_on = await request("setBedtimeMode", active=True)
        bedtime_on = runtime_on.get("bedtime") if isinstance(runtime_on.get("bedtime"), dict) else {}
        if bedtime_on.get("active") is not True:
            raise RuntimeError("setBedtimeMode active=true did not enable runtime bedtime mode")
        await request("setBedtimeMode", active=False)

    themes: list[dict[str, Any]] = []
    for page in range(40):
        response = await request("scanThemes", page=page)
        page_themes = response.get("themes", [])
        if not isinstance(page_themes, list):
            raise RuntimeError("scanThemes returned non-list themes")
        themes.extend(item for item in page_themes if isinstance(item, dict))
        if not response.get("hasMore", False):
            break
    else:
        raise RuntimeError("scanThemes did not finish within 40 pages")

    print(f"\nThemes discovered: {len(themes)}")
    for item in themes:
        print(
            f"  {item.get('id')} enabled={item.get('enabled')} "
            f"activeValid={item.get('activeValid')} total={item.get('total')} "
            f"errors={item.get('errors')}"
        )

    selected_theme = theme or next((item.get("id") for item in themes if item.get("id")), None)
    if not selected_theme:
        print("No theme to scan songs for.")
        return 0

    songs = []
    for page in range(80):
        response = await request("scanSongs", theme=selected_theme, page=page)
        page_songs = response.get("songs", [])
        if not isinstance(page_songs, list):
            raise RuntimeError("scanSongs returned non-list songs")
        songs.extend(item for item in page_songs if isinstance(item, dict))
        if not response.get("hasMore", False):
            break
    else:
        raise RuntimeError("scanSongs did not finish within 80 pages")

    print(f"\nSongs discovered for {selected_theme}: {len(songs)}")
    for item in songs[:12]:
        print(
            f"  {item.get('file')} enabled={item.get('enabled')} ok={item.get('ok')} "
            f"size={item.get('sizeBytes')} durationMs={item.get('durationMs')} "
            f"error={item.get('error', '')}"
        )
    if len(songs) > 12:
        print(f"  ... {len(songs) - 12} more")
    return 0


async def run_ble_control_smoke(client: BleakClient) -> int:
    print("\nBLE control smoke:")

    raw_volume = await client.read_gatt_char(VOLUME_UUID)
    volume = raw_volume[0] if raw_volume else 0
    await write_bytes(client, VOLUME_UUID, bytes([volume]))
    print(f"  volume read/write ok: {volume}")

    raw_kill = await client.read_gatt_char(KILLSWITCH_UUID)
    killswitch = raw_kill[0] if raw_kill else 0
    await write_bytes(client, KILLSWITCH_UUID, bytes([killswitch]))
    print(f"  killswitch read/write ok: {killswitch}")

    raw_theme = await client.read_gatt_char(THEME_UUID)
    theme = raw_theme.decode("utf-8", errors="replace")
    if theme:
        await write_bytes(client, THEME_UUID, theme.encode("utf-8"))
        print(f"  theme read/write ok: {theme}")
    else:
        print("  theme is empty; skipped write")

    raw_status = await client.read_gatt_char(STATUS_UUID)
    status = raw_status.decode("utf-8", errors="replace")
    print(f"  status read ok: {status or '<empty>'}")
    return 0


def sleep_from_config(config: dict[str, Any]) -> dict[str, Any]:
    sleep = config.get("sleep") if isinstance(config.get("sleep"), dict) else {}
    return {
        "enabled": sleep.get("enabled") is not False,
        "normalIdleSec": int(sleep.get("normalIdleSec") or 600),
        "vibrationWakeIdleSec": int(sleep.get("vibrationWakeIdleSec") or 120),
        "bleIdleSec": int(sleep.get("bleIdleSec") or 120),
    }


def bedtime_from_config(config: dict[str, Any]) -> dict[str, Any]:
    bedtime = config.get("bedtime") if isinstance(config.get("bedtime"), dict) else {}
    return {
        "enabled": bedtime.get("enabled") is not False,
        "startTime": str(bedtime.get("startTime") or "18:30"),
        "endTime": str(bedtime.get("endTime") or "06:30"),
        "theme": str(bedtime.get("theme") or "lullabies"),
        "volumeCapPct": int(bedtime.get("volumeCapPct") if bedtime.get("volumeCapPct") is not None else 45),
    }


def writable_config_from_response(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "deviceName": str(config.get("deviceName") or "SweetYaar"),
        "defaultVolumePct": int(config.get("defaultVolumePct") or 75),
        "defaultTheme": str(config.get("defaultTheme") or "lullabies"),
        "sleep": sleep_from_config(config),
        "bedtime": bedtime_from_config(config),
    }


def probe_seconds(current: int, floor: int) -> int:
    if current < 24 * 60 * 60:
        return max(floor, current + 1)
    return max(floor, current - 1)


def assert_config_matches(label: str, response: dict[str, Any], expected: dict[str, Any]) -> None:
    actual = writable_config_from_response(response)
    if actual != expected:
        raise RuntimeError(f"{label} config mismatch: expected {expected}, got {actual}")


def choose_probe_device_name(original: str) -> str:
    candidate = "SweetYaar Pytest"
    if original != candidate:
        return candidate
    return "SweetYaar Pytest 2"


def choose_probe_volume(original: int) -> int:
    return 42 if original != 42 else 43


def choose_probe_theme(original: str, themes: list[dict[str, Any]]) -> str:
    candidates = [
        str(theme.get("id") or "")
        for theme in themes
        if theme.get("canSetDefault", True) is not False
        and theme.get("enabled", False)
        and int(theme.get("activeValid") or 0) > 0
        and theme.get("id")
    ]
    for candidate in candidates:
        if candidate != original:
            return candidate
    return candidates[0] if candidates else original


def choose_probe_time(original: str, preferred: str, alternate: str) -> str:
    return preferred if original != preferred else alternate


async def run_config_round_trip_suite(
    client: BleakClient,
    command_uuid: str,
    response_uuid: str,
    timeout: float,
) -> int:
    next_id = 1000

    async def request(op: str, **extra: Any) -> dict[str, Any]:
        nonlocal next_id
        payload = {"id": next_id, "op": op, **extra}
        next_id += 1
        print(f"\n-> {op} {extra if extra else ''}")
        response = await config_request(client, payload, command_uuid, response_uuid, timeout)
        compact = json.dumps(response, separators=(",", ":"), sort_keys=True)
        print(f"<- {op} ok, {len(compact)} bytes")
        print(preview(compact, 500))
        return response

    original = await request("getConfig")
    original_config = writable_config_from_response(original)

    themes_response = await request("scanThemes", page=0)
    themes = themes_response.get("themes", [])
    if not isinstance(themes, list):
        themes = []

    original_sleep = original_config["sleep"]
    original_bedtime = original_config["bedtime"]
    probe_sleep = {
        "enabled": not original_sleep["enabled"],
        "normalIdleSec": probe_seconds(original_sleep["normalIdleSec"], 300),
        "vibrationWakeIdleSec": probe_seconds(original_sleep["vibrationWakeIdleSec"], 120),
        "bleIdleSec": probe_seconds(original_sleep["bleIdleSec"], 120),
    }
    probe_bedtime = {
        "enabled": not original_bedtime["enabled"],
        "startTime": choose_probe_time(original_bedtime["startTime"], "19:15", "18:45"),
        "endTime": choose_probe_time(original_bedtime["endTime"], "07:15", "06:45"),
        "theme": choose_probe_theme(original_bedtime["theme"], themes),
        "volumeCapPct": choose_probe_volume(original_bedtime["volumeCapPct"]),
    }
    probe_config = {
        "deviceName": choose_probe_device_name(original_config["deviceName"]),
        "defaultVolumePct": choose_probe_volume(original_config["defaultVolumePct"]),
        "defaultTheme": choose_probe_theme(original_config["defaultTheme"], themes),
        "sleep": probe_sleep,
        "bedtime": probe_bedtime,
    }

    print("\nConfig round-trip probe:")
    print(f"  original: {original_config}")
    print(f"  probe:    {probe_config}")

    try:
        updated = await request("setConfig", **probe_config)
        assert_config_matches("setConfig response", updated, probe_config)
        verified = await request("getConfig")
        assert_config_matches("post-write getConfig", verified, probe_config)
    finally:
        restored = await request("setConfig", **original_config)
        assert_config_matches("restore response", restored, original_config)
        verified_restore = await request("getConfig")
        assert_config_matches("post-restore getConfig", verified_restore, original_config)

    print("Config round-trip persisted and restored all config fields.")
    return 0


async def run_bedtime_activation_test(
    client: BleakClient,
    command_uuid: str,
    response_uuid: str,
    timeout: float,
) -> None:
    """Verify time-based bedtime activation by syncing times inside/outside the window."""
    next_id = [200]

    async def request(op: str, **extra: Any) -> dict[str, Any]:
        payload = {"id": next_id[0], "op": op, **extra}
        next_id[0] += 1
        return await config_request(client, payload, command_uuid, response_uuid, timeout)

    print("\nBedtime activation test:")

    config = await request("getConfig")
    bedtime_cfg = bedtime_from_config(config)
    if not bedtime_cfg["enabled"]:
        raise RuntimeError("Bedtime is disabled in device config; enable it to run this test.")

    def parse_hm(t: str) -> int:
        h, m = t.split(":")
        return int(h) * 60 + int(m)

    start_min = parse_hm(bedtime_cfg["startTime"])
    end_min   = parse_hm(bedtime_cfg["endTime"])
    inside, outside = _pick_inside_outside_minutes(start_min, end_min)
    tz = local_time_payload()["tzOffsetMin"]

    def fmt(m: int) -> str:
        return f"{m // 60:02d}:{m % 60:02d}"

    print(f"  Window: {bedtime_cfg['startTime']} – {bedtime_cfg['endTime']}")
    print(f"  Testing inside:  {fmt(inside)}")
    print(f"  Testing outside: {fmt(outside)}")

    resp = await request("syncTime", **_epoch_for_local_minute(inside, tz))
    b = resp.get("bedtime") or {}
    if b.get("timeKnown") is not True:
        raise RuntimeError("syncTime (inside) did not set timeKnown=true")
    if b.get("active") is not True:
        raise RuntimeError(
            f"Expected bedtime active at {fmt(inside)} but got active={b.get('active')} "
            f"autoActive={b.get('autoActive')}"
        )
    print(f"  ✓ Active inside window")

    resp = await request("syncTime", **_epoch_for_local_minute(outside, tz))
    b = resp.get("bedtime") or {}
    if b.get("active") is not False:
        raise RuntimeError(
            f"Expected bedtime inactive at {fmt(outside)} but got active={b.get('active')} "
            f"autoActive={b.get('autoActive')}"
        )
    print(f"  ✓ Inactive outside window")

    # Restore real current time
    await request("syncTime", **local_time_payload())
    print(f"  ✓ Time restored")
    print("Bedtime activation test passed.")


async def run_reconnect_test(device_name: str, service_uuid: str, timeout: float) -> int:
    """Connect BLE, disconnect, verify the device re-advertises and accepts a second connection."""
    def match(d, adv):
        name = d.name or adv.local_name or ""
        advertised = {u.lower() for u in adv.service_uuids}
        return name == device_name or service_uuid in advertised

    print(f"Reconnect test: scanning for {device_name!r}...")
    device = await BleakScanner.find_device_by_filter(match, timeout=timeout)
    if device is None:
        print("No matching BLE advertisement found.")
        return 2

    print(f"Found: {device.name!r} {device.address!r}")
    async with BleakClient(device) as client:
        raw = await client.read_gatt_char(STATUS_UUID)
        status = raw.decode("utf-8", errors="replace")
        print(f"  First connection: status={status!r}")

    print("  Disconnected. Waiting 2s for advertising to restart...")
    await asyncio.sleep(2.0)

    print("  Scanning for device after disconnect...")
    device2 = await BleakScanner.find_device_by_filter(match, timeout=timeout)
    if device2 is None:
        print("Device did not reappear after disconnect — firmware likely crashed or advertising did not restart.")
        return 3

    print(f"  Reappeared: {device2.name!r} {device2.address!r}")
    async with BleakClient(device2) as client2:
        raw2 = await client2.read_gatt_char(STATUS_UUID)
        status2 = raw2.decode("utf-8", errors="replace")
        print(f"  Second connection: status={status2!r}")

    print("BLE reconnect test passed.")
    return 0


async def main() -> int:
    parser = argparse.ArgumentParser(description="Probe SweetYaar BLE GATT services")
    parser.add_argument("--name", default="SweetYaar")
    parser.add_argument("--service", default="a1b2c3d4-e5f6-7890-abcd-ef1234567890")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--list", action="store_true", help="List advertisements instead of connecting")
    parser.add_argument("--config-get", action="store_true", help="Probe legacy config transport")
    parser.add_argument("--config-api-test", action="store_true", help="Run app-style config API checks")
    parser.add_argument("--config-round-trip-test", action="store_true",
                        help="Write, verify, and restore all config fields through BLE")
    parser.add_argument("--control-smoke-test", action="store_true",
                        help="Read/write basic BLE control characteristics without starting playback")
    parser.add_argument("--reconnect-test", action="store_true",
                        help="Connect, disconnect, verify firmware re-advertises and accepts a second connection")
    parser.add_argument("--hold-open-seconds", type=float, default=0.0,
                        help="Hold the BLE connection open for N extra seconds after tests complete (useful as a background process for concurrent tests)")
    parser.add_argument("--theme", help="Theme id to use for scanSongs in --config-api-test")
    parser.add_argument("--legacy", action="store_true", help="Force legacy command/themes transport")
    parser.add_argument("--bedtime-activation-test", action="store_true",
                        help="Verify bedtime activates/deactivates by syncing time inside/outside the configured window")
    args = parser.parse_args()

    service_uuid = args.service.lower()

    def match(device, adv):
        name = device.name or adv.local_name or ""
        advertised_services = {uuid.lower() for uuid in adv.service_uuids}
        return name == args.name or service_uuid in advertised_services

    if args.list:
        print(f"Scanning all BLE advertisements for {args.timeout:.1f}s...")
        devices = await BleakScanner.discover(timeout=args.timeout, return_adv=True)
        for address, (device, adv) in devices.items():
            name = device.name or adv.local_name or ""
            services = ", ".join(adv.service_uuids)
            print(f"{address} name={name!r} rssi={adv.rssi} services=[{services}]")
        return 0

    if args.reconnect_test:
        return await run_reconnect_test(args.name, service_uuid, args.timeout)

    print(f"Scanning for {args.name!r} / service {service_uuid}...")
    device = await BleakScanner.find_device_by_filter(match, timeout=args.timeout)
    if device is None:
        print("No matching BLE advertisement found.")
        return 2

    print(f"Found device: name={device.name!r} address={device.address!r}")
    async with BleakClient(device) as client:
        print(f"Connected: {client.is_connected}")
        services = client.services
        print("Services:")
        for service in services:
            print(f"  {service.uuid}")
            for char in service.characteristics:
                props = ",".join(char.properties)
                print(f"    {char.uuid} [{props}]")

        direct_available = (
            find_characteristic(services, CONFIG_COMMAND_UUID) and
            find_characteristic(services, CONFIG_RESPONSE_UUID)
        )
        use_direct = direct_available and not args.legacy
        command_uuid = CONFIG_COMMAND_UUID if use_direct else COMMAND_UUID
        response_uuid = CONFIG_RESPONSE_UUID if use_direct else THEMES_UUID
        transport = "direct config characteristics" if use_direct else "legacy command/themes fallback"
        print(f"Config transport: {transport}")

        if args.config_get or args.config_api_test or args.config_round_trip_test or args.control_smoke_test or args.bedtime_activation_test:
            try:
                if args.control_smoke_test:
                    await run_ble_control_smoke(client)
                response = await config_request(
                    client, {"id": 1, "op": "getConfig"}, command_uuid, response_uuid, args.timeout)
                if args.config_get:
                    print("Config response:")
                    print(json.dumps(response, indent=2, sort_keys=True))
                if args.config_api_test:
                    await run_config_api_suite(
                        client, command_uuid, response_uuid, args.timeout, args.theme, start_id=10)
                if args.config_round_trip_test:
                    await run_config_round_trip_suite(
                        client, command_uuid, response_uuid, args.timeout)
                if args.bedtime_activation_test:
                    await run_bedtime_activation_test(
                        client, command_uuid, response_uuid, args.timeout)
            except Exception as exc:
                print(f"Config probe failed: {type(exc).__name__}: {exc}")
                return 3

        if args.hold_open_seconds > 0:
            print(f"Holding BLE connection open for {args.hold_open_seconds:.1f}s...", flush=True)
            await asyncio.sleep(args.hold_open_seconds)
            print("Hold complete; disconnecting.", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
