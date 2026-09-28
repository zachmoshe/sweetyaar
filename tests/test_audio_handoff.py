"""Exercise the production BT-to-local transition with the installed WAV pipeline."""

import shutil
import wave

import pytest

from helpers import run_checked
from test_settings_runtime import function_source


def test_bluetooth_disconnect_restores_local_audio_format(repo_root, tmp_path):
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("A C++ compiler is required for audio handoff tests.")
    audio_include = next((
        base / "firmware/esp32/.pio/libdeps/sweetyaar/audio-tools/src"
        for base in (repo_root, *repo_root.parents)
        if (base / "firmware/esp32/.pio/libdeps/sweetyaar/audio-tools/src/AudioTools.h").exists()
    ), None)
    assert audio_include, "Run make build to install audio-tools."
    src = repo_root / "firmware/esp32/src"
    main = (src / "main.cpp").read_text()
    state = (src / "StateMachine.h").read_text()
    start = state.index("enum class State {")
    (tmp_path / "audio_state.inc").write_text(state[start:state.index("};", start) + 2])
    (tmp_path / "audio_handoff.inc").write_text(
        function_source(main, "setupI2S") + "\n" +
        function_source(main, "handleStateEntry")
    )
    wav_path = tmp_path / "local.wav"
    with wave.open(str(wav_path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(44100)
        wav.writeframes(b"\0" * (44100 * 4))
    exe = tmp_path / "audio_handoff"
    run_checked([
        compiler, "-std=c++17", "-DIS_DESKTOP_WITH_TIME_ONLY",
        "-I", audio_include, "-I", src, "-I", tmp_path,
        repo_root / "tests/audio_handoff_native_test.cpp", "-o", exe,
    ])
    result = run_checked([exe, wav_path])
    assert "audio handoff tests passed" in result.stdout
