"""The static ledgers of the script builder: command tables and frame placements.

Two groups of data and the small functions that read them, kept apart from
:class:`~pyflightstream.script.Script` so the builder holds the emission order
and the state, and nothing of the tables it consults.

* The command tables say which commands count, create, delete or move
  entities. The sets are named one command at a time on purpose: a prefix
  rule recorded some commands and missed their siblings (PFS-2104.020), and a
  table a reader can diff against the database is the one a guard can check.
* The frame placement ledger (FR-100) says what an explicit coordinate-system
  command states about where a frame sits, and which commands it follows.
* The provenance records the builder collects, :class:`BrokenCommandUse` for a
  waived broken command and :class:`UnsteadyActionUse` for a registered action.

:class:`FramePlacement` and the two records keep ``pyflightstream.script`` as
their module, where they are documented and imported.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field

from pyflightstream.commands import ArgSpec, ArgType, CommandEntry, Layout, ListSeparator
from pyflightstream.script._arg_checks import CommandArgumentError

# Argument names declaring the following list's length. A count that
# disagrees with its payload makes the solver consume following commands
# as data. The names mirror each manual page, rather than a type rule.
# The tier-1 test_every_declared_count_is_a_known_count_name guard walks
# the database and refuses an int scalar introducing a list under an
# unrecognized count name.
_COUNT_ARG_NAMES = {
    "boundaries",
    "count",
    "num_boundaries",
    "num_frames",
    "num_index",
    "num_sections",
    "num_variables",
    "numpts",
    # SURFACE_COMBINE's surface count (FSM-26.120 p.312).
    "surface_count",
    "surfaces",
    # WRAPPER_SET_INPUT's surface count (FSM-26.120 p.314). Each command's
    # argument spelling follows its manual page; this set covers them all.
    "num_surfaces",
    # BOOLEAN_UNITE_MESH's mesh-body count (FSM-26.120 p.316).
    "num_bodies",
    # BOOLEAN_UNITE_GEOMETRY's geometry-body count (FSM-25.000 p.272).
    # Preserve this command's argument spelling even though the same page
    # uses num_bodies for a different command.
    "bodies",
}

# Cross-reference ledger (SAD Section 4.2): commands that create an
# indexed auxiliary object, commands that delete one, and the argument
# names that cite one. Frame index 1 is the reference frame and always
# exists (FSM-26.120 p.329); created local frames take indices 2 upward.
# Mesh boundaries are cited but never created by a command: their
# inventory comes from declare_existing() and -1 selects all of them.
_CREATION_COMMANDS = {
    "CREATE_NEW_COORDINATE_SYSTEM": "frames",
    # Copy and MIRROR append new frames; MIRROR leaves the original intact
    # (coordinate_systems.yaml). Count both so the next create uses a new index.
    "DUPLICATE_COORDINATE_SYSTEM": "frames",
    "MIRROR_COORDINATE_SYSTEM": "frames",
    "CREATE_NEW_ACTUATOR": "actuators",
    "CREATE_NEW_MOTION": "motions",
    # 25.000 creates motions with one command per type rather than
    # CREATE_NEW_MOTION (FSM-25.000, PFS-2104.018).
    "CREATE_NEW_MOTION_EUCLIDEAN": "motions",
    "CREATE_NEW_MOTION_CUSTOM": "motions",
    "CREATE_NEW_MOTION_6DOF": "motions",
    "CREATE_NEW_MOTION_FSI": "motions",
}
#: The CREATE_NEW_* commands that make nothing the entity registry counts:
#: a force, an observer, a region, an inlet or outlet, a surface or a section.
#: Every CREATE_NEW_* of the database is here or in ``_CREATION_COMMANDS``, and
#: a tier-1 guard walks the database for one in neither (PFS-2104.018).
_UNCOUNTED_CREATIONS = frozenset(
    {
        "CREATE_NEW_6DOF_CUSTOM_FORCE",
        "CREATE_NEW_6DOF_EXTERNAL_FORCE",
        "CREATE_NEW_6DOF_SPRING_FORCE",
        "CREATE_NEW_ACOUSTIC_OBSERVER",
        "CREATE_NEW_BASE_REGION",
        "CREATE_NEW_CIRCLE_VOLUME_SECTION",
        "CREATE_NEW_INLET",
        "CREATE_NEW_OUTLET",
        "CREATE_NEW_RECTANGLE_VOLUME_SECTION",
        "CREATE_NEW_SURFACE_FROM_SELECTION",
        "CREATE_NEW_SURFACE_SECTION",
    }
)
#: Each deletion command, the kind it deletes and the argument naming the
#: index, which the registry needs to renumber the labels above it (RPT-021
#: section 3; PFS-2104.025).
_DELETION_COMMANDS = {
    "DELETE_ACTUATOR": ("actuators", "actuator_index"),
    "DELETE_MOTION": ("motions", "motion_id"),
    "DELETE_COORDINATE_SYSTEM": ("frames", "frame"),
}

#: THE COMMANDS THAT MOVE, SCALE, MIRROR OR COPY MESH SURFACES, named one by one
#: (PFS-2104.020). A prefix rule recorded ROTATE_SURFACE and the two
#: TRANSLATE_SURFACE_* and missed SURFACE_ROTATE, SURFACE_SCALE and
#: SURFACE_MIRROR, so the custom-field envelope was computed from a body those
#: commands had changed. A tier-1 guard walks the mesh-operations chapter for a
#: transform missing from this set.
_SURFACE_TRANSFORM_COMMANDS = frozenset(
    {
        "ROTATE_SURFACE",
        "SURFACE_ROTATE",
        "TRANSLATE_SURFACE_IN_FRAME",
        "TRANSLATE_SURFACE_BY_FRAME",
        "SURFACE_SCALE",
        "SURFACE_MIRROR",
        "SURFACE_LINEAR_COPY_PASTE",
        "SURFACE_CIRCULAR_COPY_PASTE",
        "TRANSFORM_SELECTED_NODES",
    }
)

#: The commands that discard the model the script built and start another.
_NEW_MODEL_COMMANDS = frozenset({"OPEN", "NEW_SIMULATION"})
#: The minimum-Cp limiter, whose library default a settings call emits only
#: while the script carries none (PFS-2104.023).
_MINIMUM_CP_COMMAND = "SOLVER_MINIMUM_CP"
#: The command that initialises the solver. The script keeps where it last
#: emitted it, which :meth:`Script.emit_after_initialization` needs (G02).
_INITIALIZATION_COMMAND = "INITIALIZE_SOLVER"

#: The command declaring the simulation length unit. Its one home (AD-10);
#: script.helpers reads the unit vocabulary from this declaration.
LENGTH_UNIT_COMMAND = "SET_SIMULATION_LENGTH_UNITS"
#: The command that names the analysis loads frame, in which the solver writes
#: its VTK surface export (RPT-074).
_LOADS_FRAME_COMMAND = "SET_SOLVER_ANALYSIS_LOADS_FRAME"

#: The commands that add a volume section to the solver's list, remove one by
#: its index, and remove them all (G05).
_VOLUME_SECTION_CREATES = frozenset(
    {"CREATE_NEW_RECTANGLE_VOLUME_SECTION", "CREATE_NEW_CIRCLE_VOLUME_SECTION"}
)
_VOLUME_SECTION_DELETE = "DELETE_VOLUME_SECTION"
_VOLUME_SECTION_DELETE_ALL = "DELETE_ALL_VOLUME_SECTIONS"

# Count arguments that state how many mesh boundaries the command
# selects; checked against the declared inventory, -1 meaning all.
_COUNT_REFERENCE_ARGS = {
    "num_boundaries": "boundaries",
    "boundaries": "boundaries",
    "surfaces": "boundaries",
}


def _reference_kind(spec: ArgSpec) -> str | None:
    """Return the argument's declared entity kind, or None.

    Use the per-version cites declaration rather than infer a kind from the
    argument name: index can refer to a surface, separation or section.

    Parameters
    ----------
    spec : ArgSpec
        Argument specification from the per-version view.

    Returns
    -------
    str or None
        Entity kind as spelled by script.entities, or None for no reference.
    """
    return str(spec.cites) if spec.cites is not None else None


def _vector(bound: Mapping[str, object], *names: str) -> _Vector:
    """Read three bound arguments as one vector, for the frame ledger."""
    x, y, z = (float(bound[name]) for name in names)  # type: ignore[arg-type]
    return (x, y, z)


#: A point or a direction in the reference frame's axes.
_Vector = tuple[float, float, float]

#: The reference frame, index 1, which every script has and no command
#: places: at the origin, with the reference axes.
_REFERENCE_PLACEMENT_INDEX = 1


class FramePlacement(BaseModel):
    """Placement retained from explicit coordinate-system commands (FR-100).

    Origin values retain the numeric convention of emitted frame commands.
    Axes are the named X, Y and Z directions in REFERENCE. Explicit-unit
    origins are converted through the recorded simulation unit; while no
    unit is recorded (no SET_SIMULATION_LENGTH_UNITS and no decoded saved
    head) an origin stated in METER is kept as written and one stated in any
    other unit is forgotten rather than converted, because nothing in the
    command says what the native unit is (GEO-060 A1a). Physical
    interpretation requires a measured native unit contract; this ledger does
    not establish it. Unfollowed placement commands clear affected values.
    """

    model_config = ConfigDict(frozen=True)

    origin: _Vector | None
    axes: tuple[_Vector, _Vector, _Vector] | None


#: The coordinate-system commands that move or re-index a frame in a way
#: the ledger does not follow. A frame they touch loses its placement, and
#: a delete loses every placement, because it shifts the indices above it.
_UNFOLLOWED_FRAME_COMMANDS = frozenset(
    {
        "SET_COORDINATE_SYSTEM_AXIS",
        "NORMALIZE_COORDINATE_SYSTEM",
        "TRANSLATE_COORDINATE_SYSTEM",
    }
)

#: The commands that name a frame, or make one, and leave where every frame
#: stands as it was: a creation (placed by the EDIT that follows it), a rename,
#: a copy (whose new frame the ledger does not place, so it has no entry), and
#: the two of other chapters that ASSIGN a frame, to a motion and to the
#: aeroelastic bodies, and state no origin or axis for it. Every
#: command whose name says it is about a coordinate system is in this set, in
#: ``_UNFOLLOWED_FRAME_COMMANDS``, or in ``_FRAME_FOLLOWERS``, and a tier-1 guard
#: walks the database for one that is in none, which is how a command added
#: later is kept from leaving a stale placement behind in silence.
_FRAME_NEUTRAL_COMMANDS = frozenset(
    {
        "CREATE_NEW_COORDINATE_SYSTEM",
        "SET_COORDINATE_SYSTEM_NAME",
        "DUPLICATE_COORDINATE_SYSTEM",
        "MIRROR_COORDINATE_SYSTEM",
        "SET_MOTION_COORDINATE_SYSTEM",
        "ASSIGN_AEROELASTIC_COORDINATE_SYSTEMS",
    }
)


def _placed_by_edit(
    placements: dict[int, FramePlacement], frame: int, bound: Mapping[str, object]
) -> None:
    """``EDIT_COORDINATE_SYSTEM`` states origin and axes in the reference (FSM-26.123 p.334)."""
    placements[frame] = FramePlacement(
        origin=_vector(bound, "origin_x", "origin_y", "origin_z"),
        axes=(
            _vector(bound, "vector_x_x", "vector_x_y", "vector_x_z"),
            _vector(bound, "vector_y_x", "vector_y_y", "vector_y_z"),
            _vector(bound, "vector_z_x", "vector_z_y", "vector_z_z"),
        ),
    )


def _placed_by_origin(
    placements: dict[int, FramePlacement],
    frame: int,
    bound: Mapping[str, object],
    *,
    simulation_unit: str | None = None,
) -> None:
    """``SET_COORDINATE_SYSTEM_ORIGIN`` states the origin in the reference (FSM-26.123 p.334).

    UNKNOWN UNIT, FORGOTTEN (GOAL-034 Q4, GEO-060 A1a, CX-1): the command's
    explicit unit is converted through the one length table into the native
    unit of the placement ledger only when the script knows the simulation's
    length unit (set by the script or read from the opened save). While that
    unit is unknown an origin in ``METER`` is kept as written,
    and one in any other unit is forgotten rather than converted, so
    a translation of that frame is refused.
    """
    from pyflightstream._lengths import scale

    held = placements.get(frame)
    units = str(bound.get("units"))
    if simulation_unit is None:
        factor = 1.0 if units == "METER" else None
    else:
        factor = scale(units, simulation_unit)
    values = _vector(bound, "x", "y", "z")
    origin = (
        None if factor is None else (values[0] * factor, values[1] * factor, values[2] * factor)
    )
    placements[frame] = FramePlacement(origin=origin, axes=held.axes if held is not None else None)


def _placed_by_turn(
    placements: dict[int, FramePlacement], frame: int, bound: Mapping[str, object]
) -> None:
    """``ROTATE_COORDINATE_SYSTEM`` turns by a sign the manual does not state.

    The axes are forgotten; the origin survives only when the frame sits at the
    origin of the frame it turns about, which a turn about that point cannot
    move whatever its sign.
    """
    # NO ZERO-TURN SHORTCUT (GOAL-034 Q4, GEO-060 A1b/A1c): that a turn by 0
    # leaves a frame in place is a claim about the solver with no owner decision
    # and no recorded native export behind it, so the turn is treated as any other.
    held = placements.get(frame)
    pivot = placements.get(bound.get("rotation_frame"))  # type: ignore[call-overload]
    stays = (
        held is not None
        and pivot is not None
        and held.origin is not None
        and held.origin == pivot.origin
    )
    placements[frame] = FramePlacement(
        origin=held.origin if stays and held is not None else None, axes=None
    )


def _placed_by_delete(
    placements: dict[int, FramePlacement], frame: int, bound: Mapping[str, object]
) -> None:
    """Forget every placement but the reference's: a delete shifts every index above it."""
    reference = placements[_REFERENCE_PLACEMENT_INDEX]
    placements.clear()
    placements[_REFERENCE_PLACEMENT_INDEX] = reference


#: Commands followed by the ledger, with their handlers. Keys define the
#: followed set so a declared command always has an implementation.
_FRAME_FOLLOWERS = {
    "EDIT_COORDINATE_SYSTEM": _placed_by_edit,
    "SET_COORDINATE_SYSTEM_ORIGIN": _placed_by_origin,
    "ROTATE_COORDINATE_SYSTEM": _placed_by_turn,
    "DELETE_COORDINATE_SYSTEM": _placed_by_delete,
}
_FOLLOWED_FRAME_COMMANDS = frozenset(_FRAME_FOLLOWERS)

FramePlacement.__module__ = "pyflightstream.script"


class BrokenCommandUse(BaseModel):
    """One command emitted although its evidence record is broken.

    The script records each waived command in the run manifest (FR-07), so
    its dependence on a known-broken command remains explicit.

    Attributes
    ----------
    command : str
        Command name as emitted.
    version : str
        Canonical identifier of the build the script targets.
    source_version : str
        Canonical identifier of the build measured by report. A hotfix can
        inherit this evidence from its base release. Required and nonblank:
        min_length and pattern reject empty or whitespace-only values
        without stripping a stored identifier. The manifest reader refuses
        rows lacking this field and names their manifest and schema stamp.
    report : str
        Repository-relative committed probe report recording the breakage.
        Broken status requires this evidence (CONTRIBUTING.md invariant 3).
    note : str, optional
        Database paraphrase of the probe observation, when recorded.
    reason : str
        Caller justification supplied to Script.allow_broken.
    first_line : str
        First waived script line. This identifies the particular call behind
        the reason; the script-lifetime waiver covers subsequent emissions.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    command: str
    version: str
    source_version: str = Field(min_length=1, pattern=r"\S")
    report: str
    note: str | None = None
    reason: str
    first_line: str = ""


class UnsteadyActionUse(BaseModel):
    """One action the solver runs after each unsteady time step.

    Provenance, like :class:`BrokenCommandUse`: the script collects one
    per registered action so the run record can say what ran beside the
    solver, under which name, and on what evidence.

    THE EVIDENCE FIELD IS THE POINT. SET_NEW_UNSTEADY_SOLVER_ACTION is
    documented on the two newest builds and PROBED ON NONE, so a
    workflow resting on it rests on a page rather than on a run. The
    status is read from the command database at the moment the action is
    registered and carried here, so it is stated once, at build time,
    instead of being assumed by every reader downstream.

    Attributes
    ----------
    name : str
        Action name as registered, unique within one script.
    kind : str
        ``SCRIPT`` for a FlightStream script, ``COMMAND_LINE`` for a
        shell command.
    filename : str
        The path the registration line names, exactly as passed. WHAT IT
        IS RELATIVE TO IS UNSTATED BY BOTH EDITIONS: no manual page says
        which working directory the solver runs an action from
        (RPT-030), so this library records the caller's own string and
        claims nothing about how the solver resolves it. On 26.123 the
        action was measured to run from the simulation folder (RPT-041, the
        script-action re-read probe).
    evidence : str or None
        Recorded status of the command on the script's build
        (``documented``, ``verified``, ``broken``), or None where the
        database holds no record for it.
    inherited : bool
        Whether that status was recorded for this build or inherited
        from its base release. An inherited status is an assumption, and
        a record that cannot show the difference presents one as a
        measurement.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    kind: str
    filename: str
    evidence: str | None = None
    inherited: bool = False


BrokenCommandUse.__module__ = "pyflightstream.script"
UnsteadyActionUse.__module__ = "pyflightstream.script"


def _check_joins(entry: CommandEntry, bound: dict) -> None:
    """Refuse an argument that joins a preceding argument the call left out."""
    for position, spec in enumerate(entry.args):
        if spec.joins_previous and spec.name in bound:
            anchor = entry.args[position - 1]
            if anchor.name not in bound:
                raise CommandArgumentError(
                    f"{entry.name}: {spec.name} needs {anchor.name}, the preceding "
                    f"argument it joins ({entry.citation})"
                )


class _ScriptRendering:
    """The rendering methods of :class:`~pyflightstream.script.Script`, one per layout."""

    def _format_scalar(self, value: object) -> str:
        return str(value)

    def _list_lines(self, spec: ArgSpec, items: list) -> list[str]:
        rendered = [self._format_scalar(item) for item in items]
        if spec.separator is ListSeparator.NEWLINE:
            return rendered
        joiner = "," if spec.separator is ListSeparator.COMMA else " "
        return [joiner.join(rendered)]

    def _render_command(self, entry: CommandEntry, bound: dict) -> tuple[list[str], bool]:
        _check_joins(entry, bound)
        provided = [(spec, bound[spec.name]) for spec in entry.args if spec.name in bound]
        if entry.layout is Layout.BARE:
            return [entry.name], False
        if entry.layout in (Layout.INLINE, Layout.MIXED_INLINE):
            return self._render_inline(entry, provided)
        if entry.layout is Layout.PAYLOAD_LINES:
            return self._render_payload_lines(entry, provided)
        if entry.layout is Layout.PARAM_LINES:
            return self._render_param_lines(entry, provided)
        return self._render_keyword_block(entry, provided)

    def _render_inline(
        self, entry: CommandEntry, provided: list[tuple[ArgSpec, object]]
    ) -> tuple[list[str], bool]:
        """Render an inline command: its values on one line, own-line values after it."""
        inline_parts = [entry.name]
        tail_lines: list[str] = []
        for spec, value in provided:
            if spec.own_line:
                tail_lines.append(self._format_scalar(value))
            elif spec.is_list:
                inline_parts.append(" ".join(self._format_scalar(item) for item in value))  # type: ignore[attr-defined]
            else:
                from pyflightstream.script._build_forms import _check_inline_token

                _check_inline_token(entry, spec, value)
                inline_parts.append(self._format_scalar(value))
        return [" ".join(inline_parts), *tail_lines], bool(tail_lines)

    def _render_payload_lines(
        self, entry: CommandEntry, provided: list[tuple[ArgSpec, object]]
    ) -> tuple[list[str], bool]:
        """Render a payload-lines command: scalars inline, each list on lines after it."""
        inline_parts = [entry.name]
        tail_lines: list[str] = []
        for spec, value in provided:
            if spec.is_list:
                tail_lines.extend(self._list_lines(spec, value))  # type: ignore[arg-type]
            else:
                inline_parts.append(self._format_scalar(value))
        return [" ".join(inline_parts), *tail_lines], True

    def _render_param_lines(
        self, entry: CommandEntry, provided: list[tuple[ArgSpec, object]]
    ) -> tuple[list[str], bool]:
        """Render a param-lines command: one ``NAME value`` line per argument."""
        lines = [entry.name]
        for spec, value in provided:
            if spec.is_list:
                lines.extend(self._list_lines(spec, value))  # type: ignore[arg-type]
            elif spec.type is ArgType.PATH or spec.own_line:
                lines.append(self._format_scalar(value))
            else:
                lines.append(f"{spec.name.upper()} {self._format_scalar(value)}")
        return lines, True

    def _render_keyword_block(
        self, entry: CommandEntry, provided: list[tuple[ArgSpec, object]]
    ) -> tuple[list[str], bool]:
        """Render a keyword-block command: values on its line first, then one keyword per line."""
        lines = [entry.name]
        for spec, value in provided:
            if spec.on_command_line:
                # The leading arguments of a keyword block that sit on the
                # command's own line (WRAPPER_EDIT_LOCAL_CONTROL, FSM-26.120
                # p.314). The schema holds them to the leading positions,
                # so lines[0] is still the command name here.
                lines[0] += f" {self._format_scalar(value)}"
            elif spec.is_list:
                lines.extend(self._list_lines(spec, value))  # type: ignore[arg-type]
            elif spec.type is ArgType.BOOL:
                # Presence keyword (FSM-26.120 p.307): True is the bare keyword
                # line, False emits nothing.
                if value:
                    lines.append(spec.name.upper())
            elif spec.joins_previous:
                lines[-1] += f" {self._format_scalar(value)}"
            else:
                lines.append(f"{spec.name.upper()} {self._format_scalar(value)}")
        if entry.terminator is not None:
            lines.append(entry.terminator)
        return lines, True
