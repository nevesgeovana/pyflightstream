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
    _refuse_a_row_restating_the_hand,
    _rotor_of,
    _stated_advance_ratio,
    _states_a_rotor_speed,
    _the_rotor_a_flat_row_turns,
    _variable,
    _velocity,
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

    Three row types carry them (0.30.0, M1): every ``unsteady_rotor`` and
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
        kind: str = "rotor",
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
        return RotorMach(alias, rpm, diameter, velocity, sound, tip, helical, None, kind)

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
    return [one(alias, rpm, diameter, why)]


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
                "actuator",
            )
        ]
    discs = named if isinstance(named, tuple) else (() if named is None else (named,))
    return [
        one(
            disc.name,
            disc.block.rpm_sign * float(disc.rpm),
            2.0 * disc.block.tip_radius_m,
            None,
            "actuator",
        )
        for disc in discs
    ]


def _optional_rotor_speed(case: SimCase) -> RotorSpeed | None:
    """Return the rotor speed where the row states one, and None where it does not.

    A window stated in STEPS needs no rotor speed, and refusing a case
    that never asked for one would break every such row.

    A ROW STATING ITS SPEEDS IN MOTIONS STATES ONE HERE TOO, through the
    motion that owns the clock (FR-64). Without that, a 0.15.0 transition
    row reduced over NOTHING: the row itself carries no `RPM` because each
    rotor carries its own, so this returned None and every reduction of
    the point, the time average included, was skipped with "states no
    rotor speed" (measured on a two rotor row, 2026-09-10). The clock
    motion is the right one and not merely an available one: the row's
    step and the row's length are already ITS, which is what FR-64
    settled, so the window they cut is its revolutions.

    THE BLAST RADIUS IS FOUR CALL SITES, not one, and saying so is the
    point of this paragraph: `rotor_time_stepping`, `ExportWindow.from_case`
    and the unsteady builder all reach here, so each of them now resolves a
    clock speed for a MOTIONS-only row where it previously got None. That
    is FR-64's intent and it is a change a reader of the reduction diff
    alone would not see (the architecture lens, 2026-09-10).
    THE MOTIONS ARE ASKED FIRST, and the order is the whole fix of
    2026-09-11. The two questions were asked the other way round -- does the
    row state a ratio or an rpm, and only then, does the row turn rotors --
    so a row that does BOTH took the flat branch, which resolves J against
    the configuration's single `rotor_diameter`. That length is exactly what
    FR-63 moved into each rotor block, because one configuration turning two
    sizes of rotor has no one diameter to put there, so the flat branch
    could not answer and the branch that could was never reached. Measured
    on the reference row 6002: `time_average`, `phase_locked` and
    `per_blade` all skipped, each naming a key the reference is right not to
    carry, while the SCRIPT for the same point built correctly at 36 steps.
    A motion view carries the row's own variables plus its record's, so it
    answers everything the row could answer and one thing more: the rotor's
    own diameter.

    IT IS NOT STRICTLY WIDER, AND THIS PARAGRAPH ONCE SAID IT WAS. Measured
    on 2026-09-11 over four row shapes:

        two motions each stating RPM, no CLOCK_MOTION  ->  REFUSED
        one motion stating RPM, no CLOCK_MOTION        ->  REFUSED
        one motion stating none, no CLOCK_MOTION       ->  the flat branch
        no motions at all                              ->  the flat branch

    So the shape that changed is not about HOW MANY rotors turn. A row whose
    motion records RESOLVE to a speed, and which names no `CLOCK_MOTION`, is
    now REFUSED by `_clock_speed` naming the key it wants, where a flat `RPM`
    used to answer it. A record that resolves to nothing still reaches the
    flat branch, because `_the_rotors_the_row_turns` puts it in its lost list
    and leaves `turning` empty.

    THAT REFUSAL IS THE POINT RATHER THAN A COST, and it is `_clock_speed`'s
    own rule reaching a row that had been getting past it. FR-64 settled that
    ANY row stating a `MOTIONS` list must say which motion owns the clock, in
    those words, because `DELTA_THETA` bounds a blade's travel per step and a
    list is where a row has something to choose between. A flat `RPM` beside
    that list was a back door past the question, and the clock such a row got
    was whichever number it happened to carry, with nothing saying so.

    TWO CALLERS DO NOT CATCH THE REFUSAL (`ExportWindow.from_case` and
    `rotor_time_stepping`) and two do (`time_steps_of`, `reduction_windows`),
    so on that shape the first two now refuse where they used to answer and
    the last two report a blank. The architecture lens named the shape and the
    measurement above sharpened it; the claim of strict widening was mine and
    it was wrong.
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

    The first is one ``(alias, motion view, speed)`` per rotor, where the
    ALIAS IS THE REFERENCE'S OWN SPELLING and never the record's token.
    `_rotor_of` resolves a token stripped and case folded, so a record
    writing ``" pusher "`` reaches every rotor path in this module and then
    failed an exact-match subscript one layer down, raising a `KeyError`
    out of `reduction_windows`, whose own docstring says it never raises
    for a row the builder would refuse (the architecture lens, 2026-09-10).
    One resolution, carried forward.

    THE SECOND IS THE DROP-OUTS, alias to reason, and it exists because
    the first writing simply lost them. A record this cannot resolve got
    no entry, so the rotor appeared in neither the products nor the
    skipped list of the manifest: it vanished. That is exactly what this
    module refuses to do everywhere else, where "a reduction the row
    cannot window is recorded as skipped with the reason, never guessed".
    Among the reasons swallowed is a record stating a retired key beside
    its alias, which FR-61 goes to the trouble of refusing loudly.

    Both are empty for a row that states no motion record, which is every
    row written before 0.15.0 and every steady row, so a caller that finds
    nothing here behaves exactly as it did.
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

    The design of 2026-09-10: ``CLOCK_MOTION`` names a motion the same row
    states, and the time step and the run length are that motion's. A row
    without the key keeps the arithmetic of 0.14.0, the FASTEST rotor,
    and says so in a warning naming the motion it assumed, because that
    was an inference nobody had written down: ``DELTA_THETA`` bounds a
    blade's travel per step, so the fastest rotor bounds the step, and a
    length in REVOLUTIONS is then counted in ITS revolutions while the
    others turn fewer.
    """
    fastest = max(speeds, key=lambda each: abs(each.rpm))
    named = _variable(case, CLOCK_MOTION_VARIABLE)
    if named is None:
        # REQUIRED ON ANY ROW THAT STATES A `MOTIONS` LIST, in either
        # spelling, which is the decision of 2026-09-10 (DEC-010) and then
        # its correction the same day, when the scope had been drawn
        # narrower to protect rows written at 0.14.0. A 0.x release is not
        # bound to the rows of the release before it, and a list of several
        # motions has something to choose between whatever spelling names
        # them.
        #
        # THE FLAT PRE-0.15.0 FORM IS STILL EXEMPT, and that exemption was
        # measured rather than assumed: it turns ONE rotor, so there is
        # nothing to choose between, and a reference case written that way
        # is what an acceptance arm runs. Refusing it would have cost the
        # comparison to buy a key that decides nothing.
        if case.motions:
            owner = _variable(views[speeds.index(fastest)], MOVING_BOUNDARIES_VARIABLE)
            # THE NAMES THE ACCEPTER WILL TAKE, and only those. A record
            # that names neither key contributed the literal `?` to this
            # list, so a case authored in Python could be asked to name one
            # of `?` (the interface lens of 2026-09-10).
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
                "A row written before 0.15.0, which states its rotor in the flat keys "
                f"rather than in a {MOTIONS_VARIABLE} list, needs no key: it turns one "
                "rotor and there is nothing to choose between."
            )
        if len(speeds) > 1:
            owner = _variable(views[speeds.index(fastest)], MOVING_BOUNDARIES_VARIABLE)
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {len(speeds)} motions in the spelling of "
                f"before 0.15.0 and no {CLOCK_MOTION_VARIABLE}, so the time step and the "
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
    # A MOTION THAT WAS REFUSED IS NOT A MOTION THAT IS ABSENT, and this
    # sentence said it was. `_the_rotors_the_row_turns` drops a record it
    # cannot resolve into its lost list with the reason, and the reason is
    # what the user has to read: a row naming its clock and then stating
    # that rotor's speed in a form the package refuses was told the row
    # does not turn it, which sends the user to the key that is right.
    # 0.22.0 made this reachable on a correct row, because a rotor's hand
    # written into its number is now refused (GOAL-025).
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
    # FR-70: THE ROW'S RATIO REACHES A RECORD THAT STATES NO SPEED, and
    # nothing else of the row's rotor keys does. `_MOTION_RECORD_KEYS`
    # strips every key a record may carry, which is right for the four
    # that describe ONE rotor and wrong for this one, which the row
    # states for ALL of them: stripped, the condition's ratio reached no
    # motion at all, which is the behaviour FR-70 exists to give (the
    # architecture lens of 2026-09-10).
    # A SWEPT RATIO IS THE POINT'S, NOT THE ROW'S, and that is the half a
    # variable lookup could not reach. `split_attitude` deliberately keeps
    # the swept key OUT of the variables, because its value is what varies
    # and the row states only the word; so a row writing
    # `ADVANCE_RATIO: sweep` had no ratio in its variables and the
    # condition's ratio reached no motion at all. Measured on the reference
    # matriz_transicao.fs: 9 of 16 points blocked on "states no rotor
    # speed", which is the sentence this line removes.
    row_ratio = case.variables.get(ADVANCE_RATIO_VARIABLE)
    if row_ratio is None:
        row_ratio = case.point.get("advance_ratio")
    # AND THE ROW'S SPEED, since 0.21.0, by the same rule and for the same
    # reason: RPM is a key of FLIGHT_CONDITION now, the row states it for ALL
    # its motions, and `_MOTION_RECORD_KEYS` strips it as though it described
    # one rotor. A record stating a speed of its own still wins, which is what
    # "MOTIONS wins" means; a swept speed is the POINT's.
    # FROM THE CELL AND NOT FROM THE FLAT KEY. `RPM` in VAR_NAMES_VALUES is
    # the pre-0.15.0 spelling of ONE rotor's speed and has never reached a
    # motion record: a row whose records resolve to a speed must name its
    # CLOCK_MOTION, and letting the flat key through would answer that
    # question by arithmetic instead (FR-64, pinned by
    # test_reduce_by_rotor.py::test_a_row_turning_several_rotors_still_has_to_name_its_clock).
    # The cell's RPM is the row's statement for ALL its motions, which is what
    # `condition_order` distinguishes: it lists the keys the CELL declared.
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
        # THE FRAME'S OWN THIRD AXIS WHEN THE ROTOR STATES A VECTOR, and the
        # letter itself when it states a letter. A row variable is a STRING, so
        # a three-component shaft cannot be written here at all -- which the
        # type checker is what surfaced, and the answer it forced is better than
        # a serialisation would have been. `_hub_basis` builds the hub frame with
        # the shaft as its third axis, so the motion turns about `Z` OF THAT
        # FRAME and the direction is carried by the frame rather than by this
        # cell. A rotor stating a LETTER keeps the identity frame and the letter,
        # so every reference written before 0.23.0 emits what it always did.
        variables[ROTOR_AXIS_VARIABLE] = rotor.axis if isinstance(rotor.axis, str) else "Z"
        variables[ROTOR_ORIGIN_VARIABLE] = "{},{},{}".format(*rotor.origin)
        variables[BLADES_VARIABLE] = str(rotor.blade_count)
        # THE ROTOR'S HAND IS THE REFERENCE'S, ALWAYS, and it reaches every
        # speed form. The RPM a row states
        # is a MAGNITUDE and the sign comes from the reference, which already
        # says the axis, the origin and the blade count -- the row says how
        # fast, the block says which way, and the two cannot contradict each
        # other because neither states what the other does.
        #
        # UNTIL 0.21.1 THIS WAS FILLED ONLY WHEN THE ROW STATED NO SPEED,
        # because 0.21.0 let the speed come from the cell and filling it beside
        # a stated RPM made every such row refuse itself through the old
        # "states RPM and RPM_SIGN" guard. That traded a loud refusal for a
        # SILENT WRONG SIGN: measured on a four-blade propeller whose full
        # wheel turned backwards while the same rotor as a sector, stating a
        # ratio, turned correctly. A rotor turning the wrong way converges and
        # reports numbers, which is why this is the worse of the two.
        #
        # AND IT IS REFUSED WHETHER OR NOT IT AGREES, which the first writing
        # got wrong by refusing only a disagreement. A row that agrees today is
        # a row that says nothing when the REFERENCE is corrected tomorrow: the
        # block flips, the row keeps the old hand, and the two disagree with
        # nobody to notice -- which is the shape of the defect this whole
        # change exists to close. One home for the hand, and the refusal is
        # about where the key goes rather than about its value.
        stated_hand = _variable(case, RPM_SIGN_VARIABLE)
        if stated_hand is not None:
            _refuse_a_row_restating_the_hand(case, rotor, stated_hand)
        # THE VIEW CARRIES THE ALIAS, NOT THE ANSWER. Writing the block's sign
        # into the variables put the hand in two shapes -- a resolved number
        # here, a declared block everywhere else -- and `_rpm_sign` could no
        # longer tell a hand the package had filled from one a USER had written,
        # because a view sets `motions` empty and so reads as a flat row. It
        # carries the alias instead and every shape resolves the block the one
        # way, which is the same one-home argument this release makes about the
        # reference (the architect and qa lenses, FIX-0220).
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
    """Warn from the ledger for a record that names its rotor the 0.14.0 way (FR-61).

    THE PROMISE WAS REGISTERED AND NEVER SPOKEN: `ROW_MOVING_BOUNDARIES`
    sat in the ledger with a removal version and nothing called its
    `message()`, so the deprecation it announces was invisible to the user
    it is for, and a record stating `MOVING_BOUNDARIES` was accepted in
    silence (the technical writing lens of 2026-09-10).

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
