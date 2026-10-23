#!/usr/bin/env python3
"""Render a second charging-cue audition round in the existing piano voice."""

from fractions import Fraction
from pathlib import Path
import json
import wave

import numpy as np
from scipy.signal import resample_poly


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
RATE = 44100
REFERENCE = ROOT / "content/system-sounds/reference/pairing-original.wav"
OPTIONS = {
    "01-sunrise": {
        "name": "Sunrise",
        "description": "Three overlapping notes rising through a bright major chord.",
        "pitches": "C5–E5–G5",
        "notes": [(0, 72, .28, .85), (.12, 76, .28, .92), (.26, 79, .31, 1.0)],
    },
    "02-little-celebration": {
        "name": "Little celebration",
        "description": "A playful four-note climb, finishing an octave above the first note.",
        "pitches": "G4–B4–D5–G5",
        "notes": [(0, 67, .26, .78), (.10, 71, .26, .83),
                  (.22, 74, .26, .90), (.36, 79, .27, 1.0)],
    },
    "03-smiling-finish": {
        "name": "Smiling finish",
        "description": "A cheerful leap, then a softer major-third landing with quiet harmony.",
        "pitches": "C5–G5–E5, with a soft C5 under the last note",
        "notes": [(0, 72, .32, .85), (.16, 79, .30, .98),
                  (.30, 76, .30, 1.0), (.30, 72, .30, .30)],
    },
}


def load_piano_note():
    with wave.open(str(REFERENCE), "rb") as source:
        assert source.getparams()[:3] == (1, 2, RATE)
        pcm = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2")
    # Same isolated C5 strike used for the earlier battery/charger auditions.
    return pcm[round(.260 * RATE):round(.642 * RATE)].astype(np.float64) / 32768


def piano_note(source, midi_note, duration, velocity):
    ratio = Fraction(2 ** ((72 - midi_note) / 12)).limit_denominator(4096)
    pitched = resample_poly(source, ratio.numerator, ratio.denominator)
    count = round(duration * RATE)
    note = np.zeros(count)
    copied = min(count, len(pitched))
    note[:copied] = pitched[:copied]
    # Fade the actual pitched sample, not its zero padding. Overlapping tails
    # and a gentler attack avoid the previous cue's clipped, repeated-tap feel.
    attack = min(round(.006 * RATE), copied)
    release = min(round(.100 * RATE), copied // 2)
    note[:attack] *= np.sin(np.linspace(0, np.pi / 2, attack)) ** 2
    note[copied - release:copied] *= np.cos(np.linspace(0, np.pi / 2, release)) ** 2
    return note * velocity


def render(source, notes):
    lead, tail = .018, .050
    duration = max(start + length for start, _, length, _ in notes) + lead + tail
    result = np.zeros(round(duration * RATE))
    for start, midi_note, length, velocity in notes:
        note = piano_note(source, midi_note, length, velocity)
        offset = round((start + lead) * RATE)
        result[offset:offset + len(note)] += note
    # Comparable audition levels, with headroom below the earlier cue ceiling.
    gain = min(.080 / np.sqrt(np.mean(result ** 2)), .30 / np.max(np.abs(result)))
    return result * gain


def write_wav(path, samples):
    assert np.all(np.isfinite(samples)) and np.max(np.abs(samples)) < 1
    pcm = np.rint(samples * 32767).astype("<i2")
    with wave.open(str(path), "wb") as output:
        output.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
        output.writeframes(pcm.tobytes())
    return {
        "file": path.name,
        "duration_s": round(len(samples) / RATE, 4),
        "frames": len(samples),
        "peak_dbfs": round(20 * np.log10(np.max(np.abs(pcm)) / 32768), 2),
        "rms_dbfs": round(20 * np.log10(np.sqrt(np.mean((pcm.astype(float) / 32768) ** 2))), 2),
        "bytes": path.stat().st_size,
    }


def main():
    source = load_piano_note()
    manifest = {
        "format": "44.1 kHz, 16-bit mono PCM WAV",
        "source": "content/system-sounds/reference/pairing-original.wav, isolated C5 strike",
        "status": "Sunrise selected and embedded unchanged as charger.wav; see charger-happy-sound-options.md for validation coverage.",
        "options": [],
    }
    for slug, option in OPTIONS.items():
        samples = render(source, option["notes"])
        entry = {key: option[key] for key in ("name", "description", "pitches")}
        entry.update(write_wav(OUT / f"{slug}.wav", samples))
        manifest["options"].append(entry)
        print(f"{option['name']}: {entry['duration_s']:.3f}s, {entry['bytes']} bytes")
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
