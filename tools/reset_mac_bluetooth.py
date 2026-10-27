#!/usr/bin/env python3
"""Make this Mac forget every SweetYaar board it has met over Bluetooth.

macOS keeps what it knows about a Bluetooth device in bluetoothd's protected
stores: the LE bond in the System keychain (service BluetoothLE, account
"Public <address>"), Classic link keys (service MobileBluetooth), device rows in
/Library/Bluetooth/*.db and per-device records in
/Library/Bluetooth/Library/Preferences/com.apple.MobileBluetooth.devices.plist.
System Settings > Forget does not reliably remove all of them, and a stale bond
keeps a stale GATT cache alive.

Parents rename the toy, so it is never found by name. `--scan` (run without
sudo) finds powered toys by their BLE service UUID and prints the identifiers
CoreBluetooth gives them; the reset (with sudo) maps those identifiers to
addresses through macOS's device rows. `--address` names a board directly, for
example from the toy's boot log (`[BT] Classic BT address`). Every record whose
address shares the first five octets with such a board is removed (one ESP32
uses neighbouring addresses for Classic and LE). It lists what it will delete, asks, deletes it
and restarts bluetoothd so nothing stale stays in memory. Run it with sudo from
a terminal app that has Full Disk Access. --inspect is read-only and never
prints key material.

This relies on undocumented macOS storage (checked on macOS 26); recheck the
layout with --inspect after a macOS upgrade.
"""

import argparse
import os
import plistlib
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

BLUETOOTH_DIR = Path("/Library/Bluetooth")
EXTRA_PLISTS = [
    Path("/Library/Preferences/com.apple.Bluetooth.plist"),
    Path("/private/var/root/Library/Preferences/com.apple.bluetoothd.plist"),
]
SYSTEM_KEYCHAIN = "/Library/Keychains/System.keychain"
SECRET_NAME = re.compile(r"key|irk|ltk|csrk|secret|rand|ediv|token", re.I)


def masked(name, value):
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<{len(value)} bytes>"
    if name and SECRET_NAME.search(str(name)):
        return "<masked>"
    return value


def matches(value, patterns):
    text = value.decode("utf-8", "ignore") if isinstance(value, (bytes, bytearray)) else str(value)
    return any(p in text.lower() for p in patterns)


def inspect_db(path, patterns):
    print(f"\n=== {path}")
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as error:
        print(f"  cannot open: {error}")
        return
    with db:
        tables = db.execute("SELECT name, sql FROM sqlite_master WHERE type='table'").fetchall()
        for name, sql in tables:
            count = db.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            print(f"\n  table {name} ({count} rows)\n    {sql}")
            cursor = db.execute(f'SELECT * FROM "{name}"')
            columns = [c[0] for c in cursor.description]
            for row in cursor:
                if any(matches(v, patterns) for v in row if v is not None):
                    shown = {c: masked(c, v) for c, v in zip(columns, row)}
                    print(f"    MATCH {shown}")


def walk_plist(value, path, patterns, hits):
    if isinstance(value, dict):
        for key, child in value.items():
            walk_plist(child, f"{path}/{key}", patterns, hits)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            walk_plist(child, f"{path}[{index}]", patterns, hits)
    elif matches(path, patterns) or (isinstance(value, str) and matches(value, patterns)):
        hits.append((path, masked(path.rsplit("/", 1)[-1], value)))


def inspect_plist(path, patterns):
    print(f"\n=== {path}")
    try:
        data = plistlib.loads(path.read_bytes())
    except (OSError, plistlib.InvalidFileException) as error:
        print(f"  cannot read: {error}")
        return
    if isinstance(data, dict):
        print(f"  top-level keys: {sorted(data)}")
        if "MobileBluetooth.devices" in path.name:
            # One entry per Classic device: show its field names and plain values.
            for address, entry in sorted(data.items()):
                if isinstance(entry, dict):
                    fields = {k: masked(k, v) if not isinstance(v, (dict, list)) else type(v).__name__
                              for k, v in entry.items()}
                    print(f"  {address}: {fields}")
    hits = []
    walk_plist(data, "", patterns, hits)
    for hit_path, value in hits:
        print(f"  MATCH {hit_path} = {value!r}")


def inspect(patterns):
    print(f"Matching (case-insensitive): {patterns}")
    try:
        entries = sorted(path for path in BLUETOOTH_DIR.rglob("*"))
    except OSError as error:
        sys.exit(f"Cannot list {BLUETOOTH_DIR}: {error}\n"
                 "Run with sudo from a terminal app that has Full Disk Access.")
    print(f"\n{BLUETOOTH_DIR}:")
    for entry in entries:
        kind = "dir" if entry.is_dir() else f"{entry.stat().st_size} bytes"
        print(f"  {entry.relative_to(BLUETOOTH_DIR)} ({kind})")
    for entry in entries:
        if entry.suffix == ".db":
            inspect_db(entry, patterns)
        elif entry.suffix == ".plist":
            inspect_plist(entry, patterns)
    for path in EXTRA_PLISTS:
        if path.exists():
            inspect_plist(path, patterns)
    inspect_keychain(patterns)


def inspect_keychain(patterns):
    # Without -d, dump-keychain prints item attributes only, never secrets.
    print(f"\n=== {SYSTEM_KEYCHAIN} (attributes only)")
    result = subprocess.run(["/usr/bin/security", "dump-keychain", SYSTEM_KEYCHAIN],
                            capture_output=True, text=True, errors="replace")
    if result.returncode:
        print(f"  cannot read: {result.stderr.strip()}")
        return
    services = {}
    for item in result.stdout.split("keychain: ")[1:]:
        service = re.search(r'"svce"<blob>="([^"]*)"', item)
        services[service.group(1) if service else "?"] = services.get(service.group(1) if service else "?", 0) + 1
        if (service and "luetooth" in service.group(1)) or matches(item, patterns):
            account = re.search(r'"acct"<blob>="([^"]*)"', item)
            label = re.search(r'0x00000007 <blob>="([^"]*)"', item)
            tag = "MATCH" if matches(item, patterns) else "item"
            print(f"  {tag} service={service and service.group(1)!r} "
                  f"account={account and account.group(1)!r} label={label and label.group(1)!r}")
    bluetooth = {k: v for k, v in services.items() if "luetooth" in k}
    print(f"  Bluetooth item services: {bluetooth}")


ADDRESS = re.compile(r"([0-9A-F]{2}(?::[0-9A-F]{2}){5})", re.I)
DEVICE_DBS = [
    (BLUETOOTH_DIR / "com.apple.MobileBluetooth.ledevices.paired.db", "PairedDevices"),
    (BLUETOOTH_DIR / "com.apple.MobileBluetooth.ledevices.other.db", "OtherDevices"),
]
DEVICES_PLIST = BLUETOOTH_DIR / "Library/Preferences/com.apple.MobileBluetooth.devices.plist"
KEYCHAIN_SERVICES = ("BluetoothLE", "MobileBluetooth")


def board_prefix(text):
    found = ADDRESS.search(text or "")
    return found.group(1).upper()[:14] if found else None


def keychain_items():
    result = subprocess.run(["/usr/bin/security", "dump-keychain", SYSTEM_KEYCHAIN],
                            capture_output=True, text=True, errors="replace", check=True)
    items = []
    for item in result.stdout.split("keychain: ")[1:]:
        service = re.search(r'"svce"<blob>="([^"]*)"', item)
        account = re.search(r'"acct"<blob>="([^"]*)"', item)
        label = re.search(r'0x00000007 <blob>="([^"]*)"', item)
        if service and account and service.group(1) in KEYCHAIN_SERVICES:
            items.append((service.group(1), account.group(1), label.group(1) if label else ""))
    return items


SERVICE_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"  # BLE_SERVICE_UUID in Config.h


def scan_identifiers(seconds=8.0):
    """CoreBluetooth identifiers of advertising toys, found by service UUID, never by name."""
    import asyncio
    from bleak import BleakScanner

    async def discover():
        found = await BleakScanner.discover(timeout=seconds, return_adv=True)
        return [(device.address, device.name) for device, adv in found.values()
                if SERVICE_UUID in [u.lower() for u in adv.service_uuids]]

    return asyncio.run(discover())


def find_records(identifiers, addresses):
    """Return what to delete: {'rows': [...], 'keychain': [...], 'plist': [...]}."""
    prefixes = {a.upper()[:14] for a in addresses}
    identifiers = {i.upper() for i in identifiers}
    rows = []
    for path, table in DEVICE_DBS:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
            for uuid, name, address in db.execute(f'SELECT Uuid, Name, Address FROM "{table}"'):
                if (uuid or "").upper() in identifiers:
                    prefixes.add(board_prefix(address))
                rows.append((path, table, uuid, name, address))
    prefixes.discard(None)
    keychain = [item for item in keychain_items() if board_prefix(item[1]) in prefixes]
    labels = {item[2] for item in keychain}
    rows = [row for row in rows if board_prefix(row[4]) in prefixes or row[2] in labels]
    plist = plistlib.loads(DEVICES_PLIST.read_bytes()) if DEVICES_PLIST.exists() else {}
    entries = [address for address in plist if board_prefix(address) in prefixes]
    return {"prefixes": sorted(prefixes), "rows": rows, "keychain": keychain, "plist": entries}


def delete_records(found):
    for path, table, uuid, _, address in found["rows"]:
        with sqlite3.connect(path, timeout=10) as db:
            db.execute(f'DELETE FROM "{table}" WHERE Uuid = ? AND Address IS ?', (uuid, address))
    if found["plist"]:
        mode = DEVICES_PLIST.stat()
        data = plistlib.loads(DEVICES_PLIST.read_bytes())
        for address in found["plist"]:
            data.pop(address, None)
        DEVICES_PLIST.write_bytes(plistlib.dumps(data, fmt=plistlib.FMT_BINARY))
        os.chown(DEVICES_PLIST, mode.st_uid, mode.st_gid)
        os.chmod(DEVICES_PLIST, mode.st_mode)
    for service, account, _ in found["keychain"]:
        subprocess.run(["/usr/bin/security", "delete-generic-password", "-s", service,
                        "-a", account, SYSTEM_KEYCHAIN], check=True, capture_output=True)
    # launchd restarts bluetoothd at once; it then reloads from the edited stores.
    subprocess.run(["/usr/bin/pkill", "-x", "bluetoothd"], check=False)


def reset(identifiers, addresses, assume_yes):
    found = find_records(identifiers, addresses)
    if not found["prefixes"]:
        sys.exit("No SweetYaar board identified. Power the toy on near this Mac so the scan "
                 "finds it, or pass ADDRESS=<the [BT] Classic BT address from its boot log>.")
    print(f"SweetYaar boards (address prefixes): {', '.join(found['prefixes'])}")
    print("Will delete:")
    for _, table, uuid, name, address in found["rows"]:
        print(f"  device row  {table}: {name or '(no name)'} {address} {uuid}")
    for service, account, _ in found["keychain"]:
        print(f"  keychain    {service}: {account}")
    for address in found["plist"]:
        print(f"  device record  {DEVICES_PLIST.name}: {address}")
    print("Then restart bluetoothd (other Bluetooth devices reconnect within seconds).")
    print("Quit Chrome completely (Cmd-Q) first: a running Chrome does not recover from the restart.")
    if not assume_yes and input("Continue? [y/N] ").strip().lower() != "y":
        print("Nothing changed.")
        return
    delete_records(found)
    time.sleep(3)
    left = find_records(identifiers, addresses)
    remaining = len(left["rows"]) + len(left["keychain"]) + len(left["plist"])
    if remaining:
        sys.exit(f"bluetoothd restored {remaining} record(s); run again with Bluetooth turned off.")
    print("Done. On the toy, hold both buttons for 10 seconds to clear its bonds too,")
    print("then hold them for 3 seconds to open pairing and connect again.")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--inspect", action="store_true", help="read-only report (no changes)")
    parser.add_argument("--match", action="append", default=[],
                        help="--inspect: extra text to match (an address or CoreBluetooth UUID)")
    parser.add_argument("--scan", action="store_true",
                        help="without sudo: print identifiers of nearby toys, one per line")
    parser.add_argument("--identifier", action="append", default=[],
                        help="forget the board with this CoreBluetooth identifier (from --scan)")
    parser.add_argument("--address", action="append", default=[],
                        help="forget this board's address (e.g. from the toy's boot log)")
    parser.add_argument("--yes", action="store_true", help="do not ask before deleting")
    args = parser.parse_args()
    if args.scan:
        for identifier, name in scan_identifiers():
            print(identifier)
            print(f"Found toy {name or '(no name)'}: {identifier}", file=sys.stderr)
        return
    if os.geteuid() != 0:
        sys.exit("Run with sudo: the Bluetooth stores are root-only.")
    patterns = ["sweetyaar"] + [m.lower() for m in args.match]
    if args.inspect:
        inspect(patterns)
        return
    if not os.access(BLUETOOTH_DIR, os.R_OK | os.X_OK):
        sys.exit(f"Cannot read {BLUETOOTH_DIR}: give this terminal app Full Disk Access.")
    for address in args.address:
        if not ADDRESS.fullmatch(address):
            sys.exit(f"Not a Bluetooth address: {address}")
    reset(args.identifier, args.address, args.yes)


if __name__ == "__main__":
    main()
