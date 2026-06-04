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
See docs/bedtime-mode.md for full behavior, time-sync, fallback, and parent-app
UX details.

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
