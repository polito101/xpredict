/**
 * LB-B-03 Task 2 — `/live` Server Component rendering tests.
 *
 * Runs under `jsdom` (file is `*.test.tsx`). The page is an async Server
 * Component wrapped in `<Suspense>`; we mock `next/headers` cookies(), mock
 * `@/lib/api` (controllable `fetchLiveSession` / `fetchLiveTables`, but the REAL
 * `LiveTableUnconfigured` class so the page's `instanceof` branch holds), stub
 * the `LiveTable` client island to a marker, and stub global `fetch` for the
 * server-side `/wallet/me/balance` read. We render the page and `await` the
 * Suspense boundary via `findBy*`, then assert on the DOM — fully OFFLINE.
 *
 * Mirrors `wallet/__tests__/wallet-page.test.tsx`.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

// --- Mock next/headers cookies() (server-only) -----------------------------
const cookieGet = vi.hoisted(() =>
  vi.fn<(name: string) => { value: string } | undefined>(),
);
vi.mock("next/headers", () => ({
  cookies: vi.fn(async () => ({ get: cookieGet })),
}));

// RetryError (error state) is a client component using useRouter.
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

// --- Mock @/lib/api: controllable session/table helpers, REAL error class ---
// `importActual` re-exports the genuine `LiveTableUnconfigured` so the page's
// `reason instanceof LiveTableUnconfigured` check resolves correctly.
const fetchLiveSession = vi.hoisted(() => vi.fn());
const fetchLiveTables = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchLiveSession,
    fetchLiveTables,
  };
});

// Stub the LiveTable client island so this stays a pure page-state test (no
// widget, no script, no live-actions). The marker carries its props so the
// happy-path test can assert the island was handed the resolved token/table.
vi.mock("@/app/live/live-table", () => ({
  LiveTable: ({
    sessionToken,
    tableId,
    initialBalance,
  }: {
    sessionToken: string;
    tableId: string;
    initialBalance: string;
  }) => (
    <div
      data-testid="live-table-island"
      data-session-token={sessionToken}
      data-table-id={tableId}
      data-initial-balance={initialBalance}
    />
  ),
}));

import { LiveTableUnconfigured } from "@/lib/api";
import LivePage from "../page";

/**
 * Render the page's async body, awaited.
 *
 * `LivePage()` returns `<Suspense fallback={…}><LiveBody /></Suspense>`. React's
 * jsdom client renderer does not resolve an async Server Component inside a
 * `<Suspense>` boundary (it would render the fallback forever), so — mirroring
 * `wallet-page.test.tsx`'s `render(await WalletPage())` — we reach the async
 * `LiveBody` element (the Suspense child), invoke it to resolve its promise, and
 * render the resolved tree. This awaits the real server logic with no source
 * change (LiveBody is intentionally not exported).
 */
async function renderLive() {
  const suspense = LivePage() as React.ReactElement<{
    children: React.ReactElement;
  }>;
  const bodyEl = suspense.props.children;
  const LiveBody = bodyEl.type as () => Promise<React.ReactElement>;
  render(await LiveBody());
}

/** Stub the server-side `/wallet/me/balance` read to a fixed balance string. */
function stubBalance(balance: string | null) {
  const fetchMock = vi.fn(async () =>
    balance === null
      ? ({ ok: false, status: 503, json: async () => ({}) } as unknown as Response)
      : ({ ok: true, json: async () => ({ balance }) } as unknown as Response),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => {
  cookieGet.mockReset();
  fetchLiveSession.mockReset();
  fetchLiveTables.mockReset();
  vi.unstubAllGlobals();
});

describe("LivePage (/live Server Component)", () => {
  it("prompts sign-in with no session and never calls the session helper", async () => {
    cookieGet.mockReturnValue(undefined);
    const fetchMock = stubBalance("100.0000");

    await renderLive();

    // SignedOutNotice copy (mirrors the wallet signed-out notice).
    expect(screen.getByText(/sign in/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /log in/i })).toBeInTheDocument();
    // No wallet balance shown, and the session/balance reads never fired.
    expect(screen.queryByLabelText(/wallet balance/i)).not.toBeInTheDocument();
    expect(fetchLiveSession).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the friendly empty state (NOT an error) + the balance when no table is configured", async () => {
    cookieGet.mockReturnValue({ value: "test-session" });
    fetchLiveSession.mockRejectedValue(new LiveTableUnconfigured());
    stubBalance("100.0000");

    await renderLive();

    expect(
      screen.getByText(/no live table configured yet/i),
    ).toBeInTheDocument();
    // Empty state must NOT look like an error.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    // Balance still shown inside chrome.
    expect(screen.getByLabelText(/wallet balance/i)).toHaveTextContent("100.0000");
    // The island never renders in the empty state.
    expect(screen.queryByTestId("live-table-island")).not.toBeInTheDocument();
  });

  it("shows chrome + wallet balance + the LiveTable island on the happy path", async () => {
    cookieGet.mockReturnValue({ value: "test-session" });
    fetchLiveSession.mockResolvedValue({
      session_token: "live-token-1",
      expires_at: "2026-06-06T10:00:00Z",
    });
    fetchLiveTables.mockResolvedValue([{ table_id: "tbl-1", name: "Demo" }]);
    stubBalance("100.0000");

    await renderLive();

    // Labelled wallet balance (BalanceHeader). The stubbed island also carries
    // an aria-label in production, but here it is replaced by the marker, so the
    // only "wallet balance" element is the header — assert via the island marker
    // for the token/table handoff.
    expect(screen.getByLabelText(/wallet balance/i)).toHaveTextContent(
      "100.0000",
    );
    const island = screen.getByTestId("live-table-island");
    expect(island).toBeInTheDocument();
    expect(island).toHaveAttribute("data-session-token", "live-token-1");
    expect(island).toHaveAttribute("data-table-id", "tbl-1");
    expect(island).toHaveAttribute("data-initial-balance", "100.0000");
  });

  it("shows a non-silent retry error on a generic (non-unconfigured) session failure", async () => {
    cookieGet.mockReturnValue({ value: "test-session" });
    fetchLiveSession.mockRejectedValue(new Error("live-bets 502"));
    stubBalance("100.0000");

    await renderLive();

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(/couldn't load the live table/i);
    // Not the empty state, not the island.
    expect(screen.queryByText(/no live table configured yet/i)).not.toBeInTheDocument();
    expect(screen.queryByTestId("live-table-island")).not.toBeInTheDocument();
  });
});
