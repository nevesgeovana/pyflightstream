"""The ``[equations]`` of a pproc, evaluated into the rows of a product.

An equation is arithmetic over the columns a row ALREADY holds. It is about one
alias, so the column it adds is ``<NAME>_<alias>``; it may name another
equation, and the order is the pproc's own
(:meth:`pyflightstream.cases.PprocSpec.equation_order`). The expression is
parsed and walked by :mod:`pyflightstream._expressions` and never executed.

HOW A SYMBOL FINDS ITS COLUMN, which is :func:`resolve_symbol` and nothing
else. A plotted column is named ``<parameter>_<group>``, and the group of a
rotor is named by the pproc, usually for the alias and the frame. So a symbol
``S`` of an equation about alias ``A`` in frame ``F`` is, first match wins:

1. another equation named ``S``: its value on that row;
2. ``S_A_F``, then ``S_F_A``, where the equation states a frame;
3. ``S_A``;
4. the column ``S``, exactly as the file spells it (``RHO``, ``FX_MRP_TOTAL``).

THE ALIAS COMES BEFORE THE EXACT NAME because the equation is ABOUT the alias:
the setup of a row carries the native export's own ``CL`` and ``Cx``, one instant
of the last step, and ``CL`` of an equation about ``WING`` means ``CL_WING``.

A symbol none of them answers REFUSES THE BLOCK, naming the equation, the symbol,
the spellings tried and the columns there are. It is never a column of `NA`:
a name that matched nothing is a mistake in the artifact, and a column of `NA`
is how such a mistake is published.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from pyflightstream._errors import ProductError
from pyflightstream._expressions import evaluate_expression, expression_symbols

__all__ = ["apply_equations", "derived_column", "resolve_symbol"]


def derived_column(name: str, alias: str) -> str:
    """Return the column an equation adds: its own name, then the alias it is about.

    Examples
    --------
    >>> derived_column("CTX", "PUSHER")
    'CTX_PUSHER'
    """
    return f"{name}_{alias}"


def _spellings(symbol: str, alias: str, frame: str | None) -> list[str]:
    tried = [f"{symbol}_{alias}_{frame}", f"{symbol}_{frame}_{alias}"] if frame else []
    return [*tried, f"{symbol}_{alias}", symbol]


def resolve_symbol(
    symbol: str, *, alias: str, frame: str | None, columns: Sequence[str]
) -> str | None:
    """Return the column ``symbol`` reads, or None where no spelling of it is a column.

    The order is the module's: ``<symbol>_<alias>_<frame>`` and
    ``<symbol>_<frame>_<alias>`` where a frame is stated, then
    ``<symbol>_<alias>``, then the exact name.

    Examples
    --------
    >>> held = ["RHO", "FX", "FX_PUSHER", "FX_PUSHER_SMRP"]
    >>> resolve_symbol("FX", alias="PUSHER", frame="SMRP", columns=held)
    'FX_PUSHER_SMRP'
    >>> resolve_symbol("FX", alias="PUSHER", frame=None, columns=held)
    'FX_PUSHER'
    >>> resolve_symbol("RHO", alias="PUSHER", frame=None, columns=held)
    'RHO'
    >>> resolve_symbol("CT", alias="PUSHER", frame=None, columns=held) is None
    True
    """
    held = set(columns)
    for spelling in _spellings(symbol, alias, frame):
        if spelling in held:
            return spelling
    return None


def _number(value: object) -> float | None:
    """Return a cell as a finite number, or None for anything else (`NA`, text, blank)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class _Known:
    """The numbers one row holds for one expression; a symbol with none is a LookupError."""

    def __init__(self, numbers: Mapping[str, float | None]) -> None:
        self._numbers = numbers

    def __call__(self, symbol: str) -> float:
        number = self._numbers.get(symbol)
        if number is None:
            raise LookupError(symbol)
        return number


def apply_equations(
    rows: Sequence[Mapping[str, object]],
    equations: Mapping[str, object],
    order: Sequence[str],
    *,
    columns: Sequence[str],
    where: str,
    notes: list[str] | None = None,
) -> tuple[list[str], list[dict[str, float | None]]]:
    """Evaluate every equation on every row; return the columns added and their values.

    ``equations`` maps a name to an object stating ``expression``,
    ``meshes_alias`` and ``frame`` (:class:`pyflightstream.cases.EquationSpec`);
    ``order`` is the order to evaluate them in. ``columns`` is the header of the
    table, which is what a symbol is resolved against, ONCE, so a symbol reads the
    same column on every row. ``where`` names the file, for the refusal.

    A row that holds no number under a column an equation reads (`NA` on a point
    the quantity does not apply to) gets no number from that equation either, and
    neither does a row where the arithmetic has no answer, a division by zero or
    the root of a negative; ``notes`` receives one sentence per such equation.

    Raises
    ------
    ProductError
        If a symbol is no equation and no column, or a derived column would take
        the name of one the table already has. Nothing is evaluated then: the
        block is whole or absent.

    Examples
    --------
    >>> from types import SimpleNamespace as Equation
    >>> table = [{"RHO": 1.2, "FX_PUSHER": -30.0}]
    >>> added, values = apply_equations(
    ...     table,
    ...     {"T": Equation(expression="-FX", meshes_alias="PUSHER", frame=None),
    ...      "T2": Equation(expression="T * 2 / RHO", meshes_alias="PUSHER", frame=None)},
    ...     ["T", "T2"], columns=["RHO", "FX_PUSHER"], where="polars/P1_x_uns_avg.csv",
    ... )
    >>> added, values
    (['T_PUSHER', 'T2_PUSHER'], [{'T_PUSHER': 30.0, 'T2_PUSHER': 50.0}])
    """
    held = list(columns)
    reads: dict[str, dict[str, str]] = {}
    added: list[str] = []
    for name in order:
        spec = equations[name]
        alias = str(getattr(spec, "meshes_alias", ""))
        frame = getattr(spec, "frame", None)
        target = derived_column(name, alias)
        if target in held or target in added:
            raise ProductError(
                f"[equations.{name}] would write the column {target}, which {where} already "
                f"holds. A derived column is <NAME>_<alias>; rename the equation in the pproc "
                "artifact."
            )
        reads[name] = {}
        for symbol in expression_symbols(str(getattr(spec, "expression", ""))):
            if symbol in equations:
                continue
            column = resolve_symbol(
                symbol, alias=alias, frame=None if frame is None else str(frame), columns=held
            )
            if column is None:
                tried = ", ".join(_spellings(symbol, alias, None if frame is None else str(frame)))
                raise ProductError(
                    f"[equations.{name}]: the symbol {symbol!r} is no equation of the pproc and "
                    f"no column of {where} (looked for: {tried}). No derived column is "
                    f"written. The columns there are: {', '.join(held)}. Write the symbol as "
                    "one of them, or as the <parameter> of a plot named <parameter>_<alias>; a "
                    "plot the run did not make takes a [[plots.groups]] entry and a new run."
                )
            reads[name][symbol] = column
        added.append(target)

    values: list[dict[str, float | None]] = []
    unanswered: dict[str, list[str]] = {}
    for index, row in enumerate(rows):
        derived: dict[str, float | None] = {}
        for name in order:
            spec = equations[name]
            target = derived_column(name, str(getattr(spec, "meshes_alias", "")))
            expression = str(getattr(spec, "expression", ""))
            known: dict[str, float | None] = {}
            for symbol in expression_symbols(expression):
                if symbol in equations:
                    other = str(getattr(equations[symbol], "meshes_alias", ""))
                    known[symbol] = derived.get(derived_column(symbol, other))
                else:
                    known[symbol] = _number(row.get(reads[name][symbol]))
            try:
                result = evaluate_expression(expression, _Known(known))
                derived[target] = result if math.isfinite(result) else None
                if derived[target] is None:
                    unanswered.setdefault(name, []).append(f"row {index + 1}: not finite")
            except LookupError as missing:
                derived[target] = None
                unanswered.setdefault(name, []).append(
                    f"row {index + 1}: {missing.args[0]} holds no number"
                )
            except (ArithmeticError, ValueError, TypeError) as error:
                derived[target] = None
                unanswered.setdefault(name, []).append(f"row {index + 1}: {error}")
        values.append(derived)
    if notes is not None:
        for name, reasons in unanswered.items():
            notes.append(
                f"[equations.{name}] has no value on {len(reasons)} row(s) of {where} "
                f"({'; '.join(reasons)}); those cells read NA and every other row is evaluated"
            )
    return added, values
