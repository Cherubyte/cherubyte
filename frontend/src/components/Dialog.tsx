import { type ReactNode, useEffect } from "react";
import { createPortal } from "react-dom";
import { Close } from "./Glyph";
import { useIsMobile } from "../hooks/useMediaQuery";

/** Responsive dialog — centred on desktop, bottom sheet on mobile. Sharp, bordered. */
export function Dialog({
  open,
  onClose,
  title,
  children,
  width = 460,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  width?: number;
}) {
  const isMobile = useIsMobile();

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
    <div
      className={
        "fixed inset-0 z-[95] flex " +
        (isMobile ? "flex-col justify-end" : "items-center justify-center p-4")
      }
    >
      <div
        className="absolute inset-0 bg-black/55"
        style={{ animation: "scrim-in .12s linear" }}
        onClick={onClose}
      />
      <div
        className={
          "relative flex max-h-[85vh] flex-col overflow-hidden rounded-xl border border-edge-2 bg-surface shadow-e3 " +
          (isMobile ? "pb-[env(safe-area-inset-bottom)]" : "")
        }
        style={{
          width: isMobile ? "100%" : width,
          animation: isMobile
            ? "sheet-up .2s cubic-bezier(.2,0,0,1)"
            : "overlay-in .16s cubic-bezier(.2,0,0,1)",
        }}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-edge px-4 py-3">
          <span className="key text-fg">{title}</span>
          <button onClick={onClose} className="text-fg-3 transition-colors hover:text-fg">
            <Close size={14} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
