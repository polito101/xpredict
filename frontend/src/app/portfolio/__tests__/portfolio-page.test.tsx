/**
 * Phase 5 (SC#7) — Portfolio page rendering tests.
 * Updated v1.1 Fase C: a backend failure / signed-out visitor no longer degrades
 * to a misleading "empty portfolio" — the page distinguishes three states.
 *
 * Runs under jsdom. PortfolioPage is an async Server Component reading the
 * session cookie (next/headers) + fetching GET /bets/me/portfolio; both mocked
 * so it runs OFFLINE. next/navigation is mocked for the error-state RetryError.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

const cookieGet = vi.hoisted(() =>
  vi.fn<(name: string) => { value: string } | undefined>(),
);
vi.mock("next/headers", () => ({
  cookies: vi.fn(async () => ({ get: cookieGet })),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));

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
          current_value: "40.0000",
          unrealized_pnl: "0.0000",
          priced: true,
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
          status: "SETTLED_WON",
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
          status: "SETTLED_LOST",
        },
      ],
    };

    const fetchMock = vi.fn(
      async () => ({ ok: true, json: async () => body }) as unknown as Response,
    );
    vi.stubGlobal("fetch", fetchMock);

    render(await PortfolioPage());

    const text = document.body.textContent ?? "";
    expect(text).toContain("Potential payout 80.0000 PLAY_USD");
    expect(text).toContain("Won");
    expect(text).toContain("Lost");
    expect(text).toContain("payout 0.0000 PLAY_USD");
    expect(text).toContain("-60.0000 PLAY_USD");
    expect(screen.queryByTestId("portfolio-open-empty")).toBeNull();
    expect(screen.queryByTestId("portfolio-settled-empty")).toBeNull();
    expect(text.toLowerCase()).not.toContain("deposit");
    expect(text).toContain("Cerrar");
  });

  it("prompts to sign in when there is no session — not an empty portfolio", async () => {
    cookieGet.mockReturnValue(undefined);
    const fetchMock = vi.fn(async () => {
      throw new Error("network should not be reached");
    });
    vi.stubGlobal("fetch", fetchMock);

    render(await PortfolioPage());

    expect(screen.getByText(/sign in to see your portfolio/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /log in/i })).toBeInTheDocument();
    expect(screen.queryByTestId("portfolio-open-empty")).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows a non-silent retry error when the backend fails", async () => {
    cookieGet.mockReturnValue({ value: "test-session-token" });
    const fetchMock = vi.fn(
      async () => ({ ok: false, status: 503, json: async () => ({}) }) as unknown as Response,
    );
    vi.stubGlobal("fetch", fetchMock);

    render(await PortfolioPage());

    expect(screen.getByRole("alert")).toHaveTextContent(/couldn't load your portfolio/i);
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("shows a real, negative Open P&L when a position has lost value", async () => {
    cookieGet.mockReturnValue({ value: "test-session-token" });
    const body = {
      open: [
        {
          bet_id: "00000000-0000-0000-0000-0000000000d0",
          market_id: "00000000-0000-0000-0000-0000000000e0",
          outcome_id: "00000000-0000-0000-0000-0000000000f0",
          stake: "40.0000",
          odds_at_placement: "0.500000",
          potential_payout: "80.0000",
          potential_pnl: "40.0000",
          current_value: "27.5000",
          unrealized_pnl: "-12.5000",
          priced: true,
        },
      ],
      settled: [],
    };
    const fetchMock = vi.fn(
      async () => ({ ok: true, json: async () => body }) as unknown as Response,
    );
    vi.stubGlobal("fetch", fetchMock);

    render(await PortfolioPage());

    const text = document.body.textContent ?? "";
    expect(text).toContain("-12.5000 PLAY_USD"); // per-position real P&L (negative)
    expect(text).toContain("-12.50");            // summary Open P&L tile (sum, 2dp)
    expect(text).toContain("Current value");
  });
});
