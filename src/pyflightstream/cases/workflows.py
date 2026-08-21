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

AND SO DOES THE GEOMETRY, for the same reason and by a different route.
A workflow never resolves an input-library id: by the time a builder
runs, :attr:`pyflightstream.cases.SimCase.geometry` already holds the
STAGED path of the case's own copy, put there by the campaign loop
after it hashed those bytes into the record. What the builder does with
it is open it, first, before anything else
(:func:`_open_geometry`).

Two of the three things this module reads off a row arrived at 0.8.1
and both were absent rather than wrong. A case carrying a geometry
rendered a script byte-identical to the same case without one, so
nothing opened the mesh; and every workflow initialized under
``SYMMETRY NONE`` with no cell able to say otherwise, so a periodic
rotor sector was solved as a one-bladed rotor that converged and
exported (PFS-2025.02.02, PFS-2025.02.03).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePath

from pyflightstream._errors import PyflightstreamError
from pyflightstream.cases import CampaignConfigError, ScriptRecipe, SimCase
from pyflightstream.commands import CommandRegistry
from pyflightstream.script import CommandArgumentError, Script, helpers
from pyflightstream.versions import FsVersion, known_versions, resolve

__all__ = [
    "BLADES_VARIABLE",
    "DELTA_TIME_VARIABLE",
    "GEOMETRY_VARIABLE",
    "MOVING_BOUNDARIES_VARIABLE",
    "PERIODIC_COPIES_VARIABLE",
    "ROTOR_AXIS_VARIABLE",
    "ROTOR_ORIGIN_VARIABLE",
    "ROTOR_SHEDDING_VARIABLE",
    "RPM_VARIABLE",
    "SIMULATION_SUFFIX",
    "SYMMETRY_VARIABLE",
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
    "accepted_symmetry",
    "build_script",
    "covered_builds",
    "emit_rotor_motion",
    "export_window",
    "reduction_plan",
    "require_coverage",
    "resolve_workflow",
    "rotor_relaxed_trailing_edges",
    "rotor_shedding_direction",
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

#: The geometry a row names, as a library id: the STEM of a file staged
#: under ``inputs/geometries/``, never a path and never a file name.
#:
#: Defined HERE, beside the other cell keys, and re-exported from
#: :mod:`pyflightstream.workspace.matrix`, which is where the resolver
#: that reads the cell lives and where the published import path stays.
#: It was defined THERE until 0.8.1 and the move is not tidying: a cell
#: key that a refusal in this module cannot name is a refusal that has to
#: describe the value some other way, and this one described an internal
#: staged path, so the author read back a string they had never typed.
#: Free because the name is new in this release and had no published
#: contract to keep.
GEOMETRY_VARIABLE = "GEOMETRY"

#: Free case variables a workflow reads off the row. Each is a KEY of the
#: matrix ``VAR_NAMES_VALUES`` cell and arrives as a string.
VELOCITY_VARIABLE = "VELOCITY"
RPM_VARIABLE = "RPM"
ROTOR_AXIS_VARIABLE = "ROTOR_AXIS"
ROTOR_ORIGIN_VARIABLE = "ROTOR_ORIGIN"
#: The direction a rotor case's relaxed trailing edges shed their wake:
#: AXIAL (0) or AZIMUTH (1), the second being what 26.123 adds and what a
#: rotor case wants (SRC-751 p.85). Absent means the row asks for nothing
#: and every specification stays exactly as it was written.
ROTOR_SHEDDING_VARIABLE = "ROTOR_SHEDDING"
BLADES_VARIABLE = "BLADES"
MOVING_BOUNDARIES_VARIABLE = "MOVING_BOUNDARIES"
DELTA_TIME_VARIABLE = "DELTA_TIME"
TIME_ITERATIONS_VARIABLE = "TIME_ITERATIONS"
WINDOW_DEGREES_VARIABLE = "WINDOW_DEGREES"
WINDOW_STEPS_VARIABLE = "WINDOW_STEPS"
WINDOW_REVOLUTIONS_VARIABLE = "WINDOW_REVOLUTIONS"

#: The solver symmetry the case is initialized under: ``NONE``,
#: ``MIRROR`` or ``PERIODIC``, and the accepted set is READ FROM THE
#: COMMAND DATABASE per build rather than restated here
#: (:func:`accepted_symmetry`). Absent means the row asks for nothing and
#: ``NONE`` is emitted, which is what every workflow emitted before
#: 0.8.1 and the only thing any of them could emit.
#:
#: ``MIRROR`` CARRIES A CAUTION THIS KEY CANNOT ENFORCE: initializing a
#: mirrored solution with the FULL model loaded diverges immediately,
#: because the model is then its own mirror image (SRC-003 p.217). The
#: mode describes what was MESHED, so a row declaring it must have
#: staged the half. Nothing here can check that, which is why it is
#: written where the mode is chosen rather than only in the helper.
#:
#: THIS KEY IS WHY 0.8.1 IS A DEFECT RELEASE AND NOT A FEATURE ONE. A
#: periodic sector solved under ``SYMMETRY NONE`` is not a failed run: it
#: is a ONE-BLADED ROTOR that converges, exports, and reports thrust and
#: torque a reader has no way to tell from the sector's. Two of the three
#: rows of the study this was measured on are periodic sectors, and
#: until this key existed no matrix cell could say so (PFS-2025.02.03).
SYMMETRY_VARIABLE = "SYMMETRY"

#: How many periodic copies the sector stands for, dimensionless count.
#: Required with ``SYMMETRY: PERIODIC`` and forbidden otherwise, which is
#: the command's own rule (SRC-003 p.337) and is enforced by
#: :func:`pyflightstream.script.helpers.initialize_solver`; a
#: four-bladed rotor modelled as one 90 degree sector declares 4.
PERIODIC_COPIES_VARIABLE = "PERIODIC_COPIES"

#: The only suffix a workflow opens, and it is a DELIBERATE narrowing
#: rather than an oversight (PFS-2025.02.02).
#:
#: A ``.fsm`` is a saved SIMULATION: its units, its mesh and its
#: boundary names are already established, so ``OPEN`` needs the path
#: and nothing else. A raw mesh is not, and importing one takes the
#: units as an argument the row would have to declare. A mesh import
#: that silently defaults its units is precisely the class of
#: silent-wrong-answer this release exists to remove, so the suffix is
#: REFUSED and the refusal names the route the user already has:
#: ``docs/mesh-inputs.md`` documents the supported pattern as GUI once,
#: save as ``.fsm``, script everything after.
SIMULATION_SUFFIX = ".fsm"


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
        labels; absent means every boundary). It may also declare the
        direction its relaxed trailing edges shed their wake in
        (``ROTOR_SHEDDING``); see :func:`rotor_shedding_direction` for
        why this function READS that key and emits nothing for it.
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
        If the row declares no rotor speed or no rotor axis, declares
        one that is not a number, or declares a ``ROTOR_SHEDDING``
        direction that is neither of the two. The message names the case
        (whose ``sim_id`` IS the matrix POL) and the KEY.
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
    # READ AND NOT EMITTED, deliberately: the shedding direction is a
    # component-file field and no command carries it, so this call cannot
    # act on it. It is read HERE because this is the function a rotor row
    # goes through, and a row declaring ROTOR_SHEDDING: diagonal that
    # built a perfectly good script would be told nothing at all. The
    # refusal lands before the first emission, like every other read
    # above it.
    rotor_shedding_direction(case)
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


# --- PFS-2026.06: the azimuthal shedding option, off the same row -------------


def rotor_shedding_direction(case: SimCase) -> str | None:
    """Return the relaxed-wake shedding direction this rotor row asks for.

    The direction is a field of the relaxed trailing-edge COMPONENT
    specification and not a scripting argument (SRC-751 p.85), so no
    workflow emits it. What a row CAN do is state it, and this is where
    that statement is read and checked; :func:`rotor_relaxed_trailing_edges`
    is where it is applied to the specifications a component definition
    carries.

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
        leaves a four-field specification at four fields, while a row
        asking for the axial direction states it on every specification
        that already states one.

    Raises
    ------
    CampaignConfigError
        If the row declares a direction that is neither. The message
        names the case, the KEY, the value written and both accepted
        directions, on this module's own rule that a matrix value is
        refused by the cell the author typed rather than by the
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

    THIS IS THE ROUTE TO THE AZIMUTHAL OPTION from a rotor case: a row
    writes ``ROTOR_SHEDDING: AZIMUTH`` and the specifications its
    component definition carries come back with the fifth field set. The
    library writes no component file, so the rendered text is returned
    for the caller to write where their geometry keeps it.

    Parameters
    ----------
    case : SimCase
        The case, whose ``ROTOR_SHEDDING`` variable carries the
        direction; see :func:`rotor_shedding_direction`.
    specifications : sequence of str
        The relaxed trailing-edge specifications as the component
        definition carries them, four fields or five.

    Returns
    -------
    list of str
        One rendered specification per input, in the same order. A
        four-field specification comes back with four fields where the
        row asks for nothing or for the axial direction, because those
        are what it already means; it gains the fifth field only where
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
    >>> rotor_relaxed_trailing_edges(case, ["0.5;0.1;0.9;1"])
    ['0.5;0.1;0.9;1;1']
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


# --- PFS-2025.02.02: the case geometry, opened first --------------------------


def _open_geometry(case: SimCase, script: Script) -> None:
    """Open the case's geometry, before anything else is emitted.

    THE BUG THIS CLOSES, stated once because it is the whole reason for
    the 0.8.1 patch. A case carrying a geometry and the same case with
    the geometry absent rendered BYTE-IDENTICAL scripts: no ``OPEN``, no
    ``NEW_SIMULATION``, no import of any kind. The run layer had already
    staged the file and hashed it into the record, so the manifest named
    a mesh the script never opened, and the solver solved whatever it
    happened to have in memory.

    Emitted FIRST, and not merely early: ``OPEN`` replaces the whole
    simulation state, so a coordinate system, a motion or a solver
    setting written before it would be discarded by it without a word.
    The script layer's phase order agrees (``geometry`` is the first
    phase), so a later ``OPEN`` would also be refused, but the ordering
    here is the reason rather than the consequence.

    The path opened is :attr:`pyflightstream.cases.SimCase.geometry` as
    the case carries it AT BUILD TIME, which the campaign loop has
    already rewritten to the case's own staged copy
    (:func:`pyflightstream.run.run_campaign`, which owns the staging).
    That is deliberate and
    load-bearing: ``inputs_sha256`` in the run record is the hash of the
    STAGED bytes, so opening the library original instead would break
    the pairing between the digest a record publishes and the bytes the
    solver actually read, and would break it silently.

    Parameters
    ----------
    case : SimCase
        The case; its ``geometry`` is the simulation file to open, or
        None for a case that names none.
    script : Script
        Script under construction, still empty. Nothing is emitted
        until the suffix has been judged, so a refusal leaves it exactly
        as it was.

    Raises
    ------
    CampaignConfigError
        If the geometry's suffix is not :data:`SIMULATION_SUFFIX`. The
        message names the suffix written and the documented route,
        because there IS one and it is not this function.
    """
    if case.geometry is None:
        return
    suffix = PurePath(case.geometry).suffix
    if suffix.lower() != SIMULATION_SUFFIX:
        # REFUSED RATHER THAN IMPORTED, and the narrowing is a scope
        # decision of the patch release rather than a gap. IMPORT's FIRST
        # argument is the length units of the mesh file (SRC-003 p.307),
        # which no matrix cell declares today; a mesh imported under
        # defaulted units solves, exports and reports coefficients
        # normalized against a body of the wrong size, which is exactly
        # the silent-wrong-answer class this release exists to remove.
        # Widening this to IMPORT is a UNITS key on the row first, and a
        # units key is a new promise rather than a defect fix.
        #
        # The refusal points at a route the user already has:
        # docs/mesh-inputs.md documents the supported pattern as GUI
        # once, save as .fsm, script everything after.
        written = suffix or "no suffix at all"
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {GEOMETRY_VARIABLE} as a file carrying "
            f"{written}, and a workflow opens a saved simulation ({SIMULATION_SUFFIX}) "
            "and nothing else. A .fsm already carries its own length units, its mesh "
            "and its boundary names, so opening it needs the path alone; importing a "
            "raw mesh takes the length UNITS of the file as an argument, and no matrix "
            "cell declares them, so this package would have to default them and a "
            "defaulted unit is a body of the wrong size reported without a word. Open "
            "the mesh in the FlightStream window once, save the result as a .fsm, and "
            "stage that in inputs/geometries/ instead; docs/mesh-inputs.md carries the "
            "route in full, under 'A workflow opens route 1 only'. The file this case "
            f"resolved to is {case.geometry!r}."
        )
    script.emit("OPEN", case.geometry)


# --- PFS-2025.02.03: the solver initialization, off the same row --------------


def accepted_symmetry(script: Script) -> tuple[str, ...] | None:
    """Return the symmetry modes one build's INITIALIZE_SOLVER accepts.

    READ FROM THE COMMAND DATABASE, per build, and never a literal list
    kept here. The modes are a per-version fact of the command's own
    grammar, so a list in this module would be a second declaration of
    a vocabulary this package already stores with its evidence, free to
    drift the moment a build states a different set.

    The database is reached through :attr:`Script.registry`, which is
    public for exactly this reason: everything recording a per-version
    fact ABOUT a script has to ask the same database the script itself
    validates against.

    Parameters
    ----------
    script : Script
        The script under construction, bound to one build.

    Returns
    -------
    tuple of str or None
        The accepted tokens, in the order the database declares them.
        ``None`` where that build's ``INITIALIZE_SOLVER`` declares no
        argument called ``symmetry`` at all, which is a real case and
        not a failure: FlightStream 25.000 spells it ``SYMMETRY_TYPE``
        with its own token set (SRC-749 p.298). ``None`` is what sends a
        row on to
        :func:`pyflightstream.script.helpers.initialize_solver`, whose
        refusal already names that edition and its remedy.

        ``None`` RATHER THAN AN EMPTY TUPLE, and the distinction is the
        caller's rather than this function's. An empty tuple would be
        the honest answer to a different question, an enumeration that
        declares no tokens, and today no build asks it; sharing one
        value between "this build does not express symmetry" and "this
        build accepts nothing" makes the docstring true only by a
        property of the database that nothing asserts. It also reads
        wrongly at a call site: ``accepted_symmetry(script) == ()``
        says "no mode is accepted", which is the inverse of what the
        empty tuple used to mean here.

    Raises
    ------
    pyflightstream.commands.CommandNotInVersionError
        When the build's command view carries no ``INITIALIZE_SOLVER``
        at all. Unreachable from the builders, which call
        :func:`require_coverage` first, and reachable by a caller
        passing a :class:`~pyflightstream.script.Script` bound to a
        build that only the registry knows.
    """
    entry = script.registry.for_version(script.version)["INITIALIZE_SOLVER"]
    for argument in entry.args:
        if argument.name == "symmetry":
            return tuple(argument.values or ())
    return None


def _initialize(case: SimCase, script: Script) -> None:
    """Initialize the solver under the symmetry the ROW declares.

    WHY THIS IS FATAL AND NOT COSMETIC. A rotor sector is a slice of a
    disc: one blade of four, modelled once and stood in for the other
    three by PERIODIC symmetry with three more copies. Solve that same
    sector under ``SYMMETRY NONE`` and the solver does not fail, does
    not warn and does not diverge. It solves a ONE-BLADED ROTOR. It
    converges, it exports, and it reports a thrust and a torque a reader
    cannot tell from the sector's own. Two of the three rows of the
    study that measured this defect are periodic sectors, and the
    builders called
    :func:`pyflightstream.script.helpers.initialize_solver` with no
    arguments at all, so every one of them emitted ``SYMMETRY NONE``
    with no cell anywhere able to say otherwise. That silence IS the
    defect (PFS-2025.02.03).

    The values come off the ROW and nowhere else, which is this
    module's own doctrine, and they are converted HERE so a refusal
    names the case and the KEY the author typed rather than the command.

    Parameters
    ----------
    case : SimCase
        The case; ``SYMMETRY`` in its variables carries the mode
        (:data:`SYMMETRY_VARIABLE`) and ``PERIODIC_COPIES`` the
        dimensionless copy count (:data:`PERIODIC_COPIES_VARIABLE`). A
        row declaring NEITHER emits ``SYMMETRY NONE`` and no copy count,
        which is exactly what every workflow emitted before 0.8.1.
    script : Script
        Script under construction.

    Raises
    ------
    CampaignConfigError
        If the row declares a symmetry outside the set this build's
        command database declares (the message names the value and the
        accepted modes); if ``PERIODIC_COPIES`` is not a whole positive
        count; or if the pairing rule of the command is broken, which is
        ``PERIODIC`` requiring a copy count and every other mode
        forbidding one (SRC-003 p.337).

    Notes
    -----
    A ROW THAT DECLARES NEITHER KEY REACHES THE HELPER UNTOUCHED, and
    the call is deliberately not wrapped in a ``try``. Every refusal
    this function owns is decided BEFORE the helper runs, so a build
    whose ``INITIALIZE_SOLVER`` this helper cannot express at all
    (FlightStream 25.000, SRC-749 p.298) still raises the helper's own
    message, naming that edition and the ``script.emit`` route out of
    it. Wrapping the call instead re-labelled that refusal as a
    symmetry problem on a row that had said nothing about symmetry,
    which is a worse message than the one it replaced; it was measured
    on 25.000 before this shape was chosen.
    """
    symmetry = _variable(case, SYMMETRY_VARIABLE)
    copies = None
    if _variable(case, PERIODIC_COPIES_VARIABLE) is not None:
        copies = _required_int(
            case, PERIODIC_COPIES_VARIABLE, quantity="periodic copy count", unit="copies"
        )
        if copies < 1:
            raise CampaignConfigError(
                f"case {case.sim_id!r} declares {PERIODIC_COPIES_VARIABLE} as {copies}, "
                "and a periodic sector stands for a whole positive number of copies of "
                "itself: a four-bladed rotor modelled as one 90 degree sector declares "
                "4. Fewer than one copy is not a sector."
            )
    # NONE is the mode of a row that asks for nothing, and it is the mode
    # every workflow emitted before 0.8.1 because nothing could ask.
    mode = "NONE" if symmetry is None else symmetry.upper()
    if symmetry is not None:
        accepted = accepted_symmetry(script)
        # TWO FALSY ANSWERS, BOTH MEANING "THIS BUILD CANNOT JUDGE A
        # MODE", and they are deliberately treated alike here while the
        # return value keeps them apart for callers who need to tell.
        # ``None`` is the argument absent, which is 25.000 spelling it
        # SYMMETRY_TYPE. ``()`` is the argument present and NOT an
        # enumeration, because a non-enum argument carries ``values =
        # None`` in the command database and this reads it as an empty
        # tuple. Refusing a token against an empty list would reject
        # every mode on such a build while claiming it accepts none,
        # which is the inverse of the truth.
        #
        # So the row falls through to the command's own validation, which
        # is the only thing that knows that build's grammar. Written as
        # ``accepted is not None`` for one round of this review, which
        # broke exactly the second case; the mutation that restored the
        # truthiness test survived, and chasing why is what found it.
        if accepted and mode not in accepted:
            raise CampaignConfigError(
                f"case {case.sim_id!r} declares {SYMMETRY_VARIABLE} as {symmetry!r}, and "
                f"FlightStream {script.version.canonical} initializes under "
                f"{', '.join(accepted)}. The accepted modes are read from this build's "
                "own command database rather than from a list kept beside the workflow, "
                "so they are the modes this build documents. The mode is not a "
                "presentation choice: a periodic sector initialized under NONE is solved "
                "as though the rest of the disc were not there, and that run completes "
                "and exports numbers for a rotor with one blade."
            )
    # THE PAIRING IS DECIDED HERE rather than caught from the helper,
    # because the helper's refusal names the command and the manual page
    # and not the two CELLS the author typed, which is this module's own
    # rule about where a matrix value is refused. The rule itself is the
    # command's: PERIODIC appends the number of copies (SRC-003 p.337).
    if mode == "PERIODIC" and copies is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {SYMMETRY_VARIABLE} as {symmetry!r} and no "
            f"{PERIODIC_COPIES_VARIABLE}. A periodic sector is a slice that stands for "
            "a whole number of copies of itself, and the solver cannot know how many "
            "the slice you meshed represents: a four-bladed rotor modelled as one 90 "
            f"degree sector declares '{PERIODIC_COPIES_VARIABLE}: 4'. Add it to the "
            "row's variables."
        )
    if mode != "PERIODIC" and copies is not None:
        # A row declaring the count and NO symmetry at all is the likely
        # shape of this mistake, so it is spelled out rather than
        # reported as "SYMMETRY as None", which names a value the author
        # never typed.
        stated = (
            f"{SYMMETRY_VARIABLE} as {symmetry!r}"
            if symmetry is not None
            else f"no {SYMMETRY_VARIABLE} at all, which initializes under {mode}"
        )
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {PERIODIC_COPIES_VARIABLE} as {copies} and "
            f"{stated}, and a copy count means nothing outside a periodic sector: only "
            f"PERIODIC repeats the modelled slice around the axis. Set "
            f"'{SYMMETRY_VARIABLE}: PERIODIC' if the geometry really is a sector, or "
            f"drop {PERIODIC_COPIES_VARIABLE}."
        )
    helpers.initialize_solver(script, symmetry=mode, periodic_copies=copies)


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
    """Build a steady polar point: open, free stream, settings, solve, export.

    The open is FIRST and only where the case names a geometry
    (:func:`_open_geometry`), so a case that names none emits exactly
    the lines this workflow emitted before 0.8.1.
    """
    _open_geometry(case, script)
    helpers.free_stream(script)
    _settings(case, script)
    _initialize(case, script)
    helpers.start_solver(script)
    script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", _output(conventions, case, 0))
    script.emit("CLOSE_FLIGHTSTREAM")


def _build_unsteady_rotor(case: SimCase, script: Script, conventions: WorkflowConventions) -> None:
    """Build a blade-resolved rotor run: open, rotor frame, motion, time loop.

    The open is FIRST and only where the case names a geometry
    (:func:`_open_geometry`). It has to precede the coordinate system
    rather than merely appear somewhere: ``OPEN`` replaces the whole
    simulation state, so a frame created before it would be discarded
    with nothing said, and the rotary motion would then turn about a
    frame that no longer exists.
    """
    _open_geometry(case, script)
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
    _initialize(case, script)
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
#:
#: ``OPEN`` IS DELIBERATELY ABSENT FROM EVERY ``commands`` TUPLE BELOW,
#: and this note is here so the absence is not read as an oversight and
#: quietly "fixed". Both builders emit it since 0.8.1, but only for a
#: case that names a geometry, and :class:`Workflow` states the rule
#: this follows: a command that is only SOMETIMES emitted must not be
#: listed, because :func:`covered_builds` derives coverage from this
#: tuple and listing it would narrow the range for runs that never
#: reach it. Nothing is lost by leaving it out today either: ``OPEN``
#: is documented or verified on all nine registered builds, so it
#: narrows nothing on any of them, and a build that ever lacked it
#: would refuse the emission at the line itself rather than silently
#: omitting it.
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
