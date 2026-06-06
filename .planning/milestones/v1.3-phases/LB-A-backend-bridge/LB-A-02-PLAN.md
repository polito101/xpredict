---
phase: LB-A-backend-bridge
plan: 02
type: execute
wave: 2
depends_on:
  - LB-A-01
files_modified:
  - backend/tests/integrations/livebets/__init__.py
  - backend/tests/integrations/livebets/test_migration_0011.py
  - backend/tests/integrations/livebets/test_livebets_bridge.py
  - backend/tests/integrations/livebets/test_livebets_router.py
autonomous: true
requirements:
  - LB-A-SC6   # `cd backend && uv run pytest` green for the new module: placed->won, placed->lost, void/refund, duplicate no-op, escrow-nets-to-zero, verification-rejects-mismatch
  - LB-A-SC2   # migration applies + reverses cleanly, zero behavior change (existing suites still pass)
  - LB-A-SC4   # idempotency + escrow-nets-to-zero proven by test
  - LB-A-SC5   # server-side verification proven (mismatch rejected without posting)

must_haves:
  truths:
    - "A faked live-bets client (no network) drives placed->won and placed->lost cycles that post the correct double-entry and leave livebets_escrow at its starting balance."
    - "Replaying the same placed or settled event is a no-op (no second transfer, balances unchanged) — proven for both the mirror-row guard and the idempotency_key guard."
    - "A void/refund returns the stake to the player's wallet from livebets_escrow."
    - "A verification failure (record_placed when live-bets status != PENDING; record_settled when status is still PENDING / not yet settled; or a WON settle with no payout field) is rejected with no ledger entry. On settle, stake is read from the mirror row captured at placement (not re-fetched), so the settle check is status/payout-based, not a stake comparison."
    - "The migration applies and reverses cleanly against testcontainer Postgres; the livebets_escrow singleton and livebets_bets table exist after upgrade and are gone after downgrade."
    - "Unauthenticated requests to /api/live/* are rejected (401)."
  artifacts:
    - path: "backend/tests/integrations/livebets/test_livebets_bridge.py"
      provides: "LiveBetsBridge ledger + idempotency + verification tests (faked client, testcontainers)"
      contains: "livebets_escrow"
    - path: "backend/tests/integrations/livebets/test_migration_0011.py"
      provides: "Additive/reversible migration test (escrow singleton + livebets_bets)"
      contains: "livebets_bets"
    - path: "backend/tests/integrations/livebets/test_livebets_router.py"
      provides: "Router auth-gate + happy-path test with overridden client dependency"
      contains: "/api/live"
  key_links:
    - from: "backend/tests/integrations/livebets/test_livebets_bridge.py"
      to: "app.integrations.livebets.service.LiveBetsBridge"
      via: "exercises record_placed/record_settled with a FakeLiveBetsClient"
      pattern: "LiveBetsBridge"
    - from: "backend/tests/integrations/livebets/test_livebets_bridge.py"
      to: "app.integrations.livebets.constants.LIVEBETS_ESCROW_ACCOUNT_ID"
      via: "asserts escrow balance delta nets to zero"
      pattern: "LIVEBETS_ESCROW_ACCOUNT_ID"
---

<objective>
Prove the LB-A bridge correct with hermetic backend tests (faked live-bets client, no live network), mirroring the existing `tests/bets/test_place_bet.py` + `tests/settlement/test_resolve_market.py` harness (testcontainers Postgres, `alembic upgrade head`, committed-session helpers). Cover: placed->won, placed->lost, void/refund, duplicate-event no-op, escrow-nets-to-zero, verification-rejects-mismatch; plus an additive/reversible migration test and a router auth-gate test.

Purpose: `cd backend && uv run pytest` is green for the new module (LB-A-SC6), and the additive/idempotent/verified guarantees are enforced by tests, not just asserted in prose.

Output: One test package (`tests/integrations/livebets/`) with three test modules.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/LB-A-backend-bridge/CONTEXT.md
@.planning/phases/LB-A-backend-bridge/LB-A-01-PLAN.md

# Test harness to mirror (read the exact fixture + helper shapes)
@backend/tests/conftest.py
@backend/tests/bets/test_place_bet.py
@backend/tests/settlement/test_resolve_market.py

# The code under test (read the contracts the bridge exposes)
@backend/app/integrations/livebets/service.py
@backend/app/integrations/livebets/constants.py
@backend/app/wallet/service.py
@backend/app/wallet/constants.py
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: LiveBetsBridge ledger, idempotency + verification tests (faked client)</name>
  <files>backend/tests/integrations/livebets/__init__.py, backend/tests/integrations/livebets/test_livebets_bridge.py</files>
  <behavior>
    - placed->won: wallet debited by stake on placed; on won, wallet receives stake back + (payout-stake); livebets_escrow balance delta over the full cycle == 0; mirror row WON with settled_at set; bets table untouched.
    - placed->lost: wallet down by stake after the cycle; livebets_escrow delta == 0; house_revenue gained the stake (before/after delta == stake); mirror row LOST.
    - refund (REFUNDED and VOIDED — the two real refund statuses; cover both): after placed->refund, wallet is whole again (net 0); livebets_escrow delta == 0; mirror row REFUNDED (resp. VOIDED).
    - won with payout == stake (no winnings): only the stake-return leg posts (no zero-amount winnings entry); house_promo delta == 0.
    - duplicate placed: a second record_placed for the same bet_id posts NO second transfer (transfer count for that bet unchanged) and returns applied=False; wallet balance unchanged from the single debit.
    - duplicate settled: a second record_settled is a no-op (no extra entries, balances unchanged), applied=False.
    - verification rejects mismatch: get_bet returns status != PENDING on record_placed -> raises LiveBetsVerificationError, no ledger entry, no mirror row; record_settled on a bet still PENDING in live-bets -> raises, no entry.
    - server-side stake authority: the amount that moves comes from live-bets, never the request — the test seeds get_bet with stake=S (the request carries only bet_id) and asserts exactly S moved.
  </behavior>
  <action>
Create `tests/integrations/livebets/__init__.py` (empty) and `test_livebets_bridge.py`.

Mirror `tests/settlement/test_resolve_market.py` structure EXACTLY (read it first):
- `pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]`.
- `@pytest.fixture(autouse=True) def _require_testcontainer(engine): return engine` — depending on the `engine` fixture runs `alembic upgrade head`, which (via LB-A-01's migration) creates the `livebets_escrow` singleton AND the `livebets_bets` table in the container. Therefore do NOT create `livebets_bets` via a `Base.metadata` fixture — it is a real migration table now (unlike `bets`, whose migration was deferred). If a stray `bets` table is needed by any assertion, you do not need it here.
- Committed-session helpers via `_get_session_maker()` (copy `_seed_wallet`, `_balance` verbatim from `test_resolve_market.py`). Because the testcontainer is session-scoped and `house_promo`/`house_revenue`/`livebets_escrow` are SHARED singletons, assert on those with BEFORE/AFTER deltas (never absolute), and use fresh `uuid4()` user wallets + fresh `bet_id`s per test for absolute assertions — this is the established pattern.
- Add helpers: `_livebets_escrow_balance()` (select balance where id == LIVEBETS_ESCROW_ACCOUNT_ID), `_mirror_row(bet_id)` (select the LiveBetsBet by pk), `_transfers_for_bet(bet_id)` (select transfers whose `transfer_metadata->>'bet_id'` == str(bet_id), to count legs) — model the metadata query on `_audit_for_market` in `test_resolve_market.py` which uses `AuditLog.payload["market_id"].astext`.

FakeLiveBetsClient (no network) — a tiny in-memory double matching the `LiveBetsClient` method surface the bridge calls:
```
class FakeLiveBetsClient:
    def __init__(self): self._bets = {}
    def set_bet(self, bet_id, *, status, stake, market_id=None, table_id=None, payout=None):
        self._bets[str(bet_id)] = {"bet_id": str(bet_id), "status": status, "stake": stake,
                                    "market_id": market_id, "table_id": table_id, "payout": payout}
    async def get_bet(self, bet_id): return self._bets[str(bet_id)]
    async def mint_session(self, **kw): return {"session_token": "fake", "expires_at": "2026-01-01T00:00:00Z"}
    async def list_tables(self): return []
```
Pass amounts as `Decimal` strings (NUMERIC(18,4)); never float. A minimal `user` stand-in is whatever `record_placed(user=...)` needs — if it only reads `user.id`, use `types.SimpleNamespace(id=user_id)` (the bridge takes `user`, not a full ORM `User`, to stay test-light — confirm against the signature in `service.py`).

Drive each behavior with its own `async def test_...` using a fresh `bet_id = uuid4()` and a fresh seeded wallet, calling the bridge on its own `_get_session_maker()` session (the bridge owns `session.begin()`, exactly like the settlement tests call `resolve_market`). For the placed->won cycle: `set_bet(bet_id, status="PENDING", stake=Decimal("20.0000"), payout=None)`, call `record_placed`; then `set_bet(bet_id, status="WON", stake=Decimal("20.0000"), payout=Decimal("50.0000"))`, call `record_settled`; assert wallet net change, escrow delta == 0, house_promo funded `30.0000` (payout-stake), mirror row WON/settled_at.

Verification-mismatch tests: seed `get_bet` with the WRONG status and assert `pytest.raises(LiveBetsVerificationError)` (import it from where Task-2 of LB-A-01 defined it — `app.integrations.livebets.exceptions` or `service`), then assert no transfer rows for that `bet_id` and no mirror row.

Idempotency tests: call the same `record_*` twice on two separate sessions; assert `applied` is True then False, the per-bet transfer count is unchanged on the second call, and balances match the single-application state. Prove BOTH guards explicitly — the mirror-row primary guard always fires first on a sequential replay, so the `transfers.idempotency_key` (23505) secondary guard would otherwise never be exercised:
   - PRIMARY guard: a duplicate `record_placed` / `record_settled` (mirror row already non-PENDING) -> `applied=False`, no extra transfer.
   - SECONDARY (23505) guard, two-leg WON path (M3): construct the collision directly — on a fresh `bet_id`, pre-insert a transfer carrying the WON winnings key `livebets:{bet_id}:settled:winnings` (or `:stake`) while the mirror row is still PENDING (so the primary guard does NOT short-circuit), then call `record_settled` (WON) and assert it catches the 23505, returns `applied=False`, and leaves escrow/balances consistent with no half-applied settle. This is the only test that actually covers the per-leg-key collision for the two-leg WON case.
  </action>
  <verify>
    <automated>cd backend && uv run pytest tests/integrations/livebets/test_livebets_bridge.py -x -q</automated>
  </verify>
  <done>All bridge behaviors pass against testcontainer Postgres: placed->won/lost/void post the correct double-entry, escrow nets to zero, winnings come from house_promo and losses go to house_revenue, duplicate events are no-ops (applied=False, no extra transfers), and verification mismatches raise with zero ledger effect.</done>
</task>

<task type="auto">
  <name>Task 2: Migration reversibility test + router auth-gate/happy-path test</name>
  <files>backend/tests/integrations/livebets/test_migration_0011.py, backend/tests/integrations/livebets/test_livebets_router.py</files>
  <action>
Two focused modules.

1. `test_migration_0011.py` — additive + reversible migration test (LB-A-SC2). Model it on the structure of the existing migration tests (the suite already has `tests/wallet/test_migration_0003.py` per the `0004` docstring — read it if present for the alembic-command idiom; otherwise drive alembic via `alembic.command` + `alembic.config.Config` as `conftest.py`'s `engine` fixture does). Two checks:
   - After `alembic upgrade head` (the `engine` fixture already did this), assert: the `livebets_bets` table exists (information_schema query or `inspect(engine)`), and the `livebets_escrow` singleton row exists exactly once (`SELECT count(*) FROM accounts WHERE id = '<LIVEBETS_ESCROW_ACCOUNT_ID>' AND kind='livebets_escrow' AND owner_type='system'` == 1).
   - Reversibility: in an isolated path (a dedicated sync engine on the SAME container URL, mirroring how the existing migration test downgrades), run `alembic downgrade -1` then assert `livebets_bets` is gone and the escrow row is gone; then `alembic upgrade head` again to restore (so later session-scoped tests still see the schema). IMPORTANT: because `engine` is session-scoped and shared, either (a) run this test's down/up against a throwaway second container, or (b) guarantee you upgrade back to head before yielding. Prefer (b) with a try/finally that re-runs `upgrade head` — copy whichever approach `tests/wallet/test_migration_0003.py` uses to avoid poisoning the shared schema. If neither is clean, mark this test to use its OWN `PostgresContainer` (cheap correctness over shared-state cleverness).
   - Add `pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]` only if the test is async; a sync alembic-only test needs just `pytest.mark.integration`.

2. `test_livebets_router.py` — router contract (LB-A-SC1). Use the lightweight `client` fixture from `conftest.py` (httpx ASGITransport, no Docker) plus `app.dependency_overrides`:
   - AUTH GATE (no Docker needed): without authentication, `POST /api/live/bets/{uuid}/placed`, `POST /api/live/bets/{uuid}/settled`, `POST /api/live/session`, and `GET /api/live/tables` all return 401. (Mirror how other player-gated routes are asserted unauthenticated; `current_active_player` 401s without a cookie.) This is the core SC#1 "unauth requests are rejected" check and needs no Postgres.
   - HAPPY-PATH with overrides: override `current_active_player` (return a stub user with a fixed `id`) AND `get_livebets_client` (return a `FakeLiveBetsClient`) AND, for the placed/settled routes, override `get_async_session` to yield a session — OR keep those two routes in the testcontainer-backed module and assert only `GET /tables` + `POST /session` here (they need no DB). Choose the lighter split: assert `GET /api/live/tables` returns 200 with the faked tables and `POST /api/live/session` returns 200 with the faked token via dependency overrides; leave the DB-touching placed/settled happy path to Task 1's bridge tests (which already prove the money path). Reuse the `FakeLiveBetsClient` from `test_livebets_bridge.py` via a shared import or a small local copy.
   - Always clean up `app.dependency_overrides` in a fixture teardown (mirror existing router tests so overrides do not leak across tests).
  </action>
  <verify>
    <automated>cd backend && uv run pytest tests/integrations/livebets/test_migration_0011.py tests/integrations/livebets/test_livebets_router.py -x -q</automated>
    <automated>cd backend && uv run pytest tests/integrations/livebets -q</automated>
  </verify>
  <done>The migration test proves `livebets_bets` + the `livebets_escrow` singleton appear after upgrade and disappear after downgrade (schema restored to head before teardown); the router test proves all four `/api/live/*` routes 401 unauthenticated and that `GET /tables` + `POST /session` succeed with overridden client/auth dependencies; the full `tests/integrations/livebets` suite is green.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| test -> code under test | Tests are trusted; they assert the production trust boundaries (verification, idempotency, auth) hold. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-LBA-T01 | Tampering | tests pass while the real money path is broken | mitigate | Tests assert exact ledger deltas (escrow nets to zero, house_promo/house_revenue deltas), not just status codes — a wrong account or amount fails the assertion. |
| T-LBA-T02 | Repudiation | flaky shared-singleton state hides regressions | mitigate | Use BEFORE/AFTER deltas on shared singletons and fresh UUIDs per test (the established pattern in `test_resolve_market.py`); the migration test restores head before teardown. |
| T-LBA-SC | Tampering | npm/pip/cargo installs | mitigate | No new packages: pytest, pytest-asyncio, testcontainers, httpx are already in `pyproject.toml`. No package-legitimacy checkpoint required. |
</threat_model>

<verification>
- New suite green: `cd backend && uv run pytest tests/integrations/livebets -q`.
- No regression in existing suites (zero behavior change, LB-A-SC2): `cd backend && uv run pytest tests/wallet tests/bets tests/settlement -q` stays green.
- Tests are hermetic — no live network to live-bets (the faked client is the only bet source); grep confirms no `httpx.AsyncClient`/real base-URL call in the test files.
</verification>

<success_criteria>
- `cd backend && uv run pytest` is green for the new module, covering placed->won, placed->lost, void/refund, duplicate-event no-op, escrow-nets-to-zero, and verification-rejects-mismatch (LB-A-SC6).
- Idempotency and escrow-nets-to-zero are proven by assertion, not prose (LB-A-SC4).
- Server-side verification is proven: a status/stake mismatch raises with no ledger entry (LB-A-SC5).
- The additive migration applies and reverses cleanly; existing wallet/bets/settlement suites still pass (LB-A-SC2).
- All four `/api/live/*` routes reject unauthenticated requests (LB-A-SC1).
</success_criteria>

<output>
Create `.planning/phases/LB-A-backend-bridge/LB-A-02-SUMMARY.md` when done.
</output>
