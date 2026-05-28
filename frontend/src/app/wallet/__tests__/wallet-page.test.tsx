/**
 * Plan 03-05 Task 3 — Player wallet page rendering tests.
 *
 * Runs under `jsdom` (vitest.config.ts environmentMatchGlobs picks .tsx).
 *
 * Strategy (mirrors the codebase's Server-Component-friendly pattern):
 *   - `WalletPage` is an async Server Component that fetches balance + history
 *     server-side via `next/headers` cookies() + global fetch. We mock BOTH so
 *     the test runs fully OFFLINE — no backend, no real cookie store.
 *   - The component is just an async function returning JSX; we `await` it and
 *     render the resolved element, then assert on the DOM.
 *
 * Asserts the SC#6 contract (the "Add funds" button is DISABLED) plus the
 * balance/currency region, for both the live-data path and the offline fallback.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

// --- Mock next/headers cookies() (server-only) -----------------------------
const cookieGet = vi.hoisted(() => vi.fn<(name: string) => { value: string } | undefined>());
vi.mock("next/headers", () => ({
  cookies: vi.fn(async () => ({ get: cookieGet })),
}));

import WalletPage from "../page";

beforeEach(() => {
  cookieGet.mockReset();
  vi.restoreAllMocks();
});

describe("WalletPage", () => {
  it("renders a DISABLED 'Add funds' button (SC#6) and the balance/currency region", async () => {
    // Live-data path: a session cookie is present, fetch returns balance + history.
    cookieGet.mockReturnValue({ value: "test-session-token" });

    const balanceBody = { balance: "100.0000", currency: "PLAY_USD" };
    const txBody = {
      items: [
        {
          kind: "recharge",
          amount: "100.0000",
          direction: "credit",
          created_at: "2026-05-27T16:00:00Z",
          reason: "promo",
        },
      ],
      page: 1,
      page_size: 50,
      total: 1,
      has_next: false,
    };

    const fetchMock = vi.fn(async (url: string) => {
      const body = url.includes("/balance") ? balanceBody : txBody;
      return {
        ok: true,
        json: async () => body,
        clone: () => ({ json: async () => body }),
      } as unknown as Response;
    });
    vi.stubGlobal("fetch", fetchMock);

    const ui = await WalletPage();
    render(ui);

    // SC#6 / PLT-05 — the Add funds button is present and DISABLED.
    const addFunds = screen.getByRole("button", { name: /add funds/i });
    expect(addFunds).toBeInTheDocument();
    expect(addFunds).toBeDisabled();

    // Balance + currency region is present.
    expect(screen.getByLabelText(/wallet balance/i)).toHaveTextContent("100.0000");
    // PLAY_USD appears (currency label).
    expect(screen.getAllByText(/PLAY_USD/i).length).toBeGreaterThan(0);

    // The recharge history row rendered (WAL-04) with its money STRING (SC#4).
    expect(screen.getByText(/recharge/i)).toBeInTheDocument();
    expect(screen.getByText(/\+100\.0000 PLAY_USD/i)).toBeInTheDocument();
  });

  it("renders the disabled button + empty state when offline (no session cookie)", async () => {
    // Fallback path: no session cookie → loadWallet() returns zero balance / empty.
    cookieGet.mockReturnValue(undefined);
    // fetch should not even be called, but stub it to be safe.
    const fetchMock = vi.fn(async () => {
      throw new Error("network should not be reached");
    });
    vi.stubGlobal("fetch", fetchMock);

    const ui = await WalletPage();
    render(ui);

    const addFunds = screen.getByRole("button", { name: /add funds/i });
    expect(addFunds).toBeDisabled();
    expect(screen.getByLabelText(/wallet balance/i)).toHaveTextContent("0");
    expect(screen.getByTestId("wallet-history-empty")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();

    // Copy avoids the word "deposit" (PITFALLS #3).
    expect(document.body.textContent?.toLowerCase()).not.toContain("deposit");
  });
});
