import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { TypeCode, useBrandLogos, useOsLogos } from "../components/TypeCode";
import { Badge, Button, EmptyState, Readout, SectionHeader, SkeletonRows } from "../components/ui";
import { Check, Close, Merge, Trash } from "../components/Glyph";
import { useToast } from "../components/Toaster";
import { deviceTypeLabel, timeAgo } from "../lib/format";
import { useT, type MessageKey } from "../i18n";
import { useNow } from "../hooks/useNow";

/** The backend labels confidence as a stable English key ("high" / "medium" /
 *  "low"); localise it for display. */
function confidenceLabel(t: (k: MessageKey) => string, raw: string): string {
  const map: Record<string, MessageKey> = {
    high: "approvals.dupes.high",
    medium: "approvals.dupes.medium",
    low: "approvals.dupes.low",
  };
  const key = map[raw];
  return key ? t(key) : raw;
}

export function Approvals() {
  const qc = useQueryClient();
  const toast = useToast();
  const t = useT();
  const logos = useBrandLogos();
  const osLogos = useOsLogos();
  useNow();
  const pending = useQuery({
    queryKey: ["devices", "pending"],
    queryFn: () => api.devices({ status: "pending" }),
    refetchInterval: 15000,
  });

  const done = (msg: string) => {
    qc.invalidateQueries({ queryKey: ["devices"] });
    qc.invalidateQueries({ queryKey: ["stats"] });
    toast({ tone: "success", title: msg });
  };
  const approve = useMutation({ mutationFn: (id: number) => api.approveDevice(id), onSuccess: () => done("device.approved") });
  const ignore = useMutation({ mutationFn: (id: number) => api.ignoreDevice(id), onSuccess: () => done("device.ignored") });
  const del = useMutation({ mutationFn: (id: number) => api.deleteDevice(id), onSuccess: () => done("device.deleted") });

  const suggestions = useQuery({
    queryKey: ["devices", "merge-suggestions"],
    queryFn: api.mergeSuggestions,
  });
  const merge = useMutation({
    mutationFn: ({ targetId, sourceIds }: { targetId: number; sourceIds: number[] }) =>
      api.mergeDevices(targetId, sourceIds),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["devices", "merge-suggestions"] });
      done("devices.merged");
    },
  });

  const list = pending.data ?? [];

  if (pending.isLoading) return <SkeletonRows rows={3} />;

  return (
    <div className="space-y-6">
      <div className="panel px-5 py-4">
        <Readout
          value={list.length}
          caption={list.length === 1 ? t("approvals.waiting.one") : t("approvals.waiting.many")}
          size="xl"
          tone={list.length > 0 ? "alert" : "default"}
        />
      </div>

      {(suggestions.data ?? []).length > 0 && (
        <section className="panel p-5">
          <SectionHeader title={t("approvals.dupes.title")} sub={t("approvals.dupes.sub")} />
          <div className="space-y-3">
            {(suggestions.data ?? []).map((sg) => (
              <div
                key={sg.target.id}
                className="flex flex-wrap items-center justify-between gap-3 border-b border-edge pb-3 last:border-0 last:pb-0"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link to={`/devices/${sg.target.id}`} className="font-medium hover:underline">
                      {sg.target.name}
                    </Link>
                    <span className="mono text-[11px] text-fg-3">
                      {t("approvals.dupes.absorbs", { n: sg.duplicates.length })}
                    </span>
                    <Badge tone={sg.confidence === "high" ? "signal" : "neutral"}>
                      {t("approvals.dupes.confidence", { level: confidenceLabel(t, sg.confidence) })}
                    </Badge>
                  </div>
                  <div className="mono mt-1 text-[11px] text-fg-3">
                    {sg.reason} · {sg.duplicates.map((d) => d.name).join(", ")}
                  </div>
                </div>
                <Button
                  variant="secondary"
                  size="sm"
                  icon={<Merge size={12} />}
                  loading={merge.isPending}
                  onClick={() =>
                    merge.mutate({
                      targetId: sg.target.id,
                      sourceIds: sg.duplicates.map((d) => d.id),
                    })
                  }
                >
                  {t("approvals.dupes.merge")}
                </Button>
              </div>
            ))}
          </div>
        </section>
      )}

      {list.length === 0 ? (
        <EmptyState
          title={t("approvals.empty.title")}
          description={t("approvals.empty.desc")}
        />
      ) : (
        <div className="space-y-2.5">
          {list.map((d) => {
            const mac = d.macs[0];
            return (
              <div
                key={d.id}
                className="panel flex flex-col gap-3 p-4 sm:flex-row sm:items-center"
              >
                <TypeCode device={d} logos={logos} osLogos={osLogos} size={40} />
                <div className="min-w-0 flex-1">
                  <Link
                    to={`/devices/${d.id}`}
                    className="font-display text-[14px] text-fg hover:underline"
                  >
                    {d.display_name}
                  </Link>
                  <div className="mono mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10.5px] text-fg-3">
                    <span>{d.ips[0]?.address}</span>
                    <span>·</span>
                    <span>{mac?.address}</span>
                    <span>·</span>
                    <span>{mac?.is_random ? t("approvals.randomMac") : d.short_vendor ?? t("approvals.unknownVendor")}</span>
                    <span>·</span>
                    <span>{deviceTypeLabel(d.device_type)}</span>
                    {d.os_family && <><span>·</span><span>{d.os_family}</span></>}
                    <span>·</span>
                    <span className={d.is_online ? "text-fg-2" : ""}>
                      {d.is_online ? t("common.online") : timeAgo(d.last_seen, true)}
                    </span>
                  </div>
                </div>
                <div className="flex shrink-0 gap-2">
                  <Button variant="primary" size="sm" icon={<Check size={12} />} onClick={() => approve.mutate(d.id)}>
                    {t("common.approve")}
                  </Button>
                  <Button variant="secondary" size="sm" icon={<Close size={12} />} onClick={() => ignore.mutate(d.id)}>
                    {t("common.ignore")}
                  </Button>
                  <Button
                    variant="danger"
                    size="sm"
                    icon={<Trash size={12} />}
                    onClick={() => confirm(t("list.deleteConfirm", { name: d.display_name })) && del.mutate(d.id)}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
