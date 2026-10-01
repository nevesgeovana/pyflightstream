"""Export windows and reductions: what an unsteady run averages and over which steps.

:class:`ExportWindow` and :func:`export_window` state the steps a row
exports over; :class:`ReductionPlan`, :func:`reduction_plan` and
:func:`reduction_windows` state the reductions the post-processing applies
per rotor and per blade. A new reduction joins ``REDUCTION_NAMES`` (in
``_vocabulary``) and the window reader here.
"""

from __future__ import annotations

from dataclasses import (
    dataclass,
)

from pyflightstream.cases import (
    CampaignConfigError,
    PhaseLockedSpec,
    SimCase,
)
from pyflightstream.cases import (
    windows as _windows,
)

from ._motion import (
    _optional_rotor_speed,
    _the_rotors_the_row_turns,
)
from ._rows import (
    RotorSpeed,
    _require_the_averaging_window,
    _required_float,
    _required_int,
    _variable,
    rotor_speed,
)
from ._timing import (
    rotor_time_stepping,
    unsteady_time_stepping,
)
from ._vocabulary import (
    _UNSTEADY_RECIPES,
    BLADE_FAMILIES_KEY,
    BLADES_VARIABLE,
    DELTA_TIME_VARIABLE,
    FLAT_RPM_KEY,
    LAST_ITERS_AVG_VARIABLE,
    LAST_REVS_AVG_VARIABLE,
    PERIODIC_COPIES_VARIABLE,
    ROTORS_KEY,
    RPM_VARIABLE,
    _refuse_retired_window_keys,
)

# --- PFS-2025.08: the degrees-backwards window --------------------------------


@dataclass(frozen=True)
class ExportWindow:
    """The span the expensive exports apply over, counted backwards.

    The window is stated ONCE, in whichever unit the user thinks in,
    and every other form is derived. The record carries both, so a later
    reader can see which was written and which was computed.

    Attributes
    ----------
    stated_form : str
        ``degrees``, ``steps`` or ``revolutions``: the form the user
        wrote.
    stated_value : float
        The value they wrote, verbatim and unconverted.
    steps : int
        The derived span in solver time steps.
    rpm : float or None
        Rotor speed in rev/min the degrees are counted on; None where
        the window was stated in steps and no rotor speed was given.
    delta_time_s : float or None
        Solver physical time step in s.
    time_iterations : int
        Physical time steps in the whole run; the window ends here.
    """

    stated_form: str
    stated_value: float
    steps: int
    rpm: float | None
    delta_time_s: float | None
    time_iterations: int
    #: The azimuthal step the clock was stated with, where it was; None
    #: where the row stated the seconds directly. Carried so that a
    #: revolution is counted from the ANGLE rather than from the emitted
    #: step, which is rounded to the reference precision since 2026-09-04.
    delta_theta_deg: float | None = None

    @property
    def steps_per_revolution(self) -> float | None:
        """Solver steps in one revolution, or None without the inputs.

        FROM THE AZIMUTHAL STEP WHERE THE CLOCK WAS STATED THAT WAY: a
        revolution is 360 degrees, so a ten-degree step is thirty-six
        steps exactly. Otherwise one revolution lasts ``60 / rpm`` seconds
        and one step lasts ``delta_time_s`` seconds, so a revolution is
        ``60 / (rpm * delta_time_s)`` steps.

        THE ANGLE FIRST, and a review lens is why. The emitted step is
        rounded to the reference precision since 2026-09-04, so counting a
        revolution from the seconds answered 36.0238 where the run
        resolves 36, and a one-revolution window then recorded 359.77
        degrees instead of 360.
        """
        if self.delta_theta_deg:
            return 360.0 / self.delta_theta_deg
        if self.rpm is None or self.delta_time_s is None:
            return None
        return 60.0 / (self.rpm * self.delta_time_s)

    @property
    def degrees(self) -> float | None:
        """The window in degrees of rotation, or None without a rotor speed."""
        per_revolution = self.steps_per_revolution
        if per_revolution is None:
            return None
        return 360.0 * self.steps / per_revolution

    @property
    def revolutions(self) -> float | None:
        """The window in revolutions, or None without a rotor speed."""
        per_revolution = self.steps_per_revolution
        if per_revolution is None:
            return None
        return self.steps / per_revolution

    def window_steps(self) -> tuple[int, int]:
        """Return the inclusive ``(first_step, last_step)`` span of the window.

        Counted BACKWARDS from the end of the run, which is where the
        physics of interest is: the last blade passage of a run that has
        settled, not the first of one that has not.
        """
        return (self.time_iterations - self.steps + 1, self.time_iterations)

    def record(self) -> dict[str, object]:
        """Both forms, for the run record.

        Returns
        -------
        dict
            ``form`` and ``stated`` are what the user wrote; ``steps``,
            ``degrees`` and ``revolutions`` are derived, and the last two
            are None where no rotor speed was declared, because a step
            window with no rotor speed cannot state its own degrees and
            inventing one is worse than reporting none.
        """
        return {
            "form": self.stated_form,
            "stated": self.stated_value,
            "steps": self.steps,
            "degrees": self.degrees,
            "revolutions": self.revolutions,
            "window_steps": self.window_steps(),
        }

    @classmethod
    def from_case(cls, case: SimCase) -> ExportWindow:
        """Build the window from what the row declares.

        Reads ``LAST_REVS_AVG`` or ``LAST_ITERS_AVG`` alongside the clock.
        """
        _refuse_retired_window_keys(case)
        _require_the_averaging_window(case, case.recipe)
        if (
            _variable(case, LAST_REVS_AVG_VARIABLE) is not None
            and _variable(case, LAST_ITERS_AVG_VARIABLE) is not None
        ):
            raise CampaignConfigError(
                "LAST_REVS_AVG and LAST_ITERS_AVG are two ways to say one window; state only one."
            )
        revolutions = (
            _required_float(
                case, LAST_REVS_AVG_VARIABLE, quantity="averaging window", unit="revolutions"
            )
            if _variable(case, LAST_REVS_AVG_VARIABLE) is not None
            else None
        )
        steps = (
            _required_int(
                case, LAST_ITERS_AVG_VARIABLE, quantity="averaging window", unit="iterations"
            )
            if _variable(case, LAST_ITERS_AVG_VARIABLE) is not None
            else None
        )
        # THE CLOCK IS RESOLVED, NOT READ. Both the step and the count
        # may be derived from the azimuthal step and the revolutions, so
        # reading the two cells directly would leave an angular row with
        # no window at all. The rotor speed is resolved once and handed
        # down, so the ratio is not converted twice.
        speed = _optional_rotor_speed(case)
        stepping = rotor_time_stepping(case, speed=speed)
        return export_window(
            steps=steps,
            revolutions=revolutions,
            rpm=None if speed is None else speed.rpm,
            delta_time_s=stepping.delta_time_s,
            delta_theta_deg=stepping.delta_theta_deg,
            time_iterations=stepping.time_iterations,
        )


def export_window(
    *,
    degrees: float | None = None,
    steps: int | None = None,
    revolutions: float | None = None,
    rpm: float | None = None,
    delta_time_s: float | None = None,
    delta_theta_deg: float | None = None,
    time_iterations: int,
) -> ExportWindow:
    """Build one :class:`ExportWindow`, keeping the stated form verbatim.

    Parameters
    ----------
    degrees, steps, revolutions : float, optional
        The window, in EXACTLY ONE of the three forms. Degrees are
        degrees of rotor rotation; steps are solver physical time steps;
        revolutions are whole turns.
    rpm : float, optional
        Rotor speed in rev/min the degrees are counted on. Required for
        the degrees and revolutions forms.
    delta_time_s : float, optional
        Solver physical time step in s. Required for the degrees and
        revolutions forms.
    time_iterations : int
        Physical time steps of the whole run; the window ends here and
        may not be longer than it.

    delta_theta_deg : float, optional
        Rotor rotation per solver physical time step in degrees, used to
        convert between the angular forms and steps.

    Returns
    -------
    ExportWindow
        The window, with the stated form kept verbatim and the others
        computed beside it.

    Raises
    ------
    CampaignConfigError
        If two forms or none are given; if an angular form is given with
        no rotor speed or no time step, naming the physical cause; or if
        the window is longer than the run, naming BOTH numbers.
    """
    given = {
        name: value
        for name, value in (
            ("degrees", degrees),
            ("steps", steps),
            ("revolutions", revolutions),
        )
        if value is not None
    }
    if len(given) > 1:
        raise CampaignConfigError(
            f"the export window is stated in {len(given)} forms at once "
            f"({', '.join(f'{k}={v}' for k, v in sorted(given.items()))}). State it in "
            "exactly one; the others are computed and recorded beside it, so a second "
            "stated form is a second number nobody keeps in agreement with the first."
        )
    if not given:
        raise CampaignConfigError(
            "the export window is stated in no form at all. Give exactly one of "
            "degrees (of rotor rotation), steps (solver physical time steps) or "
            "revolutions (whole turns)."
        )
    form, value = next(iter(given.items()))
    if form in ("degrees", "revolutions"):
        if rpm is None or delta_time_s is None:
            missing = "the rotor speed in rev/min" if rpm is None else "the time step in s"
            raise CampaignConfigError(
                f"an export window of {value} {form} cannot be converted without "
                f"{missing}. A degree of rotation has no duration until the rotor speed "
                "and the solver physical time step are both known: one revolution lasts "
                "60/rpm seconds and one step lasts delta_time, so the conversion needs "
                "both. State the window in steps instead if the rotor speed is not a "
                "fact of this run."
            )
        if rpm <= 0.0 or delta_time_s <= 0.0:
            raise CampaignConfigError(
                f"an angular export window needs a spinning rotor and an advancing "
                f"clock: got {rpm} rev/min and a time step of {delta_time_s} s."
            )
        per_revolution = 60.0 / (rpm * delta_time_s)
        turns = value / 360.0 if form == "degrees" else value
        span = int(round(turns * per_revolution))
    else:
        span = int(value)
    if span < 1:
        raise CampaignConfigError(
            f"an export window of {value} {form} works out at {span} solver steps, "
            "which is not a window. Widen it, or export more often."
        )
    if span > time_iterations:
        raise CampaignConfigError(
            f"the export window of {value} {form} is {span} solver steps and the run is "
            f"only {time_iterations} steps long, so it would begin before the run does. "
            "The window is counted BACKWARDS from the end of the run; shorten it, or "
            "lengthen the run."
        )
    return ExportWindow(
        stated_form=form,
        stated_value=float(value),
        steps=span,
        rpm=rpm,
        delta_time_s=delta_time_s,
        delta_theta_deg=delta_theta_deg,
        time_iterations=int(time_iterations),
    )


# --- PFS-2025.06: which windows the four reductions are taken over ------------


@dataclass(frozen=True)
class ReductionPlan:
    """Which windows the four reductions of one unsteady case are taken over.

    It is a PLAN and not a driver, and the difference is the layer rule
    rather than a preference: ``post`` sits ABOVE ``run`` and
    ``cases``, so nothing here may import the reader or the average. The
    reduction itself is
    :func:`pyflightstream.post.unsteady.blade_passage_average`, the only
    implementation of that average in the package, and the writing seam
    is :mod:`pyflightstream.post.reductions`. This object says WHICH
    windows to hand them, which is a fact of the CASE and not of the
    export.

    Attributes
    ----------
    window : ExportWindow
        The export window, which is ALSO the averaging window. One
        window, not two: two windows a user has to keep consistent is a
        defect generator.
    revolution_steps : int
        Solver steps in one whole revolution.
    period_steps : int
        Solver steps in one blade passage, being one revolution divided
        by the blade count.
    blades : int
        Blade count of the rotor.
    series_file : str
        The raw time series, which is written FIRST and ships beside
        every reduction.
    artefacts : tuple of str
        The four file names, the raw series first.
    """

    window: ExportWindow
    revolution_steps: int
    period_steps: int
    blades: int
    series_file: str
    artefacts: tuple[str, ...]

    def window_steps(self) -> tuple[int, int]:
        """Return the time-average window, which is the export window."""
        return self.window.window_steps()

    def blade_windows(self) -> list[tuple[int, int]]:
        """One window per blade, over the LAST complete revolution.

        Contiguous and inclusive, ending at the last solver step of the
        run. The per-blade split is what separates a rotor whose blades
        are not identical from one whose average hides that.
        """
        end = self.window.time_iterations
        return [
            (
                end - (self.blades - index) * self.period_steps + 1,
                end - (self.blades - 1 - index) * self.period_steps,
            )
            for index in range(self.blades)
        ]


def _blade_count(case: SimCase) -> int | None:
    """Return the blade count: ``BLADES``, ``PERIODIC_COPIES``, the sole rotor, else None.

    PFS-2015.04.01, found by the reproduction of 2026-09-09: an isolated
    rotor meshed as one blade and stated as ``PERIODIC_COPIES: 6``
    with no ``BLADES`` is a six-bladed rotor, and its phase-locked and
    per-blade reductions were skipped for want of a key that said the
    same number twice. The copies are the count when the blades are not
    stated; a row stating both keeps ``BLADES``, the key written for it.
    """
    if _variable(case, BLADES_VARIABLE) is not None:
        return _required_int(case, BLADES_VARIABLE, quantity="blade count", unit="blades")
    if _variable(case, PERIODIC_COPIES_VARIABLE) is not None:
        return _required_int(
            case, PERIODIC_COPIES_VARIABLE, quantity="periodic copy count", unit="copies"
        )
    # THE REFERENCE ALREADY STATES IT (FR-68). A row naming ONE rotor by
    # alias has said how many blades it has, in the file where the study's
    # vocabulary lives, so asking the ROW for the number again is the
    # second home this release exists to remove. One rotor only here: a
    # row turning several has no single count, and its rotors are reduced
    # one at a time by `_the_passages_of_one_rotor`.
    turning, _lost = _the_rotors_the_row_turns(case)
    if len(turning) == 1:
        block = case.rotors.get(turning[0][0])
        if block is not None and block.families_blades:
            return len(block.families_blades)
    return None


def _no_blade_count(case: SimCase) -> str:
    """Return the sentence a rotor row stating neither count is refused or skipped with.

    FOR A ROW THAT NAMES NO ROTOR BY ALIAS. A row that names its rotors
    takes each count from that rotor's block and never reaches this
    sentence through `reduction_windows`; `reduction_plan`, which is a
    public name no caller in the package uses, still can, so the sentence
    says which row it is about rather than prescribing a key that on a
    transition row would be a number that is now two numbers (the
    interface lens, 2026-09-10).
    """
    turning, _lost = _the_rotors_the_row_turns(case)
    if turning:
        return (
            f"the row of case {case.sim_id!r} names its rotors "
            f"({', '.join(alias for alias, _view, _speed in turning)}), so each reduces "
            "over ITS OWN blade passage and the ROW has no single one. Read the windows "
            f"under {ROTORS_KEY!r} of the run record, one block per rotor."
        )
    return (
        f"the row of case {case.sim_id!r} states no {BLADES_VARIABLE} and no "
        f"{PERIODIC_COPIES_VARIABLE}, so one blade passage has no length in steps and "
        "neither the phase-locked nor the per-blade reduction can be windowed. State "
        f"'{BLADES_VARIABLE}: <count>', or the sector's '{PERIODIC_COPIES_VARIABLE}: <count>'."
    )


def reduction_plan(case: SimCase) -> ReductionPlan:
    """Build the reduction plan of one unsteady rotor case.

    Parameters
    ----------
    case : SimCase
        The case; its variables carry ``BLADES`` beside the window keys
        :meth:`ExportWindow.from_case` reads.

    Returns
    -------
    ReductionPlan

    Raises
    ------
    CampaignConfigError
        If the row declares no blade count, or a window shorter than one
        blade passage.
    """
    window = ExportWindow.from_case(case)
    blades = _blade_count(case)
    if blades is None:
        raise CampaignConfigError(_no_blade_count(case))
    if blades < 1:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {blades} blades; a rotor has at least one."
        )
    per_revolution = window.steps_per_revolution
    if per_revolution is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} asks for a phase-locked and a per-blade reduction and "
            f"declares no {RPM_VARIABLE} or no {DELTA_TIME_VARIABLE}. A blade passage is "
            "a duration, and a duration needs the rotor speed in rev/min and the solver "
            "time step in s."
        )
    revolution_steps = int(round(per_revolution))
    period_steps = int(round(per_revolution / blades))
    if period_steps < 1:
        raise CampaignConfigError(
            f"case {case.sim_id!r} works out at {per_revolution:.3f} solver steps per "
            f"revolution across {blades} blades, so one blade passage is under one time "
            "step and cannot be resolved at all. Shorten the time step."
        )
    stem = f"unsteady_{case.sim_id}"
    series_file = f"{stem}_series.csv"
    return ReductionPlan(
        window=window,
        revolution_steps=revolution_steps,
        period_steps=period_steps,
        blades=blades,
        series_file=series_file,
        artefacts=(
            series_file,
            f"{stem}_time_average.csv",
            f"{stem}_phase_locked.csv",
            f"{stem}_per_blade.csv",
        ),
    )


def per_blade_window(*, last_step: int, blades: int, period_steps: int) -> tuple[int, int] | None:
    """Return THE one window every blade of a rotor is averaged over (item 8).

    The last complete revolution of the history: ``blades * period_steps``
    steps ending at ``last_step``.

    WHAT THIS REPLACES. The plan cut one window PER BLADE -- blade k from
    ``last_step - (blades - k) * period`` onwards -- so blade 1 came from one
    stretch of the history and blade 4 from another. Any difference between two
    blades then mixes a real azimuthal difference with a difference in WHEN
    they were sampled, and nothing in the file says which is which. One window
    removes the second cause entirely: even on a wheel, every blade is read over
    the same window.

    The blades are still told apart -- by their AZIMUTHS, which
    :func:`pyflightstream.post.unsteady.per_blade_rows` writes at both ends of
    this window rather than averaging away.

    None where the run holds no complete revolution: a partial turn is not
    every blade, and a short window would report three blades as four.
    """
    if blades <= 0 or period_steps <= 0:
        return None
    span = blades * period_steps
    first = last_step - span + 1
    if first < 1:
        return None
    return (first, last_step)


def phase_locked_gate(
    spec: PhaseLockedSpec | None, *, revolutions: float
) -> dict[str, object] | None:
    """Return the SKIP a short run's phase-locked reduction carries, or None.

    Item 9. `PhaseLockedSpec.generated_for` held the comparison and had NO
    CALLER, so a pproc declaring `min_revolutions` got a phase-locked reduction
    whatever the row actually turned.

    THE RULE HAS TWO HALVES and the second is the one a wiring gets wrong: if
    the matrix row reaches the minimum number of revolutions, the phase-locked
    reduction is generated; and falling short of that minimum does not refuse
    the polar, it only skips the phase-locked reduction. A short run is SKIPPED
    WITH A REASON and never refused -- losing a polar because a rotor did not
    turn long enough is taking a product away from a campaign that already
    happened.

    ABSENT IS NOT ZERO. A pproc saying nothing about `phase_locked` got one
    before this release and gets one now, so the gate changes nothing for a
    workspace that does not use it.

    Parameters
    ----------
    spec : PhaseLockedSpec or None
        The pproc's phase-locked specification; None when it states none.
    revolutions : float
        The revolutions the matrix row turns.

    Returns
    -------
    dict of str to object or None
        None when the reduction is generated (no spec, or the minimum is
        reached); otherwise the SKIP entry, with its reason, that a short run
        carries.
    """
    if spec is None or spec.generated_for(revolutions=revolutions):
        return None
    # ONE SENTENCE AND ONE COMPARISON, the resolver's, which the post stage calls
    # too when it reads the table again: a revolution counted on a clock of one
    # step is the number handed in.
    return _windows.phase_locked_entry(
        spec, last_step=revolutions, per_revolution=1.0, who="the rotor"
    )


def _every_reduction_skipped(rotor: bool, reason: str) -> dict[str, object]:
    """Build the plan of a row whose clock could not be resolved: every reduction skipped."""
    refused = {"skipped": reason}
    plan: dict[str, object] = {
        "time_iterations": None,
        "steps_per_revolution": None,
        "blades": None,
        "time_average": refused,
    }
    if rotor:
        plan["phase_locked"] = refused
        plan["per_blade"] = refused
    return plan


def _the_passages_of_one_rotor(
    case: SimCase,
    alias: str,
    view: SimCase,
    speed: RotorSpeed,
    *,
    delta_time_s: float | None,
    span: tuple[int, int],
    last_step: int,
) -> dict[str, object]:
    """Return one rotor's blade count and its two passage reductions (FR-68).

    ITS OWN REVOLUTION, not the row's. The row's clock is one rotor's
    (FR-64), and a rotor turning at another speed sweeps a different angle
    per solver step, so its revolution is a different number of steps:
    ``60 / (rpm * dt)``. Reducing the pusher over the lifters' passage is
    the defect this whole requirement is against, and it does not announce
    itself: the file is written, the columns are right, and the average is
    over the wrong window.

    The blade count is the length of the rotor's ``families_blades``,
    which is where this release already reads it for the frames and for
    the sector's copies, so the three cannot give different answers.
    """
    # ONE BLADE COUNT, READ THROUGH THE VIEW. `_motion_view` sets the
    # view's BLADES from `rotor.blade_count`, which is the model's own
    # declared rule for the number, so `_blade_count` answers here exactly
    # what it answers for the flat keys and the two cannot give different
    # numbers for one rotor. Opening `len(block.families_blades)` here
    # instead was a second home for a rule the model already states, and
    # it disagreed with the flat path wherever a row wrote `BLADES` or
    # `PERIODIC_COPIES` of its own (the architecture lens, 2026-09-10).
    #
    # THE COUNT IS NEVER NONE HERE and that is not defensive coding: the
    # view always carries BLADES, and the model refuses a rotor block
    # whose `families_blades` is empty, both measured 2026-09-10 while
    # writing a case for the empty branch that could not be built.
    blades = _blade_count(view) or 0
    entry: dict[str, object] = {"blades": blades, "rpm": speed.rpm}
    # WHERE BLADE ONE SITS, carried into the record because the PRODUCTS stage
    # needs it and cannot reach the reference artifact to ask. Item 8 writes each
    # blade's azimuth at both ends of the shared window, and every blade's angle
    # is measured from this datum: without it the products stage would assume
    # zero, which is a real azimuth and would be silently wrong for any rotor
    # whose datum is not zero.
    block = (case.rotors or {}).get(alias)
    if block is not None:
        entry["blade1_azimuth_deg"] = float(block.blade1.azimuth_deg)
        # AND WHICH FAMILIES ITS BLADES ARE, IN ITS OWN ORDER (0.24.0), for the
        # same reason: the per-blade reduction is one row per blade, a blade's
        # plots are the ones named for its family, and the products stage
        # reaches the reference only through a matrix it may not have.
        entry[BLADE_FAMILIES_KEY] = [str(family) for family in block.families_blades]
    if delta_time_s is None or not speed.rpm:
        reason = (
            f"case {case.sim_id!r} turns {alias!r} at {speed.rpm} rev/min with a solver "
            f"step of {delta_time_s}, so one blade passage of it has no length in steps."
        )
        entry["phase_locked"] = {"skipped": reason}
        entry["per_blade"] = {"skipped": reason}
        return entry
    per_revolution = 60.0 / (abs(speed.rpm) * delta_time_s)
    entry["steps_per_revolution"] = per_revolution
    period = int(round(per_revolution / blades))
    if period < 1:
        reason = (
            f"case {case.sim_id!r} turns {alias!r} at {per_revolution:.3f} solver steps "
            f"per revolution across {blades} blades, so one blade passage is under one "
            "time step and cannot be resolved at all"
        )
        entry["phase_locked"] = {"skipped": reason}
        entry["per_blade"] = {"skipped": reason}
        return entry
    entry["period_steps"] = period

    entry["phase_locked"] = _windows.phase_locked_plan(
        getattr(case.pproc, "phase_locked", None),
        last_step=last_step,
        per_revolution=per_revolution,
        who=alias,
        span=span,
        period=period,
    )
    # ITEM 8: ONE WINDOW, not one per blade. What this replaces is the list
    # that stood here -- blade k over `last_step - (blades - k) * period`
    # onwards -- so blade 1 came from one stretch of the history and blade 4
    # from another, and any difference between two blades mixed a real
    # azimuthal difference with a difference in WHEN they were sampled.
    #
    # ITEM 16: IT IS THE ROW'S WINDOW, not a second one derived here. The
    # `per_blade` average uses the same last_revs or last_iters
    # setting as the plots. `span` is what the row stated and what the POLAR and
    # the time average use; deriving the last complete revolution separately gave
    # the SAME answer only when the row asked for exactly one revolution, and a
    # different one the moment it asked for half or for three.
    #
    # `per_blade_window` still decides whether the span HOLDS a revolution to
    # split by blade, which is a different question from where the window is.
    # THE SAME INFORMATION, THIS ROTOR'S OWN STEPS. The `per_blade` average uses
    # the plots' last_revs or last_iters setting, and `last_revs_avg` is stated
    # in REVOLUTIONS: one
    # revolution of a lifter and one of a pusher are different numbers of solver
    # steps, so the same information gives each rotor a different span.
    #
    # THIS IS FR-68 AND IT IS WHY THE ROW'S SPAN IS NOT USED HERE. I wired the
    # row's span for every rotor and a test refused it, correctly: "two rotors
    # turning at two speeds have revolutions of different lengths, so one window
    # for the row would be one rotor's turn imposed on the other". Item 16 and
    # FR-68 are not in tension once the window is read as a COUNT OF
    # REVOLUTIONS rather than as a range of steps.
    #
    # NO COMPLETE-REVOLUTION GATE remains, and that is items 8 and 16 together:
    # the old shape needed a whole revolution because it CUT the window into one
    # passage per blade, and one shared window is not cut. Each blade's row
    # carries the azimuth it actually swept.
    rotor_steps = _stated_blade_steps(case, per_revolution)
    if rotor_steps is not None:
        rotor_span = (max(span[1] - rotor_steps + 1, 1), span[1])
        window_from = (
            f"the averaging window the row states, {rotor_steps} steps of {alias}, "
            "shared by every blade"
        )
    else:
        # A ROW WRITTEN BEFORE THIS RELEASE STATES NO COUNT OF REVOLUTIONS, so it
        # keeps the answer it has always had: this rotor's own last complete
        # revolution. Falling back to the ROW'S span instead would impose one
        # rotor's turn on the other, which is the defect FR-68 exists against and
        # which a test in this file refused when I tried it.
        fallback = per_blade_window(last_step=span[1], blades=blades, period_steps=period)
        if fallback is None:
            entry["per_blade"] = {
                "skipped": (
                    f"the run is {span[1]} steps and {alias} has {blades} blades of "
                    f"{period} steps each, needing {blades * period}, so the run holds no "
                    "complete revolution of it to split by blade"
                )
            }
            return entry
        rotor_span = fallback
        window_from = (
            f"the last revolution of {alias}, {blades} blades of {period} steps, "
            "shared by every blade"
        )
    entry["per_blade"] = {
        "windows": [list(rotor_span)],
        "period_steps": period,
        "window_from": window_from,
    }
    return entry


def _stated_blade_steps(case: SimCase, per_revolution: float) -> int | None:
    """Return the averaging window in THIS rotor's steps, from whichever key the row states.

    Item 16's window read as INFORMATION rather than as a range of steps, which
    is what lets it serve a row turning two rotors at two speeds. `last_revs_avg`
    says how many TURNS to average over; each rotor converts that with its OWN
    revolution, so the same instruction gives the lifter and the pusher different
    spans and neither has the other's turn imposed on it (FR-68).

    `LAST_ITERS_AVG` IS HONOURED HERE TOO, AND IT WAS NOT. This read only the
    revolutions key and returned None otherwise, so an `unsteady` row stating
    `last_iters_avg` -- the designated key for that run type -- had its POLAR and
    time average use the stated window while `per_blade` fell back to the last
    complete revolution. That is exactly the fourth-digit disagreement item 16
    exists to end, on the run type the item's own key was designed for, and the
    change log claimed the opposite. The V&V lens of the release round found it;
    every test case then passed `last_revs_avg`.

    A count of ITERATIONS is already in steps and is the same number for every
    rotor, which is the honest reading of what such a row asked for.

    None where the row states neither, so the caller falls back to the answer a
    matrix written before this release has always had.
    """
    # ONE ARITHMETIC, in `cases.windows`, which the post stage calls too (0.24.0).
    stated = {
        key: value
        for key in (LAST_REVS_AVG_VARIABLE, LAST_ITERS_AVG_VARIABLE)
        if (value := _variable(case, key)) is not None
    }
    return _windows.averaging_steps(stated, per_revolution=per_revolution)


def _averaging_window(
    case: SimCase, *, last_step: int, per_revolution: float | None
) -> tuple[tuple[int, int], str] | None:
    """Return the window the ROW states for averaging, and the sentence that says so.

    Item 16. The averaging window is a MATRIX input, `last_revs_avg` on an
    `unsteady_rotor` row and `last_iters_avg` on an `unsteady` one, and it is
    the SAME window for every unsteady product of the point -- the POLAR, the
    time average and `per_blade`.

    `last_revs_avg` TAKES A FLOAT, deliberately. One and a half revolutions is
    a window a reader can mean, and rounding it to two would
    silently average over a third more history than the row asked for.

    Returns None when neither averaging key is stated. Older recorded plans
    retain their stored windows; a new plan requires an averaging key.

    A ROW THAT STATES REVOLUTIONS WITHOUT A CLOCK gets None rather than a guess.
    Without `steps_per_revolution` a count of revolutions has no length in steps,
    and the caller's own refusal path says so with the row named.
    """
    revs = _variable(case, LAST_REVS_AVG_VARIABLE)
    iters = _variable(case, LAST_ITERS_AVG_VARIABLE)
    if revs is not None and iters is not None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states both {LAST_REVS_AVG_VARIABLE} = {revs} and "
            f"{LAST_ITERS_AVG_VARIABLE} = {iters}, and they are two ways to say one "
            "window. State the revolutions on a row that turns a rotor and the "
            "iterations on one that does not."
        )
    if revs is not None:
        turns = _required_float(
            case, LAST_REVS_AVG_VARIABLE, quantity="averaging window", unit="revolutions"
        )
        if per_revolution is None or per_revolution <= 0:
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {LAST_REVS_AVG_VARIABLE} = {revs} and the row "
                "states no rotor speed, so a count of revolutions has no length in solver "
                f"steps. State the speed, or use {LAST_ITERS_AVG_VARIABLE}."
            )
        steps = int(round(turns * float(per_revolution)))
        detail = f"{turns:g} revolution(s) of {per_revolution:g} steps"
        key = LAST_REVS_AVG_VARIABLE
    elif iters is not None:
        steps = int(
            round(
                _required_float(
                    case, LAST_ITERS_AVG_VARIABLE, quantity="averaging window", unit="iterations"
                )
            )
        )
        detail = f"{steps} iteration(s)"
        key = LAST_ITERS_AVG_VARIABLE
    else:
        return None
    if steps < 1:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states an averaging window of {steps} solver step(s), "
            "which averages nothing. State a window of at least one step."
        )
    # LONGER THAN THE RUN IS THE WHOLE RUN, not a refusal. A row asking to
    # average the last four revolutions of a run that turned three has asked for
    # everything it has, and refusing there would discard the products of a
    # campaign that already happened over an arithmetic edge.
    first = max(last_step - steps + 1, 1)
    return (first, last_step), (
        f"the averaging window the row states: {key} = {detail}, steps {first} to {last_step}"
    )


def reduction_windows(case: SimCase) -> dict[str, object] | None:
    """Resolve the windows of every applicable reduction off one row, for its record.

    The window is LAST_REVS_AVG or LAST_ITERS_AVG from the row. Removed
    WINDOW_* keys are refused. Where an older row states neither, a rotor row states
    ``DELTA_THETA`` and ``REVOLUTIONS`` (or a speed and the seconds), so a
    revolution in steps is known and the LAST revolution is the window;
    a rotorless row states ``DELTA_TIME`` and ``TIME_ITERATIONS`` and
    nothing shorter, so the whole run is. Every window is counted in
    solver steps, inclusive and 1-based, and ends at the run's last step.

    Which reductions apply is the run type's: ``unsteady_rotor`` carries
    all three, ``unsteady`` the time average alone, because a blade
    passage has no length without a rotor, and a steady row carries no
    history at all and gets None. Within a rotor row a reduction the row
    cannot window is recorded as ``skipped`` with the reason, never
    guessed: no ``BLADES`` means no passage length; a run shorter than
    one revolution has no last revolution to split by blade.

    Unresolvable clocks are recorded as skipped reductions with their reason.
    Removed row keys are refused before any window is derived.

    Parameters
    ----------
    case : SimCase
        The case, as the run stage holds it when it writes the record.

    Returns
    -------
    dict or None
        None for a run type with no time history. Otherwise a JSON-ready
        mapping: ``time_iterations``, ``steps_per_revolution`` (None
        without a rotor speed), ``blades`` (None where unstated), and one
        entry per applicable reduction, each either
        ``{"windows": [[first, last], ...], "window_from": <how the
        window was stated>}`` (the two passage reductions add
        ``period_steps``) or ``{"skipped": <reason>}``.

        A row that NAMES ITS ROTORS by alias also carries ``rotors``
        (:data:`ROTORS_KEY`), alias to that rotor's block: its ``blades``,
        its ``rpm``, its own ``steps_per_revolution`` and ``period_steps``,
        and its ``phase_locked`` and ``per_blade`` in the same two shapes
        (FR-68). On such a row the FLAT passage keys carry a skip naming
        that block, because one blade passage of the ROW has no length when
        two rotors turn at two speeds; the time average stays one window of
        the whole point. A rotor whose motion could not be resolved is a
        block carrying a skip rather than an absence, so a rotor is never
        lost from the record. A row stating no motion carries no ``rotors``
        at all and is exactly what it was.

    Examples
    --------
    >>> from pyflightstream.cases import SimCase, SweepAxis
    >>> case = SimCase(
    ...     sim_id="7001", aircraft="RotorRig", recipe="unsteady_rotor",
    ...     sweep=SweepAxis(type="alpha", values=[0.0]),
    ...     variables={"VELOCITY": "30", "RPM": "1200", "BLADES": "4",
    ...                "DELTA_TIME": "0.0001", "TIME_ITERATIONS": "720",
    ...                "LAST_REVS_AVG": "0.25"},
    ... )
    >>> plan = reduction_windows(case)
    >>> plan["time_average"]["windows"], plan["per_blade"]["period_steps"]
    ([[596, 720]], 125)
    >>> plan["per_blade"]["windows"][-1]
    [596, 720]
    """
    _refuse_retired_window_keys(case)
    if case.recipe not in _UNSTEADY_RECIPES:
        return None
    rotor = case.recipe == "unsteady_rotor"
    try:
        if rotor:
            # THE CLOCK MOTION'S SPEED where the row states its speeds in
            # MOTIONS, which `_optional_rotor_speed` resolves; `rotor_speed`
            # alone asks the ROW, and a 0.15.0 transition row carries no RPM
            # of its own, so every reduction of the point was skipped
            # (FR-64, FR-68). Falling through to `rotor_speed` keeps the
            # refusal a row with no speed anywhere has always been given.
            clock = _optional_rotor_speed(case)
            stepping = rotor_time_stepping(
                case, speed=clock if clock is not None else rotor_speed(case)
            )
        else:
            stepping = unsteady_time_stepping(case)
    except CampaignConfigError as error:
        return _every_reduction_skipped(rotor, str(error))

    last_step = stepping.time_iterations
    per_revolution = stepping.steps_per_revolution
    revolution = None if per_revolution is None else int(round(per_revolution))

    # Every unsteady product shares the averaging span stated on the row.
    averaging = _averaging_window(case, last_step=last_step, per_revolution=per_revolution)
    try:
        if averaging is not None:
            span, window_from = averaging
        elif revolution is not None:
            span = (max(last_step - revolution + 1, 1), last_step)
            window_from = (
                f"the last revolution of the run, {revolution} steps: the row states its "
                f"clock as {stepping.stated_form} and no averaging key"
            )
        else:
            span = (1, last_step)
            window_from = (
                "the whole run: the row states DELTA_TIME and TIME_ITERATIONS and no "
                "averaging key, and nothing shorter is stated"
            )
    except CampaignConfigError as error:
        return _every_reduction_skipped(rotor, str(error))
    plan: dict[str, object] = {
        # WHERE THE WINDOW CAME FROM, recorded so a reader downstream can tell a
        # window the ROW STATED from one this function defaulted. The products
        # stage needs that distinction and had no way to make it: every unsteady
        # record carries a `time_average` window, including one that fell through
        # to "the whole run", so a gate on "is there a window" is really a gate
        # on "is this point unsteady at all".
        "window_stated": averaging is not None,
        "time_iterations": last_step,
        "steps_per_revolution": per_revolution,
        "blades": None,
        "time_average": {"windows": [list(span)], "window_from": window_from},
    }
    if not rotor:
        return plan

    # THE SPEED OF A ROW THAT STATES ITS ROTOR WITH FLAT KEYS (0.24.0). It plans no
    # per-rotor block, and the rotor table read a rotor's speed from that block
    # alone, so such a row never got its table although the clock above was
    # computed from this very number. Signed, as a block's is. A row whose speed
    # cannot be resolved states none, and every reduction below says why.
    try:
        plan[FLAT_RPM_KEY] = float(rotor_speed(case).rpm)
    except CampaignConfigError:
        pass

    # ONE BLOCK PER ROTOR THE ROW TURNS (FR-68), each over its OWN blade
    # passage. A row turning one rotor also gets a block, so the products
    # may name it, and the flat keys below stay exactly what they were: a
    # row that states no motion, which is every row written before 0.15.0,
    # reduces as it always did.
    turning, lost = _the_rotors_the_row_turns(case)
    if turning or lost:
        rotors: dict[str, object] = {
            alias: _the_passages_of_one_rotor(
                case,
                alias,
                view,
                speed,
                delta_time_s=stepping.delta_time_s,
                span=span,
                last_step=last_step,
            )
            for alias, view, speed in turning
        }
        # A ROTOR THAT COULD NOT BE RESOLVED IS A SKIP, NOT AN ABSENCE. It
        # used to be dropped silently, so the rotor appeared in neither the
        # products nor the skipped list of the manifest and simply vanished
        # (the architecture lens, 2026-09-10). This shape is the one the
        # products stage already knows how to record.
        for named, reason in lost.items():
            rotors.setdefault(
                named,
                {
                    "blades": None,
                    "phase_locked": {"skipped": reason},
                    "per_blade": {"skipped": reason},
                },
            )
        plan[ROTORS_KEY] = rotors
        # A ROW THAT NAMES ITS ROTORS REDUCES PER ROTOR, AND ONLY PER
        # ROTOR. The flat passage keys carry the pointer, one rotor or
        # nine, and that uniformity is the whole of the interface lens's
        # finding of 2026-09-10: gating the rotor's name on there being
        # MORE THAN ONE made the rotor count a file-naming input, so the
        # day a second rotor is added every script pointing at
        # `<point>_per_blade.csv` stops finding its input and the stale
        # file from the one-rotor run stays on disk beside a record that
        # calls it skipped. It is also what FR-68's own sentence says,
        # unconditionally: "the reduction files name the rotor".
        #
        # A ROW STATING NO MOTION IS UNTOUCHED, which is FR-68's other
        # sentence and what keeps every workspace written before 0.15.0,
        # and every golden, reducing into exactly the files it always did.
        named = ", ".join(rotors)
        plan["blades"] = _blade_count(case)
        pointer = (
            f"case {case.sim_id!r} names its rotors, so each reduces over ITS OWN blade "
            f"passage and there is no single passage of the ROW: the windows are under "
            f"{ROTORS_KEY!r} ({named}) and the products stage writes one file per rotor, "
            f"named <point>_<reduction>_<alias>.csv."
        )
        plan["phase_locked"] = {"skipped": pointer}
        plan["per_blade"] = {"skipped": pointer}
        return plan

    # THE PASSAGE REDUCTIONS need a revolution and a blade count.
    try:
        blades = _blade_count(case)
    except CampaignConfigError as error:
        plan["phase_locked"] = {"skipped": str(error)}
        plan["per_blade"] = {"skipped": str(error)}
        return plan
    if blades is None:
        reason = _no_blade_count(case)
        plan["phase_locked"] = {"skipped": reason}
        plan["per_blade"] = {"skipped": reason}
        return plan
    plan["blades"] = blades
    # THE SAME DATUM ON THE ROW-LEVEL PATH. A row that names one rotor block
    # still has one, and item 8's azimuth columns are measured from it. A row
    # that declares no rotor block leaves the key absent rather than writing a
    # zero, because zero IS a real azimuth and the products stage must be able
    # to tell "the datum is zero" from "nobody said".
    _flat_rotor = next(iter((case.rotors or {}).values()), None)
    if _flat_rotor is not None:
        plan["blade1_azimuth_deg"] = float(_flat_rotor.blade1.azimuth_deg)
        plan[BLADE_FAMILIES_KEY] = [str(family) for family in _flat_rotor.families_blades]
    if revolution is None or per_revolution is None or blades < 1:
        reason = (
            f"case {case.sim_id!r} declares {blades} blades and "
            f"{per_revolution} steps per revolution, so a blade passage has no length"
        )
        plan["phase_locked"] = {"skipped": reason}
        plan["per_blade"] = {"skipped": reason}
        return plan
    period = int(round(per_revolution / blades))
    if period < 1:
        reason = (
            f"case {case.sim_id!r} works out at {per_revolution:.3f} solver steps per "
            f"revolution across {blades} blades, so one blade passage is under one time "
            "step and cannot be resolved at all"
        )
        plan["phase_locked"] = {"skipped": reason}
        plan["per_blade"] = {"skipped": reason}
        return plan

    plan["phase_locked"] = _windows.phase_locked_plan(
        getattr(case.pproc, "phase_locked", None),
        last_step=last_step,
        per_revolution=per_revolution,
        who="the rotor",
        span=span,
        period=period,
    )
    # One window per blade over the LAST complete revolution, contiguous
    # and ending at the run's last step: :meth:`ReductionPlan.blade_windows`.
    # ITEM 8: ONE WINDOW, not one per blade. What this replaces is the list
    # that stood here -- blade k over `last_step - (blades - k) * period`
    # onwards -- so blade 1 came from one stretch of the history and blade 4
    # from another, and any difference between two blades mixed a real
    # azimuthal difference with a difference in WHEN they were sampled.
    #
    # ITEM 16 ON THIS PATH TOO: the window is the ROW'S, the same one the POLAR
    # and the time average use, and not a second derivation. Deriving the last
    # complete revolution here agreed with the row only when the row asked for
    # exactly one, and disagreed the moment it asked for half or for three.
    # THE ROW'S OWN COUNT OF REVOLUTIONS, in this row's steps; see the note on
    # the per-rotor path for why the window is read as a COUNT rather than as a
    # range. A row stating `last_revs_avg` gets exactly that many turns.
    #
    # A ROW WRITTEN BEFORE THIS RELEASE KEEPS THE ANSWER IT HAS ALWAYS HAD: its
    # last complete revolution. That is the whole migration for `per_blade` --
    # existing matrices produce the same windows they did, and only a row
    # that states the new key moves.
    wanted = _stated_blade_steps(case, per_revolution or 0.0)
    if wanted is not None:
        blade_span: tuple[int, int] | None = (max(span[1] - wanted + 1, 1), span[1])
        window_from = f"the averaging window the row states, {wanted} steps, shared by every blade"
    else:
        blade_span = per_blade_window(last_step=span[1], blades=blades, period_steps=period)
        window_from = (
            f"the last revolution of the run, {blades} blades of {period} steps, "
            "shared by every blade"
        )
    if blade_span is None:
        plan["per_blade"] = {
            "skipped": (
                f"the run is {span[1]} steps and {blades} blades of {period} steps each "
                f"need {blades * period}, so it holds no complete revolution to split "
                "by blade"
            )
        }
    else:
        plan["per_blade"] = {
            "windows": [list(blade_span)],
            "period_steps": period,
            "window_from": window_from,
        }
    return plan
