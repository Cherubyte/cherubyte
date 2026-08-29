# Fonts

All self-hosted and served from `/fonts/*` — NetScan makes no external font
requests. Every face here is under the SIL Open Font License 1.1.

| Family | Files | Role | License |
| --- | --- | --- | --- |
| **Geist** | `Geist-{Regular,Medium,SemiBold,Bold}.woff2` | UI and body text | OFL 1.1 — `OFL-Geist.txt` (Vercel) |
| **Geist Mono** | `GeistMono-{Regular,Medium}.woff2` | Data layer: addresses, timestamps, counts | OFL 1.1 — `OFL-Geist.txt` |
| **Space Grotesk** | `SpaceGrotesk-latin.woff2`, `SpaceGrotesk-latin-ext.woff2` | Display: headings, host names, the big readouts | OFL 1.1 — `OFL-SpaceGrotesk.txt` |

Space Grotesk is a variable font (weight axis 300–700); the two files are the
`latin` and `latin-ext` subsets from Google Fonts. The `@font-face` rules and the
`.font-display` / `.font-display-lt` helpers live in `frontend/src/index.css`;
the Tailwind `font-display` family is set in `frontend/tailwind.config.js`.

To swap the display face, drop replacement `woff2` files here and update those two
places — the rest of the UI only ever refers to the `display` family, never a
specific font name.
