import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { deviceTypeLabel, stringHsl } from "../lib/format";
import { useT, type MessageKey } from "../i18n";
import {
  AnimatePresence,
  motion,
  useReducedMotion,
  snappy,
} from "../lib/motion";
import {
  ArrowRight,
  ConfigIcon,
  DeviceTypeIcon,
  HostsIcon,
  LogIcon,
  PeopleIcon,
  ReviewIcon,
  Search,
  StatsIcon,
} from "./Glyph";

type Item = {
  key: string;
  kind: "page" | "device" | "person";
  label: string;
  sub?: string;
  to: string;
  icon: React.ReactNode;
};

const PAGES: { to: string; labelKey: MessageKey; Icon: (p: { size?: number }) => JSX.Element }[] = [
  { to: "/", labelKey: "title.hosts", Icon: HostsIcon },
  { to: "/approvals", labelKey: "title.review", Icon: ReviewIcon },
  { to: "/users", labelKey: "title.people", Icon: PeopleIcon },
  { to: "/distribution", labelKey: "title.stats", Icon: StatsIcon },
  { to: "/events", labelKey: "title.log", Icon: LogIcon },
  { to: "/settings", labelKey: "title.config", Icon: ConfigIcon },
];

const groupLabel: Record<Item["kind"], MessageKey> = {
  page: "cmd.pages",
  device: "cmd.devices",
  person: "cmd.people",
};

/** ⌘K / Ctrl+K — jump to any device, person or page. Mounted once in the Shell. */
export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const nav = useNavigate();
  const t = useT();
  const reduced = useReducedMotion();
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    const openIt = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener("netscan:cmdk", openIt);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("netscan:cmdk", openIt);
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    setQ("");
    setActive(0);
    document.body.style.overflow = "hidden";
    const id = requestAnimationFrame(() => inputRef.current?.focus());
    return () => {
      cancelAnimationFrame(id);
      document.body.style.overflow = "";
    };
  }, [open]);

  const devices = useQuery({ queryKey: ["devices"], queryFn: () => api.devices(), enabled: open });
  const users = useQuery({ queryKey: ["users"], queryFn: api.users, enabled: open });

  const items = useMemo<Item[]>(() => {
    const n = q.toLowerCase().trim();
    const out: Item[] = [];

    for (const p of PAGES) {
      const label = t(p.labelKey);
      if (!n || label.toLowerCase().includes(n))
        out.push({ key: `p${p.to}`, kind: "page", label, to: p.to, icon: <p.Icon size={15} /> });
    }

    const devs = (devices.data ?? []).filter((d) => {
      if (!n) return false;
      return (
        d.display_name.toLowerCase().includes(n) ||
        (d.vendor ?? "").toLowerCase().includes(n) ||
        (d.os_family ?? "").toLowerCase().includes(n) ||
        d.ips.some((i) => i.address.includes(n)) ||
        d.macs.some((m) => m.address.toLowerCase().includes(n))
      );
    });
    for (const d of devs.slice(0, 8)) {
      const ip = (d.ips.find((i) => i.is_primary) ?? d.ips[0])?.address;
      out.push({
        key: `d${d.id}`,
        kind: "device",
        label: d.display_name,
        sub: [ip, deviceTypeLabel(d.device_type)].filter(Boolean).join(" · "),
        to: `/devices/${d.id}`,
        icon: <DeviceTypeIcon type={d.device_type} size={15} />,
      });
    }

    const ppl = (users.data ?? []).filter((u) => n && u.name.toLowerCase().includes(n));
    for (const u of ppl.slice(0, 6)) {
      out.push({
        key: `u${u.id}`,
        kind: "person",
        label: u.name,
        sub: t("users.devicesShort", { n: u.device_count }),
        to: `/users/${u.id}`,
        icon: <span className="h-3 w-3 rounded-full" style={{ background: stringHsl(u.name) }} />,
      });
    }

    return out;
  }, [q, devices.data, users.data, t]);

  useEffect(() => setActive(0), [q]);

  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>(`[data-i="${active}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [active]);

  const go = (it: Item | undefined) => {
    if (!it) return;
    setOpen(false);
    nav(it.to);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => (items.length ? (a + 1) % items.length : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => (items.length ? (a - 1 + items.length) % items.length : 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      go(items[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  let lastKind: Item["kind"] | null = null;

  return createPortal(
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-[95] flex items-start justify-center px-4 pt-[12vh]">
          <motion.div
            className="absolute inset-0 bg-black/40"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={() => setOpen(false)}
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            initial={reduced ? { opacity: 0 } : { opacity: 0, y: -8, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={reduced ? { opacity: 0 } : { opacity: 0, y: -8, scale: 0.98 }}
            transition={reduced ? { duration: 0.14 } : snappy}
            className="relative w-full max-w-[560px] overflow-hidden rounded-2xl bg-surface shadow-e3"
            onKeyDown={onKeyDown}
          >
            <div className="flex items-center gap-3 px-4">
              <Search size={16} className="shrink-0 text-fg-3" />
              <input
                ref={inputRef}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder={t("cmd.placeholder")}
                className="h-12 w-full bg-transparent text-[14.5px] text-fg outline-none placeholder:text-fg-3"
              />
              <kbd className="mono shrink-0 rounded-md bg-fg/[0.06] px-1.5 py-0.5 text-[10px] text-fg-3">esc</kbd>
            </div>

            <div ref={listRef} className="max-h-[52vh] overflow-y-auto border-t border-edge p-1.5">
              {items.length === 0 ? (
                <p className="px-3 py-6 text-center text-[12.5px] text-fg-3">
                  {q ? t("cmd.empty") : t("cmd.hint")}
                </p>
              ) : (
                items.map((it, i) => {
                  const header = it.kind !== lastKind ? t(groupLabel[it.kind]) : null;
                  lastKind = it.kind;
                  return (
                    <div key={it.key}>
                      {header && <p className="key px-3 pb-1 pt-2">{header}</p>}
                      <button
                        data-i={i}
                        onMouseMove={() => setActive(i)}
                        onClick={() => go(it)}
                        className={
                          "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left transition-colors " +
                          (i === active ? "bg-fg/[0.07]" : "")
                        }
                      >
                        <span className="grid h-5 w-5 shrink-0 place-items-center text-fg-2">
                          {it.icon}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13.5px] text-fg">{it.label}</span>
                          {it.sub && (
                            <span className="mono block truncate text-[10.5px] text-fg-3">{it.sub}</span>
                          )}
                        </span>
                        {i === active && <ArrowRight size={13} className="shrink-0 text-fg-3" />}
                      </button>
                    </div>
                  );
                })
              )}
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
