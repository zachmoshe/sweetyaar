#!/usr/bin/env python3
"""Render charger-connection auditions in SweetYaar's existing piano voice."""

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

# Onset, MIDI pitch, duration and relative velocity. Keep each cue short enough
# to leave room alongside the selected battery asset in the current OTA slot.
OPTIONS = {
    "01-soft-lift": {
        "name": "Soft lift",
        "description": "Two rising piano notes: a light, quick confirmation.",
        "pitches": "C5–E5",
        "notes": [(0, 72, .23, .88), (.18, 76, .29, 1.0)],
    },
    "02-warm-chord": {
        "name": "Warm chord",
        "description": "A softly rolled major chord: a compact, settled confirmation.",
        "pitches": "G4–B4–D5, overlapping",
        "notes": [(0, 67, .35, 1.0), (.018, 71, .35, .78), (.036, 74, .35, .62)],
    },
    "03-upward-nudge": {
        "name": "Upward nudge",
        "description": "Two short taps, then a higher note: the positive counterpart to the battery cue.",
        "pitches": "E4–E4–G4",
        "notes": [(0, 64, .12, .88), (.14, 64, .12, .88), (.30, 67, .26, 1.0)],
    },
}


def load_piano_note():
    with wave.open(str(REFERENCE), "rb") as source:
        assert source.getparams()[:3] == (1, 2, RATE)
        pcm = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2")
    # Use the same isolated C5 strike as the battery auditions. The existing
    # G4 strike has decayed below -90 dBFS at this extraction boundary.
    return pcm[round(.260 * RATE):round(.642 * RATE)].astype(np.float64) / 32768


def piano_note(source, midi_note, duration, velocity):
    ratio = Fraction(2 ** ((72 - midi_note) / 12)).limit_denominator(4096)
    pitched = resample_poly(source, ratio.numerator, ratio.denominator)
    count = round(duration * RATE)
    note = np.zeros(count)
    copied = min(count, len(pitched))
    note[:copied] = pitched[:copied]
    attack = min(round(.003 * RATE), count)
    release = min(round(.085 * RATE), count // 3)
    note[:attack] *= np.sin(np.linspace(0, np.pi / 2, attack)) ** 2
    note[-release:] *= np.cos(np.linspace(0, np.pi / 2, release)) ** 2
    return note * velocity


def render(source, notes):
    lead = .018
    duration = max(start + length for start, _, length, _ in notes) + lead + .050
    result = np.zeros(round(duration * RATE))
    for start, midi_note, length, velocity in notes:
        note = piano_note(source, midi_note, length, velocity)
        offset = round((start + lead) * RATE)
        result[offset:offset + len(note)] += note
    # Same loudness neighborhood as the existing cues; peak cap leaves headroom.
    gain = min(.085 / np.sqrt(np.mean(result ** 2)), .35 / np.max(np.abs(result)))
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
        "peak_dbfs": round(20 * np.log10(np.max(np.abs(pcm)) / 32768), 2),
        "rms_dbfs": round(20 * np.log10(np.sqrt(np.mean((pcm.astype(float) / 32768) ** 2))), 2),
        "bytes": path.stat().st_size,
    }


def main():
    source = load_piano_note()
    manifest = {
        "format": "44.1 kHz, 16-bit mono PCM WAV",
        "source": "content/system-sounds/reference/pairing-original.wav, isolated C5 strike",
        "status": "First audition round; option 3 was replaced by Sunrise from charger-happy-options. See charger-sound-options.md for history.",
        "intended_event": "Once per valid-input connection after active charging is confirmed, including boot/wake; charging resumption does not repeat it.",
        "options": [],
    }
    for slug, option in OPTIONS.items():
        samples = render(source, option["notes"])
        entry = {key: option[key] for key in ("name", "description", "pitches")}
        entry.update(write_wav(OUT / f"{slug}.wav", samples))
        manifest["options"].append(entry)
        print(f"{option['name']}: {len(samples)/RATE:.3f}s, {entry['bytes']} bytes")
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
