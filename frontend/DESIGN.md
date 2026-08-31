# DESIGN — "STUDIO"

The NetScan panel as a calm, near-monochrome instrument — in the spirit of an
Apple system app and [curated.supply](https://www.curated.supply/). Near-black ink
on a warm off-white ground, hairline rules, generous rhythm, restraint. Weight and
space carry the hierarchy; **no accent hue** — red is held back for a real alert or
a destructive action. Fluid, interruptible spring motion, all of it optional under
`prefers-reduced-motion`.

This supersedes v8 "CHART" (hydrographic-chart metaphor: buff paper, a ruled
graticule, carmine spot-colour, Big Shoulders / Overpass, nautical-survey copy),
which the owner replaced wholesale. Direction and the four foundational choices
(monochrome palette, Inter, softened copy, add `motion`) were set with the owner.

## Foundations

### Palette — tokens in `src/index.css`, Tailwind names in `tailwind.config.js`

`:root` is **light**; `:root.dark` opts into the night palette (`useTheme.ts`
toggles `.dark`, default light).

| Token | Light | Dark | Role |
|---|---|---|---|
| `--bg` / `--paper` | `250 250 249` | `12 12 12` | the page — warm off-white, no texture |
| `--surface` | `255 255 255` | `24 24 24` | a card (`.panel`) |
| `--surface-2` | `245 245 243` | `33 33 33` | input · row hover · sunken cell (`.core`) |
| `--surface-3` | `236 236 233` | `44 44 44` | skeleton |
| `--fg` | `23 23 23` | `245 245 245` | primary ink — near-black |
| `--fg-2` | `82 82 82` | `168 168 168` | secondary |
| `--fg-3` | `140 140 137` | `115 115 115` | muted · `.label` / `.key` · meta |
| `--edge` | `231 231 228` | `38 38 38` | hairline |
| `--edge-2` | `214 214 210` | `58 58 58` | control border |
| `--alert` | `200 38 38` | `248 113 113` | error · destructive · needs-action |

**Legacy tokens kept, remapped:** `--signal` and `--water` both resolve to `--fg`,
so every "active / selected / online" state that older classes expressed as a spot
colour now reads as ink. `signal-bg` / `signal-fg` = ink fill / surface text.
`--grid` is unused (the graticule is gone). Per-person colours still come from
`PERSON_COLORS` in `lib/format.ts`.

### Type — Inter (`index.html`, Google Fonts) + system fallback

- **Inter** — the whole UI. `font-sans`, `font-display` (weight 600, `-0.021em`
  tracking for titles / big figures), `font-display-lt` (500). `.key` is 11px
  uppercase, `0.04em` — quieter than the old chart register. Body 14px / 1.5.
- **System monospace** (`ui-monospace, "SF Mono", Menlo, Consolas`) — addresses,
  MAC / IP, timestamps, counts. No monospace-as-costume; it is only ever data.

### Depth & shape

`--e1` a hairline ring; `--e2` a hairline + `0 1px 2px` lift (`.panel`); `--e3`
(modals) a soft `0 24px 60px`. Radii: cards `12px`, controls `8px`, chips `6px`,
marks / avatars full. Focus ring: `0 0 0 3px rgb(--fg / .14)` + ink border.

## Chrome — `components/Shell.tsx`

**Desktop:** a `232px` sidebar on `--surface` — `AppMark` + `NetScan` wordmark,
then the nav as rounded items with a `--surface-2` selection fill behind the
active one (no number codes, no leader tick). Foot: primary **Scan** button
(editors), account + role, version. A sticky **translucent toolbar**
(`bg-surface/75` + `backdrop-blur-xl`) carries the section title (plain sentence
case) and quiet mono vitals — subnet · online/total · last scan · clock. Main
column `max-w-[1240px]`.

**Mobile:** translucent top bar (mark + online/total + Scan + sign-out) with a
scrollable vitals line → translucent bottom tab bar, active tab = filled icon +
ink label.

**Scan in progress:** a 2px indeterminate `scan-bar` under the toolbar (replaces
the old survey line).

## Motion — `src/lib/motion.ts` (adds `motion`, Framer Motion)

- `snappy` — `{spring, bounce:0, duration:0.35}` — the default; route changes,
  toggles, dialogs.
- `sheetSpring` — `{spring, bounce:0.18, duration:0.42}` — surfaces that "arrive":
  `Sheet` (drag-to-dismiss with velocity), `Dialog` on mobile.
- Route body: `AnimatePresence mode="wait"` + fade/rise (`useViewTransition`).
- `Toggle` — animated knob spring. `Toaster` — `AnimatePresence` spring in/out.
- `useReducedMotion()` everywhere → opacity-only or instant; the CSS keyframes in
  `index.css` (`view-in`, `sheet-up`, …) remain as the no-JS / reduced fallback.

## Components — `components/ui.tsx`

Export names and prop signatures are unchanged from "CHART" — only the visuals.
`.panel` a 12px card; `.core` a sunken cell; `.btn-primary` the ink fill,
`.btn-danger` red; `.input` a sunken cell with an ink focus border + soft ring;
`.tag` a 6px chip (`tag-signal` = ink fill); `.signal-mark` a small dot
(`--on` ink, `--alert` red, `--off` a hollow hairline ring that keeps its slot).
`QueryState` copy: "Couldn't load" / "Something went wrong." (`common.*` keys).

## Key surfaces

- **Dashboard** — an **overview card**: a large online count `/ total`, then
  Present · New today · Internet uptime + latency spark, split by hairlines; a red
  "N · Review" cell appended only when devices await review. Then search + a
  segmented filter → the device list.
- **Device list** (`components/DeviceListView.tsx`) — one `.panel` with `divide-y`
  hairlines. Columns: status dot · thumbnail · name + sub · address · owner · type
  · OS · last-seen (the old chart-coordinate "Ref" column is gone). Online rows
  are full-strength ink; offline rows dim under an `Offline · n` rule. Row hover
  `--surface-2`; a new device gets one soft `row-flash`.
- **People** (`components/PresenceHeatmap.tsx`) — the strip-recorder stays; present
  intervals are solid **ink** bars, hairline 6-hour gridlines, an ink "now" needle.
- **Settings** — the side-list category nav (rounded items, no codes); every
  section restyled to the new tokens. `Channel` is a rounded bordered card.
- **Login** — `AppMark` + wordmark over a single `.panel`, plain "Sign in".

## Copy

The nautical-survey language is softened in `src/i18n/{en,pt}.ts` (keys unchanged,
values only): `Devices` / `Review` / `People` / `Statistics` / `Activity` /
`Settings`; `Scan` not `Sweep`; `Couldn't load` not `No fix`. Short toast keys
(`device.deleted`, `config.saved`, …) were added to both dictionaries so
confirmations read as sentences rather than dotted identifiers.

## What stays out

Accent hues used as chrome; the graticule / any decorative background texture;
condensed display faces; uppercase-tracked buttons; hard offset shadows;
coloured structural borders; monospace as costume; Unicode/emoji icons (Phosphor
set + the drawn `AppMark`).

## Not in scope

The marketing site (`site/`), `docs/` brand assets, and the README brand imagery.
