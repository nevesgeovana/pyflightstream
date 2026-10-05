"""Which per-step exports a ``[[prune_step_exports]]`` table keeps and which it deletes (FR-416).

A recipe table may state ``keep_last = K`` (the last ``K`` steps of each
export are kept, the default 1 being the 0.30.0 behaviour) or
``delete_steps = [A, B]`` (the steps from ``A`` to ``B`` inclusive are
deleted, every other step kept), never both. This module holds the pieces of
that choice that carry no file system action: the check of a table's keys
and values before any file is touched, the split of one export's steps into
kept and deleted, the words the recorded call, the command-line summary and
a later post's refusal use to say what was kept, and the reader that groups
the stamped files of a simulation by folder and export.

The file deleting and the protection of a record's files stay in
``pyflightstream.workspace.storage``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

#: The keys of a ``[[prune_step_exports]]`` table (FR-416): the selection of
#: simulations of 0.30.0 and the two ways to say which steps go.
PRUNE_KEYS = ("sims", "status", "keep_last", "delete_steps")
#: A per-step export: the solver stamps ``_iteration=<step>`` before the
#: extension of every file an unsteady action exports at a step (RPT-041), the
#: pattern :func:`pyflightstream.post.series.stamped_exports` reads them by.
_STEP_EXPORT = re.compile(r"^(?P<stem>.+)_iteration=(?P<step>\d+)\.(?P<ext>txt|dat|vtk|csv)$")


def _whole(value: object) -> bool:
    """Return True for a positive integer (a boolean is not one)."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def check_prune_tables(
    path: Path, entries: Iterable[Mapping[str, Any]], error: type[Exception]
) -> None:
    """Refuse a ``[[prune_step_exports]]`` table that holds a key or value the mode does not read.

    Called with the whole recipe read and before any file is touched, so a
    misspelt key never turns into a silent default.

    Parameters
    ----------
    path : Path
        The recipe file, as the refusal names it.
    entries : iterable of mapping
        The ``[[prune_step_exports]]`` tables of the recipe.
    error : type
        The exception class to raise (the storage error).

    Raises
    ------
    StorageError
        (``error``) naming the key and the accepted ones, or the
        value and what it must be.
    """
    for spec in entries:
        unknown = sorted(set(spec).difference(PRUNE_KEYS))
        if unknown:
            raise error(
                f"{path}: [[prune_step_exports]] does not read {unknown}; "
                f"the keys it accepts are {', '.join(PRUNE_KEYS)}"
            )
        if "keep_last" in spec and "delete_steps" in spec:
            raise error(
                f"{path}: [[prune_step_exports]] states keep_last and delete_steps; "
                "state one: the last steps to keep, or the range of steps to delete"
            )
        if "keep_last" in spec and not _whole(spec["keep_last"]):
            raise error(
                f"{path}: keep_last is a positive whole number of steps, e.g. keep_last = 12"
            )
        if "delete_steps" in spec:
            span = spec["delete_steps"]
            if not (
                isinstance(span, list)
                and len(span) == 2
                and all(_whole(item) for item in span)
                and span[0] <= span[1]
            ):
                raise error(
                    f"{path}: delete_steps is two positive step numbers, first to last "
                    "inclusive, e.g. delete_steps = [5, 9]"
                )


def split_steps(spec: Mapping[str, Any], steps: Iterable[int]) -> tuple[list[int], list[int]]:
    """Split one export's step numbers into those kept and those to delete.

    Parameters
    ----------
    spec : mapping
        The ``[[prune_step_exports]]`` table; neither selection key means ``keep_last = 1``.
    steps : iterable of int
        The step numbers on disk for one export.

    Returns
    -------
    tuple of list of int
        ``(kept, doomed)``, each in ascending order. A ``keep_last`` at or above
        the number of steps, or a range with no step on disk, deletes none.
    """
    ordered = sorted(steps)
    if "delete_steps" in spec:
        first, last = spec["delete_steps"]
        doomed = [step for step in ordered if first <= step <= last]
    else:
        doomed = ordered[: max(len(ordered) - int(spec.get("keep_last", 1)), 0)]
    gone = set(doomed)
    return [step for step in ordered if step not in gone], doomed


def selection_record(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Return the selection a table stated, as the recorded step entry carries it.

    A table that states neither key records neither: the entry is the one of 0.30.0.
    """
    return {key: spec[key] for key in ("keep_last", "delete_steps") if key in spec}


def kept_phrase(selection: Mapping[str, Any], *, exclusive: bool = False) -> str:
    """Say what a recorded step kept: ``the last step of each export`` and its variants.

    Parameters
    ----------
    selection : mapping
        A recorded step entry, or a table: it is read for ``keep_last`` and ``delete_steps`` only.
    exclusive : bool, optional
        Add ``only`` to a statement of the steps kept (a refusal says nothing else remains).

    Returns
    -------
    str
        ``the last step of each export``, ``the last 12 steps of each export`` or
        ``every step outside 5 to 9 of each export``.
    """
    if "delete_steps" in selection:
        first, last = selection["delete_steps"]
        return f"every step outside {first} to {last} of each export"
    count = int(selection.get("keep_last", 1))
    kept = "the last step" if count == 1 else f"the last {count} steps"
    return f"{kept} of each export{' only' if exclusive else ''}"


def step_export_groups(
    folder: Path, files: Iterable[Path]
) -> dict[Path, dict[tuple[str, str], dict[int, Path]]]:
    """Every per-step export among a simulation's files, by its folder, then export, then step.

    An export is its stem (the ``_cp``, ``_sloads`` or ``_probes`` suffix
    included) and its extension, so the loads, the sectional loads, the probes
    and each surface of one point are separate exports, each with its own
    steps. Nothing under the simulation's ``inputs`` or ``scripts`` is read.

    Parameters
    ----------
    folder : Path
        The simulation folder.
    files : iterable of Path
        The regular files below it (the caller walks without following a link).

    Returns
    -------
    dict
        ``{folder: {(stem, extension): {step: path}}}``.
    """
    groups: dict[Path, dict[tuple[str, str], dict[int, Path]]] = {}
    for path in files:
        if path.relative_to(folder).parts[0] in ("inputs", "scripts"):
            continue
        matched = _STEP_EXPORT.match(path.name)
        if matched is None:
            continue
        export = (matched.group("stem"), matched.group("ext"))
        by_step = groups.setdefault(path.parent, {}).setdefault(export, {})
        by_step[int(matched.group("step"))] = path
    return groups
