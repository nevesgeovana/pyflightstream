"""A geometry reduced to its meshes and boundary conditions, and the warnings that ask for it.

FR-308 made ``pyfs-matrix inventory`` name the unsteady solver actions a saved
simulation carries and ``--clean`` remove them. FR-312 extends ``--clean``: every
block other than the meshes and the applied boundary conditions goes back to
the content a freshly imported file holds, where that content is measured
(:mod:`pyflightstream._fsm_fresh`), and is kept, with the reason said, where it
is not. FR-313 has ``pyfs-matrix plan`` read the geometry of every unsteady row
with the same reader and WARN, never refuse, naming each saved action and the
command that removes them.

The warning text is written here once, for the inventory and the plan both,
so the two cannot drift apart.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pyflightstream._textio as _textio
from pyflightstream._errors import InputArtifactError, PyflightstreamError, PyflightstreamWarning
from pyflightstream._errors import warn as _warn
from pyflightstream._fsm import (
    MeshReadError,
    boundary_names,
    saved_length_unit,
    saved_solver_actions,
    without_saved_solver_actions,
)
from pyflightstream._fsm_fresh import KEPT_BLOCKS, block_lines, reset_to_fresh_import

__all__ = [
    "UNSTEADY_WORKFLOWS",
    "CleanedGeometry",
    "clean_saved_actions",
    "saved_action_warning",
    "warn_saved_actions_of_unsteady_rows",
]

#: The run types whose rows the plan reads the geometry of (FR-313 R1): the ones
#: with a time loop, and so with unsteady solver actions to run.
UNSTEADY_WORKFLOWS: tuple[str, ...] = ("unsteady", "unsteady_rotor")

#: The suffix of a saved simulation; a raw mesh carries no action (FR-313 R5).
SAVED_SUFFIX = ".fsm"


@dataclass(frozen=True)
class CleanedGeometry:
    """What :func:`clean_saved_actions` changed in a saved simulation.

    Attributes
    ----------
    actions : tuple of (str, str, str)
        Each removed action's name, command or script file, and type.
    backup : Path or None
        The copy of the file as it was, None when nothing was changed.
    blocks_reset : tuple of str
        The blocks put back to their fresh-import content (FR-312), in file
        order; empty when none was measured for the file or none differed.
    note : str or None
        Why no block was reset, when the file's build and unit have no
        measured fresh import; None otherwise.
    """

    actions: tuple[tuple[str, str, str], ...]
    backup: Path | None
    blocks_reset: tuple[str, ...] = ()
    note: str | None = None


def _kept(text: str) -> dict[str, tuple[str, ...]]:
    """Return the blocks a clean never changes, by name: meshes and boundary conditions."""
    return {name: lines for name, lines in block_lines(text).items() if name in KEPT_BLOCKS}


def clean_saved_actions(geometry: str | Path, *, stamp: str) -> CleanedGeometry:
    """Reduce a saved simulation to its meshes and applied boundary conditions (FR-308, FR-312).

    The saved unsteady solver actions are removed (FR-308), and every block
    :data:`pyflightstream._fsm_fresh.FRESH_IMPORT` measures for the file's
    build and length unit is put back to its fresh-import content (FR-312);
    the blocks of :data:`pyflightstream._fsm_fresh.KEPT_BLOCKS` never change.
    The file as it was is copied to ``<name>.bak-<stamp>`` beside it first,
    the new text replaces it through a temporary file, and it is read again:
    its boundary names and every kept block must be as before and its action
    records must read as none, or the copy is put back and the call refused.
    A file already clean is not written.

    Parameters
    ----------
    geometry : str or Path
        A saved simulation.
    stamp : str
        The suffix of the backup's name, the caller's timestamp.

    Returns
    -------
    CleanedGeometry
        The actions removed, the blocks reset, the note when no block was
        measured, and the backup, which is None when nothing changed.

    Raises
    ------
    InputArtifactError
        A file that cannot be read, that has no closed SOLVER block, whose
        actions do not hold their shape, whose measured blocks are missing,
        or which did not read back as it should.
    """
    path = Path(geometry)
    try:
        text = path.read_bytes().decode("latin-1")
        cleaned, actions = without_saved_solver_actions(text, path.name)
        try:
            unit = saved_length_unit(path)
        except MeshReadError:
            unit = None
        reset = reset_to_fresh_import(cleaned, unit, path.name)
        before = (boundary_names(path), _kept(text))
    except (OSError, PyflightstreamError) as error:
        raise InputArtifactError(f"{path.name}: {error}") from error
    if reset.text == text:
        return CleanedGeometry(actions=(), backup=None, note=reset.note)
    backup = path.with_name(f"{path.name}.bak-{stamp}")
    shutil.copy2(path, backup)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    _textio.write_text(temporary, reset.text, encoding="latin-1")
    os.replace(temporary, path)
    after: object
    try:
        after = (boundary_names(path), _kept(path.read_bytes().decode("latin-1")))
        left = saved_solver_actions(path)
    except (OSError, PyflightstreamError) as error:
        after, left = f"unreadable: {error}", None
    if after != before or left != ():
        shutil.copy2(backup, path)
        raise InputArtifactError(
            f"{path.name}: after the clean its boundary names, its meshes and boundary "
            "conditions, or its action records did not read back as they should, so the "
            f"file was put back from {backup.name}."
        )
    return CleanedGeometry(
        actions=actions, backup=backup, blocks_reset=reset.blocks, note=reset.note
    )


def saved_action_warning(geometry: Path, shown: str, rows: Iterable[str] = ()) -> str | None:
    """Return the warning a saved simulation's actions call for, or None when it carries none.

    One text for the inventory (FR-308) and the plan (FR-313): the file,
    the rows of the plan that open it, each saved action by its name, its
    type and its command or script file, and the command that removes them.
    A file whose action records cannot be read is warned about as unreadable,
    naming the file (FR-313 R3).

    Parameters
    ----------
    geometry : Path
        The saved simulation read.
    shown : str
        The file as the ``--clean`` command should spell it.
    rows : iterable of str
        The rows (POL) of a plan that open it; none for the inventory.
    """
    named = sorted(set(rows))
    whose = f"row(s) {', '.join(named)}: " if named else ""
    try:
        actions = saved_solver_actions(geometry)
    except (OSError, MeshReadError) as error:
        return (
            f"{whose}the geometry {geometry.name} cannot be read for saved unsteady solver "
            f"actions ({error}); what the solver will run from it is not known."
        )
    if not actions:
        return None
    listed = "; ".join(f"{name} [{kind}] {command.strip()}" for name, command, kind in actions)
    return (
        f"{whose}{geometry.name} carries {len(actions)} unsteady solver action(s) saved in "
        f"the file: {listed}. A saved action keeps its name when the script creates one of "
        "the same name, and the solver runs the saved command (an interpreter path of "
        "another machine aborts the unsteady run when it fires). Remove them with: "
        f"pyfs-matrix inventory {shown} --clean"
    )


def warn_saved_actions_of_unsteady_rows(cases: Iterable[object], workflow_key: str) -> None:
    """Warn, never refuse, for each unsteady row's geometry that carries saved actions (FR-313).

    Every row whose run type (its ``workflow_key`` variable) is one of
    :data:`UNSTEADY_WORKFLOWS`, a continuation included, has its geometry read
    once per file; a file is named once, with every row that opens it. A raw
    mesh and a row naming no geometry are not read. Called from the plan, so
    the warnings join its warnings block; nothing the plan writes or returns
    depends on them.
    """
    rows_of: dict[Path, list[str]] = {}
    for case in cases:
        variables = getattr(case, "variables", {}) or {}
        geometry = getattr(case, "geometry", None)
        if str(variables.get(workflow_key, "")).strip() not in UNSTEADY_WORKFLOWS:
            continue
        if not geometry or Path(str(geometry)).suffix.lower() != SAVED_SUFFIX:
            continue
        rows_of.setdefault(Path(str(geometry)), []).append(str(getattr(case, "sim_id", "")))
    for geometry, rows in rows_of.items():
        text = saved_action_warning(geometry, str(geometry), rows)
        if text is not None:
            _warn(text, PyflightstreamWarning, stacklevel=3)
