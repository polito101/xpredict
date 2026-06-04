/**
 * Plan 12-02 (Wave 0) — admin-markets-api Server Action URL-contract tests.
 *
 * THE single most important new test of Phase 12: the regression guard for the
 * two-prefix landmine (Pitfall 1 / threat T-12-06). Market CRUD is mounted at
 * `/api/v1/admin/markets` (`markets/router.py:32-33`) but resolve / reverse /
 * force-settle live at the BARE `/admin/markets/{id}/...` prefix
 * (`settlement/router.py:46`, NO `/api/v1`). A wrong prefix silently 404s, which
 * can mask an auth failure. This locks the split so the settlement wrappers can
 * never regress to `/api/v1`.
 *
 * Mirrors `admin-api.test.ts` (which guards the analogous recharge-prefix bug):
 * hoisted next/headers cookie mock + a global fetch spy + BACKEND_URL setup.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const mocks = vi.hoisted(() => {
  const cookieStore = {
    get: vi.fn(() => ({ value: "test-admin-jwt" })),
    set: vi.fn(),
    delete: vi.fn(),
  };
  const cookiesMock = vi.fn(async () => cookieStore);
  return { cookieStore, cookiesMock };
});

vi.mock("next/headers", () => ({
  cookies: mocks.cookiesMock,
}));

import {
  fetchMarkets,
  fetchMarketAdmin,
  createMarket,
  updateMarket,
  closeMarket,
  resolveMarket,
  reverseSettlement,
  forceSettle,
} from "../admin-markets-api";

type FetchMock = {
  mockResolvedValue: (v: Response) => void;
  mockResolvedValueOnce: (v: Response) => void;
  mock: { calls: unknown[][] };
};
let fetchSpy: FetchMock;

beforeEach(() => {
  vi.clearAllMocks();
  mocks.cookieStore.get.mockReturnValue({ value: "test-admin-jwt" });
  fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  ) as unknown as FetchMock;
  process.env.BACKEND_URL = "http://backend.test";
});

describe("market CRUD keeps the /api/v1/admin/markets prefix", () => {
  it("fetchMarkets -> /api/v1/admin/markets", async () => {
    await fetchMarkets({ page: 1, page_size: 20 });
    const [url] = fetchSpy.mock.calls[0] as [string, RequestInit | undefined];
    expect(url).toContain("http://backend.test/api/v1/admin/markets");
  });

  it("fetchMarketAdmin -> /api/v1/admin/markets/{id}", async () => {
    await fetchMarketAdmin("m-1");
    const [url] = fetchSpy.mock.calls[0] as [string, RequestInit | undefined];
    expect(url).toBe("http://backend.test/api/v1/admin/markets/m-1");
  });

  it("createMarket -> POST /api/v1/admin/markets", async () => {
    await createMarket({
      question: "Will it rain?",
      resolution_criteria: "Per the weather service.",
      deadline: "2099-01-01T00:00:00Z",
    });
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit | undefined];
    expect(url).toBe("http://backend.test/api/v1/admin/markets");
    expect(init?.method).toBe("POST");
  });

  it("updateMarket -> PATCH /api/v1/admin/markets/{id}", async () => {
    await updateMarket("m-1", { category: "weather" });
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit | undefined];
    expect(url).toBe("http://backend.test/api/v1/admin/markets/m-1");
    expect(init?.method).toBe("PATCH");
  });

  it("closeMarket -> POST /api/v1/admin/markets/{id}/close", async () => {
    await closeMarket("m-1");
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit | undefined];
    expect(url).toBe("http://backend.test/api/v1/admin/markets/m-1/close");
    expect(init?.method).toBe("POST");
  });
});

describe("settlement is BARE — must NOT carry /api/v1 (the regression guard)", () => {
  it("resolveMarket -> /admin/markets/{id}/resolve, NOT /api/v1", async () => {
    await resolveMarket("m-1", { winning_outcome_id: "o-1", justification: "x" });
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit | undefined];
    expect(url).toBe("http://backend.test/admin/markets/m-1/resolve");
    // The exact regression: must NOT carry the /api/v1 CRUD prefix.
    expect(url).not.toContain("/api/v1/admin/markets");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({
      winning_outcome_id: "o-1",
      justification: "x",
    });
  });

  it("reverseSettlement -> /admin/markets/{id}/reverse, NOT /api/v1", async () => {
    await reverseSettlement("m-1", { justification: "x" });
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit | undefined];
    expect(url).toBe("http://backend.test/admin/markets/m-1/reverse");
    expect(url).not.toContain("/api/v1");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({ justification: "x" });
  });

  it("forceSettle -> /admin/markets/{id}/force-settle, NOT /api/v1", async () => {
    await forceSettle("m-1", { winning_outcome_id: "o-1", justification: "x" });
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit | undefined];
    expect(url).toBe("http://backend.test/admin/markets/m-1/force-settle");
    expect(url).not.toContain("/api/v1");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({
      winning_outcome_id: "o-1",
      justification: "x",
    });
  });
});

describe("every wrapper forwards the admin_jwt Bearer header", () => {
  it("fetchMarkets forwards Authorization: Bearer test-admin-jwt", async () => {
    await fetchMarkets({ page: 1, page_size: 20 });
    const [, init] = fetchSpy.mock.calls[0] as [string, RequestInit | undefined];
    expect(init?.headers).toMatchObject({
      Authorization: "Bearer test-admin-jwt",
    });
  });

  it("resolveMarket forwards Authorization: Bearer test-admin-jwt", async () => {
    await resolveMarket("m-1", { winning_outcome_id: "o-1", justification: "x" });
    const [, init] = fetchSpy.mock.calls[0] as [string, RequestInit | undefined];
    expect(init?.headers).toMatchObject({
      "Content-Type": "application/json",
      Authorization: "Bearer test-admin-jwt",
    });
  });
});
