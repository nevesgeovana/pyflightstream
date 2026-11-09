"""Bodies of revolution and superellipse bodies as a quadrilateral curve network.

Pipeline role: pure numerical stage of the geometry package. A resolved body
component (plain values, metres) becomes bicubic patches: a pole or flat-base
cap at each end, built from three true quadrilaterals per azimuth sector, and
front, middle and rear bands between the stations and junction stations.
"""

from __future__ import annotations

import numpy as np

from pyflightstream._errors import InputValueError

from ._distributions import spline_distribution
from ._patch import Patch, interpolate_patch


def body_station_table(component):
    """Return the shape values (width, height, centre, two exponents) at the control stations."""
    controls = np.asarray(component["stations"], float)
    rows = []
    for section in component["sections"]:
        position = section["at"]
        if isinstance(position, str):
            position = {
                "nose": controls[0],
                "front": controls[0],
                "middle": controls[1],
                "rear": controls[-1],
            }[position]
        if section.get("shape", "circle") == "circle":
            row = [section["radius"], section["radius"], 0.0, 2.0, 2.0]
        else:
            row = [
                section["width"],
                section["height"],
                section.get("centre_height", 0.0),
                section["n_top"],
                section["n_bottom"],
            ]
        rows.append((position, row))
    rows.sort(key=lambda row: row[0])
    locations = np.array([row[0] for row in rows])
    values = np.array([row[1] for row in rows])
    # A lone declared section covers the full reference body. Multiple sections
    # extend their endpoint values to the bounding transition stations.
    if len(rows) == 1:
        station_values = np.broadcast_to(values[0], (len(controls), 5)).copy()
    else:
        station_values = spline_distribution(
            locations, values, np.clip(controls, locations[0], locations[-1])
        )[0]
    return {
        "stations": controls,
        "values": station_values,
        "axisymmetric": bool(
            np.all(station_values[:, 0] == station_values[:, 1])
            and np.all(station_values[:, 2] == 0)
            and np.all(station_values[:, 3:] == 2)
        ),
    }


def body_profile(component, table, axial):
    """Return the shape values at axial fractions, closing nose and rear by their exponents."""
    axial = np.asarray(axial, float)
    first, last = table["stations"][[0, -1]]
    query = np.clip(axial, first, last)
    values, _ = spline_distribution(table["stations"], table["values"], query)
    for end, mask, exponent, is_nose in [
        (first, axial < first, component["nose_exponent"], True),
        (last, axial > last, component["rear_exponent"], False),
    ]:
        endpoint, slope = spline_distribution(table["stations"], table["values"], end)
        linear = endpoint + (axial[..., None] - end) * slope
        s = axial / first if is_nose else (1 - axial) / (1 - last)
        s = np.clip(s, 0, 1)
        closure = s**exponent * (1 + exponent * (1 - s))
        base = 0.0 if is_nose or component["rear"] == "pole" else component["base_radius"]
        linear[..., :2] = base + (linear[..., :2] - base) * closure[..., None]
        values = np.where(mask[..., None], linear, values)
    if np.any(values[..., :2] < -1e-12) or np.any(values[..., 3:] <= 0):
        raise InputValueError(
            "sections: profile interpolation makes width, height or exponent invalid"
        )
    if table["axisymmetric"]:
        values[..., 1] = values[..., 0]
    return values


def body_points(component, table, axial, azimuth):
    """Return the surface points at axial fractions and azimuths (radians), in the body frame."""
    axial, azimuth = np.broadcast_arrays(axial, azimuth)
    parameters = body_profile(component, table, axial)
    width, height, centre, top, bottom = np.moveaxis(parameters, -1, 0)
    cosine = np.cos(azimuth)
    exponent = np.where(cosine >= 0, top, bottom)
    y = width * np.maximum(0, np.sin(azimuth)) ** (2 / exponent)
    z = centre + height * np.sign(cosine) * np.abs(cosine) ** (2 / exponent)
    return np.stack((component["length"] * axial, y, z), axis=-1)


def pole_parameter_grids():
    """Split a triangular network cell into three true quadrilaterals.

    Coordinates are barycentric weights of the two station-arc vertices;
    the remaining weight belongs to the pole. Outer arc halves are inherited
    by the adjoining axial bays, so no hanging node is introduced.
    """
    a, b, c = np.array([0.0, 0.0]), np.array([1.0, 0.0]), np.array([0.0, 1.0])
    ab, bc, ca, centre = (a + b) / 2, (b + c) / 2, (c + a) / 2, (a + b + c) / 3
    u, v = np.linspace(0, 1, 17)[:, None, None], np.linspace(0, 1, 17)[None, :, None]
    return [
        (1 - u) * (1 - v) * p0 + u * (1 - v) * p1 + u * v * p2 + (1 - u) * v * p3
        for p0, p1, p2, p3 in [(a, ab, centre, ca), (ab, b, bc, centre), (centre, bc, c, ca)]
    ]


def pole_patch_grid(component, table, angles, barycentric, nose):
    """Return the sample grid of one nose or rear cap quadrilateral."""
    radius = np.sum(barycentric, axis=-1)
    fraction = np.divide(barycentric[..., 1], radius, out=np.zeros_like(radius), where=radius > 0)
    theta = angles[0] + (angles[1] - angles[0]) * fraction
    if nose:
        axial = table["stations"][0] * radius ** (1 / component["nose_exponent"])
    else:
        axial = 1 - (1 - table["stations"][-1]) * radius ** (1 / component["rear_exponent"])
    return body_points(component, table, axial, theta)


def base_patch_grid(component, table, angles, barycentric):
    """Return the sample grid of one flat-base quadrilateral."""
    radius = np.sum(barycentric, axis=-1)
    fraction = np.divide(barycentric[..., 1], radius, out=np.zeros_like(radius), where=radius > 0)
    theta = angles[0] + (angles[1] - angles[0]) * fraction
    rim = body_points(component, table, 1.0, theta)
    centre = np.array(
        [component["length"], 0.0, body_profile(component, table, np.asarray(1.0))[2]]
    )
    return centre + radius[..., None] * (rim - centre)


def body(component, junctions=()) -> list[Patch]:
    """Return the patches of a body, with extra station breaks at the ``junctions`` fractions.

    Parameters
    ----------
    component : dict
        Resolved body component (plain values, metres and degrees).
    junctions : sequence of float, optional
        Axial fractions at which extra station breaks are inserted; default empty.

    Returns
    -------
    list of Patch
        The nose, band, rear or base patches of the body, in the body frame.

    Examples
    --------
    >>> from pyflightstream.geometry._boundary import unpack
    >>> from pyflightstream.geometry.config import resolve_config
    >>> raw = {"type": "body", "length": 20.0,
    ...        "sections": [{"at": "middle", "shape": "circle", "radius": 1.2}]}
    >>> patches = body(unpack(resolve_config(raw))["components"]["COMPONENT"])
    >>> len(patches) > 0
    True
    """
    table = body_station_table(component)
    angles = np.deg2rad(component["azimuths"])
    patches = []
    for a, b in zip(angles, angles[1:], strict=False):
        for barycentric in pole_parameter_grids():
            patches.append(
                interpolate_patch(
                    pole_patch_grid(component, table, (a, b), barycentric, True), family="nose"
                )
            )
            if component["rear"] == "pole":
                patches.append(
                    interpolate_patch(
                        pole_patch_grid(component, table, (a, b), barycentric, False), family="rear"
                    )
                )
            else:
                patches.append(
                    interpolate_patch(
                        base_patch_grid(component, table, (a, b), barycentric), family="base"
                    )
                )
        for low, high in [(a, (a + b) / 2), ((a + b) / 2, b)]:
            transitions = sorted(
                set(
                    [
                        *table["stations"],
                        *(
                            float(x)
                            for x in junctions
                            if table["stations"][0] < x < table["stations"][-1]
                        ),
                    ]
                )
            )
            if component["rear"] == "base":
                transitions.append(1.0)
            for index, (x0, x1) in enumerate(zip(transitions, transitions[1:], strict=False)):
                axial, theta = np.meshgrid(np.linspace(x0, x1, 17), np.linspace(low, high, 17))
                family = "front" if index == 0 else "middle"
                if x1 == 1:
                    family = "rear"
                patches.append(
                    interpolate_patch(
                        body_points(component, table, axial, theta),
                        family=family,
                        bay=(float(x0), float(x1)),
                    )
                )
    return patches


def axisymmetric_radius(component, axial):
    """Return the radius at axial fractions of an axisymmetric body; refuse any other."""
    table = body_station_table(component)
    if not table["axisymmetric"]:
        raise InputValueError("sections: not axisymmetric")
    return body_profile(component, table, np.asarray(axial))[..., 0]
