"""The survey lattice of a far-field extraction: one source of probe positions.

Pipeline role: defines the serializable cylindrical probe lattice (stations,
ring edges, uniform azimuths) that both the FlightStream probe export and the
companion CFD extraction sample. One lattice object is the single source of
probe positions for every solver, so cross-solver data loading is transparent
by construction (design note DLV-006 Sec. 2, requirement R1).

Coordinates: cylindrical ``(x, r, psi)`` aligned with the shaft axis, ``x``
positive downstream, origin at the disk center, lengths nondimensionalized by
the tip radius. The Cartesian mapping is ``y = r sin(psi)``,
``z = r cos(psi)``: ``psi = 0`` points along +z (up) and grows toward +y. A
tier-1 test pins this convention (DLV-006 Sec. 3.1: fix it once, in code, with
a test).

Azimuthal spacing is uniform by construction: the lattice stores only the
azimuth count, so a nonuniform spacing is unrepresentable. Uniform periodic
sampling is what makes the azimuthal rectangle rule spectrally accurate and the
FFT direct (DLV-006 Sec. 2.2); this is a hard design constraint, not a default.
"""

from __future__ import annotations

import numpy as np
from pydantic import ConfigDict, model_validator

from pyflightstream.probes._model import ProbeModel
from pyflightstream.probes.errors import ProbeGeometryError

__all__ = ["ProbeLattice", "build_lattice"]


class ProbeLattice(ProbeModel):
    """Serializable cylindrical probe lattice of a far-field survey.

    The lattice is a set of transverse annular planes (constant ``x``)
    plus, optionally, rings on a lateral cylinder that closes the
    control volume on the side (DLV-006 Sec. 2.1). Ring edges are
    stored explicitly so the annular area weights of the quadrature are
    exact (DLV-006 Sec. 2.2); ring centers are the sampling radii.

    Attributes
    ----------
    tip_radius : float
        Reference radius R in simulation length units; every stored
        coordinate is nondimensionalized by it. The far-field ledgers integrate
        over areas of ``tip_radius`` squared, so they are in the field's units
        times this unit squared: SI only for R in metres (see
        :class:`pyflightstream.farfield.fields.LatticeFields`).
    stations : tuple of float
        Axial positions x/R of the annular planes, strictly increasing,
        x positive downstream of the disk center.
    ring_edges : tuple of float
        Radial ring edges r/R, strictly increasing, at least two. The
        first edge must be positive: the axis r = 0 is a coordinate
        singularity of the cylindrical quadrature, so rings start
        off-axis (DLV-006 Sec. 2.2 starts them at 0.05 R).
    n_psi : int
        Number of uniformly spaced azimuths per ring. At least 8, so
        the FFT resolves the low-order harmonic content the ledgers
        need (order 0 forces, order 1 in-plane moments).
    lateral_radius : float, optional
        Radius r/R of the lateral closure cylinder; None when the
        lattice carries no lateral rings.
    lateral_stations : tuple of float
        Axial positions x/R of the lateral rings; empty exactly when
        ``lateral_radius`` is None.
    """

    # REV010-005. allow_inf_nan=False is not redundant with the comparisons
    # in the validator below, it is what makes them work: every one of them
    # is an inequality, and every inequality against NaN is False, so a NaN
    # tip radius, station or ring edge passed each check by failing to be
    # caught by it. The same reasoning already closed the scalar half of
    # PYFS-012 in FsiConfig; the survey geometry was the sibling nobody
    # re-read. Non-physical probe placement has no honest place to be
    # attributed later: the quadrature simply returns NaN.
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    tip_radius: float
    stations: tuple[float, ...]
    ring_edges: tuple[float, ...]
    n_psi: int
    lateral_radius: float | None = None
    lateral_stations: tuple[float, ...] = ()

    @model_validator(mode="after")
    def _geometry_is_physical(self) -> ProbeLattice:
        if self.tip_radius <= 0.0:
            raise ProbeGeometryError("tip_radius must be positive: it is the reference length R")
        if not self.stations:
            raise ProbeGeometryError("a lattice needs at least one annular plane station")
        if any(b <= a for a, b in zip(self.stations, self.stations[1:], strict=False)):
            raise ProbeGeometryError("stations must be strictly increasing in x/R")
        if len(self.ring_edges) < 2:
            raise ProbeGeometryError("ring_edges must bound at least one ring")
        if self.ring_edges[0] <= 0.0:
            raise ProbeGeometryError(
                "the first ring edge must be positive: r = 0 is a coordinate "
                "singularity of the cylindrical quadrature, so rings start off-axis"
            )
        if any(b <= a for a, b in zip(self.ring_edges, self.ring_edges[1:], strict=False)):
            raise ProbeGeometryError("ring_edges must be strictly increasing in r/R")
        if self.n_psi < 8:
            raise ProbeGeometryError(
                "n_psi must be at least 8: the ledgers need azimuthal harmonics "
                "up to order 1 without aliasing, plus margin for the distortion "
                "content downstream surfaces see"
            )
        # REV010-005. The lateral cylinder had no domain check at all, so a
        # negative closure radius validated: r/R < 0 is not a cylinder on
        # the other side, it is a sign error that the quadrature integrates
        # as though it were geometry.
        if self.lateral_radius is not None and self.lateral_radius <= 0.0:
            raise ProbeGeometryError(
                "lateral_radius must be positive: it is the radius r/R of the "
                "lateral closure cylinder, and a non-positive value is a sign "
                "error rather than a cylinder on the other side of the axis"
            )
        if self.lateral_radius is not None and self.lateral_radius < self.ring_edges[-1]:
            raise ProbeGeometryError(
                "lateral_radius must not be smaller than the outer ring edge "
                f"({self.ring_edges[-1]:g}): the closure cylinder would cut the annular "
                "planes instead of enclosing them"
            )
        if any(
            b <= a for a, b in zip(self.lateral_stations, self.lateral_stations[1:], strict=False)
        ):
            raise ProbeGeometryError("lateral_stations must be strictly increasing in x/R")
        if (self.lateral_radius is None) != (len(self.lateral_stations) == 0):
            raise ProbeGeometryError(
                "lateral_radius and lateral_stations come together: the lateral "
                "cylinder closes the control volume on the side, so it needs both "
                "a radius and ring stations (or neither)"
            )
        return self

    @property
    def n_r(self) -> int:
        """Number of radial rings per annular plane."""
        return len(self.ring_edges) - 1

    @property
    def ring_centers(self) -> np.ndarray:
        """Sampling radii r/R, the midpoints of the stored ring edges."""
        edges = np.asarray(self.ring_edges)
        return 0.5 * (edges[:-1] + edges[1:])

    @property
    def psi(self) -> np.ndarray:
        """Uniform azimuths in radians, ``2 pi k / n_psi`` for k = 0..n_psi-1."""
        return 2.0 * np.pi * np.arange(self.n_psi) / self.n_psi

    @property
    def delta_psi(self) -> float:
        """Uniform azimuthal step in radians."""
        return 2.0 * np.pi / self.n_psi

    def area_weights(self) -> np.ndarray:
        """Per-sample annular quadrature weights, in units of R squared.

        Returns
        -------
        numpy.ndarray
            Shape ``(n_r,)``; the weight of the sample at ring j and
            any azimuth k is ``0.5 (r_{j+1/2}^2 - r_{j-1/2}^2) dpsi``
            (DLV-006 Sec. 3.1). Summed over rings and azimuths the
            weights give the exact annular plane area.
        """
        edges = np.asarray(self.ring_edges)
        return 0.5 * (edges[1:] ** 2 - edges[:-1] ** 2) * self.delta_psi

    def plane_points(self) -> np.ndarray:
        """Nondimensional Cartesian probe positions of the annular planes.

        Returns
        -------
        numpy.ndarray
            Shape ``(n_stations, n_r, n_psi, 3)`` with components
            ``(x, y, z)/R``; ``y = r sin(psi)``, ``z = r cos(psi)``.
        """
        r = self.ring_centers
        psi = self.psi
        x = np.asarray(self.stations)
        shape = (len(x), self.n_r, self.n_psi)
        points = np.empty((*shape, 3))
        points[..., 0] = x[:, None, None]
        points[..., 1] = (r[:, None] * np.sin(psi)[None, :])[None, :, :]
        points[..., 2] = (r[:, None] * np.cos(psi)[None, :])[None, :, :]
        return points

    def lateral_points(self) -> np.ndarray:
        """Nondimensional Cartesian positions of the lateral-cylinder rings.

        Returns
        -------
        numpy.ndarray
            Shape ``(n_lateral_stations, n_psi, 3)``; empty when the
            lattice has no lateral cylinder.
        """
        if self.lateral_radius is None:
            return np.empty((0, self.n_psi, 3))
        psi = self.psi
        x = np.asarray(self.lateral_stations)
        points = np.empty((len(x), self.n_psi, 3))
        points[..., 0] = x[:, None]
        points[..., 1] = self.lateral_radius * np.sin(psi)[None, :]
        points[..., 2] = self.lateral_radius * np.cos(psi)[None, :]
        return points

    @property
    def point_count(self) -> int:
        """Total probe count: annular planes plus lateral rings."""
        lateral = len(self.lateral_stations) * self.n_psi
        return len(self.stations) * self.n_r * self.n_psi + lateral

    def dimensional_points(self) -> np.ndarray:
        """All probe positions in simulation length units, flat and ordered.

        The order is the loading contract of the whole extraction
        chain: annular planes first (station-major, then ring, then
        azimuth), lateral rings last (station-major, then azimuth).

        Returns
        -------
        numpy.ndarray
            Shape ``(point_count, 3)``, Cartesian ``(x, y, z)`` scaled
            by ``tip_radius``.
        """
        planes = self.plane_points().reshape(-1, 3)
        lateral = self.lateral_points().reshape(-1, 3)
        return np.vstack([planes, lateral]) * self.tip_radius

    def to_json(self) -> str:
        """Serialize the defining data; arrays are derived, never stored."""
        return self.model_dump_json()

    @classmethod
    def from_json(cls, text: str) -> ProbeLattice:
        """Rebuild a lattice from :meth:`to_json` output.

        The CFD extraction consumes the same serialized object to place
        its sampling points, which is what makes cross-solver loading
        transparent (DLV-006 requirement R1).
        """
        return cls.model_validate_json(text)


def _clustered_edges(
    r_inner: float,
    r_outer: float,
    n_r: int,
    hub_width: float,
    tip_width: float,
) -> np.ndarray:
    """Ring edges clustered near hub and tip, where the gradients live.

    A smooth sampling density (uniform background plus Gaussian bumps
    at the inner edge and at r/R = 1) is integrated and inverted, the
    tanh/cosine-stretching idiom of DLV-006 Sec. 2.2 in inverse-CDF
    form. Endpoints are exact.
    """
    fine = np.linspace(r_inner, r_outer, 4001)
    density = (
        1.0
        + 2.0 * np.exp(-(((fine - r_inner) / hub_width) ** 2))
        + 3.0 * np.exp(-(((fine - 1.0) / tip_width) ** 2))
    )
    cdf = np.concatenate([[0.0], np.cumsum(0.5 * (density[1:] + density[:-1]) * np.diff(fine))])
    edges = np.interp(np.linspace(0.0, cdf[-1], n_r + 1), cdf, fine)
    edges[0], edges[-1] = r_inner, r_outer
    return edges


def build_lattice(
    *,
    tip_radius: float,
    stations: tuple[float, ...] = (-2.0, -0.2, 0.2, 0.5, 1.0, 1.5, 2.0),
    n_r: int = 40,
    r_inner: float = 0.05,
    r_outer: float = 2.5,
    n_psi: int = 72,
    lateral_radius: float | None = 2.5,
    lateral_stations: tuple[float, ...] | None = None,
    hub_width: float = 0.15,
    tip_width: float = 0.10,
) -> ProbeLattice:
    """Build the dense reference lattice of the far-field survey.

    Defaults follow DLV-006 Sec. 2: inlet plane at -2 R, disk-adjacent
    planes at +-0.2 R, wake planes to 2 R, 40 rings from 0.05 R
    clustered near hub and tip, 72 uniform azimuths (5 degree step,
    harmonics to order 36 without aliasing), lateral cylinder at 2.5 R.
    If solver cost forces a reduction, cut ``n_r`` before ``n_psi`` and
    record the change (DLV-006 Sec. 2.2).

    Parameters
    ----------
    tip_radius : float
        Reference radius R in simulation length units.
    stations : tuple of float
        Annular plane positions x/R, strictly increasing.
    n_r, r_inner, r_outer : int, float, float
        Ring count and radial extent r/R of every annular plane.
    n_psi : int
        Uniform azimuth count, at least 14 for the six stored harmonics
        (DLV-006 Sec. 3.2); uniformity is structural.
    lateral_radius : float, optional
        Lateral closure cylinder radius r/R, not smaller than ``r_outer`` so the
        cylinder encloses the annular planes; None disables it.
    lateral_stations : tuple of float, optional
        Lateral ring positions x/R; defaults to ``stations`` when the
        cylinder is enabled.
    hub_width, tip_width : float
        Gaussian widths (in r/R) of the hub and tip clustering bands.

    Returns
    -------
    ProbeLattice
        Validated, serializable lattice.

    Raises
    ------
    ProbeGeometryError
        If the survey has fewer than 14 azimuths for its six stored harmonics, or
        the lateral cylinder is smaller than the outer ring edge.
    """
    if n_psi < 14:
        raise ProbeGeometryError(
            "build_lattice requires n_psi >= 14 for six stored harmonics (DLV-006 Sec. 3.2)"
        )
    lateral: tuple[float, ...] = ()
    if lateral_radius is not None:
        lateral = tuple(stations) if lateral_stations is None else tuple(lateral_stations)
    return ProbeLattice(
        tip_radius=tip_radius,
        stations=tuple(stations),
        ring_edges=tuple(_clustered_edges(r_inner, r_outer, n_r, hub_width, tip_width)),
        n_psi=n_psi,
        lateral_radius=lateral_radius,
        lateral_stations=lateral,
    )
