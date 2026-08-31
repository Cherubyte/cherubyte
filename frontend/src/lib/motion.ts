/**
 * Shared motion primitives. The panel uses interruptible springs (motion/react)
 * for anything a pointer touches — sheets, dialogs, toggles, route changes — per
 * the apple-design guidance. Everything here collapses to an opacity-only or
 * instant transition when the viewer asks for reduced motion.
 */
import { useReducedMotion } from "motion/react";

export { AnimatePresence, motion, useReducedMotion } from "motion/react";
export type { Transition, Variants } from "motion/react";

/** critically damped — the default for UI that just needs to arrive */
export const snappy = { type: "spring", bounce: 0, duration: 0.35 } as const;

/** a touch of overshoot — only for surfaces that "arrive", like a sheet */
export const sheetSpring = { type: "spring", bounce: 0.18, duration: 0.42 } as const;

/** a plain cross-fade — the reduced-motion substitute for any of the above */
export const fade = { duration: 0.16, ease: [0.16, 1, 0.3, 1] } as const;

/**
 * Route / view enter. Returns props for a `motion.div` that fades + rises,
 * or a plain fade under reduced motion.
 */
export function useViewTransition() {
  const reduced = useReducedMotion();
  return {
    initial: reduced ? { opacity: 0 } : { opacity: 0, y: 8 },
    animate: { opacity: 1, y: 0 },
    exit: reduced ? { opacity: 0 } : { opacity: 0, y: -6 },
    transition: reduced ? fade : snappy,
  } as const;
}
