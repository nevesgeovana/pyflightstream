"""The clock of an unsteady run: export thresholds, the action counter and the wall clock.

:class:`UnsteadyExportThreshold` and :func:`unsteady_export_threshold`
decide the step from which an unsteady run exports; the action lines, the
step counter (:func:`unsteady_counter_steps`), the wall-clock program and
the stop text are what the run writes beside its script to watch itself.
"""

from __future__ import annotations

from dataclasses import (
    dataclass,
)
from pathlib import (
    PurePath,
)

from pyflightstream.cases import (
    EXPORT_KINDS,
    STEADY_ONLY_EXPORT_KINDS,
    VOLUME_SECTION_KINDS,
    CampaignConfigError,
    SimCase,
    classify_outputs,
)
from pyflightstream.cases._unsteady_actions import (
    WALLTIME_CLOCK_STATE,
    WALLTIME_STOP_SCRIPT,
)
from pyflightstream.script import (
    Script,
)
from pyflightstream.versions import (
    FsVersion,
)

from ._conventions import (
    WorkflowConventions,
    select_workflow,
)
from ._export_first_step import (
    refuse_a_threshold_after_the_averaging_start,
    refuse_threshold_on_a_steady_run,
    refuse_two_threshold_keys,
    resolve_first_step,
    stated_threshold_keys,
)
from ._exports import (
    _UPDATED_KINDS,
    _surface_export,
    surface_time_averaging,
)
from ._freestream import (
    refuse_a_wake_length,
)
from ._motion import (
    _motion_view,
)
from ._rows import (
    _variable,
    continuation_of,
    rotor_speed,
    row_walltime_s,
    walltime_margin_s,
)
from ._timing import (
    TimeStepping,
    rotor_time_stepping,
    unsteady_time_stepping,
)
from ._vocabulary import (
    _UNSTEADY_RECIPES,
    END_OF_RUN_EXPORT_KINDS,
    ROTORLESS_REFUSED_KEYS,
    WALLTIME_STOP_VERB,
    WALLTIME_VARIABLE,
    WHOLE_RUN_EXPORT_KINDS,
)


def _refuse_rotor_keys_on_a_rotorless_run(case: SimCase) -> None:
    """Refuse a rotor key on a run type that emits no motion.

    Raised BEFORE the first emission, so a refusal leaves the script
    exactly as it was.
    """
    found = sorted(key for key in ROTORLESS_REFUSED_KEYS if _variable(case, key) is not None)
    if not found:
        return
    raise CampaignConfigError(
        f"case {case.sim_id!r} states {', '.join(found)} and names a run type that emits "
        "no motion, so nothing would read them and the run would be recorded as though "
        "they had been honoured. State them on the rotor run type, which turns a rotor, "
        "or drop them from this row."
    )


def _refuse_wake_termination_without_a_rotor(case: SimCase) -> None:
    """Refuse a wake termination stated in revolutions on a rotorless run.

    A THIRD SIBLING, and it exists because the two that already guard
    this setting both give this run type FALSE advice. The rotor one
    says the row states no rotor speed and to add one, which would build
    a clock out of a speed nothing turns at. The steady one says the run
    is steady and has no time loop, and this run type has a time loop.
    A refusal that misdescribes the run it is refusing teaches the reader
    the wrong thing about their own row.
    """
    refuse_a_wake_length(case, "names a run type that turns nothing")
    revolutions = case.solver.wake_termination_revolutions
    if revolutions is None:
        return
    raise CampaignConfigError(
        f"case {case.sim_id!r} inherits a wake termination of {revolutions} revolutions "
        "from its solver preset and names a run type that turns nothing, so there is no "
        "revolution for it to be counted in. This run has a time loop, so the setting is "
        "not meaningless in principle; it is unstateable in revolutions, and this package "
        "records no steps-spelled preset key for it. Drop the key from the preset this "
        "row names, or give the row a preset of its own."
    )


@dataclass(frozen=True)
class UnsteadyExportThreshold:
    """The step the per-step exports begin on, and what they export.

    Attributes
    ----------
    stated_form : str
        ``revolutions``, ``iterations``, ``last_revolutions`` or
        ``last_iterations``: the key the row wrote.
    stated_value : float
        The value it wrote.
    first_step : int
        The first time step whose export runs: the step at which the
        invocation count reaches the threshold. ``EXPORT_UNSTEADY_AFTER_ITER:
        4`` exports at steps 4 to the end; one revolution at ten degrees a
        step exports from step 36.
    time_iterations : int
        Physical time steps of the whole run.
    delta_time_s : float
        Solver physical time step in s, written into the program so it
        can state the physical time of each count.
    step_deg : float or None
        Degrees of rotor azimuth per time step, None on a run whose clock
        has no rotor behind it.
    rpm : float or None
        The rotor speed the azimuth is counted against, None likewise.
    exports : str
        The child script text the file carries from ``first_step`` on.
    """

    stated_form: str
    stated_value: float
    first_step: int
    time_iterations: int
    delta_time_s: float
    step_deg: float | None
    rpm: float | None
    exports: str

    @property
    def program_form(self) -> str:
        """Return the form the counter program compares in.

        A last form counts back from the end of the run, which the program
        cannot know, so it compares the invocation count against the
        resolved first step: the program of ``EXPORT_UNSTEADY_LAST_REV`` is
        that of ``EXPORT_UNSTEADY_AFTER_ITER`` with the same first step
        (FR-415 R1).
        """
        return "iterations" if self.stated_form.startswith("last_") else self.stated_form

    @property
    def program_value(self) -> float:
        """Return the threshold the counter program compares against, in its own form."""
        if self.stated_form.startswith("last_"):
            return float(self.first_step)
        return self.stated_value

    def record(self) -> dict[str, object]:
        """Return the stated form and the derived step, for a reader of the run."""
        return {
            "form": self.stated_form,
            "stated": self.stated_value,
            "first_step": self.first_step,
            "time_iterations": self.time_iterations,
            "step_deg": self.step_deg,
            "rpm": self.rpm,
        }


def action_export_lines(
    conventions: WorkflowConventions,
    case: SimCase,
    *,
    whole_run: bool = False,
    version: str | FsVersion = "26.120",
) -> list[str]:
    """Return the export lines an ACTION writes: the update prelude, then the verbs.

    ONE IMPLEMENTATION FOR EVERY ACTION THAT EXPORTS, which is why this is
    a function and not a loop inside one of them. Two actions export from
    inside a run, the per-step counter and the wall clock's rescue, and
    they have to write the same thing or the one that fires rarely is the
    one that is wrong. It was: the rescue block was written as its own loop
    and diverged on both halves at once (the V&V lens, 2026-09-13).

    THE NAMES ARE CLAIMED BY `classify_outputs` and never by a bare
    ``endswith``. That function exists for this: longest suffix first, so
    ``_cp.txt`` is claimed by the sections kind before the loads kind can
    see a ``.txt``. A loop that walks :data:`EXPORT_KINDS` in declaration
    order and takes the first name ending with the suffix hands the
    sections file to ``EXPORT_SOLVER_ANALYSIS_SPREADSHEET``: the wrong
    content under the wrong name.

    THE THREE UPDATE COMMANDS COME FIRST whenever a sections,
    sectional-loads or probe export is among them, which is the rule
    :func:`_export_block` follows for the same reason: an export of
    sections nobody updated is an export of the previous state.

    ``whole_run`` KEEPS THE KINDS A PER-STEP ACTION MUST DROP: the
    simulation file, the plots table, the log and, since 0.27.0, the force
    distribution (:data:`END_OF_RUN_EXPORT_KINDS`). A per-step action must
    drop them, because a simulation file written every time step is not a
    per-step export; the wall clock's rescue is the opposite case, the
    LAST thing a stopped run does, and it needs them MOST. Sharing this
    function without the switch cost the rescue every one of them, on a
    row that declares a plots export and a log, which is the rotor row of
    the release's own example workspace. Found by the independent Codex
    review of `main`, 2026-09-13 (GEO-047-C08); the sharing itself was the
    right fix for a real divergence and the switch is what it was missing.
    """
    names = list(conventions.outputs or case.outputs)
    kinds = {
        kind: name
        for kind, name in classify_outputs(names).items()
        if whole_run or kind not in (*WHOLE_RUN_EXPORT_KINDS, *END_OF_RUN_EXPORT_KINDS)
    }
    # FR-417 R7: the per-step exports of a row whose probes are NORMAL update and
    # export them at every step of the window; the wall clock's rescue does not,
    # since the points may not exist when it fires.
    normal = not whole_run and case.pproc is not None and case.pproc.samples_normal_probes()
    if case.recipe in _UNSTEADY_RECIPES and not normal:
        for kind in STEADY_ONLY_EXPORT_KINDS:
            kinds.pop(kind, None)
    # G05: an action fires during the march and a volume section is cut after
    # it; the builders refuse the table on these rows, and this is the second
    # half of that, so an action never exports a section nobody cut.
    for kind in VOLUME_SECTION_KINDS.values():
        kinds.pop(kind, None)
    lines: list[str] = []
    if any(kind in kinds for kind in _UPDATED_KINDS):
        lines += ["UPDATE_ALL_SURFACE_SECTIONS", "COMPUTE_SURFACE_SECTIONAL_LOADS NEWTONS"]
        if "probes" in kinds:  # F01: an unsteady row has no probe points to update
            lines.append("UPDATE_PROBE_POINTS")
    for kind, _, verb, _ in EXPORT_KINDS:
        if kind in kinds:
            payload = Script(version)
            if _surface_export(payload, case, kind, kinds[kind], kinds=kinds):
                # A Tecplot whose VTK the outputs name emits nothing of its own
                # (G45), and an empty payload renders one blank line.
                rendered = payload.render()
                lines += rendered.splitlines() if rendered.strip() else []
            else:
                lines += [verb, kinds[kind]]
    return lines


def _per_step_exports(
    conventions: WorkflowConventions, case: SimCase, *, version: str | FsVersion = "26.120"
) -> str:
    """Return the child script text: the per-step kinds of the row's outputs.

    The names are the row's rendered outputs, the same names the
    end-of-run block exports, and the solver tells the two apart by the
    ``_iteration=N`` it stamps on an action's export (RPT-041 finding 3).
    """
    return "".join(f"{line}\n" for line in action_export_lines(conventions, case, version=version))


def _rotor_clock(case: SimCase) -> TimeStepping:
    """Resolve the rotor run type's clock, off the fastest rotor where the row states several."""
    if case.motions:
        speeds = [rotor_speed(_motion_view(case, record)) for record in case.motions]
        speed = max(speeds, key=lambda each: abs(each.rpm))
    else:
        speed = rotor_speed(case)
    return rotor_time_stepping(case, speed=speed)


def unsteady_export_threshold(
    case: SimCase,
    conventions: WorkflowConventions | None = None,
    *,
    version: str | FsVersion = "26.120",
) -> UnsteadyExportThreshold | None:
    """Resolve the export threshold a row states, or None when it states none.

    Called by the two unsteady builders before their first emission, so a
    refusal leaves the script as it was, and again by the run layer, which
    writes the program from it: it is a function of the case alone, so the
    two calls agree.

    Parameters
    ----------
    case : SimCase
        The case; its variables may carry one of ``EXPORT_UNSTEADY_AFTER_REV``,
        ``EXPORT_UNSTEADY_AFTER_ITER``, ``EXPORT_UNSTEADY_LAST_REV`` or
        ``EXPORT_UNSTEADY_LAST_ITER``.
    conventions : WorkflowConventions, optional
        The rendered output names; defaults to the case's own.
    version : str or FsVersion, optional
        The solver version whose conventions the resolved threshold follows;
        defaults to ``"26.120"``.

    Returns
    -------
    UnsteadyExportThreshold or None
        None when the row states none of the four keys, which is every row
        written before 0.13.0. A last form resolves to the first step
        ``TIME_ITERATIONS - n + 1`` (FR-415).

    Raises
    ------
    CampaignConfigError
        If two keys are stated, naming them; if the row names the steady
        run type, which has no time loop; if the revolutions form is
        stated on the run type that turns nothing, naming the iterations
        form that would work; if the value is not a positive number; or if
        the threshold lies beyond the run, naming both numbers.
    """
    stated = stated_threshold_keys(case)
    averaged = (
        case.pproc.time_averaging is not None
        and case.recipe in _UNSTEADY_RECIPES
        and continuation_of(case) is None
        if case.pproc is not None
        else False
    )
    if not stated and not averaged:
        return None
    if not stated:
        # G25: [time_averaging] EXPORTS THE SURFACE AT EVERY STEP OF ITS WINDOW,
        # through this machinery, as a row stating EXPORT_UNSTEADY_AFTER_ITER at
        # the window's first step would: the post averages those exports.
        window = surface_time_averaging(case)
        assert window is not None
        first = int(window["iterations"][0])
        stepping = (
            _rotor_clock(case)
            if select_workflow(case) == "unsteady_rotor"
            else unsteady_time_stepping(case)
        )
        per_revolution = stepping.steps_per_revolution
        return UnsteadyExportThreshold(
            stated_form="iterations",
            stated_value=float(first),
            first_step=first,
            time_iterations=stepping.time_iterations,
            delta_time_s=stepping.delta_time_s,
            step_deg=None if per_revolution is None else round(360.0 / per_revolution, 9),
            rpm=stepping.rpm,
            exports=_per_step_exports(
                conventions or WorkflowConventions.for_case(case), case, version=version
            ),
        )
    refuse_two_threshold_keys(case, stated)
    key = next(iter(stated))
    workflow = select_workflow(case)
    refuse_threshold_on_a_steady_run(case, key, workflow)
    if workflow == "unsteady_rotor":
        stepping = _rotor_clock(case)
    else:
        stepping = unsteady_time_stepping(case)
    per_revolution = stepping.steps_per_revolution
    form, number, first_step = resolve_first_step(case, key, stepping, workflow)
    if averaged:
        refuse_a_threshold_after_the_averaging_start(case, key, number, first_step)
    return UnsteadyExportThreshold(
        stated_form=form,
        stated_value=float(number),
        first_step=first_step,
        time_iterations=stepping.time_iterations,
        delta_time_s=stepping.delta_time_s,
        # Nine decimals: below what any cell states, so a step of 1200
        # rev/min at 0.0001 s reads 0.72 in the program and not the
        # product's last bit.
        step_deg=None if per_revolution is None else round(360.0 / per_revolution, 9),
        rpm=stepping.rpm,
        exports=_per_step_exports(
            conventions or WorkflowConventions.for_case(case), case, version=version
        ),
    )


#: The program the clock action runs, rendered with this row's deadline.
#:
#: IT KEEPS ITS OWN STATE because the solver hands an action nothing: not
#: the step, not the time, not how far the run has come. The first
#: invocation writes the start; every one after it reads that back and
#: asks one question.
#:
#: WHEN IT FIRES it writes the row's exports and the stop into the script
#: file the solver re-reads on the next step, and records WHERE it stopped
#: so a RESTART has something to subtract from. It fires ONCE: the state
#: carries a flag, because a second firing would append a second copy of
#: every export line.
WALLTIME_CLOCK_TEMPLATE = """\
# Written by pyflightstream for {sim}. The wall clock of this row, watched
# from inside the run, because the solver cannot be asked how long it has
# been going.
import json
import pathlib
import time

HERE = pathlib.Path(__file__).resolve().parent
STATE = HERE / "{state_name}"
TARGET = HERE / "{stop_name}"
DEADLINE_S = {deadline:.3f}
STOP_TEXT = {stop_text!r}

state = {{"started_at": None, "steps": 0, "fired": False}}
if STATE.is_file():
    try:
        state.update(json.loads(STATE.read_text(encoding="utf-8")))
    except ValueError:
        pass

now = time.time()
if state["started_at"] is None:
    state["started_at"] = now
state["steps"] = int(state["steps"]) + 1
elapsed = now - float(state["started_at"])
state["elapsed_s"] = elapsed

if not state["fired"] and elapsed >= DEADLINE_S:
    TARGET.write_text(STOP_TEXT, encoding="utf-8", newline="\\n")
    state["fired"] = True
    state["stopped_at"] = {{"step": state["steps"], "elapsed_s": elapsed}}

STATE.write_text(json.dumps(state, indent=2), encoding="utf-8", newline="\\n")
"""


def walltime_clock_program(
    case: SimCase, conventions: WorkflowConventions, *, version: str | FsVersion = "26.120"
) -> str:
    """Render the clock program for one row, with its deadline baked in.

    THE DEADLINE IS THE ROW'S WALL CLOCK MINUS THE SETUP'S MARGIN, computed
    here rather than in the program, so a reader of the emitted file sees
    the number the run will actually use rather than an expression they
    have to evaluate against two artifacts.
    """
    walltime = row_walltime_s(case)
    if walltime is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the wall clock program was asked for on a row that "
            f"states no {WALLTIME_VARIABLE}."
        )
    margin = walltime_margin_s(case)
    deadline = walltime - margin
    if deadline <= 0:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {WALLTIME_VARIABLE}: {walltime:g} s and a "
            f"margin of {margin:g} s, which leaves {deadline:g} s to run in. The margin "
            "is how long before the clock the run stops to write its exports, so it has "
            "to be shorter than the clock."
        )
    return WALLTIME_CLOCK_TEMPLATE.format(
        sim=case.sim_id,
        state_name=PurePath(WALLTIME_CLOCK_STATE).name,
        stop_name=PurePath(WALLTIME_STOP_SCRIPT).name,
        deadline=deadline,
        stop_text=walltime_stop_text(case, conventions, version=version),
    )


def unsteady_counter_steps(case: SimCase) -> int:
    """Return the time steps an unsteady row's step counter counts to (FR-314).

    The steps the point's script marches: a continuation's owed steps, else
    the clock of its run type, the same clock :func:`unsteady_export_threshold`
    reads. The run layer writes it into the count-only program, where the
    progress bar of a local run reads it (FR-129).

    Parameters
    ----------
    case : SimCase
        The point's case; its run type and its continuation, if any, decide
        the clock that is read.

    Returns
    -------
    int
        The number of physical time steps the point's unsteady script marches.
    """
    continuation = continuation_of(case)
    if continuation is not None:
        return continuation[1]
    if select_workflow(case) == "unsteady_rotor":
        return _rotor_clock(case).time_iterations
    return unsteady_time_stepping(case).time_iterations


def walltime_stop_text(
    case: SimCase, conventions: WorkflowConventions, *, version: str | FsVersion = "26.120"
) -> str:
    """Render what the clock writes into the stop script when it fires.

    The row's own exports, then the stop. The exports are the names the
    conventions already rendered for this point, so nothing here retypes a
    verb or a suffix; the stop is ONE LINE, which is what keeps the probe
    that measures it cheap.
    """
    lines: list[str] = [
        "# Written by the wall-clock action. The run reached its clock and",
        "# these are its outputs as they stand.",
    ]
    # THE SAME LINES THE PER-STEP ACTION WRITES, from the same function.
    # This was its own loop until 2026-09-13 and it had diverged twice
    # over: it omitted the three update commands, so a rescued run's
    # sections, sectional-loads and probe files carried the state BEFORE
    # the stop rather than at it, silently, under a record saying the
    # numbers up to that step are real; and it claimed names by a bare
    # `endswith` in declaration order, so a row declaring a `_cp.txt`
    # before a `.txt` got its sections file exported as the loads
    # spreadsheet. These are the ONLY outputs a stopped run leaves, which
    # is what makes a divergence here cost the whole run's evidence.
    lines += action_export_lines(conventions, case, whole_run=True, version=version)
    lines.append(WALLTIME_STOP_VERB)
    return "\n".join(lines) + "\n"
