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
begins with ``r``, a setup id with ``s``, a pproc id with ``p`` (``e``
until 0.11.0, when the groups artifact became the post-processing
artifact, PFS-2029.07), so ``r003``, ``s003`` and ``p003`` are three ids
rather than one number meaning three files. Before that, the three
folders each held a ``003.toml`` and a number mistyped between the REF,
SET and PPROC columns of a run matrix resolved to another artifact with
no signal at all. A geometry is named by its file name with the
extension (PFS-2029.09) and a profile by its stem, because their ids are
the names of files the user staged and a letter rule there would refuse
a mesh for being called what it is called.

The library tree, created by ``CampaignWorkspace.init``:

- ``inputs/references/<id>.toml``: reference data for coefficient
  normalization and rotor description (SI units in the field
  names: m, m^2, deg). The id begins with ``r``.
- ``inputs/setups/<id>.toml``: a named solver-setup preset, a free
  key-value table for now; the loader keeps the raw table verbatim so
  a later formal solver-setup model can consume it unchanged. The id
  begins with ``s``.
- ``inputs/pproc/<id>.toml``: the post-processing artifact (PFS-2029.07),
  six optional tables: ``[groups]`` maps a group name to the families it
  aggregates, ``[exports]`` selects the export kinds, ``[sections]``,
  ``[plots]`` and ``[probes]`` are the solver definitions, ``[products]``
  says which files are written after the run. The id begins with ``p``,
  after the PPROC column that carries it; ``pyfs-matrix upgrade --inputs``
  moves a groups library (``inputs/groups/e<id>.toml``) here.
- ``inputs/geometries/``: staged geometry files of any extension,
  registered by file name; the id is the stem. A geometry sits either
  directly in the folder (the flat layout) or in one subfolder named by
  its stem, ``geometries/30_WB/30_WB.fsm``, with its boundary inventory
  and provenance record beside it (PFS-2032.04, since 0.13.0); the cell
  says ``30_WB.fsm`` in both cases, the folder is read first, and
  :func:`migrate_geometry_layout` moves a flat library into folders.
- ``inputs/profiles/``: input profile files (for example actuator
  thrust distributions), registered by file name.
- ``inputs/executables.toml``: the build registry, mapping a
  FlightStream build id to its executable path; an explicit override
  path bypasses the registry, and that override is the only way to run
  an unregistered build (the MANUAL mode of the run matrix). An entry
  is a bare path string, or a table carrying that path and, optionally,
  the FlightStream version the build's scripts are emitted under
  (:func:`resolve_build`).
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePath, PurePosixPath
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
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
from pyflightstream._fsm import MeshReadError, boundary_names
from pyflightstream._retired_names import (
    BLOCK_KIND_ENGINE,
    POINT_KIND_ENGINE,
    retired_key,
)
from pyflightstream.cases import (
    BoundaryAliases,
    CustomFlag,
    FrameSpec,
    PprocSpec,
    RawCommand,
    RotorBlock,
)

# DOWNWARD, and the two imports in this module that leave the workspace
# layer: `cases` sits below `workspace` in the house order, and the
# migration at the foot of this file has to rewrite the REF, SET and
# ENTRY cells of a run matrix in the same call that renames the library
# files. The matrix FORMAT is the cases layer's to own, so the cell
# rewrite is asked of it rather than reimplemented here, which is what
# would put a second reader of the pipe-delimited layout in the package
# (PFS-2009.03).
from pyflightstream.cases.matrix import CODE_COLUMNS, rewrite_codes

# DOWNWARD as well, and the lowest layer of the stack: `versions` sits
# below `commands`, which sits below everything else. It is imported so a
# version DECLARED in the build registry is checked against the version
# registry at the moment it is read, rather than at the moment a run
# emits a script under it. The sister module `wake_edges` already reaches
# down to `commands` for the same kind of reason (PFS-2009.05).
from pyflightstream.versions import (
    AmbiguousVersionAliasError,
    UnknownVersionError,
    resolve,
)

INPUT_KINDS = ("geometries", "references", "setups", "pproc", "profiles")
EXECUTABLES_FILE = "executables.toml"
#: This machine's overlay of the build registry (PFS-2031.15). A workspace
#: kept in version control carries placeholder paths in the registry,
#: because where a solver is installed is machine configuration; the
#: overlay beside it, gitignored, supplies the real path of a build id. A
#: bare path keeps the committed entry's declared version, a table replaces
#: the entry, and a build id the overlay is silent on reads as committed.
LOCAL_EXECUTABLES_FILE = "executables.local.toml"

#: Every key a TABLE-valued entry of the build registry carries, and the
#: only ones read. A key outside this tuple is REFUSED naming itself
#: rather than ignored: a silently dropped ``verison`` leaves a registry
#: that looks correct and a run emitted under the campaign default, and
#: the two look identical from the manifest (PFS-2009.05).
EXECUTABLE_ENTRY_KEYS = ("path", "version")

_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

#: The letter a coded artifact id begins with, so the id DECLARES its
#: kind and a mistyped number cannot resolve to another artifact's file.
#:
#: Only the three CODED kinds are here, and their absence from the other
#: two is the rule rather than an omission. A reference, a setup and a
#: pproc artifact are addressed by ids the author writes in the REF, SET
#: and PPROC cells of a run matrix, so a bare ``003`` names three
#: different files in three folders and a typo between them is silent. A
#: geometry is addressed by the NAME OF A FILE THE USER STAGED and a
#: profile by its stem, so a letter rule there would refuse a mesh for
#: being called what it is called.
#:
#: ``p`` for pproc since 0.11.0: until then the artifact was the groups
#: file under ``e``, after the ENTRY column that carried it, and
#: ``pyfs-matrix upgrade --inputs`` renames both the file and the cell.
KIND_LETTERS = {"reference": "r", "setup": "s", "pproc": "p"}

#: The library folder each coded kind lives in, for the refusal below.
_KIND_DIRECTORIES = {"reference": "references", "setup": "setups", "pproc": "pproc"}

#: The matrix column that carries each coded kind's id. It is the pair
#: the migration walks: rename the file in the kind's folder AND rewrite
#: the cell of the column that names it, in the same call, because doing
#: one without the other is what half-resolves (PFS-2009.03).
KIND_COLUMNS = {"reference": "REF", "setup": "SET", "pproc": "PPROC"}


#: THE RETIRED POINT KIND, held as a named constant rather than as a
#: literal inside the guard. A word sweep rewrote the literal into the
#: word the guard now REQUIRES, so the refusal fired on every correct
#: file and on no wrong one; nothing failed, because a guard that
#: refuses everything and a guard that refuses the right thing look
#: alike from a suite that only writes correct files.
POINT_KIND_ENGINE_WORD = "engine"

#: What a reference point may declare itself to be (PFS-2029.11.02).
#: It was ``engine`` until 0.15.0; see :mod:`pyflightstream._retired_names`.
#: The word sweep rewrote the OLD spelling here into the new one, which is
#: the failure the comment above it was written to prevent, committed in
#: the file that records it (the interface lens of the release review).
POINT_KINDS = ("rotor", "airframe")


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
    kind : str or None
        What the point is, ``rotor`` or ``airframe`` (PFS-2029.11.02),
        stated so that a motion built on it is a decision the file shows
        and not a side effect of the name's radical; None leaves the
        convention to say (``ERP`` is a rotor, ``ARP`` the airframe).
    """

    model_config = ConfigDict(extra="forbid")
    kind: str | None = None

    @field_validator("kind")
    @classmethod
    def _kind_is_known(cls, value: str | None) -> str | None:
        # THE RETIRED SPELLING FIRST, because it is the likeliest wrong
        # value in an existing workspace and the generic refusal below
        # would send its author looking for a kind that never existed.
        if value == POINT_KIND_ENGINE_WORD:
            raise ValueError(POINT_KIND_ENGINE.message())
        if value is not None and value not in POINT_KINDS:
            raise ValueError(
                f"kind={value!r} names no point kind; a reference point is one of "
                f"{', '.join(POINT_KINDS)}"
            )
        return value

    x_m: float = 0.0
    y_m: float = 0.0
    z_m: float = 0.0


class RotorReference(BaseModel):
    """The recorded rotor of a reference artifact (``[rotor]``).

    Attributes
    ----------
    radius_m : float, optional
        Rotor radius. Optional since 0.11.0 (PFS-2029.05): the diameter
        at the artifact's root is the length the package reads, and a
        radius stated beside it must be half of it.
    hub_radius_m : float, optional
        Hub radius.
    n_blades : int
        The RESOLVED blade count of the mesh a row opens, not the physical
        one: a periodic sector meshing one blade states 1 and the row's
        symmetry supplies the wheel.
    pitch_deg, toe_deg : float, optional
        Recorded installation angles; read by nothing in the package.
    position : PointXyz
        The rotor position, the one field of this block a builder
        reads: the two unsteady run types turn it into the ROTOR_MRP frame
        (PFS-2030.03), the frame the author's probe lines and rotor plots
        are defined in and the frame a rotor row turns about unless it
        states ``ROTOR_ORIGIN``.

    Notes
    -----
    THE FOUR ROTOR FACTS LEFT THIS BLOCK AT 0.11.0 (PFS-2029.08):
    ``rotation``, ``blade_travel``, ``rpm_sign_installed`` and
    ``rpm_sign_isolated`` were recorded here from 0.8.0 to 0.10.1 and read
    by no builder, while the row states what a script needs: the sign of
    the rotor speed is the sign of ``RPM`` (or ``RPM_SIGN`` beside
    ``ADVANCE_RATIO``) and the axis is ``ROTOR_AXIS``. A file still
    carrying them is refused naming those row keys, and ``pyfs-matrix
    upgrade --inputs`` strips them; the measured argument that related
    the datasheet's sense of rotation to the sign about the rotor axis is
    kept on ``docs/mesh-inputs.md``, where a reader setting up a new rotor
    finds it.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    radius_m: float | None = Field(default=None, gt=0.0)
    hub_radius_m: float | None = Field(default=None, ge=0.0)
    n_blades: int = Field(ge=1)
    pitch_deg: float | None = None
    toe_deg: float | None = None
    position: PointXyz = Field(default_factory=PointXyz)

    @model_validator(mode="before")
    @classmethod
    def _the_rotor_facts_live_on_the_row(cls, data: object) -> object:
        """Refuse the four facts the row states now, naming the keys that carry them."""
        if not isinstance(data, Mapping):
            return data
        found = [key for key in ROTOR_FACT_KEYS if key in data]
        if not found:
            return data
        raise ValueError(
            f"the rotor block states {', '.join(found)}, which the reference artifact "
            "carried until 0.11.0 and no builder read. The row states what a script "
            "needs: the sign of the rotor speed is the sign of RPM (or RPM_SIGN beside "
            "ADVANCE_RATIO) and the axis is ROTOR_AXIS (PFS-2029.08). Drop the key(s), or "
            "call pyflightstream.workspace.strip_rotor_facts on the inputs directory, which "
            "strips them from every reference artifact (`pyfs-matrix upgrade` does the same "
            "with in_place (CLI: --in-place) and inputs (CLI: --inputs)); the measured "
            "argument behind them is on docs/mesh-inputs.md."
        )


#: The four facts a reference artifact's rotor block carried from 0.8.0
#: to 0.10.1 and states no more (PFS-2029.08).
ROTOR_FACT_KEYS: tuple[str, ...] = (
    "rotation",
    "blade_travel",
    "rpm_sign_installed",
    "rpm_sign_isolated",
)


def strip_rotor_facts(inputs_dir: Path) -> dict[str, list[str]]:
    """Remove the four rotor facts from every reference artifact, textually.

    PFS-2029.08, the ``--inputs`` half of ``pyfs-matrix upgrade``. Each line
    of ``inputs/references/*.toml`` whose key is one of
    :data:`ROTOR_FACT_KEYS` is removed, comments and every other line
    staying as written, so the diff a reader sees is the four lines and
    nothing else. Returns, per file, the keys removed; a file carrying
    none is not rewritten.
    """
    directory = Path(inputs_dir) / "references"
    removed: dict[str, list[str]] = {}
    if not directory.is_dir():
        return removed
    key_line = re.compile(r"^\s*(" + "|".join(ROTOR_FACT_KEYS) + r")\s*=")
    for path in sorted(directory.glob("*.toml")):
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        kept, gone = [], []
        for line in lines:
            match = key_line.match(line)
            if match:
                gone.append(match.group(1))
            else:
                kept.append(line)
        if gone:
            path.write_text("".join(kept), encoding="utf-8")
            removed[path.name] = gone
    return removed


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
    rotor_diameter_m : float, optional
        Rotor diameter D in m; must be positive.

        IT LIVES HERE, BESIDE THE OTHER THREE LENGTHS, and not in
        :class:`RotorReference`, which is the natural-looking home
        and the wrong one. The rotor block is RECORDED metadata of which
        this package reads one field, the position (0.11.0, the ROTOR_MRP
        frame); the diameter is a DIVISOR of
        published numbers, exactly like the area and the chord. It sets
        the rotor speed a row asks for by advance ratio
        (``n = V / (J D)``) and it normalises the rotor coefficients
        (``C_T = T / (rho n^2 D^4)``). A quantity a run is computed FROM
        belongs with the reference lengths, where a reader looking for
        "what were the coefficients divided by" finds all of them in one
        place.

        Optional because a configuration with no rotor has no
        diameter, and stating a placeholder would be worse than stating
        nothing. A row asking for an advance ratio without it is refused
        naming this field.
    moment_point : PointXyz
        Moment reference point in the simulation geometry frame, m.
    rotor : RotorReference, optional
        Rotor block, present for propulsive configurations.
    """

    model_config = ConfigDict(extra="forbid")

    area_m2: float = Field(gt=0.0)
    chord_m: float = Field(gt=0.0)
    span_m: float = Field(gt=0.0)
    rotor_diameter_m: float | None = Field(default=None, gt=0.0)
    moment_point: PointXyz = Field(default_factory=PointXyz)
    rotor: RotorReference | None = None
    #: The boundary aliases the ``[aliases]`` table declares (FR-59, the author's
    #: design of 2026-09-10). They lived in the setup preset at 0.14.0,
    #: which is per condition where this artifact is per configuration; a
    #: boundary name is not a solver setting. A member may be another
    #: alias, resolved to the end by
    #: :func:`pyflightstream.cases.resolve_alias`. Every rotor block's own
    #: name is added here by :func:`resolve_reference`, standing for
    #: everything that rotor owns.
    aliases: BoundaryAliases = Field(default_factory=dict)
    #: The custom coordinate systems the ``[[frames]]`` table defines
    #: (FR-72), in the order written. They lived in the setup preset at
    #: 0.14.0; a coordinate system is geometric data, and the frames a
    #: rotor instantiates were always derived from this file.
    frames: list[FrameSpec] = Field(default_factory=list)
    #: One entry per rotor, keyed by the block's name, read out of every
    #: top-level table whose ``kind`` is ``rotor`` (FR-60). THE KEY EQUALS
    #: :attr:`~pyflightstream.cases.RotorBlock.alias`, which is the word a
    #: row moves, so a caller iterating this mapping may use either.
    rotors: dict[str, RotorBlock] = Field(default_factory=dict)
    #: The named points of the configuration that are NOT rotors, keyed by
    #: the block's name: today the airframe point a configuration writes
    #: beside its rotors.
    #:
    #: NOTHING READS THIS YET, and that is stated rather than left for a
    #: reader to discover. A row resolving a point by name resolves it
    #: against ``inputs/reference_points.toml``
    #: (:meth:`CampaignWorkspace.reference_point`), which is the file every
    #: refusal names. The field exists so that a reference carrying its
    #: airframe point beside its rotors is READ rather than refused, which
    #: is how the author writes one; which of the two files owns a named
    #: point is the author's question of 2026-09-10 and is not answered here.
    points: dict[str, PointXyz] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _one_rotor_length(self) -> ReferenceArtifact:
        """Refuse a radius that disagrees with the diameter, or stands alone.

        PFS-2029.05. ``rotor_diameter_m`` is the length the package
        reads; ``rotor.radius_m`` is optional and, when stated, must be
        half of it, so a file cannot carry two rotors. A radius with no
        diameter is refused naming the key that carries the fact.
        """
        rotor = self.rotor
        if rotor is None or rotor.radius_m is None:
            return self
        diameter = self.rotor_diameter_m
        if diameter is None:
            raise ValueError(
                f"[rotor] states radius_m = {rotor.radius_m} and the artifact "
                "states no rotor_diameter_m. The diameter is the length this package "
                "reads (the advance ratio, the probe lines), so state "
                f"rotor_diameter_m = {2 * rotor.radius_m} at the top level; the "
                "radius may then be dropped."
            )
        if abs(diameter - 2 * rotor.radius_m) > 1e-9 * max(1.0, diameter):
            raise ValueError(
                f"rotor_diameter_m = {diameter} and [rotor] radius_m = "
                f"{rotor.radius_m} disagree: twice the radius is "
                f"{2 * rotor.radius_m}. One rotor has one length; fix one of "
                "the two, or drop the radius, which the package does not read."
            )
        return self


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
    #: The custom coordinate systems the ``[[frames]]`` table defines
    #: (PFS-2034.01), in the order written; consumed out of ``settings``
    #: by :func:`resolve_setup` so the solver-setting loop never sees them.
    #:
    #: DEPRECATED SINCE 0.15.0 (FR-72): the table's home is the REFERENCE
    #: artifact, because a coordinate system is geometric data. A preset
    #: still stating it is read with a warning and the reference wins; the
    #: preset stops being read for it at 0.17.0.
    frames: list[FrameSpec] = Field(default_factory=list)
    #: The solver commands the ``[[raw]]`` table states verbatim
    #: (PFS-2033.01), each before a named phase, in the order written;
    #: consumed out of ``settings`` by :func:`resolve_setup` the same way.
    raw_commands: list[RawCommand] = Field(default_factory=list)
    #: The custom flags the ``[[flags]]`` table declares (PFS-2035.20),
    #: in the order written; consumed out of ``settings`` by
    #: :func:`resolve_setup` the way the raw table is, so the loop that
    #: refuses a key naming no solver setting never meets it.
    #:
    #: A FLAG IS NOT A RAW LINE. A raw entry is a whole command with its
    #: arguments, fixed here, so every row citing this preset emits the
    #: same one; a flag names the command and the ROW states the value,
    #: so one preset serves a sweep over it. That is what leaves RAW to
    #: the particular case it is named for.
    flags: list[CustomFlag] = Field(default_factory=list)
    #: The boundary aliases the ``[aliases]`` table defines (the author's decision
    #: of 2026-09-09): a name to the boundary names or families it stands
    #: for, read wherever a boundary is cited (a matrix cell, a pproc
    #: group, a families entry), a member the mesh lacks ignored; consumed
    #: out of ``settings`` by :func:`resolve_setup` the same way.
    #:
    #: DEPRECATED SINCE 0.15.0 (FR-59): the table's home is the REFERENCE
    #: artifact, which is per configuration where a preset is per
    #: condition. A preset still stating it is read with a warning and the
    #: reference wins; the preset stops being read for it at 0.17.0.
    aliases: BoundaryAliases = Field(default_factory=dict)

    @model_validator(mode="after")
    def _one_frame_per_name(self) -> SetupArtifact:
        seen: set[str] = set()
        for frame in self.frames:
            key = frame.name.strip().upper()
            if key in seen:
                raise ValueError(
                    f"the frame name {frame.name!r} is defined twice; one definition per name"
                )
            seen.add(key)
        return self


#: The table of a setup artifact that defines custom coordinate systems
#: (PFS-2034.01): ``[[frames]]``, one entry per frame with ``name``,
#: ``origin`` and optionally ``x_axis`` and ``y_axis``. The name is read
#: by the goal checker of 0.14.0 and by the documentation; change it here
#: and both follow.
FRAMES_TABLE = "frames"
#: The table of a setup artifact that states solver commands verbatim
#: (PFS-2033.01): ``[[raw]]``, one entry per line with ``command`` and
#: ``before``. Read by the goal checker of 0.14.0 and the documentation.
RAW_TABLE = "raw"

#: The table a setup preset declares its custom flags in (PFS-2035.20).
#: One record per flag: the word a matrix row writes, and the
#: FlightStream command it becomes.
FLAGS_TABLE = "flags"
#: The table of a setup artifact that names groups of boundaries (the author's
#: decision of 2026-09-09): ``[aliases]``, one key per alias, a list of
#: boundary names or families. Read by the documentation.
ALIASES_TABLE = "aliases"


class PprocArtifact(PprocSpec):
    """The post-processing artifact (``inputs/pproc/<id>.toml``).

    PFS-2029.07.01, the author's decision of 2026-09-02: the groups artifact IS the
    home of post-processing and is renamed. The file carries six tables,
    every one optional: ``[groups]`` exactly as the groups file held it,
    a name to the boundary labels or 1-based indices it aggregates;
    ``[exports]`` which of the eight export kinds a point writes;
    ``[sections]``, ``[plots]`` and ``[probes]`` the solver definitions
    the builders emit; ``[products]`` the post-processed files written
    after the run. Group members are stored verbatim and resolved by the
    script layer at emission time, as before. The shape is
    :class:`pyflightstream.cases.PprocSpec`; this class is the file.
    """


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


def is_valid_artifact_id(artifact_id: str) -> bool:
    """Whether a string is well formed as an input-library id.

    THE ONE HOME OF THE SHAPE RULE, published rather than left private
    because two layers need to ask it and the alternative was reaching
    for the private pattern across a module boundary, which a tier 1
    guard refuses by design: an underscore-private name crossing into a
    public sibling is a layer boundary crossed for a helper.

    An id is a file name STEM: letters, digits, dot, underscore or
    hyphen, beginning with a letter or a digit. It is never a path, and
    the leading-character half is the part a caller cannot infer from the
    permitted set, which is why a refusal that merely lists the permitted
    characters sends an author back to make the same mistake.

    Parameters
    ----------
    artifact_id : str
        The candidate id, as the matrix cell or the caller wrote it.

    Returns
    -------
    bool
        True when the shape is acceptable. It says nothing about whether
        anything is STAGED under that id, which is
        :func:`available_ids`'s question.

    Examples
    --------
    >>> is_valid_artifact_id("wing_clean")
    True
    >>> is_valid_artifact_id("blade.v2")
    True
    >>> is_valid_artifact_id("_scratch")
    False
    """
    return bool(_ID_PATTERN.match(artifact_id))


def _check_id(artifact_id: str, kind: str) -> None:
    """Refuse ids that could not have come from a library file name.

    Two rules, and the second applies to the coded kinds alone. An id is
    a file name stem, and a reference, setup or group id also DECLARES
    its kind with a leading letter (:data:`KIND_LETTERS`), so a number
    mistyped between the REF, SET and ENTRY cells of a run matrix is
    refused instead of resolving to another artifact's file.
    """
    if not is_valid_artifact_id(artifact_id):
        raise InputArtifactError(
            f"{kind} id {artifact_id!r} is not a valid artifact id: ids are file "
            "name stems of letters, digits, dot, underscore or hyphen, beginning "
            "with a letter or a digit. The id selects a file inside the library; it "
            "is never a path.",
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
            "the REF, SET and PPROC columns cannot resolve to another artifact's file. "
            f"Rename the library file to inputs/{directory}/{letter}{artifact_id}.toml "
            "and the matrix cell that names it in the same edit; the letter is part of "
            "the id, not a prefix the library adds or strips. A library written before "
            "v0.8.0 is migrated in ONE call rather than one rename per artifact: "
            "pyflightstream.workspace.migrate_input_ids(inputs_dir, matrices, "
            "...) for the r and s letters; a groups library (e) moves to pproc (p) with "
            "`pyfs-matrix upgrade`, in_place (CLI: --in-place) and inputs (CLI: --inputs) "
            "both given. The call "
            "as documented: migrate_input_ids(inputs_dir, matrices, "
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


@dataclass(frozen=True)
class EntitySelection:
    """One artifact key whose list selects the entities a command applies to.

    PFS-2005.02. Handing such a key an empty list looks like stating no
    preference, and it is not: the command the list feeds is either not
    emitted at all, which is the solver's own default and is asked for
    by dropping the key, or emitted naming nothing, and either way the
    run proceeds against a setup nobody selected and still reports
    numbers. Whether an empty list can mean anything is decided one key
    at a time, by the domain seat, and the decision is written beside
    the key so the refusal can say whose it is.

    Attributes
    ----------
    kind : str
        The artifact kind the key lives in, ``setup`` or ``pproc``.
    key : str
        The key as the file spells it; a placeholder marks a table whose
        every entry is a selection (``groups.<name>``) or a list of
        tables (``plots.groups[].families``).
    consumer : str
        What the list feeds: the FlightStream command, or the product
        this package writes from it.
    empty_admitted : bool or None
        True where an empty list has a documented meaning and is
        accepted, False where it is refused on the manual's word, and
        None where the domain seat has not yet decided, in which case it
        is refused until the author says.
    reason : str
        The sentence the refusal prints beside the verdict: what the
        manual says, or that nothing does yet.
    """

    kind: str
    key: str
    consumer: str
    empty_admitted: bool | None
    reason: str


_VORTICITY_EMPTY = (
    "The solver's default, surface pressure integration on every boundary, is "
    "expressed by never emitting the command (SRC-003 p.202), so a stated empty list "
    "asks for a selection and names none, and the run would converge and publish "
    "induced drag against a setup nobody selected."
)

#: Every artifact key that selects entities, with the domain seat's verdict on
#: an empty list beside it. The readers consult this table; the docs page
#: repeats it. A key that is not here is not an entity selection, and a new
#: one enters here with its verdict before its reader accepts it.
ENTITY_SELECTIONS: tuple[EntitySelection, ...] = (
    EntitySelection(
        "setup",
        "vorticity_drag_boundaries",
        "SET_VORTICITY_DRAG_BOUNDARIES",
        False,
        _VORTICITY_EMPTY,
    ),
    EntitySelection(
        "setup",
        "set_vorticity_drag_boundaries",
        "SET_VORTICITY_DRAG_BOUNDARIES",
        False,
        _VORTICITY_EMPTY,
    ),
    EntitySelection(
        "setup", "vorticity_drag_families", "SET_VORTICITY_DRAG_BOUNDARIES", False, _VORTICITY_EMPTY
    ),
    EntitySelection(
        "setup",
        "aliases.<name>",
        "every boundary-citing key of a row naming this preset",
        False,
        "An alias stands for the boundary names or families listed after it, and over none "
        "it would name nothing while reading as though it named a set; the empty list that "
        "means every family is the pproc group's, one line below.",
    ),
    EntitySelection(
        "pproc",
        "groups.<name>",
        "the polar table written per group (products.polars)",
        True,
        "An empty group is every family the geometry carries, the author's decision of "
        "2026-09-09: the polar table sums every surface row of the loads table, and a "
        "motion naming the group moves every boundary of the file.",
    ),
    EntitySelection(
        "pproc",
        "plots.groups[].families",
        "UNSTEADY_SOLVER_NEW_FORCE_PLOT",
        False,
        "The entry exists to emit one plot per parameter over the families it names; "
        "over none it would emit nothing while reading as though it had. A family "
        "the geometry does not carry is left out at emission, which is the documented "
        "way an entry resolves to fewer families than it names.",
    ),
    EntitySelection(
        "pproc",
        "sections.distributions[].families",
        "NEW_SURFACE_SECTION_DISTRIBUTION",
        False,
        "The entry exists to emit one distribution per plane over the families it "
        "names; over none it would emit nothing while reading as though it had. A "
        "family the geometry does not carry is left out at emission, which is the "
        "documented way an entry resolves to fewer families than it names.",
    ),
    EntitySelection(
        "pproc",
        "base_regions",
        "DETECT_BASE_REGIONS_BY_SURFACE",
        True,
        "An empty list is the documented off switch of the base-region autodetect "
        "(PFS-2029.10): none means no detection, and the row's BASE_REGIONS key is "
        "how one row turns it on.",
    ),
)

_SELECTION_BY_KEY = {(rule.kind, rule.key): rule for rule in ENTITY_SELECTIONS}


def _stated_empty_selections(
    kind: str, data: Mapping[str, Any]
) -> list[tuple[str, EntitySelection]]:
    """Return every entity-selecting key the file states as an empty list.

    Walks the shapes the table names: a plain key of a setup, the
    ``[groups]`` table of a pproc artifact, and the ``families`` of its
    plot groups and section distributions. Returns the key as the file
    spells it beside the table entry that judges it.
    """
    found: list[tuple[str, EntitySelection]] = []
    if kind == "setup":
        for rule in ENTITY_SELECTIONS:
            if rule.kind == kind and data.get(rule.key) == []:
                found.append((rule.key, rule))
        aliases = data.get(ALIASES_TABLE)
        if isinstance(aliases, Mapping):
            rule = _SELECTION_BY_KEY[("setup", "aliases.<name>")]
            found.extend(
                (f'{ALIASES_TABLE}."{name}"', rule)
                for name, members in aliases.items()
                if members == []
            )
        return found
    groups = data.get("groups")
    if isinstance(groups, Mapping):
        for name, members in groups.items():
            if members == []:
                found.append((f'groups."{name}"', _SELECTION_BY_KEY[("pproc", "groups.<name>")]))
    for table, entries, key in (
        ("plots", "groups", "plots.groups[].families"),
        ("sections", "distributions", "sections.distributions[].families"),
    ):
        section = data.get(table)
        listed = section.get(entries) if isinstance(section, Mapping) else None
        if not isinstance(listed, list):
            continue
        for position, entry in enumerate(listed):
            if isinstance(entry, Mapping) and entry.get("families") == []:
                found.append(
                    (f"{table}.{entries}[{position}].families", _SELECTION_BY_KEY[("pproc", key)])
                )
    return found


def refuse_empty_selections(kind: str, path: Path, data: Mapping[str, Any]) -> None:
    """Refuse an artifact stating an empty list for an entity-selecting key.

    PFS-2005.02. Called by the readers before the model validates, so the
    refusal names the artifact FILE, the key as the file spells it, and
    what the empty list would have disabled, with the domain seat's
    verdict beside it. The model's own validators stay: they guard the
    Python path, and this guards the file a matrix row names.

    Parameters
    ----------
    kind : str
        ``setup`` or ``pproc``.
    path : Path
        The artifact file, for the message.
    data : mapping
        The file's TOML table as loaded.

    Raises
    ------
    InputArtifactError
        The first key stated empty whose verdict is not "admitted".
    """
    for key, rule in _stated_empty_selections(kind, data):
        if rule.empty_admitted:
            continue
        if rule.empty_admitted is None:
            verdict = (
                "Whether an empty list can mean anything here is the domain seat's call, "
                "not yet decided, and it is refused until the author says"
            )
        else:
            verdict = "An empty list is refused"
        raise InputArtifactError(
            f"the {kind} artifact {path} states {key} = [], an empty list, and that list "
            f"selects what {rule.consumer} applies to. {rule.reason} {verdict}. Name the "
            "entities, or drop the key."
        )


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
    return _validate(ReferenceArtifact, _split_reference_tables(data, path), path, "reference")


#: The keys only a rotor block carries. A top-level table stating one of
#: these and no ``kind`` is a rotor that forgot to say so, and is refused
#: with that sentence rather than as an unknown key.
_ROTOR_ONLY_KEYS = ("families_blades", "families_general", "diameter_m", "rpm_sign", "blade1")

#: The frames a rotor instantiates, as spellings to compare a declared
#: name against: ``<ALIAS>_SMRP``, ``<ALIAS>_RMRP`` and ``<ALIAS>_RMRP<k>``
#: for each blade k. The digits are matched rather than enumerated,
#: because a block's blade count is not known where a name is checked.
_ROTOR_FRAME_SUFFIX = re.compile(r"_(SMRP|RMRP\d*)$")


def _frame_of_a_rotor(spelling: str, rotors: Mapping[str, Any]) -> str | None:
    """Return the rotor whose own frames a declared name would collide with, if any."""
    token = spelling.strip().upper()
    match = _ROTOR_FRAME_SUFFIX.search(token)
    if match is None:
        return None
    radical = token[: match.start()]
    return next((name for name in rotors if name.upper() == radical), None)


def _refuse_a_retired_spelling(data: Mapping[str, Any], path: Path) -> None:
    """Refuse a reference that uses a word this package retired (the author, 2026-09-10).

    A key this file no longer knows would otherwise reach a strict model
    and come back as "extra inputs are not permitted", which is true and
    says nothing about what to write instead. The registry knows what each
    retired spelling became, so the refusal names the fix.

    Raises
    ------
    InputArtifactError
        A top-level key or table is a retired spelling, or a block states
        the retired rotor kind.
    """
    for key, value in data.items():
        entry = retired_key(key)
        if entry is not None:
            raise InputArtifactError(
                f"the reference artifact {path}: {entry.message()}",
                kind="reference",
            )
        if isinstance(value, dict) and value.get("kind") == POINT_KIND_ENGINE_WORD:
            raise InputArtifactError(
                f"the reference artifact {path} declares [{key}] with "
                f"{BLOCK_KIND_ENGINE.message()}",
                kind="reference",
            )


def _split_reference_tables(data: dict[str, Any], path: Path) -> dict[str, Any]:
    """Sort a reference file's top-level tables into the model's fields (FR-59, FR-60, FR-72).

    Three of them are not fixed keys and cannot be, because their names
    belong to the study: one table per rotor, keyed by the word a row
    moves. So this function does for the reference what
    :func:`resolve_setup` does for the preset, and reads the file's shape
    rather than requiring the author to nest it:

    * a table declaring ``kind = "rotor"`` is a rotor and goes to
      ``rotors``; the block's NAME becomes an alias over everything the
      rotor owns, the general families first, so a row citing it moves the
      spinner with the blades (the author's words of 2026-09-10);
    * a table declaring any other point ``kind`` goes to ``points``;
    * ``[aliases]`` and ``[[frames]]`` are lifted by name.

    A block whose ``alias`` differs from its name is refused here rather
    than in the model, because the model never sees the name: the name is
    the key this function reads.
    """
    _refuse_a_retired_spelling(data, path)
    rest = dict(data)
    aliases = dict(rest.pop(ALIASES_TABLE, {}) or {})
    frames = rest.pop(FRAMES_TABLE, []) or []
    rotors: dict[str, Any] = {}
    points: dict[str, Any] = {}
    for name, value in list(rest.items()):
        if not isinstance(value, dict):
            continue
        if "kind" not in value:
            # A BLOCK THAT FORGOT ITS `kind` LINE is the likeliest mistake a
            # hand-written rotor makes, and without this it falls through to
            # a strict model and reads as "extra inputs are not permitted",
            # which says nothing about rotors. The rotor-only keys are what
            # identify it (the interface lens of 2026-09-10).
            wanted = sorted(key for key in _ROTOR_ONLY_KEYS if key in value)
            if wanted:
                raise InputArtifactError(
                    f"the reference artifact {path} declares [{name}] with "
                    f"{', '.join(wanted)} and no kind. A block that states a rotor's "
                    'own keys is a rotor, and a rotor says so: add kind = "rotor" to '
                    "it. Every other top-level table of this file is a reference "
                    "quantity.",
                    kind="reference",
                )
            continue
        if value.get("kind") != "rotor":
            points[name] = rest.pop(name)
            continue
        block = rest.pop(name)
        stated = block.get("alias")
        # CASE FOLDED, as every other alias comparison in this package is:
        # `alias = "pusher"` under [PUSHER] names one word and was refused
        # for its spelling alone (the interface lens of 2026-09-10).
        if stated is not None and str(stated).casefold() != name.casefold():
            raise InputArtifactError(
                f"the reference artifact {path} declares the rotor {name!r} and states "
                f"alias = {stated!r} inside it. The block's name IS the alias, so the two "
                "can only agree or disagree; make them equal, or drop the field, which "
                "the reader then fills in from the name.",
                kind="reference",
            )
        collision = next((part for part in ("_SMRP", "_RMRP") if part in name.upper()), None)
        if collision is not None:
            raise InputArtifactError(
                f"the reference artifact {path} declares the rotor {name!r}, whose name "
                f"carries {collision}. That is the radical this package gives a rotor's own "
                f"frames, its static and rotating moment reference points ({name}_SMRP, "
                f"{name}_RMRP and {name}_RMRP<k> per blade), so a rotor named after a "
                "frame makes two different things spell the same. Choose another name.",
                kind="reference",
            )
        block.setdefault("alias", name)
        rotors[name] = block
        members = [*block.get("families_general", []), *block.get("families_blades", [])]
        # THE ROTOR'S NAME IS AN ALIAS OVER WHAT IT OWNS, and a hand-written
        # [aliases] entry of the same name would SHADOW that silently, which
        # is the design's central claim quietly reversed. Refused naming
        # both places rather than resolved by precedence.
        # CASE FOLDED, as every other alias comparison in this package is
        # and as the `alias =` check twenty-five lines above already was.
        # Exact-case here let `[PUSHER]` and `pusher = [...]` both stand, so
        # the returned table carried TWO keys for one word, one holding the
        # rotor's real membership and one holding the hand-written list, and
        # which of them moved was decided downstream by whichever the reader
        # folded to first (the architecture lens of the 0.15.0 release
        # review). The existing case spelled the alias exactly like the
        # block, which is the one spelling the guard did catch.
        shadow = next((key for key in aliases if key.casefold() == name.casefold()), None)
        if shadow is not None and list(aliases[shadow]) != members:
            raise InputArtifactError(
                f"the reference artifact {path} declares the rotor {name!r} and also an "
                f"[{ALIASES_TABLE}] entry named {shadow!r}. An alias is matched case "
                "folded, so those are one word. The rotor's name already stands "
                f"for everything it owns ({', '.join(members)}), so the table entry would "
                "quietly replace the rotor's own membership. Rename the alias, or drop "
                "it.",
                kind="reference",
            )
        if shadow is not None:
            del aliases[shadow]
        aliases[name] = members
    # THE COLLISION IS TWO SIDED, and the guard above closes one side. A
    # rotor may not be named after its frames; a FRAME or an ALIAS may not
    # be named after a rotor's frames either, and until this ran the guard
    # sat on one side of the same shadowing the interface lens of REL-0140
    # had already found once (the interface lens of 2026-09-10).
    for spelling, what in [(frame.get("name", ""), FRAMES_TABLE) for frame in frames] + [
        (name, ALIASES_TABLE) for name in aliases
    ]:
        owner = _frame_of_a_rotor(str(spelling), rotors)
        if owner is not None:
            raise InputArtifactError(
                f"the reference artifact {path} declares [{what}] {spelling!r}, which is "
                f"the name of a frame this package builds for the rotor {owner!r}: a "
                f"rotor instantiates {owner}_SMRP, {owner}_RMRP and {owner}_RMRP<k> per "
                "blade. Two different things would spell the same. Choose another name.",
                kind="reference",
            )
    if aliases:
        # THE RING IS CAUGHT WHERE THE FILE IS NAMED, which is here and not
        # in the resolver. `resolve_alias` raises AliasCycleError naming both
        # sides of the ring and nothing else, and nobody catches it, so a
        # workspace with several references gave a user a chain and no file
        # to open (the interface lens of the 0.15.0 release review). Every
        # other refusal on this path names its artifact.
        #
        # Resolving each alias against an EMPTY inventory is deliberate and
        # is what makes this cheap: a ring is a property of the table alone,
        # so no geometry is needed to find one, and a member that resolves to
        # nothing here is the ordinary case this package is built around.
        from pyflightstream.cases import AliasCycleError, resolve_alias

        for name in aliases:
            try:
                resolve_alias(name, (), aliases)
            except AliasCycleError as ring:
                raise InputArtifactError(
                    f"the reference artifact {path} carries a ring in its "
                    f"[{ALIASES_TABLE}] table: {ring}",
                    kind="reference",
                ) from None
        rest[ALIASES_TABLE] = aliases
    if frames:
        rest[FRAMES_TABLE] = frames
    if rotors:
        rest["rotors"] = rotors
    if points:
        rest["points"] = points
    return rest


def _the_run_types_that_read(word: str) -> list[str]:
    """Return the run types whose own vocabulary already holds ``word``.

    A CUSTOM FLAG'S NAME MUST BE THE STUDY'S OWN WORD (FR-74). A row states
    one cell per key, so a flag taking a word a run type reads makes that
    cell do two things: the curated handling and the flag's emission. The
    guard that refuses a key nothing reads is exempt for a declared flag,
    by design, which is exactly why the collision has to be caught here.

    The converter's own prefixed keys and the workspace's own point key are
    included, for the same reason: they are read by something, and a flag
    that takes one is a cell with two readers.
    """
    from pyflightstream.cases.workflows import (
        CONVERTER_PREFIX,
        ROTOR_ORIGIN_POINT_KEY,
        WORKFLOWS,
    )

    wanted = word.strip().casefold()
    taken = [
        name
        for name, workflow in WORKFLOWS.items()
        if any(key.strip().casefold() == wanted for key in workflow.keys)
    ]
    if wanted == ROTOR_ORIGIN_POINT_KEY.strip().casefold():
        taken.append("the workspace's own point binding")
    if wanted.startswith(CONVERTER_PREFIX.casefold()):
        taken.append("the matrix converter")
    return sorted(taken)


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
    refuse_empty_selections("setup", path, data)
    # THE FRAMES TABLE IS NOT A SOLVER SETTING (PFS-2034.01): it leaves the
    # raw table here, so the loop that refuses a key naming no setting never
    # meets it, and it is validated as the list of records it is.
    frames = data.pop(FRAMES_TABLE, [])
    if not isinstance(frames, list) or not all(isinstance(entry, dict) for entry in frames):
        raise InputArtifactError(
            f"setup preset {artifact_id!r} ({path}) states [{FRAMES_TABLE}] as {frames!r}, "
            f"and the table is a list of records: write [[{FRAMES_TABLE}]] once per frame "
            "with name, origin and optionally x_axis and y_axis."
        )
    # THE RAW TABLE IS NOT A SOLVER SETTING EITHER (PFS-2033.01): the
    # lines are the solver's own, emitted before the phase each names.
    raw = data.pop(RAW_TABLE, [])
    if not isinstance(raw, list) or not all(isinstance(entry, dict) for entry in raw):
        raise InputArtifactError(
            f"setup preset {artifact_id!r} ({path}) states [{RAW_TABLE}] as {raw!r}, and the "
            f"table is a list of records: write [[{RAW_TABLE}]] once per command with "
            "command (the line as the solver reads it) and before (the phase it precedes)."
        )
    # THE FLAGS TABLE IS NOT A SOLVER SETTING EITHER (PFS-2035.20): each
    # record names a FlightStream command and the word a row sets it by.
    flags = data.pop(FLAGS_TABLE, [])
    if not isinstance(flags, list) or not all(isinstance(entry, dict) for entry in flags):
        raise InputArtifactError(
            f"setup preset {artifact_id!r} ({path}) states [{FLAGS_TABLE}] as {flags!r}, and "
            f"the table is a list of records: write [[{FLAGS_TABLE}]] once per flag with "
            "name (the word a matrix row writes) and command (the FlightStream command it "
            "becomes, bare)."
        )
    # ONE WORD, ONE FLAG. Two records giving one name two commands make the
    # row's cell mean whichever the reader saw last, which is the shape this
    # package refuses everywhere a name is declared.
    seen: dict[str, str] = {}
    for entry in flags:
        word = str(entry.get("name", "")).strip().casefold()
        taken = _the_run_types_that_read(word)
        if taken:
            raise InputArtifactError(
                f"setup preset {artifact_id!r} ({path}) declares the flag "
                f"{entry.get('name')!r}, which is a word {', '.join(taken)} already "
                f"reads. A row stating it would drive that curated handling AND emit "
                f"{entry.get('command')}: one cell, two effects, and nothing anywhere "
                "saying so. Choose a word of your own. It is refused here, where the "
                "flag is DECLARED, because the vocabulary check that catches a stray "
                "key is the one a declared flag is deliberately exempt from."
            )
        if word in seen:
            raise InputArtifactError(
                f"setup preset {artifact_id!r} ({path}) declares the flag "
                f"{entry.get('name')!r} twice, as {seen[word]} and as "
                f"{entry.get('command')}. One word names one command, or a row stating it "
                "means whichever record was read last."
            )
        seen[word] = str(entry.get("command"))
    # THE ALIASES TABLE IS NOT A SOLVER SETTING (the author's decision of 2026-09-09):
    # a name to the boundaries it stands for, read wherever a boundary is cited.
    aliases = data.pop(ALIASES_TABLE, {})
    if not isinstance(aliases, dict) or not all(isinstance(v, list) for v in aliases.values()):
        bad = (
            sorted(k for k, v in aliases.items() if not isinstance(v, list))
            if isinstance(aliases, dict)
            else [repr(aliases)]
        )
        raise InputArtifactError(
            f"setup preset {artifact_id!r} ({path}) states [{ALIASES_TABLE}] with "
            f"{', '.join(bad)} not a list: an alias is a name and the list of boundary names "
            f'or families it stands for, as lifters = ["LiftBlade", "Hub1"].'
        )
    return _validate(
        SetupArtifact,
        {
            "settings": data,
            "frames": frames,
            "raw_commands": raw,
            "flags": flags,
            "aliases": aliases,
        },
        path,
        "setup",
    )


def resolve_pproc(inputs_dir: Path, artifact_id: str) -> PprocArtifact:
    """Load the post-processing artifact one id names.

    Parameters
    ----------
    inputs_dir : Path
        The workspace ``inputs/`` directory.
    artifact_id : str
        File name stem under ``pproc/``.

    Returns
    -------
    PprocArtifact
        The validated artifact, group members stored verbatim.

    Raises
    ------
    InputArtifactError
        Unknown id (the message lists the available ids), a file that
        does not validate, or a file in the shape the groups artifact
        had, which is named with the command that moves it.

    Notes
    -----
    An old-shape groups file is told by its BARE LISTS: a group name to
    its members at the top level, with no ``[groups]`` table. The one
    top-level list the pproc shape itself defines, ``base_regions``, is
    not that (PFS-2005.04): until 0.13.0 this reader refused the
    documented off switch ``base_regions = []`` as an old-shape file,
    while the docs page showed exactly that form. TOML puts a top-level
    key BEFORE the first table header, so the line goes above
    ``[groups]``; written under it, it is a group named base_regions and
    is refused as one.
    """
    _check_id(artifact_id, "pproc")
    directory = Path(inputs_dir) / "pproc"
    path = directory / f"{artifact_id}.toml"
    if not path.is_file():
        raise _miss("pproc", artifact_id, directory)
    data = _load_toml(path, "pproc")
    bare = sorted(
        key for key, value in data.items() if isinstance(value, list) and key != "base_regions"
    )
    if bare:
        raise InputArtifactError(
            f"the pproc artifact {path} carries group(s) {', '.join(bare)} at the top "
            "level, which is the shape the groups artifact had before 0.11.0. A pproc "
            "file holds its groups under a [groups] table, beside [exports], "
            "[sections], [plots], [probes] and [products]; "
            "pyflightstream.workspace.migrate_groups_to_pproc moves a groups file into "
            "that shape, given the workspace inputs directory (the command line "
            "spells it inputs (CLI: --inputs) on `pyfs-matrix upgrade`)."
        )
    refuse_empty_selections("pproc", path, data)
    return _validate(PprocArtifact, data, path, "pproc")


#: The kind letter a groups id carried before 0.11.0, when the kind was
#: renamed pproc (PFS-2029.07): ``e`` for ENTRY, the column that named it.
GROUPS_LETTER = "e"


def migrate_groups_to_pproc(inputs_dir: Path) -> dict[str, str]:
    """Move every ``inputs/groups/e*.toml`` to ``inputs/pproc/p*.toml`` under ``[groups]``.

    PFS-2029.07.01: the groups artifact becomes the pproc artifact, the
    file's nine groups migrating verbatim: the new file is the old one's
    text under a ``[groups]`` header, comments and all, so a diff of the
    two shows one added line. Returns the id mapping (old to new) for the
    matrix cells that name them, which :func:`upgrade_matrix` rewrites.

    Parameters
    ----------
    inputs_dir : Path
        The workspace ``inputs/`` directory.

    Returns
    -------
    dict of str to str
        Old id to new id, ``e001`` to ``p001``; empty when there is no
        groups directory or it holds no file.

    Raises
    ------
    InputArtifactError
        A groups file whose id does not carry the ``e`` letter (it
        predates the kind-letter rule; run the id migration first), a
        file that already carries a table (it is not a groups file), or
        a target that already exists.
    """
    source_dir = Path(inputs_dir) / "groups"
    target_dir = Path(inputs_dir) / "pproc"
    if not source_dir.is_dir():
        return {}
    mapping: dict[str, str] = {}
    for path in sorted(source_dir.glob("*.toml")):
        old = path.stem
        if old[:1].lower() != GROUPS_LETTER:
            raise InputArtifactError(
                f"the groups file {path} carries the id {old!r}, which does not declare "
                f"its kind with the letter {GROUPS_LETTER!r}; give the library its kind "
                "letters first (migrate_input_ids) and then move the groups to pproc."
            )
        data = _load_toml(path, "groups")
        tables = sorted(key for key, value in data.items() if isinstance(value, dict))
        if tables:
            raise InputArtifactError(
                f"the groups file {path} carries table(s) {', '.join(tables)}, so it is "
                "not a groups file of the shape this migration moves (a flat table of "
                "group name to members)."
            )
        new = KIND_LETTERS["pproc"] + old[1:]
        target = target_dir / f"{new}.toml"
        if target.exists():
            raise InputArtifactError(
                f"cannot move {path} to {target}: the target already exists. Remove or "
                "rename it, then run the migration again."
            )
        mapping[old] = new
    for old, new in mapping.items():
        path = source_dir / f"{old}.toml"
        target = target_dir / f"{new}.toml"
        text = path.read_text(encoding="utf-8")
        target_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "# Moved from inputs/groups/" + path.name + " by `pyfs-matrix upgrade --inputs`;\n"
            "# the groups are the file's own lines, under the [groups] table a pproc\n"
            "# artifact holds them in (PFS-2029.07).\n[groups]\n" + text,
            encoding="utf-8",
        )
        path.unlink()
    try:
        source_dir.rmdir()
    except OSError:
        pass
    return mapping


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


def resolve_geometry(inputs_dir: Path, name: str) -> Path:
    """Resolve the staged geometry file one ``GEOMETRY`` cell names.

    SINCE 0.11.0 THE CELL CARRIES THE FILE NAME WITH ITS EXTENSION
    (PFS-2029.09, the author's decision of 2026-09-02, amending
    PFS-2009.01): ``30_WB.fsm`` resolves to ``inputs/geometries/30_WB.fsm``
    and ``blade.v2.fsm`` to that one file, one reading and no other. What
    it buys is that the cell says what the file IS: a ``.fsm`` is a saved
    simulation with its boundary conditions in it, a mesh is not, and the
    workflow can tell the two apart before any seat is spent.

    TWO LAYOUTS, THE FOLDER READ FIRST (PFS-2032.04, the author's reading of
    2026-09-08, design 68 section A3). ``30_WB.fsm`` resolves to
    ``geometries/30_WB/30_WB.fsm`` when that folder exists and to
    ``geometries/30_WB.fsm`` otherwise, so the cell does not change and
    no matrix written since 0.11.0 breaks. What the folder buys is a home
    for the files that belong to one geometry: its boundary inventory and
    its provenance record sit beside it, and a point staged from the
    folder shows that geometry's files and never the whole library
    (:meth:`~pyflightstream.workspace.CampaignWorkspace.stage_inputs`).
    The flat layout is not deprecated; :func:`migrate_geometry_layout`
    moves a library when its owner decides to.

    Parameters
    ----------
    inputs_dir : Path
        The workspace ``inputs/`` directory.
    name : str
        File name, extension included, of a file directly under
        ``geometries/`` or under ``geometries/<stem>/``.

    Returns
    -------
    Path
        The geometry file.

    Raises
    ------
    InputArtifactError
        A bare stem (no extension), naming every staged file that carries
        that stem so the cell can be completed; a name the library does
        not hold, naming the files it does; a path, which is never an id.
    """
    directory = Path(inputs_dir) / "geometries"
    if "/" in name or "\\" in name:
        base = PurePosixPath(name.replace("\\", "/")).name
        raise InputArtifactError(
            f"geometry {name!r} is a path, and the GEOMETRY cell names a file "
            f"under {directory} by its file name, never a path: stage the file there "
            f"(directly, or in a folder named by its stem) and write GEOMETRY: {base}.",
            kind="geometry",
            artifact_id=name,
        )
    found = _staged_geometries(directory)
    staged = sorted(found)
    stem, suffix = PurePath(name).stem, PurePath(name).suffix
    if not suffix:
        _check_id(name, "geometry")
        candidates = [f for f in staged if PurePath(f).stem == name]
        if candidates:
            raise InputArtifactError(
                f"geometry {name!r} is a bare stem, and since 0.11.0 the GEOMETRY cell "
                f"carries the file name with its extension: write GEOMETRY: "
                f"{' or GEOMETRY: '.join(candidates)} (the file(s) under {directory} "
                "carrying that stem), or run `pyfs-matrix upgrade` with in_place (CLI: "
                "--in-place), which completes every GEOMETRY cell with .fsm.",
                kind="geometry",
                artifact_id=name,
                available=tuple(candidates),
            )
        raise InputArtifactError(
            f"no geometry artifact with id {name!r}; "
            + (
                f"the library {directory} holds {', '.join(staged)}"
                if staged
                else f"the library directory {directory} holds no geometry yet (stage "
                "the file there, directly or in a folder named by its stem)"
            ),
            kind="geometry",
            artifact_id=name,
            available=tuple(staged),
        )
    _check_id(stem, "geometry")
    if name not in found:
        raise InputArtifactError(
            f"geometry {name!r} is not under {directory}; it holds "
            f"{', '.join(staged) if staged else 'no file at all'}. Stage the file "
            f"there under exactly that name (directly, or as {stem}/{name}), or fix "
            "the cell.",
            kind="geometry",
            artifact_id=name,
            available=tuple(staged),
        )
    return found[name]


def _is_sidecar(name: str) -> bool:
    """Whether a file name is a geometry's inventory or provenance record."""
    return name.endswith(SIDECAR_SUFFIXES)


def _staged_geometries(directory: Path) -> dict[str, Path]:
    """Map every staged geometry file name to its path, both layouts read.

    A file directly under ``geometries/`` is the flat layout. A folder
    ``geometries/<stem>/`` is one geometry's home (PFS-2032.04), and the
    geometry files in it are the ones whose stem is the folder's name, so
    its ``<stem>.boundaries.toml`` (stem ``<stem>.boundaries``) and its
    provenance record are not offered as geometries a cell could name;
    a flat sidecar is left out by its suffix for the same reason. The
    folder is read first: a file in it stands in front of a flat file of
    the same name, which is the order the reading states.
    """
    if not directory.is_dir():
        return {}
    found: dict[str, Path] = {}
    for entry in sorted(directory.iterdir()):
        if entry.is_file():
            if not _is_sidecar(entry.name):
                found.setdefault(entry.name, entry)
        elif entry.is_dir():
            for path in sorted(entry.iterdir()):
                if path.is_file() and path.stem == entry.name:
                    found[path.name] = path
    return found


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


@dataclass(frozen=True)
class RegisteredBuild:
    """One entry of the workspace build registry, as the registry states it.

    Attributes
    ----------
    fs_exe : Path
        The executable this build id names. Existence is checked by the
        executor at construction, so a campaign can be authored away
        from the licensed machine.
    fs_version : str or None
        The FlightStream version the registry DECLARES this build's
        scripts are emitted under, canonical identifier (``"26.123"``)
        or a vendor release name that resolves to exactly one registered
        build. None means the registry declares none, and the caller's
        campaign default answers for it.

        It is a DECLARATION and never an inference. Nothing here reads a
        version out of the executable path or out of the build id, which
        is the rule :class:`pyflightstream.run.SolverBuild` exists to
        state: a build id is a key of this registry, and which command
        database a build carries is a fact only its owner knows.
    """

    fs_exe: Path
    fs_version: str | None


def _refuse_declared_version(version: str, build_id: str, registry_path: Path) -> None:
    """Refuse a declared version the version registry does not carry.

    The check happens where the version is READ rather than where a
    script is emitted under it, so a typed identifier is refused with the
    file and the build id in the message instead of surfacing much later
    as an unknown-version error from the script layer.

    Parameters
    ----------
    version : str
        The version string the registry entry declares.
    build_id : str
        The build id whose entry declares it, for the message.
    registry_path : Path
        The registry file, for the message.

    Raises
    ------
    InputArtifactError
        The identifier names no registered version, or names a vendor
        release name that more than one registered build carries. The
        chained message lists the registered versions or the candidates.
    """
    try:
        resolve(version)
    except (UnknownVersionError, AmbiguousVersionAliasError) as error:
        raise InputArtifactError(
            f"the registry entry for build {build_id!r} in {registry_path} declares "
            f"version {version!r}, which this package cannot resolve to one registered "
            "FlightStream version. The version decides which command database the "
            "build's scripts are emitted against, so it is never guessed from the "
            f"build id or the executable path. {error}"
        ) from error


def resolve_build(
    inputs_dir: Path, build_id: str, override: str | Path | None = None
) -> RegisteredBuild:
    """Read the registry entry of one build id: its executable and its version.

    Two explicit modes, translated from the run matrix's MANUAL pattern:

    - Registry mode (default): the build id must exist in
      ``inputs/executables.toml``, a top-level TOML table mapping build
      ids to entries.
    - Override mode: an explicit ``override`` path wins over the
      registry and is the only way to run an unregistered build; it is
      never guessed from the environment. An override declares NO
      version, because it is a bare path with no registry entry behind
      it to carry one.

    TWO ENTRY SHAPES, and the difference is what a build may say about
    itself:

    - ``"26.120" = "C:/fs26120/FlightStream.exe"`` is the shape this
      registry has always had and means exactly what it meant: the build
      id names an executable and declares no version, so a campaign that
      sends a row to it emits that row's script under the campaign
      default version.
    - ``"26.123" = { path = "C:/fs26123/FlightStream.exe", version =
      "26.123" }`` declares the version as well, which is what lets ONE
      run matrix send its rows to two solver builds and record each row
      against the version its own build emits under (PFS-2009.05).

    The table is where the declaration lives because it is already the
    file in which the user says what a build id MEANS on this machine.
    Deriving the version from the build id instead would be the
    inference :class:`pyflightstream.run.SolverBuild` refuses, and the
    two are not the same thing: a registry key is a name the campaign
    author chose, and nothing stops it naming an installation whose
    command database is anything at all.

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
    RegisteredBuild
        The executable, and the declared version or None.

    Raises
    ------
    InputArtifactError
        Registry file missing; build id not registered (the message
        lists the registered build ids and the override mode); an entry
        that is neither a path string nor a table; a table with no
        ``path``; a table carrying a key outside
        :data:`EXECUTABLE_ENTRY_KEYS`; or a declared version the version
        registry does not carry.

    Examples
    --------
    >>> from pyflightstream.workspace.inputs import resolve_build
    >>> build = resolve_build(workspace.inputs_dir, "26.123")  # doctest: +SKIP
    >>> build.fs_version                                       # doctest: +SKIP
    '26.123'
    """
    if override is not None:
        return RegisteredBuild(fs_exe=Path(override), fs_version=None)
    registry_path = Path(inputs_dir) / EXECUTABLES_FILE
    if not registry_path.is_file():
        raise InputArtifactError(
            f"no executable registry at {registry_path}; register builds as "
            '"<build_id>" = "<path>" entries in that TOML file (this machine\'s paths may '
            f"go in {LOCAL_EXECUTABLES_FILE} beside it, read over the registry, but the "
            "registry itself must exist), or pass the explicit override path. The "
            "executable is always explicit input, never guessed."
        )
    table = _load_toml(registry_path, "executables")
    overlay_path = registry_path.with_name(LOCAL_EXECUTABLES_FILE)
    #: Which file each build id's entry came from, so a refusal about an
    #: entry names the file the user has to edit (a review of 2026-09-08
    #: found the overlay's own mistakes reported against the registry).
    source_of: dict[str, Path] = dict.fromkeys(table, registry_path)
    if overlay_path.is_file():
        for key, local in _load_toml(overlay_path, "executables").items():
            committed = table.get(key)
            if committed is None:
                # The committed registry is the declaration of which builds
                # this workspace knows; the overlay supplies paths for them
                # and may not add one, or a row would run on one machine
                # and be refused as unregistered on another from the same
                # tree, with the file that explains it gitignored.
                raise InputArtifactError(
                    f"{overlay_path} supplies build {key!r}, which {registry_path.name} "
                    f"does not register (registered: "
                    f"{', '.join(sorted(table)) if table else 'none yet'}). The overlay "
                    "gives this machine's path for a build the committed registry "
                    "declares; declare the build there first, with a placeholder path."
                )
            if isinstance(local, str) and isinstance(committed, dict):
                table[key] = {**committed, "path": local}
            else:
                table[key] = local
            source_of[key] = overlay_path
    entry = table.get(build_id)
    entry_path = source_of.get(build_id, registry_path)
    if entry is None:
        # BOTH shapes count as registered. Listing only the string entries,
        # which is what this did while a string was the only shape, would
        # tell a user with a table-valued registry that nothing is
        # registered at all.
        registered = sorted(key for key, value in table.items() if isinstance(value, (str, dict)))
        listing = ", ".join(registered) if registered else "none yet"
        raise InputArtifactError(
            f"build id {build_id!r} is not in the executable registry "
            f"{registry_path} (registered: {listing}); add it there, or pass the "
            "explicit override path to run an unregistered build."
        )
    if isinstance(entry, str):
        return RegisteredBuild(fs_exe=Path(entry), fs_version=None)
    if not isinstance(entry, dict):
        raise InputArtifactError(
            f"the registry entry for build {build_id!r} in {entry_path} must be "
            f"a path string or a table, got {type(entry).__name__}; write "
            f'"{build_id}" = "C:/path/to/FlightStream.exe" for a build whose scripts '
            f'are emitted under the campaign default version, or "{build_id}" = '
            '{ path = "C:/path/to/FlightStream.exe", version = "26.123" } to declare '
            "the version this build's scripts are emitted under."
        )
    unknown = sorted(key for key in entry if key not in EXECUTABLE_ENTRY_KEYS)
    if unknown:
        raise InputArtifactError(
            f"the registry entry for build {build_id!r} in {entry_path} carries "
            f"key(s) {', '.join(unknown)}, and a build entry reads "
            f"{', '.join(EXECUTABLE_ENTRY_KEYS)} and nothing else. The key is refused "
            "rather than ignored because an ignored one is invisible: a misspelled "
            "version key leaves the registry looking correct and every row of this "
            "build emitted under the campaign default. Correct the spelling, or "
            "remove the key."
        )
    path_value = entry.get("path")
    if not isinstance(path_value, str):
        stated = "declares no path" if path_value is None else f"declares path {path_value!r}"
        raise InputArtifactError(
            f"the registry entry for build {build_id!r} in {entry_path} {stated}, "
            "and a table entry must carry path as a string; write "
            f'"{build_id}" = {{ path = "C:/path/to/FlightStream.exe" }}. The '
            "executable is always explicit input, never guessed."
        )
    version = entry.get("version")
    if version is None:
        return RegisteredBuild(fs_exe=Path(path_value), fs_version=None)
    if not isinstance(version, str):
        raise InputArtifactError(
            f"the registry entry for build {build_id!r} in {entry_path} declares "
            f"version {version!r} of type {type(version).__name__}, and a FlightStream "
            'version is written as a string: version = "26.123". A bare 26.123 is a '
            "TOML float and loses the three-digit form the canonical identifier is."
        )
    _refuse_declared_version(version, build_id, registry_path)
    return RegisteredBuild(fs_exe=Path(path_value), fs_version=version)


def resolve_executable(inputs_dir: Path, build_id: str, override: str | Path | None = None) -> Path:
    """Resolve the FlightStream executable of one build id.

    The path half of :func:`resolve_build`, which is where the registry
    is read and where both entry shapes are described. This is the call
    for a caller who wants the executable and nothing else; a caller who
    also needs the version the build declares calls
    :func:`resolve_build` instead, because the two facts come from one
    entry and reading it twice is how they would drift apart.

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
        Every refusal of :func:`resolve_build`: registry file missing,
        build id not registered, or a malformed entry.
    """
    return resolve_build(inputs_dir, build_id, override=override).fs_exe


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


# --- the boundary inventory sidecar (PFS-2029.06) ------------------------------------

#: Suffix of the sidecar that states a geometry's boundary order, appended
#: to the geometry's stem: ``30_WB.fsm`` has ``30_WB.boundaries.toml``.
INVENTORY_SUFFIX = ".boundaries.toml"
#: Suffix of the record that says where a geometry came from, appended to
#: its stem the same way. The package writes none: the tier-3 preparer and
#: a user do, and the library carries it beside the file it describes.
PROVENANCE_SUFFIX = ".provenance.toml"
#: The two files that belong to a geometry and are never geometries
#: themselves: the resolver leaves them out of what a cell could name and
#: the layout migration moves them with their geometry (PFS-2032.05).
SIDECAR_SUFFIXES = (INVENTORY_SUFFIX, PROVENANCE_SUFFIX)


def inventory_sidecar(geometry: str | Path) -> Path:
    """Return the sidecar path beside ``geometry``, whether or not it exists."""
    path = Path(geometry)
    return path.with_name(path.stem + INVENTORY_SUFFIX)


def write_inventory(geometry: str | Path, *, overwrite: bool = False) -> Path:
    """Write ``<stem>.boundaries.toml`` beside a saved simulation.

    THE ORDER IS READ, NEVER STATED (PFS-2029.06.02). Until 0.11.0 a
    setup preset could carry ``mesh_order_list``, an order typed by hand
    for one mesh into a file several meshes shared, and nothing checked
    it against any of them. The sidecar is produced from the mesh block
    of the file it sits beside, and a run whose sidecar disagrees with
    the file is refused before the solver starts (:func:`read_inventory`
    and the workflow builder), so the two cannot drift apart silently.

    Parameters
    ----------
    geometry : str or Path
        A saved simulation file carrying a mesh block.
    overwrite : bool
        Rewrite a sidecar that already exists. Without it an existing
        sidecar is refused, because the file may have been edited by the
        user after it was written.

    Returns
    -------
    Path
        The sidecar written.

    Raises
    ------
    InputArtifactError
        A geometry that cannot be read, that carries no mesh block, or
        whose block does not hold its shape, each naming the file; a
        sidecar that already exists, naming it and ``--overwrite``.
    """
    path = Path(geometry)
    sidecar = inventory_sidecar(path)
    if not path.is_file():
        raise InputArtifactError(
            f"{path} is not a file, so no boundary inventory can be read from it."
        )
    if sidecar.exists() and not overwrite:
        raise InputArtifactError(
            f"{sidecar} already exists; pass overwrite (CLI: --overwrite) to rewrite it "
            "from the mesh block, after checking that the file is the one the sidecar "
            "should describe."
        )
    try:
        names = boundary_names(path)
    except MeshReadError as error:
        raise InputArtifactError(f"{path.name}: {error}") from error
    if not names:
        raise InputArtifactError(
            f"{path} carries no mesh block, so it states no boundary order to write. "
            "A saved simulation (.fsm) carries one; a raw mesh does not, and its order "
            "is only known once the solver has opened it (docs/mesh-inputs.md)."
        )
    body = [
        f"# Boundary inventory of {path.name}, read from its mesh block by "
        "`pyfs-matrix inventory`.",
        "# The solver's own order: the name at position i is boundary i (1-based).",
        f'file = "{path.name}"',
        "boundaries = [",
        *[f'    "{name}",' for name in names],
        "]",
    ]
    sidecar.write_text("\n".join(body) + "\n", encoding="utf-8")
    return sidecar


def read_inventory(sidecar: str | Path) -> tuple[str, ...]:
    """Return the ordered boundary names a sidecar states.

    Raises
    ------
    InputArtifactError
        A sidecar without a ``boundaries`` list of strings, naming it.
    """
    path = Path(sidecar)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise InputArtifactError(
            f"{path} cannot be read as a boundary inventory: {error}"
        ) from error
    names = data.get("boundaries")
    if not isinstance(names, list) or not names or not all(isinstance(n, str) for n in names):
        raise InputArtifactError(
            f"{path} does not state `boundaries` as a non-empty list of strings; "
            "rewrite it from the file with `pyfs-matrix inventory <geometry>`, "
            "overwrite (CLI: --overwrite)."
        )
    return tuple(names)


# --- one subfolder per geometry (PFS-2032.05) ----------------------------------------


@dataclass(frozen=True)
class GeometryMigration:
    """What :func:`migrate_geometry_layout` did to one library.

    Attributes
    ----------
    moved : tuple of (Path, Path)
        Every file moved, as ``(where it was, where it is)``, in the order
        the moves were made: each geometry file, then the sidecars that
        carry its stem.
    kept : tuple of str
        The stems whose folder already existed and was left alone, a flat
        file of that stem included: the folder is the reading's first
        answer, so the migration does not decide which of the two the
        owner meant.
    """

    moved: tuple[tuple[Path, Path], ...]
    kept: tuple[str, ...]


def migrate_geometry_layout(inputs_dir: str | Path) -> GeometryMigration:
    """Move a flat geometry library into one folder per geometry, idempotently.

    Every ``geometries/<stem>.<ext>`` directly under the library moves to
    ``geometries/<stem>/<stem>.<ext>``, and its ``<stem>.boundaries.toml``
    and ``<stem>.provenance.toml`` move with it, so what belongs to one
    geometry sits in one place (PFS-2032.05, design 68 section A3). A
    folder that already exists is left alone with whatever it holds, and a
    second run over the same library moves nothing: nothing here decides
    for the owner. The run records of a workspace are untouched and keep
    reading, because a record names its inputs by file name and hashes
    their bytes, and neither moved.

    Nothing migrates by itself: the resolver reads both layouts, and the
    flat one is not deprecated.

    Parameters
    ----------
    inputs_dir : str or Path
        The workspace ``inputs/`` directory.

    Returns
    -------
    GeometryMigration
        The files moved and the folders left alone.

    Raises
    ------
    InputArtifactError
        A root with no ``inputs/geometries``: there is no library to move,
        and creating one here would hide a wrong path.
    """
    directory = Path(inputs_dir) / "geometries"
    if not directory.is_dir():
        raise InputArtifactError(
            f"{directory} does not exist, so there is no geometry library to migrate: "
            "the root of a campaign workspace carries inputs/geometries (create the "
            "tree with pyfs-workspace init), and the path given holds none.",
            kind="geometry",
            artifact_id=None,
        )
    entries = sorted(directory.iterdir())
    kept = tuple(entry.name for entry in entries if entry.is_dir())
    created: set[Path] = set()
    moved: list[tuple[Path, Path]] = []
    for entry in entries:
        if not entry.is_file() or _is_sidecar(entry.name):
            continue
        folder = directory / entry.stem
        if folder.exists() and folder not in created:
            continue
        if folder not in created:
            folder.mkdir()
            created.add(folder)
        sidecars = [directory / (entry.stem + suffix) for suffix in SIDECAR_SUFFIXES]
        for source in (entry, *[sidecar for sidecar in sidecars if sidecar.is_file()]):
            target = folder / source.name
            source.rename(target)
            moved.append((source, target))
    return GeometryMigration(moved=tuple(moved), kept=kept)
