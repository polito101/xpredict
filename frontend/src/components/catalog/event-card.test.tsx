/**
 * Plan 17-02 — EventCard tests (EVT-04 + the per-outcome framing LOCK).
 *
 * Proves the card is distinct (the "Event · N outcomes" badge), shows the top
 * ≤4 outcomes each with its OWN independent YES percent (percentages that sum
 * to >100% — proof they are NOT a single normalized distribution), a "+N more"
 * overflow row, and links to /events/{slug}.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...props
  }: {
    children: React.ReactNode;
    href: string;
    [key: string]: unknown;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

import { EventCard } from "@/components/catalog/event-card";
import type { CatalogItem } from "@/lib/catalog";

function makeEvent(n: number): CatalogItem {
  return {
    type: "event",
    id: "evt-1",
    slug: "who-wins",
    title: "Who wins the election?",
    category: "Politics",
    source: "HOUSE",
    status: "open",
    deadline: "2027-12-31T23:59:59Z",
    volume: "50000",
    created_at: "2026-06-01T00:00:00Z",
    outcomes: Array.from({ length: n }, (_, i) => ({
      label: `Candidate ${i + 1}`,
      yes_outcome_id: `o-${i}`,
      yes_price: (0.5 - i * 0.05).toFixed(2),
    })),
  };
}

describe("<EventCard />", () => {
  it("links the title to /events/{slug}", () => {
    render(<EventCard event={makeEvent(3)} />);
    const link = screen.getByRole("link", { name: "Who wins the election?" });
    expect(link).toHaveAttribute("href", "/events/who-wins");
  });

  it("shows the 'Event · N outcomes' badge with the full outcome count", () => {
    render(<EventCard event={makeEvent(6)} />);
    expect(screen.getByText("Event · 6 outcomes")).toBeInTheDocument();
  });

  it("renders at most 4 outcomes + a '+N more' overflow row", () => {
    render(<EventCard event={makeEvent(6)} />);
    expect(screen.getByText("Candidate 1")).toBeInTheDocument();
    expect(screen.getByText("Candidate 4")).toBeInTheDocument();
    expect(screen.queryByText("Candidate 5")).not.toBeInTheDocument();
    expect(screen.getByText("+2 more")).toBeInTheDocument();
  });

  it("shows each outcome's OWN YES percent (independent — not summed to 100)", () => {
    render(<EventCard event={makeEvent(3)} />);
    // 0.50, 0.45, 0.40 -> 50% + 45% + 40% = 135% (independent per-binary, not a
    // single normalized distribution).
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getByText("45%")).toBeInTheDocument();
    expect(screen.getByText("40%")).toBeInTheDocument();
  });

  it("omits the '+N more' row when outcomes <= 4", () => {
    render(<EventCard event={makeEvent(3)} />);
    expect(screen.queryByText(/\bmore$/)).not.toBeInTheDocument();
  });
});
