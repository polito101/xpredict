"""Money SQLAlchemy alias — the source of truth for monetary columns (D-18, WAL-05).

All money columns MUST be typed as ``Mapped[Money]``. The ``scripts/lint_money_columns.py``
CI gate AST-walks every ``*models.py`` and fails on any money-named column that does not
use this alias (or an equivalent ``Numeric(18, 4)`` direct column).

Nullable money is the documented exception (Pitfall 4): use
``amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)``
directly — the lint still validates the type.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from sqlalchemy import Numeric
from sqlalchemy.orm import mapped_column

Money = Annotated[Decimal, mapped_column(Numeric(18, 4), nullable=False)]
"""18-digit precision, 4-digit scale Decimal — never Float, never Postgres MONEY."""
