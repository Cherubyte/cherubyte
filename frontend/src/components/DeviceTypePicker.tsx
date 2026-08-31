import { useState } from "react";
import clsx from "clsx";
import type { DeviceType } from "../api/types";
import { DEVICE_TYPE_GROUPS, deviceTypeLabel } from "../lib/format";
import { useT } from "../i18n";
import { CaretDown, DeviceTypeIcon } from "./Glyph";
import { Dialog } from "./Dialog";

/** The device-type field: a trigger that opens a grid of every type, grouped. */
export function DeviceTypePicker({
  value,
  onChange,
}: {
  value: DeviceType;
  onChange: (t: DeviceType) => void;
}) {
  const t = useT();
  const [open, setOpen] = useState(false);

  const pick = (ty: DeviceType) => {
    onChange(ty);
    setOpen(false);
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="input flex items-center gap-2 text-left"
      >
        <DeviceTypeIcon type={value} size={15} className="shrink-0 text-fg-2" />
        <span className="flex-1 truncate">{deviceTypeLabel(value)}</span>
        <CaretDown size={12} className="shrink-0 text-fg-3" />
      </button>

      <Dialog open={open} onClose={() => setOpen(false)} title={t("device.field.type")} width={520}>
        <div className="space-y-4 p-4">
          {DEVICE_TYPE_GROUPS.map((group) => (
            <div key={group.key}>
              <div className="key mb-2 text-fg-3">{t(group.key)}</div>
              <div className="grid grid-cols-3 gap-1.5 sm:grid-cols-4">
                {group.types.map((ty) => {
                  const active = ty === value;
                  return (
                    <button
                      key={ty}
                      type="button"
                      onClick={() => pick(ty)}
                      aria-pressed={active}
                      className={clsx(
                        "flex flex-col items-center gap-1.5 rounded-xl p-2.5 text-center transition-colors",
                        active
                          ? "bg-fg text-surface"
                          : "bg-fg/[0.05] text-fg-2 hover:bg-fg/10 hover:text-fg",
                      )}
                    >
                      <DeviceTypeIcon type={ty} size={20} />
                      <span className="text-[10.5px] leading-tight">{deviceTypeLabel(ty)}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </Dialog>
    </>
  );
}
