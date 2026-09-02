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

import math
import re
import warnings
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePath

from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning
from pyflightstream._fsm import (
    MeshReadError,
    boundary_labels,
    boundary_names,
    resolve_family,
)
from pyflightstream.cases import CampaignConfigError, ScriptRecipe, SimCase
from pyflightstream.commands import CommandRegistry
from pyflightstream.script import CommandArgumentError, Script, helpers
from pyflightstream.versions import FsVersion, known_versions, resolve

__all__ = [
    "ADVANCE_RATIO_VARIABLE",
    "BLADES_VARIABLE",
    "DELTA_THETA_VARIABLE",
    "DELTA_TIME_VARIABLE",
    "GEOMETRY_VARIABLE",
    "LOG_OUTPUT_VARIABLE",
    "MOVING_BOUNDARIES_VARIABLE",
    "PERIODIC_COPIES_VARIABLE",
    "REVOLUTIONS_VARIABLE",
    "ROTORLESS_REFUSED_KEYS",
    "ROTOR_AXIS_VARIABLE",
    "ROTOR_ORIGIN_VARIABLE",
    "ROTOR_SHEDDING_VARIABLE",
    "RPM_SIGN_VARIABLE",
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
    "RotorSpeed",
    "TimeStepping",
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
    "rotor_speed",
    "rotor_time_stepping",
    "unsteady_time_stepping",
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
#: The rotor speed stated as a RATIO instead of a number of rev/min:
#: ``J = V / (n D)``, so ``n = V / (J D)`` and the row needs the
#: free-stream velocity, which it already resolves, and the propeller
#: diameter, which travels on the reference artifact beside the other
#: lengths (:attr:`pyflightstream.cases.ReferenceData.propeller_diameter`).
#:
#: IT IS THE FORM A PROPELLER STUDY IS DESIGNED IN. A sweep is laid out
#: in advance ratio and the rev/min are whatever that ratio works out to
#: at each condition, so a matrix stating rev/min states a DERIVED
#: number and silently pins it to one velocity: change the flight
#: condition and the row keeps a rotor speed that no longer means the
#: ratio it was chosen for. Stating the ratio keeps the study's own
#: variable in the file and lets the derived one move with the run.
#:
#: :data:`RPM_VARIABLE` stays, and a row states exactly one of the two.
ADVANCE_RATIO_VARIABLE = "ADVANCE_RATIO"
#: The sign of the rotor speed about its axis, ``1`` or ``-1``, applied
#: to a speed derived from an advance ratio. An advance ratio is a
#: magnitude and carries no hand, while ``RPM`` carries its sign in the
#: number itself, so this key exists for the derived form alone and is
#: refused beside an explicit ``RPM``. Absent means ``1``.
#:
#: A configuration whose isolated and installed meshes are opposite
#: hands needs opposite signs for one published sense of rotation; the
#: reference artifact records both measured signs and cannot know which
#: mesh a row opened, so the ROW is where the choice belongs.
RPM_SIGN_VARIABLE = "RPM_SIGN"
#: Degrees of rotor rotation per physical time step. With the rotor
#: speed this IS the time step: one revolution lasts ``60 / rpm`` s, so
#: a degree lasts ``1 / (6 rpm)`` s and ``DELTA_TIME = theta / (6 rpm)``.
#:
#: A rotor run is designed in degrees of azimuth, never in seconds. The
#: azimuthal resolution is the modelling decision -- how finely a blade
#: passage is resolved -- and the seconds are its consequence at this
#: rotor speed. Stating the seconds inverts that: the study's decision
#: becomes implicit and a reader has to divide two numbers to recover
#: it, while a change of rotor speed silently changes the resolution
#: the run was designed with.
DELTA_THETA_VARIABLE = "DELTA_THETA"
#: Total revolutions of the whole run, from which the physical time step
#: count follows: ``TIME_ITERATIONS = REVOLUTIONS * 360 / DELTA_THETA``.
#: Stated with :data:`DELTA_THETA_VARIABLE`, and the pair replaces
#: :data:`DELTA_TIME_VARIABLE` and :data:`TIME_ITERATIONS_VARIABLE`,
#: which stay for the matrices already written in them.
REVOLUTIONS_VARIABLE = "REVOLUTIONS"
#: WHICH of the row's OUTPUTS is the solver log, by 1-based position.
#: Absent means no log is exported, which is what
#: every workflow did before this release. A log is what turns an
#: unsteady run from "reached the end of its time loop" into a
#: residual verdict, because the iteration counter of a time loop
#: that always runs to its prescribed end judges nothing.
LOG_OUTPUT_VARIABLE = "LOG_OUTPUT"
WINDOW_DEGREES_VARIABLE = "WINDOW_DEGREES"
WINDOW_STEPS_VARIABLE = "WINDOW_STEPS"
WINDOW_REVOLUTIONS_VARIABLE = "WINDOW_REVOLUTIONS"

#: The mode the case is initialized under. The accepted tokens are READ
#: FROM THE COMMAND DATABASE per build rather than restated here, and on
#: today's 26-series builds they are ``NONE``, ``MIRROR`` and
#: ``PERIODIC``, while 25.000 spells the argument differently and offers
#: its own set
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
#: AND A SECOND CAUTION THIS KEY CANNOT REACH. No workflow calls
#: :func:`pyflightstream.script.helpers.analysis_setup`, so nothing
#: emits ``SET_ANALYSIS_SYMMETRY_LOADS`` and a MIRROR row takes the
#: solver's own default for whether the reported loads are the half
#: model's or the full one's. That default was calibrated on a licensed
#: 26.120 as ENABLE, which is the value a mirrored study wants, so what
#: is missing is the DECLARATION and not the number. The user guide
#: emits it explicitly for that reason.
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

#: The sentence on ``docs/mesh-inputs.md`` that the suffix refusal sends
#: a blocked user to, quoted VERBATIM so the two cannot drift.
#:
#: The refusal used to quote "A workflow opens route 1 only" while the
#: page said "A WORKFLOW TAKES ROUTE 1 ONLY". Both were written in the
#: same commit and neither was wrong on its own; only together were they
#: useless, because a user who does what the message says, opens the page
#: and searches for the phrase, finds nothing. Spelled here rather than
#: inline so a tier 1 guard can assert the page still contains it.
_MESH_PAGE_ANCHOR = "A WORKFLOW TAKES ROUTE 1 ONLY"

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
        value = float(text)
    except ValueError:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {key} as {text!r}, which is not a number. "
            f"It is the {quantity} in {unit}. Matrix variables arrive as text, so the "
            "conversion happens here rather than at the command, where the refusal "
            "would name only the command and not the cell you typed."
        ) from None
    # NAN AND INFINITY ARE REFUSED HERE, and this is the one place every
    # numeric cell of every rotor row passes through, which is why the
    # check lives here rather than beside each bound.
    #
    # `float("nan")` succeeds, so the conversion above lets it past, and
    # then EVERY COMPARISON AGAINST IT IS FALSE: a NaN advance ratio
    # passes a `<= 0` guard, resolves a NaN rotor speed, and reaches the
    # command layer; a NaN azimuthal step passes its range guard and dies
    # in `int(round(...))` with a bare ValueError naming neither the case
    # nor the key. This package already recorded that class once, on the
    # convergence threshold (PYFS-016), and answered it there with
    # `allow_inf_nan=False`. These keys arrive as TEXT and never touch
    # that model, so they needed their own.
    if not math.isfinite(value):
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {key} as {text!r}, which is not a finite "
            f"number. It is the {quantity} in {unit}, and a value that is NaN or "
            "infinite compares false against every bound, so it would pass each check "
            "below and be emitted, or fail much later where the refusal could name "
            "neither this case nor this key."
        )
    return value


def _required_int(case: SimCase, key: str, *, quantity: str, unit: str) -> int:
    value = _required_float(case, key, quantity=quantity, unit=unit)
    if value != int(value):
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {key} as {value!r}, and the {quantity} is a "
            f"count in {unit}, which has no fractional part."
        )
    return int(value)


# --- the rotor speed, and the clock it sets ----------------------------------
#
# TWO DERIVATIONS THAT WERE INPUTS, and the reason they are one section.
# A rotor study is designed in an advance ratio and an azimuthal step;
# the rev/min and the seconds are what those work out to at the run's own
# velocity. Until this release the matrix took the DERIVED numbers, so a
# row carried three constants (rpm, delta_time, time_iterations) that a
# reader had to divide back into the two decisions behind them, and a
# change of flight condition left all three silently meaning something
# else. Both forms are kept: a matrix written in the derived numbers is
# still read exactly as it was.


@dataclass(frozen=True)
class RotorSpeed:
    """The rotor speed of one case, and which form the row stated.

    Attributes
    ----------
    sim_id : str
        The case this speed was resolved from. It exists so that a speed
        HANDED to another function can be checked against the case that
        function was given: without it, a speed resolved from a
        different row produces a clock and a rotor motion that are
        internally consistent, export, and are wrong, and nothing
        anywhere could refuse it.
    stated_form : str
        ``rpm`` or ``advance_ratio``: what the author wrote.
    stated_value : float
        Their value, verbatim and unconverted.
    rpm : float
        The rotor speed in rev/min, signed. Derived where the form is an
        advance ratio, and the stated value itself where it is not.
    advance_ratio : float or None
        The ratio, where one was stated.
    velocity_m_per_s, diameter_m : float or None
        The two quantities the derivation consumed; None where nothing
        was derived, so a record cannot claim inputs it never read.
    """

    sim_id: str
    stated_form: str
    stated_value: float
    rpm: float
    advance_ratio: float | None
    velocity_m_per_s: float | None
    diameter_m: float | None

    def record(self) -> dict[str, object]:
        """Return the stated form, the derived one, and every input consumed.

        NOTHING IN THIS PACKAGE CONSUMES THIS YET; see
        :meth:`TimeStepping.record`, which states the position both are
        in and why they exist before a consumer does.
        """
        return {
            "form": self.stated_form,
            "stated": self.stated_value,
            "rpm": self.rpm,
            "advance_ratio": self.advance_ratio,
            "velocity_m_per_s": self.velocity_m_per_s,
            "diameter_m": self.diameter_m,
        }


def _rpm_sign(case: SimCase) -> int:
    """Return the declared sign of a derived rotor speed, defaulting to 1."""
    text = _variable(case, RPM_SIGN_VARIABLE)
    if text is None:
        return 1
    try:
        sign = int(str(text).strip())
    except ValueError:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {RPM_SIGN_VARIABLE} as {text!r}, and the "
            "sign of a rotor speed is 1 or -1. It is the hand of the rotation and not "
            "a magnitude, so anything else is a value nobody measured."
        ) from None
    if sign not in (1, -1):
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {RPM_SIGN_VARIABLE} as {sign}, and the sign "
            "of a rotor speed is 1 or -1."
        )
    return sign


def rotor_speed(case: SimCase) -> RotorSpeed:
    """Resolve the rotor speed a row states, in either form.

    Parameters
    ----------
    case : SimCase
        The case. It states ``ADVANCE_RATIO`` or ``RPM``, exactly one.
        The ratio form also reads ``RPM_SIGN`` (default 1), the case's
        free-stream velocity, and the propeller diameter carried on the
        case reference.

    Returns
    -------
    RotorSpeed

    Raises
    ------
    CampaignConfigError
        If the row states both forms or neither; if a ratio is stated
        with no propeller diameter on the reference, naming the artifact
        field to add; or if the ratio, the velocity or the diameter is
        not a positive number.
    """
    ratio_text = _variable(case, ADVANCE_RATIO_VARIABLE)
    rpm_text = _variable(case, RPM_VARIABLE)
    if ratio_text is not None and rpm_text is not None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states its rotor speed twice: "
            f"{ADVANCE_RATIO_VARIABLE} as {ratio_text!r} and {RPM_VARIABLE} as "
            f"{rpm_text!r}. The rev/min are what the ratio works out to at this run's "
            "velocity, so a second stated form is a second number nobody keeps in "
            f"agreement with the first. Keep {ADVANCE_RATIO_VARIABLE} and let the speed "
            f"be derived, or keep {RPM_VARIABLE} and state the speed directly."
        )
    if ratio_text is None and rpm_text is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states no rotor speed, and a rotary motion turns at "
            f"one. State '{ADVANCE_RATIO_VARIABLE}: <J>', which is resolved as "
            "n = V / (J D) against this run's velocity and the reference propeller "
            f"diameter, or '{RPM_VARIABLE}: <rev/min>' to state the speed itself."
        )

    if ratio_text is None:
        stated = _required_float(case, RPM_VARIABLE, quantity="rotor speed", unit="rev/min")
        if _variable(case, RPM_SIGN_VARIABLE) is not None:
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {RPM_VARIABLE} and {RPM_SIGN_VARIABLE}. A "
                "rev/min value carries its own sign in the number, so a second one "
                "beside it can only disagree with it. Write the sign into the "
                f"{RPM_VARIABLE} value, or state {ADVANCE_RATIO_VARIABLE} instead, which "
                "is a magnitude and is the form that needs a sign of its own."
            )
        return RotorSpeed(
            sim_id=case.sim_id,
            stated_form="rpm",
            stated_value=stated,
            rpm=stated,
            advance_ratio=None,
            velocity_m_per_s=None,
            diameter_m=None,
        )

    ratio = _required_float(
        case, ADVANCE_RATIO_VARIABLE, quantity="advance ratio", unit="dimensionless"
    )
    if ratio <= 0.0:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {ADVANCE_RATIO_VARIABLE} as {ratio}, and an "
            "advance ratio is positive: it is the axial distance travelled per "
            "revolution over the diameter. The HAND of the rotation is "
            f"{RPM_SIGN_VARIABLE}, which is where a negative sign belongs."
        )
    reference = case.reference
    diameter = None if reference is None else reference.propeller_diameter
    if diameter is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {ADVANCE_RATIO_VARIABLE} as {ratio} and its "
            "reference carries no propeller diameter, so the ratio names no rotor "
            "speed: J is a ratio against the diameter and n = V / (J D) cannot be "
            "evaluated without it. Add 'propeller_diameter_m' to the reference "
            "artifact this row's REF code names, beside the other reference lengths."
        )
    velocity = _velocity(case)
    if velocity <= 0.0:
        raise CampaignConfigError(
            f"case {case.sim_id!r} resolves a free-stream velocity of {velocity} m/s, "
            f"and an advance ratio needs a moving aircraft: J = V / (n D) inverts to "
            "n = V / (J D), which is a stopped rotor at V = 0. A static case states "
            f"{RPM_VARIABLE} directly."
        )
    # n in rev/s is V / (J D); rev/min is sixty times that.
    rpm = 60.0 * velocity / (ratio * diameter)
    return RotorSpeed(
        sim_id=case.sim_id,
        stated_form="advance_ratio",
        stated_value=ratio,
        rpm=_rpm_sign(case) * rpm,
        advance_ratio=ratio,
        velocity_m_per_s=velocity,
        diameter_m=diameter,
    )


def _own_speed(case: SimCase, speed: RotorSpeed | None) -> RotorSpeed:
    """Return the speed for this case, refusing one resolved from another.

    A HANDED SPEED ALSO SKIPS EVERY REFUSAL `rotor_speed` MAKES, which is
    the half that matters more than the mix-up: a row stating both
    ADVANCE_RATIO and RPM, or a ratio with no propeller diameter, is
    refused inside `rotor_speed` and builds a clean script when a caller
    supplies a speed instead. Checking the identity is what makes the
    parameter an optimisation rather than a way past the guards.
    """
    if speed is None:
        return rotor_speed(case)
    if speed.sim_id != case.sim_id:
        raise CampaignConfigError(
            f"a rotor speed resolved from case {speed.sim_id!r} was passed for case "
            f"{case.sim_id!r}. A speed carries the row it came from precisely so this "
            "cannot happen quietly: the run would emit a rotor speed and a clock that "
            "agree with each other and with no row."
        )
    return speed


def _optional_rotor_speed(case: SimCase) -> RotorSpeed | None:
    """Return the rotor speed where the row states one, and None where it does not.

    A window stated in STEPS needs no rotor speed, and refusing a case
    that never asked for one would break every such row.
    """
    if _variable(case, ADVANCE_RATIO_VARIABLE) is None and _variable(case, RPM_VARIABLE) is None:
        return None
    return rotor_speed(case)


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
        """Solver steps in one revolution, or None without a rotor speed."""
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
        # other, so an author who adds it meets the same refusal twice.
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
    delta_time_s = theta / (6.0 * abs(resolved.rpm))
    exact_steps = revolutions * 360.0 / theta
    steps = int(round(exact_steps))
    if abs(exact_steps - steps) > 1e-6:
        # WHOLE STEPS OR A REFUSAL. Rounding silently would move the run
        # length away from the revolutions the author asked for, and the
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


# --- PFS-2025.05: the rotor motion, off the row ------------------------------


def emit_rotor_motion(
    case: SimCase,
    script: Script,
    *,
    frame: int | str,
    moving_frames: Sequence[int | str] | str | None = "all",
    speed: RotorSpeed | None = None,
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
        (``MOVING_BOUNDARIES``, comma-separated boundary NAMES, family
        names, or 1-based positions; absent means every boundary). A
        family name is a boundary label with its trailing number
        removed, so ``Blade`` selects every blade the opened geometry
        carries and one cell is right for a sector mesh and a full
        wheel alike. Positions still work and warn: they belong to one
        file's boundary order and name different surfaces in a file
        that orders them differently. Names resolve only where the
        geometry was opened by this package, which is what declares
        the inventory. It may also declare the
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
    return helpers.rotary_motion(
        script,
        frame=frame,
        axis=axis.upper(),
        rpm=rpm,
        boundaries=boundaries,
        moving_frames=moving_frames,
    )


def _moving_boundaries(case: SimCase, script: Script, cell: str) -> list[int | str]:
    """Resolve a boundary-citing cell against the opened geometry's names.

    THE AUTHOR'S RULE, and the one sentence this function exists for:
    nowhere in this package should a user work with indices. A row names
    the mesh family and the package makes the link to the solver's
    indices (PFS-2028.00).

    A token resolves in this order, and the order is load-bearing:

    1. an exact boundary label of the opened geometry, so a row can
       always name one surface;
    2. otherwise a FAMILY, which is a label with its trailing index
       removed, so ``Blade`` selects every blade the file carries and one
       cell is correct for a sector mesh and a full wheel alike;
    3. otherwise a 1-based POSITION, which still works and now warns,
       naming the surfaces those positions actually select;
    4. otherwise the token passes through as a name and the script layer
       refuses it, listing the labels the geometry declared.

    Exact before family is not arbitrary. ``Blade1`` is both a label and
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
        return [_boundary(token) for token in tokens]
    resolved: list[int | str] = []
    positional: list[str] = []
    for token in tokens:
        found = resolve_family(token, labels)
        if found:
            resolved.extend(found)
            continue
        read = _boundary(token)
        if isinstance(read, int):
            positional.append(token)
        resolved.append(read)
    if positional:
        selected = ", ".join(
            f"{position} is {_named(position, labels, script.num_boundaries)}"
            for position in sorted({int(token) for token in positional})
        )
        warnings.warn(
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


def _named(position: int, labels: Mapping[str, int], total: int | None) -> str:
    """Say what the boundary at one position is, for a user to read.

    THE THIRD BRANCH IS NOT DEFENSIVE AND IT IS WHY ``total`` is taken.
    A boundary whose name the geometry uses more than once is deliberately
    left out of the label inventory, since a name meaning two surfaces
    selects neither. It is still a boundary, so reporting it as "no
    boundary in this geometry" would be false, and a warning that
    misdescribes what a user is looking at is worse than no warning: it
    is a wrong statement about their own mesh, in the message telling
    them to trust names over numbers.
    """
    for label, index in labels.items():
        if index == position:
            return label
    if total is not None and 1 <= position <= total:
        return "a boundary whose name this geometry uses more than once"
    return "no boundary in this geometry"


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
        # THE CLOCK IS RESOLVED, NOT READ. Both the step and the count
        # may be derived from the azimuthal step and the revolutions, so
        # reading the two cells directly would leave an angular row with
        # no window at all. The rotor speed is resolved once and handed
        # down, so the ratio is not converted twice.
        speed = _optional_rotor_speed(case)
        stepping = rotor_time_stepping(case, speed=speed)
        return export_window(
            degrees=degrees,
            steps=steps,
            revolutions=revolutions,
            rpm=None if speed is None else speed.rpm,
            delta_time_s=stepping.delta_time_s,
            time_iterations=stepping.time_iterations,
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
            f"route in full; search that page for '{_MESH_PAGE_ANCHOR}'. The file this "
            f"resolved to is {case.geometry!r}."
        )
    script.emit("OPEN", case.geometry)
    _declare_boundaries(case, script)


def _declare_boundaries(case: SimCase, script: Script) -> None:
    """Declare the opened geometry's boundary names onto the script.

    BOUND TO THE ``OPEN`` AND NOT TO THE SCRIPT'S CONSTRUCTION, which
    is the whole of why this call sits here (PFS-2028.00). Declaring
    when the script is built would assert a name-to-index map for a
    file that only the recipe decides whether to open, and would hand
    a pre-declared script to arbitrary user code: a recipe calling
    :meth:`~pyflightstream.script.Script.declare_existing` itself, which
    ``docs/mesh-inputs.md`` documents as the supported route, would then
    ADD to a total this package had already set, because the count form
    accumulates. Declared here, the inventory and the opened file are the
    same file by construction, and a script this package did not open a
    geometry into is left exactly as it was before this release.

    Parameters
    ----------
    case : SimCase
        The case whose geometry was just opened. The path read is the
        one ``OPEN`` received, which the campaign loop has already
        rewritten to the STAGED copy, so the names come from the same
        bytes the run record hashes and the solver reads.
    script : Script
        Script under construction, with ``OPEN`` already emitted.

    Notes
    -----
    NOTHING HERE REFUSES A RUN THAT WORKS TODAY. A geometry carrying no
    mesh block leaves the inventory undeclared, which is exactly the
    state FR-30c licenses and the state every run was in before this
    release. A block that opens and then does not hold its shape warns
    and leaves it undeclared too, because a patch may not stop a
    campaign that ran yesterday; what the warning buys is that the user
    learns why a name in a row is not resolving, instead of being told
    that no labels are registered as though it were their mistake.
    """
    if case.geometry is None:
        return
    try:
        names = boundary_names(case.geometry)
    except MeshReadError as unreadable:
        warnings.warn(
            f"case {case.sim_id!r}: {unreadable} No boundary names are declared for "
            "this run, so a row naming one is refused and a row citing positions is "
            "read exactly as it was before this release.",
            PyflightstreamWarning,
            stacklevel=2,
        )
        return
    if not names:
        return
    labels, ambiguous = boundary_labels(names)
    if ambiguous:
        warnings.warn(
            f"case {case.sim_id!r}: {PurePath(str(case.geometry)).name} carries "
            f"{len(ambiguous)} boundary name(s) used more than once "
            f"({', '.join(sorted(ambiguous))}), and a name that means two surfaces "
            "cannot select either one. Those boundaries are citable by position only; "
            "every other name in the file resolves.",
            PyflightstreamWarning,
            stacklevel=2,
        )
    if labels:
        script.declare_existing(boundaries=labels)
    # TOP THE TOTAL UP TO THE FILE'S TRUE COUNT. The mapping form sets
    # the total to the highest index it names, so a file whose LAST
    # boundary has a duplicated name would declare an inventory smaller
    # than the file and turn a correct position into a refusal. The
    # count form adds, which is a pinned contract, so the difference is
    # exactly what restores the true total.
    highest = max(labels.values(), default=0)
    if len(names) > highest:
        script.declare_existing(boundaries=len(names) - highest)


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

        An EMPTY TUPLE where the build declares a ``symmetry`` argument
        that is NOT an enumeration. A non-enum argument carries no
        ``values`` in the command database and reads back as ``()``. No
        registered build is that shape today: 25.000 spells the argument
        ``symmetry_type`` and every other build declares the three-token
        enum.

        BOTH FALSY ANSWERS MEAN "THIS BUILD CANNOT JUDGE A MODE", so a
        caller tests truthiness::

            if accepted and mode not in accepted:
                ...

        That is what the built-in workflows do, and they deliberately do
        NOT tell the two apart. Tell them apart only when REPORTING to a
        user which fact holds: ``None`` means the build declares no
        argument of that name, ``()`` means it declares one that is not
        an enumeration. An earlier draft of this paragraph pointed at the
        workflow builders as the precedent for distinguishing them, which
        is the opposite of what they do, and a reader following that
        citation found a truthiness test and could reasonably conclude
        ``is not None`` was sanctioned. It is not.

        AN ENUMERATION DECLARING NO TOKENS IS NOT ONE OF THESE CASES,
        and the distinction is worth a line because the obvious reading
        gets it backwards. That state cannot exist:
        :class:`pyflightstream.commands.ArgSpec` refuses to validate an
        enum with no values, so a database containing one fails to load.
        An earlier draft of this section offered it as the meaning of
        ``()`` and called the real producer impossible, which is exactly
        the reading under which ``if accepted is not None`` looks
        correct at the call site. It is not, and that regression was
        written and reverted once already.

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
    # THE PRESET REACHES INITIALIZE_SOLVER TOO, for the two arguments it
    # states. Both are passed UNCONDITIONALLY and the absent case is
    # spelled as the emitter's own default rather than as a missing
    # keyword: `solver_model=None` would be a different call, so the
    # `or` restates INCOMPRESSIBLE, which is what the helper signature
    # already defaults to, and `wall_collision_avoidance=None` is that
    # parameter's own default and emits nothing.
    #
    # The first version built a `dict[str, object]` and unpacked it,
    # which typechecks as `object` against four differently typed
    # parameters: the type checker could not see that any of them was
    # right, on the one call this round exists to make.
    helpers.initialize_solver(
        script,
        symmetry=mode,
        periodic_copies=copies,
        solver_model=case.solver.solver_model or "INCOMPRESSIBLE",
        wall_collision_avoidance=case.solver.wall_collision_avoidance,
    )


def _settings(
    case: SimCase, script: Script, *, wake_termination_time_steps: int | None = None
) -> None:
    """Emit the solver settings, including the reference if the case has one.

    THE REFERENCE REACHES THE SCRIPT HERE (PFS-2025.02.04), and until
    0.9.0 it did not. A row's REF code resolved a reference artifact,
    the artifact was bound onto the case, and no emitter ever read it:
    measured across the 29 committed workflow goldens, not one carried a
    ``REF_`` line. So a campaign declared its areas and lengths and the
    coefficients came out against whatever the solver was defaulting to,
    with nothing said.

    The emitter one layer down has always taken these two arguments;
    what was missing was the four lines that pass them. A case carrying
    no reference emits neither, exactly as before, which is what keeps
    every golden of a reference-less case byte identical.

    UNITS ARE NOT CONVERTED HERE. The reference artifact documents its
    own (area in square metres, length in metres) and the values are
    emitted as the artifact carries them; converting at the emitter
    would put a second opinion about units in the one place that cannot
    see the artifact's documentation.
    """
    reference = case.reference
    solver = case.solver
    # THE PRESET'S OWN SETTINGS REACH THE SCRIPT HERE, and until this
    # release ten of them did not: a preset asking for
    # SUBSONIC_PRANDTL_GLAUERT and a turbulent boundary layer resolved
    # onto a case that carried neither, so the run took the solver's
    # defaults and said nothing. Every argument below is passed as the
    # case carries it, so a case carrying None emits nothing for it and
    # every script written before this release is byte identical.
    #
    # `wake_termination_revolutions` is deliberately absent: it is the
    # one preset setting whose unit the emitter does not take, and the
    # conversion needs the case's own clock, so the rotor builder does
    # it (:func:`_wake_termination`) and the steady builder, which
    # has no clock, cannot and does not.
    helpers.solver_settings(
        script,
        aoa=case.point.get("alpha", 0.0),
        sideslip=case.point.get("beta"),
        velocity=_velocity(case),
        iterations=solver.iterations,
        convergence=solver.convergence,
        max_threads=solver.max_threads,
        ref_area=None if reference is None else reference.area,
        ref_length=None if reference is None else reference.length,
        forced_iterations=solver.forced_iterations,
        boundary_layer=solver.boundary_layer,
        viscous_coupling=solver.viscous_coupling,
        convergence_iterations=solver.convergence_iterations,
        minimum_cp=solver.minimum_cp,
        farfield_layers=solver.farfield_layers,
        mesh_induced_wake_velocity=solver.mesh_induced_wake_velocity,
        unsteady_pressure_and_kutta=solver.unsteady_pressure_and_kutta,
        wake_on_wake_induction=solver.wake_on_wake_induction,
        additional_wake_relaxation=solver.additional_wake_relaxation,
        reynolds_averaged_drag=solver.reynolds_averaged_drag,
        solver_stabilization=solver.solver_stabilization,
        wake_termination_time_steps=wake_termination_time_steps,
    )


def _fluid(case: SimCase, script: Script) -> None:
    """Emit the resolved air state, where the row resolved one.

    PFS-2025.02.05 and PFS-2027.05. A case whose row stated a flight
    condition arrives here carrying the state that condition resolved
    to, and it is emitted as the FIVE EXPLICIT FLUID PROPERTIES rather
    than as an altitude. That choice is forced rather than preferred:
    ``AIR_ALTITUDE`` has no argument for an ISA deviation, so a
    condition carrying ``dISA`` could not be expressed by it at all, and
    a density solved to meet a Reynolds number is not an atmosphere
    point in the first place. Emitting the state we computed says
    exactly what will be solved.

    A case carrying no resolved state emits NOTHING here, which is what
    keeps every case written before 0.9.0, and every hand-written
    campaign that sets no fluid, rendering exactly what it rendered
    before.
    """
    fluid = case.fluid
    if fluid is None:
        return
    # WHICH FIFTH PROPERTY depends on the build, and the emitter refuses
    # the one its build does not take. Asking rather than guessing is
    # what lets one case render on either side of the 26.100 boundary.
    fifth = helpers.fluid_fifth_property(script)
    helpers.atmosphere(
        script,
        density=fluid.density_kg_m3,
        pressure=fluid.pressure_pa,
        temperature=fluid.temperature_k,
        viscosity=fluid.viscosity_pa_s,
        specific_heat_ratio=(fluid.heat_capacity_ratio if fifth == "specific_heat_ratio" else None),
        sonic_velocity=(fluid.sonic_velocity_m_per_s if fifth == "sonic_velocity" else None),
    )


def _wake_termination(case: SimCase, stepping: TimeStepping) -> int | None:
    """Convert the preset's wake termination from revolutions to time steps.

    A rotor preset states it in revolutions, because that is the unit a
    rotor wake is thought about in, and negative counts backwards from
    the end of the run. The emitter takes STEPS. The conversion needs
    the steps per revolution, which is a property of this case's clock
    and its rotor speed and of nothing else, which is why it happens
    here rather than in the artifact model.

    Returns None where the preset states none, so a case that asks for
    nothing emits nothing.
    """
    revolutions = case.solver.wake_termination_revolutions
    if revolutions is None:
        return None
    per_revolution = stepping.steps_per_revolution
    if per_revolution is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} inherits a wake termination of {revolutions} "
            "revolutions from its solver preset and states no rotor speed, so a "
            "revolution has no length in time steps here. State the rotor speed with "
            f"{ADVANCE_RATIO_VARIABLE} or {RPM_VARIABLE}, or drop the preset key."
        )
    return int(round(revolutions * per_revolution))


def _refuse_wake_termination_without_a_clock(case: SimCase) -> None:
    """Refuse a wake termination on a run type that has no clock to convert it.

    THE STEADY BUILDER USED TO DROP THIS SILENTLY. A preset stating
    ``unsteady_N_revolutions_wake`` resolved onto a steady case,
    validated, reached no emitted line, and said nothing, which is
    exactly the defect this release closes one layer up for a preset key
    that maps to no field at all. A key that maps to a field and still
    reaches no script is the same wrong answer with a longer path to it.

    Revolutions cannot be converted here rather than merely being
    unused: a steady run has no time step and no rotor speed, so there
    is no number of steps a revolution could be.
    """
    revolutions = case.solver.wake_termination_revolutions
    if revolutions is None:
        return
    raise CampaignConfigError(
        f"case {case.sim_id!r} inherits a wake termination of {revolutions} revolutions "
        "from its solver preset and is a STEADY run, which has no time loop, so there "
        "are no time steps for a revolution to become and the setting would reach no "
        "line. Drop the key from the preset this row names, or give the row a preset "
        "of its own; a steady row and a rotor row cannot share a wake termination "
        "stated in revolutions."
    )


#: A signed decimal, which is what "meant as a number" has to mean here.
_DECIMAL = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)$")


def _log_position_shape(text: str) -> str:
    """Classify a LOG_OUTPUT cell that is not a whole number.

    THE FIRST VERSION ASKED `float(text)`, which is wider than the
    message it selected: `nan`, `inf` and `1e3` all parse, so their
    authors were told the value "takes no decimal point" about
    characters containing no decimal point. A refusal whose whole job is
    to point at the cell someone typed cannot be wrong about what they
    typed.
    """
    if _DECIMAL.match(text):
        return "decimal"
    if any(character in text for character in r"/\.") or text.endswith("}"):
        return "name"
    return "neither"


def _export_log(
    conventions: WorkflowConventions,
    case: SimCase,
    script: Script,
    *,
    claimed: tuple[int, ...],
) -> None:
    """Export the solver log where the row says WHICH of its outputs is one.

    WHY A ROTOR ROW WANTS ONE. Without a log this package cannot judge
    convergence of an unsteady run at all: the time loop always reaches
    its prescribed end, so the iteration counter says nothing, and every
    such run is recorded COMPLETED_MAX_ITER whether it converged at
    every time step or at none. That word is a statement about the
    evidence and it reads as a statement about the solver. One more
    export line turns it into a real verdict.

    WHY AN INDEX, which is the less pretty of the two spellings and the
    only correct one. Two earlier spellings were wrong, and both are
    recorded here as DEVELOPMENT RECOLLECTION rather than as evidence:
    neither left a committed artifact, so nothing in this tree can be
    read to confirm them. What IS committed is the pair of tests each
    one now has, and those are the falsifiable half.

    The first read ``outputs[1]``, so a row whose second output is a
    force-distribution export would have had a solver log written over
    that name. A second declared output means "a second file this row
    expects", never "a log".

    The second took the name as the row WRITES it in OUTPUTS, and the
    names have been RENDERED by the time a builder sees them: the cell
    says ``loads_{point}.txt`` and the case carries
    ``loads_a+00.0.txt``, so the comparison could never match.

    An index is the one thing that survives rendering, because rendering
    preserves order. It is 1-BASED, matching how the cell is read left
    to right rather than how a list is subscripted.

    ``claimed`` is the set of 1-based positions the calling builder has
    already exported something else to, and naming one of them is
    REFUSED. Position 1 is the loads spreadsheet in both builders, and
    it is the most likely typo of someone who has just read "counted
    from 1"; without this the solver writes the log over the loads
    table, the run completes, and the assessor sends the author to look
    for a truncated export instead of at the cell they typed.
    """
    declared = _variable(case, LOG_OUTPUT_VARIABLE)
    if declared is None:
        return
    names = conventions.outputs or tuple(case.outputs)
    text = str(declared).strip()
    try:
        position = int(text)
    except ValueError:
        # THE TWO WRONG SHAPES GET DIFFERENT MESSAGES. `2.0` is not a
        # name, and telling its author why a NAME cannot be used here
        # answers a question they did not ask.
        why = {
            "name": (
                "A name cannot be used here: the output names carry the point "
                "placeholder in the cell and reach a builder already RENDERED, so the "
                "cell's spelling and the case's never match."
            ),
            "decimal": (
                "It is a whole number of files and not a measurement, so it takes no decimal point."
            ),
            "neither": "That is not a whole number.",
        }[_log_position_shape(text)]
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {LOG_OUTPUT_VARIABLE} as {declared!r}, and "
            "it is the POSITION of the solver log among the row's own OUTPUTS, counted "
            f"from 1. {why} {LOG_OUTPUT_VARIABLE}: 2 says 'the second file this row "
            "declares'."
        ) from None
    if not 1 <= position <= len(names):
        raise CampaignConfigError(
            f"case {case.sim_id!r} names output {position} as its solver log and "
            f"declares {len(names)}: {', '.join(names) or 'nothing'}. The log is "
            "declared in OUTPUTS like every other file the row produces, so that it is "
            f"collected, and {LOG_OUTPUT_VARIABLE} says which one it is."
        )
    if position in claimed:
        raise CampaignConfigError(
            f"case {case.sim_id!r} names output {position} as its solver log and this "
            f"run type already exports {names[position - 1]!r} there. The solver would "
            "write the log over that file, the run would complete, and the export that "
            "was overwritten is the one this package judges the run by. Declare the log "
            f"as its own entry in OUTPUTS and point {LOG_OUTPUT_VARIABLE} at it."
        )
    script.emit("EXPORT_LOG", names[position - 1])


def _build_steady(case: SimCase, script: Script, conventions: WorkflowConventions) -> None:
    """Build a steady polar point: open, free stream, settings, solve, export.

    The open is FIRST and only where the case names a geometry
    (:func:`_open_geometry`), so a case that names none emits exactly
    the lines this workflow emitted before 0.8.1.
    """
    _refuse_wake_termination_without_a_clock(case)
    _open_geometry(case, script)
    helpers.free_stream(script)
    _fluid(case, script)
    _settings(case, script)
    _initialize(case, script)
    helpers.start_solver(script)
    script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", _output(conventions, case, 0))
    _export_log(conventions, case, script, claimed=(1,))
    script.emit("CLOSE_FLIGHTSTREAM")


# --- PFS-2028.01: the third run type, unsteady with nothing turning ----------


def unsteady_time_stepping(case: SimCase) -> TimeStepping:
    """Resolve the physical clock of a run that turns nothing.

    THE SECONDS AND THE COUNT, AND NOT THE ANGULAR PAIR. A degree of
    rotation has no duration in a run with no rotation: the rotor
    resolver turns ``DELTA_THETA`` into seconds as ``theta / (6 |rpm|)``,
    and there is no rpm here for it to divide by. So the angular pair is
    refused rather than left to fail further in, and the refusal says
    which of the two spellings this run type has.

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
        If the row states the angular pair, states neither pair, or
        states half of the explicit one. Each message names the case,
        which is the matrix POL, and the keys involved.
    """
    angular = {
        key: value
        for key in (DELTA_THETA_VARIABLE, REVOLUTIONS_VARIABLE)
        if (value := _variable(case, key)) is not None
    }
    if angular:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {', '.join(sorted(angular))} and this run type "
            "turns nothing, so a degree of rotation has no duration in it: the azimuthal "
            "step becomes seconds by dividing by a rotor speed, and this run has none. "
            f"State the clock directly as '{DELTA_TIME_VARIABLE}: <s>' and "
            f"'{TIME_ITERATIONS_VARIABLE}: <steps>'. A row that really does have a rotor "
            "belongs to the rotor run type, which takes the azimuthal form."
        )
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


#: The row keys that change an emitted line on the rotor run type and
#: would reach no line at all on this one. Refused rather than dropped:
#: a key that validates and reaches nothing is the same wrong answer with
#: a longer path to it, which is the reason
#: :func:`_refuse_wake_termination_without_a_clock` already exists.
#:
#: ``BLADES`` is deliberately NOT here. It changes no emitted line on
#: either existing type, so refusing it would be a new rule about an
#: unread key rather than this item's business, and the reduction plan
#: reads it for a per-blade split that a rotorless run simply never asks
#: for.
ROTORLESS_REFUSED_KEYS: tuple[str, ...] = (
    ADVANCE_RATIO_VARIABLE,
    MOVING_BOUNDARIES_VARIABLE,
    ROTOR_AXIS_VARIABLE,
    ROTOR_ORIGIN_VARIABLE,
    RPM_SIGN_VARIABLE,
    RPM_VARIABLE,
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


def _build_unsteady(case: SimCase, script: Script, conventions: WorkflowConventions) -> None:
    """Build an unsteady point of a body that does not move.

    The rotor builder without the rotor: no coordinate system, no
    motion, and a clock stated directly rather than derived from a
    speed. Both refusals run before the first emission.
    """
    _refuse_rotor_keys_on_a_rotorless_run(case)
    _refuse_wake_termination_without_a_rotor(case)
    _open_geometry(case, script)
    helpers.free_stream(script)
    _fluid(case, script)
    stepping = unsteady_time_stepping(case)
    helpers.unsteady_solver(
        script,
        time_iterations=stepping.time_iterations,
        delta_time=stepping.delta_time_s,
    )
    _settings(case, script)
    _initialize(case, script)
    helpers.start_solver(script)
    script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", _output(conventions, case, 0))
    _export_log(conventions, case, script, claimed=(1,))
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
    _fluid(case, script)
    # RESOLVED ONCE AND THREADED. The ratio was previously converted
    # twice per case, here and again for the clock, which is the saving
    # the `speed` parameter was added for and was not collecting.
    speed = rotor_speed(case)
    emit_rotor_motion(case, script, frame="rotor", speed=speed)
    # THE CLOCK COMES OFF THE SAME RESOLVER THE WINDOW USES, so a row
    # stating its azimuthal step and its revolutions emits the seconds
    # and the step count those work out to, and a row stating the
    # seconds and the count emits exactly what it always emitted.
    stepping = rotor_time_stepping(case, speed=speed)
    helpers.unsteady_solver(
        script,
        time_iterations=stepping.time_iterations,
        delta_time=stepping.delta_time_s,
    )
    _settings(case, script, wake_termination_time_steps=_wake_termination(case, stepping))
    _initialize(case, script)
    helpers.start_solver(script)
    script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", _output(conventions, case, 0))
    _export_log(conventions, case, script, claimed=(1,))
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
    "unsteady": Workflow(
        name="unsteady",
        summary=(
            "One unsteady point of a body that does not move: a uniform free stream, a "
            "physical time loop stated directly by the row, one solve, one loads export."
        ),
        commands=(
            "SET_FREESTREAM",
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
        builder=_build_unsteady,
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
