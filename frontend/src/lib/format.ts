import type { DeviceType } from "../api/types";
import type { MessageKey } from "../i18n/en";
import { intlLocale } from "../i18n/locale";
import { tStatic } from "../i18n/translate";

/** compact relative age — ticks live via useNow() */
export function timeAgo(iso: string, short = false): string {
  const s = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 10) return short ? "now" : tStatic("time.now");
  if (s < 60) return short ? `${s}s` : tStatic("time.secs", { n: s });
  const m = Math.round(s / 60);
  if (m < 60) return short ? `${m}m` : tStatic("time.mins", { n: m });
  const h = Math.round(m / 60);
  if (h < 24) return short ? `${h}h` : tStatic("time.hours", { n: h });
  const d = Math.round(h / 24);
  if (d < 30) return short ? `${d}d` : tStatic("time.days", { n: d });
  return new Date(iso).toLocaleDateString(intlLocale(), { day: "2-digit", month: "short" });
}

/** YYYY-MM-DD HH:MM — logbook style */
export function dateTime(iso: string): string {
  const d = new Date(iso);
  return `${ymd(d)} ${hm(d)}`;
}
export function hm(d: Date | string): string {
  const x = typeof d === "string" ? new Date(d) : d;
  return `${String(x.getHours()).padStart(2, "0")}:${String(x.getMinutes()).padStart(2, "0")}`;
}
export function hms(d: Date | string): string {
  const x = typeof d === "string" ? new Date(d) : d;
  return `${hm(x)}:${String(x.getSeconds()).padStart(2, "0")}`;
}
export function ymd(d: Date | string): string {
  const x = typeof d === "string" ? new Date(d) : d;
  return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, "0")}-${String(x.getDate()).padStart(2, "0")}`;
}

export function num(n: number): string {
  return n.toLocaleString("pt-PT");
}

/** "a.b.c.d" -> unsigned 32-bit int, or null if not a valid IPv4 */
export function ipToLong(ip: string): number | null {
  const p = ip.trim().split(".");
  if (p.length !== 4) return null;
  let out = 0;
  for (const part of p) {
    const n = Number(part);
    if (!Number.isInteger(n) || n < 0 || n > 255) return null;
    out = out * 256 + n;
  }
  return out >>> 0;
}

/** is `ip` inside `cidr` (e.g. "192.168.1.0/24")? tolerant of bad input */
export function ipInCidr(ip: string, cidr: string): boolean {
  const [addr, prefixRaw] = cidr.trim().split("/");
  const prefix = prefixRaw === undefined ? 32 : Number(prefixRaw);
  if (!Number.isInteger(prefix) || prefix < 0 || prefix > 32) return false;
  const a = ipToLong(ip);
  const b = ipToLong(addr);
  if (a === null || b === null) return false;
  const mask = prefix === 0 ? 0 : (0xffffffff << (32 - prefix)) >>> 0;
  return (a & mask) === (b & mask);
}

/** register coordinate: row 0 -> "A·001", row 26 -> "AA·027" (letter cycles) */
export function coord(i: number): { alpha: string; index: string } {
  const alpha = String.fromCharCode(65 + (i % 26)).repeat(Math.floor(i / 26) + 1);
  return { alpha, index: String(i + 1).padStart(3, "0") };
}

export const DEVICE_TYPES: DeviceType[] = [
  "unknown", "router", "access_point", "pc", "laptop", "phone", "tablet", "tv",
  "media", "console", "printer", "nas", "iot", "camera", "speaker", "wearable",
  "server", "car",
];

/** Localised label for a device type. Unknown values pass through unchanged. */
export function deviceTypeLabel(type: string | null | undefined): string {
  if (!type) return "";
  const key = `type.${type}` as MessageKey;
  const out = tStatic(key);
  return out === key ? type : out;
}

/** two-letter register code — replaces the icon set */
export const TYPE_CODE: Record<DeviceType, string> = {
  unknown: "??",
  router: "RT",
  access_point: "AP",
  pc: "PC",
  laptop: "LT",
  phone: "PH",
  tablet: "TB",
  tv: "TV",
  media: "MD",
  console: "CN",
  printer: "PR",
  nas: "NS",
  iot: "IO",
  camera: "CM",
  speaker: "SP",
  wearable: "WR",
  server: "SV",
  car: "CR",
};

/* A hand-picked set of vivid, mutually distinct hues for per-person colour.
   Orange and red are deliberately absent — they belong to the signal / alert
   roles and must not be confused with a person. */
const PERSON_COLORS = [
  "#6366f1", // indigo
  "#14b8a6", // teal
  "#a855f7", // purple
  "#0ea5e9", // sky
  "#84cc16", // lime
  "#ec4899", // pink
  "#eab308", // gold
  "#10b981", // emerald
  "#3b82f6", // blue
  "#d946ef", // fuchsia
  "#06b6d4", // cyan
  "#f472b6", // rose-pink
];

/** deterministic vivid colour from a name — avatars, presence dots */
export function stringHsl(str: string): string {
  let h = 0;
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) >>> 0;
  return PERSON_COLORS[h % PERSON_COLORS.length];
}

/** black or white, whichever reads on top of `hex` */
export function readableOn(hex: string): string {
  const n = parseInt(hex.slice(1), 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  return r * 0.299 + g * 0.587 + b * 0.114 > 150 ? "#0b0b0c" : "#fff";
}

export function initials(name: string): string {
  const parts = name.trim().split(/[\s._-]+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
