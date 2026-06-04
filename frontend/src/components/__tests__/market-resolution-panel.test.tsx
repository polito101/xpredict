/**
 * Plan 12-04 Task 2 (TDD RED) — MarketResolutionPanel behavior contract (STL-06).
 *
 * Written BEFORE the component exists. Pins the <behavior> block + UI-SPEC
 * §Surface 1 for the four player states the RESOLVED detail page must render:
 *
 *   1. Public facts: winning outcome, the source line derived from the
 *      `resolution_source` TOKEN ("Polymarket UMA" for POLYMARKET_UMA / "Operator"
 *      for HOUSE), the formatted settled date, and the justification rendered as
 *      ESCAPED React text (a `<b>` in the justification renders the literal
 *      characters — NO HTML injection; T-12-12).
 *   2. WON   → "Won" + the emerald (positive) P&L treatment.
 *   3. LOST  → "Lost" + the NEUTRAL zinc-700 P&L treatment (A-LOSS-NEUTRAL —
 *      never red; red is reserved for errors/destructive).
 *   4. logged-in + no bet → "You didn't bet on this market."
 *   5. logged-out → the personal-result section is omitted entirely (only the
 *      public facts show).
 *
 * The own result is the player's own `SettledPosition` (read upstream from the
 * cookie-gated /bets/me/portfolio); this component only renders it.
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import {
  MarketResolutionPanel,
  type ResolutionResult,
} from "../market-resolution-panel";

const WON: ResolutionResult = {
  bet_id: "b-won",
  market_id: "m-1",
  outcome_id: "o-yes",
  stake: "100.0000",
  odds_at_placement: "0.5000",
  won: true,
  payout: "200.0000",
  realized_pnl: "100.0000",
};

const LOST: ResolutionResult = {
  bet_id: "b-lost",
  market_id: "m-1",
  outcome_id: "o-no",
  stake: "100.0000",
  odds_at_placement: "0.5000",
  won: false,
  payout: "0.0000",
  realized_pnl: "-100.0000",
};

function renderPanel(
  props?: Partial<Parameters<typeof MarketResolutionPanel>[0]>,
) {
  return render(
    <MarketResolutionPanel
      winningOutcomeLabel="YES"
      resolutionSource="HOUSE"
      justification="The official result was YES."
      resolvedAt="2026-05-25T12:00:00Z"
      sourceUrl={null}
      source="HOUSE"
      myResult={null}
      isAuthenticated={false}
      {...props}
    />,
  );
}

describe("MarketResolutionPanel — public facts", () => {
  it("renders the Resolution title and the winning outcome label", () => {
    renderPanel();
    expect(screen.getByText("Resolution")).toBeInTheDocument();
    // The winning label appears in the outcome row.
    expect(screen.getByText("YES")).toBeInTheDocument();
  });

  it("renders the HOUSE source line as 'Operator'", () => {
    renderPanel({ resolutionSource: "HOUSE", source: "HOUSE" });
    expect(screen.getByText(/Resolved by Operator/i)).toBeInTheDocument();
  });

  it("renders the POLYMARKET_UMA source line as 'Polymarket UMA' with the source link", () => {
    renderPanel({
      resolutionSource: "POLYMARKET_UMA",
      source: "POLYMARKET",
      sourceUrl: "https://polymarket.com/event/x",
    });
    expect(screen.getByText(/Resolved by Polymarket UMA/i)).toBeInTheDocument();
    // SourceBadge renders the Polymarket source link (opens in new tab).
    expect(
      screen.getByRole("link", { name: /Polymarket/i }),
    ).toHaveAttribute("href", "https://polymarket.com/event/x");
  });

  it("renders the formatted settled date prefixed 'Settled'", () => {
    renderPanel({ resolvedAt: "2026-05-25T12:00:00Z" });
    expect(screen.getByText(/Settled May 25, 2026/)).toBeInTheDocument();
  });

  it("renders the justification as ESCAPED text (no HTML injection)", () => {
    renderPanel({ justification: "Result was <b>YES</b> per source." });
    // The literal characters render as text — never as a <b> element.
    expect(
      screen.getByText("Result was <b>YES</b> per source."),
    ).toBeInTheDocument();
    // Defense-in-depth: no <b> element was injected from the justification.
    expect(document.querySelector("b")).toBeNull();
  });

  it("shows the 'Why this resolved' heading", () => {
    renderPanel();
    expect(screen.getByText("Why this resolved")).toBeInTheDocument();
  });
});

describe("MarketResolutionPanel — personal result", () => {
  it("WON: shows 'Won' + payout and the emerald (positive) P&L", () => {
    renderPanel({ isAuthenticated: true, myResult: WON });
    expect(screen.getByText(/Won — payout 200/)).toBeInTheDocument();
    // The realized P&L renders positive (emerald), prefixed with "+".
    const pnl = screen.getByText(/\+100\.0000 PLAY_USD/);
    expect(pnl).toBeInTheDocument();
    expect(pnl).toHaveClass("text-emerald-600");
  });

  it("LOST: shows 'Lost' + payout and the NEUTRAL zinc-700 P&L (never red)", () => {
    renderPanel({ isAuthenticated: true, myResult: LOST });
    expect(screen.getByText(/Lost — payout 0/)).toBeInTheDocument();
    const pnl = screen.getByText(/-100\.0000 PLAY_USD/);
    expect(pnl).toBeInTheDocument();
    // A-LOSS-NEUTRAL: loss is neutral zinc-700, NOT red.
    expect(pnl).toHaveClass("text-zinc-700");
    expect(pnl.className).not.toMatch(/text-red/);
  });

  it("logged-in + no bet: shows the no-bet copy", () => {
    renderPanel({ isAuthenticated: true, myResult: null });
    expect(
      screen.getByText("You didn't bet on this market."),
    ).toBeInTheDocument();
  });

  it("logged-out: omits the personal-result section entirely", () => {
    renderPanel({ isAuthenticated: false, myResult: null });
    // No personal-result copy in either direction.
    expect(
      screen.queryByText("You didn't bet on this market."),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/payout/i)).not.toBeInTheDocument();
    // The public facts still render.
    expect(screen.getByText("Resolution")).toBeInTheDocument();
  });
});
