"""`make release-app`: what it asks, what it refuses, and what it creates, in a throwaway repo."""

import hashlib
import importlib.util
import json
import os
import pathlib
import subprocess
import sys

import pytest

from test_ota_update import fake_image

SW = 'const CACHE_VERSION = "sweetyaar-parent-v50";\n'
INDEX = 'const MIN_FIRMWARE_VERSION = "1.0.0";\n'
CONFIG = 'static constexpr char FIRMWARE_VERSION[] = "1.0.0";\n'
ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def load(repo_root):
    spec = importlib.util.spec_from_file_location("release_app", repo_root / "tools/release_app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_helpers(repo_root):
    tool = load(repo_root)
    assert tool.next_minor("1.2.0") == "1.3.0" and tool.next_minor("2.9.4") == "2.10.0"
    assert tool.current_version(CONFIG) == "1.0.0"
    assert tool.set_version(CONFIG, "1.1.0") == CONFIG.replace("1.0.0", "1.1.0")
    assert tool.cache_number(SW) == 50
    assert tool.min_firmware(INDEX) == "1.0.0"
    assert tool.check_note("Stability update: steadier Bluetooth.") is None
    assert tool.check_note("  ") and tool.check_note("a\nb") and tool.check_note("x" * 161)
    notes = json.loads(tool.set_note('{"1.0.0": "First."}', "1.10.0", " Newest. "))
    assert list(notes) == ["1.10.0", "1.0.0"] and notes["1.10.0"] == "Newest."
    assert tool.classify(["firmware/esp32/src/A.cpp", "docs/x.md"]) == {"firmware", "app"}
    assert tool.classify(["app/public/index.html"]) == {"app"}
    assert tool.classify(["tools/x.py", ".github/workflows/a.yml", "Makefile", "hardware/a.kicad_pcb"]) == set()
    # The current app and firmware parse.
    assert tool.min_firmware((repo_root / "app/public/index.html").read_text())
    assert tool.cache_number((repo_root / "app/public/sw.js").read_text())


def test_note_draft_comes_from_claude_and_is_checked(repo_root, monkeypatch):
    tool = load(repo_root)
    monkeypatch.setattr(tool.shutil, "which", lambda name: "/bin/" + name)
    done = lambda out, code=0: (lambda *a, **k: subprocess.CompletedProcess(a, code, out, "boom"))
    prompt = {}

    def run(args, input, **kw):
        prompt["text"] = input
        return subprocess.CompletedProcess(args, 0, ' "Stability update: steadier Bluetooth." \n', "")

    draft, _ = tool.draft_note(["abc Fix reconnects"], ["Old note."], run)
    assert draft == "Stability update: steadier Bluetooth."
    assert "abc Fix reconnects" in prompt["text"] and "Old note." in prompt["text"]
    assert tool.draft_note([], [], done("x" * 200))[0] is None      # too long: unusable
    assert "failed" in tool.draft_note([], [], done("", 1))[1]      # CLI error
    monkeypatch.setattr(tool.shutil, "which", lambda name: None)
    assert "not installed" in tool.draft_note([], [], done("x"))[1]  # no CLI


class Repo:
    def __init__(self, path):
        self.path = path
        path.mkdir(parents=True)
        self.env = {**os.environ, **ENV, "SWEETYAAR_ROOT": str(path)}
        self.git("init", "-q", "-b", "main")
        self.bin = path.parent / (path.name + "-bin")
        self.bin.mkdir()
        self.claude_log, self.clipboard = path.parent / "claude.log", path.parent / "clipboard.txt"
        self.set_guide({"mismatches": [], "not_covered": []})
        claude = self.bin / "claude"
        claude.write_text(
            '#!/bin/sh\n[ "$1" = "-p" ] || { echo "$@" >> "$CLAUDE_LOG"; exit 0; }\ninput=$(cat)\n'
            'case "$input" in *"GUIDE CHECK"*) cat "$GUIDE_REPLY";;\n'
            '*) echo "Stability update: steadier Bluetooth reconnects.";; esac\n')
        pbcopy = self.bin / "pbcopy"
        pbcopy.write_text('#!/bin/sh\ncat > "$CLIPBOARD"\n')
        for script in (claude, pbcopy):
            script.chmod(0o755)
        self.env.update({"PATH": f"{self.bin}:{os.environ['PATH']}", "SWEETYAAR_CLAUDE": str(claude),
                         "CLAUDE_LOG": str(self.claude_log), "CLIPBOARD": str(self.clipboard),
                         "GUIDE_REPLY": str(self.bin / "guide.json")})
        self.write_guide_pdf()
        for name, text in {"app/public/sw.js": SW, "app/public/index.html": INDEX,
                           "firmware/esp32/src/Config.h": CONFIG,
                           "firmware/release-notes.json": '{"1.0.0": "First."}\n'}.items():
            self.write(name, text)
        self.commit("Initial release")
        self.git("tag", "-a", "fw-v1.0.0", "-m", "Firmware 1.0.0")

    def set_guide(self, reply):
        (self.bin / "guide.json").write_text(json.dumps(reply))

    def write_guide_pdf(self):
        import pypdf
        writer = pypdf.PdfWriter()
        writer.add_blank_page(width=200, height=200)
        (self.path / "app/public").mkdir(parents=True, exist_ok=True)
        with open(self.path / "app/public/parents_user_guide.pdf", "wb") as out:
            writer.write(out)

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.path, check=True, capture_output=True,
                              text=True, env=self.env).stdout

    def write(self, name, text):
        file = self.path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text)

    def commit(self, message):
        self.git("add", ".")
        self.git("commit", "-qm", message)

    def run(self, answers, *flags, **env):
        return subprocess.run([sys.executable, pathlib.Path(__file__).parent.parent / "tools/release_app.py",
                               "--skip-tests", *flags], input="\n".join(answers) + "\n", capture_output=True,
                              text=True, env={**self.env, **env})


@pytest.fixture
def repo(tmp_path):
    return Repo(tmp_path / "repo")


def test_nothing_to_release_for_tool_only_commits(repo):
    repo.write("tools/x.py", "print()")
    repo.commit("Tweak a tool")
    result = repo.run([])
    assert result.returncode == 0 and "Nothing to release." in result.stdout
    assert "app-v" not in repo.git("tag")


def test_app_only_release(repo):
    repo.write("tools/x.py", "print()")
    repo.commit("Tweak a tool")
    repo.write("app/public/index.html", INDEX + "// new screen\n")
    repo.commit("Add a screen")
    result = repo.run(["y"])
    assert result.returncode == 0, result.stderr + result.stdout
    out = result.stdout
    assert "Last release: fw-v1.0.0" in out and "Add a screen" in out and "Tweak a tool" not in out
    assert "Release firmware too?" not in out
    assert "git push origin main app-v51" in out and "firmware 1.0.0" in out
    assert "sweetyaar-parent-v51" in (repo.path / "app/public/sw.js").read_text()
    assert repo.git("log", "-1", "--format=%s").strip() == "Release app-v51"
    assert repo.git("tag", "--list", "app-v*").split() == ["app-v51"]
    assert repo.git("status", "--porcelain").strip() == ""
    # Released: the next run has nothing new.
    assert "Nothing to release." in repo.run([]).stdout


def test_firmware_change_needs_a_release_or_a_compatibility_promise(repo):
    repo.write("firmware/esp32/src/Ble.cpp", "// new characteristic")
    repo.write("app/public/index.html", INDEX + "// uses it\n")
    repo.commit("Add a characteristic and use it")
    declined = repo.run(["n", "n"])          # no firmware release, app not compatible
    assert declined.returncode == 1 and "Release firmware too?" in declined.stdout
    assert "app-v" not in repo.git("tag")
    promised = repo.run(["n", "y", "y"])     # no firmware release, but compatible
    assert promised.returncode == 0, promised.stderr + promised.stdout
    assert "firmware 1.0.0" in promised.stdout and "git push origin main app-v51" in promised.stdout


def test_app_requiring_newer_firmware_cannot_ship_alone(repo):
    repo.write("app/public/index.html", 'const MIN_FIRMWARE_VERSION = "1.1.0";\n')
    repo.commit("Require firmware 1.1.0")
    result = repo.run(["y"])
    assert result.returncode == 1 and "requires firmware 1.1.0" in result.stderr
    assert "app-v" not in repo.git("tag")


def test_refuses_dirty_tree_and_other_branches(repo):
    repo.write("app/public/index.html", INDEX + "// wip\n")
    result = repo.run([])
    assert result.returncode == 1 and "Commit or discard" in result.stderr
    repo.git("checkout", "-q", "--", ".")
    repo.git("checkout", "-q", "-b", "feature")
    assert "from main" in repo.run([]).stderr


def test_firmware_release(repo, tmp_path):
    repo.write("firmware/esp32/src/Ble.cpp", "// fix")
    repo.write("app/public/index.html", INDEX + "// app\n")
    repo.commit("Fix reconnects")
    # A built production image for 1.1.0 and its ELF, a fake gcloud and a fake claude.
    tool = load(pathlib.Path(__file__).parent.parent)
    elf = b"\x7fELF" + bytes(range(256)) * 4
    image = bytearray(fake_image("1.1.0", "sweetyaar"))
    image[tool.rf.APP_ELF_SHA256] = hashlib.sha256(elf).digest()
    build = repo.path / "firmware/esp32/.pio/build/sweetyaar"
    build.mkdir(parents=True)
    (build / "firmware.bin").write_bytes(bytes(image))
    (build / "firmware.elf").write_bytes(elf)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gcloud = bin_dir / "gcloud"
    gcloud.write_text('#!/bin/sh\n[ "$3" = describe ] && { echo "ERROR: not found: 404" >&2; exit 1; }\n'
                      'echo "$@" >> "$GCLOUD_LOG"\nexit 0\n')
    for script in (gcloud,):
        script.chmod(0o755)
    env = {"PATH": f"{bin_dir}:{repo.env['PATH']}", "GCLOUD_LOG": str(tmp_path / "gcloud.log")}
    # Answers: release firmware, version 1.1.0, accept the draft note, use it, then not validated yet.
    not_validated = repo.run(["", "", "", "y", "n"], "--no-build", **env)
    assert not_validated.returncode == 1 and "run `make release-app` to continue" in not_validated.stdout
    assert 'FIRMWARE_VERSION[] = "1.1.0"' in (repo.path / "firmware/esp32/src/Config.h").read_text()

    # Running again resumes with the saved version and note.
    result = repo.run(["y", "y"], "--no-build", **env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "already prepared" in result.stdout
    manifest = json.loads((repo.path / "app/public/firmware/manifest.json").read_text())
    assert manifest["version"] == "1.1.0" and manifest["notes"] == "Stability update: steadier Bluetooth reconnects."
    assert (repo.path / "app/public/firmware/sweetyaar-1.1.0.bin.z").exists()
    assert "storage cp" in (tmp_path / "gcloud.log").read_text()
    assert repo.git("log", "-1", "--format=%s").strip() == "Release app-v51 with firmware 1.1.0"
    assert sorted(repo.git("tag", "--list", "app-v*", "fw-v1.1.0").split()) == ["app-v51", "fw-v1.1.0"]
    assert "git push origin main app-v51 fw-v1.1.0" in result.stdout and "firmware 1.1.0" in result.stdout
    assert repo.git("status", "--porcelain", "--untracked-files=no").strip() == ""


def test_dry_run_asks_but_changes_nothing(repo):
    repo.write("firmware/esp32/src/Ble.cpp", "// fix")
    repo.write("app/public/index.html", INDEX + "// app\n")
    repo.commit("Fix reconnects")
    head = repo.git("rev-parse", "HEAD")
    result = repo.run(["", "", "Stability update: steadier Bluetooth.", "y"], "--dry-run", SWEETYAAR_CLAUDE="/nonexistent")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "(dry run) would set FIRMWARE_VERSION to 1.1.0" in result.stdout
    assert "Release app-v51 with firmware 1.1.0. It would:" in result.stdout
    assert "tag it app-v51 and fw-v1.1.0" in result.stdout and "Nothing was changed" in result.stdout
    assert repo.git("rev-parse", "HEAD") == head and repo.git("tag", "--list", "app-v*") == ""
    assert repo.git("status", "--porcelain").strip() == ""
    assert 'FIRMWARE_VERSION[] = "1.0.0"' in (repo.path / "firmware/esp32/src/Config.h").read_text()


MISMATCH = {"mismatches": [{"guide": "p.4: 'Hold both buttons for 3 seconds'", "change": "now 5 seconds",
                            "where": "firmware/esp32/src/Config.h:12", "commit": "abc1234"}],
            "not_covered": [{"feature": "Bedtime fade-out", "commit": "def5678"}]}


def app_change(repo):
    repo.write("app/public/index.html", INDEX + "// new screen\n")
    repo.commit("Add a screen")


def test_guide_without_mismatches_is_silent(repo):
    app_change(repo)
    result = repo.run(["y"])
    assert result.returncode == 0, result.stderr + result.stdout
    assert "The guide matches this release's changes." in result.stdout


def test_new_features_alone_block_too(repo):
    app_change(repo)
    repo.set_guide({"mismatches": [], "not_covered": MISMATCH["not_covered"]})
    refused = repo.run(["n", "n"])     # no chat, do not release anyway
    assert refused.returncode == 1 and "Bedtime fade-out" in refused.stdout and "app-v" not in repo.git("tag")
    assert repo.run(["n", "y", "y"]).returncode == 0   # approved


def test_mismatch_can_open_a_claude_session_to_fix_it(repo):
    app_change(repo)
    repo.set_guide(MISMATCH)
    result = repo.run(["y"])           # open a Claude session
    assert result.returncode == 1 and "run `make release-app` again" in result.stdout
    assert "Hold both buttons for 3 seconds" in result.stdout
    prompt = repo.claude_log.read_text()
    assert "now 5 seconds" in prompt and "Bedtime fade-out" in prompt
    assert "app-v" not in repo.git("tag")


def test_mismatch_can_be_copied_or_overridden(repo):
    app_change(repo)
    repo.set_guide(MISMATCH)
    copied = repo.run(["c"])
    assert copied.returncode == 1 and "Copied to the clipboard" in copied.stdout
    assert "now 5 seconds" in repo.clipboard.read_text()
    refused = repo.run(["n", "n"])     # no chat, do not release anyway
    assert refused.returncode == 1 and "app-v" not in repo.git("tag")
    approved = repo.run(["n", "y", "y"])  # no chat, release anyway, continue
    assert approved.returncode == 0, approved.stderr + approved.stdout
    assert repo.git("tag", "--list", "app-v*").split() == ["app-v51"]


def test_unavailable_check_needs_your_word(repo):
    app_change(repo)
    env = {"SWEETYAAR_CLAUDE": "/nonexistent"}
    refused = repo.run(["n"], **env)
    assert refused.returncode == 1 and "Could not check" in refused.stdout and "app-v" not in repo.git("tag")
    assert repo.run(["y", "y"], **env).returncode == 0   # checked it myself, continue


def test_a_missing_guide_stops_the_release(repo):
    app_change(repo)
    (repo.path / "app/public/parents_user_guide.pdf").unlink()
    repo.git("add", "-A")
    repo.git("commit", "-qm", "Lose the guide")
    result = repo.run(["y"])
    assert result.returncode == 1 and "parents_user_guide.pdf not found" in result.stderr


def test_dry_run_checks_the_guide_too(repo):
    app_change(repo)
    repo.set_guide(MISMATCH)
    result = repo.run(["n"], "--dry-run")   # mismatch found, no chat; a dry run never asks to release anyway
    assert result.returncode == 0, result.stderr + result.stdout
    assert "Hold both buttons for 3 seconds" in result.stdout and "Nothing was changed" in result.stdout
