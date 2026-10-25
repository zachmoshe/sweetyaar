"""The animal-sound builder writes only to the folder it is given."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.io import wavfile

from helpers import ROOT

SCRIPT = ROOT / "tools" / "animals" / "build_animals.py"
TEMPLATE = ROOT / "content" / "sd-card-template"


def tree_hash(folder: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(p for p in folder.rglob("*") if p.is_file()):
        h.update(str(f.relative_to(folder)).encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def make_question(path: Path) -> None:
    sr = 44100
    t = np.arange(int(0.6 * sr)) / sr
    tone = 0.3 * np.sin(2 * np.pi * 500 * t) * np.sin(2 * np.pi * 3 * t) ** 2   # voice-band tone burst
    wavfile.write(path, sr, (tone * 32767).astype(np.int16))


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, cwd=ROOT)


def test_builds_into_given_folder_and_leaves_template_untouched(tmp_path):
    questions = tmp_path / "my_questions"
    questions.mkdir()
    make_question(questions / "dog.wav")
    out = tmp_path / "card_animals"
    before = tree_hash(TEMPLATE)

    result = run("default", "--tts", str(questions), "--out", str(out), "--animals", "dog")

    assert result.returncode == 0, result.stdout + result.stderr
    assert (out / "dog.wav").is_file()
    meta = json.loads((out / "metadata.json").read_text())
    assert meta["name"] == "Animals" and meta["disabledSongs"] == []
    assert tree_hash(TEMPLATE) == before


def test_out_folder_never_loses_existing_files(tmp_path):
    questions = tmp_path / "q"
    questions.mkdir()
    make_question(questions / "dog.wav")
    out = tmp_path / "out"
    out.mkdir()
    (out / "keep_me.txt").write_text("mine")

    result = run("default", "--tts", str(questions), "--out", str(out), "--animals", "dog")

    assert result.returncode == 0, result.stdout + result.stderr
    assert (out / "keep_me.txt").read_text() == "mine"


def test_refuses_the_template_folder_as_output(tmp_path):
    questions = tmp_path / "q"
    questions.mkdir()
    make_question(questions / "dog.wav")
    before = tree_hash(TEMPLATE)

    result = run("default", "--tts", str(questions), "--out", str(TEMPLATE / "animals"), "--animals", "dog")

    assert result.returncode != 0
    assert "sd-card-template" in (result.stdout + result.stderr)
    assert tree_hash(TEMPLATE) == before


def test_missing_recordings_folder_is_reported(tmp_path):
    result = run("default", "--tts", str(tmp_path / "nope"), "--out", str(tmp_path / "o"))
    assert result.returncode != 0
    assert "not found" in (result.stdout + result.stderr)
