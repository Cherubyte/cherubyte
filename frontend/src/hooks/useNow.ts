import { useEffect, useState } from "react";

/**
 * One shared ticking clock for the whole app. Every relative timestamp
 * ("38s", "14m") subscribes to this so the sheet reads as *live* without
 * each component spinning its own interval.
 */
let subs = new Set<() => void>();
let timer: ReturnType<typeof setInterval> | null = null;

function ensureTimer() {
  if (timer) return;
  timer = setInterval(() => subs.forEach((fn) => fn()), 1000);
}

export function useNow(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const fn = () => setNow(Date.now());
    subs.add(fn);
    ensureTimer();
    return () => {
      subs.delete(fn);
      if (subs.size === 0 && timer) {
        clearInterval(timer);
        timer = null;
      }
    };
  }, []);
  return now;
}
