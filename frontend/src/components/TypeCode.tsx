import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import type { Device, DeviceType } from "../api/types";
import { DeviceTypeIcon } from "./Glyph";

/* ── logo maps ────────────────────────────────────────────────────────── */
function useLogoMap(kind: "brands" | "os") {
  const q = useQuery({
    queryKey: [kind === "brands" ? "brands" : "os-logos"],
    queryFn: kind === "brands" ? api.brands : api.osLogos,
    staleTime: 60000,
  });
  const map = new Map<string, string>();
  for (const b of q.data ?? []) if (b.logo_url) map.set(b.name.toLowerCase(), b.logo_url);
  return map;
}
export const useBrandLogos = () => useLogoMap("brands");
export const useOsLogos = () => useLogoMap("os");

/** A device photo: fills the square when it's ~1:1, otherwise sits contained with
 *  a little padding so nothing is cropped. Aspect is measured on load. */
function DevicePhoto({ src }: { src: string }) {
  const [fit, setFit] = useState<"cover" | "pad">("cover");
  return (
    <img
      src={src}
      alt=""
      onLoad={(e) => {
        const { naturalWidth: w, naturalHeight: h } = e.currentTarget;
        if (w && h) setFit(Math.abs(w - h) / Math.max(w, h) > 0.06 ? "pad" : "cover");
      }}
      className={
        fit === "cover"
          ? "h-full w-full object-cover"
          : "h-full w-full object-contain p-[6%]"
      }
    />
  );
}

/* ── the glyph: photo | brand logo | device-type icon ──────────────────── */
export function TypeCode({
  device,
  logos,
  size = 30,
}: {
  device: Device;
  logos: Map<string, string>;
  /** @deprecated no longer rendered — the OS logo lives in the OS column now */
  osLogos?: Map<string, string>;
  size?: number;
}) {
  const photo = device.images.find((i) => i.is_primary)?.url ?? device.images[0]?.url;
  const logo = device.short_vendor ? logos.get(device.short_vendor.toLowerCase()) : undefined;

  return (
    <div
      className="shrink-0 overflow-hidden rounded-[10px]"
      style={{ width: size, height: size }}
    >
      {photo ? (
        <DevicePhoto src={photo} />
      ) : logo ? (
        <img src={logo} alt="" className="h-full w-full object-contain" />
      ) : (
        <span className="grid h-full w-full place-items-center bg-fg/[0.06] text-fg-3">
          <DeviceTypeIcon type={device.device_type} size={Math.round(size * 0.5)} />
        </span>
      )}
    </div>
  );
}

/** bare device-type glyph in a filled block */
export function TypeMark({ type, size = 22 }: { type: DeviceType; size?: number }) {
  return (
    <span
      className="inline-grid shrink-0 place-items-center rounded-[10px] bg-surface-2 text-fg-2"
      style={{ width: size, height: size }}
    >
      <DeviceTypeIcon type={type} size={Math.round(size * 0.5)} />
    </span>
  );
}
