"""The one lookup of a run matrix by name over the workspace's two homes (FR-310).

A workspace keeps a run matrix at its root or under ``inputs/matrices/``
(:data:`pyflightstream.workspace.MATRIX_FOLDERS`), and since 0.32.0 the
restore, the post, the plan's census and the sync found it in both. The
other commands read the path as given, or the root alone, so a matrix one
command accepted was one another could not find. Every command that takes a
matrix, or looks one up by its name or stem, now asks :func:`matrix_path`,
which asks :func:`pyflightstream.workspace.find_matrix`: one rule, one home.

THE RULE (FR-310 R2 to R4). A value that names its folder (``inputs/m.fs``,
an absolute path) is read from that folder, as before. A bare file name or a
stem is looked up in both homes: in one of them, that file; in both with the
same bytes, the root's, read once; in both with different bytes, refused
before any work, naming both paths. A bare name found in neither home is
returned as given, so a matrix beside the working directory of a command run
from outside the workspace is read as it always was. Only ``*.fs`` files are
matrices of a home (:func:`pyflightstream.workspace.matrix_files`), so a
name with another suffix is never found there and is read as given.

A BARE NAME IN A HOME AND IN THE WORKING DIRECTORY. Until 0.32.0 a bare name
was read from the working directory. When the command runs outside the
workspace and the working directory holds a file of that name too, the two
are compared as the two homes are: the same bytes are one matrix; different
bytes are refused naming both paths, so no command reads a different file
than 0.32.0 read without saying so.

This module imports the package root and the root does not import it, so the
two form no cycle; its callers import it by its own path.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.workspace import (
    MATRIX_FOLDERS,
    WorkspaceError,
    find_matrix,
    matrix_by_stem,
    matrix_files,
)

__all__ = [
    "MATRIX_ARGUMENTS",
    "MATRIX_STEM_ARGUMENTS",
    "MATRIX_SUFFIX",
    "every_matrix",
    "matrix_path",
    "matrix_to_write",
    "names_its_folder",
    "resolve_matrix_arguments",
    "warn_a_matrix_outside_the_homes",
]

#: The suffix of a run matrix, the one :func:`matrix_files` lists.
MATRIX_SUFFIX = ".fs"

#: THE MATRIX ARGUMENTS OF ``pyfs-matrix``, as (subcommand, destination). Each
#: is resolved by :func:`resolve_matrix_arguments` before the command runs. A
#: parser argument whose destination names a matrix and which is in neither
#: this set nor :data:`MATRIX_STEM_ARGUMENTS` fails a tier-1 test that reads
#: the parsers (FR-310 R1: a command added later that takes a matrix joins it).
MATRIX_ARGUMENTS: frozenset[tuple[str, str]] = frozenset(
    {
        ("upgrade", "matrix"),
        ("convert", "matrix"),
        ("plan", "matrix"),
        ("inspect-setups", "matrix"),
        ("run", "matrix"),
        ("post", "matrix"),
        ("rebuild", "matrix"),
        # 0.35.0: `status --matrix` reads the matrix of either home by its stem
        # (FR-380 R2); the resolved path is read back as the stem it names.
        ("status", "matrix"),
    }
)

#: Arguments spelled ``matrix`` that name no file: ``restore --matrix`` names the
#: folder under ``post/`` by the matrix's stem, which is the same whichever home
#: the matrix sits in, and refuses a path. Nothing here resolves them.
MATRIX_STEM_ARGUMENTS: frozenset[tuple[str, str]] = frozenset({("restore", "matrix")})


def names_its_folder(given: str | Path) -> bool:
    """Whether ``given`` names a folder (``inputs/m.fs``, an absolute path) or is a bare name."""
    path = Path(given)
    return path.is_absolute() or path.parent != Path(".")


def _stem_of(name: str) -> str:
    """Return the stem a bare name asks for: ``m.fs`` and ``m`` both ask for ``m``."""
    return name[: -len(MATRIX_SUFFIX)] if name.lower().endswith(MATRIX_SUFFIX) else name


def matrix_path(root: str | Path, given: str | Path) -> Path:
    """Return the matrix ``given`` names, looked up over the two homes of ``root``.

    Parameters
    ----------
    root : str or Path
        The workspace root.
    given : str or Path
        What the user wrote: a path that names its folder, a bare file name,
        or a stem.

    Returns
    -------
    Path
        ``given`` itself when it names its folder or is in neither home;
        otherwise the file of the home that holds it, the root's when both
        hold the same bytes.

    Raises
    ------
    WorkspaceError
        When a bare name is in both homes with different bytes, or in a home
        and in the working directory with different bytes, naming both.
    """
    if names_its_folder(given):
        return Path(given)
    found = find_matrix(root, _stem_of(Path(given).name))
    if found is None:
        return Path(given)
    local = Path(given)
    if local.is_file() and not local.samefile(found) and local.read_bytes() != found.read_bytes():
        raise WorkspaceError(
            f"the matrix {local.name} is in the working directory ({local.resolve()}) and in "
            f"the workspace ({found}) with different contents; 0.32.0 read the first. Name the "
            "one to read by its folder, or keep one."
        )
    return found


def matrix_to_write(root: str | Path, name: str) -> Path:
    """Return where a matrix named ``name`` is written: its home, or ``inputs/matrices/`` if new.

    The Excel synchronization writes matrices back. A matrix that exists is
    written where it is; one in BOTH homes is refused even with equal bytes,
    since writing one of the two would make them differ; a new one goes to
    ``inputs/matrices/``, the dedicated folder.

    Raises
    ------
    WorkspaceError
        When the matrix is in both homes.
    """
    stem = _stem_of(name)
    held = [path for path in matrix_files(root) if path.stem == stem]
    if len(held) > 1:
        raise WorkspaceError(
            f"the matrix {stem} is in both homes of the workspace ({held[0]} and {held[1]}), "
            "and writing one of them would leave the other stale. Keep one."
        )
    return held[0] if held else Path(root) / MATRIX_FOLDERS[1] / f"{stem}{MATRIX_SUFFIX}"


def every_matrix(root: str | Path) -> list[Path]:
    """Every matrix of ``root``, one per stem over the two homes, in stem order.

    Raises
    ------
    WorkspaceError
        When one stem is in both homes with different bytes.
    """
    return [path for _, path in sorted(matrix_by_stem(root).items())]


def resolve_matrix_arguments(args: object) -> int | None:
    """Resolve, in place, every matrix argument of one parsed ``pyfs-matrix`` command.

    Each (subcommand, destination) of :data:`MATRIX_ARGUMENTS` holding a value
    is replaced by :func:`matrix_path` of it over the homes of the command's
    ``--workspace`` (the working directory where it has none), as text, so
    every later use of the argument (the plan receipt, the post, the rebuild)
    reads the one file.

    Returns
    -------
    int or None
        2, after printing the refusal to standard error, when a matrix is in
        both homes with different bytes; None otherwise.
    """
    subcommand = getattr(args, "subcommand", None)
    root = getattr(args, "workspace", None) or "."
    for command, destination in sorted(MATRIX_ARGUMENTS):
        value = getattr(args, destination, None) if command == subcommand else None
        if not isinstance(value, str) or not value:
            continue
        try:
            setattr(args, destination, str(matrix_path(root, value)))
        except WorkspaceError as error:
            print(f"matrix not read: {error}", file=sys.stderr)
            return 2
    return None


def warn_a_matrix_outside_the_homes(path: str | Path, root: str | Path) -> None:
    """Warn, never refuse, when the matrix lies outside both matrix folders.

    ``sync`` and the repeated-POL census read the root and ``inputs/matrices/``
    only (P0310-POL-CENSUS); a matrix elsewhere plans and runs, but neither of
    them sees it.
    """
    base = Path(root).resolve()
    parent = Path(path).resolve().parent
    if any(parent == (base / folder).resolve() for folder in MATRIX_FOLDERS):
        return
    warnings.warn(
        f"{Path(path).name} lies outside the workspace's matrix folders ({base} and "
        f"{base / 'inputs' / 'matrices'}): `sync` and the repeated-POL census do not see it. "
        "Move it into one of the two folders.",
        PyflightstreamWarning,
        stacklevel=3,
    )
