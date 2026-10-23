"""Matrix homes, input-library identities and workspace reference points."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path, PureWindowsPath

from pydantic import BaseModel, ConfigDict

from pyflightstream.cases import SimCase
from pyflightstream.workspace._links import is_reparse
from pyflightstream.workspace.inputs import InputArtifactError, PointXyz, PprocArtifact
from pyflightstream.workspace.manifest import WorkspaceError

#: The library kinds whose id is a file-name STEM with any extension,
#: which is what makes an ambiguity possible: two files sharing a stem
#: are two files answering to one id.
#:
#: Only ``profiles``: a profile cell is a stem. A ``geometries`` cell is
#: the whole file name with its extension, so ``wing.fsm`` beside
#: ``wing.obj`` (or an OBJ beside its ``.mtl``) are two ids, which the
#: resolver reads fine, and a bare-stem cell is already refused by the
#: resolver (PFS-2124.049). Geometries are checked by full file name
#: instead (:data:`FILE_NAME_REGISTERED_KINDS`).
#:
#: It is not any of the other kinds of ``INPUT_KINDS`` because the other
#: three build their path directly as ``<id>.toml``
#: (:func:`~pyflightstream.workspace.inputs.resolve_reference` and its
#: two siblings), so their per-kind uniqueness is enforced by the file
#: system and cannot be broken. ``references/003.yaml`` beside
#: ``references/003.toml`` is not a competing id; it is a file the
#: library provably never opens, and refusing it would be code refusing
#: something no requirement promised (FR-33a, OPS-2005.08.05).
STEM_REGISTERED_KINDS = ("profiles",)

#: The library kinds whose id is the whole file name, extension included:
#: two files answer to one id only when their names are equal, which a file
#: system that ignores case makes possible (``Wing.fsm`` and ``wing.fsm``).
FILE_NAME_REGISTERED_KINDS = ("geometries",)

#: Optional workspace-level declaration of the named reference points,
#: ``inputs/reference_points.toml``. A top-level registry beside
#: ``executables.toml`` rather than a kind of its own: the points are
#: properties of the campaign's geometry, written once, not one artifact
#: per id.
REFERENCE_POINTS_FILE = "reference_points.toml"

#: ``ERP`` alone, or ``ERP`` with a propulsor number.
_ERP_PATTERN = re.compile(r"ERP(0|[1-9][0-9]*)?")

#: How many missing numbered points a gap refusal lists before it counts the rest.
_LISTED_GAPS = 8

#: The airframe reference point. Singular by construction.
_AIRFRAME_POINT = "ARP"


#: The two folders a workspace's matrices live in, relative to its root.
MATRIX_FOLDERS: tuple[str, ...] = (".", "inputs/matrices")


def matrix_files(root: str | Path) -> list[Path]:
    """Every matrix of the workspace at ``root``: its ``*.fs`` and ``inputs/matrices/*.fs``.

    THE ONE DEFINITION of where a workspace's matrices are (P0310-POL-CENSUS).
    ``sync``, the storage layer and the repeated-POL census of the plan all
    read this list, so they cannot disagree about which matrices exist. A file
    that is a link or junction is never followed and is not listed: the link
    test reads the entry itself before anything stats its target. A
    cloud-backed regular file, whose reparse tag designates no link, is
    listed. Each folder is listed in name order, the root first.

    Parameters
    ----------
    root : str or Path
        The campaign workspace directory.

    Returns
    -------
    list of Path
        Matrix files in folder and name order, excluding links and junctions.
    """
    base = Path(root)
    found: list[Path] = []
    for relative in MATRIX_FOLDERS:
        folder = base / relative
        if not folder.is_dir():
            continue
        found.extend(
            path for path in sorted(folder.glob("*.fs")) if not is_reparse(path) and path.is_file()
        )
    return found


def _one_of_both_homes(stem: str, first: Path, second: Path) -> None:
    """Refuse one stem held in both homes with different bytes, naming both paths."""
    if first.read_bytes() != second.read_bytes():
        raise WorkspaceError(
            f"the matrix {stem} is in both homes of the workspace with different content: "
            f"{first} and {second}. Which one is meant cannot be told; keep one, or make the "
            "two identical."
        )


def matrix_by_stem(root: str | Path) -> dict[str, Path]:
    """Every matrix of the workspace at ``root``, one path per stem (P0320-MATRICES-HOME).

    ``inputs/matrices/`` is a home equal to the root (RST-1): a stem held in
    both is read ONCE when the two files hold the same bytes, and the path
    returned is the root's; with different bytes the workspace is refused,
    naming both paths, because which one ran cannot be told. The files are
    the ones :func:`matrix_files` lists.

    Parameters
    ----------
    root : str or Path
        The campaign workspace directory.

    Returns
    -------
    dict of str to Path
        One matrix path per stem, preferring the root for identical copies.

    Raises
    ------
    WorkspaceError
        When one stem is in both homes with different content.
    """
    chosen: dict[str, Path] = {}
    for path in matrix_files(root):
        first = chosen.setdefault(path.stem, path)
        if first != path:
            _one_of_both_homes(path.stem, first, path)
    return chosen


def find_matrix(root: str | Path, stem: str) -> Path | None:
    """Return the matrix ``stem`` of the workspace at ``root``, from either home, or None.

    The rule of :func:`matrix_by_stem` asked of ONE stem, so a differing pair
    of another stem does not refuse this lookup.

    Parameters
    ----------
    root : str or Path
        The campaign workspace directory.
    stem : str
        Matrix name without its ``.fs`` extension.

    Returns
    -------
    Path or None
        The matching matrix path, or None when neither home holds the stem.

    Raises
    ------
    WorkspaceError
        When ``stem`` is in both homes with different content.
    """
    found = [path for path in matrix_files(root) if path.stem == stem]
    for other in found[1:]:
        _one_of_both_homes(stem, found[0], other)
    return found[0] if found else None


def check_unique_stems(inputs_dir: str | Path) -> None:
    """Refuse a library in which two files answer to one id.

    Profiles register by file-name stem with any extension
    (:data:`STEM_REGISTERED_KINDS`), so ``thrust.csv`` beside
    ``thrust.txt`` leaves the id ``thrust`` ambiguous. Geometries register
    by the whole file name (:data:`FILE_NAME_REGISTERED_KINDS`), so
    ``wing.fsm`` beside ``wing.obj`` is two ids and is accepted; only two
    names equal but for case are refused. Until this check existed the
    ambiguity was found lazily, by the resolver, for the one id a caller
    happened to ask for, and only once a campaign was already being built.

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
    for kind in (*FILE_NAME_REGISTERED_KINDS, *STEM_REGISTERED_KINDS):
        directory = root / kind
        if not directory.is_dir():
            continue
        carriers: dict[str, list[Path]] = {}
        for path in sorted(directory.iterdir()):
            if path.is_file():
                key = path.name.casefold() if kind in FILE_NAME_REGISTERED_KINDS else path.stem
                carriers.setdefault(key, []).append(path)
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
        "A profile id is the file name stem and a geometry id is the whole file name, "
        "and each must be unique within the library, so rename or remove the extras. "
        "Two files carrying one id let a campaign be built on the file nobody meant "
        "to use.",
        kind=first_kind,
        artifact_id=first_stem,
    )


def expand_group(
    artifact: PprocArtifact,
    name: str,
    artifact_id: str,
    *,
    boundaries: Mapping[str, int] | None = None,
) -> dict[str, int]:
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
    artifact : PprocArtifact
        The loaded groups descriptor.
    name : str
        Group to expand, which is also the stem of the generated names.
    artifact_id : str
        Id the descriptor was loaded under. It is a parameter because
        :class:`~pyflightstream.workspace.inputs.PprocArtifact` carries
        no id of its own, and a refusal that cannot name the file the
        user must edit is not didactic.
    boundaries : mapping of str to int, optional
        The opened geometry's boundary inventory, label to 1-based
        index. A group member written as a NAME resolves through it
        (PFS-2028.00); its absence is the only thing that refuses one,
        and that refusal names this argument rather than telling the
        user to rewrite their artifact in positions.

    Returns
    -------
    dict of str to int
        ``{name}1`` to ``{name}N`` mapped to the members' boundary
        indices, in declared order.

    Raises
    ------
    InputArtifactError
        If the group is written EMPTY, which means every family the
        geometry carries and leaves this
        expansion no positions to number; if the descriptor declares no
        group of that name (the message
        lists the ones it does declare), if a member is a boundary label
        and no inventory was given to resolve it against, or if a member
        names a boundary the given inventory does not carry (the message
        lists the ones it does).

    Examples
    --------
    >>> from pyflightstream.workspace import PprocArtifact, expand_group
    >>> artifact = PprocArtifact(groups={"Blade": "Blade1"})
    >>> expand_group(artifact, "Blade", "prop", boundaries={"Blade1": 3})
    {'Blade1': 3}

    A list is refused with the one-alias line to write:

    >>> PprocArtifact(groups={"Blade": ["Blade1"]})  # doctest: +ELLIPSIS
    Traceback (most recent call last):
        ...
    pyflightstream._errors.InputArtifactError: ... Write Blade = "Blade1" instead.
    """
    members = artifact.groups.get(name)
    if members == []:
        raise InputArtifactError(
            f"group {name!r} of the group artifact {artifact_id!r} is written empty, which "
            "means every family the geometry carries; this "
            "expansion numbers members by their position in the list and has none to "
            "number. Write the members, or use the group on the campaign path, where "
            "the polar table and the motion resolve it against the file.",
            kind="group",
            artifact_id=artifact_id,
            available=tuple(sorted(artifact.groups)),
        )
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
        if isinstance(member, int) and not isinstance(member, bool):
            expanded[f"{name}{position}"] = member
            continue
        if not isinstance(member, str):
            # A BOOLEAN, which the model's `int | str` admits because
            # bool subclasses int. It is neither a position nor a name,
            # so it is refused here rather than being used as a label and
            # failing later with a message about an unknown boundary.
            raise InputArtifactError(
                f"group {name!r} of the group artifact {artifact_id!r} names its "
                f"member {position} as {member!r}, which is neither a boundary name "
                "nor a 1-based boundary index.",
                kind="group",
                artifact_id=artifact_id,
            )
        # Resolve label members against the supplied inventory (PFS-2028.00).
        # Refuse a missing inventory instead of asking users to replace names with
        # indices.
        if boundaries is None:
            raise InputArtifactError(
                f"group {name!r} of the group artifact {artifact_id!r} names its "
                f"member {position} as {member!r}, which is a boundary label, and no "
                "boundary inventory was given to resolve it against. A label is the "
                "spelling this package prefers; pass the geometry's inventory as "
                "boundaries={label: index} and the group expands by name. A saved "
                "simulation carries those names in its own mesh block, in the order "
                "that numbers them, and a run matrix needs none of this: a workflow "
                "declares the inventory from the geometry the row opens.",
                kind="group",
                artifact_id=artifact_id,
            )
        if member not in boundaries:
            known = ", ".join(repr(label) for label in sorted(boundaries)) or "none"
            raise InputArtifactError(
                f"group {name!r} of the group artifact {artifact_id!r} names its "
                f"member {position} as {member!r}, and the geometry's boundary "
                f"inventory carries no such boundary; it carries {known}.",
                kind="group",
                artifact_id=artifact_id,
                available=tuple(sorted(boundaries)),
            )
        expanded[f"{name}{position}"] = boundaries[member]
    return expanded


class ReferencePoints(BaseModel):
    """The named reference points one campaign declares.

    Loaded from ``inputs/reference_points.toml``, one TOML table per
    point name, each holding the coordinates of a
    :class:`~pyflightstream.workspace.inputs.PointXyz` in the simulation
    geometry reference frame (m).

    The names are a convention, not free text: ``ARP`` is the airframe
    reference point, and the rotor reference point is ``ERP`` with one
    propulsor or ``ERP1`` through ``ERPn`` with more.
    :func:`check_reference_point_names` is what enforces that.

    Attributes
    ----------
    points : dict of str to PointXyz
        Declared points, keyed by name, in declaration order.
    """

    model_config = ConfigDict(extra="forbid")

    points: dict[str, PointXyz]


ReferencePoints.__module__ = "pyflightstream.workspace"


def point_kind(name: str, point: PointXyz) -> str:
    """Say what a reference point is: its stated kind, else what its name says."""
    if point.kind is not None:
        return point.kind
    return "airframe" if name == _AIRFRAME_POINT else "rotor"


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
        numbered rotor names both appear, or if the numbered ones do
        not run from 1 without a gap. Each refusal names the offending
        name and the remedy.
    """
    numbered: list[int] = []
    singular = False
    for name in names:
        if name == _AIRFRAME_POINT:
            continue
        match = _ERP_PATTERN.fullmatch(name)
        if match is None:
            raise InputArtifactError(
                f"reference point {name!r} is not one of the standard names; declare "
                f"{_AIRFRAME_POINT} for the airframe reference point and ERP for the "
                "rotor one, or ERP1 through ERPn with more than one propulsor. The "
                "names are the convention that says how many propulsors the campaign "
                "describes, so a free name would leave that unreadable."
            )
        if match.group(1) is None:
            singular = True
        else:
            numbered.append(int(match.group(1)))
    if singular and numbered:
        listing = ", ".join(f"ERP{index}" for index in sorted(numbered))
        raise InputArtifactError(
            f"reference points declare both the singular ERP and the numbered "
            f"{listing}; the singular name means the campaign has exactly one "
            "propulsor, so the two together leave the propulsor count unreadable. "
            "Number every rotor point, or declare only ERP."
        )
    if not numbered:
        return
    if 0 in numbered:
        raise InputArtifactError(
            "reference point 'ERP0' numbers a propulsor from zero; rotor points are "
            "numbered from 1, as ERP1 through ERPn, because n is the propulsor count."
        )
    _refuse_a_numbering_gap(numbered)


def _refuse_a_numbering_gap(numbered: list[int]) -> None:
    """Refuse numbered rotor points that do not run from 1 without a gap."""
    present = sorted(set(numbered))
    missing_count = present[-1] - len(present)
    if missing_count:
        shown: list[int] = []
        previous = 0
        for value in present:
            room = _LISTED_GAPS - len(shown)
            if room > 0 and value - previous > 1:
                shown.extend(range(previous + 1, min(value, previous + 1 + room)))
            previous = value
        listing = ", ".join(f"ERP{index}" for index in shown)
        if missing_count > len(shown):
            listing += f" and {missing_count - len(shown)} more"
        raise InputArtifactError(
            f"reference points ERP1 through ERP{present[-1]} are declared with a gap: "
            f"{listing} is missing. The numbered rotor points run from 1 without a gap, "
            "because n is the propulsor count; declare the missing point or renumber."
        )


# Comment-only template written by init when no registry exists yet;
# didactic: shows the entry shape without registering a fake build.
#: PFS-2032.07. Written into `inputs/geometries/` by `init`, because that is
#: where a user looking for somewhere to put a mesh is already standing.
_GEOMETRIES_README = """\
# Where a mesh goes

**One folder per mesh, named for the mesh:**

    inputs/geometries/30_WB/30_WB.fsm
    inputs/geometries/30_WB/30_WB.boundaries.toml

A matrix row still writes the FILE name in its `GEOMETRY` cell, `30_WB.fsm`,
and the workspace looks in the folder of that name. The cell does not change
when a library is laid out this way.

## Why the folder, and not the file on its own

A mesh brings a sidecar with it: `pyfs-matrix inventory` reads the boundary
order out of the saved simulation and writes `<stem>.boundaries.toml` beside
it, and a run whose sidecar disagrees with its mesh is refused before the
solver starts. An `.obj` with no sidecar gets one from the first plan, its
boundaries read from the file's groups. One folder keeps the pair together.

**And it is how a restricted mesh enters a workspace without being copied.**
A hard link or a junction into `inputs/geometries/<stem>/` puts the file
where the row expects it while the bytes stay wherever they are allowed to
live. A copy of a large mesh per workspace is the cost this layout removes.

## A flat library still works

`inputs/geometries/30_WB.fsm` still resolves. A geometry instruction requires
its own `inputs/geometries/<stem>/` folder with the geometry and sidecars.
The `GEOMETRY` cell names the file, not the path. For older workspace formats,
see the documentation's Upgrading page.

## What is not kept here

The mesh itself, usually. A `.fsm` is large and this repository's own
workspaces keep theirs outside version control; what a shared workspace keeps
is the boundary sidecar, which is small, readable, and the thing a reviewer
needs in order to check a row's family names without the mesh.
"""

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
#
# A workspace kept in version control keeps placeholder paths here and this
# machine's real ones in executables.local.toml beside this file, which is
# read over it for the same build ids and belongs in .gitignore.
"""


_WRITERS: list[Callable[[SimCase, Path], list[Path]]] = []


def register_plan_product_writer(writer: Callable[[SimCase, Path], list[Path]]) -> None:
    """Register an optional plan-product writer once.

    Parameters
    ----------
    writer : callable
        Receives the resolved case and destination, and returns written paths.

    Returns
    -------
    None
        The callback is retained for subsequent plan requests.
    """
    if writer not in _WRITERS:
        _WRITERS.append(writer)


def write_plan_products(case: SimCase, folder: Path) -> list[Path]:
    """Write the explicitly requested plan products.

    Parameters
    ----------
    case : SimCase
        Resolved workspace point.
    folder : Path
        Destination for products of this point.

    Returns
    -------
    list[Path]
        Paths written by the registered callbacks.
    """
    return [path for writer in _WRITERS for path in writer(case, folder)]


def with_wake_companions(produced: Sequence[str | Path]) -> list[str | Path]:
    """Add each ``<stem>_wakes.vtk`` that sits beside a declared surface VTK.

    The solver writes the wake beside the surface without a second export command, so it
    joins the same containment and collision pre-scans as every declared output, before
    either file is moved. An absent companion adds nothing: it is optional.
    RPT-074 (2026-09-25) measured the default wake export and its absence with
    ``-1 DISABLE`` on FlightStream 26.124; this is not a per-timestep claim.
    """
    expanded = list(produced)
    named = {Path(path).resolve() for path in expanded}
    for path in produced:
        surface = Path(path)
        if surface.suffix.lower() != ".vtk" or surface.stem.lower().endswith("_wakes"):
            continue
        wake = surface.with_name(surface.stem + "_wakes.vtk")
        if wake.is_file() and wake.resolve() not in named:
            expanded.append(wake)
            named.add(wake.resolve())
    return expanded


def datapoint_folder_inside(sim: Path, folder: str) -> Path:
    """Return the resolved datapoint folder, refusing one that leaves its simulation (F-728).

    A datapoint folder that is a link out of the simulation would make another simulation's
    output count as this point's own evidence.
    """
    own = (sim / folder).resolve()
    if not own.is_relative_to(sim.resolve()):
        raise WorkspaceError(
            f"the datapoint folder {sim / folder} resolves to {own}, outside this "
            f"simulation's own folder {sim.resolve()}. Collecting there would file "
            "or accept another folder's output as this simulation's evidence. "
            "NOTHING HAS BEEN MOVED. Replace the link with a plain folder."
        )
    return own


def check_script_name(name: str) -> None:
    """Refuse a script name that is not a plain file name of the scripts folder (F-727)."""
    if (
        not name
        or name in {".", ".."}
        or Path(name).name != name
        or PureWindowsPath(name).name != name
        or PureWindowsPath(name).drive
    ):
        raise WorkspaceError(
            f"script name {name!r} must be a plain file name: a path, an absolute "
            "name or a parent segment would leave the simulation's scripts folder."
        )
