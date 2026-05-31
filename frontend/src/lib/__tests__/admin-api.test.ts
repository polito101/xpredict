/**
 * Plan 08-03 (UAT gap fix) — admin-api Server Action URL-contract tests.
 *
 * Regression guard for the recharge-endpoint prefix bug found in UAT:
 * the Phase 3 wallet recharge endpoint is mounted at `/admin/wallets/...`
 * (NO `/api/v1` prefix), UNLIKE the 08-01/08-02 admin-CRM endpoints which DO
 * live under `/api/v1/admin`. `rechargeWallet` must target the real backend
 * path — otherwise every recharge 404s ("Not Found") and the Server Action
 * surfaces a 500.
 *
 * Mirrors the mocking pattern in `auth.test.ts` (hoisted next/headers cookies
 * + global fetch spy).
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

import { rechargeWallet, banUser, fetchUsers, fetchAuditEventTypes } from "../admin-api";

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

describe("rechargeWallet (Phase 3 primitive — different prefix)", () => {
  it("POSTs to /admin/wallets/{id}/recharge, NOT the /api/v1 CRM prefix", async () => {
    await rechargeWallet("user-123", "42.0000", "promo", "idem-key-1");

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit | undefined];
    expect(url).toBe("http://backend.test/admin/wallets/user-123/recharge");
    // The exact regression: must NOT carry the /api/v1 CRM prefix.
    expect(url).not.toContain("/api/v1/admin/wallets");
    expect(init?.method).toBe("POST");
    expect(init?.headers).toMatchObject({
      "Content-Type": "application/json",
      "Idempotency-Key": "idem-key-1",
      Authorization: "Bearer test-admin-jwt",
    });
    expect(JSON.parse(init?.body as string)).toEqual({
      amount: "42.0000",
      reason: "promo",
    });
  });
});

describe("admin-CRM endpoints keep the /api/v1/admin prefix", () => {
  it("banUser -> /api/v1/admin/users/{id}/ban", async () => {
    await banUser("user-9", "fraud");
    const [url] = fetchSpy.mock.calls[0] as [string, RequestInit | undefined];
    expect(url).toBe("http://backend.test/api/v1/admin/users/user-9/ban");
  });

  it("fetchUsers -> /api/v1/admin/users", async () => {
    await fetchUsers({ page: 1, page_size: 20 });
    const [url] = fetchSpy.mock.calls[0] as [string, RequestInit | undefined];
    expect(url).toContain("http://backend.test/api/v1/admin/users");
  });

  it("fetchAuditEventTypes -> /api/v1/admin/audit-log/event-types", async () => {
    await fetchAuditEventTypes();
    const [url] = fetchSpy.mock.calls[0] as [string, RequestInit | undefined];
    expect(url).toBe("http://backend.test/api/v1/admin/audit-log/event-types");
  });
});
