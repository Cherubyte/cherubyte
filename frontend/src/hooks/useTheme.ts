import { useEffect, useState } from "react";

/**
 * Light / dark theme, following the operating system by default.
 *
 * `:root` is the light chart sheet; the `.dark` class opts into the
 * ECDIS-night palette. Three states, not two:
 *
 *   system  — follow `prefers-color-scheme`, and keep following it when the OS
 *             flips (many desktops do that on a schedule)
 *   light   — pinned, whatever the OS says
 *   dark    — pinned
 *
 * The choice is persisted per browser and shared across every consumer through
 * a module-level store, so the toggle in the header and the control in
 * Config ▸ Interface stay in sync.
 *
 * The `light` / `setLight` / `toggle` half of the API is the *resolved* theme,
 * so callers that only ask "is the light sheet showing?" keep working.
 */

export type ThemePref = "system" | "light" | "dark";

const KEY = "netscan-theme-pref";

/**
 * The old key, deliberately not migrated.
 *
 * The previous implementation wrote `netscan-theme` on *every* page load,
 * before anyone had touched a control — so a stored value there is not evidence
 * that anybody chose anything. Honouring it would pin every existing visitor to
 * a theme they never picked, which is exactly the bug this change exists to fix.
 * Someone who did choose deliberately gets moved to `system` and re-picks with
 * one click; the alternative silently ignores the OS for everybody.
 */
const LEGACY_KEY = "netscan-theme";

const DARK_QUERY = "(prefers-color-scheme: dark)";

function media(): MediaQueryList | null {
  try {
    return window.matchMedia(DARK_QUERY);
  } catch {
    // no matchMedia (very old browser, or a non-DOM test environment)
    return null;
  }
}

function readPref(): ThemePref {
  try {
    const stored = localStorage.getItem(KEY);
    if (stored === "light" || stored === "dark" || stored === "system") return stored;
  } catch {
    /* private mode */
  }
  return "system";
}

function systemIsDark(): boolean {
  return media()?.matches ?? false;
}

/** Whether the light sheet should show, for a given preference. */
export function resolve(p: ThemePref): boolean {
  return p === "system" ? !systemIsDark() : p === "light";
}

let pref = readPref();
let light = resolve(pref);
let animate = false;
const subs = new Set<() => void>();

function apply() {
  const root = document.documentElement;
  root.classList.toggle("dark", !light);
  if (animate) {
    root.classList.add("theme-anim");
    setTimeout(() => root.classList.remove("theme-anim"), 180);
  }
}

function persist() {
  try {
    localStorage.setItem(KEY, pref);
    // the old key is meaningless now, and leaving it invites a future reader to
    // trust it
    localStorage.removeItem(LEGACY_KEY);
  } catch {
    /* private mode */
  }
}

function update(next: ThemePref, { store = true } = {}) {
  const wasLight = light;
  pref = next;
  light = resolve(pref);
  if (store) persist();
  if (light !== wasLight) {
    animate = true;
    apply();
  }
  subs.forEach((fn) => fn());
}

export function setPref(next: ThemePref) {
  if (next !== pref) update(next);
}

/** Pin the theme. Used by the two-state controls. */
export function setLight(v: boolean) {
  setPref(v ? "light" : "dark");
}

/** Flip to the opposite of what is currently showing, and pin it. */
export function toggle() {
  setLight(!light);
}

// Apply the resolved theme on first import, without the cross-fade, and without
// writing anything: a visitor who has never chosen must stay on `system`.
apply();

// Follow the OS while the preference is `system`.
media()?.addEventListener?.("change", () => {
  if (pref === "system") update("system", { store: false });
});

export function useTheme() {
  const [, force] = useState(0);
  useEffect(() => {
    const fn = () => force((n) => n + 1);
    subs.add(fn);
    return () => {
      subs.delete(fn);
    };
  }, []);
  return { light, pref, setLight, setPref, toggle };
}
