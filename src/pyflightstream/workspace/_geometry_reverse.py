"""Identifying a lifting surface from an original IGES skin (needs the gmsh extra).

Pipeline role: the workspace row of the reverse step. A component of an IGES file (named on
its level, the 406 NAME index) is cut by planes normal to its span axis on the trimmed faces
with OpenCASCADE (Newton-corrected polylines, never bridging a missing surface); the cuts feed
the numerical stage of :mod:`pyflightstream.geometry._reverse`, which finds the clean band, the
planform between a root and the outermost clean cut and the CST sections. The root is the
plane crossing of the extended leading edge for a surface on a symmetry plane, the meeting of
the extended leading edge with a host surface for a surface on a body, or the span extent of
the original's own trimmed boundary curves for a surface open inside its host.

A planform is reported with ``accepted`` set only when a coarse and a fine pass agree within
the tolerances of the result (``convergence``); sections carry their own ``accepted`` against
their residual tolerance. Nothing is repaired silently: a station that is not one closed
airfoil contour is recorded with its reason and left out of the band.

gmsh ships with the optional ``gmsh`` extra; the functions refuse with the package's
missing-extra refusal, with the install command, when it is absent.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import brentq, minimize_scalar

from pyflightstream._errors import InputValueError
from pyflightstream.geometry.stages import (
    clean_band,
    closed_contour,
    contour_features,
    cosine,
    fit_section,
    leading_extension,
    reference_planform,
    refine_tip,
)
from pyflightstream.workspace._geometry_check import (
    edge_samples,
    edges_of,
    resolve_faces,
    sample_surfaces,
)
from pyflightstream.workspace._gmsh import gmsh_module, session

__all__ = ["LiftingIdentification", "identify_lifting_surface"]

_PURPOSE = "identifying a lifting surface from an original IGES skin"
#: Convergence tolerances of the coarse pass against the fine pass, by planform quantity.
CONVERGENCE_TOLERANCES = {
    "semi_span_m": 0.002,
    "root_chord_m": 0.0005,
    "tip_chord_m": 0.0005,
    "area_m2": 0.01,
    "mac_m": 0.0005,
    "incidence_deg": 0.01,
    "dihedral_deg": 0.01,
    "tip_twist_deg": 0.01,
}
#: The coarse pass: stations and cut-grid points per side.
COARSE = (81, 129)
_ROOTS = ("auto", "plane", "host", "boundary")
_CUTS = ("plain", "bridge_te", "mirror")


# --- cuts -------------------------------------------------------------------------------


def surface_grid(face, count=257):
    """Return the face, its parameter bounds and a cosine-spaced grid of surface points."""
    gmsh = gmsh_module(_PURPOSE)
    low, high = map(np.asarray, gmsh.model.getParametrizationBounds(2, face))
    u = low[0] + np.ptp([low[0], high[0]]) * cosine(count)
    v = low[1] + np.ptp([low[1], high[1]]) * cosine(count)
    uv = np.stack(np.meshgrid(u, v), axis=-1)
    xyz = np.asarray(gmsh.model.getValue(2, face, uv.ravel())).reshape(count, count, 3)
    return face, low, high, u, v, xyz


def boundary_intersections(face, normal, station):
    """Return the points where the trim edges of ``face`` cross the plane at ``station``."""
    gmsh = gmsh_module(_PURPOSE)
    points = []
    edges = {abs(t) for d, t in gmsh.model.getBoundary([(2, face)], oriented=False) if d == 1}
    for edge in edges:
        low, high = gmsh.model.getParametrizationBounds(1, edge)
        t = low[0] + (high[0] - low[0]) * cosine(257)
        p = np.asarray(gmsh.model.getValue(1, edge, t)).reshape(-1, 3)
        f = p @ normal - station

        def value(at, edge=edge):
            return np.asarray(gmsh.model.getValue(1, edge, [at])) @ normal - station

        for i in np.flatnonzero(f[:-1] * f[1:] < 0):
            root = brentq(value, t[i], t[i + 1], xtol=1e-13)
            points.append(np.asarray(gmsh.model.getValue(1, edge, [root])))
        points.extend(p[np.abs(f) < 1e-10])
    return points


def cut_grid(grid, normal, station, tolerance=1e-8):
    """Return the contiguous trimmed polylines of one face on a plane, never bridging a gap."""
    import contourpy

    gmsh = gmsh_module(_PURPOSE)
    face, low, high, u, v, xyz = grid
    normal = np.asarray(normal, float)
    heights = xyz @ normal
    if station < heights.min() or station > heights.max():
        return []
    generator = contourpy.contour_generator(x=u, y=v, z=heights)
    segments = []
    for q in generator.lines(station):
        for _ in range(12):
            p = np.asarray(gmsh.model.getValue(2, face, q.ravel())).reshape(-1, 3)
            error = p @ normal - station
            if np.max(np.abs(error)) < tolerance:
                break
            der = np.asarray(gmsh.model.getDerivative(2, face, q.ravel())).reshape(-1, 2, 3)
            grad = der @ normal
            step = error[:, None] * grad / np.maximum(np.sum(grad**2, axis=1)[:, None], 1e-30)
            q = np.clip(q - step, low, high)
        p = np.asarray(gmsh.model.getValue(2, face, q.ravel())).reshape(-1, 3)
        good = np.array([gmsh.model.isInside(2, face, uv, parametric=True) > 0 for uv in q])
        good &= np.abs(p @ normal - station) <= tolerance
        runs = np.split(np.arange(len(p)), np.flatnonzero(np.diff(good.astype(int))) + 1)
        segments.extend(p[r] for r in runs if len(r) >= 2 and good[r[0]])
    boundary = boundary_intersections(face, normal, station)
    if segments:
        for point in boundary:
            candidates = [
                (np.linalg.norm(line[k] - point), i, k)
                for i, line in enumerate(segments)
                for k in (0, -1)
            ]
            _, i, k = min(candidates)
            segments[i] = (
                np.vstack([point, segments[i]]) if k == 0 else np.vstack([segments[i], point])
            )
    elif boundary:
        segments = [np.asarray(boundary)]
    return segments


def cut_surfaces(grids, normal, station):
    """Return every polyline the faces give on a plane; a plane that meets none is refused."""
    segments = [line for grid in grids for line in cut_grid(grid, normal, station)]
    if not segments:
        raise InputValueError(f"section at {station}: no trimmed intersection")
    return segments


def bridged_cut(grids, span, station, limit=0.01):
    """Cut an original whose blunt trailing edge is an open slit, closing it with a segment."""
    segments = [np.asarray(s) for s in cut_surfaces(grids, span, station)]
    ends = [(i, k, s[k]) for i, s in enumerate(segments) for k in (0, -1)]
    loose = []
    for i, k, p in ends:
        partners = [np.linalg.norm(p - q) for j, m, q in ends if (j, m) != (i, k)]
        if min(partners) > 5e-5:
            loose.append(p)
    if len(loose) == 2 and np.linalg.norm(loose[0] - loose[1]) < limit:
        segments.append(np.array([loose[0], loose[1]]))
    return segments


def mirrored_cut(grids, span, station):
    """Cut a half-body original (one side of its symmetry plane) and add the reflection."""
    segments = cut_surfaces(grids, span, station)
    return segments + [np.asarray(line) * [1.0, -1.0, 1.0] for line in segments]


def host_intersection(curve, faces, bracket, tolerance=5e-5):
    """Find where a leading-edge curve meets a trimmed host face; the outermost meeting wins."""
    gmsh = gmsh_module(_PURPOSE)

    def closest(station, trimmed=False):
        p = curve(station)
        candidates = []
        for face in faces:
            xyz, uv = gmsh.model.getClosestPoint(2, face, p.tolist())
            if trimmed and not gmsh.model.isInside(2, face, uv, parametric=True):
                continue
            gap = float(np.linalg.norm(np.asarray(xyz) - p))
            candidates.append((gap, face, np.asarray(xyz)))
        if not candidates:
            return float("inf"), None, None
        return min(candidates, key=lambda row: row[0])

    stations = np.linspace(*bracket, 81)
    distances = np.array([closest(s)[0] for s in stations])
    minima = (
        np.flatnonzero((distances[1:-1] <= distances[:-2]) & (distances[1:-1] <= distances[2:])) + 1
    )
    candidates = []
    for i in minima:
        fit = minimize_scalar(
            lambda s: closest(s)[0] ** 2,
            bounds=(stations[i - 1], stations[i + 1]),
            method="bounded",
            options={"xatol": 1e-12},
        )
        gap, face, _ = closest(fit.x, trimmed=True)
        if gap <= tolerance:
            candidates.append(
                {
                    "station_m": float(fit.x),
                    "gap_m": gap,
                    "host_face": face,
                    "point_m": curve(fit.x).tolist(),
                }
            )
    if not candidates:
        raise InputValueError(
            f"the leading-edge extension does not meet a trimmed host within {tolerance} m; "
            f"sampled minimum {float(distances.min())} m"
        )
    return max(candidates, key=lambda row: row["station_m"])


def boundary_extent(faces, span, count=400):
    """Return the span-station extent of the original's own trimmed boundary curves."""
    s = np.concatenate([edge_samples(e, count) @ span for e in edges_of(faces)])
    return float(s.min()), float(s.max())


# --- the driver -------------------------------------------------------------------------


def scan(grids, samples, span, count, cutter):
    """Cut the component at ``count`` cosine-spaced stations; return stations, features, reasons."""
    bounds = samples @ span
    lo, hi = float(bounds.min()), float(bounds.max())
    inset = (hi - lo) * 1e-7
    stations = lo + inset + (hi - lo - 2 * inset) * cosine(count)
    features, failures = [], []
    for s in stations:
        try:
            contour = closed_contour(cutter(grids, span, s))
            features.append(contour_features(contour, span))
            failures.append(None)
        except ValueError as error:
            features.append(None)
            failures.append(str(error))
    return stations, features, failures


def _span_direction(samples, span_axis):
    """Return the unit span axis: the one given, or y or z (the larger extent), toward the mass."""
    if span_axis is not None:
        axis = np.asarray(span_axis, float)
        if axis.shape != (3,) or not np.all(np.isfinite(axis)) or np.linalg.norm(axis) == 0:
            raise InputValueError("span_axis: three finite numbers, not all zero, required")
        return axis / np.linalg.norm(axis)
    extent = np.ptp(samples, axis=0)
    axis = np.zeros(3)
    index = 1 if extent[1] >= extent[2] else 2
    axis[index] = 1.0 if samples[:, index].mean() >= 0 else -1.0
    return axis


@dataclass(frozen=True)
class LiftingIdentification:
    """The identified planform, sections and evidence of one lifting surface (metres, degrees).

    ``planform`` is the reference planform of ``geometry._reverse.reference_planform``;
    ``sections`` are the root and tip CST fits and ``midspan`` the extra measured section.
    ``accepted`` is true when the coarse and fine passes agree and every section met its
    tolerance.
    """

    component: str
    source: str
    seed: str
    planform: dict[str, Any]
    sections: list[dict[str, Any]]
    midspan: dict[str, Any]
    accepted: bool
    root_kind: str
    clean_cuts: int
    convergence: dict[str, Any] | None = None
    scan: dict[str, Any] = field(default_factory=dict)

    def to_component(self) -> dict[str, Any]:
        """Return a ``lifting_surface`` component of a configuration that rebuilds this planform.

        The configuration describes sections by NACA designation, so the seed designation
        stands for the section shape and the measured CST fits stay in ``sections``. The
        placement carries the leading edge at the root. A span axis tilted 89 degrees or more
        from the y axis (a fin) is refused: place such a surface by rotation instead.
        """
        p = self.planform
        dihedral = p["dihedral_deg"]
        if abs(dihedral) >= 89.0:
            raise InputValueError(
                f"to_component: dihedral {dihedral:.3g} degrees is outside the configuration's "
                "range of +-89; describe this surface with a placement rotation"
            )
        tilt = math.cos(math.radians(dihedral))
        semi_y = p["semi_span_m"] * tilt
        sweep_x = math.tan(math.radians(p["sweep_le_deg"])) * p["semi_span_m"]
        return {
            "type": "lifting_surface",
            "planform": {
                "span": 2.0 * semi_y,
                "root_chord": p["root_chord_m"],
                "tip_chord": p["tip_chord_m"],
                "sweep": math.degrees(math.atan2(sweep_x, semi_y)),
                "dihedral": dihedral,
                "incidence": p["incidence_deg"],
                "tip_twist": p["tip_twist_deg"],
            },
            "sections": {"airfoils": [self.seed]},
            "placement": {"translation": list(p["reference_plane"]["origin_m"])},
        }

    def to_dict(self) -> dict[str, Any]:
        """Return the result as plain data, ready for JSON."""
        return {
            "component": self.component,
            "source": self.source,
            "seed": self.seed,
            "accepted": self.accepted,
            "root_kind": self.root_kind,
            "clean_cuts": self.clean_cuts,
            "planform": self.planform,
            "sections": self.sections,
            "midspan": self.midspan,
            "convergence": self.convergence,
            "scan": self.scan,
        }


def _identify(grids, samples, hosts, spec, count):
    """One pass: scan, band, planform. Returns the planform, band and scan diagnostics."""
    cutter = {"plain": cut_surfaces, "bridge_te": bridged_cut, "mirror": mirrored_cut}[spec["cut"]]
    span = spec["span"].copy()
    for iteration in range(2):
        stations, features, failures = scan(
            grids, samples, span, min(count, 81) if iteration == 0 else count, cutter
        )
        band, _, _ = clean_band(stations, features)
        if iteration == 0:
            le = np.array([features[i]["le"] for i in band])[:, 1:]
            slope = np.polyfit(stations[band], le, 1)[0]
            candidate = np.r_[0.0, slope] / np.linalg.norm(slope)
            if np.linalg.norm(candidate - span) < 1e-6:
                break
            span = candidate

    def evaluate(s):
        return contour_features(closed_contour(cutter(grids, span, s)), span)

    stations, features, band, bracket = refine_tip(stations, features, band, evaluate)
    mirrored = spec["mirrored"]
    root = spec["root"]
    if root == "boundary":
        lo, hi = spec["extent"]
        result = reference_planform(
            stations, features, band, span, root_station=lo, tip_station=hi,
            hold_incidence=True, mirrored=mirrored,
        )  # fmt: skip
        result["root_kind"] = "minimum span station of the original face boundary curves"
    elif root == "plane":
        axis = int(np.argmax(np.abs(span)))
        result = reference_planform(
            stations, features, band, span,
            boundary=lambda p: p[axis], root_bracket=(stations[0] - 1.0, stations[band[0]] + 1e-4),
            mirrored=mirrored,
        )  # fmt: skip
        result["root_kind"] = f"symmetry plane {'xyz'[axis]} = 0"
        lowest = float((samples @ span).min()) - 1e-6
        if lowest < result["root_station_m"] - 1e-4:  # a tilted span axis reaches below the plane
            result = reference_planform(
                stations, features, band, span, root_station=lowest, mirrored=mirrored
            )
            result["root_kind"] = (
                "symmetry plane, root station lowered to the first original sample"
            )
    else:
        curve = leading_extension(stations, features, band)
        try:
            hit = host_intersection(
                curve, hosts, (float(stations[0]) - 1.5, float(stations[band[0]])),
                tolerance=spec["host_tolerance"],
            )  # fmt: skip
            result = reference_planform(
                stations, features, band, span, root_station=hit["station_m"], mirrored=mirrored
            )
            result["root_kind"] = "extended leading edge meets host"
            result["root_host_gap_m"] = hit["gap_m"]
        except InputValueError as error:
            lowest = float((samples @ span).min())
            result = reference_planform(
                stations, features, band, span, root_station=lowest, mirrored=mirrored
            )
            result["root_kind"] = "first original sample along the span axis (no host meeting)"
            result["root_host_note"] = str(error)
    result["clean_cut_count"] = len(band)
    diagnostics = {
        "station_m": stations.tolist(),
        "clean_indices": band.tolist(),
        "tip_bracket_m": bracket,
        "rejected": {
            f"{s:.6g}": reason for s, reason in zip(stations, failures, strict=False) if reason
        },
    }
    return result, band, features, stations, span, diagnostics


def _convergence(coarse, fine):
    checks = {
        key: {
            "coarse": coarse[key],
            "fine": fine[key],
            "absolute_difference": abs(fine[key] - coarse[key]),
            "tolerance": tolerance,
            "passed": abs(fine[key] - coarse[key]) <= tolerance,
        }
        for key, tolerance in CONVERGENCE_TOLERANCES.items()
    }
    return {"accepted": all(c["passed"] for c in checks.values()), "checks": checks}


def _resolve_hosts(hosts, source):
    """Return the host face tags: names of components of ``source`` or ``path#name`` entries."""
    tags: list[int] = []
    for host in hosts:
        entry = host if "#" in str(host) else f"{source}#{host}"
        tags += resolve_faces(entry)
    return tags


def identify_lifting_surface(
    source: str | Path,
    component: str,
    *,
    hosts: Sequence[str] = (),
    root: str = "auto",
    mirrored: bool | None = None,
    cut: str = "plain",
    seed: str = "NACA0012",
    span_axis: Sequence[float] | None = None,
    stations: int = 161,
    grid: int = 257,
    section_tolerance_mm: float | None = None,
    section_degree: int = 5,
    section_max_degree: int = 20,
    host_tolerance: float = 5e-5,
    converge: bool = True,
) -> LiftingIdentification:
    """Identify one lifting-surface component of an IGES file from its trimmed skin.

    Parameters
    ----------
    source : str or Path
        The IGES file, read only. Its faces are named by the NAME of their level.
    component : str
        The component to identify.
    hosts : sequence of str, optional
        Components the surface sits on, as names in ``source`` or ``path#name``. Given, the
        root is where the extended leading edge meets them (``root="auto"``).
    root : {"auto", "plane", "host", "boundary"}
        ``plane``: the symmetry plane through the origin normal to the span axis. ``host``:
        the host surface. ``boundary``: the span extent of the original's own boundary curves
        (a surface open inside its host). ``auto``: ``host`` when ``hosts`` is given, else
        ``plane``.
    mirrored : bool, optional
        Whether the surface has a mirror image across its root (doubles span and area);
        defaults to true for a plane root and false otherwise.
    cut : {"plain", "bridge_te", "mirror"}
        ``bridge_te`` closes an open blunt trailing-edge slit; ``mirror`` adds the reflection
        of a half-body original.
    seed : str
        The NACA designation the section fit starts from.
    span_axis : sequence of float, optional
        The first estimate of the span axis; the larger of y and z extent when omitted.
    stations, grid : int
        Stations of the fine pass and cut-grid points per side of each face.
    section_tolerance_mm : float, optional
        Section residual tolerance; the larger of 0.5 mm and 0.1 percent of the chord when
        omitted.
    section_degree, section_max_degree : int
        The CST degree a section fit starts at and the highest it may rise to.
    host_tolerance : float
        The largest gap, in metres, at which the extended leading edge counts as meeting a host.
    converge : bool
        Run a coarse pass as well and require the planforms to agree for ``accepted``.

    Returns
    -------
    LiftingIdentification

    Raises
    ------
    MissingExtraError
        gmsh is not installed.
    InputValueError
        An argument is refused, the component is unknown, or no clean band exists.
    """
    if root not in _ROOTS:
        raise InputValueError(f"root: one of {list(_ROOTS)} required, got {root!r}")
    if cut not in _CUTS:
        raise InputValueError(f"cut: one of {list(_CUTS)} required, got {cut!r}")
    if stations < 20 or grid < 33:
        raise InputValueError("stations, grid: at least 20 stations and a 33-point grid required")
    if root == "host" and not hosts:
        raise InputValueError("root: 'host' needs hosts")
    gmsh_module(_PURPOSE)
    resolved = ("host" if hosts else "plane") if root == "auto" else root
    with session(_PURPOSE) as gmsh:
        gmsh.model.add("identify")
        faces = resolve_faces(f"{source}#{component}")
        host_faces = _resolve_hosts(hosts, source) if resolved == "host" or hosts else []
        samples, _ = sample_surfaces(faces, 65, 257)
        axis = _span_direction(samples, span_axis)
        spec = {
            "span": axis,
            "root": resolved,
            "cut": cut,
            "mirrored": resolved == "plane" if mirrored is None else mirrored,
            "host_tolerance": host_tolerance,
        }
        if resolved == "boundary":
            spec["extent"] = boundary_extent(faces, axis)
        grids = [surface_grid(t, grid) for t in faces]
        convergence = None
        if converge:
            small = [surface_grid(t, COARSE[1]) for t in faces]
            coarse = _identify(small, samples, host_faces, spec, min(stations, COARSE[0]))[0]
        planform, band, features, stations_m, span, diagnostics = _identify(
            grids, samples, host_faces, spec, stations
        )
        if converge:
            convergence = _convergence(coarse, planform)
        chosen = [int(band[0]), int(band[len(band) // 2]), int(band[-1])]
        fits = []
        for role, index in zip(("root", "midspan", "tip"), chosen, strict=True):
            fit = fit_section(
                features[index]["contour"], span, seed,
                degree=section_degree, max_degree=max(section_degree, section_max_degree),
                tolerance_m=None if section_tolerance_mm is None else section_tolerance_mm / 1000,
            )  # fmt: skip
            fit["role"], fit["station_m"] = role, float(stations_m[index])
            fit["eta"] = (fit["station_m"] - planform["root_station_m"]) / planform["semi_span_m"]
            fits.append(fit)
    accepted = all(f["accepted"] for f in fits) and (convergence is None or convergence["accepted"])
    return LiftingIdentification(
        component=component,
        source=Path(source).name,
        seed=seed,
        planform=planform,
        sections=[fits[0], fits[2]],
        midspan=fits[1],
        accepted=accepted,
        root_kind=planform["root_kind"],
        clean_cuts=len(band),
        convergence=convergence,
        scan={**diagnostics, "stations": stations, "grid": grid},
    )
