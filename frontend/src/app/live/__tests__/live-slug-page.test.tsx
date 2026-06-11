/**
 * `/live/[slug]` Server Component tests (live multi-table). Mirrors
 * `live-page.test.tsx` mechanics: mocked cookies()/api/catalog, stubbed island,
 * async body awaited through the Suspense wrapper. `notFound()` is asserted via
 * next/navigation's mock throwing a sentinel.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

const cookieGet = vi.hoisted(() =>
  vi.fn<(name: string) => { value: string } | undefined>(),
);
vi.mock("next/headers", () => ({
  cookies: vi.fn(async () => ({ get: cookieGet })),
}));

const NOT_FOUND = vi.hoisted(() => new Error("NEXT_NOT_FOUND_SENTINEL"));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
  notFound: vi.fn(() => {
    throw NOT_FOUND;
  }),
}));

const fetchLiveSession = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, fetchLiveSession };
});

const getLiveCatalog = vi.hoisted(() =>
  vi.fn().mockReturnValue([
    { slug: "cars", label: "Cars", tableId: "t-cars" },
    { slug: "birds", label: "Birds", tableId: "t-birds" },
  ]),
);
vi.mock("@/lib/live-catalog", () => ({
  getLiveCatalog,
  findLiveTable: (slug: string) =>
    getLiveCatalog().find((e: { slug: string }) => e.slug === slug),
}));

// Stub the island; the marker carries counter-label so the handoff is assertable.
vi.mock("@/app/live/live-table", () => ({
  LiveTable: ({
    sessionToken,
    tableId,
    initialBalance,
    counterLabel,
  }: {
    sessionToken: string;
    tableId: string;
    initialBalance: string;
    counterLabel?: string;
  }) => (
    <div
      data-testid="live-table-island"
      data-session-token={sessionToken}
      data-table-id={tableId}
      data-initial-balance={initialBalance}
      data-counter-label={counterLabel ?? ""}
    />
  ),
}));

import LiveSlugPage from "../[slug]/page";

/** Render the page's async body for a slug, awaited (mirrors live-page.test.tsx). */
async function renderSlug(slug: string) {
  const suspense = (await LiveSlugPage({
    params: Promise.resolve({ slug }),
  })) as React.ReactElement<{ children: React.ReactElement }>;
  const bodyEl = suspense.props.children;
  const Body = bodyEl.type as (props: object) => Promise<React.ReactElement>;
  render(await Body(bodyEl.props as object));
}

function stubBalance(balance: string | null) {
  const fetchMock = vi.fn(async () =>
    balance === null
      ? ({ ok: false, status: 503, json: async () => ({}) } as unknown as Response)
      : ({ ok: true, json: async () => ({ balance }) } as unknown as Response),
  );
  vi.stubGlobal("fetch", fetchMock);
}

beforeEach(() => {
  cookieGet.mockReset();
  fetchLiveSession.mockReset();
  vi.unstubAllGlobals();
});

describe("LiveSlugPage (/live/[slug])", () => {
  it("unknown slug → notFound()", async () => {
    cookieGet.mockReturnValue({ value: "test-session" });
    stubBalance("100.0000");

    await expect(renderSlug("nope")).rejects.toThrow("NEXT_NOT_FOUND_SENTINEL");
    expect(fetchLiveSession).not.toHaveBeenCalled();
  });

  it("signed out → SignedOutNotice, no mint", async () => {
    cookieGet.mockReturnValue(undefined);
    stubBalance("100.0000");

    await renderSlug("cars");

    expect(screen.getByText(/sign in/i)).toBeInTheDocument();
    expect(fetchLiveSession).not.toHaveBeenCalled();
  });

  it("happy path: mints for the slug's table, fullscreen overlay, counter-label = catalog label", async () => {
    cookieGet.mockReturnValue({ value: "test-session" });
    fetchLiveSession.mockResolvedValue({
      session_token: "live-token-9",
      expires_at: "2026-06-06T10:00:00Z",
      table_id: "t-cars",
    });
    stubBalance("100.0000");

    await renderSlug("cars");

    expect(fetchLiveSession).toHaveBeenCalledWith("test-session", "t-cars");
    const island = screen.getByTestId("live-table-island");
    expect(island).toHaveAttribute("data-session-token", "live-token-9");
    expect(island).toHaveAttribute("data-table-id", "t-cars");
    expect(island).toHaveAttribute("data-initial-balance", "100.0000");
    expect(island).toHaveAttribute("data-counter-label", "Cars");
    const overlay = screen.getByTestId("live-fullscreen");
    expect(overlay.className).toContain("fixed");
    expect(overlay.contains(island)).toBe(true);
    expect(screen.queryByLabelText(/wallet balance/i)).not.toBeInTheDocument();
  });

  it("session mint failure → non-silent RetryError", async () => {
    cookieGet.mockReturnValue({ value: "test-session" });
    fetchLiveSession.mockRejectedValue(new Error("live-bets 502"));
    stubBalance("100.0000");

    await renderSlug("birds");

    expect(screen.getByRole("alert")).toHaveTextContent(/couldn't load the live table/i);
    expect(screen.queryByTestId("live-table-island")).not.toBeInTheDocument();
  });

  it("balance read failure → non-silent RetryError (no fake 0)", async () => {
    cookieGet.mockReturnValue({ value: "test-session" });
    fetchLiveSession.mockResolvedValue({
      session_token: "live-token-9",
      expires_at: "2026-06-06T10:00:00Z",
      table_id: "t-birds",
    });
    stubBalance(null);

    await renderSlug("birds");

    expect(screen.getByRole("alert")).toHaveTextContent(/couldn't load your balance/i);
    expect(screen.queryByTestId("live-table-island")).not.toBeInTheDocument();
  });
});
