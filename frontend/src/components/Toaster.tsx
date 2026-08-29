import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { hm } from "../lib/format";

type Tone = "success" | "error" | "info";
type Toast = { id: number; tone: Tone; title: string; desc?: string; at: Date };

const Ctx = createContext<(t: { tone: Tone; title: string; desc?: string }) => void>(() => {});

export function useToast() {
  return useContext(Ctx);
}

let seq = 0;

export function ToasterProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);

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
        <div className="pointer-events-none fixed bottom-0 left-0 z-[100] flex flex-col gap-px p-3 pb-[calc(0.75rem+env(safe-area-inset-bottom))] sm:p-4">
          {items.map((t) => (
            <button
              key={t.id}
              onClick={() => dismiss(t.id)}
              className="pointer-events-auto flex w-[min(360px,calc(100vw-1.5rem))] items-stretch gap-2.5 border border-edge-2 bg-surface py-2 pl-0 pr-3 text-left"
              style={{ animation: "toast-in .16s cubic-bezier(.2,0,0,1)" }}
            >
              <span
                className={
                  "block w-[3px] shrink-0 " +
                  (t.tone === "success"
                    ? "bg-signal"
                    : t.tone === "error"
                      ? "bg-alert"
                      : "bg-fg-3")
                }
              />
              <span className="mono min-w-0 flex-1 py-0.5 text-[11px] leading-snug">
                <span className="text-fg-3">{hm(t.at)}</span>{" "}
                <span className="text-fg">{t.title}</span>
                {t.desc && <span className="block text-fg-3">{t.desc}</span>}
              </span>
            </button>
          ))}
        </div>,
        document.body,
      )}
    </Ctx.Provider>
  );
}
