"""The executors: running the solver locally and submitting it to a scheduler.

Private to :mod:`pyflightstream.run`, which re-exports every public name
of it. :class:`LocalExecutor` runs ``FlightStream.exe -script <file>``
(one dash, :data:`SCRIPT_ARGUMENT`) inside the point's own folder and
captures the solver's log; :class:`SubmittingExecutor` hands the script
to a scheduler and returns once the record is written SUBMITTED. The
invocation record, the descriptor rendering, the progress lines of a
local run and the pre-processing surface-mesh export share them.
"""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import pyflightstream._textio as _textio
from pyflightstream._errors import (
    PyflightstreamError,
)
from pyflightstream._progress import (
    say_line,
    workspace_activity,
)
from pyflightstream.cases import (
    EXPORT_KINDS,
    CampaignConfigError,
    SimCase,
    point_name,
)
from pyflightstream.cases.workflows import (
    EXPORT_LOG_VARIABLE,
    UNSTEADY_ACTION_COUNT,
    UNSTEADY_ACTION_PROGRAM,
    row_ncpus,
    row_walltime_s,
    row_walltime_text,
)
from pyflightstream.run._ids import (
    _say,
)
from pyflightstream.run._solver_windows import owned_solver_dialogs as _owned_solver_dialogs
from pyflightstream.run._solver_windows import spared_solver_windows as _spared_solver_windows
from pyflightstream.run._wake_edge_verdict import (
    SOLVER_OWN_LOG,
)
from pyflightstream.script import Script
from pyflightstream.versions import FsVersion, resolve
from pyflightstream.workspace import (
    ExecutorRecord,
)
from pyflightstream.workspace.inputs import HPC_BUILD_ALIAS, HpcProfile

_LOG_NAME = SOLVER_OWN_LOG

#: The creation flag that keeps the solver from opening a console window.
#: ``subprocess.CREATE_NO_WINDOW`` exists only on Windows, so it is read in a
#: ``sys.platform`` branch, the form a type checker resolves per platform; every
#: other platform passes 0, the default, as it did before.
if sys.platform == "win32":
    _NO_WINDOW = subprocess.CREATE_NO_WINDOW
else:
    _NO_WINDOW = 0


#: The suffix of the solver log among a point's declared outputs, the one the
#: log's export kind carries and the one `collect` copies a scheduler's log to.
_LOG_OUTPUT_SUFFIX = next(suffix for kind, suffix, _, _ in EXPORT_KINDS if kind == "log")


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
    started_at : str, optional
        When the process was started, ISO 8601 in UTC to the second
        (PFS-2012.08.01). ``wall_time_s`` says how long the solver ran
        and nothing said WHEN, which a provenance document states as the
        activity's start and end. None for an executor that reports no
        clock, and the record keeps that rather than filling it.
    finished_at : str, optional
        When the process ended, or was killed on timeout, the same way.
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
    started_at: str | None = None
    finished_at: str | None = None

    @property
    def failed(self) -> bool:
        """Whether the process timed out or returned a nonzero code."""
        return self.timed_out or self.return_code != 0

    def captured_output(self) -> str:
        """Return what the solver printed, as a scheduler's job log holds it (0.27.0).

        Standard output, then standard error, one after the other. The text a
        run writes as the declared log on a machine whose HPC profile states
        ``export_log = false``, where no scheduler writes one for a run kept
        local, and the text the build-identity pre-flight reads the build from
        there. An empty string when the solver printed nothing on either.
        """
        stdout, stderr = self.stdout or "", self.stderr or ""
        if stdout and stderr and not stdout.endswith("\n"):
            stdout += "\n"
        captured = stdout + stderr
        return captured if captured.strip() else ""

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


def invocation_record(executor: Executor, result: ExecutionResult) -> ExecutorRecord:
    """Record how the solver was called, read off the executor and its result.

    The half of the invocation the run record did not carry (PFS-2012.04):
    ``argv`` said which command line ran and nothing said which executor
    built it, so a report could only ASSERT the class name. The class
    name is read off the object that ran, and the argv off the result it
    returned, so neither is a description of what the package usually
    does.

    Parameters
    ----------
    executor : Executor
        The executor that ran the script.
    result : ExecutionResult
        What it returned; ``argv`` is empty for an executor that reports
        none, and the record keeps that emptiness rather than filling it.

    Returns
    -------
    ExecutorRecord
        The class name and the argv, in the shape the run manifest and
        the evidence reports carry.
    """
    record: ExecutorRecord = {"class_name": type(executor).__name__, "argv": list(result.argv)}
    # READ OFF THE EXECUTOR, like the class name: a local run that was asked
    # for on a machine that would have submitted says so on every point.
    if getattr(executor, "forced_local", False):
        record["forced_local"] = True
    return record


def describe_invocation(
    record: ExecutorRecord | None = None, *, hidden: bool = True, markdown: bool = False
) -> str:
    """Return the one-line description of the solver invocation.

    Single home of the sentence every report prints about how the
    solver was called, so the script argument it names is the one
    :func:`LocalExecutor._argv` passes rather than a copy of it. Six
    copies of that sentence used to sit in the report writers, where
    nothing would have noticed them disagreeing with the code (NFR-11).

    READ FROM THE RUN WHEN A RECORD IS GIVEN (PFS-2012.04), asserted
    otherwise, and the two sentences differ by construction so a reader
    of committed evidence can tell which one it holds. With a record the
    class name and the flags are the record's own: the flags are every
    argv token between the executable and the script path, which is the
    windowless flag and the script argument for :class:`LocalExecutor`
    and whatever another executor passes, a path token reduced to its
    last component so the sentence carries no machine path. Without one the sentence
    describes the executor the QA layer builds by default, a hidden
    :class:`LocalExecutor`, which is true of every report written before
    the runs carried a record and is the stated fallback for a run that
    carries none.

    Parameters
    ----------
    record : ExecutorRecord, optional
        The invocation as :func:`invocation_record` read it off a real
        run; None for the asserted sentence.
    hidden : bool
        Whether the ASSERTED description covers a windowless run;
        ignored when a record is given, the record saying what ran.
        Keyword-only: two adjacent booleans read as nothing at a call
        site, and this value is written verbatim into committed evidence.
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
    # The two citations are split because they answer different halves
    # and one of them does NOT support the spelling beside it: SRC-003
    # documents the mechanism and the windowless flag, and documents the
    # script argument with TWO dashes. Printing that page beside one
    # dash, as this string did when it was first written, cites a page
    # for a claim it denies. RPT-023 is what carries the spelling.
    citation = "mechanism SRC-003 pp.279-280; argument spelling RPT-023"
    if record is None:
        flags = f"-hidden {SCRIPT_ARGUMENT}" if hidden else SCRIPT_ARGUMENT
        if markdown:
            flags = f"`{flags}`"
        return f"LocalExecutor, {flags} ({citation})"
    # A token that is a path is printed by its last component: the
    # sentence goes into committed evidence, and a machine path in a
    # committed file is the container-directory defect the house style
    # guards against (a stub executor's argv carries its script's path).
    tokens = [
        token.replace("\\", "/").rsplit("/", 1)[-1] if ("/" in token or "\\" in token) else token
        for token in record["argv"][1:-1]
    ]
    if not tokens:
        return f"{record['class_name']}, no argv recorded (as run; {citation})"
    flags = " ".join(tokens)
    if markdown:
        flags = f"`{flags}`"
    return f"{record['class_name']}, {flags} (as run; {citation})"


#: FR-99. Whether THIS machine is the cluster.
#:
#: The predecessor asks exactly this and nothing else, and no cell of any
#: matrix has ever selected the cluster. Reading the platform rather than a
#: cell also removes a whole failure: a cell that must be remembered is a
#: cell that gets forgotten, and a forgotten one on a cluster means a
#: laptop-shaped run holding a login node for the night.
def on_a_cluster() -> bool:
    """Whether this machine submits rather than executes (FR-99).

    Returns
    -------
    bool
        True on Linux, where a cluster scheduler takes the job, and False
        on any other platform, where the solver runs as a local process.
    """
    return platform.system().lower() == "linux"


def _numeric_field(template: object, values: Mapping[str, object]) -> bool:
    """Whether a descriptor field is a bare number rather than a quoted string.

    True only when the template is exactly one substitution and the value
    behind it is an int or a float. `26.123` is a build identifier that
    reads as a float, and quoting it is the difference between a scheduler
    receiving that build and receiving 26.12.
    """
    if isinstance(template, bool):
        # A TOML boolean in the profile (``driveg = true``) is a boolean the
        # scheduler reads, written bare and lower case: quoted, the cluster
        # reads the string "true" or "True" and not the switch (0.35.0).
        return True
    text = str(template).strip()
    if not (text.startswith("{") and text.endswith("}") and text.count("{") == 1):
        return False
    return isinstance(values.get(text[1:-1]), (int, float)) and not isinstance(
        values.get(text[1:-1]), bool
    )


def render_descriptor(profile, values: Mapping[str, object]) -> str:
    """Render one submission descriptor from a profile and this point's values.

    THE PROFILE OWNS THE KEYS and this owns none: every line comes from
    the profile's own field table, so a cluster that spells ``cpus`` or
    ``queue`` or ``account`` is served by editing that table and nothing
    else. A substitution the values cannot supply is refused rather than
    written empty, because a descriptor with a blank where a job name goes
    is a job the scheduler names for you.

    Parameters
    ----------
    profile : HpcProfile
        The cluster profile: its field table, its descriptor format
        (``json``, ``text``, ``toml`` or ``yaml``) and the path it was
        read from.
    values : mapping of str to object
        This point's values, keyed by the placeholder names the profile's
        templates use (for example ``sim``, ``point``, ``fs_build``,
        ``ncpus``).

    Returns
    -------
    str
        The descriptor text, newline terminated, in the profile's format.

    Raises
    ------
    CampaignConfigError
        When a field of the profile asks for a placeholder that ``values``
        does not carry.
    """
    lines: list[str] = []
    rendered: dict[str, str] = {}
    for key, template in profile.fields.items():
        try:
            text = (
                str(template).lower()
                if isinstance(template, bool)
                else str(template).format(**values)
            )
        except KeyError as missing:
            raise CampaignConfigError(
                f"the HPC profile {profile.path} asks for {missing.args[0]!r} in its "
                f"{key!r} "
                f"field, and this run cannot supply it. What it can: "
                f"{', '.join(sorted(values))}."
            ) from None
        rendered[key] = text
    if profile.descriptor_format == "json":
        return json.dumps(rendered, indent=2) + "\n"
    for key, text in rendered.items():
        template = profile.fields[key]
        if profile.descriptor_format == "text":
            lines.append(f"{key}: {text}")
        elif profile.descriptor_format == "toml":
            lines.append(f"{key} = {text}" if isinstance(template, bool) else f'{key} = "{text}"')
        else:
            # yaml. A number stays bare and everything else is quoted, which
            # is what the predecessor's own descriptor does.
            #
            # THE SOURCE TYPE DECIDES, NOT THE TEXT. A build identifier is
            # `26.123`, which reads as a float and is not one: unquoted, a
            # scheduler is handed 26.123 and may hand back 26.12. So a field
            # is bare only when it is exactly one substitution AND the value
            # behind it was a number.
            bare = _numeric_field(template, values)
            lines.append(f"{key}: {text}" if bare else f'{key}: "{text}"')
    return "\n".join(lines) + "\n"


def _names_the_build_alias(profile) -> bool:
    """Whether any field or submit argument of a profile writes ``{fs_build_alias}``."""
    token = "{" + HPC_BUILD_ALIAS + "}"
    return any(token in str(part) for part in (*profile.fields.values(), *profile.submit))


def _canonical_build(build: object) -> str:
    try:
        return resolve(str(build)).canonical
    except PyflightstreamError:
        return str(build)


def _unmapped_build_refusal(profile, builds) -> str | None:
    """Why a profile cannot name these builds to its scheduler, or None when it can.

    PFS-2010.01.06. The matrix names a BUILD (``26.123``) and a scheduler
    may know only a family (``26.1``); the profile's ``[builds]`` table
    translates one into the other, so the cell stays the same on every
    machine. A profile that writes ``{fs_build_alias}`` and has no entry for
    a build a row names is refused here, BY NAME, rather than rendering a
    descriptor with the build in a field that expects the scheduler's word.

    A profile that never writes the substitution is never refused, which is
    every profile written before this table existed.
    """
    if not _names_the_build_alias(profile):
        return None
    table = getattr(profile, "builds", None) or {}
    missing = sorted({_canonical_build(b) for b in builds if b} - set(table))
    if not missing:
        return None
    mapped = ", ".join(f"{k} -> {v}" for k, v in sorted(table.items())) or "nothing"
    return (
        f"the HPC profile {profile.path} writes {{{HPC_BUILD_ALIAS}}} and its [builds] "
        f"table maps no alias for build(s) {', '.join(missing)} (it maps {mapped}). Add a "
        f'line per build under [builds], for example "{missing[0]}" = "<what this '
        'scheduler calls it>". The table is a declaration: it does not check that the '
        "scheduler starts that build, which only the build number in a collected log shows."
    )


@runtime_checkable
class Submitting(Protocol):
    """An executor that hands a job to a SCHEDULER instead of running it.

    ONE DECLARED SEAM, because "is this a submitting executor" was asked
    three different ways in one commit and two of them read the same
    attribute under different predicates: a method probe, an
    ``is None`` on :attr:`descriptor_path`, and a presence test against a
    string sentinel. They could disagree, and the one that decides whether
    outputs are collected was the value probe, so an executor whose submit
    path raised before it wrote anything would have had its outputs
    collected and a log assessed that does not exist (the architect lens,
    round two).

    The :class:`Executor` protocol beside this one already said in its own
    docstring that an HPC submission executor would come later. This is
    that, declared rather than inferred.
    """

    def bind_point(self, values: Mapping[str, object], *, replace: bool = False) -> None:
        """Give this executor one point's values."""

    def submission_record(self) -> dict | None:
        """Return what was handed to the scheduler, or None before anything was."""


def bind_submission_values(executor, case, point_case) -> None:
    """Give a submitting executor the values THIS point's descriptor needs.

    A descriptor names the simulation, the build, the wall clock and the
    processor count, and every one of those is the ROW's. The executor is
    built once for the campaign, so the per-point half arrives here.

    THE PROCESSOR COUNT FALLS BACK TO THE SETUP, exactly as the script's
    own count does. Passing None there was the whole of FR-93 reopened and
    inverted: a row that states no NCPUS column, which is EVERY upgraded
    row, would have reserved an empty field from the scheduler and solved
    on the setup's eight. The requirement's own evidence sentence is a job
    reserving forty-eight processors and solving on eight, and this made
    it true again in the other direction (the architect lens, round two).

    A VALUE THAT CANNOT BE RESOLVED IS OMITTED, never written empty. An
    absent key makes `render_descriptor` refuse by name, which is a
    message; an empty string is a scheduler field with nothing in it.

    Parameters
    ----------
    executor : Executor
        The campaign's executor. Nothing happens unless it submits through
        a scheduler.
    case : SimCase
        The row's case; supplies the simulation id, the build and the
        solver's thread count.
    point_case : SimCase
        The case specialized to this point; supplies the point name, the
        processor count and the wall clock the row states.

    Returns
    -------
    None
        The executor is updated in place with the values for this point's
        descriptor.
    """
    if not isinstance(executor, Submitting):
        return
    values: dict[str, object] = {
        "sim": case.sim_id,
        "point": point_name(point_case, point_case.point) if point_case.point else case.sim_id,
    }
    # C06. THE BUILD THIS POINT ACTUALLY RUNS, and a row that inherits the
    # campaign's has none of its own: writing `case.fs_build or ""` put an
    # empty version in the descriptor while the script was built for the
    # campaign's build. The executor was constructed with the campaign's
    # value, so the row overrides it only when the row HAS one.
    if case.fs_build:
        values["fs_build"] = case.fs_build
    ncpus = row_ncpus(point_case, case.solver.max_threads)
    if ncpus is not None:
        values["ncpus"] = ncpus
    # WHAT THE SCHEDULER'S FIELD CARRIES IS THE PROFILE'S TO SAY (0.21.0).
    # The default is the row's cell AS WRITTEN, so a profile writing
    # `--time={walltime}` gets `4h` where the row wrote `4h`; a profile stating
    # `walltime_arithmetic = "seconds"` gets the integer seconds this package
    # wrote until 0.20.x. Neither touches the watchdog: `walltime_s` below is
    # the deadline the clock counts down to, whatever the descriptor carries.
    walltime = row_walltime_s(point_case)
    written = row_walltime_text(point_case)
    if walltime is not None and written is not None:
        profile = _profile_of(executor)
        arithmetic = profile.walltime_arithmetic if profile is not None else "wall"
        values["walltime"] = int(walltime) if arithmetic == "seconds" else written
        # BOTH SPELLINGS ARE OFFERED, so a profile whose field wants one and
        # whose comment wants the other needs no second run to get it.
        values["walltime_s"] = int(walltime)
        values["walltime_written"] = written
    # C07. THE POINT'S MAPPING IS REBUILT, never merged into the last
    # point's. One executor serves the whole campaign, so updating meant a
    # row that resolves neither a processor count nor a wall clock kept the
    # PREVIOUS row's and submitted resources it never asked for, which also
    # bypassed the refusal the omission above exists to produce. Both of
    # these were written by this session earlier today and found by the
    # independent Codex review of `main`, 2026-09-13.
    executor.bind_point(values, replace=True)


def _submission_record(executor) -> dict | None:
    """Return what a submitting executor handed to the scheduler, or None."""
    if not isinstance(executor, Submitting):
        return None
    return executor.submission_record()


class SubmittingExecutor:
    """Hands a script to a scheduler and does NOT wait for it (FR-15, FR-99).

    THE DESIGN OF 2026-09-08, built as it was drawn. A blocking executor
    that polls the cluster holds a laptop for the night the cluster was
    bought to save; a tool outside the workflow is a run nothing records.
    So this returns as soon as the scheduler has taken the job and the
    record is written SUBMITTED.

    SINCE 0.18.0 A COLLECT STAGE COMPLETES IT. `pyfs-matrix collect`
    watches the workspace for the outputs this point declared, waits until
    every one of them is present AND settled, then collects, assesses and
    rewrites this record with what the run actually did (FR-99,
    `run/collect.py`). Until 0.18.0 a SUBMITTED record was completed BY
    HAND, and this docstring said `collect` completes it in the present
    tense a release before it did, in the one capability whose failure
    mode is an unattended job nobody collects (the V&V lens, round two).

    THE DESCRIPTOR IS WRITTEN WHETHER OR NOT IT IS SUBMITTED, which is the
    predecessor's shape and worth keeping: a descriptor you can read
    without spending anything is how the profile gets checked.
    """

    def __init__(self, profile: HpcProfile, *, values: Mapping[str, object], submit: bool = True):
        # TYPED AND REFUSED HERE, because this is where it is knowable. Reading
        # the profile's cluster fields through `isinstance` downstream turns a
        # profile of another shape into None, and None is the OLD DEFAULTS --
        # EXPORT_LOG left in the script, the walltime as written -- so the
        # failure would look exactly like success on the one machine the fields
        # exist for (the qa lens of the closing round, 2026-09-16).
        #
        # THE PACKAGE'S OWN ERROR, not a bare TypeError: this class is exported
        # and `test_exceptions_catalog` refuses a bare stdlib type from an
        # exported name. `ExecutorConfigurationError` is the one whose docstring
        # already says it is raised at CONSTRUCTION TIME so a misconfiguration
        # surfaces before a campaign starts rather than at its first point,
        # which is exactly this.
        if not isinstance(profile, HpcProfile):
            raise ExecutorConfigurationError(
                "a submitting executor takes an HpcProfile, and this is a "
                f"{type(profile).__name__}. Read one with "
                "pyflightstream.workspace.read_hpc_profile: a profile of another "
                "shape reads as no profile downstream, which is silently the "
                "behaviour of the release before this one."
            )
        self.profile = profile
        #: What every point of this campaign shares, held apart so a
        #: per-point binding can REBUILD on it rather than merge into the
        #: point before (GEO-047-C07).
        self._campaign_values = dict(values)
        self.values = dict(values)
        self.submit = submit
        #: The path of the descriptor this executor last wrote, which is
        #: how a submitted point is found again when the scheduler returns
        #: no handle of its own.
        self.descriptor_path: Path | None = None

    def bind_point(self, values: Mapping[str, object], *, replace: bool = False) -> None:
        """Give THIS point's values to the executor.

        One executor serves a whole campaign and a descriptor names one
        point, so the campaign's values are set once at construction and
        the row's arrive per point. The run stage calls this; a caller
        driving the executor directly may call it too.

        ``replace`` REBUILDS on the campaign's values rather than merging
        into the last point's, which is what the run stage asks for: a row
        that resolves neither a processor count nor a wall clock must not
        inherit the previous row's and submit resources it never asked for
        (GEO-047-C07).
        """
        if replace:
            self.values = {**self._campaign_values, **values}
            return
        self.values.update(values)

    def build_alias_refusal(self, builds) -> str | None:
        """Why this executor's profile cannot name ``builds`` to its scheduler, or None.

        PFS-2010.01.06. Asked once for every build a campaign names, before
        any point is submitted, so a build the profile's ``[builds]`` table
        does not map is refused for the whole campaign rather than at the
        first descriptor after earlier rows have spent the queue.
        """
        return _unmapped_build_refusal(self.profile, builds)

    def submission_record(self) -> dict | None:
        """Return what this executor handed to the scheduler, or None.

        THE EXECUTOR ANSWERS FOR ITSELF, so the run stage does not reach
        through it into the profile's field names. It did, guarding those
        fields with `getattr` defaults that could only ever fire for
        something that is not a profile, where they would turn a loud
        AttributeError into a record claiming an empty path (the architect
        lens, round two).

        None before `run_script` has written a descriptor, which is what
        tells a submitting executor that has submitted from one that has
        not yet.
        """
        if self.descriptor_path is None:
            return None
        return {
            "descriptor": self.descriptor_path.as_posix(),
            "profile": self.profile.path.as_posix(),
            "application_id": self.profile.application_id,
            # WHETHER SUBMISSION WAS REQUESTED, which is what this can
            # honestly say from here; the scheduler's own verdict is in
            # the ExecutionResult beside this record, and FR-99 is worded
            # to match rather than the other way round.
            "submitted": bool(self.submit),
        }

    @workspace_activity("submission", "working_dir")
    def run_script(
        self, script_path: Path, working_dir: Path, timeout_s: float | None = None
    ) -> ExecutionResult:
        """Write the descriptor, submit it, and return without waiting."""
        started = _utc_now()
        values = {
            **self.values,
            "application_id": self.profile.application_id,
            "script_path": Path(script_path).as_posix(),
            "work_dir": Path(working_dir).as_posix(),
        }
        # PFS-2010.01.06. The scheduler's word for this point's build, when
        # the profile maps it; refused by name when the profile writes the
        # substitution and maps nothing for the build.
        refusal = _unmapped_build_refusal(self.profile, [values.get("fs_build")])
        if refusal is not None:
            raise CampaignConfigError(refusal)
        if _a_steady_coupled_script(Path(script_path)):
            # FSI-G: a steady coupled script never exits by itself; only a local
            # run reads its completion line and stops it, and a submitted job
            # would hold its node until the wall clock.
            raise CampaignConfigError(
                f"{Path(script_path).name} is a steady coupled run (it ends at "
                "EXECUTE_AEROELASTIC_ANALYSIS), whose process never exits by itself: a "
                "local run stops it once the analysis ends, and a submitted job would hold "
                "its node until the wall clock. Run it with local (CLI: --local) in this "
                "release."
            )
        build = values.get("fs_build")
        if build and _canonical_build(build) in (getattr(self.profile, "builds", None) or {}):
            values[HPC_BUILD_ALIAS] = self.profile.builds[_canonical_build(build)]
        descriptor = Path(working_dir) / self.profile.descriptor_name
        descriptor.parent.mkdir(parents=True, exist_ok=True)
        _textio.write_text(descriptor, render_descriptor(self.profile, values))
        self.descriptor_path = descriptor
        argv = [
            part.format(descriptor_path=descriptor.as_posix(), **values)
            for part in self.profile.submit
        ]
        if not self.submit:
            # The switch the predecessor spells `esub`, and it gates the
            # CALL alone: the descriptor above is written either way.
            return ExecutionResult(
                return_code=0,
                stdout="",
                stderr="",
                argv=tuple(argv),
                cwd=str(working_dir),
                timeout_s=timeout_s,
                started_at=started,
                finished_at=_utc_now(),
                # A SUBMISSION HAS NO WALL TIME OF ITS OWN. The number that
                # matters is the job's, and the job has not run; reporting
                # the handful of milliseconds this took would put a
                # measurement of the submission where a reader expects a
                # measurement of the solver.
                wall_time_s=0.0,
                timed_out=False,
                log_text=None,
            )
        try:
            completed = subprocess.run(  # noqa: S603
                argv,
                cwd=str(working_dir),
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
                # EXPLICIT, and for the same reason the solver's is: a
                # submit command reads the cluster's own environment,
                # where the module paths and the queue credentials live,
                # so the inheritance is correct and the point is that it
                # is a DECISION at this call rather than a default nobody
                # chose.
                env=os.environ.copy(),
            )
        except OSError as error:
            # THE SCHEDULER IS NOT ON THIS MACHINE, which is what a
            # mistyped submit command or a login node without the client
            # looks like from here. It is this point's failure and not the
            # campaign's: uncaught, one wrong profile aborted every
            # remaining row after the descriptors were already written.
            return ExecutionResult(
                return_code=127,
                stdout="",
                stderr=(
                    f"the submit command {argv[0]!r} could not be run: {error}. It is "
                    f"named by the submit table of {self.profile.path}; the descriptor "
                    f"was written to {descriptor} and nothing was submitted."
                ),
                argv=tuple(argv),
                cwd=str(working_dir),
                timeout_s=timeout_s,
                started_at=started,
                finished_at=_utc_now(),
                wall_time_s=0.0,
                timed_out=False,
                log_text=None,
            )
        return ExecutionResult(
            return_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            argv=tuple(argv),
            cwd=str(working_dir),
            timeout_s=timeout_s,
            started_at=started,
            finished_at=_utc_now(),
            wall_time_s=0.0,
            timed_out=False,
            log_text=None,
        )


#: G43 of 0.28.0: how often an unsteady run's progress is said, in completed time
#: steps, by default. `pyfs-matrix run --progress-every N` sets it; 0 says nothing.
PROGRESS_EVERY_DEFAULT = 10


def _clock(seconds: float) -> str:
    """Seconds as H:MM:SS, for a line a person reads."""
    whole = max(0, int(round(seconds)))
    return f"{whole // 3600}:{whole % 3600 // 60:02d}:{whole % 60:02d}"


def _counter_total_steps(program: Path) -> int | None:
    """Return the time steps a point's counter program was written for, or None without one."""
    if not program.is_file():
        return None
    found = re.search(r"^TIME_ITERATIONS = (\d+)$", program.read_text(encoding="utf-8"), re.M)
    return int(found.group(1)) if found else None


def _progress_line(step: int, total: int, elapsed_s: float) -> str:
    """One progress line: a bar of twenty cells, the step, the share and the time so far."""
    share = min(1.0, step / total) if total else 0.0
    done = int(round(20 * share))
    return (
        f"        [{'#' * done}{'.' * (20 - done)}] step {step}/{total} "
        f"({100 * share:.0f}%)  {_clock(elapsed_s)}"
    )


#: Where a steady coupled run's standard output and error are written while
#: it runs, in its own working directory, so its completion line can be read
#: before the process ends (FSI-G). Read into the result and removed after.
STEADY_COUPLED_STDOUT = "pyfs-solver-stdout.txt"


STEADY_COUPLED_STDERR = "pyfs-solver-stderr.txt"


#: The note a steady coupled run's planned stop leaves beside its outputs.
STEADY_COUPLED_STOP_LOG = "pyfs-aeroelastic-stop.log"


def _run_until_the_analysis_ends(
    argv: list[str], working_dir: Path, timeout_s: float | None
) -> tuple[int | None, str, str, bool]:
    """Run a steady coupled script and stop its process once the analysis ended (FSI-G).

    In a script ``EXECUTE_AEROELASTIC_ANALYSIS`` returns at once and the
    process never exits by itself; the solver prints
    :data:`pyflightstream.cases.fsi_workspace.STEADY_AEROELASTIC_COMPLETION`
    when the analysis ends (26.124, reports/RPT-093 section 8). The
    output goes to two files in the working directory, read every two
    seconds; once the line is there the process is stopped and the run is
    a success, the planned stop noted in :data:`STEADY_COUPLED_STOP_LOG`.
    A process that exits first returns its own code; a timeout kills it as
    every other run's. The owned-window check of every run applies.
    """
    from pyflightstream.cases.fsi_workspace import steady_aeroelastic_finished

    start = time.perf_counter()
    out_path = working_dir / STEADY_COUPLED_STDOUT
    err_path = working_dir / STEADY_COUPLED_STDERR

    def captured() -> tuple[str, str]:
        texts = []
        for path in (out_path, err_path):
            try:
                texts.append(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                texts.append("")
        return texts[0], texts[1]

    def finish(
        code: int | None, timed_out: bool, note: str = ""
    ) -> tuple[int | None, str, str, bool]:
        out, err = captured()
        for path in (out_path, err_path):
            try:
                path.unlink()
            except OSError:
                pass
        return code, out, err + note, timed_out

    def wait_for_the_end(process: subprocess.Popen[str]) -> tuple[int | None, bool, str]:
        while True:
            remaining = None if timeout_s is None else timeout_s - (time.perf_counter() - start)
            if remaining is not None and remaining <= 0:
                process.kill()
                process.wait()
                return None, True, ""
            try:
                code = process.wait(timeout=2.0 if remaining is None else min(2.0, remaining))
                return code, False, ""
            except subprocess.TimeoutExpired:
                pass
            if steady_aeroelastic_finished(captured()[0]):
                process.kill()
                process.wait()
                note = (
                    f"{_utc_now()} pid={process.pid} stopped after the aeroelastic analysis "
                    "ended (its completion line printed); a steady coupled script never exits "
                    "by itself.\n"
                )
                try:
                    with _textio.open_text(working_dir / STEADY_COUPLED_STOP_LOG, "a") as log:
                        log.write(note)
                except (OSError, ValueError):
                    pass
                return 0, False, ""
            pid = getattr(process, "pid", 0)
            try:
                dialogs = _owned_solver_dialogs(pid)
            except OSError as error:
                dialogs = (f"Solver window monitoring failed: {error}",)
            if dialogs:
                diagnostic = (
                    f"{_utc_now()} solver modal/error detected pid={pid}; "
                    "terminating this owned solver process without clicking its dialog.\n"
                    + "\n\n".join(dialogs)
                    + "\n"
                )
                process.kill()
                process.wait()
                try:
                    with _textio.open_text(working_dir / "pyfs-modal-error.log", "a") as log:
                        log.write(diagnostic)
                except (OSError, ValueError) as log_error:
                    say_line(f"[solver] could not persist modal diagnostic: {log_error}")
                say_line(diagnostic.rstrip())
                return process.returncode or 1, False, "\n" + diagnostic

    with (
        _textio.open_text(out_path, "w") as out_file,
        _textio.open_text(err_path, "w") as err_file,
    ):
        process = subprocess.Popen(
            argv,
            cwd=working_dir,
            stdout=out_file,
            stderr=err_file,
            text=True,
            env=os.environ.copy(),
            creationflags=_NO_WINDOW,
        )
        code, timed_out, note = wait_for_the_end(process)
    # The files are closed here, so they can be read whole and removed.
    return finish(code, timed_out, note)


def _run_with_progress(
    argv: list[str],
    working_dir: Path,
    timeout_s: float | None,
    counter: Path,
    total: int | None,
    every: int,
) -> tuple[int | None, str, str, bool]:
    """Run the solver and say its progress every ``every`` steps while it runs.

    THE SIGNAL IS THE RUN'S OWN STEP COUNTER, never what the solver prints: the
    counter program the run wrote counts the solver's invocations of it, one per
    completed time step (RPT-041), and rewrites its state file each time. The
    process is waited on in two-second slices; between them the file is read, and a
    file caught mid-write is read again at the next slice. The output is captured
    exactly as ``subprocess.run`` captured it, and a timeout kills the process as it
    did.
    """
    start = time.perf_counter()
    process = subprocess.Popen(
        argv,
        cwd=working_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=os.environ.copy(),
        creationflags=_NO_WINDOW,
    )
    said = 0
    spared_said: set[str] = set()
    while True:
        remaining = None if timeout_s is None else timeout_s - (time.perf_counter() - start)
        if remaining is not None and remaining <= 0:
            process.kill()
            out, err = process.communicate()
            return None, out or "", err or "", True
        try:
            out, err = process.communicate(
                timeout=2.0 if remaining is None else min(2.0, remaining)
            )
            return process.returncode, out or "", err or "", False
        except subprocess.TimeoutExpired:
            pid = getattr(process, "pid", 0)
            try:
                dialogs = _owned_solver_dialogs(pid)
            except OSError as error:
                dialogs = (f"Solver window monitoring failed: {error}",)
            if dialogs:
                diagnostic = (
                    f"{_utc_now()} solver modal/error detected pid={pid}; "
                    "terminating this owned solver process without clicking its dialog.\n"
                    + "\n\n".join(dialogs)
                    + "\n"
                )
                process.kill()
                out, err = process.communicate()
                # Guarded (GOAL-034 Q8 CXQ8R4-2): a log or stderr that cannot be
                # written must not replace the failed-execution result it reports.
                try:
                    with _textio.open_text(working_dir / "pyfs-modal-error.log", "a") as log:
                        log.write(diagnostic)
                except (OSError, ValueError) as log_error:
                    say_line(f"[solver] could not persist modal diagnostic: {log_error}")
                say_line(diagnostic.rstrip())
                return process.returncode or 1, out or "", (err or "") + "\n" + diagnostic, False
            # A WINDOW THAT ASKS NOTHING IS SPARED AND SAID (0.30.0): the GUI's
            # startup splash of a HIDDEN 0 row. Written once per description
            # into the point's own folder; a failure to write it changes nothing.
            try:
                spared = [s for s in _spared_solver_windows(pid) if s not in spared_said]
            except OSError:
                spared = []
            for description in spared:
                spared_said.add(description)
                try:
                    with _textio.open_text(working_dir / "pyfs-solver-windows.log", "a") as log:
                        log.write(
                            f"{_utc_now()} pid={pid} spared a window that asks nothing: "
                            f"{description}\n"
                        )
                except (OSError, ValueError):
                    pass
            if total is None or every <= 0:
                continue
            try:
                step = action_count(counter)
            except (OSError, ValueError, KeyError, TypeError):
                step = None
            if step is not None and step >= said + every:
                said = step - step % every
                _say(_progress_line(step, total, time.perf_counter() - start))


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
    forced_local : bool
        Keyword only. Whether the local switch kept this run on a machine
        that would otherwise have submitted (``pyfs-matrix run --local``,
        0.27.0): a cluster carrying a profile. Recorded on every point's
        executor entry; it changes nothing about how the solver is called.
    export_log : bool
        Keyword only. Whether the scripts this executor runs export the
        solver log. False on a run the local switch kept on a cluster whose
        HPC profile states ``export_log = false``: that machine's build aborts
        at ``EXPORT_LOG`` whether the job is submitted or run where it is, so
        the profile's decision is the MACHINE's (0.27.0, measured on a cluster
        2026-09-24). No scheduler writes the log of a local run, so the run
        writes the declared log from what this executor captured of the
        solver, its standard output then its standard error; with nothing
        captured the point is judged from its loads export and its record says
        why it has no log.
    progress_every : int
        Keyword only. Time steps between two progress lines; 0 says
        nothing. A negative value is refused.

    Examples
    --------
    The executable is only checked for existence, so a stand-in file shows
    the constructor offline:

    >>> import tempfile
    >>> from pathlib import Path
    >>> from pyflightstream.run import LocalExecutor
    >>> with tempfile.TemporaryDirectory() as folder:
    ...     exe = Path(folder) / "FlightStream.exe"
    ...     _ = exe.write_text("stand-in")
    ...     executor = LocalExecutor(exe)
    ...     (executor.fs_exe.name, executor.hidden, executor.forced_local)
    ('FlightStream.exe', True, False)
    """

    def __init__(
        self,
        fs_exe: str | Path,
        hidden: bool = True,
        *,
        forced_local: bool = False,
        export_log: bool = True,
        progress_every: int = PROGRESS_EVERY_DEFAULT,
    ) -> None:
        self.fs_exe = Path(fs_exe)
        self.hidden = hidden
        self.forced_local = forced_local
        self.export_log = export_log
        if int(progress_every) < 0:
            raise ExecutorConfigurationError(
                f"progress_every is {progress_every}; it counts time steps between two "
                "progress lines, so it is a whole number, 0 to say nothing."
            )
        self.progress_every = int(progress_every)
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

    @workspace_activity("solver", "working_dir")
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
        # A keyword bag for ExecutionResult: values differ by key, hence ``Any``.
        invocation: dict[str, Any] = {
            "argv": tuple(argv),
            "cwd": str(working_dir),
            "timeout_s": timeout_s,
        }
        start = time.perf_counter()
        started_at = _utc_now()
        timed_out = False
        return_code: int | None = None
        stdout = ""
        stderr = ""
        # G43 of 0.28.0: an unsteady point that carries its step counter says how
        # far it is every `progress_every` steps while it runs; every other run is
        # waited on exactly as before.
        total = (
            _counter_total_steps(Path(working_dir) / UNSTEADY_ACTION_PROGRAM)
            if getattr(self, "progress_every", 0) > 0
            else None
        )
        if _a_steady_coupled_script(script_path):
            return_code, stdout, stderr, timed_out = _run_until_the_analysis_ends(
                argv, Path(working_dir), timeout_s
            )
        elif total is not None or os.name == "nt":
            return_code, stdout, stderr, timed_out = _run_with_progress(
                argv,
                Path(working_dir),
                timeout_s,
                Path(working_dir) / UNSTEADY_ACTION_COUNT,
                total,
                self.progress_every,
            )
        else:
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
        finished_at = _utc_now()
        log_path = Path(working_dir) / _LOG_NAME
        log_text = None
        if log_path.is_file():
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
        modal_log = Path(working_dir) / "pyfs-modal-error.log"
        if modal_log.is_file() and "solver modal/error detected" in stderr:
            log_text = (log_text or "") + "\n" + stderr
        return ExecutionResult(
            return_code=return_code,
            wall_time_s=wall_time_s,
            timed_out=timed_out,
            log_text=log_text,
            stdout=stdout,
            stderr=stderr,
            started_at=started_at,
            finished_at=finished_at,
            **invocation,
        )


def _a_steady_coupled_script(script_path: Path) -> bool:
    """Whether the script at this path is a steady coupled run's (FSI-G of 0.30.0)."""
    from pyflightstream.cases.fsi_workspace import is_steady_aeroelastic_script

    try:
        text = Path(script_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return is_steady_aeroelastic_script(text)


def _utc_now() -> str:
    """Return the clock reading a run record carries: ISO 8601, UTC, to the second."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def _decode(stream: str | bytes | None) -> str:
    if stream is None:
        return ""
    if isinstance(stream, bytes):
        return stream.decode(errors="replace")
    return stream


def action_count(path: Path) -> int | None:
    """Read the count the point's counter program reached, or None when it never wrote.

    The program writes its state as one JSON object per invocation,
    replacing the previous one, and ``count`` is the number of times the
    solver ran it, which is the number of time steps it completed
    (RPT-041 finding 2).

    Parameters
    ----------
    path : Path
        The JSON file the counter program writes.

    Returns
    -------
    int or None
        The number of times the solver ran the program, or None when the
        file does not exist.
    """
    if not path.is_file():
        return None
    return int(json.loads(path.read_text(encoding="utf-8"))["count"])


def _profile_of(executor: object) -> HpcProfile | None:
    """Return the HPC profile an executor submits through, or None.

    ONE `getattr`, and it asks the question that is genuinely open -- whether
    this executor submits at all -- rather than asking each field whether it
    exists. Reading `export_log` or `walltime_arithmetic` with a default hid
    the model from the type checker exactly where the cluster features live,
    and a renamed field would have returned the default in silence (the
    architecture lens, 2026-09-16).
    """
    profile = getattr(executor, "profile", None)
    return profile if isinstance(profile, HpcProfile) else None


def _machine_exports_log(executor: object) -> bool:
    """Whether the machine an executor runs on lets a script export the solver log.

    The profile's ``export_log`` for an executor submitting through one, and a
    local executor's own ``export_log``, which is False on a run the local
    switch kept on a cluster whose profile turns the export off (0.27.0): the
    build there aborts at ``EXPORT_LOG`` whether the job is submitted or not,
    and until 0.27.0 only a submitted job was spared it. True for any other
    executor.
    """
    profile = _profile_of(executor)
    if profile is not None:
        return profile.export_log
    if isinstance(executor, LocalExecutor):
        return executor.export_log
    return True


def _with_the_profile_s_log(case: SimCase, executor: object) -> SimCase:
    """Return the case as the EXECUTOR's machine writes its log (0.21.0).

    Some clusters abort at ``EXPORT_LOG`` and write their own log beside the
    run; their HPC profile says so, and the builders read the CASE and know
    nothing of a profile. So the decision is written onto the case here, the
    way the command line writes IGNORE_MISSING_FAMILIES, and only the FALSE
    side is ever written: a run on any other machine, or through any other
    executor, renders byte for byte what it rendered before.

    THE MACHINE'S DECISION, submitted or not (0.27.0): a run the local switch
    keeps on such a cluster carries it on its local executor, because the build
    that aborts at ``EXPORT_LOG`` is the same build either way. Read through
    the profile alone, a point run there with ``--local`` stopped at
    ``EXPORT_LOG`` after every other export (measured on a cluster, 2026-09-24).
    """
    if _machine_exports_log(executor):
        return case
    return case.model_copy(update={"variables": {**case.variables, EXPORT_LOG_VARIABLE: "false"}})


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
    _textio.write_text(script_path, script.render())

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
