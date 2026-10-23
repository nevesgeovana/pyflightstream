"""What the plan reads of a built geometry, and the warnings of the in-row routes (FR-473, FR-476).

Pipeline role: the workspace row, called by the matrix binding for each row
that names a geometry (:func:`judge_the_row_geometry`). Where a
``<stem>.build.json`` lies beside the geometry the row names, the plan refuses
a body whose instruction or source changed after the build (G-Q7), and warns
when the built file itself was saved again, when the body was never accepted
(G-Q6), when its audit failed (G-Q8) and when the row's ``FS_BUILD`` is not the
build that made it (G-Q11). A row whose geometry has no record is planned as
before.

The in-row routes warn with their replacement (G-Q1, option A): a row naming
a CCS, IGES or STL file, or sidecar ``[[import.operations]]`` that scale,
rename or mirror. The warning states 0.41.0 as the removal version.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pyflightstream._digest import file_sha256
from pyflightstream._errors import InputArtifactError, PyflightstreamWarning, warn
from pyflightstream.cases._ccs import CCS_FORMATS
from pyflightstream.cases._geometry_instruction import BUILD_RECORD_SUFFIX, GEOMETRY_PAGE
from pyflightstream.cases.mesh import MeshImport

__all__ = [
    "IN_ROW_GEOMETRY_SUFFIXES",
    "MOVED_OPERATIONS",
    "build_record_of",
    "judge_the_row_geometry",
]

#: The suffix of a build record, beside the body it describes.
_RECORD_SUFFIX = BUILD_RECORD_SUFFIX

#: Geometry formats handled by the geometry stage rather than the run row.
IN_ROW_GEOMETRY_SUFFIXES = frozenset({*CCS_FORMATS, ".igs", ".iges", ".stl"})

#: The sidecar operations that leave the run for the instruction file.
MOVED_OPERATIONS = ("scale", "rename", "mirror")

_PAGE = GEOMETRY_PAGE


def build_record_of(geometry: Path) -> tuple[Path, dict[str, Any]] | None:
    """Return the build record beside a geometry, or None where the body was not built."""
    record = geometry.with_name(geometry.stem + _RECORD_SUFFIX)
    if not record.is_file():
        return None
    try:
        data = json.loads(record.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise InputArtifactError(f"{record} cannot be read as a build record: {error}") from error
    if not isinstance(data, dict):
        raise InputArtifactError(f"{record} cannot be read as a build record: expected an object")
    return record, data


def _rebuild_command(record: Path, data: Mapping[str, Any]) -> str:
    instruction = (record.parent / str(data.get("instruction", {}).get("file", ""))).resolve()
    return f"pyfs-workspace geometry build {instruction.parent.name} --apply --overwrite"


def _changed_inputs(record: Path, data: Mapping[str, Any]) -> list[str]:
    changed = []
    inputs = data.get("inputs", [])
    if not isinstance(inputs, list):
        raise InputArtifactError(
            f"{record} cannot be read as a build record: inputs must be a list"
        )
    stated = [("instruction", data.get("instruction", {}))] + [
        (f"inputs[{index}]", item) for index, item in enumerate(inputs)
    ]
    for label, item in stated:
        for key in ("file", "sha256"):
            if not isinstance(item, dict) or key not in item:
                raise InputArtifactError(
                    f"{record} cannot be read as a build record: missing key {label}.{key}. "
                    "Rebuild it with pyfs-workspace geometry build from an instruction "
                    f"({_PAGE})."
                )
            if not isinstance(item[key], str) or not item[key]:
                raise InputArtifactError(
                    f"{record} cannot be read as a build record: {label}.{key} "
                    "must be a nonempty string."
                )
        path = (record.parent / str(item["file"])).resolve()
        if not path.is_file() or file_sha256(path) != item["sha256"]:
            changed.append(path.name)
    return changed


def _judge_the_record(geometry: Path, pol: str, fs_build: str | None) -> None:
    found = build_record_of(geometry)
    if found is None:
        return
    record, data = found
    where = f"matrix row POL {pol} names {geometry.name}"
    changed = _changed_inputs(record, data)
    if changed:
        raise InputArtifactError(
            f"{where}, built from an instruction whose inputs changed after the build "
            f"({', '.join(changed)}): the body on disk is not the one the instruction now "
            "describes. Hashes compare raw bytes, including line endings. "
            f"Rebuild it with `{_rebuild_command(record, data)}` ({_PAGE})."
        )
    listed = data.get("outputs", [])
    if not isinstance(listed, list) or not all(isinstance(item, dict) for item in listed):
        # F-1507: a malformed entry is a refusal naming the record, never an AttributeError.
        raise InputArtifactError(
            f"{record} cannot be read as a build record: outputs must be a list of "
            "objects, each with a file and a sha256."
        )
    outputs = [item for item in listed if Path(str(item.get("file", ""))).name == geometry.name]
    if outputs and geometry.is_file() and file_sha256(geometry) != outputs[0].get("sha256"):
        warn(
            f"{where}, and the file no longer hashes as its build recorded: it was saved again "
            f"after the build, so {record.name} no longer describes it ({_PAGE}).",
            PyflightstreamWarning,
            stacklevel=3,
        )
    if data.get("inspected") is None:
        warn(
            f"{where}, which was built and never accepted; look at its preview "
            f"({geometry.stem}.preview.vtk) and record the check with "
            f"`pyfs-workspace geometry accept {geometry.parent.name}` ({_PAGE}).",
            PyflightstreamWarning,
            stacklevel=3,
        )
    audit = data.get("audit", {})
    if audit.get("passed") is False:
        warn(
            f"{where}, whose build audit failed: "
            f"{', '.join(audit.get('failed', [])) or 'see the audit'}.",
            PyflightstreamWarning,
            stacklevel=3,
        )
    built_on = data.get("solver", {}).get("build_id")
    if fs_build and built_on and str(built_on) != str(fs_build):
        warn(
            f"{where}, built on FS_BUILD {built_on}, and the row runs on {fs_build}; a body "
            "saved by one build is opened by another (probe G-09 settles whether that holds).",
            PyflightstreamWarning,
            stacklevel=3,
        )


def _warn_a_mirrored_deflection(geometry: Path, pol: str, symmetry: str | None) -> None:
    """Warn on a MIRROR row whose body carries a deflected control surface (FR-1124)."""
    if (symmetry or "").strip().upper() != "MIRROR":
        return
    found = build_record_of(geometry)
    if found is None:
        return
    deflected = [
        surface
        for surface in found[1].get("control_surfaces", [])
        if float(surface.get("angle_deg", 0.0)) != 0.0
    ]
    if not deflected:
        return
    angles = ", ".join(f"{s.get('name')} at {s.get('angle_deg')} deg" for s in deflected)
    warn(
        f"matrix row POL {pol} mirrors {geometry.name} (SYMMETRY MIRROR), whose control "
        f"surface is deflected ({angles}): a mirrored half deflects both sides alike. "
        f"Write SYMMETRY NONE for a one-sided deflection ({_PAGE}).",
        PyflightstreamWarning,
        stacklevel=3,
    )


def _warn_in_row_routes(geometry: Path, pol: str, mesh_import: MeshImport | None) -> None:
    suffix = geometry.suffix.lower()
    moved = (
        []
        if mesh_import is None
        else [op.op for op in mesh_import.operations if op.op in MOVED_OPERATIONS]
    )
    if suffix not in IN_ROW_GEOMETRY_SUFFIXES and not moved:
        return
    folder = geometry.parent.name if geometry.parent.name != "geometries" else geometry.stem
    built = (
        f"{geometry.stem}.fsm"
        if suffix in IN_ROW_GEOMETRY_SUFFIXES - {".stl"}
        else f"{geometry.stem}.obj"
    )
    what = (
        f"the {suffix} file {geometry.name}"
        if suffix in IN_ROW_GEOMETRY_SUFFIXES
        else f"the sidecar operations {', '.join(sorted(set(moved)))} of {geometry.name}"
    )
    warn(
        f"matrix row POL {pol} builds {what} inside the run, a route the geometry stage "
        "replaces; this route currently warns without refusing. Write the instruction with "
        "`pyfs-workspace geometry "
        f"from-sidecar {geometry.name} --apply`, build it with `pyfs-workspace geometry "
        f"build {folder} --apply`, and name {built} in the GEOMETRY cell ({_PAGE}).",
        PyflightstreamWarning,
        stacklevel=3,
    )


def judge_the_row_geometry(
    geometry: Path,
    pol: str,
    *,
    fs_build: str | None,
    mesh_import: MeshImport | None,
    symmetry: str | None = None,
) -> None:
    """Judge the geometry one row names: its build record and its route (FR-473, FR-476).

    Raises
    ------
    InputArtifactError
        A built body whose instruction or a recorded input changed after the build.
    """
    _judge_the_record(geometry, pol, fs_build)
    _warn_a_mirrored_deflection(geometry, pol, symmetry)
    _warn_in_row_routes(geometry, pol, mesh_import)
