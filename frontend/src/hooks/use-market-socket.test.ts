/**
 * @vitest-environment jsdom
 *
 * Plan 09-03 Task 4 -- use-market-socket connection state machine tests.
 *
 * Runs under jsdom (overridden via the docblock above — the file is named
 * `.test.ts`, which the vitest config otherwise routes to the `node`
 * environment; `renderHook` needs a DOM container).
 *
 * Uses vitest fake timers + a stub WebSocket so the state machine is driven
 * deterministically with no real network:
 *   (a) a `price_update` message sets state "live" and updates the odds map;
 *   (b) advancing the clock past 30s with no message sets state "stale" while
 *       the prior odds value is RETAINED (RESEARCH Pitfall 5 — never blank the
 *       odds on stale).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, renderHook } from "@testing-library/react";

// -- Stub WebSocket -----------------------------------------------------------
// Captures the last constructed instance so tests can drive onopen/onmessage.

class StubWebSocket {
  static OPEN = 1;
  static CLOSED = 3;
  static instances: StubWebSocket[] = [];

  url: string;
  readyState = StubWebSocket.OPEN;
  onopen: ((ev: unknown) => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: ((ev: unknown) => void) | null = null;
  onerror: ((ev: unknown) => void) | null = null;
  sent: string[] = [];
  closed = false;

  constructor(url: string) {
    this.url = url;
    StubWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.closed = true;
    this.readyState = StubWebSocket.CLOSED;
  }

  // -- test helpers --
  emitOpen() {
    this.onopen?.({});
  }
  emitMessage(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }
}

beforeEach(() => {
  StubWebSocket.instances = [];
  vi.stubGlobal("WebSocket", StubWebSocket as unknown as typeof WebSocket);
  vi.stubEnv("NEXT_PUBLIC_WS_URL", "ws://localhost:8000");
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

const MARKET_ID = "market-123";
const OUTCOME_YES = "outcome-yes";
const OUTCOME_NO = "outcome-no";

// Import after the globals are stubbed at module-eval time is fine — the hook
// reads `WebSocket` lazily inside an effect, not at import.
import { useMarketSocket } from "@/hooks/use-market-socket";

describe("useMarketSocket", () => {
  it("connects to NEXT_PUBLIC_WS_URL/ws/markets/{id}", () => {
    renderHook(() =>
      useMarketSocket(MARKET_ID, { [OUTCOME_YES]: "0.50", [OUTCOME_NO]: "0.50" }),
    );
    const ws = StubWebSocket.instances.at(-1);
    expect(ws?.url).toBe(`ws://localhost:8000/ws/markets/${MARKET_ID}`);
  });

  it("a price_update sets state 'live' and updates the odds map", () => {
    const { result } = renderHook(() =>
      useMarketSocket(MARKET_ID, { [OUTCOME_YES]: "0.50", [OUTCOME_NO]: "0.50" }),
    );
    const ws = StubWebSocket.instances.at(-1)!;

    act(() => {
      ws.emitOpen();
      ws.emitMessage({
        type: "price_update",
        market_id: MARKET_ID,
        outcomes: [
          { outcome_id: OUTCOME_YES, odds: "0.63" },
          { outcome_id: OUTCOME_NO, odds: "0.37" },
        ],
        ts: 1.0,
      });
    });

    expect(result.current.state).toBe("live");
    expect(result.current.odds[OUTCOME_YES]).toBe("0.63");
    expect(result.current.odds[OUTCOME_NO]).toBe("0.37");
  });

  it(">30s of silence flips state to 'stale' but KEEPS the last odds (Pitfall 5)", () => {
    const { result } = renderHook(() =>
      useMarketSocket(MARKET_ID, { [OUTCOME_YES]: "0.50", [OUTCOME_NO]: "0.50" }),
    );
    const ws = StubWebSocket.instances.at(-1)!;

    act(() => {
      ws.emitOpen();
      ws.emitMessage({
        type: "price_update",
        market_id: MARKET_ID,
        outcomes: [{ outcome_id: OUTCOME_YES, odds: "0.63" }],
        ts: 1.0,
      });
    });
    expect(result.current.state).toBe("live");

    // Advance past 30s with no further message. The stale detector polls every
    // 5s, so the first tick STRICTLY past the 30s threshold is at t=35s
    // (at t=30s the elapsed is exactly 30s, not yet > 30s). This 5s detection
    // granularity matches the validated spike 003 stale timer.
    act(() => {
      vi.advanceTimersByTime(35_000);
    });

    expect(result.current.state).toBe("stale");
    // The odds value must remain visible — NEVER blanked on stale.
    expect(result.current.odds[OUTCOME_YES]).toBe("0.63");
  });

  it("ignores non-price_update messages (e.g. pong)", () => {
    const { result } = renderHook(() =>
      useMarketSocket(MARKET_ID, { [OUTCOME_YES]: "0.50" }),
    );
    const ws = StubWebSocket.instances.at(-1)!;

    act(() => {
      ws.emitOpen();
      ws.emitMessage({ type: "pong", ts: 1.0 });
    });

    // odds unchanged from the initial value; pong does not corrupt state
    expect(result.current.odds[OUTCOME_YES]).toBe("0.50");
  });
});
