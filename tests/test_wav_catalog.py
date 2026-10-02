"""Exercise the production WAV admission and duration calculation for both formats."""

import shutil
import struct
import wave

import pytest

from helpers import run_checked
from test_catalog_pagination import production_function


@pytest.fixture(scope="module")
def wav_inspector(repo_root, tmp_path_factory):
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("A C++ compiler is required for WAV catalog tests.")
    json_include = next((
        base / "firmware/esp32/.pio/libdeps/sweetyaar/ArduinoJson/src"
        for base in (repo_root, *repo_root.parents)
        if (base / "firmware/esp32/.pio/libdeps/sweetyaar/ArduinoJson/src/ArduinoJson.h").exists()
    ), None)
    assert json_include, "Run make build to install ArduinoJson."
    build = tmp_path_factory.mktemp("wav_catalog")
    source_dir = repo_root / "firmware/esp32/src"
    source = (source_dir / "ContentCatalog.cpp").read_text()
    (build / "wav_inspect.inc").write_text("\n".join(
        production_function(source, name) for name in ("le16", "le32", "readFully", "inspectWav")
    ))
    exe = build / "wav_catalog"
    run_checked([
        compiler, "-std=c++17", "-I", source_dir,
        "-I", repo_root / "tests/json_file_stubs",
        "-I", repo_root / "tests/native_stubs", "-I", json_include, "-I", build,
        repo_root / "tests/wav_catalog_native_test.cpp", "-o", exe,
    ])
    return exe


@pytest.mark.parametrize("channels,rate,bits,encoding,supported", [
    (1, 44100, 16, 1, True), (2, 44100, 16, 1, True),
    (3, 44100, 16, 1, False), (4, 44100, 16, 1, False),
    (1, 22050, 16, 1, False), (2, 48000, 16, 1, False),
    (1, 44100, 8, 1, False), (2, 44100, 24, 1, False),
    (1, 44100, 32, 3, False),
])
def test_wav_admission_and_duration(wav_inspector, tmp_path, channels, rate, bits, encoding, supported):
    path = tmp_path / "sound.wav"
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(bits // 8)
        output.setframerate(rate)
        output.writeframes(b"\0" * ((rate // 4) * channels * (bits // 8)))
    if encoding != 1:
        data = bytearray(path.read_bytes())
        data[20:22] = encoding.to_bytes(2, "little")
        path.write_bytes(data)
    valid, accepted, reported_channels, duration = map(int, run_checked([wav_inspector, path]).stdout.split())
    assert valid == 1
    assert accepted == supported
    assert reported_channels == channels
    if supported:
        assert duration == 250  # mono must not appear to play at twice the speed


@pytest.mark.parametrize("channels", [1, 2])
def test_wav_rejects_partial_pcm_frames(wav_inspector, tmp_path, channels):
    path = tmp_path / "partial.wav"
    with wave.open(str(path), "wb") as output:
        output.setparams((channels, 2, 44100, 0, "NONE", "not compressed"))
        output.writeframes(b"\0" * (channels * 2))
    data = bytearray(path.read_bytes())
    data += b"\x01\0"  # incomplete frame, followed by RIFF padding
    data[40:44] = struct.pack("<I", channels * 2 + 1)
    data[4:8] = struct.pack("<I", len(data) - 8)
    path.write_bytes(data)
    valid, accepted, _, _ = map(int, run_checked([wav_inspector, path]).stdout.split())
    assert valid == 1
    assert accepted == 0
