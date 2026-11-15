"""The run block in a visualization file: Tecplot auxiliary data and VTK field data (FR-3778).

The averaged surface of a point (``surfaces/<stem>_time_average.dat`` and
``.vtk``) names its condition like every table: one ``DATASETAUXDATA
<COLUMN>="<value>"`` record per run block column in a Tecplot file, one
``FIELD FieldData`` array per column in a legacy ASCII VTK file. Private to
the post.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import Path

__all__ = ["add_run_block_to_vtk", "run_block_text", "tecplot_run_block", "vtk_run_block_lines"]

#: The run block columns whose value is text: a numeric column that has no value
#: is ``nan`` in a VTK array, a text one keeps ``NA``.
_TEXT_BLOCK_COLUMNS = frozenset({"POL", "POINT", "RUN_TYPE", "MU"})


def _is_text(name: str, value: object) -> bool:
    return name in _TEXT_BLOCK_COLUMNS or (isinstance(value, str) and value != "NA")


def run_block_text(value: object) -> str:
    """Return one run block value as the text an auxiliary record carries.

    Examples
    --------
    >>> run_block_text(4.0), run_block_text(None), run_block_text("steady")
    ('4.0', 'NA', 'steady')
    """
    if value is None or value == "":
        return "NA"
    if isinstance(value, float) and not math.isfinite(value):
        return "NA"
    return str(value).replace('"', "'").replace("\n", " ")


def tecplot_run_block(block: Mapping[str, object]) -> dict[str, str]:
    """Return the run block as Tecplot ``DATASETAUXDATA`` records, in the block's order.

    Parameters
    ----------
    block : mapping
        The point's run block row.

    Returns
    -------
    dict of str to str
        One record per column, name to text.

    Examples
    --------
    >>> tecplot_run_block({"POL": "7001", "ALPHA": 4.0})
    {'POL': '7001', 'ALPHA': '4.0'}
    """
    return {str(name): run_block_text(value) for name, value in block.items()}


def vtk_run_block_lines(block: Mapping[str, object]) -> list[str]:
    """Return the legacy VTK ``FIELD FieldData`` block of the run block's columns.

    One array per column: ``<COLUMN> 1 1 double`` for a number (``nan`` where it
    has none) and ``<COLUMN> 1 1 string`` for a text column, spaces made
    underscores.

    Examples
    --------
    >>> vtk_run_block_lines({"POL": "7001", "ALPHA": 4.0, "RHO": None})[:6]
    ['FIELD FieldData 3', 'POL 1 1 string', '7001', 'ALPHA 1 1 double', '4', 'RHO 1 1 double']
    """
    lines = [f"FIELD FieldData {len(block)}"]
    for name, value in block.items():
        if _is_text(str(name), value):
            lines += [f"{name} 1 1 string", run_block_text(value).replace(" ", "_")]
        else:
            number = (
                float(value)
                if isinstance(value, int | float) and not isinstance(value, bool)
                else math.nan
            )
            lines += [f"{name} 1 1 double", "nan" if not math.isfinite(number) else f"{number:g}"]
    return lines


def add_run_block_to_vtk(path: str | Path, block: Mapping[str, object]) -> Path:
    """Put the run block in a legacy ASCII VTK file as dataset field data.

    The ``FIELD`` block goes after the geometry and before the first
    ``POINT_DATA`` or ``CELL_DATA`` line, or at the end of a file that has none,
    so it is the dataset's own and no attribute's. Whether ParaView's legacy
    reader of this estate shows ``string`` field arrays is unconfirmed here; the
    numeric arrays are the part a reader can rely on.

    Parameters
    ----------
    path : str or Path
        The VTK file, already written.
    block : mapping
        The point's run block row.

    Returns
    -------
    Path
        ``path``.
    """
    target = Path(path)
    lines = target.read_text(encoding="utf-8").splitlines()
    at = next(
        (i for i, line in enumerate(lines) if line.startswith(("POINT_DATA", "CELL_DATA"))),
        len(lines),
    )
    lines[at:at] = vtk_run_block_lines(block)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target
