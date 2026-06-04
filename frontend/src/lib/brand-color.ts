/**
 * Brand-color helpers — derive readable, accessible text colors from an
 * operator's arbitrary brand palette (white-label, v1.1 Fase A).
 *
 * The operator picks any `#rrggbb` in /admin/branding. We must keep text on
 * top of that color legible whether the brand is near-black or near-white, so
 * we choose the foreground from the brand's WCAG relative luminance rather than
 * hardcoding white (which breaks on a light brand).
 */

/** zinc-50 — light text for dark brand backgrounds. */
const LIGHT_TEXT = "#fafafa";
/** zinc-900 — dark text for light brand backgrounds. */
const DARK_TEXT = "#18181b";

/** Linearize one sRGB channel (0..1) per the WCAG relative-luminance formula. */
function linearize(channel: number): number {
  return channel <= 0.03928
    ? channel / 12.92
    : Math.pow((channel + 0.055) / 1.055, 2.4);
}

/**
 * Returns the readable text color (`#fafafa` or `#18181b`) to place on top of
 * the given brand hex. Accepts the hex with or without a leading `#`.
 *
 * The 0.179 cutoff is the luminance at which black text's contrast ratio
 * overtakes white text's — the standard threshold for this binary choice.
 */
export function pickReadableForeground(hex: string): string {
  const normalized = hex.replace(/^#/, "");
  const r = parseInt(normalized.slice(0, 2), 16) / 255;
  const g = parseInt(normalized.slice(2, 4), 16) / 255;
  const b = parseInt(normalized.slice(4, 6), 16) / 255;

  const luminance =
    0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b);

  return luminance > 0.179 ? DARK_TEXT : LIGHT_TEXT;
}
