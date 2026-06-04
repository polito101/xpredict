import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";

import { Button } from "./button";

/**
 * White-label (v1.1 Fase A): the primary CTA ("Place bet", etc.) must carry the
 * operator's brand color so a palette change in /admin/branding re-skins it.
 * The destructive variant stays semantic red — it signals danger, not brand.
 */
describe("<Button /> brand-aware variants", () => {
  test("the default (primary CTA) variant uses the brand token", () => {
    render(<Button>Place bet</Button>);
    const btn = screen.getByRole("button", { name: "Place bet" });
    expect(btn.className).toContain("bg-brand-primary");
    expect(btn.className).toContain("text-brand-primary-foreground");
  });

  test("the default variant no longer hardcodes the zinc palette", () => {
    render(<Button>Place bet</Button>);
    const btn = screen.getByRole("button", { name: "Place bet" });
    expect(btn.className).not.toContain("bg-zinc-900");
  });

  test("the destructive variant stays semantic red, not brand", () => {
    render(<Button variant="destructive">Delete</Button>);
    const btn = screen.getByRole("button", { name: "Delete" });
    expect(btn.className).not.toContain("bg-brand-primary");
    expect(btn.className).toContain("bg-red-500");
  });
});
