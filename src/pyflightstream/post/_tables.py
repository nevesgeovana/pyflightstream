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
#: A product never writes a BLANK cell. A blank is ambiguous three ways -- it
#: could mean zero, it could mean not-measured, it could mean
#: this-column-is-not-for-this-row -- and a reader cannot tell them apart.
#: Measured on a production superfile, 50 of 628 columns per row were blank for
#: the third reason alone: a key declared for the union of all run types, on a
#: row whose run type does not have it.
#:
#: `NA` says the third of those three and only the third. A value that was
#: EXPECTED and is missing is NOT this: it stays a visible defect rather than
#: being spelled the same as a column that never applied.
#:
#: THAT LAST SENTENCE IS AN INTENT THE FUNNEL CANNOT ENFORCE, and saying so
#: here is the difference between a rule and a wish. `_cell` sees a blank and
#: cannot know which of the three reasons produced it, so it spells every
#: blank `NA`. The promise therefore rests on the PRODUCERS: it holds exactly
#: as long as no producer emits a blank for a value it expected and did not
#: get. It is not currently checked anywhere, and `_probe_spine` is the one
#: place that would test it, since it returns a blank on the path where no
#: position was recorded.
#:
#: The QA lens of the 0.23.0 range measured this and it is registered as owed
#: rather than left implied: routing the does-not-apply case through this
#: constant AT THE PRODUCER, and leaving a blank to arrive as a visible
#: defect, is the shape that would make the sentence above testable. It is not
#: done here because it touches every producer at once, and this release
#: already changes the bytes of every product.
#:
#: One token and no second spelling, the owner's rule of 2026-09-17: *"quando
#: nao se aplica, usa sempre NA"*. The probes table's `STEP` said `-` on a
#: steady row until 0.23.0, which put two spellings of one meaning in one row
#: beside a `FRAME` that already read `NA`.
#:
#: THE SCOPE OF THAT RULE, stated here because no artifact stated it and the
#: closing round of FIX-0230 found the gap. It governs the CSV PRODUCTS -- the
#: files a reader parses -- and that is where a second spelling actually costs
#: something. The PRINTED plan and cost table of `pyfs-matrix` still writes
#: `-` for a cell it cannot derive, deliberately: it is read by eyes in a
#: terminal and never parsed, `-` is easier to scan in a column of numbers
#: than a two-letter word, and FR-82 has a test asserting it.
#:
#: WHETHER THE ESTATE SHOULD CONVERGE ON ONE TOKEN EVERYWHERE IS THE OWNER'S,
#: and it is open. What is NOT open is that the boundary be written down: the
#: one sentence in the tree that named both tokens together lived in a test
#: comment and was deleted by this release's own fix, which made the
#: inconsistency harder to find while asserting the rule that exposes it.
NOT_APPLICABLE = "NA"


def _cell(value: object) -> str:
    """One CSV cell: floats at five decimals, a blank as ``NA``, everything else as written.

    IT IS DONE HERE because this is the funnel the CSV PRODUCTS pass through --
    the polars, the superfile, the sections, the probes, the campaign reduction
    table, the POINT SERIES and, since 0.23.0, the settings table. A rule
    applied at the writers
    instead would have to be remembered at each of them, and the naming table of
    0.22.0 is the standing lesson about what that costs: held in a second place,
    it was remembered at one call site of three.

    WHAT DOES NOT PASS THROUGH IT, named rather than left to be discovered:
    `reductions.write_series` and `reductions.write_reduction` render their own
    rows with a bare `csv.writer`, and the probe-positions file in the run stage
    does the same. No `None` reaches any of the three, so none of them writes a
    blank today -- but a NaN would print as `nan` rather than `NA`, and that is
    a gap rather than a decision. The claim here is about the products, not
    about every line of CSV the package emits: an earlier writing of this
    docstring said "every CSV product", and a lens measured the settings table
    doing the exact opposite one module away.

    THIS LIST IS THE AUTHORITY AND EVERY OTHER COPY POINTS AT IT. The closing
    round of FIX-0230 found the change log naming SEVEN products here and this
    docstring naming six, the point series being the one it had dropped --
    `post.series` writes through `write_csv_table` and always did. An
    enumeration that has just been corrected for overclaiming is worth
    re-reading for the opposite, and nobody had.
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
