"""The post of one simulation: one resolved context, then the product families in order.

A private module of :mod:`pyflightstream.post` (AD-13, work package WP5 of
0.33.0). Until 0.33.0 one function of 1183 lines, twelve parameters and
seventy-seven locals wrote every product of a simulation; it is now a first
part that RESOLVES what the simulation's records state into one frozen
:class:`SimContext`, and the steps that each write one family from it, called
in the order the manifest has always had:

1. :func:`_group_polars`: the polar of each boundary group, its custom-format
   twin and the superfile rows (:mod:`pyflightstream.post.polar`);
2. :func:`_point_products`, per point: its sections table and the
   quasi-steady and harmonic products cut from it, its probes table, its
   plots table, the unsteady probes and the reductions
   (:mod:`pyflightstream.post.point_tables`,
   :mod:`pyflightstream.post._reduction_stage`);
3. :func:`_rotor_table_products`: one table per rotor the reference declares
   (:mod:`pyflightstream.post.rotor_table`);
4. :func:`_qsteady_rotor_products`: the quasi-steady clockings, their average
   and the correction route;
5. :func:`_unsteady_polar_products`: the time-averaged polar of an unsteady
   simulation (:mod:`pyflightstream.post.unsteady_polar`);
6. :func:`_superfile_drafts`: the rows of each group's superfile, written by
   the campaign once the union of its columns is known.

The byte snapshot of the products (``tests/tier1_offline/test_products_snapshot.py``,
P0330-PRODUCTS-SNAPSHOT) was taken before the decomposition and is unchanged
by it. A product family of the backlog joins as one more step here, reading
the context and writing into its sinks.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning, warn
from pyflightstream._tokens import MESH_FACES_COLUMN
from pyflightstream.cases import PprocSpec, select_group_members
from pyflightstream.cases.workflows import CONFIGURATION_VARIABLE
from pyflightstream.post import qsteady as _qsteady
from pyflightstream.post._admit import (
    _admit,
    _Admitted,
)
from pyflightstream.post._condition import (
    _advance_ratio_of,
    _effective_pproc,
    _last_time_step,
    _live_reference,
    _mach_of,
    _matrix_window,
    _refuse_a_reference_the_solver_did_not_use,
    _section_rotors,
    _simulation_metadata,
    _stated_window,
    clock_rotor_facts,
    point_condition,
)
from pyflightstream.post._installed_copies import (
    INFLOW_SUFFIX,
    write_installed_inflow,
    write_installed_probes,
)
from pyflightstream.post._reduction_stage import _drift_limit_pct, _point_reductions
from pyflightstream.post._rotor_plan import _rotor_tables
from pyflightstream.post._rotor_products import (
    _qsteady_corrections,
    _qsteady_products,
    _qsteady_sections,
    _qsteady_super_cells,
    _the_sections_writer,
    _wheel_harmonics,
)
from pyflightstream.post._stage import (
    POLARS_DIR,
    PROBES_DIR,
    SECTIONS_DIR,
    _refuse_aliases_a_file_name_cannot_tell_apart,
)
from pyflightstream.post._tables import (
    ADVANCE_RATIO_COLUMN,
    ProductError,
    ReferenceValues,
    _march_plots_text,
    read_csv_table,
    write_csv_table,
)
from pyflightstream.post.custom_polar import write_custom_polar_format
from pyflightstream.post.point_tables import (
    write_plots_table,
    write_probes_table,
    write_sections_table,
    write_unsteady_probes_table,
)
from pyflightstream.post.polar import (
    PolarPoint,
    drag_columned_rows,
    drag_columns_of,
    group_polar_rows,
    polar_table_columns,
    polar_table_rows,
    swept_axes,
    swept_polar_file_name,
)
from pyflightstream.post.provenance import refuse_an_existing_product as _refuse_an_existing_product
from pyflightstream.post.rotor_table import write_rotor_table
from pyflightstream.post.superfile import (
    SuperfileDraft,
    plots_last_row,
    super_file_name,
    superfile_row,
)
from pyflightstream.post.unsteady_polar import (
    global_frame_plot_groups,
    unsteady_polar_file_name,
    write_unsteady_polar,
)
from pyflightstream.results import FrozenSolve
from pyflightstream.workspace.inputs import rotor_integration_groups
from pyflightstream.workspace.sidecars import inventory_sidecar, recorded_mesh_faces

if TYPE_CHECKING:
    from pyflightstream.cases.matrix import MatrixRow
    from pyflightstream.workspace import CampaignWorkspace, RunRecord


@dataclass(frozen=True)
class SimContext:
    """What the first part of one simulation's post resolves, and where its steps write.

    Frozen: a step reads what was resolved and cannot rebind it. The SINKS
    (``written``, ``written_names``, ``skipped``, and ``super_rows``,
    ``plots_tables`` and ``qsteady_validity_of``, which a later step reads
    back) are containers the steps fill in the order the manifest has always
    had.

    Attributes
    ----------
    workspace : CampaignWorkspace
        The campaign the simulation belongs to.
    sim_id : str
        The simulation.
    records : sequence of RunRecord
        Its admitted records, as the stage handed them over.
    out : Path
        The products folder.
    archive, archive_stamp
        Whether, and under which stamp, a replaced product is archived.
    matrix_row : MatrixRow or None
        The row the simulation was run from, as the matrix states it today.
    sweep_rows : mapping or None
        The campaign sweep table's row of each run, for the superfile.
    drafts : list of SuperfileDraft or None
        Where the superfile rows go; None writes none.
    pproc_id, pproc
        The pproc artifact the products follow, resolved as it stands today.
    first : RunRecord
        The record whose metadata the simulation's products carry.
    mach : float
        The simulation's Mach number.
    reference : ReferenceValues
        The reference block of the records.
    window : tuple of int or None
        The averaging window of an unsteady simulation, in solver steps.
    cell : mapping or None
        The flight condition cell of the first record.
    table_name, super_name : str
        The name of the polar table and of the superfile.
    live : object or None
        The reference artifact as the workspace holds it today.
    conditions : list of dict
        The flight condition of each point, in the order of ``points``.
    aliases : mapping
        The boundary aliases the groups resolve through.
    """

    workspace: CampaignWorkspace
    sim_id: str
    records: Sequence[RunRecord]
    out: Path
    archive: bool
    archive_stamp: datetime | None
    matrix_row: MatrixRow | None
    sweep_rows: Mapping[str, Mapping[str, object]] | None
    drafts: list[SuperfileDraft] | None
    pproc_id: str | None
    pproc: PprocSpec
    first: RunRecord
    mach: float
    reference: ReferenceValues
    window: tuple[int, int] | None
    cell: Mapping[str, object] | None
    table_name: str
    super_name: str
    live: object | None
    conditions: list[dict[str, object]]
    aliases: Mapping[str, Sequence[str]]
    skipped: dict[str, str]
    points: list[PolarPoint]
    record_of: dict[str, RunRecord]
    sources: dict[str, list[str]]
    exports: dict[str, tuple[Path | None, Path | None, Path | None]]
    plans: dict[str, dict[str, object] | None]
    point_windows: dict[str, tuple[int, int]]
    frozen_points: dict[str, FrozenSolve]
    probe_positions: dict[int, tuple[float, float, float, str]]
    written: list[Path] = field(default_factory=list)
    written_names: dict[str, dict[str, object]] = field(default_factory=dict)
    super_rows: dict[str, tuple[Path, list[tuple[object, ...]], list[PolarPoint]]] = field(
        default_factory=dict
    )
    plots_tables: dict[str, Path] = field(default_factory=dict)
    qsteady_validity_of: dict[str, _qsteady.PointValidity] = field(default_factory=dict)
    #: The columns of an installed-frame copy already named as unplaced (FR-420 R2), so each
    #: is named once for the simulation.
    installed_unplaced: set[str] = field(default_factory=set)

    def target(self, path: Path) -> Path:
        """Archive what stands at ``path`` (or refuse it) and return the path to write."""
        return _refuse_an_existing_product(path, archive=self.archive, stamp=self.archive_stamp)

    def add(self, path: Path, entry: dict[str, object]) -> None:
        """Record one written product and its manifest entry."""
        self.written.append(path)
        self.written_names[path.relative_to(self.out).as_posix()] = entry

    def condition(self, point: PolarPoint, *, mach: float | None = None) -> dict[str, object]:
        """Return the flight condition one product row of ``point`` states."""
        return point_condition(
            point,
            mach=self.mach if mach is None else mach,
            cell=self.cell,
            clock=clock_rotor_facts(self.record_of.get(point.name), self.matrix_row, self.live),
        )

    def contributor_name(self, contributors: Sequence[PolarPoint]) -> str:
        """Return the name a table of ``contributors`` carries: the sweep's, or the point's."""
        varies = swept_axes([point.point or {} for point in contributors])
        record = self.record_of[contributors[0].name]
        return str(record.sweep_name if varies else record.point_name)


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
    check_frozen: bool = False,
    effective_pproc: tuple[str | None, PprocSpec | None, str | None] | None = None,
) -> tuple[list[Path], dict[str, dict[str, object]], dict[str, str]]:
    """Write one simulation's products from its admitted records.

    Returns the files written, the manifest entry of each (its run ids and,
    for a reduction, the reduction and the windows it used), and the
    reductions skipped by name with the reason.

    ``drafts`` collects this simulation's SUPERFILES (FR-89), one per group,
    which are written by the caller and not here: their header is the union
    over the whole campaign, so no simulation can know it on its own.
    """
    first = _simulation_metadata(records)
    skipped: dict[str, str] = {
        f"runs/{record.run_id}": (
            f"the run has status {record.status.value} and no pproc, Mach or reference "
            "metadata, so it cannot supply a product row; collect its complete run metadata"
        )
        for record in records
        if record.pproc is None and record.mach is None and not record.reference
    }
    pproc_id, pproc, pproc_error = effective_pproc or _effective_pproc(
        workspace, sim_id, first, matrix_row
    )
    if pproc is None:
        if pproc_error:
            skipped[sim_id] = pproc_error
        return [], {}, skipped
    admitted = _Admitted(skipped)
    sim_dir = workspace.sim_dir(sim_id)
    for record in records:
        if f"runs/{record.run_id}" not in skipped:
            _admit(admitted, record, sim_dir, matrix_row, pproc)
    if not admitted.points:
        # NOTHING COLLECTED YET, which is the ordinary state between `run` and
        # `collect` and is not an error: the stage writes no product for this
        # simulation and the campaign's other simulations are unaffected. It is
        # also what makes `recorded` non-empty below.
        return [], {}, skipped
    ctx = _resolve(
        workspace,
        sim_id,
        records,
        out,
        admitted,
        first=first,
        pproc=(pproc_id, pproc),
        archive=(archive, archive_stamp),
        matrix_row=matrix_row,
        sweep_rows=sweep_rows,
        drafts=drafts,
    )
    for step in _STEPS:
        step(ctx)
    return ctx.written, ctx.written_names, ctx.skipped


# ------------------------------------------------------------------ the context


def _resolve(
    workspace: CampaignWorkspace,
    sim_id: str,
    records: Sequence[RunRecord],
    out: Path,
    admitted: _Admitted,
    *,
    first: RunRecord,
    pproc: tuple[str | None, PprocSpec],
    archive: tuple[bool, datetime | None],
    matrix_row: MatrixRow | None,
    sweep_rows: Mapping[str, Mapping[str, object]] | None,
    drafts: list[SuperfileDraft] | None,
) -> SimContext:
    """Resolve what every step of one simulation reads, refusing what no product can carry."""
    points = admitted.points
    points.sort(key=lambda point: point.alpha_deg)
    mach = first.mach
    reference_block = first.reference
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
    _refuse_a_reference_the_solver_did_not_use(sim_id, points, reference)
    # BOUND BEFORE THE `products.polars` GATE, deliberately. Every product
    # family states the condition since item 5, so a pproc writing no polar
    # still needs this for its probes and its reduction (MC-06): binding the
    # names every family reads inside the polar branch was a NameError, and
    # then an UnboundLocalError, on `polars = false`, a real pproc setting.
    # THE MATRIX FIRST, THE RECORD SECOND. Item 16's window is a POST-PROCESSING
    # instruction and the user must be able to change it without re-running the
    # solver; `_matrix_window` resolves what the matrix says NOW against the
    # clock the record already carries. `_stated_window` remains the fallback,
    # so a point whose matrix no longer names a key reduces as it was run.
    window = _matrix_window(matrix_row, first) or _stated_window(first)
    if admitted.point_windows:
        # ANY point with a window makes this an averaged simulation; the first
        # record alone decided it, and a first point that failed to state its
        # clock took the polar away from every other point of the sweep.
        window = window or next(iter(admitted.point_windows.values()))
    # PFS-2038.03, GEO-039-F03. HERE, before the first product of this
    # simulation is written, and not in the reduction loop where the first
    # colliding file has already been written over the second. Two aliases
    # that a file name cannot tell apart are refused for the whole
    # simulation, so the refusal costs nothing to recover from.
    _refuse_aliases_a_file_name_cannot_tell_apart(admitted.plans, sim_id)
    table_name, super_name = _table_names(sim_id, points, admitted.record_of, matrix_row)
    cell = first.flight_condition if isinstance(first.flight_condition, Mapping) else None
    # BOUND BEFORE THE `products.polars` GATE, as `reference` is and for its reason:
    # the sections table and the reductions read both on a pproc that writes no
    # polar, and binding them inside the polar branch was an UnboundLocalError there.
    live = _live_reference(workspace, matrix_row)
    # THE LIVE REFERENCE'S ALIASES ARE THE LIVE ALIASES, an empty table
    # included: a reader who deleted the last alias meant it, and falling back
    # to the recorded table on "empty" resurrected a group that no longer
    # selects anything and published its row from the old membership.
    live_aliases = getattr(live, "aliases", None) if live is not None else None
    return SimContext(
        workspace=workspace,
        sim_id=sim_id,
        records=records,
        out=out,
        archive=archive[0],
        archive_stamp=archive[1],
        matrix_row=matrix_row,
        sweep_rows=sweep_rows,
        drafts=drafts,
        pproc_id=pproc[0],
        pproc=pproc[1],
        first=first,
        mach=mach,
        reference=reference,
        window=window,
        cell=cell,
        table_name=table_name,
        super_name=super_name,
        live=live,
        # ITEM 5 WIRED HERE. `point_condition` assembles the whole condition,
        # reported over requested, and `context_row` resolves each recorded
        # spelling onto its column.
        conditions=[
            point_condition(
                point,
                mach=mach,
                cell=cell,
                clock=clock_rotor_facts(admitted.record_of.get(point.name), matrix_row, live),
            )
            for point in points
        ],
        aliases=live_aliases if live_aliases is not None else first.aliases,
        skipped=admitted.skipped,
        points=points,
        record_of=admitted.record_of,
        sources=admitted.sources,
        exports=admitted.exports,
        plans=admitted.plans,
        point_windows=admitted.point_windows,
        frozen_points=admitted.frozen_points,
        probe_positions=admitted.probe_positions,
    )


def _table_names(
    sim_id: str,
    points: Sequence[PolarPoint],
    record_of: Mapping[str, RunRecord],
    matrix_row: MatrixRow | None,
) -> tuple[str, str]:
    """Return the polar table's name and the superfile's, from the names the run recorded."""
    # FR-85: ONE CONVENTION FOR THE WHOLE POINT. The table's rows are
    # the sweep, so the name is the point convention the scripts and
    # the exports already carry with the swept field written `sweep`,
    # and the fields the sweep held FIXED are carried as values. The
    # sweep is measured over the records rather than declared, so a
    # case whose sweep resolved to one point is named for the point
    # it has.
    swept = swept_axes([point.point or {} for point in points])
    # 0.21.0: THE NAMES ARE THE ONES THE RUN RECORDED. A record written before
    # 0.21.0 carries none, and naming its tables by a recomputed name would
    # set them beside files of another scheme.
    # Only contributors name the table. A skipped record can still name outputs,
    # but its failed export cannot rename the surviving points' polar.
    recorded = [record_of[point.name] for point in points]
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
    return table_name, super_name


# ------------------------------------------------------------------ step 1: the group polars


def _group_polars(ctx: SimContext) -> None:
    """Write the polar of each boundary group, its custom-format twin and its superfile rows."""
    if not ctx.pproc.products.polars:
        return
    # ITEM 17: AN UNSTEADY SIMULATION'S POLAR COMES FROM THE PLOTS, and the
    # group polars below are NOT written for it: the native coefficient export
    # states the LAST TIME STEP, which on an oscillating rotor is one instant of
    # a cycle, so a polar read from it is a polar of an instant. The unsteady
    # polar (step 5) reads the plots history and averages it over time, from the
    # plots tables step 2 has put on disk, so the scaling `write_plots_table`
    # applies is not performed a second time: two implementations of one
    # conversion is how two published numbers come to disagree.
    # THE GROUP POLARS ARE SKIPPED RATHER THAN WRITTEN FROM AN INSTANT. Writing
    # both would put two files with one name's worth of meaning in one folder,
    # and a reader would have no way to tell which of them the coefficients the
    # user is comparing came from.
    # THE ALIASES OF THE REFERENCE AS IT STANDS TODAY (PO-07). The group polars
    # resolved their members through the table frozen into the run record
    # while the rotor table beside them already read the live reference, so
    # renaming or extending an alias and posting again gave a polar of zeros,
    # or a plausible wrong sum, with no skip. A group's meaning is a
    # post-processing choice; the record stays the fallback.
    groups: Mapping[str, Sequence[int | str]] = ctx.pproc.groups
    if ctx.live is not None and getattr(ctx.live, "rotors", None):
        try:
            groups = rotor_integration_groups(getattr(ctx.live, "rotors", {}), ctx.pproc.groups)
        except PyflightstreamError as clash:
            ctx.skipped[f"{POLARS_DIR}/{ctx.sim_id}"] = str(clash)
    positions = {name: index for index, name in enumerate(groups, start=1)}
    for group, families in () if ctx.window is not None else groups.items():
        _group_polar(ctx, group, families, positions)


def _group_rows(
    ctx: SimContext, group: str, families: Sequence[int | str]
) -> tuple[list[PolarPoint], list[Mapping[str, object]], list[tuple[float, ...]], dict[str, str]]:
    """Return the points a group selects, their conditions and rows, and those it misses."""
    group_points: list[PolarPoint] = []
    group_conditions: list[Mapping[str, object]] = []
    rows: list[tuple[float, ...]] = []
    absent: dict[str, str] = {}
    for point, condition in zip(ctx.points, ctx.conditions, strict=True):
        if families and not select_group_members(
            list(families), list(point.loads.surfaces), ctx.aliases
        ):
            absent[point.name] = (
                f"point {point.name}: group {group!r} selects no surface of its loads "
                "export; no polar row is written. Check the alias against the "
                "reference's [aliases] table and recollect the complete loads export."
            )
            continue
        try:
            point_rows = group_polar_rows(
                [point], list(families), mach=ctx.mach, reference=ctx.reference, aliases=ctx.aliases
            )
        except ProductError as error:
            ctx.skipped[f"runs/{ctx.record_of[point.name].run_id}"] = (
                f"point {point.name}: {error}. Recollect this point's loads in the "
                "geometry analysis frame with its Reynolds number to settle it."
            )
            continue
        group_points.append(point)
        group_conditions.append(condition)
        rows.extend(point_rows)
    return group_points, group_conditions, rows, absent


def _group_polar(
    ctx: SimContext, group: str, families: Sequence[int | str], positions: Mapping[str, int]
) -> None:
    """One group's polar table, its superfile rows and its custom-format twin."""
    group_points, group_conditions, rows, absent = _group_rows(ctx, group, families)
    group_name = ctx.contributor_name(group_points) if group_points else ctx.table_name
    relative = f"{POLARS_DIR}/{swept_polar_file_name(ctx.sim_id, name=group_name, group=group)}"
    ctx.skipped.update({f"{relative}#{name}": reason for name, reason in absent.items()})
    if families and not any(
        select_group_members(list(families), list(point.loads.surfaces), ctx.aliases)
        for point in ctx.points
    ):
        # A NAMED SKIP, NEVER A ROW OF ZEROS. A group whose alias selects no
        # surface of any export of this simulation summed to 0.00000 in
        # every column: the token for "no value" is `NA`, and a table of
        # zeros is a table a reader believes.
        ctx.skipped[relative] = (
            f"group {group!r} names {', '.join(map(str, families))}, which selects no "
            f"surface of any loads export of simulation {ctx.sim_id!r} "
            f"({', '.join(sorted(ctx.points[0].loads.surfaces))}). Its polar table is not "
            "written. Check the alias against the reference's [aliases] table."
        )
        return
    if not group_points:
        return
    group_runs = [rid for point in group_points for rid in ctx.sources[point.name]]
    target = ctx.target(ctx.out / relative)
    # ONE ASSEMBLY. The rows the polar table is written from are the
    # rows the superfile carries, so they are built once here and
    # handed to both writers (FR-89).
    # EACH ROW'S DRAG SPLIT UNDER ITS OWN NAMES (FR-423): ``CD0, CDI`` up to
    # 26.124, ``CDV, CDP`` on 26.125, both with `NA` where the table mixes them.
    drags = [drag_columns_of(point.loads) for point in group_points]
    full = polar_table_rows(
        polar=ctx.sim_id,
        description=ctx.first.description or "",
        group=str(group),
        reference=ctx.reference,
        rows=rows,
        conditions=group_conditions,
        drag_columns=drags,
    )
    write_csv_table(target, polar_table_columns(drags), full)
    if ctx.drafts is not None:
        ctx.super_rows[str(group)] = (
            ctx.out
            / POLARS_DIR
            / super_file_name(
                ctx.sim_id,
                sweep=ctx.super_name if ctx.matrix_row is not None else group_name,
                group=group,
            ),
            full,
            group_points,
        )
    ctx.add(target, {"runs": group_runs})
    if ctx.pproc.products.custom_polar_format:
        # PFS-2014.01.01: the same rows, a second time, in the
        # format the existing tooling opens, beside the table.
        target = ctx.target(
            ctx.out
            / POLARS_DIR
            / swept_polar_file_name(ctx.sim_id, name=group_name, group=group, suffix=".dat")
        )
        coefficient_columns, coefficient_rows = drag_columned_rows(rows, drags)
        write_custom_polar_format(
            target,
            polar=ctx.sim_id,
            description=ctx.first.description or "",
            group=group,
            group_number=positions.get(group),
            mach=ctx.mach,
            reference=ctx.reference,
            rows=coefficient_rows,
            columns=coefficient_columns,
            # FR-94. The row's own label, off the matrix row this
            # polar belongs to. None where the workspace has no
            # matrix to read, which is every campaign authored in
            # Python, and the title is then what it always was.
            configuration=(
                ctx.matrix_row.variables.get(CONFIGURATION_VARIABLE)
                if ctx.matrix_row is not None
                else None
            ),
        )
        ctx.add(target, {"runs": group_runs})


# ------------------------------------------------------------------ step 2: each point's tables


def _point_products(ctx: SimContext) -> None:
    """Each point's sections, probes and plots tables and their reductions, point by point."""
    for point in ctx.points:
        sloads_path, plots_path, probes_path = ctx.exports[point.name]
        _sections_products(ctx, point, sloads_path)
        # F01: the recorded run type selects the source. An instant from an
        # older unsteady run cannot supply or replace a fluid-plots history.
        release = re.match(r"(\d+)\.(\d+)", ctx.record_of[point.name].package_version)
        legacy_profiles = bool(release and tuple(map(int, release.groups())) < (0, 25))
        _probes_products(ctx, point, probes_path, legacy_profiles)
        _plots_products(ctx, point, plots_path, legacy_profiles)


def _sections_products(ctx: SimContext, point: PolarPoint, sloads_path: Path | None) -> None:
    """Write a point's sections table, and the quasi-steady and harmonic products cut from it."""
    if not (ctx.pproc.products.sections and sloads_path is not None and sloads_path.is_file()):
        return
    record = ctx.record_of[point.name]
    relative = f"{SECTIONS_DIR}/{point.name}_sections.csv"
    target = ctx.target(ctx.out / relative)
    # ONE EXPORT, ONE PRODUCT (MT-01). A `ProductError` here used to leave
    # this function after the polars were already on disk: the caller then
    # recorded the whole SIMULATION as skipped, so the manifest disowned
    # files it had just written and a stale super file stayed beside a
    # fresh polar. The probe reader below has worked this way since 0.16.0.
    try:
        done = write_sections_table(
            target,
            sloads_path.read_text(encoding="utf-8", errors="replace"),
            # NO `point=` SINCE 0.23.0 ITEM 13: the polar's name is the
            # FILE's name and a column spent restating it told no row
            # from another. The iteration and the azimuth are read from
            # the export where it states them and are `NA` where it does
            # not, which is the honest answer for a steady distribution
            # and for a run that recorded no clock.
            mach=_mach_of(point, ctx.mach),
            # ITEM 5 WIRED HERE. A section is a distribution along a chord,
            # and a number beside no reference length is a number nobody can
            # check.
            reference=ctx.reference,
            advance_ratio=_advance_ratio_of(point),
            condition=ctx.condition(point),
            # WHICH ROWS ARE WHICH SURFACE, and where THAT rotor's blade one
            # is (0.24.0). The layout is the point's own record's, and so is
            # each rotor's speed: an RPM sweep turns a different angle per
            # step at each point.
            # THE TIME STEP OF AN UNSTEADY POINT, from its record. The export's
            # header counts the solver's INNER iterations there, summed over
            # every step: 2813 on a licensed run of 144 steps (RPT-053), from which the
            # azimuth was then computed.
            step=_last_time_step(record),
            unsteady=record.recipe in ("unsteady", "unsteady_rotor"),
            layout=record.sections_layout,
            rotors=_section_rotors(ctx.live, ctx.aliases, record),
            pol=ctx.sim_id,
        )
    except ProductError as error:
        ctx.skipped[relative] = str(error)
        return
    if done is not None:
        _sections_cut_products(ctx, point, done)


def _sections_cut_products(ctx: SimContext, point: PolarPoint, done: Path) -> None:
    """Carry a written sections table on: the wheel's validity, its harmonics and maps."""
    record = ctx.record_of[point.name]
    # 0.30.0: A QUASI-STEADY WHEEL POINT'S SECTIONS carry the 1P reduced
    # frequency of each station and the point's validity, and the point
    # keeps that validity for its clockings tables below. 0.31.0: and
    # every clocking's rows, each tabled by this same writer with this
    # point's layout and condition.
    ctx.qsteady_validity_of.update(
        _qsteady_sections(
            done,
            point,
            ctx.record_of.get(point.name),
            ctx.skipped,
            _the_sections_writer(
                mach=_mach_of(point, ctx.mach),
                reference=ctx.reference,
                advance_ratio=_advance_ratio_of(point),
                condition=ctx.condition(point),
                layout=record.sections_layout,
                rotors=_section_rotors(ctx.live, ctx.aliases, record),
                pol=ctx.sim_id,
            ),
        )
    )
    ctx.add(
        done,
        {
            "runs": ctx.sources[point.name],
            # ONE PHOTOGRAPH, AND THE MANIFEST SAYS SO (0.24.0). On an
            # unsteady point this table is the distribution at the step its
            # `STEP` column states and not an average over the window; the
            # history is `series/<point>_sections_series.csv`.
            "kind": "instant",
        },
    )
    # 0.31.0 (P0310-HARMONICS): A QUASI-STEADY WHEEL'S PER-STATION
    # HARMONICS, fitted over every blade at every clocking of the
    # table just written, read back as a user holds it.
    # 0.32.0 (P0320-G5-DISC-MAP): the same rows mapped over the disc.
    wheel_maps: list[tuple[Path, dict[str, object]]] = []
    harmonics = _wheel_harmonics(
        done,
        point,
        ctx.record_of.get(point.name),
        out=ctx.out,
        target=ctx.target,
        runs=ctx.sources[point.name],
        skipped=ctx.skipped,
        disc_maps=wheel_maps,
    )
    if harmonics is not None:
        ctx.add(harmonics[0], harmonics[1])
    for mapped_path, mapped_entry in wheel_maps:
        ctx.add(mapped_path, mapped_entry)


def _write_fields(
    ctx: SimContext, table: Path, point_name: str, *, step_source: Path | None = None
) -> None:
    """Write the field products of a probes table, where its record lays out a field."""
    from pyflightstream.post.probe_fields import point_field_products

    record = ctx.record_of.get(point_name)
    if record is None or not record.probe_field_layout:
        return
    try:
        fields = point_field_products(
            table, record, ctx.out, point_name, prepare=ctx.target, step_source=step_source
        )
    except (ValueError, OSError) as error:
        ctx.skipped[f"fields/{point_name}"] = str(error)
        return
    for path, entry in fields.items():
        ctx.add(path, {"runs": ctx.sources[point_name], **entry})
        if path.name.endswith(INFLOW_SUFFIX):
            write_installed_inflow(ctx, path, point_name)


def _probes_products(
    ctx: SimContext, point: PolarPoint, probes_path: Path | None, legacy_profiles: bool
) -> None:
    """Write a point's probe-points table; name the profiles an older unsteady point lacks.

    A steady point's, and an unsteady point's whose probes are NORMAL (FR-417
    R4): its probe-points export holds the last time step, which the table's
    `STEP` states.
    """
    record = ctx.record_of[point.name]
    unsteady = record.recipe in ("unsteady", "unsteady_rotor")
    probe_relative = f"{PROBES_DIR}/{point.name}_probes.csv"
    normal = _normal_probes(ctx, record, legacy_profiles)
    if unsteady and legacy_profiles:
        for entry in ctx.pproc.probes:
            if entry.points_file and entry.parameters:
                ctx.skipped[f"{probe_relative}#points_file={entry.points_file}"] = (
                    f"probe profile {entry.points_file!r} was sampled as an instant by "
                    f"pyflightstream {record.package_version}; no fluid-plots history was "
                    "recorded for these probes. Posting again cannot create history; "
                    "a new run is needed. Drawn probes keep their available history."
                )
    if normal and (probes_path is None or not probes_path.is_file()):
        ctx.skipped[probe_relative] = (
            "no probes table: missing probe points export. The probes of this unsteady "
            'point are normal (kind = "normal"), sampled once after the march; restore or '
            "collect the recorded probe points export, or run again if none was recorded."
        )
        return
    if (unsteady and not normal) or probes_path is None or not probes_path.is_file():
        return
    target = ctx.target(ctx.out / probe_relative)
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
            positions=ctx.probe_positions,
            # ITEM 5. A probe sample with no condition is a table about
            # nowhere, and this family carried none of the twenty-four
            # coefficients, so it states the WHOLE condition.
            condition=ctx.condition(point),
            reference=ctx.reference,
            pol=ctx.sim_id,
            # FR-417 R4: a normal probe holds the run's last time step.
            step=_last_time_step(record) if normal else None,
        )
    except ProductError as error:
        ctx.skipped[probe_relative] = str(error)
        return
    if done is not None:
        ctx.add(done, {"runs": ctx.sources[point.name]})
        write_installed_probes(ctx, done, point.name)
        _write_fields(ctx, done, point.name)


def _plots_products(
    ctx: SimContext, point: PolarPoint, plots_path: Path | None, legacy_profiles: bool
) -> None:
    """Write a point's plots table, the unsteady probes cut from it, and its reductions."""
    record = ctx.record_of[point.name]
    unsteady = record.recipe in ("unsteady", "unsteady_rotor")
    probe_relative = f"{PROBES_DIR}/{point.name}_probes.csv"
    plots = ctx.pproc.products.plots
    # FR-417: normal probes are not in the plots history; their table and
    # fields come from the probe-points export (`_probes_products`).
    fluid = unsteady and not _normal_probes(ctx, record, legacy_profiles)
    field_requested = fluid and bool(ctx.record_of.get(point.name) and record.probe_field_layout)
    probe_requested = fluid and (plots or field_requested) and bool(_probe_parameters(ctx.pproc))
    if probe_requested:
        ctx.skipped[probe_relative] = (
            "no probes table: missing plots history export. Restore or collect the "
            "recorded plots export; run again with fluid plots if no history was recorded."
        )
    if not ((plots or field_requested) and plots_path is not None and plots_path.is_file()):
        return
    relative = f"{PROBES_DIR}/{point.name}_plots.csv"
    target = ctx.target(ctx.out / relative)
    try:
        done = write_plots_table(
            target,
            _march_plots_text(ctx.workspace, ctx.record_of.get(point.name), plots_path),
            pol=ctx.sim_id,
        )
    except (ProductError, OSError) as error:
        # THE SAME RULE (MT-01): this point loses its plots table and the
        # reductions cut from it, named here, and nothing else.
        ctx.skipped[relative] = str(error)
        if probe_requested:
            ctx.skipped[probe_relative] = (
                f"no probes table: unreadable or empty plots history: {error}. "
                "Restore or collect a complete plots export; run again if none exists."
            )
        return
    if done is None:
        return
    ctx.add(done, {"runs": ctx.sources[point.name]})
    ctx.plots_tables[point.name] = done
    if fluid:
        _unsteady_probes(ctx, point, done, legacy_profiles, probe_requested=probe_requested)
    _point_reductions(
        done,
        ctx.plans[point.name],
        ctx.out,
        frozen=ctx.frozen_points.get(point.name),
        runs=ctx.sources[point.name],
        target=ctx.target,
        written=ctx.written,
        written_names=ctx.written_names,
        skipped=ctx.skipped,
        # ITEM 5, threaded from HERE because this is where the point
        # still is: `_point_reductions` takes a plots table and a
        # plan and reaches no record at all.
        condition=ctx.condition(point),
        reference=ctx.reference,
        # THE BLADES AND THE CLOCK OF EACH ROTOR (CR-04): the families
        # from the reference the row names, the clock from this point's
        # own record, as the sections table takes them.
        rotor_facts=_section_rotors(ctx.live, ctx.aliases, record),
        names=getattr(ctx.pproc, "names", None) or None,
        pol=ctx.sim_id,
        drift_limit_pct=_drift_limit_pct(ctx.pproc),
    )


def _unsteady_probes(
    ctx: SimContext,
    point: PolarPoint,
    plots_table: Path,
    legacy_profiles: bool,
    *,
    probe_requested: bool,
) -> None:
    """Write an unsteady point's probes table, cut from the fluid-plots history it wrote."""
    probe_relative = f"{PROBES_DIR}/{point.name}_probes.csv"
    probe_target = ctx.target(ctx.out / PROBES_DIR / f"{point.name}_probes.csv")
    probe_notes: list[str] = []
    try:
        field = write_unsteady_probes_table(
            probe_target,
            plots_table,
            positions=ctx.probe_positions,
            parameters=_probe_parameters(ctx.pproc, drawn_only=legacy_profiles),
            # ITEM 5. A probe sample with no condition is a table
            # about nowhere: the numbers in it are a flow field, and
            # which flow is exactly what the condition states.
            condition=ctx.condition(point),
            reference=ctx.reference,
            notes=probe_notes,
            pol=ctx.sim_id,
        )
    except (ProductError, OSError, ValueError) as error:
        ctx.skipped[probe_relative] = (
            f"no probes table: {error}. Restore the plots history and recorded "
            "probe positions, then post again."
        )
        field = None
    if field is not None:
        ctx.skipped.pop(probe_relative, None)
        # A PROBE THAT WAS RECORDED AND HAS NO HISTORY IS NAMED, under the
        # file's own name with a marker, like a names or equations block
        # that was not applied. Popping the skip above is right -- a table
        # WAS written -- and until this arm it also erased the only chance
        # to say the table is short.
        if probe_notes:
            ctx.skipped[f"{probe_relative}#positions"] = "; ".join(probe_notes)
            warn(
                f"{probe_relative}: " + "; ".join(probe_notes), PyflightstreamWarning, stacklevel=2
            )
        _write_fields(ctx, field, point.name, step_source=plots_table)
        ctx.add(field, {"runs": ctx.sources[point.name]})
        write_installed_probes(ctx, field, point.name)
    elif probe_requested and ctx.skipped[probe_relative].startswith("no probes table: missing"):
        # F01 REVIEW: the writer returns None when the history
        # carries no whole probe group, and until this line the
        # table was neither written nor named -- a product lost
        # in silence, where the probe-points route left a skip.
        # A point whose artifact declares NO probe at all is not
        # missing a product and gets no skip: this arm is only for
        # a pproc that asked for probes and got no table.
        declared = _probe_parameters(ctx.pproc, drawn_only=legacy_profiles)
        ctx.skipped[probe_relative] = (
            "no probes table: the plots history of this unsteady point carries "
            f"no whole probe group for "
            f"{', '.join(declared) if declared else 'no declared parameter'}"
            f" over {len(ctx.probe_positions)} recorded position(s). An unsteady row "
            "samples its probes through fluid plots, so the history is the only "
            "source; restore a complete history export or run "
            "again if this point should have one."
        )


# ------------------------------------------------------------------ step 3: the rotor tables


def _rotor_table_products(ctx: SimContext) -> None:
    """One coefficient table per rotor the reference declares (ITEM 6)."""
    # THE GEOMETRY COMES FROM THE REFERENCE FILE AND NOT FROM THE RECORD, which
    # is the route this item needed and did not have. A run leaves its reference
    # BLOCK -- areas, lengths, the moment point -- and a rotors block under
    # `reductions` carrying blades, rpm and steps; neither keeps the shaft, the
    # hub or the diameter, and a record does not even name its reference. The
    # matrix row does, the file is still in the workspace, and reading it costs
    # no new solver run. It runs after the per-point step because an unsteady
    # rotor reads the WRITTEN plots tables.
    for target_path, alias, plan in _rotor_tables(
        ctx.workspace,
        ctx.sim_id,
        ctx.points,
        ctx.records,
        ctx.sources,
        ctx.reference,
        ctx.matrix_row,
        ctx.out,
        plots=ctx.plots_tables,
        window=ctx.window,
        pproc=ctx.pproc,
        windows=ctx.point_windows,
        aliases=ctx.aliases,
        frozen=ctx.frozen_points,
        skipped=ctx.skipped,
    ):
        _rotor_table(ctx, target_path, alias, plan)


def _rotor_table(ctx: SimContext, target_path: Path, alias: str, plan: dict[str, object]) -> None:
    """Write one rotor's table and say which points it holds and what it averages."""
    destination = ctx.target(target_path)
    # THE PLAN'S OWN REJECTIONS PLUS THE WRITER'S, IN ONE LIST. Both halves
    # dropped points on a bare `continue` until 2026-09-18, so a table came
    # back shorter than the matrix with the manifest still naming every run.
    # NARROWED, not ignored. The plan is a `dict[str, object]` the planner
    # assembles, so its values arrive as `object` and `list(...)` on one is
    # a claim the checker is right to refuse.
    stated_left_out = plan.get("left_out")
    rotor_left_out: list[tuple[str, str]] = (
        list(stated_left_out) if isinstance(stated_left_out, list) else []
    )
    rotor_runs: list[str] = []
    done = write_rotor_table(
        destination,
        rotor=plan["rotor"],
        rows=plan["rows"],  # type: ignore[arg-type]
        reference=ctx.reference,
        left_out=rotor_left_out,
        written_runs=rotor_runs,
        pol=ctx.sim_id,
    )
    relative = destination.relative_to(ctx.out).as_posix()
    if done:
        ctx.written.append(destination)
        ctx.written_names[relative] = {
            # ONLY THE RUNS THIS TABLE ACTUALLY CONTAINS. It listed every
            # run of the simulation, so the provenance claimed points the
            # file does not hold -- which is worse than a short table,
            # because a reader checking the manifest is reassured.
            "runs": [rid for rid in rotor_runs if rid]
            or [rid for stem in ctx.sources for rid in ctx.sources[stem]],
            "rotor": alias,
            **_rotor_table_source(ctx, plan, rotor_runs),
        }
    if rotor_left_out:
        ctx.skipped[relative] = (
            f"these points of the sweep are not rows of the {alias} rotor table: "
            + "; ".join(reason for _rid, reason in rotor_left_out)
        )


def _rotor_table_source(
    ctx: SimContext, plan: Mapping[str, object], rotor_runs: Sequence[str]
) -> dict[str, object]:
    """Return what a rotor table's rows are: an average, an instant, a mean, a steady run."""
    # 0.31.0: THE k OF EVERY WRITTEN ROW THAT IS A WHEEL'S MEAN, for the entry.
    stated_rows = plan.get("rows")
    clockings_of_run = {
        str(row.get("run_id")): row["clockings"]
        for row in (stated_rows if isinstance(stated_rows, list) else [])
        if isinstance(row, Mapping)
        and isinstance(row.get("clockings"), int)
        and row.get("run_id") in rotor_runs
    }
    # AN AVERAGE OR THE SOLVER'S OWN EXPORT, AND THE MANIFEST SAYS WHICH
    # (RI-01), as the unsteady polar's entry does. A row that states a
    # window never holds an instant, so one entry describes every row.
    if plan.get("read_from") and ctx.window is not None:
        return {
            "source": f"the unsteady plots, time-averaged, of plot group {plan['read_from']}",
            "window": list(ctx.window),
            "windows": {name: list(span) for name, span in sorted(ctx.point_windows.items())},
        }
    # AN UNSTEADY RUN READ FROM ITS LOADS EXPORT HOLDS AN INSTANT, and
    # says so: that export states the LAST TIME STEP. A record that
    # states no window reaches here, and the entry called it a steady
    # run, with no `kind`, as a sections table's entry has.
    if any(str(r.recipe or "").startswith("unsteady") for r in ctx.records):
        return {
            "source": (
                "the loads export of an unsteady run: its LAST TIME STEP, one "
                "instant of a cycle, because the run states no averaging window"
            ),
            "kind": "instant",
        }
    # A QUASI-STEADY WHEEL'S ROWS ARE THE MEAN OF ITS k CLOCKINGS
    # (0.31.0), and the entry says so with the k: one number where
    # every row has the same, else each run's.
    if clockings_of_run:
        ks = set(clockings_of_run.values())
        return {
            "source": f"mean of {next(iter(ks))} clockings"
            if len(ks) == 1
            else "mean of k clockings",
            "clockings": next(iter(ks)) if len(ks) == 1 else dict(sorted(clockings_of_run.items())),
        }
    return {"source": "the loads export of a steady run"}


# ------------------------------------------------------------------ step 4: the quasi-steady rotor


def _qsteady_rotor_products(ctx: SimContext) -> None:
    """Write the quasi-steady rotor's clockings, their average, and the correction route."""
    # 0.30.0: THE QUASI-STEADY ROTOR'S CLOCKINGS AND THEIR AVERAGE, one pair of
    # tables per simulation, from the record each point's run wrote beside its
    # loads export.
    for target_path, entry in _qsteady_products(
        ctx.sim_id,
        ctx.points,
        ctx.record_of,
        reference=ctx.reference,
        out=ctx.out,
        validity_of=ctx.qsteady_validity_of,
        condition_of=lambda point: ctx.condition(point, mach=_mach_of(point, ctx.mach)),
        target=ctx.target,
        skipped=ctx.skipped,
    ):
        ctx.add(target_path, entry)
    # 0.31.0 (P0310-CAL): THE QUASI-STEADY WHEEL'S CORRECTION ROUTE AND ITS
    # DIAGNOSTIC, each corrected product a new file beside its raw one, read back
    # from the files written above and never written over them. Off by default.
    for target_path, entry in _qsteady_corrections(
        ctx.workspace,
        ctx.sim_id,
        ctx.points,
        ctx.record_of,
        pproc=ctx.pproc,
        out=ctx.out,
        written_names=ctx.written_names,
        target=ctx.target,
        skipped=ctx.skipped,
    ):
        ctx.add(target_path, entry)


# ------------------------------------------------------------------ step 5: the unsteady polar


def _unsteady_polar_products(ctx: SimContext) -> None:
    """Write the POLAR of an unsteady simulation: its plots history averaged over the window.

    ITEM 17, AT THE OUTER NESTING AND NOT INSIDE THE SUPERFILE GUARD: there, on
    every unsteady simulation the group polars were skipped AND this writer was
    never reached, and the point ended with NO POLAR OF ANY KIND. A caller inside
    a branch that cannot be true is not a caller. It reads the WRITTEN plots
    tables rather than the raw export, so the reference-velocity scaling is
    performed in one place.
    """
    if ctx.window is None:
        return
    left_out: list[str] = []
    notes: list[str] = []
    name_notes: list[str] = []
    equation_notes: list[str] = []
    unsteady_name = unsteady_polar_file_name(ctx.sim_id, name=ctx.table_name)

    def unsteady_destination(names: Sequence[str]) -> Path:
        nonlocal unsteady_name
        contributing = [point for point in ctx.points if point.name in names]
        unsteady_name = unsteady_polar_file_name(
            ctx.sim_id, name=ctx.contributor_name(contributing)
        )
        return ctx.target(ctx.out / POLARS_DIR / unsteady_name)

    # THE FILE 0.23.0 WROTE UNDER THE OLD NAME IS ARCHIVED, NOT LEFT BESIDE THIS
    # ONE. A rebuild moves what it is about to replace, and it replaces by
    # PATH: a product whose name changed would otherwise stay in the folder,
    # stale, under a name the manifest no longer knows.
    former = ctx.out / POLARS_DIR / f"{ctx.sim_id}_{ctx.table_name}_unsteady.csv"
    if former.is_file():
        ctx.target(former)
    pproc = ctx.pproc
    done = write_unsteady_polar(
        ctx.out / POLARS_DIR / unsteady_name,
        points=ctx.points,
        plots=ctx.plots_tables,
        window=ctx.window,
        windows=ctx.point_windows,
        frozen=ctx.frozen_points,
        setup=_setup_content(
            ctx.points,
            ctx.sources,
            ctx.records,
            ctx.matrix_row,
            ctx.sweep_rows,
            workspace=ctx.workspace,
        ),
        conditions=ctx.conditions,
        reference=ctx.reference,
        left_out=left_out,
        notes=notes,
        axes_groups=global_frame_plot_groups(
            pproc,
            inventory=list(
                dict.fromkeys(
                    family
                    for point in ctx.points
                    if point.loads is not None
                    for family in point.loads.surfaces
                )
            ),
            aliases=ctx.aliases,
        ),
        equations=getattr(pproc, "equations", None) or None,
        equation_order=pproc.equation_order() if getattr(pproc, "equations", None) else None,
        equation_notes=equation_notes,
        names=getattr(pproc, "names", None) or None,
        name_notes=name_notes,
        contributor_path=unsteady_destination,
        pol=ctx.sim_id,
    )
    if done is not None:
        _say_what_the_unsteady_polar_left(
            ctx, f"{POLARS_DIR}/{unsteady_name}", name_notes, equation_notes, notes
        )
    # EVERY POINT THAT IS NOT A ROW IS NAMED, with its reason. A sweep table
    # quietly shorter than the matrix says nothing about which points went
    # or why, which is a blank cell one level up.
    if left_out:
        ctx.skipped[f"{POLARS_DIR}/{unsteady_name}"] = (
            "these points of the sweep are not rows of the unsteady polar: " + "; ".join(left_out)
        )
    if done is not None:
        ctx.add(
            done,
            {
                # ONLY THE POINTS THE FILE HOLDS (MT-03). It listed every run of
                # the simulation while the writer left points out, so the
                # provenance vouched for rows that are not there.
                "runs": sorted(
                    run
                    for name, names in ctx.sources.items()
                    if not any(left.startswith(f"{name}:") for left in left_out)
                    for run in names
                ),
                "source": "the unsteady plots, time-averaged",
                "window": list(ctx.window),
                # PER POINT where the points do not share one, so the manifest
                # never states one window for a file that holds two.
                "windows": {name: list(span) for name, span in sorted(ctx.point_windows.items())},
            },
        )


def _say_what_the_unsteady_polar_left(
    ctx: SimContext,
    relative: str,
    name_notes: Sequence[str],
    equation_notes: Sequence[str],
    notes: Sequence[str],
) -> None:
    """Say, under the file's own name with a marker, each block the unsteady polar left out."""
    # THE DICTIONARY, like the two blocks below: what was not applied is SAID.
    if name_notes:
        ctx.skipped[f"{relative}#names"] = "; ".join(name_notes)
        warn("; ".join(name_notes), PyflightstreamWarning, stacklevel=2)
    # THE EQUATIONS BLOCK, like the axes block: what is not written is SAID,
    # under the file's own name with a marker, and warned, because a derived
    # column a user asked for and did not get must not be found by accident.
    if equation_notes:
        ctx.skipped[f"{relative}#equations"] = "; ".join(equation_notes)
        warn(f"{relative}: " + "; ".join(equation_notes), PyflightstreamWarning, stacklevel=2)
    # A BLOCK THAT IS NOT WRITTEN IS SAID (0.24.0), under the file's own name
    # with a marker, so it is never mistaken for the file being absent.
    if notes:
        ctx.skipped[f"{relative}#axes"] = "; ".join(notes)
        warn(f"{relative}: " + "; ".join(notes), PyflightstreamWarning, stacklevel=2)


# ------------------------------------------------------------------ step 6: the superfile rows


def _superfile_drafts(ctx: SimContext) -> None:
    """Each group's superfile rows, one per point, drafted for the campaign to write (FR-89).

    HERE, after the plots tables of every point of this simulation are on disk:
    the superfile is written after the unsteady post-process, which is what
    makes one row per converged point possible at all.
    """
    if ctx.drafts is None or not ctx.super_rows:
        return
    by_run = {record.run_id: record for record in ctx.records}
    last_step: dict[str, Mapping[str, str]] = {}
    for name, table in ctx.plots_tables.items():
        _columns, table_rows = read_csv_table(table)
        step = plots_last_row(table_rows)
        if step is not None:
            last_step[name] = step
    for group, (path, full, group_points) in ctx.super_rows.items():
        wide = [
            superfile_row(
                polar_columns=polar_table_columns(
                    [drag_columns_of(point.loads) for point in group_points]
                ),
                polar_values=polar_values,
                matrix_row=ctx.matrix_row,
                # NO FALLBACK TO ANOTHER POINT'S RECORD. This read
                # `by_run.get(run_id, records[0])` until 2026-09-11, so a run id
                # that did not resolve silently took an ARBITRARY other point of
                # the same simulation and wrote ITS flight condition into this
                # row; a reader sees a missing cell and cannot see a wrong one.
                # `sources` and `by_run` are built from the same records, so the
                # branch is not shown reachable; what the right thing is, is
                # pinned by
                # `test_a_point_whose_record_is_missing_borrows_no_other_points_values`.
                record=by_run.get((ctx.sources.get(point.name) or [""])[0]),
                sweep_row=(ctx.sweep_rows or {}).get((ctx.sources.get(point.name) or [""])[0]),
                plots_row=last_step.get(point.name),
            )
            for point, polar_values in zip(group_points, full, strict=True)
        ]
        # 0.30.0: A QUASI-STEADY WHEEL POINT'S ROW CARRIES ITS VALIDITY, the
        # columns its clockings tables carry, after every key the row holds.
        for point, row in zip(group_points, wide, strict=True):
            for validity_column, validity_cell in _qsteady_super_cells(
                point, ctx.record_of.get(point.name), ctx.qsteady_validity_of
            ).items():
                row.setdefault(validity_column, validity_cell)
            # FR-348: from the inventory only, and placed last by the writer.
            row[MESH_FACES_COLUMN] = _mesh_faces_of(
                ctx.workspace, by_run.get((ctx.sources.get(point.name) or [""])[0]), point.name
            )
        ctx.drafts.append(
            SuperfileDraft(
                path=path,
                rows=tuple(wide),
                # ITEM 7 WIRED HERE, on the DRAFT, because this is where
                # the pproc is: the campaign writer has no pproc in scope
                # and one campaign can name several.
                fmt=ctx.pproc.products.superfile_format,
                entry={
                    # The same keys `write_campaign_products` stamps on
                    # every other product's entry (PFS-2031.04 reads `sim_id`).
                    "sim_id": ctx.sim_id,
                    "pproc": ctx.pproc_id,
                    "runs": [(ctx.sources.get(p.name) or [""])[0] for p in group_points],
                    "group": group,
                },
            )
        )


#: The steps of one simulation's post, in the order the manifest has always had.
_STEPS: tuple[Callable[[SimContext], None], ...] = (
    _group_polars,
    _point_products,
    _rotor_table_products,
    _qsteady_rotor_products,
    _unsteady_polar_products,
    _superfile_drafts,
)


def _normal_probes(ctx: SimContext, record: RunRecord, legacy_profiles: bool) -> bool:
    """Whether an unsteady point sampled its pproc's probes as NORMAL probe points (FR-417).

    A record written before 0.25.0 sampled its profiles as an instant of its own
    and is read as it always was (``legacy_profiles``).
    """
    return (
        record.recipe in ("unsteady", "unsteady_rotor")
        and not legacy_profiles
        and ctx.pproc.samples_normal_probes()
    )


def _probe_parameters(pproc, *, drawn_only: bool = False) -> tuple[str, ...]:
    """Return the fluid parameters this artifact's probe entries ask for (FR-91).

    In declaration order, de-duplicated, across every `[[probes]]` entry,
    because the numbered groups of an unsteady plots export are composed
    from these names and the vertex counter runs across the entries.

    Each vertex keeps its available parameters; other parameter cells are NA.
    """
    out: list[str] = []
    for entry in getattr(pproc, "probes", None) or []:
        if drawn_only and entry.points_file:
            continue
        for parameter in getattr(entry, "parameters", None) or []:
            if parameter not in out:
                out.append(parameter)
    if getattr(pproc, "volume_section", None) is not None:
        out.extend(name for name in ("VX", "VY", "VZ") if name not in out)
    return tuple(out)


def _setup_content(
    points: Sequence[PolarPoint],
    sources: Mapping[str, Sequence[str]],
    records: Sequence[RunRecord],
    matrix_row: MatrixRow | None,
    sweep_rows: Mapping[str, Mapping[str, object]] | None,
    *,
    workspace: CampaignWorkspace,
) -> dict[str, dict[str, str]]:
    """Return the SUPER content of each point by name, through the super file's own assembly.

    `superfile_row` seeded with the point's axes and no plots block carries every flag
    of the setup and whatever the simulation knows that the polar does not: the
    record's condition and scalars, the matrix row's cells, each rotor's speed,
    the campaign sweep row and the solver flags. One assembly, so the steady super
    file and the unsteady polar cannot drift in what they call the setup. The
    face count of the point's geometry is added as the super file adds it (FR-348).
    """
    by_run = {record.run_id: record for record in records}
    content: dict[str, dict[str, str]] = {}
    for point in points:
        run_id = (sources.get(point.name) or [""])[0]
        content[point.name] = superfile_row(
            polar_columns=("ALPHA", "BETA", ADVANCE_RATIO_COLUMN),
            polar_values=(point.alpha_deg, point.beta_deg, _advance_ratio_of(point)),
            matrix_row=matrix_row,
            record=by_run.get(run_id),
            sweep_row=(sweep_rows or {}).get(run_id),
            plots_row=None,
        )
        content[point.name][MESH_FACES_COLUMN] = _mesh_faces_of(
            workspace, by_run.get(run_id), point.name
        )
    return content


def _mesh_faces_of(workspace: CampaignWorkspace, record: RunRecord | None, point: str) -> str:
    """Return the face count the inventory states for the geometry a record's run opened (FR-348).

    Taken from the inventory, never counted here: the library's inventory of
    each file the run staged, then the simulation's staged copy, whenever it
    states the field. Where its ``mesh_sha256`` is not the sha256 the record
    holds for that file, the post log WARNS naming both, and the count is
    still carried (a warning, never a refusal). A blank, written ``NA``, where
    no record or no inventory states it.
    """
    if record is None:
        return ""
    staged = workspace.sim_dir(record.sim_id) / "inputs"

    def sidecars(name: str) -> list[Path]:
        found = [staged / name]
        try:
            found.insert(0, workspace.resolve_geometry(name))
        except (PyflightstreamError, OSError):
            pass
        return [inventory_sidecar(path) for path in found]

    faces = recorded_mesh_faces(record.inputs_sha256, sidecars)
    if faces is None:
        return ""
    if not faces.same_bytes:
        warn(
            f"point={point} product={MESH_FACES_COLUMN}: the inventory {faces.sidecar} states "
            f"mesh_faces = {faces.mesh_faces} counted in mesh_sha256 {faces.counted_sha256}, "
            f"and run "
            f"{record.run_id} recorded sha256 {faces.recorded_sha256} for {faces.name}; the count "
            "is carried as the inventory states it. Take the inventory again "
            "(pyfs-matrix inventory <geometry> --overwrite) if the geometry changed (FR-348).",
            PyflightstreamWarning,
            stacklevel=2,
        )
    return str(faces.mesh_faces)
