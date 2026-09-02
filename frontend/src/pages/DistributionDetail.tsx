import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import { DeviceListView } from "../components/DeviceListView";
import { useBrandLogos, useOsLogos } from "../components/TypeCode";
import { ArrowLeft, Image } from "../components/Glyph";
import { EmptyState, Readout } from "../components/ui";
import { useT } from "../i18n";

const UNKNOWN_BRAND = "Desconhecido";

/** Devices that belong to one brand or OS family — reached by clicking a
 * row on the Distribution page. */
export function DistributionDetail() {
  const { kind, name } = useParams<{ kind: string; name: string }>();
  const nav = useNavigate();
  const t = useT();
  const isBrand = kind === "brand";
  const decoded = decodeURIComponent(name ?? "");

  const devicesQ = useQuery({ queryKey: ["devices"], queryFn: () => api.devices() });
  const brandLogos = useBrandLogos();
  const osLogos = useOsLogos();

  const all = devicesQ.data ?? [];
  const rows = useMemo(
    () =>
      all.filter((d) =>
        isBrand
          ? (d.short_vendor ?? UNKNOWN_BRAND).toLowerCase() === decoded.toLowerCase()
          : (d.os_family ?? "").toLowerCase() === decoded.toLowerCase(),
      ),
    [all, isBrand, decoded],
  );
  const online = rows.filter((d) => d.is_online).length;
  const logo = isBrand ? brandLogos.get(decoded.toLowerCase()) : osLogos.get(decoded.toLowerCase());

  if (!kind || !name || (kind !== "brand" && kind !== "os")) {
    return <EmptyState title={t("common.notFound")} />;
  }

  return (
    <div className="space-y-5">
      <button onClick={() => nav("/distribution")} className="btn btn-ghost btn-sm -ml-2">
        <ArrowLeft size={12} /> {t("nav.stats")}
      </button>

      <div className="panel flex flex-wrap items-center gap-x-8 gap-y-4 px-5 py-4">
        <div className="flex items-center gap-3">
          <div className="grid h-11 w-11 shrink-0 place-items-center overflow-hidden rounded-[10px] bg-surface-2 text-fg-3">
            {logo ? <img src={logo} alt="" className="h-full w-full object-cover" /> : <Image size={16} />}
          </div>
          <span className="font-display text-[17px] text-fg">{decoded}</span>
        </div>
        <Readout value={rows.length} caption={t("stats.devices")} size="md" />
        <Readout value={online} caption={t("stats.onlineNow")} size="md" tone={online ? "signal" : "default"} />
      </div>

      <DeviceListView devices={rows} loading={devicesQ.isLoading} emptyKey="dash.empty.noDevices" />
    </div>
  );
}
