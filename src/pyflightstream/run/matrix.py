"""Planning and running a bound run matrix.

Pipeline role: the run-layer half of the run matrix, and the one-call
first-class entry of the file-managed modality. :func:`plan_matrix`
pre-flights a matrix without executing anything and :func:`run_matrix`
takes it all the way to manifest records, composing the binding step of
:mod:`pyflightstream.workspace.matrix` with the campaign loop of
:mod:`pyflightstream.run`.

It sits here rather than beside the reader because that is where its
dependencies are. The reader in :mod:`pyflightstream.cases.matrix`
carried these two entry points and imported the campaign loop inside
their bodies, which recorded the upward dependency without declaring it
(OPS-2007.01, PFS-2009.05); at this layer the same imports are ordinary
module-level ones. Nothing about the matrix format, the flags or the
records moved with them.

Since 0.27.0 it also carries the ADDITIONAL POST (G12):
:func:`plan_additional_post` and :func:`run_additional_post` reopen each
recorded point's final saved simulation and extract a second pproc from it
with no solve, choosing the executor as :func:`run_matrix` does.

:mod:`pyflightstream.run` deliberately does NOT import this module, so
importing it can never be part of an import cycle: the dependency runs
one way, from here into the campaign loop.
"""

from __future__ import annotations

import enum
import shutil
import warnings
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePath

import pyflightstream
from pyflightstream._deprecations import MATRIX_FS_VERSION
from pyflightstream._digest import file_sha256, optional_file_sha256
from pyflightstream._errors import (
    InputArtifactError,
    PyflightstreamDeprecationWarning,
    PyflightstreamError,
    PyflightstreamWarning,
    warn,
)
from pyflightstream.cases import (
    Campaign,
    ScriptRecipe,
    SimCase,
    case_at_point,
    classify_outputs,
)
from pyflightstream.cases.matrix import (
    LEGACY_WORKFLOW,
    MatrixError,
    read_matrix,
    refuse_silent_rows_without_default,
)
from pyflightstream.cases.workflows import (
    ADDITIONAL_PPROC_VARIABLE,
    WORKFLOW_KEY,
    additional_outputs,
    build_additional_script,
    frame_pairs,
    frames_of_the_run,
)
from pyflightstream.results.tables import superseded_by_a_continuation
from pyflightstream.run import (
    CampaignPlan,
    Executor,
    ExecutorConfigurationError,
    LocalExecutor,
    OutcomeAssessor,
    SolverBuild,
    Submitting,
    SubmittingExecutor,
    invocation_record,
    on_a_cluster,
    package_vcs_state,
    plan_campaign,
    run_campaign,
)
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
    write_input_guides,
)
from pyflightstream.workspace.inputs import (
    hpc_profiles,
    read_hpc_profile,
    resolve_hpc_profile,
)
from pyflightstream.workspace.matrix import ResolvedMatrix, resolve_matrix


def _cluster_executor(
    workspace: CampaignWorkspace, resolved: ResolvedMatrix
) -> SubmittingExecutor | None:
    """Return this machine's submitting executor, or None to run locally (FR-99).

    THREE THINGS HAVE TO HOLD and each is measured rather than assumed:
    this machine is a cluster, the workspace carries a profile, and the
    profile resolves to exactly one. A workspace carrying several and
    nothing to choose between them is REFUSED by `resolve_hpc_profile`
    rather than guessed, because guessing spends a queue.

    A LINUX MACHINE WITH NO PROFILE RUNS LOCALLY, deliberately. Not every
    Linux box is a cluster, and a study that never wrote a profile is
    saying it does not submit; refusing there would break every developer
    running the tier-1 suite on Linux.
    """
    if not on_a_cluster():
        return None
    profile = resolve_hpc_profile(workspace.inputs_dir)
    if profile is None:
        return None
    return SubmittingExecutor(
        profile,
        values={"fs_build": resolved.campaign.fs_version or ""},
    )


def _refuse_an_unmapped_build(executor: Executor, resolved: ResolvedMatrix) -> None:
    """Refuse, before any point is submitted, a build the profile cannot name.

    PFS-2010.01.06. A build the profile's [builds] table does not map fails every
    point of its rows the same way, so it is refused for the whole campaign
    rather than at the first descriptor after earlier rows spent the queue.
    ASKED OF WHATEVER EXECUTOR THE CAMPAIGN RUNS ON, the one the platform chose
    or one a caller passed, and it lived inside the platform's branch only
    until the independent review of the 0.18.1 release measured a caller's own
    submitting executor submitting a first row before the refusal.
    """
    if not isinstance(executor, SubmittingExecutor):
        return
    campaign = resolved.campaign
    # THE ROW'S OWN BUILD, READ OFF THE BINDING, and not `case.fs_build`: that
    # field is filled by `_bind_row_builds` AFTER this runs, so reading it here
    # saw only the campaign default for every case, and a later row naming an
    # unmapped build was submitted-around (the independent review of the
    # 0.18.1 release, second pass, reproduced in memory).
    row_builds = resolved.row_builds
    if len(row_builds) != len(campaign.sims):
        row_builds = tuple(None for _ in campaign.sims)
    refusal = executor.build_alias_refusal(
        [
            row_build or case.fs_build or campaign.fs_version
            for case, row_build in zip(campaign.sims, row_builds, strict=True)
        ]
    )
    if refusal is not None:
        raise InputArtifactError(refusal)


__all__ = [
    "ONE_INSTANT",
    "REOPENED_SUFFIX",
    "AdditionalPointPlan",
    "AdditionalSkip",
    "plan_additional_post",
    "plan_matrix",
    "run_additional_post",
    "run_matrix",
]


def _default_version(
    default_fs_version: str | None,
    fs_version: str | None,
    *,
    caller: str,
) -> str | None:
    """Resolve the campaign default from the new keyword or the old one.

    The argument answers for rows whose FS_BUILD column names no build.
    Calling it ``fs_version`` beside a per-row build column reads as an
    OVERRIDE of that column, and nobody reads a docstring to check a
    name they think they understand, so the parameter is
    ``default_fs_version`` (PFS-2009.08.01). The old spelling still
    works and says so once, because callers of these two entry points
    exist outside this package.

    Parameters
    ----------
    default_fs_version : str or None
        The new keyword, as passed.
    fs_version : str or None
        The retired keyword, as passed.
    caller : str, keyword-only
        Name of the entry point, so the message names the call the user
        actually made.

    Returns
    -------
    str or None
        The version rows that name no build fall back to; None when no
        default was given, in which case every active row must fill
        FS_BUILD or be refused by name (PFS-2029.01).

    Raises
    ------
    pyflightstream.cases.matrix.MatrixError
        The two keywords given and disagreeing.
    """
    if fs_version is not None:
        if default_fs_version is not None and default_fs_version != fs_version:
            raise MatrixError(
                f"{caller}() was given default_fs_version={default_fs_version!r} and "
                f"fs_version={fs_version!r}, which are two names for one argument and "
                "disagree; pass default_fs_version alone."
            )
        # The text comes from the ledger row of this entry point, so the
        # release it names (1.0.0, PFS-2021.02) is the one the deadline
        # guard enforces.
        warnings.warn(
            MATRIX_FS_VERSION[caller].message(),
            PyflightstreamDeprecationWarning,
            stacklevel=3,
        )
        return fs_version
    # NO DEFAULT IS A LEGAL INPUT SINCE 0.11.0 (PFS-2029.01): a matrix whose
    # every active row fills FS_BUILD names its builds itself, and the
    # default only ever answered for a row that left the cell empty. That
    # row is still refused, by name, by refuse_silent_rows_without_default,
    # which runs before anything is bound; what went is the requirement
    # to repeat on the command line a build every row already states.
    return default_fs_version


def _warn_the_legacy_rows_saving_no_simulation(resolved: ResolvedMatrix) -> None:
    """Name each LEGACY row whose outputs declare no saved simulation (G11, 0.27.0).

    A row naming a run type saves its final ``.fsm`` on every point, which the
    pproc artifact cannot switch off. A LEGACY row's recipe decides what it
    writes, and only a ``.fsm`` name among its OUTPUTS is collected and hashed,
    so a row declaring none leaves no final state in its record. A warning,
    never a refusal: such a row runs as it always did. Called from
    :func:`plan_matrix` alone, so ``run`` does not repeat what ``plan`` said.
    """
    unsaved = [
        sim.sim_id
        for sim in resolved.campaign.sims
        if sim.variables.get(WORKFLOW_KEY) == LEGACY_WORKFLOW
        and "simulation" not in classify_outputs(sim.outputs)
    ]
    if unsaved:
        warn(
            f"POL {', '.join(unsaved)}: {LEGACY_WORKFLOW} row(s) that declare no saved "
            "simulation. No name among their OUTPUTS ends in .fsm, so no final .fsm of "
            "theirs is collected into datapoints/DP-<point>/ or hashed in their run "
            "record, and nothing can reopen it from the record. A row naming a run type "
            f"saves one on every point; a {LEGACY_WORKFLOW} recipe saves one only when it "
            "writes SAVEAS to a name its OUTPUTS declare, so declare that name and save "
            "to it, or leave the row as it is if its final state is not wanted.",
            PyflightstreamWarning,
            stacklevel=3,
        )


def _warn_the_rows_whose_additional_post_is_one_instant(resolved: ResolvedMatrix) -> None:
    """Name each unsteady row stating ADDITIONAL_PPROC, whose extraction is one instant (G12).

    The additional post reopens a point's final saved simulation, which holds
    the LAST instant of an unsteady run (RPT-062), so what it extracts there is
    one instant and not the run's per-step history. A warning, never a
    refusal: the plan says it once per matrix, naming the rows, and the post
    says it again per point. Called from :func:`plan_matrix` alone.
    """
    instants = [
        sim.sim_id
        for sim in resolved.campaign.sims
        if sim.variables.get(ADDITIONAL_PPROC_VARIABLE)
        and str(sim.variables.get(WORKFLOW_KEY, "")).startswith("unsteady")
    ]
    if instants:
        warn(
            f"POL {', '.join(instants)}: unsteady row(s) stating "
            f"{ADDITIONAL_PPROC_VARIABLE}. The additional post reopens each point's final "
            "saved simulation, which is the LAST instant of its run (RPT-062): what it "
            "extracts there is that one instant and not the run's per-step history. The "
            "plots history it exports is the run's own.",
            PyflightstreamWarning,
            stacklevel=3,
        )


def _refuse_a_run_that_names_no_build(path: str | Path, default: str | None) -> None:
    """Refuse, before anything is bound, a run with no build named anywhere.

    Both entry points call this BETWEEN resolving the default and calling
    :func:`~pyflightstream.workspace.matrix.resolve_matrix`, which is the
    only position that satisfies the whole acceptance: resolution builds
    the :class:`~pyflightstream.cases.Campaign` and selects the
    executable, and the executor is built after that, so a check inside
    or below it cannot promise that none of the three exists
    (PFS-2009.08.03).

    The rows are read here rather than borrowed from the resolution
    below, which costs one extra parse of a small text file and buys the
    ordering. :func:`~pyflightstream.cases.matrix.to_campaign` carries
    the same call, so a caller that converts a matrix without planning it
    meets the same refusal.
    """
    refuse_silent_rows_without_default(read_matrix(path), default, path)


def _bind_row_builds(
    resolved: ResolvedMatrix,
    default: str | None,
    executor: Executor,
    executor_for: Callable[[Path], Executor],
) -> tuple[Campaign, dict[str, SolverBuild] | None]:
    """Carry the matrix's build provenance into the campaign that runs.

    A manifest record says WHICH build a point ran on twice over, in
    ``fs_exe`` and in ``fs_version_requested``, and until this existed it
    could not say WHERE that build came from for a matrix-driven run: the
    campaign loop reads the provenance off
    :attr:`pyflightstream.cases.SimCase.fs_build`, the converter never set
    it, and every point of every matrix was therefore recorded as having
    inherited the campaign default even when its row's FS_BUILD cell named
    the installation outright (PFS-2009.08.02).

    The translation is one-to-one and adds nothing: a row that named a
    build gets that build id on its case and one entry in the ``builds``
    mapping, and a row that named none keeps ``fs_build`` at None, which
    is the campaign's own installation and what the loop records as
    ``campaign_default``.

    WHAT THE MAPPED BUILD CHANGES, since PFS-2009.05, is the
    installation AND the version, one row at a time. Each build takes
    the executable its own registry entry names and the version that
    entry DECLARES, so a matrix whose rows name two builds runs each row
    on the installation it asked for and emits its script under that
    installation's version. This paragraph said the opposite until that
    item, that the version was always ``default`` and that a build id
    could never move it, and the sentence was true of the code beside
    it: the mapping gave every build the campaign's one executable.

    NOTHING HERE IS INFERRED, which is the part that did not change. A
    build id is still a key of the workspace registry and still says
    nothing about a command database; what carries the version is the
    ``version`` key of that build's registry entry, written by the same
    person who wrote the path. A build whose entry declares none falls
    back to ``default``, so a registry of bare path strings, which is
    every registry written before that item, produces exactly the
    mapping this function produced before it.

    AN EXECUTOR IS BOUND TO AN EXECUTABLE at construction, so a second
    installation needs a second executor and this function cannot make
    one: whether the caller wants a
    :class:`~pyflightstream.run.LocalExecutor` and with which window
    setting is a decision one layer up. It is passed in as
    ``executor_for`` and called ONCE PER DISTINCT EXECUTABLE, with the
    campaign's own executor answering for its own executable, so a
    single-build matrix constructs nothing extra.

    Parameters
    ----------
    resolved : pyflightstream.workspace.matrix.ResolvedMatrix
        The bound matrix, carrying ``row_builds`` and ``builds``.
    default : str
        The campaign default version, declared by every build whose
        registry entry declares none of its own.
    executor : pyflightstream.run.Executor
        The campaign's own executor, which is the one bound to
        ``resolved.fs_exe``.
    executor_for : callable
        Builds the executor of one build's executable, given that
        executable as a :class:`pathlib.Path`. Called only for an
        executable that is not the campaign's own.

    Returns
    -------
    tuple of Campaign and (dict of str to SolverBuild, or None)
        The campaign to run and the ``builds`` mapping it needs. None
        means no active row named a build, so nothing is mapped and the
        campaign is returned untouched.

    Raises
    ------
    pyflightstream.cases.matrix.MatrixError
        The bound matrix names a build in ``row_builds`` that its
        ``builds`` mapping does not carry, which
        :func:`~pyflightstream.workspace.matrix.resolve_matrix` never
        produces and a hand-built ``ResolvedMatrix`` can.
    """
    campaign = resolved.campaign
    row_builds = resolved.row_builds
    if not any(row_builds):
        return campaign, None
    sims = [
        case if build is None else case.model_copy(update={"fs_build": build})
        for case, build in zip(campaign.sims, row_builds, strict=True)
    ]
    # Keyed by EXECUTABLE rather than by build id, because two build ids
    # may name one installation and building a second executor for it
    # would double the identity pre-flight it pays for.
    executors: dict[Path, Executor] = {Path(resolved.fs_exe): executor}
    builds: dict[str, SolverBuild] = {}
    for build in row_builds:
        if build is None or build in builds:
            continue
        registered = resolved.builds.get(build)
        if registered is None:
            raise MatrixError(
                f"the bound matrix reports build {build!r} in row_builds and carries no "
                "entry for it in builds, so nothing says which executable that row runs "
                "on. resolve_matrix always fills both together; a ResolvedMatrix built "
                "by hand has to do the same."
            )
        exe = Path(registered.fs_exe)
        if exe not in executors:
            executors[exe] = executor_for(exe)
        # A bare-path registry entry declares no version, and with no
        # campaign default (PFS-2029.01) the build id itself is the version
        # its scripts are emitted under, which is what the id has meant
        # since the registry took the YY.XXX identifiers.
        builds[build] = SolverBuild(
            fs_exe=exe,
            fs_version=registered.fs_version or (default or "").strip() or build,
            executor=executors[exe],
        )
    return campaign.model_copy(update={"sims": sims}), builds


def plan_matrix(
    path: str | Path,
    workspace: CampaignWorkspace,
    *,
    name: str,
    recipes: Mapping[str, str],
    default_fs_version: str | None = None,
    fs_exe: str | Path | None = None,
    recipe_registry: dict[str, ScriptRecipe] | None = None,
    write_plan: bool = True,
    fs_version: str | None = None,
    name_from: str | None = None,
    ignore_missing_families: bool = True,
    cost: bool = False,
    accept_unregistered_build: bool = False,
) -> CampaignPlan:
    """Pre-flight a run matrix without executing anything.

    Resolution
    (:func:`pyflightstream.workspace.matrix.resolve_matrix`) plus the
    campaign pre-flight
    (:func:`pyflightstream.run.plan_campaign`): every recipe resolves,
    every script builds in dry run, and points already in the manifest
    are marked ALREADY_RECORDED, exactly what
    ``run_matrix(..., resume=True)`` would skip.

    A point whose row names a build whose registry entry declares a
    version of its own is pre-flighted under THAT version, read off the
    registry with no executable bound (the residual PFS-2009.05 left,
    closed 2026-09-09): a row on 26.123 in a matrix whose default is
    26.120 used to be BLOCKED for a command 26.120 lacks and 26.123
    carries, and would have run. A build whose entry declares no version
    is pre-flighted under the default, which is what its scripts are
    emitted under at run time too.

    Parameters
    ----------
    path, workspace, name, recipes, fs_exe
        As in :func:`pyflightstream.workspace.matrix.resolve_matrix`.
    default_fs_version : str
        FlightStream version for rows whose FS_BUILD column names no
        build; a DEFAULT rather than an override, which is what the
        name says (PFS-2009.08.01). Required in practice: it defaults
        to None only so the former spelling below can still be given.
    fs_version : str, optional
        The former name of ``default_fs_version``. Still accepted, with
        a DeprecationWarning, until v1.0.0 (the ledger row
        ``PLAN_MATRIX_FS_VERSION``, PFS-2021.02); the ``pyfs-matrix``
        command line keeps ``--fs-version``.
    recipe_registry : dict of str to ScriptRecipe, optional
        Named recipe registry (name to callable) consulted before
        treating a recipe reference as ``module:function``, forwarded
        to the campaign pre-flight.
    write_plan : bool
        Write the JSON summary as ``post/<matrix stem>/plan.json`` in the
        workspace (default True), the matrix's own folder so several
        matrices of one workspace keep their own (PFS-2031.04).
    ignore_missing_families : bool
        Whether a pproc entry naming a family the opened mesh does not
        carry is left out (the default, True) or BLOCKS the point
        (False). Forwarded to
        :func:`pyflightstream.workspace.matrix.resolve_matrix`
        (PFS-2035.13); the command line spells it
        ``--ignore-missing-families``.

    Returns
    -------
    pyflightstream.run.CampaignPlan
        One status per matrix point; inspect ``blocked`` before
        running, or print ``summary()``.

    Raises
    ------
    pyflightstream.cases.matrix.MatrixError
        Layout or build-selection problems, no default version given
        under either spelling, or a default that strips to empty. The
        last names every active row whose FS_BUILD cell strips to empty
        too, by row number and POL, and is raised before the matrix is
        bound, so no campaign is built and no executable is resolved
        (PFS-2009.08.03).
    pyflightstream.workspace.InputArtifactError
        A REF, SET or ENTRY code, or a ``GEOMETRY`` stem, that the input
        library cannot resolve. The geometry half arrived with 0.8.1 and
        raises through the same call; this list said REF, SET and ENTRY
        only until the review that noticed.

    Warns
    -----
    pyflightstream.exceptions.PyflightstreamWarning
        Naming every ``LEGACY`` row whose OUTPUTS declare no ``.fsm``, so no
        final saved simulation of it is collected or hashed (0.27.0). And
        naming every unsteady row stating ``ADDITIONAL_PPROC``, whose
        additional post extracts one instant, the last, and not the run's
        history (G12, RPT-062). Neither blocks anything.

    Examples
    --------
    >>> from pyflightstream.run.matrix import plan_matrix
    >>> from pyflightstream.workspace import CampaignWorkspace
    >>> plan = plan_matrix(                 # doctest: +SKIP
    ...     "matrix.fs",
    ...     CampaignWorkspace("campaign"),
    ...     name="wing_steady",
    ...     default_fs_version="26.120",
    ...     recipes={"003": "recipes.steady_polar:build"},
    ... )
    >>> print(plan.summary())               # doctest: +SKIP
    """
    default = _default_version(default_fs_version, fs_version, caller="plan_matrix")
    _refuse_a_run_that_names_no_build(path, default)
    resolved = resolve_matrix(
        path,
        workspace,
        name=name,
        fs_version=default,
        recipes=recipes,
        fs_exe=fs_exe,
        ignore_missing_families=ignore_missing_families,
    )
    _warn_the_legacy_rows_saving_no_simulation(resolved)
    _warn_the_rows_whose_additional_post_is_one_instant(resolved)
    plan = plan_campaign(
        resolved.campaign,
        workspace,
        recipes=recipe_registry,
        write_plan=write_plan,
        name_from=name_from,
        versions=_row_versions(resolved),
        matrix_path=path,
        accept_unregistered_build=accept_unregistered_build,
    )
    if write_plan:
        # THE GENERATED PPROC GUIDES (0.24.0), written by the step every campaign
        # passes through, so a workspace made before they existed gets them and a
        # `[glossary]` just written reaches the variables page. A plan asked to
        # write nothing writes nothing.
        plan.guides.extend(write_input_guides(workspace.inputs_dir))
    if cost:
        # FR-82. Computed HERE, where the resolved cases are; a caller
        # re-resolving the matrix to find them would be re-deriving state
        # this object already holds.
        from pyflightstream.run import point_costs

        plan.costs.extend(
            point_costs(
                plan,
                cases_by_sim_id={case.sim_id: case for case in resolved.campaign.sims},
                workspace=workspace,
            )
        )
    return plan


def _row_versions(resolved: ResolvedMatrix) -> dict[str, str]:
    """Return the per-simulation version override, keyed by sim id.

    Per simulation, from the build each row named and the version its
    registry entry declares; a row on a build declaring no version, or on
    the campaign's own, is absent here and pre-flights under the campaign
    default. One function for the two callers, because the first fix
    (PFS-2009.05.01) reached ``plan_matrix`` alone and ``pyfs-matrix run``
    kept refusing the row ``plan`` had said READY: pfs0130's row 1226 on
    26.123, in a matrix whose default is 26.120, met exactly that on the
    published 0.13.0 (PFS-2009.05.02).
    """
    versions: dict[str, str] = {}
    for case, build in zip(resolved.campaign.sims, resolved.row_builds, strict=True):
        registered = resolved.builds.get(build) if build else None
        if registered is not None and registered.fs_version:
            versions[case.sim_id] = registered.fs_version
    return versions


def _campaign_executor(
    workspace: CampaignWorkspace,
    resolved: ResolvedMatrix,
    path: str | Path,
    *,
    executor: Executor | None = None,
    local: bool = False,
    hidden: bool | None = None,
) -> tuple[Executor, Callable[[Path], Executor]]:
    """Choose the executor a bound matrix runs on, and the one for each other build.

    ONE CHOICE FOR EVERY COMMAND THAT LAUNCHES THE SOLVER OVER A MATRIX:
    :func:`run_matrix` and the additional post of 0.27.0 (G12) both ask
    here, so ``local`` and the cluster rule mean one thing whichever
    command a user typed. Split out of :func:`run_matrix` with no
    change of behaviour.

    Parameters
    ----------
    workspace : CampaignWorkspace
        The campaign root, whose submission profile a cluster reads.
    resolved : pyflightstream.workspace.matrix.ResolvedMatrix
        The bound matrix; its ``fs_exe`` is the campaign's own executable.
    path : str or Path
        The matrix, whose HIDDEN column decides the window when ``hidden``
        is None.
    executor : Executor, optional
        A caller's executor, which then answers for every build.
    local : bool
        Keep the run on this machine, as ``run_matrix(local=True)``.
    hidden : bool or None
        Windowless solver runs; None lets the matrix decide.

    Returns
    -------
    tuple of Executor and callable
        The campaign's executor, and ``executor_for(exe)`` building the one
        of another build's executable.

    Raises
    ------
    pyflightstream.run.ExecutorConfigurationError
        ``local`` beside a submitting executor, or a missing executable.
    pyflightstream.workspace.InputArtifactError
        A build the submission profile cannot name.
    """
    # Held before the branch below rebinds the name, because it is what
    # tells a build's executor apart from the campaign's: a caller who
    # supplied an executor supplied it for the whole run, whatever
    # installation a row names, and building a LocalExecutor beside it
    # would send some rows somewhere the caller never asked for.
    supplied = executor
    forced = False
    machine: dict[str, bool] = {}
    if executor is None:
        # The matrix has a HIDDEN column and it used to be read into the
        # matrix_hidden variable and never acted on, so a row saying 0
        # (show the window) ran headless anyway because this parameter
        # defaults to True. The row decides when the caller did not
        # (hidden=None); an explicit True or False still wins, because a
        # caller who names it means it.
        if hidden is None:
            rows = read_matrix(path)
            hidden = all(row.hidden for row in rows) if rows else True
        # FR-99: THE CODE SEES LINUX AND THAT
        # IS THE CLUSTER. No cell selects it, so the same matrix, unchanged
        # in every cell, runs locally on Windows and submits on Linux.
        #
        # THIS BRANCH IS THE WHOLE WIRING, and without it every name the
        # release added was dead code: `on_a_cluster`, the profile reader
        # and the submitting executor existed, the CHANGELOG announced
        # them in the present tense, and `run_campaign` built a
        # LocalExecutor unconditionally, so opening the study on a cluster
        # ran it locally on the login node -- the exact failure
        # `on_a_cluster`'s own comment says it exists to prevent. All five
        # lenses found it independently (2026-09-13).
        #
        # `local=True` (the command line's --local, 0.27.0) KEEPS THE RUN ON
        # THIS MACHINE: the cluster is not asked, so a Linux box that carries
        # a profile runs the solver itself, the way Windows does. The choice
        # is recorded on every point's executor entry as `forced_local`, so a
        # record never has to be read against the platform to know why a
        # profiled workspace ran without a queue.
        #
        # `forced_local` IS THE SWITCH'S MEASURED EFFECT, not the request (the
        # opening round of 0.27.0): it is recorded only where the platform
        # would have submitted, a cluster with a profile. On Windows, or on a
        # Linux box with none, the run was local anyway and nothing was forced.
        # The profile is COUNTED rather than resolved, so a local run is never
        # refused over an ambiguity in a profile it does not use.
        #
        # EXCEPT ITS LOG, WHICH IS THE MACHINE'S (0.27.0). A profile stating
        # `export_log = false` says the build on this cluster aborts at
        # EXPORT_LOG, and it aborts there whether the job is submitted or run
        # here: a point run with --local on such a cluster stopped at
        # EXPORT_LOG after every other export (measured 2026-09-24). So a run
        # the switch keeps here reads the decision and carries it on its
        # executor. Only the false side is passed, as `_with_the_profile_s_log`
        # writes only the false side onto a case: every other executor is
        # built exactly as it was.
        submitting = None if local else _cluster_executor(workspace, resolved)
        forced = local and on_a_cluster() and bool(hpc_profiles(workspace.inputs_dir))
        if forced and not _exports_its_log_here(workspace):
            machine = {"export_log": False}
        executor = submitting or LocalExecutor(
            resolved.fs_exe, hidden=hidden, forced_local=forced, **machine
        )
    # THE PROTOCOL, NOT THE CLASS: the runner submits through anything that
    # implements `Submitting`, so a caller's own scheduler adapter that does
    # not inherit SubmittingExecutor passed a class check and could submit
    # under local=True (the opening round of 0.27.0, all five lenses).
    if local and isinstance(executor, Submitting):
        raise ExecutorConfigurationError(
            "local=True keeps the run on this machine, and the executor given is a "
            "submitting one; drop one of the two"
        )
    _refuse_an_unmapped_build(executor, resolved)
    windowless = bool(hidden)

    def executor_for(exe: Path) -> Executor:
        """Build the executor of one row's own installation.

        The window setting is the one the campaign's own executor was
        built with, so a second build runs the same way the first does.

        ON A CLUSTER EVERY BUILD SUBMITS, and this returned a LocalExecutor
        for a row naming its own installation until 2026-09-13: a
        multi-build matrix submitted its default-build rows and ran the
        rest on the login node, or died at LocalExecutor's own refusal
        about an executable path that does not exist on that machine, with
        nothing in the message mentioning a cluster. Half-wired is harder
        to see than not wired (the architect lens, round two).

        ONE PROFILE SERVES EVERY BUILD, which is why the campaign's own
        submitting executor is reused rather than one built per build: the
        descriptor names the SCRIPT and the build is a field inside it,
        which `_bind_submission_values` sets from the row.
        """
        if supplied is not None:
            return supplied
        if isinstance(executor, SubmittingExecutor):
            return executor
        return LocalExecutor(exe, hidden=windowless, forced_local=forced, **machine)

    return executor, executor_for


def _exports_its_log_here(workspace: CampaignWorkspace) -> bool:
    """Whether a run the local switch keeps on this cluster exports its solver log (0.27.0).

    The profile's ``export_log``, READ rather than counted: it is the one field
    of a profile a local run uses, because it states what the build on this
    machine does at ``EXPORT_LOG``. A profile this package cannot read is
    refused by name, as it would be for a submitted job; several profiles that
    disagree about the log are refused, because which of them is this machine
    is not a guess to make about the file a run is judged by.
    """
    stated = {
        path.name: read_hpc_profile(path).export_log for path in hpc_profiles(workspace.inputs_dir)
    }
    if len(set(stated.values())) > 1:
        said = ", ".join(
            f"{name}: export_log = {str(value).lower()}" for name, value in sorted(stated.items())
        )
        raise InputArtifactError(
            f"{workspace.inputs_dir / 'hpc'} holds {len(stated)} profiles that disagree about "
            f"the solver log ({said}), and a run kept on this machine by --local follows its "
            "machine's: whether the build here aborts at EXPORT_LOG is not a guess this "
            "package makes. Keep the profile of this cluster alone in inputs/hpc/."
        )
    return all(stated.values())


def run_matrix(
    path: str | Path,
    workspace: CampaignWorkspace,
    *,
    name: str,
    recipes: Mapping[str, str],
    assess: OutcomeAssessor,
    default_fs_version: str | None = None,
    fs_exe: str | Path | None = None,
    executor: Executor | None = None,
    recipe_registry: dict[str, ScriptRecipe] | None = None,
    resume: bool = False,
    force_rerun: Sequence[str] | None = None,
    hidden: bool | None = None,
    fs_version: str | None = None,
    name_from: str | None = None,
    ignore_missing_families: bool = True,
    accept_unregistered_build: bool = False,
    sweep_csv: str | Path | None = None,
    local: bool = False,
) -> list[RunRecord]:
    """Read a run matrix and run it: the one-call first-class entry.

    In order: the matrix converts through the canonical campaign form,
    its codes resolve against the workspace input library
    (:func:`pyflightstream.workspace.matrix.resolve_matrix`), the whole
    campaign pre-flights in dry run, and only then the points execute
    through :func:`pyflightstream.run.run_campaign`, landing one
    manifest record per point. A blocked pre-flight refuses to execute
    at all, so a broken recipe or missing artifact costs no solver time.
    A row whose build declares a version of its own pre-flights and runs
    under that version (PFS-2009.05.02; :func:`plan_matrix` says how the
    version is read).

    Parameters
    ----------
    path, workspace, name, recipes, fs_exe
        As in :func:`pyflightstream.workspace.matrix.resolve_matrix`;
        the executable comes from the FS_BUILD column through the build
        registry, or from the explicit ``fs_exe`` override (mandatory
        for MANUAL rows).
    default_fs_version : str
        FlightStream version for rows whose FS_BUILD column names no
        build; a DEFAULT rather than an override (PFS-2009.08.01).
    fs_version : str, optional
        The former name of ``default_fs_version``, still accepted with
        a DeprecationWarning until v1.0.0 (the ledger row
        ``RUN_MATRIX_FS_VERSION``, PFS-2021.02).
    assess : pyflightstream.run.OutcomeAssessor
        Solver-quality judgment, for example
        :class:`pyflightstream.run.LoadsAssessor`; required because
        the loop refuses to invent convergence evidence.
    executor : pyflightstream.run.Executor, optional
        Replacement executor; by default a
        :class:`pyflightstream.run.LocalExecutor` is built from the
        resolved executable. Given one, it answers for EVERY row,
        including a row whose FS_BUILD cell names a second installation:
        a caller who hands in an executor has bound the run to it, and
        building a local executor beside it would send some rows to a
        process the caller never asked for. Left out, one local executor
        is built per distinct executable the matrix names, each with the
        window setting ``hidden`` resolves to.
    recipe_registry : dict of str to ScriptRecipe, optional
        Named recipe registry (name to callable), forwarded to the
        pre-flight and the campaign loop.
    force_rerun : sequence of str, optional
        The points to REDO rather than refuse, each by its point name, its
        full ``run_id``, or the job id of a swept row. For a row that was
        wrong: the record and the point's collected outputs are archived
        first, and nothing is deleted. It names points rather than being a
        switch because redoing a whole matrix over one wrong row spends a
        licensed seat per point. Refused together with ``resume``.
    resume : bool
        With True, points already in the manifest are skipped, so a
        grown matrix re-runs only its new points; with False (the
        default) an already-recorded point raises before anything
        executes, as in :func:`pyflightstream.run.run_campaign`.
    ignore_missing_families : bool
        Whether a pproc entry naming a family the opened mesh does not
        carry is left out (the default, True) or BLOCKS the point
        (False), in which case the blocked pre-flight refuses the whole
        run before a seat is spent. Forwarded to
        :func:`pyflightstream.workspace.matrix.resolve_matrix`
        (PFS-2035.13); the command line spells it
        ``--ignore-missing-families``.
    sweep_csv : str or Path, optional
        Where to leave the campaign's sweep table instead of the default
        place; forwarded to :func:`pyflightstream.run.run_campaign`, which
        writes ONE table either way. The command line spells it
        ``--sweep-csv``.
    local : bool
        Keep the run on this machine (0.27.0): the cluster is not asked,
        so a Linux box carrying a submission profile runs the solver
        itself, as Windows does, and every point's executor entry says
        ``forced_local``. Refused beside a submitting ``executor``. The
        command line spells it ``--local``.
    hidden : bool or None
        Windowless solver runs, forwarded to the default executor only
        and ignored when ``executor`` is given. The default is None,
        meaning the matrix decides through its HIDDEN column: the run is
        windowless only if EVERY active row asks for it, so one row
        saying 0 makes the whole campaign visible. An explicit True or
        False wins over the column, because a caller who names it means
        it.

    Returns
    -------
    list of pyflightstream.workspace.RunRecord
        The records executed by this call, in execution order. Each one
        names the installation it ran on (``fs_exe``, hashed into
        ``fs_exe_sha256``), the version its script was emitted under
        (``fs_version_requested``), and which of the two possible
        sources chose the installation (``fs_version_source``: ``row``
        for a point whose FS_BUILD cell named the build,
        ``campaign_default`` for one that named none and for every point
        of a run given the explicit ``fs_exe`` override, which overrules
        the column). Those three reproduce the run without the matrix
        (PFS-2009.08.02).

        The first two are PER ROW since PFS-2009.05: a row naming a
        build is recorded against that build's own executable, and
        against the version its registry entry declares where it
        declares one. A row that names none, and every row of a
        registry written as bare path strings, is recorded against the
        campaign default exactly as before.

    Raises
    ------
    pyflightstream.cases.matrix.MatrixError
        Layout or build-selection problems, a blocked pre-flight (the
        message carries the plan summary; nothing was executed), no
        default version given under either spelling, or a default that
        strips to empty. The last names every active row whose FS_BUILD
        cell strips to empty too, by row number and POL, and is raised
        before the matrix is bound: no campaign is built, no executable
        is resolved and no executor is constructed (PFS-2009.08.03).
    pyflightstream.workspace.InputArtifactError
        A REF, SET or ENTRY code, or a ``GEOMETRY`` stem, that the input
        library cannot resolve. Raised during resolution, before the
        pre-flight and before any executor is constructed. Documented on
        the sibling :func:`plan_matrix` and not here until 0.8.1, which
        read as a difference in behaviour where there is none: both call
        the same resolver on the same line, and a mistyped geometry stem
        is the commonest user mistake this release makes possible.
    pyflightstream.run.ExecutorConfigurationError
        When the identity pre-flight finds the wrong build installed;
        raised before any point executes.
    pyflightstream.run.CampaignErrors
        After the loop, when at least one executed point failed.

    Examples
    --------
    >>> from pyflightstream.run import LoadsAssessor
    >>> from pyflightstream.run.matrix import run_matrix
    >>> from pyflightstream.workspace import CampaignWorkspace
    >>> records = run_matrix(               # doctest: +SKIP
    ...     "matrix.fs",
    ...     CampaignWorkspace("campaign"),
    ...     name="wing_steady",
    ...     default_fs_version="26.120",
    ...     recipes={"003": "recipes.steady_polar:build"},
    ...     assess=LoadsAssessor(),
    ... )
    """
    default = _default_version(default_fs_version, fs_version, caller="run_matrix")
    _refuse_a_run_that_names_no_build(path, default)
    resolved = resolve_matrix(
        path,
        workspace,
        name=name,
        fs_version=default,
        recipes=recipes,
        fs_exe=fs_exe,
        ignore_missing_families=ignore_missing_families,
    )
    # FR-97. THE GATE IS ON THE COMMAND, not here. The CLI
    # requires a plan receipt; the library API does not: this
    # function is the library entry a caller composes, and a caller that
    # composed plan and run into one call would be made to write a file
    # between them for no reason. `pyfs-matrix run` asks
    # `_plan_receipt_error` before it reaches this.
    plan = plan_campaign(
        resolved.campaign,
        workspace,
        recipes=recipe_registry,
        versions=_row_versions(resolved),
        matrix_path=path,
        write_plan=False,
    )
    if plan.blocked:
        raise MatrixError(
            f"pre-flight blocked {len(plan.blocked)} matrix point(s); nothing was "
            f"executed:\n{plan.summary()}"
        )
    executor, executor_for = _campaign_executor(
        workspace, resolved, path, executor=executor, local=local, hidden=hidden
    )
    # AFTER the executor exists, because a `SolverBuild` names one, and
    # after the pre-flight above, which is planned from the resolved
    # campaign.
    #
    # The pre-flight above and the run below agree on the version a point's
    # script is emitted under: a row whose build declares a version of its
    # own is pre-flighted under that version (`_row_versions`, read off the
    # registry with no executable bound) and runs under it (PFS-2009.05,
    # .05.01 for plan, .05.02 for this path). The executors are still built
    # after the pre-flight, because an executor refuses a path that is not
    # there, and a blocked plan is reported with its summary and costs no
    # solver time before any path is asked for.
    campaign, builds = _bind_row_builds(resolved, default, executor, executor_for)
    return run_campaign(
        campaign,
        executor,
        workspace,
        assess=assess,
        recipes=recipe_registry,
        resume=resume,
        force_rerun=force_rerun,
        builds=builds,
        name_from=name_from,
        accept_unregistered_build=accept_unregistered_build,
        sweep_csv=sweep_csv,
    )


# --- G12 (0.27.0): the additional post over a point's saved simulation --------
#
# `pyfs-matrix post --additional-pproc` and its library half. A row may name a
# second pproc, ADDITIONAL_PPROC: p<id>; for every recorded point of that row
# whose final .fsm is on disk and hashes as its record says, the extraction
# copies it into datapoints/DP-<point>/additional/<pid>/, opens the copy, cuts
# the pproc's distributions, updates the sections, computes their sectional
# loads, exports and closes, with no solve and no save (RPT-062 measured what a
# reopened simulation gives back on 26.124). The record of each extraction goes
# to additional.json beside runs.json, which is never written. It lives HERE,
# beside run_matrix, because it binds the matrix and chooses the executor the
# way run_matrix does, through the one _campaign_executor.
#
# THE SUBMITTING HALF IS NOT BUILT (0.27.0): where the executor chosen is a
# scheduler the pass is refused by name before anything is written. A submitted
# extraction needs a completion pass of its own (its copy of the .fsm kept until
# the job ends, its original hashed afterwards, its record rewritten), which
# costs well over what the local half does.


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
    campaign, executor_for = _campaign_executor(
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
