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
import difflib
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
from pyflightstream.workspace._matrix_homes import every_matrix, matrix_path
from pyflightstream.workspace.naming import DEFAULT_MANIFEST

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
