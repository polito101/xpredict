/**
 * Plan 17-03 — EventDetailView tests (EVT-02/03 + the WS cap).
 *
 * Proves: one INDEPENDENT row per outcome with its own YES percent (percentages
 * summing to >100% — proof they are not a normalized distribution), exactly ONE
 * live socket on screen (the selected child — the storm-proof cap), the order
 * form targets the selected child, and selecting another outcome client-fetches
 * that child and re-targets the panel. The reused heavy children are stubbed.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

const fetchMarketMock = vi.fn();
const fetchPriceHistoryMock = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    fetchMarket: (...args: unknown[]) => fetchMarketMock(...args),
    fetchPriceHistory: (...args: unknown[]) => fetchPriceHistoryMock(...args),
  };
});

vi.mock("@/components/market-detail-live-odds", () => ({
  MarketDetailLiveOdds: ({ marketId }: { marketId: string }) => (
    <div data-testid="live-odds">live:{marketId}</div>
  ),
}));
vi.mock("@/components/price-history-section", () => ({
  PriceHistorySection: ({ slug }: { slug: string }) => (
    <div data-testid="price-history">history:{slug}</div>
  ),
}));
vi.mock("@/components/order-entry-form", () => ({
  OrderEntryForm: ({ marketId }: { marketId: string }) => (
    <div data-testid="order-form">order:{marketId}</div>
  ),
}));

import { EventDetailView } from "@/components/event/event-detail-view";
import type { EventDetail } from "@/lib/catalog";
import type { MarketDetail } from "@/lib/api";

const event: EventDetail = {
  id: "evt-1",
  slug: "who-wins",
  title: "Who wins?",
  category: "Politics",
  source: "HOUSE",
  status: "open",
  deadline: null,
  created_at: "2026-06-01T00:00:00Z",
  outcomes: [
    { label: "Alice", yes_outcome_id: "ya", yes_price: "0.60", market_id: "m-a", child_slug: "who-wins-alice", child_status: "OPEN" },
    { label: "Bob", yes_outcome_id: "yb", yes_price: "0.40", market_id: "m-b", child_slug: "who-wins-bob", child_status: "OPEN" },
    { label: "Carol", yes_outcome_id: "yc", yes_price: "0.20", market_id: "m-c", child_slug: "who-wins-carol", child_status: "OPEN" },
  ],
};

function childDetail(id: string, slug: string, yes: string): MarketDetail {
  return {
    id,
    question: `Will ${id}?`,
    slug,
    category: "Politics",
    source: "HOUSE",
    source_market_id: null,
    status: "OPEN",
    deadline: "2027-01-01T00:00:00Z",
    bet_count: 0,
    created_at: "2026-06-01T00:00:00Z",
    volume: "100",
    volume_24hr: "0",
    source_url: null,
    resolution_criteria: "x",
    winning_outcome_id: null,
    resolution_source: null,
    resolution_justification: null,
    resolved_at: null,
    min_stake: null,
    max_stake: null,
    outcomes: [
      { id: `${id}-yes`, label: "YES", initial_odds: yes, current_odds: yes },
      { id: `${id}-no`, label: "NO", initial_odds: "0.5", current_odds: "0.5" },
    ],
  };
}

const defaultChild = childDetail("m-a", "who-wins-alice", "0.60");

beforeEach(() => {
  fetchMarketMock.mockReset();
  fetchPriceHistoryMock.mockReset();
});

describe("<EventDetailView />", () => {
  it("renders one independent row per outcome with its own YES % (not summed to 100)", () => {
    render(
      <EventDetailView
        event={event}
        defaultChild={defaultChild}
        defaultHistory={[]}
        isAuthenticated
      />,
    );
    // 60 + 40 + 20 = 120% -> independent per-binary, not a normalized distribution.
    expect(
      screen.getByRole("button", { name: "Alice, 60% YES" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Bob, 40% YES" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Carol, 20% YES" }),
    ).toBeInTheDocument();
  });

  it("mounts the order form + exactly ONE live socket for the selected child (WS cap)", () => {
    render(
      <EventDetailView
        event={event}
        defaultChild={defaultChild}
        defaultHistory={[]}
        isAuthenticated
      />,
    );
    expect(screen.getByTestId("order-form")).toHaveTextContent("order:m-a");
    expect(screen.getAllByTestId("live-odds")).toHaveLength(1);
    expect(screen.getByTestId("live-odds")).toHaveTextContent("live:m-a");
  });

  it("selecting another outcome fetches that child and re-targets the panel", async () => {
    fetchMarketMock.mockResolvedValue(childDetail("m-b", "who-wins-bob", "0.40"));
    fetchPriceHistoryMock.mockResolvedValue({ window: "7d", points: [] });
    render(
      <EventDetailView
        event={event}
        defaultChild={defaultChild}
        defaultHistory={[]}
        isAuthenticated
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Bob, 40% YES" }));
    expect(fetchMarketMock).toHaveBeenCalledWith("who-wins-bob");
    await waitFor(() =>
      expect(screen.getByTestId("order-form")).toHaveTextContent("order:m-b"),
    );
    // Still exactly one socket after switching — getByTestId throws on >1, so
    // this asserts the cap held AND it re-targeted the new child.
    expect(screen.getByTestId("live-odds")).toHaveTextContent("live:m-b");
  });

  it("ignores a stale out-of-order fetch (rapid switching keeps the latest)", async () => {
    let resolveBob!: (v: MarketDetail) => void;
    const bobPromise = new Promise<MarketDetail>((r) => {
      resolveBob = r;
    });
    fetchMarketMock.mockImplementation((slug: string) => {
      if (slug === "who-wins-bob") return bobPromise; // resolves LATE
      if (slug === "who-wins-carol")
        return Promise.resolve(childDetail("m-c", "who-wins-carol", "0.20"));
      return Promise.resolve(defaultChild);
    });
    fetchPriceHistoryMock.mockResolvedValue({ window: "7d", points: [] });
    render(
      <EventDetailView
        event={event}
        defaultChild={defaultChild}
        defaultHistory={[]}
        isAuthenticated
      />,
    );
    // Select Bob (its fetch stays pending), then quickly Carol (resolves fast).
    fireEvent.click(screen.getByRole("button", { name: "Bob, 40% YES" }));
    fireEvent.click(screen.getByRole("button", { name: "Carol, 20% YES" }));
    await waitFor(() =>
      expect(screen.getByTestId("order-form")).toHaveTextContent("order:m-c"),
    );
    // Bob's late response must NOT clobber the panel — it is stale.
    resolveBob(childDetail("m-b", "who-wins-bob", "0.40"));
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.getByTestId("order-form")).toHaveTextContent("order:m-c");
  });
});
