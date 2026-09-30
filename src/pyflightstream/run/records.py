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

The post and the collect of other records (work package B3), at the end of
the module: :func:`manifest_workspace` is the workspace ``post --runs NAME``
and ``collect --runs NAME`` read, :func:`assemble_records` assembles the
records of ``post --from-sims`` in memory from the simulation folders, and
:func:`from_sims_workspace` is the workspace that post reads. Both kinds are
a :class:`ManifestWorkspace`, whose products go to ``post/<matrix>@<label>/``
beside the default ones and never over them.

At module level the module imports the floor, ``_digest``, ``cases``,
``results`` and the workspace row; the workspace row reaches this module
only inside the functions that use it, so there is no import cycle. The
machinery the rebuild drives and the collect's assessor are imported inside
the functions that call them. The collect stage is made read-only by
replacing its three writes with refusals for the length of one call, under a
lock (:func:`collect_without_writing`); nothing else of the stage is changed.
"""

from __future__ import annotations

import contextlib
import csv
import dataclasses
import datetime as dt
import difflib
import json
import os
import re
import shutil
import tempfile
import threading
import time
import warnings
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from pyflightstream._digest import file_sha256
from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning, warn
from pyflightstream.cases import (
    EXPORT_KINDS,
    POINT_AXIS_KEYS,
    POINT_NAME_FIELDS,
    SWEEP_NAME_VALUE,
    classify_outputs,
)
from pyflightstream.cases.matrix import ATTITUDE_KEYS, UNSTATED_CELLS, MatrixRow, read_matrix
from pyflightstream.cases.windows import LAST_REVS_AVG, replan, stated_key
from pyflightstream.results import parse_loads, parse_unsteady_plots
from pyflightstream.workspace import (
    AdditionalRecord,
    CampaignWorkspace,
    RunRecord,
    RunStatus,
    WorkspaceError,
    find_matrix,
)
from pyflightstream.workspace.flight_condition import (
    canonical_condition_defaults,
    resolve_flight_condition,
)
from pyflightstream.workspace.inputs import ReferenceArtifact
from pyflightstream.workspace.matrix import condition_defaults_origin
from pyflightstream.workspace.naming import (
    ARCHIVE_DIR,
    ARCHIVE_STAMP,
    ARCHIVE_STAMP_PATTERN,
    PointName,
    datapoint_name_of,
    free_matrix_archive,
    free_root_archive,
)

# Since 0.33.0 (AD-09) the manifest-name rule lives in the workspace layer,
# which names the files of a workspace root; its 0.32.0 path is kept here.
from pyflightstream.workspace.naming import DEFAULT_MANIFEST as DEFAULT_MANIFEST
from pyflightstream.workspace.naming import RunsManifestError as RunsManifestError
from pyflightstream.workspace.naming import resolve_manifest as resolve_manifest
from pyflightstream.workspace.storage import register_records_rebuild

#: The file kinds :func:`restore` brings back from ``archive/``.
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

#: Seconds a simulation folder must have been quiet before its job is taken as
#: over. A folder written more recently stays SUBMITTED, since its job may
#: still be writing (RST-7); 30 minutes is the window the prototype measured.
QUIET_WINDOW_S = 1800.0

#: The word every rebuilt record's warning starts with.
REBUILT = "REBUILT"

#: A quoted interpreter path in a rendered script, which names the Python that wrote it.
_INTERPRETER = re.compile(r'"[^"\n]*[\\/]python[w]?[0-9.]*(?:\.exe)?"', re.IGNORECASE)

#: The drift classes a difference between the executed and the rendered script
#: is named by, keyed by the verb that opens the line. A line of no listed verb
#: whose token is a group of the row's pproc is a renamed group.
_DRIFT_VERBS = {
    "EXPORT_SOLVER_ANALYSIS_VTK": "VTK export line",
    "SET_SOLVER_ANALYSIS_LOADS_FRAME": "loads frame line",
    "SET_PLOT_TYPE": "plot type line",
}

_NOT_RECOVERABLE_NOTE = (
    "do not run `pyfs-matrix run --resume` on a refused simulation: with no record, the "
    "resume takes it as never run and runs it again"
)


class RecordsError(PyflightstreamError, ValueError):
    """A restore or a rebuild refused, before anything was written.

    ValueError because what is refused is the request as given: a kind, a
    stamp, a manifest name, a combination of options, or a workspace state the
    request cannot be carried out in exactly.
    """


# ---------------------------------------------------------------------------
# mark-failed
# ---------------------------------------------------------------------------


def mark_failed(
    root: str | Path,
    sims: Sequence[str],
    *,
    reason: str | None = None,
    apply: bool = False,
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
    if not ids:
        raise RunsManifestError("name the simulations to mark, comma separated: 2006,2007")
    if not manifest.is_file():
        raise RunsManifestError(f"{manifest} does not exist, so no run can be marked")

    def plan(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
        known = {str(row.get("sim_id")) for row in rows if row.get("deleted_sim") is None}
        unknown = [sim for sim in ids if sim not in known]
        if unknown:
            raise RunsManifestError(
                f"no record in {manifest.name} for simulation(s) {', '.join(unknown)}; "
                "nothing was marked"
            )
        chosen = [
            row for row in rows if row.get("deleted_sim") is None and str(row.get("sim_id")) in ids
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


# ---------------------------------------------------------------------------
# the run layer's own machinery, public
# ---------------------------------------------------------------------------


def row_versions(resolved: Any) -> dict[str, str]:
    """Return the per-simulation solver version of a bound matrix, keyed by sim id.

    The version each row's build declares in the build registry; a row on a
    build declaring none is absent and runs under the campaign default. The
    same answer ``pyfs-matrix plan`` and ``run`` use.

    Parameters
    ----------
    resolved : pyflightstream.workspace.matrix.ResolvedMatrix
        The bound matrix.
    """
    from pyflightstream.run import matrix as run_matrix

    return run_matrix._row_versions(resolved)


def campaign_executor(
    workspace: Any, resolved: Any, path: str | Path, *, executor: Any = None
) -> tuple[Any, Callable[[Path], Any]]:
    """Return the executor a bound matrix runs on, and the one for each other build.

    The one choice ``pyfs-matrix run`` makes: a caller's ``executor`` answers
    for every build; left out, the cluster rule and the matrix's HIDDEN column
    decide. A build the submission profile cannot name is refused here.

    Parameters
    ----------
    workspace : pyflightstream.workspace.CampaignWorkspace
    resolved : pyflightstream.workspace.matrix.ResolvedMatrix
    path : str or Path
        The matrix file.
    executor : pyflightstream.run.Executor, optional
    """
    from pyflightstream.run import matrix as run_matrix

    return run_matrix._campaign_executor(workspace, resolved, path, executor=executor)


def bind_row_builds(
    resolved: Any, default: str | None, executor: Any, executor_for: Callable[[Path], Any]
) -> tuple[Any, Any]:
    """Carry each row's build onto the campaign that runs, as ``pyfs-matrix run`` does.

    Returns the campaign and the ``builds`` mapping the campaign loop takes.
    """
    from pyflightstream.run import matrix as run_matrix

    return run_matrix._bind_row_builds(resolved, default, executor, executor_for)


class _WouldWriteError(RuntimeError):
    """A collection that would write in the workspace, left to ``pyfs-matrix collect``."""


_READ_ONLY = threading.Lock()


@contextlib.contextmanager
def _collect_read_only() -> Iterator[None]:
    """Make the collect stage's three writes into refusals, for this block only.

    The stage copies a scheduler's log to its declared name, writes a surface
    export translated from the VTK, and expands a compressed simulation. Each
    is replaced by a check that raises :class:`_WouldWriteError` where the write
    would happen, and restored when the block ends, under a lock so two
    rebuilds in one process do not interleave.
    """
    from pyflightstream.run import collect as collect_module

    original_translate = collect_module.translate_surface_exports

    def refuse_copy(native: Any) -> None:
        if native.source is not None and native.target is not None:
            if not Path(native.target).is_file():
                raise _WouldWriteError(
                    f"collection would copy the scheduler log {native.source} to {native.target}"
                )

    def refuse_translation(folder: Any, translations: Any, **keywords: Any) -> Any:
        for entry in translations or []:
            dat = entry.get("dat") if isinstance(entry, Mapping) else None
            if dat and not (Path(folder) / str(dat)).is_file():
                raise _WouldWriteError(
                    f"collection would write the surface export {dat} in {folder}"
                )
        return original_translate(folder, translations, **keywords)

    def refuse_expand(workspace: Any, sim_id: str, *, reason: str) -> bool:
        if not workspace.sim_dir(sim_id).is_dir():
            raise _WouldWriteError(f"collection would expand sims/sim_{sim_id}.zip")
        return False

    patches = {
        "_copy_native_log": refuse_copy,
        "translate_surface_exports": refuse_translation,
        "ensure_sim_expanded": refuse_expand,
    }
    with _READ_ONLY:
        saved = {name: getattr(collect_module, name) for name in patches}
        try:
            for name, value in patches.items():
                setattr(collect_module, name, value)
            yield
        finally:
            for name, value in saved.items():
                setattr(collect_module, name, value)


def collect_without_writing(
    root: str | Path, record: Mapping[str, Any], *, staging: str | Path
) -> tuple[dict[str, Any], str | None]:
    """Complete one SUBMITTED record from the files on disk, writing nothing there.

    The package's own collect stage (:func:`pyflightstream.run.collect.collect_once`,
    the judgement ``pyfs-matrix collect`` makes) over the workspace ``root``,
    with its manifest in ``staging`` instead of ``runs.json``. A collection that
    would move an output into its datapoint folder, copy the scheduler's log,
    write a translated surface export or expand a compressed simulation is not
    made: the record comes back SUBMITTED with the reason. A missing output is
    judged missing (the job is taken as over), so it is never CONVERGED.

    Parameters
    ----------
    root : str or Path
        The workspace root holding ``sims/``.
    record : mapping
        The SUBMITTED record, as written to a manifest.
    staging : str or Path
        A folder outside the workspace for the manifest the stage rewrites.

    Returns
    -------
    tuple of dict and str or None
        The record the stage completed (or the one given, still SUBMITTED),
        and why it was left SUBMITTED, or None.
    """
    from pyflightstream._progress import workspace_activity
    from pyflightstream.run import collect as collect_module
    from pyflightstream.workspace import CampaignWorkspace
    from pyflightstream.workspace.naming import datapoint_dir_name

    folder = Path(staging)
    folder.mkdir(parents=True, exist_ok=True)

    class _Staged(CampaignWorkspace):
        """The real workspace, with its two manifests in the staging folder."""

        @property
        def manifest_path(self) -> Path:
            return folder / DEFAULT_MANIFEST

        @property
        def additional_path(self) -> Path:
            return folder / _ROOT_KINDS["additional"]

        def collect_outputs(
            self,
            sim_id: str,
            produced: Sequence[str | Path],
            *,
            datapoint: Any,
            ran_in_datapoint: bool = False,
        ) -> list[str]:
            own = self.sim_dir(sim_id) / "datapoints" / datapoint_dir_name(datapoint)
            placed: list[str | Path] = []
            for item in produced:
                path = Path(item)
                if not path.is_file() and (own / path.name).is_file():
                    path = own / path.name
                if path.is_file() and path.resolve().parent != own.resolve():
                    raise _WouldWriteError(f"collection would move {path} into {own}")
                placed.append(path)
            return super().collect_outputs(
                sim_id, placed, datapoint=datapoint, ran_in_datapoint=True
            )

    def settled_observer(paths: Any) -> Any:
        seen = collect_module.observe(paths)
        for key, stamp in list(seen.items()):
            if stamp is None:
                seen[key] = collect_module.Stamp(size=-1, mtime_ns=-1)
        return seen

    workspace = _Staged(Path(root))
    workspace.manifest_path.write_text(
        json.dumps([dict(record)], indent=2) + "\n", encoding="utf-8"
    )

    # The stage logs its activity under the workspace it is given; entered
    # here first with the STAGING folder, its log lands there, not in the
    # workspace's own logs/.
    @workspace_activity("rebuild collection")
    def collect_in(workspace: Path) -> Any:
        return collect_module.collect_once(
            staged, interval=0.0, sleep=lambda _seconds: None, observer=settled_observer
        )

    staged = workspace
    try:
        with _collect_read_only(), warnings.catch_warnings():
            warnings.simplefilter("ignore")
            report = collect_in(folder)
    except _WouldWriteError as error:
        return dict(record), f"{error}; pyfs-matrix collect does that, a rebuild does not"
    (row,) = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    if row.get("status") == "SUBMITTED":
        detail = "; ".join(
            outcome.detail for outcome in (*report.waiting, *report.unknown, *report.failed)
        )
        return row, f"collect left it SUBMITTED: {detail}"
    return row, None


# ---------------------------------------------------------------------------
# rebuild: the evidence around the simulation folders
# ---------------------------------------------------------------------------


def _read_rows(path: Path) -> list[dict[str, Any]] | None:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    if isinstance(document, dict) and isinstance(document.get("runs"), list):
        document = document["runs"]
    if not isinstance(document, list):
        return None
    return [row for row in document if isinstance(row, dict)]


_SIM_IN_RUN_ID = re.compile(r"(?:^|/)sim_([^/]+)(?:/|$)")


def _sim_of(row: Mapping[str, Any]) -> str | None:
    if row.get("sim_id") not in (None, ""):
        return str(row["sim_id"])
    match = _SIM_IN_RUN_ID.search(str(row.get("run_id", "")))
    return match.group(1) if match else None


@dataclasses.dataclass
class _Known:
    """What some file other than the lost record still says about a simulation's run."""

    campaign: str | None = None
    name_from: str | None = None
    name_from_known: bool = False
    package_version: str | None = None
    point_name_template: str | None = None
    matrix_stem: str | None = None
    source: str = ""


def _known_runs(base: Path, rows: list[dict[str, Any]]) -> dict[str, _Known]:
    """Per simulation: the campaign, the version and the template a surviving file names.

    Read, first found wins: the manifest's own rows, the archived manifests
    newest first, then each matrix's sweep table (``campaign_sweep.csv``,
    which carries the run id and the package version of every point it
    tabled) and plan receipt.
    """
    known: dict[str, _Known] = {}

    def take(row: Mapping[str, Any], source: str) -> None:
        sim = _sim_of(row)
        run_id = str(row.get("run_id", ""))
        if sim is None or sim in known or "/" not in run_id or "deleted_sim" in row:
            return
        known[sim] = _Known(
            campaign=run_id.split("/", 1)[0],
            name_from=row.get("campaign_name_from"),
            name_from_known="campaign_name_from" in row,
            package_version=(str(row["package_version"]) if row.get("package_version") else None),
            point_name_template=row.get("point_name_template"),
            matrix_stem=row.get("matrix_stem"),
            source=source,
        )

    for row in rows:
        take(row, DEFAULT_MANIFEST)
    archived = sorted(_root_archives(base, DEFAULT_MANIFEST), key=lambda item: item.key)
    for item in reversed(archived):
        for row in _read_rows(item.path) or []:
            take(row, _relative(base, item.path))
    post = base / "post"
    for folder in sorted(post.iterdir()) if post.is_dir() else []:
        table = folder / "campaign_sweep.csv"
        if table.is_file():
            with table.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    take({**row, "matrix_stem": folder.name}, _relative(base, table))
    return known


def _plan_campaign_name(base: Path, stem: str) -> tuple[str | None, str | None]:
    receipt = base / "post" / stem / "plan.json"
    try:
        document = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None, None
    if not isinstance(document, dict):
        return None, None
    return document.get("campaign"), document.get("campaign_name_from")


def _on_disk(base: Path) -> tuple[set[str], set[str]]:
    folders: set[str] = set()
    zipped: set[str] = set()
    sims = base / "sims"
    for path in sims.iterdir() if sims.is_dir() else []:
        match = re.fullmatch(r"sim_(.+?)(\.zip)?", path.name)
        if not match:
            continue
        if match.group(2) and path.is_file():
            zipped.add(match.group(1))
        elif not match.group(2) and path.is_dir():
            folders.add(match.group(1))
    return folders, zipped


def _snapshot(root: Path, skip: Path | None) -> dict[str, tuple[int, int]]:
    """Every path under ``root`` with its size and modification time."""
    seen: dict[str, tuple[int, int]] = {}
    for folder, dirs, files in os.walk(root, followlinks=False):
        here = Path(folder)
        if skip is not None and (here == skip or skip in here.parents):
            dirs[:] = []
            continue
        for name in dirs:
            seen[(here / name).relative_to(root).as_posix() + "/"] = (-1, -1)
        for name in files:
            path = here / name
            try:
                info = path.lstat()
            except OSError:
                continue
            seen[path.relative_to(root).as_posix()] = (info.st_size, info.st_mtime_ns)
    return seen


def _changes(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    changes = [f"removed: {path}" for path in sorted(set(before) - set(after))]
    changes += [f"created: {path}" for path in sorted(set(after) - set(before))]
    changes += [
        f"changed: {path}"
        for path in sorted(set(before) & set(after))
        if before[path] != after[path]
    ]
    return changes


def _matrices(base: Path, matrix: str | Path | None, notes: list[str]) -> list[Path]:
    """Return the matrices to rebuild from: the named revision, or every one there is.

    A workspace keeps a matrix at its root or in ``inputs/matrices/``. One
    stem in both homes is read once when the two files hold the same bytes,
    and left out with a note naming both when they differ, since which one
    ran cannot be told from here.
    """
    if matrix is not None:
        return [Path(matrix).resolve()]
    by_stem: dict[str, list[Path]] = {}
    for folder in (base, base / "inputs" / "matrices"):
        for path in sorted(folder.glob("*.fs")) if folder.is_dir() else []:
            by_stem.setdefault(path.stem, []).append(path.resolve())
    chosen = []
    for stem, paths in sorted(by_stem.items()):
        if len(paths) > 1 and len({path.read_bytes() for path in paths}) > 1:
            notes.append(
                f"the matrix {stem} is at {paths[0]} and at {paths[1]} with different content; "
                "it is left out: pass the one that ran as matrix (CLI: --matrix FILE)"
            )
            continue
        chosen.append(paths[0])
    return chosen


def _reactivate(matrix: Path, sims: set[str]) -> list[str]:
    """Set RUN to 1 on the rows whose POL is one of ``sims``, in THIS (shadow) file."""
    lines = matrix.read_text(encoding="utf-8").splitlines(keepends=True)
    header: tuple[int, int] | None = None
    changed: list[str] = []
    for index, line in enumerate(lines):
        cells = line.split("|")
        names = [cell.strip() for cell in cells]
        if header is None and "POL" in names and "RUN" in names:
            header = (names.index("POL"), names.index("RUN"))
            continue
        if header is None or len(cells) <= max(header):
            continue
        pol, run = names[header[0]], names[header[1]]
        if pol in sims and run == "0":
            width = len(cells[header[1]])
            cells[header[1]] = cells[header[1]].replace("0", "1", 1) if width else "1"
            lines[index] = "|".join(cells)
            changed.append(pol)
    if changed:
        matrix.write_text("".join(lines), encoding="utf-8")
    return changed


def _copy_inputs(source: Path, target: Path, origin: Path | None) -> list[str]:
    """Copy ``inputs/`` into the shadow, then lay ``origin``'s files over it.

    Returns the input files, relative to ``inputs/``, that ``origin`` holds
    with bytes other than the workspace's: the inputs taken from the other
    origin. Nothing in the workspace's own ``inputs/`` is written.
    """
    if source.is_dir():
        shutil.copytree(source, target, symlinks=False)
    else:
        target.mkdir(parents=True)
    differing: list[str] = []
    if origin is None:
        return differing
    for path in sorted(origin.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(origin)
        own = source / relative
        if not own.is_file() or own.read_bytes() != path.read_bytes():
            differing.append(relative.as_posix())
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
    return differing


# ---------------------------------------------------------------------------
# rebuild: the identity of a script
# ---------------------------------------------------------------------------


def _slashes(text: str) -> str:
    return text.replace("\\", "/")


@dataclasses.dataclass
class _Comparison:
    same: bool
    run_root: str | None
    rendered: list[str]
    executed: list[str]


def _compare_scripts(rendered: str, executed: str, shadow: Path) -> _Comparison:
    """Ask whether the executed script is the rendered one, once the roots are set aside.

    A run on a cluster names a POSIX root with forward slashes; a rebuild on
    Windows renders the shadow with backslashes (RST-5). Both sides are
    compared with every backslash turned into a forward slash, the workspace
    root on each side replaced by one token, and the interpreter path by
    another. The run's root is returned AS THE EXECUTED SCRIPT SPELLS IT.
    """
    shadow_form = _slashes(str(shadow))
    rendered_lines = [_slashes(line) for line in rendered.splitlines()]
    executed_raw = executed.splitlines()
    executed_lines = [_slashes(line) for line in executed_raw]
    run_root = None
    for index, line in enumerate(rendered_lines):
        if shadow_form not in line:
            continue
        head, tail = line.split(shadow_form, 1)
        candidates = ([index] if index < len(executed_lines) else []) + list(
            range(len(executed_lines))
        )
        for number in candidates:
            other = executed_lines[number]
            if (
                other.startswith(head)
                and other.endswith(tail)
                and len(other) >= len(head) + len(tail)
            ):
                middle = other[len(head) : len(other) - len(tail)]
                raw = executed_raw[number]
                run_root = (
                    raw[len(head) : len(head) + len(middle)] if len(raw) == len(other) else middle
                )
                break
        break
    token = "<workspace>"
    left = [
        _INTERPRETER.sub('"<python>"', line.replace(shadow_form, token)) for line in rendered_lines
    ]
    root_form = _slashes(run_root) if run_root else None
    right = [
        _INTERPRETER.sub('"<python>"', line.replace(root_form, token) if root_form else line)
        for line in executed_lines
    ]
    return _Comparison(left == right, run_root, left, right)


#: Where each drift class's lines come from when no changed word names an
#: input: the row's inputs under these folders are the candidates.
_DRIFT_HOMES = {
    "VTK export line": ("pproc/",),
    "loads frame line": ("pproc/", "references/"),
    "plot type line": ("pproc/",),
}

_VERB = re.compile(r"^[A-Z][A-Z0-9_]*(?:\s|$)")


def _commands(lines: Sequence[str]) -> list[tuple[int, str]]:
    """Group script lines into commands: a verb line and the argument lines after it."""
    commands: list[tuple[int, list[str]]] = []
    for number, line in enumerate(lines):
        if not line.strip():
            continue
        if _VERB.match(line) or not commands:
            commands.append((number, [line.strip()]))
        else:
            commands[-1][1].append(line.strip())
    return [(number, " | ".join(parts)) for number, parts in commands]


def _drift(comparison: _Comparison, inputs: Path, input_files: Sequence[str]) -> str:
    """Name each difference between the executed and the rendered script (RST-8).

    The scripts are compared command by command (a verb and its argument
    lines). Each changed command says what it is (a VTK export line, the
    loads frame line, a plot type line, a renamed pproc group, or a script
    line) and which of the row's inputs holds the text the package renders
    there now, so a reader knows WHICH input changed after the run rather
    than only that something did. An input is named when it holds a word the
    two sides differ by; failing that, the inputs a class's lines come from
    are named as candidates.
    """
    texts = {}
    for name in input_files:
        with contextlib.suppress(OSError, UnicodeDecodeError):
            texts[name] = (inputs / name).read_text(encoding="utf-8")
    ran_commands = _commands(comparison.executed)
    render_commands = _commands(comparison.rendered)
    matcher = difflib.SequenceMatcher(
        a=[text for _, text in ran_commands],
        b=[text for _, text in render_commands],
        autojunk=False,
    )
    items: list[tuple[int, str, str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        ran = list(ran_commands[i1:i2])
        renders = list(render_commands[j1:j2])
        at = ran[0][0] if ran else (ran_commands[i1][0] if i1 < len(ran_commands) else 0)
        while ran or renders:
            if ran and renders and ran[0][1].split(" ")[0] == renders[0][1].split(" ")[0]:
                (line, left), (_, right) = ran.pop(0), renders.pop(0)
            elif ran and (
                not renders
                or ran[0][1].split(" ")[0] not in {text.split(" ")[0] for _, text in renders}
            ):
                (line, left), right = ran.pop(0), ""
            else:
                left, (line, right) = "", renders.pop(0)
                line = at
            items.append((line, left, right))
    described: list[str] = []
    for line, left, right in items[:6]:
        verb = (left or right).split(" ")[0]
        what = _DRIFT_VERBS.get(verb)
        left_words = {word for word in re.split(r"[\s,|]+", left) if word}
        right_words = {word for word in re.split(r"[\s,|]+", right) if word}
        words = [word for word in left_words ^ right_words if len(word) > 2 and word != verb]
        holders = sorted(
            name
            for name, text in texts.items()
            if any(
                re.search(rf"(?<![A-Za-z0-9_]){re.escape(word)}(?![A-Za-z0-9_])", text)
                for word in words
            )
        )
        if what is None:
            what = (
                "pproc group renamed"
                if any(name.startswith("pproc/") for name in holders)
                else "script line"
            )
        if holders:
            where = f"from inputs/{', inputs/'.join(holders)}"
        else:
            homes = _DRIFT_HOMES.get(what, ())
            candidates = [name for name in input_files if name.startswith(homes)] if homes else []
            where = (
                f"from inputs/{', inputs/'.join(candidates)} (candidates)"
                if candidates
                else "from no input of the row (the package's own rendering)"
            )
        described.append(
            f"line {line + 1}: ran {left[:90] or '(nothing)'!r}, renders "
            f"{right[:90] or '(nothing)'!r} ({what}, {where})"
        )
    if len(items) > 6:
        described.append(f"and {len(items) - 6} more changed command(s)")
    return "; ".join(described) or (
        f"ran {len(comparison.executed)} lines, renders {len(comparison.rendered)}"
    )


# ---------------------------------------------------------------------------
# rebuild: one simulation, re-minted in the shadow
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _Outcome:
    records: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    refused: dict[str, str] = dataclasses.field(default_factory=dict)
    notes: list[str] = dataclasses.field(default_factory=list)
    never_ran: list[str] = dataclasses.field(default_factory=list)
    waiting: list[str] = dataclasses.field(default_factory=list)
    changes: list[str] = dataclasses.field(default_factory=list)
    aliases: dict[str, str] = dataclasses.field(default_factory=dict)


def _row_inputs(matrix: Path, pol: str) -> list[str]:
    """Return the reference, setup and pproc files a row names, relative to ``inputs/``."""
    from pyflightstream.cases.matrix import read_matrix

    try:
        rows = read_matrix(matrix, active_only=False)
    except Exception:  # noqa: BLE001 - an unreadable matrix names no input; its refusal comes later
        return []
    for row in rows:
        if str(row.pol) == pol:
            names = []
            for folder, code in (
                ("references", row.ref_code),
                ("setups", row.set_code),
                ("pproc", row.pproc_code),
            ):
                if code:
                    names.append(f"{folder}/{code}.toml")
            return names
    return []


def _stub_profile() -> Any:
    from pyflightstream.workspace.inputs import HpcProfile

    return HpcProfile(
        application_id="pyfs-rebuild-no-submission",
        descriptor_format="text",
        descriptor_name="pyfs_rebuild_no_submission.txt",
        fields={"script": "{script_path}"},
        submit=("true",),
        defaults={},
        path=Path("pyfs-rebuild-no-submission.toml"),
    )


@dataclasses.dataclass
class _Context:
    base: Path
    shadow: Path
    version: str
    profile: Any
    build_alias: Mapping[str, str]
    origin: Path | None
    origin_differs: list[str]
    known: dict[str, _Known]
    quiet_window_s: float


def _mint(
    context: _Context,
    matrix: Path,
    sim: str,
    template: str,
    name: str,
    name_from: str | None,
    out: _Outcome,
    notes: list[str],
) -> tuple[list[dict[str, Any]], str] | str:
    """Run one simulation's row in the shadow with nothing submitted.

    Returns the SUBMITTED rows the loop wrote and the rendered script text,
    or the refusal.
    """
    from pyflightstream.cases.workflows import workflow_registry
    from pyflightstream.run import (
        CampaignErrors,
        LoadsAssessor,
        SubmittingExecutor,
        plan_campaign,
        run_campaign,
    )
    from pyflightstream.workspace import CampaignWorkspace
    from pyflightstream.workspace.matrix import resolve_matrix
    from pyflightstream.workspace.naming import NamingTemplate

    shadow = context.shadow
    workspace = CampaignWorkspace(shadow, naming=NamingTemplate(point_name=template))
    resolved = resolve_matrix(
        matrix, workspace, name=name, fs_version=None, recipes={}, ignore_missing_families=True
    )
    cases = list(resolved.campaign.sims)
    index = next(number for number, case in enumerate(cases) if str(case.sim_id) == sim)
    campaign = resolved.campaign.model_copy(update={"sims": [cases[index]]})
    row_builds = resolved.row_builds
    if len(row_builds) == len(cases):
        row_builds = (row_builds[index],)
    one = dataclasses.replace(resolved, campaign=campaign, row_builds=row_builds)
    build = row_builds[0] if row_builds else None
    profile = context.profile
    if profile is not None and profile.builds and build and build not in profile.builds:
        alias = context.build_alias.get(build, build)
        profile = dataclasses.replace(profile, builds={**profile.builds, build: alias})
        line = (
            f"the submission profile maps no scheduler name for build {build}; {alias} was "
            f"assumed (build_alias, CLI: --build-alias {build}=ALIAS; the build itself by "
            "default), in the job descriptor only: the solver script does not carry it"
        )
        if build not in out.aliases:
            out.notes.append(line)
        out.aliases[build] = alias
        notes.append(line)
    plan = plan_campaign(
        campaign,
        workspace,
        recipes=workflow_registry(),
        versions=row_versions(one),
        matrix_path=matrix,
        write_plan=False,
    )
    if plan.blocked:
        return (
            f"pyflightstream {context.version} refuses this row now, so its record cannot be "
            f"minted again: {plan.blocked[0].error}"
        )
    executor = SubmittingExecutor(
        profile or _stub_profile(),
        values={"fs_build": build or campaign.fs_version or ""},
        submit=False,
    )
    executor, executor_for = campaign_executor(workspace, one, matrix, executor=executor)
    bound, builds = bind_row_builds(one, None, executor, executor_for)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            run_campaign(
                bound,
                executor,
                workspace,
                assess=LoadsAssessor(),
                recipes=workflow_registry(),
                builds=builds,
                name_from=name_from,
                preflight=False,
                quiet=True,
            )
        except CampaignErrors:
            pass
    rows = [row for row in workspace.read_raw_manifest() if str(row.get("sim_id")) == sim]
    bad = [row for row in rows if row.get("status") != "SUBMITTED"]
    if bad or not rows:
        reason = f"{bad[0].get('status')}: {bad[0].get('error')}" if bad else "no record came out"
        return f"the package could not mint this row's record again ({reason})"
    scripts = {str(row["script_path"]) for row in rows}
    rendered = "\n".join(
        (shadow / "sims" / f"sim_{sim}" / script).read_text(encoding="utf-8", errors="replace")
        for script in sorted(scripts)
    )
    return rows, rendered


def _clear_shadow_run(shadow: Path, sim: str) -> None:
    (shadow / DEFAULT_MANIFEST).unlink(missing_ok=True)
    shutil.rmtree(shadow / "sims" / f"sim_{sim}", ignore_errors=True)


def _join_root(run_root: str, relative: Path) -> str:
    """Join a relative path onto the run's own root, in that root's separator style."""
    if run_root.startswith("/"):
        return run_root.rstrip("/") + "/" + relative.as_posix()
    return str(Path(run_root) / relative)


def _substitute(record: dict[str, Any], pairs: Sequence[tuple[str, str]]) -> dict[str, Any]:
    """Replace every spelling of the shadow root by the run's root, in its own style."""
    text = json.dumps(record)
    for old, new in pairs:
        if not old or old == new:
            continue
        text = text.replace(json.dumps(old)[1:-1], json.dumps(new)[1:-1])
        if new.startswith("/"):
            escaped = json.dumps(new)[1:-1]
            text = re.sub(
                re.escape(escaped) + r'[^"]*',
                lambda match: match.group(0).replace("\\\\", "/"),
                text,
            )
    loaded: dict[str, Any] = json.loads(text)
    return loaded


def _utc(path: Path) -> str:
    return dt.datetime.fromtimestamp(path.stat().st_mtime, dt.UTC).isoformat(timespec="seconds")


def _rebuild_one(
    context: _Context,
    matrix: Path,
    sim: str,
    name: str,
    name_from: str | None,
    templates: Sequence[str],
    notes: list[str],
    out: _Outcome,
) -> None:
    """Mint, prove and complete the records of one simulation, or refuse it."""
    base, shadow = context.base, context.shadow
    sim_dir = base / "sims" / f"sim_{sim}"
    minted: tuple[list[dict[str, Any]], str] | None = None
    refusal = "no point-name template names a script that is in the folder"
    for template in templates:
        try:
            attempt = _mint(context, matrix, sim, template, name, name_from, out, notes)
        except Exception as error:  # noqa: BLE001 - every refusal of the package is this sim's reason
            _clear_shadow_run(shadow, sim)
            refusal = (
                "the package could not mint this row's record again: "
                f"{type(error).__name__}: {error}"
            )
            break
        _clear_shadow_run(shadow, sim)
        if isinstance(attempt, str):
            refusal = attempt
            break
        rows, _rendered = attempt
        missing = [
            row["script_path"] for row in rows if not (sim_dir / row["script_path"]).is_file()
        ]
        if missing:
            refusal = (
                f"the package names its script {missing[0]}, which is not in the folder: the run "
                "used another point-name template or another matrix"
            )
            continue
        minted = attempt
        break
    if minted is None:
        out.refused[sim] = refusal
        return
    rows, rendered = minted
    executed = "\n".join(
        (sim_dir / script).read_text(encoding="utf-8", errors="replace")
        for script in sorted({str(row["script_path"]) for row in rows})
    )
    comparison = _compare_scripts(rendered, executed, shadow)
    known = context.known.get(sim)
    ran_on = known.package_version if known else None
    if ran_on and ran_on != context.version:
        out.refused[sim] = (
            f"the run was recorded by pyflightstream {ran_on} "
            f"({known.source if known else ''}) and "
            f"this is pyflightstream {context.version}: a record is rebuilt only by the version "
            f"that ran, since the proof is the script that version renders; rebuild it with "
            f"pyflightstream {ran_on}"
        )
        return
    inputs_used = _row_inputs(shadow / matrix.name, sim) or _row_inputs(matrix, sim)
    if not comparison.same:
        detail = _drift(comparison, shadow / "inputs", inputs_used)
        origin = (
            f" with the inputs of {context.origin} laid over the workspace's"
            if context.origin
            else ""
        )
        out.refused[sim] = (
            f"refused: the executed script is not the script pyflightstream {context.version} "
            f"renders for this row from this matrix and these inputs{origin}: {detail}. If an "
            "input changed after the run, pass the inputs that ran (CLI: --inputs-from "
            "<their inputs/ folder>); if the run was on another version, rebuild with that one"
        )
        return
    for row in rows:
        facts = _facts(context, sim_dir, row)
        if facts is None:
            out.never_ran.append(str(row["run_id"]))
            continue
        if isinstance(facts, str):
            out.refused[sim] = facts
            return
        facts["run_root"] = comparison.run_root
        facts["inputs_used"] = inputs_used
        if facts.get("keep_submitted"):
            completed, deferred = dict(row), facts["keep_submitted"]
        else:
            completed, deferred = collect_without_writing(
                base, row, staging=shadow / "collect" / f"sim_{sim}"
            )
        record = _finalise(context, sim, completed, facts, deferred, notes)
        try:
            from pyflightstream.workspace import RunRecord

            RunRecord.model_validate(record)
        except Exception as error:  # noqa: BLE001 - the model's refusal is the reason given
            out.refused[sim] = f"the rebuilt record does not validate: {error}"
            return
        out.records.append(record)


def _facts(context: _Context, sim_dir: Path, row: Mapping[str, Any]) -> dict[str, Any] | str | None:
    """Where the minted record's outputs are, and whether its job is over.

    None for a point with no datapoint folder (it never ran); a string for a
    refusal; else the facts the completion needs.
    """
    from pyflightstream.workspace.naming import PointName, datapoint_dir_name

    submission = row.get("submission") or {}
    working = submission.get("working_dir")
    work_dir = sim_dir / working if working else sim_dir
    by_point = submission.get("declared_by_point") or {}
    point_dirs = (
        [sim_dir / "datapoints" / datapoint_dir_name(PointName(tag)) for tag in by_point]
        if by_point
        else [work_dir]
    )
    present = [folder for folder in point_dirs if folder.is_dir()]
    if not present:
        return None
    profile = context.profile
    submitted_here = bool(profile is not None and (work_dir / profile.descriptor_name).is_file())
    declared = [str(name) for name in submission.get("declared_outputs") or []]

    def where(name: str) -> Path | None:
        for folder in [work_dir, *present]:
            if (folder / name).is_file():
                return folder / name
        return None

    found = {name: where(name) for name in declared}
    newest = max(
        (
            path.stat().st_mtime
            for folder in present
            for path in folder.rglob("*")
            if path.is_file()
        ),
        default=0.0,
    )
    quiet = time.time() - newest >= context.quiet_window_s
    facts: dict[str, Any] = {
        "work_dir": work_dir,
        "submitted_here": submitted_here,
        "found": found,
    }
    if not any(found.values()):
        if submitted_here:
            facts["keep_submitted"] = (
                "no declared output has landed yet: the job may be queued, running or lost; "
                "pyfs-matrix collect waits for it"
            )
        else:
            return (
                f"{row['run_id']}: its datapoint folder holds no declared output, so there is "
                "no run to record"
            )
    elif not quiet:
        facts["keep_submitted"] = (
            f"files changed less than {context.quiet_window_s / 60:g} minutes ago: the job may "
            "still be writing; pyfs-matrix collect completes it once it settles"
        )
    return facts


def _finalise(
    context: _Context,
    sim: str,
    record: dict[str, Any],
    facts: Mapping[str, Any],
    deferred: str | None,
    notes: Sequence[str],
) -> dict[str, Any]:
    """Put back what the shadow could not know, and say what was reconstructed."""
    from pyflightstream.run import LocalExecutor
    from pyflightstream.run.collect import assessment_of_collected
    from pyflightstream.workspace import CampaignWorkspace, RunRecord

    base, shadow = context.base, context.shadow
    sim_dir = base / "sims" / f"sim_{sim}"
    run_root = facts.get("run_root") or str(base)
    record = _substitute(record, [(str(shadow), run_root), (shadow.as_posix(), _slashes(run_root))])
    reconstructed = ["started_at", "finished_at"]
    work_dir: Path = facts["work_dir"]
    script = sim_dir / record["script_path"]
    record["script_sha256"] = file_sha256(script)
    digests = {}
    for key, value in (record.get("inputs_sha256") or {}).items():
        for folder in (work_dir, sim_dir / "inputs", sim_dir):
            if (folder / key).is_file():
                digests[key] = file_sha256(folder / key)
                break
        else:
            digests[key] = value
    record["inputs_sha256"] = digests
    workspace = CampaignWorkspace(base)
    with contextlib.suppress(Exception):
        staged_as, reason = workspace.staged_as(sim)
        if staged_as is not None:
            record["staged_as"], record["staged_as_reason"] = staged_as, reason
    status = record.get("status")
    if facts["submitted_here"]:
        descriptor = work_dir / context.profile.descriptor_name
        submission = dict(record.get("submission") or {})
        submission["submitted"] = True
        record["submission"] = submission
        record["started_at"] = record["finished_at"] = _utc(descriptor)
    else:
        if status == "SUBMITTED":
            submission = dict(record.get("submission") or {})
            submission.update(
                {"descriptor": None, "profile": None, "application_id": None, "submitted": False}
            )
            record["submission"] = submission
        else:
            record["submission"] = None
        posix = run_root.startswith("/")
        own_root = facts.get("run_root") is not None
        record["cwd"] = (
            _join_root(run_root, work_dir.relative_to(base)) if own_root else str(work_dir)
        )
        script_at_run = _join_root(run_root, script.relative_to(base)) if own_root else str(script)
        try:
            local = LocalExecutor(record["fs_exe"], hidden=True)
            argv = [str(item) for item in local._argv(Path(script_at_run))]
            if posix:
                argv = [
                    script_at_run if item == str(Path(script_at_run)) else item for item in argv
                ]
        except Exception:  # noqa: BLE001 - an executable not on this machine still has an argv
            argv = [str(record.get("fs_exe")), "-script", script_at_run]
        record["argv"] = argv
        record["executor"] = {"class_name": "LocalExecutor", "argv": argv}
        reconstructed += ["argv", "executor", "cwd"]
        record["started_at"] = _utc(script)
        log = record.get("log_file_used")
        ends = (
            [work_dir / log]
            if log and (work_dir / log).is_file()
            else [path for path in facts["found"].values() if path is not None]
        )
        record["finished_at"] = (
            _utc(max(ends, key=lambda path: path.stat().st_mtime)) if ends else record["started_at"]
        )
        record["wall_time_s"] = None
        if status != "SUBMITTED":
            with contextlib.suppress(Exception):
                record["outputs_sha256"] = workspace.output_digests(
                    sim, record.get("outputs") or []
                )
                reconstructed.append("outputs_sha256 (hashed now)")
            with contextlib.suppress(Exception):
                assessment = assessment_of_collected(RunRecord.model_validate(record), sim_dir)
                record["fs_version_reported"] = assessment.fs_version_reported
                record["fs_build"] = assessment.fs_build
    stamp = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    lost = [] if facts["submitted_here"] else ["wall_time_s"]
    note = (
        f"{REBUILT} on {stamp} from sims/sim_{sim} with pyflightstream {context.version}: not "
        "the record written when it ran. The setup fields come from the package running the "
        "matrix row again with nothing submitted, proved by the executed script being the one "
        "this version renders; status and solver figures from the package's collect stage over "
        f"the files on disk; reconstructed: {', '.join(reconstructed)}"
        + (f"; not recoverable: {', '.join(lost)}" if lost else "")
        + "."
    )
    if deferred:
        note += f" Left SUBMITTED: {deferred}"
    extra = list(dict.fromkeys(notes))
    used = set(facts.get("inputs_used") or [])
    taken = [name for name in context.origin_differs if name in used] or (
        list(context.origin_differs) if context.origin_differs and not used else []
    )
    if context.origin is not None and taken:
        extra.append(
            "DRIFT: input(s) "
            + ", ".join(f"inputs/{name}" for name in taken)
            + f" taken from {context.origin}, whose bytes differ from the workspace's; the "
            "workspace's own files were not changed"
        )
    record["warnings"] = [*list(record.get("warnings") or []), note, *extra]
    return record


# ---------------------------------------------------------------------------
# rebuild: the entry
# ---------------------------------------------------------------------------


def _refuse_before_any_work(
    base: Path,
    out: str | None,
    all_sims: bool,
    sims: Sequence[str] | None,
    matrix: str | Path | None,
    inputs_from: str | Path | None,
) -> Path | None:
    """Every refusal a rebuild can make from its arguments alone, before it reads anything."""
    if all_sims and out is None:
        raise RecordsError(
            "rebuild all_sims (CLI: --all-sims) needs out (CLI: --out), the manifest NAME: it "
            "rebuilds every simulation to compare with runs.json, and never writes runs.json"
        )
    if all_sims and sims:
        raise RecordsError(
            "rebuild: all_sims (CLI: --all-sims) is every simulation on disk; give it or sims "
            "(CLI: --sims), not both"
        )
    target = None
    if out is not None:
        target = resolve_manifest(base, out)
        if target.name.lower() == DEFAULT_MANIFEST:
            raise RecordsError(
                f"rebuild out (CLI: --out) may not be {DEFAULT_MANIFEST}: out names another file, "
                "so runs.json is never touched; choose another name"
            )
        if target.exists():
            raise RecordsError(
                f"rebuild out (CLI: --out) {out}: the file exists; choose a new name, nothing "
                "is overwritten"
            )
    if matrix is not None and not Path(matrix).is_file():
        raise RecordsError(f"rebuild matrix (CLI: --matrix) {matrix}: no such file")
    if inputs_from is not None and not Path(inputs_from).is_dir():
        raise RecordsError(
            f"rebuild inputs_from (CLI: --inputs-from) {inputs_from}: no such folder; name the "
            "inputs/ folder of the workspace whose inputs ran"
        )
    return target


def rebuild(
    root: str | Path,
    *,
    out: str | None = None,
    all_sims: bool = False,
    sims: Sequence[str] | None = None,
    build_alias: Mapping[str, str] | None = None,
    matrix: str | Path | None = None,
    apply: bool = False,
    inputs_from: str | Path | None = None,
) -> dict[str, Any]:
    """Rebuild run records from the simulation folders under ``sims/``.

    Each record is minted again by this package from the matrix row, proved
    by the executed script being the one this version renders for that row,
    and completed by the collect stage over the files on disk, read-only (the
    module docstring says how). A record the rebuild makes carries a warning
    starting with ``REBUILT`` that says what was reconstructed and with which
    version.

    Parameters
    ----------
    root : str or Path
        The workspace root.
    out : str, optional
        The manifest file the rebuilt records go to, a name
        :func:`resolve_manifest` accepts, never ``runs.json`` and never a file
        that exists: both refused before any work. With it ``runs.json`` is
        never touched: the file holds the rows of ``runs.json`` with each
        rebuilt record in the place of the row of its run id, and the other
        rebuilt records after them (with ``all_sims``, the rebuilt records
        only). Without it, applying appends the rebuilt records whose
        run ids ``runs.json`` does not hold, after archiving ``runs.json`` to
        ``archive/runs-<stamp>.json``, or writes ``runs.json`` when there is
        none.
    all_sims : bool, default False
        Rebuild EVERY simulation folder on disk, recorded or not, so the result
        can be compared with ``runs.json``; requires ``out``. A SUBMITTED status
        in ``runs.json`` is then ignored and each simulation takes the status
        its outputs support, except a folder written within
        :data:`QUIET_WINDOW_S`, which stays SUBMITTED. Without it only the
        simulations no record names are rebuilt, and each SUBMITTED record is
        pointed to ``pyfs-matrix collect`` rather than given an end.
    sims : sequence of str, optional
        The simulation ids to rebuild, recorded or not.
    build_alias : mapping of str to str, optional
        The scheduler name a solver build had when it ran, keyed by the build,
        for a build the submission profile no longer maps; the default is the
        build itself. It enters only the job descriptor of the shadow run,
        never the solver script, and the record says which alias was assumed.
    matrix : str or Path, optional
        The matrix revision the simulations ran from, for a POL no current
        matrix holds (a row deleted or renumbered after it ran). Name the file
        as the matrix was named when it ran. Without it every matrix at the
        root and in ``inputs/matrices/`` is read.
    apply : bool, default False
        Write the manifest; without it the call previews and writes nothing.
    inputs_from : str or Path, optional
        Another origin's ``inputs/`` folder (another workspace's, a copy from
        the cluster) whose files are laid over this workspace's in the shadow,
        for inputs that changed after the run. Each record names the inputs it
        took from there whose bytes differ from the workspace's; the
        workspace's own files are never changed.

    Returns
    -------
    dict
        ``target`` (the manifest applying writes), ``applied``, ``written``,
        ``archived_as``, ``package_version``, ``rebuilt`` (sim, run id and
        status per record), ``records`` (the rebuilt records), ``refused`` (by
        sim, the reason), ``submitted`` (the SUBMITTED run ids pointed to
        collect), ``waiting_for_matrix`` (the sims no matrix row names),
        ``never_ran``, ``build_aliases`` and ``notes``.

    Raises
    ------
    RunsManifestError
        ``out`` is not a file name directly in the root.
    RecordsError
        ``all_sims`` without ``out``, or with ``sims``; ``out`` naming
        ``runs.json`` or a file that exists; a ``matrix`` or ``inputs_from``
        that is not there; no ``sims/``; a run holding ``runs.json.lock``;
        applying when nothing was rebuilt, when the workspace tree changed
        during the rebuild, or when ``runs.json`` changed meanwhile.
    """
    import pyflightstream
    from pyflightstream.workspace.inputs import resolve_hpc_profile
    from pyflightstream.workspace.naming import MATRIX_POINT_NAME, NamingTemplate

    base = Path(root).resolve()
    target = _refuse_before_any_work(base, out, all_sims, sims, matrix, inputs_from)
    lock = base / (DEFAULT_MANIFEST + ".lock")
    if lock.exists():
        raise RecordsError(
            f"rebuild: {lock.name} is present, so a run is writing runs.json; try again when "
            "it ends. Nothing was read or written."
        )
    if not (base / "sims").is_dir():
        raise RecordsError(f"rebuild: {base} holds no sims/ folder; run it at the workspace root")
    manifest = base / DEFAULT_MANIFEST
    manifest_bytes = manifest.read_bytes() if manifest.is_file() else None
    rows = _read_rows(manifest) if manifest_bytes is not None else []
    if rows is None:
        raise RecordsError(f"rebuild: {manifest} is not a readable list of run records")
    live = [row for row in rows if "deleted_sim" not in row]
    retired = {str(row["deleted_sim"]) for row in rows if "deleted_sim" in row}
    recorded = {sim for sim in (_sim_of(row) for row in live) if sim is not None}
    submitted_rows = [row for row in live if row.get("status") == "SUBMITTED"]
    submitted_sims = {sim for sim in (_sim_of(row) for row in submitted_rows) if sim}
    folders, zipped = _on_disk(base)
    out_come = _Outcome()
    notes = out_come.notes
    if all_sims:
        wanted = sorted((folders | zipped) - retired)
    elif sims:
        wanted = sorted(dict.fromkeys(str(sim) for sim in sims))
    else:
        wanted = sorted((folders | zipped) - recorded - retired)
    submitted: list[str] = []
    if submitted_rows and not all_sims:
        submitted = sorted(str(row["run_id"]) for row in submitted_rows)
        notes.append(
            f"{len(submitted)} record(s) are SUBMITTED in runs.json: a rebuild gives them no "
            "end; pyfs-matrix collect completes them (then post again)"
        )
    elif submitted_rows:
        notes.append(
            f"{len(submitted_rows)} record(s) are SUBMITTED in runs.json; all_sims ignores that "
            "status and judges each simulation from its outputs"
        )
    todo = []
    for sim in wanted:
        if sim in retired:
            out_come.refused[sim] = "delete-sims retired this simulation; it is not brought back"
        elif sim in zipped and sim not in folders:
            out_come.refused[sim] = (
                "stored compressed (sims/sim_<id>.zip); expand it with the package first, then "
                "rebuild. A rebuild never expands or deletes an archive"
            )
        elif sim not in folders:
            out_come.refused[sim] = "no such simulation folder under sims/"
        elif sim in submitted_sims and not all_sims:
            out_come.refused[sim] = (
                "SUBMITTED in runs.json: a rebuild gives it no end; pyfs-matrix collect "
                "completes it, or rebuild every simulation (all_sims, CLI: --all-sims)"
            )
        else:
            todo.append(sim)
    version = str(pyflightstream.__version__)
    if todo:
        known = _known_runs(base, live)
        _rebuild_all(
            base,
            todo,
            known,
            version,
            matrix=matrix,
            build_alias=dict(build_alias or {}),
            origin=None if inputs_from is None else Path(inputs_from).resolve(),
            profile_of=lambda inputs: resolve_hpc_profile(inputs),
            templates=(MATRIX_POINT_NAME, NamingTemplate().point_name),
            out=out_come,
        )
    entry: dict[str, Any] = {
        "workspace": str(base),
        "target": target.name if target is not None else DEFAULT_MANIFEST,
        "applied": False,
        "written": None,
        "archived_as": None,
        "package_version": version,
        "rebuilt": [
            {
                "sim": str(row.get("sim_id")),
                "run_id": row.get("run_id"),
                "status": row.get("status"),
            }
            for row in out_come.records
        ],
        "records": out_come.records,
        "refused": dict(sorted(out_come.refused.items())),
        "submitted": submitted,
        "waiting_for_matrix": sorted(out_come.waiting),
        "never_ran": out_come.never_ran,
        "build_aliases": dict(out_come.aliases),
        "notes": notes + ([_NOT_RECOVERABLE_NOTE] if out_come.refused else []),
    }
    if out_come.changes:
        entry["changes"] = out_come.changes
    if not apply:
        return entry
    if out_come.changes:
        raise RecordsError(
            f"rebuild: the workspace tree changed during the rebuild ({len(out_come.changes)} "
            f"path(s), first {out_come.changes[0]}): another process is writing; nothing was "
            "written, run it again when it ends"
        )
    if not out_come.records:
        raise RecordsError("rebuild: no record was rebuilt, so there is nothing to write")
    ids = {row.get("run_id") for row in live}
    fresh = [row for row in out_come.records if row.get("run_id") not in ids]
    if target is not None:
        # The file out names holds the REBUILT records: a rebuilt run id that
        # runs.json holds takes that row's place in this copy (runs.json itself
        # is never written), and the others are appended after the rows.
        rebuilt = {row.get("run_id"): row for row in out_come.records}
        written = (
            list(out_come.records)
            if all_sims
            else [rebuilt.get(row.get("run_id"), row) for row in rows] + fresh
        )
        try:
            with target.open("x", encoding="utf-8") as handle:
                handle.write(json.dumps(written, indent=2) + "\n")
        except FileExistsError as error:
            raise RecordsError(
                f"rebuild out (CLI: --out) {target.name}: the file appeared meanwhile; nothing "
                "is overwritten"
            ) from error
        entry.update(applied=True, written=target.name)
        return entry
    if not fresh:
        raise RecordsError(
            "rebuild: every rebuilt run id is already in runs.json; nothing to write (name "
            "out (CLI: --out) to write the rebuilt records beside it)"
        )
    with manifest_lock(base):
        now = manifest.read_bytes() if manifest.is_file() else None
        if now != manifest_bytes:
            raise RecordsError("rebuild: runs.json changed while the rebuild ran; nothing written")
        if now is not None:
            kept = free_root_archive(base, DEFAULT_MANIFEST, _now_stamp())
            kept.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(manifest, kept)
            entry["archived_as"] = _relative(base, kept)
        _replace_bytes(manifest, (json.dumps([*rows, *fresh], indent=2) + "\n").encode("utf-8"))
    entry.update(applied=True, written=DEFAULT_MANIFEST)
    return entry


def summary_lines(entry: Mapping[str, Any]) -> list[str]:
    """Return the lines ``pyfs-matrix restore`` and ``rebuild`` print for an entry.

    The entry is what :func:`restore` or :func:`rebuild` returned: the lines
    say what was, or would be, written, and name every refusal.
    """
    lines: list[str] = []
    if "kind" in entry:
        lines.append(
            f"restore {entry['kind']}: {entry['source']} -> {entry['target']} "
            f"(stamp {entry['stamp']})"
        )
        lines.append(f"  stamps available: {', '.join(entry['stamps_available'])}")
        if "records" in entry:
            lines.append(f"  the archived manifest holds {entry['records']} record(s)")
        if entry["same"]:
            lines.append("  the current file already holds these bytes; nothing to do")
        elif entry["applied"]:
            kept = entry["archived_as"]
            lines.append(
                "  restored" + (f"; the current file was archived as {kept}" if kept else "")
            )
        else:
            lines.append("  preview only: add --apply to restore it")
        return lines
    rebuilt, refused = entry["rebuilt"], entry["refused"]
    lines.append(
        f"rebuild: {len(rebuilt)} record(s) rebuilt with pyflightstream "
        f"{entry['package_version']}, {len(refused)} simulation(s) refused"
    )
    for row in rebuilt:
        lines.append(f"  sim_{row['sim']}: {REBUILT} {row['status']} {row['run_id']}")
    for sim, reason in refused.items():
        lines.append(f"  sim_{sim}: NOT RECOVERABLE: {reason}")
    for run_id in entry["submitted"]:
        lines.append(f"  SUBMITTED, for pyfs-matrix collect: {run_id}")
    if entry["waiting_for_matrix"]:
        lines.append(
            "  waiting for the matrix revision that ran (--matrix FILE): "
            + ", ".join(f"sim_{sim}" for sim in entry["waiting_for_matrix"])
        )
    for run_id in entry["never_ran"]:
        lines.append(f"  never ran (no datapoint folder), no record: {run_id}")
    for line in entry["notes"]:
        lines.append(f"  note: {line}")
    for line in entry.get("changes", [])[:30]:
        lines.append(f"  the workspace changed during the rebuild: {line}")
    if entry["applied"]:
        kept = entry["archived_as"]
        lines.append(
            f"  wrote {entry['written']}"
            + (f"; the previous runs.json was archived as {kept}" if kept else "")
        )
    else:
        lines.append(f"  preview only: add --apply to write {entry['target']}")
    return lines


def _rebuild_all(
    base: Path,
    sims: Sequence[str],
    known: dict[str, _Known],
    version: str,
    *,
    matrix: str | Path | None,
    build_alias: dict[str, str],
    origin: Path | None,
    profile_of: Callable[[Path], Any],
    templates: Sequence[str],
    out: _Outcome,
) -> None:
    """Rebuild ``sims`` in one shadow workspace, proving the real tree unchanged."""
    from pyflightstream.cases.matrix import read_matrix

    notes = out.notes
    matrices = _matrices(base, matrix, notes)
    by_pol: dict[str, Path] = {}
    for path in matrices:
        try:
            pols = [str(row.pol) for row in read_matrix(path, active_only=False)]
        except Exception as error:  # noqa: BLE001 - an unreadable matrix is said, and skipped
            notes.append(
                f"{path.name}: not readable by the package ({type(error).__name__}: {error})"
            )
            continue
        for pol in pols:
            by_pol.setdefault(pol, path)
    remaining = []
    for sim in sims:
        if sim in by_pol:
            remaining.append(sim)
            continue
        out.waiting.append(sim)
        out.refused[sim] = (
            "no row of any current matrix names this simulation (deleted or renumbered after it "
            "ran): pass the matrix revision that ran (CLI: --matrix FILE), for example the old "
            "revision from version control"
        )
    if not remaining:
        return
    shadow = Path(tempfile.mkdtemp(prefix="pyfs-rebuild-")).resolve()
    skip = shadow if (shadow == base or base in shadow.parents) else None
    before = _snapshot(base, skip)
    chatter = shadow.parent / f"{shadow.name}.log"
    try:
        try:
            profile = profile_of(base / "inputs")
        except Exception as error:  # noqa: BLE001 - several profiles: the package refuses to guess
            profile = None
            notes.append(
                f"the workspace's submission profile could not be resolved ({error}); records are "
                "rebuilt as local runs"
            )
        origin_differs = _copy_inputs(base / "inputs", shadow / "inputs", origin)
        context = _Context(
            base=base,
            shadow=shadow,
            version=version,
            profile=profile,
            build_alias=build_alias,
            origin=origin,
            origin_differs=origin_differs,
            known=known,
            quiet_window_s=QUIET_WINDOW_S,
        )
        with (
            chatter.open("w", encoding="utf-8") as stream,
            contextlib.redirect_stdout(stream),
            contextlib.redirect_stderr(stream),
        ):
            for path in matrices:
                chosen = [sim for sim in remaining if by_pol.get(sim) == path]
                if not chosen:
                    continue
                shadow_matrix = shadow / path.name
                shutil.copy2(path, shadow_matrix)
                sim_notes: dict[str, list[str]] = {sim: [] for sim in chosen}
                for pol in _reactivate(shadow_matrix, set(chosen)):
                    sim_notes[pol].append(
                        f"the row of sim_{pol} has RUN 0 in {path.name}: it was rebuilt with RUN 1 "
                        "in the shadow copy only; the matrix was not changed"
                    )
                for sim in chosen:
                    identity = known.get(sim)
                    if identity is not None and identity.campaign:
                        name, name_from = identity.campaign, identity.name_from
                        if not identity.name_from_known:
                            name_from = None
                    else:
                        planned, planned_from = _plan_campaign_name(base, path.stem)
                        name, name_from = (
                            (planned, planned_from) if planned else (base.name, "directory")
                        )
                    order = (
                        [identity.point_name_template]
                        if identity is not None and identity.point_name_template
                        else list(dict.fromkeys(templates))
                    )
                    _rebuild_one(
                        context,
                        shadow_matrix,
                        sim,
                        name,
                        name_from,
                        order,
                        sim_notes[sim],
                        out,
                    )
    finally:
        after = _snapshot(base, skip)
        out.changes = _changes(before, after)
        chatter.unlink(missing_ok=True)
        shutil.rmtree(shadow, ignore_errors=True)


# ---------------------------------------------------------------------------
# 0.32.0, work package B3: the post and the collect of other records.

#: What sets the products folder of a post of other records apart from the
#: default one: ``post/<matrix>@<label>/`` beside ``post/<matrix>/``.
APART_MARK = "@"

#: The label of the products folder of ``post --from-sims``: ``post/<matrix>@sims/``.
FROM_SIMS_LABEL = "sims"

#: The note every record assembled from the simulation folders carries in its
#: ``warnings``, which the post writes into its log beside the point.
ASSEMBLED_NOTE = (
    "assembled from the simulation folder by pyfs-matrix post --from-sims: no run "
    "record and no script was compared, so the matrix row, its reference and its "
    "setup state what the point was asked, and its exports what it reported"
)

#: The two angles a loads export reports, by the sweep axis that names them.
_REPORTED_ANGLES = ("alpha", "beta")

#: Half the last printed digit of an angle in a loads export (three decimals).
_ANGLE_TOLERANCE_DEG = 5e-4 + 1e-9

#: The folders under a simulation folder that hold no export of a point: the
#: archives, the scripts and the staged link to the input library.
_NOT_EXPORT_FOLDERS = frozenset({"archive", "scripts", "inputs"})

#: The column of a plots export that counts the solver's time steps.
_CLOCK_COLUMN = "Time-step"


class ManifestWorkspace(CampaignWorkspace):
    """A workspace whose run records are not runs.json, and whose products stand apart.

    Built by :func:`manifest_workspace` for a named manifest, which it reads
    and whose three writers (``append_record``, ``complete_submitted_record``,
    ``supersede_records``) it writes under that manifest's own lock, and by
    :func:`from_sims_workspace` for records assembled in memory, which no
    writer may write. Either way the products and the post's reports land in
    ``post/<matrix>@<label>/`` (:meth:`products_dir`, :meth:`reports_root`),
    so the default products are never overwritten and the two posts can be
    compared.

    Parameters
    ----------
    root : str or Path
        The workspace root.
    label : str
        What follows :data:`APART_MARK` in the products folder's name.
    manifest : Path, optional
        The named manifest, a file directly in ``root``.
    assembled : sequence of RunRecord, optional
        Records assembled in memory; given, no manifest is read or written.
    refusals : mapping of str to str, optional
        What could not be assembled, by where it is, with the reason. Each is
        warned once, at the first :meth:`read_manifest`, so the post that reads
        the records writes it into its log.
    """

    def __init__(
        self,
        root: str | Path,
        *,
        label: str,
        manifest: Path | None = None,
        assembled: Sequence[RunRecord] | None = None,
        refusals: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(root)
        self.label = label
        self._manifest = None if manifest is None else self.root / Path(manifest).name
        self._assembled = None if assembled is None else list(assembled)
        self.refusals = dict(refusals or {})
        self._announced = False

    @property
    def manifest_path(self) -> Path:
        """The named manifest; for assembled records, the ``sims/`` folder they came from."""
        if self._manifest is not None:
            return self._manifest
        return self.root / "sims"

    @property
    def assembled(self) -> list[RunRecord] | None:
        """The records assembled in memory, without announcing a refusal; None for a manifest."""
        return None if self._assembled is None else list(self._assembled)

    def products_dir(self, matrix_stem: str | None) -> Path:
        """Where these records' products land: ``post/<matrix>@<label>/``."""
        return self.root / "post" / f"{matrix_stem or 'products'}{APART_MARK}{self.label}"

    def reports_root(self, matrix_stem: str | None) -> Path:
        """Keep the post's measurement reports inside the apart folder, never ``reports/``."""
        return self.products_dir(matrix_stem)

    def read_raw_manifest(self) -> list[dict]:
        """Read the named manifest as written, or give each assembled record as JSON."""
        if self._assembled is None:
            return super().read_raw_manifest()
        return [record.model_dump(mode="json") for record in self._assembled]

    def read_manifest(self) -> list[RunRecord]:
        """Read the named manifest, or give the assembled records, warning each refusal once."""
        if self._assembled is None:
            return super().read_manifest()
        if not self._announced:
            self._announced = True
            for where, reason in self.refusals.items():
                warn(
                    f"{where}: the record was refused, and nothing was assumed in its place: "
                    f"{reason}",
                    PyflightstreamWarning,
                    stacklevel=2,
                )
        return list(self._assembled)

    def read_additional(self) -> list[AdditionalRecord]:
        """Read the additional post's extractions; none belongs to assembled records."""
        if self._assembled is None:
            return super().read_additional()
        return []

    def _refuse_a_write(self) -> None:
        if self._assembled is not None:
            raise WorkspaceError(
                "records assembled from the simulation folders by from_sims_workspace are "
                f"never written: they live in memory for one post of {self.root}"
            )

    def append_record(self, record: RunRecord) -> None:
        """Append to the named manifest; refused for assembled records."""
        self._refuse_a_write()
        super().append_record(record)

    def complete_submitted_record(self, record: RunRecord) -> None:
        """Complete a record of the named manifest; refused for assembled records."""
        self._refuse_a_write()
        super().complete_submitted_record(record)

    def supersede_records(self, *args: Any, **kwargs: Any) -> Path | None:
        """Supersede records of the named manifest; refused for assembled records."""
        self._refuse_a_write()
        return super().supersede_records(*args, **kwargs)


def manifest_workspace(root: str | Path, runs: str | None = None) -> CampaignWorkspace:
    """Return the workspace ``post --runs NAME`` and ``collect --runs NAME`` read.

    Parameters
    ----------
    root : str or Path
        The workspace root.
    runs : str, optional
        The manifest's file name, as :func:`resolve_manifest` takes it. None,
        or ``runs.json``, is the default workspace, unchanged.

    Returns
    -------
    CampaignWorkspace
        The plain workspace for runs.json; otherwise a
        :class:`ManifestWorkspace` labeled with the manifest's stem, whose
        products land in ``post/<matrix>@<stem>/``.

    Raises
    ------
    RunsManifestError
        For a name :func:`resolve_manifest` refuses, for a manifest that is not
        in the root, and for ``sims.json``, whose folder would be the one of
        ``post --from-sims``.
    """
    path = resolve_manifest(root, runs)
    if path == resolve_manifest(root):
        return CampaignWorkspace(root)
    if path.stem == FROM_SIMS_LABEL:
        raise RunsManifestError(
            f"the manifest name {runs!r} would post into post/<matrix>{APART_MARK}"
            f"{FROM_SIMS_LABEL}/, the folder of the from_sims (CLI: --from-sims) post, whose "
            "records from_sims_workspace assembles; rename the manifest"
        )
    if not path.is_file():
        raise RunsManifestError(
            f"the manifest {path.name} is not in the workspace root {Path(root)}; name a "
            "manifest that is there (a named manifest is never read as an empty one)"
        )
    return ManifestWorkspace(root, label=path.stem, manifest=path)


def from_sims_workspace(
    root: str | Path, matrix_stem: str, *, steps_per_revolution: float | None = None
) -> ManifestWorkspace:
    """Return the workspace ``post MATRIX --from-sims`` reads: records assembled in memory.

    See :func:`assemble_records` for what is assembled and what is refused.
    The products land in ``post/<matrix>@sims/``.
    """
    assembled, refusals = assemble_records(
        root, matrix_stem, steps_per_revolution=steps_per_revolution
    )
    return ManifestWorkspace(root, label=FROM_SIMS_LABEL, assembled=assembled, refusals=refusals)


def assemble_records(
    root: str | Path, matrix_stem: str, *, steps_per_revolution: float | None = None
) -> tuple[list[RunRecord], dict[str, str]]:
    """Assemble in memory the run records of a matrix from its simulation folders.

    For points run outside this package there is no runs.json and no script
    to compare, so a record is assembled from what the workspace states: the
    matrix row (its sweep, its flight condition, its pproc, its window), the
    reference and the setup it names, and each point's exports under
    ``sims/sim_<POL>/``. One point is one loads export (a ``.txt`` no longer
    export suffix claims), anywhere under the simulation folder but its
    ``archive``, ``scripts`` and ``inputs`` folders; the point's other exports
    are the files beside it named its stem plus the suffix of another export
    kind (:data:`pyflightstream.cases.EXPORT_KINDS`). Its name is its
    ``DP-<name>`` folder's, else the export's stem. Its status is the one the
    collect's assessor gives the exports.

    What a record would carry and cannot be recovered is REFUSED by name,
    never guessed, and that point (or that row) is left out:

    * the aliases and the reference block, when the row's reference does not
      resolve;
    * the flight condition, when the row and its setup's pins do not resolve;
    * the point of the sweep, when the angles the export reports are no value
      of the row's sweep, or when the row sweeps anything but an angle over
      more than one value;
    * the averaging window of a point with a time history, when the row states
      neither ``LAST_REVS_AVG`` nor ``LAST_ITERS_AVG``;
    * the steps per revolution, when the window is in revolutions and
      ``steps_per_revolution`` does not state them.

    A record assembled here carries no rotor block, so the rotor tables and the
    per-rotor reductions of such a point are the post's own named skips.

    Parameters
    ----------
    root : str or Path
        The workspace root.
    matrix_stem : str
        The matrix, found at the root or under ``inputs/matrices/``.
    steps_per_revolution : float, optional
        The solver steps of one revolution, for a window in revolutions.

    Returns
    -------
    tuple
        The assembled records, and each refusal by where it is
        (``sims/sim_<POL>`` or the export's path) with its reason.

    Raises
    ------
    WorkspaceError
        When the matrix is in neither home, or ``steps_per_revolution`` is not
        a positive number.
    """
    import pyflightstream

    workspace = CampaignWorkspace(root)
    if steps_per_revolution is not None and not steps_per_revolution > 0:
        raise WorkspaceError(
            "steps_per_revolution (CLI: --steps-per-revolution) "
            f"{steps_per_revolution:g} is not a positive number of solver steps"
        )
    matrix = _the_matrix(workspace.root, matrix_stem)
    assembled: list[RunRecord] = []
    refusals: dict[str, str] = {}
    for row in read_matrix(matrix, active_only=False):
        sim_dir = workspace.root / "sims" / f"sim_{row.pol}"
        if not sim_dir.is_dir():
            continue
        where = f"sims/sim_{row.pol}"
        try:
            reference, pins, origin = _sims_row_inputs(workspace, row)
        except (PyflightstreamError, OSError, ValueError) as error:
            refusals[where] = str(error)
            continue
        by_point: dict[str, list[tuple[str, RunRecord]]] = {}
        for loads in _loads_exports(sim_dir):
            export = f"{where}/{loads.relative_to(sim_dir).as_posix()}"
            try:
                record = _assembled_record(
                    workspace,
                    row,
                    matrix_stem,
                    sim_dir,
                    loads,
                    reference=reference,
                    pins=pins,
                    origin=origin,
                    steps_per_revolution=steps_per_revolution,
                    version=pyflightstream.__version__,
                )
            except (PyflightstreamError, OSError, ValueError) as error:
                refusals[export] = str(error)
                continue
            by_point.setdefault(repr(sorted(record.point.items())), []).append((export, record))
        for pairs in by_point.values():
            if len(pairs) == 1:
                assembled.append(pairs[0][1])
                continue
            # TWO EXPORTS AT ONE POINT COST BOTH, never a choice between them.
            names = ", ".join(export for export, _ in pairs)
            for export, record in pairs:
                refusals[export] = (
                    f"the point of the sweep: {names} report one point of row POL {row.pol}'s "
                    f"sweep, {dict(record.point)}; a point is one export, so none is chosen"
                )
        if not by_point and not any(name.startswith(f"{where}/") for name in refusals):
            refusals[where] = (
                "the simulation folder holds no loads export, so no point of it can be assembled"
            )
    return assembled, refusals


def _the_matrix(root: Path, matrix_stem: str) -> Path:
    """Return the matrix file of ``matrix_stem``, by the workspace's two-homes rule.

    The rule is :func:`pyflightstream.workspace.find_matrix`'s, which refuses a
    stem in both homes with different bytes; only the absence is named here.
    """
    stem = Path(matrix_stem).stem
    found = find_matrix(root, stem)
    if found is None:
        raise WorkspaceError(
            f"the matrix {stem!r} is neither at the root of {root} nor under "
            "inputs/matrices/; from_sims_workspace reads its rows to assemble the records"
        )
    return found


def _sims_row_inputs(
    workspace: CampaignWorkspace, row: MatrixRow
) -> tuple[ReferenceArtifact, dict[str, float], str]:
    """Return the reference, the setup's flight-condition pins and their origin, for a row."""
    try:
        reference = workspace.resolve_reference(row.ref_code)
    except (PyflightstreamError, OSError, ValueError) as error:
        raise WorkspaceError(
            f"the aliases and the reference block: row POL {row.pol} names the reference "
            f"{row.ref_code!r}, which does not resolve ({error}); a record carries both "
            "from it, so nothing is assumed in their place"
        ) from error
    origin = condition_defaults_origin(row.set_code)
    if row.set_code in UNSTATED_CELLS:
        return reference, {}, origin
    try:
        table = workspace.resolve_setup(row.set_code).settings.get("flight_condition") or {}
        if not isinstance(table, Mapping) or any(
            isinstance(value, bool) or not isinstance(value, int | float)
            for value in table.values()
        ):
            raise WorkspaceError(
                f"{origin} states [flight_condition] as {table!r}, and its pins are numbers"
            )
        pins = canonical_condition_defaults(
            {str(key): float(value) for key, value in table.items()}, origin
        )
    except (PyflightstreamError, OSError, ValueError) as error:
        raise WorkspaceError(
            f"the flight condition: row POL {row.pol} names the setup {row.set_code!r}, whose "
            f"pins cannot be read ({error})"
        ) from error
    return reference, pins, origin


def _loads_exports(sim_dir: Path) -> Iterator[Path]:
    """Every loads export under a simulation folder, in path order."""
    found: list[Path] = []
    for folder, children, files in os.walk(sim_dir):
        children[:] = sorted(
            name
            for name in children
            if name.casefold() not in _NOT_EXPORT_FOLDERS
            and not os.path.isjunction(os.path.join(folder, name))
            and not os.path.islink(os.path.join(folder, name))
        )
        for name in files:
            if classify_outputs([name]) == {"loads": name}:
                found.append(Path(folder) / name)
    yield from sorted(found)


def _companions(loads: Path) -> list[Path]:
    """Return the exports beside a loads export, each its stem plus an export kind's suffix.

    EXACTLY the stem and a suffix, never a prefix: ``<stem>.dat`` is the point's
    surface export, and ``<stem>_b_log.txt`` is the log of another point whose
    stem merely begins with this one's.
    """
    names = {f"{loads.stem}{suffix}" for kind, suffix, _, _ in EXPORT_KINDS if kind != "loads"}
    return sorted(loads.parent / name for name in names if (loads.parent / name).is_file())


def _swept_name(row: MatrixRow) -> str:
    """Name the row's sweep as the package does: each swept field ``<code>+sweep``."""
    axes = _REPORTED_ANGLES if row.sweep.type == "alpha_beta" else (row.sweep.type,)
    codes = []
    for axis in axes:
        field = POINT_NAME_FIELDS.get(POINT_AXIS_KEYS.get(axis, axis))
        codes.append(f"{field.code if field is not None else axis}{SWEEP_NAME_VALUE}")
    return "".join(codes)


def _the_point(row: MatrixRow, export: str, alpha: float, beta: float) -> dict[str, float]:
    """Return the point of the row's sweep an export reports, or refuse naming why."""
    points = [dict(point) for point in row.sweep.points()]
    reported = {"alpha": alpha, "beta": beta}
    fitting = [
        point
        for point in points
        if all(
            abs(float(point[axis]) - reported[axis]) <= _ANGLE_TOLERANCE_DEG
            for axis in _REPORTED_ANGLES
            if axis in point
        )
    ]
    if len(fitting) == 1:
        return fitting[0]
    values = ", ".join(f"{value}" for value in row.sweep.values)
    if not fitting:
        raise WorkspaceError(
            f"the point of the sweep: {export} reports alpha {alpha:g} and beta {beta:g}, "
            f"and no point of row POL {row.pol}'s sweep ({row.sweep.type}: {values}) is at "
            "those angles, so the point it was asked as cannot be named"
        )
    raise WorkspaceError(
        f"the point of the sweep: row POL {row.pol} sweeps {row.sweep.type} over {values}, "
        f"{len(fitting)} of its points are at the angles {export} reports, and the export "
        "does not state its swept value; split the row, one value each"
    )


def _assembled_record(
    workspace: CampaignWorkspace,
    row: MatrixRow,
    matrix_stem: str,
    sim_dir: Path,
    loads: Path,
    *,
    reference: ReferenceArtifact,
    pins: Mapping[str, float],
    origin: str,
    steps_per_revolution: float | None,
    version: str,
) -> RunRecord:
    """Assemble the record of one point from its loads export, or refuse it by name."""
    from pyflightstream.run.collect import assessment_of_collected

    export = f"sims/sim_{row.pol}/{loads.relative_to(sim_dir).as_posix()}"
    try:
        report = parse_loads(loads.read_text(encoding="utf-8"))
    except (PyflightstreamError, ValueError) as error:
        raise WorkspaceError(
            f"the loads export: {export} cannot be read as one ({error})"
        ) from error
    point = _the_point(row, export, report.angle_of_attack_deg, report.sideslip_deg)
    stem = datapoint_name_of(loads.parent.name)
    name = stem if stem is not None else PointName(loads.stem)
    cell = dict(row.flight_condition)
    swept = POINT_AXIS_KEYS.get(row.sweep.type)
    if swept is not None and swept not in ATTITUDE_KEYS and row.sweep.type in point:
        cell[swept] = float(point[row.sweep.type])
    try:
        resolved = resolve_flight_condition(
            cell,
            pol=row.pol,
            reference_length_m=reference.chord_m,
            defaults=pins or None,
            defaults_origin=origin,
        )
    except PyflightstreamError as error:
        raise WorkspaceError(
            f"the flight condition of row POL {row.pol} cannot be resolved from the row and "
            f"its setup ({error})"
        ) from error
    companions = _companions(loads)
    moment = reference.moment_point
    record = RunRecord(
        run_id=f"{workspace.root.name}/sim_{row.pol}/{name}",
        sim_id=row.pol,
        point=point,
        point_name=str(name),
        sweep_name=_swept_name(row),
        matrix_stem=matrix_stem,
        fs_version_requested=row.fs_build if row.fs_build not in UNSTATED_CELLS else "unstated",
        velocity_requested_m_s=resolved.velocity_m_per_s,
        flight_condition=cell,
        flight_condition_defaults=dict(resolved.defaulted),
        flight_condition_defaults_from=origin if resolved.defaulted else "",
        density_kg_m3=resolved.density_kg_m3,
        temperature_k=resolved.temperature_k,
        viscosity_pa_s=resolved.viscosity_pa_s,
        density_source=resolved.density_source,
        reference_length_m=reference.chord_m,
        package_version=version,
        script_sha256="",
        raw_flag=False,
        pproc=row.pproc_code if row.pproc_code not in UNSTATED_CELLS else None,
        recipe=row.workflow,
        description=row.description,
        mach=resolved.mach,
        reference={
            "SREF": reference.area_m2,
            "CREF": reference.chord_m,
            "BREF": reference.span_m,
            "XMOM": moment.x_m,
            "YMOM": moment.y_m,
            "ZMOM": moment.z_m,
        },
        aliases={alias: list(members) for alias, members in reference.aliases.items()},
        motions=[dict(motion) for motion in row.motions],
        reductions=_reductions(row, export, companions, steps_per_revolution),
        outputs=[path.relative_to(sim_dir).as_posix() for path in (loads, *companions)],
        status=RunStatus.SUBMITTED,
        warnings=[ASSEMBLED_NOTE],
    )
    try:
        judged = assessment_of_collected(record, sim_dir)
    except (PyflightstreamError, OSError, ValueError) as error:
        raise WorkspaceError(
            f"the status: the collect's assessor cannot judge {export} ({error})"
        ) from error
    return record.model_copy(
        update={
            "status": judged.status,
            "iterations": judged.iterations,
            "residual": judged.residual,
            "error": judged.error,
            "fs_version_reported": judged.fs_version_reported,
            "fs_build": judged.fs_build,
            "log_file_used": judged.log_file_used,
        }
    )


def _reductions(
    row: MatrixRow,
    export: str,
    companions: Sequence[Path],
    steps_per_revolution: float | None,
) -> dict[str, object] | None:
    """Return the reductions plan of a point with a time history, cut from the row."""
    plots = next((path for path in companions if classify_outputs([path.name]).get("plots")), None)
    stated = stated_key(row.variables)
    if plots is None:
        if stated is None:
            return None
        raise WorkspaceError(
            f"the time history: row POL {row.pol} states {stated[0]} = {stated[1]:g}, and "
            f"{export} has no plots export beside it ({Path(export).stem}_plots.txt) to "
            "average over"
        )
    if stated is None:
        raise WorkspaceError(
            f"the averaging window: {export} has a time history, and row POL {row.pol} states "
            "neither LAST_REVS_AVG nor LAST_ITERS_AVG (or states both); the window a record "
            "carries is never assumed, so state one in the row"
        )
    if stated[0] == LAST_REVS_AVG and steps_per_revolution is None:
        raise WorkspaceError(
            f"the steps per revolution: row POL {row.pol} states LAST_REVS_AVG = "
            f"{stated[1]:g}, a window counted in revolutions, and nothing states how many "
            "solver steps one revolution of this run is; pass steps_per_revolution "
            "(CLI: --steps-per-revolution)"
        )
    try:
        history = parse_unsteady_plots(plots.read_text(encoding="utf-8"))
        clock = history.series(_CLOCK_COLUMN)
    except (PyflightstreamError, ValueError) as error:
        raise WorkspaceError(
            f"the time history: {plots.name} cannot be read for its {_CLOCK_COLUMN} column "
            f"({error})"
        ) from error
    if not len(clock):
        raise WorkspaceError(f"the time history: {plots.name} holds no time step")
    plan: dict[str, object] = {
        "time_iterations": int(round(float(max(clock)))),
        "steps_per_revolution": steps_per_revolution,
        "blades": None,
    }
    cut = replan(plan, row.variables)
    if cut is None:
        raise WorkspaceError(
            f"the averaging window: row POL {row.pol} states {stated[0]} = {stated[1]:g}, "
            f"and no window of the {plan['time_iterations']} steps of {plots.name} can be "
            "cut from it"
        )
    return cut


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
