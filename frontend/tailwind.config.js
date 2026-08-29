/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  // :root is dark; the `.light` class opts into the recolour.
  darkMode: ["selector", ":root:not(.light)"],
  theme: {
    extend: {
      colors: {
        // ── STATION tokens ──────────────────────────────────────────
        bg: "rgb(var(--bg) / <alpha-value>)",
        surface: "rgb(var(--surface) / <alpha-value>)",
        "surface-2": "rgb(var(--surface-2) / <alpha-value>)",
        "surface-3": "rgb(var(--surface-3) / <alpha-value>)",
        fg: "rgb(var(--fg) / <alpha-value>)",
        "fg-2": "rgb(var(--fg-2) / <alpha-value>)",
        "fg-3": "rgb(var(--fg-3) / <alpha-value>)",
        edge: "rgb(var(--edge) / <alpha-value>)",
        "edge-2": "rgb(var(--edge-2) / <alpha-value>)",
        signal: "rgb(var(--signal) / <alpha-value>)",
        "signal-bg": "rgb(var(--signal-fill-bg) / <alpha-value>)",
        "signal-fg": "rgb(var(--signal-fill-fg) / <alpha-value>)",
        alert: "rgb(var(--alert) / <alpha-value>)",
        "alert-fg": "rgb(var(--alert-fg) / <alpha-value>)",
      },
      fontFamily: {
        sans: ["Geist", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "sans-serif"],
        display: ["Space Grotesk", "Geist", "sans-serif"],
        mono: ["Geist Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      borderColor: {
        DEFAULT: "rgb(var(--edge) / <alpha-value>)",
      },
      borderRadius: {
        none: "0", sm: "3px", DEFAULT: "3px", md: "3px", lg: "4px", xl: "6px", "2xl": "8px", full: "9999px",
      },
      boxShadow: {
        none: "none", e1: "none", e2: "none", e3: "none",
      },
      fontSize: {
        "2xs": ["10px", "1.3"],
        xs: ["11px", "1.4"],
        sm: ["12px", "1.45"],
        base: ["13.5px", "1.5"],
        head: ["19px", "1.15"],
        title: ["30px", "1.05"],
        readout: ["clamp(38px, 7vw, 84px)", "0.92"],
        mega: ["clamp(44px, 8vw, 96px)", "0.9"],
      },
      transitionTimingFunction: {
        ease: "cubic-bezier(.2,0,0,1)",
      },
      keyframes: {
        "leader-draw": { from: { transform: "scaleX(0)" }, to: { transform: "scaleX(1)" } },
        "underline-slide": { from: { transform: "scaleX(0)" }, to: { transform: "scaleX(1)" } },
      },
      animation: {
        "leader-draw": "leader-draw .12s cubic-bezier(.2,0,0,1)",
        "underline-slide": "underline-slide .18s cubic-bezier(.2,0,0,1)",
      },
    },
  },
  plugins: [],
};
