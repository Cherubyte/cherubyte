import { useEffect, useState } from "react";

/**
 * Light / dark theme. `:root` is dark; the `.light` class opts into the
 * recolour. The choice is persisted per browser and shared across every
 * consumer (module-level store), so the toggle in Config ▸ Interface and any
 * other reader stay in sync. Controlled from Config ▸ Interface.
 */
function read(): boolean {
  try {
    return localStorage.getItem("netscan-theme") === "light";
  } catch {
    return false;
  }
}

let light = read();
let animate = false;
const subs = new Set<(v: boolean) => void>();

function apply() {
  const r = document.documentElement;
  r.classList.toggle("light", light);
  try {
    localStorage.setItem("netscan-theme", light ? "light" : "dark");
  } catch {
    /* private mode */
  }
  if (animate) {
    r.classList.add("theme-anim");
    setTimeout(() => r.classList.remove("theme-anim"), 180);
  }
}

function setLight(v: boolean) {
  if (v === light) return;
  light = v;
  animate = true;
  apply();
  subs.forEach((fn) => fn(light));
}

// apply the persisted choice on first import, without the cross-fade
apply();

export function useTheme() {
  const [value, setValue] = useState(light);
  useEffect(() => {
    const fn = (v: boolean) => setValue(v);
    subs.add(fn);
    return () => {
      subs.delete(fn);
    };
  }, []);
  return { light: value, setLight, toggle: () => setLight(!light) };
}
