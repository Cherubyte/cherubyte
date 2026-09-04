import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { deviceTypeLabel } from "../lib/format";
import { useT, type MessageKey } from "../i18n";
import { Dialog } from "./Dialog";
import { Button, Field } from "./ui";
import { TypeCode, useBrandLogos, useOsLogos } from "./TypeCode";
import { useToast } from "./Toaster";
import {
  Check,
  ArrowRight,
  HostsIcon,
  ReviewIcon,
  PeopleIcon,
  StatsIcon,
  LogIcon,
  ConfigIcon,
} from "./Glyph";

type Step = "name" | "devices" | "phone" | "fingerbank" | "tourAsk" | "tour";

/** device types a person plausibly carries — candidates for "is this your phone?" */
const PERSONAL_TYPES = new Set(["phone", "tablet", "wearable"]);

const TOUR: { titleKey: MessageKey; descKey: MessageKey; Icon: typeof HostsIcon }[] = [
  { titleKey: "nav.hosts", descKey: "onboarding.tour.hosts", Icon: HostsIcon },
  { titleKey: "nav.review", descKey: "onboarding.tour.review", Icon: ReviewIcon },
  { titleKey: "nav.people", descKey: "onboarding.tour.people", Icon: PeopleIcon },
  { titleKey: "nav.stats", descKey: "onboarding.tour.stats", Icon: StatsIcon },
  { titleKey: "nav.log", descKey: "onboarding.tour.log", Icon: LogIcon },
  { titleKey: "nav.config", descKey: "onboarding.tour.config", Icon: ConfigIcon },
];

/** First-run wizard: name the household, clear the review queue, claim a
 *  phone for presence, point at Fingerbank, then an optional tour. Shown once
 *  — the first time there is anything to onboard about — and never again
 *  once dismissed, skipped or finished (Settings.onboarding_dismissed). */
export function Onboarding() {
  const qc = useQueryClient();
  const t = useT();
  const toast = useToast();
  const logos = useBrandLogos();
  const osLogos = useOsLogos();

  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings, staleTime: 60000 });
  const eligible = !!settings.data && !settings.data.onboarding_dismissed;
  const devices = useQuery({
    queryKey: ["devices"],
    queryFn: () => api.devices(),
    enabled: eligible,
  });

  const [step, setStep] = useState<Step>("name");
  const [name, setName] = useState("");
  const [personId, setPersonId] = useState<number | null>(null);
  const [tourIndex, setTourIndex] = useState(0);

  const shouldShow = eligible && (devices.data?.length ?? 0) > 0;

  const dismiss = useMutation({
    mutationFn: () => api.updateSettings({ onboarding_dismissed: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings"] }),
  });

  const createPerson = useMutation({
    mutationFn: () => api.createUser({ name: name.trim() }),
    onSuccess: (u) => {
      qc.invalidateQueries({ queryKey: ["users"] });
      setPersonId(u.id);
      setStep("devices");
    },
    onError: () => toast({ tone: "error", title: "onboarding.name.failed" }),
  });

  const pending = (devices.data ?? []).filter((d) => d.approval_status === "pending");
  const acknowledgeAll = useMutation({
    mutationFn: () => Promise.all(pending.map((d) => api.approveDevice(d.id))),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["devices"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      setStep("phone");
    },
    onError: () => toast({ tone: "error", title: "onboarding.devices.failed" }),
  });

  const personalDevices = (devices.data ?? []).filter((d) => PERSONAL_TYPES.has(d.device_type));
  const claimPhone = useMutation({
    mutationFn: (deviceId: number) =>
      api.updateDevice(deviceId, { user_id: personId ?? undefined, counts_for_presence: true }),
    onError: () => toast({ tone: "error", title: "onboarding.phone.failed" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["devices"] });
      qc.invalidateQueries({ queryKey: ["users"] });
      setStep("fingerbank");
    },
  });

  if (!shouldShow) return null;

  const finish = () => dismiss.mutate();
  const skipTo = (s: Step) => setStep(s);

  return (
    <Dialog open onClose={finish} title={t("onboarding.title")} width={440}>
      {step === "name" && (
        <div className="p-4">
          <p className="font-display text-[15px] text-fg">{t("onboarding.name.title")}</p>
          <p className="mt-1 text-[12.5px] leading-relaxed text-fg-3">
            {t("onboarding.name.sub")}
          </p>
          <Field className="mt-4">
            <input
              autoFocus
              className="input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("onboarding.name.placeholder")}
              onKeyDown={(e) => {
                if (e.key === "Enter" && name.trim()) createPerson.mutate();
              }}
            />
          </Field>
          <div className="mt-4 flex items-center justify-between">
            <Button variant="ghost" size="sm" onClick={finish}>
              {t("onboarding.skipAll")}
            </Button>
            <Button
              variant="primary"
              size="sm"
              disabled={!name.trim()}
              loading={createPerson.isPending}
              onClick={() => createPerson.mutate()}
              icon={<ArrowRight size={12} />}
            >
              {t("onboarding.continue")}
            </Button>
          </div>
        </div>
      )}

      {step === "devices" && (
        <div className="p-4">
          <p className="font-display text-[15px] text-fg">
            {pending.length === 1
              ? t("onboarding.devices.titleOne")
              : t("onboarding.devices.title", { n: pending.length })}
          </p>
          <p className="mt-1 text-[12.5px] leading-relaxed text-fg-3">
            {t("onboarding.devices.sub")}
          </p>
          {pending.length > 0 && (
            <ul className="mt-3 max-h-[220px] space-y-1.5 overflow-y-auto">
              {pending.slice(0, 8).map((d) => (
                <li key={d.id} className="flex items-center gap-2.5 rounded-lg bg-surface-2 px-2.5 py-1.5">
                  <TypeCode device={d} logos={logos} osLogos={osLogos} size={22} />
                  <span className="min-w-0 flex-1 truncate text-[12px] text-fg">
                    {d.display_name}
                  </span>
                  <span className="mono shrink-0 text-[10px] text-fg-3">
                    {deviceTypeLabel(d.device_type)}
                  </span>
                </li>
              ))}
              {pending.length > 8 && (
                <li className="text-center text-[11px] text-fg-3">
                  {t("onboarding.devices.andMore", { n: pending.length - 8 })}
                </li>
              )}
            </ul>
          )}
          <div className="mt-4 flex items-center justify-between">
            <Button variant="ghost" size="sm" onClick={() => skipTo("phone")}>
              {t("onboarding.skip")}
            </Button>
            <Button
              variant="primary"
              size="sm"
              loading={acknowledgeAll.isPending}
              onClick={() =>
                pending.length > 0 ? acknowledgeAll.mutate() : skipTo("phone")
              }
              icon={<Check size={12} />}
            >
              {pending.length > 0 ? t("onboarding.devices.acknowledgeAll") : t("onboarding.continue")}
            </Button>
          </div>
        </div>
      )}

      {step === "phone" && (
        <div className="p-4">
          <p className="font-display text-[15px] text-fg">{t("onboarding.phone.title")}</p>
          <p className="mt-1 text-[12.5px] leading-relaxed text-fg-3">
            {t("onboarding.phone.sub")}
          </p>
          {personalDevices.length > 0 ? (
            <ul className="mt-3 max-h-[220px] space-y-1.5 overflow-y-auto">
              {personalDevices.slice(0, 8).map((d) => (
                <li key={d.id}>
                  <button
                    onClick={() => claimPhone.mutate(d.id)}
                    disabled={claimPhone.isPending}
                    className="flex w-full items-center gap-2.5 rounded-lg bg-surface-2 px-2.5 py-1.5 text-left transition-colors hover:bg-fg/[0.06] disabled:opacity-50"
                  >
                    <TypeCode device={d} logos={logos} osLogos={osLogos} size={22} />
                    <span className="min-w-0 flex-1 truncate text-[12px] text-fg">
                      {d.display_name}
                    </span>
                    <ArrowRight size={12} className="shrink-0 text-fg-3" />
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-[11.5px] text-fg-3">{t("onboarding.phone.none")}</p>
          )}
          <div className="mt-4 flex items-center justify-between">
            <Button variant="ghost" size="sm" onClick={() => skipTo("fingerbank")}>
              {t("onboarding.skip")}
            </Button>
          </div>
        </div>
      )}

      {step === "fingerbank" && (
        <div className="p-4">
          <p className="font-display text-[15px] text-fg">{t("onboarding.fingerbank.title")}</p>
          <p className="mt-1 text-[12.5px] leading-relaxed text-fg-3">
            {t("onboarding.fingerbank.sub")}
          </p>
          <div className="mt-4 flex items-center justify-between">
            <Button variant="ghost" size="sm" onClick={() => skipTo("tourAsk")}>
              {t("onboarding.skip")}
            </Button>
            <Link to="/settings" onClick={() => skipTo("tourAsk")}>
              <Button variant="primary" size="sm" icon={<ArrowRight size={12} />}>
                {t("onboarding.fingerbank.open")}
              </Button>
            </Link>
          </div>
        </div>
      )}

      {step === "tourAsk" && (
        <div className="p-4">
          <p className="font-display text-[15px] text-fg">{t("onboarding.tourAsk.title")}</p>
          <p className="mt-1 text-[12.5px] leading-relaxed text-fg-3">
            {t("onboarding.tourAsk.sub")}
          </p>
          <div className="mt-4 flex items-center justify-between">
            <Button variant="ghost" size="sm" onClick={finish}>
              {t("onboarding.tourAsk.skip")}
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => {
                setTourIndex(0);
                skipTo("tour");
              }}
              icon={<ArrowRight size={12} />}
            >
              {t("onboarding.tourAsk.yes")}
            </Button>
          </div>
        </div>
      )}

      {step === "tour" && (
        <div className="p-4">
          {(() => {
            const slide = TOUR[tourIndex];
            const last = tourIndex === TOUR.length - 1;
            return (
              <>
                <div className="flex items-center gap-3 rounded-xl bg-surface-2 p-4">
                  <slide.Icon size={22} className="shrink-0 text-fg-2" />
                  <div className="min-w-0">
                    <p className="font-display text-[13.5px] text-fg">{t(slide.titleKey)}</p>
                    <p className="mt-0.5 text-[12px] leading-relaxed text-fg-3">
                      {t(slide.descKey)}
                    </p>
                  </div>
                </div>
                <div className="mt-3 flex justify-center gap-1.5">
                  {TOUR.map((_, i) => (
                    <span
                      key={i}
                      className={
                        "h-1.5 w-1.5 rounded-full " + (i === tourIndex ? "bg-fg" : "bg-fg/20")
                      }
                    />
                  ))}
                </div>
                <div className="mt-4 flex items-center justify-between">
                  <Button variant="ghost" size="sm" onClick={finish}>
                    {t("onboarding.skip")}
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => (last ? finish() : setTourIndex((i) => i + 1))}
                    icon={last ? <Check size={12} /> : <ArrowRight size={12} />}
                  >
                    {last ? t("onboarding.tour.done") : t("onboarding.tour.next")}
                  </Button>
                </div>
              </>
            );
          })()}
        </div>
      )}
    </Dialog>
  );
}
