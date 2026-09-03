/**
 * Regenerates src/components/Glyph.tsx from the Phosphor icon set (regular
 * weight), vendoring each icon's path markup so the app carries no icon runtime
 * dependency. Needs the devDependency @phosphor-icons/core.
 *
 *   node scripts/gen-glyphs.mjs
 */
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const ASSETS = resolve(here, "../node_modules/@phosphor-icons/core/assets/regular");
const OUT = resolve(here, "../src/components/Glyph.tsx");

/** exported name -> phosphor icon (regular) */
const UI = {
  ArrowRight: "arrow-right",
  ArrowLeft: "arrow-left",
  ArrowUpRight: "arrow-up-right",
  Chevron: "caret-right",
  Close: "x",
  Plus: "plus",
  Check: "check",
  Trash: "trash",
  Merge: "arrows-merge",
  Send: "paper-plane-right",
  Image: "image",
  Search: "magnifying-glass",
  CaretDown: "caret-down",
  CornerDown: "arrow-elbow-down-right",
  Bell: "bell",
  Paperclip: "paperclip",
  Envelope: "envelope-simple",
  // log categories
  Radar: "broadcast",
  Plug: "plug",
  Shield: "shield-check",
  Globe: "globe-simple",
  Wave: "wave-sine",
  // sidebar nav
  HostsIcon: "list-bullets",
  ReviewIcon: "tray",
  PeopleIcon: "users-three",
  LogIcon: "clock-counter-clockwise",
  ConfigIcon: "sliders-horizontal",
  StatsIcon: "chart-bar",
};

/** DeviceType -> phosphor icon (regular); nearest match where no exact exists */
const DEVICES = {
  unknown: "question",
  router: "wifi-high",
  access_point: "wifi-medium",
  hub: "share-network",
  pc: "desktop",
  laptop: "laptop",
  vm: "cube",
  phone: "device-mobile",
  voip: "phone-call",
  tablet: "device-tablet",
  ereader: "book-open",
  tv: "television-simple",
  projector: "projector-screen",
  media: "screencast",
  display: "monitor",
  console: "game-controller",
  printer: "printer",
  nas: "hard-drive",
  iot: "cpu",
  thermostat: "thermometer-simple",
  appliance: "washing-machine",
  vacuum: "robot",
  camera: "security-camera",
  doorbell: "bell-ringing",
  speaker: "speaker-hifi",
  wearable: "watch",
  server: "hard-drives",
  car: "car",
};

/** pull the inner markup out of a phosphor svg file, normalised to one line */
function inner(icon) {
  const raw = readFileSync(resolve(ASSETS, `${icon}.svg`), "utf8");
  const m = raw.match(/<svg[^>]*>([\s\S]*?)<\/svg>/);
  if (!m) throw new Error(`no <svg> body in ${icon}.svg`);
  return m[1].replace(/\s+/g, " ").replace(/> </g, "><").trim();
}

const entries = (obj) =>
  Object.entries(obj)
    .map(([k, v]) => `  "${k}": '${inner(v).replace(/'/g, "\\'")}',`)
    .join("\n");

const out = `/**
 * Icon set — Phosphor Icons (https://phosphoricons.com), regular weight, MIT.
 * Vendored: each icon's path markup is inlined so the app ships no icon runtime
 * dependency. Do not edit by hand — regenerate with:
 *
 *   node scripts/gen-glyphs.mjs
 */
import type { DeviceType } from "../api/types";

type P = { size?: number; className?: string };

const UI: Record<string, string> = {
${entries(UI)}
};

const DEVICE: Record<DeviceType, string> = {
${entries(DEVICES)}
} as Record<DeviceType, string>;

function Icon({ size = 16, className, d }: P & { d: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 256 256"
      fill="currentColor"
      className={className}
      aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: d }}
    />
  );
}

${Object.keys(UI)
  .map((name) => `export const ${name} = (p: P) => <Icon {...p} d={UI["${name}"]} />;`)
  .join("\n")}

export function DeviceTypeIcon({ type, size = 14, className }: P & { type: DeviceType }) {
  return <Icon size={size} className={className} d={DEVICE[type] ?? DEVICE.unknown} />;
}
`;

writeFileSync(OUT, out);
console.log(`wrote ${OUT} — ${Object.keys(UI).length} ui + ${Object.keys(DEVICES).length} device icons`);
