import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { User } from "../api/types";
import { PresenceHeatmap } from "../components/PresenceHeatmap";
import { useIsMobile } from "../hooks/useMediaQuery";
import { Avatar, Badge, Button, EmptyState, Readout, Skeleton, StatusPill } from "../components/ui";
import { ArrowRight, Plus, Trash } from "../components/Glyph";
import { useToast } from "../components/Toaster";
import { stringHsl } from "../lib/format";
import { useT } from "../i18n";

export function Users() {
  const qc = useQueryClient();
  const toast = useToast();
  const t = useT();
  const isMobile = useIsMobile();
  const users = useQuery({ queryKey: ["users"], queryFn: api.users, refetchInterval: 15000 });
  const [name, setName] = useState("");
  const [asGuest, setAsGuest] = useState(false);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["users"] });
  const create = useMutation({
    mutationFn: () => api.createUser({ name: name.trim(), is_guest: asGuest }),
    onSuccess: () => {
      setName("");
      invalidate();
      toast({ tone: "success", title: asGuest ? "visita.created" : "person.created" });
    },
  });
  const remove = useMutation({ mutationFn: (id: number) => api.deleteUser(id), onSuccess: invalidate });

  const list = users.data ?? [];
  const main = list.filter((u) => !u.is_guest);
  const guests = list.filter((u) => u.is_guest);
  const present = main.filter((u) => u.is_present).length;

  const row = (u: User) => (
    <div key={u.id} className="panel p-3.5">
      <div className="mb-2.5 flex items-center gap-3">
        <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: stringHsl(u.name) }} />
        <Avatar name={u.name} size={26} />
        <Link to={`/users/${u.id}`} className="group flex min-w-0 flex-1 items-center gap-3">
          <span className="truncate font-display text-[15px] tracking-tight text-fg group-hover:text-signal">
            {u.name}
          </span>
          <StatusPill online={u.is_present} />
          <span className="mono shrink-0 text-[10px] text-fg-3">{t("users.devicesShort", { n: u.device_count })}</span>
          <ArrowRight size={12} className="ml-auto shrink-0 text-fg-3" />
        </Link>
        <button
          onClick={() => confirm(t("users.removeConfirm", { name: u.name })) && remove.mutate(u.id)}
          className="text-fg-3 hover:text-alert"
        >
          <Trash size={13} />
        </button>
      </div>
      <div className="sm:pl-[38px]">
        <PresenceHeatmap userId={u.id} days={7} cell={isMobile ? 11 : 14} />
      </div>
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="panel flex flex-wrap items-end gap-x-10 gap-y-4 px-5 py-4">
        <Readout
          value={main.length ? present : "—"}
          unit={t("users.peopleUnit", { total: main.length })}
          caption={t("users.presentNow")}
          size="xl"
        />
        <form
          className="ml-auto flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim()) create.mutate();
          }}
        >
          <label className="block">
            <span className="label mb-1.5 block">{t("users.newPerson")}</span>
            <input
              className="input h-[28px] w-44 py-0"
              placeholder={t("users.name")}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="mono flex h-[28px] items-center gap-1.5 text-[11px] text-fg-2">
            <input type="checkbox" checked={asGuest} onChange={(e) => setAsGuest(e.target.checked)} />
            {t("users.guest")}
          </label>
          <Button variant="primary" size="sm" icon={<Plus size={12} />} disabled={!name.trim()} loading={create.isPending}>
            {t("common.add")}
          </Button>
        </form>
      </div>

      {users.isLoading && <Skeleton className="h-40 w-full" />}

      {!users.isLoading && list.length === 0 && (
        <EmptyState
          title={t("users.empty.title")}
          description={t("users.empty.desc")}
        />
      )}

      {main.length > 0 && (
        <div className="grid gap-2 lg:grid-cols-2 lg:items-start">{main.map(row)}</div>
      )}

      {guests.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 pt-2">
            <span className="label">{t("users.guests")}</span>
            <Badge tone="neutral">{guests.length}</Badge>
          </div>
          <div className="grid gap-2 lg:grid-cols-2 lg:items-start">{guests.map(row)}</div>
        </div>
      )}
    </div>
  );
}
