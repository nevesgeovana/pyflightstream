"""The campaign loop: :func:`run_campaign` and what it leaves behind.

Private to :mod:`pyflightstream.run`, which re-exports every public name
of it. This module composes the case preparation, the point and sweep
paths and the plan's collision checks into the loop that lands every
campaign point in the manifest with exactly one terminal status (PP-5,
FR-14), raises :class:`~pyflightstream.run.CampaignErrors` after the loop,
and leaves the sweep table and the products of a campaign that recorded a
point (PFS-2014.03). It sits at the top of the package order: nothing of
the package imports it but the root.
"""

from __future__ import annotations

import random
import time
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

import pyflightstream

# The cold-start question is asked through its module, so a caller that
# replaces the answer replaces it for the run loop too.
import pyflightstream.run._ids as _ids
from pyflightstream._digest import (
    file_sha256,
)
from pyflightstream._errors import (
    PyflightstreamWarning,
)
from pyflightstream._progress import (
    record_activity,
    terminal_glob,
    terminal_path,
    terse_terminal,
    workspace_activity,
)
from pyflightstream.cases import (
    Campaign,
    CampaignConfigError,
    ScriptRecipe,
    SimCase,
    check_recipe,
    point_name,
    resolve_recipe,
)
from pyflightstream.cases.workflows import (
    RESTART_FROM_VARIABLE,
    RESTART_ITERATIONS_VARIABLE,
)
from pyflightstream.results.tables import sweep_table, write_table
from pyflightstream.run._assessment import (
    OutcomeAssessor,
)
from pyflightstream.run._continuation import (
    _unused_continuation_run_id,
    queued_points,
    resolve_continuation,
)
from pyflightstream.run._continuation_frame import (
    pending_restart_points,
    restart_request,
)
from pyflightstream.run._executors import (
    Executor,
    SolverBuild,
    Submitting,
    _clock,
)
from pyflightstream.run._identity import (
    _case_build,
    _check_scheduled_builds,
)
from pyflightstream.run._ids import (
    CampaignErrors,
    _is_one_job,
    _job_run_id,
    _points_the_recorded_job_ran,
    _run_id,
    _say,
    already_recorded_error,
)
from pyflightstream.run._plan import (
    _output_collision,
    _staged_inputs_conflict,
)
from pyflightstream.run._points import (
    _bare_record,
    _execute_point,
    _PointProgress,
    _record_of_an_unwritable_point,
    _unwritable,
)
from pyflightstream.run._sweep import (
    _execute_sweep,
)
from pyflightstream.versions import resolve
from pyflightstream.workspace import (
    MANIFEST_SCHEMA,
    CampaignWorkspace,
    RunRecord,
    RunStatus,
    WorkspaceError,
    planned_points_without_record,
    post_stages,
)
from pyflightstream.workspace.naming import (
    PointName,
)

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


def _leave_sweep_table(
    workspace: CampaignWorkspace,
    matrix_stem: str | None,
    target: str | Path | None = None,
) -> str | None:
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
    matrix_stem : str or None
        The run matrix's file name without extension, which names the
        ``post/<matrix>/`` folder; None for a campaign authored in Python.
    target : str or Path, optional
        Where the caller chose to have the table INSTEAD of the default
        place. The table is written once: a chosen path replaces the default
        one and is never a copy beside it.

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
    target = (
        Path(target) if target is not None else workspace.sweep_dir(matrix_stem) / SWEEP_TABLE_NAME
    )
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


@workspace_activity("run")
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
    sweep_csv: str | Path | None = None,
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
    preflight : bool
        With True (the default), every installation that still has work is
        asked which build it is before the first point executes, and the
        whole campaign is refused when one answers wrongly. With False the
        identity check is skipped; the parse-time cross-check of each
        result against the registered build still applies.
    name_from : str, optional
        Where the campaign name came from, ``option`` or ``directory``,
        recorded in every run record; None when the caller does not say.
    quiet : bool
        With True, the progress lines, the per-row lines and the closing
        summary table are not printed; the activity log still receives
        them. Default False.
    accept_unregistered_build : bool
        With True, an installed build other than the one registered for the
        version a row names is accepted instead of refused by the identity
        check, and every record of the run says the flag was used.
        Default False.
    sweep_csv : str or Path, optional
        Where to leave the campaign's sweep table instead of
        ``post/<matrix stem>/`` under :data:`SWEEP_TABLE_NAME`. ONE table is
        written either way: a chosen path replaces the default one, so the
        command line's ``--sweep-csv`` never leaves a second copy.

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
    # One status per POINT this call ran, for the closing table (G43): a job is
    # one record and several points, and the table counts points.
    outcomes: list[str] = []
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
        # `plan_campaign` asks the same question of the same helper, so what
        # the plan calls READY is what this runs.
        ran = _points_the_recorded_job_ran(campaign, case, manifest)
        if ran is not None:
            already = [_job_run_id(campaign, case)]
            # WHICH POINTS THE JOB ACTUALLY RAN, read off its record, and
            # not "all of them because the job id is there". A sweep
            # extended from two angles to three and re-run with resume
            # returned successfully having executed NOTHING: the branch
            # discarded every requested point on the strength of the job
            # id alone, and a user reads that as done. Found by the
            # independent Codex review of `main`, 2026-09-13
            # (GEO-047-C05); `points_ran` is what it is for.
            remaining = [point for point in case_points if point_name(case, point) not in ran]
            case_points = remaining
            run_ids = [_run_id(campaign, case, point) for point in remaining]
        # A ROW STATING RESTART CONTINUES WHAT IS RECORDED, so its recorded
        # points are its subject and not a fork (GOAL-021).
        # Until 0.18.1 such a row, under the campaign that recorded
        # the stopped run, was refused as a fork without `resume` and skipped
        # as done with it, and ran only under another campaign name. A point
        # of it is pending when the most recent record of that point stopped
        # continuably, when nothing records it at all, or when its most recent
        # run FAILED, and in the last two the continuation resolver refuses it
        # by name rather than skipping it in silence (the quality and V&V
        # lenses, closing round). FR-96, 0.33.0: a CONVERGED march continues
        # once per request (`continuation_verdict`), so a completed continuation
        # is not continued again, and a point not continued is said.
        continuing = restart_request(case) is not None
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
                # G37 of 0.28.0: A POINT OF A RECORDED JOB REDOES THE WHOLE JOB, which
                # the paragraph above promised and the code did not do for a point
                # name or a point's run_id: the job's record was archived and the
                # named point ran alone, cold, leaving its siblings in no record. The
                # selection is resolved here, before anything is archived, and said.
                if job in recorded_here and job not in asked.named:
                    case_points = list(case.sweep.points())
                    warnings.warn(
                        f"force_rerun names {', '.join(sorted(asked.named))}, a point of the "
                        f"recorded job {job!r}; a job is indivisible, so every point of it "
                        "runs again as one job: "
                        + ", ".join(point_name(case, point) for point in case_points)
                        + ".",
                        PyflightstreamWarning,
                        stacklevel=2,
                    )
                run_ids = [_run_id(campaign, case, point) for point in case_points]
                # THE JOB AND EVERY POINT OF IT RECORDED ON ITS OWN. A row extended
                # after its job ran records the new point by itself (--resume); the
                # job's re-run runs that point too, so its record goes with the job's
                # rather than staying active beside the replacement (reading A28).
                # Read off the manifest, not `already`: a recorded job's `already`
                # is the job's id alone.
                superseding = [job] if job in recorded_here else []
                superseding += [
                    run_id for run_id in run_ids if run_id in recorded and run_id != job
                ]
                # A POINT STILL IN A QUEUE IS NOT REDONE: its job has not finished
                # writing its folder, and archiving the record it will be collected
                # into would leave the job writing where the new run writes.
                queued = queued_points(workspace, manifest, superseding)
                if queued:
                    raise WorkspaceError(
                        f"force_rerun names {', '.join(queued)}, which is still in a "
                        "scheduler's queue (SUBMITTED): its job has not finished writing its "
                        "folder, and redoing it now would archive the record the job will be "
                        "collected into and write where the job writes. Collect it "
                        "(pyfs-matrix collect) first; nothing was archived or run."
                    )
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
            # FR-327: the refusal counts the recorded points and the ones --resume runs.
            raise already_recorded_error(campaign, manifest, already[0], workspace.root)
        if continuing:
            pending = pending_restart_points(
                case,
                list(zip(case_points, run_ids, strict=True)),
                workspace,
                lambda text: _say(text, quiet=quiet),
            )
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
        # A SIMULATION FOLDER HOLDS ONE CAMPAIGN'S QUEUED WORK. The folder carries
        # no campaign name, so another campaign's row with this simulation id
        # stages its inputs, writes its scripts and runs its points in the very
        # folder a queued job of the first will read: staging re-links or
        # re-copies inputs/, whatever the executor. Refused before anything is
        # prepared, while that work is in a queue.
        foreign = sorted(
            record.run_id
            for record in manifest.values()
            if record.sim_id == case.sim_id
            and record.status is RunStatus.SUBMITTED
            and not record.run_id.startswith(f"{campaign.name}/")
        )
        if foreign:
            raise WorkspaceError(
                f"simulation {case.sim_id} holds another campaign's work in a scheduler's "
                f"queue ({', '.join(foreign[:3])}{', ...' if len(foreign) > 3 else ''}), and "
                "a simulation's folder holds one campaign's queued work: its staged inputs, "
                "its scripts and its datapoint folders are what those jobs will read. "
                f"Collect it (pyfs-matrix collect) before campaign {campaign.name!r} runs "
                "there, or give this row another simulation id. Nothing was run or written."
            )
        # A QUEUED POINT OF THIS SIMULATION READS THE STAGED INPUTS TOO, whether or
        # not this request names it: a job still in a queue opens the copy in
        # inputs/ when it starts, so staging other bytes over it now would give
        # it a file its record does not hash.
        queued_here = [
            record.run_id
            for record in manifest.values()
            if record.sim_id == case.sim_id
            and record.status is RunStatus.SUBMITTED
            and record.run_id not in already
        ]
        # AND STAGING CHANGES NOTHING THE QUEUED JOB OPENS: the junction to the
        # library is retargeted when this row's geometry sits in another folder,
        # which swaps every file of inputs/ at once, whatever its name (9r).
        queued_in_sim = [
            record.run_id
            for record in manifest.values()
            if record.sim_id == case.sim_id and record.status is RunStatus.SUBMITTED
        ]
        if queued_in_sim and case.geometry is not None:
            change = workspace.staging_would_change(case.sim_id, [case.geometry])
            if change is not None:
                raise WorkspaceError(
                    f"cannot run {campaign.name}/sim_{case.sim_id}: "
                    f"{queued_in_sim[0]!r} is still in a scheduler's queue and opens "
                    f"this simulation's inputs when it starts, and {change}. Collect it "
                    "first (pyfs-matrix collect), or run this row with the geometry the "
                    "queued point staged; nothing was run."
                )
        if already or queued_here:
            # Partially recorded: some points ran against the inputs staged
            # last time. Re-staging different content would silently retire
            # the evidence behind those records, so the inputs are verified
            # rather than overwritten.
            conflict = _staged_inputs_conflict(
                campaign, case, workspace, manifest, [*already, *queued_here], set(queued_here)
            )
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
    # G43 of 0.28.0: A BANNER, EACH POINT NUMBERED, A TABLE AT THE END, so a long
    # local run reads at a glance: what runs, how far it is, how it ended.
    to_run = sum(len(pending) for _case, _build, pending in scheduled)
    started = time.perf_counter()
    if to_run:
        # 0.30.0: one of the two approved aircraft, drawn at random; the text
        # stays on the wing line, as before.
        top, mast, wing = random.choice(_RUN_BANNERS)
        _say(top, quiet=quiet)
        _say(mast, quiet=quiet)
        _say(
            f"{wing}   pyflightstream {pyflightstream.__version__}: "
            f"campaign {campaign.name}, {to_run} point(s) to run",
            quiet=quiet,
        )
    number = 0
    # The points this call ran on THIS machine, for the submitted line (G43): a
    # point handed to a scheduler did not run here, whether it was queued or the
    # scheduler refused it (reading A29).
    ran_here = 0
    for case, build, pending in scheduled:
        case_executor = build.executor if build is not None else executor
        runs_here = not isinstance(case_executor, Submitting)
        case_version = build.fs_version if build is not None else campaign.fs_version
        case_exe = build.fs_exe if build is not None else campaign.fs_exe
        # Read off the SAME condition the three lines above read, so the
        # record cannot say one thing while the point runs on another
        # (PFS-2009.08.02).
        case_version_source = FS_VERSION_FROM_ROW if build is not None else FS_VERSION_FROM_DEFAULT
        canonical = resolve(case_version).canonical
        # 0.30.0: A FOLDER THAT CANNOT BE WRITTEN IS THIS ROW'S RECORDED FAILURE,
        # never the end of the run: a workspace on a network share that refuses
        # one write left a row's planned points with no record at all.
        try:
            sim_dir = workspace.create_sim(case.sim_id)
            recipe, preparation_error, inputs_sha256, staged_geometry = _prepare_case(
                campaign, case, workspace, recipes
            )
        except OSError as error:
            sim_dir = workspace.sim_dir(case.sim_id)
            recipe, inputs_sha256, staged_geometry = None, {}, None
            preparation_error = _unwritable(error, "while its simulation folder was prepared")
        # FR-95: A STEADY ROW IS ONE JOB. Every point of it
        # goes through one script and one process, because that is what warm
        # start IS: point two begins from point one's converged solution
        # because nothing cleared it. The unsteady run types keep the point
        # path below unchanged, and correctly: a point that marches in time
        # starts from its own initial state and is its own job.
        #
        # A ROW WHOSE JOB IS RECORDED RUNS ITS NEW POINTS ONE EACH, as one new
        # point always has: the row's job id is the recorded job's, so a second
        # job of the row ran, spent the seat, and was then refused its record
        # as a duplicate id. A redo supersedes the job first, which takes its id
        # out of `recorded`, and runs the whole row as one job again.
        job_recorded = _job_run_id(campaign, case) in recorded
        if _is_one_job(campaign, case) and len(pending) > 1 and job_recorded:
            _say(
                f"  -> {_job_run_id(campaign, case)} is recorded; its "
                f"{len(pending)} new point(s) run one each",
                quiet=quiet,
            )
        if _is_one_job(campaign, case) and len(pending) > 1 and not job_recorded:
            job_run = _job_run_id(campaign, case)
            _say(
                f"  -> {_job_run_id(campaign, case)}  [{case.recipe}]  "
                f"{len(pending)} point(s) in one job  "
                f"({number + 1}-{number + len(pending)} of {to_run})",
                quiet=quiet,
            )
            number += len(pending)
            # A refused COLD_START is this row's recorded failure, like every
            # other preparation failure, and never an escape from the loop.
            try:
                cold = _ids._is_cold_start(case)
            except CampaignConfigError as error:
                cold, preparation_error = True, preparation_error or str(error)
            progress = _PointProgress()
            try:
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
                    cold=cold,
                    progress=progress,
                )
            except OSError as error:
                record = _record_of_an_unwritable_point(
                    progress, error, fallback=_bare_record(campaign, case, {}, job_run, canonical)
                )
            _say(
                f"     {record.run_id}  {record.status}"
                + (f"  ({record.error})" if record.error else "")
                + ("  WARNING: " + "; ".join(record.warnings) if record.warnings else ""),
                quiet=quiet,
            )
            if accept_unregistered_build:
                record = record.model_copy(update={"accept_unregistered_build": True})
            workspace.append_record(record)
            recorded.add(record.run_id)
            records.append(record)
            outcomes.extend(_job_point_statuses(record, len(pending)))
            ran_here += len(pending) if runs_here and record.executor is not None else 0
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
            continues: str | None = None
            try:
                continuation = resolve_continuation(
                    workspace, case, point, run_id=run_id, recipe=recipe, fs_version=case_version
                )
                # Archive what the continuation replaces, per
                # datapoint, under a day-and-hour stamp, BECAUSE THERE CAN BE
                # MORE THAN ONE RESTART. It happens before the solver starts,
                # so a continuation never writes into the folder holding the
                # evidence of the run it continues. INSIDE the refusal since
                # 0.30.0: an archive the folder refuses is this point's
                # recorded failure, not the end of the run.
                stamp = datetime.now()
                archived = (
                    workspace.archive_datapoint(
                        case.sim_id, PointName(point_name(case, point)), stamp=stamp
                    )
                    if continuation is not None
                    else None
                )
            except (CampaignConfigError, WorkspaceError, OSError) as error:
                # RECORDED AND REPORTED, LIKE EVERY OTHER FAILED POINT. This
                # branch put the record in the returned list alone: nothing in
                # the manifest, nothing in `failures`, so a campaign whose
                # continuation could not start returned as though it had
                # succeeded, to any caller that did not read the list.
                #
                # UNDER AN ID OF ITS OWN WHEN THE POINT'S IS TAKEN, which it is
                # whenever there was a run to continue: the stopped run holds
                # the plain id, and the manifest refuses a second row under it.
                # The stamped form is the one a continuation would have carried.
                refused = RunRecord(
                    run_id=(
                        _unused_continuation_run_id(run_id, datetime.now(), recorded)
                        if run_id in recorded
                        else run_id
                    ),
                    sim_id=case.sim_id,
                    point=dict(point),
                    matrix_stem=campaign.matrix_stem,
                    fs_version_requested=case_version,
                    package_version=pyflightstream.__version__,
                    manifest_schema=MANIFEST_SCHEMA,
                    script_sha256="",
                    raw_flag=False,
                    # FAILED_SCRIPT, because that is what happened: the
                    # script could not be built. No new status, and no
                    # guessing at one that may not exist.
                    status=RunStatus.FAILED_SCRIPT,
                    error=str(error),
                )
                workspace.append_record(refused)
                recorded.add(refused.run_id)
                records.append(refused)
                failures.append(refused)
                # IT IS ONE OF THE POINTS THE BANNER COUNTED (reading A31): it takes
                # its number and its line, and the closing table counts it.
                number += 1
                _say(
                    f"  -> {run_id}  [{case.recipe}]  refused before it was built  "
                    f"({number} of {to_run})",
                    quiet=quiet,
                )
                _say(f"     {refused.run_id}  {refused.status}  ({refused.error})", quiet=quiet)
                outcomes.append(str(refused.status))
                continue
            if continuation is not None:
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
                run_id = _unused_continuation_run_id(run_id, stamp, recorded)
                continues = str(continuation["continues"])
                _say(
                    f"  -> continuing {continuation['continues']} for "
                    f"{continuation['iterations']} more step(s)",
                    quiet=quiet,
                )
            # FR-78: the point is named as it STARTS, not when it ends. A
            # forty-point campaign that printed only on completion told a
            # reader nothing about the point currently burning the licence.
            number += 1
            _say(
                f"  -> {run_id}  [{case.recipe}]  building and running  ({number} of {to_run})",
                quiet=quiet,
            )
            progress = _PointProgress()
            try:
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
                    continues=continues,
                    recovered_continuation=continuation,
                    progress=progress,
                )
            except OSError as error:
                # 0.30.0: A FILE THIS POINT COULD NOT WRITE IS THIS POINT'S
                # FAILURE, recorded, and the run goes on with the next point.
                record = _record_of_an_unwritable_point(
                    progress, error, fallback=_bare_record(campaign, case, point, run_id, canonical)
                )
            # And as it ENDS, with the status, so the two lines bracket the
            # wait and a reader can see which point a warning between them
            # belonged to.
            _say(
                f"     {run_id}  {record.status}"
                + (f"  ({record.error})" if record.error else "")
                + ("  WARNING: " + "; ".join(record.warnings) if record.warnings else ""),
                quiet=quiet,
            )
            if accept_unregistered_build:
                record = record.model_copy(update={"accept_unregistered_build": True})
            workspace.append_record(record)
            recorded.add(record.run_id)
            records.append(record)
            outcomes.append(str(record.status))
            # Run here means the local executor was CALLED: a point refused before
            # it (a recipe that did not resolve, a name that did not render) carries
            # no executor record and ran nowhere (reading B30).
            ran_here += 1 if runs_here and record.executor is not None else 0
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
    #
    # G43 of 0.28.0: A RUN THAT SUBMITS DOES NOT POST, and its log stays short.
    # A point in a queue has no outputs
    # yet, so the post could only print a skip per point; one line says what
    # was submitted and the command that collects and then posts.
    if outcomes:
        _say_the_summary(outcomes, time.perf_counter() - started, quiet=quiet)
    # 0.30.0: EVERY ROW SAYS HOW MANY OF ITS PLANNED POINTS HAVE A RECORD, and
    # names the ones none carries: a row of ten planned points once recorded
    # six, and nothing said so until the scripts were counted by hand.
    if to_run:
        _say_the_rows(campaign, workspace, [*manifest.values(), *records], quiet=quiet)
    submitted = [record for record in records if record.status is RunStatus.SUBMITTED]
    if submitted:
        queued_count = outcomes.count(str(RunStatus.SUBMITTED))
        refused_count = len(outcomes) - queued_count - ran_here
        _say(
            f"submitted {queued_count} point(s) to the scheduler and ran {ran_here} here"
            + (f"; {refused_count} failed before they ran" if refused_count else "")
            + f"; nothing is posted until they are collected: pyfs-matrix collect "
            f"--workspace {workspace.root} (add --watch to wait), which posts once "
            "their outputs land."
        )
    elif recorded:
        problem = _leave_products(workspace, campaign.matrix_stem)
        if problem is not None:
            warnings.warn(problem, PyflightstreamWarning, stacklevel=2)
        problem = _leave_sweep_table(workspace, campaign.matrix_stem, sweep_csv)
        if problem is not None:
            # The one residual, stated rather than hidden: under
            # `-W error` this warning is promoted to an exception and
            # propagates in place of the outcome below. That promotion is
            # the caller's explicit request, and the manifest is complete
            # either way; silence would not be.
            warnings.warn(problem, PyflightstreamWarning, stacklevel=2)
    if failures:
        raise CampaignErrors(failures, records)
    return records


def _say_the_rows(
    campaign: Campaign,
    workspace: CampaignWorkspace,
    known: Sequence[RunRecord],
    *,
    quiet: bool,
) -> None:
    """Say, per row, how many planned points have a record, and warn of the rest (0.30.0).

    One line per row of the campaign, on the terminal and in
    ``logs/activity.log``: ``row 4016: all 10 executed``, or ``row 4016: 6 of
    10 point(s) executed, 4 not attempted``. A point is executed when a record
    of this campaign carries it, from this call or an earlier one
    (:func:`~pyflightstream.workspace.planned_points_without_record`); a row
    with points no record carries is also a warning naming them. The manifest
    is read again, because a forced re-run archived records this call started
    from; where it cannot be read, the records this call knows stand in.
    """
    try:
        rows: Sequence[Mapping[str, object]] = workspace.read_raw_manifest()
    except (OSError, ValueError, WorkspaceError):
        rows = [record.model_dump(mode="json") for record in known]
    for case in campaign.sims:
        planned = [_run_id(campaign, case, point) for point in case.sweep.points()]
        missing = planned_points_without_record(planned, rows)
        total = len(planned)
        if not missing:
            _say(f"row {case.sim_id}: all {total} executed", quiet=quiet)
            continue
        _say(
            f"row {case.sim_id}: {total - len(missing)} of {total} point(s) executed, "
            f"{len(missing)} not attempted",
            quiet=quiet,
        )
        warnings.warn(
            f"row {case.sim_id}: {len(missing)} of its {total} planned point(s) were not "
            "attempted and no record carries them: "
            + ", ".join(run_id.rsplit("/", 1)[-1] for run_id in missing)
            + ". Run the row again with --resume, which runs the points no record carries.",
            PyflightstreamWarning,
            stacklevel=3,
        )


def _job_point_statuses(record: RunRecord, points: int) -> list[str]:
    """Return one status per point of a job record, each point's own where it has one.

    A job whose record carries an entry for every point it ran counts each by its
    entry; one that stopped before it could (a preparation refusal, a solver that
    never started) counts every point at the job's status.
    """
    entries = record.points_ran or []
    if len(entries) == points:
        return [str(entry.get("status") or record.status) for entry in entries]
    return [str(record.status)] * points


#: The run banner's two aircraft, approved on 2026-09-28: the rows
#: above the wing, then the wing, which the banner text follows.
_RUN_BANNERS: tuple[tuple[str, str, str], ...] = (
    (
        "             _______",
        "                |",
        "     --(+)-----(_)-----(+)--",
    ),
    (
        "             _______",
        "                |",
        "   --(+)--(+)--(_)--(+)--(+)--",
    ),
)


def _say_the_summary(outcomes: Sequence[str], elapsed_s: float, *, quiet: bool) -> None:
    """Say how the points of this call ended, as a small table, and how long it took (G43)."""
    counts: dict[str, int] = {}
    for status in outcomes:
        counts[status] = counts.get(status, 0) + 1
    width = max(len("status"), *(len(status) for status in counts))
    rule = f"  +-{'-' * width}-+--------+"
    _say(rule, quiet=quiet)
    _say(f"  | {'status':<{width}} | points |", quiet=quiet)
    _say(rule, quiet=quiet)
    for status, count in sorted(counts.items()):
        _say(f"  | {status:<{width}} | {count:>6} |", quiet=quiet)
    _say(rule, quiet=quiet)
    _say(f"  {len(outcomes)} point(s) in {_clock(elapsed_s)}", quiet=quiet)


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
            f"force_rerun: the manifest was copied to {terminal_path(copied)} before "
            f"{len(run_ids)} record(s) were superseded.",
            PyflightstreamWarning,
            stacklevel=2,
        )
    # ONE LINE PER SIMULATION ON A CONSOLE WITHOUT --verbose (0.30.0, the
    # clean-log rule L3): ten points of one simulation printed ten
    # near-identical warnings. Every point's move is still written to the
    # activity log in full, whatever the console shows (L4).
    terse = terse_terminal()
    for case, points, _ in superseding:
        archived: list[Path] = []
        for point in points:
            name = point_name(case, point)
            moved = workspace.archive_datapoint(case.sim_id, PointName(name))
            if moved is None:
                continue
            archived.append(moved)
            record_activity(
                "force_rerun",
                "archived",
                f"the collected outputs of {name} moved to {moved}",
                sim_id=case.sim_id,
                datapoint=name,
                archive=str(moved),
            )
            if not terse:
                warnings.warn(
                    f"force_rerun: the collected outputs of {name} "
                    f"moved to {terminal_path(moved)}.",
                    PyflightstreamWarning,
                    stacklevel=2,
                )
        if terse and archived:
            warnings.warn(
                f"force_rerun: the collected outputs of {len(archived)} point(s) of "
                f"{workspace.sim_dir(case.sim_id).name} were archived "
                f"({terminal_glob(archived)})",
                PyflightstreamWarning,
                stacklevel=2,
            )


@workspace_activity("preparation")
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
            # `resolve_recipe` returns the imported function as a plain Callable; it is a
            # ScriptRecipe, whose named parameters a Callable type cannot state.
            recipe = cast(ScriptRecipe, resolve_recipe(case.recipe))
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
    # Every disc's native-format copy is parked by the builder and hashed by
    # _write_pending_files. Check each original still exists before building.
    profiles = set(case.actuator_profiles.values())
    if case.actuator_profile is not None:
        profiles.add(case.actuator_profile)
    for original in sorted(profiles):
        profile = Path(original)
        if not profile.is_file():
            return (
                recipe,
                f"the actuator profile {profile} is no longer present; "
                "restore the resolved inputs/profiles file before running",
                {},
                None,
            )
    if case.freestream_profile is not None:
        # G15. THE CUSTOM FREE STREAM, hashed where it lives: the solver reads
        # it there, and a record that cannot say which bytes it read cannot be
        # reproduced.
        field = Path(case.freestream_profile)
        if not field.is_file():
            return (
                recipe,
                f"the custom free stream {field} the row's FREESTREAM resolved to is no longer "
                "there; it is read where it lives, under the workspace's inputs/freestreams/",
                {},
                None,
            )
        if field.name in inputs_sha256:
            return (
                recipe,
                f"the custom free stream shares the file name {field.name!r} with another input "
                "of the row, and the record keys its inputs by name; rename one of them",
                {},
                None,
            )
        inputs_sha256 = {**inputs_sha256, field.name: file_sha256(field)}
    if case.fsi is not None and case.fsi_provenance.get("source"):
        source = Path(str(case.fsi_provenance["source"]))
        expected = case.fsi_provenance.get("source_sha256")
        if not source.is_file() or file_sha256(source) != expected:
            return (
                recipe,
                f"FSI input {source} changed after resolution; "
                "plan the matrix again before running.",
                {},
                None,
            )
        if source.name in inputs_sha256:
            return (
                recipe,
                f"FSI input name {source.name!r} collides with another staged input; rename it.",
                {},
                None,
            )
        inputs_sha256[source.name] = str(expected)
    return recipe, None, inputs_sha256, staged_geometry
