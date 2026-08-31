import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { useId, useMemo, useState } from "react";
import { motion, useReducedMotion } from "../lib/motion";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { EventItem, EventLevel } from "../api/types";
import { EmptyState, SkeletonRows } from "../components/ui";
import {
  Check,
  CornerDown,
  Globe,
  Merge,
  Plug,
  Radar,
  Search,
  Shield,
  Wave,
} from "../components/Glyph";
import { hms, ymd } from "../lib/format";
import { useT, type MessageKey } from "../i18n";

const LEVELS: { k: EventLevel | "all"; labelKey: MessageKey }[] = [
  { k: "all", labelKey: "events.level.all" },
  { k: "alert", labelKey: "events.level.alert" },
  { k: "warning", labelKey: "events.level.warning" },
  { k: "success", labelKey: "events.level.success" },
  { k: "info", labelKey: "events.level.info" },
];

type IconType = (p: { size?: number; className?: string }) => JSX.Element;

const CATEGORIES: { k: string; Icon: IconType; labelKey: MessageKey }[] = [
  { k: "discovery", Icon: Radar, labelKey: "events.cat.discovery" },
  { k: "presence", Icon: Wave, labelKey: "events.cat.presence" },
  { k: "ports", Icon: Plug, labelKey: "events.cat.ports" },
  { k: "security", Icon: Shield, labelKey: "events.cat.security" },
  { k: "scan", Icon: Search, labelKey: "events.cat.scan" },
  { k: "wan", Icon: Globe, labelKey: "events.cat.wan" },
  { k: "merge", Icon: Merge, labelKey: "events.cat.merge" },
  { k: "approval", Icon: Check, labelKey: "events.cat.approval" },
];

const LEVEL_MARK: Record<EventLevel, string> = {
  info: "bg-fg-3",
  success: "bg-fg",
  warning: "bg-alert",
  alert: "bg-alert",
};

function dayLabel(iso: string, t: (k: MessageKey) => string) {
  const d = new Date(iso);
  const now = new Date();
  const y = new Date(now.getTime() - 86400000);
  if (d.toDateString() === now.toDateString()) return `${ymd(d)} · ${t("events.today")}`;
  if (d.toDateString() === y.toDateString()) return `${ymd(d)} · ${t("events.yesterday")}`;
  return ymd(d);
}

export function Events() {
  const t = useT();
  const [level, setLevel] = useState<EventLevel | "all">("all");
  const [category, setCategory] = useState<string>("all");
  const events = useQuery({
    queryKey: ["events", level, category],
    queryFn: () =>
      api.events({
        ...(level === "all" ? {} : { level }),
        ...(category === "all" ? {} : { category }),
      }),
    refetchInterval: 10000,
  });

  const groups = useMemo(() => {
    const g: Record<string, EventItem[]> = {};
    for (const e of (events.data ?? []).slice(0, 150)) (g[dayLabel(e.timestamp, t)] ??= []).push(e);
    return Object.entries(g);
  }, [events.data, t]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap gap-2">
        <Chips
          options={LEVELS.map((l) => ({ k: l.k, label: t(l.labelKey) }))}
          value={level}
          onChange={(k) => setLevel(k as EventLevel | "all")}
        />
        <Chips
          options={[
            { k: "all", label: t("events.cat.all") },
            ...CATEGORIES.map((c) => ({ k: c.k, label: t(c.labelKey) })),
          ]}
          value={category}
          onChange={setCategory}
        />
      </div>

      {events.isLoading && <SkeletonRows rows={8} />}

      {!events.isLoading && groups.length === 0 && <EmptyState title={t("events.empty")} />}

      {groups.map(([day, items]) => (
        <section key={day}>
          <div className="mb-2.5 flex items-center gap-3">
            <span className="key">{day}</span>
            <span className="h-px flex-1 bg-edge" />
            <span className="key">{items.length}</span>
          </div>
          <div className="panel divide-y divide-edge overflow-hidden">
            {items.map((e) => (
              <Row key={e.id} e={e} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function Chips({
  options,
  value,
  onChange,
}: {
  options: { k: string; label: string }[];
  value: string;
  onChange: (k: string) => void;
}) {
  const reduced = useReducedMotion();
  const thumb = useId();
  return (
    <div className="flex gap-0.5 overflow-x-auto rounded-[10px] bg-fg/[0.06] p-0.5 text-[12.5px] font-medium">
      {options.map((o) => {
        const on = value === o.k;
        return (
          <button
            key={o.k}
            onClick={() => onChange(o.k)}
            className="relative shrink-0 rounded-[7px] px-3 py-1.5"
          >
            {on && (
              <motion.span
                layoutId={thumb}
                className="absolute inset-0 rounded-[7px] bg-surface shadow-e1"
                transition={reduced ? { duration: 0 } : { type: "spring", bounce: 0.15, duration: 0.32 }}
              />
            )}
            <span className={clsx("relative z-10 transition-colors", on ? "text-fg" : "text-fg-2 hover:text-fg")}>
              {o.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}

function Row({ e }: { e: EventItem }) {
  const t = useT();
  const meta = CATEGORIES.find((c) => c.k === e.category);
  const Icon = meta?.Icon;
  return (
    <div className="flex items-start gap-3 px-4 py-3">
      <span className={clsx("mt-1.5 h-2 w-2 shrink-0 rounded-full", LEVEL_MARK[e.level])} />
      <span className="mt-px flex w-16 shrink-0 items-center gap-1.5 text-fg-3">
        {Icon ? <Icon size={12} /> : <span className="h-[12px] w-[12px]" />}
        <span className="mono text-[10.5px] tabular-nums">{hms(e.timestamp)}</span>
      </span>
      <span className="key hidden w-24 shrink-0 pt-0.5 !text-[10px] sm:block">
        {meta ? t(meta.labelKey) : e.category}
      </span>
      <span className="min-w-0 flex-1 text-[12.5px] leading-snug text-fg">{e.message}</span>
      {e.device_id && (
        <Link
          to={`/devices/${e.device_id}`}
          title={t("events.openHost")}
          className="flex shrink-0 items-center pt-px text-fg-3 transition-colors hover:text-fg"
        >
          <CornerDown size={12} />
        </Link>
      )}
    </div>
  );
}
