"""The wire contract between an agent and a panel.

Both sides import these models rather than each keeping its own copy. The two
processes ship as separate images and can be upgraded independently, so a
duplicated schema would not diverge loudly — it would diverge in one field, on
one release, and the panel would quietly store nothing for it.

The split they describe: **the agent observes, the panel decides.** Everything
here is something the agent saw on the wire. Nothing here is a conclusion —
classification, naming, presence and alerting are the panel's, computed from
these observations, so improving them never needs an agent upgrade.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

#: Bumped when a change is not backward compatible. The panel refuses a report
#: whose major version it does not implement, rather than storing a partial
#: reading of it — a rejected report is visible, a half-parsed one is not.
PROTOCOL_VERSION = 1

__all__ = [
    "PROTOCOL_VERSION",
    "AgentConfig",
    "AgentReport",
    "ReportAck",
    "EnrolRequest",
    "EnrolResponse",
    "HostObservation",
    "WanObservation",
]


class HostObservation(BaseModel):
    """One host as a single sweep saw it."""

    mac: str
    ip: str
    subnet: str | None = None

    # True when this sweep fully probed the host. False on a discovery-only
    # cycle, where the absence of a signal means "not asked" rather than
    # "not there" — the panel needs the difference to avoid reading a skipped
    # cycle as every port closing at once.
    identified: bool = False

    hostname: str | None = None                     # reverse DNS
    open_ports: dict[int, str] = Field(default_factory=dict)
    mdns_name: str | None = None
    mdns_model: str | None = None
    mdns_services: list[str] = Field(default_factory=list)
    ssdp_name: str | None = None
    ssdp_vendor: str | None = None
    ssdp_model: str | None = None
    netbios_name: str | None = None
    http_server: str | None = None
    http_title: str | None = None
    ttl_os: str | None = None
    dhcp_param_list: str = ""
    dhcp_vendor_class: str | None = None
    dhcp_hostname: str | None = None


class WanObservation(BaseModel):
    """One internet reachability probe."""

    target: str
    ok: bool
    latency_ms: float | None = None
    at: datetime | None = None
    # The network's egress address as seen from the internet, resolved from the
    # agent's vantage point during this probe. None when the probe failed or the
    # lookup did not answer. It is an observation like any other here — what the
    # panel does with it (show it, redact it) is the panel's.
    public_ip: str | None = None


class AgentReport(BaseModel):
    """One sweep, as delivered to the panel."""

    protocol_version: int = PROTOCOL_VERSION
    sent_at: datetime
    # CIDRs this agent swept, so the panel can group and label them without
    # having to see the interfaces itself.
    subnets: list[str] = Field(default_factory=list)
    hosts: list[HostObservation] = Field(default_factory=list)
    wan: list[WanObservation] = Field(default_factory=list)
    # DHCP fingerprints the agent's passive sniffer has collected, by MAC.
    dhcp_fingerprints: int = 0
    # False when the sweep found nothing at all. A healthy sweep always sees at
    # least the agent's own host, so this is "the scan is broken", not "the
    # network emptied" — and the panel must not expire devices on it.
    healthy: bool = True
    # Where this agent's health/trigger server is listening. The panel uses it,
    # with the address the report arrived from, to ask for an out-of-band sweep.
    health_port: int = 1002


class AgentConfig(BaseModel):
    """What the panel wants this agent to do, sent back with every ack.

    The point is that an agent is configured from the panel, not from the box
    it runs on: installing one should mean a URL and a token and nothing else.
    An operator who *does* set a variable locally keeps it — see the agent's
    `apply_config`, which treats an explicitly set environment variable as
    pinned. Otherwise a value set on the machine would be silently overwritten
    on the first report, and the operator would have no way to see why.
    """

    scan_interval_seconds: int = 60
    identify_interval_seconds: int = 900
    identify_batch: int = 16
    full_sweep_interval_seconds: int = 900
    port_probe_concurrency: int = 256
    arp_timeout: float = 2.0
    enable_reverse_dns: bool = True
    enable_port_probe: bool = True
    enable_dhcp_sniffer: bool = True
    wan_enabled: bool = True
    wan_target: str = "1.1.1.1"
    # Empty means "work it out from the interface".
    subnets: list[str] = Field(default_factory=list)


class ReportAck(BaseModel):
    """The panel's answer to a report."""

    ok: bool = True
    found: int = 0
    degraded: bool = False
    config: AgentConfig = Field(default_factory=AgentConfig)
    # Set when someone pressed Sweep in the panel and it could not reach the
    # agent's trigger port directly. The agent should run one cycle now instead
    # of waiting out the rest of its interval.
    scan_now: bool = False


class EnrolRequest(BaseModel):
    """An agent asking to be admitted, once, with a token an operator issued."""

    token: str
    name: str
    version: str = ""


class EnrolResponse(BaseModel):
    agent_id: int
    #: Shown exactly once. The panel stores only a hash of it.
    key: str
    name: str
