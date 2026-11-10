"""Applied-control files and their independent stage inputs.

Pipeline role: write the numerical bases and trims as separate native pieces.
The assembly lane consumes the sidecar without reconstructing the skin.
"""

from __future__ import annotations

from itertools import product
from pathlib import Path

from pyflightstream.geometry.stages import controls, generate_components, write_record

__all__ = ["prepare"]


def _faces(kernel, model, trims):
    native = {}
    for key in {t.base for t in trims}:
        p = model.bases[key]
        native[key] = kernel.add_bspline_surface(
            p.controls,
            knots_u=p.knots_u,
            knots_v=p.knots_v,
            mult_u=p.multiplicities_u,
            mult_v=p.multiplicities_v,
            deg_u=p.degree_u,
            deg_v=p.degree_v,
        )
    return [kernel.add_trimmed_face(native[t.base], [t.loop, *t.inner]) for t in trims]


def _hosts(kernel, components, members, folder):
    """Write selected host bodies in the same placed frame as the controls."""
    names = [name for name in members if components[name]["type"] == "body"]
    if not names:
        return {}
    generated = generate_components({"components": components})
    paths = {}
    for index, name in enumerate(names):
        faces = []
        for p in generated[name]:
            faces.append(
                kernel.add_bspline_surface(
                    p.controls,
                    knots_u=p.knots_u,
                    knots_v=p.knots_v,
                    mult_u=p.multiplicities_u,
                    mult_v=p.multiplicities_v,
                    deg_u=p.degree_u,
                    deg_v=p.degree_v,
                )
            )
        path = folder / f"control-host-{index}.igs"
        kernel.export_iges({name: faces}, path)
        paths[name] = str(path)
    return paths


def _combinations(kernel, faces, name, folder, index):
    """Write each angle combination with one moving piece of every control."""
    families = {}
    for piece in faces:
        if piece != "main":
            families.setdefault(piece.rsplit("-d", 1)[0], []).append(piece)
    combined = {}
    for number, selected in enumerate(product(*families.values())):
        path = folder / f"control-combined-{index}-{number}.igs"
        kernel.export_iges({f"{name}/{piece}": faces[piece] for piece in ("main", *selected)}, path)
        combined[f"{name}/{'/'.join(selected)}"] = {
            "path": str(path),
            "previous_free": 0,
            "symmetry_axis": 1,
        }
    return combined


def prepare(kernel, components, members, out):
    """Write applied pieces and return file-based inputs for the F checks.

    Parameters
    ----------
    kernel : CadKernel
        Caller-owned guarded adapter.
    components : dict
        Resolved components, including placement parents.
    members : list
        Selected component names.
    out : str or Path
        Run output directory.

    Returns
    -------
    dict
        Sub-step inputs, with a bases-and-trims hand-off in F0.
    """
    folder = Path(out)
    folder.mkdir(parents=True, exist_ok=True)
    written, mains, moving, combined, manifest = {}, {}, {}, {}, {}
    for index, name in enumerate(members):
        component = components[name]
        if not component.get("control_surfaces"):
            continue
        model = controls.placed(components, name)
        manifest[name] = {
            "bases": {key: patch.to_dict() for key, patch in model.bases.items()},
            "pieces": {key: [t.to_dict() for t in trims] for key, trims in model.pieces.items()},
        }
        faces = {}
        for number, (piece, trims) in enumerate(model.pieces.items()):
            faces[piece] = _faces(kernel, model, trims)
            path = folder / f"control-{index}-{number}.igs"
            kernel.export_iges({f"{name}/{piece}": faces[piece]}, path)
            key = f"{name}/{piece}"
            written[key] = {"path": str(path), "written": len(trims)}
            target = mains if piece == "main" else moving
            target[key] = {"path": str(path), "symmetry_axis": 1}
        combined.update(_combinations(kernel, faces, name, folder, index))
    if not written:
        return {}
    sidecar = folder / "applied-controls.json"
    write_record(sidecar, manifest)
    inputs = {
        "F0": {"pieces": written, "applied_controls": str(sidecar)},
        "F1": {"batch": mains},
        "F2": {"batch": moving},
        "F4": {"batch": combined},
    }
    hosts = _hosts(kernel, components, members, folder)
    if hosts:
        inputs["F3"] = {
            "controls": {name: row["path"] for name, row in moving.items()},
            "hosts": hosts,
        }
    return inputs
