# SweetYaar Studio

Studio is a browser-only content editor for the toy's SD card, served at
`/studio/` beside the parent remote. The remote's opening and Remote screens
link to it with a card; below 768 px the card is grey, says to use a tablet or
laptop and is not a link, since phone browsers cannot export to a folder. There is no server: audio is processed in the page with Web Audio and
stays in the browser until exported.

## Layout

One scrolling page (nothing scrolls inside a panel, which is awkward on a
tablet). At the top, an illustrated header holds the logo, the device button,
**Export to SD card…** and the link back to the remote; while editing a track
it shrinks to a strip. Below it are two shelves, **Themes & songs** and then
**Animals**. Each holds the user's working area (on this computer) above
**On the toy**: a blue card with the connected toy's catalog, read-only.
In Themes & songs it is a compact tree: each theme (song icon, name, an
"off" or problem tag, then songs · length · size) opens to its songs, each
with length and size; songs turned off are dimmed and unplayable ones say
why. In Animals it lists the sounds as small chips, with only the count and
total size in the head. Every theme's songs are read one after another
after connecting, so the totals fill in. Without a toy the card says how
to connect. In Themes & songs the
working area is **My themes**, a warm panel with the drop picture, **+ New
theme** and the drop area: the user's own place, and the only drop target for
files. Beside it (above it below 1000 px) is the **SweetYaar library**, a
lavender panel with a bookshelf picture, so it reads as a separate shelf to
borrow from. Themes are shown as tiles; an open tile spreads across its panel.
Library tiles are compact (name on up to two lines with the note icon in the
top-right corner, length, and the tag and button along the bottom edge, the
button at the same place in every tile of a row) and
sit two to a row beside My themes, more when the library is on top, so 10–15
library themes stay a short list.

The look ("Playroom") follows the clay artwork in `app/design/studio-art/`
(sources, with the prompts used for the generated pieces); the web-sized
copies are in `app/public/assets/studio/`. The header logo is the bear at
the mixer without a background (`assets/studio/logo.png`); the same picture
on a mint tile (`assets/studio-icon.png`) is the small icon of the remote's
Studio row on phones. In the editor the header is a thin strip: the
title and **Connect** (no **Export**, which belongs to the shelves, and no
link to the remote: the editor has its own **← Library**) beside
`assets/studio/edit-strip.png`, the bear trimming a clay waveform with a broom
and two knobs, on a transparent background, standing on the wooden strip
(generated from `edit.jpg`; source `edit-strip.jpg`, prompt
`prompts/edit-strip.txt`). The recording panel
shows `assets/studio/record.jpg`, the bear at the microphone cropped from
`record.jpg`, at its left (hidden on phones). The editor is styled as the wooden
mixing console from that artwork, with the waveform as pastel bars on a dark
screen. `studio/base.css` holds the layout-independent styles and
`studio/studio.css` the design. The canvas colours (waveform, overview,
recording meter) are CSS custom properties on the canvases, read by
`studio.js`; `--wave` may list several colours, and `--wave-bar` draws the
waveform as rounded bars of that width.

## Working area

Themes, songs and animal sounds the user adds are stored in this browser's
IndexedDB (`studio/store.js`) and persist between sessions on the same
computer; Studio asks the browser to keep that storage. Files are stored as
added, unprocessed. The first time Studio changes one of the user's files
(converting it when it opens in the editor, or saving an edit), the file as
added is kept beside the working copy (`original`), so it can be restored;
an edited file therefore takes about twice the space. Files edited before
this existed have no original. Saving an edit tags the song or animal sound
*Edited* (a purple badge beside its buttons, the same for songs, prompts and
animal sounds) and adds a ↺ **Restore** button, which puts the original file
back (parts cleared; it is converted again when next opened). Converting
alone is not an edit. Clearing site data deletes them, so export what matters.
Users can create themes, add audio files, play, rename and remove. Studio
uses no browser pop-ups: removing or discarding happens at once, without a
question, and names are edited in place (a song's name in its row, like the
track name in the editor; **+ New theme** creates "New theme" with its name
field selected).

Audio files can be dropped from the computer onto a theme (adds songs to it),
onto the rest of **My themes** (a song outside any theme), or onto the Animals
working area (an animal sound). Song rows can be dragged within a theme to
change their order (a line shows where they will land; the order is what the
toy plays when the theme is not shuffled, and is kept as each song's `pos`),
between themes, or out of one. A song's name field is only as wide as the
name, so the rest of the row is the handle. Clicking a row selects it,
Cmd/Ctrl-click adds or removes one and Shift-click selects a range; dragging a
selected row moves the whole selection together. Escape or a click outside
the rows clears it. Each theme exposes the settings of its `metadata.json` and `config.json`
entry: display name, credit (one line, at most 160 bytes), enable theme,
shuffle, and per song a turn-off button (a crossed circle beside the edit
button; turning songs off is rare, so it is not a checkbox): a song turned
off is struck through and the button stays highlighted until it is turned on
again. Songs outside a theme have no such button: they are not exported until
they are put in a theme. Playback in the library stops when another page
opens.

The **SweetYaar library** (lavender, the shared library's colour, as in the
Animals panel) lists the song themes in
the shared library (`songs/` below), each with its song count and length
(worked out from the file sizes) and whether it shuffles. Opening one shows
its credit (the theme's `ATTRIBUTION.txt`, shown as everywhere else) and its
songs, which can be played. **+ Add**, or dragging the theme's title row
onto **My themes**, downloads the theme into **My themes**
as a new theme with the library's name, shuffle setting and one-line
credit (from its `metadata.json`) and all its songs; it is then an ordinary
theme that can be edited, and the library row is tagged *Added*, its button
becoming **↻ Update**. Adding a library theme that is already in My themes
(the same library folder) updates that copy instead of making another: its
songs that came from the library are replaced by the library's current files
(same row, place and on/off state), library songs it lacks are added at the
end, and songs the user added to it and its settings are kept. A message
shows while it downloads and when it is done. Themes are copied one at a
time: one added or dragged in while another is copying waits (its button
reads **Waiting…**) and is copied when its turn comes, in the order added; a
failed copy moves on to the next. The waiting list is not kept across a reload. A song from the library whose
audio has been changed in the wave editor is tagged *Edited* and gets a ↺
**Restore** button, which downloads the library's file again in its place
(name, audio and parts back to the library's; the row keeps its place and
on/off state). Updating the theme from the library also restores its songs. A library theme can only be dropped on My themes
as a whole (dropping it on one of the user's themes adds it beside them, not
into that theme); its songs cannot be dragged on their own.

Each working-area song and animal sound has a waveform icon that opens it in the
wave editor (`studio/audio.js` holds the audio processing). Opening converts the
item once to the toy's WAV format (44.1 kHz, 16-bit PCM, mono or stereo) and
stores the converted file. The editor shows the waveform with a time ruler and
an overview strip whose highlighted box is the visible part (drag it to pan);
zoom uses buttons or ctrl/⌘ + scroll, down to a 10 s window. Clicking pauses and sets the position,
clicking sets the position and clears any selection, dragging selects a range, shift-drag scrubs with sound. The volume knob changes the selected range if there is a selection when you first turn it (blended in and out over 5 ms), otherwise the whole track; it is applied to the audio immediately (the waveform and playback change as you turn it, and Undo reverts it); selecting a different range starts a new change. **Cut selection**
(or Delete) removes the selected range with a 5 ms cross-fade. Quick fixes
apply to the selection when there is one, otherwise to the whole track (the
Quick fixes heading says which): trim silence at both ends (how much is a
choice of Gentle, Normal, Firm or Strong: below -60, -50, -40 or -30 dBFS
counts as silence; Normal is the default), fade in/out (sliders, 0.5 s steps), and normalize volume (Standard:
-18 dBFS average, peaks limited to -3 dBFS; Child-safe: -24 dBFS average,
peaks to -6 dBFS), each undoable until saved. On a selection, fades and
normalizing blend into the audio around it over 5 ms.
**Reduce background noise** removes steady noise (hiss, hum, fans, room
tone): it learns the noise from the track's quietest moments (the average
spectrum of its quietest 10 % of 46 ms frames), then turns each frequency down
where it is not clearly louder than that noise (spectral gating, smoothed over
frequency and time). Light, Medium (default) and Strong set how hard
(over-subtraction 1.5/2/3, at most -8/-14/-22 dB). The noise is always learned
from the whole track, so it also works on a short selection; Studio warns when
the track has no clear pause to learn from. It does not remove changing noise
such as voices or music.

**Doll speaker preset** prepares audio for the doll's small 4 Ω speaker behind
fabric: a 24 dB/octave Butterworth high-pass at 200 Hz (two biquads), +3 dB
around 2.5 kHz (Q 1) for voice clarity, a +2 dB high shelf from 6 kHz for the
fabric's treble loss, then the peak limiter at -1 dBFS. Small speakers cannot
reproduce bass below their resonance; feeding it only adds cone excursion
(rattle, distortion) and wastes amplifier power, so the usual practice is a
fixed high-pass near or below the driver's resonance plus a peak or excursion
limiter. The MAX98357A has no filter of its own, so this is the only bass
protection. The values are starting points: measure the chosen speaker's
resonance (a sine sweep through the toy) and move the 200 Hz corner to just
below it, in `DOLL_SPEAKER` in `studio/audio.js`. Apply it once, after the
other fixes; applying it twice doubles the lift.

### Parts and recording

A track is made of **parts**, shown as chips in a strip above the waveform
(dashed lines on the waveform mark where one ends and the next starts). A
track starts as one part.

- **Make part** turns the selected range into a part of its own.
- Clicking a chip selects that part; Shift+click selects the run of parts
  from the last one clicked. **Fuse parts** joins the parts inside the
  selection into one, so they can be edited together.
- Dragging a chip in the strip moves that part (a pink marker shows where it
  will land); dragging on the waveform itself still selects a range.
- Audio files dropped on the waveform are added as new parts at the nearest
  part edge (a pink line shows where); **Insert file…** adds them at the
  position. Clicking near a part edge snaps the position onto it.
- **Record** opens the recording panel at once and starts listening: a
  scrolling scope and a level meter show what the microphone hears (grey while
  only listening, pink while recording), with a microphone chooser when there
  are several and a warning when the chosen one is silent. Nothing is recorded
  until **Start recording**; then **Pause**/**Resume**, **Stop and add**
  (inserts the take at the position as a new part and closes the panel) and
  **Discard take**. **Close** stops the microphone and adds a take in progress. Recording is mono, with the
  browser's echo cancellation, noise suppression and gain control off. While
  the panel is open the other editing controls are disabled, but clicking the
  waveform still sets the position.
- Cutting can remove every part, leaving an empty track to record into.
- Every change is undoable, and the parts are saved with the item. **Save**
  stores the edit and goes back to the shelves; **← Library** leaves without
  saving. Either way the shelves come back scrolled to where they were.

**Record prompts** in the Animals panel, and **🎙️ Record** on a theme (next
to **+ Upload songs**, for example to read a story to the child), open the
editor on a new, empty recording. It joins the working area when it is first
saved: a prompt in the Animals panel, a song in the theme it was started
from. A recording has no original file to restore, so it is never tagged
*Edited*.

The name at the top of the editor can be edited (Enter keeps it, Escape
reverts); a renamed item is saved at once and rematched in the Animals panel.
Name a prompt after its animal (for example `dog`) so it matches by itself.

## Device

The device button is also the connect button (the same Bluetooth button as the
remote). `studio/device.js` is a read-only BLE client: it runs the remote's
access check, then `scanThemes` and `scanSongs` to list themes, songs and the
reserved Animals theme (`special`) with durations and problems. It cannot read
WAV data.

Finding and linking the toy is shared with the remote (`app/public/ble-connect.js`):
both keep the toy used last under one `localStorage` key
(`sweetyaar-last-device-id`; Studio's earlier `sweetyaar.lastDeviceId` is read
once and replaced), and when Studio opens it tries that toy the same way the
remote does at startup: no chooser, listen for the toy, then link, retrying
once (see "Connecting to the toy" in [mobile-app.md](mobile-app.md)). While it connects
the device button says "Connecting…" with a **✕** beside it that stops the
attempt, as in the remote. Refusals get the remote's messages. A live
connection cannot pass from the remote to Studio: opening Studio leaves the
remote's page and the browser closes that page's link, so Studio links again
itself. As with any second phone, the last approved client takes control of
the toy and the other disconnects.

## Status

`app/public/studio/` is a prototype. Working: the layout above, the working
area, the device catalog, the wave editor (waveform, selection, cut, volume,
quick fixes, parts, recording, undo, save), the Animals matching panel and
exporting the working area's themes and animal files to a folder or SD card
(see "Export").

Shared content comes from SweetYaar's public bucket (see "Shared content");
everything else is uploaded by the user, who must have the rights to it.

## Animals

The Animals panel's working area has the settings (shuffle), then two
columns: **Prompts** (the spoken question) on the left and **Animal sounds** on
the right. Above its cards the Prompts column has **+ Add prompts** and
**Record prompts**, then the **Library prompts** box (the prompts'
attribution, a segmented language chooser and **Clear library prompts**); the
Animal sounds column has **+ Add animal sounds**, then the **Library sounds**
box (the sounds' attribution). The
cards of both columns start on the same line. Each card is grey; a matched
prompt and sound turn green and are joined by a dashed line. Everything from
the shared library is lavender: the Library prompts box, a stripe on the left
of library cards and their tags. Every
matched pair becomes one toy file on export (question, pause, sound); an
unmatched card on either side is left out, so skipping an animal means not
matching it.

- Animal sounds come from the shared library (`animal-sounds` below) plus any
  files the user adds (**+ Add animal sounds** in the column header) or drops
  on the column.
- **Library prompts** come from one language of the shared library, English
  by default; the user adds their own with **+ Add prompts** in the column
  header or by dropping files.
  The language buttons are built from the languages the library has. **Clear
  library prompts** hides the library's prompts and keeps the user's own;
  choosing a language shows them again. The user's own prompt files (dropped on
  the column, later recorded) are listed with the shared ones.
- Library prompts and sounds have an edit button: it downloads a copy and
  opens it in the wave editor. Only when that copy is saved does it join the
  working area (tagged *Edited*), replacing the library card and keeping its
  match; leaving the editor without saving leaves the library card as it was.
  Its ↺ button (*Restore*) deletes
  the copy and brings the library card back; the trash button on the user's own
  files removes them, and an edited own file (*Edited* instead of *Mine*) also
  has ↺ Restore.
- A matched animal sound has a green **▶ Play both** pill (unlike the
  round ▶ that plays the sound alone) that plays the whole animal file as
  export would build it: its matched prompt, the gap and the sound, with the
  current "Building the animal files" settings; **■ Stop** stops it. It is on
  the sound's card, not on the line, because lines can cross.
- Same names match by themselves (`dog` with `dog`, or a prompt named
  `Dog question` with the sound `dog`), when the shared prompts load, the
  language changes or files are added. Dragging a prompt onto a sound, or the
  other way, matches them and frees their earlier partners; **×** unmatches.
  An animal sound unmatched with **×** (on either card) stays unmatched: name
  matching skips it after a language change or a reload, until it is matched
  again by hand (`off` in the animals settings, by sound key, which is the
  same in every language).
  Matches, the language and the cleared state are kept with the working area.
- Below the columns, **Building the animal files** has two numbered steps,
  in the order they happen, so the recordings' own quiet edges and the
  file's gaps are never both called "silence":
  - **1 · Clean up each recording** (before they are joined):
    - **Cut the quiet start and end of each question** and **... of each
      animal sound** (both on): Trim silence at its fixed Normal level
      (-50 dBFS), so the gaps in step 2 are exactly what the sliders say;
    - **Same volume for all** (on): every question and every sound is
      levelled to one loudness, the same for the whole pack (Volume level's
      Standard, -18 dBFS), so all the animal files match each other, not
      only the two parts of one file;
    - on the same row, a small **Sound — Question** slider: how much louder
      the question is than the sound, -6 to +6 dB in 1 dB steps, default
      0 dB, as the old build script (questions levelled to -21 dBFS, library
      sounds prepared at about -23 dBFS plus 2 dB); it is split between the
      two (+2 dB = question +1 dB, sound -1 dB) so the pack's average stays
      at the target, and it is dimmed while Same volume is off.
  - **2 · Put the toy file together** (what the child hears): **Wait before
    the question** (0.1 s, up to 1 s) and **Gap between question and sound**
    (0.7 s, up to 2 s), in 0.1 s steps. Below them a strip draws the finished
    file, `[wait] Question [gap] Sound [0.3 s]`, with the gaps to scale (a 0 s gap is left out)
    (question and sound at a typical length); it follows the sliders as they
    move.

  Each joined file is then limited to -1 dBFS. The 0.3 s after the sound is
  fixed. The settings are kept with the working area. A setting that differs
  from its default shows a small ↺ that puts it back, each slider has a tick
  at its default, and **Reset all** restores every setting. The files are built on export (below).

## Toy settings

Below Animals, **Toy settings** edits the card's `config.json` (see
"`/config.json`" in [firmware.md](firmware.md)), starting from the
firmware's defaults, in three cards:

- **When the toy starts**: volume (`defaultVolumePct`, 0–100 % in steps of
  5) and theme (`defaultTheme`).
- **Bedtime**: on/off, from and until (`HH:MM`), theme and the volume cap.
- **Sleep**: on/off and the three idle times, in minutes (1 min to 24 h):
  after real activity, after a wake by a shake only, and with the remote
  connected but idle.

The theme lists offer the themes in My themes that have songs. Until one is
chosen (or when the chosen one is gone) both show, and export, the Lullabies
library theme if it is in My themes, else the first theme, so the file always
names a theme that is on the card; with no theme exported the keys are left
out and the firmware uses `lullabies`, else its first theme. Values
are kept in the browser (`settings` store, `toyConfig`, with Studio theme
ids); **Back to the defaults** clears them. The parent remote can change all
of these later; the toy's name and log sharing live on the toy, not here.

## Export

**Export…** opens a dialog that writes the toy's card layout (see "Content on
the microSD card" in [firmware.md](firmware.md)) into a folder chosen with
Chrome's or Edge's folder access: the SD card itself in a reader, or any folder
to copy onto the card later. Other browsers and phones cannot write folders,
and the dialog says so. The folder is remembered; after a browser restart the
dialog asks once (**Show what's in it**) for permission to open it again.

The dialog shows:

- **The chosen folder**: its name (browsers give a page only the name, never
  the full path), an SD-card icon and "SD card or drive" when it is the top
  of a volume (it holds a system folder such as `System Volume Information`,
  `.fseventsd` or `.Spotlight-V100`), otherwise a folder icon and "Folder",
  and "chosen last time" for the remembered folder. The button reads
  **Choose folder…** until a folder is chosen, then **Change folder…**.

- **Current content**: what the folder holds, with its total size: the themes
  in `songs/` (named from their `metadata.json`, songs listed inside), the
  animal sounds in `animals/`, `config.json`, and every other file and folder
  (macOS `._*`, `.DS_Store` and `.crswap` files counted together as junk).
  The operating system's own folders (`System Volume Information`,
  `.Spotlight-V100`, `.fseventsd`, `.Trashes`, ...) are neither listed nor
  touched. If the folder can't be opened (a card not in the reader), it says
  so and **Export** stays off.
- **Exporting**: the themes and animal sounds that will be written, with their
  file names and an estimated size (a WAV keeps about its size; other formats
  are counted as 44.1 kHz 16-bit stereo; an animal part not yet downloaded is
  counted as 1.5 s), and the folder's size afterwards. Inside an exported
  theme or the animals, files already in the folder under other names follow
  the exported ones: *kept* (in italics) with **Keep** on, *deleted* (struck
  through) with it off, and the theme or animals line counts them
  (*+3 kept*, *3 deleted*). With **Keep** off, the themes, animals and other
  files and folders the export deletes are listed struck through as well. A
  theme not yet in the folder is tagged *new*. The browser cannot tell a
  card's capacity or free space, so there is no capacity bar.
- **Keep other themes, files and folders already in the folder** (on by
  default, remembered). On, songs and animal files of the same name are
  overwritten and everything else stays: other songs in an exported theme,
  other animal files, other themes, files and folders. A song renamed or
  renumbered since the last export then stays under its old name as well.
  Off, the folder ends up holding only the export and `config.json`: every
  other song, animal file, theme, file and folder, and junk are deleted.
- **Also export the toy settings (`config.json`)** (on by default,
  remembered): writes the Toy settings into `config.json`, with the theme
  choices as the exported themes' folder ids. Into an existing `config.json` the keys Studio edits
  are replaced and every other key (inside `bedtime` and `sleep` too) is
  kept. The toy settings alone are enough for an export.
- With **Keep** off, a short warning above the button: "About to delete N
  files and folders" (deleted songs and animal files, and each deleted
  theme, folder or file counted once, plus what a deleted theme held).
- **Export** with a progress bar over building the animal files and writing
  every file. Before writing, the folder is read again; one that has no
  `songs/` or `animals/` folder, isn't empty and isn't the top of a card or
  drive (Documents, say) is written to only after the parent confirms, with
  the number of files and folders it would delete.
- If writing fails, the message names the file it stopped at and the
  browser's reason (a full card is reported as no space left), and says the
  folder is partly written.

What is written:

- `animals/<animal>.wav`: one file per matched question and sound, named after
  the sound in card-safe letters (`dog.wav`; the same name twice gets `-2`).
  Built by `studio/exporter.js` with the settings above: both parts mixed to
  mono, trimmed at -50 dBFS if asked, levelled to -18 dBFS plus or minus half
  the balance if asked, then `[silence] question [pause] sound [0.3 s]`,
  limited to -1 dBFS and written as 44.1 kHz 16-bit mono WAV.
- `animals/metadata.json`: `{"schemaVersion": 2, "name": "Animals",
  "shuffle": <Shuffle animal sounds>, "disabledSongs": []}`.
- With **Keep** on, a file of the same name in `animals/` is overwritten and
  the other animal files stay (exporting 10 of 13 animals keeps the other 3).
  With it off, `animals/` ends up holding exactly the exported files.
- `songs/<theme>/`: one folder per theme in the working area that has songs
  (a library theme added there is exported like any other, with its edits).
  The folder id is the library theme's id for an added library theme, else
  the theme's name in card-safe letters (`theme` when none are left; the same
  id twice gets `-2`). Each song is decoded like the animal parts and written
  as a 44.1 kHz 16-bit WAV, one at a time. File names are the song names
  with characters a FAT card refuses replaced; since the toy plays a folder
  in file-name order, the names get numbers (`01 - Name.wav`) when that order
  would differ from the order shown.
- `songs/<theme>/metadata.json`: `{"schemaVersion": 2, "name", "shuffle",
  "disabledSongs": <the unchecked songs>, "attribution": <the credit, if
  any>}`.
- `config.json`: `disabledThemes` is set to the folder ids of the exported
  themes that are off, plus kept themes that were already off; with the toy
  settings exported their keys are replaced too; every other key is kept. Without a `config.json` one is created only when a theme
  is off. A `config.json` that is not a JSON object stops the export before
  anything is written or deleted.
- An exported theme folder gets its songs and a new `metadata.json`; with
  **Keep** on its other songs stay (and play, unless turned off on the toy),
  with it off they are deleted. **Export** needs a theme with songs or a
  matched animal.

All animal files are built before anything is written, so a failed build
leaves the folder as it was; songs are converted while writing, so a failure
there leaves the folder partly written, and writing again finishes it. The
chosen folder is kept in the browser's IndexedDB (`settings` store); after a
browser restart Chrome asks again for permission when the folder is opened or
**Export** is pressed. Once done, the dialog lists the folder again and
reminds the parent to eject a card before removing it. A folder named `animals` or `songs` gets a warning, since Studio expects the
card's top folder.

## Shared content

Studio's shared library is the public bucket `gs://sweetyaar-studio-resources`
(project `sweetyaar`, `me-west1`, uniform access, public read for `allUsers`,
CORS allowing `GET` from any origin, objects served with
`Cache-Control: public, max-age=3600`):

```
songs/<theme>/<NN - Title>.wav        the songs of a song theme, played in name order
songs/<theme>/metadata.json           {schemaVersion, name, shuffle, disabledSongs, attribution}: the toy's
                                      metadata.json, its attribution the one-line credit (at most 160 bytes)
songs/<theme>/ATTRIBUTION.txt         the theme's attribution (its first line the same credit)
animal-sounds/<animal>.wav            the 13 animal sounds
animal-sounds/ATTRIBUTION.txt         the sounds' attribution
animal-prompts/<lang>/<animal>.wav    spoken questions per language: ar, en, fr, he (ElevenLabs)
animal-prompts/ATTRIBUTION.txt        the prompts' attribution
```

Every `ATTRIBUTION.txt` has the same format, and Studio shows it the same way
wherever it appears (`parseAttribution` in `studio/content.js`,
`attributionEl` in `studio/studio.js`):

- **The first line is the short attribution**, Markdown on one line, shown
  under the box's label (for example *Spoken questions generated with
  ElevenLabs*).
- **The other lines are the long attribution**, without the blank lines at
  their start and end (so a blank line can separate it from the first). When
  there is one, a small **ⓘ Credits** follows the short line; hovering it (or
  focusing it with the keyboard) shows the long attribution in a tooltip as
  wide as the box, which stays open while the pointer is on it so its links
  can be clicked.
- Only `[links](https://…)`, bare `https://` links, `**bold**` and `*italic*`
  are kept; `#` at a line's start is dropped and anything else, HTML
  included, is plain text. In the long part blank lines separate paragraphs
  and every line stays a line.

All files are 44.1 kHz mono 16-bit WAV. Studio reads the bucket directly
(`studio/content.js`): listings through the Cloud Storage JSON API
(`storage/v1/b/sweetyaar-studio-resources/o?prefix=…&delimiter=/`), files from
`https://storage.googleapis.com/sweetyaar-studio-resources/<path>`. A new
language is a new `animal-prompts/<lang>/` folder; a new animal is a new WAV
in `animal-sounds/` plus its line in `ATTRIBUTION.txt`. A new song theme is a new
`songs/<theme>/` folder with its songs, `metadata.json` and `ATTRIBUTION.txt`
(a theme with no songs is not listed); the AI-generated ones are made with
`content/ai_music/generate.py`. The prompts are
generated from `content/animal_prompts/prompts.json` (every language's
questions, voice and the shared ElevenLabs settings) by
`content/animal_prompts/generate.py`, which writes the whole `animal-prompts/`
folder to upload; see the README there. Nothing private belongs
in this bucket; admin data stays in the closed `sweetyaar-admin-resources`
(see [logging-and-debugging.md](logging-and-debugging.md)).

Upload with a cache header, for example:

```sh
gcloud storage cp *.wav gs://sweetyaar-studio-resources/animal-prompts/es/ --cache-control="public, max-age=3600"
```

One-time setup:

```sh
gcloud storage buckets create gs://sweetyaar-studio-resources --project=sweetyaar --location=me-west1 \
  --default-storage-class=STANDARD --uniform-bucket-level-access
gcloud storage buckets update gs://sweetyaar-studio-resources --cors-file=cors.json
#   cors.json: [{"origin": ["*"], "method": ["GET", "HEAD"], "responseHeader": ["Content-Type"], "maxAgeSeconds": 3600}]
gcloud storage buckets add-iam-policy-binding gs://sweetyaar-studio-resources --member=allUsers --role=roles/storage.objectViewer
```


## Planned areas

| Area | Purpose |
|---|---|
| Library | Themes, songs, recordings and animal sets being worked on. |
| Wave editor | Volume per theme. |
| Animal maker | Pause and gain per animal (the matching and building are in the Animals panel and Export). |
| On the toy | Rename, edit metadata or remove content on the connected toy. Needs the Wi-Fi content mode; today the catalog is read-only. |
| Export | Writing to the toy directly instead of a folder. |

## Open questions

- Pulling WAVs back from the toy may be impossible; the fallback is catalog only.
- Importing from a URL or YouTube cannot work from a static page (CORS and
  terms of service); file upload and recording come first.
- A project needs persistence (IndexedDB) so work survives a closed tab.
- The shared animal sounds are CC0 or Pixabay Content License. Pixabay does
  not allow redistributing its files unchanged on their own, and the public
  bucket makes them downloadable; accepted for now. The ElevenLabs prompts need a
  paid plan's commercial licence, and the voices are Voice Library voices
  whose owners may add terms.
