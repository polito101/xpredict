"""SQLAlchemy 2.0 declarative base.

All ORM models (Phase 2+) inherit from ``Base``. Alembic imports this module
so model metadata is discoverable for autogenerate.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
