"""The unsteady rotor builder and the rotor motion it emits.

:func:`_build_unsteady_rotor` builds the run type ``unsteady_rotor``;
:func:`emit_rotor_motion` and :func:`_rotor_motions` emit the motion of each
rotor, its moving boundaries, and the shedding of its trailing edges.
"""

from __future__ import annotations

from collections.abc import (
    Mapping,
    Sequence,
)
from pathlib import (
    PurePath,
)

from pyflightstream._errors import (
    PyflightstreamWarning,
    warn,
)
from pyflightstream.cases import (
    CampaignConfigError,
    RotorBlock,
    SimCase,
)
from pyflightstream.cases import (
    setup_surfaces as _setup_surfaces,
)
from pyflightstream.cases._unsteady_actions import (
    register_unsteady_actions,
)
from pyflightstream.script import (
    CommandArgumentError,
    Script,
    helpers,
)

from ._actuator import (
    _actuator_disc,
    _RowActuator,
    _the_actuator_the_row_names,
)
from ._clock import (
    UnsteadyExportThreshold,
    unsteady_export_threshold,
)
from ._conventions import (
    WorkflowConventions,
)
from ._frames import (
    _blade_frames,
    _blade_indices,
    _flat_rotor_frames,
    _moment_frame,
    _refuse_an_unanswered_hub,
    _rotations,
    _rotor_blade_frames,
    _rotor_frame,
    _setup_frames,
    _significant_digits,
    _the_blade_frames_under_their_rotors_names,
    _the_flat_frame_name,
    _translations,
)
from ._freestream import (
    _fluid,
    _free_stream,
    _RowFreestream,
    _the_custom_freestream,
    _wake_termination,
)
from ._geometry import (
    _open_geometry,
)
from ._motion import (
    _clock_speed,
    _motion_view,
    _origin,
)
from ._names import (
    _boundary,
    _group_indices,
    _group_members,
    _named,
    _refuse_name_absent_from_inventory,
    _refuse_name_without_inventory,
    _resolve_token,
)
from ._pproc import (
    _pproc_plots,
)
from ._probes import (
    _pproc_probes,
)
from ._reductions import (
    _blade_count,
)
from ._rows import (
    UNNAMED_ROTOR_RADICAL,
    RotorSpeed,
    _own_speed,
    _point_from_metres,
    _refuse_unregistered_keys,
    _require_the_averaging_window,
    _rotor_of,
    _variable,
    continuation_of,
    rotor_speed,
    row_walltime_s,
)
from ._skeleton import (
    _acoustic_setup,
    _script_tail,
)
from ._solver_settings import (
    _custom_flags,
    _raw_commands,
    _refuse_the_loads_selections_on_a_march,
    _settings,
)
from ._timing import (
    rotor_time_stepping,
)
from ._unsteady import (
    _build_continuation,
    _refuse_cold_start_on_a_march,
)
from ._vocabulary import (
    MOTIONS_VARIABLE,
    MOVING_BOUNDARIES_VARIABLE,
    ROTOR_AXIS_VARIABLE,
    ROTOR_SHEDDING_VARIABLE,
)


def emit_rotor_motion(
    case: SimCase,
    script: Script,
    *,
    frame: int | str,
    moving_frames: Sequence[int | str] | str | None = "all",
    speed: RotorSpeed | None = None,
) -> int:
    """Emit one rotary motion entirely from what the row declares.

    Motion, its type, its coordinate system, its rotor axis, its rotor
    speed and its moving boundaries, with nothing hand-written between the
    matrix cell and the command.

    THE VOCABULARY FOLLOWS THE BUILD, and it is decided in one place:
    :func:`pyflightstream.script.helpers.rotary_motion` writes a ``ROTARY``
    motion with its axis and speed where the build documents them, and a
    ``EUCLIDEAN`` motion with the speed as an angular velocity plus the rotor
    mark where ``script.rotor_vocabulary.euclidean_rotor`` holds (measured on
    26.000 by RPT-049), and the angular velocity in rev/min with no mark where
    ``script.rotor_vocabulary.unmarked_euclidean_rotor`` holds (26.100,
    RPT-051). Coverage counts both substitutes through ``_carried``, so the
    workflow writes them on 25.100, 26.000 and 26.100.
    :func:`require_coverage` refuses 25.000, which has the whole Euclidean
    rotor and no ``CREATE_NEW_MOTION``, before this runs.

    Parameters
    ----------
    case : SimCase
        The case; its variables carry the rotor speed in rev/min
        (``RPM``), the rotor axis within ``frame`` (``ROTOR_AXIS``, one
        of X, Y, Z) and optionally the moving boundaries
        (``MOVING_BOUNDARIES``, comma-separated boundary NAMES, family
        names, or 1-based positions; absent means every boundary). A
        family name is a boundary label with its trailing number
        removed, so ``Blade`` selects every blade the opened geometry
        carries and one cell is right for a sector mesh and a full
        wheel alike. Positions still work and warn: they belong to one
        file's boundary order and name different surfaces in a file
        that orders them differently. Names resolve only where the
        geometry was opened by this package, which is what declares
        the inventory. A matrix row stating ``ROTOR_SHEDDING`` is
        refused in 0.29.0 before this function runs
        (:func:`_refuse_rotor_shedding`, called by every builder and by
        :func:`build_script`). Called directly on a case that bypassed
        that refusal, this function still reads the key and emits
        nothing for it; see :func:`rotor_shedding_direction` for why.
    script : Script
        Script under construction. Nothing is emitted into it until
        every value has been read and converted, so a refusal leaves it
        exactly as it was.
    frame : int or str
        Local coordinate system of the rotation, by index or by its
        creation label; it must exist earlier in the script.
    moving_frames : sequence, ``"all"`` or None
        Local frames attached to the motion; ``"all"`` is the default.
    speed : RotorSpeed, optional
        The already-resolved rotor speed of THIS case; resolved here
        when not given, which is what every caller outside the builders
        does.

    Returns
    -------
    int
        Identifier of the created motion, for later citations.

    Raises
    ------
    CampaignConfigError
        If the row declares no rotor speed or no rotor axis, declares
        one that is not a number, or declares a ``ROTOR_SHEDDING``
        direction that is neither of the two. The message names the case
        (whose ``sim_id`` IS the matrix POL) and the KEY.
    """
    rpm = _own_speed(case, speed).rpm
    axis = _variable(case, ROTOR_AXIS_VARIABLE)
    if axis is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares no {ROTOR_AXIS_VARIABLE}, and a rotary "
            "motion turns about a named axis of its own coordinate system. Add it to "
            f"the row's variables as '{ROTOR_AXIS_VARIABLE}: X' (or Y, or Z)."
        )
    boundaries: Sequence[int | str] | str = "all"
    declared = _variable(case, MOVING_BOUNDARIES_VARIABLE)
    if declared is not None:
        boundaries = _moving_boundaries(case, script, declared)
        if not boundaries:
            raise CampaignConfigError(
                f"case {case.sim_id!r} declares {MOVING_BOUNDARIES_VARIABLE} as "
                f"{declared!r}, which names no boundary at all. Leave the key out to "
                "move every boundary, or list the ones that move."
            )
    # READ AND NOT EMITTED, deliberately: the shedding direction is a
    # component-file field and no command carries it, so this call cannot
    # act on it. It is read HERE because this is the function a rotor row
    # goes through, and a row declaring ROTOR_SHEDDING: diagonal that
    # built a perfectly good script would be told nothing at all. The
    # refusal lands before the first emission, like every other read
    # above it.
    rotor_shedding_direction(case)
    motion_id = helpers.rotary_motion(
        script,
        frame=frame,
        axis=axis.upper(),
        rpm=rpm,
        boundaries=boundaries,
        moving_frames=moving_frames,
    )
    _setup_surfaces.emit_wake_stabilization(script, case, motion_id, _blade_count(case))
    return motion_id


def _moving_boundaries(case: SimCase, script: Script, cell: str) -> list[int | str]:
    """Resolve a boundary-citing cell against the opened geometry's names.

    THE RULE, and the one sentence this function exists for:
    nowhere in this package should a user work with indices. A row names
    the mesh family and the package makes the link to the solver's
    indices (PFS-2028.00).

    A token resolves in this order, and the order is load-bearing:

    1. an exact boundary label of the opened geometry, so a row can
       always name one surface;
    2. otherwise an ALIAS the row's setup defines in its ``[aliases]``
       table (the design decision of 2026-09-09), whose members resolve as names
       do, a member the file lacks ignored;
    3. otherwise a FAMILY, which is a label with its trailing index
       removed, so ``Blade`` selects every blade the file carries and one
       cell is correct for a sector mesh and a full wheel alike;
    4. otherwise a 1-based POSITION, which still works and now warns,
       naming the surfaces those positions actually select;
    5. otherwise a GROUP of the row's pproc artifact, spelled
       ``g<number>`` (``g4`` is ``[groups]`` entry ``"4"``), resolved to
       the members the geometry carries the way the polar tables resolve
       it, and refused when it names nothing the file holds
       (PFS-2028.00, "MOVING_BOUNDARIES accepts ENTRY group names");
    6. otherwise the token is refused, listing the labels the geometry
       declared.

    The alias sits between the two so a preset's word cannot shadow a
    label the file actually carries. Exact before family is not
    arbitrary either. ``Blade1`` is both a label and
    a member of family ``blade``, so trying the family first would
    silently turn a row citing ONE blade into a row citing six, which is
    the same class of silent wrong answer this release exists to end.

    Parameters
    ----------
    case : SimCase
        The case; its ``sim_id`` is the matrix POL the messages name.
    script : Script
        Script under construction, with the geometry already opened and
        therefore its inventory already declared.
    cell : str
        The raw cell text, comma separated.

    Returns
    -------
    list of int or str
        Boundary indices in ascending order once every token resolved.
        A list that still holds a string is returned as written, so the
        script layer raises its own refusal naming the declared labels
        rather than this function inventing a second one.

    Notes
    -----
    WITH NO INVENTORY DECLARED THIS IS EXACTLY 0.10.0. A script that
    opened no geometry, or opened one carrying no mesh block, has no
    labels, and every token then goes through :func:`_boundary` as it
    always did. That is what keeps a direct builder call, and every
    committed golden behind one, byte for byte unchanged.
    """
    tokens = [token.strip() for token in cell.split(",") if token.strip()]
    labels = script.entities.labels("boundaries")
    if not labels:
        # PFS-2029.12: a NAME against no inventory is refused here, saying
        # why there is no inventory, instead of reaching the script layer
        # as "no labels are registered yet", which blamed the row.
        for token in tokens:
            if not isinstance(_boundary(token), int):
                _refuse_name_without_inventory(case, MOVING_BOUNDARIES_VARIABLE, token)
        return [_boundary(token) for token in tokens]
    resolved: list[int | str] = []
    positional: list[str] = []
    for token in tokens:
        found = _resolve_token(case, token, labels)
        if found:
            resolved.extend(found)
            continue
        read = _boundary(token)
        if isinstance(read, int):
            positional.append(token)
        else:
            members = _group_members(case, token)
            if members is not None:
                resolved.extend(_group_indices(case, token, members, labels))
                continue
            _refuse_name_absent_from_inventory(case, MOVING_BOUNDARIES_VARIABLE, token, labels)
        resolved.append(read)
    if positional:
        selected = ", ".join(
            f"{position} is {_named(position, labels, script.num_boundaries)}"
            for position in sorted({int(token) for token in positional})
        )
        warn(
            f"case {case.sim_id!r} states {MOVING_BOUNDARIES_VARIABLE} as {cell!r}, and "
            f"{', '.join(positional)} name a POSITION in this geometry's boundary order "
            f"rather than a surface. Against {PurePath(str(case.geometry)).name}, {selected}. "
            "A position is right for the one file it was written against and means a "
            "different surface in any file that orders them differently, and nothing would "
            "say so. Write the names instead; a family name such as the label without its "
            "trailing number selects every member the file carries.",
            PyflightstreamWarning,
            stacklevel=3,
        )
    if all(isinstance(item, int) for item in resolved):
        return sorted({int(item) for item in resolved})
    return resolved


# --- PFS-2026.06: the azimuthal shedding option, off the same row -------------


def rotor_shedding_direction(case: SimCase) -> str | None:
    """Return the relaxed-wake shedding direction this rotor row asks for.

    The direction is a field of the relaxed trailing-edge COMPONENT
    specification and not a scripting argument (SRC-751 p.85), so no
    workflow emits it. This function parses the value for the Python
    helper :func:`rotor_relaxed_trailing_edges`, which applies it to the
    specifications a component definition carries. A matrix row stating
    ``ROTOR_SHEDDING`` is refused in 0.29.0 by every matrix workflow,
    since none applies it (see ``docs/migrating-to-0.29.0.md``);
    direction control from the matrix is planned for 0.30.0.

    Parameters
    ----------
    case : SimCase
        The case; ``ROTOR_SHEDDING`` in its variables carries ``AXIAL``
        or ``0`` for the axial direction, which is the default, and
        ``AZIMUTH`` or ``1`` for the azimuth direction, which 26.123
        adds and which is the one a rotor case is likely to want.

    Returns
    -------
    str or None
        ``"AXIAL"``, ``"AZIMUTH"``, or None where the row does not
        declare the key. None is the statement "this row asks nothing",
        and it is distinct from ``"AXIAL"``: a row asking for nothing
        leaves a three-value specification at three values, while a row
        asking for the axial direction states it on every specification
        that already states one.

    Raises
    ------
    CampaignConfigError
        If the row declares a direction that is neither. The message
        names the case, the KEY, the value written and both accepted
        directions, on this module's own rule that a matrix value is
        refused by the cell the user typed rather than by the
        command.

    Examples
    --------
    >>> from pyflightstream.cases import SimCase, SweepAxis
    >>> from pyflightstream.cases.workflows import rotor_shedding_direction
    >>> case = SimCase(
    ...     sim_id="7001",
    ...     aircraft="RotorRig",
    ...     sweep=SweepAxis(type="alpha", values=[0.0]),
    ...     recipe="unsteady_rotor",
    ...     variables={"ROTOR_SHEDDING": "azimuth"},
    ... )
    >>> rotor_shedding_direction(case)
    'AZIMUTH'
    """
    text = _variable(case, ROTOR_SHEDDING_VARIABLE)
    if text is None:
        return None
    try:
        return helpers.resolve_shedding_direction(text, context=f"case {case.sim_id!r}")
    except CommandArgumentError as error:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {ROTOR_SHEDDING_VARIABLE} as {text!r}, and "
            "the direction a relaxed trailing edge sheds its wake in is AXIAL (0), the "
            "default, or AZIMUTH (1), which is the rotor option 26.123 adds. Matrix "
            "variables arrive as text, so the refusal happens here rather than at the "
            f"specification, whose message would not name your row. The library says: "
            f"{error}"
        ) from error


def rotor_relaxed_trailing_edges(case: SimCase, specifications: Sequence[str]) -> list[str]:
    """Restate a rotor case's relaxed trailing edges in the row's direction.

    THIS IS THE ROUTE TO THE AZIMUTHAL OPTION in 0.29.0, from Python: a
    case whose variables carry ``ROTOR_SHEDDING: AZIMUTH`` is passed here
    with the specifications its component definition carries, and they
    come back with the direction value set. A MATRIX ROW stating
    ``ROTOR_SHEDDING`` is refused in 0.29.0, because no workflow command
    applies it (see ``docs/migrating-to-0.29.0.md``); direction control
    from the matrix is planned for 0.30.0. The library writes no
    component file, so the rendered text is returned for the caller to
    write where their geometry keeps it.

    Parameters
    ----------
    case : SimCase
        The case, whose ``ROTOR_SHEDDING`` variable carries the
        direction; see :func:`rotor_shedding_direction`.
    specifications : sequence of str
        The relaxed trailing-edge specifications as the component
        definition carries them, three values or four (SRC-752 p.85).

    Returns
    -------
    list of str
        One rendered specification per input, in the same order. A
        three-value specification comes back with three values where the
        row asks for nothing or for the axial direction, because those
        are what it already means; it gains the direction only where
        the row asks for the azimuth direction.

    Raises
    ------
    CampaignConfigError
        If the row's direction is neither of the two, if a specification
        cannot be read, or if ``specifications`` is a single string or
        something that cannot be iterated. Every message names the case,
        and the unreadable-specification one names which of how many: a
        component definition carries one per trailing edge, so "one of
        them is malformed" is not an answer a reader can act on.

    Examples
    --------
    >>> from pyflightstream.cases import SimCase, SweepAxis
    >>> from pyflightstream.cases.workflows import rotor_relaxed_trailing_edges
    >>> case = SimCase(
    ...     sim_id="7001",
    ...     aircraft="RotorRig",
    ...     sweep=SweepAxis(type="alpha", values=[0.0]),
    ...     recipe="unsteady_rotor",
    ...     variables={"ROTOR_SHEDDING": "AZIMUTH"},
    ... )
    >>> rotor_relaxed_trailing_edges(case, ["0.5;0.1;0.9"])
    ['0.5;0.1;0.9;1']
    """
    # A bare string is a SEQUENCE of characters, so one specification
    # passed without its list would be read as thirteen unreadable ones
    # and refused by position; and an iterator has no length at all,
    # which would leave a bare TypeError out of a public name. Both are
    # named here rather than discovered downstream.
    if isinstance(specifications, str):
        raise CampaignConfigError(
            f"case {case.sim_id!r}: rotor_relaxed_trailing_edges takes a SEQUENCE of "
            f"relaxed trailing-edge specifications and was given the single string "
            f"{specifications!r}, which would be read one character at a time. A "
            f"component definition carries as many as it has trailing edges, so one "
            f"goes in a list, for example [{specifications!r}]"
        )
    try:
        listed = list(specifications)
    except TypeError as error:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: rotor_relaxed_trailing_edges takes a sequence of "
            f"relaxed trailing-edge specifications and was given "
            f"{type(specifications).__name__} {specifications!r}, which cannot be "
            f"iterated. The library says: {error}"
        ) from error
    direction = rotor_shedding_direction(case)
    total = len(listed)
    rendered: list[str] = []
    for position, text in enumerate(listed, start=1):
        try:
            edge = helpers.parse_relaxed_trailing_edge(text)
        except CommandArgumentError as error:
            raise CampaignConfigError(
                f"case {case.sim_id!r} carries a relaxed trailing-edge specification "
                f"this package cannot read, number {position} of {total}. A "
                "specification is a semicolon-separated field list written where the "
                f"component is defined, not a script line. The library says: {error}"
            ) from error
        if direction is not None:
            edge = edge.with_shedding(direction)
        rendered.append(edge.render())
    return rendered


def _build_unsteady_rotor(case: SimCase, script: Script, conventions: WorkflowConventions) -> None:
    """Build a blade-resolved rotor run: open, rotor frame, motion, time loop.

    The open is FIRST and only where the case names a geometry
    (:func:`_open_geometry`). It has to precede the coordinate system
    rather than merely appear somewhere: ``OPEN`` replaces the whole
    simulation state, so a frame created before it would be discarded
    with nothing said, and the rotary motion would then turn about a
    frame that no longer exists.
    """
    _refuse_the_loads_selections_on_a_march(case)
    _refuse_cold_start_on_a_march(case, "unsteady_rotor")
    # A CONTINUATION IS A DIFFERENT SCRIPT, not this one with a shorter
    # march: the branch is here because every line below starts from a
    # mesh, and a continuation starts from the state a stopped run saved.
    continuation = continuation_of(case)
    if continuation is not None:
        _build_continuation(
            case,
            script,
            conventions,
            *continuation,
            threshold=unsteady_export_threshold(case, conventions, version=script.version),
        )
        return
    # Resolved before the first emission, as every refusal of a row key
    # is; a row stating no threshold pays nothing here.
    threshold = unsteady_export_threshold(case, conventions, version=script.version)
    _refuse_unregistered_keys(case, "unsteady_rotor")
    _require_the_averaging_window(case, "unsteady_rotor")
    disc = _the_actuator_the_row_names(case)
    custom = _the_custom_freestream(case)
    _raw_commands(case, script, "control")
    _custom_flags(case, script, "control")
    _raw_commands(case, script, "geometry")
    _custom_flags(case, script, "geometry")
    _open_geometry(case, script)
    _raw_commands(case, script, "setup")
    _custom_flags(case, script, "setup")
    _refuse_an_unanswered_hub(case)
    frame = _moment_frame(case, script)
    # THE ROTOR'S HUB FRAME, named <ALIAS>_SMRP for the rotor the reference
    # declares and placed at its hub, unless the row states ROTOR_ORIGIN.
    #
    # NOT ON A MOTIONS ROW. Each record creates its own rotor's hub frame,
    # under the same <ALIAS>_SMRP name, so creating one here too put ONE
    # NAME AT TWO INDICES and a pproc entry citing it resolved to whichever
    # the frame table happened to hold. The package-level frame this
    # replaced had a different name and could not collide, which is why the
    # duplicate arrived with the rename (measured on the tour's rotor row).
    rotor_frame = None if case.motions else _rotor_frame(case, script)
    if rotor_frame is None and not case.motions:
        # NOTHING SAYS WHERE THE ROTOR IS: no block, no recorded position,
        # no ROTOR_ORIGIN. The frame goes at the origin, which is what this
        # builder has always done for a row that states nothing, and the
        # NAME is the alias-shaped default rather than a package-level one.
        rotor_frame = helpers.coordinate_frame(
            script,
            name=_the_flat_frame_name(case),
            origin=(0.0, 0.0, 0.0),
            x_axis=(1.0, 0.0, 0.0),
            y_axis=(0.0, 1.0, 0.0),
            label="rotor",
        )
    setup_frames = _setup_frames(case, script)
    if case.motions:
        _rotor_motions(
            conventions,
            case,
            script,
            frame,
            rotor_frame,
            threshold,
            setup_frames,
            disc=disc,
            custom=custom,
        )
        return
    # NARROWED, not asserted: the branch above raises when this is None and
    # the row states no MOTIONS, and a row that states them returned there.
    assert rotor_frame is not None
    blade_frames = _blade_frames(case, script, rotor_frame)
    rotor_frames = _flat_rotor_frames(case, rotor_frame)
    frames: dict[str, int | None | Mapping[str, int]] = {
        "MRP": frame,
        **rotor_frames,
        "BLADE_AXIS": blade_frames or None,
        # THE SAME FRAMES UNDER THEIR ROTOR'S NAMES. A flat row creates
        # BladeAxis<k>, which is what its goldens carry; a pproc entry
        # citing LOCAL_AXIS expands to <ALIAS>_RMRP<k>, and without this
        # the entry resolved on a MOTIONS row and silently on nothing here.
        # One frame, two names, which is what `named` already does for a
        # record's own hub.
        **_the_blade_frames_under_their_rotors_names(case, blade_frames),
    }
    frames.update(setup_frames)
    moved = {"MRP": frame, **rotor_frames, **setup_frames}
    followers = {name: sorted(blade_frames.values()) for name in rotor_frames}
    frames.update(_translations(case, script, moved, followers=followers))
    frames.update(
        _rotations(
            case,
            script,
            moved,
            followers=followers,
            spinning={name: _blade_indices(case, script) for name in rotor_frames},
        )
    )
    _actuator_disc(case, script, frames, disc)
    _pproc_plots(case, script, frames)
    _pproc_probes(case, script, frames, unsteady=True, analysis=False)
    _significant_digits(case, script)
    _free_stream(case, script, frames, custom)
    _fluid(case, script)
    # RESOLVED ONCE AND THREADED. The ratio was previously converted
    # twice per case, here and again for the clock, which is the saving
    # the `speed` parameter was added for and was not collecting.
    speed = rotor_speed(case)
    # The blade axis frames turn with the blades (PFS-2029.11.03); with
    # none created the motion keeps its every-frame default, as before.
    emit_rotor_motion(
        case,
        script,
        frame="rotor",
        speed=speed,
        moving_frames=sorted(blade_frames.values()) if blade_frames else "all",
    )
    # THE CLOCK COMES OFF THE SAME RESOLVER THE WINDOW USES, so a row
    # stating its azimuthal step and its revolutions emits the seconds
    # and the step count those work out to, and a row stating the
    # seconds and the count emits exactly what it always emitted.
    _acoustic_setup(case, script)
    stepping = rotor_time_stepping(case, speed=speed)
    helpers.unsteady_solver(
        script,
        time_iterations=stepping.time_iterations,
        delta_time=stepping.delta_time_s,
    )
    _settings(case, script, wake_termination_time_steps=_wake_termination(case, stepping))
    register_unsteady_actions(script, threshold, walltime=row_walltime_s(case) is not None)
    _script_tail(conventions, case, script, frame, unsteady=True, frames=frames)


def _refuse_one_rotor_moved_twice(case: SimCase, rotors: Sequence[RotorBlock | None]) -> None:
    """Refuse a row whose MOTIONS list names one rotor more than once.

    ONE ROTOR HAS ONE SET OF FRAMES. Two records naming one alias built
    ``<ALIAS>_SMRP`` twice, at two indices, and the name table kept the
    LAST, so the script carried the name twice and the two motions turned
    about different coordinate systems. It was masked by a label collision
    that fires only when the rotor's blade families are in the mesh, and
    that refusal names neither the alias nor the case; on a sector mesh
    carrying none of them nothing refused at all (the QA lens of the 0.15.0
    release review, measured on the emitted script).

    A ROW THAT MOVES ONE ROTOR TWICE IS ASKING FOR TWO SPEEDS FOR ONE
    THING, which is the shape this package refuses wherever a row states a
    rotor twice. If two speeds are wanted in one run, they are two rotors.

    Raises
    ------
    CampaignConfigError
        A rotor alias appears in more than one record, naming it.
    """
    seen: dict[str, int] = {}
    for block in rotors:
        if block is None:
            continue
        seen[block.alias] = seen.get(block.alias, 0) + 1
    twice = sorted(alias for alias, count in seen.items() if count > 1)
    if not twice:
        return
    raise CampaignConfigError(
        f"case {case.sim_id!r} states {MOTIONS_VARIABLE} naming "
        f"{', '.join(repr(alias) for alias in twice)} more than once. One rotor has one "
        "hub and one set of frames, so two records naming it ask for two speeds for one "
        "thing and the script would carry its frame name twice at two indices. Write one "
        "record per rotor; if two speeds are wanted in one run, they are two rotors and "
        "the reference declares two blocks."
    )


def _rotor_motions(
    conventions: WorkflowConventions,
    case: SimCase,
    script: Script,
    frame: int | None,
    rotor_frame: int | None,
    threshold: UnsteadyExportThreshold | None,
    setup_frames: Mapping[str, int],
    *,
    disc: _RowActuator | tuple[_RowActuator, ...] | None = None,
    custom: _RowFreestream | None,
) -> None:
    """Finish a rotor script whose row states N motions (PFS-2029.11.03).

    N records, N motions, each with its own fixed frame at its hub and its
    own moving frame attached to it by ``SET_MOTION_MOVING_FRAMES``
    (documented on every build, SRC-003 p.333, and verified on none).

    THE FRAMES TAKE THE ROTOR'S ALIAS AS THEIR RADICAL (FR-62, the design
    of 2026-09-10): ``<ALIAS>_SMRP`` at the hub, static; ``<ALIAS>_RMRP``
    turning with the motion; and ``<ALIAS>_RMRP<k>`` per blade of the
    block's ``families_blades``, turning with blade k and numbered from
    the ``blade1`` datum. A family of ``families_general`` gets no frame
    of its own: its local frame IS the rotor's, which is what makes the
    spinner ride the hub. The names a record's frames had at 0.14.0,
    ``PROP_MRP<k>`` and ``RotorAxis<k>``, do NOT resolve: they were
    positional, so a pproc entry citing one silently followed the ORDER of
    the MOTIONS list, and an entry citing one now is refused naming the
    shape to write.

    There is no package-level rotor frame. The time step follows the motion
    ``CLOCK_MOTION`` names, and the fastest rotor when a row names none
    (FR-64).
    """
    views = [_motion_view(case, record) for record in case.motions]
    rotors = [_rotor_of(case, record) for record in case.motions]
    _refuse_one_rotor_moved_twice(case, rotors)
    # A RECORD NAMING NO ROTOR takes the default radical, `ROTOR<k>`, which
    # is the alias-shaped name of an unnamed rotor. It does NOT keep the
    # 0.14.0 names: those were positional and went with the package-level
    # frame. Only a matrix converted with no workspace produces one, because
    # a record reaching the builder through a workspace names a rotor.
    radicals = [(rotor.alias if rotor is not None else None) for rotor in rotors]
    moving: list[int] = []
    hubs: list[int] = []
    blade_frames: dict[str, int] = {}
    for number, (view, rotor, radical) in enumerate(
        zip(views, rotors, radicals, strict=True), start=1
    ):
        origin = (
            _point_from_metres(view, script, rotor.origin, "rotor x_m/y_m/z_m")
            if rotor is not None
            else _origin(view)
        )
        # EVERY FRAME CARRIES ITS ROTOR'S ALIAS. A record naming no rotor
        # used to fall back to ROTOR_MRP<k> and RotorAxis<k>, positional
        # names that only mean anything beside the row that made them; the
        # record that produced them is refused before this point.
        # EVERY FRAME CARRIES A RADICAL, AND IT IS THE ROTOR'S ALIAS. A
        # record naming no rotor takes the default radical and its position;
        # the positional PROP_MRP<k> and RotorAxis<k> are gone with the
        # one-propulsor assumption that made them readable.
        stem = radical or f"{UNNAMED_ROTOR_RADICAL}{number}"
        hub_name = f"{stem}_SMRP"
        moving_name = f"{stem}_RMRP"
        hubs.append(
            helpers.coordinate_frame(
                script,
                name=hub_name,
                origin=origin,
                x_axis=(1.0, 0.0, 0.0),
                y_axis=(0.0, 1.0, 0.0),
                label=f"rotor:{number}",
            )
        )
        moving.append(
            helpers.coordinate_frame(
                script,
                name=moving_name,
                origin=origin,
                x_axis=(1.0, 0.0, 0.0),
                y_axis=(0.0, 1.0, 0.0),
                label=f"rotor_moving:{number}",
            )
        )
        if rotor is not None:
            # `rotor.alias`, not `radical`: they are the same string here
            # and only this one is visibly non-None, the other having been
            # zipped out of a list that carries a None for every record
            # naming no rotor.
            blade_frames.update(_rotor_blade_frames(script, rotor, hubs[-1], rotor.alias, view))
    frames: dict[str, int | None | Mapping[str, int]] = {
        "MRP": frame,
        "BLADE_AXIS": None,
    }
    frames.update(setup_frames)
    # A record's own frames are citable by the names the solver shows
    # (<ALIAS>_SMRP, <ALIAS>_RMRP, ...), and a rotor's moving frame follows
    # its hub frame the way the blade frames follow it (PFS-2034.02).
    named: dict[str, int | None] = {"MRP": frame, **setup_frames}
    followers: dict[str, list[int]] = {}
    spinning: dict[str, list[int]] = {}
    labels = script.entities.labels("boundaries")
    for number, (hub, axis, view, radical) in enumerate(
        zip(hubs, moving, views, radicals, strict=True), start=1
    ):
        # ONE NAME PER FRAME, and it is the rotor's alias. The positional
        # PROP_MRP<k> and RotorAxis<k> stood beside it until 0.15.0 and are
        # gone: they read as a name and were an index, so a pproc entry
        # citing one silently followed the ORDER of the MOTIONS list.
        stem = radical or f"{UNNAMED_ROTOR_RADICAL}{number}"
        named[f"{stem}_SMRP"] = hub
        named[f"{stem}_RMRP"] = axis
        followers[f"{stem}_SMRP"] = [axis]
        cell = str(_variable(view, MOVING_BOUNDARIES_VARIABLE) or "")
        # Names only: a token that is not a name is the motion's own to
        # refuse or warn about, when it is emitted below.
        turning = sorted(
            {
                index
                for token in cell.split(",")
                if token.strip()
                for index in _resolve_token(case, token.strip(), labels)
            }
        )
        spinning[f"{stem}_SMRP"] = turning
    # THE BLADE FRAMES JOIN `named` BEFORE THE ROTATIONS, not after them.
    # They were merged into `frames` on the line below the call, which is
    # after `_rotations` has run, so a rotation could not cite one and,
    # once the alias carried its own frames (FR-71), could not TURN one
    # either: a row turning a rotor left its per-blade frames behind, which
    # is the same defect the release fixed one layer up for the motion.
    # ONLY THE FRAME-NAMED HALF. `_rotor_blade_frames` returns two keys per
    # blade, the frame's own `<ALIAS>_RMRP<k>` and the blade's mesh FAMILY,
    # because a pproc entry may cite either. Merging both put family names
    # into the frame namespace, so `AXIS: Blade_1-Y` resolved as a
    # coordinate system and the refusal listing "the frames this case
    # defines" taught a vocabulary that does not exist (the architecture
    # lens, 2026-09-10; measured: it was accepted).
    named.update({name: index for name, index in blade_frames.items() if "_RMRP" in name})
    frames.update(_translations(case, script, named, followers=followers))
    frames.update(_rotations(case, script, named, followers=followers, spinning=spinning))
    # The pproc entries cite a rotor's frames by the same names (the reference p001
    # of 2026-09-09: PUSHER_X in ROTOR_MRP2 while the lifters spin).
    frames.update({name: index for name, index in named.items() if index is not None})
    frames.update(blade_frames)
    _actuator_disc(case, script, frames, disc)
    _pproc_plots(case, script, frames)
    _pproc_probes(case, script, frames, unsteady=True, analysis=False)
    _significant_digits(case, script)
    _free_stream(case, script, frames, custom)
    _fluid(case, script)
    speeds = [rotor_speed(view) for view in views]
    for number, (view, radical) in enumerate(zip(views, radicals, strict=True), start=1):
        # THE BLADE FRAMES TURN WITH THE BLADES, and until this line they
        # were created and then stood still: the payload carried the
        # rotor's own moving frame alone, so a per-blade product would
        # have been read in a frame that never moved. The technical
        # writing lens named the measurement rather than the outcome, and
        # the measurement said the docstring overstated (2026-09-10).
        turning = [moving[number - 1]]
        if radical:
            turning += sorted(
                {
                    index
                    for name, index in blade_frames.items()
                    if name.startswith(f"{radical}_RMRP")
                }
            )
        emit_rotor_motion(
            view,
            script,
            frame=f"rotor:{number}",
            speed=speeds[number - 1],
            moving_frames=turning,
        )
    _acoustic_setup(case, script)
    stepping = rotor_time_stepping(case, speed=_clock_speed(case, views, speeds))
    helpers.unsteady_solver(
        script,
        time_iterations=stepping.time_iterations,
        delta_time=stepping.delta_time_s,
    )
    _settings(case, script, wake_termination_time_steps=_wake_termination(case, stepping))
    register_unsteady_actions(script, threshold, walltime=row_walltime_s(case) is not None)
    _script_tail(conventions, case, script, frame, unsteady=True, frames=frames)
