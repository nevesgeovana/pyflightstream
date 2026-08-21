"""Binding a run matrix to the workspace input library.

Pipeline role: the workspace-layer half of the run matrix. The reader
and the converter stay in :mod:`pyflightstream.cases.matrix`, which
parses the verified 15-column file and maps it onto the canonical
``campaign.toml`` model without needing anything above the cases layer.
What lives HERE is the step that needs the layer above: resolving the
matrix's reference columns against the input library under ``inputs/``.

REF resolves to reference data (applied to each case's ``reference``),
SET to a solver preset (its runtime subset applied to each case's
``solver``), ENTRY to named boundary groups (returned verbatim),
FS_BUILD to an executable through the build registry, and the
``GEOMETRY`` variable of the free ``VAR_NAMES_VALUES`` cell to a staged
geometry file (applied to each case's ``geometry``). Plain conversion
never needs the library; resolution applies only when the matrix is
about to be planned or run.

THE GEOMETRY ARRIVED LAST AND IT IS WHY 0.8.1 EXISTS. The run layer had
always done its half: :func:`pyflightstream.run._prepare_case` stages
:attr:`pyflightstream.cases.SimCase.geometry`, hashes it into the
record, and rewrites the field to the STAGED path before the builder is
called. Nothing ever ASSIGNED that field from a matrix, so a row could
not name a geometry at all, the value was prepared and read by nobody,
and a workflow rendered a script with no ``OPEN`` in it. The script ran,
against whatever the solver happened to have open, and the numbers were
wrong with nothing said (PFS-2025.02.01).

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
from pathlib import Path, PurePath

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
from pyflightstream.cases.workflows import GEOMETRY_VARIABLE
from pyflightstream.workspace import (
    CampaignWorkspace,
    GroupsArtifact,
    InputArtifactError,
    ReferenceArtifact,
    SetupArtifact,
)

# SIDEWAYS, to the module of this layer that owns the build registry.
# `CampaignWorkspace.resolve_executable` is the path half alone and a
# matrix row now needs the version its build declares beside it, so the
# registry is read once through the function that returns both
# (PFS-2009.05).
from pyflightstream.workspace.inputs import RegisteredBuild, resolve_build

__all__ = [
    "GEOMETRY_VARIABLE",
    "ResolvedMatrix",
    "resolve_matrix",
]

#: The ``VAR_NAMES_VALUES`` key a row names its geometry with.
#:
#: RE-EXPORTED, not defined here. Its home is
#: :data:`pyflightstream.cases.workflows.GEOMETRY_VARIABLE`, beside the
#: eleven other cell keys, so the builders that refuse a bad value can
#: name the key the author typed; this module keeps the published import
#: path and reads the cell.
#:
#: The value is an input-library ID, which is the STEM of a file staged
#: under ``inputs/geometries/``, and never a path or a file name. That is
#: the same rule the REF, SET and ENTRY columns follow, and it is what
#: lets one geometry be cited by many rows, staged once per case, and
#: hashed into every record that used it
#: (:attr:`pyflightstream.run.RunRecord.inputs_sha256`).
#:
#: It is a VARIABLE and not a column of its own, deliberately: the
#: fifteen-column layout is a published format and widening it again is a
#: BREAK, which 0.8.0 has already spent once (PFS-2025.01). A key in the
#: free cell costs no format change, so every matrix written before this
#: release reads at the same width and resolves exactly as it did.


@dataclass(frozen=True)
class ResolvedMatrix:
    """A matrix bound to a workspace input library, ready to plan or run.

    Attributes
    ----------
    campaign : Campaign
        The canonical campaign form, with the resolved reference data
        applied to each case (``reference``), the solver preset applied
        to each case's runtime settings (``solver``), and the resolved
        library path of the row's ``GEOMETRY`` applied to each case's
        ``geometry`` where the row named one; the historical codes and
        the ``GEOMETRY`` stem itself stay in the case variables, so
        nothing of the matrix is lost.
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
        The executable the CAMPAIGN ITSELF binds to, which is the one
        answering for rows whose FS_BUILD cell names no build;
        existence is checked by the executor at construction, not here.

        Its meaning is unchanged by the multi-build support added at
        PFS-2009.05, deliberately, because everything downstream reads
        it as the campaign's own installation. Where several builds are
        in play, ``builds`` below is what says which executable each
        row's own build is; where only one is, the two agree and this
        field is that one.

        Where no active row names a build, the campaign default answers
        for every row and this is its executable. Where EVERY active row
        names one, no row runs on the campaign's own installation at
        all, and this field takes the first active row's build rather
        than the default's, so it still names an installation this
        matrix really uses instead of one that would merely have to be
        registered.
    builds : dict of str to RegisteredBuild
        The registry entry of each build id an active row NAMES, keyed
        by that id: its executable and the version it declares, or None
        where it declares none. Empty under the explicit ``fs_exe``
        override, which overrules the column, and empty for a matrix
        whose every active row is silent, because neither names a
        build.

        A build id appears here whether or not it is also the campaign
        default: what puts it here is a row naming it, which is the same
        condition that puts a non-None entry in ``row_builds``.
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
    builds: dict[str, RegisteredBuild] = field(default_factory=dict)
    row_builds: tuple[str | None, ...] = ()


def _name_rows(rows: list[MatrixRow], wanted: tuple[str | None, ...], build: str | None) -> str:
    """List the rows whose build id is ``build``, by row number and POL."""
    return ", ".join(
        f"row {row.row_number} (POL {row.pol})"
        for row, named in zip(rows, wanted, strict=True)
        if named == build
    )


def _registered_build(
    workspace: CampaignWorkspace,
    build: str,
    rows: list[MatrixRow],
    named: tuple[str | None, ...],
    path: str | Path,
    default: str,
) -> RegisteredBuild:
    """Read one build's registry entry, naming how the build id arrived.

    Parameters
    ----------
    workspace : CampaignWorkspace
        The managed campaign root carrying the build registry.
    build : str
        The build id to resolve.
    rows : list of MatrixRow
        The ACTIVE rows, in file order, for the row numbers of the
        message.
    named : tuple of (str or None)
        Per row the build id the ROW named, None where it named none.
    path : str or Path
        Matrix location, for the message.
    default : str
        The campaign default version, already stripped.

    Returns
    -------
    RegisteredBuild
        The executable and the version the registry declares, or None
        for a build declaring none.

    Raises
    ------
    pyflightstream.workspace.InputArtifactError
        The registry cannot resolve the build id, or resolves it to a
        malformed entry.
    """
    try:
        return resolve_build(workspace.inputs_dir, build)
    except InputArtifactError as error:
        # Which of the two ways the id arrived is named, because the
        # remedies differ: a build a ROW asked for is registered or
        # corrected in the cell, while one the DEFAULT supplied is a
        # version that answers for rows naming no build at all, and
        # editing an FS_BUILD cell would not touch it.
        if build == default and any(entry is None for entry in named):
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


def _resolve_build(
    rows: list[MatrixRow],
    workspace: CampaignWorkspace,
    override: str | Path | None,
    path: str | Path,
    default: str,
) -> tuple[Path, dict[str, RegisteredBuild], tuple[str | None, ...]]:
    """Select the executables, and say which rows chose one themselves.

    The explicit override always wins (it is the only way to run the
    MANUAL mode). In registry mode EVERY build the active rows name is
    resolved, one entry per build id, and the row that named it carries
    its own installation into the run.

    THE ACTIVE ROWS USED TO HAVE TO AGREE on a single build id, because
    a campaign declared one ``fs_exe`` and one ``fs_version`` and a
    second FS_BUILD value would have been recorded as a falsehood: every
    point named the campaign's executable whatever it ran on. That is no
    longer the shape underneath. A case names its build
    (:attr:`pyflightstream.cases.SimCase.fs_build`), the campaign loop
    takes a ``builds`` mapping of
    :class:`pyflightstream.run.SolverBuild`, and each point is recorded
    against the installation it really ran on, so the refusal was
    protecting a record that can now be told the truth (PFS-2009.05).

    Every OTHER refusal is unchanged and none of them is what that one
    was: MANUAL still needs the explicit override, an override still
    warns that it overrules a row's cell, an unregistered id is still
    refused with the remedy that matches how it arrived, and a silent
    row with no campaign default is still refused above this function.

    A row whose FS_BUILD cell strips to empty NAMES NO BUILD and falls
    back to the campaign default, which is the promise
    :func:`~pyflightstream.cases.matrix.refuse_silent_rows_without_default`
    has always made in its own refusal text and which nothing kept: the
    empty cell was carried into the build set verbatim, so a matrix of
    silent rows asked the registry for the build id ``''``
    (PFS-2009.08.02).

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
    tuple of Path, dict of str to RegisteredBuild, and tuple of (str or None)
        The campaign's own executable
        (:attr:`ResolvedMatrix.fs_exe`), the registry entry of each
        build id a row named, and per row the build id the ROW named
        with None where the campaign default answered instead.

    Raises
    ------
    pyflightstream.cases.matrix.MatrixError
        FS_BUILD is MANUAL and no explicit override was given.
    pyflightstream.workspace.InputArtifactError
        A build id the workspace registry cannot resolve.
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
        return Path(override), {}, tuple(None for _ in named)
    fallback = default.strip()
    effective = tuple(build if build is not None else fallback for build in named)
    # EVERY effective build is asked, not only the one a single-build
    # matrix used to collapse to: MANUAL names no executable whichever row
    # asks for it, and refusing it here keeps the message the one a caller
    # already knows.
    if any(build.upper() == "MANUAL" for build in effective):
        raise MatrixError(
            "FS_BUILD is MANUAL, the explicit-path mode: pass fs_exe=... "
            "(the explicit override path). MANUAL never reads the build registry, "
            "and the executable is never guessed"
        )
    # `dict.fromkeys` rather than `set`, so the registry is read in the
    # order the file names the builds and a refusal names the first one a
    # reader would look at rather than the alphabetically smallest.
    resolved = {
        build: _registered_build(workspace, build, rows, named, path, fallback)
        for build in dict.fromkeys(effective)
    }
    # The campaign's own installation is the one answering for a row that
    # names no build. Where every row names one, no row runs on it, and
    # taking the default's executable would make an unrelated registry
    # entry a precondition of a run that never touches it; the first
    # active row's build is an installation this matrix really uses.
    campaign_build = fallback if any(entry is None for entry in named) else effective[0]
    builds = {build: resolved[build] for build in dict.fromkeys(named) if build is not None}
    return resolved[campaign_build].fs_exe, builds, named


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


def _resolve_geometry(workspace: CampaignWorkspace, artifact_id: str, pol: str) -> Path:
    """Resolve one ``GEOMETRY`` id, naming the row and the library folder.

    The sibling of :func:`_resolve_code` for the one library kind a
    matrix names from its free cell rather than from a column. It is a
    separate function for one reason, and the reason is in the message:
    a reference, setup or group is a ``.toml`` the user writes, while a
    geometry is a FILE THE USER STAGED under any extension, so the
    "create this file" half of the refusal cannot be the same sentence.

    Resolution itself is not reimplemented here.
    :func:`pyflightstream.workspace.inputs.resolve_geometry` already
    takes a stem of any extension, already refuses an unknown id by
    listing the available ones, and already refuses a stem that two
    staged files share; a second resolver would be a second answer to
    "which file is this id".

    Parameters
    ----------
    workspace : CampaignWorkspace
        The managed campaign root carrying the input library.
    artifact_id : str
        The geometry id, which is the stem of a file under
        ``inputs/geometries/``.
    pol : str
        Polar identifier of the row that named it, for the message. It
        is the POL and not the row number because the POL is what the
        author reads down the left of their own matrix, which is the
        sibling refusal's own choice.

    Returns
    -------
    Path
        The staged geometry file, as the library holds it. It is the
        LIBRARY path: the run layer copies it into the case's own
        ``inputs/`` directory and rewrites
        :attr:`pyflightstream.cases.SimCase.geometry` to that copy
        before any builder sees it.

    Raises
    ------
    pyflightstream.workspace.InputArtifactError
        The library cannot resolve the id, or the stem is shared by
        several staged files. The message names the row's POL, the stem
        written, and (through the chained library refusal) the ids that
        would have resolved. The structured ``kind``, ``artifact_id``
        and ``available`` attributes are carried across, so a caller
        that offers the user a choice does not parse the sentence.
    """
    try:
        return workspace.resolve_geometry(artifact_id)
    except InputArtifactError as error:
        # THE LIKELIEST MISTAKE IS ANSWERED FIRST, and it is the one the
        # previous wording actively made worse. The id rule permits a
        # dot, so `GEOMETRY: wing_clean.fsm` (what anyone who has just
        # staged a file writes) passes the id check, misses in the
        # library, and used to be told to stage
        # `inputs/geometries/wing_clean.fsm.fsm`. That instruction is
        # satisfiable and wrong: the file was already staged correctly
        # and the CELL is what needed fixing.
        stem = PurePath(artifact_id).stem
        if PurePath(artifact_id).suffix and stem in (error.available or ()):
            remedy = (
                f"the id is the file name STEM and not the file name, so write "
                f"'{GEOMETRY_VARIABLE}: {stem}'. The file itself is staged correctly"
            )
        else:
            remedy = (
                f"stage the file as inputs/geometries/{artifact_id}<suffix> and write "
                f"'{GEOMETRY_VARIABLE}: {artifact_id}', or fix the matrix cell. A "
                "workflow opens a saved simulation, so stage a .fsm; a recipe of your "
                "own receives whatever the library holds"
            )
        raise InputArtifactError(
            f"matrix row POL {pol}: the {GEOMETRY_VARIABLE} variable names geometry "
            f"{artifact_id!r}, which the workspace input library cannot resolve; "
            f"{remedy}. A row that names no {GEOMETRY_VARIABLE} at all opens no file "
            f"and is unaffected. {error}",
            kind=error.kind,
            artifact_id=error.artifact_id,
            available=error.available,
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

    THE ``GEOMETRY`` VARIABLE RESOLVES HERE TOO, and it is the fifth of
    those bindings rather than a sixth kind of thing
    (:data:`GEOMETRY_VARIABLE`, PFS-2025.02.01). A row writing
    ``GEOMETRY: wing_v2`` in its ``VAR_NAMES_VALUES`` cell resolves that
    stem against ``inputs/geometries/`` and the file lands on the case's
    :attr:`~pyflightstream.cases.SimCase.geometry`, which is what the
    campaign loop stages, hashes into the record, and rewrites to the
    staged copy before a builder opens it. A row naming no geometry
    leaves the field absent and resolves exactly as it did before this
    release.

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
        executable.

        It is a DEFAULT rather than the version every point runs under.
        A build id is a key of the workspace registry and never a
        declaration of which command database a build carries, so the
        FS_BUILD cell alone still cannot change the version; what can is
        the registry ENTRY that build id names, which may declare one
        (:func:`pyflightstream.workspace.inputs.resolve_build`). A row
        whose build declares a version is emitted under that version and
        every other row under this one. Nothing here overrules THIS
        argument for a row that names no build: the caller declared it
        directly, and a registry entry does not overrule a declaration
        the caller made in the call.
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
        themselves keyed by their codes, the campaign's own executable,
        the registry entry of every build a row names
        (:attr:`ResolvedMatrix.builds`), and per row whether the
        installation came from the row's own FS_BUILD cell or from the
        campaign default (:attr:`ResolvedMatrix.row_builds`).

    Raises
    ------
    pyflightstream.cases.matrix.MatrixError
        Layout deviations, no active row, MANUAL mode without the
        explicit override, or a row naming no build with a campaign
        default that strips to empty. The last is raised before the
        build is selected, so no executable is looked up
        (PFS-2009.08.03). Two FS_BUILD values USED TO BE REFUSED here
        and no longer are: each row runs on the installation it names
        (PFS-2009.05).
    pyflightstream.workspace.InputArtifactError
        A code the library cannot resolve, a ``GEOMETRY`` stem the
        library cannot resolve or that two staged files share, or a
        preset that does not fit the case solver settings.

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
    exe, builds, row_builds = _resolve_build(
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
        update: dict[str, object] = {
            "reference": ReferenceData(area=reference.area_m2, length=reference.chord_m),
            "solver": solvers[row.set_code],
        }
        # ABSENT AND BLANK ARE THE SAME SILENCE, and it is the same rule
        # `_resolve_build` applies one function above: a cell that is
        # empty NAMES NOTHING. It matters more here than there, because
        # it is what makes the promise this key ships with true: a row
        # that does not name a geometry leaves the field absent, so every
        # matrix written before 0.8.1 resolves to exactly the campaign it
        # resolved to before, and the builders emit exactly the bytes they
        # emitted before.
        #
        # NO `.strip()` HERE, deliberately, and the first version of this
        # line had one. The reader strips every VAR_NAMES_VALUES value as
        # it parses the cell, so `GEOMETRY:   ` arrives as `''` already
        # and a second strip could never change an outcome: a mutation
        # deleting it left the whole suite green, which is what an
        # unreachable guard does. The composed behaviour is asserted in
        # `tests/test_matrix_run.py`, at the reader AND here, rather than
        # defended twice in code and proven in neither place.
        stem = row.variables.get(GEOMETRY_VARIABLE, "")
        if stem:
            update["geometry"] = str(_resolve_geometry(workspace, stem, row.pol))
        sims.append(case.model_copy(update=update))
    return ResolvedMatrix(
        campaign=campaign.model_copy(update={"sims": sims}),
        references=references,
        setups=setups,
        groups=groups,
        fs_exe=exe,
        builds=builds,
        row_builds=row_builds,
    )
