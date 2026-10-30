"""Scoped pre-initialization marking for the raw FSI import route."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import contextmanager
from os import PathLike, fspath
from typing import Protocol, cast

from pyflightstream.commands import CommandNotInVersionError
from pyflightstream.script import (
    LENGTH_UNIT_COMMAND,
    CommandArgumentError,
    Script,
    ScriptOrderError,
)
from pyflightstream.script._build_forms import wake_edge_import_token
from pyflightstream.script._wake_edge_file import (
    WAKE_EDGE_ANGLE_ROUTE,
    WAKE_EDGE_FILE_ROUTE_MEASURED_ON,
    WAKE_EDGE_FILE_ROUTE_REPORT,
    WAKE_EDGE_IMPORT_ROUTE,
    _refuse_a_parked_file_of_the_other_kind,
    _same_file,
    _simulation_length_units,
    _where_parked,
    render_wake_edge_node_file,
)


class _MarkingPolicy(Protocol):
    _marking_only: bool


def require_marking_build(script: Script) -> None:
    """Refuse a build whose FSI marking order is neither measured nor carried (FR-3402)."""
    if script.version.canonical not in {"26.124", "26.125", "26.126"}:
        raise ScriptOrderError(
            "the FSI marking order is supported on 26.124, 26.125 and 26.126 (measured on "
            f"the first two, carried to 26.126); this script targets {script.version.canonical}"
        )


def marking_only(script: Script) -> Script:
    """Return ``script`` as a marking-only script, after refusing an unsupported build."""
    require_marking_build(script)
    cast(_MarkingPolicy, script)._marking_only = True
    return script


@contextmanager
def marking_import(script: Script):
    """Scope B1's measured marking phase to a fresh FSI import before initialization."""
    require_marking_build(script)
    if script._initialized_at is not None:
        raise ScriptOrderError("FSI marking requires a fresh import before initialization")
    previous = getattr(script, "_marking_only", False)
    policy = cast(_MarkingPolicy, script)
    policy._marking_only = True
    try:
        yield
    finally:
        policy._marking_only = previous


def mark_wake_edges(
    script: Script,
    *,
    edge_type: str,
    tolerance: float,
    units: str,
    node_file: str | PathLike[str],
    midpoints: Sequence[Sequence[float]],
) -> str:
    """Mark trailing edges from a file of edge mid-points, not by angle.

    Emits the import route INSTEAD of the angle criterion, which is what
    the route is for: auto detection marks an edge because the surface
    creases there, and a strongly twisted blade has a trailing edge that
    is not a crease. The file marks exactly the edges it names, since
    initialisation does not add the ones detection would find (RPT-065),
    so this replaces rather than runs beside.

    THE FORM IS THE ONE 26.124 READS (RPT-061):
    ``IMPORT_WAKE_EDGES_FROM_FILE <TYPE> <TOLERANCE> <UNITS>`` with the
    node file's path on the next line. The manual prints a two-value line,
    which that build refuses as a syntax error, and the path is read only
    when the line carries a third token. The third token is required and
    had no measured effect on 26.124; that build receives the simulation's
    length unit. On 26.125 the third token is EDGE_TYPE 1 for mid-points
    (FSM-26.125 p.329). :mod:`pyflightstream.script._build_forms` selects the form.
    The node file's text is parked on the script
    (:attr:`~pyflightstream.script.Script.pending_input_files`) and the
    run writes it before the solver starts, and the number of points is
    recorded (:attr:`~pyflightstream.script.Script.wake_edge_points`) so
    the run can compare it with the count the solver logs as imported.

    Parameters
    ----------
    script : Script
        Script under construction.
    edge_type : str
        Edge type applied to every edge the import matches: the same
        four values SET_TRAILING_EDGE_TYPE takes, so this sets for a
        whole imported file what that command sets for one edge.
    tolerance : float
        Maximum distance between a mesh edge mid-point and an imported
        point for the two to count as the same edge, in the simulation's
        own length units.
    units : str
        The length unit of ``midpoints``, a token of
        SET_SIMULATION_LENGTH_UNITS other than OTHER. The solver reads the
        file in the simulation's unit and reads no unit from it, so where
        the script knows that unit
        (:attr:`~pyflightstream.script.Script.simulation_length_unit`) and
        it differs, the points are converted into it (PFS-2104.027); where
        the script does not know it, ``units`` is taken to be the simulation's
        unit. The third token follows the build-specific form described above.
    node_file : str or path-like
        Where the node file is written and read, the path the command's
        next line names.
    midpoints : sequence of (x, y, z)
        The mid-points of the mesh edges to mark, in ``units``. See
        :func:`render_wake_edge_node_file`. ``tolerance`` is in the
        simulation's unit whatever ``units`` says.

    Returns
    -------
    str
        The command emitted, for a run record that has to name the route
        it took.

    Raises
    ------
    CommandNotInVersionError
        If the build does not document the import route, or documents
        only the two-value line (26.122, 26.123), which has not been run
        and which 26.124 refuses. The message names the build and the
        angle criterion this library will NOT substitute unasked: a
        campaign that silently fell back would mark a twisted blade by an
        angle criterion and report nothing about it.
    CommandArgumentError
        If ``units`` is not a length unit with a scale, if the points
        cannot make a node file (see :func:`render_wake_edge_node_file`),
        or if this script already writes different text to ``node_file``.
        Every refusal leaves the script untouched.

    Notes
    -----
    NEITHER THE TYPE NOR THE TOLERANCE HAS A DEFAULT HERE, deliberately.
    The vendor's own defaults live one layer up, on
    :class:`~pyflightstream.workspace.wake_edges.WakeEdgeImport`,
    together with the refusals a grammatically perfect call still needs.

    Two calls on one script import two files, and
    :attr:`~pyflightstream.script.Script.wake_edge_points` is their sum,
    since the solver logs one imported count per import.

    Examples
    --------
    >>> from pyflightstream.script import Script, helpers
    >>> script = Script(version="26.124")
    >>> helpers.mark_wake_edges(
    ...     script,
    ...     edge_type="STANDARD",
    ...     tolerance=0.0001,
    ...     units="METER",
    ...     node_file="wing.wake_nodes.txt",
    ...     midpoints=[(1.0, -3.75, 0.0), (1.0, -3.25, 0.0)],
    ... )
    'IMPORT_WAKE_EDGES_FROM_FILE'
    >>> print(script.render().strip())
    IMPORT_WAKE_EDGES_FROM_FILE STANDARD 0.0001 METER
    wing.wake_nodes.txt
    >>> script.wake_edge_points
    2
    """
    try:
        grammar = script._view[WAKE_EDGE_IMPORT_ROUTE]
    except CommandNotInVersionError as error:
        raise CommandNotInVersionError(
            f"mark_wake_edges: FlightStream {script.version.canonical} does not carry "
            f"{WAKE_EDGE_IMPORT_ROUTE}, the route this campaign marks its trailing "
            f"edges by, and this library will not fall back to {WAKE_EDGE_ANGLE_ROUTE} "
            "for you. That route marks an edge where the surface creases, which is "
            "the criterion an imported node list exists to replace on a blade whose "
            "trailing edge is not a crease, so substituting it would change the "
            f"physics in silence. Run this case on a build that documents "
            f"{WAKE_EDGE_IMPORT_ROUTE}, or ask for the angle criterion deliberately. "
            f"The database says: {error}"
        ) from error
    if not any(arg.name == "file" for arg in grammar.args):
        raise CommandNotInVersionError(
            f"mark_wake_edges: FlightStream {script.version.canonical} documents "
            f"{WAKE_EDGE_IMPORT_ROUTE} only as the two-value line its manual prints, "
            "with no node file, and that route was measured on "
            f"{WAKE_EDGE_FILE_ROUTE_MEASURED_ON} only ({WAKE_EDGE_FILE_ROUTE_REPORT}), "
            "where the two-value line is a syntax error that stops the script and the "
            "file is read only from the line after a third token. Nothing has been "
            f"run on {script.version.canonical}, so no form is emitted for it. Run the "
            f"case on {WAKE_EDGE_FILE_ROUTE_MEASURED_ON}, or mark the trailing edges by "
            f"detection ({WAKE_EDGE_ANGLE_ROUTE}) deliberately"
        )
    known = _simulation_length_units(script)
    if units not in known:
        raise CommandArgumentError(
            f"mark_wake_edges: units is {units!r}; declare the midpoints' length unit "
            f"using one of the {LENGTH_UNIT_COMMAND} tokens with a "
            f"scale: {', '.join(known)}. The solver reads the node file in the "
            "simulation's unit and reads no unit from the file; the helper converts "
            "the points when the script records a different simulation unit"
        )
    text = render_wake_edge_node_file(midpoints)
    simulation = script.simulation_length_unit
    if simulation is not None and simulation != units:
        # THE SOLVER READS THE FILE IN THE SIMULATION'S UNIT (PFS-2104.027), so
        # points stated in another are converted, and that unit is the one
        # written: a METER file under a MILLIMETER simulation marked edges a
        # thousand times too close to the origin, in silence.
        from pyflightstream._lengths import scale

        factor = scale(units, simulation)
        if factor is None:
            raise CommandArgumentError(
                f"mark_wake_edges: the points are in {units} and this script's "
                f"simulation length unit is {simulation}, which names no scale, so the "
                "points cannot be stated in it. Set a simulation length unit with a scale"
            )
        midpoints = [[float(value) * factor for value in row] for row in midpoints]
        text = render_wake_edge_node_file(midpoints)
        units = simulation
    path = fspath(node_file)
    # A path equal to a parked one but for case is the same file on a
    # case-insensitive file system (Windows), so it is held to the same rule,
    # as actuator_disc holds a profile.
    for parked, already in script._pending_input_files.items():
        if not _same_file(parked, path) or already == text:
            continue
        where = _where_parked(parked, path)
        raise CommandArgumentError(
            f"mark_wake_edges: this script already writes a different node file to "
            f"{where}. One path is one file, so the second would silently replace "
            "the first and both import lines would read whichever text won. Give "
            "this import a node file of its own"
        )
    _refuse_a_parked_file_of_the_other_kind(
        script, path, writing="input file", helper="mark_wake_edges"
    )

    # Emit, then park, then record: a build or an argument the emitter
    # refuses leaves no file parked and no count recorded.
    # The third token is the unit on 26.124 and EDGE_TYPE 1 (mid-points) on 26.125.
    script.emit(
        WAKE_EDGE_IMPORT_ROUTE, edge_type, tolerance, wake_edge_import_token(script, units), path
    )
    script._pending_input_files[path] = text
    # The count is the file's own first line, so the number recorded is
    # the number written.
    points = int(text.split(maxsplit=1)[0])
    script.wake_edge_points = (script.wake_edge_points or 0) + points
    return WAKE_EDGE_IMPORT_ROUTE
