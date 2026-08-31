/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  // :root is the light surface; the `.dark` class opts into the night palette.
  darkMode: ["selector", ":root.dark"],
  theme: {
    extend: {
      colors: {
        // ── STUDIO tokens ───────────────────────────────────────────
        paper: "rgb(var(--paper) / <alpha-value>)",
        bg: "rgb(var(--bg) / <alpha-value>)",
        surface: "rgb(var(--surface) / <alpha-value>)",
        "surface-2": "rgb(var(--surface-2) / <alpha-value>)",
        "surface-3": "rgb(var(--surface-3) / <alpha-value>)",
        canvas: "rgb(var(--surface-2) / <alpha-value>)",
        fg: "rgb(var(--fg) / <alpha-value>)",
        "fg-2": "rgb(var(--fg-2) / <alpha-value>)",
        "fg-3": "rgb(var(--fg-3) / <alpha-value>)",
        edge: "rgb(var(--edge) / <alpha-value>)",
        "edge-2": "rgb(var(--edge-2) / <alpha-value>)",
        water: "rgb(var(--water) / <alpha-value>)",
        signal: "rgb(var(--signal) / <alpha-value>)",
        "signal-bg": "rgb(var(--signal-fill-bg) / <alpha-value>)",
        "signal-fg": "rgb(var(--signal-fill-fg) / <alpha-value>)",
        alert: "rgb(var(--alert) / <alpha-value>)",
        "alert-fg": "rgb(var(--alert-fg) / <alpha-value>)",
        grid: "rgb(var(--grid) / <alpha-value>)",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "sans-serif"],
        display: ["Inter", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SF Mono", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      borderColor: {
        DEFAULT: "rgb(var(--edge) / <alpha-value>)",
      },
      borderRadius: {
        none: "0", sm: "6px", DEFAULT: "8px", md: "10px", lg: "12px", xl: "16px", "2xl": "20px", full: "9999px",
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
        base: ["14px", "1.5"],
        head: ["20px", "1.15"],
        title: ["30px", "1.05"],
        readout: ["clamp(38px, 6vw, 68px)", "0.92"],
        mega: ["clamp(44px, 7vw, 88px)", "0.9"],
      },
      transitionTimingFunction: {
        ease: "cubic-bezier(.32,.72,0,1)",
        "ease-out": "cubic-bezier(.16,1,.3,1)",
      },
      keyframes: {
        "underline-slide": { from: { transform: "scaleX(0)" }, to: { transform: "scaleX(1)" } },
      },
      animation: {
        "underline-slide": "underline-slide .2s cubic-bezier(.16,1,.3,1)",
      },
    },
  },
  plugins: [],
};
