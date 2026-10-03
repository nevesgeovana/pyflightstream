"""Matrix homes, input-library identities and workspace reference points."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from pyflightstream.workspace._links import _is_reparse
from pyflightstream.workspace.inputs import InputArtifactError, PointXyz, PprocArtifact
from pyflightstream.workspace.manifest import WorkspaceError

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


#: The two folders a workspace's matrices live in, relative to its root.
MATRIX_FOLDERS: tuple[str, ...] = (".", "inputs/matrices")


def matrix_files(root: str | Path) -> list[Path]:
    """Every matrix of the workspace at ``root``: its ``*.fs`` and ``inputs/matrices/*.fs``.

    THE ONE DEFINITION of where a workspace's matrices are (P0310-POL-CENSUS).
    ``sync``, the storage layer and the repeated-POL census of the plan all
    read this list, so they cannot disagree about which matrices exist. A file
    that is a link or junction is never followed and is not listed; each
    folder is listed in name order, the root first.

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
            path for path in sorted(folder.glob("*.fs")) if path.is_file() and not _is_reparse(path)
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
        geometry carries (the design decision of 2026-09-09) and leaves this
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

    Since 0.26.0, a list is refused with the one-alias line to write:

    >>> PprocArtifact(groups={"Blade": ["Blade1"]})  # doctest: +ELLIPSIS
    Traceback (most recent call last):
        ...
    pyflightstream._errors.InputArtifactError: ... Write Blade = "Blade1" instead.
    """
    members = artifact.groups.get(name)
    if members == []:
        raise InputArtifactError(
            f"group {name!r} of the group artifact {artifact_id!r} is written empty, which "
            "means every family the geometry carries (the design decision of 2026-09-09); this "
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
        # A LABEL MEMBER IS THE POINT, not an error to be reported
        # (PFS-2028.00). This function used to refuse one and tell the
        # user, in these words, to "declare the group with indices",
        # which is the package instructing a user to work with positions
        # in the one artifact that already holds the names. What a label
        # genuinely needs is an inventory to resolve against, so that is
        # what is asked for, and only its absence refuses.
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
        match = _ERP_PATTERN.match(name)
        if match is None:
            raise InputArtifactError(
                f"reference point {name!r} is not one of the standard names; declare "
                f"{_AIRFRAME_POINT} for the airframe reference point and ERP for the "
                "rotor one, or ERP1 through ERPn with more than one propulsor. The "
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
            "Number every rotor point, or declare only ERP."
        )
    if not numbered:
        return
    if 0 in numbered:
        raise InputArtifactError(
            "reference point 'ERP0' numbers a propulsor from zero; rotor points are "
            "numbered from 1, as ERP1 through ERPn, because n is the propulsor count."
        )
    expected = set(range(1, max(numbered) + 1))
    missing = sorted(expected - set(numbered))
    if missing:
        listing = ", ".join(f"ERP{index}" for index in missing)
        raise InputArtifactError(
            f"reference points ERP1 through ERP{max(numbered)} are declared with a gap: "
            f"{listing} is missing. The numbered rotor points run from 1 without a gap, "
            "because n is the propulsor count; declare the missing point or renumber."
        )
