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
from collections.abc import Callable, Mapping
from pathlib import Path

from pyflightstream._errors import PyflightstreamDeprecationWarning
from pyflightstream.cases import Campaign, ScriptRecipe
from pyflightstream.cases.matrix import (
    MatrixError,
    read_matrix,
    refuse_silent_rows_without_default,
)
from pyflightstream.run import (
    CampaignPlan,
    Executor,
    LocalExecutor,
    OutcomeAssessor,
    SolverBuild,
    plan_campaign,
    run_campaign,
)
from pyflightstream.workspace import CampaignWorkspace, RunRecord
from pyflightstream.workspace.matrix import ResolvedMatrix, resolve_matrix

__all__ = [
    "plan_matrix",
    "run_matrix",
]


def _default_version(
    default_fs_version: str | None,
    fs_version: str | None,
    *,
    caller: str,
) -> str:
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
    str
        The version rows that name no build fall back to.

    Raises
    ------
    pyflightstream.cases.matrix.MatrixError
        Neither keyword given, or the two given and disagreeing.
    """
    if fs_version is not None:
        if default_fs_version is not None and default_fs_version != fs_version:
            raise MatrixError(
                f"{caller}() was given default_fs_version={default_fs_version!r} and "
                f"fs_version={fs_version!r}, which are two names for one argument and "
                "disagree; pass default_fs_version alone."
            )
        warnings.warn(
            f"{caller}(fs_version=...) is the former name of default_fs_version and "
            "will be removed in a future release. The argument is the version rows "
            "whose FS_BUILD column names no build fall back to, so it is a DEFAULT "
            "rather than the version the matrix runs under; a row that names a build "
            "is authoritative. The pyfs-matrix command line keeps --fs-version.",
            PyflightstreamDeprecationWarning,
            stacklevel=3,
        )
        return fs_version
    if default_fs_version is None:
        raise MatrixError(
            f"{caller}() needs default_fs_version=..., the FlightStream version to "
            "emit scripts under for matrix rows whose FS_BUILD column names no "
            "build. The matrix carries no version column, so it is explicit input."
        )
    return default_fs_version


def _refuse_a_run_that_names_no_build(path: str | Path, default: str) -> None:
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
    default: str,
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
        builds[build] = SolverBuild(
            fs_exe=exe,
            fs_version=registered.fs_version or default,
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
) -> CampaignPlan:
    """Pre-flight a run matrix without executing anything.

    Resolution
    (:func:`pyflightstream.workspace.matrix.resolve_matrix`) plus the
    campaign pre-flight
    (:func:`pyflightstream.run.plan_campaign`): every recipe resolves,
    every script builds in dry run, and points already in the manifest
    are marked ALREADY_RECORDED, exactly what
    ``run_matrix(..., resume=True)`` would skip.

    ONE RESIDUAL, stated rather than discovered: every point is
    pre-flighted under ``default_fs_version``, including a point whose
    row names a build whose registry entry declares a version of its own
    (PFS-2009.05). Binding those builds needs one executor per
    installation, an executor refuses a path that is not there, and
    pre-flighting away from the licensed machine is what this function
    is for. So a multi-build matrix is pre-flighted under one version
    and run under each build's own, and a command that differs between
    them is met at run time rather than here.

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
        a DeprecationWarning; the ``pyfs-matrix`` command line keeps
        ``--fs-version``.
    recipe_registry : dict of str to ScriptRecipe, optional
        Named recipe registry (name to callable) consulted before
        treating a recipe reference as ``module:function``, forwarded
        to the campaign pre-flight.
    write_plan : bool
        Write the JSON summary as ``plan.json`` in the campaign root
        (default True), as in the campaign pre-flight.

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
        path, workspace, name=name, fs_version=default, recipes=recipes, fs_exe=fs_exe
    )
    return plan_campaign(
        resolved.campaign, workspace, recipes=recipe_registry, write_plan=write_plan
    )


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
    hidden: bool | None = None,
    fs_version: str | None = None,
) -> list[RunRecord]:
    """Read a run matrix and run it: the one-call first-class entry.

    In order: the matrix converts through the canonical campaign form,
    its codes resolve against the workspace input library
    (:func:`pyflightstream.workspace.matrix.resolve_matrix`), the whole
    campaign pre-flights in dry run, and only then the points execute
    through :func:`pyflightstream.run.run_campaign`, landing one
    manifest record per point. A blocked pre-flight refuses to execute
    at all, so a broken recipe or missing artifact costs no solver time.

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
        a DeprecationWarning.
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
    resume : bool
        With True, points already in the manifest are skipped, so a
        grown matrix re-runs only its new points; with False (the
        default) an already-recorded point raises before anything
        executes, as in :func:`pyflightstream.run.run_campaign`.
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
        path, workspace, name=name, fs_version=default, recipes=recipes, fs_exe=fs_exe
    )
    plan = plan_campaign(resolved.campaign, workspace, recipes=recipe_registry)
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
        executor = LocalExecutor(resolved.fs_exe, hidden=hidden)
    windowless = bool(hidden)

    def executor_for(exe: Path) -> Executor:
        """Build the executor of one row's own installation.

        The window setting is the one the campaign's own executor was
        built with, so a second build runs the same way the first does.
        """
        return supplied if supplied is not None else LocalExecutor(exe, hidden=windowless)

    # AFTER the executor exists, because a `SolverBuild` names one, and
    # after the pre-flight above, which is planned from the resolved
    # campaign.
    #
    # THE TWO CAMPAIGNS CAN NOW DIFFER in the version a point's script is
    # emitted under: the pre-flight above builds every script under the
    # campaign default, while a row whose build declares a version of its
    # own runs under that one (PFS-2009.05). It said here that they could
    # not, and that was true while every build declared `default`. The
    # residual is stated rather than closed because closing it means
    # constructing the executors above the pre-flight, and an executor
    # refuses a path that is not there, which would put an existence check
    # ahead of the promise this function makes about a blocked plan: that
    # a broken recipe is reported with its summary and costs no solver
    # time. `plan_matrix` carries the same residual for the same reason
    # and has no executor at all to offer.
    campaign, builds = _bind_row_builds(resolved, default, executor, executor_for)
    return run_campaign(
        campaign,
        executor,
        workspace,
        assess=assess,
        recipes=recipe_registry,
        resume=resume,
        builds=builds,
    )
