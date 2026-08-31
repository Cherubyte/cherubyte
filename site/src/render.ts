/**
 * The public page. Server-rendered from the Worker rather than built and put
 * behind the assets binding: it is one document with no client bundle, so a
 * build step would be a moving part that buys nothing.
 *
 * Colours are the house palette, as semantic roles — no raw hex in a component,
 * sentence case throughout, one accent, space instead of dividers.
 */

const STYLES = `
:root {
  --canvas: oklch(99% 0.003 260);
  --surface: oklch(100% 0 0);
  --surface-raised: oklch(98% 0.004 260);
  --border-subtle: oklch(92% 0.006 260);
  --ink: oklch(23% 0.02 265);
  --ink-muted: oklch(52% 0.018 265);
  --accent: oklch(56% 0.16 262);
  --accent-contrast: oklch(99% 0 0);
  --accent-soft: oklch(96% 0.03 262);
  --success: oklch(58% 0.13 155);
  --radius: 10px;
  --font-sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --font-mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
  color-scheme: light dark;
}
@media (prefers-color-scheme: dark) {
  :root {
    --canvas: oklch(17% 0.012 265);
    --surface: oklch(21% 0.014 265);
    --surface-raised: oklch(25% 0.016 265);
    --border-subtle: oklch(30% 0.016 265);
    --ink: oklch(94% 0.006 265);
    --ink-muted: oklch(70% 0.014 265);
    --accent: oklch(72% 0.14 262);
    --accent-contrast: oklch(17% 0.012 265);
    --accent-soft: oklch(28% 0.05 262);
    --success: oklch(72% 0.13 155);
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--canvas); color: var(--ink);
  font-family: var(--font-sans); font-size: 16px; line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 62rem; margin: 0 auto; padding: 0 1.5rem; }
header { padding: 5rem 0 1rem; }
.brand { font-weight: 600; letter-spacing: -0.01em; }
h1 { font-size: clamp(2rem, 5vw, 3.25rem); line-height: 1.1; letter-spacing: -0.03em; margin: 2.5rem 0 1rem; max-width: 20ch; }
.lede { font-size: 1.15rem; color: var(--ink-muted); max-width: 58ch; margin: 0 0 2rem; }
.pill { display: inline-block; padding: 0.3rem 0.7rem; border-radius: 999px;
  background: var(--accent-soft); color: var(--accent); font-size: 0.8rem; font-weight: 500; }
.row { display: flex; flex-wrap: wrap; gap: 0.75rem; margin: 2rem 0 4rem; }
.btn { display: inline-block; padding: 0.7rem 1.2rem; border-radius: var(--radius);
  text-decoration: none; font-weight: 500; font-size: 0.95rem; border: 1px solid transparent;
  transition: opacity 120ms ease; }
.btn:hover { opacity: 0.88; }
.btn-primary { background: var(--accent); color: var(--accent-contrast); }
.btn-quiet { background: transparent; color: var(--ink); border-color: var(--border-subtle); }
section { padding: 3.5rem 0; }
h2 { font-size: 1.5rem; letter-spacing: -0.02em; margin: 0 0 0.5rem; }
h3 { font-size: 1rem; margin: 0 0 0.35rem; }
.muted { color: var(--ink-muted); }
.grid { display: grid; gap: 2rem; grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr)); margin-top: 2rem; }
pre { background: var(--surface-raised); border: 1px solid var(--border-subtle);
  border-radius: var(--radius); padding: 1rem; overflow-x: auto;
  font-family: var(--font-mono); font-size: 0.82rem; line-height: 1.5; }
code { font-family: var(--font-mono); font-size: 0.9em; }
.card { background: var(--surface); border: 1px solid var(--border-subtle);
  border-radius: var(--radius); padding: 1.5rem; }
.split { display: grid; gap: 2rem; grid-template-columns: 1fr; }
@media (min-width: 46rem) { .split { grid-template-columns: 1fr 1fr; } }
label { display: block; font-size: 0.85rem; font-weight: 500; margin-bottom: 0.35rem; }
input, textarea {
  width: 100%; padding: 0.6rem 0.75rem; border-radius: var(--radius);
  border: 1px solid var(--border-subtle); background: var(--canvas); color: var(--ink);
  font-family: inherit; font-size: 0.95rem;
}
input:focus, textarea:focus { outline: 2px solid var(--accent); outline-offset: -1px; }
.field { margin-bottom: 1rem; }
.note { font-size: 0.85rem; color: var(--ink-muted); }
.ok { color: var(--success); font-weight: 500; }
footer { border-top: 1px solid var(--border-subtle); margin-top: 4rem; padding: 2rem 0 4rem;
  color: var(--ink-muted); font-size: 0.9rem; }
a { color: var(--accent); }
`;

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string,
  );
}

export function landingPage(opts: { releasesUrl: string; message?: string; error?: string }): string {
  const banner = opts.message
    ? `<p class="ok">${escapeHtml(opts.message)}</p>`
    : opts.error
      ? `<p class="note" style="color:var(--accent)">${escapeHtml(opts.error)}</p>`
      : "";

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cherubyte — see every device on your network</title>
<meta name="description" content="A self-hosted network monitor. Free, open source, and your device inventory never leaves your network.">
<style>${STYLES}</style>
</head>
<body>
<div class="wrap">
  <header>
    <span class="brand">Cherubyte</span>
  </header>

  <h1>See every device on your network.</h1>
  <p class="lede">
    Cherubyte discovers everything on your LAN, works out what each thing is, tracks
    when people come and go, and tells you the moment something new appears.
    It runs on hardware you already own.
  </p>
  <p><span class="pill">Self-hosting is free, forever</span></p>
  <div class="row">
    <a class="btn btn-primary" href="#install">Install it</a>
    <a class="btn btn-quiet" href="https://github.com/Cherubyte/cherubyte">Source on GitHub</a>
  </div>

  <section>
    <h2>Two pieces</h2>
    <p class="muted">An agent watches a network. A panel keeps the history and shows it to you.</p>
    <div class="grid">
      <div>
        <h3>The agent</h3>
        <p class="muted">Sits on the network it watches, because discovery is a layer-2 job.
        One per network. Docker on Linux, or a service on Windows.</p>
      </div>
      <div>
        <h3>The panel</h3>
        <p class="muted">Holds the database and the interface. Needs no special
        privileges and never touches a network it is monitoring, so it can live
        anywhere — including on somebody else's machine.</p>
      </div>
      <div>
        <h3>Nothing leaves</h3>
        <p class="muted">No account, no cloud, no subscription. The agent talks to
        the panel you point it at, and that is the whole of it.</p>
      </div>
    </div>
  </section>

  <section id="install">
    <h2>Install</h2>
    <p class="muted">Start the panel, mint a token in it, then start an agent with that token.</p>
    <div class="split" style="margin-top:2rem">
      <div>
        <h3>Panel</h3>
        <pre>git clone https://github.com/Cherubyte/cherubyte
cd cherubyte
docker compose up -d panel</pre>
        <p class="note">Open <code>http://your-host:1001</code> and go to Config → Agents.</p>
      </div>
      <div>
        <h3>Agent</h3>
        <pre>docker run -d --name cherubyte-agent \\
  --network host --cap-add NET_RAW --cap-add NET_ADMIN \\
  -v cherubyte-agent:/var/lib/cherubyte-agent \\
  -e CHERUBYTE_AGENT_PANEL_URL=http://your-panel:1001 \\
  -e CHERUBYTE_AGENT_ENROL_TOKEN=&lt;token&gt; \\
  cherubyte-agent:latest</pre>
        <p class="note">On Windows, <a href="${escapeHtml(opts.releasesUrl)}">download the agent</a>
        and run <code>install-service.ps1</code> from an elevated PowerShell.</p>
      </div>
    </div>
  </section>

  <section id="hosted">
    <h2>Or let us run the panel</h2>
    <p class="muted" style="max-width:58ch">
      Self-hosting stays free and always will. If you would rather not keep a
      panel running — updates, backups, reaching it from outside the house —
      we will host one for you and you point your agents at it. Same software,
      same agent, one less thing to look after.
    </p>
    <div class="card" style="margin-top:2rem;max-width:34rem">
      ${banner}
      <form method="post" action="/signup">
        <div class="field">
          <label for="email">Email</label>
          <input id="email" name="email" type="email" required autocomplete="email" placeholder="you@example.com">
        </div>
        <div class="field">
          <label for="networks">How many networks?</label>
          <input id="networks" name="networks" placeholder="one at home, two at the office…">
        </div>
        <div class="field">
          <label for="note">Anything else</label>
          <textarea id="note" name="note" rows="3" placeholder="optional"></textarea>
        </div>
        <button class="btn btn-primary" type="submit" style="border:0;cursor:pointer;font:inherit;font-weight:500">
          Tell me when it is ready
        </button>
        <p class="note" style="margin-top:0.75rem">
          One email when hosting opens. Nothing else, and no account is created.
        </p>
      </form>
    </div>
  </section>

  <footer>
    <div class="wrap" style="padding:0">
      Cherubyte is open source under the licence in the repository.
      <a href="https://github.com/Cherubyte/cherubyte">Source</a> ·
      <a href="${escapeHtml(opts.releasesUrl)}">Downloads</a>
    </div>
  </footer>
</div>
</body>
</html>`;
}

export function adminPage(rows: { email: string; networks: string | null; note: string | null; created_at: string }[]): string {
  const body = rows.length
    ? rows
        .map(
          (r) => `<tr>
      <td>${escapeHtml(r.email)}</td>
      <td class="muted">${escapeHtml(r.networks ?? "—")}</td>
      <td class="muted">${escapeHtml(r.note ?? "—")}</td>
      <td class="muted">${escapeHtml(r.created_at)}</td>
    </tr>`,
        )
        .join("")
    : `<tr><td colspan="4" class="muted">No signups yet.</td></tr>`;

  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Signups — Cherubyte</title><style>${STYLES}
table { width: 100%; border-collapse: collapse; margin-top: 2rem; }
th, td { text-align: left; padding: 0.6rem 0.75rem; border-bottom: 1px solid var(--border-subtle); font-size: 0.9rem; vertical-align: top; }
th { font-weight: 500; color: var(--ink-muted); }
</style></head>
<body><div class="wrap"><header><span class="brand">Cherubyte</span></header>
<h2 style="margin-top:2rem">Hosted-panel signups</h2>
<p class="muted">${rows.length} in total.</p>
<table><thead><tr><th>Email</th><th>Networks</th><th>Note</th><th>When</th></tr></thead>
<tbody>${body}</tbody></table>
</div></body></html>`;
}
