# GEOVERSE_HEADER
# file_version: 1.2.6
# last_modified_at: 2026-09-27T23:51:00.036Z
# last_modified_by: OpenAI / Codex / unknown / api-designer-pyflightstream
# dependencies: [pyflightstream.post.writers]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: Catalog manifest-bound release refusal sites while retaining builtin catches.
# revision_source: git
"""Serialize sampled velocity fields without interpolation or frame inference."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np

from pyflightstream._digest import file_sha256
from pyflightstream._errors import ProductError
from pyflightstream.post.field_frames import field_in_reference, native_velocity_proof
from pyflightstream.post.writers import (
    OutputProvenance,
    _write_pair,
    write_vtk_points,
)
from pyflightstream.script.motion import resolve_frame_motion


def _validate_field(points_m, velocity_m_s, frame, formats, reusable_inflow):
    """Validate a complete field without creating any output."""
    points = np.asarray(points_m, dtype=float)
    velocity = np.asarray(velocity_m_s, dtype=float)
    if frame != "REFERENCE":
        raise ProductError("probe field export requires the explicit REFERENCE frame")
    if points.ndim != 2 or points.shape[1:] != (3,) or velocity.shape != points.shape:
        raise ProductError("probe positions and velocities must both be (N, 3)")
    if not len(points) or not np.isfinite(points).all() or not np.isfinite(velocity).all():
        raise ProductError("probe positions and velocities must be nonempty and finite")
    if len(set(formats)) != len(formats) or any(f not in ("vtk", "tecplot") for f in formats):
        raise ProductError("field formats are distinct vtk and/or tecplot names")
    if not formats and not reusable_inflow:
        raise ProductError("select a field format or reusable inflow")
    if reusable_inflow:
        if not np.all(points[:, 0] == points[0, 0]):
            raise ProductError("reusable inflow requires one global YZ plane (constant x)")
        if len(np.unique(points, axis=0)) != len(points):
            raise ProductError("reusable inflow cannot contain duplicate sample positions")
        if np.linalg.matrix_rank(points[:, 1:] - points[0, 1:]) < 2:
            raise ProductError("reusable inflow requires a two-dimensional YZ survey")
    return points, velocity


def write_probe_field(
    stem: str | Path,
    points_m: np.ndarray,
    velocity_m_s: np.ndarray,
    *,
    source: str | Path,
    provenance: OutputProvenance,
    frame: str = "REFERENCE",
    formats: Sequence[str] = ("vtk",),
    reusable_inflow: bool = False,
    sample_metadata: Mapping[str, object] | None = None,
    overwrite: bool = False,
) -> list[Path]:
    """Write reference-frame samples as VTK/Tecplot and optional custom inflow.

    Both arrays are finite (N, 3), in meters and m/s. No cells, surface
    interpolation or moving-frame transform is inferred. Reusable inflow is an
    unstructured global YZ-plane profile; the user validates and installs it.
    Every file carries solver setup and a source-byte hash in its provenance.
    """
    points, velocity = _validate_field(points_m, velocity_m_s, frame, formats, reusable_inflow)
    metadata = {
        **dict(sample_metadata or {}),
        "source_file": Path(source).name,
        "source_sha256": file_sha256(Path(source)),
        "frame": frame,
        "coordinate_units": "m",
        "velocity_units": "m/s",
        "topology": "vertex-cloud",
        "sample_count": len(points),
        "variables": {"X": "x", "Y": "y", "Z": "z", "Velocity": ["vx", "vy", "vz"]},
        "inflow_form": "UNSTRUCTURED" if reusable_inflow else None,
    }
    record = OutputProvenance(**{**provenance.model_dump(), "sampling": metadata})
    written: list[Path] = []
    if "vtk" in formats:
        written.extend(
            write_vtk_points(
                Path(str(stem) + ".vtk"),
                points,
                {"Velocity": velocity},
                provenance=record,
                overwrite=overwrite,
            )
        )
    if "tecplot" in formats:
        lines = [
            'TITLE = "Reference-frame velocity samples"',
            'VARIABLES = "X" "Y" "Z" "Velocity_x" "Velocity_y" "Velocity_z"',
        ]
        for index, row in enumerate(np.column_stack((points, velocity)), 1):
            lines.append(
                f'ZONE T="Sample {index}", I=1, J=1, K=1, ZONETYPE=ORDERED, DATAPACKING=POINT'
            )
            lines.append(" ".join(f"{float(value):.17g}" for value in row))
        written.extend(
            _write_pair(
                Path(str(stem) + ".dat"),
                "\n".join(lines) + "\n",
                record,
                overwrite=overwrite,
            )
        )
    if reusable_inflow:
        text = (
            "\n".join(
                " ".join(f"{float(value):.17g}" for value in row)
                for row in np.column_stack((points, velocity))
            )
            + "\n"
        )
        written.extend(
            _write_pair(
                Path(str(stem) + ".inflow.dat"),
                text,
                record,
                overwrite=overwrite,
            )
        )
    return written


def write_recorded_probe_fields(
    table,
    record,
    directory,
    point_name,
    *,
    prepare=None,
    step_source=None,
):
    """Export complete recorded samples; preserve each actual STEP separately."""
    import csv

    from pyflightstream.script.solver_setup import SolverSetup

    if not record.probe_field_layout:
        return []
    if record.solver_setup is None:
        raise ProductError("probe fields need the run's recorded solver setup")
    source = Path(table)
    with source.open(encoding="utf-8-sig", newline="") as stream:
        rows = [{str(k).upper(): v for k, v in row.items()} for row in csv.DictReader(stream)]
    required = {"PROBE", "X", "Y", "Z", "VX", "VY", "VZ"}
    if not rows or not required <= rows[0].keys():
        raise ProductError("probe field table lacks sample identity, XYZ or VX/VY/VZ")
    groups = {}
    for row in rows:
        raw_step = row.get("STEP", "NA")
        step = "NA"
        if raw_step not in ("NA", "", None):
            value = float(raw_step)
            if not np.isfinite(value):
                raise ProductError("probe field STEP must be finite")
            step = format(value, ".17g")
        group = groups.setdefault(step, {})
        number = float(row["PROBE"])
        if not number.is_integer() or int(number) in group:
            raise ProductError("probe field table has invalid or duplicate sample IDs")
        group[int(number)] = row
    step_evidence = None
    if step_source is not None:
        with Path(step_source).open(encoding="utf-8-sig", newline="") as stream:
            native_rows = list(csv.DictReader(stream))
        if not native_rows or "Time-step" not in native_rows[0]:
            raise ProductError(
                "field products require the native Time-step column; no ordinal STEP"
            )
        native_steps = [float(row["Time-step"]) for row in native_rows]
        if not np.isfinite(native_steps).all() or len(set(native_steps)) != len(native_steps):
            raise ProductError("native STEP values must be finite and unique")
        if set(groups) != {format(value, ".17g") for value in native_steps}:
            raise ProductError("field STEP values differ from the recorded native history")
        step_evidence = {"path": str(step_source), "sha256": file_sha256(Path(step_source))}
    provenance = OutputProvenance(
        run_id=record.run_id,
        campaign=getattr(record, "campaign", None),
        setup=SolverSetup.model_validate(record.solver_setup),
    )
    jobs = []
    for layout in record.probe_field_layout:
        ids = layout["probe_ids"]
        factor = float(layout["native_to_m"])
        if not np.isfinite(factor) or factor <= 0 or len(set(ids)) != len(ids):
            raise ProductError("invalid recorded probe unit conversion or sample IDs")
        for step, group in groups.items():
            if not set(ids) <= group.keys():
                raise ProductError(f"probe field at step {step} is missing recorded samples")
            selected = [group[i] for i in ids]
            if any(row.get("FRAME", layout["frame"]) != layout["frame"] for row in selected):
                raise ProductError("probe table FRAME differs from its recorded sampling frame")
            points = np.array([[float(row[a]) for a in ("X", "Y", "Z")] for row in selected])
            velocity = np.array([[float(row[a]) for a in ("VX", "VY", "VZ")] for row in selected])
            suffix = ""
            if step not in ("NA", "", None):
                value = float(step)
                if not np.isfinite(value):
                    raise ProductError("probe field STEP must be finite")
                suffix = f"_step_{value:.17g}"
            family = (
                "vsec"
                if layout.get("kind") == "volume-section"
                else (f"field_{int(layout['entry']):02d}")
            )
            stem = Path(directory) / f"{point_name}_{family}{suffix}"
            metadata = dict(layout)
            if step_evidence is not None:
                metadata["step_source"] = step_evidence
            points_m = points * factor
            if layout.get("export_kind"):
                coordinate_source = layout.get("coordinate_source")
                if coordinate_source == "native-export-reference":
                    if (
                        layout["export_kind"] != "steady-probe"
                        or layout.get("coordinate_frame_index") != 1
                    ):
                        raise ProductError(
                            "native reference coordinates require a steady-probe contract"
                        )
                    frame_index = 1
                elif coordinate_source == "emitted-local":
                    frame_index = layout.get("frame_index")
                else:
                    raise ProductError("sampled field coordinates lack a proved source contract")
                motions = getattr(record, "frame_motions", None) or {}
                motion = motions.get(frame_index)
                if motion is None:
                    raise ProductError("sampled field has no recorded final frame trajectory")
                identity = {
                    key: getattr(record, key, None) for key in ("fs_exe_sha256", "fs_build")
                }
                motion = resolve_frame_motion(motion, solver_identity=identity)
                proof = native_velocity_proof(
                    motion, solver_identity=identity, export_kind=layout["export_kind"]
                )
                original = layout.get("points_native")
                if (
                    coordinate_source == "emitted-local"
                    and original is not None
                    and not np.array_equal(points, np.asarray(original))
                ):
                    raise ProductError(
                        "probe table coordinates differ from the emitted local samples"
                    )
                points_m, velocity = field_in_reference(
                    points,
                    velocity,
                    motion,
                    step=None if step == "NA" else float(step),
                    native_to_m=factor,
                    velocity_proof=proof,
                    solver_identity=identity,
                    export_kind=layout["export_kind"],
                )
                metadata.update(
                    declared_frame=layout["frame"],
                    frame="REFERENCE",
                    frame_motion=motion,
                    velocity_convention=proof,
                )
            jobs.append((stem, points_m, velocity, metadata, step))
    destinations = set()
    for stem, points, velocity, layout, _step in jobs:
        _validate_field(
            points,
            velocity,
            layout["frame"],
            layout["formats"],
            layout.get("reusable_inflow", False),
        )
        key = str(stem).casefold()
        if key in destinations:
            raise ProductError("recorded probe fields produce colliding output names")
        destinations.add(key)
    written = []
    Path(directory).mkdir(parents=True, exist_ok=True)
    for stem, points, velocity, layout, step in jobs:
        if prepare is not None:
            suffixes = [".vtk" if f == "vtk" else ".dat" for f in layout["formats"]]
            if layout.get("reusable_inflow"):
                suffixes.append(".inflow.dat")
            for suffix in suffixes:
                prepare(Path(str(stem) + suffix))
                prepare(Path(str(stem) + suffix + ".provenance.json"))
        written.extend(
            write_probe_field(
                stem,
                points,
                velocity,
                source=source,
                provenance=provenance,
                frame=layout["frame"],
                formats=layout["formats"],
                reusable_inflow=layout.get("reusable_inflow", False),
                sample_metadata={**layout, "step": step},
            )
        )
    return written
