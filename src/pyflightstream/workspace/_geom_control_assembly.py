"""F5 and F6 boundaries measured using the existing trimmed assembly operations.

Pipeline role: compare applied host cuts with independently assembled clean
references. Cove and moving bases remain inert. Engine bounds name the bodies
introduced at F6; other selected dominance rows form the F5 boundary.
"""

from __future__ import annotations

from math import fsum
from pathlib import Path

from pyflightstream._digest import file_sha256
from pyflightstream.geometry.stages import check_entry, generate_pieces, unpack

from ._geom_assembly import Assembly
from ._geom_control import check_stage


def _boundary(kernel, pieces, rows, components, folder):
    assembly = Assembly(
        kernel,
        pieces,
        rows,
        out=folder,
        plane_axis=1,
        kinds={n: components[n]["type"] for n in pieces},
    )
    for stage in ("S10.D1", "S10.D3", "S10.D4", "S10.D5", "S10.D6", "S10.D8"):
        record = assembly.step(stage)
        if any(c["status"] == "failed" for c in record["checks"]):
            break
    lengths = {
        f"{op.dominant}/{op.dominated}": fsum(
            kernel.edge_length(e) for e in assembly._junction(op.dominant, op.dominated)
        )
        for op in assembly.plan
    }
    path = folder / "boundary.igs"
    kernel.export_iges(assembly.faces, path)
    kernel.remove(kernel.faces())
    return path, lengths, assembly.records


def _free(kernel, path):
    topology = kernel.inspect_file(path, 1e-5)
    return sum(len(fs) == 1 and not (abs(p[:, 1]) <= 1e-5).all() for p, fs in topology.edges)


def _boundaries(kernel, clean, applied, selected, *, before_rows, components, folder):
    states = {}
    for name, pieces, rows in (
        ("before", applied, before_rows),
        ("clean", clean, selected),
        ("applied", applied, selected),
    ):
        path, lengths, records = _boundary(kernel, pieces, rows, components, folder / name)
        states[name] = {"path": path, "lengths": lengths, "records": records}
        failed = next(
            (r for r in records if any(c["status"] == "failed" for c in r["checks"])), None
        )
        if failed is not None:
            return states, {
                "checks": [
                    {**c, "where": {**c["where"], "boundary": name, "sub_step": failed["stage"]}}
                    for c in failed["checks"]
                    if c["status"] != "skipped"
                ],
                "outputs": {
                    "inputs": {"geometry": {"path": str(path), "sha256": file_sha256(path)}},
                    "assembly_records": {n: s["records"] for n, s in states.items()},
                    "stopped_at": failed["stage"],
                },
            }
    return states, None


def trimmed_control_assembly(config, members, variant, out, stage, *, selection=None):
    """Return the measured F5 or F6 boundary and its clean junction reference.

    Parameters
    ----------
    config : dict
        Resolved configuration with dominance rows and engine bounds.
    members : list
        Selected registry component names.
    variant : str
        Active control variant.
    out : str
        Output record location; geometry is written beside it.
    stage : str
        F5 for body cuts, F6 for the additional engine cuts.
    selection : dict, optional
        One selected position label per active component.control.

    Returns
    -------
    dict
        Measured checks, input hashes, actual junction lengths and assembly records.
    """
    from ._gmsh import open_kernel

    plain = unpack(config)
    components = plain["components"]
    engines = {
        b["component"]
        for c in components.values()
        if c["type"] == "lifting_surface"
        for b in c.get("sections", {}).get("nacelle_bounds", [])
    }
    rows = [r for r in plain["dominance"] if set((*r["dominant"], *r["dominated"])) <= set(members)]
    body_rows = [r for r in rows if not engines.intersection((*r["dominant"], *r["dominated"]))]
    selected = body_rows if stage == "F5" else rows
    if not selected or (stage == "F6" and selected == body_rows):
        return {}
    clean = generate_pieces(config)
    applied = generate_pieces(config, variant=variant, selection=selection)
    clean, applied = ({n: p[n] for n in members} for p in (clean, applied))
    folder = Path(out).parent
    kernel = open_kernel(f"measuring trimmed control {stage}")
    try:
        before_rows = [] if stage == "F5" else body_rows
        states, stopped = _boundaries(
            kernel,
            clean,
            applied,
            selected,
            before_rows=before_rows,
            components=components,
            folder=folder,
        )
        if stopped is not None:
            stopped["outputs"]["inputs"]["control_selection"] = selection or {}
            return stopped
        before, reference, path = (states[n]["path"] for n in ("before", "clean", "applied"))
        expected, measured = (states[n]["lengths"] for n in ("clean", "applied"))
        result = check_stage(
            kernel,
            stage,
            {
                "path": str(path),
                "symmetry_axis": 1,
                "previous_free": _free(kernel, before),
                "junction_lengths_m": measured,
                "clean_junction_lengths_m": expected,
            },
        )
        boundaries = {n: s["records"] for n, s in states.items()}
        result["checks"].extend(
            {**c, "where": {**c["where"], "boundary": name}}
            for name, rs in boundaries.items()
            for r in rs
            for c in r["checks"]
            if c["status"] != "skipped"
        )
        missing = sum(length <= 0 for length in expected.values())
        result["checks"].append(
            check_entry(
                f"control.{stage.lower()}.reference_junction",
                "failed" if missing else "passed",
                missing,
                0,
                unit="absent junctions",
            )
        )
        result["outputs"]["assembly_records"] = boundaries
        result["outputs"]["length_method"] = "integral of native curve derivatives"
        result["outputs"]["inputs"]["control_selection"] = selection or {}
        result["outputs"]["inputs"]["clean_geometry"] = {
            "path": str(reference),
            "sha256": file_sha256(reference),
        }
        result["outputs"]["inputs"]["previous_geometry"] = {
            "path": str(before),
            "sha256": file_sha256(before),
        }
        return result
    finally:
        kernel.close()
