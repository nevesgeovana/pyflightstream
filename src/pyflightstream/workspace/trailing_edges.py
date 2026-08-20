"""Trailing-edge extraction from a blade surface mesh, in the rotor frame.

Pipeline role: workspace layer. It turns a surface mesh the user already
has into the node list a wake-edge import reads, and hands that list to
:func:`pyflightstream.workspace.wake_edges.write_node_file`, which is the
one artifact both documented import routes consume. The extraction is
the last piece of a rotor campaign that the user had to do by hand.

THE CRITERION IS NOT A CREASE, AND THAT IS THE WHOLE POINT (design note
DD-27, decided 2026-08-20). The obvious implementation is a dihedral
angle over face adjacency, which every mesh library offers and which
this package already refuses in three places: marking wake edges from a
file exists precisely BECAUSE auto detection is an angle criterion and
"a strongly twisted blade has a trailing edge that is not a crease"
(:mod:`pyflightstream.script.helpers`). An extraction built on adjacency
angles would reimplement in Python the criterion this package moved off
the solver to escape, and a campaign would gain a different threshold
rather than a different capability.

WHAT IS COMPUTED INSTEAD. Given a surface mesh, a rotor axis and a hub
position:

1. the SPANWISE coordinate of a vertex is its distance from the rotor
   axis, measured radially from the hub and perpendicular to the axis;
2. the vertices are binned into chordwise SECTIONS by that coordinate;
3. within each section the CHORDWISE direction is taken from the
   section's own extent, never from a global axis, which is what makes
   the answer survive twist;
4. the trailing-edge node of the section is the AFTMOST vertex along
   that direction, and the node list is those vertices ordered by span.

It needs vertices and a section plane. It needs no adjacency angle, no
watertightness test and no proximity query, so it runs on a base install
with none of this package's optional extras (``PFS-2025.20.03``).

WHICH END OF THE CHORD IS AFT is decided by the rotor frame and not
guessed. A section's extent gives a LINE, which has two ends and no
sign; the sense comes from the tangential direction
``axis x radial``, and aft is the end AGAINST it. So the ``axis`` vector
carries the rotation sense by the right-hand rule, and a rotor turning
the other way is described by passing the axis the other way round. The
sign is resolved once, on the section whose chord is most nearly
tangential (the least twisted one, ordinarily near the tip), and carried
to the other sections by continuity, so a strongly twisted root section
whose chord is nearly axial never has to decide the question on its own.

IT REFUSES RATHER THAN GUESSES. With no axis and hub there is no
spanwise direction and no chord direction, so the extraction refuses
naming both. Guessing a global axis is exactly how a twisted blade gets
the wrong edge silently, which is the failure this capability exists to
remove.

WHAT IT IS NOT EVIDENCE ABOUT. Nothing here has been run against the
solver. Whether the file this feeds is the file the import command reads
is stated as open in
:func:`~pyflightstream.workspace.wake_edges.write_node_file`, and this
module changes nothing about that.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy

from pyflightstream._errors import InputArtifactError
from pyflightstream._mesh import read_mesh
from pyflightstream.workspace.wake_edges import write_node_file

__all__ = [
    "DEFAULT_SECTIONS",
    "MINIMUM_SECTION_VERTICES",
    "TrailingEdge",
    "extract_trailing_edge",
    "write_trailing_edge_node_file",
]

#: Chordwise sections cut along the span by default. A blade's trailing
#: edge is a curve and this is how finely it is sampled, so the number is
#: a modelling choice rather than a tuning constant: twenty nodes
#: describe the edge of an ordinary rotor blade without asking the mesh
#: for more resolution than a coarse one has. Raise it for a highly
#: swept edge, lower it for a coarse mesh.
DEFAULT_SECTIONS = 20

#: Vertices a section must hold for its own extent to define a chord
#: direction. Two points define a line but not a section, and one
#: defines nothing; three is the smallest number that can disagree,
#: which is what makes the direction a measurement rather than a
#: restatement of the input.
MINIMUM_SECTION_VERTICES = 3

#: How nearly tangential the best-aligned section's chord must be for the
#: aft sense to be readable at all, as the cosine between the chord
#: direction and the tangential direction. Well below any real blade: a
#: chord within 89.94 degrees of the tangential direction clears it. It
#: exists to catch the case where the mesh, the axis and the hub
#: together describe something that is not a rotor blade, not to police
#: twist.
_MINIMUM_TANGENTIAL_ALIGNMENT = 1.0e-3

#: The kind every refusal of this module carries, so a caller can tell
#: an extraction refusal from an input-library one without parsing text.
_KIND = "trailing_edges"


@dataclass(frozen=True)
class TrailingEdge:
    """One extracted trailing edge, and what it was extracted with.

    Coordinates are in the MESH's own length units throughout. This
    class never learns what that unit is, because the mesh file does not
    carry one; the unit is declared when the node list is written
    (:meth:`write_node_file`), which is where the solver reads it.

    Attributes
    ----------
    nodes : numpy.ndarray
        The trailing-edge node coordinates, shape (n, 3), in the mesh's
        reference frame and length units, ordered by increasing span.
        One node per section.
    span : numpy.ndarray
        Spanwise coordinate of each node, shape (n,), in mesh length
        units: the distance from the rotor axis, measured perpendicular
        to it. Increasing, by construction.
    axis : numpy.ndarray
        The rotor axis the extraction used, shape (3,), normalised to
        unit length. Its SENSE carries the rotation sense by the
        right-hand rule; see the module docstring.
    hub : numpy.ndarray
        The hub position the extraction used, shape (3,), in mesh length
        units and the mesh's reference frame.
    sections : int
        Number of chordwise sections the span was cut into, which is
        also ``len(nodes)``.
    """

    nodes: numpy.ndarray
    span: numpy.ndarray
    axis: numpy.ndarray
    hub: numpy.ndarray
    sections: int

    def write_node_file(self, path: str | Path, *, unit: str, overwrite: bool = False) -> Path:
        """Write this edge as the node list a wake-edge import reads.

        The route ``PFS-2025.16`` names: the extraction produces
        coordinates and
        :func:`pyflightstream.workspace.wake_edges.write_node_file`
        turns them into the file, with no third-party mesh type crossing
        the boundary.

        Parameters
        ----------
        path : str or pathlib.Path
            Destination file.
        unit : str
            Length unit the mesh coordinates are in, one of
            :func:`~pyflightstream.workspace.wake_edges.node_file_units`.
            It is DECLARED IN THE FILE and the solver reads the
            coordinates in it, so it must be the unit the MESH was built
            in; nothing here can check that, which is why it is required
            rather than defaulted.
        overwrite : bool
            Replace an existing destination.

        Returns
        -------
        pathlib.Path
            The file written.

        Raises
        ------
        InputArtifactError
            Every refusal
            :func:`~pyflightstream.workspace.wake_edges.write_node_file`
            makes, unchanged: an unrecorded unit token, an existing
            destination without ``overwrite``, and the rest.
        """
        return write_node_file(path, self.nodes, unit=unit, overwrite=overwrite)


def _three_vector(value: Any, name: str) -> numpy.ndarray:
    """Read one three-component vector, or refuse naming what it is for."""
    try:
        array = numpy.asarray(value, dtype=float).reshape(-1)
    except (TypeError, ValueError) as error:
        raise InputArtifactError(
            f"the {name} could not be read as three numbers: {error}. It is a "
            "sequence of three coordinates in the mesh's own reference frame, for "
            "example (0.0, 0.0, 1.0)",
            kind=_KIND,
        ) from error
    if array.shape != (3,):
        raise InputArtifactError(
            f"the {name} has {array.size} components and a direction in space has "
            "three. It is given in the mesh's own reference frame, in the order x, "
            "y, z",
            kind=_KIND,
        )
    if not bool(numpy.isfinite(array).all()):
        raise InputArtifactError(
            f"the {name} carries a component that is not a finite number, so it "
            "names no direction and no position in the mesh frame",
            kind=_KIND,
        )
    return array


def _unit_axis(value: Any) -> numpy.ndarray:
    """Read the rotor axis and normalise it, or refuse."""
    array = _three_vector(value, "rotor axis")
    length = float(numpy.linalg.norm(array))
    if length == 0.0:
        raise InputArtifactError(
            "the rotor axis is the zero vector, which names no direction: with no "
            "axis there is no spanwise direction to section along and no tangential "
            "direction to tell the trailing edge from the leading one. Give the axis "
            "of rotation, pointing so that the rotor turns the right-handed way "
            "about it",
            kind=_KIND,
        )
    return array / length


def _mesh_vertices(mesh: Any) -> numpy.ndarray:
    """Return the (n, 3) vertex array of a mesh or of a mesh file path."""
    if isinstance(mesh, (str, Path)):
        try:
            mesh = read_mesh(mesh)
        except (OSError, ValueError, NotImplementedError) as error:
            # The reader's own refusals are a bare ValueError for a path
            # that is not a file and a bare NotImplementedError for a
            # suffix it has no loader for, both raised out of a public
            # name of THIS package, which FR-39 does not allow. Named
            # rather than re-worded, and chained, because the reader's
            # sentence is the specific one.
            raise InputArtifactError(
                f"the mesh file {mesh} could not be read: {error}. It is a surface "
                "mesh the reader understands from its suffix, ordinarily .obj or "
                ".stl; a path that does not exist and a suffix with no loader are "
                "the two that usually arrive here",
                kind=_KIND,
            ) from error
    vertices = getattr(mesh, "vertices", None)
    if vertices is None:
        raise InputArtifactError(
            f"the mesh is a {type(mesh).__name__} and carries no vertices, so there "
            "is nothing to section. Pass a path to a surface mesh file (.obj or "
            ".stl), or a loaded mesh. A file holding several separate bodies loads "
            "as a scene rather than as one mesh, and a blade is extracted one body "
            "at a time",
            kind=_KIND,
        )
    array = numpy.asarray(vertices, dtype=float)
    if array.ndim != 2 or array.shape[1] != 3:
        raise InputArtifactError(
            f"the mesh vertices have shape {tuple(array.shape)} and a surface mesh "
            "carries one row of three coordinates per vertex, so the array is "
            "(n, 3)",
            kind=_KIND,
        )
    if array.shape[0] < MINIMUM_SECTION_VERTICES:
        raise InputArtifactError(
            f"the mesh carries {array.shape[0]} vertices, which cannot describe a "
            "blade: a chordwise section needs at least "
            f"{MINIMUM_SECTION_VERTICES} of them before its own extent says "
            "anything about a chord direction",
            kind=_KIND,
        )
    if not bool(numpy.isfinite(array).all()):
        raise InputArtifactError(
            "the mesh carries a vertex coordinate that is not a finite number, so "
            "the spanwise coordinate of that vertex is undefined and it would fall "
            "into no section",
            kind=_KIND,
        )
    return array


def _chord_direction(points: numpy.ndarray, radial: numpy.ndarray) -> numpy.ndarray | None:
    """Return the unsigned chordwise direction of one section, or None.

    The chord is the longest dimension of an aerofoil section, so the
    direction is the first principal axis of the section's own vertices
    after the spanwise component is projected out. None when the
    section's vertices are effectively coincident, which leaves no
    direction to read.

    Parameters
    ----------
    points : numpy.ndarray
        Section vertices, shape (m, 3), in mesh length units.
    radial : numpy.ndarray
        Unit radial direction of this section, shape (3,). The component
        along it is removed so the extent is measured IN the section
        rather than across it.

    Returns
    -------
    numpy.ndarray or None
        Unit vector of shape (3,), with an arbitrary sign, or None.
    """
    centred = points - points.mean(axis=0)
    centred = centred - numpy.outer(centred @ radial, radial)
    scale = float(numpy.abs(centred).max())
    if scale == 0.0:
        return None
    centred = centred / scale
    eigenvalues, eigenvectors = numpy.linalg.eigh(centred.T @ centred)
    if float(eigenvalues[-1]) <= 0.0:
        return None
    direction = numpy.asarray(eigenvectors[:, -1], dtype=float)
    length = float(numpy.linalg.norm(direction))
    if length == 0.0:
        return None
    return direction / length


def extract_trailing_edge(
    mesh: Any,
    *,
    axis: Any = None,
    hub: Any = None,
    sections: int = DEFAULT_SECTIONS,
) -> TrailingEdge:
    """Extract the trailing edge of a blade mesh in the rotor frame.

    The criterion is the aftmost vertex of each chordwise section, with
    the chordwise direction taken from the section's own extent. Read
    the module docstring for why it is not a crease criterion and how
    the aft sense is fixed.

    Parameters
    ----------
    mesh : str, pathlib.Path or trimesh.Trimesh
        The blade surface, as a mesh file to read (``.obj`` or ``.stl``)
        or as a loaded mesh. Only its vertices are used. It need not be
        watertight and no proximity query is made, so this runs on a
        base install.
    axis : array_like
        Rotor axis of rotation, three components in the mesh's reference
        frame. Normalised internally, so only the direction matters, but
        the SENSE matters: the rotor is taken to turn the right-handed
        way about it, and that is what decides which end of the chord is
        aft.
    hub : array_like
        A point on the axis of rotation, three components in the mesh's
        reference frame and length units. Together with ``axis`` it
        fixes the spanwise coordinate of every vertex.
    sections : int
        Number of chordwise sections to cut the span into, which is the
        number of nodes returned. At least two: one section yields one
        point, and a single point names no edge.

    Returns
    -------
    TrailingEdge
        The node list and what it was extracted with.

    Raises
    ------
    InputArtifactError
        If ``axis`` or ``hub`` is missing (the refusal names both,
        because neither alone defines a spanwise direction); if either
        is not three finite numbers, or the axis is the zero vector; if
        the mesh file cannot be read, or the loaded object carries no
        usable vertices; if ``sections`` is below
        two; if the vertices have no spanwise extent about the given
        axis; if a section holds too few vertices for its own extent to
        define a chord direction; or if no section's chord has a readable
        component along the tangential direction, which is the shape of
        a mesh, an axis and a hub that do not together describe a rotor
        blade.

        NOT among them, and named because the list would otherwise read
        as exhaustive of what can go wrong: two sections choosing one
        vertex. The sections partition the vertices, so that cannot
        happen; it is an internal invariant rather than a refusal (see
        the comment at the end of this function).

    Examples
    --------
    >>> from pyflightstream.workspace.trailing_edges import extract_trailing_edge
    >>> edge = extract_trailing_edge(
    ...     "blade.obj", axis=(0.0, 0.0, 1.0), hub=(0.0, 0.0, 0.0)
    ... )  # doctest: +SKIP
    >>> edge.nodes.shape  # doctest: +SKIP
    (20, 3)
    """
    if axis is None or hub is None:
        missing = ", ".join(name for name, value in (("axis", axis), ("hub", hub)) if value is None)
        raise InputArtifactError(
            f"the trailing-edge extraction was given no {missing}, and it needs BOTH: "
            "the rotor axis and the hub position are what define the spanwise "
            "direction to section along, and the tangential direction that tells the "
            "trailing edge from the leading one. Nothing here guesses a global axis, "
            "because a blade with twist has a trailing edge that a guessed axis "
            "silently gets wrong, which is the failure this extraction exists to "
            "remove. Pass axis=(x, y, z) and hub=(x, y, z) in the mesh's own frame",
            kind=_KIND,
        )
    unit_axis = _unit_axis(axis)
    hub_point = _three_vector(hub, "hub position")
    vertices = _mesh_vertices(mesh)

    if not isinstance(sections, int) or isinstance(sections, bool) or sections < 2:
        raise InputArtifactError(
            f"the extraction was asked for {sections!r} chordwise sections, and a "
            "trailing edge is a line along the span: one section yields one point, "
            "which names no edge, and a non-integer count names no sectioning at "
            f"all. Ask for two or more (the default is {DEFAULT_SECTIONS})",
            kind=_KIND,
        )

    offset = vertices - hub_point
    radial_vectors = offset - numpy.outer(offset @ unit_axis, unit_axis)
    span = numpy.linalg.norm(radial_vectors, axis=1)
    span_min = float(span.min())
    span_max = float(span.max())
    if span_max <= span_min:
        raise InputArtifactError(
            f"every vertex of the mesh lies {span_min!r} from the given rotor axis, "
            "so the blade has no spanwise extent to section along. The axis and the "
            "hub are probably not the ones this mesh was built about: the span is "
            "measured perpendicular to the axis, so a blade lying ALONG the axis "
            "collapses to a single radius",
            kind=_KIND,
        )

    edges = numpy.linspace(span_min, span_max, sections + 1)
    membership = numpy.clip(numpy.searchsorted(edges, span, side="right") - 1, 0, sections - 1)

    section_members: list[numpy.ndarray] = []
    section_chords: list[numpy.ndarray] = []
    section_tangentials: list[numpy.ndarray] = []
    for index in range(sections):
        selected = numpy.flatnonzero(membership == index)
        if selected.size < MINIMUM_SECTION_VERTICES:
            raise InputArtifactError(
                f"chordwise section {index + 1} of {sections}, spanning "
                f"{float(edges[index])!r} to {float(edges[index + 1])!r} from the "
                f"rotor axis, holds {int(selected.size)} vertices and a section "
                f"needs at least {MINIMUM_SECTION_VERTICES} for its own extent to "
                "define a chord direction. The span is being cut finer than the "
                "mesh resolves it: ask for fewer sections, or extract from a mesh "
                "with more spanwise stations",
                kind=_KIND,
            )
        points = vertices[selected]
        mean_radial = radial_vectors[selected].mean(axis=0)
        length = float(numpy.linalg.norm(mean_radial))
        if length == 0.0:
            raise InputArtifactError(
                f"chordwise section {index + 1} of {sections} has vertices spread "
                "evenly around the rotor axis, so the section has no radial "
                "direction of its own. That is the shape of a full disc or of a "
                "complete rotor rather than of one blade, and a trailing edge is "
                "extracted one blade at a time",
                kind=_KIND,
            )
        radial = mean_radial / length
        chord = _chord_direction(points, radial)
        if chord is None:
            raise InputArtifactError(
                f"chordwise section {index + 1} of {sections} has all its vertices "
                "at one point once the spanwise component is removed, so the "
                "section has no extent and no chord direction. A degenerate or "
                "duplicated band of vertices in the mesh is the usual cause",
                kind=_KIND,
            )
        tangential = numpy.cross(unit_axis, radial)
        tangential_length = float(numpy.linalg.norm(tangential))
        section_members.append(selected)
        section_chords.append(chord)
        section_tangentials.append(
            tangential / tangential_length if tangential_length else tangential
        )

    chords = _orient(section_chords, section_tangentials, sections)

    chosen: list[int] = []
    for members, chord in zip(section_members, chords, strict=True):
        chosen.append(int(members[int(numpy.argmax(vertices[members] @ chord))]))

    # Two sections cannot choose one vertex, because `membership` gives
    # every vertex exactly one section and each choice is made inside its
    # own section's members. This was written as a user-facing refusal
    # ("the sections are finer than the mesh resolves") and the
    # adversarial pass could not reach it: a refusal that cannot fire is
    # a promise nothing keeps, and this repository's rule is that a guard
    # is proven by restoring the defect it denies. Kept as an invariant
    # instead, so a future change that lets the sections overlap fails
    # here rather than writing a node list naming one edge twice.
    if len(set(chosen)) != len(chosen):
        raise AssertionError(
            "the chordwise sections no longer partition the vertices: two of them "
            f"chose the same mesh vertex out of {sections}"
        )

    order = numpy.asarray(chosen, dtype=int)
    return TrailingEdge(
        nodes=vertices[order],
        span=span[order],
        axis=unit_axis,
        hub=hub_point,
        sections=sections,
    )


def _orient(
    chords: list[numpy.ndarray],
    tangentials: list[numpy.ndarray],
    sections: int,
) -> list[numpy.ndarray]:
    """Point every section's chord direction aft, consistently.

    Two steps, and the order is the point. Each section's extent gives a
    LINE, so the signs arrive independent of one another; they are first
    made CONSISTENT by walking the span and flipping any section that
    disagrees with its inboard neighbour, which is a comparison between
    two nearby chords and survives any amount of twist so long as the
    twist between neighbouring sections is under a right angle. Only
    then is the single remaining global sign decided, on the section
    whose chord is most nearly tangential, where the answer is least
    ambiguous. Deciding per section against the tangential direction
    instead would put the question to the strongly twisted root sections
    individually, which is where it is hardest and where a wrong answer
    flips one node of the edge and nothing says so.

    Parameters
    ----------
    chords : list of numpy.ndarray
        Unsigned unit chord directions, one per section, in span order.
    tangentials : list of numpy.ndarray
        Unit tangential directions ``axis x radial``, one per section.
    sections : int
        Number of sections, for the refusal text.

    Returns
    -------
    list of numpy.ndarray
        The same directions, every one pointing aft.

    Raises
    ------
    InputArtifactError
        If no section's chord has a readable component along its own
        tangential direction, so aft cannot be told from forward.
    """
    oriented = [chords[0]]
    for index in range(1, len(chords)):
        chord = chords[index]
        oriented.append(-chord if float(chord @ oriented[-1]) < 0.0 else chord)

    alignments = [
        float(chord @ tangential) for chord, tangential in zip(oriented, tangentials, strict=True)
    ]
    anchor = int(numpy.argmax(numpy.abs(alignments)))
    if abs(alignments[anchor]) < _MINIMUM_TANGENTIAL_ALIGNMENT:
        raise InputArtifactError(
            f"no chordwise section of the {sections} has a chord direction with a "
            "readable component along the rotor's tangential direction, so which "
            "end of the chord is aft cannot be told from which end is forward. The "
            "aft sense comes from the tangential direction axis x radial, and a "
            "chord perpendicular to it at every station is not a blade section: "
            "check that the axis and the hub are the ones this mesh was built "
            "about",
            kind=_KIND,
        )
    if alignments[anchor] > 0.0:
        return [-chord for chord in oriented]
    return oriented


def write_trailing_edge_node_file(
    mesh: Any,
    path: str | Path,
    *,
    axis: Any = None,
    hub: Any = None,
    unit: str,
    sections: int = DEFAULT_SECTIONS,
    overwrite: bool = False,
) -> Path:
    """Extract a blade's trailing edge and write it as an import node list.

    The whole route ``PFS-2025.16`` names, in one call: read the mesh,
    take the aftmost vertex of each chordwise section, and hand the
    coordinates to
    :func:`pyflightstream.workspace.wake_edges.write_node_file`. Nothing
    of the mesh library crosses into the file: what is written is
    coordinates.

    Parameters
    ----------
    mesh : str, pathlib.Path or trimesh.Trimesh
        The blade surface; see :func:`extract_trailing_edge`.
    path : str or pathlib.Path
        Destination node file.
    axis : array_like
        Rotor axis of rotation; see :func:`extract_trailing_edge`.
    hub : array_like
        A point on the axis of rotation; see
        :func:`extract_trailing_edge`.
    unit : str
        Length unit the MESH coordinates are in, one of
        :func:`~pyflightstream.workspace.wake_edges.node_file_units`.
        Required rather than defaulted: the file declares its own unit
        and the solver reads the coordinates in it, and nothing here can
        read a unit out of a mesh file.
    sections : int
        Number of chordwise sections, which is the number of nodes.
    overwrite : bool
        Replace an existing destination.

    Returns
    -------
    pathlib.Path
        The file written.

    Raises
    ------
    InputArtifactError
        Every refusal of :func:`extract_trailing_edge` and of
        :func:`~pyflightstream.workspace.wake_edges.write_node_file`.
        The extraction runs FIRST, so a refused extraction leaves no
        file behind.

    Examples
    --------
    >>> from pyflightstream.workspace.trailing_edges import (
    ...     write_trailing_edge_node_file,
    ... )
    >>> write_trailing_edge_node_file(
    ...     "blade.obj",
    ...     "wake_edges.csv",
    ...     axis=(0.0, 0.0, 1.0),
    ...     hub=(0.0, 0.0, 0.0),
    ...     unit="METER",
    ... )  # doctest: +SKIP
    """
    edge = extract_trailing_edge(mesh, axis=axis, hub=hub, sections=sections)
    return edge.write_node_file(path, unit=unit, overwrite=overwrite)
