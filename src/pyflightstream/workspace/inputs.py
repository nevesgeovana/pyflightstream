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
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

# InputArtifactError is DEFINED in `_errors`, below every layer, and
# re-exported here and from `pyflightstream.workspace`, which is the name
# a user catches and the one every docstring in this module names. It
# moved there on 2026-08-19 (OPS-2007.02.01) because the layers that bind
# a run matrix to this library catch it too, and reaching up for the type
# alone is what the five call-time imports of `cases/matrix.py` were.
# Nothing about the class changed: same two bases, same three attributes,
# same public spelling.
from pyflightstream._errors import InputArtifactError

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
    rotation : str
        Sense of rotation about the propeller axis, ``"clockwise"`` or
        ``"counterclockwise"``, viewed from behind the aircraft looking
        forward; record the convention with the geometry so the sign of
        the swirl is never guessed.
    """

    model_config = ConfigDict(extra="forbid")

    radius_m: float = Field(gt=0.0)
    hub_radius_m: float | None = Field(default=None, ge=0.0)
    n_blades: int = Field(ge=1)
    pitch_deg: float | None = None
    toe_deg: float | None = None
    position: PointXyz = Field(default_factory=PointXyz)
    rotation: Literal["clockwise", "counterclockwise"]


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
            "the id, not a prefix the library adds or strips.",
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
