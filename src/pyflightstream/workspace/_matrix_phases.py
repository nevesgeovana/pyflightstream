"""Ordered build, artifact, row and flight-state phases of matrix resolution."""

from __future__ import annotations

import warnings
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from pyflightstream._errors import InputArtifactError, PyflightstreamError, PyflightstreamWarning
from pyflightstream._fsm import MeshReadError, boundary_names
from pyflightstream.cases import (
    POINT_AXIS_KEYS,
    CampaignConfigError,
    FluidState,
    MeshImport,
    PointState,
    RawCommand,
    RawMeshConditions,
    ReferenceData,
    SimCase,
    SolverSettings,
    point_state_key,
)
from pyflightstream.cases.acoustics import resolve_observers_file
from pyflightstream.cases.corrections import (
    CALIBRATIONS_DIR,
    CalibrationError,
    calibration_path,
    read_calibration,
)
from pyflightstream.cases.matrix import (
    ATTITUDE_KEYS,
    DEFAULT_VERSION_OPTION,
    LEGACY_WORKFLOW,
    RAW_BEFORE_KEY,
    RAW_COMMAND_KEY,
    RAW_FILE_KEY,
    RAW_VARIABLE,
    SWEEP_WORD,
    VELOCITY_KEYS,
    MatrixError,
    MatrixRow,
    refuse_silent_rows_without_default,
    to_campaign,
)
from pyflightstream.cases.workflows import (
    ADDITIONAL_PPROC_VARIABLE,
    FREESTREAM_DIR,
    FREESTREAM_FORMS,
    FREESTREAM_VARIABLE,
    GEOMETRY_VARIABLE,
    IGNORE_MISSING_FAMILIES_VARIABLE,
    PROFILE_VARIABLE,
    RAW_MESH_FORMATS,
    ROTOR_ORIGIN_POINT_KEY,
    SIMULATION_LENGTH_UNIT,
    actuator_records,
    read_actuator_profile,
    refuse_an_additional_post_build,
    refuse_what_a_saved_point_cannot_give,
    row_outputs,
)
from pyflightstream.workspace import CampaignWorkspace
from pyflightstream.workspace._matrix_binding import (
    _bind_setup_ports,
    _Binding,
    _condition_defaults,
    _setup_of_the_row,
    _solver_from_setup,
    condition_defaults_origin,
)
from pyflightstream.workspace.flight_condition import resolve_flight_condition
from pyflightstream.workspace.fsi_setup import resolve_row_fsi
from pyflightstream.workspace.inputs import (
    PprocArtifact,
    RegisteredBuild,
    ensure_inventory,
    inventory_sidecar,
    is_valid_artifact_id,
    read_inventory,
    read_mesh_import,
    read_raw_mesh_conditions,
    resolve_build,
    rotor_integration_groups,
)
from pyflightstream.workspace.naming import group_token
from pyflightstream.workspace.wake_edges import (
    length_scale,
    matched_trailing_edge_points,
    read_trailing_edge_points,
)


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
    *,
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
        # nothing said (measured on the reference campaign, 2026-08-03).
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
        build: _registered_build(workspace, build, rows, named, path, default=fallback)
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


def _resolve_code(
    workspace: CampaignWorkspace, kind: str, code: str, pol: str, *, column: str | None = None
):
    """Resolve one REF/SET/ENTRY code, naming the row and the target file.

    ``column`` names the cell the code came from where it is not the kind's own
    column: the additional pproc of G12 is a pproc named by a ``VAR_NAMES_VALUES``
    key, and a refusal naming "the PPROC column" would send its writer to the
    wrong cell. Left out, every message is the one it always was.
    """
    own_column, subdir, resolver = {
        "reference": ("REF", "references", workspace.resolve_reference),
        "setup": ("SET", "setups", workspace.resolve_setup),
        "pproc": ("PPROC", "pproc", workspace.resolve_pproc),
    }[kind]
    cell = f"the {own_column} column" if column is None else f"its {column} key"
    try:
        return resolver(code)
    except InputArtifactError as error:
        path = workspace.inputs_dir / subdir / f"{code}.toml"
        if is_valid_artifact_id(code) and path.is_file():
            raise InputArtifactError(
                f"matrix row POL {pol}: the {kind} artifact at {path} does not validate. {error}",
                kind=error.kind,
                artifact_id=error.artifact_id,
                available=error.available,
            ) from error
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
            f"matrix row POL {pol}: {cell} names {kind} {code!r}, which "
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
    """REFUSE a setup preset that still carries a table the reference now owns.

    FR-59 and FR-72. It raises and never returns: this function once warned
    and let the preset's table be read until 0.17.0, and its name and this
    docstring still said so after the behaviour changed to a refusal, which
    is how a reader learns the wrong rule from the file that implements the
    right one (the technical-writing lens of the 0.15.0 release review,
    which read those words and reported the package as accepting what it
    refuses).

    The message names the row's two artifacts and where the table belongs,
    because whoever meets it has exactly one edit to make.
    """
    # THE MESSAGE CARRIES NO ROW NUMBER, deliberately: the edit is one edit
    # per PRESET, not per row, so naming a row would point a fifty-row
    # campaign at a row rather than at the file to change (the interface
    # lens of 2026-09-10, when this warned and the warning filter deduped
    # on the message; a refusal stops at the first row, and the reasoning
    # for naming the file rather than the row is unchanged).
    raise InputArtifactError(
        f"the setup preset {row.set_code!r} states [{table}], which moved to the "
        f"reference artifact {row.ref_code!r} at 0.15.0: a boundary name and a "
        "coordinate system are properties of the CONFIGURATION, and a preset is per "
        "condition. The reference's entries are the ones every row citing it uses. "
        f"Move the table into the reference {row.ref_code!r} and delete it here.",
        kind="setup",
    )


def _aliases_of(reference, setup, row: MatrixRow) -> dict[str, list[str]]:
    """Return a row case's aliases, which are the REFERENCE's and only those.

    A preset stating any of its own is refused above, so there is nothing
    to merge and no case-folding question left: this used to merge the two
    tables, and the merge is gone with the deprecation it served rather
    than left behind as unreachable code that tells the next reader a
    preset's aliases still reach a case.
    """
    if setup.aliases:
        _moved_to_the_reference(row, "aliases")
    return {name: list(members) for name, members in reference.aliases.items()}


def _frames_of(reference, setup, row: MatrixRow) -> list:
    """Return a row case's custom frames, which are the REFERENCE's and only those.

    A preset stating any of its own is refused above, so there is nothing
    to merge, for the reason given in :func:`_aliases_of`.
    """
    if setup.frames:
        _moved_to_the_reference(row, "frames")
    return list(reference.frames)


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
            # and produce an emitter refusal about a command the user can
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

    Whether that is the right division is the open question of
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
    rotor point, and the record keeps the name beside the coordinates
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
        point = workspace.rotor_point(origin)
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


def _inventory_of(geometry: Path, pol: str) -> tuple[tuple[str, ...] | None, str | None]:
    """Return the sidecar's boundary order, if one sits beside the geometry, and the source.

    PFS-2029.06.03. The sidecar is read here, at binding, so a malformed
    one is refused with the row before any seat is spent; whether it
    AGREES with the file is the builder's check at ``OPEN``, because that
    is where the file's own mesh block is read for the staged copy.

    G30: THE SIDECAR IS REACHED THROUGH :func:`ensure_inventory`, the one
    function ``pyfs-matrix inventory`` reaches it through too. An OBJ with
    none gets one written from its groups, here, before the tables beside
    it are read; one whose sidecar disagrees with its groups draws a
    warning. A refusal of the OBJ is given the row, as the sidecar's other
    tables' refusals are.
    """
    try:
        sidecar = ensure_inventory(geometry)
    except InputArtifactError as error:
        raise InputArtifactError(
            f"matrix row POL {pol}: the {GEOMETRY_VARIABLE} variable names {geometry.name}, "
            f"and {error}"
        ) from error
    if sidecar.is_file():
        return read_inventory(sidecar), "sidecar"
    try:
        declared = boundary_names(geometry)
    except MeshReadError:
        return None, None
    return None, ("mesh_block" if declared else None)


def _mesh_import_of(geometry: Path, pol: str) -> MeshImport | None:
    """Return the ``[import]`` table of the sidecar beside the geometry, if it states one (G01).

    Read here, at binding, beside :func:`_inventory_of`, so a table that does
    not hold its shape is refused with the row before any seat is spent.
    Whether the geometry is a raw mesh, and whether the build's ``IMPORT``
    takes the unit, is the builder's check, because both are judged per
    build and a case built in Python meets them too.
    """
    sidecar = inventory_sidecar(geometry)
    if not sidecar.is_file():
        return None
    try:
        return read_mesh_import(sidecar)
    except InputArtifactError as error:
        raise InputArtifactError(
            f"matrix row POL {pol}: the {GEOMETRY_VARIABLE} variable names {geometry.name}, "
            f"and {error}"
        ) from error


def _raw_mesh_conditions_of(
    geometry: Path,
    pol: str,
    mesh_import: MeshImport | None,
    solver: SolverSettings | None = None,
) -> RawMeshConditions | None:
    """Return the boundary conditions the geometry's sidecar declares, a points file read (G02).

    Read here, at binding, beside :func:`_mesh_import_of`, so a table that
    does not hold its shape, a points file that cannot be read, or a point
    that lies on no edge of the mesh is refused with the row before any
    seat is spent. The points are checked against the mesh file in the
    unit its ``[import]`` table states and come back in the simulation's
    metres, which is what the builder writes for the solver.

    The check is left to the builder's refusals where it cannot be made
    here: a geometry that is not a raw mesh, a mesh with no stated unit or
    a unit with no scale, and an import that moves or scales the body,
    since the points name edges of the file as written. Each is refused by
    the builder, naming what to change, and a case built in Python meets
    the same refusals.
    """
    sidecar = inventory_sidecar(geometry)
    if not sidecar.is_file():
        return None
    where = f"matrix row POL {pol}: the {GEOMETRY_VARIABLE} variable names {geometry.name}, and"
    try:
        declared = read_raw_mesh_conditions(sidecar)
    except InputArtifactError as error:
        raise InputArtifactError(f"{where} {error}") from error
    marking = None if declared is None else declared.trailing_edges
    if (
        declared is None
        or marking is None
        or marking.route != "file"
        or (solver is not None and solver.apply_trailing_edges is False)
    ):
        return declared
    if (
        geometry.suffix.lower() not in RAW_MESH_FORMATS
        or mesh_import is None
        or mesh_import.moving_operations
    ):
        return declared
    try:
        length_scale(mesh_import.units, SIMULATION_LENGTH_UNIT)
    except InputArtifactError:
        return declared
    assert marking.points_file is not None  # the file route's reader always sets it
    points_file = Path(marking.points_file)
    try:
        read = read_trailing_edge_points(points_file)
        points = matched_trailing_edge_points(
            read.points,
            points_unit=read.unit,
            mesh=geometry,
            mesh_unit=mesh_import.units,
            simulation_unit=SIMULATION_LENGTH_UNIT,
            tolerance=marking.tolerance,
            source=f"the [trailing_edges] file {points_file.name} of {sidecar.name}",
            lines=read.lines,
        )
    except InputArtifactError as error:
        raise InputArtifactError(f"{where} {error}") from error
    checked = tuple((float(x), float(y), float(z)) for x, y, z in points.tolist())
    return declared.model_copy(
        update={"trailing_edges": marking.model_copy(update={"points_m": checked})}
    )


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


def _with_rotor_groups(pproc: PprocArtifact, reference, code: str, pol: str) -> PprocArtifact:
    """Return ``pproc`` with one integration group per rotor the reference declares.

    Item 15. `rotor_integration_groups` held the whole rule and had NO CALLER,
    so a release that promised a group per rotor created none: every test of it
    called the function directly and passed over a campaign that never reached
    it.

    A reference declaring no rotor leaves the artifact untouched, so a matrix
    written before rotors existed binds exactly as it did.

    The refusal it can raise is re-raised with the ROW and the artifact named,
    which is what the binder adds to every other artifact refusal here: a
    message saying two lists disagree is only actionable once a reader knows
    which pproc file and which matrix row to open.
    """
    rotors = getattr(reference, "rotors", None) or {}
    if not rotors:
        return pproc
    try:
        resolved = rotor_integration_groups(rotors, pproc.groups)
    except PyflightstreamError as clash:
        raise InputArtifactError(
            f"matrix row POL {pol}: the PPROC column names pproc {code!r} "
            f"(inputs/pproc/{code}.toml). {clash}",
            kind="pproc",
            artifact_id=code,
        ) from clash
    if resolved == dict(pproc.groups):
        return pproc
    # NO SECOND NAMING REFUSAL IS ADDED HERE, and that is a decision with a
    # measurement behind it rather than an omission. A closing round reported
    # that `_refuse_groups_named_by_a_word` runs on the RAW pproc only, so the
    # groups THIS function invents from a rotor's alias were never checked --
    # and that a rotor aliased `g01` would therefore reach the products stage
    # and fail there, after the seat was spent.
    #
    # THE FIRST HALF IS TRUE AND THE CONCLUSION IS NOT. `ReferenceArtifact`
    # already refuses such an alias when the reference is validated, which is
    # before any of this and long before a run: "alias 'g01' is spelled as a
    # pproc group ... choose a name that is not g<number>". The lens measured
    # `RotorBlock` in isolation, where the alias is indeed accepted, and the
    # artifact that contains it is where the rule lives. A guard added here
    # could never fire, and an unreachable refusal carrying a comment that
    # claims to close a live hole is worse than none: it reads as cover.
    # The case that proves the refusal happens at plan time is
    # `test_a_rotor_aliased_like_the_numbered_era_is_refused_at_plan_time`,
    # which nothing covered until that round asked the question.
    return pproc.model_copy(update={"groups": resolved})


def _refuse_groups_named_by_a_word(pproc: PprocArtifact, code: str, pol: str) -> None:
    """Refuse a pproc group whose name reads as the NUMBERED era's own suffix.

    THIS REFUSED EVERY WORD UNTIL 0.23.0, and that is what made item 14
    unreachable from the other side. PFS-2032.03 refused a word here because the
    polar table carried the group NUMBER in its name and `int(group)` therefore
    stopped the whole products stage with a bare ValueError, after the seat was
    spent. The naming is what changed: a group is now NAMED and the product file
    carries that name, so the refusal's own reason is gone -- and a user
    following the migration guide met this refusal telling them to undo the very
    rename the guide had just asked for.

    WHAT STAYS REFUSED is the one name that cannot work: `g01` and its kin read
    as the suffix the numbered era wrote, so a file named after one could not be
    told from the form it supersedes -- and the migration that moves
    existing products needs exactly that difference to know what it has already
    moved. The token is resolved by
    :func:`pyflightstream.workspace.naming.group_token`, which is what the
    products stage and the super file both call, so this refusal and the file
    name cannot drift apart. THIS LINE SAID `post._tables` until a closing round
    read it: the function moved to `workspace.naming` in this same release,
    precisely so that this module could ask it without importing `post`, and the
    sentence explaining the arrangement still pointed at the layer the move was
    made to avoid.

    An artifact that writes no polar tables is left alone, as before.
    """
    if not pproc.products.polars:
        return
    # THROUGH `group_token`, the one function that decides what a product
    # file carries for a group. Asking it is how this refusal and the file
    # name stay one rule instead of two that drift.
    collides = []
    for name in pproc.groups:
        try:
            group_token(str(name))
        except ValueError:
            collides.append(str(name))
    collides.sort()
    if not collides:
        return
    raise InputArtifactError(
        f"matrix row POL {pol}: the PPROC column names pproc {code!r} "
        f"(inputs/pproc/{code}.toml), whose [groups] table names "
        f"{', '.join(repr(name) for name in collides)}. That is the shape the numbered "
        "era wrote as a SUFFIX, so a product named after it could not be told from the "
        "form it supersedes, and the rename that moves the products you already have "
        'needs that difference. Give the group a name of its own: PUSHER = "Blade1".',
        kind="pproc",
        artifact_id=code,
    )


def _resolve_cited_profiles(workspace: CampaignWorkspace, pproc, code: str, pol: str):
    """Give each probe entry that cites a survey the survey's absolute path (FR-80).

    THE GEOMETRY IS THE PRECEDENT. A GEOMETRY stem becomes an absolute path on
    the case here, when the row binds, and the script opens that path; a
    survey is an input the same way and reaches the solver the same way. The
    relative line it replaced named `profiles/<file>` inside the simulation
    folder, where nothing had ever staged the file, and which a submitted
    point's working directory is not (GOAL-021 item 2, measured 2026-09-14).

    IMPORTED IN PLACE, NOT COPIED: FR-80 says a cited profile is input a run
    must never write over, and the import reads it where it lives.

    A NAME THE FOLDER DOES NOT HOLD IS REFUSED HERE, when the row is planned,
    naming what the folder does hold. FR-80 promised that refusal and nothing
    performed it, so a missing survey reached the solver as a silent import of
    nothing.
    """
    if not any(entry.points_file for entry in pproc.probes):
        return pproc
    folder = Path(workspace.inputs_dir) / "profiles"
    probes = []
    for entry in pproc.probes:
        if not entry.points_file:
            probes.append(entry)
            continue
        path = folder / entry.points_file
        if not path.is_file():
            held = (
                sorted(p.name for p in folder.iterdir() if p.is_file()) if folder.is_dir() else []
            )
            raise InputArtifactError(
                f"matrix row POL {pol}: the pproc artifact {code!r} cites the probe survey "
                f"{entry.points_file!r}, and {folder} holds no such file"
                + (f"; it holds {', '.join(held)}" if held else ", or holds nothing")
                + ". A cited survey lives in the workspace's inputs/profiles/ folder, where "
                "no run writes over it.",
                kind="pproc",
                artifact_id=code,
            )
        probes.append(entry.model_copy(update={"resolved_points_file": str(path.resolve())}))
    return pproc.model_copy(update={"probes": probes})


def _resolve_actuator_profile(
    workspace: CampaignWorkspace,
    row: MatrixRow,
    *,
    stem: str | None = None,
) -> str | None:
    """Give a row's ``PROFILE`` the absolute path of its file under ``inputs/profiles/`` (G06).

    THE PROBE SURVEY IS THE PRECEDENT (:func:`_resolve_cited_profiles`): the
    file is imported where it lives, by the absolute path resolved here, and a
    name the folder does not hold is refused when the row is PLANNED, naming
    what the folder holds. The cell names the file by its STEM, which is how
    the profile library registers a file.

    A FILE THE SOLVER WOULD MISREAD IS REFUSED HERE TOO, naming the file and
    the line (:func:`~pyflightstream.cases.workflows.read_actuator_profile`):
    a header or a count first, a row that is not two numbers separated by
    one comma, fewer than two rows. A final newline and blank lines are not
    refused, since the solver never reads this file: the run writes its own
    copy of the rows, with no final newline, where the point runs, and the
    script names the copy. So the user's file is never staged beside the
    geometry, and never written; the record hashes the copy.
    """
    stem = row.variables.get(PROFILE_VARIABLE, "") if stem is None else stem
    if not stem:
        return None
    folder = Path(workspace.inputs_dir) / "profiles"
    try:
        path = workspace.resolve_profile(stem)
    except InputArtifactError as error:
        held = sorted(p.name for p in folder.iterdir() if p.is_file()) if folder.is_dir() else []
        raise InputArtifactError(
            f"matrix row POL {row.pol}: PROFILE names {stem!r}, and {folder} holds no "
            "single file of that stem"
            + (f"; it holds {', '.join(held)}" if held else ", or holds nothing")
            + ". An actuator profile lives in the workspace's inputs/profiles/ folder "
            f"and the cell names it by its stem ({error})",
            kind="profile",
            artifact_id=stem,
        ) from None
    resolved = path.resolve()
    try:
        read_actuator_profile(resolved)
    except CampaignConfigError as error:
        raise InputArtifactError(
            f"matrix row POL {row.pol}: PROFILE names {stem!r}, and {error}",
            kind="profile",
            artifact_id=stem,
        ) from None
    return str(resolved)


def _validate_qsteady_calibration(
    workspace: CampaignWorkspace, pproc: object, row: MatrixRow
) -> None:
    """Refuse at plan a calibration the pproc's ``[qsteady_correction]`` names and cannot read.

    0.31.0 (P0310-CAL-SCHEMA). The route is applied at post, which reads the
    file again and never blocks; the plan reads it first so a broken file is
    named before a solver runs rather than after. Nothing of the file reaches
    the script: choosing or changing a route needs no new run.
    """
    spec = getattr(pproc, "qsteady_correction", None)
    if spec is None or spec.route == "none" or not spec.file:
        return
    path = calibration_path(workspace.inputs_dir, spec.file)
    if not path.is_file():
        raise InputArtifactError(
            f"matrix row POL {row.pol}: the pproc {row.pproc_code!r} names the calibration "
            f"{spec.file!r} in [qsteady_correction], and {path} does not exist. A calibration "
            f"lives in the workspace's inputs/{CALIBRATIONS_DIR}/ folder, named by its id.",
            kind="calibration",
            artifact_id=spec.file,
        )
    calibration = read_calibration(path)
    if calibration.route != spec.route:
        raise CalibrationError(
            f"matrix row POL {row.pol}: the pproc {row.pproc_code!r} asks route "
            f"{spec.route!r} and the calibration {path} states route {calibration.route!r}. "
            f"Set the pproc's [qsteady_correction] route = {calibration.route!r} to match "
            f"the calibration, or point its file at a calibration of route {spec.route!r}",
            path=path,
        )


def _resolve_freestream(workspace: CampaignWorkspace, row: MatrixRow) -> str | None:
    """Give a row's ``FREESTREAM`` the absolute path of its file of ``inputs/freestreams/`` (G15).

    THE ACTUATOR PROFILE IS THE PRECEDENT (:func:`_resolve_actuator_profile`):
    the cell names the file by its STEM and the plan resolves it to an
    absolute path. Unlike the profile, which the run copies into the form the
    solver reads, the field is read where it lives, by the absolute path the
    script names, never staged beside the mesh; the run hashes it into the
    record's ``inputs_sha256``.

    The EXTENSION IS THE FORM, as the manual ties them: ``<stem>.txt`` is
    STRUCTURED and ``<stem>.dat`` UNSTRUCTURED. So the folder must hold exactly
    one of the two, and both, or neither, is refused naming the folder and
    what it holds. A LEGACY row stating the key is refused: its script is its
    recipe's, which writes its own free stream, so the key would change
    nothing about the run while reading as though it had.
    """
    stem = row.variables.get(FREESTREAM_VARIABLE, "")
    if not stem:
        return None
    if row.workflow == LEGACY_WORKFLOW:
        raise MatrixError(
            f"POL {row.pol} writes LEGACY and states {FREESTREAM_VARIABLE}: {stem}. A custom "
            "free stream is written by a run type's free-stream step, and a LEGACY row's "
            "script is its own recipe's, which the package does not read. Name a run type in "
            "the WORKFLOW column, or drop the key."
        )
    folder = Path(workspace.inputs_dir) / FREESTREAM_DIR
    held = sorted(p.name for p in folder.iterdir() if p.is_file()) if folder.is_dir() else []
    found = [f"{stem}{suffix}" for suffix in FREESTREAM_FORMS if f"{stem}{suffix}" in held]
    if len(found) == 1:
        return str((folder / found[0]).resolve())
    if found:
        raise InputArtifactError(
            f"matrix row POL {row.pol}: {FREESTREAM_VARIABLE} names {stem!r}, and {folder} "
            f"holds both {' and '.join(found)}. The extension states the form (.txt "
            "STRUCTURED, .dat UNSTRUCTURED), so one stem names one file: rename or remove one "
            "of them.",
            kind="freestream",
            artifact_id=stem,
        )
    forms = " nor ".join(
        f"{stem}{suffix} (the {form} form)" for suffix, form in FREESTREAM_FORMS.items()
    )
    raise InputArtifactError(
        f"matrix row POL {row.pol}: {FREESTREAM_VARIABLE} names {stem!r}, and {folder} holds "
        f"neither {forms}"
        + (f"; it holds {', '.join(held)}" if held else ", or holds nothing")
        + f". A custom free stream lives in the workspace's inputs/{FREESTREAM_DIR}/ folder, "
        "and the cell names it by its stem, without the extension.",
        kind="freestream",
        artifact_id=stem,
    )


def _derives_its_velocity(row: MatrixRow) -> bool:
    """Say whether this row's velocity comes from its rotor speed and advance ratio."""
    if any(key in row.flight_condition for key in VELOCITY_KEYS):
        return False
    first = next(row.sweep.points(), {})
    return (
        _attitude_at(row, ADVANCE_RATIO_KEY, first) is not None
        and _attitude_at(row, RPM_KEY, first) is not None
    )


def _swept_condition_key(row: MatrixRow) -> str | None:
    """Return the FLIGHT_CONDITION key this row sweeps, or None for an attitude.

    The angles, the advance ratio and the rotor speed are ATTITUDE: they reach
    the solver as they are. Every other key of the cell is the flow itself, and
    the swept one is the key whose value each point carries.
    """
    key = POINT_AXIS_KEYS.get(row.sweep.type)
    if key is None or key in ATTITUDE_KEYS:
        return None
    return key


def _attitude_at(row: MatrixRow, key: str, point: Mapping[str, float]) -> float | None:
    """Return one attitude value of this row at one point: the point's, else the row's."""
    axis = next((axis for axis, cell in POINT_AXIS_KEYS.items() if cell == key), None)
    if axis is not None and axis in point:
        return float(point[axis])
    stated = row.variables.get(key)
    if stated is None or str(stated).strip().casefold() == SWEEP_WORD.casefold():
        return None
    try:
        return float(str(stated))
    except ValueError:
        return None


def _derived_velocity(
    row: MatrixRow, point: Mapping[str, float], *, diameter_m: float | None
) -> float | None:
    """Return the velocity V = J x (RPM/60) x D this point states, or None.

    A rotor study states the speed and
    the advance ratio and no velocity at all: the three are one relation, and
    the velocity is the one the run needs. The magnitude of the speed is what
    enters it; the sign is the HAND of the rotation and turns no free stream
    around.

    THE RELATION IS THE PROPELLER ADVANCE RATIO, J = V / (n D) with n in
    revolutions per SECOND, which is why the rev/min are divided by sixty. The
    rotorcraft advance ratio, mu = V / (Omega R), is a different number for the
    same inputs -- larger by pi/2 -- and is not what this package reads. It is
    named here because the vocabulary of this package spans both (the V&V lens,
    2026-09-16).

    A cell stating a velocity as well is refused where the cell is read, so by
    the time this is asked there is nothing to disagree with.
    """
    if any(key in row.flight_condition for key in VELOCITY_KEYS):
        return None
    ratio = _attitude_at(row, ADVANCE_RATIO_KEY, point)
    rpm = _attitude_at(row, RPM_KEY, point)
    if ratio is None or rpm is None:
        return None
    if diameter_m is None:
        raise MatrixError(
            f"POL {row.pol}: FLIGHT_CONDITION states RPM and ADVANCE_RATIO and no "
            "velocity, so the velocity is V = J x (RPM/60) x D and D is the diameter "
            "of the rotor the clock follows. This row names no CLOCK_MOTION rotor "
            "whose diameter can be read: write 'CLOCK_MOTION: <alias>' in "
            "VAR_NAMES_VALUES naming a rotor of this row's REF, and give that rotor a "
            "diameter_m in the reference artifact."
        )
    return ratio * (abs(rpm) / 60.0) * diameter_m


def _clock_rotor_diameter(row: MatrixRow, reference: Any) -> float | None:
    """Return the diameter of the rotor this row's CLOCK_MOTION names.

    THE CLOCK'S ROTOR AND NO OTHER: a configuration may
    carry several rotors of different diameters, and the one the row is about
    is the one whose clock it runs on. A row naming none has no answer here and
    the caller refuses by name rather than reaching for the reference's own
    single diameter, which would be a different rotor stated somewhere else.
    """
    alias = str(row.variables.get("CLOCK_MOTION") or "").strip()
    if not alias:
        return None
    for name, block in reference.rotors.items():
        if name.casefold() == alias.casefold():
            return block.diameter_m
    return None


def _stated_at(
    row: MatrixRow, point: Mapping[str, float], *, diameter_m: float | None = None
) -> dict[str, float]:
    """Return the condition this row states AT one point of its sweep.

    The row's cell with the swept key put back at this point's value, and the
    velocity the point's advance ratio and rotor speed work out to where the
    cell states no velocity of its own.
    """
    key = _swept_condition_key(row)
    stated = dict(row.flight_condition)
    if key is not None and row.sweep.type in point:
        stated[key] = float(point[row.sweep.type])
    velocity = _derived_velocity(row, point, diameter_m=diameter_m)
    if velocity is not None:
        stated["TASmps"] = velocity
    return stated


def _states_per_point(
    row: MatrixRow,
    *,
    reference_length_m: float | None,
    defaults: Mapping[str, float] | None,
    defaults_origin: str | None,
    diameter_m: float | None = None,
) -> dict[str, PointState]:
    """Resolve the flow state of every point of a row whose points differ in it.

    Empty for every row whose points share one state, which is every sweep of
    an attitude: carrying a copy of that one state per point would put the same
    numbers in the manifest as many times as the row has points. A row that
    sweeps a flow variable is one case; so is a row whose velocity is derived
    from a swept rotor speed or a swept advance ratio, which is why this asks
    what the points STATE rather than which axis carries the word.
    """
    points = list(row.sweep.points())
    stated_per_point = [_stated_at(row, point, diameter_m=diameter_m) for point in points]
    if len(points) < 2 or all(stated == stated_per_point[0] for stated in stated_per_point):
        return {}
    states: dict[str, PointState] = {}
    for point, stated in zip(points, stated_per_point, strict=True):
        resolved = resolve_flight_condition(
            stated,
            pol=row.pol,
            reference_length_m=reference_length_m,
            defaults=defaults,
            defaults_origin=defaults_origin,
        )
        states[point_state_key(point)] = PointState(
            mach=resolved.mach,
            velocity=resolved.velocity_m_per_s,
            reynolds=resolved.reynolds,
            fluid=FluidState(
                velocity_m_per_s=resolved.velocity_m_per_s,
                density_kg_m3=resolved.density_kg_m3,
                pressure_pa=resolved.pressure_pa,
                temperature_k=resolved.temperature_k,
                viscosity_pa_s=resolved.viscosity_pa_s,
                sonic_velocity_m_per_s=resolved.sonic_velocity_m_per_s,
                heat_capacity_ratio=resolved.heat_capacity_ratio,
                source=resolved.density_source,
                reference_length_m=resolved.reference_length_m,
            ),
            flight_condition=stated,
            flight_condition_defaults=dict(resolved.defaulted),
            flight_condition_defaults_from=(
                (resolved.defaults_origin or "") if resolved.defaulted else ""
            ),
        )
    return states


def _additional_pprocs(
    rows: list[MatrixRow],
    row_builds: tuple[str | None, ...],
    builds: Mapping[str, RegisteredBuild],
    workspace: CampaignWorkspace,
    *,
    fs_version: str | None,
    campaign: str,
) -> dict[str, PprocArtifact]:
    """Resolve and judge the additional pproc every row names (G12 of 0.27.0).

    AT PLAN, like the row's PPROC, and for the reason every refusal of this
    function lives here: the additional post runs after the seat is spent, so a
    key it could not honour must stop the plan rather than surface afterwards.
    Refused, each by name:

    * the key on a LEGACY row, whose recipe creates frames by rules of its own,
      so nothing can say which frame of its saved simulation a distribution cites;
    * a row whose build is not one the additional post was measured on (RPT-062);
    * an id the input library cannot resolve, naming the key and the file;
    * an artifact asking what a reopened simulation does not give back.

    A blank value names nothing, as a blank ``GEOMETRY`` does. The value stays
    the string it is on the case: no builder reads it.
    """
    resolved: dict[str, PprocArtifact] = {}
    for row, build in zip(rows, row_builds, strict=True):
        code = row.variables.get(ADDITIONAL_PPROC_VARIABLE, "")
        if not code:
            continue
        where = f"matrix row POL {row.pol}"
        if row.workflow == LEGACY_WORKFLOW:
            raise MatrixError(
                f"POL {row.pol} writes LEGACY and states {ADDITIONAL_PPROC_VARIABLE}: {code}. "
                "The additional post cuts new distributions in the frames the point's saved "
                "simulation holds, which it knows by building the row's run type again; a "
                "LEGACY row is built by its own recipe, so nothing can say which frame is "
                "which. Name a run type in the WORKFLOW column, or drop the key."
            )
        registered = builds.get(build) if build else None
        version = (
            (registered.fs_version if registered is not None else None)
            or fs_version
            or build
            or campaign
        )
        refuse_an_additional_post_build(version, where=where)
        if code in resolved:
            continue
        artifact = _resolve_code(
            workspace, "pproc", code, row.pol, column=ADDITIONAL_PPROC_VARIABLE
        )
        _refuse_groups_named_by_a_word(artifact, code, row.pol)
        refuse_what_a_saved_point_cannot_give(artifact, pproc_id=code, where=where)
        resolved[code] = artifact
    return resolved


#: The cell keys this module reaches for by name.
ADVANCE_RATIO_KEY = "ADVANCE_RATIO"
RPM_KEY = "RPM"


def _bind_build(
    rows: list[MatrixRow],
    workspace: CampaignWorkspace,
    *,
    path: str | Path,
    name: str,
    fs_version: str | None,
    recipes: Mapping[str, str],
    fs_exe: str | Path | None,
    ignore_missing_families: bool,
) -> _Binding:
    """Resolve builds and convert the rows before binding their input artifacts."""
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
    return _Binding(
        workspace=workspace,
        rows=rows,
        campaign=campaign,
        fs_exe=exe,
        builds=builds,
        row_builds=row_builds,
        fs_version=fs_version,
        campaign_version=campaign_version,
        ignore_missing_families=ignore_missing_families,
    )


def _bind_setup(binding: _Binding, row: MatrixRow) -> None:
    """Load a row's reference, solver preset and condition pins once per code."""
    if row.ref_code not in binding.references:
        binding.references[row.ref_code] = _resolve_code(
            binding.workspace, "reference", row.ref_code, row.pol
        )
    if row.set_code not in binding.setups:
        binding.setups[row.set_code] = _resolve_code(
            binding.workspace, "setup", row.set_code, row.pol
        )
        binding.solvers[row.set_code] = _solver_from_setup(
            binding.setups[row.set_code], row.set_code
        )
        binding.setup_pins[row.set_code] = _condition_defaults(
            binding.setups[row.set_code], row.set_code
        )


def _bind_pproc(binding: _Binding, row: MatrixRow) -> None:
    """Resolve and validate the post artifact after the same row's setup."""
    if row.pproc_code not in binding.pprocs:
        binding.pprocs[row.pproc_code] = _resolve_code(
            binding.workspace, "pproc", row.pproc_code, row.pol
        )
        _refuse_groups_named_by_a_word(binding.pprocs[row.pproc_code], row.pproc_code, row.pol)
        binding.pprocs[row.pproc_code] = _resolve_cited_profiles(
            binding.workspace, binding.pprocs[row.pproc_code], row.pproc_code, row.pol
        )
        _validate_qsteady_calibration(binding.workspace, binding.pprocs[row.pproc_code], row)


def _bind_artifacts(binding: _Binding) -> None:
    """Keep reference, setup and post refusals in their original row order."""
    for row in binding.rows:
        _bind_setup(binding, row)
        _bind_pproc(binding, row)
    binding.additional_pprocs = _additional_pprocs(
        binding.rows,
        binding.row_builds,
        binding.builds,
        binding.workspace,
        fs_version=binding.fs_version,
        campaign=binding.campaign_version,
    )


def _row_update(binding: _Binding, case: SimCase, row: MatrixRow) -> dict[str, object]:
    """Bind the reference and setup onto a row before resolving its files."""
    reference = binding.references[row.ref_code]
    update: dict[str, object] = {
        # THE DIAMETER TRAVELS WITH THE OTHER TWO LENGTHS. It is a
        # reference length rather than rotor metadata, and it is
        # the one an advance ratio needs: a row stating
        # ADVANCE_RATIO resolves n = V / (J D), so a diameter that
        # stopped at the artifact would leave the ratio naming no
        # rotor speed. None stays None, which is what keeps a
        # configuration with no rotor resolving exactly as it did.
        "reference": ReferenceData(
            normalization_units="SI",
            area=reference.area_m2,
            length=reference.chord_m,
            rotor_diameter=reference.rotor_diameter_m,
            span_m=reference.span_m,
            # The moment point rides too, so a builder can put the
            # analysis loads frame on it (PFS-2030.03.02).
            moment_point_m=(
                reference.moment_point.x_m,
                reference.moment_point.y_m,
                reference.moment_point.z_m,
            ),
            rotor_position_m=(
                None
                if reference.rotor is None
                else (
                    reference.rotor.position.x_m,
                    reference.rotor.position.y_m,
                    reference.rotor.position.z_m,
                )
            ),
            body_axes=dict(reference.body_axes),
        ),
        # FR-316: THE ROW'S SETUP KEYS, over its preset, for this row only: the
        # solver, and where the row states any, the keys and the variables left.
        **_setup_of_the_row(binding.setups[row.set_code], binding.solvers[row.set_code], row, case),
        # THE REFERENCE'S FRAMES RIDE ON THE CASE (FR-72, the design decision of
        # 2026-09-10), created by the builders after the package's own; a
        # configuration defining none leaves the list empty and the script
        # unchanged. They lived in the SETUP at 0.14.0 (PFS-2034.01), and a
        # coordinate system is geometric data, so it belongs beside the
        # lengths and the rotors; a preset still stating them is REFUSED
        # when a row binds it, naming the reference to move them into.
        "frames": _frames_for_row(reference, binding.setups[row.set_code], row),
        # THE SETUP'S RAW COMMANDS RIDE ON THE CASE TOO (PFS-2033.01),
        # each naming the artifact it came from, for the run record.
        "raw_commands": [
            *(
                entry.model_copy(update={"setup": row.set_code, "source": row.set_code})
                for entry in _not_on_a_legacy_row(
                    row, binding.setups[row.set_code].raw_commands, "raw"
                )
            ),
            # THE PRESET'S LINES ARE THE GROUND AND THE ROW'S COME OVER
            # THEM, which is the decision of 2026-09-10 and the whole of the
            # ordering question at a shared seam (FR-67). The reference row 9210 is
            # the case that fixes it: a preset line, then the row's file,
            # then the row's own cell line.
            *_the_rows_raw_commands(row, binding.workspace.inputs_dir),
        ],
        # THE SETUP'S CUSTOM FLAGS RIDE ON THE CASE (PFS-2035.20), each
        # naming the artifact that declared it. A flag is what makes RAW
        # the escape rather than the ordinary way to reach a setting: the
        # preset names the command, and the ROW states the value, so one
        # preset serves a sweep over it.
        "flags": [
            entry.model_copy(update={"setup": row.set_code})
            for entry in _not_on_a_legacy_row(row, binding.setups[row.set_code].flags, "flags")
        ],
        # THE REFERENCE'S ALIASES RIDE ON THE CASE (FR-59, the design decision of
        # 2026-09-10), on a LEGACY row too: the products stage resolves a
        # group by them whatever built the script. They lived in the SETUP
        # at 0.14.0, which is per condition where a reference is per
        # configuration, and a boundary name is not a solver setting; a
        # preset still stating them is REFUSED when a row binds it,
        # naming the reference to move them into.
        "aliases": _aliases_of(reference, binding.setups[row.set_code], row),
        # THE ROTORS RIDE ON THE CASE (FR-60): a motion record names one
        # by alias and takes its hub, axis, sign, blades and diameter
        # from it, so a row states nine rotors without repeating nine
        # hubs. A reference declaring none leaves this empty and every
        # row written before 0.15.0 resolves exactly as it did.
        "rotors": dict(reference.rotors),
        # THE ACTUATOR DISCS RIDE ON THE CASE (G06), as the rotors do: the
        # row's ACTUATOR names one and its loading keys load it. A reference
        # declaring none leaves this empty and every row resolves as before.
        "actuators": dict(reference.actuators),
        # THE PPROC ARTIFACT RIDES ON THE CASE (PFS-2029.07.03): the
        # builders emit its sections, plots and probes and export the
        # kinds it selects, and the record names its id. A LEGACY row's
        # recipe decides its own outputs, so only a workflow row takes
        # the export set from the artifact.
        # ITEM 15 WIRED HERE, and here rather than where the pproc is
        # RESOLVED, because the created group comes from the ROW's
        # reference: one pproc named by two rows with different binding.references
        # owes each of them the groups of its own rotors, and resolving it
        # once per code would give the second row the first one's.
        "pproc": _with_rotor_groups(
            binding.pprocs[row.pproc_code], reference, row.pproc_code, row.pol
        ),
        "pproc_id": row.pproc_code,
    }
    return update


def _bind_geometry(binding: _Binding, row: MatrixRow, update: dict[str, object]) -> None:
    """Resolve FSI and geometry in the order their values reach the case."""
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
    fsi = resolve_row_fsi(binding.workspace.inputs_dir, row.variables)
    if fsi is not None:
        binding.fsis[row.pol] = fsi
        update["fsi"] = fsi.effective
        update["fsi_provenance"] = fsi.provenance()
    stem = row.variables.get(GEOMETRY_VARIABLE, "")
    if stem:
        geometry_path = _resolve_geometry(binding.workspace, stem, row.pol)
        update["geometry"] = str(geometry_path)
        update["inventory"], update["inventory_source"] = _inventory_of(geometry_path, row.pol)
        mesh_import = _mesh_import_of(geometry_path, row.pol)
        update["mesh_import"] = mesh_import
        update["raw_mesh_conditions"] = _raw_mesh_conditions_of(
            geometry_path, row.pol, mesh_import, cast(SolverSettings, update["solver"])
        )


def _bind_profiles(
    binding: _Binding, case: SimCase, row: MatrixRow, update: dict[str, object]
) -> None:
    """Bind actuator, free-stream and acoustic input files for one row."""
    # G06: A ROW'S PROFILE IS A FILE OF inputs/profiles/, resolved HERE, when
    # the row is planned, to the absolute path the script imports. A LEGACY
    # row keeps the word, because its recipe is the reader of its keys.
    if row.workflow != LEGACY_WORKFLOW:
        profile = _resolve_actuator_profile(binding.workspace, row)
        if profile is not None:
            update["actuator_profile"] = profile
        profiles: dict[str, str] = {}
        for record in actuator_records(case):
            if PROFILE_VARIABLE in record:
                stem = record[PROFILE_VARIABLE]
                resolved_profile = _resolve_actuator_profile(binding.workspace, row, stem=stem)
                if resolved_profile is not None:
                    profiles[stem] = resolved_profile
        if profiles:
            update["actuator_profiles"] = profiles
    # G15: AND ITS CUSTOM FREE STREAM, a file of inputs/freestreams/, the
    # same way; a LEGACY row stating one is refused there, by name.
    freestream = _resolve_freestream(binding.workspace, row)
    if freestream is not None:
        update["freestream_profile"] = freestream
    # 0.32.0 (E2): AND ITS ACOUSTIC OBSERVER FILE, a file of inputs/acoustics/.
    observers = resolve_observers_file(
        binding.workspace.inputs_dir,
        row.variables,
        pol=row.pol,
        legacy=row.workflow == LEGACY_WORKFLOW,
    )
    if observers is not None:
        update["acoustic_observers_file"] = observers


def _bind_row_variables(
    binding: _Binding, case: SimCase, row: MatrixRow, update: dict[str, object]
) -> None:
    """Resolve motion origins, then apply the invocation's missing-family choice."""
    if row.motions:
        update["motions"] = [
            _bind_motion(binding.workspace, record, row.pol) for record in row.motions
        ]
    # THE FLAT ROW'S OWN HUB, bound the same way (PFS-2031.12): one rotor
    # is not less entitled to a named hub than two, and the name stays
    # beside the coordinates so the record says which point it was.
    flat_origin = row.variables.get("ROTOR_ORIGIN", "")
    if flat_origin and not _is_three_numbers(flat_origin):
        bound = _bind_motion(
            binding.workspace, {"ROTOR_ORIGIN": flat_origin}, row.pol, where="the row"
        )
        update["variables"] = {**case.variables, **bound}
    # THE INVOCATION'S OWN CHOICE, written onto the row's variables so
    # the builders read it like any other variable and never learn that
    # a command line exists (PFS-2035.13, the design of 2026-09-10).
    #
    # ONLY THE FALSE SIDE WRITES. At the default the case is left
    # byte-for-byte the case it was before this argument existed, which
    # is what keeps every recorded run's identity and every emitted
    # script unchanged; a variable written on both sides would have put
    # a new key into every campaign of the 0.14.0 comparison.
    if not binding.ignore_missing_families:
        stated = update.get("variables")
        base = stated if isinstance(stated, Mapping) else case.variables
        update["variables"] = {**base, IGNORE_MISSING_FAMILIES_VARIABLE: "false"}


def _bind_states(binding: _Binding, row: MatrixRow, update: dict[str, object]) -> None:
    """Resolve the row and each swept point against the bound reference length."""
    reference = binding.references[row.ref_code]
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
    if row.flight_condition or _derives_its_velocity(row):
        # A SWEPT FLOW VARIABLE IS RESOLVED PER POINT (0.21.0). The row's
        # own cell holds every value but the swept one, so on such a row
        # the row-level state is the FIRST point's and each point's own
        # rides on `point_states`. Resolving once would emit the first
        # point's Mach number, density and velocity at every point of the
        # sweep, which is the whole of what a Mach sweep must not do.
        diameter_m = _clock_rotor_diameter(row, reference)
        update["point_states"] = _states_per_point(
            row,
            reference_length_m=reference.chord_m,
            defaults=binding.setup_pins[row.set_code],
            defaults_origin=condition_defaults_origin(row.set_code),
            diameter_m=diameter_m,
        )
        resolved = resolve_flight_condition(
            _stated_at(row, next(row.sweep.points(), {}), diameter_m=diameter_m),
            pol=row.pol,
            reference_length_m=reference.chord_m,
            # PFS-2030.08: the fluid constants of the campaign live in
            # the setup the row names, and the row states what varies.
            # The origin travels as WORDS because the resolver never
            # reaches an artifact and its refusals have to name the
            # file the reader must open.
            defaults=binding.setup_pins[row.set_code],
            defaults_origin=condition_defaults_origin(row.set_code),
        )
        binding.conditions[row.pol] = resolved
        # The three the case already has fields for. The rest of the
        # state -- density, temperature, viscosity, the length it was
        # measured against and WHICH branch produced the density --
        # rides on `binding.conditions` rather than being flattened onto the
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


def _bind_rows(binding: _Binding) -> None:
    """Apply the row phases in order and bind setup ports after all row values."""
    for case, row in zip(binding.campaign.sims, binding.rows, strict=True):
        update = _row_update(binding, case, row)
        _bind_geometry(binding, row, update)
        _bind_profiles(binding, case, row, update)
        _bind_row_variables(binding, case, row, update)
        _bind_states(binding, row, update)
        if row.workflow != LEGACY_WORKFLOW:
            update["outputs"] = row_outputs(case.model_copy(update=update), row.workflow)
        binding.sims.append(
            _bind_setup_ports(case.model_copy(update=update), binding.workspace.inputs_dir)
        )
