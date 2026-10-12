"""The containers the far-field core integrates: survey samples on a lattice or a plane.

Pipeline role: the frozen numpy containers that replaced the xarray dataset of
0.39.0 (FR-457). :class:`LatticeFields` carries the samples of a cylindrical
survey lattice, shaped ``(station, ring, azimuth)``, with the lattice's own
coordinates; :class:`PlaneFields` carries the samples of a rectangular
far-field plane, shaped ``(y, z)``. Neither reads or writes a file (FR-450 R2).

Field names: axial velocity ``u`` (m/s, +x downstream), transverse Cartesian
``v`` (+y) and ``w`` (+z), cylindrical ``v_r`` and ``v_theta`` (derived, see
:func:`cylindrical_components`), pressure perturbation ``p_prime`` = p - p_inf
(Pa). Radii and stations are nondimensionalized by the lattice tip radius.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import TYPE_CHECKING

import numpy as np

from pyflightstream._errors import PyflightstreamError

if TYPE_CHECKING:
    from pyflightstream.probes.lattice import ProbeLattice

__all__ = [
    "FarfieldInputError",
    "LatticeFields",
    "PlaneFields",
    "cylindrical_components",
    "hub_frame_velocities",
    "lattice_fields",
    "plane_fields",
]

_EMPTY: Mapping[str, np.ndarray] = MappingProxyType({})


class FarfieldInputError(PyflightstreamError, ValueError):
    """A far-field reduction was given fields it cannot integrate.

    Survey fields missing a sample array the ledger needs, a harmonic request
    the azimuthal sampling cannot resolve, a flux or moment call whose arrays
    do not agree on shape or frame, a station the lattice does not carry.

    Added 2026-08-03 for FR-39, keeping ``ValueError`` as a second base.
    """


@dataclass(frozen=True, eq=False)
class LatticeFields:
    """Samples of a cylindrical survey lattice with its coordinates.

    Attributes
    ----------
    stations : numpy.ndarray
        Axial positions x/R of the annular planes, shape ``(n_stations,)``.
    ring_centers : numpy.ndarray
        Sampling radii r/R, shape ``(n_r,)``.
    ring_edges : numpy.ndarray
        Ring edges r/R, shape ``(n_r + 1,)``; the quadrature weights come
        from them.
    psi : numpy.ndarray
        Uniform azimuths in radians, shape ``(n_psi,)``.
    tip_radius : float
        Reference radius R in simulation length units (m).
    values : mapping of str to numpy.ndarray
        Sampled fields, each shaped ``(n_stations, n_r, n_psi)``.
    lateral_radius : float or None
        Radius r/R of the lateral closure cylinder; None without one.
    lateral_stations : numpy.ndarray
        Axial positions x/R of the lateral rings, shape ``(n_lateral,)``.
    lateral_values : mapping of str to numpy.ndarray
        Lateral ring samples, each shaped ``(n_lateral, n_psi)``.
    """

    stations: np.ndarray
    ring_centers: np.ndarray
    ring_edges: np.ndarray
    psi: np.ndarray
    tip_radius: float
    values: Mapping[str, np.ndarray]
    lateral_radius: float | None = None
    lateral_stations: np.ndarray = field(default_factory=lambda: np.empty(0))
    lateral_values: Mapping[str, np.ndarray] = _EMPTY

    @property
    def shape(self) -> tuple[int, int, int]:
        """The sample shape ``(n_stations, n_r, n_psi)``."""
        return (len(self.stations), len(self.ring_centers), len(self.psi))

    def __getitem__(self, name: str) -> np.ndarray:
        """Return one sampled field, refusing a name the samples do not carry."""
        try:
            return self.values[name]
        except KeyError:
            raise FarfieldInputError(
                f"the survey samples carry no field {name!r}; they carry {sorted(self.values)}"
            ) from None

    def with_values(self, **arrays: np.ndarray) -> LatticeFields:
        """Return a copy with fields added or replaced (shapes checked)."""
        merged = dict(self.values)
        for name, array in arrays.items():
            merged[name] = _checked(name, array, self.shape)
        return replace(self, values=MappingProxyType(merged))

    def with_lateral_values(self, **arrays: np.ndarray) -> LatticeFields:
        """Return a copy with lateral-ring fields added or replaced."""
        shape = (len(self.lateral_stations), len(self.psi))
        merged = dict(self.lateral_values)
        for name, array in arrays.items():
            merged[name] = _checked(name, array, shape)
        return replace(self, lateral_values=MappingProxyType(merged))

    def station_index(self, station: float) -> int:
        """Return the index of a station x/R, allowing floating-point roundoff.

        An exact match wins; otherwise the one station within ``1e-12``
        (relative and absolute) is taken, so ``0.1 * 3`` finds the plane at
        ``0.3``. A nearby plane is never guessed.

        Raises
        ------
        FarfieldInputError
            If no plane, or more than one, lies at ``station`` within the
            roundoff tolerance; the message names the available stations.
        """
        found = np.flatnonzero(self.stations == station)
        if found.size == 0:
            found = np.flatnonzero(np.isclose(self.stations, station, rtol=1e-12, atol=1e-12))
        if found.size != 1:
            raise FarfieldInputError(
                f"the lattice has no single annular plane at x/R = {station!r} "
                f"({found.size} match within 1e-12); available stations are "
                f"{[float(s) for s in self.stations]}"
            )
        return int(found[0])

    def points(self) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        """Flatten the survey into the inputs of the point writers.

        The replacement of the retired ``post.dataset_to_points``: positions
        rebuilt from the survey coordinates (``x = station R``,
        ``y = r sin(psi) R``, ``z = r cos(psi) R``, the convention of
        :mod:`pyflightstream.probes`) and every field flattened in the same
        station, ring, azimuth order, so the result drops straight into
        :func:`pyflightstream.post.writers.write_vtk_points` or
        :func:`pyflightstream.post.writers.write_tecplot_points`.

        Returns
        -------
        tuple
            ``(points, fields)``: positions ``(n, 3)`` in simulation length
            units and the flattened scalar fields.
        """
        tip = float(self.tip_radius)
        x, rr, pp = np.meshgrid(self.stations, self.ring_centers, self.psi, indexing="ij")
        points = np.column_stack(
            [
                (x * tip).ravel(),
                (rr * np.sin(pp) * tip).ravel(),
                (rr * np.cos(pp) * tip).ravel(),
            ]
        )
        return points, {name: np.asarray(array).ravel() for name, array in self.values.items()}


def _checked(name: str, values: object, shape: tuple[int, ...]) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.shape != shape:
        raise FarfieldInputError(
            f"field {name!r} has shape {array.shape}, but this lattice samples "
            f"{shape} (stations, rings, azimuths)"
        )
    return array


def lattice_fields(
    lattice: ProbeLattice,
    fields: Mapping[str, np.ndarray],
    *,
    lateral: Mapping[str, np.ndarray] | None = None,
) -> LatticeFields:
    """Assemble the survey samples of a lattice, the replacement of ``lattice_dataset``.

    Parameters
    ----------
    lattice : ProbeLattice
        Lattice that placed the probes; supplies stations, ring centers, ring
        edges, azimuths, the tip radius and the lateral cylinder.
    fields : mapping of str to numpy.ndarray
        Sampled fields of the annular planes, each shaped
        ``(n_stations, n_r, n_psi)`` in the lattice sampling order.
    lateral : mapping of str to numpy.ndarray, optional
        Sampled fields of the lateral rings, each ``(n_lateral, n_psi)``.

    Returns
    -------
    LatticeFields
        The frozen container every balance integrates.
    """
    shape = (len(lattice.stations), lattice.n_r, lattice.n_psi)
    values = {name: _checked(name, array, shape) for name, array in fields.items()}
    lateral_stations = np.asarray(lattice.lateral_stations, dtype=float)
    lateral_values: dict[str, np.ndarray] = {}
    if lateral:
        lateral_shape = (len(lateral_stations), lattice.n_psi)
        lateral_values = {
            name: _checked(name, array, lateral_shape) for name, array in lateral.items()
        }
    return LatticeFields(
        stations=np.asarray(lattice.stations),
        ring_centers=lattice.ring_centers,
        ring_edges=np.asarray(lattice.ring_edges),
        psi=lattice.psi,
        tip_radius=float(lattice.tip_radius),
        values=MappingProxyType(values),
        lateral_radius=lattice.lateral_radius,
        lateral_stations=lateral_stations,
        lateral_values=MappingProxyType(lateral_values),
    )


def cylindrical_components(fields: LatticeFields) -> LatticeFields:
    """Add the cylindrical velocity components ``v_r`` and ``v_theta``.

    Convention (fixed here and pinned by a tier-1 test, DLV-006 Sec. 3.1):
    ``y = r sin(psi)``, ``z = r cos(psi)``, so the radial unit vector is
    ``(0, sin psi, cos psi)`` and the azimuthal unit vector, in the direction
    of growing psi (+z toward +y), is ``(0, cos psi, -sin psi)``. A
    right-handed rotation about +x therefore has negative ``v_theta`` in this
    convention. The lateral rings gain the same two components where they
    carry ``v`` and ``w``.

    Parameters
    ----------
    fields : LatticeFields
        Survey samples carrying ``v`` and ``w`` (m/s).

    Returns
    -------
    LatticeFields
        A copy with ``v_r`` and ``v_theta`` added (m/s).
    """
    sin_psi = np.sin(fields.psi)
    cos_psi = np.cos(fields.psi)
    out = fields.with_values(
        v_r=fields["v"] * sin_psi + fields["w"] * cos_psi,
        v_theta=fields["v"] * cos_psi - fields["w"] * sin_psi,
    )
    lateral = fields.lateral_values
    if "v" in lateral and "w" in lateral:
        out = out.with_lateral_values(
            v_r=lateral["v"] * sin_psi + lateral["w"] * cos_psi,
            v_theta=lateral["v"] * cos_psi - lateral["w"] * sin_psi,
        )
    return out


@dataclass(frozen=True, eq=False)
class PlaneFields:
    """Samples of a uniform rectangular far-field plane (Trefftz C, wing).

    Attributes
    ----------
    y, z : numpy.ndarray
        The grid axes in the plane, in m, uniform and strictly increasing,
        shapes ``(n_y,)`` and ``(n_z,)``; ``y`` to the right and ``z`` up in
        the wind axes of the point.
    values : mapping of str to numpy.ndarray
        Sampled fields, each shaped ``(n_y, n_z)``: ``u``, ``v``, ``w`` in wind
        axes (m/s) and ``p_prime`` (Pa) where the analysis needs it.
    """

    y: np.ndarray
    z: np.ndarray
    values: Mapping[str, np.ndarray]

    def __getitem__(self, name: str) -> np.ndarray:
        """Return one sampled field, refusing a name the samples do not carry."""
        try:
            return self.values[name]
        except KeyError:
            raise FarfieldInputError(
                f"the plane samples carry no field {name!r}; they carry {sorted(self.values)}"
            ) from None


def _uniform_axis(name: str, axis: object) -> np.ndarray:
    array = np.asarray(axis, dtype=float)
    if array.ndim != 1 or array.size < 3:
        raise FarfieldInputError(f"the plane axis {name} needs at least three points")
    steps = np.diff(array)
    if not np.all(steps > 0) or not np.allclose(steps, steps[0], rtol=1e-9, atol=0.0):
        raise FarfieldInputError(
            f"the plane axis {name} is not uniform and increasing; the trapezoid rule "
            "and the vorticity differences of Trefftz C are written for a uniform grid"
        )
    return array


def plane_fields(y: object, z: object, fields: Mapping[str, np.ndarray]) -> PlaneFields:
    """Assemble the samples of a far-field plane.

    Parameters
    ----------
    y, z : array_like
        Uniform grid axes in m, each with at least three points.
    fields : mapping of str to numpy.ndarray
        Sampled fields shaped ``(len(y), len(z))``.

    Returns
    -------
    PlaneFields
        The frozen container the Trefftz C integrals take.
    """
    y_axis = _uniform_axis("y", y)
    z_axis = _uniform_axis("z", z)
    shape = (len(y_axis), len(z_axis))
    values = {}
    for name, array in fields.items():
        data = np.asarray(array, dtype=float)
        if data.shape != shape:
            raise FarfieldInputError(
                f"field {name!r} has shape {data.shape}, but this plane samples {shape} (y, z)"
            )
        values[name] = data
    return PlaneFields(y=y_axis, z=z_axis, values=MappingProxyType(values))


def hub_frame_velocities(
    points: np.ndarray,
    velocities: np.ndarray,
    *,
    omega: float,
    axis: np.ndarray,
    origin: np.ndarray,
) -> np.ndarray:
    """Convert velocities sampled in a frame turning with a rotor to its hub frame.

    A quasi-steady rotor holds its blades still and carries the rotation in the
    free stream, so a probe there reads the velocity relative to a frame that
    turns at ``omega`` about ``axis``. The hub-frame velocity adds back the
    frame velocity at the probe, ``v_hub = v + Omega x (x - x_hub)`` with
    ``Omega = omega axis`` (FR-453 R8). The positions are not moved: the
    balances of one solve read the field at one instant, where the two frames
    coincide.

    Parameters
    ----------
    points : numpy.ndarray
        Probe positions, shape ``(n, 3)``, m, in the frame the velocities are
        stated in.
    velocities : numpy.ndarray
        Sampled velocities in the turning frame, shape ``(n, 3)``, m/s.
    omega : float
        Signed rotational speed in rad/s about ``axis`` (right-handed); the sign
        is the sense of the rotor's speed.
    axis : numpy.ndarray
        The rotation axis, shape ``(3,)``; normalized here.
    origin : numpy.ndarray
        A point of the rotation axis (the hub), shape ``(3,)``, m.

    Returns
    -------
    numpy.ndarray
        Hub-frame velocities, shape ``(n, 3)``, m/s.
    """
    direction = np.asarray(axis, dtype=float)
    norm = float(np.linalg.norm(direction))
    if not np.isfinite(norm) or norm == 0.0:
        raise FarfieldInputError("the rotation axis must be a finite non-zero vector")
    arm = np.asarray(points, dtype=float) - np.asarray(origin, dtype=float)
    return np.asarray(velocities, dtype=float) + np.cross(omega * direction / norm, arm)
