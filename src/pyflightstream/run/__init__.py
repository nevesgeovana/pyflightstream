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
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import warnings
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Protocol, runtime_checkable

import pyflightstream
from pyflightstream._digest import file_sha256, optional_file_sha256, text_sha256
from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning
from pyflightstream.cases import (
    Campaign,
    CampaignConfigError,
    ScriptRecipe,
    SimCase,
    case_at_point,
    check_recipe,
    point_name,
    resolve_recipe,
    sweep_name,
)
from pyflightstream.cases.workflows import (
    COLD_START_VARIABLE,
    EXPORT_LOG_VARIABLE,
    RESTART_FROM_VARIABLE,
    RESTART_ITERATIONS_VARIABLE,
    RESTART_VARIABLE,
    SIMULATION_SUFFIX,
    UNSTEADY_ACTION_COUNT,
    UNSTEADY_ACTION_PROGRAM,
    UNSTEADY_ACTION_SCRIPT,
    UNSTEADY_COUNTER_ACTION,
    WALLTIME_CLOCK_ACTION,
    WALLTIME_CLOCK_PROGRAM,
    WALLTIME_CLOCK_STATE,
    WALLTIME_STOP_SCRIPT,
    WorkflowConventions,
    build_steady_sweep,
    parse_restart,
    reduction_windows,
    restart_iterations,
    row_ncpus,
    row_walltime_s,
    row_walltime_text,
    unsteady_export_threshold,
    walltime_clock_program,
    walltime_margin_s,
)
from pyflightstream.results import (
    SOLVER_MODES,
    IncompleteOutputError,
    LoadsReport,
    VersionMismatchWarning,
    classify_solver_mode,
    parse_loads,
    parse_log_times,
    parse_residual_history,
)
from pyflightstream.results.conditions import ConditionBinding, bind_conditions
from pyflightstream.results.tables import sweep_table, write_table
from pyflightstream.run._actions_counter import render_program
from pyflightstream.script import MarchStrategy, Script
from pyflightstream.versions import FsVersion, resolve
from pyflightstream.workspace import (
    KNOWN_MANIFEST_SCHEMAS,
    LEGACY_SIM_OUTPUTS_DIR,
    MANIFEST_SCHEMA,
    SIM_DATAPOINTS_DIR,
    SIM_OUTPUTS_DIR,
    CampaignWorkspace,
    ExecutorRecord,
    NamingTemplateError,
    RunRecord,
    RunStatus,
    WorkspaceError,
    collection_name,
    datapoint_dir_name,
    post_stages,
)
from pyflightstream.workspace.inputs import HPC_BUILD_ALIAS, HpcProfile
from pyflightstream.workspace.naming import ARCHIVE_STAMP, PointName, sweep_file_stem

__all__ = [
    "ACCEPT_UNREGISTERED_BUILD_FLAG",
    "PLAN_REQUIRED_MESSAGE",
    "plan_receipt_error",
    "FS_VERSION_FROM_DEFAULT",
    "FS_VERSION_FROM_ROW",
    "SCRIPT_ARGUMENT",
    "SWEEP_TABLE_NAME",
    "Assessment",
    "CampaignErrors",
    "CampaignPlan",
    "PlannedPointCost",
    "ExecutionResult",
    "Executor",
    "ExecutorConfigurationError",
    "ExecutorRecord",
    "LoadsAssessor",
    "LocalExecutor",
    "SubmittingExecutor",
    "on_a_cluster",
    "render_descriptor",
    "OutcomeAssessor",
    "PlanStatus",
    "PointPlan",
    "estimate_point_cost",
    "format_cost_table",
    "point_costs",
    "Reconstruction",
    "SolverBuild",
    "SurfaceMeshExportError",
    "check_solver_identity",
    "describe_invocation",
    "export_surface_mesh",
    "invocation_record",
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
    return {"class_name": type(executor).__name__, "argv": list(result.argv)}


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
    """Whether this machine submits rather than executes (FR-99)."""
    return platform.system().lower() == "linux"


def _numeric_field(template: object, values: Mapping[str, object]) -> bool:
    """Whether a descriptor field is a bare number rather than a quoted string.

    True only when the template is exactly one substitution and the value
    behind it is an int or a float. `26.123` is a build identifier that
    reads as a float, and quoting it is the difference between a scheduler
    receiving that build and receiving 26.12.
    """
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
    """
    lines: list[str] = []
    rendered: dict[str, str] = {}
    for key, template in profile.fields.items():
        try:
            text = str(template).format(**values)
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
            lines.append(f'{key} = "{text}"')
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


def _bind_submission_values(executor, case, point_case) -> None:
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
        arithmetic = _profile_of(executor).walltime_arithmetic if _profile_of(executor) else "wall"
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
        build = values.get("fs_build")
        if build and _canonical_build(build) in (getattr(self.profile, "builds", None) or {}):
            values[HPC_BUILD_ALIAS] = self.profile.builds[_canonical_build(build)]
        descriptor = Path(working_dir) / self.profile.descriptor_name
        descriptor.parent.mkdir(parents=True, exist_ok=True)
        descriptor.write_text(render_descriptor(self.profile, values), encoding="utf-8")
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
                argv=argv,
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
                argv=argv,
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
            argv=argv,
            cwd=str(working_dir),
            timeout_s=timeout_s,
            started_at=started,
            finished_at=_utc_now(),
            wall_time_s=0.0,
            timed_out=False,
            log_text=None,
        )


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
        started_at = _utc_now()
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
        finished_at = _utc_now()
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
            started_at=started_at,
            finished_at=finished_at,
            **invocation,
        )


def _utc_now() -> str:
    """Return the clock reading a run record carries: ISO 8601, UTC, to the second."""
    return datetime.now(UTC).isoformat(timespec="seconds")


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
    log_file_used : str, optional
        Name of the solver log the residual verdict was read from, or
        None where none was read and the judgment fell to the iteration
        count. Recorded because the two are DIFFERENT CLAIMS about a
        result: an unsteady point with no log is recorded
        ``COMPLETED_MAX_ITER`` whatever the solver did, and a later
        reader of the manifest cannot otherwise tell that from a point
        whose residuals were actually read and missed the threshold.

        IT REACHES THE MANIFEST, which is the whole point of it and was
        not true of the first version: the field was populated on the
        assessment and dropped at the RunRecord boundary, so the reader
        it names still could not tell the two apart.
    residual_note : str, optional
        Where a final residual did not fit its printed field and was read
        from an earlier iteration instead, which column, which iteration
        and what value; None where every final residual was printed.
    solver_run_time_s, solver_initialization_s, time_steps : optional
        The solver's own run time and initialization time in seconds and the
        time steps of an unsteady run, read from the log the verdict read;
        None where no log was read or it prints no such line.
    """

    status: RunStatus
    iterations: int | None = None
    residual: float | None = None
    error: str | None = None
    fs_version_reported: str | None = None
    fs_build: str | None = None
    conditions: list[dict] | None = None
    log_file_used: str | None = None
    residual_note: str | None = None
    solver_run_time_s: float | None = None
    solver_initialization_s: float | None = None
    time_steps: int | None = None


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
    ``sim_dir / "outputs"``, and in ``sim_dir / "raw"`` where a workspace
    written before 0.16.0 holds one, FR-84) and decides between
    converged, iteration limited, and diverged. The standard
    implementation lands with the results parsers.
    """

    def __call__(self, case: SimCase, execution: ExecutionResult, sim_dir: Path) -> Assessment:
        """Return the judgment of one executed point."""
        ...


def _reads_as_residual_history(path: Path) -> bool:
    """Whether one collected file parses as a solver residual history.

    The identification is by CONTENT and never by name, the same rule
    the loads table is found under: a swept case names its outputs per
    point, so no literal could name them all. False on anything that
    does not parse, including a file this process cannot read, because
    the caller's fallback is the judgment that existed before and never
    an error about a file nobody asked it to read.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    try:
        return bool(parse_residual_history(text))
    except (IncompleteOutputError, ValueError):
        return False


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
      COMPLETED_MAX_ITER. EXPORTING a log is what changes that; naming
      it is not required, because a collected file that parses as a
      residual history is found by content.

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
        Name of the exported solver log (EXPORT_LOG). None, the default,
        finds the collected output that parses as a residual history,
        the same rule ``loads_file`` follows and for the same reason: a
        swept case names its outputs per point, so no single literal
        could name them all.

        NAMING IT IS STRICTER, not weaker: a named file that was not
        collected is a refusal, while the default falls back to the
        iteration-count judgment when nothing parses. Name it when the
        run must not be judged without residuals.
    requested_version : str or FsVersion, optional
        Version the campaign requested; enables the FR-18 cross-check
        against the version printed in the loads footer.

    Notes
    -----
    Every refusal carries ``FAILED_INCOMPLETE_OUTPUT``, and that is a
    constrained choice rather than the right name for each of them. The
    terminal set is closed at six values, and it was resolved on
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
       outputs; or ``log_file`` was not named and SEVERAL collected
       outputs parse as a residual history, because choosing one would
       be a guess about which is this point's. Zero candidates is not a
       refusal: it is the iteration-count judgment, which is what every
       campaign that exports no log has always received.
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
        # THE POINT'S OWN FOLDER, OR THE TWO A CAMPAIGN WROTE INTO BEFORE
        # 0.16.0, AND NEVER BOTH (FR-92). A point collects into
        # `datapoints/DP-<point>/` since this release, so what is there is
        # that point's evidence and nothing else; `outputs/` held every
        # point of the simulation at once, and `raw/` was its name before
        # 0.16.0. A workspace recorded under an older layout must keep
        # every one of its points, so both are still read -- but ONLY
        # where the point has no folder of its own. Mixing them would put
        # a sweep's shared folder back beside the point's own, which is
        # what this layout exists to prevent.
        #
        # The `break` below therefore ranks nothing on the first branch,
        # which holds one folder; it ranks `outputs/` before `raw/` on the
        # legacy branch, where a workspace can hold both.
        # `case` is None where a caller judges a folder directly rather
        # than a point, which the unit tests do and which is why this
        # reads through getattr like the declared-outputs narrowing below.
        point = getattr(case, "point", None)
        # `if point` and not `is not None`: an EMPTY mapping has no folder to
        # be judged from, and it cannot reach here carrying evidence anyway,
        # because `collect_outputs` refuses it before anything is moved.
        # 0.21.0: a record carried across as a case names its folder by the name
        # the run recorded; a real case is named by `point_name`.
        recorded_name = getattr(case, "datapoint_name", None)
        if recorded_name:
            own_name: str | None = datapoint_dir_name(PointName(recorded_name))
        elif point and hasattr(case, "condition_order"):
            # A REAL CASE, asked by what only a case has, and not by whether a
            # name happened to be recorded. 0.21.1: a record carried across as a
            # case can reach here with NO recorded name -- a 0.20.x swept row
            # carries neither a point name nor a working directory, because the
            # whole sweep was one job in the simulation folder -- and it then
            # fell into this branch and raised AttributeError on
            # `condition_order`. That is not a WorkspaceError, so the collecting
            # sweep does not catch it and one such record aborts the collection
            # of every other point in the workspace (the qa lens, FIX-0211).
            own_name = datapoint_dir_name(PointName(point_name(case, point)))
        else:
            # No name recorded and nothing that can compute one: the point is
            # judged from the simulation folder, as it was before 0.21.0.
            own_name = None
        own = None if own_name is None else Path(sim_dir) / SIM_DATAPOINTS_DIR / own_name
        # THE PREDICATE IS EXISTENCE AND NOT EMPTINESS, and the difference
        # is a wrong answer (the architecture and verification lenses,
        # 2026-09-11). A point whose folder EXISTS is judged from that
        # folder whatever is in it: an empty one earns this point's own
        # refusal. Falling through to the shared folder because the
        # point's own was empty is how a point whose collection failed
        # got judged on ANOTHER point's export.
        #
        # MEASURED, because on an alpha sweep the operating-point binding
        # below hides it: a loads export prints alpha, beta and velocity
        # and NEVER prints the advance ratio, so on a J sweep the binding
        # cannot tell two points apart, and the point at J=1.7 was
        # recorded CONVERGED on the export of J=1.3 in silence. That is
        # the defect REV010-001 exists against, re-entered by a new door.
        folders = (
            [f"{SIM_DATAPOINTS_DIR}/{own_name}"]
            if own is not None and own.is_dir()
            else [SIM_OUTPUTS_DIR, LEGACY_SIM_OUTPUTS_DIR]
        )
        collected: list[Path] = []
        for folder in folders:
            found = sorted(
                (path for path in (Path(sim_dir) / folder).glob("*") if path.is_file()),
                key=lambda path: path.name,
            )
            if found:
                collected = found
                break
        # THE POINT'S OWN OUTPUTS, when the case declares them. This
        # narrowed a SHARED folder to the files this point declared, and
        # it is kept for the older layouts above, where the folder is
        # still shared. In a datapoint folder it selects everything and
        # changes nothing. A case that declares no outputs is judged over
        # the whole folder.
        declared = {Path(name).name for name in getattr(case, "outputs", None) or ()}
        if declared:
            own = [path for path in collected if path.name in declared]
            if own:
                collected = own
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
            report_path = found[0]
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
            if len(usable) > 1:
                # A WORKSPACE RECORDED BEFORE 0.16.0 SHARES ONE FOLDER
                # between the points of a case, so from the second point
                # onward every earlier point's export is still sitting
                # there and parses just as well. Points collected under
                # this release each have their own folder (FR-92) and
                # never reach here. Ask REV010-001's binding,
                # thirty lines below, which of them the solver actually ran at
                # THIS point's conditions: a loads export prints the alpha,
                # the sideslip and the velocity it ran, so the file that
                # belongs to this point identifies itself.
                #
                # THIS IS NOT A RELAXATION. Where the binding does not settle
                # it -- none match, or several do -- the refusal below stands
                # exactly as it was, because attributing another point's
                # result to this one is the defect REV010-001 exists against
                # and it is worse than refusing. Naming the file cannot fix
                # this and never could: the message used to offer that, forty
                # lines under the sentence saying no literal names them all on
                # a swept case.
                mine = [
                    (path, report)
                    for path, report in usable
                    if not _bind_case_conditions(case, report).mismatches
                ]
                if len(mine) == 1:
                    usable = mine
            if len(usable) != 1:
                names = ", ".join(path.name for path in collected) or "nothing"
                reason = "none of them parses" if not usable else "several of them parse"
                return Assessment(
                    status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
                    error=(
                        f"no single collected output reads as a loads table ({reason}); "
                        f"collected: {names}. Each point collects into its own "
                        f"{SIM_DATAPOINTS_DIR}/ folder since 0.16.0, so this folder "
                        "should hold one point's exports: either the point exported "
                        "no loads spreadsheet, or it exported several. A workspace "
                        "recorded before 0.16.0 shares one folder between the points "
                        "of a case, and there this assessor keeps the export whose "
                        "printed conditions match the point it is judging; reaching "
                        "here means none of them did, or more than one did. Naming a "
                        "file is not offered as a remedy: a swept case names its "
                        "outputs per point, so no single literal names them all. "
                        "Check what this point exported, or judge the row from Python "
                        "with an assessor that knows which file is which"
                    ),
                )
            report_path = usable[0][0]
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
        stamp: dict[str, object] = {
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
                    "result of this one. Each point collects into its own "
                    "folder, so a later sweep point no longer overwrites a same "
                    "named export there; give each point a uniquely named output "
                    "anyway, because the post-processing products of a point are "
                    "named after it and two points sharing it collide in the "
                    "product tree"
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
        if self.log_file is None:
            # AUTO-DETECTION BY CONTENT, on the same ground the loads
            # table is found by content: a swept case names its outputs
            # per point, so no literal could name them all, and a file
            # collected from THIS run's folder that parses as a residual
            # history is this run's solver log.
            #
            # WHAT THIS CHANGES, said plainly because it changes a
            # published status. Until now an unsteady run was recorded
            # COMPLETED_MAX_ITER unconditionally, since the time loop
            # always reaches its prescribed end and the iteration
            # counter therefore says nothing. That is a statement about
            # this package's evidence and it reads as a statement about
            # the solver: a run that converged at every time step and a
            # run that never converged at any came out with the same
            # word. A collected log settles it, and a run that exports
            # one should not have to be asked twice for permission to
            # use it. Nothing is auto-detected when no collected file
            # parses as a history, so a campaign that exports no log is
            # judged exactly as it was.
            #
            # Several candidates are NOT resolved by choosing: that
            # would be a guess about which is the log of this point.
            candidates = [
                path
                for path in collected
                if path != report_path and _reads_as_residual_history(path)
            ]
            if len(candidates) == 1:
                log_path = candidates[0]
            elif len(candidates) > 1:
                # SEVERAL IS A REFUSAL, exactly as it is for the loads
                # table one branch up, and for the same reason: choosing
                # one would be a guess about which is the log of THIS
                # point. The first version fell through silently to the
                # iteration-count judgment, which is the verdict this
                # whole path exists to replace, so a campaign that had
                # gone to the trouble of exporting a log got the old
                # answer and no way to tell.
                names = ", ".join(path.name for path in candidates)
                return Assessment(
                    status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
                    iterations=report.current_iteration,
                    error=(
                        f"{len(candidates)} collected outputs read as a solver log "
                        f"({names}), so which one carries this point's residuals is a "
                        "guess. Name it with LoadsAssessor(log_file='<name>'), or give "
                        "each point a uniquely named log"
                    ),
                    **stamp,
                )
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
            stamp["log_file_used"] = log_path.name
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
            # 0.21.0: the times the log prints ride on every verdict read from it.
            times = parse_log_times(log_text)
            stamp["solver_run_time_s"] = times.solver_run_time_s
            stamp["solver_initialization_s"] = times.solver_initialization_s
            stamp["time_steps"] = times.time_steps
            try:
                history = parse_residual_history(log_text)
                final = history[-1]
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
            # A FIELD TOO NARROW IS NOT A DIVERGENCE. The solver prints a run
            # of asterisks when a number does not fit its column, and on the
            # LAST row that turned a converged run into FAILED_DIVERGED: a
            # 26.100 rotor printed `*************` in the pressure column at
            # its final iteration, 1.15e-9 on the row before. The overflowed
            # column is read from its last printed value, and ONLY when that
            # value is already within the limit: a column that overflowed from
            # above the limit may have overflowed because it grew, so it stays
            # unjudged. What was read, and from which iteration, is recorded.
            notes: list[str] = []
            for name in sorted(final.overflowed):
                earlier = next(
                    (
                        (sample.iteration, getattr(sample, f"{name}_residual"))
                        for sample in reversed(history[:-1])
                        if name not in sample.overflowed
                        and math.isfinite(getattr(sample, f"{name}_residual"))
                    ),
                    None,
                )
                if earlier is not None and earlier[1] <= report.convergence_limit:
                    components[name] = earlier[1]
                    notes.append(
                        f"the {name} residual of iteration {final.iteration} did not fit its "
                        f"printed field; read from iteration {earlier[0]}, {earlier[1]:.4g}"
                    )
            if notes:
                stamp["residual_note"] = "; ".join(notes)
            nonfinite = [
                f"{name}={value!r}"
                for name, value in components.items()
                if value is None or not math.isfinite(value)
            ]
            if nonfinite:
                overflow = (
                    f" The solver printed {', '.join(sorted(final.overflowed))} as a field "
                    "of asterisks, and the last printed value of that column is not within "
                    "the limit, so it may have overflowed because it grew."
                    if final.overflowed
                    else ""
                )
                return Assessment(
                    status=RunStatus.FAILED_DIVERGED,
                    iterations=final.iteration,
                    error=(
                        "non-finite final residual(s): "
                        f"{', '.join(nonfinite)}. A residual that is NaN or "
                        "infinite is not a small number, so no convergence "
                        "judgment can be made from it; the solver diverged or "
                        "the log is corrupt at that iteration." + overflow
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
                        "Export the solver log (EXPORT_LOG) for a residual judgment, which "
                        "is found by content and does not have to be named, or find "
                        "why the solver stopped"
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


def _action_count(path: Path) -> int | None:
    """Read the count the point's counter program reached, or None when it never wrote.

    The program writes its state as one JSON object per invocation,
    replacing the previous one, and ``count`` is the number of times the
    solver ran it, which is the number of time steps it completed
    (RPT-041 finding 2).
    """
    if not path.is_file():
        return None
    return int(json.loads(path.read_text(encoding="utf-8"))["count"])


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
    decision for the owning seat and is registered rather than taken. This
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


#: The command-line flag that accepts an installed build other than the registered
#: one (0.21.0), named once so the refusal, the warning and the parser agree.
ACCEPT_UNREGISTERED_BUILD_FLAG = "--accept-unregistered-build"


def check_solver_identity(
    executor: Executor,
    version: FsVersion,
    workdir: Path,
    *,
    timeout_s: float = 60.0,
    accept_unregistered_build: bool = False,
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
        # 0.21.0, the owner's decision of 2026-09-15: a build that EXISTS and is
        # not the registered one may be accepted on request, and then its
        # compatibility is the user's responsibility. It is warned, and every
        # record of the run says the acceptance was made.
        if accept_unregistered_build:
            warnings.warn(
                f"the executable is FlightStream build #{installed} and the campaign "
                f"declares {version.canonical}, registered as build #{version.build}. "
                f"Running anyway, because {ACCEPT_UNREGISTERED_BUILD_FLAG} was given: "
                "whether this build computes what the registered one does is yours to "
                "know, and every record of this run says the flag was used.",
                VersionMismatchWarning,
                stacklevel=2,
            )
            return
        raise ExecutorConfigurationError(
            f"the executable is FlightStream build #{installed}, but the campaign "
            f"declares {version.canonical}, which is build #{version.build}. Nothing "
            "ran. The printed version string cannot show this, because both builds of "
            "a minor release print the same one, and their records differ; check "
            "fs_exe against the installation folder of the version the campaign names. "
            f"If this build is one you know to be compatible, run with "
            f"{ACCEPT_UNREGISTERED_BUILD_FLAG} (accept_unregistered_build=True): its "
            "compatibility is then your responsibility, and the records say so."
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
    *,
    accept_unregistered_build: bool = False,
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
        # FR-99. A SUBMITTING EXECUTOR HAS NO SOLVER TO ASK. The identity
        # check runs a small script and reads the build back, which is a
        # question about the executable ON THIS MACHINE; a cluster's solver
        # is on the cluster, and asking would submit a probe job to a queue
        # to answer a question the descriptor states. WHAT IT STATES IS A
        # NAME, NOT A GUARANTEE: on a real cluster the descriptor carries the
        # scheduler's family name (`26.1`), which covers more than one build,
        # and the profile's [builds] table only DECLARES which build that
        # name means (PFS-2010.01.06). So a submitted point is NOT guarded
        # here; which build it ran on is known only from the build number in
        # its collected log.
        if getattr(case_executor, "descriptor_path", "missing") != "missing":
            continue
        workdir = Path(tempfile.mkdtemp(prefix="pyfs-preflight-"))
        try:
            check_solver_identity(
                case_executor,
                resolve(case_version),
                workdir,
                accept_unregistered_build=accept_unregistered_build,
            )
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


def _leave_products(workspace: CampaignWorkspace, matrix_stem: str | None) -> str | None:
    """Write the campaign's products under its products root, never raising.

    PFS-2029.15.03, the sibling of :func:`_leave_sweep_table` and under the
    same rule: the products are derived from the manifest and the collected
    exports, so rewriting them after a resume adds the new points and can
    destroy nothing, and a write error must not replace the campaign's own
    outcome. ``pyfs-matrix post`` is the same writer run by hand; it archives
    each existing product before rewriting it, and only ``--force-overwrite``
    keeps no copy.
    """
    where = workspace.products_dir(matrix_stem)
    try:
        for stage in post_stages():
            stage(workspace, overwrite=True, matrix_stem=matrix_stem)
    except Exception as error:
        return (
            f"the campaign ran and its products were NOT written under "
            f"{where}: {type(error).__name__}: {error}. "
            f"No run outcome is affected and nothing is lost: every point is recorded in "
            f"{workspace.manifest_path}. Fix the cause and rebuild them with "
            # NO --overwrite. This named that flag until 2026-09-14, and `post`
            # had not accepted it since 0.17.0, when the archive replaced the refusal, so
            # the one command the warning offered was refused by argparse.
            "`pyfs-matrix post --workspace <root>`, which archives what is there first."
        )
    return None


def _leave_sweep_table(workspace: CampaignWorkspace, matrix_stem: str | None) -> str | None:
    """Write the campaign's sweep table under ``post/``, never raising.

    Under ``post/<matrix>/`` for a campaign converted from a run matrix,
    holding that matrix's records alone (PFS-2031.04).

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
    target = workspace.sweep_dir(matrix_stem) / SWEEP_TABLE_NAME
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        write_table(sweep_table(workspace, require_loads=False, matrix_stem=matrix_stem), target)
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
    force_rerun: Sequence[str] | None = None,
    preflight: bool = True,
    builds: Mapping[str, SolverBuild] | None = None,
    name_from: str | None = None,
    quiet: bool = False,
    accept_unregistered_build: bool = False,
) -> list[RunRecord]:
    """Run every point of a campaign, recording each in the manifest.

    Per point, in order: specialize the case (sweep point and staged
    geometry), build the script through the recipe (failure:
    FAILED_SCRIPT), execute it (failure or timeout:
    FAILED_EXECUTION), collect the declared outputs into that point's
    own ``datapoints/DP-<point>/``
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
    force_rerun : sequence of str, optional
        The points to REDO rather than refuse, each by its point name, by
        its full ``run_id``, or by the job id of a swept row, which names
        every point of it because a job is indivisible. For a row that was WRONG, where the
        correction does not change the point's name and the identity is
        therefore the same: the manifest is copied into ``archive/``, the
        named records leave it, and each point's collected outputs move
        into that point's own ``archive/<stamp>/``.

        IT NAMES POINTS AND IS NOT A SWITCH. Redoing every recorded point
        of a matrix because one row was wrong spends a licensed seat per
        point, and a seat is the one thing here that archiving cannot give
        back (the interface lens, FIX-0212).

        A name that matches no recorded point is refused rather than
        ignored. Refused together with ``resume``, which SKIPS a recorded
        point instead: a caller asking for both has not said which.

        A point of a row stating RESTART is not superseded -- that row
        CONTINUES what is recorded, so its records are its subject rather
        than a fork -- and naming one says so rather than passing over it.
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
    # A RESUME UNDER ANOTHER NAME IS REFUSED (PFS-2029.03.02): the run ids
    # the manifest holds begin with the campaign's name, so a workspace
    # renamed since its first run derives a name that matches none of them,
    # and every point would read as new rather than as recorded.
    recorded_names = sorted({run_id.split("/", 1)[0] for run_id in recorded})
    if resume and recorded_names and campaign.name not in recorded_names:
        raise WorkspaceError(
            f"cannot resume under the campaign name {campaign.name!r}: the manifest of "
            f"{workspace.root} records {', '.join(repr(n) for n in recorded_names)}, and a "
            "run id begins with the name, so nothing here would be recognised as "
            "recorded. Resume under the recorded name with name (CLI: --name), or "
            "choose a new campaign root for a new campaign."
        )
    if resume and force_rerun:
        raise WorkspaceError(
            "resume (CLI: --resume) and force_rerun (CLI: --force-rerun) ask for "
            "opposite things: resume SKIPS a recorded point and force_rerun REDOES "
            "it. Name one."
        )
    scheduled: list[tuple[SimCase, SolverBuild | None, list[tuple[dict[str, float], str]]]] = []
    #: WHAT A FORCED RE-RUN WILL SUPERSEDE, decided in pass one and executed
    #: AFTER pass two, never during. Pass one's own comment says it touches
    #: nothing, and a supersede inside it left records removed and evidence
    #: archived when a later refusal fired -- a staged-inputs conflict, or any
    #: preflight failure -- with nothing executed (the architecture and
    #: interface lenses, FIX-0212).
    to_supersede: list[tuple[SimCase, list[dict[str, float]], list[str]]] = []
    #: Every point name the caller asked to redo that no recorded point carries.
    unmatched: set[str] = set(force_rerun or ())
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
        # A JOB IS RECORDED UNDER ONE ID, not under its points'. The skip
        # above reads point ids, so without this a recorded job looked
        # entirely unrun and a resume re-ran every point of it, which is
        # the opposite of what resume is for and would spend the seat twice.
        if (
            _is_one_job(campaign, case)
            and len(case_points) > 1
            and _job_run_id(campaign, case) in recorded
        ):
            already = [_job_run_id(campaign, case)]
            # WHICH POINTS THE JOB ACTUALLY RAN, read off its record, and
            # not "all of them because the job id is there". A sweep
            # extended from two angles to three and re-run with resume
            # returned successfully having executed NOTHING: the branch
            # discarded every requested point on the strength of the job
            # id alone, and a user reads that as done. Found by the
            # independent Codex review of `main`, 2026-09-13
            # (GEO-047-C05); `points_ran` is what it is for.
            job = manifest.get(_job_run_id(campaign, case))
            ran = {str(entry.get("tag") or "") for entry in (job.points_ran if job else []) or []}
            remaining = [point for point in case_points if point_name(case, point) not in ran]
            case_points = remaining
            run_ids = [_run_id(campaign, case, point) for point in remaining]
        # A ROW STATING RESTART CONTINUES WHAT IS RECORDED, so its recorded
        # points are its subject and not a fork (GOAL-021, the owner's call of
        # 2026-09-14). Until 0.18.1 such a row, under the campaign that recorded
        # the stopped run, was refused as a fork without `resume` and skipped
        # as done with it, and ran only under another campaign name. A point
        # of it is pending when the most recent record of that point stopped
        # continuably, when nothing records it at all, or when its most recent
        # run FAILED, and in the last two the continuation resolver refuses it
        # by name rather than skipping it in silence (the quality and V&V
        # lenses, closing round). A point whose most recent run finished, or is
        # still in a queue, is done for now, so running the matrix again does
        # not continue a continuation that already completed.
        continuing = _states_restart(case)
        redoing = False
        if already and force_rerun:
            asked = _points_asked_to_redo(campaign, case, force_rerun)
            unmatched -= asked.named
            if asked.points and continuing:
                warnings.warn(
                    f"force_rerun names {', '.join(sorted(asked.named))} of simulation "
                    f"{case.sim_id}, whose row states RESTART. A continuation's records "
                    "are its subject rather than a fork, so it is CONTINUED and not "
                    "superseded; nothing was archived for it.",
                    PyflightstreamWarning,
                    stacklevel=2,
                )
            elif asked.points:
                # THE NAMED POINTS RUN AGAIN, and only those. The narrowing
                # above exists for RESUME -- it drops the points a recorded job
                # already ran, which for a fully run job is all of them -- so a
                # forced re-run that inherited it would archive the evidence and
                # then execute nothing, the very failure this flag exists to be
                # distinguishable from.
                # WHAT IS SUPERSEDED IS WHAT IS RE-RUN, and the two were not the
                # same set. The queue took EVERY recorded id of the case while
                # only the NAMED points were scheduled, so a second recorded
                # point of the same case left the manifest and was never run
                # again: neither kept nor redone, with the only remaining copy
                # the archived one nobody reads. Measured on a campaign
                # recording two points of one case, `force_rerun` given one of
                # them (an independent review from another provider, FIX-0220).
                #
                # A JOB IS INDIVISIBLE, so naming any point of one redoes the
                # WHOLE job: one process ran every point of that row, and
                # re-running a part of it while its record goes would orphan the
                # rest. That is why the points come back from the resolver as
                # every point of the sweep in that case, and why the id taken
                # out of the manifest is the JOB's.
                recorded_here = set(already)
                job = _job_run_id(campaign, case)
                case_points = asked.points
                run_ids = [_run_id(campaign, case, point) for point in case_points]
                if job in recorded_here:
                    superseding = [job]
                else:
                    superseding = [run_id for run_id in run_ids if run_id in recorded_here]
                to_supersede.append((case, list(case_points), superseding))
                redoing = True
                already = [run_id for run_id in already if run_id not in set(superseding)]
                # AND THEY STOP COUNTING AS RECORDED, which is the half the
                # first writing missed. `recorded` is frozen before the loop
                # and `pending` below keeps only the points NOT in it, so
                # clearing `already` alone left every superseded point filtered
                # out: the case was dropped, and the run archived the evidence
                # and executed nothing -- the very failure the paragraph above
                # claims to prevent, one level down (the qa lens, FIX-0212).
                recorded.difference_update(superseding)
                recorded.difference_update(run_ids)
        # A FORCED RE-RUN SKIPS WHAT IT DID NOT NAME, which is the only shape
        # that works on a real matrix. Naming one point to redo says "this one
        # again"; it does not say the other rows are a fork. Refusing them made
        # the flag unusable on any matrix with more than one recorded row --
        # measured by its own test, which could not get past the second case.
        if already and force_rerun and not continuing and not redoing:
            continue
        # A CASE THE FLAG PARTIALLY NAMED IS NOT A FORK. Its unasked recorded
        # points are left exactly as they are -- not re-run, not removed -- so
        # the refusal below, which exists for a re-run nobody asked for, must
        # not fire on them.
        if already and not resume and not continuing and not redoing:
            raise WorkspaceError(
                f"run_id {already[0]!r} is already in the manifest of "
                f"{workspace.root}; re-running a recorded point would fork the "
                "run identity. To REDO it, name it: force_rerun="
                f"[{already[0]!r}] (CLI: --force-rerun {already[0]}), which "
                "archives that record and that point's collected outputs and "
                "then runs it, leaving every point it does not name alone. To "
                "run only the points that are NEW, pass resume=True (CLI: "
                "--resume), which SKIPS the recorded ones and does not re-run "
                "this one."
            )
        if continuing:
            pending = []
            for point, run_id in zip(case_points, run_ids, strict=True):
                latest = _latest_record_of_point(
                    manifest.values(), case.sim_id, point_name(case, point)
                )
                if _restart_point_is_pending(latest):
                    pending.append((point, run_id))
        else:
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
        _check_scheduled_builds(
            campaign,
            executor,
            [(case, build) for case, build, _ in scheduled],
            accept_unregistered_build=accept_unregistered_build,
        )
    if unmatched:
        raise WorkspaceError(
            f"force_rerun names {', '.join(sorted(unmatched))}, which no recorded point "
            f"of this campaign carries in {workspace.root}. A name that matches nothing "
            "is refused rather than passed over, because a forced re-run that quietly "
            "redid nothing reads exactly like one that worked. Name a point by its point "
            "name or by its full run_id, as the manifest spells it."
        )
    # SUPERSEDE HERE, once, with the schedule settled and the preflight passed:
    # every refusal that could still fire has fired, so nothing is archived for
    # a run that will not happen.
    if to_supersede:
        _supersede_recorded_points(workspace, to_supersede)

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
        # FR-95: A STEADY ROW IS ONE JOB. Every point of it
        # goes through one script and one process, because that is what warm
        # start IS: point two begins from point one's converged solution
        # because nothing cleared it. The unsteady run types keep the point
        # path below unchanged, and correctly: a point that marches in time
        # starts from its own initial state and is its own job.
        if _is_one_job(campaign, case) and len(pending) > 1:
            _say(
                f"  -> {_job_run_id(campaign, case)}  [{case.recipe}]  "
                f"{len(pending)} point(s) in one job",
                quiet=quiet,
            )
            record = _execute_sweep(
                campaign=campaign,
                canonical=canonical,
                fs_exe=case_exe,
                fs_version=case_version,
                fs_version_source=case_version_source,
                case=case,
                pending=pending,
                preparation_error=preparation_error,
                inputs_sha256=inputs_sha256,
                staged_geometry=staged_geometry,
                name_from=name_from,
                executor=case_executor,
                workspace=workspace,
                sim_dir=sim_dir,
                assess=assess,
                cold=_is_cold_start(case),
            )
            _say(
                f"     {record.run_id}  {record.status}"
                + (f"  ({record.error})" if record.error else ""),
                quiet=quiet,
            )
            if accept_unregistered_build:
                record = record.model_copy(update={"accept_unregistered_build": True})
            workspace.append_record(record)
            recorded.add(record.run_id)
            records.append(record)
            if record.status.startswith("FAILED"):
                failures.append(record)
            continue
        for point, run_id in pending:
            # FR-96, 0.18.0. A CONTINUATION IS RESOLVED BEFORE ANYTHING IS
            # BUILT, because it changes three things at once: which script
            # the builder writes, which run id the record carries, and what
            # is in the datapoint folder when the solver starts. Resolving
            # it later would mean a run id already printed and a folder
            # already read.
            point_extra: dict[str, object] = {}
            try:
                continuation = resolve_continuation(workspace, case, point, run_id=run_id)
            except (CampaignConfigError, WorkspaceError) as error:
                records.append(
                    RunRecord(
                        run_id=run_id,
                        sim_id=case.sim_id,
                        point=dict(point),
                        fs_version_requested=case_version,
                        package_version=pyflightstream.__version__,
                        script_sha256="",
                        raw_flag=False,
                        # FAILED_SCRIPT, because that is what happened: the
                        # script could not be built. No new status, and no
                        # guessing at one that may not exist.
                        status=RunStatus.FAILED_SCRIPT,
                        error=str(error),
                    )
                )
                continue
            if continuation is not None:
                stamp = datetime.now()
                # THE AUTHOR'S DECISION: archive what the continuation replaces, per
                # datapoint, under a day-and-hour stamp, BECAUSE THERE CAN BE
                # MORE THAN ONE RESTART. It happens before the solver starts,
                # so a continuation never writes into the folder holding the
                # evidence of the run it continues.
                archived = workspace.archive_datapoint(
                    case.sim_id, PointName(point_name(case, point)), stamp=stamp
                )
                # THE ARCHIVED COPY, BY ABSOLUTE PATH. The archive above has just
                # MOVED the saved simulation out of the datapoint folder, and
                # this used to hand the solver the path it had been moved from,
                # relative to a working directory a submitted point does not
                # have, so the script named a file that was no longer there.
                saved = str(continuation["saved"])
                source = (
                    archived / Path(saved).name
                    if archived is not None
                    else workspace.sim_dir(case.sim_id) / saved
                )
                point_extra = {
                    RESTART_FROM_VARIABLE: str(source.resolve()),
                    RESTART_ITERATIONS_VARIABLE: str(continuation["iterations"]),
                }
                run_id = continuation_run_id(run_id, stamp)
                _say(
                    f"  -> continuing {continuation['continues']} for "
                    f"{continuation['iterations']} more step(s)",
                    quiet=quiet,
                )
            # FR-78: the point is named as it STARTS, not when it ends. A
            # forty-point campaign that printed only on completion told a
            # reader nothing about the point currently burning the licence.
            _say(
                f"  -> {run_id}  [{case.recipe}]  building and running",
                quiet=quiet,
            )
            record = _execute_point(
                campaign=campaign,
                canonical=canonical,
                fs_exe=case_exe,
                fs_version=case_version,
                fs_version_source=case_version_source,
                case=case.model_copy(update={"variables": {**case.variables, **point_extra}})
                if point_extra
                else case,
                point=point,
                run_id=run_id,
                recipe=recipe,
                preparation_error=preparation_error,
                inputs_sha256=inputs_sha256,
                staged_geometry=staged_geometry,
                name_from=name_from,
                executor=case_executor,
                workspace=workspace,
                sim_dir=sim_dir,
                assess=assess,
            )
            # And as it ENDS, with the status, so the two lines bracket the
            # wait and a reader can see which point a warning between them
            # belonged to.
            _say(
                f"     {run_id}  {record.status}" + (f"  ({record.error})" if record.error else ""),
                quiet=quiet,
            )
            if accept_unregistered_build:
                record = record.model_copy(update={"accept_unregistered_build": True})
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
        problem = _leave_products(workspace, campaign.matrix_stem)
        if problem is not None:
            warnings.warn(problem, PyflightstreamWarning, stacklevel=2)
        problem = _leave_sweep_table(workspace, campaign.matrix_stem)
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


@dataclass(frozen=True)
class _PointsAskedToRedo:
    """Which points of one case a forced re-run named, and by which names."""

    #: The points themselves, in the case's own sweep order.
    points: list[dict[str, float]]
    #: The caller's spellings that matched, so the caller can tell what did not.
    named: set[str]


def _points_asked_to_redo(
    campaign: Campaign, case: SimCase, asked: Sequence[str]
) -> _PointsAskedToRedo:
    """Resolve the names a forced re-run gave into points of this case.

    A NAME IS A POINT NAME OR A FULL run_id, because those are the two spellings
    a user has in front of them: the refusal prints a `run_id`, and the manifest
    and the folder names carry the point name. Matching is EXACT -- a substring
    match on an identity is how the wrong point gets redone, and a seat is the
    one thing archiving cannot give back.
    """
    wanted = set(asked)
    everything = list(case.sweep.points())
    # A JOB IS INDIVISIBLE, and its id is what the refusal prints for a swept
    # steady row: one job ran every point of the row in one process, so naming
    # it names all of them. A user who reads `sim_2001/sweep` off the refusal
    # and passes it back would otherwise match nothing and be told the name
    # carries no recorded point, which is the opposite of true.
    job = _job_run_id(campaign, case)
    if job in wanted:
        return _PointsAskedToRedo(points=everything, named={job})
    points: list[dict[str, float]] = []
    named: set[str] = set()
    for point in everything:
        name = point_name(case, point)
        run_id = _run_id(campaign, case, point)
        hit = {token for token in (name, run_id) if token in wanted}
        if hit:
            points.append(point)
            named |= hit
    return _PointsAskedToRedo(points=points, named=named)


def _supersede_recorded_points(
    workspace: CampaignWorkspace,
    superseding: Sequence[tuple[SimCase, list[dict[str, float]], list[str]]],
) -> None:
    """Archive what a forced re-run replaces, then take it out of the manifest.

    ONCE PER RUN, AND AFTER THE PREFLIGHT. Pass one of `run_campaign` states
    that it touches nothing, and doing this inside it left records removed and
    evidence archived when a later refusal fired -- a staged-inputs conflict, or
    any preflight failure -- with nothing executed, so recovering meant copying
    the manifest back by hand, which is the thing this flag exists to replace
    (the architecture and interface lenses, FIX-0212).

    ARCHIVED, NEVER DESTROYED. The manifest goes to `archive/` whole before a
    row leaves it, and each point's collected outputs move into that point's own
    `archive/<stamp>/`. A forced re-run says the earlier run answered the wrong
    question, which is not the same as saying its evidence may be thrown away:
    the row that produced it was wrong, and that is exactly the thing somebody
    may need to look at afterwards.
    """
    run_ids = [run_id for _, _, ids in superseding for run_id in ids]
    copied = workspace.supersede_records(run_ids)
    if copied is not None:
        warnings.warn(
            f"force_rerun: the manifest was copied to {copied} before "
            f"{len(run_ids)} record(s) were superseded.",
            PyflightstreamWarning,
            stacklevel=2,
        )
    for case, points, _ in superseding:
        for point in points:
            moved = workspace.archive_datapoint(case.sim_id, PointName(point_name(case, point)))
            if moved is not None:
                warnings.warn(
                    f"force_rerun: the collected outputs of {point_name(case, point)} "
                    f"moved to {moved}.",
                    PyflightstreamWarning,
                    stacklevel=2,
                )


def _run_id(campaign: Campaign, case: SimCase, point: dict[str, float]) -> str:
    """Compose the fixed manifest identity of one campaign point.

    The scheme ``<campaign>/sim_<sim_id>/<point name>`` is identity (0.21.0),
    not presentation: it never goes through the naming template, so
    renaming outputs can never fork or collide run identities.
    """
    return f"{campaign.name}/sim_{case.sim_id}/{point_name(case, point)}"


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
    ratio = _advance_ratio_of(case)
    name = point_name(case, point)
    stem = workspace.naming.render_point(
        campaign=campaign.name,
        sim=case.sim_id,
        point=point,
        mach=case.mach,
        advance_ratio=ratio,
        name=name,
    )
    outputs = [
        workspace.naming.render_output(
            declared,
            campaign=campaign.name,
            sim=case.sim_id,
            point=point,
            mach=case.mach,
            advance_ratio=ratio,
            stem=stem,
            point_name=name,
        )
        for declared in case.outputs
    ]
    return stem, outputs


def _reference_block(case: SimCase) -> dict[str, float] | None:
    """Return the reference block a product row carries, from the case's reference data."""
    reference = case.reference
    if reference is None:
        return None
    moment = reference.moment_point_m or (0.0, 0.0, 0.0)
    block = {"SREF": reference.area, "CREF": reference.length}
    if reference.span_m is not None:
        block["BREF"] = reference.span_m
    block.update({"XMOM": moment[0], "YMOM": moment[1], "ZMOM": moment[2]})
    return block


def _advance_ratio_of(case: SimCase) -> float | None:
    """Return the advance ratio a case states or resolves, for its name; None without one.

    A row stating ADVANCE_RATIO names it directly; a row stating RPM with
    a velocity and a rotor diameter resolves it the way the rotor
    speed does (PFS-2029.19.01, the J field of the standard convention). A case
    that cannot resolve one is a case without a J field, not a refusal:
    the name is presentation, and the run type's own refusals still say
    what a rotor row lacks.
    """
    from pyflightstream.cases.workflows import ADVANCE_RATIO_VARIABLE, RPM_VARIABLE, rotor_speed

    stated = case.variables.get(ADVANCE_RATIO_VARIABLE)
    if stated is not None:
        try:
            return float(stated)
        except (TypeError, ValueError):
            return None
    if case.variables.get(RPM_VARIABLE) is None:
        return None
    try:
        return rotor_speed(case).advance_ratio
    except PyflightstreamError:
        return None


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
    waived_commands : tuple of str
        Commands the point's script emits under an ``allow_broken``
        waiver. Known at plan time, because the dry run builds the same
        script, and reported here so an operator learns the campaign
        leans on a command a probe measured broken BEFORE spending
        solver time rather than from the manifest afterwards. Named
        ``broken_commands`` until 0.13.0 (PFS-2022.01.05); the old name
        still reads, warning from the deprecation ledger, and the
        ``plan.json`` key moved with the field.
    raw : bool
        Whether the point's script used the ``raw()`` escape hatch.
        Same reason.
    march_strategy : str or None
        How the point's unsteady run is marched on its build, ``"actions"``
        or ``"single_march"`` (GOAL-023); None for a steady point or one
        that is BLOCKED.
    """

    run_id: str
    sim_id: str
    point: dict[str, float]
    script_name: str | None
    status: PlanStatus
    error: str | None = None
    waived_commands: tuple[str, ...] = ()
    raw: bool = False
    march_strategy: MarchStrategy | None = None


@dataclass(frozen=True)
class PlannedPointCost:
    """What one point is expected to cost, and what that expectation rests on.

    NAMED FOR THE POINT THAT HAS NOT RUN, because `PointCost` was already
    taken: :class:`pyflightstream.qa.cost.PointCost` has meant one point
    MEASURED on two solver builds since PFS-2018.02 and is exported from
    `pyflightstream.qa`. Two public classes of one name in one package is a
    traceback nobody can read, and this is the one that arrived second
    (the interface lens, 2026-09-11).

    FR-82. Every field but `seconds` and `samples` is READ from the row, the
    mesh and the setup: they are measurements of the thing about to be run. The
    two that are not are marked as such, because the difference between a
    figure a reader can check and a figure fitted from history is the whole
    question when someone is deciding whether to spend a seat.

    Attributes
    ----------
    run_id : str
        The point this row is about.
    panels : int or None
        Mesh size: the ELEMENT COUNT the geometry's mesh block states, which
        one campaign geometry overstates by about a percent (`_mesh_size`
        carries the measurement). None where the geometry states none or
        could not be read. THIS FIELD ONCE HELD THE BOUNDARY COUNT and this
        line once said so; a wing-body read 2 where its mesh states 14266.
    trailing_edges : int or None
        How many of the families the row marks for vorticity drag the
        opened geometry actually carries. ZERO is a measured none; None
        means the geometry could not be read, so the intersection this
        column promises could not be performed at all.
    farfield_layers : int or None
        The farfield layer setting, None when the setup states none.
    viscous_coupling : bool
        Whether viscous coupling is on.
    unsteady : bool
        Steady or unsteady, which is the single largest term in the cost.
    time_iterations : int or None
        Time steps for an unsteady row; None for a steady one.
    processors : int or None
        `SET_MAX_PARALLEL_THREADS`, the number of processors set.
    seconds : float or None
        EXPECTED wall time. None where no comparable run has been recorded.
    samples : int
        How many recorded runs the estimate was fitted from. ZERO means the
        estimate is absent rather than uncertain, and the table prints
        `unknown` rather than a number.
    basis : str
        One sentence naming what the estimate rests on, carried into the
        report so the figure is never read without it.
    """

    run_id: str
    panels: int | None
    trailing_edges: int | None
    farfield_layers: int | None
    viscous_coupling: bool
    unsteady: bool
    time_iterations: int | None
    processors: int | None
    seconds: float | None
    samples: int
    basis: str


def _mesh_size(geometry) -> int | None:
    """Return the element count the geometry's mesh block states, or None (FR-82).

    FR-82's "tamanho da malha", read by the layer that owns the `.fsm`
    format rather than parsed a second time here. What the number is, and
    the percent it can be off by, is documented at
    :func:`pyflightstream._fsm.element_count`; nothing does arithmetic on it.
    """
    from pyflightstream._fsm import element_count

    return element_count(geometry)


def _marked_trailing_edges(case) -> int | None:
    """How many boundaries the row marks for vorticity drag (FR-82).

    Read from the row's own statement and the geometry's inventory rather
    than from a rendered script, because the plan must not build a script
    twice to fill a column of a table; the two agree because they read the
    same two things the builder does.

    THE SELECTION IS `solver.vorticity_drag_families`, family NAMES, and
    the builder leaves out the families the opened geometry does not carry
    (PFS-2030.03.03). The first two writings of this column read
    `VORTICITY_DRAG_BOUNDARIES` off the row's variables and then
    `solver.vorticity_drag_boundaries`; neither exists, so the column
    reported 0 for every row in the table and a reader had no way to tell
    that from a campaign marking none.

    A row marking none answers 0, which is then a measurement.
    """
    families = getattr(getattr(case, "solver", None), "vorticity_drag_families", None)
    if not families:
        return 0  # a measured none: the row marks no family
    inventory = None
    if case.geometry is not None:
        try:
            from pyflightstream._fsm import boundary_names

            inventory = boundary_names(case.geometry)
        except Exception:
            inventory = None
    if not inventory:
        # NONE, AND NOT THE ROW'S OWN COUNT. This returned `len(families)`
        # unintersected, which is a different quantity printed in the same
        # cell with nothing to tell the two apart -- while `mesh` printed
        # `-` for that same unreadable geometry, so one failure had two
        # answers in one row (the technical writing lens, 2026-09-11).
        return None
    carried = {name.casefold() for name in inventory}
    return len([name for name in families if str(name).casefold() in carried])


def _recorded_is_unsteady(record: dict) -> bool:
    """Whether a recorded run was unsteady, by the fact it states (FR-82).

    The record's own `recipe` answers, and it is the same key the planned
    point is classified by. A record from an older manifest schema states
    none, and only then does this fall back to the proxy that used to be
    the rule: a run carrying a reduction block reduced, and only an
    unsteady run reduces. The fallback is named here rather than left
    looking like the rule, because it is wrong for exactly the case that
    broke it -- an unsteady run nobody planned a reduction for.
    """
    recipe = record.get("recipe")
    if isinstance(recipe, str) and recipe:
        return recipe != "steady"
    return bool(record.get("reductions"))


def _write_probe_points(
    sim_dir: Path, sim_id: str, points: Sequence[tuple[int, float, float, float, str]]
) -> str | None:
    """Write one simulation's probe positions, and name the file (FR-91).

    Parameters
    ----------
    sim_dir : Path
        The simulation folder.
    sim_id : str
        The simulation, which names the file.
    points : sequence
        ``(vertex, x, y, z, frame)`` in creation order, as the builder
        recorded them while emitting each point.

    Returns
    -------
    str or None
        The path relative to ``sim_dir``, or None when the row placed no
        probe point, which is every row that declares none and every row
        whose entry cites a points file the user wrote.

    Notes
    -----
    IDEMPOTENT BY CONSTRUCTION AND NOT BY A GUARD. Every point of a sweep
    writes this same path, and a probe layout is the artifact's and the
    row's rather than the point's, so the bytes are the same each time.
    The alternative -- one file per point -- would put a hundred identical
    files in the folder and say the layout depends on the angle of attack.
    """
    import csv

    from pyflightstream.cases.workflows import PROBE_POSITION_COLUMNS, PROBE_PROFILE_DIR

    if not points:
        return None
    relative = f"{PROBE_PROFILE_DIR}/{sim_id}_probe_points.csv"
    target = sim_dir / relative
    # A USER'S FILE MAY BE IN THIS FOLDER TOO. A cited survey (FR-80) is read
    # where it lives, under the workspace's `inputs/profiles/`, and is not
    # staged here; but a user may still have put a file of this exact name in
    # the simulation's `profiles/`, and it would have been overwritten without
    # a word. Destroying user input is not a thing to do quietly, and a
    # refusal naming both the file and the fix costs one rename (the
    # interface, architecture and verification lenses, 2026-09-11).
    if target.is_file():
        existing = target.read_text(encoding="utf-8", errors="replace").splitlines()
        header = existing[0].strip() if existing else ""
        # AN EMPTY FILE IS NOT THIS WRITER'S EITHER. The guard read
        # `if header and ...`, so a file with no first line, or a blank one,
        # fell through and was overwritten in silence while the message above
        # and the page both said it would not be (the technical writing lens,
        # round two, 2026-09-11). The absolute is made TRUE rather than the
        # sentence softened: the one file this writer may replace is one
        # carrying its own header.
        if header != ",".join(PROBE_POSITION_COLUMNS):
            raise PyflightstreamError(
                f"{target} already exists and is not a probe positions file "
                f"(its first line reads {header!r}, empty if the file is, and "
                f"this writer's is "
                f"{','.join(PROBE_POSITION_COLUMNS)!r}). This is where the package "
                "records where it put this simulation's probe points, and it will "
                "not overwrite a file it did not write. Rename the points file "
                f"your artifact cites, or rename simulation {sim_id!r}."
            )
    target.parent.mkdir(parents=True, exist_ok=True)
    # THROUGH `csv`, not through an f-string. A frame name carrying a comma,
    # a quote or a newline produced a row the reader silently dropped, and
    # the probe table then showed empty coordinates with nothing recorded.
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(PROBE_POSITION_COLUMNS)
        writer.writerows(points)
    return relative


def _recorded_costs(workspace) -> list[dict]:
    """Every recorded point that carries a wall time, as plain mappings.

    The model's whole training set. A workspace that has run nothing produces
    an empty list, and every estimate below then reports `samples = 0`, which
    the table prints as `unknown` rather than as a number.
    """
    # READ THE MANIFEST BY ITS OWN READER, and let a missing FILE be the only
    # empty answer. The first version called `workspace.records()`, which does
    # not exist, inside a bare `except Exception` -- so an AttributeError read
    # as "this workspace has run nothing" and every estimate came back
    # `unknown` against a workspace holding three recorded points. An
    # instrument that reports nothing when it cannot run is the failure this
    # estate keeps paying for, so the narrow catch is the file's absence and
    # nothing else.
    if not workspace.manifest_path.is_file():
        return []
    records = workspace.read_manifest()
    out = []
    for record in records:
        data = record if isinstance(record, dict) else record.model_dump(mode="json")
        seconds = data.get("wall_time_s")
        if isinstance(seconds, (int, float)) and seconds > 0:
            out.append(data)
    return out


def estimate_point_cost(
    case,
    *,
    run_id: str,
    recorded: list[dict],
    steps_by_run: dict[str, int | None] | None = None,
) -> PlannedPointCost:
    """Table one point's cost, and fit its time from comparable recorded runs.

    FR-82. EVERY FIGURE BUT THE TIME IS A MEASUREMENT of the row, the mesh and
    the setup. The time is an extrapolation and the row says so, carrying the
    number of samples it was fitted from and one sentence naming the basis.

    COMPARABLE MEANS THE SAME RUN TYPE, because steady and unsteady differ by
    more than any other term: an unsteady point runs its solve once per time
    step. Within a run type the fit is linear in the work the point asks for,
    which is the time steps for an unsteady row and one solve for a steady one.

    THERE IS NO PROCESSOR TERM, and this sentence once said there was. The
    processor count is READ and PRINTED so a reader can see it differ between
    rows, and it is not multiplied into anything: the fit is linear in the
    time steps and in nothing else, which is what the requirement says one
    page away (the technical writing lens, 2026-09-11).

    IT IS DELIBERATELY A CRUDE MODEL and the docstring says so rather than
    the code implying otherwise. A fuller scalability study is planned and
    will calibrate it; until then the instruction is to estimate from
    whatever the workspace already holds, so a reader gets a number with
    its sample size attached, or no number at all.
    """
    solver = getattr(case, "solver", None)
    unsteady = case.recipe != "steady"
    from pyflightstream.cases.workflows import time_steps_of

    iterations = time_steps_of(case)

    # PROCESSORS: `max_threads` on the solver settings, which is what
    # `SET_MAX_PARALLEL_THREADS` is emitted from. The first version read a
    # variable key no row writes and reported a dash for every point.
    processors = getattr(solver, "max_threads", None)
    if not isinstance(processors, int):
        processors = None

    # MESH SIZE, and this column read the BOUNDARY COUNT until it was checked
    # against a real geometry: `boundary_names` returns names, so a wing-body
    # read 2 and a rotor sector 3. The mesh block states its size on the line
    # right after `$MESH_START$`, which is 14266 for that same wing-body.
    panels = _mesh_size(case.geometry) if case.geometry else None

    # TRAILING EDGES: counted from the script the plan already builds, because
    # the marked edges are the boundaries of `SET_VORTICITY_DRAG_BOUNDARIES`
    # and no row carries them as a variable. Counting a key nobody writes
    # reported zero for every point, which reads as a measurement of none.
    trailing = _marked_trailing_edges(case)

    # THE FIT. Comparable runs are those of the same run type; the work a point
    # asks for is its time steps, or one solve for a steady row.
    #
    # THE RUN TYPE IS READ FROM THE RECORD'S OWN `recipe`, which is the same
    # fact the point is classified by three lines above, so both ends of the
    # comparison ask one question. The first writing asked a PROXY -- does the
    # record carry a reduction block -- which is true of an unsteady run until
    # it is not: a run whose reductions were never planned carries a null
    # there, read as STEADY, and a 180 second unsteady run then moved every
    # steady estimate in the table.
    same = [r for r in recorded if _recorded_is_unsteady(r) == unsteady]
    seconds = None
    basis = (
        "no recorded run of this run type in this workspace, so no estimate is "
        "offered rather than one with no basis"
    )
    rates = []
    unknown = 0
    for record in same:
        if unsteady:
            # THE SAMPLE'S OWN WORK, and it is NOT read off the manifest's
            # reductions: a recorded run whose reductions were skipped
            # carries a null step count there, and reading that as ONE
            # SOLVE made the rate 36 times too large on the reference rotor point.
            # The plan resolved the step count of every point it holds, and
            # a recorded run of a point still in the matrix is that point,
            # so the map answers; a record of a point that has left the
            # matrix stays unknown.
            steps = (steps_by_run or {}).get(record.get("run_id"))
            if not isinstance(steps, int) or steps <= 0:
                unknown += 1
                continue
            work = float(steps)
        else:
            work = 1.0
        rates.append(float(record["wall_time_s"]) / work)
    samples = len(rates)
    if rates:
        rate = sum(rates) / len(rates)
        work = float(iterations) if unsteady and iterations else 1.0
        seconds = round(rate * work, 1)
        dropped = (
            ""
            if not unknown
            else (
                f" {unknown} further recorded run(s) state no step count and were "
                "left out rather than counted as one step."
            )
        )
        # THE MECHANISM NAMED IS THE ONE THAT ACTED. Both run types were
        # told "linear in the time steps the point asks for", and a steady
        # row asks for none: its work is one solve, fixed. An operator
        # message that names a mechanism which did not act is the defect
        # this estate treats as worst, because it reads as current.
        how = (
            "linear in the time steps the point asks for"
            if unsteady
            else "one solve per recorded run, which is what a steady row asks for"
        )
        basis = (
            f"fitted from {samples} recorded "
            f"{'unsteady' if unsteady else 'steady'} run(s) of this workspace, "
            f"{how}. It is a crude model "
            "pending a scalability study and is not a measurement of "
            f"this point.{dropped}"
        )
    elif same:
        basis = (
            f"the {len(same)} recorded "
            f"{'unsteady' if unsteady else 'steady'} run(s) of this workspace state "
            "no step count, so none of them calibrates a per-step rate and no "
            "estimate is offered rather than one fitted to a guess"
        )
    return PlannedPointCost(
        run_id=run_id,
        panels=panels,
        trailing_edges=trailing,
        farfield_layers=getattr(solver, "farfield_layers", None),
        viscous_coupling=bool(getattr(solver, "viscous_coupling", False)),
        unsteady=unsteady,
        time_iterations=iterations,
        processors=processors,
        seconds=seconds,
        # THE SAMPLES THAT ACTUALLY ENTERED THE FIT, never the comparable
        # runs found: a row reporting `unknown` beside a sample count is a
        # row whose reader cannot tell which of the two numbers to believe.
        samples=samples,
        basis=basis,
    )


def point_costs(
    plan: CampaignPlan, cases_by_sim_id: Mapping[str, object], workspace
) -> list[PlannedPointCost]:
    """One cost row per planned point (FR-82).

    Parameters
    ----------
    plan : CampaignPlan
        The plan whose points are to be tabled.
    cases_by_sim_id : mapping
        The resolved case, KEYED ON THE SIMULATION ID and not on the run id.
        The name carries the key because choosing the other one produces an
        empty result and no refusal. A point whose simulation is absent gets
        no row rather than a row of blanks.
    workspace : CampaignWorkspace
        Where the recorded wall times are read from.

    Returns
    -------
    list of PlannedPointCost
        In plan order.

    Notes
    -----
    THE POINT IS FILLED IN, exactly as the campaign loop fills it before it
    builds a script. A swept row states ``ADVANCE_RATIO: sweep`` and the
    VALUE is the point's, so the un-filled row names no rotor speed and its
    clock reported a blank; the column that was asked for is the per-POINT
    cost, and a row is not a point.

    THE STEP COUNT OF EVERY POINT IS RESOLVED ONCE and handed to the fit, so
    a RECORDED run of one of these points can be weighed by the work it did.
    Read off the manifest instead, it is null for every run whose reductions
    were skipped, and the rate comes out by the factor of the steps: the
    reference rotor point was tabled at 7013.5s against a recorded run of
    194.8s of that same point.
    """
    from pyflightstream.cases.workflows import time_steps_of

    recorded = _recorded_costs(workspace)
    filled = {
        entry.run_id: case_at_point(cases_by_sim_id[entry.sim_id], entry.point)
        for entry in plan.points
        if entry.sim_id in cases_by_sim_id
    }
    steps_by_run = {run_id: time_steps_of(case) for run_id, case in filled.items()}
    return [
        estimate_point_cost(case, run_id=run_id, recorded=recorded, steps_by_run=steps_by_run)
        for run_id, case in filled.items()
    ]


#: What `_elide` puts in place of the characters it drops.
MARKER = "..."


def _elide(text: str, width: int) -> str:
    """Shorten a run id to `width`, keeping its END and marking the cut.

    FROM THE LEFT, because the left of a run id is the campaign and the
    simulation, which every row of one table shares, and the right is the
    point, which is the only thing that tells two rows apart. Truncated from
    the right with no marker, as this did until 2026-09-11, a J sweep whose
    campaign name is one character longer than the example renders every row
    with the same label and says nothing about it (the interface lens).
    """
    if len(text) <= width:
        return text
    # THE RESULT IS NEVER LONGER THAN THE WIDTH IT WAS GIVEN. Without this,
    # a width of three or less made `text[-(width - 3):]` a slice from zero or
    # from the right of the string, and the marker was prepended to the WHOLE
    # id: measured at 47 characters for a width of 3. Unreachable from the
    # table today, which fixes the width at 38, and unbounded is the half that
    # gets reached later (the QA lens, round two, 2026-09-11).
    if width <= len(MARKER):
        return text[-width:] if width > 0 else ""
    return MARKER + text[-(width - len(MARKER)) :]


def format_cost_table(costs: list[PlannedPointCost]) -> str:
    """Render the cost table FR-82 asks for, with its basis under it."""
    header = (
        f"{'point':38} {'mesh':>8} {'TEs':>5} {'layers':>7} {'visc':>5} "
        f"{'type':>9} {'steps':>7} {'procs':>6} {'expected':>10} {'samples':>8}"
    )
    rows = [header, "-" * len(header)]
    for cost in costs:
        expected = "unknown" if cost.seconds is None else f"{cost.seconds:.1f}s"
        rows.append(
            f"{_elide(cost.run_id, 38):38} "
            f"{'-' if cost.panels is None else cost.panels:>8} "
            f"{'-' if cost.trailing_edges is None else cost.trailing_edges:>5} "
            f"{'-' if cost.farfield_layers is None else cost.farfield_layers:>7} "
            f"{'yes' if cost.viscous_coupling else 'no':>5} "
            f"{'unsteady' if cost.unsteady else 'steady':>9} "
            f"{'-' if cost.time_iterations is None else cost.time_iterations:>7} "
            f"{'-' if cost.processors is None else cost.processors:>6} "
            f"{expected:>10} {cost.samples:>8}"
        )
    if costs:
        rows.append("")
        rows.append("EXPECTED TIME IS AN EXTRAPOLATION AND NOT A MEASUREMENT:")
        # ONE LINE PER DISTINCT BASIS, in the order the rows appear. The
        # first writing printed `costs[0].basis` under the whole table, so
        # a table holding a steady row and an unsteady one said "fitted
        # from 2 recorded steady run(s)" under both: a false sentence
        # about the unsteady row, and one that reads as a measurement.
        seen: list[tuple[bool, str]] = []
        for cost in costs:
            key = (cost.unsteady, cost.basis)
            if key not in seen:
                seen.append(key)
        for unsteady, basis in seen:
            rows.append(f"  {'unsteady' if unsteady else 'steady'} rows: {basis}")
    return "\n".join(rows)


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
        Where the JSON summary was written: ``post/<matrix>/plan.json``
        for a campaign converted from a run matrix, ``plan.json`` in the
        campaign root otherwise (PFS-2031.04); None when writing was
        disabled.
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
    #: Where the campaign name came from, ``directory`` or ``option`` (PFS-2029.03.01).
    campaign_name_from: str | None = None
    plan_file: Path | None = None
    build_groups: dict[str, list[str]] = field(default_factory=dict)
    #: FR-82. One row per point when the caller asked for the cost table,
    #: empty otherwise. Filled by :func:`point_costs` where the resolved
    #: cases are; a caller re-resolving the matrix to find them would be
    #: re-deriving state this object already holds.
    #:
    #: LAST, and that position is the fix for a break this field caused.
    #: Put above `campaign_name_from` it forced `points` to lose its own
    #: default, so `CampaignPlan(campaign=..., fs_version=...)` -- a public
    #: constructor call that worked in every release -- raised TypeError.
    #: The architecture and interface lenses both caught it (2026-09-11).
    costs: list[PlannedPointCost] = field(default_factory=list)

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
        waiving = [entry for entry in self.points if entry.waived_commands]
        if waiving:
            commands = sorted({name for entry in waiving for name in entry.waived_commands})
            lines.append(
                f"  {len(waiving)} point(s) waive a command recorded broken: {', '.join(commands)}"
            )
        unvalidated = [entry for entry in self.points if entry.raw]
        if unvalidated:
            lines.append(f"  {len(unvalidated)} point(s) use the raw() escape hatch")
        return "\n".join(lines)


#: FR-97: `plan` is mandatory and `run` does
#: not release without one. The plan is the receipt AND the confirmation.
#: WHAT PLAN ACTUALLY DOES, and it named two things it does not until
#: 2026-09-13: an archive preview and a confirmation. This is the one piece
#: of prose that has to be exactly right, because the user is stopped and
#: reading it, and a refusal that describes a tool by something other than
#: what it does teaches them not to trust the next one (the interface lens).
PLAN_REQUIRED_MESSAGE = (
    "no plan for this matrix, and since v0.17.0 a run needs one. Run "
    "`pyfs-matrix plan <matrix>` first: it pre-flights every point without "
    "spending any solver time, reports which are blocked and which are already "
    "recorded, and writes the receipt this refusal is asking for. Add --cost for "
    "what the run is expected to cost."
)


def plan_receipt_error(
    workspace: CampaignWorkspace, matrix_path: str | Path | None, matrix_stem: str | None
) -> str | None:
    """Return why this run may not proceed on the plan it has, or None.

    THREE ANSWERS, and the third is the one the pin exists for:

    * no matrix: a campaign authored in Python is not planned through a
      file and this gate does not apply to it.
    * no plan file: refused, naming the command that writes one.
    * a plan whose ``matrix_sha256`` is not the matrix on disk: refused,
      because the plan measured a different study. A plan that predates
      the pin carries None and is refused the same way, which is right:
      it cannot say what it read.
    """
    if matrix_path is None:
        return None
    plan_file = workspace.plan_dir(matrix_stem) / "plan.json"
    if not plan_file.is_file():
        return f"{PLAN_REQUIRED_MESSAGE} Expected it at {plan_file}."
    try:
        payload = json.loads(plan_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return f"the plan at {plan_file} cannot be read: {error}. {PLAN_REQUIRED_MESSAGE}"
    planned = payload.get("matrix_sha256")
    current = _file_digest(matrix_path)
    if planned is None:
        return (
            f"the plan at {plan_file} does not say which matrix it measured, so it "
            f"cannot be shown to be about this one. {PLAN_REQUIRED_MESSAGE}"
        )
    if planned != current:
        return (
            f"the matrix changed since it was planned: the plan at {plan_file} measured "
            f"{planned[:12]} and {Path(matrix_path).name} is {str(current)[:12]} now. "
            "Plan it again; a plan that measured another study is not a plan for this "
            "one."
        )
    return None


def plan_campaign(
    campaign: Campaign,
    workspace: CampaignWorkspace,
    *,
    recipes: dict[str, ScriptRecipe] | None = None,
    write_plan: bool = True,
    name_from: str | None = None,
    builds: Mapping[str, SolverBuild] | None = None,
    versions: Mapping[str, str] | None = None,
    matrix_path: str | Path | None = None,
    accept_unregistered_build: bool = False,
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
        Write the JSON summary as ``plan.json``, under ``post/<matrix>/``
        for a campaign converted from a run matrix and in the campaign
        root otherwise (overwritten on each call; a convenience report,
        never an identity source). Default True.
    builds : mapping of str to SolverBuild, optional
        As in :func:`run_campaign`, and pre-flighting is where it earns
        its keep: a case sent to a second build has its dry-run script
        validated against THAT build's version, so a command the second
        installation does not carry blocks the point here rather than
        failing after the first one has already run. A case naming a
        build the mapping does not carry is refused, exactly as the
        campaign loop refuses it, so the pre-flight cannot pass a
        configuration the run will reject.
    versions : mapping of str to str, optional
        Per simulation id, the version its scripts are emitted under,
        for a pre-flight that binds no executable: ``plan_matrix`` and
        ``run_matrix`` both read it off the build registry for the build
        each row named (``_row_versions``), so a row naming a second build
        has its dry-run script validated against that build's grammar
        away from the licensed machine (the residual PFS-2009.05 left,
        closed on the plan path 2026-09-09 as .05.01 and on the run path
        the same day as .05.02: a row on 26.123 in a matrix whose default
        is 26.120 was BLOCKED for a command 26.120 lacks and 26.123
        carries).
        ``builds`` wins where both name a build.

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
        if build is not None:
            case_version = build.fs_version
        elif versions is not None and case.sim_id in versions:
            case_version = versions[case.sim_id]
        else:
            case_version = campaign.fs_version
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
        plan_file = workspace.plan_dir(campaign.matrix_stem) / "plan.json"
        payload = {
            "campaign": campaign.name,
            "campaign_name_from": name_from,
            "fs_version": canonical,
            "package_version": pyflightstream.__version__,
            "build_groups": groups,
            "points": [{**asdict(entry), "status": str(entry.status)} for entry in points],
            # FR-97: WHICH MATRIX THIS PLAN MEASURED. A
            # mandatory plan that does not say is satisfied by a stale one,
            # and then "plan, edit the matrix, run" passes a gate that read
            # a different study. None when the campaign was authored in
            # Python and has no matrix to pin to; `run` asks for a plan
            # only where a matrix exists.
            "matrix_sha256": _file_digest(matrix_path) if matrix_path else None,
            # 0.21.0: plan launches no solver, so the flag changes no check here;
            # it is recorded so the plan rehearses the command line run executes.
            "accept_unregistered_build": accept_unregistered_build,
        }
        plan_file.parent.mkdir(parents=True, exist_ok=True)
        plan_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return CampaignPlan(
        campaign=campaign.name,
        fs_version=canonical,
        campaign_name_from=name_from,
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
    point_case = case_at_point(case, point, outputs=outputs)
    # THE PRE-FLIGHT RESOLVES A CONTINUATION, exactly as the run does, and the
    # reason is that a rehearsal which refuses what the run accepts is not a
    # rehearsal. A row stating RESTART carries no saved file and no step count
    # of its own: both come from the record it continues, and the builder is a
    # pure function of its case, so without this the builder was handed a
    # RESTART row with nothing resolved, raised, and the point was reported
    # BLOCKED. Since 0.17.0 a run REQUIRES a plan, so the release's headline
    # feature was unreachable through its own documented sequence: plan, then
    # run. Found by the architect lens of the 0.18.0 release round on
    # 2026-09-14, which named the command that settles it and could not run it.
    #
    # IT RESOLVES AND DOES NOT ARCHIVE. The archive belongs to the run, which
    # is about to replace the outputs; a pre-flight that moved them would
    # spend a destructive act on a rehearsal, and `plan` promises to spend
    # nothing.
    #
    # A POINT WHOSE LATEST RUN FINISHED, OR IS STILL QUEUED, IS RECORDED, not
    # blocked: a RESTART row names the points it continues, and once a
    # continuation has completed there is nothing left to continue. A point
    # whose latest run FAILED goes on to the resolver, which refuses it by
    # name, so the plan reports it BLOCKED with the reason instead of recorded.
    restarting = _states_restart(case)
    if restarting:
        latest = _latest_record_of_point(
            workspace.read_manifest(), case.sim_id, point_name(case, point)
        )
        if not _restart_point_is_pending(latest):
            return PointPlan(**base, script_name=script_name, status=PlanStatus.ALREADY_RECORDED)
    try:
        rehearsed = resolve_continuation(workspace, case, point, run_id=run_id)
    except (WorkspaceError, CampaignConfigError) as error:
        return PointPlan(
            **base, script_name=script_name, status=PlanStatus.BLOCKED, error=str(error)
        )
    if rehearsed is not None:
        point_case = point_case.model_copy(
            update={
                "variables": {
                    **point_case.variables,
                    # Where the file is NOW, absolutely: the rehearsal archives
                    # nothing, so the run's archived path does not exist yet.
                    RESTART_FROM_VARIABLE: str(
                        (workspace.sim_dir(case.sim_id) / str(rehearsed["saved"])).resolve()
                    ),
                    RESTART_ITERATIONS_VARIABLE: str(rehearsed["iterations"]),
                }
            }
        )
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
    waived = tuple(use.command for use in script.waived_commands)
    if run_id in recorded and not restarting:
        return PointPlan(
            **base,
            script_name=script_name,
            status=PlanStatus.ALREADY_RECORDED,
            waived_commands=waived,
            raw=script.raw_flag,
            march_strategy=script.march_strategy,
        )
    return PointPlan(
        **base,
        script_name=script_name,
        status=PlanStatus.READY,
        waived_commands=waived,
        raw=script.raw_flag,
        march_strategy=script.march_strategy,
    )


def _output_collision(
    campaign: Campaign, case: SimCase, workspace: CampaignWorkspace
) -> str | None:
    """Return why ONE point's output names collide, or None.

    A point's declared outputs are collected into that point's own
    folder under the name
    :func:`pyflightstream.workspace.collection_name` gives them, so two
    outputs of one point that collect to a single name overwrite each
    other's evidence while the manifest lists the survivor for both
    (incident INC-20260723-2113-pyflightstream). The check renders the
    names the way the loop will, so it judges the actual collision
    rather than the presence of a particular placeholder.

    ACROSS POINTS THE COLLISION MOVED DOWN A LAYER AND IS STILL
    CHECKED HERE (FR-92). Until 0.16.0 two points exporting
    ``loads.txt`` destroyed each other IN THE SHARED COLLECTION FOLDER,
    and that half is genuinely gone: each point collects into
    ``datapoints/DP-<point>/`` and nothing on disk overwrites anything.
    THEY STILL MEET IN ``post/products.py``, which keys every per-point
    product by the STEM of the loads file name. Measured on two points
    each in their own folder both declaring ``loads.txt`` and
    ``loads_plots.txt``: one ``probes/loads_plots.csv`` naming BOTH runs
    while holding the last point's data, and a superfile whose runs list
    records one point twice, so the other is gone from the product
    record (the quality lens, 2026-09-11).

    So the check stays, and its REASON is what changed: it is about the
    products a name will collide in, not about the folder it lands in.
    Making those product names carry the point tag the folder already
    carries would let it be lifted, and that is registered rather than
    taken on release eve, because it moves file names a user's
    downstream scripts read.

    The within-one-point half is the half that kept being got wrong
    (PLN-20260802-1904). Two inputs planned as READY and died at
    collection, each after the solver had run and each costing a
    licensed seat:

    * ``["loads.txt", "loads.txt"]`` on a single point, because the
      old check skipped a repeat carrying the same point tag as itself;
    * ``["a/loads.txt", "b/loads.txt"]`` on one point, because it keyed
      on the DECLARED string, where those differ, while collection keys
      on the base name, where they do not.

    The keying is the shared function, so the plan-time answer and the
    collect-time answer cannot disagree again.
    """
    seen: dict[str, str] = {}
    for point in case.sweep.points():
        try:
            _, names = _point_names(campaign, case, point, workspace)
        except NamingTemplateError:
            return None  # the rendering error is reported by the point itself
        tag = point_name(case, point)
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
                    f"collect to {SIM_DATAPOINTS_DIR}/{datapoint_dir_name(PointName(tag))}/"
                    f"{collected}: collection moves each output under its "
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
                    f"the same collected name {collected} for point {seen[collected]}: "
                    "each point collects into its own folder, so nothing is "
                    "overwritten there, and what two points sharing one collected "
                    "name lose is the ability to be told apart anywhere downstream. "
                    "MEASURED FOR THE LOADS TABLE, which is the case that costs "
                    "data: a point's post-processing products are named after its "
                    "loads file's stem, so two points produce ONE table naming both "
                    "runs while holding one point's, and a superfile recording one "
                    "point twice. The check is applied to EVERY declared name rather "
                    "than only the loads one, deliberately and knowing that some "
                    "kinds produce no product: which kind a name turns out to be "
                    "depends on the recipe that exports it, and refusing a name that "
                    "would have been safe costs a rename while allowing one that is "
                    "not costs a run. Name the outputs per point, for example "
                    "'loads_{point}.txt', and export case.outputs[i] from the recipe"
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


def _say(message: str, *, quiet: bool = False) -> None:
    """Print one progress line to stderr, immediately.

    FR-78. STDERR is decided before the first line was written: everything this
    run prints that a caller CONSUMES is on stdout, so a progress line there
    would break a pipeline reading records.

    THE STREAM IS RESOLVED AT CALL TIME, not bound at import. Binding it once
    at module level captured the interpreter's ORIGINAL stderr, so anything
    that replaces `sys.stderr` afterwards -- a test harness, a caller
    redirecting output, a notebook -- saw nothing at all while the lines went
    somewhere else. The first version did that and its own test caught it.

    `flush=True` is the requirement and not a precaution: a stream that is not
    a terminal is block-buffered, so a campaign redirected to a file would
    print its first line when the last point was done, which is the silence
    this requirement exists to end.
    """
    if quiet:
        return
    print(message, file=sys.stderr, flush=True)


#: The tag a JOB's run id ends with, where a point's run id ends with its
#: point tag. Reused rather than invented: 0.16.0 already names the
#: per-polar product tables by the point convention with the swept
#: variable written literally as ``sweep``, so a reader has met this token
#: and it reads correctly, naming a sweep rather than a point.
JOB_TAG = "sweep"

#: FR-95. How bad a point's outcome is, worst LAST, for folding the points
#: of one job into the job's own status.
#:
#: IT IS A STATED ORDER AND NOT A PREFERENCE ABOUT WORDS. A job's headline
#: is what a reader triages by, so it has to name the most serious thing
#: that happened rather than the most recent. The order is: converged, then
#: the two that produced numbers and did not reach the answer, then the
#: four failures with the ones that produced nothing usable last. A status
#: missing from this tuple sorts as worse than everything in it, which is
#: the safe direction: a state nobody has classified is not quietly the
#: best one.
_STATUS_SEVERITY: tuple[RunStatus, ...] = (
    RunStatus.CONVERGED,
    RunStatus.SUBMITTED,
    RunStatus.COMPLETED_MAX_ITER,
    RunStatus.WALLTIME_REACHED,
    RunStatus.FAILED_SCRIPT,
    RunStatus.FAILED_EXECUTION,
    RunStatus.FAILED_INCOMPLETE_OUTPUT,
    RunStatus.FAILED_DIVERGED,
)


def _worse_of(left: RunStatus, right: RunStatus) -> RunStatus:
    """Return the more serious of two point outcomes, by :data:`_STATUS_SEVERITY`."""

    def rank(status: RunStatus) -> int:
        try:
            return _STATUS_SEVERITY.index(status)
        except ValueError:
            return len(_STATUS_SEVERITY)

    return right if rank(right) > rank(left) else left


def _job_run_id(campaign: Campaign, case: SimCase) -> str:
    """Return the run id of a JOB, which no one point's tag may end.

    The point tag is run IDENTITY and it ends every ``run_id`` in every
    existing manifest; the rule is enforced at the sweep and carries its
    own incident history. A record covering three points cannot borrow one
    of their tags, so it ends with :data:`JOB_TAG` instead.
    """
    return f"{campaign.name}/sim_{case.sim_id}/{JOB_TAG}"


#: The run type whose points are ONE job since 0.17.0.
ONE_JOB_RECIPE = "steady"


def _is_one_job(campaign: Campaign, case: SimCase) -> bool:
    """Whether this case's points run as one job rather than one each.

    A STEADY ROW OF A MATRIX, and only that. Three conditions, each for
    its own reason:

    * the recipe is the steady run type. A LEGACY row is built by its own
      recipe, which builds one point and knows nothing of a sweep; an
      unsteady point marches in time from its own initial state, so two of
      them in one process would make the second continue the first's clock.
    * the campaign came from a MATRIX. The author's decision of 2026-09-12 is
      about the row the author writes, and a campaign authored in Python is a
      different surface with a contract of its own: thirty-one tier-1 tests
      state that a Python campaign records one point at a time, and widening
      that convention onto them would be a change nobody asked for, made
      silently, to an interface the decision was not about.
    * there is more than one point. One point is one job either way, and
      routing it here would give it a job's run id for no gain and break
      every resume that expects its point tag.

    THE INCONSISTENCY THIS LEAVES IS REAL AND IS RECORDED RATHER THAN
    HIDDEN: the same steady sweep is one job through a matrix and one job
    per point through the Python API. Whether the Python surface should
    follow is a question for the author, and answering it unasked is what
    the second condition exists to prevent.

    A FOURTH CONDITION SINCE 0.21.0: the points differ in ATTITUDE alone. A
    row may now sweep a flow variable, and one warm job cannot run such a
    sweep: the air state is a SETUP command, the solver takes it before it is
    initialised, and the phase guard refuses it after. So a row sweeping MACH,
    REmi, an altitude or any other flow variable is one job per point, each
    with its own fluid block, and the warm sweep stays what the predecessor's
    recipe was: one setup, one initialisation, many angles.
    """
    if not (case.recipe == ONE_JOB_RECIPE and bool(getattr(campaign, "matrix_stem", None))):
        return False
    return not _sweeps_the_flow(case)


def _sweeps_the_flow(case: SimCase) -> bool:
    """Whether this case's sweep moves the air state rather than the attitude.

    Read from the RESOLVED points rather than from the axis name: a row that
    sweeps a flow variable carries one state per point, and a row that sweeps
    an angle carries none. That way a variable that becomes sweepable later
    needs no second list to be added to.
    """
    states = list(case.point_states.values())
    return any(
        state.fluid != states[0].fluid or state.velocity != states[0].velocity
        for state in states[1:]
    )


def _is_cold_start(case: SimCase) -> bool:
    """Whether the row asked for a cold start (FR-95).

    WARM IS THE DEFAULT and this is the opt-out, which follows the
    evidence rather than the safer-looking choice: the predecessor's
    steady recipe never cleared the solver between points and had no
    switch to.
    """
    stated = case.variables.get(COLD_START_VARIABLE)
    if stated is None:
        return False
    return str(stated).strip().upper() in {"TRUE", "ENABLE", "YES", "1"}


def _execute_sweep(
    *,
    campaign: Campaign,
    canonical: str,
    fs_exe: str | Path,
    fs_version: str,
    fs_version_source: str,
    case: SimCase,
    pending: list[tuple[dict[str, float], str]],
    preparation_error: str | None,
    inputs_sha256: dict[str, str],
    staged_geometry: str | None,
    name_from: str | None = None,
    executor: Executor,
    workspace: CampaignWorkspace,
    sim_dir: Path,
    assess: OutcomeAssessor,
    cold: bool,
) -> RunRecord:
    """Take every point of a steady row through ONE process to ONE record.

    FR-95. The shape is the predecessor's own
    steady recipe and the reason it is one record is
    that it is one process: the wall time in this record is a measurement
    rather than a share of one, and a job is what a cluster queues.

    WHAT THE JOB RECORD CARRIES that a point record does not:
    :attr:`RunRecord.job_id` and :attr:`RunRecord.points_ran`, the points in
    the order they ran with the status each ended in. The record's own
    status is the WORST of them, because a job with one diverged point is
    not a converged job.

    WHAT THE PER-POINT FOLDERS DO NOT LOSE: each point still collects into
    its own ``datapoints/DP-<tag>/``. The predecessor already wrote one
    folder per point from inside a single script, so what changed is the
    number of processes and not the number of folders.
    """
    package_commit, package_dirty = package_vcs_state()
    run_id = _job_run_id(campaign, case)
    points = [point for point, _ in pending]
    base: dict[str, object] = {
        "run_id": run_id,
        "sim_id": case.sim_id,
        "point": dict(points[0]),
        # A JOB'S NAME IS ITS SWEEP'S, and it is written to `point_name` as
        # well: the field is what every reader of a record takes the name
        # from, collect included, so a job record that left it empty would
        # be refused as written before 0.21.0 while being one of this
        # version's own. The points it ran carry their own names.
        "point_name": sweep_name(case),
        "sweep_name": sweep_name(case),
        "job_id": run_id,
        "matrix_stem": campaign.matrix_stem,
        "fs_version_requested": canonical,
        "package_version": pyflightstream.__version__,
        "package_commit": package_commit,
        "package_dirty": package_dirty,
        "recipe": case.recipe,
        # A JOB'S RECIPE IS THE RUN TYPE, which has no user function behind
        # it and therefore no source to digest. The field is carried empty
        # rather than left out, so a reader of the manifest sees the same
        # shape on every record.
        "recipe_sha256": None,
        "fs_exe": str(fs_exe),
        "fs_exe_sha256": _file_digest(fs_exe),
        "fs_version_source": fs_version_source,
        "manifest_schema": MANIFEST_SCHEMA,
        "inputs_sha256": dict(inputs_sha256),
        "campaign_name_from": name_from,
        "pproc": case.pproc_id,
        "velocity_requested_m_s": case.velocity,
        "inventory_source": case.inventory_source,
        "motions": [dict(record) for record in case.motions],
        "point_name_template": workspace.naming.point_name,
        "description": case.description or None,
        "mach": case.mach,
        "reference": _reference_block(case),
        # THE SAME PROVENANCE A POINT RECORD CARRIES. A job is one process
        # over several points of ONE row, so every one of these is a
        # property of the row and is the same for all of them; leaving
        # them out made a job record unable to say whether its state was a
        # wind tunnel's or an altitude's, which its own guard reported.
        "flight_condition": dict(case.flight_condition),
        "flight_condition_defaults": dict(case.flight_condition_defaults),
        "flight_condition_defaults_from": case.flight_condition_defaults_from,
        "density_kg_m3": None if case.fluid is None else case.fluid.density_kg_m3,
        "temperature_k": None if case.fluid is None else case.fluid.temperature_k,
        "viscosity_pa_s": None if case.fluid is None else case.fluid.viscosity_pa_s,
        "density_source": None if case.fluid is None else case.fluid.source,
        "reference_length_m": None if case.fluid is None else case.fluid.reference_length_m,
        "waived_commands": [],
        "raw_commands": [entry.model_dump(mode="json") for entry in case.raw_commands],
        "aliases": {name: list(members) for name, members in case.aliases.items()},
        # Both are REQUIRED on a record and both are only known once the
        # script is built, so they carry the empty answer until then: a
        # record that never got as far as a script is a record whose script
        # has no digest and whose raw flag is false, and saying so is not
        # the same as leaving the field out.
        "script_sha256": "",
        "raw_flag": False,
    }
    if preparation_error is not None:
        return RunRecord(**base, status=RunStatus.FAILED_SCRIPT, error=preparation_error)

    # One case per point, differing only in the point and the names it
    # exports; everything the shared preamble reads is the same on all of
    # them, which is what makes them one script.
    point_cases = []
    for point in points:
        try:
            stem, outputs = _point_names(campaign, case, point, workspace)
        except NamingTemplateError as error:
            return RunRecord(**base, status=RunStatus.FAILED_SCRIPT, error=str(error))
        update: dict[str, object] = {"outputs": outputs}
        if staged_geometry is not None:
            update["geometry"] = staged_geometry
        point_cases.append(
            (point, stem, _with_the_profile_s_log(case_at_point(case, point, **update), executor))
        )

    script = Script(version=fs_version)
    try:
        build_steady_sweep([pc for _, _, pc in point_cases], script, cold=cold)
    except Exception as error:  # a build failure is the job's failure
        return RunRecord(
            **base,
            status=RunStatus.FAILED_SCRIPT,
            error=f"{type(error).__name__}: {error}",
        )
    setup = script.solver_setup
    if setup is not None:
        base["solver_setup"] = setup.model_dump(mode="json")
    # THE HOUSE CONVENTION FOR A SWEEP, not a name of this function's own.
    # A per-polar product table is named by the point name with the swept
    # variable written literally as `sweep`, and a job's script is about
    # exactly the same thing, so it is named the same way:
    # P5001-M090AL+sweepBE+000 (0.21.0).
    job_stem = sweep_file_stem(case.sim_id, sweep_name(case))
    script_path, script_sha = workspace.write_script(
        case.sim_id, f"{job_stem}.txt", script.render()
    )
    base["script_path"] = str(Path(script_path).relative_to(sim_dir).as_posix())
    base["script_sha256"] = script_sha
    base["raw_flag"] = script.raw_flag
    base["march_strategy"] = script.march_strategy

    # PYFS-006 ON THE SWEEP PATH, which lost it. `_execute_point` refuses
    # declared outputs that already exist in the simulation folder before
    # the solver runs, because collection asks only whether a declared
    # output EXISTS and cannot tell a file this solver wrote from one that
    # was already there. The sweep path started the solver without it, so
    # after an interrupted run a leftover export was collected and
    # assessed as fresh evidence, and its digest recorded as this run's.
    # Found by the independent Codex review of `main`, 2026-09-13
    # (GEO-047-C03).
    #
    # EVERY POINT'S OUTPUTS, checked before the shared script runs,
    # because one script writes all of them and a refusal after it has
    # started is a refusal that spent the seat.
    stale = sorted(
        {
            name
            for _, _, point_case in point_cases
            for name in point_case.outputs
            if (sim_dir / name).exists()
        }
    )
    if stale:
        return RunRecord(
            **base,
            status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
            error=(
                f"declared output(s) {', '.join(stale)} already exist in the simulation "
                "folder before this job ran, so collecting them would attribute somebody "
                "else's file to this run. Every point of this sweep shares the folder and "
                "one script writes all of them, so this is checked for the whole job "
                "before the solver starts. Archive the simulation (pyfs-workspace archive "
                "<root> <sim_id>) or remove the leftovers, then re-run."
            ),
        )

    # FR-99. THE JOB'S values, not a point's: a steady row is ONE job, so
    # the descriptor names the sweep and carries the row's clock and
    # processor count. `_bind_submission_values` reads them off the case
    # and a local executor has no such method and is handed nothing.
    _bind_submission_values(executor, case, point_cases[0][2])
    result = executor.run_script(script_path, working_dir=sim_dir, timeout_s=case.solver.timeout_s)
    base["argv"] = list(result.argv)
    base["cwd"] = result.cwd
    base["timeout_s"] = result.timeout_s
    base["executor"] = invocation_record(executor, result)
    base["started_at"] = result.started_at
    base["finished_at"] = result.finished_at
    # FR-99, and the same reason as the point path: the descriptor exists
    # before the scheduler is called, so a rejected submission must keep it.
    submitted = _submission_record(executor)
    if result.failed:
        return RunRecord(
            **base,
            status=RunStatus.FAILED_EXECUTION,
            wall_time_s=result.wall_time_s,
            error=result.diagnosis(),
            submission=submitted,
        )
    # FR-99. A SUBMITTED JOB HAS NO OUTPUTS YET. The scheduler has taken
    # the whole sweep and no point of it has run, so every point is
    # pending: the record says SUBMITTED, names where the job went, and
    # carries the points it will run rather than points it ran.
    if submitted is not None:
        return RunRecord(
            **base,
            status=RunStatus.SUBMITTED,
            wall_time_s=None,
            outputs=[],
            # The whole sweep is ONE job and one script, so the declared
            # set is every point's outputs together: the collector waits
            # for the job, not for a point of it.
            submission={
                **submitted,
                "declared_outputs": [name for _, _, pc in point_cases for name in pc.outputs],
                # AND THE SAME SET SPLIT BY POINT, because the two questions
                # are different. The flat list above is what the COLLECTOR
                # WAITS FOR: the whole sweep is one job and one script, so the
                # job is finished when all of it has landed. This mapping is
                # what the collector FILES BY: each point's evidence belongs
                # alone in its own datapoint folder, which is the rule
                # `collect_outputs` states and the rule the local sweep pays
                # two passes to honour. Without it the collector had only the
                # first point's tag to hand and filed every point's exports
                # under it, reintroducing on the cluster path the defect the
                # local path carries a comment about: an assessor reading a
                # sibling point's file and reporting the run against the wrong
                # incidence. Found by the interface lens of the 0.18.0 release
                # round, 2026-09-14.
                "declared_by_point": {
                    point_name(case, point): [str(name) for name in pc.outputs]
                    for point, _, pc in point_cases
                },
                "points_by_tag": {
                    point_name(case, point): dict(point) for point, _, _ in point_cases
                },
            },
            points_ran=[
                {
                    "tag": point_name(case, point),
                    "point": dict(point),
                    "status": str(RunStatus.SUBMITTED),
                }
                for point, _, _ in point_cases
            ],
        )
    base["wall_time_s"] = result.wall_time_s

    # EVERY POINT IS COLLECTED AND ASSESSED, and a point that fails does not
    # stop the ones after it: they have already run, their files are on
    # disk, and throwing them away because a sibling failed would spend the
    # seat twice.
    # TWO PASSES, AND THE ORDER IS THE WHOLE OF IT. Every point of a case
    # writes into the SAME simulation folder, and collection is what moves
    # each point's files into its own datapoint folder. Assessing point one
    # while points two and three are still lying in that folder made the
    # assessor read a file from another operating point and report the run
    # against the wrong incidence: "alpha requested +2.0000, exported ...".
    #
    # So EVERY point is collected first, which empties the shared folder,
    # and only then is any point assessed. The point path never met this
    # because one process wrote one point.
    ran: list[dict] = []
    worst = RunStatus.CONVERGED
    collected_all: list[str] = []
    error_lines: list[str] = []
    collected_by_tag: dict[str, list[str]] = {}
    failed_tags: dict[str, str] = {}
    for point, _stem, point_case in point_cases:
        tag = point_name(case, point)
        try:
            collected_by_tag[tag] = workspace.collect_outputs(
                case.sim_id,
                # ABSOLUTE, as the point path passes them: the names on the
                # case are relative to the execution directory and the
                # collector is handed paths, not names.
                [sim_dir / name for name in point_case.outputs],
                datapoint=PointName(tag),
            )
        except (WorkspaceError, CampaignConfigError) as error:
            failed_tags[tag] = str(error)
    for point, _stem, point_case in point_cases:
        tag = point_name(case, point)
        if tag in failed_tags:
            ran.append(
                {
                    "tag": tag,
                    "point": dict(point),
                    "status": str(RunStatus.FAILED_INCOMPLETE_OUTPUT),
                }
            )
            worst = RunStatus.FAILED_INCOMPLETE_OUTPUT
            error_lines.append(f"{tag}: {failed_tags[tag]}")
            continue
        collected = collected_by_tag[tag]
        assessment = assess(point_case, result, sim_dir)
        collected_all.extend(collected)
        ran.append(
            {
                "tag": tag,
                "point": dict(point),
                "status": str(assessment.status),
                "outputs": list(collected),
                "iterations": assessment.iterations,
                "residual": assessment.residual,
            }
        )
        if str(assessment.status).startswith("FAILED"):
            error_lines.append(f"{tag}: {assessment.error or assessment.status}")
        # THE WORST, BY A STATED ORDER, and it was the LAST failing point
        # until 2026-09-13: each failure simply overwrote the variable, so
        # a sweep whose first point DIVERGED and whose third left an
        # incomplete output recorded the third, and a reader triaging by
        # status was pointed at the wrong point (the QA lens). `points_ran`
        # carried each point's own status either way, so nothing was lost;
        # what was wrong was the job's headline.
        worst = _worse_of(worst, assessment.status)
    base["points_ran"] = ran
    return RunRecord(
        **base,
        status=worst,
        outputs=collected_all,
        outputs_sha256=workspace.output_digests(case.sim_id, collected_all),
        error="; ".join(error_lines) or None,
    )


def _walltime_stop(state_path: Path) -> dict | None:
    """Where the wall-clock watchdog stopped this run, or None if it did not.

    None covers three cases that are all the same answer to the caller: no
    clock on the row, a clock that never fired, and a state file the
    program never got to write. A run that ended for its own reasons is
    not a run the clock stopped, and saying so is the whole value.
    """
    if not state_path.is_file():
        return None
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not state.get("fired"):
        return None
    stopped = state.get("stopped_at")
    return dict(stopped) if isinstance(stopped, dict) else None


def workflow_conventions_for(case: SimCase) -> WorkflowConventions:
    """Return the conventions a builder would have been given for this case.

    The run layer owns these and the clock program needs the same ones the
    export block used, so it asks the same constructor rather than
    rebuilding the names.
    """
    return WorkflowConventions.for_case(case)


#: The statuses a continuation may continue FROM. A run that converged has
#: nothing left to march and a run that failed has no state worth resuming;
#: these two stopped with their outputs written and their step recorded,
#: which is exactly what `restart_iterations` subtracts from.
CONTINUABLE = (RunStatus.WALLTIME_REACHED, RunStatus.COMPLETED_MAX_ITER)


def continuation_run_id(run_id: str, stamp: datetime) -> str:
    """Return the run id of a continuation of ``run_id``.

    THE STAMP GOES BEFORE THE POINT TAG AND NOT AFTER IT, and that is the
    whole of the decision the owner left to this session. FR-95 states that
    the point tag is run IDENTITY and ENDS every ``run_id`` in every
    manifest; a stamp appended after it would break that for every reader
    and every resume that walks a manifest by its tags.

    So a continuation is ``<campaign>/sim_<id>/r<stamp>/<tag>``: a row of
    its own in the manifest, discriminated by the SAME stamp that names the
    folder its predecessor's outputs were archived into, and the tag still
    ends it.

    ONE RECORD PER CONTINUATION, which is the shape the author's archive
    decision pointed at without stating: if the evidence of each continuation lives
    in its own stamped folder, the stamp is already the thing that tells one
    from the next, and a record per continuation costs no new vocabulary.
    The alternative, one record growing segments, would have meant rewriting
    a finished row, which is the thing `append_record` exists to prevent.
    """
    head, _, tag = run_id.rpartition("/")
    return f"{head}/r{stamp.strftime(ARCHIVE_STAMP)}/{tag}"


def resolve_continuation(
    workspace: CampaignWorkspace,
    case: SimCase,
    point: Mapping[str, float],
    *,
    run_id: str,
) -> dict[str, object] | None:
    """Resolve the two facts a continuation needs, from the record it continues.

    None where the row states no ``RESTART``, which is every ordinary row.

    THE ROW SAYS HOW MUCH MORE AND THE MANIFEST SAYS FROM WHAT. Which run
    stopped, where it stopped, and which saved simulation it left are all
    answers the record holds; the builder is a pure function of its case and
    must not go looking for them, so they are resolved here and set on the
    point case as two reserved variables.
    """
    request = parse_restart(case)
    if request is None:
        return None
    tag = point_name(case, point)
    # THE MOST RECENT RECORD OF THE POINT, WHATEVER IT SAYS, and only then is
    # it asked whether it stopped. This read the latest STOPPED record until
    # 0.18.1, so a point whose continuation had since FINISHED was continued
    # again from the run before it, re-marching steps the finished run had
    # already done (GOAL-021, found beside the owner's item 2 measurement).
    previous = _latest_record_of_point(workspace.read_manifest(), case.sim_id, tag)
    if previous is None or previous.status not in CONTINUABLE:
        latest = (
            "records no run of it"
            if previous is None
            else f"records its latest run, {previous.run_id!r}, as {previous.status}"
        )
        failed = previous is not None and previous.status in _FAILED_STATUSES
        remedy = (
            " A failed continuation is not retried: the saved simulation of the stop it "
            "continued is kept under this point's archive/ folder. Find why it failed, "
            "then restore that file and its record by hand, or remove the "
            f"{RESTART_VARIABLE} key to march the point from the start."
            if failed
            else ""
        )
        raise CampaignConfigError(
            f"case {case.sim_id!r} point {tag} states {RESTART_VARIABLE} and this workspace "
            f"{latest}, which is not a run that STOPPED with more to do.{remedy} A continuation "
            "continues a recorded run whose latest status is one of "
            f"{', '.join(str(s) for s in CONTINUABLE)}; run the row once, or remove the "
            f"{RESTART_VARIABLE} key to march it from the start."
        )
    iterations = restart_iterations(request, previous.model_dump(mode="json"))
    saved = next(
        (name for name in previous.outputs if str(name).lower().endswith(SIMULATION_SUFFIX)),
        None,
    )
    if saved is None:
        raise CampaignConfigError(
            f"run {previous.run_id!r} stopped at {previous.status} and collected no saved "
            f"simulation ({SIMULATION_SUFFIX}), so there is no state to reopen. A row whose "
            "post-processing artifact turns the simulation export off cannot be continued; "
            "turn it on and run the row again."
        )
    if not (workspace.sim_dir(case.sim_id) / str(saved)).is_file():
        raise CampaignConfigError(
            f"run {previous.run_id!r} stopped at {previous.status} and recorded its saved "
            f"simulation as {saved}, which is not in {workspace.sim_dir(case.sim_id)}. A "
            "continuation reopens that file, so it cannot start without it; restore it, or "
            f"remove the {RESTART_VARIABLE} key to march the point from the start."
        )
    return {
        "continues": previous.run_id,
        "iterations": iterations,
        "saved": str(saved),
        "form": request.form,
    }


#: Every status a run ends in when it FAILED, read off the enum by name so a
#: failure status added there is covered here without an edit.
_FAILED_STATUSES = tuple(status for status in RunStatus if status.name.startswith("FAILED_"))


def _queued_record_of_point(
    executor, workspace: CampaignWorkspace, sim_id: str, name: str
) -> RunRecord | None:
    """Return a SUBMITTED record of this simulation and point, or None.

    Only a submitting executor is asked: a local point runs to its end before
    the next one starts, so it never meets a job of its own still in a queue.
    """
    if not isinstance(executor, Submitting):
        return None
    for record in workspace.read_manifest():
        if (
            record.sim_id == sim_id
            and record.run_id.endswith(f"/{name}")
            and record.status is RunStatus.SUBMITTED
        ):
            return record
    return None


def _restart_point_is_pending(latest: RunRecord | None) -> bool:
    """Whether a point of a RESTART row goes on to the continuation resolver.

    It does when nothing records it, when its most recent run stopped with
    more to do, and when its most recent run FAILED: the first and the last
    are refused there BY NAME, so no point of a RESTART row is ever skipped
    in silence. It does not when the most recent run finished or is still in
    a queue, because there is nothing to continue yet or any more.
    """
    return latest is None or latest.status in CONTINUABLE or latest.status in _FAILED_STATUSES


def _states_restart(case: SimCase) -> bool:
    """Whether a case's row states RESTART, without raising on a malformed cell.

    A malformed cell is the continuation resolver's to refuse, per point and by
    name; campaign scheduling only needs to know whether the row is one.
    """
    try:
        return parse_restart(case) is not None
    except CampaignConfigError:
        return False


def _latest_record_of_point(
    records: Iterable[RunRecord], sim_id: str, name: str
) -> RunRecord | None:
    """Return the most recent record of one point, in file order, whatever its status.

    A continuation's run id is ``<campaign>/sim_<id>/r<stamp>/<name>``, so the
    point name still ENDS every run id of the point, which is what this reads.
    """
    latest = None
    for record in records:
        if record.sim_id == sim_id and record.run_id.endswith(f"/{name}"):
            latest = record
    return latest


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


def _with_the_profile_s_log(case: SimCase, executor: object) -> SimCase:
    """Return the case as the EXECUTOR's machine writes its log (0.21.0).

    Some clusters abort at ``EXPORT_LOG`` and write their own log beside the
    run; their HPC profile says so, and the builders read the CASE and know
    nothing of a profile. So the decision is written onto the case here, the
    way the command line writes IGNORE_MISSING_FAMILIES, and only the FALSE
    side is ever written: a run on any other machine, or through any other
    executor, renders byte for byte what it rendered before.
    """
    profile = _profile_of(executor)
    if profile is None or profile.export_log:
        return case
    return case.model_copy(update={"variables": {**case.variables, EXPORT_LOG_VARIABLE: "false"}})


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
    name_from: str | None = None,
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
        "point_name": point_name(case, point),
        "sweep_name": sweep_name(case),
        "matrix_stem": campaign.matrix_stem,
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
        # The post-processing artifact the row named (PFS-2029.16), so a
        # reader of the record knows which sections, plots and products
        # the point was run for without opening the matrix.
        "pproc": case.pproc_id,
        "inventory_source": case.inventory_source,
        "motions": [dict(record) for record in case.motions],
        # The windows of every reduction the products stage will write for
        # this point (PFS-2015.04), resolved off the row HERE, where the
        # clock and the blade count are stated, so the stage reads the
        # record alone as it reads everything else. None for a steady row.
        # THE POINT-BEARING CASE, and this line read `reduction_windows(case)`
        # until 2026-09-11. `case` here is the SIM-level case and its `point` is
        # empty: `point_case` is built two hundred lines below, after the names
        # are rendered. So a row sweeping its advance ratio asked the planner a
        # question about a case that did not know which point it was, and the
        # planner correctly answered that no rotor speed was stated. Every
        # unsteady reduction of every swept-ratio point was skipped, four of
        # four on the licensed runs of 2026-09-11.
        #
        # The unit case for that fix passed while this path still failed,
        # because the case it builds carries its point and this one did not.
        "reductions": reduction_windows(case_at_point(case, point)),
        # How the geometry was staged (PFS-2029.17), read off the workspace
        # that staged it, so the record says link or copy and why.
        **dict(
            zip(
                ("staged_as", "staged_as_reason"),
                workspace.staged_as(case.sim_id) if staged_geometry is not None else (None, None),
                strict=True,
            )
        ),
        # The template that rendered this point's names (PFS-2029.19.01),
        # so a reader can tell a name from the identity beside it.
        "point_name_template": workspace.naming.point_name,
        "description": case.description or None,
        "mach": case.mach,
        "reference": _reference_block(case),
        "campaign_name_from": name_from,
        # PFS-2027.05: the inputs as written and the resolved state, so
        # the record is recomputable rather than merely trusted.
        "flight_condition": dict(case.flight_condition),
        "flight_condition_defaults": dict(case.flight_condition_defaults),
        "flight_condition_defaults_from": case.flight_condition_defaults_from,
        "density_kg_m3": None if case.fluid is None else case.fluid.density_kg_m3,
        "temperature_k": None if case.fluid is None else case.fluid.temperature_k,
        "viscosity_pa_s": None if case.fluid is None else case.fluid.viscosity_pa_s,
        "density_source": None if case.fluid is None else case.fluid.source,
        "reference_length_m": None if case.fluid is None else case.fluid.reference_length_m,
        "inputs_sha256": inputs_sha256,
        "script_sha256": "",
        "raw_flag": False,
        "waived_commands": [],
        # PFS-2033.02: the setup's raw commands, as the script carried them.
        "raw_commands": [entry.model_dump(mode="json") for entry in case.raw_commands],
        # The design decision of 2026-09-09: the setup's aliases, for the products stage.
        "aliases": {name: list(members) for name, members in case.aliases.items()},
        # PFS-2012.04: how the solver was called, read off the executor
        # and its result once the point has run, and None on the four
        # early returns below, where no solver ran. `argv` beside it is
        # the command line alone; this says which executor built it.
        "executor": None,
        # The export window the row states for its unsteady exports, as
        # resolved for this run (PFS-2031.18): filled below beside the two
        # action files when the row states EXPORT_UNSTEADY_AFTER_REV or
        # EXPORT_UNSTEADY_AFTER_ITER; None for a row that states neither.
        "export_window": None,
        # Stated, not defaulted (REV010-014). The field defaults to None so
        # that a row which never carried it stays honest about that; a row
        # this version writes DOES carry it, and says so here.
        "manifest_schema": MANIFEST_SCHEMA,
    }
    if preparation_error is not None or recipe is None:
        error = preparation_error or "recipe resolution failed"
        return RunRecord(**base, status=RunStatus.FAILED_SCRIPT, error=error)

    # A POINT ALREADY IN A QUEUE IS NOT SUBMITTED AGAIN, and it is refused
    # BEFORE ANY OF ITS FILES IS WRITTEN (the independent review of the
    # 0.18.1 release). A submitted point runs in its datapoint folder, which
    # carries no campaign name, so the same point submitted under another
    # campaign landed in the queued job's folder and rewrote its script,
    # descriptor, action files and clock while the stale-output check
    # passed, because the queued job had written nothing yet. The guard is
    # per simulation AND point: different points of one row still submit
    # together, which is the refusal that was lifted and stays lifted.
    queued = _queued_record_of_point(executor, workspace, case.sim_id, point_name(case, point))
    if queued is not None:
        return RunRecord(
            **base,
            status=RunStatus.FAILED_SCRIPT,
            error=(
                f"point {point_name(case, point)} of simulation {case.sim_id} is already in a "
                f"scheduler's queue as {queued.run_id!r}, and a submitted point runs in its "
                "own datapoint folder, which that job has not finished writing. Collect it "
                "(pyfs-matrix collect) before submitting this point again; nothing of it was "
                "written."
            ),
        )
    try:
        stem, outputs = _point_names(campaign, case, point, workspace)
    except NamingTemplateError as error:
        return RunRecord(**base, status=RunStatus.FAILED_SCRIPT, error=str(error))
    update: dict[str, object] = {"outputs": outputs}
    if staged_geometry is not None:
        update["geometry"] = staged_geometry
    point_case = _with_the_profile_s_log(case_at_point(case, point, **update), executor)
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
    # FR-91. WHERE THIS SCRIPT PUT ITS PROBE POINTS, written next to the
    # script that placed them. An unsteady plots export numbers its columns
    # `MACH7`, `VELOCITY7` and never says where vertex 7 is, so this file is
    # the only thing that can place a point of that table.
    #
    # A COLLISION HERE IS THIS POINT'S FAILURE AND NOT THE CAMPAIGN'S. The
    # refusal was the one statement in this function that escaped the loop,
    # so a single row whose name collides with a points file the user wrote
    # aborted a campaign whose earlier points had already spent the licence
    # (the interface lens at the release boundary, 2026-09-11). Every other
    # build failure around it records the point and carries on, and a seat
    # is the scarce thing here.
    try:
        probe_points_file = _write_probe_points(sim_dir, case.sim_id, script.probe_points)
    except PyflightstreamError as error:
        return RunRecord(
            **base,
            status=RunStatus.FAILED_SCRIPT,
            error=f"{type(error).__name__}: {error}",
        )
    if probe_points_file is not None:
        base["probe_points_file"] = probe_points_file
    # PFS-2031.13. The child script of a SCRIPT action is parked on the
    # script by helpers.unsteady_action and written HERE, before the
    # solver starts, where the registration line names it: a relative
    # path lands in the simulation folder, which is the solver's working
    # directory, an absolute one where it says. Until this existed the
    # helper promised a writer that did not exist, and a SCRIPT action
    # registered through it named a file that was never there.
    #
    # GOAL-021 ITEM 3, PFS-2010.01.02: A SUBMITTED POINT RUNS IN ITS OWN
    # DATAPOINT FOLDER, `sims/sim_<id>/datapoints/DP-<tag>/`, the folder its
    # outputs are filed under since 0.16.0 (FR-92). Every file below that
    # was written to the working directory follows it: the action programs,
    # the clock and its state, and the scheduler's descriptor. That removes
    # the reason a second submitted point of a row was refused, which was
    # that all of them rewrote those files under a job still in a queue.
    #
    # A LOCAL POINT STILL RUNS IN THE SIMULATION FOLDER. Local points run one
    # after another and never shared a folder at the same moment, and moving
    # them would change every local workspace for no defect. Every input the
    # script reads is named by absolute path since 0.18.1, which is what
    # makes the working directory free to move at all (GOAL-021 item 2).
    work_dir = (
        sim_dir / SIM_DATAPOINTS_DIR / datapoint_dir_name(PointName(point_name(case, point)))
        if isinstance(executor, Submitting)
        else sim_dir
    )
    for action_file, action_text in script.pending_action_scripts.items():
        target = Path(action_file)
        if not target.is_absolute():
            target = work_dir / target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(action_text, encoding="utf-8")
    # PFS-2031.18. A script that registered the counter action names a
    # program this layer writes: the threshold is resolved from the case
    # again (the same function the builder called, so the two agree),
    # the program is rendered with the interpreter the registration
    # line names, and both files are hashed into the record as the
    # staged inputs they are. The count file of an EARLIER point of the
    # same case is removed: every point runs in the same folder, and a
    # count carried over would put the second point past its threshold
    # before its first step.
    threshold = None
    if any(use.name == UNSTEADY_COUNTER_ACTION for use in script.unsteady_actions):
        threshold = unsteady_export_threshold(point_case)
    if threshold is not None:
        program = work_dir / UNSTEADY_ACTION_PROGRAM
        program.parent.mkdir(parents=True, exist_ok=True)
        program.write_text(render_program(threshold, interpreter=sys.executable), encoding="utf-8")
        (work_dir / UNSTEADY_ACTION_COUNT).unlink(missing_ok=True)
        base["inputs_sha256"] = {
            **inputs_sha256,
            UNSTEADY_ACTION_PROGRAM: file_sha256(program),
            UNSTEADY_ACTION_SCRIPT: file_sha256(work_dir / UNSTEADY_ACTION_SCRIPT),
        }
        base["action_program"] = UNSTEADY_ACTION_PROGRAM
        base["action_script"] = UNSTEADY_ACTION_SCRIPT
        # What the row stated and the step the exports begin on, so a
        # reader of the manifest answers "from which step" without opening
        # the counter program (the release review of 2026-09-09).
        base["export_window"] = {
            "stated_form": threshold.stated_form,
            "stated_value": threshold.stated_value,
            "first_step": threshold.first_step,
            "time_iterations": threshold.time_iterations,
            # The clock the counter program ran with, so the series tables
            # compute each step's time and azimuth by the same arithmetic
            # (PFS-2031.18.01); a rotorless row has no azimuth step.
            "delta_time_s": threshold.delta_time_s,
        }
        if threshold.step_deg is not None:
            base["export_window"]["step_deg"] = threshold.step_deg
    # FR-98. THE CLOCK PAIR, written the same way and for
    # the same reason: the program is rendered with this row's deadline so
    # the emitted file states the number the run will use, and the script
    # is parked EMPTY so the solver finds a file with no command in it
    # until the clock fires. The state of an EARLIER point of this case is
    # removed, because a clock carried over would fire the second point
    # before its first step.
    if any(use.name == WALLTIME_CLOCK_ACTION for use in script.unsteady_actions):
        clock = work_dir / WALLTIME_CLOCK_PROGRAM
        clock.parent.mkdir(parents=True, exist_ok=True)
        clock.write_text(
            walltime_clock_program(point_case, workflow_conventions_for(point_case)),
            encoding="utf-8",
        )
        (work_dir / WALLTIME_CLOCK_STATE).unlink(missing_ok=True)
        base["inputs_sha256"] = {
            **base.get("inputs_sha256", inputs_sha256),
            WALLTIME_CLOCK_PROGRAM: file_sha256(clock),
            WALLTIME_STOP_SCRIPT: file_sha256(work_dir / WALLTIME_STOP_SCRIPT),
        }
        base["walltime_s"] = row_walltime_s(point_case)
        base["walltime_margin_s"] = walltime_margin_s(point_case)
    base["script_sha256"] = script_sha
    base["script_path"] = str(Path(script_path).relative_to(sim_dir).as_posix())
    base["raw_flag"] = script.raw_flag
    base["march_strategy"] = script.march_strategy
    # FR-48: a recipe may waive a command the database records broken.
    # The waiver is the recipe's, so the record of it belongs with the
    # run, not with the recipe: this is the only place a reader of the
    # manifest can learn that the numbers below came from a command a
    # probe measured not to work.
    base["waived_commands"] = [use.model_dump(mode="json") for use in script.waived_commands]

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
    # IN THE WORKING DIRECTORY, which for a submitted point is its datapoint
    # folder: a file an earlier run of the point left there is exactly what
    # this refuses to collect as the new run's evidence.
    stale = [name for name in point_case.outputs if (work_dir / name).exists()]
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
                "archive <root> <sim_id>) or remove the leftover, then re-run."
            ),
        )

    # FR-99, GEO-047-C04. THE REFUSAL OF A SECOND SUBMITTED POINT OF A ROW IS
    # GONE FROM THIS PATH, and deliberately from this path only (the owner's
    # lifting of GOAL-020's hold, GOAL-021 item 3). It refused because every
    # point shared the simulation folder's action program, script and clock
    # state; each submitted point now runs in its own datapoint folder, so the
    # reason is removed rather than overruled. The swept-steady path is ONE job
    # over every point of its row and never had the refusal to lift.
    # FR-99. WHAT THIS POINT IS, for the scheduler's descriptor, and it is
    # bound per point because a descriptor names the simulation, its wall
    # clock and its processor count, and those are the row's. A local
    # executor has no such method and is handed nothing.
    _bind_submission_values(executor, case, point_case)
    result = executor.run_script(script_path, working_dir=work_dir, timeout_s=case.solver.timeout_s)
    # PYFS-015. The invocation is the half of a run that lived only in the
    # executor's code: which flags, which directory, which effective
    # timeout. Reproducing a run from its record used to mean re-deriving
    # all three from a class that may have changed since.
    base["argv"] = list(result.argv)
    base["cwd"] = result.cwd
    base["timeout_s"] = result.timeout_s
    base["executor"] = invocation_record(executor, result)
    # PFS-2012.08.01. WHEN the solver ran, for the provenance document's
    # activity; None where the executor reports no clock.
    base["started_at"] = result.started_at
    base["finished_at"] = result.finished_at
    # PFS-2031.18. How far the counter got, read from the file the
    # program left, on every path below: a failed execution's count is
    # evidence about the failure. None when the file was never written,
    # which is a run with no threshold or a solver that never reached a
    # time step.
    if threshold is not None:
        base["action_count"] = _action_count(work_dir / UNSTEADY_ACTION_COUNT)
    # FR-98. WHETHER THE CLOCK FIRED, read from the state the program left.
    # This is the only thing that knows: the solver reports a run that
    # ended, and the difference between ending because it finished and
    # ending because the watchdog stopped it is here or nowhere.
    stopped = _walltime_stop(work_dir / WALLTIME_CLOCK_STATE)
    if stopped is not None:
        base["stopped_at"] = stopped
    # FR-99. READ BEFORE THE FAILURE BRANCH, because the likeliest cluster
    # failure is a REJECTED SUBMISSION and the descriptor is written before
    # the scheduler is called. Read after it, a rejected job produced a
    # FAILED_EXECUTION record with no descriptor, no profile and no
    # submitted flag: the one thing FR-99 says names where the job went,
    # missing from the record of the case that most needs it (the
    # architect lens, round two). `submitted` distinguishes not-sent from
    # sent-and-refused, so the failure record needs no new vocabulary.
    submitted = _submission_record(executor)
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
            submission=submitted,
        )

    # FR-99. A SUBMITTED POINT HAS NO OUTPUTS YET, so nothing below runs.
    # The scheduler has taken the job and the solver has not started; a
    # collection here would find nothing and call it an incomplete output,
    # and an assessment would read a log that does not exist. The record
    # says SUBMITTED, which is the eighth status and is not a failure, and
    # it carries the descriptor the scheduler was handed so the job can be
    # found again.
    if submitted is not None:
        return RunRecord(
            **base,
            status=RunStatus.SUBMITTED,
            wall_time_s=None,
            outputs=[],
            # FR-99, 0.18.0. WHAT THE COLLECTOR WILL WAIT FOR, recorded at
            # the moment of submission. It is on the RECORD and not re-read
            # off the matrix later, because a matrix edited between the
            # submission and the collection is exactly the shape that made
            # a recorded flight condition read back as a different number
            # in a regenerated product (GEO-039-F02). `outputs` stays empty
            # because a submitted point has collected nothing; these are
            # what it was BUILT to write.
            submission={
                **submitted,
                "declared_outputs": list(point_case.outputs),
                # GOAL-021 item 3: WHERE the job runs and writes, relative to
                # the simulation folder so a moved workspace still resolves;
                # the collector waits on the declared outputs here.
                "working_dir": work_dir.relative_to(sim_dir).as_posix(),
            },
        )

    try:
        collected = workspace.collect_outputs(
            case.sim_id,
            [sim_dir / name for name in point_case.outputs],
            # FR-92. THE POINT'S OWN FOLDER, always, steady or unsteady.
            # Every point of one case collected into one `outputs/` until
            # 0.16.0, so from the second point of a swept row onward that
            # folder held two files that both read as loads tables and
            # nothing in the layout said which point either belonged to.
            # The point's checked NAME is passed and the folder is rendered
            # there, so a caller cannot name a folder the assessor will not read.
            datapoint=PointName(point_name(case, point)),
        )
    except (WorkspaceError, CampaignConfigError) as error:
        # BOTH, because collection can refuse for two reasons and only one of
        # them used to be caught. `collect_outputs` renders the point's folder
        # name, so a point naming no known axis raises CampaignConfigError from
        # `point_tag`, and that is not a WorkspaceError: uncaught it would abort
        # the campaign HERE, after the solver has run, instead of costing this
        # point (the architecture lens, 2026-09-11). Unreachable through
        # `sweep.points()`, which yields only points keyed by a known axis, and
        # caught anyway: the thing this costs is a licensed seat.
        return RunRecord(
            **base,
            status=RunStatus.FAILED_INCOMPLETE_OUTPUT,
            wall_time_s=result.wall_time_s,
            error=str(error),
        )

    assessment = assess(point_case, result, sim_dir)
    return RunRecord(
        **base,
        # FR-98. THE CLOCK'S VERDICT WINS, and only over a converged one.
        # A run the watchdog stopped did not converge and did not fail: it
        # ran out of clock with its outputs written, which is a state of
        # its own and the reason the value exists. A run that DIVERGED and
        # then hit the clock is still diverged, so a failure is left alone.
        status=(
            RunStatus.WALLTIME_REACHED
            if base.get("stopped_at") and not str(assessment.status).startswith("FAILED")
            else assessment.status
        ),
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
        log_file_used=assessment.log_file_used,
        residual_note=assessment.residual_note,
        solver_run_time_s=assessment.solver_run_time_s,
        solver_initialization_s=assessment.solver_initialization_s,
        time_steps=assessment.time_steps,
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
