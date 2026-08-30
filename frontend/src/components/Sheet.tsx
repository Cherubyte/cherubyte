import { type ReactNode, useEffect } from "react";
import { createPortal } from "react-dom";
import { Close } from "./Glyph";

/** Bottom sheet (mobile) — filters, action menus, the "Mais" menu. */
export function Sheet({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-[90] flex flex-col justify-end">
      <div
        className="absolute inset-0 bg-black/50"
        style={{ animation: "scrim-in .12s linear" }}
        onClick={onClose}
      />
      <div
        className="relative max-h-[85vh] overflow-y-auto rounded-t-2xl border-t border-edge-2 bg-surface pb-[env(safe-area-inset-bottom)] shadow-e3"
        style={{ animation: "sheet-up .2s cubic-bezier(.2,0,0,1)" }}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-edge bg-surface px-4 py-2.5">
          <span className="key text-fg">{title}</span>
          <button onClick={onClose} className="text-fg-3 hover:text-fg">
            <Close size={14} />
          </button>
        </div>
        <div className="p-4">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
