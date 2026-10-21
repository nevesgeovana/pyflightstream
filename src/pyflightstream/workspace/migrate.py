"""Explicit copy-first migration of the workspace record format."""

from __future__ import annotations

import json
import os
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from pydantic import ValidationError

import pyflightstream._textio as _textio
from pyflightstream.workspace.manifest import (
    MANIFEST_LOCK_POLL_S,
    MANIFEST_LOCK_RENEW_S,
    MANIFEST_LOCK_STALE_S,
    MANIFEST_LOCK_TIMEOUT_S,
    RunRecord,
    WorkspaceError,
    manifest_lock,
)
from pyflightstream.workspace.record_document import SCHEMA_VERSION, decode_document, encode_rows

__all__ = ["migrate_workspace"]


def _other_version_sentence(path: Path, version: object) -> str:
    """Say what to do with a document whose schema_version is not the current one."""
    if isinstance(version, int) and not isinstance(version, bool) and version > SCHEMA_VERSION:
        return (
            f"{path}: schema_version {version} was written by a newer pyflightstream than this "
            f"one, which reads {SCHEMA_VERSION}; upgrade pyflightstream rather than migrate."
        )
    return (
        f"{path}: schema_version {version!r}, and this pyflightstream reads {SCHEMA_VERSION}; "
        "migrate converts the list manifests of the 0.38.0 format only, so it cannot convert "
        "this document. Open it with the release that wrote it, or restore it from its .bak."
    )


def migrate_workspace(root: str | Path, *, apply: bool = False) -> list[dict[str, Any]]:
    """Preview record changes, or back up and replace each changed manifest.

    Parameters
    ----------
    root : str or Path
        Workspace directory containing live run manifests.
    apply : bool, optional
        Write the validated conversion and exact backups. The default only previews.

    Returns
    -------
    list of dict
        Changed files, original and converted byte counts, backups and apply state.

    Raises
    ------
    WorkspaceError
        The workspace, a record or an existing backup prevents migration.

    Notes
    -----
    Archives, products and solver state remain evidence. Every candidate is
    validated before the first backup or replacement. A repeated apply skips
    already migrated files. Migration instructions are in docs/upgrading.md.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise WorkspaceError(f"workspace {root} does not exist")
    candidates = _candidates(root)
    with ExitStack() as locks:
        for path in candidates if apply else []:
            locks.enter_context(
                manifest_lock(
                    path,
                    root=root,
                    timeout_s=MANIFEST_LOCK_TIMEOUT_S,
                    renew_s=MANIFEST_LOCK_RENEW_S,
                    stale_s=MANIFEST_LOCK_STALE_S,
                    poll_s=MANIFEST_LOCK_POLL_S,
                )
            )
        prepared = [_prepare_file(path) for path in candidates]
        changes = [_change_description(item, apply) for item in prepared]
        if apply:
            _write_prepared(prepared)
    return changes


def _candidates(root: Path):
    """Find live root manifests and validate documents already migrated."""
    candidates = []
    for path in sorted(root.glob("*.json")):
        if path.is_symlink():
            raise WorkspaceError(f"migration refuses linked file {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            if path.name == "runs.json":
                raise WorkspaceError(
                    f"{path}: cannot migrate unreadable records: {error}"
                ) from error
            continue
        if isinstance(data, dict) and "schema_version" in data and "runs" in data:
            version = data["schema_version"]
            if version != SCHEMA_VERSION:
                raise WorkspaceError(_other_version_sentence(path, version))
            decode_document(data, source=path)
            continue
        legacy_rows = (
            isinstance(data, list)
            and bool(data)
            and all(
                isinstance(row, dict) and ("run_id" in row or "deleted_sim" in row) for row in data
            )
            and path.name != "additional.json"
        )
        # An empty named manifest is a legacy record the reader refuses too.
        empty_named = data == [] and path.name.startswith("runs")
        if path.name == "runs.json" or legacy_rows or empty_named:
            candidates.append(path)
    return candidates


def _validate_rows(rows: list[dict], path: Path):
    """Translate only the supported legacy keys and validate every record."""
    for row in rows:
        if not isinstance(row, dict):
            raise WorkspaceError(f"{path}: a run row is not an object")
        if "deleted_sim" in row:
            continue
        if row.get("manifest_schema") not in (None, "pyfs-manifest/3"):
            raise WorkspaceError(
                f"{path}: expected the 0.38.0 pyfs-manifest/3 format; "
                "migrate older formats with an older package first"
            )
        for old, new in (("matrix", "matrix_stem"), ("broken_commands", "waived_commands")):
            if old in row:
                if new in row and row[new] != row[old]:
                    raise WorkspaceError(f"{path}: conflicting {old} and {new}; nothing changed")
                row[new] = row.pop(old)
        try:
            RunRecord.model_validate(row)
        except ValidationError as error:
            raise WorkspaceError(f"{path}: invalid run {row.get('run_id')!r}: {error}") from error


def _prepare_file(path: Path):
    """Prepare a validated document and refuse a conflicting backup."""
    before = path.read_bytes()
    rows = json.loads(before)
    if not isinstance(rows, list):
        raise WorkspaceError(
            f"{path}: expected the 0.38.0 record array; use an older package to reach 0.38.0 first"
        )
    _validate_rows(rows, path)
    document = encode_rows(rows)
    decode_document(document, source=path)
    after = (json.dumps(document, indent=2) + "\n").encode("utf-8")
    backup = path.with_suffix(path.suffix + ".bak")
    if backup.is_symlink():
        raise WorkspaceError(f"{backup}: a linked backup is not a copy; remove it before migrating")
    if backup.exists() and backup.read_bytes() != before:
        raise WorkspaceError(
            f"{backup}: a different backup already exists; preserve it before migrating again"
        )
    return path, backup, before, after


def _write_prepared(prepared: list):
    """Secure all original bytes before replacing any live manifest."""
    # All original bytes are secured before any live file changes.
    for _, backup, before, _ in prepared:
        if not backup.exists():
            # Published whole from a sibling, so an interrupted write never leaves a torn .bak
            # that the next migrate would refuse as a different backup.
            partial = backup.with_name(f"{backup.name}.{os.getpid()}.tmp")
            try:
                partial.write_bytes(before)
                partial.replace(backup)
            finally:
                partial.unlink(missing_ok=True)
    for path, _, _, after in prepared:
        temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        try:
            _textio.write_text(temporary, after.decode("utf-8"))
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def _change_description(item: tuple, apply: bool) -> dict[str, Any]:
    """Describe one prepared file in the preview and apply reports."""
    path, backup, before, after = item
    return {
        "file": path.name,
        "before_bytes": len(before),
        "after_bytes": len(after),
        "backup": backup.name,
        "applied": apply,
    }
