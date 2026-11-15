"""The post of one simulation: one resolved context, then the product families in order.

A private module of :mod:`pyflightstream.post` (AD-13). The first part
RESOLVES what the simulation's records state into one frozen
:class:`SimContext`, and the steps that each write one family from it, called
in manifest order:

1. :func:`_point_products`, per point: its sections table and the
   quasi-steady and harmonic products cut from it, its probes table, its
   plots table, the unsteady probes and the reductions
   (:mod:`pyflightstream.post.point_tables`,
   :mod:`pyflightstream.post._reduction_stage`);
2. :func:`_qsteady_rotor_products`: the quasi-steady clockings and their average;
3. :func:`_family_polars`: the polar's family and group files, steady or the
   window average of an unsteady run's plots, and the polars derived from them
   (:mod:`pyflightstream.post._polar_stage`, PFS-2231);
4. :func:`_qsteady_correction_products`: the quasi-steady wheel's correction
   route, read back from the files above, the rotor's RCOEF file among them.

The byte snapshot of the products (``tests/tier1_offline/test_products_snapshot.py``,
P0330-PRODUCTS-SNAPSHOT) was taken before the decomposition and is unchanged
by it. A product family of the backlog joins as one more step here, reading
the context and writing into its sinks.

Size exemption: one context and every product step of a simulation, each step one family.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pyflightstream._deprecations import removed_names_hook
from pyflightstream._errors import (
    ProductExistsError,
    PyflightstreamError,
    PyflightstreamWarning,
    warn,
)
from pyflightstream._tokens import MESH_FACES_COLUMN
from pyflightstream.cases import PprocSpec
from pyflightstream.post import qsteady as _qsteady
from pyflightstream.post._admit import (
    _admit,
    _Admitted,
)
from pyflightstream.post._condition import (
    _advance_ratio_of,
    _effective_pproc,
    _in_coefficients,
    _last_time_step,
    _live_reference,
    _mach_of,
    _matrix_window,
    _refuse_a_reference_the_solver_did_not_use,
    _section_rotors,
    _simulation_metadata,
    _stated_window,
    clock_rotor_facts,
    declined_profile_drag_125,
    point_condition,
    row_rotor_speeds,
)
from pyflightstream.post._installed_copies import (
    INFLOW_SUFFIX,
    write_installed_inflow,
    write_installed_probes,
)
from pyflightstream.post._noise_products import noise_products
from pyflightstream.post._point_stage import (
    finish_sections,
    rotor_ids_of,
    run_block_scope,
    split_of,
)
from pyflightstream.post._reduction_stage import _drift_limit_pct, _point_reductions
from pyflightstream.post._rotor_products import (
    _qsteady_corrections,
    _qsteady_products,
    _qsteady_sections,
    _the_sections_writer,
    _wheel_harmonics,
)
from pyflightstream.post._stage import (
    PROBES_DIR,
    SECTIONS_DIR,
    TIME_HISTORY_DIR,
    _refuse_aliases_a_file_name_cannot_tell_apart,
    failure_reason,
)
from pyflightstream.post._structure import (
    placement_check_products,
    structure_products,
)
from pyflightstream.post._tables import (
    ProductError,
    ReferenceValues,
    _march_plots_text,
)
from pyflightstream.post._tree_migration import earlier_path
from pyflightstream.post.farfield_products import farfield_products
from pyflightstream.post.point_tables import (
    export_tables,
    write_plots_table,
    write_probes_table,
    write_sections_table,
    write_unsteady_probes_table,
)
from pyflightstream.post.polar import (
    PolarPoint,
    swept_axes,
)
from pyflightstream.post.provenance import refuse_an_existing_product as _refuse_an_existing_product
from pyflightstream.post.superfile import (
    SuperfileDraft,
)
from pyflightstream.results import FrozenSolve
from pyflightstream.workspace.sidecars import (
    OBJ_SUFFIX,
    boundaries_for_matrix,
    recorded_mesh_faces,
)

if TYPE_CHECKING:
    from pyflightstream.cases.matrix import MatrixRow
    from pyflightstream.results import FrozenSolve
    from pyflightstream.workspace import CampaignWorkspace, RunRecord


@dataclass(frozen=True)
class SimContext:
    """What the first part of one simulation's post resolves, and where its steps write.

    Frozen: a step reads what was resolved and cannot rebind it. The SINKS
    (``written``, ``written_names``, ``skipped``, and ``super_rows``,
    ``plots_tables`` and ``qsteady_validity_of``, which a later step reads
    back) are containers the steps fill in manifest order.

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
    super_rows: dict[
        str, tuple[Path, tuple[str, ...], list[tuple[object, ...]], list[PolarPoint]]
    ] = field(default_factory=dict)
    plots_tables: dict[str, Path] = field(default_factory=dict)
    qsteady_validity_of: dict[str, _qsteady.PointValidity] = field(default_factory=dict)
    #: FR-1062: per point, the far-field cells of its super-file row.
    farfield_super: dict[str, dict[str, str]] = field(default_factory=dict)
    farfield_off_window: list[str] = field(default_factory=list)
    #: The columns of an installed-frame copy already named as unplaced (FR-898), so each
    #: is named once for the simulation.
    installed_unplaced: set[str] = field(default_factory=set)
    #: FR-460: each point's streamline exports, by kind.
    streamlines: dict[str, dict[str, Path]] = field(default_factory=dict)
    structure_tips: dict[str, list[tuple[float, float]]] = field(default_factory=dict)
    #: The post was asked to replace what it finds (``overwrite``): a product written
    #: outside the products folder, the per-point validity file, is replaced only then.
    overwrite: bool = False

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
            clock=clock_rotor_facts(
                self.record_of.get(point.name),
                self.matrix_row,
                self.live,
                own_speeds=row_rotor_speeds(self.record_of.get(point.name), point.loads_path),
            ),
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
        overwrite=overwrite,
        matrix_row=matrix_row,
        sweep_rows=sweep_rows,
        drafts=drafts,
    )
    with run_block_scope(ctx):
        _run_steps(ctx, _STEPS)
    return ctx.written, ctx.written_names, ctx.skipped


def _run_steps(ctx: SimContext, steps: Sequence[Callable[[SimContext], None]]) -> None:
    """Run the steps of one simulation's post, each costing only itself on a failure."""
    for step in steps:
        # EACH STEP COSTS ONLY ITSELF: a refusal after step one must not orphan the products
        # already written (their predecessors archived, their manifest entries lost) nor
        # stop the steps that read other things. The step is named by its family and the
        # simulation, as every other skip of a simulation is keyed.
        # AN UNEXPECTED FAILURE COSTS THE STEP TOO (FR-2313): a defect in one product
        # must not take the independent products of the post with it; it is named with
        # its type, so it reads as the defect it is and not as a refusal.
        try:
            scoped = _load_step_context(ctx, step)
            if scoped is ctx or scoped.points:
                step(scoped)
        except (ProductExistsError, Warning):
            # An existing product refuses the post; a warning raised as an error is
            # the caller's filter, and it stays the caller's.
            raise
        except Exception as error:  # noqa: BLE001 -- every failure is named, never fatal here
            family = step.__name__.lstrip("_")
            said = failure_reason(error)
            ctx.skipped[f"{family}/{ctx.sim_id}"] = said
            warn(
                f"simulation={ctx.sim_id} step={family}: {said}",
                PyflightstreamWarning,
                stacklevel=2,
            )


# ------------------------------------------------------------------ the context


def _load_step_context(ctx: SimContext, step: Callable[[SimContext], None]) -> SimContext:
    """Scope load-table consumers without suppressing independent export products."""
    if step not in (_family_polars, _qsteady_rotor_products, _qsteady_correction_products):
        return ctx
    if step is _family_polars and ctx.window is not None:
        # AN UNSTEADY POLAR IS READ FROM THE PLOTS, not from the loads export.
        return ctx
    selected = [
        (point, condition)
        for point, condition in zip(ctx.points, ctx.conditions, strict=True)
        if _in_coefficients(point.loads)
    ]
    return replace(
        ctx, points=[point for point, _ in selected], conditions=[state for _, state in selected]
    )


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
    overwrite: bool = False,
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
        overwrite=overwrite,
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
                clock=clock_rotor_facts(
                    admitted.record_of.get(point.name),
                    matrix_row,
                    live,
                    own_speeds=row_rotor_speeds(
                        admitted.record_of.get(point.name), point.loads_path
                    ),
                ),
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
        streamlines=admitted.streamlines,
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
    # Use recorded point and sweep names; recomputing absent names could
    # place tables beside files of another naming scheme. Only contributing
    # points name the table: a failed export cannot rename surviving products.
    recorded = [record_of[point.name] for point in points]
    if any(record.sweep_name is None or record.point_name is None for record in recorded):
        raise ProductError(
            f"simulation {sim_id!r} holds records with no "
            "point_name or sweep_name; those fields are required. See docs/upgrading.md "
            "to reach the 0.38.0 format before running `pyfs-workspace migrate`."
        )
    table_name = str(recorded[0].sweep_name) if swept else str(recorded[0].point_name)
    # FR-89: the SUPERFILE is about the sweep the ROW DECLARES, which is the one
    # place its name differs from the polar table's beside it: a row declaring
    # a one-value sweep still names it `+sweep`. With no matrix row in reach it
    # follows the table.
    super_name = str(recorded[0].sweep_name) if matrix_row is not None or swept else table_name
    return table_name, super_name


# ------------------------------------------------------------------ step 1: the polar files


def _family_polars(ctx: SimContext) -> None:
    """Write the polar's family and group files and their derived polars (PFS-2231).

    One form for every run type (:mod:`pyflightstream.post._polar_stage`): a steady
    point's rows are its loads export, an unsteady point's the window average of
    its plots. The files of 0.57.0 (the per-group polars, the superfile, the
    unsteady polar, the rotor tables) are not written.
    """
    if not ctx.pproc.products.polars:
        return
    if ctx.window is None:
        for point in ctx.points:
            # A DECLINED SURFACE ON 26.125 PRINTS CDp 0 (RPT-166, P0400-DECLINED125):
            # said once per point, naming the surfaces and the build.
            declined_125 = declined_profile_drag_125(point.loads, point.vorticity_selection)
            if declined_125:
                warn(
                    f"point={point.name} product=polars: the solver (build 26.125) printed CDp "
                    f"exactly 0 for {', '.join(declined_125)}, on the vorticity induced-drag list "
                    "(SET_VORTICITY_DRAG_BOUNDARIES); a boundary there without a defined "
                    "trailing edge is not computed. The axis drag columns that sum it are "
                    "written as the export printed them, short by the drag not computed. "
                    "Give the surface a trailing edge or leave it off the list.",
                    PyflightstreamWarning,
                    stacklevel=2,
                )
    from pyflightstream.post._polar_stage import family_polar_products

    family_polar_products(ctx)


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
        probe_ctx = _recorded_probe_defaults(ctx, ctx.record_of[point.name])
        _probes_products(probe_ctx, point, probes_path, legacy_profiles)
        _plots_products(probe_ctx, point, plots_path, legacy_profiles)
        # FR-1083: the streamline products of the point, from its exports.
        from pyflightstream.post.streamlines import write_point_streamlines

        write_point_streamlines(ctx, point.name)


def _recorded_probe_defaults(ctx: SimContext, record: RunRecord) -> SimContext:
    """Keep the pre-0.45.1 sampling default when reading an older run's history."""
    release = re.match(r"(\d+)\.(\d+)(?:\.(\d+))?", record.package_version)
    if (
        record.recipe not in ("unsteady", "unsteady_rotor")
        or release is None
        or tuple(int(part or 0) for part in release.groups()) >= (0, 45, 1)
    ):
        return ctx
    probes = [
        entry
        if "kind" in entry.model_fields_set
        else entry.model_copy(update={"kind": "instantaneous"})
        for entry in ctx.pproc.probes
    ]
    return replace(ctx, pproc=ctx.pproc.model_copy(update={"probes": probes}))


def _sections_products(ctx: SimContext, point: PolarPoint, sloads_path: Path | None) -> None:
    """Write a point's sections table, and the quasi-steady and harmonic products cut from it."""
    if not (ctx.pproc.products.sections and sloads_path is not None and sloads_path.is_file()):
        return
    record = ctx.record_of[point.name]
    relative = f"{SECTIONS_DIR}/{point.name}_sections.csv"
    target = ctx.target(ctx.out / relative)
    # MT-01: scope ProductError to this export's product. Products already
    # written for the simulation must retain their manifest entries when
    # another export is unreadable.
    family_files: list[Path] = []
    try:
        split = split_of(ctx)
        done = write_sections_table(
            target,
            sloads_path.read_text(encoding="utf-8", errors="replace"),
            # The filename identifies the polar. Read iteration and azimuth from
            # the export where stated, otherwise write NA, including a steady
            # distribution or a run with no recorded clock.
            mach=_mach_of(point, ctx.mach),
            # ITEM 5 WIRED HERE. A section is a distribution along a chord,
            # and a number beside no reference length is a number nobody can
            # check.
            reference=ctx.reference,
            advance_ratio=_advance_ratio_of(point),
            condition=ctx.condition(point),
            # WHICH ROWS ARE WHICH SURFACE, and where THAT rotor's blade one
            # is. The layout is the point's own record's, and so is
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
            inventory=record.inventory,
            rotor_ids=rotor_ids_of(ctx),
            split=split,
            family_files=family_files,
        )
    except (ProductError, OSError) as error:
        ctx.skipped[relative] = str(error)
        return
    if done is None:
        _retire_unwritten(
            ctx,
            relative,
            target,
            "the sectional loads export declares no section, so no sections table is written",
        )
        return
    _sections_cut_products(ctx, point, done)
    finish_sections(ctx, point, done, family_files, split)


def _retire_unwritten(ctx: SimContext, relative: str, target: Path, reason: str) -> None:
    """Name a product the writer did not write, where a previous one would stay current.

    A post without the archive prepares a destination by leaving the previous
    product in place for the writer to overwrite. A writer that writes nothing
    (an export with no section, a history with no step) then left that file on
    disk, unnamed by the new manifest and read as current. Named in ``skipped``,
    it is retired by the post's retirement, which removes it. The reason is named whether or
    not a previous table exists: a product that was never written says why too.
    """
    ctx.skipped[relative] = (
        f"{reason}; the previous table is retired" if target.exists() else reason
    )


def _sections_cut_products(ctx: SimContext, point: PolarPoint, done: Path) -> None:
    """Carry a written sections table on: the wheel's validity, its harmonics and maps."""
    record = ctx.record_of[point.name]
    # A quasi-steady wheel's sections carry each station's 1P reduced
    # frequency and the point's validity. Preserve that validity for the
    # clocking tables; use this writer, layout and condition for every clocking.
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
            sim_dir=ctx.workspace.sim_dir(ctx.sim_id),
        )
    )
    ctx.add(
        done,
        {
            "runs": ctx.sources[point.name],
            # ONE PHOTOGRAPH, AND THE MANIFEST SAYS SO. On an
            # unsteady point this table is the distribution at the step its
            # `STEP` column states and not an average over the window; the
            # history is `series/<point>_sections_series.csv`.
            "kind": "instant",
        },
    )
    # P0310-HARMONICS: A QUASI-STEADY WHEEL'S PER-STATION
    # HARMONICS, fitted over every blade at every clocking of the
    # table just written, read back as a user holds it.
    # P0320-G5-DISC-MAP: the same rows mapped over the disc.
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
        sim_dir=ctx.workspace.sim_dir(ctx.sim_id),
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
    source_kind = "unsteady-fluid-plot" if step_source is not None else "steady-probe"
    layouts = [
        layout
        for layout in record.probe_field_layout
        if layout.get("export_kind", source_kind) == source_kind
        and (layout.get("formats") or layout.get("reusable_inflow"))
    ]
    if not layouts:
        return
    record = record.model_copy(update={"probe_field_layout": layouts})
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
    FR-887): its probe-points export holds the state at the end of the march
    (RPT-153, "normal probes after an unsteady march on 26.124", 2026-10-05; not the
    same sample as the last fluid-plot step), which the table's `STEP` states.
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
            'point are normal (kind = "default"), sampled once after the march; restore or '
            "collect the recorded probe points export, or run again if none was recorded."
        )
        return
    if (unsteady and not normal) or probes_path is None or not probes_path.is_file():
        return
    target = ctx.target(ctx.out / probe_relative)
    # PFS-2031.16: an unreadable probe export is a skip of its product,
    # not of the simulation's whole stage. Preserve its independent polar
    # and other readable products.
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
            # FR-887: a normal probe holds the run's last time step.
            step=_last_time_step(record) if normal else None,
        )
    except (ProductError, OSError) as error:
        ctx.skipped[probe_relative] = str(error)
        return
    if done is None:
        _retire_unwritten(
            ctx,
            probe_relative,
            target,
            "the probe points export declares no point, so no probes table is written",
        )
        return
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
    fluid = unsteady and (
        (ctx.pproc.volume_section is not None and ctx.pproc.volume_section.kind != "default")
        or any(entry.kind != "default" for entry in ctx.pproc.probes)
    )
    if fluid and _normal_probes(ctx, record, legacy_profiles):
        probe_relative = f"{PROBES_DIR}/{point.name}_probes_history.csv"
    field_requested = fluid and bool(ctx.record_of.get(point.name) and record.probe_field_layout)
    probe_requested = fluid and (plots or field_requested) and bool(_probe_parameters(ctx.pproc))
    if probe_requested:
        ctx.skipped[probe_relative] = (
            "no probes table: missing plots history export. Restore or collect the "
            "recorded plots export; run again with fluid plots if no history was recorded."
        )
    relative = f"{TIME_HISTORY_DIR}/{point.name}_plots.csv"
    if not ((plots or field_requested) and plots_path is not None and plots_path.is_file()):
        # A changed averaging window needs no solver re-run: with the raw export gone, the
        # history an earlier post wrote is read again, from time_history/ or, in a post
        # folder of the earlier layout, from probes/ with the migration warning. It is
        # not rewritten and not listed as a product of this post.
        if not (plots or field_requested):
            return
        done = earlier_path(ctx.out, relative, kind="plots")
        if not done.is_file():
            return
        ctx.skipped.pop(probe_relative, None)
        ctx.plots_tables[point.name] = done
    else:
        target = ctx.target(ctx.out / relative)
        try:
            written_table = write_plots_table(
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
        if written_table is None:
            _retire_unwritten(
                ctx,
                relative,
                target,
                "the plots export holds no step, so no plots table is written",
            )
            return
        done = written_table
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
    if ctx.pproc.samples_normal_probes():
        probe_relative = f"{PROBES_DIR}/{point.name}_probes_history.csv"
    probe_target = ctx.target(ctx.out / probe_relative)
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


# ------------------------------------------------------------------ step 4: the quasi-steady rotor


def _qsteady_rotor_products(ctx: SimContext) -> None:
    """Write the quasi-steady rotor's clockings and their average."""
    # THE QUASI-STEADY ROTOR'S CLOCKINGS AND THEIR AVERAGE, one pair of
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
        replace=ctx.overwrite,
    ):
        ctx.add(target_path, entry)


def _qsteady_correction_products(ctx: SimContext) -> None:
    """Write the quasi-steady wheel's correction route and its diagnostic (P0310-CAL)."""
    # Each corrected product is a new file beside its raw one, read back from the
    # files written before and never written over them. Off by default. AFTER THE
    # POLAR FILES (i2 #6): the rotor's raw file is its group's RCOEF file, which
    # the polar step writes.
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


def _merged_polar_products(ctx: SimContext) -> None:
    """Write the merged polar, when the pproc asks for it (FR-3511)."""
    from pyflightstream.post._merged_polar import merged_polar_products

    merged_polar_products(ctx)


#: The steps of one simulation's post, in manifest order.
_STEPS: tuple[Callable[[SimContext], None], ...] = (
    export_tables,
    structure_products,
    # FR-3416: where the solver placed the coupled blade, step by step.
    placement_check_products,
    _point_products,
    _qsteady_rotor_products,
    noise_products,
    # FR-1062: read reduced plots first, then project far-field cells into the polars.
    farfield_products,
    _family_polars,
    # P0310-CAL: reads back the rotor's RCOEF file the polar step wrote.
    _qsteady_correction_products,
    # FR-3511: last, so it reads the tables as every step above left them.
    _merged_polar_products,
)


def _normal_probes(ctx: SimContext, record: RunRecord, legacy_profiles: bool) -> bool:
    """Whether an unsteady point sampled its pproc's probes as NORMAL probe points (FR-417).

    A record with ``legacy_profiles`` treats its profiles as a separate instant.
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
        if entry.kind == "default":
            continue
        if drawn_only and entry.points_file:
            continue
        for parameter in getattr(entry, "parameters", None) or []:
            if parameter not in out:
                out.append(parameter)
    section = getattr(pproc, "volume_section", None)
    if section is not None and section.kind != "default":
        out.extend(name for name in ("VX", "VY", "VZ") if name not in out)
    return tuple(out)


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
        return [boundaries_for_matrix(path) for path in found]

    faces = recorded_mesh_faces(record.inputs_sha256, sidecars)
    if faces is None:
        return ""
    if not faces.same_bytes:
        # THE REMEDY BY GEOMETRY KIND: the sidecar of an OBJ is never
        # rewritten, --overwrite or not, so naming --overwrite there names a
        # command that is always refused.
        remedy = (
            "Move the inventory aside, take it again "
            "(pyfs-mesh inventory <geometry>) and "
            "copy its tables beneath the new list (docs/mesh-inputs.md)"
            if Path(str(faces.name)).suffix.lower() == OBJ_SUFFIX
            else "Take the inventory again (pyfs-mesh inventory <geometry> --overwrite)"
        )
        warn(
            f"point={point} product={MESH_FACES_COLUMN}: the inventory {faces.sidecar} states "
            f"mesh_faces = {faces.mesh_faces} counted in mesh_sha256 {faces.counted_sha256}, "
            f"and run "
            f"{record.run_id} recorded sha256 {faces.recorded_sha256} for {faces.name}; the count "
            f"is carried as the inventory states it. {remedy} if the geometry changed (FR-348).",
            PyflightstreamWarning,
            stacklevel=2,
        )
    return str(faces.mesh_faces)


# The old column tuple is refused at its former private re-export too.
__getattr__ = removed_names_hook(__name__)
