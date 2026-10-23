#!/usr/bin/env python3
"""Render battery-cue auditions using the existing SweetYaar felt-piano tone.

Run with the repository's Python environment (numpy and scipy audio group).
These are design candidates, not firmware assets or enabled device behavior.
"""

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

# (onset seconds, MIDI note, duration seconds, relative velocity).
OPTIONS = {
    "01-falling-pair": {
        "name": "Falling pair",
        "description": "Two soft descending notes; the simplest, shortest reminder.",
        "medium": [(0, 71, .28, .90), (.21, 67, .40, 1.0)],
        "low": [(0, 67, .29, .95), (.24, 64, .43, 1.0)],
    },
    "02-little-staircase": {
        "name": "Little staircase",
        "description": "Three falling piano notes; a more melodic sense of energy dropping.",
        "medium": [(0, 74, .24, .84), (.15, 71, .26, .92), (.32, 67, .39, 1.0)],
        "low": [(0, 71, .26, .88), (.18, 67, .28, .95), (.38, 64, .42, 1.0)],
    },
    "03-gentle-nudge": {
        "name": "Gentle nudge",
        "description": "Two short taps followed by a lower note; the clearest attention cue.",
        "medium": [(0, 67, .16, .88), (.20, 67, .16, .88), (.42, 64, .35, 1.0)],
        "low": [(0, 64, .16, .92), (.20, 64, .16, .92), (.44, 60, .40, 1.0)],
    },
}


def silence(seconds):
    return np.zeros(round(seconds * RATE), dtype=np.float64)


def load_piano_note():
    with wave.open(str(REFERENCE), "rb") as source:
        assert source.getnchannels() == 1
        assert source.getsampwidth() == 2
        assert source.getframerate() == RATE
        pcm = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2")
    # Pairing is G4 -> C5. Its isolated C5 strike starts near 0.264 s.
    # The previous note is below -90 dBFS at this extraction boundary.
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


def render(source, notes, target_rms):
    lead = .018
    duration = max(start + length for start, _, length, _ in notes) + lead + .050
    result = silence(duration)
    for start, midi_note, length, velocity in notes:
        note = piano_note(source, midi_note, length, velocity)
        offset = round((start + lead) * RATE)
        result[offset:offset + len(note)] += note
    # Existing cues measure 0.09 RMS, with peaks around 0.30-0.36 full scale.
    gain = min(target_rms / np.sqrt(np.mean(result ** 2)), .35 / np.max(np.abs(result)))
    return result * gain


def write_wav(path, samples):
    assert np.all(np.isfinite(samples))
    assert np.max(np.abs(samples)) < 1
    pcm = np.rint(samples * 32767).astype("<i2")
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(RATE)
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
        "status": "Audition candidates only; no firmware integration or hardware validation.",
        "preview_order": "Good to medium, 1.10 seconds of silence, medium to low",
        "options": [],
    }
    for slug, option in OPTIONS.items():
        medium = render(source, option["medium"], .082)
        low = render(source, option["low"], .090)
        entry = {"id": slug, "name": option["name"], "description": option["description"]}
        entry["medium"] = write_wav(OUT / f"{slug}-medium.wav", medium)
        entry["low"] = write_wav(OUT / f"{slug}-low.wav", low)
        preview = np.concatenate([silence(.18), medium, silence(1.10), low, silence(.20)])
        entry["preview"] = write_wav(OUT / f"{slug}-preview.wav", preview)
        manifest["options"].append(entry)
        print(f"{option['name']}: medium {len(medium)/RATE:.3f}s, low {len(low)/RATE:.3f}s")
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
