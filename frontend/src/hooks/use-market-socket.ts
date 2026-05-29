/**
 * useMarketSocket -- "use client" WebSocket hook for live market odds
 * (Plan 09-03 Task 4, MKT-04).
 *
 * Ports the validated spike 003 reconnect + stale-detection client logic
 * (`.planning/spikes/003-websocket-price-streaming/index.html`) into a React
 * hook, against the production payload contract (CONTEXT Area 3):
 *
 *   { type: "price_update", market_id, outcomes: [{ outcome_id, odds }], ts }
 *
 * Connection state machine (RESEARCH Pattern 6 + UI-SPEC connection-state
 * table):
 *   - "live"        : socket open + a message within the last 30s.
 *   - "stale"       : socket open but >30s with no message. The last-known
 *                     odds STAY VISIBLE — never blanked (RESEARCH Pitfall 5).
 *   - "reconnecting": socket dropped; reconnect with exponential backoff +
 *                     jitter, capped at 30s (RESEARCH Pattern 6 / Pitfall T-09-11).
 *
 * The base URL comes from `process.env.NEXT_PUBLIC_WS_URL` (browser-readable,
 * MUST be NEXT_PUBLIC_-prefixed — RESEARCH Pitfall 7 / SP-7). Prices are
 * live-only: history is NOT replayed on reconnect (anti-pattern).
 */
"use client";

import { useEffect, useRef, useState } from "react";

export type ConnState = "live" | "stale" | "reconnecting";

const STALE_THRESHOLD_MS = 30_000;
const STALE_CHECK_INTERVAL_MS = 5_000;
const PING_INTERVAL_MS = 25_000;
const MAX_RECONNECT_DELAY_MS = 30_000;

const WS_BASE = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

interface PriceUpdateMessage {
  type: string;
  market_id?: string;
  outcomes?: { outcome_id: string; odds: string }[];
  ts?: number;
}

export interface UseMarketSocketResult {
  odds: Record<string, string>;
  state: ConnState;
}

export function useMarketSocket(
  marketId: string,
  initialOdds: Record<string, string>,
): UseMarketSocketResult {
  const [odds, setOdds] = useState<Record<string, string>>(initialOdds);
  const [state, setState] = useState<ConnState>("reconnecting");

  // Mutable connection state lives in refs so the (single) effect can manage
  // the socket lifecycle without re-subscribing on every render.
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastMsgRef = useRef<number>(0);
  const closedByUnmountRef = useRef(false);

  useEffect(() => {
    closedByUnmountRef.current = false;

    function scheduleReconnect() {
      if (reconnectTimerRef.current || closedByUnmountRef.current) return;
      setState("reconnecting");
      // Exponential backoff: 1s, 2s, 4s, ... capped at 30s, plus 20% jitter.
      const delay = Math.min(
        1000 * 2 ** reconnectAttemptRef.current,
        MAX_RECONNECT_DELAY_MS,
      );
      const jitter = delay * 0.2 * Math.random();
      reconnectAttemptRef.current += 1;
      reconnectTimerRef.current = setTimeout(() => {
        reconnectTimerRef.current = null;
        connect();
      }, Math.round(delay + jitter));
    }

    function connect() {
      if (closedByUnmountRef.current) return;
      // Tear down any prior socket BEFORE creating a new one (BL-01). On a flaky
      // connection (open→error→close→reconnect) the old socket's handlers stay
      // live until the browser GCs it, so a late frame from socket A could call
      // setOdds AFTER socket B is authoritative — odds briefly regress. Detach
      // its handlers and close it so it can neither schedule another reconnect
      // nor mutate state once it is no longer wsRef.current.
      const prev = wsRef.current;
      if (prev) {
        prev.onopen = null;
        prev.onmessage = null;
        prev.onclose = null;
        prev.onerror = null;
        try {
          prev.close();
        } catch {
          /* noop */
        }
      }
      const url = `${WS_BASE}/ws/markets/${marketId}`;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        reconnectAttemptRef.current = 0;
        lastMsgRef.current = Date.now();
        setState("live");
      };

      ws.onmessage = (event: MessageEvent) => {
        // Guard against a stale socket (BL-01): if this is no longer the
        // authoritative socket, a late frame must NOT mutate odds — otherwise
        // an older socket could regress the value a newer socket just set.
        if (wsRef.current !== ws) return;
        let data: PriceUpdateMessage;
        try {
          data = JSON.parse(event.data) as PriceUpdateMessage;
        } catch {
          return;
        }
        // Ignore pong / anything that is not a price delta.
        if (data.type !== "price_update" || !Array.isArray(data.outcomes)) {
          return;
        }
        lastMsgRef.current = Date.now();
        setOdds((prev) => {
          const next = { ...prev };
          for (const o of data.outcomes!) {
            if (o && typeof o.outcome_id === "string") {
              next[o.outcome_id] = o.odds;
            }
          }
          return next;
        });
        setState("live");
      };

      ws.onclose = () => {
        // A stale socket's close must not schedule a reconnect (BL-01) — only
        // the current socket drives the reconnect state machine.
        if (closedByUnmountRef.current || wsRef.current !== ws) return;
        scheduleReconnect();
      };

      ws.onerror = () => {
        // Let onclose drive reconnection; closing here is redundant but safe.
        try {
          ws.close();
        } catch {
          /* noop */
        }
      };
    }

    connect();

    // Stale detector: every 5s, if the socket is open but no message has
    // arrived for >30s, flag "stale" WITHOUT clearing the odds (Pitfall 5).
    const staleInterval = setInterval(() => {
      const ws = wsRef.current;
      if (
        ws &&
        ws.readyState === WebSocket.OPEN &&
        lastMsgRef.current > 0 &&
        Date.now() - lastMsgRef.current > STALE_THRESHOLD_MS
      ) {
        setState("stale");
      }
    }, STALE_CHECK_INTERVAL_MS);

    // Keep-alive ping; the server replies {type:"pong"} (ignored above).
    const pingInterval = setInterval(() => {
      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) {
        try {
          ws.send("ping");
        } catch {
          /* noop */
        }
      }
    }, PING_INTERVAL_MS);

    return () => {
      closedByUnmountRef.current = true;
      clearInterval(staleInterval);
      clearInterval(pingInterval);
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      const ws = wsRef.current;
      if (ws) {
        ws.onopen = null;
        ws.onmessage = null;
        ws.onclose = null;
        ws.onerror = null;
        try {
          ws.close();
        } catch {
          /* noop */
        }
        wsRef.current = null;
      }
    };
    // Re-subscribe only when the target market changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [marketId]);

  return { odds, state };
}
