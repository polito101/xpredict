/**
 * Aurora — the fixed obsidian backdrop behind the whole app.
 *
 * Renders soft, brand-tinted radial glows that echo the X crossing, on top of
 * the deep obsidian canvas. Purely decorative (`aria-hidden`), fixed and
 * non-interactive (`pointer-events-none`), so it sits behind all content without
 * affecting layout or scroll. Server Component.
 */
import { cn } from "@/lib/utils";

export function Aurora({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "pointer-events-none fixed inset-0 -z-10 aurora",
        className,
      )}
    >
      {/* A faint technical line grid — blueprint / infrastructure texture that
          adds depth without noise. Masked to the top so it frames the hero and
          melts away down the page. */}
      <div
        className="absolute inset-0 opacity-[0.55]"
        style={{
          backgroundImage:
            "linear-gradient(to right, color-mix(in oklab, var(--foreground) 7%, transparent) 1px, transparent 1px), linear-gradient(to bottom, color-mix(in oklab, var(--foreground) 7%, transparent) 1px, transparent 1px)",
          backgroundSize: "64px 64px",
          maskImage:
            "radial-gradient(78% 68% at 50% 0%, black, transparent 82%)",
          WebkitMaskImage:
            "radial-gradient(78% 68% at 50% 0%, black, transparent 82%)",
        }}
      />
    </div>
  );
}
