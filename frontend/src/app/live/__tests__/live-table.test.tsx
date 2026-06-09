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
  // Default settle resolution carries a backend status (WR-01: the host keys
  // the toast off THIS, not the event detail). Per-case tests override it.
  actions.recordLiveSettled.mockResolvedValue({
    ok: true,
    applied: true,
    status: "WON",
  });
  actions.mintLiveSession.mockResolvedValue({
    ok: true,
    session_token: "t2",
    table_id: "tbl",
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

  it("HOST-01: pushes the initial balance onto the widget `balance` attribute (raw String, D-07)", () => {
    const { container } = render(
      <LiveTable sessionToken="t" tableId="tbl" initialBalance="100.0000" />,
    );
    const host = getHost(container);
    // The host reflects the raw `String(initialBalance)` — no `$`, no toFixed;
    // the widget owns `$X.XX`/`—` formatting (D-07).
    expect(host.getAttribute("balance")).toBe("100.0000");
  });

  it("HOST-01: re-pushes the refreshed balance onto the widget `balance` attribute after a bet-placed refresh", async () => {
    const { container } = render(
      <LiveTable sessionToken="t" tableId="tbl" initialBalance="100.0000" />,
    );
    const host = getHost(container);
    expect(host.getAttribute("balance")).toBe("100.0000");

    // getLiveBalance resolves "150.0000" (beforeEach default); the bet-placed
    // refresh moves the in-island `balance`, so the balance-keyed effect re-runs
    // and the attribute reflects the new value (SC1, post-event push).
    await fire(host, "live-bets-bet-placed", { bet_id: "B1" });

    expect(host.getAttribute("balance")).toBe("150.0000");
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

  it("result(WON) -> recordLiveSettled(betId) + refresh + a WON toast keyed off the BACKEND status (WR-01)", async () => {
    // The BACKEND (recordLiveSettled) is the authority on the outcome; the WON
    // toast must come from its returned status, not the event detail.
    actions.recordLiveSettled.mockResolvedValue({
      ok: true,
      applied: true,
      status: "WON",
    });
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

  it("WR-01: event detail says WON but the BACKEND settles LOST -> a 'lost' toast, NOT a celebratory win", async () => {
    // The untrusted widget event claims a win; the backend's authoritative
    // result says LOST. The toast must follow the BACKEND, never the detail.
    actions.recordLiveSettled.mockResolvedValue({
      ok: true,
      applied: true,
      status: "LOST",
    });
    const { container } = render(
      <LiveTable sessionToken="t" tableId="tbl" initialBalance="100.0000" />,
    );
    const host = getHost(container);

    await fire(host, "live-bets-result", {
      bet_id: "B2",
      status: "WON", // tampered/optimistic event detail
      payout: "9999",
    });

    expect(actions.recordLiveSettled).toHaveBeenCalledWith("B2");
    // No "You won!" toast — the backend said LOST.
    expect(toast.success).not.toHaveBeenCalled();
    // The neutral "better luck" copy fired instead.
    expect(toast).toHaveBeenCalledTimes(1);
    expect(toast).toHaveBeenCalledWith(expect.stringMatching(/better luck/i));
  });

  it("WR-01: event detail says LOST but the BACKEND settles WON -> a celebratory win toast (follows the backend)", async () => {
    // The mirror image: a pessimistic/tampered detail must not suppress a real win.
    actions.recordLiveSettled.mockResolvedValue({
      ok: true,
      applied: true,
      status: "WON",
    });
    const { container } = render(
      <LiveTable sessionToken="t" tableId="tbl" initialBalance="100.0000" />,
    );
    const host = getHost(container);

    await fire(host, "live-bets-result", { bet_id: "B2", status: "LOST" });

    expect(toast.success).toHaveBeenCalledTimes(1);
    expect(toast.success).toHaveBeenCalledWith(expect.stringMatching(/won/i));
  });

  it("WR-01: a REFUNDED/unknown backend status falls back to neutral 'settled' copy (no win/loss claim)", async () => {
    actions.recordLiveSettled.mockResolvedValue({
      ok: true,
      applied: true,
      status: "REFUNDED",
    });
    const { container } = render(
      <LiveTable sessionToken="t" tableId="tbl" initialBalance="100.0000" />,
    );
    const host = getHost(container);

    await fire(host, "live-bets-result", { bet_id: "B2", status: "WON" });

    expect(toast.success).not.toHaveBeenCalled();
    expect(toast).toHaveBeenCalledTimes(1);
    expect(toast).toHaveBeenCalledWith(expect.stringMatching(/settled/i));
  });

  it("WR-01: an idempotent settle no-op (applied:false) shows NO win/loss toast", async () => {
    // A duplicate settle event: nothing moved, so the host must not re-announce
    // an outcome — even if the (untrusted) detail claims a win.
    actions.recordLiveSettled.mockResolvedValue({
      ok: true,
      applied: false,
      status: "WON",
    });
    const { container } = render(
      <LiveTable sessionToken="t" tableId="tbl" initialBalance="100.0000" />,
    );
    const host = getHost(container);

    await fire(host, "live-bets-result", { bet_id: "B2", status: "WON" });

    expect(actions.recordLiveSettled).toHaveBeenCalledWith("B2");
    expect(toast.success).not.toHaveBeenCalled();
    expect(toast).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
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

  it("CR-01: a balance refresh AFTER a session re-mint does NOT clobber the freshly re-minted token (SC3)", async () => {
    // Regression for CR-01: the balance push must live in its OWN effect, NOT
    // the identity effect. onSessionExpired re-mints the token imperatively
    // (element -> "t2") without touching the `sessionToken` prop (still "t").
    // A subsequent bet triggers refreshBalance -> setBalance, which must
    // re-push ONLY `balance` — it must NOT re-run the identity effect and
    // clobber session-token back to the stale prop "t" (which would make the
    // widget Branch A teardown WS/HLS and re-init with the EXPIRED token: the
    // stuck-"connecting"/session-expired loop).
    const { container } = render(
      <LiveTable sessionToken="t" tableId="tbl" initialBalance="100.0000" />,
    );
    const host = getHost(container);

    // Re-mint: the element's token becomes "t2" (the prop stays "t").
    await fire(host, "live-bets-session-expired");
    expect(host.getAttribute("session-token")).toBe("t2");

    // A bet refreshes the balance (-> "150.0000"), re-running the balance effect.
    await fire(host, "live-bets-bet-placed", { bet_id: "B1" });

    // The balance moved...
    expect(host.getAttribute("balance")).toBe("150.0000");
    // ...but the re-minted token MUST survive (NOT reverted to the stale "t").
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
