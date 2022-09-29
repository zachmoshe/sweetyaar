#! /usr/bin/env python

import pathlib
import subprocess
import sys
import tempfile


_DEFAULT_FFMPEG_TP = -6
_DEFAULT_FFMPEG_I = -12
_DEFAULT_FFMPEG_LRA = 11
_DEFAULT_FFMPEG_SAMPLE_RATE = 16000

_MEDIA_FILE_SUFFIXES = ("wav", "mp3", "ogg", "aiff", "asf", "avi", "flv")


def _is_valid_media_file(path):
    return path.suffix[1:] in _MEDIA_FILE_SUFFIXES


def _traverse_descendants(path):
    yield path
    yield from path.glob("**/*")


def _renormalize_audio_volume(input_path, output_path, i=_DEFAULT_FFMPEG_I, lra=_DEFAULT_FFMPEG_LRA, tp=_DEFAULT_FFMPEG_TP):
    subprocess.call(["ffmpeg", "-i", str(input_path), "-ac", "1", "-af", f"loudnorm=I={i}:LRA={lra}:TP={tp}", "-acodec", "pcm_s16le", "-ar", str(_DEFAULT_FFMPEG_SAMPLE_RATE), "-y", str(output_path)])


def main(args):
    if len(args) != 2:
        raise ValueError(f"Usage: {args[0]} [input file root]")
    input_file_root = pathlib.Path(args[1])

    for input_file in _traverse_descendants(input_file_root):
        if not _is_valid_media_file(input_file):
            print(f"Skipping non-media file '{input_file}'")
            continue

        output_file = input_file.relative_to(input_file_root.parent)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        _renormalize_audio_volume(input_file, output_file)


if __name__ == "__main__":
    main(sys.argv)