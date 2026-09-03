# Decisions

Why Cherubyte is shaped the way it is. Every entry names the failure that produced
it, because a constraint without its incident gets deleted by someone who does
not know what it prevents — including by whoever wrote it, six months later.

The repository's history was rewritten before publication, so the pull requests
that carried this reasoning no longer exist. This file is where it lives now.

---

## The split: the agent observes, the panel decides

Discovery is a layer-2 job. The ARP sweep is broadcast, mDNS and SSDP are
multicast, and the neighbour table belongs to the kernel — so whatever performs
it has to sit on the network being watched, holding raw sockets. **Nothing else
does.**

Everything crossing the wire is therefore something an agent *saw*. No
conclusion travels: classification, naming, presence and alerting are all the
panel's, computed from those observations.

Two consequences worth keeping:

- The privileged half is small and holds no data. The half holding your history
  needs no privileges at all, which is what lets it be hosted somewhere the LAN
  is not.
- Improving how a device is named or classified is a **panel** upgrade that
  applies to every agent already in the field, including old ones.

`best_name` and `best_model` originally lived in the scanner. They are
interpretation, not observation, so they moved to `backend/app/services/naming.py`.

## The agent pushes; the panel never reaches back

An agent sits on somebody's LAN behind NAT. A panel that polled would need a way
in, which is the one thing a customer will not grant. Pushing also means the same
agent works unchanged against a panel hosted anywhere — pointing at a different
panel is one environment variable, and no relay is needed for it.

## The wire contract lives here; the agent repo vendors a pinned copy

`protocol/` in this repo is the source of truth — the panel imports it, and it
is the half that *defines* what a report may contain. The agent
([Cherubyte/cherubyte-agent](https://github.com/Cherubyte/cherubyte-agent))
carries a vendored copy: `protocol/UPSTREAM` there pins the commit it was taken
from, `scripts/sync-protocol.sh` re-copies it, and a CI job fails on any drift.
A duplicated schema would not diverge loudly — it would diverge in one field, on
one release, with **both sides reporting success** — so a wire change is
deliberately two commits: land it here, then bump the pin and re-sync there.

The agent repo's `agent/tests/test_contract.py` compares the scanner's
observable fields against the wire's and fails by name if the scanner grows a
signal the protocol cannot carry. Verified by adding one:

```
AssertionError: the scanner observes {'snmp_sysdescr'}, which no wire field carries
```

The panel refuses a report whose protocol version it does not implement, rather
than half-reading it. A rejected report is visible in both logs; a partially
understood one is invisible in both.

## A sweep that finds nothing is a broken scan, not an empty network

A healthy sweep always sees at least the machine the agent runs on. Zero hosts
therefore means the scan is broken — interface down, capabilities lost — and
expiring devices on it would mark everything offline at once and fan out a
notification per device.

The agent flags the report degraded; the panel keeps every device's state and
logs one alert, on the transition only. If the agent declares itself unhealthy
*and* sends hosts, the agent is believed.

Demonstrated live: on Docker's default bridge the agent sweeps `172.17.0.0/24`,
finds nothing of yours, and the panel preserves everything.

## Port changes are only diffed on a cycle that actually probed

Identification is spaced out, so most cycles probe no ports. Reading that
absence as "every port closed" would fire false alerts every minute. The report
carries `identified` per host precisely so the panel can tell *not asked* from
*not there*.

## Pinned settings are a snapshot of startup, not a live view

The panel configures the agent; a variable set on the machine wins. That set is
captured once at import, from `model_fields_set`.

If it were a live view, every field would become pinned the instant the panel
first wrote it — and **the panel could change each value exactly once**. Found
while writing the test that now guards it.

## Enrolment: machine clients carry a key, never a login

An agent cannot do an interactive login, so it is never put behind an
edge-authentication gate. It spends a single-use, 24-hour token once for a
long-lived key, of which the panel stores only a hash — proven by a test that
reads the row out of the database rather than trusting the API's own answer.

Every path refuses by default: unknown token, spent token, expired token, wrong
key, **another agent's key**, disabled agent. All of them return the same
message; distinguishing "unknown" from "already used" is free reconnaissance for
someone who is not enrolled.

## The scheduler job that never ran

The periodic scan was registered with `add_job(..., next_run_time=None)`.
APScheduler treats that as *paused*: the job appeared in the job list and never
fired. It only came alive if a settings save happened to call `reschedule()`,
and went back to sleep on the next restart.

Reproduced with two otherwise identical jobs:

```
job without next_run_time:  next_run_time=2026-08-29 13:34:33+00:00
job as it was in the repo:  next_run_time=None
firings after 3s:           {'as it was': 0, 'without': 3}
```

`backend/tests/test_scheduler_jobs.py` asserts every registered job is armed.
**Do not pass `next_run_time=None` to make a job "not run immediately"** — omit
it, which schedules the first run one interval out.

## Path traversal in the SPA fallback

`_dist / full_path` with a request path that arrives percent-decoded resolved
outside the built frontend, and `FileResponse` served it — arbitrary file read
with the service's privileges, which include `CAP_NET_RAW` or root. The `.env`
and the database were both in reach.

```
GET /%2e%2e/%2e%2e/…/etc/hostname   →   the file
```

The plain `../` form never worked because browsers normalise it; `%2e%2e` does
not. Resolve first, then require the result to still be inside — which closes the
symlink case too.

## CORS was not needed at all

`allow_origins=["*"]` on an unauthenticated LAN service let any website the user
visited read the whole device inventory and call the write endpoints. Neither
supported setup needs CORS: in production the SPA is same-origin, and in
development Vite proxies `/api` server-side. It is off unless configured.

## Uploads are bounded and sniffed, and there were two of them

`shutil.copyfileobj` wrote without limit, and the type came from the filename —
chosen by whoever is uploading. Now capped *during* the write, validated by
leading bytes, and a rejected upload leaves no partial file.

Note there were **two** upload paths: device photos and brand/OS logos. The
second was missed in the first review and had the same problem. In the logo
path the replacement is now written before the old file is deleted, so a
rejected upload cannot leave a brand with no logo.

## An uploaded SVG is a document, not a picture

`/uploads` is served from our own origin and logos accept `.svg`. Opened
directly, an SVG can run script there. It is served with
`Content-Security-Policy: … sandbox` and `X-Content-Type-Options: nosniff`,
which keeps it usable inside `<img>` and inert otherwise — better than banning
the format.

## The Windows agent speaks the SCM protocol

A console executable registered with `sc create` installs cleanly and then fails
to start with **error 1053** — the least helpful moment to discover it. The
executable therefore registers and runs itself as a service via
`win32serviceutil`.

The enrolment token goes into the machine environment rather than the service's
command line, where any user could read it with `sc qc`.

`.github/workflows/agent-windows.yml` builds the executable on a Windows runner
and then installs the service, starts it, asserts it reaches `Running`, calls its
health endpoint, stops it and removes it. Packaging and service registration are
the two things most likely to be wrong and cannot be exercised anywhere else.

## The algorithm pin in the Access verifier is not load-bearing — keep it anyway

Removing `if (header.alg !== "RS256")` does **not** make the `alg: none` test
fail: the signature is always verified as RSASSA-PKCS1-v1_5 against the JWKS key,
whatever the header claims, so the forgery already dies there. Verified by
removing the line and watching the suite stay green.

It stays as a guard against a later refactor that starts honouring `header.alg`.
Do not delete it as dead code — it guards a future, not a bug.

The audience check and the email allowlist *are* load-bearing; removing either
fails its own test.

## Tests that pass for the wrong reason

The Access tests were first written using only absent-configuration cases. They
passed — and would have passed against a verifier that did nothing at all,
because a JWKS fetch that fails also returns null.

They now sign real tokens with a real RSA key and serve a real JWKS. **When a
test guards something that matters, remove the check it depends on and confirm
the right test fails.** Every claim in this file marked "verified" was checked
that way.

## Restore swaps the files and then exits

Rewriting `cherubyte.db` while the async engine holds open connections to it
corrupts the file it is reading. So `POST /api/settings/restore` moves the new
database and uploads into place, disposes the engine, and calls `os._exit(0)`
about a second later. Every supported deployment restarts on any exit — systemd
`Restart=always`, Docker `restart: unless-stopped` — so it comes straight back
on the restored data. A hand-run `start.sh` does not restart; the response says
so.

The previous database and uploads are moved aside as `*.pre-restore` rather than
deleted, so a restore of the wrong file is undone by hand, not from a backup of
the backup.

Archive members are checked before extraction — regular files only, relative
paths only, no `..` — because `tarfile.extractall` without `filter="data"`
(Python 3.12+, and the CI floor is 3.11) will happily write outside the target
directory, and this one runs with the service's privileges.

## Protocol v2 is a lockstep bump, not a negotiated floor

Adding `dhcp_servers` to the report is backward-compatible on paper — an old
panel would ignore the field, an old agent would omit it. It is still a version
bump the panel enforces exactly (`report.protocol_version != PROTOCOL_VERSION`
→ 409), because the two images ship from one repo and one release: there is no
supported configuration where a v1 agent talks to a v2 panel, so "tolerate the
old shape" is untested code guarding a state that cannot occur. A hard refuse is
visible in both logs; a silent partial read is visible in neither.

If agent and panel ever ship on separate cadences, this is the decision to
revisit — accept `<= PROTOCOL_VERSION` and lean on the fields all being
optional.

## `snmp_sysdescr` stopped being hypothetical

The wire-contract section above used `snmp_sysdescr` as its example of a signal
the scanner might grow — the contract test even fails by that name if you add it
to `Host` without adding it to the protocol. v3 makes it real: `snmp_sysname`,
`snmp_sysdescr` and `lldp_neighbors` on `HostObservation`, all optional, behind
an opt-in `enable_snmp`.

The agent shells out to `snmpget` / `snmpwalk` rather than importing pysnmp — the
same choice as `ping` and `ip neigh`. A missing binary degrades to "no SNMP
data", logged once; it is never a hard dependency, because most LANs have
nothing that answers SNMP at all.

Only the panel interprets it: `sysDescr` feeds the OS guess ("Cisco IOS
Software…" → `Cisco IOS`), and the LLDP neighbour table becomes rows in
`topology_edges`, refreshed whole per agent so a link that goes away just stops
being re-inserted. `/api/topology` serves the edges; drawing them is still
future work.

## Wake-on-LAN goes through the agents, not the panel

The panel cannot send a magic packet — it never sits on a monitored network,
which is the whole point of the split. So a "wake" is a queued MAC, not an
action: `POST /devices/{id}/wake` writes a `pending_wakes` row, and every agent
that reports within a 90-second window is handed the MAC on its ack (`wake: []`,
additive and optional — no protocol bump). Each agent broadcasts the packet on
its own segment; only the one on the target's link reaches its NIC, the rest go
nowhere and cost nothing. Rows are cleared once they age past ten minutes.

Handing it to *every* reporting agent rather than routing by subnet keeps the
panel from having to track which agent owns which L2 segment — a mapping that is
already fuzzy for routed subnets. A randomised MAC is refused up front: the
device isn't using it while it's asleep, so the packet would wake nothing.

## Host temperature: the panel samples itself, agents ride the report

Settings ▸ Monitor charts CPU/SoC temperature for every host in the deployment.
An agent already phones home every sweep, so its reading is one more optional
field on `AgentReport` (`host_temp_c`, v5 — a lockstep bump like the others).
The panel is the one host nothing reports for, so it samples its own sensor on a
60-second APScheduler job and writes the same `host_temp_samples` table with a
NULL `agent_id`.

Reading the sensor is dependency-free and Linux-only: `/sys/class/thermal/
thermal_zone*/`, preferring a zone whose `type` names a package/CPU sensor and
falling back to the hottest. A host with nothing readable (most containers,
macOS, Windows) reports `None` and simply drops off the chart — there is no
config flag to forget to set.

`host_temp_samples` is as dense as `wan_samples` (a row a minute per host), so
the retention purge trims it on the same cutoff, and `/api/host-metrics` buckets
the window down to ~240 points before it goes over the wire rather than shipping
a week of raw minutes. The panel job carries `misfire_grace_time=45`: a reading
delayed by a busy event loop is worth more than the APScheduler default of
dropping anything more than a second late.

## The agent moved to its own repository; the panel serves it

`agent/` and `site/` are gone from this repo — the agent is
[Cherubyte/cherubyte-agent](https://github.com/Cherubyte/cherubyte-agent), the
site is [Cherubyte/cherubyte-site](https://github.com/Cherubyte/cherubyte-site).
The two halves already shipped as separate images and upgraded independently;
the repo split just makes that the default.

`protocol/` stays here (see "The wire contract lives here" above). The panel no
longer opens raw sockets or imports `scapy`/`zeroconf`, so its systemd unit
drops `CAP_NET_RAW`/`CAP_NET_ADMIN` and keeps only `CAP_NET_BIND_SERVICE`.

**Getting an agent still starts in the panel.** `services/agent_release.py`
reads the agent repo's latest GitHub release, and `/api/agents/download/{platform}`
streams the binary from the panel's own origin — so an operator installs an
agent without visiting GitHub, and a panel that can reach GitHub can hand the
binary to a machine that cannot. `/api/agents/installer/{platform}` proxies the
matching installer, which now writes its unit inline, so a native install is:

```
curl -fsSL PANEL/api/agents/download/linux -o cherubyte-agent && chmod +x cherubyte-agent
curl -fsSL PANEL/api/agents/installer/linux | sudo bash -s -- --panel PANEL --token TOK --binary ./cherubyte-agent
```

A GitHub outage degrades Settings ▸ Agents to the Docker and `git clone` paths;
it does not break the page.

## A silent agent is an alert, and the "already told you" bit lives on the row

An agent pushes a report every sweep. If one stops, the panel is blind to that
whole L2 segment and nothing else says so — `Stats.agents_stale` greys a number
on the dashboard, but nobody is looking at the dashboard, that being the point
of push alerts. `services/agent_health.check_agents()` runs on a 120-second
scheduler job, compares every enabled agent's `last_seen` against
`agent_offline_after_seconds`, and fires `agent_offline` (urgent, like
`scan_degraded`) on the way out and `agent_online` on the way back.

The "have we already alerted" flag is a column (`Agent.offline_alerted`), not an
in-memory set, for the same reason the WAN probe keeps its last state in the
panel: a panel restart in the middle of an outage must not re-notify. It clears
when the agent reports within the threshold again — checked by the same job, so
recovery can lag by up to one interval, which is fine for "it's back".

The threshold has a hard 120-second floor in code regardless of what the
operator sets: an agent that misses a single sweep (default cadence: 60s) is not
an outage, and a twitchy alert trains people to ignore it. `0` disables the
check entirely. An agent that has *never* reported since enrolment is skipped —
that is the Agents page's job to surface, not an outage notification.
