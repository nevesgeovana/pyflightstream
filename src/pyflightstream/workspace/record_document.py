"""Versioned run storage with immutable definitions and resolved in-memory rows.

Only the explicit workspace migration accepts an earlier document. Resolving a
current document never consults today's inputs or changes historical evidence.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from pyflightstream.workspace.manifest import RunStatus, WorkspaceError

__all__ = ["SCHEMA_VERSION", "decode_document", "encode_rows", "read_rows"]

SCHEMA_VERSION = 4
_HEADER = {
    "id": "run_id",
    "point": "point",
    "build": "fs_build",
    "status": "status",
    "started_at": "started_at",
    "finished_at": "finished_at",
}
_BLOCKS = {"solver_setup_id": "solver_setups", "frames_id": "frames", "geometry_id": "geometries"}


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _definition(document: dict, registry: str, value: Any) -> str:
    key = _digest(value)
    document[registry][key] = value
    return key


def _pack_setup(value: Any) -> Any:
    if isinstance(value, dict):
        for command, flag in value.get("flags", {}).items():
            if flag.get("command") == command:
                del flag["command"]
    return value


def _pack_frames(value: Any) -> Any:
    if isinstance(value, dict):
        for index, frame in value.items():
            if (
                isinstance(frame, dict)
                and type(frame.get("frame_index")) is int
                and str(frame["frame_index"]) == str(index)
            ):
                del frame["frame_index"]
    return value


def encode_rows(rows: list[dict]) -> dict:
    """Build one self-contained document without mutating resolved records.

    Parameters
    ----------
    rows : list of dict
        Resolved run records and deletion entries, in their recorded order.

    Returns
    -------
    dict
        Current document containing run headers and immutable shared definitions.
    """
    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "solver_setups": {},
        "frames": {},
        "geometries": {},
        "runs": [],
    }
    document["runs"] = [_encode_row(document, source) for source in rows]
    return document


def _missing_fields(row: dict):
    """Record absent fields so decoding does not invent historical evidence."""
    missing = [
        [key]
        for key in (
            *_HEADER.values(),
            "solver_setup",
            "frame_motions",
            "outputs",
            "outputs_sha256",
        )
        if key not in row
    ]
    setup = row.get("solver_setup")
    if isinstance(setup, dict):
        missing.extend(
            ["solver_setup", "flags", key, "command"]
            for key, flag in setup.get("flags", {}).items()
            if "command" not in flag
        )
    frames = row.get("frame_motions")
    if isinstance(frames, dict):
        missing.extend(
            ["frame_motions", key, "frame_index"]
            for key, frame in frames.items()
            if isinstance(frame, dict) and "frame_index" not in frame
        )
    if isinstance(row.get("executor"), dict) and "argv" not in row["executor"]:
        missing.append(["executor", "argv"])
    return missing


def _pack_artifacts(row: dict, header: dict):
    """Store each output path once while preserving occurrence order."""
    outputs = row.pop("outputs", [])
    hashes = row.pop("outputs_sha256", {})
    paths = list(dict.fromkeys([*outputs, *hashes]))
    for point in row.get("points_ran", []):
        for path in point.get("outputs", []):
            if path not in paths:
                paths.append(path)
    artifacts = [
        {"path": path, **({"sha256": hashes[path]} if path in hashes else {})} for path in paths
    ]
    # The ordinary case needs no second list. Preserve unusual subsets and
    # repeated output occurrences explicitly, rather than inventing evidence.
    if outputs != paths:
        header["artifact_indices"] = [paths.index(path) for path in outputs]
    for point in row.get("points_ran", []):
        if "outputs" in point:
            point["artifact_indices"] = [paths.index(path) for path in point.pop("outputs")]
    header["artifacts"] = artifacts
    header["details"] = row


def _encode_row(document: dict, source: dict):
    """Separate the run header from its immutable definitions."""
    row = copy.deepcopy(source)
    if "deleted_sim" in row:
        return {"deletion": row}
    # JSON object keys are strings on disk. Normalize before recording absent
    # frame fields and hashing definitions so both use the stored key order.
    if isinstance(row.get("frame_motions"), dict):
        row["frame_motions"] = {str(key): value for key, value in row["frame_motions"].items()}
    missing = _missing_fields(row)
    header = {key: row.pop(field, None) for key, field in _HEADER.items()}
    if missing:
        header["unrecorded_fields"] = missing
    if header["status"] not in {str(status) for status in RunStatus}:
        raise WorkspaceError(f"run {header['id']!r}: unknown status {header['status']!r}")
    header["run_folder"] = f"sims/sim_{row['sim_id']}"
    if row.get("point_name"):
        header["run_folder"] += f"/datapoints/DP-{row['point_name']}"
    header["solver_setup_id"] = _definition(
        document, "solver_setups", _pack_setup(row.pop("solver_setup", None))
    )
    header["frames_id"] = _definition(
        document, "frames", _pack_frames(row.pop("frame_motions", {}))
    )
    geometry = {
        key: row.pop(key) for key in ("inventory", "mesh_import", "inventory_source") if key in row
    }
    header["geometry_id"] = _definition(document, "geometries", geometry)
    executor = row.get("executor")
    if isinstance(executor, dict) and "argv" in executor and executor["argv"] == row.get("argv"):
        del executor["argv"]
    _pack_artifacts(row, header)
    return header


def decode_document(document: Any, *, source: str | Path = "runs.json") -> list[dict]:
    """Validate and resolve the current document without converting earlier formats.

    Parameters
    ----------
    document : object
        Parsed JSON document in the current storage format.
    source : str or Path, optional
        Source filename used in a refusal.

    Returns
    -------
    list of dict
        Resolved records with the original evidence and order preserved.

    Raises
    ------
    WorkspaceError
        The document has an old format or invalid references or headers.
    """
    if not isinstance(document, dict) or document.get("schema_version") != SCHEMA_VERSION:
        raise WorkspaceError(
            f"{source}: expected schema_version={SCHEMA_VERSION} with runs and shared definitions; "
            "old record formats require `pyfs-workspace migrate`. See docs/upgrading.md."
        )
    try:
        _validate_registries(document)
        ids: set[str] = set()
        return [_decode_run(document, run, ids, source) for run in document["runs"]]
    except (KeyError, TypeError, ValueError, AttributeError, WorkspaceError) as error:
        raise WorkspaceError(
            f"{source}: invalid schema_version={SCHEMA_VERSION} record: {error}"
        ) from error


def _validate_registries(document: dict):
    """Reject altered shared definitions and a malformed run collection."""
    for registry in _BLOCKS.values():
        if not isinstance(document[registry], dict):
            raise WorkspaceError(f"{registry} must be an object")
        for key, value in document[registry].items():
            if key != _digest(value):
                raise WorkspaceError(f"{registry}.{key}: definition digest differs")
    if not isinstance(document["runs"], list):
        raise WorkspaceError("runs must be an array")


def _restore_definitions(document: dict, run: dict, row: dict):
    """Resolve historical definitions without consulting current inputs."""
    blocks = {
        reference: copy.deepcopy(document[registry][run[reference]])
        for reference, registry in _BLOCKS.items()
    }
    row["solver_setup"] = blocks["solver_setup_id"]
    row["frame_motions"] = blocks["frames_id"]
    geometry = blocks["geometry_id"]
    if not isinstance(geometry, dict) or geometry.keys() - {
        "inventory",
        "mesh_import",
        "inventory_source",
    }:
        raise WorkspaceError(
            "geometry must contain only inventory, mesh_import and inventory_source"
        )
    row.update(geometry)
    setup = row["solver_setup"]
    if isinstance(setup, dict):
        for command, flag in setup.get("flags", {}).items():
            flag.setdefault("command", command)
    frames = row["frame_motions"]
    if isinstance(frames, dict):
        for index, frame in frames.items():
            if isinstance(frame, dict) and str(index).lstrip("-").isdigit():
                frame.setdefault("frame_index", int(index))
    executor = row.get("executor")
    if isinstance(executor, dict):
        executor.setdefault("argv", copy.deepcopy(row.get("argv", [])))


def _restore_artifacts(run: dict, row: dict):
    """Resolve output occurrences and their recorded hashes."""
    artifacts = run["artifacts"]
    paths = [artifact["path"] for artifact in artifacts]
    if len(paths) != len(set(paths)):
        raise WorkspaceError("artifacts has repeated paths")

    def outputs(indices: list[int], paths: list[str] = paths) -> list[str]:
        if any(type(index) is not int or not 0 <= index < len(paths) for index in indices):
            raise WorkspaceError("artifact_indices contains an invalid index")
        return [paths[index] for index in indices]

    row["outputs"] = outputs(run.get("artifact_indices", list(range(len(paths)))))
    row["outputs_sha256"] = {item["path"]: item["sha256"] for item in artifacts if "sha256" in item}
    for point in row.get("points_ran", []):
        if "artifact_indices" in point:
            point["outputs"] = outputs(point.pop("artifact_indices"))


def _remove_unrecorded(run: dict, row: dict):
    """Restore the absence of fields that the original record did not state."""
    for parts in run.get("unrecorded_fields", []):
        if (
            not isinstance(parts, list)
            or not parts
            or not all(isinstance(part, str) for part in parts)
        ):
            raise WorkspaceError("unrecorded_fields must contain nonempty string paths")
        if parts[0] in {"run_id", "status"}:
            raise WorkspaceError(f"unrecorded_fields cannot remove required field {parts[0]!r}")
        target = row
        for key in parts[:-1]:
            target = target[key]
        target.pop(parts[-1], None)


def _decode_run(document: dict, run: dict, ids: set[str], source: str | Path):
    """Resolve and validate one run without changing its history."""
    if "deletion" in run:
        deletion = run["deletion"]
        if not isinstance(deletion, dict) or deletion.get("deleted_sim") is None:
            raise WorkspaceError("deletion must be an object naming deleted_sim")
        return copy.deepcopy(deletion)
    if not isinstance(run["id"], str) or run["id"] in ids:
        raise WorkspaceError(f"duplicate or invalid id {run['id']!r}")
    ids.add(run["id"])
    if run["status"] not in {str(status) for status in RunStatus}:
        raise WorkspaceError(f"unknown status {run['status']!r}")
    row = copy.deepcopy(run["details"])
    for old, new in (("matrix", "matrix_stem"), ("broken_commands", "waived_commands")):
        if old in row:
            raise WorkspaceError(
                f"{source}: {old} was replaced by {new}; run `pyfs-workspace migrate`"
            )
    if any(field in row for field in _HEADER.values()):
        raise WorkspaceError("details repeats a header field")
    row.update({field: run[key] for key, field in _HEADER.items()})
    _restore_definitions(document, run, row)
    _restore_artifacts(run, row)
    _remove_unrecorded(run, row)
    return row


def read_rows(path: Path) -> list[dict]:
    """Read a current manifest; an absent file describes no executed runs.

    Parameters
    ----------
    path : Path
        Manifest file to read without taking a writer lock or changing the file.

    Returns
    -------
    list of dict
        Resolved records, or an empty list when the file is absent.

    Raises
    ------
    WorkspaceError
        The file is unreadable, invalid or requires explicit migration.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as error:
        raise WorkspaceError(f"{path}: cannot read run records: {error}") from error
    return decode_document(document, source=path)
