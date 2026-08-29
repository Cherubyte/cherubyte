import clsx from "clsx";
import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { AUTH_KEY, useAuth, useCanWrite } from "../auth/AuthProvider";
import { useStream } from "../hooks/useStream";
import { useIsMobile } from "../hooks/useMediaQuery";
import { useNow } from "../hooks/useNow";
import { useToast } from "./Toaster";
import { hms } from "../lib/format";
import { useT, useLocale, type MessageKey } from "../i18n";
import { LOCALES } from "../i18n/locale";
import {
  HostsIcon,
  ReviewIcon,
  PeopleIcon,
  LogIcon,
  ConfigIcon,
  StatsIcon,
} from "./Glyph";

/* ── the routes ─────────────────────────────────────────────────────── */
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

/* ── theme — :root is dark; `.light` opts into the recolour ─────────── */
function useTheme() {
  const [light, setLight] = useState(() => localStorage.getItem("netscan-theme") === "light");
  const first = useRef(true);
  useEffect(() => {
    const r = document.documentElement;
    r.classList.toggle("light", light);
    localStorage.setItem("netscan-theme", light ? "light" : "dark");
    if (first.current) {
      first.current = false;
      return;
    }
    // brief cross-fade only on an actual toggle
    r.classList.add("theme-anim");
    const t = setTimeout(() => r.classList.remove("theme-anim"), 180);
    return () => clearTimeout(t);
  }, [light]);
  return { light, toggle: () => setLight((v) => !v) };
}

/* ── scan ──────────────────────────────────────────────────────────── */
function useScan() {
  const qc = useQueryClient();
  const toast = useToast();
  const t = useT();
  const [running, setRunning] = useState(false);
  const mut = useMutation({
    mutationFn: api.scan,
    onMutate: () => setRunning(true),
    onSuccess: (data) => {
      // The panel can't start a sweep — an agent does, on its own cadence. With
      // no agent enrolled, clicking Sweep would do nothing at all; say so.
      if (data.agents === 0) {
        setRunning(false);
        toast({
          tone: "error",
          title: t("scan.noAgents"),
          desc: t("scan.noAgentsDesc"),
        });
        return;
      }
      setTimeout(async () => {
        setRunning(false);
        await qc.invalidateQueries({ queryKey: ["devices"] });
        await qc.invalidateQueries({ queryKey: ["stats"] });
        toast({ tone: "success", title: t("toast.scanComplete") });
      }, 2600);
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

/* ═══════════════════════════ Shell ═══════════════════════════════════ */
export function Shell() {
  useStream();
  const isMobile = useIsMobile();
  return isMobile ? <MobileShell /> : <DesktopShell />;
}

/* ── DESKTOP ───────────────────────────────────────────────────────── */
function LangSwitch() {
  const [locale, setLocale] = useLocale();
  return (
    <span className="mono inline-flex overflow-hidden rounded-[3px] border border-edge-2 text-[9px] leading-none">
      {(Object.keys(LOCALES) as Array<keyof typeof LOCALES>).map((l) => (
        <button
          key={l}
          onClick={() => setLocale(l)}
          className={clsx(
            "px-1.5 py-1 uppercase tracking-[0.08em] transition-colors",
            locale === l ? "bg-signal-bg text-signal-fg" : "text-fg-3 hover:text-fg",
          )}
        >
          {l}
        </button>
      ))}
    </span>
  );
}

function DesktopShell() {
  const { pathname } = useLocation();
  const { light, toggle } = useTheme();
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
      <aside className="flex w-[196px] shrink-0 flex-col border-r border-edge bg-surface">
        <div className="flex h-[52px] items-center gap-2.5 border-b border-edge px-4">
          <span className="h-[9px] w-[9px] shrink-0 bg-signal" />
          <span className="font-display text-[15px] tracking-tight text-fg">NETSCAN</span>
        </div>

        <nav className="flex flex-1 flex-col py-2">
          {ROUTES.map((r) => {
            const on = r.to === active;
            return (
              <NavLink
                key={r.to}
                to={r.to}
                end={r.end}
                className={clsx(
                  "relative flex items-center gap-3 px-4 py-2.5 text-[13px] font-medium transition-colors",
                  on ? "text-fg" : "text-fg-2 hover:text-fg",
                )}
              >
                {on && <span className="absolute left-0 top-0 h-full w-[3px] bg-signal" />}
                <r.Icon size={15} className={on ? "text-signal" : "text-fg-3"} />
                {t(r.labelKey)}
                {r.to === "/approvals" && (s?.pending ?? 0) > 0 && (
                  <span className="tag tag-alert ml-auto !h-[15px] !px-1 !text-[9px]">{s?.pending}</span>
                )}
              </NavLink>
            );
          })}
        </nav>

        <div className="border-t border-edge p-3">
          {canWrite && (
            <button onClick={run} disabled={running} className="btn btn-primary w-full">
              {running ? t("shell.sweeping") : t("shell.sweep")}
            </button>
          )}
          {account && (
            <div className={clsx("flex items-center justify-between gap-2", canWrite && "mt-3")}>
              <span className="min-w-0 truncate">
                <span className="text-[12px] text-fg-2">{account.username}</span>
                <span className="mono ml-1.5 text-[9px] uppercase tracking-[0.08em] text-fg-3">
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
          <div className="mt-3 flex items-center justify-between gap-2">
            <button onClick={toggle} className="label transition-colors hover:text-fg">
              {light ? t("shell.dark") : t("shell.light")}
            </button>
            <LangSwitch />
          </div>
          <div className="mt-2 text-right">
            <span className="label">v0.1.0</span>
          </div>
        </div>
      </aside>

      {/* content */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* status strip */}
        <header className="flex h-[44px] shrink-0 items-center gap-7 border-b border-edge bg-surface px-6">
          <Vital k={t("shell.vital.subnet")} v={s?.subnet ?? "—"} />
          <Vital k={t("shell.vital.online")} v={s ? `${s.online}/${s.total}` : "—"} big />
          <Vital k={t("shell.vital.sweep")} v={cadence(iv)} />
          <Vital k={t("shell.vital.last")} v={running ? "···" : lastSweep(s?.last_scan ?? null, now)} tone={running ? "signal" : undefined} />
          <Vital k={t("shell.vital.clock")} v={hms(new Date(now))} className="ml-auto" />
        </header>

        <main className="relative min-h-0 flex-1 overflow-y-auto">
          {running && (
            <div className="pointer-events-none absolute inset-0 z-20 overflow-hidden">
              <div className="sweep-line" />
            </div>
          )}
          <div key={pathname} className="view-in mx-auto w-full max-w-[1320px] px-6 py-5">
            <p className="key mb-4 border-l-2 border-signal pl-2 !text-[11px] text-fg-2">{t(titleKeyOf(pathname))}</p>
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
  tone?: "signal";
  className?: string;
}) {
  return (
    <span className={clsx("flex items-baseline gap-2 whitespace-nowrap", className)}>
      <span className="key">{k}</span>
      <span
        className={clsx(
          "mono tnum",
          big ? "text-[14px] text-fg" : "text-[12px]",
          tone === "signal" ? "text-signal" : big ? "text-fg" : "text-fg-2",
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
  const { light, toggle } = useTheme();
  const { run, running } = useScan();
  const { s, iv } = useVitals();
  const now = useNow();
  const t = useT();
  const active = activeKey(pathname);
  const canWrite = useCanWrite();
  const logout = useLogout();

  return (
    <div className="flex min-h-screen flex-col bg-bg">
      <header className="sticky top-0 z-40 shrink-0 border-b border-edge bg-surface">
        <div className="flex h-[48px] items-center gap-2.5 px-4">
          <span className="h-2 w-2 shrink-0 bg-signal" />
          <span className="font-display text-[14px] tracking-tight text-fg">NETSCAN</span>
          <span className="mono ml-1 text-[13px] tnum text-fg">
            {s ? `${s.online}/${s.total}` : "—"}
          </span>
          <div className="ml-auto flex items-center gap-2">
            <LangSwitch />
            <button onClick={toggle} className="label">
              {light ? "DRK" : "LGT"}
            </button>
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
          <span className="text-signal">{s ? t("shell.onlineCount", { n: s.online }) : "—"}</span>
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
          <p className="key mb-3 border-l-2 border-signal pl-2 !text-[11px] text-fg-2">{t(titleKeyOf(pathname))}</p>
          <Outlet />
        </div>
      </main>

      {/* bottom tabs */}
      <nav className="fixed inset-x-0 bottom-0 z-40 flex items-stretch border-t border-edge bg-surface pb-[env(safe-area-inset-bottom)]">
        {ROUTES.map((r) => {
          const on = r.to === active;
          return (
            <NavLink
              key={r.to}
              to={r.to}
              end={r.end}
              className="relative flex min-h-[56px] flex-1 flex-col items-center justify-center gap-1 py-2"
            >
              <span className={clsx("absolute inset-x-0 top-0 h-[2px]", on ? "bg-signal" : "bg-transparent")} />
              <span className="relative">
                <r.Icon size={17} className={on ? "text-signal" : "text-fg-3"} />
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
