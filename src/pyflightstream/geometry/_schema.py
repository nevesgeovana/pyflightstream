"""The keys of the geometry TOML, their defaults and their checks.

Pipeline role: pure configuration stage of the geometry package, below
:mod:`pyflightstream.geometry.config`. It holds the number readers, the declared
units, and the readers of every table that is not one component's own
parameters: the ``aircraft``, ``acceptance`` and ``reader`` tables, the
dominance rows, the variants, the configuration registry and the control
surfaces of a lifting surface.

THE DEFAULT FOR AN UNKNOWN KEY IS WARN AND SKIP. A key a table does not know is
left out and reported in the ``warnings`` list the caller returns. The refusals
are the few that would give a wrong surface silently: a missing or unknown
type, a non-finite or out-of-domain number, a cycle, a missing parent, host or
piece, and a key that would create a solid. Each refusal names the key.

NO AIRCRAFT VALUE LIVES HERE. Every default is a generic number a reader can
state without knowing any aircraft; the component names are free text.
"""

from __future__ import annotations

import math
import re
from copy import deepcopy

from pyflightstream._errors import InputValueError
from pyflightstream.geometry._boundary import unit_for

__all__ = [
    "ANGLE_UNITS",
    "LENGTH_UNITS",
    "TYPES",
    "fill",
    "known_keys",
    "number",
    "read_acceptance",
    "read_dominance",
    "read_reader",
    "read_units",
    "read_variants_and_registry",
    "scale_units",
    "stations",
]

TYPES = ("lifting_surface", "body", "fillet", "blister", "propeller", "wing_fuselage_fairing")
LENGTH_UNITS = {"m": 1.0, "mm": 1e-3}
ANGLE_UNITS = {"deg": 1.0, "rad": 180.0 / math.pi}
READER_PROFILES = ("flightstream",)
OPERATIONS = ("auto", "cut", "project")
_VERSION = r"\d+\.\d+\.\d+"


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


def fill(defaults, supplied, path, warnings):
    """Overlay ``supplied`` on ``defaults`` for one small table; warn and skip an unknown key."""
    if not isinstance(supplied, dict):
        raise InputValueError(f"{path}: expected a table")
    result = deepcopy(defaults)
    for key, value in supplied.items():
        if key not in defaults:
            warnings.append(f"{path}.{key}: unknown key, skipped")
        else:
            result[key] = deepcopy(value)
    return result


def known_keys(table, known, path, warnings):
    """Remove from ``table``, in place, each key not in ``known``, warning about each by name."""
    if not isinstance(table, dict):
        raise InputValueError(f"{path}: expected a table")
    for key in sorted(set(table) - set(known), key=str):
        del table[key]
        warnings.append(f"{path}.{key}: unknown key, skipped")
    return table


def read_units(units, warnings):
    """Return the scales to metres and degrees of a declared ``[units]`` table."""
    if not isinstance(units, dict):
        raise InputValueError("units: expected a table")
    for key in sorted(set(units) - {"length", "angle"}):
        warnings.append(f"units.{key}: unknown key, skipped; metres and degrees stay in force")
    length, angle = units.get("length", "m"), units.get("angle", "deg")
    if str(length) not in LENGTH_UNITS or str(angle) not in ANGLE_UNITS:
        raise InputValueError(
            f"units: length is one of {sorted(LENGTH_UNITS)}, angle one of {sorted(ANGLE_UNITS)}"
        )
    return LENGTH_UNITS[length], ANGLE_UNITS[angle]


def scale_units(node, path, length_scale, angle_scale):
    """Return ``node`` converted to metres and degrees, by the unit each dotted path implies.

    A table with ``of`` holds ratios of what it names and is left alone. A key whose name states
    its unit (``tolerance_m``, ``deflection_deg``) is already in that unit, whatever the file
    declares, so it is left alone too.
    """
    if length_scale == 1.0 and angle_scale == 1.0:
        return node
    if isinstance(node, dict):
        if "of" in node:
            return node
        return {
            k: scale_units(v, f"{path}.{k}", length_scale, angle_scale) for k, v in node.items()
        }
    if isinstance(node, list):
        return [scale_units(v, path, length_scale, angle_scale) for v in node]
    if isinstance(node, bool) or not isinstance(node, (int, float)):
        return node
    if path.endswith(("_m", "_mm", "_deg")):
        return node
    factor = {"m": length_scale, "m2": length_scale**2, "deg": angle_scale}.get(unit_for(path), 1.0)
    return node * factor


def read_acceptance(supplied, warnings):
    """Resolve ``[acceptance]`` with range checks; the defaults are generic fractions."""
    defaults = {
        "floor_mm": 0.5,
        "fraction": 0.001,
        "coverage_fraction": 1e-4,
        "coverage_spacing": 1 / 200,
        "area_excess": 1e-4,
    }
    table = fill(defaults, supplied, "acceptance", warnings)
    for key, value in table.items():
        number(value, f"acceptance.{key}", 0, strict=True)
    if table["fraction"] >= 1 or table["coverage_fraction"] >= 1:
        raise InputValueError("acceptance.fraction: expected a fraction below 1")
    return table


def read_reader(supplied, warnings):
    """Resolve ``[reader]``; an unknown profile warns and the default is used."""
    table = fill({"profile": "flightstream"}, supplied, "reader", warnings)
    if table["profile"] not in READER_PROFILES:
        warnings.append(f"reader.profile: unknown {table['profile']!r}, the default is used")
        table["profile"] = "flightstream"
    return table


def _names(value, path, key):
    """Return ``value`` (a name or a list of names) as a list of names."""
    names = [value] if isinstance(value, str) else value
    if not isinstance(names, list) or not names or not all(isinstance(n, str) and n for n in names):
        raise InputValueError(f"{path}.{key}: expected a name or a list of names")
    return list(names)


def _cycle(edges):
    """Return one node of a cycle in a directed graph given as ``{node: set}``, else ``None``."""
    state = {}

    def visit(node):
        state[node] = 1
        for nxt in sorted(edges.get(node, ())):
            if state.get(nxt) == 1 or (nxt not in state and visit(nxt)):
                return True
        state[node] = 2
        return False

    return next((n for n in sorted(edges) if n not in state and visit(n)), None)


def read_dominance(rows, components, warnings):
    """Resolve the ``[[dominance]]`` rows; a cycle or an unknown operation is refused."""
    if not isinstance(rows, list):
        raise InputValueError("dominance: expected an array of tables")
    defaults = {
        "dominant": "",
        "dominated": "",
        "operation": "auto",
        "tolerance_m": 5e-5,
        "contact_deg": 10.0,
    }
    result, edges = [], {}
    for i, raw in enumerate(rows):
        path = f"dominance[{i}]"
        ribbon = raw.get("ribbon") if isinstance(raw, dict) else None
        row = fill({**defaults, "ribbon": None}, raw, path, warnings)
        row["dominant"] = _names(raw.get("dominant"), path, "dominant")
        row["dominated"] = _names(raw.get("dominated"), path, "dominated")
        if row["operation"] not in OPERATIONS:
            raise InputValueError(f"{path}.operation: expected one of {OPERATIONS}")
        number(row["tolerance_m"], f"{path}.tolerance_m", 0, strict=True)
        number(row["contact_deg"], f"{path}.contact_deg", 0, 90, strict=True)
        if ribbon is None:
            del row["ribbon"]
        elif row["operation"] == "cut":
            warnings.append(f"{path}.ribbon: used by project only, skipped")
            del row["ribbon"]
        else:
            row["ribbon"] = known_keys(
                deepcopy(ribbon),
                ("half_height", "extend", "half_span", "tail"),
                f"{path}.ribbon",
                warnings,
            )
        for name in row["dominant"] + row["dominated"]:
            if name not in components:
                warnings.append(f"{path}: unknown component {name!r}")
        for dominant in row["dominant"]:
            edges.setdefault(dominant, set()).update(row["dominated"])
        result.append(row)
    node = _cycle(edges)
    if node is not None:
        raise InputValueError(f"dominance: a cycle through {node!r} leaves no order")
    return result


def _members(raw, name, components, warnings):
    """Normalize the members of one configuration to ``{component, version}`` rows."""
    if not isinstance(raw, list) or not raw:
        raise InputValueError(f"configurations.{name}.members: expected a nonempty list")
    rows = []
    for item in raw:
        row = {"component": item} if isinstance(item, str) else dict(item)
        known_keys(row, ("component", "version"), f"configurations.{name}.members", warnings)
        piece = row.get("component")
        if piece not in components:
            raise InputValueError(f"configurations.{name}: unknown component {piece}")
        version = row.get("version", components[piece]["version"])
        if not isinstance(version, str) or not re.fullmatch(_VERSION, version):
            raise InputValueError(f"configurations.{name}.members.version: expected X.Y.Z")
        rows.append({"component": piece, "version": version})
    if len({r["component"] for r in rows}) != len(rows):
        raise InputValueError(f"configurations.{name}: expected unique nonempty members")
    return rows


def read_variants_and_registry(variants, configurations, components, warnings):
    """Resolve the variants and the configuration registry.

    Returns ``(variants, registry)``: the variant table, ``clean`` always present, and one row
    per configuration with its members, its ``extends`` and the variants it keeps.
    """
    if not isinstance(variants, dict) or not isinstance(configurations, dict):
        raise InputValueError("variants and configurations: expected tables")
    variants = {k: list(v) for k, v in variants.items()}
    variants.setdefault("clean", [])
    surfaces = {
        f"{n}.{s['name']}" for n, c in components.items() for s in c.get("control_surfaces", [])
    }
    for variant, entries in variants.items():
        if not isinstance(entries, list) or not all(isinstance(e, str) for e in entries):
            raise InputValueError(f"variants.{variant}: expected a list of component.surface")
        for entry in entries:
            if entry not in surfaces:
                warnings.append(f"variants.{variant}: {entry!r} names no control surface, skipped")
        entries[:] = [entry for entry in entries if entry in surfaces]
    raw = {k: ({"members": v} if isinstance(v, list) else v) for k, v in configurations.items()}
    registry = {}
    for name, table in raw.items():
        table = fill(
            {"members": [], "extends": "", "variants": None},
            table,
            f"configurations.{name}",
            warnings,
        )
        registry[name] = {
            "members": _members(table["members"], name, components, warnings),
            "extends": table["extends"],
            "variants": table["variants"],
        }
    return variants, _flatten(registry, variants, warnings)


def _inherited(registry, name, done):
    """Return the members of a configuration: the parent's, then its own, one per component."""
    if name not in done:
        row, merged = registry[name], []
        if row["extends"]:
            merged = [dict(m) for m in _inherited(registry, row["extends"], done)]
        index = {m["component"]: i for i, m in enumerate(merged)}
        for member in row["members"]:
            if member["component"] in index:
                merged[index[member["component"]]] = dict(member)
            else:
                merged.append(dict(member))
        done[name] = merged
    return done[name]


def _flatten(registry, variants, warnings):
    """Append inherited members, refuse a cycle or a missing parent, resolve the variant lists."""
    edges = {}
    for name, row in registry.items():
        parent = row["extends"]
        if parent and parent not in registry:
            raise InputValueError(f"configurations.{name}.extends: missing configuration {parent}")
        edges[name] = {parent} if parent else set()
    node = _cycle(edges)
    if node is not None:
        raise InputValueError(f"configurations.{node}.extends: a cycle")
    done, result = {}, {}
    for name, row in registry.items():
        kept = sorted(variants) if row["variants"] is None else list(row["variants"])
        for variant in [v for v in kept if v not in variants]:
            warnings.append(f"configurations.{name}.variants: unknown {variant!r}, skipped")
        result[name] = {
            "members": _inherited(registry, name, done),
            "extends": row["extends"],
            "variants": [v for v in kept if v in variants],
        }
    return result
