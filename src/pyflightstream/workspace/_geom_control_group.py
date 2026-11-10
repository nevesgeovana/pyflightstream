"""Automatic F7 group inputs, selected from the configuration's control variants.

Pipeline role: retain every selected component, choose one angle per active
control, add the planar root barrier of a standalone fin, and measure each
combined file in one native import. F5/F6 assembly boundaries remain separate.
"""

from __future__ import annotations

import copy
from itertools import product
from pathlib import Path

import numpy as np

from pyflightstream.geometry.stages import GeneratedPiece, controls, generate_components

from ._geom_assembly import Assembly
from ._geom_control import check_stage
from ._geom_control_build import _faces


def _lifting_groups(kernel, components, members, active):
    stationary, families, caps, checks, sources = {}, {}, {}, [], {}
    for name in members:
        component = components[name]
        if component["type"] != "lifting_surface":
            continue
        component["control_surfaces"] = [
            entry
            for entry in component.get("control_surfaces", [])
            if f"{name}.{entry['name']}" in active
        ]
        cap = component["planform"]["orientation"] == "vertical" and component.get("root") != "flat"
        if cap:
            component["root"] = "flat"
        model = controls.placed(components, name)
        checks.extend(model.checks)
        for piece, trims in model.pieces.items():
            faces = _faces(kernel, model, trims)
            key = name if piece == "main" else f"{name}/{piece}"
            sources[key] = GeneratedPiece.from_patches(
                key, component["version"], controls.face_patches(model, trims)
            )
            if piece == "main":
                stationary[key] = faces
                if cap:
                    caps[name] = sum(
                        kernel.area(face)
                        for face, trim in zip(faces, trims, strict=True)
                        if trim.face == "root"
                    )
            else:
                families.setdefault(f"{name}/{piece.rsplit('-d', 1)[0]}", []).append((key, faces))
    return stationary, families, caps, checks, sources


def _junction_lengths(kernel, assembly):
    owners = {}
    for name, faces in assembly.faces.items():
        for face in faces:
            for edge in kernel.boundary(face):
                owners.setdefault(abs(edge), set()).add(name)
    lengths = {}
    for op in assembly.plan:
        pair = f"{op.dominant}/{op.dominated}"
        total = 0.0
        for edge, names in owners.items():
            if {op.dominant, op.dominated} <= names:
                low, high = kernel.edge_bounds(edge)
                points = np.array(kernel.edge_values(edge, np.linspace(low, high, 257)))
                total += float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum())
        lengths[pair] = total
    return lengths


def _join(kernel, groups, sources, resolved, folder):
    """Reuse the measured assembly operations on exact restricted source faces."""
    rows = resolved.get("dominance", [])
    if not rows:
        return groups, [], {}
    assembly = Assembly(
        kernel,
        {name: sources[name] for name in groups},
        rows,
        out=folder,
        members=list(groups),
        plane_axis=1,
        kinds={n: c["type"] for n, c in resolved["components"].items()},
    )
    for stage in ("S10.D1", "S10.D3", "S10.D4", "S10.D5", "S10.D6", "S10.D8", "S10.D9"):
        record = assembly.step(stage)
        if any(c["status"] == "failed" for c in record["checks"]):
            break
    return assembly.faces, assembly.records, _junction_lengths(kernel, assembly)


def group(kernel, resolved, members, variant, out):
    """Build and sew every angle combination of the requested registry variant.

    Parameters
    ----------
    kernel : CadKernel
        Caller-owned guarded adapter.
    resolved : dict
        Plain resolved configuration, including variant membership.
    members : list
        Component names selected by the configuration registry.
    variant : str
        Variant whose component.control entries are active; clean has none.
    out : str or Path
        Directory for independent combined IGES files.

    Returns
    -------
    dict
        Measured topology, root-cap areas, inputs and variant file paths.
    """
    components = copy.deepcopy(resolved["components"])
    active = resolved["variants"][variant]
    stationary, families, caps, checks, sources = _lifting_groups(
        kernel, components, members, active
    )
    generated = generate_components({"components": components}, trimmed=True)
    for name in members:
        if components[name]["type"] != "lifting_surface":
            model = generated[name]
            stationary[name] = _faces(kernel, model, model.trims)
            sources[name] = model
    folder = Path(out)
    folder.mkdir(parents=True, exist_ok=True)
    variants, inputs, junctions, assemblies = {}, {}, {}, {}
    for index, chosen in enumerate(product(*families.values())):
        groups = {**stationary, **dict(chosen)}
        groups, records, lengths = _join(
            kernel, groups, sources, resolved, folder / f"variant-join-{index}"
        )
        checks.extend(c for record in records for c in record["checks"])
        path = folder / f"control-variant-{index}.igs"
        kernel.export_iges(groups, path)
        result = check_stage(kernel, "F7", {"path": str(path), "symmetry_axis": 1})
        label = "/".join(key for key, _ in chosen) or "clean"
        checks.extend(
            {**c, "where": {"variant": variant, "combination": label}} for c in result["checks"]
        )
        inputs[label] = result["outputs"]["inputs"]
        variants[label] = {"path": str(path), "components": list(groups)}
        junctions[label], assemblies[label] = lengths, records
    return {
        "checks": checks,
        "outputs": {
            "variants": variants,
            "root_caps_m2": caps,
            "junction_lengths_m": junctions,
            "assembly_records": assemblies,
            "inputs": {"geometry": inputs, "variant": variant, "active_controls": active},
        },
    }
