"""The record files of a workspace: their kinds, archives, lease and write.

What :func:`~pyflightstream.run.records.restore`,
:func:`~pyflightstream.run.records.mark_failed` and the rebuild share about the
records family: the kinds and where each lives (the workspace root, or
``post/<matrix>/``), the archived copies of each and the order a stamp, its
number and its label give them, the lease a workspace's writers hold around a
manifest (:func:`manifest_lock`), the write through a temporary file, and
:class:`RecordsError`, which every records operation refuses with before it
writes anything.

The public names are re-exported, unchanged, by :mod:`pyflightstream.run.records`,
their path of 0.32.0 (AD-11, since 0.33.0).
"""

from __future__ import annotations

import contextlib
import dataclasses
import datetime as dt
import os
import re
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pyflightstream._errors import PyflightstreamError
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus
from pyflightstream.workspace.naming import (
    ARCHIVE_DIR,
    ARCHIVE_STAMP,
    ARCHIVE_STAMP_PATTERN,
    DEFAULT_MANIFEST,
    free_root_archive,
)

#: The file kinds :func:`~pyflightstream.run.records.restore` brings back from ``archive/``.
RESTORE_KINDS = ("runs", "storage", "products", "plan", "additional")

#: The kinds kept at the workspace root, archived as ``archive/<stem>-<stamp>.json``
#: (``runs.json`` has always been archived there as ``archive/runs-<stamp>.json``).
_ROOT_KINDS = {
    "runs": DEFAULT_MANIFEST,
    "storage": "storage_management.json",
    "additional": "additional.json",
}

#: The kinds kept per matrix under ``post/<matrix>/``, archived beside the
#: products as ``post/<matrix>/archive/<stamp>/<name>``.
_MATRIX_KINDS = {"products": "products.json", "plan": "plan.json"}

#: The pattern of an archive stamp, from its one home beside the spelling
#: (``workspace.naming``, since 0.33.0, AD-10).
_STAMP = ARCHIVE_STAMP_PATTERN


class RecordsError(PyflightstreamError, ValueError):
    """A restore or a rebuild refused, before anything was written.

    ValueError because what is refused is the request as given: a kind, a
    stamp, a manifest name, a combination of options, or a workspace state the
    request cannot be carried out in exactly.
    """


# ---------------------------------------------------------------------------
# restore
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class _Archived:
    """One archived copy: where it is, its stamp, and the key it sorts by."""

    path: Path
    stamp: str
    label: str

    @property
    def key(self) -> tuple[str, int, str]:
        # ``.2`` numbers a second copy within one stamp; a label may follow the
        # number (``.2-before-doctor``) or stand alone (``-before-doctor``, or
        # any suffix of a post archive folder), and then it counts as the first.
        number = re.match(r"\.(\d+)", self.label)
        index = int(number.group(1)) if number else 1
        return (self.stamp, index, self.label)


def _root_archives(base: Path, name: str) -> list[_Archived]:
    stem = Path(name).stem
    pattern = re.compile(rf"^{re.escape(stem)}-({_STAMP})((?:\.\d+)?(?:-[A-Za-z0-9_-]+)?)\.json$")
    folder = base / ARCHIVE_DIR
    found = []
    for path in sorted(folder.iterdir()) if folder.is_dir() else []:
        match = pattern.match(path.name)
        if match and path.is_file():
            found.append(_Archived(path, match.group(1), match.group(2)))
    return found


def _matrix_archives(base: Path, stem: str, name: str) -> list[_Archived]:
    pattern = re.compile(rf"^({_STAMP})(.*)$")
    folder = base / "post" / stem / ARCHIVE_DIR
    found = []
    for stamped in sorted(folder.iterdir()) if folder.is_dir() else []:
        match = pattern.match(stamped.name)
        if match and (stamped / name).is_file():
            found.append(_Archived(stamped / name, match.group(1), match.group(2)))
    return found


def _relative(base: Path, path: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return str(path)


def _now_stamp() -> str:
    return dt.datetime.now().strftime(ARCHIVE_STAMP)


def _replace_bytes(target: Path, payload: bytes) -> None:
    """Write ``payload`` to ``target`` through a temporary file of this process."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    temporary.write_bytes(payload)
    temporary.replace(target)


def _leases(base: Path, target: Path) -> contextlib.ExitStack:
    """Hold the leases a restore of ``target`` writes under, and return them.

    Always the lease on ``runs.json``: the run, the collect and the sync hold
    it while they write in the workspace, the sync for the whole of its copy,
    so a restore neither interleaves with a sync nor starts while one writes
    (RST-6). For a root record with a lease of its own (the storage record,
    the additional-post record) that lease too, the one its writer holds.
    """
    stack = contextlib.ExitStack()
    try:
        stack.enter_context(manifest_lock(base))
        if target.parent == base and target.name in _ROOT_KINDS.values():
            if target.name != DEFAULT_MANIFEST:
                stack.enter_context(manifest_lock(base, target))
    except BaseException:
        stack.close()
        raise
    return stack


def manifest_lock(root: str | Path, manifest: str | Path | None = None) -> Any:
    """Hold the lease a workspace's writers hold around a manifest.

    The public face of the workspace's lease (``runs.json.lock``, or
    ``additional.json.lock`` for the additional-post record), so a caller
    outside the run layer rewrites a manifest under the same rule as the
    run, the collect and the forced re-run do.

    Parameters
    ----------
    root : str or Path
        The workspace root.
    manifest : str or Path, optional
        The manifest the lease guards; ``runs.json`` when None.

    Returns
    -------
    context manager
        Entered, it holds the lease; left, it releases it.
    """
    from pyflightstream.workspace import CampaignWorkspace

    workspace = CampaignWorkspace(Path(root))
    return workspace._manifest_lock(None if manifest is None else Path(manifest))


def mark_runs_failed(
    workspace: CampaignWorkspace,
    run_ids: Sequence[str],
    *,
    reason: str | None = None,
    discarded_by: str | None = None,
) -> list[RunRecord]:
    """Mark selected runs failed, preserving the previous manifest and all outputs.

    Parameters
    ----------
    workspace : CampaignWorkspace
        Workspace whose current manifest is updated under its own lease.
    run_ids : sequence of str
        Run identities to mark; absent and already marked runs are left alone.
    reason : str, optional
        Explanation recorded with the previous status and timestamp.
    discarded_by : str, optional
        Command that requested the discard, when applicable.

    Returns
    -------
    list of RunRecord
        The updated records. Each identity keeps one current manifest row,
        as with ``mark_failed``; its previous row remains in the archive.
    """
    chosen = set(run_ids)
    with manifest_lock(workspace.root, workspace.manifest_path):
        rows = workspace.read_raw_manifest()
        todo = [
            row
            for row in rows
            if row.get("run_id") in chosen
            and row.get("deleted_sim") is None
            and row.get("status") != RunStatus.FAILED_MARKED
        ]
        if not todo:
            return []
        archived = free_root_archive(workspace.root, workspace.manifest_path.name, _now_stamp())
        archived.parent.mkdir(exist_ok=True)
        shutil.copy2(workspace.manifest_path, archived)
        at = dt.datetime.now(dt.UTC).isoformat()
        for row in todo:
            row["marked"] = {"from": row.get("status"), "at": at, "reason": reason}
            row["status"] = str(RunStatus.FAILED_MARKED)
            if discarded_by is not None:
                row["discarded_by"] = discarded_by
        workspace._replace_manifest(rows)
    return [RunRecord.model_validate(row) for row in todo]
