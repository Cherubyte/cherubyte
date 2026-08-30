# Fonts

All self-hosted and served from `/fonts/*` — NetScan makes no external font
requests.

| Family | File | Role | License |
| --- | --- | --- | --- |
| **Clash Display** | `ClashDisplay-Variable.woff2` | Display: headings, host names, the big readouts | Fontshare Free License — `FFL-ClashDisplay.txt` (Indian Type Foundry) |
| **Hanken Grotesk** | `HankenGrotesk-Variable.woff2` | UI and body text | OFL 1.1 — `OFL-HankenGrotesk.txt` |
| **Spline Sans Mono** | `SplineSansMono-Variable.woff2` | Data layer: addresses, timestamps, counts, chart labels | OFL 1.1 — `OFL-SplineSansMono.txt` |

All three are variable fonts (weight axis). The `@font-face` rules and the
`.font-display` / `.font-display-lt` / `.mono` / `.label` / `.key` helpers live in
`frontend/src/index.css`; the Tailwind `display` / `sans` / `mono` families are
set in `frontend/tailwind.config.js`.

To swap a face, drop a replacement `woff2` here and update those two places — the
rest of the UI only refers to the family role, never a specific font name.
