"""The additional post: more products from a point's saved simulation, with no solve (G12).

Pipeline role: the run-layer half of ``pyfs-matrix post --additional-pproc``.
A matrix row may name a second pproc, ``ADDITIONAL_PPROC: p<id>``; for every
recorded point of that row whose final ``.fsm`` is on disk and hashes as its
record says, :func:`run_additional_post` writes and launches a script that
OPENS a copy of that file, cuts the additional pproc's section distributions,
updates the sections, computes their sectional loads, exports and closes. It
never solves, never saves and never samples the field off the body: RPT-062
measured on 26.124 what a reopened simulation gives back identically (the
total loads, the surface solution, every section and the sectional loads
computed on it, a new distribution included, and on an unsteady point the
plots history), and the plan refuses whatever it does not.

WHERE THINGS GO. The solver runs in the extraction's own folder,
``sims/sim_<POL>/datapoints/DP-<point>/additional/<pid>/``, and writes there;
the script goes under ``sims/sim_<POL>/scripts/additional/<pid>/``; the record
of each extraction goes to ``additional.json`` beside ``runs.json``, which is
never opened for writing, so the run's own record and its saved simulation
stay exactly as the run left them. The original ``.fsm`` is copied, the copy is
opened, and the original is hashed again after the launch.

WHAT IS SKIPPED, BY NAME, PER POINT (:class:`AdditionalSkip`): a row without
the key, a point whose saved simulation is not there or does not hash as its
record says, a point already extracted over the same bytes with the same
artifact, a point whose build is not the one its row names today, a run that
averaged its surface in time, a point whose run script no longer matches the
row (the frames would be cut in the wrong place), a job still in a queue, a
run a continuation replaced, a row no longer active.

THE SUBMITTING HALF IS NOT BUILT (0.27.0). The executor is chosen as
``pyfs-matrix run`` chooses it (:func:`~pyflightstream.run.matrix.campaign_executor`),
so ``local`` means the same thing; where that choice is a scheduler, the
extraction is refused by name before anything is written, naming ``--local``.
A submitted extraction needs a completion pass of its own (its copy of the
``.fsm`` kept until the job ends, its original hashed afterwards, its record
rewritten), which costs well over what the local half does.

This module imports the run layer, the workspace, the cases and the results
layers, and nothing from ``post``: the products of an extraction are written by
the post stage, which reads ``additional.json``.
"""

from __future__ import annotations

import enum
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePath

import pyflightstream
from pyflightstream._digest import file_sha256, optional_file_sha256
from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning, warn
from pyflightstream.cases import SimCase, case_at_point, classify_outputs
from pyflightstream.cases.workflows import (
    ADDITIONAL_PPROC_VARIABLE,
    additional_outputs,
    build_additional_script,
    frame_pairs,
    frames_of_the_run,
)
from pyflightstream.results.tables import superseded_by_a_continuation
from pyflightstream.run import (
    Executor,
    ExecutorConfigurationError,
    Submitting,
    invocation_record,
    package_vcs_state,
)
from pyflightstream.run.matrix import campaign_executor
from pyflightstream.script import Script
from pyflightstream.versions import resolve
from pyflightstream.workspace import (
    ADDITIONAL_DIR,
    ARCHIVE_DIR,
    ARCHIVE_STAMP,
    AdditionalRecord,
    CampaignWorkspace,
    ExtractionStatus,
    RunRecord,
    RunStatus,
)
from pyflightstream.workspace.matrix import ResolvedMatrix, resolve_matrix

__all__ = [
    "AdditionalPointPlan",
    "AdditionalSkip",
    "ONE_INSTANT",
    "REOPENED_SUFFIX",
    "plan_additional_post",
    "run_additional_post",
]

#: What an unsteady point's extraction is, said in its record and in a warning.
ONE_INSTANT = (
    "the saved simulation holds the LAST instant of this unsteady run (RPT-062): this "
    "extraction is that one instant and not the run's per-step history; its plots "
    "history is the run's own"
)

#: The name the matrix is bound under. The campaign name reaches no record the
#: additional post reads or writes: every identity comes from the run records.
_BOUND_AS = "additional_post"

#: The suffix of the copy of a saved simulation the solver opens.
REOPENED_SUFFIX = ".reopened.fsm"


class AdditionalSkip(enum.StrEnum):
    """Why a recorded point was not extracted, one word each (G12)."""

    #: The row the point belongs to is no longer an active row of the matrix.
    ROW_NOT_ACTIVE = "ROW_NOT_ACTIVE"
    #: The row states no ADDITIONAL_PPROC.
    NO_KEY = "NO_KEY"
    #: A continuation replaced this run; the end of the chain is the point.
    SUPERSEDED = "SUPERSEDED"
    #: The point is still in a scheduler's queue.
    NOT_FINISHED = "NOT_FINISHED"
    #: The record names no saved simulation, or the file it names is not there.
    NO_SAVED_SIMULATION = "NO_SAVED_SIMULATION"
    #: The file on disk does not hash as the record says, or the record holds no hash.
    HASH_MISMATCH = "HASH_MISMATCH"
    #: This pproc was already extracted over these bytes with this artifact.
    ALREADY_EXTRACTED = "ALREADY_EXTRACTED"
    #: The build the row names today is not the one the point ran on.
    BUILD_CHANGED = "BUILD_CHANGED"
    #: The run averaged its surface in time, which RPT-062 did not measure reopened.
    SURFACE_AVERAGED = "SURFACE_AVERAGED"
    #: The run's recorded script no longer matches the row's frames or boundaries.
    SCRIPT_DRIFT = "SCRIPT_DRIFT"


@dataclass(frozen=True)
class AdditionalPointPlan:
    """What the additional post will do for one recorded point.

    Attributes
    ----------
    run_id : str
        The point's run id.
    sim_id : str
        Its simulation, the matrix POL.
    point_name : str or None
        Its point name.
    pproc : str or None
        The additional pproc id its row states, or None.
    status : str
        ``READY`` or ``SKIPPED``.
    reason : AdditionalSkip or None
        Why a skipped point was skipped.
    message : str
        The sentence that says so, naming the path or the hashes involved.
    unsteady : bool
        Whether the point marched in time, so its extraction is one instant.
    fsm : str or None
        The saved simulation, relative to the simulation folder.
    script_text : str or None
        The extraction script of a READY point, built before any launch.
    """

    run_id: str
    sim_id: str
    point_name: str | None
    pproc: str | None
    status: str
    reason: AdditionalSkip | None = None
    message: str = ""
    unsteady: bool = False
    fsm: str | None = None
    script_text: str | None = None
    #: What the launch needs and a reader does not: the record the point came
    #: from, the folder, the build and the layout of the sections.
    context: Mapping[str, object] = field(default_factory=dict, repr=False, compare=False)


def _skipped(
    point: RunRecord, pproc: str | None, reason: AdditionalSkip, message: str
) -> AdditionalPointPlan:
    return AdditionalPointPlan(
        run_id=point.run_id,
        sim_id=point.sim_id,
        point_name=point.point_name,
        pproc=pproc,
        status="SKIPPED",
        reason=reason,
        message=message,
        unsteady=str(point.recipe or "").startswith("unsteady"),
    )


def _canonical(version: str) -> str:
    try:
        return resolve(version).canonical
    except PyflightstreamError:
        return str(version)


def _row_build(resolved: ResolvedMatrix, index: int, default: str | None) -> tuple[str, Path]:
    """Return the version and the executable a row's script is emitted under and run on today.

    The same reading ``run_matrix`` makes: the build the row names, with the
    version its registry entry declares, else the campaign default, else the
    build id; the campaign's own executable for a row that names none.
    """
    build = resolved.row_builds[index] if index < len(resolved.row_builds) else None
    registered = resolved.builds.get(build) if build else None
    version = (
        (registered.fs_version if registered is not None else None)
        or (default or "").strip()
        or build
        or resolved.campaign.fs_version
        or ""
    )
    exe = Path(registered.fs_exe) if registered is not None else Path(resolved.fs_exe)
    return _canonical(str(version)), exe


def _first_of_the_chain(point: RunRecord, by_run: Mapping[str, RunRecord]) -> RunRecord | None:
    """Walk ``continues`` back to the run that started the chain, or None if a link is gone."""
    seen = {point.run_id}
    current = point
    while current.continues:
        previous = by_run.get(current.continues)
        if previous is None or previous.run_id in seen:
            return None
        seen.add(previous.run_id)
        current = previous
    return current


def _first_difference(recorded: tuple, today: tuple) -> str:
    for at, (was, now) in enumerate(zip(recorded, today, strict=False)):
        if was != now:
            return f"frame {at + 1} of the run was {' '.join(was)} and is {' '.join(now)} today"
    if len(recorded) != len(today):
        return f"the run created {len(recorded)} frame(s) and the row creates {len(today)} today"
    return "no frame differs"


def _latest_extractions(records: list[AdditionalRecord]) -> dict[str, AdditionalRecord]:
    latest: dict[str, AdditionalRecord] = {}
    for record in records:
        latest[record.extraction_id] = record
    return latest


def _outputs_present(workspace: CampaignWorkspace, record: AdditionalRecord) -> bool:
    folder = workspace.sim_dir(record.sim_id)
    return bool(record.outputs) and all((folder / name).is_file() for name in record.outputs)


def _layout_of(point: RunRecord, script: Script, pproc: str) -> tuple[list[dict[str, object]], int]:
    """Return the run's own section blocks, then the extraction's, numbered on after the run's.

    RPT-062: a reopened export carries the distributions the run created first
    and the new ones after them, identical to the ones a run would have cut.
    """
    own = [dict(block) for block in (point.sections_layout or [])]
    leading = sum(
        int(count)
        for block in own
        if isinstance(count := block.get("count"), int) and not isinstance(count, bool)
    )
    offset = max(
        (
            int(number)
            for block in own
            if isinstance(number := block.get("distribution"), int) and not isinstance(number, bool)
        ),
        default=0,
    )
    added = []
    for block in script.section_blocks:
        entry = dict(block)
        number = entry.get("distribution")
        if isinstance(number, int) and not isinstance(number, bool):
            entry["distribution"] = offset + number
        entry["pproc"] = pproc
        added.append(entry)
    return own + added, leading


def plan_additional_post(
    matrix: str | Path,
    workspace: CampaignWorkspace,
    *,
    default_fs_version: str | None = None,
    recipes: Mapping[str, str] | None = None,
    fs_exe: str | Path | None = None,
) -> list[AdditionalPointPlan]:
    """Say, per recorded point of a matrix, what the additional post would do.

    Nothing is written and nothing is launched. The matrix is bound exactly as
    ``pyfs-matrix run`` binds it, so a key the plan refuses is refused here too;
    then every record of the manifest naming this matrix, one per point, is
    checked in this order: the row is active, it states ``ADDITIONAL_PPROC``,
    no continuation replaced it, it is not in a queue, its saved simulation is
    on disk, that file hashes as the record says, it was not already extracted
    over those bytes with that artifact, its build is the one the row names
    today, it did not average its surface in time, and the run's recorded
    script created the frames and declared the boundaries the row gives today.
    A point passing every check is READY with its extraction script built.

    Parameters
    ----------
    matrix : str or Path
        The run matrix; its file stem selects the records.
    workspace : CampaignWorkspace
        The campaign root holding ``runs.json`` and the input library.
    default_fs_version : str, optional
        The build a row whose FS_BUILD cell names none falls back to, as for
        ``pyfs-matrix run``.
    recipes : mapping of str to str, optional
        A LEGACY row's RECIPE code to its reference, so a matrix mixing them binds.
    fs_exe : str or Path, optional
        The explicit executable override, as for ``pyfs-matrix run``.

    Returns
    -------
    list of AdditionalPointPlan
        One per recorded point, in manifest order.

    Raises
    ------
    pyflightstream.cases.CampaignConfigError
        An extraction script that cannot be built (a distribution citing a frame
        the run did not create, a family the geometry refuses), before anything
        is launched; and every refusal of the plan of the matrix.
    pyflightstream.cases.matrix.MatrixError
        As ``pyfs-matrix plan`` raises it.
    pyflightstream.workspace.InputArtifactError
        As ``pyfs-matrix plan`` raises it.

    Warns
    -----
    pyflightstream.exceptions.PyflightstreamWarning
        Once per READY unsteady point: its extraction is one instant, the last.
    """
    return _plan_all(
        matrix,
        workspace,
        default_fs_version=default_fs_version,
        recipes=recipes,
        fs_exe=fs_exe,
    )[1]


def _plan_all(
    matrix: str | Path,
    workspace: CampaignWorkspace,
    *,
    default_fs_version: str | None,
    recipes: Mapping[str, str] | None,
    fs_exe: str | Path | None,
) -> tuple[ResolvedMatrix, list[AdditionalPointPlan]]:
    """Bind the matrix and judge every recorded point; the binding travels to the launch."""
    path = Path(matrix)
    resolved = resolve_matrix(
        path,
        workspace,
        name=_BOUND_AS,
        fs_version=default_fs_version,
        recipes=dict(recipes or {}),
        fs_exe=fs_exe,
    )
    cases = {case.sim_id: (index, case) for index, case in enumerate(resolved.campaign.sims)}
    records = [record for record in workspace.read_manifest() if record.matrix_stem == path.stem]
    points = [(record, point) for record in records for point in record.as_points()]
    superseded = superseded_by_a_continuation([point for _, point in points])
    by_run = {point.run_id: point for _, point in points}
    latest = _latest_extractions(workspace.read_additional())
    exe_digests: dict[Path, str | None] = {}
    plans: list[AdditionalPointPlan] = []
    for record, point in points:
        plans.append(
            _plan_point(
                workspace,
                resolved,
                cases,
                record,
                point,
                superseded=superseded,
                by_run=by_run,
                latest=latest,
                default=default_fs_version,
                exe_digests=exe_digests,
            )
        )
    for plan in plans:
        if plan.status == "READY" and plan.unsteady:
            warn(
                f"point={plan.run_id} product={ADDITIONAL_DIR}/{plan.pproc}: {ONE_INSTANT}.",
                PyflightstreamWarning,
                stacklevel=3,
            )
    return resolved, plans


def _plan_point(
    workspace: CampaignWorkspace,
    resolved: ResolvedMatrix,
    cases: Mapping[str, tuple[int, SimCase]],
    record: RunRecord,
    point: RunRecord,
    *,
    superseded: Mapping[str, str],
    by_run: Mapping[str, RunRecord],
    latest: Mapping[str, AdditionalRecord],
    default: str | None,
    exe_digests: dict[Path, str | None],
) -> AdditionalPointPlan:
    """Judge one recorded point, and build its extraction script where it passes."""
    found = cases.get(point.sim_id)
    if found is None:
        return _skipped(
            point,
            None,
            AdditionalSkip.ROW_NOT_ACTIVE,
            f"POL {point.sim_id} is no longer an active row of the matrix (RUN 0, or removed), "
            "so nothing states what to extract from it",
        )
    index, case = found
    pid = str(case.variables.get(ADDITIONAL_PPROC_VARIABLE) or "").strip() or None
    if pid is None:
        return _skipped(
            point,
            None,
            AdditionalSkip.NO_KEY,
            f"the row of POL {point.sim_id} states no {ADDITIONAL_PPROC_VARIABLE}, so there is "
            "no additional pproc to extract",
        )
    if point.run_id in superseded:
        return _skipped(
            point,
            pid,
            AdditionalSkip.SUPERSEDED,
            f"this run was continued by {superseded[point.run_id]}, whose saved simulation is "
            "the point's; that run is extracted instead",
        )
    if point.status is RunStatus.SUBMITTED:
        return _skipped(
            point,
            pid,
            AdditionalSkip.NOT_FINISHED,
            "the point is still in a scheduler's queue; collect it (pyfs-matrix collect) first",
        )
    sim_dir = workspace.sim_dir(point.sim_id)
    fsm = classify_outputs(point.outputs).get("simulation")
    if fsm is None:
        return _skipped(
            point,
            pid,
            AdditionalSkip.NO_SAVED_SIMULATION,
            "the record names no saved simulation (.fsm) among its outputs",
        )
    saved = sim_dir / fsm
    if not saved.is_file():
        return _skipped(
            point,
            pid,
            AdditionalSkip.NO_SAVED_SIMULATION,
            f"the saved simulation the record names is not at {saved}",
        )
    recorded = point.outputs_sha256.get(fsm)
    on_disk = file_sha256(saved)
    if recorded is None or recorded != on_disk:
        said = "holds no hash for it" if recorded is None else f"hashed {recorded[:12]}"
        return _skipped(
            point,
            pid,
            AdditionalSkip.HASH_MISMATCH,
            f"{saved} is {on_disk[:12]} on disk and the record {said}, so it is not the file "
            "the run saved",
        )
    artifact = resolved.additional_pprocs[pid]
    artifact_path = workspace.inputs_dir / "pproc" / f"{pid}.toml"
    pproc_sha256 = optional_file_sha256(artifact_path)
    extraction_id = f"{point.run_id}/{ADDITIONAL_DIR}/{pid}"
    done = latest.get(extraction_id)
    if (
        done is not None
        and done.status is ExtractionStatus.EXTRACTED
        and done.fsm_sha256 == recorded
        and done.pproc_sha256 == pproc_sha256
        and _outputs_present(workspace, done)
    ):
        return _skipped(
            point,
            pid,
            AdditionalSkip.ALREADY_EXTRACTED,
            f"{pid} was extracted from these bytes of the saved simulation with this artifact "
            f"on {done.finished_at or 'an earlier pass'}; its files are in {done.working_dir}",
        )
    version, exe = _row_build(resolved, index, default)
    if _canonical(point.fs_version_requested) != version:
        return _skipped(
            point,
            pid,
            AdditionalSkip.BUILD_CHANGED,
            f"the point ran on FlightStream {point.fs_version_requested} and its row names "
            f"{version} today; a saved simulation is reopened on the build that saved it",
        )
    if point.fs_exe_sha256:
        if exe not in exe_digests:
            exe_digests[exe] = optional_file_sha256(exe)
        today = exe_digests[exe]
        if today is not None and today != point.fs_exe_sha256:
            return _skipped(
                point,
                pid,
                AdditionalSkip.BUILD_CHANGED,
                f"the executable the row resolves today, {exe}, is {today[:12]} and the point "
                f"ran on one that hashed {point.fs_exe_sha256[:12]}",
            )
    elif point.fs_exe and PurePath(point.fs_exe) != PurePath(str(exe)):
        return _skipped(
            point,
            pid,
            AdditionalSkip.BUILD_CHANGED,
            f"the point ran on {point.fs_exe} and its row resolves {exe} today",
        )
    if point.surface_time_averaging is not None:
        return _skipped(
            point,
            pid,
            AdditionalSkip.SURFACE_AVERAGED,
            "the run averaged its surface solution in time ([time_averaging]); whether a "
            "reopened file gives back the average or an instant was not measured (RPT-062)",
        )
    stem = PurePath(fsm).stem
    geometry = (
        str(sim_dir / "inputs" / PurePath(str(case.geometry)).name) if case.geometry else None
    )
    point_case = case_at_point(
        case,
        dict(point.point),
        outputs=[PurePath(name).name for name in point.outputs],
        **({"geometry": geometry} if geometry is not None else {}),
    )
    drift = _script_drift(workspace, point, point_case, version, by_run)
    if isinstance(drift, str):
        return _skipped(point, pid, AdditionalSkip.SCRIPT_DRIFT, drift)
    shadow = drift
    folder = sim_dir / PurePath(fsm).parent / ADDITIONAL_DIR / pid
    unsteady = str(point.recipe or "").startswith("unsteady")
    extraction = point_case.model_copy(
        update={
            "pproc": artifact,
            "pproc_id": pid,
            "outputs": list(additional_outputs(artifact, stem=stem, unsteady=unsteady)),
        }
    )
    script = Script(version)
    build_additional_script(
        extraction, script, saved=str(folder / f"{stem}{REOPENED_SUFFIX}"), shadow=shadow
    )
    layout, leading = _layout_of(point, script, pid)
    return AdditionalPointPlan(
        run_id=point.run_id,
        sim_id=point.sim_id,
        point_name=point.point_name,
        pproc=pid,
        status="READY",
        message=f"extract {pid} into {folder.relative_to(sim_dir).as_posix()}/",
        unsteady=unsteady,
        fsm=fsm,
        script_text=script.render(),
        context={
            "record": record,
            "point": point,
            "case": extraction,
            "folder": folder,
            "stem": stem,
            "version": version,
            "exe": exe,
            "fsm_sha256": recorded,
            "pproc_sha256": pproc_sha256,
            "extraction_id": extraction_id,
            "layout": layout,
            "leading": leading,
            "frames": dict(shadow.frames_by_name or {}),
            "inventory": list(shadow.boundary_inventory)
            if shadow.boundary_inventory is not None
            else None,
        },
    )


def _script_drift(
    workspace: CampaignWorkspace,
    point: RunRecord,
    point_case: SimCase,
    version: str,
    by_run: Mapping[str, RunRecord],
) -> Script | str:
    """Build the point's run script again and compare it with the one the run recorded.

    Returns the rebuilt script when the two created the same frames at the same
    indices and declared the same boundaries, and otherwise the sentence saying
    where they part. The script compared is the one of the run that STARTED a
    continuation chain, since a continuation reopens and creates no frame.
    """
    first = _first_of_the_chain(point, by_run)
    if first is None:
        return (
            f"the run {point.run_id} continues a run the manifest no longer holds, so the "
            "frames its saved simulation carries cannot be read"
        )
    sim_dir = workspace.sim_dir(point.sim_id)
    if not first.script_path:
        return f"the record of {first.run_id} names no script"
    recorded = sim_dir / first.script_path
    if not recorded.is_file():
        return f"the script of {first.run_id} is not at {recorded}"
    if first.script_sha256 and file_sha256(recorded) != first.script_sha256:
        return f"the script of {first.run_id} at {recorded} no longer hashes as its record says"
    try:
        shadow = frames_of_the_run(point_case, version)
    except (PyflightstreamError, ValueError) as error:
        return f"the row no longer builds the run it recorded: {type(error).__name__}: {error}"
    was = frame_pairs(recorded.read_text(encoding="utf-8", errors="replace"))
    now = frame_pairs(shadow.render())
    if was != now:
        return (
            f"the row creates other frames today than the run created, so a distribution "
            f"would be cut in the wrong one: {_first_difference(was, now)}"
        )
    if point.inventory is not None and list(shadow.boundary_inventory or ()) != list(
        point.inventory
    ):
        return (
            f"the run declared the boundaries {', '.join(point.inventory)} and the geometry "
            f"declares {', '.join(shadow.boundary_inventory or ()) or 'none'} today"
        )
    return shadow


def run_additional_post(
    matrix: str | Path,
    workspace: CampaignWorkspace,
    *,
    default_fs_version: str | None = None,
    recipes: Mapping[str, str] | None = None,
    fs_exe: str | Path | None = None,
    executor: Executor | None = None,
    local: bool = False,
    hidden: bool | None = None,
) -> tuple[list[AdditionalPointPlan], list[AdditionalRecord]]:
    """Extract every READY point's additional pproc from its saved simulation, with no solve.

    The plan first (:func:`plan_additional_post`), so every script is built
    before the first launch and a refusal costs nothing. Then, per READY point,
    ONE launch: anything already in the extraction's folder moves to its
    ``archive/<stamp>/`` (nothing is deleted); the saved simulation is COPIED
    there and the copy must hash as the record says; the script is written
    under ``scripts/additional/<pid>/`` and run with the extraction's folder as
    the working directory; every declared output must exist and is hashed; the
    copy is removed; the ORIGINAL is hashed again, and an original that moved
    fails the extraction loudly. One record per launch goes to
    ``additional.json``; ``runs.json`` is never opened for writing.

    Parameters
    ----------
    matrix, workspace, default_fs_version, recipes, fs_exe
        As :func:`plan_additional_post`.
    executor : Executor, optional
        A caller's executor, which answers for every build; by default the one
        ``pyfs-matrix run`` would build for this matrix.
    local : bool
        Keep the extraction on this machine, as ``pyfs-matrix run --local``.
    hidden : bool or None
        Windowless solver runs; None lets the matrix's HIDDEN column decide.

    Returns
    -------
    tuple of (list of AdditionalPointPlan, list of AdditionalRecord)
        The plan of every recorded point and the record of every launch.

    Raises
    ------
    pyflightstream.run.ExecutorConfigurationError
        Where the executor chosen is a scheduler: the submitting half is not
        built in 0.27.0, so the extraction is refused before anything is
        written; pass ``local=True``.
    pyflightstream.cases.CampaignConfigError
        As :func:`plan_additional_post`.
    """
    resolved, plans = _plan_all(
        matrix,
        workspace,
        default_fs_version=default_fs_version,
        recipes=recipes,
        fs_exe=fs_exe,
    )
    ready = [plan for plan in plans if plan.status == "READY"]
    if not ready:
        return plans, []
    campaign, executor_for = campaign_executor(
        workspace, resolved, matrix, executor=executor, local=local, hidden=hidden
    )
    if isinstance(campaign, Submitting):
        raise ExecutorConfigurationError(
            "the additional post runs on this machine in 0.27.0, and this workspace submits "
            "from here (a submission profile on a cluster): completing a submitted "
            "extraction is not built. Nothing was written. Pass local (CLI: --local) to "
            "reopen the saved simulations on this machine."
        )
    executors: dict[Path, Executor] = {Path(resolved.fs_exe): campaign}
    stamp = datetime.now().strftime(ARCHIVE_STAMP)
    written: list[AdditionalRecord] = []
    for plan in ready:
        exe = Path(str(plan.context["exe"]))
        if exe not in executors:
            executors[exe] = executor_for(exe)
        written.append(_extract(workspace, plan, executors[exe], stamp=stamp))
    return plans, written


def _extract(
    workspace: CampaignWorkspace, plan: AdditionalPointPlan, executor: Executor, *, stamp: str
) -> AdditionalRecord:
    """Launch one READY point's extraction and record it."""
    context = plan.context
    point = context["point"]
    record = context["record"]
    case = context["case"]
    folder = context["folder"]
    assert isinstance(point, RunRecord) and isinstance(record, RunRecord)
    assert isinstance(case, SimCase) and isinstance(folder, Path)
    assert plan.fsm is not None and plan.pproc is not None and plan.script_text is not None
    sim_dir = workspace.sim_dir(point.sim_id)
    original = sim_dir / plan.fsm
    recorded = str(context["fsm_sha256"])
    # WHATEVER AN EARLIER PASS LEFT MOVES ASIDE, the archive_datapoint rule: a
    # declared output already in the folder would be collected as this launch's.
    if folder.is_dir():
        movable = [child for child in folder.iterdir() if child.name != ARCHIVE_DIR]
        if movable:
            target = folder / ARCHIVE_DIR / stamp
            target.mkdir(parents=True, exist_ok=True)
            for child in movable:
                child.replace(target / child.name)
    folder.mkdir(parents=True, exist_ok=True)
    copy = folder / f"{context['stem']}{REOPENED_SUFFIX}"
    shutil.copy2(original, copy)
    (sim_dir / "scripts" / ADDITIONAL_DIR / plan.pproc).mkdir(parents=True, exist_ok=True)
    script_path, script_sha = workspace.write_script(
        point.sim_id, _script_name(plan.pproc, str(context["stem"])), plan.script_text
    )
    commit, dirty = package_vcs_state()
    base: dict[str, object] = {
        "extraction_id": str(context["extraction_id"]),
        "run_id": point.run_id,
        "job_id": record.run_id if record.points_ran else None,
        "sim_id": point.sim_id,
        "point_name": point.point_name,
        "matrix_stem": point.matrix_stem,
        "pproc": plan.pproc,
        "pproc_sha256": context["pproc_sha256"],
        "fsm": plan.fsm,
        "fsm_sha256": recorded,
        "unsteady": plan.unsteady,
        "note": ONE_INSTANT if plan.unsteady else None,
        "fs_version_requested": str(context["version"]),
        "fs_exe": str(context["exe"]),
        "fs_exe_sha256": optional_file_sha256(Path(str(context["exe"]))),
        "package_version": pyflightstream.__version__,
        "package_commit": commit,
        "package_dirty": dirty,
        "script_path": script_path.relative_to(sim_dir).as_posix(),
        "script_sha256": script_sha,
        "working_dir": folder.relative_to(sim_dir).as_posix(),
        "sections_layout": context["layout"],
        "leading_sections": context["leading"],
        "frames": context["frames"],
        "inventory": context["inventory"],
    }
    copied = file_sha256(copy)
    if copied != recorded:
        copy.unlink(missing_ok=True)
        return _recorded(
            workspace,
            base,
            status=ExtractionStatus.FAILED_EXECUTION,
            error=f"the copy of {original} hashed {copied[:12]}, not {recorded[:12]}; nothing ran",
            original=original,
        )
    result = executor.run_script(script_path, working_dir=folder, timeout_s=case.solver.timeout_s)
    copy.unlink(missing_ok=True)
    base.update(
        {
            "argv": list(result.argv),
            "cwd": result.cwd,
            "timeout_s": result.timeout_s,
            "executor": invocation_record(executor, result),
            "started_at": result.started_at,
            "finished_at": result.finished_at,
            "wall_time_s": result.wall_time_s,
        }
    )
    if result.failed:
        return _recorded(
            workspace,
            base,
            status=ExtractionStatus.FAILED_EXECUTION,
            error=result.diagnosis(),
            original=original,
        )
    relative = folder.relative_to(sim_dir).as_posix()
    names = [f"{relative}/{name}" for name in case.outputs]
    missing = [name for name in names if not (sim_dir / name).is_file()]
    if missing:
        return _recorded(
            workspace,
            base,
            status=ExtractionStatus.FAILED_INCOMPLETE_OUTPUT,
            error=f"the extraction ended and did not write {', '.join(missing)}",
            original=original,
            outputs=[name for name in names if name not in missing],
        )
    return _recorded(
        workspace,
        base,
        status=ExtractionStatus.EXTRACTED,
        error=None,
        original=original,
        outputs=names,
    )


def _script_name(pproc: str, stem: str) -> str:
    return f"{ADDITIONAL_DIR}/{pproc}/{stem}.txt"


def _recorded(
    workspace: CampaignWorkspace,
    base: Mapping[str, object],
    *,
    status: ExtractionStatus,
    error: str | None,
    original: Path,
    outputs: list[str] | None = None,
) -> AdditionalRecord:
    """Hash the original again, then write the record; an original that moved fails it."""
    sim_dir = workspace.sim_dir(str(base["sim_id"]))
    after = optional_file_sha256(original)
    if after != base["fsm_sha256"]:
        status = ExtractionStatus.FAILED_EXECUTION
        error = (
            f"THE ORIGINAL SAVED SIMULATION MOVED during the extraction: {original} hashed "
            f"{str(base['fsm_sha256'])[:12]} before and {(after or 'nothing')[:12]} after. "
            "The extraction opens a copy and never the original, so something else wrote "
            "it; the point's record no longer describes the file." + (f" {error}" if error else "")
        )
    listed = outputs or []
    record = AdditionalRecord.model_validate(
        {
            **base,
            "fsm_sha256_after": after,
            "status": status,
            "error": error,
            "outputs": listed,
            "outputs_sha256": {name: file_sha256(sim_dir / name) for name in listed},
        }
    )
    workspace.append_additional(record)
    return record
