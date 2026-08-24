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

Every campaign that records a point also LEAVES ITS TABLE: at the end
of the loop, and before any failure is raised, :func:`run_campaign`
writes the sweep csv into the workspace's ``post/`` folder under
:data:`SWEEP_TABLE_NAME`, one line per point with the integrated
forces and with each line stating whether it is a raw integration or a
reduction and over what window (PFS-2014.03). Nobody has to ask for
it, and a campaign whose points all failed still leaves the file,
because the identity rows are the record of what was attempted.

The local mechanism is the documented command-line script execution:
``FlightStream.exe -script <file>``, with the
``-hidden`` flag for windowless batch runs. ONE dash on the script
argument, and the spelling is the module constant
:data:`SCRIPT_ARGUMENT` rather than a literal here: SRC-003
pp.279-280 documents the two-dash form, the 25 series does not accept
it, and one dash is the spelling every registered build accepts
(RPT-023). In hidden mode an
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
import inspect
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
import warnings
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import pyflightstream
from pyflightstream._digest import file_sha256, optional_file_sha256, text_sha256
from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning
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
from pyflightstream.results.tables import sweep_table, write_table
from pyflightstream.script import Script
from pyflightstream.versions import FsVersion, resolve
from pyflightstream.workspace import (
    KNOWN_MANIFEST_SCHEMAS,
    MANIFEST_SCHEMA,
    CampaignWorkspace,
    NamingTemplateError,
    RunRecord,
    RunStatus,
    WorkspaceError,
    collection_name,
)

__all__ = [
    "FS_VERSION_FROM_DEFAULT",
    "FS_VERSION_FROM_ROW",
    "SCRIPT_ARGUMENT",
    "SWEEP_TABLE_NAME",
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
    "SolverBuild",
    "SurfaceMeshExportError",
    "check_solver_identity",
    "describe_invocation",
    "export_surface_mesh",
    "package_vcs_state",
    "plan_campaign",
    "reconstruct",
    "run_campaign",
]

_LOG_NAME = "FlightStreamLog.txt"

#: The two values :attr:`~pyflightstream.workspace.RunRecord.fs_version_source`
#: takes, spelled once here rather than at the branch that chooses between
#: them and again at every assertion about a record (PFS-2009.08.02).
#:
#: ``row`` means the case named its own
#: :attr:`~pyflightstream.cases.SimCase.fs_build`, which in a run matrix is
#: the row's FS_BUILD cell. ``campaign_default`` means it inherited the
#: campaign's single declared installation. Neither is a default the record
#: may be missing: a row written before the field carries None, and None is
#: a third state meaning the question was never recorded.
FS_VERSION_FROM_ROW = "row"
FS_VERSION_FROM_DEFAULT = "campaign_default"


class ExecutorConfigurationError(PyflightstreamError, ValueError):
    """The executor cannot run as configured.

    Raised at construction time, because a missing solver executable
    must surface before a campaign starts, not at its first point.
    The FlightStream path is always explicit input (SAD Section 5):
    nothing is read from environment variables or guessed.
    """


#: How many trailing lines of a captured channel a diagnosis quotes.
#: The last lines are where a solver says why it stopped, and a whole
#: log in an exception message is unreadable.
_DIAGNOSIS_LINES = 3


def _last_lines(text: str | None) -> str:
    """Return the last few non-blank lines of a captured channel.

    NUL bytes are stripped: real hidden-mode exports carry them
    (RPT-001) and the 25.0 banner embeds one mid-line (RPT-023), where
    a terminal draws it as a space and a reader cannot see it at all.

    Parameters
    ----------
    text : str or None
        A captured channel, possibly empty or absent.

    Returns
    -------
    str
        The trailing lines joined by ``" / "``, or the empty string
        when the channel carried nothing.
    """
    if not text:
        return ""
    lines = [line.strip().replace("\x00", "") for line in text.splitlines()]
    kept = [line for line in lines if line]
    return " / ".join(kept[-_DIAGNOSIS_LINES:])


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

    def diagnosis(self) -> str:
        """Say what happened, from every channel this run captured.

        Single home of the sentence a refusal quotes when a solver run
        goes wrong. Every caller that needs one calls this; none builds
        its own, and a tier 1 AST guard enforces that.

        WHY THIS EXISTS, because the reason is the whole design. Four
        sites independently composed
        ``log_text or stderr or f"return code {return_code}"``, and all
        four omitted the same field: STDOUT, which the executor captures
        on every run and which nothing in the package read. On
        2026-08-09 a build was handed a command-line spelling it does
        not accept; it started, printed its banner, checked out its
        licence successfully, received no script and waited. The harness
        saw a timeout, no exported log and an empty stderr, and told the
        operator that the environment was unusable and that the licence
        checkout was one of three candidate causes, while holding
        unprinted the line saying the checkout had SUCCEEDED. About a
        dozen licensed solver launches went into the licence hypothesis
        (RPT-023, INC-20260809-2230).

        The lesson generalises past that spelling: everything the
        harness reads is written by the solver AFTER it accepts a
        script, so every failure BEFORE that point looks identical.
        Standard output is the only channel that carries pre-script
        evidence, and it is the one the four chains dropped.

        Returns
        -------
        str
            One line naming the outcome, then whichever captured
            channels are non-empty, most specific first. Never empty:
            with nothing captured it still reports the outcome, which
            is more than "return code None" said.
        """
        parts: list[str] = []
        if self.timed_out:
            limit = "" if self.timeout_s is None else f" of {self.timeout_s:g} s"
            parts.append(f"timed out after {self.wall_time_s:.1f} s (limit{limit}) and was killed")
        else:
            parts.append(f"exited with return code {self.return_code}")

        for label, text in (
            ("FlightStreamLog.txt", self.log_text),
            ("stderr", self.stderr),
            ("stdout", self.stdout),
        ):
            tail = _last_lines(text)
            if tail:
                parts.append(f"{label}: {tail}")
        return "; ".join(parts)


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


@dataclass(frozen=True)
class SolverBuild:
    """One solver installation a campaign may send some of its cases to.

    A campaign declares ONE ``fs_version`` and ONE ``fs_exe``, which is
    the right shape for the ordinary case and makes a study ACROSS two
    solver builds unstatable: the run matrix refused a second FS_BUILD
    value outright rather than record a falsehood, because the manifest
    would have said every point ran on the campaign's executable. This
    is the shape that lets a campaign say otherwise, one case at a time,
    through :attr:`pyflightstream.cases.SimCase.fs_build` and the
    ``builds`` mapping of :func:`run_campaign` and :func:`plan_campaign`.

    Every field is stated rather than derived, and that is the point of
    the class. Nothing here infers a command-database version from an
    executable path or from a build id: which version a build's scripts
    are emitted under is a declaration the caller makes, so the manifest
    records what was asked for rather than what was guessed.

    Attributes
    ----------
    fs_exe : pathlib.Path
        The executable of this build, recorded in every point's
        ``fs_exe`` and hashed into ``fs_exe_sha256``.
    fs_version : str
        FlightStream version the scripts of this build are emitted
        under, canonical identifier (26.120) or a vendor release name
        that resolves to exactly one registered build. Recorded in
        ``fs_version_requested``.
    executor : Executor
        How to run this build's scripts; one per build, because an
        executor is bound to an executable at construction.
    """

    fs_exe: Path
    fs_version: str
    executor: Executor


#: Command-line argument that names the script file, one dash.
#:
#: Read this together with :func:`describe_invocation`, which is what
#: every report prints; the two must not be restated apart.
#:
#: The vendor spells this argument two ways and the difference is not
#: cosmetic. The 25.0 edition documents ``-script`` on its command-line
#: inputs topic and the 26.12 edition documents ``--script`` at SRC-003
#: pp.279-280. Note the asymmetry in what can be CITED: the 26.12
#: edition has a source id and a page, and the 25.0 edition has neither,
#: because that install ships a compiled help archive with topics rather
#: than pages and no source id has been allocated for it
#: (PLN-20260809-2350). So the spelling used here rests on the
#: measurement, RPT-023, and not on a page reference.
#:
#: A build that does not recognise the
#: spelling it is given does not refuse it, it starts, checks out its
#: licence, receives no script, and waits for a user. Under ``-hidden``
#: with the standard streams redirected there is no console for it to
#: report on, so the Fortran runtime raises severe(30) on ``CONOUT$``
#: and opens a modal dialog that no timeout can answer. That is a hang
#: with a clean licence checkout and an empty log, which is how it was
#: misread for a day as a licence-seat problem.
#:
#: One dash is used for every build because it is the only spelling
#: measured to work on all of them: the seven registered builds were
#: swept with both spellings on 2026-08-09 and two dashes failed on
#: 25.000 and 25.100 (RPT-023). A future build that drops the one-dash
#: spelling fails its probe baseline loudly rather than silently, since
#: the baseline asserts the sentinel reached the exported log.
SCRIPT_ARGUMENT = "-script"


def describe_invocation(*, hidden: bool = True, markdown: bool = False) -> str:
    """Return the one-line description of the solver invocation.

    Single home of the sentence every report prints about how the
    solver was called, so the script argument it names is the one
    :func:`LocalExecutor._argv` passes rather than a copy of it. Six
    copies of that sentence used to sit in the report writers, where
    nothing would have noticed them disagreeing with the code (NFR-11).

    What it derives and what it still restates, stated because the
    difference is the residual: the script argument is read from
    :data:`SCRIPT_ARGUMENT`, while the executor's class name and the
    windowless flag are described rather than read from an executor.
    Both are true of every report this package can currently write, the
    QA layer building a default :class:`LocalExecutor` at each of its
    three entry points, and both would become wrong the day an HPC
    executor lands (FR-15) or a report is written from a visible run.
    Taking the executor as an argument is registered as
    PLN-20260809-2340.

    Parameters
    ----------
    hidden : bool
        Whether the description covers a windowless run. Keyword-only:
        two adjacent booleans read as nothing at a call site, and this
        value is written verbatim into committed evidence.
    markdown : bool
        Wrap the flags in a markdown code span, for the rendered table
        of a report; the machine-readable field takes them plain. Named
        for the output format rather than for the span, ``code`` being
        ambiguous next to :attr:`ExecutionResult.return_code`.

    Returns
    -------
    str
        Description naming the executor class and its flags, for the
        ``executor`` field of a compat, drift, or physics report.
    """
    flags = f"-hidden {SCRIPT_ARGUMENT}" if hidden else SCRIPT_ARGUMENT
    if markdown:
        flags = f"`{flags}`"
    # The two citations are split because they answer different halves
    # and one of them does NOT support the spelling beside it: SRC-003
    # documents the mechanism and the windowless flag, and documents the
    # script argument with TWO dashes. Printing that page beside one
    # dash, as this string did when it was first written, cites a page
    # for a claim it denies. RPT-023 is what carries the spelling.
    return f"LocalExecutor, {flags} (mechanism SRC-003 pp.279-280; argument spelling RPT-023)"


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
        # THE PATH AS THE CALLER SPELLED IT, deliberately, and this line
        # was `str(Path(script_path).resolve())` for one commit. The
        # argument for resolving here was that every caller passes
        # through this one place; the argument against is that CI made
        # visible and this machine could not. `Path("C:/runs/point.txt")`
        # is absolute on Windows and RELATIVE on Linux, so resolving
        # rewrote it against the working directory there and broke the
        # documented headless mechanism on half the platforms.
        #
        # It was also redundant. Every caller that hands the solver a
        # path resolves its own directory first: the campaign inherits an
        # absolute root from CampaignWorkspace, and `export_surface_mesh`
        # and `check_solver_identity` each resolve the `workdir` their
        # script path is built from. What a RELATIVE path means here is
        # the caller's business, and it means what it always meant: the
        # solver resolves it from its own working directory.
        argv.extend([SCRIPT_ARGUMENT, str(script_path)])
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
                # EXPLICIT and IDENTICAL to what an omitted env= would give.
                # This is not a behaviour change and is not meant to be one:
                # the solver needs the ambient environment (its licence server
                # address and its own installation variables live there), so
                # the inheritance is correct and the point is that it is now a
                # DECISION at this call rather than a default nobody chose.
                # A future change that narrows it belongs here, where the
                # solver's requirements are known, and not in a caller.
                env=os.environ.copy(),
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

    Notes
    -----
    WHICH SUPPLIED VELOCITY WINS, stated here because this is the one
    function that applies the rule and it was previously written nowhere
    (OPS-2009.01.04). Free-stream velocity can arrive from two places at
    once and the order is:

    1. ``case.point["velocity"]``, the value of THIS point, wins;
    2. :attr:`~pyflightstream.cases.SimCase.velocity`, the case default,
       fills in when the point supplies none;
    3. neither: nothing is requested, which is not the same as zero, and
       the binding records the axis as unasked rather than as agreed.

    ``setdefault`` is what encodes 1 over 2. A plain assignment reads
    identically at the call site and reverses the order, and nothing
    else in the package would notice: the campaign would run at one
    speed and the record would claim another.

    TWO SUPPLY POINTS ARE DELIBERATELY OUTSIDE THIS RULE. A sweep cannot
    emit a velocity at all today: :meth:`SweepAxis.points` yields alpha,
    beta and advance_ratio only, so step 1 is reachable only by a caller
    that fills ``point`` itself, and a test pins that reading rather
    than presenting the branch as campaign-reachable. And
    :attr:`~pyflightstream.cases.ReferenceData.velocity` is the
    COEFFICIENT reference velocity, read by no library code and passed
    to the solver only by a user recipe through
    :func:`pyflightstream.script.helpers.solver_settings`; the library
    holds no precedence over it and states none.
    """
    if case is None:
        return ConditionBinding()
    requested: dict[str, float] = {
        axis: value for axis, value in case.point.items() if value is not None
    }
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
    never be the thing that fails a run. That policy now lives in the
    FUNCTION that implements it, :func:`pyflightstream._digest.
    optional_file_sha256`, rather than in a comment beside a second
    copy of the same chunked read.
    """
    return optional_file_sha256(path)


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
    return text_sha256(source)


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
    if record.manifest_schema not in KNOWN_MANIFEST_SCHEMAS:
        # The set, not the current constant. Reconstruction asks which
        # fields the row has, and every stamp in the set describes a layout
        # THIS version can still read, so refusing an older one would make
        # a schema bump equivalent to deleting the manifests written before
        # it: nothing here migrates a manifest, so there is no route back
        # (PFS-2012.03). A stamp outside the set, older or newer, still
        # denies, which is the half the constant's own comment demands.
        raise WorkspaceError(
            f"run {record.run_id!r} was written under manifest schema "
            f"{record.manifest_schema!r} and this version knows "
            f"{', '.join(KNOWN_MANIFEST_SCHEMAS)}. Which fields exist, and what "
            "they mean, is what the schema names; guessing would reconstruct a run "
            "that never happened. Use the pyflightstream version that wrote the "
            "manifest."
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
                # Explicit, and identical to the inherited default. git needs
                # the ambient environment to find its own installation and the
                # user's configuration, so narrowing it here would change what
                # this function reports rather than harden it.
                env=os.environ.copy(),
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
    # RESOLVED FIRST, and this is the boundary with the worst failure of
    # the four. `log_path` below becomes SCRIPT TEXT, in an EXPORT_LOG,
    # and the solver runs with its working directory set to `workdir`.
    # Spelled relatively, the solver writes the log one level too deep,
    # this function finds no log, reads no build number, and takes the
    # WARN branch instead of raising: a campaign pointed at the wrong
    # installation proceeds, and the warning blames the solver for
    # "could not read a build number" when the cause was our own path.
    # A guard that reads its own missing evidence as permission is not a
    # guard. The same shape was measured against a real 26.120 export in
    # qa.probes, where it failed silently for exactly this reason.
    workdir = Path(workdir).resolve()
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
    result = executor.run_script(script_path, working_dir=workdir, timeout_s=timeout_s)

    if log_path.exists():
        # Real 26.120 hidden-mode exports carry NUL bytes (RPT-001).
        text = log_path.read_text(encoding="utf-8", errors="replace").replace("\x00", "")
    else:
        text = ""
    found = _BUILD_LINE.search(text)
    if found is None:
        # THE CAUSE IS NAMED WHEN IT IS KNOWN. The result of the run was
        # discarded here, so a solver that failed to start, or one killed
        # by the timeout, produced the same sentence as a solver that ran
        # perfectly and printed nothing: "could not read a build number
        # from the solver". That is the misattribution this function's
        # own path fix was about, one line further on, and the timeout
        # case is one the operator can act on by raising timeout_s.
        if result.timed_out:
            cause = (
                f"the pre-flight run was killed by its {timeout_s} second timeout, so "
                "no build number could be read; raise timeout_s if this installation "
                "is simply slow to start"
            )
        elif result.failed:
            cause = (
                f"the pre-flight run exited with return code {result.return_code} and "
                "wrote no readable log, so no build number could be read"
            )
        else:
            cause = "the pre-flight could not read a build number from the solver"
        warnings.warn(
            f"{cause}, so the "
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


def _case_build(
    case: SimCase,
    builds: Mapping[str, SolverBuild] | None,
) -> SolverBuild | None:
    """Return the build a case names, or None for the campaign's own.

    Refuses a case naming a build the caller did not supply, rather
    than falling back to the campaign's executable. The fallback is
    what makes a record lie: the point would run on one installation
    and the manifest would name another, which is the exact failure the
    run matrix's single-build refusal existed to prevent.

    Parameters
    ----------
    case : SimCase
        The case about to be planned or run.
    builds : mapping of str to SolverBuild, optional
        What the caller supplied.

    Returns
    -------
    SolverBuild or None
        None means the campaign's own ``fs_exe`` and ``fs_version``.

    Raises
    ------
    ExecutorConfigurationError
        When the case names a build the mapping does not carry.
    """
    if case.fs_build is None:
        return None
    if builds and case.fs_build in builds:
        return builds[case.fs_build]
    known = ", ".join(sorted(builds)) if builds else "none"
    raise ExecutorConfigurationError(
        f"case {case.sim_id!r} declares fs_build {case.fs_build!r} and the builds "
        f"mapping carries {known}. Nothing ran. A case naming a build is asking to "
        "run on a DIFFERENT installation from the campaign's, so falling back to "
        "campaign.fs_exe would record every point against an executable it never "
        "used. Pass builds={<id>: SolverBuild(fs_exe=..., fs_version=..., "
        "executor=...)} covering every fs_build the campaign names, or clear the "
        "field to run the case on the campaign's own installation."
    )


def _build_groups(campaign: Campaign) -> dict[str, list[str]]:
    """Group a campaign's cases by the installation each one runs on.

    The key is :attr:`~pyflightstream.cases.SimCase.fs_build`, verbatim
    and in first-appearance order, with the EMPTY STRING standing for
    the campaign's own installation. The empty key is the same one the
    campaign loop already uses internally to key its pre-flight, so the
    grouping a reader sees and the grouping the loop spends are one
    thing rather than two that can disagree.

    Parameters
    ----------
    campaign : Campaign
        What is about to be planned or run.

    Returns
    -------
    dict of str to list of str
        Build id to the ``sim_id`` values naming it, in the order the
        campaign declares them.
    """
    groups: dict[str, list[str]] = {}
    for case in campaign.sims:
        groups.setdefault(case.fs_build or "", []).append(case.sim_id)
    return groups


def _build_label(key: str) -> str:
    """Name one grouping key the way a message should say it."""
    return f"build {key!r}" if key else "the campaign's own installation"


def _check_scheduled_builds(
    campaign: Campaign,
    executor: Executor,
    scheduled: list[tuple[SimCase, SolverBuild | None]],
) -> None:
    """Confirm every installation that still has work, before any of it runs.

    ONE CHECK PER BUILD, and ALL OF THEM before the first point of ANY
    build executes. The check used to fire at the first point of each
    build in turn, which is one process per installation and correct
    about cost, but it meant a campaign whose SECOND build is
    misconfigured ran every point of the first one and refused
    afterwards. Those licensed seats are gone by the time the message
    arrives, and saving them is the whole reason a pre-flight exists
    (PFS-2009.09.02).

    THE LAZINESS IS KEPT, which is the constraint that makes this
    subtle. Only builds with points still PENDING are asked, so a resume
    with nothing left to do still launches no solver process at all, and
    a build all of whose points are recorded is not probed either. The
    naive fix, probing every declared build up front, closes one spend
    by opening another in exactly the case that spends nothing today.

    Parameters
    ----------
    campaign : Campaign
        The campaign being run; its own version answers for cases
        naming no build.
    executor : Executor
        The campaign's own executor, likewise.
    scheduled : list of (SimCase, SolverBuild or None)
        The cases that have at least one point left to run, paired with
        the build each resolved to.

    Raises
    ------
    ExecutorConfigurationError
        When any installation reports a build other than the one the
        campaign asked for. ONE refusal naming every failing build and
        the cases that asked for it, rather than the first one found.
    """
    groups: dict[str, tuple[Executor, str, list[str]]] = {}
    for case, build in scheduled:
        key = case.fs_build or ""
        if key not in groups:
            groups[key] = (
                build.executor if build is not None else executor,
                build.fs_version if build is not None else campaign.fs_version,
                [],
            )
        groups[key][2].append(case.sim_id)
    failures: list[str] = []
    for key, (case_executor, case_version, sims) in groups.items():
        workdir = Path(tempfile.mkdtemp(prefix="pyfs-preflight-"))
        try:
            check_solver_identity(case_executor, resolve(case_version), workdir)
        except ExecutorConfigurationError as error:
            failures.append(
                f"  {_build_label(key)}, asked for by case(s) {', '.join(sims)}: {error}"
            )
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
    if failures:
        raise ExecutorConfigurationError(
            f"the identity pre-flight refused {len(failures)} of {len(groups)} solver "
            "installation(s) this campaign still has work for. NOTHING ran and no "
            "point was recorded:\n" + "\n".join(failures) + "\nEvery installation with "
            "work left is confirmed before the first point of ANY of them executes, so "
            "a misconfigured build cannot spend the licensed seats of a healthy one "
            "first. Fix the executable each case above points at, or drop those cases "
            "from this run."
        )


#: Name of the sweep csv :func:`run_campaign` leaves under the
#: workspace's ``post/`` folder at the end of every campaign, spelled
#: once here rather than at the write and again at every assertion
#: about it (PFS-2014.03).
#:
#: WHY THIS NAME, since the item asks the choice to be justified rather
#: than merely made. Three things had to be true of it.
#:
#: It says WHOSE table it is. The file covers the whole CAMPAIGN, one
#: line per recorded point, because :func:`~pyflightstream.results.
#: tables.sweep_table` reads the manifest and not the records of the
#: call that happened to write it. So a resumed campaign rewrites one
#: file that describes everything recorded so far, rather than leaving a
#: per-call fragment nobody can join. A timestamped or per-call name
#: would accumulate files of which none is "the" table.
#:
#: It says what is INSIDE: a sweep table, the tabular layer's own word
#: for one row per point, which is what a reader opens it expecting.
#:
#: And it does not collide with ``sweep.csv``, the default target of
#: ``pyfs-matrix run --sweep-csv``, which the operator names and which
#: lands in the campaign ROOT. The two files would hold the same table,
#: so a collision would corrupt nothing; what it would cost is a reader
#: who cannot tell which file the tool maintains and which one a
#: colleague put there.
SWEEP_TABLE_NAME = "campaign_sweep.csv"


def _leave_sweep_table(workspace: CampaignWorkspace) -> str | None:
    """Write the campaign's sweep table under ``post/``, never raising.

    PFS-2014.03. A completed sweep leaves its csv WITHOUT ANYONE ASKING
    FOR IT: until this existed, only ``pyfs-matrix run`` wrote one, so a
    campaign driven from Python left every number it produced inside the
    manifest and the raw exports, and a colleague opening the workspace
    found no table at all.

    ``require_loads=False`` is the keyword written for exactly this
    call: a campaign whose every point failed still has identity rows,
    and raising there would leave nothing to write in the one case the
    file is most wanted. :func:`~pyflightstream.results.tables.
    write_table` is the tabular layer's single write path and refuses a
    frame that cannot say what produced its numbers, so each row states
    whether it is a raw integration or a reduction and over what window.

    Overwriting is deliberate and is not the silent-overwrite class
    (PFS-2011.02): every value in this file is derived from the
    manifest, which is append-only, so rewriting it after a resume adds
    the new points and can destroy nothing. The flow-visualization
    writers refuse an existing destination because their content is NOT
    reconstructable; this content is.

    Parameters
    ----------
    workspace : CampaignWorkspace
        The managed campaign root whose manifest is tabulated and under
        whose ``post/`` folder the file lands.

    Returns
    -------
    str or None
        None when the table was written. Otherwise the sentence saying
        why it was not, for the caller to warn with.

    Notes
    -----
    WHY THIS CATCHES ``Exception`` AND RETURNS INSTEAD OF RAISING. The
    table is a side product written after all the expensive work is
    done: the solver seats are spent, every point is in the manifest,
    and the caller is owed either its records or the
    :class:`CampaignErrors` naming the points that failed. Letting a
    write error out of here would replace that outcome with a report
    about a csv, which is the worse of the two failures by a long way,
    and would do it precisely on the failing campaigns whose table this
    item exists to leave. The narrow ``except`` clause the
    ``pyfs-matrix`` writer uses is right THERE, where the write is the
    last thing the process does; here an unforeseen error (a manifest
    row the tabular layer cannot widen, a pandas type error) would cost
    the campaign's own result, so the clause is deliberately total.
    ``BaseException`` is NOT caught: a ``KeyboardInterrupt`` means the
    operator asked for the process to stop.
    """
    target = Path(workspace.root) / "post" / SWEEP_TABLE_NAME
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        write_table(sweep_table(workspace, require_loads=False), target)
    except Exception as error:
        return (
            f"the campaign ran and its sweep table was NOT written to {target}: "
            f"{type(error).__name__}: {error}. No run outcome is affected and nothing "
            f"is lost: every point is recorded in {workspace.manifest_path}. Fix the "
            "cause (an unwritable post/ folder, a full disk, or a manifest row the "
            "tabular layer cannot widen) and rebuild the file with "
            "pyflightstream.results.sweep_table(CampaignWorkspace(root))."
        )
    return None


def run_campaign(
    campaign: Campaign,
    executor: Executor,
    workspace: CampaignWorkspace,
    *,
    assess: OutcomeAssessor,
    recipes: dict[str, ScriptRecipe] | None = None,
    resume: bool = False,
    preflight: bool = True,
    builds: Mapping[str, SolverBuild] | None = None,
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

    Afterwards, and WITHOUT ANYONE ASKING FOR IT, the campaign's sweep
    table is written to ``post/`` under :data:`SWEEP_TABLE_NAME`: one
    line per recorded point, carrying the integrated forces, and each
    line saying whether its numbers are a raw integration or a reduction
    and over what window, so a steady point and an unsteady point's time
    average are never read as one method (PFS-2014.03, PFS-2014.05). It
    is written BEFORE :class:`CampaignErrors` is raised, so a campaign
    with failing points still leaves the table; the failed points are
    the identity rows whose coefficient columns are empty. A campaign
    that recorded nothing at all leaves no file, having nothing to
    tabulate.

    The table is a side product and never costs the campaign its own
    outcome: a write that fails is reported as a
    :class:`~pyflightstream.exceptions.PyflightstreamWarning` naming the
    cause and the rebuild call, and the records (or the
    :class:`CampaignErrors`) are returned exactly as they would have
    been (:func:`_leave_sweep_table`).

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
        (:func:`pyflightstream.run.matrix.run_matrix`) forwards its
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
    builds : mapping of str to SolverBuild, optional
        One entry per solver installation the campaign's cases name in
        :attr:`~pyflightstream.cases.SimCase.fs_build`. A case naming
        none runs on ``executor``, ``campaign.fs_exe`` and
        ``campaign.fs_version``, which is every campaign written before
        v0.8.0 and every single-installation campaign since; a case
        naming one runs on that build's executor and is RECORDED against
        that build's executable, its digest and its version, so a study
        across two builds no longer has to lie about which one produced
        a point. A case naming a build this mapping does not carry is
        refused before anything executes.

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
    ExecutorConfigurationError
        When a case names an ``fs_build`` that ``builds`` does not
        carry; or when the identity pre-flight finds the wrong build
        installed at any installation the campaign still has work for.
        The second is raised ONCE, naming every failing installation and
        the cases that asked for it, before the first point of ANY of
        them executes, so a misconfigured build cannot spend the
        licensed seats of a healthy one first (PFS-2009.09.02).

    Warns
    -----
    PyflightstreamWarning
        When the automatic sweep table could not be written. The runs
        themselves are unaffected and the manifest is complete.
    """
    # EVERY case's build is resolved before the FIRST one runs. Doing it
    # inside the loop looked equivalent and was not: the campaign would run
    # its first cases, then refuse on a later one, leaving a half-recorded
    # manifest for a mistake that was fully knowable before anything
    # started. A missing build is a configuration error, not a run outcome.
    case_builds = [_case_build(case, builds) for case in campaign.sims]
    manifest = {record.run_id: record for record in workspace.read_manifest()}
    recorded = set(manifest)
    records: list[RunRecord] = []
    failures: list[RunRecord] = []
    # PASS ONE decides what is left to run, for every case, and touches
    # nothing. The whole schedule is knowable from the campaign and the
    # manifest, so every refusal that rests on it belongs here rather than
    # halfway through a run that has already spent seats (PFS-2009.09.02).
    scheduled: list[tuple[SimCase, SolverBuild | None, list[tuple[dict[str, float], str]]]] = []
    for case, build in zip(campaign.sims, case_builds, strict=True):
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
        scheduled.append((case, build, pending))
    # PASS TWO asks every installation that still has work which build it
    # is, once each, and refuses the whole campaign if any of them answers
    # wrongly. It is still LAZY: a schedule with nothing in it asks
    # nothing, so a resume with no pending point launches no process.
    if preflight and scheduled:
        _check_scheduled_builds(campaign, executor, [(case, build) for case, build, _ in scheduled])
    # PASS THREE is the only one that stages, executes or records.
    for case, build, pending in scheduled:
        case_executor = build.executor if build is not None else executor
        case_version = build.fs_version if build is not None else campaign.fs_version
        case_exe = build.fs_exe if build is not None else campaign.fs_exe
        # Read off the SAME condition the three lines above read, so the
        # record cannot say one thing while the point runs on another
        # (PFS-2009.08.02).
        case_version_source = FS_VERSION_FROM_ROW if build is not None else FS_VERSION_FROM_DEFAULT
        canonical = resolve(case_version).canonical
        sim_dir = workspace.create_sim(case.sim_id)
        recipe, preparation_error, inputs_sha256, staged_geometry = _prepare_case(
            campaign, case, workspace, recipes
        )
        for point, run_id in pending:
            record = _execute_point(
                campaign=campaign,
                canonical=canonical,
                fs_exe=case_exe,
                fs_version=case_version,
                fs_version_source=case_version_source,
                case=case,
                point=point,
                run_id=run_id,
                recipe=recipe,
                preparation_error=preparation_error,
                inputs_sha256=inputs_sha256,
                staged_geometry=staged_geometry,
                executor=case_executor,
                workspace=workspace,
                sim_dir=sim_dir,
                assess=assess,
            )
            workspace.append_record(record)
            recorded.add(record.run_id)
            records.append(record)
            if record.status.startswith("FAILED"):
                failures.append(record)
    # BEFORE THE RAISE, and that is the whole placement (PFS-2014.03).
    # `CampaignErrors` is raised by a campaign that RAN and had failing
    # points, and those points have records; writing the table after it
    # would mean a sweep with one failed point leaves no table at all,
    # which is this item's acceptance exactly inverted. The same defect
    # was found and fixed one layer up, in `pyfs-matrix run`, where the
    # writer sat under an `except` arm that returned first.
    #
    # `recorded` is the manifest's run ids, so an empty one means nothing
    # anywhere has ever been recorded here: there is no table to leave and
    # no problem to report, and complaining would put a warning on every
    # resume that found its work already done.
    if recorded:
        problem = _leave_sweep_table(workspace)
        if problem is not None:
            # The one residual, stated rather than hidden: under
            # `-W error` this warning is promoted to an exception and
            # propagates in place of the outcome below. That promotion is
            # the caller's explicit request, and the manifest is complete
            # either way; silence would not be.
            warnings.warn(problem, PyflightstreamWarning, stacklevel=2)
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
    build_groups : dict of str to list of str
        Which cases run on which solver installation, keyed by
        :attr:`~pyflightstream.cases.SimCase.fs_build` with the empty
        string standing for the campaign's own. Reported here because
        how many installations a study actually spans is usually a
        surprise, and the pre-flight is the one place it can be learned
        without spending a licensed seat (PFS-2009.09.01).
    """

    campaign: str
    fs_version: str
    points: list[PointPlan] = field(default_factory=list)
    plan_file: Path | None = None
    build_groups: dict[str, list[str]] = field(default_factory=dict)

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
        # The grouping comes FIRST, before any per-point line, because it
        # is the thing an operator has to decide on before starting: one
        # line per installation, whatever the row count.
        if self.build_groups:
            lines.append(f"  {len(self.build_groups)} solver installation(s):")
            for key, sims in self.build_groups.items():
                lines.append(f"    {_build_label(key)}: {len(sims)} case(s) ({', '.join(sims)})")
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
    builds: Mapping[str, SolverBuild] | None = None,
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
    builds : mapping of str to SolverBuild, optional
        As in :func:`run_campaign`, and pre-flighting is where it earns
        its keep: a case sent to a second build has its dry-run script
        validated against THAT build's version, so a command the second
        installation does not carry blocks the point here rather than
        failing after the first one has already run. A case naming a
        build the mapping does not carry is refused, exactly as the
        campaign loop refuses it, so the pre-flight cannot pass a
        configuration the run will reject.

    Returns
    -------
    CampaignPlan
        One :class:`PointPlan` per point; inspect ``blocked`` before
        running, or print ``summary()``.

    Raises
    ------
    ExecutorConfigurationError
        When a case names an ``fs_build`` that ``builds`` does not
        carry.
    """
    canonical = resolve(campaign.fs_version).canonical
    # Before the first folder is allocated, for the reason run_campaign
    # states: a missing build is knowable up front, and discovering it
    # halfway leaves a plan that describes part of a campaign.
    case_builds = [_case_build(case, builds) for case in campaign.sims]
    recorded = {record.run_id for record in workspace.read_manifest()}
    points: list[PointPlan] = []
    for case, build in zip(campaign.sims, case_builds, strict=True):
        case_version = build.fs_version if build is not None else campaign.fs_version
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
                _plan_point(
                    campaign,
                    case,
                    point,
                    workspace,
                    recipe,
                    case_error,
                    recorded,
                    fs_version=case_version,
                )
            )
    groups = _build_groups(campaign)
    plan_file = None
    if write_plan:
        plan_file = workspace.root / "plan.json"
        payload = {
            "campaign": campaign.name,
            "fs_version": canonical,
            "package_version": pyflightstream.__version__,
            "build_groups": groups,
            "points": [{**asdict(entry), "status": str(entry.status)} for entry in points],
        }
        workspace.root.mkdir(parents=True, exist_ok=True)
        plan_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return CampaignPlan(
        campaign=campaign.name,
        fs_version=canonical,
        points=points,
        plan_file=plan_file,
        build_groups=groups,
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
    *,
    fs_version: str,
) -> PointPlan:
    """Judge one point in dry run: names, script build, manifest state.

    ``fs_version`` is the version the dry-run script is built against,
    which is the campaign's unless the case named its own build; it is
    keyword-only and has no default, so a caller cannot silently fall
    back to the campaign's version for a case that runs elsewhere.
    """
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
    script = Script(version=fs_version)
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
    # The dry run built the same COMMANDS the campaign will, so the two
    # provenance flags are already determined here. Not the same bytes,
    # and the difference is exactly one argument: the plan runs before
    # anything is staged, so a case naming a geometry renders `OPEN
    # <library path>` here and `OPEN <staged copy>` at run time. Nothing
    # depends on that today (the plan checks the library file exists, the
    # builder judges only the suffix, and plan.json carries no script
    # text), and it is written down so a later reader does not reuse this
    # render AS the run's. Two things make that reuse wrong even for a
    # case naming no geometry: `write_script` writes in text mode, so on
    # this Windows-primary machine the bytes the solver reads and
    # `script_sha256` hashes carry CRLF while `render()` returns LF; and
    # a RECIPE is user code that may read `case.geometry` in more than one
    # place, or branch on it, so the one-argument difference is a property
    # of the two shipped builders rather than of the mechanism.
    # Reported at plan time
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
    current = file_sha256(origin)
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
        # ABSOLUTE, and not by anything done here: this path is EMITTED
        # into the script while the solver runs with working_dir=sim_dir,
        # so a root-relative spelling would be re-resolved from the
        # simulation folder, one level too deep. CampaignWorkspace
        # resolves its root once, at construction, which is what makes
        # every path derived from it safe to hand to the solver; the
        # reasoning is there rather than repeated at each boundary.
        staged_geometry = str(staged)
    return recipe, None, inputs_sha256, staged_geometry


def _execute_point(
    *,
    campaign: Campaign,
    canonical: str,
    fs_exe: str | Path,
    fs_version: str,
    fs_version_source: str,
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
        # The BUILD's executable, which is the campaign's unless the case
        # named another. Recording campaign.fs_exe unconditionally is what
        # made a per-case build unstatable: the record would name an
        # executable the point never ran (PFS-2009.05).
        "fs_exe": str(fs_exe),
        "fs_exe_sha256": _file_digest(fs_exe),
        # WHICH of the two sources chose that build, beside WHICH build it
        # was. The pair above reproduces the run; without this a reader of
        # a finished record cannot tell a build chosen FOR THIS ROW from
        # one inherited from the campaign, and the two are different facts
        # about how the study was configured (PFS-2009.08.02).
        "fs_version_source": fs_version_source,
        # The velocity the case ASKED for, in the base dict rather than in
        # the success path: four early returns below build the record from
        # `base` alone, so a field written later would be absent from
        # exactly the failed points a reader most wants to compare
        # (OPS-2009.01.13).
        "velocity_requested_m_s": case.velocity,
        # PFS-2027.05: the inputs as written and the resolved state, so
        # the record is recomputable rather than merely trusted.
        "flight_condition": dict(case.flight_condition),
        "density_kg_m3": None if case.fluid is None else case.fluid.density_kg_m3,
        "temperature_k": None if case.fluid is None else case.fluid.temperature_k,
        "viscosity_pa_s": None if case.fluid is None else case.fluid.viscosity_pa_s,
        "density_source": None if case.fluid is None else case.fluid.source,
        "reference_length_m": None if case.fluid is None else case.fluid.reference_length_m,
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
    # The BUILD's version, so a case sent to a second installation emits
    # the commands that installation documents rather than the campaign's.
    script = Script(version=fs_version)
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
        # One composer, never a chain here: the timeout branch used to
        # discard every captured channel, and the timeout branch is the
        # one a pre-script failure takes (INC-20260809-2230).
        error = result.diagnosis()
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
    # RESOLVED, for the reason `CampaignWorkspace.__init__` carries at
    # length: this function has no workspace to inherit an absolute root
    # from, and it hands the solver three things spelled from HERE while
    # the solver runs THERE. Two of them, the simulation it opens and the
    # mesh it writes, become script text, which no chokepoint downstream
    # can fix; the third is the argv, which `_argv` also resolves. A
    # relative `workdir` used to write the mesh one level below the
    # directory this then checks, and report a run that did everything
    # right as "the mesh was not written".
    workdir = Path(workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    mesh_path = workdir / f"surface_mesh.{file_type.lower()}"

    script = Script(version)
    script.emit("OPEN", str(Path(fsm_path).resolve()))
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
