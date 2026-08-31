import { type ReactNode, useEffect } from "react";
import { createPortal } from "react-dom";
import { Close } from "./Glyph";
import { useIsMobile } from "../hooks/useMediaQuery";
import { AnimatePresence, motion, useReducedMotion, sheetSpring, snappy } from "../lib/motion";

/** Responsive dialog — centred on desktop, bottom sheet on mobile. */
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
  const reduced = useReducedMotion();

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

  const panelMotion = reduced
    ? { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 }, transition: { duration: 0.14 } }
    : isMobile
      ? { initial: { y: "100%" }, animate: { y: 0 }, exit: { y: "100%" }, transition: sheetSpring }
      : { initial: { opacity: 0, scale: 0.96 }, animate: { opacity: 1, scale: 1 }, exit: { opacity: 0, scale: 0.98 }, transition: snappy };

  return createPortal(
    <AnimatePresence>
      {open && (
        <div
          className={
            "fixed inset-0 z-[95] flex " +
            (isMobile ? "flex-col justify-end" : "items-center justify-center p-4")
          }
        >
          <motion.div
            className="absolute inset-0 bg-black/45"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.16 }}
            onClick={onClose}
          />
          <motion.div
            {...panelMotion}
            className={
              "relative flex max-h-[85vh] flex-col overflow-hidden bg-surface shadow-e3 " +
              (isMobile ? "w-full rounded-t-[20px] pb-[env(safe-area-inset-bottom)]" : "rounded-2xl")
            }
            style={{ width: isMobile ? "100%" : width }}
          >
            <div className="flex shrink-0 items-center justify-between px-4 pb-2.5 pt-3.5">
              <span className="font-display text-[13.5px] text-fg">{title}</span>
              <button onClick={onClose} className="text-fg-3 transition-colors hover:text-fg">
                <Close size={15} />
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
