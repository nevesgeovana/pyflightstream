"""Geometry gate of the probe planner: culling and near-surface refinement.

Pipeline role: keeps the probe budget honest. Probe points that fall
inside the body sample nothing physical, so the gate discards them
against the surface mesh (an ``.obj``/``.stl`` exported from the
simulation, see :func:`pyflightstream.run.export_surface_mesh`), and
the optional boundary-layer band re-samples the cells within a
distance ``d`` of the surface with finer elements. Every decision is
counted in the :class:`~pyflightstream.probes.planar.GeometryGateReport`:
no probe is dropped or added silently.

The containment and distance queries come from trimesh (public library
per the engineering policy), which reaches them through a SPATIAL INDEX:
scipy's kd-tree and rtree's bounds tree. Those two are what
``pip install pyflightstream[geom]`` installs and what this module's
refusal is about (license evidence reports/RPT-003). The reader itself
is a runtime dependency since 2026-08-19 (design note DD-27), so its
absence is a broken installation rather than a missing extra, and the
one accessor for it lives in :mod:`pyflightstream._mesh`. The two are
worth keeping apart: before the promotion a missing trimesh and a
missing index were one state, and afterwards a refusal naming the
reader would send a reader to reinstall a distribution they already
have. This module never runs the solver: it consumes a mesh file that
already exists.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path

import numpy as np

from pyflightstream._errors import PyflightstreamError
from pyflightstream._mesh import read_mesh
from pyflightstream.extras import MissingExtraError
from pyflightstream.probes.errors import ProbeGeometryError
from pyflightstream.probes.planar import (
    GeometryGateReport,
    PlanarProbeGrid,
    PlannedProbes,
)

__all__ = [
    "GeometryEngineMissingError",
    "OpenMeshError",
    "load_surface_mesh",
    "apply_geometry_gate",
]


class GeometryEngineMissingError(MissingExtraError):
    """The optional SPATIAL INDEX is not installed.

    Point-in-body containment and distance-to-surface queries are ray
    and nearest-neighbour searches over the mesh, and trimesh runs them
    through scipy's kd-tree and rtree's bounds tree. Those two are the
    ``[geom]`` extra; the plain installation leaves the grids fully
    usable without culling.

    WHAT THIS CLASS MEANS CHANGED ON 2026-08-19 and the old meaning is
    written down because a reader will otherwise reconstruct it wrongly.
    It used to mean "the geometry ENGINE is missing", the engine being
    trimesh, because before that date trimesh, scipy and rtree arrived
    together in one extra and no environment could hold one without the
    others. trimesh is a runtime dependency now (design note DD-27), so
    an installation carrying the reader and not the index is a state
    that can exist for the first time, and it is the only state this
    refusal is about. Naming trimesh here would send a reader to
    reinstall a distribution they already have.

    A subclass of :class:`~pyflightstream.extras.MissingExtraError`
    rather than a sibling of it, so ``except MissingExtraError`` now
    catches this one while every existing ``except
    GeometryEngineMissingError`` keeps working unchanged. It survives
    as its own name because the geometry gate is the one extra whose
    absence is RECOVERABLE: the grids stay usable without culling, so a
    caller has a reason to single it out (PYFS-025).
    """


class OpenMeshError(PyflightstreamError, ValueError):
    """The surface mesh is not watertight.

    Inside/outside is undefined for an open surface (a half model cut
    by a symmetry plane, an unclosed trailing edge): the ray-parity
    test would return arbitrary answers, so the gate refuses instead
    of guessing.
    """


#: What the ``[geom]`` extra actually installs, named once so the two
#: refusal sites cannot drift into naming different things. It is the
#: index, not the reader: see :class:`GeometryEngineMissingError`.
_SPATIAL_INDEX = "scipy and rtree, the spatial index trimesh searches through"


@contextlib.contextmanager
def _spatial_index(purpose: str) -> Iterator[None]:
    """Turn a missing spatial index into the didactic refusal.

    The guard is around the CALL rather than around an import, and that
    is not a style choice. trimesh imports scipy and rtree defensively
    and substitutes a placeholder that re-raises the original
    ``ImportError`` at the moment it is USED, so an import-time try
    would catch nothing and the reader would meet the bare
    ``ImportError`` the didactic refusal exists to replace. The original
    is chained, so a failure that is not a missing distribution stays
    diagnosable.

    Parameters
    ----------
    purpose : str
        What the caller was doing, as a sentence subject, for the
        refusal text.

    Yields
    ------
    None
        The guarded block runs unchanged when the index is present.
    """
    try:
        yield
    except ImportError as error:
        raise GeometryEngineMissingError(
            extra="geom",
            package=_SPATIAL_INDEX,
            purpose=purpose,
        ) from error


def load_surface_mesh(path: str | Path, *, require_watertight: bool = True):
    """Load a surface mesh file for the geometry gate.

    Parameters
    ----------
    path : str or pathlib.Path
        Mesh file (``.obj`` or ``.stl``), in simulation length units
        and the reference frame, as EXPORT_SURFACE_MESH writes it
        (SRC-003 pp.307-308).
    require_watertight : bool
        Refuse open meshes (the default): containment is undefined on
        them. Disable only for distance-only uses.

    Returns
    -------
    trimesh.Trimesh
        The loaded mesh.

    Raises
    ------
    OpenMeshError
        If the mesh is not watertight and containment would be
        undefined.

    Notes
    -----
    Reading a mesh needs no optional extra: it is the reader alone, and
    the reader is a runtime dependency (:mod:`pyflightstream._mesh`).
    This function raised :class:`GeometryEngineMissingError` until
    2026-08-19, when trimesh left the ``[geom]`` extra; the refusal now
    belongs to the QUERIES, which is where the index is actually
    reached.
    """
    mesh = read_mesh(path)
    if require_watertight and not mesh.is_watertight:
        raise OpenMeshError(
            f"the surface mesh {path} is not watertight, so inside/outside is "
            "undefined and containment culling would guess. Close the geometry "
            "(mirror a half model, close open ends) or run the gate with "
            "cull disabled."
        )
    return mesh


def _fine_axis(values: np.ndarray, factor: int) -> np.ndarray:
    """Subdivide each axis cell linearly into ``factor`` fine cells."""
    segments = [
        np.linspace(values[i], values[i + 1], factor + 1)[:-1] for i in range(len(values) - 1)
    ]
    return np.concatenate([*segments, [values[-1:]]], axis=None)


def _surface_distance(mesh, points: np.ndarray) -> np.ndarray:
    # RE-POINTED on 2026-08-19 at what is actually absent. This refusal
    # named trimesh as the missing package, which was right while trimesh
    # and the index arrived in one extra and became wrong the moment
    # trimesh was promoted: from that day the only way to reach this
    # branch is with the reader present and the index absent, so the old
    # text sent a reader to reinstall a distribution they already have.
    #
    # The import is inside the guarded block rather than outside it
    # because a future trimesh could move its own scipy import to module
    # level; today the failure surfaces on the CALL, which is why the
    # block covers both.
    with _spatial_index(
        "the distance-to-surface query behind the geometry gate's "
        "clearance band (or run the grid without culling)"
    ):
        from trimesh.proximity import ProximityQuery

        _, distance, _ = ProximityQuery(mesh).on_surface(points)
    return np.asarray(distance)


def _inside(mesh, points: np.ndarray) -> np.ndarray:
    """Point-in-body test, with the same refusal the distance query has.

    A NEW guard on 2026-08-19, and the reason is the promotion rather
    than an oversight found late: trimesh answers ``contains`` by ray
    casting against an rtree bounds tree, so containment needs the index
    exactly as the distance query does. It could not be reached without
    the index before, because one extra installed both the reader and
    the index; an installation carrying trimesh and not rtree is a state
    the promotion created. Unguarded it would raise a bare
    ``ImportError`` out of the public
    :func:`apply_geometry_gate`.
    """
    with _spatial_index(
        "the point-in-body containment test of the geometry gate (or run the grid without culling)"
    ):
        return np.asarray(mesh.contains(points), dtype=bool)


def apply_geometry_gate(
    grid: PlanarProbeGrid,
    mesh=None,
    *,
    mesh_path: str | Path | None = None,
    cull: bool = True,
    standoff: float = 0.0,
) -> PlannedProbes:
    """Run the geometry gate of a planar grid and return the final probes.

    Parameters
    ----------
    grid : PlanarProbeGrid
        The prescribing grid; its optional ``refinement`` band is
        honored here, because only the mesh knows where the surface
        is.
    mesh : trimesh.Trimesh, optional
        Loaded surface mesh; alternatively give ``mesh_path``.
    mesh_path : str or pathlib.Path, optional
        Mesh file to load through :func:`load_surface_mesh`.
    cull : bool
        Discard points inside the body. Disabling keeps every point
        while still allowing band refinement.
    standoff : float
        Also discard points closer to the surface than this margin
        (simulation length units). A probe on or hugging the wall
        samples the body's surface state, not the flow: the 26.120
        round trip exported zero velocity for a node sitting exactly
        on the leading edge, and near-wall probes carry
        boundary-layer columns regardless of the viscous toggles
        (reports/RPT-004). Zero disables the margin.

    Returns
    -------
    PlannedProbes
        Final reference-frame points in the deterministic parser
        order, plus the probe accounting report.

    Raises
    ------
    ValueError
        If the grid asks for refinement, or a positive standoff is
        requested, without a mesh: both are measured from the
        surface, so they cannot exist without one.
    """
    resolved_path = str(mesh_path) if mesh_path is not None else None
    if mesh is None and mesh_path is not None:
        mesh = load_surface_mesh(mesh_path)
    if grid.refinement is not None and mesh is None:
        raise ProbeGeometryError(
            "the grid prescribes a near-surface refinement band, but no surface "
            "mesh was given; the band is measured from the surface, so pass mesh "
            "or mesh_path (export one with pyflightstream.run.export_surface_mesh)"
        )
    if standoff < 0.0:
        raise ProbeGeometryError("standoff must be zero or positive: it is a wall margin")
    if standoff > 0.0 and mesh is None:
        raise ProbeGeometryError(
            "a standoff margin is measured from the surface, so it needs a mesh; "
            "pass mesh or mesh_path, or drop the margin"
        )

    base = grid.base_points()
    if mesh is not None and cull:
        inside = _inside(mesh, base)
    else:
        inside = np.zeros(len(base), dtype=bool)
    if standoff > 0.0:
        near = (_surface_distance(mesh, base) < standoff) & ~inside
    else:
        near = np.zeros(len(base), dtype=bool)
    kept_base = base[~(inside | near)]

    refined_points: list[np.ndarray] = []
    refined_culled = 0
    refined_standoff_culled = 0
    if grid.refinement is not None:
        refined, refined_culled, refined_standoff_culled = _refine_band(
            grid, mesh, cull=cull, standoff=standoff
        )
        if len(refined):
            refined_points.append(refined)

    points = np.vstack([kept_base, *refined_points]) if refined_points else kept_base
    report = GeometryGateReport(
        base_total=len(base),
        base_culled=int(inside.sum()),
        base_standoff_culled=int(near.sum()),
        refined_added=sum(len(block) for block in refined_points),
        refined_culled=refined_culled,
        refined_standoff_culled=refined_standoff_culled,
        band_distance=grid.refinement.distance if grid.refinement else None,
        standoff=standoff if standoff > 0.0 else None,
        mesh_path=resolved_path,
    )
    return PlannedProbes(grid=grid, points=points, report=report)


def _refine_band(
    grid: PlanarProbeGrid, mesh, *, cull: bool, standoff: float = 0.0
) -> tuple[np.ndarray, int, int]:
    """Fine nodes of the cells within the band distance of the surface.

    Cells are flagged by their center: within ``distance`` of the
    surface and not inside the body. Flagged cells are re-sampled
    ``factor`` times finer per direction; nodes already present in the
    base grid are skipped, and nodes shared between adjacent flagged
    cells are emitted once, in cell-major order. Candidates inside the
    body or within the standoff margin are discarded and counted.
    """
    factor = grid.refinement.factor
    distance = grid.refinement.distance
    u = grid.u.points()
    v = grid.v.points()

    centers_local = np.zeros(((len(u) - 1) * (len(v) - 1), 3))
    centers_u = 0.5 * (u[:-1] + u[1:])
    centers_v = 0.5 * (v[:-1] + v[1:])
    centers_local[:, 0] = np.repeat(centers_u, len(centers_v))
    centers_local[:, 1] = np.tile(centers_v, len(centers_u))
    centers = grid.frame.to_reference(centers_local)

    center_distance = _surface_distance(mesh, centers)
    center_inside = _inside(mesh, centers)
    flagged = (center_distance < distance) & ~center_inside
    flagged = flagged.reshape(len(centers_u), len(centers_v))

    fine_u = _fine_axis(u, factor)
    fine_v = _fine_axis(v, factor)
    seen: set[tuple[int, int]] = set()
    nodes_local: list[tuple[float, float]] = []
    for iu in range(len(u) - 1):
        for iv in range(len(v) - 1):
            if not flagged[iu, iv]:
                continue
            for a in range(factor + 1):
                gu = iu * factor + a
                for b in range(factor + 1):
                    gv = iv * factor + b
                    if gu % factor == 0 and gv % factor == 0:
                        continue  # a base-grid node
                    if (gu, gv) in seen:
                        continue  # shared with an adjacent flagged cell
                    seen.add((gu, gv))
                    nodes_local.append((fine_u[gu], fine_v[gv]))
    if not nodes_local:
        return np.empty((0, 3)), 0, 0

    local = np.zeros((len(nodes_local), 3))
    local[:, :2] = np.asarray(nodes_local)
    candidates = grid.frame.to_reference(local)
    if cull:
        inside = _inside(mesh, candidates)
    else:
        inside = np.zeros(len(candidates), dtype=bool)
    if standoff > 0.0:
        near = (_surface_distance(mesh, candidates) < standoff) & ~inside
    else:
        near = np.zeros(len(candidates), dtype=bool)
    return candidates[~(inside | near)], int(inside.sum()), int(near.sum())
