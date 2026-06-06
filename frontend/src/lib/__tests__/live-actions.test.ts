/**
 * LB-B-03 (plan-check M-1) — live-bets mirror Server Action contract tests.
 *
 * `recordLivePlaced` / `recordLiveSettled` / `mintLiveSession` / `getLiveBalance`
 * are the ONLY authed path that mirrors live-bets money into the XPredict ledger,
 * and had no direct test. This guards: the HttpOnly session cookie is forwarded
 * as a `Cookie: xpredict_session=…` header to the correct backend URL + method,
 * and each LB-A status maps to the right discriminated result
 * (200 -> parsed/applied · 401 unauthenticated · 404 not_found · 409 conflict ·
 * else error). Runs under `node` (file is `*.test.ts`).
 *
 * Mirrors the Server-Action mocking pattern in `admin-api.test.ts` / `auth.test.ts`
 * (hoisted `next/headers` cookies + a global `fetch` spy asserting URL/method).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const mocks = vi.hoisted(() => {
  // The cookie getter must be able to return `undefined` (no-session cases), so
  // type it explicitly — otherwise the default impl narrows it to `{value}`.
  const cookieStore = {
    get: vi.fn<(name: string) => { value: string } | undefined>(() => ({
      value: "test-session",
    })),
    set: vi.fn(),
    delete: vi.fn(),
  };
  const cookiesMock = vi.fn(async () => cookieStore);
  return { cookieStore, cookiesMock };
});

vi.mock("next/headers", () => ({ cookies: mocks.cookiesMock }));

import {
  recordLivePlaced,
  recordLiveSettled,
  mintLiveSession,
  getLiveBalance,
} from "../live-actions";

type FetchMock = {
  mockResolvedValue: (v: Response) => void;
  mockResolvedValueOnce: (v: Response) => void;
  mockRejectedValueOnce: (e: Error) => void;
  mock: { calls: unknown[][] };
};
let fetchSpy: FetchMock;

/** A JSON Response with a chosen status (LB-A always replies JSON on 200). */
function jsonResponse(status: number, body: unknown = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.cookieStore.get.mockReturnValue({ value: "test-session" });
  fetchSpy = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(jsonResponse(200, { applied: true })) as unknown as FetchMock;
  process.env.BACKEND_URL = "http://backend.test";
});

// ===========================================================================
// recordLivePlaced
// ===========================================================================

describe("recordLivePlaced", () => {
  it("POSTs to /api/live/bets/{betId}/placed forwarding the session cookie", async () => {
    await recordLivePlaced("bet-1");

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit | undefined];
    expect(url).toBe("http://backend.test/api/live/bets/bet-1/placed");
    expect(init?.method).toBe("POST");
    expect(init?.headers).toMatchObject({ Cookie: "xpredict_session=test-session" });
  });

  it("url-encodes the betId in the path", async () => {
    await recordLivePlaced("a/b#c");
    const [url] = fetchSpy.mock.calls[0] as [string, RequestInit | undefined];
    expect(url).toBe("http://backend.test/api/live/bets/a%2Fb%23c/placed");
  });

  it("200 -> {ok:true, applied:true} when the backend applied the mirror", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(200, { applied: true }));
    expect(await recordLivePlaced("bet-1")).toEqual({ ok: true, applied: true });
  });

  it("200 with applied:false -> {ok:true, applied:false} (idempotent no-op)", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(200, { applied: false }));
    expect(await recordLivePlaced("bet-1")).toEqual({ ok: true, applied: false });
  });

  it("no session cookie -> {ok:false, reason:'unauthenticated'} WITHOUT calling fetch", async () => {
    mocks.cookieStore.get.mockReturnValue(undefined);
    const result = await recordLivePlaced("bet-1");
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(result).toEqual({ ok: false, reason: "unauthenticated" });
  });

  it("maps statuses: 401->unauthenticated, 404->not_found, 409->conflict, 500->error", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(401));
    expect(await recordLivePlaced("b")).toEqual({ ok: false, reason: "unauthenticated" });
    fetchSpy.mockResolvedValueOnce(jsonResponse(404));
    expect(await recordLivePlaced("b")).toEqual({ ok: false, reason: "not_found" });
    fetchSpy.mockResolvedValueOnce(jsonResponse(409));
    expect(await recordLivePlaced("b")).toEqual({ ok: false, reason: "conflict" });
    fetchSpy.mockResolvedValueOnce(jsonResponse(500));
    expect(await recordLivePlaced("b")).toEqual({ ok: false, reason: "error" });
  });

  it("a thrown fetch (network error) -> {ok:false, reason:'error'}", async () => {
    fetchSpy.mockRejectedValueOnce(new Error("ECONNREFUSED"));
    expect(await recordLivePlaced("b")).toEqual({ ok: false, reason: "error" });
  });
});

// ===========================================================================
// recordLiveSettled
// ===========================================================================

describe("recordLiveSettled", () => {
  it("POSTs to /api/live/bets/{betId}/settled forwarding the session cookie", async () => {
    await recordLiveSettled("bet-2");
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit | undefined];
    expect(url).toBe("http://backend.test/api/live/bets/bet-2/settled");
    expect(init?.method).toBe("POST");
    expect(init?.headers).toMatchObject({ Cookie: "xpredict_session=test-session" });
  });

  it("200 -> {ok:true, applied:true}; 404 -> not_found", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(200, { applied: true }));
    expect(await recordLiveSettled("bet-2")).toEqual({ ok: true, applied: true });
    fetchSpy.mockResolvedValueOnce(jsonResponse(404));
    expect(await recordLiveSettled("bet-2")).toEqual({ ok: false, reason: "not_found" });
  });

  it("no session cookie -> {ok:false, reason:'unauthenticated'} WITHOUT calling fetch", async () => {
    mocks.cookieStore.get.mockReturnValue(undefined);
    expect(await recordLiveSettled("bet-2")).toEqual({
      ok: false,
      reason: "unauthenticated",
    });
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

// ===========================================================================
// mintLiveSession
// ===========================================================================

describe("mintLiveSession", () => {
  it("POSTs to /api/live/session with JSON content-type + the session cookie", async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse(200, { session_token: "t2", expires_at: "2026-06-06T11:00:00Z" }),
    );
    await mintLiveSession("tbl-1");

    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit | undefined];
    expect(url).toBe("http://backend.test/api/live/session");
    expect(init?.method).toBe("POST");
    expect(init?.headers).toMatchObject({
      "Content-Type": "application/json",
      Cookie: "xpredict_session=test-session",
    });
  });

  it("sends { table_id } only when a tableId is supplied", async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse(200, { session_token: "t2", expires_at: "x" }),
    );
    await mintLiveSession("tbl-1");
    const [, init] = fetchSpy.mock.calls[0] as [string, RequestInit | undefined];
    expect(JSON.parse(init?.body as string)).toEqual({ table_id: "tbl-1" });
  });

  it("sends an empty body {} when no tableId is supplied (LB-A defaults)", async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse(200, { session_token: "t2", expires_at: "x" }),
    );
    await mintLiveSession();
    const [, init] = fetchSpy.mock.calls[0] as [string, RequestInit | undefined];
    expect(JSON.parse(init?.body as string)).toEqual({});
  });

  it("200 with token+expiry -> {ok:true, session_token, expires_at}", async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse(200, { session_token: "t2", expires_at: "2026-06-06T11:00:00Z" }),
    );
    expect(await mintLiveSession("tbl")).toEqual({
      ok: true,
      session_token: "t2",
      expires_at: "2026-06-06T11:00:00Z",
    });
  });

  it("200 with a malformed body (missing fields) -> {ok:false, reason:'error'}", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(200, { session_token: "t2" }));
    expect(await mintLiveSession("tbl")).toEqual({ ok: false, reason: "error" });
  });

  it("409 -> {ok:false, reason:'conflict'}", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(409));
    expect(await mintLiveSession("tbl")).toEqual({ ok: false, reason: "conflict" });
  });

  it("no session cookie -> {ok:false, reason:'unauthenticated'} WITHOUT calling fetch", async () => {
    mocks.cookieStore.get.mockReturnValue(undefined);
    expect(await mintLiveSession("tbl")).toEqual({
      ok: false,
      reason: "unauthenticated",
    });
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

// ===========================================================================
// getLiveBalance (M-2 in-island refresh source)
// ===========================================================================

describe("getLiveBalance", () => {
  it("GETs /wallet/me/balance forwarding the session cookie", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(200, { balance: "150.0000" }));
    await getLiveBalance();

    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit | undefined];
    expect(url).toBe("http://backend.test/wallet/me/balance");
    // GET: no explicit method set by the action (fetch defaults to GET).
    expect(init?.method).toBeUndefined();
    expect(init?.headers).toMatchObject({ Cookie: "xpredict_session=test-session" });
  });

  it("200 with a string balance -> {ok:true, balance} (string verbatim, SP-1)", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(200, { balance: "150.0000" }));
    expect(await getLiveBalance()).toEqual({ ok: true, balance: "150.0000" });
  });

  it("a non-string balance -> {ok:false} (never coerced)", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(200, { balance: 150 }));
    expect(await getLiveBalance()).toEqual({ ok: false });
  });

  it("a non-ok response -> {ok:false}", async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(503));
    expect(await getLiveBalance()).toEqual({ ok: false });
  });

  it("no session cookie -> {ok:false} WITHOUT calling fetch", async () => {
    mocks.cookieStore.get.mockReturnValue(undefined);
    expect(await getLiveBalance()).toEqual({ ok: false });
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
