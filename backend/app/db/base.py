"""SQLAlchemy declarative base — every model inherits from this.

Models register against this metadata; Alembic ``env.py`` imports it for autogenerate.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Project-wide declarative base. Subclassed by every ORM model."""
