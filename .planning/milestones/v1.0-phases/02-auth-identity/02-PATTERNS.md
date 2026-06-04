# Phase 2: Auth & Identity - Pattern Map

**Mapped:** 2026-05-26
**Files analyzed:** 16 new/modified files
**Analogs found:** 12 / 16 strong matches (3 no-analog frontend pages, 1 net-new admin seeding script)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/app/auth/models.py` | model (ORM) | CRUD | `backend/app/core/audit/models.py` + `backend/app/core/feature_flags/models.py` | role-match (no `SQLAlchemyBaseUserTableUUID` mixin in repo yet) |
| `backend/app/auth/schemas.py` | schema (Pydantic) | request-response | — (no Pydantic schemas in Phase 1 yet) | no-analog; use RESEARCH §"Common Operation 2" |
| `backend/app/auth/manager.py` | service (UserManager) | event-driven (lifecycle hooks) | `backend/app/core/audit/service.py` (staticmethod service shape) | role-match (different lifecycle shape) |
| `backend/app/auth/strategy.py` | service (token store) | CRUD | `backend/app/core/audit/service.py` (session-bound writes) | role-match |
| `backend/app/auth/email.py` | service (transport) | request-response (one-shot send) | `backend/app/core/redis.py` (env-driven singleton) | role-match (no email sender in repo yet) |
| `backend/app/auth/rate_limit.py` | utility (Limiter factory) | request-response | `backend/app/core/redis.py` (Redis client factory) | role-match |
| `backend/app/auth/deps.py` | utility (re-exports) | request-response | `backend/app/db/session.py` (`get_async_session` dependency) | role-match |
| `backend/app/auth/router.py` | controller (router builder) | request-response | `backend/app/routers/health.py` (APIRouter + Depends pattern) | exact-role |
| `backend/app/core/config.py` (MODIFY) | config | — | self (extend in place) | exact |
| `backend/app/main.py` (MODIFY) | bootstrap | — | self (extend in place) | exact |
| `backend/alembic/versions/0002_phase2_auth.py` | migration | DDL | `backend/alembic/versions/0001_phase1_foundations.py` | exact |
| `backend/bin/create-admin.py` | utility (CLI) | one-shot batch | `backend/scripts/lint_money_columns.py` (CLI w/ `if __name__`) | role-match (no async CLI yet) |
| `backend/tests/auth/conftest.py` | test fixture | — | `backend/tests/conftest.py` | exact |
| `backend/tests/auth/test_*.py` (10 files) | test (integration) | — | `backend/tests/core/test_audit_immutability.py` + `test_health.py` | exact |
| `frontend/src/app/(auth)/{login,register,forgot-password,verify-email}/page.tsx` | component (Next.js page) | request-response | `frontend/src/app/page.tsx` (server component shell only) | partial — RSC shell exists, form + Server Action net-new |
| `frontend/src/app/admin/login/page.tsx` | component | request-response | same as above | partial |
| `frontend/src/middleware.ts` | middleware (Edge) | request-response | — (no middleware in repo yet) | no-analog; use RESEARCH §"Pattern 5" |

---

## Pattern Assignments

### `backend/app/auth/models.py` (model, CRUD)

**Analog:** `backend/app/core/audit/models.py` (lines 1-52) and `backend/app/core/feature_flags/models.py` (lines 1-41)

**Imports + module-docstring pattern** (audit/models.py lines 1-19):
```python
"""AuditLog ORM model (D-19, PLT-02).

Schema is locked here; the Alembic 0001 baseline migration (Plan 01-03) creates
the table to match this declaration. Defense-in-depth immutability lives at the
DB layer (BEFORE UPDATE/DELETE trigger + REVOKE) — see Plan 01-03.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID as PyUUID, uuid4

from sqlalchemy import DateTime, Text, func
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import get_settings
from app.db.base import Base
```

**UUID PK + Python+server default pattern** (audit/models.py lines 26-33):
```python
id: Mapped[PyUUID] = mapped_column(
    UUID(as_uuid=True),
    primary_key=True,
    default=uuid4,                      # Python-side default (WR-05): id is set
    server_default=func.gen_random_uuid(),  # immediately on construction, no
    # pre-flush None window. server_default is still present for raw SQL inserts.
)
```

**timestamptz with server-default NOW pattern** (audit/models.py lines 34-38):
```python
occurred_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    server_default=func.now(),
    nullable=False,
)
```

**`tenant_id` ghost column pattern** (audit/models.py lines 47-51 — replicate verbatim for `User.tenant_id`):
```python
tenant_id: Mapped[PyUUID | None] = mapped_column(
    UUID(as_uuid=True),
    nullable=True,
    default=lambda: get_settings().TENANT_ID_DEFAULT,
)
```

**Integer column with server_default pattern** (feature_flags/models.py lines 28-30 — replicate for `token_version` and `reuse_count`):
```python
enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
```
> Note: Phase 2 needs `Integer` with `server_default="0"` — see RESEARCH lines 1095-1097 for the exact `token_version` column spec. Use `Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)`.

**Apply notes:**
- `User` MUST be `class User(SQLAlchemyBaseUserTableUUID, Base):` — multiple inheritance per D-02. Import `Base` from `app.db.base`, `SQLAlchemyBaseUserTableUUID` from `fastapi_users_db_sqlalchemy`.
- `RefreshToken(Base)` — single inheritance.
- `User.refresh_tokens` relationship: `Mapped[list[RefreshToken]] = relationship(back_populates="user", cascade="all, delete-orphan")`
- Full models content matches RESEARCH §"Common Operation 1" lines 1062-1147 verbatim — copy that.

---

### `backend/app/auth/schemas.py` (schema, request-response)

**Analog:** No Pydantic schemas exist in Phase 1 (only `Settings(BaseSettings)`). Use RESEARCH §"Common Operation 2" (lines 1149-1192) as the template.

**Source pattern** (RESEARCH lines 1156-1191 — copy directly):
```python
import uuid

from fastapi_users import schemas
from pydantic import EmailStr, computed_field


class UserRead(schemas.BaseUser[uuid.UUID]):
    """API representation — exposes is_admin, hides is_superuser."""

    display_name: str | None = None
    is_superuser: bool = False

    @computed_field
    @property
    def is_admin(self) -> bool:
        return self.is_superuser


class UserCreate(schemas.BaseUserCreate):
    display_name: str | None = None


class UserUpdate(schemas.BaseUserUpdate):
    display_name: str | None = None
```

**Apply notes:**
- `from __future__ import annotations` per Phase 1 convention (all `.py` files have it).
- Use `Field(exclude=True)` on `is_superuser` to ensure it doesn't leak through `model_dump()`. RESEARCH lines 1193-1194 flag this as an open verification item; planner should pick `Field(exclude=True)` over `computed_field` for clarity, OR include both for defense-in-depth.

---

### `backend/app/auth/manager.py` (service, event-driven)

**Analog:** `backend/app/core/audit/service.py` (lines 1-59) — same "module-docstring locking signature + staticmethod" shape, though `UserManager` is a class with instance state (the `email_service`).

**Module docstring locking pattern** (audit/service.py lines 1-11):
```python
"""AuditService — the SINGLE allowed entry point for inserting audit rows (D-20, D-21).

Phases 2-10 MUST NOT run raw ``INSERT INTO audit_log`` from any code path. Use
``AuditService.record()``. The audit row commits atomically with the underlying
action because the caller passes its own ``AsyncSession`` — no async event bus,
no background queue.
"""
```

**Apply notes:**
- `UserManager(UUIDIDMixin, BaseUserManager[User, UUID])` — see RESEARCH §"Pattern 3" plumbing block (lines 690-721) for the canonical shape.
- `reset_password_token_secret = get_settings().SECRET_KEY` + `verification_token_secret = get_settings().SECRET_KEY` — assign at class-body level (these are fastapi-users conventions, not instance attrs).
- `validate_password` body: RESEARCH §"Common Operation 3" lines 1205-1223 — copy verbatim.
- `on_after_register`: trigger `self.request_verify(user, request)`; wrap in try/except per Pitfall 5 (lines 1000-1014). Log via `structlog.get_logger()` per Phase 1 convention.
- `on_after_reset_password`: bump `user.token_version` AND `UPDATE refresh_tokens SET revoked_at = NOW()` — per Pitfall 6 (lines 1019-1024).
- All four lifecycle hooks MUST call `await AuditService.record(session, actor=f"user:{user.id}", event_type="auth.*", ...)` — see CONTEXT lines 88, 1540. Audit event taxonomy is locked in `backend/CONVENTIONS.md §3`.

---

### `backend/app/auth/strategy.py` (service, CRUD with reuse detection)

**Analog:** `backend/app/core/audit/service.py` for the session-bound write pattern; the rest is net-new per RESEARCH §"Pattern 2".

**Session-bound write pattern** (audit/service.py lines 36-58 — strategy follows the same `session.add(row); await session.flush()` shape):
```python
@staticmethod
async def record(
    session: AsyncSession,
    *,
    actor: str,
    event_type: str,
    payload: dict[str, Any],
    ip: str | None = None,
    tenant_id: UUID | None = None,
) -> AuditLog:
    row = AuditLog(
        actor=actor,
        event_type=event_type,
        payload=payload,
        ip=ip,
        tenant_id=tenant_id or get_settings().TENANT_ID_DEFAULT,
    )
    session.add(row)
    await session.flush()
    return row
```

**Apply notes:**
- Full strategy body: RESEARCH §"Pattern 2" lines 505-602 — copy verbatim.
- **CRITICAL** Pitfall 9 (RESEARCH lines 1042-1049): the strategy must NOT call `await self.session.commit()` if the session is the request-scoped one — use a separate `async_sessionmaker()` for token operations OR `flush()` instead of `commit()`. **Planner decision required** — recommend approach (a) from Pitfall 9: own transaction lifetime via a fresh sessionmaker.
- `_hash(token)` helper stores SHA256 only (Anti-pattern: never store raw token).
- `get_database_strategy` is a FastAPI dependency that returns `DatabaseStrategy(session, lifetime_seconds=settings.REFRESH_TOKEN_LIFETIME_SECONDS)`.
- Uses the existing `get_async_session` from `app.db.session` — see session.py lines 51-60.

---

### `backend/app/auth/email.py` (service, request-response transport)

**Analog:** `backend/app/core/redis.py` (lines 1-29) — env-driven client factory, single class, settings-based configuration.

**Env-driven dependency pattern** (core/redis.py lines 17-29):
```python
async def get_redis() -> AsyncGenerator[Redis, None]:
    """FastAPI dependency yielding an async Redis client.

    Creates a fresh client per request and closes it on teardown. For Phases 2+
    that need a shared connection pool, consider promoting to a lifespan-managed
    singleton — but the per-request pattern keeps tests trivial.
    """
    settings = get_settings()
    client: Redis = Redis.from_url(str(settings.REDIS_URL), decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()
```

**Apply notes:**
- Full email service: RESEARCH §"Pattern 3" lines 614-684 — copy verbatim.
- `EmailService.__init__` reads `get_settings()` once; switches by `settings.is_dev`.
- HTML templates inline as module constants (`VERIFY_HTML`, `RESET_HTML`) per D-07.
- Mailpit branch uses `aiosmtplib.send` to `settings.SMTP_HOST:settings.SMTP_PORT` (no auth, no TLS in dev).
- Resend branch uses `await resend.Emails.send_async(params)` per RESEARCH line 116.
- Pitfall 5 (lines 1000-1014): never let SMTP outage block register — handled at the `UserManager.on_after_register` layer, not here.

---

### `backend/app/auth/rate_limit.py` (utility, request-response)

**Analog:** `backend/app/core/redis.py` (env-driven Redis-backed singleton).

**Apply notes:**
- `limiter = Limiter(key_func=get_remote_address, storage_uri=str(_settings.REDIS_URL) + "/1", default_limits=[], headers_enabled=True)` per RESEARCH §"Pattern 4" lines 743-749.
- Use Redis DB `/1` (DB `/0` is for general app cache; `/1` is dedicated to slowapi). Document this in module docstring.
- Export key funcs: `get_remote_address` (re-exported from `slowapi.util`) for per-IP; custom `email_key_func` for per-email.
- Pitfall 1 (lines 962-973): planner MUST choose **Option A (thin proxy routes)** — wrap fastapi-users login/register/forgot-password/verify endpoints with our own `@limiter.limit(...)` decorated routes; mount fastapi-users' actual router under a different prefix internally OR call the manager methods directly. Do NOT decorate fastapi-users-provided routes.

---

### `backend/app/auth/deps.py` (utility, re-exports)

**Analog:** `backend/app/db/session.py` lines 51-60 (the dependency-yielding generator).

**FastAPI dependency pattern** (db/session.py):
```python
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an ``AsyncSession``.

    Sessions are NOT auto-committed; callers control transaction boundaries.
    """
    session_maker = _get_session_maker()
    async with session_maker() as session:
        yield session
```

**Apply notes:**
- Re-export `current_active_player = fastapi_users_player.current_user(active=True, verified=True)` and `current_active_admin = fastapi_users_admin.current_user(active=True, superuser=True)` per RESEARCH §"Pattern 1" lines 448-449.
- Re-export `get_user_db` (FastAPI dependency producing `SQLAlchemyUserDatabase(session, User)` — see fastapi-users docs).
- Re-export `get_user_manager` (depends on `get_user_db` + `get_email_service`).
- Phase 3+ imports `current_active_player` from here.

---

### `backend/app/auth/router.py` (controller, request-response)

**Analog:** `backend/app/routers/health.py` (lines 1-61) — APIRouter + tags + Depends pattern.

**APIRouter + tags pattern** (routers/health.py lines 23):
```python
router = APIRouter(tags=["health"])
```

**Depends + route handler pattern** (routers/health.py lines 32-60):
```python
@router.get("/readyz")
async def readyz(
    session: AsyncSession = Depends(get_async_session),
    redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    """Readiness probe — DB + Redis both reachable."""
    failures: dict[str, str] = {}
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        failures["db"] = type(exc).__name__
    ...
    if failures:
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "failures": failures},
        )
    return {"status": "ready"}
```

**Apply notes:**
- Full router body: RESEARCH §"Pattern 1" lines 392-483 — copy `build_auth_routers() -> APIRouter` verbatim.
- Two `FastAPIUsers[User, uuid.UUID]` instances: `fastapi_users_player` with `cookie_transport`, `fastapi_users_admin` with `bearer_transport`. Both share the same `get_user_manager` dep but distinct backends per D-03.
- Mount routers under `/auth/*` (player) and `/admin/auth/*` (admin).
- For Pitfall 1: write thin proxy routes for `login`, `register`, `forgot-password`, `verify` — those carry the `@limiter.limit(...)` decorator stack. They internally call into the underlying fastapi-users route function or delegate to `UserManager` methods directly. Admin uses only `login` (admins are seeded, not registered).

---

### `backend/app/core/config.py` (config, MODIFY in place)

**Analog:** Self — extend the existing `Settings(BaseSettings)` class (D-09 + CONTEXT line 87 + RESEARCH lines 952-953).

**Existing Settings pattern** (config.py lines 22-48):
```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ENVIRONMENT: Literal["dev", "staging", "prod"] = "dev"
    DATABASE_URL: PostgresDsn
    DATABASE_URL_SYNC: PostgresDsn
    REDIS_URL: RedisDsn
    SENTRY_DSN: str | None = None
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    TENANT_ID_DEFAULT: UUID = UUID("00000000-0000-0000-0000-000000000001")

    @property
    def is_dev(self) -> bool:
        return self.ENVIRONMENT == "dev"
```

**Apply notes:** APPEND new fields (do NOT redefine the class) — per CONTEXT line 87 + RESEARCH line 953:
- `SECRET_KEY: str` (JWT signing + fastapi-users verification/reset token secrets)
- `JWT_ALGORITHM: Literal["HS256"] = "HS256"`
- `ACCESS_TOKEN_LIFETIME_SECONDS: int = 900` (15 min)
- `REFRESH_TOKEN_LIFETIME_SECONDS: int = 2_592_000` (30 days)
- `RESEND_API_KEY: str | None = None`
- `RESEND_FROM_ADDRESS: str = "noreply@xpredict.local"`
- `SMTP_HOST: str = "mailpit"`, `SMTP_PORT: int = 1025`
- `FIRST_ADMIN_EMAIL: str | None = None`, `FIRST_ADMIN_PASSWORD: str | None = None`
- `FRONTEND_BASE_URL: str = "http://localhost:3000"`
- `ADMIN_JWT_PUBLIC_SECRET: str | None = None` (mirrors SECRET_KEY but exposed to Next.js middleware; A8 in RESEARCH).
- Mirror all in `.env.example` with placeholders (gitleaks-safe). The Phase 2 comment block in `.env.example` lines 50-54 already reserves space.

---

### `backend/app/main.py` (bootstrap, MODIFY in place)

**Analog:** Self — extend the existing FastAPI factory.

**Existing factory pattern** (main.py lines 67-89):
```python
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Configure logging + Sentry at startup; nothing to tear down in Phase 1."""
    configure_logging(settings)
    init_sentry(
        service="api",
        settings=settings,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
    )
    yield


app = FastAPI(lifespan=lifespan, title="XPredict API")
app.add_middleware(RequestIdMiddleware)
app.include_router(health.router)
```

**Apply notes:**
- Add `SlowAPIMiddleware` after `RequestIdMiddleware`: `app.add_middleware(SlowAPIMiddleware)` + set `app.state.limiter = limiter` per slowapi convention.
- Add `CORSMiddleware` per Pitfall 7 (lines 1027-1031) — `allow_origins=[settings.FRONTEND_BASE_URL]`, `allow_credentials=True`. Do NOT use `["*"]` for origins.
- Add `app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)` per slowapi convention.
- Include the auth router: `app.include_router(build_auth_routers())` from `app.auth.router`.
- Do NOT regress the `RequestIdMiddleware` ordering — it must run FIRST so `structlog` contextvars are bound before any auth logic.

---

### `backend/alembic/versions/0002_phase2_auth.py` (migration, DDL)

**Analog:** `backend/alembic/versions/0001_phase1_foundations.py` (exact-role match).

**Revision header pattern** (0001_phase1_foundations.py lines 1-32):
```python
"""Phase 1 foundations: audit_log + feature_flags with tenant_id ghost column.

Revision ID: 0001_phase1_foundations
Revises:
Create Date: 2026-05-26
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_phase1_foundations"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None

TENANT_DEFAULT = "00000000-0000-0000-0000-000000000001"
```

**Table-create pattern with UUID PK + tenant_id** (0001_phase1_foundations.py lines 43-67):
```python
op.create_table(
    "audit_log",
    sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    ),
    sa.Column(
        "occurred_at",
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.text("NOW()"),
    ),
    sa.Column("actor", sa.Text, nullable=False),
    sa.Column("event_type", sa.Text, nullable=False),
    sa.Column("payload", postgresql.JSONB, nullable=False),
    sa.Column("ip", postgresql.INET, nullable=True),
    sa.Column(
        "tenant_id",
        postgresql.UUID(as_uuid=True),
        nullable=True,
        server_default=sa.text(f"'{TENANT_DEFAULT}'::uuid"),
    ),
)
op.create_index(
    "ix_audit_log_occurred_at",
    "audit_log",
    [sa.text("occurred_at DESC")],
)
```

**Downgrade pattern** (0001_phase1_foundations.py lines 144-161):
```python
def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_immutability_trigger ON audit_log;")
    op.execute("DROP FUNCTION IF EXISTS raise_audit_immutable();")
    op.drop_table("feature_flags")
    op.drop_index("ix_audit_log_actor", table_name="audit_log")
    op.drop_index("ix_audit_log_event_type", table_name="audit_log")
    op.drop_index("ix_audit_log_occurred_at", table_name="audit_log")
    op.execute("DROP TABLE IF EXISTS audit_log CASCADE;")
```

**Apply notes:**
- `revision: str = "0002_phase2_auth"`, `down_revision: str | None = "0001_phase1_foundations"`.
- Reuse the `TENANT_DEFAULT` constant.
- Full body: RESEARCH §"Common Operation 4" lines 1247-1306 — copy verbatim. Both `users` and `refresh_tokens` tables.
- Indexes: `ix_users_email UNIQUE`, `ix_refresh_tokens_token_hash UNIQUE`, `ix_refresh_tokens_user_id`.
- Downgrade order: drop FK-bearing table (`refresh_tokens`) BEFORE `users`. Drop indexes BEFORE tables.
- Test fixture in `tests/conftest.py` lines 124-171 runs `alembic upgrade head` against testcontainers — verify the new migration works under that path before merging.

---

### `backend/bin/create-admin.py` (utility CLI, batch)

**Analog:** `backend/scripts/lint_money_columns.py` (lines 1-292) — CLI pattern with `if __name__ == "__main__": sys.exit(...)`.

**CLI entry-point pattern** (lint_money_columns.py lines 290-291):
```python
if __name__ == "__main__":
    sys.exit(lint(Path("app")))
```

**Module docstring + invocation note** (lint_money_columns.py lines 1-17):
```python
"""Money-column AST lint (D-17, WAL-05) — pre-commit + CI gate.

Rules:
  R1. ...

Invoke from ``backend/``:
    uv run python scripts/lint_money_columns.py
The script walks ``app/**/models.py`` and ``app/**/*models*.py`` ...
"""
```

**Apply notes:**
- Full body: RESEARCH §"Common Operation 5" lines 1311-1366 — copy verbatim.
- Note that RESEARCH §"Component Responsibilities" line 323 places this at `backend/bin/create-admin.py` (not `scripts/`). The CONTEXT phase boundary lists `bin/create-admin.py` (line in pattern_mapping_context). **Path decision for planner: use `backend/bin/create-admin.py`** to match RESEARCH and CONTEXT D-11 (line 56 of CONTEXT).
- Idempotency: `SELECT User WHERE email == FIRST_ADMIN_EMAIL` first; if exists → print + return 0.
- Use `pwdlib.PasswordHash.recommended()` for hashing (same hasher fastapi-users uses).
- Document invocation in module docstring: `uv run python bin/create-admin.py` (per CONTEXT line 128).
- Must be runnable via `uv run` — no `__init__.py` needed; `pyproject.toml` `[tool.pytest.ini_options] pythonpath = [".", "scripts"]` does NOT include `bin` — planner may need to add `bin` to pythonpath OR invoke via `python -m bin.create_admin` after creating `bin/__init__.py`. Recommendation: add `bin/__init__.py` + register in pyproject.

---

### `backend/tests/auth/conftest.py` (test fixture)

**Analog:** `backend/tests/conftest.py` (lines 1-199) — exact match.

**Env-seeding pattern** (conftest.py lines 49-59 — Phase 2 adds new env keys):
```python
_DEFAULT_TEST_ENV: dict[str, str] = {
    "ENVIRONMENT": "dev",
    "DATABASE_URL": "postgresql+asyncpg://xpredict:xpredict@localhost:5432/xpredict",
    "DATABASE_URL_SYNC": "postgresql+psycopg2://xpredict:xpredict@localhost:5432/xpredict",
    "REDIS_URL": "redis://localhost:6379/0",
    "SENTRY_DSN": "",
    "LOG_LEVEL": "INFO",
}

for _k, _v in _DEFAULT_TEST_ENV.items():
    os.environ.setdefault(_k, _v)
```
> Phase 2 adds: `SECRET_KEY`, `FIRST_ADMIN_EMAIL`, `FIRST_ADMIN_PASSWORD`, `FRONTEND_BASE_URL`, `SMTP_HOST`, `SMTP_PORT`, `RESEND_API_KEY=""`. Either extend the parent conftest OR redeclare in `tests/auth/conftest.py` (planner choice — extending parent is simpler).

**Async client fixture pattern** (conftest.py lines 80-95):
```python
@pytest_asyncio.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    import httpx
    from app.main import app

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

**Apply notes:**
- Add auth-specific fixtures: `verified_user`, `unverified_user`, `admin_user`, `mailpit_messages` (per RESEARCH line 1478).
- For `mailpit_messages`: Mailpit exposes an HTTP API at `http://mailpit:8025/api/v1/messages` — clear between tests and assert message presence. Use `httpx.AsyncClient` to talk to it.
- For Redis rate-limit tests: use `fakeredis` (already in dev deps per `pyproject.toml` line 45) OR flush keys between tests.

---

### `backend/tests/auth/test_*.py` — 10 integration test files (test)

**Analog:** `backend/tests/core/test_audit_immutability.py` (lines 1-137) and `backend/tests/core/test_feature_flags.py` (lines 1-119) — exact match.

**Integration pytestmark pattern** (test_audit_immutability.py lines 22-28):
```python
pytestmark = [
    pytest.mark.integration,
    # Share the session-scoped event loop with the engine + async_session
    # fixtures (pytest-asyncio 0.25: fixtures and tests must agree on loop
    # scope or asyncpg connections get cross-loop "Event loop is closed").
    pytest.mark.asyncio(loop_scope="session"),
]
```

**Async test with session fixture pattern** (test_audit_immutability.py lines 62-83):
```python
async def test_audit_service_record(async_session: AsyncSession) -> None:
    """``AuditService.record()`` inserts via caller's session; row visible after flush."""
    row = await AuditService.record(
        async_session,
        actor="test",
        event_type="test.event",
        payload={"key": "val"},
    )

    assert row.id is not None
    assert row.actor == "test"
    ...
    stmt = select(AuditLog).where(AuditLog.event_type == "test.event")
    found = (await async_session.execute(stmt)).scalar_one()
    assert found.actor == "test"
```

**Health-endpoint test with dependency_overrides pattern** (test_health.py lines 82-92 — apply for any endpoint test that wants to mock deps):
```python
async def test_readyz_returns_ready_when_deps_ok(client: httpx.AsyncClient) -> None:
    """GET /readyz returns 200 + {"status":"ready"} when both deps respond."""
    app.dependency_overrides[get_async_session] = _override_session()
    app.dependency_overrides[get_redis] = _override_redis()
    try:
        response = await client.get("/readyz")
        assert response.status_code == 200
        assert response.json() == {"status": "ready"}
    finally:
        app.dependency_overrides.clear()
```

**Apply notes:**
- 10 test files match RESEARCH lines 1477-1488: `test_register.py`, `test_login.py`, `test_logout.py`, `test_email_verification.py`, `test_password_reset.py`, `test_refresh_rotation.py`, `test_admin_bearer.py`, `test_rate_limit.py`, `test_email_enumeration.py`. Plus `tests/auth/__init__.py` (empty marker) and `tests/auth/conftest.py`.
- All MUST have `pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]` for the testcontainers Postgres + `async_session` fixture.
- Refresh-token reuse-detection test (AUTH-09 critical): registers user → logs in (token A issued) → logs out (token A revoked) → presents token A again → assert ALL user's tokens are revoked (the reuse-detection branch in `DatabaseStrategy.read_token`). RESEARCH line 1465.
- Rate-limit test (AUTH-08): 5 successful logins → 6th returns 429. Use `fakeredis` or per-test Redis flush.
- Email-enumeration test (AUTH-08): forgot-password to unknown email returns 202 (matches known-email response). Timing variance < 50 ms (RESEARCH line 1040).

---

### `frontend/src/app/(auth)/{login,register,forgot-password,verify-email}/page.tsx` (Next.js page, request-response)

**Analog:** `frontend/src/app/page.tsx` (partial — only the RSC shell exists; no forms, no Server Actions, no shadcn yet).

**Existing RSC shell pattern** (page.tsx full):
```tsx
export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-4 px-6 py-24 text-center">
      <h1 className="text-4xl font-semibold tracking-tight">XPredict</h1>
      <p className="text-base text-zinc-600 dark:text-zinc-400">
        Phase 1 &mdash; scaffold OK
      </p>
    </main>
  );
}
```

**Apply notes:**
- Wrap `(auth)` segment with `app/(auth)/layout.tsx` providing a centered card layout. Route-group `(auth)` = no URL segment.
- Login page: Server Component shell that renders a Client Component `<LoginForm />`. Form uses `useActionState` (Next 15 idiom) bound to a `loginAction` Server Action defined in `frontend/src/lib/auth.ts`.
- Server Action full body: RESEARCH §"Pattern 5" lines 822-878 — copy verbatim.
- shadcn/ui: install via `pnpm dlx shadcn@latest add form input button label card` per RESEARCH line 168. Components live in `frontend/src/components/ui/`.
- Form schema with zod: RESEARCH §"Pattern 5" lines 829-832 (also RESEARCH line 131).
- Submits to FastAPI via `fetch(`${BACKEND_URL}/auth/login`, { credentials: "include" })` per RESEARCH line 849.

---

### `frontend/src/app/admin/login/page.tsx` (Next.js page, request-response)

**Analog:** Same as `(auth)/login` but with Bearer flow instead of cookie flow.

**Apply notes:**
- After successful POST to `/admin/auth/login`, parse the JSON Bearer token from response body, then `cookies().set('admin_jwt', token, { httpOnly: true, secure: !is_dev, sameSite: 'lax', path: '/' })`. Middleware reads this cookie.
- The `app/admin/` segment has its own `layout.tsx` (separate navbar per D-13) — net-new file; no analog. Use the same `app/layout.tsx` (lines 1-19) pattern: an HTML wrapper + `<body>` styling, but with admin-specific nav.

---

### `frontend/src/middleware.ts` (middleware, Edge runtime)

**Analog:** None — no middleware exists in `frontend/src/`. Use RESEARCH §"Pattern 5 admin middleware" (lines 883-911) as the template.

**Source pattern** (RESEARCH lines 884-911 — copy directly):
```typescript
import { NextRequest, NextResponse } from 'next/server'
import { jwtVerify } from 'jose'

const ADMIN_PROTECTED = /^\/admin(\/|$)/
const ADMIN_LOGIN = '/admin/login'

export async function middleware(req: NextRequest) {
  if (!ADMIN_PROTECTED.test(req.nextUrl.pathname)) return NextResponse.next()
  if (req.nextUrl.pathname === ADMIN_LOGIN) return NextResponse.next()

  const token = req.cookies.get('admin_jwt')?.value
  if (!token) return NextResponse.redirect(new URL(ADMIN_LOGIN, req.url))

  try {
    const secret = new TextEncoder().encode(process.env.ADMIN_JWT_PUBLIC_SECRET!)
    await jwtVerify(token, secret, { algorithms: ['HS256'] })
    return NextResponse.next()
  } catch {
    return NextResponse.redirect(new URL(ADMIN_LOGIN, req.url))
  }
}

export const config = {
  matcher: ['/admin/:path*'],
}
```

**Apply notes:**
- Edge runtime (default in Next.js 15). Do NOT use Node-only APIs (no DB queries — Anti-pattern in RESEARCH line 923).
- This is OPTIMISTIC — the FastAPI `current_active_admin` guard is the authoritative gate (RESEARCH lines 913-914).
- Add `frontend/src/__tests__/middleware.test.ts` per RESEARCH line 1489. Use vitest in node environment (matches existing `vitest.config.ts`).

---

### `frontend/src/app/(auth)/login/page.test.tsx` and `frontend/src/__tests__/middleware.test.ts` (frontend test)

**Analog:** `frontend/src/app/api/healthz/route.test.ts` (lines 1-11) — exact match.

**Vitest pattern** (healthz/route.test.ts full):
```typescript
import { describe, it, expect } from "vitest";
import { GET } from "./route";

describe("/api/healthz", () => {
  it("returns 200 with status ok", async () => {
    const res = await GET();
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body).toEqual({ status: "ok" });
  });
});
```

**Apply notes:**
- `vitest.config.ts` (frontend) currently uses `environment: "node"` (line 7). For component tests with React render, planner MUST switch to `environment: "jsdom"` for `*.test.tsx` files (use `environmentMatchGlobs` or split configs).
- Component testing library: not yet installed — planner adds `@testing-library/react` + `@testing-library/jest-dom`. The current Phase 1 frontend has only API-route tests (no React component tests).
- Middleware test: import the `middleware` function, construct a `NextRequest` with the test URL + cookie, assert the returned `NextResponse` is a redirect / passthrough.

---

## Shared Patterns

### Authentication Audit Event Pattern
**Source:** `backend/app/core/audit/service.py` lines 27-58
**Apply to:** Every state mutation in `UserManager` hooks (register, login, logout, verify, reset).

```python
await AuditService.record(
    session,
    actor=f"user:{user.id}",
    event_type="auth.session_started",   # or auth.email_verified, auth.password_reset_requested etc.
    payload={"client_ip": ip, "user_agent": ua},
    ip=ip,
)
```

**Event taxonomy (locked in `backend/CONVENTIONS.md §3`, repeated in RESEARCH line 1540):**
- `auth.guest_created` — register
- `auth.session_started` — login
- `auth.session_revoked` — logout / password reset cascade
- `auth.email_verified` — verify
- `auth.password_reset_requested` — forgot-password
- `auth.password_reset_completed` — reset-password
- `auth.admin_login_started` — admin login success
- `auth.admin_login_failed` — admin login failure

The audit row commits atomically in the caller's transaction (D-21) — never call `commit()` from inside `AuditService.record`.

---

### Tenant ID Ghost Column Pattern
**Source:** `backend/app/core/audit/models.py` lines 47-51
**Apply to:** `User.tenant_id` (D-08 + RESEARCH line 1098-1102).

```python
tenant_id: Mapped[PyUUID | None] = mapped_column(
    UUID(as_uuid=True),
    nullable=True,
    default=lambda: get_settings().TENANT_ID_DEFAULT,
)
```

`RefreshToken` does NOT need `tenant_id` (it inherits via `user_id` FK — same multi-tenant scope as the user).

---

### UUID PK with Dual Default Pattern
**Source:** `backend/app/core/audit/models.py` lines 27-33
**Apply to:** `RefreshToken.id` (and any new ORM models that aren't auto-defaulted by fastapi-users base).

```python
id: Mapped[PyUUID] = mapped_column(
    UUID(as_uuid=True),
    primary_key=True,
    default=uuid4,                      # Python-side default
    server_default=func.gen_random_uuid(),  # DB-side default for raw SQL
)
```

`User.id` is provided by `SQLAlchemyBaseUserTableUUID` — do NOT redeclare it.

---

### Settings Extension Pattern
**Source:** `backend/app/core/config.py` lines 22-48
**Apply to:** Every new env var in Phase 2.

**Rules:**
1. APPEND to `class Settings(BaseSettings)` — never redefine the class (RESEARCH line 953).
2. Use `Literal` for closed-set strings (e.g., `JWT_ALGORITHM: Literal["HS256"] = "HS256"`).
3. Use `Optional[str] = None` for secrets that may be absent in dev (e.g., `RESEND_API_KEY`).
4. Mirror every new var in `.env.example` with a placeholder. gitleaks pre-commit checks this.
5. The `extra="ignore"` mode (line 33) means an unknown env var doesn't fail boot — but adding a new var to `Settings` without updating `.env.example` will lint-fail.

---

### Pure-ASGI Middleware Pattern
**Source:** `backend/app/main.py` lines 37-64 (RequestIdMiddleware)
**Apply to:** ANY new ASGI middleware (e.g., the planner must NOT use `BaseHTTPMiddleware` — RESEARCH note on Pitfall in Phase 1).

```python
class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # ... bind contextvars, call self.app, clean up
```

For Phase 2 specifically: `SlowAPIMiddleware` is provided by slowapi itself — use `app.add_middleware(SlowAPIMiddleware)`. The pure-ASGI rule applies if we ever write our own middleware.

---

### Integration Test Pattern
**Source:** `backend/tests/core/test_audit_immutability.py` lines 22-28
**Apply to:** All Phase 2 integration tests (every file in `tests/auth/`).

```python
pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]
```

This pairs with `tests/conftest.py` `engine` + `async_session` session-scoped fixtures (lines 124-198) so testcontainers Postgres is spun up once for the whole session, and `alembic upgrade head` applies the new `0002_phase2_auth` migration.

---

## No Analog Found

Files with no close match in the codebase (planner uses RESEARCH.md patterns or external docs):

| File | Role | Data Flow | Reason | Reference |
|------|------|-----------|--------|-----------|
| `backend/app/auth/schemas.py` | Pydantic schema | request-response | No `pydantic.BaseModel` schemas in Phase 1 (only `BaseSettings`) | RESEARCH §"Common Operation 2" lines 1149-1192 |
| `frontend/src/lib/auth.ts` (Server Actions) | Next.js Server Action | request-response | No Server Actions exist; no `lib/` directory yet | RESEARCH §"Pattern 5" lines 822-878 |
| `frontend/src/middleware.ts` | Edge middleware | request-response | No middleware exists | RESEARCH §"Pattern 5 admin middleware" lines 883-911 |
| `frontend/src/app/admin/layout.tsx` | Next.js admin layout | — | Only one layout (`app/layout.tsx`) exists, no nested `admin/` | Mirror `app/layout.tsx` shape with admin nav |

---

## Metadata

**Analog search scope:**
- `C:/Users/pobom/xpredict/backend/app/` — all subdirectories (auth, core, db, routers, integrations, wallet, markets, bets, admin)
- `C:/Users/pobom/xpredict/backend/alembic/versions/`
- `C:/Users/pobom/xpredict/backend/tests/`
- `C:/Users/pobom/xpredict/backend/scripts/`
- `C:/Users/pobom/xpredict/frontend/src/`

**Files scanned:** 27 Python modules + 5 TS/TSX files + 1 Alembic migration + 1 pyproject + 1 `.env.example`.

**Best-match files used as analogs (most-reused first):**
1. `backend/app/core/audit/models.py` — UUID PK, tenant_id ghost, server_default patterns
2. `backend/app/core/audit/service.py` — staticmethod service + session-bound writes + module-docstring lock
3. `backend/app/core/feature_flags/models.py` — composite PK + Boolean with default
4. `backend/alembic/versions/0001_phase1_foundations.py` — migration scaffolding, TENANT_DEFAULT, downgrade ordering
5. `backend/app/routers/health.py` — APIRouter + Depends + raise HTTPException patterns
6. `backend/app/core/config.py` — `Settings(BaseSettings)` with `extra="ignore"` and `is_dev` property
7. `backend/app/main.py` — FastAPI factory + lifespan + middleware ordering
8. `backend/app/db/session.py` — async session dependency
9. `backend/app/core/redis.py` — env-driven async client factory
10. `backend/tests/conftest.py` — testcontainers Postgres + async_session fixture + env seeding
11. `backend/tests/core/test_audit_immutability.py` — integration test pytestmark + `async_session` consumer
12. `backend/tests/test_health.py` — `app.dependency_overrides` mock pattern
13. `backend/scripts/lint_money_columns.py` — CLI `if __name__` pattern
14. `frontend/src/app/page.tsx` — RSC shell pattern
15. `frontend/src/app/api/healthz/route.test.ts` — Vitest pattern

**Pattern extraction date:** 2026-05-26
