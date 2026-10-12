"""What the plan reads of a built geometry, and the warnings of the in-row routes (FR-473, FR-476).

Pipeline role: the workspace row, called by the matrix binding for each row
that names a geometry (:func:`judge_the_row_geometry`). Where a
``<stem>.build.json`` lies beside the geometry the row names, the plan refuses
a body whose instruction or source changed after the build (G-Q7), and warns
when the built file itself was saved again, when the body was never accepted
(G-Q6), when its audit failed (G-Q8) and when the row's ``FS_BUILD`` is not the
build that made it (G-Q11). A row whose geometry has no record is planned as
before.

THE IN-ROW ROUTES WARN IN 0.40.0 (G-Q1, option A). A row naming a CCS, IGES or
STL file, or a sidecar whose ``[[import.operations]]`` scale, rename or mirror,
still runs exactly as in 0.39.0 and is warned with the exact replacement; 0.41.0
refuses it.
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

#: The geometry files a row names in 0.39.0 that the geometry stage now builds.
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
        return record, json.loads(record.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise InputArtifactError(f"{record} cannot be read as a build record: {error}") from error


def _rebuild_command(record: Path, data: Mapping[str, Any]) -> str:
    instruction = (record.parent / str(data.get("instruction", {}).get("file", ""))).resolve()
    return f"pyfs-workspace geometry build {instruction.parent.name} --apply --overwrite"


def _changed_inputs(record: Path, data: Mapping[str, Any]) -> list[str]:
    changed = []
    stated = [data.get("instruction", {}), *data.get("inputs", [])]
    for item in stated:
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
            f"describes. Rebuild it with `{_rebuild_command(record, data)}` ({_PAGE})."
        )
    outputs = [
        item
        for item in data.get("outputs", [])
        if Path(str(item.get("file", ""))).name == geometry.name
    ]
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
        f"replaces and 0.41.0 refuses. Write the instruction with `pyfs-workspace geometry "
        f"from-sidecar {geometry.name} --apply`, build it with `pyfs-workspace geometry "
        f"build {folder} --apply`, and name {built} in the GEOMETRY cell ({_PAGE}).",
        PyflightstreamWarning,
        stacklevel=3,
    )


def judge_the_row_geometry(
    geometry: Path, pol: str, *, fs_build: str | None, mesh_import: MeshImport | None
) -> None:
    """Judge the geometry one row names: its build record and its route (FR-473, FR-476).

    Raises
    ------
    InputArtifactError
        A built body whose instruction or a recorded input changed after the build.
    """
    _judge_the_record(geometry, pol, fs_build)
    _warn_in_row_routes(geometry, pol, mesh_import)
