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

THE DEFAULT ROUTE RESTS ON A COMMAND NOBODY HAS RUN, and that is stated
rather than left for a reader to discover. Marking wake edges from a
file replaces trailing-edge auto detection, which is an angle criterion
and cannot find the edges this capability exists for; that is the
reason for the trade and it is a good one. It is still a move from a
command three committed probe reports cover to one that no run has ever
exercised, on any build. :func:`evidence_notice` renders that sentence
from the command database at the moment it is asked, so the day a probe
promotes the import the sentence follows it, and a reader meeting the
default never reads it as settled practice.

The two defaults are the vendor's own numbers rather than this
package's taste: the manual page prints a sample call passing
VORTEX_SHEDDING and 0.0001, and states the same number as the parameter
default in its own table (SRC-750 p.324, SRC-751 p.323).
"""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, model_validator

from pyflightstream.commands import CommandRegistry, Status
from pyflightstream.workspace.inputs import InputArtifactError, PointXyz

__all__ = [
    "DEFAULT_EDGE_TYPE",
    "DEFAULT_TOLERANCE",
    "TRAILING_EDGE_DETECTION_COMMAND",
    "WAKE_EDGE_IMPORT_COMMAND",
    "WakeEdgeImport",
    "edge_types",
    "evidence_notice",
    "tolerance_unit",
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
