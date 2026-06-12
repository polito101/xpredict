/**
 * LB-B-02 — `/live` player surface (v1.3 Live-Bets demo, SC1).
 *
 * An async Server Component (mirrors `markets/[slug]/page.tsx` + `wallet/page.tsx`)
 * that gates on the player session, mints the live-bets session (which resolves
 * and echoes back the demo `table_id`), and — on the happy path — hands the full
 * viewport to the `LiveFullscreenHost` from `./shared` which renders `<LiveTable>`
 * and wires its DOM events (design §6); wallet balance + XPredict chrome remain
 * only on the empty/error states.
 *
 * The widget's `table-id` comes from the session response's `table_id`, NOT from
 * `/api/live/tables`: the live-bets `GET /tables` route is JWT-gated, so the
 * operator-key `/api/live/tables` 401s and can't supply it.
 *
 * States (none degrade to a misleading empty/zero — v1.1 Fase C error contract):
 *   - catalog configured → table picker (chrome + balance), links to /live/[slug].
 *   - no session cookie        → `SignedOutNotice` (reachable only when authed).
 *   - LiveTableUnconfigured     → friendly "No live table configured yet" empty
 *     state, STILL inside chrome + STILL showing the wallet balance. This is the
 *     DEFAULT LB-B demo state (LB-A ships `LIVEBETS_DEFAULT_TABLE_ID=None`; the
 *     real table arrives in LB-C) and must NOT look like an error (CONTEXT bullet 1).
 *   - balance failure (session OK) → renders with `"0.0000"` fallback; widget refreshes.
 *   - any other session failure    → non-silent `RetryError`.
 *   - success                   → full-viewport overlay + the `<LiveTable>` host
 *     (Plan D: no chrome/balance header — the widget HUD owns all UI).
 *
 * BRAND (CONTEXT white-label note): the XPredict chrome around the widget is
 * on-brand (`--brand-*`); the widget INTERIOR is the live-bets widget's own
 * (partially brandable) styling — out of our control here.
 *
 * Money is a STRING on the wire (SP-1) — the balance is rendered exactly as the
 * backend serialized it; never parsed to a float.
 */
import { Suspense } from "react";
import { cookies } from "next/headers";

import { fetchLiveSession, LiveTableUnconfigured } from "@/lib/api";
import { getLiveCatalog } from "@/lib/live-catalog";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { RetryError } from "@/components/retry-error";
import { SignedOutNotice } from "@/components/signed-out-notice";
import { LiveCatalogPicker } from "./picker";
import {
  BalanceHeader,
  LiveFullscreenHost,
  LiveShell,
  LiveSkeleton,
  loadBalance,
  PAGE_SHELL,
} from "./shared";

async function LiveBody() {
  // Auth gate: derive presence of the HttpOnly session cookie server-side; the
  // cookie VALUE never crosses into client JS (only the rendered result + the
  // minted live-bets token do). SC1: reachable only when authenticated.
  const store = await cookies();
  const session = store.get(SESSION_COOKIE_NAME)?.value;
  if (!session) {
    return (
      <main className={PAGE_SHELL}>
        <header className="mb-8 flex flex-col gap-1">
          <h1 className="font-display text-3xl font-semibold tracking-tight">
          Live
        </h1>
          <p className="text-sm text-muted-foreground">
            Multiplayer live bets with your XPrediction balance.
          </p>
        </header>
        <SignedOutNotice resource="live" />
      </main>
    );
  }

  // Multi-table: a configured catalog turns /live into a picker — no session
  // mint here (each /live/[slug] page mints for its own table). Empty catalog
  // → the original single-default-table flow below, unchanged.
  const catalog = getLiveCatalog();
  if (catalog.length > 0) {
    const balanceResult = await loadBalance(session);
    return (
      <LiveCatalogPicker
        entries={catalog}
        balance={balanceResult.ok ? balanceResult.balance : null}
      />
    );
  }

  // SP-5: mint the live session + read the balance IN PARALLEL. The session is
  // the gate (LiveTableUnconfigured → empty state); the balance degrades to a
  // non-silent error only when the session itself succeeded.
  const [sessionResult, balanceResult] = await Promise.allSettled([
    fetchLiveSession(session),
    loadBalance(session),
  ]);

  // Resolve the balance for display (string). A balance failure on its own does
  // not blank the page — but with a working session we still surface it as an
  // error below; in the empty state we show whatever balance we have.
  const balance =
    balanceResult.status === "fulfilled" && balanceResult.value.ok
      ? balanceResult.value.balance
      : null;

  // No table configured yet (the default LB-B demo state) → friendly empty state,
  // STILL in chrome + STILL showing the balance. Not an error.
  if (
    sessionResult.status === "rejected" &&
    sessionResult.reason instanceof LiveTableUnconfigured
  ) {
    return (
      <LiveShell>
        <BalanceHeader balance={balance ?? "0.0000"} />
        <Card>
          <CardHeader>
            <CardTitle className="text-lg font-semibold">
              No live table configured yet
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm leading-relaxed text-muted-foreground">
              The live-bets table isn&apos;t set up in this environment yet. Once
              a table is running, it will appear here and your XPrediction balance
              will react to every bet.
            </p>
          </CardContent>
        </Card>
      </LiveShell>
    );
  }

  // Any other session failure → non-silent error (mirror wallet/portfolio).
  if (sessionResult.status === "rejected") {
    return (
      <LiveShell>
        <RetryError
          title="We couldn't load the live table"
          message="The live-bets service didn't respond. Please try again."
        />
      </LiveShell>
    );
  }

  // Session OK but the balance read failed → degrade gracefully: pass "0.0000"
  // as the initial balance and let the component render anyway. The HOST-01 widget
  // handles its own balance refresh, so the stale/missing initial value is
  // corrected on first widget event without blocking the page.
  const initialBalance = balance ?? "0.0000";

  // The widget's `table-id` comes straight from the session: LB-A mints the
  // session for a resolved table (`body.table_id` or `LIVEBETS_DEFAULT_TABLE_ID`)
  // and echoes that id back as `SessionResponse.table_id`. We deliberately do NOT
  // call `/api/live/tables` for it — the underlying live-bets `GET /tables` is
  // JWT-gated, but our route uses the operator key, which 401s. A session with no
  // configured table already 400'd above into the friendly empty state, so a
  // successful session always carries a usable `table_id` here.
  const { session_token, table_id } = sessionResult.value;

  return (
    <LiveFullscreenHost
      sessionToken={session_token}
      tableId={table_id}
      initialBalance={initialBalance}
    />
  );
}

export default function LivePage() {
  return (
    <Suspense fallback={<LiveSkeleton />}>
      <LiveBody />
    </Suspense>
  );
}
