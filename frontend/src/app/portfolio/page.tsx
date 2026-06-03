/**
 * Phase 5 (SC#7) — Player portfolio page.
 *
 * A Server Component that shows the logged-in player their OPEN positions
 * (stake, locked odds, potential payout / P&L) and SETTLED positions (stake,
 * won/lost, payout, realized P&L).
 *
 * Money + odds are rendered exactly as the backend serialized them — STRINGS
 * (SC#4); never parsed to a JS number (floats would lose NUMERIC precision,
 * PITFALLS #4). Copy avoids "deposit"/casino framing (PITFALLS #3 — play money).
 *
 * Failure handling (v1.1 Fase C): the fetch result is a discriminated union, so
 * a backend failure shows a non-silent RetryError and a signed-out visitor sees
 * a sign-in prompt — neither is degraded to a misleading "empty portfolio".
 */
import { cookies } from "next/headers";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { RetryError } from "@/components/retry-error";
import { SignedOutNotice } from "@/components/signed-out-notice";

const CURRENCY = "PLAY_USD";

type OpenPosition = {
  bet_id: string;
  market_id: string;
  outcome_id: string;
  stake: string; // SC#4 — money is a JSON string.
  odds_at_placement: string;
  potential_payout: string;
  potential_pnl: string;
};

type SettledPosition = {
  bet_id: string;
  market_id: string;
  outcome_id: string;
  stake: string;
  odds_at_placement: string;
  won: boolean;
  payout: string;
  realized_pnl: string;
};

type Portfolio = { open: OpenPosition[]; settled: SettledPosition[] };

type PortfolioResult =
  | { status: "ok"; data: Portfolio }
  | { status: "error" }
  | { status: "unauthenticated" };

function getBackendUrl(): string {
  return process.env.BACKEND_URL || "http://localhost:8000";
}

/**
 * Fetch the player's portfolio server-side, forwarding the session cookie.
 * Returns a discriminated result so the page can tell apart a signed-out
 * visitor, a backend failure, and a genuinely empty portfolio.
 */
async function loadPortfolio(): Promise<PortfolioResult> {
  const store = await cookies();
  const session = store.get("xpredict_session")?.value;
  if (!session) return { status: "unauthenticated" };

  try {
    const res = await fetch(`${getBackendUrl()}/bets/me/portfolio`, {
      headers: { Cookie: `xpredict_session=${session}` },
      cache: "no-store",
    });
    if (!res.ok) return { status: "error" };

    const data = (await res.json()) as {
      open?: OpenPosition[];
      settled?: SettledPosition[];
    };
    return {
      status: "ok",
      data: { open: data.open ?? [], settled: data.settled ?? [] },
    };
  } catch {
    return { status: "error" };
  }
}

/** Render a signed P&L string (the backend already prefixes "-" for a loss). */
function PnL({ value }: { value: string }) {
  const negative = value.trim().startsWith("-");
  return (
    <span
      className={
        negative
          ? "text-sm font-medium text-zinc-700 dark:text-zinc-300"
          : "text-sm font-medium text-emerald-600"
      }
    >
      {negative ? "" : "+"}
      {value} {CURRENCY}
    </span>
  );
}

export default async function PortfolioPage() {
  const result = await loadPortfolio();

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-col gap-6 px-4 py-12 sm:px-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-3xl font-semibold tracking-tight">Portfolio</h1>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Your open positions and settled results.
        </p>
      </header>

      {result.status === "unauthenticated" ? (
        <SignedOutNotice resource="portfolio" />
      ) : result.status === "error" ? (
        <RetryError
          title="We couldn't load your portfolio"
          message="The positions service didn't respond. Please try again."
        />
      ) : (
        <PortfolioContent {...result.data} />
      )}
    </main>
  );
}

function PortfolioContent({ open, settled }: Portfolio) {
  return (
    <>
      {/* Open positions — potential payout / P&L at the odds locked when you bet. */}
      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-medium tracking-tight">Open positions</h2>
        {open.length === 0 ? (
          <p className="text-sm text-zinc-500" data-testid="portfolio-open-empty">
            No open positions yet.
          </p>
        ) : (
          <ul className="flex flex-col gap-3">
            {open.map((p) => (
              <li key={p.bet_id}>
                <Card>
                  <CardHeader>
                    <CardDescription>
                      Stake {p.stake} {CURRENCY} @ {p.odds_at_placement}
                    </CardDescription>
                    <CardTitle className="text-base font-medium">
                      Potential payout {p.potential_payout} {CURRENCY}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                    <span className="min-w-0 text-sm text-zinc-500">If this outcome wins</span>
                    <PnL value={p.potential_pnl} />
                  </CardContent>
                </Card>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Settled positions — realized P&L (exactly what settlement posted). */}
      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-medium tracking-tight">Settled positions</h2>
        {settled.length === 0 ? (
          <p className="text-sm text-zinc-500" data-testid="portfolio-settled-empty">
            No settled positions yet.
          </p>
        ) : (
          <ul className="flex flex-col gap-3">
            {settled.map((p) => (
              <li key={p.bet_id}>
                <Card>
                  <CardHeader>
                    <CardDescription>
                      Stake {p.stake} {CURRENCY} @ {p.odds_at_placement}
                    </CardDescription>
                    <CardTitle className="text-base font-medium">
                      {p.won ? "Won" : "Lost"} — payout {p.payout} {CURRENCY}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                    <span className="min-w-0 text-sm text-zinc-500">Realized P&amp;L</span>
                    <PnL value={p.realized_pnl} />
                  </CardContent>
                </Card>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
