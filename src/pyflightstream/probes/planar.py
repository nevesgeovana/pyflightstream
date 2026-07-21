"""Planar Cartesian probe grids on arbitrary coordinate frames.

Pipeline role: the controlled replacement for FlightStream volume
sections. `CREATE_NEW_RECTANGLE_VOLUME_SECTION` places its sampling
points internally (SRC-003 p.366); a :class:`PlanarProbeGrid` instead
prescribes every probe position: element size or point distribution
per in-plane axis, on a plane defined by an explicit
:class:`FrameDefinition` (origin plus axes in the reference frame,
mirroring the EDIT_COORDINATE_SYSTEM grammar). Points are transformed
to the reference frame in Python and imported with FRAME 1, so the
geometry culling of :mod:`pyflightstream.probes.geometry` always
operates on the same coordinates the solver sees.

The grid is serializable like the cylindrical survey lattice: the
JSON round trip is the cross-consumer contract, and the deterministic
point ordering (base nodes row-major in u then v; refined nodes
appended cell-major) is what a probe-export parser keys its rows on.

Units: every stored length is in simulation length units; the frame
axes are dimensionless unit vectors in the reference frame.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, model_validator

__all__ = [
    "FrameDefinition",
    "AxisSpec",
    "RefinementBand",
    "PlanarProbeGrid",
    "GeometryGateReport",
    "PlannedProbes",
]

_DEGENERATE = 1e-10


def _unit(vector: tuple[float, float, float], name: str) -> np.ndarray:
    array = np.asarray(vector, dtype=float)
    norm = float(np.linalg.norm(array))
    if norm < _DEGENERATE:
        raise ValueError(
            f"{name} has near-zero length; a frame axis must be a direction, "
            "and a zero vector defines none"
        )
    return array / norm


class FrameDefinition(BaseModel):
    """A local coordinate frame expressed in the reference frame.

    Mirrors what EDIT_COORDINATE_SYSTEM sends to the solver (origin
    plus axis vectors in the reference frame, coordinate_systems
    chapter): the same object can therefore both place probe grids in
    Python and, optionally, create the matching solver-side frame via
    :func:`pyflightstream.script.helpers.coordinate_frame`.

    ``x_axis`` and ``y_axis`` are normalized on construction and
    ``y_axis`` is orthogonalized against ``x_axis`` (Gram-Schmidt);
    ``z_axis`` is their cross product, so the frame is always
    right-handed orthonormal.

    Attributes
    ----------
    origin : tuple of float
        Frame origin in the reference frame (simulation length units).
    x_axis, y_axis : tuple of float
        In-plane directions of the grid, reference-frame components;
        stored normalized and orthogonal.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    origin: tuple[float, float, float] = (0.0, 0.0, 0.0)
    x_axis: tuple[float, float, float]
    y_axis: tuple[float, float, float]

    @model_validator(mode="before")
    @classmethod
    def _orthonormalize(cls, data: dict) -> dict:
        if not isinstance(data, dict) or "x_axis" not in data or "y_axis" not in data:
            return data
        x = _unit(tuple(data["x_axis"]), "x_axis")
        y_raw = np.asarray(data["y_axis"], dtype=float)
        y_perp = y_raw - np.dot(y_raw, x) * x
        if float(np.linalg.norm(y_perp)) < _DEGENERATE:
            raise ValueError(
                "y_axis is parallel to x_axis; two independent in-plane "
                "directions are needed to define a plane"
            )
        y = y_perp / float(np.linalg.norm(y_perp))
        data = dict(data)
        data["x_axis"] = tuple(float(c) for c in x)
        data["y_axis"] = tuple(float(c) for c in y)
        return data

    @property
    def z_axis(self) -> tuple[float, float, float]:
        """Plane normal, the right-handed cross product of x and y axes."""
        z = np.cross(self.x_axis, self.y_axis)
        return tuple(float(c) for c in z)

    @property
    def basis(self) -> np.ndarray:
        """Rows are the x, y, z axes in reference-frame components."""
        return np.asarray([self.x_axis, self.y_axis, self.z_axis], dtype=float)

    def to_reference(self, local_points: np.ndarray) -> np.ndarray:
        """Transform local ``(..., 3)`` coordinates into the reference frame.

        Parameters
        ----------
        local_points : numpy.ndarray
            Coordinates along the frame axes (simulation length units).

        Returns
        -------
        numpy.ndarray
            Same shape, reference-frame coordinates.
        """
        return np.asarray(self.origin) + np.asarray(local_points, dtype=float) @ self.basis

    def from_reference(self, points: np.ndarray) -> np.ndarray:
        """Inverse of :meth:`to_reference`."""
        return (np.asarray(points, dtype=float) - np.asarray(self.origin)) @ self.basis.T


class AxisSpec(BaseModel):
    """Point distribution along one in-plane axis of a grid.

    The primary path prescribes the element size directly
    (``spacing``, uniform); the alternative prescribes a point
    ``count`` with a ``distribution``. Endpoints are always included
    exactly.

    Attributes
    ----------
    start, stop : float
        Axis extent in the local frame (simulation length units).
    spacing : float, optional
        Uniform element size; snapped so an integer number of elements
        fills the extent exactly (the snapped size never exceeds the
        requested one by more than the fill rounding).
    count : int, optional
        Number of points (at least 2); required for the nonuniform
        distributions.
    distribution : str
        ``uniform``, ``cosine`` (smooth clustering), or ``geometric``
        (element sizes in geometric progression away from the
        clustered end).
    ratio : float, optional
        Geometric growth ratio, greater than 1; geometric only.
    cluster : str
        Which end(s) get the small elements: ``start``, ``end``, or
        ``both``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    start: float
    stop: float
    spacing: float | None = None
    count: int | None = None
    distribution: Literal["uniform", "cosine", "geometric"] = "uniform"
    ratio: float | None = None
    cluster: Literal["start", "end", "both"] = "both"

    @model_validator(mode="after")
    def _specification_is_consistent(self) -> AxisSpec:
        if self.stop <= self.start:
            raise ValueError("stop must exceed start: an axis needs a positive extent")
        if self.distribution == "uniform":
            if (self.spacing is None) == (self.count is None):
                raise ValueError(
                    "a uniform axis takes exactly one of spacing (element size) "
                    "or count (number of points)"
                )
            if self.ratio is not None:
                raise ValueError("ratio only applies to the geometric distribution")
        else:
            if self.count is None or self.spacing is not None:
                raise ValueError(
                    f"the {self.distribution} distribution varies its element size, "
                    "so it takes count, never spacing"
                )
            if self.distribution == "geometric" and (self.ratio is None or self.ratio <= 1.0):
                raise ValueError(
                    "the geometric distribution needs ratio > 1: it is the growth "
                    "factor of consecutive element sizes away from the clustered end"
                )
            if self.distribution == "cosine" and self.ratio is not None:
                raise ValueError("ratio only applies to the geometric distribution")
        if self.spacing is not None and self.spacing <= 0.0:
            raise ValueError("spacing must be positive: it is the element size")
        if self.count is not None and self.count < 2:
            raise ValueError("count must be at least 2: an axis needs both endpoints")
        return self

    @property
    def extent(self) -> float:
        """Axis length, ``stop - start``."""
        return self.stop - self.start

    def points(self) -> np.ndarray:
        """Return the axis points, increasing, endpoints exact."""
        if self.distribution == "uniform":
            if self.spacing is not None:
                cells = max(1, round(self.extent / self.spacing))
            else:
                cells = self.count - 1
            return np.linspace(self.start, self.stop, cells + 1)
        t = np.linspace(0.0, 1.0, self.count)
        if self.distribution == "cosine":
            if self.cluster == "both":
                s = 0.5 * (1.0 - np.cos(np.pi * t))
            elif self.cluster == "start":
                s = 1.0 - np.cos(0.5 * np.pi * t)
            else:
                s = np.sin(0.5 * np.pi * t)
        else:
            cells = self.count - 1
            index = np.arange(cells, dtype=float)
            if self.cluster == "start":
                sizes = self.ratio**index
            elif self.cluster == "end":
                sizes = self.ratio ** index[::-1]
            else:
                sizes = self.ratio ** np.minimum(index, cells - 1 - index)
            s = np.concatenate([[0.0], np.cumsum(sizes)]) / float(np.sum(sizes))
        points = self.start + self.extent * s
        points[0], points[-1] = self.start, self.stop
        return points


class RefinementBand(BaseModel):
    """Two-level near-surface refinement of a planar grid.

    Base cells whose center lies within ``distance`` of the body
    surface (and outside the body) are re-sampled with elements
    ``factor`` times finer in both in-plane directions, the
    boundary-layer band of the survey.

    Attributes
    ----------
    distance : float
        Band thickness measured from the surface (simulation length
        units), positive.
    factor : int
        Integer subdivision factor per direction, at least 2.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    distance: float
    factor: int

    @model_validator(mode="after")
    def _band_is_physical(self) -> RefinementBand:
        if self.distance <= 0.0:
            raise ValueError(
                "distance must be positive: it is the thickness of the "
                "near-surface band that gets the finer sampling"
            )
        if self.factor < 2:
            raise ValueError("factor must be at least 2, otherwise nothing is refined")
        return self


class PlanarProbeGrid(BaseModel):
    """A planar Cartesian probe grid on an explicit frame.

    Attributes
    ----------
    frame : FrameDefinition
        Plane placement; grid points live at local ``(u, v, 0)``.
    u, v : AxisSpec
        In-plane distributions along the frame x and y axes.
    refinement : RefinementBand, optional
        Near-surface two-level refinement, applied by the geometry
        gate (it needs the body mesh to know where the surface is).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    frame: FrameDefinition
    u: AxisSpec
    v: AxisSpec
    refinement: RefinementBand | None = None

    def local_points(self) -> np.ndarray:
        """Grid nodes in the local frame, shape ``(n_u, n_v, 3)``."""
        u = self.u.points()
        v = self.v.points()
        nodes = np.zeros((len(u), len(v), 3))
        nodes[..., 0] = u[:, None]
        nodes[..., 1] = v[None, :]
        return nodes

    def base_points(self) -> np.ndarray:
        """Grid nodes in the reference frame, flat, row-major in (u, v).

        This ordering (u index major, v index minor) is part of the
        serialization contract: probe-export rows map back to grid
        nodes through it.
        """
        return self.frame.to_reference(self.local_points()).reshape(-1, 3)

    @property
    def shape(self) -> tuple[int, int]:
        """Node counts ``(n_u, n_v)`` of the base grid."""
        return len(self.u.points()), len(self.v.points())

    @property
    def point_count(self) -> int:
        """Base node count, before culling and refinement."""
        n_u, n_v = self.shape
        return n_u * n_v

    def to_json(self) -> str:
        """Serialize the defining data; points are always derived."""
        return self.model_dump_json()

    @classmethod
    def from_json(cls, text: str) -> PlanarProbeGrid:
        """Rebuild a grid from :meth:`to_json` output (cross-consumer contract)."""
        return cls.model_validate_json(text)


class GeometryGateReport(BaseModel):
    """Accounting of what the geometry gate did to a grid.

    Every run states how many probes it kept, discarded inside the
    body, and added in the refinement band, so no probe budget is
    spent silently (the design rule of the survey work: masked or
    dropped content is always reported, never implied).

    Attributes
    ----------
    base_total : int
        Base grid nodes before the gate.
    base_culled : int
        Base nodes discarded because they fall inside the body.
    refined_added : int
        Refinement-band nodes added (after their own culling).
    refined_culled : int
        Refinement-band candidates discarded inside the body.
    band_distance : float, optional
        Refinement band thickness used; None when no refinement ran.
    mesh_path : str, optional
        Surface mesh file the gate tested against; None when the gate
        ran without a mesh (no culling, no refinement).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    base_total: int
    base_culled: int
    refined_added: int
    refined_culled: int
    band_distance: float | None = None
    mesh_path: str | None = None

    @property
    def kept(self) -> int:
        """Probes that survive the gate."""
        return self.base_total - self.base_culled + self.refined_added

    @property
    def culled_fraction(self) -> float:
        """Fraction of base nodes discarded inside the body."""
        return self.base_culled / self.base_total if self.base_total else 0.0


@dataclass(frozen=True)
class PlannedProbes:
    """Final probe positions of a grid after the geometry gate.

    Attributes
    ----------
    grid : PlanarProbeGrid
        The prescribing grid.
    points : numpy.ndarray
        Reference-frame positions, shape ``(n, 3)``, in the
        deterministic order the export parser relies on: surviving
        base nodes first (row-major in u, v), then surviving refined
        nodes (cell-major, sub-row-major).
    report : GeometryGateReport
        The probe accounting of the gate.
    """

    grid: PlanarProbeGrid
    points: np.ndarray
    report: GeometryGateReport

    def to_json(self) -> str:
        """Serialize grid, points, and report together.

        The points are stored explicitly (not re-derived) because they
        depend on the surface mesh the gate ran against; the file is
        the complete loading contract for parsing the probe export.
        """
        return json.dumps(
            {
                "grid": json.loads(self.grid.to_json()),
                "points": np.asarray(self.points).tolist(),
                "report": json.loads(self.report.model_dump_json()),
            }
        )

    @classmethod
    def from_json(cls, text: str) -> PlannedProbes:
        """Rebuild from :meth:`to_json` output."""
        payload = json.loads(text)
        return cls(
            grid=PlanarProbeGrid.model_validate(payload["grid"]),
            points=np.asarray(payload["points"], dtype=float),
            report=GeometryGateReport.model_validate(payload["report"]),
        )
