r"""The one route every text file of the package is written through, below every layer.

Pipeline role: below every layer, imported by every module that writes a
text file. It imports only the standard library, which is the reason it is a
module of its own, the same reason :mod:`pyflightstream._errors` is: the
cases layer writes scripts, the post layer writes products, the run layer
writes records and the workspace layer writes inputs, and none of them may
import another to get one write function.

WHY THERE IS ONE ROUTE (NFR-32, 0.34.0). A file written in text mode
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
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import IO, Any

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
    return Path(path).write_text(text, encoding=encoding, errors=errors, newline=LINE_END)


def append_text(path: str | Path, text: str, *, encoding: str = "utf-8") -> int:
    """Append ``text`` to ``path`` with LF line ends, creating the file when absent."""
    with open_text(path, "a", encoding=encoding) as stream:
        return stream.write(text)


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
    with open_text(path, "w") as handle:
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
    with open_text(path, "w", encoding=encoding) as handle:
        for line in lines:
            handle.write(line + LINE_END)
            count += 1
    return count


def write_json(path: str | Path, payload: object, *, indent: int | None = 2, **dump: Any) -> int:
    """Write ``payload`` as JSON with a final LF, on every platform.

    ``dump`` is passed to :func:`json.dumps` (``sort_keys``, ``ensure_ascii``,
    ``default``), and the text ends with exactly one LF, the form every JSON
    record of the package has.
    """
    return write_text(path, json.dumps(payload, indent=indent, **dump) + LINE_END)


def lf(text: str) -> str:
    """Return ``text`` with every CRLF and every lone CR turned into LF.

    This is the reading side of NFR-32: the parity script compares a 0.33.0 file
    with a current one after this normalisation, and a reader that must accept a
    file written by an older release applies it before splitting lines.
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
