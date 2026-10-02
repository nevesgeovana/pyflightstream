"""Copy and move the points of a batch from its job folder to their simulations (0.35.0).

Pipeline role: below :mod:`pyflightstream.run._batch_collect`, which decides
WHEN a point is copied (it settled while the job runs) and when the rest of a
simulation is moved (the job ended); this module only does it, file by file,
and reports what it did.

Two rules carry the whole module (FR-367, recorded 2026-10-02):

- **A copy never writes under the batch folder.** :func:`copy_point` reads
  ``sims/batch/<label>/sim_<id>/`` and writes only under ``sims/sim_<id>/``;
  the solver may still be writing next to what it reads.
- **A link is never crossed.** The ``inputs`` entry of a simulation is a
  directory link (a junction on Windows) to the workspace's staged inputs; a
  copy through it would duplicate every geometry, and a removal through it
  would delete them. :func:`relink_inputs` re-makes it as a link to the same
  target with the workspace's own link primitives, and :func:`move_sim`
  removes the batch's link as a link.

The move reconciles by content (section 8, reading 2, of IMPL-0350): the
batch folder at the job's end is the truth, so a file whose copy differs in
size or sha256 replaces the copy and is named in the report, an equal one is
dropped from the batch, and a file only in the simulation (the sliced log) is
left as it is.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from pyflightstream._digest import file_sha256
from pyflightstream.workspace import SIM_DATAPOINTS_DIR, WorkspaceError
from pyflightstream.workspace._links import _is_link, _make_dir_link, _remove_link

__all__ = ["RelocationReport", "copy_point", "move_sim", "relink_inputs"]

#: The simulation entry that is a link to the workspace's inputs, never copied through.
INPUTS_LINK = "inputs"


@dataclass(frozen=True)
class RelocationReport:
    """What one copy or move did, as paths relative to the simulation folder.

    Attributes
    ----------
    copied : tuple of str
        Files that did not exist in the simulation folder and now do.
    replaced : tuple of str
        Files whose copy differed (size or sha256) and were replaced by the
        batch's file. A move names them, because a point already completed
        from the earlier copy was judged on bytes that are no longer there.
    kept : tuple of str
        Files already present with the same bytes, left as they were.
    """

    copied: tuple[str, ...] = ()
    replaced: tuple[str, ...] = ()
    kept: tuple[str, ...] = ()


@dataclass
class _Tally:
    """The report while it is being built."""

    copied: list[str] = field(default_factory=list)
    replaced: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)

    def report(self) -> RelocationReport:
        return RelocationReport(
            copied=tuple(sorted(self.copied)),
            replaced=tuple(sorted(self.replaced)),
            kept=tuple(sorted(self.kept)),
        )


def _same_bytes(left: Path, right: Path) -> bool:
    """Say whether two files hold the same bytes: size first, then sha256."""
    if left.stat().st_size != right.stat().st_size:
        return False
    return file_sha256(left) == file_sha256(right)


def _relink(source: Path, target: Path) -> None:
    """Make ``target`` a link to what the link ``source`` points at; refuse a real folder.

    An EMPTY real folder is replaced, as staging replaces it: the plan allocates
    ``sims/sim_<id>/inputs`` empty before any run, so a batched sim brought back
    always meets one. A folder holding anything is refused, never overwritten.
    """
    destination = source.resolve()
    if _is_link(target):
        if target.resolve() == destination:
            return
        _remove_link(target)
    elif target.is_dir() and not any(target.iterdir()):
        target.rmdir()
    elif target.exists():
        raise WorkspaceError(
            f"{target} is a real folder where the batch holds a link to {destination}. A link is "
            "never copied through, and a folder is not replaced by one here; move it aside and "
            "collect again."
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    _make_dir_link(destination, target)


def _copy_tree(source: Path, target: Path, root: Path, tally: _Tally) -> None:
    """Copy ``source`` into ``target`` file by file, re-making links, writing only under target."""
    if _is_link(source):
        _relink(source, target)
        return
    if source.is_dir():
        for entry in sorted(source.iterdir()):
            _copy_tree(entry, target / entry.name, root, tally)
        return
    name = target.relative_to(root).as_posix()
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        tally.copied.append(name)
    elif _same_bytes(source, target):
        tally.kept.append(name)
    else:
        shutil.copy2(source, target)
        tally.replaced.append(name)


def copy_point(batch_sim: Path, sim: Path, datapoint: str) -> RelocationReport:
    """Copy one settled point of a running batch into its simulation folder.

    Copied: the point's datapoint folder, and every entry of the batch's
    simulation folder other than ``datapoints/`` and ``inputs`` (the
    per-point scripts and the ``profiles/`` probe file among them). NOTHING
    under ``batch_sim`` is written, renamed or removed. The ``inputs`` link is
    not touched here; :func:`relink_inputs` re-makes it.

    Parameters
    ----------
    batch_sim : Path
        ``sims/batch/<label>/sim_<id>/``.
    sim : Path
        ``sims/sim_<id>/``, created when missing.
    datapoint : str
        The point's datapoint folder name, ``DP-<tag>``.

    Returns
    -------
    RelocationReport
        The files copied, replaced and kept, relative to ``sim``.
    """
    tally = _Tally()
    sim.mkdir(parents=True, exist_ok=True)
    for entry in sorted(batch_sim.iterdir()):
        if entry.name in (SIM_DATAPOINTS_DIR, INPUTS_LINK):
            continue
        _copy_tree(entry, sim / entry.name, sim, tally)
    point = batch_sim / SIM_DATAPOINTS_DIR / datapoint
    if point.is_dir():
        _copy_tree(point, sim / SIM_DATAPOINTS_DIR / datapoint, sim, tally)
    return tally.report()


def relink_inputs(batch_sim: Path, sim: Path) -> None:
    """Make ``sim/inputs`` the same link ``batch_sim/inputs`` is, never a copy through it.

    Parameters
    ----------
    batch_sim : Path
        ``sims/batch/<label>/sim_<id>/``; nothing is done when it holds no
        ``inputs`` link.
    sim : Path
        ``sims/sim_<id>/``.

    Raises
    ------
    WorkspaceError
        When ``sim/inputs`` is a real folder rather than a link.
    """
    source = batch_sim / INPUTS_LINK
    if _is_link(source):
        _relink(source, sim / INPUTS_LINK)


def _move_tree(source: Path, target: Path, root: Path, tally: _Tally) -> None:
    """Move ``source`` into ``target`` file by file; links re-made, then removed as links."""
    if _is_link(source):
        _relink(source, target)
        _remove_link(source)
        return
    if source.is_dir():
        for entry in sorted(source.iterdir()):
            _move_tree(entry, target / entry.name, root, tally)
        if not any(source.iterdir()):
            source.rmdir()
        return
    name = target.relative_to(root).as_posix()
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        tally.copied.append(name)
    elif _same_bytes(source, target):
        source.unlink()
        tally.kept.append(name)
    else:
        target.unlink()
        shutil.move(str(source), str(target))
        tally.replaced.append(name)


def move_sim(batch_sim: Path, sim: Path) -> RelocationReport:
    """Move everything left of an ended batch's simulation into its simulation folder.

    Every file under ``batch_sim`` lands under ``sim``: a missing one is
    moved, one with the same bytes is dropped from the batch, one that
    differs replaces the copy (and is named in ``replaced``). The ``inputs``
    link is re-made in ``sim`` and removed from the batch as a link. The
    batch's ``sim_<id>`` folder is removed once empty; the job's own files,
    one level up, are not touched.

    Parameters
    ----------
    batch_sim : Path
        ``sims/batch/<label>/sim_<id>/``.
    sim : Path
        ``sims/sim_<id>/``, created when missing.

    Returns
    -------
    RelocationReport
        The files moved (``copied``), replaced and kept, relative to ``sim``.
    """
    tally = _Tally()
    sim.mkdir(parents=True, exist_ok=True)
    if batch_sim.is_dir():
        _move_tree(batch_sim, sim, sim, tally)
    return tally.report()
