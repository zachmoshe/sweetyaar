#!/usr/bin/env python3
import argparse
import asyncio
import json
from typing import Any

from bleak import BleakClient, BleakScanner

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


async def write_json(client: BleakClient, char_uuid: str, payload: dict[str, Any]) -> None:
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
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
) -> int:
    next_id = 1

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


async def main() -> int:
    parser = argparse.ArgumentParser(description="Probe SweetYaar BLE GATT services")
    parser.add_argument("--name", default="SweetYaar")
    parser.add_argument("--service", default="a1b2c3d4-e5f6-7890-abcd-ef1234567890")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--list", action="store_true", help="List advertisements instead of connecting")
    parser.add_argument("--config-get", action="store_true", help="Probe legacy config transport")
    parser.add_argument("--config-api-test", action="store_true", help="Run app-style config API checks")
    parser.add_argument("--theme", help="Theme id to use for scanSongs in --config-api-test")
    parser.add_argument("--legacy", action="store_true", help="Force legacy command/themes transport")
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

        if args.config_get or args.config_api_test:
            try:
                if args.config_api_test:
                    return await run_config_api_suite(
                        client, command_uuid, response_uuid, args.timeout, args.theme)
                response = await config_request(
                    client,
                    {"id": 1, "op": "getConfig"},
                    command_uuid,
                    response_uuid,
                    args.timeout,
                )
                print("Config response:")
                print(json.dumps(response, indent=2, sort_keys=True))
            except Exception as exc:
                print(f"Config probe failed: {type(exc).__name__}: {exc}")
                return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
