"""Money-column AST lint (D-17, WAL-05) — pre-commit + CI gate.

Rules:
  R1. ``Numeric(p, s)`` in any ``mapped_column(...)`` must have ``p == 18`` and ``s == 4``.
  R2. Columns named after money concepts MUST use ``Mapped[Money]`` (or an
      equivalent direct ``Numeric(18, 4)``).
  R3. ``Numeric(18, 4)`` on a non-money-named column → warning (typo detector),
      not a failure.

Exit code: 0 on pass; 1 on any R1 or R2 failure (R3 prints but doesn't fail).

Invoke from ``backend/``:
    uv run python scripts/lint_money_columns.py
The script walks ``app/**/models.py`` and ``app/**/*models*.py`` (and any
``alembic/versions/*.py`` — Open Question #4 says yes, extend the lint).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

MONEY_NAMES: set[str] = {
    "amount",
    "balance",
    "price",
    "stake",
    "payout",
    "fee",
    "volume",
    "liquidity",
    "credit",
    "debit",
    "cost",
    "value",
}


class MoneyColumnLinter(ast.NodeVisitor):
    """Walks an AST and collects R1/R2 errors and R3 warnings."""

    def __init__(self, file: Path) -> None:
        self.file = file
        self.errors: list[str] = []
        self.warnings: list[str] = []

    # ----- ORM models: `name: Mapped[T] = mapped_column(...)` ---------------

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if not isinstance(node.target, ast.Name):
            self.generic_visit(node)
            return
        col_name = node.target.id

        if node.value is None or not isinstance(node.value, ast.Call):
            self.generic_visit(node)
            return

        call = node.value
        if not (isinstance(call.func, ast.Name) and call.func.id == "mapped_column"):
            self.generic_visit(node)
            return

        numeric_args = self._find_numeric_args(call)
        is_money_name = col_name.lower() in MONEY_NAMES
        uses_money_alias = self._uses_money_alias(node)
        annotation_kind = self._annotation_kind(node)  # "numeric" | "non-money" | "unknown"
        bad_type_name = self._find_bad_money_type(call)  # Float / Real / etc.

        if numeric_args is not None:
            precision, scale = numeric_args
            if precision != 18 or scale != 4:
                self.errors.append(
                    f"{self.file}:{node.lineno}: '{col_name}' uses "
                    f"Numeric({precision},{scale}); must be Numeric(18,4) [WAL-05]"
                )
            elif not is_money_name:
                self.warnings.append(
                    f"{self.file}:{node.lineno}: '{col_name}' uses Numeric(18,4) but name "
                    f"is not in money-list — typo or unintentional Money type?"
                )
        elif is_money_name and not uses_money_alias and annotation_kind != "non-money":
            # R2 — money-named column with a non-money type. Suppress when the
            # annotation clearly signals a non-numeric column (JSONB dict, bool,
            # str, datetime, etc.) — those are legitimate uses of generic names
            # like `value` that the money lint should not block.
            detail = f" (uses {bad_type_name})" if bad_type_name else " (no Numeric(18,4) found)"
            self.errors.append(
                f"{self.file}:{node.lineno}: '{col_name}' has money-suggesting name but "
                f"is not Money / Numeric(18,4){detail} [WAL-05]"
            )

        self.generic_visit(node)

    # ----- Helpers -----------------------------------------------------------

    @staticmethod
    def _find_numeric_args(call: ast.Call) -> tuple[int, int] | None:
        """Extract (precision, scale) from a Numeric(...) inside mapped_column(...)."""
        for arg in call.args:
            if (
                isinstance(arg, ast.Call)
                and isinstance(arg.func, ast.Name)
                and arg.func.id == "Numeric"
            ):
                precision: int | None = None
                scale: int | None = None

                # Positional args
                if len(arg.args) >= 1 and isinstance(arg.args[0], ast.Constant):
                    val = arg.args[0].value
                    if isinstance(val, int):
                        precision = val
                if len(arg.args) >= 2 and isinstance(arg.args[1], ast.Constant):
                    val = arg.args[1].value
                    if isinstance(val, int):
                        scale = val

                # Keyword args (precision=18, scale=4)
                for kw in arg.keywords:
                    if not isinstance(kw.value, ast.Constant):
                        continue
                    val = kw.value.value
                    if not isinstance(val, int):
                        continue
                    if kw.arg == "precision":
                        precision = val
                    elif kw.arg == "scale":
                        scale = val

                if precision is not None and scale is not None:
                    return precision, scale
        return None

    @staticmethod
    def _uses_money_alias(node: ast.AnnAssign) -> bool:
        """Detect ``Mapped[Money]`` annotations (the canonical money type)."""
        if not isinstance(node.annotation, ast.Subscript):
            return False
        inner = node.annotation.slice
        return isinstance(inner, ast.Name) and inner.id == "Money"

    # Annotations that clearly signal a non-money column (suppresses R2 false-pos).
    _NON_MONEY_ANNOTATION_NAMES: frozenset[str] = frozenset(
        {
            "bool",
            "str",
            "bytes",
            "dict",
            "list",
            "tuple",
            "set",
            "datetime",
            "date",
            "time",
            "timedelta",
            "UUID",
            "PyUUID",
        }
    )
    # Annotations that signal a numeric column (R2 still applies if no Numeric/Money).
    _NUMERIC_ANNOTATION_NAMES: frozenset[str] = frozenset({"Decimal", "int", "float"})

    @classmethod
    def _annotation_kind(cls, node: ast.AnnAssign) -> str:
        """Classify the ``Mapped[T]`` annotation as numeric / non-money / unknown.

        Returns ``"non-money"`` when ``T`` is a clearly non-numeric type
        (``dict``, ``bool``, ``str``, ``datetime``, ...); ``"numeric"`` for
        ``Decimal``/``int``/``float``; ``"unknown"`` otherwise. Handles
        ``Mapped[T]``, ``Mapped[T | None]``, and ``Mapped[Optional[T]]``.
        """
        if not isinstance(node.annotation, ast.Subscript):
            return "unknown"
        inner = node.annotation.slice
        names = cls._collect_name_ids(inner)
        if not names:
            return "unknown"
        # Strip "None" from union types — `Mapped[Decimal | None]` is still numeric.
        names_no_none = {n for n in names if n != "None"}
        if names_no_none & cls._NON_MONEY_ANNOTATION_NAMES:
            # If ANY component is a clearly non-money name, classify the whole
            # column as non-money. (Mixed Mapped[str | None] is non-money.)
            return "non-money"
        if names_no_none & cls._NUMERIC_ANNOTATION_NAMES:
            return "numeric"
        return "unknown"

    @classmethod
    def _collect_name_ids(cls, node: ast.AST) -> set[str]:
        """Collect ``ast.Name`` ids reachable from an annotation expression."""
        out: set[str] = set()
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Constant) and node.value is None:
            out.add("None")
        elif isinstance(node, ast.BinOp):
            out |= cls._collect_name_ids(node.left)
            out |= cls._collect_name_ids(node.right)
        elif isinstance(node, ast.Subscript):
            # e.g. Optional[Decimal], list[int]
            out |= cls._collect_name_ids(node.value)
            out |= cls._collect_name_ids(node.slice)
        elif isinstance(node, ast.Tuple):
            for elt in node.elts:
                out |= cls._collect_name_ids(elt)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
        return out

    @staticmethod
    def _find_bad_money_type(call: ast.Call) -> str | None:
        """Return the name of an obviously-wrong-for-money SQLAlchemy type, if any."""
        forbidden = {"Float", "REAL", "Real", "Integer", "BigInteger", "SmallInteger", "MONEY"}
        for arg in call.args:
            if isinstance(arg, ast.Name) and arg.id in forbidden:
                return arg.id
            if (
                isinstance(arg, ast.Call)
                and isinstance(arg.func, ast.Name)
                and arg.func.id in forbidden
            ):
                return arg.func.id
        return None


def lint(root: Path) -> int:
    """Lint a directory; return 0 on pass, 1 on any R1/R2 error."""
    patterns = ("**/models.py", "**/*models*.py", "**/versions/*.py")
    files: list[Path] = []
    seen: set[Path] = set()
    for pattern in patterns:
        for f in root.rglob(pattern):
            if f in seen or not f.is_file():
                continue
            seen.add(f)
            files.append(f)

    total_errors, total_warnings = 0, 0
    for f in files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            print(f"ERROR: {f}: failed to parse — {exc}", file=sys.stderr)
            total_errors += 1
            continue
        linter = MoneyColumnLinter(f)
        linter.visit(tree)
        for err in linter.errors:
            print(f"ERROR: {err}")
            total_errors += 1
        for warn in linter.warnings:
            print(f"WARN:  {warn}")
            total_warnings += 1

    if total_errors:
        print(f"\nFAIL: {total_errors} money-column violations", file=sys.stderr)
        return 1
    print(f"OK: {len(files)} files checked, {total_warnings} warnings.")
    return 0


if __name__ == "__main__":
    sys.exit(lint(Path("app")))
