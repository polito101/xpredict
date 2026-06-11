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

  it("renders the headline and login/demo links without demo mode", () => {
    render(<XGridHero demoMode={false} />);
    expect(
      screen.getByRole("heading", { level: 1, name: /connects every prediction market/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Log in" })).toHaveAttribute("href", "/login");
    expect(screen.getByRole("link", { name: "Explore the demo" })).toHaveAttribute(
      "href",
      "/markets",
    );
    expect(screen.queryByRole("button", { name: /probar la demo/i })).toBeNull();
  });

  it("demo mode: one-click demo button is the primary CTA", () => {
    render(<XGridHero demoMode />);
    expect(
      screen.getByRole("button", { name: /probar la demo/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Log in" })).toHaveAttribute("href", "/login");
    expect(screen.queryByRole("link", { name: "Explore the demo" })).toBeNull();
  });
});
