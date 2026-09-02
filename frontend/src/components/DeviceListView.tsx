import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Device } from "../api/types";
import { useNow } from "../hooks/useNow";
import { deviceTypeLabel, stringHsl, timeAgo } from "../lib/format";
import { useT, type MessageKey } from "../i18n";
import { TypeCode, useBrandLogos, useOsLogos } from "./TypeCode";
import { EmptyState, SkeletonRows } from "./ui";
import { ArrowUpRight, CaretDown, DeviceTypeIcon, PeopleIcon, Trash } from "./Glyph";
import { useToast } from "./Toaster";

type SortKey = "name" | "ip" | "type" | "seen";

/* one grid track shared by the header and every row */
const GRID =
  "grid-cols-[10px_40px_minmax(0,1fr)_auto] " +
  "sm:grid-cols-[10px_40px_minmax(0,1fr)_128px_72px] " +
  "md:grid-cols-[10px_40px_minmax(0,1fr)_128px_128px_136px_72px] " +
  "lg:grid-cols-[10px_40px_minmax(0,1fr)_128px_128px_136px_92px_72px]";

function ipNum(d: Device) {
  const ip = (d.ips.find((i) => i.is_primary) ?? d.ips[0])?.address ?? "";
  const p = ip.split(".").map(Number);
  if (p.length !== 4 || p.some(Number.isNaN)) return 2 ** 32;
  return ((p[0] * 256 + p[1]) * 256 + p[2]) * 256 + p[3];
}

export function DeviceListView({
  devices,
  loading,
  emptyKey = "list.empty.title",
}: {
  devices: Device[];
  loading?: boolean;
  emptyKey?: MessageKey;
}) {
  const nav = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const t = useT();
  const logos = useBrandLogos();
  const osLogos = useOsLogos();
  useNow();
  const [sort, setSort] = useState<{ k: SortKey; dir: 1 | -1 }>({ k: "ip", dir: 1 });
  const prevOnline = useRef<Map<number, boolean>>(new Map());

  const del = useMutation({
    mutationFn: (id: number) => api.deleteDevice(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["devices"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      toast({ tone: "success", title: "device.deleted" });
    },
  });

  const sorted = useMemo(() => {
    const arr = [...devices];
    arr.sort((a, b) => {
      let r = 0;
      if (sort.k === "name") r = a.display_name.localeCompare(b.display_name);
      else if (sort.k === "ip") r = ipNum(a) - ipNum(b);
      else if (sort.k === "type") r = a.device_type.localeCompare(b.device_type);
      else r = +new Date(b.last_seen) - +new Date(a.last_seen);
      return r * sort.dir;
    });
    return arr;
  }, [devices, sort]);

  const online = sorted.filter((d) => d.is_online);
  const offline = sorted.filter((d) => !d.is_online);
  const toggleSort = (k: SortKey) =>
    setSort((s) => (s.k === k ? { k, dir: (s.dir * -1) as 1 | -1 } : { k, dir: 1 }));

  if (loading) return <SkeletonRows rows={8} />;
  if (devices.length === 0)
    return <EmptyState title={t(emptyKey)} description={t("list.empty.desc")} />;

  const Head = ({ k, children, className }: { k?: SortKey; children: React.ReactNode; className?: string }) => (
    <button
      type="button"
      disabled={!k}
      onClick={() => k && toggleSort(k)}
      className={clsx(
        "key flex items-center gap-1 disabled:cursor-default",
        k && sort.k === k && "text-fg",
        k && "hover:text-fg",
        className,
      )}
    >
      {children}
      {k && sort.k === k && <CaretDown size={9} className={sort.dir === -1 ? "rotate-180" : ""} />}
    </button>
  );

  const group = (list: Device[], dim?: boolean) => (
    <div className="panel divide-y divide-edge overflow-hidden">
      {list.map((d) => {
        const flash = !dim && prevOnline.current.get(d.id) === false ? "row-flash" : "";
        prevOnline.current.set(d.id, !dim);
        return <Row key={d.id} d={d} logos={logos} osLogos={osLogos} nav={nav} del={del} dim={dim} flash={flash} />;
      })}
    </div>
  );

  // the last column is "Joined" (when this device came online) for the online
  // table, "Seen" (how long ago it was last seen) for the offline one
  const header = (lastKey: SortKey, lastLabel: MessageKey) => (
    <div className={clsx("hidden items-center gap-3 px-4 pb-2 sm:grid", GRID)}>
      <span />
      <span />
      <Head k="name">{t("list.col.host")}</Head>
      <Head k="ip">{t("list.col.address")}</Head>
      <span className="key hidden md:block">{t("list.col.user")}</span>
      <Head k="type" className="hidden md:flex">{t("list.col.type")}</Head>
      <span className="key hidden lg:block">{t("list.col.os")}</span>
      <Head k={lastKey} className="justify-end">{t(lastLabel)}</Head>
    </div>
  );

  return (
    <div className="relative">
      {online.length > 0 && (
        <>
          {header("seen", "list.col.joined")}
          {group(online)}
        </>
      )}

      {offline.length > 0 && (
        <>
          <div className="mb-2.5 flex items-center gap-3" style={{ marginTop: online.length > 0 ? "1.75rem" : 0 }}>
            <span className="key">{t("list.offlineCount", { n: offline.length })}</span>
            <span className="h-px flex-1 bg-edge" />
          </div>
          {header("seen", "list.col.seen")}
          {group(offline, true)}
        </>
      )}
    </div>
  );
}

function Row({
  d,
  logos,
  osLogos,
  nav,
  del,
  dim,
  flash,
}: {
  d: Device;
  logos: Map<string, string>;
  osLogos: Map<string, string>;
  nav: (to: string) => void;
  del: { mutate: (id: number) => void };
  dim?: boolean;
  flash?: string;
}) {
  const t = useT();
  const ip = (d.ips.find((i) => i.is_primary) ?? d.ips[0])?.address ?? "—";
  const pending = d.approval_status === "pending";
  const sub = !d.name && d.hostname && d.hostname !== d.display_name ? d.hostname : d.model;

  return (
    <div
      onClick={() => nav(`/devices/${d.id}`)}
      className={clsx(
        "group relative grid h-[64px] cursor-pointer items-center gap-3 px-4 transition-colors sm:h-[56px]",
        GRID,
        "hover:bg-surface-2",
        flash,
      )}
    >
      {/* status mark */}
      <span className="justify-self-center">
        <span
          className={clsx(
            "signal-mark",
            pending ? "signal-mark--alert" : d.is_online ? "signal-mark--on" : "signal-mark--off",
          )}
          style={{ ["--m" as string]: "9px" }}
        />
      </span>

      {/* device image */}
      <TypeCode device={d} logos={logos} osLogos={osLogos} size={40} />

      {/* name + sub */}
      <div className="min-w-0 overflow-hidden">
        <div className="flex items-center gap-2">
          <span className={clsx("truncate text-[13.5px] font-medium", dim ? "text-fg-2" : "text-fg")}>
            {d.display_name}
          </span>
          {d.user && d.counts_for_presence && (
            <span
              className="hidden shrink-0 text-fg-3 sm:inline-block"
              title={t("device.countsForPresence")}
            >
              <PeopleIcon size={11} />
            </span>
          )}
          {pending && (
            <span className="hidden shrink-0 text-[10px] font-medium text-alert sm:inline">
              {t("list.unreviewed")}
            </span>
          )}
          {d.tags.slice(0, 2).map((g) => (
            <span key={g} className="hidden shrink-0 rounded bg-fg/[0.07] px-1.5 py-0.5 text-[10px] text-fg-3 sm:inline">
              {g}
            </span>
          ))}
        </div>
        <div className="mono mt-0.5 truncate text-[10.5px] text-fg-3 sm:hidden">
          {ip} · {deviceTypeLabel(d.device_type)}
          {d.os_family ? ` · ${d.os_family}` : ""} ·{" "}
          <span className={d.is_online ? "text-fg-2" : ""}>
            {d.is_online ? t("common.online") : timeAgo(d.last_seen, true)}
          </span>
        </div>
        {sub && (
          <div className="mono mt-0.5 hidden truncate text-[10.5px] text-fg-3 sm:block">{sub}</div>
        )}
      </div>

      {/* address — desktop */}
      <span className="mono hidden truncate text-[11.5px] text-fg-2 sm:block">
        {ip}
        {d.ips.length > 1 && <span className="ml-1 text-fg-3">+{d.ips.length - 1}</span>}
      </span>

      {/* user — md+ */}
      <span className="hidden items-center gap-1.5 md:flex">
        {d.user ? (
          <>
            <span
              className="h-[7px] w-[7px] shrink-0 rounded-full"
              style={{ background: stringHsl(d.user.name) }}
            />
            <span className="truncate text-[11.5px] text-fg-2">{d.user.name}</span>
          </>
        ) : (
          <span className="text-[11.5px] text-fg-3">—</span>
        )}
      </span>

      {/* type — md+ */}
      <span className="hidden items-center gap-1.5 md:flex">
        <DeviceTypeIcon type={d.device_type} size={14} className="shrink-0 text-fg-3" />
        <span className="truncate text-[11.5px] text-fg-2">{deviceTypeLabel(d.device_type)}</span>
      </span>

      {/* os — lg+ */}
      <span className="mono hidden items-center gap-1.5 truncate text-[10px] text-fg-3 lg:flex">
        {d.os_family && osLogos.get(d.os_family.toLowerCase()) && (
          <img src={osLogos.get(d.os_family.toLowerCase())} alt="" className="h-3.5 w-3.5 shrink-0 object-contain" />
        )}
        <span className="truncate">{d.os_family ?? "—"}</span>
      </span>

      {/* joined (online) / seen (offline) — desktop */}
      <span
        className={clsx(
          "mono hidden justify-self-end text-[10.5px] sm:block",
          d.is_online ? "text-fg" : "text-fg-3",
        )}
      >
        {d.is_online
          ? timeAgo(d.online_since ?? d.first_seen, true)
          : timeAgo(d.last_seen, true)}
      </span>

      {/* hover actions — desktop */}
      <span className="pointer-events-none absolute right-3 top-1/2 hidden -translate-y-1/2 items-center gap-3 bg-surface-2 pl-4 opacity-0 group-hover:opacity-100 sm:flex">
        <button
          onClick={(e) => {
            e.stopPropagation();
            if (confirm(t("list.deleteConfirm", { name: d.display_name }))) del.mutate(d.id);
          }}
          className="pointer-events-auto text-fg-3 hover:text-alert"
        >
          <Trash size={13} />
        </button>
        <span className="key flex items-center gap-1 text-fg">
          {t("common.open")} <ArrowUpRight size={11} />
        </span>
      </span>

      {/* chevron — mobile */}
      <span className="pointer-events-none justify-self-end text-fg-3 sm:hidden">
        <ArrowUpRight size={13} />
      </span>
    </div>
  );
}
