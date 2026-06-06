/**
 * LB-B-02 — `/live` player surface (v1.3 Live-Bets demo, SC1).
 *
 * An async Server Component (mirrors `markets/[slug]/page.tsx` + `wallet/page.tsx`)
 * that gates on the player session, mints the live-bets session (which resolves
 * and echoes back the demo `table_id`), and shows the player's XPredict wallet
 * balance inside XPredict chrome — then hands off to the `"use client"`
 * `<LiveTable>` host which loads the widget and wires its DOM events (design §6).
 *
 * The widget's `table-id` comes from the session response's `table_id`, NOT from
 * `/api/live/tables`: the live-bets `GET /tables` route is JWT-gated, so the
 * operator-key `/api/live/tables` 401s and can't supply it.
 *
 * States (none degrade to a misleading empty/zero — v1.1 Fase C error contract):
 *   - no session cookie        → `SignedOutNotice` (reachable only when authed).
 *   - LiveTableUnconfigured     → friendly "No live table configured yet" empty
 *     state, STILL inside chrome + STILL showing the wallet balance. This is the
 *     DEFAULT LB-B demo state (LB-A ships `LIVEBETS_DEFAULT_TABLE_ID=None`; the
 *     real table arrives in LB-C) and must NOT look like an error (CONTEXT bullet 1).
 *   - any other session/balance failure → non-silent `RetryError`.
 *   - success                   → chrome + balance header + the `<LiveTable>` host.
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
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { RetryError } from "@/components/retry-error";
import { SignedOutNotice } from "@/components/signed-out-notice";
import { LiveTable } from "./live-table";

const PAGE_SHELL = "w-full max-w-6xl mx-auto px-4 sm:px-6 py-12";
const CURRENCY = "PLAY_USD";

/**
 * Server-only backend base for the cookie-forwarded wallet-balance read (mirrors
 * `wallet/page.tsx:53-55`). No `NEXT_PUBLIC_` prefix, so the backend origin never
 * leaks into the client bundle.
 */
function getBackendUrl(): string {
  return process.env.BACKEND_URL || "http://localhost:8000";
}

type BalanceResult = { ok: true; balance: string } | { ok: false };

/**
 * Read the player's wallet balance server-side, forwarding the session cookie —
 * REUSES the exact `/wallet/me/balance` mechanism from `wallet/page.tsx:62-90`
 * (`{ balance }`, a string). Returns a discriminated result so the page can keep
 * rendering chrome + a non-silent error rather than a misleading "0".
 */
async function loadBalance(session: string): Promise<BalanceResult> {
  try {
    const res = await fetch(`${getBackendUrl()}/wallet/me/balance`, {
      headers: { Cookie: `xpredict_session=${session}` },
      cache: "no-store",
    });
    if (!res.ok) return { ok: false };
    const data = (await res.json()) as { balance?: unknown };
    // WR-02: a non-string balance (malformed/garbage body) is a FAILURE, not a
    // real "0". Route it to the page's existing RetryError path — never fabricate
    // a zero balance, which the page's own no-misleading-zero contract forbids.
    // Matches the sibling `getLiveBalance` `{ok:false}` on the identical case.
    if (typeof data.balance !== "string") return { ok: false };
    return { ok: true, balance: data.balance };
  } catch {
    return { ok: false };
  }
}

/** The `/live` body — loading skeleton shape (header + balance card + widget). */
function LiveSkeleton() {
  return (
    <main className={PAGE_SHELL}>
      <div className="mb-8 flex flex-col gap-2">
        <Skeleton className="h-9 w-32" />
        <Skeleton className="h-4 w-64" />
      </div>
      <Skeleton className="mb-6 h-20 w-full rounded-xl" />
      <Skeleton className="h-96 w-full rounded-xl" />
    </main>
  );
}

/** Page chrome wrapper shared by the empty + success states. */
function LiveShell({ children }: { children: React.ReactNode }) {
  return (
    <main className={PAGE_SHELL}>
      <header className="mb-8 flex flex-col gap-1">
        <h1 className="font-display text-3xl font-semibold tracking-tight">
          Live
        </h1>
        <p className="text-sm text-muted-foreground">
          Multiplayer live bets — your XPrediction balance, in real time.
        </p>
      </header>
      {children}
    </main>
  );
}

/** The wallet-balance header card (labelled element mirrors `wallet/page.tsx`). */
function BalanceHeader({ balance }: { balance: string }) {
  return (
    <Card className="mb-6">
      <CardHeader>
        <CardTitle>
          <span aria-label="wallet balance">{balance}</span>{" "}
          <span className="text-base font-normal text-muted-foreground">
            {CURRENCY}
          </span>
        </CardTitle>
      </CardHeader>
    </Card>
  );
}

async function LiveBody() {
  // Auth gate: derive presence of the HttpOnly session cookie server-side; the
  // cookie VALUE never crosses into client JS (only the rendered result + the
  // minted live-bets token do). SC1: reachable only when authenticated.
  const store = await cookies();
  const session = store.get("xpredict_session")?.value;
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
        {balance !== null && <BalanceHeader balance={balance} />}
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

  // Session OK but the balance read failed → non-silent error (don't show "0").
  if (balance === null) {
    return (
      <LiveShell>
        <RetryError
          title="We couldn't load your balance"
          message="The balance service didn't respond. Your funds are safe — please try again."
        />
      </LiveShell>
    );
  }

  // The widget's `table-id` comes straight from the session: LB-A mints the
  // session for a resolved table (`body.table_id` or `LIVEBETS_DEFAULT_TABLE_ID`)
  // and echoes that id back as `SessionResponse.table_id`. We deliberately do NOT
  // call `/api/live/tables` for it — the underlying live-bets `GET /tables` is
  // JWT-gated, but our route uses the operator key, which 401s. A session with no
  // configured table already 400'd above into the friendly empty state, so a
  // successful session always carries a usable `table_id` here.
  const { session_token, table_id } = sessionResult.value;

  return (
    <LiveShell>
      <BalanceHeader balance={balance} />
      {/* The widget interior is the live-bets widget's own (partially brandable)
          styling; the chrome above/around it is on-brand XPredict. */}
      <LiveTable
        sessionToken={session_token}
        tableId={table_id}
        initialBalance={balance}
      />
    </LiveShell>
  );
}

export default function LivePage() {
  return (
    <Suspense fallback={<LiveSkeleton />}>
      <LiveBody />
    </Suspense>
  );
}
