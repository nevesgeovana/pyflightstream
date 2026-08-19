"""Workflows: a run TYPE that builds the whole script by itself.

Pipeline role: the builder half of the file-managed modality. A recipe
is a function a USER writes and the loop imports by reference; a
WORKFLOW is a run type this package already knows how to build, named
by the matrix's ``WORKFLOW`` column and resolved by TABLE LOOKUP in
:data:`WORKFLOWS`. That difference is the whole point of the module: a
workflow cannot be supplied from outside, so a study can be run by
somebody who writes no Python at all.

Three properties follow from the table, and each is enforced here
rather than described:

* **Nothing is imported by reference.** There is no ``importlib`` in
  this module and no reference string that reaches one. A name either
  is in the table or is refused against the table's own contents.
* **A case names ONE builder.** A case naming both a workflow and a
  user recipe is refused naming both, and a case naming neither is
  refused naming the types that exist. Two builders is not a merge, it
  is a question nobody answered.
* **A workflow takes the solver BUILD as an input.** It declares the
  commands it always emits and :func:`covered_builds` DERIVES the
  builds it covers from the command database. A build outside that
  range is refused before the first line is emitted, naming the build,
  the range and the commands that forced it. Nothing here is a
  hand-written version list, so a build registered tomorrow joins the
  range the moment its evidence lands.

WHERE THE NUMBERS COME FROM. A workflow reads the case, and a case
converted from a run matrix carries its ``VAR_NAMES_VALUES`` cell as
strings (the matrix reader has no types to give them). So every value
this module takes off a case is converted HERE, with a refusal that
names the case and the KEY, rather than at the command, whose refusal
would name only the command and send the author to the command
reference instead of to the cell they typed.

THE WORKSPACE CONVENTIONS ARRIVE AS DATA. ``workspace`` sits ABOVE
``cases`` in the layer order, so a workflow can never import the naming
template that rendered its output names. :class:`WorkflowConventions`
is what the run layer passes down instead.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from pyflightstream._errors import PyflightstreamError
from pyflightstream.cases import CampaignConfigError, ScriptRecipe, SimCase
from pyflightstream.commands import CommandRegistry
from pyflightstream.script import Script, helpers
from pyflightstream.versions import FsVersion, known_versions, resolve

__all__ = [
    "BLADES_VARIABLE",
    "DELTA_TIME_VARIABLE",
    "MOVING_BOUNDARIES_VARIABLE",
    "ROTOR_AXIS_VARIABLE",
    "ROTOR_ORIGIN_VARIABLE",
    "RPM_VARIABLE",
    "TIME_ITERATIONS_VARIABLE",
    "VELOCITY_VARIABLE",
    "WINDOW_DEGREES_VARIABLE",
    "WINDOW_REVOLUTIONS_VARIABLE",
    "WINDOW_STEPS_VARIABLE",
    "WORKFLOWS",
    "WORKFLOW_KEY",
    "ExportWindow",
    "ReductionPlan",
    "Workflow",
    "WorkflowConventions",
    "WorkflowCoverageError",
    "build_script",
    "covered_builds",
    "emit_rotor_motion",
    "export_window",
    "reduction_plan",
    "require_coverage",
    "resolve_workflow",
    "select_workflow",
    "workflow_names",
    "workflow_registry",
]

#: Case-variable key carrying the matrix ``WORKFLOW`` column.
#:
#: Spelled here rather than imported from
#: :mod:`pyflightstream.cases.matrix`, which is a sibling module with no
#: constant for it: the converter writes the key as a keyword argument
#: (``matrix_workflow=row.workflow``). The reserved ``matrix_`` namespace
#: is written by the converter and never by a user's ``VAR_NAMES_VALUES``
#: cell, so the value cannot be shadowed by case data. When ``SimCase``
#: gains the declared ``workflow`` field, this key becomes a fallback and
#: the field wins.
WORKFLOW_KEY = "matrix_workflow"

#: The workflow name a row written before the ``WORKFLOW`` column asks
#: for: the established matrix behaviour, whose builder is the user's own
#: recipe. It is deliberately NOT in :data:`WORKFLOWS`; it means "no
#: workflow", which is what keeps every matrix written before v0.8.0
#: running exactly as it always ran.
_LEGACY = "LEGACY"

#: Free case variables a workflow reads off the row. Each is a KEY of the
#: matrix ``VAR_NAMES_VALUES`` cell and arrives as a string.
VELOCITY_VARIABLE = "VELOCITY"
RPM_VARIABLE = "RPM"
ROTOR_AXIS_VARIABLE = "ROTOR_AXIS"
ROTOR_ORIGIN_VARIABLE = "ROTOR_ORIGIN"
BLADES_VARIABLE = "BLADES"
MOVING_BOUNDARIES_VARIABLE = "MOVING_BOUNDARIES"
DELTA_TIME_VARIABLE = "DELTA_TIME"
TIME_ITERATIONS_VARIABLE = "TIME_ITERATIONS"
WINDOW_DEGREES_VARIABLE = "WINDOW_DEGREES"
WINDOW_STEPS_VARIABLE = "WINDOW_STEPS"
WINDOW_REVOLUTIONS_VARIABLE = "WINDOW_REVOLUTIONS"


class WorkflowCoverageError(PyflightstreamError, RuntimeError):
    """A workflow was asked for a solver build it does not cover.

    Raised BEFORE the first emission and before any executor is
    constructed, so nothing is spent and no half-built script exists
    (PFS-2025.18). The message names the build received, the builds the
    workflow covers in release order, and the commands whose absence
    forced the range.

    ``RuntimeError`` is the standard-library base rather than
    ``ValueError``, because this refusal is about the ENVIRONMENT the
    script would run in and not about an argument the caller passed:
    every argument may be perfectly well formed and the answer still be
    that this build cannot run this study.

    There is deliberately NO override route. The escape already exists
    one level up, in :meth:`pyflightstream.script.Script.allow_broken`,
    which is a recorded waiver naming a reason; a second, quieter one
    here would be a way past the guard that leaves no record.
    """


# --- the conventions the layer above passes down -----------------------------


@dataclass(frozen=True)
class WorkflowConventions:
    """What the run layer tells a workflow about the workspace.

    ``workspace`` sits ABOVE ``cases``, so a workflow can never reach
    the naming template that rendered these names; they arrive as data
    or they do not arrive at all.

    Attributes
    ----------
    outputs : tuple of str
        Output file names for the point being built, relative to the
        execution directory, already rendered by the workspace. A
        workflow exports these and never a literal, which is what keeps
        two points of one case from overwriting each other.
    animation_folder : str
        Folder, relative to the execution directory, that the unsteady
        animation writes its per-timestep frames into.
    """

    outputs: tuple[str, ...] = ()
    animation_folder: str = "frames"

    @classmethod
    def for_case(cls, case: SimCase) -> WorkflowConventions:
        """Fall back to the names the case itself carries.

        Used when no caller passed conventions in. The campaign loop
        renders :attr:`SimCase.outputs` for the point before the builder
        runs, so this is the same information one layer earlier.
        """
        return cls(outputs=tuple(case.outputs))


# --- the table ----------------------------------------------------------------


@dataclass(frozen=True)
class Workflow:
    """One run type, and everything needed to judge it before it runs.

    Attributes
    ----------
    name : str
        The name a ``WORKFLOW`` cell writes.
    summary : str
        One sentence, in plain language, saying what the type is FOR.
    commands : tuple of str
        Every command the builder ALWAYS emits, whatever the case says.
        This is what :func:`covered_builds` derives coverage from, so a
        command that is only sometimes emitted must NOT be listed:
        listing it would narrow the range for runs that never reach it.
    builder : callable
        ``builder(case, script, conventions) -> None``.
    """

    name: str
    summary: str
    commands: tuple[str, ...]
    builder: Callable[[SimCase, Script, WorkflowConventions], None]


def workflow_names() -> tuple[str, ...]:
    """Return the registered workflow names, sorted."""
    return tuple(sorted(WORKFLOWS))


def resolve_workflow(name: str) -> Workflow:
    """Look one workflow up in the table.

    Parameters
    ----------
    name : str
        The workflow type, as a ``WORKFLOW`` cell writes it.

    Returns
    -------
    Workflow
        The registered workflow.

    Raises
    ------
    CampaignConfigError
        If no workflow of that name is registered. The refusal lists
        what IS registered, because a workflow cannot be supplied from
        outside: an unknown name is always a typo or a version gap, and
        never a module the caller forgot to install.
    """
    try:
        return WORKFLOWS[name]
    except KeyError:
        raise CampaignConfigError(
            f"{name!r} names no registered workflow type. The registered types are "
            f"{', '.join(workflow_names())}. A workflow is looked up in this package's "
            "own table and is never imported by reference, which is what separates it "
            "from a recipe: if you meant a function of your own, write it as a recipe "
            "reference ('package.module:function') and leave the WORKFLOW cell at "
            f"{_LEGACY}."
        ) from None


# --- selection: exactly one builder per case ---------------------------------


def _workflow_cell(case: SimCase) -> str | None:
    """Return the workflow a case names, or None when it names none."""
    declared = getattr(case, "workflow", None)
    if declared is None:
        declared = case.variables.get(WORKFLOW_KEY)
    if declared is None:
        return None
    name = str(declared).strip()
    if not name or name == _LEGACY:
        return None
    return name


def select_workflow(case: SimCase) -> str:
    """Return the workflow a case names, refusing two builders or none.

    Parameters
    ----------
    case : SimCase
        The case, as converted from a matrix row or authored in
        ``campaign.toml``.

    Returns
    -------
    str
        The workflow name; :func:`resolve_workflow` turns it into the
        builder.

    Raises
    ------
    CampaignConfigError
        If the case names BOTH a workflow and a user recipe, printing
        both values so the author can see which to delete; or if it
        names NEITHER, listing the types that exist.
    """
    workflow = _workflow_cell(case)
    recipe = (case.recipe or "").strip()
    # A recipe cell that simply repeats a registered workflow name is the
    # SAME statement said twice (the FS_SCRIPT code mapped to the type),
    # never a second builder, so it is not a conflict.
    recipe_is_a_workflow = recipe in WORKFLOWS
    if workflow and recipe and not recipe_is_a_workflow:
        raise CampaignConfigError(
            f"case {case.sim_id!r} names a workflow AND a recipe: the workflow "
            f"{workflow!r} and the recipe {recipe!r}. One case builds its script one "
            "way. A workflow is this package's own run type and a recipe is a function "
            "you wrote; keeping both would leave which one runs to the order the loop "
            f"happens to check. Delete one: set the WORKFLOW cell to {_LEGACY} to keep "
            "the recipe, or drop the recipe reference to keep the workflow."
        )
    if workflow and recipe_is_a_workflow and recipe != workflow:
        raise CampaignConfigError(
            f"case {case.sim_id!r} names a workflow AND a recipe: the workflow "
            f"{workflow!r} and the recipe {recipe!r}. Both are registered workflow "
            "types and they disagree, so nothing here can tell which run type the "
            "author meant. Make the two agree, or leave only one of them."
        )
    if workflow:
        return workflow
    if recipe_is_a_workflow:
        return recipe
    if not recipe:
        raise CampaignConfigError(
            f"case {case.sim_id!r} names neither a workflow nor a recipe, so nothing "
            "would build its script. Name a run type in the WORKFLOW cell (the "
            f"registered types are {', '.join(workflow_names())}), or point FS_SCRIPT "
            "at a recipe reference of your own."
        )
    raise CampaignConfigError(
        f"case {case.sim_id!r} names the recipe {recipe!r} and no workflow, so this "
        "call has no workflow to build. Use the recipe path, or name a run type in the "
        f"WORKFLOW cell; the registered types are {', '.join(workflow_names())}."
    )


# --- coverage: the build is an input -----------------------------------------


def covered_builds(
    workflow: Workflow, *, registry: CommandRegistry | None = None
) -> tuple[str, ...]:
    """Return the solver builds a workflow covers, DERIVED from the database.

    A build is covered when its command view carries every command the
    workflow always emits. Nothing is declared: a build registered
    tomorrow joins this tuple the moment its evidence lands, and a
    command whose status moves narrows it in the same commit.

    Parameters
    ----------
    workflow : Workflow
        The run type.
    registry : CommandRegistry, optional
        Alternative database, used by tests; defaults to the packaged
        one.

    Returns
    -------
    tuple of str
        Canonical identifiers, in RELEASE order, which is the order of
        ``commands/_meta.yaml`` and the only ordering authority
        (CLAUDE.md invariant 4).
    """
    database = registry or CommandRegistry.load()
    covered = []
    for build in known_versions():
        view = database.for_version(build)
        if all(name in view for name in workflow.commands):
            covered.append(build.canonical)
    return tuple(covered)


def _missing_commands(
    workflow: Workflow, version: FsVersion, registry: CommandRegistry
) -> tuple[str, ...]:
    view = registry.for_version(version)
    return tuple(name for name in workflow.commands if name not in view)


def require_coverage(
    workflow: Workflow,
    version: str | FsVersion,
    *,
    registry: CommandRegistry | None = None,
) -> None:
    """Refuse a build the workflow does not cover, before anything is emitted.

    Parameters
    ----------
    workflow : Workflow
        The run type about to build.
    version : str or FsVersion
        The target FlightStream build.
    registry : CommandRegistry, optional
        Alternative database, used by tests.

    Raises
    ------
    WorkflowCoverageError
        If the build's command database does not carry every command
        the workflow always emits. The message names the build, the
        covered range in release order, and the commands that forced
        it.
    """
    database = registry or CommandRegistry.load()
    target = resolve(version)
    missing = _missing_commands(workflow, target, database)
    if not missing:
        return
    covered = covered_builds(workflow, registry=database)
    view = database.for_version(target)
    # The earlier vocabulary, named only where the build actually has
    # it, so this sentence is a checkable truth on the builds it appears
    # on rather than a general claim.
    earlier = tuple(name for name in _EARLIER_VOCABULARY if name in view)
    note = ""
    if earlier:
        note = (
            f" That build carries {', '.join(earlier)} instead, which is the earlier "
            "vocabulary for the same intent and does not accept the same arguments, so "
            "it is not a substitution this package can make on your behalf."
        )
    covered_text = ", ".join(covered) if covered else "no registered build"
    raise WorkflowCoverageError(
        f"the {workflow.name!r} workflow does not cover FlightStream build "
        f"{target.canonical}. It covers {covered_text}, in release order. "
        f"{target.canonical} is outside that range because its command database carries "
        f"no {', '.join(missing)}.{note} Run this study on a build the workflow covers. "
        "There is no override: emitting a command a build does not carry is not a "
        "decision this package makes for you, and the one recorded way past a command "
        "the database refuses is Script.allow_broken, which names its reason."
    )


#: Commands that do the same job as a rotor workflow's own on the builds
#: that predate its vocabulary. Named in a refusal, never emitted: no
#: registered build documents both this and SET_MOTION_ROTOR_RPM, so a
#: version branch that chose between them would be unreachable code.
_EARLIER_VOCABULARY = ("SET_MOTION_IS_ROTOR",)


# --- reading the row ----------------------------------------------------------


def _variable(case: SimCase, key: str) -> str | None:
    value = case.variables.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_float(case: SimCase, key: str, *, quantity: str, unit: str) -> float:
    """One numeric case variable, refused by CASE and KEY rather than by command."""
    text = _variable(case, key)
    if text is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares no {key}, and the run type it names needs "
            f"the {quantity} in {unit}. Add it to the row's variables as "
            f"'{key}: <value>'."
        )
    try:
        return float(text)
    except ValueError:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {key} as {text!r}, which is not a number. "
            f"It is the {quantity} in {unit}. Matrix variables arrive as text, so the "
            "conversion happens here rather than at the command, where the refusal "
            "would name only the command and not the cell you typed."
        ) from None


def _required_int(case: SimCase, key: str, *, quantity: str, unit: str) -> int:
    value = _required_float(case, key, quantity=quantity, unit=unit)
    if value != int(value):
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {key} as {value!r}, and the {quantity} is a "
            f"count in {unit}, which has no fractional part."
        )
    return int(value)


# --- PFS-2025.05: the rotor motion, off the row ------------------------------


def emit_rotor_motion(
    case: SimCase,
    script: Script,
    *,
    frame: int | str,
    moving_frames: Sequence[int | str] | str | None = "all",
) -> int:
    """Emit one rotary motion entirely from what the row declares.

    Motion, its ``ROTARY`` type, its coordinate system, its rotor axis,
    its rotor speed and its moving boundaries, with nothing hand-written
    between the matrix cell and the command.

    THE ROTOR FLAG, and why there is no version branch here. Measured
    over every registered build: ``SET_MOTION_IS_ROTOR`` is available on
    the four earliest and on none of the later ones, while
    ``SET_MOTION_ROTOR_AXIS`` and ``SET_MOTION_ROTOR_RPM`` are available
    on exactly the complementary set. The two vocabularies are DISJOINT,
    so on every build this step can target the rotor flag IS the
    ``ROTARY`` token of ``CREATE_NEW_MOTION``. The earlier flag command
    is named in :func:`require_coverage`'s refusal, where it is a truth
    a test can exercise, and nowhere else.

    Parameters
    ----------
    case : SimCase
        The case; its variables carry the rotor speed in rev/min
        (``RPM``), the rotor axis within ``frame`` (``ROTOR_AXIS``, one
        of X, Y, Z) and optionally the moving boundaries
        (``MOVING_BOUNDARIES``, comma-separated 1-based indices or
        labels; absent means every boundary).
    script : Script
        Script under construction. Nothing is emitted into it until
        every value has been read and converted, so a refusal leaves it
        exactly as it was.
    frame : int or str
        Local coordinate system of the rotation, by index or by its
        creation label; it must exist earlier in the script.
    moving_frames : sequence, ``"all"`` or None
        Local frames attached to the motion; ``"all"`` is the default.

    Returns
    -------
    int
        Identifier of the created motion, for later citations.

    Raises
    ------
    CampaignConfigError
        If the row declares no rotor speed or no rotor axis, or declares
        one that is not a number. The message names the case (whose
        ``sim_id`` IS the matrix POL) and the KEY.
    """
    rpm = _required_float(case, RPM_VARIABLE, quantity="rotor speed", unit="rev/min")
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
        boundaries = [_boundary(token) for token in declared.split(",") if token.strip()]
        if not boundaries:
            raise CampaignConfigError(
                f"case {case.sim_id!r} declares {MOVING_BOUNDARIES_VARIABLE} as "
                f"{declared!r}, which names no boundary at all. Leave the key out to "
                "move every boundary, or list the ones that move."
            )
    return helpers.rotary_motion(
        script,
        frame=frame,
        axis=axis.upper(),
        rpm=rpm,
        boundaries=boundaries,
        moving_frames=moving_frames,
    )


def _boundary(token: str) -> int | str:
    text = token.strip()
    try:
        return int(text)
    except ValueError:
        return text


# --- PFS-2025.08: the degrees-backwards window --------------------------------


@dataclass(frozen=True)
class ExportWindow:
    """The span the expensive exports apply over, counted backwards.

    The window is stated ONCE, in whichever unit the author thinks in,
    and every other form is derived. The record carries both, so a later
    reader can see which was written and which was computed.

    Attributes
    ----------
    stated_form : str
        ``degrees``, ``steps`` or ``revolutions``: the form the author
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

    @property
    def steps_per_revolution(self) -> float | None:
        """Solver steps in one revolution, or None without the inputs.

        One revolution lasts ``60 / rpm`` seconds and one step lasts
        ``delta_time_s`` seconds, so a revolution is
        ``60 / (rpm * delta_time_s)`` steps.
        """
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
            ``form`` and ``stated`` are what the author wrote; ``steps``,
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

        Reads ``WINDOW_DEGREES``, ``WINDOW_STEPS`` or
        ``WINDOW_REVOLUTIONS`` (exactly one), plus ``RPM``,
        ``DELTA_TIME`` and ``TIME_ITERATIONS``.
        """
        degrees = revolutions = None
        steps = None
        if _variable(case, WINDOW_DEGREES_VARIABLE) is not None:
            degrees = _required_float(
                case, WINDOW_DEGREES_VARIABLE, quantity="export window", unit="degrees"
            )
        if _variable(case, WINDOW_REVOLUTIONS_VARIABLE) is not None:
            revolutions = _required_float(
                case, WINDOW_REVOLUTIONS_VARIABLE, quantity="export window", unit="revolutions"
            )
        if _variable(case, WINDOW_STEPS_VARIABLE) is not None:
            steps = _required_int(
                case, WINDOW_STEPS_VARIABLE, quantity="export window", unit="solver steps"
            )
        rpm = (
            None
            if _variable(case, RPM_VARIABLE) is None
            else _required_float(case, RPM_VARIABLE, quantity="rotor speed", unit="rev/min")
        )
        delta_time_s = (
            None
            if _variable(case, DELTA_TIME_VARIABLE) is None
            else _required_float(
                case, DELTA_TIME_VARIABLE, quantity="solver physical time step", unit="s"
            )
        )
        return export_window(
            degrees=degrees,
            steps=steps,
            revolutions=revolutions,
            rpm=rpm,
            delta_time_s=delta_time_s,
            time_iterations=_required_int(
                case, TIME_ITERATIONS_VARIABLE, quantity="physical time step count", unit="steps"
            ),
        )


def export_window(
    *,
    degrees: float | None = None,
    steps: int | None = None,
    revolutions: float | None = None,
    rpm: float | None = None,
    delta_time_s: float | None = None,
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

    Returns
    -------
    ExportWindow

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
    blades = _required_int(case, BLADES_VARIABLE, quantity="blade count", unit="blades")
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


# --- the builders -------------------------------------------------------------


def _velocity(case: SimCase) -> float:
    if case.velocity is not None:
        return float(case.velocity)
    return _required_float(case, VELOCITY_VARIABLE, quantity="free-stream velocity", unit="m/s")


def _output(conventions: WorkflowConventions, case: SimCase, index: int) -> str:
    names = conventions.outputs or tuple(case.outputs)
    if len(names) <= index:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {len(names)} output file(s) and this run "
            f"type exports at least {index + 1}. A workflow exports the names the "
            "workspace rendered for this point and never a literal, so the row has to "
            "declare them: add them to the row's variables as "
            "'OUTPUTS: loads_{point}.txt'."
        )
    return names[index]


def _settings(case: SimCase, script: Script) -> None:
    helpers.solver_settings(
        script,
        aoa=case.point.get("alpha", 0.0),
        sideslip=case.point.get("beta"),
        velocity=_velocity(case),
        iterations=case.solver.iterations,
        convergence=case.solver.convergence,
        max_threads=case.solver.max_threads,
    )


def _build_steady(case: SimCase, script: Script, conventions: WorkflowConventions) -> None:
    """Build a steady polar point: free stream, settings, solve, export."""
    helpers.free_stream(script)
    _settings(case, script)
    helpers.initialize_solver(script)
    helpers.start_solver(script)
    script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", _output(conventions, case, 0))
    script.emit("CLOSE_FLIGHTSTREAM")


def _build_unsteady_rotor(case: SimCase, script: Script, conventions: WorkflowConventions) -> None:
    """Build a blade-resolved rotor run: rotor frame, motion, time loop."""
    origin = _origin(case)
    helpers.coordinate_frame(
        script,
        name=f"rotor_{case.sim_id}",
        origin=origin,
        x_axis=(1.0, 0.0, 0.0),
        y_axis=(0.0, 1.0, 0.0),
        label="rotor",
    )
    helpers.free_stream(script)
    emit_rotor_motion(case, script, frame="rotor")
    window = ExportWindow.from_case(case)
    helpers.unsteady_solver(
        script,
        time_iterations=window.time_iterations,
        delta_time=float(window.delta_time_s or 0.0),
    )
    _settings(case, script)
    helpers.initialize_solver(script)
    helpers.start_solver(script)
    script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", _output(conventions, case, 0))
    script.emit("CLOSE_FLIGHTSTREAM")


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
    return (x, y, z)


#: The registered run types. A TABLE, deliberately: a workflow is looked
#: up here and never imported, which is what a user cannot supply.
WORKFLOWS: Mapping[str, Workflow] = {
    "steady": Workflow(
        name="steady",
        summary=(
            "One steady point of a polar: a uniform free stream, the solver settings the "
            "row and its input library resolved to, one solve, one loads export."
        ),
        commands=(
            "SET_FREESTREAM",
            "SOLVER_SET_AOA",
            "SOLVER_SET_VELOCITY",
            "SOLVER_SET_ITERATIONS",
            "SOLVER_SET_CONVERGENCE",
            "INITIALIZE_SOLVER",
            "START_SOLVER",
            "EXPORT_SOLVER_ANALYSIS_SPREADSHEET",
            "CLOSE_FLIGHTSTREAM",
        ),
        builder=_build_steady,
    ),
    "unsteady_rotor": Workflow(
        name="unsteady_rotor",
        summary=(
            "A blade-resolved rotor run: a rotor coordinate system, one rotary motion "
            "turning at the row's RPM about the row's axis, and a physical time loop."
        ),
        commands=(
            "CREATE_NEW_COORDINATE_SYSTEM",
            "EDIT_COORDINATE_SYSTEM",
            "SET_FREESTREAM",
            "CREATE_NEW_MOTION",
            "SET_MOTION_BOUNDARIES",
            "SET_MOTION_MOVING_FRAMES",
            "SET_MOTION_COORDINATE_SYSTEM",
            "SET_MOTION_ROTOR_AXIS",
            "SET_MOTION_ROTOR_RPM",
            "SET_SOLVER_UNSTEADY",
            "SOLVER_SET_AOA",
            "SOLVER_SET_VELOCITY",
            "SOLVER_SET_ITERATIONS",
            "SOLVER_SET_CONVERGENCE",
            "INITIALIZE_SOLVER",
            "START_SOLVER",
            "EXPORT_SOLVER_ANALYSIS_SPREADSHEET",
            "CLOSE_FLIGHTSTREAM",
        ),
        builder=_build_unsteady_rotor,
    ),
}


def build_script(
    case: SimCase,
    script: Script,
    *,
    conventions: WorkflowConventions | None = None,
    registry: CommandRegistry | None = None,
) -> None:
    """Build one case's whole script from the run type it names.

    In order: select the workflow (refusing two builders or none), check
    that the script's build is covered (refusing BEFORE the first
    emission), then build.

    Parameters
    ----------
    case : SimCase
        The case, with its sweep point already filled by the campaign
        loop.
    script : Script
        An empty script bound to the campaign's FlightStream build.
    conventions : WorkflowConventions, optional
        What the run layer says about the workspace; defaults to the
        names the case carries.
    registry : CommandRegistry, optional
        Alternative command database, used by tests.

    Raises
    ------
    CampaignConfigError
        If the case names two builders or none, or if a value the run
        type needs is absent or unparsable.
    WorkflowCoverageError
        If the script's build is outside the workflow's derived
        coverage.

    Examples
    --------
    >>> from pyflightstream.cases import SimCase, SweepAxis
    >>> from pyflightstream.script import Script
    >>> case = SimCase(
    ...     sim_id="7002",
    ...     aircraft="RotorRig",
    ...     sweep=SweepAxis(type="alpha", values=[0.0]),
    ...     recipe="steady",
    ...     outputs=["loads_a+00.0.txt"],
    ...     variables={"VELOCITY": "30.0"},
    ...     point={"alpha": 0.0},
    ... )
    >>> script = Script("26.120")
    >>> build_script(case, script)
    >>> script.render().splitlines()[0]
    'SET_FREESTREAM CONSTANT'
    """
    workflow = resolve_workflow(select_workflow(case))
    require_coverage(workflow, script.version, registry=registry)
    workflow.builder(case, script, conventions or WorkflowConventions.for_case(case))


def workflow_registry(*, conventions: WorkflowConventions | None = None) -> dict[str, ScriptRecipe]:
    """Return the workflows as a recipe registry the campaign loop can take.

    This is the seam that makes a workflow reachable with NO user
    function: hand it to ``run_matrix(recipe_registry=...)`` and a row
    whose ``FS_SCRIPT`` code maps to a workflow NAME builds through the
    table instead of through an import.

    Parameters
    ----------
    conventions : WorkflowConventions, optional
        Passed down to every builder; the run layer owns these, since
        ``workspace`` sits above ``cases``.

    Returns
    -------
    dict of str to callable
        ``{name: build(case, script) -> None}``, satisfying
        :class:`pyflightstream.cases.ScriptRecipe`.
    """

    def _bind(name: str) -> ScriptRecipe:
        def build(case: SimCase, script: Script) -> None:
            # Selected again rather than assumed: the registry entry says
            # which name the loop LOOKED UP, and the case is what says
            # whether that name conflicts with a recipe of its own.
            build_script(case, script, conventions=conventions)

        build.__name__ = f"workflow_{name}"
        build.__doc__ = WORKFLOWS[name].summary
        return build

    return {name: _bind(name) for name in WORKFLOWS}
