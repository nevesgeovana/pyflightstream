"""Wake-edge marking inputs, staged in the workspace.

Pipeline role: workspace layer. A campaign that marks its trailing
edges from an imported node list needs three things the emitter cannot
supply and cannot check: the nodes themselves, the edge type the marked
edges take, and the distance within which an imported coordinate counts
as sitting on a mesh edge. This module holds those three, refuses a
combination that can mark nothing, and states the evidence the choice
rests on.

WHY THE REFUSALS LIVE HERE AND NOT IN THE EMITTER. The emitter checks
grammar, and every combination this module refuses is grammatically
perfect: an empty node list is a file with no rows, and a tolerance of
zero is a real number in the right position. The solver then marks
nothing and reports nothing, and the campaign runs to completion with
no wake where the wake was the point. A check that can only run before
the script is written has to live above the script layer, which is
here.

THE DEFAULT ROUTE WAS RUN ON ONE BUILD, and that is stated rather than
left for a reader to discover. Marking wake edges from a file replaces
trailing-edge auto detection, which is an angle criterion and cannot
find the edges this capability exists for; that is the reason for the
trade and it is a good one. The import was run on 26.124 only
(RPT-061), where it reads its node list from the path on the line after
the command and marks the edges whose mid-points the file names; the
builds before it print a grammar that build refuses. :func:`evidence_notice`
renders the standing from the command database at the moment it is
asked, so the day a compat report promotes the import the sentence
follows it, and a reader meeting the default never reads it as settled
practice.

THE NODE FILE IS WHAT 26.124 READS (RPT-061): the count, one coordinate
line the solver consumes and does not use, then the edge MID-POINTS in
the simulation's length unit. The file's unit is not read, so
:func:`write_node_file` converts the points to the simulation's unit
rather than declaring one, and the text itself comes from
:func:`pyflightstream.script.helpers.render_wake_edge_node_file`, the
one place that layout is written.

The two defaults are the vendor's own numbers rather than this
package's taste: the manual page prints a sample call passing
VORTEX_SHEDDING and 0.0001, and states the same number as the parameter
default in its own table (FSM-26.122 p.324, FSM-26.123 p.323).
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from fractions import Fraction
from pathlib import Path
from typing import Any, NamedTuple

import numpy
from pydantic import BaseModel, ConfigDict, model_validator

import pyflightstream._textio as _textio
from pyflightstream._decimal import plain_decimal
from pyflightstream._errors import PyflightstreamWarning, warn
from pyflightstream._fsm import MeshReadError, saved_mesh_coordinate_unit, trailing_edge_midpoints
from pyflightstream._lengths import METRES_PER_UNIT, scale
from pyflightstream._mesh import read_mesh
from pyflightstream.cases.mesh import TrailingEdgeMarking, WakeTerminationMarking
from pyflightstream.commands import CommandRegistry, Status
from pyflightstream.script import LENGTH_UNIT_COMMAND, CommandArgumentError
from pyflightstream.script.helpers import render_wake_edge_node_file
from pyflightstream.workspace.inputs import InputArtifactError, PointXyz
from pyflightstream.workspace.manifest import RunStatus

__all__ = [
    "DEFAULT_TOLERANCE",
    "LENGTH_UNIT_COMMAND",
    "TRAILING_EDGE_DETECTION_COMMAND",
    "WAKE_EDGE_IMPORT_COMMAND",
    "TrailingEdgePoints",
    "WakeEdgeImport",
    "matched_trailing_edge_points",
    "saved_wake_edge_verdict",
    "edge_types",
    "evidence_notice",
    "length_scale",
    "node_file_units",
    "read_trailing_edge_points",
    "tolerance_unit",
    "write_node_file",
    "write_trailing_edge_points",
    "write_trailing_edge_midnodes",
    "write_trailing_edge_midnodes_per_family",
    "write_trailing_edges_identified",
    "write_trailing_edge_points_from_nodes",
]

#: The command this module's inputs are assembled for.
WAKE_EDGE_IMPORT_COMMAND = "IMPORT_WAKE_EDGES_FROM_FILE"

#: What the import replaces: the angle criterion that marks trailing
#: edges without being told where they are.
TRAILING_EDGE_DETECTION_COMMAND = "AUTO_DETECT_TRAILING_EDGES"

#: The tolerance the manual's parameter table states as the default and
#: the printed sample call passes (FSM-26.122 p.324, FSM-26.123 p.323). It is
#: recorded here rather than invented, so nobody has to reverse engineer
#: where it came from.
DEFAULT_TOLERANCE = 0.0001


def saved_wake_edge_verdict(sets, folder: Path, collected: Sequence[str], build: str):
    """Compare the marked saved mesh with every declared set in physical metres.

    Parameters
    ----------
    sets : sequence of mappings
        Declared edge points, tolerances and source files.
    folder : Path
        Folder containing the collected saved simulation.
    collected : sequence of str
        Collected output names, including exactly one saved simulation.
    build : str
        Solver build associated with the marking pass.

    Returns
    -------
    tuple or None
        Failure status and diagnosis, or None when every declared point is marked.
    """
    saves = [folder / name for name in collected if Path(name).suffix.lower() == ".fsm"]
    if len(saves) != 1:
        return (
            RunStatus.FAILED_INCOMPLETE_OUTPUT,
            "multiple wake-edge imports are checked on the saved simulation, and the run "
            f"collected {len(saves)} .fsm files; list exactly one saved simulation (.fsm) "
            "among the row's outputs",
        )
    try:
        unit = saved_mesh_coordinate_unit(saves[0])
        factor = None if unit is None else scale(unit, "METER")
        if factor is None:
            raise MeshReadError("saved mesh coordinate unit is unknown")
        marked = (
            numpy.asarray(trailing_edge_midpoints(saves[0]), dtype=float).reshape(-1, 3) * factor
        )
    except (OSError, ValueError, MeshReadError) as exc:
        return RunStatus.FAILED_INCOMPLETE_OUTPUT, f"cannot check saved trailing-edge sets: {exc}"
    missing, present, total = [], 0, 0
    for entry in sets:
        found = 0
        for point in entry["points_m"]:
            found += bool(
                len(marked)
                and numpy.any(numpy.linalg.norm(marked - point, axis=1) <= entry["tolerance"])
            )
        total += len(entry["points_m"])
        present += found
        if found < len(entry["points_m"]):
            missing.append(entry["file"])
    if missing:
        return RunStatus.FAILED_SCRIPT, (
            f"the saved simulation marks {present} of {total} trailing-edge points; the edges of "
            f"{', '.join(missing)} are missing, which is what a second wake-edge import replacing "
            f"the first would leave (unmeasured on {build}, PFS-2149.01)"
        )
    return None


def tolerance_unit() -> str:
    """Return the unit the command database records for the tolerance.

    READ FROM THE RECORD, never written here. The unit is DERIVED and
    printed nowhere in the manual: the page describes a distance between
    a mesh edge mid-point and an imported node coordinate, and both are
    expressed in the simulation's own length unit, so the tolerance can
    be in no other. That reading belongs to the command entry, which is
    where its citation lives, and a constant here would be a second copy
    that could disagree with it.

    Returns
    -------
    str
        The declared unit of the import's ``tolerance`` argument, or the
        empty string if the record states none.

    Examples
    --------
    >>> from pyflightstream.workspace.wake_edges import tolerance_unit
    >>> tolerance_unit()
    'simulation length units'
    """
    entry = CommandRegistry.load().commands[WAKE_EDGE_IMPORT_COMMAND]
    for arg in entry.args:
        if arg.name == "tolerance":
            return arg.unit or ""
    return ""


def edge_types() -> tuple[str, ...]:
    """Return the edge types the command database records for the import.

    Read from the command record on every call rather than copied into a
    constant. The set is per version in the database, and a constant
    here would be a second copy that cannot follow a build.

    Returns
    -------
    tuple of str
        The declared values of the import's ``type`` argument, in the
        order the manual page prints them.

    Examples
    --------
    >>> from pyflightstream.workspace.wake_edges import edge_types
    >>> "VORTEX_SHEDDING" in edge_types()
    True
    """
    entry = CommandRegistry.load().commands[WAKE_EDGE_IMPORT_COMMAND]
    for arg in entry.args:
        if arg.name == "type":
            return tuple(arg.values or ())
    return ()


def _verified_builds(command: str) -> tuple[str, ...]:
    """Canonical builds on which a command carries a row of status verified."""
    entry = CommandRegistry.load().commands[command]
    return tuple(
        sorted(
            canonical for canonical, row in entry.versions.items() if row.status is Status.VERIFIED
        )
    )


#: A narrative report id, as a row's note cites the run behind a grammar.
_REPORT_ID = re.compile(r"\bRPT-\d{3}\b")


def _runs_in_notes(command: str) -> dict[str, tuple[str, ...]]:
    """Return the report ids each build's own note cites, where it cites one.

    A row whose grammar was settled by a run outside the compatibility
    harness keeps its documented status and names the run in its note, so
    the note is where that evidence is read from.
    """
    entry = CommandRegistry.load().commands[command]
    found = {
        canonical: tuple(sorted(set(_REPORT_ID.findall(row.note or ""))))
        for canonical, row in entry.versions.items()
    }
    return {canonical: ids for canonical, ids in sorted(found.items()) if ids}


def _reports_for(command: str) -> tuple[str, ...]:
    """Every committed report a command's own rows cite, sorted and unique."""
    entry = CommandRegistry.load().commands[command]
    cited = {row.report for row in entry.versions.values() if row.report}
    cited |= {row.probe_ref for row in entry.versions.values() if row.probe_ref}
    return tuple(sorted(cited))


def evidence_notice(canonical: str) -> str:
    """State the evidence behind the imported-node route, for one build.

    The sentence names both commands, the build it is about, and which
    builds the replaced command was actually run on. It is derived from
    the command database at call time, so a probe that promotes the
    import moves the sentence in the same commit that writes the row,
    and a report id appears here as soon as one is cited.

    Parameters
    ----------
    canonical : str
        Canonical build identifier, for example ``"26.123"``. Used in
        the rendered sentence only; nothing is resolved against the
        version registry, because the notice is about the two commands
        rather than about the build.

    Returns
    -------
    str
        One paragraph, ready to be printed beside the emitted script or
        carried in a run record.

    Examples
    --------
    >>> from pyflightstream.workspace.wake_edges import evidence_notice
    >>> "IMPORT_WAKE_EDGES_FROM_FILE" in evidence_notice("26.123")
    True
    """
    import_reports = _reports_for(WAKE_EDGE_IMPORT_COMMAND)
    detection_verified = _verified_builds(TRAILING_EDGE_DETECTION_COMMAND)

    runs = _runs_in_notes(WAKE_EDGE_IMPORT_COMMAND)
    import_verified = _verified_builds(WAKE_EDGE_IMPORT_COMMAND)
    if import_reports:
        # A REPORT PROMOTES A BUILD, NOT THE COMMAND: the sentence names the
        # builds it is verified on and says so when this build is not one.
        standing = "cites a probe report on this database: " + ", ".join(import_reports)
        if import_verified:
            standing += ", verified on " + ", ".join(import_verified)
            if canonical not in import_verified:
                standing += f" and not on {canonical}"
    elif runs:
        # A GRAMMAR SETTLED BY A RUN IS NOT A STATUS PROMOTED BY ONE. The
        # 26.124 row states the form that build reads because RPT-061 ran it,
        # and it is still documented, because only a compat report promotes.
        # The sentence says both halves, so neither reads as the other.
        measured = "; ".join(f"{build} by {', '.join(ids)}" for build, ids in runs.items())
        standing = (
            "cites no compat report on any build and is verified on none, its grammar "
            f"having been measured by a run outside the compatibility harness on {measured}"
        )
    else:
        # Compat rows name this command as unprobed when no probe specification
        # exists. The refusal concerns the absence of a cited report.
        standing = "cites no probe report on any build, every row it has being read off a page"

    if detection_verified:
        replaced = (
            f"{TRAILING_EDGE_DETECTION_COMMAND} was run and recorded verified on "
            + ", ".join(detection_verified)
        )
    else:
        replaced = f"{TRAILING_EDGE_DETECTION_COMMAND} carries no verified row either"

    weaker = (
        "It is stated so the default is read with its evidence"
        if canonical in import_verified
        else "It is stated because it is a move to weaker evidence"
    )
    return (
        f"Trailing edges are marked on FlightStream {canonical} through "
        f"{WAKE_EDGE_IMPORT_COMMAND}, which {standing}, in place of "
        f"{TRAILING_EDGE_DETECTION_COMMAND}. The trade is deliberate and the "
        f"reason is physical: auto detection is an angle criterion and cannot "
        f"find an edge that is not a geometric crease, which is exactly the "
        f"edge an imported node list exists to mark. {weaker}: {replaced}."
    )


class WakeEdgeImport(BaseModel):
    """The inputs one wake-edge marking pass takes.

    Attributes
    ----------
    nodes : tuple of PointXyz
        Node coordinates that name the edges to mark, in the simulation
        geometry reference frame, m. At least one; an empty list marks
        nothing and the solver says nothing about it.
    edge_type : str
        Edge type applied to every edge the import matches, one of
        :func:`edge_types`. Required, with no default: ``VORTEX_SHEDDING``
        and ``STANDARD`` mark different edges, so the caller says which.
    tolerance : float
        Maximum distance between the mid-point of a mesh edge and an
        imported node coordinate for the two to be treated as the same
        edge, in the unit :func:`tolerance_unit` reports. Positive and
        finite. Defaults to :data:`DEFAULT_TOLERANCE`, which the manual
        page states as the parameter's own default.

    Examples
    --------
    >>> from pyflightstream.workspace.inputs import PointXyz
    >>> from pyflightstream.workspace.wake_edges import WakeEdgeImport
    >>> settings = WakeEdgeImport(
    ...     nodes=(PointXyz(x_m=1.0, y_m=0.0, z_m=0.0),), edge_type="VORTEX_SHEDDING"
    ... )
    >>> settings.edge_type, settings.tolerance
    ('VORTEX_SHEDDING', 0.0001)
    """

    model_config = ConfigDict(extra="forbid")

    nodes: tuple[PointXyz, ...] = ()
    edge_type: str
    tolerance: float = DEFAULT_TOLERANCE

    @model_validator(mode="before")
    @classmethod
    def _the_edge_type_is_stated(cls, data: object) -> object:
        if isinstance(data, Mapping) and "edge_type" not in data:
            raise InputArtifactError(
                f"{WAKE_EDGE_IMPORT_COMMAND} was given no edge type, and it has no "
                "default: VORTEX_SHEDDING and STANDARD mark different edges. State one of "
                f"{', '.join(edge_types())}",
                kind="wake_edges",
            )
        return data

    @model_validator(mode="after")
    def _the_inputs_can_mark_something(self) -> WakeEdgeImport:
        if not self.nodes:
            raise InputArtifactError(
                f"{WAKE_EDGE_IMPORT_COMMAND} was given {len(self.nodes)} node "
                "coordinates, and the imported node list is what names the edges to "
                "mark. With none the solver marks nothing and reports nothing, so "
                "the run completes with no wake where the wake was the point",
                kind="wake_edges",
            )
        if not math.isfinite(self.tolerance) or self.tolerance <= 0.0:
            raise InputArtifactError(
                f"{WAKE_EDGE_IMPORT_COMMAND} was given a tolerance of "
                f"{self.tolerance!r} {tolerance_unit()}, and the tolerance is the "
                "distance within which a mesh edge mid-point counts as the imported "
                "node coordinate. It must be positive and finite: zero matches only "
                "on exact floating-point equality and so matches nothing, and a "
                "negative, infinite or undefined distance makes the mid-point test "
                f"meaningless. The manual's own default is {DEFAULT_TOLERANCE}",
                kind="wake_edges",
            )
        declared = edge_types()
        if self.edge_type not in declared:
            raise InputArtifactError(
                f"{WAKE_EDGE_IMPORT_COMMAND} was given edge type "
                f"{self.edge_type!r}, which the command database does not record "
                f"for it. The recorded types are: {', '.join(declared)}",
                kind="wake_edges",
            )
        return self

    def evidence_notice(self, canonical: str) -> str:
        """Return :func:`evidence_notice` for one build.

        Offered on the model so a caller holding the settings can print
        the notice at the moment it emits, without importing the module
        function separately. One implementation, delegated to.

        Parameters
        ----------
        canonical : str
            Canonical build identifier, for example ``"26.123"``.

        Returns
        -------
        str
            The paragraph :func:`evidence_notice` renders.
        """
        return evidence_notice(canonical)


# LENGTH_UNIT_COMMAND, the command whose enumeration is the simulation's
# length-unit vocabulary, is imported from its one home in the script root
# (AD-10) and stays in this module's __all__. The solver reads the node file's
# coordinates in the SIMULATION's unit and reads no unit from the file
# (RPT-061), so points given in another unit are converted, and both units
# have to be tokens of the solver's vocabulary and not of this package's taste.

#: Metres in one of each length unit the solver records, exact as decimals.
#: OTHER is absent on purpose: it names no scale, so nothing can be
#: converted to or from it. Every other recorded token has an entry, which
#: ``tests/tier1_offline/test_wake_edges.py`` holds against the record. The
#: table is the floor's (:mod:`pyflightstream._lengths`), which
#: the cases layer converts the actuator disc and the volume section with.
_METRES_PER_UNIT: Mapping[str, Fraction] = METRES_PER_UNIT


def length_scale(from_unit: str, to_unit: str) -> float:
    """Return the factor that turns a length in ``from_unit`` into ``to_unit``.

    The ratio is taken exactly and rounded once, so a millimetre-to-metre
    conversion multiplies by the float nearest 0.001 and a metre-to-metre
    one by exactly 1.0.

    Parameters
    ----------
    from_unit, to_unit : str
        Tokens of :func:`node_file_units` other than ``OTHER``.

    Returns
    -------
    float
        The factor to multiply a ``from_unit`` length by.

    Raises
    ------
    InputArtifactError
        If either token is ``OTHER``, which names no scale, or is not a
        recorded length unit.

    Examples
    --------
    >>> from pyflightstream.workspace.wake_edges import length_scale
    >>> length_scale("MILLIMETER", "METER")
    0.001
    """
    for unit in (from_unit, to_unit):
        if unit not in _METRES_PER_UNIT:
            scaled = ", ".join(u for u in node_file_units() if u in _METRES_PER_UNIT)
            reason = (
                "which names no scale, so nothing can be converted to or from it"
                if unit == "OTHER"
                else f"which the command database does not record for {LENGTH_UNIT_COMMAND}"
            )
            raise InputArtifactError(
                f"the length unit {unit!r} was given, {reason}. The units a length can be "
                f"converted between are: {scaled}",
                kind="wake_edges",
            )
    factor = scale(from_unit, to_unit)
    assert factor is not None  # both tokens were found in the table above
    return factor


def node_file_units() -> tuple[str, ...]:
    """Return the length-unit tokens the command database records.

    Read from the record on every call, for the same reason
    :func:`edge_types` is: a constant here would be a second copy that
    cannot follow a build.

    Returns
    -------
    tuple of str
        The declared values of the simulation length unit, in the order
        the manual page prints them.

    Examples
    --------
    >>> from pyflightstream.workspace.wake_edges import node_file_units
    >>> "METER" in node_file_units()
    True
    """
    entry = CommandRegistry.load().commands[LENGTH_UNIT_COMMAND]
    for arg in entry.args:
        if arg.name == "units":
            return tuple(arg.values or ())
    return ()


def _coordinates(nodes: object) -> numpy.ndarray:
    """Read an (n, 3) array of finite coordinates, at least one row, or refuse."""
    try:
        array = numpy.asarray(nodes, dtype=float)
    except (TypeError, ValueError) as error:
        # Wrap invalid numpy inputs, including strings, ragged lists and object
        # arrays, in the package's public refusal class (FR-39), naming the cause.
        raise InputArtifactError(
            "the node list could not be read as an array of coordinates: "
            f"{error}. It is an (n, 3) array of numbers, or any nested sequence "
            "numpy can read as one; a ragged list of rows and a list of strings are "
            "the two that usually arrive here",
            kind="wake_edges",
        ) from error
    if array.ndim != 2 or array.shape[1] != 3:
        raise InputArtifactError(
            f"the node list has shape {tuple(array.shape)}, and a node file carries one "
            "row of three coordinates per node, so the array is (n, 3). An (n, 2) array "
            "is usually a planar extraction that lost its third component, and a "
            "one-dimensional one is usually a flattened list",
            kind="wake_edges",
        )
    if array.shape[0] == 0:
        raise InputArtifactError(
            f"the node list carries {array.shape[0]} node coordinates, and the imported "
            "list is what names the edges to mark. With none the solver marks nothing "
            "and reports nothing, so the run completes with no wake where the wake was "
            "the point",
            kind="wake_edges",
        )
    finite = numpy.isfinite(array)
    if not finite.all():
        row = int(numpy.argmax(~finite.all(axis=1))) + 1
        raise InputArtifactError(
            f"the node list carries a coordinate that is not a finite number, first at "
            f"row {row} of {array.shape[0]}. It would be written into the file as a "
            "word, and the solver would read that word as a coordinate. A NaN here is "
            "usually an extraction that produced no intersection for one node",
            kind="wake_edges",
        )
    return array


def _refuse_an_existing_file(destination: Path, overwrite: bool) -> None:
    """Refuse to replace a file that exists unless asked to."""
    if destination.exists() and not overwrite:
        raise InputArtifactError(
            f"{destination} already exists. Pass overwrite=True to replace it "
            "deliberately, or write under a name that carries the geometry: one path is "
            "one file, so a second node list written here would silently win and both "
            "scripts citing it would import whichever ran last",
            kind="wake_edges",
        )


def write_trailing_edge_points(
    path: str | Path,
    points: object,
    *,
    unit: str,
    overwrite: bool = False,
) -> Path:
    """Write a trailing-edge points file: its unit, then one mid-point per line.

    The PACKAGE-SIDE file a geometry names for its trailing edge, which a
    user may also write by hand. It is not the file the solver reads: the
    run reads it, checks every point against the mesh, converts the points
    to the simulation's unit and writes the solver's node file from them
    (:func:`write_node_file`). So the unit is stated here, on the first
    line, where the solver's file carries none.

    Parameters
    ----------
    path : str or pathlib.Path
        Destination file.
    points : array_like
        The mid-points of the mesh edges on the trailing edge, shape (n, 3),
        in ``unit``.
    unit : str
        The unit the points are in, one of :func:`node_file_units` other
        than ``OTHER``, written alone on the first line.
    overwrite : bool
        Replace an existing destination.

    Returns
    -------
    pathlib.Path
        The file written.

    Raises
    ------
    InputArtifactError
        On the refusals of :func:`write_node_file`: no points, a shape
        other than (n, 3), a coordinate that is not finite, a unit with no
        scale, or an existing file without ``overwrite``. Each fires before
        the file is opened.

    Examples
    --------
    >>> from pyflightstream.workspace.wake_edges import write_trailing_edge_points
    >>> written = write_trailing_edge_points(
    ...     tmp_path / "wing.te.txt", [(1.0, -3.75, 0.0)], unit="METER"
    ... )  # doctest: +SKIP
    """
    destination = Path(path)
    array = _coordinates(points)
    length_scale(unit, unit)
    _refuse_an_existing_file(destination, overwrite)
    rows = [",".join(plain_decimal(float(value)) for value in point) for point in array]
    _textio.write_text(destination, "\n".join([unit, *rows]) + "\n")
    return destination


class TrailingEdgePoints(NamedTuple):
    """A trailing-edge points file as read.

    Attributes
    ----------
    unit : str
        The length unit its first line names.
    points : numpy.ndarray
        The points, shape (n, 3), in ``unit``, in file order.
    lines : tuple of int
        The 1-based file line each point was read from, so a refusal can
        name the line a user has to open.
    """

    unit: str
    points: numpy.ndarray
    lines: tuple[int, ...]


def _ansa_nodes(source: Path) -> numpy.ndarray:
    """Read five-column SET rows in listed order, with physical line diagnostics."""
    points = []
    seen: set[int] = set()
    number = 1
    for number, raw in enumerate(source.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        fields = [field.strip() for field in raw.split(",")]
        reason = "expected five fields: Id, Name, X, Y, Z"
        if len(fields) == 5:
            try:
                node = int(fields[0])
                xyz = [float(value) for value in fields[2:]]
            except ValueError:
                reason = "expected an integer node id and three finite coordinates"
            else:
                reason = "expected three finite coordinates"
                if node in seen:
                    reason = f"repeated node id {node}; list each node once"
                elif all(math.isfinite(value) for value in xyz):
                    seen.add(node)
                    points.append(xyz)
                    continue
        raise InputArtifactError(f"{source}: line {number}: {reason}", kind="wake_edges")
    if len(points) < 2:
        raise InputArtifactError(
            f"{source}: line {number}: fewer than two nodes; list at least two ordered nodes",
            kind="wake_edges",
        )
    return numpy.asarray(points, dtype=float)


def write_trailing_edge_points_from_nodes(
    source: str | Path, path: str | Path, *, unit: str = "METER", overwrite: bool = False
) -> Path:
    """Write edge mid-points from an ordered ANSA SET node-window export.

    Parameters
    ----------
    source : str or pathlib.Path
        Comma-separated Id, Name, X, Y, Z rows; blank and comment lines are ignored.
    path : str or pathlib.Path
        Destination points file. No mesh is needed.
    unit : str
        Length unit of the coordinates, preserved in the output.
    overwrite : bool
        Allow replacement of an existing destination.

    Returns
    -------
    pathlib.Path
        The written points file, with one midpoint per neighbouring pair in listed order.

    Raises
    ------
    InputArtifactError
        For fewer than two nodes, malformed rows, repeated ids or non-finite coordinates,
        naming the source line; also for an invalid unit or an existing output.
    OSError
        If the input cannot be read or the destination cannot be written.

    Notes
    -----
    Coordinates retain the input reference frame. Nodes are neither sorted nor joined
    by proximity: the supplied order defines the trailing-edge chain.
    """
    nodes = _ansa_nodes(Path(source))
    return write_trailing_edge_points(
        path, nodes[:-1] / 2 + nodes[1:] / 2, unit=unit, overwrite=overwrite
    )


#: A step this many times longer than a node's distance to its nearest node starts a
#: new line in a node list: along a line the next node is about one spacing away.
MIDNODE_GAP = 5.0


def write_trailing_edge_midnodes(
    source: str | Path, path: str | Path, *, unit: str = "METER", overwrite: bool = False
) -> Path:
    """Write the edge mid-points of an ANSA SET node-window export, in any node order.

    The nodes are put in order along their lines: from an end, each step goes
    to the nearest node left, and a step longer than :data:`MIDNODE_GAP` times
    the node's distance to its nearest node starts a new line, so one list may hold the
    trailing edges of every component. Each neighbouring pair gives one
    mid-point. No mesh is needed. A closed line loses the mid-point of its
    closing edge.

    Parameters
    ----------
    source : str or pathlib.Path
        Comma-separated Id, Name, X, Y, Z rows; blank and comment lines are ignored.
    path : str or pathlib.Path
        Destination points file.
    unit : str
        Length unit of the coordinates, written on the first line.
    overwrite : bool
        Allow replacement of an existing destination.

    Returns
    -------
    pathlib.Path
        The written points file.

    Raises
    ------
    InputArtifactError
        For fewer than two nodes, malformed rows, repeated ids or non-finite
        coordinates, naming the source line; also for an invalid unit or an
        existing output.
    """
    nodes = _ansa_nodes(Path(source))
    lines = _node_lines(nodes)
    alone = sum(len(line) == 1 for line in lines)
    if alone:
        warn(
            f"{source}: {alone} node(s) are far from every other and give no mid-point; "
            "list one continuous line of nodes per trailing edge",
            PyflightstreamWarning,
            stacklevel=2,
        )
    mids = [
        (nodes[a] + nodes[b]) / 2.0 for line in lines for a, b in zip(line, line[1:], strict=False)
    ]
    return write_trailing_edge_points(
        path, numpy.asarray(mids).reshape(-1, 3), unit=unit, overwrite=overwrite
    )


def write_trailing_edge_midnodes_per_family(
    source: str | Path,
    mesh: str | Path,
    path: str | Path,
    *,
    unit: str = "METER",
    overwrite: bool = False,
) -> list[Path]:
    """Write one points file per family of a mesh from an ANSA SET node list.

    Each listed node is matched to the mesh vertex within a quarter of that
    vertex's shortest edge, and every edge of a family joining two listed
    nodes gives its mid-point, so the points are the mesh's own. The files are
    named ``<path stem>.<family>.te.txt`` beside ``path``; a family no edge
    of the list lies on gets none, and a node that matches no vertex is
    warned and skipped.

    Parameters
    ----------
    source : str or pathlib.Path
        The node list saved from the SET (Id, Name, X, Y, Z), in any order.
    mesh : str or pathlib.Path
        The OBJ the nodes belong to, in the same unit as the list.
    path : str or pathlib.Path
        The points file the per-family names are built from.
    unit : str
        Length unit of the coordinates, written on each file's first line.
    overwrite : bool
        Allow replacement of existing destinations.

    Returns
    -------
    list of pathlib.Path
        The written points files, in the mesh's family order.

    Raises
    ------
    InputArtifactError
        For a list with no node read, a list that joins no edge of the mesh, an
        unreadable mesh, an invalid unit or an existing output.
    """
    from pyflightstream.workspace._refine._obj import perimeter_edges, read_node_list, read_obj

    nodes = read_node_list(source)
    if not nodes.ids:
        raise InputArtifactError(
            f"{source}: no node is read; save the SET's node window (Id, Name, X, Y, Z)",
            kind="wake_edges",
        )
    obj = read_obj(Path(mesh))
    found, unmatched = perimeter_edges(obj.verts, obj.families, nodes)
    if unmatched:
        shown = ", ".join(str(i) for i in unmatched[:5])
        warn(
            f"{source}: {len(unmatched)} of {len(nodes.ids)} node(s) match no vertex of {mesh} "
            f"and are skipped (ids {shown}{' and more' if len(unmatched) > 5 else ''}); the "
            "list and the OBJ must be saved from the same model, in the same unit",
            PyflightstreamWarning,
            stacklevel=2,
        )
    target = Path(path)
    stem = target.name[: -len(".te.txt")] if target.name.endswith(".te.txt") else target.stem
    written = []
    for name, edges in found.items():
        if not edges:
            continue
        pairs = numpy.array(sorted(edges), dtype=numpy.int64)
        mids = 0.5 * (obj.verts[pairs[:, 0]] + obj.verts[pairs[:, 1]])
        written.append(
            write_trailing_edge_points(
                target.with_name(f"{stem}.{name}.te.txt"), mids, unit=unit, overwrite=overwrite
            )
        )
    if not written:
        raise InputArtifactError(
            f"{source}: no edge of {mesh} joins two listed nodes; nothing was written",
            kind="wake_edges",
        )
    return written


def write_trailing_edges_identified(
    mesh: str | Path,
    source: str | Path | None = None,
    families: Sequence[str] | None = None,
    *,
    aft: Sequence[float] = (1.0, 0.0, 0.0),
    max_angle: float = 45.0,
    unit: str | None = None,
    simulation_unit: str | None = None,
    overwrite: bool = False,
) -> list[Path]:
    """Find the trailing edges of an OBJ and write them in the solver's node-file format.

    The trailing edge of a family is its rearmost line: the edges its surface
    lies forward of (:func:`pyflightstream.workspace._refine._obj.rearmost_edges`,
    ``aft`` the direction from the nose to the tail), taken among

    - with ``source``, the lines of its listed nodes (an ANSA SET node-window
      export, any order, every perimeter in one file), each node joined to its
      near neighbours (:data:`NEIGHBOUR_REACH`): an edge whose two ends lie on
      those segments is on a line, so the OBJ may be a refined level whose nodes
      are not the listed ones;
    - without it, the boundaries of the family cut along its sharp edges, an
      edge kept when its tangent makes ``max_angle`` degrees or less with the yz
      plane (:func:`pyflightstream.workspace._refine._prepare.rearmost_lines`).

    Beside the mesh, ``families`` given, each family's file is
    ``<mesh stem>.<family>.fs.te.txt``; else every family's trailing edge is
    one file, ``<mesh stem>.nodes.te.txt``. Without ``source``, the nodes found
    are also written as ``<mesh stem>.nodes.txt`` in the ANSA format, the node
    list a refine file's ``[[perimeter]]`` reads. The node files are written by
    :func:`write_node_file`.

    Parameters
    ----------
    mesh : str or pathlib.Path
        The OBJ, with its families (merged components, for a refined level).
    source : str or pathlib.Path, optional
        The node list saved from the SET (Id, Name, X, Y, Z), in the mesh's unit.
    families : sequence of str, optional
        The families, one file each; a name the OBJ does not hold, or one on
        which no trailing edge is found, is warned and skipped. Default: every
        family, in one file.
    aft : sequence of float
        The aft direction, from the nose to the tail (default +x).
    max_angle : float
        Without ``source``, the largest angle in degrees between a trailing-edge
        edge and the yz plane (default 45).
    unit : str, optional
        The coordinates' unit; else the ``[import] units`` of the mesh's
        boundaries file, else METER.
    simulation_unit : str, optional
        The unit the solver reads the file in (default: ``unit``, unconverted).
    overwrite : bool
        Replace existing files.

    Returns
    -------
    list of pathlib.Path
        The files written: the node files in the order of ``families``, then
        the node list.

    Raises
    ------
    InputArtifactError
        For a node list with fewer than two nodes, an unreadable mesh, an
        invalid unit, an existing file, or no trailing edge found.
    """
    from pyflightstream.workspace._refine._obj import (
        mesh_unit,
        perimeter_edges_near,
        read_node_list,
        read_obj,
        rearmost_edges,
    )
    from pyflightstream.workspace._refine._prepare import rearmost_lines

    target = Path(mesh)
    obj = read_obj(target)
    x, y, z = (float(c) for c in aft)
    names = list(obj.families) if families is None else list(families)
    for name in names:
        if name not in obj.families:
            warn(
                f"{target}: holds no family {name!r} (it holds {', '.join(obj.families)}); "
                "it is skipped",
                PyflightstreamWarning,
                stacklevel=2,
            )
    chosen = {n: obj.families[n] for n in names if n in obj.families}
    found: dict[str, set[tuple[int, int]]] = {}
    if source is not None:
        nodes = read_node_list(source)
        if len(nodes.ids) < 2:
            raise InputArtifactError(
                f"{source}: fewer than two nodes are read; save the SET's node window "
                "(Id, Name, X, Y, Z)",
                kind="wake_edges",
            )
        pairs = _neighbour_pairs(nodes.points)
        a = nodes.points[[i for i, _ in pairs]].reshape(-1, 3)
        b = nodes.points[[j for _, j in pairs]].reshape(-1, 3)
        near = perimeter_edges_near(obj.verts, chosen, a, b)
        for name, faces in chosen.items():
            found[name] = rearmost_edges(obj.verts, faces, near[name], (x, y, z))
    else:
        for name, faces in chosen.items():
            found[name] = rearmost_lines(obj.verts, faces, (x, y, z), max_angle)
    for name, edges in found.items():
        if not edges and families is not None:
            warn(
                f"{target}: no trailing edge was found on family {name!r} (no line its surface "
                "lies forward of); it is skipped",
                PyflightstreamWarning,
                stacklevel=2,
            )
    found = {n: e for n, e in found.items() if e}
    if not found:
        raise InputArtifactError(
            f"{target}: no trailing edge was found on {', '.join(names) or 'any family'}; "
            "nothing was written",
            kind="wake_edges",
        )
    if families is None:
        files = {target.with_name(f"{target.stem}.nodes.te.txt"): set().union(*found.values())}
    else:
        files = {target.with_name(f"{target.stem}.{n}.fs.te.txt"): e for n, e in found.items()}
    listing = None if source is not None else target.with_name(f"{target.stem}.nodes.txt")
    planned = [*files, *([listing] if listing else [])]
    existing = [f for f in planned if f.exists()]
    if existing and not overwrite:
        raise InputArtifactError(
            f"{existing[0]}: exists; pass overwrite (CLI: --overwrite) to replace it. "
            "Nothing was written.",
            kind="wake_edges",
        )
    unit = unit or mesh_unit(target) or "METER"
    written = []
    for path, edges in files.items():
        ends = numpy.array(sorted(edges), dtype=numpy.int64)
        mids = 0.5 * (obj.verts[ends[:, 0]] + obj.verts[ends[:, 1]])
        written.append(
            write_node_file(
                path, mids, unit=unit, simulation_unit=simulation_unit or unit, overwrite=True
            )
        )
    if listing is not None:
        rows = ["#  Id, Name, X , Y, Z"]
        for name, edges in found.items():
            for v in sorted({v for e in edges for v in e}, key=lambda v: float(obj.verts[v, 1])):
                px, py, pz = (repr(float(c)) for c in obj.verts[v])
                rows.append(f"{v + 1}, {name}, {px}, {py}, {pz}")
        _textio.write_text(listing, "\n".join(rows) + "\n")
        written.append(listing)
    return written


#: A listed node is joined to each other node closer than this many times its distance
#: to its nearest node: along a line the two neighbours are about one spacing away, and a
#: corner where two lines of different spacing meet still joins both.
NEIGHBOUR_REACH = 2.5


def _neighbour_pairs(nodes: numpy.ndarray) -> list[tuple[int, int]]:
    """Return each pair of listed nodes closer than NEIGHBOUR_REACH times either's spacing."""
    pairs: set[tuple[int, int]] = set()
    count = len(nodes)
    for start in range(0, count, 512):
        block = numpy.linalg.norm(nodes[start : start + 512, None] - nodes[None], axis=2)
        rows = numpy.arange(len(block))
        block[rows, start + rows] = numpy.inf
        spacing = block.min(axis=1)
        for r, c in zip(*numpy.nonzero(block <= NEIGHBOUR_REACH * spacing[:, None]), strict=True):
            i, j = int(start + r), int(c)
            pairs.add((min(i, j), max(i, j)))
    return sorted(pairs)


def _node_lines(nodes: numpy.ndarray) -> list[list[int]]:
    """Order nodes into lines: grow each line both ways to the nearest node left.

    A step longer than :data:`MIDNODE_GAP` times the node's spacing ends that
    direction; the line then grows from its other end, so a line started in its
    middle is still walked whole.
    """
    count = len(nodes)
    spacing = numpy.empty(count)
    for start in range(0, count, 512):
        block = numpy.linalg.norm(nodes[start : start + 512, None] - nodes[None], axis=2)
        block[numpy.arange(len(block)), numpy.arange(start, start + len(block))] = numpy.inf
        spacing[start : start + 512] = block.min(axis=1)
    left = numpy.ones(count, dtype=bool)

    def grow(line: list[int]) -> None:
        while left.any():
            rest = numpy.flatnonzero(left)
            distance = numpy.linalg.norm(nodes[rest] - nodes[line[-1]], axis=1)
            nearest = int(numpy.argmin(distance))
            if distance[nearest] > MIDNODE_GAP * spacing[line[-1]]:
                return
            line.append(int(rest[nearest]))
            left[line[-1]] = False

    lines: list[list[int]] = []
    while left.any():
        rest = numpy.flatnonzero(left)
        centre = nodes[rest].mean(axis=0)
        line = [int(rest[numpy.argmax(numpy.linalg.norm(nodes[rest] - centre, axis=1))])]
        left[line[0]] = False
        grow(line)
        line.reverse()
        grow(line)
        lines.append(line)
    return lines


def read_trailing_edge_points(path: str | Path) -> TrailingEdgePoints:
    """Read a trailing-edge points file: a unit line, then one x,y,z per line.

    The file :func:`write_trailing_edge_points` writes, or a user writes by
    hand. Its first non-blank line names the length unit of the points, a
    token of ``SET_SIMULATION_LENGTH_UNITS`` other than ``OTHER``; every
    later non-blank line is one point, three finite numbers separated by
    commas. The unit is what lets the run convert the points to the
    simulation's unit, since the solver's own file carries none.

    Parameters
    ----------
    path : str or pathlib.Path
        The points file.

    Returns
    -------
    TrailingEdgePoints
        Its unit, its points and the file line of each point.

    Raises
    ------
    InputArtifactError
        If the file cannot be read, opens with anything but a unit line
        (a line of numbers there is a file without one), names ``OTHER``,
        carries a line after the unit that is not three finite numbers
        (named by its line), or names no point.

    Examples
    --------
    >>> from pyflightstream.workspace.wake_edges import read_trailing_edge_points
    >>> read = read_trailing_edge_points(tmp_path / "wing.te.txt")  # doctest: +SKIP
    >>> read.unit, read.points.shape  # doctest: +SKIP
    ('METER', (16, 3))
    """
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as error:
        raise InputArtifactError(
            f"the trailing-edge points file {source} cannot be read: {error}",
            kind="wake_edges",
        ) from error
    scaled = ", ".join(unit for unit in node_file_units() if unit in _METRES_PER_UNIT)
    unit: str | None = None
    points: list[list[float]] = []
    lines: list[int] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if unit is None:
            if line == "OTHER":
                raise InputArtifactError(
                    f"{source}: the unit line names OTHER, which names no scale, so its "
                    "points cannot be converted to the simulation's length unit. Name the "
                    f"unit the points are in, one of: {scaled}",
                    kind="wake_edges",
                )
            if line not in _METRES_PER_UNIT:
                raise InputArtifactError(
                    f"{source}: line {number} reads {line!r}, and a trailing-edge points "
                    "file opens with a unit line naming the length unit its points are "
                    f"in, one of: {scaled}. A line of numbers there is a file with no unit "
                    "line, and its points would have no scale to convert by",
                    kind="wake_edges",
                )
            unit = line
            continue
        try:
            values = [float(field) for field in line.split(",")]
        except ValueError:
            values = []
        if len(values) != 3 or not all(math.isfinite(value) for value in values):
            raise InputArtifactError(
                f"{source}: line {number} reads {line!r}, and every line after the unit "
                "line is one trailing-edge point: x, y and z, three finite numbers "
                "separated by commas",
                kind="wake_edges",
            )
        points.append(values)
        lines.append(number)
    if unit is None:
        raise InputArtifactError(
            f"{source} is empty, and a trailing-edge points file opens with a unit line "
            f"naming the length unit of its points, one of: {scaled}",
            kind="wake_edges",
        )
    if not points:
        raise InputArtifactError(
            f"{source} names its unit, {unit}, and no point after it. The points name the "
            "edges to mark, and with none the import marks nothing and says nothing",
            kind="wake_edges",
        )
    return TrailingEdgePoints(
        unit=unit, points=numpy.asarray(points, dtype=float), lines=tuple(lines)
    )


def _mesh_edge_midpoints(mesh: Any) -> numpy.ndarray:
    """Return the mid-point of every edge of a surface mesh, shape (k, 3).

    A file holding several bodies loads as a scene, and its bodies are
    joined, since a points file may name edges on more than one of them.
    """
    loaded = mesh
    if isinstance(mesh, (str, Path)):
        try:
            loaded = read_mesh(mesh)
        except (OSError, ValueError, NotImplementedError) as error:
            raise InputArtifactError(
                f"the mesh file {mesh} could not be read to check the trailing-edge "
                f"points against it: {error}",
                kind="wake_edges",
            ) from error
    if getattr(loaded, "faces", None) is None and hasattr(loaded, "to_mesh"):
        loaded = loaded.to_mesh()
    vertices = numpy.asarray(getattr(loaded, "vertices", ()), dtype=float)
    faces = numpy.asarray(getattr(loaded, "faces", ()), dtype=int)
    if faces.ndim != 2 or faces.shape[0] == 0 or faces.shape[1] != 3 or vertices.ndim != 2:
        raise InputArtifactError(
            f"the mesh carries no triangular faces (their array has shape "
            f"{tuple(faces.shape)}), so it has no edges for a trailing-edge point to lie on",
            kind="wake_edges",
        )
    if vertices.shape[1] != 3:
        raise InputArtifactError(
            f"the mesh vertices have shape {tuple(vertices.shape)}, and a vertex array is "
            "n by 3 (x, y, z); a trailing-edge point cannot be checked against anything else",
            kind="wake_edges",
        )
    if faces.min() < 0 or faces.max() >= len(vertices):
        raise InputArtifactError(
            f"the mesh faces name vertex indices from {int(faces.min())} to "
            f"{int(faces.max())}, and the mesh has {len(vertices)} vertices, indexed 0 to "
            f"{len(vertices) - 1}; a face outside that range is not a face of this mesh",
            kind="wake_edges",
        )
    edges = numpy.unique(numpy.sort(faces[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), axis=1), axis=0)
    return (vertices[edges[:, 0]] + vertices[edges[:, 1]]) / 2.0


def _nearest(
    points: numpy.ndarray, candidates: numpy.ndarray
) -> tuple[numpy.ndarray, numpy.ndarray]:
    """For each point, the index of and the distance to its nearest candidate.

    Brute force in blocks sized to keep the difference array near three
    million numbers, so a fine mesh costs time and not memory, and no
    proximity library is needed.
    """
    index = numpy.empty(len(points), dtype=int)
    distance = numpy.empty(len(points), dtype=float)
    step = max(1, 1_000_000 // max(1, len(candidates)))
    for start in range(0, len(points), step):
        block = points[start : start + step]
        gaps = numpy.linalg.norm(block[:, None, :] - candidates[None, :, :], axis=2)
        chosen = gaps.argmin(axis=1)
        index[start : start + step] = chosen
        distance[start : start + step] = gaps[numpy.arange(len(block)), chosen]
    return index, distance


def _as_written(point: Sequence[float]) -> str:
    """Spell a point as a points file line: x,y,z."""
    return ",".join(repr(float(value)) for value in point)


def matched_trailing_edge_points(
    points: object,
    *,
    points_unit: str,
    mesh: Any,
    mesh_unit: str,
    simulation_unit: str,
    tolerance: float = DEFAULT_TOLERANCE,
    source: str = "the trailing-edge points",
    lines: Sequence[int] | None = None,
) -> numpy.ndarray:
    """Return the trailing-edge points in the simulation unit, each matched to a mesh edge.

    Every point is checked against the mesh before any run, and the first
    that matches no edge is refused. The import marks an edge whose
    mid-point lies within ``tolerance`` of a
    point and marks nothing, in silence, for a point outside that distance
    of every edge's mid-point (RPT-061); an end vertex of an edge is such a
    point whenever the edge is longer than twice the tolerance. So each
    point must lie within the tolerance of a mesh-edge mid-point,
    compared in the simulation's length unit, and no two points
    may be nearest one edge, since the solver would then log fewer
    imported edges than points written and the run would be refused after
    the seat is spent.

    Parameters
    ----------
    points : array_like
        The points, shape (n, 3), in ``points_unit``.
    points_unit : str
        Their unit, a token of :func:`node_file_units` other than OTHER.
    mesh : str, pathlib.Path or trimesh.Trimesh
        The surface the points name edges of, as a file (a scene's bodies
        are joined) or loaded.
    mesh_unit : str
        The unit the mesh coordinates are in.
    simulation_unit : str
        The simulation's length unit, the one the tolerance is in and the
        one the points come back in.
    tolerance : float
        The import's tolerance, in ``simulation_unit``; positive and finite.
    source : str
        What the points are, for the refusal: ordinarily the file's path.
    lines : sequence of int, optional
        The file line of each point, as :func:`read_trailing_edge_points`
        returns them, so a refusal names the line to open.

    Returns
    -------
    numpy.ndarray
        The points converted to ``simulation_unit``, shape (n, 3), ready
        for :func:`pyflightstream.script.helpers.mark_wake_edges`.

    Raises
    ------
    InputArtifactError
        On the FIRST point farther than the tolerance from every mesh-edge
        mid-point, naming its position, its file line, its coordinates and
        its distance; on two points nearest one edge; and on a unit with no
        scale, a tolerance that is not positive and finite, points that are
        not (n, 3) finite coordinates, or a mesh with no faces.

    Notes
    -----
    The mesh's edges are those of its triangles, so a mesh read from quads
    carries the diagonals its reader added, and a point on a diagonal's
    mid-point passes here although no edge of the solver's mesh may lie
    there. A trailing edge seldom runs along a diagonal; it is stated so a
    passing check is not read as more than it is.

    Examples
    --------
    >>> from pyflightstream.workspace.wake_edges import (
    ...     matched_trailing_edge_points,
    ...     read_trailing_edge_points,
    ... )
    >>> read = read_trailing_edge_points("wing.te.txt")  # doctest: +SKIP
    >>> in_metres = matched_trailing_edge_points(
    ...     read.points,
    ...     points_unit=read.unit,
    ...     mesh="wing.stl",
    ...     mesh_unit="METER",
    ...     simulation_unit="METER",
    ...     source="wing.te.txt",
    ...     lines=read.lines,
    ... )  # doctest: +SKIP
    """
    array = _coordinates(points)
    if not math.isfinite(tolerance) or tolerance <= 0.0:
        raise InputArtifactError(
            f"the trailing-edge points were to be checked with a tolerance of "
            f"{tolerance!r} {tolerance_unit()}, and the tolerance is the distance within "
            "which a mesh-edge mid-point counts as a point; it must be positive and finite",
            kind="wake_edges",
        )
    scaled = array * length_scale(points_unit, simulation_unit)
    midpoints = _mesh_edge_midpoints(mesh) * length_scale(mesh_unit, simulation_unit)
    nearest, distance = _nearest(scaled, midpoints)
    count = len(scaled)
    for position in range(count):
        if distance[position] <= tolerance:
            continue
        where = f", file line {lines[position]}" if lines is not None else ""
        raise InputArtifactError(
            f"{source}: point {position + 1} of {count}{where} ({_as_written(array[position])} "
            f"{points_unit}) lies {distance[position]:.6g} {simulation_unit} from the nearest "
            f"mesh-edge mid-point ({_as_written(midpoints[nearest[position]])} "
            f"{simulation_unit}). The import matches an edge whose mid-point is within "
            f"{tolerance:g} {simulation_unit} of a point and marks nothing, silently, for a "
            "point outside that distance of every edge; an end vertex of an edge is such a "
            "point. Write the mid-point of each trailing-edge mesh edge",
            kind="wake_edges",
        )
    first_on: dict[int, int] = {}
    for position, edge in enumerate(nearest.tolist()):
        if edge in first_on:
            raise InputArtifactError(
                f"{source}: points {first_on[edge] + 1} and {position + 1} of {count} both "
                f"lie nearest the mesh-edge mid-point {_as_written(midpoints[edge])} "
                f"{simulation_unit}, so the import would mark one edge for two points and "
                "the solver would log fewer imported edges than points written. Name each "
                "edge once",
                kind="wake_edges",
            )
        first_on[edge] = position
    return scaled


def bind_wake_termination(conditions, geometry, mesh_import, solver):
    """Bind a selected explicit termination route when the imported mesh is unchanged."""
    if conditions is None or not isinstance(conditions.wake_termination, WakeTerminationMarking):
        return conditions
    if solver is not None and solver.apply_wake_termination is False:
        return conditions
    if mesh_import is None or mesh_import.moving_operations:
        return conditions
    return conditions.model_copy(
        update={
            "wake_termination": matched_wake_termination_nodes(
                conditions.wake_termination, geometry, mesh_import.units
            )
        }
    )


def matched_wake_termination_nodes(
    marking: WakeTerminationMarking, mesh: Path, mesh_unit: str
) -> WakeTerminationMarking:
    """Match each point to exactly one mesh vertex, refusing absent or ambiguous matches."""
    read = read_trailing_edge_points(marking.points_file)
    if mesh.suffix.lower() == ".obj":
        # SELECT uses the written OBJ vertex index. A mesh loader may weld,
        # reorder or discard vertices, so its indices cannot identify these nodes.
        vertices = numpy.asarray(
            [
                [float(v) for v in line.split()[1:4]]
                for line in mesh.read_text(encoding="utf-8").splitlines()
                if line.split() and line.split()[0] == "v"
            ]
        ) * length_scale(mesh_unit, "METER")
    else:
        loaded = read_mesh(mesh)
        if getattr(loaded, "vertices", None) is None and hasattr(loaded, "to_mesh"):
            loaded = loaded.to_mesh()
        vertices = numpy.asarray(loaded.vertices) * length_scale(mesh_unit, "METER")
    points = read.points * length_scale(read.unit, "METER")
    nodes = []
    for index, point in enumerate(points, start=1):
        matches = numpy.flatnonzero(
            numpy.linalg.norm(vertices - point, axis=1) <= marking.tolerance
        )
        if len(matches) != 1:
            raise InputArtifactError(
                f"{marking.points_file}: wake-termination point {index} matches "
                f"{len(matches)} mesh vertices within {marking.tolerance:g} m; "
                "require exactly one, adjust the point or tolerance"
            )
        # SELECT_MESH_NODE uses node 1 in qa/_spec_0400_gap.py P1-10 (RPT-166).
        nodes.append(int(matches[0]) + 1)
    return marking.model_copy(update={"nodes": tuple(nodes)})


def matched_trailing_edge_sets(
    marking: TrailingEdgeMarking, mesh: Path, mesh_unit: str
) -> TrailingEdgeMarking:
    """Bind every file to the source mesh and refuse edges claimed by two files."""
    midpoints = _mesh_edge_midpoints(mesh) * length_scale(mesh_unit, "METER")
    owners: dict[int, str] = {}
    checked = []
    for entry in marking.sets:
        assert entry.points_file is not None
        source = Path(entry.points_file)
        read = read_trailing_edge_points(source)
        points = matched_trailing_edge_points(
            read.points,
            points_unit=read.unit,
            mesh=mesh,
            mesh_unit=mesh_unit,
            simulation_unit="METER",
            tolerance=marking.tolerance,
            source=source.name,
            lines=read.lines,
        )
        nearest, _ = _nearest(points, midpoints)
        for index in nearest.tolist():
            if index in owners:
                raise InputArtifactError(
                    f"trailing-edge files {owners[index]} and {source.name} claim "
                    "the same mesh edge; name each edge once"
                )
            owners[index] = source.name
        checked.append(entry.model_copy(update={"points_m": tuple(map(tuple, points.tolist()))}))
    return marking.model_copy(update={"sets": tuple(checked)})


def write_node_file(
    path: str | Path,
    nodes: object,
    *,
    unit: str,
    simulation_unit: str,
    overwrite: bool = False,
) -> Path:
    """Write the node list the wake-edge import reads, from edge mid-points.

    The seam between a third-party mesh reader and a solver input
    format: the extraction happens outside, with a mesh library, and
    this turns the mid-points it produced into the file the solver
    imports.

    THE LAYOUT IS THE ONE 26.124 WAS MEASURED TO READ (RPT-061): the
    number of points, one coordinate line the solver consumes and does
    not use, then one ``x,y,z`` row per mesh-edge MID-POINT, in the
    simulation's length unit, with no unit line and no ids. The layout the
    manual prints for the GUI's import (a count, a unit token, then an id
    and three coordinates per END VERTEX) was run and marks nothing, and
    so does any file with a word on a line. The file's unit is not read,
    so the points are CONVERTED from ``unit`` to ``simulation_unit`` here
    rather than labelled. The text is
    :func:`pyflightstream.script.helpers.render_wake_edge_node_file`'s,
    the one place the layout is written.

    Parameters
    ----------
    path : str or pathlib.Path
        Destination file.
    nodes : array_like
        The mid-points of the mesh edges to mark, shape (n, 3), in the
        unit named by ``unit``. Any nested sequence numpy can read is
        accepted, so a caller need not convert an extraction first.
    unit : str
        Length unit the given coordinates are in, one of
        :func:`node_file_units` other than ``OTHER``.
    simulation_unit : str
        The simulation's length unit, the one its
        ``SET_SIMULATION_LENGTH_UNITS`` names, which is the unit the
        solver reads the file's coordinates in. Same vocabulary.
    overwrite : bool
        Replace an existing destination. False refuses instead, because
        one path is one file and a second write would silently win.

    Returns
    -------
    pathlib.Path
        The file written.

    Raises
    ------
    InputArtifactError
        If the node list is empty, is not (n, 3), carries a coordinate
        that is not a finite number, names a unit with no scale (``OTHER``
        or a token outside the recorded vocabulary), or would replace an
        existing file without ``overwrite``. Every one of these fires
        before the file is opened, so a refused call leaves no partial
        file behind.

    Notes
    -----
    The existing-destination refusal is an
    :class:`~pyflightstream.workspace.InputArtifactError` rather than the
    ``OutputExistsError`` the flow-visualization writers raise, because
    that class lives in the post layer and this one sits below it;
    importing it here would point upward. The rule it enforces is the
    same rule.

    The file is written with LF line ends on every platform, which is
    the form the measured file had.

    Examples
    --------
    >>> import numpy
    >>> from pyflightstream.workspace.wake_edges import write_node_file
    >>> written = write_node_file(
    ...     tmp_path / "wake_nodes.txt",
    ...     numpy.array([[1000.0, -3750.0, 0.0], [1000.0, -3250.0, 0.0]]),
    ...     unit="MILLIMETER",
    ...     simulation_unit="METER",
    ... )  # doctest: +SKIP
    """
    destination = Path(path)
    array = _coordinates(nodes)
    # Both units are checked before anything is opened: the solver reads the
    # coordinates in the simulation's unit and no unit from the file, so a
    # token with no scale leaves nothing to convert by.
    scale = length_scale(unit, simulation_unit)
    _refuse_an_existing_file(destination, overwrite)

    try:
        text = render_wake_edge_node_file((array * scale).tolist())
    except CommandArgumentError as error:
        # Reached only when a converted coordinate overflows to infinity;
        # refused in this layer's vocabulary rather than the script layer's.
        raise InputArtifactError(str(error), kind="wake_edges") from error
    _textio.write_text(destination, text)
    return destination
