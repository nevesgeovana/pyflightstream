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
  text file the existing tooling opens, specified line by line in
  :func:`write_custom_polar_format` and read back by
  :func:`read_custom_polar_format`;
* a PROVENANCE document per recorded run, under ``provenance/`` and
  named by the point's own convention since 0.16.0 (FR-86)
  (PFS-2012.08.01): W3C PROV in its PROV-JSON serialization, the staged
  inputs, the script and the outputs as entities with their sha256, the
  solver run as the activity with its start, end and argv, the package
  and the solver build as agents.

THE ARITHMETIC IS THE REFERENCE ONE, re-derived here from the recorded files and
never imported. FlightStream's ``CL``, ``CDi + CDo`` and ``Cy`` are the
STABILITY-axis force coefficients and the body-axis forces follow by
turning them through the angle of attack; the solver's ``CMx`` and ``CMz``
are the BODY-axis rolling and yawing moments, scaled from the chord to the
span and, by the reference sign convention, negated, and the stability-axis moments
follow by turning them through the angle of attack. The reference polars carried
``BETA 0.0`` on every row, so the wind axes coincide with the stability
axes in every table this writer has been checked against; a point with a
non-zero sideslip is REFUSED naming the point, because the wind-axis turn
through sideslip has been checked against nothing. Values are written at
five decimals, the reference precision, so a table regenerated from the same exports
is equal text. The evidence is the products arm of GOAL-011,
``python GeoversePlan/goals/check_goal_011.py --products``, which
regenerates the 27 recorded polars and 5 section tables through
:func:`write_recorded_polar` and compares them with the reference tables
converted to this shape outside the package: 32 of 32 equal on 2026-09-03.
"""

from __future__ import annotations

import csv
import json
import math
import re
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
    CONFIGURATION_VARIABLE,
    PER_ROTOR_REDUCTIONS,
    PROBE_POSITION_COLUMNS,
    REDUCTION_NAMES,
    ROTORS_KEY,
)
from pyflightstream.fsi.loads import SectionalLoadsReport, parse_sectional_loads
from pyflightstream.post._tables import (
    _COEFFICIENT_PLOT_PREFIXES,
    _DECIMALS,
    ADVANCE_RATIO_COLUMN,
    CONTEXT_COLUMNS,
    FLIGHT_CONDITION_COLUMNS,
    NOT_APPLICABLE,
    REFERENCE_LENGTH_COLUMNS,
    SECTION_COLUMNS,
    ProductError,
    ProductExistsError,
    context_row,
    write_csv_table,
)
from pyflightstream.post.series import run_clock, write_point_series
from pyflightstream.post.superfile import (
    SuperfileDraft,
    matrix_rows,
    measure_sections,
    plots_last_row,
    super_file_name,
    superfile_row,
    union_the_workspace_knows,
    write_sections_report,
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
from pyflightstream.workspace.naming import ARCHIVE_DIR, ARCHIVE_STAMP, sweep_file_stem

if TYPE_CHECKING:
    from pyflightstream.cases.matrix import MatrixRow
    from pyflightstream.workspace import CampaignWorkspace, RunRecord

__all__ = [
    "ADVANCE_RATIO_COLUMN",
    "COEFFICIENT_COLUMNS",
    # The condition and length tuples every product family composes. They live
    # in `post._tables` because three modules share them and the sharer cannot
    # sit in the module that imports it; they are re-exported here because that
    # is where a reader finds every public name of that module, and the tier-1
    # test of that claim is what caught their absence the minute they moved.
    "CONTEXT_COLUMNS",
    "FLIGHT_CONDITION_COLUMNS",
    "REFERENCE_LENGTH_COLUMNS",
    "context_row",
    # The token a reader of any product compares against. It was reachable
    # only from the private `_tables` until 0.23.0, while that module's own
    # docstring said this one re-exports every public name it holds -- so the
    # sentence was false, and a test that wanted the constant had to import
    # the private module to get it.
    "NOT_APPLICABLE",
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

#: WHY THE ADVANCE RATIO HAS A COLUMN AT ALL (FR-85), kept here beside its one
#: user although the constant itself moved to `post._tables` at 0.23.0, where
#: three modules can compose it. Measured on the reference ``0001_M15_g01.csv``,
#: written by 0.15.0 for a three-value sweep of the advance ratio: the three
#: rows carried identical ``ALPHA``, ``BETA``, ``MACH`` and ``RE`` and no column
#: naming what was swept, so the only thing distinguishing the first row from
#: the third was its POSITION in the file. A table whose rows are told apart by
#: order is not a table.

#: What the POLAR adds beside the twenty-four, which already carry `ALPHA`,
#: `BETA`, `MACH` and `RE`.
#:
#: WHY THESE THREE SIT OUTSIDE THE TWENTY-FOUR and may never move inside:
#: :data:`COEFFICIENT_COLUMNS` IS the custom format's own line 9 and a fixture
#: pins it line by line, so a flight-condition column added there changes a
#: file format that was specified byte by byte. `J` was already outside for
#: exactly this reason; `VINF` and `ALT` join it rather than it.
_POLAR_CONDITION_COLUMNS: tuple[str, ...] = ("VINF", "ALT", ADVANCE_RATIO_COLUMN)

#: A polar table's columns: the polar, its description, the group, the
#: reference block, the condition the twenty-four do not carry, the
#: twenty-four coefficients.
POLAR_COLUMNS: tuple[str, ...] = (
    "POLAR",
    "DESCRIPTION",
    "GROUP",
    *_REFERENCE_COLUMNS,
    *_POLAR_CONDITION_COLUMNS,
    *COEFFICIENT_COLUMNS,
)


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


@dataclass(frozen=True)
class GroupCoefficients:
    """The coefficients of one group, summed over its families, as the solver reports them.

    ``lift``, ``drag`` and ``side`` are the STABILITY-axis forces; ``roll``,
    ``pitch`` and ``yaw`` are the BODY-axis moments, ``roll`` and ``yaw``
    already scaled from the chord to the span and carrying the reference sign. That
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


def _stated_iteration(export_text: str) -> int | None:
    """Return the solver iteration an export states, or None where it states none.

    Both the loads and the surface sections exports carry `Current solver
    iteration number` in their header. A steady export written before the
    solver stamped it carries none, and that is `NA` rather than a guess.
    """
    try:
        return int(float(labeled_value(export_text, "Current solver iteration number:")))
    except (MalformedOutputError, ValueError):
        return None


def _advance_ratio_of(point: PolarPoint) -> float | None:
    """Return the point's advance ratio, or None where the run recorded none.

    None and not zero: zero is a value a rotor row can HAVE, and "not recorded"
    is not it. The funnel writes `NA` for the None, which says the column does
    not apply to this row rather than that the rotor was stopped.
    """
    stated = (point.point or {}).get("advance_ratio")
    return float(stated) if isinstance(stated, int | float) else None


def point_condition(
    point: PolarPoint,
    *,
    mach: float,
    cell: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Return the flight condition ONE product row states.

    Item 5: every file the post stage writes says what it is a file OF, which
    means the condition has to reach the row rather than only the header. The
    columns existed from the first commit of this release and the values did
    not; a release round measured `VINF` and `ALT` reading `NA` in every row of
    every polar and super file.

    THE REPORTED CONDITION WINS OVER THE REQUESTED ONE. Two sources exist per
    point and they are not equivalent: ``cell`` is the matrix row, what was
    ASKED for, and ``point.loads`` is the export header, what the solver SAYS it
    ran at. A file that says what it is a file of must carry the second, because
    the two differ exactly when something went wrong -- which is the case a
    reader most needs to see, and the one a product silently stating the request
    would hide.

    The winner is chosen HERE and not by dictionary insertion order: each
    reported value replaces every other spelling of its column before it is
    written, so a swept ``alpha`` cannot outrank the ``ALPHA`` the run reports
    because it happened to be inserted first.

    Parameters
    ----------
    point : PolarPoint
        The point, carrying its loads report and the sweep point it was asked
        for.
    mach : float
        The row's Mach number, which no export header states.
    cell : mapping, optional
        The matrix row's flight condition, for the keys no export reports --
        the altitude among them.

    Returns
    -------
    dict
        Keys in the spellings :func:`pyflightstream.post._tables.context_row`
        resolves, which is the column's own name or one of its recorded aliases.
    """
    condition: dict[str, object] = {}
    for source in (cell or {}, point.point or {}):
        condition.update(source)

    report = point.loads
    if report is not None:
        reported: tuple[tuple[str, object | None], ...] = (
            ("ALPHA", report.angle_of_attack_deg),
            ("BETA", report.sideslip_deg),
            ("VINF", report.freestream_velocity_m_s),
            ("RE", report.reynolds),
        )
        for column, value in reported:
            if value is None:
                continue
            for spelling in [key for key in condition if str(key).casefold() == column.casefold()]:
                del condition[spelling]
            condition[column] = value

    condition.setdefault("MACH", mach)
    return condition


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
    the table does not carry is left out, as the reference writer left it out; a
    group none of whose families is in the table sums to zero, which is
    what the reference products carry for the rotor groups of a wing-body
    polar. The rolling and yawing moments are the solver's ``CMx`` and
    ``CMz``, scaled from the reference chord to the span and negated,
    the standard convention.

    ``empty_is_every`` is what an EMPTY member list means, and it is
    False here on purpose (the interface lens of 2026-09-09). The reference
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

    The reference polars carried ``BETA 0.0`` on every row, so the wind axes coincide
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
    name: str,
    group: str | int,
    suffix: str = ".csv",
) -> str:
    """``P<sim>-<name>_g<group:02d>.csv`` (FR-85, 0.21.0).

    ``name`` is the recorded sweep name, each swept field written
    ``<code>+sweep``, for a table over a sweep
    (``P0001-M150AL+000BE+000J+sweep_g01.csv``), and the recorded point name for
    a case whose sweep resolved to one point. The ``.dat`` of the custom format
    takes the same stem, which is what ``suffix`` is for.
    """
    return f"{sweep_file_stem(sim, name)}_g{int(group):02d}{suffix}"


#: A group name that reads as the NUMBERED era's suffix, which the rename must
#: be able to tell apart from a name of its own.
_NUMBERED_GROUP = re.compile(r"^g\d+$", re.IGNORECASE)


#: The six coefficients a rotor table carries, in the order the owner named
#: them on 2026-09-17: "J, CT, CQ, CP, ETA, ETAW (eficiência no eixo do
#: vento) para cada rotor".
ROTOR_COEFFICIENT_COLUMNS: tuple[str, ...] = ("J", "CT", "CQ", "CP", "ETA", "ETAW")


def rotor_table_alias_line(alias: str) -> str:
    """Return the first line of a rotor table: the rotor's alias, alone.

    v0.23.0 item 18, the owner's rule of 2026-09-17: the alias is written on the
    first line "para saber qual grupo e' aquele quando tiver sido carregado por
    script".

    WHY THE FILE NAME IS NOT ENOUGH, which is the whole reason this exists. A
    script that has already LOADED the file no longer has its name: it holds an
    array of numbers. The alias has to be inside the bytes.

    ALONE ON THE LINE, with no label and no separator. A line carrying a label
    and the alias makes every reader strip a prefix, and a prefix is the kind
    of thing that gets spelled two ways within a year -- which is the defect
    this release spent a round removing from the `NA` token.
    """
    token = str(alias).strip()
    if not token:
        raise ProductError(
            "a rotor table's first line is its rotor's alias, and none was given; a "
            "first line that names nobody is worse than no first line"
        )
    if "\n" in token or "\r" in token:
        raise ProductError(
            f"the rotor alias {alias!r} spans more than one line, and the first LINE is "
            "the unit a reader takes; an alias carrying a newline breaks the file's shape"
        )
    return token + "\n"


def rotor_coefficient_columns(alias: str) -> tuple[str, ...]:
    """Return the rotor coefficient columns of ONE rotor, suffixed with its alias.

    Her constraint, and it is physical rather than cosmetic: "esses coefs fazem
    sentido físico apenas para um rotor, não vários juntos". Two rotors summed
    into one CT is not a worse CT, it is not a CT at all -- the diameters and
    the speeds that normalise it are different numbers. The alias in every
    column name is what makes summing them impossible by accident.
    """
    token = str(alias).strip()
    if not token:
        raise ProductError("a rotor coefficient column needs the rotor's alias to carry")
    return tuple(f"{name}_{token}" for name in ROTOR_COEFFICIENT_COLUMNS)


def rotor_coefficients(
    *,
    thrust_n: float,
    torque_nm: float,
    rps: float,
    diameter_m: float,
    density_kg_m3: float,
    speed_m_s: float,
    shaft_angle_deg: float = 0.0,
) -> dict[str, float | str]:
    """Return the six standard coefficients of one rotor.

    THE DEFINITIONS, written here because a coefficient whose formula lives
    only in code is a number nobody can check. ``n`` is revolutions per SECOND
    and ``D`` the diameter::

        J    = V / (n D)
        CT   = T / (rho n^2 D^4)
        CQ   = Q / (rho n^2 D^5)
        CP   = 2 pi CQ
        ETA  = J CT / CP
        ETAW = ETA cos(theta)

    ``shaft_angle_deg`` is the angle between the rotor's SHAFT and the free
    stream, which is why this rests on item 19: until the installation vector
    existed the shaft was assumed to lie on a geometry axis, so a rotor
    installed at pitch reported the wind-axis efficiency of an aligned rotor.
    A rotor tilted out of the flight direction does not put all of its thrust
    into going forward, and `ETAW` is the half that does.

    ETA AND ETAW ARE `NA` ON A STATIC POINT. At V = 0 both are 0/0: the rotor
    produces thrust and absorbs torque and no useful propulsive power, so any
    number there is an artifact of the algebra rather than a measurement. `CT`
    and `CQ` are still real and still written. The static measure is a figure
    of merit, which by the owner's decision of 2026-09-17 the package does not
    choose: "o usuário define uma se ele for rodar estático".

    THE DEFINITION OF `ETAW` IS A DOMAIN CALL AND IS FLAGGED AS ONE. It is
    implemented as the thrust component along the free stream, which is the
    standard reading of "eficiência no eixo do vento", and it is the owner's to
    confirm or correct before the release is tagged.

    Raises
    ------
    ZeroDivisionError
        If the rotor is not turning. Every coefficient divides by the square of
        the speed, and a rotor at zero rev/min has no coefficients rather than
        infinite ones.
    """
    if rps == 0:
        raise ZeroDivisionError(
            "the rotor is not turning, so it has no thrust or torque coefficient: "
            "every one of them divides by the square of its speed"
        )
    advance_ratio = speed_m_s / (rps * diameter_m)
    thrust_coefficient = thrust_n / (density_kg_m3 * rps**2 * diameter_m**4)
    torque_coefficient = torque_nm / (density_kg_m3 * rps**2 * diameter_m**5)
    power_coefficient = 2.0 * math.pi * torque_coefficient
    values: dict[str, float | str] = {
        "J": advance_ratio,
        "CT": thrust_coefficient,
        "CQ": torque_coefficient,
        "CP": power_coefficient,
    }
    if speed_m_s == 0 or power_coefficient == 0:
        values["ETA"] = NOT_APPLICABLE
        values["ETAW"] = NOT_APPLICABLE
        return values
    efficiency = advance_ratio * thrust_coefficient / power_coefficient
    values["ETA"] = efficiency
    values["ETAW"] = efficiency * math.cos(math.radians(shaft_angle_deg))
    return values


def group_product_name(*, polar: str, mach: float, group: str, suffix: str = ".csv") -> str:
    """Return the product file name of one polar GROUP, carrying the group's NAME.

    Item 14 of 0.23.0, on the owner's rule that `GROUPS` takes one named input
    and "no nome do arquivo vai vir o nome desse input e não um numero". A
    number told a reader which position the group held in a list, which is a
    fact about the list and not about the group.

    A group whose name IS the old numbered suffix is refused. It would produce
    a file indistinguishable from the pre-0.23.0 form, and the rename that
    moves her existing products has to be able to tell the two eras apart to
    know what it has already moved.
    """
    token = str(group).strip()
    if not token:
        raise ProductError("a polar group has no name, and the product file is named after it")
    if _NUMBERED_GROUP.match(token):
        raise ProductError(
            f"the polar group is named {token!r}, which is the shape this release "
            "replaced; a file named after it could not be told from the numbered "
            "form it supersedes, and the rename of existing products needs that "
            "difference. Choose a name for the group"
        )
    return f"{polar}-M{_mach_code(mach):02d}_{token}{suffix}"


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
    conditions: Sequence[Mapping[str, object]] | None = None,
) -> list[tuple[object, ...]]:
    """Assemble the rows of one polar table, each under :data:`POLAR_COLUMNS`.

    ``conditions`` is the flight condition of each row, in the row order, for
    the columns the twenty-four coefficients do NOT carry: ``VINF``, ``ALT``
    and the advance ratio. A key a run did not record arrives as ``NA`` rather
    than as a blank or a zero. ``advance_ratios`` remains accepted and means
    the same as a ``conditions`` sequence carrying only ``J``; giving both is
    refused rather than silently preferring one, because a caller that states
    the ratio twice has two sources for it and this function cannot know which
    is current.

    ONE ASSEMBLY, TWO CONSUMERS, and that is why it is a function of its
    own rather than three lines inside the writer below. The superfile of
    FR-89 carries every column the polar table has, so it needs the same
    values the table is written from; building them a second time beside
    this one is exactly the shape that broke `legacy_products.py` on
    2026-09-10, where a column inserted in one assembly reached the other
    as a value under its neighbour's name.
    """
    if advance_ratios is not None and conditions is not None:
        raise ProductError(
            "the polar table was given both advance_ratios and conditions, which "
            "are two sources for the same column; pass the advance ratio inside "
            "conditions as 'J' and drop advance_ratios"
        )
    lead = (str(polar), description, str(group), *reference.as_row())
    if conditions is not None:
        states: list[Mapping[str, object]] = list(conditions)
    elif advance_ratios is not None:
        states = [{ADVANCE_RATIO_COLUMN: ratio} for ratio in advance_ratios]
    else:
        states = [{} for _ in rows]
    if len(states) != len(rows):
        raise ProductError(
            f"the polar table was given {len(states)} flight condition(s) for {len(rows)} rows"
        )
    full: list[tuple[object, ...]] = []
    for row, state in zip(rows, states, strict=True):
        if len(row) != len(COEFFICIENT_COLUMNS):
            raise ProductError(f"a polar row has {len(row)} values, not {len(COEFFICIENT_COLUMNS)}")
        full.append((*lead, *context_row(state, columns=_POLAR_CONDITION_COLUMNS), *row))
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
    known writes :data:`NOT_APPLICABLE` rather than a zero, because zero is
    a value a rotor row can have and "not recorded" is not it. Omitted
    entirely, every row's cell reads `NA`, which is what a caller with no
    sweep point to offer should write.

    IT WAS AN EMPTY CELL UNTIL 0.23.0, and the reasoning above is what
    changed the token rather than what resisted it: arguing for a cell that
    is not a zero is arguing for a DISTINGUISHABLE one, and a blank is not
    distinguishable -- from a zero, from a value that went missing, or from
    a column that never applied. This is the worked example the change log
    uses, `...,0.00000,NA,-2.00000,...` on a steady row.
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


# --- PFS-2014.01: the custom polar format, the polar table as the reference tooling reads it --

#: The columns of the custom format's reference line: the nominal Mach and then the
#: reference block in the polar table's own order.
_CUSTOM_REFERENCE_COLUMNS: tuple[str, ...] = ("MNOM", *_REFERENCE_COLUMNS)

#: Every field of the custom format is right-aligned to this width.
_CUSTOM_WIDTH = 10

#: The reference date line, ``Tue Sep 08 23:41:07  2026``: two spaces before the year.
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
    """Refuse the polar format's REMOVED names, naming the replacement.

    Those names carried a possessive prefix before 0.14.0, are spelled
    ``custom`` since, and were removed at 0.16.0 on their promise. This
    hook used to carry a docstring saying it SERVED them and warned, over
    a body that raised the bare AttributeError Python raises with no hook
    at all: the user this most fails is the one upgrading from a
    published 0.14.0, where the old name still worked (the interface lens
    at the release boundary, 2026-09-11).
    """
    from pyflightstream._deprecations import REMOVED_AT_0_16_0, removed_name_refusal

    if name in REMOVED_AT_0_16_0:
        raise AttributeError(removed_name_refusal(__name__, name))
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
    configuration: str | None = None,
) -> Path:
    """Write one polar of one group in the fixed-width text format the reference tooling opens.

    THIS DOCSTRING IS THE SPECIFICATION OF THE FORMAT (PFS-2014.01.02). The
    shape was read off a recorded file and is pinned by the committed fixture
    ``tests/tier1_offline/fixtures/custom_polar_format_sample.dat``, whose
    every value is synthetic; the tier-1 test feeds the fixture's rows
    through this writer and requires byte equality with the fixture,
    except line 3. The file is ASCII, one line feed per line, a line feed
    after the last line, and no line carries a trailing space beyond the
    width of its fields:

    * line 1: the title, ``FlightStream - <description>``, with
      `` - <configuration>`` appended where the row states one (FR-94).
      THE HEADER IS EXACTLY NINE LINES AND THE READER COUNTS THEM, so the
      label joins a line rather than taking one of its own;
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
      (width 10, five decimals, the reference precision), in the column order of
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
    configuration : str, optional
        The row's `CONFIGURATION` label (FR-94), appended to the title of
        line 1 after ` - `. Absent from the title when the row states
        none, so a file written by a row without one is unchanged.

    Returns
    -------
    pathlib.Path
        The file written.

    Raises
    ------
    ProductError
        If a row is not twenty-four values wide.
    """
    # FR-94. THE CONFIGURATION GOES ON LINE 1 AND NOWHERE ELSE, because
    # the format has exactly nine header lines and the reader counts them:
    # a tenth would make every file this writes unreadable by the
    # reference tooling. The title is the one line with room for a word,
    # and ` - ` is the separator the prefix itself already uses.
    title = f"{_CUSTOM_TITLE_PREFIX}{description}"
    if configuration and configuration.strip() and configuration.strip() != "-":
        title = f"{title} - {configuration.strip()}"
    lines = [
        title,
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
    path: str | Path,
    export_text: str,
    *,
    mach: float,
    iteration: int | None = None,
    azimuth_deg: float | None = None,
    step_deg: float | None = None,
    reference: ReferenceValues | None = None,
    advance_ratio: float | None = None,
) -> Path | None:
    """Write one sections table from a sectional loads export.

    ``iteration`` is the solver iteration the distribution was sampled at and
    ``azimuth_deg`` is where the blade was when it was; both lead the row
    because they are the only two things that vary down the file. They replace
    the `POINT` column, which carried the polar's NAME and therefore restated
    the file name (v0.23.0 item 13). A run with no rotor states no azimuth and
    the cell reads `NA`, which is not zero: zero is a real azimuth.

    BOTH ARE READ FROM THE EXPORT WHERE IT STATES THEM, which this docstring
    promised before anything did it: the surface sections export carries
    `Current solver iteration number` in its header, exactly as the loads
    export does, and nothing read it -- so every row of every sections file
    said `NA,NA` while the answer sat in the text the writer was handed. A
    caller that knows better may still pass ``iteration`` and it wins.

    ``step_deg`` is the row's clock: how far the blade turns in one solver
    step, from :func:`pyflightstream.post.series.run_clock`. Given it, the
    azimuth is the iteration ON that clock, WRAPPED -- a step count is not an
    angle, and 1575 steps of 3.6 degrees is 5670 degrees, which is not
    somewhere a blade can be. Without it the azimuth stays `NA`, because the
    alternative is writing a zero that a reader would believe.

    Returns None without writing when the export declares no section, as
    a run that defined no distribution leaves; the columns are the point,
    its condition, and the export's own seven, in the export's units.

    ``reference`` supplies the reference LENGTHS, which this table carried
    none of until 0.23.0: a sectional force beside no area is a number nobody
    can check. It is optional because a caller that genuinely holds no
    reference should write `NA` rather than be refused a product it can
    otherwise make, and a run's reference is recorded beside its outputs
    rather than inside this export.
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
    # ITEM 13. The export states which iteration it is, and the caller's own
    # value wins where it has one -- a caller holding a stamped file name knows
    # the step better than a header does.
    if iteration is None:
        iteration = _stated_iteration(export_text)
    if azimuth_deg is None and iteration is not None and step_deg is not None:
        # WRAPPED. A step count is not an angle.
        azimuth_deg = (iteration * step_deg) % 360.0
    table = np.asarray(report.values, dtype=float)
    if table.shape[1] < 7:
        raise ProductError(
            f"the sectional loads export carries {table.shape[1]} columns, fewer than the seven "
            "the product tables"
        )
    # THROUGH `context_row` AND NOT ASSEMBLED HERE. This lead used to be built
    # by hand in the order ALPHA, BETA, MACH, VINF, RE, ALT; the shared tuple
    # orders them ALPHA, BETA, MACH, RE, VINF, ALT, J, and a hand-built lead is
    # exactly how two families come to disagree about which column is which --
    # a value landing under its neighbour's name, which is the defect 0.23.0
    # item 5 found in three of the four families.
    lead = (
        iteration,
        azimuth_deg,
        *context_row(
            {
                "ALPHA": report.angle_of_attack_deg,
                "BETA": report.sideslip_deg,
                "MACH": mach,
                "RE": _reynolds_millions(export_text),
                "VINF": report.freestream_velocity_m_s,
                "ALT": _altitude_ft(export_text),
                ADVANCE_RATIO_COLUMN: advance_ratio,
            },
            None if reference is None else reference.as_lengths(),
        ),
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


#: FR-91. The columns every probe table opens with, whatever run type filled
#: it, and the whole of what its transparency rests on: which point this is,
#: where it is, the frame those coordinates are measured in, and which solver
#: step the sample is from.
#:
#: `PROBE` IS THE PROBE POINT'S NUMBER and not the `[[probes]]` entry's. It is
#: the vertex counter that runs ACROSS the entries of one artifact, which is
#: the number an unsteady fluid plot carries in its own name, so `MACH7` is
#: row `PROBE` 7. The interface lens asked whether `VERTEX` or `POINT` would
#: be clearer: `POINT` is taken, by the sweep point that names the run, and
#: `PROBE` is the word the requirement uses for these, so the column
#: keeps it and this note says which of the two things it counts.
#:
#: `STEP` carries `NA` on a steady row, which has one step: NOT APPLICABLE.
#: It said `-` until 0.23.0, the glyph the PRINTED cost table still uses, and
#: no product writes a second spelling any more. No spine cell is EVER blank
#: now either: a run recorded before 0.16.0 leaves `NA` in the position and
#: frame columns, which is the one place `NA` stands for a value the package
#: could not derive rather than a column that does not apply -- the exception
#: named beside :data:`NOT_APPLICABLE` and in the change log.
#:
#: THE COORDINATES ARE IN THE UNITS THE ARTIFACT WROTE THEM IN. A probe entry
#: states its points either in the reference's length unit or, where it says
#: `scale = "rotor_radius"`, in rotor radii, which the builder resolves before
#: it emits; no export and no artifact states a unit name, so no column here
#: invents one (the technical writing lens asked, 2026-09-11).
#: THE CONTEXT FOLLOWS THE SPINE AND PRECEDES THE FLUID COLUMNS, so the shape
#: a reader learned at 0.16.0 -- where the point is, in which frame, at which
#: step -- is still the first thing in the row, and the export's own columns
#: still arrive in the export's own order after it. Inserting the condition
#: between them would have moved the fluid columns twice: once now and once
#: whenever the condition grows.
PROBE_SPINE: tuple[str, ...] = (*PROBE_POSITION_COLUMNS, "STEP", *CONTEXT_COLUMNS)


def _probe_parameters(pproc) -> tuple[str, ...]:
    """Return the fluid parameters this artifact's probe entries ask for (FR-91).

    In declaration order, de-duplicated, across every `[[probes]]` entry,
    because the numbered groups of an unsteady plots export are composed
    from these names and the vertex counter runs across the entries.

    THIS IS A UNION AND IT ASSUMES THE ENTRIES AGREE. Where two entries of
    one artifact declare DIFFERENT parameters, the union composes a name for
    each vertex that only one of them has, and `write_unsteady_probes_table`
    cannot write a half row. So such an artifact loses its probe table
    instead of getting a wrong one, which is the right way round.

    SINCE 0.17.0 IT SAYS SO (PFS-2038.05, GEO-039-F06). The drop used to be
    indistinguishable from a row that declared no probes at all; the writer
    now refuses the shape by name. The vertex-to-entry association is known
    in the builder loop that already records the vertex and the frame, and
    recording the parameters beside them is what would SERVE the shape
    rather than name it; that is deliberately not done here.
    """
    out: list[str] = []
    for entry in getattr(pproc, "probes", None) or []:
        for parameter in getattr(entry, "parameters", None) or []:
            if parameter not in out:
                out.append(parameter)
    return tuple(out)


def read_probe_positions(path: str | Path) -> dict[int, tuple[float, float, float, str]]:
    """Read a run's probe positions, keyed by the vertex number (FR-91).

    The file the run stage wrote beside the script that placed the points,
    `sims/<sim>/profiles/<sim>_probe_points.csv`. The key is the vertex
    number, which is the suffix an unsteady fluid plot carries in its own
    name, so `MACH7` is vertex 7 here.

    A file THAT IS NOT THERE answers an empty mapping: every run recorded
    before 0.16.0 names none, and a probe table without its positions is
    what those runs have always produced. Refusing them would take a
    product away from a campaign that already happened.

    A FILE THAT IS THERE AND CANNOT BE READ IS A REFUSAL, which is the
    other half and the one this docstring promised wrongly until
    2026-09-11: it said an unrecognised file answers an empty mapping too,
    twelve lines above the `raise` in this same function. The two states
    are different and must not read alike, or a positions file this
    release wrote and a crash truncated produces a table of empty
    coordinates with nothing anywhere saying so.

    Returns
    -------
    dict
        Vertex number to ``(x, y, z, frame)``, empty when the file is
        absent.

    Raises
    ------
    ProductError
        The file is there and this reader cannot read it. The caller
        records it as a skip naming the file, as it does for a probe
        export it cannot parse.
    """
    target = Path(path)
    if not target.is_file():
        return {}
    out: dict[int, tuple[float, float, float, str]] = {}
    try:
        columns, rows = read_csv_table(target)
    except Exception as error:
        # THE FILE IS THERE AND SAYS NOTHING, which is not the same state as
        # a run recorded before 0.16.0 and must not read as one. Both
        # answered an empty mapping and nothing anywhere recorded it, so a
        # positions file this release wrote and a crash truncated produced a
        # table of empty coordinates in silence (the architecture and
        # interface lenses, 2026-09-11). The ABSENT file above stays silent,
        # as designed.
        raise ProductError(
            f"the probe positions file {target} cannot be read: {error}. It is "
            "where the run stage recorded which probe point is where, so the "
            "probe table of this point cannot say where its samples are. Delete "
            "it and re-run the point to have it written again, or, to get the "
            "rest of the products now, move it aside: a point whose positions "
            "file is ABSENT still gets its table, without the position columns."
        ) from error
    # NO SHAPE CHECK ON THE HEADER, and its absence is deliberate. One stood
    # here and a mutant that deleted it changed no answer this module can
    # produce: the per-row guard below already yields nothing for a table
    # whose cells are not there, and the strict check additionally REFUSED a
    # correctly named table whose columns are in another order, which is a
    # worse answer than reading it. A check nothing can tell from its
    # absence is an opinion wearing a guard's clothes.
    for row in rows:
        try:
            vertex = int(float(row["PROBE"]))
            out[vertex] = (float(row["X"]), float(row["Y"]), float(row["Z"]), str(row["FRAME"]))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _probe_spine(
    vertex: int,
    positions: Mapping[int, tuple[float, float, float, str]],
    step: object = NOT_APPLICABLE,
    *,
    stated: tuple[float, float, float] | None = None,
    context: Sequence[object] = (),
) -> tuple[object, ...]:
    """One row's spine: the point, where it is, its frame, and the step.

    ``stated`` is the position the EXPORT ITSELF carries, which a steady
    probe export does and an unsteady plots export does not. Where the
    export states one it wins, because it is the solver's own answer about
    the point it sampled; the recorded position then supplies only the
    frame NAME, which no export carries at all.

    THE STEP OF A STEADY ROW IS ``NA`` AND WAS ``-`` UNTIL 0.23.0. The owner's
    rule of 2026-09-17 is one sentence -- *"Quando nao se aplica, usa sempre
    NA"* -- and the technical-writing lens had just measured why it matters:
    a steady probes row read ``FRAME=NA`` beside ``STEP=-``, two different
    tokens for one meaning in one row, because ``-`` is non-blank and passed
    the funnel untouched. A reader then has to learn a second token and cannot
    infer it from the documented rule.
    """
    recorded = positions.get(vertex)
    if stated is not None:
        x, y, z = stated
    elif recorded is not None:
        x, y, z = recorded[0], recorded[1], recorded[2]
    else:
        return (vertex, "", "", "", "", step, *context)
    frame = "" if recorded is None else recorded[3]
    return (vertex, x, y, z, frame, step, *context)


def write_probes_table(
    path: str | Path,
    export_text: str,
    *,
    positions: Mapping[int, tuple[float, float, float, str]] | None = None,
    condition: Mapping[str, object] | None = None,
    reference: ReferenceValues | None = None,
) -> Path | None:
    """Write one probe-points table from an EXPORT_PROBE_POINTS export (FR-87, FR-91).

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

    FR-91 PUTS THE SPINE IN FRONT OF THOSE COLUMNS. A steady export
    already states `X`, `Y` and `Z` and it never states WHICH FRAME they
    are measured in, so a reader could place the numbers only by knowing
    the artifact. The export's own coordinates are kept, because they are
    the solver's answer about the point it sampled; the recorded
    positions supply the frame name and nothing else here.

    Parameters
    ----------
    positions : mapping, optional
        Vertex number to ``(x, y, z, frame)``, from
        :func:`read_probe_positions`. Absent for every run recorded
        before 0.16.0, and the spine's position and frame cells then read
        ``NA`` rather than the table being refused. They were EMPTY until
        0.23.0; the producer still returns a blank there and the funnel in
        :mod:`pyflightstream.post._tables` renders it, so this says what the
        user opens rather than what the tuple carries.
    """
    try:
        report = parse_probe_points(export_text)
    except PyflightstreamError as error:
        raise ProductError(f"the probe points export {path} cannot be read: {error}") from error
    values = np.asarray(report.values, dtype=float)
    if values.size == 0:
        return None
    # ONE ASSEMBLY PER TABLE, not per row: every sample in a probes table is a
    # sample of the same point, so the condition belongs to the file.
    context = context_row(condition, None if reference is None else reference.as_lengths())
    known = dict(positions or {})
    columns = tuple(report.columns)
    # THE EXPORT'S OWN X, Y AND Z MOVE INTO THE SPINE rather than being
    # repeated after it. A table carrying two pairs of coordinate columns
    # invites the question of which pair to trust, and the answer would
    # have to be "they are the same", which is a thing to assert and not a
    # thing to ship twice.
    axes = {name: index for index, name in enumerate(columns) if name in ("X", "Y", "Z")}
    rest = tuple(name for name in columns if name not in axes)
    rows: list[tuple[object, ...]] = []
    for order, row in enumerate(values.tolist(), start=1):
        stated = None
        if len(axes) == 3:
            stated = (float(row[axes["X"]]), float(row[axes["Y"]]), float(row[axes["Z"]]))
        rows.append(
            (
                *_probe_spine(order, known, stated=stated, context=context),
                *(float(row[columns.index(name)]) for name in rest),
            )
        )
    return write_csv_table(path, (*PROBE_SPINE, *rest), rows)


def write_unsteady_probes_table(
    path: str | Path,
    plots_table: str | Path,
    *,
    positions: Mapping[int, tuple[float, float, float, str]],
    parameters: Sequence[str],
    condition: Mapping[str, object] | None = None,
    reference: ReferenceValues | None = None,
) -> Path | None:
    """Write the probe table of an UNSTEADY row, from its plots table (FR-91).

    The export that an unsteady row produces for its probes is the plots
    table, and it carries one NUMBERED GROUP per probe point:
    ``MACH7, VELOCITY7, VX7, VY7, VZ7, STATIC_PRESSURE_RATIO7``. It never
    says where vertex 7 is, which is the whole of the requirement: an
    unsteady export never states where its probes are, so the positions
    file is what makes a sample placeable. This un-pivots those groups
    into one row per point and step and puts the recorded position in front
    of them.

    THE COLUMNS ARE COMPOSED FORWARD, from the parameters the artifact
    declares and the vertices the script recorded, exactly as the builder
    composed the names it emitted. A pattern read backward off the header
    would collect a force column of a family named ``Blade1`` as parameter
    ``Blade`` of vertex 1.

    Read from the WRITTEN plots table rather than from the export in
    memory, which is this module's rule: a derived table is derived from
    the file a user holds and can be recomputed from it.

    THE `STEP` COLUMN IS THE TABLE'S OWN `Time-step`, not the row's position,
    which is the rule `post.superfile` already states: the step a sample came
    from is not a guess. A plots table carrying no such column falls back to
    the ordinal, because a product is better than a refusal there and the two
    agree on every export that begins at one and steps by one.

    Returns
    -------
    Path or None
        None when the row recorded no probe position, when the artifact
        declares no probe parameter, or when no group of the two is
        actually in the table: a file of a spine and nothing else is a
        promise of content that is not there.

    Raises
    ------
    ProductError
        If EVERY probe point carries part of its composed group and not
        all of it, which is what an artifact whose entries ask for
        different parameters produces (PFS-2038.05): no table can be
        written, and None there would be a lost product with no message.
        A single incomplete point among whole ones is still left out.
    """
    if not positions or not parameters:
        return None
    columns, rows = read_csv_table(plots_table)
    present = set(columns)
    groups = [
        (vertex, [f"{parameter}{vertex}" for parameter in parameters])
        for vertex in sorted(positions)
    ]
    # PFS-2038.05, GEO-039-F06. A vertex holding SOME of its composed names
    # and not all of them is what an artifact whose entries ask for
    # DIFFERENT parameters produces: `_probe_parameters` unions them and
    # this writer then requires the union at every vertex.
    #
    # THE REFUSAL IS FOR THE LOST PRODUCT ALONE, which is the narrowing.
    # A single point dropped from a table that still gets written is the
    # rule this writer has always had and it stays: a row carrying MACH2
    # with a blank where VX2 belongs reads as a measured absence. What
    # changes is the case where EVERY point is partial, so no table is
    # written and nothing says why: silence there is indistinguishable
    # from a row that declared no probes at all. The review's own fix, the
    # vertex-to-entry-to-parameter mapping, would SERVE the shape; that is
    # a refactor of the probe product nobody has asked for and is not taken.
    partial = [
        (vertex, [n for n in names if n in present])
        for vertex, names in groups
        if not all(n in present for n in names) and any(n in present for n in names)
    ]
    groups = [(vertex, names) for vertex, names in groups if all(n in present for n in names)]
    if not groups:
        if partial:
            vertex, have = partial[0]
            raise ProductError(
                f"no probe table can be written from {Path(plots_table).name}: it carries "
                f"{', '.join(have)} for probe point {vertex}, and every one of its "
                f"{len(partial)} probe points holds part of {', '.join(parameters)} and not "
                "all of it. Those are the parameters the artifact's [[probes]] entries ask "
                "for BETWEEN them, and this writer composes one group per point from their "
                "union, so a point that belongs to only one entry can never be whole. "
                "Declare the SAME parameters on every [[probes]] entry of this artifact. "
                "The samples are in the plots table and are not lost."
            )
        return None
    # THE STEP THE TABLE STATES, never the row's position in it. The plots
    # table carries `Time-step` and the superfile already reads it, with the
    # rule written down there: "The step it came from is not a guess". This
    # read `enumerate(rows, start=1)`, which agrees with the column on every
    # fixture in the tree and disagrees the first time an export does not
    # begin at one or does not step by one (the QA lens scoring M22,
    # 2026-09-11). A table with no such column falls back to the ordinal,
    # which is the only thing left, rather than refusing a product.
    stated = "Time-step" if "Time-step" in present else None
    context = context_row(condition, None if reference is None else reference.as_lengths())
    out: list[tuple[object, ...]] = []
    for ordinal, row in enumerate(rows, start=1):
        step: object = ordinal
        if stated is not None:
            text = str(row.get(stated) or "").strip()
            try:
                value = float(text)
            except ValueError:
                value = float("nan")
            if value == value:  # not NaN
                step = int(value) if value.is_integer() else value
        for vertex, names in groups:
            out.append(
                (
                    *_probe_spine(vertex, positions, step, context=context),
                    *(float(row[name]) for name in names),
                )
            )
    return write_csv_table(path, (*PROBE_SPINE, *tuple(parameters)), out)


# --- PFS-2015.04: the reductions of a plots table, beside it -----------------------

#: The window block every reduction row carries before the plots table's own
#: columns: which reduction, which window of it (1-based), the inclusive
#: solver steps it spans, and how many rows of the table fell inside.
REDUCTION_COLUMNS: tuple[str, ...] = (
    "REDUCTION",
    "WINDOW",
    "FIRST_STEP",
    "LAST_STEP",
    "STEPS",
    *CONTEXT_COLUMNS,
)


#: PFS-2038.04. The column an unsteady plots export states its clock in.
#: The same name `post.superfile` and the probe table already read, and the
#: same rule those two write down: the step a sample came from is not a guess.
PLOTS_STEP_COLUMN = "Time-step"


def _stated_steps(columns: Sequence[str], values: np.ndarray, n_rows: int) -> np.ndarray:
    """Return the exported clock where the table states one, the ordinal otherwise."""
    ordinal = np.arange(1, n_rows + 1, dtype=int)
    if PLOTS_STEP_COLUMN not in columns or not n_rows:
        return ordinal
    stated = values[:, list(columns).index(PLOTS_STEP_COLUMN)]
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

    Returns
    -------
    tuple
        The table's columns, in its order, and the series.
    """
    columns, rows = read_csv_table(path)
    values = np.asarray([[float(row[name]) for name in columns] for row in rows], dtype=float)
    return columns, TimestepSeries(
        steps=_stated_steps(columns, values, len(rows)),
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
    condition: Mapping[str, object] | None = None,
    reference: ReferenceValues | None = None,
) -> Path:
    """Write one reduction of a plots table: one row per window, the table's columns averaged.

    ``condition`` and ``reference`` are what the row is a reduction OF, and
    this table carried neither until 0.23.0: a window of averaged coefficients
    with no angle of attack and no reference area beside it is a set of numbers
    about nothing. Both are optional, and what neither supplies reads `NA`
    rather than being invented.

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
    # PFS-2038.04. Against the STEPS the table states, not against its row
    # count. The two are the same number on every export recorded here, and
    # they part company the moment a clock does not begin at one: a window
    # of steps 101 to 102 over a three-row table is inside the history and
    # was refused as though it reached past the end of it. This is the
    # bound alone; the review's step-coverage validation, which would
    # refuse windows that work today, is not taken.
    # ASSEMBLED ONCE, OUTSIDE THE LOOP: every window of one reduction is a
    # reduction of the SAME point, so the condition is the row's context and
    # not the window's.
    context = context_row(condition, None if reference is None else reference.as_lengths())
    first_step = int(series.steps[0]) if len(series.steps) else 1
    last_step = int(series.steps[-1]) if len(series.steps) else 0
    for index, (first, last) in enumerate(windows, start=1):
        if int(last) > last_step or int(first) < first_step:
            raise ProductError(
                f"the plots table runs from step {first_step} to step {last_step} and the "
                f"{reduction} window {index} spans steps {first} to {last}, so the history "
                "does not cover the window the row states; a shorter history averaged as a "
                "whole one would be an average of a run that did not finish writing"
            )
        average = blade_passage_average(series, window=(int(first), int(last)))
        rows.append(
            (
                reduction,
                index,
                int(first),
                int(last),
                average.n_frames,
                *context,
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
    (the design decision of 2026-09-09) and the summer is asked for that reading.
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
                # NO `point=` SINCE 0.23.0 ITEM 13: the polar's name is the
                # FILE's name and a column spent restating it told no row
                # from another. The iteration and the azimuth are read from
                # the export where it states them and are `NA` where it does
                # not, which is the honest answer for a steady distribution
                # and for a run that recorded no clock.
                mach=mach,
                # ITEM 5. This path rebuilds from a bare folder of recorded
                # loads files and reaches no run record, so the advance ratio
                # is not available here and is NOT invented: the reference is
                # what this caller has, and it is what a coefficient most needs
                # beside it.
                reference=ref,
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
#: WHY THEY MOVED. Measured in the reference workspace recorded after
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


#: The folder an existing product is moved into before a new one is
#: written, under the matrix's own post folder: ``archive/<day and hour>/``.
#: One folder per rebuild, so a rebuild is one thing a reader can look at.
#:
#: BOTH NAMES MOVED DOWN TO THE NAMING MODULE AT 0.18.0 and are re-exported
#: here under the spellings this layer has always used. A continuation
#: archives a DATAPOINT under the same stamp, and the workspace layer cannot
#: import from post: dependencies flow downward. A second copy of the format
#: in the lower layer would be a second home for one fact, which is the
#: failure this estate keeps paying for, so the fact moved rather than being
#: duplicated.
PRODUCT_ARCHIVE_DIR = ARCHIVE_DIR

#: How the stamp is spelled. Sortable, no separator a file system objects
#: to, and to the SECOND: two rebuilds in one minute are two rebuilds.
PRODUCT_ARCHIVE_STAMP = ARCHIVE_STAMP


def product_archive_dir(path: Path, *, now: datetime | None = None) -> Path:
    """Where the product at ``path`` is archived to before it is rewritten.

    ``<the product's own folder>/archive/<day and hour>/``: the archive
    sits BESIDE the product it replaces, so a reader who has opened
    ``polars/`` to compare two polar tables finds the old one in that same
    folder rather than in a tree somewhere above it.

    THE STAMP IS THE REBUILD'S, passed in by the post stage, so every
    product a rebuild archives lands under one folder name even though the
    folders themselves are per-product.

    THIS DOCSTRING SAID ``post/<matrix>/archive/`` UNTIL 2026-09-13, which
    is one archive for the whole rebuild "keeping whatever folders the
    product sat in below the matrix". That is a different layout from the
    one the body returns and from the one the tier-1 case asserts, and the
    sentence read as a design nobody had built (the QA lens).
    """
    stamp = (now or datetime.now()).strftime(PRODUCT_ARCHIVE_STAMP)
    for parent in path.parents:
        if parent.name == PRODUCT_ARCHIVE_DIR:
            # Already inside an archive: never archive an archive.
            return path.parent
    return path.parent / PRODUCT_ARCHIVE_DIR / stamp


def _refuse_an_existing_product(
    path: Path, *, archive: bool = True, stamp: datetime | None = None
) -> Path:
    """Return ``path``, ARCHIVING an existing product rather than losing it.

    THE AUTHOR'S INSTRUCTION OF 2026-09-12, and it arrived as feedback on the fix
    that makes a regenerated SUPER file report different numbers: without
    an archive the previous table is gone and nothing says it ever said
    something else.

    THREE BEHAVIOURS AND ONE FLAG, and the default is the first:

    * the product exists and ``archive`` holds: it is MOVED into
      ``<its own folder>/archive/<day and hour>/`` and the new one is
      written in its place. Nothing is lost and nothing is refused.
    * the product exists and ``archive`` is false: it is overwritten and
      no copy is kept. That is the explicit escape, and the command line
      spells it ``--force-overwrite`` and asks for a confirmation, so it
      cannot be reached by habit.
    * the product does not exist: nothing happens.

    IT TOOK AN ``overwrite`` FLAG TOO, AND THAT WAS THE DEFECT. The guard
    read ``not archive and overwrite``, so a caller asking for no archive
    with no overwrite, which is the documented do-not-archive request,
    fell through and archived anyway: one cell of a two-boolean truth
    table that no test named and no shipped path reached. Making them
    independent left ``overwrite`` deciding nothing at all, and a
    parameter that decides nothing is one the next caller will set and be
    surprised by, so it is gone rather than left dead (the QA lens, rounds
    one and two).

    THE OLD REFUSAL IS GONE, which is the part worth saying plainly. It
    existed to stop a rebuild destroying a product silently, and archiving
    answers that better: a refusal makes the user delete the file, which
    destroys it just as thoroughly and puts the work on them.
    """
    if not path.exists():
        return path
    # THE TWO FLAGS ARE INDEPENDENT, and they were not: the guard read
    # `not archive and overwrite`, so a caller asking for no archive with
    # no overwrite, which is the documented do-not-archive request, fell
    # through and archived anyway. One cell of a two-boolean truth table
    # that no test named and no shipped path reached, which is exactly how
    # it survived (the QA lens, 2026-09-13).
    if not archive:
        return path
    target = product_archive_dir(path, now=stamp)
    target.mkdir(parents=True, exist_ok=True)
    moved = target / path.name
    if moved.exists():
        # Two rebuilds inside one second, which the stamp cannot separate.
        # Numbering is better than either losing one or refusing the write.
        index = 2
        while (target / f"{path.stem}.{index}{path.suffix}").exists():
            index += 1
        moved = target / f"{path.stem}.{index}{path.suffix}"
    path.replace(moved)
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
    archive: bool = True,
    archive_stamp: datetime | None = None,
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
    probe_positions: dict[int, tuple[float, float, float, str]] = {}
    # DECLARED HERE rather than with its siblings below, because the
    # positions are read in the record loop and an unreadable file is
    # recorded there, before the products loop that fills the rest.
    skipped: dict[str, str] = {}
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
        # FR-91. Where this run put its probe points. Per SIM and identical
        # across the sweep, so the first record that names one answers for
        # every point; a record written before 0.16.0 names none and the
        # probe table is then written without the position columns, as it
        # always was.
        if record.probe_points_file and not probe_positions:
            # CAUGHT HERE, AND THE BLAST RADIUS IS WHY. `read_probe_positions`
            # refuses a file that is there and cannot be read, which is the
            # distinction round one asked for; but this function's caller
            # catches `ProductError` per SIMULATION, so letting it out would
            # cost this simulation its polar table, its plots tables and every
            # reduction over one unreadable positions file. That is the rename
            # taking a product away that the probe-export reader twenty lines
            # below is written against (the QA lens, round two, 2026-09-11).
            try:
                probe_positions.update(read_probe_positions(sim_dir / record.probe_points_file))
            except ProductError as error:
                skipped[f"{PROBES_DIR}/{record.probe_points_file}"] = str(error)
    if not points:
        # NOTHING COLLECTED YET, which is the ordinary state between `run` and
        # `collect` and is not an error: the stage writes no product for this
        # simulation and the campaign's other simulations are unaffected. It is
        # also what makes `recorded` non-empty below.
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
    # BOUND BEFORE THE `products.polars` GATE, deliberately. Every product
    # family states the condition since item 5, so a pproc writing no polar
    # still needs this for its probes and its reduction; binding it inside the
    # polar branch is a NameError on `polars = false`, which is the shape the
    # advance-ratio list beside it already had.
    cell = first.flight_condition if isinstance(first.flight_condition, Mapping) else None
    # ITEM 13's other half. The clock is a property of the ROW's export
    # settings, so every point of one row shares it; the iteration is per point
    # and comes out of each export's own header.
    _, step_deg = run_clock(first)
    run_ids = [rid for stem in sources for rid in sources[stem]]
    written_names: dict[str, dict[str, object]] = {}
    #: One entry per group: where its superfile goes and the polar rows it
    #: carries, in the point order of `points` (FR-89).
    super_rows: dict[str, tuple[Path, list[tuple[object, ...]]]] = {}
    #: The plots table written for each point, read back for the superfile.
    plots_tables: dict[str, Path] = {}

    def _target(path: Path) -> Path:
        return _refuse_an_existing_product(path, archive=archive, stamp=archive_stamp)

    # PFS-2038.03, GEO-039-F03. HERE, before the first product of this
    # simulation is written, and not in the reduction loop where the first
    # colliding file has already been written over the second. Two aliases
    # that a file name cannot tell apart are refused for the whole
    # simulation, so the refusal costs nothing to recover from.
    _refuse_aliases_a_file_name_cannot_tell_apart(plans, sim_id)

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
        # 0.21.0: THE NAMES ARE THE ONES THE RUN RECORDED. A record written before
        # 0.21.0 carries none, and naming its tables by a recomputed name would
        # set them beside files of another scheme.
        # NON-EMPTY BY CONSTRUCTION, and the construction is twenty lines up:
        # a point is appended only inside the loop that SKIPS a record with no
        # outputs, so `points` is empty whenever this list would be, and
        # `if not points: return` has already returned. The closing round of
        # 0.21.0 put a refusal here against an IndexError at `recorded[0]`;
        # measured by probe, no case reaches it, and a branch nothing reaches
        # reads as covered while proving nothing.
        recorded = [record for record in records if record.outputs]
        if any(record.sweep_name is None or record.point_name is None for record in recorded):
            raise ProductError(
                f"simulation {sim_id!r} holds records written before 0.21.0, which carry no "
                "point name; run `pyfs-matrix rename` once, naming the workspace root as workspace "
                "(CLI: --workspace), then post"
            )
        table_name = str(recorded[0].sweep_name) if swept else str(recorded[0].point_name)
        # FR-89: the SUPERFILE is about the sweep the ROW DECLARES, which is the one
        # place its name differs from the polar table's beside it: a row declaring
        # a one-value sweep still names it `+sweep`. With no matrix row in reach it
        # follows the table.
        super_name = str(recorded[0].sweep_name) if matrix_row is not None or swept else table_name
        # ITEM 5 WIRED HERE. This read ONE key of the condition by hand --
        # `advance_ratio` -- and the other columns the release added therefore
        # reached the file as `NA` in every row. `point_condition` assembles the
        # whole condition, reported over requested, and `context_row` resolves
        # each recorded spelling onto its column.
        conditions = [point_condition(point, mach=mach, cell=cell) for point in points]
        for group, families in pproc.groups.items():
            rows = _polar_rows(
                points, list(families), mach=mach, reference=reference, aliases=first.aliases
            )
            target = _target(
                out / POLARS_DIR / swept_polar_file_name(sim_id, name=table_name, group=group)
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
                conditions=conditions,
            )
            write_csv_table(target, POLAR_COLUMNS, full)
            if drafts is not None:
                super_rows[str(group)] = (
                    out / POLARS_DIR / super_file_name(sim_id, sweep=super_name, group=group),
                    full,
                )
            written.append(target)
            written_names[target.relative_to(out).as_posix()] = {"runs": run_ids}
            if products.custom_polar_format:
                # PFS-2014.01.01: the same rows, a second time, in the
                # format the existing tooling opens, beside the table.
                target = _target(
                    out
                    / POLARS_DIR
                    / swept_polar_file_name(sim_id, name=table_name, group=group, suffix=".dat")
                )
                write_custom_polar_format(
                    target,
                    polar=sim_id,
                    description=description,
                    group=group,
                    mach=mach,
                    reference=reference,
                    rows=rows,
                    # FR-94. The row's own label, off the matrix row this
                    # polar belongs to. None where the workspace has no
                    # matrix to read, which is every campaign authored in
                    # Python, and the title is then what it always was.
                    configuration=(
                        matrix_row.variables.get(CONFIGURATION_VARIABLE)
                        if matrix_row is not None
                        else None
                    ),
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
                # NO `point=` SINCE 0.23.0 ITEM 13: the polar's name is the
                # FILE's name and a column spent restating it told no row
                # from another. The iteration and the azimuth are read from
                # the export where it states them and are `NA` where it does
                # not, which is the honest answer for a steady distribution
                # and for a run that recorded no clock.
                mach=mach,
                # ITEM 5 WIRED HERE. A section is a distribution along a chord,
                # and a number beside no reference length is a number nobody can
                # check. The sections table carried no length AT ALL before this
                # release, and carried the COLUMN and not the value until this
                # line.
                reference=reference,
                advance_ratio=_advance_ratio_of(point),
                # ITEM 13. The iteration comes out of the export itself; the
                # CLOCK does not, and only a record states it. `run_clock` is
                # the one that writes the point series, published for this
                # rather than copied: two functions deriving one clock is how
                # two products of a point disagree about when it was sampled.
                step_deg=step_deg,
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
                    target,
                    probes_path.read_text(encoding="utf-8", errors="replace"),
                    positions=probe_positions,
                    # ITEM 5. A probe sample with no condition is a table about
                    # nowhere, and this family carried none of the twenty-four
                    # coefficients, so it states the WHOLE condition.
                    condition=point_condition(point, mach=mach, cell=cell),
                    reference=reference,
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
                # FR-91. The unsteady half, and only where the steady
                # export did not already write this point's table: a row
                # that produced both has the fuller of the two, and two
                # writers racing for one name is the duplicate FR-90 is
                # about.
                # FROM THE DATA AND NOT FROM THE FILESYSTEM. This asked
                # whether the destination existed, so a stale table left by an
                # earlier post run suppressed the fresh one and the product
                # depended on state outside this invocation (the architecture
                # lens, 2026-09-11). The question is whether THIS point had a
                # steady probe export, which is the thing the rule is about.
                steady_probes = exports[point.name][2]
                if steady_probes is None or not steady_probes.is_file():
                    # `_target` IS CALLED INSIDE THE GATE, not before it. It
                    # refuses a product that already exists, and on a point
                    # that produced BOTH exports the steady writer has just
                    # written this very path, so calling it first turned the
                    # steady-wins rule into a refusal of the whole simulation
                    # (found by the case written for this rule, 2026-09-11).
                    probe_target = _target(out / PROBES_DIR / f"{point.name}_probes.csv")
                    field = write_unsteady_probes_table(
                        probe_target,
                        done,
                        positions=probe_positions,
                        parameters=_probe_parameters(pproc),
                        # ITEM 5. A probe sample with no condition is a table
                        # about nowhere: the numbers in it are a flow field, and
                        # which flow is exactly what the condition states.
                        condition=point_condition(point, mach=mach, cell=cell),
                        reference=reference,
                    )
                    if field is not None:
                        written.append(field)
                        written_names[field.relative_to(out).as_posix()] = {
                            "runs": sources[point.name]
                        }
                _point_reductions(
                    done,
                    plans[point.name],
                    out,
                    runs=sources[point.name],
                    target=_target,
                    written=written,
                    written_names=written_names,
                    skipped=skipped,
                    # ITEM 5, threaded from HERE because this is where the point
                    # still is: `_point_reductions` takes a plots table and a
                    # plan and reaches no record at all.
                    condition=point_condition(point, mach=mach, cell=cell),
                    reference=reference,
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
    archive: bool = True,
    archive_stamp: datetime | None = None,
) -> tuple[list[Path], dict[str, dict[str, object]]]:
    """Write the series tables of one windowed record (PFS-2031.18.01).

    Each existing table is archived under the rebuild's stamp before it is
    rewritten, by the same archiver as every other product; ``archive``
    false keeps no copy.
    """
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
        # `archive` WAS ACCEPTED HERE AND NEVER USED until 2026-09-14, so the
        # series were the one product a rebuild rewrote in place.
        target=lambda path: _refuse_an_existing_product(path, archive=archive, stamp=archive_stamp),
    )


#: The characters an alias may carry into a file name. Everything else is
#: replaced, because a rotor's alias is a word the user chose and a file
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


def _refuse_aliases_a_file_name_cannot_tell_apart(
    plans: Mapping[str, Mapping[str, object] | None], sim_id: str
) -> None:
    """Refuse two rotor aliases that sanitize to one file name (PFS-2038.03).

    THE COMPLETE TARGET SET, RESOLVED BEFORE ANY WRITE. `A/B` and `A:B`
    are both valid aliases and both become `A_B`, and the product path
    writes with overwrite: the reviewer measured two writes reported and
    one file left, carrying the second rotor's identity. Silent
    replacement of a derived result is the worst failure class here.

    WHAT IS NOT TAKEN is the review's other option, a collision-resistant
    filename encoding. The readable point name is a deliberate convention
    of this release and hashing it, to close a case that has never
    occurred, would cost every file a reader opens. MEASURED 2026-09-11:
    all 14 rotor aliases declared in every reference here are letters and
    underscores only, so nothing in these workspaces is refused by this;
    it is for the users the package now has.
    """
    by_safe: dict[str, list[str]] = {}
    for plan in plans.values():
        rotors = plan.get(ROTORS_KEY) if isinstance(plan, Mapping) else None
        if not isinstance(rotors, Mapping):
            continue
        for alias in rotors:
            spelling = str(alias)
            held = by_safe.setdefault(_a_name_a_file_may_carry(spelling), [])
            if spelling not in held:
                held.append(spelling)
    collisions = {safe: names for safe, names in by_safe.items() if len(names) > 1}
    if not collisions:
        return
    detail = "; ".join(
        f"{' and '.join(repr(name) for name in names)} both become {safe!r}"
        for safe, names in sorted(collisions.items())
    )
    raise ProductError(
        f"simulation {sim_id!r} names rotors a file name cannot tell apart: {detail}. Each "
        "rotor's passage reductions land in a file named for its alias, so one rotor's "
        "result would be written over another's and the file left would carry the wrong "
        "rotor's identity. Nothing has been written. Rename these rotors so they differ in "
        "letters, digits, hyphens, underscores or dots, which are the characters a file "
        "name keeps; the alias you choose is recorded verbatim in the manifest either way."
    )


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
    condition: Mapping[str, object] | None = None,
    reference: ReferenceValues | None = None,
) -> None:
    """Write every applicable reduction of one plots table beside it (PFS-2015.04).

    The plots table is written FIRST and is never touched here: the
    reductions are read off it and land under their own names beside it,
    which is the rule of 2026-08-16 (a reduction ships beside the history
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
                # THE POINTER REPLACES THE GENERIC TAIL AND ADDS NOTHING ELSE.
                # The head up to the last colon already says the row names its
                # rotors; appending that again made one fact print twice and
                # buried the file names at the end of the repetition, on six
                # lines of every rotor sweep (PFS-2015.05).
                reason = (
                    f"{reason.rsplit(':', 1)[0]}: the per-rotor files are "
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
                destination,
                series,
                columns,
                reduction=name,
                windows=windows,
                # ITEM 5. A reduction is an AVERAGE over a window, and an
                # average of coefficients states nothing without the condition
                # they were taken at and the lengths they were normalised by.
                # Both are threaded in from the caller: this function reaches no
                # record, and inventing them here is how two products of one
                # point come to disagree about what point it was.
                condition=condition,
                reference=reference,
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


def operator_agent(name: str | None) -> dict[str, object]:
    """Return the `prov:Person` agent for the operator a record names.

    A `prov:Person` and not a string on the activity, because the document is
    W3C PROV and already carries two `prov:SoftwareAgent`s: the operator is the
    third agent the run was associated with, which another tool reads without
    being told anything about this package.

    ``None`` is the run she ALREADY HAS. `submitted_by` is a RUN-time fact and
    nobody recorded it for the simulations that already finished; it cannot be
    recovered and none is invented. The field is PRESENT and reads `NA`, so a
    reader tells a run that predates this release from a document that forgot.
    """
    stated = (name or "").strip()
    return {
        "prov:type": "prov:Person",
        "pyfs:submitted_by": stated or NOT_APPLICABLE,
    }


def _prov_document(record: RunRecord, sim_dir: Path) -> dict[str, object]:
    """Build one run's PROV-JSON document from its record and the files it left.

    W3C PROV, in the PROV-JSON serialization (the design decision of 2026-09-08,
    design 68): the run record carried every fact a provenance document
    needs and lacked a shape another tool reads without reading this
    package's docs. ENTITIES are each staged input (``inputs_sha256``), the
    script (``script_sha256``) and each collected output, every one with
    its sha256 under ``pyfs:sha256``; an output's hash is computed from
    the file when it is still there and taken from the record otherwise,
    and ``pyfs:sha256_from`` says which.

    WHERE THE FILE'S BYTES ARE NOT THE RECORDED ONES the output entity
    keeps the RECORDED digest and the generation claim, because that
    claim is true, and what the file holds now becomes a second entity,
    ``pyfs:file/<name>``, of type ``pyfs:ChangedOutput``, listed under
    ``wasDerivedFrom`` and generated by no activity (PFS-2038.01). The
    document therefore never asserts that a run produced bytes it did
    not. It does not refuse: an edited or re-exported output is a
    workspace's business, and saying so correctly is the fix.

    The ACTIVITY is the solver run,
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
    # ONE AGENT ID PER OPERATOR, so two runs by the same person are the same
    # agent in the document rather than two agents that happen to agree.
    operator = operator_agent(getattr(record, "submitted_by", None))
    operator_id = f"pyfs:operator/{operator['pyfs:submitted_by']}"
    entities: dict[str, dict[str, object]] = {}
    used: dict[str, dict[str, str]] = {}
    generated: dict[str, dict[str, str]] = {}
    attributed: dict[str, dict[str, str]] = {}
    #: PFS-2038.01. One entry per output whose bytes on disk are not the
    #: bytes the run recorded: what the file holds now, derived from what
    #: the run produced and generated by nothing.
    derived: dict[str, dict[str, str]] = {}
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
        recorded = record.outputs_sha256.get(name)
        current = file_sha256(path) if path.is_file() else None
        # PFS-2038.01, GEO-039-F01. THE BYTES ON DISK MAY NOT BE THE BYTES
        # THE RUN WROTE, and this document used to say they were: it
        # preferred the current digest whenever the file existed and then
        # bound that entity to the run through `wasGeneratedBy`. A file
        # edited, repaired or re-exported after the run was therefore
        # attributed to a run that never produced it. That is a false
        # statement rather than a wrong number.
        changed = current is not None and recorded is not None and current != recorded
        if changed:
            # The ORIGINAL entity keeps the recorded digest and keeps the
            # generation claim, which is true: the run did produce those
            # bytes. What is on disk becomes a SEPARATE, DERIVED entity
            # that says so, generated by nothing here and attributed to
            # nobody.
            output_sha256: str | None = recorded
            sha256_from: str | None = "record"
        elif current is not None:
            output_sha256 = current
            sha256_from = "file"
        else:
            output_sha256 = recorded
            sha256_from = "record" if recorded is not None else None
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
        if changed:
            derived_id = f"pyfs:file/{name}"
            entities[derived_id] = _attributes(
                **{
                    "prov:type": "pyfs:ChangedOutput",
                    "pyfs:name": name,
                    "pyfs:sha256": current,
                    "pyfs:sha256_from": "file",
                    "pyfs:recorded_sha256": recorded,
                    "pyfs:note": (
                        "the bytes at this path differ from the ones the run recorded; "
                        "this entity is what the file holds now and no activity here "
                        "claims to have produced it"
                    ),
                }
            )
            derived[f"_:derived{len(derived) + 1}"] = {
                "prov:generatedEntity": derived_id,
                "prov:usedEntity": entity_id,
            }
            # NO REFUSAL, and that is the narrowing. The review recommends
            # refusing or marking mismatches before deriving trusted
            # products; a refusal would stop the post stage on any
            # workspace whose outputs were ever touched by hand, including
            # a legitimate re-export or a file repaired after a partial
            # write. Correcting the assertion is the whole defect.
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
            # The design decision of 2026-09-09: the setup's aliases the polar tables resolved by.
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
        # THE OPERATOR, v0.23.0 item 12. Always present: a record that names
        # nobody reads `NA`, which is the run she already has, and the absence
        # is visible rather than silent.
        operator_id: operator,
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
    # PFS-2038.01. Absent on every document whose outputs still hold the
    # bytes they were recorded with, which is every document this package
    # has written until one of them does not.
    if derived:
        document["wasDerivedFrom"] = derived
    return document


def _run_provenance(
    workspace: CampaignWorkspace,
    records: Sequence[RunRecord],
    out: Path,
    *,
    overwrite: bool,
    archive: bool = True,
    archive_stamp: datetime | None = None,
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
        if target.exists() and archive:
            # THE SAME RULE AS A PRODUCT. A provenance document about to
            # be rewritten is evidence about the run that produced the
            # file it describes, so it is archived rather than replaced.
            _refuse_an_existing_product(target, archive=True, stamp=archive_stamp)
        elif target.exists() and not overwrite:
            raise ProductExistsError(
                f"the provenance document {target} exists; pass overwrite=True to rewrite "
                "it from the manifest, and the old one is archived rather than lost. "
                "`pyfs-matrix post` passes it already, so this reaches a library caller "
                "alone: the command-line flag this named until 2026-09-13, --overwrite, "
                "is gone and argparse now refuses it (the interface lens)"
            )
        document = _prov_document(record, workspace.sim_dir(record.sim_id))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8")
        index[record.run_id] = relative
    return index


def write_campaign_products(
    workspace: CampaignWorkspace,
    *,
    overwrite: bool = False,
    archive: bool = True,
    archive_stamp: datetime | None = None,
    matrix_stem: str | None = None,
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
    # ONE STAMP PER REBUILD, taken here and threaded to every archiver.
    #
    # The archive folder's whole claim is that a rebuild is ONE thing a
    # reader can look at. It was not: each archiver called `datetime.now()`
    # for itself at one-second resolution, so a rebuild that archived more
    # products than fit in one second scattered them across two folders or
    # more, and the reader comparing before and after had to union N
    # siblings and could not tell a second boundary from a second rebuild
    # (the interface lens, 2026-09-13). The collision branch below the
    # stamp guards two rebuilds INSIDE one second, which is the rare case;
    # this was the common one.
    archive_stamp = archive_stamp or datetime.now()
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
        # FR-95. ONE JOB IS SEVERAL POINTS, so the record is expanded
        # before its status is read. A steady row is one job since 0.17.0
        # and its record carries every point of the sweep; unexpanded, the
        # product stage classified all of their outputs together, selected
        # ONE loads file, and wrote a three-point polar with one row. And
        # the aggregate status was the filter, so one failed point
        # excluded every successful point of the same job.
        #
        # `as_points()` exists for exactly this and was called by the
        # sweep table and the QA matrix and not here: a method built and
        # not wired, in the one place nobody looked. Found by the
        # independent Codex review of `main`, 2026-09-13 (GEO-047-C02).
        # A record that is one point returns itself, so nothing written
        # before 0.17.0 changes.
        for point_record in record.as_points():
            if point_record.status in (RunStatus.CONVERGED, RunStatus.COMPLETED_MAX_ITER):
                by_sim.setdefault(point_record.sim_id, []).append(point_record)
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
                    workspace,
                    sim_id,
                    record,
                    out,
                    overwrite=overwrite,
                    archive=archive,
                    archive_stamp=archive_stamp,
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
                archive=archive,
                archive_stamp=archive_stamp,
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
            target=lambda path: _refuse_an_existing_product(
                path, archive=archive, stamp=archive_stamp
            ),
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

        # THE SECTIONS MEASUREMENT, beside the superfile one and written the
        # same way: from the workspace rather than from this stage's own
        # arithmetic. It counts what each point's ARTIFACT declared against
        # what its SCRIPT emitted, two different files, neither derived from
        # the other (FR-83).
        # The records are pydantic models here and the measurement takes
        # plain mappings, because it reads the same JSON a manifest on disk
        # holds and must not depend on this package's model to do it.
        section_cases = measure_sections(
            workspace.root, [record.model_dump(mode="json") for record in records]
        )
        if section_cases:
            sections_report = write_sections_report(
                workspace.root,
                version=pyflightstream.__version__,
                cases=section_cases,
            )
            manifest["sections_report"] = sections_report.relative_to(workspace.root).as_posix()
    # Always present, empty when nothing was refused, so a wrapper reads one
    # key rather than testing for it (review round two of 2026-09-08).
    manifest["skipped"] = skipped
    # PFS-2012.08.01: one document per recorded run, whatever its status.
    manifest["provenance"] = _run_provenance(
        workspace,
        records,
        out,
        overwrite=overwrite,
        archive=archive,
        archive_stamp=archive_stamp,
    )
    if written or skipped or records:
        out.mkdir(parents=True, exist_ok=True)
        (out / PRODUCTS_MANIFEST).write_text(
            json.dumps(manifest, indent=1) + "\n", encoding="utf-8"
        )
    return written
