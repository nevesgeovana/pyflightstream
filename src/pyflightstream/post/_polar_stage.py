"""The polar step of one simulation's post: its family and group files (PFS-2231).

A private module of :mod:`pyflightstream.post` (AD-13), called by the simulation
stage (:mod:`pyflightstream.post._sim`) over its frozen context. It gathers what
each point contributes, the run block, the loads of every family and the speed of
every rotor, hands it to :func:`pyflightstream.post._family_polar.polar_files`, and
writes the files under ``polars/`` with the derived polars the pproc asks for
beside each group ACOEF file (trimmed, interpolated, custom format).

A steady point's loads are its loads export. An unsteady point's are the window
average of its plots: each family's six components of the plot group
``MRP_<family>``, which a run declares for every family, and each group's own plot
where its families' are not all there (``MRP_TOTAL`` for TOTAL, the rotor's own
history for a rotor). A record written without the family plots gives NA family
rows, said once with the plots it lacks; its group rows come from the group plots
it has.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from pyflightstream._errors import (
    NotApplicableWarning,
    PyflightstreamError,
    PyflightstreamWarning,
    warn,
)
from pyflightstream._identifier_columns import stated_identifiers
from pyflightstream._tokens import FAMILY_PLOT_GROUP, NOT_APPLICABLE
from pyflightstream.cases import AXES_PLOT_COMPONENTS, AXES_PLOT_GROUP
from pyflightstream.post._block_scope import block_of_point
from pyflightstream.post._family_columns import DEFAULT_DRAG_SPLIT, group_id
from pyflightstream.post._family_polar import (
    Family,
    Loads,
    PolarFile,
    PolarGroup,
    PolarPointLoads,
    PolarRotor,
    family_ids,
    group_file_name,
    polar_files,
    polar_groups,
    polar_rotors,
    steady_family_loads,
)
from pyflightstream.post._manifest_schema import FamilyEntry, GroupEntry, note_polar
from pyflightstream.post._point_stage import point_block_rows
from pyflightstream.post._run_block import RUN_TYPES
from pyflightstream.post._stage import (
    _PLOTS_CLOCK_COLUMNS,
    POLARS_DIR,
    _judge_average,
)
from pyflightstream.post._tables import (
    COEFFICIENT_COLUMNS,
    ProductError,
    plots_table_series,
    write_csv_table,
)
from pyflightstream.post.polar import (
    DRAG_PRODUCT_COLUMNS,
    GEOMETRY_ANALYSIS_FRAMES,
    TRIM_SUFFIX,
    declined_induced_drag,
    write_interpolated_polar,
    write_trimmed_polar,
)
from pyflightstream.post.rotor_table import warn_rotor_declared_aft
from pyflightstream.post.unsteady import blade_passage_average
from pyflightstream.results import drag_pair

if TYPE_CHECKING:
    from pyflightstream.post._sim import SimContext
    from pyflightstream.post.polar import PolarPoint

__all__ = ["family_polar_products"]


def _recorded_rpm(record: object, alias: str, rotor_count: int) -> float | None:
    from pyflightstream.post._condition import row_rotor_speeds
    from pyflightstream.post._rotor_plan import _recorded_rotor_rpm

    if record is None:
        return None
    rpm = _recorded_rotor_rpm(record, alias, rotor_count)  # type: ignore[arg-type]
    if rpm is None:
        own = row_rotor_speeds(record, None)
        rpm = next((v for k, v in own.items() if str(k).casefold() == alias.casefold()), None)
    return rpm


def _rotor_speeds(
    ctx: SimContext, point: PolarPoint, rotors: Sequence[PolarRotor]
) -> dict[int, float | None]:
    from pyflightstream.post._condition import row_rotor_speeds

    record = ctx.record_of.get(point.name)
    own = row_rotor_speeds(record, point.loads_path)
    speeds: dict[int, float | None] = {}
    for rotor in rotors:
        rpm = _recorded_rpm(record, rotor.alias, len(rotors))
        if rpm is None:
            rpm = next(
                (v for k, v in own.items() if str(k).casefold() == rotor.alias.casefold()), None
            )
        speeds[rotor.rotor_id] = rpm
    return speeds


def _number(value: object) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value):
        return float(value)
    return None


def _drag_split(point: PolarPoint, declined: Sequence[str]) -> dict[str, dict[str, float]]:
    induced_key, profile_key = drag_pair(point.loads.total)
    names = DRAG_PRODUCT_COLUMNS[(induced_key, profile_key)]
    return {
        str(family): {
            names[0]: float(row[profile_key]),
            names[1]: math.nan if family in declined else float(row[induced_key]),
        }
        for family, row in point.loads.surfaces.items()
        if profile_key in row and induced_key in row
    }


def _averaged_plots(
    ctx: SimContext, point: PolarPoint, span: tuple[int, int], left_out: list[str], product: str
) -> dict[str, float] | None:
    source = ctx.plots_tables.get(point.name)
    if source is None or not source.is_file():
        left_out.append(f"{point.name}: no plots table")
        return None
    try:
        names, series = plots_table_series(source)
        steps = np.asarray(series.steps, dtype=int)
        if not np.array_equal(
            steps[(steps >= span[0]) & (steps <= span[1])], np.arange(span[0], span[1] + 1)
        ):
            held = f"steps {int(steps[0])} to {int(steps[-1])}" if len(steps) else "no step"
            left_out.append(
                f"{point.name}: the row states steps {span[0]} to {span[1]} and the history "
                f"holds {held}, with a missing sample or gap in that window"
            )
            return None
        read_steps: set[int] = set()
        averaged = blade_passage_average(series, window=span, read_steps=read_steps)
    except (PyflightstreamError, ValueError) as error:
        left_out.append(f"{point.name}: its plots table could not be read: {error}")
        return None
    refusal = _judge_average(
        ctx.frozen_points.get(point.name), read_steps, point=point.name, product=product
    )
    if refusal is not None:
        left_out.append(f"{point.name}: {refusal}")
        return None
    values: dict[str, float] = {}
    for name in names:
        if name in _PLOTS_CLOCK_COLUMNS:
            continue
        column = averaged.fields.get(name)
        if column is not None and len(column):
            values[name] = float(column[0])
    return values


def _plotted(values: Mapping[str, float], group: str) -> Loads | None:
    six = [values.get(f"{part}_{group}") for part in AXES_PLOT_COMPONENTS]
    if any(value is None for value in six):
        return None
    numbers = [float(value) for value in six]  # type: ignore[arg-type]
    return (numbers[0], numbers[1], numbers[2]), (numbers[3], numbers[4], numbers[5])


def _unsteady_loads(
    ctx: SimContext,
    values: Mapping[str, float],
    families: Sequence[Family],
    rotors: Sequence[PolarRotor],
    lacking: set[str],
) -> tuple[dict[str, Loads | None], dict[str, Loads]]:
    from pyflightstream.post._rotor_plan import rotor_plot_source

    family_loads: dict[str, Loads | None] = {}
    for family in families:
        group = FAMILY_PLOT_GROUP.format(family=family.name)
        family_loads[family.name] = _plotted(values, group)
        if family_loads[family.name] is None:
            lacking.add(group)
    groups: dict[str, Loads] = {}
    total = _plotted(values, AXES_PLOT_GROUP)
    if total is not None and any(loads is None for loads in family_loads.values()):
        groups["TOTAL"] = total
    inventory = [family.name for family in families]
    for rotor in rotors:
        if all(family_loads.get(member) is not None for member in rotor.members):
            continue
        candidates, _refused = rotor_plot_source(
            ctx.pproc,
            rotor.alias,
            rotor_families=list(rotor.members),
            inventory=inventory,
            aliases=ctx.aliases,
        )
        for name in candidates:
            own = _plotted(values, name)
            if own is not None:
                groups[rotor.alias] = own
                break
    return family_loads, groups


@dataclass
class _Gathered:
    """What the points of one polar contribute, and what was left out or lacking."""

    rows: list[PolarPointLoads] = field(default_factory=list)
    held: list[PolarPoint] = field(default_factory=list)
    plotted: list[dict[str, float]] = field(default_factory=list)
    splits: list[tuple[str, str]] = field(default_factory=list)
    left_out: list[str] = field(default_factory=list)
    lacking: set[str] = field(default_factory=set)
    refused: list[tuple[str, str]] = field(default_factory=list)


def _layout(
    ctx: SimContext,
) -> tuple[list[Family], list[PolarRotor], list[PolarGroup]] | None:
    """Return the families, rotors and groups of the polar, naming each group refused."""
    surfaces = list(
        dict.fromkeys(
            name for point in ctx.points if point.loads is not None for name in point.loads.surfaces
        )
    )
    if not surfaces:
        return None
    inventory = next(
        (found for record in ctx.records if (found := ctx.workspace.recorded_inventory(record))),
        None,
    )
    ids = family_ids(surfaces, inventory)
    rotors = polar_rotors(getattr(ctx.live, "rotors", None) or {}, surfaces, ctx.aliases)
    owner = {member: rotor.rotor_id for rotor in rotors for member in reversed(rotor.members)}
    families = [Family(name, ids[name], owner.get(name)) for name in surfaces]
    refused: dict[str, str] = {}
    groups = polar_groups(families, rotors, ctx.pproc.groups, aliases=ctx.aliases, refused=refused)
    for name, reason in refused.items():
        ctx.skipped[f"{POLARS_DIR}/P{ctx.sim_id}-{name}"] = reason
        warn(reason, PyflightstreamWarning, stacklevel=3)
    for group in groups:
        if not group.members:
            ctx.skipped[f"{POLARS_DIR}/P{ctx.sim_id}-{group.name}"] = (
                f"group {group.name!r} selects no family of the loads exports of simulation "
                f"{ctx.sim_id!r} ({', '.join(surfaces)}): {_selector(ctx, group)} names no "
                "surface or alias there; its files are not written."
            )
    for rotor in rotors:
        warn_rotor_declared_aft(rotor.alias, rotor.frame)
    return families, rotors, [group for group in groups if group.members]


def _selector(ctx: SimContext, group: PolarGroup) -> str:
    """Name what selects a group's families: its ``[groups]`` alias, its rotor's families."""
    if group.origin == "rotor":
        block = (getattr(ctx.live, "rotors", None) or {}).get(group.name)
        families = [str(name) for name in getattr(block, "members", None) or ()]
        return f"rotor {group.name}'s families ({', '.join(families) or 'none declared'})"
    if group.origin == "declared":
        for position, (name, members) in enumerate(ctx.pproc.groups.items(), start=1):
            if group_id("declared", position=position) == group.group_id:
                return f"its selector {name} = {', '.join(str(m) for m in members) or 'all'}"
    return "every family"


def _say_omitted(
    ctx: SimContext,
    gathered: _Gathered,
    groups: Sequence[PolarGroup],
    omitted: Sequence[tuple[str, int]],
) -> None:
    """Name each group row a point does not have because the group selects nothing there."""
    by_name = {group.name: group for group in groups}
    for name, index in omitted:
        point = gathered.held[index]
        stated = ", ".join(str(s) for s in point.loads.surfaces) if point.loads else "none"
        key = f"{POLARS_DIR}/{group_file_name(ctx.sim_id, name, 'ACOEF')}#{point.name}"
        ctx.skipped[key] = (
            f"point {point.name}: group {name!r} selects no surface of its loads export "
            f"({stated}): {_selector(ctx, by_name[name])} names no surface or alias of that "
            "point, so the point is no row of the group's files (never a row of NA)."
        )
        warn(ctx.skipped[key], PyflightstreamWarning, stacklevel=3)


def _said_instant(ctx: SimContext) -> bool:
    """Say, and return, that an unsteady simulation with no window reads its last step."""
    instant = ctx.window is None and any(
        str(getattr(ctx.record_of.get(point.name), "recipe", "") or "").startswith("unsteady")
        or str(point.loads.solver_mode).strip().casefold() == "unsteady"
        for point in ctx.points
    )
    if instant:
        warn(
            f"point={POLARS_DIR}/{ctx.sim_id} product={POLARS_DIR}/{ctx.sim_id}: simulation "
            f"{ctx.sim_id}'s polar files are read from the loads export of an unsteady run, its "
            "LAST TIME STEP, one instant of a cycle, because no averaging window resolves for "
            "it; the manifest marks them kind: instant.",
            PyflightstreamWarning,
            stacklevel=3,
        )
    return instant


def _point_loads(
    ctx: SimContext,
    point: PolarPoint,
    condition: Mapping[str, object],
    layout: tuple[list[Family], list[PolarRotor]],
    gathered: _Gathered,
) -> (
    tuple[
        dict[str, Loads | None],
        dict[str, Loads],
        dict[str, dict[str, float]],
        tuple[str, ...],
        dict[str, float],
    ]
    | None
):
    """Return one point's family loads, group loads, drag split, declined and plot values."""
    families, rotors = layout
    if ctx.window is not None:
        span = ctx.point_windows.get(point.name, ctx.window)
        values = _averaged_plots(
            ctx, point, span, gathered.left_out, f"{POLARS_DIR}/FAM-P{ctx.sim_id}"
        )
        if values is None:
            return None
        family_loads, own = _unsteady_loads(ctx, values, families, rotors, gathered.lacking)
        return family_loads, own, {}, (), values
    vref = _number(condition.get("VREF"))
    surfaces = _wheel_mean(ctx, point, vref, gathered.left_out)
    if surfaces is None:
        return None
    declined = declined_induced_drag(point.loads, point.vorticity_selection)
    family_loads = steady_family_loads(
        surfaces,
        density_kg_m3=_number(condition.get("RHO")),
        vref_m_s=vref,
        sref_m2=ctx.reference.sref_m2,
        cref_m=ctx.reference.cref_m,
    )
    stated_frame = str(point.loads.frame or "").strip().casefold()
    if stated_frame and stated_frame not in GEOMETRY_ANALYSIS_FRAMES:
        # A FRAME OF UNKNOWN ROTATION IS NO ROW, never a row of NA: the reason of the
        # 0.57.0 polar (post.polar.polar_rows), named per group file of the point.
        gathered.refused.append(
            (
                point.name,
                f"{point.loads_path} states analysis frame {point.loads.frame!r}; polar axes "
                "require vectors in the geometry's axes, and this frame's rotation is unknown",
            )
        )
        return None
    names = DRAG_PRODUCT_COLUMNS[drag_pair(point.loads.total)]
    if names not in gathered.splits:
        gathered.splits.append(names)
    return family_loads, {}, _drag_split(point, declined), declined, {}


def _gather(ctx: SimContext, layout: tuple[list[Family], list[PolarRotor]]) -> _Gathered:
    """Return what every point of the polar contributes, in sweep order."""
    gathered = _Gathered()
    rotors = layout[1]
    built: dict[str, dict[str, object]] | None = None
    for point, condition in zip(ctx.points, ctx.conditions, strict=True):
        found = _point_loads(ctx, point, condition, layout, gathered)
        if found is None:
            continue
        family_loads, own, split, declined, values = found
        speeds = _rotor_speeds(ctx, point, rotors)
        # ONE RUN BLOCK FOR EVERY TABLE OF THE POINT (FR-3778): the row the stage's
        # scope laid out over the whole sweep, so POINT_ID is the point's place in
        # it even where this step reads a filtered list of points.
        block = block_of_point(point.name)
        if block is None:
            built = point_block_rows(ctx) if built is None else built
            block = built[point.name]
        gathered.rows.append(
            PolarPointLoads(
                run_block=block,
                alpha_deg=point.alpha_deg,
                beta_deg=point.beta_deg,
                density_kg_m3=_number(condition.get("RHO")),
                vref_m_s=_number(condition.get("VREF")),
                vinf_m_s=_number(condition.get("VINF")),
                family_loads=family_loads,
                group_loads=own,
                drag_split=split,
                declined=declined,
                rpm=speeds,
                mesh_faces=_faces(ctx, point),
            )
        )  # fmt: skip
        gathered.held.append(point)
        gathered.plotted.append(values)
    return gathered


def _entry(ctx: SimContext, held: Sequence[PolarPoint], *, instant: bool) -> dict[str, object]:
    """Return the manifest entry every file of the polar carries."""
    entry: dict[str, object] = {"runs": [rid for point in held for rid in ctx.sources[point.name]]}
    if ctx.window is not None:
        names = {point.name for point in held}
        entry.update(
            {
                "source": "the unsteady plots, time-averaged",
                "window": list(ctx.window),
                "windows": {
                    name: list(span)
                    for name, span in sorted(ctx.point_windows.items())
                    if name in names
                },
            }
        )
    elif instant:
        entry["kind"] = "instant"
    return entry


def _say_keys_not_applied(ctx: SimContext) -> None:
    """Name and warn the [products] keys the polar files do not apply (yet)."""
    if ctx.pproc.products.rotor_cn_slope:
        # SAID, NEVER SILENT: the slope read the rotor table, which is retired.
        reason = (
            "the rotor normal-force slope is not written: it read the rotor table, which the "
            "rotor groups' RCOEF files replace, and its reading of those files is not yet "
            "defined"
        )
        ctx.skipped[f"{POLARS_DIR}/{ctx.sim_id}#rotor_cn_slope"] = reason
        warn(reason, PyflightstreamWarning, stacklevel=2)
    if ctx.pproc.products.polar_axes is not None:
        # WARN AND SKIP: the key appended selected-axis columns to the 0.57.0 polar
        # table; the ACOEF files state every frame (W, S, B), and the key's reading
        # of them is not yet defined.
        said = (
            f"[products] polar_axes = {ctx.pproc.products.polar_axes!r} is not applied: the "
            "ACOEF files state the coefficients in every frame (W, S, B), and the key's reading "
            "of those files is not yet defined"
        )
        ctx.skipped[f"{POLARS_DIR}/{ctx.sim_id}#polar_axes"] = said
        warn(said, PyflightstreamWarning, stacklevel=2)


def family_polar_products(ctx: SimContext) -> None:
    """Write the family and group files of one simulation's polar, and their derived polars."""
    if not ctx.pproc.products.polars:
        return
    _say_keys_not_applied(ctx)
    layout = _layout(ctx)
    if layout is None:
        return
    families, rotors, groups = layout
    instant = _said_instant(ctx)
    gathered = _gather(ctx, (families, rotors))
    if gathered.left_out:
        ctx.skipped[f"{POLARS_DIR}/P{ctx.sim_id}"] = (
            "these points of the sweep are not rows of the polar files: "
            + "; ".join(gathered.left_out)
        )
    for name, reason in gathered.refused:
        for group in groups:
            key = f"{POLARS_DIR}/{group_file_name(ctx.sim_id, group.name, 'ACOEF')}#{name}"
            ctx.skipped[key] = f"point {name} is no row of the polar files: {reason}"
        warn(
            f"{POLARS_DIR}/P{ctx.sim_id}: point {name} is no row of the polar files: {reason}",
            PyflightstreamWarning,
            stacklevel=2,
        )
    if not gathered.rows:
        return
    if gathered.lacking:
        warn(
            f"{POLARS_DIR}/{ctx.sim_id}: the plots hold no FX to MZ of plot group(s) "
            f"{', '.join(sorted(gathered.lacking))}, so those families' rows of the FAM files "
            "are NA; the group rows come from the group plots the run has. A run declares one "
            f"{FAMILY_PLOT_GROUP} plot group per family (docs/pproc/fam-dim.md).",
            PyflightstreamWarning,
            stacklevel=2,
        )
    unsteady = ctx.window is not None
    omitted: list[tuple[str, int]] = []
    files = polar_files(
        pol=ctx.sim_id,
        points=gathered.rows,
        families=families,
        groups=groups,
        rotors=rotors,
        reference=ctx.reference,
        load_frame="MRP" if unsteady else _load_frame(ctx),
        identifiers=tuple(getattr(ctx.matrix_row, "identifiers", {}) or {}),
        drag_split=[name for pair in (gathered.splits or [DEFAULT_DRAG_SPLIT]) for name in pair],
        omitted=omitted,
    )
    _say_omitted(ctx, gathered, groups, omitted)
    _note_the_polar(
        ctx,
        (families, rotors, groups),
        files,
        load_frame="MRP" if unsteady else _load_frame(ctx),
        drag_split=[name for pair in (gathered.splits or [DEFAULT_DRAG_SPLIT]) for name in pair],
    )
    entry = _entry(ctx, gathered.held, instant=instant)
    if unsteady:
        _equations(ctx, files, gathered.plotted)
    # THE RUN BLOCK STATES THE IDENTIFIERS, after POINT, so the post's stamping of
    # them after POL (FR-3564) is not applied to these files or their derived polars.
    with stated_identifiers({}):
        for polar in files:
            target = _write(ctx, polar)
            own = entry
            if polar.group is not None:
                # A FILE NAMES THE RUNS OF ITS OWN ROWS: a point the group selects
                # nothing at is no row of it, so it is no run of it either.
                gone = {index for name, index in omitted if name == polar.group}
                runs = [
                    rid
                    for index, point in enumerate(gathered.held)
                    if index not in gone
                    for rid in ctx.sources[point.name]
                ]
                own = {**entry, "runs": runs, "group": polar.group}
            ctx.add(target, own)
            if polar.group is not None and polar.kind == "ACOEF":
                _derived_polars(ctx, target, polar, own, groups)


_NO_RCOEF_NOTE = "its members are not all inside one rotor, so it has DIM and ACOEF files only"


def _note_the_polar(
    ctx: SimContext,
    layout: tuple[Sequence[Family], Sequence[PolarRotor], Sequence[PolarGroup]],
    files: Sequence[PolarFile],
    *,
    load_frame: str,
    drag_split: Sequence[str],
) -> None:
    """State the polar's families, groups and rotor frames for ``products.json`` (FR-3779)."""
    families, rotors, groups = layout
    ids = {family.name: family.family_id for family in families}
    with_rcoef = {polar.group for polar in files if polar.kind == "RCOEF" and polar.group}
    record = ctx.record_of.get(ctx.points[0].name) if ctx.points else None
    recipe = str(getattr(record, "recipe", "") or "")
    note_polar(
        str(ctx.sim_id),
        run_type=recipe if recipe in RUN_TYPES else "steady",
        description=getattr(record, "description", None),
        families=[
            FamilyEntry(family.family_id, family.name, family.rotor_id) for family in families
        ],
        groups=[
            GroupEntry(
                group.group_id,
                group.name,
                group.origin,
                tuple(sorted(ids[name] for name in group.members if name in ids)),
                _NO_RCOEF_NOTE
                if rotors and group.origin == "declared" and group.name not in with_rcoef
                else None,
            )
            for group in groups
        ],
        rotors=[
            {
                "id": rotor.rotor_id,
                "alias": rotor.alias,
                "pitch_deg": rotor.frame.pitch_deg,
                "toe_deg": rotor.frame.toe_deg,
            }
            for rotor in rotors
        ],
        load_frame=load_frame,
        drag_split=drag_split,
        identifiers=tuple(getattr(ctx.matrix_row, "identifiers", {}) or {}),
    )


def _load_frame(ctx: SimContext) -> str:
    """Return the frame the loads exports state their loads in, as the first one names it."""
    return next(
        (str(p.loads.frame) for p in ctx.points if p.loads is not None and p.loads.frame), "MRP"
    )


def _wheel_mean(
    ctx: SimContext, point: PolarPoint, vref: float | None, left_out: list[str]
) -> Mapping[str, Mapping[str, float]] | None:
    """Return a point's surfaces: a quasi-steady WHEEL's mean over its clockings.

    A wheel point's loads are the mean of its k clockings (P0310-ROTOR-MEAN),
    never clocking 0 alone; a clocking that cannot be read costs the point its
    rows, named, because a mean of the others is not its mean. Every other
    point's are its loads export.
    """
    from pyflightstream.cases.qsteady import QsteadyRecordError, read_qsteady_record
    from pyflightstream.cases.workflows import QSTEADY_ROTOR
    from pyflightstream.post import qsteady as _qsteady

    record = ctx.record_of.get(point.name)
    if getattr(record, "recipe", None) != QSTEADY_ROTOR or vref is None:
        return point.loads.surfaces
    try:
        quasi = read_qsteady_record(point.loads_path)
    except QsteadyRecordError:
        return point.loads.surfaces
    if quasi.case != "wheel":
        return point.loads.surfaces
    try:
        return _qsteady.mean_clocking_surfaces(
            quasi, point.loads_path.parent, speed_m_s=vref
        ).surfaces
    except PyflightstreamError as refused:
        left_out.append(
            f"{point.name}: {refused}; the row of a wheel is the mean of all its clockings, "
            "never of the others"
        )
        return None


def _faces(ctx: SimContext, point: PolarPoint) -> object:
    from pyflightstream.post._sim import _mesh_faces_of

    record = ctx.record_of.get(point.name)
    return _mesh_faces_of(ctx.workspace, record, point.name) or NOT_APPLICABLE


def _write(ctx: SimContext, polar: PolarFile) -> Path:
    target = ctx.target(ctx.out / POLARS_DIR / polar.name)
    if ctx.pproc.products.polar_format == "legacy_polar":
        from pyflightstream.post._tables import write_fixed_width_table

        return write_fixed_width_table(target, polar.columns, polar.rows)
    return write_csv_table(target, polar.columns, polar.rows)


def _equations(
    ctx: SimContext, files: list[PolarFile], plotted: Sequence[Mapping[str, float]]
) -> None:
    """Evaluate the pproc's ``[equations]`` into trailing columns of the TOTAL ACOEF file."""
    from pyflightstream.post.equations import apply_equations

    equations = getattr(ctx.pproc, "equations", None)
    total = next((f for f in files if f.group == "TOTAL" and f.kind == "ACOEF"), None)
    if not equations or total is None or len(total.rows) != len(plotted):
        return
    rows = []
    for cells, values in zip(total.rows, plotted, strict=True):
        row: dict[str, object] = dict(values)
        row.update(dict(zip(total.columns, cells, strict=True)))
        rows.append(row)
    columns = list(dict.fromkeys(name for row in rows for name in row))
    notes: list[str] = []
    resolved: dict[str, dict[str, str]] = {}
    where = f"{POLARS_DIR}/{total.name}"
    try:
        added, derived = apply_equations(
            rows, equations, list(ctx.pproc.equation_order()), columns=columns, where=where,
            notes=notes, resolved_columns=resolved,
        )  # fmt: skip
    except ProductError as refused:
        notes.append(str(refused))
        added, derived = [], []
    if notes:
        ctx.skipped[f"{where}#equations"] = "; ".join(notes)
        warn(f"{where}: " + "; ".join(notes), PyflightstreamWarning, stacklevel=2)
    if not added:
        return
    # TRAILING VALUES, BEFORE MESH_FACES, which stays last for positional readers.
    at = len(total.columns) - 1
    rebuilt = replace(
        total,
        columns=(*total.columns[:at], *added, *total.columns[at:]),
        rows=[
            (*cells[:at], *(value.get(name) for name in added), *cells[at:])
            for cells, value in zip(total.rows, derived, strict=True)
        ],
    )
    files[files.index(total)] = rebuilt
    ctx.written_names[f"{where}#equations"] = {"resolved_columns": resolved}


def _derived_polars(
    ctx: SimContext,
    target: Path,
    polar: PolarFile,
    entry: Mapping[str, object],
    groups: Sequence[object],
) -> None:
    """Write the trimmed, interpolated and custom-format polars of one group ACOEF file."""
    products = ctx.pproc.products
    if products.trimmed_polar:
        trim = ctx.target(target.with_name(f"{target.stem}{TRIM_SUFFIX}.csv"))
        relative = trim.relative_to(ctx.out).as_posix()
        moment, axis = products.trim_moment, products.trim_axis
        try:
            write_trimmed_polar(target, trim, moment=moment, angle=axis, overwrite=True)
        except ProductError as error:
            ctx.skipped[relative] = f"the trimmed polar is not written: {error}"
            warn(ctx.skipped[relative], NotApplicableWarning, stacklevel=2)
        else:
            ctx.add(
                trim, {**entry, "group": polar.group, "trimmed": {"moment": moment, "angle": axis}}
            )
    for sample in ctx.pproc.polar_at:
        interpolated = ctx.target(target.with_name(f"{target.stem}_at_{sample.output_name}.csv"))
        try:
            write_interpolated_polar(target, interpolated, axis=sample.axis, values=sample.values)
        except ProductError as error:
            ctx.skipped[interpolated.relative_to(ctx.out).as_posix()] = str(error)
            warn(str(error), NotApplicableWarning, stacklevel=2)
        else:
            ctx.add(
                interpolated,
                {
                    **entry,
                    "group": polar.group,
                    "kind": "interpolated",
                    "axis": sample.axis,
                    "values": sample.values,
                },
            )
    if products.custom_polar_format:
        _custom_polar(ctx, target, polar, entry, groups)


#: The custom format's twenty-four coefficient columns, by the ACOEF column each is
#: read from (the migration map: ``CR<f>25 -> Cl<f>``, ``CM<f>25 -> Cm<f>``,
#: ``CN<f>25 -> Cn<f>``; the values are the same).
_CUSTOM_FROM_ACOEF: dict[str, str] = {
    f"{old}{frame}{suffix}": f"{new}{frame}"
    for frame in "BSW"
    for old, new, suffix in (
        ("CD", "CD", ""),
        ("CY", "CY", ""),
        ("CL", "CL", ""),
        ("CR", "Cl", "25"),
        ("CM", "Cm", "25"),
        ("CN", "Cn", "25"),
    )
}


def _custom_polar(
    ctx: SimContext,
    target: Path,
    polar: PolarFile,
    entry: Mapping[str, object],
    groups: Sequence[object],
) -> None:
    from pyflightstream.cases.workflows import CONFIGURATION_VARIABLE
    from pyflightstream.post.custom_polar import write_custom_polar_format

    header = list(polar.columns)
    split = [name for pair in DRAG_PRODUCT_COLUMNS.values() for name in pair if name in header]
    columns = (*COEFFICIENT_COLUMNS[:-2], *split)
    rows = []
    for cells in polar.rows:
        row = dict(zip(header, cells, strict=True))
        values = []
        for name in columns:
            source = _CUSTOM_FROM_ACOEF.get(name, name)
            value = row.get(source)
            number = _number(value) if not isinstance(value, str) else _text_number(value)
            values.append(math.nan if number is None else number)
        rows.append(tuple(values))
    # LINE FOUR STATES THE GROUP BY ITS GROUP_ID (post._family_columns.group_id), so
    # AIRFRAME (1) and the first declared group (101) never read one number.
    group = next((g for g in groups if getattr(g, "name", None) == polar.group), None)
    group_id = getattr(group, "group_id", None)
    custom = ctx.target(target.with_suffix(".dat"))
    write_custom_polar_format(
        custom,
        polar=ctx.sim_id,
        description=ctx.first.description or "",
        group=str(polar.group),
        group_number=group_id,
        mach=ctx.mach,
        reference=ctx.reference,
        rows=rows,
        columns=columns,
        configuration=(
            ctx.matrix_row.variables.get(CONFIGURATION_VARIABLE)
            if ctx.matrix_row is not None
            else None
        ),
    )
    ctx.add(custom, {**entry, "group": polar.group})


def _text_number(text: str) -> float | None:
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None
