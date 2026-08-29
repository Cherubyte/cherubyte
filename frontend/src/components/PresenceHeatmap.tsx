import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { api } from "../api/client";
import { intlLocale } from "../i18n/locale";
import { useT } from "../i18n";
import { Skeleton } from "./ui";

/**
 * Presence as a chart-recorder strip: one row per local calendar day (oldest
 * first, today last), an orange segment for every hour the person had at least
 * one presence device online. Gridlines sit behind the fill so segments stay
 * solid. A hairline marks "now" on today's row.
 */
export function PresenceHeatmap({
  userId,
  days = 7,
  cell = 12,
}: {
  userId: number;
  days?: number;
  cell?: number;
}) {
  const t = useT();
  const grid = useQuery({
    queryKey: ["users", userId, "presence", days],
    queryFn: () => api.userPresence(userId, days),
    refetchInterval: 60000,
  });

  if (grid.isError)
    return (
      <div className="border-y-2 border-alert bg-surface px-2 py-2">
        <span className="key text-alert">{t("common.signalLost")}</span>
      </div>
    );
  if (!grid.data)
    return <Skeleton className="w-full" style={{ height: (cell + 3) * days + 20 }} />;

  const { start, cells } = grid.data;
  const startDate = new Date(start); // local midnight of the oldest day
  const anyPresent = cells.some((c) => c === 1);

  const now = new Date();
  const nowFrac = now.getHours() + now.getMinutes() / 60;

  const label = (d: number) => {
    const dt = new Date(startDate.getTime() + d * 86400000);
    return {
      text: dt.toLocaleDateString(intlLocale(), { day: "2-digit", month: "2-digit" }),
      isToday: d === days - 1,
    };
  };

  return (
    <div className="w-full max-w-[1080px]">
      {/* hour axis */}
      <div className="mb-1 grid grid-cols-[52px_1fr]">
        <span />
        <div className="relative h-3">
          {[0, 6, 12, 18].map((h) => (
            <span
              key={h}
              className="mono absolute top-0 text-[8px] text-fg-3"
              style={{ left: `${(h / 24) * 100}%` }}
            >
              {String(h).padStart(2, "0")}
            </span>
          ))}
          <span className="mono absolute right-0 top-0 text-[8px] text-fg-3">24</span>
        </div>
      </div>

      <div className="space-y-[3px]">
        {Array.from({ length: days }).map((_, d) => {
          const L = label(d);
          const dayCells = cells.slice(d * 24, d * 24 + 24);
          return (
            <div key={d} className="grid grid-cols-[52px_1fr] items-center">
              <span
                className={clsx(
                  "mono flex items-baseline gap-1 pr-2 text-[8.5px]",
                  L.isToday ? "text-signal" : "text-fg-3",
                )}
              >
                <span className="w-8 text-right tabular-nums">{L.text}</span>
              </span>

              <div className="relative bg-surface-2" style={{ height: cell }}>
                {/* 6-hour gridlines — behind the fill */}
                {[6, 12, 18].map((h) => (
                  <span
                    key={h}
                    className="absolute top-0 h-full w-px bg-bg"
                    style={{ left: `${(h / 24) * 100}%` }}
                  />
                ))}
                {/* present hours */}
                {dayCells.map((v, h) =>
                  v === 1 ? (
                    <span
                      key={h}
                      title={`${L.text} · ${String(h).padStart(2, "0")}:00`}
                      className="absolute top-0 h-full bg-signal"
                      style={{ left: `${(h / 24) * 100}%`, width: `${(1 / 24) * 100}%` }}
                    />
                  ) : null,
                )}
                {/* today: shade the hours not yet reached + a "now" hairline */}
                {L.isToday && (
                  <>
                    <span
                      className="absolute top-0 h-full bg-bg/35"
                      style={{ left: `${(nowFrac / 24) * 100}%`, right: 0 }}
                    />
                    <span
                      className="absolute top-[-2px] h-[calc(100%+4px)] w-[1.5px] bg-fg"
                      style={{ left: `${(nowFrac / 24) * 100}%` }}
                    />
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {!anyPresent && (
        <p className="mono mt-2 text-[10px] text-fg-3">{t("presence.empty")}</p>
      )}
    </div>
  );
}
