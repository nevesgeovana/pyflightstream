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
reads off the import block: this module imports the cases layer and the
script layer downward, the workspace layer sideways, and nothing from
:mod:`pyflightstream.run`.

THE SCRIPT IMPORT IS THE NEWEST OF THOSE AND THE SENTENCE ABOVE IS AN
ENUMERATION, so it is named rather than left to be inferred:
:func:`pyflightstream.script.toggles.resolve_toggle` resolves a preset's
ENABLE/DISABLE gate in the same vocabulary
:class:`pyflightstream.cases.SolverSettings` validates its own toggles
with. `script` is two rows below `workspace` in
:data:`pyflightstream.overview._CORE_LAYERS`, so it is downward. This
paragraph is a rendering source for the architecture overview (AD-02),
which is why an enumeration that has drifted from the import block
matters here more than it would in an ordinary comment.
"""

from __future__ import annotations

import warnings
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePath, PurePosixPath

from pydantic import ValidationError

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import (
    Campaign,
    FluidState,
    ReferenceData,
    SimCase,
    SolverSettings,
)
from pyflightstream.cases.matrix import (
    MatrixError,
    MatrixRow,
    read_matrix,
    refuse_silent_rows_without_default,
    to_campaign,
)
from pyflightstream.cases.workflows import GEOMETRY_VARIABLE
from pyflightstream.script.toggles import resolve_toggle
from pyflightstream.workspace import (
    CampaignWorkspace,
    GroupsArtifact,
    InputArtifactError,
    ReferenceArtifact,
    SetupArtifact,
)

# SIDEWAYS, to the module of this layer that resolves a constraint set
# into a flow state. It needs the reference LENGTH, which is why it is
# here and not on the floor with the atmosphere (PFS-2027.02).
from pyflightstream.workspace.flight_condition import (
    ResolvedCondition,
    resolve_flight_condition,
)

# SIDEWAYS, to the module of this layer that owns the build registry.
# `CampaignWorkspace.resolve_executable` is the path half alone and a
# matrix row now needs the version its build declares beside it, so the
# registry is read once through the function that returns both
# (PFS-2009.05).
from pyflightstream.workspace.inputs import (
    RegisteredBuild,
    is_valid_artifact_id,
    resolve_build,
)

__all__ = [
    "GEOMETRY_VARIABLE",
    "ResolvedMatrix",
    "resolve_matrix",
]

#: The ``VAR_NAMES_VALUES`` key a row names its geometry with.
#:
#: RE-EXPORTED, not defined here. Its home is
#: :data:`pyflightstream.cases.workflows.GEOMETRY_VARIABLE`, beside its
#: sibling cell keys, so the builders that refuse a bad value can
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
#: published column layout is a format and widening it again is a
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
    conditions : dict of str to ResolvedCondition
        The resolved flow state of every row that STATED a flight
        condition, keyed by POL (PFS-2027.02, .04). A row that states
        none has no entry, which is not the same as an empty one.

        It rides here rather than on the case because a case is not a
        record: the density, the temperature, the viscosity, the length
        the Reynolds number was measured against and WHICH branch
        produced the density are what the run record must carry so a
        reader can recompute the resolution rather than trust it.
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
    conditions: dict[str, ResolvedCondition] = field(default_factory=dict)
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
        # THE SAME THREE-WAY READING ITS GEOMETRY SIBLING MAKES, and for
        # the same reason: one arm prescribed a file for every refusal,
        # so a code refused for its SHAPE was told to create a file that
        # could not resolve under any name. The sharpest case is the one
        # 0.8.0 created, a bare pre-0.8.0 code: `003` was answered with
        # "put the artifact at inputs/references/003.toml" while the
        # library's own sentence, chained immediately after it, said the
        # file must be `r003.toml` and named the migration that renames
        # it.
        if not is_valid_artifact_id(code):
            remedy = (
                "the cell is what to fix rather than the library: a code is a file "
                "name stem of letters, digits, dot, underscore or hyphen, beginning "
                "with a letter or a digit, and never a path"
            )
        else:
            remedy = (
                f"put the artifact at inputs/{subdir}/{code}.toml, or fix the matrix "
                "code. An id declares its kind with a leading letter since v0.8.0, so "
                "a code written before that release resolves nothing until it is "
                "migrated; the library's own sentence follows and names the id it "
                "expected"
            )
        raise InputArtifactError(
            f"matrix row POL {pol}: the {column} column names {kind} {code!r}, which "
            f"the workspace input library cannot resolve; {remedy}. {error}",
            # CARRIED ACROSS, as the geometry sibling already does. The
            # class docstring promises a caller can offer the user a
            # choice without parsing the sentence, and this re-raise
            # dropped all three, so a genuine miss with real candidates
            # was indistinguishable from an empty library.
            kind=error.kind,
            artifact_id=error.artifact_id,
            available=error.available,
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
        In two cases, which carry DIFFERENT structured attributes, and
        the difference is stated because a caller that offers the user a
        choice will otherwise offer an empty one.

        A MISS. The library holds no file of that stem. ``kind``,
        ``artifact_id`` and ``available`` are carried across from the
        library's refusal, so the ids that would have resolved are
        readable without parsing the sentence.

        AN AMBIGUOUS STEM, where several staged files share it. The
        library raises that one with no structured attributes at all
        (:func:`pyflightstream.workspace.inputs.resolve_geometry`), so
        ``kind`` and ``artifact_id`` are ``None`` and ``available`` is
        empty here too, and the colliding FILE NAMES appear only in the
        chained sentence. Filling them at the ambiguity site would be
        the better fix and is not this function's to make.

        Both messages name the row's POL and the stem written.
    """
    try:
        return workspace.resolve_geometry(artifact_id)
    except InputArtifactError as error:
        # THREE ARMS, and which one fires is decided by the SUFFIX alone
        # rather than by what happens to be staged. The first version of
        # this branch also required the stem to be in `available`, which
        # served only the user who had already staged the file, and left
        # the commoner order (write the cell, then stage) reading the
        # general arm: with an empty library it still told them to create
        # `inputs/geometries/wing_clean.fsm.fsm` and to keep the cell that
        # was wrong. That is the original defect, in the half that meets
        # more people. The id rule permits a dot, so a written id CARRYING
        # a suffix is diagnosable on its own and nothing else needs to be
        # true for the diagnosis to hold.
        # THE STEM IS COMPUTED PER ARM, and the reason is a platform.
        # `PurePath` is `PureWindowsPath` here and `PurePosixPath` on the
        # runner, and only the first treats a backslash as a separator.
        # One shared `PurePath(...).stem` therefore made the PATH arm
        # print the user's own input back at them on Linux, inside a
        # sentence saying "never a path", and took the ubuntu leg of CI
        # red on the case that guards it. The suffix arm wants the
        # platform-neutral dot rule; the path arm wants both separators.
        stem = PurePath(artifact_id).stem
        path_stem = PurePosixPath(artifact_id.replace("\\", "/")).stem
        available = error.available or ()
        # The library's OWN rule, imported rather than restated, so a
        # cell refused for its SHAPE is never told to stage a file that
        # could not resolve under any name.
        well_formed = is_valid_artifact_id(artifact_id)
        if error.artifact_id is None:
            # THE AMBIGUOUS STEM, AND IT IS TESTED FIRST. An ambiguity
            # refusal proves BY CONSTRUCTION that the written id already
            # IS the shared stem, so nothing any later arm could say
            # about stems or staging can be true on this path. Ordered
            # after the suffix arm for one round, which shadowed every
            # ambiguous id containing a dot: `wing.v2` staged as both
            # `.fsm` and `.stl` was told to write `GEOMETRY: wing` and
            # stage a third file, three sentences before the library's
            # own text said the id matched two files and one should go.
            #
            # The library raises this one with no structured attributes,
            # which is why the discriminator is their absence. That is
            # the weak half: filling them at the raise site is the right
            # fix and would invert this test, so it is registered rather
            # than relied upon, and the guard below goes red if it moves.
            remedy = "the library's own refusal below names the files and the fix"
        elif "/" in artifact_id or "\\" in artifact_id:
            # A PATH, not an id. `_check_id` refuses the shape, and its
            # refusal is indistinguishable from a miss into an empty
            # library, so without this arm the general one told the user
            # to stage a file whose NAME contains separators, which
            # cannot be created and which the chained sentence
            # immediately contradicts.
            #
            # Both separators are named explicitly rather than asking
            # PurePath, which is PureWindowsPath here and PurePosixPath
            # in CI: a cell carrying a backslash would otherwise be
            # diagnosed on one platform and not the other, and a matrix
            # is a file that travels.
            remedy = (
                f"the id is the stem of a file directly under inputs/geometries/ and "
                f"never a path, so write '{GEOMETRY_VARIABLE}: {path_stem}' and stage "
                "the file directly under that directory rather than in a subdirectory "
                "of it"
            )
        elif not well_formed:
            # REFUSED ON ITS SHAPE, which the library's own sentence
            # explains. Prescribing a file to stage would be wrong: no
            # file of that name can resolve under any extension, so the
            # cell is the only thing to change.
            remedy = (
                "the cell is what to fix rather than the library: an id is a file "
                "name stem of letters, digits, dot, underscore or hyphen, beginning "
                "with a letter or a digit"
            )
        elif PurePath(artifact_id).suffix and (not available or stem in available):
            # A FILE NAME, and the library CORROBORATES that reading:
            # either it holds a file under the stem, or it holds nothing
            # at all and no other reading is available.
            settled = (
                f"A file is already staged under the stem {stem!r}"
                if stem in available
                else f"Then stage the file as inputs/geometries/{stem} plus its extension"
            )
            remedy = (
                f"the id is the file name STEM and not the file name, so write "
                f"'{GEOMETRY_VARIABLE}: {stem}'. {settled}"
            )
        elif PurePath(artifact_id).suffix:
            # A DOT, AND NOTHING CORROBORATES EITHER READING, so both are
            # given rather than one guessed. A dot is legal INSIDE an id,
            # so `blade.v2` is as likely a version-tagged stem as a file
            # name, and the arm above used to answer it by truncating a
            # correct version tag while the listing below named the id
            # that would have resolved. Saying both is the only sentence
            # that is true whichever the author meant.
            remedy = (
                f"{artifact_id!r} reads two ways and neither resolves: as a FILE NAME "
                f"its id would be the stem {stem!r}, and nothing is staged under that; "
                "as an id in its own right, a dot being legal inside one, nothing is "
                "staged under it either. The ids that would have resolved follow"
            )
        else:
            remedy = (
                f"stage a file whose name is '{artifact_id}' plus its extension under "
                f"inputs/geometries/, or fix the matrix cell. A workflow opens a saved "
                "simulation, so stage a .fsm; a recipe of your own receives whatever "
                "the library holds"
            )
        raise InputArtifactError(
            f"matrix row POL {pol}: the {GEOMETRY_VARIABLE} variable names geometry "
            f"{artifact_id!r}, which the workspace input library cannot resolve; "
            f"{remedy}. {error}",
            kind=error.kind,
            artifact_id=error.artifact_id,
            available=error.available,
        ) from error


#: Preset spellings that name a :class:`SolverSettings` field under a
#: different word, and the field they name.
#:
#: These are the SOLVER's own key names, which is what a preset
#: transcribed from a working FlightStream session carries. The library
#: field names follow the emitter's keyword arguments instead, so the
#: two vocabularies genuinely differ and neither is the wrong one. The
#: alias table is where they meet, and it is a table rather than a
#: rename so the file a user already has keeps working.
_PRESET_ALIASES = {
    "NITER": "iterations",
    "boundary_layer_type": "boundary_layer",
    "max_parallel_threads": "max_threads",
    "set_solver_model": "solver_model",
    "proximity_avoidance": "wall_collision_avoidance",
    "solver_minimum_cp": "minimum_cp",
    "induced_wake_velocity": "mesh_induced_wake_velocity",
    "unsteady_pressure_kutta": "unsteady_pressure_and_kutta",
    "additional_wake_relaxation_iteration": "additional_wake_relaxation",
    "reynolds_averaged_drag_forces": "reynolds_averaged_drag",
    "unsteady_N_revolutions_wake": "wake_termination_revolutions",
}

#: Preset keys that are RECORDED and deliberately emit nothing, each
#: with the reason, which is printed when a reader asks why.
#:
#: This set is the difference between "we read your file" and "we read
#: the part of your file we happened to have a field for". A key here
#: is a decision; a key in neither this set nor the alias table nor the
#: model is a REFUSAL, because silently dropping a solver setting is how
#: a run answers a question nobody asked.
_PRESET_RECORDED_ONLY = {
    "solver": (
        "the run TYPE, which the matrix WORKFLOW column names: a preset shared by "
        "several rows cannot decide whether one of them is steady"
    ),
    "motion": ("the motion type, which the workflow creates from the row's own rotor keys"),
    "mesh_order_list": (
        "boundary ORDER of one mesh, which is a property of the geometry a row opens "
        "and not of a preset several geometries share"
    ),
    "symmetry_type": (
        "symmetry describes what was MESHED, so it belongs to the row's geometry and "
        "is stated in the row's SYMMETRY key; a preset value would silently overrule "
        "the mesh it knows nothing about"
    ),
    "symmetry_loads": (
        "whether the reported loads are the modelled slice's or the whole body's. It "
        "has an emitter (SET_ANALYSIS_SYMMETRY_LOADS) and is still recorded-only, "
        "deliberately: applying it would multiply or divide every published "
        "coefficient of a periodic or mirrored case by the copy count, so it is a "
        "decision to make with a measurement in hand rather than a key to honour "
        "silently"
    ),
    "unsteady_delta_theta_deg": (
        "superseded by the row's DELTA_THETA, which is where the azimuthal step is "
        "stated now that the clock is derived from it"
    ),
    "unsteady_N_revolutions": ("superseded by the row's REVOLUTIONS, for the same reason"),
    "set_base_region_trailing_edges": (
        "a separation model that selects boundaries, and a preset carries no boundary "
        "selection; state it in a recipe"
    ),
    "significant_digits": "no emitter in this package",
    "slipstream_wake_stabilization": "no emitter in this package",
    "wake_layers": "no emitter in this package",
}

#: Reserved preset key by which a FILE declares its own recorded-only
#: keys, as a list of names.
#:
#: The library table above covers the keys the library knows about, and
#: it cannot cover a setting from a solver build or a workflow nobody
#: here has seen. Without this, such a key would be refused with no way
#: forward except editing the library, so the decision is handed to the
#: person who wrote the file: name the key here and it is kept, emits
#: nothing, and says so. What it is NOT is a way to be quiet about it:
#: a declared key still warns on every resolve, because the whole point
#: is that the author knows their setting is not reaching the solver.
_PRESET_RECORDED_ONLY_KEY = "recorded_only"


def _resolve_stabilization(settings: Mapping[str, object], set_code: str) -> float | None:
    """Resolve the two-key stabilization pair into one strength, or None.

    A preset gates the strength with its own ENABLE/DISABLE key, and the
    emitter takes a single number. Disabled therefore means ABSENT and
    not zero: zero is a stabilization of zero strength that is still
    switched on, and emitting it would be a different run from the one
    the file describes.
    """
    if "stabilization" not in settings and "stabilization_strength" not in settings:
        return None
    gate = settings.get("stabilization")
    enabled = True if gate is None else resolve_toggle(gate, context="stabilization")
    if not enabled:
        return None
    strength = settings.get("stabilization_strength")
    if strength is None:
        raise InputArtifactError(
            f"setup preset {set_code!r} enables stabilization and states no "
            "stabilization_strength, so there is no number to emit. Add the strength, "
            "or disable it."
        )
    # NARROWED RATHER THAN COERCED. A TOML value arrives as `object`, and
    # `float(object)` is both untypeable and a worse refusal: a string
    # would raise a bare ValueError naming neither the preset nor the
    # key. A bool is excluded on its own line because it is an int in
    # Python, so `True` would silently become a stabilization of 1.0.
    if isinstance(strength, bool) or not isinstance(strength, (int, float)):
        raise InputArtifactError(
            f"setup preset {set_code!r} states stabilization_strength as {strength!r}, "
            "and a stabilization strength is a number."
        )
    return float(strength)


def _solver_from_setup(setup: SetupArtifact, set_code: str) -> SolverSettings:
    """Map one preset onto the case solver settings, refusing what it cannot.

    Three outcomes per key, and the third is the change. A key that
    names a :class:`~pyflightstream.cases.SolverSettings` field, or an
    alias of one, APPLIES. A key declared recorded-only is kept in the
    artifact and emits nothing, on the stated ground written beside it.
    Anything else is REFUSED, naming the key and what is available.

    UNTIL THIS RELEASE THE THIRD CASE WAS A WARNING AND A SILENT DROP,
    and that is the defect this closes. A preset asking for
    ``SUBSONIC_PRANDTL_GLAUERT`` ran INCOMPRESSIBLE and a preset asking
    for a turbulent boundary layer ran the solver's default. Each of
    those is a run that converges, exports and publishes numbers against
    a physics nobody selected. A refusal costs an edit; a silent drop
    costs a result.

    ``NITER`` WAS IN THE SAME POSITION AND IS DELIBERATELY NOT OFFERED
    as a third instance: the campaign that surfaced this states 500 and
    the model default is 500, so both of its runs emitted the same line
    and it cannot be demonstrated from them. An earlier version of this
    docstring listed it beside the other two, which made an unmeasured
    instance read like a measured one.
    """
    settings = dict(setup.settings)
    declared = settings.pop(_PRESET_RECORDED_ONLY_KEY, None)
    if declared is None:
        declared_names: set[str] = set()
    elif isinstance(declared, (list, tuple)) and all(isinstance(name, str) for name in declared):
        declared_names = {str(name) for name in declared}
    else:
        raise InputArtifactError(
            f"setup preset {set_code!r} states {_PRESET_RECORDED_ONLY_KEY} as "
            f"{declared!r}, and it is a list of key NAMES, for example "
            f"{_PRESET_RECORDED_ONLY_KEY} = ['my_setting']."
        )
    # THE PAIR IS CONSUMED BEFORE THE LOOP, so neither half reaches the
    # recorded-only report. An earlier version left them in it, and the
    # warning then told an author that a stabilization they had switched
    # ON emitted nothing, while the strength was in fact reaching the
    # script. A message that names the wrong outcome is worse than none.
    stabilization = _resolve_stabilization(settings, set_code)
    gated = "stabilization" in settings or "stabilization_strength" in settings
    settings.pop("stabilization", None)
    settings.pop("stabilization_strength", None)
    known = set(SolverSettings.model_fields)
    matched: dict[str, object] = {}
    refused: list[str] = []
    recorded: list[str] = []
    for key, value in settings.items():
        field = _PRESET_ALIASES.get(key, key)
        if field in known:
            matched[field] = value
        elif key in _PRESET_RECORDED_ONLY or key in declared_names:
            recorded.append(key)
        else:
            refused.append(key)
    if refused:
        # THE CONSUMED KEYS BELONG IN THE LIST. `stabilization`,
        # `stabilization_strength` and the reserved `recorded_only` are
        # all accepted and are all taken out of `settings` before this
        # loop, so the first version of this message refused
        # `stabilisation` with a list of "keys that apply" that did not
        # contain the word its author meant, which is the one case where
        # the list is the whole value of the refusal.
        available = sorted(
            known
            | set(_PRESET_ALIASES)
            | {"stabilization", "stabilization_strength", _PRESET_RECORDED_ONLY_KEY}
        )
        raise InputArtifactError(
            f"setup preset {set_code!r} states key(s) {', '.join(sorted(refused))}, "
            "which name no solver setting this package can emit and are not declared "
            "as recorded-only. A key that reaches no script would change nothing about "
            "the run while reading as though it had, so it is refused rather than "
            f"dropped. The keys that apply are: {', '.join(available)}. The keys this "
            "package already records without emitting are: "
            f"{', '.join(sorted(_PRESET_RECORDED_ONLY))}. If the setting really is one "
            "this package cannot emit and you want it kept in the artifact anyway, "
            f"name it in {_PRESET_RECORDED_ONLY_KEY} in the preset file."
        )
    if recorded:
        # THE WARNING SURVIVES, and it is the useful half now that the
        # silent drop is gone: the keys it lists are exactly the ones an
        # author might still believe reached the solver.
        reasons = ", ".join(
            f"{key} ({_PRESET_RECORDED_ONLY.get(key, 'declared recorded-only by this preset')})"
            for key in sorted(recorded)
        )
        warnings.warn(
            f"setup preset {set_code!r}: key(s) {reasons} are RECORDED in the artifact "
            "and emit nothing, so the solver takes its own default for each. Every "
            "other key of this preset reaches the script.",
            PyflightstreamWarning,
            stacklevel=2,
        )
    if stabilization is not None:
        matched["solver_stabilization"] = stabilization
    elif gated:
        warnings.warn(
            f"setup preset {set_code!r}: stabilization is DISABLED, so no "
            "stabilization strength is emitted and the solver takes its own default. "
            "A disabled stabilization is an absent one and not a strength of zero, "
            "which would still be switched on.",
            PyflightstreamWarning,
            stacklevel=2,
        )
    try:
        # `model_validate` AND NOT `SolverSettings(**matched)`. The dict is
        # `dict[str, object]` by construction, because a preset table is
        # untyped until it is validated, and unpacking it as keywords
        # typechecks `object` against every field: the checker could not
        # see that any preset value had the right type, on the one call
        # whose whole purpose is that preset values reach solver fields.
        # Passing the mapping is the same validation and it is typed.
        return SolverSettings.model_validate(matched)
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
    conditions: dict[str, ResolvedCondition] = {}
    for case, row in zip(campaign.sims, rows, strict=True):
        reference = references[row.ref_code]
        update: dict[str, object] = {
            # THE DIAMETER TRAVELS WITH THE OTHER TWO LENGTHS. It is a
            # reference length rather than propeller metadata, and it is
            # the one an advance ratio needs: a row stating
            # ADVANCE_RATIO resolves n = V / (J D), so a diameter that
            # stopped at the artifact would leave the ratio naming no
            # rotor speed. None stays None, which is what keeps a
            # configuration with no propeller resolving exactly as it did.
            "reference": ReferenceData(
                area=reference.area_m2,
                length=reference.chord_m,
                propeller_diameter=reference.propeller_diameter_m,
            ),
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
        # PFS-2027.02 and .04. THE POSITION IS LOAD-BEARING and it is not
        # a comment asking for an ordering: the reference is bound at the
        # top of this loop body and reaches the case only through the
        # `model_copy` below, so `case.reference` is still None here. The
        # resolver therefore takes the length from the LOCAL binding, and
        # a resolver moved above that binding would silently resolve
        # every Reynolds constraint against no length at all -- which is
        # the failure `.04` exists to prevent, and which
        # `tests/test_flight_condition_resolution.py` fails on rather
        # than describing.
        if row.flight_condition:
            resolved = resolve_flight_condition(
                row.flight_condition,
                pol=row.pol,
                reference_length_m=reference.chord_m,
            )
            conditions[row.pol] = resolved
            # The three the case already has fields for. The rest of the
            # state -- density, temperature, viscosity, the length it was
            # measured against and WHICH branch produced the density --
            # rides on `conditions` rather than being flattened onto the
            # case, because the run record is what has to carry it and a
            # case is not a record.
            update["mach"] = resolved.mach
            update["velocity"] = resolved.velocity_m_per_s
            update["reynolds"] = resolved.reynolds
            # The whole resolved state, so a BUILDER can emit it. The
            # resolver lives here and a builder cannot import this layer,
            # so the value travels rather than the computation
            # (PFS-2025.02.05, PFS-2027.05).
            update["fluid"] = FluidState(
                velocity_m_per_s=resolved.velocity_m_per_s,
                density_kg_m3=resolved.density_kg_m3,
                pressure_pa=resolved.pressure_pa,
                temperature_k=resolved.temperature_k,
                viscosity_pa_s=resolved.viscosity_pa_s,
                sonic_velocity_m_per_s=resolved.sonic_velocity_m_per_s,
                heat_capacity_ratio=resolved.heat_capacity_ratio,
                source=resolved.density_source,
                reference_length_m=resolved.reference_length_m,
            )
        sims.append(case.model_copy(update=update))
    return ResolvedMatrix(
        campaign=campaign.model_copy(update={"sims": sims}),
        conditions=conditions,
        references=references,
        setups=setups,
        groups=groups,
        fs_exe=exe,
        builds=builds,
        row_builds=row_builds,
    )
