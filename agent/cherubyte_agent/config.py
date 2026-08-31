"""Agent configuration. Everything comes from the environment — the agent has
no database and no UI of its own, by design: it is the half that may need raw
sockets and host networking, so it holds as little as possible."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
STATE_DIR = Path("/var/lib/cherubyte-agent")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_prefix="CHERUBYTE_AGENT_", extra="ignore"
    )

    # Where the panel is, and how this agent proves who it is. The enrolment
    # token is spent once, on first start, for a long-lived key.
    panel_url: str = "http://panel:1001"
    enrol_token: str = ""
    name: str = ""
    # Where the issued key is kept between restarts. Mount this.
    state_file: str = str(STATE_DIR / "agent.json")

    # Health endpoint, so a container runtime can tell a wedged agent from a
    # working one. Deliberately not an API — the agent takes no orders.
    health_host: str = "0.0.0.0"
    health_port: int = 1002

    # Scanning. Mirrors what the panel used to own; see the scanner module.
    subnet: str = ""
    subnets: list[dict] = []
    interface: str = ""
    scan_interval_seconds: int = 60
    arp_timeout: float = 2.0
    identify_interval_seconds: int = 900
    identify_batch: int = 16
    full_sweep_interval_seconds: int = 900
    port_probe_concurrency: int = 256
    enable_reverse_dns: bool = True
    enable_port_probe: bool = True
    enable_dhcp_sniffer: bool = True
    enable_snmp: bool = False
    snmp_community: str = "public"

    # Internet reachability probe, reported alongside the sweep.
    wan_enabled: bool = True
    wan_target: str = "1.1.1.1"

    # How long to wait for the panel before giving up on one report.
    report_timeout_seconds: float = 30.0


settings = Settings()

# Fields the operator set explicitly on this machine. The panel's configuration
# fills in everything else, but never overrules these: a value set on the box
# and then silently overwritten on the first report is a setting whose owner
# has no way to see why it did not take.
PINNED: frozenset[str] = frozenset(settings.model_fields_set)


def apply_config(config, *, pinned: frozenset[str] = PINNED) -> list[str]:
    """Adopt the panel's configuration for every field not pinned locally.

    Returns the names of the fields that changed, so a restart is not needed to
    tell whether the panel is actually driving this agent.
    """
    changed: list[str] = []
    for field, value in config.model_dump().items():
        if field in pinned or not hasattr(settings, field):
            continue
        if field == "subnets":
            value = [{"cidr": c, "label": ""} for c in value]
        if getattr(settings, field) == value:
            continue
        setattr(settings, field, value)
        changed.append(field)
    return changed
