"""The forms a command takes on the builds whose manual changed it (FR-423).

Pipeline role: emission helpers below the workflows and the probe catalog.
Each function here writes the one form the build the script targets
documents, where two builds document two forms of the same request, so a
caller states the request once and the script states the form.

THE EVERY-BOUNDARY DETECTIONS. The 26.125 edition of the manual (SRC-753)
stops printing ``AUTO_DETECT_TRAILING_EDGES``, ``AUTO_DETECT_BASE_REGIONS`` and
``AUTO_DETECT_WAKE_TERMINATION_NODES`` and documents, in their place, the -1
(every boundary) form of the three ``DETECT_*_BY_SURFACE`` commands
(SRC-753 pp.327, 329, 331). A build that carries the automatic command
emits it, so every script for 26.124 and earlier is byte-identical; a build
that does not emits the -1 form.

THE WAKE-EDGE IMPORT TOKEN. 26.124 was measured to require a third token on
``IMPORT_WAKE_EDGES_FROM_FILE`` and to read the node list from the next line
only after it (RPT-061); its manual printed two values. SRC-753 p.329 names
that token EDGE_TYPE, 1 for a file of edge mid-points and 2 for edge corner
nodes. The package's node file lists mid-points, so a build whose grammar
names the token gets 1, and a build whose grammar is the measured 26.124
form keeps the simulation's length unit it was measured with.

THE CCS CURVE ASSIGNMENT. SRC-753 asks for
``ASSIGN_SELECTED_CURVES_TO_CCS_<COMPONENT>`` before a CCS component gets a
control surface, a refinement zone or a trailing edge (pp.307, 311, 314).
No earlier edition prints it, so it is emitted only where the build
carries it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyflightstream._errors import PyflightstreamWarning, warn
from pyflightstream.script import CommandArgumentError

if TYPE_CHECKING:
    from pyflightstream.commands import VersionView
    from pyflightstream.script import Script

__all__ = [
    "assign_selected_ccs_curves",
    "detect_every_boundary",
    "every_boundary_detection",
    "solver_time_averaging",
    "takes_every_boundary",
    "wake_edge_import_token",
]

#: Every-boundary detection, by what it detects: the automatic command of the
#: builds up to 26.124, and the by-surface command whose -1 form SRC-753
#: documents in its place.
_DETECTIONS: dict[str, tuple[str, str]] = {
    "trailing_edges": ("AUTO_DETECT_TRAILING_EDGES", "DETECT_TRAILING_EDGES_BY_SURFACE"),
    "base_regions": ("AUTO_DETECT_BASE_REGIONS", "DETECT_BASE_REGIONS_BY_SURFACE"),
    "wake_termination_nodes": (
        "AUTO_DETECT_WAKE_TERMINATION_NODES",
        "DETECT_WAKE_TERMINATION_NODES_BY_SURFACE",
    ),
}

#: The index the by-surface detections read as every boundary (SRC-753
#: pp.327, 329, 331).
EVERY_BOUNDARY = -1

#: The EDGE_TYPE token of a node file listing edge mid-points (SRC-753 p.329),
#: which is the file the package writes.
MIDPOINT_EDGE_TYPE = "1"

#: The CCS curve assignment, by the component kind the CCS builders name.
_CCS_ASSIGNMENT: dict[str, str] = {
    "wing": "ASSIGN_SELECTED_CURVES_TO_CCS_WING",
    "fuselage": "ASSIGN_SELECTED_CURVES_TO_CCS_FUSELAGE",
    "revolution": "ASSIGN_SELECTED_CURVES_TO_CCS_REVOLVE_BODY",
}


def every_boundary_detection(script: Script, kind: str) -> tuple[str, tuple[int, ...]]:
    """Return the command and arguments that detect ``kind`` on every boundary.

    Parameters
    ----------
    script : Script
        The script whose build decides the form.
    kind : str
        ``"trailing_edges"``, ``"base_regions"`` or ``"wake_termination_nodes"``.

    Returns
    -------
    tuple of (str, tuple of int)
        The automatic command with no argument where the build carries it,
        else the by-surface command with the every-boundary index.

    Raises
    ------
    KeyError
        If ``kind`` is not one of the three detections.
    """
    automatic, by_surface = _DETECTIONS[kind]
    if automatic in script._view or not takes_every_boundary(script._view, by_surface):
        # A build with neither form is refused by the emitter, naming the
        # automatic command, as it always was.
        return automatic, ()
    return by_surface, (EVERY_BOUNDARY,)


def takes_every_boundary(view: VersionView, command: str) -> bool:
    """Say whether a build's grammar of a by-surface detection takes the -1 form.

    Parameters
    ----------
    view : VersionView
        The command database's view of one build.
    command : str
        A ``DETECT_*_BY_SURFACE`` command.

    Returns
    -------
    bool
        True where the build carries the command and its grammar takes the
        every-boundary index or omits the index list (26.125); False on the
        builds whose by-surface detection names its surfaces only.
    """
    if command not in view:
        return False
    args = view[command].args
    return any(arg.all_sentinel == EVERY_BOUNDARY or not arg.required for arg in args)


def detect_every_boundary(script: Script, kind: str) -> str:
    """Emit the every-boundary detection of ``kind`` in the build's form.

    Parameters
    ----------
    script : Script
        The script being built.
    kind : str
        ``"trailing_edges"``, ``"base_regions"`` or ``"wake_termination_nodes"``.

    Returns
    -------
    str
        The command emitted.

    Examples
    --------
    >>> from pyflightstream.script import Script
    >>> old, new = Script(version="26.124"), Script(version="26.125")
    >>> detect_every_boundary(old, "trailing_edges"), detect_every_boundary(new, "trailing_edges")
    ('AUTO_DETECT_TRAILING_EDGES', 'DETECT_TRAILING_EDGES_BY_SURFACE')
    >>> print(new.render().strip())
    DETECT_TRAILING_EDGES_BY_SURFACE
    SURFACES -1
    """
    command, arguments = every_boundary_detection(script, kind)
    script.emit(command, *arguments)
    return command


def wake_edge_import_token(script: Script, units: str) -> str:
    """Return the third token of the wake-edge import on the script's build.

    Parameters
    ----------
    script : Script
        The script whose build decides the token.
    units : str
        The simulation's length unit, the token 26.124 was measured with.

    Returns
    -------
    str
        :data:`MIDPOINT_EDGE_TYPE` where the build's grammar names the
        EDGE_TYPE token (26.125), else ``units``.
    """
    grammar = script._view["IMPORT_WAKE_EDGES_FROM_FILE"]
    if any(arg.name == "edge_type" for arg in grammar.args):
        return MIDPOINT_EDGE_TYPE
    return units


def solver_time_averaging(script: Script, window: tuple[int, int]) -> None:
    """Emit ``ENABLE_SOLVER_TIME_AVERAGING`` over a window of time iterations.

    The command it replaces, ``SOLVER_TIME_AVERAGING``, hung the 26.124 solver
    (C01). This one is a different command of a different build and no run
    has measured it, so on a build where it is documented and not verified
    the line is written and a warning says so, naming the remedy.

    Parameters
    ----------
    script : Script
        The script being built.
    window : tuple of (int, int)
        The first and the last time iteration of the average, both counted
        from 1 in the solver's own time steps (SRC-753 p.360).

    Raises
    ------
    CommandArgumentError
        If the window is not two positive integers in order.
    """
    first, last = window
    if not (0 < first <= last):
        raise CommandArgumentError(
            f"solver_time_averaging = [{first}, {last}] is not a window: state the first "
            "and the last time iteration of the average, both positive, the first not "
            "after the last"
        )
    command = "ENABLE_SOLVER_TIME_AVERAGING"
    script.emit(command, first, last)
    record = script.registry.commands[command].status_in(script.version)
    if record is not None and str(record.status) != "verified":
        warn(
            f"solver_time_averaging: {command} is documented on FlightStream "
            f"{script.version.canonical} and no run has verified it, and the command it "
            "replaces hung the 26.124 solver. Run the 26.125 probe campaign before relying "
            "on it, or average with the pproc [time_averaging] table instead",
            PyflightstreamWarning,
            stacklevel=2,
        )


def assign_selected_ccs_curves(script: Script, kind: str) -> str | None:
    """Emit the CCS curve assignment of ``kind`` where the build carries it.

    Parameters
    ----------
    script : Script
        The script being built, after its curves were selected.
    kind : str
        ``"wing"``, ``"fuselage"`` or ``"revolution"``.

    Returns
    -------
    str or None
        The command emitted, or None on a build that does not carry it.
    """
    command = _CCS_ASSIGNMENT[kind]
    if command not in script._view:
        return None
    script.emit(command)
    return command
