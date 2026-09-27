# GEOVERSE_HEADER
# file_version: 1.0.0
# last_modified_at: 2026-09-27T18:37:42.350Z
# last_modified_by: OpenAI / Codex / GPT-6 / implementer
# dependencies: [pyflightstream.results.surface, pyflightstream.results.SurfaceSection]
# authority: pyflightstream
# status: draft
# confidentiality: public
# change_summary: Use measured native XYZ convention and original polygon cut-plane chords.
# revision_source: git
"""Raw VTK boundary-layer scalars at recorded surface-section cut points.

A shared edge belongs to every incident source cell. Values are never averaged,
interpolated to nodes, converted to a guessed thickness unit, or turned into a
wall-normal velocity profile.
"""

from __future__ import annotations

import csv
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from pyflightstream._digest import file_sha256
from pyflightstream._errors import PyflightstreamError
from pyflightstream.post._tables import ProductError
from pyflightstream.results import SurfaceSection, parse_surface_sections
from pyflightstream.results.surface import (
    REFERENCE_FRAME,
    SurfaceFrame,
    VtkSurface,
    read_vtk_surface,
)

if TYPE_CHECKING:
    from pyflightstream.cases import PprocSpec
    from pyflightstream.workspace import RunRecord

BL_FIELDS = (
    "BL_Thickness",
    "BL_displacement_thickness",
    "BL_momentum_thickness",
    "BL_shape_factor",
    "BL_streamline_length",
    "Transition_marker",
    "Separation_marker",
    "skin_friction_coeff.",
    "Normalized_Vorticity",
    "Cp_freestream",
    "Static_pressure_ratio",
    "Boundary_Index",
)
BL_COLUMNS = ("SECTION", "CUT_POINT", "CELL_ID", "INCIDENT_CELLS", "X", "Y", "Z", *BL_FIELDS)


@dataclass(frozen=True)
class BoundaryLayerSamples:
    """Cell-associated rows and the exact fields available in their VTK source."""

    rows: tuple[dict[str, object], ...]
    available_fields: tuple[str, ...]
    missing_fields: tuple[str, ...]
    tolerance: float


def _on_section_chord(
    point: np.ndarray, vertices: np.ndarray, normal: np.ndarray, tolerance: float
) -> bool:
    """Intersect the original edges with the recorded cut plane, without triangulation."""
    signed = (vertices - point) @ normal
    cuts: list[np.ndarray] = []
    for index, a in enumerate(vertices):
        b = vertices[(index + 1) % len(vertices)]
        da, db = signed[index], signed[(index + 1) % len(vertices)]
        if abs(float(da)) <= tolerance:
            cuts.append(a)
        if da * db < 0:
            cuts.append(a + (da / (da - db)) * (b - a))
    unique: list[np.ndarray] = []
    for cut in cuts:
        if not any(np.linalg.norm(cut - other) <= tolerance for other in unique):
            unique.append(cut)
    if len(unique) != 2:
        return False  # Coplanar or ambiguous multiple chords need the planar test.
    a, b = unique
    vector = b - a
    squared = float(vector @ vector)
    if squared == 0:
        return False
    along = float((point - a) @ vector) / squared
    closest = a + np.clip(along, 0, 1) * vector
    return bool(np.linalg.norm(point - closest) <= tolerance)


def _incident(point: np.ndarray, vertices: np.ndarray, tolerance: float) -> bool:
    """Test edges exactly, then interiors of planar polygons without triangulation."""
    edges = np.roll(vertices, -1, axis=0) - vertices
    squared = np.einsum("ij,ij->i", edges, edges)
    usable = squared > 0
    if not np.any(usable):
        return False
    origins, vectors, lengths = vertices[usable], edges[usable], squared[usable]
    along = np.einsum("ij,ij->i", point - origins, vectors) / lengths
    closest = origins + np.clip(along, 0, 1)[:, None] * vectors
    if np.any(np.linalg.norm(closest - point, axis=1) <= tolerance):
        return True
    shifted = vertices - vertices[0]
    normal = np.cross(shifted, np.roll(shifted, -1, axis=0)).sum(axis=0)
    length = float(np.linalg.norm(normal))
    if length == 0:
        return False
    normal /= length
    if np.max(np.abs((vertices - vertices[0]) @ normal)) > tolerance:
        return False  # A warped interior has no uniquely proved planar placement.
    if abs(float((point - vertices[0]) @ normal)) > tolerance:
        return False
    keep = [axis for axis in range(3) if axis != int(np.argmax(np.abs(normal)))]
    x, y = point[keep]
    polygon = vertices[:, keep]
    inside = False
    for a, b in zip(polygon, np.roll(polygon, -1, axis=0), strict=True):
        if (a[1] > y) != (b[1] > y):
            crossing = a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if x < crossing:
                inside = not inside
    return inside


def sample_boundary_layer(
    surface: VtkSurface,
    sections: Sequence[SurfaceSection],
    *,
    surface_frame: SurfaceFrame,
    section_frames: Mapping[int, SurfaceFrame],
    section_normals: Mapping[int, Sequence[float]] | None = None,
    tolerance: float | None = None,
) -> BoundaryLayerSamples:
    """Associate actual cut points with source cells in a common reference frame.

    Coordinates and placement origins use the simulation length unit. Scalars
    retain their native values. CELL_ID is the original zero-based VTK polygon
    index; Boundary_Index remains the raw solver scalar, with no inferred name.
    Shared edges produce one row per incident cell. Missing scalar fields are
    None (NA in CSV); missing geometry or placement is refused explicitly.
    """
    available = tuple(name for name in BL_FIELDS if name in surface.cell_data)
    missing = tuple(name for name in BL_FIELDS if name not in surface.cell_data)
    if not any(name in available for name in BL_FIELDS[:4]):
        raise ProductError("VTK has no boundary-layer CELL_DATA; integral product unavailable")
    if surface.n_cells == 0 or surface.n_points == 0:
        raise ProductError("VTK has no cells to associate with section samples")
    for name in available:
        values = np.asarray(surface.cell_data[name])
        if values.shape != (surface.n_cells,) or not np.all(np.isfinite(values)):
            raise ProductError(f"VTK {name} does not provide one finite value per cell")
    points = surface_frame.to_reference(surface.points)
    scale = float(np.linalg.norm(np.ptp(points, axis=0)))
    distance = max(1e-10, scale * 1e-7) if tolerance is None else float(tolerance)
    if not np.isfinite(distance) or distance <= 0:
        raise ProductError("section-cell tolerance must be finite and positive")
    polygons = [
        points[surface.connectivity[a:b]]
        for a, b in zip(surface.offsets[:-1], surface.offsets[1:], strict=True)
    ]
    lower = np.array([vertices.min(axis=0) for vertices in polygons])
    upper = np.array([vertices.max(axis=0) for vertices in polygons])
    rows: list[dict[str, object]] = []
    for section in sections:
        frame = section_frames.get(section.index)
        if frame is None:
            raise ProductError(f"section {section.index} has no proved placement")
        located = frame.to_reference(section.positions)
        normal_value = None if section_normals is None else section_normals.get(section.index)
        normal: np.ndarray | None = None
        if normal_value is not None:
            normal = np.asarray(normal_value, dtype=float)
            if normal.shape != (3,) or not np.all(np.isfinite(normal)):
                raise ProductError("section cut normal must be a finite three-vector")
            length = float(np.linalg.norm(normal))
            if length == 0:
                raise ProductError("section cut normal must be nonzero")
            normal = normal / length
        for sample, point in enumerate(located, 1):
            candidates = np.flatnonzero(
                np.all((point >= lower - distance) & (point <= upper + distance), axis=1)
            )
            cells = [
                int(cell)
                for cell in candidates
                if _incident(point, polygons[cell], distance)
                or (
                    normal is not None
                    and _on_section_chord(point, polygons[cell], normal, distance)
                )
            ]
            if not cells:
                raise ProductError(
                    f"section {section.index} sample {sample} has no incident VTK cell; "
                    "check recorded frames, units, state and export precision"
                )
            for cell in cells:
                row: dict[str, object] = {
                    "SECTION": section.index,
                    "CUT_POINT": sample,
                    "CELL_ID": cell,
                    "INCIDENT_CELLS": len(cells),
                    **{axis: float(point[k]) for k, axis in enumerate(("X", "Y", "Z"))},
                }
                row.update(
                    {
                        name: float(surface.cell_data[name][cell]) if name in available else None
                        for name in BL_FIELDS
                    }
                )
                rows.append(row)
    return BoundaryLayerSamples(tuple(rows), available, missing, distance)


def write_boundary_layer_table(path: str | Path, samples: BoundaryLayerSamples) -> Path:
    """Write raw cell values with round-trip float precision and explicit NA fields.

    The caller applies its archive/overwrite policy before invoking this writer.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(BL_COLUMNS)
        for row in samples.rows:
            writer.writerow(
                "NA"
                if row[key] is None
                else format(row[key], ".17g")
                if isinstance(row[key], float)
                else row[key]
                for key in BL_COLUMNS
            )
    return target


def _recorded_frame(record: RunRecord, index: object, step: int | None) -> SurfaceFrame:
    from pyflightstream.post.field_frames import frame_pose

    if not isinstance(index, int) or isinstance(index, bool):
        raise ProductError("BL source has no recorded integer frame identity")
    ledger = record.frame_motions or {}
    motion = ledger.get(index)
    if motion is None:
        raise ProductError(f"BL frame {index} has no recorded placement/motion proof")
    pose = frame_pose(
        motion,
        step=step,
        solver_identity={
            "fs_exe_sha256": record.fs_exe_sha256,
            "fs_build": record.fs_build,
        },
    )
    return SurfaceFrame.from_record(
        {
            "frame": index,
            "origin": pose.origin_native.tolist(),
            "axes": pose.basis.T.tolist(),
        }
    )


def _section_count(block: Mapping[str, object]) -> int:
    value = block.get("count")
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ProductError("BL section layout requires a positive integer count per block")
    return value


def write_boundary_layer_products(
    *,
    sim_dir: Path,
    record: RunRecord,
    stem: str,
    out: Path,
    target: Callable[[Path], Path],
    skipped: dict[str, str],
    step: int | None,
    pproc: PprocSpec | None,
) -> tuple[list[Path], dict[str, dict[str, object]]]:
    """Write a final-state point product from its exact VTK and section exports.

    Missing source fields are named in the manifest and written NA. Missing
    placement, cut coordinates, state or original-cell association skips this
    product explicitly. No solver is run and no nearest-cell substitute is used.
    """
    if pproc is None or not pproc.products.boundary_layer_integrals:
        return [], {}
    relative = f"sections/{stem}_boundary_layer.csv"
    try:
        sources: dict[str, Path] = {}
        hashes: dict[str, str] = {}
        for kind, name in (("vtk", f"{stem}.vtk"), ("sections", f"{stem}_cp.txt")):
            matches = [output for output in record.outputs if Path(output).name == name]
            if len(matches) != 1:
                raise ProductError(f"BL product needs one recorded {name}; found {len(matches)}")
            path = sim_dir / matches[0]
            digest = file_sha256(path)
            expected = record.outputs_sha256.get(matches[0])
            if expected and digest != expected:
                raise ProductError(f"BL source {name} changed since collection")
            sources[kind], hashes[name] = path, digest
        sections = parse_surface_sections(sources["sections"].read_text(encoding="utf-8"))
        layout = record.sections_layout
        if not layout or sum(_section_count(block) for block in layout) != sections.count:
            raise ProductError("BL product requires the recorded layout covering every cut section")
        loads_indices = {block.get("loads_frame_index") for block in layout}
        if len(loads_indices) != 1:
            raise ProductError("BL cuts disagree on their recorded VTK loads frame")
        surface_frame = _recorded_frame(record, loads_indices.pop(), step)
        frames: dict[int, SurfaceFrame] = {}
        normals: dict[int, Sequence[float]] = {}
        units: set[str] = set()
        cursor = 0
        for block in layout:
            frame = _recorded_frame(record, block.get("frame_index"), step)
            motion = (record.frame_motions or {}).get(frame.index, {})
            unit = motion.get("length_unit")
            if not isinstance(unit, str) or not unit:
                raise ProductError("BL section frame has no recorded simulation length unit")
            units.add(unit)
            axis = {"XY": 2, "XZ": 1, "YZ": 0}.get(str(block.get("plane")))
            if axis is None:
                raise ProductError("BL section layout has no proved XY/XZ/YZ cut plane")
            for section in sections.sections[cursor : cursor + _section_count(block)]:
                # Native XYZ columns are REFERENCE coordinates; only the cut normal
                # uses the configured section frame (measured on 26.124).
                frames[section.index] = REFERENCE_FRAME
                normals[section.index] = frame.axes[axis]
            cursor += _section_count(block)
        source_unit = (record.frame_motions or {}).get(surface_frame.index, {}).get("length_unit")
        if len(units) != 1 or source_unit not in units:
            raise ProductError(
                "BL source and section frames do not prove one simulation length unit"
            )
        sampled = sample_boundary_layer(
            read_vtk_surface(sources["vtk"]),
            sections.sections,
            surface_frame=surface_frame,
            section_frames=frames,
            section_normals=normals,
        )
        path = write_boundary_layer_table(target(out / relative), sampled)
    except (OSError, ValueError, KeyError, TypeError, PyflightstreamError) as error:
        skipped[relative] = f"boundary_layer_integrals unavailable: {error}"
        return [], {}
    return [path], {
        relative: {
            "kind": "boundary_layer_integrals",
            "runs": [record.run_id],
            "step": step,
            "source_sha256": hashes,
            "available_fields": list(sampled.available_fields),
            "unavailable_fields": list(sampled.missing_fields),
            "section_blocks": layout,
            "cell_index_base": 0,
            "association": "each original VTK cell incident on each recorded cut point",
            "coordinate_frame": "REFERENCE",
            "section_xyz_frame": "native exported XYZ are REFERENCE",
            "warped_cell_rule": "recorded section plane intersects original polygon edges",
            "coordinate_unit": source_unit,
            "scalar_units": "native VTK values, unchanged; no inferred thickness conversion",
            "boundary_index": "raw solver value; no inferred inventory-name mapping",
            "matching_tolerance_native": sampled.tolerance,
            "empty_sections": [section.index for section in sections.sections if not section.count],
        }
    }
