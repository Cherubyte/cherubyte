# Fonts

Self-hosted and served from `/fonts/*` — **Cherubyte makes no external font
requests.**

| Family | File | Role | License |
| --- | --- | --- | --- |
| **Inter** | `Inter-Variable.woff2` | The whole UI — headings, body, the big figures | OFL 1.1 — `OFL-Inter.txt` (The Inter Project Authors) |

Inter is a variable font (weight axis, `100–900`). Data — IP/MAC addresses,
timestamps, counts — uses the platform monospace stack (`ui-monospace, "SF Mono",
Menlo, Consolas`), no web font.

The `@font-face` rule is at the top of `frontend/src/index.css`; the
`.font-display` / `.font-display-lt` / `.mono` / `.label` / `.key` helpers and the
Tailwind `display` / `sans` / `mono` families (`frontend/tailwind.config.js`) all
refer to the family role, never a specific font name — drop a replacement `woff2`
here and update those two places to swap the face.
