import importlib.util
import plistlib
import sqlite3


def load_tool(repo_root):
    spec = importlib.util.spec_from_file_location("reset_mac_bluetooth", repo_root / "tools/reset_mac_bluetooth.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_db(path, table, rows):
    with sqlite3.connect(path) as db:
        db.execute(f"CREATE TABLE {table}(Uuid TEXT, Name TEXT, Address TEXT)")
        db.executemany(f"INSERT INTO {table} VALUES (?, ?, ?)", rows)


def test_finds_and_deletes_only_the_scanned_toys_records(repo_root, tmp_path, monkeypatch):
    tool = load_tool(repo_root)
    paired, other = tmp_path / "paired.db", tmp_path / "other.db"
    make_db(paired, "PairedDevices", [
        ("C0785144", "", "Public F8:B3:B7:E1:59:32"),       # the toy's LE bond, unnamed
        ("61C6EA16", "Bose", "Public E4:58:BC:2B:C4:4E")])
    make_db(other, "OtherDevices", [
        ("FABF42FC", "SweetTommy", "Public F8:B3:B7:E1:59:72"),  # renamed by a parent
        ("BBBB0000", "SweetYaar", "Public 30:76:F5:EF:48:F6"),   # the name alone is never enough
        ("AAAA0000", "Phone", "Random 11:22:33:44:55:66")])
    devices = tmp_path / "devices.plist"
    devices.write_bytes(plistlib.dumps({"F8:B3:B7:E1:59:32": {"Name": ""},
                                        "E4:58:BC:2B:C4:4E": {"Name": "Bose"}}, fmt=plistlib.FMT_BINARY))
    monkeypatch.setattr(tool, "DEVICE_DBS", [(paired, "PairedDevices"), (other, "OtherDevices")])
    monkeypatch.setattr(tool, "DEVICES_PLIST", devices)
    keychain = [("BluetoothLE", "Public F8:B3:B7:E1:59:32", "C0785144"),
                ("BluetoothLE", "Public E4:58:BC:2B:C4:4E", "61C6EA16"),
                ("MobileBluetooth", "E4:58:BC:2B:C4:4E", "MobileBluetooth")]
    monkeypatch.setattr(tool, "keychain_items", lambda: list(keychain))
    commands = []
    monkeypatch.setattr(tool.subprocess, "run", lambda args, **_: commands.append(args))

    assert tool.find_records([], [])["prefixes"] == []
    found = tool.find_records(["fabf42fc"], [])  # identifier from the BLE service scan
    assert found["prefixes"] == ["F8:B3:B7:E1:59"]
    assert {row[2] for row in found["rows"]} == {"C0785144", "FABF42FC"}
    assert found["keychain"] == [keychain[0]]
    assert found["plist"] == ["F8:B3:B7:E1:59:32"]

    tool.delete_records(found)
    with sqlite3.connect(paired) as db:
        assert [r[0] for r in db.execute("SELECT Uuid FROM PairedDevices")] == ["61C6EA16"]
    with sqlite3.connect(other) as db:
        assert [r[0] for r in db.execute("SELECT Uuid FROM OtherDevices")] == ["BBBB0000", "AAAA0000"]
    assert list(plistlib.loads(devices.read_bytes())) == ["E4:58:BC:2B:C4:4E"]
    assert ["/usr/bin/security", "delete-generic-password", "-s", "BluetoothLE",
            "-a", "Public F8:B3:B7:E1:59:32", tool.SYSTEM_KEYCHAIN] in commands
    assert commands[-1] == ["/usr/bin/pkill", "-x", "bluetoothd"]
    assert not any("E4:58" in " ".join(c) for c in commands)


def test_explicit_address_without_named_rows(repo_root, tmp_path, monkeypatch):
    tool = load_tool(repo_root)
    paired, other = tmp_path / "paired.db", tmp_path / "other.db"
    make_db(paired, "PairedDevices", [("C0785144", "", "Public F8:B3:B7:E1:59:32")])
    make_db(other, "OtherDevices", [])
    monkeypatch.setattr(tool, "DEVICE_DBS", [(paired, "PairedDevices"), (other, "OtherDevices")])
    monkeypatch.setattr(tool, "DEVICES_PLIST", tmp_path / "missing.plist")
    monkeypatch.setattr(tool, "keychain_items", lambda: [])
    assert tool.find_records(["FABF42FC"], [])["prefixes"] == []  # unknown to macOS
    found = tool.find_records([], ["f8:b3:b7:e1:59:30"])
    assert [row[2] for row in found["rows"]] == ["C0785144"]
