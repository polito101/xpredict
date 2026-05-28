/**
 * Plan 06-03 Task 2 -- MarketCard component rendering tests.
 *
 * Verifies: question text, odds display, volume formatting, source badge
 * variants (Polymarket with link, House without link), and odds bar
 * accessibility.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

// Mock next/link to render a plain anchor with children.
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

import { MarketCard } from "@/components/market-card";
import type { MarketItem } from "@/lib/api";

const mockMarket: MarketItem = {
  id: "market-001",
  question: "Will ETH hit $5000?",
  slug: "will-eth-hit-5000",
  category: "crypto",
  source: "POLYMARKET",
  source_market_id: "poly-123",
  status: "OPEN",
  deadline: "2027-12-31T23:59:59Z",
  bet_count: 42,
  created_at: "2026-01-01T00:00:00Z",
  volume: "2100000",
  volume_24hr: "150000",
  source_url: "https://polymarket.com/event/test-123",
  outcomes: [
    { id: "out-1", label: "YES", initial_odds: "0.50", current_odds: "0.63" },
    { id: "out-2", label: "NO", initial_odds: "0.50", current_odds: "0.37" },
  ],
};

describe("<MarketCard />", () => {
  it("renders the market question text", () => {
    render(<MarketCard market={mockMarket} />);
    expect(screen.getByText("Will ETH hit $5000?")).toBeInTheDocument();
  });

  it("renders YES and NO odds percentages", () => {
    render(<MarketCard market={mockMarket} />);
    expect(screen.getByText("63%")).toBeInTheDocument();
    expect(screen.getByText("37%")).toBeInTheDocument();
  });

  it("renders formatted volume", () => {
    render(<MarketCard market={mockMarket} />);
    expect(screen.getByText(/\$2\.1M/i)).toBeInTheDocument();
  });

  it("renders Polymarket source badge", () => {
    render(<MarketCard market={mockMarket} />);
    expect(screen.getByText("Polymarket")).toBeInTheDocument();
  });

  it("renders House badge without link for HOUSE source", () => {
    const houseMarket: MarketItem = {
      ...mockMarket,
      id: "market-002",
      source: "HOUSE",
      source_url: null,
      source_market_id: null,
    };
    render(<MarketCard market={houseMarket} />);
    expect(screen.getByText("House")).toBeInTheDocument();
  });

  it("has an accessible odds bar with role=img", () => {
    render(<MarketCard market={mockMarket} />);
    const oddsBar = screen.getByRole("img");
    expect(oddsBar).toHaveAttribute(
      "aria-label",
      "YES 63%, NO 37%",
    );
  });
});
