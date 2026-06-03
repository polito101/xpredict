/**
 * Plan 12-04 — Player resolution display (STL-06).
 *
 * Renders the RESOLVED block in the player detail page's RIGHT column, in place
 * of the order-entry panel. It COMPOSES three shipped pieces (no single-file
 * clone): the order-panel `Card` shell (`markets/[slug]/page.tsx:193-205`), the
 * portfolio sign-coloring `PnL` span (`portfolio/page.tsx:86-100`, loss → neutral
 * zinc-700, NOT red — A-LOSS-NEUTRAL), and the won/lost settled-card copy
 * (`portfolio/page.tsx:155-170`). The Polymarket source link reuses `SourceBadge`.
 *
 * Public facts (winning outcome, source attribution, settled date, justification)
 * always render. The personal result renders only for a logged-in player: their
 * own Won/Lost + payout + realized P&L when they bet, the no-bet copy when they
 * didn't, and nothing at all when logged out (UI-SPEC §Surface 1).
 *
 * SECURITY (T-12-12): the operator-authored `justification` is rendered as
 * ESCAPED React text (`{justification}`) — NEVER `dangerouslySetInnerHTML`; a
 * `<b>` in the text renders the literal characters (asserted in the panel test).
 *
 * Money is a STRING end-to-end (SP-1): the P&L sign/colour is derived from the
 * leading "-" character, never `parseFloat`.
 *
 * Resolution-source copy (RESEARCH A2 / UI-SPEC Open Q3): 12-01 stores the TOKEN
 * only (no admin display-name snapshot on the public read), so HOUSE renders
 * "Resolved by Operator" WITHOUT a name. The copy is written defensively: if a
 * future backend supplies a resolver display name (`operatorName`), it renders
 * "Resolved by Operator: {name}". Flagged in the 12-04 SUMMARY for Pol.
 */
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { SourceBadge } from "@/components/source-badge";
import { formatDate } from "@/lib/admin-format";
import { cn } from "@/lib/utils";

const CURRENCY = "PLAY_USD";

/**
 * The player's own settled result for this market — the `SettledPosition` shape
 * from `/bets/me/portfolio` (`portfolio/page.tsx:43-52`). Read upstream
 * (cookie-gated, self-scoped); this component only renders it.
 */
export interface ResolutionResult {
  bet_id: string;
  market_id: string;
  outcome_id: string;
  stake: string;
  odds_at_placement: string;
  won: boolean;
  payout: string;
  realized_pnl: string;
}

export interface MarketResolutionPanelProps {
  /** The winning outcome's label (e.g. "YES"); `null` if not resolvable. */
  winningOutcomeLabel: string | null;
  /** The `resolution_source` token: "HOUSE" | "POLYMARKET_UMA" (or null). */
  resolutionSource: string | null;
  /** Operator-authored public justification (rendered as escaped text). */
  justification: string | null;
  /** ISO settlement timestamp (`resolved_at`). */
  resolvedAt: string | null;
  /** The market's source_url — passed to `SourceBadge` for the Polymarket link. */
  sourceUrl?: string | null;
  /** The market source token ("HOUSE" | "POLYMARKET") for `SourceBadge`. */
  source: string;
  /** The player's own settled result, or `null` if they didn't bet. */
  myResult: ResolutionResult | null;
  /** Whether a player session is present (drives the personal-result section). */
  isAuthenticated: boolean;
  /**
   * Defensive (UI-SPEC Open Q3): a resolver display name if the backend ever
   * supplies one. Until then it is undefined and HOUSE shows a bare "Operator".
   */
  operatorName?: string | null;
}

/**
 * Signed P&L span — cloned from `portfolio/page.tsx:86-100`. A loss (leading
 * "-") renders NEUTRAL zinc-700 (A-LOSS-NEUTRAL), never red; a gain renders
 * emerald with a "+" prefix. Sign is read from the string (SP-1).
 */
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

/** Token → human label for the resolution-source line (defensive fallback). */
function sourceLine(
  resolutionSource: string | null,
  operatorName?: string | null,
): string {
  if (resolutionSource === "POLYMARKET_UMA") {
    return "Resolved by Polymarket UMA";
  }
  // HOUSE (and any other token) → Operator. A name is appended only if supplied.
  if (operatorName) {
    return `Resolved by Operator: ${operatorName}`;
  }
  return "Resolved by Operator";
}

export function MarketResolutionPanel({
  winningOutcomeLabel,
  resolutionSource,
  justification,
  resolvedAt,
  sourceUrl,
  source,
  myResult,
  isAuthenticated,
  operatorName,
}: MarketResolutionPanelProps) {
  const won = myResult?.won === true;
  const showPersonal = isAuthenticated;

  return (
    <Card className="lg:sticky lg:top-8">
      <CardHeader>
        <CardTitle className="text-lg font-semibold">Resolution</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {/* Winning outcome — emerald chip if the player won, else neutral. */}
        <div className="flex flex-wrap items-center gap-2 text-base font-medium">
          <span className="text-zinc-600 dark:text-zinc-400">Resolved:</span>
          <span
            className={cn(
              "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold",
              won
                ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
                : "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
            )}
          >
            {winningOutcomeLabel ?? "—"}
          </span>
        </div>

        {/* Resolution source attribution — token-derived (+ link for Polymarket). */}
        <div className="flex flex-wrap items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400">
          <span>{sourceLine(resolutionSource, operatorName)}</span>
          {resolutionSource === "POLYMARKET_UMA" && (
            <SourceBadge source={source} sourceUrl={sourceUrl} />
          )}
        </div>

        {/* Settlement timestamp. */}
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          Settled {formatDate(resolvedAt)}
        </p>

        {/* Public justification — ESCAPED React text (NEVER dangerouslySetInnerHTML). */}
        <div className="flex flex-col gap-1">
          <h3 className="text-sm font-medium">Why this resolved</h3>
          <p className="text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
            {justification}
          </p>
        </div>

        {/* Personal result — only for a logged-in player (omitted when logged out). */}
        {showPersonal && (
          <>
            <Separator />
            {myResult ? (
              <div className="flex flex-col gap-2">
                <p className="text-base font-medium">
                  {won ? "Won" : "Lost"} — payout {myResult.payout} {CURRENCY}
                </p>
                <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                  <span className="min-w-0 text-sm text-zinc-500">
                    Realized P&amp;L
                  </span>
                  <PnL value={myResult.realized_pnl} />
                </div>
              </div>
            ) : (
              <p className="text-sm text-zinc-500">
                You didn&apos;t bet on this market.
              </p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
