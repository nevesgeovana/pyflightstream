# GEOVERSE_HEADER
# file_version: 1.0.2
# file_role: continued-field-motion-evidence
# last_modified_at: 2026-09-27T20:01:58.425Z
# last_modified_by: OpenAI / Codex / GPT-6 / implementation-agent
# dependencies: [pyflightstream.script.motion]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: Validate and preserve inherited sampling positions and solver setup.
# revision_source: git
"""Carry a saved state's frame facts without treating OPEN as new geometry."""

import csv
from copy import deepcopy
from math import isclose
from pathlib import Path


def continued_frame_motions(previous, script):
    """Copy inherited motion facts; refuse to assert them after unproved changes."""
    if not previous:
        return None
    result = deepcopy(previous)
    current = script.frame_motions
    commands = current.get(1, {}).get("command_provenance", [])
    geometry_changed = script.raw_flag or any(
        item.get("name") != "SET_SOLVER_UNSTEADY" for item in commands
    )
    unit = script.simulation_length_unit
    for record in result.values():
        reasons = []
        if geometry_changed:
            reasons.append("continuation changes frame/motion commands or contains raw commands")
        if unit and unit != record.get("length_unit"):
            reasons.append("continuation changes the recorded native coordinate unit")
        trajectory = record.get("trajectory", {})
        if trajectory.get("kind") == "constant_rotation":
            for item in commands:
                if item.get("name") == "SET_SOLVER_UNSTEADY":
                    stated = item.get("args", {}).get("delta_time")
                    old = trajectory.get("dt_s")
                    if (
                        stated is None
                        or old is None
                        or not isclose(float(stated), float(old), rel_tol=1e-12, abs_tol=0.0)
                    ):
                        reasons.append(
                            "continuation changes or cannot prove the recorded time increment"
                        )
        if reasons:
            record["state"] = "unknown"
            record["reason"] = "; ".join(reasons)
            proof = record.setdefault("proof", {})
            proof["timing"] = None
            if geometry_changed or (unit and unit != record.get("length_unit")):
                proof["geometry"] = None
            record["continuation_commands"] = deepcopy(commands)
    return result


def continued_field_inputs(previous, sim_dir):
    """Retain a saved sampling request only with matching recorded point evidence."""
    layout = deepcopy(previous.probe_field_layout)
    if not layout:
        return {}
    if previous.solver_setup is None or not previous.probe_points_file:
        raise ValueError("continued fields need the predecessor's setup and sample-position file")
    root = Path(sim_dir).resolve()
    source = (root / previous.probe_points_file).resolve()
    if not source.is_relative_to(root):
        raise ValueError("continued sample-position evidence escapes the simulation folder")
    with source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["PROBE", "X", "Y", "Z", "FRAME"]:
            raise ValueError("continued sample-position file has an unrecognized header")
        points = {}
        for row in reader:
            number = float(row["PROBE"])
            if not number.is_integer() or int(number) in points:
                raise ValueError("continued sample-position file has invalid sample IDs")
            points[int(number)] = ([float(row[a]) for a in ("X", "Y", "Z")], row["FRAME"])
    for item in layout:
        ids, coordinates = item.get("probe_ids", []), item.get("points_native", [])
        if not ids or len(ids) != len(coordinates):
            raise ValueError("continued field layout has no complete recorded local coordinates")
        expected_frame = (
            "REFERENCE"
            if item.get("coordinate_source") == "native-export-reference"
            else item["frame"]
        )
        for number, xyz in zip(ids, coordinates, strict=True):
            if points.get(number) != (list(xyz), expected_frame):
                raise ValueError("continued sample-position file differs from the recorded layout")
    return {
        "probe_field_layout": layout,
        "probe_points_file": previous.probe_points_file,
        "solver_setup": deepcopy(previous.solver_setup),
    }
