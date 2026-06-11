# Plan D — xpredict `/live` Fullscreen Widget Host Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** xpredict's `/live` page becomes a fullscreen host for the live-bets widget — no duplicate balance, no `controls` on the slotted video, widget fills the viewport.

**Architecture:** Render-layer-only change in two files of the xpredict frontend. `page.tsx`'s happy path swaps the `LiveShell` + `BalanceHeader` chrome for a `fixed inset-0` black overlay that letterboxes the 16:9 widget; `live-table.tsx` drops the in-island balance `<div>` and the `controls` attribute, and restyles the slotted `<video>` to mirror the widget's own `::slotted(video)` full-bleed rules. All state, attribute pushes (HOST-01), the four DOM-event listeners, and the CR-01 re-mint behavior are untouched.

**Tech Stack:** Next.js 16 App Router, React 19, Tailwind, vitest 2 + @testing-library/react + jsdom.

**Working directory:** ALL commands run in the **xpredict** repo — `C:\Users\pobom\ProyectosClaude\xpredict` (git) and `C:\Users\pobom\ProyectosClaude\xpredict\frontend` (npm). This plan does NOT touch the live-bets repo.

**Upstream spec:** `live-bets/docs/superpowers/specs/2026-06-10-live-bets-fixed-multiplier-fullscreen-design.md` §11 (stream lock — xpredict line), §12 (xpredict host `/live` fullscreen), §13 (xpredict vitest tests).

---

## Design decisions (locked for this plan)

1. **Only the happy path goes fullscreen.** Signed-out, "no table configured" (empty), session-error, balance-error states and `loading.tsx` keep the existing `PAGE_SHELL` chrome — they have no widget, and full-bleed cards would be broken UX. Spec intent is "give the **widget** the full viewport".
2. **`BalanceHeader` survives as a component** but is removed from the happy path. The empty state keeps it: there is no widget there, so it is not a duplicate, and the LB-B contract ("STILL showing the wallet balance" in the empty state) holds.
3. **The widget already strips `controls` at runtime** (live-bets `widget.js` stream-lock does `videoEl.removeAttribute('controls')`). Removing the attribute host-side is still required by spec §11: it kills the pre-init flash of native controls and covers the widget-script-not-loaded case.
4. **Fullscreen = `fixed inset-0 z-50` overlay.** It covers the xpredict `SiteFrame` nav on purpose — "the widget HUD owns all UI" (155.io posture). The sonner `<Toaster>` stays visible (its own z-index is far higher). Exit is browser back; a host-side exit button is a possible follow-up, NOT in scope.
5. **Letterbox clamp.** The widget's shadow stage is hard 16:9 (`.lb-stage { width:100%; aspect-ratio:16/9 }` in widget.js, not changeable from the host). The host wrapper is `w-full max-w-[min(100vw,calc(100dvh*16/9))]` centered on black — the whole widget (HUD included) always fits the viewport at any aspect ratio. That is the achievable "widget fills viewport" without touching the widget.
6. **Video inline styles mirror the widget's `::slotted(video)` exactly** (`position:absolute; inset:0; width/height:100%; object-fit:cover; background:#000; display:block`). Inline styles beat `::slotted()` on specificity, and Safari iOS ignores `::slotted()` on media elements (same reason live-bets `demo.html` inlines them) — so they must carry the SAME values as the widget's rules, not the old `aspectRatio/borderRadius/contain` set.
7. **`aspect-video` on the island's root div**: pre-upgrade the custom element has no size; the div provides the 16:9 box from the first frame (no layout jump when widget.js initializes, and the absolute-positioned video has a correct offset parent before the shadow stage exists).

---

### Task 1: Branch setup

**Files:** none (git only)

- [ ] **Step 1: Verify clean main and branch off**

Run (note: if executing inside an isolated worktree created via superpowers:using-git-worktrees, the worktree IS the branch — skip the checkout):

```powershell
git -C C:\Users\pobom\ProyectosClaude\xpredict status --short
git -C C:\Users\pobom\ProyectosClaude\xpredict checkout main
git -C C:\Users\pobom\ProyectosClaude\xpredict pull
git -C C:\Users\pobom\ProyectosClaude\xpredict checkout -b feat/plan-d-live-fullscreen-host
```

Expected: empty status, `main` up to date (last known HEAD `657e961`), new branch created.

- [ ] **Step 2: Baseline — confirm the live tests are green before touching anything**

```powershell
cd C:\Users\pobom\ProyectosClaude\xpredict\frontend
npm run test -- src/app/live/__tests__/
```

Expected: 2 files, all tests PASS (live-page: 5, live-table: 14). If not green, STOP and report — do not build on a broken baseline.

---

### Task 2: `live-table.tsx` — drop in-island balance, drop `controls`, full-bleed video (TDD)

**Files:**
- Modify: `frontend/src/app/live/live-table.tsx`
- Test: `frontend/src/app/live/__tests__/live-table.test.tsx`

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/live/__tests__/live-table.test.tsx`:

**(a)** Add two NEW tests at the end of the `describe("<LiveTable /> DOM-event wiring", …)` block (before its closing `});`):

```tsx
  it("Plan D: renders NO in-island balance element — the widget HUD owns it via HOST-01", () => {
    const { container } = render(
      <LiveTable sessionToken="t" tableId="tbl" initialBalance="100.0000" />,
    );
    // The old wallet-balance block is gone from the island…
    expect(
      container.querySelector('[data-testid="live-balance"]'),
    ).toBeNull();
    expect(
      container.querySelector('[aria-label="wallet balance"]'),
    ).toBeNull();
    // …but the balance still reaches the widget as an attribute (HOST-01).
    expect(getHost(container).getAttribute("balance")).toBe("100.0000");
  });

  it("Plan D (stream lock §11): the slotted <video> carries NO `controls` attribute", () => {
    const { container } = render(
      <LiveTable sessionToken="t" tableId="tbl" initialBalance="100.0000" />,
    );
    const video = container.querySelector('video[slot="video"]');
    expect(video).not.toBeNull();
    expect(video!.hasAttribute("controls")).toBe(false);
  });
```

**(b)** REPLACE the existing test `"bet-placed -> recordLivePlaced(betId) + getLiveBalance refresh updates the balance"` (it queries the now-removed `[data-testid="live-balance"]`) with this version that asserts the refresh through the host attribute instead:

```tsx
  it("bet-placed -> recordLivePlaced(betId) + getLiveBalance refresh moves the widget `balance` attribute", async () => {
    const { container } = render(
      <LiveTable sessionToken="t" tableId="tbl" initialBalance="100.0000" />,
    );
    const host = getHost(container);
    expect(host.getAttribute("balance")).toBe("100.0000");

    await fire(host, "live-bets-bet-placed", { bet_id: "B1" });

    expect(actions.recordLivePlaced).toHaveBeenCalledWith("B1");
    // M-2: the in-island balance state is refreshed via getLiveBalance and the
    // HOST-01 push reflects it (the island no longer renders balance text).
    expect(actions.getLiveBalance).toHaveBeenCalledTimes(1);
    expect(host.getAttribute("balance")).toBe("150.0000");
    expect(toast.error).not.toHaveBeenCalled();
  });
```

- [ ] **Step 2: Run the file — verify the new tests fail and the rewrite passes**

```powershell
cd C:\Users\pobom\ProyectosClaude\xpredict\frontend
npm run test -- src/app/live/__tests__/live-table.test.tsx
```

Expected: the two `Plan D:` tests FAIL (`live-balance` element still present; `controls` still set). The rewritten bet-placed test PASSES (the attribute push already works today). All other tests PASS.

- [ ] **Step 3: Implement `live-table.tsx`**

Three edits — state, effects, event wiring, `readBetId`/`readString`, and the module augmentation are all UNTOUCHED:

**(a)** Delete the now-unused currency constant (line ~62):

```tsx
const CURRENCY = "PLAY_USD";
```

**(b)** Replace the component docstring above `LiveTable` (the one starting `/** Client host for the live-bets widget. Renders the wallet balance …`) with:

```tsx
/**
 * Client host for the live-bets widget (Plan D: fullscreen, no in-island
 * balance). The wallet balance is still held in state and refreshed after
 * placed/settled events, but it is ONLY pushed onto the widget's `balance`
 * attribute (HOST-01) — the widget HUD renders it; the island renders nothing.
 * Loads `widget.js` and renders `<live-bets-table>` with `session-token` +
 * `table-id` set via `setAttribute`.
 */
```

**(c)** Replace the entire `return (…)` JSX block (from `return (` through the closing `);`) with:

```tsx
  return (
    // 16:9 box from the first frame: pre-upgrade the custom element has no
    // size; this div keeps the layout stable and gives the absolutely
    // positioned slotted <video> a correct offset parent until the widget's
    // shadow stage (itself 16:9) takes over.
    <div className="relative aspect-video w-full bg-black">
      {/* If the widget src isn't configured, render a non-blocking notice rather
          than an empty `<script src="undefined">` (T-LBB-07). */}
      {widgetSrc ? (
        <Script src={widgetSrc} strategy="afterInteractive" />
      ) : (
        <p
          role="status"
          className="absolute inset-x-4 top-4 z-10 rounded-xl border border-border bg-surface p-4 text-sm text-muted-foreground"
        >
          Live widget not configured.
        </p>
      )}

      {/* CP-12: the widget renders HLS into a light-DOM `<video slot="video">`
          child (NOT its shadow DOM). Inline styles MIRROR the widget's
          `::slotted(video)` rules exactly (absolute full-bleed, cover): inline
          beats ::slotted on specificity and Safari iOS ignores ::slotted on
          media elements. No `controls` — stream lock (§11). */}
      <live-bets-table ref={elementRef}>
        <video
          slot="video"
          autoPlay
          muted
          playsInline
          style={{
            position: "absolute",
            inset: 0,
            width: "100%",
            height: "100%",
            background: "#000",
            display: "block",
            objectFit: "cover",
          }}
        />
      </live-bets-table>
    </div>
  );
```

- [ ] **Step 4: Run the file — all green**

```powershell
npm run test -- src/app/live/__tests__/live-table.test.tsx
```

Expected: ALL 16 tests PASS (14 original, of which 1 rewritten in place, + 2 new).

- [ ] **Step 5: Commit**

```powershell
git -C C:\Users\pobom\ProyectosClaude\xpredict add frontend/src/app/live/live-table.tsx frontend/src/app/live/__tests__/live-table.test.tsx
git -C C:\Users\pobom\ProyectosClaude\xpredict commit -m "feat(live): island drops in-island balance + video controls, full-bleed slotted video (Plan D)"
```

---

### Task 3: `page.tsx` — happy path goes full-viewport, no `BalanceHeader` (TDD)

**Files:**
- Modify: `frontend/src/app/live/page.tsx`
- Test: `frontend/src/app/live/__tests__/live-page.test.tsx`

- [ ] **Step 1: Rewrite the happy-path test**

In `frontend/src/app/live/__tests__/live-page.test.tsx`, REPLACE the test `"shows chrome + wallet balance + the LiveTable island on the happy path"` with:

```tsx
  it("happy path (Plan D): full-viewport host — NO duplicate balance header, island inside the fixed overlay", async () => {
    cookieGet.mockReturnValue({ value: "test-session" });
    fetchLiveSession.mockResolvedValue({
      session_token: "live-token-1",
      expires_at: "2026-06-06T10:00:00Z",
      table_id: "tbl-1",
    });
    stubBalance("100.0000");

    await renderLive();

    // Plan D: the widget HUD owns the balance (HOST-01) — the page renders NO
    // balance header on the happy path (spec §12 "no duplicate balance").
    expect(screen.queryByLabelText(/wallet balance/i)).not.toBeInTheDocument();

    // The island still gets the resolved token/table/balance handoff…
    const island = screen.getByTestId("live-table-island");
    expect(island).toHaveAttribute("data-session-token", "live-token-1");
    expect(island).toHaveAttribute("data-table-id", "tbl-1");
    expect(island).toHaveAttribute("data-initial-balance", "100.0000");

    // …inside the full-viewport overlay (spec §13 "widget fills viewport";
    // jsdom does no layout, so assert the Tailwind fixed-inset classes).
    const overlay = screen.getByTestId("live-fullscreen");
    expect(overlay.className).toContain("fixed");
    expect(overlay.className).toContain("inset-0");
    expect(overlay.contains(island)).toBe(true);
  });
```

ALL other tests in the file stay byte-identical — signed-out, empty state (balance still shown there), generic session error, and WR-02 are unchanged contracts.

- [ ] **Step 2: Run the file — verify the happy-path test fails**

```powershell
cd C:\Users\pobom\ProyectosClaude\xpredict\frontend
npm run test -- src/app/live/__tests__/live-page.test.tsx
```

Expected: the rewritten happy-path test FAILS (a `wallet balance`-labelled header IS in the document; no `live-fullscreen` testid exists). The other 4 tests PASS.

- [ ] **Step 3: Implement `page.tsx`**

Two edits — `PAGE_SHELL`, `LiveShell`, `BalanceHeader`, `LiveSkeleton`, `loadBalance`, the auth gate, the empty state, and both error branches are all UNTOUCHED:

**(a)** Replace the final happy-path `return (…)` of `LiveBody` (the block starting `return (\n    <LiveShell>\n      <BalanceHeader balance={balance} />` through its closing `);`) with:

```tsx
  // Plan D (spec §12): the happy path is a full-viewport black overlay — no
  // LiveShell chrome, no BalanceHeader (the widget HUD shows the balance via
  // HOST-01). It deliberately covers the SiteFrame nav: the widget HUD owns
  // all UI. The wrapper width is clamped to min(100vw, 100dvh·16/9) so the
  // widget's hard-16:9 shadow stage (HUD included) always fits the viewport
  // (letterboxed on black) at any aspect ratio.
  return (
    <main
      data-testid="live-fullscreen"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black"
    >
      <div className="w-full max-w-[min(100vw,calc(100dvh*16/9))]">
        <LiveTable
          sessionToken={session_token}
          tableId={table_id}
          initialBalance={balance}
        />
      </div>
    </main>
  );
```

**(b)** In the file-top docstring, replace the success-state line

```
 *   - success                   → chrome + balance header + the `<LiveTable>` host.
```

with:

```
 *   - success                   → full-viewport overlay + the `<LiveTable>` host
 *     (Plan D: no chrome/balance header — the widget HUD owns all UI).
```

- [ ] **Step 4: Run the file — all green**

```powershell
npm run test -- src/app/live/__tests__/live-page.test.tsx
```

Expected: ALL 5 tests PASS.

- [ ] **Step 5: Commit**

```powershell
git -C C:\Users\pobom\ProyectosClaude\xpredict add frontend/src/app/live/page.tsx frontend/src/app/live/__tests__/live-page.test.tsx
git -C C:\Users\pobom\ProyectosClaude\xpredict commit -m "feat(live): happy path goes full-viewport, drop duplicate BalanceHeader (Plan D)"
```

---

### Task 4: Full gates + PR

**Files:** none (verification + git only)

- [ ] **Step 1: Full frontend gates**

```powershell
cd C:\Users\pobom\ProyectosClaude\xpredict\frontend
npm run test
npm run lint
npm run typecheck
```

Expected: full vitest suite green (42 test files — any failure outside `src/app/live/` is a regression you caused or a dirty baseline: diff against `main` before concluding); eslint clean (watch for the removed `CURRENCY` const — it must be deleted, not left unused); tsc clean.

- [ ] **Step 2: Push + PR**

```powershell
git -C C:\Users\pobom\ProyectosClaude\xpredict push -u origin feat/plan-d-live-fullscreen-host
gh pr create --repo polito101/xpredict --base main --head feat/plan-d-live-fullscreen-host --title "feat(live): Plan D — /live fullscreen widget host" --body "Implements spec §11–§13 (live-bets fixed-multiplier refactor, Plan D): happy path is a full-viewport black overlay (widget HUD owns all UI), in-island balance and BalanceHeader removed from the happy path (HOST-01 attribute push kept; empty state keeps its balance), slotted <video> loses controls and mirrors the widget's ::slotted full-bleed styles. Render-layer only; all 4 DOM-event wirings + CR-01 re-mint untouched.

Tests: live-table 16 green (2 new: no in-island balance, no controls), live-page 5 green (happy path rewritten for the overlay), full suite + lint + typecheck green.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

(Origin already verified: `https://github.com/polito101/xpredict.git`. If the push is rejected for auth, stop and report — do not retry with force.)

---

## Spec coverage map (§13)

| Spec requirement | Where |
|---|---|
| `/live` renders no duplicate balance | Task 2 test (a) — island level; Task 3 test — page level |
| slotted `<video>` has no `controls` | Task 2 test (a, second) + impl (c) |
| widget fills viewport | Task 3 test (fixed/inset-0 classes + containment) + impl (a) |
| §11 xpredict: remove `controls` in `live-table.tsx` | Task 2 impl (c) |
| §12 page.tsx: drop BalanceHeader + `max-w-6xl…py-12` shell on the widget path | Task 3 impl (a) |
| §12 live-table.tsx: keep session/balance pushes + 4 listeners | untouched by design — guarded by the 13 pre-existing live-table tests |
