"""Admin tenant-config branding surface (Phase 10, Plan 10-01, D-07/D-09/D-12).

Two admin-Bearer-gated endpoints under ``/api/v1/admin/tenant-config``:

  - ``GET ""``  load the single branding row -> ``TenantConfigRead``.
  - ``PUT ""``  multipart/form-data: brand_name + primary/secondary hex
                (validated via ``TenantConfigUpdate`` so ``extra="forbid"`` + the
                hex ``Field(pattern=...)`` raise -> 422) + an OPTIONAL ``logo``
                ``UploadFile``. The logo is validated out-of-band: a hard 256 KB
                size cap (T-10-03), a content-type allowlist + leading magic-byte
                sniff for PNG/JPEG/WebP (SVG accepted under the cap only, T-10-04).
                The single row is UPDATED in place (seeded if absent — never a
                duplicate insert). The mutation is audited
                (``admin.branding_updated``) then committed.

Every endpoint takes ``admin: Annotated[User, Depends(current_active_admin)]``
(T-10-05 / SC#6) — a player cookie or no auth is 401/403.

# Note on the postponed-annotations future import (intentionally ABSENT): FastAPI's
# ``inspect.signature`` dependency resolver on Python 3.13 mis-resolves
# ``Annotated[T, Depends(...)]`` / ``Form()`` / ``UploadFile`` when annotations are
# forward-ref strings (params get read as query params -> 422). Same constraint as
# ``app/wallet/admin_router.py`` and ``app/markets/router.py``.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_active_admin
from app.auth.models import User
from app.branding.models import TenantConfig
from app.branding.schemas import TenantConfigRead, TenantConfigUpdate
from app.core.audit.service import AuditService
from app.core.config import get_settings
from app.db.session import get_async_session

tenant_config_admin_router = APIRouter(
    prefix="/api/v1/admin/tenant-config",
    tags=["admin-branding"],
)

# Logo upload guards (D-08 / T-10-03 / T-10-04).
_MAX_LOGO_BYTES = 262144  # 256 KB
_LOGO_ALLOWLIST = {"image/png", "image/jpeg", "image/webp", "image/svg+xml"}
# Leading magic bytes per declared type. SVG is untrusted text/xml — no magic-byte
# check (accepted under the size cap + allowlist only; served via <img>, nosniff).
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"


def _logo_url_for(row: TenantConfig) -> str | None:
    """``/branding/logo`` when a logo is set, else ``None``."""
    return "/branding/logo" if row.logo_bytes is not None else None


async def _load_singleton(session: AsyncSession) -> TenantConfig | None:
    """Load the single tenant_config row (or None on a fresh, unseeded DB)."""
    return (await session.execute(select(TenantConfig).limit(1))).scalar_one_or_none()


def _validate_logo(content_type: str | None, data: bytes) -> str:
    """Validate an uploaded logo; return the resolved content-type or raise 422."""
    declared = (content_type or "").split(";", 1)[0].strip().lower()
    if declared not in _LOGO_ALLOWLIST:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Logo must be a PNG, JPEG, WebP, or SVG file.",
        )
    if len(data) > _MAX_LOGO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Logo must be 256 KB or smaller.",
        )
    # Leading magic-byte verification for the binary formats (content-type lies,
    # T-10-04). SVG is text/xml — no magic check; the size cap + allowlist guard it.
    if declared == "image/png" and not data.startswith(_PNG_MAGIC):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Logo content does not match a PNG file.",
        )
    if declared == "image/jpeg" and not data.startswith(_JPEG_MAGIC):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Logo content does not match a JPEG file.",
        )
    if declared == "image/webp" and not (
        data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Logo content does not match a WebP file.",
        )
    return declared


@tenant_config_admin_router.get("", response_model=TenantConfigRead)
async def get_tenant_config(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin: Annotated[User, Depends(current_active_admin)],
) -> TenantConfigRead:
    """Return the current branding row (admin-only)."""
    row = await _load_singleton(session)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Branding configuration not found.",
        )
    return TenantConfigRead(
        brand_name=row.brand_name,
        primary_hex=row.primary_hex,
        secondary_hex=row.secondary_hex,
        logo_url=_logo_url_for(row),
    )


@tenant_config_admin_router.put("", response_model=TenantConfigRead)
async def update_tenant_config(
    session: Annotated[AsyncSession, Depends(get_async_session)],
    admin: Annotated[User, Depends(current_active_admin)],
    brand_name: Annotated[str, Form()],
    primary_hex: Annotated[str, Form()],
    secondary_hex: Annotated[str, Form()],
    logo: Annotated[UploadFile | None, File()] = None,
) -> TenantConfigRead:
    """Persist branding to the single row (admin-only); audited.

    The hex + brand_name fields are validated by constructing ``TenantConfigUpdate``
    (so ``extra="forbid"`` + the hex pattern raise a 422). The optional logo is
    validated out-of-band (size cap + content-type allowlist + magic bytes). The
    single row is updated in place (seeded if absent); the mutation is audited as
    ``admin.branding_updated`` and committed.
    """
    # Capture the admin id as a plain value NOW — the commit below expires the ORM
    # instance loaded by the dependency; a later ``admin.id`` would lazy-reload
    # outside the async greenlet (MissingGreenlet, wallet/admin_router.py:70-76).
    admin_id = admin.id

    # Schema-level validation: extra=forbid + ^#[0-9a-fA-F]{6}$ -> 422 (T-10-01).
    try:
        body = TenantConfigUpdate(
            brand_name=brand_name,
            primary_hex=primary_hex,
            secondary_hex=secondary_hex,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc

    # Optional logo — validate size + content-type + magic bytes BEFORE persisting.
    logo_bytes: bytes | None = None
    logo_content_type: str | None = None
    if logo is not None:
        data = await logo.read()
        if data:  # an empty file part means "no logo provided" — ignore it
            logo_content_type = _validate_logo(logo.content_type, data)
            logo_bytes = data

    # Update the single row in place (seed if absent — never a duplicate insert).
    row = await _load_singleton(session)
    if row is None:
        row = TenantConfig(
            brand_name=body.brand_name,
            primary_hex=body.primary_hex,
            secondary_hex=body.secondary_hex,
            tenant_id=get_settings().TENANT_ID_DEFAULT,
        )
        session.add(row)
    else:
        row.brand_name = body.brand_name
        row.primary_hex = body.primary_hex
        row.secondary_hex = body.secondary_hex

    logo_changed = False
    if logo_bytes is not None:
        row.logo_bytes = logo_bytes
        row.logo_content_type = logo_content_type
        logo_changed = True

    await session.flush()
    has_logo = row.logo_bytes is not None

    await AuditService.record(
        session,
        actor=f"user:{admin_id}",
        event_type="admin.branding_updated",
        payload={
            "brand_name": body.brand_name,
            "primary_hex": body.primary_hex,
            "secondary_hex": body.secondary_hex,
            "logo_changed": logo_changed,
        },
    )
    await session.commit()

    return TenantConfigRead(
        brand_name=body.brand_name,
        primary_hex=body.primary_hex,
        secondary_hex=body.secondary_hex,
        logo_url="/branding/logo" if has_logo else None,
    )


__all__ = ["tenant_config_admin_router"]
