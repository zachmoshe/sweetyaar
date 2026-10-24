#!/usr/bin/env python3
"""
Prepare the next firmware release, interactively.

  1. Shows the current FIRMWARE_VERSION and proposes the next minor version.
  2. Lists the commits since the current version was set.
  3. Asks for the release note parents will see (written by you, one line).
  4. Writes the version to Config.h and the note to firmware/release-notes.json.
  5. Builds the production firmware and prints how to try it on your own doll.

Nothing is published: when the build works on your doll, run
`make release-firmware`, then commit and push.

    make create-published-firmware
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(os.environ.get("SWEETYAAR_ROOT", pathlib.Path(__file__).resolve().parent.parent))
CONFIG_H = "firmware/esp32/src/Config.h"
NOTES = "firmware/release-notes.json"
NOTE_MAX_CHARS = 160
VERSION_RE = re.compile(r'(FIRMWARE_VERSION\[\]\s*=\s*")(\d+\.\d+\.\d+)(")')


class Abort(Exception):
    pass


def parse_version(text: str) -> tuple[int, int, int] | None:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", text.strip())
    return tuple(int(part) for part in match.groups()) if match else None


def next_minor(version: str) -> str:
    major, minor, _ = parse_version(version)
    return f"{major}.{minor + 1}.0"


def current_version(config_text: str) -> str:
    match = VERSION_RE.search(config_text)
    if not match:
        raise Abort(f"FIRMWARE_VERSION not found in {CONFIG_H}")
    return match.group(2)


def set_version(config_text: str, version: str) -> str:
    return VERSION_RE.sub(lambda m: m.group(1) + version + m.group(3), config_text, count=1)


def check_note(note: str) -> str | None:
    """Returns why the note is unusable, or None."""
    note = note.strip()
    if not note:
        return "The note is empty."
    if "\n" in note:
        return "Use a single line."
    if len(note) > NOTE_MAX_CHARS:
        return f"Keep it to {NOTE_MAX_CHARS} characters (this is {len(note)})."
    return None


def set_note(notes_text: str, version: str, note: str) -> str:
    notes = json.loads(notes_text or "{}")
    notes[version] = note.strip()
    ordered = dict(sorted(notes.items(), key=lambda item: parse_version(item[0]) or (0, 0, 0), reverse=True))
    return json.dumps(ordered, indent=2, ensure_ascii=False) + "\n"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def commits_since_version(version: str) -> tuple[str | None, list[str]]:
    """Commits after the one that set FIRMWARE_VERSION to |version|."""
    since = git("log", "-1", "--format=%H", f'-SFIRMWARE_VERSION[] = "{version}"', "--", CONFIG_H).strip()
    if since:
        return since, git("log", "--no-merges", "--format=%h %s", f"{since}..HEAD").splitlines()
    # The version was never committed: show recent history instead.
    return None, git("log", "--no-merges", "--format=%h %s", "-n", "30", "HEAD").splitlines()


def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        raise Abort("No input.")
    return answer or (default or "")


def confirm(prompt: str, default: bool = True) -> bool:
    answer = ask(f"{prompt} ({'Y/n' if default else 'y/N'})").lower()
    return default if not answer else answer in ("y", "yes")


def choose_version(current: str) -> str:
    proposed = next_minor(current)
    while True:
        version = ask("New version", proposed)
        parsed = parse_version(version)
        if not parsed:
            print("  Use major.minor.patch, for example 1.2.0.")
        elif parsed <= parse_version(current):
            print(f"  It must be newer than {current}.")
        else:
            return version


def write_note(version: str, existing: str | None) -> str:
    print("\nRelease note: one line, at most 160 characters, shown to parents as written.")
    print("Write it yourself; describe what changes for the parent, not the code.")
    while True:
        note = ask(f"Note for {version}", existing)
        problem = check_note(note)
        if problem:
            print(f"  {problem}")
            continue
        print(f'\n  Parents will see: "Version {version}: {note.strip()}"')
        if confirm("Use this note?"):
            return note.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-build", action="store_true", help="skip the PlatformIO build")
    args = parser.parse_args()
    try:
        config_path = ROOT / CONFIG_H
        notes_path = ROOT / NOTES
        config_text = config_path.read_text()
        current = current_version(config_text)

        dirty = [line for line in git("status", "--porcelain").splitlines() if line.strip()]
        if dirty:
            print(f"Note: {len(dirty)} uncommitted change(s); they will be part of this build.")

        print(f"Current firmware version: {current}")
        since, commits = commits_since_version(current)
        where = (f"since {since[:9]} (set version {current})" if since
                 else f"(no commit sets {current} yet; showing the last 30)")
        print(f"\nCommits {where}:")
        for line in commits or ["  (none)"]:
            print(f"  {line}")
        if not commits and not confirm("\nNo new commits. Prepare a release anyway?", default=False):
            return 1

        version = choose_version(current)
        notes_text = notes_path.read_text() if notes_path.exists() else "{}"
        note = write_note(version, json.loads(notes_text or "{}").get(version))

        print(f"\nThis will set FIRMWARE_VERSION to {version} in {CONFIG_H}")
        print(f"and add the note to {NOTES}.")
        if not confirm("Continue?"):
            return 1
        config_path.write_text(set_version(config_text, version))
        notes_path.write_text(set_note(notes_text, version, note))
        print("Updated both files.")

        if not args.no_build:
            print("\nBuilding the production firmware...")
            pio = os.environ.get("PIO", str(ROOT / ".venv/bin/pio"))  # the Makefile passes its own
            subprocess.run([pio, "run", "-d", str(ROOT / "firmware/esp32"), "-e", "sweetyaar"], check=True)
            image = ROOT / "firmware/esp32/.pio/build/sweetyaar/firmware.bin"
            print(f"Built {image.relative_to(ROOT)} ({image.stat().st_size} bytes).")

        print(f"""
Next steps for {version}:
  1. Try it on your own doll (approved remote, macOS Terminal):
       make ota-update
     or by cable:
       make flash
  2. Commit the version and note, for example:
       git commit -am "Prepare firmware {version}"
  3. When it works, publish it to parents:
       make release-firmware
     then commit app/public/firmware and push to main.""")
        return 0
    except (Abort, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(f"\ncreate_published_firmware: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
