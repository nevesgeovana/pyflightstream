"""Checking a rebuilt surface against an original: sampled forward and restricted reverse distance.

Pipeline role: the workspace row of the geometry check. Both skins are sampled on
their trimmed faces and edges and each sample is measured to the other skin with
OpenCASCADE witnesses (seeded Gauss-Newton on faces, curve projection on edges,
conservative bounding-box pruning). Forward is original to rebuilt everywhere;
reverse is rebuilt to original, restricted to samples whose nearest original
witness is not on a trim edge, so a rebuilt surface that extends past the original
trim is not penalized. Empty reverse coverage is a rejection, never a vacuous
acceptance. The limit is a named profile of
:data:`pyflightstream.geometry.component.DEVIATION_PROFILES` (``study_default``:
the larger of 0.5 mm and 0.1 percent of the local chord). Distances are sampled
upper bounds, not continuous Hausdorff distances.

gmsh ships with the optional ``gmsh`` extra; the functions refuse with the
package's missing-extra refusal, with the install command, when it is absent.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
from scipy.spatial import cKDTree

from pyflightstream._errors import InputValueError
from pyflightstream._lengths import METRES_PER_UNIT
from pyflightstream.geometry.component import DEVIATION_PROFILES
from pyflightstream.workspace._gmsh import gmsh_module, import_named

__all__ = ["check_against_original", "local_limits"]

_PURPOSE = "checking a rebuilt surface against an original"


def import_component(path, name=None):
    """Import an IGES file at metre scale and return the faces of one component, or all of them."""
    gmsh = gmsh_module(_PURPOSE)
    named = import_named(gmsh, [path])
    factor = float(METRES_PER_UNIT[named.unit])
    if factor != 1.0:
        gmsh.model.occ.dilate([(2, t) for t in named.faces], 0, 0, 0, factor, factor, factor)
        gmsh.model.occ.synchronize()
    selected = [
        tag
        for tag, label in zip(named.faces, named.names, strict=True)
        if name is None or label == name
    ]
    if not selected:
        raise InputValueError(f"IGES import: no faces named {name}")
    return selected


def surface_tags(surfaces):
    """Return the OCC surface tags of ``surfaces``, given as tags or ``(2, tag)`` pairs."""
    tags = [
        int(item[1])
        if isinstance(item, (tuple, list)) and len(item) == 2 and item[0] == 2
        else int(item)
        for item in surfaces
    ]
    if not tags or len(set(tags)) != len(tags):
        raise InputValueError("component_surfaces: nonempty unique OCC surface tags required")
    return tags


def resolve_faces(value, name=None):
    """Return face tags for an IGES path (optionally ``path#component``) or a list of tags."""
    if isinstance(value, (str, Path)):
        path, separator, component = str(value).partition("#")
        return import_component(path, component if separator else name)
    return surface_tags(value)


def edges_of(faces):
    gmsh = gmsh_module(_PURPOSE)
    return sorted(
        {
            abs(tag)
            for face in faces
            for dim, tag in gmsh.model.getBoundary([(2, face)], combined=False, oriented=False)
            if dim == 1
        }
    )


def face_samples(face, count):
    gmsh = gmsh_module(_PURPOSE)
    low, high = map(np.asarray, gmsh.model.getParametrizationBounds(2, face))
    axis = (np.arange(count) + 0.5) / count
    uv = np.stack(
        np.meshgrid(
            low[0] + axis * (high[0] - low[0]), low[1] + axis * (high[1] - low[1]), indexing="ij"
        ),
        axis=-1,
    ).reshape(-1, 2)
    inside = np.array([bool(gmsh.model.isInside(2, face, point, parametric=True)) for point in uv])
    uv = uv[inside]
    xyz = (
        np.asarray(gmsh.model.getValue(2, face, uv.ravel())).reshape(-1, 3)
        if len(uv)
        else np.empty((0, 3))
    )
    return xyz, uv, (low, high)


def edge_samples(edge, count):
    gmsh = gmsh_module(_PURPOSE)
    low, high = gmsh.model.getParametrizationBounds(1, edge)
    try:
        return np.asarray(
            gmsh.model.getValue(1, edge, np.linspace(low[0], high[0], count))
        ).reshape(-1, 3)
    except Exception:
        vertices = gmsh.model.getBoundary([(1, edge)], oriented=False)
        return np.asarray([gmsh.model.getValue(0, abs(v), []) for _, v in vertices]).reshape(-1, 3)


def sample_surfaces(faces, count, edge_count):
    points, coverage = [], []
    for face in faces:
        xyz, _, _ = face_samples(face, count)
        used = count
        while not len(xyz) and used < 257:
            used = used * 2 + 1
            xyz, _, _ = face_samples(face, used)
        if not len(xyz):
            raise InputValueError(f"sampling: face {face} has no sampled trimmed interior")
        points.append(xyz)
        coverage.append(dict(face=int(face), interior_samples=len(xyz), lattice=used))
    for edge in edges_of(faces):
        points.append(edge_samples(edge, edge_count))
    result = np.concatenate(points)
    if not np.all(np.isfinite(result)):
        raise InputValueError("sampling: nonfinite coordinates")
    return result, coverage


def box_lower_bound(points, dim, tag):
    gmsh = gmsh_module(_PURPOSE)
    box = np.asarray(gmsh.model.getBoundingBox(dim, tag))
    return np.linalg.norm(np.maximum(np.maximum(box[:3] - points, points - box[3:]), 0), axis=1)


def edge_distance(points, edge):
    """Recover curve parameters from XYZ; batched OCC returned parameters are unreliable."""
    gmsh = gmsh_module(_PURPOSE)
    low, high = gmsh.model.getParametrizationBounds(1, edge)
    try:
        xyz, _ = gmsh.model.getClosestPoint(1, edge, points.ravel())
        parameter = gmsh.model.getParametrization(1, edge, xyz)
        projected = np.asarray(
            gmsh.model.getValue(1, edge, np.clip(parameter, low[0], high[0]))
        ).reshape(-1, 3)
        distance = np.linalg.norm(points - projected, axis=1)
        endpoints = edge_samples(edge, 2)
        return np.minimum(distance, cKDTree(endpoints).query(points)[0])
    except Exception:
        vertices = gmsh.model.getBoundary([(1, edge)], oriented=False)
        if not vertices:
            raise InputValueError(
                f"projection: edge {edge} has neither curve nor vertex witness"
            ) from None
        xyz = np.asarray([gmsh.model.getValue(0, abs(v), []) for _, v in vertices])
        return cKDTree(xyz).query(points)[0]


def surface_distance(points, face, seed_xyz, seed_uv, bounds):
    gmsh = gmsh_module(_PURPOSE)
    low, high = bounds
    xyz, uv = gmsh.model.getClosestPoint(2, face, points.ravel())
    uv = np.asarray(uv).reshape(-1, 2)
    xyz = np.asarray(xyz).reshape(-1, 3)
    valid = np.array([bool(gmsh.model.isInside(2, face, p, parametric=True)) for p in uv])
    distance = np.where(valid, np.linalg.norm(points - xyz, axis=1), np.inf)
    uv = seed_uv[cKDTree(seed_xyz).query(points)[1]].copy()
    moving = np.arange(len(points))
    for _ in range(20):
        if not len(moving):
            break
        here = uv[moving]
        xyz = np.asarray(gmsh.model.getValue(2, face, here.ravel())).reshape(-1, 3)
        derivative = np.asarray(gmsh.model.getDerivative(2, face, here.ravel())).reshape(-1, 2, 3)
        residual = xyz - points[moving]
        a = np.sum(derivative[:, 0] ** 2, axis=1)
        b = np.sum(derivative[:, 0] * derivative[:, 1], axis=1)
        c = np.sum(derivative[:, 1] ** 2, axis=1)
        d = np.sum(derivative[:, 0] * residual, axis=1)
        e = np.sum(derivative[:, 1] * residual, axis=1)
        determinant = np.maximum(a * c - b * b, 1e-30)
        delta = np.column_stack(((c * d - b * e) / determinant, (a * e - b * d) / determinant))
        updated = np.clip(
            here - np.clip(delta, -0.15 * (high - low), 0.15 * (high - low)), low, high
        )
        uv[moving] = updated
        moving = moving[np.max(abs(updated - here) / np.maximum(high - low, 1e-30), axis=1) > 1e-11]
    xyz = np.asarray(gmsh.model.getValue(2, face, uv.ravel())).reshape(-1, 3)
    valid = np.array([bool(gmsh.model.isInside(2, face, p, parametric=True)) for p in uv])
    return np.minimum(distance, np.where(valid, np.linalg.norm(points - xyz, axis=1), np.inf))


def nearest(points, faces, boundary_tolerance=1e-8):
    """Reuse SMIGEOM4's bounded candidate selection and seeded projection algorithm."""
    gmsh = gmsh_module(_PURPOSE)
    seeds = {}
    for face in faces:
        xyz, uv, bounds = face_samples(face, 17)
        if not len(xyz):
            xyz = np.concatenate([edge_samples(e, 17) for e in edges_of([face])])
            uv = np.asarray(gmsh.model.getParametrization(2, face, xyz.ravel())).reshape(-1, 2)
        seeds[face] = xyz, uv, bounds
    best = cKDTree(np.concatenate([entry[0] for entry in seeds.values()])).query(points)[0]
    for face, seed in seeds.items():
        ids = np.flatnonzero(box_lower_bound(points, 2, face) <= best + boundary_tolerance)
        if len(ids):
            best[ids] = np.minimum(best[ids], surface_distance(points[ids], face, *seed))
    boundary = np.full(len(points), np.inf)
    for edge in edges_of(faces):
        ids = np.flatnonzero(box_lower_bound(points, 1, edge) <= best + boundary_tolerance)
        if len(ids):
            boundary[ids] = np.minimum(boundary[ids], edge_distance(points[ids], edge))
    distance = np.minimum(best, boundary)
    if not np.all(np.isfinite(distance)):
        raise InputValueError("projection: no finite valid witness")
    return distance, best < boundary - boundary_tolerance


def local_limits(points, limits, profile="study_default"):
    """Return the allowed deviation, in metres, at each of ``points`` under a named profile.

    The local chord comes from ``limits``: ``local_chord`` (a function of the points),
    ``stations_m`` with ``chords_m`` along ``axis`` (default y), or one ``chord_m``.
    """
    constants = _profile(profile)
    if callable(limits.get("local_chord")):
        chord = np.asarray(limits["local_chord"](points), float)
    elif "stations_m" in limits:
        stations = np.asarray(limits["stations_m"], float)
        chords = np.asarray(limits["chords_m"], float)
        if len(stations) < 2 or len(stations) != len(chords) or np.any(np.diff(stations) <= 0):
            raise InputValueError("limits: increasing stations and matching chords required")
        chord = np.interp(points[:, limits.get("axis", 1)], stations, chords)
    elif "chord_m" in limits:
        chord = np.full(len(points), limits["chord_m"])
    else:
        raise InputValueError(
            "limits: give chord_m, stations_m with chords_m, or a local_chord function"
        )
    chord = np.broadcast_to(chord, (len(points),))
    if np.any(~np.isfinite(chord)) or np.any(chord <= 0):
        raise InputValueError("limits: positive finite local chord required")
    return np.maximum(constants["floor_mm"] / 1000, constants["local_fraction"] * chord)


def _profile(profile):
    try:
        return DEVIATION_PROFILES[profile]
    except KeyError:
        raise InputValueError(
            f"deviation profile {profile!r}: unknown; available: {sorted(DEVIATION_PROFILES)}"
        ) from None


def statistics(points, distance, limits, profile="study_default"):
    """Return the maximum, mean and exceedance count of ``distance`` against the local limit."""
    if not len(distance):
        return {
            "samples": 0,
            "max_m": None,
            "mean_m": None,
            "max_mm": None,
            "mean_mm": None,
            "exceedance_count": 0,
            "sampled_pass": False,
        }
    tolerance = local_limits(points, limits, profile)
    ratio = distance / tolerance
    worst = int(np.argmax(distance))
    return {
        "samples": len(distance),
        "max_m": float(distance[worst]),
        "mean_m": float(distance.mean()),
        "max_mm": float(distance[worst] * 1000),
        "mean_mm": float(distance.mean() * 1000),
        "exceedance_count": int(np.count_nonzero(ratio > 1)),
        "maximum_distance_to_limit_ratio": float(ratio.max()),
        "worst_point_m": points[worst].tolist(),
        "local_limit_at_worst_m": float(tolerance[worst]),
        "sampled_pass": bool(np.all(ratio <= 1)),
    }


def _region_results(limits, profile, old, new, forward, *, reverse, interior):
    regions = {}
    for label, mask in (limits.get("regions") or {}).items():
        fm, rm = np.asarray(mask(old), bool), np.asarray(mask(new[interior]), bool)
        fr = statistics(old[fm], forward[fm], limits, profile)
        rr = statistics(new[interior][rm], reverse[interior][rm], limits, profile)
        regions[label] = {
            "forward": fr,
            "restricted_reverse": rr,
            "accepted": bool(fr["sampled_pass"] and (rr["sampled_pass"] or rr["samples"] == 0)),
        }
    return regions


def check_against_original(
    rebuilt: Any, original: Any, limits: Mapping[str, Any], *, profile: str = "study_default"
) -> dict[str, Any]:
    """Compare a rebuilt surface with an original: forward and restricted reverse distance.

    ``rebuilt`` and ``original`` are OCC surface tags in the active model or IGES paths,
    optionally ``path#component``. Distances and local chord inputs are metres. Reverse
    samples whose nearest original witness lies on an original face trim edge are excluded
    explicitly. Empty reverse coverage is a rejection, never a vacuous acceptance.

    Parameters
    ----------
    limits : mapping
        The local chord (see :func:`local_limits`), and optionally ``component``,
        ``exclude_faces``, ``forward_count``, ``reverse_count``, ``edge_count``, ``fold_y``
        and ``regions`` (a mapping of label to a mask of points).
    rebuilt, original
        The two surfaces, as described above.
    profile : str
        Named deviation profile; an unknown name is refused with the available names.

    Returns
    -------
    dict
        ``accepted`` (both directions passed), the ``forward``, ``restricted_reverse`` and
        ``unrestricted_reverse`` statistics, the ``regions`` results, the excluded original
        faces and boundary samples, the sample coverage of each surface, the ``profile`` and
        its ``tolerance_rule``, and the ``method`` (sampled upper bounds, not continuous
        Hausdorff distances).

    Raises
    ------
    InputValueError
        For an unknown profile, limits that name no chord, or a surface that cannot be resolved.
    pyflightstream.extras.MissingExtraError
        When the optional gmsh extra is not installed.
    """
    constants = _profile(profile)
    gmsh = gmsh_module(_PURPOSE)
    own_session = not gmsh.isInitialized()
    if own_session:
        gmsh.initialize(readConfigFiles=False)
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("geometry-check")
    try:
        new_faces = resolve_faces(rebuilt, limits.get("component"))
        old_faces = resolve_faces(original, limits.get("component"))
        excluded = [
            {"index": int(i), "tag": int(old_faces[i])} for i in (limits.get("exclude_faces") or [])
        ]
        drop = {e["index"] for e in excluded}
        old_faces = [f for i, f in enumerate(old_faces) if i not in drop]
        edge_count = limits.get("edge_count", 101)
        old, old_coverage = sample_surfaces(old_faces, limits.get("forward_count", 45), edge_count)
        new, new_coverage = sample_surfaces(new_faces, limits.get("reverse_count", 31), edge_count)
        if limits.get(
            "fold_y"
        ):  # half-body original: the rebuilt mirror half folds onto the modelled side
            new = np.c_[new[:, 0], -np.abs(new[:, 1]), new[:, 2]]
        forward, _ = nearest(old, new_faces)
        reverse, interior = nearest(new, old_faces)
        f = statistics(old, forward, limits, profile)
        r = statistics(new[interior], reverse[interior], limits, profile)
        return {
            "accepted": bool(f["sampled_pass"] and r["sampled_pass"]),
            "regions": _region_results(
                limits, profile, old, new, forward, reverse=reverse, interior=interior
            ),
            "forward": f,
            "restricted_reverse": r,
            "unrestricted_reverse": statistics(new, reverse, limits, profile),
            "excluded_original_faces": excluded,
            "reverse_excluded_boundary_samples": int(np.count_nonzero(~interior)),
            "reverse_included_samples": int(np.count_nonzero(interior)),
            "source_coverage": old_coverage,
            "rebuilt_coverage": new_coverage,
            "profile": profile,
            "tolerance_rule": (
                f"max({constants['floor_mm']} mm, {constants['local_fraction']} times local chord)"
            ),
            "boundary_tolerance_m": 1e-8,
            "method": (
                "Dense trimmed UV interiors and edges; valid OCC and seeded Gauss-Newton surface "
                "witnesses, curve witnesses and conservative face-box pruning. Sampled upper "
                "bounds, not continuous Hausdorff distances."
            ),
        }
    finally:
        if own_session:
            gmsh.finalize()
