"""Check template conversion and the format of the embedded firmware sounds."""

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
    # Cues are embedded in flash and mixed into the I2S stream: mono 16-bit
    # 44.1 kHz PCM, starting and ending on silence so they never click.
    sounds = sorted((repo_root / "firmware/esp32/assets/sounds").glob("*.wav"))
    assert sounds
    for path in sounds:
        with wave.open(str(path), "rb") as sound:
            frames = sound.getnframes()
            assert sound.getparams()[:3] == (1, 2, 44100), path.name
            assert sound.getcomptype() == "NONE", path.name
            assert frames > 2, path.name
            pcm = struct.unpack(f"<{frames}h", sound.readframes(frames))
        assert pcm[0] == pcm[-1] == 0, path.name
