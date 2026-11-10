"""Export the retained assembly faces and their measured source provenance.

Pipeline role: S11 writes the faces still owned by each piece after S10. The
manifest records measurements made on the live model, before any reimport.
Layout sidecars carry source bases and lines without resampling the geometry.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from pyflightstream._errors import InputArtifactError
from pyflightstream.geometry.stages import write_record
from pyflightstream.workspace._geom_assembly import Assembly
from pyflightstream.workspace._geom_parts import plain


def write_assembly(assembly: Assembly, target: Path) -> dict[str, Any]:
    """Write one file per piece and per face, plus the combined sewing input.

    Per-face files let a fresh kernel import each face alone, so adjacency
    healing cannot conceal a missing trim or an excessive face area.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    manifest = assembly.export_state()
    manifest["iges"] = target.name
    manifest["components"] = dict(manifest["components"])
    for name, faces in assembly.faces.items():
        piece = manifest["components"][name]
        piece["iges"] = f"{name}.igs"
        piece["layout"] = f"{name}.layout.json"
        assembly.k.export_iges({name: faces}, target.parent / piece["iges"])
        model = assembly.models[name]
        bases = {
            key: {
                "controls": p.controls.tolist(),
                "knots_u": p.knots_u,
                "knots_v": p.knots_v,
                "mult_u": p.multiplicities_u,
                "mult_v": p.multiplicities_v,
                "degree_u": p.degree_u,
                "degree_v": p.degree_v,
            }
            for key, p in model.bases.items()
        }
        for i, (face, entry) in enumerate(zip(faces, piece["faces"], strict=True)):
            entry["iges"] = f"{name}.face-{i}.igs"
            assembly.k.export_iges({entry["name"]: [face]}, target.parent / entry["iges"])
            entry["source_faces"] = [t.to_dict() for t in model.trims if t.base == entry["base"]]
            centre = np.mean(assembly.k.uv_bounds(face), axis=0)
            roles = set()
            for trim in model.trims:
                bounds = np.asarray(trim.loop).reshape(-1, 2)
                if (
                    trim.base == entry["base"]
                    and np.all(centre >= bounds.min(axis=0))
                    and np.all(centre <= bounds.max(axis=0))
                ):
                    roles.add(trim.role)
            if len(roles) != 1:
                raise InputArtifactError(
                    f"{entry['name']}: retained face has no unique source role", kind="geometry"
                )
            entry["role"] = roles.pop()
            entry["lines"] = model.layout["lines"]
        write_record(
            target.parent / piece["layout"],
            plain(
                {
                    **model.layout,
                    "bases": bases,
                    "faces": piece["faces"],
                    "source_surface_id": model.source_surface_id,
                }
            ),
        )
    assembly.k.export_iges(assembly.faces, target)
    write_record(target.parent / "manifest.json", manifest)
    return {
        "iges": str(target),
        "manifest": str(target.parent / "manifest.json"),
        "faces": {name: len(faces) for name, faces in assembly.faces.items()},
        "warnings": [],
        "audit": {"source": "retained assembly faces"},
    }


def generate_record(config: Any, path: str, configuration: str | None) -> dict[str, Any]:
    """Build unassembled source pieces on a kernel for a configuration with no operations."""
    from pyflightstream.geometry.stages import generate_pieces, unpack
    from pyflightstream.workspace._gmsh import open_kernel

    plain_config = unpack(config)
    every = generate_pieces(config)
    members = (
        list(every) if configuration is None else plain_config["configurations"][configuration]
    )
    kernel = open_kernel("writing source pieces")
    try:
        assembly = Assembly(kernel, {n: every[n] for n in members}, [], out=Path(path).parent)
        record = assembly.step("S10.D1")
        if any(c["status"] == "failed" for c in record["checks"]):
            raise InputArtifactError(str(record["checks"]), kind="geometry")
        return write_assembly(assembly, Path(path))
    finally:
        kernel.close()
