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
import math
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

#: Decimals written for every coefficient and section value, the reference precision.
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


#: What a cell writes when the column does not apply to that row.
#:
#: THE OWNER'S DECISION: a product never writes a BLANK cell. A blank is
#: ambiguous three ways -- it could mean zero, it could mean not-measured, it
#: could mean this-column-is-not-for-this-row -- and a reader cannot tell them
#: apart. Measured on her own superfile: 50 blank cells per row out of 628
#: columns, every one of them a key declared for the union of all run types on a
#: row whose run type does not have it.
#:
#: `NA` says the third of those three and only the third. A value that was
#: EXPECTED and is missing is NOT this: it stays a visible defect rather than
#: being spelled the same as a column that never applied.
NOT_APPLICABLE = "NA"


def _cell(value: object) -> str:
    """One CSV cell: floats at five decimals, a blank as ``NA``, everything else as written.

    IT IS DONE HERE because this is the one funnel every CSV product passes
    through -- the polars, the superfile, the sections, the probes and the
    reductions all render their cells in this function. A rule applied at the
    writers instead would have to be remembered at each of them, and the naming
    table of 0.22.0 is the standing lesson about what that costs: held in a
    second place, it was remembered at one call site of three.
    """
    if value is None:
        return NOT_APPLICABLE
    if isinstance(value, float | np.floating):
        number = float(value)
        return NOT_APPLICABLE if math.isnan(number) else f"{number:.{_DECIMALS}f}"
    text = str(value)
    return text if text.strip() else NOT_APPLICABLE


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
