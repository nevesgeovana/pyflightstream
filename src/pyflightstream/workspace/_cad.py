"""The CAD kernel interface of the geometry stages, with no kernel import.

A stage that builds, intersects, trims, queries or writes surfaces takes a :class:`CadKernel` and
never sees the library behind it. :mod:`pyflightstream.workspace._gmsh` is the one module that
imports a kernel library and holds the adapter; a permissive kernel replaces it by adding an adapter
that satisfies this protocol and changing :func:`pyflightstream.workspace._gmsh.open_kernel`.

Everything here is a plain type: a face is an opaque handle, points are tuples of floats in the
model's unit, and a result is a frozen dataclass. The interface is surfaces only: no method builds
or returns a solid.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

__all__ = [
    "CadKernel",
    "Face",
    "FragmentMap",
    "NamedFaces",
    "Point",
    "UV",
]

#: A point in the model's length unit.
Point = tuple[float, float, float]
#: A surface parameter pair.
UV = tuple[float, float]


@dataclass(frozen=True, order=True)
class Face:
    """An opaque handle to one surface of an open kernel; only the kernel that made it reads it."""

    tag: int


@dataclass(frozen=True)
class FragmentMap:
    """The result of :meth:`CadKernel.fragment`.

    ``faces`` is every face left after the operation. ``from_a`` and ``from_b`` give, for each input
    face of the two groups in order, the faces it became (one face when it was not cut).
    """

    faces: tuple[Face, ...]
    from_a: tuple[tuple[Face, ...], ...]
    from_b: tuple[tuple[Face, ...], ...]


@dataclass(frozen=True)
class NamedFaces:
    """The faces of one imported IGES file, each with the name the file gives it."""

    faces: tuple[Face, ...]
    names: tuple[str, ...]
    unit: str | None = None
    notes: tuple[str, ...] = field(default=())


@runtime_checkable
class CadKernel(Protocol):
    """What a geometry stage may ask of a CAD kernel: 22 methods in seven groups."""

    # Life
    @property
    def name(self) -> str:
        """The kernel's short name, recorded in a build identity."""
        ...

    @property
    def version(self) -> str:
        """The kernel library's version string, recorded in a build identity."""
        ...

    def close(self) -> None:
        """Release the kernel; the object is unusable afterwards. Closing twice is harmless."""
        ...

    # Build
    def add_bspline_surface(
        self,
        net: Sequence[Sequence[Point]],
        knots_u: Sequence[float],
        knots_v: Sequence[float],
        mult_u: Sequence[int],
        mult_v: Sequence[int],
        deg_u: int,
        deg_v: int,
    ) -> Face:
        """Add one non-rational B-spline surface; ``net[i][j]`` is the point at u index i."""
        ...

    def add_planar_face(self, loop: Sequence[Point]) -> Face:
        """Add a planar face bounded by the closed polyline ``loop``."""
        ...

    def add_ribbon(self, curve_points: Sequence[Point], normal_vectors: Sequence[Point]) -> Face:
        """Add the ruled face between a curve and the same curve moved along ``normal_vectors``."""
        ...

    # Boolean
    def fragment(self, a: Sequence[Face], b: Sequence[Face]) -> FragmentMap:
        """Imprint the faces of ``a`` and ``b`` on each other and return what each became."""
        ...

    # Edit
    def remove(self, faces: Sequence[Face]) -> None:
        """Delete the faces and what only they bound."""
        ...

    def copy(self, faces: Sequence[Face]) -> tuple[Face, ...]:
        """Return copies of the faces, in order."""
        ...

    def transform(self, faces: Sequence[Face], matrix: Sequence[Sequence[float]]) -> None:
        """Apply a 4 by 4 homogeneous matrix, row-major, to the faces in place."""
        ...

    # Query
    def faces(self) -> tuple[Face, ...]:
        """Return every face of the model, in creation order."""
        ...

    def boundary(self, face: Face) -> tuple[int, ...]:
        """Return the signed edge tags that bound ``face``, in loop order."""
        ...

    def adjacent(self, edge: int) -> tuple[Face, ...]:
        """Return the faces that share ``edge``; more than two means a non-manifold edge."""
        ...

    def area(self, face: Face) -> float:
        """Return the exact area of ``face``, in the model's unit squared."""
        ...

    def centroid(self, face: Face) -> Point:
        """Return the center of mass of ``face``."""
        ...

    def bbox(self, face: Face) -> tuple[Point, Point]:
        """Return the axis-aligned bounding box of ``face`` as ``(minimum, maximum)``."""
        ...

    def uv_bounds(self, face: Face) -> tuple[UV, UV]:
        """Return the parametric bounds of ``face`` as ``(minimum, maximum)``."""
        ...

    def value(self, face: Face, uv: UV) -> Point:
        """Return the point of ``face`` at ``uv``."""
        ...

    def normal(self, face: Face, uv: UV) -> Point:
        """Return the unit normal of ``face`` at ``uv``."""
        ...

    def derivative(self, face: Face, uv: UV) -> tuple[Point, Point]:
        """Return the partial derivatives ``(d/du, d/dv)`` of ``face`` at ``uv``."""
        ...

    def closest(self, face: Face, points: Sequence[Point]) -> tuple[tuple[Point, UV], ...]:
        """For each point, the closest point of ``face`` and its ``uv``."""
        ...

    def is_inside(self, face: Face, uv: UV) -> bool:
        """Whether ``uv`` lies inside the trimmed face, not only inside its bounds."""
        ...

    # Hull
    def triangulate(
        self, faces: Sequence[Face], size: float
    ) -> tuple[tuple[Point, ...], tuple[tuple[int, int, int], ...]]:
        """Triangulate the faces at element size ``size``: nodes, and triangles as node indices."""
        ...

    # IO
    def import_iges(self, path: str | Path) -> NamedFaces:
        """Read one IGES file into the model and return its faces with the names the file gives."""
        ...

    def export_iges(self, groups: Mapping[str, Sequence[Face]], path: str | Path) -> None:
        """Write one IGES file, each group's faces carrying the group name as their NAME."""
        ...
