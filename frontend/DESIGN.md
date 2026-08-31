# DESIGN — "STUDIO"

The NetScan panel as a calm, near-monochrome instrument — in the spirit of an
Apple system app and [curated.supply](https://www.curated.supply/). Near-black ink
on a soft grey ground, generous rhythm, restraint. **Depth is elevation, not a
stroke**: white cards float on the grey ground with a soft shadow, controls are
filled greys, chips and secondary buttons have no outline. The one hairline kept
is the inset separator inside a grouped list. Weight and space carry the
hierarchy; **no accent hue** — red is held back for a real alert or a destructive
action. Fluid, interruptible spring motion, all of it optional under
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
| `--bg` / `--paper` | `242 242 245` | `0 0 0` | the page — soft grey ground / true black |
| `--surface` | `255 255 255` | `28 28 30` | a card (`.panel`) — floats on the ground, no stroke |
| `--surface-2` | `240 240 243` | `44 44 46` | fill: sunken cell (`.core`), thumbnails, chip tracks |
| `--surface-3` | `230 230 234` | `58 58 60` | row hover · skeleton |
| `--fg` | `23 23 23` | `245 245 245` | primary ink — near-black |
| `--fg-2` | `92 92 96` | `174 174 178` | secondary |
| `--fg-3` | `142 142 147` | `122 122 128` | muted · `.label` / `.key` · meta |
| `--edge` / `--edge-2` | `226 · 210` grey | `56 · 72` grey | the one hairline: inset list separators |
| `--alert` | `200 38 38` | `248 113 113` | error · destructive · needs-action |

Filled controls (`.input`, `.btn-secondary`, `.tag-neutral`, segmented tracks) use
`rgb(var(--fg) / .05–.11)` — a translucent grey that adapts to whatever surface it
sits on. Elevation: `--e2` is a soft drop shadow in light, a faint inset top-edge
highlight + depth in dark. `--e3` (modals/toasts) is shadow only, no ring.

**Legacy tokens kept, remapped:** `--signal` and `--water` both resolve to `--fg`,
so every "active / selected / online" state that older classes expressed as a spot
colour now reads as ink. `signal-bg` / `signal-fg` = ink fill / surface text.
`--grid` is unused (the graticule is gone). Per-person colours still come from
`PERSON_COLORS` in `lib/format.ts`.

### Type — Inter (self-hosted `@font-face`, `public/fonts/`) + system fallback

- **Inter** — the whole UI. `font-sans`, `font-display` (weight 600, `-0.021em`
  tracking for titles / big figures), `font-display-lt` (500). `.key` is 11px
  uppercase, `0.04em` — quieter than the old chart register. Body 14px / 1.5.
- **System monospace** (`ui-monospace, "SF Mono", Menlo, Consolas`) — addresses,
  MAC / IP, timestamps, counts. No monospace-as-costume; it is only ever data.

### Depth & shape

`--e2` a soft drop shadow (`.panel`); `--e3` (modals/toasts) a deeper shadow, no
ring. Radii: cards `14px`, controls `8–10px`, chips `6px`, thumbnails `10px`,
marks / avatars full. Focus ring: `0 0 0 3px rgb(--fg / .14)`, no border.

## Chrome — `components/Shell.tsx`

**Desktop:** a `228px` sidebar that sits on the grey ground with no divider —
`AppMark` + `NetScan` wordmark,
then the nav as rounded items — the active one is a white pill (`--surface` +
a whisper of shadow), no number codes, no leader tick. Foot: primary **Scan**
button (editors), account + role, version, a sun/moon theme toggle. A sticky
**translucent toolbar** (`bg-bg/70` + `backdrop-blur-xl`, no divider) carries the
section title (plain sentence case), a **`Search ⌘K`** pill, and quiet mono
vitals — subnet · online/total · last scan · clock. Main column `max-w-[1240px]`.

**Mobile:** translucent top bar (mark + online/total + search + theme + sign-out
+ Scan) with a scrollable vitals line → translucent bottom tab bar, active tab =
filled icon + ink label.

**Command palette** (`components/CommandPalette.tsx`, mounted once in `Shell`):
⌘K / Ctrl+K (or the toolbar pill) opens a Spotlight-style search over devices,
people and pages — grouped, arrow-key + Enter, Esc to close, spring-in.

**Scan in progress:** a 2px indeterminate `scan-bar` under the toolbar (replaces
the old survey line).

## Motion — `src/lib/motion.ts` (adds `motion`, Framer Motion)

- `snappy` — `{spring, bounce:0, duration:0.35}` — the default; route changes,
  toggles, dialogs.
- `sheetSpring` — `{spring, bounce:0.18, duration:0.42}` — surfaces that "arrive":
  `Sheet` (drag-to-dismiss with velocity), `Dialog` on mobile.
- Route body: a keyed `motion.div` fade/rise per `pathname`.
- `Toggle` — an iOS-style switch, animated knob spring. `Toaster` — `AnimatePresence`
  spring in/out.
- `useReducedMotion()` everywhere → opacity-only or instant; the CSS keyframes in
  `index.css` (`view-in`, `sheet-up`, …) remain as the no-JS / reduced fallback.

## Components — `components/ui.tsx`

Export names and prop signatures are unchanged from "CHART" — only the visuals.
`.panel` a 14px card, shadow only, no border; `.core` a grey sunken fill;
`.btn-primary` the ink fill, `.btn-secondary` a grey fill, `.btn-danger` a red
tint that commits to solid on hover; `.input` a translucent-grey fill with no
stroke, an ink focus ring; `.tag` a 6px filled chip (`tag-signal` = ink fill,
`tag-neutral` / `tag-alert` = tint); `.signal-mark` a small dot (`--on` ink,
`--alert` red, `--off` a hollow hairline that keeps its slot). Segmented controls,
subnet tabs and filter chips are all filled pills on a translucent-grey track.
`QueryState` / error states use an `alert/10` tinted block, not a border.

## Key surfaces

- **Dashboard** — an **overview card**: a large online count `/ total`, then
  Present · New today · Internet uptime + latency spark, spaced with generous
  gaps (no dividers); a red-tinted "N · Review" pill only when devices await review.
  Then a search field + filter segmented control → the device list.
- **Device list** (`components/DeviceListView.tsx`) — one borderless `.panel` with
  `divide-y` inset separators. Columns: status dot · thumbnail (10px round-square)
  · name + sub · address · owner · type · OS · last-seen. Online rows full-strength
  ink; offline rows dim under an `Offline · n` rule. Row hover `--surface-2`; a new
  device gets one soft `row-flash`.
- **People** (`components/PresenceHeatmap.tsx`) — the strip-recorder stays; present
  intervals are solid **ink** bars, faint 6-hour gridlines, an ink "now" needle.
- **Settings** — the side-list category nav (rounded items, no codes); every
  section restyled. `Channel` is a filled grey block; its expanded body is white
  so the fields read against it.
- **Login** — `AppMark` + wordmark over a single floating `.panel`, plain "Sign in".

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
