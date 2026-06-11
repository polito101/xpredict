# Live Multi-Table Catalog (`/live` → Cars + Birds) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** xpredict players can reach BOTH live-bets verticals — Cars (bangkok) and Birds (demo) — from `/live`: a table picker at `/live`, one fullscreen widget host per table at `/live/[slug]`, each with the right HUD counter label.

**Architecture:** Frontend-only (the LB-A backend mint `POST /api/live/session` already accepts an optional `table_id`, and `fetchLiveSession(session, tableId?)` already forwards it). A server-only env var `LIVEBETS_TABLES` (JSON) defines the catalog (slug/label/tableId). `/live` shows a picker when the catalog is non-empty (keeps the chrome — no widget on that page) and keeps today's single-default-table fullscreen behavior when it's empty. A new dynamic route `/live/[slug]` mints the session for the slug's table and renders the Plan D fullscreen host, passing the catalog label to the widget's `counter-label` attribute (added to the widget today — text-only, no teardown). Shared page internals (shell/balance/skeleton/fullscreen host) move to a non-route module so both pages reuse them.

**Tech Stack:** Next.js 16 App Router (async Server Components, `params` is a Promise), React 19, Tailwind, vitest 2 + RTL + jsdom.

**Working directory:** the xpredict repo — git commands in the worktree root, npm commands in its `frontend\` subdir. Windows + PowerShell.

---

## Design decisions (locked)

1. **Catalog source = server-only env `LIVEBETS_TABLES`**, JSON array: `[{"slug":"cars","label":"Cars","tableId":"<uuid>"},{"slug":"birds","label":"Birds","tableId":"<uuid>"}]`. No `NEXT_PUBLIC_` prefix — read at SSR runtime (works with runtime env in the standalone Docker image; no rebuild needed to change tables). Invalid/missing env → empty catalog → today's behavior, byte-compatible.
2. **Non-empty catalog (≥1 entry) → `/live` is a picker** (uniform rule, no special 1-entry case). Empty catalog → `/live` keeps the current mint-default-table fullscreen flow exactly.
3. **Picker keeps the chrome** (LiveShell + BalanceHeader): there is no widget on it, so the balance is NOT a duplicate there (same rationale as the empty state in Plan D). A balance read failure does not block the picker — it just hides the header (no misleading zero).
4. **`/live/[slug]`**: unknown slug → `notFound()`. Session mint failure → `RetryError` (a 400/`LiveTableUnconfigured` with an explicit table_id is a misconfigured catalog → generic retry error, not the friendly empty state). Happy path → the exact Plan D fullscreen overlay with `counter-label` set from the catalog label.
5. **Shared internals move to `frontend/src/app/live/shared.tsx`** (a non-route module — App Router page files must not export extra symbols): `PAGE_SHELL`, `LiveSkeleton`, `LiveShell`, `BalanceHeader`, `loadBalance`, `LiveFullscreenHost`. Pure extraction, no behavior change; existing tests are the gate.
6. **`counter-label` flows as a React prop** `counterLabel?: string` on `<LiveTable>` → own `useEffect` → `setAttribute`/`removeAttribute`. The widget's Branch E is text-only/no-teardown, so this can never disturb WS/HLS. Absent prop → attribute absent → widget's neutral `COUNT` default.
7. **Prod wiring**: `docker-compose.prod.yml` passes `LIVEBETS_TABLES: ${LIVEBETS_TABLES:-}` to the frontend service; `.env.prod.example` documents it. The actual VM `.env.prod` value is set at deploy time (NOT in the repo).

---

### Task 1: Branch setup + clean baseline

**Files:** none (git/npm only)

- [ ] **Step 1: Worktree + branch off main**

If executing inside an isolated worktree created via superpowers:using-git-worktrees, the worktree IS the branch. Otherwise:

```powershell
git -C <repo> checkout main
git -C <repo> pull
git -C <repo> checkout -b feat/live-multi-table-catalog
```

Branch name: `feat/live-multi-table-catalog`, base `main` (≥ `b446799`).

- [ ] **Step 2: Install + baseline**

```powershell
cd <worktree>\frontend
npm install
npm run test
```

Expected: full suite green (42 files / 251 tests at `b446799`). If not green, STOP and report.

---

### Task 2: `live-catalog.ts` — parse `LIVEBETS_TABLES` (TDD)

**Files:**
- Create: `frontend/src/lib/live-catalog.ts`
- Test: `frontend/src/lib/__tests__/live-catalog.test.ts`  (`.ts` → runs under the node vitest environment)

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/lib/__tests__/live-catalog.test.ts`:

```ts
/**
 * `LIVEBETS_TABLES` catalog parsing (live multi-table). Server-only env (no
 * NEXT_PUBLIC) read at request time; malformed input must NEVER throw — it
 * degrades to an empty catalog so /live falls back to the single-default-table
 * flow.
 */
import { describe, it, expect, vi, afterEach } from "vitest";

import { getLiveCatalog, findLiveTable } from "@/lib/live-catalog";

const VALID = JSON.stringify([
  { slug: "cars", label: "Cars", tableId: "f90e010d-4540-42d2-8c7f-bade3543fe3e" },
  { slug: "birds", label: "Birds", tableId: "c4138d9f-6333-4d18-bc09-cffe08e2358a" },
]);

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("getLiveCatalog", () => {
  it("returns [] when LIVEBETS_TABLES is unset", () => {
    vi.stubEnv("LIVEBETS_TABLES", "");
    expect(getLiveCatalog()).toEqual([]);
  });

  it("parses a valid two-entry catalog in order", () => {
    vi.stubEnv("LIVEBETS_TABLES", VALID);
    expect(getLiveCatalog()).toEqual([
      { slug: "cars", label: "Cars", tableId: "f90e010d-4540-42d2-8c7f-bade3543fe3e" },
      { slug: "birds", label: "Birds", tableId: "c4138d9f-6333-4d18-bc09-cffe08e2358a" },
    ]);
  });

  it("returns [] (and warns) on invalid JSON — never throws", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.stubEnv("LIVEBETS_TABLES", "{not json");
    expect(getLiveCatalog()).toEqual([]);
    expect(warn).toHaveBeenCalled();
  });

  it("returns [] when the JSON is not an array", () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.stubEnv("LIVEBETS_TABLES", JSON.stringify({ slug: "cars" }));
    expect(getLiveCatalog()).toEqual([]);
  });

  it("drops malformed entries (bad slug chars, empty label, missing tableId) and keeps valid ones", () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.stubEnv(
      "LIVEBETS_TABLES",
      JSON.stringify([
        { slug: "CARS!", label: "Bad slug", tableId: "x" },
        { slug: "ok", label: "  ", tableId: "x" },
        { slug: "ok2", label: "Ok", tableId: "" },
        { slug: "birds", label: "Birds", tableId: "t-1" },
      ]),
    );
    expect(getLiveCatalog()).toEqual([{ slug: "birds", label: "Birds", tableId: "t-1" }]);
  });

  it("drops duplicate slugs (first wins)", () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.stubEnv(
      "LIVEBETS_TABLES",
      JSON.stringify([
        { slug: "cars", label: "First", tableId: "t-1" },
        { slug: "cars", label: "Second", tableId: "t-2" },
      ]),
    );
    expect(getLiveCatalog()).toEqual([{ slug: "cars", label: "First", tableId: "t-1" }]);
  });
});

describe("findLiveTable", () => {
  it("finds an entry by slug", () => {
    vi.stubEnv("LIVEBETS_TABLES", VALID);
    expect(findLiveTable("birds")?.label).toBe("Birds");
  });

  it("returns undefined for an unknown slug", () => {
    vi.stubEnv("LIVEBETS_TABLES", VALID);
    expect(findLiveTable("nope")).toBeUndefined();
  });
});
```

- [ ] **Step 2: Run — verify it fails**

```powershell
npm run test -- src/lib/__tests__/live-catalog.test.ts
```

Expected: FAIL — module `@/lib/live-catalog` not found.

- [ ] **Step 3: Implement**

Create `frontend/src/lib/live-catalog.ts`:

```ts
/**
 * Live-bets multi-table catalog (live multi-table plan, 2026-06-11).
 *
 * SERVER-ONLY: parses the `LIVEBETS_TABLES` env var (no `NEXT_PUBLIC_` prefix,
 * so it is read at request time on the server and never baked into the client
 * bundle — table changes need an env edit + container recreate, NOT a rebuild).
 *
 * Shape: JSON array of `{ slug, label, tableId }`:
 *   [{"slug":"cars","label":"Cars","tableId":"<uuid>"},
 *    {"slug":"birds","label":"Birds","tableId":"<uuid>"}]
 *
 * Contract: malformed input NEVER throws. Bad JSON / non-array → empty catalog
 * (the `/live` page then falls back to the single-default-table flow, exactly
 * the pre-catalog behavior). Malformed entries and duplicate slugs are dropped
 * with a console.warn (first occurrence of a slug wins).
 */

export interface LiveCatalogEntry {
  /** URL segment for /live/[slug] — lowercase, [a-z0-9-], 1..32 chars. */
  slug: string;
  /** Human label: picker card title AND the widget HUD `counter-label`. */
  label: string;
  /** live-bets table UUID, forwarded to LB-A `POST /api/live/session`. */
  tableId: string;
}

const SLUG_RE = /^[a-z0-9-]{1,32}$/;

export function getLiveCatalog(): LiveCatalogEntry[] {
  const raw = process.env.LIVEBETS_TABLES;
  if (!raw) return [];

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    console.warn("LIVEBETS_TABLES is not valid JSON — ignoring the catalog.");
    return [];
  }
  if (!Array.isArray(parsed)) {
    console.warn("LIVEBETS_TABLES must be a JSON array — ignoring the catalog.");
    return [];
  }

  const entries: LiveCatalogEntry[] = [];
  const seen = new Set<string>();
  for (const item of parsed) {
    const o = item as Record<string, unknown> | null;
    const slug = typeof o?.slug === "string" ? o.slug : "";
    const label = typeof o?.label === "string" ? o.label.trim() : "";
    const tableId = typeof o?.tableId === "string" ? o.tableId.trim() : "";
    if (!SLUG_RE.test(slug) || !label || label.length > 40 || !tableId || seen.has(slug)) {
      console.warn(`LIVEBETS_TABLES: dropping malformed/duplicate entry ${JSON.stringify(item)}`);
      continue;
    }
    seen.add(slug);
    entries.push({ slug, label, tableId });
  }
  return entries;
}

export function findLiveTable(slug: string): LiveCatalogEntry | undefined {
  return getLiveCatalog().find((e) => e.slug === slug);
}
```

- [ ] **Step 4: Run — all green**

```powershell
npm run test -- src/lib/__tests__/live-catalog.test.ts
```

Expected: 8 tests PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/lib/live-catalog.ts frontend/src/lib/__tests__/live-catalog.test.ts
git commit -m "feat(live): LIVEBETS_TABLES catalog parser (server-only, never-throw)"
```

Append trailer (own line after a blank line): `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` (same for every commit in this plan).

---

### Task 3: Extract `shared.tsx` (pure refactor — existing tests are the gate)

**Files:**
- Create: `frontend/src/app/live/shared.tsx`
- Modify: `frontend/src/app/live/page.tsx`
- Test: `frontend/src/app/live/__tests__/live-page.test.tsx` (must stay green UNCHANGED)

- [ ] **Step 1: Create `frontend/src/app/live/shared.tsx`**

Move (verbatim bodies, now exported) `PAGE_SHELL`, `CURRENCY`, `getBackendUrl`, `BalanceResult`, `loadBalance`, `LiveSkeleton`, `LiveShell`, `BalanceHeader` out of `page.tsx`, and add `LiveFullscreenHost` (the Plan D overlay, parameterized):

```tsx
/**
 * Shared internals for the /live route family (live multi-table plan).
 *
 * App Router page files must not export extra symbols, so everything reused by
 * BOTH `/live/page.tsx` and `/live/[slug]/page.tsx` lives here: the page shell,
 * skeleton, balance header, the server-side wallet-balance read, and the Plan D
 * fullscreen widget host. Bodies are verbatim moves from the pre-catalog
 * `page.tsx` — behavior-preserving by construction.
 *
 * Money is a STRING on the wire (SP-1) — never parsed to a float.
 */
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

import { LiveTable } from "./live-table";

export const PAGE_SHELL = "w-full max-w-6xl mx-auto px-4 sm:px-6 py-12";
const CURRENCY = "PLAY_USD";

/**
 * Server-only backend base for the cookie-forwarded wallet-balance read (mirrors
 * `wallet/page.tsx:53-55`). No `NEXT_PUBLIC_` prefix, so the backend origin never
 * leaks into the client bundle.
 */
function getBackendUrl(): string {
  return process.env.BACKEND_URL || "http://localhost:8000";
}

export type BalanceResult = { ok: true; balance: string } | { ok: false };

/**
 * Read the player's wallet balance server-side, forwarding the session cookie —
 * REUSES the exact `/wallet/me/balance` mechanism from `wallet/page.tsx:62-90`
 * (`{ balance }`, a string). Returns a discriminated result so pages can keep
 * rendering chrome + a non-silent error rather than a misleading "0".
 */
export async function loadBalance(session: string): Promise<BalanceResult> {
  try {
    const res = await fetch(`${getBackendUrl()}/wallet/me/balance`, {
      headers: { Cookie: `xpredict_session=${session}` },
      cache: "no-store",
    });
    if (!res.ok) return { ok: false };
    const data = (await res.json()) as { balance?: unknown };
    // WR-02: a non-string balance (malformed/garbage body) is a FAILURE, not a
    // real "0" — never fabricate a zero balance.
    if (typeof data.balance !== "string") return { ok: false };
    return { ok: true, balance: data.balance };
  } catch {
    return { ok: false };
  }
}

/** The /live body — loading skeleton shape (header + balance card + widget). */
export function LiveSkeleton() {
  return (
    <main className={PAGE_SHELL}>
      <div className="mb-8 flex flex-col gap-2">
        <Skeleton className="h-9 w-32" />
        <Skeleton className="h-4 w-64" />
      </div>
      <Skeleton className="mb-6 h-20 w-full rounded-xl" />
      <Skeleton className="h-96 w-full rounded-xl" />
    </main>
  );
}

/** Page chrome wrapper shared by the picker + empty + error states. */
export function LiveShell({ children }: { children: React.ReactNode }) {
  return (
    <main className={PAGE_SHELL}>
      <header className="mb-8 flex flex-col gap-1">
        <h1 className="font-display text-3xl font-semibold tracking-tight">
          Live
        </h1>
        <p className="text-sm text-muted-foreground">
          Multiplayer live bets — your XPrediction balance, in real time.
        </p>
      </header>
      {children}
    </main>
  );
}

/** The wallet-balance header card (labelled element mirrors `wallet/page.tsx`). */
export function BalanceHeader({ balance }: { balance: string }) {
  return (
    <Card className="mb-6">
      <CardHeader>
        <CardTitle>
          <span aria-label="wallet balance">{balance}</span>{" "}
          <span className="text-base font-normal text-muted-foreground">
            {CURRENCY}
          </span>
        </CardTitle>
      </CardHeader>
    </Card>
  );
}

/**
 * Plan D (spec §12) fullscreen widget host: a full-viewport black overlay — no
 * LiveShell chrome, no BalanceHeader (the widget HUD shows the balance via
 * HOST-01). It deliberately covers the SiteFrame nav: the widget HUD owns all
 * UI. The wrapper width is clamped to min(100vw, 100dvh·16/9) so the widget's
 * hard-16:9 shadow stage (HUD included) always fits the viewport (letterboxed
 * on black) at any aspect ratio. `counterLabel` names the HUD live counter
 * (catalog label, e.g. "Cars"/"Birds"); absent → the widget's COUNT default.
 */
export function LiveFullscreenHost({
  sessionToken,
  tableId,
  initialBalance,
  counterLabel,
}: {
  sessionToken: string;
  tableId: string;
  initialBalance: string;
  counterLabel?: string;
}) {
  return (
    <main
      data-testid="live-fullscreen"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black"
    >
      <div className="w-full max-w-[min(100vw,calc(100dvh*16/9))]">
        <LiveTable
          sessionToken={sessionToken}
          tableId={tableId}
          initialBalance={initialBalance}
          counterLabel={counterLabel}
        />
      </div>
    </main>
  );
}
```

NOTE: `LiveFullscreenHost` passes `counterLabel` to `<LiveTable>`; the prop is ADDED to `LiveTable` in Task 4. To keep Task 3 self-contained and compiling, Task 3 includes the minimal prop addition in `live-table.tsx` (Step 2c below) WITHOUT the attribute effect (that effect + its tests are Task 4's TDD scope).

- [ ] **Step 2: Slim `page.tsx` to imports**

(a) DELETE from `page.tsx`: `PAGE_SHELL`, `CURRENCY`, `getBackendUrl`, `BalanceResult`, `loadBalance`, `LiveSkeleton`, `LiveShell`, `BalanceHeader` definitions, and the `Skeleton` import; trim the `Card` import to what the empty state still uses (`Card, CardContent, CardHeader, CardTitle`).

(b) ADD the import and swap the happy-path return:

```tsx
import {
  BalanceHeader,
  LiveFullscreenHost,
  LiveShell,
  LiveSkeleton,
  loadBalance,
  PAGE_SHELL,
} from "./shared";
```

and replace the entire Plan D `return (<main data-testid="live-fullscreen" …>…</main>);` block (including its preceding "Plan D (spec §12)" comment — the rationale now lives on `LiveFullscreenHost`) with:

```tsx
  return (
    <LiveFullscreenHost
      sessionToken={session_token}
      tableId={table_id}
      initialBalance={balance}
    />
  );
```

The `LiveTable` import in `page.tsx` becomes unused — remove it.

(c) In `frontend/src/app/live/live-table.tsx`, extend the props interface ONLY (no effect yet):

```tsx
export interface LiveTableProps {
  sessionToken: string;
  tableId: string;
  initialBalance: string;
  /** Names the widget HUD live counter (catalog label); absent → widget COUNT default. */
  counterLabel?: string;
}
```

and the destructuring: `export function LiveTable({ sessionToken, tableId, initialBalance, counterLabel }: LiveTableProps) {` — with `void counterLabel;` as the first statement of the function body (placeholder so lint passes until Task 4 wires it; Task 4 DELETES the `void` line).

- [ ] **Step 3: Run the live suites — UNCHANGED tests must stay green**

```powershell
npm run test -- src/app/live/__tests__/
npm run typecheck
```

Expected: live-page 5 + live-table 16 PASS with zero test-file edits; tsc clean. If a test fails, the refactor changed behavior — fix the refactor, not the test.

- [ ] **Step 4: Commit**

```powershell
git add frontend/src/app/live/shared.tsx frontend/src/app/live/page.tsx frontend/src/app/live/live-table.tsx
git commit -m "refactor(live): extract shared shell/balance/fullscreen-host for the route family"
```

---

### Task 4: `counterLabel` prop → `counter-label` attribute (TDD)

**Files:**
- Modify: `frontend/src/app/live/live-table.tsx`
- Test: `frontend/src/app/live/__tests__/live-table.test.tsx`

- [ ] **Step 1: Write the failing tests**

Add at the end of the `describe("<LiveTable /> DOM-event wiring", …)` block:

```tsx
  it("multi-table: counterLabel prop is pushed onto the widget `counter-label` attribute", () => {
    const { container } = render(
      <LiveTable
        sessionToken="t"
        tableId="tbl"
        initialBalance="100.0000"
        counterLabel="Birds"
      />,
    );
    expect(getHost(container).getAttribute("counter-label")).toBe("Birds");
  });

  it("multi-table: no counterLabel prop → no `counter-label` attribute (widget COUNT default)", () => {
    const { container } = render(
      <LiveTable sessionToken="t" tableId="tbl" initialBalance="100.0000" />,
    );
    expect(getHost(container).getAttribute("counter-label")).toBeNull();
  });
```

- [ ] **Step 2: Run — verify the first fails**

```powershell
npm run test -- src/app/live/__tests__/live-table.test.tsx
```

Expected: the "pushed onto" test FAILS (attribute null); the "no prop" test PASSES; the other 16 PASS.

- [ ] **Step 3: Implement**

In `live-table.tsx`: DELETE the `void counterLabel;` placeholder from Task 3, and add this effect right AFTER the balance-push effect (the one with the CR-01 comment block):

```tsx
  // Multi-table: name the widget HUD live counter from the catalog label.
  // `counter-label` is the widget's Branch E — text-only render, NO teardown
  // (mirrors balance Branch D) — so this effect can never disturb WS/HLS.
  // Absent prop → attribute removed → the widget's neutral COUNT default.
  useEffect(() => {
    const el = elementRef.current;
    if (!el) return;
    if (counterLabel) {
      el.setAttribute("counter-label", counterLabel);
    } else {
      el.removeAttribute("counter-label");
    }
  }, [counterLabel]);
```

- [ ] **Step 4: Run — all green**

```powershell
npm run test -- src/app/live/__tests__/live-table.test.tsx
```

Expected: 18 PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/app/live/live-table.tsx frontend/src/app/live/__tests__/live-table.test.tsx
git commit -m "feat(live): counterLabel prop drives the widget counter-label attribute"
```

---

### Task 5: `/live` picker when the catalog is configured (TDD)

**Files:**
- Modify: `frontend/src/app/live/page.tsx`
- Test: `frontend/src/app/live/__tests__/live-page.test.tsx`

- [ ] **Step 1: Mock the catalog module + write the failing tests**

In `live-page.test.tsx`, add a hoisted catalog mock next to the existing mocks (the DEFAULT must be an empty catalog so all five existing tests keep exercising the single-default-table flow unchanged):

```tsx
// Catalog: default EMPTY (single-default-table flow); picker tests override.
const getLiveCatalog = vi.hoisted(() => vi.fn().mockReturnValue([]));
vi.mock("@/lib/live-catalog", () => ({
  getLiveCatalog,
  findLiveTable: (slug: string) =>
    getLiveCatalog().find((e: { slug: string }) => e.slug === slug),
}));
```

Add to `beforeEach`: `getLiveCatalog.mockReturnValue([]);`

Then add new tests at the end of the describe block:

```tsx
  it("multi-table: configured catalog → picker with one link per table, chrome + balance, NO widget", async () => {
    cookieGet.mockReturnValue({ value: "test-session" });
    getLiveCatalog.mockReturnValue([
      { slug: "cars", label: "Cars", tableId: "t-cars" },
      { slug: "birds", label: "Birds", tableId: "t-birds" },
    ]);
    stubBalance("100.0000");

    await renderLive();

    // One link per catalog entry, pointing at the slug route.
    expect(screen.getByRole("link", { name: /cars/i })).toHaveAttribute(
      "href",
      "/live/cars",
    );
    expect(screen.getByRole("link", { name: /birds/i })).toHaveAttribute(
      "href",
      "/live/birds",
    );
    // Chrome + balance (no widget on this page → not a duplicate).
    expect(screen.getByLabelText(/wallet balance/i)).toHaveTextContent("100.0000");
    // No session mint, no widget host, no fullscreen overlay.
    expect(fetchLiveSession).not.toHaveBeenCalled();
    expect(screen.queryByTestId("live-table-island")).not.toBeInTheDocument();
    expect(screen.queryByTestId("live-fullscreen")).not.toBeInTheDocument();
  });

  it("multi-table: picker still renders when the balance read fails (no misleading zero, no block)", async () => {
    cookieGet.mockReturnValue({ value: "test-session" });
    getLiveCatalog.mockReturnValue([
      { slug: "cars", label: "Cars", tableId: "t-cars" },
    ]);
    stubBalance(null);

    await renderLive();

    expect(screen.getByRole("link", { name: /cars/i })).toBeInTheDocument();
    expect(screen.queryByLabelText(/wallet balance/i)).not.toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });
```

- [ ] **Step 2: Run — verify the new tests fail**

```powershell
npm run test -- src/app/live/__tests__/live-page.test.tsx
```

Expected: the two `multi-table:` tests FAIL (no links rendered — the page minted a session instead); the original 5 PASS.

- [ ] **Step 3: Implement the picker branch in `page.tsx`**

(a) Add imports:

```tsx
import Link from "next/link";

import { getLiveCatalog, type LiveCatalogEntry } from "@/lib/live-catalog";
```

(b) Add the picker component (module level, above `LiveBody`):

```tsx
/**
 * Multi-table picker (catalog configured): one card per live table, linking to
 * /live/[slug]. Chrome + balance stay — there is no widget on this page, so the
 * balance header is NOT a duplicate (same rationale as the empty state).
 */
function LiveCatalogPicker({
  entries,
  balance,
}: {
  entries: LiveCatalogEntry[];
  balance: string | null;
}) {
  return (
    <LiveShell>
      {balance !== null && <BalanceHeader balance={balance} />}
      <div className="grid gap-4 sm:grid-cols-2">
        {entries.map((e) => (
          <Link
            key={e.slug}
            href={`/live/${e.slug}`}
            className="group rounded-xl focus-visible:outline-2 focus-visible:outline-offset-2"
          >
            <Card className="h-full transition-colors group-hover:border-[--brand-primary]">
              <CardHeader>
                <CardTitle>{e.label}</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm leading-relaxed text-muted-foreground">
                  Multiplayer live table — join the round and bet in real time.
                </p>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </LiveShell>
  );
}
```

(c) In `LiveBody`, right AFTER the auth gate (the `if (!session) { … }` block) and BEFORE the `Promise.allSettled`, add:

```tsx
  // Multi-table: a configured catalog turns /live into a picker — no session
  // mint here (each /live/[slug] page mints for its own table). Empty catalog
  // → the original single-default-table flow below, unchanged.
  const catalog = getLiveCatalog();
  if (catalog.length > 0) {
    const balanceResult = await loadBalance(session);
    return (
      <LiveCatalogPicker
        entries={catalog}
        balance={balanceResult.ok ? balanceResult.balance : null}
      />
    );
  }
```

(d) Update the file-top docstring States list: add a line `- catalog configured → table picker (chrome + balance), links to /live/[slug].` above the existing states.

- [ ] **Step 4: Run — all green**

```powershell
npm run test -- src/app/live/__tests__/live-page.test.tsx
```

Expected: 7 PASS (5 original + 2 new).

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/app/live/page.tsx frontend/src/app/live/__tests__/live-page.test.tsx
git commit -m "feat(live): /live becomes a table picker when LIVEBETS_TABLES is configured"
```

---

### Task 6: `/live/[slug]` fullscreen host per table (TDD)

**Files:**
- Create: `frontend/src/app/live/[slug]/page.tsx`
- Test: `frontend/src/app/live/__tests__/live-slug-page.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/app/live/__tests__/live-slug-page.test.tsx`:

```tsx
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
```

- [ ] **Step 2: Run — verify it fails**

```powershell
npm run test -- src/app/live/__tests__/live-slug-page.test.tsx
```

Expected: FAIL — module `../[slug]/page` not found.

- [ ] **Step 3: Implement `frontend/src/app/live/[slug]/page.tsx`**

```tsx
/**
 * `/live/[slug]` — fullscreen widget host for ONE catalog table (live
 * multi-table plan). Resolves the slug against `LIVEBETS_TABLES`
 * (`findLiveTable`), mints the live-bets session FOR THAT TABLE
 * (`fetchLiveSession(session, tableId)` → LB-A `POST /api/live/session`
 * `{table_id}`), and renders the Plan D fullscreen overlay with the catalog
 * label as the widget HUD `counter-label`.
 *
 * States (mirrors /live):
 *   - unknown slug          → notFound() (404).
 *   - no session cookie     → SignedOutNotice.
 *   - mint failure          → non-silent RetryError (an explicit-table 400 is a
 *     misconfigured catalog, NOT the friendly unconfigured empty state).
 *   - balance read failure  → non-silent RetryError (no fake "0").
 *   - success               → full-viewport overlay (widget HUD owns all UI).
 */
import { Suspense } from "react";
import { cookies } from "next/headers";
import { notFound } from "next/navigation";

import { fetchLiveSession } from "@/lib/api";
import { findLiveTable } from "@/lib/live-catalog";
import { RetryError } from "@/components/retry-error";
import { SignedOutNotice } from "@/components/signed-out-notice";
import {
  LiveFullscreenHost,
  LiveShell,
  LiveSkeleton,
  loadBalance,
  PAGE_SHELL,
} from "../shared";

async function LiveSlugBody({ slug }: { slug: string }) {
  const entry = findLiveTable(slug);
  if (!entry) notFound();

  // Auth gate: cookie presence only — the value never crosses into client JS.
  const store = await cookies();
  const session = store.get("xpredict_session")?.value;
  if (!session) {
    return (
      <main className={PAGE_SHELL}>
        <header className="mb-8 flex flex-col gap-1">
          <h1 className="font-display text-3xl font-semibold tracking-tight">
            {entry.label}
          </h1>
          <p className="text-sm text-muted-foreground">
            Multiplayer live bets with your XPrediction balance.
          </p>
        </header>
        <SignedOutNotice resource="live" />
      </main>
    );
  }

  // SP-5: mint for THIS table + read the balance in parallel.
  const [sessionResult, balanceResult] = await Promise.allSettled([
    fetchLiveSession(session, entry.tableId),
    loadBalance(session),
  ]);

  const balance =
    balanceResult.status === "fulfilled" && balanceResult.value.ok
      ? balanceResult.value.balance
      : null;

  // Any mint failure here (including a 400 on an explicit table_id — that is a
  // misconfigured catalog, not the LB-B "unconfigured" demo state) → retry error.
  if (sessionResult.status === "rejected") {
    return (
      <LiveShell>
        <RetryError
          title="We couldn't load the live table"
          message="The live-bets service didn't respond. Please try again."
        />
      </LiveShell>
    );
  }

  if (balance === null) {
    return (
      <LiveShell>
        <RetryError
          title="We couldn't load your balance"
          message="The balance service didn't respond. Your funds are safe — please try again."
        />
      </LiveShell>
    );
  }

  const { session_token, table_id } = sessionResult.value;
  return (
    <LiveFullscreenHost
      sessionToken={session_token}
      tableId={table_id}
      initialBalance={balance}
      counterLabel={entry.label}
    />
  );
}

export default async function LiveSlugPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  return (
    <Suspense fallback={<LiveSkeleton />}>
      <LiveSlugBody slug={slug} />
    </Suspense>
  );
}
```

- [ ] **Step 4: Run — all green**

```powershell
npm run test -- src/app/live/__tests__/live-slug-page.test.tsx
npm run test -- src/app/live/__tests__/
```

Expected: 5 new PASS; whole live family green (live-page 7, live-table 18, live-slug 5).

- [ ] **Step 5: Commit**

```powershell
git add "frontend/src/app/live/[slug]/page.tsx" frontend/src/app/live/__tests__/live-slug-page.test.tsx
git commit -m "feat(live): /live/[slug] fullscreen host per catalog table"
```

---

### Task 7: Prod wiring + full gates + PR

**Files:**
- Modify: `docker-compose.prod.yml`
- Modify: `.env.prod.example`

- [ ] **Step 1: Pass the env through the prod compose**

In `docker-compose.prod.yml`, find the `frontend:` service's `environment:` block (it already carries `BACKEND_URL: http://backend:8000`) and add:

```yaml
      # Live multi-table catalog (server-only; empty → single default table).
      LIVEBETS_TABLES: ${LIVEBETS_TABLES:-}
```

- [ ] **Step 2: Document in `.env.prod.example`**

Next to the existing `NEXT_PUBLIC_LIVEBETS_WIDGET_SRC` block, add:

```dotenv
# Live multi-table catalog (frontend, server-only — NOT baked at build time).
# JSON array of {slug,label,tableId}. Empty/unset → /live uses the single
# LIVEBETS_DEFAULT_TABLE_ID flow. Example:
# LIVEBETS_TABLES='[{"slug":"cars","label":"Cars","tableId":"<cars-table-uuid>"},{"slug":"birds","label":"Birds","tableId":"<birds-table-uuid>"}]'
LIVEBETS_TABLES=
```

- [ ] **Step 3: Full gates**

```powershell
cd <worktree>\frontend
npm run test
npm run lint
npm run typecheck
npm run build
```

Expected: full suite green (now ~260 tests), lint 0 errors, tsc clean, production build OK (the `[slug]` route appears in the route list).

- [ ] **Step 4: Commit + push + PR**

```powershell
git add docker-compose.prod.yml .env.prod.example
git commit -m "chore(deploy): LIVEBETS_TABLES passthrough for the live multi-table catalog"
git push -u origin feat/live-multi-table-catalog
gh pr create --repo polito101/xpredict --base main --head feat/live-multi-table-catalog --title "feat(live): multi-table catalog — Cars + Birds from /live" --body "Frontend-only: server-only LIVEBETS_TABLES JSON env defines the live-table catalog (slug/label/tableId; malformed input degrades to empty, never throws). Non-empty catalog turns /live into a picker (chrome + balance — no widget there, so no duplicate); /live/[slug] mints the session FOR that table (fetchLiveSession already forwards table_id; zero backend changes) and renders the Plan D fullscreen host with the catalog label on the widget's counter-label attribute. Empty catalog → today's single-default-table flow, byte-compatible (original page tests unchanged). Shared shell/balance/fullscreen-host extracted to app/live/shared.tsx (pure refactor). Tests: live-catalog 8, live-page 7 (5 original untouched + 2 picker), live-slug 5, live-table 18 (2 new). Full suite + lint + typecheck + build green. Prod: compose passes LIVEBETS_TABLES through to the frontend service (runtime env — table changes need no rebuild)."
```

---

## Deploy note (NOT part of this repo's tasks — controller runs it on the VM after merge)

On the VM: add to `~/xpredict/.env.prod` →
`LIVEBETS_TABLES='[{"slug":"cars","label":"Cars","tableId":"f90e010d-4540-42d2-8c7f-bade3543fe3e"},{"slug":"birds","label":"Birds","tableId":"c4138d9f-6333-4d18-bc09-cffe08e2358a"}]'`
then `git pull`, `$C build frontend`, `$C up -d frontend`. The cars table additionally needs its grown clip pool + bucket seed + ACTIVE status (separate data workstream) before its rounds open.

## Spec coverage map

| Requirement | Where |
|---|---|
| Reach BOTH verticals from xpredict | Task 5 picker + Task 6 slug hosts |
| Per-table session mint | Task 6 (`fetchLiveSession(session, entry.tableId)`) — backend already supports it |
| Correct HUD label per vertical | Task 4 prop→attribute + Task 6 `counterLabel={entry.label}` |
| No regression when catalog unset | Task 2 never-throw parse + Task 5 default-mock keeps the original 5 page tests green |
| Prod configurability without rebuild | server-only env, Task 7 compose passthrough |
