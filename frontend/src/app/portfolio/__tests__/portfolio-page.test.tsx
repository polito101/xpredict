/**
 * Phase 5 (SC#7) — Portfolio page rendering tests.
 *
 * Runs under jsdom. Mirrors the wallet-page test: PortfolioPage is an async Server
 * Component that reads the session cookie (next/headers) + fetches GET /bets/me/portfolio
 * server-side; we mock BOTH so the test runs fully OFFLINE. We await the component, render
 * the resolved element, and assert on the DOM — both the live-data path and the empty
 * fallback. Money/odds are rendered as STRINGS (SC#4).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

const cookieGet = vi.hoisted(() =>
  vi.fn<(name: string) => { value: string } | undefined>(),
);
vi.mock("next/headers", () => ({
  cookies: vi.fn(async () => ({ get: cookieGet })),
}));

import PortfolioPage from "../page";

beforeEach(() => {
  cookieGet.mockReset();
  vi.restoreAllMocks();
});

describe("PortfolioPage", () => {
  it("renders open + settled positions with payouts and P&L (SC#7)", async () => {
    cookieGet.mockReturnValue({ value: "test-session-token" });

    const body = {
      open: [
        {
          bet_id: "00000000-0000-0000-0000-0000000000a0",
          market_id: "00000000-0000-0000-0000-0000000000b0",
          outcome_id: "00000000-0000-0000-0000-0000000000c0",
          stake: "40.0000",
          odds_at_placement: "0.500000",
          potential_payout: "80.0000",
          potential_pnl: "40.0000",
        },
      ],
      settled: [
        {
          bet_id: "00000000-0000-0000-0000-0000000000a1",
          market_id: "00000000-0000-0000-0000-0000000000b1",
          outcome_id: "00000000-0000-0000-0000-0000000000c1",
          stake: "40.0000",
          odds_at_placement: "0.500000",
          won: true,
          payout: "80.0000",
          realized_pnl: "40.0000",
        },
        {
          bet_id: "00000000-0000-0000-0000-0000000000a2",
          market_id: "00000000-0000-0000-0000-0000000000b2",
          outcome_id: "00000000-0000-0000-0000-0000000000c2",
          stake: "60.0000",
          odds_at_placement: "0.500000",
          won: false,
          payout: "0.0000",
          realized_pnl: "-60.0000",
        },
      ],
    };

    const fetchMock = vi.fn(async () => {
      return {
        ok: true,
        json: async () => body,
        clone: () => ({ json: async () => body }),
      } as unknown as Response;
    });
    vi.stubGlobal("fetch", fetchMock);

    const ui = await PortfolioPage();
    render(ui);

    const text = document.body.textContent ?? "";
    // Open position — potential payout/P&L at the locked odds, money as STRINGS.
    expect(text).toContain("Potential payout 80.0000 PLAY_USD");
    // Settled — won + lost results with realized P&L and payouts.
    expect(text).toContain("Won");
    expect(text).toContain("Lost");
    expect(text).toContain("payout 0.0000 PLAY_USD"); // loser payout
    expect(text).toContain("-60.0000 PLAY_USD"); // loser realized P&L
    // No empty states when there is data.
    expect(screen.queryByTestId("portfolio-open-empty")).toBeNull();
    expect(screen.queryByTestId("portfolio-settled-empty")).toBeNull();
    // Play money — never "deposit" (PITFALLS #3).
    expect(text.toLowerCase()).not.toContain("deposit");
  });

  it("renders empty states when offline (no session cookie)", async () => {
    cookieGet.mockReturnValue(undefined);
    const fetchMock = vi.fn(async () => {
      throw new Error("network should not be reached");
    });
    vi.stubGlobal("fetch", fetchMock);

    const ui = await PortfolioPage();
    render(ui);

    expect(screen.getByTestId("portfolio-open-empty")).toBeInTheDocument();
    expect(screen.getByTestId("portfolio-settled-empty")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
