#!/usr/bin/env python3
"""Check the assumptions of the firmware's hooks into library internals.

See "Firmware hooks" in docs/engineering/firmware.md. Run after every
firmware link (firmware/esp32/check_firmware_hooks_post.py) and by
tests/test_firmware_hooks.py. Reads the prebuilt Bluetooth library and,
when given, the linked firmware; changes nothing.

The GAP Device Name hook (BLEParentService.cpp) wraps
BTM_ReadLocalDeviceName and acts only when it returns into
gap_read_attr_value at one of two exact offsets. This checks that:
- in libbt.a, the only callers of BTM_ReadLocalDeviceName are
  gap_read_attr_value, bta_dm_set_eir and bta_dm_get_dev_name, and the
  call inside gap_read_attr_value is the l32r + callx8 that returns at the
  long offset;
- in the linked firmware, gap_read_attr_value's call reaches the wrapper and
  returns at the short or the long offset;
- both offsets are the ones written in BLEParentService.cpp.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "firmware/esp32/src/BLEParentService.cpp"
DOC = "\"Firmware hooks\" in docs/engineering/firmware.md"
DEFAULT_ELF = ROOT / "firmware/esp32/.pio/build/sweetyaar/firmware.elf"
DEFAULT_TOOLCHAIN = pathlib.Path.home() / ".platformio/packages/toolchain-xtensa-esp32/bin"
DEFAULT_LIBBT = (pathlib.Path.home() /
                 ".platformio/packages/framework-arduinoespressif32/tools/sdk/esp32/lib/libbt.a")

HOOKED = "BTM_ReadLocalDeviceName"
GAP_READ = "gap_read_attr_value"
EXPECTED_CALLERS = {
    "gap_ble.c.obj": {GAP_READ},
    "bta_dm_act.c.obj": {"bta_dm_set_eir", "bta_dm_get_dev_name"},
}


class HookCheckError(Exception):
    pass


def source_offsets() -> tuple[int, int]:
    text = SOURCE.read_text()
    found = {}
    for name in ("GAP_NAME_CALL_RETURN_SHORT", "GAP_NAME_CALL_RETURN_LONG"):
        match = re.search(rf"{name}\s*=\s*(0x[0-9A-Fa-f]+)", text)
        if not match:
            raise HookCheckError(f"{name} not found in {SOURCE.relative_to(ROOT)}")
        found[name] = int(match.group(1), 16)
    return found["GAP_NAME_CALL_RETURN_SHORT"], found["GAP_NAME_CALL_RETURN_LONG"]


def run(tool: pathlib.Path, *args: str) -> str:
    return subprocess.run([str(tool), *args], check=True, capture_output=True, text=True).stdout


def functions_referencing(objdump_text: str, symbol: str) -> set[str]:
    """Functions whose code or literals refer to |symbol| (objdump -dr)."""
    found, current = set(), None
    for line in objdump_text.splitlines():
        head = re.match(r"^[0-9a-f]+ <(?:\.literal\.)?([^>+]+)>:", line)
        if head:
            current = head.group(1)
        elif current and re.search(rf"\b{re.escape(symbol)}\b", line):
            found.add(current)
    return found


def check_library(toolchain: pathlib.Path, libbt: pathlib.Path, long_offset: int) -> list[str]:
    nm, objdump, ar = (toolchain / f"xtensa-esp32-elf-{name}" for name in ("nm", "objdump", "ar"))
    notes = []
    objects = set()
    for line in run(nm, "-A", str(libbt)).splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[-2] == "U" and parts[-1] == HOOKED:
            objects.add(parts[0].split(":")[-2])
    if objects != set(EXPECTED_CALLERS):
        raise HookCheckError(f"{HOOKED} is called from {sorted(objects)} in libbt.a, "
                             f"expected {sorted(EXPECTED_CALLERS)}")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([str(ar), "x", str(libbt), *EXPECTED_CALLERS], cwd=tmp, check=True)
        for obj, expected in EXPECTED_CALLERS.items():
            text = run(objdump, "-dr", str(pathlib.Path(tmp) / obj))
            callers = functions_referencing(text, HOOKED)
            if callers != expected:
                raise HookCheckError(f"{HOOKED} is called by {sorted(callers)} in {obj}, "
                                     f"expected {sorted(expected)}")
            if obj == "gap_ble.c.obj":
                body = text.split(f"<{GAP_READ}>:", 1)[1].split("\n\n", 1)[0]
                reloc = re.search(rf"^\s+([0-9a-f]+): R_XTENSA_ASM_EXPAND\s+{HOOKED}$", body, re.M)
                if not reloc:
                    raise HookCheckError(f"no call to {HOOKED} found in {GAP_READ} (libbt.a)")
                callx = re.search(r"^\s+([0-9a-f]+):\s+[0-9a-f]+\s+callx8\s", body[reloc.end():], re.M)
                returns = int(callx.group(1), 16) + 3 if callx else None
                if returns != long_offset:
                    raise HookCheckError(f"{GAP_READ}'s call to {HOOKED} returns at "
                                         f"{returns and hex(returns)} in libbt.a, expected {hex(long_offset)}")
    notes.append(f"libbt.a: {HOOKED} callers and the {GAP_READ} call (returns at {hex(long_offset)}) as expected")
    return notes


def check_elf(toolchain: pathlib.Path, elf: pathlib.Path, short_offset: int, long_offset: int) -> list[str]:
    nm, objdump = toolchain / "xtensa-esp32-elf-nm", toolchain / "xtensa-esp32-elf-objdump"
    symbols = {}
    for line in run(nm, "-S", str(elf)).splitlines():
        parts = line.split()
        if len(parts) == 4:
            symbols[parts[3]] = (int(parts[0], 16), int(parts[1], 16))
    if f"__wrap_{HOOKED}" not in symbols:
        raise HookCheckError(f"__wrap_{HOOKED} is not linked into {elf.name}: is -Wl,--wrap={HOOKED} set?")
    start, size = symbols[GAP_READ]
    wrap = symbols[f"__wrap_{HOOKED}"][0]
    text = run(objdump, "-d", f"--start-address={start:#x}", f"--stop-address={start + size:#x}", str(elf))
    short = re.search(rf"^([0-9a-f]+):\s+[0-9a-f]+\s+call8\s+{wrap:x} <__wrap_{HOOKED}>", text, re.M)
    if short:
        returns = int(short.group(1), 16) + 3 - start
        if returns != short_offset:
            raise HookCheckError(f"the call returns at {hex(returns)} in {elf.name}, expected {hex(short_offset)}")
        return [f"{elf.name}: {GAP_READ} calls the wrapper with call8, returning at {hex(returns)}"]
    calls = [int(m.group(1), 16) + 3 - start
             for m in re.finditer(r"^([0-9a-f]+):\s+[0-9a-f]+\s+callx8\s", text, re.M)]
    if long_offset in calls:
        return [f"{elf.name}: {GAP_READ} calls the wrapper with l32r + callx8, returning at {hex(long_offset)}"]
    raise HookCheckError(f"{GAP_READ} does not call the wrapper at {hex(short_offset)} or {hex(long_offset)} "
                         f"in {elf.name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--elf", type=pathlib.Path, help=f"linked firmware (default {DEFAULT_ELF} if it exists)")
    parser.add_argument("--toolchain-bin", type=pathlib.Path, default=DEFAULT_TOOLCHAIN)
    parser.add_argument("--libbt", type=pathlib.Path, default=DEFAULT_LIBBT)
    args = parser.parse_args(argv)
    elf = args.elf or (DEFAULT_ELF if DEFAULT_ELF.exists() else None)
    try:
        short_offset, long_offset = source_offsets()
        notes = check_library(args.toolchain_bin, args.libbt, long_offset)
        if elf:
            notes += check_elf(args.toolchain_bin, elf, short_offset, long_offset)
    except HookCheckError as error:
        print(f"[hooks] FAILED: {error}\n[hooks] The GAP Device Name hook's assumptions changed. "
              f"Read {DOC}, re-derive the call offsets and update BLEParentService.cpp.", file=sys.stderr)
        return 1
    for note in notes:
        print(f"[hooks] ok: {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
