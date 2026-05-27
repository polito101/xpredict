"""Pydantic API schemas for auth — D-09, D-10.

D-09 (the critical one): the wire surface exposes ``is_admin: bool``;
``is_superuser`` is excluded from ``model_dump()`` via ``Field(exclude=True)``
(authoritative hider) AND a ``computed_field`` exposes ``is_admin`` from
``is_superuser`` (convenience mapping). Defense-in-depth per PATTERNS line 137.

Player-facing endpoints (``GET /auth/users/me``) MUST never serialize
``is_superuser`` — that would leak admin-escalation footprint. The unit test
``test_user_read_maps_is_superuser_to_is_admin`` asserts this.
"""

from __future__ import annotations

import uuid

from fastapi_users import schemas
from pydantic import Field, computed_field


class UserRead(schemas.BaseUser[uuid.UUID]):
    """API representation — exposes is_admin, hides is_superuser (D-09)."""

    display_name: str | None = None

    # T-02-06 mitigation: ``is_superuser`` is excluded from JSON output so
    # ``model_dump()`` never emits it. The computed_field below exposes the
    # bool under the API-facing name ``is_admin``.
    is_superuser: bool = Field(default=False, exclude=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_admin(self) -> bool:
        """Alias of internal ``is_superuser`` for the API surface (D-09)."""
        return self.is_superuser


class UserCreate(schemas.BaseUserCreate):
    """Register payload (POST /auth/register)."""

    display_name: str | None = None


class UserUpdate(schemas.BaseUserUpdate):
    """PATCH /auth/users/me payload."""

    display_name: str | None = None
