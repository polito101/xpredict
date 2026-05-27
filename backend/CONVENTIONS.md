# Backend Conventions

> Lock document — every Phase 2+ contributor reads this BEFORE writing code.
> Anything below is the result of Phase 1 decisions in
> `.planning/phases/01-scaffold-foundations/01-CONTEXT.md`. Diverging requires a
> phase-context update, not a quiet refactor.

---

## 1. Money columns (D-17, D-18, WAL-05)

**Every money column uses `Mapped[Money]`.** The `Money` alias is defined once in
`app/db/types.py` as:

```python
Money = Annotated[Decimal, mapped_column(Numeric(18, 4), nullable=False)]
```

Rules enforced by `scripts/lint_money_columns.py` (runs in pre-commit and CI):

- **R1** — Any `Numeric(p, s)` in a `mapped_column` must have `p == 18, s == 4`.
- **R2** — Columns named `amount`, `balance`, `price`, `stake`, `payout`, `fee`,
  `volume`, `liquidity`, `credit`, `debit`, `cost`, `value` MUST use `Mapped[Money]`
  (or a direct `Numeric(18, 4)` for the nullable exception below).
- **R3** — `Numeric(18, 4)` on a non-money-named column emits a WARNING (typo
  detector); not a failure.

**Nullable money** (Pitfall 4 — `Annotated`-baked kwargs can't be overridden):

```python
refund_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
```

The lint still validates the type. Never use `Float`, `REAL`, or Postgres `MONEY`.

---

## 2. `tenant_id` ghost column policy (D-42, PLT-01)

**Every player-owned and market table in v1 declares a nullable `tenant_id`
column with a fixed default constant.** Pattern:

```python
from uuid import UUID as PyUUID
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.config import Settings

tenant_id: Mapped[PyUUID | None] = mapped_column(
    UUID(as_uuid=True),
    nullable=True,
    default=lambda: Settings().TENANT_ID_DEFAULT,
)
```

The default UUID lives in `Settings.TENANT_ID_DEFAULT`
(`00000000-0000-0000-0000-000000000001`). In v1 every row has this exact value;
v2 multi-tenant flips `nullable=False`, swaps the default to a contextvar lookup,
and adds RLS policies — none of those steps require schema changes here.

**`audit_log` and `feature_flags` carry this column** in Phase 1's baseline
migration (D-19, D-37) to model the pattern.

---

## 3. Audit-event naming (D-40)

Event types are **dotted lowercase `domain.action`**. Phase prefixes:

| Phase | Domain prefix examples |
| ----- | ---------------------- |
| 2     | `auth.guest_created`, `auth.session_started`, `auth.session_revoked` |
| 3     | `wallet.transfer.completed`, `wallet.deposit.failed`, `wallet.recharge_admin` |
| 4     | `market.created`, `market.opened`, `market.closed`, `market.resolved` |
| 5     | `bet.placed`, `bet.settled`, `bet.refunded` |
| 6     | `polymarket.sync.completed`, `polymarket.sync.failed` |
| 7     | `settlement.completed`, `settlement.requeued` |
| 8     | `admin.user.banned`, `admin.user.balance_credited` |
| ?     | `cleanup.guest_purge`, `cleanup.market_archive` (cron sweeps) |

Use the singular noun (`market` not `markets`); use past-tense for completion
(`completed`, `failed`, `revoked`) and present for ongoing (`opened`, `running`).

---

## 4. `SET LOCAL` only (D-41, PITFALLS.md #7)

**Never run `SET app.tenant_id = ...` — only `SET LOCAL app.tenant_id = ...`**.
Session-level Postgres GUCs survive the connection's return to the asyncpg pool
and leak across requests. v1 has no runtime multi-tenant scope so this doctrine
is dormant; v2 makes it load-bearing. Lock it now so the muscle memory is
correct when RLS arrives.

---

## 5. Alembic migrations run via the sync engine (D-16)

Alembic is sync-only by design. `env.py` reads `DATABASE_URL_SYNC` (psycopg2)
from Settings. The app uses asyncpg via `DATABASE_URL`. Both env vars exist in
`.env.example`; never collapse them.

Run migrations via `docker compose exec backend uv run alembic upgrade head`
(Pitfall 2) — running from the host with `localhost` in the URL is fine for
host-side Alembic but always re-verify the URL inside containers.

---

## 6. Audit log is APPEND-ONLY (D-20, D-21, PLT-02)

**Phases 2-10 MUST NOT write raw `INSERT INTO audit_log` from any code path.**
The single allowed API is `AuditService.record(session, *, actor, event_type,
payload, ip=None, tenant_id=None)`. Caller passes its own `AsyncSession`; the
audit row commits atomically with the underlying action (no separate
transaction, no async event bus).

Defense in depth on the DB side:

1. `BEFORE UPDATE OR DELETE` trigger raises
   `'audit_log is append-only -- UPDATE and DELETE are forbidden'`.
2. `REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC` — the GRANT layer fails
   first.

Both are exercised by the integration tests in
`tests/core/test_audit_immutability.py` (Phase 1 Plan 01-03).

---

## 7. Settings reads only — never `os.getenv` (D-09, PLT-03)

All env-driven configuration goes through `Settings()` in `app/core/config.py`.
Never call `os.getenv` from app code — it bypasses validation, escapes the
structlog scrub list, and breaks the audit story for "where does this value
come from."

`Settings(extra="ignore")` is mandatory (Pitfall 3). New env vars added by
future phases append to `Settings`; older code paths must not raise
`ValidationError` because they encounter a new key.

---

## 8. Logging contract (D-23, D-24, D-25, D-26)

- **structlog only.** No `print()`, no `loguru`, no raw `logging.getLogger`.
- One `configure_logging(settings)` call per process at startup (FastAPI
  lifespan; Celery `worker_process_init` and `beat_init` signals).
- Renderer: `ConsoleRenderer(colors=True)` when `settings.is_dev`,
  `JSONRenderer()` otherwise.
- The `scrub_secrets` processor masks values for keys in `SCRUB_KEYS`
  (`password`, `password_hash`, `session_signing_key`, `admin_token`,
  `sentry_dsn`, `api_key`, `secret`, `xp_session`).
- FastAPI binds `request_id`, `path`, `method`, `client_ip` to contextvars via
  `RequestIdMiddleware` (pure ASGI — not `BaseHTTPMiddleware`); Celery binds
  `task_id`, `task_name` in `task_prerun` and clears in `task_postrun`
  (Pitfall 7).

---

## 9. Sentry tagging (D-27, D-28)

Four init points, one project per environment, every event tagged
`service=api|worker|beat|frontend`. Init lives in:

- FastAPI lifespan (`init_sentry("api", settings, integrations=[FastApiIntegration(), SqlalchemyIntegration()])`).
- Celery `worker_process_init` signal (`init_sentry("worker", ...)`).
- Celery `beat_init` signal (`init_sentry("beat", ...)`).
- `frontend/instrumentation.ts` + `instrumentation-client.ts` (Plan 01-02).

Pitfall 5 — Sentry SDK is process-global; init MUST NOT happen at module load
time in Celery (the worker process inherits parent state otherwise).
