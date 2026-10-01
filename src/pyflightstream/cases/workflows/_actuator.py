"""Actuator discs: the disc a row names, its profile, its speed, and its emission.

A row names an actuator disc by its record; :func:`_the_actuator_the_row_names`
reads it, :func:`actuator_records` lists the records,
:func:`_actuator_disc` and :func:`_emit_actuator_disc` emit it.
"""

from __future__ import annotations

import re
from dataclasses import (
    dataclass,
)
from os import (
    PathLike,
    fspath,
)
from pathlib import (
    Path,
    PurePath,
)

from pyflightstream._fsm import (
    MeshReadError,
    saved_actuators,
)
from pyflightstream.cases import (
    ActuatorBlock,
    CampaignConfigError,
    SimCase,
)
from pyflightstream.script import (
    CommandArgumentError,
    Script,
    helpers,
)

from ._rows import (
    _DERIVED_RPM_DECIMALS,
    _POINT_ADVANCE_RATIO,
    _from_metres,
    _required_float,
    _stated_advance_ratio,
    _variable,
    _velocity,
)
from ._vocabulary import (
    ACTUATOR_KEYS,
    ACTUATOR_PROFILE_COPY_SUFFIX,
    ACTUATOR_RPM_VARIABLE,
    ACTUATOR_THRUST_VARIABLE,
    ACTUATOR_VARIABLE,
    ADVANCE_RATIO_VARIABLE,
    PROFILE_VARIABLE,
    SIMULATION_SUFFIX,
    Frames,
)


@dataclass(frozen=True)
class _RowActuator:
    """The disc a row names and the loading it states (G06), resolved before emission.

    ``profile`` is the user's file and ``profile_text`` what the run's own
    copy of it holds (:func:`read_actuator_profile`); both None for a disc
    loaded by its net thrust.
    """

    name: str
    block: ActuatorBlock
    rpm: float
    thrust: float | None
    profile: str | None
    profile_text: str | None = None


def read_actuator_profile(path: str | PathLike[str]) -> str:
    """Read a radial thrust profile file into the text the solver is given (G06).

    The user's file stays as its editor saved it; the run writes its own
    copy for the solver, and this is that copy's text: the file's rows put
    in the one form 26.124 was measured to read by
    :func:`pyflightstream.script.helpers.render_actuator_profile`, two
    numbers ``r,F`` per line with NO final newline (RPT-070). A final
    newline, blank lines, CR LF line ends, surrounding spaces and a
    byte-order mark are removed rather than refused.

    One reader for both places that ask: the plan, when a row's ``PROFILE``
    is resolved, and every builder that emits the disc, so a case built in
    Python is held to the same form.

    Parameters
    ----------
    path : str or path-like
        The profile file, where it lives.

    Returns
    -------
    str
        The copy's text, newline separated and not newline terminated.

    Raises
    ------
    CampaignConfigError
        The file cannot be read as UTF-8 text, or is not in the form the
        solver reads, naming the file and the line: a header or a count
        first, a row that is not two numbers separated by one comma, a
        number that is not finite, fewer than two rows.
    """
    where = f"the actuator profile {fspath(path)}"
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as error:
        raise CampaignConfigError(
            f"{where} cannot be read as UTF-8 text: {error}. A radial thrust profile is a "
            "text file of rows r,F."
        ) from error
    try:
        return helpers.render_actuator_profile(text, source=where)
    except CommandArgumentError as error:
        raise CampaignConfigError(str(error)) from None


def _disc_rpm_from_the_advance_ratio(case: SimCase, name: str, block: ActuatorBlock) -> float:
    """Return a disc's speed from the row's advance ratio, in rev/min (G20 of 0.28.0).

    The rotors' rule, n = V / (J D), with the DISC's own diameter, twice its
    ``tip_radius_m``, never the reference's rotor diameter, which belongs to
    another rotor or to none; the hand stays the block's ``rpm_sign``. The ratio
    is read where a rotor reads it (the row, or the point of a swept row), and
    rounded as a rotor's derived speed is. A row stating neither form is refused
    naming both.
    """
    ratio_text = _stated_advance_ratio(case)
    if ratio_text is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} names {ACTUATOR_VARIABLE}: {name} and states neither "
            f"{ACTUATOR_RPM_VARIABLE} nor {ADVANCE_RATIO_VARIABLE}. The disc turns at the "
            f"speed the row states, in rev/min ('{ACTUATOR_RPM_VARIABLE}: <speed>'), or at "
            f"the speed its advance ratio works out to ('{ADVANCE_RATIO_VARIABLE}: <J>', "
            "n = V / (J D) with the disc's own diameter)."
        )
    ratio = _required_float(
        case,
        ADVANCE_RATIO_VARIABLE,
        quantity="advance ratio",
        unit="dimensionless",
        text=ratio_text,
    )
    if ratio <= 0.0:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {ADVANCE_RATIO_VARIABLE} as {ratio} for the disc "
            f"{name!r}; an advance ratio is positive, and the hand is the block's rpm_sign."
        )
    velocity = _velocity(case)
    if velocity <= 0.0:
        raise CampaignConfigError(
            f"case {case.sim_id!r} resolves a free-stream velocity of {velocity} m/s, and "
            f"the disc {name!r} takes its speed from {ADVANCE_RATIO_VARIABLE}: n = V / (J D) "
            f"is a stopped disc at V = 0. State {ACTUATOR_RPM_VARIABLE} directly."
        )
    return round(60.0 * velocity / (ratio * 2.0 * block.tip_radius_m), _DERIVED_RPM_DECIMALS)


def actuator_records(case: SimCase) -> list[dict[str, str]]:
    """Read ACTUATOR brace records using the same pair grammar as MOTIONS.

    Flat single-disc rows remain unchanged. Each record names ACTUATOR and its
    own speed and loading; a row-level advance ratio can supply a shared ratio.
    """
    text = _variable(case, ACTUATOR_VARIABLE)
    if text is None or not text.strip().startswith("{"):
        return []
    forbidden = [
        key
        for key in ACTUATOR_KEYS
        if key != ACTUATOR_VARIABLE and _variable(case, key) is not None
    ]
    if forbidden:
        raise CampaignConfigError(
            "ACTUATOR records cannot be combined with flat " + ", ".join(forbidden)
        )
    bodies = re.findall(r"\{([^{}]*)\}", text)
    if not bodies or re.sub(r"\{[^{}]*\}", "", text).strip(" ,"):
        raise CampaignConfigError("ACTUATOR requires {ACTUATOR: name / KEY: value}, {...}")
    allowed = {*ACTUATOR_KEYS, ADVANCE_RATIO_VARIABLE}
    records: list[dict[str, str]] = []
    names: set[str] = set()
    for body in bodies:
        record: dict[str, str] = {}
        for pair in body.split("/"):
            key, separator, value = pair.strip().partition(":")
            key, value = key.strip(), value.strip()
            if not separator or key not in allowed or not value or key in record:
                raise CampaignConfigError(
                    f"ACTUATOR record has an invalid or repeated pair: {pair!r}"
                )
            record[key] = value
        name = record.get(ACTUATOR_VARIABLE)
        if not name or name in names:
            raise CampaignConfigError("each ACTUATOR record must name a different reference block")
        names.add(name)
        records.append(record)
    return records


def disc_speed_moves_with_the_point(case: SimCase) -> bool:
    """Return whether the row's disc turns at a different speed at each point.

    True when the row names a disc, states no ``ACTUATOR_RPM`` and no row-level
    ``ADVANCE_RATIO``, and its points carry more than one advance ratio: each
    point's speed is then its own n = V / (J D). The steady run type reads this
    to run such a row one job per point, because a warm job sets the disc once
    and every point after the first would turn at the first point's speed.

    Parameters
    ----------
    case : SimCase
        The row, before it is split into points.

    Returns
    -------
    bool
        True when the disc speed differs between the points of the sweep.
    """
    if _variable(case, ACTUATOR_VARIABLE) is None:
        return False
    records = actuator_records(case)
    if records and all(
        ACTUATOR_RPM_VARIABLE in record or ADVANCE_RATIO_VARIABLE in record for record in records
    ):
        return False
    if _variable(case, ACTUATOR_RPM_VARIABLE) is not None:
        return False
    if _variable(case, ADVANCE_RATIO_VARIABLE) is not None:
        return False
    ratios = {point.get(_POINT_ADVANCE_RATIO) for point in case.sweep.points()}
    return len(ratios) > 1


def _the_actuator_the_row_names(
    case: SimCase,
) -> _RowActuator | tuple[_RowActuator, ...] | None:
    """Resolve the row's disc and its loading, or refuse naming the key (G06).

    CALLED BEFORE THE FIRST EMISSION by every builder that emits a disc, so a
    row that cannot be built is refused with nothing written. A row stating
    none of the four keys returns None, whatever its reference declares: a
    reference's disc moves nothing a row does not name. A saved simulation
    that already carries an actuator is refused here too
    (:func:`_refuse_a_disc_beside_a_saved_one`), and a profile file the
    solver would misread, naming its line (:func:`read_actuator_profile`).
    """
    records = actuator_records(case)
    if records:
        discs: list[_RowActuator] = []
        for record in records:
            variables = {
                key: value for key, value in case.variables.items() if key not in ACTUATOR_KEYS
            }
            variables.update(record)
            view = case.model_copy(
                update={
                    "variables": variables,
                    "actuator_profile": case.actuator_profiles.get(
                        record.get(PROFILE_VARIABLE, "")
                    ),
                }
            )
            disc = _the_actuator_the_row_names(view)
            assert isinstance(disc, _RowActuator)
            discs.append(disc)
        return tuple(discs)
    stated = [key for key in ACTUATOR_KEYS if _variable(case, key) is not None]
    if not stated:
        return None
    name = _variable(case, ACTUATOR_VARIABLE)
    if name is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {', '.join(stated)} and no {ACTUATOR_VARIABLE}. "
            "Those keys load the actuator disc the row names, so the row names one: "
            f"'{ACTUATOR_VARIABLE}: <block>', a block its reference declares with "
            'kind = "actuator".'
        )
    block = case.actuators.get(name)
    if block is None:
        declared = ", ".join(sorted(case.actuators)) or "none"
        reference = case.variables.get("matrix_ref")
        whose = f"its reference {reference!r}" if reference else "its reference"
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {ACTUATOR_VARIABLE}: {name}, and {whose} declares "
            f"no actuator of that name (it declares: {declared}). Name a block the "
            'reference declares with kind = "actuator".'
        )
    if _variable(case, ACTUATOR_RPM_VARIABLE) is None:
        rpm = _disc_rpm_from_the_advance_ratio(case, name, block)
    else:
        rpm = _required_float(case, ACTUATOR_RPM_VARIABLE, quantity="disc speed", unit="rev/min")
    if rpm <= 0.0:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {ACTUATOR_RPM_VARIABLE}: "
            f"{_variable(case, ACTUATOR_RPM_VARIABLE)}; the speed is a magnitude and the "
            f"sense is the block's rpm_sign (+1 the right-hand rule about its axis), "
            f"which the reference's {name!r} states as {block.rpm_sign:+d}."
        )
    thrust_text = _variable(case, ACTUATOR_THRUST_VARIABLE)
    profile_stem = _variable(case, PROFILE_VARIABLE)
    if thrust_text is not None and profile_stem is not None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {ACTUATOR_THRUST_VARIABLE} and {PROFILE_VARIABLE}; "
            "a disc takes one loading, the net thrust (the ELLIPTICAL model) or a radial "
            "profile (the CUSTOM model). Keep one."
        )
    if thrust_text is None and profile_stem is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} names {ACTUATOR_VARIABLE}: {name} and states neither "
            f"{ACTUATOR_THRUST_VARIABLE} nor {PROFILE_VARIABLE}. A disc is loaded by its net "
            f"thrust in {block.thrust_units} ('{ACTUATOR_THRUST_VARIABLE}: <value>') "
            "or by a profile file of "
            f"inputs/profiles/ ('{PROFILE_VARIABLE}: <stem>')."
        )
    thrust: float | None = None
    profile: str | None = None
    profile_text: str | None = None
    if thrust_text is not None:
        thrust = _required_float(
            case, ACTUATOR_THRUST_VARIABLE, quantity="disc's net thrust", unit=block.thrust_units
        )
    else:
        if block.blades is None:
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {PROFILE_VARIABLE}: {profile_stem} for the disc "
                f"{name!r}, whose reference block states no blades. The imported "
                "distribution is read per blade, so the block states blades = <count>."
            )
        if case.actuator_profile is None:
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {PROFILE_VARIABLE}: {profile_stem} and carries no "
                "resolved profile file. A matrix row's PROFILE is resolved against the "
                "workspace's inputs/profiles/ when the row binds; a case built in Python "
                "sets actuator_profile to the file's absolute path."
            )
        profile = case.actuator_profile
        try:
            profile_text = read_actuator_profile(profile)
        except CampaignConfigError as error:
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {PROFILE_VARIABLE}: {profile_stem}, and {error}"
            ) from None
    _refuse_a_disc_beside_a_saved_one(case, name)
    return _RowActuator(
        name=name,
        block=block,
        rpm=rpm,
        thrust=thrust,
        profile=profile,
        profile_text=profile_text,
    )


def _refuse_a_disc_beside_a_saved_one(case: SimCase, name: str) -> None:
    """Refuse a row's disc on a saved simulation that already carries an actuator (G06).

    ``CREATE_NEW_ACTUATOR`` APPENDS to the actuators the opened simulation
    holds, and the script's ledger starts from none, so on a file that saved
    one the axis, radius, speed and loading the script cites as actuator 1
    would configure the SAVED actuator and leave the row's own unset. Numbering
    the new disc after the saved ones would not answer the row either: the
    saved actuator stays in the simulation, and the row states one disc. So
    the row is refused, naming what the file carries
    (:func:`pyflightstream._fsm.saved_actuators`), and a file whose actuators
    cannot be read is refused rather than written into on a guess. A raw
    mesh is imported into a new simulation and carries none, and a
    placeholder with no physics block reads as none, as its inventory does.
    """
    geometry = case.geometry
    if geometry is None or PurePath(str(geometry)).suffix.lower() != SIMULATION_SUFFIX:
        return
    file = PurePath(str(geometry)).name
    try:
        saved = saved_actuators(geometry)
    except MeshReadError as error:
        raise CampaignConfigError(
            f"case {case.sim_id!r} names the actuator disc {name!r}, and the actuators its "
            f"saved simulation {file} already carries cannot be read: {error}. The disc the row "
            "creates is cited by the index after them, so it is not created on a guess; open "
            "a simulation saved without an actuator."
        ) from error
    if saved:
        carried = ", ".join(repr(each) for each in saved)
        raise CampaignConfigError(
            f"case {case.sim_id!r} names the actuator disc {name!r}, and its saved simulation "
            f"{file} already carries the actuator {carried}. The disc the script creates would "
            f"be actuator {len(saved) + 1} beside it, the commands after it would configure the "
            "saved one, and the row states one disc. Open a simulation saved without an "
            "actuator, or name no ACTUATOR on this row and the saved actuator stays as it was "
            "saved."
        )


def _actuator_disc(
    case: SimCase,
    script: Script,
    frames: Frames,
    disc: _RowActuator | tuple[_RowActuator, ...] | None,
) -> None:
    """Create requested discs and apply explicit actions in their declared order."""
    records = disc if isinstance(disc, tuple) else (() if disc is None else (disc,))
    actions = case.solver.actuator_operations or ()
    planned: list[tuple[str, int, str | None]] = []
    existing: list[str] = []
    if actions:
        if not records and case.geometry is not None:
            if PurePath(case.geometry).suffix.lower() == SIMULATION_SUFFIX:
                try:
                    saved = saved_actuators(case.geometry)
                    if saved is None:
                        raise CampaignConfigError(
                            "actuator operations require a readable saved physics inventory"
                        )
                    existing = list(saved)
                except MeshReadError as error:
                    raise CampaignConfigError(
                        f"actuator operations cannot read the saved actuator inventory: {error}"
                    ) from error
        names = existing + [item.name for item in records]
        commands = {
            "rename": "SET_ACTUATOR_NAME",
            "delete": "DELETE_ACTUATOR",
            "enable": "ENABLE_ACTUATOR",
            "disable": "DISABLE_ACTUATOR",
        }
        for action in actions:
            command = commands[action.op]
            script.entry(command)
            matches = [index for index, name in enumerate(names) if name == action.actuator]
            if len(matches) != 1:
                raise CampaignConfigError(
                    f"actuator {action.actuator!r} resolves to {len(matches)} objects; "
                    f"actuator_operations require one exact current name (available: {names})"
                )
            index = matches[0]
            if action.op == "rename":
                assert action.name is not None
                if action.name != action.actuator and action.name in names:
                    raise CampaignConfigError(f"actuator rename would duplicate {action.name!r}")
                names[index] = action.name
            elif action.op == "delete":
                names.pop(index)
            planned.append((command, index + 1, action.name))
    if existing:
        if script.num_actuators not in (0, len(existing)):
            raise CampaignConfigError("saved actuator inventory disagrees with script entity count")
        if script.num_actuators == 0:
            script.declare_existing(actuators=len(existing))
    for item in records:
        _emit_actuator_disc(case, script, frames, item)
    for command, index, name in planned:
        if name is None:
            script.emit(command, index)
        else:
            script.emit(command, index, name)


def _solver_disc_speed(block: ActuatorBlock, rpm: float) -> float:
    """Return the signed speed the disc command is handed, in rev/min (FR-331).

    THE SOLVER'S DISC SPEED IS THE OPPOSITE OF THE BLOCK'S HAND. ``rpm_sign``
    is the hand a rotor block states, ``+1`` the right-hand rule about the
    block's ``axis``, and a disc whose block states it swirls its wake the way
    a rotor of that sign turns. Measured on 26.124 (RPT-137), a disc handed
    ``+rpm`` swirled AGAINST a rotor of ``rpm_sign +1`` and a disc handed
    ``-rpm`` swirled with it, so the emitted speed is minus the hand times the
    magnitude. 0.33.0 and earlier handed plus the hand. On another build the
    rule is the same and unmeasured.
    """
    return -block.rpm_sign * rpm


def _emit_actuator_disc(
    case: SimCase,
    script: Script,
    frames: Frames,
    disc: _RowActuator | tuple[_RowActuator, ...] | None,
) -> None:
    """Emit the row's actuator disc in the frame its block names (G06).

    AFTER EVERY FRAME EXISTS and before the solver is initialised: the disc is
    a setup definition, and ``SET_ACTUATOR_AXIS`` cites a frame that must
    already exist. The emission itself is the curated helper's, which refuses
    the profile route on a build whose grammar takes no blade count.

    THE BLOCK'S METRES ARE WRITTEN IN THE SIMULATION'S UNIT, which is the unit
    the two commands read (:func:`_from_metres`); a unit the package cannot
    know is refused naming the three keys.

    A PROFILE IS READ FROM THE RUN'S OWN COPY, never from the user's file: the
    copy, ``<stem>.actuator_profile.txt``
    (:data:`ACTUATOR_PROFILE_COPY_SUFFIX`), is named in the folder the script
    runs in (:attr:`~pyflightstream.script.Script.working_dir`), and its text
    (:func:`read_actuator_profile`) is parked on the script, which the run
    writes there before the solver starts and hashes into the record, as it
    does the trailing-edge node file. The user's file stays as its editor
    saved it, usually ending in a newline, and 26.124 reads that newline as
    one point more, refuses the file and holds the run in a dialog (RPT-070). A
    script with no working folder (a plan's rehearsal, a case built in
    Python) names the copy by its bare name.
    """
    if isinstance(disc, tuple):
        raise CampaignConfigError("internal actuator emission expects one resolved disc")
    if disc is None:
        return
    frame = frames.get(disc.block.frame)
    if not isinstance(frame, int):
        created = sorted(key for key, value in frames.items() if isinstance(value, int))
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the actuator disc {disc.name!r} of its reference is placed "
            f"in frame {disc.block.frame!r}, and this run created no such frame (created: "
            f"{', '.join(created) or 'none'}). A disc's frame is one the reference's "
            "[[frames]] declares, MRP, or a frame of a rotor this row turns."
        )
    block = disc.block
    factor = _from_metres(
        case,
        script,
        f"the offset_m, tip_radius_m and hub_radius_m of the actuator disc {disc.name!r}",
    )
    copy: str | None = None
    if disc.profile is not None:
        name = f"{PurePath(disc.profile).stem}{ACTUATOR_PROFILE_COPY_SUFFIX}"
        copy = name if script.working_dir is None else str(PurePath(script.working_dir) / name)
    helpers.actuator_disc(
        script,
        disc.name,
        frame=frame,
        axis=block.axis,
        offset=block.offset_m * factor,
        r_tip=block.tip_radius_m * factor,
        r_hub=block.hub_radius_m * factor,
        rpm=_solver_disc_speed(block, disc.rpm),
        thrust=disc.thrust,
        thrust_type=block.thrust_units,
        profile=copy,
        profile_force_unit=block.profile_units,
        n_blades=block.blades,
        profile_text=disc.profile_text,
        swirl=block.swirl,
        wake_type=block.wake_type,
        label=f"actuator:{disc.name}",
    )
