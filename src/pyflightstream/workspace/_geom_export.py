"""Export the retained assembly faces and their measured source provenance.

Pipeline role: S11 writes the faces still owned by each piece after S10. The
manifest records measurements made on the live model, before any reimport.
Layout sidecars carry source bases and lines without resampling the geometry.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import numpy as np

from pyflightstream._errors import InputArtifactError
from pyflightstream.geometry.stages import check_entry, manifest_checks, unpack, write_record
from pyflightstream.workspace._geom_assembly import Assembly
from pyflightstream.workspace._geom_parts import plain
from pyflightstream.workspace._gmsh_worker import run_isolated


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
        "sources": {
            n: {"version": p.version, "source_surface_id": p.source_surface_id}
            for n, p in assembly.models.items()
        },
    }


def check_export(stage, resolved, configuration, members, out, source) -> dict[str, Any]:
    """Measure one export sub-step against the retained source record."""
    manifest = json.loads((Path(out) / "manifest.json").read_text(encoding="utf-8"))
    if stage == "S11.R":
        return read_back(Path(out), manifest, float(unpack(resolved)["acceptance"]["area_excess"]))
    checks = manifest_checks(resolved, configuration, members, manifest, source["sources"])
    return {"checks": checks, "outputs": {"inputs": {"members": members}}}


def inspect_record(file: str, tolerance: float | None) -> dict[str, Any]:
    """Read one file alone in a fresh worker; return measured topology in metres."""
    from pyflightstream.workspace._gmsh import open_kernel

    kernel = open_kernel("export read-back")
    try:
        topology = kernel.inspect_file(file, tolerance)
        return plain(
            {
                "areas": topology.areas,
                "perimeters": topology.perimeters,
                "edges": [{"samples": points, "faces": faces} for points, faces in topology.edges],
                "names": topology.names,
                "pid": os.getpid(),
            }
        )
    finally:
        kernel.close()


def _inspect(path: Path, tolerance: float | None = None) -> dict[str, Any]:
    return run_isolated(
        f"{__name__}:inspect_record", {"file": str(path), "tolerance": tolerance}, inspect_record
    )


def _measured(check, value, limit, *, unit, where=None):
    return check_entry(
        check, "passed" if value <= limit else "failed", value, limit, unit=unit, where=where
    )


def read_back(folder: Path, manifest: dict, area_excess: float) -> dict[str, Any]:
    """Measure component count, free edges and each isolated face's trimmed area.

    Area reads have no sewing. Free-edge comparison uses a separate import sewn
    at 1e-5 m. A failed import counts as a lost face and a full area loss.
    """
    count_gap, free_gap, triple, worst, excess = 0, 0, 0, 0.0, 0.0
    where: dict[str, Any] = {}
    pids, failures, files = [], [], []

    def read(file, tolerance=None):
        files.append(file)
        try:
            record = _inspect(folder / file, tolerance)
            pids.append(record["pid"])
            return record
        except InputArtifactError as error:
            failures.append({"file": file, "error": str(error)})
            return {"areas": [], "edges": []}

    for name, piece in manifest["components"].items():
        expected = [float(f["area_m2"]) for f in piece["faces"]]
        imported = read(piece["iges"])
        areas = imported["areas"]
        count_gap = max(count_gap, abs(len(areas) - len(expected)))
        if len(areas) == len(expected):
            for got, wanted in zip(sorted(areas), sorted(expected), strict=True):
                relative = abs(got - wanted) / max(wanted, 1e-30)
                if relative >= worst:
                    worst, where = (
                        relative,
                        {"component": name, "expected_m2": wanted, "read_m2": got},
                    )
        else:
            worst, where = max(worst, 1.0), {"component": name, "file": piece["iges"]}
        source_area = float(piece["source_area_m2"])
        excess = max(excess, (sum(areas) - source_area) / max(source_area, 1e-30))
        sewn = read(piece["iges"], 1e-5)
        free = sum(len(e["faces"]) == 1 for e in sewn["edges"])
        free_gap = max(free_gap, abs(free - piece["free_edges"]))
        triple += sum(len(e["faces"]) > 2 for e in sewn["edges"])
        for face in piece["faces"]:
            alone = read(face["iges"])
            count_gap = max(count_gap, abs(len(alone["areas"]) - 1))
            area = sum(alone["areas"])
            relative = abs(area - face["area_m2"]) / max(face["area_m2"], 1e-30)
            if relative >= worst:
                worst, where = (
                    relative,
                    {
                        "component": name,
                        "face": face["name"],
                        "expected_m2": face["area_m2"],
                        "read_m2": area,
                    },
                )
    return {
        "checks": [
            _measured("area.read_back", worst, 1e-3, unit="relative", where=where),
            _measured("area.source_excess", excess, area_excess, unit="relative"),
            _measured("reimport.each_component", count_gap, 0, unit="faces"),
            _measured("reimport.free_edges", free_gap, 0, unit="edges"),
            _measured("reimport.triple_edges", triple, 0, unit="edges"),
        ],
        "outputs": {"inputs": {"files": files}, "worker_pids": pids, "failures": failures},
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
