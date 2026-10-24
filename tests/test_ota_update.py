"""Firmware-update protocol and release tooling, without a radio or a toy."""

import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
import zlib

import pytest

from helpers import run_checked


def test_ota_session_protocol(repo_root, tmp_path):
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("A C++ compiler is required.")
    src = repo_root / "firmware/esp32/src"
    exe = tmp_path / "ota_session"
    run_checked([compiler, "-std=c++17", "-Wall", "-Wextra", "-I", src,
                 repo_root / "tests/ota_session_native_test.cpp", src / "OtaSession.cpp", "-o", exe])
    assert "OTA session tests passed" in run_checked([exe]).stdout


def load_release_tool(repo_root):
    spec = importlib.util.spec_from_file_location("release_firmware", repo_root / "tools/release_firmware.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_image(version, board, size=4000):
    body = bytes((i * 13) & 255 for i in range(size))
    return b"\xe9" + body + f"{version}\0".encode() + f"{board}\0".encode()


def test_release_version_matches_app_minimum(repo_root):
    tool = load_release_tool(repo_root)
    version = tool.firmware_version((repo_root / "firmware/esp32/src/Config.h").read_text())
    app = (repo_root / "app/public/index.html").read_text()
    minimum = re.search(r'const MIN_FIRMWARE_VERSION = "([\d.]+)";', app).group(1)
    as_tuple = lambda text: tuple(int(part) for part in text.split("."))
    # Firmware the app itself would call too old could never be released.
    assert as_tuple(minimum) <= as_tuple(version)
    assert isinstance(json.loads((repo_root / "firmware/release-notes.json").read_text()), dict)


def test_release_notes_must_be_written_for_the_version(repo_root):
    tool = load_release_tool(repo_root)
    assert tool.release_note({"1.2.0": "  Bedtime songs fade out gently. "}, "1.2.0") == "Bedtime songs fade out gently."
    for notes in ({}, {"1.2.0": ""}, {"1.2.0": "   "}, {"1.2.0": 5}, {"1.2.0": "two\nlines"},
                  {"1.2.0": "x" * 161}, {"1.1.0": "Older release"}):
        with pytest.raises(tool.ReleaseError):
            tool.release_note(notes, "1.2.0")


def test_release_publishes_only_the_production_board(repo_root):
    tool = load_release_tool(repo_root)
    assert tool.BOARDS == ("sweetyaar",)
    assert set(tool.ALL_BOARDS) == {"sweetyaar", "sweetyaar-generic"}


def test_release_writes_verified_compressed_images_and_manifest(repo_root, tmp_path):
    tool = load_release_tool(repo_root)
    out = tmp_path / "firmware"
    out.mkdir()
    (out / "sweetyaar-1.0.0.bin.z").write_bytes(b"old")
    (out / "unrelated.txt").write_text("keep")
    images = {board: fake_image("1.2.0", board) for board in tool.BOARDS}
    manifest = tool.build_release(images, "1.2.0", "Bedtime songs fade out gently.", out)
    assert json.loads((out / "manifest.json").read_text()) == manifest
    assert manifest["format"] == 1 and manifest["version"] == "1.2.0"
    assert manifest["notes"] == "Bedtime songs fade out gently."
    for board, image in images.items():
        entry = manifest["images"][board]
        packed = (out / entry["file"]).read_bytes()
        assert entry["file"] == f"{board}-1.2.0.bin.z" and entry["encoding"] == "zlib"
        assert zlib.decompress(packed) == image
        assert entry["size"] == len(image) and entry["encodedSize"] == len(packed)
        assert entry["sha256"] == hashlib.sha256(image).hexdigest()
        assert entry["fileSha256"] == hashlib.sha256(packed).hexdigest()
    assert not (out / "sweetyaar-1.0.0.bin.z").exists()  # superseded image removed
    assert (out / "unrelated.txt").exists()


@pytest.mark.parametrize("image, problem", [
    (b"\x00" + fake_image("1.2.0", "sweetyaar")[1:], "not an ESP32 app image"),
    (fake_image("1.1.0", "sweetyaar"), "not version 1.2.0"),
    (fake_image("1.2.0", "sweetyaar-generic"), "another board"),
    (fake_image("1.2.0", "sweetyaar") + b"sweetyaar-generic\0", "another board"),
    (fake_image("1.2.0", "sweetyaar-generic") + b"sweetyaar\0", "another board"),
    (fake_image("1.2.0", "sweetyaar", size=0x330000), "does not fit"),
])
def test_release_rejects_wrong_or_stale_images(repo_root, tmp_path, image, problem):
    tool = load_release_tool(repo_root)
    good = fake_image("1.2.0", "sweetyaar-generic")
    with pytest.raises(tool.ReleaseError, match=problem):
        tool.build_release({"sweetyaar-generic": good, "sweetyaar": image}, "1.2.0", "Note.", tmp_path)
    assert list(tmp_path.iterdir()) == []  # nothing written, even for the valid board


def load_tool(repo_root, name):
    spec = importlib.util.spec_from_file_location(name, repo_root / f"tools/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_bumps_the_app_cache_version(repo_root):
    tool = load_release_tool(repo_root)
    assert tool.bump_cache_version('const CACHE_VERSION = "sweetyaar-parent-v50";\n') == \
        'const CACHE_VERSION = "sweetyaar-parent-v51";\n'
    with pytest.raises(tool.ReleaseError):
        tool.bump_cache_version("no version here")
    tool.bump_cache_version((repo_root / "app/public/sw.js").read_text())  # current file parses


def test_prepare_release_helpers(repo_root):
    tool = load_tool(repo_root, "create_published_firmware")
    assert tool.next_minor("1.0.0") == "1.1.0" and tool.next_minor("2.9.4") == "2.10.0"
    config = 'x\nstatic constexpr char FIRMWARE_VERSION[] = "1.0.0";\ny\n'
    assert tool.current_version(config) == "1.0.0"
    assert tool.set_version(config, "1.1.0") == config.replace("1.0.0", "1.1.0")
    assert tool.check_note("Bedtime songs fade out gently.") is None
    assert tool.check_note("  ") and tool.check_note("a\nb") and tool.check_note("x" * 161)
    notes = json.loads(tool.set_note('{"1.0.0": "First."}', "1.10.0", " Newest. "))
    assert list(notes) == ["1.10.0", "1.0.0"] and notes["1.10.0"] == "Newest."
    assert json.loads(tool.set_note(json.dumps(notes), "1.10.0", "Fixed."))["1.10.0"] == "Fixed."


def test_prepare_release_interactive_run(repo_root, tmp_path):
    import subprocess
    repo = tmp_path / "repo"
    (repo / "firmware/esp32/src").mkdir(parents=True)
    config = repo / "firmware/esp32/src/Config.h"
    config.write_text('static constexpr char FIRMWARE_VERSION[] = "1.0.0";\n')
    (repo / "firmware/release-notes.json").write_text('{"1.0.0": "First release."}\n')

    def git(*args):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True,
                       env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})

    git("init", "-q")
    git("add", ".")
    git("commit", "-qm", "Initial work")
    (repo / "a.txt").write_text("feature")
    git("add", ".")
    git("commit", "-qm", "Add bedtime fade-out")
    answers = "\n".join([
        "0.9.0",                            # rejected: older than current
        "",                                 # accept the proposed 1.1.0
        "",                                 # empty note is rejected
        "Bedtime songs fade out gently.",
        "y",                                # use this note
        "y",                                # write the files
    ]) + "\n"
    result = subprocess.run([sys.executable, repo_root / "tools/create_published_firmware.py", "--no-build"],
                            input=answers, capture_output=True, text=True,
                            env={**os.environ, "SWEETYAAR_ROOT": str(repo)})
    assert result.returncode == 0, result.stderr + result.stdout
    out = result.stdout
    assert "Current firmware version: 1.0.0" in out
    assert "Add bedtime fade-out" in out and "Initial work" not in out  # only since 1.0.0
    assert "New version [1.1.0]" in out and "must be newer than 1.0.0" in out
    assert "The note is empty." in out
    assert 'Parents will see: "Version 1.1.0: Bedtime songs fade out gently."' in out
    assert "make release-firmware" in out
    assert 'FIRMWARE_VERSION[] = "1.1.0"' in config.read_text()
    notes = json.loads((repo / "firmware/release-notes.json").read_text())
    assert notes == {"1.1.0": "Bedtime songs fade out gently.", "1.0.0": "First release."}
