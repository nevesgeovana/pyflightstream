"""Read blade-local strips from labelled saved geometry and surface exports.

Pipeline role: geometric and unit adapter for the rotor section numerical
core. Boundary labels identify blades; azimuth numbering is never assumed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from pyflightstream._fsm import boundary_vertices, saved_mesh_coordinate_unit
from pyflightstream._lengths import scale
from pyflightstream.farfield.rotor_sections import SectionLoads
from pyflightstream.results.surface import read_vtk_surface

__all__ = ["blade_surface_strips"]


def blade_surface_strips(
    surface_path: Path,
    saved_path: Path,
    families: list[str],
    lines: list[np.ndarray],
    *,
    hub: np.ndarray,
    axis: np.ndarray,
    moment_point: np.ndarray,
    per_m: float,
    rho: float,
    reference_speed: float,
    thrust_sign: float,
    chord_fraction: float,
) -> tuple[dict[str, SectionLoads], dict[str, np.ndarray], np.ndarray]:
    """Re-cut blade surface loads into radial strips on the wake's radii.

    Parameters
    ----------
    surface_path, saved_path : pathlib.Path
        Matching surface export and saved simulation containing blade labels.
    families : list of str
        The selected rotor's modelled blade families.
    lines : list of numpy.ndarray
        Selected rotor wake lines in geometry metres, newest node first.
    hub, axis, moment_point : numpy.ndarray
        Geometry-metre origins and unit shaft direction.
    per_m : float
        Native surface length units per metre.
    rho, reference_speed : float
        Density in kg/m^3 and reference velocity in m/s for Cp_reference.
    thrust_sign : float
        Sign of the measured blade axial load, resolving polygon winding.
    chord_fraction : float
        Chord fraction for induction evaluation and filament attachment.

    Returns
    -------
    tuple
        Strips by blade, wake indices by blade, and chord attachment per line.
        The VTK friction coefficient uses local dynamic pressure.
    """
    vertices = boundary_vertices(saved_path)
    unit = saved_mesh_coordinate_unit(saved_path)
    factor = scale(unit, "METER") if unit else None
    if not vertices or factor is None:
        raise ValueError("rotor sections need labelled saved blade geometry with known units")
    owned: dict[str, list] = {name: [] for name in families}
    for label, boundary_points in vertices.items():
        for name in families:
            if label.casefold() == name.casefold():
                owned[name].extend(boundary_points)
    if any(not value for value in owned.values()):
        raise ValueError("saved geometry does not identify every selected blade family")
    geometry = {name: np.asarray(value) * factor for name, value in owned.items()}
    surface = read_vtk_surface(surface_path)
    points = surface.points / per_m
    all_vertices = np.concatenate(list(geometry.values()))
    tree = cKDTree(all_vertices)
    # Only blade-near nodes vote; the surface may also contain a wing or body.
    distances = [tree.query(points + shift)[0] for shift in (np.zeros(3), moment_point)]
    score = [float(np.sort(d)[: len(all_vertices)].mean()) for d in distances]
    points = points + (moment_point if score[1] < score[0] else 0.0)
    tolerance = max(float(np.ptp(all_vertices, axis=0).max()) * 1e-5, 1e-8)
    polygons = [
        surface.connectivity[surface.offsets[i] : surface.offsets[i + 1]]
        for i in range(surface.n_cells)
    ]
    centers = np.array([points[poly].mean(axis=0) for poly in polygons])
    normals = np.array(
        [
            0.5 * np.cross(points[poly], np.roll(points[poly], -1, axis=0)).sum(axis=0)
            for poly in polygons
        ]
    )
    data = surface.cell_data
    required = ("Cp_reference", "skin_friction_coeff.", "Vx", "Vy", "Vz")
    if any(key not in data for key in required):
        raise ValueError("rotor sections need Cp_reference, skin_friction_coeff., Vx, Vy and Vz")
    velocity = np.column_stack([data[key] for key in ("Vx", "Vy", "Vz")])
    starts = np.array([line[0] for line in lines])
    distances_to_blades = np.array([cKDTree(geometry[name]).query(starts)[0] for name in families])
    nearest = distances_to_blades.argmin(axis=0)
    # Periodic exports may include images absent from the saved modelled
    # sector. Only the labelled sector enters the force reduction; its wake
    # is expanded by the explicit periodic copy count in the product adapter.
    nearest[distances_to_blades.min(axis=0) > tolerance * 100] = -1
    strips, groups = {}, {}
    attachment = np.zeros_like(starts)
    for index, name in enumerate(families):
        on_blade = cKDTree(geometry[name]).query(points)[0] <= tolerance
        faces = np.array([i for i, poly in enumerate(polygons) if np.all(on_blade[poly])])
        group = np.flatnonzero(nearest == index)
        if len(faces) == 0 or len(group) < 2:
            raise ValueError(
                f"blade {name} needs matching surface faces and at least two wake lines"
            )
        blade, ordered, legs = _cut(
            points,
            polygons,
            centers=centers[faces],
            normals=normals[faces],
            velocity=velocity[faces],
            cp=data["Cp_reference"][faces],
            cf=data["skin_friction_coeff."][faces],
            faces=faces,
            vertices=geometry[name],
            starts=starts,
            group=group,
            hub=hub,
            axis=axis,
            rho=rho,
            reference_speed=reference_speed,
            thrust_sign=thrust_sign,
            chord_fraction=chord_fraction,
        )
        strips[name], groups[name], attachment[ordered] = blade, ordered, legs
    return strips, groups, attachment


def _cut(
    points,
    polygons,
    *,
    centers,
    normals,
    velocity,
    cp,
    cf,
    faces,
    vertices,
    starts,
    group,
    hub,
    axis,
    rho,
    reference_speed,
    thrust_sign,
    chord_fraction,
):
    rel = vertices - hub
    across = rel - (rel @ axis)[:, None] * axis
    _, _, vh = np.linalg.svd(across - across.mean(axis=0), full_matrices=False)
    radial = vh[0]
    if radial @ across.mean(axis=0) < 0:
        radial = -radial
    radial -= (radial @ axis) * axis
    radial /= np.linalg.norm(radial)
    line_radius = np.linalg.norm(
        starts[group] - hub - ((starts[group] - hub) @ axis)[:, None] * axis, axis=1
    )
    order = np.argsort(line_radius)
    group, line_radius = group[order], line_radius[order]
    root = float(np.min(rel @ radial))
    edges = np.concatenate(([root], line_radius))
    if np.any(np.diff(edges) <= 0):
        raise ValueError(
            "blade root and wake radii must increase; use matching noncollapsed exports"
        )
    width, radius = np.diff(edges), (edges[:-1] + edges[1:]) / 2
    bin_index = np.clip(np.searchsorted(edges, (centers - hub) @ radial) - 1, 0, len(width) - 1)
    qref = 0.5 * rho * reference_speed**2
    pressure = -qref * cp[:, None] * normals
    if pressure.sum(axis=0) @ axis * thrust_sign < 0:
        pressure = -pressure
        normals = -normals
    speed = np.linalg.norm(velocity, axis=1)
    friction = 0.5 * rho * (speed * cf * np.linalg.norm(normals, axis=1))[:, None] * velocity
    force_strip, friction_strip = np.zeros((len(width), 3)), np.zeros((len(width), 3))
    np.add.at(force_strip, bin_index, pressure + friction)
    np.add.at(friction_strip, bin_index, friction)
    moments = np.zeros(len(width))
    np.add.at(moments, bin_index, np.cross(centers - hub, pressure) @ radial)
    chord, chord_points, circulation = _chords(
        points,
        polygons,
        faces=faces,
        hub=hub,
        radial=radial,
        radius=radius,
        starts=starts[group],
        line_radius=line_radius,
        fraction=chord_fraction,
        normals=normals,
        velocity=velocity,
    )
    legs = np.column_stack([np.interp(line_radius, radius, chord_points[:, k]) for k in range(3)])
    return (
        SectionLoads(
            radius,
            width,
            chord,
            radial,
            chord_points,
            force_strip / width[:, None],
            friction_strip / width[:, None],
            moments / width,
            circulation,
        ),
        group,
        legs,
    )


def _chords(
    points,
    polygons,
    *,
    faces,
    hub,
    radial,
    radius,
    starts,
    line_radius,
    fraction,
    normals,
    velocity,
):
    rings: list[list[np.ndarray]] = [[] for _ in radius]
    circulation = np.zeros(len(radius))
    for index, face in enumerate(faces):
        polygon = points[polygons[face]]
        offset = (polygon - hub) @ radial
        for j in np.flatnonzero((radius >= offset.min()) & (radius < offset.max())):
            crossing = []
            for a, b, ra, rb in zip(
                polygon, np.roll(polygon, -1, axis=0), offset, np.roll(offset, -1), strict=True
            ):
                if ra <= radius[j] < rb or rb <= radius[j] < ra:
                    crossing.append(a + (b - a) * (radius[j] - ra) / (rb - ra))
            rings[j].extend(crossing)
            if len(crossing) == 2:
                segment = crossing[1] - crossing[0]
                if segment @ np.cross(radial, normals[index]) < 0:
                    segment = -segment
                circulation[j] += velocity[index] @ segment
    chord, locations = [], []
    for r, ring in zip(radius, rings, strict=True):
        if len(ring) < 2:
            raise ValueError(
                "surface has no closed blade cut at a strip; retain a matching complete surface"
            )
        te = np.array([np.interp(r, line_radius, starts[:, k]) for k in range(3)])
        cut = np.array(ring)
        te = cut[np.argmin(np.linalg.norm(cut - te, axis=1))]
        le = cut[np.argmax(np.linalg.norm(cut - te, axis=1))]
        chord.append(np.linalg.norm(te - le))
        locations.append(le + fraction * (te - le))
    return np.array(chord), np.array(locations), circulation
