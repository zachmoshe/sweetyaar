"""The animal-prompt mapping and its ElevenLabs generator (no network)."""
import importlib.util
import json
import wave
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("animal_prompts", ROOT / "content/animal_prompts/generate.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)


def test_mapping_is_complete():
    config = gen.load_config()
    assert len(config["animals"]) == 13
    assert set(config["languages"]) >= {"en", "he", "fr", "ar"}
    for code, lang in config["languages"].items():
        assert set(lang["prompts"]) == set(config["animals"]), code


def test_hebrew_has_niqqud():
    he = gen.load_config()["languages"]["he"]["prompts"]
    for animal, text in he.items():
        assert any("ְ" <= ch <= "ׇ" for ch in text), animal


def test_validation_rejects_a_missing_prompt():
    config = gen.load_config()
    del config["languages"]["en"]["prompts"]["cat"]
    with pytest.raises(gen.ConfigError, match="en: no prompt for cat"):
        gen.validate(config)


def test_language_overrides_merge_over_defaults():
    config = gen.load_config()
    config["languages"]["fr"]["model_id"] = "other"
    config["languages"]["fr"]["voice_settings"] = {"stability": 1.0}
    s = gen.settings_for(config, "fr")
    assert s["model_id"] == "other"
    assert s["voice_settings"]["stability"] == 1.0
    assert s["voice_settings"]["similarity_boost"] == config["defaults"]["voice_settings"]["similarity_boost"]
    assert gen.settings_for(config, "en")["model_id"] == config["defaults"]["model_id"]


def fake_api(calls):
    def http(method, url, key, body=None):
        calls.append((method, url, body))
        if "/v2/voices" in url:
            return json.dumps({"voices": [{"name": "Sunny - Bubbly, Children Narrator", "voice_id": "voiceSunny123456789"},
                                          {"name": "Sunny", "voice_id": "otherSunny123456789"}]}).encode()
        rate = int(url.split("output_format=pcm_")[1]) if "output_format=pcm_" in url else 48000
        return b"\x01\x00" * rate                # one second of 16-bit mono PCM
    return http


def test_run_writes_the_bucket_layout(tmp_path):
    config = gen.load_config()
    calls = []
    done = gen.run(config, tmp_path, ["en"], ["cat", "owl"], "k", http=fake_api(calls), log=lambda *_: None)
    assert done == {"generated": 2, "skipped": 0}
    assert (tmp_path / "ATTRIBUTION.txt").read_text(encoding="utf-8") == config["attribution"] + "\n"
    with wave.open(str(tmp_path / "en/cat.wav")) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 44100)
        assert abs(w.getnframes() - 44100) < 50                          # one second, resampled from 48 kHz
    assert not [c for c in calls if "/v2/voices" in c[1]]       # a voice ID needs no lookup
    tts = [c for c in calls if c[0] == "POST"]
    assert f"/v1/text-to-speech/{config['languages']['en']['voice']}?output_format=pcm_48000" in tts[0][1]
    assert tts[0][2]["text"] == "[childish] [warm] [engaged] How does a cat sound?"
    assert tts[0][2]["model_id"] == config["defaults"]["model_id"]
    # a rerun keeps what is there
    again = gen.run(config, tmp_path, ["en"], ["cat", "owl"], "k", http=fake_api([]), log=lambda *_: None)
    assert again == {"generated": 0, "skipped": 2}


def test_every_language_has_a_voice_id():
    for code, lang in gen.load_config()["languages"].items():
        assert gen.looks_like_id(lang["voice"]), code


def test_a_voice_name_is_looked_up_exactly():
    calls = []
    assert gen.resolve_voice("Sunny – Bubbly, Children Narrator", "k", http=fake_api(calls)) == "voiceSunny123456789"
    assert "/v2/voices?" in calls[0][1]


def test_finish_trims_silence_and_levels(tmp_path):
    import array, math
    rate = 44100
    tone = [int(3000 * math.sin(2 * math.pi * 440 * i / rate)) for i in range(rate // 2)]      # 0.5 s of speech-ish
    x = array.array("h", [0] * rate + tone + [0] * rate)                                    # 1 s silence each side
    path = tmp_path / "x.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(x.tobytes())
    seconds = gen.finish(path, {"trim_threshold_db": -40, "target_rms_db": -20, "peak_db": -1})
    assert 0.5 < seconds < 0.65                                   # 0.5 s tone + 30 ms + 80 ms
    with wave.open(str(path)) as w:
        y = array.array("h", w.readframes(w.getnframes()))
    rms = math.sqrt(sum(v * v for v in y[2000:-5000]) / len(y[2000:-5000]))
    assert abs(20 * math.log10(rms / 32767) - (-20)) < 0.5
    assert max(abs(v) for v in y) <= 32767 * 10 ** (-1 / 20) + 1


def test_a_much_longer_take_is_retaken_with_another_seed(tmp_path):
    config = gen.load_config()
    seeds = []
    def http(method, url, key, body=None):
        seeds.append((body["text"].split()[-1], body.get("seed")))
        repeated = "sound?" in body["text"] and "sheep" in body["text"] and body.get("seed") == 1
        return b"\x01\x00" * 48000 * (3 if repeated else 1)              # the first sheep take "repeats"
    animals = ["cat", "cow", "dog", "duck", "sheep"]
    done = gen.run(config, tmp_path, ["en"], animals, "k", http=http, log=lambda *_: None)
    assert done["retaken"] == 1 and "check" not in done
    assert [s for s in seeds if s[0] == "sound?"][-1:] == [("sound?", 1001)]
    with wave.open(str(tmp_path / "en/sheep.wav")) as w:
        assert w.getnframes() / w.getframerate() < 1.2


def test_a_language_without_a_voice_stops(tmp_path):
    config = gen.load_config()
    config["languages"]["he"]["voice"] = ""
    with pytest.raises(RuntimeError, match="he: no voice"):
        gen.run(config, tmp_path, ["he"], ["cat"], "k", http=fake_api([]), log=lambda *_: None)


def test_an_unknown_voice_name_is_explained():
    with pytest.raises(RuntimeError, match="0 exact matches"):
        gen.resolve_voice("Nobody", "k", http=fake_api([]))


def test_dry_run_needs_no_key(capsys, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    assert gen.main(["--dry-run", "--languages", "he", "--animals", "cow"]) == 0
    assert "he/cow.wav  [childish] [warm] [engaged] אֵיךְ עוֹשָׂה פָּרָה?" in capsys.readouterr().out
