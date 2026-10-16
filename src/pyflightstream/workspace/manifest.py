"""Run and extraction records, manifest writers and the owned manifest lease.

The workspace facade keeps the historical imports and delegates writes here.
Existing record shapes and serialized fields are preserved.
"""

from __future__ import annotations

import enum
import json
import os
import shutil
import socket
import sys
import threading
import time
import uuid
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, NotRequired, Protocol, TypedDict

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
    model_validator,
)

import pyflightstream._textio as _textio
from pyflightstream._errors import PyflightstreamError
from pyflightstream.cases import BoundaryAliases, RawCommand
from pyflightstream.cases.windows import (
    ExportThresholdRecord,
    StoppedStepRecord,
    surface_average_window,
    surface_averaging_window,
)
from pyflightstream.script import MarchStrategy, SurfaceAverageWindow, SurfaceAveragingWindow
from pyflightstream.workspace.naming import ARCHIVE_DIR, ARCHIVE_STAMP, free_root_archive

__all__ = [
    "COST_EXCLUDED_STATUSES",
    "ADDITIONAL_MANIFEST",
    "ADDITIONAL_MANIFEST_SCHEMA",
    "AdditionalRecord",
    "BrokenCommandRecord",
    "ExecutorRecord",
    "ExtractionStatus",
    "JOB_TAG",
    "KNOWN_MANIFEST_SCHEMAS",
    "MANIFEST_LOCK_POLL_S",
    "MANIFEST_LOCK_RENEW_S",
    "MANIFEST_LOCK_STALE_S",
    "MANIFEST_LOCK_TIMEOUT_S",
    "MANIFEST_SCHEMA",
    "RunRecord",
    "RunStatus",
    "SOURCE_VERSION_REQUIRED_SINCE",
    "WorkspaceError",
    "append_record",
    "complete_submitted_record",
    "manifest_lock",
    "planned_points_without_record",
    "supersede_records",
]


class WorkspaceError(PyflightstreamError, RuntimeError):
    """A file-management operation was refused or impossible.

    The refusals protect run evidence: archiving or cleaning without a
    manifest record would destroy a run the manifest cannot account
    for, and collection of a declared output that the solver never
    produced points at an incomplete run.
    """


WorkspaceError.__module__ = "pyflightstream.workspace"


#: Layout identifier recorded on every manifest row. It changes when a field is removed or
#: changes meaning, never for an addition. Schema "1" permits an absent ``source_version`` in
#: ``broken_commands`` entries; schema "2" requires it. Schema "3" writes ``waived_commands``
#: instead of ``broken_commands``. The old key remains readable with a deprecation warning.
MANIFEST_SCHEMA = "pyfs-manifest/3"

#: Every stamp this version can still READ, newest last. The bump above
#: is a change of what may be WRITTEN, and a reader that refused every
#: older stamp would make a bump equivalent to deleting the manifests
#: that came before it: nothing in this package migrates a manifest, so
#: there would be no route back. A stamp outside this tuple is refused,
#: which is the "must refuse when the value is one it has never seen"
#: half, and that includes a stamp from a LATER version.
KNOWN_MANIFEST_SCHEMAS = ("pyfs-manifest/1", "pyfs-manifest/2", "pyfs-manifest/3")

#: Maximum wait for a held manifest, in seconds; a timeout is not proof of death.
MANIFEST_LOCK_TIMEOUT_S = 60.0
#: Renew a held lock's modification timestamp every five seconds.
MANIFEST_LOCK_RENEW_S = 5.0
#: Recover an unrenewed lease after five minutes (60 renewal periods), including
#: legacy or unreadable owner records. A confirmed dead local PID is recovered
#: immediately. Shared hosts must have synchronised clocks for lease expiry.
MANIFEST_LOCK_STALE_S = 300.0
#: The pause between two attempts to take the manifest, in seconds.
MANIFEST_LOCK_POLL_S = 0.02

#: The stamp from which every waiver row carries ``source_version``
#: (PFS-2012.03). Named apart from :data:`MANIFEST_SCHEMA` the day that
#: constant moved for a second reason: the refusals below cite the stamp
#: that made the key required, and citing the CURRENT stamp there would
#: have told a reader the key arrived with the rename.
SOURCE_VERSION_REQUIRED_SINCE = "pyfs-manifest/2"


class RunStatus(enum.StrEnum):
    """Terminal status of one executed campaign point (SAD Section 7).

    Every executed point lands in exactly one of these; a silent skip
    is structurally impossible in the campaign loop.

    Examples
    --------
    >>> from pyflightstream.workspace import RunStatus
    >>> RunStatus("SUBMITTED") is RunStatus.SUBMITTED
    True
    >>> str(RunStatus.CONVERGED)
    'CONVERGED'
    """

    CONVERGED = "CONVERGED"
    COMPLETED_MAX_ITER = "COMPLETED_MAX_ITER"
    #: FR-434,  a STEADY point whose evidence (the solver log, else the
    #: loads footer) shows the iteration counter AT the iteration limit the run
    #: requested, with the residual not settled below the convergence limit.
    #: NOT A FAILURE, and a different statement from COMPLETED_MAX_ITER, which
    #: an unsteady run that ended its time loop keeps, and which a steady point
    #: whose evidence does not show the counter at the limit keeps too: this
    #: value needs that evidence and is never inferred. The record states the
    #: requested limit in ``iterations_requested`` beside the ``iterations``
    #: reached, and ``residual_note`` words both. Every
    #: reader that treats COMPLETED_MAX_ITER as an ended run that is not a
    #: failure treats this value the same. A manifest holding it is refused by
    #: an older reader that does not recognise this status; upgrade that reader
    #: before sharing the manifest, as the migration note states.
    MAX_ITER_REACHED = "MAX_ITER_REACHED"
    FAILED_EXECUTION = "FAILED_EXECUTION"
    FAILED_SCRIPT = "FAILED_SCRIPT"
    FAILED_INCOMPLETE_OUTPUT = "FAILED_INCOMPLETE_OUTPUT"
    FAILED_DIVERGED = "FAILED_DIVERGED"
    #: FR-98: the run reached its WALLTIME and the watchdog
    #: stopped it with its outputs written. NOT A FAILURE, and the whole
    #: point of the value: the numbers up to that step are real and the user
    #: judges whether to continue. Its sibling is COMPLETED_MAX_ITER, which
    #: is the same shape for the iteration cap; this one is the clock cap.
    #:
    #: A record in this state carries `stopped_at`, without which
    #: `RESTART: {FINISH_PENDING}` has nothing to subtract from.
    WALLTIME_REACHED = "WALLTIME_REACHED"
    #: FR-99: the point was handed to a scheduler and has
    #: not come back. NOT A FAILURE EITHER, and it cannot be folded into an
    #: existing value: a submitted point is not converged, not failed and
    #: not blocked, and calling it any of those makes a sweep report a
    #: verdict for a run that has not happened.
    SUBMITTED = "SUBMITTED"
    #: FR-309: the person marked the point failed with ``pyfs-matrix
    #: mark-failed``, whatever it ended in, because a run that completed can
    #: be found wrong later. A FAILED_ value on purpose: every reader that
    #: asks ``startswith("FAILED")`` (the post, the cost estimate,
    #: delete-sims) treats it as a failure without learning a new name. The
    #: record keeps what it was in ``marked``.
    FAILED_MARKED = "FAILED_MARKED"
    #: FR-413,  the point's outputs are all present and its declared
    #: solver log is absent (deleted after the run, or never copied back). NOT A
    #: FAILURE: the run ENDED with its outputs, which are collected and posted;
    #: what only the log carries (the residual history, the convergence verdict,
    #: the frozen-point reading, the solver clock and its iteration count) is
    #: named in ``residual_note`` as unavailable, and the point is never
    #: CONVERGED by assumption.
    RAN_MISSING_LOG = "RAN_MISSING_LOG"


COST_EXCLUDED_STATUSES = frozenset(
    status
    for status in RunStatus
    if status.name.startswith("FAILED")
    or status in {RunStatus.WALLTIME_REACHED, RunStatus.SUBMITTED, RunStatus.RAN_MISSING_LOG}
)
"""Statuses whose wall clock is not a completed-run cost sample."""


class ExecutorRecord(TypedDict):
    """How the solver was called, as the run layer read it off the run.

    The JSON shape of the ``executor`` entry of a manifest row
    (PFS-2012.04). ``class_name`` is the executor's class as it ran
    (``LocalExecutor`` today; an HPC executor the day FR-15 lands) and
    ``argv`` the command line it returned, which is the same list as the
    row's own ``argv`` and travels here as well so the entry is one
    self-contained fact a report can be built from. Both keys are
    required: the entry is written whole or, on a point where no solver
    ran, not at all, and the row says ``None``. ``forced_local`` is
    present, and true, only on a point the run's local switch kept on a
    machine that would otherwise have submitted; a record
    written before it, or by a run that did not ask, has no key, and a legacy reader refuses a
    manifest that carries one.
    """

    class_name: str
    argv: list[str]
    forced_local: NotRequired[bool]


class BrokenCommandRecord(TypedDict, total=False):
    """One serialized :class:`~pyflightstream.script.BrokenCommandUse`.

    The JSON shape of a ``waived_commands`` entry of the manifest,
    declared here rather than imported so the workspace layer keeps its
    manifest schema and the script layer keeps the model. The model is
    the single home of what each field MEANS: read
    :class:`~pyflightstream.script.BrokenCommandUse` for that, including
    why two of these are versions and are not interchangeable.

    Every key is optional (``total=False``) and no member type is
    narrower than the model's, which is the compatibility half: a
    manifest row written before a key existed still reads back, exactly
    as :attr:`RunRecord.manifest_schema` may be None. Unknown keys are
    KEPT rather than dropped, so reading a manifest a later version
    wrote never quietly edits the evidence.
    """

    command: str
    version: str
    source_version: str | None
    report: str
    note: str | None
    reason: str
    first_line: str


# Set after the class body because mypy refuses any statement inside a
# TypedDict definition that is not a field declaration.
BrokenCommandRecord.__pydantic_config__ = ConfigDict(extra="allow")  # type: ignore[attr-defined]


class RunRecord(BaseModel):
    """One manifest record: a single executed campaign point.

    The record plus the staged inputs reproduce the run (NFR-07).

    Attributes
    ----------
    run_id : str
        Unique identity of the executed point, for example
        ``"campaign/sim_9001/a+02.0_b+00.0"``; the manifest rejects
        duplicates.
    sim_id : str
        Simulation identity; ties the record to ``sims/sim_<sim_id>``.
    point : dict of str to float
        Sweep point coordinates, for example alpha and beta in deg.
    fs_version_requested : str
        Canonical FlightStream version the script was built for.
    fs_version_reported : str, optional
        Version printed in the solver outputs; filled by the parsers
        and cross-checked against the requested one (FR-18).
    fs_build : str, optional
        Build string reported by the solver, when available.
    fs_version_source : str or None
        Where the build this point ran on came from: ``"row"`` when the
        case named its own :attr:`~pyflightstream.cases.SimCase.fs_build`
        and ``"campaign_default"`` when it inherited the campaign's
        (PFS-2009.08.02). ``fs_exe`` and ``fs_version_requested`` say
        WHICH build; this says WHICH OF THE TWO SOURCES chose it, which
        the record could not state at all while a campaign declared one
        installation and a case could name another.

        None means the row PREDATES the field and is not a claim that the
        build was inherited, exactly as ``manifest_schema`` may be None.
        Adding it did NOT move :data:`MANIFEST_SCHEMA`: that constant's
        own rule bumps for a removal or a change of meaning, never for an
        addition.
    velocity_requested_m_s : float or None
        Free-stream velocity in m/s the case ASKED for, as
        :attr:`~pyflightstream.cases.SimCase.velocity` declared it
        (OPS-2009.01.13). Recorded because two places compare requested
        conditions against the conditions a solver export prints back,
        and only one of them could see this axis, so the two could reach
        opposite verdicts about one run.

        None means the run did not request a velocity, which includes
        every row written before the field existed, and is NOT zero: a
        binding treats an unrequested axis as unasked rather than as
        agreed, and zero would be a request the export could contradict.
    package_version : str
        pyflightstream version that produced the run. Read from the
        installed distribution's metadata, which is a static string, so
        every commit between two tags reports the tag: use
        ``package_commit`` to tell them apart.
    package_commit : str, optional
        Git commit the package's code came from, when it came from a
        tracked work tree; None for a wheel install, where there is no
        repository to ask (PYFS-017).
    package_dirty : bool, optional
        Whether that work tree had uncommitted changes. None travels
        with a None ``package_commit`` and means "not knowable here",
        never "clean".
    script_sha256 : str
        Hash of the executed script text.
    inputs_sha256 : dict of str to str
        Hash per staged input file name, recorded at staging time.
    raw_flag : bool
        True when the script used the ``raw()`` escape hatch and its
        content bypassed database validation (FR-07).
    manifest_schema : str or None
        Identifier of the record layout this row was written under.
        A reader that does not know the value should refuse rather than
        guess which fields exist (PYFS-015).

        None means the row PREDATES the field and is not a claim that
        it was written under the current schema. Reading an older row does not stamp it with the
        current schema (REV010-014). "The
        field is absent because the row is old" and "the row asserts
        the current schema" are different facts about the evidence.
    conditions : list of dict, optional
        The operating-point binding recorded by the assessor, one
        entry per requested axis the export printed back: ``axis``,
        ``requested``, ``reported``, ``deviation``, ``tolerance``,
        ``unit`` and ``within`` (REV010-001). None means the run was
        recorded by an assessor that did not perform the comparison,
        which includes every row written before this field existed;
        an empty list means the comparison ran and had nothing to
        compare. The two are deliberately distinguishable.
    fs_exe : str, optional
        Solver executable the run invoked, as resolved.
    fs_exe_sha256 : str, optional
        Hash of that executable, so a later reader can tell whether the
        same binary is still installed. None when it could not be read.
    argv : list of str
        The exact command line, argument by argument. Reproducing a run
        from the record needs the flags, not a guess at how the
        executor builds them.
    cwd : str, optional
        Working directory the solver process ran in.
    timeout_s : float, optional
        Wall-clock limit actually applied to the process.
    recipe : str, optional
        Recipe identifier as the case declared it.
    recipe_sha256 : str, optional
        Hash of the recipe function's source at run time. A recipe is
        user code that can be edited between runs, so the name alone
        does not identify what built the script; None when the source
        is not introspectable.
    script_path : str, optional
        Generated script, relative to the simulation folder.
    outputs_sha256 : dict of str to str
        Hash per collected output, keyed by the same relative name that
        appears in ``outputs``. Empty for a point that collected
        nothing and for manifests written in legacy releases. Inputs have
        carried a hash since the first manifest and outputs did not, so
        a record could name evidence that had since been edited,
        truncated or replaced with nothing to compare against
        (PYFS-006).
    waived_commands : list of BrokenCommandRecord
        Serialized
        :class:`~pyflightstream.script.BrokenCommandUse` entries, one
        per command the script emitted under an ``allow_broken`` waiver
        (FR-48). That class is the single home of the field list and
        their meanings; note only that TWO of them are versions and they
        are not interchangeable, ``version`` being the build the script
        targeted and ``source_version`` the build whose record is broken,
        which is the build the cited report was run on.

        The key was ``broken_commands`` in legacy releases (PFS-2022.01.05,
        OPS-2009.02.08), and read as the commands that broke in the run,
        which is the opposite of a waiver the recipe registered on
        purpose. A row written under the old key still reads, with a
        DeprecationWarning built from the ledger entry that names the
        release dropping it; no row is written under it. The rename
        moved :data:`MANIFEST_SCHEMA` to ``pyfs-manifest/3``, for the
        reason recorded on that constant.
        Empty for the ordinary run, which is the
        point: a run that leaned on a command known not to work is
        distinguishable from one that did not, forever, without
        re-reading the script.

        ``source_version`` is REQUIRED since ``pyfs-manifest/2``
        (PFS-2012.03). :meth:`read_manifest` refuses an entry that lacks
        it, naming this manifest and the stamp the row carries, rather
        than reading the field as empty.
    executor : ExecutorRecord or None
        Which executor ran the point and the argv it ran, read off the
        run rather than asserted (PFS-2012.04); None on a point where
        no solver ran, and on every row written in legacy releases. Adding
        it did not move :data:`MANIFEST_SCHEMA`.
    export_window : ExportThresholdRecord or None
        The export threshold the row states for its unsteady exports
        (PFS-2031.18), as resolved for this run: ``stated_form``
        (``revolutions`` or ``iterations``, the key the row wrote),
        ``stated_value``, ``first_step`` (the first time step whose
        export runs) and the local ``time_iterations``. ``step_offset`` is
        the absolute step where this march begins. None for a row that states
        no threshold (a count-only march or no counter staged), and for older
        records. This is distinct from the public
        averaging ExportWindow; the persisted key remains compatible.
    solver_setup : dict, optional
        Serialized solver-setup snapshot
        (:class:`pyflightstream.script.solver_setup.SolverSetup`) of
        the built script: every solver flag with its effective value
        and provenance (explicit, default with citation, or unknown).
        None for scripts built without the curated ``solver_settings``
        helper and for manifests written in legacy releases.
    status : RunStatus
        Terminal status of the point.
    iterations : int, optional
        Solver iterations reached, when parsed.
    residual : float, optional
        Final residual, when parsed.
    wall_time_s : float, optional
        Wall-clock duration of the solver process in seconds.
    started_at : str, optional
        When the solver process was started, ISO 8601 in UTC to the
        second, as the executor read its clock (PFS-2012.08.01); the
        provenance document the products stage writes states it as the
        run activity's start. None where no solver ran, where the
        executor reports no clock, and on every row written in legacy releases. Adding it did
        not move :data:`MANIFEST_SCHEMA`.
    finished_at : str, optional
        When the process ended, or was killed on timeout, the same way.
    outputs : list of str
        Collected output files, relative to the simulation folder
        (for example ``"outputs/loads.txt"``; a record written in legacy releases names
        ``"raw/loads.txt"`` and is read unchanged, FR-84).
    error : str, optional
        Error text for failed points.
    flight_condition_defaults : dict of str to float
        The fluid pins the row's SETUP artifact supplied, with the values
        used, for the keys the row did not state (PFS-2030.08). Empty
        means the row stated everything its resolution used, which is
        every record written in legacy releases; it is NOT a claim that the
        setup carried no table. HOW TO READ THE PAIR: a pin in
        ``flight_condition`` and not here was stated by the ROW and
        overrode whatever the setup said, since a key the row states
        never enters this mapping. Recorded beside the condition as
        written because without it a record cannot be recomputed once the
        constants move out of the row, and adding it did not move
        :data:`MANIFEST_SCHEMA`, whose rule bumps for a removal or a
        change of meaning and never for an addition.
    flight_condition_defaults_from : str
        Which setup supplied those pins, id and path, for example
        ``setup 's001' (inputs/setups/s001.toml)``. Empty when the row
        inherited nothing, which includes every record written in legacy releases.
    matrix_stem : str, optional
        The stem of the run matrix the point came from, when the campaign
        was converted from one (PFS-2031.04). A workspace may hold several
        matrices sharing this one manifest, and the sweep table and the
        products of each are rebuilt from the records that name it. None
        means the record predates the field or the campaign was authored
        in Python; such a record belongs to no matrix and is left out of a
        per-matrix table rather than counted in every one. Adding it did
        not move :data:`MANIFEST_SCHEMA`.
    reductions : dict or None
        The windows of every reduction the products stage writes beside
        the point's plots table (PFS-2015.04), resolved off the row by
        :func:`pyflightstream.cases.workflows.reduction_windows` when the
        record was written: ``time_iterations``, ``steps_per_revolution``,
        ``blades``, and one entry per applicable reduction (``time_average``,
        ``phase_locked``, ``per_blade``) carrying its ``windows`` in solver
        steps and ``window_from``, how the row stated them, or ``skipped``
        with the reason the row could not window it. None means the row
        carries no time history (a steady point) or the record predates
        the field; a products stage reading None writes no reduction and
        records why. Adding it did not move :data:`MANIFEST_SCHEMA`. [REF-03]

        a row that names its rotors by alias also carries
        ``rotors`` (FR-68), alias to one block per rotor holding that
        rotor's ``blades``, ``rpm``, ``steps_per_revolution``,
        ``period_steps`` and its own ``phase_locked`` and ``per_blade``;
        on such a row the flat passage entries carry a skip naming that
        block, because one blade passage of the ROW has no length when two
        rotors turn at two speeds. Adding it did not move
        :data:`MANIFEST_SCHEMA` either: it is an ADDITION, and a record
        written before it degrades correctly, a products stage finding no
        ``rotors`` reading the flat keys exactly as it always did.
    flight_condition : dict of str to float
        The flight condition AS WRITTEN in the row, canonical key to
        value, in the units the key names (``MACH`` dimensionless,
        ``TASmps`` m/s, ``REmi`` millions, ``ALTFT`` ft, ``dISA``
        Celsius as a delta). Empty when the case stated none.
    density_kg_m3 : float, optional
        Resolved density in kg/m3. ``None`` when no condition resolved.
    temperature_k : float, optional
        Resolved static temperature in K, including any ISA deviation.
    viscosity_pa_s : float, optional
        Resolved dynamic viscosity in Pa s, from Sutherland's law at
        ``temperature_k``.
    density_source : {"atmosphere", "solved-from-reynolds"}, optional
        WHICH BRANCH produced ``density_kg_m3``. ``"atmosphere"`` is the
        standard value at the stated altitude; ``"solved-from-reynolds"``
        means the density was solved to meet a stated Reynolds number and
        is deliberately not a point in any atmosphere. Read it before
        reading the density as an altitude.
    reference_length_m : float, optional
        The reference length in m that the resolution used, which is
        ``None`` unless a Reynolds number was stated. Recorded because
        the resolved density cannot be checked without it.
    action_program : str, optional
        The counter program the run layer wrote for a row stating
        ``EXPORT_UNSTEADY_AFTER_REV`` or ``EXPORT_UNSTEADY_AFTER_ITER``
        (PFS-2031.18), relative to the simulation folder; its sha256 is
        in ``inputs_sha256`` under the same name, because the program is
        an input of the run like the geometry. None for a row stating
        neither key, which is every record written in legacy releases.
    action_script : str, optional
        The file the SCRIPT action points at and the program rewrites,
        relative to the simulation folder; ``inputs_sha256`` carries the
        hash of the EMPTY file the run layer wrote, not of what the run
        left, which is the rewritten one. None likewise.
    action_count : int, optional
        The invocation count the program reached, read from its count
        file after the solver exited: the number of time steps the
        solver completed, since the count is the step count exactly
        (RPT-041). None when the file was never written: a row with no
        threshold, or a solver that never reached a time step.

    Examples
    --------
    A synthetic record illustrates serialization without running a solver:

    >>> from pyflightstream.workspace import RunRecord, RunStatus
    >>> record = RunRecord(
    ...     run_id="demo/sim_1/AL+000", sim_id="1",
    ...     fs_version_requested="25.0", package_version="0.36.0",
    ...     script_sha256="0" * 64, raw_flag=False, status=RunStatus.SUBMITTED,
    ... )
    >>> record.model_dump(mode="json")["status"]
    'SUBMITTED'
    >>> record.as_points()[0] is record
    True
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str
    sim_id: str
    point: dict[str, float] = Field(default_factory=dict)
    #:  the point's name, which ends the run_id, names its datapoint
    #: folder and is the stem of its files (`pyflightstream.cases.point_name`);
    #: and the name of the whole sweep of its case, each swept field written
    #: `<code>+sweep`, which the polar tables and superfiles of the case carry.
    #: Required when posting; older records need explicit migration (docs/upgrading.md).
    point_name: str | None = None
    sweep_name: str | None = None
    fs_version_requested: str
    fs_version_reported: str | None = None
    fs_build: str | None = None
    fs_version_source: str | None = None
    velocity_requested_m_s: float | None = None
    #: The flight condition AS WRITTEN in the row, canonical key to
    #: value, in the units the keys name. Empty when the case stated
    #: none (PFS-2027.05).
    flight_condition: dict[str, float] = Field(default_factory=dict)
    flight_condition_defaults: dict[str, float] = Field(default_factory=dict)
    flight_condition_defaults_from: str = ""
    matrix_stem: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _refuse_old_matrix_key(cls, data: object) -> object:
        """Name the current key and the explicit migration for an older record."""
        if isinstance(data, dict) and "matrix" in data:
            raise ValueError("matrix was replaced by matrix_stem; run `pyfs-workspace migrate`")
        return data

    #: The resolved flow state, and WHICH BRANCH produced the density.
    #: Recorded so a reader can RECOMPUTE the resolution rather than
    #: trust it: the inputs above plus these values plus the reference
    #: length are everything the resolver used.
    #:
    #: `density_source` is not decoration. A density solved to meet a
    #: Reynolds number is deliberately NOT a point in any atmosphere, so
    #: without this field a later reader has no way to tell a
    #: wind-tunnel state from an altitude and may "fix" it into one.
    density_kg_m3: float | None = None
    temperature_k: float | None = None
    viscosity_pa_s: float | None = None
    density_source: str | None = None
    reference_length_m: float | None = None
    package_version: str
    package_commit: str | None = None
    package_dirty: bool | None = None
    #: Submitting user, captured at run time because it cannot be recovered
    #: afterwards. An unrecorded identity remains None and reads as NA. The
    #: standard-library lookup serves both Windows and cluster execution.
    submitted_by: str | None = None
    manifest_schema: str | None = None
    fs_exe: str | None = None
    fs_exe_sha256: str | None = None
    argv: list[str] = Field(default_factory=list)
    cwd: str | None = None
    timeout_s: float | None = None
    recipe: str | None = None
    #: FR-98: where a WALLTIME_REACHED run stopped, as the watchdog counted
    #: it. The program that stops the run is the only thing that knows, so
    #: it writes the number down before the solver goes away; without it
    #: `RESTART: {FINISH_PENDING}` has nothing to subtract from.
    stopped_at: StoppedStepRecord | None = None
    #: The ``run_id`` of the run this record CONTINUES; None on a run
    #: that continues nothing and on every record written in legacy releases.
    #:
    #: A continuation archives the CONTENTS of the datapoint folder and writes
    #: into that same folder, and the stopped run's row is never rewritten, so
    #: its ``outputs`` go on naming the folder its continuation fills. This is
    #: what lets a reader tell a chain from two runs of one point and take the
    #: end of it; the continuation resolver knew the answer and nothing kept it.
    continues: str | None = None
    #: FR-96: the RESTART request a continuation answered, form and value.
    restart: dict[str, Any] | None = None
    #: FR-98: the wall clock the ROW stated, in seconds, and the margin the
    #: SETUP stated, on a run that registered the watchdog. Both are written
    #: because neither can be recovered afterwards: the row may have been
    #: edited and the margin has a default, so a record that says only
    #: WALLTIME_REACHED cannot say what it reached. None on every run that
    #: states no wall clock, which is every steady row and every unsteady
    #: row written in legacy releases.
    #:
    #: FOUND BY THE FIRST REAL RUN OF pfs0170, not by a test: the run stage
    #: had written these two keys into the record since the watchdog landed
    #: and this model forbids extras, so the first rotor point that stated a
    #: WALLTIME died at the manifest with the solver's work already done.
    walltime_s: float | None = None
    walltime_margin_s: float | None = None
    #: GOAL-023: how an unsteady point was marched on its build, "actions" or
    #: "single_march"; None for a steady point and on every record written
    #: in legacy releases.
    march_strategy: MarchStrategy | None = None
    #: FR-99: what a SUBMITTED point was handed to, and where. The
    #: descriptor the scheduler was given, the profile that rendered it,
    #: the application id inside it, and whether the submit command was
    #: actually run. None on every run this machine executed itself.
    #:
    #: A SUBMITTED record has no outputs and no wall time of its own, so
    #: this is the only thing that says where the job went; without it a
    #: queued point is a record that says nothing a user can act on.
    submission: dict | None = None
    #: FR-95: the JOB this record is. One steady row is one
    #: job for all its points so a record is a job and not a
    #: point, and this is what a submitted job is asked after by. None on a
    #: record written in legacy releases and on any record whose job is one point,
    #: which is every unsteady point and every LEGACY row.
    job_id: str | None = None
    #: The points that job ran, IN THE ORDER IT RAN THEM, each with the tag
    #: that names its folder and the status it ended in.
    #:
    #: THE ORDER IS RECORDED BECAUSE IT IS PART OF THE RESULT. A warm sweep
    #: begins each point from the previous point's converged solution, so
    #: the same three alphas run in another order are not the same three
    #: numbers. Empty on
    #: a record that is one point.
    points_ran: list[dict] = Field(default_factory=list)
    #: The pproc artifact id the row named (PFS-2029.16); None on a
    #: record written in legacy releases or by a campaign built without one.
    pproc: str | None = None
    #: The naming template that rendered the point's stem and output names
    #: (PFS-2029.19.01); None on a record written in legacy releases.
    point_name_template: str | None = None
    #: What the post stage needs to rebuild the products from the manifest
    #: alone (PFS-2029.15.03): the row's description, its Mach number and
    #: the reference block (SREF, CREF, BREF, XMOM, YMOM, ZMOM).
    description: str | None = None
    mach: float | None = None
    reference: dict[str, float] | None = None
    #: Where the campaign name came from (PFS-2029.03.01): ``directory``
    #: when the workspace directory named it, ``option`` when ``--name``
    #: or the ``name`` argument did; None on a record written before.
    campaign_name_from: str | None = None
    #: Where the boundary inventory came from, ``sidecar`` or ``mesh_block``
    #: (PFS-2029.06.03); None when the geometry declares none.
    inventory_source: str | None = None
    #: THE BOUNDARY NAMES THE SCRIPT WAS BUILT OVER (R03), in the
    #: solver's order, the name at position ``i`` being boundary ``i``: what
    #: the builder read at OPEN from the source ``inventory_source`` names.
    #: The post reads a section distribution's selection over them, where
    #: the cuts alone cannot say what a family stem or ``all`` selected, for
    #: a block recorded in a common frame or with the rotor definitions in
    #: hand; in a rotor's frame the builder read the rotor families instead.
    #: None on every record written in legacy releases, which the post recovers
    #: by the geometry's hash (:meth:`CampaignWorkspace.recorded_inventory`),
    #: and on a run that opened no geometry declaring names.
    #:
    #: Adding it did not move MANIFEST_SCHEMA. The key is ABSENT where the
    #: value is None, as ``forced_local`` of the executor entry is where
    #: nothing was forced: a legacy reader refuses a record that
    #: carries a key it does not know, so only a record that has names to
    #: state writes one.
    inventory: list[str] | None = None
    #: How a raw mesh was imported (G01): the ``[import]`` table of its
    #: sidecar as the run read it, ``{"units": "MILLIMETER"}``. None for a
    #: point that opened a saved simulation or no geometry. Recorded because
    #: only the geometry's bytes are hashed, so without it two runs of one
    #: mesh under two units would carry identical records. ABSENT where
    #: None, as ``inventory`` is, so a manifest of ``.fsm`` rows stays
    #: readable by a legacy reader.
    mesh_import: dict[str, object] | None = None
    #: How the inputs were staged (PFS-2029.17): ``link``, a directory
    #: junction on Windows and a symbolic link elsewhere, at the geometry's
    #: own folder of the library or at the flat library (PFS-2032.04), or
    #: ``copy``; None for a point with no staged input.
    staged_as: str | None = None
    #: Why a copy was made where a link was asked for; None otherwise.
    staged_as_reason: str | None = None
    #: The rotor motions the row's ``MOTIONS`` list stated, as bound
    #: (PFS-2029.11.03): a named hub carries its coordinates and the name.
    motions: list[dict[str, str]] = Field(default_factory=list)
    #: The reduction windows the products stage reads (PFS-2015.04); see
    #: the class docstring. A mapping rather than a model so the record
    #: carries exactly what the resolver wrote and a reader never guesses.
    reductions: dict[str, object] | None = None
    #: M1: on a point of an ``unsteady_rotor`` row, a ``steady``
    #: row stating ``RPM`` or a row naming an actuator disc, each rotor's and
    #: disc's tip and helical Mach numbers keyed by its alias or disc name,
    #: with the speed, the diameter, the free-stream speed and the speed of
    #: sound they were taken at, or a ``note`` saying why they are not known
    #: (:meth:`pyflightstream.cases.workflows.RotorMach.record`). A steady
    #: JOB record keys them one level up by the point's name, since one job
    #: runs several points, and :meth:`as_points` hands each point its own.
    #: ABSENT where None, as ``inventory`` is, so a manifest without such a
    #: point stays readable by a legacy reader.
    rotor_mach: dict[str, dict[str, object]] | None = None
    recipe_sha256: str | None = None
    script_path: str | None = None
    script_sha256: str
    inputs_sha256: dict[str, str] = Field(default_factory=dict)
    raw_flag: bool
    #:  the run was told to accept an installed build other than the
    #: registered one (--accept-unregistered-build), so its compatibility was the
    #: user's responsibility; the build the solver printed is `fs_build`.
    accept_unregistered_build: bool = False
    #: FR-998, FR-999: each value the invocation took from a workspace
    #: settings file, and the file it came from (``pyfs.toml``, ``pyfs.local.toml``),
    #: with the acceptance of the build under ``accept_unregistered_build`` where a
    #: file, or the build's entry of ``inputs/executables.local.toml``, stated it.
    #: ABSENT where None, as ``inventory`` is: a value typed or left at the
    #: package default is recorded as before, so a workspace without the files
    #: writes the existing record format.
    settings_sources: dict[str, str] | None = None
    outputs_sha256: dict[str, str] = Field(default_factory=dict)
    waived_commands: list[BrokenCommandRecord] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _refuse_old_waived_commands_key(cls, data: object) -> object:
        """Refuse the earlier key; only explicit migration translates it."""
        if isinstance(data, dict) and "broken_commands" in data:
            raise ValueError(
                "broken_commands was replaced by waived_commands; run `pyfs-workspace migrate`"
            )
        return data

    @model_serializer(mode="wrap")
    def _omit_unrecorded_keys(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        """Write none of the keys a reader older than their release may not know, where unstated.

        ``inventory``, ``mesh_import``, ``rotor_mach``, ``clocking_verdicts``, FR-96's ``restart``,
        FR-435's ``skipped_names``, FR-436's ``settings_sources`` and FR-455's ``farfield_layout``.

        R03 and G01, M1 and the L1 fixes, FR-999 of FR-436
        and FR-1047 of FR-455.

        The rule ``forced_local`` follows: a key a legacy reader
        does not know is written only where something was recorded, so a
        manifest of LEGACY or geometry-less records, which carry neither,
        stays readable by it.
        A serializer rather than ``Field(exclude_if=...)``, which needs
        pydantic 2.11 where this package's floor is pydantic 2.
        """
        keys = (
            "inventory mesh_import rotor_mach clocking_verdicts marked restart discarded_by"
            " iterations_requested skipped_names settings_sources farfield_layout"
        ).split()
        return {key: v for key, v in handler(self).items() if v is not None or key not in keys}

    #: How the solver was called (PFS-2012.04), None where no solver ran
    #: and on every row written before the field existed.
    executor: ExecutorRecord | None = None
    #: When the solver process started and ended (PFS-2012.08.01), None
    #: where no solver ran and on every row written before the fields.
    started_at: str | None = None
    finished_at: str | None = None
    #: The unsteady export window as resolved for this run, keyed by the
    #: row key that stated it; None until a row key states one
    #: (PFS-2031.18), and on every row written before the field existed.
    #: it also carries the clock the counter program ran with
    #: (PFS-2031.18.01): ``delta_time_s``, the solver time step in seconds,
    #: always; ``step_deg``, the azimuth per step in degrees, on the rotor
    #: run type alone, absent on a rotorless row. A record written before
    #: carries neither, and the series tables leave the time blank for it.
    export_window: ExportThresholdRecord | None = None
    #: Solver surface averaging as emitted, never re-derived from an edited pproc.
    #: Only a record written in legacy releases carries one; none has since.
    surface_time_averaging: SurfaceAveragingWindow | None = None
    #: THE WINDOW THE PACKAGE AVERAGES THE SURFACE OVER (G25), as the
    #: run resolved it from the pproc's ``[time_averaging]``: inclusive time
    #: steps, and the revolutions or iterations asked for. The run exports the
    #: surface at every step of it and the post averages those exports; the post
    #: reads this and never an edited pproc. None where the pproc states none and
    #: on every record written in legacy releases. Adding it did not move
    #: MANIFEST_SCHEMA.
    surface_average_window: SurfaceAverageWindow | None = None
    #: THE TECPLOT SURFACES THE PACKAGE WROTE FROM A VTK (G45), one per
    #: Tecplot output of the point: ``vtk`` and ``dat``, the two names; ``frame``,
    #: the analysis loads frame the solver wrote the VTK in, as the script placed
    #: it (index, origin, axes); ``written``, the Tecplot files written, the end
    #: of the run's first and each step's after it; and ``problems``, one
    #: sentence per file that could not be written. None on every record written
    #: in legacy releases, whose Tecplot is the solver's own, per node, and on a point
    #: that exports none. Adding it did not move MANIFEST_SCHEMA.
    surface_translations: list[dict[str, object]] | None = None
    #: The solver commands the row's setup stated verbatim and the script
    #: carried (PFS-2033.02): ``command``, ``before`` and ``setup`` each;
    #: empty for a setup stating none and for every record written before
    #: the field existed, which the reader takes as the same thing, and
    #: which is why MANIFEST_SCHEMA does not move for it.
    raw_commands: list[RawCommand] = Field(default_factory=list)
    #: Boundary aliases carried by the record so products can resolve groups without reopening the
    #: input artifact. An absent key reads as an empty table.
    aliases: BoundaryAliases = Field(default_factory=dict)
    conditions: list[dict] | None = None

    log_file_used: str | None = None
    #:  where a final residual overflowed its printed field and was read
    #: from an earlier iteration, which column, iteration and value.  and
    #: where the log a residual is read from came from, or why there is none,
    #: on a run the local switch kept on a cluster whose HPC profile states
    #: ``export_log = false``: the log is then the solver's captured output,
    #: written by this package, or absent because the solver printed nothing.
    #: An existing free-text field, so adding the sentence moved no schema.
    residual_note: str | None = None
    #:  what the solver log prints about the run, beside the Python clock
    #: (wall_time_s): its run time and initialization time in seconds, and the
    #: time steps of an unsteady run. None where no log was read.
    solver_run_time_s: float | None = None
    solver_initialization_s: float | None = None
    time_steps: int | None = None
    #: L1, RPT-091: a quasi-steady rotor wheel solved at several
    #: clockings, one verdict per clocking read from that clocking's solve in
    #: the one log the run exports (``index``, ``clocking_deg``, ``status``,
    #: ``iterations``, ``residual``, and a ``note`` or ``error`` where there is
    #: one), in the order the run solved them; the record's status and residual
    #: are the worst of them. Written only where recorded, so every other
    #: record, and MANIFEST_SCHEMA, is unchanged.
    clocking_verdicts: list[dict[str, Any]] | None = None
    #: FR-989: the names this point's row skipped, one ``{artifact, key,
    #: name}`` per name a key of its setup or pproc cites that its study holds
    #: and its model lacks, in the order the build skipped them. Written only
    #: where the row skipped one, so every other record keeps its content and
    #: identity, and MANIFEST_SCHEMA does not move.
    skipped_names: list[dict[str, str]] | None = None
    solver_setup: dict | None = None
    status: RunStatus
    iterations: int | None = None
    #: FR-974: the iteration limit the run requested, written ONLY for
    #: ``MAX_ITER_REACHED`` (``iterations`` is the counter reached); absent from the
    #: record of every other status, so a record keeps its existing content.
    iterations_requested: int | None = None
    residual: float | None = None
    wall_time_s: float | None = None
    outputs: list[str] = Field(default_factory=list)
    #: FR-91. Where this run's probe positions were written, relative to
    #: the simulation folder, or None for a row that declares no probes
    #: and for one whose entry cites a points file the user wrote (the
    #: package does not parse a survey the user authored to re-state it).
    #:
    #: The file is per SIM and every point of the simulation writes the
    #: same bytes to it, because a probe layout is the artifact's and the
    #: row's rather than the sweep point's. Adding it did not move
    #: MANIFEST_SCHEMA: a record written in legacy releases reads None here,
    #: and a post stage meeting one writes the probe table without the
    #: position columns rather than refusing a run that already happened.
    probe_points_file: str | None = None
    #: Emitted sample IDs and field output contract; absent on older runs.
    probe_field_layout: list[dict] | None = None
    #: FR-1047, PFS-2081.58: the far-field plane and lattice this
    #: point's script laid or reused, ``{"shapes": [...]}``, each shape as
    #: :meth:`pyflightstream.cases.workflows.FarfieldShape.record` states it
    #: (kind, added or declared, the entry reused, the point count and the
    #: geometry that rebuilds its points in metres). A steady JOB record keys it
    #: one level up, ``{"by_point": {<point name>: {"shapes": [...]}}}``, and
    #: :meth:`as_points` hands each point its own. Post matches every exported
    #: position to it before integrating. ABSENT where None, so a record of a
    #: row without a far field keeps its existing content.
    farfield_layout: dict[str, Any] | None = None
    #: Native surface-property declarations and plot names; absent on historical records.
    surface_probe_layout: list[dict] | None = None
    #: Final frame trajectories and explicit unknowns; absent on legacy records.
    frame_motions: dict[int, dict] | None = None
    #: Conservative final custom-field coverage; absent when uncomputed or legacy.
    custom_field_coverage: dict | None = None
    #: Explicit source-unit declaration, retained to refuse changed continuation semantics.
    freestream_units: str | None = None
    #: The section distributions this point's script created, in order, each
    #: with its families by name, its plane, its frame and its count.
    #: The EMPTY list where the script added or removed no surface section, and on a
    #: continuation the layout of the run it continues,
    #: whose saved simulation it reopens. None where the layout is not known:
    #: every record written in legacy releases, one whose script changed sections no
    #: run type built (a LEGACY recipe's, a raw command's), and, in legacy releases,
    #: one whose script created none. Its sections table then states `NA` for
    #: the identity of a row rather than a guess.
    sections_layout: list[dict[str, object]] | None = None
    error: str | None = None
    #: FR-309: marking keeps the prior status, timestamp and reason in ``marked``.
    #: FR-400: ``discarded_by`` names the collect option that discarded the point.
    #: Both fields are omitted when unset, so every other record is unchanged.
    marked: dict[str, Any] | None = None
    discarded_by: str | None = None
    #: The two files of a row stating an export threshold (PFS-2031.18),
    #: relative to the simulation folder, and the count the program
    #: reached; None on every record written in legacy releases and on a row
    #: stating no threshold. Adding them did not move MANIFEST_SCHEMA.
    action_program: str | None = None
    action_script: str | None = None
    action_count: int | None = None
    #: Nonfatal run diagnostics, separate from the assessed solver status and
    #: error. In particular, missing per-step action evidence does not invalidate
    #: converged final loads. Recorded by local execution and collection alike.
    warnings: list[str] = Field(default_factory=list)

    @field_validator("surface_time_averaging")
    @classmethod
    def _surface_window_matches_request(
        cls, window: SurfaceAveragingWindow | None
    ) -> SurfaceAveragingWindow | None:
        if window is None:
            return None
        resolved = surface_averaging_window(
            last_step=window["iterations"][1],
            last_iters=window.get("last_iters"),
            last_revs=window.get("last_revs"),
            per_revolution=window.get("steps_per_revolution"),
        )
        if window["iterations"] != resolved["iterations"]:
            fields = (
                "last_iters" if "last_iters" in window else "last_revs and steps_per_revolution"
            )
            raise ValueError(
                f"iterations {window['iterations']} contradict recorded {fields}; "
                f"expected {resolved['iterations']}"
            )
        return window

    @field_validator("surface_average_window")
    @classmethod
    def _package_window_matches_request(
        cls, window: SurfaceAverageWindow | None
    ) -> SurfaceAverageWindow | None:
        if window is None:
            return None
        resolved = surface_average_window(
            last_step=window["iterations"][1],
            last_iters=window.get("last_iters"),
            last_revs=window.get("last_revs"),
            per_revolution=window.get("steps_per_revolution"),
        )
        if window["iterations"] != resolved["iterations"]:
            raise ValueError(
                f"iterations {window['iterations']} contradict the recorded request; "
                f"expected {resolved['iterations']}"
            )
        return window

    @field_validator("points_ran")
    @classmethod
    def _points_ran_entries_are_readable(cls, entries: list[dict]) -> list[dict]:
        """Refuse an entry whose status is no RunStatus or whose tag is no text (PFS-2093.005).

        Read here, so the row is unreadable when the manifest is read, rather
        than a bare ValueError later in every per-point consumer of :meth:`as_points`.
        """
        known = {status.value for status in RunStatus}
        for index, entry in enumerate(entries):
            status = entry.get("status")
            if status is not None and (not isinstance(status, str) or status not in known):
                raise ValueError(
                    f"entry {index} has status {status!r}, which is not a run status this "
                    f"release reads ({', '.join(sorted(known))})"
                )
            tag = entry.get("tag")
            if tag is not None and not isinstance(tag, str):
                raise ValueError(f"entry {index} has tag {tag!r}, and a tag is text")
        return entries

    def as_points(self) -> list[RunRecord]:
        """Return this record as one record per POINT.

        THE MANIFEST STORES JOBS and a steady matrix row is
        one job over several points, so a consumer that reasons per point
        (the physics reduction, a per-point table, an assessor comparing
        angles) would see one point where three ran. Rather than have each
        of them learn the job shape, they ask here.

        A record that is one point returns itself, unchanged and not
        copied, so every caller can use this unconditionally and the
        common path costs nothing.
        """
        if not self.points_ran:
            return [self]
        out: list[RunRecord] = []
        for entry in self.points_ran:
            tag = str(entry.get("tag") or "")
            # A JOB marked failed WHOLE (the mark on the row, as a record marked
            # before mark-failed marked each entry carries it) fails every point
            # that carries no verdict of its own; the entry's own CONVERGED would
            # otherwise hand a failed point to the post, status and re-run as
            # converged. A job FAILED_MARKED because ONE of its points was
            # marked (PFS-2103.009) has no mark on the row, and its other
            # points keep their own status.
            failed_job = (
                self.status == RunStatus.FAILED_MARKED
                and self.marked is not None
                and not entry.get("marked")
            )
            out.append(
                self.model_copy(
                    update={
                        "run_id": f"{self.run_id.rsplit('/', 1)[0]}/{tag}",
                        # The entry's tag is the point name the job
                        # recorded, and a per-point record carries it as such.
                        "point_name": tag or None,
                        "point": dict(entry.get("point") or {}),
                        "status": self.status
                        if failed_job or not entry.get("status")
                        else RunStatus(entry["status"]),
                        "outputs": list(entry.get("outputs") or []),
                        "iterations": entry.get("iterations"),
                        "residual": entry.get("residual"),
                        # The point's own limit and note (FR-977); the job's
                        # note is the excused-log one, or none.
                        "residual_note": entry.get("residual_note") or self.residual_note,
                        "iterations_requested": entry.get(
                            "iterations_requested", self.iterations_requested
                        ),
                        "points_ran": [],
                        # M1: a job keys its Mach numbers by point name.
                        "rotor_mach": (self.rotor_mach or {}).get(tag) or None,
                        # FR-1047: a job keys its far-field layouts by point name.
                        "farfield_layout": ((self.farfield_layout or {}).get("by_point") or {}).get(
                            tag
                        )
                        or None,
                        # FR-414: a person's verdict on one point of the job.
                        "marked": entry.get("marked") or self.marked,
                    }
                )
            )
        return out


#: The tag a JOB's run id ends with, where a point's run id ends with its
#: point tag. Reused rather than invented: the package already names the
#: per-polar product tables by the point convention with the swept
#: variable written literally as ``sweep``, so a reader has met this token
#: and it reads correctly, naming a sweep rather than a point. Its home is
#: here, beside the record it names: the run layer composes
#: the id and the workspace layer reads it (:func:`planned_points_without_record`).
JOB_TAG = "sweep"


def planned_points_without_record(
    planned: Iterable[str], rows: Iterable[Mapping[str, object]]
) -> list[str]:
    """Return the planned run ids no record carries, in the order planned.

    A planned point (``<campaign>/sim_<id>/<point>``, as ``plan.json`` lists it)
    is recorded by a record of its own id; by a record of the same campaign and
    simulation whose id ends with its point, which is a continuation of it; by
    a JOB record of its row (``<campaign>/sim_<id>/sweep``) whose ``points_ran``
    names it; or by a job record that ran no point, which stands for every
    point of its row (a job refused before it ran records them all at once).
    Rows without a ``run_id``, such as a delete-sims note, carry nothing.

    Parameters
    ----------
    planned : iterable of str
        The planned run ids.
    rows : iterable of mapping
        The manifest's rows as written (``runs.json``), or records dumped to
        mappings.

    Returns
    -------
    list of str
        The planned run ids with no record, the points a run never attempted.

    Examples
    --------
    >>> planned_points_without_record(
    ...     ["c/sim_1/J1", "c/sim_1/J2", "c/sim_2/AL+000"],
    ...     [{"run_id": "c/sim_1/J1", "sim_id": "1"},
    ...      {"run_id": "c/sim_2/sweep", "sim_id": "2", "points_ran": []}],
    ... )
    ['c/sim_1/J2']
    """
    points: set[tuple[str, str, str]] = set()
    whole_rows: set[tuple[str, str]] = set()
    for row in rows:
        run_id = row.get("run_id")
        if not isinstance(run_id, str) or "/" not in run_id:
            continue
        campaign, sim = run_id.split("/", 1)[0], str(row.get("sim_id"))
        tag = run_id.rsplit("/", 1)[-1]
        if tag != JOB_TAG:
            points.add((campaign, sim, tag))
            continue
        ran = row.get("points_ran")
        entries = ran if isinstance(ran, list) else []
        if not entries:
            whole_rows.add((campaign, sim))
        for entry in entries:
            if isinstance(entry, Mapping):
                points.add((campaign, sim, str(entry.get("tag") or "")))
    missing: list[str] = []
    for run_id in planned:
        parts = run_id.split("/")
        campaign, tag = parts[0], parts[-1]
        sim = parts[1].removeprefix("sim_") if len(parts) > 2 else ""
        if (campaign, sim, tag) in points or (campaign, sim) in whole_rows:
            continue
        missing.append(run_id)
    return missing


#: THE EXTRACTION MANIFEST of the additional post (G12), a file of its
#: own beside ``runs.json`` at the workspace root. NOT a row of ``runs.json``, for
#: four reasons: the original run record must stay as it was written, so the
#: manifest of runs is never opened for writing by an extraction; an extraction
#: is not a run (no solve, no convergence verdict, no setup); every reader of
#: ``runs.json`` takes a row there as a run of its point (a sweep-table row, a
#: continuation's predecessor, a resume identity); and a row carrying keys a
#: a legacy reader does not know makes it refuse the WHOLE manifest, while this
#: file is simply unread by it.
ADDITIONAL_MANIFEST = "additional.json"

#: Layout identifier of an extraction record, with the rule of
#: :data:`MANIFEST_SCHEMA`: bumped when a field is removed or changes meaning.
ADDITIONAL_MANIFEST_SCHEMA = "pyfs-additional/1"


class ExtractionStatus(enum.StrEnum):
    """Status of one extraction of the additional post (G12).

    There is no convergence verdict among them: an extraction solves nothing,
    so it is judged by its process and by the files it declared.
    """

    #: Submitted to a scheduler; not yet evidence that extraction completed.
    SUBMITTED = "SUBMITTED"
    #: Every declared file was written and hashed.
    EXTRACTED = "EXTRACTED"
    #: The process failed, or the original saved simulation moved during it.
    FAILED_EXECUTION = "FAILED_EXECUTION"
    #: The process ended and a declared file is missing.
    FAILED_INCOMPLETE_OUTPUT = "FAILED_INCOMPLETE_OUTPUT"


class AdditionalRecord(BaseModel):
    """One extraction of the additional post: a saved simulation reopened, with no solve.

    Written to :data:`ADDITIONAL_MANIFEST` and never to ``runs.json``, so the
    point's own record stays exactly as its run wrote it. Every path is
    relative to the point's simulation folder, as a run record's are.

    Attributes
    ----------
    manifest_schema : str
        :data:`ADDITIONAL_MANIFEST_SCHEMA`.
    extraction_id : str
        ``<point run_id>/additional/<pproc id>``, the identity of this
        extraction; the LATEST record of an identity is the one that counts.
    run_id : str
        The point's run id, as :meth:`RunRecord.as_points` names it.
    job_id : str or None
        The run id of the job record the point belongs to, for a steady row
        run as one job; None for a point recorded on its own.
    sim_id, point_name, matrix_stem : str or None
        Copied from the point's record.
    pproc : str
        The ADDITIONAL pproc id, which the products are marked with.
    pproc_sha256 : str or None
        sha256 of ``inputs/pproc/<pproc>.toml`` when the extraction ran, so an
        artifact edited since is extracted again.
    fsm : str
        The point's saved simulation, as its record names it.
    fsm_sha256 : str
        Its sha256 in the point's record, which the file on disk matched and
        the copy the solver opened matched too.
    fsm_sha256_after : str or None
        The ORIGINAL file hashed again after the launch; it equals
        ``fsm_sha256`` or the extraction is recorded failed.
    unsteady : bool
        Whether the point marched in time; its extraction is then one instant,
        the last.
    note : str or None
        What a reader of the extraction must know: the one-instant sentence on
        an unsteady point.
    fs_version_requested, fs_exe, fs_exe_sha256 : str or None
        The build the extraction was emitted under and run on.
    package_version, package_commit, package_dirty
        As on a run record.
    script_path, script_sha256 : str
        The extraction script, under ``scripts/additional/<pproc>/``.
    working_dir : str
        Where the solver ran and wrote: ``datapoints/DP-<point>/additional/<pproc>``.
    argv, cwd, timeout_s, executor, started_at, finished_at, wall_time_s
        How the solver was called, as on a run record.
    status : ExtractionStatus
        The terminal status.
    error : str or None
        Why a failed extraction failed.
    outputs : list of str
        The files written, relative to the simulation folder.
    outputs_sha256 : dict of str to str
        sha256 of each, keyed by the same name.
    sections_layout : list of dict
        Which rows of the sections exports are which distribution: the run's
        own layout first, then the additional pproc's blocks, numbered on after
        the run's and marked with the pproc (RPT-062: a reopened export carries
        the run's distributions first and the new ones after them).
    leading_sections : int
        How many rows at the head of those exports are the run's own.
    frames : dict
        The frames the extraction cited, by name, as the run created them.
    inventory : list of str or None
        The boundary names the saved simulation holds, in the solver's order.
    surface_translations : list of dict or None
        The Tecplot surfaces the package wrote from the extraction's VTK
        (G45), as a run record states them.
    """

    model_config = ConfigDict(extra="forbid")

    manifest_schema: str = ADDITIONAL_MANIFEST_SCHEMA
    extraction_id: str
    run_id: str
    job_id: str | None = None
    sim_id: str
    point_name: str | None = None
    matrix_stem: str | None = None
    pproc: str
    pproc_sha256: str | None = None
    fsm: str
    fsm_sha256: str
    fsm_sha256_after: str | None = None
    unsteady: bool = False
    note: str | None = None
    fs_version_requested: str
    fs_exe: str | None = None
    fs_exe_sha256: str | None = None
    package_version: str
    package_commit: str | None = None
    package_dirty: bool | None = None
    script_path: str
    script_sha256: str
    working_dir: str
    argv: list[str] = Field(default_factory=list)
    cwd: str | None = None
    timeout_s: float | None = None
    executor: ExecutorRecord | None = None
    started_at: str | None = None
    finished_at: str | None = None
    wall_time_s: float | None = None
    status: ExtractionStatus
    #: Output names relative to working_dir that a submitted extraction must produce.
    declared_outputs: list[str] = Field(default_factory=list)
    #: Verified private copy retained until collection.
    reopened_copy: str | None = None
    #: Scheduler receipt; submission is not evidence that extraction completed.
    submission: dict[str, object] | None = None
    #: Whether the script exports a solver log; native cluster logs stay native when false.
    exports_log: bool = True
    error: str | None = None
    outputs: list[str] = Field(default_factory=list)
    outputs_sha256: dict[str, str] = Field(default_factory=dict)
    sections_layout: list[dict[str, object]] = Field(default_factory=list)
    leading_sections: int = 0
    frames: dict[str, int | dict[str, int] | None] = Field(default_factory=dict)
    inventory: list[str] | None = None
    #: The Tecplot surfaces the extraction wrote from its VTK (G45), as
    #: :attr:`RunRecord.surface_translations` states them.
    surface_translations: list[dict[str, object]] | None = None


#: Filesystem link operations share the implementation in
#: :mod:`pyflightstream.workspace._links`.


class _ManifestWorkspace(Protocol):
    """The paths and operations a manifest writer reads from its owner."""

    root: Path

    @property
    def manifest_path(self) -> Path: ...

    def _manifest_lock(self, manifest: Path | None = None) -> AbstractContextManager[None]: ...

    def read_raw_manifest(self) -> list[dict]: ...

    def _replace_manifest(self, raw: list[dict]) -> None: ...

    def _refuse_a_waiver_this_version_may_not_write(self, record: RunRecord) -> None: ...


@contextmanager
def manifest_lock(
    manifest: Path,
    *,
    root: Path,
    timeout_s: float,
    renew_s: float,
    stale_s: float,
    poll_s: float,
) -> Iterator[None]:
    """Hold the manifest's read-modify-replace under an owned, renewable lease.

    ``manifest`` is the file the lease guards, ``runs.json`` unless named:
    the extraction manifest of the additional post (G12) takes a lease of
    its own under the same rules, ``additional.json.lock``, so an extraction
    never holds or waits on the lease of the runs.

    ``runs.json.lock`` records the PID, host and a unique token. A background
    heartbeat updates its modification timestamp every five seconds. A waiter
    recovers it only for a confirmed dead local PID or after 300 seconds with
    no renewal; elapsed time since acquisition alone never expires a lease.
    Legacy PID-only files have no verifiable host and use the same stale bound.

    A persistent ``.runs.json.lock.guard`` serialises the brief ownership
    checks, renewal and removal using an OS byte/file lock. It is never
    deleted: replacing its inode would split the arbitration between waiters.
    The OS releases this guard if its process dies. The filesystem must honour
    these locks across clients (SMB/NFS deployments must support locking), and
    hosts must synchronise clocks for the stale-heartbeat fallback. No guard
    is held while the manifest is being read or rewritten.

    A release removes only its own token, including on a refused write.

    Parameters
    ----------
    manifest : Path
        The manifest file whose lease is acquired.
    root : Path
        The workspace directory, created before acquiring the lease.
    timeout_s : float
        Maximum wait in seconds for another writer or the arbitration guard.
    renew_s : float
        Seconds between heartbeat renewals while the lease is held.
    stale_s : float
        Seconds without renewal after which a lease may be recovered.
    poll_s : float
        Seconds between acquisition attempts.

    Yields
    ------
    None
        Control to the writer while it owns the lease.

    Raises
    ------
    WorkspaceError
        If another writer holds the manifest for the configured wait bound.
    """
    root.mkdir(parents=True, exist_ok=True)
    guarded = manifest
    lock = guarded.with_suffix(".json.lock")
    guard = lock.with_name(f".{lock.name}.guard")
    owner = {"pid": os.getpid(), "host": socket.gethostname(), "token": uuid.uuid4().hex}

    @contextmanager
    def arbitrate() -> Iterator[None]:
        # Only metadata operations hold this OS lock, never the slow writer.
        with guard.open("a+b") as handle:
            if os.fstat(handle.fileno()).st_size == 0:
                handle.write(b"0")
                handle.flush()
            until = time.monotonic() + timeout_s
            while True:
                try:
                    handle.seek(0)
                    if sys.platform == "win32":
                        import msvcrt

                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    if time.monotonic() > until:
                        raise WorkspaceError(
                            f"the manifest guard {guard} stays held; the record was NOT written"
                        ) from None
                    time.sleep(poll_s)
                else:
                    break
            try:
                yield
            finally:
                handle.seek(0)
                if sys.platform == "win32":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def read_owner() -> dict:
        try:
            value = json.loads(lock.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    def dead_local_holder(holder: dict) -> bool:
        pid = holder.get("pid")
        if holder.get("host") != owner["host"] or not isinstance(pid, int) or pid <= 0:
            return False
        if pid == os.getpid():
            return False
        if sys.platform == "win32":
            # os.kill(pid, 0) can terminate a process on Windows. Query only.
            import ctypes
            from ctypes import wintypes

            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.GetExitCodeProcess.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(wintypes.DWORD),
            ]
            kernel.GetExitCodeProcess.restype = wintypes.BOOL
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            process = kernel.OpenProcess(0x1000, False, pid)
            if not process:
                return ctypes.get_last_error() == 87  # ERROR_INVALID_PARAMETER: no such PID
            try:
                code = wintypes.DWORD()
                return (
                    bool(kernel.GetExitCodeProcess(process, ctypes.byref(code)))
                    and code.value != 259
                )
            finally:
                kernel.CloseHandle(process)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except OSError:
            pass  # Permission denied is not proof that the process is gone.
        return False

    deadline = time.monotonic() + timeout_s
    while True:
        with arbitrate():
            if lock.exists():
                holder = read_owner()
                if dead_local_holder(holder) or time.time() - lock.stat().st_mtime > stale_s:
                    lock.unlink()
            try:
                with _textio.open_text(lock, "x") as handle:
                    handle.write(json.dumps(owner) + "\n")
            except (FileExistsError, PermissionError):
                pass
            else:
                break
        if time.monotonic() > deadline:
            raise WorkspaceError(
                f"the manifest {guarded} has been held by another writer "
                f"for {timeout_s:.0f} s ({lock} exists), so this record "
                "was NOT written. The lock is recovered only after its local owner "
                "exits or its heartbeat expires; retry after the holder finishes."
            )
        time.sleep(poll_s)

    stopped = threading.Event()

    def renew() -> None:
        while not stopped.wait(renew_s):
            try:
                with arbitrate():
                    if read_owner() != owner:
                        return
                    os.utime(lock, None)
            except (OSError, WorkspaceError):
                # A transient filesystem refusal can be retried next period.
                continue

    heartbeat = threading.Thread(target=renew, name="pyfs-manifest-heartbeat", daemon=True)
    try:
        heartbeat.start()
        yield
    finally:
        stopped.set()
        if heartbeat.ident is not None:
            heartbeat.join()
        with arbitrate():
            if read_owner() == owner:
                lock.unlink()


def append_record(workspace: _ManifestWorkspace, record: RunRecord) -> None:
    """Append one record to the manifest, atomically.

    The manifest is rewritten through a temporary file and an
    atomic replace, so a crash never leaves it half-written; a
    duplicate ``run_id`` is rejected because the manifest is the
    run identity (PP-6).

    Existing rows are carried across AS THEY WERE WRITTEN.
    REV010-014: do not re-serialize existing rows through validated models,
    which would add defaults and a manifest_schema not recorded by their
    writer. Historical evidence is not this method's to edit; migrating a
    manifest is a separate, deliberate, auditable act.

    Parameters
    ----------
    workspace : CampaignWorkspace
        The owner of the manifest and its read and write operations.
    record : RunRecord
        The new run to append, with a unique ``run_id``.

    Raises
    ------
    WorkspaceError
        If the ``run_id`` is already in the manifest, or if the
        record carries a waiver row that this version may not write:
        one whose ``source_version`` names no build, or one under any
        stamp but :data:`MANIFEST_SCHEMA`. Refused before anything is
        written, because the row would be one
        :meth:`read_manifest` refuses and nothing here migrates a
        manifest (PFS-2012.03).

    Examples
    --------
    Append a synthetic record to a temporary workspace without a solver:

    >>> from tempfile import TemporaryDirectory
    >>> from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
    >>> from pyflightstream.workspace.manifest import append_record
    >>> record = RunRecord(
    ...     run_id="demo/sim_1/AL+000", sim_id="1",
    ...     fs_version_requested="25.0", package_version="0.36.0",
    ...     script_sha256="0" * 64, raw_flag=False, status=RunStatus.SUBMITTED,
    ... )
    >>> with TemporaryDirectory() as directory:
    ...     workspace = CampaignWorkspace(directory)
    ...     append_record(workspace, record)
    ...     workspace.read_manifest()[0].run_id == record.run_id
    True
    """
    workspace._refuse_a_waiver_this_version_may_not_write(record)
    with workspace._manifest_lock():
        raw = workspace.read_raw_manifest()
        if any(entry.get("run_id") == record.run_id for entry in raw):
            raise WorkspaceError(
                f"run_id {record.run_id!r} is already in the manifest; run identity "
                "must be unique. Use a new run_id or archive the campaign first."
            )
        raw.append(record.model_dump(mode="json"))
        workspace._replace_manifest(raw)


def supersede_records(
    workspace: _ManifestWorkspace, run_ids: Sequence[str], *, stamp: datetime | None = None
) -> Path | None:
    """Copy the manifest into ``archive/`` and take the named rows out of it.

    For a FORCED RE-RUN: a point whose matrix row was wrong keeps its
    identity when the correction does not change its name, so the recorded
    row has to leave before the point can run again. The copy is made FIRST
    and the write is atomic, so there is no instant at which the workspace
    holds neither the old manifest nor a whole one.

    THE COPY GOES WHERE THIS PACKAGE ALREADY PUTS ONE. ``pyfs-matrix
    rename`` archives the manifest to ``archive/runs-<stamp>.json`` before
    rewriting it, and a second home for one artifact name is how a reader
    who knows the first never finds the second.

    Parameters
    ----------
    workspace : CampaignWorkspace
        The owner of the manifest and its read and write operations.
    run_ids : sequence of str
        The run identities to remove. One that the manifest does not hold
        is not an error here: the caller decides what an unmatched name
        means, and for a forced re-run it refuses before reaching this.
    stamp : datetime, optional
        The moment the copy is named for. Injected so a test does not race
        the clock; the default is now.

    Returns
    -------
    Path or None
        Where the manifest was copied, or None when there is no manifest
        to copy, which is a workspace nothing has run in yet.
    """
    if not workspace.manifest_path.is_file():
        return None
    (workspace.root / ARCHIVE_DIR).mkdir(parents=True, exist_ok=True)
    # The spelling has one home, which restore reads: archive/runs-<stamp>.json,
    # numbered .2, .3 when two supersedes share one stamp window, so the older
    # copy, the state before either change, is never overwritten.
    target = free_root_archive(
        workspace.root,
        workspace.manifest_path.name,
        (stamp or datetime.now()).strftime(ARCHIVE_STAMP),
    )
    shutil.copy2(workspace.manifest_path, target)

    superseded = set(run_ids)
    with workspace._manifest_lock():
        kept = [
            row
            for row in workspace.read_raw_manifest()
            if str(row.get("run_id", "")) not in superseded
        ]
        workspace._replace_manifest(kept)
    return target


def complete_submitted_record(workspace: _ManifestWorkspace, record: RunRecord) -> None:
    """Replace a SUBMITTED row with the completed run it became (FR-99).

    THE ONE METHOD THAT REWRITES A ROW, and the narrowness is the
    whole design. :meth:`append_record` carries existing rows across
    AS THEY WERE WRITTEN because historical evidence is not this
    class's to edit; a manifest that any code may rewrite is a
    manifest whose rows are opinions.

    A ``SUBMITTED`` row is the ONE deliberate exception, and it is an
    exception in a precise sense: it is not a finished record that a
    later reading disagrees with, it is a record that says in its own
    status that the run has not come back yet. Completing it is not
    editing evidence. It is the evidence ARRIVING.

    So the refusal is on the existing row rather than on the new one:
    a row in any other status is a run that finished, and this
    refuses to touch it whatever the caller passes. That is what
    stops this method becoming the general-purpose rewrite that
    `append_record`'s docstring exists to prevent.

    Parameters
    ----------
    workspace : CampaignWorkspace
        The owner of the manifest and its read and write operations.
    record : RunRecord
        The completed record replacing the row with the same ``run_id``.

    Raises
    ------
    WorkspaceError
        When the manifest holds no row with that ``run_id``, or when
        the row it holds is not ``SUBMITTED``. Both name the run and
        the status found, because a collector pointed at the wrong
        workspace and a collector pointed at a finished run are
        different mistakes and the message has to tell them apart.
    """
    with workspace._manifest_lock():
        raw = workspace.read_raw_manifest()
        for index, entry in enumerate(raw):
            if entry.get("run_id") != record.run_id:
                continue
            was = str(entry.get("status"))
            if was != str(RunStatus.SUBMITTED):
                raise WorkspaceError(
                    f"refusing to complete run {record.run_id!r}: the manifest records "
                    f"it {was}, not {RunStatus.SUBMITTED}. Only a submitted run is "
                    "completed later; every other row is a run that finished, and this "
                    "is not the method that edits one."
                )
            raw[index] = record.model_dump(mode="json")
            workspace._replace_manifest(raw)
            return
    raise WorkspaceError(
        f"refusing to complete run {record.run_id!r}: the manifest at "
        f"{workspace.manifest_path} holds no row with that run_id."
    )


# Preserve public identities after Pydantic has resolved the record annotations.
RunStatus.__module__ = "pyflightstream.workspace"
ExecutorRecord.__module__ = "pyflightstream.workspace"
BrokenCommandRecord.__module__ = "pyflightstream.workspace"
RunRecord.__module__ = "pyflightstream.workspace"
ExtractionStatus.__module__ = "pyflightstream.workspace"
AdditionalRecord.__module__ = "pyflightstream.workspace"
