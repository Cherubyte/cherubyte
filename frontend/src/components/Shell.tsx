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
import { AppMark } from "./Glyph";
import { motion, useReducedMotion, snappy, fade } from "../lib/motion";
import { useT, type MessageKey } from "../i18n";
import {
  HostsIcon,
  ReviewIcon,
  PeopleIcon,
  LogIcon,
  ConfigIcon,
  StatsIcon,
} from "./Glyph";

/** shown in the sidebar foot — single source is package.json */
const APP_VERSION = `v${__APP_VERSION__}`;

/* ── the routes ────────────────────────────────────────────────────── */
type Route = {
  to: string;
  labelKey: MessageKey;
  titleKey: MessageKey;
  end?: boolean;
  Icon: (p: { size?: number; className?: string }) => JSX.Element;
};
const ROUTES: Route[] = [
  { to: "/", labelKey: "nav.hosts", titleKey: "title.hosts", end: true, Icon: HostsIcon },
  { to: "/approvals", labelKey: "nav.review", titleKey: "title.review", Icon: ReviewIcon },
  { to: "/users", labelKey: "nav.people", titleKey: "title.people", Icon: PeopleIcon },
  { to: "/distribution", labelKey: "nav.stats", titleKey: "title.stats", Icon: StatsIcon },
  { to: "/events", labelKey: "nav.log", titleKey: "title.log", Icon: LogIcon },
  { to: "/settings", labelKey: "nav.config", titleKey: "title.config", Icon: ConfigIcon },
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

/* ── mark + wordmark ─────────────────────────────────────────────── */
function Wordmark({ compact }: { compact?: boolean }) {
  return (
    <span className="flex items-center gap-2.5">
      <AppMark size={compact ? 20 : 22} className="text-fg" />
      <span
        className={clsx(
          "font-display leading-none text-fg",
          compact ? "text-[15px]" : "text-[16px]",
        )}
      >
        NetScan
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

/* ── the animated page body, shared by both shells ─────────────────── */
function PageBody({
  pathname,
  className,
  children,
}: {
  pathname: string;
  className?: string;
  children: React.ReactNode;
}) {
  const reduced = useReducedMotion();
  return (
    <motion.div
      key={pathname}
      initial={reduced ? { opacity: 0 } : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={reduced ? fade : snappy}
      className={className}
    >
      {children}
    </motion.div>
  );
}

/* ── DESKTOP ───────────────────────────────────────────────────────── */
function DesktopShell() {
  const { pathname } = useLocation();
  useTheme();
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
      {/* sidebar */}
      <aside className="flex w-[232px] shrink-0 flex-col border-r border-edge bg-surface">
        <div className="flex h-[56px] items-center px-5">
          <Wordmark />
        </div>

        <nav className="flex flex-1 flex-col gap-0.5 px-3 py-3">
          {ROUTES.map((r) => {
            const on = r.to === active;
            const pend = r.to === "/approvals" && (s?.pending ?? 0) > 0;
            return (
              <NavLink
                key={r.to}
                to={r.to}
                end={r.end}
                className={clsx(
                  "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-[13.5px] transition-colors",
                  on ? "bg-surface-2 text-fg" : "text-fg-2 hover:bg-surface-2/60 hover:text-fg",
                )}
              >
                <r.Icon size={16} className={on ? "text-fg" : "text-fg-3 group-hover:text-fg-2"} />
                <span className={clsx(on ? "font-medium" : "font-normal")}>{t(r.labelKey)}</span>
                {pend && (
                  <span className="ml-auto grid h-[18px] min-w-[18px] place-items-center rounded-full bg-alert px-1 text-[10px] font-medium tabular-nums text-alert-fg">
                    {s?.pending}
                  </span>
                )}
              </NavLink>
            );
          })}
        </nav>

        <div className="border-t border-edge p-3.5">
          {canWrite && (
            <button onClick={run} disabled={running} className="btn btn-primary w-full">
              {running ? t("shell.sweeping") : t("shell.sweep")}
            </button>
          )}
          {account && (
            <div className={clsx("flex items-center justify-between gap-2", canWrite && "mt-3")}>
              <span className="min-w-0 truncate">
                <span className="text-[12.5px] text-fg-2">{account.username}</span>
                <span className="ml-1.5 text-[10.5px] text-fg-3">
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
          <div className="mt-2.5 label">{APP_VERSION}</div>
        </div>
      </aside>

      {/* content */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="relative z-10 flex h-[56px] shrink-0 items-center gap-6 border-b border-edge bg-surface/75 px-8 backdrop-blur-xl">
          <h1 className="font-display text-[15px] text-fg">{t(titleKeyOf(pathname))}</h1>
          <div className="ml-auto flex items-center gap-5 text-[12px] text-fg-3">
            <Vital k={t("shell.vital.subnet")} v={s?.subnet ?? "—"} />
            <Vital k={t("shell.vital.online")} v={s ? `${s.online} / ${s.total}` : "—"} strong />
            <Vital
              k={t("shell.vital.last")}
              v={running ? t("shell.sweeping") : lastSweep(s?.last_report ?? s?.last_scan ?? null, now)}
              tone={s?.agents_stale ? "alert" : undefined}
            />
            <Vital k={t("shell.vital.sweep")} v={cadence(iv)} />
            <span className="mono tnum text-fg-2">{hms(new Date(now))}</span>
          </div>
          {running && <div className="scan-bar" />}
        </header>

        <main className="relative min-h-0 flex-1 overflow-y-auto">
          <PageBody pathname={pathname} className="mx-auto w-full max-w-[1240px] px-8 py-8">
            <Outlet />
          </PageBody>
        </main>
      </div>
    </div>
  );
}

function Vital({
  k,
  v,
  strong,
  tone,
}: {
  k: string;
  v: string;
  strong?: boolean;
  tone?: "alert";
}) {
  return (
    <span className="flex items-baseline gap-1.5 whitespace-nowrap">
      <span className="text-[10.5px] uppercase tracking-[0.04em] text-fg-3">{k}</span>
      <span
        className={clsx(
          "mono tnum",
          tone === "alert" ? "text-alert" : strong ? "text-fg" : "text-fg-2",
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
      <header className="sticky top-0 z-40 shrink-0 border-b border-edge bg-surface/80 backdrop-blur-xl">
        <div className="flex h-[52px] items-center gap-2.5 px-4">
          <Wordmark compact />
          <span className="mono ml-1 text-[13px] tnum text-fg">
            {s ? `${s.online}/${s.total}` : "—"}
          </span>
          <div className="ml-auto flex items-center gap-2.5">
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
          <span>{cadence(iv)}</span>
          <span>
            {running
              ? t("shell.sweepingShort")
              : t("shell.lastShort", { ago: lastSweep(s?.last_scan ?? null, now) })}
          </span>
        </div>
        {running && <div className="scan-bar" />}
      </header>

      <main className="relative min-h-0 flex-1">
        <PageBody pathname={pathname} className="px-4 py-4 pb-24">
          <p className="font-display mb-3.5 text-[15px] text-fg">{t(titleKeyOf(pathname))}</p>
          <Outlet />
        </PageBody>
      </main>

      {/* bottom tabs */}
      <nav className="fixed inset-x-0 bottom-0 z-40 flex items-stretch border-t border-edge bg-surface/85 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl">
        {ROUTES.map((r) => {
          const on = r.to === active;
          return (
            <NavLink
              key={r.to}
              to={r.to}
              end={r.end}
              className="relative flex min-h-[54px] flex-1 flex-col items-center justify-center gap-1 py-2"
            >
              <span className="relative">
                <r.Icon size={19} className={on ? "text-fg" : "text-fg-3"} />
                {r.to === "/approvals" && (s?.pending ?? 0) > 0 && (
                  <span className="absolute -right-2.5 -top-1.5 grid h-[14px] min-w-[14px] place-items-center rounded-full bg-alert px-[3px] text-[8px] leading-none text-alert-fg">
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
