import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ChangeEvent, type ReactNode } from "react";
import clsx from "clsx";
import { api } from "../api/client";
import type { AccountRole, AlertRule, HostTempPoint, HostTempSeries, SubnetCfg } from "../api/types";
import { AUTH_KEY, useAuth, useCanWrite, useIsAdmin } from "../auth/AuthProvider";
import { Badge, Button, Field, Redacted, SectionHeader, Toggle } from "../components/ui";
import {
  Bell,
  Envelope,
  Close,
  Globe,
  Image,
  LogIcon,
  PeopleIcon,
  Plug,
  Plus,
  Power,
  Radar,
  Send,
  DownloadIcon,
  Shield,
  ThermoIcon,
  Trash,
  UpdateIcon,
  Wave,
} from "../components/Glyph";
import { useToast } from "../components/Toaster";
import { useTheme, type ThemePref } from "../hooks/useTheme";
import { copyText } from "../lib/ports";
import { timeAgo } from "../lib/format";
import { useT, useLocale, type MessageKey } from "../i18n";
import { intlLocale, LOCALES, type Locale } from "../i18n/locale";

/** Alert-kind labels come from the backend (`k.label`, in English); prefer a
 * localised string keyed by the stable `k.key` when we have one. */
function alertLabel(t: (k: MessageKey) => string, key: string, fallback: string): string {
  const mk = `alert.${key}` as MessageKey;
  const out = t(mk);
  return out === mk ? fallback : out;
}

/** Config is split into categories navigated from a side list, so no single
 *  screen carries the whole surface at once. */
type SettingsCat =
  | "network"
  | "notifications"
  | "integrations"
  | "internet"
  | "history"
  | "update"
  | "agents"
  | "monitor"
  | "interface"
  | "account"
  | "accounts";

const SETTINGS_CATS: {
  k: SettingsCat;
  code: string;
  labelKey: MessageKey;
  Icon: (p: { size?: number; className?: string }) => JSX.Element;
  adminOnly?: boolean;
  writeOnly?: boolean;
}[] = [
  { k: "network", code: "01", labelKey: "settings.cat.network", Icon: Radar },
  { k: "notifications", code: "02", labelKey: "settings.cat.notifications", Icon: Bell },
  { k: "integrations", code: "03", labelKey: "settings.cat.integrations", Icon: Plug },
  { k: "internet", code: "04", labelKey: "settings.cat.internet", Icon: Globe },
  { k: "history", code: "05", labelKey: "settings.cat.history", Icon: LogIcon },
  { k: "update", code: "06", labelKey: "settings.cat.update", Icon: UpdateIcon },
  { k: "agents", code: "07", labelKey: "settings.cat.agents", Icon: Wave, writeOnly: true },
  { k: "monitor", code: "08", labelKey: "settings.cat.monitor", Icon: ThermoIcon },
  { k: "interface", code: "09", labelKey: "settings.cat.interface", Icon: Image },
  { k: "account", code: "10", labelKey: "settings.cat.account", Icon: Shield },
  { k: "accounts", code: "11", labelKey: "settings.cat.accounts", Icon: PeopleIcon, adminOnly: true },
];

/** Categories that edit the shared settings form and so need the Save bar. */
const FORM_CATS = new Set<SettingsCat>([
  "network",
  "notifications",
  "integrations",
  "internet",
  "history",
]);

const CAT_KEY = "cherubyte-settings-tab";

function readCat(isAdmin: boolean): SettingsCat {
  try {
    const s = localStorage.getItem(CAT_KEY) as SettingsCat | null;
    if (s && SETTINGS_CATS.some((c) => c.k === s && (!c.adminOnly || isAdmin))) return s;
  } catch {
    /* private mode */
  }
  return "network";
}

function SettingsNav({
  cat,
  setCat,
  isAdmin,
  canWrite,
}: {
  cat: SettingsCat;
  setCat: (c: SettingsCat) => void;
  isAdmin: boolean;
  canWrite: boolean;
}) {
  const t = useT();
  const items = SETTINGS_CATS.filter(
    (c) => (!c.adminOnly || isAdmin) && (!c.writeOnly || canWrite),
  );
  return (
    <nav className="panel flex gap-1 overflow-x-auto p-1.5 lg:sticky lg:top-4 lg:flex-col lg:gap-0.5 lg:self-start lg:overflow-visible lg:p-2">
      <span className="key hidden px-2 pb-1.5 pt-1 lg:block">{t("settings.sections")}</span>
      {items.map((c) => {
        const on = c.k === cat;
        return (
          <button
            key={c.k}
            onClick={() => setCat(c.k)}
            className={clsx(
              "group flex shrink-0 items-center gap-2.5 whitespace-nowrap rounded-lg px-3 py-2 text-left text-[12.5px] transition-colors",
              on ? "bg-surface-2 text-fg" : "text-fg-2 hover:bg-surface-2/60 hover:text-fg",
            )}
          >
            <c.Icon size={15} className={on ? "text-fg" : "text-fg-3 group-hover:text-fg-2"} />
            <span className={clsx(on ? "font-medium" : "font-normal")}>{t(c.labelKey)}</span>
          </button>
        );
      })}
    </nav>
  );
}

/** Settings ▸ Monitor: CPU/SoC temperature of the panel host and every agent
 *  host, on one chart each. The panel samples its own sensor every minute (see
 *  the scheduler); agents send theirs on every sweep. Read-only, so no Save bar. */
function MonitorSection() {
  const t = useT();
  const [hours, setHours] = useState(24);
  const q = useQuery({
    queryKey: ["host-metrics", hours],
    queryFn: () => api.hostMetrics(hours),
    refetchInterval: 60_000,
  });
  const series = q.data?.series ?? [];
  const ranges: [number, MessageKey][] = [
    [24, "settings.monitor.range.24h"],
    [168, "settings.monitor.range.7d"],
  ];

  return (
    <section className="panel mb-3 p-4">
      <SectionHeader
        title={t("settings.section.monitor")}
        sub={t("settings.monitor.sub")}
        actions={
          <div className="flex gap-0.5 rounded-lg bg-surface-2 p-0.5">
            {ranges.map(([h, k]) => (
              <button
                key={h}
                onClick={() => setHours(h)}
                className={clsx(
                  "rounded-md px-2.5 py-1 text-[11px] transition-colors",
                  hours === h ? "bg-bg text-fg" : "text-fg-3 hover:text-fg-2",
                )}
              >
                {t(k)}
              </button>
            ))}
          </div>
        }
      />

      {q.isLoading ? (
        <div className="space-y-3">
          {[0, 1].map((i) => (
            <div key={i} className="h-40 animate-pulse rounded-xl bg-surface-2" />
          ))}
        </div>
      ) : series.length === 0 ? (
        <p className="mono text-[12px] text-fg-3">{t("settings.monitor.empty")}</p>
      ) : (
        <div className="space-y-3">
          {series.map((s) => (
            <TempCard key={s.key} s={s} hours={hours} />
          ))}
        </div>
      )}
    </section>
  );
}

function TempCard({ s, hours }: { s: HostTempSeries; hours: number }) {
  const t = useT();
  const label = s.kind === "panel" ? t("settings.monitor.panel") : s.label;
  const hot = (s.max ?? 0) >= 85;
  const deg = (v: number | null, digits = 0) =>
    v === null ? "—" : t("settings.monitor.degrees", { n: v.toFixed(digits) });

  return (
    <div className="rounded-xl bg-surface-2 p-3.5">
      <div className="mb-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-display text-[13px] text-fg">{label}</span>
        <span
          className={clsx(
            "font-display text-[20px] leading-none tnum",
            hot ? "text-alert" : "text-fg",
          )}
        >
          {deg(s.current, 1)}
        </span>
        <span className="mono ml-auto text-[10.5px] text-fg-3">
          {t("settings.monitor.min")} {deg(s.min)} · {t("settings.monitor.avg")} {deg(s.avg)} ·{" "}
          {t("settings.monitor.max")} {deg(s.max)}
        </span>
      </div>
      {s.points.length >= 2 ? (
        <TempChart points={s.points} hours={hours} hot={hot} label={label} />
      ) : (
        <p className="mono py-6 text-center text-[11px] text-fg-3">
          {t("settings.monitor.empty")}
        </p>
      )}
    </div>
  );
}

/** A hand-rolled SVG line chart — same house style as the dashboard sparkline,
 *  scaled up with axes. Monochrome; the line only goes alert-red when the run
 *  is running hot. */
function TempChart({
  points,
  hours,
  hot,
  label,
}: {
  points: HostTempPoint[];
  hours: number;
  hot: boolean;
  label: string;
}) {
  const t = useT();
  const W = 640;
  const H = 150;
  const padL = 30;
  const padR = 6;
  const padT = 8;
  const padB = 18;

  const xs = points.map((p) => new Date(p.t).getTime());
  const cs = points.map((p) => p.c);
  const t0 = xs[0];
  const t1 = xs[xs.length - 1];

  const rawLo = Math.min(...cs);
  const rawHi = Math.max(...cs);
  const span = Math.max(8, rawHi - rawLo);
  const mid = (rawHi + rawLo) / 2;
  const lo = Math.floor(mid - span / 2 - 1);
  const hi = Math.ceil(mid + span / 2 + 1);

  const x = (ms: number) => padL + ((ms - t0) / Math.max(1, t1 - t0)) * (W - padL - padR);
  const y = (c: number) => padT + (1 - (c - lo) / (hi - lo)) * (H - padT - padB);

  const line = points
    .map((p, i) => `${i ? "L" : "M"}${x(xs[i]).toFixed(1)} ${y(p.c).toFixed(1)}`)
    .join("");
  const area = `${line}L${x(t1).toFixed(1)} ${(H - padB).toFixed(1)}L${x(t0).toFixed(1)} ${(H - padB).toFixed(1)}Z`;
  const stroke = hot ? "rgb(var(--alert))" : "rgb(var(--fg-2))";

  const yTicks = [hi, Math.round(mid), lo];
  const fmtTime = (ms: number) => {
    const d = new Date(ms);
    return hours <= 48
      ? d.toLocaleTimeString(intlLocale(), { hour: "2-digit", minute: "2-digit" })
      : d.toLocaleDateString(intlLocale(), { day: "2-digit", month: "2-digit" });
  };
  const xTicks = [0, 1, 2, 3].map((i) => t0 + ((t1 - t0) * i) / 3);
  const rangeLabel = hours <= 48 ? t("settings.monitor.range.24h") : t("settings.monitor.range.7d");

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-[150px] w-full"
      role="img"
      aria-label={t("settings.monitor.chartLabel", { label, range: rangeLabel })}
    >
      {yTicks.map((c, i) => (
        <g key={i}>
          <line
            x1={padL}
            x2={W - padR}
            y1={y(c)}
            y2={y(c)}
            stroke="rgb(var(--fg) / 0.08)"
            strokeWidth={1}
          />
          <text x={0} y={y(c) + 3} className="mono" fontSize={8} fill="rgb(var(--fg-3))">
            {c}°
          </text>
        </g>
      ))}
      {xTicks.map((ms, i) => (
        <text
          key={i}
          x={x(ms)}
          y={H - 4}
          textAnchor={i === 0 ? "start" : i === 3 ? "end" : "middle"}
          className="mono"
          fontSize={8}
          fill="rgb(var(--fg-3))"
        >
          {fmtTime(ms)}
        </text>
      ))}
      <path d={area} fill={stroke} opacity={0.08} />
      <path d={line} fill="none" stroke={stroke} strokeWidth={1.5} strokeLinejoin="round" />
    </svg>
  );
}

/** Per-browser interface preferences: language and theme. Client-only. */
function InterfaceSection() {
  const t = useT();
  const [locale, setLocale] = useLocale();
  const { pref, setPref } = useTheme();
  return (
    <section className="panel mb-3 p-4">
      <SectionHeader title={t("settings.cat.interface")} />
      <div className="space-y-4">
        <Field label={t("settings.iface.language")}>
          <select
            className="input"
            value={locale}
            onChange={(e) => setLocale(e.target.value as Locale)}
          >
            {(Object.keys(LOCALES) as Locale[]).map((l) => (
              <option key={l} value={l}>
                {LOCALES[l]}
              </option>
            ))}
          </select>
        </Field>
        <Field label={t("settings.iface.theme")}>
          <select
            className="input"
            value={pref}
            onChange={(e) => setPref(e.target.value as ThemePref)}
          >
            <option value="system">{t("settings.iface.theme.system")}</option>
            <option value="light">{t("settings.iface.theme.light")}</option>
            <option value="dark">{t("settings.iface.theme.dark")}</option>
          </select>
        </Field>
      </div>
    </section>
  );
}

export function Settings() {
  const qc = useQueryClient();
  const toast = useToast();
  const t = useT();
  const isAdmin = useIsAdmin();
  const canWrite = useCanWrite();
  const [cat, setCat] = useState<SettingsCat>(() => readCat(isAdmin));
  useEffect(() => {
    try {
      localStorage.setItem(CAT_KEY, cat);
    } catch {
      /* private mode */
    }
  }, [cat]);
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [form, setForm] = useState({
    scan_interval_seconds: 60,
    offline_after_seconds: 180,
    identify_interval_seconds: 900,
    subnets: [] as SubnetCfg[],
    retention_days: 90,
    telegram_enabled: false,
    public_base_url: "",
    dhcp_allowlist: "",
    risky_ports_ignore: "",
    quiet_hours_start: "",
    quiet_hours_end: "",
    agent_offline_after_seconds: 600,
    mqtt_enabled: false,
    mqtt_host: "",
    mqtt_port: 1883,
    mqtt_username: "",
    mqtt_password: "",
    mqtt_base_topic: "cherubyte",
    mqtt_discovery_prefix: "homeassistant",
    wan_enabled: true,
    wan_target: "1.1.1.1",
    wan_interval_seconds: 60,
    metrics_enabled: true,
    metrics_token: "",
    enable_snmp: false,
    snmp_community: "public",
    topology_enabled: false,
    weekly_summary_enabled: false,
    weekly_summary_weekday: 0,
    weekly_summary_hour: 9,
    telegram_bot_token: "",
    telegram_chat_id: "",
    ntfy_enabled: false,
    ntfy_server: "https://ntfy.sh",
    ntfy_topic: "",
    ntfy_token: "",
    ntfy_username: "",
    ntfy_password: "",
    ntfy_priority: 3,
    smtp_enabled: false,
    smtp_host: "",
    smtp_port: 587,
    smtp_security: "starttls",
    smtp_username: "",
    smtp_password: "",
    smtp_from: "",
    smtp_to: "",
    fingerbank_api_key: "",
  });
  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) =>
    setForm((s) => ({ ...s, [k]: v }));

  const [policy, setPolicy] = useState<Record<string, AlertRule>>({});

  useEffect(() => {
    if (settings.data) setPolicy(settings.data.alert_policy);
  }, [settings.data]);

  useEffect(() => {
    if (settings.data)
      setForm((s) => ({
        ...s,
        scan_interval_seconds: settings.data.scan_interval_seconds,
        offline_after_seconds: settings.data.offline_after_seconds,
        identify_interval_seconds: settings.data.identify_interval_seconds,
        subnets: settings.data.subnets.length
          ? settings.data.subnets
          : settings.data.subnet
            ? [{ cidr: settings.data.subnet, label: "" }]
            : [],
        retention_days: settings.data.retention_days,
        telegram_enabled: settings.data.telegram_enabled,
        public_base_url: settings.data.public_base_url,
        dhcp_allowlist: settings.data.dhcp_allowlist,
        risky_ports_ignore: settings.data.risky_ports_ignore,
        quiet_hours_start: settings.data.quiet_hours_start,
        quiet_hours_end: settings.data.quiet_hours_end,
        agent_offline_after_seconds: settings.data.agent_offline_after_seconds,
        mqtt_enabled: settings.data.mqtt_enabled,
        mqtt_host: settings.data.mqtt_host,
        mqtt_port: settings.data.mqtt_port,
        mqtt_username: settings.data.mqtt_username,
        mqtt_base_topic: settings.data.mqtt_base_topic,
        mqtt_discovery_prefix: settings.data.mqtt_discovery_prefix,
        wan_enabled: settings.data.wan_enabled,
        wan_target: settings.data.wan_target,
        wan_interval_seconds: settings.data.wan_interval_seconds,
        metrics_enabled: settings.data.metrics_enabled,
        enable_snmp: settings.data.enable_snmp,
        snmp_community: settings.data.snmp_community,
        topology_enabled: settings.data.topology_enabled,
        weekly_summary_enabled: settings.data.weekly_summary_enabled,
        weekly_summary_weekday: settings.data.weekly_summary_weekday,
        weekly_summary_hour: settings.data.weekly_summary_hour,
        telegram_chat_id: settings.data.telegram_chat_id ?? "",
        ntfy_enabled: settings.data.ntfy_enabled,
        ntfy_server: settings.data.ntfy_server,
        ntfy_topic: settings.data.ntfy_topic,
        ntfy_username: settings.data.ntfy_username,
        ntfy_priority: settings.data.ntfy_priority,
        smtp_enabled: settings.data.smtp_enabled,
        smtp_host: settings.data.smtp_host,
        smtp_port: settings.data.smtp_port,
        smtp_security: settings.data.smtp_security,
        smtp_username: settings.data.smtp_username,
        smtp_from: settings.data.smtp_from,
        smtp_to: settings.data.smtp_to,
      }));
  }, [settings.data]);

  const save = useMutation({
    mutationFn: () =>
      api.updateSettings({
        scan_interval_seconds: form.scan_interval_seconds,
        offline_after_seconds: form.offline_after_seconds,
        identify_interval_seconds: form.identify_interval_seconds,
        // the list is now the single source of truth — clear the legacy single value
        subnet: "",
        subnets: form.subnets
          .map((s) => ({ cidr: s.cidr.trim(), label: s.label.trim() }))
          .filter((s) => s.cidr),
        retention_days: form.retention_days,
        telegram_enabled: form.telegram_enabled,
        alert_policy: policy,
        quiet_hours_start: form.quiet_hours_start,
        quiet_hours_end: form.quiet_hours_end,
        agent_offline_after_seconds: form.agent_offline_after_seconds,
        public_base_url: form.public_base_url,
        dhcp_allowlist: form.dhcp_allowlist,
        risky_ports_ignore: form.risky_ports_ignore,
        mqtt_enabled: form.mqtt_enabled,
        mqtt_host: form.mqtt_host,
        mqtt_port: form.mqtt_port,
        mqtt_username: form.mqtt_username,
        mqtt_base_topic: form.mqtt_base_topic,
        mqtt_discovery_prefix: form.mqtt_discovery_prefix,
        ...(form.mqtt_password ? { mqtt_password: form.mqtt_password } : {}),
        wan_enabled: form.wan_enabled,
        wan_target: form.wan_target,
        wan_interval_seconds: form.wan_interval_seconds,
        metrics_enabled: form.metrics_enabled,
        enable_snmp: form.enable_snmp,
        snmp_community: form.snmp_community,
        topology_enabled: form.topology_enabled,
        ...(form.metrics_token ? { metrics_token: form.metrics_token } : {}),
        weekly_summary_enabled: form.weekly_summary_enabled,
        weekly_summary_weekday: form.weekly_summary_weekday,
        weekly_summary_hour: form.weekly_summary_hour,
        ...(form.telegram_bot_token ? { telegram_bot_token: form.telegram_bot_token } : {}),
        telegram_chat_id: form.telegram_chat_id,
        ntfy_enabled: form.ntfy_enabled,
        ntfy_server: form.ntfy_server,
        ntfy_topic: form.ntfy_topic,
        ntfy_username: form.ntfy_username,
        ntfy_priority: form.ntfy_priority,
        ...(form.ntfy_token ? { ntfy_token: form.ntfy_token } : {}),
        ...(form.ntfy_password ? { ntfy_password: form.ntfy_password } : {}),
        smtp_enabled: form.smtp_enabled,
        smtp_host: form.smtp_host,
        smtp_port: form.smtp_port,
        smtp_security: form.smtp_security,
        smtp_username: form.smtp_username,
        smtp_from: form.smtp_from,
        smtp_to: form.smtp_to,
        ...(form.smtp_password ? { smtp_password: form.smtp_password } : {}),
        ...(form.fingerbank_api_key ? { fingerbank_api_key: form.fingerbank_api_key } : {}),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      toast({ tone: "success", title: "config.saved" });
    },
  });
  const test = useMutation({
    mutationFn: api.testTelegram,
    onSuccess: (r) =>
      toast(
        r.ok
          ? { tone: "success", title: "telegram.sent" }
          : { tone: "error", title: "telegram.failed", desc: "toast.telegramFailedDesc" },
      ),
  });
  const purge = useMutation({
    mutationFn: api.purgeHistory,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      toast({ tone: "success", title: "history.purged" });
    },
  });
  const testDigest = useMutation({
    mutationFn: api.testDigest,
    onSuccess: (r) =>
      toast(
        r.ok
          ? { tone: "success", title: "digest.sent" }
          : { tone: "error", title: "digest.failed", desc: "toast.digestFailedDesc" },
      ),
  });
  const testNtfy = useMutation({
    mutationFn: api.testNtfy,
    onSuccess: (r) =>
      toast(
        r.ok
          ? { tone: "success", title: "ntfy.sent" }
          : { tone: "error", title: "ntfy.failed", desc: "toast.ntfyFailedDesc" },
      ),
  });
  const testEmail = useMutation({
    mutationFn: api.testEmail,
    onSuccess: (r) =>
      toast(
        r.ok
          ? { tone: "success", title: "email.sent" }
          : { tone: "error", title: "email.failed", desc: "toast.emailFailedDesc" },
      ),
  });
  const testFb = useMutation({
    mutationFn: async () => {
      // Testing an unsaved key the user just typed used to silently test
      // whatever was already on disk instead — save it first so Test always
      // checks what's on screen.
      if (form.fingerbank_api_key) {
        await api.updateSettings({ fingerbank_api_key: form.fingerbank_api_key });
        qc.invalidateQueries({ queryKey: ["settings"] });
      }
      return api.testFingerbank();
    },
    onSuccess: (r) => {
      if (r.status === "ok") {
        toast({
          tone: "success",
          title: "settings.fingerbank.result.ok",
          desc: [r.name, r.os, r.score != null ? `${r.score}%` : null]
            .filter(Boolean)
            .join(" · "),
        });
      } else {
        toast({
          tone: "error",
          title: `settings.fingerbank.result.${r.status}` as MessageKey,
          desc: r.detail,
        });
      }
    },
  });
  const d = settings.data;
  const panelOrigin = typeof window === "undefined" ? "" : window.location.origin;

  return (
    <div className="grid max-w-5xl gap-5 lg:grid-cols-[220px_1fr] lg:items-start">
      <SettingsNav cat={cat} setCat={setCat} isAdmin={isAdmin} canWrite={canWrite} />

      <div className="min-w-0">
      {cat === "agents" && canWrite && <AgentsSection />}
      {cat === "update" && <UpdateSection isAdmin={isAdmin} />}
      {cat === "monitor" && <MonitorSection />}
      {cat === "interface" && <InterfaceSection />}
      {cat === "account" && <AccountCard />}
      {cat === "accounts" && isAdmin && (
        <>
          <AccountsCard />
          <ApiTokensCard />
        </>
      )}

      {/* ── Network & scanning ─────────────────────────────────────── */}
      <div hidden={cat !== "network"}>
      <section className="panel mb-3 p-4">
        <SectionHeader title={t("settings.section.network")} />
        <div className="space-y-4">
          <div>
            <span className="label mb-1.5 block">{t("settings.subnets")}</span>
            <div className="space-y-2">
              {form.subnets.map((s, i) => (
                <div key={i} className="flex gap-2">
                  <input
                    className="input mono flex-1"
                    placeholder={t("settings.subnet.cidr")}
                    value={s.cidr}
                    onChange={(e) =>
                      setForm((f) => ({
                        ...f,
                        subnets: f.subnets.map((x, j) =>
                          j === i ? { ...x, cidr: e.target.value } : x,
                        ),
                      }))
                    }
                  />
                  <input
                    className="input flex-1"
                    placeholder={t("settings.subnet.label")}
                    value={s.label}
                    onChange={(e) =>
                      setForm((f) => ({
                        ...f,
                        subnets: f.subnets.map((x, j) =>
                          j === i ? { ...x, label: e.target.value } : x,
                        ),
                      }))
                    }
                  />
                  <button
                    type="button"
                    onClick={() =>
                      setForm((f) => ({ ...f, subnets: f.subnets.filter((_, j) => j !== i) }))
                    }
                    className="shrink-0 px-2 text-fg-3 hover:text-alert"
                    title={t("common.remove")}
                  >
                    <Trash size={13} />
                  </button>
                </div>
              ))}
              <Button
                type="button"
                variant="secondary"
                size="sm"
                icon={<Plus size={12} />}
                onClick={() =>
                  setForm((f) => ({ ...f, subnets: [...f.subnets, { cidr: "", label: "" }] }))
                }
              >
                {t("settings.subnet.add")}
              </Button>
            </div>
            <span className="mono mt-1 block text-[11px] text-fg-3">{t("settings.subnetsHint")}</span>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label={t("settings.sweepInterval")}>
              <input
                type="number"
                min={15}
                className="input mono"
                value={form.scan_interval_seconds}
                onChange={(e) => set("scan_interval_seconds", +e.target.value)}
              />
            </Field>
            <Field label={t("settings.offlineAfter")}>
              <input
                type="number"
                min={30}
                className="input mono"
                value={form.offline_after_seconds}
                onChange={(e) => set("offline_after_seconds", +e.target.value)}
              />
            </Field>
            <Field label={t("settings.reidentifyAfter")} hint={t("settings.reidentifyHint")}>
              <input
                type="number"
                min={0}
                className="input mono"
                value={form.identify_interval_seconds}
                onChange={(e) => set("identify_interval_seconds", +e.target.value)}
              />
            </Field>
          </div>
        </div>
      </section>

      </div>

      {/* ── History ────────────────────────────────────────────────── */}
      <div hidden={cat !== "history"}>
      <section className="panel mb-3 p-4">
        <SectionHeader title={t("settings.section.history")} />
        <div className="flex flex-wrap items-end gap-4">
          <Field label={t("settings.retentionDays")} hint={t("settings.retentionHint")} className="w-40">
            <input
              type="number"
              min={0}
              className="input mono"
              value={form.retention_days}
              onChange={(e) => set("retention_days", +e.target.value)}
            />
          </Field>
          <div className="flex flex-1 flex-wrap items-center justify-between gap-3">
            <span className="mono text-[11px] text-fg-3">
              {t("settings.storedCounts", {
                events: (d?.stored_events ?? 0).toLocaleString(intlLocale()),
                connections: (d?.stored_connections ?? 0).toLocaleString(intlLocale()),
              })}
            </span>
            <div className="flex items-center gap-2">
              <a className="btn btn-secondary btn-sm" href={api.devicesCsvUrl()}>
                {t("settings.exportCsv")}
              </a>
              <Button
                variant="secondary"
                size="sm"
                icon={<Trash size={12} />}
                loading={purge.isPending}
                onClick={() => purge.mutate()}
              >
                {t("settings.purgeNow")}
              </Button>
            </div>
          </div>
        </div>
      </section>

      {isAdmin && <BackupCard />}

      </div>

      {/* ── Notifications + Alerts ─────────────────────────────────── */}
      <div hidden={cat !== "notifications"}>
      <section className="panel mb-3 p-4">
        <SectionHeader title={t("settings.section.notifications")} />
        <div className="space-y-2">
          <Channel
            icon={<Send size={14} />}
            name="Telegram"
            enabled={form.telegram_enabled}
            configured={!!d?.telegram_configured}
            onToggle={(v) => set("telegram_enabled", v)}
          >
            <Field label={t("settings.telegram.token")}>
              <input
                className="input mono"
                type="password"
                placeholder={d?.telegram_token_saved ? t("settings.telegram.saved") : "123456:ABC-DEF"}
                value={form.telegram_bot_token}
                onChange={(e) => set("telegram_bot_token", e.target.value)}
              />
            </Field>
            <Field label={t("settings.telegram.chatId")}>
              <input
                className="input mono"
                value={form.telegram_chat_id}
                onChange={(e) => set("telegram_chat_id", e.target.value)}
              />
            </Field>
            <Button
              variant="secondary"
              size="sm"
              icon={<Send size={12} />}
              disabled={!d?.telegram_configured}
              loading={test.isPending}
              onClick={() => test.mutate()}
            >
              {t("settings.testMessage")}
            </Button>
          </Channel>

          <Channel
            icon={<Bell size={14} />}
            name="ntfy"
            enabled={form.ntfy_enabled}
            configured={!!d?.ntfy_configured}
            onToggle={(v) => set("ntfy_enabled", v)}
          >
            <Field label={t("settings.ntfy.server")} hint={t("settings.ntfy.serverHint")}>
              <input
                className="input mono"
                placeholder="https://ntfy.sh"
                value={form.ntfy_server}
                onChange={(e) => set("ntfy_server", e.target.value)}
              />
            </Field>
            <Field label={t("settings.ntfy.topic")} hint={t("settings.ntfy.topicHint")}>
              <input
                className="input mono"
                placeholder="cherubyte-a7f3k2"
                value={form.ntfy_topic}
                onChange={(e) => set("ntfy_topic", e.target.value)}
              />
            </Field>
            <Field label={t("settings.ntfy.priority")}>
              <select
                className="input mono"
                value={form.ntfy_priority}
                onChange={(e) => set("ntfy_priority", +e.target.value)}
              >
                <option value={1}>{t("settings.ntfy.prio1")}</option>
                <option value={2}>{t("settings.ntfy.prio2")}</option>
                <option value={3}>{t("settings.ntfy.prio3")}</option>
                <option value={4}>{t("settings.ntfy.prio4")}</option>
                <option value={5}>{t("settings.ntfy.prio5")}</option>
              </select>
            </Field>
            <Field label={t("settings.ntfy.token")} hint={t("settings.ntfy.tokenHint")}>
              <input
                className="input mono"
                type="password"
                placeholder={d?.ntfy_auth_configured ? t("settings.telegram.saved") : "tk_..."}
                value={form.ntfy_token}
                onChange={(e) => set("ntfy_token", e.target.value)}
              />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={t("settings.ntfy.username")} hint={t("settings.ntfy.usernameHint")}>
                <input
                  className="input mono"
                  autoComplete="off"
                  value={form.ntfy_username}
                  onChange={(e) => set("ntfy_username", e.target.value)}
                />
              </Field>
              <Field label={t("settings.ntfy.password")}>
                <input
                  className="input mono"
                  type="password"
                  autoComplete="new-password"
                  placeholder={d?.ntfy_auth_configured ? t("settings.telegram.saved") : ""}
                  value={form.ntfy_password}
                  onChange={(e) => set("ntfy_password", e.target.value)}
                />
              </Field>
            </div>
            <Button
              variant="secondary"
              size="sm"
              icon={<Send size={12} />}
              disabled={!d?.ntfy_configured}
              loading={testNtfy.isPending}
              onClick={() => testNtfy.mutate()}
            >
              {t("settings.testMessage")}
            </Button>
          </Channel>

          <Channel
            icon={<Envelope size={14} />}
            name={t("settings.email.name")}
            enabled={form.smtp_enabled}
            configured={!!d?.smtp_configured}
            onToggle={(v) => set("smtp_enabled", v)}
          >
            <div className="grid gap-4 sm:grid-cols-[1fr_120px]">
              <Field label={t("settings.email.host")} hint={t("settings.email.hostHint")}>
                <input
                  className="input mono"
                  placeholder="smtp.gmail.com"
                  value={form.smtp_host}
                  onChange={(e) => set("smtp_host", e.target.value)}
                />
              </Field>
              <Field label={t("settings.email.port")}>
                <input
                  type="number"
                  min={1}
                  max={65535}
                  className="input mono"
                  value={form.smtp_port}
                  onChange={(e) => set("smtp_port", +e.target.value)}
                />
              </Field>
            </div>
            <Field label={t("settings.email.security")}>
              <select
                className="input mono"
                value={form.smtp_security}
                onChange={(e) => set("smtp_security", e.target.value)}
              >
                <option value="starttls">STARTTLS (587)</option>
                <option value="ssl">SSL/TLS (465)</option>
                <option value="none">{t("settings.email.securityNone")}</option>
              </select>
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={t("settings.email.username")} hint={t("settings.email.usernameHint")}>
                <input
                  className="input mono"
                  autoComplete="off"
                  value={form.smtp_username}
                  onChange={(e) => set("smtp_username", e.target.value)}
                />
              </Field>
              <Field label={t("settings.email.password")}>
                <input
                  className="input mono"
                  type="password"
                  autoComplete="new-password"
                  placeholder={d?.smtp_auth_configured ? t("settings.telegram.saved") : ""}
                  value={form.smtp_password}
                  onChange={(e) => set("smtp_password", e.target.value)}
                />
              </Field>
            </div>
            <Field label={t("settings.email.from")} hint={t("settings.email.fromHint")}>
              <input
                className="input mono"
                placeholder="cherubyte@example.com"
                value={form.smtp_from}
                onChange={(e) => set("smtp_from", e.target.value)}
              />
            </Field>
            <Field label={t("settings.email.to")} hint={t("settings.email.toHint")}>
              <input
                className="input mono"
                placeholder="me@example.com, you@example.com"
                value={form.smtp_to}
                onChange={(e) => set("smtp_to", e.target.value)}
              />
            </Field>
            <Button
              variant="secondary"
              size="sm"
              icon={<Send size={12} />}
              disabled={!d?.smtp_configured}
              loading={testEmail.isPending}
              onClick={() => testEmail.mutate()}
            >
              {t("settings.testMessage")}
            </Button>
          </Channel>
        </div>
      </section>

      {/* ── Alerts ────────────────────────────────────────────────── */}
      <section className="panel mb-3 p-4">
        <SectionHeader title={t("settings.section.alerts")} sub={t("settings.alerts.sub")} />
        <div className="space-y-3">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[420px] text-left">
              <thead>
                <tr className="label border-b border-fg/10 text-fg-3">
                  <th className="pb-2 font-normal">{t("settings.alerts.col.event")}</th>
                  <th className="pb-2 font-normal">{t("settings.alerts.col.on")}</th>
                  <th className="pb-2 font-normal">Telegram</th>
                  <th className="pb-2 font-normal">ntfy</th>
                  <th className="pb-2 font-normal">{t("settings.email.name")}</th>
                </tr>
              </thead>
              <tbody>
                {(d?.alert_kinds ?? []).map((k) => {
                  const label = alertLabel(t, k.key, k.label);
                  const rule = policy[k.key] ?? { enabled: true, channels: [] };
                  const setRule = (patch: Partial<AlertRule>) =>
                    setPolicy((p) => ({ ...p, [k.key]: { ...rule, ...patch } }));
                  const toggleChannel = (name: string) =>
                    setRule({
                      channels: rule.channels.includes(name)
                        ? rule.channels.filter((c) => c !== name)
                        : [...rule.channels, name],
                    });
                  return (
                    <tr key={k.key} className="border-b border-edge/60 last:border-0">
                      <td className="py-2 pr-3">
                        {label}
                        {k.urgent && (
                          <span className="mono ml-2 text-[10px] text-alert">
                            {t("settings.alerts.ignoresQuiet")}
                          </span>
                        )}
                      </td>
                      <td className="py-2 pr-3">
                        <Toggle
                          label={label}
                          checked={rule.enabled}
                          onChange={(v) => setRule({ enabled: v })}
                        />
                      </td>
                      {["telegram", "ntfy", "email"].map((name) => (
                        <td key={name} className="py-2 pr-3">
                          <input
                            type="checkbox"
                            aria-label={`${label} · ${name}`}
                            checked={rule.channels.includes(name)}
                            disabled={!rule.enabled}
                            onChange={() => toggleChannel(name)}
                          />
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label={t("settings.alerts.quietFrom")} hint={t("settings.alerts.quietFromHint")}>
              <input
                className="input mono"
                placeholder="23:00"
                value={form.quiet_hours_start}
                onChange={(e) => set("quiet_hours_start", e.target.value)}
              />
            </Field>
            <Field label={t("settings.alerts.quietUntil")}>
              <input
                className="input mono"
                placeholder="07:30"
                value={form.quiet_hours_end}
                onChange={(e) => set("quiet_hours_end", e.target.value)}
              />
            </Field>
            <Field label={t("settings.alerts.publicUrl")} hint={t("settings.alerts.publicUrlHint")}>
              <input
                className="input mono"
                placeholder="http://192.168.1.9:1001"
                value={form.public_base_url}
                onChange={(e) => set("public_base_url", e.target.value)}
              />
            </Field>
            <Field
              label={t("settings.alerts.agentSilent")}
              hint={t("settings.alerts.agentSilentHint")}
              className="sm:col-span-3"
            >
              <input
                type="number"
                min={0}
                step={60}
                className="input mono w-40"
                value={form.agent_offline_after_seconds}
                onChange={(e) => set("agent_offline_after_seconds", +e.target.value)}
              />
            </Field>
            <Field
              label={t("settings.alerts.dhcpAllow")}
              hint={t("settings.alerts.dhcpAllowHint")}
              className="sm:col-span-3"
            >
              <input
                className="input mono"
                placeholder="192.168.1.1, 192.168.1.2"
                value={form.dhcp_allowlist}
                onChange={(e) => set("dhcp_allowlist", e.target.value)}
              />
            </Field>
            <Field
              label={t("settings.alerts.riskyIgnore")}
              hint={t("settings.alerts.riskyIgnoreHint")}
              className="sm:col-span-3"
            >
              <input
                className="input mono"
                placeholder="445, 3389"
                value={form.risky_ports_ignore}
                onChange={(e) => set("risky_ports_ignore", e.target.value)}
              />
            </Field>
          </div>
        </div>
      </section>

      </div>

      {/* ── Integrations: Home Assistant · MQTT + Fingerbank ───────── */}
      <div hidden={cat !== "integrations"}>
      <section className="panel mb-3 p-4">
        <SectionHeader
          title={t("settings.section.mqtt")}
          actions={
            <div className="flex items-center gap-2">
              <Badge tone={d?.mqtt_enabled && d?.mqtt_host ? "signal" : "neutral"}>
                {d?.mqtt_enabled && d?.mqtt_host ? t("settings.active") : t("settings.inactive")}
              </Badge>
              <Toggle
                label={t("settings.mqtt.enable")}
                checked={form.mqtt_enabled}
                onChange={(v) => set("mqtt_enabled", v)}
              />
            </div>
          }
        />
        {form.mqtt_enabled && (
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label={t("settings.mqtt.broker")} className="sm:col-span-2">
                <input
                  className="input mono"
                  placeholder="192.168.1.10"
                  value={form.mqtt_host}
                  onChange={(e) => set("mqtt_host", e.target.value)}
                />
              </Field>
              <Field label={t("settings.mqtt.port")}>
                <input
                  type="number"
                  className="input mono"
                  value={form.mqtt_port}
                  onChange={(e) => set("mqtt_port", +e.target.value)}
                />
              </Field>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={t("settings.ntfy.username")}>
                <input
                  className="input mono"
                  autoComplete="off"
                  value={form.mqtt_username}
                  onChange={(e) => set("mqtt_username", e.target.value)}
                />
              </Field>
              <Field label={t("settings.ntfy.password")}>
                <input
                  className="input mono"
                  type="password"
                  autoComplete="new-password"
                  placeholder={d?.mqtt_auth_configured ? t("settings.telegram.saved") : ""}
                  value={form.mqtt_password}
                  onChange={(e) => set("mqtt_password", e.target.value)}
                />
              </Field>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={t("settings.mqtt.baseTopic")}>
                <input
                  className="input mono"
                  value={form.mqtt_base_topic}
                  onChange={(e) => set("mqtt_base_topic", e.target.value)}
                />
              </Field>
              <Field label={t("settings.mqtt.discoveryPrefix")} hint={t("settings.mqtt.discoveryHint")}>
                <input
                  className="input mono"
                  value={form.mqtt_discovery_prefix}
                  onChange={(e) => set("mqtt_discovery_prefix", e.target.value)}
                />
              </Field>
            </div>
          </div>
        )}
      </section>

      </div>

      {/* ── Internet & digest ─────────────────────────────────────── */}
      <div hidden={cat !== "internet"}>
      <section className="panel mb-3 p-4">
        <SectionHeader
          title={t("settings.section.internet")}
          actions={
            <Toggle
              label={t("settings.wan.enable")}
              checked={form.wan_enabled}
              onChange={(v) => set("wan_enabled", v)}
            />
          }
        />
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("settings.wan.target")}>
              <input
                className="input mono"
                placeholder="1.1.1.1"
                value={form.wan_target}
                onChange={(e) => set("wan_target", e.target.value)}
              />
            </Field>
            <Field label={t("settings.wan.interval")}>
              <input
                type="number"
                min={30}
                className="input mono"
                value={form.wan_interval_seconds}
                onChange={(e) => set("wan_interval_seconds", +e.target.value)}
              />
            </Field>
          </div>
          <div className="flex items-center justify-between border-t border-fg/10 pt-3">
            <span className="label text-fg-3">{t("settings.digest.title")}</span>
            <Toggle
              label={t("settings.digest.title")}
              checked={form.weekly_summary_enabled}
              onChange={(v) => set("weekly_summary_enabled", v)}
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("settings.digest.day")}>
              <select
                className="input mono"
                value={form.weekly_summary_weekday}
                onChange={(e) => set("weekly_summary_weekday", +e.target.value)}
              >
                {t("settings.digest.days").split(",").map((label, i) => (
                  <option key={i} value={i}>{label}</option>
                ))}
              </select>
            </Field>
            <Field label={t("settings.digest.hour")}>
              <input
                type="number"
                min={0}
                max={23}
                className="input mono"
                value={form.weekly_summary_hour}
                onChange={(e) => set("weekly_summary_hour", +e.target.value)}
              />
            </Field>
          </div>
          <Button
            variant="secondary"
            size="sm"
            icon={<Send size={12} />}
            loading={testDigest.isPending}
            onClick={() => testDigest.mutate()}
          >
            {t("settings.digest.sendNow")}
          </Button>
        </div>
      </section>

      </div>

      {/* ── Device identification · Fingerbank ─────────────────────── */}
      <div hidden={cat !== "integrations"}>
      <section className="panel mb-3 p-4">
        <SectionHeader
          title={t("settings.section.fingerbank")}
          actions={<Badge tone="neutral">{t("settings.fingerbank.count", { n: d?.dhcp_fingerprints ?? 0 })}</Badge>}
        />
        <div className="space-y-3">
          <Field label={t("settings.fingerbank.key")} hint={t("settings.fingerbank.keyHint")}>
            <input
              className="input mono"
              type="password"
              placeholder={d?.fingerbank_configured ? t("settings.telegram.saved") : t("settings.fingerbank.keyPlaceholder")}
              value={form.fingerbank_api_key}
              onChange={(e) => set("fingerbank_api_key", e.target.value)}
            />
          </Field>
          <Button
            variant="secondary"
            size="sm"
            icon={<Send size={12} />}
            disabled={!d?.fingerbank_configured && !form.fingerbank_api_key}
            loading={testFb.isPending}
            onClick={() => testFb.mutate()}
          >
            {t("settings.fingerbank.test")}
          </Button>
          <p className="mono text-[11px] text-fg-3">{t("settings.fingerbank.testHint")}</p>
        </div>
      </section>
      </div>

      {/* ── SNMP · topology ───────────────────────────────────────── */}
      <div hidden={cat !== "integrations"}>
      <section className="panel mb-3 p-4">
        <SectionHeader
          title={t("settings.section.snmp")}
          sub={t("settings.snmp.sub")}
          actions={
            <Toggle
              label={t("settings.snmp.enable")}
              checked={form.enable_snmp}
              onChange={(v) => set("enable_snmp", v)}
            />
          }
        />
        {form.enable_snmp && (
          <Field label={t("settings.snmp.community")} hint={t("settings.snmp.communityHint")}>
            <input
              className="input mono"
              placeholder="public"
              value={form.snmp_community}
              onChange={(e) => set("snmp_community", e.target.value)}
            />
          </Field>
        )}
        <div className="mt-4 flex items-center justify-between rounded-lg bg-surface-2 px-3.5 py-3">
          <div>
            <p className="text-[13px] text-fg">{t("settings.topology.enable")}</p>
            <p className="text-[11.5px] text-fg-3">{t("settings.topology.enableHint")}</p>
          </div>
          <Toggle checked={form.topology_enabled} onChange={(v) => set("topology_enabled", v)} />
        </div>
      </section>
      </div>

      {/* ── Prometheus metrics ────────────────────────────────────── */}
      <div hidden={cat !== "integrations"}>
      <section className="panel mb-3 p-4">
        <SectionHeader
          title={t("settings.section.metrics")}
          actions={
            <Toggle
              label={t("settings.metrics.enable")}
              checked={form.metrics_enabled}
              onChange={(v) => set("metrics_enabled", v)}
            />
          }
        />
        {form.metrics_enabled && (
          <div className="space-y-3">
            <Field label={t("settings.metrics.url")} hint={t("settings.metrics.urlHint")}>
              <div className="flex gap-2">
                <input
                  className="input mono"
                  readOnly
                  value={`${panelOrigin}${d?.metrics_path ?? "/api/metrics"}`}
                />
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => copyText(`${panelOrigin}${d?.metrics_path ?? "/api/metrics"}`)}
                >
                  {t("agents.token.copy")}
                </Button>
              </div>
            </Field>
            <Field label={t("settings.metrics.token")} hint={t("settings.metrics.tokenHint")}>
              <input
                className="input mono"
                type="password"
                autoComplete="new-password"
                placeholder={d?.metrics_token_set ? t("settings.telegram.saved") : t("settings.metrics.tokenPlaceholder")}
                value={form.metrics_token}
                onChange={(e) => set("metrics_token", e.target.value)}
              />
            </Field>
          </div>
        )}
      </section>
      </div>

      {canWrite && FORM_CATS.has(cat) && (
        <div className="sticky bottom-0 -mx-1 mt-3 rounded-t-xl bg-bg/80 px-1 py-3 backdrop-blur-md">
          <Button variant="primary" loading={save.isPending} onClick={() => save.mutate()}>
            {t("settings.save")}
          </Button>
        </div>
      )}
      </div>
    </div>
  );
}

/** Enrolling and watching the agents that feed this panel.
 *
 *  Lives in Config rather than the sidebar: the nav already carries six items
 *  and a seventh crowds the mobile bar, while enrolling an agent is something
 *  you do once per network.
 */
function AgentsSection() {
  const t = useT();
  const qc = useQueryClient();
  const toast = useToast();
  const [token, setToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const agents = useQuery({
    queryKey: ["agents"],
    queryFn: api.agents,
    refetchInterval: 30_000,
  });
  const release = useQuery({
    queryKey: ["agent-release"],
    queryFn: api.agentRelease,
    staleTime: 300_000,
  });
  const mint = useMutation({
    mutationFn: () => api.createEnrolToken(),
    onSuccess: (r) => {
      setToken(r.token);
      setCopied(false);
    },
  });
  const revoke = useMutation({
    mutationFn: (id: number) => api.deleteAgent(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["agents"] });
      toast({ tone: "success", title: t("agents.revoked") });
    },
  });

  const rows = agents.data ?? [];
  const panelUrl = typeof window === "undefined" ? "" : window.location.origin;

  return (
    <section className="panel mb-3 break-inside-avoid p-4 lg:[column-span:all]">
      <SectionHeader
        title={t("agents.title")}
        sub={t("agents.sub")}
        actions={
          <Button
            variant="secondary"
            size="sm"
            icon={<Plus size={12} />}
            loading={mint.isPending}
            onClick={() => mint.mutate()}
          >
            {t("agents.enrol")}
          </Button>
        }
      />

      {token && (
        <div className="mb-4 rounded-xl bg-surface-2 p-4">
          <div className="label mb-1.5 text-fg-2">{t("agents.token.title")}</div>
          <div className="flex flex-wrap items-center gap-2">
            <code className="mono flex-1 break-all text-[12px]">{token}</code>
            <Button
              variant="secondary"
              size="sm"
              onClick={() =>
                copyText(token).then((ok) => {
                  setCopied(ok);
                  if (!ok) toast({ tone: "error", title: t("agents.token.copy") });
                })
              }
            >
              {copied ? t("agents.token.copied") : t("agents.token.copy")}
            </Button>
          </div>
          <p className="mono mt-2 text-[11px] text-fg-3">
            {t("agents.token.hint", { hours: 24 })}
          </p>
          <div className="mt-3 space-y-3">
            {/* Docker — one command, nothing to download */}
            <div>
              <span className="label text-fg-3">{t("agents.install.docker")}</span>
              <pre className="mono mt-1 overflow-x-auto rounded-lg bg-surface p-2.5 text-[11px] text-fg-2">
{`docker run -d --name cherubyte-agent --network host \\
  --cap-add NET_RAW --cap-add NET_ADMIN \\
  -v cherubyte-agent:/var/lib/cherubyte-agent \\
  -e CHERUBYTE_AGENT_PANEL_URL=${panelUrl} \\
  -e CHERUBYTE_AGENT_ENROL_TOKEN=${token} \\
  ${release.data?.docker_image ?? "ghcr.io/cherubyte/cherubyte-agent:latest"}`}
              </pre>
            </div>

            {/* Native binary — served by this panel */}
            {release.data && !release.data.error && release.data.platforms.length > 0 && (
              <div>
                <span className="label text-fg-3">
                  {t("agents.install.native")}
                  {release.data.tag && (
                    <span className="mono ml-1.5 normal-case text-fg-3">{release.data.tag}</span>
                  )}
                </span>
                <div className="mt-1.5 flex flex-wrap gap-2">
                  {release.data.platforms.map((p) => (
                    <a
                      key={p}
                      href={api.agentDownloadUrl(p)}
                      className="btn btn-secondary btn-sm"
                    >
                      <DownloadIcon size={12} />
                      {t(`agents.dl.${p}` as MessageKey)}
                    </a>
                  ))}
                </div>
                {release.data.platforms.map((p) => (
                  <pre
                    key={p}
                    className="mono mt-2 overflow-x-auto rounded-lg bg-surface p-2.5 text-[11px] text-fg-2"
                  >
{p === "windows"
  ? `# ${t("agents.install.windows")}  (elevated PowerShell)
curl.exe -fsSL ${panelUrl}/api/agents/download/windows -o cherubyte-agent.exe
curl.exe -fsSL ${panelUrl}/api/agents/installer/windows -o install.ps1
.\\install.ps1 -PanelUrl ${panelUrl} -EnrolToken ${token} -ExePath .\\cherubyte-agent.exe`
  : `# ${t(p === "macos" ? "agents.install.macos" : "agents.install.linux")}
curl -fsSL ${panelUrl}/api/agents/download/${p} -o cherubyte-agent && chmod +x cherubyte-agent
curl -fsSL ${panelUrl}/api/agents/installer/${p} | sudo bash -s -- \\
  --panel ${panelUrl} --token ${token} --binary ./cherubyte-agent`}
                  </pre>
                ))}
                <p className="mono mt-1.5 text-[10.5px] text-fg-3">{t("agents.native.hint")}</p>
              </div>
            )}

            {release.data?.error && (
              <p className="mono text-[11px] text-fg-3">
                {t("agents.native.unavailable", { err: release.data.error })}
              </p>
            )}

            {/* From source */}
            <div>
              <span className="label text-fg-3">{t("agents.install.source")}</span>
              <pre className="mono mt-1 overflow-x-auto rounded-lg bg-surface p-2.5 text-[11px] text-fg-2">
{`git clone ${release.data?.repo_url ?? "https://github.com/Cherubyte/cherubyte-agent"}`}
              </pre>
            </div>
          </div>
        </div>
      )}

      {rows.length === 0 ? (
        <p className="mono text-[12px] text-fg-3">{t("agents.none")}</p>
      ) : (
        <div className="space-y-2">
          {rows.map((a) => (
            <div
              key={a.id}
              className="flex flex-wrap items-center justify-between gap-3 border-b border-edge/60 pb-2 last:border-0 last:pb-0"
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{a.name}</span>
                  <Badge tone={a.last_healthy ? "signal" : "alert"}>
                    {a.last_healthy ? t("agents.healthy") : t("agents.degraded")}
                  </Badge>
                  {a.version && (
                    <span className="mono text-[11px] text-fg-3">v{a.version}</span>
                  )}
                </div>
                <div className="mono mt-0.5 text-[11px] text-fg-3">
                  {a.last_seen
                    ? `${t("agents.lastSeen")} ${timeAgo(a.last_seen)} · ${t("agents.hosts", { n: a.last_hosts })}`
                    : t("agents.never")}
                  {a.subnets.length > 0 && ` · ${a.subnets.join(", ")}`}
                </div>
                {a.public_ip && (
                  <div className="mt-0.5 flex items-center gap-1.5">
                    <span className="mono text-[11px] text-fg-3">{t("dash.wan.ip")}</span>
                    <Redacted value={a.public_ip} className="text-[11px]" />
                  </div>
                )}
              </div>
              <Button
                variant="secondary"
                size="sm"
                icon={<Trash size={12} />}
                loading={revoke.isPending}
                onClick={() => {
                  if (window.confirm(t("agents.revoke.confirm"))) revoke.mutate(a.id);
                }}
              >
                {t("agents.revoke")}
              </Button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

/** A notification channel: header row with a toggle; the fields only show
 * once the channel is switched on. */
function Channel({
  icon,
  name,
  enabled,
  configured,
  onToggle,
  children,
}: {
  icon: ReactNode;
  name: string;
  enabled: boolean;
  configured: boolean;
  onToggle: (v: boolean) => void;
  children: ReactNode;
}) {
  const t = useT();
  const status = !enabled
    ? { tone: "neutral" as const, label: t("settings.channel.off") }
    : configured
      ? { tone: "signal" as const, label: t("settings.active") }
      : { tone: "alert" as const, label: t("settings.channel.setup") };

  return (
    <div className="overflow-hidden rounded-xl bg-surface-2">
      <div className="flex items-center gap-3 px-4 py-3">
        <span className="text-fg-2">{icon}</span>
        <span className="font-display text-[14px] text-fg">{name}</span>
        <Badge tone={status.tone}>{status.label}</Badge>
        <span className="ml-auto">
          <Toggle checked={enabled} onChange={onToggle} label={name} />
        </span>
      </div>
      {enabled && (
        <div className="space-y-4 bg-surface px-4 py-4 shadow-[inset_0_1px_0_rgba(0,0,0,0.04)]">{children}</div>
      )}
    </div>
  );
}

/** Checks the running version against `main` and, for a git checkout, can pull
 *  and rebuild in place. Everyone can see it; only an admin can trigger a
 *  check or apply it — same split as backup/restore. */
function UpdateSection({ isAdmin }: { isAdmin: boolean }) {
  const t = useT();
  const toast = useToast();
  const qc = useQueryClient();
  const [applying, setApplying] = useState(false);

  const q = useQuery({
    queryKey: ["update-status"],
    queryFn: api.updateStatus,
    refetchInterval: (query) => {
      const st = query.state.data?.apply.status;
      return applying || st === "updating" || st === "restarting" ? 2000 : 60000;
    },
  });

  const check = useMutation({
    mutationFn: api.checkForUpdate,
    onSuccess: (d) => {
      qc.setQueryData(["update-status"], d);
      toast({
        tone: "success",
        title: d.update_available ? "update.status.available" : "update.status.upToDate",
      });
    },
    onError: (e) =>
      toast({ tone: "error", title: "update.toast.checkFailed", desc: String(e).slice(0, 140) }),
  });

  const apply = useMutation({
    mutationFn: api.applyUpdate,
    onSuccess: (d) => {
      qc.setQueryData(["update-status"], d);
      setApplying(true);
    },
    onError: (e) =>
      toast({ tone: "error", title: "update.toast.applyFailed", desc: String(e).slice(0, 140) }),
  });

  const d = q.data;
  const applyStatus = d?.apply.status;

  useEffect(() => {
    if (!applying || !applyStatus) return;
    if (applyStatus === "idle") {
      setApplying(false);
      toast({ tone: "success", title: "update.toast.applied" });
    } else if (applyStatus === "failed") {
      setApplying(false);
      toast({ tone: "error", title: "update.toast.applyFailed", desc: d?.apply.error ?? undefined });
    }
  }, [applying, applyStatus]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!d) return <div className="panel mb-3 p-4"><SectionHeader title={t("settings.cat.update")} /></div>;

  const badge = applying || applyStatus === "updating" || applyStatus === "restarting"
    ? { tone: "amber" as const, label: t("update.status.updating") }
    : d.error
      ? { tone: "alert" as const, label: t("update.status.error") }
      : !d.latest
        ? { tone: "neutral" as const, label: t("update.status.unknown") }
        : d.update_available
          ? { tone: "amber" as const, label: t("update.status.available") }
          : { tone: "signal" as const, label: t("update.status.upToDate") };

  return (
    <section className="panel mb-3 p-4">
      <SectionHeader
        title={t("update.title")}
        sub={t("update.sub")}
        actions={
          isAdmin && (
            <Button
              variant="secondary"
              size="sm"
              icon={<UpdateIcon size={12} />}
              loading={check.isPending}
              disabled={applying}
              onClick={() => check.mutate()}
            >
              {t("update.check")}
            </Button>
          )
        }
      />

      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-3 rounded-xl bg-surface-2 px-4 py-3">
          <div>
            <p className="label mb-0.5">{t("update.current")}</p>
            <p className="mono text-[16px] text-fg">v{d.current}</p>
          </div>
          <Badge tone={badge.tone}>{badge.label}</Badge>
          <div className="ml-auto text-right">
            {d.latest && (
              <p className="mono text-[11px] text-fg-3">
                {t("update.latest", { version: d.latest })}
              </p>
            )}
            <p className="mono text-[10.5px] text-fg-3">
              {d.checked_at
                ? t("update.checked", { ago: timeAgo(d.checked_at) })
                : t("update.neverChecked")}
            </p>
          </div>
        </div>

        {d.error && (
          <p className="text-[11.5px] text-alert">{t("update.checkErrorPrefix")} {d.error}</p>
        )}

        {d.update_available && isAdmin && (
          <div className="space-y-3 rounded-xl bg-surface-2 p-4">
            {d.deploy_mode === "git" ? (
              <>
                <p className="text-[12.5px] text-fg-2">{t("update.git.hint")}</p>
                <Button
                  variant="primary"
                  size="sm"
                  icon={<Power size={12} />}
                  loading={applying}
                  disabled={applying}
                  onClick={() => {
                    if (confirm(t("update.apply.confirm"))) apply.mutate();
                  }}
                >
                  {t("update.applyNow")}
                </Button>
              </>
            ) : (
              <>
                <p className="text-[12.5px] text-fg-2">{t("update.container.hint")}</p>
                <pre className="mono overflow-x-auto rounded-lg bg-surface p-2.5 text-[11px] text-fg-2">
{`docker compose pull panel
docker compose up -d panel`}
                </pre>
              </>
            )}
          </div>
        )}

        {(applying || d.apply.log.length > 0) && (
          <div className="rounded-xl bg-surface-2 p-3">
            <p className="label mb-1.5">
              {applyStatus === "restarting"
                ? t("update.apply.restarting")
                : applyStatus === "failed"
                  ? t("update.apply.failed")
                  : t("update.apply.running")}
            </p>
            <pre className="mono max-h-48 overflow-y-auto whitespace-pre-wrap break-all text-[10.5px] text-fg-3">
              {d.apply.log.join("\n") || "…"}
            </pre>
          </div>
        )}

        <p className="text-[11px] leading-relaxed text-fg-3">
          {d.deploy_mode === "git" ? t("update.mode.git") : t("update.mode.container")}
        </p>
      </div>
    </section>
  );
}

/** Change your own username and password. Shown to every signed-in account. */
function AccountCard() {
  const t = useT();
  const toast = useToast();
  const qc = useQueryClient();
  const me = useAuth().account;
  const [username, setUsername] = useState(me?.username ?? "");
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");

  const nameChanged = username.trim().length >= 2 && username.trim() !== me?.username;
  const pwChanged = next.length >= 8;

  const save = useMutation({
    mutationFn: () =>
      api.updateProfile({
        current,
        ...(nameChanged ? { username: username.trim() } : {}),
        ...(pwChanged ? { new_password: next } : {}),
      }),
    onSuccess: () => {
      setCurrent("");
      setNext("");
      qc.invalidateQueries({ queryKey: AUTH_KEY });
      qc.invalidateQueries({ queryKey: ["accounts"] });
      toast({ tone: "success", title: "auth.account.saved" });
    },
    onError: () => toast({ tone: "error", title: "auth.account.failed" }),
  });

  return (
    <section className="panel mb-3 break-inside-avoid p-4">
      <SectionHeader title={t("auth.account.title")} />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={t("auth.field.username")}>
          <input
            className="input"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </Field>
        <div className="hidden sm:block" />
        <Field label={t("auth.password.current")} hint={t("auth.account.currentHint")}>
          <input
            className="input"
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
          />
        </Field>
        <Field label={t("auth.account.newOptional")}>
          <input
            className="input"
            type="password"
            autoComplete="new-password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
          />
        </Field>
      </div>
      <div className="mt-3">
        <Button
          variant="secondary"
          size="sm"
          loading={save.isPending}
          disabled={current.length < 1 || (!nameChanged && !pwChanged)}
          onClick={() => save.mutate()}
        >
          {t("auth.account.submit")}
        </Button>
      </div>
    </section>
  );
}

const ROLES: AccountRole[] = ["viewer", "editor", "admin"];

/** List / add / edit / remove accounts. Admin only. */
function AccountsCard() {
  const t = useT();
  const toast = useToast();
  const qc = useQueryClient();
  const me = useAuth().account;
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: api.accounts });
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<AccountRole>("viewer");

  const invalidate = () => qc.invalidateQueries({ queryKey: ["accounts"] });
  const fail = (e: unknown) =>
    toast({ tone: "error", title: "auth.accounts.failed", desc: String(e).slice(0, 120) });

  const create = useMutation({
    mutationFn: () => api.createAccount(username.trim(), password, role),
    onSuccess: () => {
      setUsername("");
      setPassword("");
      setRole("viewer");
      invalidate();
      toast({ tone: "success", title: "auth.accounts.created" });
    },
    onError: fail,
  });
  const setRoleFor = useMutation({
    mutationFn: (v: { id: number; role: AccountRole }) =>
      api.updateAccount(v.id, { role: v.role }),
    onSuccess: invalidate,
    onError: fail,
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.deleteAccount(id),
    onSuccess: invalidate,
    onError: fail,
  });

  return (
    <section className="panel mb-3 break-inside-avoid p-4">
      <SectionHeader title={t("auth.accounts.title")} sub={t("auth.accounts.sub")} />
      <div className="space-y-2">
        {(accounts.data ?? []).map((a) => (
          <div key={a.id} className="flex items-center gap-2 rounded-lg bg-surface-2 px-3 py-2">
            <span className="flex-1 truncate text-[12px] text-fg-2">{a.username}</span>
            <select
              className="input mono h-[26px] w-28 py-0 text-[11px]"
              value={a.role}
              disabled={a.id === me?.id}
              onChange={(e) =>
                setRoleFor.mutate({ id: a.id, role: e.target.value as AccountRole })
              }
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {t(`auth.role.${r}` as MessageKey)}
                </option>
              ))}
            </select>
            {a.id !== me?.id && (
              <button
                onClick={() => confirm(t("auth.accounts.removeConfirm")) && remove.mutate(a.id)}
                className="shrink-0 px-1 text-fg-3 hover:text-alert"
                title={t("common.remove")}
              >
                <Trash size={13} />
              </button>
            )}
          </div>
        ))}
      </div>
      <div className="mt-4 space-y-3 border-t border-fg/10 pt-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("auth.field.username")}>
            <input
              className="input"
              autoComplete="off"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
          </Field>
          <Field label={t("auth.field.password")}>
            <input
              className="input"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
        </div>
        <div className="flex items-end gap-3">
          <Field label={t("auth.accounts.role")} className="w-40">
            <select
              className="input mono"
              value={role}
              onChange={(e) => setRole(e.target.value as AccountRole)}
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {t(`auth.role.${r}` as MessageKey)}
                </option>
              ))}
            </select>
          </Field>
          <Button
            variant="secondary"
            size="sm"
            icon={<Plus size={12} />}
            loading={create.isPending}
            disabled={username.trim().length < 2 || password.length < 8}
            onClick={() => create.mutate()}
          >
            {t("auth.accounts.add")}
          </Button>
        </div>
      </div>
    </section>
  );
}

/** Download a full backup, or restore one (which restarts the panel). */
function BackupCard() {
  const t = useT();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  const onFile = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!confirm(t("settings.backup.restoreConfirm"))) return;
    setBusy(true);
    try {
      await api.restoreBackup(file);
      setDone(true);
      setTimeout(() => window.location.reload(), 5000);
    } catch (err) {
      toast({ tone: "error", title: "settings.backup.restoreFailed", desc: String(err).slice(0, 140) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel mb-3 p-4">
      <SectionHeader title={t("settings.section.backup")} sub={t("settings.backup.sub")} />
      {done ? (
        <p className="mono text-[12px] text-fg-2">{t("settings.backup.restored")}</p>
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          <a className="btn btn-secondary" href={api.backupUrl()}>
            {t("settings.backup.download")}
          </a>
          <label className="btn btn-secondary cursor-pointer">
            {busy ? t("settings.backup.restoring") : t("settings.backup.restore")}
            <input
              type="file"
              accept=".gz,.tgz,application/gzip"
              className="hidden"
              disabled={busy}
              onChange={onFile}
            />
          </label>
        </div>
      )}
    </section>
  );
}

/** Read-only bearer tokens for scripts and scrapers. Shown once on creation. */
function ApiTokensCard() {
  const t = useT();
  const toast = useToast();
  const qc = useQueryClient();
  const tokens = useQuery({ queryKey: ["api-tokens"], queryFn: api.apiTokens });
  const [name, setName] = useState("");
  const [fresh, setFresh] = useState<string | null>(null);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["api-tokens"] });
  const create = useMutation({
    mutationFn: () => api.createApiToken(name.trim()),
    onSuccess: (row) => {
      setName("");
      setFresh(row.token);
      invalidate();
    },
    onError: (e) =>
      toast({ tone: "error", title: "auth.tokens.failed", desc: String(e).slice(0, 120) }),
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.deleteApiToken(id),
    onSuccess: invalidate,
  });

  return (
    <section className="panel mb-3 break-inside-avoid p-4">
      <SectionHeader title={t("auth.tokens.title")} sub={t("auth.tokens.sub")} />

      {fresh && (
        <div className="mb-3 rounded-xl bg-surface-2 p-4">
          <p className="label text-fg-3">{t("auth.tokens.once")}</p>
          <div className="mt-1 flex items-center gap-2">
            <code className="mono flex-1 truncate text-[12px]">{fresh}</code>
            <Button
              variant="secondary"
              size="sm"
              onClick={() =>
                copyText(fresh).then((ok) =>
                  ok
                    ? toast({ tone: "success", title: "agents.token.copied" })
                    : toast({ tone: "error", title: "agents.token.copy" }),
                )
              }
            >
              {t("agents.token.copy")}
            </Button>
            <button
              onClick={() => setFresh(null)}
              className="shrink-0 px-1 text-fg-3 hover:text-fg"
              title={t("common.close")}
            >
              <Close size={13} />
            </button>
          </div>
        </div>
      )}

      <div className="space-y-2">
        {(tokens.data ?? []).map((tk) => (
          <div key={tk.id} className="flex items-center gap-2 rounded-lg bg-surface-2 px-3 py-2">
            <span className="flex-1 truncate text-[12px] text-fg-2">{tk.name}</span>
            <span className="mono shrink-0 text-[11px] text-fg-3">
              {tk.last_used_at ? timeAgo(tk.last_used_at) : t("auth.tokens.neverUsed")}
            </span>
            <button
              onClick={() => confirm(t("auth.tokens.removeConfirm")) && remove.mutate(tk.id)}
              className="shrink-0 px-1 text-fg-3 hover:text-alert"
              title={t("common.remove")}
            >
              <Trash size={13} />
            </button>
          </div>
        ))}
        {(tokens.data ?? []).length === 0 && (
          <p className="mono text-[12px] text-fg-3">{t("auth.tokens.none")}</p>
        )}
      </div>

      <div className="mt-4 flex items-end gap-3 border-t border-fg/10 pt-3">
        <Field label={t("auth.tokens.name")} className="flex-1">
          <input
            className="input"
            autoComplete="off"
            placeholder={t("auth.tokens.namePlaceholder")}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
        <Button
          variant="secondary"
          size="sm"
          icon={<Plus size={12} />}
          loading={create.isPending}
          disabled={name.trim().length < 2}
          onClick={() => create.mutate()}
        >
          {t("auth.tokens.add")}
        </Button>
      </div>
      <p className="mono mt-2 text-[11px] text-fg-3">{t("auth.tokens.hint")}</p>
    </section>
  );
}
