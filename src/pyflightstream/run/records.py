"""The run records of a workspace: which manifest, its restore and its rebuild.

Pipeline role: the run row, beside the manifest the run stage writes. It is
the 0.32.0 home of three operations on the records of a campaign workspace
(work package B1; the packages that call it, B2 with the sync and B3 with the
post and collect reading ``--runs``, code against the same signatures):

* :func:`resolve_manifest` names the manifest file a command reads: the
  default ``runs.json``, or another file directly in the workspace root
  (``pyfs-matrix post --runs NAME`` and its siblings). Since 0.33.0 it is
  defined in :mod:`pyflightstream.workspace.naming` and re-exported here
  (AD-09), so the storage layer below this one reads it without reaching up.
* :func:`restore` brings a file of the records family back from the
  workspace's archive, EXACTLY: the manifest, the storage record, a matrix's
  products record, the plan receipt or the additional-post record (the kinds
  of :data:`RESTORE_KINDS`). It previews unless asked to apply, and archives
  the current file before it replaces it, so a restore can itself be undone.
* :func:`rebuild` makes run records AGAIN from the simulation folders under
  ``sims/`` when no archive holds them. It is not a restore and every record
  it makes says so in its ``warnings``.

The two operations carry two names on purpose (GEO-066, R2): a reader must
never trust a rebuilt record as the one written when the point ran.

**How a record is rebuilt, and what proves it.** The matrix row is run again
through this package's own campaign loop in a throwaway SHADOW workspace (a
copy of ``inputs/`` and of the matrix in a temporary folder), with a
submitting executor that submits nothing, which mints the SUBMITTED record
the cluster path writes. The proof of identity is the executed script: the
script on disk under ``sims/sim_<id>/scripts/`` must be the script THIS
package version renders for that row, once the workspace root and the
interpreter path are set aside on both sides; otherwise the simulation is
refused, naming the version and, line by line, which input the difference
comes from. The record is then completed by the package's own collect stage
run READ-ONLY over the files already on disk (:func:`collect_without_writing`):
a collection that would move, copy, translate or expand a file is not done,
and the record stays SUBMITTED for ``pyfs-matrix collect``. The whole
workspace tree is compared before and after, and nothing is written when it
changed.

Deliberately NOT rebuilt: a simulation stored compressed, one whose record a
known run of another package version wrote, one whose row no matrix holds (it
waits for the revision that ran, ``matrix``), one whose executed script
differs, and one with no declared output. A SUBMITTED record is pointed to
``pyfs-matrix collect`` unless every simulation is rebuilt (``all_sims``),
which judges each from its outputs instead.

The post and the collect of other records (work package B3):
:func:`manifest_workspace` is the workspace ``post --runs NAME``
and ``collect --runs NAME`` read, :func:`assemble_records` assembles the
records of ``post --from-sims`` in memory from the simulation folders, and
:func:`from_sims_workspace` is the workspace that post reads. Both kinds are
a :class:`ManifestWorkspace`, whose products go to ``post/<matrix>@<label>/``
beside the default ones and never over them.

FIVE MODULES SINCE 0.33.0 (AD-11). This one holds :func:`restore` and
:func:`mark_failed` and keeps every public name of the records family at its
0.32.0 path. The record files, their archives, the lease and
:class:`RecordsError` are :mod:`pyflightstream.run._record_files`; what a
rebuild reads and compares is :mod:`pyflightstream.run._rebuild_evidence`;
the rebuild itself is :mod:`pyflightstream.run._rebuild`; the assembly of
other records for the post is :mod:`pyflightstream.run._assemble`. Each
imports only ones before it and none imports this module, so there is no
import cycle among them. The machinery the rebuild drives and the collect's
assessor are imported inside the functions that call them. The collect stage
is made read-only by replacing its three writes with refusals for the length
of one call, under a lock (:func:`collect_without_writing`); nothing else of
the stage is changed.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

# The names below are imported only because 0.32.0 offered them from this
# module, which had no __all__; each keeps importing from here (a release
# does everything the previous one did, as scripts/check_parity.py checks).
from pyflightstream._digest import file_sha256 as file_sha256
from pyflightstream._errors import PyflightstreamError
from pyflightstream._errors import PyflightstreamWarning as PyflightstreamWarning
from pyflightstream._errors import warn as warn
from pyflightstream.cases import EXPORT_KINDS as EXPORT_KINDS
from pyflightstream.cases import POINT_AXIS_KEYS as POINT_AXIS_KEYS
from pyflightstream.cases import POINT_NAME_FIELDS as POINT_NAME_FIELDS
from pyflightstream.cases import SWEEP_NAME_VALUE as SWEEP_NAME_VALUE
from pyflightstream.cases import classify_outputs as classify_outputs
from pyflightstream.cases.matrix import ATTITUDE_KEYS as ATTITUDE_KEYS
from pyflightstream.cases.matrix import UNSTATED_CELLS as UNSTATED_CELLS
from pyflightstream.cases.matrix import MatrixRow as MatrixRow
from pyflightstream.cases.matrix import read_matrix as read_matrix
from pyflightstream.cases.windows import LAST_REVS_AVG as LAST_REVS_AVG
from pyflightstream.cases.windows import replan as replan
from pyflightstream.cases.windows import stated_key as stated_key
from pyflightstream.results import parse_loads as parse_loads
from pyflightstream.results import parse_unsteady_plots as parse_unsteady_plots

# Since 0.33.0 (AD-11) the rebuild, what it reads, the assembly and the record
# files are private modules of this package; every public name of them keeps
# its 0.32.0 path here.
from pyflightstream.run._alias import row_selected
from pyflightstream.run._assemble import APART_MARK as APART_MARK
from pyflightstream.run._assemble import ASSEMBLED_NOTE as ASSEMBLED_NOTE
from pyflightstream.run._assemble import FROM_SIMS_LABEL as FROM_SIMS_LABEL
from pyflightstream.run._assemble import ManifestWorkspace as ManifestWorkspace
from pyflightstream.run._assemble import assemble_records as assemble_records
from pyflightstream.run._assemble import from_sims_workspace as from_sims_workspace
from pyflightstream.run._assemble import manifest_workspace as manifest_workspace
from pyflightstream.run._mark_converged import mark_converged as mark_converged
from pyflightstream.run._rebuild import QUIET_WINDOW_S as QUIET_WINDOW_S
from pyflightstream.run._rebuild import REBUILT as REBUILT
from pyflightstream.run._rebuild import bind_row_builds as bind_row_builds
from pyflightstream.run._rebuild import campaign_executor as campaign_executor
from pyflightstream.run._rebuild import rebuild
from pyflightstream.run._rebuild import row_versions as row_versions
from pyflightstream.run._rebuild import summary_lines as summary_lines
from pyflightstream.run._rebuild_evidence import (
    collect_without_writing as collect_without_writing,
)
from pyflightstream.run._record_files import (
    _MATRIX_KINDS,
    _ROOT_KINDS,
    RESTORE_KINDS,
    RecordsError,
    _leases,
    _matrix_archives,
    _now_stamp,
    _relative,
    _replace_bytes,
    _root_archives,
    manifest_lock,
)
from pyflightstream.run._record_files import (
    mark_runs_failed as mark_runs_failed,
)

# More of the names 0.32.0 offered from this module, kept for the same reason.
from pyflightstream.workspace import AdditionalRecord as AdditionalRecord
from pyflightstream.workspace import CampaignWorkspace as CampaignWorkspace
from pyflightstream.workspace import RunRecord as RunRecord
from pyflightstream.workspace import RunStatus as RunStatus
from pyflightstream.workspace import WorkspaceError as WorkspaceError
from pyflightstream.workspace import find_matrix as find_matrix
from pyflightstream.workspace.flight_condition import (
    canonical_condition_defaults as canonical_condition_defaults,
)
from pyflightstream.workspace.flight_condition import (
    resolve_flight_condition as resolve_flight_condition,
)
from pyflightstream.workspace.inputs import ReferenceArtifact as ReferenceArtifact
from pyflightstream.workspace.matrix import condition_defaults_origin as condition_defaults_origin
from pyflightstream.workspace.naming import (
    ARCHIVE_DIR,
    free_matrix_archive,
    free_root_archive,
)

# Since 0.33.0 (AD-09) the manifest-name rule lives in the workspace layer,
# which names the files of a workspace root; its 0.32.0 path is kept here,
# as is the archive stamp's, which run._record_files writes (AD-11).
from pyflightstream.workspace.naming import ARCHIVE_STAMP as ARCHIVE_STAMP
from pyflightstream.workspace.naming import DEFAULT_MANIFEST as DEFAULT_MANIFEST
from pyflightstream.workspace.naming import PointName as PointName
from pyflightstream.workspace.naming import RunsManifestError as RunsManifestError
from pyflightstream.workspace.naming import datapoint_name_of as datapoint_name_of
from pyflightstream.workspace.naming import resolve_manifest as resolve_manifest
from pyflightstream.workspace.storage import register_records_rebuild

# ---------------------------------------------------------------------------
# mark-failed
# ---------------------------------------------------------------------------


def mark_failed(
    root: str | Path,
    sims: Sequence[str],
    *,
    reason: str | None = None,
    apply: bool = False,
    points: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, Any]:
    """Mark every record of the named simulations FAILED_MARKED (FR-309).

    A run can end CONVERGED and still be wrong, which the person finds
    only later, reading its products. The record is not deleted: its
    status becomes ``FAILED_MARKED``, and ``marked`` keeps the status it
    had, when it was marked and the reason given, so the post, the cost
    estimate and delete-sims treat it as any failure and the history stays.

    Parameters
    ----------
    root : str or Path
        The workspace root.
    sims : sequence of str
        Simulation ids. An id with no record in ``runs.json`` is refused by
        name before anything is written.
    reason : str, optional
        Why the runs are marked, recorded as it is given.
    apply : bool
        Write. Without it nothing changes and the result says what would.
    points : mapping of str to sequence of str, optional
        Per simulation, the point names whose records alone are marked (a run id
        alias, FR-395); a simulation also in ``sims`` is marked whole.

    Returns
    -------
    dict
        ``applied``, ``marked`` (per record: ``sim_id``, ``run_id``,
        ``from``), ``already`` (the run ids already FAILED_MARKED, left as
        they are) and, when applied, ``runs_archived_as``.

    Raises
    ------
    RunsManifestError
        No ``runs.json``, no simulation named, or an id with no record.
    """
    from pyflightstream.workspace import CampaignWorkspace, RunStatus

    base = Path(root)
    manifest = base / DEFAULT_MANIFEST
    ids = list(dict.fromkeys(str(sim).strip() for sim in sims if str(sim).strip()))
    only = {sim: tags for sim, tags in (points or {}).items() if sim not in ids}
    if not ids and not only:
        raise RunsManifestError("name the simulations to mark, comma separated: 2006,2007")
    if not manifest.is_file():
        raise RunsManifestError(f"{manifest} does not exist, so no run can be marked")

    def plan(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
        known = {str(row.get("sim_id")) for row in rows if row.get("deleted_sim") is None}
        unknown = [sim for sim in [*ids, *only] if sim not in known]
        if unknown:
            raise RunsManifestError(
                f"no record in {manifest.name} for simulation(s) {', '.join(unknown)}; "
                "nothing was marked"
            )
        chosen = [
            row
            for row in rows
            if row.get("deleted_sim") is None
            and (
                str(row.get("sim_id")) in ids
                or row_selected(row, only.get(str(row.get("sim_id")), ()))
            )
        ]
        already = [
            str(row["run_id"]) for row in chosen if row.get("status") == RunStatus.FAILED_MARKED
        ]
        todo = [row for row in chosen if row.get("status") != RunStatus.FAILED_MARKED]
        return todo, already

    def read() -> list[dict[str, Any]]:
        rows = json.loads(manifest.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise RunsManifestError(f"{manifest} is not a list of run records")
        return rows

    todo, already = plan(read())
    result: dict[str, Any] = {
        "applied": False,
        "marked": [
            {
                "sim_id": str(row.get("sim_id")),
                "run_id": str(row["run_id"]),
                "from": row.get("status"),
            }
            for row in todo
        ],
        "already": already,
        "reason": reason,
    }
    if not apply or not todo:
        return result
    workspace = CampaignWorkspace(base)
    stamp = _now_stamp()
    at = dt.datetime.now(dt.UTC).isoformat()
    with manifest_lock(base):
        rows = read()
        todo, already = plan(rows)
        (base / ARCHIVE_DIR).mkdir(exist_ok=True)
        archived = base / ARCHIVE_DIR / f"{manifest.stem}-{stamp}.json"
        shutil.copy2(manifest, archived)
        for row in todo:
            row["marked"] = {"from": row.get("status"), "at": at, "reason": reason}
            row["status"] = str(RunStatus.FAILED_MARKED)
        workspace._replace_manifest(rows)
    result.update(
        applied=True,
        runs_archived_as=_relative(base, archived),
        marked=[
            {
                "sim_id": str(row.get("sim_id")),
                "run_id": str(row["run_id"]),
                "from": row["marked"]["from"],
            }
            for row in todo
        ],
        already=already,
    )
    return result


def restore(
    root: str | Path,
    kind: str,
    *,
    stamp: str | None = None,
    apply: bool = False,
    matrix: str | None = None,
) -> dict[str, Any]:
    """Restore one file of the records family from the workspace's archive.

    Exact and cheap: the archived bytes become the file again, unchanged. The
    archive forms read are ``archive/runs-<stamp>.json``, where ``sync``,
    ``--force-rerun``, ``delete-sims`` and ``rename`` copy the manifest before
    rewriting it; in the same form ``archive/storage_management-<stamp>.json``
    and ``archive/additional-<stamp>.json``; and, beside a matrix's products,
    ``post/<matrix>/archive/<stamp>/products.json`` and ``.../plan.json``.
    Every restore that applies archives the file it replaces in these forms.
    The writers of the storage record, the products record, the plan receipt
    and the additional-post record archive their file before rewriting it (0.32.0,
    ``workspace.naming.archive_previous``, the one home of these names), so every
    kind has copies to bring back; ``products.json`` is archived rather than
    removed when a post rebuilds. A copy numbered within one stamp
    (``runs-<stamp>.2.json``) or labelled after it
    (``runs-<stamp>-before-doctor.json``) is found too.

    Parameters
    ----------
    root : str or Path
        The workspace root.
    kind : str
        One of :data:`RESTORE_KINDS`: ``runs`` (``runs.json``), ``storage``
        (``storage_management.json``), ``additional`` (``additional.json``),
        ``products`` (``post/<matrix>/products.json``) or ``plan``
        (``post/<matrix>/plan.json``).
    stamp : str, optional
        The archive stamp to restore from, ``YYYYMMDD-HHMMSS`` as the archive
        spells it, or the whole numbered or labelled stamp. The copy of
        exactly that name is taken; a bare stamp that no plain copy carries
        takes the newest numbered or labelled copy of it. None takes the
        newest copy.
    apply : bool, default False
        Change files; without it the call previews and changes nothing. With
        it the current file, when there is one, is archived first under the
        same form, so the restore can be undone by restoring that copy.
    matrix : str, optional
        For ``products`` and ``plan``, the matrix stem whose file to restore;
        needed only when archives exist for several matrices.

    Returns
    -------
    dict
        ``kind``, ``target`` and ``source`` (paths relative to the root),
        ``stamp``, ``stamps_available``, ``same`` (the current file already
        holds the archived bytes), ``applied``, ``archived_as`` (where the
        current file went, or None) and, for ``runs``, ``records`` (the rows
        the archived manifest holds).

    Raises
    ------
    RecordsError
        An unknown kind; no archived copy (naming where it was looked for); a
        stamp no copy carries (naming the stamps that exist); archives for
        several matrices and none named; a ``matrix`` that is not a bare
        folder name under ``post/``; an archived copy that is not
        readable JSON, or a manifest copy that is not a list of records; an
        applying restore of any kind while ``runs.json.lock`` is held (a run,
        a collect or a sync writing in the workspace), or while the restored
        file's own lease is held (``storage_management.json.lock``,
        ``additional.json.lock``). The write itself holds those leases (RST-6).
    """
    base = Path(root)
    if kind not in RESTORE_KINDS:
        raise RecordsError(
            f"restore: the kind {kind!r} is not one this package archives; name one of "
            f"{', '.join(RESTORE_KINDS)}"
        )
    if kind in _ROOT_KINDS:
        name = _ROOT_KINDS[kind]
        target = base / name
        found = _root_archives(base, name)
        where = f"{ARCHIVE_DIR}/{Path(name).stem}-<stamp>.json"
        stem = None
    else:
        name = _MATRIX_KINDS[kind]
        if matrix is not None and (
            not matrix or matrix in (".", "..") or Path(matrix).name != matrix
        ):
            raise RecordsError(
                f"restore {kind}: {matrix!r} is not a matrix stem: name the folder under "
                f"{base / 'post'} as matrix (CLI: --matrix), with no path in it; nothing was "
                "changed"
            )
        stems = (
            [matrix]
            if matrix is not None
            else sorted(
                folder.name
                for folder in (base / "post").iterdir()
                if folder.is_dir() and _matrix_archives(base, folder.name, name)
            )
            if (base / "post").is_dir()
            else []
        )
        if len(stems) > 1:
            raise RecordsError(
                f"restore {kind}: archives of {name} exist for several matrices "
                f"({', '.join(stems)}); name the one to restore as matrix (CLI: --matrix)"
            )
        stem = stems[0] if stems else (matrix or "<matrix>")
        target = base / "post" / stem / name
        found = _matrix_archives(base, stem, name) if stems else []
        where = f"post/{stem}/{ARCHIVE_DIR}/<stamp>/{name}"
    if not found:
        raise RecordsError(
            f"restore {kind}: no archived copy of {name} under {base} (looked for {where}); "
            "nothing was changed"
        )
    available = sorted(found, key=lambda item: item.key)
    if stamp is not None:
        # The copy of exactly that name first; a bare stamp with no plain copy
        # then takes the newest numbered or labelled copy of it.
        chosen = [item for item in available if stamp == item.stamp + item.label] or [
            item for item in available if stamp == item.stamp
        ]
        if not chosen:
            raise RecordsError(
                f"restore {kind}: no archived copy of {name} carries the stamp {stamp!r}; the "
                f"stamps there are {', '.join(item.stamp + item.label for item in available)}"
            )
        source = chosen[-1]
    else:
        source = available[-1]
    payload = source.path.read_bytes()
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise RecordsError(
            f"restore {kind}: the archived copy {_relative(base, source.path)} is not readable "
            f"JSON ({error}); choose another stamp, nothing was changed"
        ) from error
    if kind == "runs" and not (
        isinstance(document, list) and all(isinstance(row, dict) for row in document)
    ):
        raise RecordsError(
            f"restore runs: the archived copy {_relative(base, source.path)} is not a list of "
            "run records; choose another stamp, nothing was changed"
        )
    same = target.is_file() and target.read_bytes() == payload
    entry: dict[str, Any] = {
        "kind": kind,
        "target": _relative(base, target),
        "source": _relative(base, source.path),
        "stamp": source.stamp + source.label,
        "stamps_available": [item.stamp + item.label for item in available],
        "same": same,
        "applied": False,
        "archived_as": None,
    }
    if kind == "runs":
        entry["records"] = len(document)
    if not apply or same:
        return entry
    for lock in dict.fromkeys(
        (base / f"{DEFAULT_MANIFEST}.lock", target.with_name(target.name + ".lock"))
    ):
        if lock.exists():
            raise RecordsError(
                f"restore {kind}: {lock.name} is present, so a run, a collect or a sync is "
                "writing in the workspace; try again when it ends. Nothing was changed."
            )
    with _leases(base, target):
        if target.is_file():
            if stem is None:
                kept = free_root_archive(base, name, _now_stamp())
            else:
                kept = free_matrix_archive(base, stem, name, _now_stamp())
            kept.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, kept)
            entry["archived_as"] = _relative(base, kept)
        _replace_bytes(target, payload)
    entry["applied"] = True
    return entry


def _rebuild_for_sync(root: Path, sims: list[str]) -> dict[str, Any]:
    """Rebuild the records of ``sims`` as an applying ``sync --restore`` asks.

    P0320-SYNC-RESTORE-OPTIN and AD-09. The storage layer, below this one,
    calls it through the registry it owns
    (:func:`pyflightstream.workspace.storage.register_records_rebuild`), after
    the sync released the ``runs.json`` lease, which the rebuild takes itself.
    It returns the entry's ``restore`` block: a refusal is its ``error``, not
    the sync's, and the rebuilt records, which are in ``runs.json``, are left
    out of ``result``. :func:`rebuild` is looked up when called.
    """
    outcome: dict[str, Any] = {"asked": True, "sims": sims, "result": None, "error": None}
    try:
        result = rebuild(root, sims=sims, apply=True)
    except (PyflightstreamError, OSError) as error:
        outcome["error"] = str(error)
        return outcome
    kept = {key: value for key, value in result.items() if key != "records"}
    outcome["result"] = json.loads(json.dumps(kept, default=str))
    return outcome


register_records_rebuild(_rebuild_for_sync)
