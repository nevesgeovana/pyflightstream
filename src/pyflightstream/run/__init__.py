"""Execution of FlightStream and the campaign loop.

Pipeline role: runs the solver headless on rendered scripts and lands
every campaign point in the manifest with exactly one terminal status.
:func:`run_campaign` composes an :class:`Executor` with the managed
workspace of :mod:`pyflightstream.files`; there is no code path from
"point started" to "loop continued" that does not write a status, so
silent skips are structurally impossible (PP-5, FR-14). Failures
accumulate into :class:`CampaignErrors`, raised after the loop.

The local mechanism is the documented command-line script execution:
``FlightStream.exe --script <file>`` (SRC-003 p.279), with the
``-hidden`` flag for windowless batch runs; in hidden mode an
abnormal termination writes ``FlightStreamLog.txt`` into the command
execution directory, which is why the executor runs the solver inside
the simulation folder and captures that file (SRC-003 p.280). An HPC
executor with the same interface is deferred (FR-15).

Judging solver quality (converged, iteration limited, diverged) needs
the solver outputs, so :func:`run_campaign` takes an
:class:`OutcomeAssessor`; the standard implementation arrives with the
results parsers, the next step of milestone M2.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pyflightstream
from pyflightstream.cases import Campaign, ScriptRecipe, SimCase, point_tag, resolve_recipe
from pyflightstream.files import CampaignWorkspace, RunRecord, RunStatus, WorkspaceError
from pyflightstream.script import Script
from pyflightstream.versions import resolve

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
    """

    status: RunStatus
    iterations: int | None = None
    residual: float | None = None
    error: str | None = None


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
        and the manifest. Re-running into the same root fails on the
        duplicate ``run_id``; archive the sims or choose a new root.
    assess : OutcomeAssessor
        Solver-quality judgment; required because the loop refuses to
        invent convergence evidence it cannot see.
    recipes : dict of str to ScriptRecipe, optional
        Named recipe registry consulted before treating
        :attr:`SimCase.recipe` as a ``module:function`` reference;
        the legacy matrix reader will register its recipe names here.

    Returns
    -------
    list of RunRecord
        All records of this run, in execution order.

    Raises
    ------
    CampaignErrors
        After the loop, when at least one point failed.
    """
    canonical = resolve(campaign.fs_version).canonical
    records: list[RunRecord] = []
    failures: list[RunRecord] = []
    for case in campaign.sims:
        sim_dir = workspace.create_sim(case.sim_id)
        recipe, preparation_error, inputs_sha256, staged_geometry = _prepare_case(
            case, workspace, recipes
        )
        for point in case.sweep.points():
            record = _execute_point(
                campaign=campaign,
                canonical=canonical,
                case=case,
                point=point,
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
            records.append(record)
            if record.status.startswith("FAILED"):
                failures.append(record)
    if failures:
        raise CampaignErrors(failures)
    return records


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
    tag = point_tag(point)
    base = {
        "run_id": f"{campaign.name}/sim_{case.sim_id}/{tag}",
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

    update: dict[str, object] = {"point": dict(point)}
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
    script_path, script_sha = workspace.write_script(case.sim_id, f"{tag}.txt", script.render())
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
            case.sim_id, [sim_dir / name for name in case.outputs]
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
        wall_time_s=result.wall_time_s,
        outputs=collected,
        error=assessment.error,
    )
