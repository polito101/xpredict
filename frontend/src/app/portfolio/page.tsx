/**
 * Player portfolio page (SC#7) — restyled to the premium dark system (Phase 19).
 *
 * A Server Component (behind auth — the edge middleware gates `/portfolio`) that
 * shows the logged-in player a performance summary plus their OPEN positions
 * (stake, locked odds, potential payout / P&L) and SETTLED positions (stake,
 * won/lost, payout, realized P&L).
 *
 * Money + odds are rendered exactly as the backend serialized them — STRINGS
 * (SC#4). The summary aggregates use `parseFloat` for DISPLAY ONLY (like
 * `formatVolume`); per-position values are never parsed for storage (PITFALLS #4).
 * Copy avoids "deposit"/casino framing (PITFALLS #3 — play money).
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
import { ClosePositionButton } from "@/components/close-position-button";
import { RetryError } from "@/components/retry-error";
import { SignedOutNotice } from "@/components/signed-out-notice";
import { cn } from "@/lib/utils";

const CURRENCY = "PLAY_USD";

type OpenPosition = {
  bet_id: string;
  market_id: string;
  outcome_id: string;
  stake: string; // SC#4 — money is a JSON string.
  odds_at_placement: string;
  potential_payout: string;
  potential_pnl: string;
  current_value: string;
  unrealized_pnl: string;
  priced: boolean;
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
  status: string;
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

/** DISPLAY-only sum of money strings → fixed 2dp (never feeds storage math). */
function sumMoney(values: string[]): number {
  return values.reduce((s, v) => s + (Number.parseFloat(v) || 0), 0);
}

/** Render a signed P&L string (the backend already prefixes "-" for a loss). */
function PnL({ value, className }: { value: string; className?: string }) {
  const negative = value.trim().startsWith("-");
  return (
    <span
      className={cn(
        "font-medium tabular-nums",
        negative ? "text-rose-400" : "text-emerald-400",
        className,
      )}
    >
      {negative ? "" : "+"}
      {value} {CURRENCY}
    </span>
  );
}

export default async function PortfolioPage() {
  const result = await loadPortfolio();

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-4 py-10 sm:px-6">
      <header className="flex flex-col gap-1">
        <h1 className="font-display text-3xl font-semibold tracking-tight">
          Portfolio
        </h1>
        <p className="text-sm text-muted-foreground">
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

/** A single summary stat tile. */
function StatTile({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1 bg-card px-5 py-4">
      <span className="font-display text-2xl font-semibold tabular-nums">
        {children}
      </span>
      <span className="text-xs font-medium uppercase tracking-wide text-subtle-foreground">
        {label}
      </span>
    </div>
  );
}

function PortfolioContent({ open, settled }: Portfolio) {
  const hasAny = open.length + settled.length > 0;

  // DISPLAY-only aggregates.
  const openPnl = sumMoney(open.map((p) => p.unrealized_pnl));
  const realizedPnl = sumMoney(settled.map((p) => p.realized_pnl));
  const totalStaked = sumMoney([
    ...open.map((p) => p.stake),
    ...settled.map((p) => p.stake),
  ]);
  const wins = settled.filter((p) => p.won).length;
  const winRate = settled.length > 0 ? Math.round((wins / settled.length) * 100) : null;

  const signed = (n: number) => `${n >= 0 ? "+" : ""}${n.toFixed(2)}`;
  const signClass = (n: number) =>
    n >= 0 ? "text-emerald-400" : "text-rose-400";

  return (
    <>
      {/* Summary — instant "how am I doing". */}
      {hasAny && (
        <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-border bg-border sm:grid-cols-4">
          <StatTile label="Open P&L">
            <span className={signClass(openPnl)}>{signed(openPnl)}</span>
          </StatTile>
          <StatTile label="Realized P&L">
            <span className={signClass(realizedPnl)}>{signed(realizedPnl)}</span>
          </StatTile>
          <StatTile label="Total staked">{totalStaked.toFixed(2)}</StatTile>
          <StatTile label="Win rate">
            {winRate === null ? "—" : `${winRate}%`}
          </StatTile>
        </dl>
      )}

      {/* Open positions — potential payout / P&L at the odds locked when you bet. */}
      <section className="flex flex-col gap-3">
        <div className="flex items-baseline justify-between">
          <h2 className="text-lg font-semibold tracking-tight">Open positions</h2>
          {open.length > 0 && (
            <span className="text-sm text-muted-foreground">{open.length}</span>
          )}
        </div>
        {open.length === 0 ? (
          <p
            className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground"
            data-testid="portfolio-open-empty"
          >
            No open positions yet.
          </p>
        ) : (
          <ul className="flex flex-col gap-3">
            {open.map((p) => (
              <li key={p.bet_id}>
                <Card className="transition-colors hover:border-border-strong">
                  <CardHeader>
                    <CardDescription>
                      Stake {p.stake} {CURRENCY} @ {p.odds_at_placement}
                    </CardDescription>
                    <CardTitle className="text-base font-medium">
                      Potential payout {p.potential_payout} {CURRENCY}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-2">
                    <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                      <span className="min-w-0 text-sm text-muted-foreground">
                        Current value{p.priced ? "" : " (live price unavailable)"}
                      </span>
                      <span className="text-sm font-medium tabular-nums">
                        {p.current_value} {CURRENCY}
                      </span>
                    </div>
                    <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                      <span className="min-w-0 text-sm text-muted-foreground">Open P&amp;L</span>
                      <PnL value={p.unrealized_pnl} className="text-sm" />
                    </div>
                    <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                      <span className="min-w-0 text-sm text-muted-foreground">
                        If this outcome wins
                      </span>
                      <PnL value={p.potential_pnl} className="text-sm" />
                    </div>
                    <ClosePositionButton betId={p.bet_id} cashout={p.current_value} />
                  </CardContent>
                </Card>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Settled positions — realized P&L (exactly what settlement posted). */}
      <section className="flex flex-col gap-3">
        <div className="flex items-baseline justify-between">
          <h2 className="text-lg font-semibold tracking-tight">
            Settled positions
          </h2>
          {settled.length > 0 && (
            <span className="text-sm text-muted-foreground">
              {settled.length}
            </span>
          )}
        </div>
        {settled.length === 0 ? (
          <p
            className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground"
            data-testid="portfolio-settled-empty"
          >
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
                    <CardTitle className="flex flex-wrap items-center gap-2 text-base font-medium">
                      <span
                        className={cn(
                          "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold",
                          p.won
                            ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-400"
                            : "border-border bg-muted text-muted-foreground",
                        )}
                      >
                        {p.won ? "Won" : "Lost"}
                      </span>
                      <span>
                        — payout {p.payout} {CURRENCY}
                      </span>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                    <span className="min-w-0 text-sm text-muted-foreground">
                      Realized P&amp;L
                    </span>
                    <PnL value={p.realized_pnl} className="text-sm" />
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
