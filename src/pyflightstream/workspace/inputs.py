"""Input-artifact library of the managed campaign workspace.

Pipeline role: organizes the reusable inputs of a campaign the same
way the workspace organizes its outputs. A support library under
``inputs/`` holds one declarative artifact per file, referenced by a
stable id (the file name stem), so a campaign line can select its
reference data, solver preset, boundary groups, geometry, and profile
by id instead of by path; the pattern is translated from the author's
research workflow. Artifacts are TOML, never executable code:
they are validated by pydantic models at load time and fail with a
didactic message naming the file and the available ids.

AN ID OF A CODED KIND DECLARES THAT KIND, since 2026-08-19
(PFS-2009.01, PFS-2009.03, a BREAK carried by v0.8.0). A reference id
begins with ``r``, a setup id with ``s``, a group id with ``e``, so
``r003``, ``s003`` and ``e003`` are three ids rather than one number
meaning three files. Before that, the three folders each held a
``003.toml`` and a number mistyped between the REF, SET and ENTRY
columns of a run matrix resolved to another artifact with no signal at
all. Geometries and profiles keep bare stems, because their ids are the
names of files the user staged and a letter rule there would refuse a
mesh for being called what it is called.

The library tree, created by ``CampaignWorkspace.init``:

- ``inputs/references/<id>.toml``: reference data for coefficient
  normalization and propeller description (SI units in the field
  names: m, m^2, deg). The id begins with ``r``.
- ``inputs/setups/<id>.toml``: a named solver-setup preset, a free
  key-value table for now; the loader keeps the raw table verbatim so
  a later formal solver-setup model can consume it unchanged. The id
  begins with ``s``.
- ``inputs/groups/<id>.toml``: named boundary groups, mapping a group
  name to a list of boundary labels or indices, stored verbatim. The id
  begins with ``e``, after the ENTRY column that carries it.
- ``inputs/geometries/``: staged geometry files of any extension,
  registered by file name; the id is the stem.
- ``inputs/profiles/``: input profile files (for example actuator
  thrust distributions), registered by file name.
- ``inputs/executables.toml``: the build registry, mapping a
  FlightStream build id to its executable path; an explicit override
  path bypasses the registry, and that override is the only way to run
  an unregistered build (the MANUAL mode of the run matrix).
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
)

# InputArtifactError is DEFINED in `_errors`, below every layer, and
# re-exported here and from `pyflightstream.workspace`, which is the name
# a user catches and the one every docstring in this module names. It
# moved there on 2026-08-19 (OPS-2007.02.01) because the layers that bind
# a run matrix to this library catch it too, and reaching up for the type
# alone is what the five call-time imports of `cases/matrix.py` were.
# Nothing about the class changed: same two bases, same three attributes,
# same public spelling.
from pyflightstream._errors import InputArtifactError

# DOWNWARD, and the one import in this module that leaves the workspace
# layer: `cases` sits below `workspace` in the house order, and the
# migration at the foot of this file has to rewrite the REF, SET and
# ENTRY cells of a run matrix in the same call that renames the library
# files. The matrix FORMAT is the cases layer's to own, so the cell
# rewrite is asked of it rather than reimplemented here, which is what
# would put a second reader of the pipe-delimited layout in the package
# (PFS-2009.03).
from pyflightstream.cases.matrix import CODE_COLUMNS, rewrite_codes

INPUT_KINDS = ("geometries", "references", "setups", "groups", "profiles")
EXECUTABLES_FILE = "executables.toml"

_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

#: The letter a coded artifact id begins with, so the id DECLARES its
#: kind and a mistyped number cannot resolve to another artifact's file.
#:
#: Only the three CODED kinds are here, and their absence from the other
#: two is the rule rather than an omission. A reference, a setup and a
#: group are addressed by ids the author writes in the REF, SET and ENTRY
#: cells of a run matrix, so a bare ``003`` names three different files
#: in three folders and a typo between them is silent. A geometry or a
#: profile is addressed by the STEM OF A FILE THE USER STAGED, so a
#: letter rule there would refuse a mesh for being called what it is
#: called.
#:
#: ``e`` for groups, not ``g``: the matrix column that carries a group id
#: is ENTRY, which is the word the author's own files use, and the letter
#: follows the column a user types rather than the model's class name.
KIND_LETTERS = {"reference": "r", "setup": "s", "group": "e"}

#: The library folder each coded kind lives in, for the refusal below.
_KIND_DIRECTORIES = {"reference": "references", "setup": "setups", "group": "groups"}

#: The matrix column that carries each coded kind's id. It is the pair
#: the migration walks: rename the file in the kind's folder AND rewrite
#: the cell of the column that names it, in the same call, because doing
#: one without the other is what half-resolves (PFS-2009.03).
KIND_COLUMNS = {"reference": "REF", "setup": "SET", "group": "ENTRY"}


class PointXyz(BaseModel):
    """One point in the simulation geometry reference frame, meters.

    Attributes
    ----------
    x_m : float
        X coordinate in m.
    y_m : float
        Y coordinate in m.
    z_m : float
        Z coordinate in m.
    """

    model_config = ConfigDict(extra="forbid")

    x_m: float = 0.0
    y_m: float = 0.0
    z_m: float = 0.0


class PropellerReference(BaseModel):
    """Propeller description block of a reference artifact.

    Attributes
    ----------
    radius_m : float
        Propeller tip radius in m; must be positive.
    hub_radius_m : float, optional
        Hub (root cutout) radius in m.
    n_blades : int
        Blade count; at least 1.
    pitch_deg : float, optional
        Blade pitch angle in deg.
    toe_deg : float, optional
        Toe (in-plane inclination) angle of the propeller axis in deg.
    position : PointXyz
        Hub position in the simulation geometry frame, m.
    rotation : {"clockwise", "counterclockwise"}
        Sense of rotation about the propeller axis, viewed from behind
        the aircraft looking forward. Record the convention with the
        geometry so the sign of the swirl is never guessed.
    blade_travel : {"inboard_up", "inboard_down"}, optional
        The SAME physical fact in the vocabulary a vendor datasheet
        usually prints: where the blade nearest the fuselage travels.

        It is a separate field rather than two more values of
        ``rotation`` because the two vocabularies are not
        interchangeable. This one is side-independent, so the left and
        the right propeller of a symmetric pair carry the same word,
        which is exactly why it cannot be converted to the
        viewed-from-behind sense without knowing which side this
        propeller is on. Keeping them apart makes "which vocabulary"
        a static fact of the field rather than something every consumer
        re-derives from a string.
    rpm_sign_installed : {-1, 1}, optional
        Measured sign of the rotor speed about the propeller's rotation
        axis, for the INSTALLED meshes of this configuration.
        Dimensionless. The axis is the one the case emits its rotary
        motion about and is a per-case argument, so this field states a
        sign and never an axis.
    rpm_sign_isolated : {-1, 1}, optional
        The same for the ISOLATED meshes, which are frequently the
        opposite hand of the installed ones and therefore take the
        opposite sign for the same published sense.

    Notes
    -----
    NOTHING IN THIS PACKAGE READS THE TWO SIGN FIELDS YET, and that is
    said here rather than left to be discovered. They are RECORDED, so a
    recipe that emits a rotor speed reads the artifact and applies the
    sign itself; setting one changes no emitted script on its own.

    THE SENSE DOES NOT DETERMINE THE SIGN OF THE ROTOR SPEED, which is
    why those fields exist and are not derived. Going from a published
    sense to the number a motion command takes needs the rotor axis, the
    side of the aircraft, and the handedness of the mesh actually
    loaded; a mirrored mesh of the same aircraft takes the opposite sign
    for the same published sense.

    Read that against
    :data:`pyflightstream.script.helpers.ROTATION_SENSE_SIGN`, which DOES
    derive a sign from a sense and is not contradicted here: it signs the
    AZIMUTH INCREMENT, which way round the disc the blades are numbered,
    and that is a different quantity from the sign of the rotor speed.
    Two different signs, one of them derivable and one of them measured.

    Both sign fields are optional, and absence means the campaign has not
    established them rather than that the sign is ``+1``. That promise is
    what closes them to COERCION as well as to value: ``true`` and
    ``1.0`` are refused rather than read as the integer ``1``, because a
    boolean that becomes a measured positive sign is the package
    deciding the physical fact this field exists to record. Without it
    the domain was also asymmetric in a way that modelled nothing:
    ``true`` was admitted as ``+1`` and ``false`` refused for being
    outside the domain.

    ``blade_travel`` and the two sign fields were added at 0.8.0
    (PFS-2009.02), after the shipped vocabulary was checked against a
    real campaign for the first time and refused that campaign's
    reference artifact on all three. ``rotation`` itself is unchanged,
    so an artifact written before 0.8.0 validates unaltered.
    """

    model_config = ConfigDict(extra="forbid")

    radius_m: float = Field(gt=0.0)
    hub_radius_m: float | None = Field(default=None, ge=0.0)
    n_blades: int = Field(ge=1)
    pitch_deg: float | None = None
    toe_deg: float | None = None
    position: PointXyz = Field(default_factory=PointXyz)
    rotation: Literal["clockwise", "counterclockwise"]
    blade_travel: Literal["inboard_up", "inboard_down"] | None = None
    rpm_sign_installed: Literal[-1, 1] | None = None
    rpm_sign_isolated: Literal[-1, 1] | None = None

    @field_validator("rpm_sign_installed", "rpm_sign_isolated", mode="before")
    @classmethod
    def _sign_is_an_integer_and_not_something_that_coerces_to_one(
        cls, value: object, info: ValidationInfo
    ) -> object:
        """Refuse a value that would become a sign nobody measured.

        Runs BEFORE the literal domain, so a value of the right type and
        the wrong magnitude still meets the domain's own message.
        """
        if value is None or type(value) is int:
            return value
        raise ValueError(
            f"{info.field_name} is {value!r}, of type {type(value).__name__}, and a "
            "measured sign is written as the integer 1 or -1. A boolean or a real "
            "number here would be coerced to a sign this campaign never measured, "
            "and an unmeasured sign is recorded by leaving the field out"
        )


class ReferenceArtifact(BaseModel):
    """Reference data of one configuration (``inputs/references/<id>.toml``).

    Attributes
    ----------
    area_m2 : float
        Reference area S_ref in m^2; must be positive.
    chord_m : float
        Reference chord c_ref in m; must be positive.
    span_m : float
        Reference span b_ref in m; must be positive.
    moment_point : PointXyz
        Moment reference point in the simulation geometry frame, m.
    propeller : PropellerReference, optional
        Propeller block, present for propulsive configurations.
    """

    model_config = ConfigDict(extra="forbid")

    area_m2: float = Field(gt=0.0)
    chord_m: float = Field(gt=0.0)
    span_m: float = Field(gt=0.0)
    moment_point: PointXyz = Field(default_factory=PointXyz)
    propeller: PropellerReference | None = None


class SetupArtifact(BaseModel):
    """A named solver-setup preset (``inputs/setups/<id>.toml``).

    The preset is a free key-value table for now: the file's top-level
    TOML table is kept verbatim in :attr:`settings`, so the future
    formal solver-setup model can consume the same raw table without a
    file format change.

    Attributes
    ----------
    settings : dict
        The raw TOML table of the preset, verbatim (keys are setting
        names, values are TOML scalars, arrays, or nested tables).
    """

    model_config = ConfigDict(extra="forbid")

    settings: dict[str, Any]


class GroupsArtifact(BaseModel):
    """Named boundary groups (``inputs/groups/<id>.toml``).

    Group members are stored verbatim as boundary labels (strings) or
    boundary indices (1-based integers, the FlightStream convention);
    the script layer resolves labels at emission time, so this model
    never interprets them.

    Attributes
    ----------
    groups : dict of str to list
        Mapping group name to its member boundary labels or indices.
    """

    model_config = ConfigDict(extra="forbid")

    groups: dict[str, list[int | str]]

    @field_validator("groups")
    @classmethod
    def _groups_have_members(cls, value: dict[str, list[int | str]]) -> dict:
        empty = sorted(name for name, members in value.items() if not members)
        if empty:
            raise ValueError(
                f"group(s) {', '.join(empty)} have no members; a named boundary "
                "group aggregates at least one boundary label or index"
            )
        return value


def available_ids(directory: Path, suffix: str | None = ".toml") -> list[str]:
    """List the artifact ids present in one library directory.

    Parameters
    ----------
    directory : Path
        One ``inputs/<kind>/`` directory.
    suffix : str, optional
        Restrict to files with this extension (default ``".toml"``);
        None lists every file (geometries and profiles register any
        extension).

    Returns
    -------
    list of str
        Sorted file name stems; empty when the directory is missing.
    """
    if not directory.is_dir():
        return []
    stems = {
        path.stem
        for path in directory.iterdir()
        if path.is_file() and (suffix is None or path.suffix == suffix)
    }
    return sorted(stems)


def _check_id(artifact_id: str, kind: str) -> None:
    """Refuse ids that could not have come from a library file name.

    Two rules, and the second applies to the coded kinds alone. An id is
    a file name stem, and a reference, setup or group id also DECLARES
    its kind with a leading letter (:data:`KIND_LETTERS`), so a number
    mistyped between the REF, SET and ENTRY cells of a run matrix is
    refused instead of resolving to another artifact's file.
    """
    if not _ID_PATTERN.match(artifact_id):
        raise InputArtifactError(
            f"{kind} id {artifact_id!r} is not a valid artifact id: ids are file "
            "name stems (letters, digits, dot, underscore, hyphen). The id selects "
            "a file inside the library; it is never a path.",
            kind=kind,
            artifact_id=artifact_id,
        )
    letter = KIND_LETTERS.get(kind)
    # Case-insensitive on purpose: the id is a file stem, and the two
    # spellings name the same file on a case-insensitive file system, so
    # refusing one of them would refuse a file that resolves.
    if letter is not None and artifact_id[:1].lower() != letter:
        directory = _KIND_DIRECTORIES[kind]
        raise InputArtifactError(
            f"{kind} id {artifact_id!r} does not declare its kind: a {kind} id begins "
            f"with {letter!r} (for example {letter}003), so a number mistyped between "
            "the REF, SET and ENTRY columns cannot resolve to another artifact's file. "
            f"Rename the library file to inputs/{directory}/{letter}{artifact_id}.toml "
            "and the matrix cell that names it in the same edit; the letter is part of "
            "the id, not a prefix the library adds or strips. A library written before "
            "v0.8.0 is migrated in ONE call rather than one rename per artifact: "
            "pyflightstream.workspace.migrate_input_ids(inputs_dir, matrices, "
            "apply=True) renames every file and rewrites the REF, SET and ENTRY cells "
            "of the matrices you hand it, together.",
            kind=kind,
            artifact_id=artifact_id,
        )


def _miss(
    kind: str, artifact_id: str, directory: Path, suffix: str | None = ".toml"
) -> InputArtifactError:
    """Build the didactic not-found refusal listing what exists.

    Returns the exception (structured: kind, artifact_id, available)
    instead of a bare message, so every miss site raises with the same
    attributes.
    """
    ids = available_ids(directory, suffix)
    if ids:
        listing = f"available {kind} ids: {', '.join(ids)}"
    else:
        listing = (
            f"the library directory {directory} holds no {kind} artifacts yet "
            "(create it with CampaignWorkspace.init or pyfs-workspace init, then "
            "add the artifact file)"
        )
    return InputArtifactError(
        f"no {kind} artifact with id {artifact_id!r}; {listing}",
        kind=kind,
        artifact_id=artifact_id,
        available=tuple(ids),
    )


def _load_toml(path: Path, kind: str) -> dict[str, Any]:
    """Read one TOML artifact file, naming the file on a syntax error."""
    try:
        with open(path, "rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as error:
        raise InputArtifactError(
            f"the {kind} artifact {path} is not valid TOML: {error}. Artifacts are "
            "declarative TOML files, one artifact per file."
        ) from error


def _validate(model: type[BaseModel], data: dict[str, Any], path: Path, kind: str) -> BaseModel:
    """Validate one artifact table, naming the file on a model error."""
    try:
        return model.model_validate(data)
    except ValidationError as error:
        raise InputArtifactError(
            f"the {kind} artifact {path} does not validate: {error}"
        ) from error


def resolve_reference(inputs_dir: Path, artifact_id: str) -> ReferenceArtifact:
    """Load the reference artifact one id names.

    Parameters
    ----------
    inputs_dir : Path
        The workspace ``inputs/`` directory.
    artifact_id : str
        File name stem under ``references/``.

    Returns
    -------
    ReferenceArtifact
        The validated reference data (SI units in the field names).

    Raises
    ------
    InputArtifactError
        Unknown id (the message lists the available ids) or a file
        that does not validate.
    """
    _check_id(artifact_id, "reference")
    directory = Path(inputs_dir) / "references"
    path = directory / f"{artifact_id}.toml"
    if not path.is_file():
        raise _miss("reference", artifact_id, directory)
    data = _load_toml(path, "reference")
    return _validate(ReferenceArtifact, data, path, "reference")


def resolve_setup(inputs_dir: Path, artifact_id: str) -> SetupArtifact:
    """Load the solver-setup preset one id names.

    The file's top-level table is kept verbatim in
    :attr:`SetupArtifact.settings`; see the module docstring for why.

    Parameters
    ----------
    inputs_dir : Path
        The workspace ``inputs/`` directory.
    artifact_id : str
        File name stem under ``setups/``.

    Returns
    -------
    SetupArtifact
        The preset with its raw settings table.

    Raises
    ------
    InputArtifactError
        Unknown id (the message lists the available ids) or invalid
        TOML.
    """
    _check_id(artifact_id, "setup")
    directory = Path(inputs_dir) / "setups"
    path = directory / f"{artifact_id}.toml"
    if not path.is_file():
        raise _miss("setup", artifact_id, directory)
    data = _load_toml(path, "setup")
    return _validate(SetupArtifact, {"settings": data}, path, "setup")


def resolve_group(inputs_dir: Path, artifact_id: str) -> GroupsArtifact:
    """Load the named boundary groups one id names.

    Parameters
    ----------
    inputs_dir : Path
        The workspace ``inputs/`` directory.
    artifact_id : str
        File name stem under ``groups/``.

    Returns
    -------
    GroupsArtifact
        The validated groups, members stored verbatim.

    Raises
    ------
    InputArtifactError
        Unknown id (the message lists the available ids) or a file
        that does not validate.
    """
    _check_id(artifact_id, "group")
    directory = Path(inputs_dir) / "groups"
    path = directory / f"{artifact_id}.toml"
    if not path.is_file():
        raise _miss("group", artifact_id, directory)
    data = _load_toml(path, "group")
    return _validate(GroupsArtifact, {"groups": data}, path, "group")


def _resolve_file(inputs_dir: Path, kind: str, subdir: str, artifact_id: str) -> Path:
    """Resolve a file artifact (geometry or profile) registered by stem."""
    _check_id(artifact_id, kind)
    directory = Path(inputs_dir) / subdir
    matches = sorted(
        path
        for path in (directory.iterdir() if directory.is_dir() else [])
        if path.is_file() and path.stem == artifact_id
    )
    if not matches:
        raise _miss(kind, artifact_id, directory, suffix=None)
    if len(matches) > 1:
        names = ", ".join(path.name for path in matches)
        raise InputArtifactError(
            f"{kind} id {artifact_id!r} matches {len(matches)} files ({names}); the "
            "id is the file name stem and must be unique within the library, so "
            "rename or remove the extras."
        )
    return matches[0]


def resolve_geometry(inputs_dir: Path, artifact_id: str) -> Path:
    """Resolve the staged geometry file one id names.

    Geometries register by file name (any extension); the id is the
    stem, so ``resolve_geometry(inputs_dir, "wing_v2")`` finds
    ``inputs/geometries/wing_v2.fsm``.

    Parameters
    ----------
    inputs_dir : Path
        The workspace ``inputs/`` directory.
    artifact_id : str
        File name stem under ``geometries/``.

    Returns
    -------
    Path
        The geometry file.

    Raises
    ------
    InputArtifactError
        Unknown id (the message lists the available ids) or an
        ambiguous stem shared by several files.
    """
    return _resolve_file(inputs_dir, "geometry", "geometries", artifact_id)


def resolve_profile(inputs_dir: Path, artifact_id: str) -> Path:
    """Resolve the input profile file one id names.

    Profiles (for example actuator thrust distributions) register by
    file name; the id is the stem.

    Parameters
    ----------
    inputs_dir : Path
        The workspace ``inputs/`` directory.
    artifact_id : str
        File name stem under ``profiles/``.

    Returns
    -------
    Path
        The profile file.

    Raises
    ------
    InputArtifactError
        Unknown id (the message lists the available ids) or an
        ambiguous stem shared by several files.
    """
    return _resolve_file(inputs_dir, "profile", "profiles", artifact_id)


def resolve_executable(inputs_dir: Path, build_id: str, override: str | Path | None = None) -> Path:
    """Resolve the FlightStream executable of one build id.

    Two explicit modes, translated from the run matrix's MANUAL pattern:

    - Registry mode (default): the build id must exist in
      ``inputs/executables.toml``, a top-level TOML table mapping build
      ids to executable paths.
    - Override mode: an explicit ``override`` path wins over the
      registry and is the only way to run an unregistered build; it is
      never guessed from the environment.

    Existence of the executable is checked by the executor at
    construction (so campaigns can be authored away from the licensed
    machine), not here.

    Parameters
    ----------
    inputs_dir : Path
        The workspace ``inputs/`` directory.
    build_id : str
        Build identifier key of the registry, for example ``"26.120"``.
    override : str or Path, optional
        Explicit executable path bypassing the registry.

    Returns
    -------
    Path
        The executable path.

    Raises
    ------
    InputArtifactError
        Registry file missing, or build id not registered (the message
        lists the registered build ids and the override mode).
    """
    if override is not None:
        return Path(override)
    registry_path = Path(inputs_dir) / EXECUTABLES_FILE
    if not registry_path.is_file():
        raise InputArtifactError(
            f"no executable registry at {registry_path}; register builds as "
            '"<build_id>" = "<path>" entries in that TOML file, or pass the '
            "explicit override path. The executable is always explicit input, "
            "never guessed."
        )
    table = _load_toml(registry_path, "executables")
    entry = table.get(build_id)
    if entry is None:
        registered = sorted(key for key in table if isinstance(table[key], str))
        listing = ", ".join(registered) if registered else "none yet"
        raise InputArtifactError(
            f"build id {build_id!r} is not in the executable registry "
            f"{registry_path} (registered: {listing}); add it there, or pass the "
            "explicit override path to run an unregistered build."
        )
    if not isinstance(entry, str):
        raise InputArtifactError(
            f"the registry entry for build {build_id!r} in {registry_path} must be "
            f"a path string, got {type(entry).__name__}; write "
            f'"{build_id}" = "C:/path/to/FlightStream.exe"'
        )
    return Path(entry)


@dataclass(frozen=True)
class IdMigration:
    """What a kind-letter migration renamed and rewrote, or would.

    Attributes
    ----------
    renames : tuple of (Path, Path)
        Library files to rename, source then destination, sorted by
        source. Empty for a library already migrated, which is a
        legitimate outcome and not an error.
    cells : dict of str to dict of str to int
        Per matrix (as given, stringified) and per column, how many
        cells the rewrite changed. A matrix that names no migrated id
        appears with zeros rather than being dropped, so a caller can
        tell "this matrix was looked at and nothing matched" from "this
        matrix was never read".
    applied : bool
        Whether the plan was carried out. False is the dry run.
    """

    renames: tuple[tuple[Path, Path], ...]
    cells: dict[str, dict[str, int]]
    applied: bool

    @property
    def is_empty(self) -> bool:
        """True when nothing would move: no rename and no changed cell."""
        return not self.renames and not any(
            count for columns in self.cells.values() for count in columns.values()
        )


def _rename_plan(inputs_dir: Path) -> tuple[list[tuple[Path, Path]], dict[str, dict[str, str]]]:
    """Plan the renames of one library, and the cell mapping they imply.

    A file whose stem already begins with its kind's letter is left
    alone; it is already an id of the new form. Matching is
    case-insensitive for the same reason :func:`_check_id` is: the id is
    a file stem and two spellings name one file on a case-insensitive
    file system.
    """
    renames: list[tuple[Path, Path]] = []
    mapping: dict[str, dict[str, str]] = {column: {} for column in CODE_COLUMNS}
    for kind, letter in KIND_LETTERS.items():
        directory = inputs_dir / _KIND_DIRECTORIES[kind]
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if not path.is_file() or path.suffix != ".toml":
                continue
            old = path.stem
            if old[:1].lower() == letter:
                continue
            new = f"{letter}{old}"
            renames.append((path, path.with_name(f"{new}{path.suffix}")))
            mapping[KIND_COLUMNS[kind]][old] = new
    return renames, mapping


def migrate_input_ids(
    inputs_dir: str | Path,
    matrices: Sequence[str | Path] = (),
    *,
    apply: bool = False,
) -> IdMigration:
    r"""Give every coded library id its kind letter, and move the matrices with it.

    A reference, setup or group id declares its kind with a leading
    letter since v0.8.0 (:data:`KIND_LETTERS`, PFS-2009.01), so a library
    written before that break holds files no id can reach and matrices
    whose REF, SET and ENTRY cells name ids the library refuses. This
    performs BOTH halves of the repair IN ONE CALL, which is the whole
    safety property: renaming the files without rewriting the cells, or
    the other way round, leaves a corpus that half-resolves, and half of
    it silently.

    Nothing is written until every step is known to be possible. A
    rename onto an existing file, a matrix that is missing, and a matrix
    at any other layout are all refused with the library and the
    matrices untouched, so a refused migration is a no-op rather than a
    half-done one.

    Parameters
    ----------
    inputs_dir : str or Path
        The workspace ``inputs/`` directory
        (:attr:`~pyflightstream.workspace.CampaignWorkspace.inputs_dir`).
    matrices : sequence of str or Path
        Every run matrix whose cells name ids of this library. It
        defaults to none, and passing none is a real choice rather than
        an oversight: a library with no matrix beside it still migrates,
        and this signature makes the omission visible in the call.
    apply : bool
        Carry the plan out. Keyword-only and False by default, so the
        call that finds out what would happen cannot be the call that
        does it.

    Returns
    -------
    IdMigration
        The renames and the per-column cell counts, with ``applied``
        saying whether they happened.

    Raises
    ------
    InputArtifactError
        A rename would land on a file that already exists, or a named
        matrix does not exist. Both are refused before anything is
        written.
    pyflightstream.cases.matrix.MatrixError
        A named matrix does not read at the verified layout. Also
        refused before anything is written.

    Examples
    --------
    >>> from pyflightstream.workspace import CampaignWorkspace, migrate_input_ids
    >>> workspace = CampaignWorkspace("campaign")            # doctest: +SKIP
    >>> plan = migrate_input_ids(                            # doctest: +SKIP
    ...     workspace.inputs_dir, ["matrix.fs"]
    ... )
    >>> [(old.name, new.name) for old, new in plan.renames]  # doctest: +SKIP
    [('003.toml', 'r003.toml')]
    >>> migrate_input_ids(                                   # doctest: +SKIP
    ...     workspace.inputs_dir, ["matrix.fs"], apply=True
    ... ).applied
    True
    """
    inputs = Path(inputs_dir)
    renames, mapping = _rename_plan(inputs)
    collisions = [(old, new) for old, new in renames if new.exists()]
    if collisions:
        listing = "; ".join(f"{old.name} -> {new.name} in {new.parent}" for old, new in collisions)
        raise InputArtifactError(
            f"{len(collisions)} rename(s) would land on a file that already exists: "
            f"{listing}. Nothing was renamed and no matrix was rewritten. Both files "
            "answer to one id once the letter is added, so the migration cannot say "
            "which artifact a matrix cell means; open the pair, decide which one the "
            "campaign uses, and give the other a distinct id first."
        )
    missing = [str(path) for path in matrices if not Path(path).is_file()]
    if missing:
        raise InputArtifactError(
            f"matrix file(s) {', '.join(missing)} do not exist, so their REF, SET and "
            "ENTRY cells cannot be rewritten. Nothing was renamed: renaming the "
            "library while a matrix that names it stays behind is exactly the "
            "half-resolving state this migration exists to prevent."
        )
    # DRY FIRST, every matrix, before a single byte moves. rewrite_codes
    # refuses a wrong layout or a malformed row, and finding that out
    # after the library has been renamed would leave the corpus split.
    rewritten: dict[str, bytes] = {}
    cells: dict[str, dict[str, int]] = {}
    for path in matrices:
        text, counts = rewrite_codes(path, mapping)
        rewritten[str(path)] = text
        cells[str(path)] = counts
    if apply:
        for old, new in renames:
            old.rename(new)
        for name, text in rewritten.items():
            Path(name).write_bytes(text)
    return IdMigration(renames=tuple(renames), cells=cells, applied=apply)
