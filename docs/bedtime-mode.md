# SweetYaar Bedtime Mode

Bedtime mode is a parent-controlled local playback mode. It keeps bedtime
behavior simple: during configured bedtime hours, the toy can switch to one
bedtime theme and clamp local WAV volume so bedtime playback stays calm.

This is not a general scheduler. It has one daily window, one bedtime theme,
one volume cap, and one runtime on/off state.

## Parent Settings

Bedtime settings live in `SD:/config.json`:

```json
{
  "bedtime": {
    "enabled": true,
    "startTime": "18:30",
    "endTime": "06:30",
    "theme": "lullabies",
    "volumeCapPct": 45
  }
}
```

- `enabled`: master switch. When false, the toy behaves as it does without
  Bedtime mode.
- `startTime`: local clock time when automatic Bedtime mode starts. Default:
  `18:30`.
- `endTime`: local clock time when automatic Bedtime mode ends. Default:
  `06:30`.
- `theme`: a single enabled song theme to use while Bedtime mode is active.
- `volumeCapPct`: maximum effective local WAV volume while Bedtime mode is
  active. This cap applies to song and animal WAV playback. It does not rewrite
  the saved default volume or current volume slider value.
  The checked-in SD-card template uses `45` as the initial cap. The cap is an
  effective playback ceiling only; when Bedtime mode ends, the toy returns to
  the uncapped parent-selected volume.

The bedtime window may cross midnight, which is the normal case. Parents may
also choose unusual windows, such as `10:00` to `13:00`; the app warns about
unusual values but does not block them.

## Runtime Behavior

Bedtime mode has two layers:

- The parent setting `bedtime.enabled` decides whether the feature exists at
  all.
- The runtime Bedtime state decides whether the toy is currently in Bedtime
  mode.

When `bedtime.enabled` is true and the device has reliable local clock time:

- Enter Bedtime mode automatically at `startTime`.
- Leave Bedtime mode automatically at `endTime`.
- While Bedtime mode is active, local song playback uses the configured bedtime
  theme.
- While Bedtime mode is active, local song and animal playback use
  `min(currentVolumePct, volumeCapPct)` as the effective WAV volume.
- Animal sound selection is otherwise unaffected.
- Classic Bluetooth A2DP streaming is unaffected. Bedtime theme selection and
  volume capping do not apply while BT audio is connected.

If `bedtime.enabled` is false, or if local clock time is unknown or unreliable,
Bedtime mode is treated as inactive. The toy uses normal theme and volume
behavior.

If the configured bedtime theme is missing, disabled, or has no playable WAV
files, firmware should log a serial warning and fall back to the normal active
theme for song playback. Bedtime mode still remains active in this fallback, so
the bedtime volume cap still applies to local song and animal WAV playback.

## Parent Overrides

The parent app exposes a Bedtime/Daytime mode card on the main Ready screen
whenever the Bedtime master setting is enabled. The card shows the current
runtime state and uses a small glowing moon icon anywhere a compact Bedtime
indicator is needed.

Pressing the mode card toggles the runtime Bedtime state only. It does not
change the saved `bedtime.enabled` setting.

- If a parent turns Bedtime mode on during the day, it stays on until the next
  configured `endTime` occurrence, or until deep sleep/reboot clears the runtime
  override.
- If a parent turns Bedtime mode off during bedtime hours, that override is
  respected for the current awake session until the next automatic boundary or
  deep sleep/reboot.
- If a parent changes the active theme while Bedtime mode is active, that theme
  selection overrides Bedtime mode for the current awake session.
- After deep sleep wake, runtime overrides are cleared. The toy returns to
  automatic Bedtime mode decisions based on saved settings and reliable local
  time.

Children cannot change themes from the physical toy buttons, so parent app
actions are the only runtime overrides.

## Time Sync

The toy does not assume local time on a fresh boot. Whenever a phone, computer,
or other controller connects over BLE, the controller sends its current local
time context. The controller's time wins, so traveling across time zones is
handled by reconnecting the parent app.

The BLE config command should stay simple, for example:

```json
{
  "op": "syncTime",
  "epochSec": 1780595400,
  "tzOffsetMin": 180
}
```

- `epochSec`: controller wall-clock Unix time.
- `tzOffsetMin`: controller local timezone offset from UTC at the moment of
  sync.

Firmware should track whether the local clock is reliable. A clock can be
considered reliable after a successful BLE time sync, or after a deep-sleep wake
if implementation retains enough RTC-backed time state to trust it. If the clock
is not reliable, Bedtime mode is inactive even if the saved setting is enabled.

## Parent App UX

Main Ready screen:

- If the Bedtime master setting is off, do not show the mode card.
- If Bedtime is enabled and reliable time is available, show a mode card near
  the local controls:
  - `Daytime`: daytime artwork, calm/neutral state, tap to manually enable
    Bedtime mode for the current awake session.
  - `Bedtime`: bedtime artwork, active/glowing state, small glowing moon icon,
    tap to manually disable Bedtime mode for the current awake session.
- If Bedtime is enabled but reliable local time is unavailable, show a muted
  `Time unknown` card. Use an icon that suggests a broken watch, clock alert, or
  unavailable time, plus clear text that the toy needs a time sync. This state
  should not pretend the toy is in Daytime mode. Tapping can retry/request time
  sync, but should not force a runtime Bedtime toggle until the clock is
  reliable.
- When Bedtime mode is active and volume is capped, keep the parent's normal
  volume value intact but prevent the Ready-screen volume slider from moving
  past the cap. Mark the capped region in yellow and show a small glowing moon
  indicator above the cap.
- If the theme selector is visible while Bedtime mode is enabled, mark the
  configured bedtime theme with a small glowing moon icon.

Settings screen:

- Add a `Bedtime mode` section.
- Include a master toggle.
- Include a single bedtime-theme selector.
- Include a volume-cap control.
- Include two time controls: `Starts` and `Ends`.
- Use native mobile time-picker semantics where possible, such as
  `input[type=time]` styled as tappable rows. Native time inputs give users a
  familiar picker, respect locale display, and still provide a precise `HH:mm`
  value for firmware.
- Do not use a custom slider as the primary time control. Sliders are good for
  ranges like volume, but exact times need picker/input affordances and
  accessible manual entry.
- Mark unusual but allowed hours in orange: `startTime` before `16:00`, or
  `endTime` after `12:00`.

The app should send a time-sync message during connection before relying on
automatic Bedtime state.
