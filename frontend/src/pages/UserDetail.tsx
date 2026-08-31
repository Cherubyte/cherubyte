import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { UserDeviceMini } from "../api/types";
import { TypeMark } from "../components/TypeCode";
import { PresenceHeatmap } from "../components/PresenceHeatmap";
import { useIsMobile } from "../hooks/useMediaQuery";
import { Avatar, Badge, Button, EmptyState, QueryState, SectionHeader, StatusPill, Toggle } from "../components/ui";
import { ArrowLeft, Trash } from "../components/Glyph";
import { deviceTypeLabel, timeAgo } from "../lib/format";
import { useT } from "../i18n";
import { useNow } from "../hooks/useNow";

export function UserDetail() {
  const { id } = useParams();
  const userId = Number(id);
  const nav = useNavigate();
  const qc = useQueryClient();
  const t = useT();
  const isMobile = useIsMobile();
  useNow();

  const user = useQuery({
    queryKey: ["user", userId],
    queryFn: () => api.user(userId),
    refetchInterval: 20000,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["user", userId] });
    qc.invalidateQueries({ queryKey: ["users"] });
    qc.invalidateQueries({ queryKey: ["users", userId, "presence"] });
    qc.invalidateQueries({ queryKey: ["devices"] });
  };
  const togglePresence = useMutation({
    mutationFn: ({ deviceId, on }: { deviceId: number; on: boolean }) =>
      api.updateDevice(deviceId, { counts_for_presence: on }),
    onSuccess: invalidate,
  });
  const setGuest = useMutation({
    mutationFn: (on: boolean) => api.updateUser(userId, { is_guest: on }),
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: () => api.deleteUser(userId),
    onSuccess: () => {
      invalidate();
      nav("/users");
    },
  });

  if (user.isLoading || user.isError)
    return (
      <div className="space-y-4">
        <button onClick={() => nav("/users")} className="btn btn-ghost btn-sm -ml-2">
          <ArrowLeft size={12} /> {t("nav.people")}
        </button>
        <QueryState q={user} />
      </div>
    );
  if (!user.data)
    return (
      <EmptyState
        title={t("common.notFound")}
        action={<Link to="/users" className="btn btn-secondary btn-sm">{t("common.back")}</Link>}
      />
    );

  const u = user.data;
  const devices = u.devices ?? [];

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <button onClick={() => nav("/users")} className="btn btn-ghost btn-sm -ml-2">
          <ArrowLeft size={12} /> {t("nav.people")}
        </button>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setGuest.mutate(!u.is_guest)}
            loading={setGuest.isPending}
          >
            {u.is_guest ? t("users.makePerson") : t("users.makeGuest")}
          </Button>
          <Button
            variant="danger"
            size="sm"
            icon={<Trash size={12} />}
            onClick={() => confirm(t("users.removeConfirm", { name: u.name })) && remove.mutate()}
          >
            {t("common.remove")}
          </Button>
        </div>
      </div>

      <div className="panel flex items-center gap-4 px-5 py-4">
        <Avatar name={u.name} size={44} />
        <div>
          <div className="flex items-center gap-2">
            <h1 className="font-display text-[28px] leading-tight text-fg">{u.name}</h1>
            {u.is_guest && <Badge tone="neutral">{t("person.guest")}</Badge>}
          </div>
          <div className="mt-1.5">
            <StatusPill online={u.is_present} />
          </div>
        </div>
      </div>

      <section className="panel p-5">
        <SectionHeader title={t("person.presence")} sub={t("person.presenceSub")} />
        <PresenceHeatmap userId={userId} days={10} cell={isMobile ? 12 : 16} />
      </section>

      <section className="panel p-5">
        <SectionHeader title={t("person.devices")} sub={String(devices.length)} />
        {devices.length === 0 ? (
          <EmptyState title={t("person.empty.title")} description={t("person.empty.desc")} />
        ) : (
          <div className="space-y-1">
            {devices.map((d) => (
              <DeviceRow key={d.id} d={d} onToggle={(on) => togglePresence.mutate({ deviceId: d.id, on })} />
            ))}
          </div>
        )}
        <p className="mt-3 text-[11px] leading-relaxed text-fg-3">{t("person.presenceHint")}</p>
      </section>
    </div>
  );
}

function DeviceRow({ d, onToggle }: { d: UserDeviceMini; onToggle: (on: boolean) => void }) {
  const t = useT();
  return (
    <div className="flex items-center gap-3 rounded-lg bg-surface-2 px-3 py-2.5">
      {d.primary_image ? (
        <img
          src={d.primary_image}
          alt=""
          className="h-9 w-9 shrink-0 rounded-lg border border-edge object-cover"
        />
      ) : (
        <TypeMark type={d.device_type} size={26} />
      )}
      <Link to={`/devices/${d.id}`} className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span
            className={"h-[7px] w-[7px] shrink-0 rounded-full " + (d.is_online ? "bg-fg" : "border border-edge-2")}
          />
          <span className="font-display truncate text-[13px] text-fg hover:underline">
            {d.display_name}
          </span>
        </div>
        <div className="mono mt-0.5 text-[10px] text-fg-3">
          {deviceTypeLabel(d.device_type)} · {d.is_online ? t("common.online") : timeAgo(d.last_seen, true)}
        </div>
      </Link>
      <Toggle checked={d.counts_for_presence} onChange={onToggle} label={t("person.countsForPresence")} />
    </div>
  );
}
