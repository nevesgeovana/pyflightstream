"""Export the retained assembly faces and their measured source provenance.

Pipeline role: S11 writes the faces still owned by each piece after S10. The
manifest records measurements made on the live model, before any reimport.
Layout sidecars carry source bases and lines without resampling the geometry.
"""

from __future__ import annotations

import json
import os
from importlib import metadata
from pathlib import Path
from typing import Any

import numpy as np

from pyflightstream._errors import InputArtifactError
from pyflightstream.geometry.stages import (
    build_id,
    check_entry,
    manifest_checks,
    manifest_record,
    parameter_id,
    sha256_file,
    sidecar_identity,
    surface_id,
    unpack,
    write_record,
)
from pyflightstream.geometry.stages import junctions as jn
from pyflightstream.workspace._geom_assembly import Assembly
from pyflightstream.workspace._geom_parts import plain
from pyflightstream.workspace._gmsh_worker import run_isolated


def _export_units(resolved, names):
    """Choose the definition's mm for propeller-only groups; other groups use kernel metres."""
    components = unpack(resolved or {}).get("components", {})
    if names and all(
        components.get(n, {}).get("type") == "propeller"
        and components[n].get("definition", {}).get("output", {}).get("units") == "mm"
        for n in names
    ):
        return {"unit": "mm"}
    return {}


def write_assembly(
    assembly: Assembly, target: Path, *, resolved=None, configuration=None
) -> dict[str, Any]:
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
        units = _export_units(resolved, [name])
        assembly.k.export_iges({name: faces}, target.parent / piece["iges"], **units)
        piece["sha256"] = sha256_file(target.parent / piece["iges"])
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
            assembly.k.export_iges({entry["name"]: [face]}, target.parent / entry["iges"], **units)
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
                    "base_order": list(model.bases),
                    "source_trims": [t.to_dict() for t in model.trims],
                    "faces": piece["faces"],
                    "source_surface_id": model.source_surface_id,
                }
            ),
        )
    assembly.k.export_iges(assembly.faces, target, **_export_units(resolved, assembly.faces))
    config = (
        unpack(resolved)
        if resolved is not None
        else {
            "components": {
                n: {"version": p.version, "source_surface_id": p.source_surface_id}
                for n, p in assembly.models.items()
            }
        }
    )
    parameter = parameter_id(config)
    try:
        package = metadata.version("pyflightstream")
    except metadata.PackageNotFoundError:
        package = "0.0.0+uninstalled"
    identity = surface_id(
        {n: list(p.bases.values()) for n, p in assembly.models.items()},
        {n: p.trims for n, p in assembly.models.items()},
    )
    coverage: dict[str, Any] = next(
        (r["outputs"].get("pieces", {}) for r in assembly.records if r["stage"] == "S10.D8b"), {}
    )
    manifest = manifest_record(
        manifest,
        configuration=configuration,
        identities={
            "parameter_id": parameter,
            "surface_id": identity,
            "build_id": build_id(parameter, package, assembly.k.name, assembly.k.version),
        },
        dominance=config.get("dominance", []),
        coverage=coverage,
    )
    write_record(target.parent / "manifest.json", manifest)
    return {
        "iges": str(target),
        "manifest": str(target.parent / "manifest.json"),
        "surface_id": manifest["surface_id"],
        "build_id": manifest["build_id"],
        "faces": {name: len(faces) for name, faces in assembly.faces.items()},
        "warnings": [],
        "audit": {"source": "retained assembly faces"},
        "sources": {
            n: {"version": p.version, "source_surface_id": p.source_surface_id}
            for n, p in assembly.models.items()
        },
    }


def check_export(stage, resolved, *, configuration, members, out, source) -> dict[str, Any]:
    """Measure one export sub-step against the retained source record."""
    manifest = json.loads((Path(out) / "manifest.json").read_text(encoding="utf-8"))
    if stage == "S11":
        return write_checks(Path(out), manifest)
    if stage == "S11.P":
        return profile_checks(Path(out), manifest, source)
    if stage == "S11.R":
        return read_back(Path(out), manifest, float(unpack(resolved)["acceptance"]["area_excess"]))
    if stage == "S11.S":
        return sew_back(Path(out), manifest)
    if stage in ("S12.C", "S12.G", "S12"):
        from pyflightstream.workspace._geom_reader import reader_check

        return reader_check(stage, out, manifest, resolved)
    if stage in ("S13.R", "S13"):
        from pyflightstream.workspace._geom_roundtrip import identify, regenerate

        return (
            regenerate(resolved, out, members, manifest, source)
            if stage == "S13.R"
            else identify(resolved, out, manifest)
        )
    checks = manifest_checks(resolved, configuration, members, manifest, source["sources"])
    return {"checks": checks, "outputs": {"inputs": {"members": members}}}


def write_checks(folder, manifest):
    """Count emitted faces and solid entities in each file immediately after writing."""
    from pyflightstream.geometry.iges_profile import SOLID_ENTITIES
    from pyflightstream.workspace._iges_write import read_iges

    expected = {manifest["iges"]: sum(p["faces"] for p in manifest["pieces"])}
    for piece in manifest["pieces"]:
        expected[piece["file"]] = piece["faces"]
        expected.update({f["iges"]: 1 for f in piece["face_records"]})
    missing, solid = 0, 0
    for file, count in expected.items():
        entities = read_iges(folder / file)["entities"]
        missing = max(missing, abs(sum(e["type"] == 144 for e in entities) - count))
        solid += sum(e["type"] in SOLID_ENTITIES for e in entities)
    return {
        "checks": [
            _measured("write.face_count", missing, 0, unit="faces"),
            _measured("profile.surfaces_only", solid, 0, unit="solid entities"),
        ],
        "outputs": {"inputs": {"expected_faces": expected}},
    }


def profile_checks(folder, manifest, source):
    """Measure the reader flags and every published base against source provenance."""
    from pyflightstream.geometry.iges_profile import SOLID_ENTITIES
    from pyflightstream.workspace._geom_gate import base_displacement, check_profile, read_bases
    from pyflightstream.workspace._iges_write import read_iges

    files, combined, shared = {}, {}, 0.0
    for piece in manifest["pieces"]:
        name = piece["component"]
        layout = json.loads((folder / piece["layout"]).read_text(encoding="utf-8"))
        identity = sidecar_identity(name, layout)
        shared = max(shared, float(identity != source["sources"][name]["source_surface_id"]))
        written_bases = {}
        for face in piece["face_records"]:
            if face["base"] not in written_bases:
                written_bases[face["base"]] = read_bases(folder / face["iges"])[face["name"]]
        combined[name] = list(written_bases.values())
        files[piece["file"]] = {name: combined[name]}
        for face in piece["face_records"]:
            files[face["iges"]] = {face["name"]: [written_bases[face["base"]]]}
    files[manifest["iges"]] = combined
    solid, flags = 0, 0
    for file, bases in files.items():
        document = read_iges(folder / file)
        by_id = {e["id"]: e for e in document["entities"]}
        solid += sum(e["type"] in SOLID_ENTITIES for e in by_id.values())
        for entity in by_id.values():
            if entity["type"] == 142:
                values = entity["parameters"]
                parameter, model = by_id.get(int(values[3])), by_id.get(int(values[4]))
                flags += int(
                    values[5] != "1"
                    or parameter is None
                    or model is None
                    or parameter["d1"][8][4:6] != "05"
                )
        shared = max(shared, base_displacement(folder / file, bases))
    report = None if solid else check_profile(folder / manifest["iges"])
    failures = flags + (len(report.failed) if report is not None else solid)
    return {
        "checks": [
            _measured("profile.reader", failures, 0, unit="defects"),
            _measured("profile.base_shared", shared, 1e-12, unit="coefficient difference"),
        ],
        "warnings": []
        if report is None
        else [str(f) for f in report.findings if f.severity == "warn"],
        "outputs": {
            "inputs": {"files": list(files)},
            "findings": [] if report is None else [vars(f) for f in report.findings],
        },
    }


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

    for piece in manifest["pieces"]:
        name = piece["component"]
        expected = [float(f["area_m2"]) for f in piece["face_records"]]
        imported = read(piece["file"])
        areas = imported["areas"]
        piece["reimport_area_m2"] = sum(areas)
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
            worst, where = max(worst, 1.0), {"component": name, "file": piece["file"]}
        source_area = float(piece["source_area_m2"])
        excess = max(excess, (sum(areas) - source_area) / max(source_area, 1e-30))
        sewn = read(piece["file"], 1e-5)
        free = sum(len(e["faces"]) == 1 for e in sewn["edges"])
        free_gap = max(free_gap, abs(free - piece["free_edges"]))
        triple += sum(len(e["faces"]) > 2 for e in sewn["edges"])
        for face in piece["face_records"]:
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
    write_record(folder / "manifest.json", manifest)
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


def sew_back(folder: Path, manifest: dict) -> dict[str, Any]:
    """Read the combined file once per tolerance and compare with the input openings.

    Faces from separately imported files are never treated as sewn together.
    Thin faces already present in the input are listed, not treated as new defects.
    """
    reference = [np.asarray(p, float) for p in manifest["input_free_edges"]]
    axis = manifest.get("plane_axis")

    def brought(points):
        if axis is not None and float(np.abs(points[:, axis]).max()) <= jn.SYMMETRY_M:
            return True
        return any(
            float(jn.distance_to_polyline(points, p).max()) <= jn.OPENING_M for p in reference
        )

    imports = []
    for tolerance in (jn.SEW_M, jn.SEW_WIDE_M):
        topology = _inspect(folder / manifest["iges"], tolerance)
        free = [np.asarray(e["samples"]) for e in topology["edges"] if len(e["faces"]) == 1]
        new = [p.tolist() for p in free if not brought(p)]
        widths = [
            jn.mean_width(a, p)
            for a, p in zip(topology["areas"], topology["perimeters"], strict=True)
        ]
        thin = [
            {"face": i, "area_m2": topology["areas"][i], "width_m": widths[i]}
            for i in jn.slivers(widths)
        ]
        imports.append(
            {
                "tolerance_m": tolerance,
                "pid": topology["pid"],
                "free_edges": len(free),
                "introduced": new,
                "triple_edges": sum(len(e["faces"]) > 2 for e in topology["edges"]),
                "slivers": thin,
                "slivers_introduced": max(0, len(thin) - manifest["input_slivers"]),
            }
        )
    return {
        "checks": [
            _measured(
                "sew.free_introduced", max(len(r["introduced"]) for r in imports), 0, unit="edges"
            ),
            _measured("sew.triple_edges", max(r["triple_edges"] for r in imports), 0, unit="edges"),
            _measured(
                "sew.slivers", max(r["slivers_introduced"] for r in imports), 0, unit="faces"
            ),
        ],
        "outputs": {
            "inputs": {
                "file": manifest["iges"],
                "free_edges": len(reference),
                "slivers": manifest["input_slivers"],
            },
            "imports": imports,
        },
    }


def generate_record(config: Any, path: str, configuration: str | None) -> dict[str, Any]:
    """Build unassembled source pieces on a kernel for a configuration with no operations."""
    from pyflightstream.geometry.stages import generate_pieces, unpack
    from pyflightstream.workspace._geom_propeller import PropellerAssembly
    from pyflightstream.workspace._gmsh import open_kernel

    plain_config = unpack(config)
    every = generate_pieces(config)
    members = (
        list(every) if configuration is None else plain_config["configurations"][configuration]
    )
    kernel = open_kernel("writing source pieces")
    try:
        factory = (
            PropellerAssembly
            if any(plain_config["components"][n]["type"] == "propeller" for n in members)
            else Assembly
        )
        assembly = factory(kernel, {n: every[n] for n in members}, [], out=Path(path).parent)
        record = assembly.step("S10.D1")
        if any(c["status"] == "failed" for c in record["checks"]):
            raise InputArtifactError(str(record["checks"]), kind="geometry")
        written = write_assembly(assembly, Path(path), resolved=config, configuration=configuration)
        written["sections"] = {
            n: p.layout["sections"] for n, p in every.items() if "sections" in p.layout
        }
        return written
    finally:
        kernel.close()
