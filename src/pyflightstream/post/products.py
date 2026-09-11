"""The campaign's post-processed products: polar, section and plot tables as CSV.

PFS-2029.15. A campaign's raw exports are the solver's own text files, one
set per point; the products are the tables a study reads and plots, and
this module writes them as plain CSV, one header line and one row per
record, so any spreadsheet or dataframe reads them with nothing else:

* a POLAR table per boundary GROUP of the pproc artifact, under
  ``polars/`` since 0.16.0 (FR-88): one row per point of the polar, the
  reference block and the coefficients of the group in body, stability
  and wind axes with the two drag parts;
* the SUPERFILE of each polar and group beside it since 0.16.0 (FR-89),
  ``polars/SUPER-<point with the swept variable as sweep>_g<NN>.csv``:
  one row per CONVERGED point, written after the unsteady post-process so
  it holds no time series, and its column set is a SUPERSET of the union
  of everything the workspace knows about that simulation. The assembly
  is :mod:`pyflightstream.post.superfile`, which says where each of its
  blocks comes from;
* a SECTIONS table per point, ``sections/<point>_sections.csv``: the
  sectional loads export re-tabled, when the run defined sections at all;
* the FLOW-FIELD SAMPLES of a point under ``probes/`` since 0.16.0
  (FR-87), whatever the run type was: ``probes/<point>_plots.csv``, the
  unsteady plots export re-tabled with its coefficient columns brought
  from the solver's reference velocity to the free stream, and
  ``probes/<point>_probes.csv``, the probe-points export of a row of any
  kind re-tabled in its own units;
* the REDUCTIONS of that table, one file per applicable reduction beside
  it (PFS-2015.04): ``probes/<point>_time_average.csv``,
  ``probes/<point>_phase_locked.csv`` and
  ``probes/<point>_per_blade.csv``,
  each a row per window with the window in solver steps and then the
  plots table's own columns averaged over it. Since 0.15.0 a row that
  NAMES ITS ROTORS reduces per rotor (FR-68), so the two passage files
  carry the rotor's alias, ``probes/<point>_per_blade_<ALIAS>.csv``, and
  their manifest entries carry a ``rotor`` field; the time average is one
  file whatever turns in the run. Raw is the plots table
  itself and is written once. The windows come off the run record, which
  the run stage resolved from the row
  (:func:`pyflightstream.cases.workflows.reduction_windows`), and a
  reduction the row could not window is recorded under ``skipped`` in
  ``products.json`` with its reason, as a refused polar is;
* THE CUSTOM POLAR FORMAT beside each polar table when the pproc artifact asks
  (``[products] custom_polar_format = true``, PFS-2014.01.01):
  ``<polar>_M<mach code>_g<group>.dat``, the same rows in the fixed-width
  text file the author's existing tooling opens, specified line by line in
  :func:`write_custom_polar_format` and read back by
  :func:`read_custom_polar_format`;
* a PROVENANCE document per recorded run, under ``provenance/`` and
  named by the point's own convention since 0.16.0 (FR-86)
  (PFS-2012.08.01): W3C PROV in its PROV-JSON serialization, the staged
  inputs, the script and the outputs as entities with their sha256, the
  solver run as the activity with its start, end and argv, the package
  and the solver build as agents.

THE ARITHMETIC IS THE AUTHOR'S, re-derived here from the author's recorded files and
never imported. FlightStream's ``CL``, ``CDi + CDo`` and ``Cy`` are the
STABILITY-axis force coefficients and the body-axis forces follow by
turning them through the angle of attack; the solver's ``CMx`` and ``CMz``
are the BODY-axis rolling and yawing moments, scaled from the chord to the
span and, by the author's sign convention, negated, and the stability-axis moments
follow by turning them through the angle of attack. The author's polars carried
``BETA 0.0`` on every row, so the wind axes coincide with the stability
axes in every table this writer has been checked against; a point with a
non-zero sideslip is REFUSED naming the point, because the wind-axis turn
through sideslip has been checked against nothing. Values are written at
five decimals, the author's precision, so a table regenerated from the same exports
is equal text. The evidence is the products arm of GOAL-011,
``python GeoversePlan/goals/check_goal_011.py --products``, which
regenerates the author's 27 recorded polars and 5 section tables through
:func:`write_recorded_polar` and compares them with the author's own tables
converted to this shape outside the package: 32 of 32 equal on 2026-09-03.
"""

from __future__ import annotations

import csv
import json
import math
import warnings
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from pyflightstream._digest import file_sha256
from pyflightstream._errors import (
    PyflightstreamError,
    PyflightstreamWarning,
)
from pyflightstream.cases import select_group_members
from pyflightstream.cases.workflows import (
    PER_ROTOR_REDUCTIONS,
    REDUCTION_NAMES,
    ROTORS_KEY,
)
from pyflightstream.fsi.loads import SectionalLoadsReport, parse_sectional_loads
from pyflightstream.post._tables import (
    _COEFFICIENT_PLOT_PREFIXES,
    _DECIMALS,
    SECTION_COLUMNS,
    ProductError,
    ProductExistsError,
    write_csv_table,
)
from pyflightstream.post.series import write_point_series
from pyflightstream.post.superfile import (
    SuperfileDraft,
    declared_sweep,
    matrix_rows,
    plots_last_row,
    super_file_name,
    superfile_row,
    union_the_workspace_knows,
    write_superfile_report,
    write_superfiles,
)
from pyflightstream.post.unsteady import TimestepSeries, blade_passage_average
from pyflightstream.results import (
    LoadsReport,
    MalformedOutputError,
    UnsteadyPlotsReport,
    labeled_value,
    parse_loads,
    parse_probe_points,
    parse_unsteady_plots,
)
from pyflightstream.workspace import RunStatus
from pyflightstream.workspace.naming import polar_name

if TYPE_CHECKING:
    from pyflightstream.cases.matrix import MatrixRow
    from pyflightstream.workspace import CampaignWorkspace, RunRecord

__all__ = [
    "ADVANCE_RATIO_COLUMN",
    "COEFFICIENT_COLUMNS",
    "POLAR_COLUMNS",
    "SWEEP_AXES",
    "POLARS_DIR",
    "PROBES_DIR",
    "PROVENANCE_DIR",
    "PROVENANCE_SUFFIX",
    "SECTION_COLUMNS",
    "GroupCoefficients",
    "CustomPolarTable",
    "PRODUCTS_MANIFEST",
    "REDUCTION_COLUMNS",
    "PolarPoint",
    "ProductError",
    "ProductExistsError",
    "ReferenceValues",
    "group_coefficients",
    "custom_polar_file_name",
    "plots_table_series",
    "point_name_of",
    "polar_file_name",
    "polar_row",
    "swept_axes",
    "swept_polar_file_name",
    "provenance_file_name",
    "read_csv_table",
    "read_custom_polar_format",
    "write_csv_table",
    "write_custom_polar_format",
    "write_plots_table",
    "write_probes_table",
    "write_reduction_table",
    "write_polar_table",
    "write_campaign_products",
    "write_recorded_polar",
    "write_sections_table",
]

#: The twenty-four coefficient columns of a polar row, in the author's order: the
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

#: The column naming the ADVANCE RATIO of a polar row (FR-85).
#:
#: WHY IT EXISTS. Measured on the author's ``0001_M15_g01.csv``, written by
#: 0.15.0 for a three-value sweep of the advance ratio: the three rows
#: carried identical ``ALPHA``, ``BETA``, ``MACH`` and ``RE`` and no
#: column naming what was swept, so the only thing distinguishing the
#: first row from the third was its position in the file. A table whose
#: rows are told apart by order is not a table.
#:
#: IT IS OUTSIDE :data:`COEFFICIENT_COLUMNS` on purpose: those
#: twenty-four are the custom format's own line 9 and its fixture pins
#: them, so a flight-condition column added there would change a file
#: format that was specified line by line.
ADVANCE_RATIO_COLUMN = "J"

#: A polar table's columns: the polar, its description, the group, the
#: reference block, the advance ratio, the twenty-four coefficients.
POLAR_COLUMNS: tuple[str, ...] = (
    "POLAR",
    "DESCRIPTION",
    "GROUP",
    *_REFERENCE_COLUMNS,
    ADVANCE_RATIO_COLUMN,
    *COEFFICIENT_COLUMNS,
)


#: A sections table's columns: the point and its condition, then the
#: sectional loads export's own seven columns, in its units.
@dataclass(frozen=True)
class ReferenceValues:
    """The reference block of a product: SREF, CREF, BREF and the moment point.

    The moment point is in the geometry's own coordinate system, the one the
    solver holds the mesh in and reports loads about (the MRP frame the author's
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


@dataclass(frozen=True)
class GroupCoefficients:
    """The coefficients of one group, summed over its families, as the solver reports them.

    ``lift``, ``drag`` and ``side`` are the STABILITY-axis forces; ``roll``,
    ``pitch`` and ``yaw`` are the BODY-axis moments, ``roll`` and ``yaw``
    already scaled from the chord to the span and carrying the author's sign. That
    is the mixed convention the solver's loads table reports in, and
    :func:`polar_row` turns each half into the other axes from there.
    """

    drag: float
    side: float
    lift: float
    roll: float
    pitch: float
    yaw: float
    drag_profile: float
    drag_induced: float
    families_used: tuple[str, ...]


@dataclass(frozen=True)
class PolarPoint:
    """One point of a polar: its loads report and where it came from.

    ``point`` is the sweep point the RECORD states, which is what the
    point was ASKED for; the angles below are what the solver REPORTED
    and are read off the table. The two are separate on purpose: the file
    name and the swept column are about the request (FR-85), and the
    coefficients are about the answer.
    """

    name: str
    loads: LoadsReport
    loads_path: Path
    point: Mapping[str, float] | None = None

    @property
    def alpha_deg(self) -> float:
        """The point's angle of attack, from its loads table."""
        return self.loads.angle_of_attack_deg

    @property
    def beta_deg(self) -> float:
        """The point's sideslip, from its loads table."""
        return self.loads.sideslip_deg


def group_coefficients(
    loads: LoadsReport,
    families: Sequence[int | str],
    *,
    bref_m: float,
    aliases: Mapping[str, Sequence[str]] | None = None,
    empty_is_every: bool = False,
) -> GroupCoefficients:
    """Sum the loads table's rows over the families of one group.

    The members are resolved against the table's surface rows by
    :func:`pyflightstream.cases.select_group_members`: a name is its row,
    an alias of the row's setup (``aliases``, as the run record carries
    them) is its members' rows, a family is every row of it. A family
    the table does not carry is left out, as the author's writer left it out; a
    group none of whose families is in the table sums to zero, which is
    what the author's products carry for the rotor groups of a wing-body
    polar. The rolling and yawing moments are the solver's ``CMx`` and
    ``CMz``, scaled from the reference chord to the span and negated,
    the author's convention.

    ``empty_is_every`` is what an EMPTY member list means, and it is
    False here on purpose (the interface lens of 2026-09-09). The author's
    decision of that day is about the ARTIFACT: a ``[groups]`` entry
    written empty is every family, and the products stage passes True
    for it. A Python caller that built ``families`` by filtering and got
    an empty list still sums to zero, which is what this function did
    before and what its docstring promised.
    """
    cref = loads.reference_length
    if cref is None:
        raise ProductError("the loads table states no reference length, so no span scaling")
    drag = side = lift = roll = pitch = yaw = profile = induced = 0.0
    used: list[str] = []
    selected: list[str] = []
    if families or empty_is_every:
        selected = select_group_members(families, list(loads.surfaces), aliases)
    for family in selected:
        row = loads.surfaces[family]
        used.append(family)
        drag += row["CDi"] + row["CDo"]
        side += row["Cy"]
        lift += row["CL"]
        roll -= row["CMx"] * cref / bref_m
        pitch += row["CMy"]
        yaw -= row["CMz"] * cref / bref_m
        profile += row["CDo"]
        induced += row["CDi"]
    return GroupCoefficients(drag, side, lift, roll, pitch, yaw, profile, induced, tuple(used))


def polar_row(
    alpha_deg: float,
    mach: float,
    reynolds_millions: float,
    coefficients: GroupCoefficients,
    *,
    cref_m: float,
    bref_m: float,
) -> tuple[float, ...]:
    """Return the twenty-four coefficient values of one polar row.

    The author's polars carried ``BETA 0.0`` on every row, so the wind axes coincide
    with the stability axes in every table this row has been checked
    against; :func:`_polar_rows` refuses a point stating a sideslip, and the
    wind-axis turn below is written for the day one is checked.
    """
    beta_deg = 0.0
    a = math.radians(alpha_deg)
    b = math.radians(beta_deg)
    g = coefficients
    cds, cys, cls = g.drag, g.side, g.lift
    crb, cmb, cnb = g.roll, g.pitch, g.yaw
    cdb = cds * math.cos(a) - cls * math.sin(a)
    cyb = cys
    clb = cds * math.sin(a) + cls * math.cos(a)
    crs = crb * math.cos(a) + cnb * math.sin(a)
    cms = cmb
    cns = -crb * math.sin(a) + cnb * math.cos(a)
    cdw = cds * math.cos(b) - cys * math.sin(b)
    cyw = cds * math.sin(b) + cys * math.cos(b)
    clw = cls
    crw = crs * math.cos(b) + cms * math.sin(b) * cref_m / bref_m
    cmw = -crs * math.sin(b) * bref_m / cref_m + cms * math.cos(b)
    cnw = cns
    return (
        alpha_deg, beta_deg, mach, reynolds_millions,
        cdb, cyb, clb, crb, cmb, cnb,
        cds, cys, cls, crs, cms, cns,
        cdw, cyw, clw, crw, cmw, cnw,
        g.drag_profile, g.drag_induced,
    )  # fmt: skip


def _mach_code(mach: float) -> int:
    """Return the two-digit Mach code of the author's file names: ``round(mach * 100)``."""
    return round(mach * 100)


def polar_file_name(polar: str | int, mach: float, group: str | int) -> str:
    """``<polar>_M<mach code:02d>_g<group:02d>.csv``: one polar table per group.

    THE RECORDED CONVENTION, and the one the author's own tooling wrote
    before this package existed. :func:`write_recorded_polar` regenerates
    her recorded tables under it and is compared with her files name for
    name, which is why it stays. A polar table of a WORKSPACE is named by
    :func:`swept_polar_file_name`, the standard point convention (FR-85).
    """
    return f"{polar}_M{_mach_code(mach):02d}_g{int(group):02d}.csv"


#: The axes a polar can be swept over, spelled as a sweep point spells
#: them, in the order the point convention writes their fields.
SWEEP_AXES: tuple[str, ...] = ("alpha", "beta", "advance_ratio")


def swept_axes(points: Sequence[Mapping[str, float]]) -> tuple[str, ...]:
    """Return the axes that VARY across ``points``, in the convention's order (FR-85).

    Measured over the points rather than declared, so a one-point case
    sweeps nothing and a row whose matrix declared a sweep that resolved
    to a single value is named for the value it actually has. Compared at
    the precision the name itself writes, because two advance ratios that
    round to one field are one field.
    """
    varying = []
    for axis in SWEEP_AXES:
        seen = {round(float(point[axis]), 6) for point in points if point.get(axis) is not None}
        if len(seen) > 1:
            varying.append(axis)
    return tuple(varying)


def swept_polar_file_name(
    sim: str,
    *,
    mach: float,
    group: str | int,
    point: Mapping[str, float],
    swept: Sequence[str] = (),
    suffix: str = ".csv",
) -> str:
    """``<point convention with 'sweep' in the swept field>_g<group:02d>.csv`` (FR-85).

    The name the script and every export of the same point already carry,
    with the swept variable's field written as the literal word instead of
    one of its values: ``POLAR-0001_M15AL+000BE+000J+sweep_g01.csv``. The
    ``.dat`` of the custom format takes the same stem, which is what
    ``suffix`` is for.
    """
    stem = polar_name(
        sim,
        mach,
        float(point.get("alpha", 0.0) or 0.0),
        float(point.get("beta", 0.0) or 0.0),
        None if point.get("advance_ratio") is None else float(point["advance_ratio"]),
        swept=swept,
    )
    return f"{stem}_g{int(group):02d}{suffix}"


def read_csv_table(path: str | Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    """Read one CSV table back: its columns and its rows as mappings of text.

    Values come back as the text written, so a caller decides what is a
    number; a row whose width differs from the header is refused naming
    the line, which is what makes the round trip a proof.
    """
    target = Path(path)
    with target.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
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


def polar_table_rows(
    *,
    polar: str | int,
    description: str,
    group: str | int,
    reference: ReferenceValues,
    rows: Sequence[Sequence[float]],
    advance_ratios: Sequence[float | None] | None = None,
) -> list[tuple[object, ...]]:
    """Assemble the rows of one polar table, each under :data:`POLAR_COLUMNS`.

    ONE ASSEMBLY, TWO CONSUMERS, and that is why it is a function of its
    own rather than three lines inside the writer below. The superfile of
    FR-89 carries every column the polar table has, so it needs the same
    values the table is written from; building them a second time beside
    this one is exactly the shape that broke `legacy_products.py` on
    2026-09-10, where a column inserted in one assembly reached the other
    as a value under its neighbour's name.
    """
    lead = (str(polar), description, str(group), *reference.as_row())
    ratios = list(advance_ratios) if advance_ratios is not None else [None] * len(rows)
    if len(ratios) != len(rows):
        raise ProductError(
            f"the polar table was given {len(ratios)} advance ratios for {len(rows)} rows"
        )
    full: list[tuple[object, ...]] = []
    for row, ratio in zip(rows, ratios, strict=True):
        if len(row) != len(COEFFICIENT_COLUMNS):
            raise ProductError(f"a polar row has {len(row)} values, not {len(COEFFICIENT_COLUMNS)}")
        full.append((*lead, "" if ratio is None else float(ratio), *row))
    return full


def write_polar_table(
    path: str | Path,
    *,
    polar: str | int,
    description: str,
    group: str | int,
    reference: ReferenceValues,
    rows: Sequence[Sequence[float]],
    advance_ratios: Sequence[float | None] | None = None,
) -> Path:
    """Write one polar table: the reference block and the coefficients per point.

    ``advance_ratios`` is the advance ratio of each row in the row order,
    for :data:`ADVANCE_RATIO_COLUMN` (FR-85); a row whose ratio is not
    known writes an EMPTY cell rather than a zero, because zero is a
    value a rotor row can have and "not recorded" is not it. Omitted
    entirely, every row's cell is empty, which is what a caller with no
    sweep point to offer should write.
    """
    full = polar_table_rows(
        polar=polar,
        description=description,
        group=group,
        reference=reference,
        rows=rows,
        advance_ratios=advance_ratios,
    )
    return write_csv_table(path, POLAR_COLUMNS, full)


# --- PFS-2014.01: the custom polar format, the polar table as the author's tooling reads it --

#: The columns of the custom format's reference line: the nominal Mach and then the
#: reference block in the polar table's own order.
_CUSTOM_REFERENCE_COLUMNS: tuple[str, ...] = ("MNOM", *_REFERENCE_COLUMNS)

#: Every field of the custom format is right-aligned to this width.
_CUSTOM_WIDTH = 10

#: The author's date line, ``Tue Sep 08 23:41:07  2026``: two spaces before the year.
_CUSTOM_DATE_FORMAT = "%a %b %d %H:%M:%S  %Y"

_CUSTOM_TITLE_PREFIX = "FlightStream - "


@dataclass(frozen=True)
class CustomPolarTable:
    """One file of the custom polar format, read back: the header block and the rows.

    Attributes
    ----------
    description : str
        The title line's description, after ``FlightStream - ``.
    polar : str
        The polar identifier, line 2 without its two-digit Mach code.
    mach : float
        The nominal Mach number, ``MNOM`` of the reference line.
    date : str
        Line 3 as written; :func:`write_custom_polar_format` takes it back so
        a read file is rewritten byte for byte.
    group : int
        The group number of line 4.
    reference : ReferenceValues
        The reference block of line 6.
    columns : tuple of str
        The column names of line 9, in the file's order.
    rows : list of dict
        One mapping per data row, column name to value.
    """

    description: str
    polar: str
    mach: float
    date: str
    group: int
    reference: ReferenceValues
    columns: tuple[str, ...]
    rows: list[dict[str, float]]


def __getattr__(name: str) -> object:
    """Serve the polar format's former names, warning from the ledger.

    Those names carried a possessive prefix before 0.14.0 and are spelled
    ``custom`` now; the old ones are read until 0.16.0.
    """
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def custom_polar_file_name(polar: str | int, *, mach: float, group: str | int) -> str:
    """``<polar>_M<mach code:02d>_g<group:02d>.dat``: the custom format beside the polar table."""
    return polar_file_name(polar, mach, group)[: -len(".csv")] + ".dat"


def _custom_field(value: object) -> str:
    return f"{value!s:>{_CUSTOM_WIDTH}}"


def write_custom_polar_format(
    path: str | Path,
    *,
    polar: str | int,
    description: str,
    group: str | int,
    mach: float,
    reference: ReferenceValues,
    rows: Sequence[Sequence[float]],
    date: str | None = None,
) -> Path:
    """Write one polar of one group in the fixed-width text format the author's tooling opens.

    THIS DOCSTRING IS THE SPECIFICATION OF THE FORMAT (PFS-2014.01.02). The
    shape was read off a file of the author's and is pinned by the committed fixture
    ``tests/tier1_offline/fixtures/custom_polar_format_sample.dat``, whose
    every value is synthetic; the tier-1 test feeds the fixture's rows
    through this writer and requires byte equality with the fixture,
    except line 3. The file is ASCII, one line feed per line, a line feed
    after the last line, and no line carries a trailing space beyond the
    width of its fields:

    * line 1: the title, ``FlightStream - <description>``;
    * line 2: the polar identifier followed by the two-digit Mach code,
      ``<polar><round(mach * 100):02d>``, the same code the polar table's
      file name carries (``3207`` at Mach 0.20 is ``320720``);
    * line 3: the write time, ``%a %b %d %H:%M:%S  %Y`` of the local
      clock (``Tue Sep 08 23:41:07  2026``, two spaces before the year),
      or ``date`` verbatim when given, which is how a read file is
      rewritten byte for byte;
    * line 4: the number of reference columns as three digits, a space,
      and the group number as two digits: ``007 01``;
    * line 5: the reference column names ``MNOM SREF CREF BREF XMOM YMOM
      ZMOM``, each right-aligned to width 10;
    * line 6: their values, the nominal Mach and the reference block, each
      written as Python writes a float (the shortest text that reads
      back to the same number, ``50.0`` and ``2.526``) and right-aligned
      to width 10;
    * line 7: the number of data rows as three digits, ``013``;
    * line 8: the number of data columns as three digits, ``024``;
    * line 9: the twenty-four column names, exactly
      :data:`COEFFICIENT_COLUMNS` in that order, each right-aligned to
      width 10;
    * then one line per data row, every number formatted ``%10.5f``
      (width 10, five decimals, the author's precision), in the column order of
      line 9, the rows in the order given (the stage gives them alpha
      ascending, as the polar table).

    The rows are the same twenty-four values the polar table carries per
    point (:func:`polar_row`), so the two files are two serializations of
    one table; :func:`read_custom_polar_format` reads this one back.

    Parameters
    ----------
    path : str or pathlib.Path
        Destination, ``<polar>_M<code>_g<group>.dat`` beside the polar table.
    polar : str or int
        The polar identifier, the simulation id.
    description : str
        The row's description, as the polar table carries it.
    group : str or int
        The group number.
    mach : float
        The nominal Mach number, written as ``MNOM`` and as the code of line 2.
    reference : ReferenceValues
        The reference block.
    rows : sequence of sequence of float
        The coefficient rows, each of :data:`COEFFICIENT_COLUMNS` width.
    date : str, optional
        Line 3 as it should be written; the local clock when None.

    Returns
    -------
    pathlib.Path
        The file written.

    Raises
    ------
    ProductError
        If a row is not twenty-four values wide.
    """
    lines = [
        f"{_CUSTOM_TITLE_PREFIX}{description}",
        f"{polar}{_mach_code(mach):02d}",
        date if date is not None else datetime.now().strftime(_CUSTOM_DATE_FORMAT),
        f"{len(_CUSTOM_REFERENCE_COLUMNS):03d} {int(group):02d}",
        "".join(_custom_field(name) for name in _CUSTOM_REFERENCE_COLUMNS),
        "".join(_custom_field(float(value)) for value in (mach, *reference.as_row())),
        f"{len(rows):03d}",
        f"{len(COEFFICIENT_COLUMNS):03d}",
        "".join(_custom_field(name) for name in COEFFICIENT_COLUMNS),
    ]
    for row in rows:
        if len(row) != len(COEFFICIENT_COLUMNS):
            raise ProductError(f"a polar row has {len(row)} values, not {len(COEFFICIENT_COLUMNS)}")
        lines.append("".join(f"{float(value):{_CUSTOM_WIDTH}.{_DECIMALS}f}" for value in row))
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(("\n".join(lines) + "\n").encode("ascii"))
    return target


def _custom_count(line: str, path: Path, number: int, what: str) -> int:
    try:
        return int(line.split()[0])
    except (IndexError, ValueError):
        raise ProductError(
            f"{path} line {number} should be the number of {what} as digits; it reads {line!r}"
        ) from None


def read_custom_polar_format(path: str | Path) -> CustomPolarTable:
    """Read a custom polar format file back, as :func:`write_custom_polar_format` specifies it.

    The counts the file states are checked against what it holds, which is
    what makes the round trip (write, read, write again) a proof rather
    than a re-echo: a reference line, a row or a row's width that does not
    fit its count is refused naming the line.

    Parameters
    ----------
    path : str or pathlib.Path
        A file in the custom format.

    Returns
    -------
    CustomPolarTable
        The header block and the rows, each row a mapping of column name to
        value.

    Raises
    ------
    ProductError
        If the file does not have the shape the writer's docstring states.
    """
    target = Path(path)
    lines = target.read_text(encoding="ascii").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if len(lines) < 9 or not lines[0].startswith(_CUSTOM_TITLE_PREFIX):
        raise ProductError(
            f"{target} is not in the custom polar format: it needs nine header lines, the first "
            f"beginning {_CUSTOM_TITLE_PREFIX!r}"
        )
    description = lines[0][len(_CUSTOM_TITLE_PREFIX) :]
    identifier = lines[1].strip()
    if len(identifier) < 3 or not identifier[-2:].isdigit():
        raise ProductError(
            f"{target} line 2 should be the polar identifier and a two-digit Mach code; "
            f"it reads {lines[1]!r}"
        )
    counts = lines[3].split()
    if len(counts) != 2:
        raise ProductError(
            f"{target} line 4 should be the reference count and the group number; "
            f"it reads {lines[3]!r}"
        )
    reference_count, group = int(counts[0]), int(counts[1])
    names = tuple(lines[4].split())
    values = lines[5].split()
    if len(names) != reference_count or len(values) != reference_count:
        raise ProductError(
            f"{target} line 4 states {reference_count} reference columns and lines 5 and 6 "
            f"carry {len(names)} names and {len(values)} values"
        )
    reference_values = dict(zip(names, (float(v) for v in values), strict=True))
    row_count = _custom_count(lines[6], target, 7, "data rows")
    column_count = _custom_count(lines[7], target, 8, "data columns")
    columns = tuple(lines[8].split())
    if len(columns) != column_count:
        raise ProductError(
            f"{target} line 8 states {column_count} columns and line 9 names {len(columns)}"
        )
    data = lines[9:]
    if len(data) != row_count:
        raise ProductError(
            f"{target} line 7 states {row_count} rows and the file holds {len(data)}"
        )
    rows: list[dict[str, float]] = []
    for number, line in enumerate(data, start=10):
        cells = line.split()
        if len(cells) != column_count:
            raise ProductError(
                f"{target} line {number} carries {len(cells)} values for {column_count} columns"
            )
        rows.append(dict(zip(columns, (float(c) for c in cells), strict=True)))
    mach = reference_values.pop("MNOM", None)
    if mach is None:
        raise ProductError(f"{target} line 5 names no MNOM column; it names {names}")
    return CustomPolarTable(
        description=description,
        polar=identifier[:-2],
        mach=mach,
        date=lines[2],
        group=group,
        reference=ReferenceValues.from_mapping(reference_values),
        columns=columns,
        rows=rows,
    )


def _reynolds_millions(text: str) -> float:
    return float(labeled_value(text, "Reynolds Number")) / 1e6


def _altitude_ft(text: str) -> float:
    try:
        return float(labeled_value(text, "Altitude (ft)"))
    except (MalformedOutputError, ValueError):
        return 0.0


def write_sections_table(
    path: str | Path, export_text: str, *, point: str, mach: float
) -> Path | None:
    """Write one sections table from a sectional loads export.

    Returns None without writing when the export declares no section, as
    a run that defined no distribution leaves; the columns are the point,
    its condition, and the export's own seven, in the export's units.
    """
    # A run that defined no distribution leaves an export declaring zero
    # sections, which the parser refuses as impossible for a real table;
    # here it is the ordinary case of a steady polar and means no product.
    try:
        declared = int(float(labeled_value(export_text, "Number of Surface Sections:")))
    except (MalformedOutputError, ValueError):
        declared = -1
    if declared == 0:
        return None
    try:
        report: SectionalLoadsReport = parse_sectional_loads(export_text)
    except PyflightstreamError as error:
        raise ProductError(f"the sectional loads export cannot be read: {error}") from error
    if report.count == 0:
        return None
    table = np.asarray(report.values, dtype=float)
    if table.shape[1] < 7:
        raise ProductError(
            f"the sectional loads export carries {table.shape[1]} columns, fewer than the seven "
            "the product tables"
        )
    lead = (
        point,
        report.angle_of_attack_deg,
        report.sideslip_deg,
        mach,
        report.freestream_velocity_m_s,
        _reynolds_millions(export_text),
        _altitude_ft(export_text),
    )
    rows = [(*lead, *(float(v) for v in row[:7])) for row in table]
    return write_csv_table(path, SECTION_COLUMNS, rows)


def write_plots_table(path: str | Path, export_text: str) -> Path | None:
    """Write one plots table from an unsteady plots export.

    The coefficient columns (``CL_``, ``CDI_``, ``CDO_``, ``CD_``) are
    multiplied by the square of the reference velocity over the free
    stream, so a run whose reference velocity differs from the free stream
    reads as free-stream coefficients. An export the reader cannot parse is
    a refusal naming the file, never a silent skip; an export with no step
    returns None.
    """
    try:
        report: UnsteadyPlotsReport = parse_unsteady_plots(export_text)
    except PyflightstreamError as error:
        raise ProductError(f"the unsteady plots export {path} cannot be read: {error}") from error
    values = np.asarray(report.values, dtype=float)
    if values.size == 0:
        return None
    vinf = float(labeled_value(export_text, "Freestream velocity (m/s)"))
    try:
        vref = float(labeled_value(export_text, "Reference velocity (m/s)"))
    except (MalformedOutputError, ValueError):
        vref = vinf
    scale = (vref / vinf) ** 2 if vinf else 1.0
    scaled = values.copy()
    for index, name in enumerate(report.columns):
        if name.startswith(_COEFFICIENT_PLOT_PREFIXES):
            scaled[:, index] *= scale
    return write_csv_table(
        path, tuple(report.columns), [tuple(float(v) for v in row) for row in scaled]
    )


def write_probes_table(path: str | Path, export_text: str) -> Path | None:
    """Write one probe-points table from an EXPORT_PROBE_POINTS export (FR-87).

    The flow-field samples of a point that is not an unsteady history:
    one row per probe point, the export's own columns in its own order
    and units, which carry the fluid quantities (``Mach``, ``Cp``,
    ``vx``, ``vy``, ``vz``, ``vtot``) beside the boundary-layer columns.
    Nothing is scaled: the plots table brings its COEFFICIENT columns
    from the solver's reference velocity to the free stream because those
    columns are coefficients, and a sampled velocity is not.

    It lands beside the unsteady plots table, under
    :data:`PROBES_DIR`, which is the whole point of FR-87: a steady row
    and an unsteady row citing the same artifact put their flow-field
    samples in one place. An export the reader cannot parse is a refusal
    naming the file, never a silent skip; an export with no probe point
    returns None, as an unsteady export with no step does, since a table
    of nothing is a promise of content that is not there.
    """
    try:
        report = parse_probe_points(export_text)
    except PyflightstreamError as error:
        raise ProductError(f"the probe points export {path} cannot be read: {error}") from error
    values = np.asarray(report.values, dtype=float)
    if values.size == 0:
        return None
    return write_csv_table(
        path, tuple(report.columns), [tuple(float(v) for v in row) for row in values]
    )


# --- PFS-2015.04: the reductions of a plots table, beside it -----------------------

#: The window block every reduction row carries before the plots table's own
#: columns: which reduction, which window of it (1-based), the inclusive
#: solver steps it spans, and how many rows of the table fell inside.
REDUCTION_COLUMNS: tuple[str, ...] = ("REDUCTION", "WINDOW", "FIRST_STEP", "LAST_STEP", "STEPS")


def plots_table_series(path: str | Path) -> tuple[tuple[str, ...], TimestepSeries]:
    """Read a written plots table back as the series its reductions are taken over.

    Row ``k`` of the table is solver step ``k``: the export writes one row
    per time step (the manual's paraphrase in the database entry for
    ``UNSTEADY_SOLVER_EXPORT_PLOTS``), so the step axis is the row number,
    1-based, and the table's own time column is carried as a field like
    any other rather than read as the clock. Every column is one field of
    one sample, since the plots table samples no position; the sample
    position is the origin, which stands for the configuration the plot
    was defined over.

    Read from the WRITTEN table rather than from the export in memory, so a
    reduction is of the file a user holds and can be recomputed from it.

    Returns
    -------
    tuple
        The table's columns, in its order, and the series.
    """
    columns, rows = read_csv_table(path)
    values = np.asarray([[float(row[name]) for name in columns] for row in rows], dtype=float)
    return columns, TimestepSeries(
        steps=np.arange(1, len(rows) + 1, dtype=int),
        times_s=None,
        points=np.zeros((1, 3)),
        fields={name: values[:, index][:, None] for index, name in enumerate(columns)},
        sources=(Path(path),),
    )


def write_reduction_table(
    path: str | Path,
    series: TimestepSeries,
    columns: Sequence[str],
    *,
    reduction: str,
    windows: Sequence[Sequence[int]],
) -> Path:
    """Write one reduction of a plots table: one row per window, the table's columns averaged.

    The average is :func:`pyflightstream.post.unsteady.blade_passage_average`,
    the only implementation of that average in the package, applied once
    per window; the time average is one window, the phase-locked reduction
    one per passage, the per-blade reduction one per blade. Values are at
    the table's five decimals.

    Parameters
    ----------
    path : str or pathlib.Path
        Destination CSV, beside the plots table it reduces.
    series : TimestepSeries
        The plots table as :func:`plots_table_series` reads it.
    columns : sequence of str
        The plots table's columns, in its order.
    reduction : str
        ``time_average``, ``phase_locked`` or ``per_blade``.
    windows : sequence of (first, last)
        Inclusive solver-step windows, 1-based, each inside the table.

    Raises
    ------
    ProductError
        If a window reaches past the rows the table holds: a shorter
        history averaged as a whole one is the shape every reader here
        refuses, and the caller records the refusal as a skip.
    """
    rows: list[tuple[object, ...]] = []
    last_row = series.n_frames
    for index, (first, last) in enumerate(windows, start=1):
        if int(last) > last_row or int(first) < 1:
            raise ProductError(
                f"the plots table holds {last_row} rows and the {reduction} window {index} "
                f"spans steps {first} to {last}, so the history is shorter than the window "
                "the row states; a shorter history averaged as a whole one would be an "
                "average of a run that did not finish writing"
            )
        average = blade_passage_average(series, window=(int(first), int(last)))
        rows.append(
            (
                reduction,
                index,
                int(first),
                int(last),
                average.n_frames,
                *(float(average.fields[name][0]) for name in columns),
            )
        )
    return write_csv_table(path, (*REDUCTION_COLUMNS, *columns), rows)


def _polar_points(polar_dir: Path, *, loads_suffix: str = ".txt") -> list[PolarPoint]:
    """Return the points of a recorded polar: one folder per point, its loads table inside."""
    points: list[PolarPoint] = []
    for folder in sorted(p for p in polar_dir.iterdir() if p.is_dir()):
        loads_path = folder / f"{folder.name}{loads_suffix}"
        if not loads_path.is_file():
            continue
        text = loads_path.read_text(encoding="utf-8", errors="replace")
        try:
            report = parse_loads(text)
        except PyflightstreamError as error:
            raise ProductError(f"{loads_path} is not a loads table: {error}") from error
        points.append(PolarPoint(name=folder.name, loads=report, loads_path=loads_path))
    if not points:
        raise ProductError(f"{polar_dir} holds no point folder with a loads table")
    return sorted(points, key=lambda point: point.alpha_deg)


def _polar_rows(
    points: Sequence[PolarPoint],
    families: Sequence[int | str],
    *,
    mach: float,
    reference: ReferenceValues,
    aliases: Mapping[str, Sequence[str]] | None = None,
) -> list[tuple[float, ...]]:
    """Return the coefficient rows of one group over the points of a polar, alpha ascending.

    This is the ARTIFACT's path, so an empty member list is every family
    (the author's decision of 2026-09-09) and the summer is asked for that reading.
    """
    rows = []
    for point in points:
        reynolds = point.loads.reynolds
        if reynolds is None:
            raise ProductError(f"{point.loads_path} states no Reynolds number")
        if point.beta_deg != 0.0:
            raise ProductError(
                f"{point.loads_path} states a sideslip of {point.beta_deg} deg, and the polar "
                "table's wind-axis columns have been checked against the recorded tables at "
                "zero sideslip only; a polar under sideslip is not written by this release. "
                "Leave the point out of the products, or state the sweep without sideslip."
            )
        coefficients = group_coefficients(
            point.loads,
            list(families),
            bref_m=reference.bref_m,
            aliases=aliases,
            empty_is_every=True,
        )
        rows.append(
            polar_row(
                point.alpha_deg,
                mach,
                reynolds / 1e6,
                coefficients,
                cref_m=reference.cref_m,
                bref_m=reference.bref_m,
            )
        )
    return rows


def write_recorded_polar(
    polar_dir: str | Path,
    out_dir: str | Path,
    *,
    groups: Mapping[str, Sequence[str]],
    reference: Mapping[str, float] | ReferenceValues,
    description: str,
    mach: float,
    sections: bool = True,
    plots: bool = False,
    aliases: Mapping[str, Sequence[str]] | None = None,
) -> list[Path]:
    """Write every product of one recorded polar from its point folders.

    ``polar_dir`` is ``POLAR-<n>/`` holding one folder per point, each with
    the point's loads table ``<point>.txt`` and, when the run left them, the
    sectional loads ``<point>_sloads.txt`` and the plots ``<point>_plots.txt``.
    One polar table is written per group of ``groups`` (the pproc
    artifact's ``[groups]`` table, name to families), a sections table per
    point whose export declares sections, and, when asked, a plots table
    per point that has a plots export. Returns the paths written, in order.
    """
    polar_dir = Path(polar_dir)
    out = Path(out_dir)
    ref = (
        reference
        if isinstance(reference, ReferenceValues)
        else ReferenceValues.from_mapping(reference)
    )
    polar = polar_dir.name.split("-")[-1] if polar_dir.name.startswith("POLAR-") else polar_dir.name
    points = _polar_points(polar_dir)
    written: list[Path] = []
    for group, families in groups.items():
        written.append(
            write_polar_table(
                out / polar_file_name(polar, mach, group),
                polar=polar,
                description=description,
                group=group,
                reference=ref,
                rows=_polar_rows(points, list(families), mach=mach, reference=ref, aliases=aliases),
            )
        )
    for point in points:
        folder = point.loads_path.parent
        sloads = folder / f"{point.name}_sloads.txt"
        if sections and sloads.is_file():
            target = write_sections_table(
                out / "sections" / f"{point.name}_sections.csv",
                sloads.read_text(encoding="utf-8", errors="replace"),
                point=point.name,
                mach=mach,
            )
            if target is not None:
                written.append(target)
        plots_export = folder / f"{point.name}_plots.txt"
        if plots and plots_export.is_file():
            target = write_plots_table(
                out / PROBES_DIR / f"{point.name}_plots.csv",
                plots_export.read_text(encoding="utf-8", errors="replace"),
            )
            if target is not None:
                written.append(target)
    return written


# --- PFS-2029.15.03: the products of a campaign, from its manifest ---------------

#: The manifest of the products: which file came from which runs and pproc.
PRODUCTS_MANIFEST = "products.json"

#: The folder under a matrix's products where the per-polar tables and
#: their ``.dat`` companions land (FR-88).
#:
#: WHY THEY MOVED. Measured in the workspace the author sent back after
#: running 0.15.0: `post/matriz/` held the polar tables LOOSE at its top
#: level beside `sections/`, `plots/` and `provenance/`, so the same
#: folder read as a directory and as a drawer at once. Every other family
#: of file already had a directory and this one did not.
#:
#: THE CAMPAIGN-LEVEL FILES DO NOT MOVE HERE, and that is the half a
#: check for an empty top level would not see: `products.json` and
#: `campaign_sweep.csv` are about the CAMPAIGN rather than about one
#: polar's sweep, so sweeping them in would be wrong in exactly the way
#: that passes a shallower test.
POLARS_DIR = "polars"

#: The folder under a matrix's products where the FLOW-FIELD SAMPLES of a
#: point land, whatever the run type was (FR-87).
#:
#: IT WAS ``plots`` UNTIL 0.16.0, after the solver verb that produced the
#: file rather than after what the file holds. THE GENERICITY IS THE
#: REQUIREMENT and not a side effect of the rename: a reader of a
#: finished campaign should not have to know whether a row was steady or
#: unsteady to know where the flow-field samples are, so the unsteady
#: plots table, its reductions and the probe-points table of any row all
#: land here.
PROBES_DIR = "probes"


def _refuse_an_existing_product(path: Path, *, overwrite: bool) -> Path:
    """Return ``path``, refusing it when it exists and the caller did not ask to rewrite."""
    if path.exists() and not overwrite:
        raise ProductExistsError(
            f"the product {path} exists; pass overwrite (CLI: --overwrite) to rewrite "
            "it from the manifest"
        )
    return path


def _sweep_rows(
    workspace: CampaignWorkspace, matrix_stem: str | None
) -> dict[str, dict[str, object]]:
    """Return the campaign sweep table's own rows, keyed by run id (FR-89).

    The frame `campaign_sweep.csv` is written from, read here so the
    superfile carries what that file holds by carrying the SAME row. A
    campaign whose records yield no table at all leaves this empty and the
    superfile is short of those columns rather than of the whole file:
    every other block of the row is independent of this one.
    """
    from pyflightstream.results.tables import sweep_table

    try:
        with warnings.catch_warnings():
            # The "no run yielded coefficients" warning belongs to the caller
            # who asked for a sweep table, not to a products stage reading it
            # as one source among seven.
            warnings.simplefilter("ignore", PyflightstreamWarning)
            frame = sweep_table(workspace, require_loads=False, matrix_stem=matrix_stem)
    except (PyflightstreamError, OSError, ValueError):
        return {}
    rows: dict[str, dict[str, object]] = {}
    for row in frame.to_dict("records"):
        run_id = row.get("run_id")
        if run_id is not None:
            rows[str(run_id)] = row
    return rows


def _sim_products(
    workspace: CampaignWorkspace,
    sim_id: str,
    records: Sequence[RunRecord],
    out: Path,
    *,
    overwrite: bool,
    matrix_row: MatrixRow | None = None,
    sweep_rows: Mapping[str, Mapping[str, object]] | None = None,
    drafts: list[SuperfileDraft] | None = None,
) -> tuple[list[Path], dict[str, dict[str, object]], dict[str, str]]:
    """Write one simulation's products from its successful records.

    Returns the files written, the manifest entry of each (its run ids and,
    for a reduction, the reduction and the windows it used), and the
    reductions skipped by name with the reason.

    ``drafts`` collects this simulation's SUPERFILES (FR-89), one per group,
    which are written by the caller and not here: their header is the union
    over the whole campaign, so no simulation can know it on its own.
    """
    from pyflightstream.cases import classify_outputs

    first = records[0]
    pproc_id = first.pproc
    if pproc_id is None:
        return [], {}, {}
    pproc = workspace.resolve_pproc(pproc_id)
    products = pproc.products
    reference_block = first.reference
    description = first.description or ""
    mach = first.mach
    written: list[Path] = []
    sources: dict[str, list[str]] = {}
    points: list[PolarPoint] = []
    exports: dict[str, tuple[Path | None, Path | None, Path | None]] = {}
    plans: dict[str, dict[str, object] | None] = {}
    sim_dir = workspace.sim_dir(sim_id)
    for record in records:
        if not record.outputs:
            continue
        kinds = classify_outputs([Path(o).name for o in record.outputs])
        by_name = {Path(o).name: sim_dir / o for o in record.outputs}
        loads_name = kinds.get("loads")
        if loads_name is None or not by_name[loads_name].is_file():
            continue
        text = by_name[loads_name].read_text(encoding="utf-8", errors="replace")
        try:
            report = parse_loads(text)
        except PyflightstreamError as error:
            raise ProductError(f"{by_name[loads_name]} is not a loads table: {error}") from error
        stem = loads_name[: -len(".txt")]
        points.append(
            PolarPoint(
                name=stem,
                loads=report,
                loads_path=by_name[loads_name],
                point=dict(record.point),
            )
        )
        sloads_path = by_name.get(kinds["sectional_loads"]) if "sectional_loads" in kinds else None
        plots_path = by_name.get(kinds["plots"]) if "plots" in kinds else None
        probes_path = by_name.get(kinds["probes"]) if "probes" in kinds else None
        exports[stem] = (sloads_path, plots_path, probes_path)
        plans.setdefault(stem, record.reductions)
        sources.setdefault(stem, []).append(record.run_id)
    if not points:
        return [], {}, {}
    points.sort(key=lambda point: point.alpha_deg)
    if mach is None:
        raise ProductError(
            f"simulation {sim_id!r} records no Mach number, so its polar table has none"
        )
    if not reference_block or "BREF" not in reference_block:
        raise ProductError(
            f"simulation {sim_id!r} records no reference block with a span (BREF), which the "
            "polar table scales the rolling and yawing moments to; state span_m on the "
            "reference artifact"
        )
    reference = ReferenceValues.from_mapping(reference_block)
    run_ids = [rid for stem in sources for rid in sources[stem]]
    written_names: dict[str, dict[str, object]] = {}
    skipped: dict[str, str] = {}
    #: One entry per group: where its superfile goes and the polar rows it
    #: carries, in the point order of `points` (FR-89).
    super_rows: dict[str, tuple[Path, list[tuple[object, ...]]]] = {}
    #: The plots table written for each point, read back for the superfile.
    plots_tables: dict[str, Path] = {}

    def _target(path: Path) -> Path:
        return _refuse_an_existing_product(path, overwrite=overwrite)

    if products.polars:
        # FR-85: ONE CONVENTION FOR THE WHOLE POINT. The table's rows are
        # the sweep, so the name is the point convention the scripts and
        # the exports already carry with the swept field written `sweep`,
        # and the fields the sweep held FIXED are carried as values. The
        # sweep is measured over the records rather than declared, so a
        # case whose sweep resolved to one point is named for the point
        # it has.
        stated = [point.point or {} for point in points]
        swept = swept_axes(stated)
        fixed: dict[str, float] = {}
        for axis in SWEEP_AXES:
            values = [point[axis] for point in stated if point.get(axis) is not None]
            if values and axis not in swept:
                fixed[axis] = float(values[0])
        ratios = [(point.point or {}).get("advance_ratio") for point in points]
        # FR-89: the SUPERFILE is named for the axis the ROW DECLARES it
        # sweeps, which is the one place its name differs from the polar
        # table's beside it; `declared_sweep` carries the measurement that
        # decided it. The fields it holds fixed follow from that axis and
        # not from the measured one, or a one-point sweep would be named
        # for both at once.
        super_swept = declared_sweep(matrix_row, swept)
        super_fixed: dict[str, float] = {}
        for axis in SWEEP_AXES:
            values = [point[axis] for point in stated if point.get(axis) is not None]
            if values and axis not in super_swept:
                super_fixed[axis] = float(values[0])
        for group, families in pproc.groups.items():
            rows = _polar_rows(
                points, list(families), mach=mach, reference=reference, aliases=first.aliases
            )
            target = _target(
                out
                / POLARS_DIR
                / swept_polar_file_name(sim_id, mach=mach, group=group, point=fixed, swept=swept)
            )
            # ONE ASSEMBLY. The rows the polar table is written from are the
            # rows the superfile carries, so they are built once here and
            # handed to both writers (FR-89).
            full = polar_table_rows(
                polar=sim_id,
                description=description,
                group=str(group),
                reference=reference,
                rows=rows,
                advance_ratios=ratios,
            )
            write_csv_table(target, POLAR_COLUMNS, full)
            if drafts is not None:
                super_rows[str(group)] = (
                    out
                    / POLARS_DIR
                    / super_file_name(
                        sim_id, mach=mach, group=group, point=super_fixed, swept=super_swept
                    ),
                    full,
                )
            written.append(target)
            written_names[target.relative_to(out).as_posix()] = {"runs": run_ids}
            if products.custom_polar_format:
                # PFS-2014.01.01: the same rows, a second time, in the
                # format the author's existing tooling opens, beside the table.
                target = _target(
                    out
                    / POLARS_DIR
                    / swept_polar_file_name(
                        sim_id, mach=mach, group=group, point=fixed, swept=swept, suffix=".dat"
                    )
                )
                write_custom_polar_format(
                    target,
                    polar=sim_id,
                    description=description,
                    group=group,
                    mach=mach,
                    reference=reference,
                    rows=rows,
                )
                written.append(target)
                written_names[target.relative_to(out).as_posix()] = {"runs": run_ids}
    for point in points:
        sloads_path, plots_path, probes_path = exports[point.name]
        if products.sections and sloads_path is not None and sloads_path.is_file():
            target = _target(out / "sections" / f"{point.name}_sections.csv")
            done = write_sections_table(
                target,
                sloads_path.read_text(encoding="utf-8", errors="replace"),
                point=point.name,
                mach=mach,
            )
            if done is not None:
                written.append(done)
                written_names[done.relative_to(out).as_posix()] = {"runs": sources[point.name]}
        # FR-87, the steady half. The probe-points export is the
        # flow-field sample of a point that is not an unsteady history,
        # and it is the ONE export both run types produce, so it is what
        # makes `probes/` mean the same thing on a steady row and an
        # unsteady one. It is gated by no `[products]` key of its own,
        # deliberately: the artifact's `[exports]` table already decides
        # whether a row exports probe points at all, and a second switch
        # over the same fact is a way for the two to disagree.
        if probes_path is not None and probes_path.is_file():
            relative = f"{PROBES_DIR}/{point.name}_probes.csv"
            target = _target(out / relative)
            # A SKIP AND NOT THE SIMULATION'S WHOLE STAGE, which is where
            # this reader differs from the sections and plots readers
            # beside it (PFS-2031.16). Those have read their export since
            # the stage existed, so a file they cannot parse is news; the
            # probe export was collected and never read until 0.16.0, so
            # every workspace already recorded holds files this reader
            # meets for the first time, and letting one of them cost a
            # simulation its polar would be a rename taking a product
            # away.
            try:
                done = write_probes_table(
                    target, probes_path.read_text(encoding="utf-8", errors="replace")
                )
            except ProductError as error:
                skipped[relative] = str(error)
                done = None
            if done is not None:
                written.append(done)
                written_names[done.relative_to(out).as_posix()] = {"runs": sources[point.name]}
        if products.plots and plots_path is not None and plots_path.is_file():
            target = _target(out / PROBES_DIR / f"{point.name}_plots.csv")
            done = write_plots_table(
                target, plots_path.read_text(encoding="utf-8", errors="replace")
            )
            if done is not None:
                written.append(done)
                written_names[done.relative_to(out).as_posix()] = {"runs": sources[point.name]}
                plots_tables[point.name] = done
                _point_reductions(
                    done,
                    plans[point.name],
                    out,
                    runs=sources[point.name],
                    target=_target,
                    written=written,
                    written_names=written_names,
                    skipped=skipped,
                )
    if drafts is not None and super_rows:
        # FR-89, and it happens HERE, after the plots tables of every point
        # of this simulation are on disk: the superfile is written after the
        # unsteady post-process, which is what makes one row per converged
        # point possible at all.
        by_run = {record.run_id: record for record in records}
        last_step: dict[str, Mapping[str, str]] = {}
        for name, table in plots_tables.items():
            _columns, table_rows = read_csv_table(table)
            step = plots_last_row(table_rows)
            if step is not None:
                last_step[name] = step
        for group, (path, full) in super_rows.items():
            wide: list[dict[str, str]] = []
            for point, polar_values in zip(points, full, strict=True):
                run_id = (sources.get(point.name) or [""])[0]
                wide.append(
                    superfile_row(
                        polar_columns=POLAR_COLUMNS,
                        polar_values=polar_values,
                        matrix_row=matrix_row,
                        # NO FALLBACK TO ANOTHER POINT'S RECORD. This read
                        # `by_run.get(run_id, records[0])` until 2026-09-11,
                        # so a run id that did not resolve silently took an
                        # ARBITRARY other point of the same simulation and
                        # wrote ITS flight condition, velocity, density and
                        # rotor speeds into this row. In the one file whose
                        # claim is that it says everything about THAT
                        # simulation, a borrowed value is worse than a
                        # missing one: a reader sees a missing cell and
                        # cannot see a wrong one.
                        #
                        # NOT SHOWN TO BE REACHABLE, and that is stated
                        # rather than left implied. `sources` and `by_run`
                        # are built from the same records in the same loop,
                        # so a run id the first names is one the second
                        # holds. A test that drove this path was written and
                        # DELETED: restoring the fallback left it green, so
                        # it guarded nothing while its name said it did.
                        # The branch is removed as one that would do the
                        # wrong thing silently if it ever became reachable;
                        # what the right thing is, is pinned by
                        # `test_a_point_whose_record_is_missing_borrows_no_other_points_values`.
                        record=by_run.get(run_id),
                        sweep_row=(sweep_rows or {}).get(run_id),
                        plots_row=last_step.get(point.name),
                    )
                )
            drafts.append(
                SuperfileDraft(
                    path=path,
                    rows=tuple(wide),
                    entry={
                        # The same keys `write_campaign_products` stamps on
                        # every other product's entry, written here because
                        # the superfiles are added to the index after that
                        # loop has run (PFS-2031.04 reads `sim_id`).
                        "sim_id": sim_id,
                        "pproc": pproc_id,
                        "runs": [(sources.get(p.name) or [""])[0] for p in points],
                        "group": group,
                    },
                )
            )
    return written, written_names, skipped


def _point_series(
    workspace: CampaignWorkspace,
    sim_id: str,
    record: RunRecord,
    out: Path,
    *,
    overwrite: bool,
) -> tuple[list[Path], dict[str, dict[str, object]]]:
    """Write the series tables of one windowed record (PFS-2031.18.01)."""
    from pyflightstream.cases import classify_outputs

    kinds = classify_outputs([Path(o).name for o in record.outputs])
    loads_name = kinds.get("loads")
    if loads_name is None:
        return [], {}
    stem = loads_name[: -len(".txt")]
    return write_point_series(
        workspace.root,
        sim_dir=workspace.sim_dir(sim_id),
        record=record,
        stem=stem,
        out=out,
        overwrite=overwrite,
    )


#: The characters an alias may carry into a file name. Everything else is
#: replaced, because a rotor's alias is a word the author chose and a file
#: name is a thing the operating system parses.
_SAFE_IN_A_FILE_NAME = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
)


def _a_name_a_file_may_carry(alias: str) -> str:
    """Return ``alias`` reduced to characters a file name may hold (FR-68).

    A ROTOR'S ALIAS IS UNCONSTRAINED by the model: `RotorBlock.alias` is a
    string with no pattern, so a slash, a colon, a star or a trailing dot
    can reach a path, and a slash writes outside the folder the manifest
    keys the file under (the architecture lens, 2026-09-10). This package
    already sanitises an identifier before it becomes a file name, in
    `provenance_file_name` below, and the precedent is followed rather than
    argued with.

    The rotor's OWN spelling is still recorded, in the manifest entry's
    ``rotor`` field, so nothing is lost by the substitution: the file name
    is for the file system and the field is for the reader.
    """
    cleaned = "".join(
        character if character in _SAFE_IN_A_FILE_NAME else "_" for character in alias
    )
    return cleaned.strip("._ ") or "rotor"


def _point_reductions(
    plots_table: Path,
    plan: Mapping[str, object] | None,
    out: Path,
    *,
    runs: list[str],
    target: Callable[[Path], Path],
    written: list[Path],
    written_names: dict[str, dict[str, object]],
    skipped: dict[str, str],
) -> None:
    """Write every applicable reduction of one plots table beside it (PFS-2015.04).

    The plots table is written FIRST and is never touched here: the
    reductions are read off it and land under their own names beside it,
    which is the author's rule of 2026-08-16 (a reduction ships beside the history
    and never in its place) kept by construction. A reduction the record
    cannot window, or whose window reaches past the table, is a skip
    recorded under the file it would have been, with the reason.
    """
    stem = plots_table.name[: -len("_plots.csv")]
    if plan is None:
        skipped[f"{PROBES_DIR}/{stem}_time_average.csv"] = (
            "the run record carries no reduction windows, so no reduction of the plots "
            "table can say which steps it averaged; the record was written before the "
            "field existed or by hand. Rerun the row, and the record will carry the "
            "windows its row states."
        )
        return
    series: TimestepSeries | None = None
    columns: tuple[str, ...] = ()
    # ONE READING LIST, TWO SHAPES (FR-68). A row turning several rotors
    # has no single blade passage, so its two passage reductions live one
    # per ROTOR under `rotors` and land in files that NAME the rotor; the
    # flat keys carry the skip that says where they went, and the products
    # record it as it records any skip. A row turning one rotor, and every
    # row written before 0.15.0, reads the flat keys alone and its files
    # keep the names they have always had.
    reading: list[tuple[str, object, str, str | None]] = [
        (name, plan.get(name), f"{PROBES_DIR}/{stem}_{name}.csv", None) for name in REDUCTION_NAMES
    ]
    rotors = plan.get(ROTORS_KEY)
    if isinstance(rotors, Mapping):
        for alias, block in rotors.items():
            if not isinstance(block, Mapping):
                continue
            safe = _a_name_a_file_may_carry(str(alias))
            for name in PER_ROTOR_REDUCTIONS:
                reading.append(
                    (
                        name,
                        block.get(name),
                        f"{PROBES_DIR}/{stem}_{name}_{safe}.csv",
                        str(alias),
                    )
                )
    # THE FLAT SKIP NAMES THE FILES, because this layer knows the stem and
    # the cases layer does not. Its own sentence can only describe the
    # SHAPE of the names; read by someone who has just opened the plots
    # folder and not found their per-blade table, that is one inference
    # away from the two files sitting in the folder they are looking at
    # (the interface lens, 2026-09-10).
    per_rotor: dict[str, list[str]] = {}
    for name, _entry, relative, rotor in reading:
        if rotor is not None:
            per_rotor.setdefault(name, []).append(relative)
    for name, entry, relative, rotor in reading:
        if not isinstance(entry, Mapping):
            continue  # not applicable to this run type
        if "skipped" in entry:
            reason = str(entry["skipped"])
            if rotor is None and per_rotor.get(name):
                reason = (
                    f"{reason.rsplit(':', 1)[0]}: this row names its rotors, so each is "
                    f"reduced over its own blade passage, in "
                    f"{' and '.join(per_rotor[name])}."
                )
            skipped[relative] = reason
            continue
        stated = entry.get("windows", ())
        windows = [tuple(int(v) for v in window) for window in stated]  # type: ignore[union-attr]
        if series is None:
            columns, series = plots_table_series(plots_table)
        destination = target(out / relative)
        try:
            done = write_reduction_table(
                destination, series, columns, reduction=name, windows=windows
            )
        except ProductError as error:
            skipped[relative] = str(error)
            continue
        written.append(done)
        record: dict[str, object] = {
            "runs": runs,
            "reduction": name,
            "windows": [list(window) for window in windows],
            "window_from": entry.get("window_from"),
        }
        if "period_steps" in entry:
            record["period_steps"] = entry["period_steps"]
        if rotor is not None:
            # THE ROTOR AS A FIELD, not only as a piece of a file name. The
            # name is `{stem}_{reduction}_{alias}` and both the reduction
            # and the alias carry underscores, so it does not decompose: a
            # reader holding `a-02.0_per_blade_LIFT_L1.csv` could not say
            # which rotor it is without already knowing the alias set (the
            # interface lens, 2026-09-10).
            record["rotor"] = rotor
        written_names[relative] = record


# --- PFS-2012.08.01: a run's provenance in an interchange format, PROV-JSON --------

#: The folder under the matrix's products where the documents land.
PROVENANCE_DIR = "provenance"

#: The suffix of one document, appended to the point's own name, or to
#: the run id with its separators replaced where the point's name is not
#: known or is not unique (FR-86).
PROVENANCE_SUFFIX = ".prov.json"

#: The namespaces a document declares. ``prov`` and ``xsd`` are the W3C's;
#: ``pyfs`` is this package's, for the attributes and identifiers it coins,
#: a URN rather than a web address so the document promises no page.
_PROV_PREFIX = {
    "prov": "http://www.w3.org/ns/prov#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "pyfs": "urn:pyflightstream:",
}


#: The extension every generated point script is written under
#: (``run._run_point``: ``write_script(sim_id, f"{stem}.txt", ...)``), and
#: therefore the one this module strips to recover a point's own name
#: from the script the record already names. Stripped by this exact
#: literal rather than by `Path.stem`, because a point stem carries dots
#: of its own: `Path("a+02.0").stem` is `a+02`, and a name shortened that
#: way would collide two points of one sweep.
_SCRIPT_SUFFIX = ".txt"


def point_name_of(record: RunRecord) -> str | None:
    """Return the point name a record's script carries, or None (FR-86).

    THE SCRIPT IS THE SOURCE and not the naming template. The template a
    workspace is configured with today is not the one a record from last
    month was written under; the record names the file the run actually
    wrote, and that file's stem IS the convention every other generated
    file of the point carries. A record whose script is not named the way
    this package writes one answers None, and the caller keeps the run
    id, which is what every document was named before 0.16.0.
    """
    declared = record.script_path
    if not declared:
        return None
    name = str(declared).replace("\\", "/").rsplit("/", 1)[-1]
    if not name.endswith(_SCRIPT_SUFFIX):
        return None
    return name[: -len(_SCRIPT_SUFFIX)] or None


def provenance_file_name(run_id: str, *, point_name: str | None = None) -> str:
    """Return the name of one run's provenance document (FR-86).

    ``<point name>.prov.json`` when the point's own name is known, which
    is the convention the script and every export of the same point carry
    and what lets a reader sort ``scripts/`` and ``provenance/`` side by
    side. ``<run id with '/' replaced by '_'>.prov.json`` otherwise, which
    is what every document was named before 0.16.0.

    NOTHING RENAMES A RUN. The run id is unchanged: it keys the products
    manifest and it is a field inside the document, under
    ``pyfs:run_id``, and it is the identifier of the activity. What moves
    is a file name, which this package never parses for meaning.
    """
    stem = run_id if point_name is None else point_name
    return stem.replace("/", "_") + PROVENANCE_SUFFIX


def _attributes(**pairs: object) -> dict[str, object]:
    """Return the attributes of one PROV node, a None value left out rather than written."""
    return {name: value for name, value in pairs.items() if value is not None}


def _prov_document(record: RunRecord, sim_dir: Path) -> dict[str, object]:
    """Build one run's PROV-JSON document from its record and the files it left.

    W3C PROV, in the PROV-JSON serialization (the author's decision of 2026-09-08,
    design 68): the run record carried every fact a provenance document
    needs and lacked a shape another tool reads without reading this
    package's docs. ENTITIES are each staged input (``inputs_sha256``), the
    script (``script_sha256``) and each collected output, every one with
    its sha256 under ``pyfs:sha256``; an output's hash is computed from
    the file when it is still there and taken from the record otherwise,
    and ``pyfs:sha256_from`` says which. The ACTIVITY is the solver run,
    with ``prov:startTime`` and ``prov:endTime`` where the record carries
    them, the wall time, the status and the executor's argv. The AGENTS
    are the package at its version and commit and the solver build at its
    executable identity, both ``prov:SoftwareAgent``. The activity
    ``used`` the inputs and the script, every output ``wasGeneratedBy``
    it, it ``wasAssociatedWith`` both agents, the outputs are attributed
    to the solver and the script to the package. Standard library only:
    the document is a mapping :mod:`json` writes.
    """
    activity_id = f"pyfs:run/{record.run_id}"
    package_id = f"pyfs:package/pyflightstream/{record.package_version}"
    solver_id = f"pyfs:solver/FlightStream/{record.fs_version_requested}"
    entities: dict[str, dict[str, object]] = {}
    used: dict[str, dict[str, str]] = {}
    generated: dict[str, dict[str, str]] = {}
    attributed: dict[str, dict[str, str]] = {}
    for name, input_sha256 in sorted(record.inputs_sha256.items()):
        entity_id = f"pyfs:input/{name}"
        entities[entity_id] = _attributes(
            **{"prov:type": "pyfs:StagedInput", "pyfs:name": name, "pyfs:sha256": input_sha256}
        )
        used[f"_:used{len(used) + 1}"] = {"prov:activity": activity_id, "prov:entity": entity_id}
    script_id = f"pyfs:script/{record.script_path or 'script'}"
    entities[script_id] = _attributes(
        **{
            "prov:type": "pyfs:Script",
            "pyfs:name": record.script_path,
            "pyfs:sha256": record.script_sha256,
            "pyfs:raw": record.raw_flag,
            "pyfs:recipe": record.recipe,
            "pyfs:recipe_sha256": record.recipe_sha256,
        }
    )
    used[f"_:used{len(used) + 1}"] = {"prov:activity": activity_id, "prov:entity": script_id}
    attributed["_:attributed1"] = {"prov:entity": script_id, "prov:agent": package_id}
    for name in record.outputs:
        entity_id = f"pyfs:output/{name}"
        path = sim_dir / name
        if path.is_file():
            output_sha256: str | None = file_sha256(path)
            sha256_from: str | None = "file"
        else:
            output_sha256 = record.outputs_sha256.get(name)
            sha256_from = "record" if output_sha256 is not None else None
        entities[entity_id] = _attributes(
            **{
                "prov:type": "pyfs:Output",
                "pyfs:name": name,
                "pyfs:sha256": output_sha256,
                "pyfs:sha256_from": sha256_from,
            }
        )
        generated[f"_:generated{len(generated) + 1}"] = {
            "prov:entity": entity_id,
            "prov:activity": activity_id,
        }
        attributed[f"_:attributed{len(attributed) + 1}"] = {
            "prov:entity": entity_id,
            "prov:agent": solver_id,
        }
    executor = record.executor
    activity = _attributes(
        **{
            "prov:type": "pyfs:SolverRun",
            "prov:startTime": record.started_at,
            "prov:endTime": record.finished_at,
            "pyfs:run_id": record.run_id,
            "pyfs:sim_id": record.sim_id,
            "pyfs:status": record.status.value,
            "pyfs:wall_time_s": record.wall_time_s,
            "pyfs:iterations": record.iterations,
            "pyfs:residual": record.residual,
            "pyfs:executor": executor["class_name"] if executor else None,
            "pyfs:argv": list(executor["argv"]) if executor else None,
            "pyfs:cwd": record.cwd,
            "pyfs:error": record.error,
            # PFS-2033.02: the setup's raw commands the script carried, or nothing.
            "pyfs:raw_commands": [entry.model_dump(mode="json") for entry in record.raw_commands]
            or None,
            # The author's decision of 2026-09-09: the setup's aliases the polar tables resolved by.
            "pyfs:aliases": dict(record.aliases) or None,
        }
    )
    agents = {
        package_id: _attributes(
            **{
                "prov:type": "prov:SoftwareAgent",
                "pyfs:name": "pyflightstream",
                "pyfs:version": record.package_version,
                "pyfs:commit": record.package_commit,
                "pyfs:dirty": record.package_dirty,
            }
        ),
        solver_id: _attributes(
            **{
                "prov:type": "prov:SoftwareAgent",
                "pyfs:name": "FlightStream",
                "pyfs:version_requested": record.fs_version_requested,
                "pyfs:version_reported": record.fs_version_reported,
                "pyfs:build": record.fs_build,
                "pyfs:executable": record.fs_exe,
                "pyfs:executable_sha256": record.fs_exe_sha256,
            }
        ),
    }
    document: dict[str, object] = {
        "prefix": dict(_PROV_PREFIX),
        "entity": entities,
        "activity": {activity_id: activity},
        "agent": agents,
        "used": used,
        "wasAssociatedWith": {
            f"_:associated{number}": {"prov:activity": activity_id, "prov:agent": agent_id}
            for number, agent_id in enumerate(agents, start=1)
        },
        "wasAttributedTo": attributed,
    }
    # As applicable: a run that collected nothing generated nothing, and the
    # key is absent rather than empty.
    if generated:
        document["wasGeneratedBy"] = generated
    return document


def _run_provenance(
    workspace: CampaignWorkspace, records: Sequence[RunRecord], out: Path, *, overwrite: bool
) -> dict[str, str]:
    """Write one PROV-JSON document per record under ``out/provenance``.

    Every recorded run, whatever its status: a failed run's provenance is
    evidence about the failure. Returns the manifest's ``provenance`` map,
    run id to the document's path relative to ``out``. An existing document
    is refused as an existing table is, unless ``overwrite`` is set.
    """
    # A POINT NAME NEED NOT BE UNIQUE AND A RUN ID IS (FR-86). The
    # default naming template is `{point}`, which carries no sim id, so
    # two simulations of one matrix swept over the same angles render the
    # same stem; so do two records of one point. Naming the document
    # after the point alone would then have had the second run's
    # provenance OVERWRITE the first's and the manifest name one file for
    # two runs, which is the class of defect this whole stage exists to
    # make impossible. Measured over the whole set first and then
    # applied, so the fallback does not depend on manifest order: a stem
    # claimed more than once sends EVERY record that claims it back to
    # the run id, which is unique by construction.
    stems = {record.run_id: point_name_of(record) for record in records}
    claims = Counter(stem for stem in stems.values() if stem is not None)
    index: dict[str, str] = {}
    for record in records:
        stem = stems[record.run_id]
        if stem is not None and claims[stem] > 1:
            stem = None
        relative = f"{PROVENANCE_DIR}/{provenance_file_name(record.run_id, point_name=stem)}"
        target = out / relative
        if target.exists() and not overwrite:
            raise ProductExistsError(
                f"the provenance document {target} exists; pass overwrite (CLI: --overwrite) "
                "to rewrite it from the manifest"
            )
        document = _prov_document(record, workspace.sim_dir(record.sim_id))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8")
        index[record.run_id] = relative
    return index


def write_campaign_products(
    workspace: CampaignWorkspace, *, overwrite: bool = False, matrix_stem: str | None = None
) -> list[Path]:
    """Write the products of the simulations in a workspace's manifest.

    PFS-2029.15.03. Reads the manifest alone: each successful record names
    its collected exports, its pproc artifact, its description, its Mach and
    its reference block, so the products are rebuilt with no executable
    configured. ``products.json`` beside them names every file written
    with the run ids it derives from. An existing product is refused
    unless ``overwrite`` is set; the run itself passes it, since a product
    is derived and a resume rewrites it with the new points.

    Beside the tables, one PROV-JSON document per recorded run, every
    status, under ``provenance/`` (PFS-2012.08.01), named in
    ``products.json`` under ``provenance`` keyed by run id; the documents
    are not in the returned list, which is the tables, and the manifest is
    where they are found.

    Where they land is the matrix's own folder (PFS-2031.04): with
    ``matrix_stem`` given, the records naming that matrix stem are written under
    ``post/<matrix stem>/``, so several matrices of one workspace keep their
    own; with it None, every record that names no matrix is written under
    ``post/products``, the historical place of a campaign authored in
    Python.

    Since 0.16.0 it also writes the SUPERFILE of every polar and group
    (FR-89), under ``polars/`` beside the polar table, and the measurement
    of what it wrote under ``reports/`` beside ``post/``. Both come last,
    after the plots tables of every point are on disk, because a superfile
    carries the unsteady post-process's own parameters and one row per
    converged point.
    """
    everything = workspace.read_manifest()
    records = [record for record in everything if record.matrix_stem == matrix_stem]
    if matrix_stem is not None and not records:
        # The same refusal sweep_table gives the same keyword (PFS-2031.04):
        # a stem the manifest never recorded is a typo or a matrix not yet
        # run, and an empty product folder would say neither.
        stems = sorted({r.matrix_stem for r in everything if r.matrix_stem})
        raise ProductError(
            f"the manifest of {workspace.root} holds no record of matrix {matrix_stem!r}; the "
            f"matrices it names are {', '.join(stems) if stems else 'none'}. Run that matrix "
            "first, or name one of those."
        )
    out = workspace.products_dir(matrix_stem)
    by_sim: dict[str, list[RunRecord]] = {}
    for record in records:
        if record.status in (RunStatus.CONVERGED, RunStatus.COMPLETED_MAX_ITER):
            by_sim.setdefault(record.sim_id, []).append(record)
    written: list[Path] = []
    products_index: dict[str, dict[str, object]] = {}
    manifest: dict[str, object] = {"products": products_index}
    # PFS-2031.16. A simulation whose product is REFUSED by design, the
    # polar under sideslip among them, is recorded as skipped with the
    # reason, and the others are written: until 2026-09-08 the first
    # refusal aborted the stage, and a sideslip row cost every later row
    # of its matrix its tables and the workspace its products.json. An
    # existing product without overwrite is still the whole stage's
    # refusal, since it is about the caller's flag and not about a row.
    skipped: dict[str, str] = {}
    # FR-89, gathered ONCE for the whole campaign and never per simulation:
    # the rows of the matrix this campaign came from, keyed by POL, and the
    # campaign sweep table's own rows keyed by run id. The sweep table is
    # the frame `campaign_sweep.csv` is written from, so the superfile
    # carries what that file holds by carrying the same row rather than by
    # assembling one that looks like it.
    rows_of_the_matrix = matrix_rows(workspace.root, matrix_stem)
    sweep_rows = _sweep_rows(workspace, matrix_stem)
    drafts: list[SuperfileDraft] = []
    for sim_id, sim_records in by_sim.items():
        # PFS-2031.18.01: the per-step exports of a windowed point as a
        # series, written before the polar so a simulation the polar
        # refuses (no Mach, a sideslip) keeps its series, which rest on
        # the stamped files and the record alone.
        # A stamped file the parsers cannot read (a run stopped mid-window
        # leaves one) is that point's skip, recorded under series/<run id>,
        # and never the stage's abort: the same rule the polar below follows
        # since 2026-09-08 (the V&V lens of REL-0140).
        for record in sim_records:
            if not record.export_window:
                continue
            try:
                series_files, series_names = _point_series(
                    workspace, sim_id, record, out, overwrite=overwrite
                )
            except ProductExistsError:
                raise
            except ProductError as error:
                skipped[f"series/{record.run_id}"] = str(error)
                warnings.warn(
                    f"series of {record.run_id} not written: {error}",
                    PyflightstreamWarning,
                    stacklevel=2,
                )
                continue
            written.extend(series_files)
            for name, entry in series_names.items():
                products_index[name] = {"sim_id": sim_id, "pproc": record.pproc, **entry}
        try:
            files, names, reductions_skipped = _sim_products(
                workspace,
                sim_id,
                sim_records,
                out,
                overwrite=overwrite,
                matrix_row=rows_of_the_matrix.get(sim_id),
                sweep_rows=sweep_rows,
                drafts=drafts,
            )
        except ProductExistsError:
            raise
        except ProductError as error:
            skipped[sim_id] = str(error)
            warnings.warn(
                f"products of simulation {sim_id} not written: {error}",
                PyflightstreamWarning,
                stacklevel=2,
            )
            continue
        written.extend(files)
        for name, entry in names.items():
            products_index[name] = {
                "sim_id": sim_id,
                "pproc": sim_records[0].pproc,
                **entry,
            }
        # A reduction the row could not window is a skip under the file it
        # would have been (PFS-2015.04), beside the simulations refused whole.
        skipped.update(reductions_skipped)
    # FR-89: the superfiles LAST, and all of them together. Their header is
    # the union over every draft of this campaign, so a steady polar's file
    # and a rotor's carry the same columns and a reader cannot tell from the
    # file which kind of run is behind a row.
    if drafts:
        super_files, super_entries, super_columns = write_superfiles(
            drafts,
            target=lambda path: _refuse_an_existing_product(path, overwrite=overwrite),
        )
        written.extend(super_files)
        for path, entry in super_entries.items():
            products_index[path.relative_to(out).as_posix()] = entry
        # THE MEASUREMENT, and the union in it is built from the WORKSPACE
        # and not from the columns just written: a report whose `known` were
        # the file's own columns would pass a superset test by construction,
        # which is a check that accepts everything.
        known = union_the_workspace_knows(
            workspace.root,
            out,
            matrix_stem,
            polars_dir=POLARS_DIR,
            probes_dir=PROBES_DIR,
        )
        import pyflightstream

        report = write_superfile_report(
            workspace.root,
            version=pyflightstream.__version__,
            files=[
                (path, super_columns, len(draft.rows))
                for path, draft in zip(super_files, drafts, strict=True)
            ],
            known=known,
        )
        manifest["superfile_report"] = report.relative_to(workspace.root).as_posix()
    # Always present, empty when nothing was refused, so a wrapper reads one
    # key rather than testing for it (review round two of 2026-09-08).
    manifest["skipped"] = skipped
    # PFS-2012.08.01: one document per recorded run, whatever its status.
    manifest["provenance"] = _run_provenance(workspace, records, out, overwrite=overwrite)
    if written or skipped or records:
        out.mkdir(parents=True, exist_ok=True)
        (out / PRODUCTS_MANIFEST).write_text(
            json.dumps(manifest, indent=1) + "\n", encoding="utf-8"
        )
    return written
