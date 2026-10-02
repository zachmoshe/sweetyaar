"""Check byte-accurate mono expansion and stereo passthrough with real volume code."""

import shutil

import pytest

from helpers import run_checked


def test_wav_pcm_conversion(repo_root, tmp_path):
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("A C++ compiler is required for WAV conversion tests.")
    audio_include = next((
        base / "firmware/esp32/.pio/libdeps/sweetyaar/audio-tools/src"
        for base in (repo_root, *repo_root.parents)
        if (base / "firmware/esp32/.pio/libdeps/sweetyaar/audio-tools/src/AudioTools.h").exists()
    ), None)
    assert audio_include, "Run make build to install audio-tools."
    exe = tmp_path / "wav_pcm"
    run_checked([
        compiler, "-std=c++17", "-DIS_DESKTOP_WITH_TIME_ONLY",
        "-I", audio_include, "-I", repo_root / "firmware/esp32/src",
        repo_root / "tests/wav_pcm_native_test.cpp", "-o", exe,
    ])
    assert "WAV mono/stereo PCM tests passed" in run_checked([exe]).stdout
