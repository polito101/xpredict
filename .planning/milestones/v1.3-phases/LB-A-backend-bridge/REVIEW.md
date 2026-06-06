---
phase: LB-A-backend-bridge
reviewed: 2026-06-06T00:00:00Z
depth: deep
files_reviewed: 16
files_reviewed_list:
  - backend/app/integrations/livebets/__init__.py
  - backend/app/integrations/livebets/constants.py
  - backend/app/integrations/livebets/models.py
  - backend/app/integrations/livebets/schemas.py
  - backend/app/integrations/livebets/client.py
  - backend/app/integrations/livebets/service.py
  - backend/app/integrations/livebets/router.py
  - backend/alembic/versions/0011_livebets_bridge.py
  - backend/app/core/config.py
  - backend/app/main.py
  - .env.example
  - backend/tests/integrations/livebets/test_livebets_bridge.py
  - backend/tests/integrations/livebets/test_livebets_router.py
  - backend/tests/integrations/livebets/test_migration_0011.py
  - backend/tests/integrations/__init__.py
  - backend/tests/integrations/livebets/__init__.py
findings:
  blocker: 1
  warning: 4
  info: 3
  total: 8
status: resolved
resolution:
  resolved_at: 2026-06-06
  resolved_by: Claude Opus 4.8 (1M context)
  branch: gsd/livebets-demo
  blocker_resolved: 1
  warning_resolved: 4
  info_wont_fix: 3
  tests_added: 14
  livebets_suite: "35 passed"
  regression_suite: "130 passed (wallet/bets/settlement)"
---

# Phase LB-A: Backend bridge — Code Review Report

**Reviewed:** 2026-06-06
**Depth:** deep (cross-file: service ↔ wallet/settlement/bets baselines, live-bets API contract, migration ↔ model parity)
**Files Reviewed:** 16
**Status:** CHANGES-REQUESTED

## Summary

This is a careful, well-documented additive bridge that faithfully mirrors the validated `app/bets` + `app/settlement` ledger patterns: owned `session.begin()`, canonical UUID lock order, `WalletService._post_transfer` as the sole writer, two-layer idempotency (mirror-row primary + `transfers.idempotency_key` 23505 secondary), `Decimal`-only money, server-side `get_bet` verification, the loss sink correctly routed to `house_revenue`, the winnings leg correctly funded from `house_promo` and skipped when `payout - stake <= 0`, and a clean escrow-nets-to-zero invariant proven by tests. The transaction-ordering fix (reads inside `session.begin()` in `record_settled`, verification read outside) is correct in both `record_placed` and `record_settled`, and the autobegin pitfall is avoided in both. The migration is additive/reversible and matches the model DDL.

The double-entry math, idempotency, transaction integrity, lock order, and no-zero-amount-entry guarantees are all correct — I could not fault the money path itself. The one BLOCKER is an **authorization / trust-boundary gap that is orthogonal to the ledger correctness**: the bridge never binds the verified bet to the calling player, so any authenticated player can mirror (and be credited for) another player's winning bet, or debit a victim's wallet. The live-bets `GET /v2/bets/{id}` contract scopes reads to the *operator* key, not the player, and the bet payload carries no `player_ref`, so XPredict is the only party that can enforce per-player ownership — and currently does not. The remaining findings are robustness/quality.

## Critical Issues

### BL-01: Missing per-player ownership check — a player can mirror and be paid for another player's bet (IDOR / cross-player credit)

**File:** `backend/app/integrations/livebets/service.py:108-200` (`record_placed`), `:202-351` (`record_settled`); router `backend/app/integrations/livebets/router.py:92-134`

**Issue:**
The bridge verifies the bet's *status/stake/payout* against live-bets but never verifies that the `bet_id` belongs to the **calling player**. `record_placed` writes `user_id=user.id` and resolves *that caller's* wallet, and `record_settled` resolves *the caller's* wallet for the WON stake-return + winnings legs — but nothing ties `bet_id` to `user.id`.

Trace the trust boundary against the live-bets contract (`live-bets/docs/INTEGRATION-GUIDE.md`):
- `GET /v2/bets/{id}` requires scope `bets:read` = "Read **own** bets" (guide line 362). "Own" here means the **operator** (the single XPredict API key), not the end player. Every XPredict player shares one operator key, so live-bets will happily return *any* operator bet to *any* XPredict player.
- The bet response (guide lines 157-167) has **no `player_ref` / user field** at all — `parse_verified_bet` (`schemas.py:117-154`) only extracts `bet_id, status, stake, market_id, table_id, payout`. So XPredict cannot even cross-check the player from the live-bets payload; XPredict is the *only* place per-player ownership can be enforced, and it isn't.

Concrete exploits (both authenticated as ordinary players, the `current_active_player` gate is satisfied):
1. **Cross-player winnings theft.** Player A places a winning bet in the widget. Attacker B (any logged-in player) learns/guesses A's `bet_id` (it is a UUID, but it is echoed to the browser via the widget DOM events `live-bets-result`/`live-bets-bet-placed` per guide lines 117-135, and is sent in plaintext to B's own `/placed`/`settled` calls) and calls `POST /api/live/bets/{A_bet_id}/placed` then `/settled`. The bridge writes the mirror row with `user_id=B`, debits **B's** wallet the stake, then on WON credits **B's** wallet stake + winnings from `house_promo`. B is paid for A's bet. With `payout > 2*stake` B nets a profit funded by the house; the mirror row PK then blocks A from ever mirroring their own real bet.
2. **Griefing / wallet drain.** B repeatedly calls `/placed` with arbitrary valid-but-foreign PENDING `bet_id`s, each debiting B's own wallet — self-inflicted, but symmetrically, because the mirror row is keyed only on `bet_id`, B placing first permanently denies the real owner their mirror (a cross-player DoS on the ledger mirror).

The phase's own threat model lists T-LBA-01 (client-supplied amount) and T-LBA-03 (unauth access) but **omits cross-player authorization** — the verification mitigates amount-tampering, not ownership. SC#5 ("never trusts a client-supplied amount") is met for the *amount* but the *bet identity* is fully client-supplied and unverified against the caller.

**Fix:**
Bind the bet to the player at the live-bets boundary and re-check on settle. Two layers:

1. Mint sessions with a per-player `player_ref` (already done: `router.py:75` passes `player_ref=str(player.id)`), and **persist + verify** that binding. The cleanest server-side check is to include `player_ref` in the `get_bet` response contract and assert it equals `str(user.id)`:
```python
# schemas.py parse_verified_bet — extract the owner the session was minted under
player_ref = raw.get("player_ref")
...
return VerifiedBet(..., player_ref=str(player_ref) if player_ref is not None else None)

# service.py record_placed, after parsing, before any write:
if verified.player_ref is not None and verified.player_ref != str(user.id):
    raise LiveBetsVerificationError(
        f"bet {bet_id} belongs to {verified.player_ref}, not caller {user.id}"
    )
```
2. If live-bets cannot return `player_ref` (confirm against the real API — the guide does not document it), enforce ownership on **settle** via the mirror row that placement already wrote:
```python
# service.py record_settled, inside session.begin(), after loading `mirror`:
if mirror.user_id != user.id:
    raise LiveBetsVerificationError(
        f"bet {bet_id} mirror belongs to {mirror.user_id}, not caller {user.id}"
    )
```
The settle-side mirror check is a one-line, zero-dependency mitigation that closes exploit (1)'s *payout* leg (the attacker can no longer be credited for a bet whose mirror row records a different `user_id`) and should be added regardless. The placement-side `player_ref` check (or an equivalent design decision documented as accepted risk for the off-grid demo) is needed to fully close placement-side debit/DoS. At minimum this gap must be recorded as an explicit accepted risk in the phase threat model rather than left silent.

**RESOLVED (settle-side; placement residual ACCEPTED FOR DEMO):**
- **Settle-side ownership check (closes the payout-theft vector).** `record_settled` now rejects a caller who does not own the mirrored bet. Order is exactly as required: load mirror → ownership check → primary idempotency guard (`status != PENDING`) → post. A new `LiveBetsOwnershipError` (distinct from `LiveBetsVerificationError`) is raised when `mirror.user_id != user.id`, BEFORE the idempotency guard and any posting (`service.py`).
- **Router maps ownership to HTTP 404 (IDOR-safe).** Both `/placed` and `/settled` map `LiveBetsOwnershipError` → 404 ("Bet not found.") so a foreign bet's existence is never leaked, reusing the existing exception-mapping style (`router.py`). 404 ordering precedes the 409 verification mapping.
- **Placement claim documented + residual accepted.** `record_placed` keeps the first-caller claim (`user_id=user.id`) with an in-code comment explaining that a STRONG placement-time binding needs live-bets to return `player_ref` on `GET /v2/bets/{id}` (the contract does NOT today), so the placement-side residual (an attacker placing first to claim/DoS a foreign bet, self-debiting their OWN wallet — no cross-player payout) is **ACCEPTED FOR DEMO** and deferred to **LB-C** (where we control live-bets and can return/verify `player_ref`). The settle-side check closes the actual payout-theft vector.
- **Tests:** `test_record_settled_by_non_owner_is_rejected_no_ledger_effect` (service: raises `LiveBetsOwnershipError`, zero ledger effect — no transfers, mirror untouched/owned by A, attacker+owner wallets and escrow unchanged) and `test_settled_route_non_owner_returns_404_no_ledger_effect` (route: 404, zero ledger effect end-to-end through the app).

## Warnings

### WR-01: `_safe_decimal` silently swallows a malformed authoritative amount, turning a verification signal into a money bug

**File:** `backend/app/integrations/livebets/schemas.py:28-40`, used at `:136-145`

**Issue:**
`_safe_decimal` catches only `InvalidOperation`. `Decimal(str(value))` on a value whose `str()` is fine but type is hostile is mostly covered, but two real cases slip through to the *opposite* of the intended "raise on garbage" contract:
- A NaN/Infinity from live-bets: `Decimal(str(float("nan")))` returns `Decimal('NaN')` (no `InvalidOperation`), and `Decimal('Infinity')` likewise. A `stake` of `Decimal('NaN')` passes the `stake is None` guard (`:137-138`), is stored in the mirror row and posted to `_post_transfer`; `NaN > 0` is `False`, and arithmetic/`CHECK (amount > 0)` behavior with NaN against `NUMERIC` is undefined/avoidable surprise. For WON, `winnings = payout - stake` with a NaN payout yields NaN and the `winnings > 0` guard silently skips the winnings leg — a winner is shorted with no error.
- The docstring says it returns `None` on "garbage" so the caller can treat absence as a verification failure, but NaN/Inf are neither `None` nor a legitimate finite amount.

**Fix:** Reject non-finite values explicitly so they become the intended verification failure:
```python
def _safe_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        d = Decimal(str(value))
    except InvalidOperation:
        return None
    if not d.is_finite():
        return None
    return d
```
(Then a NaN stake raises `ValueError` at `parse_verified_bet:137-138` / a NaN payout makes a WON settle raise at `service.py:267-270` — the desired "reject, no ledger effect" behavior.)

**RESOLVED:** `_safe_decimal` now adds `if not d.is_finite(): return None` after constructing the `Decimal` (`schemas.py`), so NaN/Infinity become the intended verification failure: a non-finite stake raises `ValueError` at parse time (no posting), a non-finite payout on a WON settle is treated as "no payout" and rejected. **Tests:** `test_record_placed_rejects_non_finite_stake_no_debit` and `test_record_settled_won_rejects_non_finite_payout_no_posting` (both parametrized over `nan`/`inf`/`"NaN"`/`"Infinity"`, asserting zero ledger effect).

### WR-02: No upper bound / sanity check on the live-bets stake before debiting the player's wallet

**File:** `backend/app/integrations/livebets/service.py:132` (placed), and the trust boundary generally

**Issue:**
The bridge debits `verified.stake` from the player's wallet with no maximum. `WalletService.transfer` enforces `InsufficientBalance` and the DB `CHECK (balance >= 0)`, so the player cannot be driven negative — but a compromised or buggy live-bets (the authority, but a *separate* off-grid service) returning an absurd `stake` (or the NaN/precision cases in WR-01) can drain the player's entire wallet in one mirrored "placement" with no operator-side guardrail. `app/bets/place_bet` deliberately enforces per-market `min_stake`/`max_stake` (`bets/service.py:97-101`) precisely because stake is money-affecting input; the live-bets stake is *more* externally-controlled, not less.

**Fix:** Apply a defensive ceiling (and floor) before posting — reuse the existing `settings.BET_MIN_STAKE`/`BET_MAX_STAKE` or a dedicated `LIVEBETS_MAX_STAKE`, raising `LiveBetsVerificationError` outside the band. This is cheap defense-in-depth at a money-moving trust boundary and matches the established `place_bet` convention.

**RESOLVED:** `record_placed` now enforces `settings.BET_MIN_STAKE <= stake <= settings.BET_MAX_STAKE` (the SAME settings `BetService.place_bet` uses — confirmed `[Decimal("1.0000"), Decimal("100000.0000")]` in `config.py`) immediately after reading `verified.stake`, BEFORE `session.begin()`/the debit, raising `LiveBetsVerificationError` (router → 409) outside the band (`service.py`). **Tests:** `test_record_placed_rejects_out_of_band_stake_no_debit` (parametrized above-max / below-min, asserting no debit / no mirror / no transfer) and `test_record_placed_accepts_stake_at_band_boundaries` (inclusive band — guards against an off-by-one).

### WR-03: `record_settled` reads stake from the mirror row but never reconciles it against the live-bets `verified.stake`

**File:** `backend/app/integrations/livebets/service.py:226` (parse), `:258` (uses `mirror.stake`)

**Issue:**
The settle path correctly reads the authoritative captured `stake` from the mirror row (`:258`) and the design explicitly says settle is "status/payout-based, not a stake comparison" (LB-A-02-PLAN must_haves). However, `parse_verified_bet` *already requires and parses* `verified.stake` at settle time (`schemas.py:137-138` raises if absent), and the WON winnings math is `verified.payout - stake_from_mirror` (`:280`). If live-bets' settled `stake` ever differs from the placement `stake` (e.g. a partially-cancelled/rebated round, or a live-bets bug), the winnings leg mixes a live-bets payout with a mirror-row stake and the discrepancy is silently ignored. The escrow stake-return leg uses the mirror stake while the winnings delta uses a *different* implied stake — escrow still nets to zero, but the winnings amount can be wrong.

**Fix:** Since `verified.stake` is parsed anyway, assert consistency and reject on drift (no extra I/O):
```python
if verified.stake != mirror.stake:
    raise LiveBetsVerificationError(
        f"settle stake {verified.stake} != mirrored stake {mirror.stake} for bet {bet_id}"
    )
```
This turns an undetected payout-math error into a clean verification rejection with zero ledger effect, consistent with the phase's "mismatch rejected without posting" stance.

**RESOLVED:** `record_settled` now reconciles `verified.stake` against `mirror.stake` (after the ownership check + primary idempotency guard, before deriving leg specs); on drift it raises `LiveBetsVerificationError` with zero ledger effect (`service.py`). **Test:** `test_record_settled_rejects_stake_drift_no_posting` (placed stake 20, settle reports 25 → rejected, mirror still PENDING, balances unchanged). Existing WON-cycle tests already settle with a matching stake, so they are unaffected.

### WR-04: Retry/timeout config drift from the sibling Polymarket client invites unbounded/odd backoff (and an undocumented divergence)

**File:** `backend/app/integrations/livebets/client.py:89-94, 117-122, 140-145`

**Issue:**
The module docstring claims it "mirrors `app/integrations/polymarket/client.py`", but `wait_exponential_jitter(initial=1, max=10, jitter=2)` is a specific choice that should be verified against the sibling (the Gamma client's parameters were not matched in this review — they differ enough to call out). More concretely, `get_bet`/`list_tables` are `GET`s and safely retryable, but `mint_session` is a `POST /v2/sessions` decorated with the *same* retry on `(NetworkError, TimeoutException)`. A timeout *after* live-bets created the session will retry and mint duplicate sessions (the guide does not document session idempotency for `POST /v2/sessions`, unlike `POST /v2/bets` which mandates an `Idempotency-Key`). For the demo this is low-impact (extra short-lived JWTs), but it is an unflagged behavior.

**Fix:** Either (a) document explicitly that `mint_session` retries are acceptable because sessions are cheap/short-lived, or (b) drop the retry decorator from `mint_session` (leave it on the idempotent `GET`s), or (c) pass an `Idempotency-Key` header if/when live-bets supports it for sessions. Also state the deliberate retry-parameter values rather than claiming a mirror that does not hold.

**RESOLVED (option b + docstring):** The `@retry` decorator was removed from `mint_session` (the non-idempotent `POST /v2/sessions`) — a post-success timeout can no longer mint duplicate sessions — with a one-line comment stating the reasoning. Retry stays on the idempotent GETs (`get_bet`, `list_tables`). The module docstring no longer claims a strict "mirror" of the polymarket client; it states the deliberate `wait_exponential_jitter(initial=1, max=10, jitter=2)` values and the GET-only retry policy (`client.py`). Behavior is unchanged for the happy path; covered by the existing router happy-path `POST /session` test (no network).

## Info

### IN-01: `LiveBetsVerificationError` (no-fault verification miss) is mapped to HTTP 409, conflating "your fault" with "not settled yet"

**File:** `backend/app/integrations/livebets/router.py:109-110, 131-132`

**Issue:**
Both routes map every `LiveBetsVerificationError` to `409 CONFLICT`. But the error covers semantically different cases: a genuine conflict/replay vs. transient "live-bets says still PENDING, try again later" (`service.py:227-230`) vs. "settle before placed" (`:250-252`) vs. "WON without payout" (a live-bets data problem, `:267-270`). A 409 for "still PENDING" is misleading for the caller/UX (it is closer to 425 Too Early / 404). Low impact for a demo but worth a follow-up; consider distinct exception subclasses → distinct status codes.

**WON'T FIX FOR DEMO:** Splitting `LiveBetsVerificationError` into per-case subclasses with distinct status codes is over-engineering for the demo (the reviewer rates it low-impact). Note: the BL-01 fix already introduces ONE new distinct subclass (`LiveBetsOwnershipError` → 404) where it materially matters (IDOR leak avoidance); the remaining 409 cases stay as-is. Deferred as a follow-up.

### IN-02: `record_placed` upserts the mirror row then posts the debit; a missing-wallet (`NoResultFound`) path is reached only after the insert in `record_placed` but before any insert in `record_settled` — asymmetric, and the placed-side wallet resolution happens after the conflict check

**File:** `backend/app/integrations/livebets/service.py:136-158`

**Issue:**
In `record_placed`, `_resolve_user_wallet_id` (`:136-138`) runs *before* the mirror upsert, so a missing wallet raises `NoResultFound` (→ router 404) with no row written — correct. Minor observation: the mirror row is inserted (`:145-157`) *before* the lock acquisition and the debit; if `_post_transfer` later fails for a non-23505 reason, the whole `session.begin()` rolls back (including the mirror insert), which is correct. No bug — but the ordering (insert mirror, then lock, then post) differs from `place_bet` (lock, then insert bet, then post). It works because everything is in one transaction; flagging only so a future reader does not "fix" the order and break the primary-guard semantics. No change required.

**WON'T FIX (no change required):** The reviewer confirms there is no bug. Left as-is.

### IN-03: `_safe_uuid` catches `(ValueError, AttributeError)` but `UUID(str(value))` can also surface a malformed `market_id`/`table_id` as `None` silently

**File:** `backend/app/integrations/livebets/schemas.py:43-52`

**Issue:**
`market_id`/`table_id` parse to `None` on any unparseable value (`:151-152`). These are non-money, nullable, metadata-only fields (stored on the mirror row, used in transfer metadata), so silently dropping a malformed value is acceptable — but it means a malformed `market_id` from live-bets is invisibly lost rather than logged. Consider a debug log when a present-but-unparseable id is dropped, to aid demo troubleshooting. No correctness impact.

**WON'T FIX FOR DEMO:** `market_id`/`table_id` are non-money, nullable, metadata-only fields; the reviewer confirms no correctness impact. Adding a debug log is a nice-to-have not worth the change for the demo. Deferred.

---

## Notes on things checked and found correct (not findings)

- **Double-entry math / escrow nets to zero:** placed `wallet→escrow` (+stake); WON `escrow→wallet` (−stake) + `house_promo→wallet` (payout−stake); LOST `escrow→house_revenue` (−stake); REFUNDED/VOIDED `escrow→wallet` (−stake). Escrow returns to prior balance on every full cycle. Verified against `service.py:266-314` and the passing assertions in `test_livebets_bridge.py:218-266, 273-306, 314-349`.
- **No zero-amount entries:** winnings leg skipped when `winnings <= 0` (`service.py:283`), mirroring settlement's `if sb.pnl > 0` (`settlement/service.py:172`). Covered by `test_won_with_no_winnings_posts_only_stake_return_leg`.
- **Transaction integrity / autobegin:** verification `get_bet` reads are outside `session.begin()` in both methods; all DB reads/posts are inside the owned `begin()`; `record_settled` correctly issues the mirror read *inside* begin (the wave-1 read-before-begin bug is fixed and the same pattern is correctly applied to `record_placed`). Canonical UUID lock order via `sorted(..., key=str)` with `with_for_update()` before any post, matching `place_bet`/`resolve_market`.
- **Idempotency:** mirror-row PK `on_conflict_do_nothing` primary guard (`service.py:145-162`), `status != PENDING` settle primary guard (`:253-256`), per-leg WON keys `:settled:stake`/`:settled:winnings` (`constants.py:107-114`) so the two legs never collide, and the 23505 secondary guard caught in both methods (`:190-198`, `:343-349`). The secondary guard is genuinely exercised by `test_won_secondary_idempotency_key_collision_is_caught`.
- **Money typing:** `Decimal` throughout; `stake` is `Mapped[Money]` (NUMERIC(18,4)); float JSON like `10.0` is parsed via `Decimal(str(...))` avoiding binary-float error (modulo the NaN/Inf gap in WR-01).
- **Migration:** additive, reversible, model↔DDL parity (CHECK, index, columns, tenant ghost), idempotent escrow seed copying the established `0004_phase3_wallet_ledger.py` `ON CONFLICT DO NOTHING` house-seed pattern verbatim; chains `0011 → 0010` on the main line; fixed escrow UUID in a non-colliding `…00b1` block. (Pre-existing dual-`0004` revision branch and the NULL-`owner_id` `ON CONFLICT` semantics are inherited from existing migrations, not introduced here.)
- **Security:** routes gated by `current_active_player` (401 proven for all four routes); `X-API-Key` lives only in `Settings`, set as an httpx default header, never logged, never returned to the browser; live-bets `403` mapped to a clear `RuntimeError` (need `bets:read`) rather than a generic 500; no SQLi (parametrized `text()`/ORM everywhere); `.env.example` placeholder-only; `extra="ignore"` settings tolerate the appended keys; router correctly omits `from __future__ import annotations`; structlog scrubbing relied upon and never fed the key.

---

_Reviewed: 2026-06-06_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
