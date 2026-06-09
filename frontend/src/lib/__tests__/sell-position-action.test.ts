import { describe, it, expect, vi, beforeEach } from "vitest";

const cookieGet = vi.hoisted(() => vi.fn());
vi.mock("next/headers", () => ({ cookies: vi.fn(async () => ({ get: cookieGet })) }));
vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));

import { sellPositionAction } from "@/lib/bet-actions";

beforeEach(() => {
  cookieGet.mockReset();
  vi.restoreAllMocks();
});

function form(betId: string): FormData {
  const f = new FormData();
  f.set("bet_id", betId);
  return f;
}

describe("sellPositionAction", () => {
  it("returns success with the cash-out amount on 200", async () => {
    cookieGet.mockReturnValue({ value: "tok" });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, json: async () => ({ payout: "64.0000" }) }) as unknown as Response),
    );
    const res = await sellPositionAction({}, form("bet-1"));
    expect(res.success).toBe(true);
    expect(res.message).toContain("64.0000");
  });

  it("maps 409 to an inline not-closable error", async () => {
    cookieGet.mockReturnValue({ value: "tok" });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false, status: 409, json: async () => ({}) }) as unknown as Response),
    );
    const res = await sellPositionAction({}, form("bet-1"));
    expect(res.error).toBeTruthy();
    expect(res.success).toBeUndefined();
  });

  it("requires a session and does not call the backend when signed out", async () => {
    cookieGet.mockReturnValue(undefined);
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const res = await sellPositionAction({}, form("bet-1"));
    expect(res.error).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
