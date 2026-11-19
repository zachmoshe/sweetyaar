#!/usr/bin/env python3
"""Generate an AI song theme with Eleven Music.

Reads a theme file (for example my-day.json) and writes a folder laid out like
the bucket's songs/<theme>/ folder:

    <out>/metadata.json             {schemaVersion, name, shuffle, disabledSongs, attribution}
    <out>/ATTRIBUTION.txt           the theme's one attribution line
    <out>/NN - <Title>.wav          44.1 kHz mono 16-bit, levelled
    <out>/.raw/<song>.mp3, .json    what Eleven Music returned, and the request (not uploaded)

The API key comes from ELEVENLABS_API_KEY. Eleven Music costs credits per second
of music, so --dry-run shows the plan and its length first. Needs ffmpeg.

    python3 content/ai_music/generate.py content/ai_music/my-day.json --out /tmp/my-day --dry-run
    ... --preview --length 60        only the theme's preview songs, 60 s each
    ... --songs 03-brush-your-teeth  only these songs
    ... --force                      regenerate songs that already exist
"""
from __future__ import annotations

import argparse
import array
import json
import math
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import wave
from pathlib import Path

API = "https://api.elevenlabs.io/v1/music"
CREDITS_PER_MINUTE = 750          # what Eleven Music charged us (2026-11-15); used only for the estimate


def load_theme(path: Path) -> dict:
    theme = json.loads(path.read_text(encoding="utf-8"))
    ids = [s["id"] for s in theme["songs"]]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate song ids")
    for s in theme["songs"]:
        if not s.get("prompt", "").strip() or not s.get("title", "").strip():
            raise ValueError(f"{s['id']}: needs a title and a prompt")
    for p in theme.get("preview", []):
        if p not in ids:
            raise ValueError(f"preview song {p} is not in songs")
    if "\n" in theme["attribution"] or len(theme["attribution"].encode()) > 160:
        raise ValueError("attribution must be one line of at most 160 bytes (firmware limit)")
    return theme


def full_prompt(theme: dict, song: dict, length_s: int) -> str:
    return f"{song['prompt']} {theme['defaults']['style']} About {length_s} seconds long."


def file_name(song: dict) -> str:
    number = song["id"].split("-")[0]
    title = "".join(c for c in song["title"] if c not in '/\\:*?"<>|')
    return f"{number} - {title}.wav"


def bar_ms(song: dict, section: dict | None = None) -> float:
    bpm = (section or {}).get("bpm", song["bpm"])
    return song.get("beats_per_bar", 4) * 60000 / bpm


def plan_for(theme: dict, song: dict) -> dict:
    """A composition plan (Eleven Music v2.5) from a song's sections: each section is a chunk whose
    length comes from its bars and the song's tempo, so the form (intro, A, B, A', ending) and its
    harmony directions are kept."""
    d = theme["defaults"]
    chunks = []
    allowed = set(song.get("allow_styles", []))           # e.g. the drums piece lifts the theme's "heavy drum kit" ban
    for i, sec in enumerate(song["sections"]):
        bpm = sec.get("bpm", song["bpm"])
        styles = (song["styles"] if i == 0 else []) + [f"{bpm} BPM", sec.get("key", song["key"])] + sec["styles"]
        text = f"[{sec['name']}] {{{sec['cue']}}}"
        if len(text) > 200:                                   # the API refuses longer lines
            raise ValueError(f"{song['id']} / {sec['name']}: section text is {len(text)} characters, the limit is 200")
        chunks.append({
            "text": text,
            "duration_ms": max(3000, round(sec["bars"] * bar_ms(song, sec))),
            "positive_styles": styles,
            "negative_styles": [n for n in d["negative_styles"] + song.get("negative", []) + sec.get("negative", [])
                                if n not in allowed],
            "context_adherence": sec.get("context_adherence", "high"),
        })
    return {"chunks": chunks}


def song_seconds(theme: dict, song: dict, length_s: int) -> float:
    if song.get("sections"):
        return sum(c["duration_ms"] for c in plan_for(theme, song)["chunks"]) / 1000
    return length_s


def compose(prompt: str, length_s: int, defaults: dict, key: str, plan: dict | None = None) -> tuple[bytes, str]:
    if plan:
        body = {"model_id": defaults["model_id"], "composition_plan": plan}
    else:
        body = {"model_id": defaults["model_id"], "prompt": prompt, "music_length_ms": length_s * 1000,
                "force_instrumental": defaults.get("force_instrumental", True)}
    req = urllib.request.Request(f"{API}?output_format={defaults['output_format']}", data=json.dumps(body).encode(),
                                 method="POST", headers={"xi-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            return resp.read(), resp.headers.get("song-id", "")
    except urllib.error.HTTPError as err:
        raise RuntimeError(f"Eleven Music -> HTTP {err.code}: {err.read().decode(errors='replace')[:400]}") from None


def trim_edges(x: array.array, rate: int, defaults: dict) -> array.array:
    """Cut the silence Eleven Music leaves at the start and end, keeping a short lead-in and a tail
    for the last note to ring, with short fades so nothing clicks."""
    win = rate // 20
    thr = 32767 * 10 ** (defaults.get("silence_db", -50) / 20)
    loud = [i for i in range(0, len(x), win)
            if math.sqrt(sum(v * v for v in x[i:i + win]) / max(1, len(x[i:i + win]))) > thr]
    if not loud:
        return x
    start = max(0, loud[0] - int(0.15 * rate))
    end = min(len(x), loud[-1] + win + int(defaults.get("tail_s", 0.8) * rate))
    y = x[start:end]
    fin, fout = int(0.01 * rate), int(0.3 * rate)
    for i in range(min(fin, len(y))):
        y[i] = int(y[i] * i / fin)
    for i in range(min(fout, len(y))):
        y[len(y) - 1 - i] = int(y[len(y) - 1 - i] * i / fout)
    return y


def to_levelled_wav(mp3: Path, wav: Path, defaults: dict) -> float:
    """Decode to mono 44.1 kHz 16-bit, level to target_rms_db with peaks under peak_db. Returns seconds."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is needed (brew install ffmpeg)")
    rate = defaults.get("sample_rate", 44100)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp3), "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    x = array.array("h", raw)
    x = trim_edges(x, rate, defaults)
    win = rate // 10
    frames = [x[i:i + win] for i in range(0, len(x), win)]
    rms_f = [math.sqrt(sum(v * v for v in f) / len(f)) for f in frames if f]
    loud = [r for r in rms_f if r > 32767 * 10 ** (-60 / 20)]            # ignore near-silence
    rms = math.sqrt(sum(r * r for r in loud) / max(1, len(loud))) or 1.0
    gain = 10 ** (defaults.get("target_rms_db", -19) / 20) * 32767 / rms
    peak = max(1, max(abs(v) for v in x))
    gain = min(gain, 10 ** (defaults.get("peak_db", -1) / 20) * 32767 / peak)
    out = array.array("h", (max(-32768, min(32767, round(v * gain))) for v in x))
    wav.parent.mkdir(parents=True, exist_ok=True)
    tmp = wav.with_name(wav.stem + ".tmp.wav")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(out.tobytes())
    tmp.replace(wav)
    return len(out) / rate


def write_theme_files(theme: dict, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    meta = {"schemaVersion": 2, "name": theme["name"], "shuffle": theme.get("shuffle", False),
            "disabledSongs": [], "attribution": theme["attribution"]}
    (out / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "ATTRIBUTION.txt").write_text(theme["attribution"] + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("theme", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--songs", help="comma-separated song ids (default: all)")
    ap.add_argument("--preview", action="store_true", help="only the theme's preview songs")
    ap.add_argument("--length", type=int, help="seconds per song (default: the theme's length_s)")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--reconvert", action="store_true",
                    help="rebuild the WAVs from the saved .raw files (no API calls, no credits)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    theme = load_theme(args.theme)
    d = theme["defaults"]
    wanted = theme["preview"] if args.preview else ([s.strip() for s in args.songs.split(",")] if args.songs else None)
    songs = [s for s in theme["songs"] if wanted is None or s["id"] in wanted]
    if wanted and len(songs) != len(wanted):
        ap.error("unknown song id in --songs")
    length = args.length or d["length_s"]
    if args.reconvert:
        for s in songs:
            raw = args.out / ".raw" / f"{s['id']}.mp3"
            if raw.exists():
                print(f"  {file_name(s)}  {to_levelled_wav(raw, args.out / file_name(s), d):.0f} s")
        return 0
    todo = [s for s in songs if args.force or not (args.out / file_name(s)).exists()]
    total = sum(song_seconds(theme, s, length) for s in todo)
    print(f"{len(todo)} songs, {total / 60:.1f} min, about {round(total / 60 * CREDITS_PER_MINUTE)} credits")
    if args.dry_run:
        for s in todo:
            print(f"\n{file_name(s)}  ({song_seconds(theme, s, length):.0f} s)")
            if s.get("sections"):
                for c in plan_for(theme, s)["chunks"]:
                    print(f"  {c['duration_ms'] / 1000:5.1f} s  {c['text']}\n           + {', '.join(c['positive_styles'])}")
            else:
                print(f"  {full_prompt(theme, s, length)}")
        return 0
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        ap.error("set ELEVENLABS_API_KEY")
    write_theme_files(theme, args.out)
    for s in todo:
        plan = plan_for(theme, s) if s.get("sections") else None
        prompt = None if plan else full_prompt(theme, s, length)
        audio, song_id = compose(prompt, length, d, key, plan)
        raw = args.out / ".raw" / f"{s['id']}.mp3"
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_bytes(audio)
        (raw.with_suffix(".json")).write_text(json.dumps({"song_id": song_id, "model_id": d["model_id"],
                                                          "length_s": song_seconds(theme, s, length), "prompt": prompt,
                                                          "composition_plan": plan},
                                                         ensure_ascii=False, indent=2), encoding="utf-8")
        seconds = to_levelled_wav(raw, args.out / file_name(s), d)
        print(f"  {file_name(s)}  {seconds:.0f} s")
    print(f"\nDone: {args.out}. Listen, then upload the folder (without .raw) to "
          f"gs://sweetyaar-studio-resources/songs/{theme['id']}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
