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
default in its own table (SRC-750 p.324, SRC-751 p.323).
"""

from __future__ import annotations

import math
from fractions import Fraction
from pathlib import Path

import numpy
from pydantic import BaseModel, ConfigDict, model_validator

from pyflightstream.commands import CommandRegistry, Status
from pyflightstream.script import CommandArgumentError
from pyflightstream.script.helpers import render_wake_edge_node_file
from pyflightstream.workspace.inputs import InputArtifactError, PointXyz

__all__ = [
    "DEFAULT_EDGE_TYPE",
    "DEFAULT_TOLERANCE",
    "LENGTH_UNIT_COMMAND",
    "TRAILING_EDGE_DETECTION_COMMAND",
    "WAKE_EDGE_IMPORT_COMMAND",
    "WakeEdgeImport",
    "edge_types",
    "evidence_notice",
    "length_scale",
    "node_file_units",
    "tolerance_unit",
    "write_node_file",
]

#: The command this module's inputs are assembled for.
WAKE_EDGE_IMPORT_COMMAND = "IMPORT_WAKE_EDGES_FROM_FILE"

#: What the import replaces: the angle criterion that marks trailing
#: edges without being told where they are.
TRAILING_EDGE_DETECTION_COMMAND = "AUTO_DETECT_TRAILING_EDGES"

#: The edge type the manual's own printed sample call passes.
DEFAULT_EDGE_TYPE = "VORTEX_SHEDDING"

#: The tolerance the manual's parameter table states as the default and
#: the printed sample call passes (SRC-750 p.324, SRC-751 p.323). It is
#: recorded here rather than invented, so nobody has to reverse engineer
#: where it came from.
DEFAULT_TOLERANCE = 0.0001


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

    if import_reports:
        standing = "cites a probe report on this database: " + ", ".join(import_reports)
    else:
        # PRECISE, because the loose wording was wrong. The command IS
        # named by the compat runs that reached its builds; each records
        # it unprobed for want of a probe specification. What no row of
        # it cites is a report, which is what this sentence claims and
        # all it claims.
        standing = "cites no probe report on any build, every row it has being read off a page"

    if detection_verified:
        replaced = (
            f"{TRAILING_EDGE_DETECTION_COMMAND} was run and recorded verified on "
            + ", ".join(detection_verified)
        )
    else:
        replaced = f"{TRAILING_EDGE_DETECTION_COMMAND} carries no verified row either"

    return (
        f"Trailing edges are marked on FlightStream {canonical} through "
        f"{WAKE_EDGE_IMPORT_COMMAND}, which {standing}, in place of "
        f"{TRAILING_EDGE_DETECTION_COMMAND}. The trade is deliberate and the "
        f"reason is physical: auto detection is an angle criterion and cannot "
        f"find an edge that is not a geometric crease, which is exactly the "
        f"edge an imported node list exists to mark. It is stated because it "
        f"is a move to weaker evidence: {replaced}."
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
        :func:`edge_types`. Defaults to ``"VORTEX_SHEDDING"``, the value
        the manual's own printed sample passes.
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
    >>> settings = WakeEdgeImport(nodes=(PointXyz(x_m=1.0, y_m=0.0, z_m=0.0),))
    >>> settings.edge_type, settings.tolerance
    ('VORTEX_SHEDDING', 0.0001)
    """

    model_config = ConfigDict(extra="forbid")

    nodes: tuple[PointXyz, ...] = ()
    edge_type: str = DEFAULT_EDGE_TYPE
    tolerance: float = DEFAULT_TOLERANCE

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


#: The command whose enumeration is the simulation's length-unit
#: vocabulary. The solver reads the node file's coordinates in the
#: SIMULATION's unit and reads no unit from the file (RPT-061), so points
#: given in another unit are converted, and both units have to be tokens
#: of the solver's vocabulary and not of this package's taste.
LENGTH_UNIT_COMMAND = "SET_SIMULATION_LENGTH_UNITS"

#: Metres in one of each length unit the solver records, exact as decimals.
#: OTHER is absent on purpose: it names no scale, so nothing can be
#: converted to or from it. Every other recorded token has an entry, which
#: ``tests/tier1_offline/test_wake_edges.py`` holds against the record.
_METRES_PER_UNIT: dict[str, Fraction] = {
    "METER": Fraction(1),
    "CENTIMETER": Fraction("0.01"),
    "MILLIMETER": Fraction("0.001"),
    "MICRON": Fraction("0.000001"),
    "KILOMETER": Fraction(1000),
    "INCH": Fraction("0.0254"),
    "FEET": Fraction("0.3048"),
    "MILE": Fraction("1609.344"),
    "MILS": Fraction("0.0000254"),
    "MICROINCH": Fraction("0.0000000254"),
}


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
    return float(_METRES_PER_UNIT[from_unit] / _METRES_PER_UNIT[to_unit])


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

    The file is written in the platform's text mode, as the run writes
    the script that names it, which is the form the measured file had.

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
    try:
        array = numpy.asarray(nodes, dtype=float)
    except (TypeError, ValueError) as error:
        # Found by the adversarial pass: a string, a ragged list or an
        # object array reached numpy and left a bare ValueError on a
        # public name, which is the one exception shape this repository
        # refuses (FR-39). The cause is named rather than re-worded.
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
    # Both units are checked before anything is opened: the solver reads the
    # coordinates in the simulation's unit and no unit from the file, so a
    # token with no scale leaves nothing to convert by.
    scale = length_scale(unit, simulation_unit)
    if destination.exists() and not overwrite:
        raise InputArtifactError(
            f"{destination} already exists. Pass overwrite=True to replace it "
            "deliberately, or write under a name that carries the geometry: one path is "
            "one file, so a second node list written here would silently win and both "
            "scripts citing it would import whichever ran last",
            kind="wake_edges",
        )

    try:
        text = render_wake_edge_node_file((array * scale).tolist())
    except CommandArgumentError as error:
        # Reached only when a converted coordinate overflows to infinity;
        # refused in this layer's vocabulary rather than the script layer's.
        raise InputArtifactError(str(error), kind="wake_edges") from error
    destination.write_text(text, encoding="utf-8")
    return destination
