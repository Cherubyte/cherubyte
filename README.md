<p align="center">
  <img src="docs/logo-wordmark.png" alt="NetScan" width="620">
</p>

<p align="center">
  <a href="https://github.com/nobrega8/netscan/actions/workflows/ci.yml"><img src="https://github.com/nobrega8/netscan/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/nobrega8/netscan/actions/workflows/agent-windows.yml"><img src="https://github.com/nobrega8/netscan/actions/workflows/agent-windows.yml/badge.svg" alt="Agent (Windows)"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-3776ab?logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/node-20%2B-339933?logo=nodedotjs&logoColor=white" alt="Node 20+">
  <img src="https://img.shields.io/badge/platform-Linux%20%C2%B7%20Raspberry%20Pi-555" alt="Platform: Linux · Raspberry Pi">
  <a href="https://github.com/nobrega8/netscan/pulls"><img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg" alt="PRs welcome"></a>
</p>

# NetScan

**A self-hosted network monitor — a free, private alternative to Fing.**

NetScan continuously discovers every device on your LAN, identifies what each one
is, tracks when it joins and leaves, and tells you the moment something new shows
up.

It comes in two halves. The **panel** stores the inventory, classifies devices,
raises alerts and serves the web UI (default port **1001**) — on a Raspberry Pi,
a NAS, or any Linux box. One or more **agents** do the actual scanning; run one
on the same box for a single LAN, or one per network you want to watch. The
`setup.sh` below installs both on one machine, which is all most people need.

No cloud. No subscription. One local admin account, and your device inventory
never leaves your network.

## Screens

<p align="center">
  <img src="docs/screenshots/dashboard.png" alt="NetScan dashboard — the host register plotted like a chart, with the plan title-block above it" width="880">
</p>

<table>
  <tr>
    <td width="50%"><img src="docs/screenshots/device.png" alt="Device detail — identity, network, connection history"><br><sub><b>Device detail</b> — rename it, set its owner and type, see every IP and MAC folded in, and its join/leave history.</sub></td>
    <td width="50%"><img src="docs/screenshots/people.png" alt="People &amp; presence — a chart-recorder strip of when each person was home"><br><sub><b>People &amp; presence</b> — link devices to people; a strip-chart of when they were home, drawn to the minute.</sub></td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/screenshots/log.png" alt="Event log in the dark ECDIS-night theme — a filterable timeline of joins, leaves, ports and alerts"><br><sub><b>Event log</b> (dark theme) — every join, leave, port change and alert, filterable by level and category.</sub></td>
    <td width="50%"><img src="docs/screenshots/stats.png" alt="Statistics — new devices over time, breakdown by type, brand and OS"><br><sub><b>Statistics</b> — new devices over time, and the network broken down by type, brand and OS.</sub></td>
  </tr>
</table>

<sub>Screens show a demo network with generic device and people names. Light chart-sheet by default, ECDIS-night as the dark theme; English or Portuguese.</sub>

---

## Why not just use Fing?

[Fing](https://www.fing.com/) is a great app, but the useful parts — device
details, presence history, custom alerts, more than a handful of devices — sit
behind **Fing Premium**, a paid subscription, and everything syncs through
Fing's cloud with an account attached.

NetScan does the same job on hardware you already own:

| | NetScan | Fing (free) | Fing Premium |
| --- | --- | --- | --- |
| Price | Free | Free | Paid subscription |
| Runs | On your own machine | Phone / cloud | Phone / cloud |
| Account | One, local to your box | Fing cloud account | Fing cloud account |
| Where your data lives | Your LAN, in SQLite | Fing's cloud | Fing's cloud |
| Device limit | None | Limited | Higher |
| Presence history per person | Yes | — | Limited |
| New-device alerts | Telegram / ntfy | — | Yes (Fing's channels) |
| Open source | Yes | No | No |
| Always-on monitoring | Yes (it's a service) | Only while the app scans | Fingbox hardware |

If you want a polished mobile app and don't mind the cloud, Fing is fine.
If you'd rather own the whole thing, run NetScan.

---

## What it does

- **Active discovery** — an agent runs an ARP sweep (`scapy`, raw sockets) +
  ICMP ping + the OS neighbour table, so it also finds devices that ignore ARP.
  Runs on a schedule you set in the panel.
- **Automatic identification** — reverse DNS, mDNS / DNS-SD, SSDP / UPnP,
  NetBIOS, HTTP banners, TCP port fingerprinting, MAC vendor (OUI), passive DHCP
  fingerprinting, optional [Fingerbank](https://fingerbank.org/) lookup, and OS
  guessing by TTL. Devices are classified as phone, laptop, TV, console, camera,
  printer, NAS, IoT, router, and so on.
- **One device, many addresses** — merge multiple IPs and MACs (including
  randomised MACs) into a single device.
- **People & presence** — link devices to people and get a GitHub-style activity
  grid of when each person was home, one square per hour. Always-on devices can
  be excluded from the presence calculation.
- **Connection history & event log** — every join/leave, every new device,
  searchable and filterable.
- **Approvals** — new devices land in a review queue; approve the ones you know,
  ignore the rest.
- **Notifications** — pushed to **Telegram** and/or **[ntfy](https://ntfy.sh/)**
  (public server or your own), with a per-event-type policy, a quiet-hours window
  (urgent alerts still get through), and **Approve / Ignore buttons right on the
  ntfy notification** (signed, expiring, single-device tokens).
- **Home Assistant via MQTT** — auto-discovery turns each person into a
  `device_tracker` and each device into a connectivity sensor, no YAML needed.
- **Internet monitoring** — WAN uptime and latency, an alert on the transition,
  and a sparkline on the dashboard. Your public IP is shown too, redacted until
  you hover it, so a screenshot doesn't give it away.
- **Configurable alerts** — ARP anomalies (the gateway's MAC changing, an IP
  hopping between devices), a per-device open-port diary (what opened or closed),
  merge suggestions for phones that rotate their MAC, and a weekly digest.
- **Statistics** — new devices per day, breakdown by type, by brand, by OS, with
  logos you can assign.
- **Multiple subnets** — scan several CIDRs; each gets its own tab.
- **Per-device photos** — snap a picture so you recognise the thing later.
- **English or Portuguese** UI, and light or dark themes — both in **Config ▸ Interface**.

---

## Requirements

- Linux (developed on a Raspberry Pi; anything with Python 3.11+ works)
- Python 3.11+ and Node.js 20+ to build
- The agent needs `CAP_NET_RAW` for the ARP sweep and DHCP sniffer; the panel
  needs `CAP_NET_BIND_SERVICE` for port 1001. Both systemd units grant these
  without running as root — `setup.sh` and the install scripts wire them up.

## Quick start

```bash
git clone https://github.com/nobrega8/netscan.git
cd netscan

# builds the panel, creates the database, prompts for the admin account,
# builds the bundled agent, and installs both as systemd services
./scripts/setup.sh --service --agent
```

`setup.sh` is interactive; for an unattended run set `NETSCAN_ADMIN_USERNAME`
and `NETSCAN_ADMIN_PASSWORD` first. Drop `--service` to run it by hand instead
(`./scripts/start.sh`), or `--agent` if this box only hosts the panel.

Then open **<http://localhost:1001>**, log in, and enrol the agent:

1. **Config ▸ Agents ▸ New agent** — copy the token.
2. `./scripts/install-agent-service.sh http://localhost:1001 <token>`

The first sweep lands a few seconds later. NetScan does **not** scan until an
agent is enrolled and reporting.

Managing the services:

```bash
sudo systemctl {status,restart,stop} netscan          # the panel
sudo systemctl {status,restart,stop} netscan-agent    # the scanner
journalctl -u netscan -f
journalctl -u netscan-agent -f
```

Reset a lost admin password: `cd backend && .venv/bin/python manage.py create-admin <name>`.

### Other ways to run

The ARP scan **and** binding port 1001 both need network privileges. The
systemd unit is the recommended path; if you're not using it, pick one:

```bash
# capabilities on the venv's python (must be a real file, not a symlink —
# the venv setup above already ensures that)
sudo setcap 'cap_net_raw,cap_net_admin,cap_net_bind_service+eip' \
  "$(readlink -f backend/.venv/bin/python)"

# ...or just run as root
sudo backend/.venv/bin/python backend/run.py
```

- `./scripts/start.sh` — production, everything on `:1001`
- `./scripts/dev.sh` — backend on `:1001` + Vite dev server on `:5173` with hot reload

### Installing an agent

An agent needs **two things**: the URL of a panel, and an enrolment token that
panel minted. Everything else — sweep interval, subnets, what to identify and
how often — is configured in the panel and sent back with every report, so
there is nothing to keep in step by hand.

Mint a token in **Config ▸ Agents**; the page prints the exact command for
each install method below, filled in.

**Linux / Raspberry Pi** (from a clone of this repo, the common case — a scanner
right next to the panel):

```bash
./scripts/install-agent-service.sh http://your-panel:1001 <token>
```

It creates `agent/.venv`, writes `agent/.env`, and installs a `netscan-agent`
systemd unit that starts at boot, restarts on failure, and gets `CAP_NET_RAW`
without running as root. The long-lived key is kept in
`~/.local/state/netscan-agent/` so a restart does not re-enrol.

**Docker** (Linux host, any distribution):

```bash
docker run -d --name netscan-agent --network host \
  --cap-add NET_RAW --cap-add NET_ADMIN \
  -v netscan-agent:/var/lib/netscan-agent \
  -e NETSCAN_AGENT_PANEL_URL=http://your-panel:1001 \
  -e NETSCAN_AGENT_ENROL_TOKEN=<token> \
  ghcr.io/nobrega8/netscan-agent:latest
```

**Windows service** — download `netscan-agent.exe` from the releases page, then
from an elevated PowerShell:

```powershell
.\install-service.ps1 -PanelUrl http://your-panel:1001 -EnrolToken <token>
```

It installs to Program Files, registers itself as a service that starts at boot
and restarts on failure, and keeps its key in ProgramData so an upgrade does not
lose it. `.\uninstall-service.ps1` removes it.

The token is spent once, on first start, for a long-lived key. Keep the state
volume (Docker) or the ProgramData directory (Windows) — without it the agent
re-enrols on every restart, and the second restart fails because the token is
already spent.

**Pointing an agent at somebody else's panel** is just a different
`NETSCAN_AGENT_PANEL_URL`. Agents push outbound over HTTP, so nothing needs to
be opened on the network the agent sits on.

### Docker — agent and panel

NetScan runs as **two containers**, and the split is the point.

```bash
docker compose up -d panel              # panel on http://<host>:1001
# in the panel: Agents → new token, then:
AGENT_ENROL_TOKEN=<token> docker compose up -d agent
```

The images are on GHCR — `ghcr.io/nobrega8/netscan-panel` and `-agent` —
published multi-arch (`amd64` + `arm64`) on every release as `:latest`, `:0.5`
and `:0.5.0`. `compose` pulls `:latest` by default; set `PANEL_IMAGE` /
`AGENT_IMAGE` to pin a version, or run `docker compose build` to build from a
checkout instead.

| | Agent | Panel |
|---|---|---|
| Does | Sweeps a network, reports what it saw | Stores, classifies, alerts, serves the UI |
| Networking | `network_mode: host` — required | Ordinary bridge, published port |
| Capabilities | `NET_RAW`, `NET_ADMIN` | None |
| Holds | Nothing but its own key | The database and the uploads |
| How many | One per network | One |

**Why split at all.** Discovery is a layer-2 job — the ARP sweep is broadcast,
mDNS and SSDP are multicast, the neighbour table is the kernel's — so whatever
does it must sit on the network being watched, with raw sockets. Nothing else
must. Separating them means the privileged half is small and holds no data, and
the half holding your history needs no privileges at all and can live anywhere.

**The rule the split follows: the agent observes, the panel decides.** Everything
crossing the wire is something an agent saw. Classification, naming, presence
and alerting are the panel's, computed from those observations — so improving
any of them is a panel upgrade that applies to every agent already in the field,
including old ones.

**Enrolment.** Agents are machine clients and cannot do an interactive login, so
they carry a key rather than sitting behind one. Mint a single-use, 24-hour
enrolment token in the panel, put it in the agent's environment, and it is spent
once on first start for a long-lived key. The panel stores only a hash of that
key. Mount the agent's state volume — otherwise it re-enrols on every restart,
and the second restart fails, because the token is spent.

**On the bridge network the agent finds nothing** — it would sweep Docker's own
subnet. It reports that as a *degraded* sweep rather than an empty network, and
the panel then keeps every device's state instead of marking them all offline.
Worth knowing, because "found nothing" and "there is nothing" look identical
otherwise.

**Docker Desktop on macOS/Windows will not do** for the agent: even with host
networking the "host" is the Linux VM, not your machine. The panel is fine
anywhere.

Also handled in the images: `iputils-ping` and `iproute2` in the agent (the
sweep and the internet probe shell out to both), `tzdata` in the panel (the
presence grid is drawn in local time and a container starts in UTC), and a
volume each — `/var/lib/netscan-agent` for the agent's key, `/app/backend/data`
for the panel's database and uploads.

---

## Configuration

Everything below is editable in the **Config** tab and stored in the database;
`backend/.env` (`NETSCAN_*`, see `.env.example`) sets the initial values. The
scan-related settings are pushed to every agent with each report — an agent only
holds its panel URL and its key, nothing you have to keep in step by hand.

- **Subnets** — leave empty to let the agent auto-detect its interface's `/24`,
  or list one or more CIDRs. ARP only reaches subnets on the agent's own link;
  routed subnets fall back to ping + the OS ARP table and may be partial.
- **Sweep interval**, **offline-after**, and **re-identify interval** — discovery
  runs every sweep; the heavier identification (ports, DNS, HTTP, mDNS, SSDP) is
  spaced out, immediate for new devices and batched for known ones.
- **History retention** — the event and connection tables are purged daily.
  Default 90 days; `0` keeps everything.
- **Notifications** — enable Telegram and/or ntfy and fill in the details. On a
  public ntfy server, anyone who knows the topic name can read your
  notifications, so pick something unguessable or use authentication.
- **Fingerbank API key** — free from fingerbank.org; turns DHCP fingerprints
  into device names and OS.

## Architecture

```
backend/   FastAPI + APScheduler + SQLAlchemy (async)   the panel  → :1001
frontend/  React + TypeScript + Vite + Tailwind         the web UI
agent/     FastAPI + scapy + zeroconf                    the scanner → :1002 (health only)
protocol/  pydantic models — the agent↔panel wire contract
```

The panel serves the API at `/api/*`, an SSE feed at `/api/stream`, uploads at
`/uploads/*`, and the compiled SPA (`frontend/dist`) for everything else. Agents
push reports to `/api/agents/{id}/report` and never listen for the panel — see
the **Docker — agent and panel** section for why the split exists and what
crosses the wire.

## Security

- **Authentication** — first launch asks you to create an admin account; after
  that the UI and the write API are behind a login. Passwords are hashed with
  PBKDF2-HMAC-SHA256 (600k rounds, stdlib only); a session is an opaque token in
  an `httponly` cookie, looked up in `auth_sessions`, so logout is a row delete.
  Failed logins are throttled per username. Three roles: **viewer** (read-only),
  **editor** (writes), **admin** (also manages accounts). Manage accounts and
  reset passwords with `backend/manage.py`.
- **Agents** carry a key, not a login — a single-use 24h enrolment token is
  spent once for a long-lived key, of which the panel stores only a hash.
- the SPA fallback only serves files from inside `frontend/dist` (path traversal
  is blocked, including via `%2e%2e` and symlinks)
- CORS is **off** by default — neither production nor the Vite dev server needs
  it (Vite proxies `/api` server-side). Set `NETSCAN_CORS_ORIGINS` only if you
  hit the dev server from another machine.
- uploads are size-capped and validated by their leading bytes, not the filename
- files under `/uploads` are served with a locked-down CSP so an uploaded SVG
  can't run script on the app's origin

Still, don't put NetScan directly on the public internet. The login helps, but a
VPN or an authenticating reverse proxy in front is the right posture.

## Development & tests

```bash
cd backend
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest            # panel tests, no network

cd ../agent
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest            # agent tests

cd ../frontend
npm run build               # runs tsc --noEmit first
```

Both run in CI on every push and pull request. `aiomqtt` (for the Home Assistant
integration) is pulled in with the rest of `requirements.txt`.

## Roadmap

### Not yet done, and needed before the install instructions are true

- **Cut the first release.** `.github/workflows/images.yml` publishes both
  images to GHCR — `:latest` and semver tags on a GitHub release, multi-arch.
  Until one is cut the `:latest` tag the README and `docker-compose.yml` point
  at does not exist, so `docker compose up` needs a `build` first.
  `docs/RELEASING.md` has the steps.
- **Deploy the site.** `site/wrangler.jsonc` still carries a placeholder
  `database_id`, no Cloudflare Access application exists, and `ACCESS_AUD` and
  `ALLOWED_EMAILS` are unset. `site/README.md` has the four commands.
- **Run the Windows agent on a real machine.** It is built, installed, started,
  health-checked and removed on every pull request by a Windows runner — but no
  human has ever installed it on a machine they own.

### Ideas

- Network topology map — worth it only with managed switches (LLDP/CDP or SNMP);
  on a flat LAN the picture is always "everything hangs off the router"
- Wake-on-LAN and per-device actions
- CSV / report export
- Passive discovery (sniffing) alongside the active ARP sweep
- Alembic for non-additive migrations
- The presence grid captures the timezone once at import, so it drifts by an
  hour after each DST change until the panel restarts

See [`docs/DECISIONS.md`](docs/DECISIONS.md) for why the system is shaped the way
it is — each entry anchored to the failure that produced it.

## License

[MIT](LICENSE). The bundled fonts (`frontend/public/fonts/`) — Hanken Grotesk and
Spline Sans Mono under the SIL Open Font License 1.1, Clash Display under the
Fontshare Free License — self-hosted, with their license files sitting next to
them. NetScan makes no external font requests.
