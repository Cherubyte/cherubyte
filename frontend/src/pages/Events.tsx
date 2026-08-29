import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { EventItem, EventLevel } from "../api/types";
import { EmptyState, LevelDot, SkeletonRows } from "../components/ui";
import { CornerDown } from "../components/Glyph";
import { hms, ymd } from "../lib/format";
import { useT, type MessageKey } from "../i18n";

const LEVELS: { k: EventLevel | "all"; labelKey: MessageKey }[] = [
  { k: "all", labelKey: "events.level.all" },
  { k: "alert", labelKey: "events.level.alert" },
  { k: "warning", labelKey: "events.level.warning" },
  { k: "success", labelKey: "events.level.success" },
  { k: "info", labelKey: "events.level.info" },
];

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
  const events = useQuery({
    queryKey: ["events", level],
    queryFn: () => api.events(level === "all" ? undefined : { level }),
    refetchInterval: 10000,
  });

  const groups = useMemo(() => {
    const g: Record<string, EventItem[]> = {};
    for (const e of (events.data ?? []).slice(0, 100)) (g[dayLabel(e.timestamp, t)] ??= []).push(e);
    return Object.entries(g);
  }, [events.data, t]);

  return (
    <div className="space-y-5">
      <div className="flex gap-px overflow-x-auto rounded-[3px] border border-edge-2 text-[12px] font-medium">
        {LEVELS.map((l, i) => (
          <button
            key={l.k}
            onClick={() => setLevel(l.k)}
            className={clsx(
              "shrink-0 px-3.5 py-2 transition-colors",
              i > 0 && "border-l border-edge-2",
              level === l.k ? "bg-signal-bg text-signal-fg" : "text-fg-2 hover:text-fg",
            )}
          >
            {t(l.labelKey)}
          </button>
        ))}
      </div>

      {events.isLoading && <SkeletonRows rows={8} />}

      {!events.isLoading && groups.length === 0 && <EmptyState title={t("events.empty")} />}

      {groups.map(([day, items]) => (
        <section key={day}>
          <div className="mb-1.5 flex items-center gap-3">
            <span className="key">{day}</span>
            <span className="h-[2px] flex-1 bg-edge" />
            <span className="key">{items.length}</span>
          </div>
          <div className="space-y-px">
            {items.map((e) => (
              <div key={e.id} className="flex items-stretch gap-3 bg-surface px-3 py-2.5">
                <LevelDot level={e.level} />
                <span className="mono w-16 shrink-0 pt-px text-[10.5px] text-fg-3">
                  {hms(e.timestamp)}
                </span>
                <span className="key hidden w-28 shrink-0 pt-0.5 !text-[9px] sm:block">
                  {e.category}
                </span>
                <span className="min-w-0 flex-1 text-[12.5px] leading-snug text-fg">
                  {e.message}
                </span>
                {e.device_id && (
                  <Link
                    to={`/devices/${e.device_id}`}
                    className="mono flex shrink-0 items-center gap-1 pt-px text-[10px] text-fg-3 hover:text-signal"
                  >
                    <CornerDown size={11} />
                    {String(e.device_id).padStart(3, "0")}
                  </Link>
                )}
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
