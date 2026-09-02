/** A backdrop blur that ramps smoothly from full strength at the top edge
 * down to nothing, instead of the hard band a flat `backdrop-blur` produces.
 * `backdrop-filter` has no gradient of its own, so this stacks several
 * full-bleed layers, each blurred a little more and masked to its own
 * horizontal band with soft edges — the overlap reads as one continuous
 * fade. Render it absolutely positioned behind header content, sized a bit
 * taller than the header so the fade finishes in the content below it. */
const STEPS = 8;

export function ProgressiveBlur({
  strength = 24,
  className,
}: {
  /** blur radius (px) at the strongest — top — edge */
  strength?: number;
  className?: string;
}) {
  return (
    <div className={className} aria-hidden="true">
      {Array.from({ length: STEPS }, (_, i) => {
        const blur = strength * (1 - i / (STEPS - 1));
        const bandStart = (i / STEPS) * 100;
        const bandEnd = ((i + 1) / STEPS) * 100;
        const fade = 100 / STEPS;
        const mask = `linear-gradient(to bottom, transparent ${Math.max(0, bandStart - fade)}%, black ${bandStart}%, black ${bandEnd}%, transparent ${Math.min(100, bandEnd + fade)}%)`;
        return (
          <div
            key={i}
            className="absolute inset-0"
            style={{
              backdropFilter: `blur(${blur.toFixed(1)}px)`,
              WebkitBackdropFilter: `blur(${blur.toFixed(1)}px)`,
              maskImage: mask,
              WebkitMaskImage: mask,
            }}
          />
        );
      })}
    </div>
  );
}
