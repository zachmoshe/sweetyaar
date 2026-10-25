#!/usr/bin/env python3
"""Build the SD-card /animals folder for one toy from a profile.

Each output file is  [lead-in] [spoken question] [pause] [animal sound] [tail silence].
The question is trimmed to the human voice only (speech-band, sustained activity, so clicks, breaths and
reverb tails do not count); the animal sound is trimmed by level. The lead-in, pause and tail are then the
only silence at the edges and the timing is identical for every animal.

    content/animal-sounds/sounds/<animal>.wav                  language-independent animal sound
    content/animal-sounds/tts/<theme>/<animal>.wav             the spoken question (any language/voice)
    content/animal-sounds/profiles/<name>.json                 tts theme, animals, overrides
    content/animal-sounds/build.json                           global timing/gain defaults

    build_animals.py default                      -> content/animal-sounds/build/default/animals/
    build_animals.py default --out ~/Desktop/animals          write into a folder you choose
    build_animals.py default --tts ~/my_voice --out ~/Desktop/animals   use your own recordings
    build_animals.py he_mom --pause 1.0
    build_animals.py default --sdcard /Volumes/SWEETYAAR   (then syncs <card>/animals to the build)

--out never deletes anything: it creates the folder if needed and writes the animal WAVs plus
metadata.json into it (same-named files are replaced). Nothing is written to content/sd-card-template.
--tts takes a folder with one recording per animal (dog.wav, cat.wav, ...) instead of the profile's
tts/<theme> folder. Copy the result to the card's /animals folder.

Prompts may be any sample rate, mono/stereo, 16/24/32-bit or float WAV; they are converted.
Profile "overrides" use the same keys as build.json "animals" entries, e.g. {"duck": {"animal_gain_db": -2}},
and may also override top-level keys through a "settings" object.
"""
import argparse
import json
import shutil
import sys
from math import gcd
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.io import wavfile

import audio_clean as ac

ROOT = Path(__file__).resolve().parents[2]
CONTENT = ROOT / "content" / "animal-sounds"
# Written next to the WAVs so the card's /animals folder is complete. Kept here (not read from
# content/sd-card-template) so this script never depends on, or touches, the template.
ANIMALS_METADATA = {"schemaVersion": 2, "name": "Animals", "shuffle": True, "disabledSongs": []}


def load_wav(path, target_sr):
    sr, x = wavfile.read(path)
    if x.dtype == np.int16:
        x = x / 32768.0
    elif x.dtype == np.int32:
        x = x / 2147483648.0
    elif x.dtype == np.uint8:
        x = (x.astype(np.float64) - 128) / 128.0
    else:
        x = x.astype(np.float64)
    if x.ndim > 1:
        x = x.mean(axis=1)
    if sr != target_sr:
        g = gcd(sr, target_sr)
        x = signal.resample_poly(x, target_sr // g, sr // g)
    return x


def trim_silence(x, sr, thresh_db, keep_sec):
    thr = 10 ** (thresh_db / 20) * max(np.max(np.abs(x)), 1e-9)
    idx = np.where(np.abs(x) > thr)[0]
    if len(idx) == 0:
        return x
    keep = int(keep_sec * sr)
    return x[max(idx[0] - keep, 0): idx[-1] + keep + 1]


def voice_bounds(x, sr, cfg):
    """Sample range of the human voice: band-pass to the speech range, then keep sustained activity
    (>= min_run_sec, words closer than merge_gap_sec are joined). Clicks, breaths, hiss and reverb tails
    shorter or quieter than that do not count. Returns (start, end), or None when no voice is found."""
    band, frame = cfg["voice_band_hz"], 0.01
    y = signal.sosfiltfilt(signal.butter(4, band, btype="bandpass", fs=sr, output="sos"), x)
    w = int(sr * frame)
    n = len(y) // w
    if n == 0:
        return None
    e = np.sqrt((y[: n * w].reshape(n, w) ** 2).mean(1))
    act = e > e.max() * 10 ** (cfg["voice_threshold_db"] / 20)
    runs, i = [], 0
    while i < n:
        if act[i]:
            j = i
            while j < n and act[j]:
                j += 1
            if runs and (i - runs[-1][1]) * frame <= cfg["voice_merge_gap_sec"]:
                runs[-1][1] = j
            else:
                runs.append([i, j])
            i = j
        else:
            i += 1
    runs = [r for r in runs if (r[1] - r[0]) * frame >= cfg["voice_min_run_sec"]]
    if not runs:
        return None
    return runs[0][0] * w, min(runs[-1][1] * w, len(x))


def trim_voice(x, sr, cfg):
    """Trim the question to the voice plus a small margin, fading the margins so the cut is inaudible."""
    b = voice_bounds(x, sr, cfg)
    if b is None:
        return x
    m0, m1 = (int(m * sr) for m in cfg["voice_margin_sec"])
    out = x[max(b[0] - m0, 0): min(b[1] + m1, len(x))].copy()
    f0, f1 = min(m0, len(out)), min(m1, len(out))
    if f0:
        out[:f0] *= np.sin(np.linspace(0, np.pi / 2, f0)) ** 2
    if f1:
        out[-f1:] *= np.cos(np.linspace(0, np.pi / 2, f1)) ** 2
    return out


def db(g):
    return 10 ** (g / 20)


def build_one(animal, prompt_dir, out_dir, cfg, overrides, pause):
    sr = cfg["sample_rate"]
    s = {**cfg["defaults"], **cfg.get("animals", {}).get(animal, {}), **overrides.get(animal, {})}
    if pause is not None:
        s["pause_after_prompt_sec"] = pause
    prompt_p = prompt_dir / f"{animal}.wav"
    sound_p = CONTENT / "sounds" / f"{animal}.wav"
    for p, what in ((prompt_p, "prompt"), (sound_p, "animal sound")):
        if not p.exists():
            print(f"  - {animal:9s} SKIPPED (missing {what}: {p.relative_to(ROOT)})")
            return False

    prompt = load_wav(prompt_p, sr) * db(s["prompt_gain_db"])
    trim = cfg.get("trim_silence", True)
    raw_len = len(prompt)
    if trim:
        prompt = trim_voice(prompt, sr, cfg)
    if cfg.get("prompt_target_db") is not None:
        prompt = prompt * 10 ** (cfg["prompt_target_db"] / 20) / ac.active_rms(prompt)
    snd = load_wav(sound_p, sr) * db(s["animal_gain_db"])
    snd_raw_len = len(snd)
    if trim:   # the files in sounds/ are already trimmed, so this normally removes nothing
        snd = trim_silence(snd, sr, cfg["trim_threshold_db"], cfg["keep_edge_silence_sec"])

    parts = [np.zeros(int(s["lead_in_sec"] * sr)), prompt, np.zeros(int(s["pause_after_prompt_sec"] * sr))]
    parts.append(snd)
    parts.append(np.zeros(int(s["tail_silence_sec"] * sr)))
    out = np.concatenate(parts)

    peak = np.max(np.abs(out))
    if peak > 0.99:
        out = out / peak * 0.99
        print(f"    (note: {animal} was scaled down to avoid clipping)")

    wavfile.write(out_dir / f"{animal}.wav", sr, (out * 32767).astype(np.int16))
    print(f"  ok {animal:9s} {len(out) / sr:5.2f}s  question {len(prompt) / sr:4.2f}s (trimmed {(raw_len - len(prompt)) / sr:4.2f}s)  sound {len(snd) / sr:4.2f}s (trimmed {(snd_raw_len - len(snd)) / sr:4.2f}s)  pause {s['pause_after_prompt_sec']}s")
    return True


def sync_to_card(src, dest):
    """Make <card>/animals contain exactly the files in src: copy them, delete everything else there."""
    if not dest.parent.is_dir():
        sys.exit(f"SD card not found: {dest.parent}")
    dest.mkdir(exist_ok=True)
    wanted = {f.name for f in src.iterdir()}
    for old in sorted(dest.iterdir()):
        if old.name not in wanted:
            print(f"  removed from card: {old.name}")
            shutil.rmtree(old) if old.is_dir() else old.unlink()
    for f in sorted(src.iterdir()):
        shutil.copy(f, dest / f.name)
    print(f"Synced {len(wanted)} files to {dest} (card /animals now matches this build exactly)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("profile", nargs="?", default="default",
                    help="name of a file in content/animal-sounds/profiles/ (without .json); default: default")
    ap.add_argument("--tts", help="folder with your spoken questions, one WAV per animal (dog.wav, cat.wav, ...); "
                    "replaces the profile's tts/<theme> folder")
    ap.add_argument("--out", help="folder to write the animal WAVs and metadata.json into (created if missing; "
                    "nothing in it is deleted). Default: content/animal-sounds/build/<profile>/animals")
    ap.add_argument("--animals", nargs="*", help="only these animals")
    ap.add_argument("--pause", type=float, help="override pause_after_prompt_sec for this run")
    ap.add_argument("--sdcard", help="after building, make <SDCARD>/animals identical to the build output "
                    "(copies its files, deletes everything else in that folder)")
    args = ap.parse_args()
    if args.sdcard and args.animals:
        sys.exit("--animals builds a subset; use it without --sdcard (the card would lose the other animals)")

    profile = json.loads((CONTENT / "profiles" / f"{args.profile}.json").read_text())
    cfg = json.loads((CONTENT / "build.json").read_text())
    cfg.update(profile.get("settings", {}))
    if args.tts:
        prompt_dir = Path(args.tts).expanduser().resolve()
        if not prompt_dir.is_dir():
            sys.exit(f"Recordings folder not found: {prompt_dir}")
        source_label = str(prompt_dir)
    else:
        prompt_dir = CONTENT / "tts" / profile["tts"]
        if not prompt_dir.is_dir():
            sys.exit(f"No prompts at {prompt_dir.relative_to(ROOT)}")
        source_label = f"tts/{profile['tts']}"

    if args.out:
        out_dir = Path(args.out).expanduser().resolve()
        template_dir = (ROOT / "content" / "sd-card-template").resolve()
        if out_dir == template_dir or template_dir in out_dir.parents:
            sys.exit("--out must not be inside content/sd-card-template; choose another folder")
        out_dir.mkdir(parents=True, exist_ok=True)   # existing files are never deleted
    else:
        out_dir = CONTENT / "build" / args.profile / "animals"   # git-ignored scratch folder
        shutil.rmtree(out_dir, ignore_errors=True)
        out_dir.mkdir(parents=True)
    animals = args.animals or profile["animals"]
    print(f"Building profile '{args.profile}' ({source_label}) -> {out_dir}")
    built, missing = [], []
    for a in animals:
        (built if build_one(a, prompt_dir, out_dir, cfg, profile.get("overrides", {}), args.pause) else missing).append(a)
    (out_dir / "metadata.json").write_text(json.dumps(ANIMALS_METADATA, indent=2, ensure_ascii=False) + "\n")
    print(f"Done: {len(built)}/{len(animals)} built.")
    if missing:
        print(f"\n!! INCOMPLETE: {len(missing)} animal(s) not built, missing files: {', '.join(missing)}")
    if not built:
        return 1
    if args.sdcard:
        sync_to_card(out_dir, Path(args.sdcard) / "animals")
    return 0


if __name__ == "__main__":
    sys.exit(main())
