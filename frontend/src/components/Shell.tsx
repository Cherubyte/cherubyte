import clsx from "clsx";
import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { AUTH_KEY, useAuth, useCanWrite } from "../auth/AuthProvider";
import { useStream } from "../hooks/useStream";
import { useIsMobile } from "../hooks/useMediaQuery";
import { useNow } from "../hooks/useNow";
import { useTheme } from "../hooks/useTheme";
import { useToast } from "./Toaster";
import { hms } from "../lib/format";
import { ChartMark } from "./Glyph";
import { useT, type MessageKey } from "../i18n";
import {
  HostsIcon,
  ReviewIcon,
  PeopleIcon,
  LogIcon,
  ConfigIcon,
  StatsIcon,
} from "./Glyph";

/** shown in the margin / mobile drawer — single source is package.json */
const APP_VERSION = `v${__APP_VERSION__}`;

/* ── the routes — each is a sheet in the chart folio ────────────────── */
type Route = {
  to: string;
  code: string;
  labelKey: MessageKey;
  titleKey: MessageKey;
  end?: boolean;
  Icon: (p: { size?: number; className?: string }) => JSX.Element;
};
const ROUTES: Route[] = [
  { to: "/", code: "01", labelKey: "nav.hosts", titleKey: "title.hosts", end: true, Icon: HostsIcon },
  { to: "/approvals", code: "02", labelKey: "nav.review", titleKey: "title.review", Icon: ReviewIcon },
  { to: "/users", code: "03", labelKey: "nav.people", titleKey: "title.people", Icon: PeopleIcon },
  { to: "/distribution", code: "04", labelKey: "nav.stats", titleKey: "title.stats", Icon: StatsIcon },
  { to: "/events", code: "05", labelKey: "nav.log", titleKey: "title.log", Icon: LogIcon },
  { to: "/settings", code: "06", labelKey: "nav.config", titleKey: "title.config", Icon: ConfigIcon },
];

function titleKeyOf(pathname: string): MessageKey {
  if (pathname.startsWith("/devices/")) return "title.hostDetail";
  if (pathname.startsWith("/users/")) return "title.personDetail";
  const r = ROUTES.find((s) => (s.end ? pathname === s.to : pathname.startsWith(s.to) && s.to !== "/"));
  return r?.titleKey ?? "title.hosts";
}
function activeKey(pathname: string): string {
  if (pathname.startsWith("/devices/")) return "/";
  if (pathname.startsWith("/users/")) return "/users";
  const r = ROUTES.find((s) => (s.end ? pathname === s.to : pathname.startsWith(s.to) && s.to !== "/"));
  return r?.to ?? "/";
}

/* ── scan ──────────────────────────────────────────────────────────── */
function useScan() {
  const qc = useQueryClient();
  const toast = useToast();
  const t = useT();
  const [running, setRunning] = useState(false);
  const refresh = async () => {
    await qc.invalidateQueries({ queryKey: ["devices"] });
    await qc.invalidateQueries({ queryKey: ["stats"] });
  };
  const mut = useMutation({
    mutationFn: api.scan,
    onMutate: () => setRunning(true),
    onSuccess: (data) => {
      // The panel can't sweep a network itself — it nudges the agents that can,
      // and the response says what actually happened.
      if (data.status === "no-agents") {
        setRunning(false);
        toast({ tone: "error", title: t("scan.noAgents"), desc: t("scan.noAgentsDesc") });
        return;
      }
      if (data.status === "stale") {
        setRunning(false);
        toast({ tone: "error", title: t("scan.staleTitle"), desc: t("scan.staleDesc") });
        void refresh();
        return;
      }
      if (data.status === "queued") {
        setRunning(false);
        toast({ tone: "info", title: t("scan.queued") });
        void refresh();
        return;
      }
      // triggered: give the agent a moment to sweep and report back
      toast({ tone: "success", title: t("scan.triggered", { n: data.triggered }) });
      setTimeout(async () => {
        setRunning(false);
        await refresh();
      }, 3200);
    },
    onError: () => {
      setRunning(false);
      toast({ tone: "error", title: t("scan.failed") });
    },
  });
  return { run: () => mut.mutate(), running: running || mut.isPending };
}

function lastSweep(iso: string | null, now: number): string {
  if (!iso) return "—";
  const s = Math.round((now - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.round(s / 60)}m`;
  return `${Math.round(s / 3600)}h`;
}
function cadence(iv?: number): string {
  if (!iv) return "—";
  return iv >= 60 ? `${Math.round(iv / 60)}min` : `${iv}s`;
}

function useVitals() {
  const stats = useQuery({ queryKey: ["stats"], queryFn: api.stats, refetchInterval: 12000 });
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  return { s: stats.data, iv: settings.data?.scan_interval_seconds };
}

function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.logout,
    onSuccess: () => {
      qc.clear();
      qc.invalidateQueries({ queryKey: AUTH_KEY });
    },
  });
}

/* ── the chart's title block — mark + wordmark ─────────────────────── */
function TitleBlock({ compact }: { compact?: boolean }) {
  return (
    <span className="flex items-center gap-2.5">
      <ChartMark size={compact ? 20 : 24} />
      <span
        className={clsx(
          "font-display leading-none tracking-[0.06em] text-fg",
          compact ? "text-[16px]" : "text-[18px]",
        )}
      >
        NETSCAN
      </span>
    </span>
  );
}

/* ═══════════════════════════ Shell ═══════════════════════════════════ */
export function Shell() {
  useStream();
  const isMobile = useIsMobile();
  return isMobile ? <MobileShell /> : <DesktopShell />;
}

/* ── DESKTOP ───────────────────────────────────────────────────────── */
function DesktopShell() {
  const { pathname } = useLocation();
  useTheme(); // keeps the persisted theme class applied; controlled in Config
  const { run, running } = useScan();
  const { s, iv } = useVitals();
  const now = useNow();
  const t = useT();
  const active = activeKey(pathname);
  const { account } = useAuth();
  const canWrite = useCanWrite();
  const logout = useLogout();

  return (
    <div className="flex h-screen bg-bg">
      {/* left margin — the chart folio */}
      <aside className="flex w-[212px] shrink-0 flex-col border-r border-edge-2 bg-surface/70">
        <div className="flex h-[52px] items-center px-4">
          <TitleBlock />
        </div>
        <div className="mx-4 border-t border-edge-2" />

        <nav className="flex flex-1 flex-col px-2 py-2.5">
          <span className="key px-2.5 pb-2 pt-1">{t("nav.folio")}</span>
          {ROUTES.map((r) => {
            const on = r.to === active;
            const pend = r.to === "/approvals" && (s?.pending ?? 0) > 0;
            return (
              <NavLink
                key={r.to}
                to={r.to}
                end={r.end}
                className={clsx(
                  "group relative flex items-center gap-2.5 py-[7px] pl-2.5 pr-2 text-[12.5px] transition-colors",
                  on ? "text-fg" : "text-fg-2 hover:text-fg",
                )}
              >
                {/* leader tick — carmine only on the held sheet */}
                <span
                  className={clsx(
                    "absolute left-0 top-1/2 h-[13px] w-[2px] -translate-y-1/2",
                    on ? "bg-signal" : "bg-transparent",
                  )}
                />
                <span
                  className={clsx(
                    "mono text-[9.5px] tabular-nums",
                    on ? "text-signal" : "text-fg-3",
                  )}
                >
                  {r.code}
                </span>
                <r.Icon size={14} className={on ? "text-fg" : "text-fg-3 group-hover:text-fg-2"} />
                <span className={clsx("font-medium", on && "font-semibold")}>{t(r.labelKey)}</span>
                {pend && (
                  <span className="tag tag-alert ml-auto !h-[15px] !px-1.5 !text-[9px]">{s?.pending}</span>
                )}
              </NavLink>
            );
          })}
        </nav>

        <div className="mx-4 border-t border-edge-2" />
        <div className="p-3.5">
          {canWrite && (
            <button onClick={run} disabled={running} className="btn btn-primary w-full">
              {running ? t("shell.sweeping") : t("shell.sweep")}
            </button>
          )}
          {account && (
            <div className={clsx("flex items-center justify-between gap-2", canWrite && "mt-3")}>
              <span className="min-w-0 truncate">
                <span className="text-[12px] text-fg-2">{account.username}</span>
                <span className="mono ml-1.5 text-[9px] uppercase tracking-[0.1em] text-fg-3">
                  {t(`auth.role.${account.role}` as MessageKey)}
                </span>
              </span>
              <button
                onClick={() => logout.mutate()}
                className="label shrink-0 transition-colors hover:text-fg"
              >
                {t("auth.logout")}
              </button>
            </div>
          )}
          <div className="mt-2.5 flex items-center gap-2">
            <span className="key text-fg-3/80">{t("shell.edition")}</span>
            <span className="label tabular-nums">{APP_VERSION}</span>
          </div>
        </div>
      </aside>

      {/* content */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* margin strip — chart marginalia */}
        <header className="flex h-[44px] shrink-0 items-center gap-6 border-b border-edge-2 bg-surface/70 px-6">
          <Vital k={t("shell.vital.subnet")} v={s?.subnet ?? "—"} />
          <Vital k={t("shell.vital.held")} v={s ? `${s.online} / ${s.total}` : "—"} big />
          <Vital k={t("shell.vital.sweep")} v={cadence(iv)} />
          <Vital
            k={t("shell.vital.last")}
            v={running ? "surveying" : lastSweep(s?.last_report ?? s?.last_scan ?? null, now)}
            tone={running ? "signal" : s?.agents_stale ? "alert" : undefined}
          />
          <Vital k={t("shell.vital.epoch")} v={hms(new Date(now))} className="ml-auto" />
        </header>

        <main className="relative min-h-0 flex-1 overflow-y-auto">
          {running && (
            <div className="pointer-events-none absolute inset-0 z-20 overflow-hidden">
              <div className="sweep-line" />
            </div>
          )}
          <div key={pathname} className="view-in mx-auto w-full max-w-[1320px] px-8 py-7">
            <p className="key mb-6 flex items-center gap-2.5 text-fg-2">
              <span className="h-[11px] w-[2px] bg-signal" />
              {t(titleKeyOf(pathname))}
            </p>
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}

function Vital({
  k,
  v,
  big,
  tone,
  className,
}: {
  k: string;
  v: string;
  big?: boolean;
  tone?: "signal" | "alert";
  className?: string;
}) {
  return (
    <span className={clsx("flex items-baseline gap-2 whitespace-nowrap", className)}>
      <span className="key">{k}</span>
      <span
        className={clsx(
          "mono tnum",
          big ? "text-[13px] text-fg" : "text-[12px]",
          tone === "signal"
            ? "text-signal"
            : tone === "alert"
              ? "text-alert"
              : big
                ? "text-fg"
                : "text-fg-2",
        )}
      >
        {v}
      </span>
    </span>
  );
}

/* ── MOBILE ────────────────────────────────────────────────────────── */
function MobileShell() {
  const { pathname } = useLocation();
  useTheme();
  const { run, running } = useScan();
  const { s, iv } = useVitals();
  const now = useNow();
  const t = useT();
  const active = activeKey(pathname);
  const canWrite = useCanWrite();
  const logout = useLogout();

  return (
    <div className="flex min-h-screen flex-col bg-bg">
      <header className="sticky top-0 z-40 shrink-0 border-b border-edge-2 bg-surface">
        <div className="flex h-[48px] items-center gap-2.5 px-4">
          <TitleBlock compact />
          <span className="mono ml-1 text-[13px] tnum text-fg">
            {s ? `${s.online}/${s.total}` : "—"}
          </span>
          <div className="ml-auto flex items-center gap-2">
            <button onClick={() => logout.mutate()} className="label">
              {t("auth.logout")}
            </button>
            {canWrite && (
              <button onClick={run} disabled={running} className="btn btn-primary btn-sm">
                {running ? "···" : t("shell.sweep")}
              </button>
            )}
          </div>
        </div>
        <div className="mono flex items-center gap-x-3 overflow-x-auto border-t border-edge px-4 py-1.5 text-[10.5px] text-fg-3">
          <span>{s?.subnet ?? "—"}</span>
          <span className="text-fg-2">{s ? t("shell.onlineCount", { n: s.online }) : "—"}</span>
          <span>sweep {cadence(iv)}</span>
          <span>
            {running
              ? t("shell.sweepingShort")
              : t("shell.lastShort", { ago: lastSweep(s?.last_scan ?? null, now) })}
          </span>
        </div>
      </header>

      <main className="relative min-h-0 flex-1">
        {running && (
          <div className="pointer-events-none sticky top-0 z-20 h-0 overflow-visible">
            <div className="sweep-line" />
          </div>
        )}
        <div key={pathname} className="view-in px-4 py-4 pb-24">
          <p className="key mb-3.5 flex items-center gap-2.5 text-fg-2">
            <span className="h-[11px] w-[2px] bg-signal" />
            {t(titleKeyOf(pathname))}
          </p>
          <Outlet />
        </div>
      </main>

      {/* bottom tabs */}
      <nav className="fixed inset-x-0 bottom-0 z-40 flex items-stretch border-t border-edge-2 bg-surface pb-[env(safe-area-inset-bottom)]">
        {ROUTES.map((r) => {
          const on = r.to === active;
          return (
            <NavLink
              key={r.to}
              to={r.to}
              end={r.end}
              className="relative flex min-h-[56px] flex-1 flex-col items-center justify-center gap-1 py-2"
            >
              <span className={clsx("absolute inset-x-3 top-0 h-[2px]", on ? "bg-signal" : "bg-transparent")} />
              <span className="relative">
                <r.Icon size={17} className={on ? "text-fg" : "text-fg-3"} />
                {r.to === "/approvals" && (s?.pending ?? 0) > 0 && (
                  <span className="absolute -right-2 -top-1.5 grid h-[13px] min-w-[13px] place-items-center bg-alert px-[3px] text-[8px] leading-none text-alert-fg">
                    {s?.pending}
                  </span>
                )}
              </span>
              <span className={clsx("text-[9.5px] font-medium", on ? "text-fg" : "text-fg-3")}>
                {t(r.labelKey)}
              </span>
            </NavLink>
          );
        })}
      </nav>
    </div>
  );
}
