# Animal prompts

The spoken questions ("How does a cat sound?") that SweetYaar Studio joins to
each animal sound. They live in the public bucket under `animal-prompts/`
(see "Shared content" in [docs/engineering/studio.md](../../docs/engineering/studio.md)).

- `prompts.json`: the source of truth.
  - **`defaults`** apply to every language: the ElevenLabs model, the audio
    tags put before every question (`[childish] [warm] [engaged]`), the voice
    settings, the format to request (`output_format`) and the output sample
    rate.
  - **`languages`** has one block per language: its voice and the 13
    questions. A block may override any default key (`model_id`, `tags`,
    `voice_settings`, `output_format`, `sample_rate`, `language_code`).
  - **`attribution`** is the one line written to `ATTRIBUTION.txt`. It applies
    to every file, so the attribution file has nothing else.
- `generate.py`: makes the audio with the ElevenLabs API, converts it to
  44.1 kHz WAV with ffmpeg, trims the silence at both ends (keeping 30 ms
  before and 80 ms after the speech) and levels every file to the same
  loudness (`target_rms_db`, with peaks kept under `peak_db`); nothing is
  uploaded. Takes use a fixed `seed`, so a rerun is repeatable. The model
  sometimes repeats the start of a sentence; such a take is much longer than
  the language's other questions (over `max_length_ratio` × their median), so
  the script redoes it with other seeds, up to `max_retakes` times, and names
  any file still too long. `output_format` is
  `pcm_48000`, lossless and the best our Starter plan allows (checked
  2026-11-15: 44.1 kHz PCM and 192 kbps MP3 are refused); change it if the
  plan changes.

## Generate

```sh
export ELEVENLABS_API_KEY=...     # a paid plan: the free plan has no commercial licence
python3 content/animal_prompts/generate.py --dry-run                 # see the exact texts
python3 content/animal_prompts/generate.py --out /tmp/animal-prompts
python3 content/animal_prompts/generate.py --out /tmp/animal-prompts --languages es --animals cat,dog --force
```

The output folder mirrors the bucket folder:

```
<out>/ATTRIBUTION.txt
<out>/<lang>/<animal>.wav     44.1 kHz mono 16-bit, converted from what ElevenLabs returns
```

Existing files are kept unless `--force`, so a rerun only fills in what is
missing. Listen to the files, then upload with the command the script prints
(`gcloud storage cp -r <out>/* gs://sweetyaar-studio-resources/animal-prompts/`).

## A new language

Add a block under `languages` with its code (`es`), its name, the voice and the
13 questions, run `generate.py --languages es`, listen, upload. Studio lists the
new language on its own.

- **The voice** is the exact name of a voice in the account's *My Voices*
  (add it from the Voice Library first) or its voice ID.
- **Pronunciation:** write the text the way the voice must read it. Hebrew
  needs full niqqud (and the gender of the verb: עוֹשֶׂה, or עוֹשָׂה for a
  feminine animal). The voice reads every sheva as silent, so write a vocal
  sheva as the vowel actually said: תַּרְנֶגוֹל, not תַּרְנְגוֹל ("tarngol").
  Arabic can take tashkeel the same way.
- **The model is Eleven v4**, the one our voices (professional clones) are
  verified on; the website uses it too. A voice on a model it isn't verified
  on sounds wrong (Danit on v3 did). Check a new voice's verified models in
  its page, or with `GET /v1/voices/<id>`, before choosing it.
- **Audio tags** like `[warm]` work with v4; set `tags` to `""` for a
  language if its voice reads them aloud.
