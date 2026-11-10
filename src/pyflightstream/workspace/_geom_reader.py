"""Run the shipped readers and audit their mesh against retained face roles.

Pipeline role: S12.C converts the exported assembly, S12.G grids its named
retained faces, and S12 measures the mesh topology and sidecar trailing edges.
The mesher establishes true CAD boundaries before the independent mesh audit.
No geometric trailing-edge search is used for these native exports.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from pyflightstream._errors import PyflightstreamError
from pyflightstream.geometry.stages import check_entry, unpack, write_config, write_record
from pyflightstream.workspace._refine._obj import read_obj, write_te


def measured(name, value, *, where=None):
    """Return a zero-defect reader check with its measured location."""
    return check_entry(name, "passed" if value == 0 else "failed", value, 0, where=where)


def convert(folder, manifest):
    """Exercise the shipped converter and compare its read-back face counts."""
    from pyflightstream.workspace.iges_convert import convert_iges

    target = folder / "S12-converted.igs"
    try:
        record = convert_iges([folder / manifest["iges"]], target)
        expected = {p["component"]: p["faces"] for p in manifest["pieces"]}
        errors = abs(record["faces"] - sum(expected.values()))
        errors += record["components"] != expected
    except PyflightstreamError as error:
        record, errors = {"error": str(error)}, 1
    return {
        "checks": [measured("gate.convert", errors)],
        "outputs": {
            "inputs": {"file": manifest["iges"]},
            "converted": str(target),
            "conversion": record,
        },
    }


def owners(mesh):
    """Index undirected mesh edges by all incident face families."""
    edges = defaultdict(list)
    for name, faces in mesh.families.items():
        for face in faces:
            for a, b in zip(face, face[1:] + face[:1], strict=True):
                edges[tuple(sorted((a, b)))].append(name)
    return edges


def edge_key(mesh, edge):
    """Represent an edge geometrically, independent of OBJ node numbering."""
    return tuple(sorted(tuple(float(v) for v in mesh.verts[n]) for n in edge))


def grid(folder, manifest):
    """Grid retained faces once and retain the reader's validated boundary reference."""
    from pyflightstream.workspace.iges_grid import grid_iges

    faces = [f for p in manifest["pieces"] for f in p["face_records"]]
    control, target = folder / "S12-grid.toml", folder / "S12.obj"
    config = {
        "defaults": {"remove_inner_faces": False},
        "component": {f["name"]: {"chord": {"count": 16}, "span": {"count": 16}} for f in faces},
    }
    write_config(config, control)
    try:
        record = grid_iges([folder / f["iges"] for f in faces], control, target)
        mesh = read_obj(target)
        edges = owners(mesh)
        errors = record["conformal"]["conformal_mismatches"]
        errors += sum(len(names) > 2 for names in edges.values())
        errors += set(mesh.families) != {f["name"] for f in faces}
        reference = {
            "boundary": [edge_key(mesh, e) for e, names in edges.items() if len(names) == 1],
            "faces": {n: len(fs) for n, fs in mesh.families.items()},
            "validated": errors == 0,
        }
        write_record(folder / "S12-boundary.json", reference)
    except PyflightstreamError as error:
        record, errors = {"error": str(error)}, 1
    return {
        "checks": [measured("gate.grid", errors)],
        "warnings": record.get("warnings", []),
        "outputs": {
            "inputs": {"files": [f["iges"] for f in faces]},
            "mesh": str(target),
            "grid": record,
        },
    }


def trailing_edges(folder, manifest, config, mesh, edges):
    """Find the upper rim of each TE face from retained sidecar roles."""
    checks, results = [], {}
    for piece in manifest["pieces"]:
        name = piece["component"]
        if config["components"][name]["type"] != "lifting_surface":
            continue
        layout = json.loads((folder / piece["layout"]).read_text(encoding="utf-8"))
        roles = {f["name"]: f["role"] for f in layout["faces"]}
        found = [
            edge
            for edge, names in edges.items()
            if len(names) == 2 and {roles.get(n) for n in names} == {"upper", "trailing_edge"}
        ]
        length = sum(float(np.linalg.norm(mesh.verts[a] - mesh.verts[b])) for a, b in found)
        checks.append(
            measured("gate.te_found", int(not found or length <= 0), where={"component": name})
        )
        result = {"edges": len(found), "length_m": length, "source": "sidecar roles"}
        if found:
            path = folder / f"S12-{name}.te.txt"
            write_te(path, "m", np.asarray([(mesh.verts[a] + mesh.verts[b]) / 2 for a, b in found]))
            result["file"] = str(path)
        results[name] = result
    if not checks:
        checks.append(check_entry("gate.te_found", "skipped", note="no lifting pieces"))
    return checks, results


def audit(folder, manifest, resolved):
    """Re-read the OBJ and reject new open seams, triple edges and absent TE rims."""
    mesh = read_obj(folder / "S12.obj")
    reference = json.loads((folder / "S12-boundary.json").read_text(encoding="utf-8"))
    boundary = {tuple(tuple(p) for p in e) for e in reference["boundary"]}
    edges = owners(mesh)
    missing = sum(len(ns) == 1 and edge_key(mesh, e) not in boundary for e, ns in edges.items())
    triple = sum(len(ns) > 2 for ns in edges.values())
    changed = {n: len(fs) for n, fs in mesh.families.items()} != reference["faces"]
    errors = missing + triple + int(changed) + int(not reference["validated"])
    checks, trailing = trailing_edges(folder, manifest, unpack(resolved), mesh, edges)
    return {
        "checks": [measured("gate.conformal", errors), *checks],
        "outputs": {
            "inputs": {"mesh": "S12.obj", "boundary": "S12-boundary.json"},
            "new_open_edges": missing,
            "triple_edges": triple,
            "trailing_edges": trailing,
        },
    }


def reader_check(stage, folder, manifest, resolved):
    """Dispatch one reader sub-step without introducing a second assembly scheme."""
    folder = Path(folder)
    if stage == "S12.C":
        return convert(folder, manifest)
    if stage == "S12.G":
        return grid(folder, manifest)
    return audit(folder, manifest, resolved)
