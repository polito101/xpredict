# Phase 18 — Research & Pattern Mapping

**Method:** 3 parallel read-only analysis agents over the merged backend (event domain · catalog/category
surfacing · integrity check + seed tests), then direct read-verification of the load-bearing transaction
semantics. All file:line refs verified against the working tree at branch base `e627224`.

## Pattern map (new work → closest existing analog)

| New seed work | Mirror / reuse | Source |
|---|---|---|
| Create a house event | `EventService.create_house_event(session, admin_id, body)` | `event_service.py:634` |
| Event request body | `CreateEventRequest` + `OutcomeInput(label, initial_odds∈(0,1))`, outcomes≥2 | `event_schemas.py:21,41` |
| Resolve a house event | `EventService.resolve_event(group_id, winner_yes_outcome_id, justification, actor)` | `event_service.py:217` |
| Void a house event | `EventService.void_event(group_id, justification, actor)` | `event_service.py:327` |
| **Partial** event (1 child settled) | `SettlementService.resolve_market(session, market_id, winning_outcome_id, HouseMarketResolveAdapter(), …)` — fresh session, exactly the existing `seed_resolutions` call | `service.py:84`, `seed_demo.py:730` |
| Derived event status | `derive_event_status(children) → {open,partially_resolved,resolved,void}` (pure) | `event_service.py:105` |
| Read back child YES/NO outcome ids | mirror `seed_markets` post-commit outcome read (`select(Outcome.id, Outcome.label).where(market_id==…)`) | `seed_demo.py:524` |
| Event-child odds history | reuse `seed_odds_history` over `SeededMarket`-shaped children (`_odds_walk` non-flat series) | `seed_demo.py:559,575` |
| Event-child bets | mirror `seed_bets` both-sides spread via `BetService.place_bet` + `HouseMarketReadAdapter`, session-per-bet | `seed_demo.py:673` |
| Funding / money discipline | `WalletService.grant_signup_bonus`/`recharge`, Decimal-from-string, session-per-call | `seed_demo.py:195` |
| Integrity check | `app.wallet.reconcile._reconcile_async(session=None) → {accounts_checked,drift_count}`; GREEN=drift 0; baseline-relative in tests | `reconcile.py:61`, `test_seed_demo_e2e.py:81` |
| Category vocabulary (pinned) | `settings.POLYMARKET_CATEGORIES` → `[Politics,Sports,Crypto,Pop Culture,Economy,Tech,World]` | `config.py:132` |
| Category surfacing rule (CAT-06) | a category shows if ≥1 group has it (no status filter) OR ≥1 visible standalone market | `catalog/service.py:291` |
| Test harness | parent `engine` fixture = testcontainers PG16 + `alembic upgrade head`; `async_session`; `pytest.mark.integration` + asyncio session loop | `tests/conftest.py`, `test_seed_demo_e2e.py:30` |

## Load-bearing constraints (verified by direct read)

1. **23505 dangling-tx landmine** — self-committing services (`grant_signup_bonus`/`recharge`/`place_bet`/
   `resolve_market`/`resolve_event`) must each run on their OWN fresh session; never chain two in one
   `with`/`begin()`. `create_house_event` is a plain-ORM insert + single commit (NOT a settle loop) → safe
   on its own session. `resolve_event`/`void_event` open their own per-child sessions internally.
2. **`resolve_event` CR-01 guard** — `winning_outcome_id` MUST be the winner child's **YES** outcome
   (passing NO would settle every child NO → derive "void" with a mismatched audit). The seed passes the
   read-back YES id of the chosen winner child.
3. **`market_groups` not in `_RESET_TABLES`** — confirmed omission; `markets.group_id→market_groups.id`
   means truncating `markets` leaves groups orphaned → deterministic slug re-seed collides on the UNIQUE
   `market_groups.slug`. **Must add `market_groups` to the reset set** (DEMO-04).
4. **Event children carry no creation-time OddsSnapshot** (`_add_event_child` seeds Outcomes only) — the
   backfill (`seed_odds_history`) supplies the non-flat history; ≥2 points in every chart window (DEMO-02).
5. **Create-validator forbids past deadlines** — resolved/void events keep a FUTURE deadline (admin resolve
   is deadline-independent); they still derive `resolved`/`void` and land in the catalog "resolved" bucket.

## Open questions — resolved

- *How to get `partially_resolved` through the real ledger?* → settle ONE child via `SettlementService.resolve_market` (D2).
- *Idempotency of deterministic group slugs?* → safe because the whole seed is guarded by the demo-admin marker and `--reset` wipes first (now incl. `market_groups`).
- *Does seeding ≥1 event per category fill the tab?* → yes; groups surface a category with no status filter (CAT-06).
