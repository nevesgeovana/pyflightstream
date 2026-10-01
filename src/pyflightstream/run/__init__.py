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
because the identity rows are the record of what was attempted. The
exception is a call that submitted points to a scheduler: a queued point
has no outputs yet, so that call writes no product and no table and
names the ``pyfs-matrix collect`` command that posts once they land.

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
the point's own datapoint folder and captures that file (SRC-003 p.280);
a steady row of several points is one job and runs in the simulation
folder. A cluster route shares the executor interface:
:class:`SubmittingExecutor` hands the script to a scheduler and returns
once the record is written SUBMITTED, and the collect stage of
:mod:`pyflightstream.run.collect` completes that record when the
declared outputs have landed (FR-99). FR-15, the HPC executor
requirement, stays pending until the submitting half is measured on a
cluster.

On Windows, :mod:`pyflightstream.run._solver_windows` inspects only the
launched solver PID. A visible standard dialog, a modal window whose owned
parent is disabled, or a titled error window fails that point. Its text goes
to ``pyfs-modal-error.log`` and the execution record; the executor terminates
only its own process and never clicks a dialog. Custom GUI messages outside
these recognizable forms remain subject to the configured execution timeout.

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

Since 0.32, :mod:`pyflightstream.run.records` holds the operations on the
records themselves: which manifest a command reads (``runs.json``, or
another file of the workspace root named by ``--runs``; resolved in
:mod:`pyflightstream.workspace.naming` since 0.33.0), the exact restore
of a records file from the workspace's archive (``pyfs-matrix restore``),
and the rebuild of run records from the folders under ``sims/``
(``pyfs-matrix rebuild``), which runs each row again in a throwaway copy
with nothing submitted, accepts a record only when the executed script is
the one this version renders, completes it read-only and marks it
``REBUILT``. It also assembles the in-memory records of
``pyfs-matrix post --from-sims``.

THIS ROOT IS A FACADE since 0.33.0 (AD-14): the definitions are in private
modules of the package, in this order from the top, each importing only the
ones after it: :mod:`~pyflightstream.run._campaign` (the loop),
``_sweep`` (a steady row run as one job), ``_points`` (one point),
``_pending`` (the files written before the solver starts), ``_plan`` (the
plan, its cost and its receipt), ``_continuation``, ``_identity`` (the
package and the solver build, and :func:`reconstruct`), ``_assessment``,
``_executors`` and ``_ids`` (the run ids and :class:`CampaignErrors`). Every
name keeps its 0.32.0 path here.

The records family is cut the same way since 0.33.0 (AD-11):
:mod:`pyflightstream.run.records` keeps the restore and the mark-failed and
re-exports the rest from ``_rebuild`` (the rebuild), ``_rebuild_evidence``
(what a rebuild reads and compares), ``_assemble`` (the in-memory records of
``--runs`` and ``--from-sims``) and ``_record_files`` (the record files,
their archives and lease), and it registers its rebuild with
:mod:`pyflightstream.workspace.storage` when it loads, so the workspace row
never imports this one. The ``pyfs-matrix`` argument parser, every
subcommand, option and help text, is ``_cli_parsers``;
:mod:`pyflightstream.run.cli` keeps the commands.
"""

from __future__ import annotations

from pyflightstream.run._assessment import (
    Assessment,
    LoadsAssessor,
    OutcomeAssessor,
)
from pyflightstream.run._assessment import (
    worse_of as worse_of,
)
from pyflightstream.run._campaign import (
    FS_VERSION_FROM_DEFAULT,
    FS_VERSION_FROM_ROW,
    SWEEP_TABLE_NAME,
    run_campaign,
)
from pyflightstream.run._continuation import (
    continuation_run_id as continuation_run_id,
)
from pyflightstream.run._continuation import (
    resolve_continuation as resolve_continuation,
)
from pyflightstream.run._continuation import (
    workflow_conventions_for as workflow_conventions_for,
)
from pyflightstream.run._continuation_frame import CONTINUABLE as CONTINUABLE
from pyflightstream.run._executors import (
    PROGRESS_EVERY_DEFAULT as PROGRESS_EVERY_DEFAULT,
)
from pyflightstream.run._executors import (
    SCRIPT_ARGUMENT,
    ExecutionResult,
    Executor,
    ExecutorConfigurationError,
    LocalExecutor,
    SolverBuild,
    SubmittingExecutor,
    SurfaceMeshExportError,
    action_count,
    bind_submission_values,
    describe_invocation,
    export_surface_mesh,
    invocation_record,
    on_a_cluster,
    render_descriptor,
)
from pyflightstream.run._executors import (
    STEADY_COUPLED_STDERR as STEADY_COUPLED_STDERR,
)
from pyflightstream.run._executors import (
    STEADY_COUPLED_STDOUT as STEADY_COUPLED_STDOUT,
)
from pyflightstream.run._executors import (
    STEADY_COUPLED_STOP_LOG as STEADY_COUPLED_STOP_LOG,
)
from pyflightstream.run._executors import (
    Submitting as Submitting,
)
from pyflightstream.run._identity import (
    ACCEPT_UNREGISTERED_BUILD_FLAG,
    Reconstruction,
    check_solver_identity,
    package_vcs_state,
    reconstruct,
)
from pyflightstream.run._ids import (
    JOB_TAG as JOB_TAG,
)
from pyflightstream.run._ids import (
    ONE_JOB_RECIPE as ONE_JOB_RECIPE,
)
from pyflightstream.run._ids import (
    CampaignErrors,
)
from pyflightstream.run._ids import (
    runs_as_one_job as runs_as_one_job,
)
from pyflightstream.run._plan import (
    MARKER as MARKER,
)
from pyflightstream.run._plan import (
    PLAN_REQUIRED_MESSAGE,
    CampaignPlan,
    PlannedPointCost,
    PlanStatus,
    PointPlan,
    estimate_point_cost,
    format_cost_table,
    plan_campaign,
    plan_receipt_error,
    point_costs,
)
from pyflightstream.run._plan import (
    inflow_harmonics_line as inflow_harmonics_line,
)
from pyflightstream.run._plan import (
    qsteady_validity_line as qsteady_validity_line,
)
from pyflightstream.run._plan import (
    rotor_mach_line as rotor_mach_line,
)
from pyflightstream.workspace import ExecutorRecord


def __getattr__(name: str) -> object:
    """Refuse the removed plot assessor with its migration instruction."""
    if name == "assess_unsteady_from_plots":
        raise ImportError(
            "assess_unsteady_from_plots was removed in 0.26.0; use LoadsAssessor for "
            "campaign assessment; history settling is the user's own analysis."
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "action_count",
    "bind_submission_values",
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
