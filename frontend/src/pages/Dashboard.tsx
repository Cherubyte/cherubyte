import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { DeviceListView } from "../components/DeviceListView";
import { Sheet } from "../components/Sheet";
import { ArrowRight, Search } from "../components/Glyph";
import { Readout, Redacted } from "../components/ui";
import { useIsMobile } from "../hooks/useMediaQuery";
import { ipInCidr, timeAgo } from "../lib/format";
import { useT, type MessageKey } from "../i18n";
import type { Device, WanStatus } from "../api/types";

type Filter = "all" | "online" | "pending";
const FILTERS: { k: Filter; labelKey: MessageKey }[] = [
  { k: "all", labelKey: "dash.filter.all" },
  { k: "online", labelKey: "dash.filter.online" },
  { k: "pending", labelKey: "dash.filter.pending" },
];

function isToday(iso: string) {
  return new Date(iso).toDateString() === new Date().toDateString();
}

function primaryIp(d: Device): string {
  return (d.ips.find((i) => i.is_primary) ?? d.ips[0])?.address ?? "";
}

export function Dashboard() {
  const isMobile = useIsMobile();
  const t = useT();
  const [filter, setFilter] = useState<Filter>("all");
  const [q, setQ] = useState("");
  const [filterSheet, setFilterSheet] = useState(false);
  const [subnetTab, setSubnetTab] = useState("all");

  const stats = useQuery({ queryKey: ["stats"], queryFn: api.stats });
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const devices = useQuery({
    queryKey: ["devices"],
    queryFn: () => api.devices(),
    refetchInterval: 20000,
  });

  const all = devices.data ?? [];
  const newToday = all.filter((d) => isToday(d.first_seen)).length;
  const s = stats.data;

  const subnets = settings.data?.subnets ?? [];
  const hasOther =
    subnets.length > 0 &&
    all.some((d) => !subnets.some((sn) => ipInCidr(primaryIp(d), sn.cidr)));

  const rows = useMemo(() => {
    let list = all;
    if (filter === "online") list = list.filter((d) => d.is_online);
    if (filter === "pending") list = list.filter((d) => d.approval_status === "pending");
    if (subnets.length > 0 && subnetTab !== "all") {
      list =
        subnetTab === "other"
          ? list.filter((d) => !subnets.some((sn) => ipInCidr(primaryIp(d), sn.cidr)))
          : list.filter((d) => ipInCidr(primaryIp(d), subnetTab));
    }
    const n = q.toLowerCase().trim();
    if (n)
      list = list.filter(
        (d) =>
          d.display_name.toLowerCase().includes(n) ||
          (d.vendor ?? "").toLowerCase().includes(n) ||
          (d.os_family ?? "").toLowerCase().includes(n) ||
          d.ips.some((i) => i.address.includes(n)) ||
          d.macs.some((m) => m.address.toLowerCase().includes(n)),
      );
    return list;
  }, [all, filter, q, subnets, subnetTab]);

  const blind = !!s?.agents_stale && (s?.agents_configured ?? 0) > 0;

  return (
    <div className="space-y-6">
      {blind && (
        <Link
          to="/settings"
          className="panel panel-ruled flex items-start gap-3 p-4 transition-colors hover:bg-surface-2"
        >
          <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-alert" />
          <span className="min-w-0">
            <span className="font-display block text-[14px] leading-tight text-fg">
              {t("agents.blind", {
                ago: s?.last_report ? timeAgo(s.last_report, true) : "—",
              })}
            </span>
            <span className="mt-1 block text-[12px] leading-relaxed text-fg-2">
              {t("agents.blindDesc")}
            </span>
          </span>
          <span className="key ml-auto hidden shrink-0 items-center gap-1 self-center text-fg-2 sm:flex">
            {t("agents.checkLink")}
            <ArrowRight size={11} />
          </span>
        </Link>
      )}

      {/* overview */}
      <div className="panel overflow-hidden">
        <div className="flex items-center justify-between border-b border-edge px-5 py-2.5">
          <span className="key">{t("dash.plan")}</span>
          <span className="mono text-[11px] text-fg-3">{s?.subnet ?? "—"}</span>
        </div>
        <div className="flex flex-wrap items-stretch divide-x divide-edge">
          <div className="min-w-[180px] flex-[1.4] px-5 py-4">
            <Readout
              value={s?.online ?? "—"}
              unit={t("dash.totalUnit", { total: s?.total ?? "—" })}
              caption={t("dash.onlineNow")}
              size="xl"
            />
          </div>
          <div className="min-w-[110px] flex-1 px-5 py-4">
            <Readout value={s?.users_present ?? "—"} caption={t("dash.present")} size="sm" />
          </div>
          <div className="min-w-[110px] flex-1 px-5 py-4">
            <Readout
              value={newToday}
              caption={t("dash.newToday")}
              size="sm"
              tone={newToday > 0 ? "signal" : "default"}
            />
          </div>
          <div className="min-w-[220px] flex-[1.5] px-5 py-4">
            <WanReadout />
          </div>
          {(s?.pending ?? 0) > 0 && (
            <Link
              to="/approvals"
              className="group flex min-w-[150px] flex-1 items-center gap-2.5 bg-alert px-5 text-alert-fg transition-opacity hover:opacity-90"
            >
              <span className="font-display text-[24px] leading-none tnum">{s?.pending}</span>
              <span className="text-[12px] font-medium">{t("dash.review")}</span>
              <ArrowRight size={12} className="ml-auto" />
            </Link>
          )}
        </div>
      </div>

      {/* subnet tabs */}
      {subnets.length > 0 && (
        <div className="-mb-2 flex gap-1 overflow-x-auto border-b border-edge">
          {[
            { k: "all", label: t("dash.tab.all") },
            ...subnets.map((sn) => ({ k: sn.cidr, label: sn.label || sn.cidr })),
            ...(hasOther ? [{ k: "other", label: t("dash.tab.other") }] : []),
          ].map((tab) => (
            <button
              key={tab.k}
              onClick={() => setSubnetTab(tab.k)}
              className={clsx(
                "shrink-0 whitespace-nowrap border-b-2 px-3 py-2 text-[12.5px] font-medium transition-colors",
                subnetTab === tab.k
                  ? "border-fg text-fg"
                  : "border-transparent text-fg-3 hover:text-fg",
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
      )}

      {/* toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[200px] flex-1">
          <Search
            size={14}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-fg-3"
          />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={isMobile ? t("dash.searchShort") : t("dash.search")}
            className="input pl-9"
          />
        </div>
        {isMobile ? (
          <button onClick={() => setFilterSheet(true)} className="btn btn-secondary btn-sm">
            {t(FILTERS.find((f) => f.k === filter)!.labelKey)}
          </button>
        ) : (
          <Segmented
            value={filter}
            onChange={(v) => setFilter(v as Filter)}
            options={FILTERS.map((f) => ({
              k: f.k,
              label: f.k === "all" ? `${t(f.labelKey)} ${all.length}` : t(f.labelKey),
            }))}
          />
        )}
      </div>

      <DeviceListView
        devices={rows}
        loading={devices.isLoading}
        emptyKey={q || filter !== "all" ? "dash.empty.noResults" : "dash.empty.noDevices"}
      />

      <Sheet open={filterSheet} onClose={() => setFilterSheet(false)} title={t("dash.filterSheet")}>
        <div className="space-y-1">
          {FILTERS.map((f) => (
            <button
              key={f.k}
              onClick={() => {
                setFilter(f.k);
                setFilterSheet(false);
              }}
              className={clsx(
                "flex w-full items-center justify-between rounded-lg px-3 py-3.5 text-left",
                filter === f.k ? "bg-surface-2 text-fg" : "text-fg-3",
              )}
            >
              <span className="font-display text-[14px]">{t(f.labelKey)}</span>
              {filter === f.k && <span className="h-2 w-2 rounded-full bg-fg" />}
            </button>
          ))}
        </div>
      </Sheet>
    </div>
  );
}

export function Segmented({
  value,
  onChange,
  options,
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { k: string; label: string }[];
  className?: string;
}) {
  return (
    <div
      className={clsx(
        "flex shrink-0 gap-0.5 rounded-lg border border-edge-2 bg-surface-2 p-0.5 text-[12.5px] font-medium leading-none",
        className,
      )}
    >
      {options.map((o) => (
        <button
          key={o.k}
          onClick={() => onChange(o.k)}
          className={clsx(
            "rounded-md px-3 py-1.5 transition-colors",
            value === o.k ? "bg-surface text-fg shadow-e1" : "text-fg-2 hover:text-fg",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Internet reachability: current state, uptime, and a latency sparkline. */
function WanReadout() {
  const t = useT();
  const wan = useQuery({
    queryKey: ["wan"],
    queryFn: () => api.wan(24),
    refetchInterval: 60_000,
  });
  const d = wan.data;
  if (!d || !d.samples) return null;

  const tone = d.online === false ? "alert" : "default";
  const uptime = d.uptime === null ? "—" : `${(d.uptime * 100).toFixed(1)}%`;

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-end gap-3">
        <Readout
          value={d.online === false ? t("dash.wan.down") : uptime}
          caption={
            d.online === false
              ? t("dash.wan.label", { target: d.target })
              : t("dash.wan.label24h")
          }
          size="sm"
          tone={tone}
        />
        <Sparkline points={d.points} />
      </div>
      {d.public_ip && (
        <div className="flex items-center gap-2">
          <span className="key">{t("dash.wan.ip")}</span>
          <Redacted value={d.public_ip} className="text-[12px]" />
        </div>
      )}
    </div>
  );
}

function Sparkline({ points }: { points: WanStatus["points"] }) {
  const t = useT();
  const W = 120;
  const H = 26;
  const withMs = points.filter((p) => p.ms !== null);
  if (withMs.length < 2) return null;
  const max = Math.max(...withMs.map((p) => p.ms as number), 1);
  const x = (i: number) => (i / Math.max(1, points.length - 1)) * W;
  const y = (ms: number) => H - (ms / max) * (H - 3) - 1;

  const paths: string[] = [];
  let current = "";
  points.forEach((p, i) => {
    if (p.ms === null) {
      if (current) paths.push(current);
      current = "";
      return;
    }
    current += `${current ? "L" : "M"}${x(i).toFixed(1)} ${y(p.ms).toFixed(1)}`;
  });
  if (current) paths.push(current);

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-[26px] w-[120px] shrink-0"
      role="img"
      aria-label={t("dash.wan.spark", { ms: Math.round(max) })}
    >
      {points.map((p, i) =>
        p.ok ? null : (
          <rect key={i} x={x(i)} y={0} width={Math.max(1, W / points.length)} height={H} fill="rgb(var(--alert))" opacity={0.22} />
        ),
      )}
      {paths.map((dPath, i) => (
        <path key={i} d={dPath} fill="none" stroke="rgb(var(--fg-2))" strokeWidth={1.25} />
      ))}
    </svg>
  );
}
