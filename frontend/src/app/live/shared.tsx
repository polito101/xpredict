/**
 * Shared internals for the /live route family (live multi-table plan).
 *
 * App Router page files must not export extra symbols, so everything reused by
 * BOTH `/live/page.tsx` and `/live/[slug]/page.tsx` lives here: the page shell,
 * skeleton, balance header, the server-side wallet-balance read, and the Plan D
 * fullscreen widget host. Bodies are verbatim moves from the pre-catalog
 * `page.tsx` — behavior-preserving by construction.
 *
 * Money is a STRING on the wire (SP-1) — never parsed to a float.
 */
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

import { LiveTable } from "./live-table";
import { LiveOrientationGate } from "./live-orientation-gate";

export const PAGE_SHELL = "w-full max-w-6xl mx-auto px-4 sm:px-6 py-12";
const CURRENCY = "PLAY_USD";

/**
 * Server-only backend base for the cookie-forwarded wallet-balance read (mirrors
 * `wallet/page.tsx:53-55`). No `NEXT_PUBLIC_` prefix, so the backend origin never
 * leaks into the client bundle.
 */
function getBackendUrl(): string {
  return process.env.BACKEND_URL || "http://localhost:8000";
}

export type BalanceResult = { ok: true; balance: string } | { ok: false };

/**
 * Read the player's wallet balance server-side, forwarding the session cookie —
 * REUSES the exact `/wallet/me/balance` mechanism from `wallet/page.tsx:62-90`
 * (`{ balance }`, a string). Returns a discriminated result so pages can keep
 * rendering chrome + a non-silent error rather than a misleading "0".
 */
export async function loadBalance(session: string): Promise<BalanceResult> {
  try {
    const res = await fetch(`${getBackendUrl()}/wallet/me/balance`, {
      headers: { Cookie: `xpredict_session=${session}` },
      cache: "no-store",
    });
    if (!res.ok) return { ok: false };
    const data = (await res.json()) as { balance?: unknown };
    // WR-02: a non-string balance (malformed/garbage body) is a FAILURE, not a
    // real "0" — never fabricate a zero balance.
    if (typeof data.balance !== "string") return { ok: false };
    return { ok: true, balance: data.balance };
  } catch {
    return { ok: false };
  }
}

/** The /live body — loading skeleton shape (header + balance card + widget). */
export function LiveSkeleton() {
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

/** Page chrome wrapper shared by the picker + empty + error states. */
export function LiveShell({ children }: { children: React.ReactNode }) {
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
export function BalanceHeader({ balance }: { balance: string }) {
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

/**
 * Plan D (spec §12) fullscreen widget host: a full-viewport black overlay — no
 * LiveShell chrome, no BalanceHeader (the widget HUD shows the balance via
 * HOST-01). It deliberately covers the SiteFrame nav: the widget HUD owns all
 * UI. The wrapper width is clamped to min(100vw, 100dvh·16/9) so the widget's
 * hard-16:9 shadow stage (HUD included) always fits the viewport (letterboxed
 * on black) at any aspect ratio. `counterLabel` names the HUD live counter
 * (catalog label, e.g. "Cars"/"Birds"); absent → the widget's COUNT default.
 */
export function LiveFullscreenHost({
  sessionToken,
  tableId,
  initialBalance,
  counterLabel,
}: {
  sessionToken: string;
  tableId: string;
  initialBalance: string;
  counterLabel?: string;
}) {
  return (
    <LiveOrientationGate>
      <main
        data-testid="live-fullscreen"
        className="fixed inset-0 z-50 flex items-center justify-center bg-black"
      >
        <div className="w-full max-w-[min(100vw,calc(100dvh*16/9))]">
          <LiveTable
            sessionToken={sessionToken}
            tableId={tableId}
            initialBalance={initialBalance}
            counterLabel={counterLabel}
          />
        </div>
      </main>
    </LiveOrientationGate>
  );
}
