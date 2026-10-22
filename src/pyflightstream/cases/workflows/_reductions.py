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
    RotorBlock,
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
    _the_rotor_a_flat_row_turns,
    _variable,
    rotor_speed,
)
from ._timing import (
    TimeStepping,
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
    delta_theta_deg : float or None
        The azimuthal step the clock was stated with, where it was.
    clipped_from_steps : int or None
        The span the row asked for, in solver steps, when it was longer than
        the run and was cut to the whole run; None when nothing was cut.
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
    #: step, which is rounded to the reference precision.
    delta_theta_deg: float | None = None
    #: The span the row asked for, in solver steps, when it was longer than the
    #: run and was cut to it (X-F-0303); None where nothing was cut.
    clipped_from_steps: int | None = None

    @property
    def steps_per_revolution(self) -> float | None:
        """Solver steps in one revolution, or None without the inputs.

        FROM THE AZIMUTHAL STEP WHERE THE CLOCK WAS STATED THAT WAY: a
        revolution is 360 degrees, so a ten-degree step is thirty-six
        steps exactly. Otherwise one revolution lasts ``60 / rpm`` seconds
        and one step lasts ``delta_time_s`` seconds, so a revolution is
        ``60 / (rpm * delta_time_s)`` steps.

        Use the angle first. The emitted step is rounded to the reference
        precision, so deriving revolutions from seconds can yield 36.0238
        steps where the run resolves 36, or a one-revolution window of
        359.77 degrees instead of 360.
        """
        if self.delta_theta_deg:
            return 360.0 / self.delta_theta_deg
        if not self.rpm or self.delta_time_s is None or self.delta_time_s <= 0:
            return None
        # THE MAGNITUDE: a rotor turning the other way (`rpm_sign` -1) takes the
        # same number of steps per revolution, as TimeStepping counts it.
        return 60.0 / (abs(self.rpm) * self.delta_time_s)

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
            inventing one is worse than reporting none. ``clipped_from_steps``
            appears only when the stated window was longer than the run and
            was cut to it.
        """
        record: dict[str, object] = {
            "form": self.stated_form,
            "stated": self.stated_value,
            "steps": self.steps,
            "degrees": self.degrees,
            "revolutions": self.revolutions,
            "window_steps": self.window_steps(),
        }
        if self.clipped_from_steps is not None:
            # THE CUT IS IN THE RECORD: a window that reads as stated over a run
            # shorter than it is a sentence a reader takes at its word.
            record["clipped_from_steps"] = self.clipped_from_steps
        return record

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
        Physical time steps of the whole run. The window ends here and
        is clipped to the available history when it is longer.

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
        the run or the resolved window contains no time steps.
    """
    if time_iterations < 1:
        raise CampaignConfigError("an export window requires at least one solver time step")
    if delta_theta_deg is not None and not delta_theta_deg > 0.0:
        raise CampaignConfigError(
            f"the export window is given an azimuthal step of {delta_theta_deg} degrees, and "
            "a step advances the rotor by a positive angle; the window would otherwise be "
            "recorded in negative degrees and revolutions."
        )
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
        # THE SPEED IS SIGNED BY THE HAND, so its magnitude is what spins: a
        # left-handed rotor was refused here as not spinning.
        if rpm == 0.0 or delta_time_s <= 0.0:
            raise CampaignConfigError(
                f"an angular export window needs a spinning rotor and an advancing "
                f"clock: got {rpm} rev/min and a time step of {delta_time_s} s."
            )
        per_revolution = (
            360.0 / delta_theta_deg
            if delta_theta_deg is not None and delta_theta_deg > 0
            else 60.0 / (abs(rpm) * delta_time_s)
        )
        turns = value / 360.0 if form == "degrees" else value
        span = int(round(turns * per_revolution))
    else:
        span = int(value)
    if span < 1:
        raise CampaignConfigError(
            f"an export window of {value} {form} works out at {span} solver steps, "
            "which is not a window. Widen it, or export more often."
        )
    clipped_from = span if span > time_iterations else None
    span = min(span, time_iterations)
    return ExportWindow(
        stated_form=form,
        stated_value=float(value),
        steps=span,
        rpm=rpm,
        delta_time_s=delta_time_s,
        delta_theta_deg=delta_theta_deg,
        time_iterations=int(time_iterations),
        clipped_from_steps=clipped_from,
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


def _the_count_the_block_declares(case: SimCase, block: RotorBlock, stated: int | None) -> int:
    """Return the blade count a rotor block declares, refusing a ``BLADES`` that contradicts it.

    A block that lists the families the MESH carries, with the row's
    ``PERIODIC_COPIES`` supplying the rest of the wheel (a one-blade sector
    stated as six copies), is not contradicted by ``BLADES: 6``: the families
    times the copies is that count, and the row is valid as it was before
    the block became the count. Any other disagreement is refused, naming both.
    """
    declared = len(block.families_blades)
    if stated is None or stated == declared:
        return declared
    copies = (
        _required_int(case, PERIODIC_COPIES_VARIABLE, quantity="periodic copy count", unit="copies")
        if _variable(case, PERIODIC_COPIES_VARIABLE) is not None
        else None
    )
    if copies is not None and declared * copies == stated:
        return stated
    raise CampaignConfigError(
        f"case {case.sim_id!r} states {BLADES_VARIABLE}: {stated} and its reference "
        f"declares rotor {block.alias!r} with {declared} blade(s) "
        f"({', '.join(block.families_blades)}). The block is the count (FR-68); "
        f"remove {BLADES_VARIABLE} from the row, or correct the block."
    )


def _blade_count(case: SimCase) -> int | None:
    """Return the blade count: the sole rotor's block, ``BLADES``, ``PERIODIC_COPIES``, else None.

    THE BLOCK FIRST (FR-68). A row whose reference declares its one rotor has
    said how many blades it has, in the file where the study's vocabulary
    lives. ``PERIODIC_COPIES`` is what the FILE is, not the rotor: a 4-blade
    rotor meshed as a 2-blade half states two copies, and reading those as
    blades halved its passage and its per-blade table. A row ``BLADES`` that
    disagrees with the block is refused, naming both.

    PFS-2015.04.01: an isolated
    rotor meshed as one blade and stated as ``PERIODIC_COPIES: 6``, with no
    block and no ``BLADES``, is a six-bladed rotor. The copies are the count
    only where nothing else states it.
    """
    # One rotor only: a row turning several has no single count, and its
    # rotors are reduced one at a time by `_the_passages_of_one_rotor`.
    block = None
    if case.motions:
        turning, _lost = _the_rotors_the_row_turns(case)
        if len(turning) == 1:
            block = case.rotors.get(turning[0][0])
    else:
        block = _the_rotor_a_flat_row_turns(case)
    stated = (
        _required_int(case, BLADES_VARIABLE, quantity="blade count", unit="blades")
        if _variable(case, BLADES_VARIABLE) is not None
        else None
    )
    if block is not None and block.families_blades:
        return _the_count_the_block_declares(case, block, stated)
    if stated is not None:
        return stated
    if _variable(case, PERIODIC_COPIES_VARIABLE) is not None:
        return _required_int(
            case, PERIODIC_COPIES_VARIABLE, quantity="periodic copy count", unit="copies"
        )
    return None


def _no_blade_count(case: SimCase) -> str:
    """Return the sentence a rotor row stating neither count is refused or skipped with.

    FOR A ROW THAT NAMES NO ROTOR BY ALIAS. A row that names its rotors
    takes each count from that rotor's block and never reaches this
    sentence through `reduction_windows`; `reduction_plan`, which is a
    public name no caller in the package uses, still can, so the sentence
    says which row it is about rather than prescribing a key that on a
    transition row would need a separate value for each rotor.
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

    Item 9. Apply `PhaseLockedSpec.generated_for` to the revolutions the row
    actually turns before generating a phase-locked reduction.

    THE RULE HAS TWO HALVES and the second is the one a wiring gets wrong: if
    the matrix row reaches the minimum number of revolutions, the phase-locked
    reduction is generated; and falling short of that minimum does not refuse
    the polar, it only skips the phase-locked reduction. A short run is SKIPPED
    WITH A REASON and never refused -- losing a polar because a rotor did not
    turn long enough is taking a product away from a campaign that already
    happened.

    A pproc saying nothing about `phase_locked` receives a phase-locked
    reduction without a declared minimum-revolution gate.

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
    clock: TimeStepping | None = None,
) -> dict[str, object]:
    """Return one rotor's blade count and its two passage reductions (FR-68).

    ITS OWN REVOLUTION, not the row's. The row's clock is one rotor's
    (FR-64), and a rotor turning at another speed sweeps a different angle
    per solver step, so its revolution is a different number of steps:
    ``60 / (rpm * dt)``. Reducing the pusher over the lifters' passage is
    the defect this whole requirement is against, and it does not announce
    itself: the file is written, the columns are right, and the average is
    over the wrong window.

    The blade count comes through the rotor's motion view, sharing the
    model's count with the flat path, frames and sector copies.
    """
    # Read the blade count through the motion view: _motion_view sets BLADES
    # from rotor.blade_count, sharing the model's rule with the flat path.
    # The count cannot be None: the view carries BLADES and the model refuses
    # a rotor block with empty families_blades.
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
        # AND WHICH FAMILIES ITS BLADES ARE, IN ITS OWN ORDER, for the
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
    per_revolution = _own_steps_per_revolution(speed.rpm, delta_time_s, clock)
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

    rotor_steps = _stated_blade_steps(case, per_revolution)
    own_steps = rotor_steps if rotor_steps is not None else int(round(per_revolution))
    own_span = (max(last_step - own_steps + 1, 1), last_step)
    entry["phase_locked"] = _windows.phase_locked_plan(
        getattr(case.pproc, "phase_locked", None),
        last_step=last_step,
        per_revolution=per_revolution,
        who=alias,
        span=own_span,
        period=per_revolution / blades,
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
    if rotor_steps is not None:
        rotor_span = (max(span[1] - rotor_steps + 1, 1), span[1])
        window_from = (
            f"the averaging window the row states, {rotor_steps} steps of {alias}, "
            "shared by every blade"
        )
    else:
        # Without a stated revolution count, use this rotor's own last complete
        # revolution. The row's span could impose another rotor's turn on it
        # and violate FR-68.
        if last_step < own_steps:
            entry["per_blade"] = {
                "skipped": (
                    f"the run is {span[1]} steps and {alias} has {blades} blades of "
                    f"{per_revolution / blades} steps each, needing {own_steps}, "
                    "so the run holds no "
                    "complete revolution of it to split by blade"
                )
            }
            return entry
        rotor_span = own_span
        window_from = (
            f"the last revolution of {alias}, {own_steps} solver steps, shared by every blade"
        )
    entry["per_blade"] = {
        "windows": [list(rotor_span)],
        "period_steps": period,
        "window_from": window_from,
    }
    return entry


def _own_steps_per_revolution(rpm: float, delta_time_s: float, clock: TimeStepping | None) -> float:
    """Return one rotor's steps per revolution, from the azimuthal step where the clock has one.

    THE PACKAGE'S OWN RULE (`TimeStepping.steps_per_revolution`): a ten-degree
    step is thirty-six steps a turn exactly, and the seconds derived from it read
    back as 36.0000000001. A rotor at another speed sweeps the clock rotor's
    step scaled by the ratio of the speeds, which is exactly 1 for the clock
    rotor itself.
    """
    if clock is not None and clock.delta_theta_deg and clock.rpm:
        return (360.0 / clock.delta_theta_deg) * (abs(clock.rpm) / abs(rpm))
    return 60.0 / (abs(rpm) * delta_time_s)


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

    None where the row states neither, so the caller uses its default window.
    """
    # ONE ARITHMETIC, in `cases.windows`, which the post stage calls too.
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

    A ROW THAT STATES REVOLUTIONS WITHOUT A CLOCK IS REFUSED rather than guessed:
    without `steps_per_revolution` a count of revolutions has no length in steps.
    The refusal names the row, and :func:`reduction_windows` records it as every
    reduction skipped with that reason.
    """
    try:
        stated = _windows.stated_key(case.variables)
        steps = _windows.averaging_steps(case.variables, per_revolution=per_revolution)
    except CampaignConfigError as error:
        raise CampaignConfigError(f"case {case.sim_id!r}: {error}") from error
    if stated is None:
        return None
    key, value = stated
    if steps is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {key} = {value:g} and the row "
            "states no rotor speed, so a count of revolutions has no length in solver "
            f"steps. State the speed, or use {LAST_ITERS_AVG_VARIABLE}."
        )
    detail = (
        f"{value:g} revolution(s) of {per_revolution:g} steps"
        if key == LAST_REVS_AVG_VARIABLE
        else f"{steps} iteration(s)"
    )
    # LONGER THAN THE RUN IS THE WHOLE RUN, not a refusal. A row asking to
    # average the last four revolutions of a run that turned three has asked for
    # everything it has, and refusing there would discard the products of a
    # campaign that already happened over an arithmetic edge.
    first = max(last_step - steps + 1, 1)
    # AND THE RECORD SAYS SO: "the window the row states" over a window that
    # was cut is a sentence a reader of the record takes at its word.
    cut = (
        f", cut to the whole run because the run is {last_step} step(s) and the window {steps}"
        if steps > last_step
        else ""
    )
    return (first, last_step), (
        f"the averaging window the row states: {key} = {detail}, steps {first} to {last_step}{cut}"
    )


def _time_average_span(
    case: SimCase,
    stepping: TimeStepping,
    *,
    last_step: int,
    per_revolution: float | None,
    revolution: int | None,
) -> tuple[bool, tuple[int, int], str]:
    """Return whether the row states its averaging window, the window, and where it came from."""
    averaging = _averaging_window(case, last_step=last_step, per_revolution=per_revolution)
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
    return averaging is not None, span, window_from


def _named_rotors_plan(
    case: SimCase,
    plan: dict[str, object],
    turning: list[tuple[str, SimCase, RotorSpeed]],
    lost: dict[str, str],
    *,
    stepping: TimeStepping,
    span: tuple[int, int],
    last_step: int,
) -> dict[str, object]:
    """Add the per-rotor blocks of a row that names its rotors, and the flat pointers."""
    rotors: dict[str, object] = {
        alias: _the_passages_of_one_rotor(
            case,
            alias,
            view,
            speed,
            delta_time_s=stepping.delta_time_s,
            span=span,
            last_step=last_step,
            clock=stepping,
        )
        for alias, view, speed in turning
    }
    # Record an unresolved rotor as a skip, preserving it and its reason
    # in the shape the products stage records in the manifest.
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
    # A row naming its rotors reduces per rotor (FR-68). The reduction files
    # name the rotor even when there is only one, so adding another rotor
    # does not rename existing products. The flat passage keys carry the
    # pointer. A row stating no motion uses the flat reduction files.
    named = ", ".join(rotors)
    try:
        plan["blades"] = _blade_count(case)
    except CampaignConfigError:
        # Each rotor's own block carries its count and its skip; the row's
        # single count is a convenience no reduction reads.
        plan["blades"] = None
    pointer = (
        f"case {case.sim_id!r} names its rotors, so each reduces over ITS OWN blade "
        f"passage and there is no single passage of the ROW: the windows are under "
        f"{ROTORS_KEY!r} ({named}) and the products stage writes one file per rotor, "
        f"named <point>_<reduction>_<alias>.csv."
    )
    plan["phase_locked"] = {"skipped": pointer}
    plan["per_blade"] = {"skipped": pointer}
    return plan


def _flat_row_passages(
    case: SimCase,
    plan: dict[str, object],
    *,
    span: tuple[int, int],
    last_step: int,
    per_revolution: float | None,
    revolution: int | None,
) -> dict[str, object]:
    """Add the passage reductions of a flat-key rotor row, or their skips."""
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
        period=per_revolution / blades,
    )
    # Use one shared window for every blade so blade comparisons sample
    # the same time interval (item 8). Read the row's requested revolution
    # count, as for the polar and time average (item 16). With no count,
    # use the last complete revolution; with last_revs_avg, use that many
    # turns in this rotor's steps.
    wanted = _stated_blade_steps(case, per_revolution or 0.0)
    if wanted is not None:
        blade_span: tuple[int, int] | None = (max(span[1] - wanted + 1, 1), span[1])
        window_from = f"the averaging window the row states, {wanted} steps, shared by every blade"
    else:
        # THE LAST REVOLUTION IN WHOLE STEPS, rounded once: blades times a rounded
        # blade passage is not a revolution (five blades of 7.2 steps made 35, not 36).
        whole_revolution = int(round(per_revolution))
        blade_span = (
            (span[1] - whole_revolution + 1, span[1])
            if whole_revolution >= 1 and span[1] - whole_revolution + 1 >= 1
            else None
        )
        window_from = (
            f"the last revolution of the run, {whole_revolution} steps over {blades} "
            "blades, shared by every blade"
        )
    if blade_span is None:
        plan["per_blade"] = {
            "skipped": (
                f"the run is {span[1]} steps and one revolution of {blades} blades is "
                f"{int(round(per_revolution))} steps, so it holds no complete revolution "
                "to split by blade"
            )
        }
    else:
        plan["per_blade"] = {
            "windows": [list(blade_span)],
            "period_steps": period,
            "window_from": window_from,
        }
    return plan


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
            # Use the clock motion's speed for MOTIONS rows (FR-64, FR-68), resolved
            # by _optional_rotor_speed. Fall through to rotor_speed for its refusal
            # when the row states no speed anywhere.
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
    # INSIDE THE TRY, as the docstring promises: a window the row states and the
    # clock cannot resolve is a skip with its reason, not an exception out of
    # the point record the run is building.
    try:
        stated, span, window_from = _time_average_span(
            case,
            stepping,
            last_step=last_step,
            per_revolution=per_revolution,
            revolution=revolution,
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
        "window_stated": stated,
        "time_iterations": last_step,
        "steps_per_revolution": per_revolution,
        "blades": None,
        "time_average": {"windows": [list(span)], "window_from": window_from},
    }
    if not rotor:
        return plan

    # THE SPEED OF A ROW THAT STATES ITS ROTOR WITH FLAT KEYS. It plans no
    # per-rotor block, and the rotor table read a rotor's speed from that block
    # alone, so such a row never got its table although the clock above was
    # computed from this very number. Signed, as a block's is. A row whose speed
    # cannot be resolved states none, and every reduction below says why.
    try:
        plan[FLAT_RPM_KEY] = float(rotor_speed(case).rpm)
    except CampaignConfigError:
        pass

    # One block per rotor the row turns (FR-68), each over its own blade
    # passage, including a single rotor. The flat keys below serve rows
    # that state no motion.
    turning, lost = _the_rotors_the_row_turns(case)
    if turning or lost:
        return _named_rotors_plan(
            case, plan, turning, lost, stepping=stepping, span=span, last_step=last_step
        )
    return _flat_row_passages(
        case,
        plan,
        span=span,
        last_step=last_step,
        per_revolution=per_revolution,
        revolution=revolution,
    )
