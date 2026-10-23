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
    for name, frames in (("ready", 31899), ("error", 27831), ("pairing", 27762), ("battery", 33675), ("charger", 21807)):
        with wave.open(str(root / f"{name}.wav"), "rb") as sound:
            assert sound.getparams()[:4] == (1, 2, 44100, frames)
            assert sound.getcomptype() == "NONE"
            pcm = struct.unpack(f"<{frames}h", sound.readframes(frames))
            assert pcm[0] == pcm[-1] == 0
            assert pcm[1] != 0 and pcm[-2] != 0


def active_pcm(path):
    with wave.open(str(path), "rb") as sound:
        pcm = struct.unpack(f"<{sound.getnframes()}h", sound.readframes(sound.getnframes()))
    start = next(i for i, value in enumerate(pcm) if value)
    end = len(pcm) - next(i for i, value in enumerate(reversed(pcm)) if value)
    return pcm[start:end]


def test_battery_cue_is_the_selected_first_gentle_nudge(repo_root):
    selected = repo_root / "content/system-sounds/battery-options/03-gentle-nudge-medium.wav"
    embedded = repo_root / "firmware/esp32/assets/sounds/battery.wav"
    assert active_pcm(embedded) == active_pcm(selected)


def test_sunrise_preview_preserves_selected_audio(repo_root):
    selected = repo_root / "content/system-sounds/charger-happy-options/01-sunrise.wav"
    preview = repo_root / "content/system-sounds/trimmed/charger-sunrise.wav"
    assert active_pcm(preview) == active_pcm(selected)


def test_charger_uses_selected_trimmed_sunrise(repo_root):
    selected = repo_root / "content/system-sounds/trimmed/charger-sunrise.wav"
    embedded = repo_root / "firmware/esp32/assets/sounds/charger.wav"
    assert embedded.read_bytes() == selected.read_bytes()
