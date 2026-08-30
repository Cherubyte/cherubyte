import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { TypeCode, useBrandLogos, useOsLogos } from "../components/TypeCode";
import { Badge, Button, EmptyState, Readout, SectionHeader, SkeletonRows } from "../components/ui";
import { Check, Close, Merge, Trash } from "../components/Glyph";
import { useToast } from "../components/Toaster";
import { coord, deviceTypeLabel, timeAgo } from "../lib/format";
import { useT, type MessageKey } from "../i18n";
import { useNow } from "../hooks/useNow";

/** The backend labels confidence in Portuguese ("alta" / "média"); localise it. */
function confidenceLabel(t: (k: MessageKey) => string, raw: string): string {
  const map: Record<string, MessageKey> = {
    alta: "approvals.dupes.high",
    "média": "approvals.dupes.medium",
    baixa: "approvals.dupes.low",
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
    <div className="space-y-5">
      <div className="panel px-5 py-4">
        <Readout
          value={list.length}
          caption={list.length === 1 ? t("approvals.waiting.one") : t("approvals.waiting.many")}
          size="xl"
          tone={list.length > 0 ? "alert" : "default"}
        />
      </div>

      {(suggestions.data ?? []).length > 0 && (
        <section className="panel p-4">
          <SectionHeader
            title={t("approvals.dupes.title")}
            sub={t("approvals.dupes.sub")}
          />
          <div className="space-y-3">
            {(suggestions.data ?? []).map((s) => (
              <div
                key={s.target.id}
                className="flex flex-wrap items-center justify-between gap-3 border-b border-edge/60 pb-3 last:border-0 last:pb-0"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link to={`/devices/${s.target.id}`} className="font-medium hover:underline">
                      {s.target.name}
                    </Link>
                    <span className="mono text-[11px] text-fg-3">
                      {t("approvals.dupes.absorbs", { n: s.duplicates.length })}
                    </span>
                    <Badge tone={s.confidence === "alta" ? "signal" : "neutral"}>
                      {t("approvals.dupes.confidence", { level: confidenceLabel(t, s.confidence) })}
                    </Badge>
                  </div>
                  <div className="mono mt-1 text-[11px] text-fg-3">
                    {s.reason} · {s.duplicates.map((d) => d.name).join(", ")}
                  </div>
                </div>
                <Button
                  variant="secondary"
                  size="sm"
                  icon={<Merge size={12} />}
                  loading={merge.isPending}
                  onClick={() =>
                    merge.mutate({
                      targetId: s.target.id,
                      sourceIds: s.duplicates.map((d) => d.id),
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
        <div className="space-y-2">
          {list.map((d, i) => {
            const c = coord(i);
            const mac = d.macs[0];
            return (
              <div
                key={d.id}
                className="panel relative flex flex-col gap-3 py-4 pl-5 pr-4 sm:flex-row sm:items-center"
              >
                <span className="absolute left-0 top-0 h-full w-[3px] bg-signal" />
                <span className="mono hidden shrink-0 self-start pt-1 text-[10px] text-fg-3 sm:block">
                  {c.alpha}·{c.index}
                </span>
                <TypeCode device={d} logos={logos} osLogos={osLogos} size={38} />
                <div className="min-w-0 flex-1">
                  <Link
                    to={`/devices/${d.id}`}
                    className="font-display text-[15px] tracking-tight text-fg hover:text-signal"
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
                    <span className={d.is_online ? "text-signal" : ""}>
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
