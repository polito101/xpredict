"""Public branding surface (Phase 10, Plan 10-01, D-08/D-12).

Two PUBLIC (no auth) endpoints — the player UI is unauthenticated for branding:

  - ``GET /branding/current``  small JSON: {brand_name, primary_hex, secondary_hex,
                               logo_url}. NO bytes inlined (Pitfall 7) — the logo is
                               a URL the browser <img> fetches separately.
  - ``GET /branding/logo``     the stored bytes with the stored Content-Type +
                               ``X-Content-Type-Options: nosniff`` (T-10-02), or 404
                               when no logo is set.

# Note on the postponed-annotations future import (intentionally ABSENT): same
# FastAPI 3.13 ``Annotated[T, Depends(...)]`` forward-ref constraint as every other
# router in this repo (wallet/admin_router.py, markets/router.py).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.branding.repo import load_singleton, logo_url_for
from app.branding.schemas import BrandingPublic
from app.db.session import get_async_session

branding_router = APIRouter(tags=["branding"])


@branding_router.get("/branding/current", response_model=BrandingPublic)
async def get_branding_current(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> BrandingPublic:
    """Public branding payload — name + palette + a logo URL (no bytes)."""
    row = await load_singleton(session)
    if row is None:
        # Fresh, unseeded DB — safe defaults so the player UI never breaks.
        return BrandingPublic(
            brand_name="XPredict",
            primary_hex="#4f46e5",
            secondary_hex="#0ea5e9",
            logo_url=None,
        )
    return BrandingPublic(
        brand_name=row.brand_name,
        primary_hex=row.primary_hex,
        secondary_hex=row.secondary_hex,
        logo_url=logo_url_for(row),
    )


@branding_router.get("/branding/logo")
async def get_branding_logo(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> Response:
    """Serve the stored logo bytes with the stored Content-Type + nosniff (T-10-02)."""
    row = await load_singleton(session)
    if row is None or row.logo_bytes is None:
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    return Response(
        content=row.logo_bytes,
        media_type=row.logo_content_type or "application/octet-stream",
        headers={
            "X-Content-Type-Options": "nosniff",
            # Defense-in-depth (IN-04): prevent a hypothetical future
            # <object>/<embed> mis-use from executing script in an SVG.
            # An SVG served via <img> cannot run script regardless, but if
            # the URL is ever navigated to directly or embedded, the CSP
            # sandbox + inline disposition remove any script execution surface.
            "Content-Disposition": "inline",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


__all__ = ["branding_router"]
