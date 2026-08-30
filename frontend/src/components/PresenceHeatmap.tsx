import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { api } from "../api/client";
import { intlLocale } from "../i18n/locale";
import { useT } from "../i18n";
import { Skeleton } from "./ui";

/**
 * Presence as a chart-recorder strip: one row per local calendar day (oldest
 * first, today last). Each interval the person was present is drawn as a solid
 * orange bar, clipped to that day and positioned to the minute. Everything is
 * converted to the viewer's own timezone. A hairline marks "now" on today's row.
 */
const DAY_MS = 86_400_000;

function startOfLocalDay(d: Date): Date {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
}

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

  const spans = grid.data.intervals.map(
    ([a, b]) => [new Date(a).getTime(), new Date(b).getTime()] as const,
  );
  const anyPresent = spans.length > 0;

  const now = new Date();
  const nowFrac = now.getHours() + now.getMinutes() / 60;
  // local midnight of the oldest row
  const firstDay = startOfLocalDay(new Date(now.getTime() - (days - 1) * DAY_MS));

  const label = (d: number) => {
    const dt = new Date(firstDay.getTime() + d * DAY_MS);
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
          const dayStart = firstDay.getTime() + d * DAY_MS;
          const dayEnd = dayStart + DAY_MS;
          // intervals overlapping this local day, clipped to it, as [0..24] hours
          const bars = spans
            .filter(([a, b]) => b > dayStart && a < dayEnd)
            .map(([a, b]) => {
              const from = (Math.max(a, dayStart) - dayStart) / 3_600_000;
              const to = (Math.min(b, dayEnd) - dayStart) / 3_600_000;
              return { from, to };
            });
          return (
            <div key={d} className="grid grid-cols-[52px_1fr] items-center">
              <span
                className={clsx(
                  "mono flex items-baseline gap-1 pr-2 text-[8.5px]",
                  L.isToday ? "text-fg" : "text-fg-3",
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
                {/* present intervals, to the minute */}
                {bars.map((b, i) => (
                  <span
                    key={i}
                    title={`${fmtHour(b.from)}–${fmtHour(b.to)}`}
                    className="absolute top-0 h-full bg-signal"
                    style={{
                      left: `${(b.from / 24) * 100}%`,
                      width: `${((b.to - b.from) / 24) * 100}%`,
                    }}
                  />
                ))}
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

/** hour-of-day float (e.g. 13.5) → "13:30" */
function fmtHour(h: number): string {
  const hh = Math.floor(h) % 24;
  const mm = Math.round((h - Math.floor(h)) * 60);
  const m = mm === 60 ? 0 : mm;
  const carry = mm === 60 ? 1 : 0;
  return `${String((hh + carry) % 24).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}
