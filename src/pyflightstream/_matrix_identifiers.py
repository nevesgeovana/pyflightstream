"""The ``IDENTIFIERS`` key of a matrix row: read it, and read the matrix without it.

Below :mod:`pyflightstream.cases`, :mod:`pyflightstream.run`, :mod:`pyflightstream.post` and
:mod:`pyflightstream.workspace`, which share it. A row states in its ``VAR_NAMES_VALUES`` cell
``IDENTIFIERS: {FLAP:0,TESTE:10}``: columns for the tables the post writes and nothing for the
process. So this module answers two questions, and nothing else reads the key.

:func:`take_identifiers` takes the pair out of the cell before the variables are parsed. It does so
apart from the cell's grammar because a brace left open would otherwise swallow the keys after it,
which would change the run over a column that does nothing in it.

:func:`matrix_run_digests` is what a matrix digests to for the run: the file with its identifiers
removed, so editing one never makes a plan stale. A matrix with no identifiers digests to the plain
digest of its file, which is what every earlier plan recorded. :func:`matrix_form_digest` is what a
plan records beside it, for rows that end differently: the same file with its spaces normalized, so
an edit of those spaces alone is not seen either. :func:`plan_measured` accepts either; every other
edit is seen.
"""

from __future__ import annotations

import difflib
import hashlib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from pyflightstream._errors import PyflightstreamWarning, warn
from pyflightstream._tokens import plain_cell

#: The key a row states its identifiers under.
IDENTIFIERS_VARIABLE = "IDENTIFIERS"

_VARIABLES_COLUMN = "VAR_NAMES_VALUES"
_KEY = re.compile(rf"\s*{IDENTIFIERS_VARIABLE}\s*:")
_PAIR_SEPARATOR = "/"
#: Another ``NAME:value`` in a value, after a slash: the separator of the cell's other records.
_PAIR_INSIDE_A_VALUE = re.compile(r"/\s*[^/:]+:")

#: What a row's last cell may end in, past what it states: as found first, since that is what a
#: plan records, then none and one space. The two forms a person or an editor leaves behind a
#: pipe, when the key was the whole cell or the last pair of it.
_TAILS = (None, "", " ")


def _pair_end(cell: str, start: int) -> int:
    """Return where the ``/``-separated pair starting at ``start`` ends, at brace depth zero."""
    depth = 0
    for index in range(start, len(cell)):
        character = cell[index]
        if character == "{":
            depth += 1
        elif character == "}":
            depth = max(depth - 1, 0)
        elif character == _PAIR_SEPARATOR and depth == 0:
            return index
    return len(cell)


def _value_end(cell: str, start: int) -> int:
    """Return where the identifiers' value ends; a brace left open ends at the next slash."""
    end = _pair_end(cell, start)
    if cell[start:end].count("{") > cell[start:end].count("}"):
        slash = cell.find(_PAIR_SEPARATOR, start)
        return len(cell) if slash < 0 else slash
    return end


def take_identifiers(cell: str) -> tuple[str, list[str]]:
    """Return ``cell`` without its ``IDENTIFIERS`` pairs, and the value of each, as written.

    A cell with no such pair comes back unchanged and with an empty list.

    Parameters
    ----------
    cell : str
        The text of a ``VAR_NAMES_VALUES`` cell, with the spaces around it.

    Returns
    -------
    tuple of (str, list of str)
        The cell with the same spaces around what is left, and the values.
    """
    if IDENTIFIERS_VARIABLE not in cell:
        return cell, []
    kept: list[str] = []
    values: list[str] = []
    at = 0
    while at <= len(cell):
        key = _KEY.match(cell, at)
        if key is None:
            end = _pair_end(cell, at)
            kept.append(cell[at:end])
        else:
            end = _value_end(cell, key.end())
            values.append(cell[key.end() : end].strip())
        at = end + 1
    if not values:
        return cell, []
    lead = cell[: len(cell) - len(cell.lstrip())]
    trail = cell[len(cell.rstrip()) :]
    return lead + _PAIR_SEPARATOR.join(kept).strip() + trail, values


def _malformed(value: str, pol: str, reason: str) -> dict[str, str]:
    """Warn that a row's identifiers cannot be read; the row then states none."""
    warn(
        f"POL {pol}: {IDENTIFIERS_VARIABLE} is {value!r}, and {reason}; write "
        f"{IDENTIFIERS_VARIABLE}: {{NAME:value,NAME:value}}. This row states no identifiers, and "
        "nothing else of it changes.",
        PyflightstreamWarning,
        stacklevel=3,
    )
    return {}


def identifiers_stated_twice(stated: Sequence[str], pol: str) -> dict[str, str]:
    """Warn that a cell states the key more than once; the row then states none.

    Parameters
    ----------
    stated : sequence of str
        The values the cell gives the key, as written.
    pol : str
        The row's POL, for the warning.

    Returns
    -------
    dict of str to str
        Empty, as for any value that cannot be read.
    """
    return _malformed(stated[0], pol, f"the cell states it again as {stated[1]!r}")


def warn_of_a_near_key(names: Iterable[str], pol: str) -> None:
    """Warn of a variable spelled nearly as the key, since it is no column and the run reads it.

    Parameters
    ----------
    names : iterable of str
        The row's variables, the key already taken out.
    pol : str
        The row's POL, for the warning.
    """
    for name in names:
        if "_" not in name and difflib.get_close_matches(
            name.upper(), [IDENTIFIERS_VARIABLE], n=1, cutoff=0.85
        ):
            warn(
                f"POL {pol}: {name} is not {IDENTIFIERS_VARIABLE}, so it writes no column and "
                f"the run reads it as any variable. If it is meant as labels, write "
                f"{IDENTIFIERS_VARIABLE}: {{NAME:value,NAME:value}}.",
                PyflightstreamWarning,
                stacklevel=3,
            )


def parse_identifiers(value: str, pol: str) -> dict[str, str]:
    """Return the ``NAME: value`` pairs of one ``IDENTIFIERS`` value, as written.

    The pairs are separated by commas, so neither a name nor a value holds one; a slash stays in
    them, as the matrix reader does not split inside braces. A value is kept as its text. Nothing
    here stops a run: what cannot be read warns and states none (:class:`PyflightstreamWarning`).

    Parameters
    ----------
    value : str
        The value of the key, its braces included.
    pol : str
        The row's POL, for the warning.

    Returns
    -------
    dict of str to str
        The identifiers by name, in the order written; empty where the value cannot be read.
    """
    closes = value.find("}")
    if value.startswith("{") and value.count("}") == 1 and closes != len(value) - 1:
        warn(
            f"POL {pol}: {IDENTIFIERS_VARIABLE} is followed by {value[closes + 1 :].strip()!r} "
            "with no slash, and the run does not read that text. Put a / before the next key. "
            "This row states no identifiers.",
            PyflightstreamWarning,
            stacklevel=2,
        )
        return {}
    if (
        not (value.startswith("{") and value.endswith("}"))
        or value.count("{") != 1
        or (value.count("}") != 1)
    ):
        return _malformed(value, pol, "it is not one pair of braces")
    stated: dict[str, str] = {}
    held: set[str] = set()
    for pair in value[1:-1].split(","):
        if not pair.strip():
            continue
        name, separator, cell = pair.partition(":")
        name = name.strip()
        if not separator or not name:
            return _malformed(value, pol, f"{pair.strip()!r} is not a NAME:value pair")
        if plain_cell(name) in held:
            return _malformed(value, pol, f"it states {name} twice")
        held.add(plain_cell(name))
        stated[name] = cell.strip()
        if _PAIR_INSIDE_A_VALUE.search(cell):
            warn(
                f"POL {pol}: {IDENTIFIERS_VARIABLE} gives {name} the value {cell.strip()!r}, which "
                "holds another NAME:value after a slash. It is written as that text. Pairs are "
                "separated by commas: {NAME:value,NAME:value}.",
                PyflightstreamWarning,
                stacklevel=2,
            )
    return stated


@dataclass(frozen=True)
class _Line:
    """One line of a matrix file, its last cell without the identifiers."""

    body: str
    tail: str
    ending: str
    #: The row's last cell held identifiers or is empty, so what follows it is not the row's.
    loose: bool
    #: The line with the pairs around the removed key spaced as the matrix writes them.
    spaced: str | None = None

    def text(self, tail: str | None, spaced: bool = False) -> str:
        body = self.spaced if spaced and self.spaced is not None else self.body
        return body + (self.tail if tail is None or not self.loose else tail) + self.ending


def _respaced(cell: str) -> str:
    """Return a cell with its pairs spaced as the matrix writes them, for a key written tight."""
    pairs: list[str] = []
    at = 0
    while at <= len(cell):
        end = _pair_end(cell, at)
        pairs.append(cell[at:end].strip())
        at = end + 1
    return " " + " / ".join(pair for pair in pairs if pair) + cell[len(cell.rstrip()) :]


def _matrix_line(line: str, column: int | None) -> _Line:
    """Return one line of the file with the identifiers of its variables cell removed."""
    content = line.rstrip("\r\n")
    ending = line[len(content) :]
    cells = content.split("|")
    if column is None or content.lstrip().startswith("#") or column >= len(cells):
        return _Line(content, "", ending, False)
    cell, values = take_identifiers(cells[column])
    cells[column] = cell
    joined = "|".join(cells)
    body = joined.rstrip()
    empty = not cell.strip()
    tail = "" if values and empty else joined[len(body) :]
    spaced = None
    if values and not empty:
        cells[column] = _respaced(cell)
        spaced = "|".join(cells).rstrip()
    return _Line(body, tail, ending, bool(values) or empty, spaced)


def _variables_column(lines: list[str]) -> int | None:
    """Return the index of the variables cell, or None where no line is the matrix header."""
    for line in lines:
        if line.lstrip().startswith("#"):
            continue
        names = [name.strip() for name in line.split("|")]
        if _VARIABLES_COLUMN in names:
            return names.index(_VARIABLES_COLUMN)
    return None


def matrix_run_digests(path: str | Path) -> tuple[str, ...]:
    """Return what the matrix at ``path`` digests to for the run, the recorded form first.

    Every digest is of the file with its identifiers removed. The first is what a plan records: a
    matrix with no identifiers gives the plain SHA-256 of its file there, as every plan has
    recorded. The others differ only in what follows the last cell of a row that held identifiers
    or holds nothing, and in the spaces around the pairs beside a removed key, because taking the
    key away cannot tell how the cell stood before it was written. These are one of the two
    answers :func:`plan_measured` accepts; by these digests alone, the file's other bytes all count.

    Parameters
    ----------
    path : str or Path
        The matrix file.

    Returns
    -------
    tuple of str
        The digests, one or more; empty when the file cannot be read.
    """
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return ()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return (hashlib.sha256(raw).hexdigest(),)
    pieces = text.splitlines(keepends=True)
    column = _variables_column(pieces)
    lines = [_matrix_line(piece, column) for piece in pieces]
    digests = (
        hashlib.sha256(
            "".join(line.text(tail, spaced) for line in lines).encode("utf-8")
        ).hexdigest()
        for spaced in (False, True)
        for tail in _TAILS
    )
    return tuple(dict.fromkeys(digests))


def matrix_run_digest(path: str | Path) -> str | None:
    """Return the digest a plan records for the matrix at ``path``; None when it cannot be read.

    Parameters
    ----------
    path : str or Path
        The matrix file.

    Returns
    -------
    str or None
        The first of :func:`matrix_run_digests`.
    """
    digests = matrix_run_digests(path)
    return digests[0] if digests else None


def _formed_line(line: str, column: int | None) -> str:
    """Return one line with its identifiers out, its pairs spaced one way and no end spaces."""
    content = line.rstrip("\r\n")
    cells = content.split("|")
    if column is None or content.lstrip().startswith("#") or column >= len(cells):
        return line
    cell = take_identifiers(cells[column])[0]
    pairs = []
    at = 0
    while at <= len(cell):
        end = _pair_end(cell, at)
        pairs.append(cell[at:end].strip())
        at = end + 1
    cells[column] = " " + " / ".join(pair for pair in pairs if pair)
    return "|".join(cells).rstrip() + line[len(content) :]


def matrix_form_digest(path: str | Path) -> str | None:
    """Return the digest of what the matrix states for the run, whatever spaces surround it.

    The file with its identifiers removed, the pairs of each row's cell spaced one way and no
    space ending a row. Those spaces mean nothing to the reader, and taking a key away cannot tell
    how they stood, row by row, where a person's editor left them: a digest of the file as found
    answers only when every row ended alike. A plan records this beside ``matrix_sha256``.

    Parameters
    ----------
    path : str or Path
        The matrix file.

    Returns
    -------
    str or None
        The digest; None when the file cannot be read.
    """
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return hashlib.sha256(raw).hexdigest()
    pieces = text.splitlines(keepends=True)
    column = _variables_column(pieces)
    formed = "".join(_formed_line(piece, column) for piece in pieces)
    return hashlib.sha256(formed.encode("utf-8")).hexdigest()


def plan_measured(planned: str, planned_form: object, path: str | Path) -> bool:
    """Return whether a plan's digests are of the matrix at ``path`` as the run reads it.

    Parameters
    ----------
    planned : str
        The plan's ``matrix_sha256``.
    planned_form : object
        The plan's ``matrix_form_sha256``; a plan of an earlier release holds none.
    path : str or Path
        The matrix file.

    Returns
    -------
    bool
        True when either digest answers.
    """
    if planned in matrix_run_digests(path):
        return True
    return isinstance(planned_form, str) and planned_form == matrix_form_digest(path)
