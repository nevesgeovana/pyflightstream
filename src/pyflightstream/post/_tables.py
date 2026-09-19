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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# RE-EXPORTED, not used here. `post.products` imports both from this module,
# which is what its own docstring promises a reader, and they are DEFINED in
# `_errors` since 0.23.0 because two layers name them: the products stage
# raises them and `workspace.rename_groups` does too.
from pyflightstream._errors import ProductError as ProductError
from pyflightstream._errors import ProductExistsError as ProductExistsError
from pyflightstream._tokens import ADVANCE_RATIO_COLUMN as ADVANCE_RATIO_COLUMN
from pyflightstream._tokens import CONTEXT_COLUMNS as CONTEXT_COLUMNS
from pyflightstream._tokens import FLIGHT_CONDITION_COLUMNS as FLIGHT_CONDITION_COLUMNS
from pyflightstream._tokens import NOT_APPLICABLE as NOT_APPLICABLE
from pyflightstream._tokens import REFERENCE_LENGTH_COLUMNS as REFERENCE_LENGTH_COLUMNS
from pyflightstream.post.axes import blade_azimuth_deg

#: The spellings a RUN recorded, mapped to the product column they mean.
#:
#: `context_row` folds case and nothing else, so a recorded key reaches a column
#: only when the two are the same word -- and none of the three columns item 5
#: most needs is spelled the way the run recorded it. The cell keys carry their
#: UNIT in the name (`TASmps`, `ALTFT`) and the column does not; the sweep point
#: and the matrix cell spell the advance ratio two ways; and the loads export
#: reports under the labels its own header uses. Without this table the products
#: carry the columns and never the values, which is what a release round
#: measured on real files: `VINF` and `ALT` read `NA` in every row of every
#: polar and super file.
#:
#: ONLY PAIRS WHOSE UNITS AGREE ARE HERE, and that is the whole discipline of
#: the table rather than a note on it. `ALTFT` is feet and so is `ALT`; `TASmps`
#: is m/s and so is `VINF`.
#:
#: `REmi` IS DELIBERATELY ABSENT, and the reason is the opposite of the one this
#: comment first gave. It said `REmi` "would write 4.38 into a column where
#: every other row writes 4380000". THE COLUMN IS MILLIONS: the polar's
#: twenty-four say so at `products.COEFFICIENT_COLUMNS`, and the sections table
#: writes `_reynolds_millions`. A V&V round measured the tree against this
#: sentence and found the sentence wrong -- and, because the sentence was wrong,
#: the rotor table had been wired to write the absolute number, putting 4380000
#: and 4.38 under one column name in two files of one directory.
#:
#: So `REmi` stays out for a plainer reason: an alias may not carry a unit
#: conversion. The cell keys that ARE here differ from their column only in
#: spelling. `point_condition` converts the export's absolute Reynolds where it
#: assembles the condition, which is a place a reader can see it happen.
CONDITION_KEY_ALIASES: dict[str, str] = {
    # The sweep point and the matrix cell, which spell one quantity two ways.
    "advance_ratio": ADVANCE_RATIO_COLUMN,
    "tasmps": "VINF",
    "altft": "ALT",
    # What the loads export REPORTS, which is what the solver says it ran at
    # rather than what the matrix asked for. A product should carry this one:
    # the two differ exactly when something went wrong, which is the case a
    # reader most needs to see.
    "angle_of_attack_deg": "ALPHA",
    "sideslip_deg": "BETA",
    "freestream_velocity_m_s": "VINF",
    "altitude_ft": "ALT",
    "reynolds": "RE",
    # 0.24.0. The export's reference velocity, the record's air, and the cell
    # keys that pin the air directly. Units agree in every pair: m/s, kg/m3, K
    # and Pa s.
    "reference_velocity_m_s": "VREF",
    "density_kg_m3": "RHO",
    "temperature_k": "TEMP",
    "viscosity_pa_s": "MU",
    "rhokgm3": "RHO",
    "tk": "TEMP",
    "mupas": "MU",
}


def context_row(
    condition: Mapping[str, object] | None = None,
    reference: Mapping[str, object] | None = None,
    *,
    columns: Sequence[str] = CONTEXT_COLUMNS,
) -> tuple[object, ...]:
    """Return the values of ``columns``, read from what the run recorded.

    ONE ASSEMBLY FOR EVERY PRODUCT FAMILY, which is the whole point of the
    function existing rather than four list comprehensions. Item 5 of 0.23.0
    exists because three of the four families had drifted into carrying
    different subsets of the condition, and four call sites assembling the same
    tuple is how they drift again.

    A key the run did not record is NOT invented and is not left blank: it
    arrives at the funnel as ``None`` and is written as ``NA``, which says the
    column does not apply to that row. That is the third of the three reasons a
    cell can be empty and the only one `NA` stands for -- so a condition the
    solver was never told is visibly absent rather than quietly zero, and a
    zero angle of attack stays a zero.

    The lookup is CASE-INSENSITIVE on purpose: a record writes ``alpha`` and a
    column is ``ALPHA``, and requiring the two to agree makes every caller
    remember a convention that this function can simply apply.
    """
    folded: dict[str, object] = {}
    for source in (condition or {}, reference or {}):
        for key, value in source.items():
            name = str(key).casefold()
            folded[name] = value
            alias = CONDITION_KEY_ALIASES.get(name)
            if alias is not None:
                # `setdefault` and not assignment: a mapping already carrying
                # the COLUMN's own spelling wins over an alias, so a caller that
                # has done the translation itself is never overwritten by one
                # that happens to carry both spellings.
                folded.setdefault(alias.casefold(), value)
    return tuple(folded.get(name.casefold()) for name in columns)


#: What tells one sections ROW from another, in front of the condition every
#: row of the file shares. v0.23.0 item 13, found by reading a real production
#: file: `POINT` carried the polar's NAME, which the file name already
#: carries, so the column restated the one fact a reader holds before opening
#: the file while the two facts that vary down the table were nowhere. On an
#: unsteady run every row then looked identical apart from its position.
#:
#: `AZIMUTH` is `NA` on a run with no rotor, and never zero: zero is a real
#: azimuth a rotor row can hold.
#: 0.24.0. `STEP` is the ONE name of the solver step across the package's tables
#: (it was `ITERATION` here); on a steady run it is the solver iteration. `FAMILY`,
#: `PLANE` and `ROTOR` say which DISTRIBUTION a row belongs to, which nothing did.
_SECTION_IDENTITY_COLUMNS: tuple[str, ...] = ("STEP", "FAMILY", "PLANE", "ROTOR", "AZIMUTH")

SECTION_COLUMNS: tuple[str, ...] = (
    *_SECTION_IDENTITY_COLUMNS,
    *CONTEXT_COLUMNS,
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
#: ONE PRODUCER IS A KNOWN EXCEPTION TODAY, and it is named because the
#: closing round found the same commit asserting the promise and breaking it.
#: A run recorded before 0.16.0 names no probe-positions file, so that table's
#: position and frame cells are a value the package COULD NOT DERIVE -- reason
#: two, which this comment says is not spelled `NA` -- and they read `NA` all
#: the same, because a blank is the one thing a product may not write. The
#: honest statement is therefore narrower than the sentence above: `NA` means
#: does-not-apply EXCEPT in the probes spine of a pre-0.16.0 run, where it
#: means the record that would have said is not there.
#:
#: THAT EXCEPTION IS CARRIED FOR COMPATIBILITY and remains open: refusing such
#: a table instead would take a product away from a campaign that already
#: happened, which is why it was never refused. The alternative, a third token
#: meaning "not recorded", is a change to the product file format and is not
#: taken here.
#:
#: ONE TOKEN IN THE CSV PRODUCTS, and the scope word is load-bearing. The
#: rule is that where a value does not apply the token is always `NA`, and
#: it is written here with the boundary the rule's REASON gives it: a second
#: spelling costs something exactly where a reader PARSES, which is the
#: products. The probes table's `STEP` said `-` on a steady row until 0.23.0,
#: putting two spellings of one meaning in one row beside a `FRAME` that
#: already read `NA`.
#:
#: `-` WAS A LIVE SENTINEL OUTSIDE THE PRODUCTS UNTIL 2026-09-18, and the
#: paragraph that stood here listed the five surfaces that contradicted this
#: rule and then left the question open, because converging them changes a
#: file format users already read. IT IS DECIDED: every surface converges on
#: `NA`.
#:
#: The five were the printed plan and cost table (`run/__init__`, FR-82), the
#: QA physics, drift and CLI tables, and `cases.matrix.UNSTATED_CELL`. All five
#: now WRITE `NA`, and every READER still accepts `-`, so a matrix or a product
#: written by an earlier release is read exactly as it was.
#:
#: THE TOKEN NO LONGER LIVES HERE. It moved to :mod:`pyflightstream._tokens`,
#: below every layer, for the reason the rule itself demands: `qa` does not
#: import `post` and must not start, so a token defined in `post` could only
#: reach those three tables by inverting a layer. It is re-exported under this
#: name because every existing importer asks for it here, and because this
#: module remains the FUNNEL even though it is no longer the DEFINITION --
#: `_cell` below is still the one place a CSV product turns a value into a cell.
#:
#: (The re-export is the `X as X` form in the import block above, which is what
#: makes it explicit to a type checker rather than incidental.)


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


def renamed_columns(
    columns: Sequence[str],
    names: Mapping[str, str] | None,
    *,
    printed: Sequence[str],
    where: str,
) -> tuple[str, ...]:
    """Return ``columns`` with the pproc's ``[names]`` dictionary applied (0.24.0).

    ``printed`` is what the plots export prints, which is what a dictionary's
    left side may name. THE WHOLE DICTIONARY APPLIES OR NONE OF IT DOES: half a
    dictionary applied is a file nobody can predict.

    Raises
    ------
    ProductError
        If an entry names a column no plot prints, which must never become a
        column of `NA` nor pass in silence; or gives a column a name the table
        already carries.
    """
    if not names:
        return tuple(columns)
    unknown = [name for name in names if name not in printed]
    if unknown:
        raise ProductError(
            f"{where}: the pproc's [names] table names {', '.join(unknown)}, which no plot "
            f"of this point prints (it prints {', '.join(printed) or 'none'}). A plot column "
            "is <parameter>_<group name>; correct the left side of the entry, or remove "
            "it. No column was renamed."
        )
    held = set(columns)
    clash = [f"{old} -> {new}" for old, new in names.items() if new != old and new in held]
    if clash:
        raise ProductError(
            f"{where}: the pproc's [names] table renames {', '.join(clash)}, and the table "
            "already carries a column of that name. Choose another name. No column was "
            "renamed."
        )
    return tuple(names.get(name, name) for name in columns)


#: How a rotor table's file name ends, and how many lines lead its header: the
#: rotor's alias, alone on line one, so a script that has loaded the file still
#: knows which rotor it holds. Every reader of `polars/` needs both.
ROTOR_TABLE_SUFFIX = "_rotor.csv"
ROTOR_TABLE_LEAD_LINES = 1


def section_identity(
    n_rows: int,
    layout: Sequence[Mapping[str, object]] | None,
    rotors: Mapping[str, Mapping[str, object]] | None,
    step: int | None,
    azimuth_deg: float | None,
) -> list[tuple[object, object, object, object]]:
    """Return (FAMILY, PLANE, ROTOR, AZIMUTH) for each row of one sections export.

    A layout whose counts do not add up to the export is NOT applied: a row given
    its neighbour's family is worse than a row given none.
    """
    unknown: list[tuple[object, object, object, object]] = [
        (None, None, None, azimuth_deg)
    ] * n_rows
    if not layout:
        return unknown
    counts: list[int] = []
    for block in layout:
        count = block.get("count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            return unknown
        counts.append(count)
    if sum(counts) != n_rows:
        return unknown
    identity: list[tuple[object, object, object, object]] = []
    for block, count in zip(layout, counts, strict=True):
        families = _names_of(block.get("families"))
        alias, azimuth = _rotor_of_the_block(families, rotors, step)
        cell = ("+".join(families) or None, block.get("plane"), alias, azimuth)
        identity.extend([cell] * count)
    return identity


def _names_of(stated: object) -> list[str]:
    """Return a recorded list of names as strings, and nothing for anything else."""
    if isinstance(stated, str) or not isinstance(stated, Sequence):
        return []
    return [str(name) for name in stated]


def _rotor_of_the_block(
    families: Sequence[str],
    rotors: Mapping[str, Mapping[str, object]] | None,
    step: int | None,
) -> tuple[str | None, float | None]:
    """Return the rotor that owns every family of a block, and blade one's azimuth."""
    for alias, rotor in (rotors or {}).items():
        owned = set(_names_of(rotor.get("families")))
        if not families or not set(families) <= owned:
            continue
        return str(alias), blade_azimuth_deg(
            rotor.get("blade1_azimuth_deg"),
            step=step,
            steps_per_revolution=rotor.get("steps_per_revolution"),
            rpm=rotor.get("rpm"),
        )
    return None, None


#: The twenty-four coefficient columns of a polar row, in the order: the
#: point, the body axes, the stability axes, the wind axes, the two drag
#: parts. ``RE`` is the Reynolds number in millions.
COEFFICIENT_COLUMNS: tuple[str, ...] = (
    "ALPHA",
    "BETA",
    "MACH",
    "RE",
    "CDB",
    "CYB",
    "CLB",
    "CRB25",
    "CMB25",
    "CNB25",
    "CDS",
    "CYS",
    "CLS",
    "CRS25",
    "CMS25",
    "CNS25",
    "CDW",
    "CYW",
    "CLW",
    "CRW25",
    "CMW25",
    "CNW25",
    "CD0",
    "CDI",
)

#: The reference block every product row carries in front of its values,
#: so a row is self-describing: which polar, which group, which reference.
_REFERENCE_COLUMNS: tuple[str, ...] = ("SREF", "CREF", "BREF", "XMOM", "YMOM", "ZMOM")


#: A sections table's columns: the point and its condition, then the
#: sectional loads export's own seven columns, in its units.
@dataclass(frozen=True)
class ReferenceValues:
    """The reference block of a product: SREF, CREF, BREF and the moment point.

    The moment point is in the geometry's own coordinate system, the one the
    solver holds the mesh in and reports loads about (the MRP frame the reference
    scripts created sits at this point); the units ride on the field names.
    """

    sref_m2: float
    cref_m: float
    bref_m: float
    xmom_m: float = 0.0
    ymom_m: float = 0.0
    zmom_m: float = 0.0

    @classmethod
    def from_mapping(cls, values: Mapping[str, float]) -> ReferenceValues:
        """Read the block from a mapping keyed by the column names."""
        try:
            return cls(
                sref_m2=float(values["SREF"]),
                cref_m=float(values["CREF"]),
                bref_m=float(values["BREF"]),
                xmom_m=float(values.get("XMOM", 0.0)),
                ymom_m=float(values.get("YMOM", 0.0)),
                zmom_m=float(values.get("ZMOM", 0.0)),
            )
        except KeyError as missing:
            raise ProductError(
                f"the reference block needs {missing.args[0]}; it carries {sorted(values)}"
            ) from missing

    def as_row(self) -> tuple[float, ...]:
        """Return the six values in :data:`_REFERENCE_COLUMNS` order."""
        return (self.sref_m2, self.cref_m, self.bref_m, self.xmom_m, self.ymom_m, self.zmom_m)

    def as_lengths(self) -> dict[str, float]:
        """Return the three reference LENGTHS, keyed by their column names.

        For the product families that carry no moment: a probe sample and a
        reduction window have no moment coefficient, so three columns of moment
        point would be three columns of nothing. The lengths are what a reader
        of those files needs to check a coefficient against.
        """
        return {"SREF": self.sref_m2, "CREF": self.cref_m, "BREF": self.bref_m}

    def as_moment_point(self) -> dict[str, float]:
        """Return the moment point, keyed by its column names (0.24.0).

        For the families that DO carry a moment without carrying the polar's own
        reference block: the unsteady polar and the reductions average the plots'
        `MX_/MY_/MZ_` columns, and a moment states nothing without the point it
        is taken about.
        """
        return {"XMOM": self.xmom_m, "YMOM": self.ymom_m, "ZMOM": self.zmom_m}


def _mach_code(mach: float) -> int:
    """Return the two-digit Mach code of the reference file names: ``round(mach * 100)``."""
    return round(mach * 100)


def polar_file_name(polar: str | int, mach: float, group: str | int) -> str:
    """``<polar>_M<mach code:02d>_g<group:02d>.csv``: one polar table per group.

    THE RECORDED CONVENTION, and the one the reference tooling wrote
    before this package existed. :func:`write_recorded_polar` regenerates
    the recorded tables under it and is compared with what those files name for
    name, which is why it stays. A polar table of a WORKSPACE is named by
    :func:`swept_polar_file_name`, the standard point convention (FR-85).
    """
    return f"{polar}_M{_mach_code(mach):02d}_g{int(group):02d}.csv"
