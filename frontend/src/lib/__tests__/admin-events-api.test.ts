/**
 * Plan 17-01 — admin-events-api Server Action URL-contract tests.
 *
 * The regression guard for the event prefix: the admin event surface is BARE
 * `/admin/events…` (NO `/api/v1`), mirroring the settlement router. Also locks
 * the two-step `confirm` flag passthrough and the 423 edit-lock recognition.
 * Clone of `admin-markets-api.test.ts` (hoisted next/headers cookie mock + a
 * global fetch spy + BACKEND_URL setup).
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
  createEvent,
  updateEvent,
  resolveEvent,
  voidEvent,
  reverseEvent,
} from "../admin-events-api";
import { isEventLockedError } from "../admin-events-types";

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

const TWO_OUTCOMES = [
  { label: "A", initial_odds: "0.5" },
  { label: "B", initial_odds: "0.5" },
];

beforeEach(() => {
  vi.clearAllMocks();
  mocks.cookieStore.get.mockReturnValue({ value: "test-admin-jwt" });
  fetchSpy = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(ok({ ok: true })) as unknown as FetchMock;
  process.env.BACKEND_URL = "http://backend.test";
});

describe("admin events use the BARE /admin/events prefix (never /api/v1)", () => {
  it("createEvent -> POST /admin/events", async () => {
    await createEvent({
      title: "Who wins?",
      deadline: "2099-01-01T00:00:00Z",
      outcomes: TWO_OUTCOMES,
    });
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit | undefined];
    expect(url).toBe("http://backend.test/admin/events");
    expect(url).not.toContain("/api/v1");
    expect(init?.method).toBe("POST");
  });

  it("updateEvent -> PATCH /admin/events/{id}", async () => {
    await updateEvent("g-1", { title: "x" });
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit | undefined];
    expect(url).toBe("http://backend.test/admin/events/g-1");
    expect(url).not.toContain("/api/v1");
    expect(init?.method).toBe("PATCH");
  });

  it("resolveEvent -> POST /admin/events/{id}/resolve", async () => {
    await resolveEvent("g-1", {
      winning_outcome_id: "o-1",
      justification: "x",
      confirm: false,
    });
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit | undefined];
    expect(url).toBe("http://backend.test/admin/events/g-1/resolve");
    expect(url).not.toContain("/api/v1");
    expect(init?.method).toBe("POST");
  });

  it("voidEvent -> POST /admin/events/{id}/void", async () => {
    await voidEvent("g-1", { justification: "x" });
    const [url] = fetchSpy.mock.calls[0] as [string];
    expect(url).toBe("http://backend.test/admin/events/g-1/void");
  });

  it("reverseEvent -> POST /admin/events/{id}/reverse", async () => {
    await reverseEvent("g-1", { justification: "x" });
    const [url] = fetchSpy.mock.calls[0] as [string];
    expect(url).toBe("http://backend.test/admin/events/g-1/reverse");
  });
});

describe("two-step confirm flag passes through the body", () => {
  it("confirm:false (preview)", async () => {
    await resolveEvent("g-1", {
      winning_outcome_id: "o-1",
      justification: "x",
      confirm: false,
    });
    const [, init] = fetchSpy.mock.calls[0] as [string, RequestInit | undefined];
    expect(JSON.parse(init?.body as string)).toEqual({
      winning_outcome_id: "o-1",
      justification: "x",
      confirm: false,
    });
  });

  it("confirm:true (execute)", async () => {
    await resolveEvent("g-1", {
      winning_outcome_id: "o-1",
      justification: "x",
      confirm: true,
    });
    const [, init] = fetchSpy.mock.calls[0] as [string, RequestInit | undefined];
    expect(JSON.parse(init?.body as string).confirm).toBe(true);
  });
});

describe("Bearer header + 423 edit-lock", () => {
  it("forwards Authorization: Bearer admin_jwt", async () => {
    await createEvent({
      title: "x",
      deadline: "2099-01-01T00:00:00Z",
      outcomes: TWO_OUTCOMES,
    });
    const [, init] = fetchSpy.mock.calls[0] as [string, RequestInit | undefined];
    expect(init?.headers).toMatchObject({
      "Content-Type": "application/json",
      Authorization: "Bearer test-admin-jwt",
    });
  });

  it("a 423 PATCH rejects and is recognized as EVENT_LOCKED", async () => {
    fetchSpy.mockResolvedValue(new Response("locked", { status: 423 }));
    const err = await updateEvent("g-1", { outcomes: TWO_OUTCOMES }).catch(
      (e) => e,
    );
    expect(err).toBeInstanceOf(Error);
    expect(isEventLockedError(err)).toBe(true);
  });
});
