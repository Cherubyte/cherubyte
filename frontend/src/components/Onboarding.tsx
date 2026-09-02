import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Device, User } from "../api/types";
import { deviceTypeLabel } from "../lib/format";
import {
  INSTALL_TARGETS,
  hasDownload,
  installCommand,
  type InstallTarget,
} from "../lib/agentInstall";
import { copyText } from "../lib/ports";
import { useT, type MessageKey } from "../i18n";
import { Button } from "./ui";
import { useToast } from "./Toaster";
import { AppMark, ArrowRight, Check, DeviceTypeIcon, DownloadIcon } from "./Glyph";

/* The setup a fresh install actually needs, in the order it needs it. Unlike the
 * old modal this runs before there is anything on the network to talk about —
 * step one is what puts it there. */
const STEPS = ["agent", "review", "people", "names"] as const;
type Step = (typeof STEPS)[number];

/** heading comment baked into the pasted command, per target */
const HEADING: Record<InstallTarget, MessageKey | null> = {
  docker: null,
  linux: "agents.install.linux",
  macos: "agents.install.macos",
  windows: "agents.install.windows",
};

export function Onboarding() {
  const qc = useQueryClient();
  const t = useT();

  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings, staleTime: 60_000 });
  const eligible = !!settings.data && !settings.data.onboarding_dismissed;

  const [step, setStep] = useState<Step>("agent");
  const i = STEPS.indexOf(step);

  const dismiss = useMutation({
    mutationFn: () => api.updateSettings({ onboarding_dismissed: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings"] }),
  });

  if (!eligible) return null;

  const finish = () => dismiss.mutate();
  const go = (s: Step) => setStep(s);
  const next = () => (i === STEPS.length - 1 ? finish() : go(STEPS[i + 1]));

  return (
    <div className="fixed inset-0 z-[95] flex flex-col bg-bg">
      <header className="flex h-[60px] flex-shrink-0 items-center px-6">
        <span className="flex items-center gap-2.5">
          <AppMark size={22} />
          <span className="font-display text-[16px] leading-none text-fg">Cherubyte</span>
        </span>
        <button type="button" className="btn btn-sm btn-ghost ml-auto" onClick={finish}>
          {t("onboarding.skipAll")}
        </button>
      </header>

      <div className="flex min-h-0 flex-1 justify-center gap-6 px-5 pb-8 pt-4 md:gap-14 md:px-14 md:pb-8 md:pt-7">
        <nav className="hidden w-[196px] flex-shrink-0 flex-col gap-0.5 pt-1.5 md:flex">
          <span className="key mb-3.5">{t("onboarding.rail")}</span>
          {STEPS.map((s, n) => (
            <button
              key={s}
              type="button"
              onClick={() => go(s)}
              className="flex cursor-pointer items-center gap-3 border-0 bg-transparent px-1 py-2 text-left text-[13px]"
              style={{ color: n === i ? "rgb(var(--fg))" : n < i ? "rgb(var(--fg-2))" : "rgb(var(--fg-3))" }}
            >
              <span
                className="h-[9px] w-[9px] flex-shrink-0 rounded-full"
                style={{
                  background: n <= i ? "rgb(var(--fg))" : "transparent",
                  boxShadow:
                    n === i
                      ? "0 0 0 3px rgb(var(--fg) / .14)"
                      : n < i
                        ? "none"
                        : "inset 0 0 0 1.5px rgb(var(--fg-3) / .7)",
                }}
              />
              <span style={{ fontWeight: n === i ? 500 : 400 }}>
                {t(`onboarding.${s}.rail` as MessageKey)}
              </span>
            </button>
          ))}
        </nav>

        <div className="flex w-full min-h-0 max-w-[620px] flex-col self-start" style={{ maxHeight: "100%" }}>
          <div className="min-h-0 flex-1 overflow-y-auto pr-1">
            <span className="key">
              {t("onboarding.stepOf", { n: i + 1, total: STEPS.length })}
            </span>
            <h2 className="font-display mt-3 text-[26px] leading-[1.16] text-fg [text-wrap:pretty]">
              {t(`onboarding.${step}.title` as MessageKey)}
            </h2>
            <p className="mt-2.5 max-w-[58ch] text-[14px] leading-[1.55] text-fg-2 [text-wrap:pretty]">
              {t(`onboarding.${step}.lede` as MessageKey)}
            </p>

            <div className="panel mt-5 flex-shrink-0 p-[18px]">
              {step === "agent" && <AgentStep />}
              {step === "review" && <ReviewStep onEmpty={() => go("people")} />}
              {step === "people" && <PeopleStep />}
              {step === "names" && <NamesStep />}
            </div>

            <p className="mt-3.5 max-w-[64ch] flex-shrink-0 text-[12.5px] leading-[1.6] text-fg-3">
              {t(`onboarding.${step}.why` as MessageKey)}
            </p>
          </div>

          <div className="flex flex-shrink-0 items-center gap-3 pt-5">
            <Button variant="primary" onClick={next}>
              {t(`onboarding.${step}.primary` as MessageKey)}
            </Button>
            {i > 0 && (
              <Button variant="ghost" onClick={() => go(STEPS[i - 1])}>
                {t("onboarding.back")}
              </Button>
            )}
            <button type="button" className="btn btn-ghost ml-auto" onClick={next}>
              {t(`onboarding.${step}.skip` as MessageKey)}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── 1 · agent ────────────────────────────────────────────────────────────
 * The step the old wizard could never show: it only rendered once devices
 * existed, which already required an agent. */
function AgentStep() {
  const t = useT();
  const toast = useToast();
  const [target, setTarget] = useState<InstallTarget>("docker");
  const [copied, setCopied] = useState<"" | "token" | "cmd">("");

  const panelUrl = typeof window === "undefined" ? "" : window.location.origin;

  const release = useQuery({
    queryKey: ["agent-release"],
    queryFn: api.agentRelease,
    staleTime: 300_000,
  });
  // One token for the whole step: minted on arrival, re-used across platform
  // switches so flipping tabs doesn't quietly invalidate what you already pasted.
  const token = useQuery({
    queryKey: ["onboarding-enrol-token"],
    queryFn: () => api.createEnrolToken("setup"),
    staleTime: Infinity,
    gcTime: Infinity,
    retry: false,
  });
  // Until one reports in there is nothing else to do on this screen, so poll.
  const agents = useQuery({ queryKey: ["agents"], queryFn: api.agents, refetchInterval: 4000 });

  const found = (agents.data ?? []).length > 0;
  const heading = HEADING[target];
  const cmd = installCommand(target, {
    panelUrl,
    token: token.data?.token ?? "…",
    heading: heading ? t(heading) : undefined,
    dockerImage: release.data?.docker_image,
  });

  const copy = async (what: "token" | "cmd", text: string) => {
    if (await copyText(text)) setCopied(what);
    else toast({ tone: "error", title: "onboarding.agent.copyFailed" });
  };

  return (
    <div className="flex flex-col gap-4">
      <div>
        <span className="label mb-2 block">{t("onboarding.agent.where")}</span>
        <div className="segmented">
          {INSTALL_TARGETS.map((p) => (
            <button
              key={p.k}
              type="button"
              aria-selected={p.k === target}
              onClick={() => {
                setTarget(p.k);
                setCopied("");
              }}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      <div className="core px-4 py-3.5">
        <span className="label mb-2 block">{t("agents.token.title")}</span>
        <div className="flex items-center gap-2.5">
          <code className="mono flex-1 break-all text-[12.5px] text-fg">
            {token.isError ? t("onboarding.agent.tokenFailed") : (token.data?.token ?? "…")}
          </code>
          <button
            type="button"
            className="btn btn-xs btn-secondary"
            disabled={!token.data}
            onClick={() => copy("token", token.data!.token)}
          >
            {copied === "token" ? t("agents.token.copied") : t("agents.token.copy")}
          </button>
        </div>
        <p className="mt-2 text-[11.5px] text-fg-3">
          {t("onboarding.agent.tokenHint", { hours: token.data?.expires_in_hours ?? 24 })}
        </p>
      </div>

      {/* A native build exists for this platform — offer it, and still show the
          command, because the installer is what enrols it. */}
      {hasDownload(target, release.data) && (
        <div>
          <span className="label mb-2 block">{t("onboarding.agent.download")}</span>
          <a
            className="btn btn-sm btn-primary"
            href={api.agentDownloadUrl(target as Exclude<InstallTarget, "docker">)}
          >
            <DownloadIcon size={13} />
            {t(`agents.dl.${target}` as MessageKey)}
          </a>
        </div>
      )}

      <div>
        <span className="mb-2 flex items-center gap-2.5">
          <span className="label">{t("onboarding.agent.paste")}</span>
          <button
            type="button"
            className="btn btn-xs btn-secondary ml-auto"
            disabled={!token.data}
            onClick={() => copy("cmd", cmd)}
          >
            {copied === "cmd" ? t("agents.token.copied") : t("onboarding.agent.copyCmd")}
          </button>
        </span>
        <pre className="mono core max-h-[150px] overflow-auto whitespace-pre-wrap break-words px-3.5 py-3 text-[11px] leading-[1.5] text-fg-2">
          {cmd}
        </pre>
      </div>

      <div className="flex items-center gap-2.5 border-t border-edge pt-3.5">
        <span
          className="h-2 w-2 rounded-full"
          style={{
            background: found ? "rgb(var(--fg))" : "rgb(var(--fg-3))",
            animation: found ? "none" : "cb-pulse 1.4s ease-in-out infinite",
          }}
        />
        <span className="text-[12.5px] text-fg-2">
          {found
            ? t("onboarding.agent.found", {
                name: agents.data![0].name,
                n: agents.data![0].last_hosts,
              })
            : t("onboarding.agent.waiting")}
        </span>
      </div>
    </div>
  );
}

/* ── 2 · review ───────────────────────────────────────────────────────────
 * One device at a time, on purpose. Bulk-approving the network on first run
 * teaches the alerting that everything is already fine. */
function ReviewStep({ onEmpty }: { onEmpty: () => void }) {
  const qc = useQueryClient();
  const t = useT();
  const toast = useToast();
  // Devices the user said "not sure" to: left pending so Review keeps them,
  // just taken off this screen.
  const [deferred, setDeferred] = useState<number[]>([]);

  const devices = useQuery({ queryKey: ["devices"], queryFn: () => api.devices() });
  const pending = (devices.data ?? []).filter(
    (d) => d.approval_status === "pending" && !deferred.includes(d.id),
  );

  const approve = useMutation({
    mutationFn: (id: number) => api.approveDevice(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["devices"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
    },
    onError: () => toast({ tone: "error", title: "onboarding.review.failed" }),
  });

  if (devices.isLoading) return <p className="text-[12.5px] text-fg-3">{t("common.loading")}</p>;

  if (pending.length === 0)
    return (
      <div className="flex items-center justify-between gap-4">
        <p className="text-[12.5px] text-fg-3">{t("onboarding.review.none")}</p>
        <button type="button" className="btn btn-xs btn-secondary" onClick={onEmpty}>
          {t("onboarding.continue")}
        </button>
      </div>
    );

  return (
    <div className="flex flex-col gap-3.5">
      {pending.slice(0, 6).map((d, n) => (
        <div key={d.id}>
          {n > 0 && <div className="mb-3.5 border-t border-edge" />}
          <div className="flex items-center gap-3.5">
            <span className="grid h-10 w-10 flex-shrink-0 place-items-center rounded-[10px] bg-fg/[0.06] text-fg-3">
              <DeviceTypeIcon type={d.device_type} size={20} />
            </span>
            <div className="min-w-0 flex-1">
              <span className="font-display text-[13.5px] text-fg">{d.display_name}</span>
              <div className="mono mt-[3px] truncate text-[10.5px] text-fg-3">{meta(d)}</div>
            </div>
            <div className="flex flex-shrink-0 gap-2">
              <button
                type="button"
                className="btn btn-xs btn-primary"
                disabled={approve.isPending}
                onClick={() => approve.mutate(d.id)}
              >
                {t("onboarding.review.mine")}
              </button>
              <button
                type="button"
                className="btn btn-xs btn-secondary"
                onClick={() => setDeferred((v) => [...v, d.id])}
              >
                {t("onboarding.review.unsure")}
              </button>
            </div>
          </div>
        </div>
      ))}
      {pending.length > 6 && (
        <p className="text-center text-[11px] text-fg-3">
          {t("onboarding.review.andMore", { n: pending.length - 6 })}
        </p>
      )}
    </div>
  );
}

/** "192.168.1.77 · TP-Link · IoT" — whatever of that we actually know */
function meta(d: Device): string {
  const ip = d.ips.find((a) => a.is_primary)?.address ?? d.ips[0]?.address;
  return [ip, d.short_vendor, deviceTypeLabel(d.device_type)].filter(Boolean).join(" · ");
}

/* ── 3 · people ───────────────────────────────────────────────────────── */
function PeopleStep() {
  const qc = useQueryClient();
  const t = useT();
  const toast = useToast();
  const [name, setName] = useState("");
  const [skipped, setSkipped] = useState<number[]>([]);

  const users = useQuery({ queryKey: ["users"], queryFn: api.users });
  const devices = useQuery({ queryKey: ["devices"], queryFn: () => api.devices() });

  const add = useMutation({
    mutationFn: () => api.createUser({ name: name.trim() }),
    onSuccess: () => {
      setName("");
      qc.invalidateQueries({ queryKey: ["users"] });
    },
    onError: () => toast({ tone: "error", title: "onboarding.people.failed" }),
  });

  const link = useMutation({
    mutationFn: (v: { deviceId: number; userId: number }) =>
      api.updateDevice(v.deviceId, { user_id: v.userId, counts_for_presence: true }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["devices"] });
      qc.invalidateQueries({ queryKey: ["users"] });
    },
    onError: () => toast({ tone: "error", title: "onboarding.people.linkFailed" }),
  });

  // "Cherubyte's guesses" — a device carrying somebody's name usually is theirs.
  const guesses = useMemo(() => {
    const people = users.data ?? [];
    if (!people.length) return [];
    return (devices.data ?? [])
      .filter((d) => !d.user && !skipped.includes(d.id))
      .map((d) => {
        const hay = d.display_name.toLowerCase();
        const who = people.find((p) => hay.includes(p.name.toLowerCase().split(/\s+/)[0]));
        return who ? { device: d, person: who } : null;
      })
      .filter((g): g is { device: Device; person: User } => g !== null)
      .slice(0, 4);
  }, [users.data, devices.data, skipped]);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-end gap-2.5">
        <label className="block flex-1">
          <span className="label mb-2 block">{t("onboarding.people.who")}</span>
          <input
            className="input"
            value={name}
            placeholder={t("onboarding.people.placeholder")}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && name.trim()) add.mutate();
            }}
          />
        </label>
        <Button
          variant="secondary"
          size="sm"
          disabled={!name.trim()}
          loading={add.isPending}
          onClick={() => add.mutate()}
        >
          {t("common.add")}
        </Button>
      </div>

      {(users.data ?? []).length > 0 && (
        <div className="flex flex-wrap gap-2.5">
          {users.data!.map((p) => (
            <span
              key={p.id}
              className="inline-flex items-center gap-2 rounded-full bg-fg/[0.06] py-1.5 pl-3 pr-3"
            >
              <span className="text-[12.5px] text-fg">{p.name}</span>
              <span className="mono text-[10.5px] text-fg-3">
                {t(
                  p.device_count === 1
                    ? "onboarding.people.deviceOne"
                    : "onboarding.people.devices",
                  { n: p.device_count },
                )}
              </span>
            </span>
          ))}
        </div>
      )}

      {guesses.length > 0 && (
        <div className="flex flex-col gap-3 border-t border-edge pt-4.5">
          <span className="label">{t("onboarding.people.guesses")}</span>
          {guesses.map(({ device, person }) => (
            <div key={device.id} className="flex items-center gap-3">
              <span className="grid h-[30px] w-[30px] flex-shrink-0 place-items-center rounded-[10px] bg-fg/[0.06] text-fg-3">
                <DeviceTypeIcon type={device.device_type} size={15} />
              </span>
              <span className="min-w-0 truncate text-[13px] text-fg">{device.display_name}</span>
              <ArrowRight size={12} className="flex-shrink-0 text-fg-3" />
              <span className="text-[13px] text-fg-2">{person.name}</span>
              <span className="ml-auto flex flex-shrink-0 items-center gap-2">
                <button
                  type="button"
                  className="btn btn-xs btn-secondary"
                  disabled={link.isPending}
                  onClick={() => link.mutate({ deviceId: device.id, userId: person.id })}
                >
                  <Check size={11} />
                  {t("onboarding.people.keep")}
                </button>
                <button
                  type="button"
                  className="btn btn-xs btn-ghost"
                  onClick={() => setSkipped((v) => [...v, device.id])}
                >
                  {t("onboarding.people.change")}
                </button>
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── 4 · names — kept from the modal wizard; it is what makes step 2 legible */
function NamesStep() {
  const t = useT();
  return (
    <div className="flex items-center justify-between gap-6">
      <p className="max-w-[46ch] text-[12.5px] leading-relaxed text-fg-2">
        {t("onboarding.names.detail")}
      </p>
      <Link to="/settings" className="btn btn-sm btn-primary flex-shrink-0">
        {t("onboarding.names.open")}
        <ArrowRight size={12} />
      </Link>
    </div>
  );
}
