"""The polar: one row per point of a sweep, per boundary group, as a CSV table.

One of the product families of :mod:`pyflightstream.post` (AD-13, work
package WP5), written by the post stage of
:mod:`pyflightstream.post.products`, which re-exports the legacy product surface.
The interpolation writer is available directly from this domain module.

The polar files of a polar, the FAM files and one set of group files per boundary
GROUP under ``polars/`` (FR-88), are written by the post stage
(:mod:`pyflightstream.post._polar_stage`). This module holds what they share: a
point is a :class:`PolarPoint`, the axes a polar is swept over are measured by
:func:`swept_axes` (:data:`SWEEP_AXES`), and an induced drag the solver declined
to compute is named by :func:`declined_induced_drag` and summed as ``NA``. The
earlier table writers are refused by name (``docs/upgrading.md``).

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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pyflightstream._textio as _textio
from pyflightstream._deprecations import removed_names_hook
from pyflightstream._errors import InputValueError, PyflightstreamWarning, warn
from pyflightstream._tokens import NOT_APPLICABLE, POLAR_ID_COLUMN, plain_cell
from pyflightstream.post._condition import (
    PointState,
    _on_the_vorticity_list,
)
from pyflightstream.post._tables import (
    COEFFICIENT_COLUMNS,
    CONTEXT_COLUMNS,
    ProductError,
    ProductExistsError,
    read_csv_table,
    write_csv_table,
)
from pyflightstream.results import DRAG_PAIRS, LoadsReport

__all__ = [
    "DRAG_PRODUCT_COLUMNS",
    "GEOMETRY_ANALYSIS_FRAMES",
    "SWEEP_AXES",
    "PolarPoint",
    "declined_induced_drag",
    "farfield_column_names",
    "swept_axes",
    "GCI_SAFETY_FACTOR",
    "GridConvergence",
    "grid_convergence",
    "TRIM_ANGLE_COLUMN",
    "TRIM_MOMENT_COLUMN",
    "TRIM_SUFFIX",
    "trimmed_polar_row",
    "write_trimmed_polar",
    "write_interpolated_polar",
]


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
        raise InputValueError(f"{path}: polar axes require {sorted(required)}")
    selected = {
        (f"selected_{physical}_coefficient{group}" if group else quantity): quantity
        + suffix
        + group
        for group in groups
        for quantity, physical in quantities.items()
    }
    added = [*selected, "polar_axes"]
    if collisions := set(added).intersection(columns):
        raise InputValueError(
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


def _interpolated_row(
    columns: Sequence[str],
    rows: Sequence[Mapping[str, object]],
    axis: str,
    value: float,
) -> dict[str, object] | None:
    """Return the unique exact hit or strict adjacent bracket, in sweep order.

    Exact hits count once, even at an interior vertex. Repeated hits and multiple
    brackets are ambiguous. Missing axis cells break adjacency rather than bridge
    a gap. Sorting by the requested axis would erase branches and is never done.
    """
    coordinates = [_trim_number(row.get(axis)) for row in rows]
    matches = [(row, row, 0.0) for row, x in zip(rows, coordinates, strict=True) if x == value]
    for index, (low, high) in enumerate(zip(coordinates, coordinates[1:], strict=False)):
        if low is not None and high is not None and min(low, high) < value < max(low, high):
            matches.append((rows[index], rows[index + 1], (value - low) / (high - low)))
    if len(matches) != 1:
        return None
    first, second, fraction = matches[0]
    return {name: _trim_cell(first.get(name), second.get(name), fraction) for name in columns}


def write_interpolated_polar(
    polar: str | Path, target: str | Path, *, axis: str, values: Sequence[float]
) -> Path:
    """Write requested coordinates with POL then axis, warning once per unavailable row.

    Every numeric cell is linear in the selected coordinate. Text survives only
    when both bracket rows agree. Unavailable rows retain their requested axis
    value and common POL identity; all other cells are NA (FR-3343 to FR-3347).
    The caller prepares the destination using the existing product archive rule.

    Parameters
    ----------
    polar : str or Path
        Source polar CSV in sweep order.
    target : str or Path
        Destination CSV, replaced if it already exists.
    axis : str
        Numeric column used as the interpolation coordinate, in its recorded units.
    values : sequence of float
        Requested finite coordinates in output order and the axis column's units.

    Returns
    -------
    Path
        The written table, including warned NA rows where no unique bracket exists.

    Raises
    ------
    ProductError
        If the axis is absent or wholly nonnumeric. The campaign post catches
        this error and warns and skips only the requested product.
    """
    polar, target = Path(polar), Path(target)
    columns, source = read_csv_table(polar)
    if axis not in columns or not any(_trim_number(row.get(axis)) is not None for row in source):
        raise ProductError(
            f"{polar.name}: axis {axis!r} is not an available numeric polar column; "
            "choose a numeric column present in this table"
        )
    ordered = list(dict.fromkeys([POLAR_ID_COLUMN, axis, *columns]))
    identity = source[0].get(POLAR_ID_COLUMN) if source else None
    if any(row.get(POLAR_ID_COLUMN) != identity for row in source):
        identity = None
    output: list[list[object]] = []
    for value in values:
        row = _interpolated_row(columns, source, axis, value)
        if row is None:
            warn(
                f"{polar.name}: {axis}={value:g} has no unique interpolation bracket "
                "(outside the sweep, a gap, or multiple brackets); writing NA. "
                "Choose a value on a single sampled branch; nothing is extrapolated.",
                PyflightstreamWarning,
                stacklevel=2,
            )
            row = {name: None for name in ordered}
            row[POLAR_ID_COLUMN] = identity
        row[axis] = value
        output.append([row.get(name) for name in ordered])
    return write_csv_table(target, ordered, output)


#: NL-TRST-7: the safety factor of the grid convergence index of a three-level study.
GCI_SAFETY_FACTOR = 1.25


@dataclass(frozen=True)
class GridConvergence:
    """The numerical uncertainty of one result from a three-level refinement study (NL-TRST-7).

    The levels are ordered finest first: ``f1`` on the smallest representative
    size ``h1``. ``order`` is the observed order of convergence ``p``;
    ``extrapolated`` the Richardson extrapolation ``(r21^p f1 - f2) / (r21^p - 1)``;
    ``gci_fine`` the fine-level grid convergence index ``Fs e21 / (r21^p - 1)``,
    relative to ``f1`` (None where ``f1`` is zero); ``uncertainty`` the same band
    in the result's own units, ``Fs |f1 - f2| / (r21^p - 1)``, the numerical
    uncertainty ``u_num`` reported beside ``f1``. Three equal values give no order
    (None) and a zero band.
    """

    order: float | None
    extrapolated: float
    gci_fine: float | None
    uncertainty: float


def _observed_order(ratio: float, r21: float, r32: float) -> float:
    """Solve the observed order by fixed point, for any refinement ratios (Celik and others)."""
    order = math.log(ratio) / math.log(r21)
    for _ in range(200):
        shift = math.log((r21**order - 1.0) / (r32**order - 1.0)) if order > 0.0 else 0.0
        updated = (math.log(ratio) + shift) / math.log(r21)
        if abs(updated - order) <= 1e-12 * max(1.0, abs(updated)):
            return updated
        order = updated
    raise ProductError(
        f"the observed order does not settle (last {order:.6g}); the three levels are not in "
        "the asymptotic range"
    )


def grid_convergence(
    values: Sequence[float],
    spacings: Sequence[float],
    *,
    safety_factor: float = GCI_SAFETY_FACTOR,
) -> GridConvergence:
    """Estimate the discretization uncertainty of a result from three refinement levels.

    The procedure of the grid convergence index (Roache; Celik and others):
    the changes ``e21 = f2 - f1`` and ``e32 = f3 - f2`` between the levels and
    the ratios ``r21 = h2 / h1`` and ``r32 = h3 / h2`` give the observed order
    ``p``, solved by fixed point where the ratios differ; the result is
    extrapolated to ``h = 0`` and its fine-level band is the GCI. The same
    procedure serves a time-step study, the time steps as ``spacings``.

    Parameters
    ----------
    values : sequence of float
        ``f1, f2, f3``, the result on each level, finest first.
    spacings : sequence of float
        ``h1, h2, h3``, each level's representative size (a cell size or a
        time step), positive and increasing.
    safety_factor : float, optional
        ``Fs``, 1.25 for three levels; at least 1.

    Returns
    -------
    GridConvergence
        The observed order, the extrapolated value and the uncertainty band.

    Raises
    ------
    ProductError
        If there are not three finite values and three positive increasing
        spacings, if the changes alternate in sign or one of them is zero
        (oscillatory or stalled convergence, from which no order is
        estimated), or if the values move away with refinement.

    Examples
    --------
    >>> study = grid_convergence([1.5, 3.0, 9.0], [1.0, 2.0, 4.0])
    >>> study.order, study.extrapolated, study.uncertainty
    (2.0, 1.0, 0.625)
    """
    f = [float(value) for value in values]
    h = [float(spacing) for spacing in spacings]
    if len(f) != 3 or len(h) != 3 or not all(map(math.isfinite, [*f, *h])):
        raise ProductError(
            f"a refinement study needs three finite values and three finite spacings, finest "
            f"first; got values {list(values)} and spacings {list(spacings)}"
        )
    if not 0.0 < h[0] < h[1] < h[2] or not safety_factor >= 1.0:
        raise ProductError(
            f"the spacings {h} are not positive and increasing (finest first), or the safety "
            f"factor {safety_factor!r} is below 1"
        )
    e21, e32 = f[1] - f[0], f[2] - f[1]
    if e21 == 0.0 and e32 == 0.0:
        return GridConvergence(None, f[0], 0.0, 0.0)
    if e21 == 0.0 or e32 / e21 <= 0.0:
        raise ProductError(
            f"the changes between levels, {e21:.6g} then {e32:.6g}, are not of one sign: the "
            "convergence is oscillatory or stalled and no observed order is estimated from it"
        )
    order = _observed_order(e32 / e21, h[1] / h[0], h[2] / h[1])
    if not order > 0.0:
        raise ProductError(
            f"the values move away from each other as the levels are refined (observed order "
            f"{order:.6g}); the study does not converge"
        )
    growth = (h[1] / h[0]) ** order - 1.0
    band = safety_factor * abs(e21) / growth
    return GridConvergence(
        order=order,
        extrapolated=f[0] - e21 / growth,
        gci_fine=band / abs(f[0]) if f[0] != 0.0 else None,
        uncertainty=band,
    )


def farfield_column_names(
    rows: Sequence[tuple[tuple[object, ...], str]],
    columns: Sequence[str],
    *,
    declared_entries: Mapping[str, Sequence[str]] | None = None,
) -> list[dict[int, str]]:
    """Name each far-field cell by quantity, method and target (FR-1062).

    Parameters
    ----------
    rows : sequence
        Long-table rows paired with point names, after window selection.
    columns : sequence of str
        Columns following POL, ENTRY, step and the condition block.
    declared_entries : mapping, optional
        Entry names in declaration order for each method of this simulation row.
        Without declarations, use the row's table union and warn once (FR-3661).

    Returns
    -------
    list of dict
        One mapping from cell index to projected name per input row.
    """
    first = 3 + len(CONTEXT_COLUMNS)
    family, variant = (first + columns.index(name) for name in ("FAMILY", "VARIANT"))
    identities = [(str(row[variant]), str(row[1]), str(row[family])) for row, _ in rows]
    entries = {method: list(names) for method, names in (declared_entries or {}).items()}
    if rows and not any(entries.values()):
        warn(
            "far-field declared entries unavailable; naming columns from the row's table union",
            PyflightstreamWarning,
        )
        for method, entry, _ in sorted(set(identities)):
            if entry not in entries.setdefault(method, []):
                entries[method].append(entry)
    quantities = {
        first + index: column.replace("_T", "", 1)
        if column.startswith(("CL_T", "CDI_T", "CY_T", "E_T"))
        else column.replace("ETA_FF", "ETA")
        for index, column in enumerate(columns)
        if column not in ("FAMILY", "VARIANT", "STATUS")
    }
    # Reserve once for the row, never once per point. Declaration order and the
    # sorted union of each entry's targets also make missing exports immaterial.
    ordered = sorted(
        set(identities),
        key=lambda identity: (
            identity[0],
            entries.get(identity[0], []).index(identity[1])
            if identity[1] in entries.get(identity[0], [])
            else len(entries.get(identity[0], [])),
            identity[1],
            identity[2],
        ),
    )
    names = {}
    occupied: dict[str, str] = {}
    for method, entry, raw_target in ordered:
        target = "TOTAL" if raw_target == "net" else raw_target
        suffix = f"_{entry}" if len(entries.get(method, [])) > 1 else ""
        projected = {}
        for index, quantity in quantities.items():
            name = plain_cell(f"{quantity}_FF_{method}_{target}{suffix}")
            cell = f"entry {entry!r}, method {method!r}, target {raw_target!r}, {quantity}"
            previous = occupied.get(name)
            original = name
            while name in occupied:
                name += plain_cell(f"_{entry}")
            if previous is not None:
                warn(
                    f"far-field column {original!r} on the row collides between "
                    f"{previous} and {cell}; keeping the earlier cell and naming the later "
                    f"cell {name!r}",
                    PyflightstreamWarning,
                )
            occupied[name] = cell
            projected[index] = name
        names[method, entry, raw_target] = projected
    return [names[identity] for identity in identities]


# The names retired with their products answer by name (FR-457).
__getattr__ = removed_names_hook(__name__)
