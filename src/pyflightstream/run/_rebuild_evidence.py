"""What a rebuild reads: the known runs, the workspace's state and the scripts compared.

Every run the workspace or its archive has a record of (:func:`_known_runs`),
the simulations on disk, a snapshot of the workspace taken before the rebuild
and compared after it, so a write meanwhile refuses the apply, the collect
made read-only for the length of one call (:func:`collect_without_writing`),
and the comparison of the script a simulation ran with the script the row
renders today, with the class of every difference named (:func:`_drift`).
Nothing here writes into the workspace.

The public names are re-exported, unchanged, by :mod:`pyflightstream.run.records`,
their path of 0.32.0 (AD-11, since 0.33.0).
"""

from __future__ import annotations

import contextlib
import csv
import dataclasses
import json
import os
import re
import threading
import warnings
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import pyflightstream._textio as _textio
from pyflightstream.run._record_files import _ROOT_KINDS, _relative, _root_archives
from pyflightstream.workspace._batches import batch_sim_dirs
from pyflightstream.workspace._matrix_homes import every_matrix, matrix_path
from pyflightstream.workspace._script_comparison import (
    _compare_scripts as _compare_scripts,
)
from pyflightstream.workspace._script_comparison import (
    _drift as _drift,
)
from pyflightstream.workspace._script_comparison import (
    _slashes as _slashes,
)
from pyflightstream.workspace.naming import DEFAULT_MANIFEST


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
    _textio.write_text(workspace.manifest_path, json.dumps([dict(record)], indent=2) + "\n")

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


def descriptor_folder(base: Path, sim_dir: Path, work_dir: Path, profile: Any) -> Path | None:
    """Return the folder holding the scheduler descriptor of a simulation's job, or None.

    A point run alone writes its descriptor in its own working folder. A point
    of a batch has it in the job folder, ``sims/batch/<matrix>_b<ID>/``, beside
    the batch's copy of the simulation: that point was submitted, never run
    here, and its record says so (FR-372).

    Parameters
    ----------
    base : Path
        The workspace root.
    sim_dir : Path
        ``sims/sim_<id>``.
    work_dir : Path
        The point's working folder.
    profile : object or None
        The HPC profile, whose ``descriptor_name`` names the file.

    Returns
    -------
    Path or None
        The folder with the descriptor, else None.
    """
    if profile is None:
        return None
    folders = [work_dir, *(p.parent for p in batch_sim_dirs(base).get(sim_dir.name[4:], []))]
    return next((f for f in folders if (f / profile.descriptor_name).is_file()), None)


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


def _matrices(base: Path, matrix: str | Path | None) -> list[Path]:
    """Return the matrices to rebuild from: the named revision, or every one there is.

    Both through the workspace's one lookup of a matrix (FR-310): a named
    matrix is found in either home, and the sweep reads one file per stem. A
    stem in both homes with different bytes is refused, naming both, before
    any work; until 0.32.0 the sweep left it out with a note instead.
    """
    if matrix is not None:
        return [matrix_path(base, matrix).resolve()]
    return [path.resolve() for path in every_matrix(base)]


# ---------------------------------------------------------------------------
# rebuild: the identity of a script
# ---------------------------------------------------------------------------
