<p align="center">
  <img src="docs/logo-wordmark.png" alt="Cherubyte" width="560">
</p>

<p align="center">
  <a href="https://github.com/Cherubyte/cherubyte/actions/workflows/ci.yml"><img src="https://github.com/Cherubyte/cherubyte/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/Cherubyte/cherubyte-agent"><img src="https://img.shields.io/badge/agent-Cherubyte%2Fcherubyte--agent-555?logo=github" alt="Agent repo"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-3776ab?logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/node-20%2B-339933?logo=nodedotjs&logoColor=white" alt="Node 20+">
  <img src="https://img.shields.io/badge/platform-Linux%20%C2%B7%20Raspberry%20Pi-555" alt="Platform: Linux · Raspberry Pi">
</p>

<h1 align="center">Your whole network, in one quiet place.</h1>

<p align="center">
  Cherubyte watches every device on your LAN, works out what each one is,<br>
  remembers when it comes and goes, and tells you the moment something new appears.<br>
  Self-hosted. No account. No cloud. A free, private alternative to Fing.
</p>

<p align="center">
  <img src="docs/screenshots/dashboard.png" alt="The Cherubyte dashboard — an overview strip above the list of every device on the network" width="880">
</p>

---

## What it does

**Everything at a glance.** Open the panel and you know, in seconds, what's online
now, who's home, what's new since last time, and whether anything needs a look.

**It knows what things are.** Reverse DNS, mDNS (every service type actually on
the network, not a fixed list), SSDP, NetBIOS, LLMNR, HTTP banners, TCP
fingerprints, MAC vendor, passive DHCP fingerprinting, an optional
[Fingerbank](https://fingerbank.org/) lookup and TTL hints combine into a type,
a brand and an OS for each device — phone, laptop, TV, console, camera, NAS,
router, and the rest.

**One device, however many addresses.** Randomised MACs and multiple IPs fold
into a single identity, so a phone that rotates its MAC is one row, not five.

**It remembers who's home.** Link devices to people and get a per-hour grid of
when each person was on the network. Always-on devices can sit it out.

**It speaks up when it should.** New devices land in a review queue. A rogue DHCP
server, a gateway MAC that changes, a known device that starts presenting a
different OS, a sensitive port opening up, an agent that goes silent — each
raises an alert, pushed to Telegram, [ntfy](https://ntfy.sh/) or email with a
quiet-hours window and Approve / Ignore buttons right on the notification.

**Private by design.** It runs on hardware you already own. The inventory lives
in a SQLite file on your LAN and never leaves it.

<details>
<summary>Everything else it does</summary>

- **Connection history & activity log** — every join, leave, port change and
  alert, searchable and filterable.
- **Statistics** — new devices per day; the network broken down by type, brand
  and OS, with logos you can assign.
- **Internet monitoring** — WAN uptime and latency with a sparkline, an alert on
  the transition, and your public IP shown redacted until you hover it.
- **Home Assistant via MQTT** — auto-discovery turns each person into a
  `device_tracker` and each device into a connectivity sensor.
- **Prometheus** — a `/api/metrics` scrape endpoint (device counts, per-person
  presence, agent freshness, WAN state), optionally behind a token.
- **Multiple subnets** — scan several CIDRs; each gets its own tab.
- **Per-device photos & files** — snap a picture so you recognise the thing
  later; attach the manual, the invoice or the warranty PDF alongside it.
- **Wake-on-LAN** — a Wake button on an offline device; the agent on that
  segment sends the magic packet.
- **CSV export** — the whole device inventory from **Settings ▸ History**.
- **SNMP · topology** (opt-in) — name managed switches from their `sysDescr`
  and read the links between them from the LLDP-MIB; switch on **Settings ▸
  Integrations ▸ Show topology map** to draw them as a **Topology** page.
- **Passive ARP listening**, alongside the active sweep — a host that answers
  someone else's "who has" rather than the agent's own probe still gets caught.
- **Risky-port watchlist** — a database, a remote shell or an unauthenticated
  admin API answering on the LAN gets a louder alert and a mark on the device.
- **Merge suggestions** for phones that rotate their MAC, and a weekly digest.
- **Update check** — **Settings ▸ Update** compares the running version against
  `main` and, for a git install, updates in place with one click; a container
  install gets the `docker compose pull` command instead.
- English or Portuguese, light or dark — a tap to switch either.
</details>

<table>
  <tr>
    <td width="50%"><img src="docs/screenshots/device.png" alt="Device detail — identity, network, connection history"><br><sub><b>Device</b> — rename it, set its owner and type, see every IP and MAC folded in, and its join/leave history.</sub></td>
    <td width="50%"><img src="docs/screenshots/people.png" alt="People & presence — a per-minute strip of when each person was home"><br><sub><b>People</b> — link devices to people; a per-minute strip of when they were home.</sub></td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/screenshots/log.png" alt="Activity in the dark theme — a filterable timeline of joins, leaves, ports and alerts"><br><sub><b>Activity</b> — every join, leave, port change and alert, filterable by level and category.</sub></td>
    <td width="50%"><img src="docs/screenshots/stats.png" alt="Statistics — new devices over time, breakdown by type, brand and OS"><br><sub><b>Statistics</b> — new devices over time, and the network broken down by type, brand and OS.</sub></td>
  </tr>
</table>

<sub>Screens show a generic demo network. Light by default, dark on a tap; English or Portuguese.</sub>

---

## Why not just use Fing?

[Fing](https://www.fing.com/) is a polished app, but the useful parts — device
detail, presence history, custom alerts, more than a handful of devices — are
behind a paid subscription, and everything syncs through Fing's cloud with an
account attached.

Cherubyte does the same job on your own hardware.

| | Cherubyte | Fing (free) | Fing Premium |
| --- | --- | --- | --- |
| Price | Free | Free | Paid subscription |
| Runs | On your own machine | Phone / cloud | Phone / cloud |
| Account | One, local to your box | Fing cloud account | Fing cloud account |
| Where your data lives | Your LAN, in SQLite | Fing's cloud | Fing's cloud |
| Device limit | None | Limited | Higher |
| Presence history per person | Yes | — | Limited |
| New-device alerts | Telegram / ntfy / email | — | Yes (Fing's channels) |
| Open source | Yes | No | No |
| Always-on | Yes, it's a service | Only while the app scans | Fingbox hardware |

---

## Two halves

Cherubyte is a **panel** and one or more **agents**, and the split is the point.
They are two programs in two repositories — this one is the panel; the agent is
[**Cherubyte/cherubyte-agent**](https://github.com/Cherubyte/cherubyte-agent).

An **agent** sits on the network it watches and does the scanning — an ARP sweep,
mDNS, SSDP, the kernel's neighbour table — which needs raw sockets and a place on
that LAN. It holds nothing but its own key.

The **panel** stores the history, classifies devices, raises alerts, serves the
web UI on port **1001**, and hands out the agent build for each platform from
**Settings ▸ Agents**. It needs no raw sockets and never touches a monitored
network, so it can live anywhere — a Raspberry Pi, a NAS, someone else's box.

Everything crossing the wire is something an agent *saw*. Naming, presence and
alerting are the panel's, computed from those observations — so improving any of
them is a panel upgrade that reaches every agent already in the field.

---

## Get started

```bash
git clone https://github.com/Cherubyte/cherubyte.git
cd cherubyte

# builds the panel, creates the database, prompts for an admin
# account, installs the panel as a systemd service
./scripts/setup.sh --service
```

Then open **<http://localhost:1001>**, sign in, and add an agent:

1. **Settings ▸ Agents ▸ New agent** — mint a token.
2. The page prints the filled-in command for each platform — Docker, or a
   native binary the panel serves and installs:

   ```bash
   curl -fsSL http://localhost:1001/api/agents/download/linux -o cherubyte-agent && chmod +x cherubyte-agent
   curl -fsSL http://localhost:1001/api/agents/installer/linux | sudo bash -s -- \
     --panel http://localhost:1001 --token <token> --binary ./cherubyte-agent
   ```

The first scan lands a few seconds later. Cherubyte does not scan until an agent
is enrolled and reporting.

```bash
sudo systemctl {status,restart,stop} cherubyte          # the panel
sudo systemctl {status,restart,stop} cherubyte-agent    # the scanner (installed above)
journalctl -u cherubyte -f
```

Scripting the whole thing instead of clicking through the UI? `manage.py
create-agent-token [label]` mints the same enrolment token step 1 above does,
straight from the terminal — no browser session needed:

```bash
cd backend && .venv/bin/python manage.py create-admin <name>   # unattended: $CHERUBYTE_ADMIN_PASSWORD
TOKEN=$(.venv/bin/python manage.py create-agent-token)
curl -fsSL http://localhost:1001/api/agents/installer/linux | sudo bash -s -- \
  --panel http://localhost:1001 --token "$TOKEN" --binary ./cherubyte-agent
```

Reset a lost admin password with the same `create-admin` command — it also
promotes an existing account and resets its password. Back up everything — the
database and the uploads — from **Settings ▸ History** or `manage.py backup`.

<details>
<summary>Docker</summary>

Two containers, `ghcr.io/cherubyte/cherubyte-panel` and `-agent`, multi-arch
(`amd64` + `arm64`).

`docker-compose.yml` in this repository is the maintained one and can also build
both images from a checkout. The example below is the same thing without the
checkout — save it as `docker-compose.yml` in an empty directory and it is
everything you need:

```yaml
services:
  panel:
    image: ghcr.io/cherubyte/cherubyte-panel:latest
    container_name: cherubyte-panel
    restart: unless-stopped

    # The panel scans nothing, so it gets an ordinary bridge, no capabilities
    # and one published port. It does not have to sit on the network it shows.
    ports:
      - "1001:1001"

    environment:
      # Containers start in UTC; the presence grid is drawn in local time.
      TZ: Europe/Lisbon

    volumes:
      # The SQLite database and the uploads. Losing this loses your history.
      - panel-data:/app/backend/data

  agent:
    image: ghcr.io/cherubyte/cherubyte-agent:latest
    container_name: cherubyte-agent
    restart: unless-stopped
    depends_on:
      - panel

    # Discovery is a layer-2 job: the ARP sweep is broadcast, mDNS and SSDP are
    # multicast, the neighbour table is the kernel's. On Docker's default bridge
    # this would sweep 172.17.0.0/16 and find nothing of yours.
    network_mode: host

    cap_add:
      - NET_RAW      # ARP sweep, DHCP sniffer, TTL probe
      - NET_ADMIN    # promiscuous mode for the DHCP sniffer

    environment:
      TZ: Europe/Lisbon
      # Host networking means the panel is reachable on the published port
      # above, not by service name. A panel elsewhere is just another URL.
      CHERUBYTE_AGENT_PANEL_URL: http://127.0.0.1:1001
      # Minted in the panel, spent on first start — see the two commands below.
      CHERUBYTE_AGENT_ENROL_TOKEN: ${AGENT_ENROL_TOKEN:-}
      CHERUBYTE_AGENT_NAME: casa
      # CHERUBYTE_AGENT_SUBNET: "192.168.1.0/24"   # empty auto-detects the /24

    volumes:
      # The key issued at enrolment. Keep it — see below.
      - agent-state:/var/lib/cherubyte-agent

volumes:
  panel-data:
  agent-state:
```

The two services come up in two steps, because the token only exists once the
panel is running:

```bash
docker compose up -d panel              # panel on http://<host>:1001
# in the panel: Agents → new token, then:
AGENT_ENROL_TOKEN=<token> docker compose up -d agent
```

One agent per network: for a second site, copy the `agent` block under a new
name, give it its own token and its own state volume, and point it at the same
panel.

Keep the agent's state volume — without it the agent re-enrols on every restart,
and the second restart fails because the token is already spent.

Docker Desktop on macOS/Windows won't do for the agent: even with host
networking the "host" is the Linux VM. The panel is fine anywhere.
</details>

<details>
<summary>Adding an agent</summary>

An agent needs a panel URL and an enrolment token. Everything else is configured
in the panel and sent back with every report. Mint a token in **Settings ▸
Agents** — the page prints the filled-in command for each method.

- **Native binary** — the panel serves the build for each platform and the
  matching installer, so an install is two `curl`s (see *Get started* above).
  The agent lives at `/usr/local/bin/cherubyte-agent`, its config at
  `/etc/cherubyte-agent/agent.env` (Linux) / `%ProgramData%\Cherubyte Agent\`
  (Windows) / `/Library/Application Support/Cherubyte Agent/` (macOS), and the
  enrolment key outside the install directory so upgrading the binary never
  loses it.
- **Docker** — `ghcr.io/cherubyte/cherubyte-agent:latest`, `network_mode: host`
  with `NET_RAW`/`NET_ADMIN`; keep the state volume.
- **From source** — clone
  [Cherubyte/cherubyte-agent](https://github.com/Cherubyte/cherubyte-agent).

The token is single-use, valid 24 h, spent once on first start for a long-lived
key the panel stores only as a hash. Losing the state means needing a *fresh*
token — `--purge` on the uninstallers removes it deliberately. Agents push
outbound over HTTP; nothing needs opening on the network the agent sits on.
</details>

<details>
<summary>Running the panel without systemd</summary>

The panel scans nothing — it only needs to bind the privileged port 1001. The
systemd unit is the recommended path; otherwise:

```bash
# one capability on the venv's python (a real file, not a symlink)
sudo setcap 'cap_net_bind_service+eip' "$(readlink -f backend/.venv/bin/python)"

# ...or use a high port
CHERUBYTE_PORT=8001 backend/.venv/bin/python backend/run.py
```

- `./scripts/start.sh` — production, everything on `:1001`
- `./scripts/dev.sh` — backend on `:1001` + Vite dev server on `:5173`
</details>

---

## Requirements

- Linux (developed on a Raspberry Pi; anything with Python 3.11+)
- Python 3.11+ and Node.js 20+ to build
- The panel needs only `CAP_NET_BIND_SERVICE` for port 1001 — the systemd unit
  grants it without root (the agent, in its own repo, is the half that needs raw
  sockets)

---

## Configuration

Everything is editable in **Settings** and stored in the database; `backend/.env`
(`CHERUBYTE_*`, see `.env.example`) sets the initial values. Scan-related settings
are pushed to every agent with each report.

- **Subnets** — empty auto-detects the agent's `/24`, or list CIDRs; each
  resolves its own interface, for boxes with more than one NIC or VLAN. ARP
  only reaches the agent's own link — a routed subnet (through a gateway, a
  VPN peer pool) falls back to ping + the OS neighbour table, which finds
  little or nothing since there's no MAC to see across a router. Run one
  agent per subnet for reliable discovery there, rather than adding a routed
  subnet to an existing agent's list.
- **Scan interval / offline-after / re-identify interval** — discovery runs every
  scan; the heavier identification is spaced out, immediate for new devices.
- **History retention** — event and connection tables are purged daily; default
  90 days, `0` keeps everything.
- **Notifications** — Telegram, ntfy and/or email (SMTP). On a public ntfy
  server anyone who knows the topic can read your alerts, so pick something
  unguessable. Email goes out through your own SMTP server (STARTTLS, SSL or
  plain) to one or more addresses, with the alert body laid out in the panel's
  own style.
- **Fingerbank API key** — free from fingerbank.org; turns DHCP fingerprints
  into a device name and OS.

---

## Architecture

```
backend/   FastAPI + APScheduler + SQLAlchemy (async)   the panel  → :1001
frontend/  React + TypeScript + Vite + Tailwind         the web UI
protocol/  pydantic models — the agent↔panel wire contract (also vendored
           into the agent repo, drift-checked)
```

The panel serves the API at `/api/*`, an SSE feed at `/api/stream`, uploads at
`/uploads/*`, the agent builds at `/api/agents/download/*`, and the compiled SPA
for everything else. Agents push reports to `/api/agents/{id}/report` and never
listen for the panel. The scanner is
[Cherubyte/cherubyte-agent](https://github.com/Cherubyte/cherubyte-agent).

---

## Security

- **Authentication** — first launch creates an admin account; after that the UI
  and the write API are behind a login. Passwords are PBKDF2-HMAC-SHA256 (600k
  rounds, stdlib); a session is an opaque `httponly` cookie looked up in a table,
  so logout is a row delete. Failed logins are throttled per username. Three
  roles: **viewer**, **editor**, **admin**.
- **Agents** carry a single-use enrolment token, spent once for a long-lived key
  the panel stores only as a hash.
- **API tokens** — `nsk_`-prefixed bearer tokens for scripts, stored hashed,
  shown once, always read-only.
- The SPA fallback only serves files inside `frontend/dist`; uploads are
  size-capped, validated by their leading bytes, and served under a locked-down
  CSP. CORS is off by default.

Still — don't put Cherubyte directly on the public internet. A VPN or an
authenticating reverse proxy in front is the right posture.

---

## Development

```bash
cd backend  && .venv/bin/pytest      # panel tests, no network
cd frontend && npm run build         # runs tsc --noEmit first
```

All run in CI on every push and pull request. See
[`docs/DECISIONS.md`](docs/DECISIONS.md) for why the system is shaped the way it
is — each entry anchored to the failure that produced it.

**Schema changes** go through Alembic (`backend/alembic/`). A database it has
never touched — every install predating this — is stamped at `baseline`
without re-running its DDL, since `init_db()`'s `create_all` plus a handful of
frozen additive patches already bring any database, however old, to exactly
what `baseline` builds from nothing; anything from here on is a real
migration:

```bash
cd backend && .venv/bin/alembic revision --autogenerate -m "add a column"
```

Review the generated file before committing — autogenerate is a good first
draft, not a decision.

---

## Roadmap

**Before 1.0**

- **Cut the first panel release** — the GHCR image and semver tags are wired up
  in CI but no release has been cut, so `docker compose up` needs a `build`
  first until one is (`docs/RELEASING.md`). The agent already releases from its
  own repo.
- **Run the Windows agent on real hardware once** — it's CI-tested but never
  hand-installed.

---

## License

[MIT](LICENSE). The UI font is [Inter](https://rsms.me/inter/) under the SIL Open
Font License 1.1, self-hosted in `frontend/public/fonts/` with its license file
next to it. Cherubyte makes no external font requests.
