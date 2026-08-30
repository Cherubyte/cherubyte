export type ApprovalStatus = "pending" | "approved" | "ignored";

export type DeviceType =
  | "unknown"
  | "pc"
  | "laptop"
  | "server"
  | "phone"
  | "voip"
  | "tablet"
  | "ereader"
  | "wearable"
  | "tv"
  | "projector"
  | "media"
  | "display"
  | "console"
  | "speaker"
  | "router"
  | "access_point"
  | "hub"
  | "iot"
  | "thermostat"
  | "appliance"
  | "vacuum"
  | "camera"
  | "doorbell"
  | "printer"
  | "nas"
  | "car";

export type EventLevel = "info" | "success" | "warning" | "alert";

export type NotifyPolicy = "default" | "always" | "mute";

export type AccountRole = "viewer" | "editor" | "admin";

export interface Account {
  id: number;
  username: string;
  role: AccountRole;
  created_at: string;
  last_login: string | null;
}

export interface AuthStatus {
  setup_required: boolean;
  account: Account | null;
}

export interface FingerbankTest {
  status: "no_key" | "ok" | "invalid_key" | "rate_limited" | "error";
  name?: string | null;
  os?: string | null;
  score?: number | null;
  detail?: string;
}

export interface Mac {
  address: string;
  vendor: string | null;
  is_random: boolean;
  last_seen: string;
}

export interface Ip {
  address: string;
  is_primary: boolean;
  last_seen: string;
}

export interface Port {
  port: number;
  service: string | null;
}

export interface DeviceImage {
  id: number;
  filename: string;
  is_primary: boolean;
  url: string;
}

export interface UserRef {
  id: number;
  name: string;
  avatar: string | null;
}

export interface Device {
  id: number;
  name: string | null;
  hostname: string | null;
  display_name: string;
  default_label: string;
  short_vendor: string | null;
  device_type: DeviceType;
  vendor: string | null;
  model: string | null;
  os_guess: string | null;
  os_family: string | null;
  icon: string | null;
  notes: string | null;
  approval_status: ApprovalStatus;
  is_online: boolean;
  counts_for_presence: boolean;
  notify_policy: NotifyPolicy;
  first_seen: string;
  last_seen: string;
  user: UserRef | null;
  macs: Mac[];
  ips: Ip[];
  open_ports: Port[];
  images: DeviceImage[];
}

export interface EventItem {
  id: number;
  level: EventLevel;
  category: string;
  message: string;
  device_id: number | null;
  timestamp: string;
}

export interface Connection {
  id: number;
  device_id: number;
  event: "join" | "leave";
  ip: string | null;
  mac: string | null;
  timestamp: string;
}

export interface User {
  id: number;
  name: string;
  avatar: string | null;
  notes: string | null;
  is_guest: boolean;
  is_present: boolean;
  device_count: number;
}

export interface UserDeviceMini {
  id: number;
  display_name: string;
  short_vendor: string | null;
  device_type: DeviceType;
  icon: string | null;
  is_online: boolean;
  counts_for_presence: boolean;
  last_seen: string;
  primary_image: string | null;
}

export interface UserDetail extends User {
  devices: UserDeviceMini[];
}

export interface PresenceData {
  /** server "now", UTC ISO — the right edge of today's row */
  now: string;
  /** oldest instant the window covers, UTC ISO */
  since: string;
  /** [start, end] pairs, UTC ISO, merged and sorted */
  intervals: [string, string][];
}

export interface Brand {
  name: string;
  logo_url: string | null;
  device_count: number;
}

export type OsLogo = Brand;

export interface TimelinePoint {
  date: string;
  new_devices: number;
  total: number;
}

export interface Timeline {
  days: number;
  starting_total: number;
  series: TimelinePoint[];
}

export interface TypeCount {
  type: DeviceType;
  count: number;
}

export interface BrandCount {
  brand: string;
  count: number;
  online: number;
  logo: string | null;
}

export interface Stats {
  total: number;
  online: number;
  pending: number;
  approved: number;
  users_present: number;
  subnet: string;
  last_scan: string | null;
}

export interface SubnetCfg {
  cidr: string;
  label: string;
}

export interface AppSettings {
  subnet: string;
  subnets: SubnetCfg[];
  scan_interval_seconds: number;
  offline_after_seconds: number;
  identify_interval_seconds: number;
  retention_days: number;
  stored_events: number;
  stored_connections: number;
  telegram_enabled: boolean;
  telegram_configured: boolean;
  telegram_token_saved: boolean;
  telegram_chat_id: string | null;
  ntfy_configured: boolean;
  ntfy_enabled: boolean;
  ntfy_server: string;
  ntfy_topic: string;
  ntfy_username: string;
  ntfy_priority: number;
  /** True when a token or password is stored; the secret itself is never returned. */
  ntfy_auth_configured: boolean;
  fingerbank_configured: boolean;
  dhcp_fingerprints: number;
  alert_policy: Record<string, AlertRule>;
  alert_kinds: AlertKind[];
  quiet_hours_start: string;
  quiet_hours_end: string;
  public_base_url: string;
  notification_actions_ready: boolean;
  mqtt_enabled: boolean;
  mqtt_host: string;
  mqtt_port: number;
  mqtt_username: string;
  mqtt_base_topic: string;
  mqtt_discovery_prefix: string;
  mqtt_auth_configured: boolean;
  wan_enabled: boolean;
  wan_target: string;
  wan_interval_seconds: number;
  weekly_summary_enabled: boolean;
  weekly_summary_weekday: number;
  weekly_summary_hour: number;
}

export interface AlertRule {
  enabled: boolean;
  channels: string[];
}

export interface AlertKind {
  key: string;
  label: string;
  urgent: boolean;
}

export interface WanPoint {
  t: string;
  ok: boolean;
  ms: number | null;
}

export interface WanStatus {
  samples: number;
  uptime: number | null;
  avg_latency_ms: number | null;
  online: boolean | null;
  target: string;
  public_ip: string | null;
  public_ip_at: string | null;
  points: WanPoint[];
}

export interface MergeSuggestion {
  reason: string;
  confidence: string;
  target: { id: number; name: string };
  duplicates: { id: number; name: string; first_seen: string }[];
}


export interface AgentRow {
  id: number;
  name: string;
  version: string | null;
  enabled: boolean;
  subnets: string[];
  last_seen: string | null;
  last_hosts: number;
  last_fingerprints: number;
  last_healthy: boolean;
  public_ip: string | null;
  public_ip_at: string | null;
}

export interface EnrolToken {
  token: string;
  expires_in_hours: number;
}
