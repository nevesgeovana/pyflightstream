"""The time stepping of a row and the marching strategy of a build.

:class:`TimeStepping` and :func:`time_steps_of` turn the row's time keys
(or the rotor speed and the step in degrees) into the solver's step and
count; :func:`march_strategy` decides whether a build marches through the
action counter or in one command, reading the restart and wall-time cells.
"""

from __future__ import annotations

from dataclasses import (
    dataclass,
)

from pyflightstream.cases import (
    CampaignConfigError,
    SimCase,
)
from pyflightstream.commands import (
    CommandRegistry,
)
from pyflightstream.script import (
    MARCH_ACTIONS,
    MARCH_SINGLE,
    MarchStrategy,
)

from ._conventions import (
    _ACTION_COMMAND,
    BuildCapabilities,
    BuildCapabilityError,
    _builds_with_actions,
    select_workflow,
)
from ._motion import (
    _optional_rotor_speed,
)
from ._rows import (
    RotorSpeed,
    _own_speed,
    _required_float,
    _required_int,
    _variable,
    parse_restart,
    row_walltime_s,
)
from ._vocabulary import (
    ADVANCE_RATIO_VARIABLE,
    DELTA_THETA_VARIABLE,
    DELTA_TIME_VARIABLE,
    EXPORT_UNSTEADY_AFTER_ITER_VARIABLE,
    EXPORT_UNSTEADY_AFTER_REV_VARIABLE,
    RESTART_ADDITIONAL_ITERS,
    RESTART_ADDITIONAL_REVS,
    RESTART_FINISH_PENDING,
    RESTART_VARIABLE,
    REVOLUTIONS_VARIABLE,
    RPM_VARIABLE,
    TIME_ITERATIONS_VARIABLE,
    WALLTIME_VARIABLE,
)


def march_strategy(
    case: SimCase,
    *,
    capabilities: BuildCapabilities,
    registry: CommandRegistry | None = None,
) -> MarchStrategy | None:
    """Decide how an unsteady case is marched on a build, or refuse it by name.

    THE ONE SEAM. :func:`build_script` calls it once, after the coverage
    check and before the first emission; the plan and the run record carry
    what it returns.

    Parameters
    ----------
    case : SimCase
        The case about to build.
    capabilities : BuildCapabilities
        The target build's capabilities.
    registry : CommandRegistry, optional
        Alternative database, used by tests to name the builds with actions.

    Returns
    -------
    MarchStrategy or None
        None for a case that is not unsteady; ``MARCH_ACTIONS`` when the row
        states a per-step threshold or a wall clock, or its pproc a
        ``[time_averaging]`` window (G25), and the build has the actions they
        need; ``MARCH_SINGLE`` otherwise. A continuation marks no
        action of its own: it is ``MARCH_SINGLE`` unless it also states one
        of those.

    Raises
    ------
    BuildCapabilityError
        If the build documents no per-step action and the row asks for a
        per-step threshold, a wall clock, or a continuation that reads their
        records (``RESTART: {FINISH_PENDING}`` or ``{ADDITIONAL_REVS=n}``).

    Examples
    --------
    >>> from pyflightstream.cases import SimCase, SweepAxis
    >>> case = SimCase(
    ...     sim_id="7003",
    ...     aircraft="Wing",
    ...     sweep=SweepAxis(type="alpha", values=[0.0]),
    ...     recipe="unsteady",
    ...     variables={"VELOCITY": "30.0", "DELTA_TIME": "0.01", "TIME_ITERATIONS": "4"},
    ... )
    >>> march_strategy(case, capabilities=BuildCapabilities.for_build("26.120"))
    'single_march'
    """
    if select_workflow(case) not in ("unsteady", "unsteady_rotor"):
        return None
    wanted: list[tuple[str, str]] = []
    if case.variables.get(EXPORT_UNSTEADY_AFTER_ITER_VARIABLE) not in (None, ""):
        wanted.append(
            (
                f"per-step snapshot exports ({EXPORT_UNSTEADY_AFTER_ITER_VARIABLE})",
                f"remove {EXPORT_UNSTEADY_AFTER_ITER_VARIABLE}, and the plots table still "
                "records every time step",
            )
        )
    if case.variables.get(EXPORT_UNSTEADY_AFTER_REV_VARIABLE) not in (None, ""):
        wanted.append(
            (
                f"per-step snapshot exports ({EXPORT_UNSTEADY_AFTER_REV_VARIABLE})",
                f"remove {EXPORT_UNSTEADY_AFTER_REV_VARIABLE}, and the plots table still "
                "records every time step",
            )
        )
    if row_walltime_s(case) is not None:
        wanted.append(
            (
                f"the in-run wall clock ({WALLTIME_VARIABLE})",
                f"remove {WALLTIME_VARIABLE} and size {TIME_ITERATIONS_VARIABLE} to the queue; "
                f"continue a capped run with {RESTART_VARIABLE}: "
                f"{{{RESTART_ADDITIONAL_ITERS}=n}}",
            )
        )
    restart = parse_restart(case)
    if case.pproc is not None and case.pproc.time_averaging is not None and restart is None:
        # G25: the window's steps are exported through the per-step actions.
        wanted.append(
            (
                "the per-step surface exports of the pproc's [time_averaging]",
                "remove [time_averaging], and the surface exports are the run's last instant",
            )
        )
    uses_actions = bool(wanted)
    if restart is not None and restart.form in (RESTART_FINISH_PENDING, RESTART_ADDITIONAL_REVS):
        needs = (
            "the stop the wall clock records"
            if restart.form == RESTART_FINISH_PENDING
            else "the export window its step counter records"
        )
        wanted.append(
            (
                f"{RESTART_VARIABLE}: {{{restart.form}}}, which continues from {needs}",
                f"write {RESTART_VARIABLE}: {{{RESTART_ADDITIONAL_ITERS}=n}}, which reopens the "
                "saved simulation and marches n more steps",
            )
        )
    if not wanted or capabilities.unsteady_actions:
        return MARCH_ACTIONS if uses_actions else MARCH_SINGLE
    with_actions = ", ".join(_builds_with_actions(registry)) or "no registered build"
    asked = "; ".join(feature for feature, _ in wanted)
    remedies = " ".join(f"For {feature}: {remedy}." for feature, remedy in wanted)
    raise BuildCapabilityError(
        f"FlightStream build {capabilities.build} documents no unsteady solver action "
        f"({_ACTION_COMMAND}), and case {case.sim_id!r} asks for {asked}, which only those "
        f"actions provide. Set FS_BUILD to a build that documents them ({with_actions}), "
        f"or change the row. {remedies} Once they are removed, the row runs on "
        f"{capabilities.build} as a single march: the plots declared before one solver "
        "start over every time step, and the exports after it."
    )


@dataclass(frozen=True)
class TimeStepping:
    """The physical clock of an unsteady run, and which form set it.

    Attributes
    ----------
    stated_form : str
        ``angular`` (``DELTA_THETA`` and ``REVOLUTIONS``) or ``explicit``
        (``DELTA_TIME`` and ``TIME_ITERATIONS``).
    delta_time_s : float
        Solver physical time step in s.
    time_iterations : int
        Physical time steps of the whole run.
    delta_theta_deg, revolutions : float or None
        The stated pair, where the form was angular.
    rpm : float or None
        The rotor speed the conversion ran against.
    """

    stated_form: str
    delta_time_s: float
    time_iterations: int
    delta_theta_deg: float | None
    revolutions: float | None
    rpm: float | None

    @property
    def steps_per_revolution(self) -> float | None:
        """Solver steps in one revolution, or None without a rotor speed.

        FROM THE AZIMUTHAL STEP WHERE THE CLOCK WAS STATED THAT WAY, and
        from the seconds only where it was not. A revolution is 360
        degrees, so a ten-degree step is thirty-six steps exactly;
        deriving it from the seconds instead reads the rounding of the
        emitted step back as physics: 60 / (473.1723 * 0.00352) is 36.0238
        for a run that resolves 36, once the step took the reference tooling's five
        decimals.
        """
        if self.delta_theta_deg:
            return 360.0 / self.delta_theta_deg
        if self.rpm is None or self.delta_time_s <= 0.0:
            return None
        return 60.0 / (abs(self.rpm) * self.delta_time_s)

    def record(self) -> dict[str, object]:
        """Return the stated form and every form derived from it.

        NOTHING IN THIS PACKAGE CONSUMES THIS YET, and that is said here
        rather than left to be discovered: it is the record SHAPE, and
        the run record does not carry the rotor decisions today. Its
        sibling :meth:`ExportWindow.record` has stood in the same
        position since 0.8.1. What the method is for is that when a
        record does carry them, there is one place that decides what
        "them" means.

        ``rpm`` IS INCLUDED although it is an input rather than a
        derived form. ``steps_per_revolution`` below is computed FROM
        it, so a record carrying the quotient and not the divisor would
        show a reader a number they could not recover the working for.
        The paired :meth:`RotorSpeed.record` states the same rule as its
        reason for carrying every input it consumed.
        """
        return {
            "form": self.stated_form,
            "delta_time_s": self.delta_time_s,
            "time_iterations": self.time_iterations,
            "delta_theta_deg": self.delta_theta_deg,
            "revolutions": self.revolutions,
            "rpm": self.rpm,
            "steps_per_revolution": self.steps_per_revolution,
        }


def time_steps_of(case: SimCase) -> int | None:
    """Return the physical time steps one case asks for, or None for a steady row.

    The cost table of FR-82 needs this for a point it is about to plan, and
    the fit behind it needs the same number for a point already RECORDED, so
    it is one function rather than two readings of one fact.

    BOTH UNSTEADY RUN TYPES RESOLVE ONE. The first writing asked
    :func:`unsteady_time_stepping` for the ``unsteady`` recipe alone, so a
    ROTOR row -- the row whose cost anyone actually wants to know -- reported
    nothing. A rotor row states its azimuthal step and its revolutions rather
    than a count: ``DELTA_THETA`` 15 over ``REVOLUTIONS`` 1.5 is 36 steps, and
    :func:`rotor_time_stepping` is what turns the one into the other.

    Parameters
    ----------
    case : SimCase
        The case, with its sweep point already filled: a row sweeping
        ``ADVANCE_RATIO`` states no rotor speed until the point supplies the
        value, and the clock of a rotor row is resolved against that speed.

    Returns
    -------
    int or None
        The step count, or None for a steady row and for a row this reader
        cannot step. The second answers None rather than raising because the
        caller is a REPORT: a row the builder will refuse gets its refusal
        from the builder, with the builder's message, and a table meanwhile
        prints a blank instead of a number nobody can check.
    """
    if case.recipe == "steady":
        return None
    try:
        if case.recipe == "unsteady_rotor":
            stepping = rotor_time_stepping(case, speed=_optional_rotor_speed(case))
        else:
            stepping = unsteady_time_stepping(case)
        iterations = getattr(stepping, "time_iterations", None)
    except CampaignConfigError:
        iterations = None
    if iterations is None:
        # THROUGH THE TEXT, and not through `int(raw)` directly: a variable
        # cell is a str, a float or an int, and only the digits check below
        # tells the three apart safely. `int(3.7)` would silently truncate a
        # clock nobody stated that way.
        raw = str(case.variables.get(TIME_ITERATIONS_VARIABLE) or "").strip()
        iterations = int(raw) if raw.isdigit() else None
    return iterations


def rotor_time_stepping(case: SimCase, *, speed: RotorSpeed | None = None) -> TimeStepping:
    """Resolve the physical clock of an unsteady rotor run, in either form.

    Parameters
    ----------
    case : SimCase
        The case. It states ``DELTA_THETA`` and ``REVOLUTIONS``, or
        ``DELTA_TIME`` and ``TIME_ITERATIONS``; one pair, not both and
        not half of one.
    speed : RotorSpeed, optional
        The already-resolved rotor speed of THIS case, so the caller that
        needs both resolves the ratio once. Resolved here when not given.

        KEYWORD-ONLY, deliberately. Nothing here can check that a passed
        speed belongs to this case, so a speed resolved from another row
        would produce a clock that is internally consistent, exports, and
        is wrong. A keyword-only parameter cannot be supplied by
        accident from a positional call site, and the name at the call
        site is what makes the mistake visible in a diff.

    Returns
    -------
    TimeStepping

    Raises
    ------
    CampaignConfigError
        If both pairs or neither are stated; if one pair is stated half;
        or if the revolutions and the azimuthal step do not work out to
        a WHOLE number of time steps, which is refused naming the two
        numbers and the nearest pair that does.
    """
    angular = {
        key: _variable(case, key)
        for key in (DELTA_THETA_VARIABLE, REVOLUTIONS_VARIABLE)
        if _variable(case, key) is not None
    }
    explicit = {
        key: _variable(case, key)
        for key in (DELTA_TIME_VARIABLE, TIME_ITERATIONS_VARIABLE)
        if _variable(case, key) is not None
    }
    if angular and explicit:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states its clock in two forms at once: "
            f"{', '.join(f'{k}={v!r}' for k, v in sorted(angular.items()))} and "
            f"{', '.join(f'{k}={v!r}' for k, v in sorted(explicit.items()))}. The "
            "seconds and the step count are what the azimuthal step and the "
            "revolutions work out to at this rotor speed, so the second form is a "
            f"second set of numbers nobody keeps in agreement with the first. Keep "
            f"{DELTA_THETA_VARIABLE} and {REVOLUTIONS_VARIABLE}, or keep "
            f"{DELTA_TIME_VARIABLE} and {TIME_ITERATIONS_VARIABLE}."
        )
    if not angular and not explicit:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states no physical clock, so an unsteady run of it "
            f"has no step and no length. State '{DELTA_THETA_VARIABLE}: <deg>' and "
            f"'{REVOLUTIONS_VARIABLE}: <turns>', which are resolved against the rotor "
            f"speed, or '{DELTA_TIME_VARIABLE}: <s>' and "
            f"'{TIME_ITERATIONS_VARIABLE}: <steps>' to state them directly."
        )

    if explicit:
        # HALF A PAIR IS NAMED HERE rather than left to the required-value
        # helper, whose message asks for one key and says nothing about the
        # other, so a user who adds it meets the same refusal twice.
        missing = [
            key for key in (DELTA_TIME_VARIABLE, TIME_ITERATIONS_VARIABLE) if key not in explicit
        ]
        if missing:
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {', '.join(sorted(explicit))} and not "
                f"{', '.join(missing)}. The explicit clock is a PAIR: a step with no "
                "count has no length and a count with no step has no duration. Add the "
                f"missing key, or state {DELTA_THETA_VARIABLE} and "
                f"{REVOLUTIONS_VARIABLE} instead and let both be derived."
            )
        delta_time_s = _required_float(
            case, DELTA_TIME_VARIABLE, quantity="solver physical time step", unit="s"
        )
        iterations = _required_int(
            case, TIME_ITERATIONS_VARIABLE, quantity="physical time step count", unit="steps"
        )
        resolved = _own_speed(case, speed) if speed is not None else _optional_rotor_speed(case)
        return TimeStepping(
            stated_form="explicit",
            delta_time_s=delta_time_s,
            time_iterations=iterations,
            delta_theta_deg=None,
            revolutions=None,
            rpm=None if resolved is None else resolved.rpm,
        )

    missing = [key for key in (DELTA_THETA_VARIABLE, REVOLUTIONS_VARIABLE) if key not in angular]
    if missing:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {', '.join(sorted(angular))} and not "
            f"{', '.join(missing)}. The angular clock is a PAIR: an azimuthal step "
            "sets how finely one revolution is resolved and the revolutions set how "
            "many there are, and neither implies the other. Add the missing key."
        )
    theta = _required_float(case, DELTA_THETA_VARIABLE, quantity="azimuthal step", unit="degrees")
    revolutions = _required_float(
        case, REVOLUTIONS_VARIABLE, quantity="run length", unit="revolutions"
    )
    if theta <= 0.0 or theta > 360.0:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {DELTA_THETA_VARIABLE} as {theta}, and an "
            "azimuthal step is a positive angle no larger than a whole revolution. A "
            "step of 360 degrees resolves nothing inside one turn."
        )
    if revolutions <= 0.0:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {REVOLUTIONS_VARIABLE} as {revolutions}, "
            "and a run turns for a positive number of revolutions."
        )
    resolved = _own_speed(case, speed)
    if resolved.rpm == 0.0:
        raise CampaignConfigError(
            f"case {case.sim_id!r} resolves a rotor speed of zero, and a degree of "
            "rotation has no duration on a rotor that does not turn. State the clock "
            f"as {DELTA_TIME_VARIABLE} and {TIME_ITERATIONS_VARIABLE} if this run "
            "really is stationary."
        )
    # One revolution lasts 60/rpm seconds, so one degree lasts 1/(6 rpm)
    # seconds. The magnitude is what sets the clock: a rotor turning the
    # other way takes the same time to sweep the same angle.
    #
    # DERIVED AND NOT ROUNDED. The reference scripts state 0.00352 where
    # this gives 0.0035223250952, and that is the reference tooling's rounding of the
    # same derivation rather than a different clock: the correction of
    # 2026-09-04, after a session had read the rounded value as the number
    # to emit. Rounding here would end a run at an azimuth nobody chose,
    # which is what stating the revolutions exists to prevent; a comparison
    # against a file the user rounded belongs in that comparison rather than in
    # the number this package emits.
    delta_time_s = theta / (6.0 * abs(resolved.rpm))
    exact_steps = revolutions * 360.0 / theta
    steps = int(round(exact_steps))
    if abs(exact_steps - steps) > 1e-6:
        # WHOLE STEPS OR A REFUSAL. Rounding silently would move the run
        # length away from the revolutions the user asked for, and the
        # run would end mid-step at an azimuth nobody chose, which is a
        # wrong answer that converges and exports.
        low = steps * theta / 360.0
        raise CampaignConfigError(
            f"case {case.sim_id!r} asks for {revolutions} revolutions at "
            f"{theta} degrees per step, which is {exact_steps:g} time steps and not a "
            "whole number, so the run would end part way through a step at an azimuth "
            f"nobody chose. {low:g} revolutions is {steps} whole steps at this step "
            f"size; a step size that divides {revolutions} revolutions exactly is the "
            "other way to close it."
        )
    return TimeStepping(
        stated_form="angular",
        delta_time_s=delta_time_s,
        time_iterations=steps,
        delta_theta_deg=theta,
        revolutions=revolutions,
        rpm=resolved.rpm,
    )


# --- PFS-2028.01: the third run type, unsteady with nothing turning ----------


def unsteady_time_stepping(case: SimCase) -> TimeStepping:
    """Resolve the physical clock of a run that turns nothing.

    THE SECONDS AND THE COUNT, OR THE ANGULAR PAIR WITH A SPEED BESIDE IT
    (the design decision of 2026-09-04). A degree of rotation has a duration only
    against a rotor speed, and this run type meshes nothing that turns, so
    the pair was refused here outright until a row of the reference
    campaign showed the case it exists for: a wing-body in a rotor's
    slipstream, whose step is an azimuthal step of that rotor and
    whose row states its advance ratio. A row stating the pair and a speed
    is resolved exactly as the rotor type resolves it; a row stating the
    pair and no speed is refused as before, naming the two keys that
    would make it resolvable.

    IT IS A SEPARATE FUNCTION AND :func:`rotor_time_stepping` IS NOT
    TOUCHED. Extracting the shape checks the two share would save about
    ten lines and put an edit into the resolver that feeds fifteen
    committed goldens and the whole rotor clock surface. Inside a patch
    carrying a priority-zero item, "provably zero changed lines in the
    rotor resolver" is worth more than the ten lines. That is a
    deliberate choice for this release and it should be revisited.

    Parameters
    ----------
    case : SimCase
        The case; its variables carry ``DELTA_TIME`` in seconds and
        ``TIME_ITERATIONS`` as a step count.

    Returns
    -------
    TimeStepping
        The resolved clock, in the explicit stated form, carrying no
        rotor speed because the run has none.

    Raises
    ------
    CampaignConfigError
        If the row states the angular pair with no rotor speed to
        divide by, states neither pair, or states half of the explicit
        one. Each message names the case, which is the matrix POL, and
        the keys involved.
    """
    angular = {
        key: value
        for key in (DELTA_THETA_VARIABLE, REVOLUTIONS_VARIABLE)
        if (value := _variable(case, key)) is not None
    }
    if angular:
        # THE DECISION OF 2026-09-04, and the evidence is the reference campaign.
        # This run type meshes nothing that turns, and until now the
        # azimuthal pair was refused here on the ground that there was no
        # rotor speed to divide by. The reference unsteady wing-body row states one:
        # POLAR-3224 is the wing-body in a rotor's slipstream at an
        # advance ratio of 1.3, its description is UNS_WB_DTHETA20deg_REV8p0,
        # and its recorded DELTA_TIME of 0.00388 is twenty degrees at that
        # rotor's speed. So the row that states a speed takes the
        # azimuthal clock, and the row that states none is refused as
        # before, naming what would make it resolvable.
        speed = _optional_rotor_speed(case)
        if speed is None or speed.rpm == 0.0:
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {', '.join(sorted(angular))} and no rotor "
                "speed, and this run type meshes nothing that turns: an azimuthal step "
                "becomes seconds by dividing by a speed, and there is none here to "
                f"divide by. State '{ADVANCE_RATIO_VARIABLE}: <J>' or "
                f"'{RPM_VARIABLE}: <rev/min>' for the rotor whose azimuth the step "
                f"measures, or state the clock directly as '{DELTA_TIME_VARIABLE}: <s>' "
                f"and '{TIME_ITERATIONS_VARIABLE}: <steps>'."
            )
        return rotor_time_stepping(case, speed=speed)
    explicit = {
        key
        for key in (DELTA_TIME_VARIABLE, TIME_ITERATIONS_VARIABLE)
        if _variable(case, key) is not None
    }
    if not explicit:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states no physical clock, so an unsteady run of it has "
            f"no step and no length. State '{DELTA_TIME_VARIABLE}: <s>' and "
            f"'{TIME_ITERATIONS_VARIABLE}: <steps>'."
        )
    missing = [
        key for key in (DELTA_TIME_VARIABLE, TIME_ITERATIONS_VARIABLE) if key not in explicit
    ]
    if missing:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {', '.join(sorted(explicit))} and not "
            f"{', '.join(missing)}. The clock is a PAIR: a step with no count has no "
            "length and a count with no step has no duration. Add the missing key."
        )
    return TimeStepping(
        stated_form="explicit",
        delta_time_s=_required_float(
            case, DELTA_TIME_VARIABLE, quantity="solver physical time step", unit="s"
        ),
        time_iterations=_required_int(
            case, TIME_ITERATIONS_VARIABLE, quantity="physical time step count", unit="steps"
        ),
        delta_theta_deg=None,
        revolutions=None,
        rpm=None,
    )
