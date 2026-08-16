# SweetYaar Mobile App

The SweetYaar mobile app is the parent's remote control for the toy. It can
start and stop local audio, choose what the toy plays, adjust its volume, pause
the child's buttons, and change persistent settings such as the device name,
Bedtime schedule, and sleep timeouts.

The app connects directly to the toy over Bluetooth Low Energy (BLE). This is
separate from the Classic Bluetooth connection used when SweetYaar acts as a
speaker: the app controls audio stored on the microSD card, while a phone or
computer connected as an audio source controls its own stream. The app does not
upload audio files or firmware.

Parents open the remote as a website and may install it on a supported device
for an app-like launcher and offline access. There is no account, cloud service,
Wi-Fi setup, native-app package, or application server. See
[Firmware](firmware.md) for the behavior implemented by the toy and
[Hardware](hardware.md) for the board and electrical design.

## Connecting to the toy

The toy must be powered on and nearby. Open the app in a browser with Web
Bluetooth support, press **Connect to SweetYaar**, and select the toy in the
browser's device chooser. The current interface directs parents to Chrome or
Edge on desktop or Android when Web Bluetooth is unavailable.

Web Bluetooth requires a secure origin. The deployed HTTPS site and
`http://localhost` are valid; a page opened through `file://` or an ordinary
`http://192.168.x.x` LAN address is not. Bluetooth permissions are associated
with the site's origin, so moving the app to a different domain requires the
parent to grant access again.

After connecting, the app reads the current volume, theme, playback state, and
available content from the toy. It also sends the phone or computer's time and
UTC offset so the firmware can evaluate the Bedtime schedule. Status updates
then arrive over BLE and keep the screen synchronized with physical-button and
playback activity on the toy.

If the toy disconnects, restarts, or enters deep sleep, the app returns to its
opening screen and the parent must reconnect. Installing the app does not
remove the browser's Bluetooth permission or connection requirements.

## The parent remote

Once connected, the Ready screen shows what the toy is doing and provides the
controls used during normal local playback.

| Control | Behavior |
|---|---|
| **Play song** | Starts a song from the active theme. Pressing it again advances to the next song. |
| **Animal** | Plays one animal sound. Pressing it again advances to another sound. |
| **Stop** | Stops local playback. |
| **Loop songs** | Continues with the next song when one finishes. Looping is temporary and resets after Stop, animal playback, Quiet time, Bluetooth speaker mode, or reboot. |
| **Volume** | Changes the current local WAV volume. It does not control audio streamed over Classic Bluetooth. |
| **Theme** | Changes the song theme for the current awake session. Only enabled themes containing playable audio are offered. |
| **Quiet time** | Stops local playback and ignores physical-button and app playback commands for ten minutes, or until the parent cancels it. |
| **Daytime / Bedtime** | Shows the current Bedtime state and allows a temporary manual override when Bedtime mode and the toy's clock are available. |

The Ready screen reflects playback started from either the app or the physical
buttons. It also displays warnings reported by the firmware, such as content or
playback problems, rather than silently leaving the controls out of sync.

When another device is connected through Classic Bluetooth, the app changes to
the **Used as a speaker** screen. Local playback, theme, volume, loop, and Quiet
time controls remain unavailable until that audio connection ends. Stream
volume belongs to the phone, tablet, or computer sending the audio.

## Settings and content

The Settings screen reads the toy's saved configuration and its SD-card content
catalog. A parent can make several changes and then write them together with
the **Save** button.

| Area | Available settings |
|---|---|
| General | Device name, default local volume, and default song theme. |
| Bedtime mode | Enable or disable the feature, choose its theme, set the daily window, and set its volume cap. |
| Sleep | Enable automatic sleep and set the normal-idle, vibration-wake-idle, and connected-BLE-idle timeouts. |
| Themes | Enable or disable song themes and turn shuffling on or off. |
| Songs and animals | Inspect detected files and validation errors, and enable or disable individual recordings. |

Most saved settings live in `/config.json` or the relevant `metadata.json` file
on the microSD card. The device name is stored in the ESP32's non-volatile
storage so changing cards does not rename the toy. A new name appears after the
app reconnects.

The app manages the catalog already present on the card; it does not add,
delete, or replace WAV files. New content must be copied to the microSD card
directly. The firmware discovers manual card changes at its next boot. During a
BLE session, the app scans the catalog the first time Settings opens and keeps
that result in memory until the toy disconnects.

The Ready-screen volume and theme are current-session controls. The settings
screen's default volume and theme are the values restored by the firmware on a
future boot. Changing one does not silently change the other.

## Bedtime mode

Bedtime mode modifies local playback during one parent-defined daily window.
It selects a bedtime song theme and caps the effective volume of both songs and
animal sounds. It does not affect Classic Bluetooth audio or overwrite the
normal volume setting.

The app reads and writes this object inside `SD:/config.json` through the BLE
configuration API:

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

`startTime` and `endTime` are local `HH:mm` values. The window may cross
midnight, and equal start and end times mean an all-day window. The settings
screen warns about a start before 16:00 or an end after 12:00, but it does not
reject either value. The bedtime theme must be an enabled song theme, and the
volume cap is a percentage from 0 to 100.

While the mode is active, local volume is
`min(currentVolumePct, volumeCapPct)`. The Ready-screen slider shows the cap and
does not send a value above it, but the parent's normal volume remains intact
for Daytime mode. If the bedtime theme is missing, disabled, or empty, songs
fall back to the normal active theme while the cap still applies. Animal
selection is unchanged.

The Bedtime card appears on the Ready screen only when the feature is enabled.
A parent may switch the current state between Daytime and Bedtime without
changing the saved schedule. That manual choice lasts until the next automatic
boundary or a reboot. Selecting a different Ready-screen theme while Bedtime is
active changes the effective theme for the rest of that awake session; the
volume cap remains active.

The ESP32 does not retain wall-clock time through a cold boot. On every BLE
connection, the app sends the controller's current time and UTC offset:

```json
{
  "op": "syncTime",
  "epochSec": 1780595400,
  "tzOffsetMin": 180
}
```

This also updates the toy after travel or a timezone change. Until the firmware
has reliable time, Bedtime mode remains inactive and the card displays
`clock not set`; the app does not guess or force the scheduled state.

## Installation and offline use

SweetYaar is a Progressive Web App, which means a supported browser can place
the remote on the home screen or application launcher. Installation is
optional: the same remote works in a normal browser tab.

After one successful online load, the service worker keeps the application
shell, manifest, icons, and listed UI images in a local cache. Navigation uses
a network-first strategy, falling back to the cached app when the network is
unavailable. Static precached assets are shown immediately from cache and
refreshed in the background. The BLE connection itself is local and does not
need Internet access.

The app displays its own install banner only after the browser supplies a
`beforeinstallprompt` event. If the banner does not appear, the app may already
be installed or the browser may instead expose installation through its address
bar or menu. Installation alone cannot add Web Bluetooth support to a browser
that does not provide it.

> [!WARNING]
> **TBD — Complete offline artwork:** `bedtime-day-art.png` and
> `bedtime-night-art.png` are used by the Ready screen but are not currently in
> `sw.js`'s precache list. Add them before treating both Bedtime illustrations
> as guaranteed offline assets.

The app does not force a page reload while BLE is active. A newly deployed
version is used on a later reload or launch. Whenever the application shell or
precache list changes, increment `CACHE_VERSION` in `public/sw.js`; activation
then removes older SweetYaar caches.

## How the app is organized

The parent remote is deliberately a small static application with no framework
or build step. Its production files are:

| Path | Responsibility |
|---|---|
| `public/index.html` | The complete screen markup, component styles, application state, Web Bluetooth client, and UI behavior. This is the single source file for the app itself. |
| `public/tokens.css` | Shared colors, typography, radii, shadows, and responsive spacing used by `index.html`. |
| `public/manifest.webmanifest` | Installed-app name, scope, portrait presentation, colors, and icon declarations. |
| `public/sw.js` | Offline cache contents, update version, and request strategies. |
| `public/assets/` | Browser-ready artwork, control icons, favicons, and install icons. |
| `public/CNAME` | The custom domain published with the Pages artifact. |

The interface has four states: the opening connection screen, the Ready remote,
the Bluetooth-streaming status screen, and Settings. `index.html` owns the
transitions between them and communicates with the BLE service implemented by
`src/BLEParentService.*`. It first reads the live characteristics used for
volume, theme, Quiet time, status, and commands, then uses the configuration
request/response characteristics for settings and paged content scans.

The app subscribes to firmware notifications rather than assuming every write
succeeded. Older firmware without the optional notice characteristic can still
connect; firmware missing the required service or control characteristics is
reported as needing an upgrade.

## Visual design and assets

The interface is a calm, friendly control surface for a children's toy rather
than a marketing page. It is designed around a 390 px mobile content width and
is capped at 430 px on larger screens. The layout uses `100dvh`, remains
scrollable on short displays, keeps configurable text as live text, and uses
touch targets of at least 44 px. Decorative images have empty alternative text,
while actual controls retain native button, range, time, and switch semantics.

`public/tokens.css` is the runtime source of truth for shared visual values.
Component-specific layout and screen styling remain beside their markup in
`public/index.html`. The current palette uses soft off-white surfaces, teal
primary actions, pastel playback cards, rounded system fonts, 16 px card radii,
and restrained shadows.

Editable assets are kept out of the deployed `public/` directory:

| Path | Purpose |
|---|---|
| `design/sweetyaar-mobile/assets/source/` | High-resolution or editable source material for the app icon, favicon, header, and footer artwork. |
| `design/sweetyaar-mobile/assets/final/` | Prepared reference exports for the opening, streaming, header, footer, and control artwork. |
| `public/assets/` | The exact browser-ready files used by the deployed app. |

Some retained design exports are byte-identical to deployed files with newer
names:

| Retained design export | Deployed asset |
|---|---|
| `opening-hero.png` | `opening-hero-art.png` |
| `streaming-hero.png` | `streaming-toy-scene.png` |
| `ready-bottom-overlay.png` | `ready-bottom-graphics.png` |
| `ready-bottom-overlay@2x.png` | `ready-bottom-graphics@2x.png` |
| `icon-theme.png` | `icon-theme.png` |

Other deployed controls and header artwork are newer or differently sized
variants. `public/index.html` and `public/assets/` are therefore production
truth; the design folders preserve material useful for a future revision, not
a second runnable app.

There is intentionally no checked-in image generator. To change an image,
start with the closest retained source, reference export, or deployed asset;
keep a high-resolution reusable result under `assets/source/`; keep a useful
approved reference under `assets/final/`; and export the browser-ready version
to `public/assets/`. Update its references in `index.html`, the manifest, and
the service-worker precache list as applicable. App-icon, maskable-icon, and
favicon sizes are exported manually and must be checked visually after changes.

## Local development and deployment

Serve the checked-in `public/` directory directly from the repository root:

```bash
/Users/zmoshe/proj/sweetyaar/.venv/bin/python -m http.server --directory public 8000
```

Then open `http://localhost:8000/`. `localhost` is treated as a secure context,
so it can register the service worker and use Web Bluetooth without a local TLS
certificate.

For a manual browser check, connect from Chrome or Edge, exercise the Ready and
Settings screens, and inspect the Application panel to confirm that the
manifest and service worker loaded. Reload once online, switch DevTools to
offline mode, and reload again to verify the cached shell. Finally reconnect to
the toy from the installed or offline app; offline rendering does not by itself
prove that Bluetooth permissions and GATT behavior work.

Production is deployed by `.github/workflows/pages.yml`. Relevant pushes to
`main` upload only `public/` to GitHub Pages, so files under `design/`, `docs/`,
and the firmware tree are never part of the web artifact. Pages must use GitHub
Actions as its publishing source. Relative paths in the manifest and service
worker allow the same files to run from the Pages project path, the custom HTTPS
domain, or a local server rooted at `public/`.

## Testing changes

The app tests execute the real JavaScript embedded in `public/index.html`
against a mocked DOM and Web Bluetooth device. They cover connection outcomes,
live controls, Bluetooth-streaming lockout, settings scans and saves, and the
Bedtime flow. Separate PWA checks validate the manifest, icons, design tokens,
precache contents, and offline-shell contract.

Run the app-focused regression tests from the repository root:

```bash
uv run python -m pytest tests/test_parent_app.py tests/test_parent_app_pwa.py
```

Run the entire project suite with:

```bash
uv run python -m pytest
```

Automated tests do not grant real browser permissions, install the app, or
exercise a physical BLE radio. Changes to connection behavior still require a
manual check on the intended HTTPS origin and, when firmware interaction has
changed, the real-device BLE smoke tests described in
[Firmware](firmware.md#testing-changes).
