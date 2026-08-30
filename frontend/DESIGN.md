# DESIGN — "CHART"

The NetScan panel as a hydrographic chart of the LAN. The network is charted
water; every device is a plotted contact with a symbol, a leader-tethered
label, and a sounding (its last-seen). The panel *records and charts* — it does
not perform. Ink on chart paper by default; the ECDIS-night palette for dark.

This supersedes v7 "INSTRUMENT" (warm graphite + tungsten amber + machined
depth), which the owner rejected as still-generic, over-staged, and wrong in
density. Direction chosen from the `impeccable` concept-seed roll (seed
`0192d9d2`, mode `operate`, grounded candidate 5 of 7: hydrographic chart + AIS
overlay), then locked by the owner. Build path: code-led (no image generation
available). Contract comment lives in `frontend/index.html`.

## Foundations

### Palette — tokens in `src/index.css`, Tailwind names in `tailwind.config.js`

`:root` is the **light chart sheet**; `.dark` opts into **ECDIS night**
(`useTheme.ts` toggles `.dark`, default light).

| Token | Light | Dark | Role |
|---|---|---|---|
| `--bg` / `--paper` | `244 239 228` warm buff | `9 16 20` | the chart sheet (carries the graticule) |
| `--surface` | `250 247 239` | `21 33 39` | a plate laid on the sheet (`.panel`) |
| `--surface-2` | `235 228 213` | `30 46 53` | sunken sample cell · input · row hover |
| `--surface-3` | `224 216 199` | `42 62 70` | deep sunken · skeleton |
| `--fg` | `27 43 51` chart ink | `226 235 233` | primary ink (a charcoal slate, never pure black — chart-print convention) |
| `--fg-2` | `74 90 96` | `165 183 182` | secondary ink |
| `--fg-3` | `125 138 141` | `124 145 146` | soundings · ticks · coordinates · `.label` / `.key` |
| `--edge` | `211 205 191` | `42 60 67` | hairline rule |
| `--edge-2` | `185 177 160` | `66 90 97` | structural rule · control border |
| `--water` | `127 168 160` | `116 168 156` | charted water · known/online contact · area tint |
| `--signal` | `200 16 46` carmine | `240 92 116` | **the one spot colour** — chart warning: a real caution, the live/selected mark, unreviewed |
| `--alert` | `166 13 34` | `240 92 116` | needs-action — always filled + used for latched alarm |
| `--grid` | `27 43 51` | `150 190 185` | the graticule, at 0.03–0.06 alpha |

**Colour discipline:** carmine is reserved. It appears only for: the held (active)
folio sheet's leader tick, the page-title tick, pending/unreviewed badges and
marks, destructive actions, the focus ring, the device-type-picker selection,
`LEAVE` events, and the presence strip-chart trace. It is never chrome — the
primary button and every active segmented/toggle state are an **ink stamp**
(`--fg` fill, `--surface` text), not carmine. Online is carried by ink weight +
a faint `--water` row tint, not a colour of its own. Per-person colours come
from `PERSON_COLORS` in `lib/format.ts` (carmine/orange deliberately absent).

### Type — Google Fonts, loaded in `index.html` with preconnect

- **Big Shoulders** (`.font-display`, weight 700 / `.font-display-lt` 600) —
  the signage / chart title-block voice: page titles, host & person names, the
  big readouts. A tall condensed grotesque.
- **Overpass** (`font-sans`, body/UI) — derived from the FHWA Highway Gothic
  road-sign typeface; the wayfinding workhorse. Buttons are Overpass 600,
  `letter-spacing 0.03em`, near-square (2px radius).
- **Overpass Mono** (`.mono`, `.label`, `.key`, `.data`) — the data layer:
  MAC/IP addresses, timestamps, coordinates, soundings, column keys. `.key` is
  10px uppercase, `letter-spacing 0.11em`; `.label` 11px sentence-case.

### Depth & shape

Charts are printed flat. `--e1` is a hairline ring; `--e2` a hairline + a
`0 1px 3px` lift; `--e3` (modals only) a soft `0 12px 40px`. Radii are near-square
throughout — 2px controls, 3px plates, `borderRadius` scale capped at 6px.

### The graticule

`body` carries a two-axis ruled grid (96px major, 24px minor) as low-alpha
`linear-gradient` layers. The `impeccable` detector flags decorative grid
backgrounds as slop — kept deliberately: CHART is a map/measurement surface and
the graticule is its coordinate system, which the detector's own rule exempts.

## Chrome — `components/Shell.tsx`

**Desktop:** a fixed left **margin** (212px) — the title block (`ChartMark` +
`NETSCAN` in Big Shoulders), then the **folio**: each route is a numbered sheet
(`01`–`06`) with a code, icon and name; the held sheet gets a 2px carmine leader
tick. Sweep (ink stamp), account + role, and an `Ed. v0.x.x` edition stamp sit
at the foot. A thin top **marginalia strip** carries the survey particulars —
SUBNET / HELD (online / total) / SWEEP interval / LAST / EPOCH clock — in
Overpass Mono with `.key` labels. The page title is a `.key` with a carmine tick,
no icon. Main column `max-w-[1320px]`.

**Mobile:** compact title block + a scrollable mono particulars line → bottom
tab bar (6 sheets, active = 2px carmine top-tick).

**Motion** (`index.css`): during a sweep, one **survey line** — a single 1px ink
hairline with a faint carmine trailing edge — is dragged once down the plot
(`.sweep-line`, `sweep-down`, linear, no glow). The only "something changed"
motion anywhere else is `.row-flash` — a single hard **chart-negative** flash
(row briefly fills `--fg`, then settles) when a new contact drops onto the sheet.
Route change is one quiet crisp `view-in` fade-up (no blur). `.mark-breathe` is a
no-op. All of it collapses under `prefers-reduced-motion`.

## Components — `components/ui.tsx`

- `.panel` — a chart plate: `--surface`, 1px `--edge`, 3px radius, `--e2`.
  `.panel-ruled` adds a 2px carmine caution hairline along the top.
- `.core` — a sunken sample cell.
- `Readout` — Big Shoulders numeral (`font-display`, tabular) + a `.key` caption;
  `tone="signal"` only for a genuine caution count (e.g. new-today > 0).
- `.signal-mark` — a plotted contact position: `--on` a solid ink disc inside a
  `--water` ring (charted / online); `--alert` a carmine disc + ring (uncharted /
  unreviewed — "position approximate"); `--off` a hollow hairline disc that
  **keeps its place** (a reported position, not held).
- `.btn` — near-square, Overpass 600, `0.03em` tracking, press-scale `.975`.
  `.btn-primary` is the ink stamp; `.btn-danger` is carmine.
- `.tag` — a chart-legend chip. `.input` — a sunken cell, carmine focus hairline
  + `0 0 0 3px` ring, carmine caret.
- `Toggle` / `Segmented` — active segment is the ink stamp, never carmine.
- `QueryState` empty/error copy: "No fix" / "could not be plotted" (`common.*`
  i18n keys; PT "Sem fixação" / "não foi possível plotar").

## Key surfaces

- **Dashboard** (`pages/Dashboard.tsx`) — opens on the **plan's title block**: a
  bordered plate with a `PLAN · <subnet>` header and a row of soundings (held /
  present / new / internet + latency spark), a carmine caution cell appended
  when devices await review. Below: search + ink segmented filter → the contact
  register.
- **Contact register** (`components/DeviceListView.tsx`) — one continuous ruled
  sheet (`.panel` + `divide-y`). Columns: **Ref** (a chart grid coordinate,
  `A·001`, from `format.ts coord()`), contact mark, device image, host + sub,
  address, owner (person colour), type, OS, seen. Online rows carry a faint
  `--water` tint; offline rows drop to plain surface with a hollow mark under an
  `OFFLINE · n` rule. Row hover reveals a 2px carmine left edge.
- **People** (`pages/Users.tsx` + `components/PresenceHeatmap.tsx`) — presence
  renders as a **strip-chart recorder**: one ruled row per local day, each
  present interval a solid carmine bar positioned to the minute, a 1px "now"
  needle on today. This is the one place a bold carmine field is on-world (a
  recorder trace, not chrome).
- **Login** (`pages/Login.tsx`) — the `ChartMark` + wordmark over a single plate;
  Big Shoulders "Sign in", carmine focus.

## What stays out

Same-size icon+heading+text card grids; kickers/eyebrows above headings; gradient
text; glass/blur decoration; coloured borders above 2px as structure; hard offset
shadows; monospace as costume (here it is only ever data); Unicode/emoji icons
(Phosphor set + the drawn `ChartMark`); category-default display faces.

## Not in scope

The marketing site (`site/`), the `docs/` logo & wordmark, and the README brand
assets keep their existing INSTRUMENT-era mark and are untouched by this redesign.
