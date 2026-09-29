"""The directory link primitives the workspace layer stages and archives with.

Pipeline role: below :mod:`pyflightstream.workspace`, private to it and to
its sibling :mod:`pyflightstream.workspace.storage`. It imports nothing
from this package, which is what lets a public sibling reach it without
crossing a layer boundary for an underscore-private name out of another
PUBLIC module (`tests/tier1_offline/test_digest.py`'s layer-boundary
guard): a private name out of a private module is that module's own
business.

MOVED HERE FROM ``workspace/__init__.py`` ON 2026-09-28, PUSH REVIEW,
0.30.0. The four functions below are unchanged from that module, where
they stayed private and are imported back under their original names so
every existing caller there is unchanged. ``workspace/storage.py`` used to
reach them through three PUBLIC wrappers (``is_link``, ``make_dir_link``,
``remove_link``) kept only so a public sibling would not import a private
name out of another public module; publishing this module in its place
removes the reason those wrappers existed, the same fix ``_digest`` and
``_errors`` made for a digest helper and the exception base.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path


def _is_reparse(path: Path) -> bool:
    """Say whether ``path`` is a symbolic link or a Windows junction (never followed)."""
    try:
        info = path.lstat()
    except OSError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


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
