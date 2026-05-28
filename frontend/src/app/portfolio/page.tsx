/**
 * Phase 5 (SC#7) — Player portfolio page.
 *
 * A Server Component that shows the logged-in player:
 *   - OPEN positions: stake, the odds locked at placement, and the POTENTIAL payout / P&L
 *     if that outcome wins (at the locked odds), and
 *   - SETTLED positions: stake, the won/lost result, the payout, and the REALIZED P&L.
 *
 * Money + odds are rendered exactly as the backend serialized them — STRINGS (SC#4); we
 * never parse them to a JS number (floats would lose the NUMERIC precision, PITFALLS #4).
 * Copy is ENGLISH and avoids "deposit"/casino framing (PITFALLS #3 — this is play money).
 *
 * Data fetch mirrors the wallet page: read `BACKEND_URL` server-side (no `NEXT_PUBLIC_`
 * prefix, so it never leaks into the client bundle) and forward the player's
 * `xpredict_session` cookie to `GET /bets/me/portfolio`. On any failure it degrades to an
 * empty portfolio rather than crashing. The live unrealized P&L at CURRENT odds (SC#7)
 * arrives once the backend enriches open positions at integration (the market read port is
 * wired then); today the OPEN view is the locked-odds potential. `loadPortfolio()` is
 * isolated so tests can mock it.
 */
import { cookies } from "next/headers";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

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

function getBackendUrl(): string {
  return process.env.BACKEND_URL || "http://localhost:8000";
}

/**
 * Fetch the player's portfolio server-side, forwarding the session cookie. Degrades to an
 * empty portfolio on any failure so the page always renders (the read is cookie-gated
 * server-side).
 */
async function loadPortfolio(): Promise<Portfolio> {
  const fallback: Portfolio = { open: [], settled: [] };
  try {
    const store = await cookies();
    const session = store.get("xpredict_session")?.value;
    if (!session) return fallback;

    const res = await fetch(`${getBackendUrl()}/bets/me/portfolio`, {
      headers: { Cookie: `xpredict_session=${session}` },
      cache: "no-store",
    });
    if (!res.ok) return fallback;

    const data = await res.json();
    return { open: data.open ?? [], settled: data.settled ?? [] };
  } catch {
    return fallback;
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
  const { open, settled } = await loadPortfolio();

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-col gap-6 px-6 py-12">
      <header className="flex flex-col gap-1">
        <h1 className="text-3xl font-semibold tracking-tight">Portfolio</h1>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Your open positions and settled results.
        </p>
      </header>

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
                  <CardContent className="flex items-center justify-between">
                    <span className="text-sm text-zinc-500">If this outcome wins</span>
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
                  <CardContent className="flex items-center justify-between">
                    <span className="text-sm text-zinc-500">Realized P&amp;L</span>
                    <PnL value={p.realized_pnl} />
                  </CardContent>
                </Card>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
