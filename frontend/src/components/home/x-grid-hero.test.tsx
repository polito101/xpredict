/**
 * XGridHero content tests — overlay copy, CTAs, and brand-name normalization.
 * Canvas internals are covered by x-particles.test.tsx; here getContext is
 * nulled so XParticles mounts inert.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

  it("renders the headline, badge, and both CTAs", () => {
    render(<XGridHero brandName="XPredict" />);
    expect(
      screen.getByRole("heading", { level: 1, name: /connects every prediction market/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Prediction-market platform")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Log in" })).toHaveAttribute("href", "/login");
    expect(screen.getByRole("link", { name: "Explore the demo" })).toHaveAttribute(
      "href",
      "/markets",
    );
  });

  it("normalizes the default brand name to XPrediction", () => {
    render(<XGridHero brandName="XPredict" />);
    expect(screen.getByText(/^XPrediction — white-label, API-first/)).toBeInTheDocument();
  });

  it("uses an operator brand name verbatim", () => {
    render(<XGridHero brandName="Acme Bets" />);
    expect(screen.getByText(/^Acme Bets — white-label, API-first/)).toBeInTheDocument();
  });
});
