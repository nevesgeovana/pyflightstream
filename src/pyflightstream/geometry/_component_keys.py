"""Checks of the component keys that the first geometry release did not have.

Pipeline role: pure configuration stage, called by
:mod:`pyflightstream.geometry.config` after a component's defaults and supplied
values are merged. It checks the keys common to every component, the section
items, the physical section form, the tip cap and control-surface tables of a
lifting surface, the rear forms of a body, and the fillet and blister
components. A key it does not know was skipped with a warning before this point;
what it refuses is named in the message with the key's dotted path.
"""

from __future__ import annotations

import math
import re

from pyflightstream._errors import InputValueError
from pyflightstream.geometry._schema import number, stations

__all__ = [
    "check_blister",
    "check_body_extras",
    "check_common",
    "check_fillet",
    "check_lifting_extras",
]

SURFACE_KINDS = ("aileron", "elevator", "rudder", "plain_flap", "fowler")
_CAP_KINDS = ("flat", "rounded", "ridged", "exact_loft", "none")
_NACA = re.compile(r"NACA(?:\d{4}|\d{5})")


def check_common(name, component, warnings):
    """Check ``original``, ``creases`` and ``open_findings`` of any component."""
    if not isinstance(component["original"], str):
        raise InputValueError(f"{name}.original: expected file#component text")
    if not isinstance(component["open_findings"], list) or not all(
        isinstance(f, str) for f in component["open_findings"]
    ):
        raise InputValueError(f"{name}.open_findings: expected a list of text")
    for i, crease in enumerate(component["creases"]):
        if not isinstance(crease, dict) or not isinstance(crease.get("at"), str):
            raise InputValueError(f"{name}.creases[{i}]: expected at and deg")
        number(crease.get("deg"), f"{name}.creases[{i}].deg", 0, 180)
        for key in set(crease) - {"at", "deg"}:
            warnings.append(f"{name}.creases[{i}].{key}: unknown key, skipped")


def _item_form(name, i, item):
    """Return which form a section item takes: ``naca``, ``cst`` or ``file``."""
    path = f"{name}.sections.items[{i}]"
    forms = [k for k in ("naca", "cst_upper", "file") if k in item]
    if len(forms) != 1:
        raise InputValueError(f"{path}: expected one of naca, cst_upper with cst_lower, file")
    number(item.get("eta"), f"{path}.eta", 0, 1)
    if forms[0] == "naca":
        if not isinstance(item["naca"], str) or not _NACA.fullmatch(f"NACA{item['naca']}"):
            raise InputValueError(f"{path}.naca: expected a NACA designation")
    elif forms[0] == "cst_upper":
        for key in ("cst_upper", "cst_lower"):
            values = item.get(key)
            if not isinstance(values, list) or len(values) < 2:
                raise InputValueError(f"{path}.{key}: expected at least two coefficients")
            for v in values:
                number(v, f"{path}.{key}")
        number(item.get("te", 0.0), f"{path}.te", 0, 0.1)
    elif not isinstance(item["file"], str) or not item["file"]:
        raise InputValueError(f"{path}.file: expected a path")
    return forms[0]


def _check_sections(name, component, raw):
    """Resolve ``sections.items`` into the legacy airfoil and station lists, check the rest."""
    section = component["sections"]
    if section["form"] != "cst":
        raise InputValueError(
            f"{name}.sections.form: only cst is stored; cubic waits for the owner's decision"
        )
    physical = section.get("physical")
    if physical is not None and ("airfoils" in raw or "items" in raw):
        raise InputValueError(f"{name}.sections.physical: given together with naca sections")
    if physical is not None:
        for key in ("nose_radius", "boat_tail_deg", "te_thickness", "thickness_at"):
            if key in physical:
                number(physical[key], f"{name}.sections.physical.{key}", 0)
    items = section["items"]
    if not items:
        return
    forms = [_item_form(name, i, item) for i, item in enumerate(items)]
    stations([item["eta"] for item in items], f"{name}.sections.items", 1)
    section["eta"] = [item["eta"] for item in items]
    section["airfoils"] = [
        f"NACA{item['naca']}" if f == "naca" else "" for item, f in zip(items, forms, strict=True)
    ]


def _check_surface(name, i, surface, span):
    """Check one control surface table of a lifting surface (C.7)."""
    path = f"{name}.control_surfaces[{i}]"
    if not isinstance(surface.get("name"), str) or not surface["name"]:
        raise InputValueError(f"{path}.name: required")
    if surface["kind"] not in SURFACE_KINDS:
        raise InputValueError(f"{path}.kind: expected one of {SURFACE_KINDS}")
    for key in ("eta_in", "eta_out"):
        if surface.get(key) != "host":
            number(surface.get(key), f"{path}.{key}", 0, 1)
    if (
        "host" not in (surface["eta_in"], surface["eta_out"])
        and surface["eta_in"] >= surface["eta_out"]
    ):
        raise InputValueError(f"{path}.eta_in: overlaps or inverts the span interval")
    number(surface["chord_ratio"], f"{path}.chord_ratio", 0.05, 0.5)
    if surface["span_basis"] not in ("semi_span", "exposed"):
        raise InputValueError(f"{path}.span_basis: expected semi_span or exposed")
    if surface["gap_closure"] not in ("end_faces", "strip"):
        raise InputValueError(
            f"{path}.gap_closure: expected end_faces or strip, open leaves free edges"
        )
    number(surface["gap_span"], f"{path}.gap_span", 0, 0.05)
    number(surface["gap_chord"], f"{path}.gap_chord", 0)
    deflections = surface["deflection_deg"]
    if not isinstance(deflections, list) or not deflections:
        raise InputValueError(f"{path}.deflection_deg: expected a list")
    for d in deflections:
        number(d, f"{path}.deflection_deg", -89, 89)
    if surface["kind"] == "fowler":
        _check_fowler(path, surface, deflections)
    else:
        for key in ("cove", "nested_dz_pct", "clearance_pct", "kinematics", "nose"):
            if key in surface:
                warnings_key = f"{path}.{key}"
                surface.pop(key)
                surface.setdefault("_skipped", []).append(warnings_key)
    if any(d != 0 for d in deflections) and not math.isfinite(span):
        raise InputValueError(f"{path}: the host span is not finite")


def _check_fowler(path, surface, deflections):
    """Check the extra keys of a Fowler flap; kinematics are required for a nonzero deflection."""
    cove = surface.get("cove", {})
    if "p3" not in cove:
        raise InputValueError(f"{path}.cove.p3: required for a fowler flap")
    number(cove["p3"].get("eta"), f"{path}.cove.p3.eta", 0, 1)
    number(cove["p3"].get("z_over_c"), f"{path}.cove.p3.z_over_c")
    number(cove.get("wall_x", 0.745), f"{path}.cove.wall_x", 0, 1, strict=True)
    number(cove.get("lip_x", 0.96), f"{path}.cove.lip_x", 0, 1, strict=True)
    number(surface.get("clearance_pct", 0.10), f"{path}.clearance_pct", 0)
    number(surface.get("nested_dz_pct", -0.145), f"{path}.nested_dz_pct")
    kinematics = surface.get("kinematics", [])
    needed = {d for d in deflections if d != 0}
    given = {row.get("deflection_deg") for row in kinematics}
    for row in kinematics:
        for key in ("pivot_x", "pivot_z", "gap_pct", "overlap_pct"):
            number(row.get(key), f"{path}.kinematics.{key}")
    if needed - given:
        raise InputValueError(
            f"{path}.kinematics: required for deflection {sorted(needed - given)}"
        )


def check_lifting_extras(name, component, raw, warnings, findings):
    """Check the C.2 and C.3 keys added to a lifting surface; fills sections from ``items``."""
    check_common(name, component, warnings)
    _check_sections(name, component, raw.get("sections", {}))
    if component["trailing_edge"] == "collapsed":
        warnings.append(f"{name}.trailing_edge: collapse is a mesh key, blunt is kept")
        component["trailing_edge"] = "blunt"
    if component["trailing_edge"] != "blunt":
        raise InputValueError(f"{name}.trailing_edge: expected blunt")
    cap = component["tip_cap"]
    if cap["kind"] not in _CAP_KINDS:
        raise InputValueError("tip_cap.kind: expected flat, rounded, ridged, exact_loft or none")
    for key in ("sections", "control_points"):
        if not isinstance(cap[key], int) or isinstance(cap[key], bool) or cap[key] < 2:
            raise InputValueError(f"tip_cap.{key}: expected an integer of at least 2")
    for i, bound in enumerate(component["sections"].get("nacelle_bounds", [])):
        path = f"{name}.sections.nacelle_bounds[{i}]"
        number(bound.get("eta_in"), f"{path}.eta_in", 0, 1)
        number(bound.get("eta_out"), f"{path}.eta_out", 0, 1)
        if bound["eta_in"] >= bound["eta_out"]:
            raise InputValueError(f"{path}.eta_in: expected below eta_out")
        if not isinstance(bound.get("component"), str):
            raise InputValueError(f"{path}.component: required")
    names = [s.get("name") for s in component["control_surfaces"]]
    if len(set(names)) != len(names):
        raise InputValueError(f"{name}.control_surfaces.name: duplicate")
    for i, surface in enumerate(component["control_surfaces"]):
        _check_surface(name, i, surface, component["planform"]["span"])
        for skipped in surface.pop("_skipped", []):
            warnings.append(f"{skipped}: used by fowler only, skipped")
    findings.extend(f"{name}: {text}" for text in component["open_findings"])


def check_body_extras(name, component, warnings, findings):
    """Check ``rings_file``, the rear forms and ``continuity`` of a body."""
    check_common(name, component, warnings)
    findings.extend(f"{name}: {text}" for text in component["open_findings"])
    if component["continuity"] != "G1":
        raise InputValueError(
            f"{name}.continuity: expected G1; the one exception is a declared crease"
        )
    rear = component["rear"]
    if isinstance(rear, dict):
        form = rear.get("boat_tail")
        if set(rear) != {"boat_tail"} or not isinstance(form, dict):
            raise InputValueError(f"{name}.rear: expected pole, base or a boat_tail table")
        number(form.get("x_cut"), f"{name}.rear.boat_tail.x_cut", 0, 1, strict=True)
        number(form.get("base_height"), f"{name}.rear.boat_tail.base_height", 0)
        number(
            form.get("angle_limit_deg"),
            f"{name}.rear.boat_tail.angle_limit_deg",
            0,
            90,
            strict=True,
        )
    elif rear not in ("base", "pole"):
        raise InputValueError(f"{name}.rear: expected pole, base or a boat_tail table")
    if not isinstance(component["rings_file"], str):
        raise InputValueError(f"{name}.rings_file: expected a path")


def check_fillet(name, component, warnings, findings):
    """Check a fillet component: two hosts, a patch count and the bands."""
    check_common(name, component, warnings)
    findings.extend(f"{name}: {text}" for text in component["open_findings"])
    hosts = component["hosts"]
    if len(hosts) != 2 or len(set(hosts)) != 2 or not all(isinstance(h, str) and h for h in hosts):
        raise InputValueError(f"{name}.hosts: requires two distinct host names")
    if not isinstance(component["patches"], int) or component["patches"] < 4:
        raise InputValueError(f"{name}.patches: at least 4 required")
    for key in ("wing_band", "host_band"):
        number(component[key], f"{name}.{key}", 0, strict=True)
    if not isinstance(component["extend_lower_to_te"], bool):
        raise InputValueError(f"{name}.extend_lower_to_te: expected true or false")
    for key in component.get("laws", {}).items():
        if key not in ("radius", "handle", "setback"):
            warnings.append(f"{name}.laws.{key}: unknown key, skipped")


def check_blister(name, component, warnings, findings):
    """Check a blister component: a host, increasing stations and a depth."""
    check_common(name, component, warnings)
    findings.extend(f"{name}: {text}" for text in component["open_findings"])
    if not component["host"]:
        raise InputValueError(f"{name}.host: required")
    x = component.get("stations", {}).get("x")
    if x is None:
        raise InputValueError(f"{name}.stations.x: required")
    stations(x, f"{name}.stations.x", 2, -math.inf, math.inf)
    depth = component.get("profile", {}).get("depth")
    if depth is None:
        raise InputValueError(f"{name}.profile.depth: required")
    number(depth, f"{name}.profile.depth", 0, strict=True)
    if component["sections_file"] == "" and "sections" not in component:
        component["sections"] = {"kind": "superellipse"}
    if component["tips"] != "pole":
        warnings.append(f"{name}.tips: only pole exists, pole is used")
        component["tips"] = "pole"
