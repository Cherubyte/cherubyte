import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type DevicePatch } from "../api/client";
import type { DeviceType } from "../api/types";
import { TypeCode, useBrandLogos, useOsLogos } from "../components/TypeCode";
import { MergeDialog } from "../components/MergeDialog";
import { DeviceTypePicker } from "../components/DeviceTypePicker";
import { useIsMobile } from "../hooks/useMediaQuery";
import { useNow } from "../hooks/useNow";
import {
  ApprovalTag,
  Button,
  EmptyState,
  Field,
  SectionHeader,
  Skeleton,
  StatusPill,
  Toggle,
} from "../components/ui";
import { ArrowLeft, ArrowUpRight, Check, Close, Image, Merge, Plus, Trash } from "../components/Glyph";
import { useToast } from "../components/Toaster";
import { deviceTypeLabel, dateTime, timeAgo } from "../lib/format";
import { useT } from "../i18n";
import { copyText, downloadRdp, portAction } from "../lib/ports";
const OS_OPTIONS = [
  "Windows", "macOS", "iOS", "iPadOS", "Android", "Linux", "ChromeOS",
  "tvOS", "watchOS", "Tizen", "webOS", "Roku OS", "PlayStation OS",
];

export function DeviceDetail() {
  const { id } = useParams();
  const deviceId = Number(id);
  const nav = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const t = useT();
  const isMobile = useIsMobile();
  const logos = useBrandLogos();
  const osLogos = useOsLogos();
  const fileRef = useRef<HTMLInputElement>(null);
  useNow();

  const device = useQuery({
    queryKey: ["device", deviceId],
    queryFn: () => api.device(deviceId),
    refetchInterval: 20000,
  });
  const history = useQuery({
    queryKey: ["device", deviceId, "history"],
    queryFn: () => api.deviceHistory(deviceId),
  });
  const users = useQuery({ queryKey: ["users"], queryFn: api.users });

  const [draft, setDraft] = useState<DevicePatch>({});
  const [mergeOpen, setMergeOpen] = useState(false);
  const [newMac, setNewMac] = useState("");
  useEffect(() => setDraft({}), [deviceId]);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["device", deviceId] });
    qc.invalidateQueries({ queryKey: ["devices"] });
    qc.invalidateQueries({ queryKey: ["stats"] });
  };
  const save = useMutation({
    mutationFn: (p: DevicePatch) => api.updateDevice(deviceId, p),
    onSuccess: () => { setDraft({}); invalidate(); toast({ tone: "success", title: "device.saved" }); },
  });
  const approve = useMutation({ mutationFn: () => api.approveDevice(deviceId), onSuccess: () => { invalidate(); toast({ tone: "success", title: "device.approved" }); } });
  const ignore = useMutation({ mutationFn: () => api.ignoreDevice(deviceId), onSuccess: invalidate });
  const remove = useMutation({
    mutationFn: () => api.deleteDevice(deviceId),
    onSuccess: () => { invalidate(); toast({ tone: "success", title: "device.deleted" }); nav("/"); },
  });
  const upload = useMutation({ mutationFn: (f: File) => api.uploadImage(deviceId, f), onSuccess: invalidate });
  const delImage = useMutation({ mutationFn: (i: number) => api.deleteImage(deviceId, i), onSuccess: invalidate });
  const absorbMac = useMutation({
    mutationFn: (a: string) => api.absorbMac(deviceId, a),
    onSuccess: () => { setNewMac(""); invalidate(); toast({ tone: "success", title: "mac.attached" }); },
    onError: (e) => toast({ tone: "error", title: "mac.failed", desc: String(e).slice(0, 100) }),
  });
  const detachMac = useMutation({ mutationFn: (a: string) => api.detachMac(deviceId, a), onSuccess: invalidate });

  if (device.isLoading)
    return (
      <div className="space-y-4">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  if (device.isError || !device.data)
    return (
      <EmptyState
        title={t("device.notFound")}
        action={<Link to="/" className="btn btn-secondary btn-sm">{t("common.back")}</Link>}
      />
    );

  const d = device.data;
  const val = <K extends keyof DevicePatch>(k: K): DevicePatch[K] =>
    draft[k] !== undefined ? draft[k] : (d[k as keyof typeof d] as DevicePatch[K]);
  const dirty = Object.keys(draft).length > 0;
  const osLogo = d.os_family ? osLogos.get(d.os_family.toLowerCase()) : undefined;

  const facts: [string, React.ReactNode][] = [
    [t("device.fact.ip"), (d.ips.find((i) => i.is_primary) ?? d.ips[0])?.address ?? "—"],
    [t("device.fact.mac"), d.macs[0]?.address ?? "—"],
    [t("device.fact.type"), deviceTypeLabel(d.device_type)],
    [t("device.fact.system"), d.os_family ?? "—"],
    [t("device.fact.owner"), d.user?.name ?? "—"],
    [t("device.fact.firstSeen"), dateTime(d.first_seen)],
  ];

  const identity = (
    <section className="panel p-4">
      <SectionHeader
        title={t("device.section.identity")}
        actions={
          dirty && (
            <>
              <Button size="sm" variant="ghost" onClick={() => setDraft({})}>{t("common.cancel")}</Button>
              <Button size="sm" variant="primary" icon={<Check size={12} />} loading={save.isPending} onClick={() => save.mutate(draft)}>
                {t("common.save")}
              </Button>
            </>
          )
        }
      />
      <div className="space-y-4">
        <Field label={t("device.field.nickname")} hint={t("device.field.nicknameHint", { label: d.default_label })}>
          <input
            className="input font-display text-[15px] tracking-tight"
            value={(val("name") as string) ?? ""}
            placeholder={d.default_label}
            onChange={(e) => setDraft((s) => ({ ...s, name: e.target.value }))}
          />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("device.field.type")}>
            <DeviceTypePicker
              value={val("device_type") as DeviceType}
              onChange={(ty) => setDraft((s) => ({ ...s, device_type: ty }))}
            />
          </Field>
          <Field label={t("device.field.owner")}>
            <select
              className="input"
              value={String(val("user_id") ?? d.user?.id ?? "")}
              onChange={(e) => setDraft((s) => ({ ...s, user_id: e.target.value ? Number(e.target.value) : null }))}
            >
              <option value="">{t("device.field.ownerNone")}</option>
              {users.data?.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
            </select>
          </Field>
          <Field label={t("device.field.brand")}>
            <input className="input" value={(val("vendor") as string) ?? ""} onChange={(e) => setDraft((s) => ({ ...s, vendor: e.target.value }))} />
          </Field>
          <Field label={t("device.field.model")}>
            <input className="input" value={(val("model") as string) ?? ""} onChange={(e) => setDraft((s) => ({ ...s, model: e.target.value }))} />
          </Field>
        </div>
        <Field label={t("device.field.os")}>
          <div className="flex items-center gap-2">
            {osLogo && <img src={osLogo} alt="" className="h-5 w-5 shrink-0 object-contain" />}
            <input
              className="input"
              list="os-list"
              placeholder="—"
              value={(val("os_guess") as string) ?? ""}
              onChange={(e) => setDraft((s) => ({ ...s, os_guess: e.target.value }))}
            />
            <datalist id="os-list">
              <option value={t("device.os.none")} />
              {OS_OPTIONS.map((o) => <option key={o} value={o} />)}
            </datalist>
          </div>
        </Field>
        <Field label={t("device.field.notes")}>
          <textarea className="input" value={(val("notes") as string) ?? ""} onChange={(e) => setDraft((s) => ({ ...s, notes: e.target.value }))} />
        </Field>
        <div className="flex items-center justify-between bg-surface-2 px-3 py-2.5">
          <div>
            <p className="text-[12px] text-fg">{t("device.countsForPresence")}</p>
            <p className="mono text-[10px] text-fg-3">{t("device.countsForPresenceHint")}</p>
          </div>
          <Toggle
            checked={(val("counts_for_presence") as boolean) ?? d.counts_for_presence}
            onChange={(v) => setDraft((s) => ({ ...s, counts_for_presence: v }))}
          />
        </div>
        <Field label={t("device.notify.title")} hint={t("device.notify.hint")}>
          <select
            className="input"
            value={(val("notify_policy") as string) ?? "default"}
            onChange={(e) =>
              setDraft((s) => ({
                ...s,
                notify_policy: e.target.value as DevicePatch["notify_policy"],
              }))
            }
          >
            <option value="default">{t("device.notify.default")}</option>
            <option value="always">{t("device.notify.always")}</option>
            <option value="mute">{t("device.notify.mute")}</option>
          </select>
        </Field>
      </div>
    </section>
  );

  const network = (
    <section className="panel p-4">
      <SectionHeader title={t("device.section.network")} />
      <div className="space-y-5">
        <div>
          <p className="label mb-2">{t("device.ipAddresses")}</p>
          <div className="space-y-px">
            {d.ips.map((ip) => (
              <div key={ip.address} className="flex items-center justify-between bg-surface-2 px-3 py-2">
                <span className="mono text-[12px] text-fg-2">
                  {ip.address}
                  {ip.is_primary && <span className="ml-2 text-[10px] text-fg-3">{t("device.primary")}</span>}
                </span>
                <span className="mono text-[10px] text-fg-3">{timeAgo(ip.last_seen, true)}</span>
              </div>
            ))}
          </div>
        </div>
        <div>
          <p className="label mb-2">{t("device.macAddresses")}</p>
          <div className="space-y-px">
            {d.macs.map((m) => (
              <div key={m.address} className="flex items-center gap-2 bg-surface-2 px-3 py-2">
                <span className="mono flex-1 text-[12px] text-fg-2">{m.address}</span>
                <span className="mono text-[10px] text-fg-3">
                  {m.is_random ? t("device.macRandom") : m.vendor ?? "—"}
                </span>
                {d.macs.length > 1 && (
                  <button onClick={() => detachMac.mutate(m.address)} title={t("device.macDetach")} className="text-fg-3 hover:text-alert">
                    <Close size={11} />
                  </button>
                )}
              </div>
            ))}
          </div>
          <form
            className="mt-2 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              const v = newMac.trim().toLowerCase();
              if (/^([0-9a-f]{2}:){5}[0-9a-f]{2}$/.test(v)) absorbMac.mutate(v);
            }}
          >
            <input
              className="input mono h-[28px] py-0 text-[11px]"
              placeholder="aa:bb:cc:dd:ee:ff"
              value={newMac}
              onChange={(e) => setNewMac(e.target.value)}
            />
            <Button size="sm" variant="secondary" icon={<Plus size={12} />} className="shrink-0" />
          </form>
          <p className="mono mt-1.5 text-[10px] text-fg-3">{t("device.macAbsorbHint")}</p>
        </div>
        {d.open_ports.length > 0 && (
          <div>
            <p className="label mb-2">{t("device.openPorts", { n: d.open_ports.length })}</p>
            <div className="flex flex-wrap gap-1.5">
              {d.open_ports.map((p) => {
                const ip = (d.ips.find((i) => i.is_primary) ?? d.ips[0])?.address ?? "";
                const inner = (
                  <>
                    {p.port}
                    {p.service && <span className="text-fg-3">/{p.service}</span>}
                  </>
                );
                if (!ip)
                  return (
                    <span key={p.port} className="tag tag-neutral">
                      {inner}
                    </span>
                  );
                const act = portAction(ip, p.port, p.service);
                const cls =
                  "tag tag-neutral inline-flex items-center gap-1 transition-colors hover:border-signal hover:text-signal";
                if (act.kind === "web" || act.kind === "scheme")
                  return (
                    <a
                      key={p.port}
                      href={act.href}
                      target="_blank"
                      rel="noreferrer"
                      title={t(act.hint)}
                      className={cls}
                    >
                      {inner}
                      <ArrowUpRight size={9} />
                    </a>
                  );
                if (act.kind === "rdp")
                  return (
                    <button
                      key={p.port}
                      type="button"
                      title={t(act.hint)}
                      onClick={() => downloadRdp(act.host)}
                      className={cls}
                    >
                      {inner}
                      <ArrowUpRight size={9} />
                    </button>
                  );
                return (
                  <button
                    key={p.port}
                    type="button"
                    title={t(act.hint)}
                    onClick={async () => {
                      await copyText(act.text);
                      toast({ tone: "success", title: "porta.copiada", desc: act.text });
                    }}
                    className={cls}
                  >
                    {inner}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </section>
  );

  const photos = (
    <section className="panel p-4">
      <SectionHeader
        title={t("device.section.photos")}
        sub={String(d.images.length)}
        actions={
          <Button size="sm" variant="ghost" icon={<Image size={12} />} onClick={() => fileRef.current?.click()}>
            {t("common.add")}
          </Button>
        }
      />
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) upload.mutate(f);
          e.target.value = "";
        }}
      />
      {d.images.length === 0 ? (
        <EmptyState title={t("device.photos.empty.title")} description={t("device.photos.empty.desc")} />
      ) : (
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
          {d.images.map((img) => (
            <div key={img.id} className="group relative aspect-square overflow-hidden border border-edge bg-surface-2">
              <img src={img.url} alt="" className="h-full w-full object-contain" />
              <button
                onClick={() => delImage.mutate(img.id)}
                className="absolute right-1 top-1 grid h-6 w-6 place-items-center bg-black/70 text-white opacity-0 transition-opacity group-hover:opacity-100"
              >
                <Trash size={11} />
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );

  const historyCard = (
    <section className="panel p-4">
      <SectionHeader title={t("device.section.history")} />
      {(history.data ?? []).length === 0 ? (
        <EmptyState title={t("device.history.empty")} />
      ) : (
        <div className="space-y-px">
          {history.data!.slice(0, 30).map((h) => (
            <div key={h.id} className="flex items-center gap-3 bg-surface-2 py-2 pl-0 pr-3 text-[11.5px]">
              <span className={"h-full w-[3px] shrink-0 self-stretch " + (h.event === "join" ? "bg-signal" : "bg-alert")} />
              <span className={"mono w-12 shrink-0 " + (h.event === "join" ? "text-signal" : "text-alert")}>
                {h.event === "join" ? "JOIN" : "LEAVE"}
              </span>
              <span className="mono text-fg-3">{dateTime(h.timestamp)}</span>
              {h.ip && <span className="mono ml-auto text-[10px] text-fg-3">{h.ip}</span>}
            </div>
          ))}
        </div>
      )}
    </section>
  );

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <button onClick={() => nav(-1)} className="btn btn-ghost btn-sm -ml-2">
          <ArrowLeft size={12} /> {t("common.back")}
        </button>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" icon={<Merge size={12} />} onClick={() => setMergeOpen(true)}>
            {isMobile ? t("device.merge") : t("device.mergeWith")}
          </Button>
          {!isMobile && (
            <>
              {d.approval_status !== "approved" && (
                <Button variant="primary" size="sm" icon={<Check size={12} />} onClick={() => approve.mutate()}>{t("common.approve")}</Button>
              )}
              {d.approval_status !== "ignored" && (
                <Button variant="secondary" size="sm" icon={<Close size={12} />} onClick={() => ignore.mutate()}>{t("common.ignore")}</Button>
              )}
              <Button variant="danger" size="sm" icon={<Trash size={12} />} onClick={() => confirm(t("device.deleteConfirm")) && remove.mutate()} />
            </>
          )}
        </div>
      </div>

      <MergeDialog open={mergeOpen} onClose={() => setMergeOpen(false)} device={d} />

      {/* header */}
      <div className="panel flex items-start gap-4 p-4">
        <TypeCode device={d} logos={logos} osLogos={osLogos} size={isMobile ? 46 : 56} />
        <div className="min-w-0 flex-1">
          <div className="mb-1.5 flex flex-wrap items-center gap-2">
            <span className="tag tag-neutral">HOST {String(d.id).padStart(3, "0")}</span>
            <StatusPill online={d.is_online} />
            {!d.is_online && <span className="mono text-[10px] text-fg-3">{t("device.seenAgo", { ago: timeAgo(d.last_seen) })}</span>}
            <ApprovalTag status={d.approval_status} />
          </div>
          <h1 className="font-display truncate text-title leading-none tracking-tight text-fg sm:text-[38px]">
            {d.display_name}
          </h1>
          <dl className="mt-4 grid grid-cols-1 gap-x-8 sm:grid-cols-2">
            {facts.map(([k, v]) => (
              <div key={k} className="flex items-baseline gap-2 border-b border-dotted border-edge py-1.5">
                <dt className="label shrink-0">{k}</dt>
                <span className="h-px flex-1" />
                <dd className="mono truncate text-right text-[11.5px] text-fg-2">{v}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>

      {isMobile ? (
        <>
          {identity}
          {network}
          {photos}
          {historyCard}
        </>
      ) : (
        <div className="grid gap-3 lg:grid-cols-[1.3fr_1fr]">
          <div className="space-y-3">
            {identity}
            {photos}
          </div>
          <div className="space-y-3">
            {network}
            {historyCard}
          </div>
        </div>
      )}

      {isMobile && (
        <div className="sticky bottom-16 -mx-4 flex gap-2 border-t-2 border-edge-2 bg-surface px-4 py-3">
          {d.approval_status !== "approved" && (
            <Button variant="primary" className="flex-1" icon={<Check size={13} />} onClick={() => approve.mutate()}>{t("common.approve")}</Button>
          )}
          {d.approval_status !== "ignored" && (
            <Button variant="secondary" className="flex-1" onClick={() => ignore.mutate()}>{t("common.ignore")}</Button>
          )}
          <Button variant="danger" icon={<Trash size={13} />} onClick={() => confirm(t("device.deleteConfirmShort")) && remove.mutate()} />
        </div>
      )}
    </div>
  );
}
