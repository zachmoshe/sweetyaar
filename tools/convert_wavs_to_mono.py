#!/usr/bin/env python3
"""Copy 44.1 kHz/16-bit PCM WAVs to a separate tree, averaging stereo to mono."""

import argparse
from array import array
from pathlib import Path
import sys
import wave


def convert(source: Path, destination: Path) -> tuple[int, int]:
    if source.resolve() == destination.resolve():
        raise ValueError("Choose a separate destination; source WAVs are preserved.")
    with wave.open(str(source), "rb") as original:
        channels = original.getnchannels()
        if (channels not in (1, 2) or original.getsampwidth() != 2
                or original.getframerate() != 44100 or original.getcomptype() != "NONE"):
            raise ValueError(f"Unsupported source format: {source}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as target_file, wave.open(target_file, "wb") as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(44100)
            frames = 0
            while data := original.readframes(4096):
                if len(data) % (2 * channels):
                    raise ValueError(f"Incomplete PCM frame: {source}")
                samples = array("h", data)
                if sys.byteorder != "little":
                    samples.byteswap()
                if channels == 2:
                    # Integer arithmetic avoids overflow and preserves identical
                    # channels exactly. This matches the amplifier's L/2 + R/2 mix.
                    samples = array("h", ((left + right) // 2
                                          for left, right in zip(samples[::2], samples[1::2])))
                frames += len(samples)
                if sys.byteorder != "little":
                    samples.byteswap()
                target.writeframesraw(samples.tobytes())
            if frames != original.getnframes():
                raise ValueError(f"Truncated PCM data: {source}")
    with wave.open(str(destination), "rb") as result:
        assert result.getparams()[:4] == (1, 2, 44100, frames)
    return source.stat().st_size, destination.stat().st_size


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Folder containing the original WAVs")
    parser.add_argument("destination", type=Path, help="Separate folder for mono WAVs; existing files are not overwritten")
    args = parser.parse_args()
    source, destination = args.source.resolve(), args.destination.resolve()
    if source == destination or source in destination.parents:
        parser.error("Destination must be separate from the source tree.")
    paths = sorted(p for p in source.rglob("*") if p.suffix.lower() == ".wav" and not p.name.startswith("."))
    if not paths:
        parser.error("No WAV files found in the source folder.")
    before = after = 0
    for path in paths:
        relative = path.relative_to(source)
        old_size, new_size = convert(path, destination / relative)
        before += old_size
        after += new_size
        print(f"{relative}: {old_size:,} -> {new_size:,} bytes")
    print(f"Converted {len(paths)} WAVs: {before:,} -> {after:,} bytes")


if __name__ == "__main__":
    main()
