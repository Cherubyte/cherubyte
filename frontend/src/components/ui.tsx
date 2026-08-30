import clsx from "clsx";
import { useState } from "react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { ApprovalStatus, EventLevel } from "../api/types";
import { initials, readableOn, stringHsl } from "../lib/format";
import { useT } from "../i18n";

/* ── Button ──────────────────────────────────────────────────────────── */
type BtnVariant = "primary" | "secondary" | "ghost" | "danger";
type BtnSize = "sm" | "md" | "lg";

export function Button({
  variant = "secondary",
  size = "md",
  loading,
  icon,
  className,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: BtnVariant;
  size?: BtnSize;
  loading?: boolean;
  icon?: ReactNode;
}) {
  return (
    <button
      {...rest}
      disabled={rest.disabled || loading}
      className={clsx(
        "btn",
        `btn-${variant}`,
        size === "sm" && "btn-sm",
        size === "lg" && "btn-lg",
        !children && "btn-icon",
        className,
      )}
    >
      {loading ? <Spinner /> : icon}
      {children}
    </button>
  );
}

function Spinner() {
  return <span className="inline-block h-3 w-3 animate-spin border border-current border-t-transparent" />;
}

/* ── Block — the only grouping primitive (a solid panel, no border) ───── */
export function Block({
  children,
  className,
  ruled,
  as: As = "section",
}: {
  children: ReactNode;
  className?: string;
  ruled?: boolean;
  as?: "div" | "section";
}) {
  return <As className={clsx("panel", ruled && "panel-ruled", className)}>{children}</As>;
}
/** legacy name — pages still import `Card` */
export function Card({
  children,
  className,
  as: As = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "section";
}) {
  return <As className={clsx("panel", className)}>{children}</As>;
}

/* ── Readout — the station-board figure: big display numeral + caption ── */
export function Readout({
  value,
  unit,
  caption,
  size = "lg",
  tone = "default",
  className,
}: {
  value: ReactNode;
  unit?: ReactNode;
  caption?: ReactNode;
  size?: "sm" | "md" | "lg" | "xl";
  tone?: "default" | "signal" | "alert";
  className?: string;
}) {
  const px = { sm: "text-[24px]", md: "text-[34px]", lg: "text-[clamp(34px,5vw,58px)]", xl: "text-[clamp(40px,6vw,72px)]" }[size];
  const color =
    tone === "signal" ? "text-signal" : tone === "alert" ? "text-alert" : "text-fg";
  return (
    <div className={clsx("flex flex-col gap-1.5", className)}>
      <div className="flex items-baseline gap-2">
        <span className={clsx("font-display-lt leading-[0.8] tnum", px, color)}>{value}</span>
        {unit && <span className="mono text-[12px] text-fg-3">{unit}</span>}
      </div>
      {caption != null && <span className="key">{caption}</span>}
    </div>
  );
}

/* ── Redacted — a value shown masked, revealed on hover / focus / tap ──
   For things you want on screen but not on a screenshot: the public IP. The
   dots keep the shape (dots, colons) so the reveal is not a layout jump. */
export function Redacted({
  value,
  label,
  className,
}: {
  value: string;
  label?: string;
  className?: string;
}) {
  const t = useT();
  const [shown, setShown] = useState(false);
  const masked = value.replace(/[^.:]/g, "•");
  return (
    <button
      type="button"
      onMouseEnter={() => setShown(true)}
      onMouseLeave={() => setShown(false)}
      onFocus={() => setShown(true)}
      onBlur={() => setShown(false)}
      onClick={() => setShown((s) => !s)}
      aria-label={shown ? value : label ?? t("dash.wan.ipReveal")}
      title={shown ? undefined : label ?? t("dash.wan.ipReveal")}
      className={clsx(
        "mono tnum cursor-pointer select-none text-fg-2 transition-colors hover:text-fg focus-visible:text-fg",
        className,
      )}
    >
      {shown ? value : masked}
    </button>
  );
}

/* ── SectionHeader ───────────────────────────────────────────────────── */
export function SectionHeader({
  title,
  sub,
  actions,
  className,
}: {
  title: ReactNode;
  sub?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={clsx(
        "mb-3 flex items-center justify-between gap-3 border-b-2 border-edge-2 pb-2",
        className,
      )}
    >
      <div className="flex items-baseline gap-2.5">
        <h2 className="font-display text-[15px] tracking-tight text-fg">{title}</h2>
        {sub != null && <span className="label">{sub}</span>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-1.5">{actions}</div>}
    </div>
  );
}

/* ── Label ──────────────────────────────────────────────────────────── */
export function Label({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={clsx("label", className)}>{children}</span>;
}
export function Key({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={clsx("key", className)}>{children}</span>;
}

/* ── Badge → hard tag chip ──────────────────────────────────────────── */
export function Badge({
  tone = "neutral",
  children,
  className,
}: {
  tone?: "neutral" | "amber" | "signal" | "red" | "alert" | "ink";
  children: ReactNode;
  className?: string;
}) {
  const map: Record<string, string> = {
    neutral: "tag-neutral",
    ink: "tag-ink",
    amber: "tag-signal",
    signal: "tag-signal",
    red: "tag-alert",
    alert: "tag-alert",
  };
  return <span className={clsx("tag", map[tone], className)}>{children}</span>;
}

/* ── status marks — a filled square, not a dot ──────────────────────── */
export function StatusMark({
  state = "offline",
  size = 9,
}: {
  state?: "online" | "offline" | "unreviewed";
  online?: boolean;
  size?: number;
}) {
  if (state === "online")
    return (
      <span
        className="inline-block shrink-0 bg-signal"
        style={{ width: size, height: size }}
      />
    );
  if (state === "unreviewed")
    return <span className="inline-block shrink-0 bg-alert" style={{ width: size, height: size }} />;
  return (
    <span
      className="inline-block shrink-0 border border-edge-2"
      style={{ width: size, height: size }}
    />
  );
}
/** legacy signature: <StatusMark online={bool} /> */
export function statusOf(online: boolean): "online" | "offline" {
  return online ? "online" : "offline";
}

export function StatusPill({ online }: { online: boolean }) {
  const t = useT();
  return (
    <span
      className={clsx(
        "label inline-flex items-center gap-2",
        online ? "text-signal" : "text-fg-3",
      )}
    >
      <StatusMark state={online ? "online" : "offline"} size={8} />
      {online ? t("shell.vital.online") : "Offline"}
    </span>
  );
}

export function ApprovalTag({ status }: { status: ApprovalStatus }) {
  const t = useT();
  if (status === "approved") return <Badge tone="ink">{t("approval.approved")}</Badge>;
  if (status === "pending") return <Badge tone="alert">{t("approval.pending")}</Badge>;
  return <Badge tone="neutral">{t("approval.ignored")}</Badge>;
}

/** left-edge level tick for the log */
export function LevelDot({ level }: { level: EventLevel }) {
  const c = {
    info: "bg-fg-3",
    success: "bg-signal",
    warning: "bg-alert",
    alert: "bg-alert",
  }[level];
  return <span className={clsx("block h-full w-[2px] shrink-0", c)} />;
}

/* ── Avatar — solid block, initials ────────────────────────────────── */
export function Avatar({ name, size = 26 }: { name: string; size?: number }) {
  const bg = stringHsl(name);
  return (
    <span
      className="grid shrink-0 place-items-center font-semibold"
      style={{
        width: size,
        height: size,
        background: bg,
        color: readableOn(bg),
        fontSize: size * 0.38,
        borderRadius: 3,
      }}
    >
      {initials(name)}
    </span>
  );
}

/* ── Field ──────────────────────────────────────────────────────────── */
export function Field({
  label,
  hint,
  error,
  children,
  className,
}: {
  label?: string;
  hint?: ReactNode;
  error?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={clsx("block", className)}>
      {label && <span className="label mb-1.5 block">{label}</span>}
      {children}
      {error ? (
        <span className="mono mt-1 block text-[11px] text-alert">{error}</span>
      ) : (
        hint && <span className="mono mt-1 block text-[11px] text-fg-3">{hint}</span>
      )}
    </label>
  );
}

/* ── Toggle → ON | OFF segmented ────────────────────────────────────── */
export function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label?: string;
}) {
  return (
    <span
      role="group"
      aria-label={label}
      className="mono inline-flex shrink-0 select-none overflow-hidden rounded-[3px] border border-edge-2 text-[10px] leading-none"
    >
      {(["ON", "OFF"] as const).map((s) => {
        const active = (s === "ON") === checked;
        return (
          <button
            key={s}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(s === "ON")}
            className={clsx(
              "px-2.5 py-1.5 tracking-[0.1em] transition-colors",
              active
                ? "bg-signal-bg text-signal-fg"
                : "bg-transparent text-fg-3 hover:text-fg",
            )}
          >
            {s}
          </button>
        );
      })}
    </span>
  );
}

/* ── Skeletons ──────────────────────────────────────────────────────── */
export function Skeleton({
  className,
  style,
}: {
  className?: string;
  style?: React.CSSProperties;
}) {
  return <div className={clsx("skeleton", className)} style={style} />;
}

export function SkeletonRows({ rows = 6 }: { rows?: number }) {
  return (
    <div className="space-y-px">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 bg-surface px-3 py-3.5">
          <div className="skeleton h-[9px] w-[9px]" />
          <div className="skeleton h-6 w-6" />
          <div className="skeleton h-4 flex-1" style={{ maxWidth: `${40 + ((i * 37) % 40)}%` }} />
          <div className="skeleton ml-auto h-3 w-24" />
        </div>
      ))}
    </div>
  );
}

/* ── EmptyState ────────────────────────────────────────────────────── */
export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2.5 border border-edge bg-surface-2 px-6 py-16 text-center">
      {icon ? (
        <span className="text-fg-3">{icon}</span>
      ) : (
        <span className="mb-0.5 h-2.5 w-2.5 shrink-0 border border-edge-2" />
      )}
      <p className="font-display text-[15px] tracking-tight text-fg">{title}</p>
      {description && (
        <p className="mono max-w-sm text-[11px] leading-relaxed text-fg-2">{description}</p>
      )}
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}

/* ── Stat → small readout ─────────────────────────────────────────── */
export function Stat({
  label,
  value,
  delta,
  tone = "default",
}: {
  label: string;
  value: number | string;
  delta?: string;
  tone?: "default" | "amber" | "signal" | "red" | "alert";
}) {
  const t =
    tone === "red" || tone === "alert"
      ? Number(value) > 0
        ? "alert"
        : "default"
      : tone === "amber"
        ? "signal"
        : (tone as "default" | "signal");
  return (
    <div className="flex flex-col gap-1 py-1">
      <span className="key">{label}</span>
      <div className="flex items-baseline gap-2">
        <span
          className={clsx(
            "font-display-lt text-[30px] leading-none tnum",
            t === "alert" ? "text-alert" : t === "signal" ? "text-signal" : "text-fg",
          )}
        >
          {value}
        </span>
        {delta && <span className="mono text-[10px] text-signal">{delta}</span>}
      </div>
    </div>
  );
}

/* ── QueryState — SIGNAL LOST / skeleton ────────────────────────────── */
export function QueryState({
  q,
  label,
}: {
  q: { isLoading: boolean; isError: boolean; error?: unknown; refetch?: () => void };
  label?: string;
}) {
  const t = useT();
  if (q.isError) {
    const msg = q.error instanceof Error ? q.error.message : t("common.loadError");
    return (
      <div className="border-y-2 border-alert bg-surface px-3 py-4">
        <p className="key text-alert">{t("common.signalLost")}</p>
        <p className="mono mt-1.5 text-[11px] leading-relaxed text-fg-2">{msg}</p>
        {q.refetch && (
          <button onClick={() => q.refetch!()} className="btn btn-danger btn-sm mt-3">
            {t("common.retry")}
          </button>
        )}
      </div>
    );
  }
  if (q.isLoading) {
    return (
      <div className="space-y-2 py-1">
        {label && <p className="key">{label}</p>}
        <SkeletonRows rows={4} />
      </div>
    );
  }
  return null;
}
