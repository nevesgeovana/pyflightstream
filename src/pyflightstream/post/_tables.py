"""What the products stage and the series tables share: the CSV writer and the product errors.

A private module below :mod:`pyflightstream.post.products` and
:mod:`pyflightstream.post.series`, so both import downward and neither
imports the other (the architecture lens of REL-0140 found the two
importing each other, one direction hidden inside a function).
:mod:`pyflightstream.post.products` re-exports every public name here,
which is where a reader finds them.
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from pyflightstream._errors import PyflightstreamError

SECTION_COLUMNS: tuple[str, ...] = (
    "POINT",
    "ALPHA",
    "BETA",
    "MACH",
    "VINF",
    "RE",
    "ALT",
    "Offset",
    "Chord",
    "X_QC",
    "Z_QC",
    "Fx",
    "Fz",
    "Moment",
)

#: The plot-column prefixes that are coefficients, which the solver
#: normalises by its reference velocity and the product by the free stream.
_COEFFICIENT_PLOT_PREFIXES = ("CL_", "CDI_", "CDO_", "CD_")

#: Decimals written for every coefficient and section value, the author's precision.
_DECIMALS = 5


class ProductError(PyflightstreamError, ValueError):
    """A product cannot be written from what the run left."""


class ProductExistsError(ProductError):
    """A product exists and ``overwrite`` was not given.

    Its own class because the campaign writer treats it differently from
    every other refusal (PFS-2031.16): a refusal about one simulation's
    content is recorded as a skip and the other simulations are written,
    while this one is about the caller's flag and stops the stage.
    """


def _cell(value: object) -> str:
    """One CSV cell: floats at five decimals, everything else as written."""
    if isinstance(value, float | np.floating):
        return f"{float(value):.{_DECIMALS}f}"
    return str(value)


def write_csv_table(
    path: str | Path, columns: Sequence[str], rows: Sequence[Sequence[object]]
) -> Path:
    """Write one CSV table: a header line and one line per row, floats at five decimals."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        for row in rows:
            if len(row) != len(columns):
                raise ProductError(f"a row has {len(row)} values for {len(columns)} columns")
            writer.writerow([_cell(value) for value in row])
    return target
