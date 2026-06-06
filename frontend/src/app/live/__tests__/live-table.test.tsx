/**
 * LB-B-03 Task 3 — `<LiveTable>` client island DOM-event wiring tests.
 *
 * Runs under `jsdom` (file is `*.test.tsx`). Renders the real client island with
 * `@/lib/live-actions`, `next/script`, `next/navigation` and `sonner` mocked,
 * then drives the real `<live-bets-table>` custom element with `CustomEvent`s and
 * asserts the wiring: each event -> the correct Server Action, the in-island
 * wallet refresh via `getLiveBalance` (plan-check M-2), the toast surfaces, the
 * `applied:false` no-op, and listener cleanup on unmount (SC3). Fully hermetic —
 * no real widget, no network. Mirrors the `act`/event-driving style of
 * `use-market-socket.test.ts`.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, act } from "@testing-library/react";

// --- Mock the Server Actions (stable hoisted fns, M-2: getLiveBalance too) ---
const actions = vi.hoisted(() => ({
  recordLivePlaced: vi.fn(),
  recordLiveSettled: vi.fn(),
  mintLiveSession: vi.fn(),
  getLiveBalance: vi.fn(),
}));
vi.mock("@/lib/live-actions", () => actions);

// next/script must not load a real widget script.
vi.mock("next/script", () => ({ default: () => null }));

// The island calls useRouter() indirectly only if used; mock defensively.
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

// sonner toast: a callable fn (toast(...)) carrying .success/.error methods.
const toast = vi.hoisted(() => {
  const fn = vi.fn() as ReturnType<typeof vi.fn> & {
    success: ReturnType<typeof vi.fn>;
    error: ReturnType<typeof vi.fn>;
  };
  fn.success = vi.fn();
  fn.error = vi.fn();
  return fn;
});
vi.mock("sonner", () => ({ toast }));

import { LiveTable } from "../live-table";

/** The custom element host the widget would otherwise own. */
function getHost(container: HTMLElement): HTMLElement {
  const el = container.querySelector("live-bets-table");
  if (!el) throw new Error("live-bets-table host not found");
  return el as HTMLElement;
}

/** Dispatch a widget event and flush the handler's chained async work. */
async function fire(el: HTMLElement, type: string, detail?: unknown) {
  await act(async () => {
    el.dispatchEvent(new CustomEvent(type, detail ? { detail } : {}));
    // Flush the handler's `void (async () => …)()` chain (action -> refresh ->
    // setState). Two awaited microtask turns cover action + refreshBalance.
    await Promise.resolve();
    await Promise.resolve();
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  // Default happy resolutions; per-case tests override.
  actions.recordLivePlaced.mockResolvedValue({ ok: true, applied: true });
  actions.recordLiveSettled.mockResolvedValue({ ok: true, applied: true });
  actions.mintLiveSession.mockResolvedValue({
    ok: true,
    session_token: "t2",
    expires_at: "2026-06-06T11:00:00Z",
  });
  actions.getLiveBalance.mockResolvedValue({ ok: true, balance: "150.0000" });
  vi.stubEnv("NEXT_PUBLIC_LIVEBETS_WIDGET_SRC", "http://widget.test/widget.js");
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("<LiveTable /> DOM-event wiring", () => {
  it("mounts the widget host with session-token + table-id set imperatively", () => {
    const { container } = render(
      <LiveTable sessionToken="t" tableId="tbl" initialBalance="100.0000" />,
    );
    const host = getHost(container);
    expect(host.getAttribute("session-token")).toBe("t");
    expect(host.getAttribute("table-id")).toBe("tbl");
  });

  it("bet-placed -> recordLivePlaced(betId) + getLiveBalance refresh updates the balance", async () => {
    const { container } = render(
      <LiveTable sessionToken="t" tableId="tbl" initialBalance="100.0000" />,
    );
    const host = getHost(container);
    const balance = container.querySelector('[data-testid="live-balance"]')!;
    expect(balance).toHaveTextContent("100.0000");

    await fire(host, "live-bets-bet-placed", { bet_id: "B1" });

    expect(actions.recordLivePlaced).toHaveBeenCalledWith("B1");
    // M-2: the in-island balance is refreshed via getLiveBalance and moves.
    expect(actions.getLiveBalance).toHaveBeenCalledTimes(1);
    expect(balance).toHaveTextContent("150.0000");
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("result(WON) -> recordLiveSettled(betId) + refresh + a WON toast", async () => {
    const { container } = render(
      <LiveTable sessionToken="t" tableId="tbl" initialBalance="100.0000" />,
    );
    const host = getHost(container);

    await fire(host, "live-bets-result", {
      bet_id: "B2",
      status: "WON",
      payout: "50",
    });

    expect(actions.recordLiveSettled).toHaveBeenCalledWith("B2");
    expect(actions.getLiveBalance).toHaveBeenCalledTimes(1);
    expect(toast.success).toHaveBeenCalledTimes(1);
    expect(toast.success).toHaveBeenCalledWith(expect.stringMatching(/won/i));
  });

  it("session-expired -> mintLiveSession + re-sets session-token to the new token", async () => {
    const { container } = render(
      <LiveTable sessionToken="t" tableId="tbl" initialBalance="100.0000" />,
    );
    const host = getHost(container);

    await fire(host, "live-bets-session-expired");

    expect(actions.mintLiveSession).toHaveBeenCalledWith("tbl");
    expect(host.getAttribute("session-token")).toBe("t2");
  });

  it("error -> a non-silent toast carrying the widget message (nothing swallowed)", async () => {
    const { container } = render(
      <LiveTable sessionToken="t" tableId="tbl" initialBalance="100.0000" />,
    );
    const host = getHost(container);

    await fire(host, "live-bets-error", { message: "boom" });

    expect(toast.error).toHaveBeenCalledTimes(1);
    expect(toast.error).toHaveBeenCalledWith("boom");
  });

  it("applied:false is a benign no-op success — no error toast (idempotent duplicate)", async () => {
    actions.recordLivePlaced.mockResolvedValue({ ok: true, applied: false });
    const { container } = render(
      <LiveTable sessionToken="t" tableId="tbl" initialBalance="100.0000" />,
    );
    const host = getHost(container);

    await fire(host, "live-bets-bet-placed", { bet_id: "B1" });

    expect(actions.recordLivePlaced).toHaveBeenCalledWith("B1");
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("removes listeners on unmount — a later event does NOT re-fire the action (SC3)", async () => {
    const { container, unmount } = render(
      <LiveTable sessionToken="t" tableId="tbl" initialBalance="100.0000" />,
    );
    const host = getHost(container);

    await fire(host, "live-bets-bet-placed", { bet_id: "B1" });
    expect(actions.recordLivePlaced).toHaveBeenCalledTimes(1);

    // Detach the host from React BEFORE unmount so the element survives to be
    // re-dispatched against (proves the listener — not the node — was removed).
    unmount();
    await fire(host, "live-bets-bet-placed", { bet_id: "B1" });

    // Still only the single pre-unmount call — the listener was cleaned up.
    expect(actions.recordLivePlaced).toHaveBeenCalledTimes(1);
  });
});
