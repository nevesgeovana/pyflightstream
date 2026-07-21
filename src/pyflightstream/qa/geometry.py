"""Synthetic committable geometry for the Tier 3 physics cases.

Pipeline role: manufactures the NACA wing meshes the physics
regression matrix imports (PHY-01, PHY-02; SAD Section 11), so every
committed physics case is reproducible from code alone and no research
geometry ever enters the repository (CLAUDE.md invariant 5). The wing
is written as ASCII STL, one of the mesh formats the IMPORT command
accepts (SRC-003 p.307).

Reference frame: chord along +X (leading edge at x = 0), span along
+Y, thickness along +Z; all lengths in meters. A half wing spans
0 <= y <= span/2 with an open root section lying in the XZ plane, the
shape the solver's MIRROR symmetry expects: a face on the symmetry
plane would duplicate itself into coincident faces (the tip-treatment
caveat of SRC-003 p.386, paraphrased).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

__all__ = ["WingSpec", "naca4_contour", "wing_triangles", "write_stl", "generate_wing_stl"]


@dataclass(frozen=True)
class WingSpec:
    """A rectangular untwisted wing meshed from one NACA 4-digit section.

    Attributes
    ----------
    naca : str
        Four-digit NACA designation, for example ``"0012"``: maximum
        camber in percent chord, camber position in tenths of chord,
        thickness in percent chord.
    chord_m : float
        Chord length in meters; constant along the span.
    span_m : float
        Full span in meters, tip to tip.
    n_chord : int
        Chordwise panel count per surface side (upper and lower each).
    n_span : int
        Spanwise panel count over the full span; a half wing uses half
        of them.
    """

    naca: str = "0012"
    chord_m: float = 1.0
    span_m: float = 8.0
    n_chord: int = 25
    n_span: int = 40

    def __post_init__(self) -> None:
        """Reject definitions outside the implemented 4-digit family."""
        if len(self.naca) != 4 or not self.naca.isdigit():
            raise ValueError(
                f"NACA designation {self.naca!r} is not four digits; the generator "
                "implements the 4-digit family only"
            )
        if self.chord_m <= 0 or self.span_m <= 0:
            raise ValueError("chord_m and span_m must be positive lengths in meters")
        if self.n_chord < 4 or self.n_span < 2:
            raise ValueError("mesh needs at least 4 chordwise and 2 spanwise panels")

    @property
    def area_m2(self) -> float:
        """Planform reference area in m^2 (chord times span)."""
        return self.chord_m * self.span_m

    @property
    def aspect_ratio(self) -> float:
        """Aspect ratio span^2 / area of the rectangular planform."""
        return self.span_m / self.chord_m


def naca4_contour(naca: str, n_chord: int) -> np.ndarray:
    """Return the closed NACA 4-digit section contour in unit-chord axes.

    The analytic thickness polynomial uses the closed-trailing-edge
    variant (last coefficient -0.1036), so the surface can be meshed
    watertight. Chordwise stations are cosine spaced, clustering points
    at the leading and trailing edges.

    Parameters
    ----------
    naca : str
        Four-digit designation, for example ``"2412"``.
    n_chord : int
        Panels per side; the contour has ``2 * n_chord + 1`` points.

    Returns
    -------
    numpy.ndarray
        Shape ``(2 * n_chord + 1, 2)`` array of (x/c, z/c) points,
        traversing the lower surface from the trailing edge to the
        leading edge and the upper surface back; first and last point
        are both the trailing edge, so the polygon is closed.
    """
    m = int(naca[0]) / 100.0
    p = int(naca[1]) / 10.0
    t = int(naca[2:]) / 100.0
    beta = np.linspace(0.0, np.pi, n_chord + 1)
    x = 0.5 * (1.0 - np.cos(beta))  # 0 (leading edge) to 1 (trailing edge)
    half_thickness = (
        5.0 * t * (0.2969 * np.sqrt(x) - 0.1260 * x - 0.3516 * x**2 + 0.2843 * x**3 - 0.1036 * x**4)
    )
    camber = np.zeros_like(x)
    slope = np.zeros_like(x)
    if m > 0.0:
        front = x < p
        camber[front] = m / p**2 * (2.0 * p * x[front] - x[front] ** 2)
        slope[front] = 2.0 * m / p**2 * (p - x[front])
        rear = ~front
        camber[rear] = m / (1.0 - p) ** 2 * (1.0 - 2.0 * p + 2.0 * p * x[rear] - x[rear] ** 2)
        slope[rear] = 2.0 * m / (1.0 - p) ** 2 * (p - x[rear])
    theta = np.arctan(slope)
    upper = np.column_stack(
        (x - half_thickness * np.sin(theta), camber + half_thickness * np.cos(theta))
    )
    lower = np.column_stack(
        (x + half_thickness * np.sin(theta), camber - half_thickness * np.cos(theta))
    )
    return np.vstack((lower[::-1], upper[1:]))


def wing_triangles(spec: WingSpec, half: bool = False) -> np.ndarray:
    """Mesh the wing surface into outward-oriented triangles.

    Parameters
    ----------
    spec : WingSpec
        Wing definition; see :class:`WingSpec`.
    half : bool
        When True, mesh only the y >= 0 half with an open root section
        in the XZ symmetry plane (for MIRROR-symmetry runs, PHY-02);
        when False, mesh the full span with closed caps on both tips.

    Returns
    -------
    numpy.ndarray
        Shape ``(n_triangles, 3, 3)`` vertex array in meters; every
        triangle winds counterclockwise seen from outside the wing.
    """
    contour = naca4_contour(spec.naca, spec.n_chord) * spec.chord_m
    if half:
        stations = np.linspace(0.0, spec.span_m / 2.0, spec.n_span // 2 + 1)
    else:
        stations = np.linspace(-spec.span_m / 2.0, spec.span_m / 2.0, spec.n_span + 1)
    # Sections indexed [span, contour, xyz]; y ascends, which keeps one
    # winding rule valid across the whole span.
    sections = np.empty((stations.size, contour.shape[0], 3))
    sections[:, :, 0] = contour[:, 0]
    sections[:, :, 1] = stations[:, None]
    sections[:, :, 2] = contour[:, 1]
    triangles: list[np.ndarray] = []
    for j in range(stations.size - 1):
        near, far = sections[j], sections[j + 1]
        for i in range(contour.shape[0] - 1):
            quad = (near[i], near[i + 1], far[i + 1], far[i])
            triangles.append(np.array((quad[0], quad[1], quad[2])))
            triangles.append(np.array((quad[0], quad[2], quad[3])))
    triangles.extend(_tip_cap(sections[-1], outward_positive_y=True))
    if not half:
        triangles.extend(_tip_cap(sections[0], outward_positive_y=False))
    return np.array(triangles)


def _tip_cap(section: np.ndarray, outward_positive_y: bool) -> list[np.ndarray]:
    """Triangulate one tip section as a fan from a mid-camber point.

    The airfoil polygon is star shaped seen from a point on the camber
    line near mid-chord, so the fan cannot self-intersect. The contour
    traverses lower-then-upper, which is clockwise in the XZ plane and
    therefore winds +Y outward as built; the -Y cap flips each fan
    triangle.
    """
    hub = 0.5 * (section[0] + section[section.shape[0] // 2])
    hub[1] = section[0, 1]
    fan = []
    for i in range(section.shape[0] - 1):
        triangle = np.array((hub, section[i], section[i + 1]))
        if not outward_positive_y:
            triangle = triangle[::-1]
        fan.append(triangle)
    return fan


def write_stl(triangles: np.ndarray, path: str | Path, name: str = "pyflightstream_wing") -> Path:
    """Write triangles as deterministic ASCII STL.

    Parameters
    ----------
    triangles : numpy.ndarray
        Shape ``(n, 3, 3)`` vertex array in meters, outward wound.
    path : str or Path
        Destination file; parent directories must exist.
    name : str
        Solid name recorded in the STL header.

    Returns
    -------
    Path
        The written path.
    """
    lines = [f"solid {name}"]
    for triangle in triangles:
        edge_a = triangle[1] - triangle[0]
        edge_b = triangle[2] - triangle[0]
        normal = np.cross(edge_a, edge_b)
        norm = np.linalg.norm(normal)
        if norm > 0.0:
            normal = normal / norm
        lines.append(f"  facet normal {normal[0]:.9e} {normal[1]:.9e} {normal[2]:.9e}")
        lines.append("    outer loop")
        for vertex in triangle:
            lines.append(f"      vertex {vertex[0]:.9e} {vertex[1]:.9e} {vertex[2]:.9e}")
        lines.append("    endloop")
        lines.append("  endfacet")
    lines.append(f"endsolid {name}")
    destination = Path(path)
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination


def generate_wing_stl(spec: WingSpec, path: str | Path, half: bool = False) -> Path:
    """Mesh ``spec`` and write it as ASCII STL in one call.

    Parameters
    ----------
    spec : WingSpec
        Wing definition.
    path : str or Path
        Destination STL file.
    half : bool
        Mesh the open-root y >= 0 half instead of the full span.

    Returns
    -------
    Path
        The written path.
    """
    label = f"naca{spec.naca}_{'half' if half else 'full'}"
    return write_stl(wing_triangles(spec, half=half), path, name=label)
