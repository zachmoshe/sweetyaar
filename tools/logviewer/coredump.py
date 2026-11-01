"""Decodes a core dump from the log into a backtrace and task list.

esp-coredump needs the exact firmware.elf of the build that crashed. Releases
archive theirs in the firmware-elfs bucket (tools/release_firmware.py); the
viewer downloads one as the read-only logs-viewer service account and keeps it
in CACHE. To decode a crash of a bench build, put its ELF there by hand:
CACHE/<board>/<version>/firmware.elf.
"""

from __future__ import annotations

import gzip
import hashlib
import pathlib
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request

BUCKET = "sweetyaar-firmware-elfs"
BOARD = "sweetyaar"  # releases are built for the production board only
CACHE = pathlib.Path.home() / ".cache/sweetyaar/elfs"
GDB = pathlib.Path.home() / ".platformio/packages/toolchain-xtensa-esp32/bin/xtensa-esp32-elf-gdb"
ESP_COREDUMP = pathlib.Path(sys.executable).parent / "esp-coredump"


class DecodeError(Exception):
    pass


class Decoder:
    def __init__(self, token, cache: pathlib.Path = CACHE, board: str = BOARD, fetch=urllib.request.urlopen,
                 run=subprocess.run):
        """|token| returns a logs-viewer access token, asked for only on a download."""
        self.token, self.cache, self.board, self.fetch, self.run = token, cache, board, fetch, run
        self._decoded: dict[str, str] = {}
        self._lock = threading.Lock()

    def elf(self, version: str) -> pathlib.Path:
        path = self.cache / self.board / version / "firmware.elf"
        if path.exists():
            return path
        name = urllib.parse.quote(f"{self.board}/{version}/firmware.elf.gz", safe="")
        request = urllib.request.Request(
            f"https://storage.googleapis.com/storage/v1/b/{BUCKET}/o/{name}?alt=media",
            headers={"Authorization": f"Bearer {self.token()}"})
        try:
            with self.fetch(request, timeout=120) as response:
                packed = response.read()
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise DecodeError(f"No ELF of {version} in gs://{BUCKET} (only releases are archived). "
                                  f"For a bench build, put its firmware.elf at {path}.") from None
            raise DecodeError(f"Could not download the {version} ELF: HTTP {error.code}") from None
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(".part")
        partial.write_bytes(gzip.decompress(packed))
        partial.replace(path)
        return path

    def decode(self, core: bytes, version: str | None) -> str:
        """esp-coredump's report: crashed task, registers, backtrace, all tasks."""
        if not version:
            raise DecodeError("The log does not say which firmware crashed (its BOOT record was overwritten)")
        if self.run is subprocess.run and not ESP_COREDUMP.exists():
            raise DecodeError(f"esp-coredump is not installed in {ESP_COREDUMP.parent.parent}: run make setup")
        key = hashlib.sha256(core + version.encode()).hexdigest()
        with self._lock:
            if key in self._decoded:
                return self._decoded[key]
            elf = self.elf(version)
            with tempfile.TemporaryDirectory() as folder:
                core_file = pathlib.Path(folder) / "core.bin"
                core_file.write_bytes(core)
                result = self.run([str(ESP_COREDUMP), "--chip", "esp32", "info_corefile", "--core-format", "raw",
                                   "--gdb", str(GDB), "--core", str(core_file), str(elf)],
                                  capture_output=True, text=True, timeout=180)
            if result.returncode:
                lines = (result.stderr or result.stdout).strip().splitlines()
                raise DecodeError("esp-coredump failed: " + (lines[-1] if lines else f"exit {result.returncode}"))
            self._decoded[key] = result.stdout
            return result.stdout
