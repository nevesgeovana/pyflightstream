"""The rotor a row turns: its motion record, its clock speed and its Mach numbers.

A row names its rotors by the alias of a motion record (``MOTIONS``) or by
the flat rotor keys; :func:`_motion_view` resolves the record,
:func:`_clock_speed` the speed the unsteady clock reads, and
:func:`rotor_machs` the Mach numbers of every rotor and actuator disc the
row turns.
"""

from __future__ import annotations

import math
from collections.abc import (
    Callable,
    Mapping,
    Sequence,
)

from pyflightstream._deprecations import (
    ROW_MOVING_BOUNDARIES,
    refusal_text,
)
from pyflightstream.cases import (
    AXIS_UNIT_VECTORS,
    CampaignConfigError,
    SimCase,
)

from ._actuator import (
    _the_actuator_the_row_names,
)
from ._rows import (
    UNNAMED_ROTOR_RADICAL,
    RotorMach,
    RotorSpeed,
    _admit_a_row_hand,
    _rotor_frame_axis,
    _rotor_of,
    _stated_advance_ratio,
    _states_a_rotor_speed,
    _the_rotor_a_flat_row_turns,
    _variable,
    _velocity,
    advancing_tip_mach_number,
    free_stream_direction,
    rotor_mach_numbers,
    rotor_speed,
)
from ._vocabulary import (
    ACTUATOR_VARIABLE,
    ADVANCE_RATIO_VARIABLE,
    BLADES_VARIABLE,
    CLOCK_MOTION_VARIABLE,
    MOTIONS_VARIABLE,
    MOVING_BC_ALIAS_VARIABLE,
    MOVING_BOUNDARIES_VARIABLE,
    QSTEADY_ROTOR,
    ROTOR_AXIS_VARIABLE,
    ROTOR_ORIGIN_POINT_KEY,
    ROTOR_ORIGIN_VARIABLE,
    RPM_SIGN_VARIABLE,
    RPM_VARIABLE,
)


def rotor_machs(case: SimCase) -> list[RotorMach]:
    """Return the tip and helical Mach numbers of every rotor and disc a row turns.

    Three row types carry them (M1): every ``unsteady_rotor`` and
    ``qsteady_rotor`` row,
    every ``steady`` row that states ``RPM``, and every row, of any run type,
    that names an actuator disc (``ACTUATOR``). Each rotor and each disc is
    one :class:`RotorMach`.

    The case is the point's (:func:`pyflightstream.cases.case_at_point`), so
    the free-stream speed and the speed of sound are that point's resolved
    flight condition, the velocity a static rig derives from its advance
    ratio and speed included; at ``V = 0`` the helical number is the tip's.
    A rotor's speed is the one the run turns (:func:`rotor_speed`, per motion
    record where the row states ``MOTIONS``) and its diameter the rotor
    block's, else the reference's ``rotor_diameter_m``. A disc's speed is the
    one its builder resolves, ``ACTUATOR_RPM`` or the speed its advance ratio
    works out to against the disc's own diameter, and its diameter is twice
    its ``tip_radius_m``.

    NEVER RAISES for a row the builder would refuse: a quantity that cannot
    be resolved is a :class:`RotorMach` whose ``note`` names the row and what
    is missing, because an addition by the package may not refuse a run. A
    rotor with no known diameter is said so, never guessed.

    Parameters
    ----------
    case : SimCase
        The point's case, with its flight condition resolved.

    Returns
    -------
    list of RotorMach
        One per rotor, then one per disc; empty for a row of none of the
        three types.
    """
    where = f"POL {case.sim_id}"
    try:
        velocity: float | None = _velocity(case)
    except CampaignConfigError:
        velocity = None
    sound = None if case.fluid is None else case.fluid.sonic_velocity_m_per_s

    def one(
        alias: str,
        rpm: float | None,
        diameter: float | None,
        why: str | None,
        *,
        kind: str = "rotor",
        axis: tuple[float, float, float] | None = None,
    ) -> RotorMach:
        note = why
        if note is None and diameter is None:
            note = (
                f"{where}: rotor {alias} has no known radius: its reference declares no "
                "rotor block for it and states no rotor_diameter_m, so its tip and "
                "helical Mach numbers are not computed"
            )
        if note is None and velocity is None:
            note = f"{where}: {kind} {alias}: the row resolves no free-stream speed"
        if note is None and not sound:
            note = f"{where}: {kind} {alias}: the row resolves no speed of sound"
        if note is not None or rpm is None or diameter is None or velocity is None or not sound:
            return RotorMach(alias, rpm, diameter, velocity, sound, None, None, note, kind)
        tip, helical = rotor_mach_numbers(
            rpm=rpm,
            diameter_m=diameter,
            velocity_m_per_s=velocity,
            sonic_velocity_m_per_s=sound,
        )
        # FR-1201: the advancing tip; an axis the row cannot resolve gives the
        # edgewise bound, which the record and the plan line say.
        advancing, resolved = advancing_tip_mach_number(
            rpm=rpm,
            diameter_m=diameter,
            velocity_m_per_s=velocity,
            sonic_velocity_m_per_s=sound,
            flow_direction=None if axis is None else free_stream_direction(case),
            axis=axis,
        )
        return RotorMach(
            alias, rpm, diameter, velocity, sound, tip, helical, None, kind, advancing, resolved
        )

    machs: list[RotorMach] = []
    if case.recipe in ("unsteady_rotor", QSTEADY_ROTOR) or (
        case.recipe == "steady" and _states_a_rotor_speed(case)
    ):
        machs.extend(_rotor_machs(case, where, one))
    if _variable(case, ACTUATOR_VARIABLE) is not None:
        machs.extend(_disc_machs(case, where, one))
    return machs


def _rotor_machs(case: SimCase, where: str, one: Callable[..., RotorMach]) -> list[RotorMach]:
    """Return the rotors' half of :func:`rotor_machs`."""
    if case.motions:
        turning, lost = _the_rotors_the_row_turns(case)
        machs = [
            one(
                alias,
                float(speed.rpm),
                case.rotors[alias].diameter_m if alias in case.rotors else None,
                None,
                axis=case.rotors[alias].axis_vector if alias in case.rotors else None,
            )
            for alias, _view, speed in turning
        ]
        machs.extend(
            one(alias, None, None, f"{where}: rotor {alias}: its speed is not resolved: {reason}")
            for alias, reason in lost.items()
        )
        return machs
    block = _the_rotor_a_flat_row_turns(case)
    alias = block.alias if block is not None else UNNAMED_ROTOR_RADICAL
    if block is not None:
        diameter: float | None = block.diameter_m
    else:
        diameter = None if case.reference is None else case.reference.rotor_diameter
    try:
        rpm: float | None = float(rotor_speed(case).rpm)
        why = None
    except CampaignConfigError as error:
        rpm, why = None, f"{where}: rotor {alias}: its speed is not resolved: {error}"
    return [one(alias, rpm, diameter, why, axis=None if block is None else block.axis_vector)]


def _disc_machs(case: SimCase, where: str, one: Callable[..., RotorMach]) -> list[RotorMach]:
    """Return the actuator discs' half of :func:`rotor_machs`.

    The discs are resolved by the builder's own resolution
    (:func:`_the_actuator_the_row_names`), so the speed is the one the script
    emits, stated or derived from the advance ratio against the disc's own
    diameter, and a row the builder would refuse is a note carrying its
    refusal.
    """
    try:
        named = _the_actuator_the_row_names(case)
    except CampaignConfigError as error:
        stated = str(_variable(case, ACTUATOR_VARIABLE) or "").strip()
        alias = stated if stated and not stated.startswith("{") else ACTUATOR_VARIABLE
        return [
            one(
                alias,
                None,
                None,
                f"{where}: actuator {alias}: its disc is not resolved: {error}",
                kind="actuator",
            )
        ]
    discs = named if isinstance(named, tuple) else (() if named is None else (named,))
    return [
        one(
            disc.name,
            disc.block.rpm_sign * float(disc.rpm),
            2.0 * disc.block.tip_radius_m,
            None,
            kind="actuator",
            axis=_disc_axis(case, disc.block.frame, disc.block.axis),
        )
        for disc in discs
    ]


def _disc_axis(case: SimCase, frame: str, letter: str) -> tuple[float, float, float] | None:
    """Return a disc's axis in the geometry's frame, or None where it cannot be resolved.

    ``MRP`` is the reference frame itself and a ``[[frames]]`` entry states its
    axes; a rotor's own frame is built from a shaft this function does not
    rebuild, so a disc on one is unresolved and its ``M_adv`` is the edgewise
    bound (FR-1201).
    """
    if frame.upper() == "MRP":
        return AXIS_UNIT_VECTORS[letter]
    for spec in case.frames:
        if spec.name.upper() == frame.upper():
            x, y = spec.x_axis, spec.y_axis
            z = (
                x[1] * y[2] - x[2] * y[1],
                x[2] * y[0] - x[0] * y[2],
                x[0] * y[1] - x[1] * y[0],
            )
            return {"X": x, "Y": y, "Z": z}[letter]
    return None


def _optional_rotor_speed(case: SimCase) -> RotorSpeed | None:
    """Return the rotor speed where the row states one, and None where it does not.

    A window stated in STEPS needs no rotor speed. Resolved motions take
    precedence over flat RPM or advance ratio: their views carry each rotor's
    own diameter (FR-63), and the clock motion owns the row's step, length
    and revolution window (FR-64).

    A MOTIONS list with a resolved speed requires CLOCK_MOTION, even for one
    motion and even beside a flat RPM. With no resolved motion, the flat
    branch answers the row's stated ratio or RPM, or returns None. Records
    that cannot resolve are kept in the lost list by _the_rotors_the_row_turns.

    ExportWindow.from_case and rotor_time_stepping propagate the clock
    refusal; time_steps_of and reduction_windows catch it and report a blank.
    """
    turning, _lost = _the_rotors_the_row_turns(case)
    if turning:
        views = [view for _, view, _ in turning]
        speeds = [speed for _, _, speed in turning]
        return _clock_speed(case, views, speeds)
    if _stated_advance_ratio(case) is not None or _variable(case, RPM_VARIABLE) is not None:
        return rotor_speed(case)
    return None


def _the_rotors_the_row_turns(
    case: SimCase,
) -> tuple[list[tuple[str, SimCase, RotorSpeed]], dict[str, str]]:
    """Return the rotors the row's motions turn, and the ones that could not (FR-68).

    The first list contains one (alias, motion view, speed) per resolved rotor.
    The alias uses the reference's spelling after stripping and case folding
    the record's token, so downstream exact lookups use the resolved name.

    The second mapping preserves unresolved records and their refusal reasons,
    including retired keys (FR-61). A reduction that cannot be windowed is
    recorded as skipped with its reason. Both collections are empty for a row
    that states no motion record.
    """
    turning: list[tuple[str, SimCase, RotorSpeed]] = []
    lost: dict[str, str] = {}
    for index, record in enumerate(case.motions or [], start=1):
        token = record.get(MOVING_BC_ALIAS_VARIABLE)
        named = str(token).strip() if token else f"motion {index}"
        try:
            view = _motion_view(case, record)
            rotor = _rotor_of(case, record)
            if rotor is None:
                raise CampaignConfigError(
                    f"case {case.sim_id!r}: motion {index} names no rotor of the reference"
                )
            turning.append((rotor.alias, view, rotor_speed(view)))
        except CampaignConfigError as error:
            lost[named] = str(error)
    return turning, lost


def _clock_speed(case: SimCase, views: Sequence[SimCase], speeds: Sequence[RotorSpeed]):
    """Return the speed that owns the row's clock (FR-64).

    CLOCK_MOTION names a motion stated by this row. Its speed determines the
    time step and run length. A MOTIONS list requires that key. A flat row
    without it uses the fastest rotor and warns if several speeds compete.
    DELTA_THETA bounds blade travel per step; a length in REVOLUTIONS then
    counts the clock rotor's revolutions while slower rotors turn fewer.
    """
    fastest = max(speeds, key=lambda each: abs(each.rpm))
    named = _variable(case, CLOCK_MOTION_VARIABLE)
    if named is None:
        # A MOTIONS list requires CLOCK_MOTION in either spelling (DEC-010).
        # The flat form is exempt: it turns one rotor and has no clock to choose.
        if case.motions:
            owner = _variable(views[speeds.index(fastest)], MOVING_BOUNDARIES_VARIABLE)
            # List only names the accepter can resolve; a record with neither key
            # must not contribute a placeholder as a supposed clock choice.
            offered = [
                str(record.get(MOVING_BC_ALIAS_VARIABLE) or record.get(MOVING_BOUNDARIES_VARIABLE))
                for record in case.motions
                if record.get(MOVING_BC_ALIAS_VARIABLE) or record.get(MOVING_BOUNDARIES_VARIABLE)
            ]
            stated = ", ".join(offered) if offered else "the motions this row states"
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {len(case.motions)} motion(s) and no "
                f"{CLOCK_MOTION_VARIABLE}. Which rotor bounds the time step and counts "
                "the revolutions is a decision the ROW states, not arithmetic the "
                f"package performs in silence: without the key the clock would follow "
                f"the fastest, which here is {owner!r} at {fastest.rpm:g} rev/min, and "
                "nothing in the row would say so. Write "
                f"'{CLOCK_MOTION_VARIABLE}: <alias>' in the row's VAR_NAMES_VALUES "
                f"cell, beside {MOTIONS_VARIABLE}, naming one of {stated}.\n\n"
                "A row that states its rotor in the flat keys "
                f"rather than in a {MOTIONS_VARIABLE} list, needs no key: it turns one "
                "rotor and there is nothing to choose between."
            )
        if len(speeds) > 1:
            owner = _variable(views[speeds.index(fastest)], MOVING_BOUNDARIES_VARIABLE)
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {len(speeds)} motions using flat rotor keys "
                f"and no {CLOCK_MOTION_VARIABLE}, so the time step and the "
                f"run length follow the FASTEST rotor, which is {owner!r} at "
                f"{fastest.rpm:g} rev/min. That is the package's own arithmetic and not a "
                f"decision the row wrote: name the motion that owns the clock with "
                f"{CLOCK_MOTION_VARIABLE}. A row turning more than one rotor names "
                "the one that owns the clock, whichever spelling it states its "
                "rotors in."
            )
        return fastest
    token = str(named).strip()
    for view, speed in zip(views, speeds, strict=True):
        owner = str(_variable(view, MOVING_BOUNDARIES_VARIABLE) or "")
        if owner.casefold() == token.casefold():
            return speed
    stated = ", ".join(str(_variable(view, MOVING_BOUNDARIES_VARIABLE) or "") for view in views)
    # An unresolved motion retains its reason in the lost list. Report that
    # reason when it is the named clock, rather than claiming the rotor is
    # absent and directing the user to a valid alias key (GOAL-025).
    refused = _the_rotors_the_row_turns(case)[1] if case.motions else {}
    if refused:
        why = "; ".join(f"{alias}: {reason}" for alias, reason in sorted(refused.items()))
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {CLOCK_MOTION_VARIABLE}: {token}, and no motion "
            f"of this row RESOLVES to it. The motions that resolved are {stated or 'none'}, "
            f"and {len(refused)} was refused, which is the likelier cause of what you are "
            f"reading -- {why}"
        )
    raise CampaignConfigError(
        f"case {case.sim_id!r} states {CLOCK_MOTION_VARIABLE}: {token}, and no motion of "
        f"this row moves it. The motions it states are {stated}. The clock is one of the "
        "row's own motions, because the time step is that rotor's blade travel per step."
    )


def _motion_view(case: SimCase, record: Mapping[str, str]) -> SimCase:
    """Return the case as ONE of its motion records sees it: the record's keys in the variables.

    Every reader of a rotor key (:func:`rotor_speed`, :func:`_origin`,
    :func:`emit_rotor_motion`) reads the row's variables, so a record is
    made into a row that states exactly that rotor; the flat motion keys
    cannot be there beside a list, which the matrix reader refused.
    """
    variables: dict[str, str | float | int | bool] = {
        key: value for key, value in case.variables.items() if key not in _MOTION_RECORD_KEYS
    }
    # FR-70: the row's ratio reaches each record that states no speed. Other
    # rotor keys describe one rotor and are stripped by _MOTION_RECORD_KEYS.
    # A swept ratio comes from the point: split_attitude leaves that key out
    # of the variables because the row states the sweep rather than a value.
    row_ratio = case.variables.get(ADVANCE_RATIO_VARIABLE)
    if row_ratio is None:
        row_ratio = case.point.get("advance_ratio")
    # The FLIGHT_CONDITION cell's RPM applies to all motions. A record's own
    # speed wins; a swept speed is the point's. condition_order identifies
    # keys declared by the cell. The flat RPM key describes one rotor and
    # must not bypass a MOTIONS row's CLOCK_MOTION requirement (FR-64).
    row_rpm = case.variables.get(RPM_VARIABLE) if RPM_VARIABLE in case.condition_order else None
    if row_rpm is None:
        row_rpm = case.point.get(RPM_VARIABLE)
    states_its_own = RPM_VARIABLE in record or ADVANCE_RATIO_VARIABLE in record
    if row_ratio is not None and not states_its_own:
        variables[ADVANCE_RATIO_VARIABLE] = row_ratio
    if row_rpm is not None and not states_its_own:
        variables[RPM_VARIABLE] = row_rpm
    variables.update({key: value for key, value in record.items() if key != ROTOR_ORIGIN_POINT_KEY})
    update: dict[str, object] = {"variables": variables, "motions": []}
    rotor = _rotor_of(case, record)
    if rotor is None:
        _warn_a_record_still_naming_its_boundaries(case, record)
    else:
        _refuse_two_rotor_identities(case, record)
        # THE BLOCK FILLS THE VIEW, and this is the one seam where it can:
        # every reader below (rotor_speed, _origin, emit_rotor_motion) reads
        # the row's variables, so filling them here makes the whole rotor
        # path read the reference without one of those readers changing.
        variables[MOVING_BOUNDARIES_VARIABLE] = rotor.alias
        # For a vector shaft, _hub_basis makes the shaft the hub frame's third
        # axis, so the motion uses Z of that frame. A row variable holds a string,
        # not a vector. A letter shaft retains the identity frame and that letter.
        variables[ROTOR_AXIS_VARIABLE] = _rotor_frame_axis(rotor)
        variables[ROTOR_ORIGIN_VARIABLE] = "{},{},{}".format(*rotor.origin)
        variables[BLADES_VARIABLE] = str(rotor.blade_count)
        # The reference owns the rotor's hand for every speed form. The row
        # states a magnitude; the reference states axis, origin, blade count and
        # hand. A row-level hand is refused only when it disagrees with the block.
        stated_hand = _variable(case, RPM_SIGN_VARIABLE)
        if stated_hand is not None:
            _admit_a_row_hand(case, rotor, stated_hand)
        # The view carries the rotor alias, not a copied sign. A view has no
        # motions and reads as a flat row; copying the sign into its variables
        # would make _rpm_sign unable to distinguish package-resolved hand from
        # a user declaration. The alias resolves the reference's single value.
        variables[MOVING_BC_ALIAS_VARIABLE] = rotor.alias
        # THE DIAMETER IS THIS ROTOR'S (FR-63). It is the reason one ratio
        # written once can govern rotors of different sizes: n = V/(J D)
        # is resolved per rotor, and the configuration's single
        # rotor_diameter_m cannot answer for a second size.
        if case.reference is None:
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {MOVING_BC_ALIAS_VARIABLE}: {rotor.alias}, "
                "and the case carries no reference data, so there is nothing to resolve "
                "the rotor's diameter against. A matrix row always binds one; a case "
                "authored in Python states reference=ReferenceData(...)."
            )
        update["reference"] = case.reference.model_copy(update={"rotor_diameter": rotor.diameter_m})
    return case.model_copy(update=update)


def _warn_a_record_still_naming_its_boundaries(case: SimCase, record: Mapping[str, str]) -> None:
    """Warn from the ledger for a record using MOVING_BOUNDARIES (FR-61).

    ROW_MOVING_BOUNDARIES owns the removal version and migration message.
    Every record stating the key receives that deprecation message.

    The text is the LEDGER ENTRY'S OWN, so the release it names is the one
    the deadline guard enforces rather than a second copy that nothing
    keeps equal.
    """
    if MOVING_BOUNDARIES_VARIABLE not in record:
        return
    raise CampaignConfigError(f"case {case.sim_id!r}: {refusal_text(ROW_MOVING_BOUNDARIES)}")


def _refuse_two_rotor_identities(case: SimCase, record: Mapping[str, str]) -> None:
    """Refuse a record stating the alias AND one of the keys the alias replaces."""
    also = sorted(key for key in _RETIRED_MOTION_KEYS if key in record)
    if also:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {MOVING_BC_ALIAS_VARIABLE}: "
            f"{record[MOVING_BC_ALIAS_VARIABLE]} and {', '.join(also)} in one motion "
            "record. The alias names the rotor and the reference states the rest of it, "
            f"so {', '.join(also)} would be a second answer to a question already "
            "answered. Drop them from the record; the reference is where they live."
        )


#: The four keys an alias replaces (FR-61). A record stating the alias and
#: any of these states one rotor twice, and is refused naming both.
#: ``BLADES`` is here too: the blade count is the length of the block's
#: ``families_blades``, and a row stating its own is the same second
#: answer.
_RETIRED_MOTION_KEYS = (
    "MOVING_BOUNDARIES",
    "ROTOR_AXIS",
    "ROTOR_ORIGIN",
    "RPM_SIGN",
    "BLADES",
)

#: The keys a motion record carries, mirrored from the matrix reader so a
#: record's view of the row holds its own rotor and no other.
_MOTION_RECORD_KEYS = frozenset(
    {
        MOVING_BC_ALIAS_VARIABLE,
        MOVING_BOUNDARIES_VARIABLE,
        RPM_VARIABLE,
        ADVANCE_RATIO_VARIABLE,
        RPM_SIGN_VARIABLE,
        ROTOR_AXIS_VARIABLE,
        ROTOR_ORIGIN_VARIABLE,
    }
)


def _origin(case: SimCase) -> tuple[float, float, float]:
    text = _variable(case, ROTOR_ORIGIN_VARIABLE)
    if text is None:
        return (0.0, 0.0, 0.0)
    parts = [token.strip() for token in text.split(",") if token.strip()]
    if len(parts) != 3:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {ROTOR_ORIGIN_VARIABLE} as {text!r}; a rotor "
            "hub is three coordinates in the reference frame, in simulation length "
            "units, comma separated."
        )
    try:
        x, y, z = (float(part) for part in parts)
    except ValueError:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {ROTOR_ORIGIN_VARIABLE} as {text!r}, which "
            "is not three numbers."
        ) from None
    # THE SAME NON-FINITE ROUTE AS EVERY OTHER NUMERIC CELL, and this one
    # does not pass through `_required_float` because it parses three
    # values out of one string. `float("nan")` succeeds, so without this
    # a NaN coordinate became the origin of the frame the whole rotary
    # motion turns about.
    if not all(math.isfinite(value) for value in (x, y, z)):
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {ROTOR_ORIGIN_VARIABLE} as {text!r}, which "
            "carries a value that is not finite. A rotor hub is three coordinates in "
            "simulation length units, and NaN or infinity is not a position."
        )
    return (x, y, z)
