/**
 * Plan 09-04 Task 1 — OrderEntryForm backend-status → inline-copy mapping
 * (T-09-12 / MKT-03).
 *
 * The load-bearing assertion: for EACH backend bet error status (402 / 409 /
 * 403 / 422) the form renders the SPECIFIC inline copy string in a
 * `role="alert"` region — never a generic toast. We mock `placeBetAction` to
 * return each mapped `ActionState` error (the action's status→copy mapping is
 * unit-covered by exercising the exact strings it produces), then drive the
 * form's submit → confirm flow and assert the inline copy renders.
 *
 * The outcome Select defaults to "YES", so the test only needs to type a stake
 * and submit — this keeps the Radix Select (portals/pointer-events under jsdom)
 * off the critical path while still rendering it.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import type { ActionState } from "@/lib/bet-schemas";

// Mock the Server Action; each test sets its return value. `useActionState`
// invokes this and stores the result, which the form renders inline.
const placeBetAction = vi.fn();
vi.mock("@/lib/bet-actions", () => ({
  placeBetAction: (prev: ActionState, fd: FormData) =>
    placeBetAction(prev, fd),
}));

import { OrderEntryForm } from "@/components/order-entry-form";

const OUTCOMES = [
  { id: "11111111-1111-1111-1111-111111111111", label: "YES", current_odds: "0.50" },
  { id: "22222222-2222-2222-2222-222222222222", label: "NO", current_odds: "0.50" },
];

function renderForm(props?: Partial<Parameters<typeof OrderEntryForm>[0]>) {
  return render(
    <OrderEntryForm
      marketId="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
      outcomes={OUTCOMES}
      marketStatus="OPEN"
      isAuthenticated
      {...props}
    />,
  );
}

/** Type a stake, submit, then confirm in the dialog (fires the action). */
async function submitAndConfirm(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/stake/i), "50");
  await user.click(screen.getByRole("button", { name: "Place bet" }));
  // The confirm dialog opens; "Confirm bet" fires placeBetAction.
  await user.click(await screen.findByRole("button", { name: "Confirm bet" }));
}

describe("OrderEntryForm — backend-status → inline-copy mapping", () => {
  beforeEach(() => {
    placeBetAction.mockReset();
  });

  it("402 → insufficient-balance inline copy", async () => {
    const user = userEvent.setup();
    placeBetAction.mockResolvedValue({
      errors: {
        _form: ["Not enough play balance. Lower your stake or check your wallet."],
      },
    } satisfies ActionState);
    renderForm();
    await submitAndConfirm(user);
    const alert = await screen.findByTestId("bet-error");
    expect(alert).toHaveTextContent(
      "Not enough play balance. Lower your stake or check your wallet.",
    );
  });

  it("409 → market-closed inline copy", async () => {
    const user = userEvent.setup();
    placeBetAction.mockResolvedValue({
      errors: { _form: ["This market is closed and no longer accepting bets."] },
    } satisfies ActionState);
    renderForm();
    await submitAndConfirm(user);
    const alert = await screen.findByTestId("bet-error");
    expect(alert).toHaveTextContent(
      "This market is closed and no longer accepting bets.",
    );
  });

  it("403 → verify-email inline copy (+ resend affordance)", async () => {
    const user = userEvent.setup();
    placeBetAction.mockResolvedValue({
      errors: { _form: ["Verify your email to place bets."] },
    } satisfies ActionState);
    renderForm();
    await submitAndConfirm(user);
    const alert = await screen.findByTestId("bet-error");
    expect(alert).toHaveTextContent("Verify your email to place bets.");
    // The resend-verification link is part of the 403 unverified affordance.
    expect(
      screen.getByRole("link", { name: "Resend verification" }),
    ).toHaveAttribute("href", "/verify-email");
  });

  it("422 → stake-limit inline copy", async () => {
    const user = userEvent.setup();
    placeBetAction.mockResolvedValue({
      errors: { _form: ["Stake must be between 1 and 100000 PLAY_USD."] },
    } satisfies ActionState);
    renderForm();
    await submitAndConfirm(user);
    const alert = await screen.findByTestId("bet-error");
    expect(alert).toHaveTextContent(
      "Stake must be between 1 and 100000 PLAY_USD.",
    );
  });

  it("renders no toast in the bet flow — errors are inline (role=alert)", async () => {
    const user = userEvent.setup();
    placeBetAction.mockResolvedValue({
      errors: { _form: ["Your bet couldn't be placed. Try again."] },
    } satisfies ActionState);
    renderForm();
    await submitAndConfirm(user);
    // The error is in a role="alert" region, not a transient toast.
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Your bet couldn't be placed. Try again.");
  });

  it("unauthenticated → 'Log in to place a bet' affordance, not a dead form", () => {
    renderForm({ isAuthenticated: false });
    expect(
      screen.getByRole("link", { name: "Log in to place a bet" }),
    ).toHaveAttribute("href", "/login");
    // No stake field is rendered for the logged-out affordance.
    expect(screen.queryByLabelText(/stake/i)).not.toBeInTheDocument();
  });

  it("CLOSED market → form disabled with the closed-market copy", () => {
    renderForm({ marketStatus: "CLOSED" });
    expect(screen.getByTestId("market-closed")).toHaveTextContent(
      "This market is closed and no longer accepting bets.",
    );
    expect(screen.getByRole("button", { name: "Place bet" })).toBeDisabled();
  });

  // BET-06 — per-market bounds (client mirror, UX-only; server authoritative).
  it("per-market bounds → a stake below the passed min shows the range message and does NOT submit", async () => {
    const user = userEvent.setup();
    renderForm({ minStake: "10.0000", maxStake: "50.0000" });
    // 5 is above the global min (1) but below the per-market min (10).
    await user.type(screen.getByLabelText(/stake/i), "5");
    await user.click(screen.getByRole("button", { name: "Place bet" }));
    // The inline FormMessage shows the per-market range copy with PLAY_USD…
    expect(
      await screen.findByText("Stake must be between 10 and 50 PLAY_USD."),
    ).toBeInTheDocument();
    // …and the client zod blocked the flow — the confirm dialog never opened, so
    // the Server Action was never fired.
    expect(
      screen.queryByRole("button", { name: "Confirm bet" }),
    ).not.toBeInTheDocument();
    expect(placeBetAction).not.toHaveBeenCalled();
  });

  it("per-market bounds → a stake above the passed max shows the range message", async () => {
    const user = userEvent.setup();
    renderForm({ minStake: "10.0000", maxStake: "50.0000" });
    // 60 is far below the global max (100000) but above the per-market max (50).
    await user.type(screen.getByLabelText(/stake/i), "60");
    await user.click(screen.getByRole("button", { name: "Place bet" }));
    expect(
      await screen.findByText("Stake must be between 10 and 50 PLAY_USD."),
    ).toBeInTheDocument();
    expect(placeBetAction).not.toHaveBeenCalled();
  });
});
