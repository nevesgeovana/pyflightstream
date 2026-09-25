"""Solid section properties of a blade, from its geometry and a material.

Pipeline role: generates the per-station structural distributions of
:class:`~pyflightstream.fsi.config.BladeProperties` instead of having
them typed into the configuration. Each station's section is a closed
contour in the section frame of :mod:`pyflightstream.fsi.config`
(chordwise toward the leading edge, normal toward the suction side,
origin on the pitch axis); :func:`solid_section_properties` computes
its area, centroid, second moments and torsion constant for a SOLID,
homogeneous section, and :func:`blade_properties_from_sections`
multiplies them by one entry of :mod:`pyflightstream.fsi.materials`
and records where every number came from beside the distributions.

What is exact and what is numerical. The area, the centroid and the
second moments of a polygon are closed forms of its vertices (Green's
theorem), exact to rounding for the polygon handed in. The torsion
constant J has no closed form for an airfoil, so it is computed
numerically from the Prandtl stress function (``laplacian(phi) = -2``
inside, ``phi = 0`` on the contour, ``J = 2 integral(phi dA)``) with
second-order finite differences on a structured grid over the section's
bounding box, the grid cut exactly at the polygon (the Shortley-Weller
stencil). The grid is recorded with the result, and refining it
converges J at second order; the tier 1 suite holds it against the
closed forms of the ellipse and the rectangle. The thin-section formula
(1/3) integral t^3 ds is computed beside it as a cross-check only and
never replaces it.

Stated hypotheses, recorded in the provenance of every generated blade:

* the section is SOLID and HOMOGENEOUS: the whole contour is filled
  with one isotropic material. A hollow shell or a spar-and-skin
  section is a different distribution and is not built here;
* the elastic axis passes through the CENTROID. The shear centre of a
  solid section is not computed; the centroid is its exact location for
  a doubly symmetric section and an approximation otherwise. The
  sectional center of gravity of a homogeneous section is the centroid,
  so the generated offset from the elastic axis to the center of
  gravity is zero;
* the flapwise bending stiffness is E times the second moment of area
  about the chordwise axis through the centroid, the axis of flap
  bending in the section frame.

Stiffness enters ONCE: the generated EI and GJ are the values a typed
configuration carries, and :mod:`pyflightstream.fsi.beam` keeps its
unit-moduli material, so no modulus is applied twice.

Only numpy is needed, so this module imports on a base install; the
beam that consumes its output needs the ``[fsi]`` extra.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray

from pyflightstream._digest import file_sha256
from pyflightstream.fsi.config import (
    BladeProperties,
    BladePropertiesProvenance,
    MaterialProvenance,
)
from pyflightstream.fsi.errors import FsiInputError
from pyflightstream.fsi.materials import MATERIALS_DATABASE_VERSION, Material
from pyflightstream.fsi.materials import material as material_entry

__all__ = [
    "BENDING_STIFFNESS_RULE",
    "DEFAULT_TORSION_GRID_CELLS",
    "ELASTIC_AXIS_HYPOTHESIS",
    "MAX_TORSION_GRID_CELLS_LONG",
    "SECTION_MODEL",
    "TORSION_METHOD",
    "PolygonMoments",
    "SolidSectionProperties",
    "TorsionConstant",
    "airfoil_section_contour",
    "blade_properties_from_sections",
    "polygon_area_moments",
    "solid_section_properties",
    "thin_section_torsion_estimate",
    "torsion_constant",
]

#: Default number of grid cells across the SHORTER side of a section's
#: bounding box for the torsion solve; the longer side gets cells of the
#: same size, up to :data:`MAX_TORSION_GRID_CELLS_LONG`.
DEFAULT_TORSION_GRID_CELLS = 64

#: Cap on the cells along the LONGER side of the bounding box. A section
#: thinner than this ratio gets cells longer than they are tall, which
#: the stencil handles; the cap bounds the solve's memory, which grows as
#: (cells along) x (cells across)^2.
MAX_TORSION_GRID_CELLS_LONG = 2048

#: The structural hypothesis on every section this module computes.
SECTION_MODEL = (
    "solid homogeneous section: the whole contour is filled with one isotropic, "
    "linear elastic material"
)

#: How the elastic axis is located, stated as the hypothesis it is.
ELASTIC_AXIS_HYPOTHESIS = (
    "hypothesis: the elastic axis passes through the centroid of each section; the "
    "shear centre is not computed (the centroid is its exact location for a doubly "
    "symmetric section only). The center of gravity of a homogeneous section is its "
    "centroid, so the offset from the elastic axis to the center of gravity is zero"
)

#: Which second moment of area the bending stiffness multiplies.
BENDING_STIFFNESS_RULE = (
    "EI = E * second moment of area about the chordwise axis through the centroid "
    "(flap bending); GJ = G * J; mass per length = rho * A; mass moments per length = "
    "rho * principal second moments of area"
)

#: How the torsion constant is computed.
TORSION_METHOD = (
    "Prandtl stress function: laplacian(phi) = -2 inside the contour, phi = 0 on it, "
    "J = 2 * integral(phi dA); second-order finite differences (Shortley-Weller) on a "
    "structured grid over the section's bounding box with nodes at the cell centres "
    "and the boundary distances cut exactly at the polygon, solved directly; the "
    "integral by the trapezoidal rule along each grid row closed at the polygon, then "
    "across the rows. The thin-section formula (1/3) integral t^3 ds is a cross-check "
    "only"
)

#: A node closer to the contour than this fraction of a cell, along a grid
#: line, is taken ON the contour (phi = 0). The error this admits is of
#: the order of the fraction times the cell size times the stress gradient.
_ON_CONTOUR_FRACTION = 1.0e-6

#: Two consecutive vertices closer than this fraction of the contour's
#: largest extent are one vertex.
_COINCIDENT_FRACTION = 1.0e-12

#: Rows of the pair test in the simple-polygon check, per chunk; bounds its
#: memory at chunk x edges booleans rather than edges squared.
_PAIR_CHUNK = 256

#: The float arrays the private helpers pass between them.
_Floats = NDArray[np.floating[Any]]


@dataclass(frozen=True)
class PolygonMoments:
    """Exact area properties of a polygonal section.

    All second moments are about axes through the centroid, in the
    section frame of the contour (x chordwise, z normal).

    Attributes
    ----------
    area_m2 : float
        Area A [m^2].
    centroid_chordwise_m, centroid_normal_m : float
        Centroid in the contour's coordinates [m].
    second_moment_flap_m4 : float
        Integral of z^2 dA about the chordwise centroidal axis [m^4]:
        the stiffness against flap bending (deflection normal to the
        chord).
    second_moment_chord_m4 : float
        Integral of x^2 dA about the normal centroidal axis [m^4]: the
        stiffness against in-plane (chordwise) bending.
    product_moment_m4 : float
        Integral of x z dA about the centroid [m^4]; zero for a section
        symmetric about either axis.
    """

    area_m2: float
    centroid_chordwise_m: float
    centroid_normal_m: float
    second_moment_flap_m4: float
    second_moment_chord_m4: float
    product_moment_m4: float

    @property
    def principal_max_m4(self) -> float:
        """Larger principal second moment of area [m^4]."""
        mean, radius = self._mohr()
        return mean + radius

    @property
    def principal_min_m4(self) -> float:
        """Smaller principal second moment of area [m^4]."""
        mean, radius = self._mohr()
        return mean - radius

    @property
    def principal_angle_rad(self) -> float:
        """Angle of the principal axis of the SMALLER second moment [rad].

        Measured from the chordwise axis toward the normal axis; zero
        for a section symmetric about its chord line, where that axis
        is the chordwise one.
        """
        return 0.5 * math.atan2(
            2.0 * self.product_moment_m4,
            self.second_moment_chord_m4 - self.second_moment_flap_m4,
        )

    def _mohr(self) -> tuple[float, float]:
        """Centre and radius of the Mohr circle of the second moments."""
        mean = 0.5 * (self.second_moment_flap_m4 + self.second_moment_chord_m4)
        half_difference = 0.5 * (self.second_moment_chord_m4 - self.second_moment_flap_m4)
        return mean, math.hypot(half_difference, self.product_moment_m4)


@dataclass(frozen=True)
class TorsionConstant:
    """Saint-Venant torsion constant of a solid section, computed numerically.

    Attributes
    ----------
    torsion_constant_m4 : float
        J [m^4]; the torsional stiffness is G J.
    grid_cells : tuple of (int, int)
        ``(cells along the longer side, cells across the shorter side)``
        of the section's bounding box.
    unknowns : int
        Grid nodes strictly inside the contour, where phi was solved.
    """

    torsion_constant_m4: float
    grid_cells: tuple[int, int]
    unknowns: int


@dataclass(frozen=True)
class SolidSectionProperties:
    """Everything the blade properties need from one solid section.

    Attributes
    ----------
    moments : PolygonMoments
        Exact area, centroid and second moments.
    torsion : TorsionConstant
        Numerical torsion constant and its grid.
    thin_section_torsion_m4 : float
        The thin-section estimate (1/3) integral t^3 ds [m^4], a
        cross-check on :attr:`torsion` and never a substitute for it.
    """

    moments: PolygonMoments
    torsion: TorsionConstant
    thin_section_torsion_m4: float


def airfoil_section_contour(
    unit_contour: ArrayLike, chord_m: float, pitch_axis_chord_fraction: float = 0.25
) -> NDArray[np.float64]:
    """Place a unit-chord airfoil contour in the blade's section frame.

    Airfoil coordinates run from the leading edge (x/c = 0) to the
    trailing edge (x/c = 1) with the upper surface at positive z/c; the
    section frame of :mod:`pyflightstream.fsi.config` has its chordwise
    axis pointing toward the LEADING edge and its origin on the pitch
    axis. This is the one conversion between the two, so the sign of
    the chordwise offsets cannot be got wrong at every call site.

    Parameters
    ----------
    unit_contour : array_like, shape (n, 2)
        Closed contour in (x/c, z/c), the upper surface being the
        suction side, for example
        :func:`pyflightstream.qa.geometry.naca4_contour`.
    chord_m : float
        Local chord [m].
    pitch_axis_chord_fraction : float
        Chordwise position of the pitch axis as a fraction of chord
        from the leading edge; 0.25 is the quarter chord, about which
        the sectional loads are exported.

    Returns
    -------
    numpy.ndarray, shape (n, 2)
        (chordwise toward the leading edge, normal toward the suction
        side) [m], origin on the pitch axis.
    """
    points = np.asarray(unit_contour, dtype=float)
    if points.ndim != 2 or points.shape[1] != 2:
        raise FsiInputError(
            f"an airfoil contour is an (n, 2) array of (x/c, z/c) points, got shape {points.shape}"
        )
    if not math.isfinite(chord_m) or chord_m <= 0.0:
        raise FsiInputError(f"chord_m must be a positive length in meters, got {chord_m!r}")
    if not 0.0 <= pitch_axis_chord_fraction <= 1.0:
        raise FsiInputError(
            "pitch_axis_chord_fraction is a fraction of chord from the leading edge, "
            f"within [0, 1]; got {pitch_axis_chord_fraction!r}"
        )
    chordwise = chord_m * (pitch_axis_chord_fraction - points[:, 0])
    normal = chord_m * points[:, 1]
    return np.column_stack((chordwise, normal))


def polygon_area_moments(contour_m: ArrayLike) -> PolygonMoments:
    """Area, centroid and centroidal second moments of a polygon, exactly.

    The contour may be open or closed (a repeated first point is
    dropped) and in either orientation; it must be a simple polygon.
    The second moments are summed over vertices already moved to the
    centroid, which keeps them exact to rounding rather than a
    difference of two large parallel-axis terms.

    Source: the vertex formulas obtained from Green's theorem for the
    moments of a simple polygon, C. Steger, "On the Calculation of
    Arbitrary Moments of Polygons", Technical Report FGBV-96-05,
    Technische Universitaet Muenchen, 1996.

    Parameters
    ----------
    contour_m : array_like, shape (n, 2)
        Vertices (chordwise, normal) [m].

    Returns
    -------
    PolygonMoments
        Area, centroid and second moments about the centroid.
    """
    polygon = _as_polygon(contour_m)
    x, z = polygon[:, 0], polygon[:, 1]
    cross = x * np.roll(z, -1) - np.roll(x, -1) * z
    area = 0.5 * float(np.sum(cross))
    centroid_x = float(np.sum((x + np.roll(x, -1)) * cross)) / (6.0 * area)
    centroid_z = float(np.sum((z + np.roll(z, -1)) * cross)) / (6.0 * area)

    xc = x - centroid_x
    zc = z - centroid_z
    xn, zn = np.roll(xc, -1), np.roll(zc, -1)
    cross_c = xc * zn - xn * zc
    integral_x2 = float(np.sum((xc * xc + xc * xn + xn * xn) * cross_c)) / 12.0
    integral_z2 = float(np.sum((zc * zc + zc * zn + zn * zn) * cross_c)) / 12.0
    integral_xz = (
        float(np.sum((xc * zn + 2.0 * xc * zc + 2.0 * xn * zn + xn * zc) * cross_c)) / 24.0
    )
    return PolygonMoments(
        area_m2=area,
        centroid_chordwise_m=centroid_x,
        centroid_normal_m=centroid_z,
        second_moment_flap_m4=integral_z2,
        second_moment_chord_m4=integral_x2,
        product_moment_m4=integral_xz,
    )


def torsion_constant(
    contour_m: ArrayLike, grid_cells: int = DEFAULT_TORSION_GRID_CELLS
) -> TorsionConstant:
    """Saint-Venant torsion constant J of a solid polygonal section.

    Solves the Prandtl stress function problem, laplacian(phi) = -2
    inside the contour with phi = 0 on it, and returns
    J = 2 integral(phi dA), for which the torsional stiffness is G J.
    The grid covers the section's bounding box with ``grid_cells``
    cells across its shorter side and cells of the same size along the
    longer side (at most :data:`MAX_TORSION_GRID_CELLS_LONG`); nodes sit
    at the cell centres. A node next to the contour uses the
    Shortley-Weller stencil with its exact distance to the polygon along
    the grid line, which keeps the scheme second-order accurate on a
    curved or slanted boundary where a staircase grid would be first
    order. The linear system is block tridiagonal (one block per grid
    column) and is solved directly, so there is no iteration tolerance.
    The integral is taken by the trapezoidal rule along every grid row,
    closed with phi = 0 at the points where the row meets the polygon,
    then across the rows.

    Refining the grid converges J at second order; doubling
    ``grid_cells`` divides the error by about four.

    Source: the Prandtl stress function formulation of Saint-Venant
    torsion and its closed forms for the elliptic and rectangular
    sections, S. P. Timoshenko and J. N. Goodier, "Theory of
    Elasticity", 3rd ed., McGraw-Hill, 1970, Chapter 10; the stencil,
    G. H. Shortley and R. Weller, "The numerical solution of Laplace's
    equation", Journal of Applied Physics 9, 334-348, 1938.

    Parameters
    ----------
    contour_m : array_like, shape (n, 2)
        Vertices of a simple polygon [m], either orientation.
    grid_cells : int
        Cells across the shorter side of the bounding box; at least 8.

    Returns
    -------
    TorsionConstant
        J [m^4], with the grid it was computed on.
    """
    if isinstance(grid_cells, bool) or not isinstance(grid_cells, int) or grid_cells < 8:
        raise FsiInputError(
            "grid_cells is the number of cells across the shorter side of the "
            f"section and must be an integer of at least 8, got {grid_cells!r}"
        )
    polygon = _as_polygon(contour_m)
    polygon = polygon - polygon.min(axis=0)
    extent = polygon.max(axis=0)
    if extent[1] > extent[0]:
        # Long side along x from here on; a reflection leaves J unchanged.
        polygon = polygon[:, ::-1]
        extent = extent[::-1]
    extent_long, extent_short = float(extent[0]), float(extent[1])
    cells_short = grid_cells
    cells_long = min(
        MAX_TORSION_GRID_CELLS_LONG,
        max(cells_short, math.ceil(extent_long / (extent_short / cells_short) - 1e-9)),
    )
    hx = extent_long / cells_long
    hz = extent_short / cells_short
    xs = (np.arange(cells_long) + 0.5) * hx
    zs = (np.arange(cells_short) + 0.5) * hz

    # Where every grid row (constant z) and column (constant x) meets the
    # polygon: the crossings are exact, so the stencil's boundary
    # distances are the polygon's own.
    rows = _crossings(polygon[:, 1], polygon[:, 0], zs)
    cols = _crossings(polygon[:, 0], polygon[:, 1], xs)

    shape = (cells_long, cells_short)
    inside_row = np.zeros(shape, dtype=bool)
    inside_col = np.zeros(shape, dtype=bool)
    west = np.zeros(shape)
    east = np.zeros(shape)
    south = np.zeros(shape)
    north = np.zeros(shape)
    for j, crossing in enumerate(rows):
        inside, before, after = _distances(crossing, xs)
        inside_row[:, j] = inside
        west[:, j] = before
        east[:, j] = after
    for i, crossing in enumerate(cols):
        inside, before, after = _distances(crossing, zs)
        inside_col[i, :] = inside
        south[i, :] = before
        north[i, :] = after

    tolerance_x = _ON_CONTOUR_FRACTION * hx
    tolerance_z = _ON_CONTOUR_FRACTION * hz
    unknown = (
        inside_row
        & inside_col
        & (west > tolerance_x)
        & (east > tolerance_x)
        & (south > tolerance_z)
        & (north > tolerance_z)
    )
    west = np.where(unknown, np.minimum(west, hx), 1.0)
    east = np.where(unknown, np.minimum(east, hx), 1.0)
    south = np.where(unknown, np.minimum(south, hz), 1.0)
    north = np.where(unknown, np.minimum(north, hz), 1.0)

    coefficient_east = 2.0 / (east * (east + west))
    coefficient_west = 2.0 / (west * (east + west))
    coefficient_north = 2.0 / (north * (north + south))
    coefficient_south = 2.0 / (south * (north + south))
    diagonal = coefficient_east + coefficient_west + coefficient_north + coefficient_south

    # A neighbour is coupled when no crossing lies between it and the node
    # (distance a full cell) and it is itself an unknown; otherwise the
    # stencil's neighbour value is the contour's phi = 0.
    shifted_east = np.zeros(shape, dtype=bool)
    shifted_east[:-1, :] = unknown[1:, :]
    shifted_west = np.zeros(shape, dtype=bool)
    shifted_west[1:, :] = unknown[:-1, :]
    shifted_north = np.zeros(shape, dtype=bool)
    shifted_north[:, :-1] = unknown[:, 1:]
    shifted_south = np.zeros(shape, dtype=bool)
    shifted_south[:, 1:] = unknown[:, :-1]
    link_east = unknown & (east >= hx) & shifted_east
    link_west = unknown & (west >= hx) & shifted_west
    link_north = unknown & (north >= hz) & shifted_north
    link_south = unknown & (south >= hz) & shifted_south

    phi = _solve_block_tridiagonal(
        unknown,
        diagonal,
        {
            "east": np.where(link_east, coefficient_east, 0.0),
            "west": np.where(link_west, coefficient_west, 0.0),
            "north": np.where(link_north, coefficient_north, 0.0),
            "south": np.where(link_south, coefficient_south, 0.0),
        },
    )

    integral = _integrate_over_polygon(phi, xs, zs, rows, extent_short)
    unknowns = int(np.count_nonzero(unknown))
    if unknowns == 0 or integral <= 0.0:
        raise FsiInputError(
            f"the torsion grid of {cells_long} x {cells_short} cells placed no node "
            "inside the section; the contour is degenerate for its bounding box"
        )
    return TorsionConstant(
        torsion_constant_m4=2.0 * integral,
        grid_cells=(cells_long, cells_short),
        unknowns=unknowns,
    )


def thin_section_torsion_estimate(contour_m: ArrayLike, samples: int = 4096) -> float:
    """Thin-section estimate of the torsion constant, (1/3) integral t^3 ds.

    t is the section's thickness measured across its longer bounding-box
    side, integrated along that side by the midpoint rule over
    ``samples`` stations. Exact in the thin limit of a strip; for a
    thick or tapering section it differs from the true J, which is why
    it is a CROSS-CHECK on :func:`torsion_constant` and never its value:
    it tells a reader whether the computed J is of the right size.

    Source: the torsion of thin sections, J = (1/3) integral t^3 ds, in
    S. P. Timoshenko and J. N. Goodier, "Theory of Elasticity", 3rd
    ed., McGraw-Hill, 1970, Chapter 10.

    Parameters
    ----------
    contour_m : array_like, shape (n, 2)
        Vertices of a simple polygon [m].
    samples : int
        Midpoint-rule stations along the longer side.

    Returns
    -------
    float
        The estimate [m^4].
    """
    if isinstance(samples, bool) or not isinstance(samples, int) or samples < 2:
        raise FsiInputError(f"samples must be an integer of at least 2, got {samples!r}")
    polygon = _as_polygon(contour_m)
    polygon = polygon - polygon.min(axis=0)
    extent = polygon.max(axis=0)
    if extent[1] > extent[0]:
        polygon = polygon[:, ::-1]
        extent = extent[::-1]
    step = float(extent[0]) / samples
    stations = (np.arange(samples) + 0.5) * step
    total = 0.0
    for crossing in _crossings(polygon[:, 0], polygon[:, 1], stations):
        thickness = float(np.sum(crossing[1::2] - crossing[0::2]))
        total += thickness**3
    return total * step / 3.0


def solid_section_properties(
    contour_m: ArrayLike, grid_cells: int = DEFAULT_TORSION_GRID_CELLS
) -> SolidSectionProperties:
    """Area properties, torsion constant and its cross-check of one section.

    Parameters
    ----------
    contour_m : array_like, shape (n, 2)
        Vertices (chordwise, normal) [m] of a simple polygon; for a
        blade, in the section frame with the pitch axis at the origin
        (:func:`airfoil_section_contour`).
    grid_cells : int
        Cells across the shorter side for :func:`torsion_constant`.

    Returns
    -------
    SolidSectionProperties
        The exact moments, the numerical J and the thin-section estimate.
    """
    return SolidSectionProperties(
        moments=polygon_area_moments(contour_m),
        torsion=torsion_constant(contour_m, grid_cells=grid_cells),
        thin_section_torsion_m4=thin_section_torsion_estimate(contour_m),
    )


def blade_properties_from_sections(
    station_radii_m: Sequence[float],
    sections_m: Sequence[ArrayLike],
    chord_m: Sequence[float],
    geometric_pitch_deg: Sequence[float],
    material: Material | str,
    *,
    geometry_source: str,
    geometry_file: str | Path | None = None,
    torsion_grid_cells: int = DEFAULT_TORSION_GRID_CELLS,
) -> BladeProperties:
    """Generate a blade's structural distributions from its sections and a material.

    At every station the solid section's properties
    (:func:`solid_section_properties`) are multiplied by the material:
    bending stiffness E I about the chordwise centroidal axis, torsional
    stiffness G J, running mass rho A, and mass moments of inertia per
    length rho times the larger (``inertia_major_kg_m``) and the smaller
    (``inertia_minor_kg_m``) principal second moment. The elastic axis
    is placed at the centroid, a stated hypothesis
    (:data:`ELASTIC_AXIS_HYPOTHESIS`), so the elastic-axis offset from
    the pitch axis is the centroid's position in the section frame and
    the offset from the elastic axis to the center of gravity is zero.
    The provenance of all of it (the material entry and its source, the
    geometry and its sha256 when a file, the hypotheses, the torsion
    method and grid per station) is recorded in
    :attr:`BladeProperties.provenance`.

    The stiffnesses are the values a typed configuration would carry:
    the beam applies them through its unit-moduli material, so the
    modulus enters once, here.

    Source: the flexural rigidity E I and the torsional rigidity G J of
    Saint-Venant beam theory, S. P. Timoshenko and J. N. Goodier,
    "Theory of Elasticity", 3rd ed., McGraw-Hill, 1970, Chapter 10 for
    G J; the mass and the mass moments per unit length of a homogeneous
    section are its density times its area and its second moments of
    area.

    Parameters
    ----------
    station_radii_m : sequence of float
        Radial stations [m], root to tip, as in
        :attr:`BladeProperties.station_radii_m`.
    sections_m : sequence of array_like, shape (n, 2) each
        One closed contour per station in the section frame (chordwise
        toward the leading edge, normal toward the suction side), with
        the pitch axis at the origin; :func:`airfoil_section_contour`
        places an airfoil there.
    chord_m : sequence of float
        Local chord per station [m].
    geometric_pitch_deg : sequence of float
        Built-in geometric pitch per station [deg].
    material : Material or str
        An entry of :mod:`pyflightstream.fsi.materials`, or its key.
    geometry_source : str
        What the contours were built or read from, in words. It enters
        the configuration's sha256, so describe the geometry and leave
        machine paths out of it.
    geometry_file : str or Path, optional
        The file the contours were read from, when there is one; its
        sha256 and its name (not its path) are recorded.
    torsion_grid_cells : int
        Cells across the shorter side of every section for the torsion
        solve (:func:`torsion_constant`).

    Returns
    -------
    BladeProperties
        Validated distributions with their provenance.

    Examples
    --------
    >>> from pyflightstream.fsi.sections import blade_properties_from_sections
    >>> plate = [(0.02, 0.002), (-0.02, 0.002), (-0.02, -0.002), (0.02, -0.002)]
    >>> blade = blade_properties_from_sections(
    ...     [0.1, 0.5], [plate, plate], [0.04, 0.04], [20.0, 10.0],
    ...     "ti-6al-4v-grade5-annealed", geometry_source="a flat 40 x 4 mm plate",
    ... )
    >>> round(blade.mass_per_length_kg_per_m[0], 4)
    0.7088
    >>> blade.provenance.material.key
    'ti-6al-4v-grade5-annealed'
    """
    entry = material_entry(material) if isinstance(material, str) else material
    count = len(station_radii_m)
    for name, values in (
        ("sections_m", sections_m),
        ("chord_m", chord_m),
        ("geometric_pitch_deg", geometric_pitch_deg),
    ):
        if len(values) != count:
            raise FsiInputError(
                f"{name} has {len(values)} entries for {count} radial stations; "
                "every station needs its own section, chord and pitch"
            )
    if not geometry_source.strip():
        raise FsiInputError(
            "geometry_source is empty; say in words what the contours were built or "
            "read from, since the generated configuration records it as provenance"
        )
    geometry_sha256: str | None = None
    geometry_file_name: str | None = None
    if geometry_file is not None:
        path = Path(geometry_file)
        if not path.is_file():
            raise FsiInputError(
                f"geometry_file {path} is not a file; the provenance records the "
                "sha256 of the file the contours were read from, so it must exist"
            )
        geometry_sha256 = file_sha256(path)
        geometry_file_name = path.name

    properties = [solid_section_properties(section, torsion_grid_cells) for section in sections_m]
    moments = [item.moments for item in properties]
    density = entry.density_kg_per_m3

    provenance = BladePropertiesProvenance(
        generator=f"{__name__}.blade_properties_from_sections",
        material=MaterialProvenance(
            key=entry.key,
            name=entry.name,
            density_kg_per_m3=entry.density_kg_per_m3,
            youngs_modulus_pa=entry.youngs_modulus_pa,
            shear_modulus_pa=entry.shear_modulus_pa,
            poisson_ratio=entry.poisson_ratio,
            shear_modulus_basis=entry.shear_modulus_basis,
            source=entry.source.citation(),
            database_version=MATERIALS_DATABASE_VERSION,
        ),
        geometry_source=geometry_source,
        geometry_file_name=geometry_file_name,
        geometry_sha256=geometry_sha256,
        section_model=SECTION_MODEL,
        elastic_axis=ELASTIC_AXIS_HYPOTHESIS,
        bending_stiffness=BENDING_STIFFNESS_RULE,
        torsion_method=TORSION_METHOD,
        torsion_grid_cells=[list(item.torsion.grid_cells) for item in properties],
        thin_section_torsion_ratio=[
            item.thin_section_torsion_m4 / item.torsion.torsion_constant_m4 for item in properties
        ],
    )
    return BladeProperties(
        station_radii_m=list(station_radii_m),
        chord_m=list(chord_m),
        mass_per_length_kg_per_m=[density * item.area_m2 for item in moments],
        inertia_major_kg_m=[density * item.principal_max_m4 for item in moments],
        inertia_minor_kg_m=[density * item.principal_min_m4 for item in moments],
        bending_stiffness_n_m2=[
            entry.youngs_modulus_pa * item.second_moment_flap_m4 for item in moments
        ],
        torsion_stiffness_n_m2=[
            entry.shear_modulus_pa * item.torsion.torsion_constant_m4 for item in properties
        ],
        elastic_axis_offset_chordwise_m=[item.centroid_chordwise_m for item in moments],
        elastic_axis_offset_normal_m=[item.centroid_normal_m for item in moments],
        cg_offset_chordwise_m=[0.0] * count,
        cg_offset_normal_m=[0.0] * count,
        geometric_pitch_deg=list(geometric_pitch_deg),
        provenance=provenance,
    )


def _as_polygon(contour_m: ArrayLike) -> _Floats:
    """Validate a contour and return it as a counter-clockwise vertex array.

    Drops a repeated closing point and repeated consecutive points, and
    refuses anything that is not a simple polygon of positive area: a
    self-intersecting contour has no inside, and every formula of this
    module would return a number for it anyway.
    """
    points = np.asarray(contour_m, dtype=float)
    if points.ndim != 2 or points.shape[1] != 2:
        raise FsiInputError(
            "a section contour is an (n, 2) array of (chordwise, normal) vertices in "
            f"meters, got shape {points.shape}"
        )
    if not np.all(np.isfinite(points)):
        raise FsiInputError("a section contour carries a NaN or infinite coordinate")
    # Coincident within rounding, not only bit-equal: a closed airfoil
    # trailing edge is computed twice, once per surface, and the two
    # copies differ in the last bits, which would leave a zero-length edge
    # that the crossing test below reads as the two surfaces crossing.
    merge = _COINCIDENT_FRACTION * float(np.max(np.ptp(points, axis=0)))
    keep = np.ones(len(points), dtype=bool)
    keep[1:] = np.hypot(*(points[1:] - points[:-1]).T) > merge
    points = points[keep]
    if len(points) > 1 and float(np.hypot(*(points[0] - points[-1]))) <= merge:
        points = points[:-1]
    if len(points) < 3:
        raise FsiInputError(
            f"a section contour needs at least 3 distinct vertices, got {len(points)}"
        )
    x, z = points[:, 0], points[:, 1]
    twice_area = float(np.sum(x * np.roll(z, -1) - np.roll(x, -1) * z))
    span = float(np.max(np.ptp(points, axis=0)))
    if not abs(twice_area) > 1.0e-12 * span * span:
        raise FsiInputError(
            "a section contour encloses no area (its vertices are collinear or "
            "degenerate), so it describes no solid section"
        )
    if twice_area < 0.0:
        points = points[::-1].copy()
    crossing = _first_self_intersection(points)
    if crossing is not None:
        first, second = crossing
        raise FsiInputError(
            f"the section contour crosses itself: edge {first} intersects edge "
            f"{second}. A self-intersecting contour has no inside, so its area and "
            "moments would be numbers describing no section"
        )
    return points


def _first_self_intersection(points: _Floats) -> tuple[int, int] | None:
    """Return the first pair of non-adjacent edges that properly cross, if any."""
    start = points
    end = np.roll(points, -1, axis=0)
    count = len(points)
    for offset in range(0, count, _PAIR_CHUNK):
        rows = slice(offset, min(count, offset + _PAIR_CHUNK))
        a, b = start[rows, None, :], end[rows, None, :]
        c, d = start[None, :, :], end[None, :, :]
        o1 = _orientation(a, b, c)
        o2 = _orientation(a, b, d)
        o3 = _orientation(c, d, a)
        o4 = _orientation(c, d, b)
        proper = (o1 * o2 < 0.0) & (o3 * o4 < 0.0)
        index_i = np.arange(rows.start, rows.stop)[:, None]
        index_j = np.arange(count)[None, :]
        separation = np.abs(index_i - index_j)
        adjacent = (separation <= 1) | (separation == count - 1)
        proper &= ~adjacent
        hits = np.argwhere(proper)
        if hits.size:
            i, j = hits[0]
            return int(i + offset), int(j)
    return None


def _orientation(p: _Floats, q: _Floats, r: _Floats) -> _Floats:
    """Twice the signed area of the triangle (p, q, r), broadcast."""
    result: _Floats = (q[..., 0] - p[..., 0]) * (r[..., 1] - p[..., 1]) - (
        q[..., 1] - p[..., 1]
    ) * (r[..., 0] - p[..., 0])
    return result


def _crossings(
    level_coordinate: _Floats,
    along_coordinate: _Floats,
    levels: _Floats,
) -> list[_Floats]:
    """Sorted crossings of the polygon with each line ``level = constant``.

    Half-open rule: an edge crosses a line when exactly one of its ends
    lies strictly above it, so a vertex on the line is counted once and
    an edge lying along the line not at all, and every line meets the
    closed polygon an even number of times.
    """
    start_level = level_coordinate
    end_level = np.roll(level_coordinate, -1)
    start_along = along_coordinate
    end_along = np.roll(along_coordinate, -1)
    found: list[_Floats] = []
    for offset in range(0, len(levels), _PAIR_CHUNK):
        chunk = levels[offset : offset + _PAIR_CHUNK, None]
        crosses = (start_level[None, :] > chunk) != (end_level[None, :] > chunk)
        with np.errstate(divide="ignore", invalid="ignore"):
            fraction = (chunk - start_level[None, :]) / (end_level - start_level)[None, :]
        position = start_along[None, :] + fraction * (end_along - start_along)[None, :]
        for row, mask in zip(position, crosses, strict=True):
            found.append(np.sort(row[mask]))
    return found


def _distances(crossing: _Floats, positions: _Floats) -> tuple[NDArray[np.bool_], _Floats, _Floats]:
    """Inside flag and distances to the previous and next crossing, per node."""
    count = np.searchsorted(crossing, positions, side="right")
    inside = (count % 2) == 1
    before = np.zeros(len(positions))
    after = np.zeros(len(positions))
    where = np.nonzero(inside)[0]
    before[where] = positions[where] - crossing[count[where] - 1]
    after[where] = crossing[count[where]] - positions[where]
    return inside, before, after


def _solve_block_tridiagonal(
    unknown: NDArray[np.bool_],
    diagonal: _Floats,
    couplings: dict[str, _Floats],
) -> _Floats:
    """Solve the Shortley-Weller system column by column, directly.

    Unknowns are grouped by grid column; within a column the north and
    south couplings make a tridiagonal block, and the east and west
    couplings connect consecutive columns only, so the whole matrix is
    block tridiagonal. Block Gaussian elimination without pivoting
    between blocks is stable here because the matrix is an irreducibly
    diagonally dominant M-matrix, whose Schur complements stay so. The
    right-hand side is 2 at every unknown (laplacian(phi) = -2).

    Returns phi on the full grid, zero where no unknown sits.
    """
    columns, rows = unknown.shape
    local = np.full(unknown.shape, -1, dtype=int)
    members: list[NDArray[np.intp]] = []
    for i in range(columns):
        present = np.nonzero(unknown[i])[0]
        local[i, present] = np.arange(len(present))
        members.append(present)

    east, west = couplings["east"], couplings["west"]
    north, south = couplings["north"], couplings["south"]
    eliminated: list[_Floats] = []
    reduced: list[_Floats] = []
    for i in range(columns):
        present = members[i]
        size = len(present)
        if size == 0:
            eliminated.append(np.zeros((0, 0)))
            reduced.append(np.zeros(0))
            continue
        block = np.diag(diagonal[i, present])
        position = np.arange(size)
        up = north[i, present] != 0.0
        up_rows = position[up]
        block[up_rows, local[i, present[up] + 1]] = -north[i, present[up]]
        down = south[i, present] != 0.0
        down_rows = position[down]
        block[down_rows, local[i, present[down] - 1]] = -south[i, present[down]]
        rhs = np.full(size, 2.0)
        if i > 0 and len(members[i - 1]):
            to_west = np.zeros((size, len(members[i - 1])))
            linked = west[i, present] != 0.0
            to_west[position[linked], local[i - 1, present[linked]]] = -west[i, present[linked]]
            block = block - to_west @ eliminated[i - 1]
            rhs = rhs - to_west @ reduced[i - 1]
        if i + 1 < columns and len(members[i + 1]):
            to_east = np.zeros((size, len(members[i + 1])))
            linked = east[i, present] != 0.0
            to_east[position[linked], local[i + 1, present[linked]]] = -east[i, present[linked]]
            solved = np.linalg.solve(block, np.column_stack((to_east, rhs)))
            eliminated.append(solved[:, :-1])
            reduced.append(solved[:, -1])
        else:
            eliminated.append(np.zeros((size, 0)))
            reduced.append(np.linalg.solve(block, rhs))

    phi = np.zeros(unknown.shape)
    following: _Floats = np.zeros(0)
    for i in range(columns - 1, -1, -1):
        present = members[i]
        if len(present) == 0:
            following = np.zeros(0)
            continue
        values = reduced[i]
        if eliminated[i].shape[1]:
            values = values - eliminated[i] @ following
        phi[i, present] = values
        following = values
    return phi


def _integrate_over_polygon(
    phi: _Floats,
    xs: _Floats,
    zs: _Floats,
    rows: list[_Floats],
    extent_z: float,
) -> float:
    """Integral of phi over the polygon: trapezoid along rows, then across.

    Along a row the integrand is phi at the grid nodes inside each
    interval the row cuts from the polygon, closed with phi = 0 where
    the row meets the contour. Across the rows it is closed with zero at
    the bounding box's bottom and top, where the rows touch the contour
    only.
    """
    per_row = np.zeros(len(zs))
    for j, crossing in enumerate(rows):
        total = 0.0
        for low, high in zip(crossing[0::2], crossing[1::2], strict=True):
            chosen = (xs > low) & (xs < high)
            abscissa = np.concatenate(([low], xs[chosen], [high]))
            ordinate = np.concatenate(([0.0], phi[chosen, j], [0.0]))
            total += float(np.trapezoid(ordinate, abscissa))
        per_row[j] = total
    abscissa = np.concatenate(([0.0], zs, [extent_z]))
    ordinate = np.concatenate(([0.0], per_row, [0.0]))
    return float(np.trapezoid(ordinate, abscissa))
