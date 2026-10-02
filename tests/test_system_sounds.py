"""Execute flash cue rendering and production startup/error/pairing events."""

import shutil
import struct
import wave

from helpers import run_checked
from test_settings_runtime import function_source


def test_flash_cues_and_audio_ownership(repo_root, tmp_path):
    compiler = shutil.which("c++")
    assert compiler, "A C++ compiler is required."
    audio_include = next((
        base / "firmware/esp32/.pio/libdeps/sweetyaar/audio-tools/src"
        for base in (repo_root, *repo_root.parents)
        if (base / "firmware/esp32/.pio/libdeps/sweetyaar/audio-tools/src/AudioTools.h").exists()
    ), None)
    assert audio_include, "Run make build to install audio-tools."
    src = repo_root / "firmware/esp32/src"
    main = (src / "main.cpp").read_text()
    (tmp_path / "sound_events.inc").write_text("\n".join(
        function_source(main, name) for name in ("reportSystemError", "finishSystemSoundStartup")
    ))
    (tmp_path / "pairing_events.inc").write_text(function_source(main, "pollBluetoothPairing"))
    fixture = tmp_path / "samples.wav"
    with wave.open(str(fixture), "wb") as wav:
        wav.setparams((1, 2, 44100, 0, "NONE", "not compressed"))
        wav.writeframes(struct.pack("<8h", -32768, 32767, 0, 10000, -10000, 1, -1, 1234))
    exe = tmp_path / "system_sounds"
    run_checked([
        compiler, "-std=c++17", "-pthread", "-DIS_DESKTOP_WITH_TIME_ONLY",
        "-I", tmp_path, "-I", audio_include, "-I", src,
        repo_root / "tests/system_sounds_native_test.cpp",
        "-o", exe,
    ])
    assets = repo_root / "firmware/esp32/assets/sounds"
    result = run_checked([exe, fixture, *(assets / f"{name}.wav" for name in ("ready", "error", "pairing"))])
    assert "system sound tests passed" in result.stdout


def test_cue_assets_are_embedded_and_triggers_are_reachable(repo_root):
    # Guard deployment wiring as well as the separately executed renderer/policy.
    src = repo_root / "firmware/esp32/src"
    main = (src / "main.cpp").read_text()
    config = (src.parent / "platformio.ini").read_text()
    assert "board_build.embed_files" in config
    for name in ("ready", "error", "pairing"):
        assert f"assets/sounds/{name}.wav" in config
    setup = function_source(main, "setup")
    assert setup.index("finishSystemSoundStartup();") > setup.index("setupLoopTaskWatchdog();")
    assert "pollBluetoothPairing();" in function_source(main, "loop")
    assert "systemAudio.active()" in function_source(main, "canEnterIdleSleep")
