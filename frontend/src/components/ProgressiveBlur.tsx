/** A backdrop blur that ramps from full strength at the top edge down to
 * nothing, without the hard band a flat `backdrop-blur` leaves.
 *
 * `backdrop-filter` has no gradient of its own, so this stacks a few full-bleed
 * layers of increasing blur. The trick that keeps the fade seamless: every
 * layer's mask ramps from opaque near the top *all the way to transparent at
 * the very bottom of the box* — no layer ever has a sharp opaque→clear step,
 * so no layer can leave a visible line. The layers differ only in how early
 * that ramp starts, so the heavier blur is gone sooner and the lightest one
 * carries the tail out to nothing.
 *
 * Render it absolutely positioned behind header content, sized past the header
 * (e.g. `-bottom-16`) so the tail — and the hard clip `backdrop-filter` makes
 * at the element edge — lands well below anything the eye is on. */
const STEPS = 4;

export function ProgressiveBlur({
  strength = 28,
  className,
}: {
  /** blur radius (px) at the strongest — top — edge */
  strength?: number;
  className?: string;
}) {
  return (
    <div className={className} aria-hidden="true">
      {Array.from({ length: STEPS }, (_, i) => {
        const t = i / (STEPS - 1); // 0 = lightest/longest, 1 = heaviest/shortest
        // ease-in so only the top layer carries the full radius
        const blur = strength * (0.12 + 0.88 * t ** 1.6);
        // where this layer starts fading — heavier blur starts sooner. Every
        // layer is fully clear by 100%, so the ramps are 60-100% of the box
        // tall and nothing reads as an edge.
        const start = t * 42;
        const mask = `linear-gradient(to bottom, black ${start.toFixed(0)}%, transparent 100%)`;
        return (
          <div
            key={i}
            className="absolute inset-0"
            style={{
              backdropFilter: `blur(${blur.toFixed(2)}px)`,
              WebkitBackdropFilter: `blur(${blur.toFixed(2)}px)`,
              maskImage: mask,
              WebkitMaskImage: mask,
            }}
          />
        );
      })}
    </div>
  );
}
