"""The files the helpers park for a run, split out of ``helpers`` (AD-08).

``helpers.mark_wake_edges`` writes the import command that marks wake edges
from a node list; this module holds the node file's text, the two route
names, the build the file route was measured on, the reader of the
simulation's length-unit vocabulary, and the checks that hold one path to
one parked file. Every name is imported back into
:mod:`pyflightstream.script.helpers`, which stays the public path.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from pyflightstream._decimal import plain_decimal
from pyflightstream._digest import one_file_key
from pyflightstream.script import LENGTH_UNIT_COMMAND, CommandArgumentError, Script

#: Marking wake edges from an imported node list, and the angle
#: criterion it replaces. Named as a pair because the whole point of the
#: refusal below is that one is never silently substituted for the other.
WAKE_EDGE_IMPORT_ROUTE = "IMPORT_WAKE_EDGES_FROM_FILE"
WAKE_EDGE_ANGLE_ROUTE = "AUTO_DETECT_TRAILING_EDGES"

#: The coordinate line the 26.124 import consumes after the count and does
#: not use (RPT-061): the first line holding three numbers is read and
#: discarded, so a file without it loses its first point. It is a triple
#: because a bare number or an empty line is skipped rather than consumed.
WAKE_EDGE_NODE_PLACEHOLDER = "0,0,0"


def render_wake_edge_node_file(midpoints: Sequence[Sequence[float]]) -> str:
    """Return the text of the node file the wake-edge import reads on 26.124.

    The layout is the one measured to mark (RPT-061): the number of points,
    then :data:`WAKE_EDGE_NODE_PLACEHOLDER`, the coordinate line the solver
    consumes and does not use, then one ``x,y,z`` row per trailing-edge
    MID-POINT, in the simulation's length unit. There is no unit line and
    no id column: the file's unit is not read, and a word or an id on any
    line makes the import mark nothing, in silence.

    Parameters
    ----------
    midpoints : sequence of (x, y, z)
        The mid-points of the mesh edges to mark, already in the
        simulation's length unit. Any sequence of three-number rows,
        including an (n, 3) array.

    Returns
    -------
    str
        The file's text, newline separated and newline terminated.

    Raises
    ------
    CommandArgumentError
        If there is no point, a row is not three coordinates, or a
        coordinate is not a finite number. Each names the point.

    Examples
    --------
    >>> from pyflightstream.script import helpers
    >>> print(helpers.render_wake_edge_node_file([(1.0, -3.75, 0.0)]), end="")
    1
    0,0,0
    1.0,-3.75,0.0
    """
    rows = list(midpoints)
    if not rows:
        raise CommandArgumentError(
            f"{WAKE_EDGE_IMPORT_ROUTE} node file: 0 edge mid-points were given, and the "
            "points are what name the edges to mark. With none the import marks nothing "
            "and says nothing, so the run would solve with no wake"
        )
    lines = [str(len(rows)), WAKE_EDGE_NODE_PLACEHOLDER]
    for position, row in enumerate(rows, start=1):
        where = f"point {position} of {len(rows)}"
        if isinstance(row, (str, bytes)):
            raise CommandArgumentError(
                f"{WAKE_EDGE_IMPORT_ROUTE} node file: {where} is {row!r}, a text and not "
                "three coordinates. Give each point as a sequence of three numbers, x, y "
                "and z, so that a string is never read character by character"
            )
        try:
            values = [float(value) for value in row]
        except (TypeError, ValueError, OverflowError) as error:
            raise CommandArgumentError(
                f"{WAKE_EDGE_IMPORT_ROUTE} node file: {where} is {row!r}, which is not "
                f"three coordinates ({error})"
            ) from error
        if len(values) != 3:
            raise CommandArgumentError(
                f"{WAKE_EDGE_IMPORT_ROUTE} node file: {where} holds {len(values)} values, "
                "and every point is three coordinates, x, y and z"
            )
        if not all(math.isfinite(value) for value in values):
            raise CommandArgumentError(
                f"{WAKE_EDGE_IMPORT_ROUTE} node file: {where} is {tuple(values)!r}, and a "
                "coordinate that is not a finite number would be written as a word, which "
                "makes the import mark nothing"
            )
        lines.append(",".join(plain_decimal(value) for value in values))
    return "\n".join(lines) + "\n"


# The command whose enumeration is the simulation's length-unit vocabulary,
# which is where the import's third token is drawn from, is
# `LENGTH_UNIT_COMMAND`, imported from its one home in the script root (AD-10).

#: The one build the file route was run on, and the report that ran it.
WAKE_EDGE_FILE_ROUTE_MEASURED_ON = "26.124"
WAKE_EDGE_FILE_ROUTE_REPORT = "RPT-061"


def _simulation_length_units(script: Script) -> tuple[str, ...]:
    """Return the length-unit tokens the script's database records, OTHER excluded.

    OTHER names no scale, so a node file converted to it would carry
    coordinates in nothing the package can state.
    """
    entry = script.registry.commands.get(LENGTH_UNIT_COMMAND)
    if entry is None:
        return ()
    for arg in entry.args:
        if arg.name == "units":
            return tuple(value for value in (arg.values or ()) if value != "OTHER")
    return ()


def _same_file(parked: str, path: str) -> bool:
    """Whether two paths a script parks are one file where the run writes them.

    A path through a parent folder (``sub/../x``) names the file the folded path
    names, and a path equal to another but for case is the same file on a
    case-insensitive file system, as on Windows, as is a name Windows reads as
    another's alias (a trailing dot or space); the run's writer holds every
    parked file to the same rule (run._pending._write_pending_files).
    """
    return one_file_key(parked) == one_file_key(path)


def _refuse_a_parked_file_of_the_other_kind(
    script: Script, path: str, *, writing: str, helper: str
) -> None:
    """Refuse a path the OTHER parked register already holds (PFS-2093.011).

    An action script and a data file are parked by different helpers, each of
    which checked only its own register, so the two could name one file and
    the run would write whichever came last.
    """
    held = script._parked_file(path)
    if held is None or held[0] == writing:
        return
    register, parked = held
    raise CommandArgumentError(
        f"{helper}: this script already writes an {register} to "
        f"{_where_parked(parked, path)}, and this call would write an {writing} "
        "there. One path is one file, so the second would silently replace the "
        "first. Give it a path of its own"
    )


def _where_parked(parked: str, path: str) -> str:
    """How a refusal names the parked file that ``path`` would replace."""
    if parked == path:
        return repr(path)
    if parked.casefold() == path.casefold():
        return (
            f"{parked!r}, which differs from {path!r} only in case: a case-insensitive "
            "file system reads the two as one file"
        )
    if parked.rstrip(". ").casefold() == path.rstrip(". ").casefold():
        return (
            f"{parked!r}, which differs from {path!r} only in a trailing dot or space: "
            "Windows reads the two names as one file"
        )
    return f"{parked!r}, which is the file {path!r} names through a parent folder: one file"
