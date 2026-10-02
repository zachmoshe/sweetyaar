SweetYaar SD Card Layout
========================

Copy this folder structure to the root of a FAT32-formatted microSD card.

/config.json                  — parent-editable toy defaults, sleep, bedtime mode
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
  - Mono / 1 channel (recommended), or stereo / 2 channels
  - Files can be any size; the SD card is read in streaming chunks

Recommended tools for converting audio:
  - ffmpeg: ffmpeg -i input.mp3 -ar 44100 -ac 1 -c:a pcm_s16le output.wav
  - Audacity: Tracks > Mix > Mix Stereo Down, then Export > WAV > 44100 Hz, 16-bit PCM

The template recordings are mono. The firmware duplicates each mono sample to
both output channels; existing stereo recordings still work. Stereo-to-mono
conversion averages the left and right samples, matching the amplifier's mix.
Sample rate, timing, and filenames stay unchanged.

To convert an existing folder while preserving its original recordings:
  .venv/bin/python tools/convert_wavs_to_mono.py SOURCE_FOLDER DESTINATION_FOLDER
The destination must be separate; existing WAV files are not overwritten.
WAV recordings are local content ignored by Git. The conversion script and this
folder's configuration/metadata are versioned; copy the converted WAVs with them
when preparing a card.

System cues (ready, error, pairing) belong in firmware/esp32/assets/sounds for
future embedding in firmware flash. Do not put those cues on the SD card: an SD
failure must not prevent the error cue from being available.

config.json schema:
  {
    "schemaVersion": 2,
    "defaultVolumePct": 75,
    "defaultTheme": "lullabies",
    "disabledThemes": [],
    "bedtime": {
      "enabled": true,
      "startTime": "18:30",
      "endTime": "06:30",
      "theme": "lullabies",
      "volumeCapPct": 45
    },
    "sleep": {
      "enabled": true,
      "normalIdleSec": 600,
      "vibrationWakeIdleSec": 120,
      "bleIdleSec": 120
    }
  }

bedtime.enabled controls the Bedtime mode master setting. startTime and endTime
are local HH:MM clock times. The default bedtime window is 18:30 to 06:30 and
crosses midnight. The bedtime theme is a single normal song theme folder id.
volumeCapPct caps effective local WAV volume while Bedtime mode is active.
See docs/engineering/mobile-app.md for full behavior, time-sync, fallback, and parent-app UX
details.

sleep.enabled controls automatic deep sleep. normalIdleSec is used after real
toy activity. vibrationWakeIdleSec is used when the device woke only because the
vibration switch moved and then nobody interacted with it. bleIdleSec is how
long a connected but idle parent app is allowed to block sleep.

Deep sleep is a full reboot on wake. Bluetooth/BLE clients disconnect, playback
state is not remembered, and the toy starts normally after the vibration switch
wakes GPIO27. Sleep is skipped while a song/animal is playing, while Classic BT
audio is connected, and while killswitch is active.

theme metadata.json schema:
  {
    "schemaVersion": 2,
    "name": "Lullabies",
    "shuffle": false,
    "disabledSongs": []
  }

Bedtime theme selection lives in /config.json. Individual theme metadata files
do not need a bedtime flag.

animals metadata.json uses the same schema. The app shows it as a special
always-enabled "Animals" theme and ignores any custom name.

If config.json is missing or invalid, firmware defaults are used.
