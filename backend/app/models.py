from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime | None) -> datetime | None:
    """History is stored in UTC, but SQLite hands datetimes back naive. Re-attach
    the timezone so anything serialising the value emits an offset the browser
    can read — without it `new Date(iso)` parses the string as local time."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def iso_utc(dt: datetime | None) -> str | None:
    aware = as_utc(dt)
    return aware.isoformat() if aware is not None else None


class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    ignored = "ignored"


class DeviceType(str, enum.Enum):
    unknown = "unknown"

    # computers
    pc = "pc"
    laptop = "laptop"
    server = "server"
    vm = "vm"

    # phones, tablets, things you carry
    phone = "phone"
    voip = "voip"
    tablet = "tablet"
    ereader = "ereader"
    wearable = "wearable"

    # entertainment
    tv = "tv"
    projector = "projector"
    media = "media"
    display = "display"
    console = "console"
    speaker = "speaker"

    # network
    router = "router"
    ap = "access_point"
    hub = "hub"

    # smart home
    iot = "iot"
    thermostat = "thermostat"
    appliance = "appliance"
    vacuum = "vacuum"
    camera = "camera"
    doorbell = "doorbell"

    # other
    printer = "printer"
    nas = "nas"
    car = "car"


class EventLevel(str, enum.Enum):
    info = "info"
    success = "success"
    warning = "warning"
    alert = "alert"


class AccountRole(str, enum.Enum):
    """Who may do what once login is required.

    viewer: read-only. editor: everything a viewer can plus writes (devices,
    people, settings). admin: everything an editor can plus managing accounts.
    """

    viewer = "viewer"
    editor = "editor"
    admin = "admin"


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[AccountRole] = mapped_column(
        Enum(AccountRole), default=AccountRole.viewer
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthSession(Base):
    """An opaque login session. The cookie carries only `token`; everything
    else lives here so logout and expiry are a row delete / a timestamp."""

    __tablename__ = "auth_sessions"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(255))

    account: Mapped[Account] = relationship()


class ApiToken(Base):
    """A bearer token for scripts and scrapers — read-only, revocable.

    Like an agent key, this is stored hashed (plain SHA-256: it is 32 bytes of
    `secrets.token_urlsafe`, not a chosen password, so a slow KDF buys nothing).
    The token is shown once, on creation. It authenticates against the same
    routes a browser session does, but only ever at `viewer` level — reads pass,
    writes and account/agent management do not.
    """

    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    role: Mapped[AccountRole] = mapped_column(
        Enum(AccountRole), default=AccountRole.viewer
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    avatar: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    # Visitas: pessoas ocasionais, listadas em separado das pessoas principais.
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    devices: Mapped[list[Device]] = relationship(back_populates="user")


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    # User-set nickname. When unset the display name defaults to "Marca Modelo".
    name: Mapped[str | None] = mapped_column(String(255))
    # Best auto-detected name (mDNS / NetBIOS / reverse-DNS / UPnP).
    hostname: Mapped[str | None] = mapped_column(String(255))
    device_type: Mapped[DeviceType] = mapped_column(
        Enum(DeviceType), default=DeviceType.unknown
    )
    vendor: Mapped[str | None] = mapped_column(String(255))
    model: Mapped[str | None] = mapped_column(String(255))
    os_guess: Mapped[str | None] = mapped_column(String(255))
    icon: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)

    # Comma-separated names of auto-populated fields the user has edited by hand.
    # The scan reconciler must never overwrite a field listed here.
    overrides: Mapped[str | None] = mapped_column(String(255))

    # Last identity fingerprint the reconciler computed (JSON: os family, open
    # ports). Compared on each identified cycle so a known MAC that starts
    # presenting as a different OS raises an alert.
    fingerprint: Mapped[str | None] = mapped_column(Text)

    approval_status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus), default=ApprovalStatus.pending, index=True
    )

    is_online: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # When False the device's online state is ignored for its user's presence
    # (e.g. an always-on device that never leaves the network).
    counts_for_presence: Mapped[bool] = mapped_column(Boolean, default=True)

    # Per-device override of the alert policy for join/leave notices:
    # "default" follows the global rules, "always" notifies on every
    # join/leave regardless of them, "mute" silences this device entirely.
    notify_policy: Mapped[str] = mapped_column(String(16), default="default")

    # Free-text labels the user attaches — a room, a purpose, a person's kit.
    # Comma-separated on the column; `tag_list` / `set_tags` do the parsing.
    tags: Mapped[str | None] = mapped_column(String(255))

    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    user: Mapped[User | None] = relationship(back_populates="devices")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    macs: Mapped[list[MacAddress]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )
    ips: Mapped[list[IpAddress]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )
    images: Mapped[list[DeviceImage]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )
    open_ports: Mapped[list[OpenPort]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )

    @property
    def short_vendor(self) -> str | None:
        return _short_vendor(self.vendor)

    @property
    def os_family(self) -> str | None:
        return _os_family(self.os_guess)

    @property
    def locked_fields(self) -> set[str]:
        return {f for f in (self.overrides or "").split(",") if f}

    @property
    def tag_list(self) -> list[str]:
        return [t for t in (self.tags or "").split(",") if t]

    def set_tags(self, values: list[str]) -> None:
        seen: dict[str, str] = {}
        for raw in values:
            t = " ".join(raw.split()).strip(" #").strip()[:32]
            if t and t.lower() not in seen:
                seen[t.lower()] = t
        self.tags = ",".join(seen.values()) or None

    @property
    def default_label(self) -> str:
        """Label shown when no nickname is set.

        A meaningful detected name wins; otherwise fall back to "Marca Modelo".
        """
        if self.hostname and not _generic_host(self.hostname):
            return self.hostname
        v, m = self.short_vendor, (self.model or "").strip()
        if v and m:
            vlow = v.lower()
            if vlow in m.lower() or any(w in m.lower() for w in vlow.split()):
                return m
            return f"{v} {m}"
        if v:
            return v
        if self.hostname:
            return self.hostname
        return self.macs[0].address if self.macs else f"device-{self.id}"

    @property
    def display_name(self) -> str:
        return self.name or self.default_label


# OUI vendor string (substring, lowercase) -> clean brand name
_VENDOR_CANON: tuple[tuple[str, str], ...] = (
    ("apple", "Apple"),
    ("samsung", "Samsung"),
    ("sony interactive", "Sony"),
    ("sony", "Sony"),
    ("nintendo", "Nintendo"),
    ("microsoft", "Microsoft"),
    ("google", "Google"),
    ("amazon", "Amazon"),
    ("intel", "Intel"),
    ("raspberry pi", "Raspberry Pi"),
    ("espressif", "Espressif"),
    ("mercusys", "Mercusys"),
    ("tp-link", "TP-Link"),
    ("tplink", "TP-Link"),
    ("ubiquiti", "Ubiquiti"),
    ("mikrotik", "MikroTik"),
    ("netgear", "Netgear"),
    ("d-link", "D-Link"),
    ("huawei", "Huawei"),
    ("xiaomi", "Xiaomi"),
    ("hui zhou gaoshengda", "Lenovo"),
    ("lenovo", "Lenovo"),
    ("liteon", "Liteon"),
    ("hewlett", "HP"),
    ("hp inc", "HP"),
    ("dell", "Dell"),
    ("asustek", "ASUS"),
    ("asus", "ASUS"),
    ("lg electronics", "LG"),
    ("sonos", "Sonos"),
    ("philips", "Philips"),
    ("signify", "Philips Hue"),
    ("ubee", "Ubee"),
    ("sagemcom", "Sagemcom"),
    ("technicolor", "Technicolor"),
    ("arcadyan", "Arcadyan"),
    ("synology", "Synology"),
    ("qnap", "QNAP"),
    ("hikvision", "Hikvision"),
    ("dahua", "Dahua"),
    ("reolink", "Reolink"),
    ("roku", "Roku"),
    ("tuya", "Tuya"),
    ("shelly", "Shelly"),
    ("realtek", "Realtek"),
)

_VENDOR_NOISE = (
    ", inc.", ", inc", " inc.", " inc", " corporation", " corporate", " co.,ltd",
    " co., ltd", " co.,limited", " co., limited", " technologies", " technology",
    " electronics", " communications", " gmbh", " s.a.", " ltd.", " ltd", " llc",
    " (shenzhen)", " international", " company", " co.", " limited",
)


def _short_vendor(vendor: str | None) -> str | None:
    if not vendor:
        return None
    low = vendor.strip().lower()
    for needle, canon in _VENDOR_CANON:
        if needle in low:
            return canon
    v = vendor.strip()
    low = v.lower()
    for noise in _VENDOR_NOISE:
        idx = low.find(noise)
        if idx > 0:
            v = v[:idx]
            low = v.lower()
    return v.strip(" ,.")


_OS_CANON: tuple[tuple[str, str], ...] = (
    ("ipados", "iPadOS"),
    ("ios", "iOS"),
    ("tvos", "tvOS"),
    ("watchos", "watchOS"),
    ("macos", "macOS"),
    ("mac os", "macOS"),
    ("os x", "macOS"),
    ("windows", "Windows"),
    ("android", "Android"),
    ("chrome os", "ChromeOS"),
    ("chromeos", "ChromeOS"),
    ("playstation", "PlayStation OS"),
    ("tizen", "Tizen"),
    ("webos", "webOS"),
    ("roku", "Roku OS"),
    ("fire os", "Fire OS"),
    ("linux", "Linux"),
    ("unix", "Linux"),
    ("apple", "Apple OS"),
)


def _os_family(os_guess: str | None) -> str | None:
    if not os_guess:
        return None
    low = os_guess.strip().lower()
    # explicit "no OS" — the user cleared it; keep it out of the stats entirely
    if low in {"none", "nenhum", "n/a", "-", "—"}:
        return None
    for needle, canon in _OS_CANON:
        if needle in low:
            return canon
    return os_guess.strip() or None


def _generic_host(host: str) -> bool:
    import re

    h = host.lower().strip()
    return (
        not h
        or h in {"localhost", "unknown"}
        or h.startswith(("android-", "espressif", "amazon-", "dhcp-", "ip-"))
        or h.replace("-", "").replace(".", "").isdigit()
        # auto-generated "MAC-1E310A", "ESP-A1B2C3", "device-4f2a"
        or bool(re.fullmatch(r"[a-z]{2,10}[-_][0-9a-f]{4,8}", h))
    )


class MacAddress(Base):
    __tablename__ = "mac_addresses"
    __table_args__ = (UniqueConstraint("address", name="uq_mac_address"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    address: Mapped[str] = mapped_column(String(17), index=True)
    vendor: Mapped[str | None] = mapped_column(String(255))
    is_random: Mapped[bool] = mapped_column(Boolean, default=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    device: Mapped[Device] = relationship(back_populates="macs")


class IpAddress(Base):
    __tablename__ = "ip_addresses"
    __table_args__ = (UniqueConstraint("address", name="uq_ip_address"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    address: Mapped[str] = mapped_column(String(45), index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    device: Mapped[Device] = relationship(back_populates="ips")


class OpenPort(Base):
    __tablename__ = "open_ports"
    __table_args__ = (UniqueConstraint("device_id", "port", name="uq_device_port"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    port: Mapped[int] = mapped_column(Integer)
    service: Mapped[str | None] = mapped_column(String(64))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    device: Mapped[Device] = relationship(back_populates="open_ports")


class DeviceImage(Base):
    __tablename__ = "device_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    device: Mapped[Device] = relationship(back_populates="images")


class ConnectionHistory(Base):
    """Append-only log of join/leave transitions per device."""

    __tablename__ = "connection_history"
    # the presence grid reads one device's history inside a time window
    __table_args__ = (Index("ix_conn_history_device_ts", "device_id", "timestamp"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    event: Mapped[str] = mapped_column(String(16))  # "join" | "leave"
    ip: Mapped[str | None] = mapped_column(String(45))
    mac: Mapped[str | None] = mapped_column(String(17))
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[EventLevel] = mapped_column(Enum(EventLevel), default=EventLevel.info)
    category: Mapped[str] = mapped_column(String(64), default="system")
    message: Mapped[str] = mapped_column(Text)
    device_id: Mapped[int | None] = mapped_column(
        ForeignKey("devices.id", ondelete="SET NULL")
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class TopologyEdge(Base):
    """One link an LLDP-MIB read reported: a local device's port connects to a
    neighbour's port. Refreshed whole per agent on each report that carries
    LLDP data, so a link that goes away simply stops being re-inserted.
    """

    __tablename__ = "topology_edges"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent_id: Mapped[int | None] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), index=True
    )
    # The device the LLDP table was read from, when we could match it to one.
    local_device_id: Mapped[int | None] = mapped_column(
        ForeignKey("devices.id", ondelete="SET NULL")
    )
    local_label: Mapped[str] = mapped_column(String(255), default="")
    local_port: Mapped[str | None] = mapped_column(String(120))
    remote_label: Mapped[str] = mapped_column(String(255), default="")
    remote_port: Mapped[str | None] = mapped_column(String(120))
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Brand(Base):
    """A manufacturer, keyed by its normalised short name, with an optional logo."""

    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    logo: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OsLogo(Base):
    """An operating-system family, keyed by its canonical name, with a logo."""

    __tablename__ = "os_logos"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    logo: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Agent(Base):
    """A scanning agent admitted to this panel.

    The key is stored hashed, like a password: the panel never needs the
    original, and a database that leaks then yields nothing that can be
    replayed against it.
    """

    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    key_hash: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str | None] = mapped_column(String(32))
    subnets: Mapped[str | None] = mapped_column(Text)      # JSON list of CIDRs
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The address the last report came from, and where its trigger server
    # listens — together they let the panel ask for an out-of-band sweep.
    last_ip: Mapped[str | None] = mapped_column(String(45))
    health_port: Mapped[int] = mapped_column(Integer, default=1002)
    # Set when Sweep was pressed and the panel could not reach the agent
    # directly; sent on the next ack, then cleared.
    scan_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    # The egress address this agent's network shows the internet, and when it
    # was last confirmed. Per-agent because two agents on two networks have two.
    public_ip: Mapped[str | None] = mapped_column(String(45))
    public_ip_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_hosts: Mapped[int] = mapped_column(Integer, default=0)
    last_fingerprints: Mapped[int] = mapped_column(Integer, default=0)
    last_healthy: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EnrolmentToken(Base):
    """A single-use, expiring invitation for an agent to join.

    Single-use and expiring because it is the one credential an operator has to
    copy into a container's environment, where it tends to stay: a token that
    outlived its use would be a permanent way in.
    """

    __tablename__ = "enrolment_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    label: Mapped[str | None] = mapped_column(String(120))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    used_by_agent_id: Mapped[int | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WanSample(Base):
    """One reachability probe of the internet, for the uptime/latency chart."""

    __tablename__ = "wan_samples"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    target: Mapped[str] = mapped_column(String(64), default="")


class HostTempSample(Base):
    """One CPU/SoC temperature reading of a host that feeds this panel — the
    panel's own machine (`agent_id` NULL) or an agent's (`agent_id` set), for
    the Settings ▸ Monitor chart. As dense as `wan_samples`: one row per minute
    per host, so the retention purge trims it the same way."""

    __tablename__ = "host_temp_samples"
    __table_args__ = (Index("ix_host_temp_agent_ts", "agent_id", "timestamp"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    # NULL means "the panel host itself".
    agent_id: Mapped[int | None] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), index=True
    )
    temp_c: Mapped[float] = mapped_column(Float)


class PendingWake(Base):
    """A Wake-on-LAN request queued for the agents. Every agent that reports
    within a short window after the request sends the magic packet — only the
    one on the target's segment reaches its NIC; the rest are harmless. Rows are
    cleared once they age out."""

    __tablename__ = "pending_wakes"

    id: Mapped[int] = mapped_column(primary_key=True)
    mac: Mapped[str] = mapped_column(String(17), unique=True)
    device_id: Mapped[int | None] = mapped_column(
        ForeignKey("devices.id", ondelete="SET NULL")
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
