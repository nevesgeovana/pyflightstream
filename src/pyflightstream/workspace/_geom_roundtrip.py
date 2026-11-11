"""Regenerate stored source surfaces and identify the written lifting pieces.

Pipeline role: S13.R reloads a resolved TOML with exact B-spline sections and
compares source bases and loops without a kernel. S13 independently runs the
existing reverse capability on each supported component in a fresh process.
"""

from __future__ import annotations

from pathlib import Path

from pyflightstream._errors import PyflightstreamError
from pyflightstream.geometry import load_config
from pyflightstream.geometry.stages import (
    check_entry,
    generate_pieces,
    parameter_id,
    placement_transform,
    stored_sections_config,
    surface_id,
    unpack,
    write_config,
)
from pyflightstream.workspace._gmsh_worker import run_isolated


def regenerate(resolved, folder, members, manifest, source):
    """Reload the stored sections and compare independently retained source identities."""
    path = Path(folder) / "resolved.toml"
    stored = stored_sections_config(resolved, source["sections"])
    write_config(stored, path)
    loaded = load_config(path)
    every = generate_pieces(
        loaded,
        variant=manifest.get("variant", "clean"),
        selection=manifest.get("control_selection"),
    )
    pieces = {n: every[n] for n in members}
    identity = surface_id(
        {n: list(p.bases.values()) for n, p in pieces.items()},
        {n: p.trims for n, p in pieces.items()},
    )
    comparisons = {
        name: {
            "expected": source["sources"][name]["source_surface_id"],
            "regenerated": piece.source_surface_id,
            "bases": len(piece.bases),
            "trims": len(piece.trims),
        }
        for name, piece in pieces.items()
    }
    differences = sum(r["expected"] != r["regenerated"] for r in comparisons.values())
    differences += identity != manifest["surface_id"]
    return {
        "checks": [
            check_entry(
                "roundtrip.same_surface",
                "passed" if differences == 0 else "failed",
                differences,
                0,
                unit="identities",
                where={"pieces": comparisons},
            )
        ],
        "outputs": {
            "inputs": {"members": members},
            "resolved_toml": str(path),
            "regenerated_surface_id": identity,
            "stored_parameter_id": parameter_id(loaded),
            "pieces": comparisons,
        },
    }


def identify_record(file, component, options):
    """Identify one written component in the worker's disposable kernel process."""
    from pyflightstream.workspace.geometry_pipeline import identify_lifting_surface

    result = identify_lifting_surface(file, component, **options)
    return result.to_dict()


def identify(resolved, folder, manifest):
    """Measure reverse identification where a component type has that capability."""
    config = unpack(resolved)
    components = config["components"]
    checks, results = [], {}
    for piece in manifest["pieces"]:
        name = piece["component"]
        component = components[name]
        if component["type"] != "lifting_surface":
            checks.append(
                check_entry(
                    "roundtrip.identify",
                    "skipped",
                    where={"component": name},
                    note=f"no reverse capability for {component['type']}",
                )
            )
            continue
        rotation, _ = placement_transform(components, name)
        chord = max(component["planform"]["root_chord"], component["planform"]["tip_chord"])
        tolerance = max(
            config["acceptance"]["floor_mm"], 1000 * config["acceptance"]["fraction"] * chord
        )
        arguments = {
            "file": str(Path(folder) / piece["file"]),
            "component": name,
            "options": {
                "root": "boundary",
                "mirrored": True,
                "span_axis": rotation[:, 1].tolist(),
                "section_tolerance_mm": tolerance,
            },
        }
        try:
            result = run_isolated(f"{__name__}:identify_record", arguments, identify_record)
        except (PyflightstreamError, ValueError) as error:
            result = {"accepted": False, "error": str(error)}
        results[name] = result
        checks.append(
            check_entry(
                "roundtrip.identify",
                "passed" if result["accepted"] else "failed",
                int(not result["accepted"]),
                0,
                unit="rejected pieces",
                where={"component": name},
                note=result.get("error", ""),
            )
        )
    return {
        "checks": checks,
        "outputs": {
            "inputs": {"files": [p["file"] for p in manifest["pieces"]]},
            "identification": results,
        },
    }
