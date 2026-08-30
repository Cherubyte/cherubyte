from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, computed_field

from .models import AccountRole, ApprovalStatus, DeviceType, EventLevel, as_utc

# SQLite returns naive datetimes even for DateTime(timezone=True) columns, and
# Pydantic then serialises them with no offset — the browser reads that as local
# time. Coerce every outbound datetime to aware-UTC so the wire always carries a
# "+00:00"/"Z" and the client can render it in the viewer's own timezone.
AwareUtc = Annotated[datetime, BeforeValidator(as_utc)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MacOut(ORMModel):
    address: str
    vendor: str | None = None
    is_random: bool = False
    last_seen: AwareUtc


class IpOut(ORMModel):
    address: str
    is_primary: bool = False
    last_seen: AwareUtc


class PortOut(ORMModel):
    port: int
    service: str | None = None


class ImageOut(ORMModel):
    id: int
    filename: str
    is_primary: bool

    @computed_field
    @property
    def url(self) -> str:
        return f"/uploads/{self.filename}"


class UserRef(ORMModel):
    id: int
    name: str
    avatar: str | None = None


class DeviceOut(ORMModel):
    id: int
    name: str | None = None
    hostname: str | None = None
    display_name: str
    default_label: str
    short_vendor: str | None = None
    device_type: DeviceType
    vendor: str | None = None
    model: str | None = None
    os_guess: str | None = None
    icon: str | None = None
    notes: str | None = None
    os_family: str | None = None
    approval_status: ApprovalStatus
    is_online: bool
    counts_for_presence: bool = True
    notify_policy: str = "default"
    first_seen: AwareUtc
    last_seen: AwareUtc
    user: UserRef | None = None
    macs: list[MacOut] = []
    ips: list[IpOut] = []
    open_ports: list[PortOut] = []
    images: list[ImageOut] = []


class DeviceUpdate(BaseModel):
    name: str | None = None
    device_type: DeviceType | None = None
    vendor: str | None = None
    model: str | None = None
    os_guess: str | None = None
    icon: str | None = None
    notes: str | None = None
    user_id: int | None = None
    approval_status: ApprovalStatus | None = None
    counts_for_presence: bool | None = None
    notify_policy: Literal["default", "always", "mute"] | None = None


class MergeRequest(BaseModel):
    source_ids: list[int]


class AbsorbMacRequest(BaseModel):
    address: str


class EventOut(ORMModel):
    id: int
    level: EventLevel
    category: str
    message: str
    device_id: int | None = None
    timestamp: AwareUtc


class ConnectionOut(ORMModel):
    id: int
    device_id: int
    event: str
    ip: str | None = None
    mac: str | None = None
    timestamp: AwareUtc


class UserOut(ORMModel):
    id: int
    name: str
    avatar: str | None = None
    notes: str | None = None
    is_guest: bool = False
    is_present: bool = False
    device_count: int = 0


class UserIn(BaseModel):
    name: str
    avatar: str | None = None
    notes: str | None = None
    is_guest: bool = False


class UserPatch(BaseModel):
    name: str | None = None
    avatar: str | None = None
    notes: str | None = None
    is_guest: bool | None = None


class DeviceMini(ORMModel):
    id: int
    display_name: str
    short_vendor: str | None = None
    device_type: DeviceType
    icon: str | None = None
    is_online: bool
    counts_for_presence: bool = True
    last_seen: AwareUtc
    images: list[ImageOut] = Field(default=[], exclude=True)

    @computed_field
    @property
    def primary_image(self) -> str | None:
        chosen = next((i for i in self.images if i.is_primary), None) or (
            self.images[0] if self.images else None
        )
        return chosen.url if chosen else None


class UserDetailOut(UserOut):
    devices: list[DeviceMini] = []


class BrandOut(BaseModel):
    name: str
    logo_url: str | None = None
    device_count: int = 0


class OsLogoOut(BaseModel):
    name: str
    logo_url: str | None = None
    device_count: int = 0


class SubnetCfg(BaseModel):
    cidr: str
    label: str = ""


class SettingsOut(BaseModel):
    subnet: str
    subnets: list[SubnetCfg] = []
    scan_interval_seconds: int
    offline_after_seconds: int
    identify_interval_seconds: int = 900
    retention_days: int = 90
    stored_events: int = 0
    stored_connections: int = 0
    telegram_enabled: bool = True
    telegram_configured: bool
    telegram_token_saved: bool = False
    telegram_chat_id: str | None = None
    ntfy_configured: bool = False
    ntfy_enabled: bool = True
    ntfy_server: str = "https://ntfy.sh"
    ntfy_topic: str = ""
    ntfy_username: str = ""
    ntfy_priority: int = 3
    # True when a token or password is stored; the secret itself is never returned.
    ntfy_auth_configured: bool = False
    fingerbank_configured: bool = False
    dhcp_fingerprints: int = 0
    # alerts
    alert_policy: dict[str, dict] = {}
    quiet_hours_start: str = ""
    quiet_hours_end: str = ""
    alert_kinds: list[dict] = []
    public_base_url: str = ""
    notification_actions_ready: bool = False
    # mqtt
    mqtt_enabled: bool = False
    mqtt_host: str = ""
    mqtt_port: int = 1883
    mqtt_username: str = ""
    mqtt_base_topic: str = "netscan"
    mqtt_discovery_prefix: str = "homeassistant"
    mqtt_auth_configured: bool = False
    # wan
    wan_enabled: bool = True
    wan_target: str = "1.1.1.1"
    wan_interval_seconds: int = 60
    # metrics
    metrics_enabled: bool = True
    metrics_token_set: bool = False
    metrics_path: str = "/api/metrics"
    # weekly digest
    weekly_summary_enabled: bool = False
    weekly_summary_weekday: int = 0
    weekly_summary_hour: int = 9


class SettingsIn(BaseModel):
    scan_interval_seconds: int | None = None
    offline_after_seconds: int | None = None
    identify_interval_seconds: int | None = None
    retention_days: int | None = None
    subnet: str | None = None
    subnets: list[SubnetCfg] | None = None
    telegram_enabled: bool | None = None
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    ntfy_enabled: bool | None = None
    ntfy_server: str | None = None
    ntfy_topic: str | None = None
    ntfy_token: str | None = None
    ntfy_username: str | None = None
    ntfy_password: str | None = None
    ntfy_priority: int | None = None
    fingerbank_api_key: str | None = None
    alert_policy: dict[str, dict] | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    public_base_url: str | None = None
    mqtt_enabled: bool | None = None
    mqtt_host: str | None = None
    mqtt_port: int | None = None
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_base_topic: str | None = None
    mqtt_discovery_prefix: str | None = None
    wan_enabled: bool | None = None
    wan_target: str | None = None
    wan_interval_seconds: int | None = None
    metrics_enabled: bool | None = None
    metrics_token: str | None = None
    weekly_summary_enabled: bool | None = None
    weekly_summary_weekday: int | None = None
    weekly_summary_hour: int | None = None


class AccountOut(ORMModel):
    id: int
    username: str
    role: AccountRole
    created_at: AwareUtc
    last_login: AwareUtc | None = None


class AuthStatusOut(BaseModel):
    setup_required: bool
    account: AccountOut | None = None


class LoginIn(BaseModel):
    username: str
    password: str


class AccountCreateIn(BaseModel):
    username: str
    password: str
    role: AccountRole = AccountRole.viewer


class AccountPatchIn(BaseModel):
    role: AccountRole | None = None
    password: str | None = None


class ApiTokenOut(ORMModel):
    id: int
    name: str
    role: AccountRole
    created_at: AwareUtc
    last_used_at: AwareUtc | None = None


class ApiTokenCreateIn(BaseModel):
    name: str


class ApiTokenCreatedOut(ApiTokenOut):
    # populated once, on creation, then never again
    token: str = ""


class ProfileUpdateIn(BaseModel):
    """Change your own username and/or password. `current` is always required."""

    current: str
    username: str | None = None
    new_password: str | None = None


class StatsOut(BaseModel):
    total: int
    online: int
    pending: int
    approved: int
    users_present: int
    subnet: str
    last_scan: AwareUtc | None = None
    # Agent health, so the UI can say when the monitor has gone blind.
    agents_configured: int = 0
    last_report: AwareUtc | None = None
    agents_stale: bool = False
