"""What the products stage and the series tables share: the CSV writer and reader, the errors.

A private module below :mod:`pyflightstream.post.products` and
:mod:`pyflightstream.post.series`, so both import downward and neither
imports the other (the architecture lens of REL-0140 found the two
importing each other, one direction hidden inside a function).
:mod:`pyflightstream.post.products` re-exports every public name here,
which is where a reader finds them.

Since 0.33.0 (AD-10) the post's one CSV reader, :func:`read_csv_table`, and
the plots-table readers (:func:`plots_table_series` and the step clock it
reads) are defined here too, so :mod:`pyflightstream.post.corrections`, which
:mod:`pyflightstream.post.products` imports, reads a table without importing
that module back.
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

# DEPENDENCIES, NOT RE-EXPORTS (G16): the sections table's first column, and the
# rule every cell is written by. The products take them from the floor themselves.
from pyflightstream._tokens import POLAR_ID_COLUMN, plain_cell
from pyflightstream._tokens import REFERENCE_LENGTH_COLUMNS as REFERENCE_LENGTH_COLUMNS
from pyflightstream.post.axes import blade_azimuth_deg, placed_blade_azimuth_deg
from pyflightstream.post.unsteady import TimestepSeries

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

    Parameters
    ----------
    condition : mapping of str to object, optional
        The point's recorded condition.
    reference : mapping of str to object, optional
        The point's recorded reference dimensions.
    columns : sequence of str, optional
        The columns to read, :data:`CONTEXT_COLUMNS` by default.

    Returns
    -------
    tuple of object
        One value per column, looked up without regard to case in the condition and the reference;
        None where the run recorded none.
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


def rotor_advance_ratio(speed_m_s: object, rpm: object, diameter_m: object) -> float | None:
    """Return ``J = V / (n D)`` of a rotor at its own speed and diameter, or None.

    THE ONE HOME of the ratio a rotor RAN at (P0320-QS-J): ``J_CLOCK`` of every
    table and the ``J`` of a quasi-steady point's tables read it here. ``n`` is
    in rev/s and its MAGNITUDE, because the hand of the rotation is the rotor's
    and ``RPM_CLOCK`` carries it. None, and not a guess, where the speed, the
    free stream or the diameter is missing, not a number or not positive.

    Parameters
    ----------
    speed_m_s : object
        The free-stream speed in m/s.
    rpm : object
        The rotor's speed in rev/min; its sign is left out.
    diameter_m : object
        The rotor's diameter in metres.

    Returns
    -------
    float or None
        ``J``, or None where an input is missing, not a number or not positive.
    """
    values = []
    for value in (speed_m_s, rpm, diameter_m):
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None
        values.append(float(value))
    speed, rate, diameter = values
    if not all(math.isfinite(value) for value in values):
        return None
    if abs(rate) <= 0.0 or diameter <= 0.0:
        return None
    return speed / (abs(rate) / 60.0 * diameter)


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

#: 0.27.0 (G16): the polar first, as in every table the post writes.
SECTION_COLUMNS: tuple[str, ...] = (
    POLAR_ID_COLUMN,
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

    NO CELL HOLDS A COMMA OR A DOUBLE QUOTE (G16, 0.27.0), which is the second
    rule held here for the same reason as the first: a text cell goes through
    :func:`pyflightstream._tokens.plain_cell`, so a comma is written ``;``, a
    double quote a single one and a line break a space, and the CSV writer has
    nothing to quote. A reader that splits each line on ``,`` then reads every
    row to the header's count. The matrix cells the super content echoes were
    the cells that broke it: ``SWEEP_VALUES`` and ``FLIGHT_CONDITION`` were
    written quoted, commas inside.
    """
    if value is None:
        return NOT_APPLICABLE
    if isinstance(value, float | np.floating):
        number = float(value)
        return NOT_APPLICABLE if math.isnan(number) else f"{number:.{_DECIMALS}f}"
    text = str(value)
    return plain_cell(text) if text.strip() else NOT_APPLICABLE


def write_csv_table(
    path: str | Path, columns: Sequence[str], rows: Sequence[Sequence[object]]
) -> Path:
    """Write one CSV table: a header line and one line per row, floats at five decimals.

    The header names pass the cells' rule too (G16): no name holds a comma or a
    double quote, so nothing on any line is quoted.

    Parameters
    ----------
    path : str or Path
        The table to write.
    columns : sequence of str
        The header names.
    rows : sequence of sequence of object
        The rows, one value per column; None is written as ``NA``.

    Returns
    -------
    Path
        The written table.

    Raises
    ------
    ProductError
        If a row's width differs from the header's.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow([plain_cell(str(name)) for name in columns])
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

    Parameters
    ----------
    columns : sequence of str
        The table's columns.
    names : mapping of str to str, or None
        The pproc's ``[names]`` dictionary, printed name to new name; None or empty leaves the
        columns as they are.
    printed : sequence of str
        The columns the plots export prints.
    where : str
        What the refusal names as the place of the dictionary.

    Returns
    -------
    tuple of str
        The columns, each renamed where the dictionary names it.

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


#: How a rotor table's file name ends, and how many lines lead its header.
#:
#: NONE SINCE 0.27.0 (G16). From 0.23.0 the rotor's alias stood alone on line
#: one, so a script that had loaded the file still knew which rotor it held;
#: but a line before the header is a file no CSV reader takes as written. The
#: alias is the `ROTOR` column now, right after `POL`, on every row, which keeps
#: the promise inside the bytes and makes the first line the header. The name
#: stays, at zero, for a reader that skips this many lines; a table written by
#: 0.23.0 to 0.26.x still leads with its alias, and a reader of those files
#: drops a first line of one cell (as `post.superfile` does).
ROTOR_TABLE_SUFFIX = "_rotor.csv"
ROTOR_TABLE_LEAD_LINES = 0


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

    Parameters
    ----------
    n_rows : int
        The export's number of rows.
    layout : sequence of mapping, or None
        The recorded sections layout, one block per distribution with its ``count``, ``families``
        and ``plane``.
    rotors : mapping of str to mapping, or None
        Rotor alias to its recorded metadata, which says which rotor owns a block and where its
        blade is.
    step : int or None
        The export's time step, for the azimuth at it.
    azimuth_deg : float or None
        The azimuth every row carries where the layout is not applied, in degrees.

    Returns
    -------
    list of tuple
        One ``(FAMILY, PLANE, ROTOR, AZIMUTH)`` per row; None for the first three of every row
        where the layout is missing or its counts do not add up.
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
    """Return the rotor that owns every family of a block, and the azimuth it states.

    A block that cuts the families of ONE blade of the rotor (the rotor's
    ``blade_families``, blade n from 1, each the geometry families that blade
    may state) states THAT blade's azimuth: blade one's, placed by
    :func:`~pyflightstream.post.axes.placed_blade_azimuth_deg`, the one home of
    where blade n sits. Any other block of the rotor (several blades, the
    general families, or a rotor that states no blade grouping) states blade
    one's azimuth, as before.
    """
    for alias, rotor in (rotors or {}).items():
        owned = set(_names_of(rotor.get("families")))
        if not families or not set(families) <= owned:
            continue
        blade_one = blade_azimuth_deg(
            rotor.get("blade1_azimuth_deg"),
            step=step,
            steps_per_revolution=rotor.get("steps_per_revolution"),
            rpm=rotor.get("rpm"),
        )
        return str(alias), _own_blade_azimuth(families, rotor, blade_one)
    return None, None


def _own_blade_azimuth(
    families: Sequence[str], rotor: Mapping[str, object], blade_one_deg: float | None
) -> float | None:
    """Return the azimuth of the ONE blade a block cuts, else blade one's (``blade_one_deg``)."""
    grouped = rotor.get("blade_families")
    if isinstance(grouped, str) or not isinstance(grouped, Sequence):
        return blade_one_deg
    blades = [set(_names_of(members)) for members in grouped]
    cut = [number for number, members in enumerate(blades, start=1) if set(families) <= members]
    if len(cut) != 1:
        return blade_one_deg
    return placed_blade_azimuth_deg(blade_one_deg, blade=cut[0], blades=len(blades))


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

    Parameters
    ----------
    polar : str or int
        The polar's number.
    mach : float
        The Mach number, written as its two-digit code.
    group : str or int
        The plot group's number.

    Returns
    -------
    str
        The polar table's file name.
    """
    return f"{polar}_M{_mach_code(mach):02d}_g{int(group):02d}.csv"


# --- the post's one CSV reader (0.33.0, AD-10: moved from post.products) ---


def read_csv_table(
    path: str | Path, *, skip: int = 0
) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    """Read one CSV table back: its columns and its rows as mappings of text.

    Values come back as the text written, so a caller decides what is a
    number; a row whose width differs from the header is refused naming
    the line, which is what makes the round trip a proof.

    ``skip`` drops that many lines before the header. No table the post writes
    since 0.27.0 has one (G16): its first line is the header and its first
    column `POL`. A rotor table written by 0.23.0 to 0.26.x leads with its
    rotor's alias alone on the first line, and ``skip=1`` reads it.

    Parameters
    ----------
    path : str or Path
        The CSV table.
    skip : int, optional
        Lines dropped before the header.

    Returns
    -------
    tuple of (tuple of str, list of dict of str to str)
        The columns and the rows, each a mapping of column to the text written.

    Raises
    ------
    ProductError
        If the file is empty, or a row's width differs from the header's, naming the line.
    """
    target = Path(path)
    with target.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        for _ in range(max(0, int(skip))):
            next(reader, None)
        try:
            columns = tuple(next(reader))
        except StopIteration:
            raise ProductError(f"{target} is empty; a table has at least its header") from None
        rows = []
        for number, cells in enumerate(reader, start=2):
            if len(cells) != len(columns):
                raise ProductError(
                    f"{target} line {number} carries {len(cells)} values for {len(columns)} columns"
                )
            rows.append(dict(zip(columns, cells, strict=True)))
    return columns, rows


# --- the plots-table readers (0.33.0, AD-10: moved from post.products) ---

#: PFS-2038.04. The column an unsteady plots export states its clock in.
#: Private here, since this module's public names are the ones post.products
#: lists; post.products keeps it as ``PLOTS_STEP_COLUMN`` (0.33.0, AD-10).
#: The same name `post.superfile` and the probe table already read, and the
#: same rule those two write down: the step a sample came from is not a guess.
_PLOTS_STEP_COLUMN = "Time-step"


def _stated_steps(columns: Sequence[str], values: np.ndarray, n_rows: int) -> np.ndarray:
    """Return the exported clock where the table states one, the ordinal otherwise."""
    ordinal = np.arange(1, n_rows + 1, dtype=int)
    if _PLOTS_STEP_COLUMN not in columns or not n_rows:
        return ordinal
    stated = values[:, list(columns).index(_PLOTS_STEP_COLUMN)]
    if not bool(np.all(np.isfinite(stated))):
        return ordinal
    whole = np.rint(stated)
    if not bool(np.all(np.abs(stated - whole) < 1e-9)):
        # A fractional clock is a time and not a step; the windows a
        # reduction states are whole steps, so the ordinal is what is left.
        return ordinal
    steps = whole.astype(int)
    if n_rows > 1 and not bool(np.all(np.diff(steps) > 0)):
        # Duplicated or out of order. Selecting a window by value would
        # then pick rows the window did not name, which is worse than the
        # ordinal it has always used.
        return ordinal
    return steps


def plots_table_series(path: str | Path) -> tuple[tuple[str, ...], TimestepSeries]:
    """Read a written plots table back as the series its reductions are taken over.

    THE TABLE'S OWN CLOCK WHEN IT STATES ONE (PFS-2038.04, GEO-039-F05).
    The export writes one row per time step (the manual's paraphrase in the
    database entry for ``UNSTEADY_SOLVER_EXPORT_PLOTS``) and states the step
    it wrote in a ``Time-step`` column; the step axis is that column, so a
    window's ``FIRST_STEP`` and ``LAST_STEP`` mean what the file means. This
    used to be the row number regardless, so an export whose clock does not
    begin at one was labelled with ordinals and could not be reduced by its
    own step numbers.

    MEASURED 2026-09-11 over every recorded plots export in these
    workspaces: 49 of 49 begin at 1 and step by 1, so the column and the
    ordinal agree on every export this solver has produced and nothing
    already recorded changes. What this closes is the silent mislabel if an
    offset or sparse clock ever arrives.

    THE ORDINAL REMAINS THE FALLBACK, for a table that states no such
    column and for one whose column is not a strictly increasing whole
    number: a product is better than a refusal there, and the review's
    coverage validation, which would refuse windows that work today, is
    deliberately not taken. The column is still carried as a FIELD as well,
    so no existing product loses a value.

    Every column is one field of one sample, since the plots table samples
    no position; the sample position is the origin, which stands for the
    configuration the plot was defined over.

    Read from the WRITTEN table rather than from the export in memory, so a
    reduction is of the file a user holds and can be recomputed from it.

    `POL` IS NOT A PLOTTED QUANTITY (G16, 0.27.0). The table opens with the
    polar its point belongs to, which says which polar the file is OF and is
    no field of any sample: it is left out of the columns and of the series,
    so no reduction averages it and no reduction states it twice. A table
    written before 0.27.0 carries no such column and reads as it always did.

    Parameters
    ----------
    path : str or Path
        A plots table the post wrote.

    Returns
    -------
    tuple
        The table's plotted columns, in its order, and the series.
    """
    header, rows = read_csv_table(path)
    columns = tuple(name for name in header if name != POLAR_ID_COLUMN)
    values = np.asarray([[float(row[name]) for name in columns] for row in rows], dtype=float)
    return columns, TimestepSeries(
        steps=_stated_steps(columns, values, len(rows)),
        times_s=None,
        points=np.zeros((1, 3)),
        fields={name: values[:, index][:, None] for index, name in enumerate(columns)},
        sources=(Path(path),),
    )
