"""The polar: one row per point of a sweep, per boundary group, as a CSV table.

One of the product families of :mod:`pyflightstream.post` (AD-13, work
package WP5 of 0.33.0), written by the post stage of
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

The polar of the backlog's further kinds (a Richardson-extrapolated polar
over a mesh family, a trimmed polar) joins this module beside the table it
extends.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pyflightstream._errors import PyflightstreamError
from pyflightstream._tokens import POLAR_ID_COLUMN
from pyflightstream.cases import select_group_members
from pyflightstream.post._condition import (
    PointState,
    _mach_of,
    _refuse_a_reference_the_solver_did_not_use,
)
from pyflightstream.post._stage import PROBES_DIR, SECTIONS_DIR
from pyflightstream.post._tables import (
    _REFERENCE_COLUMNS,
    ADVANCE_RATIO_COLUMN,
    COEFFICIENT_COLUMNS,
    FLIGHT_CONDITION_COLUMNS,
    ProductError,
    ReferenceValues,
    context_row,
    polar_file_name,
    write_csv_table,
)
from pyflightstream.post.axes import polar_axis_coefficients
from pyflightstream.post.point_tables import write_plots_table, write_sections_table
from pyflightstream.results import LoadsReport, parse_loads
from pyflightstream.workspace.naming import group_token, sweep_file_stem

__all__ = [
    "GEOMETRY_ANALYSIS_FRAMES",
    "POLAR_COLUMNS",
    "SWEEP_AXES",
    "GroupCoefficients",
    "PolarPoint",
    "declined_induced_drag",
    "group_coefficients",
    "group_polar_rows",
    "polar_row",
    "polar_table_rows",
    "swept_axes",
    "swept_polar_file_name",
    "write_polar_table",
    "write_recorded_polar",
]

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
#: `POL` FIRST SINCE 0.27.0 (G16), as in every table the post writes, under the
#: name the run matrix gives its polar column, and the ONLY column that states the
#: polar. Until 0.26.x this table named it `POLAR`, in the same first place; the
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


@dataclass(frozen=True)
class GroupCoefficients:
    """The coefficients of one group, summed over its families, as the solver reports them.

    ``lift`` and ``drag`` are the solver's OWN integrals, ``CL`` and
    ``CDi + CDo``, and ``side`` its ``Cy``; ``roll``, ``pitch`` and ``yaw`` are
    the BODY-axis moments, ``roll`` and ``yaw`` already scaled from the chord to
    the span and carrying the reference sign.

    ``force`` and ``moment`` are the VECTORS the export states in its own
    frame, ``(Cx, Cy, Cz)`` and ``(CMx, CMy, CMz)``, summed over the same
    families. They are what :func:`polar_row` builds the axis columns from
    since 0.24.0; the solver's own ``CL`` is between 0.10 and 0.25 per cent above the
    projection of that vector on 27 of the 28 lifting recorded exports (lift above
    0.05); one sits at 0.71 per cent. See
    ``tests/tier1_offline/fixtures/recorded_total_rows.csv``. A row built from one
    and printed beside the other did not agree with itself.

    NOTHING IN THE PACKAGE READS ``drag``, ``side``, ``lift``, ``roll``,
    ``pitch`` OR ``yaw`` SINCE 0.24.0. They stay for a caller that wants the
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
    force: tuple[float, float, float] = (0.0, 0.0, 0.0)
    moment: tuple[float, float, float] = (0.0, 0.0, 0.0)


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
    #: The state THIS point resolved to (0.24.0): its Mach, its row cell with the
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
    False here on purpose (the interface lens of 2026-09-09). The reference
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
        selected = select_group_members(families, list(loads.surfaces), aliases)
    for family in selected:
        row = loads.surfaces[family]
        used.append(family)
        # NOT COMPUTED IS NOT ZERO (PFS-2006.03): the printed 0.0 of a declined
        # surface stays in the parsed table, and no sum made here takes it.
        cdi = math.nan if family in declined else row["CDi"]
        drag += cdi + row["CDo"]
        side += row["Cy"]
        lift += row["CL"]
        roll -= row["CMx"] * cref / bref_m
        pitch += row["CMy"]
        yaw -= row["CMz"] * cref / bref_m
        profile += row["CDo"]
        induced += cdi
        for at, (f, m) in enumerate((("Cx", "CMx"), ("Cy", "CMy"), ("Cz", "CMz"))):
            force[at] += row[f]
            moment[at] += row[m]
    return GroupCoefficients(
        drag, side, lift, roll, pitch, yaw, profile, induced, tuple(used),
        force=(force[0], force[1], force[2]),
        moment=(moment[0], moment[1], moment[2]),
    )  # fmt: skip


def declined_induced_drag(loads: LoadsReport, selection: object) -> tuple[str, ...]:
    """Return the surfaces whose induced drag the solver did not compute, in table order.

    PFS-2006.03, FR-22a. A boundary on the vorticity induced-drag list
    (``SET_VORTICITY_DRAG_BOUNDARIES``) without a defined trailing edge is not
    computed, and the export prints its ``CDi`` as zero (SRC-003 p.202). A
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
    index through the boundary names each run records since 0.27.0
    (``RunRecord.inventory``, R03), rather than through the table's order, is
    the stronger reading; the record now exists, and reading the index
    through it is not done here yet and is owed to 0.28.0. A list holding
    anything the table cannot place -- a label, a bool, an index out of
    range -- is read as every surface, because a false `NA` is loud and a
    false zero is a number a reader believes. The empty default, None and
    anything else decline nothing.

    A trailing-edged surface whose induced drag rounds to zero at the printed
    precision is declined too; ``SET_SIGNIFICANT_DIGITS`` narrows that band.
    """
    names = list(loads.surfaces)
    if isinstance(selection, str):
        listed = set(names) if selection == "all" else set()
    elif isinstance(selection, Sequence) and selection:
        placed = [
            names[item - 1]
            for item in selection
            if isinstance(item, int) and not isinstance(item, bool) and 1 <= item <= len(names)
        ]
        listed = set(placed) if len(placed) == len(selection) else set(names)
    else:
        return ()
    return tuple(name for name in names if name in listed and loads.surfaces[name]["CDi"] == 0.0)


def polar_row(
    alpha_deg: float,
    mach: float,
    reynolds_millions: float,
    coefficients: GroupCoefficients,
    *,
    cref_m: float,
    bref_m: float,
    beta_deg: float = 0.0,
) -> tuple[float, ...]:
    """Return the twenty-four coefficient values of one polar row.

    EVERY AXIS COLUMN COMES FROM ONE VECTOR (0.24.0): the force ``(Cx, Cy, Cz)`` and
    the moment ``(CMx, CMy, CMz)`` the export states in its own frame, turned by
    :func:`pyflightstream.post.axes.polar_axis_coefficients`. So ``CDB`` IS the
    ``Cx`` of the export and ``CLB`` its ``Cz``, and the wind-axis drag of that
    vector is the ``CDi + CDo`` the solver integrates, which the recorded exports
    confirm to their printed precision, under sideslip too.

    Until 0.24.0 the row took the solver's ``CL`` and ``CDi + CDo`` as
    stability-axis forces and turned them BACK to body axes. The solver's ``CL``
    sits between 0.10 and 0.25 per cent above the projection of its own vector on
    27 of the 28 lifting recorded exports (lift above 0.05); one sits at 0.71 per cent.
    See ``tests/tier1_offline/fixtures/recorded_total_rows.csv``. ``CLS`` and
    ``CLW`` fall by the measured gap against a table written before, and ``CDB`` and
    ``CLB`` now equal the columns printed beside them. A point under sideslip was
    refused; it is a row like any other, with ``BETA`` as the point flew it.

    ``CD0`` and ``CDI`` stay the solver's own profile and induced drag.

    AN OMITTED ``beta_deg`` ASSERTS ZERO SIDESLIP. The axes are turned by it, so
    a caller whose point flew at sideslip states it, or gets the row of a point
    that did not.

    AN INDUCED DRAG THE SOLVER DECLINED (PFS-2006.03) is ``CDI`` NaN, and so is
    every axis column the x force reaches at this point's angles: the export's
    ``Cx`` holds the same ``CDi`` the solver printed as zero (its wind-axis drag
    IS ``CDi + CDo``), so it is short by exactly what was not computed. The
    columns it does not reach, the moments and ``CLB`` among them, keep their
    numbers.
    """
    g = coefficients
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
    """``P<sim>-<name>_<group>.csv``, the group NAMED since 0.23.0 (FR-85).

    ``name`` is the recorded sweep name, each swept field written
    ``<code>+sweep``, for a table over a sweep
    (``P0001-M150AL+000BE+000J+sweep_PUSHER.csv``), and the recorded point name
    for a case whose sweep resolved to one point. The ``.dat`` of the custom
    format takes the same stem, which is what ``suffix`` is for.

    A NUMBERED group still writes ``_g01``, because a workspace recorded before
    0.23.0 holds those files and a pproc that still numbers its groups must keep
    producing the names beside them rather than a second era of its own.

    ``int(group)`` WAS UNCONDITIONAL HERE, which made item 14 unreachable: a
    named group raised a bare `ValueError` inside the products stage -- not even
    a `ProductError`, so `except PyflightstreamError` did not catch it and the
    refusal carried no file, no group and no fix. The matrix binder refused the
    same pproc one stage earlier, so the feature this release is named for was
    refused at BOTH ends.
    """
    return f"{sweep_file_stem(sim, name)}_{group_token(group)}{suffix}"


#: The analysis frames whose axes are the GEOMETRY's, so a force stated in them
#: may be projected on a shaft and rotated into wind axes.
#:
#: `MRP` IS IN THE LIST AND WAS LEFT OUT, and leaving it out would have denied
#: `ETAW` on exactly the campaign item 6 exists for. This package POINTS THE
#: ANALYSIS AT MRP ITSELF whenever the reference states a moment point
#: (`cases.workflows._moment_frame`, then `_analysis(loads_frame=...)`), and it
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
    """Return the coefficient rows of one group over the points of a polar, alpha ascending.

    This is the ARTIFACT's path, so an empty member list is every family
    (the design decision of 2026-09-09) and the summer is asked for that reading.
    A surface whose induced drag the point's record says the solver declined
    is `NA` in the sum (:func:`declined_induced_drag`, PFS-2006.03). Public
    since 0.33.0 (AD-13): the simulation stage and :func:`write_recorded_polar`
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
        if frame is not None and frame.strip().casefold() not in GEOMETRY_ANALYSIS_FRAMES:
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
                # AS THE POINT FLEW IT. A sideslip was a refusal until 0.24.0.
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
            )
        )
    for point in points:
        folder = point.loads_path.parent
        sloads = folder / f"{point.name}_sloads.txt"
        if sections and sloads.is_file():
            target = write_sections_table(
                out / SECTIONS_DIR / f"{point.name}_sections.csv",
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
