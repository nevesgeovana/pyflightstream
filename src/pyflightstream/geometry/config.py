"""One TOML input boundary for the parametric geometry.

Pipeline role: pure configuration stage of the geometry package. Values use
metres, degrees and unitless fractions. A configuration is read from TOML,
validated, completed with documented defaults and returned with a unit and a
source (``given`` or ``default``) on every value. The resolved form can be
written back and read again without change.

Generation defaults that the supplied values do not fix are explicit in
``default_component``; they are generic examples, never inferred from any
particular aircraft.
"""

from __future__ import annotations

import math
import re
import tomllib
from copy import deepcopy
from pathlib import Path

from pyflightstream._errors import InputValueError
from pyflightstream.geometry._boundary import unit_for, unpack

__all__ = ["load_config", "resolve_config"]

RESOLVED_FORMAT = "pyflightstream-geometry-resolved"


def default_component(kind):
    """Return fresh plain data, with no shared mutable defaults."""
    common = {
        "type": kind,
        "version": "1.1.0",
        "placement": {"translation": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0]},
        "attach": {"parent": "", "station": 0.0},
    }
    if kind == "lifting_surface":
        common.update(
            planform={
                "span": 1.0,
                "aspect_ratio": 8.0,
                "taper": 1.0,
                "sweep": 0.0,
                "sweep_reference": "leading_edge",
                "dihedral": 0.0,
                "incidence": 0.0,
                "tip_twist": 0.0,
                "twist_axis": 0.25,
                "control_stations": [0.0, 1 / 3, 2 / 3, 1.0],
                "breaks": [],
            },
            sections={
                "airfoils": ["NACA0012", "NACA0012"],
                "eta": [0.0, 1.0],
                "degree": 5,
                "n1": 0.5,
                "n2": 1.0,
                "trailing_edge_thickness": 0.00252,
                "blend": "spline",
            },
            tip_cap={
                "kind": "flat",
                "length": 1.0,
                "exponent": 1.0,
                "profile": {
                    "stations": [0.0, 0.25, 1.0],
                    "start": [0.0, 0.01, 0.015],
                    "ridge": [0.01, 0.07, 0.078],
                    "exponent": [2.3, 2.3, 2.6],
                },
            },
            root_fillet={"enabled": False, "radii": [0.0, 0.0, 0.0]},
            continuity="G1",
        )
    elif kind == "body":
        common.update(
            length=1.0,
            stations=[0.15, 0.35, 0.75],
            sections=[{"at": "middle", "shape": "circle", "radius": 0.1}],
            azimuths=[0.0, 60.0, 120.0, 180.0],
            rear="pole",
            base_radius=0.05,
            nose_exponent=0.5,
            rear_exponent=1.0,
            continuity="G1",
        )
    elif kind == "wing_fuselage_fairing":
        common.update(
            hosts=["FUS", "WING"],
            start=-0.25,
            end=1.25,
            stations=[-0.25, 0.0, 0.3, 1.0, 1.25],
            width=[0.0, 0.1, 0.15, 0.1, 0.0],
            footprint_upper=45.0,
            footprint_lower=135.0,
            body_blend_radius=0.05,
            wing_blend_radius=0.05,
            start_exponent=0.5,
            end_exponent=0.5,
        )
    elif kind == "propeller":
        common.update(
            radius=1.0,
            hub_radius=0.2,
            blade_count=2,
            rotation_sense=1,
            stations=[0.2, 0.6, 1.0],
            chord=[0.12, 0.10, 0.06],
            twist=[0.0, 0.0, 0.0],
            xbar=[0.0, 0.0, 0.0],
            ybar=[0.0, 0.0, 0.0],
            setting_angle=0.0,
            pitch_reference=0.7,
            sections={
                "airfoils": ["NACA0012"],
                "eta": [0.0],
                "degree": 5,
                "n1": 0.5,
                "n2": 1.0,
                "trailing_edge_thickness": 0.00252,
                "blend": "spline",
            },
        )
    else:
        raise InputValueError(f"type: unsupported {kind!r}")
    return common


def merge_values(defaults, supplied, path=""):
    """Overlay supplied values on defaults, refusing any parameter the defaults do not know."""
    result = deepcopy(defaults)
    for key, value in supplied.items():
        label = f"{path}.{key}".strip(".")
        if key not in defaults and key not in {
            "original",
            "distributions",
            "root_chord",
            "tip_chord",
            "area",
        }:
            raise InputValueError(f"{label}: unknown parameter")
        if isinstance(result.get(key), dict):
            if not isinstance(value, dict):
                raise InputValueError(f"{label}: expected a table")
            result[key] = merge_values(result[key], value, label)
        else:
            result[key] = deepcopy(value)
    return result


def number(value, name, lower=None, upper=None, strict=False):
    """Return ``value`` if it is a finite number inside the bounds, else refuse naming ``name``."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise InputValueError(f"{name}: expected finite number")
    if lower is not None and (value <= lower if strict else value < lower):
        raise InputValueError(f"{name}: below permitted range")
    if upper is not None and value > upper:
        raise InputValueError(f"{name}: above permitted range")
    return value


def stations(values, name, count=2, lower=0.0, upper=1.0):
    """Refuse unless ``values`` holds ``count`` or more strictly increasing numbers in bounds."""
    if not isinstance(values, list) or len(values) < count:
        raise InputValueError(f"{name}: requires at least {count} stations")
    for value in values:
        number(value, name, lower, upper)
    if any(a >= b for a, b in zip(values, values[1:], strict=False)):
        raise InputValueError(f"{name}: stations must be strictly increasing")


def validate_ridge_profile(profile):
    """Validate a ridged cap profile.

    Per chord station: spanwise start of the rounding, ridge height and superellipse exponent.
    """
    stations(profile["stations"], "tip_cap.profile.stations")
    if profile["stations"][0] != 0 or profile["stations"][-1] != 1:
        raise InputValueError("tip_cap.profile.stations: must run from 0 to 1")
    for key in ("start", "ridge", "exponent"):
        values = profile[key]
        if not isinstance(values, list) or len(values) != len(profile["stations"]):
            raise InputValueError(f"tip_cap.profile.{key}: count must match the stations")
        for value in values:
            number(value, f"tip_cap.profile.{key}", 0, strict=key == "exponent")
    if any(r <= s for r, s in zip(profile["ridge"], profile["start"], strict=True)):
        raise InputValueError("tip_cap.profile.ridge: must exceed start at every station")
    if any(n < 1.2 for n in profile["exponent"]):
        raise InputValueError("tip_cap.profile.exponent: at least 1.2 required")


def resolve_planform(supplied, defaults):
    """Complete an independent trapezoidal set, rejecting redundant disagreement."""
    p = deepcopy(defaults)
    span = number(p["span"], "planform.span", 0, strict=True)
    if "root_chord" in supplied:
        root = number(supplied["root_chord"], "planform.root_chord", 0, strict=True)
        tip = supplied.get("tip_chord", root * p["taper"])
        taper = tip / root
        area = span * (root + tip) / 2
        ar = span**2 / area
    elif "area" in supplied:
        area = number(supplied["area"], "planform.area", 0, strict=True)
        ar = supplied.get("aspect_ratio", span**2 / area)
        if "span" not in supplied and "aspect_ratio" in supplied:
            span = math.sqrt(area * ar)
        taper = p["taper"]
        root = 2 * area / (span * (1 + taper))
        tip = root * taper
    else:
        ar, taper = p["aspect_ratio"], p["taper"]
        number(ar, "planform.aspect_ratio", 0, strict=True)
        number(taper, "planform.taper", 0, strict=True)
        area = span**2 / ar
        root = 2 * area / (span * (1 + taper))
        tip = root * taper
    expected = {
        "span": span,
        "root_chord": root,
        "tip_chord": tip,
        "area": area,
        "aspect_ratio": span**2 / area,
        "taper": taper,
    }
    for key, value in expected.items():
        number(value, f"planform.{key}", 0, strict=True)
        if key in supplied and not math.isclose(supplied[key], value, rel_tol=1e-10, abs_tol=1e-12):
            raise InputValueError(
                f"planform.root_chord/planform.{key}: inconsistent independent set"
            )
    p.update(expected)
    return p


def resolve_lifting(raw, component):
    """Complete and validate a lifting-surface component; return its derived area and mean chord."""
    component["planform"] = resolve_planform(raw.get("planform", {}), component["planform"])
    p, section = component["planform"], component["sections"]
    if "eta" not in raw.get("sections", {}):
        count = len(section["airfoils"])
        section["eta"] = [i / max(1, count - 1) for i in range(count)]
    stations(p["control_stations"], "planform.control_stations")
    if p["control_stations"][0] != 0 or p["control_stations"][-1] != 1:
        raise InputValueError("planform.control_stations: must cover [0, 1]")
    if p["breaks"]:
        stations(p["breaks"], "planform.breaks", 1)
    if p["sweep_reference"] not in ("leading_edge", "quarter_chord"):
        raise InputValueError("planform.sweep_reference: unsupported reference")
    if p["twist_axis"] != 0.25:
        raise InputValueError("planform.twist_axis: must be 0.25")
    for key in ("sweep", "dihedral", "incidence", "tip_twist"):
        number(p[key], f"planform.{key}", -89, 89)
    for key, distribution in component.get("distributions", {}).items():
        if key not in ("leading_edge_x", "leading_edge_z", "chord", "twist"):
            raise InputValueError(f"distributions.{key}: unsupported distribution")
        stations(distribution["stations"], f"distributions.{key}.stations")
        if len(distribution["values"]) != len(distribution["stations"]):
            raise InputValueError(f"distributions.{key}.values: count mismatch")
        for value in distribution["values"]:
            number(
                value,
                f"distributions.{key}.values",
                0 if key == "chord" else None,
                strict=key == "chord",
            )
    if component["tip_cap"]["kind"] not in ("flat", "rounded", "ridged", "none"):
        raise InputValueError("tip_cap.kind: expected flat, rounded, ridged or none")
    if component["tip_cap"]["kind"] == "ridged":
        validate_ridge_profile(component["tip_cap"]["profile"])
    number(component["tip_cap"]["length"], "tip_cap.length", 0, strict=True)
    number(component["tip_cap"]["exponent"], "tip_cap.exponent", 0, strict=True)
    if len(component["root_fillet"]["radii"]) != 3:
        raise InputValueError("root_fillet.radii: requires LE, maximum thickness and TE values")
    for radius in component["root_fillet"]["radii"]:
        number(radius, "root_fillet.radii", 0)
    validate_sections(section)
    taper, root = p["taper"], p["root_chord"]
    return {
        "area": p["area"],
        "mac": 2 * root * (1 + taper + taper**2) / (3 * (1 + taper)),
        "mac_eta": (1 + 2 * taper) / (3 * (1 + taper)),
    }


def validate_sections(section):
    """Validate the section table of a lifting surface or propeller."""
    stations(section["eta"], "sections.eta", 1)
    if len(section["airfoils"]) != len(section["eta"]):
        raise InputValueError("sections.airfoils: count differs from sections.eta")
    for name in section["airfoils"]:
        if not isinstance(name, str) or not re.fullmatch(r"NACA(?:\d{4}|\d{5})", name):
            raise InputValueError("sections.airfoils: expected NACA designation")
    if not isinstance(section["degree"], int) or section["degree"] < 1:
        raise InputValueError("sections.degree: expected positive integer")
    for key in ("n1", "n2"):
        number(section[key], f"sections.{key}", 0, strict=True)
    number(section["trailing_edge_thickness"], "sections.trailing_edge_thickness", 0, 0.1)
    if section["blend"] != "spline":
        raise InputValueError("sections.blend: must be spline")


def resolve_body(raw, component):
    """Validate a body component and return its (empty) derived quantities."""
    number(component["length"], "length", 0, strict=True)
    stations(component["stations"], "stations", 3)
    if component["stations"][0] <= 0 or component["stations"][-1] >= 1:
        raise InputValueError("stations: body transitions must be inside (0, 1)")
    stations(component["azimuths"], "azimuths", 4, 0, 180)
    if component["azimuths"][0] != 0 or component["azimuths"][-1] != 180:
        raise InputValueError("azimuths: half body requires top and bottom")
    if component["rear"] not in ("base", "pole"):
        raise InputValueError("rear: expected base or pole")
    if not component["sections"]:
        raise InputValueError("sections: requires a section")
    for i, section in enumerate(component["sections"]):
        name = f"sections[{i}]"
        if section.get("at") not in ("nose", "front", "middle", "rear"):
            number(section.get("at"), name + ".at", 0, 1)
        if section.get("shape", "circle") == "circle":
            number(section.get("radius"), name + ".radius", 0, strict=True)
        elif section["shape"] == "superellipse":
            for key in ("width", "height", "n_top", "n_bottom"):
                number(section.get(key), name + "." + key, 0, strict=True)
            number(section.get("centre_height", 0), name + ".centre_height")
        else:
            raise InputValueError(name + ".shape: unsupported shape")
    for key in ("base_radius", "nose_exponent", "rear_exponent"):
        number(component[key], key, 0, strict=True)
    return {}


def resolve_fairing(raw, component):
    """Validate a wing-fuselage fairing component and return its (empty) derived quantities."""
    if len(component["hosts"]) != 2 or len(set(component["hosts"])) != 2:
        raise InputValueError("hosts: requires distinct body and lifting surface")
    stations(component["stations"], "stations", 5, component["start"], component["end"])
    if len(component["width"]) != len(component["stations"]):
        raise InputValueError("width: count differs from stations")
    for value in component["width"]:
        number(value, "width", 0)
    for key in ("body_blend_radius", "wing_blend_radius", "start_exponent", "end_exponent"):
        number(component[key], key, 0, strict=True)
    for key in ("footprint_upper", "footprint_lower"):
        number(component[key], key, 0, 180)
    return {}


def resolve_propeller(raw, component):
    """Validate a propeller component and return its (empty) derived quantities."""
    number(component["radius"], "radius", 0, strict=True)
    number(component["hub_radius"], "hub_radius", 0, component["radius"], strict=True)
    if component["hub_radius"] >= component["radius"]:
        raise InputValueError("hub_radius: must be below radius")
    stations(component["stations"], "stations", 2, component["hub_radius"] / component["radius"], 1)
    if type(component["blade_count"]) is not int or component["blade_count"] < 1:
        raise InputValueError("blade_count: expected positive integer")
    if component["rotation_sense"] not in (-1, 1):
        raise InputValueError("rotation_sense: expected -1 or 1")
    for key in ("chord", "twist", "xbar", "ybar"):
        if len(component[key]) != len(component["stations"]):
            raise InputValueError(f"{key}: count differs from stations")
        for value in component[key]:
            number(value, key, 0 if key == "chord" else None, strict=key == "chord")
    number(component["setting_angle"], "setting_angle", -180, 180)
    number(component["pitch_reference"], "pitch_reference", 0, 1)
    validate_sections(component["sections"])
    return {}


def provenance(value, supplied, path=""):
    """Wrap each leaf of a component as ``{value, unit, source}``; source is given or default."""
    if isinstance(value, dict):
        provided = supplied if isinstance(supplied, dict) else {}
        return {
            k: provenance(v, provided.get(k), f"{path}.{k}".strip(".")) for k, v in value.items()
        }
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return [provenance(v, supplied[i] if supplied else None, path) for i, v in enumerate(value)]
    return {
        "value": value,
        "unit": unit_for(path),
        "source": "default" if supplied is None else "given",
    }


def validate_relationships(components, configurations):
    """Refuse attachment cycles, missing parents, wrong fairing hosts and bad members."""
    for name, component in components.items():
        parent = component["attach"]["parent"]
        seen = {name}
        while parent:
            if parent not in components or parent in seen:
                raise InputValueError(f"{name}.attach.parent: missing parent or cycle")
            seen.add(parent)
            parent = components[parent]["attach"]["parent"]
        if component["type"] == "wing_fuselage_fairing" and len(components) > 1:
            for host, kind in zip(component["hosts"], ("body", "lifting_surface"), strict=True):
                if host not in components or components[host]["type"] != kind:
                    raise InputValueError(f"{name}.hosts: expected {kind} host {host}")
    for name, members in configurations.items():
        if not isinstance(members, list) or not members or len(members) != len(set(members)):
            raise InputValueError(f"configurations.{name}: expected unique nonempty members")
        for member in members:
            if member not in components:
                raise InputValueError(f"configurations.{name}: unknown component {member}")


def assembly_defaults(components, supplied):
    """Seed generic layout defaults, not measurements: WING at .4L, HTP at .95L.

    Fairing blend radii default to .4 root chord when its hosts are available.
    Explicit inputs always win. Standalone primitive defaults are unchanged.
    """
    for name, component in components.items():
        raw = supplied[name]
        if (
            name in ("WING", "HTP")
            and component["attach"]["parent"]
            and components.get(component["attach"]["parent"], {}).get("type") == "body"
            and "station" not in raw.get("attach", {})
        ):
            component["attach"]["station"] = 0.4 if name == "WING" else 0.95
        if component["type"] == "wing_fuselage_fairing":
            body_name, wing_name = component["hosts"]
            if wing_name in components and body_name in components:
                chord = components[wing_name]["planform"]["root_chord"]
                for key in ("body_blend_radius", "wing_blend_radius"):
                    if key not in raw:
                        component[key] = 0.4 * chord
                if "parent" not in raw.get("attach", {}):
                    component["attach"]["parent"] = body_name


def resolve_config(data):
    """Validate a geometry configuration and resolve it with the source of every value.

    Parameters
    ----------
    data : dict
        A configuration as read from TOML: fresh input (a ``components``
        table, or a single component carrying ``type``) or a previously
        resolved configuration (``format = "pyflightstream-geometry-resolved"``),
        whose derived quantities are recomputed and compared.

    Returns
    -------
    dict
        The resolved configuration: ``format``, ``units`` (m and deg),
        ``components`` with each leaf wrapped as ``{value, unit, source}``
        (source ``given`` or ``default``), ``derived`` quantities and
        ``configurations``. A resolved input that checks out is returned as a
        copy of itself.

    Raises
    ------
    InputValueError
        When the units are not m and deg, no component is given, a component
        lacks its type or an X.Y.Z version, a value or relationship is out of
        range, or a resolved input's derived quantity is inconsistent.
    """
    resolved = data.get("format") == RESOLVED_FORMAT
    source = unpack(data)
    if "type" in source:
        source = {"components": {"COMPONENT": source}}
    if source.get("units", {"length": "m", "angle": "deg"}) != {"length": "m", "angle": "deg"}:
        raise InputValueError("units: supported length=m, angle=deg")
    components, annotated, derived = {}, {}, {}
    if not source.get("components"):
        raise InputValueError("components: requires at least one component")
    resolvers = {
        "lifting_surface": resolve_lifting,
        "body": resolve_body,
        "wing_fuselage_fairing": resolve_fairing,
        "propeller": resolve_propeller,
    }
    for name, raw in source["components"].items():
        if "type" not in raw:
            raise InputValueError(f"components.{name}.type: required")
        component = merge_values(default_component(raw["type"]), raw)
        derived[name] = resolvers[raw["type"]](raw, component)
        if not re.fullmatch(r"\d+\.\d+\.\d+", component["version"]):
            raise InputValueError(f"{name}.version: expected X.Y.Z")
        for key in ("translation", "rotation"):
            values = component["placement"][key]
            if len(values) != 3:
                raise InputValueError(f"{name}.placement.{key}: requires three values")
            for value in values:
                number(value, f"{name}.placement.{key}")
        number(component["attach"]["station"], f"{name}.attach.station", 0, 1)
        components[name] = component
        annotated[name] = provenance(component, raw)
    assembly_defaults(components, source["components"])
    annotated = {
        name: provenance(component, source["components"][name])
        for name, component in components.items()
    }
    configurations = source.get("configurations", {})
    validate_relationships(components, configurations)
    result = {
        "format": RESOLVED_FORMAT,
        "units": {"length": "m", "angle": "deg"},
        "components": annotated,
        "derived": derived,
        "configurations": configurations,
    }
    if resolved:
        for name, quantities in derived.items():
            for key, expected in quantities.items():
                supplied = source.get("derived", {}).get(name, {}).get(key)
                if supplied is None or not math.isclose(
                    supplied, expected, rel_tol=1e-12, abs_tol=1e-14
                ):
                    raise InputValueError(f"derived.{name}.{key}: inconsistent quantity")
        return deepcopy(data)
    return result


def load_config(path):
    """Read a TOML geometry configuration file and return it validated and resolved.

    Parameters
    ----------
    path : str or os.PathLike
        The TOML file to read.

    Returns
    -------
    dict
        The resolved configuration, as returned by :func:`resolve_config`.
    """
    with Path(path).open("rb") as stream:
        return resolve_config(tomllib.load(stream))
