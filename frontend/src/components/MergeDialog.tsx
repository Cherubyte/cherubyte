import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Device } from "../api/types";
import { deviceTypeLabel } from "../lib/format";
import { useT } from "../i18n";
import { TypeCode, useBrandLogos, useOsLogos } from "./TypeCode";
import { Dialog } from "./Dialog";
import { Button } from "./ui";
import { ArrowRight, Merge, Search } from "./Glyph";
import { useToast } from "./Toaster";

/**
 * Fold THIS (duplicate) device into a canonical one the user picks.
 * All IPs / MACs / ports / history / photos move to the canonical device.
 */
export function MergeDialog({
  open,
  onClose,
  device,
}: {
  open: boolean;
  onClose: () => void;
  device: Device;
}) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const toast = useToast();
  const t = useT();
  const logos = useBrandLogos();
  const osLogos = useOsLogos();
  const [q, setQ] = useState("");
  const [target, setTarget] = useState<Device | null>(null);

  const all = useQuery({ queryKey: ["devices"], queryFn: () => api.devices(), enabled: open });

  const results = useMemo(() => {
    const nq = q.toLowerCase().trim();
    return (all.data ?? [])
      .filter((d) => d.id !== device.id)
      .filter(
        (d) =>
          !nq ||
          d.display_name.toLowerCase().includes(nq) ||
          (d.vendor ?? "").toLowerCase().includes(nq) ||
          d.ips.some((i) => i.address.includes(nq)) ||
          d.macs.some((m) => m.address.toLowerCase().includes(nq)),
      )
      .sort((a, b) => a.display_name.localeCompare(b.display_name))
      .slice(0, 40);
  }, [all.data, q, device.id]);

  const merge = useMutation({
    mutationFn: () => api.mergeDevices(target!.id, [device.id]),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["devices"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      toast({ tone: "success", title: "devices.merged", desc: `-> ${target!.display_name}` });
      onClose();
      nav(`/devices/${target!.id}`);
    },
    onError: (e) => toast({ tone: "error", title: "merge.failed", desc: String(e).slice(0, 120) }),
  });

  const reset = () => {
    setTarget(null);
    setQ("");
  };

  return (
    <Dialog
      open={open}
      onClose={() => {
        reset();
        onClose();
      }}
      title={t("merge.title")}
      width={480}
    >
      {!target ? (
        <div className="flex flex-col">
          <div className="px-4 pb-3 pt-3.5">
            <p className="text-xs leading-relaxed text-fg-3">
              {t("merge.pickCanonical", { name: device.display_name })}
            </p>
            <div className="relative mt-3">
              <Search
                size={13}
                className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-fg-3"
              />
              <input
                autoFocus
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder={t("merge.search")}
                className="input mono pl-8"
              />
            </div>
          </div>
          <ul className="max-h-[46vh] overflow-y-auto border-t border-edge">
            {results.length === 0 && (
              <li className="label px-4 py-6 text-center">
                {all.isLoading ? t("common.loading") : t("common.noResults")}
              </li>
            )}
            {results.map((d) => (
              <li key={d.id} className="border-t border-edge first:border-t-0">
                <button
                  onClick={() => setTarget(d)}
                  className="flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors hover:bg-surface-2"
                >
                  <TypeCode device={d} logos={logos} osLogos={osLogos} size={28} />
                  <div className="min-w-0 flex-1">
                    <div className="font-display truncate text-[13px] tracking-tight text-fg">
                      {d.display_name}
                    </div>
                    <div className="mono truncate text-[10px] text-fg-3">
                      {(d.ips.find((i) => i.is_primary) ?? d.ips[0])?.address ?? "—"} ·{" "}
                      {deviceTypeLabel(d.device_type)}
                      {d.short_vendor ? ` · ${d.short_vendor}` : ""}
                    </div>
                  </div>
                  <ArrowRight size={13} className="shrink-0 text-fg-3" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="p-4">
          <div className="flex items-center justify-center gap-4 border border-edge bg-surface-2 p-4">
            <div className="flex flex-col items-center gap-1.5 text-center">
              <TypeCode device={device} logos={logos} osLogos={osLogos} size={38} />
              <span className="mono max-w-[110px] truncate text-[10px] text-fg-3 line-through">
                {device.display_name}
              </span>
            </div>
            <ArrowRight size={16} className="shrink-0 text-fg-3" />
            <div className="flex flex-col items-center gap-1.5 text-center">
              <TypeCode device={target} logos={logos} osLogos={osLogos} size={38} />
              <span className="font-display max-w-[120px] truncate text-[12px] tracking-tight text-fg">
                {target.display_name}
              </span>
            </div>
          </div>
          <p className="mt-3 text-xs leading-relaxed text-fg-3">
            {t("merge.summary", {
              ips: device.ips.length,
              macs: device.macs.length,
              ports: device.open_ports.length
                ? t("merge.portsFragment", { n: device.open_ports.length })
                : "",
              name: target.display_name,
            })}
          </p>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => setTarget(null)}>
              {t("merge.pickAnother")}
            </Button>
            <Button
              variant="primary"
              size="sm"
              icon={<Merge size={12} />}
              loading={merge.isPending}
              onClick={() => merge.mutate()}
            >
              {t("merge.confirm")}
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}
