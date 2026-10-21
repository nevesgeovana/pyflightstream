"""The tables of one point: its sections, its plots and probes, and their reductions.

One of the product families of :mod:`pyflightstream.post` (AD-13, work
package WP5), written by the post stage of
:mod:`pyflightstream.post.products`, which re-exports every name here:

* the SECTIONS table of a point, ``sections/<point>_sections.csv``, the
  sectional loads export re-tabled with the point's condition and the
  rotor each section belongs to (:func:`write_sections_table`);
* the PLOTS table of a point, ``probes/<point>_plots.csv``, the unsteady
  plots export re-tabled with its coefficients brought to the free stream
  (:func:`write_plots_table`);
* the PROBES table of a point, ``probes/<point>_probes.csv``: the probe
  points export of a steady row (:func:`write_probes_table`) or the
  fluid-plots history of an unsteady row (:func:`write_unsteady_probes_table`),
  with the recorded positions (:func:`read_probe_positions`) on the spine
  :data:`PROBE_SPINE`;
* the REDUCTIONS of the plots table, one file per applicable reduction
  beside it: the time average (:func:`write_reduction_table`), the per-blade
  table (:func:`write_per_blade_table`, :data:`PER_BLADE_COLUMNS`) and the
  phase-locked table (:func:`write_phase_locked_table`,
  :data:`PHASE_LOCKED_COLUMNS`);
* the PER-REVOLUTION table: one row per complete revolution of the
  plots history (:func:`per_revolution_table`, :data:`PER_REVOLUTION_COLUMNS`),
  and the drift of each force or moment column between the last two
  revolutions (:func:`revolution_drift_pct`, :func:`is_force_or_moment_column`),
  written beside it (:data:`DRIFT_SUFFIX`).

Which reductions a point gets, over which windows, is decided by the private
reduction stage (:mod:`pyflightstream.post._reduction_stage`); the tables are
written here.

A new per-point table of the backlog (a far-field product, a further
reduction) joins this module beside the writers it resembles.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyflightstream._digest import file_sha256
from pyflightstream.cases import classify_outputs
from pyflightstream.results import parse_force_distributions, parse_solver_analysis_csv

if TYPE_CHECKING:
    from pyflightstream.post._sim import SimContext

import math
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np

from pyflightstream._errors import (
    ProductArgumentError,
    PyflightstreamError,
    PyflightstreamWarning,
    warn,
)
from pyflightstream._tokens import POLAR_ID_COLUMN, REDUCTION_COLUMNS, ROTOR_ID_COLUMN
from pyflightstream.cases import FORCE_PLOT_PARAMETERS
from pyflightstream.cases.workflows import PROBE_POSITION_COLUMNS
from pyflightstream.post._condition import _stated_iteration
from pyflightstream.post._stage import (
    _MOMENT_POINT_COLUMNS,
    _PLOTS_CLOCK_COLUMNS,
    PROBES_DIR,
    _names_location,
)
from pyflightstream.post._tables import (
    _COEFFICIENT_PLOT_PREFIXES,
    _PLOTS_STEP_COLUMN,
    ADVANCE_RATIO_COLUMN,
    CONTEXT_COLUMNS,
    NOT_APPLICABLE,
    SECTION_COLUMNS,
    ProductError,
    ReferenceValues,
    _read_step_clock,
    context_row,
    read_csv_table,
    renamed_columns,
    section_identity,
    write_csv_table,
)
from pyflightstream.post.axes import blade_azimuth_deg
from pyflightstream.post.unsteady import (
    TimestepSeries,
    blade_passage_average,
    per_blade_rows,
    phase_locked_rows,
)
from pyflightstream.results import (
    MalformedOutputError,
    UnsteadyPlotsReport,
    labeled_value,
    parse_probe_points,
    parse_unsteady_plots,
)
from pyflightstream.results.sectional_loads import SectionalLoadsReport, parse_sectional_loads

__all__ = [
    "DRIFT_SUFFIX",
    "PER_BLADE_COLUMNS",
    "PER_REVOLUTION_COLUMNS",
    "PHASE_LOCKED_COLUMNS",
    "PROBE_SPINE",
    "is_force_or_moment_column",
    "per_revolution_table",
    "read_probe_positions",
    "revolution_drift_pct",
    "write_per_blade_table",
    "write_phase_locked_table",
    "write_plots_table",
    "write_probes_table",
    "write_reduction_table",
    "write_sections_table",
    "write_unsteady_probes_table",
]


def _reynolds_millions(text: str) -> float:
    return float(labeled_value(text, "Reynolds Number")) / 1e6


def _altitude_ft(text: str) -> float | None:
    try:
        return float(labeled_value(text, "Altitude (ft)"))
    except (MalformedOutputError, ValueError):
        # NOT STATED IS `NA`, never a zero: sea level is an altitude.
        return None


_ITERATION_UNSET = object()


def write_sections_table(
    path: str | Path,
    export_text: str,
    *,
    mach: float,
    step: int | None = None,
    iteration: object = _ITERATION_UNSET,
    unsteady: bool = False,
    azimuth_deg: float | None = None,
    reference: ReferenceValues | None = None,
    advance_ratio: float | None = None,
    condition: Mapping[str, object] | None = None,
    layout: Sequence[Mapping[str, object]] | None = None,
    rotors: Mapping[str, Mapping[str, object]] | None = None,
    pol: str | int | None = None,
) -> Path | None:
    """Write one sections table from a sectional loads export.

    ``pol`` is the polar the point belongs to, the matrix row's POL: the first
    column of every row (G16), `NA` where the caller states none.

    ``layout`` is WHICH DISTRIBUTION EACH ROW BELONGS TO: the blocks the
    run's script created, in order, as the run record states them under
    ``sections_layout``. A pproc declares several distributions, the wing in XZ
    and each blade in its own frame, and the export concatenates them with no
    marker; with `Offset` the only coordinate, two distributions of similar span
    were indistinguishable. `FAMILY`, `PLANE` and `ROTOR` say which is which.
    The layout is applied ONLY when its counts add up to the rows the export
    holds; otherwise, and on every record written before the run recorded one,
    the three read `NA`. The script states surfaces by index, so nothing at post
    can name them.

    ``rotors`` maps a rotor's alias to its ``families``, its
    ``steps_per_revolution``, its ``blade1_azimuth_deg`` and its signed ``rpm``.
    `AZIMUTH` is where BLADE ONE OF THE BLOCK'S OWN ROTOR is at the export's step,

        (blade1_azimuth_deg + sign(rpm) * STEP * 360 / steps_per_revolution) mod 360

    and `NA` on a block no rotor owns.

    ``condition`` is the POINT's condition as :func:`point_condition` assembles it,
    and the stage always passes it. The export header's `Altitude (ft)` line
    is not set by the campaign and cannot substitute for the point's altitude.
    Without it the header is read, for a caller holding an export and no point.

    ``step`` is the solver step the distribution was sampled at and
    ``azimuth_deg`` is where the blade was when it was; both lead the row
    because they are the only two things that vary down the file. They replace
    the `POINT` column, which carried the polar's NAME and therefore restated
    the file name. A run with no rotor states no azimuth and
    the cell reads `NA`, which is not zero: zero is a real azimuth.

    Write ``step=``; passing ``iteration=`` raises
    :class:`ProductArgumentError` naming that replacement, even for ``None``.

    On a steady export, an omitted ``step`` is read from the header.
    With ``unsteady=True`` the header counts inner iterations, so the caller
    supplies the time step from the run record; an unknown step stays `NA`.

    THE AZIMUTH IS WRAPPED -- a step count is not an angle, and 1575 steps of
    3.6 degrees is 5670 degrees, which is not somewhere a blade can be. Without
    a rotor that owns the block it stays `NA`, because the alternative is
    writing a zero that a reader would believe. ``azimuth_deg`` is for a caller
    holding one export of one rotor and no layout; it states every row.

    Returns None without writing when the export declares no section, as
    a run that defined no distribution leaves; the columns are the point,
    its condition, and the export's own seven, in the export's units.

    ``reference`` supplies the reference LENGTHS, which this table carried
    none of in legacy releases: a sectional force beside no area is a number nobody
    can check. It is optional because a caller that genuinely holds no
    reference should write `NA` rather than be refused a product it can
    otherwise make, and a run's reference is recorded beside its outputs
    rather than inside this export.

    Parameters
    ----------
    path : str or Path
        Destination CSV.
    export_text : str
        Complete text of the sectional loads export.
    mach : float
        Mach number of the point, for the condition block when ``condition``
        is not given.
    step : int, optional
        Solver step the distribution was sampled at; read from the export's
        header on a steady export when omitted, ``NA`` on an unsteady one.
    iteration : object, optional
        Removed; passing any value raises.
    unsteady : bool, optional
        Whether the export is of an unsteady run, whose header counts inner
        iterations rather than time steps.
    azimuth_deg : float, optional
        Azimuth in degrees stated for every row, for a caller holding one
        export of one rotor and no layout.
    reference : ReferenceValues, optional
        Reference lengths written beside each row; ``NA`` where None.
    advance_ratio : float, optional
        Advance ratio of the point, used only when ``condition`` is not given.
    condition : mapping, optional
        The point's condition as :func:`point_condition` assembles it.
    layout : sequence of mapping, optional
        The distribution blocks of the run's script, in order, as the run
        record states them.
    rotors : mapping of str to mapping, optional
        Each rotor's alias to its ``families``, ``steps_per_revolution``,
        ``blade1_azimuth_deg`` and signed ``rpm``.
    pol : str or int, optional
        The polar the point belongs to, written first in every row.

    Returns
    -------
    Path or None
        The file written, or None when the export declares no section.

    Raises
    ------
    ProductArgumentError
        If ``iteration`` is passed.
    ProductError
        If the export cannot be read or carries fewer than seven columns.
    """
    if iteration is not _ITERATION_UNSET:
        raise ProductArgumentError(
            "write_sections_table(iteration=) was removed in 0.26.0; use step= instead."
        )
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
    if step is None and not unsteady:
        step = _stated_iteration(export_text)
    table = np.asarray(report.values, dtype=float)
    if table.shape[1] < 7:
        raise ProductError(
            f"the sectional loads export carries {table.shape[1]} columns, fewer than the seven "
            "the product tables"
        )
    # Use context_row for the shared condition-column order so values
    # land under the same headings across product families.
    try:
        reynolds = None if condition is not None else _reynolds_millions(export_text)
    except (PyflightstreamError, ValueError) as error:
        # A banner without its Reynolds number is an export this table cannot
        # state a condition for: a refusal naming the file, as the parser's.
        raise ProductError(f"the sectional loads export {path} cannot be read: {error}") from error
    stated: Mapping[str, object] = (
        condition
        if condition is not None
        else {
            "ALPHA": report.angle_of_attack_deg,
            "BETA": report.sideslip_deg,
            "MACH": mach,
            "RE": reynolds,
            "VINF": report.freestream_velocity_m_s,
            "ALT": _altitude_ft(export_text),
            ADVANCE_RATIO_COLUMN: advance_ratio,
        }
    )
    context = context_row(stated, None if reference is None else reference.as_lengths())
    identity = section_identity(len(table), layout, rotors, step, azimuth_deg)
    rows = [
        (pol, step, *identity[at], *context, *(float(v) for v in row[:7]))
        for at, row in enumerate(table)
    ]
    return write_csv_table(path, SECTION_COLUMNS, rows)


def write_plots_table(
    path: str | Path, export_text: str, *, pol: str | int | None = None
) -> Path | None:
    """Write one plots table from an unsteady plots export.

    The coefficient columns (``CL_``, ``CDI_``, ``CDO_``, ``CDP_``, ``CDV_``, ``CD_``) are
    multiplied by the square of the reference velocity over the free
    stream, so a run whose reference velocity differs from the free stream
    reads as free-stream coefficients. An export the reader cannot parse is
    a refusal naming the file, never a silent skip; an export with no step
    returns None.

    ``pol`` is the polar the point belongs to. It is the table's FIRST column
    (G16), `NA` where the caller states none, and the export's own
    header follows it unchanged; :func:`plots_table_series` reads every column
    AFTER it back as a plotted quantity.

    Parameters
    ----------
    path : str or Path
        Destination CSV; also named in the refusal message.
    export_text : str
        Complete text of the unsteady plots export.
    pol : str or int, optional
        The polar the point belongs to, written first in every row.

    Returns
    -------
    Path or None
        The file written, or None when the export holds no step.

    Raises
    ------
    ProductError
        If the export cannot be read.
    """
    try:
        report: UnsteadyPlotsReport = parse_unsteady_plots(export_text)
    except PyflightstreamError as error:
        raise ProductError(f"the unsteady plots export {path} cannot be read: {error}") from error
    values = np.asarray(report.values, dtype=float)
    if values.size == 0:
        return None
    # Inside a refusal, as the parse above: the parser accepts an export with
    # no banner, and the bare AnchorNotFoundError (or a ValueError for a
    # value that is no number) was neither a ProductError nor an OSError, so
    # it ended the whole post instead of skipping this point's table.
    try:
        vinf = float(labeled_value(export_text, "Freestream velocity (m/s)"))
    except (PyflightstreamError, ValueError) as error:
        raise ProductError(f"the unsteady plots export {path} cannot be read: {error}") from error
    try:
        vref = float(labeled_value(export_text, "Reference velocity (m/s)"))
    except (PyflightstreamError, ValueError) as error:
        raise ProductError(f"the plots export {path} has no readable reference velocity") from error
    scale = (vref / vinf) ** 2 if vinf > 0.0 else math.nan
    if vinf <= 0.0:
        # NO FREE STREAM TO BRING THEM TO (PFS-2105.015): the coefficients were
        # kept by VREF in silence while the definition and the post log said
        # they were the free stream's. They read NA, and the log says why.
        target = Path(path)
        warn(
            f"point={target.stem.removesuffix('_plots')} product={PROBES_DIR}/{target.name}: "
            f"the plots export states a free-stream velocity of {vinf:g} m/s, so its "
            "coefficient columns cannot be brought to the free stream by (VREF / VINF)^2 and "
            "read NA; the forces and every other column are written as exported.",
            PyflightstreamWarning,
            stacklevel=2,
        )
    scaled = values.copy()
    for index, name in enumerate(report.columns):
        if name.startswith(_COEFFICIENT_PLOT_PREFIXES):
            scaled[:, index] *= scale
    return write_csv_table(
        path,
        (POLAR_ID_COLUMN, *report.columns),
        [(pol, *(float(v) for v in row)) for row in scaled],
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
#: It said `-` in legacy releases, the glyph the PRINTED cost table still uses, and
#: no product writes a second spelling any more. No spine cell is EVER blank
#: now either: a run recorded in legacy releases leaves `NA` in the position and
#: frame columns, which is the one place `NA` stands for a value the package
#: could not derive rather than a column that does not apply -- the exception
#: named beside :data:`NOT_APPLICABLE` and in the change log.
#:
#: Exported steady (and normal-probe) coordinates are in the solver's native
#: length unit and REFERENCE frame. Unsteady history coordinates are the
#: recorded emitted positions, with rotor-radius scaling already resolved,
#: in native length units and their recorded frame.
#: THE CONTEXT FOLLOWS THE SPINE AND PRECEDES THE FLUID COLUMNS, so the shape
#: a reader learned -- where the point is, in which frame, at which
#: step -- is still the first thing in the row, and the export's own columns
#: still arrive in the export's own order after it. Inserting the condition
#: between them would have moved the fluid columns twice: once now and once
#: whenever the condition grows.
#: `POL` LEADS IT (G16), as it leads every table the post writes.
PROBE_SPINE: tuple[str, ...] = (
    POLAR_ID_COLUMN,
    *PROBE_POSITION_COLUMNS,
    "STEP",
    *CONTEXT_COLUMNS,
)


def read_probe_positions(path: str | Path) -> dict[int, tuple[float, float, float, str]]:
    """Read a run's probe positions, keyed by the vertex number (FR-91).

    The file the run stage wrote beside the script that placed the points,
    `sims/<sim>/profiles/<sim>_probe_points.csv`. The key is the vertex
    number, which is the suffix an unsteady fluid plot carries in its own
    name, so `MACH7` is vertex 7 here.

    A file THAT IS NOT THERE answers an empty mapping: every run recorded
    in legacy releases names none, and a probe table without its positions is
    what those runs have always produced. Refusing them would take a
    product away from a campaign that already happened.

    An existing positions file that cannot be read is refused. A missing file and a malformed file
    are distinct: a truncated file must not silently produce empty coordinates.

    Parameters
    ----------
    path : str or Path
        The positions file of the run.

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
        # An empty existing positions file is unreadable evidence, distinct
        # from an absent file. Name the empty-file failure instead of silently
        # writing empty coordinates; an absent file remains silent.
        raise ProductError(
            f"the probe positions file {target} cannot be read: {error}. It is "
            "where the run stage recorded which probe point is where, so the "
            "probe table of this point cannot say where its samples are. Delete "
            "it and re-run the point to have it written again, or, to get the "
            "rest of the products now, move it aside: a point whose positions "
            "file is ABSENT still gets its table, without the position columns."
        ) from error
    if not {"PROBE", "X", "Y", "Z", "FRAME"}.issubset(columns) or not rows:
        raise ProductError(f"the probe positions file {target} has no complete positions table")
    for number, row in enumerate(rows, start=2):
        try:
            raw = float(row["PROBE"])
            if not raw.is_integer():
                raise ValueError("PROBE must be an integer")
            vertex = int(raw)
            if vertex in out:
                raise ValueError(f"duplicate PROBE {vertex}")
            xyz = (float(row["X"]), float(row["Y"]), float(row["Z"]))
            if not all(math.isfinite(value) for value in xyz):
                raise ValueError("coordinates must be finite")
            out[vertex] = (*xyz, str(row["FRAME"]))
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            raise ProductError(
                f"the probe positions file {target}, row {number}, cannot be read: {error}"
            ) from error
    return out


def _probe_spine(
    vertex: int,
    positions: Mapping[int, tuple[float, float, float, str]],
    step: object = NOT_APPLICABLE,
    *,
    stated: tuple[float, float, float] | None = None,
    context: Sequence[object] = (),
    pol: str | int | None = None,
) -> tuple[object, ...]:
    """One row's spine: the polar, the point, where it is, its frame, and the step.

    ``stated`` is the position the EXPORT ITSELF carries, which a steady
    probe export does and an unsteady plots export does not. Where the
    export states one it wins, because it is the solver's own answer about
    the point it sampled. These coordinates are in the REFERENCE frame and
    native length units; a recorded entry's frame cannot relabel them.

    THE STEP OF A STEADY ROW IS ``NA`` AND WAS ``-`` in legacy releases. The rule is
    one sentence -- where a value does not apply, the token is always ``NA`` --
    and the technical-writing lens had just measured why it matters:
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
        return (pol, vertex, "", "", "", "", step, *context)
    frame = "REFERENCE" if stated is not None else ("" if recorded is None else recorded[3])
    return (pol, vertex, x, y, z, frame, step, *context)


def write_probes_table(
    path: str | Path,
    export_text: str,
    *,
    positions: Mapping[int, tuple[float, float, float, str]] | None = None,
    condition: Mapping[str, object] | None = None,
    reference: ReferenceValues | None = None,
    pol: str | int | None = None,
    step: int | None = None,
) -> Path | None:
    """Write one probe-points table from an EXPORT_PROBE_POINTS export (FR-87, FR-91).

    ``pol`` is the polar the point belongs to, the first column of every row
    (G16); `NA` where the caller states none.

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
    path : str or Path
        Destination CSV; also named in the refusal message.
    export_text : str
        Complete text of the probe points export.
    positions : mapping, optional
        Vertex number to ``(x, y, z, frame)``, from
        :func:`read_probe_positions`. Absent for every run recorded
        in legacy releases, and the spine's position and frame cells then read
        ``NA`` rather than the table being refused. They were EMPTY in legacy releases; the
        producer still returns a blank there and the funnel in
        :mod:`pyflightstream.post._tables` renders it, so this says what the
        user opens rather than what the tuple carries.
    condition : mapping, optional
        The point's condition block, written in every row.
    reference : ReferenceValues, optional
        Reference lengths written beside each row.
    pol : str or int, optional
        The polar the point belongs to, written first in every row.
    step : int, optional
        The time step the export holds, written in every row's ``STEP``: the
        last time step of an unsteady run whose probes are normal (FR-417
        FR-887). ``NA`` where the caller states none, as on a steady point.

    Returns
    -------
    Path or None
        The file written, or None when the export holds no probe point.

    Raises
    ------
    ProductError
        If the export cannot be read.
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
                *_probe_spine(
                    order,
                    known,
                    NOT_APPLICABLE if step is None else step,
                    stated=stated,
                    context=context,
                    pol=pol,
                ),
                *(float(row[columns.index(name)]) for name in rest),
            )
        )
    return write_csv_table(path, (*PROBE_SPINE, *rest), rows)


def _plotted_value(text: str | None) -> float | None:
    """Read one plots-table cell back, its `NA` (or blank) as a missing value.

    The plots table writes a NaN the export carried as `NA`, and ``float``
    refused it, so one missing sample dropped the point's whole probes table.
    """
    cell = (text or "").strip()
    return None if cell in ("", "-", NOT_APPLICABLE) else float(cell)


def write_unsteady_probes_table(
    path: str | Path,
    plots_table: str | Path,
    *,
    positions: Mapping[int, tuple[float, float, float, str]],
    parameters: Sequence[str],
    condition: Mapping[str, object] | None = None,
    reference: ReferenceValues | None = None,
    notes: list[str] | None = None,
    pol: str | int | None = None,
) -> Path | None:
    """Write the probe table of an UNSTEADY row, from its plots table (FR-91).

    ``pol`` is the polar the point belongs to, the first column of every row
    (G16); `NA` where the caller states none. The plots table it
    reads carries its own `POL` first, which is read by name and never as a
    probe group.

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

    Parameters
    ----------
    path : str or Path
        Destination CSV.
    plots_table : str or Path
        The plots table written for the same point.
    positions : mapping
        Vertex number to ``(x, y, z, frame)``, from
        :func:`read_probe_positions`.
    parameters : sequence of str
        The probe parameters the artifact declares, for example ``MACH``.
    condition : mapping, optional
        The point's condition block, written in every row.
    reference : ReferenceValues, optional
        Reference lengths written beside each row.
    notes : list of str, optional
        Receives the recorded vertices the table has no history for.
    pol : str or int, optional
        The polar the point belongs to, written first in every row.

    Returns
    -------
    Path or None
        None when the row recorded no probe position, when the artifact
        declares no probe parameter, or when no group of the two is
        actually in the table: a file of a spine and nothing else is a
        promise of content that is not there.

    Parameters absent at a vertex are written as NA, so entries requesting
    different parameters retain their available histories in the same table.

    A recorded vertex whose group is absent from the export is named in ``notes``; the remaining
    vertices are kept.
    """
    if not positions or not parameters:
        return None
    columns, rows = read_csv_table(plots_table)
    present = set(columns)
    groups = [
        (vertex, [f"{parameter}{vertex}" for parameter in parameters])
        for vertex in sorted(positions)
    ]
    kept = [(vertex, names) for vertex, names in groups if any(n in present for n in names)]
    absent = [vertex for vertex, names in groups if not any(n in present for n in names)]
    groups = kept
    if absent and notes is not None:
        notes.append(
            "no history for recorded probe position(s) "
            + ", ".join(str(vertex) for vertex in absent)
            + ": the plots export carries no column of "
            + ", ".join(parameters)
            + " for them, so they are not in this table; a new run is needed to sample them"
        )
    if not groups or not rows:
        return None
    # Use _read_step_clock, shared with reductions and series. The table's
    # Time-step column supplies STEP, including offset and sparse clocks;
    # only a table without that column falls back to row ordinals.
    steps = (
        _read_step_clock([row.get(_PLOTS_STEP_COLUMN) or "" for row in rows])
        if _PLOTS_STEP_COLUMN in present
        else np.arange(1, len(rows) + 1, dtype=int)
    )
    context = context_row(condition, None if reference is None else reference.as_lengths())
    out: list[tuple[object, ...]] = []
    for row, stated in zip(rows, steps, strict=True):
        step = int(stated)
        for vertex, names in groups:
            out.append(
                (
                    *_exact_position(
                        _probe_spine(vertex, positions, step, context=context, pol=pol)
                    ),
                    *(_plotted_value(row[name]) if name in present else None for name in names),
                )
            )
    return write_csv_table(path, (*PROBE_SPINE, *tuple(parameters)), out)


#: WHERE X, Y AND Z SIT IN A PROBE SPINE, read off the spine itself.
_SPINE_XYZ = slice(PROBE_SPINE.index("X"), PROBE_SPINE.index("Z") + 1)


def _exact_position(spine: tuple[object, ...]) -> tuple[object, ...]:
    """Write a spine's RECORDED position at round-trip precision (Q0 CX-3).

    The position of an unsteady sample is not a measurement: it is the vertex
    this package emitted, read back from the positions file. The probe-field
    product compares it for EXACT equality with the emitted samples
    (``points_native``) and refuses a difference, so the five-decimal rule of
    the CSV funnel, which is right for the measured cells, turned every
    fractional grid (1/3 written ``0.33333``) into a refusal of the package's
    own table. Only these three cells are exempt; the measured cells keep five
    decimals.
    """
    cells = list(spine)
    cells[_SPINE_XYZ] = [
        format(float(value), ".17g") if isinstance(value, float | np.floating) else value
        for value in cells[_SPINE_XYZ]
    ]
    return tuple(cells)


def write_reduction_table(
    path: str | Path,
    series: TimestepSeries,
    columns: Sequence[str],
    *,
    reduction: str,
    windows: Sequence[Sequence[int]],
    names: Mapping[str, str] | None = None,
    condition: Mapping[str, object] | None = None,
    reference: ReferenceValues | None = None,
    rotor: str | None = None,
    pol: str | int | None = None,
) -> Path:
    """Write one reduction of a plots table: one row per window, the table's columns averaged.

    ``pol`` is the polar the point belongs to, the first column of every row
    (G16) and the first of :data:`REDUCTION_COLUMNS`; `NA` where the
    caller states none.

    THE CLOCK IS NOT AVERAGED. FIRST_STEP and LAST_STEP identify the span;
    Time-step is a counter rather than a plotted physical quantity.
    ``rotor`` is the alias this reduction is cut for, `NA` for the time average.

    ``condition`` and ``reference`` are what the row is a reduction OF, and
    this table carried neither in legacy releases: a window of averaged coefficients
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
    names : mapping of str to str, optional
        The pproc dictionary renaming columns of the heading.
    condition : mapping, optional
        The point's condition block, written in every row.
    reference : ReferenceValues, optional
        Reference lengths and moment point written beside each row.
    rotor : str, optional
        The alias the reduction is cut for; ``NA`` for the time average.
    pol : str or int, optional
        The polar the point belongs to, written first in every row.

    Returns
    -------
    Path
        The file written, one row per window.

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
    moment = context_row(
        None if reference is None else reference.as_moment_point(),
        None,
        columns=_MOMENT_POINT_COLUMNS,
    )
    columns = [name for name in columns if name not in _PLOTS_CLOCK_COLUMNS]
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
                pol,
                reduction,
                rotor,
                index,
                int(first),
                int(last),
                average.n_frames,
                *context,
                *moment,
                *(float(average.fields[name][0]) for name in columns),
            )
        )
    heading = renamed_columns(
        (*REDUCTION_COLUMNS, *columns),
        names,
        printed=columns,
        where=_names_location(PROBES_DIR, path),
    )
    return write_csv_table(path, heading, rows)


#: What a per-blade row states before the condition: the polar first (G16),
#: which reduction, which rotor, which blade and its family, the ONE window
#: every blade shares, and where THAT blade was when the window opened and closed.
PER_BLADE_COLUMNS: tuple[str, ...] = (
    POLAR_ID_COLUMN,
    "REDUCTION",
    "ROTOR",
    "BLADE",
    "FAMILY",
    "FIRST_STEP",
    "LAST_STEP",
    "STEPS",
    "AZIMUTH_START",
    "AZIMUTH_END",
    *CONTEXT_COLUMNS,
    "XMOM",
    "YMOM",
    "ZMOM",
)


def write_per_blade_table(
    path: str | Path,
    series: TimestepSeries,
    columns: Sequence[str],
    *,
    window: Sequence[int],
    rotor: str | None,
    blades: int,
    facts: Mapping[str, object],
    condition: Mapping[str, object] | None = None,
    reference: ReferenceValues | None = None,
    pol: str | int | None = None,
) -> Path:
    """Write the per-blade reduction: ONE ROW PER BLADE over the one shared window.

    ``pol`` is the polar the point belongs to, the first column of every row
    (G16); `NA` where the caller states none.

    ``facts`` is what the run and the reference state of the rotor, as
    :func:`write_sections_table` takes it: its blade ``families`` in order, its
    ``steps_per_revolution``, its ``blade1_azimuth_deg`` and its signed ``rpm``.
    ``blades`` is the rotor's blade count, which spaces the blades; on a sector the
    mesh carries fewer families than that and there is one row per family.

    A blade's columns are the plots ENDING in its family (``CL_MRP_Blade1``),
    written with the family removed so two blades line up under one heading.
    `AZIMUTH_START` and `AZIMUTH_END` are where that blade is AT the window's first
    and last step, by the sections table's own formula; without the rotor's clock
    they read `NA`, and the averages are written all the same.

    in legacy releases this file was one row with the time average's shape under the
    per-blade name.

    Parameters
    ----------
    path : str or Path
        Destination CSV.
    series : TimestepSeries
        The plots table as :func:`plots_table_series` reads it.
    columns : sequence of str
        The plots table's columns, in its order.
    window : sequence of int
        First and last solver step of the window every blade shares.
    rotor : str or None
        The rotor's alias, named in the refusal and written in each row.
    blades : int
        The rotor's blade count, which spaces the blades in azimuth.
    facts : mapping
        What the run states of the rotor: ``families``,
        ``steps_per_revolution``, ``blade1_azimuth_deg`` and ``rpm``.
    condition : mapping, optional
        The point's condition block, written in every row.
    reference : ReferenceValues, optional
        Reference lengths and moment point written beside each row.
    pol : str or int, optional
        The polar the point belongs to, written first in every row.

    Returns
    -------
    Path
        The file written, one row per blade.

    Raises
    ------
    ProductError
        If the history does not cover the window, or holds no column of any blade
        family: a per-blade table with no blade in it is the defect this replaces.
    """
    first, last = int(window[0]), int(window[1])
    first_step = int(series.steps[0]) if len(series.steps) else 1
    last_step = int(series.steps[-1]) if len(series.steps) else 0
    if last > last_step or first < first_step:
        raise ProductError(
            f"the plots table runs from step {first_step} to step {last_step} and the "
            f"per_blade window spans steps {first} to {last}, so the history does not cover "
            "the window the row states; a shorter history averaged as a whole one would be "
            "an average of a run that did not finish writing"
        )
    stated = facts.get("families")
    families = (
        [str(f) for f in stated]
        if isinstance(stated, Sequence) and not isinstance(stated, str)
        else []
    )
    if not families:
        raise ProductError(
            f"nothing states which families are the blades of rotor {rotor!r}, so the "
            "per-blade reduction has no blade to give a row to. A rotor's blades are the "
            "families_blades of its block in the reference artifact: declare the rotor "
            "there and have the row cite it. The run records them; this "
            "row names no rotor block, so neither its record nor the reference has them."
        )
    held = [f for f in families if any(str(c).endswith(f"_{f}") for c in columns)]
    if not held:
        raise ProductError(
            f"the plots table holds no column of a blade family of rotor {rotor!r} "
            f"(its blades are {families}), so there is no "
            "blade to give a row to. A blade's plots are the ones named for its family: "
            'declare a plot group with families = "each" or frame = "LOCAL_AXIS" over the '
            "rotor in the pproc artifact. It takes a new run; the script defines what the "
            "solver plots."
        )
    per_revolution = facts.get("steps_per_revolution")
    datum = facts.get("blade1_azimuth_deg")
    rpm = facts.get("rpm")
    # WHERE BLADE ONE IS AT THE WINDOW'S FIRST STEP, from its datum at step zero.
    opening = blade_azimuth_deg(datum, step=first, steps_per_revolution=per_revolution, rpm=rpm)
    clocked = opening is not None
    sense = 1.0 if not clocked or float(rpm) > 0 else -1.0  # type: ignore[arg-type]
    try:
        blade_rows = per_blade_rows(
            series,
            window=(first, last),
            blades=int(blades) if int(blades) >= len(families) else len(families),
            steps_per_revolution=float(per_revolution) if clocked else None,  # type: ignore[arg-type]
            blade1_azimuth_deg=opening,
            blade_families=families,
            sense=sense,
        )
    except ValueError as error:
        raise ProductError(f"the per_blade reduction of rotor {rotor!r}: {error}") from error
    context = context_row(condition, None if reference is None else reference.as_lengths())
    moment = context_row(
        None if reference is None else reference.as_moment_point(),
        None,
        columns=_MOMENT_POINT_COLUMNS,
    )
    lead = {"BLADE", "FAMILY", "FIRST_STEP", "LAST_STEP", "AZIMUTH_START", "AZIMUTH_END"}
    names: list[str] = []
    for row in blade_rows:
        for name in row:
            if name not in lead and name not in names:
                names.append(name)
    table = [
        (
            pol,
            "per_blade",
            rotor,
            row["BLADE"],
            row.get("FAMILY"),
            first,
            last,
            last - first + 1,
            row["AZIMUTH_START"],
            row["AZIMUTH_END"],
            *context,
            *moment,
            *(row.get(name) for name in names),
        )
        for row in blade_rows
        if row.get("FAMILY") in held
    ]
    return write_csv_table(path, (*PER_BLADE_COLUMNS, *names), table)


#: What a row of the azimuthal phase-locked table states before the condition:
#: the polar (first G16), which reduction and rotor, WHERE blade one
#: is, the step of the last revolution
#: that azimuth falls on, how many revolutions entered the mean, and the steps
#: those revolutions span.
PHASE_LOCKED_COLUMNS: tuple[str, ...] = (
    POLAR_ID_COLUMN,
    "REDUCTION",
    "ROTOR",
    "AZIMUTH",
    "STEP",
    "REVOLUTIONS",
    "FIRST_STEP",
    "LAST_STEP",
    "STEPS",
    *CONTEXT_COLUMNS,
    "XMOM",
    "YMOM",
    "ZMOM",
)


def write_phase_locked_table(
    path: str | Path,
    series: TimestepSeries,
    columns: Sequence[str],
    *,
    window: Sequence[int],
    revolutions: float,
    steps_per_revolution: float,
    rotor: str | None,
    blades: int,
    facts: Mapping[str, object],
    condition: Mapping[str, object] | None = None,
    reference: ReferenceValues | None = None,
    pol: str | int | None = None,
) -> Path:
    """Write the phase-locked reduction a ``[phase_locked]`` table asks for: ONE ROW PER AZIMUTH.

    ``pol`` is the polar the point belongs to, the first column of every row
    (G16); `NA` where the caller states none.

    Each row is an azimuthal position of the rotor's last revolution, and each
    value the mean of the samples AT that position across the last
    ``revolutions`` revolutions; the rows run from 0 towards 360 degrees. It is
    :func:`pyflightstream.post.unsteady.phase_locked_rows`, which says how a
    blade's own columns are tabulated by that blade's azimuth.

    ``facts`` is what :func:`write_per_blade_table` takes of the rotor: its blade
    ``families``, its ``blade1_azimuth_deg`` and its signed ``rpm``. The columns
    keep the names the plots export prints, all in one file: a blade's end in its
    family, a rotor's in the group the pproc named for it.

    Parameters
    ----------
    path : str or Path
        Destination CSV.
    series : TimestepSeries
        The plots table as :func:`plots_table_series` reads it.
    columns : sequence of str
        The plots table's columns, in its order.
    window : sequence of int
        First and last solver step of the window.
    revolutions : float
        How many of the last revolutions enter each mean.
    steps_per_revolution : float
        Solver steps in one revolution.
    rotor : str or None
        The rotor's alias, written in each row.
    blades : int
        The rotor's blade count.
    facts : mapping
        What the run states of the rotor: ``families``,
        ``blade1_azimuth_deg`` and ``rpm``.
    condition : mapping, optional
        The point's condition block, written in every row.
    reference : ReferenceValues, optional
        Reference lengths and moment point written beside each row.
    pol : str or int, optional
        The polar the point belongs to, written first in every row.

    Returns
    -------
    Path
        The file written, one row per azimuth.

    Raises
    ------
    ProductError
        If nothing states where blade one is or which way the rotor turns, so no
        azimuth can be written, or the history does not hold the revolutions.
    """
    datum = facts.get("blade1_azimuth_deg")
    rpm = facts.get("rpm")
    if (
        not isinstance(datum, int | float)
        or not isinstance(rpm, int | float)
        or not math.isfinite(datum)
        or not math.isfinite(rpm)
        or not rpm
    ):
        raise ProductError(
            f"the phase-locked table of rotor {rotor!r} is tabulated by azimuth, and nothing "
            f"states where its blade one is (blade1_azimuth_deg: {datum!r}) or which way it "
            f"turns (rpm: {rpm!r}). Declare the rotor in the reference artifact, with its "
            "[rotors.<ALIAS>.blade1] azimuth_deg, and have the matrix row cite it; the run "
            "records both."
        )
    stated = facts.get("families")
    families = (
        [str(f) for f in stated]
        if isinstance(stated, Sequence) and not isinstance(stated, str)
        else []
    )
    first, last = int(window[0]), int(window[1])
    names = [name for name in columns if name not in _PLOTS_CLOCK_COLUMNS]
    read_steps: set[int] = set()
    try:
        rows = phase_locked_rows(
            series,
            names,
            last_step=last,
            revolutions=float(revolutions),
            steps_per_revolution=float(steps_per_revolution),
            blade1_azimuth_deg=float(datum),
            sense=1.0 if float(rpm) > 0 else -1.0,
            blades=int(blades),
            blade_families=families,
            read_steps=read_steps,
        )
    except ProductError as error:
        raise ProductError(f"the phase_locked reduction of rotor {rotor!r}: {error}") from error
    first = min(read_steps) if read_steps else first
    last = max(read_steps) if read_steps else last
    context = context_row(condition, None if reference is None else reference.as_lengths())
    moment = context_row(
        None if reference is None else reference.as_moment_point(),
        None,
        columns=_MOMENT_POINT_COLUMNS,
    )
    table = [
        (
            pol,
            "phase_locked",
            rotor,
            row["AZIMUTH"],
            row["STEP"],
            row["REVOLUTIONS"],
            first,
            last,
            len(read_steps),
            *context,
            *moment,
            *(row.get(name) for name in names),
        )
        for row in rows
    ]
    return write_csv_table(path, (*PHASE_LOCKED_COLUMNS, *names), table)


# The drift limit of a pproc that declares no `[per_revolution]` table, in per
# cent, is `DEFAULT_DRIFT_LIMIT_PCT`, imported from `pyflightstream.cases` (its one
# home, which the pproc model's default reads too) and re-exported here.

#: What a drift column's name ends with: the plotted column it is the drift of.
DRIFT_SUFFIX = "_DRIFT_PCT"


#: What a per-revolution row states before the means: the polar, which reduction,
#: which rotor, which revolution (counted from one), the steps it spans, the
#: condition and the moment point. The time average's `WINDOW` is `REVOLUTION`.
PER_REVOLUTION_COLUMNS: tuple[str, ...] = (
    POLAR_ID_COLUMN,
    "REDUCTION",
    ROTOR_ID_COLUMN,
    "REVOLUTION",
    "FIRST_STEP",
    "LAST_STEP",
    "STEPS",
    *CONTEXT_COLUMNS,
    *_MOMENT_POINT_COLUMNS,
)


def is_force_or_moment_column(name: str) -> bool:
    """Whether a plotted column is a force or a moment, or a force coefficient of one.

    The plots table names a column `<parameter>_<group>` (`FX_MRP_TOTAL`), and the
    parameter is one of the solver's force plot parameters: the six components
    and the four force coefficients. The parameter is what is asked, so a group
    that happens to begin with `F` is not mistaken for a force.

    Parameters
    ----------
    name : str
        A column name of the plots table.

    Returns
    -------
    bool
        True when the part of the name before the first underscore is one of
        the solver's force plot parameters.

    Examples
    --------
    >>> is_force_or_moment_column("FX_MRP_TOTAL"), is_force_or_moment_column("CDI_WING")
    (True, True)
    >>> is_force_or_moment_column("VX_probe1"), is_force_or_moment_column("FXX_TOTAL")
    (False, False)
    """
    return name.split("_", 1)[0] in FORCE_PLOT_PARAMETERS


def per_revolution_table(
    series: TimestepSeries,
    columns: Sequence[str],
    *,
    revolution_steps: int,
    read_steps: set[int] | None = None,
) -> tuple[list[tuple[int, int]], list[dict[str, float]], int]:
    """Cut a plots history into COMPLETE revolutions and take each column's mean.

    Revolution ``k`` is rows ``(k-1) * revolution_steps`` to
    ``k * revolution_steps - 1`` of the table, counted from its first row, so a
    history that begins at step one cuts at steps 1 to N, N+1 to 2N and so on.
    The mean is :func:`pyflightstream.post.unsteady.blade_passage_average`, the
    package's one implementation of that average, so this table cannot disagree
    with the time average about what a mean is. A trailing partial revolution is
    NOT averaged: its length differs, so its mean would be the mean of another
    thing under the same name.

    Parameters
    ----------
    series : TimestepSeries
        The plots table as :func:`plots_table_series` reads it.
    columns : sequence of str
        The columns to average.
    revolution_steps : int
        Solver steps in one revolution; at least one.
    read_steps : set of int, optional
        Receives the steps the averages read.

    Returns
    -------
    tuple
        The (first, last) step of each complete revolution, each revolution's
        mean by column, and the number of rows left over in the partial one.

    Raises
    ------
    ProductError
        If ``revolution_steps`` is below one.
    """
    if revolution_steps < 1:
        raise ProductError("a revolution of under one solver step cannot be cut")
    rows = len(series.steps)
    complete = rows // revolution_steps
    windows: list[tuple[int, int]] = []
    means: list[dict[str, float]] = []
    for index in range(complete):
        first = int(series.steps[index * revolution_steps])
        last = int(series.steps[(index + 1) * revolution_steps - 1])
        average = blade_passage_average(series, window=(first, last), read_steps=read_steps)
        windows.append((first, last))
        means.append({name: float(average.fields[name][0]) for name in columns})
    return windows, means, rows - complete * revolution_steps


def revolution_drift_pct(current: float, previous: float) -> float | None:
    """Return the drift of one mean from the previous one, in per cent, or None (`NA`).

    ``(current - previous) / |previous| * 100``: the sign says whether the mean
    rose or fell whatever the sign of the quantity. None where the previous mean
    is zero, which has no relative change, and where either mean is not a number.

    Parameters
    ----------
    current : float
        The mean of the revolution.
    previous : float
        The mean of the revolution before it.

    Returns
    -------
    float or None
        The drift in per cent, or None where it is undefined.

    Examples
    --------
    >>> revolution_drift_pct(101.0, 100.0)
    1.0
    >>> revolution_drift_pct(-99.0, -100.0)
    1.0
    >>> revolution_drift_pct(1.0, 0.0) is None
    True
    """
    if previous == 0.0 or not math.isfinite(previous) or not math.isfinite(current):
        return None
    difference = current - previous
    ratio = (
        difference / abs(previous)
        if math.isfinite(difference)
        else current / abs(previous) - math.copysign(1.0, previous)
    )
    return ratio * 100.0


def export_tables(ctx: SimContext) -> None:
    """Table exported numbers with POL and condition, without inferring an unstated scalar field."""
    for point in ctx.points:
        record = ctx.record_of[point.name]
        exports = classify_outputs(record.outputs, package_version=record.package_version)
        for kind, product in (
            ("force_distributions", "force_distributions"),
            ("csv", "surface_values"),
        ):
            if kind not in exports:
                continue
            source = ctx.workspace.sim_dir(record.sim_id) / exports[kind]
            relative = f"tables/{point.name}_{product}.csv"
            try:
                text = source.read_text(encoding="utf-8")
                if kind == "force_distributions":
                    force = parse_force_distributions(
                        text, requested_version=record.fs_version_requested
                    )
                    columns, values = force.columns, force.values
                    details = {"force_units": force.force_units, "moment_units": force.moment_units}
                else:
                    surface = parse_solver_analysis_csv(text)
                    columns, values = surface.columns, surface.values
                    details = {"scalar_field": surface.scalar_field}
            except (OSError, ValueError, PyflightstreamError) as error:
                ctx.skipped[relative] = f"{product}: {error}"
                continue
            target = ctx.target(ctx.out / relative)
            context = context_row(ctx.condition(point), ctx.reference.as_lengths())
            write_csv_table(
                target,
                (POLAR_ID_COLUMN, *CONTEXT_COLUMNS, *columns),
                [(ctx.sim_id, *context, *(str(value) for value in row)) for row in values],
            )
            ctx.add(
                target,
                {
                    "runs": ctx.sources[point.name],
                    "kind": product,
                    "source_sha256": file_sha256(source),
                    **details,
                },
            )
