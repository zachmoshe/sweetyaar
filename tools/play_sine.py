#!/usr/bin/env python3
import argparse
import math
import os
import subprocess
import tempfile
import wave


def write_sine(path, frequency, duration, volume, sample_rate):
    frames = int(duration * sample_rate)
    amplitude = int(32767 * volume)

    with wave.open(path, "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)

        for i in range(frames):
            sample = int(amplitude * math.sin(2.0 * math.pi * frequency * i / sample_rate))
            pcm = sample.to_bytes(2, byteorder="little", signed=True)
            wav.writeframesraw(pcm + pcm)


def main():
    parser = argparse.ArgumentParser(description="Play a stereo sine wave through the current macOS output device.")
    parser.add_argument("--frequency", "-f", type=float, default=440.0)
    parser.add_argument("--duration", "-d", type=float, default=60.0)
    parser.add_argument("--volume", "-v", type=float, default=0.25)
    parser.add_argument("--sample-rate", "-r", type=int, default=44100)
    parser.add_argument("--loops", "-l", type=int, default=1)
    args = parser.parse_args()

    fd, path = tempfile.mkstemp(prefix="sweetyaar-sine-", suffix=".wav")
    os.close(fd)
    try:
        write_sine(path, args.frequency, args.duration, args.volume, args.sample_rate)
        for _ in range(args.loops):
            subprocess.run(["afplay", path], check=True)
    finally:
        os.unlink(path)


if __name__ == "__main__":
    main()
