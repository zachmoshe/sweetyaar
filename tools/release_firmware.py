#!/usr/bin/env python3
"""
Publish firmware images for the parent app's update flow.

Reads FIRMWARE_VERSION from firmware/esp32/src/Config.h and the release note for
that version from firmware/release-notes.json, compresses the production board's
built image and writes app/public/firmware/manifest.json. Before that it
archives the build's firmware.elf in the firmware-elfs bucket, since a core
dump from the field can only be decoded with the exact ELF that crashed. The generic prototype
is not published; update it from a Mac with tools/ota_update.py. Deploying the app then
offers the update to toys running an older version.

The release note is shown to parents as-is. It must be a short text written or
approved by a person for this release; never generate it from commit messages.

Usage (after a hardware-validated build):
    .venv/bin/python tools/release_firmware.py --build
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import zlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG_H = ROOT / "firmware/esp32/src/Config.h"
NOTES = ROOT / "firmware/release-notes.json"
FIRMWARE_DIR = ROOT / "firmware/esp32"
OUT_DIR = ROOT / "app/public/firmware"
SERVICE_WORKER = ROOT / "app/public/sw.js"
BOARDS = ("sweetyaar",)  # published boards; PlatformIO env == board ID
# Every board ID in platformio.ini, to catch an image built for another board.
ALL_BOARDS = ("sweetyaar", "sweetyaar-generic")
APP_SLOT_BYTES = 0x330000  # partitions_8mb.csv app0/app1
NOTE_MAX_CHARS = 160
ZLIB_WINDOW_BITS = 15  # the device inflates with a 32 KB dictionary
ELF_BUCKET = "gs://sweetyaar-firmware-elfs"  # project sweetyaar; never overwritten
APP_ELF_SHA256 = slice(0xB0, 0xD0)  # esp_app_desc_t.app_elf_sha256 in the image


class ReleaseError(Exception):
    pass


def firmware_version(config_text: str) -> str:
    match = re.search(r'FIRMWARE_VERSION\[\]\s*=\s*"(\d+\.\d+\.\d+)"', config_text)
    if not match:
        raise ReleaseError("FIRMWARE_VERSION (major.minor.patch) not found in Config.h")
    return match.group(1)


def release_note(notes: dict, version: str) -> str:
    note = notes.get(version)
    if not isinstance(note, str) or not note.strip():
        raise ReleaseError(
            f"Add a short human-written release note for {version} to {NOTES.relative_to(ROOT)}.")
    note = note.strip()
    if "\n" in note or len(note) > NOTE_MAX_CHARS:
        raise ReleaseError(f"The {version} release note must be one line of at most {NOTE_MAX_CHARS} characters.")
    return note


def compress(image: bytes) -> bytes:
    packer = zlib.compressobj(level=9, wbits=ZLIB_WINDOW_BITS)
    packed = packer.compress(image) + packer.flush()
    if zlib.decompress(packed) != image:
        raise ReleaseError("Compressed image does not round-trip")
    return packed


def check_image(board: str, image: bytes, version: str) -> None:
    if not image or image[0] != 0xE9:
        raise ReleaseError(f"{board}: not an ESP32 app image")
    if len(image) > APP_SLOT_BYTES:
        raise ReleaseError(f"{board}: {len(image)} bytes does not fit the {APP_SLOT_BYTES}-byte app slot")
    # FIRMWARE_VERSION and FIRMWARE_BOARD_ID are stored as C strings, so a
    # stale build or another board's image fails these checks.
    if f"{version}\0".encode() not in image:
        raise ReleaseError(f"{board}: image is not version {version}; rebuild it")
    if f"{board}\0".encode() not in image or any(
            f"{other}\0".encode() in image for other in ALL_BOARDS if other != board):
        raise ReleaseError(f"{board}: image was built for another board")


def elf_sha256(image: bytes, elf: bytes) -> str:
    """The ELF's SHA-256, checked against the one the build wrote into the image."""
    digest = hashlib.sha256(elf).hexdigest()
    if image[APP_ELF_SHA256].hex() != digest:
        raise ReleaseError("firmware.elf is not the ELF of this firmware.bin; rebuild")
    return digest


def elf_object(board: str, version: str) -> str:
    return f"{ELF_BUCKET}/{board}/{version}/firmware.elf.gz"


def gcloud(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gcloud", *args], capture_output=True, text=True)


def archive_elf(board: str, version: str, image: bytes, elf: bytes, commit: str, run=gcloud) -> str:
    """Uploads the ELF unless this exact build is already archived; returns what happened.

    An archived ELF of another build of the same version is never replaced:
    toys may run that build, and their crashes need its ELF.
    """
    digest = elf_sha256(image, elf)
    target = elf_object(board, version)
    existing = run("storage", "objects", "describe", target, "--format=value(custom_fields.elf-sha256)")
    if existing.returncode == 0:
        if existing.stdout.strip() == digest:
            return f"{target} already holds this build"
        raise ReleaseError(f"{target} holds another build of {version}; publish a new version instead")
    if "not found" not in (existing.stderr or "").lower() and "404" not in (existing.stderr or ""):
        raise ReleaseError(f"Could not check {target}: {existing.stderr.strip()}")
    with tempfile.TemporaryDirectory() as folder:
        packed = pathlib.Path(folder) / "firmware.elf.gz"
        packed.write_bytes(gzip.compress(elf, 9, mtime=0))
        metadata = (f"version={version},board={board},commit={commit},"
                    f"image-sha256={hashlib.sha256(image).hexdigest()},elf-sha256={digest}")
        uploaded = run("storage", "cp", str(packed), target, "--no-clobber",
                       "--content-type=application/gzip", f"--custom-metadata={metadata}")
    if uploaded.returncode:
        raise ReleaseError(f"Could not upload {target}: {uploaded.stderr.strip()}")
    return f"Archived firmware.elf as {target}"


def git_commit() -> str:
    result = subprocess.run(["git", "-C", str(ROOT), "describe", "--always", "--dirty", "--abbrev=40"],
                            capture_output=True, text=True)
    return result.stdout.strip() or "unknown"


def bump_cache_version(sw_text: str) -> str:
    """Next CACHE_VERSION, so installed apps pick up the release promptly."""
    pattern = re.compile(r'(const CACHE_VERSION = "sweetyaar-parent-v)(\d+)(";)')
    if not pattern.search(sw_text):
        raise ReleaseError("CACHE_VERSION not found in app/public/sw.js")
    return pattern.sub(lambda m: f"{m.group(1)}{int(m.group(2)) + 1}{m.group(3)}", sw_text, count=1)


def build_release(images: dict[str, bytes], version: str, note: str, out_dir: pathlib.Path) -> dict:
    # Check every board before writing anything: no half-written release.
    for board, image in images.items():
        check_image(board, image, version)
    packed_images = {board: compress(image) for board, image in images.items()}
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"format": 1, "version": version, "notes": note, "images": {}}
    for board, image in images.items():
        packed = packed_images[board]
        name = f"{board}-{version}.bin.z"
        for old in out_dir.glob(f"{board}-*.bin.z"):
            if old.name != name:
                old.unlink()
        (out_dir / name).write_bytes(packed)
        manifest["images"][board] = {
            "file": name,
            "encoding": "zlib",
            "size": len(image),
            "encodedSize": len(packed),
            "sha256": hashlib.sha256(image).hexdigest(),
            "fileSha256": hashlib.sha256(packed).hexdigest(),
        }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--build", action="store_true", help="build with PlatformIO first")
    parser.add_argument("--board", action="append", choices=BOARDS, help="limit to these boards (default: all)")
    args = parser.parse_args()
    boards = args.board or list(BOARDS)
    try:
        version = firmware_version(CONFIG_H.read_text())
        note = release_note(json.loads(NOTES.read_text()), version)
        if args.build:
            pio = ROOT / ".venv/bin/pio"
            for board in boards:
                subprocess.run([str(pio), "run", "-d", str(FIRMWARE_DIR), "-e", board], check=True)
        images = {board: (FIRMWARE_DIR / ".pio/build" / board / "firmware.bin").read_bytes() for board in boards}
        for board, image in images.items():
            check_image(board, image, version)
            elf = (FIRMWARE_DIR / ".pio/build" / board / "firmware.elf").read_bytes()
            print(archive_elf(board, version, image, elf, git_commit()))
        manifest = build_release(images, version, note, OUT_DIR)
        SERVICE_WORKER.write_text(bump_cache_version(SERVICE_WORKER.read_text()))
    except (ReleaseError, FileNotFoundError, subprocess.CalledProcessError) as error:
        print(f"release_firmware: {error}", file=sys.stderr)
        return 1
    for board, entry in manifest["images"].items():
        print(f"{board}: {entry['size']} B -> {entry['encodedSize']} B ({entry['file']})")
    print(f"Wrote {OUT_DIR.relative_to(ROOT)}/manifest.json for {version}: {note}")
    print("Bumped CACHE_VERSION in app/public/sw.js.")
    print("Commit app/public and push to main; parents see the update on their next connection.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
