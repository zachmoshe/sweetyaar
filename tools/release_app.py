#!/usr/bin/env python3
"""
Release the parent app, and the firmware when it changed, interactively.

    make release-app

  1. Finds the last release tag (app-vN; fw-v1.2.0 for firmware) and lists the
     commits since then that matter: firmware/esp32/ (firmware), app/ and
     docs/ (app). Commits that only touch tools, workflows and the like are
     ignored: they stay on main but need no release.
  2. If the firmware changed, asks whether to release it too; the app and
     firmware are coupled (BLE contract), so declining requires confirming the
     app works with the published firmware, and the app's MIN_FIRMWARE_VERSION
     must not exceed the firmware that will be live. If yes: proposes
     the next version, drafts the release note with `claude -p` (you edit or
     accept it; type your own when Claude is unavailable), writes Config.h and
     release-notes.json, builds the production image, and waits while you
     validate it on your doll.
  3. Checks the parents' guide (app/public/parents_user_guide.pdf) against this
     release's changes with `claude -p`: contradictions the changes caused, and
     new features it does not mention. Contradictions and
     missing features stop the release unless you approve; you can open a Claude session with them to fix the guide.
     Then runs the host tests, archives the firmware ELF, writes
     app/public/firmware/, bumps CACHE_VERSION, makes the release commit and
     tags it (app-vN, plus fw-vX.Y.Z for firmware).
  4. Prints the git push command. Nothing leaves your machine until you run it;
     pushing the app-vN tag is what deploys (.github/workflows/pages.yml).

`make release-app-dry-run` goes through the same questions and prints the plan
without changing, building or publishing anything.

If you stop after the build (not validated yet), the version and note stay in
the working tree; run the command again to continue.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

try:
    import readline  # lets the draft note be edited in place
except ImportError:
    readline = None

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import release_firmware as rf  # noqa: E402  image checks, manifest, ELF archive, CACHE_VERSION bump

ROOT = pathlib.Path(os.environ.get("SWEETYAAR_ROOT", pathlib.Path(__file__).resolve().parent.parent))
CONFIG_H = "firmware/esp32/src/Config.h"
NOTES = "firmware/release-notes.json"
SERVICE_WORKER = "app/public/sw.js"
FIRMWARE_OUT = "app/public/firmware"
FIRMWARE_PATHS = ("firmware/esp32/",)  # only commits under it change the image
APP_PATHS = ("app/", "docs/")          # what users see; everything else needs no release
NOTE_MAX_CHARS = rf.NOTE_MAX_CHARS
VERSION_RE = re.compile(r'(FIRMWARE_VERSION\[\]\s*=\s*")(\d+\.\d+\.\d+)(")')
CACHE_RE = re.compile(r'const CACHE_VERSION = "sweetyaar-parent-v(\d+)";')
CLAUDE = os.environ.get("SWEETYAAR_CLAUDE", "claude")
GUIDE = "app/public/parents_user_guide.pdf"
# What a parent can see or do; the guide is checked against what changed in these.
GUIDE_DIFF_PATHS = ("firmware/esp32/src", "firmware/release-notes.json", "app/public/index.html",
                    "app/public/ble-connect.js", "docs/engineering/firmware.md",
                    "docs/engineering/mobile-app.md", "docs/engineering/studio.md")


class Abort(Exception):
    pass


# --- versions and notes -------------------------------------------------------

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


def cache_number(sw_text: str) -> int:
    match = CACHE_RE.search(sw_text)
    if not match:
        raise Abort(f"CACHE_VERSION not found in {SERVICE_WORKER}")
    return int(match.group(1))


def min_firmware(index_text: str) -> str:
    """The oldest firmware the app can control (MIN_FIRMWARE_VERSION in index.html)."""
    match = re.search(r'const MIN_FIRMWARE_VERSION = "(\d+\.\d+\.\d+)";', index_text)
    if not match:
        raise Abort("MIN_FIRMWARE_VERSION not found in app/public/index.html")
    return match.group(1)


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


def note_prompt(commits: list[str], previous_notes: list[str]) -> str:
    examples = "\n".join(f"- {note}" for note in previous_notes) or "- (none yet)"
    changes = "\n".join(f"- {line}" for line in commits)
    return f"""Write the release note for a firmware update of a children's audio toy.
Parents read it in their phone app when the update is offered.

Rules:
- One line, at most 100 characters, plain text, no quotes, no version number.
- Start with the kind of update, then a colon: "Stability update: ...",
  "Feature update: ...", "Diagnostics update: ...".
- Say what changes for the parent in everyday words. No code terms, no detail.
- Output only the note.

Earlier notes, for style:
{examples}

Firmware commits in this release:
{changes}
"""


def draft_note(commits: list[str], previous_notes: list[str], run=subprocess.run) -> tuple[str | None, str]:
    """Returns (draft, why not). The draft is a suggestion; a person approves it."""
    if not shutil.which(CLAUDE):
        return None, f"`{CLAUDE}` is not installed"
    try:
        result = run([CLAUDE, "-p", "--tools", "", "--no-session-persistence"],
                     input=note_prompt(commits, previous_notes), capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, f"`{CLAUDE}` failed ({error})"
    if result.returncode:
        return None, f"`{CLAUDE}` failed: {(result.stderr or result.stdout).strip()[:200]}"
    note = result.stdout.strip().strip('"“”').strip()
    problem = check_note(note)
    return (None, f"the draft was unusable ({problem})") if problem else (note, "")


# --- git ----------------------------------------------------------------------

def git(*args: str, check: bool = True) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=check, capture_output=True, text=True).stdout


def is_ancestor(older: str, newer: str) -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", older, newer], cwd=ROOT).returncode == 0


def tags(pattern: str, key) -> list[str]:
    found = git("tag", "--list", pattern, "--merged", "HEAD").split()
    return sorted(found, key=key)


def last_firmware_tag() -> str | None:
    found = tags("fw-v[0-9]*", lambda tag: parse_version(tag.removeprefix("fw-v")) or (0, 0, 0))
    return found[-1] if found else None


def last_app_tag() -> str | None:
    found = tags("app-v[0-9]*", lambda tag: int(tag.removeprefix("app-v")))
    return found[-1] if found else None


def app_baseline(firmware_tag: str | None, app_tag: str | None) -> str:
    """The latest release of either kind; firmware releases carry both tags."""
    if firmware_tag and app_tag:
        return app_tag if is_ancestor(firmware_tag, app_tag) else firmware_tag
    baseline = app_tag or firmware_tag
    if not baseline:
        raise Abort("No release tag found. Tag the last published release first, "
                    "for example: git tag -a fw-v1.2.0 <commit> -m 'Firmware 1.2.0'")
    return baseline


def classify(paths: list[str]) -> set[str]:
    kinds = set()
    if any(path.startswith(FIRMWARE_PATHS) for path in paths):
        kinds.add("firmware")
    if any(path.startswith(APP_PATHS) for path in paths):
        kinds.add("app")
    return kinds


def commits_since(base: str) -> list[tuple[str, set[str]]]:
    """(one-line commit, kinds) for each commit after |base|, oldest first."""
    out = git("log", "--reverse", "--no-merges", "--name-only", "--format=%x1e%h %s", f"{base}..HEAD")
    commits = []
    for chunk in out.split("\x1e")[1:]:
        lines = [line for line in chunk.splitlines() if line.strip()]
        commits.append((lines[0], classify(lines[1:])))
    return commits


def git_commit_id() -> str:
    return git("describe", "--always", "--dirty", "--abbrev=40").strip() or "unknown"


# --- prompts ------------------------------------------------------------------

def paint(text: str, code: str) -> str:
    """ANSI color for a terminal; plain text when piped or NO_COLOR is set."""
    if sys.stdout.isatty() and "NO_COLOR" not in os.environ:
        return f"\033[{code}m{text}\033[0m"
    return text


def tag_cell(label: str, on: bool, color: str) -> str:
    return paint(label, color) if on else " " * len(label)


def ask(prompt: str, default: str | None = None, prefill: bool = False) -> str:
    """Asks one question. With prefill the default is typed into the line, so it can be edited, not rewritten."""
    editable = prefill and bool(default) and sys.stdin.isatty()
    if editable:
        editable = prefill_line(default)
    suffix = f" [{default}]" if default and not editable else ""
    try:
        answer = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        raise Abort("No input.")
    finally:
        if editable and readline is not None:
            readline.set_startup_hook()
    return answer or (default or "")


def prefill_line(text: str) -> bool:
    """Puts text on the next input() line, ready to edit. Returns False when this terminal cannot."""
    if readline is not None and "libedit" not in (readline.__doc__ or ""):
        readline.set_startup_hook(lambda: readline.insert_text(text))
        return True
    try:  # macOS's libedit has no startup hook: type the text into the terminal's input queue instead
        import fcntl
        import termios
        for byte in text.encode():
            fcntl.ioctl(sys.stdin.fileno(), termios.TIOCSTI, bytes([byte]))
        return True
    except (ImportError, OSError):
        return False


def confirm(prompt: str, default: bool = True) -> bool:
    answer = ask(f"{prompt} ({'Y/n' if default else 'y/N'})").lower()
    return default if not answer else answer in ("y", "yes")


def choose_version(current: str) -> str:
    proposed = next_minor(current)
    while True:
        version = ask("New firmware version", proposed)
        parsed = parse_version(version)
        if not parsed:
            print("  Use major.minor.patch, for example 1.3.0.")
        elif parsed <= parse_version(current):
            print(f"  It must be newer than {current}.")
        else:
            return version


def write_note(version: str, existing: str | None, commits: list[str], previous: list[str]) -> str:
    print("\nRelease note: one line, at most 160 characters, shown to parents as written.")
    default = existing
    if not existing:
        print("Asking Claude for a draft...")
        draft, why_not = draft_note(commits, previous)
        if draft:
            default = draft
            print("  Draft ready. It is filled in below: press Enter to accept it, or edit it first.")
        else:
            print(f"  No draft: {why_not}. Write the note yourself; describe what changes for the parent.")
    while True:
        note = ask(f"Note for {version}", default, prefill=True)
        problem = check_note(note)
        if problem:
            print(f"  {problem}")
            continue
        print(f'\n  Parents will see: "Version {version}: {note.strip()}"')
        if confirm("Use this note?"):
            return note.strip()
        default = note


# --- steps --------------------------------------------------------------------

def prepare_firmware(args, firmware_tag: str, commits: list[str]) -> tuple[str, str] | None:
    """Sets the version and note, builds, waits for validation. Returns (version, note) or None."""
    config_path, notes_path = ROOT / CONFIG_H, ROOT / NOTES
    config_text = config_path.read_text()
    notes_text = notes_path.read_text() if notes_path.exists() else "{}"
    notes = json.loads(notes_text or "{}")
    published = firmware_tag.removeprefix("fw-v")
    prepared = current_version(config_text)

    if parse_version(prepared) > parse_version(published):
        version = prepared
        note = notes.get(version, "")
        print(f"\nFirmware {version} is already prepared in the working tree; continuing with it.")
        if check_note(note):
            note = write_note(version, None, commits, list(notes.values())[:3])
            if not args.dry_run:
                notes_path.write_text(set_note(notes_text, version, note))
    else:
        version = choose_version(published)
        note = write_note(version, notes.get(version), commits, list(notes.values())[:3])
        if args.dry_run:
            print(f"(dry run) would set FIRMWARE_VERSION to {version} and save the note; no file was changed.")
        else:
            config_path.write_text(set_version(config_text, version))
            notes_path.write_text(set_note(notes_text, version, note))
            print(f"Set FIRMWARE_VERSION to {version} and saved the note.")

    if args.dry_run:
        print(f"(dry run) would build the production firmware, then wait while you validate {version} on your doll.")
        return version, note
    if not args.no_build:
        print("\nBuilding the production firmware...")
        pio = os.environ.get("PIO", str(ROOT / ".venv/bin/pio"))
        subprocess.run([pio, "run", "-d", str(ROOT / "firmware/esp32"), "-e", "sweetyaar"], check=True)
    print(f"""
Validate {version} on your own doll before releasing (approved remote, macOS Terminal):
    make ota-update        (an update from the previous release over BLE)
    make flash             (or by cable)""")
    if not confirm("Validated on your doll and ready to release?", default=False):
        print(f"\nStopped. The version and note are saved in the working tree; run `make release-app` to continue.")
        return None
    return version, note


def run_tests() -> None:
    print("\nRunning the host tests...")
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-m", "not firmware"], cwd=ROOT)
    if result.returncode:
        raise Abort("The host tests failed; nothing was released.")


def publish_firmware(version: str, note: str) -> None:
    """Checks and archives the build, then writes app/public/firmware/. Raises Abort on any problem."""
    images, elfs = {}, {}
    for board in rf.BOARDS:
        build = ROOT / "firmware/esp32/.pio/build" / board
        images[board] = (build / "firmware.bin").read_bytes()
        elfs[board] = (build / "firmware.elf").read_bytes()
    try:
        for board, image in images.items():
            rf.check_image(board, image, version)
            print(rf.archive_elf(board, version, image, elfs[board], git_commit_id()))
        rf.build_release(images, version, note, ROOT / FIRMWARE_OUT)
    except rf.ReleaseError as error:
        raise Abort(str(error))


# --- parents' guide check -----------------------------------------------------

def guide_prompt(work: pathlib.Path) -> str:
    return f"""GUIDE CHECK. You are checking the parents' user guide of a children's audio toy (SweetYaar)
before a release. Work read-only.

Files (already prepared):
- {work}/guide.txt: the guide's text, with "--- page N ---" markers.
- {work}/changes.diff: the git diff of the parent-visible code and specs in this release.
- {work}/commits.txt: the commits in this release.
The current code is in the repository you are in (firmware/esp32/src, app/public/index.html).

Report two lists, only about what THIS release changed (ignore older problems in the guide):
1. contradictions: guide statements, pictures or table rows that these changes made wrong or
   misleading for a parent: button gestures, status-LED behavior, timings, screen and setting names,
   defaults, update, Bedtime and Quiet time flows. Major ones only; no wording, style or typos.
   Verify each against the current code (Read/Grep) before reporting it. Give each a short
   "subject" (the topic, such as "Speaker name in the phone's Bluetooth list"); items on the same
   subject share exactly the same subject text and are reported together. For each item say what the
   guide says or shows ("guide": page and a short quote or description) and what the code actually
   does ("actual").
2. missing: new parent-visible FEATURES added by these commits that the guide does not mention at
   all. Features only: not fixes, internals or tuning. Describe the feature in a sentence or two
   ("feature") and say where in the guide it could be mentioned ("where_to_mention": a new chapter
   or section, or the page, table or sentence whose wording would change).

Reply with ONLY this JSON, empty lists when there is nothing:
{{"contradictions": [{{"subject": "topic", "guide": "p.N: what the guide says or shows", "actual": "what really happens now", "where": "file:line", "commit": "abc1234"}}],
  "missing": [{{"feature": "what it is and does", "where_to_mention": "where in the guide", "commit": "abc1234"}}]}}
"""


def extract_guide(pdf: pathlib.Path, out: pathlib.Path) -> None:
    try:
        import pypdf
    except ImportError:
        raise Abort("pypdf is not installed; run `make setup`.")
    reader = pypdf.PdfReader(pdf)
    out.write_text("\n".join(f"--- page {n} ---\n{page.extract_text()}" for n, page in enumerate(reader.pages, 1)))


def parse_guide_reply(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.S)
    try:
        data = json.loads(match.group(0)) if match else None
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return {key: [item for item in (data.get(key) or []) if isinstance(item, dict)]
            for key in ("contradictions", "missing")}


def check_guide(base: str, commit_lines: list[str], run=subprocess.run) -> tuple[dict | None, str]:
    """Asks Claude to compare the guide with this release's changes. Returns (findings, why not)."""
    pdf = ROOT / GUIDE
    if not pdf.exists():
        raise Abort(f"{GUIDE} not found.")
    diff = git("diff", base, "HEAD", "--", *GUIDE_DIFF_PATHS)
    if not diff.strip():
        return {"contradictions": [], "missing": []}, "no parent-visible changes in this release"
    if not shutil.which(CLAUDE):
        return None, f"`{CLAUDE}` is not installed"
    work = pathlib.Path(tempfile.mkdtemp(prefix="sweetyaar-guide-", dir="/tmp"))
    try:
        extract_guide(pdf, work / "guide.txt")
        (work / "changes.diff").write_text(diff)
        (work / "commits.txt").write_text("\n".join(commit_lines) + "\n")
        result = run([CLAUDE, "-p", "--tools", "Read,Grep,Glob", "--no-session-persistence"], cwd=ROOT,
                     input=guide_prompt(work), capture_output=True, text=True, timeout=1200)
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, f"`{CLAUDE}` failed ({error})"
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if result.returncode:
        return None, f"`{CLAUDE}` failed: {(result.stderr or result.stdout).strip()[:200]}"
    findings = parse_guide_reply(result.stdout)
    return (findings, "") if findings else (None, "its reply was not the expected JSON")


def findings_text(findings: dict) -> str:
    """The report: contradictions grouped by subject, then the missing features."""
    lines = ["CONTRADICTIONS (grouped by subject)"]
    subjects: dict[str, list[dict]] = {}
    for item in findings["contradictions"]:
        subjects.setdefault(str(item.get("subject") or "Other"), []).append(item)
    for number, (subject, items) in enumerate(subjects.items(), 1):
        lines.append(f"\n{chr(64 + number) if number < 27 else number}. {subject}")
        for item in items:
            lines.append(f"   - Guide {item.get('guide', '?')}\n     Actually: {item.get('actual', '?')} "
                         f"({item.get('where', '?')}, commit {item.get('commit', '?')})")
    if not subjects:
        lines.append("  none")
    lines.append("\nMISSING FEATURES")
    for number, item in enumerate(findings["missing"], 1):
        lines.append(f"{number}. {item.get('feature', '?')}\n   Could go: {item.get('where_to_mention', '?')} "
                     f"(commit {item.get('commit', '?')})")
    if not findings["missing"]:
        lines.append("  none")
    return "\n".join(lines)


def fix_prompt(findings: dict) -> str:
    return (f"The parents' guide ({GUIDE}) does not match what the next SweetYaar release changes. Please help me "
            f"fix it. The check found this:\n\n{findings_text(findings)}\n\nThe guide is a ReportLab-generated PDF "
            f"whose source is not in the repo; its text can be read with pypdf (a dev dependency). Check each item "
            f"against the code first. Then your first message must be this report: the missing features (describe "
            f"each and say where you think it belongs: a new chapter, or a wording change somewhere) and the "
            f"contradictions grouped by subject (what the PDF says or shows, and what the code does). I will "
            f"comment on each, and we then decide together how to fix or ignore it. Do not edit the guide or its "
            f"source before I approve the wording.")


def guide_gate(args, base: str, commit_lines: list[str]) -> bool:
    """Checks the guide against the release; returns False when the release should stop."""
    print("\nChecking the parents' guide against this release's changes (read-only, a few minutes)...")
    findings, why_not = check_guide(base, commit_lines)
    if findings is None:
        print(f"  Could not check: {why_not}.")
        return True if args.dry_run else confirm("Have you checked the guide yourself, and is it up to date?", default=False)
    if not findings["contradictions"] and not findings["missing"]:
        print(f"  No mismatches ({why_not})." if why_not else "  The guide matches this release's changes.")
        return True
    print("\n" + findings_text(findings))
    answer = ask("\nOpen a Claude session with these findings to fix the guide? (y = open, c = copy them, n = no)", "n").lower()
    if answer in ("y", "yes"):
        subprocess.run([CLAUDE, fix_prompt(findings)], cwd=ROOT)
        print("\nFix the guide, commit it, then run `make release-app` again.")
        return False
    if answer == "c":
        copied = shutil.which("pbcopy") and subprocess.run(["pbcopy"], input=fix_prompt(findings), text=True).returncode == 0
        print("\nCopied to the clipboard; paste it into a new session." if copied else "\nNo clipboard tool found:\n" + fix_prompt(findings))
        return False
    return True if args.dry_run else confirm("Release anyway?", default=False)


def release_commit(number: int, version: str | None, note: str | None) -> list[str]:
    """Commits the release and tags it. Returns the tags."""
    paths = [SERVICE_WORKER]
    title = f"Release app-v{number}"
    new_tags = [f"app-v{number}"]
    if version:
        paths += [CONFIG_H, NOTES, FIRMWARE_OUT]
        title += f" with firmware {version}"
        new_tags.append(f"fw-v{version}")
    for tag in new_tags:
        if git("tag", "--list", tag).strip():
            raise Abort(f"Tag {tag} already exists.")
    git("add", "--all", "--", *paths)
    message = title + (f"\n\n{note}" if note else "")
    git("commit", "-m", message)
    for tag in new_tags:
        git("tag", "-a", tag, "-m", title)
    return new_tags


def check_repo(allow_prepared: bool) -> None:
    branch = git("rev-parse", "--abbrev-ref", "HEAD").strip()
    if branch != "main":
        raise Abort(f"Releases are made from main (this is {branch}).")
    changes = [line for line in git("status", "--porcelain", "--untracked-files=no").splitlines() if line.strip()]
    allowed = (CONFIG_H, NOTES) if allow_prepared else ()
    stray = [line for line in changes if not line[3:] in allowed]
    if stray:
        raise Abort("Commit or discard these changes first:\n  " + "\n  ".join(stray))
    if git("remote").strip():
        subprocess.run(["git", "fetch", "--quiet", "--tags", "origin"], cwd=ROOT, capture_output=True)
        behind = git("rev-list", "--count", "HEAD..origin/main", check=False).strip()
        if behind not in ("", "0"):
            raise Abort(f"main is {behind} commit(s) behind origin/main; pull first.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-build", action="store_true", help="skip the PlatformIO build")
    parser.add_argument("--skip-tests", action="store_true", help="do not run the host tests")
    parser.add_argument("--dry-run", action="store_true",
                        help="go through the questions and show the plan; change, build and publish nothing")
    args = parser.parse_args()
    try:
        firmware_tag, app_tag = last_firmware_tag(), last_app_tag()
        base = app_baseline(firmware_tag, app_tag)
        prepared = firmware_tag is not None and parse_version(
            current_version((ROOT / CONFIG_H).read_text())) > parse_version(firmware_tag.removeprefix("fw-v"))
        check_repo(allow_prepared=prepared)

        commits = commits_since(base)
        relevant = [(line, kinds) for line, kinds in commits if kinds]
        ignored = len(commits) - len(relevant)
        print(f"Last release: {base}. Commits since: {len(commits)} ({ignored} need no release).")
        firmware_base = firmware_tag or base
        firmware_commits = [line for line, kinds in commits_since(firmware_base) if "firmware" in kinds]
        print(f"\n  {paint('FW ', '2')} {paint('APP', '2')}  commit")
        for line, kinds in relevant:
            print(f"  {tag_cell('FW ', 'firmware' in kinds, '1;35')} {tag_cell('APP', 'app' in kinds, '1;32')}  {line}")

        release_firmware = False
        if prepared:
            release_firmware = True
        elif firmware_commits:
            print(f"\nThe firmware changed since {firmware_tag} ({len(firmware_commits)} commit(s), marked FW above).")
            release_firmware = confirm("Release firmware too?")
        if not release_firmware and not any("app" in kinds for _, kinds in relevant):
            print("\nNothing to release.")
            return 0
        if not release_firmware and firmware_commits:
            # The app is deployed to every parent at once; toys update only when a parent accepts.
            print(f"\nThe app on main may rely on those firmware commits (new BLE characteristics, commands).\n"
                  f"Parents' toys would keep running firmware {firmware_tag.removeprefix("fw-v")} with the new app.")
            if not confirm(f"Is this app fully compatible with firmware {firmware_tag.removeprefix("fw-v")}?", default=False):
                print("\nRelease the firmware too (run again and answer yes), or finish the compatibility work first.")
                return 1

        version = note = None
        if release_firmware:
            outcome = prepare_firmware(args, firmware_tag, firmware_commits)
            if outcome is None:
                return 1
            version, note = outcome
        live = version or (firmware_tag.removeprefix("fw-v") if firmware_tag else "0.0.0")
        required = min_firmware((ROOT / "app/public/index.html").read_text())
        if parse_version(required) > parse_version(live):
            raise Abort(f"The app requires firmware {required} or newer (MIN_FIRMWARE_VERSION), "
                        f"but firmware {live} would be live. Release the firmware too.")
        sw_path = ROOT / SERVICE_WORKER
        number = cache_number(sw_path.read_text()) + 1
        what = f"app-v{number}" + (f" with firmware {version}" if version else " (firmware unchanged)")
        if not guide_gate(args, base, [line for line, _ in relevant]):
            print("\nStopped; nothing was committed, tagged or uploaded.")
            return 1
        if args.dry_run:
            steps = ["run the host tests"]
            if version:
                steps += ["check the firmware image and archive its ELF", "write app/public/firmware/ (image and manifest)"]
            steps += [f"bump CACHE_VERSION to {number}", f"commit \"Release {what.replace(' (firmware unchanged)', '')}\"",
                      f"tag it {' and '.join([f'app-v{number}'] + ([f'fw-v{version}'] if version else []))}"]
            print(f"\n(dry run) Release {what}. It would:")
            for step in steps:
                print(f"  - {step}")
            print("Nothing was changed, built, archived, committed or tagged.")
            return 0
        if not args.skip_tests:
            run_tests()
        print(f"\nThis will create release {what}.")
        if not confirm("Continue?"):
            print("\nStopped; nothing was committed, tagged or uploaded.")
            if version:
                print(f"The version and note are still in the working tree. To discard them:\n"
                      f"    git checkout -- {CONFIG_H} {NOTES}")
            return 1
        if version:
            publish_firmware(version, note)
        sw_path.write_text(rf.bump_cache_version(sw_path.read_text()))
        new_tags = release_commit(number, version, note)
    except (Abort, rf.ReleaseError, FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(f"\nrelease_app: {error}", file=sys.stderr)
        return 1

    live_firmware = version or (firmware_tag.removeprefix("fw-v") if firmware_tag else "unchanged")
    print(f"""
Released locally: {' and '.join(new_tags)}. After the push, live: app-v{number}, firmware {live_firmware}.
Pushing app-v{number} deploys the app (and the firmware update, if any) to parents:

    git push origin main {' '.join(new_tags)}
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
