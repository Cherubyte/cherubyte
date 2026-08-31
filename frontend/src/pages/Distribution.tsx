import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { DeviceType, TimelinePoint } from "../api/types";
import { EmptyState, QueryState, Readout, SectionHeader } from "../components/ui";
import { Image, Close, DeviceTypeIcon } from "../components/Glyph";
import { useToast } from "../components/Toaster";
import { deviceTypeLabel } from "../lib/format";
import { useT } from "../i18n";

const MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";

export function Distribution() {
  const t = useT();
  const stats = useQuery({ queryKey: ["stats"], queryFn: api.stats });
  const timeline = useQuery({ queryKey: ["stats", "timeline"], queryFn: () => api.timeline(30) });
  const byType = useQuery({ queryKey: ["stats", "type"], queryFn: api.byType });
  const byBrand = useQuery({ queryKey: ["stats", "brand"], queryFn: api.byBrand });
  const s = stats.data;

  const totalTyped = (byType.data ?? []).reduce((n, r) => n + r.count, 0) || 1;

  return (
    <div className="space-y-5">
      {/* figures */}
      <div className="panel flex flex-wrap items-end gap-x-10 gap-y-4 px-5 py-4">
        <Readout value={s?.total ?? "—"} caption={t("stats.devices")} size="xl" />
        <Readout value={s?.online ?? "—"} caption={t("stats.onlineNow")} size="sm" />
        <Readout value={s?.approved ?? "—"} caption={t("stats.approved")} size="sm" />
        <Readout value={s?.pending ?? "—"} caption={t("stats.pending")} size="sm" tone={s?.pending ? "alert" : "default"} />
      </div>

      {/* timeline */}
      <section className="panel p-5">
        <SectionHeader title={t("stats.newDevices")} sub={t("stats.newDevicesSub")} />
        {timeline.data ? <Plot series={timeline.data.series} /> : <QueryState q={timeline} />}
      </section>

      <div className="grid gap-3 lg:grid-cols-3">
        <section className="panel p-5">
          <SectionHeader title={t("stats.byType")} sub={String((byType.data ?? []).length)} />
          {byType.data ? (
            <TypeBars rows={byType.data} total={totalTyped} />
          ) : (
            <QueryState q={byType} />
          )}
        </section>

        <section className="panel p-5">
          <SectionHeader title={t("stats.byBrand")} sub={t("stats.assignLogoHint")} />
          <LogoBars kind="brands" online={byBrand.data} />
        </section>

        <section className="panel p-5">
          <SectionHeader title={t("stats.bySystem")} sub={t("stats.assignLogoHint")} />
          <LogoBars kind="os" />
        </section>
      </div>
    </div>
  );
}

/* ── timeline: daily bars + cumulative line ─────────────────────────── */
function Plot({ series }: { series: TimelinePoint[] }) {
  const t = useT();
  const [hover, setHover] = useState<number | null>(null);
  const W = 960;
  const H = 124;
  const pad = { l: 30, r: 34, t: 10, b: 20 };
  const iw = W - pad.l - pad.r;
  const ih = H - pad.t - pad.b;
  const maxNew = Math.max(3, ...series.map((p) => p.new_devices));
  const maxTot = Math.max(1, ...series.map((p) => p.total));
  const x = (i: number) => pad.l + (i / Math.max(1, series.length - 1)) * iw;
  const yNew = (v: number) => pad.t + ih - (v / maxNew) * ih;
  const yTot = (v: number) => pad.t + ih - (v / maxTot) * ih;
  const bw = Math.max(2, iw / series.length - 3);
  const linePath = series.map((p, i) => `${i ? "L" : "M"}${x(i)} ${yTot(p.total)}`).join(" ");
  const h = hover != null ? series[hover] : null;

  return (
    <div className="overflow-x-auto">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full min-w-[600px]"
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          const px = ((e.clientX - r.left) / r.width) * W;
          const i = Math.round(((px - pad.l) / iw) * (series.length - 1));
          setHover(Math.max(0, Math.min(series.length - 1, i)));
        }}
      >
        {[0, Math.round(maxNew / 2), maxNew].map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={W - pad.r} y1={yNew(v)} y2={yNew(v)} stroke="rgb(var(--edge))" />
            <text x={pad.l - 6} y={yNew(v) + 3} textAnchor="end" fontSize="8" fontFamily={MONO} fill="rgb(var(--fg-3))">
              {v}
            </text>
          </g>
        ))}
        <text x={W - pad.r + 6} y={pad.t + 3} fontSize="8" fontFamily={MONO} fill="rgb(var(--fg-3))">
          {maxTot}
        </text>
        <line x1={pad.l} x2={W - pad.r} y1={pad.t + ih} y2={pad.t + ih} stroke="rgb(var(--edge-2))" strokeWidth={1.5} />

        {series.map((p, i) => (
          <rect
            key={i}
            x={x(i) - bw / 2}
            y={yNew(p.new_devices)}
            width={bw}
            height={pad.t + ih - yNew(p.new_devices)}
            rx={1}
            fill={hover === i ? "rgb(var(--fg))" : "rgb(var(--fg-3))"}
          />
        ))}

        <path d={linePath} fill="none" stroke="rgb(var(--fg))" strokeWidth={1.5} />

        {series.map((p, i) =>
          i % 5 === 0 ? (
            <text key={i} x={x(i)} y={H - 6} fontSize="8" fontFamily={MONO} fill="rgb(var(--fg-3))" textAnchor="middle">
              {p.date.slice(5)}
            </text>
          ) : null,
        )}

        {hover != null && (
          <>
            <line x1={x(hover)} x2={x(hover)} y1={pad.t} y2={pad.t + ih} stroke="rgb(var(--fg))" strokeDasharray="2 2" />
            <circle cx={x(hover)} cy={yTot(series[hover].total)} r={2.5} fill="rgb(var(--fg))" />
          </>
        )}
      </svg>
      <div className="mono mt-1 h-4 text-[10px] text-fg-3">
        {h && (
          <span>
            {h.date} · <b className="text-fg">{h.new_devices}</b> {t("stats.plotNew")} ·{" "}
            {t("stats.plotTotal")} <b className="text-fg">{h.total}</b>
          </span>
        )}
      </div>
    </div>
  );
}

/* ── by type — icon + label + bar ──────────────────────────────────── */
function TypeBars({ rows, total }: { rows: { type: string; count: number }[]; total: number }) {
  const t = useT();
  if (rows.length === 0) return <EmptyState title={t("stats.noData")} />;
  const max = Math.max(1, ...rows.map((r) => r.count));
  return (
    <div className="space-y-2.5">
      {rows.map((r) => (
        <div key={r.type} className="grid grid-cols-[16px_88px_1fr_46px] items-center gap-2.5">
          <DeviceTypeIcon type={r.type as DeviceType} size={13} className="text-fg-3" />
          <span className="truncate text-[12px] text-fg-2">{deviceTypeLabel(r.type)}</span>
          <div className="h-2 overflow-hidden rounded-full bg-surface-2">
            <div className="h-full rounded-full bg-fg" style={{ width: `${(r.count / max) * 100}%` }} />
          </div>
          <span className="mono text-right text-[11px] text-fg-2">
            {r.count}
            <span className="ml-1 text-fg-3">{Math.round((r.count / total) * 100)}%</span>
          </span>
        </div>
      ))}
    </div>
  );
}

function LogoBars({
  kind,
  online,
}: {
  kind: "brands" | "os";
  online?: { brand: string; online: number }[];
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const t = useT();
  const key = kind === "brands" ? "brands" : "os-logos";
  const list = useQuery({ queryKey: [key], queryFn: kind === "brands" ? api.brands : api.osLogos });
  const fileRef = useRef<HTMLInputElement>(null);
  const [target, setTarget] = useState<string | null>(null);
  const onlineMap = useMemo(() => {
    const m = new Map<string, number>();
    for (const b of online ?? []) m.set(b.brand.toLowerCase(), b.online);
    return m;
  }, [online]);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: [key] });
    qc.invalidateQueries({ queryKey: ["devices"] });
  };
  const upload = useMutation({
    mutationFn: ({ name, file }: { name: string; file: File }) => api.uploadLogo(kind, name, file),
    onSuccess: () => {
      invalidate();
      toast({ tone: "success", title: "logo.set" });
    },
  });
  const clear = useMutation({ mutationFn: (name: string) => api.deleteLogo(kind, name), onSuccess: invalidate });

  const rows = useMemo(
    () => (list.data ?? []).filter((b) => b.device_count > 0 && b.name !== "Desconhecido"),
    [list.data],
  );
  const max = Math.max(1, ...rows.map((b) => b.device_count));
  if (!list.data) return <QueryState q={list} />;
  if (rows.length === 0) return <EmptyState title={t("stats.noData")} />;

  return (
    <div className="space-y-2.5">
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f && target) upload.mutate({ name: target, file: f });
          e.target.value = "";
          setTarget(null);
        }}
      />
      {rows.map((b) => {
        const on = onlineMap.get(b.name.toLowerCase());
        return (
          <div key={b.name} className="group grid grid-cols-[22px_84px_1fr_44px] items-center gap-2.5">
            <button
              onClick={() => {
                setTarget(b.name);
                fileRef.current?.click();
              }}
              title={t("stats.assignLogo")}
              className="grid h-[22px] w-[22px] place-items-center overflow-hidden rounded-md bg-surface-2 text-fg-3 hover:text-fg"
            >
              {b.logo_url ? (
                <img src={b.logo_url} alt="" className="h-full w-full object-contain p-px" />
              ) : (
                <Image size={10} />
              )}
            </button>
            <span className="truncate text-[11.5px] text-fg-2">{b.name}</span>
            <div className="relative h-2 overflow-hidden rounded-full bg-surface-2">
              <div className="absolute inset-y-0 left-0 rounded-full bg-fg-3" style={{ width: `${(b.device_count / max) * 100}%` }} />
              {on != null && on > 0 && (
                <div className="absolute inset-y-0 left-0 rounded-full bg-fg" style={{ width: `${(on / max) * 100}%` }} />
              )}
            </div>
            <div className="flex items-center justify-end gap-1">
              <span className="mono text-[11px] text-fg-2">{b.device_count}</span>
              {b.logo_url && (
                <button
                  onClick={() => clear.mutate(b.name)}
                  className="text-fg-3 opacity-0 hover:text-alert group-hover:opacity-100"
                >
                  <Close size={10} />
                </button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
