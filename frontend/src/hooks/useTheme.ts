import { useEffect, useState } from "react";

/**
 * Light / dark theme. `:root` is the light chart sheet; the `.dark` class opts
 * into the ECDIS-night palette. The choice is persisted per browser and shared
 * across every consumer (module-level store), so the toggle in Config ▸
 * Interface and any other reader stay in sync. Default is light.
 *
 * The public API keeps a `light` flag (and `setLight` / `toggle`) so callers
 * read as "is the light sheet showing?".
 */
function readLight(): boolean {
  try {
    // default (unset) is the light chart sheet
    return localStorage.getItem("cherubyte-theme") !== "dark";
  } catch {
    return true;
  }
}

let light = readLight();
let animate = false;
const subs = new Set<(v: boolean) => void>();

function apply() {
  const r = document.documentElement;
  r.classList.toggle("dark", !light);
  try {
    localStorage.setItem("cherubyte-theme", light ? "light" : "dark");
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
