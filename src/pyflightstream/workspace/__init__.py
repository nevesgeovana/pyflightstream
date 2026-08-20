"""Managed campaign workspace: inputs, run files, and the manifest.

Pipeline role: owns where campaign files live, inputs and outputs
alike. Folder layout, the reusable input-artifact library, staging of
solver inputs, collection of outputs, and archiving are managed by the
package, not by the user: folder identity mistakes were a recurring
failure mode in the predecessor toolchain. Run identity lives in the
manifest (``runs.json``), never in folder or file names; names are
generated, English, and stable, and are never parsed for meaning (SAD
Section 6). Human-readable names come from the output-only
:class:`~pyflightstream.workspace.naming.NamingTemplate`.

The managed layout under a user-chosen campaign root, created by
:meth:`CampaignWorkspace.init` (or ``pyfs-workspace init``):

- ``runs.json``: the authoritative manifest, one record per executed
  point.
- ``inputs/``: the reusable input-artifact library
  (:mod:`pyflightstream.workspace.inputs`): ``geometries/``,
  ``references/``, ``setups/``, ``groups/``, ``profiles/``, plus the
  ``executables.toml`` build registry; artifacts are declarative TOML
  resolved by stable id.
- ``sims/sim_<sim_id>/``: per-simulation folder with ``inputs/``
  (staged copies with recorded sha256), ``scripts/`` (generated script
  text per point), ``raw/`` (solver outputs as produced), and
  ``parsed/`` (typed extracts).
- ``post/``: post-processing products (sweep tables and exports built
  by reading the manifest).
- ``archive/``: zipped completed simulations, manifest-driven.

Archiving and cleaning refuse to act when the manifest is missing or
does not record the target simulation, so file management can never
destroy an unrecorded run.

This package was renamed from ``pyflightstream.files`` in v0.3.0. The
old module name re-exported everything with a DeprecationWarning for
one minor release and was REMOVED at v0.4.0, on the horizon its own
deprecation entry recorded; importing it now raises ImportError.
"""

from __future__ import annotations

import enum
import json
import re
import shutil
import sys
import tomllib
import zipfile
from collections.abc import Sequence
from pathlib import Path

if sys.version_info >= (3, 12):
    from typing import TypedDict
else:  # pragma: no cover - the 3.11 leg of the support range
    # pydantic cannot build a schema from `typing.TypedDict` below 3.12,
    # and the floor of this package is 3.11, so the runtime import has to
    # branch. `typing_extensions` is pydantic's own hard dependency, so it
    # is present wherever this package is.
    from typing_extensions import TypedDict

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pyflightstream._digest import file_sha256
from pyflightstream._errors import PyflightstreamError
from pyflightstream.workspace.inputs import (
    EXECUTABLES_FILE,
    INPUT_KINDS,
    KIND_LETTERS,
    GroupsArtifact,
    IdMigration,
    InputArtifactError,
    PointXyz,
    PropellerReference,
    ReferenceArtifact,
    RegisteredBuild,
    SetupArtifact,
    migrate_input_ids,
    resolve_build,
    resolve_executable,
    resolve_geometry,
    resolve_group,
    resolve_profile,
    resolve_reference,
    resolve_setup,
)
from pyflightstream.workspace.naming import NamingTemplate, NamingTemplateError
from pyflightstream.workspace.trailing_edges import (
    TrailingEdge,
    extract_trailing_edge,
    write_trailing_edge_node_file,
)

__all__ = [
    "EXECUTABLES_FILE",
    "INPUT_KINDS",
    "KIND_LETTERS",
    "KNOWN_MANIFEST_SCHEMAS",
    "MANIFEST_SCHEMA",
    "REFERENCE_POINTS_FILE",
    "STEM_REGISTERED_KINDS",
    "BrokenCommandRecord",
    "CampaignWorkspace",
    "GroupsArtifact",
    "IdMigration",
    "InputArtifactError",
    "NamingTemplate",
    "NamingTemplateError",
    "PointXyz",
    "PropellerReference",
    "ReferenceArtifact",
    "ReferencePoints",
    "RegisteredBuild",
    "RunRecord",
    "RunStatus",
    "SetupArtifact",
    "TrailingEdge",
    "WorkspaceError",
    "check_reference_point_names",
    "check_unique_stems",
    "collection_name",
    "expand_group",
    "extract_trailing_edge",
    "migrate_input_ids",
    "resolve_build",
    "write_trailing_edge_node_file",
]

#: Layout identifier of a manifest record. Bumped when a field is
#: removed or changes meaning, never for an addition: a reader written
#: against "1" keeps working when a field it does not know appears, and
#: must refuse when the value is one it has never seen. Recorded on
#: every row rather than once per file, because a manifest accumulates
#: rows across package versions (PYFS-015).
#:
#: IT MOVED TO "2" ON 2026-08-19 (PFS-2012.03) and the reason is exactly
#: the rule above rather than an exception to it. ``source_version`` of a
#: ``broken_commands`` entry stopped being optional, so the ABSENCE of
#: that key changed meaning: under "1" it meant "written before the field
#: existed", and under "2" there is no row that may lack it. Two fields
#: were ADDED in the same release, ``fs_version_source`` and
#: ``velocity_requested_m_s``, and neither of them moved this constant,
#: which is the half of the rule that is easy to lose.
MANIFEST_SCHEMA = "pyfs-manifest/2"

#: Every stamp this version can still READ, newest last. The bump above
#: is a change of what may be WRITTEN, and a reader that refused every
#: older stamp would make a bump equivalent to deleting the manifests
#: that came before it: nothing in this package migrates a manifest, so
#: there would be no route back. A stamp outside this tuple is refused,
#: which is the "must refuse when the value is one it has never seen"
#: half, and that includes a stamp from a LATER version.
KNOWN_MANIFEST_SCHEMAS = ("pyfs-manifest/1", "pyfs-manifest/2")


def collection_name(declared: str | Path) -> str:
    r"""Return the name a declared output takes once collected.

    Collection MOVES each declared output into ``raw/`` under its base
    name, so any directory part of the declared name is dropped: both
    ``loads.txt`` and ``out/loads.txt`` become ``raw/loads.txt``.

    This is a module-level function rather than an inline expression
    because two layers have to agree on it, and when they did not, the
    disagreement cost a licensed solver seat. :meth:`collect_outputs`
    keyed on the base name and the campaign's plan-time check keyed on
    the DECLARED string, so a case declaring ``a/loads.txt`` and
    ``b/loads.txt`` planned as READY and was refused only after the
    solver had run (PLN-20260802-1904). Both sides now call this, so
    neither can re-derive the rule.

    Both separators are accepted regardless of platform, because the
    declared name comes from a campaign file that may have been
    authored anywhere, while the produced path is local. Treating
    ``a\loads.txt`` as a directory on Windows and as a filename on
    POSIX would make the two boundaries disagree by operating system.

    Parameters
    ----------
    declared : str or Path
        Declared output name, or a produced path.

    Returns
    -------
    str
        Base name, with any directory part removed.
    """
    return str(declared).replace("\\", "/").rsplit("/", 1)[-1]


_SIM_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_SIM_SUBDIRS = ("inputs", "scripts", "raw", "parsed")

# Comment-only template written by init when no registry exists yet;
# didactic: shows the entry shape without registering a fake build.
_EXECUTABLES_TEMPLATE = """\
# FlightStream build registry of this workspace (one entry per build).
#
# A bare path is the short form, and a build written this way declares no
# version: its rows are emitted under the campaign's default version.
#   "26.120" = "C:/path/to/FlightStream.exe"
#
# A table declares the version this build's scripts are emitted under, which
# is what lets ONE run matrix send different rows to different builds. The
# version is checked against the registry when this file is read, so a
# typo is refused here rather than at the first emission.
#   "26.123" = { path = "C:/path/to/FlightStream.exe", version = "26.123" }
#
# resolve_executable(build_id) reads the path and resolve_build(build_id)
# reads both; an explicit override path is the only way to run an
# unregistered build, and it declares no version either.
"""


class WorkspaceError(PyflightstreamError, RuntimeError):
    """A file-management operation was refused or impossible.

    The refusals protect run evidence: archiving or cleaning without a
    manifest record would destroy a run the manifest cannot account
    for, and collection of a declared output that the solver never
    produced points at an incomplete run.
    """


class RunStatus(enum.StrEnum):
    """Terminal status of one executed campaign point (SAD Section 7).

    Every executed point lands in exactly one of these; a silent skip
    is structurally impossible in the campaign loop.
    """

    CONVERGED = "CONVERGED"
    COMPLETED_MAX_ITER = "COMPLETED_MAX_ITER"
    FAILED_EXECUTION = "FAILED_EXECUTION"
    FAILED_SCRIPT = "FAILED_SCRIPT"
    FAILED_INCOMPLETE_OUTPUT = "FAILED_INCOMPLETE_OUTPUT"
    FAILED_DIVERGED = "FAILED_DIVERGED"


class BrokenCommandRecord(TypedDict, total=False):
    """One serialized :class:`~pyflightstream.script.BrokenCommandUse`.

    The JSON shape of a ``broken_commands`` entry of the manifest,
    declared here rather than imported so the workspace layer keeps its
    manifest schema and the script layer keeps the model. The model is
    the single home of what each field MEANS: read
    :class:`~pyflightstream.script.BrokenCommandUse` for that, including
    why two of these are versions and are not interchangeable.

    Every key is optional (``total=False``) and no member type is
    narrower than the model's, which is the compatibility half: a
    manifest row written before a key existed still reads back, exactly
    as :attr:`RunRecord.manifest_schema` may be None. Unknown keys are
    KEPT rather than dropped, so reading a manifest a later version
    wrote never quietly edits the evidence.
    """

    command: str
    version: str
    source_version: str | None
    report: str
    note: str | None
    reason: str
    first_line: str


# Set after the class body because mypy refuses any statement inside a
# TypedDict definition that is not a field declaration.
BrokenCommandRecord.__pydantic_config__ = ConfigDict(extra="allow")  # type: ignore[attr-defined]


class RunRecord(BaseModel):
    """One manifest record: a single executed campaign point.

    The record plus the staged inputs reproduce the run (NFR-07).

    Attributes
    ----------
    run_id : str
        Unique identity of the executed point, for example
        ``"campaign/sim_9001/a+02.0_b+00.0"``; the manifest rejects
        duplicates.
    sim_id : str
        Simulation identity; ties the record to ``sims/sim_<sim_id>``.
    point : dict of str to float
        Sweep point coordinates, for example alpha and beta in deg.
    fs_version_requested : str
        Canonical FlightStream version the script was built for.
    fs_version_reported : str, optional
        Version printed in the solver outputs; filled by the parsers
        and cross-checked against the requested one (FR-18).
    fs_build : str, optional
        Build string reported by the solver, when available.
    fs_version_source : str or None
        Where the build this point ran on came from: ``"row"`` when the
        case named its own :attr:`~pyflightstream.cases.SimCase.fs_build`
        and ``"campaign_default"`` when it inherited the campaign's
        (PFS-2009.08.02). ``fs_exe`` and ``fs_version_requested`` say
        WHICH build; this says WHICH OF THE TWO SOURCES chose it, which
        the record could not state at all while a campaign declared one
        installation and a case could name another.

        None means the row PREDATES the field and is not a claim that the
        build was inherited, exactly as ``manifest_schema`` may be None.
        Adding it did NOT move :data:`MANIFEST_SCHEMA`: that constant's
        own rule bumps for a removal or a change of meaning, never for an
        addition.
    velocity_requested_m_s : float or None
        Free-stream velocity in m/s the case ASKED for, as
        :attr:`~pyflightstream.cases.SimCase.velocity` declared it
        (OPS-2009.01.13). Recorded because two places compare requested
        conditions against the conditions a solver export prints back,
        and only one of them could see this axis, so the two could reach
        opposite verdicts about one run.

        None means the run did not request a velocity, which includes
        every row written before the field existed, and is NOT zero: a
        binding treats an unrequested axis as unasked rather than as
        agreed, and zero would be a request the export could contradict.
    package_version : str
        pyflightstream version that produced the run. Read from the
        installed distribution's metadata, which is a static string, so
        every commit between two tags reports the tag: use
        ``package_commit`` to tell them apart.
    package_commit : str, optional
        Git commit the package's code came from, when it came from a
        tracked work tree; None for a wheel install, where there is no
        repository to ask (PYFS-017).
    package_dirty : bool, optional
        Whether that work tree had uncommitted changes. None travels
        with a None ``package_commit`` and means "not knowable here",
        never "clean".
    script_sha256 : str
        Hash of the executed script text.
    inputs_sha256 : dict of str to str
        Hash per staged input file name, recorded at staging time.
    raw_flag : bool
        True when the script used the ``raw()`` escape hatch and its
        content bypassed database validation (FR-07).
    manifest_schema : str or None
        Identifier of the record layout this row was written under.
        A reader that does not know the value should refuse rather than
        guess which fields exist (PYFS-015).

        None means the row PREDATES the field and is not a claim that
        it was written under the current schema. It defaulted to
        :data:`MANIFEST_SCHEMA` until 2026-08-03, so reading a
        historical manifest stamped every row in it with a positive
        assertion about a layout that never described it, and appending
        a new run wrote that assertion back to disk (REV010-014). "The
        field is absent because the row is old" and "the row asserts
        the current schema" are different facts about the evidence.
    conditions : list of dict, optional
        The operating-point binding recorded by the assessor, one
        entry per requested axis the export printed back: ``axis``,
        ``requested``, ``reported``, ``deviation``, ``tolerance``,
        ``unit`` and ``within`` (REV010-001). None means the run was
        recorded by an assessor that did not perform the comparison,
        which includes every row written before this field existed;
        an empty list means the comparison ran and had nothing to
        compare. The two are deliberately distinguishable.
    fs_exe : str, optional
        Solver executable the run invoked, as resolved.
    fs_exe_sha256 : str, optional
        Hash of that executable, so a later reader can tell whether the
        same binary is still installed. None when it could not be read.
    argv : list of str
        The exact command line, argument by argument. Reproducing a run
        from the record needs the flags, not a guess at how the
        executor builds them.
    cwd : str, optional
        Working directory the solver process ran in.
    timeout_s : float, optional
        Wall-clock limit actually applied to the process.
    recipe : str, optional
        Recipe identifier as the case declared it.
    recipe_sha256 : str, optional
        Hash of the recipe function's source at run time. A recipe is
        user code that can be edited between runs, so the name alone
        does not identify what built the script; None when the source
        is not introspectable.
    script_path : str, optional
        Generated script, relative to the simulation folder.
    outputs_sha256 : dict of str to str
        Hash per collected output, keyed by the same relative name that
        appears in ``outputs``. Empty for a point that collected
        nothing and for manifests written before v0.4.0. Inputs have
        carried a hash since the first manifest and outputs did not, so
        a record could name evidence that had since been edited,
        truncated or replaced with nothing to compare against
        (PYFS-006).
    broken_commands : list of BrokenCommandRecord
        Serialized
        :class:`~pyflightstream.script.BrokenCommandUse` entries, one
        per command the script emitted under an ``allow_broken`` waiver
        (FR-48). That class is the single home of the field list and
        their meanings; note only that TWO of them are versions and they
        are not interchangeable, ``version`` being the build the script
        targeted and ``source_version`` the build whose record is broken,
        which is the build the cited report was run on.
        Empty for the ordinary run, which is the
        point: a run that leaned on a command known not to work is
        distinguishable from one that did not, forever, without
        re-reading the script.

        ``source_version`` is REQUIRED since ``pyfs-manifest/2``
        (PFS-2012.03). :meth:`read_manifest` refuses an entry that lacks
        it, naming this manifest and the stamp the row carries, rather
        than reading the field as empty.
    solver_setup : dict, optional
        Serialized solver-setup snapshot
        (:class:`pyflightstream.script.solver_setup.SolverSetup`) of
        the built script: every solver flag with its effective value
        and provenance (explicit, default with citation, or unknown).
        None for scripts built without the curated ``solver_settings``
        helper and for manifests written before v0.3.0.
    status : RunStatus
        Terminal status of the point.
    iterations : int, optional
        Solver iterations reached, when parsed.
    residual : float, optional
        Final residual, when parsed.
    wall_time_s : float, optional
        Wall-clock duration of the solver process in seconds.
    outputs : list of str
        Collected output files, relative to the simulation folder
        (for example ``"raw/loads.txt"``).
    error : str, optional
        Error text for failed points.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str
    sim_id: str
    point: dict[str, float] = Field(default_factory=dict)
    fs_version_requested: str
    fs_version_reported: str | None = None
    fs_build: str | None = None
    fs_version_source: str | None = None
    velocity_requested_m_s: float | None = None
    package_version: str
    package_commit: str | None = None
    package_dirty: bool | None = None
    manifest_schema: str | None = None
    fs_exe: str | None = None
    fs_exe_sha256: str | None = None
    argv: list[str] = Field(default_factory=list)
    cwd: str | None = None
    timeout_s: float | None = None
    recipe: str | None = None
    recipe_sha256: str | None = None
    script_path: str | None = None
    script_sha256: str
    inputs_sha256: dict[str, str] = Field(default_factory=dict)
    raw_flag: bool
    outputs_sha256: dict[str, str] = Field(default_factory=dict)
    broken_commands: list[BrokenCommandRecord] = Field(default_factory=list)
    conditions: list[dict] | None = None
    solver_setup: dict | None = None
    status: RunStatus
    iterations: int | None = None
    residual: float | None = None
    wall_time_s: float | None = None
    outputs: list[str] = Field(default_factory=list)
    error: str | None = None


def _sha256(path: Path) -> str:
    """Return the sha256 of a file, through the package's one owner.

    Kept as a name because this module's own call sites read better
    with it, and it is now three characters of delegation rather than
    a second implementation. The definition moved to
    :mod:`pyflightstream._digest` on 2026-08-19: NFR-07 claims two runs
    with the same inputs are recognisably the same run, and that claim
    rested on a digest written in three places, one of which the run
    layer reached across a layer boundary to borrow.
    """
    return file_sha256(path)


#: The library kinds whose id is a file-name STEM with any extension,
#: which is what makes an ambiguity possible: two files sharing a stem
#: are two files answering to one id.
#:
#: It is these two and not the five of ``INPUT_KINDS`` because the other
#: three build their path directly as ``<id>.toml``
#: (:func:`~pyflightstream.workspace.inputs.resolve_reference` and its
#: two siblings), so their per-kind uniqueness is enforced by the file
#: system and cannot be broken. ``references/003.yaml`` beside
#: ``references/003.toml`` is not a competing id; it is a file the
#: library provably never opens, and refusing it would be code refusing
#: something no requirement promised (FR-33a, OPS-2005.08.05).
STEM_REGISTERED_KINDS = ("geometries", "profiles")

#: Optional workspace-level declaration of the named reference points,
#: ``inputs/reference_points.toml``. A top-level registry beside
#: ``executables.toml`` rather than a kind of its own: the points are
#: properties of the campaign's geometry, written once, not one artifact
#: per id.
REFERENCE_POINTS_FILE = "reference_points.toml"

#: ``ERP`` alone, or ``ERP`` with a propulsor number.
_ERP_PATTERN = re.compile(r"^ERP([0-9]*)$")

#: The airframe reference point. Singular by construction.
_AIRFRAME_POINT = "ARP"


def check_unique_stems(inputs_dir: str | Path) -> None:
    """Refuse a library in which two files answer to one id.

    Geometries and profiles register by file-name stem with any
    extension (:data:`STEM_REGISTERED_KINDS`), so ``wing_v2.fsm`` beside
    ``wing_v2.stl`` leaves the id ``wing_v2`` ambiguous. Until this
    check existed the ambiguity was found lazily, by the resolver, for
    the one id a caller happened to ask for, and only once a campaign
    was already being built.

    The check is per directory: ids are namespaced per kind, so the same
    stem under ``references/`` and ``setups/`` is two different ids and
    both are legal. That idiom is used by real run matrices.

    Parameters
    ----------
    inputs_dir : str or Path
        The workspace ``inputs/`` directory. A directory that does not
        exist holds no ambiguity and is not an error here.

    Raises
    ------
    InputArtifactError
        If any stem is carried by more than one file, naming the stem
        and the full path of every file carrying it.

    Examples
    --------
    >>> from pyflightstream.workspace import check_unique_stems
    >>> check_unique_stems("campaign/inputs")     # doctest: +SKIP
    """
    root = Path(inputs_dir)
    offenders: list[str] = []
    first_kind: str | None = None
    first_stem: str | None = None
    for kind in STEM_REGISTERED_KINDS:
        directory = root / kind
        if not directory.is_dir():
            continue
        carriers: dict[str, list[Path]] = {}
        for path in sorted(directory.iterdir()):
            if path.is_file():
                carriers.setdefault(path.stem, []).append(path)
        for stem, paths in carriers.items():
            if len(paths) < 2:
                continue
            if first_stem is None:
                first_kind, first_stem = kind, stem
            listing = ", ".join(str(path) for path in paths)
            offenders.append(f"{kind}/{stem} is carried by {len(paths)} files ({listing})")
    if not offenders:
        return
    raise InputArtifactError(
        f"the input library {root} holds an ambiguous artifact id: {'; '.join(offenders)}. "
        "The id is the file name stem and must be unique within the library, so rename "
        "or remove the extras. A geometry or profile id selects a file by its stem, so "
        "two files carrying one stem let a campaign be built on the geometry nobody "
        "meant to use.",
        kind=first_kind,
        artifact_id=first_stem,
    )


def expand_group(artifact: GroupsArtifact, name: str, artifact_id: str) -> dict[str, int]:
    """Expand one named boundary group into its per-member names.

    ``Blade`` with three members becomes ``Blade1``, ``Blade2`` and
    ``Blade3``, numbered 1-based in the members' declared order and
    mapped to the boundary index each member names. The workspace
    descriptor is the AUTHORITY for that expansion: it is read from the
    inputs a study ships with, so re-resolving it later gives the same
    names in the same order rather than whatever an inspection of the
    mesh concluded that day (PFS-2025.03).

    Parameters
    ----------
    artifact : GroupsArtifact
        The loaded groups descriptor.
    name : str
        Group to expand, which is also the stem of the generated names.
    artifact_id : str
        Id the descriptor was loaded under. It is a parameter because
        :class:`~pyflightstream.workspace.inputs.GroupsArtifact` carries
        no id of its own, and a refusal that cannot name the file the
        user must edit is not didactic.

    Returns
    -------
    dict of str to int
        ``{name}1`` to ``{name}N`` mapped to the members' boundary
        indices, in declared order.

    Raises
    ------
    InputArtifactError
        If the descriptor declares no group of that name (the message
        lists the ones it does declare), or if a member is a boundary
        LABEL rather than an index. A label carries no index, so it
        cannot number a per-member entity; resolve labels to indices in
        the descriptor, or expand a group whose members are indices.

    Examples
    --------
    >>> from pyflightstream.workspace import GroupsArtifact, expand_group
    >>> artifact = GroupsArtifact(groups={"Blade": [3, 5, 7]})
    >>> expand_group(artifact, "Blade", "prop")
    {'Blade1': 3, 'Blade2': 5, 'Blade3': 7}
    """
    members = artifact.groups.get(name)
    if members is None:
        declared = ", ".join(sorted(artifact.groups)) or "none"
        raise InputArtifactError(
            f"the group artifact {artifact_id!r} declares no group named {name!r}; it "
            f"declares: {declared}. The workspace descriptor is the authority for what "
            f"{name} expands to, so add the group there rather than letting the "
            "expansion be inferred from the mesh.",
            kind="group",
            artifact_id=artifact_id,
            available=tuple(sorted(artifact.groups)),
        )
    expanded: dict[str, int] = {}
    for position, member in enumerate(members, start=1):
        if not isinstance(member, int) or isinstance(member, bool):
            raise InputArtifactError(
                f"group {name!r} of the group artifact {artifact_id!r} cannot be "
                f"expanded per member: member {position} is {member!r}, a boundary "
                "label rather than a 1-based boundary index. Numbering a per-member "
                "entity needs the index, so declare the group with indices, or expand "
                "a group that already carries them.",
                kind="group",
                artifact_id=artifact_id,
            )
        expanded[f"{name}{position}"] = member
    return expanded


class ReferencePoints(BaseModel):
    """The named reference points one campaign declares.

    Loaded from ``inputs/reference_points.toml``, one TOML table per
    point name, each holding the coordinates of a
    :class:`~pyflightstream.workspace.inputs.PointXyz` in the simulation
    geometry reference frame (m).

    The names are a convention, not free text: ``ARP`` is the airframe
    reference point, and the engine reference point is ``ERP`` with one
    propulsor or ``ERP1`` through ``ERPn`` with more.
    :func:`check_reference_point_names` is what enforces that.

    Attributes
    ----------
    points : dict of str to PointXyz
        Declared points, keyed by name, in declaration order.
    """

    model_config = ConfigDict(extra="forbid")

    points: dict[str, PointXyz]


def check_reference_point_names(names: Sequence[str]) -> None:
    """Refuse a set of point names that is not the standard convention.

    The convention carries information a free-text name would not: how
    many propulsors the campaign describes. ``ERP`` alone says one;
    ``ERP1`` through ``ERPn`` say n, which is why a gap is refused
    rather than tolerated.

    Parameters
    ----------
    names : sequence of str
        The declared point names, in declaration order.

    Raises
    ------
    InputArtifactError
        If a name is outside the convention, if the singular and the
        numbered engine names both appear, or if the numbered ones do
        not run from 1 without a gap. Each refusal names the offending
        name and the remedy.
    """
    numbered: list[int] = []
    singular = False
    for name in names:
        if name == _AIRFRAME_POINT:
            continue
        match = _ERP_PATTERN.match(name)
        if match is None:
            raise InputArtifactError(
                f"reference point {name!r} is not one of the standard names; declare "
                f"{_AIRFRAME_POINT} for the airframe reference point and ERP for the "
                "engine one, or ERP1 through ERPn with more than one propulsor. The "
                "names are the convention that says how many propulsors the campaign "
                "describes, so a free name would leave that unreadable."
            )
        if match.group(1) == "":
            singular = True
        else:
            numbered.append(int(match.group(1)))
    if singular and numbered:
        listing = ", ".join(f"ERP{index}" for index in sorted(numbered))
        raise InputArtifactError(
            f"reference points declare both the singular ERP and the numbered "
            f"{listing}; the singular name means the campaign has exactly one "
            "propulsor, so the two together leave the propulsor count unreadable. "
            "Number every engine point, or declare only ERP."
        )
    if not numbered:
        return
    if 0 in numbered:
        raise InputArtifactError(
            "reference point 'ERP0' numbers a propulsor from zero; engine points are "
            "numbered from 1, as ERP1 through ERPn, because n is the propulsor count."
        )
    expected = set(range(1, max(numbered) + 1))
    missing = sorted(expected - set(numbered))
    if missing:
        listing = ", ".join(f"ERP{index}" for index in missing)
        raise InputArtifactError(
            f"reference points ERP1 through ERP{max(numbered)} are declared with a gap: "
            f"{listing} is missing. The numbered engine points run from 1 without a gap, "
            "because n is the propulsor count; declare the missing point or renumber."
        )


class CampaignWorkspace:
    """The managed folder layout of one campaign root.

    Parameters
    ----------
    root : str or Path
        User-chosen campaign root; everything below it is managed by
        this class and never hand-built.
    naming : NamingTemplate, optional
        Output-only naming template for generated scripts, rendered
        export names, and archive names; the default reproduces the
        historical names (``{point}`` stems, ``sim_<sim_id>`` zips).
        Identity always stays in the manifest, never in a name.

    Attributes
    ----------
    root : Path
        The campaign root.
    naming : NamingTemplate
        The active naming template.
    """

    def __init__(self, root: str | Path, naming: NamingTemplate | None = None):
        self.root = Path(root)
        self.naming = naming if naming is not None else NamingTemplate()

    @classmethod
    def init(cls, root: str | Path, naming: NamingTemplate | None = None) -> CampaignWorkspace:
        """Create the full campaign tree under ``root``, idempotently.

        Creates the input-artifact library skeleton
        (``inputs/geometries``, ``inputs/references``,
        ``inputs/setups``, ``inputs/groups``, ``inputs/profiles``),
        ``sims/``, ``post/``, and ``archive/``; existing folders and
        files are kept untouched, so re-running init on a live
        campaign root is safe. When no build registry exists yet, a
        comment-only ``inputs/executables.toml`` template is written
        showing the entry shape.

        Parameters
        ----------
        root : str or Path
            Campaign root to create or complete.
        naming : NamingTemplate, optional
            Naming template of the returned workspace.

        Returns
        -------
        CampaignWorkspace
            The workspace over the created tree.

        Raises
        ------
        InputArtifactError
            If the library already holds two files answering to one
            geometry or profile id. The creation contract is untouched:
            every folder and the registry template are written first, and
            only the RETURN becomes a refusal, so re-running init on a
            campaign that has grown an ambiguity still completes the tree
            and then says what is wrong with it
            (:func:`check_unique_stems`).
        """
        workspace = cls(root, naming=naming)
        for kind in INPUT_KINDS:
            (workspace.inputs_dir / kind).mkdir(parents=True, exist_ok=True)
        for name in ("sims", "post", "archive"):
            (workspace.root / name).mkdir(parents=True, exist_ok=True)
        registry = workspace.inputs_dir / EXECUTABLES_FILE
        if not registry.exists():
            registry.write_text(_EXECUTABLES_TEMPLATE, encoding="utf-8")
        check_unique_stems(workspace.inputs_dir)
        return workspace

    @classmethod
    def open(cls, root: str | Path, naming: NamingTemplate | None = None) -> CampaignWorkspace:
        """Open an existing campaign root, checking what it already holds.

        The validating constructor. ``CampaignWorkspace(root)`` stays
        free of I/O so a campaign can be described cheaply and away from
        the files; this one asks the questions that are worth asking once,
        when the library opens, rather than when a single id happens to
        resolve.

        Parameters
        ----------
        root : str or Path
            Existing campaign root.
        naming : NamingTemplate, optional
            Naming template of the returned workspace.

        Returns
        -------
        CampaignWorkspace
            The workspace over that root.

        Raises
        ------
        InputArtifactError
            If two files under ``inputs/geometries/`` or
            ``inputs/profiles/`` answer to one id
            (:func:`check_unique_stems`).

        Examples
        --------
        >>> from pyflightstream.workspace import CampaignWorkspace
        >>> workspace = CampaignWorkspace.open("campaign")   # doctest: +SKIP
        """
        workspace = cls(root, naming=naming)
        check_unique_stems(workspace.inputs_dir)
        return workspace

    @property
    def manifest_path(self) -> Path:
        """Location of the authoritative manifest, ``runs.json``."""
        return self.root / "runs.json"

    @property
    def inputs_dir(self) -> Path:
        """Root of the input-artifact library, ``inputs/``."""
        return self.root / "inputs"

    def resolve_reference(self, artifact_id: str) -> ReferenceArtifact:
        """Load the reference-data artifact one id names.

        See :func:`pyflightstream.workspace.inputs.resolve_reference`;
        the id is the file name stem under ``inputs/references/``, and
        a miss lists the available ids.
        """
        return resolve_reference(self.inputs_dir, artifact_id)

    def resolve_setup(self, artifact_id: str) -> SetupArtifact:
        """Load the solver-setup preset one id names.

        See :func:`pyflightstream.workspace.inputs.resolve_setup`; the
        raw settings table is kept verbatim for the future formal
        solver-setup model.
        """
        return resolve_setup(self.inputs_dir, artifact_id)

    def resolve_group(self, artifact_id: str) -> GroupsArtifact:
        """Load the named boundary groups one id names.

        See :func:`pyflightstream.workspace.inputs.resolve_group`;
        members are boundary labels or indices, stored verbatim.
        """
        return resolve_group(self.inputs_dir, artifact_id)

    def expand_group(self, artifact_id: str, name: str) -> dict[str, int]:
        """Expand one named boundary group into its per-member names.

        The group ``Blade`` of the descriptor becomes ``Blade1`` through
        ``BladeN`` over the members' 1-based positions. See
        :func:`expand_group`, which this loads the artifact for.

        Parameters
        ----------
        artifact_id : str
            File name stem under ``inputs/groups/``.
        name : str
            Group to expand, and the stem of the generated names.

        Returns
        -------
        dict of str to int
            ``{name}1`` to ``{name}N`` mapped to boundary indices.

        Raises
        ------
        InputArtifactError
            Unknown artifact id, unknown group name, or a group whose
            members are boundary labels rather than indices.
        """
        return expand_group(self.resolve_group(artifact_id), name, artifact_id)

    def reference_points(self) -> dict[str, PointXyz]:
        """Read the named reference points this campaign declares.

        The points live in ``inputs/reference_points.toml``, one TOML
        table per name, and the user writes them once: ``ARP`` for the
        airframe reference point, ``ERP`` for the engine one with a
        single propulsor, ``ERP1`` through ``ERPn`` with more. Nothing
        emitted to the solver takes a pivot, so a named point becomes a
        local coordinate system at those coordinates, which is why the
        declaration is the authority and not a downstream guess
        (PFS-2025.15).

        Returns
        -------
        dict of str to PointXyz
            Declared points keyed by name, in declaration order. Empty
            when the campaign declares no points, which is the ordinary
            case for a study that needs none.

        Raises
        ------
        InputArtifactError
            If the file is not valid TOML, does not validate as
            coordinates, or declares names outside the convention
            (:func:`check_reference_point_names`).

        Examples
        --------
        >>> from pyflightstream.workspace import CampaignWorkspace
        >>> workspace = CampaignWorkspace("campaign")
        >>> workspace.reference_points()                     # doctest: +SKIP
        {'ARP': PointXyz(x_m=1.5, y_m=0.0, z_m=0.25)}
        """
        path = self.inputs_dir / REFERENCE_POINTS_FILE
        if not path.is_file():
            return {}
        try:
            # `path.open` rather than the builtin, which the classmethod
            # `open` above does not shadow but does make ambiguous to read.
            with path.open("rb") as handle:
                table = tomllib.load(handle)
        except tomllib.TOMLDecodeError as error:
            raise InputArtifactError(
                f"the reference points file {path} is not valid TOML: {error}. It "
                "declares one table per named point, each holding the coordinates of "
                "that point in the simulation geometry frame (m)."
            ) from error
        try:
            declared = ReferencePoints.model_validate({"points": table})
        except ValidationError as error:
            raise InputArtifactError(
                f"the reference points file {path} does not validate: {error}. Each "
                "table holds x_m, y_m and z_m, the coordinates of that point in the "
                "simulation geometry frame."
            ) from error
        check_reference_point_names(list(declared.points))
        return declared.points

    def reference_point(self, name: str) -> PointXyz:
        """Resolve one named reference point by name.

        Parameters
        ----------
        name : str
            Point name, for example ``"ARP"`` or ``"ERP2"``.

        Returns
        -------
        PointXyz
            Its coordinates in the simulation geometry frame, m.

        Raises
        ------
        InputArtifactError
            If the campaign declares no reference points at all, or
            declares none by that name; the message lists the ones it
            does declare, because a point the workspace never defined
            cannot be turned into a coordinate system.
        """
        points = self.reference_points()
        if not points:
            raise InputArtifactError(
                f"this campaign declares no reference points, so {name!r} cannot be "
                f"resolved; declare it in {self.inputs_dir / REFERENCE_POINTS_FILE} as a "
                "table holding x_m, y_m and z_m. The workspace declaration is the "
                "authority for where a named point is.",
                artifact_id=name,
            )
        if name not in points:
            listing = ", ".join(points)
            raise InputArtifactError(
                f"this campaign declares no reference point named {name!r}; it declares: "
                f"{listing}. Add it to "
                f"{self.inputs_dir / REFERENCE_POINTS_FILE}, or cite one of the declared "
                "names.",
                artifact_id=name,
                available=tuple(points),
            )
        return points[name]

    def resolve_geometry(self, artifact_id: str) -> Path:
        """Resolve the staged geometry file one id (file stem) names.

        See :func:`pyflightstream.workspace.inputs.resolve_geometry`.
        """
        return resolve_geometry(self.inputs_dir, artifact_id)

    def resolve_profile(self, artifact_id: str) -> Path:
        """Resolve the input profile file one id (file stem) names.

        See :func:`pyflightstream.workspace.inputs.resolve_profile`.
        """
        return resolve_profile(self.inputs_dir, artifact_id)

    def resolve_executable(self, build_id: str, override: str | Path | None = None) -> Path:
        """Resolve the FlightStream executable of one build id.

        Registry mode reads ``inputs/executables.toml``; an explicit
        ``override`` path bypasses the registry and is the only way to
        run an unregistered build. See
        :func:`pyflightstream.workspace.inputs.resolve_executable`.

        Returns the PATH alone, which is what it has always returned and
        what most callers want. Use :meth:`resolve_build` where the
        version the registry declares for the build matters too.
        """
        return resolve_executable(self.inputs_dir, build_id, override=override)

    def resolve_build(self, build_id: str, override: str | Path | None = None) -> RegisteredBuild:
        """Resolve the executable AND the declared version of one build id.

        The sibling of :meth:`resolve_executable`, and the one a caller
        wants when a run matrix sends different rows to different builds:
        a registry entry written as a table declares the version that
        build's scripts are emitted under, and a bare path entry declares
        none.

        Parameters
        ----------
        build_id : str
            Build identifier key of the registry.
        override : str or Path, optional
            Explicit executable path bypassing the registry. It declares
            no version, exactly as it declares no registry entry.

        Returns
        -------
        pyflightstream.workspace.inputs.RegisteredBuild
            The path, and the declared version or None.

        See Also
        --------
        pyflightstream.workspace.inputs.resolve_build : the free function
            this delegates to, which carries the full refusal rules.
        """
        return resolve_build(self.inputs_dir, build_id, override=override)

    def sim_dir(self, sim_id: str) -> Path:
        """Return the managed folder of one simulation.

        Parameters
        ----------
        sim_id : str
            Simulation identity; letters, digits, underscore, and
            hyphen only, so the derived folder name is stable and
            portable (NFR-10).
        """
        if not _SIM_ID_PATTERN.match(sim_id):
            raise WorkspaceError(
                f"sim_id {sim_id!r} cannot name a managed folder: use letters, digits, "
                "underscore, or hyphen. Folder names derive from sim_id and must stay "
                "stable and portable; identity lives in the manifest, not in names."
            )
        return self.root / "sims" / f"sim_{sim_id}"

    def create_sim(self, sim_id: str) -> Path:
        """Create the managed subfolders of one simulation and return its path.

        Creates ``inputs/``, ``scripts/``, ``raw/``, and ``parsed/``;
        existing folders are kept, so the call is idempotent.
        """
        sim = self.sim_dir(sim_id)
        for name in _SIM_SUBDIRS:
            (sim / name).mkdir(parents=True, exist_ok=True)
        return sim

    def stage_inputs(self, sim_id: str, sources: Sequence[str | Path]) -> dict[str, str]:
        """Copy input files into ``inputs/`` and record their hashes.

        Staging happens before execution so the manifest can tie the
        run to the exact input content (NFR-07).

        Parameters
        ----------
        sim_id : str
            Target simulation.
        sources : sequence of str or Path
            Files to copy; each must exist.

        Returns
        -------
        dict of str to str
            sha256 per staged file name, ready for
            :attr:`RunRecord.inputs_sha256`.
        """
        sim = self.create_sim(sim_id)
        # FR-33f, and PYFS-005 is the incident behind it: the staging half of
        # the same collision class. Two sources with the same base name staged
        # onto one file: the second copy won, and the returned dict carried ONE
        # entry, so the manifest recorded a single hash for what the case
        # declared as two inputs. The run then claimed to be reproducible from
        # inputs one of which was never staged at all.
        seen: dict[str, str] = {}
        for source in sources:
            name = Path(source).name
            if name in seen and str(source) != seen[name]:
                raise WorkspaceError(
                    f"two declared inputs share the base name {name!r} "
                    f"({seen[name]} and {source}). Staging copies each into "
                    "inputs/ under its base name, so the second would overwrite "
                    "the first and the manifest would record one hash for two "
                    "inputs. Rename one, or stage them from directories the "
                    "recipe references separately."
                )
            seen[name] = str(source)
        hashes: dict[str, str] = {}
        for source in sources:
            origin = Path(source)
            if not origin.is_file():
                raise WorkspaceError(
                    f"cannot stage {origin}: the file does not exist. Staging copies "
                    "inputs before execution so the manifest records what actually ran."
                )
            target = sim / "inputs" / origin.name
            shutil.copy2(origin, target)
            hashes[origin.name] = _sha256(target)
        return hashes

    def write_script(self, sim_id: str, name: str, text: str) -> tuple[Path, str]:
        """Write one generated script into ``scripts/`` and hash it.

        Parameters
        ----------
        sim_id : str
            Target simulation.
        name : str
            Script file name, for example ``"a+02.0_b+00.0.txt"``.
        text : str
            Rendered script text from the builder.

        Returns
        -------
        Path
            Location of the written script.
        str
            sha256 of the written text, for
            :attr:`RunRecord.script_sha256`.
        """
        sim = self.create_sim(sim_id)
        target = sim / "scripts" / name
        target.write_text(text, encoding="utf-8")
        return target, _sha256(target)

    #: What each managed subdirectory of a simulation folder IS, so a
    #: refusal can name the role rather than only the folder. A reader
    #: who is told "raw/" has to know what raw/ holds; a reader who is
    #: told "this simulation's own collected outputs" does not.
    _SUBDIR_ROLES = {
        "inputs": "this simulation's staged input artifacts",
        "scripts": "this simulation's generated solver scripts",
        "raw": "this simulation's own collected outputs",
        "parsed": "this simulation's parsed results",
    }

    def _output_trespass(self, sim: Path, origin: Path) -> str | None:
        """Say why one declared output may not be collected, or None.

        The question is asked of the RESOLVED path, because the harm is
        about where a file physically is and not about how it was
        spelled. ``sims/sim_A/../sim_B/raw/loads.txt`` is another run's
        evidence however it is written.

        Three answers, in the order a reader meets them:

        * OUTSIDE this campaign root: collect it. That is the ordinary
          case and the one every current caller uses, since the solver's
          working directory is not managed here.
        * inside the root but outside this simulation's folder: refuse,
          naming the simulation it actually belongs to when it is one.
        * inside this simulation's folder but under one of the four
          managed subdirectories: refuse, naming the role of that
          subdirectory.

        An unmanaged subfolder of the simulation, ``sim/out/x.txt``, is
        accepted: nothing in this class owns it, so moving a file out of
        it destroys no record.
        """
        try:
            resolved = origin.resolve()
            root = self.root.resolve()
            simulation = sim.resolve()
        except OSError:
            # A path this process cannot resolve is a problem for the
            # move to report with its own diagnosis, not for a
            # containment check to guess at.
            return None

        if not resolved.is_relative_to(root):
            return None

        if not resolved.is_relative_to(simulation):
            owner = ""
            sims = root / "sims"
            if resolved.is_relative_to(sims):
                other = resolved.relative_to(sims).parts[0]
                owner = f", which belongs to {other}"
            return (
                f"cannot collect {origin}: it resolves inside this campaign root but "
                f"outside {sim.name}{owner}. Collection MOVES the file, so this would "
                "take evidence that another part of the campaign records as its own, "
                "and two manifests would then name a file only one of them has. "
                "Declare outputs the solver wrote in its own working directory."
            )

        relative = resolved.relative_to(simulation)
        first = relative.parts[0] if relative.parts else ""
        role = self._SUBDIR_ROLES.get(first)
        if role is not None:
            return (
                f"cannot collect {origin}: it resolves inside {sim.name}/{first}, which "
                f"holds {role} and is managed by this class. Collection MOVES the file, "
                "so this would take a record out of the layout that owns it. Declare "
                "outputs the solver wrote in its own working directory, or in an "
                "unmanaged subfolder of the simulation."
            )
        return None

    def collect_outputs(self, sim_id: str, produced: Sequence[str | Path]) -> list[str]:
        """Move declared solver outputs into ``raw/``.

        Parameters
        ----------
        sim_id : str
            Target simulation.
        produced : sequence of str or Path
            Output files the run declared it would produce. Anywhere
            OUTSIDE this campaign root, which is where a solver working
            directory normally sits; inside the root, only in this
            simulation's own folder and not in one of its four managed
            subdirectories. See Raises.

        Returns
        -------
        list of str
            Collected names relative to the simulation folder
            (``"raw/<name>"``), ready for :attr:`RunRecord.outputs`.

        Raises
        ------
        WorkspaceError
            If a declared output does not exist; the campaign loop
            turns this into FAILED_INCOMPLETE_OUTPUT, never into a
            silently shorter output set.

            If a declared output RESOLVES INSIDE this campaign root but
            outside this simulation's own folder, or inside one of that
            folder's four managed subdirectories. Collection MOVES, so
            without this a run could take another run's collected
            evidence: naming ``sims/sim_OTHER/raw/loads.txt`` as an
            output moved it into this simulation's ``raw/``, and both
            manifests then named a file only one of them had.

            A source resolving OUTSIDE the root is still accepted, and
            that is deliberate rather than an oversight: it is the
            ordinary case, since the solver's working directory is not
            managed by this class.

            If two declared outputs of one call would collect to the
            same name, or if a declared output's base name is already
            held in ``raw/`` from an earlier point or run. Both are
            FR-33e and neither takes an overwrite argument: the remedies
            are a per-point output name and an archived simulation. They
            differ in WHEN they are decided, which a caller can see: the
            first is a pre-scan over the whole call, so a refusal moves
            nothing at all, while the second is asked immediately before
            each move, so a call whose third output lands on a held name
            refuses with the first two already collected.

        Notes
        -----
        Collection MOVES rather than copies. Every refusal here exists
        because of that and a reader has had to infer it from the
        collision message until now.
        """
        sim = self.create_sim(sim_id)
        missing = [str(path) for path in produced if not Path(path).is_file()]
        if missing:
            raise WorkspaceError(
                f"declared outputs were not produced: {', '.join(missing)}. A missing "
                "declared output marks the point FAILED_INCOMPLETE_OUTPUT; outputs are "
                "never silently dropped."
            )
        # PFS-2011.01 and PFS-2011.03, which are one piece of work. The
        # rule is on RESOLVED paths and never on the declared string,
        # which is what separates it from `_check_output_containment` in
        # `naming.py`: that one refuses any ABSOLUTE path, and every
        # production caller here passes absolute paths, so reusing it
        # would refuse the normal case. What is uncovered is a DIRECT
        # caller of this method.
        #
        # Detected before the collision pre-scan and therefore before any
        # move, so a refusal leaves every source exactly where it was.
        for path in produced:
            trespass = self._output_trespass(sim, Path(path))
            if trespass is not None:
                raise WorkspaceError(trespass)
        # FR-33e, first shape, and PYFS-005 is the incident behind it.
        # Collection MOVES, so two declared outputs whose base names agree used
        # to land on one file in raw/: both moves ran, only the second content
        # survived, and the manifest recorded the same name twice as though two
        # artifacts existed. A campaign then carried a record naming evidence
        # that had been overwritten by other evidence, with nothing anywhere
        # saying so.
        #
        # Detected before any move rather than during, so a refusal leaves
        # every source where it was instead of half-collecting.
        destinations: dict[str, list[str]] = {}
        for path in produced:
            destinations.setdefault(collection_name(path), []).append(str(path))
        clashing = {name: sources for name, sources in destinations.items() if len(sources) > 1}
        if clashing:
            detail = "; ".join(
                f"raw/{name} from {' and '.join(sources)}" for name, sources in clashing.items()
            )
            raise WorkspaceError(
                f"two or more declared outputs collect to the same name: {detail}. "
                "Collection moves each output into raw/, so the later one would "
                "overwrite the earlier and the manifest would record one name "
                "twice while only the last content survived. Declare outputs whose "
                "base names differ, or use a per-point placeholder such as "
                "loads_{point}.txt so each point exports under its own name."
            )
        collected: list[str] = []
        for path in produced:
            origin = Path(path)
            destination = sim / "raw" / origin.name
            # FR-33e, second shape. Same rule as the pre-scan above and a
            # different remedy: the name is unique within THIS call, and what
            # is in the way is a record an earlier point or run collected.
            # Asked per destination rather than as a pre-scan, so a refusal
            # here leaves the outputs already handled in raw/. Nothing is
            # destroyed either way, which is the guarantee; making it a
            # pre-scan would change behaviour rather than tighten it.
            if destination.exists():
                raise WorkspaceError(
                    f"cannot collect {origin} into raw/{origin.name}: that name is "
                    "already in raw/ from an earlier point or run. Collection moves "
                    "the file, so continuing would destroy the collected evidence "
                    "and leave two manifest records pointing at one file. Use a "
                    "per-point output name, or archive the simulation before "
                    "re-running it."
                )
            shutil.move(str(origin), destination)
            collected.append(f"raw/{origin.name}")
        return collected

    def output_digests(self, sim_id: str, collected: Sequence[str]) -> dict[str, str]:
        """Return the sha256 of each collected output, keyed by its name.

        The manifest has recorded a hash per staged INPUT since the first
        version and none per collected output, so a record could name
        evidence that had been edited, truncated or replaced since the
        run and nothing compared (PYFS-006). This is what
        :attr:`RunRecord.outputs_sha256` carries.

        Parameters
        ----------
        sim_id : str
            Simulation the outputs were collected into.
        collected : sequence of str
            Names as :meth:`collect_outputs` returned them, relative to
            the simulation folder (``"raw/<name>"``).

        Returns
        -------
        dict of str to str
            Hex sha256 keyed by the same relative name.

        Raises
        ------
        WorkspaceError
            If a named output is not there to hash. Collection has just
            moved these files, so a miss here means something removed
            one in between, and hashing what remains would produce a
            record quieter than the truth.
        """
        sim = self.sim_dir(sim_id)
        digests: dict[str, str] = {}
        for name in collected:
            path = sim / name
            if not path.is_file():
                raise WorkspaceError(
                    f"collected output {name!r} of sim {sim_id!r} is not at {path}, so "
                    "it cannot be hashed for the manifest. Collection had just moved it "
                    "there, so something removed it in between; recording the rest "
                    "would leave a run whose evidence list is longer than its hashes."
                )
            digests[name] = _sha256(path)
        return digests

    def read_raw_manifest(self) -> list[dict]:
        """Read ``runs.json`` as written, without validating or defaulting.

        This is the manifest AS EVIDENCE: the fields each row actually
        carries, with nothing filled in. :meth:`read_manifest` is the
        typed view built from it, and :meth:`append_record` writes
        through this one so that reading a historical manifest cannot
        change it (REV010-014).

        Returns
        -------
        list of dict
            One dict per row, in file order; empty when the manifest
            does not exist yet.
        """
        if not self.manifest_path.is_file():
            return []
        entries = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        return list(entries)

    def read_manifest(self) -> list[RunRecord]:
        """Read and validate every record of ``runs.json``.

        Returns an empty list when the manifest does not exist yet.
        The typed view fills defaults for fields a row does not carry;
        use :meth:`read_raw_manifest` when the question is what the row
        actually asserts rather than how this version reads it.

        Raises
        ------
        WorkspaceError
            When a ``broken_commands`` entry carries no
            ``source_version``, naming the manifest and the stamp the
            row was written under (PFS-2012.03).
        """
        records = [RunRecord.model_validate(entry) for entry in self.read_raw_manifest()]
        for record in records:
            self._check_waivers_name_their_source(record)
        return records

    def _check_waivers_name_their_source(self, record: RunRecord) -> None:
        """Refuse a waiver row that does not say which build it rests on.

        ``BrokenCommandUse.source_version`` names the build whose record
        says the command is broken, which is the build the cited probe
        report was run on. It stopped being optional at
        :data:`MANIFEST_SCHEMA` ``pyfs-manifest/2`` (PFS-2012.03), so no
        row this version writes can lack it.

        The refusal is HERE rather than in the model because the entries
        are read back as :class:`BrokenCommandRecord`, a ``total=False``
        typed mapping, and its totality is the compatibility half that
        lets a row written before a key existed read back at all. Making
        the key required there would refuse the row with a schema error
        naming neither the file nor the stamp; the evidence a reader
        needs is which manifest, and under which layout, made the claim.

        Loading it with the field empty is the one outcome refused: a
        waiver that does not say which build's record it leaned on is a
        provenance row asserting nothing, and it would be indistinguishable
        from one whose source happened to equal the script's own version.
        """
        for entry in record.broken_commands:
            # Blank, not merely empty: " " is truthy and names no build,
            # so a row carrying it would pass a truthiness test while
            # asserting exactly what the missing key asserts. The value is
            # never stripped, only judged: a stored identifier is evidence
            # and this method does not edit evidence.
            if (entry.get("source_version") or "").strip():
                continue
            stamp = record.manifest_schema or "no stamp at all"
            # A row carrying requested_version is from the layout written
            # before 2026-08-04, the only one this package ever wrote
            # without source_version, and it is not the empty-handed case
            # the rest of this message assumes: the build is IN the row,
            # under a key that has since been renamed. Sending its owner
            # away to find what they already have is why this branch
            # exists rather than one message for every row.
            if "requested_version" in entry:
                relabel = (
                    " This row carries requested_version, which only the layout "
                    "written before 2026-08-04 had, so the build is already in it "
                    "and nothing has to be recovered: there, version held the "
                    "record's source build and requested_version held the build the "
                    "script targeted, which are this layout's source_version and "
                    "version in that order."
                )
            else:
                relabel = (
                    " Read the manifest with the pyflightstream version that wrote "
                    "it, or migrate the row deliberately by naming the build the "
                    "report was run on."
                )
            raise WorkspaceError(
                f"the manifest {self.manifest_path} records run {record.run_id!r} "
                f"waiving the broken command {entry.get('command', '<unnamed>')!r} "
                f"whose source_version is {entry.get('source_version')!r}, which names "
                "no build, so the row does not say which build's "
                "record says the command is broken, and the cited report cannot be "
                f"tied to a build. That row was written under {stamp}, and "
                f"source_version has been required since {MANIFEST_SCHEMA}."
                f"{relabel}"
            )

    def _refuse_a_waiver_this_version_may_not_write(self, record: RunRecord) -> None:
        """Refuse, before any write, a waiver row this version may not write.

        The read guard above is the LATE half and cannot be the only
        one. Measured on 2026-08-19, before this method existed:
        :meth:`append_record` accepted a record whose ``broken_commands``
        entry carried no ``source_version``, wrote it stamped
        ``pyfs-manifest/2``, and :meth:`read_manifest` then refused the
        file it had just written. Nothing in this package migrates a
        manifest, so that manifest had no route back, and the refusal
        text advised reading it "with the pyflightstream version that
        wrote it", which was this one. A writer that manufactures
        evidence its own reader rejects is the defect; refusing the
        record is the fix, and it costs a caller nothing, because the
        row was never readable.

        Two arms, both scoped to records that actually carry a waiver.

        The FIELD arm is the acceptance clause: every ``broken_commands``
        row written carries a ``source_version`` that names a build,
        which rules out the missing key, the empty string and the blank
        one alike. The test is the reader's, deliberately the same
        expression, because a writer that admitted a value the reader
        refuses would restore the hole one string at a time.

        The STAMP arm is the other half of the same clause. A waiver row
        is exactly the row whose meaning :data:`MANIFEST_SCHEMA` moved,
        so writing one under ``pyfs-manifest/1`` or under no stamp at all
        labels new-layout evidence with the layout in which the key was
        optional. That label is what a later reader consults to decide
        whether an absent key means "predates the field"; a row written
        today under the old stamp makes that inference wrong for the
        whole file.

        WHAT THIS DOES NOT GUARD, stated because the scope is narrower
        than the sentence "every manifest this release writes is
        stamped" would be: a record carrying NO waiver may still be
        appended unstamped, and several callers do exactly that.
        :attr:`RunRecord.manifest_schema` is optional so that a row which
        never carried it stays honest about that (REV010-014), and the
        run layer stamps every record it builds, which
        ``tests/test_run_campaign.py`` measures separately. Requiring a
        stamp on every append is a wider public break than this item
        carries evidence for.

        Parameters
        ----------
        record : RunRecord
            The record about to be appended. Not modified: a record this
            method would have to repair is one it refuses instead.
        """
        for entry in record.broken_commands:
            # The reader's expression, deliberately identical, including
            # the blank case: a writer that admitted a value its reader
            # refuses is the whole defect, and " " is that value.
            if not (entry.get("source_version") or "").strip():
                raise WorkspaceError(
                    f"refusing to write run {record.run_id!r} into the manifest "
                    f"{self.manifest_path}: it waives the broken command "
                    f"{entry.get('command', '<unnamed>')!r} whose source_version is "
                    f"{entry.get('source_version')!r}, which names no build, so "
                    "the row would not say which build's record says the command is "
                    "broken, and the cited report could not be tied to a build. "
                    f"source_version has been required since {MANIFEST_SCHEMA}, and "
                    "reading this manifest back would refuse the row this call is "
                    "about to add, with nothing in the package able to migrate it. "
                    "Nothing was written. Name the build the report was run on, which "
                    "is what Script.allow_broken records for you."
                )
            if record.manifest_schema != MANIFEST_SCHEMA:
                stamp = record.manifest_schema or "no stamp at all"
                raise WorkspaceError(
                    f"refusing to write run {record.run_id!r} into the manifest "
                    f"{self.manifest_path}: it waives the broken command "
                    f"{entry.get('command', '<unnamed>')!r} under {stamp}, and a waiver "
                    f"row is the row {MANIFEST_SCHEMA} exists for. Under the older "
                    "layout source_version was optional, so a row written today under "
                    "that stamp tells a later reader that an absent key means the "
                    "writer predated the field. Nothing was written. Stamp the record "
                    f"with the current schema ({MANIFEST_SCHEMA}), which is what the "
                    "run layer does for every record it builds."
                )

    def append_record(self, record: RunRecord) -> None:
        """Append one record to the manifest, atomically.

        The manifest is rewritten through a temporary file and an
        atomic replace, so a crash never leaves it half-written; a
        duplicate ``run_id`` is rejected because the manifest is the
        run identity (PP-6).

        Existing rows are carried across AS THEY WERE WRITTEN.
        REV010-014: this used to re-serialize the validated models, so
        appending one run rewrote every older row with more than twenty
        defaulted fields and a manifest_schema it had never carried.
        Historical evidence is not this method's to edit; migrating a
        manifest is a separate, deliberate, auditable act.

        Raises
        ------
        WorkspaceError
            If the ``run_id`` is already in the manifest, or if the
            record carries a waiver row that this version may not write:
            one whose ``source_version`` names no build, or one under any
            stamp but :data:`MANIFEST_SCHEMA`. Refused before anything is
            written, because the row would be one
            :meth:`read_manifest` refuses and nothing here migrates a
            manifest (PFS-2012.03).
        """
        self._refuse_a_waiver_this_version_may_not_write(record)
        raw = self.read_raw_manifest()
        if any(entry.get("run_id") == record.run_id for entry in raw):
            raise WorkspaceError(
                f"run_id {record.run_id!r} is already in the manifest; run identity "
                "must be unique. Use a new run_id or archive the campaign first."
            )
        raw.append(record.model_dump(mode="json"))
        self.root.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(raw, indent=2)
        temporary = self.manifest_path.with_suffix(".json.tmp")
        temporary.write_text(payload + "\n", encoding="utf-8")
        temporary.replace(self.manifest_path)

    def archive_sim(self, sim_id: str, campaign: str | None = None) -> Path:
        """Zip one recorded simulation into ``archive/`` and remove its folder.

        The zip name comes from the workspace naming template
        (default ``sim_<sim_id>.zip``); like every generated name it
        is output only and never parsed back.

        Parameters
        ----------
        sim_id : str
            Recorded simulation to archive.
        campaign : str, optional
            Campaign name, needed only when the archive template uses
            the ``{campaign}`` placeholder.

        Returns
        -------
        Path
            Location of the written zip file.

        Raises
        ------
        WorkspaceError
            If the manifest is missing, does not record ``sim_id``, or
            the simulation folder does not exist: file management
            never destroys an unrecorded run. Also when the archive
            name is already taken, because writing it would replace one
            archived run with another and then delete the folder the
            first came from.
        """
        sim = self._recorded_sim(sim_id, operation="archive")
        archive_dir = self.root / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        stem = self.naming.render_archive(sim=sim_id, campaign=campaign)
        target = archive_dir / f"{stem}.zip"
        # PYFS-006. The archive name is derived from the sim id, so
        # archiving the same sim twice renders the same name, and
        # ZipFile(..., "w") truncates: the second archive replaced the
        # first and the source folder was then deleted, so both copies of
        # the earlier run were gone and nothing was raised. Archiving is
        # the operation this class exists to make safe, and it was the one
        # that destroyed evidence silently.
        if target.exists():
            raise WorkspaceError(
                f"archive {target.name} already exists in archive/ and archiving "
                f"sim {sim_id!r} would replace it, then delete the folder it came "
                "from, so both copies of the earlier run would be gone. Move or "
                "rename the existing archive, or give the workspace a naming "
                "template whose archive name distinguishes the runs."
            )
        with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(sim.rglob("*")):
                if path.is_file():
                    bundle.write(path, path.relative_to(sim))
        shutil.rmtree(sim)
        return target

    def clean_sim(self, sim_id: str) -> None:
        """Remove one recorded simulation folder without archiving it.

        Raises
        ------
        WorkspaceError
            Same refusals as :meth:`archive_sim`.
        """
        sim = self._recorded_sim(sim_id, operation="clean")
        shutil.rmtree(sim)

    def _recorded_sim(self, sim_id: str, operation: str) -> Path:
        sim = self.sim_dir(sim_id)
        if not self.manifest_path.is_file():
            raise WorkspaceError(
                f"refusing to {operation} sim_{sim_id}: no manifest (runs.json) exists "
                "in this campaign root. Without the manifest the folder content cannot "
                "be accounted for, and file management never destroys an unrecorded run."
            )
        if not any(record.sim_id == sim_id for record in self.read_manifest()):
            raise WorkspaceError(
                f"refusing to {operation} sim_{sim_id}: the manifest has no record of "
                "this simulation, so its folder would be destroyed unaccounted."
            )
        if not sim.is_dir():
            raise WorkspaceError(
                f"cannot {operation} sim_{sim_id}: the folder {sim} does not exist."
            )
        return sim
