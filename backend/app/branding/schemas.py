"""Branding Pydantic schemas (Phase 10, Plan 10-01).

Three contracts:
  - ``TenantConfigUpdate`` — the admin PUT body (``extra="forbid"`` firewall +
    server-side hex allowlist via ``Field(pattern=...)``, D-09 / T-10-01). The
    logo is handled out-of-band as a multipart ``UploadFile`` in the router (size
    cap + content-type allowlist), so it is NOT a field here.
  - ``TenantConfigRead`` — the admin GET / PUT response (``from_attributes=True``).
  - ``BrandingPublic`` — the public ``/branding/current`` payload: exactly four
    fields, no bytes, no tenant_id, no timestamps (Pitfall 7 / T-10-06).

This file intentionally OMITS the postponed-annotations future import: Pydantic v2's
``Field(pattern=...)`` + ``ConfigDict`` are forward-ref sensitive — stringized
annotations can break pattern/constraint resolution (the same forward-ref hazard
the routers document). ``app/admin/schemas.py`` omits it too; match that.
"""

from pydantic import BaseModel, ConfigDict, Field

# Server-side hex allowlist (D-09, Pitfall 5 — the <style>-injection guard). A
# 6-digit hex cannot contain '<', '>', '}', or quotes, so no </style> break-out.
_HEX = r"^#[0-9a-fA-F]{6}$"


class TenantConfigUpdate(BaseModel):
    """Admin PUT body — a stray field is a hard 422 (``extra="forbid"``)."""

    model_config = ConfigDict(extra="forbid")

    brand_name: str = Field(min_length=1, max_length=120)
    primary_hex: str = Field(pattern=_HEX)
    secondary_hex: str = Field(pattern=_HEX)


class TenantConfigRead(BaseModel):
    """Admin GET / PUT response — built from the ORM row."""

    model_config = ConfigDict(from_attributes=True)

    brand_name: str
    primary_hex: str
    secondary_hex: str
    logo_url: str | None = None


class BrandingPublic(BaseModel):
    """Public ``/branding/current`` payload — small, no bytes (Pitfall 7)."""

    brand_name: str
    primary_hex: str
    secondary_hex: str
    logo_url: str | None = None


__all__ = ["BrandingPublic", "TenantConfigRead", "TenantConfigUpdate"]
