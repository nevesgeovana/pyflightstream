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
from collections.abc import Mapping
from pathlib import Path

from pyflightstream._errors import PyflightstreamDeprecationWarning
from pyflightstream.cases import ScriptRecipe
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
    plan_campaign,
    run_campaign,
)
from pyflightstream.workspace import CampaignWorkspace, RunRecord
from pyflightstream.workspace.matrix import resolve_matrix

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
        A REF, SET or ENTRY code the input library cannot resolve.

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
        resolved executable.
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
        The records executed by this call, in execution order.

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
    return run_campaign(
        resolved.campaign,
        executor,
        workspace,
        assess=assess,
        recipes=recipe_registry,
        resume=resume,
    )
