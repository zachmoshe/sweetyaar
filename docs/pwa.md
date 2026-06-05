# SweetYaar Parent Remote PWA

The parent remote is a static Progressive Web App served from `docs/`. It can
be installed by browsers that support PWAs and can reload from cache after one
successful online visit.

## Serving Requirements

Serve the app from a secure origin:

- Production: GitHub Pages from the repository `docs/` folder.
- Local development: `http://localhost:<port>/` or another loopback URL.

Do not test PWA or Web Bluetooth behavior from `file://` or from a plain
`http://192.168.x.x` LAN URL. Service workers and Web Bluetooth require a
secure context, and browser permissions/cache state are tied to the origin. If
the production origin changes, parents should expect to reconnect Bluetooth and
possibly reinstall the app.

The manifest and service worker use relative paths so the same files work from a
GitHub Pages project path, a custom HTTPS domain, or a local server rooted at
`docs/`.

## Local Testing

From the repository root:

```bash
/Users/zmoshe/proj/sweetyaar/.venv/bin/python -m http.server --directory docs 8000
```

Then open:

```text
http://localhost:8000/
```

In Chrome or Edge:

1. Open DevTools > Application.
2. Confirm `manifest.webmanifest` is loaded and installable.
3. Confirm `sw.js` is registered for the current scope.
4. Reload once while online.
5. Look for the browser install icon/menu item or the in-app install banner.
6. Enable offline mode in DevTools and reload again.
7. Confirm the app shell and images still render.

Chrome does not always show a large built-in install message. The app shows an
install banner only after the browser fires `beforeinstallprompt`, which means
the current origin is secure, the manifest/service worker are valid, and the app
is not already installed. If the banner does not appear, check Chrome's address
bar install icon, the three-dot menu, and DevTools > Application > Manifest.

For Bluetooth, use Chrome or Edge on desktop or Android. After loading the app
from the intended HTTPS origin, install it, disconnect network access, launch the
installed app, and confirm the BLE connection flow still opens from the Connect
button. Web Bluetooth support is browser-specific; an installable PWA does not
make unsupported browsers support BLE.

## Cache And Updates

`sw.js` precaches the static app shell:

- `index.html`
- `manifest.webmanifest`
- PWA icons
- UI images in `docs/assets/`

Navigation requests use a network-first strategy with cached fallback. This
keeps online parents moving to the newest app instead of staying pinned to an
old cached `index.html`. Static assets use cached responses with a background
refresh.

When changing the app shell or asset list, update `CACHE_VERSION` in `sw.js`.
The service worker deletes older SweetYaar caches during activation. The app
does not force a page reload during an active BLE session; the next browser
reload or app launch should use the updated shell.
