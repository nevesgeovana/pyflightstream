"""Plan a grouped matrix: which polars share one FlightStream instance, and for how long.

Covers FR-362 to FR-365, FR-378, FR-379 and FR-405.

Private to :mod:`pyflightstream.run`. ``plan --batch N`` and ``plan --polar-sweep`` first plan
the matrix as any plan does (with the cost table), then group the unsteady polars: leave out and
NAME what a grouped job cannot hold, refuse a geometry that carries saved solver actions,
split the polars into jobs, estimate each job and price its wall clock, and write the whole
decision into ``plan.json`` as the ``grouping`` block that ``run`` requires.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePath
from typing import Any, Literal, cast

import pyflightstream._textio as _textio
from pyflightstream._console import table
from pyflightstream.cases import ScriptRecipe, SimCase, case_at_point, resolve_recipe
from pyflightstream.cases._unsteady_actions import documents_actions
from pyflightstream.cases.workflows import (
    WORKFLOW_KEY,
    parse_restart,
    row_ncpus,
    walltime_margin_s,
)
from pyflightstream.cases.workflows._batch_actions import is_absolute_target
from pyflightstream.cases.workflows._batch_script import (
    JobPoint,
    job_point,
    refuse_unspliceable,
    user_actions_of,
)
from pyflightstream.cases.workflows._rows import (
    row_walltime_is_best,
    row_walltime_s,
    row_walltime_text,
)
from pyflightstream.run._batch_split import (
    BEST_FACTOR,
    MEASURED_OVERHEADS,
    JobSplit,
    PolarUnit,
    job_estimate,
    job_walltime,
    split_polars,
    walltime_text,
)
from pyflightstream.run._grouped import grouped_case
from pyflightstream.run._ids import _point_names, narrow_to_selection
from pyflightstream.run._plan import (
    CampaignPlan,
    PlannedPointCost,
    PlanStatus,
    PointPlan,
    _plan_point,
)
from pyflightstream.run.matrix import plan_matrix
from pyflightstream.script import Script
from pyflightstream.workspace import SIM_DATAPOINTS_DIR, CampaignWorkspace
from pyflightstream.workspace._batches import (
    GROUPING_SCHEMA,
    GroupedJob,
    GroupingReceipt,
    batch_label,
    batch_script_name,
    next_batch_id,
)
from pyflightstream.workspace._geometry_clean import UNSTEADY_WORKFLOWS, saved_action_warning
from pyflightstream.workspace.hpc import HpcProfile, resolve_hpc_profile
from pyflightstream.workspace.matrix import ResolvedMatrix, resolve_matrix

__all__ = ["eligibility", "grouping_table_lines", "plan_grouped_matrix"]

#: The polar-sweep job's script stem: one job per polar, ``sims/sim_<id>/FULL-POLAR.txt``.
_FULL_POLAR = "FULL-POLAR"


def eligibility(case: SimCase, *, workspace: CampaignWorkspace, version: str) -> str | None:
    """Return the reason a polar cannot join a grouped job, or None when it can (reading 7).

    A polar is left out and NAMED, never refused: a steady or quasi-steady row (a steady point
    after an unsteady one is not measured), a RESTART row (it opens a datapoint's ``.fsm``), a
    row whose setup states a SCRIPT ``unsteady_solver_actions`` entry by a relative file,
    and a build that does not document the unsteady action command.

    A row whose setup states ``unsteady_solver_actions`` otherwise joins a grouped job (FR-405,
    0.35.1): the split puts it only with polars stating the same actions, and the job registers
    them once, before the package's actions, as the point run alone does. A user action cannot
    be withdrawn between polars. A relative SCRIPT
    file is the exception, because a point run alone reads it in its own datapoint folder (the
    solver's working directory) and one registration in one instance, whose working directory
    is the job's folder for the whole job (RPT-141), can name only one file.

    Parameters
    ----------
    case : SimCase
        The row's case.
    workspace : CampaignWorkspace
        The campaign workspace (reserved for checks that read the staged inputs).
    version : str
        The FlightStream version the row's scripts are built under.

    Returns
    -------
    str or None
        The reason, as a sentence fragment, or None when the polar is eligible.
    """
    del workspace
    workflow = str(case.variables.get(WORKFLOW_KEY, "")).strip()
    actions = user_actions_of(case)
    if workflow not in UNSTEADY_WORKFLOWS:
        return f"a {workflow or 'LEGACY'} row: grouped modes run unsteady rows only"
    reasons = (
        (parse_restart(case) is not None, "a RESTART row opens a datapoint's saved simulation"),
        (
            any(kind == "SCRIPT" and not is_absolute_target(name) for kind, _, name in actions),
            "its setup states a SCRIPT unsteady_solver_actions entry by a relative file, which "
            "a point run alone reads in its own datapoint folder; state the file absolute",
        ),
    )
    for found, reason in reasons:
        if found:
            return reason
    if not documents_actions(Script(version=version)):
        return f"build {version} does not document the unsteady solver action command"
    return None


def _pristine_refusal(case: SimCase) -> str | None:
    """Return the block a geometry carrying saved solver actions earns (decision 3, FR-378).

    Re-examined for 0.35.1 and KEPT, on three measurements. ``OPEN`` loads a file's saved
    actions (RPT-141, arm G). A saved action runs beside the script's action of the same name,
    both firing each step (RPT-135: twice the runtime commands, a step counter of 24 for 12
    steps). An action survives ``NEW_SIMULATION`` and no command withdraws one (RPT-141, Test
    2). The job's counter re-indexes ONE invocation per step into (point, step) (FR-355), so a
    saved counter beside it misplaces every point's steps, exports and clock, and a saved action
    of another name would run on every later polar of the job. ``pyfs-matrix inventory <file>
    --clean`` (FR-308) removes the saved actions, and the cleaned polar groups.
    """
    geometry = case.geometry
    if not geometry or Path(str(geometry)).suffix.lower() != ".fsm":
        return None
    return saved_action_warning(Path(str(geometry)), str(geometry), [case.sim_id])


def _clock(seconds: float | None) -> str:
    """Return a duration as ``3h05m``, or ``unknown``."""
    if seconds is None:
        return "unknown"
    minutes = int(round(seconds / 60.0))
    return f"{minutes // 60}h{minutes % 60:02d}m"


def _sims_text(sims: Sequence[str]) -> str:
    """Return the sims of a job as ``2006-2007``, or the one sim."""
    return sims[0] if len(sims) == 1 else f"{sims[0]}-{sims[-1]}"


def grouping_table_lines(receipt: GroupingReceipt) -> list[str]:
    """Return the table of a grouped plan: a row per job, a total line, warnings, left-out polars.

    Parameters
    ----------
    receipt : GroupingReceipt
        The grouping the plan decided.

    Returns
    -------
    list of str
        The lines to print: ``batch id sims cpus points estimate walltime source`` per job, the
        sum and the longest of the estimates, each warning, then each polar left out with its
        reason.
    """
    rows = [["batch", "id", "sims", "cpus", "points", "estimate", "walltime", "source"]]
    for job in receipt.jobs:
        rows.append(
            [
                job.label if job.batch_id is not None else job.name,
                "-" if job.batch_id is None else str(job.batch_id),
                _sims_text(job.sims),
                str(job.ncpus),
                str(len(job.points)),
                _clock(job.estimate_s),
                job.walltime_written or "none",
                job.walltime_source,
            ]
        )
    lines = list(table(rows))
    lines.append(
        f"  total {_clock(receipt.total_estimate_s)} (sum of the jobs), "
        f"longest job {_clock(receipt.longest_estimate_s)}"
    )
    lines.extend(f"  warning: {text}" for text in receipt.warnings)
    if receipt.left_out:
        lines.append("  left out of the grouping:")
        lines.extend(f"    POL {item['sim']}: {item['reason']}" for item in receipt.left_out)
    return lines


def _version_of(plan: CampaignPlan, resolved: ResolvedMatrix, case: SimCase) -> str:
    """Return the version a row's scripts are built under: its build's, else the campaign's."""
    for sim, build in zip(resolved.campaign.sims, resolved.row_builds, strict=True):
        registered = resolved.builds.get(build) if build else None
        if sim.sim_id == case.sim_id and registered is not None and registered.fs_version:
            return registered.fs_version
    return plan.fs_version


def _unit_of(
    case: SimCase,
    points: Sequence[PointPlan],
    costs: Mapping[str, PlannedPointCost],
    fs_build: str,
    order: int,
) -> PolarUnit:
    """Build the :class:`PolarUnit` of one eligible polar."""
    best = row_walltime_is_best(case)
    cell = None if best else row_walltime_s(case)
    seconds = tuple(
        costs[entry.run_id].seconds if entry.run_id in costs else None for entry in points
    )
    return PolarUnit(
        sim_id=case.sim_id,
        order=order,
        ncpus=int(row_ncpus(case, case.solver.max_threads) or 0),
        fs_build=fs_build,
        run_ids=tuple(entry.run_id for entry in points),
        point_seconds=seconds,
        walltime_cell_s=cell,
        walltime_cell_text=None if best else row_walltime_text(case),
        best=best,
        margin_s=walltime_margin_s(case),
        actions=user_actions_of(case),
    )


def _user_action_warnings(split: JobSplit) -> list[str]:
    """Return the warning a job running the setup's own actions earns (FR-405).

    The job registers them once, before the package's actions, as a point run alone does;
    what differs is the working directory: a point run alone runs them from its datapoint
    folder, a job from its own folder for every point (RPT-141), so a relative path inside a
    COMMAND_LINE action resolves there.
    """
    actions = split.units[0].actions
    if not actions:
        return []
    sims = ", ".join(unit.sim_id for unit in split.units)
    names = ", ".join(name for _, name, _ in actions)
    return [
        f"POL {sims}: the setup's unsteady_solver_actions ({names}) are registered once for "
        "the job and run on every point of it, from the job's folder and not from each point's "
        "datapoint folder, so a relative path inside a COMMAND_LINE action resolves there."
    ]


def _job_of(
    split: JobSplit,
    *,
    mode: str,
    matrix_stem: str,
    batch_id: int | None,
    costs: Mapping[str, PlannedPointCost],
    profile: HpcProfile | None,
) -> tuple[GroupedJob, list[str], str | None]:
    """Estimate one job, price its wall clock and name it; returns the job, warnings, refusal."""
    units = split.units
    sims = tuple(unit.sim_id for unit in units)
    overheads = MEASURED_OVERHEADS
    estimate, fallback, unestimated = job_estimate(split, overheads)
    maximum = profile.max_walltime_s if profile is not None else None
    walltime, source, fits, short, warnings, refusal = job_walltime(
        split, estimate, max_walltime_s=maximum
    )
    warnings = [*warnings, *_user_action_warnings(split)]
    if mode == "batch" and batch_id is not None:
        label = batch_label(matrix_stem, batch_id)
        script_name = batch_script_name(sims[0], sims[-1])
        name, folder = script_name.removesuffix(".txt"), f"sims/batch/{label}/"
        script = f"{folder}{script_name}"
    else:
        label, name = sims[0], _FULL_POLAR
        folder, script = f"sims/sim_{sims[0]}/", f"sims/sim_{sims[0]}/{_FULL_POLAR}.txt"
    run_ids = tuple(run_id for unit in units for run_id in unit.run_ids)
    bases = sorted({costs[r].basis for r in run_ids if r in costs and costs[r].seconds is not None})
    basis = "; ".join(bases) or "no recorded run to fit from"
    job = GroupedJob(
        name=name,
        batch_id=batch_id,
        label=label,
        dir=folder,
        script=script,
        sims=sims,
        points=run_ids,
        fs_build=units[0].fs_build,
        ncpus=units[0].ncpus,
        estimate_s=estimate,
        estimate_basis=f"{basis}; overheads: {overheads.basis}",
        fallback_points=tuple(fallback),
        unestimated_points=tuple(unestimated),
        overheads_s={
            "start": overheads.start_s,
            "reinit": overheads.reinit_s,
            "refresh": overheads.refresh_s,
        },
        factor=BEST_FACTOR,
        margin_s=max(unit.margin_s for unit in units),
        walltime_s=walltime,
        walltime_written=walltime_text(walltime, split=split) if walltime is not None else "",
        walltime_source=source,
        fits=fits is not False,
        shortfall_s=short,
    )
    return job, warnings, refusal


def _rejudged(
    plan: CampaignPlan,
    resolved: ResolvedMatrix,
    case: SimCase,
    *,
    workspace: CampaignWorkspace,
    version: str,
    registry: Mapping[str, ScriptRecipe] | None,
) -> list[PointPlan]:
    """Judge a BEST row's pending points again as a grouped job builds them (no WALLTIME)."""
    own = grouped_case(case)
    recipe = (registry or {}).get(case.recipe) or cast(ScriptRecipe, resolve_recipe(case.recipe))
    judged = [
        _plan_point(
            resolved.campaign,
            own,
            entry.point,
            workspace,
            recipe,
            None,
            set(),
            fs_version=version,
        )
        for entry in plan.points
        if entry.sim_id == case.sim_id and entry.status is not PlanStatus.ALREADY_RECORDED
    ]
    fresh = {entry.run_id: entry for entry in judged}
    plan.points[:] = [fresh.get(entry.run_id, entry) for entry in plan.points]
    return judged


def _splice_refusal(
    resolved: ResolvedMatrix,
    case: SimCase,
    pending: Sequence[PointPlan],
    *,
    workspace: CampaignWorkspace,
    version: str,
    registry: Mapping[str, ScriptRecipe] | None,
) -> str | None:
    """Dry-splice a polar: render each pending point and refuse the first that cannot splice.

    Each point is rendered as the plan renders it, without its WALLTIME, turned into a
    :class:`~pyflightstream.cases.workflows._batch_script.JobPoint` under the datapoint folder
    it would run in, and compared with the polar's first pending point.

    Returns
    -------
    str or None
        The refusal naming the line, or None when every point splices.
    """
    own = grouped_case(case)
    recipe = (registry or {}).get(case.recipe) or cast(ScriptRecipe, resolve_recipe(case.recipe))
    first: JobPoint | None = None
    try:
        for entry in pending:
            stem, outputs = _point_names(resolved.campaign, own, entry.point, workspace)
            point_case = case_at_point(own, entry.point, outputs=outputs)
            script = Script(version=version)
            recipe(point_case, script)
            point = job_point(
                point_case,
                run_id=entry.run_id,
                text=script.render(),
                datapoint_dir=PurePath(workspace.sim_dir(case.sim_id))
                / SIM_DATAPOINTS_DIR
                / f"DP-{entry.run_id.rpartition('/')[2]}",
                version=version,
            )
            if first is None:
                first = point
            else:
                refuse_unspliceable(first, point)
    except Exception as error:  # recipes are user code; a polar that cannot splice is left out
        return f"its points do not splice into one instance: {error}"
    return None


def _block(plan: CampaignPlan, run_ids: Sequence[str], error: str) -> None:
    """Mark the points BLOCKED with ``error`` in the plan, in place."""
    wanted = set(run_ids)
    plan.points[:] = [
        dataclasses.replace(entry, status=PlanStatus.BLOCKED, error=error)
        if entry.run_id in wanted
        else entry
        for entry in plan.points
    ]


def _eligible_units(
    plan: CampaignPlan,
    resolved: ResolvedMatrix,
    workspace: CampaignWorkspace,
    registry: Mapping[str, ScriptRecipe] | None,
) -> tuple[list[PolarUnit], list[dict[str, Any]]]:
    """Walk the polars in matrix order: the units that can group, the polars left out."""
    costs = {cost.run_id: cost for cost in plan.costs}
    units: list[PolarUnit] = []
    left_out: list[dict[str, Any]] = []
    for order, case in enumerate(resolved.campaign.sims, start=1):
        pending = [
            entry
            for entry in plan.points
            if entry.sim_id == case.sim_id and entry.status is not PlanStatus.ALREADY_RECORDED
        ]
        version = _version_of(plan, resolved, case)
        if not pending:
            left_out.append({"sim": case.sim_id, "reason": "every point is already recorded"})
            continue
        reason = eligibility(case, workspace=workspace, version=version)
        if reason is not None:
            left_out.append({"sim": case.sim_id, "reason": reason})
            continue
        if row_walltime_is_best(case):
            pending = _rejudged(
                plan, resolved, case, workspace=workspace, version=version, registry=registry
            )
        if any(entry.status is not PlanStatus.READY for entry in pending):
            continue  # the plan already names why a point is blocked
        refusal = _pristine_refusal(case)
        if refusal is not None:
            _block(plan, [entry.run_id for entry in pending], refusal)
            continue
        unspliceable = _splice_refusal(
            resolved, case, pending, workspace=workspace, version=version, registry=registry
        )
        if unspliceable is not None:
            left_out.append({"sim": case.sim_id, "reason": unspliceable})
            continue
        build = case.fs_build or plan.fs_version
        units.append(_unit_of(case, pending, costs, build, order))
    return units, left_out


def _profile_warnings(profile: HpcProfile | None) -> list[str]:
    """Return the warning a profile with no job end file earns for a batch (reading 1)."""
    if profile is None or profile.export_log or profile.job_end_files:
        return []
    return [
        "the profile states export_log = false and no job_end_files, so a batch is moved only "
        "if its clock fires; job_end_files makes the move possible."
    ]


def _write_receipt(plan: CampaignPlan, receipt: GroupingReceipt) -> None:
    """Rewrite ``plan.json`` in place with the ``grouping`` block and the points as judged."""
    if plan.plan_file is None:
        return
    payload = json.loads(plan.plan_file.read_text(encoding="utf-8"))
    judged = {entry.run_id: entry for entry in plan.points}
    for stored in payload["points"]:
        entry = judged.get(stored["run_id"])
        if entry is not None:
            stored["status"] = str(entry.status)
            stored["error"] = entry.error
    payload["grouping"] = receipt.to_json()
    _textio.write_json(plan.plan_file, payload)


def _revive_not_started(plan: CampaignPlan, workspace: CampaignWorkspace) -> None:
    """Make a failed point pending again for a grouped plan (FR-370, D5).

    The plain plan counts any record as recorded. A grouped plan reads a point
    whose latest record is a FAILED_* status (a point a previous job never
    started among them) as not recorded, so the next batch takes it; the
    grouped run archives that record and its outputs before it runs it.
    """
    latest = {record.run_id: record for record in workspace.read_manifest()}
    notes = {run_id for run_id, record in latest.items() if str(record.status).startswith("FAILED")}
    plan.points[:] = [
        dataclasses.replace(entry, status=PlanStatus.READY, error=None)
        if entry.status is PlanStatus.ALREADY_RECORDED and entry.run_id in notes
        else entry
        for entry in plan.points
    ]


def plan_grouped_matrix(
    path: str | Path,
    workspace: CampaignWorkspace,
    *,
    mode: Literal["batch", "polar_sweep"],
    batch: int | None,
    **keywords: Any,
) -> CampaignPlan:
    """Plan a matrix and group its unsteady polars into jobs (FR-362 to FR-365, FR-378).

    Plans the matrix with its costs as :func:`pyflightstream.run.matrix.plan_matrix` does, then
    leaves out and names the polars a job cannot hold (FR-379), blocks a polar whose geometry
    carries saved solver actions (FR-378), splits the rest (a job holds one set of the setup's
    own unsteady solver actions, FR-405) (``batch`` jobs, or one per polar
    for ``polar_sweep``), estimates each job, prices its wall clock and gives each batch the next
    free ID. The decision is written into ``plan.json`` as ``grouping`` and returned on the plan.

    Parameters
    ----------
    path : str or Path
        The run matrix.
    workspace : CampaignWorkspace
        The campaign workspace.
    mode : {"batch", "polar_sweep"}
        Group into ``batch`` jobs, or one job per polar.
    batch : int or None
        The number of jobs of ``--batch N``; None for a polar sweep.
    **keywords
        The keywords of :func:`pyflightstream.run.matrix.plan_matrix`.

    Returns
    -------
    CampaignPlan
        The plan, its ``grouping`` set; a point of a refused job or polar is BLOCKED.
    """
    plan = plan_matrix(path, workspace, **{**keywords, "cost": True})
    _revive_not_started(plan, workspace)
    default = keywords.get("default_fs_version") or keywords.get("fs_version")
    resolved = narrow_to_selection(
        resolve_matrix(
            path,
            workspace,
            name=keywords["name"],
            fs_version=default,
            recipes=keywords["recipes"],
            fs_exe=keywords.get("fs_exe"),
            ignore_missing_families=keywords.get("ignore_missing_families", True),
        ),
        keywords.get("sims"),
        keywords.get("points"),
        workspace,
    )
    units, left_out = _eligible_units(plan, resolved, workspace, keywords.get("recipe_registry"))
    profile = resolve_hpc_profile(workspace.inputs_dir)
    splits, warnings = (
        split_polars(units, int(batch or 1))
        if mode == "batch"
        else ([JobSplit((unit,)) for unit in units], [])
    )
    stem = Path(path).stem
    first_id = next_batch_id(workspace.root, stem)
    costs = {cost.run_id: cost for cost in plan.costs}
    jobs: list[GroupedJob] = []
    for index, split in enumerate(splits):
        batch_id = first_id + index if mode == "batch" else None
        job, notes, refusal = _job_of(
            split, mode=mode, matrix_stem=stem, batch_id=batch_id, costs=costs, profile=profile
        )
        jobs.append(job)
        warnings.extend(notes)
        if refusal is not None:
            warnings.append(f"{job.label}: {refusal}")
            _block(plan, job.points, refusal)
    warnings.extend(_profile_warnings(profile))
    known = [job.estimate_s for job in jobs if job.estimate_s is not None]
    receipt = GroupingReceipt(
        schema=GROUPING_SCHEMA,
        mode=mode,
        requested=batch if mode == "batch" else None,
        selection={"sims": keywords.get("sims"), "points": keywords.get("points")},
        jobs=tuple(jobs),
        left_out=tuple(left_out),
        total_estimate_s=sum(known) if known and len(known) == len(jobs) else None,
        longest_estimate_s=max(known) if known and len(known) == len(jobs) else None,
        max_walltime_s=int(profile.max_walltime_s) if profile and profile.max_walltime_s else None,
        warnings=tuple(warnings),
    )
    _write_receipt(plan, receipt)
    return dataclasses.replace(plan, grouping=receipt)
