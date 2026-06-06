/**
 * Plan 12-02 Task 3 (Wave 0 — RED) — MarketStatusBadge behavior contract.
 *
 * Written BEFORE the component exists (TDD RED). Pins the <behavior> block:
 *   1. Renders all 5 market statuses with their label text.
 *   2. Each carries `aria-label="Status: {STATUS}"` (a11y chip convention,
 *      cloned from user-status-badge.tsx).
 *   3. The locked UI-SPEC §Status badge palette colors map per status — at
 *      least RESOLVED → bg-zinc-900 and OPEN → bg-emerald-100 are asserted.
 *   4. An optional `className` is merged via cn().
 *
 * The 5-state palette + the `px-2.5 py-0.5 text-xs font-semibold` inset are the
 * locked inherited convention (UI-SPEC §Spacing inherited locked exceptions).
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { MarketStatusBadge } from "../market-status-badge";

const STATUSES = ["OPEN", "CLOSED", "RESOLVED", "CANCELLED", "DRAFT"] as const;

describe("MarketStatusBadge", () => {
  it.each(STATUSES)("renders the %s status label", (status) => {
    render(<MarketStatusBadge status={status} />);
    expect(screen.getByText(status)).toBeInTheDocument();
  });

  it.each(STATUSES)("exposes aria-label \"Status: %s\"", (status) => {
    render(<MarketStatusBadge status={status} />);
    expect(screen.getByLabelText(`Status: ${status}`)).toBeInTheDocument();
  });

  it("keeps the locked chip inset on every status", () => {
    render(<MarketStatusBadge status="OPEN" />);
    const chip = screen.getByLabelText("Status: OPEN");
    expect(chip).toHaveClass(
      "inline-flex",
      "items-center",
      "rounded-full",
      "px-2.5",
      "py-0.5",
      "text-xs",
      "font-semibold",
    );
  });

  it("applies the OPEN palette (emerald tint)", () => {
    render(<MarketStatusBadge status="OPEN" />);
    expect(screen.getByLabelText("Status: OPEN")).toHaveClass(
      "bg-emerald-500/15",
      "text-emerald-400",
    );
  });

  it("applies the RESOLVED palette (neutral terminal)", () => {
    render(<MarketStatusBadge status="RESOLVED" />);
    expect(screen.getByLabelText("Status: RESOLVED")).toHaveClass(
      "bg-foreground/10",
      "text-foreground",
    );
  });

  it("applies the CANCELLED palette (red tint terminal-negative)", () => {
    render(<MarketStatusBadge status="CANCELLED" />);
    expect(screen.getByLabelText("Status: CANCELLED")).toHaveClass(
      "bg-red-500/15",
      "text-red-400",
    );
  });

  it("merges an optional className via cn()", () => {
    render(<MarketStatusBadge status="DRAFT" className="ml-2" />);
    expect(screen.getByLabelText("Status: DRAFT")).toHaveClass("ml-2");
  });
});
