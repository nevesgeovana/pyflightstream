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

:mod:`pyflightstream.run` deliberately does NOT import this module, so
importing it can never be part of an import cycle: the dependency runs
one way, from here into the campaign loop.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from pyflightstream._deprecations import MATRIX_FS_VERSION
from pyflightstream._errors import InputArtifactError, PyflightstreamDeprecationWarning
from pyflightstream.cases import Campaign, ScriptRecipe
from pyflightstream.cases.matrix import (
    MatrixError,
    read_matrix,
    refuse_silent_rows_without_default,
)
from pyflightstream.run import (
    CampaignPlan,
    Executor,
    ExecutorConfigurationError,
    LocalExecutor,
    OutcomeAssessor,
    SolverBuild,
    Submitting,
    SubmittingExecutor,
    on_a_cluster,
    plan_campaign,
    run_campaign,
)
from pyflightstream.workspace import CampaignWorkspace, RunRecord, write_input_guides
from pyflightstream.workspace.inputs import hpc_profiles, resolve_hpc_profile
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
    "plan_matrix",
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
    # Held before the branch below rebinds the name, because it is what
    # tells a build's executor apart from the campaign's: a caller who
    # supplied an executor supplied it for the whole run, whatever
    # installation a row names, and building a LocalExecutor beside it
    # would send some rows somewhere the caller never asked for.
    supplied = executor
    forced = False
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
        submitting = None if local else _cluster_executor(workspace, resolved)
        forced = local and on_a_cluster() and bool(hpc_profiles(workspace.inputs_dir))
        executor = submitting or LocalExecutor(resolved.fs_exe, hidden=hidden, forced_local=forced)
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
        return LocalExecutor(exe, hidden=windowless, forced_local=forced)

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
