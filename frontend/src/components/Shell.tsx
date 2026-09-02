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
import { RollingValue } from "./ui";
import { CommandPalette } from "./CommandPalette";
import { Onboarding } from "./Onboarding";
import { ProgressiveBlur } from "./ProgressiveBlur";
import { hms } from "../lib/format";
import { AppMark, Moon, Search, Sun } from "./Glyph";
import { motion, useReducedMotion, snappy, fade } from "../lib/motion";
import { useT, type MessageKey } from "../i18n";
import { translate } from "../i18n/translate";

/** Toast confirmations are always in English, regardless of the UI locale. */
const enT = (k: MessageKey, vars?: Record<string, string | number>) => translate("en", k, vars);
import {
  HostsIcon,
  ReviewIcon,
  PeopleIcon,
  LogIcon,
  ConfigIcon,
  StatsIcon,
  Radar,
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
  { to: "/topology", labelKey: "nav.topology", titleKey: "title.topology", Icon: Radar },
  { to: "/settings", labelKey: "nav.config", titleKey: "title.config", Icon: ConfigIcon },
];

/** Settings ▸ Network ▸ SNMP gates this — most installs have nothing LLDP
 *  would draw, so it stays out of the nav until switched on. */
function useTopologyEnabled(): boolean {
  const q = useQuery({ queryKey: ["settings"], queryFn: api.settings, staleTime: 60000 });
  return q.data?.topology_enabled ?? false;
}

function visibleRoutes(topologyEnabled: boolean): Route[] {
  return topologyEnabled ? ROUTES : ROUTES.filter((r) => r.to !== "/topology");
}

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
        toast({ tone: "error", title: enT("scan.noAgents"), desc: enT("scan.noAgentsDesc") });
        return;
      }
      if (data.status === "stale") {
        setRunning(false);
        toast({ tone: "error", title: enT("scan.staleTitle"), desc: enT("scan.staleDesc") });
        void refresh();
        return;
      }
      if (data.status === "queued") {
        setRunning(false);
        toast({ tone: "info", title: enT("scan.queued") });
        void refresh();
        return;
      }
      // triggered: give the agent a moment to sweep and report back
      toast({ tone: "success", title: enT("scan.triggered", { n: data.triggered }) });
      setTimeout(async () => {
        setRunning(false);
        await refresh();
      }, 3200);
    },
    onError: () => {
      setRunning(false);
      toast({ tone: "error", title: enT("scan.failed") });
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

/** `stats.subnet` is a comma-joined list — keep one as-is, collapse several to
 * "first +N" with the full list on hover so the header line stays tidy. */
function subnetVital(joined?: string): { label: string; title?: string } {
  const list = (joined ?? "").split(",").map((s) => s.trim()).filter(Boolean);
  if (list.length === 0) return { label: "—" };
  if (list.length === 1) return { label: list[0] };
  return { label: `${list[0]} +${list.length - 1}`, title: list.join(", ") };
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

/* ── quick theme toggle — sun / moon ─────────────────────────────── */
function ThemeToggle({ className }: { className?: string }) {
  const { light, toggle } = useTheme();
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={light ? "Switch to dark" : "Switch to light"}
      title={light ? "Dark" : "Light"}
      className={clsx(
        "grid h-7 w-7 place-items-center rounded-lg text-fg-3 transition-colors hover:bg-fg/[0.06] hover:text-fg",
        className,
      )}
    >
      {light ? <Moon size={15} /> : <Sun size={15} />}
    </button>
  );
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
        Cherubyte
      </span>
    </span>
  );
}

/* ═══════════════════════════ Shell ═══════════════════════════════════ */
export function Shell() {
  useStream();
  const isMobile = useIsMobile();
  return (
    <>
      {isMobile ? <MobileShell /> : <DesktopShell />}
      <CommandPalette />
      <Onboarding />
    </>
  );
}

/** small toolbar / top-bar trigger for the ⌘K palette */
function CmdKButton({ compact }: { compact?: boolean }) {
  const t = useT();
  const open = () => window.dispatchEvent(new Event("cherubyte:cmdk"));
  if (compact)
    return (
      <button onClick={open} aria-label={t("cmd.placeholder")} className="grid h-8 w-8 place-items-center rounded-lg text-fg-3 hover:bg-fg/[0.06] hover:text-fg">
        <Search size={16} />
      </button>
    );
  return (
    <button
      onClick={open}
      className="flex items-center gap-2 rounded-lg bg-fg/[0.05] px-3 py-1.5 text-[12.5px] text-fg-3 transition-colors hover:bg-fg/[0.08] hover:text-fg-2"
    >
      <Search size={13} />
      <span>{t("cmd.trigger")}</span>
      <kbd className="mono rounded bg-fg/[0.06] px-1 text-[10px]">⌘K</kbd>
    </button>
  );
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
  const reduced = useReducedMotion();
  const active = activeKey(pathname);
  const net = subnetVital(s?.subnet);
  const { account } = useAuth();
  const canWrite = useCanWrite();
  const logout = useLogout();
  const routes = visibleRoutes(useTopologyEnabled());

  return (
    <div className="flex h-screen bg-bg">
      {/* sidebar — sits on the grey ground, no divider */}
      <aside className="flex w-[228px] shrink-0 flex-col">
        <div className="flex h-[60px] items-center px-6">
          <Wordmark />
        </div>

        <nav className="flex flex-1 flex-col gap-0.5 px-3 py-2">
          {routes.map((r) => {
            const on = r.to === active;
            const pend = r.to === "/approvals" && (s?.pending ?? 0) > 0;
            return (
              <NavLink
                key={r.to}
                to={r.to}
                end={r.end}
                className={clsx(
                  "group relative flex items-center gap-3 rounded-[10px] px-3 py-[7px] text-[13.5px] transition-colors",
                  on ? "text-fg" : "text-fg-2 hover:bg-fg/[0.05] hover:text-fg",
                )}
              >
                {on && (
                  <motion.span
                    layoutId="nav-active-desktop"
                    className="absolute inset-0 rounded-[10px] bg-surface shadow-e1"
                    transition={reduced ? { duration: 0 } : snappy}
                  />
                )}
                <r.Icon
                  size={16}
                  className={clsx("relative z-[1]", on ? "text-fg" : "text-fg-3 group-hover:text-fg-2")}
                />
                <span className={clsx("relative z-[1]", on ? "font-medium" : "font-normal")}>{t(r.labelKey)}</span>
                {pend && (
                  <span className="relative z-[1] ml-auto grid h-[18px] min-w-[18px] place-items-center rounded-full bg-alert px-1 text-[10px] font-medium tabular-nums text-alert-fg">
                    {s?.pending}
                  </span>
                )}
              </NavLink>
            );
          })}
        </nav>

        <div className="p-3.5">
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
          <div className="mt-2.5 flex items-center justify-between">
            <span className="label">{APP_VERSION}</span>
            <ThemeToggle className="-mr-1" />
          </div>
        </div>
      </aside>

      {/* content — the header floats over it, so the page scrolls up under a
          transparent, heavily-blurred bar rather than stopping at an opaque one */}
      <div className="relative flex min-w-0 flex-1 flex-col">
        <header className="absolute inset-x-0 top-0 z-20 flex h-[60px] items-center gap-4 px-8">
          <div className="pointer-events-none absolute -bottom-16 inset-x-0 top-0 -z-10">
            <ProgressiveBlur strength={28} className="absolute inset-0" />
            <div className="absolute inset-0 bg-gradient-to-b from-bg/65 to-transparent" />
          </div>
          <h1 className="font-display text-[15px] text-fg">{t(titleKeyOf(pathname))}</h1>
          <CmdKButton />
          <div className="ml-auto flex items-center gap-5 text-[12px] text-fg-3">
            <Vital k={t("shell.vital.subnet")} v={net.label} title={net.title} />
            <Vital k={t("shell.vital.online")} v={s ? `${s.online} / ${s.total}` : "—"} strong roll />
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

        <main className="relative min-h-0 flex-1 overflow-y-auto pt-[60px]">
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
  roll,
  title,
}: {
  k: string;
  v: string;
  strong?: boolean;
  tone?: "alert";
  /** flip the figure on change — only for values that tick rarely, not the clock */
  roll?: boolean;
  title?: string;
}) {
  return (
    <span className="flex items-baseline gap-1.5 whitespace-nowrap" title={title}>
      <span className="text-[10.5px] uppercase tracking-[0.04em] text-fg-3">{k}</span>
      <span
        className={clsx(
          "mono tnum",
          tone === "alert" ? "text-alert" : strong ? "text-fg" : "text-fg-2",
        )}
      >
        {roll ? <RollingValue>{v}</RollingValue> : v}
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
  const reduced = useReducedMotion();
  const active = activeKey(pathname);
  const net = subnetVital(s?.subnet);
  const canWrite = useCanWrite();
  const logout = useLogout();
  const routes = visibleRoutes(useTopologyEnabled());

  return (
    <div className="flex min-h-screen flex-col bg-bg">
      <header className="sticky top-0 z-40 shrink-0 shadow-[0_1px_12px_-4px_rgba(0,0,0,0.12)]">
        <div className="pointer-events-none absolute -bottom-16 inset-x-0 top-0 -z-10">
          <ProgressiveBlur strength={28} className="absolute inset-0" />
          <div className="absolute inset-0 bg-gradient-to-b from-bg/65 to-transparent" />
        </div>
        <div className="flex h-[52px] items-center gap-2.5 px-4">
          <Wordmark compact />
          <span className="mono ml-1 text-[13px] tnum text-fg">
            <RollingValue>{s ? `${s.online}/${s.total}` : "—"}</RollingValue>
          </span>
          <div className="ml-auto flex items-center gap-1.5">
            <CmdKButton compact />
            <ThemeToggle />
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
        <div className="mono flex items-center gap-x-3 overflow-x-auto px-4 pb-2 text-[10.5px] text-fg-3">
          <span title={net.title}>{net.label}</span>
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
      <nav className="fixed inset-x-0 bottom-0 z-40 flex items-stretch bg-bg/85 pb-[env(safe-area-inset-bottom)] shadow-[0_-1px_12px_-4px_rgba(0,0,0,0.12)] backdrop-blur-xl">
        {routes.map((r) => {
          const on = r.to === active;
          return (
            <NavLink
              key={r.to}
              to={r.to}
              end={r.end}
              className="relative flex min-h-[54px] flex-1 flex-col items-center justify-center gap-1 py-2"
            >
              {on && (
                <motion.span
                  layoutId="nav-active-mobile"
                  className="absolute inset-x-2 inset-y-1.5 rounded-xl bg-fg/[0.06]"
                  transition={reduced ? { duration: 0 } : snappy}
                />
              )}
              <span className="relative z-[1]">
                <r.Icon size={19} className={on ? "text-fg" : "text-fg-3"} />
                {r.to === "/approvals" && (s?.pending ?? 0) > 0 && (
                  <span className="absolute -right-2.5 -top-1.5 grid h-[14px] min-w-[14px] place-items-center rounded-full bg-alert px-[3px] text-[8px] leading-none text-alert-fg">
                    {s?.pending}
                  </span>
                )}
              </span>
              <span className={clsx("relative z-[1] text-[9.5px] font-medium", on ? "text-fg" : "text-fg-3")}>
                {t(r.labelKey)}
              </span>
            </NavLink>
          );
        })}
      </nav>
    </div>
  );
}
