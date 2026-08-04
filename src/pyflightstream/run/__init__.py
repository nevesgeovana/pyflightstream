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

Afterwards, :func:`reconstruct` reads one manifest record back into the
invocation that produced it: the command line, the working directory,
the effective timeout and the script text, with a per-artifact verdict
on whether each file still hashes to what the record says. That is the
collectable half of NFR-07's promise, and :func:`package_vcs_state`
supplies the other end of it, recording which commit of this package
ran.
"""

from __future__ import annotations

import enum
import hashlib
import inspect
import json
import math
import re
import shutil
import subprocess
import tempfile
import time
import warnings
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import pyflightstream
from pyflightstream._errors import PyflightstreamError
from pyflightstream.cases import (
    Campaign,
    ScriptRecipe,
    SimCase,
    check_recipe,
    point_tag,
    resolve_recipe,
)
from pyflightstream.results import (
    SOLVER_MODES,
    IncompleteOutputError,
    LoadsReport,
    VersionMismatchWarning,
    classify_solver_mode,
    parse_loads,
    parse_residual_history,
)
from pyflightstream.results.conditions import ConditionBinding, bind_conditions
from pyflightstream.script import Script
from pyflightstream.versions import FsVersion, resolve
from pyflightstream.workspace import (
    MANIFEST_SCHEMA,
    CampaignWorkspace,
    NamingTemplateError,
    RunRecord,
    RunStatus,
    WorkspaceError,
    _sha256,
    collection_name,
)

__all__ = [
    "Assessment",
    "CampaignErrors",
    "CampaignPlan",
    "ExecutionResult",
    "Executor",
    "ExecutorConfigurationError",
    "LoadsAssessor",
    "LocalExecutor",
    "OutcomeAssessor",
    "PlanStatus",
    "PointPlan",
    "Reconstruction",
    "SurfaceMeshExportError",
    "check_solver_identity",
    "export_surface_mesh",
    "package_vcs_state",
    "plan_campaign",
    "reconstruct",
    "run_campaign",
]

_LOG_NAME = "FlightStreamLog.txt"


class ExecutorConfigurationError(PyflightstreamError, ValueError):
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
    argv : tuple of str
        The exact command line the executor ran, argument by argument.
        Empty for an executor that does not report one; recorded so a
        run can be reproduced without re-deriving the flags from the
        executor's code (PYFS-015).
    cwd : str, optional
        Working directory the process ran in.
    timeout_s : float, optional
        The wall-clock limit actually applied, which is the case's
        limit resolved rather than the default a reader would assume.
    """

    return_code: int | None
    wall_time_s: float
    timed_out: bool
    log_text: str | None
    stdout: str
    stderr: str
    argv: tuple[str, ...] = ()
    cwd: str | None = None
    timeout_s: float | None = None

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
        invocation = {
            "argv": tuple(argv),
            "cwd": str(working_dir),
            "timeout_s": timeout_s,
        }
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
            **invocation,
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
    conditions : list of dict, optional
        The operating-point binding, one entry per requested axis the
        export prints back: ``axis``, ``requested``, ``reported``,
        ``deviation``, ``tolerance``, ``unit`` and ``within``
        (REV010-001). Empty when the assessor had no case to compare
        against; ``None`` when the assessor does not perform the
        comparison at all. Recorded on EVERY outcome rather than only
        on a refusal, because "checked and agreed" and "never checked"
        are different claims about a result and a later reader cannot
        otherwise tell them apart.
    """

    status: RunStatus
    iterations: int | None = None
    residual: float | None = None
    error: str | None = None
    fs_version_reported: str | None = None
    fs_build: str | None = None
    conditions: list[dict] | None = None


def _bind_case_conditions(case: SimCase | None, report: LoadsReport) -> ConditionBinding:
    """Compare the point a case requested against the one an export printed.

    Parameters
    ----------
    case : SimCase or None
        The requested point. None means there is nothing to compare
        against, which the campaign loop never produces: it fills
        :attr:`SimCase.point` before the assessor runs. It reaches here
        only when :class:`LoadsAssessor` is called directly on a file,
        and the empty binding that results is recorded as empty rather
        than as agreement.
    report : LoadsReport
        The parsed export.

    Returns
    -------
    ConditionBinding
        Every comparable field with its deviation and decision.
    """
    if case is None:
        return ConditionBinding()
    requested: dict[str, float] = {
        axis: value for axis, value in case.point.items() if value is not None
    }
    # The free-stream velocity is a case attribute rather than a sweep
    # axis unless the campaign sweeps it, in which case `point` already
    # carries it and must win: it is the value of THIS point, while the
    # attribute is the case default.
    if case.velocity is not None:
        requested.setdefault("velocity", case.velocity)
    return bind_conditions(requested, reported=report)


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


def _read_loads(path: Path, requested_version: str | FsVersion | None):
    """Parse one collected file as a loads table, or say why not."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        return parse_loads(text, requested_version=requested_version), None
    except (OSError, IncompleteOutputError, ValueError) as error:
        return None, str(error)


class LoadsAssessor:
    """The standard solver-quality judgment, built on the run outputs.

    Reads the collected loads spreadsheet and, when available, the
    exported solver log. It produces four of the six terminal statuses:
    CONVERGED, COMPLETED_MAX_ITER and FAILED_DIVERGED when it can judge
    the run, and FAILED_INCOMPLETE_OUTPUT when it cannot. The Notes
    below list every case in the last group and say why they share one
    status.

    - NaN or infinite Total coefficients: FAILED_DIVERGED.
    - With a log: the final velocity and pressure residuals against
      the run's convergence limit (SRC-003 p.200). A NaN or infinite
      residual in EITHER column is a divergence, judged before the two
      are combined: reducing them first cannot preserve the invalidity
      of one of them.
    - Without a log, steady mode: an iteration counter below the
      requested limit means the threshold stopped the solver
      (CONVERGED); reaching the limit means COMPLETED_MAX_ITER. Unless
      the run forced all iterations, which disables that threshold: an
      early stop is then a refusal, because the one mechanism that
      could have ended the loop legitimately was off (PYFS-008).
    - Without a log, unsteady mode: the time loop always runs to its
      prescribed end, so completion is recorded as
      COMPLETED_MAX_ITER; declare the log export to get a residual
      judgment.

    Parameters
    ----------
    loads_file : str, optional
        Name of the loads spreadsheet among the collected outputs, by
        file name (any directory part of the declared name is dropped
        by collection). None, the default, finds the collected output
        that parses as a loads table, the same rule
        :func:`pyflightstream.results.tables.parse_run_loads` uses on the
        manifest: a swept case names its outputs per point
        (``loads_{point}.txt``), so no single literal could name them
        all, and the content is what identifies the file anyway.
    log_file : str, optional
        Name of the exported solver log (EXPORT_LOG), when the recipe
        declares one; enables the residual-based judgment.
    requested_version : str or FsVersion, optional
        Version the campaign requested; enables the FR-18 cross-check
        against the version printed in the loads footer.

    Notes
    -----
    Every refusal carries ``FAILED_INCOMPLETE_OUTPUT``, and that is a
    constrained choice rather than the right name for each of them. The
    terminal set is closed at six values, and the author resolved on
    2026-08-03 that it stays closed: FR-46 holds and FR-37 closes as
    covered, so there is no seventh value meaning "the solver ran and
    this package cannot judge the result".

    The reason this one is chosen is asymmetric rather than aesthetic.
    Every other available status describes an outcome the solver
    reached, so any of them would make a point nobody judged
    indistinguishable from a point that passed. Over-reporting
    incompleteness costs a re-run; under-reporting it publishes a
    number.

    Read ``COMPLETED_MAX_ITER`` with the same care. It is not a success
    value here: it says the solver reached its iteration cap, which is
    one of the two ways of not converging. The other, a non-finite
    residual, is ``FAILED_DIVERGED``. ``CONVERGED`` is the only status
    this assessor gives to a run that met its threshold.

    The refusals, in the order they are tested:

    1. The file named by ``loads_file`` is not among the collected
       outputs. The error lists what was collected, because the usual
       cause is a swept case whose recipe names its outputs per point.
    2. No ``loads_file`` was named and no single collected output reads
       as a loads table, either because none parses or because several
       do. Choosing one would be a guess about which point ran.
    3. The loads spreadsheet is unparseable or truncated.
    4. The export is evidence of a different operating point from the
       one the case requested, beyond tolerance (REV010-001).
    5. The loads footer prints a solver mode this package has not been
       taught (REV010-002).
    6. The file named by ``log_file`` is not among the collected
       outputs.
    7. The solver log is present but no residual history can be read
       from it.
    8. Steady mode with all iterations forced, and the solver stopped
       early (PYFS-008), as described above.

    Items 4 and 5 are new at v0.4.0 and both replace a path that used
    to end in a SUCCESS, which is what makes them worth stating here
    rather than only in the changelog. Item 4 ran as CONVERGED on a
    valid export belonging to another case: nothing about such a file
    is malformed, so no parser guard could ever have seen it. Item 5
    fell through to the unsteady branch and returned
    COMPLETED_MAX_ITER with no error, so a mode this package had never
    seen became a successful terminal state.

    Item 4 is also tested BEFORE divergence, deliberately. Divergence
    is a physical outcome, and attributing one to a case that never
    produced the file is a worse error than reporting that the evidence
    could not be matched to the case.
    """

    def __init__(
        self,
        loads_file: str | None = None,
        *,
        log_file: str | None = None,
        requested_version: str | FsVersion | None = None,
    ):
        self.loads_file = loads_file
        self.log_file = log_file
        self.requested_version = requested_version

    def __call__(self, case: SimCase, execution: ExecutionResult, sim_dir: Path) -> Assessment:
        """Judge one executed point from its collected outputs."""
        raw = Path(sim_dir) / "raw"
        collected = sorted(path for path in raw.glob("*") if path.is_file())
        if self.loads_file is not None:
            wanted = Path(self.loads_file).name
            found = [path for path in collected if path.name == wanted]
            if not found:
                return Assessment(
                    status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
                    error=(
                        f"no collected output named {wanted!r} to judge; collected: "
                        f"{', '.join(path.name for path in collected) or 'nothing'}. The "
                        "name must match the file the recipe exported, or leave "
                        "LoadsAssessor() unnamed to judge whichever output parses as a "
                        "loads table"
                    ),
                )
            report, error = _read_loads(found[0], self.requested_version)
            if report is None:
                return Assessment(
                    status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
                    error=f"loads spreadsheet {wanted!r} unusable: {error}",
                )
        else:
            usable = [
                (path, report)
                for path, (report, _) in (
                    (path, _read_loads(path, self.requested_version)) for path in collected
                )
                if report
            ]
            if len(usable) != 1:
                names = ", ".join(path.name for path in collected) or "nothing"
                reason = "none of them parses" if not usable else "several of them parse"
                return Assessment(
                    status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
                    error=(
                        f"no single collected output reads as a loads table ({reason}); "
                        f"collected: {names}. Name the file with "
                        "LoadsAssessor('<name>')"
                    ),
                )
            report = usable[0][1]
        # REV010-001, the check whose absence let a converged result for one
        # flight condition be recorded as the evidence of another. The
        # assessor received `case` and never read it, so a valid, complete,
        # genuinely converged export printing alpha=2 deg was accepted as
        # CONVERGED for a point requesting alpha=0 deg. Nothing about that
        # file is malformed, which is exactly why no parser guard could see
        # it. The tabular layer already had the comparison and the manifest
        # never consults it, so the status was authorized long before
        # anything disagreed.
        #
        # It runs FIRST, before divergence and before the mode, because
        # those two judge a file that is assumed to be this run's evidence.
        # Calling a result diverged when it belongs to another point
        # attributes a physical outcome to a case that never produced it.
        # The binding rides in `stamp` so every outcome below carries it:
        # what was requested, what was printed, by how much they differ, and
        # whether that was accepted (REV010-001's closure asks for the
        # decision to be persisted, not just acted on).
        binding = _bind_case_conditions(case, report)
        stamp = {
            "fs_version_reported": report.fs_version_reported,
            "fs_build": report.fs_build,
            "conditions": binding.as_records(),
        }
        if binding.mismatches:
            return Assessment(
                status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
                iterations=report.current_iteration,
                error=(
                    "the collected export is evidence of a different operating "
                    f"point than this run requested: {binding.describe()}. A loads "
                    "export prints the conditions the solver actually ran, so this "
                    "file is a valid result of another case rather than a bad "
                    "result of this one. Within one simulation folder a later "
                    "sweep point overwrites a same named export, so give each "
                    "point a uniquely named output"
                ),
                **stamp,
            )
        diverged = report.diverged_columns()
        if diverged:
            return Assessment(
                status=RunStatus.FAILED_DIVERGED,
                iterations=report.current_iteration,
                error=f"non-finite Total coefficients: {', '.join(diverged)}",
                **stamp,
            )
        # REV010-002. The mode decides WHICH judgment rule applies, so an
        # unrecognized one is checked before any rule is chosen, including
        # the residual path below. The old code tested for "steady" and let
        # everything else fall through to the unsteady branch, which returns
        # COMPLETED_MAX_ITER with error=None: a solver mode this package has
        # never seen became a successful terminal state, indistinguishable
        # from a genuine unsteady run. Failing closed here is the difference
        # between "we judged this" and "we did not recognize it".
        mode = classify_solver_mode(report.solver_mode)
        if mode is None:
            return Assessment(
                status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
                iterations=report.current_iteration,
                error=(
                    f"the loads footer prints solver mode {report.solver_mode.strip()!r}, "
                    f"which is not one this package knows ({', '.join(SOLVER_MODES)}). The "
                    "mode selects the judgment rule, so an unrecognized one means the "
                    "export cannot be assessed rather than that it completed. Either the "
                    "solver version prints a mode this package has not been taught, or "
                    "the footer is malformed"
                ),
                **stamp,
            )
        log_path = None
        if self.log_file is not None:
            wanted_log = Path(self.log_file).name
            matches = [path for path in collected if path.name == wanted_log]
            if not matches:
                return Assessment(
                    status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
                    error=(
                        f"no collected output named {wanted_log!r} to read residuals "
                        f"from; collected: "
                        f"{', '.join(path.name for path in collected) or 'nothing'}. A "
                        "solver log of a swept case carries the point in its name, so "
                        "name it as the recipe exported it, or drop log_file and accept "
                        "the iteration-count judgment"
                    ),
                    **stamp,
                )
            log_path = matches[0]
        if log_path is not None:
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
            try:
                final = parse_residual_history(log_text)[-1]
            except (IncompleteOutputError, ValueError) as error:
                return Assessment(
                    status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
                    error=f"solver log unusable: {error}",
                    **stamp,
                )
            # PYFS-007. Every component is judged BEFORE they are combined,
            # and that order is the fix rather than a detail of it.
            #
            # This was `max(velocity, pressure)` followed by a NaN test on the
            # result. Python's max returns the first argument when the
            # comparison is False, and every comparison against NaN is False,
            # so max(9.6e-8, nan) is 9.6e-08: a NaN in the SECOND position was
            # swallowed and the test below it never fired. The point was then
            # published CONVERGED, carrying a residual that is not the residual
            # that decided it. The guard only ever worked when the NaN happened
            # to land in the velocity column.
            #
            # Infinity is the same class and was also wrong: inf <= limit is
            # False, so an infinite residual read as COMPLETED_MAX_ITER, which
            # says the solver ran out of iterations. It did not; it diverged.
            #
            # Reducing a set of numbers cannot be trusted to preserve the
            # invalidity of one of them, so validity is established first.
            components = {
                "velocity": final.velocity_residual,
                "pressure": final.pressure_residual,
            }
            nonfinite = [
                f"{name}={value!r}"
                for name, value in components.items()
                if value is None or not math.isfinite(value)
            ]
            if nonfinite:
                return Assessment(
                    status=RunStatus.FAILED_DIVERGED,
                    iterations=final.iteration,
                    error=(
                        "non-finite final residual(s): "
                        f"{', '.join(nonfinite)}. A residual that is NaN or "
                        "infinite is not a small number, so no convergence "
                        "judgment can be made from it; the solver diverged or "
                        "the log is corrupt at that iteration"
                    ),
                    **stamp,
                )
            residual = max(components.values())
            converged = residual <= report.convergence_limit
            return Assessment(
                status=RunStatus.CONVERGED if converged else RunStatus.COMPLETED_MAX_ITER,
                iterations=final.iteration,
                residual=residual,
                **stamp,
            )
        if mode == "steady":
            stopped_early = report.current_iteration < report.requested_iterations
            # PYFS-008. The iteration-count judgment below reads an early stop
            # as "the convergence threshold stopped the solver", and that
            # inference holds only while the threshold is what can stop it.
            # SOLVER_SET_FORCED_ITERATIONS turns the threshold off: the solver
            # is told to run the full budget whatever the residual does. So
            # under forced iterations an early stop means the opposite of
            # convergence, because the one mechanism that could legitimately
            # end the loop early was disabled. The field was parsed
            # (LoadsReport.forced_iterations) and never consulted, so a run
            # that stopped at 312 of a forced 500 was published CONVERGED,
            # indistinguishable from one that met the threshold at 312.
            if stopped_early and report.forced_iterations:
                return Assessment(
                    status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
                    iterations=report.current_iteration,
                    error=(
                        f"the solver stopped at iteration {report.current_iteration} of "
                        f"{report.requested_iterations} with forced iterations enabled, "
                        "so the convergence threshold was not what ended the loop: it "
                        "was disabled. The loads file describes an unfinished solve. "
                        "Export the solver log (EXPORT_LOG) and name it to LoadsAssessor "
                        "for a residual judgment, or find why the solver stopped"
                    ),
                    **stamp,
                )
            # forced_iterations is None when the loads footer does not print
            # the line; the count judgment then stands, because nothing says
            # the threshold was off. Stated rather than left implicit: the
            # falsy branch covers False and None, and they mean different
            # things.
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


class CampaignErrors(PyflightstreamError, RuntimeError):  # noqa: N818 (the SAD Section 7 name)
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


def _file_digest(path: str | Path) -> str | None:
    """Hash a file, or None when it cannot be read.

    None rather than a raise: a missing or unreadable solver executable
    is the executor's problem to report, and a provenance field must
    never be the thing that fails a run.
    """
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(65536), b""):
                digest.update(block)
    except OSError:
        return None
    return digest.hexdigest()


def _recipe_digest(recipe: ScriptRecipe | None) -> str | None:
    """Hash the recipe function's source, or None when not introspectable.

    A recipe is USER CODE resolved by a dotted name, and it can be
    edited between two runs that record the same name. The name says
    which function; this says which version of it (PYFS-015). A lambda,
    a C-implemented callable or a function defined in a REPL has no
    retrievable source, and None there is honest.
    """
    if recipe is None:
        return None
    try:
        source = inspect.getsource(recipe)
    except (OSError, TypeError):
        return None
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Reconstruction:
    """Everything needed to re-run one recorded point (PYFS-015, NFR-07).

    Built by :func:`reconstruct` from a manifest record and the
    workspace it names. Every field is what the run ACTUALLY used, read
    back from the record rather than re-derived from today's code.

    Attributes
    ----------
    argv : tuple of str
        The command line, argument by argument.
    cwd : str
        Working directory the process ran in.
    timeout_s : float or None
        Wall-clock limit that was applied.
    script_text : str
        Text of the generated script, read from the workspace.
    verified : dict of str to str
        One entry per artifact whose recorded hash was checked against
        the file on disk today: the script, each staged input, each
        collected output, and the solver executable. Three values, and
        the third exists because collapsing it into the second was
        wrong: ``"match"``, ``"differs"`` (the file is there and its
        bytes moved, so somebody edited a result), and ``"missing"``
        (the file cannot be read at all, so the evidence is gone and the
        answer is to restore it from ``archive/``). Those are different
        problems with different answers.
    """

    argv: tuple[str, ...]
    cwd: str
    timeout_s: float | None
    script_text: str
    verified: dict[str, str]

    @property
    def faithful(self) -> bool:
        """Whether every checked artifact still matches its recorded hash."""
        return all(state == "match" for state in self.verified.values())


def _record_by_id(workspace: CampaignWorkspace, run_id: str) -> RunRecord:
    """Find one manifest record by its run identity, or refuse by name."""
    records = workspace.read_manifest()
    for record in records:
        if record.run_id == run_id:
            return record
    known = ", ".join(sorted(entry.run_id for entry in records)) or "none"
    raise WorkspaceError(
        f"no run {run_id!r} in the manifest of {workspace.root}. Recorded runs: {known}"
    )


def reconstruct(run: RunRecord | str, *, workspace: CampaignWorkspace) -> Reconstruction:
    """Rebuild one recorded run's invocation from the manifest.

    The promise of NFR-07 is that the record plus the staged inputs
    reproduce the run. Until PYFS-015 the record held neither the
    command line, nor the working directory, nor the effective timeout,
    so "reproduce" meant re-deriving all three from executor code that
    may have changed in between. This reads them back instead.

    Parameters
    ----------
    run : RunRecord or str
        A manifest row, as :meth:`CampaignWorkspace.read_manifest`
        returns it, or the ``run_id`` of one. The id form exists so a
        caller can name the run they mean instead of reaching it by list
        position, which is what a reader of the manifest actually has.
    workspace : CampaignWorkspace
        The workspace the run belongs to. Keyword-only, so this cannot
        be confused with
        :func:`~pyflightstream.results.tables.parse_run_loads`, whose
        two positional arguments are the same pair in the other order.

    Returns
    -------
    Reconstruction
        The invocation, the script text, and a per-artifact verdict on
        whether the files still hash to what the record says.

    Raises
    ------
    WorkspaceError
        If no record carries the given ``run_id``, if the record was
        written under a manifest schema this version does not know, or
        carries no script path, or the script is not where it says.
        Refusing beats reconstructing something that is not the run.
    """
    record = run if isinstance(run, RunRecord) else _record_by_id(workspace, run)
    if record.manifest_schema is None:
        # REV010-014. A row with no schema field predates it, and saying so
        # is different from naming a schema it never claimed. This branch
        # was unreachable while the field defaulted to the current value:
        # the legacy row simply asserted the current layout and walked
        # straight into a reconstruction of fields it does not have.
        raise WorkspaceError(
            f"run {record.run_id!r} carries no manifest schema, so it was written "
            "before the field existed and nothing in the row says which layout it "
            "follows. Reconstructing it would mean assuming the current one. Read "
            "it with the pyflightstream version that wrote it, or migrate the "
            "manifest deliberately."
        )
    if record.manifest_schema != MANIFEST_SCHEMA:
        raise WorkspaceError(
            f"run {record.run_id!r} was written under manifest schema "
            f"{record.manifest_schema!r} and this version knows "
            f"{MANIFEST_SCHEMA!r}. Which fields exist, and what they mean, is "
            "what the schema names; guessing would reconstruct a run that never "
            "happened. Use the pyflightstream version that wrote the manifest."
        )
    sim = workspace.sim_dir(record.sim_id)
    if not record.script_path:
        raise WorkspaceError(
            f"run {record.run_id!r} records no script path, so its script cannot "
            "be found. Records written before v0.4.0 predate the field; the run "
            "is not reconstructable from the manifest alone."
        )
    script = sim / record.script_path
    if not script.is_file():
        raise WorkspaceError(
            f"the script of run {record.run_id!r} is not at {script}. The record "
            "names it, so the simulation folder was archived, cleaned or edited; "
            "restore it before reconstructing."
        )

    def state(path: str | Path, recorded: str) -> str:
        digest = _file_digest(path)
        if digest is None:
            return "missing"
        return "match" if digest == recorded else "differs"

    verified = {record.script_path: state(script, record.script_sha256)}
    for name, digest in record.inputs_sha256.items():
        verified[f"inputs/{name}"] = state(sim / "inputs" / name, digest)
    for name, digest in record.outputs_sha256.items():
        verified[name] = state(sim / name, digest)
    if record.fs_exe and record.fs_exe_sha256:
        verified[record.fs_exe] = state(record.fs_exe, record.fs_exe_sha256)
    return Reconstruction(
        argv=tuple(record.argv),
        cwd=record.cwd or str(sim),
        timeout_s=record.timeout_s,
        script_text=script.read_text(encoding="utf-8"),
        verified=verified,
    )


@lru_cache(maxsize=1)
def package_vcs_state() -> tuple[str | None, bool | None]:
    """Return the commit this package's code came from, and whether it is dirty.

    PYFS-017. ``package_version`` reads the installed distribution's
    metadata, which is a static string in ``pyproject.toml``: at the
    time the review measured it, 28 commits and 85 files past the
    ``v0.3.0`` tag, every run still recorded ``0.3.0``. A campaign run
    from a development tree was therefore indistinguishable, in its own
    manifest, from one run against the release.

    Two of the three clauses that finding asks for are a versioning
    scheme change (a dev version carrying the sha, and a guard refusing
    a final version string off a tag), which is a release-mechanics
    decision for the author and is registered rather than taken. This
    is the third: the manifest says which commit ran and whether the
    tree was clean, which is the part that needs no decision because it
    adds evidence without changing what anything claims.

    Returns
    -------
    tuple of (str or None, bool or None)
        Commit sha and dirty flag, or ``(None, None)`` when the package
        did not come from a git work tree. Both are None together, and
        None means "not knowable here" rather than "clean": a wheel
        install has no repository to ask, and inventing an answer is
        the failure this pair exists to prevent.

    Notes
    -----
    The package directory must be TRACKED, not merely inside a work
    tree. A wheel installed into a virtualenv that happens to sit
    inside the repository is not this repository's code, and reporting
    the repository's HEAD for it would be a confident wrong answer.
    """
    package_dir = Path(pyflightstream.__file__).resolve().parent

    def git(*args: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=package_dir,
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return result.stdout.strip() if result.returncode == 0 else None

    if git("ls-files", "--error-unmatch", "__init__.py") is None:
        return None, None
    commit = git("rev-parse", "HEAD")
    if commit is None:
        return None, None
    status = git("status", "--porcelain")
    return commit, None if status is None else bool(status)


_IDENTITY_MARKER = "PYFS_PREFLIGHT"
_BUILD_LINE = re.compile(r"build\s*#?\s*(?P<build>\d+)", re.IGNORECASE)


def check_solver_identity(
    executor: Executor,
    version: FsVersion,
    workdir: Path,
    *,
    timeout_s: float = 60.0,
) -> None:
    """Refuse before the campaign runs if the wrong solver build is configured.

    The build-time refusal of an ambiguous vendor name settles which
    build a campaign ASKED for; it cannot show which one is installed at
    ``fs_exe``, and the version string the solver prints cannot either,
    because every registered 26.1x prints the same one. This runs the
    cheapest possible script (a PRINT sentinel, a log export, and close)
    and reads the build number out of the exported log, so a campaign
    pointed at the wrong installation stops before its first point
    instead of after its last.

    Layered rather than sole: a mismatch is refused HERE, on positive
    evidence, and every parsed result is still cross-checked against the
    registered build afterwards. So an identity this cannot read
    degrades to the parse-time check rather than to nothing, which is
    why the unreadable case warns instead of refusing. Refusing there
    would make the guard's own failure mode "no campaign runs at all".

    Does nothing at all when the version has no registered build: there
    is nothing to compare, so no solver process is spent.

    Parameters
    ----------
    executor : Executor
        The executor the campaign will use, so the check exercises the
        same executable.
    version : FsVersion
        Version the campaign declares.
    workdir : Path
        Scratch directory for the sentinel script and its log.
    timeout_s : float, keyword-only
        Wall-clock limit for the sentinel run, in seconds.

    Raises
    ------
    ExecutorConfigurationError
        When the exported log names a build that is not the registered
        build of ``version``.

    Warns
    -----
    VersionMismatchWarning
        When the log carries no readable build number, so the installed
        build could be confirmed neither right nor wrong.
    """
    if version.build is None:
        return
    workdir.mkdir(parents=True, exist_ok=True)
    log_path = workdir / "preflight_log.txt"
    if log_path.exists():
        log_path.unlink()
    script = Script(version)
    script.comment("pre-flight: which FlightStream build is actually installed")
    script.emit("PRINT", _IDENTITY_MARKER)
    script.emit("EXPORT_LOG", log_path)
    script.emit("CLOSE_FLIGHTSTREAM")
    script_path = workdir / "preflight.txt"
    script_path.write_text(script.render(), encoding="utf-8")
    executor.run_script(script_path, working_dir=workdir, timeout_s=timeout_s)

    if log_path.exists():
        # Real 26.120 hidden-mode exports carry NUL bytes (RPT-001).
        text = log_path.read_text(encoding="utf-8", errors="replace").replace("\x00", "")
    else:
        text = ""
    found = _BUILD_LINE.search(text)
    if found is None:
        warnings.warn(
            f"the pre-flight could not read a build number from the solver, so the "
            f"installation at the campaign's executable was neither confirmed nor "
            f"refused as {version.canonical} (build #{version.build}). Every parsed "
            "result is still cross-checked against the registered build.",
            VersionMismatchWarning,
            stacklevel=2,
        )
        return
    installed = found.group("build")
    if installed != version.build:
        raise ExecutorConfigurationError(
            f"the executable is FlightStream build #{installed}, but the campaign "
            f"declares {version.canonical}, which is build #{version.build}. Nothing "
            "ran. The printed version string cannot show this, because both builds of "
            "a minor release print the same one, and their records differ; check "
            "fs_exe against the installation folder of the version the campaign names."
        )


def run_campaign(
    campaign: Campaign,
    executor: Executor,
    workspace: CampaignWorkspace,
    *,
    assess: OutcomeAssessor,
    recipes: dict[str, ScriptRecipe] | None = None,
    resume: bool = False,
    preflight: bool = True,
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
        A case with nothing left to run is not prepared at all, so a
        resume that executes nothing also STAGES nothing: skipping is a
        read-only operation on the simulation folder. A case with some
        points recorded and some pending is prepared, and is refused
        when its staged input no longer hashes to what the recorded
        points ran against, because re-staging would retire the evidence
        those records point at.
        With False (the default) a duplicate point raises
        :class:`~pyflightstream.workspace.WorkspaceError` before
        anything executes or is staged, because silently redoing
        recorded evidence would fork the run identity.

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
        On the first already-recorded point when ``resume`` is False;
        or, with ``resume`` True, when a partially recorded case's
        declared input no longer matches the hash its recorded points
        were run against.
    """
    version = resolve(campaign.fs_version)
    canonical = version.canonical
    # The pre-flight is LAZY, fired just before the first point executes
    # rather than here. A campaign with nothing left to run must spend no
    # solver process at all: that is what a resume with nothing pending
    # means, and a test pins it. Firing it here also spent a process
    # before the duplicate-run_id refusal below, which raises without
    # executing anything.
    pending_preflight = [preflight]
    manifest = {record.run_id: record for record in workspace.read_manifest()}
    recorded = set(manifest)
    records: list[RunRecord] = []
    failures: list[RunRecord] = []
    for case in campaign.sims:
        # PYFS-004. Which points of this case still need running is decided
        # BEFORE anything is prepared, because preparation is not read-only:
        # _prepare_case stages the inputs, and staging overwrites the copy in
        # inputs/ that the already-recorded points were run against. Deciding
        # afterwards meant a resume with nothing left to do still replaced the
        # staged file while the manifest kept the OLD hash, so the manifest
        # stopped describing the bytes on disk and nothing reported it. The
        # skip has to happen at the CASE, because that is the level staging
        # works at; skipping per point (which is what the loop below did) is
        # already too late.
        case_points = list(case.sweep.points())
        run_ids = [_run_id(campaign, case, point) for point in case_points]
        already = [run_id for run_id in run_ids if run_id in recorded]
        if already and not resume:
            raise WorkspaceError(
                f"run_id {already[0]!r} is already in the manifest of "
                f"{workspace.root}; re-running a recorded point would fork the "
                "run identity. Pass resume=True to skip recorded points (and "
                "run only the new ones), or archive the simulation / choose a "
                "new campaign root to redo it."
            )
        pending = [
            (point, run_id)
            for point, run_id in zip(case_points, run_ids, strict=True)
            if run_id not in recorded
        ]
        if not pending:
            # Nothing to run, so nothing may be touched. This is the case the
            # review reproduced, and the fix is the whole of it: return without
            # creating the sim directory or staging anything.
            continue
        if already:
            # Partially recorded: some points ran against the inputs staged
            # last time. Re-staging different content would silently retire
            # the evidence behind those records, so the inputs are verified
            # rather than overwritten.
            conflict = _staged_inputs_conflict(campaign, case, workspace, manifest, already)
            if conflict is not None:
                raise WorkspaceError(conflict)
        if pending_preflight[0]:
            # First point that will really run: confirm the installed build
            # before spending the campaign on it. Scratch goes to a temp
            # directory, not the managed workspace, whose layout is checked
            # elsewhere and whose emptiness a no-op resume asserts.
            pending_preflight[0] = False
            preflight_dir = Path(tempfile.mkdtemp(prefix="pyfs-preflight-"))
            try:
                check_solver_identity(executor, version, preflight_dir)
            finally:
                shutil.rmtree(preflight_dir, ignore_errors=True)
        sim_dir = workspace.create_sim(case.sim_id)
        recipe, preparation_error, inputs_sha256, staged_geometry = _prepare_case(
            campaign, case, workspace, recipes
        )
        for point, run_id in pending:
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
    broken_commands : tuple of str
        Commands the point's script emits under an ``allow_broken``
        waiver. Known at plan time, because the dry run builds the same
        script, and reported here so an operator learns the campaign
        leans on a command a probe measured broken BEFORE spending
        solver time rather than from the manifest afterwards.
    raw : bool
        Whether the point's script used the ``raw()`` escape hatch.
        Same reason.
    """

    run_id: str
    sim_id: str
    point: dict[str, float]
    script_name: str | None
    status: PlanStatus
    error: str | None = None
    broken_commands: tuple[str, ...] = ()
    raw: bool = False


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
        # A point that waives a broken command, or uses the raw escape
        # hatch, plans READY and is otherwise indistinguishable from a
        # clean one. The operator should learn that here rather than
        # from the manifest, after the solver time is spent.
        waiving = [entry for entry in self.points if entry.broken_commands]
        if waiving:
            commands = sorted({name for entry in waiving for name in entry.broken_commands})
            lines.append(
                f"  {len(waiving)} point(s) waive a command recorded broken: {', '.join(commands)}"
            )
        unvalidated = [entry for entry in self.points if entry.raw]
        if unvalidated:
            lines.append(f"  {len(unvalidated)} point(s) use the raw() escape hatch")
        return "\n".join(lines)


def plan_campaign(
    campaign: Campaign,
    workspace: CampaignWorkspace,
    *,
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
        case_error = _plan_case_error(campaign, case, workspace, recipes)
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
    campaign: Campaign,
    case: SimCase,
    workspace: CampaignWorkspace,
    recipes: dict[str, ScriptRecipe] | None,
) -> str | None:
    """Return what blocks a whole case (recipe, outputs, geometry), or None."""
    try:
        if recipes and case.recipe in recipes:
            check_recipe(case.recipe, recipes[case.recipe])
        else:
            resolve_recipe(case.recipe)
    except ValueError as error:
        return str(error)
    collision = _output_collision(campaign, case, workspace)
    if collision is not None:
        return collision
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
    # The dry run built the same script the campaign will, so the two
    # provenance flags are already determined here. Reported at plan time
    # rather than only in the manifest: an operator who learns from the
    # manifest that a point leaned on a broken command has already spent
    # the solver time (PYFS-002, and the pre-flight promise of FR-14).
    waived = tuple(use.command for use in script.broken_commands)
    if run_id in recorded:
        return PointPlan(
            **base,
            script_name=script_name,
            status=PlanStatus.ALREADY_RECORDED,
            broken_commands=waived,
            raw=script.raw_flag,
        )
    return PointPlan(
        **base,
        script_name=script_name,
        status=PlanStatus.READY,
        broken_commands=waived,
        raw=script.raw_flag,
    )


def _output_collision(
    campaign: Campaign, case: SimCase, workspace: CampaignWorkspace
) -> str | None:
    """Return why this case's output names collide, or None.

    Every point of a case executes in the same simulation folder and its
    declared outputs are collected into ``raw/`` under the name
    :func:`pyflightstream.workspace.collection_name` gives them, so two
    outputs that collect to one name overwrite each other's evidence
    while the manifest lists the survivor for both (incident
    INC-20260723-2113-pyflightstream). The check renders the names the
    way the loop will, so it judges the actual collision rather than the
    presence of a particular placeholder: any naming template that
    distinguishes the points passes.

    Two collisions exist and this checks both, which it did not
    (PLN-20260802-1904). Collection refuses duplicates WITHIN one
    point's declared set and refuses a name already sitting in ``raw/``
    from an EARLIER point, and only the second was anticipated here.
    Three inputs therefore planned as READY and died at collection,
    each after the solver had run and each costing a licensed seat:

    * ``["loads.txt", "loads.txt"]`` on a single point, because the
      old check skipped a repeat carrying the same point tag as itself;
    * ``["a/loads.txt", "b/loads.txt"]`` on one point, because it keyed
      on the DECLARED string, where those differ, while collection keys
      on the base name, where they do not;
    * the same two names across two points of one case.

    The keying is now the shared function, so the plan-time answer and
    the collect-time answer cannot disagree again.
    """
    seen: dict[str, str] = {}
    for point in case.sweep.points():
        try:
            _, names = _point_names(campaign, case, point, workspace)
        except NamingTemplateError:
            return None  # the rendering error is reported by the point itself
        tag = point_tag(point)
        within: dict[str, str] = {}
        for declared in names:
            collected = collection_name(declared)
            if collected in within:
                first = within[collected]
                detail = (
                    f"{first!r} and {declared!r}" if first != declared else f"{declared!r}, twice"
                )
                return (
                    f"sim {case.sim_id!r} declares {detail} for point {tag}, and both "
                    f"collect to raw/{collected}: collection moves each output under its "
                    "base name, so the second would overwrite the first and the manifest "
                    "would record one name twice while only the last content survived. "
                    "Declare outputs whose base names differ; a directory part does not "
                    "make them differ, because collection drops it"
                )
            within[collected] = declared
        for collected, declared in within.items():
            if collected in seen:
                return (
                    f"sim {case.sim_id!r} would write {declared!r} for point {tag} and "
                    f"the same collected name raw/{collected} for point {seen[collected]}: "
                    "every point of a case runs in the same folder and its outputs are "
                    "collected under their base names, so the second would overwrite the "
                    "first and the manifest would list one file for both. Name the "
                    "outputs per point, for example 'loads_{point}.txt', and export "
                    "case.outputs[i] from the recipe"
                )
            seen[collected] = tag
    return None


def _staged_inputs_conflict(
    campaign: Campaign,
    case: SimCase,
    workspace: CampaignWorkspace,
    manifest: dict[str, RunRecord],
    already: list[str],
) -> str | None:
    """Refuse a partial resume whose inputs changed since the recorded points.

    Returns the refusal message, or None when resuming is safe.

    Staging is a copy, so on a partial resume the file the new points would
    run against replaces the one the recorded points DID run against. If the
    source changed in between, the campaign would end up with one manifest
    holding two sets of records that used different inputs, distinguishable
    only by a hash the later staging has already overwritten. Comparing
    before staging is what keeps the manifest's ``inputs_sha256`` a fact
    about the run rather than about whatever was last copied (NFR-07).

    A recorded point with no ``inputs_sha256`` (a case with no geometry, or a
    record from a preparation failure) constrains nothing and is skipped.
    """
    if case.geometry is None:
        return None
    origin = Path(case.geometry)
    if not origin.is_file():
        # Absent sources are stage_inputs' refusal to make, with its own
        # message; anticipating it here would report the wrong cause.
        return None
    current = _sha256(origin)
    name = origin.name
    for run_id in already:
        record = manifest.get(run_id)
        if record is None:
            # Recorded during THIS call rather than read from disk: it staged
            # the same inputs by construction, so it constrains nothing.
            # `recorded` grows as points execute while `manifest` is read once,
            # so the two stop being equal and indexing would raise.
            continue
        recorded_hashes = record.inputs_sha256 or {}
        was = recorded_hashes.get(name)
        if was is None or was == current:
            continue
        return (
            f"cannot resume {campaign.name}/sim_{case.sim_id}: its input {name!r} "
            f"has changed since {run_id!r} ran. The manifest records "
            f"{was[:12]}... for that point and {origin} now hashes to "
            f"{current[:12]}.... Resuming would stage the new content over the "
            "copy the recorded points used, leaving one manifest describing two "
            "different sets of inputs. Restore the original input to resume, or "
            "archive the simulation and run it again as new evidence."
        )
    return None


def _prepare_case(
    campaign: Campaign,
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
            # A registered callable skips resolve_recipe, so the protocol
            # check has to happen here too: both routes cross one gate.
            check_recipe(case.recipe, recipe)
        else:
            recipe = resolve_recipe(case.recipe)
    except ValueError as error:
        return None, str(error), {}, None
    collision = _output_collision(campaign, case, workspace)
    if collision is not None:
        return recipe, collision, {}, None
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
    package_commit, package_dirty = package_vcs_state()
    base = {
        "run_id": run_id,
        "sim_id": case.sim_id,
        "point": dict(point),
        "fs_version_requested": canonical,
        "package_version": pyflightstream.__version__,
        "package_commit": package_commit,
        "package_dirty": package_dirty,
        "recipe": case.recipe,
        "recipe_sha256": _recipe_digest(recipe),
        "fs_exe": str(campaign.fs_exe),
        "fs_exe_sha256": _file_digest(campaign.fs_exe),
        "inputs_sha256": inputs_sha256,
        "script_sha256": "",
        "raw_flag": False,
        "broken_commands": [],
        # Stated, not defaulted (REV010-014). The field defaults to None so
        # that a row which never carried it stays honest about that; a row
        # this version writes DOES carry it, and says so here.
        "manifest_schema": MANIFEST_SCHEMA,
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
    setup = script.solver_setup
    if setup is not None:
        base["solver_setup"] = setup.model_dump(mode="json")
    script_path, script_sha = workspace.write_script(case.sim_id, f"{stem}.txt", script.render())
    base["script_sha256"] = script_sha
    base["script_path"] = str(Path(script_path).relative_to(sim_dir).as_posix())
    base["raw_flag"] = script.raw_flag
    # FR-48: a recipe may waive a command the database records broken.
    # The waiver is the recipe's, so the record of it belongs with the
    # run, not with the recipe: this is the only place a reader of the
    # manifest can learn that the numbers below came from a command a
    # probe measured not to work.
    base["broken_commands"] = [use.model_dump(mode="json") for use in script.broken_commands]

    # PYFS-006. Every point of a case runs in the same simulation folder,
    # and collection asks only whether the declared output EXISTS, never
    # whether this run produced it. A file left there by anything else, a
    # point that failed after the solver wrote, a hand copy, an aborted
    # sweep, was collected as this point's evidence and the point was
    # published CONVERGED from a solver that wrote nothing at all. The
    # measurement is in the commit message; the record was
    # indistinguishable from a real one.
    #
    # Refused before the solver runs rather than reconciled afterwards. A
    # baseline hash comparison would also work and is strictly weaker: it
    # cannot tell a rewritten identical file from an untouched one, and it
    # spends solver time before saying so. The script is already written,
    # so the refused point still records the script it would have run.
    stale = [name for name in point_case.outputs if (sim_dir / name).exists()]
    if stale:
        return RunRecord(
            **base,
            status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
            error=(
                f"declared output(s) {', '.join(stale)} already exist in the simulation "
                "folder before this point ran, so collecting them would attribute "
                "somebody else's file to this run. Every point of a case shares the "
                "folder, and collection cannot tell a file this solver wrote from one "
                "that was already there. Archive the simulation (pyfs-workspace "
                "archive) or remove the leftover, then re-run."
            ),
        )

    result = executor.run_script(script_path, working_dir=sim_dir, timeout_s=case.solver.timeout_s)
    # PYFS-015. The invocation is the half of a run that lived only in the
    # executor's code: which flags, which directory, which effective
    # timeout. Reproducing a run from its record used to mean re-deriving
    # all three from a class that may have changed since.
    base["argv"] = list(result.argv)
    base["cwd"] = result.cwd
    base["timeout_s"] = result.timeout_s
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
        # PYFS-006, the other half of "which file is this record about".
        # The refusal above stops a stale file becoming evidence; this
        # states which bytes the evidence WAS, so a file edited or
        # replaced after the run stops matching its own record. inputs
        # have carried this since the first manifest; outputs never did.
        outputs_sha256=workspace.output_digests(case.sim_id, collected),
        # REV010-001. The decision is persisted, not just acted on: a later
        # reader of the manifest can see which axes were compared, by how
        # much the export deviated, and what tolerance let it through. A
        # status alone cannot answer "was this result ever bound to the
        # point it claims", and that question is the whole finding.
        conditions=assessment.conditions,
        error=assessment.error,
    )


class SurfaceMeshExportError(PyflightstreamError, RuntimeError):
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
