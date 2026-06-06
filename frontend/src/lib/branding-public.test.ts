/**
 * Plan 10-05 Task 1 (RED) — public branding fetch helper tests.
 *
 * Validates `frontend/src/lib/branding-public.ts` (built GREEN in Task 2):
 *   1. fetchBrandingPublic() parses a 200 `/branding/current` JSON into the
 *      typed `{ brand_name, primary_hex, secondary_hex, logo_url }` object.
 *   2. fetchBrandingPublic() calls the backend with `cache: "no-store"` (the
 *      per-navigation freshness contract — a re-skin must apply on the player's
 *      NEXT navigation, never a build-time static cache).
 *   3. A non-2xx response THROWS — so the root layout's try/catch can fall back
 *      to `DEFAULT_BRANDING` (the safe-fallback / never-unbranded contract).
 *   4. `DEFAULT_BRANDING` is the XPredict indigo/sky palette used by that
 *      fallback.
 *
 * Mocks: global `fetch` only (no Next runtime needed — this is a plain public
 * helper, NOT a "use server" module). Mirrors the fetch-spy style in
 * `lib/__tests__/auth.test.ts`.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

import {
  fetchBrandingPublic,
  DEFAULT_BRANDING,
  type BrandingPublic,
} from "./branding-public";

// Spy on global fetch (different impl per test). Mirrors auth.test.ts: a plain
// `unknown`-keyed mock rather than the constrained `vi.spyOn` overload, which
// the TS compiler refuses to feed the Web-API + Node.js `fetch` intersection
// into (and next-lint blocks plain `any`).
type FetchMock = {
  mockResolvedValue: (v: Response) => void;
  mockResolvedValueOnce: (v: Response) => void;
  mock: { calls: unknown[][] };
};
let fetchSpy: FetchMock;

const PAYLOAD: BrandingPublic = {
  brand_name: "Acme Predictions",
  primary_hex: "#112233",
  secondary_hex: "#445566",
  logo_url: "/branding/logo",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  fetchSpy = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(jsonResponse(PAYLOAD)) as unknown as FetchMock;
  process.env.BACKEND_URL = "http://backend.test";
});

describe("fetchBrandingPublic", () => {
  it("parses a 200 /branding/current response into the typed object", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(PAYLOAD));

    const result = await fetchBrandingPublic();

    expect(result).toEqual(PAYLOAD);
  });

  it("requests /branding/current with cache: 'no-store' (per-navigation freshness)", async () => {
    await fetchBrandingPublic();

    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/branding/current");
    expect(init.cache).toBe("no-store");
  });

  it("throws on a non-ok response so the layout falls back to the default palette", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse({ detail: "boom" }, 503));

    await expect(fetchBrandingPublic()).rejects.toThrow();
  });
});

describe("DEFAULT_BRANDING", () => {
  it("is the XPrediction indigo/sky safe-fallback palette", () => {
    expect(DEFAULT_BRANDING).toEqual({
      brand_name: "XPrediction",
      primary_hex: "#4f46e5",
      secondary_hex: "#0ea5e9",
      logo_url: null,
    });
  });
});
