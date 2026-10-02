"""Exercise the production BT-to-local transition with the installed WAV pipeline."""

import shutil
import struct
import wave

import pytest

from helpers import run_checked
from test_settings_runtime import function_source
from test_catalog_pagination import production_function


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
    json_include = audio_include.parents[1] / "ArduinoJson/src"
    src = repo_root / "firmware/esp32/src"
    main = (src / "main.cpp").read_text()
    state = (src / "StateMachine.h").read_text()
    start = state.index("enum class State {")
    (tmp_path / "audio_state.inc").write_text(state[start:state.index("};", start) + 2])
    (tmp_path / "audio_handoff.inc").write_text(
        function_source(main, "setupI2S") + "\n" +
        function_source(main, "handleStateEntry")
    )
    # Use the actual player class and methods, exposing internals only in this
    # temporary test header so file selection needs no directory/SPI emulation.
    (tmp_path / "WavPlayer.h").write_text((src / "WavPlayer.h").read_text().replace("private:", "public:"))
    player = (src / "WavPlayer.cpp").read_text()
    constructor = next(line for line in player.splitlines() if line.startswith("WavPlayer::WavPlayer("))
    (tmp_path / "wav_player.inc").write_text(constructor + "\n" + "\n".join(
        function_source(player, name) for name in (
            "WavPlayer::openFile", "WavPlayer::loop", "WavPlayer::stop", "WavPlayer::teardown",
        )
    ))
    catalog = (src / "ContentCatalog.cpp").read_text()
    (tmp_path / "wav_inspect.inc").write_text("\n".join(
        production_function(catalog, name) for name in ("le16", "le32", "readFully", "inspectWav")
    ))
    wav_paths = []
    for channels in (1, 2):
        wav_path = tmp_path / f"local-{channels}.wav"
        wav_paths.append(wav_path)
        with wave.open(str(wav_path), "wb") as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(2)
            wav.setframerate(44100)
            samples = [((frame * 137 + channel * 379) % 60001) - 30000
                       for frame in range(4097) for channel in range(channels)]
            wav.writeframes(struct.pack(f"<{len(samples)}h", *samples))
        if channels == 1:
            # Odd-size padded metadata, a header beyond 200 bytes, and trailing
            # metadata must not lose the first PCM block or become speaker data.
            data = wav_path.read_bytes()
            junk = b"JUNK" + struct.pack("<I", 257) + b"x" * 257 + b"\0"
            data = data[:36] + junk + data[36:] + b"LIST\x04\0\0\0TEST"
            data = data[:4] + struct.pack("<I", len(data) - 8) + data[8:]
            wav_path.write_bytes(data)
    exe = tmp_path / "audio_handoff"
    run_checked([
        compiler, "-std=c++17", "-DIS_DESKTOP_WITH_TIME_ONLY",
        "-I", tmp_path, "-I", audio_include, "-I", src, "-I", json_include,
        "-I", repo_root / "tests/native_stubs", "-I", repo_root / "tests/json_file_stubs",
        repo_root / "tests/audio_handoff_native_test.cpp", "-o", exe,
    ])
    result = run_checked([exe, *wav_paths])
    assert "audio handoff tests passed" in result.stdout
