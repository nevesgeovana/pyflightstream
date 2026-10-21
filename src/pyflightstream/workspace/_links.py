"""The directory link primitives the workspace layer stages and archives with.

Pipeline role: below :mod:`pyflightstream.workspace`, private to it and to
its sibling :mod:`pyflightstream.workspace.storage`. It imports nothing
from this package, which is what lets a public sibling reach it without
crossing a layer boundary for an underscore-private name out of another
PUBLIC module (`tests/tier1_offline/test_digest.py`'s layer-boundary
guard): a private name out of a private module is that module's own
business.

Workspace creation and storage share these link operations through this
module. The workspace package imports the helpers under their private names.
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
import zipfile
from collections.abc import Sequence
from pathlib import Path


def _copy_inputs_problem(inputs: Path, origins: Sequence[Path], reason: str | None) -> str | None:
    """Refuse copying through links before any source is written (PFS-2095.062)."""
    if origins and (_is_link(inputs) or not inputs.is_dir()):
        return (
            f"cannot stage into {inputs}: {reason}. Copying through a link would "
            "write the sources into the folder it points at. Remove the inputs "
            "link by hand and stage again; no input was copied."
        )
    for origin in origins:
        target = inputs / origin.name
        if _is_link(target) or (target.exists() and target.stat().st_nlink > 1):
            return (
                f"cannot stage {origin}: the destination {target} is a linked file. "
                "Copying over it could overwrite a user's input outside the "
                "simulation. Remove the staged link or choose another simulation; "
                "no input was copied."
            )
    return None


def _write_sim_archive(sim: Path, temporary: Path) -> None:
    """Write simulation evidence, recording staged links without following them."""
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in _sim_files(sim):
            bundle.write(path, path.relative_to(sim))
        for path in _sim_file_links(sim):
            # A file link is recorded, never followed: its target is not simulation evidence.
            note = path.relative_to(sim).as_posix() + ".LINK.txt"
            bundle.writestr(note, os.path.realpath(path) + "\n")
        link = sim / "inputs"
        if _is_link(link):
            bundle.writestr("inputs/STAGED_AS_LINK.txt", os.path.realpath(link) + "\n")


def is_reparse(path: Path) -> bool:
    """Say whether ``path`` is a symbolic link or a Windows junction (never followed)."""
    # Only a symbolic link or a mount-point junction: another reparse point (a cloud-backed
    # placeholder, a deduplicated file) reads as the ordinary file it is.
    return _is_link(path)


def _is_link(path: Path) -> bool:
    """Whether ``path`` is a symbolic link or, on Windows, a directory junction."""
    return path.is_symlink() or (sys.platform == "win32" and _is_junction(path))


def _is_junction(path: Path) -> bool:
    """Whether ``path`` is a Windows directory junction, on every supported Python.

    ``os.path.isjunction`` arrived in Python 3.12 and this package supports
    3.11, where the same fact is read off ``lstat``: a reparse point whose
    tag is the mount-point tag. False on any other platform.
    """
    if sys.platform != "win32":
        return False
    reader = getattr(os.path, "isjunction", None)
    if reader is not None:
        return bool(reader(path))
    try:
        found = os.lstat(path)
    except OSError:
        return False
    attributes = getattr(found, "st_file_attributes", 0)
    tag = getattr(found, "st_reparse_tag", 0)
    return (
        bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
        and tag == stat.IO_REPARSE_TAG_MOUNT_POINT
    )


def _make_dir_link(target: Path, link: Path) -> None:
    """Create ``link`` pointing at directory ``target``: a junction on Windows, a symlink elsewhere.

    A JUNCTION AND NOT A SYMLINK ON WINDOWS, because a symbolic link there
    needs a privilege an ordinary account does not hold and a junction
    needs none; both resolve for every reader and both are removed without
    touching what they point at.
    """
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def _remove_link(link: Path) -> None:
    """Remove a link and never what it points at."""
    if _is_junction(link):
        os.rmdir(link)
    else:
        os.unlink(link)


def _sim_files(sim: Path) -> list[Path]:
    """Every file under a simulation folder, never crossing a link."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(sim):
        here = Path(dirpath)
        dirnames[:] = sorted(name for name in dirnames if not _is_link(here / name))
        found.extend(here / name for name in sorted(filenames) if not _is_link(here / name))
    return found


def _sim_file_links(sim: Path) -> list[Path]:
    """Every file link under a simulation folder (dangling ones too), never crossing a link."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(sim):
        here = Path(dirpath)
        dirnames[:] = sorted(name for name in dirnames if not _is_link(here / name))
        found.extend(here / name for name in sorted(filenames) if _is_link(here / name))
    return found


def _remove_sim_tree(sim: Path) -> None:
    """Remove a simulation folder, unlinking every link inside it first.

    The estate's own incident is the reason this is not a bare rmtree: a
    scan that crossed sixteen junctions reported 13.8 GB inside a 6.4 GB
    tree, and a removal that crossed one would have deleted the survivor.
    """
    for dirpath, dirnames, _ in os.walk(sim):
        here = Path(dirpath)
        for name in list(dirnames):
            if _is_link(here / name):
                _remove_link(here / name)
                dirnames.remove(name)
    shutil.rmtree(sim)
