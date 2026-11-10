"""Automatic F7 group inputs, selected from the configuration's control variants.

Pipeline role: retain every selected component, choose one angle per active
control, add the planar root barrier of a standalone fin, and measure each
combined file in one native import. F5/F6 assembly boundaries remain separate.
"""

from __future__ import annotations

import copy
from itertools import product
from pathlib import Path

from pyflightstream.geometry.stages import controls, generate_components

from ._geom_control import check_stage
from ._geom_control_build import _faces


def _lifting_groups(kernel, components, members, active):
    stationary, families, caps, checks = {}, {}, {}, []
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
            key = f"{name}/{piece}"
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
    return stationary, families, caps, checks


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
    stationary, families, caps, checks = _lifting_groups(kernel, components, members, active)
    generated = generate_components({"components": components}, trimmed=True)
    for name in members:
        if components[name]["type"] != "lifting_surface":
            model = generated[name]
            stationary[name] = _faces(kernel, model, model.trims)
    folder = Path(out)
    folder.mkdir(parents=True, exist_ok=True)
    variants, inputs = {}, {}
    for index, chosen in enumerate(product(*families.values())):
        groups = {**stationary, **dict(chosen)}
        path = folder / f"control-variant-{index}.igs"
        kernel.export_iges(groups, path)
        result = check_stage(kernel, "F7", {"path": str(path), "symmetry_axis": 1})
        label = "/".join(key for key, _ in chosen) or "clean"
        checks.extend(
            {**c, "where": {"variant": variant, "combination": label}} for c in result["checks"]
        )
        inputs[label] = result["outputs"]["inputs"]
        variants[label] = {"path": str(path), "components": list(groups)}
    return {
        "checks": checks,
        "outputs": {
            "variants": variants,
            "root_caps_m2": caps,
            "inputs": {"geometry": inputs, "variant": variant, "active_controls": active},
        },
    }
