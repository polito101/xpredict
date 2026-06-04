import { describe, expect, test } from "vitest";

import { pickReadableForeground } from "./brand-color";

/**
 * The operator picks an arbitrary brand color in /admin/branding. Any text we
 * place on top of it (CTA labels, etc.) must stay legible on BOTH a very dark
 * and a very light brand — so we derive the foreground from the brand's
 * relative luminance (WCAG) rather than hardcoding white.
 *
 * Light text  = zinc-50  (#fafafa)
 * Dark text   = zinc-900 (#18181b)
 */
describe("pickReadableForeground", () => {
  test("returns light text on a dark brand color", () => {
    // indigo-600 — the default brand primary, dark enough for white text
    expect(pickReadableForeground("#4f46e5")).toBe("#fafafa");
  });

  test("returns dark text on a light brand color", () => {
    // bright yellow — white text would be unreadable, needs dark text
    expect(pickReadableForeground("#fde047")).toBe("#18181b");
  });

  test("handles the extremes: pure black gets light text, pure white gets dark", () => {
    expect(pickReadableForeground("#000000")).toBe("#fafafa");
    expect(pickReadableForeground("#ffffff")).toBe("#18181b");
  });

  test("accepts a hex without the leading hash", () => {
    expect(pickReadableForeground("4f46e5")).toBe("#fafafa");
  });
});
