"""The firmware hooks' assumptions about the prebuilt libraries still hold.

See "Firmware hooks" in docs/engineering/firmware.md. The same checks run
after every firmware link; this test also catches a library change before
anyone builds.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_firmware_hooks", ROOT / "tools" / "check_firmware_hooks.py")
hooks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hooks)

needs_toolchain = pytest.mark.skipif(
    not (hooks.DEFAULT_TOOLCHAIN / "xtensa-esp32-elf-objdump").exists() or not hooks.DEFAULT_LIBBT.exists(),
    reason="the ESP32 toolchain or Arduino framework is not installed (run a firmware build once)")


def test_offsets_are_written_in_the_source() -> None:
    short, long = hooks.source_offsets()
    assert (short, long) == (0x80, 0x82)


@needs_toolchain
def test_library_still_matches_the_name_hook() -> None:
    _, long = hooks.source_offsets()
    hooks.check_library(hooks.DEFAULT_TOOLCHAIN, hooks.DEFAULT_LIBBT, long)


@needs_toolchain
def test_a_moved_call_is_reported() -> None:
    with pytest.raises(hooks.HookCheckError, match="returns at"):
        hooks.check_library(hooks.DEFAULT_TOOLCHAIN, hooks.DEFAULT_LIBBT, 0x84)


@needs_toolchain
@pytest.mark.skipif(not hooks.DEFAULT_ELF.exists(), reason="the firmware has not been built")
def test_linked_firmware_calls_the_hook_where_expected() -> None:
    short, long = hooks.source_offsets()
    hooks.check_elf(hooks.DEFAULT_TOOLCHAIN, hooks.DEFAULT_ELF, short, long)
