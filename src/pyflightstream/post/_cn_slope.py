"""The normal-force slope of a rotor table against incidence, per advance ratio (FR-3502).

``[products] rotor_cn_slope`` writes ``P<sim>-<ALIAS>_cn_slope.csv`` beside a rotor
table. It is read from the table the post has just written, so no solver run is
added, and the definition is on ``docs/definitions/rotor-coefficients.md``
("The normal-force slope against incidence"). A private module below
:mod:`pyflightstream.post._sim`, which calls it.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from pyflightstream._errors import NotApplicableWarning, warn
from pyflightstream._tokens import CONTEXT_COLUMNS, POLAR_ID_COLUMN, ROTOR_ID_COLUMN
from pyflightstream.post._tables import read_csv_table, write_csv_table

if TYPE_CHECKING:
    from pyflightstream.post._sim import SimContext

__all__ = ["CN_SLOPE_SUFFIX", "cn_slope_rows", "rotor_cn_slope_product", "write_cn_slope"]

#: The file suffix of the slope table, replacing the rotor table's ``_rotor.csv``.
CN_SLOPE_SUFFIX = "_cn_slope.csv"

#: The columns after the context block, in the order they are written.
_SLOPE_COLUMNS = ("J", "ALPHA_LOW", "ALPHA_HIGH", "CN_LOW", "CN_HIGH", "CN_SLOPE_PER_DEG")

_NA = "NA"


def _number(text: str | None) -> float | None:
    """Return the finite number ``text`` states, or None for ``NA`` and anything else."""
    try:
        value = float(text) if text is not None else math.nan
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _the_value_or_na(rows: Sequence[dict[str, str]], column: str) -> str:
    """Return ``column``'s text when every row states the same one, ``NA`` otherwise."""
    values = {row.get(column, _NA) for row in rows}
    return values.pop() if len(values) == 1 else _NA


def _secant(rows: Sequence[dict[str, str]], alias: str) -> tuple[float, ...] | None:
    """Return (alpha_low, alpha_high, cn_low, cn_high, slope) of the two lowest ``|ALPHA|``."""
    usable: dict[float, tuple[float, float]] = {}
    candidates = ((_number(row.get("ALPHA")), _number(row.get(f"CN_{alias}"))) for row in rows)
    # Positive incidence first, so two rows of equal |ALPHA| keep the positive one.
    for alpha, cn in sorted(
        ((a, c) for a, c in candidates if a is not None and c is not None),
        key=lambda pair: (abs(pair[0]), -pair[0]),
    ):
        usable.setdefault(abs(alpha), (alpha, cn))
    if len(usable) < 2:
        return None
    (alpha_low, cn_low), (alpha_high, cn_high) = (usable[key] for key in sorted(usable)[:2])
    return alpha_low, alpha_high, cn_low, cn_high, (cn_high - cn_low) / (alpha_high - alpha_low)


def cn_slope_rows(
    columns: Sequence[str], rows: Sequence[dict[str, str]], alias: str
) -> tuple[list[str], list[list[object]], list[str]]:
    """Return the columns, the rows and the skip lines of the slope table of a rotor table.

    One row per distinct ``J_<alias>`` (the six figures the table writes), ascending.
    A ``J`` with fewer than two usable incidences reads ``NA`` and is named in the
    skip lines; nothing is refused.
    """
    context = [name for name in CONTEXT_COLUMNS if name not in ("ALPHA", "J") and name in columns]
    header = [POLAR_ID_COLUMN, *context, ROTOR_ID_COLUMN, *_SLOPE_COLUMNS]
    groups: dict[float, list[dict[str, str]]] = {}
    skipped: list[str] = []
    for row in rows:
        j = _number(row.get(f"J_{alias}"))
        if j is None:
            skipped.append(f"a row of the {alias} table states no J, so it has no slope")
            continue
        groups.setdefault(round(j, 6), []).append(row)
    out: list[list[object]] = []
    for j in sorted(groups):
        group = groups[j]
        secant = _secant(group, alias)
        if secant is None:
            skipped.append(
                f"J={j:g}: fewer than two incidences with a CN, so CN_SLOPE_PER_DEG is NA"
            )
            numbers: list[object] = [_NA] * 5
        else:
            numbers = list(secant)
        out.append(
            [
                _the_value_or_na(group, POLAR_ID_COLUMN),
                *(_the_value_or_na(group, name) for name in context),
                _the_value_or_na(group, ROTOR_ID_COLUMN),
                j,
                *numbers,
            ]
        )
    return header, out, skipped


def write_cn_slope(rotor_table: Path, target: Path, alias: str) -> tuple[Path, list[str]]:
    """Write the slope table of ``rotor_table`` to ``target``; return it and its skip lines."""
    columns, rows = read_csv_table(rotor_table)
    header, body, skipped = cn_slope_rows(columns, rows, alias)
    return write_csv_table(target, header, body), skipped


def rotor_cn_slope_product(
    ctx: SimContext, rotor_table: Path, alias: str, entry: dict[str, object]
) -> None:
    """Write the slope table beside ``rotor_table`` and record it in the manifest.

    ``entry`` is the rotor table's manifest entry; the slope table states the same
    runs and rotor with ``kind: cn_slope``. A ``J`` that cannot give a slope is named
    under ``skipped`` for the file and warned once, and the table is still written.
    """
    name = rotor_table.name.removesuffix("_rotor.csv") + CN_SLOPE_SUFFIX
    target = ctx.target(rotor_table.with_name(name))
    _, skipped = write_cn_slope(rotor_table, target, alias)
    ctx.add(target, {**entry, "kind": "cn_slope"})
    if skipped:
        relative = target.relative_to(ctx.out).as_posix()
        ctx.skipped[relative] = "; ".join(skipped)
        warn(f"{relative}: {ctx.skipped[relative]}", NotApplicableWarning, stacklevel=2)
