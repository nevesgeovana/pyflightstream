"""Generating a named IGES file from a resolved parametric configuration (FR-1220).

Pipeline role: the workspace row of the geometry generation. The pure geometry
package gives the placed patches of every component and the inside predicate of
each; this module adds them to one OpenCASCADE model, fragments them against
each other, drops the faces buried in another component, audits the edges
(free edges off the symmetry plane, non-manifold edges, the transition ring where
components cross) and writes one IGES file whose faces carry one 406 form 15 NAME
per component. Coordinates are metres and the file declares them so.

gmsh ships with the optional ``gmsh`` extra; :func:`generate_iges` refuses with
the package's missing-extra refusal, with the install command, when it is absent.
The pure geometry package never imports this module.
"""

from __future__ import annotations

import re
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import numpy as np

from pyflightstream._errors import InputValueError
from pyflightstream.geometry.config import load_config, resolve_config
from pyflightstream.geometry.generation import assembly_regions, generate_components
from pyflightstream.geometry.patch import Patch
from pyflightstream.workspace._gmsh import session

__all__ = ["add_occ_patch", "assemble", "generate_iges", "write_iges"]


def add_occ_patch(occ: Any, patch: Patch) -> int:
    """Add one patch to the model as an OpenCASCADE B-spline surface and return its tag.

    No initialization, export or global model change happens here.
    """
    controls = np.asarray(patch.controls)
    points = [occ.addPoint(*point) for point in controls.transpose(1, 0, 2).reshape(-1, 3)]
    return occ.addBSplineSurface(
        points,
        controls.shape[0],
        degreeU=patch.degree_u,
        degreeV=patch.degree_v,
        knotsU=list(patch.knots_u),
        knotsV=list(patch.knots_v),
        multiplicitiesU=list(patch.multiplicities_u),
        multiplicitiesV=list(patch.multiplicities_v),
    )


def fragment_surfaces(model, groups):
    entries = [(name, tag) for name, tags in groups.items() for tag in tags]
    entities = [(2, tag) for _, tag in entries]
    _, mapping = model.occ.fragment(entities[:1], entities[1:], removeObject=True, removeTool=True)
    model.occ.synchronize()
    result = {name: set() for name in groups}
    for (name, _), descendants in zip(entries, mapping, strict=True):
        result[name].update(tag for dim, tag in descendants if dim == 2)
    return result


def interior_point(model, tag):
    centre = np.asarray(model.occ.getCenterOfMass(2, tag))
    bounds = model.getParametrizationBounds(2, tag)
    candidates = []
    for u in np.linspace(bounds[0][0], bounds[1][0], 11)[1:-1]:
        for v in np.linspace(bounds[0][1], bounds[1][1], 11)[1:-1]:
            if model.isInside(2, tag, [u, v], parametric=True):
                candidates.append(np.asarray(model.getValue(2, tag, [u, v])))
    if not candidates:
        point, _ = model.getClosestPoint(2, tag, centre.tolist())
        return np.asarray(point)
    return min(candidates, key=lambda point: np.linalg.norm(point - centre))


def exposed_faces(model, groups, inside):
    result, remove = {}, set()
    for name, tags in groups.items():
        result[name] = []
        for tag in sorted(tags):
            point = interior_point(model, tag)
            if any(predicate(point) for other, predicate in inside.items() if other != name):
                remove.add(tag)
            else:
                result[name].append(tag)
    retained = {tag for tags in result.values() for tag in tags}
    remove.difference_update(retained)
    model.occ.remove([(2, tag) for tag in sorted(remove)], recursive=False)
    model.occ.synchronize()
    return result


def edge_audit(model, groups, tolerance=1e-7, intersection_owners=None):
    surfaces = {tag for tags in groups.values() for tag in tags}
    free, nonmanifold, shared, nonquad = [], [], [], []
    edges = set()
    for tag in surfaces:
        boundary = model.getBoundary([(2, tag)], oriented=False)
        if len(boundary) != 4:
            nonquad.append({"surface": tag, "edges": len(boundary)})
        edges.update(edge for _, edge in boundary)
    owners = {tag: sorted(name for name, tags in groups.items() if tag in tags) for tag in surfaces}
    intersections, ring, details = [], set(), []
    for edge in sorted(edges):
        parents, _ = model.getAdjacencies(1, edge)
        parents = set(parents).intersection(surfaces)
        components = sorted({name for tag in parents for name in owners[tag]})
        original_components = (intersection_owners or {}).get(edge, components)
        if len(original_components) > 1:
            intersections.append(
                {
                    "edge": edge,
                    "components": original_components,
                    "faces": sorted(int(tag) for tag in parents),
                    "shared": len(parents) == 2,
                }
            )
            ring.update(parents)
        if len(parents) == 2:
            shared.append(edge)
        elif len(parents) != 1:
            nonmanifold.append(edge)
        else:
            bounds = model.getParametrizationBounds(1, edge)
            xyz = np.asarray(
                model.getValue(1, edge, np.linspace(bounds[0][0], bounds[1][0], 17))
            ).reshape(-1, 3)
            if np.max(abs(xyz[:, 1])) > tolerance:
                free.append(edge)
        if edge in free or edge in nonmanifold:
            details.append(
                {
                    "edge": edge,
                    "kind": "free" if edge in free else "nonmanifold",
                    "location_m": list(model.occ.getCenterOfMass(1, edge)),
                    "length_m": model.occ.getMass(1, edge),
                    "components": components,
                    "faces": [
                        {
                            "surface": int(tag),
                            "components": owners[tag],
                            "area_m2": model.occ.getMass(2, int(tag)),
                        }
                        for tag in sorted(parents)
                    ],
                }
            )
    return {
        "free_edges_off_symmetry": free,
        "nonmanifold_edges": nonmanifold,
        "shared_edges": shared,
        "nonquadrilateral_faces": nonquad,
        "intersection_curves": intersections,
        "unshared_intersection_curves": [row for row in intersections if not row["shared"]],
        "transition_ring_faces": sorted(int(tag) for tag in ring),
        "transition_ring_area_m2": sum(model.occ.getMass(2, int(tag)) for tag in ring),
        "non_ring_nonquadrilateral_faces": [row for row in nonquad if row["surface"] not in ring],
        "defect_locations": details,
    }


def assemble(model, groups, inside):
    fragmented = fragment_surfaces(model, groups)
    intersection_owners = {}
    for name, tags in fragmented.items():
        for tag in tags:
            for _, edge in model.getBoundary([(2, tag)], oriented=False):
                intersection_owners.setdefault(edge, set()).add(name)
    intersection_owners = {
        edge: sorted(names) for edge, names in intersection_owners.items() if len(names) > 1
    }
    exposed = exposed_faces(model, fragmented, inside)
    # A tangent contact can map one descendant to more than one source. Keep
    # that face once. Later configuration members own coincident overlays.
    owner = {tag: name for name, tags in exposed.items() for tag in tags}
    overlaps = [
        {
            "surface": tag,
            "sources": [name for name, tags in exposed.items() if tag in tags],
            "owner": name,
            "area_m2": model.occ.getMass(2, tag),
        }
        for tag, name in owner.items()
        if sum(tag in tags for tags in exposed.values()) > 1
    ]
    exposed = {name: [tag for tag in tags if owner[tag] == name] for name, tags in exposed.items()}
    audit = edge_audit(model, exposed, intersection_owners=intersection_owners)
    audit["coincident_ownership"] = overlaps
    audit["component_faces"] = exposed
    return exposed, audit


def tokens(payload):
    result, i = [], 0
    while i < len(payload):
        while i < len(payload) and payload[i].isspace():
            i += 1
        match = re.match(r"(\d+)H", payload[i:])
        if match:
            end = i + len(match[0]) + int(match[1])
            result.append(payload[i:end])
            i = end
            while payload[i].isspace():
                i += 1
        else:
            end = i
            while end < len(payload) and payload[end] not in ",;":
                end += 1
            result.append(payload[i:end].strip())
            i = end
        if i == len(payload) or payload[i] == ";":
            break
        i += 1
    return result


def read_iges(path):
    lines = Path(path).read_text(encoding="ascii").splitlines()
    sections = {
        key: [line for line in lines if len(line) == 80 and line[72] == key] for key in "SGDPT"
    }
    parameters = sections["P"]
    entities = []
    for first, second in zip(sections["D"][::2], sections["D"][1::2], strict=True):
        d1 = [first[i : i + 8] for i in range(0, 72, 8)]
        d2 = [second[i : i + 8] for i in range(0, 72, 8)]
        start, count = int(d1[1]) - 1, int(d2[3])
        payload = "".join(line[:64] for line in parameters[start : start + count])
        entities.append(
            {
                "id": int(first[73:]),
                "d1": d1,
                "d2": d2,
                "parameters": tokens(payload),
                "type": int(d1[0]),
            }
        )
    return {
        "start": [line[:72] for line in sections["S"]],
        "global": tokens("".join(line[:72] for line in sections["G"])),
        "entities": entities,
    }


def surface_key(document, entity):
    by_id = {e["id"]: e for e in document["entities"]}

    def geometry(row):
        values = list(row["parameters"])
        kind = row["type"]
        if kind == 144:
            references = [1, *range(4, 5 + int(values[3]))]
        elif kind == 142:
            references = [2, 3, 4]
        elif kind == 102:
            references = list(range(2, 2 + int(values[1])))
        else:
            references = []
        for index in references:
            pointer = int(values[index])
            values[index] = geometry(by_id[pointer]) if pointer else ()
        transform = int(row["d1"][6])
        return (tuple(values), geometry(by_id[transform]) if transform else ())

    return geometry(entity)


def component_keys(gmsh, groups, directory):
    entities = gmsh.model.getEntities()
    visibility = [(dim, tag, gmsh.model.getVisibility(dim, tag)) for dim, tag in entities]
    old = gmsh.option.getNumber("Geometry.OCCExportOnlyVisible")
    keys = {}
    try:
        gmsh.option.setNumber("Geometry.OCCExportOnlyVisible", 1)
        for index, (name, tags) in enumerate(groups.items()):
            gmsh.model.setVisibility(entities, 0)
            gmsh.model.setVisibility([(2, tag) for tag in tags], 1, recursive=True)
            path = directory / f"component-{index}.igs"
            gmsh.write(str(path))
            document = read_iges(path)
            for entity in document["entities"]:
                if entity["type"] == 144:
                    key = surface_key(document, entity)
                    if key in keys and keys[key] != name:
                        raise InputValueError(
                            "IGES.NAME: coincident bases require unambiguous component ownership"
                        )
                    keys[key] = name
    finally:
        for dim, tag, visible in visibility:
            gmsh.model.setVisibility([(dim, tag)], visible)
        gmsh.option.setNumber("Geometry.OCCExportOnlyVisible", old)
    return keys


def name_properties(document, groups, keys):
    """Name every component twice: a property pointer on each face and a level per component.

    Each trimmed surface (144) points at its component's 406 form 15 NAME and also stands on
    that component's level, on which the NAME stands too, so a reader that names a face by its
    level (this package's own IGES reader) and one that follows property pointers agree.
    """
    result = document
    levels = {name: i + 1 for i, name in enumerate(groups)}
    last = max(entity["id"] for entity in result["entities"])
    property_ids = {name: last + 2 * i + 2 for i, name in enumerate(groups)}
    for entity in result["entities"]:
        if entity["type"] == 144:
            name = keys[surface_key(document, entity)]
            values = entity["parameters"]
            if len(values) != 5 + int(values[3]):
                raise InputValueError("IGES.NAME: unexpected pre-existing surface property lists")
            entity["parameters"] += ["0", "1", str(property_ids[name])]
            entity["d1"][4] = f"{levels[name]:8d}"
    for name, identity in property_ids.items():
        if not name.isascii() or "," in name or ";" in name:
            raise InputValueError("IGES.NAME: ASCII component identifiers required")
        d1 = [f"{406:8d}"] + [f"{0:8d}"] * 7 + ["00000200"]
        d1[4] = f"{levels[name]:8d}"
        d2 = [
            f"{406:8d}",
            f"{0:8d}",
            f"{0:8d}",
            f"{0:8d}",
            f"{15:8d}",
            " " * 8,
            " " * 8,
            f"{'NAME':>8}",
            f"{0:8d}",
        ]
        result["entities"].append(
            {
                "id": identity,
                "type": 406,
                "d1": d1,
                "d2": d2,
                "parameters": ["406", "1", f"{len(name)}H{name}"],
            }
        )
    result["global"][13:15] = ["6", "1HM"]
    return result


def _records(values, width):
    """Pack ``values`` into records of at most ``width`` columns, breaking only between values.

    A parameter is never split across records, which the OpenCASCADE reader does not accept for
    numbers; only a single Hollerith string longer than a record is cut.
    """
    records, current = [], ""
    for k, value in enumerate(values):
        text = value + (";" if k == len(values) - 1 else ",")
        if current and len(current) + len(text) > width:
            records.append(current)
            current = ""
        current += text
        while len(current) > width:
            records.append(current[:width])
            current = current[width:]
    return records + [current] if current else records


def serialize_iges(document):
    lines = [f"{payload:<72}S{i + 1:07d}" for i, payload in enumerate(document["start"])]
    global_lines = _records(document["global"], 72)
    lines += [f"{payload:<72}G{i + 1:07d}" for i, payload in enumerate(global_lines)]
    directory, parameters = [], []
    for entity in document["entities"]:
        chunks = _records(entity["parameters"], 64)
        d1, d2 = list(entity["d1"]), list(entity["d2"])
        d1[1], d2[3] = f"{len(parameters) + 1:8d}", f"{len(chunks):8d}"
        directory.extend(
            ["".join(d1) + f"D{entity['id']:07d}", "".join(d2) + f"D{entity['id'] + 1:07d}"]
        )
        for chunk in chunks:
            parameters.append(f"{chunk:<64}{entity['id']:8d}P{len(parameters) + 1:07d}")
    counts = (
        f"S{len(document['start']):07d}G{len(global_lines):07d}"
        f"D{len(directory):07d}P{len(parameters):07d}"
    )
    return "\n".join(lines + directory + parameters + [f"{counts:<72}T0000001"]) + "\n"


def write_iges(gmsh, groups, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    entities = gmsh.model.getEntities()
    visibility = [(dim, tag, gmsh.model.getVisibility(dim, tag)) for dim, tag in entities]
    old = gmsh.option.getNumber("Geometry.OCCExportOnlyVisible")
    try:
        gmsh.option.setNumber("Geometry.OCCExportOnlyVisible", 1)
        gmsh.model.setVisibility(entities, 0)
        gmsh.model.setVisibility(
            [(2, tag) for tags in groups.values() for tag in tags], 1, recursive=True
        )
        gmsh.write(str(path))
    finally:
        for dim, tag, visible in visibility:
            gmsh.model.setVisibility([(dim, tag)], visible)
        gmsh.option.setNumber("Geometry.OCCExportOnlyVisible", old)
    document = read_iges(path)
    with TemporaryDirectory(prefix="iges-names-", dir=path.parent) as temporary:
        directory = Path(temporary).resolve()
        if not directory.is_relative_to(path.parent.resolve()):
            raise InputValueError("IGES.NAME: temporary folder left the output folder")
        keys = component_keys(gmsh, groups, directory)
    document = name_properties(document, groups, keys)
    path.write_text(serialize_iges(document), encoding="ascii")


def generate_iges(
    config: Any, path: str | Path, *, configuration: str | None = None
) -> dict[str, Any]:
    """Generate the exposed skin of a configuration and write it as a named IGES file.

    Parameters
    ----------
    config : mapping or path
        A configuration (resolved or not) or the path of its TOML file.
    path : str or Path
        The IGES file to write.
    configuration : str, optional
        Name of an entry of the configuration's ``configurations`` table to generate;
        every component is generated when omitted.

    Returns
    -------
    dict
        ``path``, the number of exposed ``faces`` of each component, and the edge ``audit``.
    """
    resolved = load_config(config) if isinstance(config, (str, Path)) else resolve_config(config)
    every = generate_components(resolved)
    regions = assembly_regions(resolved, every)
    placed = every
    if configuration is not None:
        members = resolved["configurations"].get(configuration)
        if members is None:
            raise InputValueError(
                f"configuration {configuration!r}: unknown; available: "
                f"{sorted(resolved['configurations'])}"
            )
        placed = {name: every[name] for name in members if name in every}
    inside = {name: regions[name] for name in placed}
    with session("generating an IGES file from a parametric configuration") as gmsh:
        gmsh.model.add("generate")
        groups = {
            name: [add_occ_patch(gmsh.model.occ, patch) for patch in patches]
            for name, patches in placed.items()
        }
        gmsh.model.occ.synchronize()
        exposed, audit = assemble(gmsh.model, groups, inside)
        write_iges(gmsh, exposed, path)
    return {"path": Path(path), "faces": {n: len(t) for n, t in exposed.items()}, "audit": audit}
