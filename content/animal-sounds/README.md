# Animal sounds content

Source material and build recipe for the SD card's `/animals` folder. Each animal file is
`[0.1 s lead-in] [spoken question] [0.7 s pause] [animal sound] [0.3 s tail]`, 44.1 kHz mono 16-bit WAV.
The question is trimmed to the human voice (speech-band activity of at least 60 ms; clicks, breaths and
reverb tails are ignored; `voice_*` in `build.json`), and the animal sound is trimmed by level
(`trim_threshold_db`), so those fixed gaps are the only edge silence. The files in `sounds/` are already
trimmed, so for them this step does nothing (the log shows `trimmed 0.00s`); the questions are trimmed
on every build.
The question and the sound are separate inputs so the question can change per language or voice.

```
sounds/                      13 approved animal sounds (language-independent) + ATTRIBUTION.txt
tts/<theme>/<animal>.wav     the spoken questions for one language/voice: en-coral, he-mom, he-dad, ...
profiles/<name>.json         one toy's choices: which tts theme, which animals, per-animal overrides
build.json                   global pause / gain defaults
build/<profile>/animals/     generated output (ignored by Git)
```

The questions come from outside this repo. Drop one folder per theme into `tts/`, one WAV per animal
(`dog.wav`, `cat.wav`, ...). Any sample rate, mono or stereo, 16/24/32-bit or float is accepted.

## Workflow

```sh
make animals PROFILE=default
make animals PROFILE=he_mom SDCARD=/Volumes/SWEETYAAR     # then syncs the card
```

Build without `SDCARD` first and check `build/<profile>/animals/`. With `SDCARD`, the card's `/animals`
folder is made identical to the build: its files are copied and everything else in that folder is
deleted (only `/animals`; songs and `config.json` are untouched). If files were missing, the build is
still copied, and the log ends with `!! INCOMPLETE` and the names of the animals left out.

A new toy or language = add `tts/<theme>/`, copy `profiles/default.json` to `profiles/<name>.json` and
set `tts` to the theme folder name. Per-toy tweaks go in `overrides`, e.g.
`{"duck": {"pause_after_prompt_sec": 1.0, "animal_gain_db": -2}}`. The build also writes
`metadata.json` (from `sd-card-template/animals/`). Songs, `config.json` and everything else still
come from `sd-card-template/`.

## Rules

- There is no repeat option. Dog, cat, sheep and duck are short single calls, so their files in
  `sounds/` are already doubled (call, 0.25 s gap, call). To change that, edit the sound file.
- Do not overwrite approved WAVs in `sounds/` without the owner's ear on it; offer A/B/C options.
- Keep `sounds/ATTRIBUTION.txt` current. Cow, dog and sheep are CC-BY-NC (fine for a personal
  gift, replace before any sale); duck and horse need author credit if shared.
- The shared I2S output is stereo and the firmware duplicates mono; keep sounds mono 44.1 kHz.
- Sounds are real recordings; synthesized animals were rejected. Sources and licenses are in
  `sounds/ATTRIBUTION.txt`.
