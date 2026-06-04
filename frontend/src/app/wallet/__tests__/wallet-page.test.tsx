/**
 * Plan 03-05 Task 3 — Player wallet page rendering tests.
 * Updated v1.1 Fase C: the page no longer degrades a backend failure / a
 * signed-out visitor to a misleading "0". It now distinguishes three states.
 *
 * Runs under `jsdom`. `WalletPage` is an async Server Component; we mock
 * `next/headers` cookies() and global fetch so it runs fully OFFLINE, await it,
 * and assert on the rendered DOM. `next/navigation` is mocked because the error
 * state renders the client RetryError (useRouter).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

// --- Mock next/headers cookies() (server-only) -----------------------------
const cookieGet = vi.hoisted(() => vi.fn<(name: string) => { value: string } | undefined>());
vi.mock("next/headers", () => ({
  cookies: vi.fn(async () => ({ get: cookieGet })),
}));
// RetryError (error state) is a client component using useRouter.
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

import WalletPage from "../page";

beforeEach(() => {
  cookieGet.mockReset();
  vi.restoreAllMocks();
});

describe("WalletPage", () => {
  it("renders balance, history and the DISABLED 'Add funds' button on the happy path", async () => {
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
    };

    const fetchMock = vi.fn(async (url: string) => {
      const body = url.includes("/balance") ? balanceBody : txBody;
      return { ok: true, json: async () => body } as unknown as Response;
    });
    vi.stubGlobal("fetch", fetchMock);

    render(await WalletPage());

    const addFunds = screen.getByRole("button", { name: /add funds/i });
    expect(addFunds).toBeDisabled();
    expect(screen.getByLabelText(/wallet balance/i)).toHaveTextContent("100.0000");
    expect(screen.getByText(/recharge/i)).toBeInTheDocument();
    expect(screen.getByText(/\+100\.0000 PLAY_USD/i)).toBeInTheDocument();
    // Copy avoids the word "deposit" (PITFALLS #3).
    expect(document.body.textContent?.toLowerCase()).not.toContain("deposit");
  });

  it("prompts to sign in when there is no session — never a misleading zero", async () => {
    cookieGet.mockReturnValue(undefined);
    const fetchMock = vi.fn(async () => {
      throw new Error("network should not be reached");
    });
    vi.stubGlobal("fetch", fetchMock);

    render(await WalletPage());

    expect(screen.getByText(/sign in to see your wallet/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /log in/i })).toBeInTheDocument();
    expect(screen.queryByLabelText(/wallet balance/i)).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows a non-silent retry error when the backend fails (not a fake zero)", async () => {
    cookieGet.mockReturnValue({ value: "test-session-token" });
    const fetchMock = vi.fn(
      async () => ({ ok: false, status: 503, json: async () => ({}) }) as unknown as Response,
    );
    vi.stubGlobal("fetch", fetchMock);

    render(await WalletPage());

    expect(screen.getByRole("alert")).toHaveTextContent(/couldn't load your wallet/i);
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
    expect(screen.queryByLabelText(/wallet balance/i)).not.toBeInTheDocument();
  });
});
