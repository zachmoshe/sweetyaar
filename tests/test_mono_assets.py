"""Check template conversion and the selected firmware sound asset contract."""

import importlib.util
import struct
import wave

import pytest


@pytest.mark.parametrize("channels,samples,expected", [
    (2, [32767, 32767, -32768, -32768, 30000, -30000, 100, 200], [32767, -32768, 0, 150]),
    (1, [32767, -32768, 0, 1234], [32767, -32768, 0, 1234]),
])
def test_mono_conversion_preserves_timing_and_mix(repo_root, tmp_path, channels, samples, expected):
    spec = importlib.util.spec_from_file_location("mono_convert", repo_root / "tools/convert_wavs_to_mono.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source, target = tmp_path / "source.wav", tmp_path / "target.wav"
    with wave.open(str(source), "wb") as output:
        output.setparams((channels, 2, 44100, 0, "NONE", "not compressed"))
        output.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    original = source.read_bytes()
    module.convert(source, target)
    assert source.read_bytes() == original
    with wave.open(str(target), "rb") as output:
        assert output.getparams()[:4] == (1, 2, 44100, len(expected))
        assert struct.unpack(f"<{len(expected)}h", output.readframes(len(expected))) == tuple(expected)
    with pytest.raises(FileExistsError):
        module.convert(source, target)


def test_system_sounds_are_compact_pcm(repo_root):
    root = repo_root / "firmware/esp32/assets/sounds"
    for name, frames in (("ready", 33869), ("error", 29635), ("pairing", 29635)):
        with wave.open(str(root / f"{name}.wav"), "rb") as sound:
            assert sound.getparams()[:4] == (1, 2, 44100, frames)
            assert sound.getcomptype() == "NONE"
