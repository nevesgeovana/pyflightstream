"""The saved-simulation reader this package reads boundary names through.

Pipeline role: a floor, like :mod:`pyflightstream._digest` and
:mod:`pyflightstream._mesh`. It imports only the base exception and the
standard library, and it is a floor BY BEHAVIOUR rather than a declared
row of the layer table, which is the same standing `_digest` has and
which ``tests/tier1_offline/test_conventions.py`` records in those words.

WHY IT EXISTS (PFS-2028.00). A run matrix used to cite a mesh boundary
by its POSITION in one geometry's boundary order. Those positions are
right for the file they were written against and mean different surfaces
in any file whose order differs, and nothing said so: the run completed,
exported, and reported loads for a rotor whose moving set was wrong.
The instruction is that nowhere in this package should a user
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
the boundary index: measured over the eight geometries of the reference
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

A POSITIONAL READING OUTSIDE THE MESH BLOCK (0.27.0) is the line map the
paragraph above says the mesh reading is not, so it reads only the shape it
was measured on and refuses every other: :func:`saved_length_unit` reads the
first two lines of the global block, and reads one head as metres and no
other. ``tests/tier1_offline/test_g06_actuator_disc.py`` holds it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TextIO

from pyflightstream._errors import PyflightstreamError

#: The CONSUMED surface, which is what this list is for. It carries
#: every name another module imports and no name only this one uses,
#: so `family_of` is deliberately absent and `resolve_family` is
#: deliberately present. The first version omitted `resolve_family`
#: while `cases/workflows.py` imported it, which would have let a
#: later tidy-up of unexported names break the caller.
__all__ = [
    "MESH_MARKER",
    "element_count",
    "MeshReadError",
    "boundary_labels",
    "boundary_names",
    "resolve_family",
    "saved_length_unit",
    "surface_mesh",
    "trailing_edge_midpoints",
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

    The boundary readers raise it only for a block that OPENS and then
    does not hold its shape. A file carrying no mesh block at all is not
    an error to them and reads as None: the campaign suite stages
    placeholder geometries deliberately, and FR-30c already licenses an
    undeclared inventory as permissive. The two readers of the block's
    CONTENTS, :func:`surface_mesh` and :func:`trailing_edge_midpoints`,
    refuse a file with no block, because they are asked for what the
    block holds and None would read as an empty mesh.
    """


def family_of(label: str) -> str:
    """Return the family a boundary label belongs to, case-folded.

    A label with no trailing index is its own family, so ``S`` belongs
    to ``s`` and matches only itself.
    """
    return _FAMILY_INDEX.sub("", label).casefold()


def element_count(path: str | Path) -> int | None:
    """Return the element count the mesh block STATES, or None.

    The first line after :data:`MESH_MARKER`, which is the line
    :func:`boundary_names` steps over. It is here, beside that skip, because
    the `.fsm` format has one reader: this one was written in the run layer
    for FR-82's cost table and a second parser of one format is two sites for
    the next format change (the architecture lens, 2026-09-11).

    THE NUMBER IS NOT TRUSTWORTHY TO THE UNIT, which is why
    :data:`_LINES_BEFORE_COUNT` skips it: one campaign geometry states 7848
    where every array holds 7784. It is the right order of magnitude for a
    reader comparing one row against another, and it must not be multiplied
    into anything.

    Returns
    -------
    int or None
        None for a file with no mesh block, one whose stated count is not a
        number, and one that cannot be opened. A wrong size is compared
        against other rows and a blank is not.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.strip() == MESH_MARKER:
                    stated = handle.readline().strip()
                    return int(stated) if stated.isdigit() else None
    except OSError:
        return None
    return None


def _block(path: str | Path, name: str) -> list[str] | None:
    """Return the lines of one ``$<name>_START$`` block, or None when the file has none.

    Read line by line, for the reason :func:`boundary_names` gives: the mesh
    block before it can hold a single line of a megabyte. A block that opens
    and never closes is refused, since its last lines would be read as some
    other block's.
    """
    target = Path(path)
    start, end = f"${name}_START$", f"${name}_END$"
    try:
        handle = target.open(encoding="utf-8", errors="replace")
    except OSError as error:
        raise MeshReadError(f"{target.name}: cannot be read: {error}") from error
    with handle:
        for line in handle:
            if line.strip() == start:
                break
        else:
            return None
        lines: list[str] = []
        for line in handle:
            if line.strip() == end:
                return lines
            lines.append(line.rstrip("\r\n"))
    raise MeshReadError(f"{target.name}: the block {start} opens and never closes")


#: THE HEAD OF THE GLOBAL BLOCK OF EVERY SAVED SIMULATION READ, and what it is
#: read as (G05, G06 of 0.27.0): the two values its first two lines carry.
#: Every save read on 2026-09-24, builds 26.120 to 26.124, opens with these two
#: and no other, among them the tier-3 geometries, which their preparation put
#: in metres (``SET_SIMULATION_LENGTH_UNITS METER`` before the save), and the
#: licensed saves made from them. 1.0 is a metre in metres, and 5 is METER's
#: position in the unit list the manual prints for that command.
#: WHETHER A SAVE IN ANOTHER UNIT WRITES ANOTHER HEAD IS NOT MEASURED: no save
#: in another unit has been read. So the head is not decoded into a unit; a
#: save carrying this head is read as metres, and one carrying any other head
#: is refused as a unit this package has not read.
_METRE_HEAD = (1.0, "5")


def saved_length_unit(path: str | Path) -> str | None:
    """Return the length unit a saved simulation was saved in, as far as it is read.

    Parameters
    ----------
    path : str or Path
        A saved simulation file.

    Returns
    -------
    str or None
        ``"METER"`` when the global block opens with the head every save read
        carries (:data:`_METRE_HEAD`). None when the file carries no global
        block at all, which no save of the solver lacks: a placeholder staged
        by a test reads as None, as it reads as no boundary inventory.

    Raises
    ------
    MeshReadError
        If the file cannot be read, or its global block opens with any other
        head, naming the two lines: the unit it was saved in is then not one
        this package has read, and a length converted on a guess is a body of
        the wrong size that solves without a word.
    """
    block = _block(path, "GLOBAL")
    if block is None:
        return None
    scale, index = (block + ["", ""])[:2]
    try:
        read = (float(scale), index.strip())
    except ValueError:
        read = (float("nan"), index.strip())
    if read != _METRE_HEAD:
        raise MeshReadError(
            f"{Path(path).name}: its global block opens with {scale.strip()!r} and "
            f"{index.strip()!r}, where every saved simulation this package has read opens "
            f"with {_METRE_HEAD[0]!r} and {_METRE_HEAD[1]!r}, the saves known to be in metres "
            "among them; the unit it was saved in is not one this package has read"
        )
    return "METER"


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
        If the file cannot be opened, naming it and the cause, or if the
        block opens and then does not hold its documented shape: an
        unreadable count, a record whose first line is not the flag
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
    except OSError as error:
        # REPORTED BY NAME (PFS-2029.12). Until 0.11.0 this returned None
        # in silence, so a file that could not be opened and a file
        # carrying no mesh block read the same, and the user was later
        # told their row cited an unknown label. The caller decides what
        # an unreadable file means for its run; this reader only says
        # which file and why.
        raise MeshReadError(f"{target.name}: cannot be read: {error}") from error
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


def names_of(token: str, names: Sequence[str]) -> list[str]:
    """Return the names one cell token selects out of a declared inventory, in its order.

    The rule, and the reason for its order, are
    :func:`resolve_family`'s: an exact name wins over a family, and the
    family match is case folded where the exact one is not. This is the
    same rule expressed over a SEQUENCE of names, which is what a caller
    holds when it judges by the surface rows of a loads table rather
    than by a label-to-index map, and it is the one home both readers
    call (the architecture lens of 2026-09-09 measured two).
    """
    if token in names:
        return [token]
    wanted = family_of(token)
    return [name for name in names if family_of(name) == wanted]


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
    return tuple(sorted(labels[name] for name in names_of(token, list(labels))))


#: The number of per-face T/F rows the mesh block carries after its 0/1
#: rows, measured on every saved simulation of the tier-3 library. A block
#: with another number is not the shape the trailing-edge reading below
#: was measured on, so it is refused rather than read by position.
_FLAG_ROWS = 5

#: Which T/F row flags which edge of a triangle, as the pair of the face's
#: vertex slots the edge joins (1-based row, 0-based slots). Rows 2, 3 and
#: 4 are the three edge slots (1,2), (2,3) and (3,1); rows 1 and 5 are set
#: on every face of the files read and carry no trailing-edge meaning that
#: has been established. The reading is measured, not documented: on the
#: solver's own saves of a straight wing these rows give exactly the
#: sixteen mid-points of its trailing edge and on a twisted blade the
#: twelve its detection marked, with every edge flagged from both of its
#: faces (RPT-065, the instrument of that report).
_EDGE_SLOT_ROWS = {2: (0, 1), 3: (1, 2), 4: (2, 0)}

#: A token of a T/F row.
_FLAGS = frozenset({"T", "F"})

#: The mesh a block holds: vertices, 0-based triangles, and the T/F rows.
_Block = tuple[
    tuple[tuple[float, float, float], ...],
    tuple[tuple[int, int, int], ...],
    tuple[tuple[bool, ...], ...],
]


def _tokens(line: str) -> list[str]:
    """Return the comma-separated tokens of one block row, blanks dropped.

    The id and per-face rows end in a comma, so a plain split leaves one
    empty token that is not a value.
    """
    return [token.strip() for token in line.split(",") if token.strip()]


class _BlockReader:
    """Reads a mesh block row by row, refusing by name any row out of shape."""

    def __init__(self, handle: TextIO, name: str) -> None:
        self.handle = handle
        self.name = name

    def refuse(self, detail: str) -> MeshReadError:
        return MeshReadError(
            f"{self.name}: {detail}. The mesh block is not the shape this reader knows, so no "
            "surface or trailing edge is read from it rather than a wrong one being guessed at"
        )

    def row(self, what: str) -> str:
        line = self.handle.readline()
        if not line:
            raise self.refuse(f"the mesh block ends before its {what}")
        return line.rstrip("\r\n")

    def count(self, what: str) -> int:
        text = self.row(what).strip()
        if not text.isdigit():
            raise self.refuse(f"its {what} reads {text!r}, which is not a count")
        return int(text)

    def sized(self, what: str, size: int, unit: str) -> list[str]:
        tokens = _tokens(self.row(what))
        if len(tokens) != size:
            raise self.refuse(
                f"its {what} holds {len(tokens)} values where the block states {size} {unit}"
            )
        return tokens


def _mesh_block(path: str | Path) -> _Block:
    """Read the mesh block's vertices, triangles and five T/F rows.

    Everything is located by the block's own counts, never by an absolute
    line: the boundary count gives the records to step over, the face
    count gives every per-face row's length, and the vertex count gives
    the coordinate rows'. The layout read, after the boundary records, is
    the face count, the face ids, the vertices per face, three
    vertex-index rows (1-based), the 0/1 rows, the five T/F rows, a line
    reading 0, the vertex count, and the x, y and z rows. Every deviation
    is refused by name.
    """
    target = Path(path)
    try:
        handle = target.open(encoding="utf-8", errors="replace")
    except OSError as error:
        raise MeshReadError(f"{target.name}: cannot be read: {error}") from error
    with handle:
        for line in handle:
            if line.strip() == MESH_MARKER:
                break
        else:
            raise MeshReadError(
                f"{target.name}: carries no mesh block ({MESH_MARKER}), so it has no surface "
                "mesh and no trailing-edge rows to read"
            )
        block = _BlockReader(handle, target.name)
        for _ in range(_LINES_BEFORE_COUNT):
            block.row("header")
        boundaries = block.count("boundary count")
        for position in range(1, boundaries + 1):
            head = block.row(f"boundary record {position}").strip()
            if not _HEAD_LINE.match(head):
                raise block.refuse(f"boundary {position} of {boundaries} begins with {head!r}")
            block.row(f"boundary record {position}")
            block.row(f"boundary record {position}")
        faces = block.count("face count")
        block.sized("face id row", faces, "faces")
        corners = block.sized("vertices-per-face row", faces, "faces")
        odd = next((value for value in corners if value != "3"), None)
        if odd is not None:
            raise block.refuse(
                f"a face has {odd!r} vertices, and only a triangle's three edge slots have "
                "been read in this format"
            )
        try:
            slots = [
                [int(value) - 1 for value in block.sized("vertex-index row", faces, "faces")]
                for _ in range(3)
            ]
        except ValueError as error:
            raise block.refuse(f"a vertex-index row holds a non-integer ({error})") from error
        # The 0/1 rows run until the first T/F row; their number is not
        # used, and each is held to the face count like every per-face row.
        while True:
            tokens = block.sized("per-face flag row", faces, "faces")
            if set(tokens) <= _FLAGS:
                break
        flags = [tuple(token == "T" for token in tokens)]
        while True:
            line = block.row("line after the T/F rows")
            tokens = _tokens(line)
            if not tokens or not set(tokens) <= _FLAGS:
                break
            if len(tokens) != faces:
                raise block.refuse(
                    f"a T/F row holds {len(tokens)} values where the block states {faces} faces"
                )
            flags.append(tuple(token == "T" for token in tokens))
        if len(flags) != _FLAG_ROWS:
            raise block.refuse(
                f"it carries {len(flags)} T/F rows where every block read carries five"
            )
        if line.strip() != "0":
            raise block.refuse(
                f"the line after the five T/F rows reads {line.strip()!r} where every block "
                "read carries 0"
            )
        points = block.count("vertex count")
        axes: list[list[float]] = []
        for axis in "xyz":
            try:
                axes.append([float(v) for v in block.sized(f"{axis} row", points, "vertices")])
            except ValueError as error:
                raise block.refuse(f"its {axis} row holds a non-number ({error})") from error
    if any(not 0 <= index < points for slot in slots for index in slot):
        raise block.refuse(f"a face names a vertex outside the {points} the block states")
    vertices = tuple(zip(axes[0], axes[1], axes[2], strict=True))
    triangles = tuple(zip(slots[0], slots[1], slots[2], strict=True))
    return vertices, triangles, tuple(flags)


def surface_mesh(
    path: str | Path,
) -> tuple[tuple[tuple[float, float, float], ...], tuple[tuple[int, int, int], ...]]:
    """Return the surface mesh a saved simulation's mesh block holds.

    Parameters
    ----------
    path : str or Path
        A saved simulation file.

    Returns
    -------
    tuple of (x, y, z)
        The vertices, in the block's order, in the simulation's length unit.
    tuple of (int, int, int)
        The triangles, as 0-based indices into the vertices.

    Raises
    ------
    MeshReadError
        If the file cannot be read, carries no mesh block, or carries one
        that does not hold the shape read here: a face that is not a
        triangle, a T/F row count other than five, or a row whose length
        is not the count the block states.
    """
    vertices, triangles, _ = _mesh_block(path)
    return vertices, triangles


def trailing_edge_midpoints(path: str | Path) -> tuple[tuple[float, float, float], ...]:
    """Return the mid-points of the mesh edges a saved simulation marks as trailing edges.

    The mesh block flags a trailing edge per face and per edge slot; this
    reads the three edge-slot rows and returns the mid-point of every
    flagged edge once, sorted. The mid-point is the form the wake-edge
    import reads, so a save can be compared as a set with the file that
    marked it, and a saved detection can be written back as a file
    (RPT-061, RPT-065).

    Parameters
    ----------
    path : str or Path
        A saved simulation file.

    Returns
    -------
    tuple of (x, y, z)
        The unique mid-points in the simulation's length unit, sorted.
        Empty when nothing is marked.

    Raises
    ------
    MeshReadError
        As :func:`surface_mesh`.

    Notes
    -----
    Every edge is flagged from both of its faces, in whichever slot it
    occupies on each, so an edge cleared from one side is still read from
    the other. A multi-boundary file shares one face array across its
    boundaries, so the result is every boundary's trailing edge together.
    Only triangular meshes have been read.
    """
    vertices, triangles, flags = _mesh_block(path)
    found: set[tuple[float, float, float]] = set()
    for row, (first, second) in _EDGE_SLOT_ROWS.items():
        for face, flagged in enumerate(flags[row - 1]):
            if flagged:
                a = vertices[triangles[face][first]]
                b = vertices[triangles[face][second]]
                found.add(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2))
    return tuple(sorted(found))
