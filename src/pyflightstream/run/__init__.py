"""Execution of FlightStream and the campaign loop.

Pipeline role: runs the solver headless on rendered scripts and lands
every campaign point in the manifest with exactly one terminal status.
:func:`run_campaign` composes an :class:`Executor` with the managed
workspace of :mod:`pyflightstream.workspace`; there is no code path
from "point started" to "loop continued" that does not write a status,
so silent skips are structurally impossible (PP-5, FR-14). Failures
accumulate into :class:`CampaignErrors`, raised after the loop.

Before any execution, :func:`plan_campaign` pre-flights the same
campaign: it resolves every recipe, allocates the managed folders,
verifies the geometry files exist, and builds every script in dry run
(the builder validates phase, version, and entity references without a
solver), returning one status per point and writing the plan summary
into the campaign root. Re-running a campaign into the same root uses
``run_campaign(..., resume=True)``, which skips the points already
recorded in the manifest; the manifest's append-only duplicate
rejection is what makes the skip safe, and with ``resume=False`` a
duplicate point raises before anything executes.

The local mechanism is the documented command-line script execution:
``FlightStream.exe --script <file>`` (SRC-003 p.279), with the
``-hidden`` flag for windowless batch runs; in hidden mode an
abnormal termination writes ``FlightStreamLog.txt`` into the command
execution directory, which is why the executor runs the solver inside
the simulation folder and captures that file (SRC-003 p.280). An HPC
executor with the same interface is deferred (FR-15).

Judging solver quality (converged, iteration limited, diverged) needs
the solver outputs, so :func:`run_campaign` takes an
:class:`OutcomeAssessor`; the standard implementation is
:class:`LoadsAssessor`, built on the anchor-based parsers of
:mod:`pyflightstream.results`.
"""

from __future__ import annotations

import enum
import json
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol

import pyflightstream
from pyflightstream.cases import Campaign, ScriptRecipe, SimCase, point_tag, resolve_recipe
from pyflightstream.results import (
    IncompleteOutputError,
    parse_loads,
    parse_residual_history,
)
from pyflightstream.script import Script
from pyflightstream.script.solver_setup import SolverSetup
from pyflightstream.versions import FsVersion, resolve
from pyflightstream.workspace import (
    CampaignWorkspace,
    NamingTemplateError,
    RunRecord,
    RunStatus,
    WorkspaceError,
)

_LOG_NAME = "FlightStreamLog.txt"


class ExecutorConfigurationError(ValueError):
    """The executor cannot run as configured.

    Raised at construction time, because a missing solver executable
    must surface before a campaign starts, not at its first point.
    The FlightStream path is always explicit input (SAD Section 5):
    nothing is read from environment variables or guessed.
    """


@dataclass(frozen=True)
class ExecutionResult:
    """Typed outcome of one solver process.

    Attributes
    ----------
    return_code : int or None
        Process return code; None when the run timed out and the
        process was killed.
    wall_time_s : float
        Wall-clock duration of the process in seconds.
    timed_out : bool
        Whether the timeout expired before the process finished.
    log_text : str or None
        Content of ``FlightStreamLog.txt`` from the execution
        directory when the solver wrote one (hidden-mode abnormal
        termination, SRC-003 p.280); None otherwise.
    stdout : str
        Captured standard output of the process.
    stderr : str
        Captured standard error of the process.
    """

    return_code: int | None
    wall_time_s: float
    timed_out: bool
    log_text: str | None
    stdout: str
    stderr: str

    @property
    def failed(self) -> bool:
        """Whether the process timed out or returned a nonzero code."""
        return self.timed_out or self.return_code != 0


class Executor(Protocol):
    """Anything that can run one rendered script to completion.

    Implementations must be interchangeable without touching the
    campaign model (FR-15): :class:`LocalExecutor` today, an HPC
    submission executor later.
    """

    def run_script(
        self, script_path: Path, working_dir: Path, timeout_s: float | None = None
    ) -> ExecutionResult:
        """Run one script and return the typed outcome."""
        ...


class LocalExecutor:
    """Runs FlightStream as a local subprocess (SRC-003 pp.279-280).

    Parameters
    ----------
    fs_exe : str or Path
        Explicit path of the FlightStream executable; it must exist.
        Never read from environment variables or guessed.
    hidden : bool
        Pass the ``-hidden`` flag for a windowless run; this is the
        batch mode that writes ``FlightStreamLog.txt`` on abnormal
        termination (SRC-003 p.280). Disable only for local debugging
        with the interface visible.
    """

    def __init__(self, fs_exe: str | Path, hidden: bool = True):
        self.fs_exe = Path(fs_exe)
        self.hidden = hidden
        if not self.fs_exe.is_file():
            raise ExecutorConfigurationError(
                f"FlightStream executable not found at {self.fs_exe}. The path is "
                "explicit campaign input (fs_exe); check the installation folder of "
                "the version the campaign requests."
            )

    def _argv(self, script_path: Path) -> list[str]:
        argv = [str(self.fs_exe)]
        if self.hidden:
            argv.append("-hidden")
        argv.extend(["--script", str(script_path)])
        return argv

    def run_script(
        self, script_path: Path, working_dir: Path, timeout_s: float | None = None
    ) -> ExecutionResult:
        """Run one rendered script to completion.

        The process runs inside ``working_dir`` so that the hidden-mode
        error log lands next to the run's files and can be captured.

        Parameters
        ----------
        script_path : Path
            Rendered ASCII script to execute.
        working_dir : Path
            Execution directory of the process; also where
            ``FlightStreamLog.txt`` appears on abnormal termination.
        timeout_s : float, optional
            Wall-clock limit; on expiry the process is killed and the
            result reports ``timed_out``.

        Returns
        -------
        ExecutionResult
            Typed outcome; no exception is raised for solver failure,
            the campaign loop decides the manifest status.
        """
        argv = self._argv(script_path)
        start = time.perf_counter()
        timed_out = False
        return_code: int | None = None
        stdout = ""
        stderr = ""
        try:
            completed = subprocess.run(
                argv,
                cwd=working_dir,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
            return_code = completed.returncode
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
        except subprocess.TimeoutExpired as expired:
            timed_out = True
            stdout = _decode(expired.stdout)
            stderr = _decode(expired.stderr)
        wall_time_s = time.perf_counter() - start
        log_path = Path(working_dir) / _LOG_NAME
        log_text = None
        if log_path.is_file():
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
        return ExecutionResult(
            return_code=return_code,
            wall_time_s=wall_time_s,
            timed_out=timed_out,
            log_text=log_text,
            stdout=stdout,
            stderr=stderr,
        )


def _decode(stream: str | bytes | None) -> str:
    if stream is None:
        return ""
    if isinstance(stream, bytes):
        return stream.decode(errors="replace")
    return stream


@dataclass(frozen=True)
class Assessment:
    """Judgment of one successfully executed point.

    Attributes
    ----------
    status : RunStatus
        ``CONVERGED``, ``COMPLETED_MAX_ITER``, or ``FAILED_DIVERGED``;
        execution and completeness failures are decided by the loop
        before the assessor runs.
    iterations : int, optional
        Solver iterations reached, when the assessor parsed them.
    residual : float, optional
        Final residual, when parsed.
    error : str, optional
        Explanation for a diverged judgment.
    fs_version_reported : str, optional
        Version string printed in the assessed output, verbatim
        (FR-18).
    fs_build : str, optional
        Build number printed in the assessed output.
    """

    status: RunStatus
    iterations: int | None = None
    residual: float | None = None
    error: str | None = None
    fs_version_reported: str | None = None
    fs_build: str | None = None


class OutcomeAssessor(Protocol):
    """Judges solver quality from the outputs of one executed point.

    The campaign loop already handled execution failure and missing
    declared outputs; the assessor inspects the collected outputs (in
    ``sim_dir / "raw"``) and decides between converged, iteration
    limited, and diverged. The standard implementation lands with the
    results parsers.
    """

    def __call__(self, case: SimCase, execution: ExecutionResult, sim_dir: Path) -> Assessment:
        """Return the judgment of one executed point."""
        ...


class LoadsAssessor:
    """The standard solver-quality judgment, built on the run outputs.

    Reads the collected loads spreadsheet and, when available, the
    exported solver log, and decides between CONVERGED,
    COMPLETED_MAX_ITER, and FAILED_DIVERGED:

    - NaN or infinite Total coefficients: FAILED_DIVERGED.
    - With a log: the final velocity and pressure residuals against
      the run's convergence limit (SRC-003 p.200); NaN residuals are
      a divergence.
    - Without a log, steady mode: an iteration counter below the
      requested limit means the threshold stopped the solver
      (CONVERGED); reaching the limit means COMPLETED_MAX_ITER.
    - Without a log, unsteady mode: the time loop always runs to its
      prescribed end, so completion is recorded as
      COMPLETED_MAX_ITER; declare the log export to get a residual
      judgment.

    An unparseable or truncated loads file is FAILED_INCOMPLETE_OUTPUT.

    Parameters
    ----------
    loads_file : str
        Name of the loads spreadsheet among the case's declared
        outputs (collected into ``raw/``).
    log_file : str, optional
        Name of the exported solver log (EXPORT_LOG), when the recipe
        declares one; enables the residual-based judgment.
    requested_version : str or FsVersion, optional
        Version the campaign requested; enables the FR-18 cross-check
        against the version printed in the loads footer.
    """

    def __init__(
        self,
        loads_file: str,
        log_file: str | None = None,
        requested_version: str | FsVersion | None = None,
    ):
        self.loads_file = loads_file
        self.log_file = log_file
        self.requested_version = requested_version

    def __call__(self, case: SimCase, execution: ExecutionResult, sim_dir: Path) -> Assessment:
        """Judge one executed point from its collected outputs."""
        raw = Path(sim_dir) / "raw"
        try:
            text = (raw / self.loads_file).read_text(encoding="utf-8", errors="replace")
            report = parse_loads(text, requested_version=self.requested_version)
        except (OSError, IncompleteOutputError, ValueError) as error:
            return Assessment(
                status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
                error=f"loads spreadsheet unusable: {error}",
            )
        stamp = {
            "fs_version_reported": report.fs_version_reported,
            "fs_build": report.fs_build,
        }
        diverged = report.diverged_columns()
        if diverged:
            return Assessment(
                status=RunStatus.FAILED_DIVERGED,
                iterations=report.current_iteration,
                error=f"non-finite Total coefficients: {', '.join(diverged)}",
                **stamp,
            )
        if self.log_file is not None and (raw / self.log_file).is_file():
            log_text = (raw / self.log_file).read_text(encoding="utf-8", errors="replace")
            try:
                final = parse_residual_history(log_text)[-1]
            except (IncompleteOutputError, ValueError) as error:
                return Assessment(
                    status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
                    error=f"solver log unusable: {error}",
                    **stamp,
                )
            residual = max(final.velocity_residual, final.pressure_residual)
            if residual != residual:  # NaN
                return Assessment(
                    status=RunStatus.FAILED_DIVERGED,
                    iterations=final.iteration,
                    error="final residuals are NaN",
                    **stamp,
                )
            converged = residual <= report.convergence_limit
            return Assessment(
                status=RunStatus.CONVERGED if converged else RunStatus.COMPLETED_MAX_ITER,
                iterations=final.iteration,
                residual=residual,
                **stamp,
            )
        if report.solver_mode.strip().lower() == "steady":
            stopped_early = report.current_iteration < report.requested_iterations
            return Assessment(
                status=RunStatus.CONVERGED if stopped_early else RunStatus.COMPLETED_MAX_ITER,
                iterations=report.current_iteration,
                **stamp,
            )
        return Assessment(
            status=RunStatus.COMPLETED_MAX_ITER,
            iterations=report.current_iteration,
            error=None,
            **stamp,
        )


class CampaignErrors(RuntimeError):  # noqa: N818 (the SAD Section 7 name)
    """One or more campaign points failed; raised after the loop.

    Every failed point is listed with its status and error text, and
    all points, failed or not, are already in the manifest: the
    exception reports, it never hides.

    Attributes
    ----------
    failures : list of RunRecord
        The manifest records of the failed points.
    """

    def __init__(self, failures: list[RunRecord]):
        self.failures = failures
        lines = "\n".join(
            f"  {record.run_id}: {record.status} ({record.error or 'no error text'})"
            for record in failures
        )
        super().__init__(
            f"{len(failures)} campaign point(s) failed; every point is recorded in "
            f"the manifest:\n{lines}"
        )


def run_campaign(
    campaign: Campaign,
    executor: Executor,
    workspace: CampaignWorkspace,
    assess: OutcomeAssessor,
    recipes: dict[str, ScriptRecipe] | None = None,
    resume: bool = False,
) -> list[RunRecord]:
    """Run every point of a campaign, recording each in the manifest.

    Per point, in order: specialize the case (sweep point and staged
    geometry), build the script through the recipe (failure:
    FAILED_SCRIPT), execute it (failure or timeout:
    FAILED_EXECUTION), collect the declared outputs into ``raw/``
    (missing output: FAILED_INCOMPLETE_OUTPUT), and judge the solver
    quality through ``assess`` (CONVERGED, COMPLETED_MAX_ITER, or
    FAILED_DIVERGED). Exactly one record per point is appended to the
    manifest; an unexpected internal error crashes the loop loudly
    instead of masquerading as a solver status.

    Parameters
    ----------
    campaign : Campaign
        What to run; its ``fs_version`` is resolved to canonical for
        the manifest.
    executor : Executor
        How to run it, for example :class:`LocalExecutor` built from
        ``campaign.fs_exe``.
    workspace : CampaignWorkspace
        The managed campaign root receiving folders, scripts, outputs,
        and the manifest; its naming template renders the generated
        script names and any placeholders in the declared output
        names.
    assess : OutcomeAssessor
        Solver-quality judgment; required because the loop refuses to
        invent convergence evidence it cannot see.
    recipes : dict of str to ScriptRecipe, optional
        Named recipe registry consulted before treating
        :attr:`SimCase.recipe` as a ``module:function`` reference;
        the run-matrix entry
        (:func:`pyflightstream.cases.matrix.run_matrix`) forwards its
        recipe registry here.
    resume : bool
        With True, points whose ``run_id`` is already in the manifest
        are skipped without execution, so a campaign can grow sweep
        points and re-run into the same root; the manifest's
        append-only duplicate rejection is what makes the skip safe.
        With False (the default) a duplicate point raises
        :class:`~pyflightstream.workspace.WorkspaceError` before
        anything executes, because silently redoing recorded evidence
        would fork the run identity.

    Returns
    -------
    list of RunRecord
        The records executed by this call, in execution order; points
        skipped by ``resume`` keep their existing manifest records and
        are not repeated here.

    Raises
    ------
    CampaignErrors
        After the loop, when at least one executed point failed.
    WorkspaceError
        On the first already-recorded point when ``resume`` is False.
    """
    canonical = resolve(campaign.fs_version).canonical
    recorded = {record.run_id for record in workspace.read_manifest()}
    records: list[RunRecord] = []
    failures: list[RunRecord] = []
    for case in campaign.sims:
        sim_dir = workspace.create_sim(case.sim_id)
        recipe, preparation_error, inputs_sha256, staged_geometry = _prepare_case(
            case, workspace, recipes
        )
        for point in case.sweep.points():
            run_id = _run_id(campaign, case, point)
            if run_id in recorded:
                if resume:
                    continue
                raise WorkspaceError(
                    f"run_id {run_id!r} is already in the manifest of "
                    f"{workspace.root}; re-running a recorded point would fork the "
                    "run identity. Pass resume=True to skip recorded points (and "
                    "run only the new ones), or archive the simulation / choose a "
                    "new campaign root to redo it."
                )
            record = _execute_point(
                campaign=campaign,
                canonical=canonical,
                case=case,
                point=point,
                run_id=run_id,
                recipe=recipe,
                preparation_error=preparation_error,
                inputs_sha256=inputs_sha256,
                staged_geometry=staged_geometry,
                executor=executor,
                workspace=workspace,
                sim_dir=sim_dir,
                assess=assess,
            )
            workspace.append_record(record)
            recorded.add(record.run_id)
            records.append(record)
            if record.status.startswith("FAILED"):
                failures.append(record)
    if failures:
        raise CampaignErrors(failures)
    return records


def _run_id(campaign: Campaign, case: SimCase, point: dict[str, float]) -> str:
    """Compose the fixed manifest identity of one campaign point.

    The scheme ``<campaign>/sim_<sim_id>/<point_tag>`` is identity,
    not presentation: it never goes through the naming template, so
    renaming outputs can never fork or collide run identities.
    """
    return f"{campaign.name}/sim_{case.sim_id}/{point_tag(point)}"


def _point_names(
    campaign: Campaign,
    case: SimCase,
    point: dict[str, float],
    workspace: CampaignWorkspace,
) -> tuple[str, list[str]]:
    """Render the human-readable names of one point, output only.

    Returns the script file stem and the declared output names with
    their placeholders rendered; the recipe sees the rendered names in
    :attr:`SimCase.outputs`, so what it exports is what the loop
    collects. The default template reproduces the historical names.
    """
    stem = workspace.naming.render_point(
        campaign=campaign.name, sim=case.sim_id, point=point, mach=case.mach
    )
    outputs = [
        workspace.naming.render_output(
            name, campaign=campaign.name, sim=case.sim_id, point=point, mach=case.mach
        )
        for name in case.outputs
    ]
    return stem, outputs


class PlanStatus(enum.StrEnum):
    """Pre-flight status of one campaign point (no execution involved).

    READY: the recipe resolved, the geometry exists, and the script
    built and rendered in dry run. BLOCKED: something failed before any
    solver could run; the plan carries the error text.
    ALREADY_RECORDED: the manifest already holds this ``run_id``, so
    ``run_campaign(..., resume=True)`` would skip it.
    """

    READY = "READY"
    BLOCKED = "BLOCKED"
    ALREADY_RECORDED = "ALREADY_RECORDED"


@dataclass(frozen=True)
class PointPlan:
    """Pre-flight judgment of one campaign point.

    Attributes
    ----------
    run_id : str
        Manifest identity the point would run under.
    sim_id : str
        Simulation identity of the case.
    point : dict of str to float
        Sweep point coordinates (alpha and beta in deg, advance_ratio
        dimensionless).
    script_name : str or None
        File name the generated script would take (from the naming
        template); None when the name itself could not be rendered.
    status : PlanStatus
        The pre-flight status.
    error : str or None
        What blocks the point, for BLOCKED entries.
    """

    run_id: str
    sim_id: str
    point: dict[str, float]
    script_name: str | None
    status: PlanStatus
    error: str | None = None


@dataclass(frozen=True)
class CampaignPlan:
    """The pre-flight plan of one campaign: statuses per point, no execution.

    Attributes
    ----------
    campaign : str
        Campaign name.
    fs_version : str
        Canonical FlightStream version the scripts were validated
        against.
    points : list of PointPlan
        One entry per campaign point, in campaign order.
    plan_file : Path or None
        Where the JSON summary was written (``plan.json`` in the
        campaign root), or None when writing was disabled.
    """

    campaign: str
    fs_version: str
    points: list[PointPlan] = field(default_factory=list)
    plan_file: Path | None = None

    @property
    def blocked(self) -> list[PointPlan]:
        """The points that cannot run as planned."""
        return [entry for entry in self.points if entry.status is PlanStatus.BLOCKED]

    @property
    def ready(self) -> list[PointPlan]:
        """The points that built cleanly in dry run."""
        return [entry for entry in self.points if entry.status is PlanStatus.READY]

    @property
    def already_recorded(self) -> list[PointPlan]:
        """The points the manifest already holds (resume would skip them)."""
        return [entry for entry in self.points if entry.status is PlanStatus.ALREADY_RECORDED]

    def summary(self) -> str:
        """Return the one-paragraph human summary of the plan."""
        lines = [
            f"campaign {self.campaign!r} on FlightStream {self.fs_version}: "
            f"{len(self.ready)} ready, {len(self.blocked)} blocked, "
            f"{len(self.already_recorded)} already recorded"
        ]
        for entry in self.blocked:
            lines.append(f"  {entry.run_id}: {entry.error}")
        return "\n".join(lines)


def plan_campaign(
    campaign: Campaign,
    workspace: CampaignWorkspace,
    recipes: dict[str, ScriptRecipe] | None = None,
    write_plan: bool = True,
) -> CampaignPlan:
    """Pre-flight a campaign: validate every point without executing any.

    Per case, in order: allocate the managed simulation folders,
    resolve the recipe, and verify the geometry file exists; per
    point: render the output names through the naming template and
    build the whole script in dry run (the builder validates phase,
    version, and entity references without a solver, and the dry-run
    script is not written to ``scripts/``, so the files of a later
    real run stay the only scripts on disk). Points whose ``run_id``
    is already in the manifest are marked ALREADY_RECORDED, which is
    exactly what ``run_campaign(..., resume=True)`` would skip; this
    pairing is what lets a sweep grow points and re-run safely.

    Nothing is executed and nothing is appended to the manifest: a
    broken recipe or a missing geometry surfaces here, before any
    solver time is spent, instead of as a FAILED_SCRIPT record inside
    the campaign loop.

    Parameters
    ----------
    campaign : Campaign
        What would run; its ``fs_version`` is resolved to canonical
        and every dry-run script is validated against it.
    workspace : CampaignWorkspace
        The managed campaign root; folders are allocated, the
        manifest is read, nothing else is touched.
    recipes : dict of str to ScriptRecipe, optional
        Named recipe registry, as in :func:`run_campaign`.
    write_plan : bool
        Write the JSON summary as ``plan.json`` in the campaign root
        (overwritten on each call; a convenience report, never an
        identity source). Default True.

    Returns
    -------
    CampaignPlan
        One :class:`PointPlan` per point; inspect ``blocked`` before
        running, or print ``summary()``.
    """
    canonical = resolve(campaign.fs_version).canonical
    recorded = {record.run_id for record in workspace.read_manifest()}
    points: list[PointPlan] = []
    for case in campaign.sims:
        workspace.create_sim(case.sim_id)
        case_error = _plan_case_error(case, workspace, recipes)
        recipe = None
        if case_error is None:
            recipe = (
                recipes[case.recipe]
                if recipes and case.recipe in recipes
                else resolve_recipe(case.recipe)
            )
        for point in case.sweep.points():
            points.append(
                _plan_point(campaign, case, point, workspace, recipe, case_error, recorded)
            )
    plan_file = None
    if write_plan:
        plan_file = workspace.root / "plan.json"
        payload = {
            "campaign": campaign.name,
            "fs_version": canonical,
            "package_version": pyflightstream.__version__,
            "points": [{**asdict(entry), "status": str(entry.status)} for entry in points],
        }
        workspace.root.mkdir(parents=True, exist_ok=True)
        plan_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return CampaignPlan(
        campaign=campaign.name, fs_version=canonical, points=points, plan_file=plan_file
    )


def _plan_case_error(
    case: SimCase,
    workspace: CampaignWorkspace,
    recipes: dict[str, ScriptRecipe] | None,
) -> str | None:
    """Return what blocks a whole case (recipe or geometry), or None."""
    try:
        if not (recipes and case.recipe in recipes):
            resolve_recipe(case.recipe)
    except ValueError as error:
        return str(error)
    if case.geometry is not None and not Path(case.geometry).is_file():
        return (
            f"geometry file {case.geometry} does not exist; the campaign loop "
            "stages it into the managed inputs/ folder before execution, so the "
            "authored path must point at a real file (check the path, or resolve "
            "it from the workspace geometry library)."
        )
    return None


def _plan_point(
    campaign: Campaign,
    case: SimCase,
    point: dict[str, float],
    workspace: CampaignWorkspace,
    recipe: ScriptRecipe | None,
    case_error: str | None,
    recorded: set[str],
) -> PointPlan:
    """Judge one point in dry run: names, script build, manifest state."""
    run_id = _run_id(campaign, case, point)
    base = {"run_id": run_id, "sim_id": case.sim_id, "point": dict(point)}
    if case_error is not None or recipe is None:
        return PointPlan(
            **base,
            script_name=None,
            status=PlanStatus.BLOCKED,
            error=case_error or "recipe resolution failed",
        )
    try:
        stem, outputs = _point_names(campaign, case, point, workspace)
    except NamingTemplateError as error:
        return PointPlan(**base, script_name=None, status=PlanStatus.BLOCKED, error=str(error))
    script_name = f"{stem}.txt"
    point_case = case.model_copy(update={"point": dict(point), "outputs": outputs})
    script = Script(version=campaign.fs_version)
    try:
        recipe(point_case, script)
        script.render()
    except Exception as error:  # recipes are user code; any failure blocks the point
        return PointPlan(
            **base,
            script_name=script_name,
            status=PlanStatus.BLOCKED,
            error=f"{type(error).__name__}: {error}",
        )
    if run_id in recorded:
        return PointPlan(**base, script_name=script_name, status=PlanStatus.ALREADY_RECORDED)
    return PointPlan(**base, script_name=script_name, status=PlanStatus.READY)


def _prepare_case(
    case: SimCase,
    workspace: CampaignWorkspace,
    recipes: dict[str, ScriptRecipe] | None,
) -> tuple[ScriptRecipe | None, str | None, dict[str, str], str | None]:
    """Resolve the recipe and stage the geometry of one case.

    Returns the recipe, a preparation error (which sends every point
    of the case to FAILED_SCRIPT instead of skipping it silently),
    the staged input hashes, and the staged geometry path.
    """
    try:
        if recipes and case.recipe in recipes:
            recipe = recipes[case.recipe]
        else:
            recipe = resolve_recipe(case.recipe)
    except ValueError as error:
        return None, str(error), {}, None
    inputs_sha256: dict[str, str] = {}
    staged_geometry: str | None = None
    if case.geometry is not None:
        try:
            inputs_sha256 = workspace.stage_inputs(case.sim_id, [case.geometry])
        except WorkspaceError as error:
            return recipe, str(error), {}, None
        staged = workspace.sim_dir(case.sim_id) / "inputs" / Path(case.geometry).name
        staged_geometry = str(staged)
    return recipe, None, inputs_sha256, staged_geometry


def _execute_point(
    *,
    campaign: Campaign,
    canonical: str,
    case: SimCase,
    point: dict[str, float],
    run_id: str,
    recipe: ScriptRecipe | None,
    preparation_error: str | None,
    inputs_sha256: dict[str, str],
    staged_geometry: str | None,
    executor: Executor,
    workspace: CampaignWorkspace,
    sim_dir: Path,
    assess: OutcomeAssessor,
) -> RunRecord:
    """Take one point from sweep coordinates to its manifest record."""
    base = {
        "run_id": run_id,
        "sim_id": case.sim_id,
        "point": dict(point),
        "fs_version_requested": canonical,
        "package_version": pyflightstream.__version__,
        "inputs_sha256": inputs_sha256,
        "script_sha256": "",
        "raw_flag": False,
    }
    if preparation_error is not None or recipe is None:
        error = preparation_error or "recipe resolution failed"
        return RunRecord(**base, status=RunStatus.FAILED_SCRIPT, error=error)

    try:
        stem, outputs = _point_names(campaign, case, point, workspace)
    except NamingTemplateError as error:
        return RunRecord(**base, status=RunStatus.FAILED_SCRIPT, error=str(error))
    update: dict[str, object] = {"point": dict(point), "outputs": outputs}
    if staged_geometry is not None:
        update["geometry"] = staged_geometry
    point_case = case.model_copy(update=update)
    script = Script(version=campaign.fs_version)
    try:
        recipe(point_case, script)
    except Exception as error:  # recipes are user code; any failure is a build failure
        return RunRecord(
            **base,
            status=RunStatus.FAILED_SCRIPT,
            error=f"{type(error).__name__}: {error}",
        )
    # Provenance (decision 4 of 2026-07-22): a script built through the
    # curated solver_settings helper carries the snapshot of every
    # solver flag's effective value; record it with the run.
    setup = getattr(script, "solver_setup", None)
    if isinstance(setup, SolverSetup):
        base["solver_setup"] = setup.model_dump(mode="json")
    script_path, script_sha = workspace.write_script(case.sim_id, f"{stem}.txt", script.render())
    base["script_sha256"] = script_sha
    base["raw_flag"] = script.raw_flag

    result = executor.run_script(script_path, working_dir=sim_dir, timeout_s=case.solver.timeout_s)
    if result.failed:
        if result.timed_out:
            error = f"timed out after {result.wall_time_s:.1f} s and was killed"
        else:
            error = result.log_text or result.stderr or f"return code {result.return_code}"
        return RunRecord(
            **base,
            status=RunStatus.FAILED_EXECUTION,
            wall_time_s=result.wall_time_s,
            error=error,
        )

    try:
        collected = workspace.collect_outputs(
            case.sim_id, [sim_dir / name for name in point_case.outputs]
        )
    except WorkspaceError as error:
        return RunRecord(
            **base,
            status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
            wall_time_s=result.wall_time_s,
            error=str(error),
        )

    assessment = assess(point_case, result, sim_dir)
    return RunRecord(
        **base,
        status=assessment.status,
        iterations=assessment.iterations,
        residual=assessment.residual,
        fs_version_reported=assessment.fs_version_reported,
        fs_build=assessment.fs_build,
        wall_time_s=result.wall_time_s,
        outputs=collected,
        error=assessment.error,
    )


class SurfaceMeshExportError(RuntimeError):
    """The pre-processing surface-mesh export did not produce its file.

    Raised by :func:`export_surface_mesh` when the solver run failed
    or finished without writing the requested mesh file; the message
    carries the process outcome and the captured log excerpt, because
    hidden-mode failures are otherwise silent (SRC-003 p.280).
    """


def export_surface_mesh(
    fsm_path: str | Path,
    workdir: str | Path,
    *,
    version: str | FsVersion,
    executor: Executor | None = None,
    fs_exe: str | Path | None = None,
    file_type: str = "OBJ",
    surface: int = -1,
    timeout_s: float | None = 600.0,
) -> Path:
    """Export the simulation surface mesh in a pre-processing solver run.

    Builds and runs the minimal version-validated script (OPEN the
    simulation, EXPORT_SURFACE_MESH, close), so the probe planner's
    geometry gate can test candidate probes against the real body when
    no mesh file exists yet (SRC-003 pp.282, 307-308). When a mesh
    file already exists, skip this and hand it to the gate directly.

    Parameters
    ----------
    fsm_path : str or pathlib.Path
        Input simulation file to open.
    workdir : str or pathlib.Path
        Execution directory; the script, the exported mesh, and any
        hidden-mode log land here.
    version : str or FsVersion
        Target FlightStream version; emission is validated against it.
    executor : Executor, optional
        Executor to run the script with; alternatively give
        ``fs_exe`` to build a :class:`LocalExecutor`.
    fs_exe : str or pathlib.Path, optional
        FlightStream executable path (explicit input, never guessed).
    file_type : str
        Export format token, one of STL, TRI, OBJ (SRC-003 p.307);
        OBJ is the geometry gate default.
    surface : int
        Surface index to export; -1 exports all geometry surfaces.
    timeout_s : float, optional
        Wall-clock limit of the pre-processing run.

    Returns
    -------
    pathlib.Path
        The exported mesh file.

    Raises
    ------
    ExecutorConfigurationError
        If neither executor nor a valid ``fs_exe`` is given.
    SurfaceMeshExportError
        If the run fails or leaves no mesh file behind.
    """
    if executor is None:
        if fs_exe is None:
            raise ExecutorConfigurationError(
                "export_surface_mesh needs a way to run FlightStream: pass an "
                "executor or the explicit fs_exe path"
            )
        executor = LocalExecutor(fs_exe)
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    mesh_path = workdir / f"surface_mesh.{file_type.lower()}"

    script = Script(version)
    script.emit("OPEN", str(Path(fsm_path)))
    script.emit("EXPORT_SURFACE_MESH", file_type, surface, str(mesh_path))
    script.emit("CLOSE_FLIGHTSTREAM")
    script_path = workdir / "export_surface_mesh.txt"
    script_path.write_text(script.render(), encoding="utf-8")

    result = executor.run_script(script_path, working_dir=workdir, timeout_s=timeout_s)
    if result.failed or not mesh_path.is_file():
        outcome = "timed out" if result.timed_out else f"returned {result.return_code}"
        log_excerpt = (result.log_text or "")[-2000:]
        raise SurfaceMeshExportError(
            f"the pre-processing run {outcome} and the mesh file "
            f"{mesh_path.name} {'exists' if mesh_path.is_file() else 'was not written'}; "
            f"check the simulation file and the log excerpt: {log_excerpt!r}"
        )
    return mesh_path
