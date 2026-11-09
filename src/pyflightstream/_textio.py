r"""The one route every text file of the package is written through, below every layer.

Pipeline role: below every layer, imported by every module that writes a
text file. It imports only the standard library, which is the reason it is a
module of its own, the same reason :mod:`pyflightstream._errors` is: the
cases layer writes scripts, the post layer writes products, the run layer
writes records and the workspace layer writes inputs, and none of them may
import another to get one write function.

WHY THERE IS ONE ROUTE (NFR-32). A file written in text mode
without a stated line end gets CRLF on Windows and LF on Linux, so the same
campaign posted on two platforms could give different bytes, and a byte
snapshot could not be portable. Every function here writes with
``newline="\n"``: the line end the text holds is the line end the file
holds, on every platform, and the package puts LF in the text. A bare
``Path.write_text(text)`` or ``open(path, "w")`` anywhere under ``src/``
brings the platform default back, so a tier-1 guard
(``tests/tier1_offline/test_p0340_lf_products.py``) walks the package and
refuses one, with a planted bypass as its control.

WHAT THE ROUTE DOES NOT DO. It never rewrites the text it is given: a text
that already holds a CR keeps it, because a captured solver log is a record
of what the solver printed. It does not cover binary writes (a workbook, a
byte-exact copy, a digest input), which are not text files. The CSV
functions fix the one thing the ``csv`` module decides on its own, its
default record terminator, which is CRLF whatever the handle does.


THE EXTENDED-LENGTH SPELLING. Windows refuses a file operation on a path of 260
characters or more unless the path is spelled ``\\?\`` followed by the absolute path
(``\\?\UNC\`` followed by the share for a network path). A workspace passes that
length once a datapoint's earlier attempt is moved into ``archive/<stamp>/``. The
:func:`long_path` spelling is handed to the file operation only; the names written do
not change.
"""

from __future__ import annotations

import csv
import json
import os
import stat
import sys
import threading
import time
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any
from uuid import uuid4

LINE_END = "\n"
"""The line end of every text file the package writes."""

_WRITE_MODES = frozenset({"w", "a", "x"})


def write_text(
    path: str | Path, text: str, *, encoding: str = "utf-8", errors: str | None = None
) -> int:
    r"""Write ``text`` to ``path`` with LF line ends on every platform.

    Parameters
    ----------
    path : str or Path
        The file to create or replace.
    text : str
        The text, whose own line ends are written unchanged.
    encoding : str, optional
        The encoding, UTF-8 unless a solver file needs another.
    errors : str, optional
        The ``errors`` argument of :func:`open`.

    Returns
    -------
    int
        The number of characters written.

    Examples
    --------
    >>> import tempfile
    >>> from pathlib import Path
    >>> target = Path(tempfile.mkdtemp()) / "lines.txt"
    >>> write_text(target, "a\nb\n")
    4
    >>> target.read_bytes()
    b'a\nb\n'
    """
    with atomic_text(path, encoding=encoding, errors=errors) as stream:
        return stream.write(text)


@contextmanager
def atomic_text(
    path: str | Path, *, encoding: str = "utf-8", errors: str | None = None
) -> Iterator[IO[str]]:
    """Publish a complete text file by replacing it from a sibling temporary file.

    A writer or close failure leaves the destination intact. Temporary files
    are removed on ordinary exceptions; abrupt process termination can leave
    a temporary sibling, but cannot publish its partial contents.

    Existing regular-file permission bits are retained. New files use the
    ordinary creation mode (0666 filtered by the process umask). Replacement
    publishes a new inode; ownership, ACLs and extended attributes are not
    copied. A destination symlink is replaced by a regular file, leaving its
    referent untouched, rather than following the link for writing.
    """
    target = Path(path)
    mode = None
    if target.is_file() and not target.is_symlink():
        mode = stat.S_IMODE(target.stat().st_mode)
    temporary = target.with_name(f".pfs-{uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    try:
        with os.fdopen(
            descriptor, "w", encoding=encoding, errors=errors, newline=LINE_END
        ) as stream:
            yield stream
        if mode is not None:
            os.chmod(temporary, mode)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def append_text(path: str | Path, text: str, *, encoding: str = "utf-8") -> int:
    """Append ``text`` to ``path`` with LF line ends, creating the file when absent."""
    with open_text(path, "a", encoding=encoding) as stream:
        return stream.write(text)


def write_bytes(path: str | Path, data: bytes) -> int:
    """Replace a complete byte payload atomically through a sibling temporary file.

    Keep the same permission and symlink policy as :func:`atomic_text`.
    Latin-1 maps each byte to one character; the explicit LF newline policy
    leaves CR, LF and CRLF bytes unchanged, including non-UTF-8 matrix comments.
    """
    with atomic_text(path, encoding="latin-1") as stream:
        return stream.write(data.decode("latin-1"))


def open_text(
    path: str | Path, mode: str = "w", *, encoding: str = "utf-8", errors: str | None = None
) -> IO[str]:
    """Open ``path`` for text writing with LF line ends on every platform.

    Parameters
    ----------
    path : str or Path
        The file to open.
    mode : str, optional
        ``"w"``, ``"a"`` or ``"x"``, a text mode that writes. A read mode or a
        binary mode is refused, because this is the write route.
    encoding : str, optional
        The encoding.
    errors : str, optional
        The ``errors`` argument of :func:`open`.

    Returns
    -------
    IO[str]
        The open handle, to be used as a context manager.

    Raises
    ------
    ValueError
        When ``mode`` is not a text mode that writes.
    """
    if mode not in _WRITE_MODES:
        # A floor module (FR-1155): the mode is the package's own argument, never a
        # user input, so the standard class stays and the package is not imported.
        raise ValueError(f"open_text writes text files: mode {mode!r} is not one of 'w', 'a', 'x'")
    return open(path, mode, encoding=encoding, errors=errors, newline=LINE_END)  # noqa: SIM115


def csv_writer(handle: IO[str], **fmt: Any) -> Any:
    """Return a ``csv.writer`` on ``handle`` whose record terminator is LF.

    The ``csv`` module ends a record with CRLF unless told otherwise, and it
    does so on every platform, so a handle that writes LF is not enough.
    """
    fmt.setdefault("lineterminator", LINE_END)
    return csv.writer(handle, **fmt)


def csv_dict_writer(handle: IO[str], fieldnames: Sequence[str], **fmt: Any) -> Any:
    """Return a ``csv.DictWriter`` on ``handle`` whose record terminator is LF."""
    fmt.setdefault("lineterminator", LINE_END)
    return csv.DictWriter(handle, fieldnames=list(fieldnames), **fmt)


def write_csv(
    path: str | Path, rows: Iterable[Iterable[object]], *, header: Sequence[str] | None = None
) -> int:
    """Write ``rows`` (and an optional ``header``) as a CSV file with LF record ends.

    Returns the number of data rows written.
    """
    count = 0
    with atomic_text(path) as handle:
        writer = csv_writer(handle)
        if header is not None:
            writer.writerow(header)
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


def write_lines(path: str | Path, lines: Iterable[str], *, encoding: str = "utf-8") -> int:
    """Write ``lines`` to ``path``, each ended by LF, and return how many were written."""
    count = 0
    with atomic_text(path, encoding=encoding) as handle:
        for line in lines:
            handle.write(line + LINE_END)
            count += 1
    return count


def write_json(path: str | Path, payload: object, *, indent: int | None = 2, **dump: Any) -> int:
    """Write ``payload`` as JSON with a final LF, on every platform.

    ``dump`` is passed to :func:`json.dumps` (``sort_keys``, ``ensure_ascii``,
    ``default``), and the text ends with exactly one LF, the form every JSON
    record of the package has. Non-finite floats are refused with ValueError
    before the destination is touched; ``allow_nan`` is always False.
    """
    dump["allow_nan"] = False
    return write_text(path, json.dumps(payload, indent=indent, **dump) + LINE_END)


def lf(text: str) -> str:
    """Return ``text`` with every CRLF and every lone CR turned into LF.

    This is the reading side of NFR-32: the parity script compares files
    after this normalisation. Readers apply it before splitting lines to
    accept either line-ending convention.
    """
    return text.replace("\r\n", LINE_END).replace("\r", LINE_END)


def count_cr(data: bytes) -> int:
    """Return how many CR bytes ``data`` holds, the measure of a file that is not LF."""
    return data.count(b"\r")


def file_cr_count(path: str | Path) -> int:
    """Return how many CR bytes the file at ``path`` holds; 0 is an LF file."""
    return count_cr(Path(path).read_bytes())


def append_lines(path: str | Path, lines: Iterable[str], *, encoding: str = "utf-8") -> int:
    """Append ``lines`` to ``path``, each ended by LF, and return how many were written."""
    count = 0
    with open_text(path, "a", encoding=encoding) as handle:
        for line in lines:
            handle.write(line + LINE_END)
            count += 1
    return count


_EXTENDED_PREFIX = "\\\\?\\"


def extended_length(path: str | os.PathLike[str], *, windows: bool | None = None) -> str:
    r"""Return ``path`` in the spelling a file operation accepts at any length.

    Parameters
    ----------
    path : str or path-like
        The path to spell.
    windows : bool, optional
        Whether to spell for Windows. Defaults to whether this process runs
        on Windows; a caller sets it to read the Windows spelling elsewhere.

    Returns
    -------
    str
        On Windows the absolute path behind ``\\?\`` (``\\?\UNC\`` for a
        network path); an already extended path is returned unchanged.
        Elsewhere the path as given.

    Examples
    --------
    >>> from pyflightstream._textio import extended_length
    >>> extended_length("a/b", windows=False)
    'a/b'
    >>> extended_length("D:/data/a", windows=True)
    '\\\\?\\D:\\data\\a'
    """
    text = os.fspath(path)
    if windows is None:
        windows = os.name == "nt"
    if not windows or not text or text.startswith(_EXTENDED_PREFIX):
        return text
    absolute = text.replace("/", "\\")
    if not (absolute.startswith("\\\\") or (len(absolute) > 2 and absolute[1:3] == ":\\")):
        absolute = os.path.abspath(absolute)
    if absolute.startswith("\\\\"):
        return _EXTENDED_PREFIX + "UNC\\" + absolute[2:]
    return _EXTENDED_PREFIX + absolute


def long_path(path: str | os.PathLike[str]) -> Path:
    """Return ``path`` as a path any file operation accepts at any length.

    Parameters
    ----------
    path : str or path-like
        The path.

    Returns
    -------
    pathlib.Path
        The path in its extended-length spelling on Windows, unchanged
        elsewhere. Use it for the file operation only: names and relative
        paths are derived from the original.

    Examples
    --------
    >>> from pyflightstream._textio import long_path
    >>> long_path("a").name
    'a'
    """
    return Path(extended_length(path))


def without_extended_prefix(path: str) -> str:
    r"""Return a Windows path without its extended-length prefix.

    ``Path.resolve`` answers ``\\?\C:\...`` once a resolved path reaches the Windows limit
    of 260 characters, and the plain form below it. So a file reached through a junction
    with a short name can resolve to a prefixed path while its folder resolves to a plain
    one, and the two no longer compare as parent and child.

    Examples
    --------
    >>> without_extended_prefix("\\\\?\\C:\\a\\b.txt")
    'C:\\a\\b.txt'
    >>> without_extended_prefix("\\\\?\\UNC\\host\\share\\b.txt")
    '\\\\host\\share\\b.txt'
    >>> without_extended_prefix("C:\\a\\b.txt")
    'C:\\a\\b.txt'
    """
    if path.startswith(_EXTENDED_PREFIX + "UNC\\"):
        return "\\\\" + path[8:]
    return path[4:] if path.startswith(_EXTENDED_PREFIX) else path


def resolved_plain(path: str | Path) -> Path:
    """Return ``path`` resolved, in the plain form whatever its resolved length."""
    return Path(without_extended_prefix(str(Path(path).resolve())))


#: The byte the Windows lock holds: past the end of any file the package
#: writes, so a reader of the content is never blocked by a held lock.
_LOCK_BYTE = 0x7FFFFFF0
#: How long a writer waits for another process's lock before it warns and skips (REL-R2-017).
LOCK_WAIT = 600.0
#: The locks this process holds, per file and thread, so a nested take is a no-op.
_HELD: dict[tuple[str, int], IO[bytes]] = {}


if sys.platform == "win32":
    import msvcrt

    def _lock(fd: int) -> bool:
        os.lseek(fd, _LOCK_BYTE, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    def _unlock(fd: int) -> None:
        os.lseek(fd, _LOCK_BYTE, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        return True

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


def _locked_handle(target: str, wait: float) -> IO[bytes] | None:
    """Open ``target`` (created when absent) and lock it, retrying until ``wait`` seconds pass."""
    deadline = time.monotonic() + wait
    while True:
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0)
        handle = open(os.open(target, flags, 0o666), "r+b", buffering=0)  # noqa: SIM115
        if _lock(handle.fileno()):
            try:
                mine, now = os.fstat(handle.fileno()), os.stat(target)
                if (mine.st_dev, mine.st_ino) == (now.st_dev, now.st_ino):
                    return handle
            except OSError:
                pass
            # REPLACED WHILE THIS PROCESS WAITED: the lock is on a file no longer at the name.
            _unlock(handle.fileno())
        handle.close()
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.05)


@contextmanager
def exclusive(path: str | os.PathLike[str], *, wait: float) -> Iterator[IO[bytes] | None]:
    """Hold an exclusive lock between processes on ``path``, yielding its open binary handle.

    The lock is the operating system's (``msvcrt.locking`` on one byte past the
    content on Windows, ``fcntl.flock`` elsewhere), so it is released when the
    process ends, however it ends. The file is created when absent and removed
    again on release if it is still empty. A thread that already holds it gets
    the same handle. After ``wait`` seconds of another holder it yields None:
    the caller warns and skips its write. Write through :func:`replace_content`;
    a replace onto a file a process holds open is refused on Windows.
    """
    target = extended_length(path)
    key = (os.path.normcase(os.path.abspath(target)), threading.get_ident())
    if key in _HELD:
        yield _HELD[key]
        return
    created = not os.path.exists(target)
    handle = _locked_handle(target, wait)
    if handle is None:
        yield None
        return
    _HELD[key] = handle
    try:
        yield handle
    finally:
        del _HELD[key]
        try:
            _unlock(handle.fileno())
        finally:
            handle.close()
        if created:
            try:
                if os.path.getsize(target) == 0:
                    os.unlink(target)
            except OSError:
                pass


def _a_json_object(text: str) -> bool:
    try:
        return isinstance(json.loads(text), dict)
    except ValueError:
        return False


def locked_document_text(path: str | os.PathLike[str], *, wait: float) -> str:
    """Read a JSON document under :func:`exclusive`, as its locked writer leaves it.

    A writer stages the whole document as ``<name>.tmp`` and then rewrites the
    file in place (:func:`replace_content`); a document cut off there is read
    from that staged copy, which stays until the rewrite completes. Every
    reader of such a document reads it here, so none reads it half written
    (REL-R3-002). An empty file reads as ``""``.
    """
    target = Path(path)
    with exclusive(target, wait=wait) as handle:
        if handle is None:
            text = target.read_text(encoding="utf-8")
        else:
            handle.seek(0)
            text = handle.read().decode("utf-8")
    staged = target.with_name(f"{target.name}.tmp")
    if text.strip() and not _a_json_object(text) and staged.is_file():
        backup = staged.read_text(encoding="utf-8")
        if _a_json_object(backup):
            return backup
    return text


def rewrite_locked(handle: IO[bytes], path: str | os.PathLike[str], text: str) -> None:
    """Rewrite ``path``, locked through ``handle``, as :func:`locked_document_text` reads it.

    Staged whole as ``<name>.tmp`` first (a write that fails there leaves the
    document untouched), then rewritten in place through ``handle``, since
    Windows refuses a replace onto a file a process holds open; the staged
    copy is removed once the rewrite completed (REL-R3-003).
    """
    target = Path(path)
    staged = target.with_name(f"{target.name}.tmp")
    try:
        write_text(staged, text)
    except BaseException:
        staged.unlink(missing_ok=True)
        raise
    replace_content(handle, text)
    staged.unlink(missing_ok=True)


def replace_content(handle: IO[bytes], text: str) -> None:
    """Replace the whole content of a locked ``handle`` with ``text`` in UTF-8, flushed to disk."""
    data = memoryview(text.encode("utf-8"))
    handle.seek(0)
    while data:
        data = data[handle.write(data) or 0 :]
    handle.truncate()
    os.fsync(handle.fileno())
