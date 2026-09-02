"""The saved-simulation reader this package reads boundary names through.

Pipeline role: a floor, like :mod:`pyflightstream._digest` and
:mod:`pyflightstream._mesh`. It imports only the base exception and the
standard library, and it is a floor BY BEHAVIOUR rather than a declared
row of the layer table, which is the same standing `_digest` has and
which ``tests/test_conventions.py`` records in those words.

WHY IT EXISTS (PFS-2028.00). A run matrix used to cite a mesh boundary
by its POSITION in one geometry's boundary order. Those positions are
right for the file they were written against and mean different surfaces
in any file whose order differs, and nothing said so: the run completed,
exported, and reported loads for a rotor whose moving set was wrong.
The author's instruction is that nowhere in this package should a user
work with indices; a row names the mesh family and the package makes the
link. The names are already in the geometry file, so this module is the
package looking, instead of the user counting.

WHAT IT IS NOT. It is not a per-build line map, and it is not the thing
:mod:`pyflightstream.qa.probes` warns against when it says a saved
simulation is "sectioned text, every field being positional within its
section". The mesh block is SELF-DESCRIBING: it states its own boundary
count and its entries are fixed three-line records, so it is read
without knowing anything about the rest of the file, and every deviation
from that shape is refused rather than guessed at.

THE POSITION IS THE INDEX, AND THE NUMBER ON THE LINE IS NOT. Each
boundary's first line begins with an integer, and that integer is NOT
the boundary index: measured over the eight geometries of the author's
campaign, seven start theirs at 2 and one starts at 1, so a map built
from it would be off by one in seven files out of eight.

THE EVIDENCE IS A COMMITTED REPORT AND NOT THIS PARAGRAPH:
``reports/RPT-039_boundary-position-is-the-solver-index_2026-09-02.md``.
It states three measurements with their figures rather than describing
them, and the strongest is the solver answering the question itself: the
run log of the licensed 26.123 run lists that geometry's boundaries in
exactly mesh-block order. A fourth measurement was reported by a review
agent and EXCLUDED from the report, because the session writing it could
not reproduce the reading. A claim resting only on a docstring is what a
verification review refused here, correctly.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from pyflightstream._errors import PyflightstreamError

#: The CONSUMED surface, which is what this list is for. It carries
#: every name another module imports and no name only this one uses,
#: so `family_of` is deliberately absent and `resolve_family` is
#: deliberately present. The first version omitted `resolve_family`
#: while `cases/workflows.py` imported it, which would have let a
#: later tidy-up of unexported names break the caller.
__all__ = [
    "MESH_MARKER",
    "MeshReadError",
    "boundary_labels",
    "boundary_names",
    "resolve_family",
]

#: Opens the mesh section of a saved simulation. It is SEARCHED for and
#: never assumed at an offset: it sits on line 16 of seven campaign
#: geometries and on line 33 of the eighth, whose CAD block precedes it.
MESH_MARKER = "$MESH_START$"

#: Each boundary's first line. The three flags never vary across the 34
#: boundaries of the campaign's eight geometries, so a line that does not
#: match means the block is not the shape this reader knows, and the read
#: is abandoned rather than continued on a guess.
_HEAD_LINE = re.compile(r"^\d+,\s*[TF],\s*[TF],\s*[TF]$")

#: Lines per boundary record: the head line, the name alone on its own
#: line, and the display colour.
_RECORD_LINES = 3

#: Lines between the marker and the count. The first is an element count
#: that is not trustworthy (one campaign geometry states 7848 where every
#: array holds 7784) and the second follows no rule that eight files
#: agree on. Neither is needed, so both are skipped rather than read.
_LINES_BEFORE_COUNT = 2

#: A boundary whose name is written as an integer cannot be told apart
#: from a POSITION in a matrix cell, which is the whole defect this
#: module exists to remove. No campaign geometry carries one; the reader
#: refuses rather than admitting a name that reintroduces the ambiguity
#: through the one door being closed.
_NUMERIC = re.compile(r"^[+-]?\d+$")

#: Trailing index of a boundary label, which is what a FAMILY name is the
#: label without. ``Blade_1``, ``Blade 2`` and ``Blade3`` all belong to
#: the family ``blade``. Spelled the same way as, and deliberately kept
#: consistent with, ``script.helpers._COMPONENT_INDEX``, which is the
#: expander this package already owned and never reached.
_FAMILY_INDEX = re.compile(r"[\s_.-]*\d+$")


class MeshReadError(PyflightstreamError, ValueError):
    """A saved simulation carries a mesh block this reader cannot trust.

    Raised only for a block that OPENS and then does not hold its shape.
    A file carrying no mesh block at all is not an error and reads as
    None: the campaign suite stages placeholder geometries deliberately,
    and FR-30c already licenses an undeclared inventory as permissive.
    """


def family_of(label: str) -> str:
    """Return the family a boundary label belongs to, case-folded.

    A label with no trailing index is its own family, so ``S`` belongs
    to ``s`` and matches only itself.
    """
    return _FAMILY_INDEX.sub("", label).casefold()


def boundary_names(path: str | Path) -> tuple[str, ...] | None:
    """Return the ordered boundary names of a saved simulation.

    The tuple is in the solver's own boundary order, so the name at
    1-based position ``i`` is the name of boundary ``i``.

    Parameters
    ----------
    path : str or Path
        A saved simulation file.

    Returns
    -------
    tuple of str or None
        The ordered names, or None when the file carries no mesh block
        at all, which is not an error: a file that is not a saved
        simulation, or a placeholder staged by a test, reads as None and
        leaves the inventory undeclared exactly as it was before this
        module existed.

    Raises
    ------
    MeshReadError
        If the block opens and then does not hold its documented shape:
        an unreadable count, a record whose first line is not the flag
        line, a block that ends early, or a name written as an integer.

    Notes
    -----
    READ LINE BY LINE, NEVER WHOLE. These files run to 9 MB and one
    campaign geometry carries a single line of 1,013,200 bytes, so
    reading the whole text to find a name 600 bytes in would cost four
    orders of magnitude more than the answer is worth. The reader stops
    at the last boundary's colour line, which is under 700 bytes into
    seven of the eight campaign geometries and 41 KB into the eighth.
    """
    target = Path(path)
    try:
        handle = target.open(encoding="utf-8", errors="replace")
    except OSError:
        # SILENT, AND DELIBERATELY. A script builder emits OPEN with
        # whatever path its case carries and does not require the file
        # to be on disk; the run layer is what proves existence, with
        # its own message. Warning here fired on four script-building
        # tests whose cases name a path nobody creates, and a warning
        # that cries wolf on a normal state teaches a reader to ignore
        # the one that matters.
        return None
    with handle:
        for line in handle:
            if line.strip() == MESH_MARKER:
                break
        else:
            return None
        for _ in range(_LINES_BEFORE_COUNT):
            handle.readline()
        stated = handle.readline().strip()
        try:
            count = int(stated)
        except ValueError as error:
            raise MeshReadError(
                f"{target.name}: the mesh block states its boundary count "
                f"{_LINES_BEFORE_COUNT + 1} lines after {MESH_MARKER}, and that line reads "
                f"{stated!r}, which is not a number. The block is not the shape this reader "
                "knows, so no boundary name is taken from it rather than a wrong one being "
                "guessed at"
            ) from error
        if count < 0:
            raise MeshReadError(f"{target.name}: the mesh block states {count} boundaries")
        names: list[str] = []
        for position in range(1, count + 1):
            head = handle.readline()
            if not head:
                raise MeshReadError(
                    f"{target.name}: the mesh block states {count} boundaries and ends after "
                    f"{position - 1}"
                )
            if not _HEAD_LINE.match(head.strip()):
                raise MeshReadError(
                    f"{target.name}: boundary {position} of {count} begins with {head.strip()!r} "
                    "and every boundary record in this format begins with its number and three "
                    "flags. The block is not the shape this reader knows, so no name is taken "
                    "from it"
                )
            name = handle.readline().rstrip("\r\n").strip()
            handle.readline()
            if not name:
                raise MeshReadError(
                    f"{target.name}: boundary {position} of {count} carries no name"
                )
            if _NUMERIC.match(name):
                raise MeshReadError(
                    f"{target.name}: boundary {position} of {count} is named {name!r}, and a "
                    "boundary whose name is a number cannot be told apart from a POSITION in a "
                    "run matrix cell, which is the ambiguity this release exists to remove. "
                    "Rename it in the geometry, and any name that is not a bare number will do"
                )
            names.append(name)
    return tuple(names)


def boundary_labels(
    names: Sequence[str],
) -> tuple[dict[str, int], tuple[str, ...]]:
    """Split ordered names into a label inventory and the ambiguous ones.

    Parameters
    ----------
    names : sequence of str
        Ordered boundary names, as :func:`boundary_names` returns them.

    Returns
    -------
    dict of str to int
        Every name carried by exactly ONE boundary, mapped to its 1-based
        index.
    tuple of str
        The names carried by more than one boundary, in first-seen order.
        They are left OUT of the inventory, because a name that means two
        surfaces cannot select either one.

    Notes
    -----
    THE DUPLICATE IS FOUND HERE AND NOT BY THE REGISTRY, and that is the
    whole reason this function exists rather than a dict comprehension at
    the call site. Building ``{name: position for ...}`` collapses a
    duplicate silently: the later position wins, the earlier boundary
    vanishes from the inventory, and the registry's own collision guard
    never fires because the collision died before the call. The result
    is an inventory smaller than the file, which caps the declared total
    below the true boundary count and turns a correct index into a
    refusal. Nothing in the format forbids two boundaries sharing a name,
    and the rename command takes a free string, so this is a real state
    and not a defensive one.
    """
    seen: dict[str, list[int]] = {}
    for index, name in enumerate(names, start=1):
        seen.setdefault(name, []).append(index)
    labels = {name: positions[0] for name, positions in seen.items() if len(positions) == 1}
    ambiguous = tuple(name for name, positions in seen.items() if len(positions) > 1)
    return labels, ambiguous


def resolve_family(token: str, labels: Mapping[str, int]) -> tuple[int, ...]:
    """Resolve one cell token against a declared boundary inventory.

    Parameters
    ----------
    token : str
        One comma-separated word of a boundary-citing matrix cell.
    labels : mapping of str to int
        The declared inventory, label to 1-based index.

    Returns
    -------
    tuple of int
        Every boundary the token names, in ascending index order. Empty
        when the token names none, which the caller reports, because only
        the caller knows which row and which key asked.

    Notes
    -----
    AN EXACT LABEL WINS OVER A FAMILY, and the order is not arbitrary.
    ``Blade1`` is a label AND belongs to family ``blade``, so a family
    match tried first would silently turn a row citing one blade into a
    row citing six. Exact first means a row can always name one surface,
    and a family name is reachable precisely because no boundary is
    called ``Blade`` on its own.

    The exact match is case sensitive, matching the script layer's own
    label lookup. The family match is case folded, matching the expander
    this package already carried for rotating a component. The two
    differ deliberately: an exact name is the file's own spelling, and a
    family is a word the user chooses.
    """
    if token in labels:
        return (labels[token],)
    wanted = family_of(token)
    return tuple(sorted(index for label, index in labels.items() if family_of(label) == wanted))
