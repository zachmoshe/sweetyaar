# SweetYaar Mobile App Design Spec

This package translates the three-screen mock into implementation-ready guidance for a responsive web app. The design target is a friendly parent remote for a small toy: soft, rounded, tactile, and calm. Build the app as a real mobile-first control surface, not a marketing page.

## Source And Scale

- Source mock: `/Users/zmoshe/Downloads/after.png`
- Native extracted screen width: `432px`
- Recommended CSS design width: `390px`
- Responsive shell: `width: min(100vw, 430px)` and centered on desktop/laptop.
- Never hard-code the viewport height. The background stretches; the top art is pinned to the top; the bottom art is pinned to the bottom.

## Final Assets

Use only the production assets in `design/sweetyaar-mobile/assets/final/`.

| Asset | Size | Transparency | Use |
|---|---:|---|---|
| `top-overlay.png` | `428 x 188` | Yes | Generated header sky with decorative leaves, star, right cloud, and a transparent scalloped bottom edge. Pin to top and scale by width only. |
| `top-overlay@2x.png` | `856 x 376` | Yes | Retina version of `top-overlay.png`; display at `428 x 188` CSS px. |
| `ready-bottom-overlay.png` | `428 x 134` | Yes | Ready screen generated bottom hill and toys. Pin to bottom and scale by width only. |
| `ready-bottom-overlay@2x.png` | `856 x 268` | Yes | Retina version of `ready-bottom-overlay.png`; display at `428 x 134` CSS px. |
| `opening-hero.png` | `432 x 245` | Yes | Opening screen toy speaker scene. Center in content flow. |
| `streaming-hero.png` | `432 x 322` | Yes | Bluetooth streaming music scene. Center in content flow. |
| `icon-song.png` | `64 x 64` | Yes | Ready screen song control icon, centered on a transparent canvas. |
| `icon-teddy.png` | `76 x 76` | Yes | Ready screen animal sound icon, centered on a transparent canvas. |
| `icon-stop.png` | `64 x 64` | Yes | Ready screen stop control icon, centered on a transparent canvas. |
| `icon-pause-moon.png` | `76 x 76` | Yes | Pause mode panel illustration, centered on a transparent canvas. |
| `icon-theme.png` | `56 x 56` | Yes | Full uncropped Theme book icon on a transparent canvas. |

The asset generation script is `design/sweetyaar-mobile/scripts/create_design_assets.py`. Re-run it only if the source mock changes.

## Typography

Use rounded system fonts first; load `Baloo 2`/`Nunito` only as optional web fallbacks:

```css
@import url("https://fonts.googleapis.com/css2?family=Baloo+2:wght@700;800&family=Nunito:wght@400;600;700;800&display=swap");
```

- App title: `"Arial Rounded MT Bold", "Avenir Next Rounded", "Baloo 2"`, `35px` to `40px`, `900`, line-height `0.95`, color `#087B78`, letter-spacing `0`.
- Subtitle: same rounded display stack, `18px` to `22px`, `850`, color `#08716F`, line-height `1.0`.
- Card titles: `Nunito`, `18px`, `800`.
- Body copy: `Nunito`, `15px`, `600`, line-height `1.35`.
- Button labels: `Nunito`, `16px` to `19px`, `800`.

Use `tokens.css` as the canonical token source.

## Layout Model

Use this layer order:

1. App background: warm `#FCF8F3` to `#FDF4EB` gradient with subtle pastel radial circles.
2. Decorative overlays: `top-overlay.png` and, on the Ready screen only, `ready-bottom-overlay.png`.
3. Header text and controls.
4. Native browser/PWA safe area.

Core CSS:

```css
.sweetyaar-app {
  position: relative;
  width: min(100vw, 430px);
  min-height: 100dvh;
  margin: 0 auto;
  overflow: hidden;
  background:
    radial-gradient(circle at 83% 18%, rgba(141, 217, 205, 0.15) 0 4.7rem, transparent 5rem),
    radial-gradient(circle at 12% 44%, rgba(251, 223, 126, 0.14) 0 7rem, transparent 7.35rem),
    radial-gradient(circle at 74% 68%, rgba(255, 204, 221, 0.12) 0 5.8rem, transparent 6.15rem),
    radial-gradient(circle at 24% 88%, rgba(184, 219, 129, 0.12) 0 5.3rem, transparent 5.65rem),
    linear-gradient(180deg, #FCF8F3 0%, #FDF4EB 100%);
}

.sweetyaar-app::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  aspect-ratio: 428 / 188;
  background: url("./assets/final/top-overlay.png") center top / 100% auto no-repeat;
  pointer-events: none;
}

.screen-ready .bottom-art {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  aspect-ratio: 428 / 134;
  background: url("./assets/final/ready-bottom-overlay.png") center bottom / 100% auto no-repeat;
  pointer-events: none;
}
```

Header:

- Top padding: `max(58px, env(safe-area-inset-top) + 46px)`.
- Use live text for the brand so the toy name can be configured. Do not bake `SweetYaar` or `Parent remote` into the header image.
- Keep the brand centered around `top: 52px` on a `428px` design surface.
- Header must sit above the top overlay so the text is crisp.

Main content:

- Horizontal padding: `18px`.
- Default content starts at `51px` below the header block.
- Opening and streaming hero art is full-bleed across the app shell: set width to `calc(100% + side padding + side padding)` and offset by negative side padding.
- Cards are `surface-card`: radius `16px`, background `rgba(255,255,255,.93)`, border `rgba(218,205,190,.45)`, shadow `0 10px 22px rgba(93,66,35,.12), 0 2px 5px rgba(93,66,35,.08)`.
- On short phones, allow vertical scrolling. Do not scale font size down by viewport width.

## Components

Status card:

- Normal card: full width, min-height `76px`, padding `14px 17px`, grid columns `56px 1fr 14px`.
- Opening large card: min-height `138px`, padding `22px`, grid columns `70px 1fr`.
- Bluetooth icon circle: `54px`, border-radius `999px`, white lucide `Bluetooth`, stroke `2.7`.
- Disconnected circle: `#91999C`, red dot `#F04456`, dot size `13px`, lower-right attached to circle.
- Connected streaming circle: gradient `#0C7DF0` to `#006BDB`.
- Ready circle: gradient `#5FD092` to `#39B975`.
- Online dot: `12px`, color `#56BD48`.

Primary CTA:

- Width `284px`, height `63px`, centered.
- Border radius `12px`.
- Blue gradient `#0677E8` to `#006BDB`.
- Shadow `0 8px 16px rgba(0,95,210,.27)`.
- Label `19px`, `800`, white.
- Left icon: lucide `Bluetooth`, `32px`, white.

Control buttons:

- Grid: `3` columns, gap `16px`, margin-top `22px`.
- Each control: height `105px`, radius `13px`, shadow from `--sy-shadow-control`.
- Song background: `linear-gradient(160deg, #C5EEEB, #D6F1EA)`.
- Animal background: `linear-gradient(160deg, #FFDF76, #FFD261)`.
- Stop background: `linear-gradient(160deg, #FFD2DD, #F5B8C5)`.
- Icon image boxes: song `64px`, teddy `76px`, stop `64px`; the visible artwork is already centered inside each transparent PNG.
- Label margin-top `4px`, font `15px`, weight `800`, black.

Volume card:

- Height `68px`, margin-top `20px`.
- Left lucide `Volume2`, `34px`, color `#119B96`.
- Label top row: `Volume`, `15px`, `800`; value right aligned, `15px`, `800`.
- Track height `7px`, radius `999px`.
- Filled track color `#36B9AB`, unfilled `#D6D6D3`.
- Thumb: `28px`, white, subtle shadow.

Theme card:

- Height `64px`, margin-top `12px`.
- Left lucide `BookOpen`, `34px`, color `#7B62C7`.
- Label `Theme`, `15px`, `700`.
- Selected theme `Lullabies`, `18px`, `800`, color `#7B62C7`.
- Right lucide `ChevronDown`, `24px`, color `#717981`.

Pause panel:

- Height `118px`, margin-top `20px`.
- Background `#FFE7ED` with the standard card border and shadow.
- Left illustration: `icon-pause-moon.png`, display at `56px`; the visible artwork is centered inside the transparent PNG.
- Heading `Pause mode`, `18px`, `800`, color `#D83E67`.
- Body `12px`, `700`, line-height `1.25`.
- Primary pause button: text `Pause for 10 mins`, width about `148px`, min-height `44px`, radius `10px`, gradient `#E9527C` to `#D93E6B`, white `14px/800`, no wrapping.
- Cancel button: width `147px`, height `44px`, radius `10px`, white background, text `#30324A`.

Use lucide icons for `Bluetooth`, `Info`, `Volume2`, `BookOpen`, and `ChevronDown`. Use the provided PNGs for the 3D/emoji-style controls.

## Screen Compositions

Opening:

- Header as above.
- Large disconnected status card first.
- CTA margin-top `24px`.
- `opening-hero.png`: width `100%`, margin-top `20px`.
- Info card: height `76px`, margin-top `14px`, icon `Info` at `30px`, text centered vertically.
- Body copy: “Connect to control songs, animal sounds, volume, themes, and pause mode.”
- Footer copy: “Make sure SweetYaar is powered on and nearby.”

Bluetooth Streaming:

- Normal status card first, text “BT connected” and “SweetYaar is streaming audio.”
- `streaming-hero.png`: width `100%`, margin-top `19px`.
- Bottom info card: min-height `149px`, margin-top `14px`.
- Pink music badge: `54px`, gradient `#F06A92` to `#E44E79`, white music icon.
- Title copy: “SweetYaar is streaming music now.”
- Body copy: “Set volume from the streaming device. Remote controls return when the streaming device disconnects.”
- Do not show local controls on this screen.

Ready To Play:

- Normal status card first, text “Ready to play” only; do not show secondary copy in that state.
- Three control buttons below.
- Volume card below controls.
- Theme card below volume.
- Pause panel below theme.
- Add `.bottom-art` as the final child of the screen root; it is absolute, bottom-aligned, and outside content flow.
- Content bottom padding should be at least `112px` so controls do not collide with the bottom toy art on short screens.

## Responsive Behavior

- Mobile: app fills width and height. Use `100dvh`, not `100vh`, so browser chrome changes do not crop the design.
- Laptop: keep the same single-column app shell, centered. Optional preview frame may be added outside `.sweetyaar-app`, but never inside it.
- Very short screens: enable `overflow-y: auto` on `.sweetyaar-app`; keep top and bottom overlays pinned. The Ready screen should scroll content above the bottom art if needed.
- Wide screens: do not stretch the app past `430px`; the design depends on compact proportions.
- Avoid CSS `vw` font scaling. Scale art by width, not type.

## Interaction States

- Button hover on desktop: reduce translateY by `-1px` and slightly increase shadow.
- Button active/tap: translateY `1px`, use `--sy-shadow-press`.
- Disabled controls during Bluetooth streaming: do not render them. The streaming screen is the disabled state.
- Touch targets: minimum `44px`.
- Decorative assets should use `aria-hidden="true"`.
