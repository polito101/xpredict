/**
 * Plan 17-01 — catalog client URL-contract + adapter tests.
 *
 * Locks the public catalog fetch shapes (the `/api/v1/catalog|events|categories`
 * prefix, the non-empty-params-only query build, the EventNotFound 404 throw)
 * and the binary-card adapter (deadline-null guard). Mirrors the global-fetch
 * spy style of `auth.test.ts` / `admin-markets-api.test.ts`.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

import {
  fetchCatalog,
  fetchEvent,
  fetchCategories,
  EventNotFound,
  catalogMarketToMarketItem,
  type CatalogItem,
} from "../catalog";

type FetchMock = {
  mockResolvedValue: (v: Response) => void;
  mockResolvedValueOnce: (v: Response) => void;
  mock: { calls: unknown[][] };
};
let fetchSpy: FetchMock;

function ok(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  fetchSpy = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(ok([])) as unknown as FetchMock;
  process.env.BACKEND_URL = "http://backend.test";
});

describe("fetchCatalog builds /api/v1/catalog with non-empty params only", () => {
  it("includes all provided filters", async () => {
    await fetchCatalog({
      q: "btc",
      category: "Crypto",
      status: "open",
      sort: "newest",
    });
    const [url] = fetchSpy.mock.calls[0] as [string];
    expect(url).toContain("http://backend.test/api/v1/catalog?");
    expect(url).toContain("q=btc");
    expect(url).toContain("category=Crypto");
    expect(url).toContain("status=open");
    expect(url).toContain("sort=newest");
  });

  it("omits empty params (no query string when none)", async () => {
    await fetchCatalog({});
    const [url] = fetchSpy.mock.calls[0] as [string];
    expect(url).toBe("http://backend.test/api/v1/catalog");
  });
});

describe("fetchEvent", () => {
  it("hits /api/v1/events/{slug}", async () => {
    fetchSpy.mockResolvedValue(ok({ id: "e1", slug: "s", outcomes: [] }));
    await fetchEvent("my-event");
    const [url] = fetchSpy.mock.calls[0] as [string];
    expect(url).toBe("http://backend.test/api/v1/events/my-event");
  });

  it("throws EventNotFound on 404", async () => {
    fetchSpy.mockResolvedValue(new Response("not found", { status: 404 }));
    await expect(fetchEvent("missing")).rejects.toBeInstanceOf(EventNotFound);
  });
});

describe("fetchCategories", () => {
  it("hits /api/v1/categories", async () => {
    fetchSpy.mockResolvedValue(ok(["Sports", "Crypto"]));
    const cats = await fetchCategories();
    const [url] = fetchSpy.mock.calls[0] as [string];
    expect(url).toBe("http://backend.test/api/v1/categories");
    expect(cats).toEqual(["Sports", "Crypto"]);
  });
});

describe("catalogMarketToMarketItem adapter", () => {
  const item: CatalogItem = {
    type: "market",
    id: "m1",
    slug: "will-x",
    title: "Will X happen?",
    category: "Crypto",
    source: "POLYMARKET",
    status: "open",
    deadline: null,
    volume: "1234.5",
    created_at: "2026-06-01T00:00:00Z",
    outcomes: [{ label: "YES", yes_outcome_id: "o1", yes_price: "0.42" }],
  };

  it("maps title->question, yes_price->YES current_odds, null deadline->''", () => {
    const m = catalogMarketToMarketItem(item);
    expect(m.question).toBe("Will X happen?");
    expect(m.deadline).toBe("");
    const yes = m.outcomes.find((o) => o.label === "YES");
    expect(yes?.current_odds).toBe("0.42");
    expect(yes?.id).toBe("o1");
    expect(m.volume).toBe("1234.5");
    expect(m.source_url).toBeNull();
  });
});
