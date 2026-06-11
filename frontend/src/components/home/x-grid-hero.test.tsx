/**
 * XGridHero content tests — headline + CTA wiring, and the demoMode branch
 * (one-click demo button vs plain links). Canvas internals are covered by
 * x-particles.test.tsx; here getContext is nulled so XParticles mounts inert.
 * demoLoginAction / useRouter are mocked exactly like demo-login.test.tsx.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const demoLoginActionMock = vi.hoisted(() =>
  vi.fn<(...args: unknown[]) => Promise<unknown>>(async () => undefined),
);
vi.mock("@/lib/auth", async () => {
  const actual = await vi.importActual<typeof import("@/lib/auth")>("@/lib/auth");
  return {
    ...actual,
    demoLoginAction: demoLoginActionMock,
  };
});

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  redirect: vi.fn(),
}));

import { XGridHero } from "./x-grid-hero";

describe("XGridHero", () => {
  beforeEach(() => {
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    window.matchMedia = vi.fn().mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as unknown as MediaQueryList) as unknown as typeof window.matchMedia;
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders login/demo links and NO headline (dropped by request, 2026-06-11) without demo mode", () => {
    render(<XGridHero demoMode={false} />);
    // The hero is canvas + CTAs only — the old "core that connects" h1 is gone.
    expect(screen.queryByRole("heading")).toBeNull();
    expect(screen.getByRole("link", { name: "Log in" })).toHaveAttribute("href", "/login");
    expect(screen.getByRole("link", { name: "Explore the demo" })).toHaveAttribute(
      "href",
      "/markets",
    );
    expect(screen.queryByRole("button", { name: /probar la demo/i })).toBeNull();
  });

  it("demo mode: the one-click demo button is the ONLY CTA (no Log in link, 2026-06-11)", () => {
    render(<XGridHero demoMode />);
    expect(
      screen.getByRole("button", { name: /probar la demo/i }),
    ).toBeInTheDocument();
    // The demo face shows a single action; /login stays reachable by URL only.
    expect(screen.queryByRole("link", { name: "Log in" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Explore the demo" })).toBeNull();
  });
});
