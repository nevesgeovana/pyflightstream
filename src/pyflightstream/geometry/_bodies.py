"""Bodies of revolution and superellipse bodies as a quadrilateral curve network.

Pipeline role: pure numerical stage of the geometry package. A resolved body component (plain
values, metres) becomes bicubic patches: a pole or flat-base cap at each closed end, built from
three true quadrilaterals per azimuth sector, and one skinned band between the first and the last
station, cut at the stations and junctions by knot insertion. An end may also be open, so a
parent and a child can share its rim; a boat-tail rear closes on a flat base by a law limited in
slope.
"""

from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path

import numpy as np

from pyflightstream._errors import InputValueError

from ._continuity import edge_jumps
from ._distributions import spline_distribution
from ._patch import Patch, interpolate_patch
from ._schema import stations as check_stations
from ._skin import (
    POLE_TARGET_DEG,
    SAMPLE_LADDER,
    band_axial,
    cap_edge_ids,
    clustered,
    pole_parameter_grids,
    skin_band,
)


def rear_kind(component) -> str:
    """Return ``pole``, ``base``, ``open`` or ``boat_tail``, the form of the rear end."""
    rear = component["rear"]
    return "boat_tail" if isinstance(rear, dict) else rear


def rear_end(component) -> float:
    """Return the axial fraction where the rear of the body ends."""
    if rear_kind(component) == "boat_tail":
        return float(component["rear"]["boat_tail"]["x_cut"])
    return 1.0


def is_full(component) -> bool:
    """Whether the body is a whole body about its axis rather than the half at y >= 0."""
    return component.get("symmetry", "half_y0") == "full"


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


def _ring_row(number, row):
    """Return one rings-file row as numbers, or refuse it naming its line."""
    defaults = {"centre_height": 0.0, "n_top": 2.0, "n_bottom": 2.0}
    try:
        values = {key: float(row[key]) for key in ("x", "width", "height")}
        values |= {key: float(row.get(key) or default) for key, default in defaults.items()}
    except (TypeError, ValueError) as error:
        raise InputValueError(
            f"rings_file: line {number} holds a value that is no number"
        ) from error
    return values


def read_rings(path) -> tuple[list[float], list[dict]]:
    """Read a rings file: sections measured elsewhere, one row per station.

    The file is CSV with the header ``x`` (axial fraction), ``width``, ``height`` and optionally
    ``centre_height``, ``n_top`` and ``n_bottom`` (defaults 0, 2 and 2). Returns the stations and
    the superellipse sections, in the form ``sections`` takes.

    Raises
    ------
    InputValueError
        When the file is empty, lacks a column, holds a value that is not a number, has fewer
        than three rows, or its stations are not strictly increasing inside (0, 1).
    """
    try:
        with Path(path).open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as error:
        raise InputValueError(f"rings_file: cannot read {path}") from error
    if not rows or not {"x", "width", "height"} <= set(rows[0]):
        raise InputValueError("rings_file: a header with x, width and height is required")
    values = [_ring_row(number, row) for number, row in enumerate(rows, start=2)]
    stations = [v.pop("x") for v in values]
    if len(rows) < 3 or any(b <= a for a, b in zip(stations, stations[1:], strict=False)):
        raise InputValueError("rings_file: at least three rows with increasing x are required")
    if stations[0] <= 0 or stations[-1] >= 1:
        raise InputValueError("rings_file: x must lie inside (0, 1)")
    sections = [
        {"shape": "superellipse", "at": x, **v} for x, v in zip(stations, values, strict=True)
    ]
    return stations, sections


def apply_rings(component, base, warnings) -> None:
    """Replace the sections and stations of a body by those of its ``rings_file``.

    A missing file is left for the data-file check to refuse; a file that is not a rings table
    is warned about and skipped. Given sections are replaced, and that is warned, so a file and a
    table never disagree silently.
    """
    path = component.get("rings_file", "")
    if not path or not (Path(base) / path).is_file():
        return
    try:
        stations, sections = read_rings(Path(base) / path)
    except InputValueError as error:
        warnings.append(f"{error}; skipped, the sections of the table are used")
        return
    if component["sections"] != [{"at": "middle", "shape": "circle", "radius": 0.1}]:
        warnings.append("sections: replaced by rings_file")
    component["stations"], component["sections"] = stations, sections


def check_body_symmetry(raw, component) -> None:
    """Check ``symmetry``, ``nose`` and the azimuths of a body; a whole body spans 0 to 360."""
    if component["symmetry"] not in ("full", "half_y0"):
        raise InputValueError("symmetry: expected full or half_y0")
    if component["nose"] not in ("pole", "open"):
        raise InputValueError("nose: expected pole or open")
    top = 360 if component["symmetry"] == "full" else 180
    if "azimuths" not in raw and top == 360:
        component["azimuths"] = [0.0, 60.0, 120.0, 180.0, 240.0, 300.0, 360.0]
    check_stations(component["azimuths"], "azimuths", 4, 0, top)
    if component["azimuths"][0] != 0 or component["azimuths"][-1] != top:
        what = (
            "whole body requires 0 and 360" if top == 360 else "half body requires top and bottom"
        )
        raise InputValueError(f"azimuths: {what}")


def _hermite(form, table):
    """Return the boat-tail ratio law of the axial fraction and the height it scales."""
    last = float(table["stations"][-1])
    x_cut = float(form["x_cut"])
    values, slope = spline_distribution(table["stations"], table["values"], last)
    height = float(values[1])
    if not height > 0 or not x_cut > last:
        raise InputValueError("rear.boat_tail: x_cut must lie beyond the last station of a body")
    span = x_cut - last
    end = float(form["base_height"]) / height
    m0, m1 = float(slope[1]) / height, (end - 1.0) / span

    def law(axial):
        t = np.clip((np.asarray(axial, float) - last) / span, 0.0, 1.0)
        ratio = (
            (2 * t**3 - 3 * t**2 + 1)
            + (t**3 - 2 * t**2 + t) * span * m0
            + (-2 * t**3 + 3 * t**2) * end
            + (t**3 - t**2) * span * m1
        )
        derivative = (
            (6 * t**2 - 6 * t) / span
            + (3 * t**2 - 4 * t + 1) * m0
            + (-6 * t**2 + 6 * t) * end / span
            + (3 * t**2 - 2 * t) * m1
        )
        return ratio, derivative

    return law, height


def check_boat_tail(component) -> None:
    """Refuse a boat-tail closure whose steepest slope exceeds ``angle_limit_deg``.

    The slope is the angle of the profile to the axis, over the closure from the last station to
    ``x_cut``. Does nothing for another rear.

    Raises
    ------
    InputValueError
        When ``x_cut`` is not beyond the last station, or the law needs more than the limit.
    """
    if rear_kind(component) != "boat_tail":
        return
    form = component["rear"]["boat_tail"]
    law, height = _hermite(form, body_station_table(component))
    _, derivative = law(np.linspace(float(component["stations"][-1]), form["x_cut"], 401))
    steepest = np.max(np.abs(derivative)) * height / component["length"]
    angle = float(np.degrees(np.arctan(steepest)))
    if angle > form["angle_limit_deg"] + 1e-9:
        raise InputValueError(
            f"rear.boat_tail: the closure needs {angle:.3g} degrees, above angle_limit_deg "
            f"{form['angle_limit_deg']:.3g}; move x_cut aft or raise base_height"
        )


def _closed_end(component, table, axial, values, nose):
    """Return ``values`` with the nose or the rear closed by its exponent."""
    first, last = table["stations"][[0, -1]]
    end = first if nose else last
    mask = axial < first if nose else axial > last
    exponent = component["nose_exponent" if nose else "rear_exponent"]
    endpoint, slope = spline_distribution(table["stations"], table["values"], end)
    linear = endpoint + (axial[..., None] - end) * slope
    s = axial / first if nose else (1 - axial) / (1 - last)
    s = np.clip(s, 0, 1)
    closure = s**exponent * (1 + exponent * (1 - s))
    base = 0.0 if nose or component["rear"] == "pole" else component["base_radius"]
    linear[..., :2] = base + (linear[..., :2] - base) * closure[..., None]
    return np.where(mask[..., None], linear, values)


def _boat_tail(component, table, axial, values):
    """Return ``values`` with the rear closed by the boat-tail law from the last station."""
    law, _ = _hermite(component["rear"]["boat_tail"], table)
    ratio, _ = law(axial)
    last = spline_distribution(table["stations"], table["values"], float(table["stations"][-1]))[0]
    scaled = np.array(last, float) * np.ones((*axial.shape, 1))
    scaled[..., :3] *= ratio[..., None]
    return np.where((axial > table["stations"][-1])[..., None], scaled, values)


def body_profile(component, table, axial):
    """Return the shape values at axial fractions, closing nose and rear by their exponents."""
    axial = np.asarray(axial, float)
    first, last = table["stations"][[0, -1]]
    query = np.clip(axial, first, last)
    values, _ = spline_distribution(table["stations"], table["values"], query)
    if component.get("nose", "pole") == "pole":
        values = _closed_end(component, table, axial, values, True)
    kind = rear_kind(component)
    if kind == "boat_tail":
        values = _boat_tail(component, table, axial, values)
    elif kind != "open":
        values = _closed_end(component, table, axial, values, False)
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
    sine = np.sin(azimuth)
    side = sine if is_full(component) else np.maximum(0, sine)
    y = width * np.sign(side) * np.abs(side) ** (2 / exponent)
    z = centre + height * np.sign(cosine) * np.abs(cosine) ** (2 / exponent)
    return np.stack((component["length"] * axial, y, z), axis=-1)


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
    end = rear_end(component)
    rim = body_points(component, table, end, theta)
    centre = np.array(
        [end * component["length"], 0.0, body_profile(component, table, np.asarray(end))[2]]
    )
    return centre + radius[..., None] * (rim - centre)


def _with_ids(patch, role, ids, family=None, bay=None):
    return replace(patch, role=role, edge_ids=tuple(ids), family=family or patch.family, bay=bay)


def _cap_patches(component, table, angles, sector, plan):
    """Return the nose and rear cap patches of one azimuth sector, quad by quad."""
    kind = rear_kind(component)
    ends = []
    if component.get("nose", "pole") == "pole":
        ends.append((True, "nose", "nose_cap", "ring0"))
    if kind != "open":
        ends.append(
            (False, "rear" if kind == "pole" else "base", "rear_cap", f"ring{plan['rings']}")
        )
    patches = []
    s = clustered(plan["samples"])
    for q, barycentric in enumerate(pole_parameter_grids(plan["samples"])):
        for is_nose, family, role, ring in ends:
            if is_nose or kind == "pole":
                grid = pole_patch_grid(component, table, angles, barycentric, is_nose)
            else:
                grid = base_patch_grid(component, table, angles, barycentric)
            name = "nose" if is_nose else "rear"
            ids = cap_edge_ids(name, sector, plan["sectors"], ring, plan["full"])[q]
            role = "base" if family == "base" else role
            patches.append(_with_ids(interpolate_patch(grid, family, None, s, s), role, ids))
    return patches


def _transitions(component, table, junctions):
    """Return the axial fractions where a band is cut: stations, junctions and a flat rear."""
    stations = table["stations"]
    inside = (float(x) for x in junctions if stations[0] < x < stations[-1])
    transitions = sorted({*(float(s) for s in stations), *inside})
    if rear_kind(component) in ("base", "boat_tail"):
        transitions.append(rear_end(component))
    return transitions


def _half_edges(half, plan):
    """Return the names of the two side edges of an azimuth half, without the bay suffix."""
    halves, full = plan["halves"], plan["full"]
    low = "sym0" if half == 0 and not full else f"hseam{half}"
    high_half = (half + 1) % halves if full else half + 1
    high = "sym1" if half == halves - 1 and not full else f"hseam{high_half}"
    return low, high


def _band_patches(component, theta, half, plan):
    """Return the patches of one azimuth half: one skin through every ring, cut at the stations."""
    transitions = plan["transitions"]
    s = clustered(plan["samples"])
    axial = band_axial(transitions, plan["samples"])
    azimuth = theta[0] + s * (theta[1] - theta[0])
    # Native u is azimuth and v is axial in a band; the mesher reads that order.
    points = body_points(component, plan["table"], axial[None, :], azimuth[:, None])
    pieces = skin_band(points, s, axial, transitions)
    low, high = _half_edges(half, plan)
    patches = []
    for index, piece in enumerate(pieces):
        x0, x1 = transitions[index], transitions[index + 1]
        family = "rear" if x1 == 1 else ("front" if index == 0 else "middle")
        ids = (
            f"{low}.b{index}",
            f"{high}.b{index}",
            f"ring{index}.h{half}",
            f"ring{index + 1}.h{half}",
        )
        patches.append(_with_ids(piece, "band", ids, family, (float(x0), float(x1))))
    return patches


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
        The cap and band patches of the body, in the body frame. Each carries a ``role``
        (``nose_cap``, ``rear_cap``, ``base`` or ``band``) and the names of its four edges, so
        two patches that share an edge carry the same name for it. A closed end is a cap at the
        pole or a flat base; an open end has no patch and its rim edges are the band's.

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
    for samples in SAMPLE_LADDER:
        patches = _build(component, junctions, samples)
        if _pole_turn(patches) <= POLE_TARGET_DEG:
            break
    return patches


def _pole_turn(patches) -> float:
    """Return the largest turn, in degrees, across a seam between two cap patches of one end."""
    caps = [p for p in patches if p.role in ("nose_cap", "rear_cap")]
    found = edge_jumps(caps)
    return max((r["jump_deg"] for r in found), default=0.0)


def _build(component, junctions, samples):
    """Return the patches of a body sampled with ``samples`` points along every edge."""
    table = body_station_table(component)
    angles = np.deg2rad(component["azimuths"])
    transitions = _transitions(component, table, junctions)
    pairs = list(zip(angles, angles[1:], strict=False))
    plan = {
        "sectors": len(pairs),
        "halves": 2 * len(pairs),
        "full": is_full(component),
        "rings": len(transitions) - 1,
        "samples": samples,
        "table": table,
        "transitions": transitions,
    }
    patches = []
    for sector, (a, b) in enumerate(pairs):
        patches += _cap_patches(component, table, (a, b), sector, plan)
        for offset, (low, high) in enumerate([(a, (a + b) / 2), ((a + b) / 2, b)]):
            patches += _band_patches(component, (low, high), 2 * sector + offset, plan)
    return patches


def axisymmetric_radius(component, axial):
    """Return the radius at axial fractions of an axisymmetric body; refuse any other."""
    table = body_station_table(component)
    if not table["axisymmetric"]:
        raise InputValueError("sections: not axisymmetric")
    return body_profile(component, table, np.asarray(axial))[..., 0]
