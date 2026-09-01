import json
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


def _read_app_version() -> str:
    """`frontend/package.json`'s `version` is the single source of truth for the
    app (see docs/RELEASING.md) — the frontend build reads the same file. Both a
    git checkout and the Docker image keep it at `<repo root>/frontend/package.json`."""
    pkg = BASE_DIR.parent / "frontend" / "package.json"
    try:
        return json.loads(pkg.read_text())["version"]
    except (OSError, ValueError, KeyError):
        return "0.0.0"


APP_VERSION = _read_app_version()


def _migrate_legacy_db() -> None:
    """The panel was once called NetScan and its database was `netscan.db`.
    Rename it (and its SQLite sidecars) in place on first boot so an upgrade is
    zero-touch. Only runs when there is no `cherubyte.db` yet."""
    new = DATA_DIR / "cherubyte.db"
    old = DATA_DIR / "netscan.db"
    if new.exists() or not old.exists():
        return
    for suffix in ("", "-wal", "-shm"):
        legacy = old.with_name(old.name + suffix)
        if legacy.exists():
            legacy.rename(new.with_name(new.name + suffix))


_migrate_legacy_db()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_prefix="CHERUBYTE_", extra="ignore"
    )

    # HTTP
    host: str = "0.0.0.0"
    port: int = 1001

    # Largest accepted image upload (device photos, brand / OS logos).
    max_upload_bytes: int = 5 * 1024 * 1024
    # Extra browser origins allowed to call the API, comma separated. Empty is
    # correct for both supported setups: in production the SPA is served from
    # this same origin, and the Vite dev server proxies /api server-side, so
    # neither ever makes a cross-origin request.
    cors_origins: str = ""

    # Storage
    database_url: str = f"sqlite+aiosqlite:///{DATA_DIR / 'cherubyte.db'}"

    # Multi-tenant, for the hosted panel. Off by default: a self-hosted panel
    # is one database and none of this applies. When on there is no default
    # database at all — every request has to name a tenant, and one that does
    # not is refused rather than served from somewhere shared, because in
    # multi-tenant mode a shared database is exactly the thing that must not
    # exist.
    multi_tenant: bool = False
    # One SQLite file per tenant lives here, named `<tenant_id>.db`. The id is
    # a path segment, which is why tenancy.validate_tenant_id() is strict.
    tenants_dir: str = str(DATA_DIR / "tenants")
    # The header the edge sets once it has resolved the tenant. Honoured only
    # in multi-tenant mode, and only because the origin is reachable through
    # the tunnel alone: on a panel anyone can reach, a header is not evidence.
    tenant_header: str = "X-Cherubyte-Tenant"
    # Engines to keep open. Each holds a connection and SQLite's page cache,
    # and that — not CPU — is what decides how many tenants fit in a small
    # box. Past the cap the least recently used is disposed and reopened on
    # its next request, a few milliseconds later.
    tenant_engine_cache: int = 32

    # Scanning
    # Leave empty to auto-detect the primary interface's subnet (CIDR).
    subnet: str = ""
    # Several subnets to sweep, each {"cidr": ..., "label": ...}. When non-empty
    # this supersedes `subnet`. Persisted in the DB as JSON (key "subnets").
    subnets: list[dict] = []
    interface: str = ""
    scan_interval_seconds: int = 60
    # A device not seen for this long is considered offline / to have left.
    offline_after_seconds: int = 180
    arp_timeout: float = 2.0

    # History retention. 0 keeps everything (the tables then grow without bound).
    retention_days: int = 90
    # Per-device, per-kind quiet period between notifications. Stops a device
    # with flaky Wi-Fi from fanning out a notice on every bounce. 0 disables.
    notify_cooldown_seconds: int = 900

    # Identification cadence. Probing a host (ports, reverse DNS, NetBIOS, HTTP,
    # TTL) is the expensive half of a cycle and its answers barely change, so it
    # is spread out instead of repeated every sweep.
    # Seconds before a known host is re-identified. 0 = every cycle (old behaviour).
    identify_interval_seconds: int = 900
    # Most hosts to identify per cycle; new hosts are always done immediately
    # and are never counted against it. 0 = no cap.
    identify_batch: int = 16
    # How often to ping the whole address range instead of only known addresses.
    full_sweep_interval_seconds: int = 900
    # Concurrent TCP connects across all hosts (the probe is one event loop).
    port_probe_concurrency: int = 256

    # Enrichment
    enable_reverse_dns: bool = True
    enable_port_probe: bool = True
    enable_dhcp_sniffer: bool = True
    # Passive ARP listening on the agent, alongside the active sweep — catches
    # a host that answers someone else's ARP but missed ours.
    enable_passive_arp: bool = True
    # SNMP (opt-in): names managed gear from sysDescr and draws switch links
    # from the LLDP-MIB. Needs a read community and something that answers it.
    enable_snmp: bool = False
    snmp_community: str = "public"
    # Shows the Topology nav item / page. Off by default: on a flat LAN there
    # is nothing to draw (LLDP edges only exist behind SNMP-enabled gear), so
    # most installs would just see an empty page cluttering the nav.
    topology_enabled: bool = False
    fingerbank_api_key: str = ""

    # Telegram notifications
    telegram_enabled: bool = True
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Comma-separated IPs and/or MACs of DHCP servers that are meant to be on
    # the LAN. The gateway is always allowed; anything else answering DHCP that
    # is not listed here raises a `rogue_dhcp` alert.
    dhcp_allowlist: str = ""

    # Comma-separated port numbers to leave out of the risky-port watchlist
    # (services/portrisk.py) — e.g. an SMB share you run on purpose.
    risky_ports_ignore: str = ""

    # Alert policy (which events notify, on which channel) as JSON; empty means
    # the defaults in services/alerts.py. Quiet hours are local, HH:MM; equal
    # values disable them. Alerts marked urgent ignore quiet hours.
    alert_policy: str = ""
    quiet_hours_start: str = ""
    quiet_hours_end: str = ""

    # Base URL this service is reachable at from a phone, e.g. http://192.168.1.9:1001.
    # Needed for the action buttons on ntfy notifications; empty disables them.
    public_base_url: str = ""

    # MQTT / Home Assistant
    mqtt_enabled: bool = False
    mqtt_host: str = ""
    mqtt_port: int = 1883
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_base_topic: str = "cherubyte"
    mqtt_discovery_prefix: str = "homeassistant"

    # Prometheus metrics at /api/metrics. When metrics_token is set it must be
    # sent as a bearer header or ?token=; empty leaves the endpoint open on the
    # LAN like the rest of the API.
    metrics_enabled: bool = True
    metrics_token: str = ""

    # Internet (WAN) monitoring
    wan_enabled: bool = True
    wan_target: str = "1.1.1.1"
    wan_interval_seconds: int = 60

    # Weekly digest, local time. day: 0 = Monday.
    weekly_summary_enabled: bool = False
    weekly_summary_weekday: int = 0
    weekly_summary_hour: int = 9

    # ntfy notifications
    ntfy_enabled: bool = True
    ntfy_server: str = "https://ntfy.sh"
    ntfy_topic: str = ""
    # Either an access token, or username + password (basic auth).
    ntfy_token: str = ""
    ntfy_username: str = ""
    ntfy_password: str = ""
    ntfy_priority: int = 3

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def frontend_dist(self) -> Path:
        return BASE_DIR.parent / "frontend" / "dist"


settings = Settings()
