"""The skin patches of every component of a resolved configuration, and their inside regions.

Pipeline role: pure numerical stage of the geometry package, below the geometry
kernel. :func:`generate_components` turns a resolved configuration into placed
patches per component; :func:`assembly_regions` gives the inside predicate of
each component, which the workspace assembly uses to drop faces buried in
another component.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from pyflightstream._errors import InputValueError

from ._blister import blister_model, blister_region
from ._bodies import body, body_station_table
from ._boundary import unpack
from ._caps import tip_cap, wing_contour_point
from ._fairings import wing_fuselage_fairing, wing_junction
from ._fillet import fillet_hosts, fillet_model
from ._lifting import lifting_surface, section_models, thickness_station
from ._patch import Patch, interpolate_patch
from ._placement import (
    body_junctions,
    move,
    place,
    placement_transform,
    wing_in_body_frame,
)
from ._regions import (
    body_region,
    fairing_volume_triangles,
    inside_triangles,
    lifting_region,
    placed_region,
)
from ._skin import split_along

__all__ = ["assembly_regions", "generate_components", "junction_lifting_surface"]


def generate_components(config) -> dict[str, list[Patch]]:
    """Return the placed patches of every component of a resolved configuration.

    Parameters
    ----------
    config : dict
        Resolved configuration; its components are unpacked to plain values.

    Returns
    -------
    dict
        Component name to its list of placed patches, in the world frame.

    Raises
    ------
    InputValueError
        If a component is of a type other than body, lifting_surface or wing_fuselage_fairing.
    """
    components = unpack(config)["components"]
    result = {}
    for name, component in components.items():
        kind = component["type"]
        if kind == "body":
            patches = body(component, body_junctions(components, name))
        elif kind == "lifting_surface":
            fairings = [
                other
                for other in components.values()
                if other["type"] == "wing_fuselage_fairing" and other["hosts"][1] == name
            ]
            if fairings:
                fairing = fairings[0]
                body_name = fairing["hosts"][0]
                host_wing = wing_in_body_frame(components, body_name, name)
                patches = junction_lifting_surface(host_wing, components[body_name], fairing)
                patches += tip_cap(host_wing)
                rotation, translation = placement_transform(components, body_name)
                result[name] = move(patches, rotation, translation)
                continue
            patches = lifting_surface(component) + tip_cap(component)
        elif kind == "wing_fuselage_fairing":
            body_name, wing_name = component["hosts"]
            wing = wing_in_body_frame(components, body_name, wing_name)
            patches = wing_fuselage_fairing(component, components[body_name], wing)
        elif kind in ("fillet", "blister"):
            # Built in the frame of the body they lie on; their own placement is not read.
            patches, body_name = blend_faces(components, name)
            result[name] = move(patches, *placement_transform(components, body_name))
            continue
        else:
            raise InputValueError(
                f"{name}.type: this assembly driver supports body, lifting_surface, "
                "wing_fuselage_fairing, fillet and blister"
            )
        result[name] = place(patches, components, name)
    return result


def blend_faces(components, name) -> tuple[list[Patch], str]:
    """Return the faces a fillet or a blister writes today, and the body whose frame they are in.

    Until the assembly writes trimmed faces, each face is its base cut at iso lines: a fillet's
    two faces lie between its contact lines, split at the leading edge; a blister's base is cut
    at its mean crease into the face outside the host and a band inside it, which the assembly
    drops as buried. No count is assumed: every face carries its family and role.
    """
    component = components[name]
    if component["type"] == "fillet":
        model = fillet_model(component, components, name)
        _, body_name = fillet_hosts(components, name)
        start = model.trims[0].loop[0][0][0]
        middle = split_along(model.base, "v", [model.contacts["v_host"], model.contacts["v_wing"]])[
            1
        ]
        cuts = [start, 0.5] if start > 0.0 else [0.5]
        pieces = split_along(middle, "u", cuts)[-2:]
        return [
            replace(piece, family=f"fillet_{side}", role="fillet")
            for piece, side in zip(pieces, ("lower", "upper"), strict=True)
        ], body_name
    host = component["host"]
    if components[host]["type"] != "body":
        raise InputValueError(f"{name}.host: a blister lies on a body; {host!r} is not one")
    loft = blister_model(component, components[host])
    patches = []
    for base, patch in loft.bases.items():
        crease = float(np.mean(loft.crease[base][1:-1, 0]))
        outer, inner = split_along(patch, "u", [crease])
        patches.append(replace(outer, family=f"blister_{base}", role="blister"))
        patches.append(replace(inner, family=f"blister_{base}_inside", role="blister_band"))
    return patches, host


def junction_lifting_surface(wing, host, fairing) -> list[Patch]:
    """Imprint the fairing contact as a tensor-patch edge on both wing skins.

    The same contour samples and knots are used at the junction. The thickness
    split blends to the tip split with zero slope at the junction, preserving
    the span tangent there and the existing tip-cap boundary.
    """
    models, table = section_models(wing["sections"]), body_station_table(host)
    root_max, tip_max = (thickness_station(wing, models, eta) for eta in (0.0, 1.0))
    families = [
        "upper_fore",
        "upper_aft",
        "trailing_upper",
        "trailing_lower",
        "lower_aft",
        "lower_fore",
    ]
    patches = []
    for index, family in enumerate(families):
        contacts = [
            wing_junction(fairing, host, table, wing, models, maximum=root_max, index=index, u=u)
            for u in np.linspace(0, 1, 49)
        ]
        for bay in ("inner", "outer", "outboard"):
            grid = []
            for u, (contact, _, width) in zip(np.linspace(0, 1, 49), contacts, strict=True):
                junction_eta = 2 * contact[1] / wing["planform"]["span"]
                ring_eta = junction_eta + min(
                    2
                    * max(width, 0.05 * wing["planform"]["root_chord"])
                    / wing["planform"]["span"],
                    (1 - junction_eta) / 2,
                )
                row = []
                for v in np.linspace(0, 1, 9):
                    low, high = {
                        "inner": (0.0, junction_eta),
                        "outer": (junction_eta, ring_eta),
                        "outboard": (ring_eta, 1.0),
                    }[bay]
                    eta = low + (high - low) * v
                    maximum = (
                        root_max + (tip_max - root_max) * (3 * v * v - 2 * v * v * v)
                        if bay == "outboard"
                        else root_max
                    )
                    row.append(wing_contour_point(wing, models, maximum, index, u, eta))
                grid.append(row)
            patches.append(interpolate_patch(grid, family=family))
    return patches


def assembly_regions(config, patches) -> dict:
    """Return the inside predicate of every component, in the world frame.

    Parameters
    ----------
    config : dict
        Resolved configuration of the assembly.
    patches : dict
        Placed patches per component name, as :func:`generate_components` returns; the fairing
        volume is built from them.

    Returns
    -------
    dict
        Component name to a function of a world point that tells whether it is inside.
    """
    components = unpack(config)["components"]
    regions = {}
    for name, component in components.items():
        rotation, translation = placement_transform(components, name)
        if component["type"] == "body":
            regions[name] = placed_region(body_region(component), rotation, translation)
        elif component["type"] == "lifting_surface":
            regions[name] = placed_region(lifting_region(component), rotation, translation)
        elif component["type"] == "wing_fuselage_fairing":
            wing_name = component["hosts"][1]
            wr, wt = placement_transform(components, wing_name)
            interior = wt + wr @ np.array(
                [components[wing_name]["planform"]["root_chord"] / 2, 0.0, 0.0]
            )
            triangles = fairing_volume_triangles(patches[name], interior)
            regions[name] = lambda point, skin=triangles: inside_triangles(point, skin)
        elif component["type"] == "blister":
            host = component["host"]
            regions[name] = placed_region(
                blister_region(component, components[host]),
                *placement_transform(components, host),
            )
        elif component["type"] == "fillet":
            # The blend buries nothing until the dominance stage trims its hosts by it.
            regions[name] = lambda point: False
    return regions
