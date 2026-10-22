"""The polar: one row per point of a sweep, per boundary group, as a CSV table.

One of the product families of :mod:`pyflightstream.post` (AD-13, work
package WP5), written by the post stage of
:mod:`pyflightstream.post.products`, which re-exports every name here.

A POLAR table per boundary GROUP of the pproc artifact, under ``polars/``
(FR-88): one row per point, the reference block and the coefficients of the
group in body, stability and wind axes with the two drag parts
(:data:`POLAR_COLUMNS`). A point is a :class:`PolarPoint`, its group's sums a
:class:`GroupCoefficients` (:func:`group_coefficients`), its row
:func:`polar_row`; the table is assembled once by :func:`polar_table_rows`,
so the superfile beside it carries the same rows, and written by
:func:`write_polar_table`. The file is named for the sweep the records
measure (:data:`SWEEP_AXES`, :func:`swept_axes`, :func:`swept_polar_file_name`).
An induced drag the solver declined to compute is named by
:func:`declined_induced_drag` and summed as ``NA``.

:func:`write_recorded_polar` regenerates the polar, sections and plots
tables of a recorded point from its exports alone.

The TRIMMED POLAR (FR-2302, FR-2303) is the polar's row at zero pitching
moment, interpolated inside the sampled angles and never extrapolated:
:func:`trimmed_polar_row` finds it and :func:`write_trimmed_polar` writes it
beside its polar table (``[products] trimmed_polar``). A further kind of the
backlog (a Richardson-extrapolated polar over a mesh family) joins this
module beside the table it extends.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from warnings import warn

import pyflightstream._textio as _textio
from pyflightstream._errors import PyflightstreamDeprecationWarning, PyflightstreamError
from pyflightstream._tokens import NOT_APPLICABLE, POLAR_ID_COLUMN
from pyflightstream.cases import select_group_members
from pyflightstream.post._condition import (
    PointState,
    _mach_of,
    _on_the_vorticity_list,
    _refuse_a_reference_the_solver_did_not_use,
)
from pyflightstream.post._stage import PROBES_DIR, SECTIONS_DIR
from pyflightstream.post._tables import (
    _REFERENCE_COLUMNS,
    ADVANCE_RATIO_COLUMN,
    COEFFICIENT_COLUMNS,
    FLIGHT_CONDITION_COLUMNS,
    ProductError,
    ProductExistsError,
    ReferenceValues,
    context_row,
    polar_file_name,
    read_csv_table,
    write_csv_table,
)
from pyflightstream.post.axes import polar_axis_coefficients
from pyflightstream.post.point_tables import write_plots_table, write_sections_table
from pyflightstream.results import DRAG_PAIRS, LoadsReport, drag_pair, parse_loads
from pyflightstream.workspace.naming import group_token, sweep_file_stem

__all__ = [
    "DRAG_PRODUCT_COLUMNS",
    "GEOMETRY_ANALYSIS_FRAMES",
    "POLAR_COLUMNS",
    "SWEEP_AXES",
    "GroupCoefficients",
    "PolarPoint",
    "declined_induced_drag",
    "drag_columned_rows",
    "drag_columns_of",
    "group_coefficients",
    "group_polar_rows",
    "polar_row",
    "polar_table_columns",
    "polar_table_rows",
    "swept_axes",
    "swept_polar_file_name",
    "write_polar_table",
    "write_recorded_polar",
    "TRIM_ANGLE_COLUMN",
    "TRIM_MOMENT_COLUMN",
    "TRIM_SUFFIX",
    "trimmed_polar_row",
    "write_trimmed_polar",
]

#: WHY THE ADVANCE RATIO HAS A COLUMN AT ALL (FR-85), kept here beside its one
#: user although the constant itself moved to `post._tables`, where
#: three modules can compose it. Measured on the reference ``0001_M15_g01.csv``,
#: written by the package for a three-value sweep of the advance ratio: the three
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
#: DERIVED, not listed: the shared condition minus the four the twenty-four
#: already carry. It was a hand-kept triple, which is how a family drifts from
#: the tuple every other family composes.
_POLAR_CONDITION_COLUMNS: tuple[str, ...] = tuple(
    name for name in FLIGHT_CONDITION_COLUMNS if name not in COEFFICIENT_COLUMNS
)


#: A polar table's columns: the polar, its description, the group, the
#: reference block, the condition the twenty-four do not carry, the
#: twenty-four coefficients.
#:
#: `POL` FIRST (G16), as in every table the post writes, under the
#: name the run matrix gives its polar column, and the ONLY column that states the
#: polar. in legacy releases this table named it `POLAR`, in the same first place; the
#: polar stated twice, once under each name, is one value a reader has to choose
#: between, so `POLAR` is gone from every table the post writes.
POLAR_COLUMNS: tuple[str, ...] = (
    POLAR_ID_COLUMN,
    "DESCRIPTION",
    "GROUP",
    *_REFERENCE_COLUMNS,
    *_POLAR_CONDITION_COLUMNS,
    *COEFFICIENT_COLUMNS,
)

#: THE PRODUCT COLUMNS OF A DRAG SPLIT, by the loads columns they are summed from
#: (FR-423), in the order the twenty-four place them: the profile or viscous part,
#: then the induced or pressure part. Up to 26.124 the loads table prints
#: ``CDi, CDo`` and the polar writes ``CD0, CDI``; 26.125 prints ``CDp, CDv``
#: (FSM-26.125 pp.227, 229) and the polar writes ``CDV, CDP`` in the same two
#: places. Each pair is carried under its own names: nothing here says the two
#: splits measure the same quantities. A table holding rows of both builds
#: carries both pairs, the absent one ``NA`` in each row.
DRAG_PRODUCT_COLUMNS: dict[tuple[str, str], tuple[str, str]] = {
    DRAG_PAIRS[0]: (COEFFICIENT_COLUMNS[-2], COEFFICIENT_COLUMNS[-1]),
    DRAG_PAIRS[1]: ("CDV", "CDP"),
}

#: The split every build up to 26.124 prints, and the two cells of a split a
#: row's loads table did not print.
_LEGACY_DRAG: tuple[str, str] = DRAG_PRODUCT_COLUMNS[DRAG_PAIRS[0]]
_NA_PAIR: tuple[float, float] = (math.nan, math.nan)


def _drag_kinds(owned: Sequence[tuple[str, str]]) -> list[tuple[str, str]]:
    """Return the splits a table's rows carry, in the order of :data:`DRAG_PRODUCT_COLUMNS`."""
    return [kind for kind in DRAG_PRODUCT_COLUMNS.values() if kind in owned] or [_LEGACY_DRAG]


def drag_columns_of(loads: LoadsReport) -> tuple[str, str]:
    """Return the product columns of the drag split a loads table prints (FR-423).

    Parameters
    ----------
    loads : LoadsReport
        The parsed loads table.

    Returns
    -------
    tuple of str
        ``("CD0", "CDI")`` up to 26.124, ``("CDV", "CDP")`` on 26.125.
    """
    return DRAG_PRODUCT_COLUMNS[drag_pair(loads.total)]


def drag_columned_rows(
    rows: Sequence[Sequence[float]], drag_columns: Sequence[tuple[str, str]] | None = None
) -> tuple[tuple[str, ...], list[tuple[float, ...]]]:
    """Return the coefficient columns of a polar table and its rows under them (FR-423).

    Every row of ``rows`` is twenty-four values wide, :func:`polar_row`'s, its
    last two the drag split of its own loads table. A table whose rows all
    carry one split names the last two columns after it, ``CD0, CDI`` or
    ``CDV, CDP``, and its rows are unchanged. A table holding both carries both
    pairs, in the order of :data:`DRAG_PRODUCT_COLUMNS`, each row ``NA`` (NaN)
    under the pair its loads table did not print, never zero.

    Parameters
    ----------
    rows : sequence of sequence of float
        The coefficient rows, each :func:`polar_row`'s.
    drag_columns : sequence of tuple of str, optional
        The product columns of each row's split, :func:`drag_columns_of` of its
        loads table; None is ``CD0, CDI`` for every row.

    Returns
    -------
    tuple
        The coefficient column names and the rows written under them.

    Raises
    ------
    ProductError
        If ``drag_columns`` does not hold one entry per row.
    """
    owned = [_LEGACY_DRAG] * len(rows) if drag_columns is None else list(drag_columns)
    if len(owned) != len(rows):
        raise ProductError(
            f"the polar table was given {len(owned)} drag split(s) for {len(rows)} rows"
        )
    kinds = _drag_kinds(owned)
    columns = (*COEFFICIENT_COLUMNS[:-2], *(name for kind in kinds for name in kind))
    if len(kinds) == 1:
        return columns, [tuple(row) for row in rows]
    widened = [
        (
            *row[:-2],
            *(value for kind in kinds for value in (row[-2:] if kind == own else _NA_PAIR)),
        )
        for row, own in zip(rows, owned, strict=True)
    ]
    return columns, widened


def polar_table_columns(drag_columns: Sequence[tuple[str, str]] | None = None) -> tuple[str, ...]:
    """Return the columns of a polar table whose rows carry these drag splits (FR-423).

    Parameters
    ----------
    drag_columns : sequence of tuple of str, optional
        The product columns of each row's split; None is :data:`POLAR_COLUMNS`.

    Returns
    -------
    tuple of str
        :data:`POLAR_COLUMNS` with its last two columns named after the splits.
    """
    kinds = _drag_kinds(list(drag_columns or ()))
    return (*POLAR_COLUMNS[:-2], *(name for kind in kinds for name in kind))


# Recorded-export source: RPT-063, "emitted coefficients are scored against the
# solver's own recorded output" (2026-09-23), oracle inventory and .01.02.
# It identifies the hashed Total-row fixture used for the comparisons below.
@dataclass(frozen=True)
class GroupCoefficients:
    """The coefficients of one group, summed over its families, as the solver reports them.

    ``lift`` and ``drag`` are the solver's OWN integrals, ``CL`` and
    ``CDi + CDo``, and ``side`` its ``Cy``; ``roll``, ``pitch`` and ``yaw`` are
    the BODY-axis moments, ``roll`` and ``yaw`` already scaled from the chord to
    the span and carrying the reference sign.

    ``force`` and ``moment`` are the VECTORS the export states in its own
    frame, ``(Cx, Cy, Cz)`` and ``(CMx, CMy, CMz)``, summed over the same
    families. They are what :func:`polar_row` builds the axis columns from; the solver's own
    ``CL`` is between 0.10 and 0.25 per cent above the
    projection of that vector on 27 of the 28 lifting recorded exports (lift above
    0.05); one sits at 0.71 per cent. See
    ``tests/tier1_offline/fixtures/recorded_total_rows.csv``. A row built from one
    and printed beside the other did not agree with itself.

    NOTHING IN THE PACKAGE READS ``drag``, ``side``, ``lift``, ``roll``,
    ``pitch`` OR ``yaw``. They stay for a caller that wants the
    solver's own integrals, and they are the source of NO axis column of any
    product: ``lift`` is the solver's ``CL``, which a polar no longer prints.
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
    force: tuple[float, float, float] | None = None
    moment: tuple[float, float, float] | None = None
    #: The product columns ``drag_profile`` and ``drag_induced`` are written under
    #: (FR-423): ``CD0, CDI`` up to 26.124, ``CDV, CDP`` on 26.125.
    drag_columns: tuple[str, str] = (COEFFICIENT_COLUMNS[-2], COEFFICIENT_COLUMNS[-1])


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
    #: The state THIS point resolved to: its Mach, its row cell with the
    #: swept value in place, its air. None on a caller that builds a point by
    #: hand, which then states the simulation's.
    state: PointState | None = None
    #: The induced-drag boundary selection the point's run RECORDED
    #: (``SET_VORTICITY_DRAG_BOUNDARIES``: ``"all"``, a list of 1-based boundary
    #: indices, or the empty default), read by :func:`declined_induced_drag`.
    #: None where no record is at hand, which declines nothing.
    vorticity_selection: object = None

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
    declined: Collection[str] = (),
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
    False here on purpose . The reference
    decision of that day is about the ARTIFACT: a ``[groups]`` entry
    written empty is every family, and the products stage passes True
    for it. A Python caller that built ``families`` by filtering and got
    an empty list still sums to zero, which is what this function did
    before and what its docstring promised.

    ``declined`` names the surfaces whose induced drag the solver did not
    compute (PFS-2006.03, FR-22a), as :func:`declined_induced_drag` finds them.
    A member among them makes ``drag_induced`` and ``drag`` NaN, which every
    CSV product writes as `NA`: its printed ``CDi`` of zero is not a zero, and a sum
    that took it as one would be a number a reader believes. ``force`` keeps the
    printed ``Cx``; a NaN there would reach, through the turn, columns the x
    force does not touch, so :func:`polar_row` masks exactly the ones it does.

    Parameters
    ----------
    loads : LoadsReport
        The parsed loads table, one row per surface.
    families : sequence of int or str
        The group's members: surface names, aliases or families.
    bref_m : float
        Reference span in metres, which the rolling and yawing moments are
        scaled to.
    aliases : mapping of str to sequence of str, optional
        The boundary aliases a member may name.
    empty_is_every : bool, optional
        Whether an empty ``families`` means every surface; False sums to zero.
    declined : collection of str, optional
        The surfaces whose induced drag was not computed.

    Returns
    -------
    GroupCoefficients
        The summed coefficients and the names of the surfaces summed.

    Raises
    ------
    ProductError
        If the loads table states no reference length.
    """
    cref = loads.reference_length
    if cref is None:
        raise ProductError("the loads table states no reference length, so no span scaling")
    drag = side = lift = roll = pitch = yaw = profile = induced = 0.0
    force = [0.0, 0.0, 0.0]
    moment = [0.0, 0.0, 0.0]
    used: list[str] = []
    selected: list[str] = []
    if families or empty_is_every:
        selected = select_group_members(families, list(loads.surfaces), aliases, strict=False)
    # THE SPLIT AS THE TABLE PRINTS IT (FR-423): ``CDi, CDo`` up to 26.124,
    # ``CDp, CDv`` on 26.125, never one read under the other's name.
    induced_key, profile_key = drag_pair(loads.total)
    for family in selected:
        row = loads.surfaces[family]
        used.append(family)
        # NOT COMPUTED IS NOT ZERO (PFS-2006.03): the printed 0.0 of a declined
        # surface stays in the parsed table, and no sum made here takes it.
        cdi = math.nan if family in declined else row[induced_key]
        # THE TOTAL DRAG IS THE SUM OF THE SPLIT ON EITHER BUILD: FSM-26.124 p.227
        # states it of CDi and CDo, FSM-26.125 p.229 of CDp and CDv (FR-423).
        drag += cdi + row[profile_key]
        side += row["Cy"]
        lift += row["CL"]
        roll -= row["CMx"] * cref / bref_m
        pitch += row["CMy"]
        yaw -= row["CMz"] * cref / bref_m
        profile += row[profile_key]
        induced += cdi
        for at, (f, m) in enumerate((("Cx", "CMx"), ("Cy", "CMy"), ("Cz", "CMz"))):
            force[at] += row[f]
            moment[at] += row[m]
    return GroupCoefficients(
        drag, side, lift, roll, pitch, yaw, profile, induced, tuple(used),
        force=(force[0], force[1], force[2]),
        moment=(moment[0], moment[1], moment[2]),
        drag_columns=DRAG_PRODUCT_COLUMNS[(induced_key, profile_key)],
    )  # fmt: skip


def declined_induced_drag(loads: LoadsReport, selection: object) -> tuple[str, ...]:
    """Return the surfaces whose induced drag the solver did not compute, in table order.

    PFS-2006.03, FR-22a. A boundary on the vorticity induced-drag list
    (``SET_VORTICITY_DRAG_BOUNDARIES``) without a defined trailing edge is not
    computed, and the export prints its ``CDi`` as zero (FSM-26.120 p.202). A
    surface is declined when ``selection`` puts it on that list AND its printed
    ``CDi`` is exactly ``0.0``. The list is what decides, not the zero: a body
    left off it is integrated by surface pressure and can print a real zero.

    ``selection`` is the value the run record keeps for that command: ``"all"``
    (the ``-1`` the script emits) is every surface; a list of 1-based boundary
    indices is those surfaces, boundary ``i`` read as the table's ``i``-th
    surface row, since the export prints one row per boundary in the order the
    geometry numbers them: measured on 40 recorded exports of 11 geometries,
    four of them with several boundaries, every table in its inventory's order
    (``reports/probes/PFS-2006-03_2026-09-24_row-order.yaml``). Resolving the
    index through the boundary names each run records (``RunRecord.inventory``, R03), rather
    than through the table's order, is
    the stronger reading; the record now exists, and reading the index
    through it is not done here yet and remains unimplemented. A list holding
    anything the table cannot place -- a label, a bool, an index out of
    range -- is read as every surface, because a false `NA` is loud and a
    false zero is a number a reader believes. The empty default, None and
    anything else decline nothing.

    A trailing-edged surface whose induced drag rounds to zero at the printed
    precision is declined too; ``SET_SIGNIFICANT_DIGITS`` narrows that band.

    Parameters
    ----------
    loads : LoadsReport
        The parsed loads table, one row per surface in the solver's order.
    selection : object
        The recorded value of ``SET_VORTICITY_DRAG_BOUNDARIES``: ``"all"``, a
        list of 1-based boundary indices, or an empty or other value.

    Returns
    -------
    tuple of str
        The names of the declined surfaces, in table order; empty when none.
    """
    # THE RULE READS CDi ONLY (FR-423). A table printing the 26.125 split
    # declines nothing here; its CDp zero is said by declined_profile_drag_125.
    if DRAG_PAIRS[0][0] not in loads.total:
        return ()
    names = list(loads.surfaces)
    listed = _on_the_vorticity_list(names, selection)
    return tuple(name for name in names if name in listed and loads.surfaces[name]["CDi"] == 0.0)


# The vector/integral comparison uses the same RPT-063 (2026-09-23) Total-row
# evidence identified above GroupCoefficients, including its four sideslip rows.
def polar_row(
    alpha_deg: float,
    mach: float,
    reynolds_millions: float,
    coefficients: GroupCoefficients,
    *,
    cref_m: float,
    bref_m: float,
    beta_deg: float | None = None,
) -> tuple[float, ...]:
    """Return the twenty-four coefficient values of one polar row.

    EVERY AXIS COLUMN COMES FROM ONE VECTOR: the force ``(Cx, Cy, Cz)`` and
    the moment ``(CMx, CMy, CMz)`` the export states in its own frame, turned by
    :func:`pyflightstream.post.axes.polar_axis_coefficients`. So ``CDB`` IS the
    ``Cx`` of the export and ``CLB`` its ``Cz``, and the wind-axis drag of that
    vector is the ``CDi + CDo`` the solver integrates, which the recorded exports
    confirm to their printed precision, under sideslip too.

    in legacy releases the row took the solver's ``CL`` and ``CDi + CDo`` as
    stability-axis forces and turned them BACK to body axes. The solver's ``CL``
    sits between 0.10 and 0.25 per cent above the projection of its own vector on
    27 of the 28 lifting recorded exports (lift above 0.05); one sits at 0.71 per cent.
    See ``tests/tier1_offline/fixtures/recorded_total_rows.csv``. ``CLS`` and
    ``CLW`` fall by the measured gap against a table written before, and ``CDB`` and
    ``CLB`` now equal the columns printed beside them. A point under sideslip was
    refused; it is a row like any other, with ``BETA`` as the point flew it.

    ``CD0`` and ``CDI`` stay the solver's own profile and induced drag.

    Omitting ``beta_deg`` is deprecated and warns while retaining zero sideslip.
    It will be required at the next breaking window; pass the point's sideslip explicitly.
    Both measured vectors must be supplied; absent vectors are never measured zeros.

    AN INDUCED DRAG THE SOLVER DECLINED (PFS-2006.03) is ``CDI`` NaN, and so is
    every axis column the x force reaches at this point's angles: the export's
    ``Cx`` holds the same ``CDi`` the solver printed as zero (its wind-axis drag
    IS ``CDi + CDo``), so it is short by exactly what was not computed. The
    columns it does not reach, the moments and ``CLB`` among them, keep their
    numbers.

    Parameters
    ----------
    alpha_deg : float
        Angle of attack in degrees.
    mach : float
        Mach number of the point.
    reynolds_millions : float
        Reynolds number in millions.
    coefficients : GroupCoefficients
        The group's summed coefficients, from :func:`group_coefficients`.
    cref_m : float
        Reference chord in metres.
    bref_m : float
        Reference span in metres.
    beta_deg : float, optional
        Sideslip angle in degrees; omission warns and currently uses zero.

    Returns
    -------
    tuple of float
        The values under the coefficient columns of the polar table: the two
        angles, Mach, Reynolds, the axis coefficients, then ``CD0`` and
        ``CDI``.

    Raises
    ------
    ProductError
        If either measured force or moment vector is absent.
    """
    g = coefficients
    if beta_deg is None:
        warn(
            "Omitting beta_deg from polar_row is deprecated; pass beta_deg explicitly. "
            "It will be required at the next breaking window; zero is used for now.",
            PyflightstreamDeprecationWarning,
            stacklevel=2,
        )
        beta_deg = 0.0
    if g.force is None or g.moment is None:
        raise ProductError("polar_row needs measured force and moment vectors; supply both")
    axes = polar_axis_coefficients(
        g.force, g.moment, alpha_deg, beta_deg, cref_m=cref_m, bref_m=bref_m
    )
    if math.isnan(g.drag_induced):
        reach = polar_axis_coefficients(
            (1.0, 0.0, 0.0), (0.0, 0.0, 0.0), alpha_deg, beta_deg, cref_m=cref_m, bref_m=bref_m
        )
        axes = tuple(math.nan if r != 0.0 else a for a, r in zip(axes, reach, strict=True))
    return (alpha_deg, beta_deg, mach, reynolds_millions, *axes, g.drag_profile, g.drag_induced)


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

    Parameters
    ----------
    points : sequence of mapping of str to float
        The sweep points, each holding some of ``alpha``, ``beta`` and
        ``advance_ratio``.

    Returns
    -------
    tuple of str
        The axes whose values differ across the points, in the order of
        :data:`SWEEP_AXES`.
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
    """``P<sim>-<name>_<group>.csv``, the group NAMED (FR-85).

    ``name`` is the recorded sweep name, each swept field written
    ``<code>+sweep``, for a table over a sweep
    (``P0001-M150AL+000BE+000J+sweep_PUSHER.csv``), and the recorded point name
    for a case whose sweep resolved to one point. The ``.dat`` of the custom
    format takes the same stem, which is what ``suffix`` is for.

    A NUMBERED group still writes ``_g01``, because a workspace recorded in legacy releases
    holds those files and a pproc that still numbers its groups must keep
    producing the names beside them rather than a second era of its own.

    Groups may be names as well as numbers (item 14). Preserve the named
    form instead of forcing integer conversion and raising an uncontextualised
    ValueError outside the product-refusal handling.

    Parameters
    ----------
    sim : str
        The simulation identifier the name opens with.
    name : str
        The recorded sweep or point name.
    group : str or int
        The pproc group, named or numbered.
    suffix : str, optional
        The file extension, with its dot.

    Returns
    -------
    str
        The file name, without a directory.
    """
    return f"{sweep_file_stem(sim, name)}_{group_token(group)}{suffix}"


#: The analysis frames whose axes are the GEOMETRY's, so a force stated in them
#: may be projected on a shaft and rotated into wind axes.
#:
#: `MRP` IS IN THE LIST AND WAS LEFT OUT, and leaving it out would have denied
#: `ETAW` on exactly the campaign item 6 exists for. This package POINTS THE
#: ANALYSIS AT MRP ITSELF whenever the reference states a moment point
#: (`cases.workflows._frames._moment_frame`, then `_analysis(loads_frame=...)`), and it
#: builds that frame with `x_axis = (1,0,0)` and `y_axis = (0,1,0)` -- the origin
#: moves and the AXES DO NOT. A pure translation leaves every force direction
#: unchanged, so the rotation is valid in it.
#:
#: MY COMMENT HERE SAID "measured across the recorded exports of these
#: workspaces: every one prints `Reference`". THAT WAS FALSE and it is the worst
#: kind of false: I read the sections and force-distribution fixtures and wrote
#: the sentence as though I had read the loads ones. The unsteady loads fixture
#: prints `MRP` on line 21, and so does every loads fixture of the rotor tests.
#: The V&V lens of the closing round read the file I claimed to have read.
#:
#: IT IS A NAME CHECK AND THAT IS A LIMITATION, not a measurement. It admits the
#: frames THIS PACKAGE creates as translations of the geometry and refuses
#: everything else -- including a rotor's own `<ALIAS>_SMRP`, whose axes really
#: are turned, and including a user's created frame whatever its axes. The
#: question it stands for is "is this frame rotated relative to the geometry",
#: and a name cannot answer that. What makes it safe is the DIRECTION of its
#: error: an unknown frame is refused, never silently accepted.
GEOMETRY_ANALYSIS_FRAMES = frozenset({"reference", "global", "geometry", "mrp"})


def polar_table_rows(
    *,
    polar: str | int,
    description: str,
    group: str | int,
    reference: ReferenceValues,
    rows: Sequence[Sequence[float]],
    advance_ratios: Sequence[float | None] | None = None,
    conditions: Sequence[Mapping[str, object]] | None = None,
    drag_columns: Sequence[tuple[str, str]] | None = None,
) -> list[tuple[object, ...]]:
    """Assemble the rows of one polar table, each under :func:`polar_table_columns`.

    ``conditions`` is the flight condition of each row, in the row order, for
    the columns the twenty-four coefficients do NOT carry: ``VINF``, ``ALT``
    and the advance ratio. A key a run did not record arrives as ``NA`` rather
    than as a blank or a zero. ``advance_ratios`` remains accepted and means
    the same as a ``conditions`` sequence carrying only ``J``; giving both is
    refused rather than silently preferring one, because a caller that states
    the ratio twice has two sources for it and this function cannot know which
    is current.

    The writer and superfile share this assembly so labels and values use the same column order.

    Parameters
    ----------
    polar : str or int
        The polar's identifier, written as ``POL`` in every row.
    description : str
        Free text describing the polar, written in every row.
    group : str or int
        The pproc group the rows belong to.
    reference : ReferenceValues
        The reference lengths and moment point, written in every row.
    rows : sequence of sequence of float
        The coefficient values of each point, as :func:`polar_row` returns
        them.
    advance_ratios : sequence of float or None, optional
        The advance ratio of each row; None entries read ``NA``.
    conditions : sequence of mapping, optional
        The flight condition of each row, in row order.
    drag_columns : sequence of tuple of str, optional
        The product columns of each row's drag split (FR-423,
        :func:`drag_columned_rows`); None is ``CD0, CDI`` for every row.

    Returns
    -------
    list of tuple
        One full row per input row, ready under :data:`POLAR_COLUMNS`.

    Raises
    ------
    ProductError
        If both ``advance_ratios`` and ``conditions`` are given, the number
        of conditions differs from the number of rows, or a row does not
        hold one value per coefficient column.
    """
    if advance_ratios is not None and conditions is not None:
        raise ProductError(
            "the polar table was given both advance_ratios and conditions, which "
            "are two sources for the same column; pass the advance ratio inside "
            "conditions as 'J' and drop advance_ratios"
        )
    # THE POLAR ONCE, as `POL`, the first column every table opens with (G16).
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
    for row in rows:
        if len(row) != len(COEFFICIENT_COLUMNS):
            raise ProductError(f"a polar row has {len(row)} values, not {len(COEFFICIENT_COLUMNS)}")
    _columns, named = drag_columned_rows(rows, drag_columns)
    return [
        (*lead, *context_row(state, columns=_POLAR_CONDITION_COLUMNS), *row)
        for row, state in zip(named, states, strict=True)
    ]


def write_polar_table(
    path: str | Path,
    *,
    polar: str | int,
    description: str,
    group: str | int,
    reference: ReferenceValues,
    rows: Sequence[Sequence[float]],
    advance_ratios: Sequence[float | None] | None = None,
    conditions: Sequence[Mapping[str, object]] | None = None,
    drag_columns: Sequence[tuple[str, str]] | None = None,
) -> Path:
    """Write one polar table: the reference block and the coefficients per point.

    ``advance_ratios`` is the advance ratio of each row in the row order,
    for :data:`ADVANCE_RATIO_COLUMN` (FR-85); a row whose ratio is not
    known writes :data:`NOT_APPLICABLE` rather than a zero, because zero is
    a value a rotor row can have and "not recorded" is not it. Omitted
    entirely, every row's cell reads `NA`, which is what a caller with no
    sweep point to offer should write.

    Pass ``conditions=[{"VINF": 23.0, "ALT": 150.0, "J": 0.4}]`` for a
    single row's speed in m/s, altitude in m and advance ratio. For multiple
    rows, supply one mapping per row. Inapplicable values use ``NA`` so a
    missing quantity cannot be mistaken for a measured zero.

    Parameters
    ----------
    path : str or Path
        Destination file.
    polar : str or int
        The polar's identifier, written as ``POL`` in every row.
    description : str
        Free text describing the polar, written in every row.
    group : str or int
        The pproc group the rows belong to.
    reference : ReferenceValues
        The reference lengths and moment point, written in every row.
    rows : sequence of sequence of float
        The coefficient values of each point, as :func:`polar_row` returns
        them.
    advance_ratios : sequence of float or None, optional
        The advance ratio of each row; None entries read ``NA``.
    conditions : sequence of mapping, optional
        Per-row flight conditions, forwarded to :func:`polar_table_rows`.
        Supply J here instead of passing advance_ratios at the same time.
    drag_columns : sequence of tuple of str, optional
        The product columns of each row's drag split (FR-423); None is
        ``CD0, CDI`` for every row.

    Returns
    -------
    Path
        The file written.

    Raises
    ------
    ProductError
        As :func:`polar_table_rows`: a row of the wrong width or an
        advance-ratio count that differs from the rows.
    """
    full = polar_table_rows(
        polar=polar,
        description=description,
        group=group,
        reference=reference,
        rows=rows,
        advance_ratios=advance_ratios,
        conditions=conditions,
        drag_columns=drag_columns,
    )
    return write_csv_table(path, polar_table_columns(drag_columns), full)


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


def group_polar_rows(
    points: Sequence[PolarPoint],
    families: Sequence[int | str],
    *,
    mach: float,
    reference: ReferenceValues,
    aliases: Mapping[str, Sequence[str]] | None = None,
) -> list[tuple[float, ...]]:
    """Return the coefficient rows of one group over the points of a polar, in the given order.

    This is the ARTIFACT's path, so an empty member list is every family
    and the summer is asked for that reading.
    A surface whose induced drag the point's record says the solver declined
    is `NA` in the sum (:func:`declined_induced_drag`, PFS-2006.03). Public
    (AD-13): the simulation stage and :func:`write_recorded_polar`
    build a group's rows through it, and so may a product over the polar rows.

    Parameters
    ----------
    points : sequence of PolarPoint
        The points of the polar, in the order their rows are wanted.
    families : sequence of int or str
        The group's members: surface families, aliases or indices; empty is
        every family.
    mach : float
        The simulation's Mach number, for a point that states none of its own.
    reference : ReferenceValues
        The reference lengths the moments are normalised by.
    aliases : mapping of str to sequence of str, optional
        The boundary aliases a member may name.

    Returns
    -------
    list of tuple of float
        One :func:`polar_row` per point.

    Raises
    ------
    ProductError
        When a point's loads are in a frame other than the geometry's axes,
        or state no Reynolds number.
    """
    rows = []
    for point in points:
        frame = point.loads.frame
        if frame is None or frame.strip().casefold() not in GEOMETRY_ANALYSIS_FRAMES:
            raise ProductError(
                f"{point.loads_path} states analysis frame {frame!r}; polar axes require "
                "vectors in the geometry's axes, and this frame's rotation is unknown"
            )
        reynolds = point.loads.reynolds
        if reynolds is None:
            raise ProductError(f"{point.loads_path} states no Reynolds number")
        coefficients = group_coefficients(
            point.loads,
            list(families),
            bref_m=reference.bref_m,
            aliases=aliases,
            empty_is_every=True,
            declined=declined_induced_drag(point.loads, point.vorticity_selection),
        )
        rows.append(
            polar_row(
                point.alpha_deg,
                _mach_of(point, mach),
                reynolds / 1e6,
                coefficients,
                cref_m=reference.cref_m,
                bref_m=reference.bref_m,
                # Transform using the sideslip the point flew at.
                beta_deg=point.beta_deg,
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

    The point folders carry no run record, so nothing here knows which
    boundaries were on the vorticity induced-drag list: every printed ``CDi``
    is summed as printed, a zero included. The campaign stage, which holds the
    record, writes `NA` for an induced drag the solver declined (PFS-2006.03).

    Parameters
    ----------
    polar_dir : str or Path
        The ``POLAR-<n>`` folder of point folders.
    out_dir : str or Path
        Folder the products are written under.
    groups : mapping of str to sequence of str
        The pproc ``[groups]`` table: group name to its families.
    reference : mapping of str to float or ReferenceValues
        The reference lengths and moment point of the run.
    description : str
        Free text describing the polar, written in every row.
    mach : float
        The simulation's Mach number.
    sections : bool, optional
        Whether to write a sections table for each point that has sectional
        loads.
    plots : bool, optional
        Whether to write a plots table for each point that has a plots export.
    aliases : mapping of str to sequence of str, optional
        The boundary aliases a group member may name.

    Returns
    -------
    list of Path
        The files written, in order.

    Raises
    ------
    ProductError
        If a point's loads table cannot be read, the folder holds no point, or
        a point's loads are in a frame other than the geometry's axes or state
        no Reynolds number. A reference that differs from the one the export
        printed is not refused here: it is warned, naming both numbers, and the
        products are written, as the default warning policy states.
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
    _refuse_a_reference_the_solver_did_not_use(polar, points, ref)
    written: list[Path] = []
    for group, families in groups.items():
        written.append(
            write_polar_table(
                out / polar_file_name(polar, mach, group),
                polar=polar,
                description=description,
                group=group,
                reference=ref,
                rows=group_polar_rows(
                    points, list(families), mach=mach, reference=ref, aliases=aliases
                ),
                drag_columns=[drag_columns_of(point.loads) for point in points],
            )
        )
    for point in points:
        folder = point.loads_path.parent
        sloads = folder / f"{point.name}_sloads.txt"
        if sections and sloads.is_file():
            target = write_sections_table(
                out / SECTIONS_DIR / f"{point.name}_sections.csv",
                sloads.read_text(encoding="utf-8", errors="replace"),
                # The filename identifies the polar. Read iteration and azimuth from
                # the export where stated, otherwise write NA, including steady
                # distributions and records with no clock.
                mach=mach,
                # ITEM 5. This path rebuilds from a bare folder of recorded
                # loads files and reaches no run record, so the advance ratio
                # is not available here and is NOT invented: the reference is
                # what this caller has, and it is what a coefficient most needs
                # beside it.
                reference=ref,
                pol=polar,
            )
            if target is not None:
                written.append(target)
        plots_export = folder / f"{point.name}_plots.txt"
        if plots and plots_export.is_file():
            target = write_plots_table(
                out / PROBES_DIR / f"{point.name}_plots.csv",
                plots_export.read_text(encoding="utf-8", errors="replace"),
                pol=polar,
            )
            if target is not None:
                written.append(target)
    return written


def selected_axes(path: Path, axes: Literal["wind", "stability"] | None) -> None:
    """Append selected force coefficients while keeping explicitly labelled frame columns."""
    if axes is None:
        return
    with path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or ())
        rows = list(reader)
    suffix = "W" if axes == "wind" else "S"
    quantities = {"CD": "drag", "CY": "side_force", "CL": "lift"}
    groups = [
        column[len("CD" + suffix) :] for column in columns if column.startswith(f"CD{suffix}_")
    ]
    if f"CD{suffix}" in columns:
        groups.insert(0, "")
    required = {quantity + suffix + group for group in groups or [""] for quantity in quantities}
    if not required.issubset(columns):
        raise ValueError(f"{path}: polar axes require {sorted(required)}")
    selected = {
        (f"selected_{physical}_coefficient{group}" if group else quantity): quantity
        + suffix
        + group
        for group in groups
        for quantity, physical in quantities.items()
    }
    added = [*selected, "polar_axes"]
    if collisions := set(added).intersection(columns):
        raise ValueError(
            f"{path}: selected polar axes would replace existing columns {sorted(collisions)}"
        )
    for row in rows:
        row.update({name: row[source] for name, source in selected.items()})
        row["polar_axes"] = axes
    with _textio.open_text(path, "w") as handle:
        writer = _textio.csv_dict_writer(handle, fieldnames=[*columns, *added])
        writer.writeheader()
        writer.writerows(rows)


#: FR-2302: what a trimmed polar zeroes and what it moves. The pitching moment of
#: the polar's body axes about the reference point (``CMB25``; the stability axes'
#: ``CMS25`` is the same moment, both turn about ``y``) and the angle of attack.
TRIM_MOMENT_COLUMN = "CMB25"
TRIM_ANGLE_COLUMN = "ALPHA"
#: The suffix a trimmed polar adds to the stem of the polar table it is read from.
TRIM_SUFFIX = "_trim"


def _trim_number(text: object) -> float | None:
    """Return a cell as a finite number, or None (``NA``, text, blank, NaN)."""
    try:
        number = float(str(text).strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def trimmed_polar_row(
    columns: Sequence[str],
    rows: Sequence[Mapping[str, object]],
    *,
    moment: str = TRIM_MOMENT_COLUMN,
    angle: str = TRIM_ANGLE_COLUMN,
) -> dict[str, object]:
    """Return a polar's row at zero pitching moment, interpolated inside its sampled range.

    The rows are ordered by ``angle``; the pair of neighbouring rows whose
    ``moment`` changes sign brackets the trim, and every numeric column is
    interpolated linearly between them at the fraction ``m0 / (m0 - m1)`` of
    the way, so ``moment`` reads exactly zero (FR-2302). A row that states the
    zero itself is the trim. A text column keeps its value where both rows
    agree and reads ``NA`` where they do not; so does a numeric cell either
    row lacks. Nothing is extrapolated: a polar whose sampled moments do not
    change sign is refused (FR-2303), and so is one that changes sign more
    than once, because it has more than one trim and the table would have to
    choose.

    Parameters
    ----------
    columns : sequence of str
        The polar table's columns.
    rows : sequence of mapping
        The polar table's rows, by column (the text :func:`read_csv_table` reads).
    moment : str, optional
        The pitching-moment column, :data:`TRIM_MOMENT_COLUMN` by default.
    angle : str, optional
        The angle the trim moves, :data:`TRIM_ANGLE_COLUMN` by default.

    Returns
    -------
    dict of str to object
        The trimmed row by column; None where a cell is not available.

    Raises
    ------
    ProductError
        If ``moment`` or ``angle`` is not a column, fewer than two rows state
        both, the sampled moments do not bracket zero, or they cross it more
        than once.

    Examples
    --------
    >>> rows = [{"ALPHA": "0.0", "CMB25": "0.1", "CLB": "0.2"},
    ...         {"ALPHA": "4.0", "CMB25": "-0.1", "CLB": "0.6"}]
    >>> trimmed_polar_row(["ALPHA", "CMB25", "CLB"], rows)
    {'ALPHA': 2.0, 'CMB25': 0.0, 'CLB': 0.4}
    """
    for name in (moment, angle):
        if name not in columns:
            raise ProductError(
                f"the polar has no column {name!r}, which a trimmed polar reads; its "
                f"columns are {', '.join(columns)}"
            )
    stated = sorted(
        (
            (a, m, row)
            for row in rows
            if (a := _trim_number(row.get(angle))) is not None
            and (m := _trim_number(row.get(moment))) is not None
        ),
        key=lambda item: item[0],
    )
    if len(stated) < 2:
        raise ProductError(
            f"a trimmed polar needs at least two rows that state {angle} and {moment}; "
            f"this polar has {len(stated)}"
        )
    bracket = _the_trim_bracket(stated, moment=moment, angle=angle)
    if len(bracket) == 1:
        point = bracket[0][2]
        return {name: _trim_cell(point.get(name), point.get(name), 0.0) for name in columns}
    (_, m0, first), (_, m1, second) = bracket
    fraction = m0 / (m0 - m1)
    trimmed = {name: _trim_cell(first.get(name), second.get(name), fraction) for name in columns}
    trimmed[moment] = 0.0
    return trimmed


_Stated = tuple[float, float, Mapping[str, object]]


def _the_trim_bracket(stated: Sequence[_Stated], *, moment: str, angle: str) -> tuple[_Stated, ...]:
    """Return the one pair of rows whose moment changes sign, or the one row stating zero.

    ``stated`` is ``(angle, moment, row)`` ordered by angle. No change of sign, or
    more than one, is refused (FR-2303): nothing is extrapolated and no trim is chosen.
    """
    brackets: list[tuple[_Stated, ...]] = []
    for low, high in zip(stated, stated[1:], strict=False):
        if low[1] == 0.0:
            brackets.append((low,))
        elif low[1] * high[1] < 0.0:
            brackets.append((low, high))
    if stated[-1][1] == 0.0:
        brackets.append((stated[-1],))
    if not brackets:
        moments = [item[1] for item in stated]
        raise ProductError(
            f"the sampled {moment} runs from {min(moments):.6g} to {max(moments):.6g} over "
            f"{angle} {stated[0][0]:.6g} to {stated[-1][0]:.6g} and never crosses zero, so "
            "the polar does not bracket the trim; extend the sweep past the angle where "
            "the pitching moment changes sign (a trimmed polar is never extrapolated)"
        )
    if len(brackets) > 1:
        where = ", ".join(f"{pair[0][0]:.6g}" for pair in brackets)
        raise ProductError(
            f"the sampled {moment} crosses zero {len(brackets)} times, at or after {angle} "
            f"{where}, so the polar has more than one trim and none is chosen; narrow the "
            "sweep to the range of the trim you mean"
        )
    return brackets[0]


def _trim_cell(first: object, second: object, fraction: float) -> object:
    """One cell of the trimmed row: equal cells as written, numbers interpolated, else None.

    Kept as written first, so an identifier such as ``POL`` or ``GROUP`` and a
    condition the sweep holds constant read exactly as in the polar.
    """
    if first == second and str(first).strip() not in ("", NOT_APPLICABLE):
        return first
    low, high = _trim_number(first), _trim_number(second)
    if low is not None and high is not None:
        return low + fraction * (high - low)
    return None


def write_trimmed_polar(
    polar: str | Path,
    out: str | Path | None = None,
    *,
    moment: str = TRIM_MOMENT_COLUMN,
    angle: str = TRIM_ANGLE_COLUMN,
    overwrite: bool = False,
) -> Path:
    """Write a polar table's trimmed polar: its row at zero pitching moment (FR-2302).

    The table is read back as written, :func:`trimmed_polar_row` finds the row,
    and the file has the polar's own columns and that one row, by default
    beside the polar as ``<polar stem>_trim.csv``. The pproc artifact asks for
    it beside every polar table with ``[products] trimmed_polar = true``.

    Parameters
    ----------
    polar : str or Path
        A polar table.
    out : str or Path, optional
        Where the trimmed polar is written; ``<polar stem>_trim.csv`` beside it
        by default.
    moment, angle : str, optional
        As :func:`trimmed_polar_row`.
    overwrite : bool, optional
        Replace a file already at ``out``.

    Returns
    -------
    Path
        The file written.

    Raises
    ------
    ProductError
        As :func:`trimmed_polar_row`, naming the polar.
    ProductExistsError
        If ``out`` exists and ``overwrite`` is not set.
    """
    source = Path(polar)
    target = Path(out) if out is not None else source.with_name(f"{source.stem}{TRIM_SUFFIX}.csv")
    if target.exists() and not overwrite:
        raise ProductExistsError(f"{target} already exists; pass overwrite=True to replace it")
    columns, rows = read_csv_table(source)
    try:
        row = trimmed_polar_row(columns, rows, moment=moment, angle=angle)
    except ProductError as error:
        raise ProductError(f"{source.name}: {error}") from error
    return write_csv_table(target, columns, [[row[name] for name in columns]])
