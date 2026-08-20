"""Binding a run matrix to the workspace input library.

Pipeline role: the workspace-layer half of the run matrix. The reader
and the converter stay in :mod:`pyflightstream.cases.matrix`, which
parses the verified 15-column file and maps it onto the canonical
``campaign.toml`` model without needing anything above the cases layer.
What lives HERE is the step that needs the layer above: resolving the
matrix's reference columns against the input library under ``inputs/``.

REF resolves to reference data (applied to each case's ``reference``),
SET to a solver preset (its runtime subset applied to each case's
``solver``), ENTRY to named boundary groups (returned verbatim), and
FS_BUILD to an executable through the build registry. Plain conversion
never needs the library; resolution applies only when the matrix is
about to be planned or run.

This module exists because the reader used to do the binding itself and
paid for it with imports deferred to call time, which recorded an
upward dependency while hiding it from every module-level reader
(OPS-2007.01, PFS-2009.05). The execution half went to
:mod:`pyflightstream.run.matrix` in the same move, and the direction now
reads off the import block: this module imports the cases layer
downward and the workspace layer sideways, and imports nothing from
:mod:`pyflightstream.run`.
"""

from __future__ import annotations

import warnings
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import Campaign, ReferenceData, SimCase, SolverSettings
from pyflightstream.cases.matrix import (
    MatrixError,
    MatrixRow,
    read_matrix,
    refuse_silent_rows_without_default,
    to_campaign,
)
from pyflightstream.workspace import (
    CampaignWorkspace,
    GroupsArtifact,
    InputArtifactError,
    ReferenceArtifact,
    SetupArtifact,
)

__all__ = [
    "ResolvedMatrix",
    "resolve_matrix",
]


@dataclass(frozen=True)
class ResolvedMatrix:
    """A matrix bound to a workspace input library, ready to plan or run.

    Attributes
    ----------
    campaign : Campaign
        The canonical campaign form, with the resolved reference data
        applied to each case (``reference``) and the solver preset
        applied to each case's runtime settings (``solver``); the
        historical codes stay in the case variables, so nothing of the
        matrix is lost.
    references : dict of str to ReferenceArtifact
        Resolved reference-data artifacts, keyed by REF code.
    setups : dict of str to SetupArtifact
        Resolved solver-setup presets, keyed by SET code; the raw
        preset table is kept verbatim for consumers beyond the runtime
        subset (see :func:`resolve_matrix`).
    groups : dict of str to GroupsArtifact
        Resolved named boundary groups, keyed by ENTRY code; members
        are boundary labels or indices, verbatim, for the script layer
        and the post-processing aggregation.
    fs_exe : Path
        The executable selected through the FS_BUILD column (registry
        mode) or the explicit override; existence is checked by the
        executor at construction, not here.
    row_builds : tuple of (str or None)
        Where each case's build came from, one entry per case of
        ``campaign.sims`` and in the same order: the build id the ROW's
        FS_BUILD cell named, or None when the cell named none and the
        campaign default answered for it (PFS-2009.08.02).

        It is the ONE fact only this function knows. ``fs_exe`` says
        WHICH installation was selected, and by the time a manifest
        record is written nothing can still tell whether the row asked
        for it or inherited it, because both arrive as the same
        executable. :func:`pyflightstream.run.matrix.run_matrix` turns
        each entry into :attr:`pyflightstream.cases.SimCase.fs_build`
        and the matching ``builds`` mapping, which is what makes the
        record's ``fs_version_source`` say ``row`` rather than
        ``campaign_default``.

        Every entry is None under an explicit ``fs_exe`` override, and
        that is a statement rather than a gap: the override runs every
        point on one caller-named executable and overrules whatever the
        cells said, which is exactly what the warning it raises says
        will be recorded.
    """

    campaign: Campaign
    references: dict[str, ReferenceArtifact] = field(default_factory=dict)
    setups: dict[str, SetupArtifact] = field(default_factory=dict)
    groups: dict[str, GroupsArtifact] = field(default_factory=dict)
    fs_exe: Path = Path()
    row_builds: tuple[str | None, ...] = ()


def _name_rows(rows: list[MatrixRow], wanted: tuple[str | None, ...], build: str | None) -> str:
    """List the rows whose build id is ``build``, by row number and POL."""
    return ", ".join(
        f"row {row.row_number} (POL {row.pol})"
        for row, named in zip(rows, wanted, strict=True)
        if named == build
    )


def _resolve_build(
    rows: list[MatrixRow],
    workspace: CampaignWorkspace,
    override: str | Path | None,
    path: str | Path,
    default: str,
) -> tuple[Path, tuple[str | None, ...]]:
    """Select the executable, and say which rows chose it themselves.

    The explicit override always wins (it is the only way to run the
    MANUAL mode); registry mode requires the active rows to
    agree on a single build id, because a campaign binds to exactly
    one FlightStream installation.

    A row whose FS_BUILD cell strips to empty NAMES NO BUILD and falls
    back to the campaign default, which is the promise
    :func:`~pyflightstream.cases.matrix.refuse_silent_rows_without_default`
    has always made in its own refusal text and which nothing kept: the
    empty cell was carried into the build set verbatim, so a matrix of
    silent rows asked the registry for the build id ``''`` and a matrix
    mixing a silent row with a named one was refused for naming two
    builds, one of which was the empty string (PFS-2009.08.02).

    Parameters
    ----------
    rows : list of MatrixRow
        The ACTIVE rows, in file order.
    workspace : CampaignWorkspace
        The managed campaign root carrying the build registry.
    override : str or Path or None
        The explicit ``fs_exe`` override, when the caller passed one.
    path : str or Path
        Matrix location, for the messages.
    default : str
        The campaign default version, which is the build id a silent row
        falls back to. It is non-blank by the time this runs: a blank one
        is refused above, before anything is resolved.

    Returns
    -------
    tuple of Path and tuple of (str or None)
        The executable, and per row the build id the ROW named, with
        None where the campaign default answered instead.
    """
    named = tuple(row.fs_build.strip() or None for row in rows)
    if override is not None:
        # The override is the only way to run MANUAL, so it has to win.
        # It used to win SILENTLY over a row that named a real build,
        # which is how a row saying FS_BUILD 26.121 ran on the 26.120
        # executable and was recorded as having requested 26.120, with
        # nothing said (measured on the author's campaign, 2026-08-03).
        # Overruling an explicit request is a decision the caller is
        # entitled to hear about, whatever it then does with it.
        #
        # A SILENT row is not overruled by it and must not be listed: it
        # asked for nothing, so there is nothing to overrule, and listing
        # it printed an empty id into the middle of the sentence.
        overruled = sorted({build for build in named if build and build.upper() != "MANUAL"})
        if overruled:
            warnings.warn(
                f"the explicit fs_exe override runs every row on {Path(override).name}, "
                f"overruling the FS_BUILD value(s) {', '.join(overruled)} that row(s) of "
                f"{path} name. Those rows will be recorded against the campaign's "
                "declared version, not the build they asked for. Run the matrix once "
                "per build, or drop the override where no row is MANUAL.",
                PyflightstreamWarning,
                stacklevel=3,
            )
        # Under the override NO row chose the installation: one executable
        # the caller named runs every point, which is what the warning
        # above promises will be recorded, so the provenance reported here
        # has to agree with it rather than with the overruled cells.
        return Path(override), tuple(None for _ in named)
    effective = tuple(build if build is not None else default.strip() for build in named)
    builds = sorted(set(effective))
    if len(builds) > 1:
        inherited = _name_rows(rows, named, None)
        detail = (
            f" The campaign default {default.strip()} answers for the row(s) whose "
            f"FS_BUILD cell names no build: {inherited}."
            if inherited
            else ""
        )
        raise MatrixError(
            f"the active rows of {path} run on {len(builds)} FS_BUILD values "
            f"({', '.join(builds)}), but a campaign binds to exactly one FlightStream "
            f"installation.{detail} Run the matrix once per build, or pass the explicit "
            "fs_exe override to force a single executable"
        )
    build = builds[0]
    if build.upper() == "MANUAL":
        raise MatrixError(
            "FS_BUILD is MANUAL, the explicit-path mode: pass fs_exe=... "
            "(the explicit override path). MANUAL never reads the build registry, "
            "and the executable is never guessed"
        )
    try:
        return workspace.resolve_executable(build), named
    except InputArtifactError as error:
        # Which of the two ways the id arrived is named, because the
        # remedies differ: a build a ROW asked for is registered or
        # corrected in the cell, while one the DEFAULT supplied is a
        # version that answers for rows naming no build at all, and
        # editing an FS_BUILD cell would not touch it.
        if any(entry is None for entry in named):
            source = (
                f"the campaign default version {build!r} is the build the row(s) of "
                f"{path} that name no build fall back to ({_name_rows(rows, named, None)}"
                "), and the workspace build registry cannot resolve it"
            )
        else:
            source = (
                f"the FS_BUILD column of {path} names build {build!r}, which the "
                "workspace build registry cannot resolve"
            )
        raise InputArtifactError(
            f"{source}; register it in inputs/executables.toml, or pass the explicit "
            f"fs_exe override. {error}"
        ) from error


def _resolve_code(workspace: CampaignWorkspace, kind: str, code: str, pol: str):
    """Resolve one REF/SET/ENTRY code, naming the row and the target file."""
    column, subdir, resolver = {
        "reference": ("REF", "references", workspace.resolve_reference),
        "setup": ("SET", "setups", workspace.resolve_setup),
        "group": ("ENTRY", "groups", workspace.resolve_group),
    }[kind]
    try:
        return resolver(code)
    except InputArtifactError as error:
        raise InputArtifactError(
            f"matrix row POL {pol}: the {column} column names {kind} {code!r}, which "
            "the workspace input library cannot resolve; put the artifact at "
            f"inputs/{subdir}/{code}.toml (or fix the matrix code). {error}"
        ) from error


def _solver_from_setup(setup: SetupArtifact, set_code: str) -> SolverSettings:
    """Map the runtime subset of one preset onto the case solver settings.

    Preset keys that name :class:`~pyflightstream.cases.SolverSettings`
    fields apply; the remaining keys stay verbatim in the artifact (a
    warning lists them), awaiting the formal solver-setup model that
    will consume the full table.
    """
    known = set(SolverSettings.model_fields)
    matched = {key: value for key, value in setup.settings.items() if key in known}
    unmatched = sorted(key for key in setup.settings if key not in known)
    if unmatched:
        warnings.warn(
            f"setup preset {set_code!r}: key(s) {', '.join(unmatched)} do not map to "
            "the case solver settings yet and were left to the preset artifact "
            "verbatim; the formal solver-setup model will consume the full table",
            PyflightstreamWarning,
            stacklevel=2,
        )
    try:
        return SolverSettings(**matched)
    except ValidationError as error:
        raise InputArtifactError(
            f"setup preset {set_code!r} does not fit the case solver settings: {error}"
        ) from error


def resolve_matrix(
    path: str | Path,
    workspace: CampaignWorkspace,
    *,
    name: str,
    fs_version: str,
    recipes: Mapping[str, str],
    fs_exe: str | Path | None = None,
) -> ResolvedMatrix:
    """Bind a run matrix to the workspace input library.

    The matrix converts through the canonical campaign form
    (:func:`pyflightstream.cases.matrix.to_campaign`) and its reference
    columns resolve against the library under ``inputs/``: REF to
    reference data (applied to each case's ``reference``), SET to a
    solver preset (its runtime subset applied to each case's
    ``solver``), ENTRY to named boundary groups (returned verbatim), and
    FS_BUILD to an executable through the build registry. A missing
    artifact fails with a didactic error naming the row, the missing id,
    and the ``inputs/`` file to create; plain conversion
    (:func:`pyflightstream.cases.matrix.convert_matrix`) never needs the
    library.

    Parameters
    ----------
    path : str or Path
        Matrix location; only RUN = 1 rows resolve.
    workspace : CampaignWorkspace
        The managed campaign root carrying the input library.
    name : str
        Campaign name; the matrix has none, so it is explicit input.
    fs_version : str
        FlightStream version, canonical identifier (26.120); a vendor
        release name works only where it names exactly one registered
        build. The FS_BUILD column
        selects an executable, not a command-database version, so the
        version stays explicit input.

        It is also the build id a row whose FS_BUILD cell names nothing
        falls back to, which is the one sense in which it answers for an
        executable: the scripts of every point are emitted under this
        version whatever the FS_BUILD column says, because a build id is
        a key of the workspace registry and never a declaration of which
        command database a build carries.
    recipes : mapping of str to str
        FS_SCRIPT code to recipe reference, as in
        :func:`pyflightstream.cases.matrix.to_campaign`.
    fs_exe : str or Path, optional
        Explicit executable override; it always wins over the build
        registry and is the only way to run the MANUAL mode.

    Returns
    -------
    ResolvedMatrix
        The campaign with resolved artifacts applied, the artifacts
        themselves keyed by their codes, the selected executable, and
        per row whether that executable came from the row's own
        FS_BUILD cell or from the campaign default
        (:attr:`ResolvedMatrix.row_builds`).

    Raises
    ------
    pyflightstream.cases.matrix.MatrixError
        Layout deviations, no active row, two FS_BUILD values, MANUAL
        mode without the explicit override, or a row naming no build
        with a campaign default that strips to empty. The last is
        raised before the build is selected, so no executable is looked
        up (PFS-2009.08.03).
    pyflightstream.workspace.InputArtifactError
        A code the library cannot resolve, or a preset that does not
        fit the case solver settings.

    Examples
    --------
    >>> from pyflightstream.workspace import CampaignWorkspace
    >>> from pyflightstream.workspace.matrix import resolve_matrix
    >>> resolved = resolve_matrix(          # doctest: +SKIP
    ...     "matrix.fs",
    ...     CampaignWorkspace("campaign"),
    ...     name="wing_steady",
    ...     fs_version="26.120",
    ...     recipes={"003": "recipes.steady_polar:build"},
    ... )
    >>> resolved.fs_exe                     # doctest: +SKIP
    WindowsPath('C:/FlightStream/FlightStream.exe')
    """
    rows = read_matrix(path)
    if not rows:
        raise MatrixError(f"{path} has no active rows (RUN = 1); nothing to resolve or run")
    # BEFORE the build is selected, not after: a silent row falls back to
    # this default, so a blank one leaves nothing naming a build for that
    # row, and the refusal has to arrive before an executable is looked up
    # rather than as an unregistered-build message about the empty string
    # (PFS-2009.08.03). The two entry points in
    # `pyflightstream.run.matrix` refuse earlier still, above this whole
    # function; this call is what covers a caller who binds a matrix
    # directly.
    refuse_silent_rows_without_default(rows, fs_version, path)
    exe, row_builds = _resolve_build(
        rows, workspace, override=fs_exe, path=path, default=fs_version
    )
    campaign = to_campaign(path, name=name, fs_version=fs_version, fs_exe=str(exe), recipes=recipes)
    references: dict[str, ReferenceArtifact] = {}
    setups: dict[str, SetupArtifact] = {}
    groups: dict[str, GroupsArtifact] = {}
    solvers: dict[str, SolverSettings] = {}
    for row in rows:
        if row.ref_code not in references:
            references[row.ref_code] = _resolve_code(workspace, "reference", row.ref_code, row.pol)
        if row.set_code not in setups:
            setups[row.set_code] = _resolve_code(workspace, "setup", row.set_code, row.pol)
            solvers[row.set_code] = _solver_from_setup(setups[row.set_code], row.set_code)
        if row.entry_code not in groups:
            groups[row.entry_code] = _resolve_code(workspace, "group", row.entry_code, row.pol)
    sims: list[SimCase] = []
    for case, row in zip(campaign.sims, rows, strict=True):
        reference = references[row.ref_code]
        sims.append(
            case.model_copy(
                update={
                    "reference": ReferenceData(area=reference.area_m2, length=reference.chord_m),
                    "solver": solvers[row.set_code],
                }
            )
        )
    return ResolvedMatrix(
        campaign=campaign.model_copy(update={"sims": sims}),
        references=references,
        setups=setups,
        groups=groups,
        fs_exe=exe,
        row_builds=row_builds,
    )
