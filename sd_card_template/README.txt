SweetYaar SD Card Layout
========================

Copy this folder structure to the root of a FAT32-formatted microSD card.

/config.json                  — parent-editable toy defaults
/songs/<theme>/metadata.json   — theme metadata (name, shuffle)
/songs/<theme>/01.wav          — songs named numerically or any name, alphabetical order
/songs/<theme>/02.wav
...

/animals/metadata.json         — animal metadata (shuffle, disabledSongs)
/animals/cat.wav               — animal sound files (any name ending in .wav)
/animals/dog.wav
...

Audio format requirements:
  - WAV (PCM, uncompressed)
  - 44100 Hz sample rate
  - 16-bit depth
  - Stereo / 2 channels
  - Files can be any size; the SD card is read in streaming chunks

Recommended tools for converting audio:
  - ffmpeg: ffmpeg -i input.mp3 -ar 44100 -ac 2 -sample_fmt s16 output.wav
  - Audacity: Tracks > Mix > Mix Stereo Down, then Export > WAV > 44100 Hz, 16-bit PCM

config.json schema:
  {
    "schemaVersion": 2,
    "defaultVolumePct": 75,
    "defaultTheme": "lullabies",
    "disabledThemes": []
  }

theme metadata.json schema:
  {
    "schemaVersion": 2,
    "name": "Lullabies",
    "shuffle": false,
    "disabledSongs": []
  }

animals metadata.json uses the same schema. The app shows it as a special
always-enabled "Animals" theme and ignores any custom name.

If config.json is missing or invalid, firmware defaults are used.
