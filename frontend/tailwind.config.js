/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  // :root is dark; the `.light` class opts into the recolour.
  darkMode: ["selector", ":root:not(.light)"],
  theme: {
    extend: {
      colors: {
        // ── INSTRUMENT tokens ───────────────────────────────────────
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
        sans: ["Hanken Grotesk", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "sans-serif"],
        display: ["Clash Display", "Hanken Grotesk", "sans-serif"],
        mono: ["Spline Sans Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      borderColor: {
        DEFAULT: "rgb(var(--edge) / <alpha-value>)",
      },
      borderRadius: {
        none: "0", sm: "5px", DEFAULT: "7px", md: "8px", lg: "10px", xl: "12px", "2xl": "16px", full: "9999px",
      },
      boxShadow: {
        none: "none",
        e1: "var(--e1)",
        e2: "var(--e2)",
        e3: "var(--e3)",
      },
      fontSize: {
        "2xs": ["10px", "1.3"],
        xs: ["11px", "1.4"],
        sm: ["12px", "1.45"],
        base: ["13.5px", "1.5"],
        head: ["19px", "1.15"],
        title: ["30px", "1.05"],
        readout: ["clamp(40px, 7vw, 88px)", "0.9"],
        mega: ["clamp(46px, 8vw, 100px)", "0.88"],
      },
      transitionTimingFunction: {
        ease: "cubic-bezier(.32,.72,0,1)",
        "ease-out": "cubic-bezier(.16,1,.3,1)",
      },
      keyframes: {
        "leader-draw": { from: { transform: "scaleX(0)" }, to: { transform: "scaleX(1)" } },
        "underline-slide": { from: { transform: "scaleX(0)" }, to: { transform: "scaleX(1)" } },
      },
      animation: {
        "leader-draw": "leader-draw .18s cubic-bezier(.16,1,.3,1)",
        "underline-slide": "underline-slide .2s cubic-bezier(.16,1,.3,1)",
      },
    },
  },
  plugins: [],
};
