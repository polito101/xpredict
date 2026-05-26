"""Money-column AST lint tests — D-17 / WAL-05 coverage.

Writes fixture model files to ``tmp_path`` and asserts ``lint()`` returns 0 or
1 per the four canonical cases.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.lint_money_columns import lint

# ---------------------------------------------------------------------------
# Fixture model snippets
# ---------------------------------------------------------------------------

PASS_FIXTURE = """\
from decimal import Decimal
from typing import Annotated
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Numeric

Money = Annotated[Decimal, mapped_column(Numeric(18, 4), nullable=False)]


class Account:
    __tablename__ = "accounts"
    balance: Mapped[Money] = mapped_column()
    fee:     Mapped[Money] = mapped_column()
"""


FLOAT_FIXTURE = """\
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Float


class Account:
    __tablename__ = "accounts"
    balance: Mapped[float] = mapped_column(Float)
"""


WRONG_NUMERIC_FIXTURE = """\
from decimal import Decimal
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Numeric


class Account:
    __tablename__ = "accounts"
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2))
"""


UNKNOWN_WARN_FIXTURE = """\
from decimal import Decimal
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Numeric


class Sensor:
    __tablename__ = "sensors"
    radius: Mapped[Decimal] = mapped_column(Numeric(18, 4))
"""


KEYWORD_NUMERIC_FIXTURE = """\
from decimal import Decimal
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Numeric


class Account:
    __tablename__ = "accounts"
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=4))
"""


NULLABLE_MONEY_FIXTURE = """\
from decimal import Decimal
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Numeric


class Refund:
    __tablename__ = "refunds"
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
"""


JSONB_VALUE_FIXTURE = """\
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB


class FeatureFlag:
    __tablename__ = "feature_flags"
    value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _write(tmp_path: Path, name: str, source: str) -> Path:
    """Write a fixture file under tmp_path/app/<name> for the lint walker to find."""
    target_dir = tmp_path / "app"
    target_dir.mkdir(exist_ok=True)
    target = target_dir / name
    target.write_text(source, encoding="utf-8")
    return target


def test_pass_case(tmp_path: Path) -> None:
    """Mapped[Money] usage on money-named columns returns 0 (no errors)."""
    _write(tmp_path, "models.py", PASS_FIXTURE)
    assert lint(tmp_path) == 0


def test_float_for_money_name_fails(tmp_path: Path) -> None:
    """`balance: Mapped[float] = mapped_column(Float)` triggers R2 → exit 1."""
    _write(tmp_path, "models.py", FLOAT_FIXTURE)
    assert lint(tmp_path) == 1


def test_wrong_numeric_args_fails(tmp_path: Path) -> None:
    """`Numeric(10, 2)` on a money column triggers R1 → exit 1."""
    _write(tmp_path, "models.py", WRONG_NUMERIC_FIXTURE)
    assert lint(tmp_path) == 1


def test_unknown_column_warns(tmp_path: Path) -> None:
    """`Numeric(18,4)` on a non-money name only warns — exit 0."""
    _write(tmp_path, "models.py", UNKNOWN_WARN_FIXTURE)
    assert lint(tmp_path) == 0


def test_keyword_numeric_args_recognized(tmp_path: Path) -> None:
    """`Numeric(precision=18, scale=4)` is equivalent to positional — exit 0."""
    _write(tmp_path, "models.py", KEYWORD_NUMERIC_FIXTURE)
    assert lint(tmp_path) == 0


def test_nullable_money_direct_passes(tmp_path: Path) -> None:
    """`Mapped[Decimal | None] = mapped_column(Numeric(18,4), nullable=True)` — Pitfall 4 case."""
    _write(tmp_path, "models.py", NULLABLE_MONEY_FIXTURE)
    assert lint(tmp_path) == 0


def test_jsonb_value_passes(tmp_path: Path) -> None:
    """JSONB `value` column (feature_flags) is non-money — must NOT trigger R2."""
    _write(tmp_path, "models.py", JSONB_VALUE_FIXTURE)
    assert lint(tmp_path) == 0


def test_lint_returns_zero_on_empty_tree(tmp_path: Path) -> None:
    """Walking a directory with no models.py files exits 0."""
    (tmp_path / "app").mkdir(exist_ok=True)
    assert lint(tmp_path) == 0


@pytest.mark.parametrize(
    "name",
    ["amount", "balance", "price", "stake", "payout", "fee", "credit", "debit", "cost"],
)
def test_money_names_all_fail_with_float(tmp_path: Path, name: str) -> None:
    """Every money-suggesting column name (except `value`/`volume`/`liquidity`) fails with Float."""
    source = (
        "from sqlalchemy.orm import Mapped, mapped_column\n"
        "from sqlalchemy import Float\n\n"
        "class M:\n"
        '    __tablename__ = "m"\n'
        f"    {name}: Mapped[float] = mapped_column(Float)\n"
    )
    _write(tmp_path, "models.py", source)
    assert lint(tmp_path) == 1
