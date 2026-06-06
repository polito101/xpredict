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
      {/* A faint dotted grid adds depth without noise. */}
      <div
        className="absolute inset-0 opacity-[0.4]"
        style={{
          backgroundImage:
            "radial-gradient(circle at 1px 1px, color-mix(in oklab, var(--foreground) 6%, transparent) 1px, transparent 0)",
          backgroundSize: "44px 44px",
          maskImage:
            "radial-gradient(70% 60% at 50% 0%, black, transparent 80%)",
          WebkitMaskImage:
            "radial-gradient(70% 60% at 50% 0%, black, transparent 80%)",
        }}
      />
    </div>
  );
}
