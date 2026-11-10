"""Private input vocabulary of a geometry configuration: the names a user writes.

Pipeline role: private helper of :mod:`pyflightstream.geometry.config`. A fresh configuration is
written with the key names of the published geometry input form (``[surface]``, ``[planform]``
with ``sref_m2``, ``aspect_ratio`` and ``taper`` or ``semispan_mm`` and the two chords,
``[[stations]]``, ``[cap]``, ``[[control]]``, ``[[engine]]``). This module reads those names and
hands the resolver the quantities it works with, in metres and degrees. The names the first
drafts used were never released: each is refused with a message naming its replacement, never
read as an alias. A resolved configuration is not translated; it already holds resolved names.
"""

from __future__ import annotations

from pyflightstream._errors import InputValueError
from pyflightstream.geometry._schema import known_keys, number

__all__ = ["adopt_surface_file", "apply_engines", "translate_lifting"]

#: Old planform names, with the replacement the refusal names.
_RENAMED_PLANFORM = {
    "span": "semispan_mm (half the span, tip cap included) or sref_m2 with aspect_ratio",
    "height": "semispan_mm",
    "area": "sref_m2",
    "root_chord": "root_chord_mm",
    "tip_chord": "tip_chord_mm",
    "sweep": "le_sweep_deg",
    "dihedral": "dihedral_deg",
    "orientation": "surface.span_axis",
    "twist_axis": "surface.twist_axis",
}
_RENAMED_TOP = {
    "tip_cap": "cap (with type in place of kind)",
    "control_surfaces": "control (with eta = [inner, outer] in place of eta_in and eta_out)",
}
_SET_A = ("semispan_mm", "root_chord_mm", "tip_chord_mm")
_SURFACE_KEYS = ("name", "span_axis", "section_type", "model", "twist_axis")
_STATION_KEYS = ("eta", "twist_deg", "te_thickness_mm", "section")
_CONTROL_KEYS = ("name", "kind", "eta", "chord_ratio", "cove", "hinge_line")
_ENGINE_KEYS = ("name", "eta_axis", "half_width_mm")
_PLANFORM_TO_INTERNAL = {
    "sref_m2": ("area", 1.0),
    "root_chord_mm": ("root_chord", 1e-3),
    "tip_chord_mm": ("tip_chord", 1e-3),
    "le_sweep_deg": ("sweep", 1.0),
    "dihedral_deg": ("dihedral", 1.0),
}
#: Keys of the proposal no verb implements yet: each is warned about and skipped.
_NOT_IMPLEMENTED = {
    "bay": "kinked planforms by bays are not implemented, the single trapezoid is built",
}


def adopt_surface_file(source):
    """Return ``source`` with a ``[surface]`` or ``[body]`` file read as one component.

    A file of the published form holds no ``type``: ``[surface]`` makes it a lifting surface and
    ``[body]`` a body. The file-level tables (``units``, ``aircraft``, ``acceptance``,
    ``reader``) stay at the file level; every other table belongs to the component.
    """
    if "components" in source or "type" in source:
        return source
    kind = "lifting_surface" if "surface" in source else "body" if "body" in source else None
    if kind is None:
        return source
    file_level = ("units", "aircraft", "acceptance", "reader", "dominance")
    component = {k: v for k, v in source.items() if k not in file_level}
    head = component.get("surface" if kind == "lifting_surface" else "body")
    name = head.get("name", "COMPONENT") if isinstance(head, dict) else "COMPONENT"
    if kind == "body":
        body = component.pop("body")
        component.update({k: v for k, v in body.items() if k not in ("type", "name")})
    component["type"] = kind
    adopted = {k: v for k, v in source.items() if k in file_level}
    adopted["components"] = {str(name): component}
    return adopted


def _refuse_renamed(label, table, renamed):
    """Refuse each old key of ``table`` naming its replacement."""
    if not isinstance(table, dict):
        return
    for old, new in renamed.items():
        if old in table:
            raise InputValueError(f"{label}.{old}: renamed to {new}; the old name is refused")


def _planform_set(name, planform):
    """Refuse a planform that mixes the two complete sets, naming the redundant keys."""
    a = [k for k in _SET_A if k in planform]
    b = [k for k in ("sref_m2", "aspect_ratio") if k in planform]
    if a and b:
        raise InputValueError(
            f"{name}.planform: one set only, {', '.join(a)} and {', '.join(b)} are redundant "
            "together; give sref_m2, aspect_ratio and taper, or semispan_mm, root_chord_mm and "
            "tip_chord_mm"
        )


def _translate_planform(name, raw, vertical):
    """Replace the planform names by the quantities the resolver reads, in metres and degrees."""
    planform = raw.get("planform")
    if not isinstance(planform, dict):
        return
    _planform_set(name, planform)
    for key in (*_PLANFORM_TO_INTERNAL, "semispan_mm"):
        if key in planform:
            positive = None if key.endswith("_deg") else 0
            value = number(planform.pop(key), f"{name}.planform.{key}", positive, strict=True)
            planform[_internal_name(key, vertical)] = value * _factor(key, vertical)
    if "root_le_mm" in planform:
        _root_le(name, raw, planform.pop("root_le_mm"))


def _internal_name(key, vertical):
    """Return the resolver's name of a planform key; a fin keeps its one-sided height."""
    if key == "semispan_mm":
        return "height" if vertical else "span"
    return _PLANFORM_TO_INTERNAL[key][0]


def _factor(key, vertical):
    """Return the factor from the input unit to the resolver's: a semispan becomes a span."""
    if key == "semispan_mm":
        return 1e-3 if vertical else 2e-3
    return _PLANFORM_TO_INTERNAL[key][1]


def _root_le(name, raw, point):
    """Place the component at the root leading edge ``root_le_mm``."""
    if not isinstance(point, list) or len(point) != 3:
        raise InputValueError(f"{name}.planform.root_le_mm: requires three values")
    for value in point:
        number(value, f"{name}.planform.root_le_mm")
    placement = raw.setdefault("placement", {})
    if "translation" in placement:
        raise InputValueError(
            f"{name}.planform.root_le_mm: given together with placement.translation"
        )
    placement["translation"] = [v * 1e-3 for v in point]


def _translate_surface(name, raw, warnings):
    """Read ``[surface]``; return whether the span axis is vertical."""
    surface = raw.pop("surface", None)
    if surface is None:
        return False
    known_keys(surface, _SURFACE_KEYS, f"{name}.surface", warnings)
    if "name" in surface:
        warnings.append(f"{name}.surface.name: the component name is the table key, skipped")
    for key, accepted in (("section_type", "full"), ("model", "full")):
        _accept_or_skip(name, surface, key, accepted, warnings)
    axis = surface.get("span_axis", "y")
    if axis not in ("y", "z"):
        raise InputValueError(f"{name}.surface.span_axis: expected y or z")
    if "twist_axis" in surface:
        raw.setdefault("planform", {})["twist_axis"] = surface["twist_axis"]
    if axis == "z":
        raw.setdefault("planform", {})["orientation"] = "vertical"
    return axis == "z"


def _accept_or_skip(name, surface, key, accepted, warnings):
    """Accept the implemented value of a ``surface`` key and skip the other choice by name."""
    if key not in surface:
        return
    value = surface[key]
    if value not in ("full", "half"):
        raise InputValueError(f"{name}.surface.{key}: expected full or half")
    if value != accepted:
        warnings.append(f"{name}.surface.{key}: {value!r} is not implemented, skipped")


def _translate_cap(name, raw, warnings):
    """Read ``[cap]`` as the tip cap; ``type`` is the kind, a template has no reader yet."""
    cap = raw.pop("cap", None)
    if cap is None:
        return
    if not isinstance(cap, dict):
        raise InputValueError(f"{name}.cap: expected a table")
    cap = dict(cap)
    if "template" in cap:
        cap.pop("template")
        warnings.append(f"{name}.cap.template: cap templates are not implemented, skipped")
    kind = cap.pop("type", None)
    if kind == "original":
        warnings.append(f"{name}.cap.type: 'original' needs a template, not implemented, skipped")
    elif kind is not None:
        cap["kind"] = kind
    raw["tip_cap"] = cap


def _station_section(path, section, warnings):
    """Return the section item of a station, or ``None`` when it cannot be read yet."""
    if not isinstance(section, dict) or "kind" not in section:
        raise InputValueError(f"{path}.section.kind: required")
    kind = section["kind"]
    body = {k: v for k, v in section.items() if k != "kind"}
    if kind == "naca":
        return {"naca": body.get("naca")}
    if kind == "coords":
        return {"file": body.get("file")}
    if kind == "cst":
        return {k: v for k, v in body.items() if k in ("cst_upper", "cst_lower", "te")}
    if kind != "bspline":
        raise InputValueError(f"{path}.section.kind: expected bspline, naca, cst or coords")
    if "file" in body:
        warnings.append(f"{path}.section.file: a B-spline section file is not read yet, skipped")
        return None
    return {"bspline": body}


def _station_twist(name, raw, stations, warnings):
    """Map the stations' ``twist_deg`` to the linear twist law; other cases skip by name."""
    given = [(i, s) for i, s in enumerate(stations) if "twist_deg" in s]
    if not given:
        return
    planform = raw.setdefault("planform", {})
    if "incidence" in planform or "tip_twist" in planform:
        raise InputValueError(f"{name}.stations.twist_deg: given together with planform.incidence")
    for _, s in given:
        number(s["twist_deg"], f"{name}.stations.twist_deg")
    first, last = given[0][1], given[-1][1]
    if first["eta"] != 0:
        warnings.append(f"{name}.stations.twist_deg: needs a station at eta 0, skipped")
    elif len(given) == 1:
        planform["incidence"] = first["twist_deg"]
    elif len(given) == 2 and last["eta"] == 1:
        planform["incidence"] = first["twist_deg"]
        planform["tip_twist"] = last["twist_deg"] - first["twist_deg"]
    else:
        warnings.append(
            f"{name}.stations.twist_deg: only a twist at eta 0, or at eta 0 and 1, is "
            "implemented, skipped"
        )


def _translate_stations(name, raw, warnings):
    """Read ``[[stations]]`` as the section items, the twist law and the knot-only breaks."""
    stations = raw.pop("stations", None)
    if stations is None:
        return
    if not isinstance(stations, list) or not all(isinstance(s, dict) for s in stations):
        raise InputValueError(f"{name}.stations: expected a list of tables")
    for i, s in enumerate(stations):
        known_keys(s, _STATION_KEYS, f"{name}.stations[{i}]", warnings)
        number(s.get("eta"), f"{name}.stations[{i}].eta", 0, 1)
        if "te_thickness_mm" in s:
            s.pop("te_thickness_mm")
            warnings.append(
                f"{name}.stations[{i}].te_thickness_mm: per-station trailing edge "
                "thickness is not implemented, skipped"
            )
    _station_twist(name, raw, stations, warnings)
    items, breaks = [], []
    for i, s in enumerate(stations):
        if "section" not in s:
            breaks.append(s["eta"])
            continue
        item = _station_section(f"{name}.stations[{i}]", s["section"], warnings)
        if item is not None:
            items.append({"eta": s["eta"], **item})
    if items:
        raw.setdefault("sections", {})["items"] = items
    if breaks:
        raw.setdefault("planform", {})["breaks"] = breaks


def _translate_control(name, raw, warnings):
    """Read ``[[control]]`` as the control surfaces; ``eta`` is the span interval."""
    table = raw.pop("control", None)
    if table is None:
        return
    if not isinstance(table, list) or not all(isinstance(c, dict) for c in table):
        raise InputValueError(f"{name}.control: expected a list of tables")
    surfaces = []
    for i, source in enumerate(table):
        path = f"{name}.control[{i}]"
        _refuse_renamed(path, source, {"eta_in": "eta = [inner, outer]", "eta_out": "eta"})
        surface = _control_surface(path, source, warnings)
        if surface is not None:
            surfaces.append(surface)
    raw["control_surfaces"] = surfaces


def _control_surface(path, source, warnings):
    """Return one control surface in the resolver's form, or ``None`` when it must be skipped."""
    others = {k: v for k, v in source.items() if k not in _CONTROL_KEYS}
    surface = {k: v for k, v in source.items() if k in ("name", "kind", "chord_ratio", "cove")}
    surface.update(others)
    eta = source.get("eta")
    if not isinstance(eta, list) or len(eta) != 2:
        raise InputValueError(f"{path}.eta: expected [inner, outer]")
    surface["eta_in"], surface["eta_out"] = eta
    if source.get("kind") == "plain":
        surface["kind"] = "plain_flap"
    if "hinge_line" in source:
        warnings.append(f"{path}.hinge_line: not implemented, skipped")
    cove = source.get("cove")
    if source.get("kind") == "fowler" and (
        cove is None or (isinstance(cove, dict) and "from" in cove)
    ):
        warnings.append(
            f"{path}.cove: a fowler flap without a stated cove (a tabulated cove is not "
            f"implemented); the flap {source.get('name', '')!r} is skipped"
        )
        return None
    return surface


def translate_lifting(name, raw, warnings, resolved):
    """Translate a fresh lifting-surface input to the resolver's names, in place.

    A resolved input is left alone. Every old name is refused with its replacement.
    """
    if resolved:
        return
    _refuse_renamed(name, raw, _RENAMED_TOP)
    _refuse_renamed(f"{name}.planform", raw.get("planform"), _RENAMED_PLANFORM)
    vertical = _translate_surface(name, raw, warnings)
    _translate_planform(name, raw, vertical)
    _translate_cap(name, raw, warnings)
    _translate_stations(name, raw, warnings)
    _translate_control(name, raw, warnings)
    for key, note in _NOT_IMPLEMENTED.items():
        if raw.pop(key, None) is not None:
            warnings.append(f"{name}.{key}: {note}, skipped")


def apply_engines(name, component, warnings):
    """Turn ``[[engine]]`` into the nacelle bounds of the sections, by semi-span fractions."""
    engines = component.pop("engine", None)
    if engines is None:
        return
    if not isinstance(engines, list) or not all(isinstance(e, dict) for e in engines):
        raise InputValueError(f"{name}.engine: expected a list of tables")
    semispan = component["planform"]["span"] / 2
    bounds = component["sections"].setdefault("nacelle_bounds", [])
    for i, engine in enumerate(engines):
        path = f"{name}.engine[{i}]"
        known_keys(engine, _ENGINE_KEYS, path, warnings)
        axis = number(engine.get("eta_axis"), f"{path}.eta_axis", 0, 1)
        if "half_width_mm" not in engine:
            warnings.append(
                f"{path}.half_width_mm: absent, the bounding sections are not derived, "
                "the engine is skipped"
            )
            continue
        half = number(engine["half_width_mm"], f"{path}.half_width_mm", 0, strict=True)
        reach = half * 1e-3 / semispan
        if not 0 <= axis - reach < axis + reach <= 1:
            raise InputValueError(f"{path}.half_width_mm: the bounds leave the semi-span")
        bounds.append(
            {
                "component": str(engine.get("name", "")),
                "eta_in": axis - reach,
                "eta_out": axis + reach,
            }
        )
