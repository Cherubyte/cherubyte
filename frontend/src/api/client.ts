import type {
  Account,
  AccountRole,
  ApiToken,
  AgentRow,
  AlertRule,
  AppSettings,
  AuthStatus,
  EnrolToken,
  Brand,
  BrandCount,
  Connection,
  Device,
  DeviceType,
  EventItem,
  FingerbankTest,
  NotifyPolicy,
  PresenceData,
  Stats,
  Timeline,
  TypeCount,
  MergeSuggestion,
  User,
  UserDetail,
  WanStatus,
} from "./types";

const BASE = "/api";

export class ApiError extends Error {
  constructor(message: string, readonly stale = false, readonly status = 0) {
    super(message);
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new ApiError(
      `${res.status} ${res.statusText} — ${body.slice(0, 200)}`,
      false,
      res.status,
    );
  }
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") ?? "";
  if (!ct.includes("json")) {
    // old backend has no such route -> SPA fallback served index.html
    throw new ApiError(
      "Endpoint em falta — reinicia o backend (sudo systemctl restart cherubyte).",
      true,
    );
  }
  return res.json() as Promise<T>;
}

export interface DevicePatch {
  name?: string | null;
  device_type?: DeviceType;
  vendor?: string | null;
  model?: string | null;
  os_guess?: string | null;
  notes?: string | null;
  user_id?: number | null;
  counts_for_presence?: boolean;
  notify_policy?: NotifyPolicy;
  tags?: string[];
}

export const api = {
  stats: () => req<Stats>("/stats"),

  devices: (params?: { status?: string; online?: boolean; q?: string }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.online !== undefined) qs.set("online", String(params.online));
    if (params?.q) qs.set("q", params.q);
    const s = qs.toString();
    return req<Device[]>(`/devices${s ? `?${s}` : ""}`);
  },
  device: (id: number) => req<Device>(`/devices/${id}`),
  updateDevice: (id: number, patch: DevicePatch) =>
    req<Device>(`/devices/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  approveDevice: (id: number) => req<Device>(`/devices/${id}/approve`, { method: "POST" }),
  ignoreDevice: (id: number) => req<Device>(`/devices/${id}/ignore`, { method: "POST" }),
  wakeDevice: (id: number) => req<{ ok: boolean; mac: string }>(`/devices/${id}/wake`, { method: "POST" }),
  deleteDevice: (id: number) => req<void>(`/devices/${id}`, { method: "DELETE" }),
  deviceHistory: (id: number) => req<Connection[]>(`/devices/${id}/history`),
  deviceUptime: (id: number, days = 30) =>
    req<{ days: number; ratio: number | null; since: string; now: string; samples: number }>(
      `/devices/${id}/uptime?days=${days}`,
    ),
  devicesCsvUrl: () => BASE + "/devices/export.csv",
  deviceTags: () => req<string[]>("/devices/tags"),
  mergeDevices: (targetId: number, sourceIds: number[]) =>
    req<Device>(`/devices/${targetId}/merge`, {
      method: "POST",
      body: JSON.stringify({ source_ids: sourceIds }),
    }),
  absorbMac: (targetId: number, address: string) =>
    req<Device>(`/devices/${targetId}/absorb-mac`, {
      method: "POST",
      body: JSON.stringify({ address }),
    }),
  detachMac: (deviceId: number, address: string) =>
    req<Device>(`/devices/${deviceId}/macs/${encodeURIComponent(address)}`, {
      method: "DELETE",
    }),
  uploadImage: async (id: number, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`${BASE}/devices/${id}/images`, { method: "POST", body: fd });
    if (!res.ok) throw new Error(await res.text());
    return res.json() as Promise<Device>;
  },
  deleteImage: (id: number, imageId: number) =>
    req<Device>(`/devices/${id}/images/${imageId}`, { method: "DELETE" }),

  scan: () =>
    req<{
      ok: boolean;
      status: "triggered" | "queued" | "stale" | "no-agents";
      agents: number;
      triggered: number;
      queued: number;
      last_report: string | null;
      stale: boolean;
      detail: string;
    }>("/scan", { method: "POST" }),

  events: (params?: { level?: string; category?: string; device_id?: number }) => {
    const qs = new URLSearchParams();
    if (params?.level) qs.set("level", params.level);
    if (params?.category) qs.set("category", params.category);
    if (params?.device_id) qs.set("device_id", String(params.device_id));
    const s = qs.toString();
    return req<EventItem[]>(`/events${s ? `?${s}` : ""}`);
  },
  connections: () => req<Connection[]>("/events/connections"),

  users: () => req<User[]>("/users"),
  user: (id: number) => req<UserDetail>(`/users/${id}`),
  userPresence: (id: number, days = 10) =>
    req<PresenceData>(`/users/${id}/presence?days=${days}`),
  createUser: (data: { name: string; notes?: string; is_guest?: boolean }) =>
    req<User>("/users", { method: "POST", body: JSON.stringify(data) }),
  updateUser: (
    id: number,
    data: { name?: string; notes?: string; is_guest?: boolean },
  ) => req<User>(`/users/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteUser: (id: number) => req<void>(`/users/${id}`, { method: "DELETE" }),

  brands: () => req<Brand[]>("/brands"),
  osLogos: () => req<Brand[]>("/os"),
  uploadLogo: async (kind: "brands" | "os", name: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`${BASE}/${kind}/${encodeURIComponent(name)}/logo`, {
      method: "POST",
      body: fd,
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json() as Promise<Brand>;
  },
  deleteLogo: (kind: "brands" | "os", name: string) =>
    req<void>(`/${kind}/${encodeURIComponent(name)}/logo`, { method: "DELETE" }),

  timeline: (days = 30) => req<Timeline>(`/stats/timeline?days=${days}`),
  byType: () => req<TypeCount[]>("/stats/by-type"),
  byBrand: () => req<BrandCount[]>("/stats/by-brand"),

  settings: () => req<AppSettings>("/settings"),
  updateSettings: (data: Partial<AppSettings> & {
    telegram_bot_token?: string;
    telegram_chat_id?: string;
    ntfy_token?: string;
    ntfy_password?: string;
    mqtt_password?: string;
    fingerbank_api_key?: string;
    metrics_token?: string;
    alert_policy?: Record<string, AlertRule>;
  }) => req<AppSettings>("/settings", { method: "PATCH", body: JSON.stringify(data) }),
  testTelegram: () => req<{ ok: boolean }>("/settings/telegram/test", { method: "POST" }),
  testNtfy: () => req<{ ok: boolean }>("/settings/ntfy/test", { method: "POST" }),
  purgeHistory: () =>
    req<AppSettings>("/settings/purge-history", { method: "POST" }),
  testDigest: () =>
    req<{ ok: boolean; summary: string[] }>("/settings/digest/test", { method: "POST" }),

  wan: (hours = 24) => req<WanStatus>(`/wan?hours=${hours}`),
  mergeSuggestions: () => req<MergeSuggestion[]>("/devices/merge-suggestions"),

  agents: () => req<AgentRow[]>("/agents"),
  createEnrolToken: (label?: string) =>
    req<EnrolToken>(`/agents/tokens${label ? `?label=${encodeURIComponent(label)}` : ""}`, {
      method: "POST",
    }),
  deleteAgent: (id: number) => req<void>(`/agents/${id}`, { method: "DELETE" }),

  testFingerbank: () =>
    req<FingerbankTest>("/settings/fingerbank/test", { method: "POST" }),

  // ── auth ──────────────────────────────────────────────────────────
  authStatus: () => req<AuthStatus>("/auth/status"),
  login: (username: string, password: string) =>
    req<Account>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  setup: (username: string, password: string) =>
    req<Account>("/auth/setup", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  logout: () => req<void>("/auth/logout", { method: "POST" }),
  updateProfile: (patch: {
    current: string;
    username?: string;
    new_password?: string;
  }) =>
    req<Account>("/auth/me", {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  accounts: () => req<Account[]>("/auth/accounts"),
  createAccount: (username: string, password: string, role: AccountRole) =>
    req<Account>("/auth/accounts", {
      method: "POST",
      body: JSON.stringify({ username, password, role }),
    }),
  updateAccount: (id: number, patch: { role?: AccountRole; password?: string }) =>
    req<Account>(`/auth/accounts/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  deleteAccount: (id: number) =>
    req<void>(`/auth/accounts/${id}`, { method: "DELETE" }),

  backupUrl: () => BASE + "/settings/backup",
  restoreBackup: async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(BASE + "/settings/restore", { method: "POST", body: fd });
    if (!res.ok) {
      throw new ApiError(
        `${res.status} — ${(await res.text()).slice(0, 200)}`,
        false,
        res.status,
      );
    }
    return res.json() as Promise<{ ok: boolean; restarting: boolean; uploads: number }>;
  },

  apiTokens: () => req<ApiToken[]>("/auth/tokens"),
  createApiToken: (name: string) =>
    req<ApiToken & { token: string }>("/auth/tokens", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  deleteApiToken: (id: number) =>
    req<void>(`/auth/tokens/${id}`, { method: "DELETE" }),
};
