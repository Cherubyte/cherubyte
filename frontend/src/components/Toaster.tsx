import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import clsx from "clsx";
import { hm } from "../lib/format";
import { en } from "../i18n/en";
import { translate } from "../i18n/translate";
import { AnimatePresence, motion, useReducedMotion } from "../lib/motion";

type Tone = "success" | "error" | "info";
type Toast = { id: number; tone: Tone; title: string; desc?: string; at: Date };

const Ctx = createContext<(t: { tone: Tone; title: string; desc?: string }) => void>(() => {});

export function useToast() {
  return useContext(Ctx);
}

/** Toast confirmations are always shown in English, regardless of the UI locale.
 *  Call sites pass either an i18n key or plain text — translate when it's a key. */
function label(s: string): string {
  return s in en ? translate("en", s as keyof typeof en) : s;
}

let seq = 0;

export function ToasterProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const reduced = useReducedMotion();

  const push = useCallback((t: { tone: Tone; title: string; desc?: string }) => {
    const id = ++seq;
    setItems((s) => [...s, { ...t, id, at: new Date() }]);
    setTimeout(() => setItems((s) => s.filter((x) => x.id !== id)), 4600);
  }, []);

  const dismiss = (id: number) => setItems((s) => s.filter((x) => x.id !== id));

  return (
    <Ctx.Provider value={push}>
      {children}
      {createPortal(
        <div
          className={clsx(
            "pointer-events-none fixed inset-x-0 z-[100] flex flex-col gap-2 p-3",
            // Mobile: clears the fixed bottom tab bar (54px + its own safe-area
            // padding) instead of stacking underneath it.
            "bottom-[calc(70px+env(safe-area-inset-bottom))]",
            // Desktop: bottom-right, clear of the sidebar's own footer
            // (Scan button, account, version) which lives bottom-left.
            "sm:inset-x-auto sm:right-0 sm:bottom-0 sm:p-4 sm:pb-[calc(1rem+env(safe-area-inset-bottom))]",
          )}
        >
          <AnimatePresence>
            {items.map((t) => (
              <motion.button
                key={t.id}
                initial={reduced ? { opacity: 0 } : { opacity: 0, y: 10, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={reduced ? { opacity: 0 } : { opacity: 0, x: 16 }}
                transition={{ type: "spring", bounce: 0, duration: 0.3 }}
                onClick={() => dismiss(t.id)}
                className="pointer-events-auto flex w-[min(360px,calc(100vw-1.5rem))] items-stretch gap-3 overflow-hidden rounded-2xl bg-surface py-2.5 pl-0 pr-3.5 text-left shadow-e3"
              >
                <span
                  className={
                    "block w-[3px] shrink-0 rounded-full " +
                    (t.tone === "error" ? "bg-alert" : "bg-fg")
                  }
                />
                <span className="min-w-0 flex-1 py-0.5 text-[12.5px] leading-snug">
                  <span className="mono text-[10.5px] text-fg-3">{hm(t.at)}</span>{" "}
                  <span className="font-medium text-fg">{label(t.title)}</span>
                  {t.desc && <span className="mt-0.5 block text-[11.5px] text-fg-3">{label(t.desc)}</span>}
                </span>
              </motion.button>
            ))}
          </AnimatePresence>
        </div>,
        document.body,
      )}
    </Ctx.Provider>
  );
}
