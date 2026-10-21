"""Input-artifact library of the managed campaign workspace.

Pipeline role: organizes the reusable inputs of a campaign the same
way the workspace organizes its outputs. A support library under
``inputs/`` holds one declarative artifact per file, referenced by a
stable id (the file name stem), so a campaign line can select its
reference data, solver preset, boundary groups, geometry, and profile
by id instead of by path; the pattern is translated from the reference
research workflow. Artifacts are TOML, never executable code:
they are validated by pydantic models at load time and fail with a
didactic message naming the file and the available ids.

AN ID OF A CODED KIND DECLARES THAT KIND, (PFS-2009.01, PFS-2009.03). A reference id
begins with ``r``, a setup id with ``s``, a pproc id with ``p`` (``e``
in legacy releases, when the groups artifact became the post-processing
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
  key-value table; the loader validates recognized solver settings and
  keeps the raw values for later matrix binding. The id
  begins with ``s``.
- ``inputs/pproc/<id>.toml``: the post-processing artifact (PFS-2029.07),
  twelve optional tables (listed on :class:`PprocArtifact`): ``[groups]`` maps a
  product name to one alias string, ``[exports]`` selects the export kinds,
  ``[sections]``, ``[plots]`` and ``[[probes]]`` are the solver definitions,
  ``[products]`` says which files are written after the run. The id begins
  with ``p``, after the PPROC column that carries it.
- ``inputs/geometries/``: staged geometry files of any extension,
  registered by file name; the id is the stem. A geometry sits either
  directly in the folder (the flat layout) or in one subfolder named by
  its stem, ``geometries/30_WB/30_WB.fsm``, with its boundary inventory
  and provenance record beside it (PFS-2032.04); the cell
  says ``30_WB.fsm`` in both cases, and the folder is read first.
- ``inputs/profiles/``: input profile files (for example actuator
  thrust distributions), registered by file name.
- ``inputs/freestreams/``: custom free-stream fields a row's
  ``FREESTREAM`` names by stem (G15), ``<stem>.txt`` in the
  manual's STRUCTURED form or ``<stem>.dat`` in its UNSTRUCTURED form; the
  matrix binding resolves them (``workspace.matrix``).
- ``inputs/calibrations/``: the quasi-steady wheel's calibration files, ``<id>.toml``, which a
pproc's ``[qsteady_correction]`` table
  names by id (:mod:`pyflightstream.cases.corrections`); the plan validates
  the one a row's pproc names, and the post applies it.
- ``inputs/executables.toml``: the build registry, mapping a
  FlightStream build id to its executable path; an explicit override
  path bypasses the registry, and that override is the only way to run
  an unregistered build (the MANUAL mode of the run matrix). An entry
  is a bare path string, or a table carrying that path and, optionally,
  the FlightStream version the build's scripts are emitted under
  (:func:`resolve_build`).

FIVE MODULES (AD-11). The files beside a geometry (the
boundary inventory, the provenance record, the raw-mesh sidecar and the
layout migration) are :mod:`pyflightstream.workspace.sidecars`; the HPC
profile is :mod:`pyflightstream.workspace.hpc`; the build registry is
:mod:`pyflightstream.workspace.builds`; the rule on empty entity selections
is :mod:`pyflightstream.workspace.selections`. This module resolves the
artifacts and re-exports every name of the four at its public path, which
its ``__all__`` lists.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePath, PurePosixPath
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ModelWrapValidatorHandler,
    ValidationError,
    field_validator,
    model_validator,
)

# InputArtifactError is defined in _errors below all layers and re-exported
# here and from workspace. Matrix-binding layers can catch it without an
# upward dependency. The other imports below preserve public import paths
# checked by scripts/check_parity.py.
from pyflightstream._digest import aliased_name_fault as aliased_name_fault
from pyflightstream._digest import file_sha256 as file_sha256
from pyflightstream._errors import InputArtifactError
from pyflightstream._errors import PyflightstreamWarning as PyflightstreamWarning
from pyflightstream._errors import warn as warn
from pyflightstream._fsm import MeshReadError as MeshReadError
from pyflightstream._fsm import boundary_names as boundary_names
from pyflightstream._retired_names import (
    BLOCK_KIND_ENGINE,
    POINT_KIND_ENGINE,
    retired_key,
)
from pyflightstream.cases import EVERY_SURFACE as EVERY_SURFACE
from pyflightstream.cases import (
    ActuatorBlock,
    BoundaryAliases,
    CampaignConfigError,
    CustomFlag,
    FrameSpec,
    PprocSpec,
    RawCommand,
    RotorBlock,
    SolverSettings,
)
from pyflightstream.cases import InputKey as InputKey
from pyflightstream.cases import MeshImport as MeshImport
from pyflightstream.cases import RawMeshConditions as RawMeshConditions
from pyflightstream.cases import TrailingEdgeMarking as TrailingEdgeMarking

# DOWNWARD, and the two imports in this module that leave the workspace
# layer: `cases` sits below `workspace` in the house order, and the
# migration at the foot of this file has to rewrite the REF, SET and
# ENTRY cells of a run matrix in the same call that renames the library
# files. The matrix FORMAT is the cases layer's to own, so the cell
# rewrite is asked of it rather than reimplemented here, which is what
# would put a second reader of the pipe-delimited layout in the package
# (PFS-2009.03).
from pyflightstream.versions import AmbiguousVersionAliasError as AmbiguousVersionAliasError
from pyflightstream.versions import UnknownVersionError as UnknownVersionError
from pyflightstream.versions import resolve as resolve

# DOWNWARD as well, and the lowest layer of the stack: `versions` sits
# below `commands`, which sits below everything else. It is imported so a
# version DECLARED in the build registry is checked against the version
# registry at the moment it is read, rather than at the moment a run
# emits a script under it. The sister module `wake_edges` already reaches
# down to `commands` for the same kind of reason (PFS-2009.05).
from pyflightstream.workspace._geometry_clean import CleanedGeometry as CleanedGeometry
from pyflightstream.workspace._geometry_clean import (
    clean_saved_actions as clean_saved_actions,
)
from pyflightstream.workspace.builds import (
    EXECUTABLE_ENTRY_KEYS,
    EXECUTABLES_FILE,
    LOCAL_EXECUTABLES_FILE,
    RegisteredBuild,
    resolve_build,
    resolve_executable,
)
from pyflightstream.workspace.hpc import (
    HPC_BUILD_ALIAS,
    HPC_DIR,
    HPC_FORMATS,
    HPC_LOG_KEYS,
    HPC_PROFILE_KEYS,
    HPC_REQUIRED,
    WALLTIME_ARITHMETIC,
    HpcProfile,
    descriptor_name_refusal,
    hpc_profiles,
    read_hpc_profile,
    resolve_hpc_profile,
)
from pyflightstream.workspace.selections import (
    ALIASES_TABLE,
    ENTITY_SELECTIONS,
    EntitySelection,
    refuse_empty_selections,
)
from pyflightstream.workspace.sidecars import (
    BASE_REGIONS_TABLE,
    DETECT_EVERYWHERE,
    GEOMETRIES_README,
    GEOMETRY_SIDECAR_KEYS,
    IMPORT_TABLE,
    INVENTORY_SUFFIX,
    OBJ_SUFFIX,
    PROVENANCE_SUFFIX,
    RAW_MESH_CONDITION_KEYS,
    RAW_MESH_CONDITION_TABLES,
    SIDECAR_SUFFIXES,
    TRAILING_EDGE_DETECT_KEYS,
    TRAILING_EDGES_TABLE,
    WAKE_TERMINATION_TABLE,
    ensure_inventory,
    inventory_sidecar,
    is_sidecar,
    load_toml,
    obj_boundary_names,
    read_inventory,
    read_mesh_import,
    read_raw_mesh_conditions,
    write_inventory,
)

__all__ = [
    "ACTUATOR_KIND",
    "ALIASES_TABLE",
    "BASE_REGIONS_TABLE",
    "DETECT_EVERYWHERE",
    "ENTITY_SELECTIONS",
    "EXECUTABLES_FILE",
    "EXECUTABLE_ENTRY_KEYS",
    "FLAGS_TABLE",
    "FRAMES_TABLE",
    "GEOMETRIES_README",
    "GEOMETRY_SIDECAR_KEYS",
    "GROUPS_LETTER",
    "HPC_BUILD_ALIAS",
    "HPC_DIR",
    "HPC_FORMATS",
    "HPC_LOG_KEYS",
    "HPC_PROFILE_KEYS",
    "HPC_REQUIRED",
    "IMPORT_TABLE",
    "INPUT_KINDS",
    "INVENTORY_SUFFIX",
    "KIND_COLUMNS",
    "KIND_LETTERS",
    "LOCAL_EXECUTABLES_FILE",
    "OBJ_SUFFIX",
    "POINT_KINDS",
    "PROVENANCE_SUFFIX",
    "RAW_MESH_CONDITION_KEYS",
    "RAW_MESH_CONDITION_TABLES",
    "RAW_TABLE",
    "ROTOR_FACT_KEYS",
    "SIDECAR_SUFFIXES",
    "STUDY_TABLE",
    "TRAILING_EDGES_TABLE",
    "TRAILING_EDGE_DETECT_KEYS",
    "WAKE_TERMINATION_TABLE",
    "WALLTIME_ARITHMETIC",
    "CleanedGeometry",
    "EntitySelection",
    "HpcProfile",
    "InputArtifactError",
    "PointXyz",
    "PprocArtifact",
    "ReferenceArtifact",
    "RegisteredBuild",
    "RotorReference",
    "SetupArtifact",
    "StudyVocabulary",
    "available_ids",
    "clean_saved_actions",
    "descriptor_name_refusal",
    "ensure_inventory",
    "hpc_profiles",
    "inventory_sidecar",
    "is_valid_artifact_id",
    "obj_boundary_names",
    "read_hpc_profile",
    "read_inventory",
    "read_mesh_import",
    "read_raw_mesh_conditions",
    "refuse_empty_selections",
    "resolve_build",
    "resolve_executable",
    "resolve_geometry",
    "resolve_hpc_profile",
    "resolve_pproc",
    "resolve_profile",
    "resolve_reference",
    "resolve_setup",
    "rotor_integration_groups",
    "write_inventory",
]


INPUT_KINDS = (
    "geometries",
    "references",
    "setups",
    "pproc",
    "profiles",
    "freestreams",
    "calibrations",
    "hpc",
    "fsi",
    "matrices",
    "management",
)

_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

#: The letter a coded artifact id begins with, so the id DECLARES its
#: kind and a mistyped number cannot resolve to another artifact's file.
#:
#: Only the three CODED kinds are here, and their absence from the other
#: two is the rule rather than an omission. A reference, a setup and a
#: pproc artifact are addressed by ids the user writes in the REF, SET
#: and PPROC cells of a run matrix, so a bare ``003`` names three
#: different files in three folders and a typo between them is silent. A
#: geometry is addressed by the NAME OF A FILE THE USER STAGED and a
#: profile by its stem, so a letter rule there would refuse a mesh for
#: being called what it is called.
#:
#: ``p`` for pproc : until then the artifact was the groups
#: file under ``e``, after the ENTRY column that carried it, and
#: Earlier packages migrated both the file and the cell.
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
_POINT_KIND_ENGINE_WORD = "engine"

#: Allowed reference-point kinds (PFS-2029.11.02). The retired spelling
#: engine is handled by pyflightstream._retired_names.
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

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    kind: str | None = None

    @field_validator("kind")
    @classmethod
    def _kind_is_known(cls, value: str | None) -> str | None:
        # THE RETIRED SPELLING FIRST, because it is the likeliest wrong
        # value in an existing workspace and the generic refusal below
        # would send its writer looking for a kind that never existed.
        if value == _POINT_KIND_ENGINE_WORD:
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
        Rotor radius. Optional (PFS-2029.05): the diameter
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
        reads: the two unsteady run types turn it into the rotor's hub frame
        (PFS-2030.03), the frame the reference probe lines and rotor plots
        are defined in and the frame a rotor row turns about unless it
        states ``ROTOR_ORIGIN``.

    Rotor motion belongs to the row, not the reference block (PFS-2029.08). The reference declares
    geometry; the builder reads the row's motion declaration.
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
            "cannot supply to a builder. What a script needs is stated "
            "elsewhere: the hand is rpm_sign on a rotor block of the reference (or RPM_SIGN "
            "on a row whose reference declares no rotor); RPM is a magnitude; and the axis "
            "is ROTOR_AXIS (PFS-2029.08). Drop the key(s), or "
            "use an older package to reach the 0.38.0 format before "
            "pyfs-workspace migrate. See docs/upgrading.md and docs/mesh-inputs.md."
        )


#: The retired rotor motion keys are refused in reference artifacts (PFS-2029.08).
ROTOR_FACT_KEYS: tuple[str, ...] = (
    "rotation",
    "blade_travel",
    "rpm_sign_installed",
    "rpm_sign_isolated",
)


#: The top-level table of a reference that declares the study's vocabulary (FR-980).
STUDY_TABLE = "study"


class StudyVocabulary(BaseModel):
    """The surfaces of a study, ``[study] surfaces`` of a reference artifact (FR-980).

    One setup, one pproc and one reference may serve every model of a study
    only if a name one model lacks can be told from a misspelling. The table
    is where the study says which names it uses: with the reference's aliases
    and their members it is the vocabulary a cited name is judged against.

    Attributes
    ----------
    surfaces : tuple of str
        The boundary names or family words the models of the study carry,
        at least one.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    surfaces: tuple[str, ...] = Field(min_length=1)


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
        this package reads one field, the position (the rotor hub
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
    body_axes : dict of str to str
        Which model axis, ``X``, ``Y`` or ``Z``, each body rate turns about,
        keyed ``roll``, ``pitch`` and ``yaw``.
    rotor : RotorReference, optional
        Rotor block, present for propulsive configurations.
    aliases : dict of str to list of str
        Names for groups of boundaries, each standing for the boundary names,
        families or aliases listed under it.
    frames : list of FrameSpec
        The custom coordinate systems of the configuration, in the order
        written.
    rotors : dict of str to RotorBlock
        One rotor per top-level table stating ``kind = "rotor"``.
    actuators : dict of str to ActuatorBlock
        One actuator disc per top-level table stating ``kind = "actuator"``.
    points : dict of str to PointXyz
        One named point per top-level table stating another point ``kind``.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    area_m2: float = Field(gt=0.0)
    chord_m: float = Field(gt=0.0)
    span_m: float = Field(gt=0.0)
    rotor_diameter_m: float | None = Field(default=None, gt=0.0)
    moment_point: PointXyz = Field(default_factory=PointXyz)
    #: WHICH MODEL AXIS EACH BODY RATE TURNS ABOUT: ``roll``,
    #: ``pitch`` and ``yaw`` to ``X``, ``Y`` or ``Z``. A mesh is built in
    #: whatever orientation its author chose, so a row stating a body rate
    #: needs the configuration to say which axis is which; the values are
    #: checked where they reach the case. A configuration that declares none
    #: is a configuration no row may turn.
    body_axes: dict[str, str] = Field(default_factory=dict)
    rotor: RotorReference | None = None
    #: The boundary aliases the ``[aliases]`` table declares (FR-59). They lived in the setup
    #: preset,
    #: which is per condition where this artifact is per configuration; a
    #: boundary name is not a solver setting. A member may be another
    #: alias, resolved to the end by
    #: :func:`pyflightstream.cases.resolve_alias`. Every rotor block's own
    #: name is added here by :func:`resolve_reference`, standing for
    #: everything that rotor owns.
    aliases: BoundaryAliases = Field(default_factory=dict)
    #: The custom coordinate systems the ``[[frames]]`` table defines
    #: (FR-72), in the order written. They lived in the setup preset at
    #: a coordinate system is geometric data, and the frames a
    #: rotor instantiates were always derived from this file.
    frames: list[FrameSpec] = Field(default_factory=list)
    #: One entry per rotor, keyed by the block's name, read out of every
    #: top-level table whose ``kind`` is ``rotor`` (FR-60). THE KEY EQUALS
    #: :attr:`~pyflightstream.cases.RotorBlock.alias`, which is the word a
    #: row moves, so a caller iterating this mapping may use either.
    rotors: dict[str, RotorBlock] = Field(default_factory=dict)
    #: One entry per actuator disc, keyed by the block's name, read out of
    #: every top-level table whose ``kind`` is ``actuator`` (G06). The name is
    #: what a row's ``ACTUATOR`` cites; a disc no row names emits nothing.
    actuators: dict[str, ActuatorBlock] = Field(default_factory=dict)
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
    #: is how a user writes one.
    points: dict[str, PointXyz] = Field(default_factory=dict)
    #: THE STUDY'S VOCABULARY (FR-980): the top-level ``[study]`` table that
    #: states no ``kind`` and one key, ``surfaces``. A setup or pproc name the
    #: vocabulary holds and a row's model lacks is skipped and said at plan; a
    #: name it does not hold is refused there. None for a reference declaring
    #: none, which keeps the reading of every name a row cites.
    study: StudyVocabulary | None = None

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

    The file's solver fields are validated at read time with SolverSettings.
    The raw values remain in :attr:`settings` alongside non-solver entries
    for matrix binding, without inserting defaults or coercing stored values.

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
    #: DEPRECATED (FR-72): the table's home is the REFERENCE
    #: artifact, because a coordinate system is geometric data. A preset
    #: still stating it is REFUSED when a row binds it, naming the
    #: reference to move the table into. The field survives so that the
    #: refusal can name what it found.
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
    #: The boundary aliases the ``[aliases]`` table defines : a name to the boundary names or
    #: families it stands
    #: for, read wherever a boundary is cited (a matrix cell, a pproc
    #: group, a families entry), a member the mesh lacks ignored; consumed
    #: out of ``settings`` by :func:`resolve_setup` the same way.
    #:
    #: DEPRECATED (FR-59): the table's home is the REFERENCE
    #: artifact, which is per configuration where a preset is per
    #: condition. A preset still stating it is REFUSED when a row binds it,
    #: naming the reference to move the table into. The field survives so
    #: that the refusal can name what it found.
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
#: by the goal checker and by the documentation; change it here
#: and both follow.
FRAMES_TABLE = "frames"
#: The table of a setup artifact that states solver commands verbatim
#: (PFS-2033.01): ``[[raw]]``, one entry per line with ``command`` and
#: ``before``. Read by the goal checker and the documentation.
RAW_TABLE = "raw"

#: The table a setup preset declares its custom flags in (PFS-2035.20).
#: One record per flag: the word a matrix row writes, and the
#: FlightStream command it becomes.
FLAGS_TABLE = "flags"


class PprocArtifact(PprocSpec):
    """The post-processing artifact (``inputs/pproc/<id>.toml``).

    PFS-2029.07.01, the groups artifact IS the
    home of post-processing and is renamed. The file carries twelve tables,
    every one optional: ``[groups]`` maps each product name to one alias string;
    define several members in the reference's ``[aliases]`` table;
    ``[exports]`` which of the export kinds a point writes, where the
    loads table and the saved simulation cannot be switched off and a steady point's solver
    plots (``plot_residuals``,
    ``plot_loads``, ``plot_sections_cp``) can;
    ``[sections]``, ``[plots]`` and ``[[probes]]`` the solver definitions
    the builders emit; ``[products]`` the post-processed files written
    after the run; ``[phase_locked]``, ``[equations]``,
    ``[glossary]`` and ``[names]``, which the post stage reads;
    ``[time_averaging]`` the surface window; and ``[volume_section]``, the one flow-field plane
    a steady point cuts and
    exports. Group aliases are stored
    verbatim and resolved by the script layer at emission time. Member lists,
    including empty lists, are refused. The
    shape is
    :class:`pyflightstream.cases.PprocSpec`; this class is the file.

    Validation refusals raise :class:`InputArtifactError`, including refusals
    from nested tables. Field constraints retain the invalid field's location;
    the artifact loader adds the source file's path.

    Examples
    --------
    Use the built-in ``all`` only when no reference alias or boundary has that
    name; otherwise declare a unique reference alias with the intended members.
    The input is one string; the model normalizes it to a one-member list.

    >>> PprocArtifact(groups={"TOTAL": "all"}).groups
    {'TOTAL': ['all']}
    >>> PprocArtifact(groups={"AIRFRAME": "airframe"}).groups
    {'AIRFRAME': ['airframe']}
    """

    @model_validator(mode="wrap")
    @classmethod
    def _artifact_refusals(
        cls, data: Any, handler: ModelWrapValidatorHandler[PprocArtifact]
    ) -> PprocArtifact:
        """Keep the artifact's public error class across all validation routes."""
        try:
            return handler(data)
        except ValidationError as error:
            messages = []
            for detail in error.errors():
                message = str(detail.get("ctx", {}).get("error", detail["msg"]))
                location = ".".join(str(part) for part in detail["loc"])
                # Custom validator messages already name their domain input.
                # Pydantic's field constraints need the separate location.
                if location and detail["type"] != "value_error":
                    message = f"{location}: {message}"
                messages.append(message)
            raise InputArtifactError("\n".join(messages), kind="pproc") from error


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
    characters sends a user back to make the same mistake.

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
    return _ID_PATTERN.fullmatch(artifact_id) is not None


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
            "the id, not a prefix the library adds or strips. This format predates "
            "0.38.0. Use an older package to reach 0.38.0, then pyfs-workspace migrate. "
            "See docs/upgrading.md.",
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


def _validate(model: type[BaseModel], data: dict[str, Any], path: Path, kind: str) -> BaseModel:
    """Validate one artifact table, naming the file on a model error."""
    try:
        return model.model_validate(data)
    except (ValidationError, InputArtifactError) as error:
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
    data = load_toml(path, "reference")
    _refuse_a_study_table_of_another_shape(data, path)
    return _validate(ReferenceArtifact, _split_reference_tables(data, path), path, "reference")


def _refuse_a_study_table_of_another_shape(data: Mapping[str, Any], path: Path) -> None:
    """Refuse a ``[study]`` table that states anything but a list of names (FR-980).

    A table named ``study`` that states a ``kind`` is a block like any other
    and is left to the reader, as it was before the vocabulary existed.

    Raises
    ------
    InputArtifactError
        The table states a key other than ``surfaces``, or ``surfaces`` is
        missing, empty, or not a list of non-blank strings; the message names
        the reference file and the table.
    """
    table = data.get(STUDY_TABLE)
    if not isinstance(table, dict) or "kind" in table:
        return
    others = sorted(str(key) for key in table if key != "surfaces")
    surfaces = table.get("surfaces")
    names = isinstance(surfaces, list) and all(
        isinstance(name, str) and name.strip() for name in surfaces
    )
    if not others and names and surfaces:
        return
    what = (
        f"the key {', '.join(others)}, which it does not read"
        if others
        else f"surfaces = {surfaces!r}, which is not a non-empty list of names"
    )
    raise InputArtifactError(
        f"the reference artifact {path} declares [{STUDY_TABLE}] with {what}. The table "
        "states one key, surfaces, the boundary names or family words the models of the "
        'study carry, for example surfaces = ["Wing", "Body", "Base"] (FR-435).',
        kind="reference",
    )


#: The keys only a rotor block carries. A top-level table stating one of
#: these and no ``kind`` is a rotor that forgot to say so, and is refused
#: with that sentence rather than as an unknown key.
_ROTOR_ONLY_KEYS = ("families_blades", "families_general", "diameter_m", "rpm_sign", "blade1")

#: The ``kind`` of a reference block that is an actuator disc (G06), and the
#: keys only such a block carries, for the refusal of one that forgot its kind.
ACTUATOR_KIND = "actuator"
_ACTUATOR_ONLY_KEYS = ("tip_radius_m", "hub_radius_m", "profile_units", "swirl")

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
    """Refuse a reference that uses a word this package retired.

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
        if isinstance(value, dict) and value.get("kind") == _POINT_KIND_ENGINE_WORD:
            raise InputArtifactError(
                f"the reference artifact {path} declares [{key}] with "
                f"{BLOCK_KIND_ENGINE.message()}",
                kind="reference",
            )


def _lifted_table(path: Path, table: str, value: Any) -> Any:
    """Return a reference artifact's ``[aliases]`` or ``[[frames]]`` value, refusing a wrong shape.

    PFS-2095.058: a ``[frames]`` table (single brackets) or a list of aliases
    crashed with AttributeError or ValueError. Refused here in the words
    :func:`resolve_setup` uses for the same mistakes in a preset.
    """
    if table == FRAMES_TABLE and (
        not isinstance(value, list) or not all(isinstance(entry, dict) for entry in value)
    ):
        raise InputArtifactError(
            f"the reference artifact {path} states [{FRAMES_TABLE}] as {value!r}, "
            f"and the table is a list of records: write [[{FRAMES_TABLE}]] once per frame "
            "with name, origin and optionally x_axis and y_axis.",
            kind="reference",
        )
    if table == ALIASES_TABLE and (
        not isinstance(value, dict) or not all(isinstance(v, list) for v in value.values())
    ):
        bad = (
            sorted(k for k, v in value.items() if not isinstance(v, list))
            if isinstance(value, dict)
            else [repr(value)]
        )
        raise InputArtifactError(
            f"the reference artifact {path} states [{ALIASES_TABLE}] with "
            f"{', '.join(bad)} not a list: an alias is a name and the list of boundary names "
            f'or families it stands for, as lifters = ["LiftBlade", "Hub1"].',
            kind="reference",
        )
    return value


def _refuse_a_kindless_block(name: str, value: dict[str, Any], path: Path) -> None:
    """Refuse a block that states a rotor's or a disc's own keys and no ``kind``."""
    # Identify a missing rotor kind from rotor-only keys and give a rotor
    # remedy instead of the generic extra-inputs refusal.
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
    # Likewise identify an actuator disc missing kind (G06), excluding the
    # model's own tables: hub_radius_m is also valid under [rotor]. Let the
    # model validate those tables (G47).
    disc = sorted(key for key in _ACTUATOR_ONLY_KEYS if key in value)
    if disc and name not in ReferenceArtifact.model_fields:
        raise InputArtifactError(
            f"the reference artifact {path} declares [{name}] with "
            f"{', '.join(disc)} and no kind. A block that states an actuator "
            'disc\'s own keys is a disc, and a disc says so: add kind = "actuator" '
            "to it.",
            kind="reference",
        )


def _split_reference_tables(data: dict[str, Any], path: Path) -> dict[str, Any]:
    """Sort a reference file's top-level tables into the model's fields (FR-59, FR-60, FR-72).

    Three of them are not fixed keys and cannot be, because their names
    belong to the study: one table per rotor, keyed by the word a row
    moves. So this function does for the reference what
    :func:`resolve_setup` does for the preset, and reads the file's shape
    rather than requiring the user to nest it:

    * a table declaring ``kind = "rotor"`` is a rotor and goes to
      ``rotors``; the block's NAME becomes an alias over everything the
      rotor owns, the general families first, so a row citing it moves the
      spinner with the blades;
    * a table declaring ``kind = "actuator"`` is an actuator disc and goes to
      ``actuators`` (G06); its name may be no rotor's, alias's or frame's;
    * a table declaring any other point ``kind`` goes to ``points``;
    * ``[aliases]`` and ``[[frames]]`` are lifted by name.

    A block whose ``alias`` differs from its name is refused here rather
    than in the model, because the model never sees the name: the name is
    the key this function reads.
    """
    _refuse_a_retired_spelling(data, path)
    rest = dict(data)
    aliases = dict(_lifted_table(path, ALIASES_TABLE, rest.pop(ALIASES_TABLE, {})))
    frames = _lifted_table(path, FRAMES_TABLE, rest.pop(FRAMES_TABLE, []))
    rotors: dict[str, Any] = {}
    points: dict[str, Any] = {}
    actuators: dict[str, Any] = {}
    for name, value in list(rest.items()):
        if not isinstance(value, dict):
            continue
        if "kind" not in value:
            _refuse_a_kindless_block(name, value, path)
            continue
        if name == "moment_point":
            # The moment reference is a fixed table of the model, and its own kind key
            # (rotor or airframe) names what the point is: it is never rerouted to the
            # named points, which would reset the moment reference to the origin.
            continue
        if value.get("kind") == ACTUATOR_KIND:
            # G06: A DISC IS NEITHER A ROTOR NOR A POINT, and it is routed before
            # the branch below sends every kind that is not a rotor to the points.
            actuators[name] = rest.pop(name)
            continue
        if value.get("kind") != "rotor":
            points[name] = rest.pop(name)
            continue
        block = rest.pop(name)
        stated = block.get("alias")
        # Compare aliases without case, so pusher under [PUSHER] names one alias.
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
        for family_key in ("families_general", "families_blades"):
            if family_key in block and not isinstance(block[family_key], list):
                raise InputArtifactError(
                    f"the reference artifact {path} declares the rotor {name!r} with "
                    f"{family_key} = {block[family_key]!r}. A rotor's families are a list of "
                    f'names, for example {family_key} = ["Blade_1", "Blade_2"].',
                    kind="reference",
                )
        block.setdefault("alias", name)
        rotors[name] = block
        members = [*block.get("families_general", []), *block.get("families_blades", [])]
        # The rotor's name is an alias over its own members. Refuse a handwritten
        # alias of the same name rather than silently shadowing either membership.
        # Compare without case, as for the alias= check above.
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
    # Check both sides: a rotor cannot take its frames' names, and neither a
    # frame nor an alias can take the names of a rotor's frames.
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
        # Catch AliasCycleError here, where the artifact path is known, so the
        # refusal names both the cycle and its file. Resolve against an empty
        # inventory: cycles depend only on the alias table, not geometry members.
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
    # A DISC'S NAME IS THE WORD A ROW'S `ACTUATOR` CITES (G06), so it may not
    # also be an alias's (which every rotor's name is, above) or a frame's: one
    # word would then name two things in one file. Case folded, as every other
    # name comparison of this file is.
    for name in actuators:
        if not re.fullmatch(r"[A-Za-z0-9_.\-]+", name):
            raise InputArtifactError(
                f"the reference artifact {path} declares the actuator disc {name!r}. Its name "
                "is the actuator's name on the solver's command line, which is read word by "
                "word, so it is one word of letters, digits, dots, underscores and hyphens.",
                kind="reference",
            )
        taken = [
            what
            for what, names in (
                ("rotor or alias", list(aliases)),
                ("frame", [str(frame.get("name", "")) for frame in frames]),
            )
            if any(other.casefold() == name.casefold() for other in names)
        ]
        if taken:
            raise InputArtifactError(
                f"the reference artifact {path} declares the actuator disc {name!r} and "
                f"a {' and a '.join(taken)} of the same name. A row's ACTUATOR cites the "
                "disc by that word, so it names one thing in this file; rename one of them.",
                kind="reference",
            )
    if rotors:
        rest["rotors"] = rotors
    if actuators:
        rest["actuators"] = actuators
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

    Recognized solver fields are validated with SolverSettings before returning
    the raw table in :attr:`SetupArtifact.settings`. Non-solver entries retain
    their later matrix-binding validation.

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
        TOML or solver settings outside the model's declared bounds.
    """
    _check_id(artifact_id, "setup")
    directory = Path(inputs_dir) / "setups"
    path = directory / f"{artifact_id}.toml"
    if not path.is_file():
        raise _miss("setup", artifact_id, directory)
    data = load_toml(path, "setup")
    refuse_empty_selections("setup", path, data)
    try:
        SolverSettings.model_validate(
            {key: value for key, value in data.items() if key in SolverSettings.model_fields}
        )
    except ValidationError as error:
        raise InputArtifactError(
            f"setup preset {artifact_id!r} ({path}) does not fit the case solver settings: {error}"
        ) from error
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
    # Aliases map names to boundaries wherever a boundary is cited; they are
    # not solver settings.
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
    not that (PFS-2005.04): in legacy releases this reader refused the
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
    data = load_toml(path, "pproc")
    # A model field is never a legacy top-level group, whatever its type. Read
    # PprocArtifact.model_fields rather than duplicating its list-valued fields,
    # including probes and vtk_variables; let the model validate their contents.
    own_keys = PprocArtifact.model_fields
    bare = sorted(
        key for key, value in data.items() if isinstance(value, list) and key not in own_keys
    )
    if bare:
        raise InputArtifactError(
            f"the pproc artifact {path} carries group(s) {', '.join(bare)} at the top "
            "level, which is a legacy groups-artifact shape. A pproc "
            "file holds its groups under a [groups] table, beside [exports], "
            "[sections], [plots], [[probes]] and [products]; "
            "this format predates 0.38.0. Use an older package to reach 0.38.0, "
            "then pyfs-workspace migrate. See docs/upgrading.md."
        )
    refuse_empty_selections("pproc", path, data)
    return _validate(PprocArtifact, data, path, "pproc")


#: The kind letter a groups id carried in legacy releases, when the kind was
#: renamed pproc (PFS-2029.07): ``e`` for ENTRY, the column that named it.
GROUPS_LETTER = "e"


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

    THE CELL CARRIES THE FILE NAME WITH ITS EXTENSION
    (PFS-2029.09, amending
    PFS-2009.01): ``30_WB.fsm`` resolves to ``inputs/geometries/30_WB.fsm``
    and ``blade.v2.fsm`` to that one file, one reading and no other. What
    it buys is that the cell says what the file IS: a ``.fsm`` is a saved
    simulation with its boundary conditions in it, a mesh is not, and the
    workflow can tell the two apart before any seat is spent.

    TWO LAYOUTS, THE FOLDER READ FIRST (PFS-2032.04). ``30_WB.fsm`` resolves to
    ``geometries/30_WB/30_WB.fsm`` when that folder exists and to
    ``geometries/30_WB.fsm`` otherwise, so the cell does not change and
    no matrix written breaks. What the folder buys is a home
    for the files that belong to one geometry: its boundary inventory and
    its provenance record sit beside it, and a point staged from the
    folder shows that geometry's files and never the whole library
    (:meth:`~pyflightstream.workspace.CampaignWorkspace.stage_inputs`).
    The flat layout remains supported.

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

    Examples
    --------
    >>> import tempfile
    >>> from pathlib import Path
    >>> from pyflightstream._errors import InputArtifactError
    >>> from pyflightstream.workspace.inputs import resolve_geometry
    >>> with tempfile.TemporaryDirectory() as folder:
    ...     geometries = Path(folder) / "geometries"
    ...     geometries.mkdir()
    ...     _ = (geometries / "wing.fsm").write_text("")
    ...     print(resolve_geometry(Path(folder), "wing.fsm").name)
    ...     try:
    ...         resolve_geometry(Path(folder), "wing")
    ...     except InputArtifactError:
    ...         print("a bare stem is refused")
    wing.fsm
    a bare stem is refused
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
    clashes: dict[str, list[Path]] = {}
    found = _staged_geometries(directory, clashes)
    staged = sorted(found)
    stem, suffix = PurePath(name).stem, PurePath(name).suffix
    if not suffix:
        _check_id(name, "geometry")
        candidates = [f for f in staged if PurePath(f).stem == name]
        if candidates:
            raise InputArtifactError(
                f"geometry {name!r} is a bare stem, and the GEOMETRY cell "
                f"carries the file name with its extension: write GEOMETRY: "
                f"{' or GEOMETRY: '.join(candidates)} (the file(s) under {directory} "
                "carrying that stem). This layout predates 0.38.0; see docs/upgrading.md.",
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
    if name in clashes:
        raise InputArtifactError(
            f"geometry {name!r} is derived by more than one folder under {directory}: "
            f"{', '.join(str(path.relative_to(directory)) for path in clashes[name])}. A "
            "cell names a file, and two folders offering the same file name leave it "
            "ambiguous which one the row meant; rename or remove one of them.",
            kind="geometry",
            artifact_id=name,
        )
    return found[name]


def _staged_geometries(
    directory: Path, clashes: dict[str, list[Path]] | None = None
) -> dict[str, Path]:
    """Map every staged geometry file name to its path, both layouts read.

    A file directly under ``geometries/`` is the flat layout. A folder
    ``geometries/<stem>/`` is one geometry's home (PFS-2032.04), and the
    geometry files in it carry the folder's stem or a derived thin-blade
    OBJ stem (including a selected boundary). Thus
    its ``<stem>.boundaries.toml`` (stem ``<stem>.boundaries``) and its
    provenance record are not offered as geometries a cell could name;
    a flat sidecar is left out by its suffix for the same reason. The
    folder is read first: a file in it stands in front of a flat file of
    the same name, which is the order the reading states.

    AND THE FOLDER'S OWN README IS NOT A GEOMETRY. ``init`` writes one
    there (PFS-2032.07), and without this the refusal that lists what the
    library holds offered it as a file a GEOMETRY cell could name. That is
    not cosmetic: the list exists to be read by somebody who has just
    mistyped a mesh name, and a refusal that suggests the instruction page
    as the thing they meant is worse than one that lists nothing. Caught
    by an existing test asserting the whole tuple, which is why it is
    asserted as the whole tuple.
    """
    if not directory.is_dir():
        return {}
    found: dict[str, Path] = {}
    in_folder: dict[str, Path] = {}
    for entry in sorted(directory.iterdir()):
        if entry.is_file():
            if not is_sidecar(entry.name) and entry.name != GEOMETRIES_README:
                found.setdefault(entry.name, entry)
        elif entry.is_dir():
            for path in sorted(entry.iterdir()):
                derived = (
                    path.suffix.lower() == ".obj"
                    and path.stem.startswith(entry.name + "_")
                    and path.stem.endswith("_thin_blade")
                )
                if path.is_file() and (path.stem == entry.name or derived):
                    if path.name in in_folder and clashes is not None:
                        clashes.setdefault(path.name, [in_folder[path.name]]).append(path)
                    in_folder[path.name] = found[path.name] = path
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


def rotor_integration_groups(
    rotors: Mapping[str, object],
    declared: Mapping[str, Sequence[int | str]],
) -> dict[str, list[int | str]]:
    """Return the pproc's groups with one integration group per DECLARED rotor.

     an integration group is always created for each rotor that
    does not already have one.

    WHY IT IS CREATED RATHER THAN REQUIRED. The rotor table integrates thrust
    and torque over ONE rotor's own families. Left to a user remembering to
    declare the group, the coefficient and the group are two lists kept in step
    by hand, and the day they drift one rotor's thrust is reported under
    another rotor's coefficient -- a number that looks right and is wrong,
    which is the same class as a rotor turning the wrong way. Created from the
    rotor itself, the group and the coefficient agree by construction.

    THE CREATED GROUP IS A NORMAL GROUP. It takes the rotor's ALIAS as its name
    and the rotor's own families as its members, general families first and
    then the blades, so it produces its own products like any other group. A
    group that exists but is invisible is the kind of thing nobody can debug.

    A GROUP THE USER DECLARED IS NEVER REPLACED. Creation fills a gap; it does
    not overrule what the user wrote.

    Parameters
    ----------
    rotors : mapping of str to object
        The pproc's rotor blocks by alias; each block's ``members`` are the
        rotor's families.
    declared : mapping of str to sequence of int or str
        The groups the pproc declares, by name, with their members. A group
        whose only member names a rotor is read as that rotor's families.

    Returns
    -------
    dict of str to list of int or str
        The declared groups, with each rotor's integration group added under the
        rotor's alias when none was declared.

    Raises
    ------
    CampaignConfigError
        If a DECLARED group takes a rotor's alias and its members are not that
        rotor's families. The two then disagree about what the alias means, and
        silently preferring either one attributes one rotor's loads to another
        rotor's coefficient. The message names BOTH sets, because a refusal
        that names only the alias sends the reader to two files to find out
        which half is wrong.
    """
    resolved: dict[str, list[int | str]] = {
        name: list(members) for name, members in declared.items()
    }
    # A GROUP THAT NAMES A ROTOR IS THAT ROTOR'S FAMILIES. A group is one
    # alias, and a rotor's alias is the one name for its families, so
    # `PUSHER = "PUSHER"` and `PROP = "PUSHER"` both mean the rotor. Expanded
    # here, before the agreement check below, which would otherwise read the
    # rotor's own name as a family that is not the rotor's.
    by_name = {str(alias).casefold(): block for alias, block in rotors.items()}
    for name, stated in list(resolved.items()):
        if len(stated) == 1 and str(stated[0]).casefold() in by_name:
            block = by_name[str(stated[0]).casefold()]
            resolved[name] = [str(member) for member in getattr(block, "members", [])]
    for alias, block in rotors.items():
        members = [str(name) for name in getattr(block, "members", [])]
        # Aliases compare case-folded, as everywhere in this file: a group
        # `pusher` IS rotor PUSHER's, checked against it, never a second group.
        matching = [k for k in resolved if k.casefold() == str(alias).casefold()]
        if not matching:
            resolved[alias] = list(members)
            continue
        owned = {name.casefold() for name in members}
        # EVERY group of the alias's name is checked, not the first one met: a
        # second spelling that disagrees would otherwise pass or fail by the
        # order the pproc listed them in.
        group = next(
            (k for k in matching if {str(name).casefold() for name in resolved[k]} != owned),
            None,
        )
        if group is not None:
            raise CampaignConfigError(
                f"the pproc declares a group named {group!r}, which is a rotor's alias, "
                f"and its members are {sorted(resolved[group], key=str)}; that rotor's own "
                f"families are {sorted(members)}. The two disagree about what {alias!r} means, "
                "and a "
                "rotor coefficient integrated over the wrong families is a number that looks "
                "right and is wrong. Rename the group, or give it the rotor's families"
            )
    return resolved
