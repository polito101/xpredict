/**
 * Plan 12-06 Task 1 (TDD — RED) — settlement dialog behavior contract.
 *
 * Written BEFORE the four dialogs exist. Pins the load-bearing behaviors from
 * the plan's <behavior>/<action> blocks against the EXACT 12-UI-SPEC copy:
 *
 *   1. resolve dialog — confirming with NO justification shows
 *      "A justification is required." and does NOT call resolveMarket; confirming
 *      with an outcome + justification calls resolveMarket(id, {winning_outcome_id,
 *      justification}) exactly once and toasts "Market resolved.".
 *   2. reverse dialog — the body carries the §Reverse copy guard ("does not
 *      re-open the market for a clean re-resolution") and an empty justification
 *      blocks the call.
 *   3. force-settle dialog — an empty justification blocks the call.
 *   4. close dialog — has NO reason/justification field and calls closeMarket(id)
 *      on confirm (no body).
 *
 * The `"use server"` settlement wrappers are mocked so NO network call occurs —
 * the backend is authoritative on validation (the client mirror is UX-only).
 */

import { describe, it, expect, vi, beforeEach, beforeAll } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// jsdom does not implement the pointer-capture / scrollIntoView APIs that
// @radix-ui/react-select calls when its trigger/content mount. Polyfill them
// HERE (scoped to this suite, not the global setup) so the YES/NO outcome
// Select can actually open under userEvent — otherwise the Radix primitive
// throws "hasPointerCapture is not a function" and the outcome assertions fail
// for the wrong reason.
beforeAll(() => {
  if (!Element.prototype.hasPointerCapture) {
    Element.prototype.hasPointerCapture = () => false;
  }
  if (!Element.prototype.setPointerCapture) {
    Element.prototype.setPointerCapture = () => {};
  }
  if (!Element.prototype.releasePointerCapture) {
    Element.prototype.releasePointerCapture = () => {};
  }
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => {};
  }
});

// Mock the use-server settlement/close wrappers so the dialogs never hit the network.
const resolveMarket = vi.fn();
const reverseSettlement = vi.fn();
const forceSettle = vi.fn();
const closeMarket = vi.fn();
vi.mock("@/lib/admin-markets-api", () => ({
  resolveMarket: (id: string, body: unknown) => resolveMarket(id, body),
  reverseSettlement: (id: string, body: unknown) => reverseSettlement(id, body),
  forceSettle: (id: string, body: unknown) => forceSettle(id, body),
  closeMarket: (id: string) => closeMarket(id),
}));

// Mock sonner so success/failure toasts are deterministically assertable.
const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock("sonner", () => ({
  toast: {
    success: (msg: string) => toastSuccess(msg),
    error: (msg: string) => toastError(msg),
  },
}));

import { ResolveMarketDialog } from "@/components/admin/resolve-market-dialog";
import { ReverseSettlementDialog } from "@/components/admin/reverse-settlement-dialog";
import { ForceSettleDialog } from "@/components/admin/force-settle-dialog";
import { CloseMarketDialog } from "@/components/admin/close-market-dialog";
import type { OutcomeRead } from "@/lib/admin-markets-types";

const OUTCOMES: OutcomeRead[] = [
  { id: "o-yes", label: "YES", initial_odds: "0.5", current_odds: "0.5" },
  { id: "o-no", label: "NO", initial_odds: "0.5", current_odds: "0.5" },
];

const noop = () => {};

describe("settlement dialogs", () => {
  beforeEach(() => {
    resolveMarket.mockReset();
    reverseSettlement.mockReset();
    forceSettle.mockReset();
    closeMarket.mockReset();
    toastSuccess.mockReset();
    toastError.mockReset();
  });

  describe("<ResolveMarketDialog />", () => {
    it("blocks confirm with an empty justification and does NOT call resolveMarket", async () => {
      const user = userEvent.setup();
      render(
        <ResolveMarketDialog
          open
          onOpenChange={noop}
          marketId="m-1"
          outcomes={OUTCOMES}
          onResolved={noop}
        />,
      );

      // Pick an outcome so the only blocker is the missing justification.
      await user.click(screen.getByLabelText("Winning outcome"));
      await user.click(await screen.findByRole("option", { name: "YES" }));

      await user.click(screen.getByRole("button", { name: "Confirm resolve" }));

      expect(
        await screen.findByText("A justification is required."),
      ).toBeInTheDocument();
      expect(resolveMarket).not.toHaveBeenCalled();
    });

    it("calls resolveMarket(id, {winning_outcome_id, justification}) once and toasts on success", async () => {
      const user = userEvent.setup();
      resolveMarket.mockResolvedValue({});
      const onResolved = vi.fn();
      render(
        <ResolveMarketDialog
          open
          onOpenChange={noop}
          marketId="m-1"
          outcomes={OUTCOMES}
          onResolved={onResolved}
        />,
      );

      await user.click(screen.getByLabelText("Winning outcome"));
      await user.click(await screen.findByRole("option", { name: "YES" }));
      await user.type(
        screen.getByLabelText("Justification (required)"),
        "Resolved YES per official source.",
      );
      await user.click(screen.getByRole("button", { name: "Confirm resolve" }));

      expect(resolveMarket).toHaveBeenCalledTimes(1);
      expect(resolveMarket).toHaveBeenCalledWith("m-1", {
        winning_outcome_id: "o-yes",
        justification: "Resolved YES per official source.",
      });
      expect(toastSuccess).toHaveBeenCalledWith("Market resolved.");
      expect(onResolved).toHaveBeenCalledTimes(1);
    });

    it("blocks confirm when no outcome is selected", async () => {
      const user = userEvent.setup();
      render(
        <ResolveMarketDialog
          open
          onOpenChange={noop}
          marketId="m-1"
          outcomes={OUTCOMES}
          onResolved={noop}
        />,
      );

      await user.type(
        screen.getByLabelText("Justification (required)"),
        "A justification.",
      );
      await user.click(screen.getByRole("button", { name: "Confirm resolve" }));

      expect(
        await screen.findByText("Select the winning outcome."),
      ).toBeInTheDocument();
      expect(resolveMarket).not.toHaveBeenCalled();
    });
  });

  describe("<ReverseSettlementDialog />", () => {
    it("renders the reverse copy guard (no re-resolution promise)", () => {
      render(
        <ReverseSettlementDialog
          open
          onOpenChange={noop}
          marketId="m-1"
          onReversed={noop}
        />,
      );

      expect(
        screen.getByText(
          /does not re-open the market for a clean re-resolution/i,
        ),
      ).toBeInTheDocument();
    });

    it("blocks confirm with an empty justification and does NOT call reverseSettlement", async () => {
      const user = userEvent.setup();
      render(
        <ReverseSettlementDialog
          open
          onOpenChange={noop}
          marketId="m-1"
          onReversed={noop}
        />,
      );

      await user.click(screen.getByRole("button", { name: "Confirm reversal" }));

      expect(
        await screen.findByText("A justification is required."),
      ).toBeInTheDocument();
      expect(reverseSettlement).not.toHaveBeenCalled();
    });

    it("has NO outcome Select", () => {
      render(
        <ReverseSettlementDialog
          open
          onOpenChange={noop}
          marketId="m-1"
          onReversed={noop}
        />,
      );
      expect(screen.queryByLabelText("Winning outcome")).not.toBeInTheDocument();
    });

    it("calls reverseSettlement(id, {justification}) once and toasts on success", async () => {
      const user = userEvent.setup();
      reverseSettlement.mockResolvedValue({});
      render(
        <ReverseSettlementDialog
          open
          onOpenChange={noop}
          marketId="m-1"
          onReversed={noop}
        />,
      );

      await user.type(
        screen.getByLabelText("Justification (required)"),
        "Reversing — wrong outcome.",
      );
      await user.click(screen.getByRole("button", { name: "Confirm reversal" }));

      expect(reverseSettlement).toHaveBeenCalledTimes(1);
      expect(reverseSettlement).toHaveBeenCalledWith("m-1", {
        justification: "Reversing — wrong outcome.",
      });
      expect(toastSuccess).toHaveBeenCalledWith("Settlement reversed.");
    });
  });

  describe("<ForceSettleDialog />", () => {
    it("blocks confirm with an empty justification and does NOT call forceSettle", async () => {
      const user = userEvent.setup();
      render(
        <ForceSettleDialog
          open
          onOpenChange={noop}
          marketId="m-1"
          outcomes={OUTCOMES}
          onForceSettled={noop}
        />,
      );

      await user.click(screen.getByLabelText("Winning outcome"));
      await user.click(await screen.findByRole("option", { name: "NO" }));

      await user.click(
        screen.getByRole("button", { name: "Confirm force-settle" }),
      );

      expect(
        await screen.findByText("A justification is required."),
      ).toBeInTheDocument();
      expect(forceSettle).not.toHaveBeenCalled();
    });

    it("calls forceSettle(id, {winning_outcome_id, justification}) once and toasts on success", async () => {
      const user = userEvent.setup();
      forceSettle.mockResolvedValue({});
      render(
        <ForceSettleDialog
          open
          onOpenChange={noop}
          marketId="m-1"
          outcomes={OUTCOMES}
          onForceSettled={noop}
        />,
      );

      await user.click(screen.getByLabelText("Winning outcome"));
      await user.click(await screen.findByRole("option", { name: "NO" }));
      await user.type(
        screen.getByLabelText("Justification (required)"),
        "Polymarket stuck; settling NO.",
      );
      await user.click(
        screen.getByRole("button", { name: "Confirm force-settle" }),
      );

      expect(forceSettle).toHaveBeenCalledTimes(1);
      expect(forceSettle).toHaveBeenCalledWith("m-1", {
        winning_outcome_id: "o-no",
        justification: "Polymarket stuck; settling NO.",
      });
      expect(toastSuccess).toHaveBeenCalledWith("Market force-settled.");
    });
  });

  describe("<CloseMarketDialog />", () => {
    it("has NO reason/justification field", () => {
      render(
        <CloseMarketDialog
          open
          onOpenChange={noop}
          marketId="m-1"
          onClosed={noop}
        />,
      );
      expect(
        screen.queryByLabelText("Justification (required)"),
      ).not.toBeInTheDocument();
      // The consequence copy is present instead.
      expect(
        screen.getByText(/stops the market from accepting new bets/i),
      ).toBeInTheDocument();
    });

    it("calls closeMarket(id) on confirm and toasts on success", async () => {
      const user = userEvent.setup();
      closeMarket.mockResolvedValue({});
      const onClosed = vi.fn();
      render(
        <CloseMarketDialog
          open
          onOpenChange={noop}
          marketId="m-1"
          onClosed={onClosed}
        />,
      );

      // The footer "Close market" button (the dialog title is also "Close market").
      const footer = screen.getByRole("button", { name: "Close market" });
      await user.click(footer);

      expect(closeMarket).toHaveBeenCalledTimes(1);
      expect(closeMarket).toHaveBeenCalledWith("m-1");
      expect(toastSuccess).toHaveBeenCalledWith(
        "Market closed. It's no longer accepting bets.",
      );
      expect(onClosed).toHaveBeenCalledTimes(1);
    });
  });

  it("maps a 401/403 from the wrapper to the session-expired toast", async () => {
    const user = userEvent.setup();
    resolveMarket.mockRejectedValue(new Error("API error: 401"));
    render(
      <ResolveMarketDialog
        open
        onOpenChange={noop}
        marketId="m-1"
        outcomes={OUTCOMES}
        onResolved={noop}
      />,
    );

    await user.click(screen.getByLabelText("Winning outcome"));
    await user.click(await screen.findByRole("option", { name: "YES" }));
    await user.type(
      screen.getByLabelText("Justification (required)"),
      "Resolving.",
    );
    await user.click(screen.getByRole("button", { name: "Confirm resolve" }));

    // The within() import is kept available for future row-scoped assertions.
    void within;
    expect(toastError).toHaveBeenCalledWith(
      "Your session expired. Please sign in again.",
    );
  });
});
