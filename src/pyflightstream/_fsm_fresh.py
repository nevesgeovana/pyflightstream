"""The content a freshly imported saved simulation holds, block by block (FR-312).

Pipeline role: a floor, like :mod:`pyflightstream._fsm`, whose reader it
completes. It imports only the base exception and the standard library.

WHY IT EXISTS. A saved simulation carries the state of the run that saved it,
and that state takes precedence over what a script sets: the saved solver
actions of FR-308 are one case of it. A geometry meant as an input should hold
the meshes and the boundary conditions already set (the base regions, the
trailing edges and the others), and everything else should come from the
script. So every block other than those is put back to the content a freshly
imported file holds.

WHAT IS RESET IS MEASURED, NEVER GUESSED (FR-312 R2). A saved simulation is a
sequence of ``$<NAME>_START$`` ... ``$<NAME>_END$`` blocks after a two-line
head (the solver's version, then its build). Measured on 2026-09-30 over the
ten committed tier-3 geometries, which the tier-3 preparation made by
importing an STL, setting the length unit to metres, detecting the trailing
edges and the wake termination nodes and saving, nothing else, on 26.120
(build 7012026): the blocks below hold the SAME lines in all ten, whatever the
shape (wing, half wing, body, blade, pusher, twin). :func:`common_blocks` is
that measurement, and a tier-1 test re-measures the table against the files.

WHAT THE MEASUREMENT SHOWS AND WHAT IT DOES NOT. It shows the content common
to ten saves made by ONE preparation recipe, not that every fresh import of
that build holds it, and not that these blocks hold nothing a person sets on
purpose: ``GLOBAL`` holds the reference point and frame and ``SOLVER`` and
``WAKE`` the solver and wake settings, and a clean discards any of them set by
hand. That is the owner's statement of the clean (a geometry keeps its meshes
and its boundary conditions, everything else comes from the script), not a
measurement; the paired measurement FR-312 names (a simulation carrying every
block against the same mesh freshly imported) is still owed, and the blocks a
clean resets are named on standard error each time.

Kept unchanged in every file, each for a measured reason:

* ``MESH``: the meshes, their boundary names, the trailing edges and the wake
  termination marks.
* ``PHYSICS``, ``WRAPPER``, ``GRAPHICS``: they differ between the ten fresh
  imports, so their fresh content depends on the geometry and is not a
  constant; ``PHYSICS`` also holds the surface lists the boundary conditions
  are set in.
* ``CAD``, ``CADCREATE``, ``CADMESHING``: equal in the ten, which are all STL
  imports; what a CAD import holds there is not measured, so they are kept
  rather than reset on a guess.

A file of another build, or saved in another length unit, has no measured
fresh import: every block is kept and the caller is told so. On 26.124 (build
8172026) the layout itself differs (``CADCREATE`` and ``STABILITY`` carry one
line more than on 26.120), which is why the table is keyed by build and unit,
and why a new build enters it from a fresh save of that build, measured by
:func:`common_blocks`, and from nothing else.

WHAT THE SOLVER DOES WITH A RESET FILE IS NOT MEASURED HERE. That the solver
opens and runs a cleaned file is owed by the licensed round of FR-312.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pyflightstream._errors import PyflightstreamError

__all__ = [
    "FRESH_IMPORT",
    "KEPT_BLOCKS",
    "FreshReset",
    "FreshResetError",
    "block_lines",
    "common_blocks",
    "reset_to_fresh_import",
    "saved_build",
]

#: Opens or closes one block; the name is what the two markers share.
_MARKER = re.compile(r"^\$([A-Z0-9_]+)_(START|END)\$$")

#: The blocks never reset, and why (the module docstring gives the measurement).
KEPT_BLOCKS: Mapping[str, str] = {
    "MESH": "the meshes, the boundaries, the trailing edges and the wake termination marks",
    "PHYSICS": "the boundary-condition surface lists; differs between fresh imports",
    "WRAPPER": "differs between fresh imports of different geometries",
    "GRAPHICS": "differs between fresh imports of different geometries",
    "CAD": "the import source; measured on STL imports only",
    "CADCREATE": "the import source; measured on STL imports only",
    "CADMESHING": "the import source; measured on STL imports only",
}

#: THE MEASURED FRESH IMPORTS, keyed by (build, length unit): each block's lines
#: between its markers, exactly as the ten tier-3 geometries of 26.120 hold them.
FRESH_IMPORT: Mapping[tuple[str, str], Mapping[str, tuple[str, ...]]] = {
    ("7012026", "METER"): {
        "GLOBAL": (
            " 1.00000000000000000E+00",
            "5",
            " 6.00000000000000000E+01",
            " 9.99999999999999955E-08",
            "7012026",
            " 0.00000000000000000E+00, 0.00000000000000000E+00, 0.00000000000000000E+00",
            "4",
            "1",
            "Reference",
            " T,",
            " 0.00000000000000000E+00, 0.00000000000000000E+00, 0.00000000000000000E+00",
            " 1.00000000000000000E+00, 0.00000000000000000E+00, 0.00000000000000000E+00",
            " 0.00000000000000000E+00, 1.00000000000000000E+00, 0.00000000000000000E+00",
            " 0.00000000000000000E+00, 0.00000000000000000E+00, 1.00000000000000000E+00",
            "0, F, F, F,0",
            " F, F, F, F, F",
            " F, F, F",
            " 0.00000000000000000E+00, 0.00000000000000000E+00, 1.00000000000000000E+00",
            " 0.00000000000000000E+00, 0.00000000000000000E+00, 1.00000000000000000E+00",
            " 0.00000000000000000E+00, 0.00000000000000000E+00, 1.00000000000000000E+00",
            "0,1,2,3,4,5,6,7,8,9,10,11,",
            "100,100,100,100,100,100,100,100,100,100,100,100,",
            " F, F,1, 0.00000000000000000E+00, 0.00000000000000000E+00",
            "1, F",
            " 0.00000000000000000E+00, 0.00000000000000000E+00, 0.0000000"
            "0000000000E+00, 0.00000000000000000E+00, 0.00000000000000000"
            "E+00, 0.00000000000000000E+00, 0.00000000000000000E+00, 0.00"
            "000000000000000E+00, 0.00000000000000000E+00, 0.000000000000"
            "00000E+00, 0.00000000000000000E+00, 0.00000000000000000E+00,"
            " 0.00000000000000000E+00, 0.00000000000000000E+00, 0.0000000"
            "0000000000E+00, 0.00000000000000000E+00, 0.00000000000000000"
            "E+00, 0.00000000000000000E+00, 0.00000000000000000E+00, 0.00"
            "000000000000000E+00, 0.00000000000000000E+00, 0.000000000000"
            "00000E+00, 0.00000000000000000E+00, 0.00000000000000000E+00,"
            " 0.00000000000000000E+00, 0.00000000000000000E+00, 0.0000000"
            "0000000000E+00, 0.00000000000000000E+00, 0.00000000000000000"
            "E+00, 0.00000000000000000E+00,",
            " 0.00000000000000000E+00, 0.00000000000000000E+00, 0.00000000000000000E+00",
            " 0.00000000000000000E+00, 0.00000000000000000E+00, 0.00000000000000000E+00",
            " 0.00000000000000000E+00, 0.00000000000000000E+00, 0.00000000000000000E+00",
            " 0.00000000000000000E+00, 0.00000000000000000E+00, 0.00000000000000000E+00",
            "0,0,0",
            "0,0,0",
        ),
        "MOTION": (
            "0",
            " F",
            "Gust",
            " 0.00000000000000000E+00,0",
            "1",
        ),
        "POST": (
            " T",
            " 0.00000000000000000E+00",
            "0",
            "0",
            "0",
            "0",
            "0",
            "0",
        ),
        "WAKE": (
            " 1.00000000000000000E+00",
            " 1.00000000000000000E+01",
            " T",
            "0",
            " T,1",
            "0,1",
            "0",
            " F",
            "-1",
            " T",
            "100.000",
            ".150",
            ".000",
        ),
        "SOLVER": (
            "0",
            "0",
            "0",
            "1",
            "0",
            "0",
            " F",
            "  0.000000000000000E+000  0.100000000000000     ",
            "0,2",
            " T, 1.00000000000000000E+00",
            " F",
            "0",
            " 1.00000000000000000E+00, 0.00000000000000000E+00",
            "0,1",
            "0",
            " F",
            "0",
            " T",
            " T, T, T, T, T, T, T, T, T, T, T, T, T, T, T, T, T, T, T, T,"
            " T, T, T, T, T, T, T, T, T, T,",
            " 0.00000000000000000E+00",
            " 0.00000000000000000E+00",
            " 1.00000000000000000E+02",
            " 1.00000000000000000E+00, 0.00000000000000000E+00, 0.00000000000000000E+00",
            " 0.00000000000000000E+00, 1.00000000000000000E+00, 0.00000000000000000E+00",
            " 0.00000000000000000E+00, 0.00000000000000000E+00, 1.00000000000000000E+00",
            "500",
            " 1.00000000000000008E-05, 1.00000000000000000E+03",
            " F",
            "0",
            " 1.00000000000000000E+02",
            " 1.00000000000000000E+00",
            " 1.00000000000000000E+00",
            "-2.00000000000000000E+01",
            " F",
            "20",
            "2, 0.00000000000000000E+00, F, 1.00000000000000000E+00, F",
            "0",
            " 0.00000000000000000E+00, 1.00000000000000000E+00, 1.00000000000000000E+00",
            "15",
            " F",
            " T",
            " F",
            "3",
            "0,0",
            "1,2,0,2,2",
            " T,0",
            "0,1,2,3,4,5,6,7,8,9",
            "100,70,70,70,70,70,70,70,70,70",
            " F, F, F, F",
            "0,0",
            " T",
            "0",
            " F",
            "0",
            "0",
            "0",
        ),
        "ACOUSTIC": (
            " F,0,100, 0.00000000000000000E+00, 1.00000000000000000E+00",
            "0",
            "0",
            " F, F,1,1,2,1,10,40",
            "0, 0.00000000000000000E+00, 0.00000000000000000E+00, 1.00000000000000000E+00",
            "0",
            "0",
            " F, F,1,1,10,1, 1.00000000000000000E+00,0",
            "0",
            "0",
        ),
        "STABILITY": ("1, F,1,0, 2.00000000000000011E-01",),
        "AEROELASTIC": (
            "0,0,0,10,0",
            " F, F,0,0",
            "",
            "",
            "1,0,0,0,1",
            " F",
            " " * 1000,
            "0",
        ),
    },
}


class FreshResetError(PyflightstreamError, ValueError):
    """A file whose build is measured but whose blocks are not the measured layout."""


@dataclass(frozen=True)
class FreshReset:
    """What :func:`reset_to_fresh_import` did to one saved simulation.

    Attributes
    ----------
    text : str
        The file's text with the measured blocks reset.
    blocks : tuple of str
        The blocks whose content changed, in file order.
    note : str or None
        Why nothing was reset, when no fresh import of the file's build and
        unit is measured; None when the table applied.
    """

    text: str
    blocks: tuple[str, ...]
    note: str | None = None


def _lines(text: str) -> tuple[str, list[str]]:
    """Split a whole saved simulation into its line ending and its lines."""
    eol = "\r\n" if "\r\n" in text else "\n"
    return eol, text.split(eol)


def saved_build(text: str) -> str | None:
    """Return the build a saved simulation's head names, or None when the head is not one."""
    _, lines = _lines(text)
    if len(lines) < 2 or not re.fullmatch(r"\d+,\d+", lines[0].strip()):
        return None
    build = lines[1].strip()
    return build if build.isdigit() else None


def block_lines(text: str) -> dict[str, tuple[str, ...]]:
    """Return every top-level block of a saved simulation, by name, as its lines.

    Raises
    ------
    FreshResetError
        When a block opens twice, closes without opening, or never closes.
    """
    _, lines = _lines(text)
    found: dict[str, tuple[str, ...]] = {}
    open_name: str | None = None
    start = 0
    for index, line in enumerate(lines):
        marker = _MARKER.match(line.strip())
        if marker is None:
            continue
        name, side = marker.groups()
        if side == "START" and open_name is None:
            open_name, start = name, index
        elif side == "END" and name == open_name:
            if name in found:
                raise FreshResetError(f"the block {name} appears twice")
            found[name] = tuple(lines[start + 1 : index])
            open_name = None
    if open_name is not None:
        raise FreshResetError(f"the block {open_name} opens and never closes")
    return found


def common_blocks(texts: Sequence[str]) -> dict[str, tuple[str, ...]]:
    """Return the blocks every one of ``texts`` holds with the same lines: the measurement.

    Given fresh imports of several geometries saved by one build in one unit,
    the result is the content a fresh import of that build holds whatever
    the geometry; a block that differs between them is left out.
    """
    tables = [block_lines(text) for text in texts]
    if not tables:
        return {}
    return {
        name: lines
        for name, lines in tables[0].items()
        if all(table.get(name) == lines for table in tables[1:])
    }


def reset_to_fresh_import(text: str, unit: str | None, where: str) -> FreshReset:
    """Reset every measured block of a saved simulation to its fresh-import content.

    Parameters
    ----------
    text : str
        The whole saved simulation, decoded byte for byte (latin-1), so that
        encoding the result back keeps every byte of every kept block.
    unit : str or None
        The length unit the file was saved in, as
        :func:`pyflightstream._fsm.saved_length_unit` reads it.
    where : str
        The file's name, for the messages.

    Returns
    -------
    FreshReset
        The new text, the blocks reset, and a note when the file's build and
        unit have no measured fresh import, in which case the text is
        returned unchanged.

    Raises
    ------
    FreshResetError
        When the build is measured and a block the table resets is missing
        or malformed; nothing is reset then.
    """
    build = saved_build(text)
    table = FRESH_IMPORT.get((build or "", unit or ""))
    if table is None:
        return FreshReset(
            text,
            (),
            f"{where}: no fresh import of build {build or 'unknown'} saved in "
            f"{unit or 'an unread unit'} is measured, so every block other than the "
            "saved solver actions is kept as it is (FR-312 R2)",
        )
    eol, lines = _lines(text)
    held = block_lines(text)
    reset: list[str] = []
    for name, fresh in table.items():
        if name not in held:
            raise FreshResetError(f"{where}: build {build} and carries no {name} block")
        if held[name] == fresh:
            continue
        start = next(i for i, line in enumerate(lines) if line.strip() == f"${name}_START$")
        end = next(i for i in range(start, len(lines)) if lines[i].strip() == f"${name}_END$")
        lines[start + 1 : end] = list(fresh)
        reset.append(name)
    order = list(held)
    return FreshReset(eol.join(lines), tuple(sorted(reset, key=order.index)))
