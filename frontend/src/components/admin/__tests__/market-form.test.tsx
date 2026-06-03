/**
 * Plan 12-05 Task 2 (TDD — RED) — MarketForm behavior contract.
 *
 * Written BEFORE the component exists. Pins the load-bearing behaviors from the
 * plan's <behavior> block against the EXACT 12-UI-SPEC copy:
 *
 *   1. Create-mode renders question / criteria / deadline / odds / category +
 *      Min/Max stake fields; submitting empty shows the required-field messages.
 *   2. min_stake > max_stake shows "Min stake cannot exceed max stake."
 *   3. Edit-mode with betCount={3} renders the resolution_criteria field DISABLED
 *      and shows the locked helper (ADM-07).
 *   4. A stubbed 422 maps a server field error to the right field's FormMessage.
 *
 * The `"use server"` CRUD helpers are mocked so NO network call occurs. The
 * server is authoritative on validation (the client zod mirror is UX-only).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Mock the use-server CRUD helpers so the form never hits the network.
const createMarket = vi.fn();
const updateMarket = vi.fn();
vi.mock("@/lib/admin-markets-api", () => ({
  createMarket: (body: unknown) => createMarket(body),
  updateMarket: (id: string, body: unknown) => updateMarket(id, body),
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

// Mock the router so create-mode submit navigation is a no-op in jsdom.
const routerPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerPush }),
}));

import { MarketForm } from "@/components/admin/market-form";
import type { MarketFormValues } from "@/components/admin/market-form";

describe("<MarketForm />", () => {
  beforeEach(() => {
    createMarket.mockReset();
    updateMarket.mockReset();
    toastSuccess.mockReset();
    toastError.mockReset();
    routerPush.mockReset();
  });

  it("create-mode renders every field incl. the BET-06 stake inputs and shows required-field errors on empty submit", async () => {
    const user = userEvent.setup();
    render(<MarketForm mode="create" />);

    // All fields present.
    expect(screen.getByLabelText("Question")).toBeInTheDocument();
    expect(screen.getByLabelText("Resolution criteria")).toBeInTheDocument();
    expect(screen.getByLabelText("Deadline")).toBeInTheDocument();
    expect(screen.getByLabelText("Initial odds (YES)")).toBeInTheDocument();
    expect(screen.getByLabelText("Category")).toBeInTheDocument();
    expect(screen.getByLabelText("Min stake (PLAY_USD)")).toBeInTheDocument();
    expect(screen.getByLabelText("Max stake (PLAY_USD)")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Create market" }));

    expect(
      await screen.findByText("A question is required."),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Resolution criteria are required."),
    ).toBeInTheDocument();
    expect(createMarket).not.toHaveBeenCalled();
  });

  it("min_stake > max_stake shows the cross-field error and blocks submit", async () => {
    const user = userEvent.setup();
    createMarket.mockResolvedValue({ id: "m-1" });
    render(<MarketForm mode="create" />);

    await user.type(screen.getByLabelText("Question"), "Will it rain?");
    await user.type(
      screen.getByLabelText("Resolution criteria"),
      "Resolves YES if it rains.",
    );
    // A valid future deadline.
    await user.type(
      screen.getByLabelText("Deadline"),
      "2099-12-31T23:59",
    );
    await user.type(screen.getByLabelText("Min stake (PLAY_USD)"), "100");
    await user.type(screen.getByLabelText("Max stake (PLAY_USD)"), "10");

    await user.click(screen.getByRole("button", { name: "Create market" }));

    expect(
      await screen.findByText("Min stake cannot exceed max stake."),
    ).toBeInTheDocument();
    expect(createMarket).not.toHaveBeenCalled();
  });

  it("edit-mode with bets disables resolution_criteria and shows the locked helper (ADM-07)", () => {
    const initialValues: MarketFormValues = {
      question: "Locked market?",
      resolution_criteria: "Locked criteria text.",
      deadline: "2099-12-31T23:59",
      odds_yes: "0.5",
      category: "",
      min_stake: "",
      max_stake: "",
    };
    render(
      <MarketForm
        mode="edit"
        marketId="m-9"
        initialValues={initialValues}
        betCount={3}
      />,
    );

    const criteria = screen.getByLabelText(
      "Resolution criteria",
    ) as HTMLTextAreaElement;
    expect(criteria).toBeDisabled();
    expect(
      screen.getByText(
        "Resolution criteria are locked once a market has bets.",
      ),
    ).toBeInTheDocument();
  });

  it("a 422 from the API maps a server field error to the matching FormMessage", async () => {
    const user = userEvent.setup();
    // The use-server layer throws Error("API error: <status>"); for a 422 with
    // structured field errors the form maps each to its field. We encode the
    // field errors in a JSON message so parseMarketApiError can recover them.
    createMarket.mockRejectedValue(
      new Error(
        JSON.stringify({
          kind: "market_api_error",
          status: 422,
          fieldErrors: { question: "Question is already taken." },
        }),
      ),
    );
    render(<MarketForm mode="create" />);

    await user.type(screen.getByLabelText("Question"), "Dup question");
    await user.type(
      screen.getByLabelText("Resolution criteria"),
      "Resolves YES if X.",
    );
    await user.type(screen.getByLabelText("Deadline"), "2099-12-31T23:59");

    await user.click(screen.getByRole("button", { name: "Create market" }));

    expect(
      await screen.findByText("Question is already taken."),
    ).toBeInTheDocument();
  });
});
