---
phase: LB-B-frontend-surface
reviewed: 2026-06-06T00:00:00Z
depth: deep
files_reviewed: 10
files_reviewed_list:
  - frontend/src/lib/live-actions.ts
  - frontend/src/app/live/live-table.tsx
  - frontend/src/app/live/page.tsx
  - frontend/src/app/live/loading.tsx
  - frontend/src/lib/api.ts
  - frontend/src/components/player-nav.tsx
  - frontend/.env.example
  - frontend/src/lib/__tests__/live-actions.test.ts
  - frontend/src/app/live/__tests__/live-table.test.tsx
  - frontend/src/app/live/__tests__/live-page.test.tsx
findings:
  critical: 0
  warning: 2
  info: 3
  total: 5
status: resolved
verdict: APPROVE-WITH-NITS
resolution:
  resolved_at: 2026-06-06
  resolved_by: Claude Opus 4.8 (1M context)
  branch: gsd/livebets-demo
  WR-01: resolved   # recordLiveSettled surfaces backend MirrorResult.status; settle toast branches on it, not detail.status
  WR-02: resolved   # loadBalance treats a non-string balance as {ok:false} -> RetryError (no fabricated "0")
  IN-01: resolved   # expires_at dropped from LiveSessionResult (still validated in the 200 branch)
  IN-02: resolved   # dissolved by WR-01 (status no longer read from the untrusted detail for branching)
  IN-03: skipped     # empty-state Card dedupe not done — low-value, avoided over-engineering per scope
---

# Phase LB-B: Frontend surface — Code Review Report

**Reviewed:** 2026-06-06
**Depth:** deep (cross-file: live-actions ↔ live-table ↔ page; frontend ↔ LB-A backend contract `router.py` / `schemas.py` / `service.py`; baselines `bet-actions.ts` / `wallet/page.tsx` / `signed-out-notice.tsx`)
**Files Reviewed:** 10
**Status:** issues_found (no blockers)

## Summary

This is a clean, security-conscious frontend surface that faithfully mirrors the
approved `bet-actions.ts` / `wallet/page.tsx` patterns. The core security
properties the phase is responsible for are all correct and verified:

- **HttpOnly session safety holds.** Every mutation routes through a `"use server"`
  action that reads `cookies().get("xpredict_session")` server-side
  (`live-actions.ts:88-91`) and forwards it as a `Cookie:` header to a **server-only**
  `BACKEND_URL` (no `NEXT_PUBLIC_` prefix — `live-actions.ts:60-62`, `page.tsx:48-50`).
  The cookie value never enters client JS or the browser bundle. The only token
  that reaches the DOM is the short-lived **live-bets** session JWT, which the
  widget legitimately requires (`live-table.tsx:122`, set via `setAttribute`) — that
  is by design and is a different credential from `xpredict_session`.
- **Untrusted widget events are handled correctly.** The DOM-event `detail` is
  treated as attacker-influencable: only `bet_id` is extracted (defensively, via
  `readBetId`, `live-table.tsx:77-83`) and forwarded; the backend (LB-A) re-verifies
  status/stake/payout and enforces ownership. No client-supplied amount or status is
  forwarded as authoritative — confirmed by tracing the action signatures
  (`recordLivePlaced(betId)` / `recordLiveSettled(betId)` take only the id).
- **Idempotency UX is correct.** `applied:false` is a benign no-op success (no error
  toast, no double-credit) — `live-table.tsx:138-143` and the test at
  `live-table.test.tsx:151-162` prove it. 401/404/409 map to sane reasons
  (`reasonForStatus`, `live-actions.ts:68-81`), exercised in `live-actions.test.ts:103-112`.
- **Listener lifecycle is clean.** All four `addEventListener`s are removed in the
  same effect's cleanup (`live-table.tsx:193-198`), with a dedicated unmount/no-refire
  test (`live-table.test.tsx:164-180`).
- **No XSS / injection.** No `dangerouslySetInnerHTML`, no `eval`, no unsanitized
  interpolation; the `next/script` src is `NEXT_PUBLIC_LIVEBETS_WIDGET_SRC` (a build-time
  public widget URL, not user-controlled) with a graceful "not configured" fallback
  (`live-table.tsx:214-223`). `betId` is `encodeURIComponent`'d into the path
  (`live-actions.ts:108,143`), tested at `live-actions.test.ts:80-84`.
- **Error/empty/auth states are non-misleading.** Signed-out → `SignedOutNotice`;
  `LiveTableUnconfigured` → friendly empty state (NOT an error) while still showing
  chrome + balance; any other session failure or a balance-read failure → non-silent
  `RetryError` rather than a misleading "0" (`page.tsx:120-240`). No sensitive info is
  leaked in any error copy.
- **Conventions respected.** Money/odds stay strings end-to-end (SP-1) — the balance
  is rendered verbatim and `getLiveBalance` rejects a non-string balance
  (`live-actions.ts:233`, test `live-actions.test.ts:240-243`). No `any` (the custom
  element is typed via a scoped `React.JSX.IntrinsicElements` augmentation). Brand
  `--brand-*` is used on the nav chrome (`player-nav.tsx:44`).

The test suite is genuinely strong: the money-path action tests assert cookie
forwarding, URL/method, status→result mapping, and the `applied` no-op
(`live-actions.test.ts`); the island tests drive real `CustomEvent`s and verify the
in-island balance actually moves and that listeners are cleaned up.

Findings below are robustness/quality (two WARNINGs, three NITs); none block the demo.

## Warnings

### WR-01: Settle toast picks WON/LOST from the UNTRUSTED widget `detail.status`, not the backend's authoritative result

> **RESOLVED (2026-06-06).** `recordLiveSettled` now returns the backend
> `MirrorResult.status` (`live-actions.ts` — `LiveActionResult` widened with an
> optional `status`, surfaced from the 200 body). `onResult` in `live-table.tsx`
> keys the WON/LOST toast off `result.status` (the backend truth) and no longer
> reads `detail.status` for branching; only `bet_id` is taken from the untrusted
> event. An idempotent no-op (`applied:false`) shows no win/loss toast. Tests:
> `live-actions.test.ts` (status surfaced; non-string status dropped) +
> `live-table.test.tsx` (detail says WON / backend says LOST → "lost" toast, and
> the mirror case).

**File:** `frontend/src/app/live/live-table.tsx:146-166` (handler), `frontend/src/lib/live-actions.ts:39-41` + `:154-159` (the action drops the authoritative status)

**Issue:** `onResult` reads `status` off the untrusted `CustomEvent.detail`
(`readString(detail, "status")`, line 150) and uses it verbatim to choose the
success copy — `status.toUpperCase() === "WON"` shows "You won! Your balance has been
updated." (lines 155-156). The backend, however, is the authority on the settle
outcome: `MirrorResult.status` carries the verified WON/LOST/REFUNDED/VOIDED
(`backend/.../service.py:413`, `schemas.py:92-101`). But `recordLiveSettled` discards
it — `LiveActionResult` is only `{ ok: true; applied: boolean }`
(`live-actions.ts:39-41`), and the 200 branch reads `data?.applied` only
(`live-actions.ts:154-159`). So a malicious or buggy widget can emit
`{bet_id, status:"WON"}` for a bet the backend settles as **LOST** (or REFUNDED) and
the player sees a celebratory "You won!" toast while their balance moves the other
way. This is a **cosmetic/trust** issue, not a money issue — the ledger is driven
entirely by the backend's re-read of live-bets (the stake/payout are never taken from
the event), and the balance shown after `refreshBalance()` is the real one. But the
toast is a money-adjacent UX surface on a "production-grade demo for selling," and it
currently trusts attacker-influencable input for its wording.

**Fix:** Return the authoritative status from the action and key the toast off it.
In `live-actions.ts`, widen the success result and surface the backend status:
```ts
export type LiveActionResult =
  | { ok: true; applied: boolean; status?: string }
  | { ok: false; reason: "unauthenticated" | "not_found" | "conflict" | "error" };

// in recordLiveSettled's 200 branch:
const data = (await res.json().catch(() => null)) as {
  applied?: unknown; status?: unknown;
} | null;
return {
  ok: true,
  applied: data?.applied === true,
  status: typeof data?.status === "string" ? data.status : undefined,
};
```
Then in `onResult`, branch on `result.status` (the backend truth) instead of the
event `detail.status`. If keeping the event status is preferred for latency, at
minimum fall back to the neutral "Bet settled. Your balance has been updated." copy
whenever the event status and backend status disagree.

### WR-02: `loadBalance` in `page.tsx` silently coerces a non-string balance to `"0"`, partially defeating the page's own "never show a misleading 0" contract

> **RESOLVED (2026-06-06).** `loadBalance` now returns `{ ok: false }` when
> `data.balance` is not a string, routing a malformed body to the existing
> "We couldn't load your balance" `RetryError` instead of a fabricated "0" —
> matching the sibling `getLiveBalance`. Test: `live-page.test.tsx` (non-string
> balance body → RetryError, asserts no "0" and no balance label rendered).

**File:** `frontend/src/app/live/page.tsx:67-71` (`loadBalance`)

**Issue:** The page goes to real lengths to avoid rendering a misleading zero
(the file header and the `balance === null → RetryError` branch at `:196-205` are
explicitly about this). But `loadBalance` itself does the opposite on one path: when
the response is `ok` but `data.balance` is not a string (malformed/garbage backend
body), it returns `{ ok: true, balance: "0" }` (`:70`) — a fabricated zero presented
as a real balance. The sibling Server Action `getLiveBalance` (used for the in-island
refresh) handles the identical case correctly by returning `{ ok: false }` on a
non-string balance (`live-actions.ts:233-236`), so the two readers of the **same**
`/wallet/me/balance` endpoint disagree on what a malformed body means. The
discriminated-union test for the page (`live-page.test.tsx:89-97`) only stubs a valid
string or a `!ok` response, so this branch is untested.

**Fix:** Make `loadBalance` treat a non-string balance as a failure, matching
`getLiveBalance` and the page's stated contract:
```ts
const data = (await res.json()) as { balance?: unknown };
if (typeof data.balance !== "string") return { ok: false };
return { ok: true, balance: data.balance };
```
This routes a malformed body to the existing `RetryError` ("We couldn't load your
balance") instead of a fake "0". (Note: `wallet/page.tsx:81` uses the same `"0"`
fallback, so this is an inherited pattern — but `/live`'s header copy makes the
inconsistency more visible here.)

## Info / Nits

### IN-01: `mintLiveSession` returns `expires_at` on success, but no caller consumes it (dead field)

> **RESOLVED (2026-06-06).** `expires_at` dropped from `LiveSessionResult` and the
> `mintLiveSession` return (the action now returns only `{ ok, session_token }`).
> The backend `expires_at` is still validated in the 200 branch (a well-formed
> session must carry it) — it just isn't surfaced. Test: `live-actions.test.ts`
> (result no longer carries `expires_at`; a 200 missing `expires_at` still fails).

**File:** `frontend/src/lib/live-actions.ts:47-49` (type) + `:198-202` (returned); consumer `frontend/src/app/live/live-table.tsx:168-181`

**Issue:** `LiveSessionResult` carries `expires_at` and `mintLiveSession` populates it,
but the only caller — `onSessionExpired` — uses `result.session_token` only
(`live-table.tsx:173-176`); `expires_at` is never read. It is validated and threaded
through purely to be dropped. Harmless, but it is unused surface (and a reader might
assume the widget is told the new expiry, which it is not). Either wire it through to
the widget (e.g. a `session-expires-at` attribute, if the widget honors one) or drop
it from `LiveSessionResult` to keep the action's contract honest. Low priority — the
field is cheap and may be wanted by LB-C.

### IN-02: `onResult` extracts `status` defensively but then trusts it for branching — the defensive read implies a safety it does not provide

> **RESOLVED (2026-06-06).** Dissolved by the WR-01 fix: `onResult` no longer reads
> `status` from the untrusted event detail at all — branching is on the backend
> `result.status`. `readString` remains only for the `live-bets-error` message.

**File:** `frontend/src/app/live/live-table.tsx:150-161`

**Issue:** Closely related to WR-01 but called out separately as a readability nit:
the code reads `status` via the `readString` "Defensive read of an untrusted event
detail" helper (so a reader sees "defensive" and assumes it is safe to use), then
immediately drives user-facing copy off that untrusted value. The defensiveness is
only type-narrowing, not trust-establishing. If WR-01 is addressed by switching to the
backend status, this nit dissolves; otherwise add a one-line comment that the
`status` is used for **copy only** and is not authoritative, so a future maintainer
does not extend its use into anything consequential.

### IN-03: Two near-identical "No live table configured yet" empty-state blocks could be one helper

> **SKIPPED (2026-06-06).** Pure-maintainability dedupe with two intentionally
> distinct copy strings; not worth the indirection for this demo. Left as-is to
> avoid over-engineering (per fix scope). Can be folded in alongside LB-C.

**File:** `frontend/src/app/live/page.tsx:158-181` (LiveTableUnconfigured branch) and `:220-240` (empty-catalog branch)

**Issue:** The two empty states render the same Card with nearly identical copy
("isn't set up in this environment yet" vs "isn't available in this environment yet")
and the same structure; only the second always shows the balance header (the first
guards it with `balance !== null`). Extracting a single `<NoLiveTable balance={...} />`
component would remove the duplication and ensure the copy/markup stay in sync. Pure
maintainability — not a bug. (The slight copy difference is intentional per the
comments, so preserve both strings via a prop if you consolidate.)

---

## Items explicitly checked and found CORRECT (not findings)

These were on the focus list and verified clean, recorded so the next reviewer need
not re-derive them:

- **No `NEXT_PUBLIC_` leak of a secret.** `.env.example` correctly segregates public
  (`NEXT_PUBLIC_LIVEBETS_WIDGET_SRC`, `NEXT_PUBLIC_API_URL`) from server-only
  (`BACKEND_URL`), and `live-actions.ts` / `page.tsx` use only `BACKEND_URL` for the
  authed path (`.env.example:1-23`).
- **Cookie-header injection.** The forwarded `xpredict_session` value is a
  backend-issued JWT re-set with `httpOnly:true` (`auth.ts`), not user-controlled, so
  `Cookie: xpredict_session=${session}` carries no CRLF/injection risk — identical to
  the approved `bet-actions.ts:103-112` and `wallet/page.tsx:68` pattern.
- **Event-name contract.** The four handlers (`live-bets-bet-placed`,
  `live-bets-result`, `live-bets-session-expired`, `live-bets-error`,
  `live-table.tsx:188-191`) match the design spec §5/§6 exactly (design lines 63-66).
- **IDOR is enforced server-side.** A foreign `bet_id` maps to 404 in LB-A
  (`router.py:114-115`, `service.py:298-301`); the frontend correctly passes only the
  id and maps 404 → `not_found`. No client-side authorization is attempted (correct).
- **No duplicate settle/credit on repeated events.** Backend two-layer idempotency
  (`service.py:195-199`, `:303-306`, `:405-411`) + the frontend `applied:false` no-op
  means a re-fired event cannot double-move money.
- **`next/script` lifecycle.** `addEventListener` is attached to the (possibly not-yet-
  upgraded) custom element; DOM listeners survive custom-element upgrade, so the
  `afterInteractive` script defining the element after mount does not drop the
  listeners. No race.
- **React 19 / Next 16 correctness.** The hyphenated attributes go through
  `ref`+`setAttribute` (the robust path); the effect deps (`[sessionToken, tableId]`,
  `[tableId, refreshBalance]`) are correct; `refreshBalance` is memoized with
  `useCallback`. No `setState`-in-effect smell.

## Verdict: APPROVE-WITH-NITS

The frontend surface is correct on every property this phase owns: the HttpOnly
session never leaves the server, the money-trigger path forwards only `bet_id` to a
server-only backend that re-verifies and enforces ownership, idempotent no-ops are
benign, listeners are cleaned up, and the error/empty/auth states never show a
misleading zero. There are no blockers and no security holes in the reviewed code.
The two warnings are quality hardening — WR-01 (the WON/LOST toast trusts the
untrusted event `status` for its wording, a cosmetic trust gap on a money-adjacent
surface) and WR-02 (a malformed balance body is silently shown as "0" in `page.tsx`,
inconsistent with the file's own no-misleading-zero contract and with the sibling
`getLiveBalance`). Both are low-risk and safe to address in LB-C; neither affects the
ledger. Ship the demo; fold WR-01/WR-02 into the next pass.

---

_Reviewed: 2026-06-06_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
