import clsx from "clsx";
import { useState } from "react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { ApprovalStatus, EventLevel } from "../api/types";
import { initials, readableOn, stringHsl } from "../lib/format";
import { useT } from "../i18n";
import { AnimatePresence, motion, useReducedMotion } from "../lib/motion";

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
  return <span className="inline-block h-3 w-3 animate-spin rounded-full border border-current border-t-transparent" />;
}

/* ── Block / Card — the grouping primitive (a card, hairline, soft lift) ─ */
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

/* ── RollingValue — the figure flips when it changes (a metric ticked) ── */
export function RollingValue({ children }: { children: ReactNode }) {
  const reduced = useReducedMotion();
  // Clip the roll with clip-path, NOT overflow:hidden — an inline-block with
  // overflow≠visible takes its bottom edge as the baseline, which knocks the
  // figure out of line with the labels beside it in the header vitals.
  return (
    <span className="relative inline-block [clip-path:inset(0)]">
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.span
          key={String(children)}
          className="inline-block"
          initial={reduced ? { opacity: 0 } : { y: "65%", opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={reduced ? { opacity: 0 } : { y: "-65%", opacity: 0 }}
          transition={reduced ? { duration: 0.14 } : { type: "spring", bounce: 0.16, duration: 0.42 }}
        >
          {children}
        </motion.span>
      </AnimatePresence>
    </span>
  );
}

/* ── Readout — a big figure + a quiet caption ─────────────────────────── */
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
  const px = {
    sm: "text-[24px]",
    md: "text-[32px]",
    lg: "text-[clamp(30px,4.4vw,48px)]",
    xl: "text-[clamp(38px,5.4vw,64px)]",
  }[size];
  const color = tone === "alert" ? "text-alert" : "text-fg";
  return (
    <div className={clsx("flex flex-col gap-1.5", className)}>
      <div className="flex items-baseline gap-2">
        <span className={clsx("font-display leading-[0.95] tnum", px, color)}>
          <RollingValue>{value}</RollingValue>
        </span>
        {unit && <span className="mono text-[12px] text-fg-3">{unit}</span>}
      </div>
      {caption != null && <span className="label">{caption}</span>}
    </div>
  );
}

/* ── Redacted — a value shown masked, revealed on hover / focus / tap ── */
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
        "mb-4 flex items-center justify-between gap-3",
        className,
      )}
    >
      <div className="flex items-baseline gap-2.5">
        <h2 className="font-display text-[15px] text-fg">{title}</h2>
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

/* ── Badge → chip ──────────────────────────────────────────────────── */
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

/* ── status marks — a small dot ─────────────────────────────────────── */
export function StatusMark({
  state = "offline",
  size = 9,
}: {
  state?: "online" | "offline" | "unreviewed";
  online?: boolean;
  size?: number;
}) {
  const cls =
    state === "online" ? "signal-mark signal-mark--on"
    : state === "unreviewed" ? "signal-mark signal-mark--alert"
    : "signal-mark signal-mark--off";
  return <span className={cls} style={{ ["--m" as string]: `${size}px` }} />;
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
        online ? "text-fg-2" : "text-fg-3",
      )}
    >
      <StatusMark state={online ? "online" : "offline"} size={8} />
      {online ? t("shell.vital.online") : t("common.offline")}
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
    success: "bg-fg",
    warning: "bg-alert",
    alert: "bg-alert",
  }[level];
  return <span className={clsx("block h-full w-[2px] shrink-0 rounded-full", c)} />;
}

/* ── Avatar — rounded, initials ────────────────────────────────────── */
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
        borderRadius: size * 0.32,
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
        <span className="mt-1 block text-[11.5px] text-alert">{error}</span>
      ) : (
        hint && <span className="mt-1 block text-[11.5px] text-fg-3">{hint}</span>
      )}
    </label>
  );
}

/* ── Toggle → an animated switch ────────────────────────────────────── */
export function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label?: string;
}) {
  const reduced = useReducedMotion();
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={clsx(
        "relative inline-flex h-[24px] w-[42px] shrink-0 items-center rounded-full transition-colors",
        checked ? "bg-fg" : "bg-fg/[0.14]",
      )}
    >
      <motion.span
        className="block h-[20px] w-[20px] rounded-full shadow-[0_1px_3px_rgba(0,0,0,0.25)]"
        animate={{ x: checked ? 20 : 2 }}
        transition={reduced ? { duration: 0 } : { type: "spring", bounce: 0, duration: 0.25 }}
        style={{ background: "#fff" }}
      />
    </button>
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
    <div className="panel divide-y divide-edge overflow-hidden">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 px-4 py-3.5">
          <div className="skeleton h-[9px] w-[9px] rounded-full" />
          <div className="skeleton h-8 w-8 rounded-lg" />
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
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-16 text-center">
      {icon ? (
        <span className="text-fg-3">{icon}</span>
      ) : (
        <span className="signal-mark signal-mark--off mb-0.5" style={{ ["--m" as string]: "11px" }} />
      )}
      <p className="font-display text-[15px] text-fg">{title}</p>
      {description && (
        <p className="max-w-sm text-[12.5px] leading-relaxed text-fg-2">{description}</p>
      )}
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}

/* ── Stat → small figure ─────────────────────────────────────────── */
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
  const isAlert =
    (tone === "red" || tone === "alert") && Number(value) > 0;
  return (
    <div className="flex flex-col gap-1 py-1">
      <span className="key">{label}</span>
      <div className="flex items-baseline gap-2">
        <span
          className={clsx(
            "font-display text-[28px] leading-none tnum",
            isAlert ? "text-alert" : "text-fg",
          )}
        >
          {value}
        </span>
        {delta && <span className="mono text-[10px] text-fg-3">{delta}</span>}
      </div>
    </div>
  );
}

/* ── QueryState — error / skeleton ─────────────────────────────────── */
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
      <div className="rounded-xl bg-alert/10 px-4 py-4">
        <p className="text-[13px] font-medium text-alert">{t("common.signalLost")}</p>
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
