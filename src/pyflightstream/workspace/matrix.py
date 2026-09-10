"""Binding a run matrix to the workspace input library.

Pipeline role: the workspace-layer half of the run matrix. The reader
and the converter stay in :mod:`pyflightstream.cases.matrix`, which
parses the verified 15-column file and maps it onto the canonical
``campaign.toml`` model without needing anything above the cases layer.
What lives HERE is the step that needs the layer above: resolving the
matrix's reference columns against the input library under ``inputs/``.

REF resolves to reference data (applied to each case's ``reference``),
SET to a solver preset (its runtime subset applied to each case's
``solver``), PPROC to the post-processing artifact (bound onto the case),
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
from pathlib import Path

from pydantic import ValidationError

from pyflightstream._errors import PyflightstreamDeprecationWarning, PyflightstreamWarning
from pyflightstream._fsm import MeshReadError, boundary_names
from pyflightstream.cases import (
    Campaign,
    FluidState,
    RawCommand,
    ReferenceData,
    SimCase,
    SolverSettings,
)
from pyflightstream.cases.matrix import (
    DEFAULT_VERSION_OPTION,
    LEGACY_WORKFLOW,
    RAW_BEFORE_KEY,
    RAW_COMMAND_KEY,
    RAW_FILE_KEY,
    RAW_VARIABLE,
    MatrixError,
    MatrixRow,
    read_matrix,
    refuse_silent_rows_without_default,
    to_campaign,
)
from pyflightstream.cases.workflows import (
    GEOMETRY_VARIABLE,
    IGNORE_MISSING_FAMILIES_VARIABLE,
    ROTOR_ORIGIN_POINT_KEY,
)
from pyflightstream.script.toggles import resolve_toggle
from pyflightstream.workspace import (
    CampaignWorkspace,
    InputArtifactError,
    PprocArtifact,
    ReferenceArtifact,
    SetupArtifact,
)

# SIDEWAYS, to the module of this layer that resolves a constraint set
# into a flow state. It needs the reference LENGTH, which is why it is
# here and not on the floor with the atmosphere (PFS-2027.02).
from pyflightstream.workspace.flight_condition import (
    PINNED_KEYS,
    ResolvedCondition,
    canonical_condition_defaults,
    resolve_flight_condition,
)

# SIDEWAYS, to the module of this layer that owns the build registry.
# `CampaignWorkspace.resolve_executable` is the path half alone and a
# matrix row now needs the version its build declares beside it, so the
# registry is read once through the function that returns both
# (PFS-2009.05).
from pyflightstream.workspace.inputs import (
    RegisteredBuild,
    inventory_sidecar,
    is_valid_artifact_id,
    read_inventory,
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
    pprocs : dict of str to PprocArtifact
        Resolved post-processing artifacts, keyed by PPROC code; group members
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
    pprocs: dict[str, PprocArtifact] = field(default_factory=dict)
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
    default: str | None,
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
    default: str | None,
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
    # No default is legal when every active row names a build (PFS-2029.01);
    # the silent row that would have needed it was refused by name before
    # this function ran, so the empty fallback answers for no row.
    fallback = (default or "").strip()
    effective = tuple(build if build is not None else fallback for build in named)
    # EVERY effective build is asked, not only the one a single-build
    # matrix used to collapse to: MANUAL names no executable whichever row
    # asks for it, and refusing it here keeps the message the one a caller
    # already knows.
    if any(build.upper() == "MANUAL" for build in effective):
        raise MatrixError(
            "FS_BUILD is MANUAL, the explicit-path mode: pass fs_exe (CLI: --fs-exe), "
            "the explicit override path. MANUAL never reads the build registry, "
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
        "pproc": ("PPROC", "pproc", workspace.resolve_pproc),
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


def _moved_to_the_reference(row: MatrixRow, table: str) -> None:
    """Warn that a setup preset still carries a table the reference now owns.

    FR-59 and FR-72, her decision of 2026-09-10. The warning names the row,
    both artifacts and where the table belongs, because a user meeting it is
    holding a workspace that still plans and has one edit to make. The
    tables are read from the preset until 0.17.0.
    """
    # THE MESSAGE CARRIES NO ROW NUMBER, deliberately. The warning filter
    # dedupes on the message, and the EDIT is one edit per preset: keyed on
    # the POL, a fifty-row campaign citing one unmigrated preset printed
    # fifty warnings for one file, and pointed at a row rather than at the
    # file to change (the interface lens of 2026-09-10).
    warnings.warn(
        f"the setup preset {row.set_code!r} states [{table}], which moved to the "
        f"reference artifact {row.ref_code!r} at 0.15.0: a boundary name and a "
        "coordinate system are properties of the CONFIGURATION, and a preset is per "
        "condition. The reference's entries are the ones every row citing it uses. Move "
        "the table and the warning goes; the preset stops being read for it at 0.17.0.",
        PyflightstreamDeprecationWarning,
        stacklevel=2,
    )


def _aliases_of(reference, setup, row: MatrixRow) -> dict[str, list[str]]:
    """Return a row case's aliases: the reference's, with the preset's deprecated.

    THE COMPARISON FOLDS CASE, and a merge by exact key does not. An alias
    is looked up case folded everywhere else in this package, so a preset
    stating ``Wing`` and a reference stating ``wing`` name ONE word; merged
    by exact key both survive, the preset's is inserted first, and the
    folded lookup then returns the DEPRECATED file's members. The
    interface lens of 2026-09-10 found it, and the frames merge beside
    this one had already got it right.
    """
    if setup.aliases:
        _moved_to_the_reference(row, "aliases")
    taken = {name.casefold() for name in reference.aliases}
    merged = {
        name: list(members)
        for name, members in setup.aliases.items()
        if name.casefold() not in taken
    }
    merged.update({name: list(members) for name, members in reference.aliases.items()})
    return merged


def _frames_of(reference, setup, row: MatrixRow) -> list:
    """Return a row case's custom frames: the reference's, with the preset's deprecated.

    A name declared in both files is the REFERENCE's, and the preset's is
    dropped rather than emitted twice, because two frames of one name are
    what :class:`SetupArtifact` refuses inside one file.
    """
    if setup.frames:
        _moved_to_the_reference(row, "frames")
    taken = {frame.name.strip().upper() for frame in reference.frames}
    kept = [frame for frame in setup.frames if frame.name.strip().upper() not in taken]
    return [*reference.frames, *kept]


def _the_rows_raw_commands(row: MatrixRow, inputs_dir: Path) -> list[RawCommand]:
    """Expand the row's ``RAW`` records into commands, reading any file (FR-67).

    A ``COMMAND`` record is one command, sourced to the word ``matrix``. A
    ``FILE`` record is a text file of the workspace's inputs, and becomes
    ONE COMMAND PER LINE, each sourced to ``<path>:<line number>``: a blank
    line and a line opening with ``#`` are skipped, so a raw file may
    explain itself, and every other line is emitted verbatim in order.

    THE LINE NUMBER IS THE POINT of the source field. A file carrying a
    command this build lacks is refused by the emitter naming THE FILE and
    THE LINE, not the cell that pointed at it, because the cell holds a
    path and the mistake is thirty lines away.
    """
    entries: list[RawCommand] = []
    for record in row.raw:
        before = record[RAW_BEFORE_KEY].strip()
        line = record.get(RAW_COMMAND_KEY)
        if line:
            entries.append(RawCommand(command=line, before=before, source="matrix"))
            continue
        stated = record[RAW_FILE_KEY].strip()
        inputs = inputs_dir.resolve()
        # RESOLVED BEFORE COMPARED, and that ORDER is the whole soundness of
        # the check: `.resolve()` normalises `..` AND follows a link, so a
        # junction placed inside the inputs and pointing out is caught. A
        # lexical comparison defeats `..` and lets the junction through, and
        # the QA lens measured that a lexical mutant survived the whole
        # suite because no case reached the link (2026-09-10).
        path = (inputs_dir / stated).resolve()
        # UNDER THE INPUTS AND NOWHERE ELSE. A relative path that climbs out
        # of the workspace would read a file the run record cannot describe
        # and a second machine does not have.
        if not path.is_relative_to(inputs):
            raise MatrixError(
                f"POL {row.pol}: {RAW_VARIABLE} names the file {stated!r}, which resolves "
                f"outside the workspace's inputs ({inputs_dir}). A raw file is a file of "
                "the workspace, so that the run record names a path a second machine has."
            )
        if not path.is_file():
            raise MatrixError(
                f"POL {row.pol}: {RAW_VARIABLE} names the file {stated!r}, and "
                f"{path} is not a file. A raw file is written under the workspace's "
                "inputs and its path is stated relative to them."
            )
        # THE SOURCE IS THE RESOLVED PATH, NOT THE CELL'S TEXT, and this is
        # the containment check's own stated purpose kept rather than
        # merely claimed. `RAW/EXTRA.TXT`, `raw\\extra.txt`,
        # `raw/../raw/extra.txt` and `raw/extra.txt.` all resolve inside the
        # inputs on this platform and all four were written into the run
        # record verbatim: an upper-cased name that no Linux machine
        # resolves, a Windows separator, a non-canonical path, and a
        # trailing dot the file system strips and the record did not. Each
        # satisfies containment and defeats the reason for it (the QA lens,
        # 2026-09-10). One canonical POSIX-relative spelling, so the record
        # is separator-stable for the same reason the goldens are.
        canonical = path.relative_to(inputs).as_posix()
        try:
            body = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as error:
            # EVERY OTHER REFUSAL ON THIS PATH NAMES THE POL AND THE FILE,
            # and this one reached the user as a bare decode error naming
            # neither. A UTF-16 file saved from a Windows editor is an
            # ordinary artifact. `utf-8-sig` above also eats a byte-order
            # mark, which would otherwise ride into the first command name
            # and produce an emitter refusal about a command the author can
            # see is spelled correctly.
            raise MatrixError(
                f"POL {row.pol}: {RAW_VARIABLE} names the file {stated!r}, and {path} is "
                f"not UTF-8 text ({error}). A raw file is read line by line as text; save "
                "it as UTF-8, which is what every other input of the workspace is."
            ) from error
        for number, raw_line in enumerate(body.splitlines(), start=1):
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            entries.append(
                RawCommand(command=stripped, before=before, source=f"{canonical}:{number}")
            )
    return entries


def _frames_for_row(reference, setup, row: MatrixRow) -> list:
    """Return a row's custom frames, refusing only what the ROW chose (FR-72).

    A LEGACY row is built by its own recipe, which reads no frames, so a
    table it would carry and never emit is refused rather than dropped in
    silence. That was written when the table was the SETUP's, which a row
    chooses by its SET cell.

    THE REFERENCE IS NOT A ROW'S CHOICE. It is per configuration, and
    every row of that configuration cites it, so refusing a legacy row for
    a table the reference declares would let one legacy row block a whole
    study. The reference's frames are DROPPED for that row, with a warning
    naming it, so the record cannot claim what the script never took; the
    setup's are refused exactly as before.

    Whether that is the right division is the author's question of
    2026-09-10 (the interface lens, API1-20): refusing is the other
    defensible answer and costs a study one edit per legacy row.
    """
    if row.workflow == LEGACY_WORKFLOW and reference.frames:
        warnings.warn(
            f"POL {row.pol} writes LEGACY and its reference {row.ref_code!r} declares "
            f"{len(reference.frames)} custom frame(s). A LEGACY row is built by its own "
            "recipe, which reads no frames, so they are left out of this row rather than "
            "carried into a record the script would not match. Every row of this "
            "configuration that names a run type gets them.",
            PyflightstreamWarning,
            stacklevel=2,
        )
        return _not_on_a_legacy_row(row, list(setup.frames), "frames", f"setup {row.set_code!r}")
    return _not_on_a_legacy_row(
        row,
        _frames_of(reference, setup, row),
        "frames",
        _frame_sources(reference, setup, row),
    )


def _frame_sources(reference, setup, row: MatrixRow) -> str:
    """Name the file or files a row's custom frames came from, for a refusal."""
    parts = []
    if reference.frames:
        parts.append(f"reference {row.ref_code!r}")
    if setup.frames:
        parts.append(f"setup {row.set_code!r}")
    return " and ".join(parts)


def _not_on_a_legacy_row(row: MatrixRow, entries: list, table: str, sources: str = "") -> list:
    """Refuse a setup table a LEGACY row's recipe would drop in silence (the QA lens of REL-0140).

    A LEGACY row is built by its own recipe, which is the reader of its
    keys and reads no frames and no raw commands; the case would carry
    them and the record would claim them while the script never took
    them, which is the silence the ROTATE refusal of PFS-2034.03 ends for
    the row's own key.
    """
    if entries and row.workflow == LEGACY_WORKFLOW:
        # THE MESSAGE NAMES THE FILE THE ENTRIES CAME FROM, and it used to
        # name the preset always. Since 0.15.0 the frames may come from the
        # REFERENCE, so the old sentence could name a preset that states
        # nothing and prescribe an edit that changes nothing (the interface
        # lens of 2026-09-10). The caller knows which file contributed and
        # says so in `sources`.
        sources = sources or f"setup {row.set_code!r}"
        raise MatrixError(
            f"POL {row.pol} writes LEGACY and takes a [[{table}]] table from {sources}; a "
            f"LEGACY row is built by its own recipe, which reads no {table} table, so the "
            "entries would reach no script while the record claimed them. Name a run type "
            "in the WORKFLOW column, or take the table out of the file named here."
        )
    return list(entries)


def _bind_motion(
    workspace: CampaignWorkspace,
    record: Mapping[str, str],
    pol: str,
    *,
    where: str = "a MOTIONS record",
) -> dict[str, str]:
    """Bind one motion record: a ROTOR_ORIGIN naming a point becomes that point's coordinates.

    PFS-2029.11.02. Three numbers pass through as written; a name is
    resolved against ``inputs/reference_points.toml`` and must be an
    engine point, and the record keeps the name beside the coordinates
    as ``ROTOR_ORIGIN_POINT`` so the run record says which point it was.
    Since 0.13.0 the flat rotor row's own ``ROTOR_ORIGIN`` is bound through
    the same function (PFS-2031.12), ``where`` naming which of the two the
    refusal is about.
    """
    bound = dict(record)
    origin = bound.get("ROTOR_ORIGIN")
    if origin is None or _is_three_numbers(origin):
        return bound
    try:
        point = workspace.engine_point(origin)
    except InputArtifactError as error:
        raise InputArtifactError(
            f"matrix row POL {pol}: {where} states ROTOR_ORIGIN: {origin}, which "
            f"the workspace cannot turn a rotor about. {error}",
            kind=error.kind,
            artifact_id=error.artifact_id,
            available=error.available,
        ) from error
    bound["ROTOR_ORIGIN"] = f"{point.x_m},{point.y_m},{point.z_m}"
    bound[ROTOR_ORIGIN_POINT_KEY] = origin
    return bound


def _is_three_numbers(text: str) -> bool:
    parts = [token.strip() for token in text.split(",")]
    if len(parts) != 3:
        return False
    try:
        [float(part) for part in parts]
    except ValueError:
        return False
    return True


def _inventory_of(geometry: Path) -> tuple[tuple[str, ...] | None, str | None]:
    """Return the sidecar's boundary order, if one sits beside the geometry, and the source.

    PFS-2029.06.03. The sidecar is read here, at binding, so a malformed
    one is refused with the row before any seat is spent; whether it
    AGREES with the file is the builder's check at ``OPEN``, because that
    is where the file's own mesh block is read for the staged copy.
    """
    sidecar = inventory_sidecar(geometry)
    if sidecar.is_file():
        return read_inventory(sidecar), "sidecar"
    try:
        declared = boundary_names(geometry)
    except MeshReadError:
        return None, None
    return None, ("mesh_block" if declared else None)


def _resolve_geometry(workspace: CampaignWorkspace, name: str, pol: str) -> Path:
    """Resolve one ``GEOMETRY`` cell, naming the row.

    The sibling of :func:`_resolve_code` for the one library kind a matrix
    names from its free cell rather than from a column. Since 0.11.0 the
    cell carries the FILE NAME with its extension (PFS-2029.09), and the
    library's own refusal already says which file to write or to stage;
    this function adds the row so a reader finds the cell.
    """
    try:
        return workspace.resolve_geometry(name)
    except InputArtifactError as error:
        raise InputArtifactError(
            f"matrix row POL {pol}: the {GEOMETRY_VARIABLE} variable names geometry "
            f"{name!r}, which the workspace input library cannot resolve. {error}",
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
    # The settings her own scripts state and 0.10.1 did not emit (FR-54).
    "reference_velocity_mps": "reference_velocity_m_per_s",
    "vorticity_drag_boundaries": "vorticity_drag_families",
    "set_vorticity_drag_boundaries": "vorticity_drag_families",
}

#: Preset keys that are RECORDED and deliberately emit nothing, each
#: with the reason, which is printed when a reader asks why.
#:
#: This set is the difference between "we read your file" and "we read
#: the part of your file we happened to have a field for". A key here
#: is a decision; a key in neither this set nor the alias table nor the
#: model is a REFUSAL, because silently dropping a solver setting is how
#: a run answers a question nobody asked.
#: The tables a setup artifact is refused for naming, because they are
#: post-processing and the pproc artifact is their home (PFS-2029.16).
_POST_PROCESSING_KEYS = ("sections", "plots", "probes", "products", "exports", "groups")

_PRESET_RECORDED_ONLY = {
    "solver": (
        "the run TYPE, which the matrix WORKFLOW column names: a preset shared by "
        "several rows cannot decide whether one of them is steady"
    ),
    "motion": ("the motion type, which the workflow creates from the row's own rotor keys"),
    "symmetry_type": (
        "symmetry describes what was MESHED, so it belongs to the row's geometry and "
        "is stated in the row's SYMMETRY key; a preset value would silently overrule "
        "the mesh it knows nothing about"
    ),
    # `symmetry_loads` LEFT THIS TABLE on 2026-09-02, her decision (PFS-2028.05)
    # with the measurement in hand: the 0.10.1 reproduction of her isolated
    # rotor reported loads six times hers because her preset stated the
    # symmetry loads off and nothing was emitted. A STATED key now reaches
    # SET_ANALYSIS_SYMMETRY_LOADS as stated; an absent key still emits nothing.
    "unsteady_delta_theta_deg": (
        "superseded by the row's DELTA_THETA, which is where the azimuthal step is "
        "stated now that the clock is derived from it"
    ),
    "unsteady_N_revolutions": ("superseded by the row's REVOLUTIONS, for the same reason"),
    "set_base_region_trailing_edges": (
        "a separation model that selects boundaries, and a preset carries no boundary "
        "selection; state it in a recipe"
    ),
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

#: The table a setup carries for the FLIGHT CONDITION rather than for the
#: solver (PFS-2030.08). It is not a solver setting and is consumed before
#: the key loop that would otherwise refuse it as one; its contents are
#: judged by the resolver, which owns the pin vocabulary.
_FLIGHT_CONDITION_TABLE = "flight_condition"


def condition_defaults_origin(set_code: str) -> str:
    """Name the setup a defaults table came from, id AND path.

    One home, because it is written in a refusal the user acts on and
    recorded on the resolved state, and an interface review found the two
    disagreeing by two quote characters. THE PATH IS THE POINT: an id
    tells a reader WHICH artifact is wrong and not which of a dozen files
    under ``inputs/setups/`` to open.
    """
    return f"setup {set_code!r} (inputs/setups/{set_code}.toml)"


def _condition_defaults(setup: SetupArtifact, set_code: str) -> dict[str, float]:
    """Read a setup's flight-condition defaults, refusing what is not a number.

    WHAT THIS FUNCTION DECIDES AND WHAT IT DOES NOT. It decides the
    SHAPE: that the key names a table and that every value in it is a
    finite number. It does NOT decide which keys may appear, because that
    is the pin vocabulary and it lives with the resolver that owns it; it
    CALLS that rule rather than restating it
    (:func:`~pyflightstream.workspace.flight_condition.canonical_condition_defaults`),
    so a key added to the pins is accepted here the day it is added
    there, with no second list to move.

    IT CALLS IT HERE, once per setup, and that placement is the finding
    of an architecture review on 2026-09-04 rather than a preference:
    while the vocabulary was judged only inside the resolver, it ran once
    per ROW THAT STATED A CONDITION, so one file was legal or illegal
    depending on other rows' cells.

    Two exception classes leave this function, and the split is the one
    the rest of the package makes: a malformed FILE is an
    ``InputArtifactError``, and a well-formed file stating the wrong
    CONSTANT is a ``FlightConditionError`` from the rule above.

    A bool is excluded on its own line because it is an int in Python, so
    ``MUPas = true`` would otherwise pin a viscosity of 1.0.
    """
    table = setup.settings.get(_FLIGHT_CONDITION_TABLE)
    if table is None:
        return {}
    if not isinstance(table, dict):
        raise InputArtifactError(
            f"setup preset {set_code!r} states {_FLIGHT_CONDITION_TABLE} as {table!r}, "
            f"and it is a TABLE of flight-condition pins, for example "
            f"[{_FLIGHT_CONDITION_TABLE}] with MUPas = 1.789e-5 under it."
        )
    defaults: dict[str, float] = {}
    for key, value in table.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InputArtifactError(
                f"setup preset {set_code!r} states {_FLIGHT_CONDITION_TABLE}.{key} as "
                f"{value!r}, and a flight-condition pin is a number."
            )
        number = float(value)
        if number != number or number in (float("inf"), float("-inf")):
            raise InputArtifactError(
                f"setup preset {set_code!r} states {_FLIGHT_CONDITION_TABLE}.{key} as "
                f"{value!r}, which is not a finite number. A fluid constant cannot be "
                "stated as a NaN or an infinity, and one would otherwise reach the "
                "emitted script unrefused."
            )
        defaults[key] = number
    return canonical_condition_defaults(defaults, condition_defaults_origin(set_code))


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
    # THE FLIGHT-CONDITION TABLE IS CONSUMED HERE, for the same reason
    # the pair below it is: it is accepted, it is not a solver setting,
    # and a key left in `settings` reaches the loop that refuses anything
    # naming no setting this package can emit. `_condition_defaults`
    # reads it from the artifact, so nothing is lost by dropping it.
    # Its CONTENTS are read by `_condition_defaults` above, and the two
    # are load-bearing on each other through this constant alone: delete
    # this pop and a valid file is refused, delete that read and valid
    # pins are silently ignored.
    settings.pop(_FLIGHT_CONDITION_TABLE, None)
    stabilization = _resolve_stabilization(settings, set_code)
    gated = "stabilization" in settings or "stabilization_strength" in settings
    settings.pop("stabilization", None)
    settings.pop("stabilization_strength", None)
    known = set(SolverSettings.model_fields)
    matched: dict[str, object] = {}
    if "mesh_order_list" in settings:
        # PFS-2029.06.01. Until 0.11.0 the key was recorded-only: kept,
        # warned about, never emitted. Recorded-only was the wrong answer
        # for the one key whose value is CHECKABLE against the file it
        # describes, because a preset several geometries share cannot
        # state the order of any one of them, and a wrong order that is
        # merely warned about is read as documentation by the next reader.
        raise InputArtifactError(
            f"setup preset {set_code!r} states mesh_order_list, which is the boundary "
            "order of one mesh and belongs beside that mesh, not in a preset several "
            "geometries share. Write it from the file itself: `pyfs-matrix inventory "
            "inputs/geometries/<file>` reads the mesh block and writes "
            "<stem>.boundaries.toml beside the geometry, and the run refuses a sidecar "
            "that disagrees with the file (PFS-2029.06). Remove the key from the setup."
        )
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
    near_miss = sorted(
        key
        for key in refused
        if key.strip().lower().replace("-", "_").replace(" ", "_").rstrip("s")
        == _FLIGHT_CONDITION_TABLE.rstrip("s")
    )
    if near_miss:
        # A MISSPELLING OF THE TABLE MUST NOT BE ANSWERED BY THE GENERIC
        # REFUSAL, and an interface review found why on 2026-09-04. That
        # message calls the key a solver setting, which this table is
        # explicitly not, and its closing sentence offers `recorded_only`
        # as the remedy -- which would make the table legal, silent and
        # INERT, four pinned fluid constants reaching no script, on a
        # surface whose whole premise is that a silent drop costs a
        # result.
        raise InputArtifactError(
            f"setup preset {set_code!r} states key(s) {', '.join(near_miss)}, which "
            f"look like the flight-condition table misspelled. That table is spelled "
            f"exactly [{_FLIGHT_CONDITION_TABLE}] and holds the fluid pins "
            f"({', '.join(PINNED_KEYS)}) every row naming this setup inherits. Rename "
            f"it. Do NOT name it in {_PRESET_RECORDED_ONLY_KEY}: that would make it "
            "legal, silent and inert, and the constants under it would reach no "
            "script."
        )
    post_processing = sorted(set(refused) & set(_POST_PROCESSING_KEYS))
    if post_processing:
        # PFS-2029.16: a setup artifact carries solver settings only. Her
        # SET files carried a second table of post-processing, and that
        # table's home is the pproc artifact the row's PPROC cell names.
        raise InputArtifactError(
            f"setup preset {set_code!r} states key(s) {', '.join(post_processing)}, "
            "which name post-processing, not a solver setting. Post-processing does "
            "not belong in a setup artifact: sections, plots, probes, products, "
            "exports and groups live in the pproc artifact the row's PPROC cell names "
            "(inputs/pproc/p001.toml, PFS-2029.07). Move the table there."
        )
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
            | {
                "stabilization",
                "stabilization_strength",
                _PRESET_RECORDED_ONLY_KEY,
                _FLIGHT_CONDITION_TABLE,
            }
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


def _refuse_groups_named_by_a_word(pproc: PprocArtifact, code: str, pol: str) -> None:
    """Refuse a pproc artifact whose polar groups are keyed by a word.

    PFS-2032.03. The polar table written per group carries the group
    NUMBER in its name (``<polar>_M<mach>_g<number>.csv``, her
    convention, :func:`pyflightstream.post.products.polar_file_name`), so
    a group named ``wing`` reached ``int(group)`` in the products stage
    and stopped the whole stage with a bare ValueError, outside the skip
    mechanism and after the seat was spent; measured planning READY on
    2026-09-08. Refused HERE, at binding, and not at the artifact's shape:
    a group's members are also what :func:`pyflightstream.workspace.expand_group`
    numbers by the group's own name (``Blade`` to ``Blade1``, ``Blade2``),
    which is a recipe's tool and reads no polar, so the shape stays free
    and the campaign path, where the number is the table's name, is what
    refuses. An artifact that writes no polar tables is left alone.
    """
    if not pproc.products.polars:
        return
    words = sorted(name for name in pproc.groups if not str(name).strip().isdigit())
    if not words:
        return
    raise InputArtifactError(
        f"matrix row POL {pol}: the PPROC column names pproc {code!r} "
        f"(inputs/pproc/{code}.toml), whose [groups] table is keyed by "
        f"{', '.join(repr(name) for name in words)}. A group is keyed by its NUMBER, "
        "which is the entry the polar table written per group carries in its name "
        "(<polar>_M<mach>_g<number>.csv), and the families it sums are the list: write "
        '"1" = ["Wing"] rather than wing = ["Wing"]. An artifact whose groups are not '
        "for polar tables says so with products.polars = false.",
        kind="pproc",
        artifact_id=code,
    )


def _refuse_a_pol_stated_by_a_sibling(
    path: str | Path, workspace: CampaignWorkspace, rows: list[MatrixRow]
) -> None:
    """Refuse a POL that another matrix of the same workspace root also states.

    PFS-2031.04. Several matrices may share one workspace, each keeping
    its own plan, sweep table and products under ``post/<stem>/``, and
    ``runs.json`` stays the one manifest of all of them. A POL names the
    simulation folder ``sims/sim_<POL>`` and the run ids of that
    manifest, so two matrices stating one POL would write into one
    folder and a resume of either would find the other's points already
    recorded. The siblings are every ``*.fs`` beside the matrix in the
    workspace root, read the way the matrix itself is; a sibling that
    cannot be read is named as the problem rather than skipped, because
    a check that skips what it cannot read accepts the collision it
    exists to refuse.
    """
    matrix = Path(path).resolve()
    root = Path(workspace.root).resolve()
    if matrix.parent != root:
        return
    mine = {row.pol: row.row_number for row in rows}
    for sibling in sorted(root.glob("*.fs")):
        if sibling.resolve() == matrix:
            continue
        try:
            theirs = read_matrix(sibling)
        except MatrixError as error:
            raise MatrixError(
                f"{sibling.name} shares this workspace with {matrix.name} and could not be "
                f"read: {error}. Every matrix of one workspace is read at plan time, because "
                f"a POL stated by two of them would share one simulation folder."
            ) from error
        shared = [row for row in theirs if row.pol in mine]
        if shared:
            first = shared[0]
            raise MatrixError(
                f"POL {first.pol} is stated by two matrices of this workspace, {matrix.name} "
                f"(row {mine[first.pol]}) and {sibling.name} (row {first.row_number})"
                + (f", and {len(shared) - 1} more POL(s) likewise" if len(shared) > 1 else "")
                + f". A POL names the simulation folder sims/sim_{first.pol} and the run ids "
                f"of the one manifest, {workspace.manifest_path.name}, so each matrix of a "
                f"workspace states its own POLs; renumber the rows of one of the two."
            )


def resolve_matrix(
    path: str | Path,
    workspace: CampaignWorkspace,
    *,
    name: str,
    fs_version: str | None,
    recipes: Mapping[str, str],
    fs_exe: str | Path | None = None,
    ignore_missing_families: bool = True,
) -> ResolvedMatrix:
    """Bind a run matrix to the workspace input library.

    The matrix converts through the canonical campaign form
    (:func:`pyflightstream.cases.matrix.to_campaign`) and its reference
    columns resolve against the library under ``inputs/``: REF to
    reference data (applied to each case's ``reference``), SET to a
    solver preset (its runtime subset applied to each case's
    ``solver``), PPROC to the post-processing artifact (bound onto the case), and
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
    ignore_missing_families : bool
        Whether a pproc entry naming a family the opened mesh does not
        carry is left out (the default, True) or REFUSES the point
        (False, PFS-2035.13). It is a PER-INVOCATION choice and not a
        property of the row or of the artifact, both of which are meant
        to serve several geometries, so it travels as an argument and
        lands on each case's variables as ``IGNORE_MISSING_FAMILIES``,
        where the builders read it. ONLY FALSE WRITES ANYTHING: at the
        default every case resolves to exactly the case it resolved to
        before this argument existed, which is what keeps a run's
        identity and its emitted script unchanged.

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
        explicit override, a POL that another matrix of the workspace
        root states (PFS-2031.04, naming both files and rows), an
        executable override with no default version and no row build
        left (PFS-2031.14), or a row naming no build with a campaign
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
    _refuse_a_pol_stated_by_a_sibling(path, workspace, rows)
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
    # With no default given, the campaign's version is the first active
    # row's build, which is the installation _resolve_build already chose
    # the campaign executable from (PFS-2029.01); every row still runs on
    # the build its own cell names.
    if fs_version is not None:
        campaign_version = fs_version
    else:
        named = [build for build in row_builds if build]
        if not named:
            # Every active row named a build and the explicit override
            # overruled all of them, so nothing left says which version
            # the scripts are built for. A refusal naming the option,
            # where a bare StopIteration stood until 2026-09-08
            # (PFS-2031.14).
            raise MatrixError(
                f"{Path(path).name}: the explicit executable override overrules the "
                f"FS_BUILD cell of every active row, and no default version was given, so "
                f"nothing says which FlightStream version to build the scripts for. Pass "
                f"default_fs_version (CLI: {DEFAULT_VERSION_OPTION}), the version of the "
                f"installation the override names, or drop the override so each row runs "
                f"on the build its cell names through the registry."
            )
        campaign_version = named[0]
    campaign = to_campaign(
        path,
        name=name,
        fs_version=campaign_version,
        fs_exe=str(exe),
        recipes=recipes,
        # THE ONE CALLER THAT WILL RESOLVE THEM. A raw FILE record needs the
        # workspace's inputs, which this function has and `to_campaign` does
        # not; the list it builds is replaced below with the preset's lines
        # and the row's fully resolved ones (FR-67).
        defer_raw_files=True,
    )
    references: dict[str, ReferenceArtifact] = {}
    setups: dict[str, SetupArtifact] = {}
    pprocs: dict[str, PprocArtifact] = {}
    solvers: dict[str, SolverSettings] = {}
    #: The flight-condition pins each setup supplies, by setup id
    #: (PFS-2030.08). Read once per setup beside the solver settings, so a
    #: malformed table is refused at the first row that names the file.
    setup_pins: dict[str, dict[str, float]] = {}
    for row in rows:
        if row.ref_code not in references:
            references[row.ref_code] = _resolve_code(workspace, "reference", row.ref_code, row.pol)
        if row.set_code not in setups:
            setups[row.set_code] = _resolve_code(workspace, "setup", row.set_code, row.pol)
            solvers[row.set_code] = _solver_from_setup(setups[row.set_code], row.set_code)
            setup_pins[row.set_code] = _condition_defaults(setups[row.set_code], row.set_code)
        if row.pproc_code not in pprocs:
            pprocs[row.pproc_code] = _resolve_code(workspace, "pproc", row.pproc_code, row.pol)
            _refuse_groups_named_by_a_word(pprocs[row.pproc_code], row.pproc_code, row.pol)
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
                span_m=reference.span_m,
                # The moment point rides too, so a builder can put the
                # analysis loads frame on it (PFS-2030.03.02).
                moment_point_m=(
                    reference.moment_point.x_m,
                    reference.moment_point.y_m,
                    reference.moment_point.z_m,
                ),
                propeller_position_m=(
                    None
                    if reference.propeller is None
                    else (
                        reference.propeller.position.x_m,
                        reference.propeller.position.y_m,
                        reference.propeller.position.z_m,
                    )
                ),
            ),
            "solver": solvers[row.set_code],
            # THE REFERENCE'S FRAMES RIDE ON THE CASE (FR-72, her decision of
            # 2026-09-10), created by the builders after the package's own; a
            # configuration defining none leaves the list empty and the script
            # unchanged. They lived in the SETUP at 0.14.0 (PFS-2034.01), and a
            # coordinate system is geometric data, so it belongs beside the
            # lengths and the rotors; a preset still stating them is read with a
            # deprecation warning and the reference wins.
            "frames": _frames_for_row(reference, setups[row.set_code], row),
            # THE SETUP'S RAW COMMANDS RIDE ON THE CASE TOO (PFS-2033.01),
            # each naming the artifact it came from, for the run record.
            "raw_commands": [
                *(
                    entry.model_copy(update={"setup": row.set_code, "source": row.set_code})
                    for entry in _not_on_a_legacy_row(row, setups[row.set_code].raw_commands, "raw")
                ),
                # THE PRESET'S LINES ARE THE GROUND AND THE ROW'S COME OVER
                # THEM, which is her answer of 2026-09-10 and the whole of the
                # ordering question at a shared seam (FR-67). Her row 9210 is
                # the case that fixes it: a preset line, then the row's file,
                # then the row's own cell line.
                *_the_rows_raw_commands(row, workspace.inputs_dir),
            ],
            # THE REFERENCE'S ALIASES RIDE ON THE CASE (FR-59, her decision of
            # 2026-09-10), on a LEGACY row too: the products stage resolves a
            # group by them whatever built the script. They lived in the SETUP
            # at 0.14.0, which is per condition where a reference is per
            # configuration, and a boundary name is not a solver setting; a
            # preset still stating them is read with a deprecation warning and
            # the reference wins, so an unmigrated workspace keeps planning.
            "aliases": _aliases_of(reference, setups[row.set_code], row),
            # THE ROTORS RIDE ON THE CASE (FR-60): a motion record names one
            # by alias and takes its hub, axis, sign, blades and diameter
            # from it, so a row states nine rotors without repeating nine
            # hubs. A reference declaring none leaves this empty and every
            # row written before 0.15.0 resolves exactly as it did.
            "engines": dict(reference.engines),
            # THE PPROC ARTIFACT RIDES ON THE CASE (PFS-2029.07.03): the
            # builders emit its sections, plots and probes and export the
            # kinds it selects, and the record names its id. A LEGACY row's
            # recipe decides its own outputs, so only a workflow row takes
            # the export set from the artifact.
            "pproc": pprocs[row.pproc_code],
            "pproc_id": row.pproc_code,
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
        # `tests/tier1_offline/test_matrix_run.py`, at the reader AND here, rather than
        # defended twice in code and proven in neither place.
        stem = row.variables.get(GEOMETRY_VARIABLE, "")
        if stem:
            geometry_path = _resolve_geometry(workspace, stem, row.pol)
            update["geometry"] = str(geometry_path)
            update["inventory"], update["inventory_source"] = _inventory_of(geometry_path)
        if row.motions:
            update["motions"] = [_bind_motion(workspace, record, row.pol) for record in row.motions]
        # THE FLAT ROW'S OWN HUB, bound the same way (PFS-2031.12): one rotor
        # is not less entitled to a named hub than two, and the name stays
        # beside the coordinates so the record says which point it was.
        flat_origin = row.variables.get("ROTOR_ORIGIN", "")
        if flat_origin and not _is_three_numbers(flat_origin):
            bound = _bind_motion(workspace, {"ROTOR_ORIGIN": flat_origin}, row.pol, where="the row")
            update["variables"] = {**case.variables, **bound}
        # THE INVOCATION'S OWN CHOICE, written onto the row's variables so
        # the builders read it like any other variable and never learn that
        # a command line exists (PFS-2035.13, her design of 2026-09-10).
        #
        # ONLY THE FALSE SIDE WRITES. At the default the case is left
        # byte-for-byte the case it was before this argument existed, which
        # is what keeps every recorded run's identity and every emitted
        # script unchanged; a variable written on both sides would have put
        # a new key into every campaign of the 0.14.0 comparison.
        if not ignore_missing_families:
            stated = update.get("variables")
            base = stated if isinstance(stated, Mapping) else case.variables
            update["variables"] = {**base, IGNORE_MISSING_FAMILIES_VARIABLE: "false"}
        # PFS-2027.02 and .04. THE POSITION IS LOAD-BEARING and it is not
        # a comment asking for an ordering: the reference is bound at the
        # top of this loop body and reaches the case only through the
        # `model_copy` below, so `case.reference` is still None here. The
        # resolver therefore takes the length from the LOCAL binding, and
        # a resolver moved above that binding would silently resolve
        # every Reynolds constraint against no length at all -- which is
        # the failure `.04` exists to prevent, and which
        # `tests/tier1_offline/test_flight_condition_resolution.py` fails on rather
        # than describing.
        if row.flight_condition:
            resolved = resolve_flight_condition(
                row.flight_condition,
                pol=row.pol,
                reference_length_m=reference.chord_m,
                # PFS-2030.08: the fluid constants of the campaign live in
                # the setup the row names, and the row states what varies.
                # The origin travels as WORDS because the resolver never
                # reaches an artifact and its refusals have to name the
                # file the reader must open.
                defaults=setup_pins[row.set_code],
                defaults_origin=condition_defaults_origin(row.set_code),
            )
            conditions[row.pol] = resolved
            # The three the case already has fields for. The rest of the
            # state -- density, temperature, viscosity, the length it was
            # measured against and WHICH branch produced the density --
            # rides on `conditions` rather than being flattened onto the
            # case, because the run record is what has to carry it and a
            # case is not a record.
            # WHICH PINS CAME FROM THE SETUP, carried onto the case so the
            # run record can say. Without it a row that states four fewer
            # keys because its setup states them would record a resolution
            # nothing in the record explains, and PFS-2027.05 asks the
            # record to be recomputable rather than trusted.
            update["flight_condition_defaults"] = dict(resolved.defaulted)
            # AND WHERE THEY CAME FROM. Two reviews found the origin dying
            # at this boundary while its own docstring claimed a record
            # role: the record carried four numbers and could not name the
            # file that supplied them, which is one hop short of the
            # recomputability PFS-2027.05 asks for.
            update["flight_condition_defaults_from"] = (
                resolved.defaults_origin if resolved.defaulted else ""
            )
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
        if row.workflow != LEGACY_WORKFLOW:
            update["outputs"] = pprocs[row.pproc_code].outputs(
                unsteady=row.workflow.startswith("unsteady")
            )
        sims.append(case.model_copy(update=update))
    return ResolvedMatrix(
        campaign=campaign.model_copy(update={"sims": sims}),
        conditions=conditions,
        references=references,
        setups=setups,
        pprocs=pprocs,
        fs_exe=exe,
        builds=builds,
        row_builds=row_builds,
    )
