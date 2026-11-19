#!/usr/bin/env python3
"""Generate the spoken animal questions with ElevenLabs.

Reads prompts.json (next to this file) and writes a folder that mirrors the
bucket's animal-prompts/ folder:

    <out>/ATTRIBUTION.txt
    <out>/<lang>/<animal>.wav      44.1 kHz mono 16-bit PCM

The API key comes from the ELEVENLABS_API_KEY environment variable. Nothing is
uploaded; the script prints the gcloud command for that. Python standard
library plus ffmpeg, which converts what ElevenLabs returns ('output_format',
set for our plan) to 44.1 kHz WAV. Each file is then trimmed of the silence at
both ends and levelled to the same loudness ('trim_threshold_db',
'target_rms_db', 'peak_db').

    ELEVENLABS_API_KEY=... python3 content/animal_prompts/generate.py --out /tmp/animal-prompts
    ... --languages he,fr            only these languages
    ... --animals cat,dog            only these animals
    ... --force                      regenerate files that already exist
    ... --dry-run                    print what would be generated; no key, no calls
"""
from __future__ import annotations

import argparse
import array
import math
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_CONFIG = HERE / "prompts.json"
API = "https://api.elevenlabs.io"
BUCKET_PREFIX = "gs://sweetyaar-studio-resources/animal-prompts/"


class ConfigError(ValueError):
    pass



# ---------------------------------------------------------------- config

def load_config(path: Path = DEFAULT_CONFIG) -> dict:
    with open(path, encoding="utf-8") as f:
        config = json.load(f)
    validate(config)
    return config


def validate(config: dict) -> None:
    animals = config.get("animals")
    if not animals or len(set(animals)) != len(animals):
        raise ConfigError("'animals' must be a non-empty list without duplicates")
    if not config.get("attribution", "").strip() or "\n" in config["attribution"]:
        raise ConfigError("'attribution' must be one non-empty line")
    languages = config.get("languages") or {}
    if not languages:
        raise ConfigError("no languages")
    for code, lang in languages.items():
        prompts = lang.get("prompts") or {}
        missing = [a for a in animals if not str(prompts.get(a, "")).strip()]
        extra = [a for a in prompts if a not in animals]
        if missing:
            raise ConfigError(f"{code}: no prompt for {', '.join(missing)}")
        if extra:
            raise ConfigError(f"{code}: prompts for unknown animals {', '.join(extra)}")
        if "voice" not in lang:
            raise ConfigError(f"{code}: no 'voice' key")
    fmt = config.get("defaults", {}).get("output_format", "")
    if not fmt.startswith(("pcm_", "mp3_")):
        raise ConfigError("'output_format' must be an ElevenLabs pcm_* or mp3_* format")


def settings_for(config: dict, code: str) -> dict:
    """The defaults merged with the language's own overrides."""
    merged = json.loads(json.dumps(config.get("defaults", {})))
    lang = config["languages"][code]
    for key in ("model_id", "tags", "sample_rate", "language_code", "output_format", "seed"):
        if key in lang:
            merged[key] = lang[key]
    if "voice_settings" in lang:
        merged.setdefault("voice_settings", {}).update(lang["voice_settings"])
    return merged


def spoken_text(settings: dict, prompt: str) -> str:
    tags = (settings.get("tags") or "").strip()
    return f"{tags} {prompt}".strip() if tags else prompt


# ---------------------------------------------------------------- API

def request(method: str, url: str, key: str, body: dict | None = None, retries: int = 5) -> bytes:
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, method=method, headers={
            "xi-api-key": key, "Content-Type": "application/json", "Accept": "*/*"})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read()
        except urllib.error.HTTPError as err:
            detail = err.read().decode(errors="replace")[:400]
            if err.code in (429, 500, 502, 503, 504) and attempt + 1 < retries:
                time.sleep(2 ** attempt * 3)
                continue
            raise RuntimeError(f"{method} {url.split('?')[0]} -> HTTP {err.code}: {detail}") from None
    raise RuntimeError("unreachable")


def looks_like_id(voice: str) -> bool:
    return len(voice) >= 16 and voice.isalnum()


def resolve_voice(voice: str, key: str, http=request) -> str:
    """A voice ID, or the exact name of a voice in the account's My Voices."""
    if looks_like_id(voice):
        return voice
    url = f"{API}/v2/voices?" + urllib.parse.urlencode({"search": voice, "page_size": 100})
    found = json.loads(http("GET", url, key)).get("voices", [])
    norm = lambda s: " ".join(s.replace("–", "-").replace("—", "-").lower().split())
    matches = [v["voice_id"] for v in found if norm(v.get("name", "")) == norm(voice)]
    if len(matches) != 1:
        names = ", ".join(v.get("name", "?") for v in found[:8]) or "none"
        raise RuntimeError(f"voice '{voice}': {len(matches)} exact matches in My Voices (found: {names}). "
                           "Add it from the Voice Library to My Voices, or put its voice ID in prompts.json.")
    return matches[0]


def synthesize(text: str, voice_id: str, settings: dict, key: str, http=request, seed: int | None = None) -> bytes:
    url = f"{API}/v1/text-to-speech/{voice_id}?output_format={settings['output_format']}"
    body = {"text": text, "model_id": settings["model_id"], "voice_settings": settings.get("voice_settings", {})}
    if settings.get("language_code"):
        body["language_code"] = settings["language_code"]
    if seed is not None:
        body["seed"] = seed
    return http("POST", url, key, body)


def to_wav(audio: bytes, fmt: str, path: Path, rate: int) -> float:
    """Convert ElevenLabs' pcm_<rate> (16-bit mono) or mp3 bytes to a mono 16-bit WAV at |rate|.
    Returns the duration in seconds."""
    if len(audio) < 2000:
        raise RuntimeError(f"{path.name}: only {len(audio)} bytes of audio came back")
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is needed to convert to 44.1 kHz WAV (brew install ffmpeg)")
    source = ["-f", "s16le", "-ar", fmt.split("_")[1], "-ac", "1"] if fmt.startswith("pcm_") else ["-f", "mp3"]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".tmp.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *source, "-i", "-", "-ac", "1", "-ar", str(rate),
                    "-c:a", "pcm_s16le", "-map_metadata", "-1", str(tmp)], input=audio, check=True)
    tmp.replace(path)
    return (path.stat().st_size - 44) / 2 / rate


def finish(path: Path, settings: dict) -> float:
    """Trim the silence at both ends and level the speech, in place. Returns the new duration.

    trim_threshold_db: a 10 ms window quieter than this (relative to the clip's peak) counts as silence;
    target_rms_db: loudness of the speech (RMS of its non-silent windows, dBFS);
    peak_db: the gain is lowered if needed so no sample goes above this."""
    with wave.open(str(path)) as w:
        rate = w.getframerate()
        x = array.array("h", w.readframes(w.getnframes()))
    if not x:
        return 0.0
    peak = max(1, max(abs(v) for v in x))
    win = rate // 100
    level = [max(abs(v) for v in x[i:i + win]) for i in range(0, len(x), win)]
    floor = peak * 10 ** (settings.get("trim_threshold_db", -40) / 20)
    loud = [i for i, v in enumerate(level) if v >= floor]
    start = max(0, loud[0] * win - int(0.03 * rate))                 # keep 30 ms before the first sound
    end = min(len(x), (loud[-1] + 1) * win + int(0.08 * rate))      # and 80 ms after the last
    x = x[start:end]
    voiced = [x[i:i + win] for i in range(0, len(x), win) if max((abs(v) for v in x[i:i + win]), default=0) >= floor]
    rms = math.sqrt(sum(v * v for c in voiced for v in c) / max(1, sum(len(c) for c in voiced))) or 1.0
    gain = 10 ** (settings.get("target_rms_db", -20) / 20) * 32767 / rms
    gain = min(gain, 10 ** (settings.get("peak_db", -1) / 20) * 32767 / max(abs(v) for v in x))
    fade = min(len(x) // 2, int(0.005 * rate))                       # 5 ms fades: no clicks at the cuts
    out = array.array("h", (round(v * gain * min(1.0, i / fade if fade else 1, (len(x) - 1 - i) / fade if fade else 1))
                            for i, v in enumerate(x)))
    tmp = path.with_name(path.stem + ".tmp.wav")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(out.tobytes())
    tmp.replace(path)
    return len(out) / rate


# ---------------------------------------------------------------- run

def plan(config: dict, languages: list[str], animals: list[str]) -> list[tuple[str, str, str]]:
    jobs = []
    for code in languages:
        settings = settings_for(config, code)
        for animal in animals:
            jobs.append((code, animal, spoken_text(settings, config["languages"][code]["prompts"][animal])))
    return jobs


def run(config: dict, out: Path, languages: list[str], animals: list[str], key: str,
        force: bool = False, http=request, log=print, convert=to_wav) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    (out / "ATTRIBUTION.txt").write_text(config["attribution"].strip() + "\n", encoding="utf-8")
    done = {"generated": 0, "skipped": 0}
    for code in languages:
        lang = config["languages"][code]
        if not lang.get("voice", "").strip():
            raise RuntimeError(f"{code}: no voice set in prompts.json")
        settings = settings_for(config, code)
        voice_id = resolve_voice(lang["voice"], key, http)
        log(f"{code}: voice '{lang['voice']}' ({voice_id}), model {settings['model_id']}")
        made = {}
        for animal in animals:
            path = out / code / f"{animal}.wav"
            if path.exists() and not force:
                done["skipped"] += 1
                continue
            seconds = take(lang["prompts"][animal], voice_id, settings, key, http, convert, path, settings.get("seed"))
            made[animal] = seconds
            done["generated"] += 1
            log(f"  {code}/{animal}.wav  {seconds:.1f} s  {spoken_text(settings, lang['prompts'][animal])}")
        retake_long(code, lang, made, out, voice_id, settings, key, http, convert, log, done)
    return done


def take(prompt, voice_id, settings, key, http, convert, path, seed) -> float:
    audio = synthesize(spoken_text(settings, prompt), voice_id, settings, key, http, seed)
    convert(audio, settings["output_format"], path, settings.get("sample_rate", 44100))
    return finish(path, settings)


def retake_long(code, lang, made, out, voice_id, settings, key, http, convert, log, done) -> None:
    """The model sometimes repeats the start of a sentence ("How does a, how does a sheep..."). Such a
    take is far longer than the language's other questions, so it is redone with other seeds. With fewer
    than 4 new files in the language, the files already in its folder count for the comparison."""
    lengths = dict(made)
    for p in (out / code).glob("*.wav"):
        if p.stem not in lengths:
            with wave.open(str(p)) as w:
                lengths[p.stem] = w.getnframes() / w.getframerate()
    if len(lengths) < 4:
        return
    median = sorted(lengths.values())[len(lengths) // 2]
    limit = max(median * settings.get("max_length_ratio", 1.4), median + 0.5)
    base = settings.get("seed") or 0
    for animal, seconds in made.items():
        tries = 0
        while seconds > limit and tries < settings.get("max_retakes", 3):
            tries += 1
            log(f"  {code}/{animal}.wav  {seconds:.1f} s is much longer than the others ({median:.1f} s); retaking")
            seconds = take(lang["prompts"][animal], voice_id, settings, key, http, convert,
                           out / code / f"{animal}.wav", base + 1000 * tries)
            done["retaken"] = done.get("retaken", 0) + 1
        if seconds > limit:
            log(f"  {code}/{animal}.wav  still {seconds:.1f} s after {tries} retakes: listen to it")
            done.setdefault("check", []).append(f"{code}/{animal}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("animal-prompts-out"), help="output folder (created if needed)")
    ap.add_argument("--languages", help="comma-separated language codes (default: all in prompts.json)")
    ap.add_argument("--animals", help="comma-separated animals (default: all)")
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--force", action="store_true", help="regenerate files that already exist")
    ap.add_argument("--dry-run", action="store_true", help="print the texts that would be generated and stop")
    args = ap.parse_args(argv)

    config = load_config(args.config)
    pick = lambda arg, allowed, what: [x.strip() for x in arg.split(",") if x.strip()] if arg else list(allowed)
    languages = pick(args.languages, config["languages"], "language")
    animals = pick(args.animals, config["animals"], "animal")
    unknown = [l for l in languages if l not in config["languages"]] + [a for a in animals if a not in config["animals"]]
    if unknown:
        ap.error(f"unknown: {', '.join(unknown)}")

    if args.dry_run:
        for code, animal, text in plan(config, languages, animals):
            print(f"{code}/{animal}.wav  {text}")
        return 0
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        ap.error("set ELEVENLABS_API_KEY")
    done = run(config, args.out, languages, animals, key, force=args.force)
    print(f"\n{done['generated']} generated, {done.get('retaken', 0)} retaken, {done['skipped']} already there, in {args.out}")
    if done.get("check"):
        print("Still too long, listen to: " + ", ".join(done["check"]))
    print(f"Listen to them, then upload:\n  gcloud storage cp -r '{args.out}'/* {BUCKET_PREFIX} "
          '--cache-control="public, max-age=3600"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
