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
would name only the command and send the user to the command
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
import sys
import warnings
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from pathlib import PurePath
from types import MappingProxyType

from pyflightstream._deprecations import (
    ROW_MOVING_BOUNDARIES,
    ROW_ROTATE_FAMILIES,
    refusal_text,
)
from pyflightstream._errors import (
    PyflightstreamError,
    PyflightstreamWarning,
)
from pyflightstream._fsm import (
    MeshReadError,
    boundary_labels,
    boundary_names,
)
from pyflightstream._retired_names import retired_frame
from pyflightstream.cases import (
    EXPANDING_FRAMES,
    EXPORT_KINDS,
    FORCE_PLOT_PARAMETERS,
    RAW_PHASES,
    CampaignConfigError,
    CustomFlag,
    RotorBlock,
    ScriptRecipe,
    SimCase,
    alias_members_missing,
    classify_outputs,
    resolve_alias,
    select_families,
    select_group_members,
    warn_a_selector_that_guesses,
)
from pyflightstream.commands import CommandRegistry, Phase
from pyflightstream.script import CommandArgumentError, Script, ScriptReferenceError, helpers
from pyflightstream.versions import FsVersion, known_versions, resolve

__all__ = [
    "ADVANCE_RATIO_VARIABLE",
    "BLADES_VARIABLE",
    "DELTA_THETA_VARIABLE",
    "DELTA_TIME_VARIABLE",
    "EXPORT_UNSTEADY_AFTER_ITER_VARIABLE",
    "EXPORT_UNSTEADY_AFTER_REV_VARIABLE",
    "GEOMETRY_VARIABLE",
    "IGNORE_MISSING_FAMILIES_VARIABLE",
    "LOG_OUTPUT_VARIABLE",
    "BASE_REGIONS_VARIABLE",
    "MOTIONS_VARIABLE",
    "MOVING_BOUNDARIES_VARIABLE",
    "ROTATE_VARIABLE",
    "PERIODIC_COPIES_VARIABLE",
    "PROBE_POSITION_COLUMNS",
    "PROBE_PROFILE_DIR",
    "RAW_BEFORE_KEY",
    "RAW_COMMAND_KEY",
    "RAW_FILE_KEY",
    "RAW_VARIABLE",
    "REVOLUTIONS_VARIABLE",
    "ROTORLESS_REFUSED_KEYS",
    "ROTOR_AXIS_VARIABLE",
    "ROTOR_ORIGIN_POINT_KEY",
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
    "PER_ROTOR_REDUCTIONS",
    "REDUCTION_NAMES",
    "ROTORS_KEY",
    "ReductionPlan",
    "RotorSpeed",
    "TimeStepping",
    "UNSTEADY_ACTION_COUNT",
    "UNSTEADY_ACTION_PROGRAM",
    "UNSTEADY_ACTION_SCRIPT",
    "UNSTEADY_COUNTER_ACTION",
    "UNSTEADY_EXPORTS_ACTION",
    "UnsteadyExportThreshold",
    "WHOLE_RUN_EXPORT_KINDS",
    "Workflow",
    "WorkflowConventions",
    "WorkflowCoverageError",
    "accepted_symmetry",
    "build_script",
    "covered_builds",
    "emit_rotor_motion",
    "export_window",
    "reduction_plan",
    "reduction_windows",
    "require_coverage",
    "resolve_workflow",
    "rotor_relaxed_trailing_edges",
    "rotor_shedding_direction",
    "rotor_speed",
    "rotor_time_stepping",
    "time_steps_of",
    "unsteady_action_command_line",
    "unsteady_export_threshold",
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
#: staged path, so the user read back a string they had never typed.
#: Free because the name is new in this release and had no published
#: contract to keep.
GEOMETRY_VARIABLE = "GEOMETRY"

#: Free case variables a workflow reads off the row. Each is a KEY of the
#: matrix ``VAR_NAMES_VALUES`` cell and arrives as a string.
VELOCITY_VARIABLE = "VELOCITY"
RPM_VARIABLE = "RPM"
ROTOR_AXIS_VARIABLE = "ROTOR_AXIS"
ROTOR_ORIGIN_VARIABLE = "ROTOR_ORIGIN"
#: The key the WORKSPACE writes beside a bound ``ROTOR_ORIGIN``, carrying
#: the rotor point's name once the coordinates replaced it, so the run
#: record says which point the hub was (PFS-2029.11.02). A user never
#: writes it, which is why the vocabulary check below leaves it alone.
ROTOR_ORIGIN_POINT_KEY = "ROTOR_ORIGIN_POINT"
#: The one ``VAR_NAMES_VALUES`` key whose value is a LIST OF RECORDS
#: (PFS-2029.11.01): ``MOTIONS: {A: 1 / B: x}, {A: 2 / B: y}``. Each
#: record holds the keys one rotor motion is stated with; a row with the
#: list states no flat motion key beside it. Defined HERE, beside the
#: other cell keys, since 0.13.0, so the rotor run type can register it;
#: :mod:`pyflightstream.cases.matrix`, whose reader consumes the list
#: into :attr:`~pyflightstream.cases.SimCase.motions`, re-exports it.
MOTIONS_VARIABLE = "MOTIONS"
#: The row's ROTATION of the opened mesh (PFS-2034.02, the design of
#: 2026-09-09, design/69): a list of records like ``MOTIONS``, each one
#: rotation, in the order written, ``ROTATE: {ANGLE: 3 / AXIS: NAC-Y /
#: ALIAS: PUSHER}, {...}``. ``AXIS`` names a
#: frame the setup defines or the package creates and one of its axes;
#: ``FAMILIES`` names boundaries or families of the geometry, never
#: indices; ``AUX_FRAMES`` names the frames that turn with the mesh. One
#: row is one geometry, so a row states its angles here and not as a
#: sweep. Read by :mod:`pyflightstream.cases.matrix` into
#: :attr:`~pyflightstream.cases.SimCase.rotations`.
ROTATE_VARIABLE = "ROTATE"

#: The word a value carries instead of a number when its key is the one
#: the row sweeps (FR-69). SWEEP_VALUES then holds its values, and exactly
#: one key of the cell may carry it.
SWEEP_WORD = "sweep"

#: The keys a rotation record carries. ``ANGLE`` and ``AXIS`` are always
#: stated; WHAT IT TURNS is stated once, as ``ALIAS`` since 0.15.0 or as
#: ``FAMILIES`` before it.
ROTATION_RECORD_KEYS = ("ANGLE", "AXIS")

#: The word a rotation turns (FR-71, the design of 2026-09-10). A rotation
#: and a motion cite a set THE SAME WAY, which is the whole point of the
#: rename: after it, every surface of this package that names a group of
#: boundaries names it by alias, and the reference is the one place a
#: study says what its groups are.
ROTATION_ALIAS_KEY = "ALIAS"

#: The 0.14.0 spelling, REFUSED since 0.15.0 naming ``ALIAS``. It
#: named the boundaries INLINE, which is the thing the alias replaces: a
#: row listing families is a row that has to be edited when the mesh is
#: renamed, and there are as many of those rows as there are studies.
ROTATION_FAMILIES_KEY = "FAMILIES"

#: What the alias makes unnecessary rather than what it forbids. Every
#: frame an alias OWNS turns with its boundaries since 0.15.0, so a record
#: no longer lists them; a record still listing them is read SILENTLY and
#: the frames it names turn as they did, and a frame the alias already
#: carries is not turned twice for having been named twice. This comment
#: said "read with a warning until 0.17.0" until a review round asked
#: where that warning was: there is none, and no ledger entry behind it
#: either (2026-09-10).
ROTATION_OPTIONAL_KEYS = ("AUX_FRAMES",)
#: The direction a rotor case's relaxed trailing edges shed their wake:
#: AXIAL (0) or AZIMUTH (1), the second being what 26.123 adds and what a
#: rotor case wants (SRC-751 p.85). Absent means the row asks for nothing
#: and every specification stays exactly as it was written.
ROTOR_SHEDDING_VARIABLE = "ROTOR_SHEDDING"
BLADES_VARIABLE = "BLADES"
MOVING_BOUNDARIES_VARIABLE = "MOVING_BOUNDARIES"
#: The word a motion record uses to name its rotor since 0.15.0 (FR-61,
#: the design of 2026-09-10): an ALIAS the reference declares as a rotor
#: block, and the only rotor identity a row carries. The hub, the axis,
#: the sign, the blade count and the diameter come from that block, so a
#: row states which rotors turn and at what operating point and nothing
#: else about them. It replaces :data:`MOVING_BOUNDARIES_VARIABLE` and the
#: four keys beside it, which are REFUSED since 0.15.0 naming their
#: replacements, and refused a second way in the same record as this one.
MOVING_BC_ALIAS_VARIABLE = "MOVING_BC_ALIAS"
#: The motion that owns the row's clock (FR-64, the design of 2026-09-10).
#: It names a motion the same row states, and the time step and the run
#: length are that motion's. A row without it keeps the arithmetic of
#: 0.14.0, the fastest rotor, with a warning naming the motion assumed;
#: the key becomes required at 0.17.0. `rotor_speed` is what a one-rotor
#: row resolves; on a row of several, `_clock_speed` is which of them the
#: clock follows. FR-64 also asks for `rotor_speed` to be renamed
#: `rotor_speed_ref` at the call site, and that half is NOT done: the
#: requirement says so rather than this comment naming a symbol the tree
#: does not carry (the technical writing lens of 2026-09-10).
CLOCK_MOTION_VARIABLE = "CLOCK_MOTION"
#: Whether the solver reports the loads of the meshed sector or of the
#: whole wheel (FR-66, the design decision of 2026-09-10). A preset key promoted
#: to a row key, because one preset serves a sector row and a full-wheel
#: row; a row stating it overrides the preset and warns naming both.
SYMMETRY_LOADS_VARIABLE = "SYMMETRY_LOADS"
#: The two angles that fix the attitude of a point (FR-69, the rule of
#: 2026-09-10). They are keys of the FLIGHT_CONDITION cell, stated on
#: every row, so that no run reaches the solver at an angle nobody wrote;
#: the swept one carries the word `sweep` instead of a number and is the
#: point's, and the other is read from here. They are the row's own keys
#: on the case, put there by the matrix reader, and are NOT registered in
#: the run types' key vocabularies for that reason.
ALPHA_VARIABLE = "ALPHA"
BETA_VARIABLE = "BETA"
#: The mesh families the base-region autodetect is allowed to consider
#: (PFS-2029.10), comma separated; overrides the pproc artifact's list.
BASE_REGIONS_VARIABLE = "BASE_REGIONS"
DELTA_TIME_VARIABLE = "DELTA_TIME"
TIME_ITERATIONS_VARIABLE = "TIME_ITERATIONS"
#: The rotor speed stated as a RATIO instead of a number of rev/min:
#: ``J = V / (n D)``, so ``n = V / (J D)`` and the row needs the
#: free-stream velocity, which it already resolves, and the rotor
#: diameter, which travels on the reference artifact beside the other
#: lengths (:attr:`pyflightstream.cases.ReferenceData.rotor_diameter`).
#:
#: IT IS THE FORM A ROTOR STUDY IS DESIGNED IN. A sweep is laid out
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
#: The step the per-step exports BEGIN on, stated in revolutions of the
#: rotor or in time iterations (PFS-2031.18, the design of 2026-09-08,
#: GeoversePlan design 67). A row states at most one. From that step to
#: the end of the run the solver exports every per-step kind of the row's
#: output set after each time step, each file stamped ``_iteration=N`` by
#: the solver itself (RPT-041 finding 3). Revolutions need a rotor clock,
#: so the form is refused on the run type that turns nothing; iterations
#: are accepted on both unsteady types and refused on a steady row, which
#: has no time loop for an action to run in.
#:
#: This is the "after N" form that supersedes the degrees-backwards window
#: of PFS-2025.08 for the mid-run exports; ``WINDOW_*`` stays what it was,
#: the averaging window of the reductions.
EXPORT_UNSTEADY_AFTER_REV_VARIABLE = "EXPORT_UNSTEADY_AFTER_REV"
EXPORT_UNSTEADY_AFTER_ITER_VARIABLE = "EXPORT_UNSTEADY_AFTER_ITER"

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

#: The cell key whose value is a LIST OF RECORDS, each one raw solver
#: command line the row states, or one file of them (FR-67, the design decision of
#: 2026-09-10, "a linha ganha um jeito de passar comando bruto, mantendo a
#: feature original preservada").
RAW_VARIABLE = "RAW"

#: The two forms a raw record takes, and exactly one of them is written:
#: the line itself, or a text file of the workspace holding lines.
RAW_COMMAND_KEY = "COMMAND"
RAW_FILE_KEY = "FILE"

#: The key every raw record states beside its form: the phase the line goes
#: before, spelled as the preset's `[[raw]]` table spells it.
RAW_BEFORE_KEY = "BEFORE"

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
    keys : tuple of str
        Every ``VAR_NAMES_VALUES`` key the run type READS: the row's
        vocabulary, and the list a refusal prints when a row states a
        key outside it (PFS-2008.02.01, the rule of 2026-09-08: a row
        states only what the script will carry). A key here is one the
        builder, the clock, the window or the point name resolves; a key
        another run type reads is refused on this one naming that type,
        because a value nothing reads would change nothing about the
        run while reading as though it had. The tier-3 workspace is the
        control that the tuple is complete: every matrix there plans
        READY, so a key a row of it states is registered here.
    """

    name: str
    summary: str
    commands: tuple[str, ...]
    builder: Callable[[SimCase, Script, WorkflowConventions], None]
    keys: tuple[str, ...]


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
        both values so the user can see which to delete; or if it
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
            "user meant. Make the two agree, or leave only one of them."
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
        (CONTRIBUTING.md invariant 4).
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


def _required_float(
    case: SimCase, key: str, *, quantity: str, unit: str, text: str | None = None
) -> float:
    """One numeric case variable, refused by CASE and KEY rather than by command.

    ``text`` is for a caller that has ALREADY resolved the value from somewhere
    other than ``variables``, which today means the advance ratio a swept row
    puts on its POINT. It exists so that the conversion,
    the not-a-number refusal and the non-finite refusal keep ONE home: the first
    fix for that incident hand-rolled a second conversion beside the fallback
    and silently dropped the non-finite half, which two existing cases caught.
    """
    if text is None:
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
        ``rpm`` or ``advance_ratio``: what the user wrote.
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


#: The decimals a rotor speed derived from an advance ratio is emitted at:
#: the reference tooling wrote four, and the recorded runs turned at that value.
_DERIVED_RPM_DECIMALS = 4


#: The swept axis's own key on a point, which is where a row that writes
#: `ADVANCE_RATIO:sweep` in its flight condition puts the VALUE.
_POINT_ADVANCE_RATIO = "advance_ratio"


def _stated_advance_ratio(case: SimCase) -> str | None:
    """Resolve the advance ratio this row states, from `variables` or its POINT.

    ONE FACT WITH TWO HOMES, and until 2026-09-11 only one of them was read.
    A row stating `ADVANCE_RATIO:sweep` in its flight condition puts the VALUE
    on the point: the HELD coordinates of a sweep are merged into `variables`
    and the SWEPT one is not, so `variables` carries `ALPHA` and `BETA` and no
    `ADVANCE_RATIO` at all. The script emitter resolves the point correctly and
    writes the speed into the script; the reduction planner asked `variables`
    and concluded the row stated no speed, so every unsteady reduction of every
    such point was recorded as SKIPPED with a message prescribing the thing the
    row had already done. Four of four points, three of three reductions each,
    on the licensed runs of 2026-09-11. Measured on four of four
    points of two licensed runs on 2026-09-11, three of three reductions each.

    THE POINT IS CONSULTED ONLY WHEN `variables` STATE NEITHER FORM. A row that
    states `RPM` keeps `RPM`; a motion record carrying its own speed keeps it;
    the two-forms refusal and the sweep-word refusal read `variables` alone and
    fire exactly where they fired before. The narrowness is the point: this
    adds a reading where there was none, and changes none that existed.
    """
    stated = _variable(case, ADVANCE_RATIO_VARIABLE)
    if stated is not None or _variable(case, RPM_VARIABLE) is not None:
        return stated
    value = (getattr(case, "point", None) or {}).get(_POINT_ADVANCE_RATIO)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def rotor_speed(case: SimCase) -> RotorSpeed:
    """Resolve the rotor speed a row states, in either form.

    Parameters
    ----------
    case : SimCase
        The case. It states ``ADVANCE_RATIO`` or ``RPM``, exactly one.
        The ratio form also reads ``RPM_SIGN`` (default 1), the case's
        free-stream velocity, and the rotor diameter carried on the
        case reference.

    Returns
    -------
    RotorSpeed

    Raises
    ------
    CampaignConfigError
        If the row states both forms or neither; if a ratio is stated
        with no rotor diameter on the reference, naming the artifact
        field to add; or if the ratio, the velocity or the diameter is
        not a positive number.
    """
    # THE POINT IS A HOME FOR THIS VALUE TOO, and a swept row's only one.
    # `_stated_advance_ratio` falls back to it when the variables state neither
    # form, so a row writing `ADVANCE_RATIO:sweep` resolves here as it already
    # resolved in the script emitter, which reads the point and writes
    # `SET_MOTION_ROTOR_RPM` from it.
    ratio_text = _stated_advance_ratio(case)
    rpm_text = _variable(case, RPM_VARIABLE)
    # READ FROM `variables`, NOT from the fallback: this refusal is about a
    # MOTION RECORD writing the word `sweep`, and a point carries a number.
    for key, text in (
        (ADVANCE_RATIO_VARIABLE, _variable(case, ADVANCE_RATIO_VARIABLE)),
        (RPM_VARIABLE, rpm_text),
    ):
        if isinstance(text, str) and text.strip().casefold() == SWEEP_WORD.casefold():
            # SWEEPING IS THE CONDITION'S JOB (FR-70). A record that writes
            # the word is asking the motion to vary, and a row varies ONE
            # variable, stated once, where every other reader can see it.
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {key}: {text.strip()} on a motion record. "
                "Sweeping is stated in FLIGHT_CONDITION, once for the row, and it then "
                "reaches every motion that states no speed of its own; a record states a "
                "VALUE, which is how one rotor holds while another is swept."
            )
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
            "n = V / (J D) against this run's velocity and the reference rotor "
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
        case,
        ADVANCE_RATIO_VARIABLE,
        quantity="advance ratio",
        unit="dimensionless",
        text=ratio_text,
    )
    if ratio <= 0.0:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares {ADVANCE_RATIO_VARIABLE} as {ratio}, and an "
            "advance ratio is positive: it is the axial distance travelled per "
            "revolution over the diameter. The HAND of the rotation is "
            f"{RPM_SIGN_VARIABLE}, which is where a negative sign belongs."
        )
    reference = case.reference
    diameter = None if reference is None else reference.rotor_diameter
    if diameter is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {ADVANCE_RATIO_VARIABLE} as {ratio} and its "
            "reference carries no rotor diameter, so the ratio names no rotor "
            "speed: J is a ratio against the diameter and n = V / (J D) cannot be "
            "evaluated without it. Add 'rotor_diameter_m' to the reference "
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
    # FOUR DECIMALS, the reference tooling's precision for the derived speed: the recorded
    # 9001 script states SET_MOTION_ROTOR_RPM 1 473.1723 0.0 0.0 (quoted in
    # reports/RPT-040, the reproduction report, from the recorded script)
    # where the unrounded derivation gives 473.17227304, and the run that
    # produced the reference tables turned at the four-decimal value. The scripts arm
    # of GOAL-011 found it as the one difference on that point on 2026-09-03.
    # A ten-thousandth of a rev/min is below anything the solver resolves.
    rpm = round(60.0 * velocity / (ratio * diameter), _DERIVED_RPM_DECIMALS)
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
    ADVANCE_RATIO and RPM, or a ratio with no rotor diameter, is
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


# --- PFS-2025.05: the rotor motion, off the row ------------------------------


def _the_copies_the_sector_stands_for(case: SimCase, script: Script) -> tuple[int | None, str]:
    """Return the copy count a sector row implies, and WHY not (FR-59, FR-61).

    THE COUNT IS THE MESH'S AND IS READ FROM THE MESH. FR-61 draws the
    line and this function stands on it: ``PERIODIC_COPIES`` states what
    the FILE THE ROW OPENS is, a sector of a wheel, while the blade COUNT
    it was also read for belongs to the reference (FR-68). So the count is
    the wheel's blades divided by the blades this file carries, which is
    how many times the slice repeats:

        copies = len(block.families_blades) // (those the geometry carries)

    The reference 91_LIFTER_SECTOR carries LH and LB_1 of a rotor declared with four
    blade families, so it stands for four copies; the same rotor meshed as
    a half, carrying two of them, stands for two. The first writing of
    this default returned the wheel's four in BOTH cases, because it read
    the reference alone, and that is the SRS and the code saying different
    things about the same key (the architecture lens, 2026-09-10).

    ONE ROTOR ONLY, and deliberately: a sector is a slice of ONE wheel, so
    a row turning several rotors has no single count and is left to state
    one.

    THE SECOND RETURN IS THE REASON, because five different rows reach the
    same None and the refusal used to tell all of them the same thing,
    including one that told a row to do what it had already done (the
    interface lens, 2026-09-10).
    """
    aliases = [
        record.get(MOVING_BC_ALIAS_VARIABLE)
        for record in (case.motions or [])
        if record.get(MOVING_BC_ALIAS_VARIABLE)
    ]
    if not aliases:
        alias = _variable(case, MOVING_BC_ALIAS_VARIABLE)
        aliases = [str(alias)] if alias else []
    named = {str(alias).strip().casefold() for alias in aliases}
    if not named:
        return None, (
            f"Add it to the row's variables, or name the rotor by alias "
            f"({MOVING_BC_ALIAS_VARIABLE}) and let its block's blades say it."
        )
    if len(named) != 1:
        return None, (
            f"This row turns {len(named)} rotors, so there is no single wheel for the "
            "sector to be a slice of; a sector row states one count of its own."
        )
    block = next(
        (rotor for name, rotor in case.rotors.items() if name.casefold() in named),
        None,
    )
    if block is None:
        return None, (
            f"The row names {', '.join(sorted(named))}, which the reference declares as "
            "no rotor, so its blades cannot say the count."
        )
    if not block.families_blades:
        return None, (
            f"The row names {block.alias}, whose reference block lists no "
            "families_blades, so its blades cannot say the count either: add them to "
            "the block, or state the count on the row."
        )
    inventory = {name.casefold() for name in script.entities.labels("boundaries")}
    carried = [name for name in block.families_blades if name.casefold() in inventory]
    if not carried:
        return None, (
            f"The row names {block.alias}, whose blade list "
            f"({', '.join(block.families_blades)}) reaches no boundary of the geometry "
            "this row opens, so the file cannot say how many of itself it stands for. "
            "State the count on the row, or name in the reference the blade families "
            "this mesh actually carries."
        )
    whole, sector = len(block.families_blades), len(carried)
    if whole == sector:
        # THE FILE IS THE WHOLE WHEEL, so it is not a slice of anything and
        # the arithmetic would answer one copy, which passes the positive
        # check above and initializes a full mesh as a sector of itself. A
        # row that means a half MODEL rather than a blade sector lands here
        # too, and it is the row 0.14.0 refused for the missing key (the QA
        # lens, 2026-09-10). Both are questions rather than counts.
        return None, (
            f"The row names {block.alias} and the geometry carries all "
            f"{whole} of its blade families, so the file is the whole wheel "
            "rather than a slice of it and there is nothing for it to stand "
            f"for {whole} of. State {PERIODIC_COPIES_VARIABLE} on the row if "
            "the periodicity is of something else, such as a half model, or "
            f"write {SYMMETRY_VARIABLE} as the mode that mesh actually is."
        )
    if whole % sector:
        return None, (
            f"The row names {block.alias}, whose reference declares {whole} blade "
            f"families while the geometry carries {sector} of them "
            f"({', '.join(carried)}), and {whole} is not a whole number of {sector}. A "
            "periodic sector repeats an exact number of times, so this pair cannot be "
            "one: state the count on the row."
        )
    return whole // sector, ""


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

    THE RULE, and the one sentence this function exists for:
    nowhere in this package should a user work with indices. A row names
    the mesh family and the package makes the link to the solver's
    indices (PFS-2028.00).

    A token resolves in this order, and the order is load-bearing:

    1. an exact boundary label of the opened geometry, so a row can
       always name one surface;
    2. otherwise an ALIAS the row's setup defines in its ``[aliases]``
       table (the design decision of 2026-09-09), whose members resolve as names
       do, a member the file lacks ignored;
    3. otherwise a FAMILY, which is a label with its trailing index
       removed, so ``Blade`` selects every blade the file carries and one
       cell is correct for a sector mesh and a full wheel alike;
    4. otherwise a 1-based POSITION, which still works and now warns,
       naming the surfaces those positions actually select;
    5. otherwise a GROUP of the row's pproc artifact, spelled
       ``g<number>`` (``g4`` is ``[groups]`` entry ``"4"``), resolved to
       the members the geometry carries the way the polar tables resolve
       it, and refused when it names nothing the file holds
       (PFS-2028.00, "MOVING_BOUNDARIES accepts ENTRY group names");
    6. otherwise the token is refused, listing the labels the geometry
       declared.

    The alias sits between the two so a preset's word cannot shadow a
    label the file actually carries. Exact before family is not
    arbitrary either. ``Blade1`` is both a label and
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
        # PFS-2029.12: a NAME against no inventory is refused here, saying
        # why there is no inventory, instead of reaching the script layer
        # as "no labels are registered yet", which blamed the row.
        for token in tokens:
            if not isinstance(_boundary(token), int):
                _refuse_name_without_inventory(case, MOVING_BOUNDARIES_VARIABLE, token)
        return [_boundary(token) for token in tokens]
    resolved: list[int | str] = []
    positional: list[str] = []
    for token in tokens:
        found = _resolve_token(case, token, labels)
        if found:
            resolved.extend(found)
            continue
        read = _boundary(token)
        if isinstance(read, int):
            positional.append(token)
        else:
            members = _group_members(case, token)
            if members is not None:
                resolved.extend(_group_indices(case, token, members, labels))
                continue
            _refuse_name_absent_from_inventory(case, MOVING_BOUNDARIES_VARIABLE, token, labels)
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


#: The spelling of a pproc group in a boundary-citing cell: ``g`` and the
#: group's number, which is the ``[groups]`` key and the ``_g<number>``
#: of the polar table written per group. A bare number is a POSITION and
#: keeps meaning one (sixteen committed goldens carry positional cells),
#: so a group needs a letter the file's own labels do not start a number
#: with.
_GROUP_TOKEN = re.compile(r"^g(\d+)$")


def _resolve_token(case: SimCase, token: str, labels: Mapping[str, int]) -> tuple[int, ...]:
    """Resolve one cited boundary token: an exact label, an alias of the setup, or a family.

    An ADAPTER over :func:`pyflightstream.cases.select_group_members`,
    which is the one home of that precedence (the architecture lens of
    2026-09-09 measured the order written out twice): one token, the
    inventory in its own order, and the row's aliases. The design decision of
    2026-09-09 puts the alias between the exact name and the family, and
    a member the file lacks is ignored. Empty when the token names
    nothing, which the caller refuses for its own key.
    """
    ordered = [name for name, _ in sorted(labels.items(), key=lambda item: item[1])]
    return tuple(labels[name] for name in select_group_members([token], ordered, case.aliases))


def _group_members(case: SimCase, token: str) -> list[int | str] | None:
    """Return the members of the pproc group ``token`` spells as g<number>, or None.

    None means the token is not a group of the row's artifact: either it
    is not spelled as one, or the artifact carries no group of that
    number, and the caller refuses it as a name the inventory lacks.
    """
    match = _GROUP_TOKEN.match(token)
    if match is None or case.pproc is None:
        return None
    number = int(match.group(1))
    for key, members in case.pproc.groups.items():
        if str(key).strip().isdigit() and int(key) == number:
            return list(members)
    return None


def _group_indices(
    case: SimCase, token: str, members: Sequence[int | str], labels: Mapping[str, int]
) -> list[int]:
    """Resolve one pproc group's members against the inventory, as the polar tables do.

    The names go through :func:`pyflightstream.cases.select_group_members`
    over the inventory's labels: an EMPTY group is every boundary of the
    file (the design decision of 2026-09-09), a member the geometry does not
    carry is left out, which is the artifact's own rule (one artifact
    serves a wing-body and an isolated rotor), and an alias of the
    setup is its members; a position passes through. A group that
    resolves to NOTHING is refused naming
    the group, its members, the file and its inventory, because a motion
    over no boundary is the silent no-op the rule of 2026-09-08 forbids.
    """
    ordered = [name for name, _ in sorted(labels.items(), key=lambda item: item[1])]
    indices = [member for member in members if isinstance(member, int)]
    indices.extend(labels[name] for name in select_group_members(members, ordered, case.aliases))
    if indices:
        return sorted(set(indices))
    declared = _declared_labels(labels)
    spelled = ", ".join(repr(member) for member in members) or "nothing, meaning every family"
    raise ScriptReferenceError(
        f"case {case.sim_id!r} states {MOVING_BOUNDARIES_VARIABLE} with {token!r}, group "
        f"{token[1:]} of {_artifact_of(case)}, whose members are {spelled}, "
        f"and {_inventory_source(case)} "
        f"declares none of those names or families; it declares {declared}. Name a group "
        "written for this geometry, or write the names the file carries."
    )


def _artifact_of(case: SimCase) -> str:
    """Name the row's pproc artifact for a message, with its file where the id is known."""
    if case.pproc_id:
        return f"the pproc artifact {case.pproc_id!r} (inputs/pproc/{case.pproc_id}.toml)"
    return "the row's pproc artifact"


def _declared_labels(labels: Mapping[str, int]) -> str:
    """Return the declared labels in inventory order, quoted, for a message."""
    return ", ".join(repr(name) for name, _ in sorted(labels.items(), key=lambda item: item[1]))


def _refuse_a_pproc_the_geometry_shares_no_name_with(case: SimCase, script: Script) -> None:
    """Refuse a pproc artifact none of whose cited names the opened geometry carries.

    PFS-2028.00, the RED of RPT-044: a group citing the mesh solid name
    ``Wing`` against a file whose inventory carries ``MainWing`` only
    planned READY, because a steady row's groups are resolved at products
    time, after the seat is spent, where a group none of whose families
    is in the loads table sums to zero. That is the case of a boundary
    renamed in the solver before the save: the new name is the file's
    and the mesh solid's resolves nothing.

    WHAT IS REFUSED IS THE ARTIFACT AND THE GEOMETRY SHARING NO NAME, not
    a member missing from one group. The artifact is written once for a
    study and shared by rows opening different geometries (the tier-3
    ``p002`` is ``Wing``, ``Body`` and ``Base`` and serves the wing rows
    and the body rows alike), so a family the file lacks is left out by
    design, per group and per plot entry, and a group summing to zero on
    the wing rows is what the reference products carry for the body groups of a
    wing polar. An artifact that cites a POSITION resolves by construction.
    With no inventory declared there is nothing to check against, which
    is the permissive state FR-30c licenses. An EMPTY group is every
    family and resolves by construction (the design decision of 2026-09-09) and
    is passed over rather than ending the check. A word is resolved as
    every boundary-citing cell resolves it, exact name then alias then
    family, and the message cites the word THE FILE WRITES, not what an
    alias expands to.
    """
    pproc = case.pproc
    if pproc is None or not pproc.groups:
        return
    labels = script.entities.labels("boundaries")
    if not labels:
        return
    cited: list[str] = []
    for members in pproc.groups.values():
        if not members:
            # Every family, which resolves by construction; the OTHER
            # groups of the same artifact are still read (the interface
            # lens of 2026-09-09: this returned from the function and
            # disabled the guard for the whole file).
            continue
        for member in members:
            if isinstance(member, int):
                return
            if str(member) not in cited:
                cited.append(str(member))
    if not cited or any(_resolve_token(case, name, labels) for name in cited):
        return
    raise ScriptReferenceError(
        f"case {case.sim_id!r} names {_artifact_of(case)}, whose groups cite "
        f"{', '.join(repr(name) for name in cited)}, and {_inventory_source(case)} declares "
        f"none of those names or families; it declares {_declared_labels(labels)}. Every "
        "polar table of this row would sum nothing. A boundary renamed in the solver "
        "before the save carries its new name in the saved file and the mesh solid's name "
        "resolves nothing (RPT-044): write the names the file carries, or name the "
        "artifact written for this geometry."
    )


def _inventory_source(case: SimCase) -> str:
    """Say where this case's boundary inventory was read from, for a message."""
    file_name = PurePath(str(case.geometry)).name
    if case.inventory is not None:
        return f"the sidecar {PurePath(str(case.geometry)).stem}.boundaries.toml beside {file_name}"
    return f"the mesh block of {file_name}"


def _refuse_name_absent_from_inventory(
    case: SimCase, key: str, token: str, labels: Mapping[str, int]
) -> None:
    """Refuse a boundary name the declared inventory lacks, naming the inventory read."""
    groups = ""
    if key == MOVING_BOUNDARIES_VARIABLE and case.pproc is not None and case.pproc.groups:
        numbers = ", ".join(f"g{number}" for number in case.pproc.groups)
        groups = f", or a group of {_artifact_of(case)} as {numbers}"
    if key == MOVING_BOUNDARIES_VARIABLE and _GROUP_TOKEN.match(token):
        # The token is spelled as a GROUP, so the cause is the artifact and
        # not the geometry (the release review of 2026-09-09).
        if case.pproc is None:
            raise ScriptReferenceError(
                f"case {case.sim_id!r} states {key} with {token!r}, a group spelling, and "
                "names no PPROC artifact, so it resolves to no group. Name the artifact "
                "in the PPROC column, or write a boundary name of "
                f"{_inventory_source(case)}: {_declared_labels(labels)}."
            )
        raise ScriptReferenceError(
            f"case {case.sim_id!r} states {key} with {token!r}, a group spelling, and "
            f"{_artifact_of(case)} carries no group of that number; it carries "
            f"{', '.join(f'g{n}' for n in case.pproc.groups) or 'no group'}. Write one of "
            f"those, or a boundary name of {_inventory_source(case)}: {_declared_labels(labels)}."
        )
    raise ScriptReferenceError(
        f"case {case.sim_id!r} states {key} with {token!r}, and {_inventory_source(case)} "
        f"declares no boundary of that name or family; it declares "
        f"{_declared_labels(labels)}. Write one of those, or a family name (the label "
        f"without its trailing number) to select every member the file carries{groups}."
    )


def _refuse_name_without_inventory(case: SimCase, key: str, token: str) -> None:
    """Refuse a boundary name when no inventory could be declared, saying why.

    PFS-2029.12. Three states leave the inventory undeclared and each is
    the file's, not the row's: the case opens no geometry; the geometry
    carries no mesh block, which is what a raw mesh and a placeholder
    are; or the block could not be read and was warned about at OPEN.
    The reader is re-run here, once and cheaply, because the refusal
    has to say which of the three it is.
    """
    if case.geometry is None:
        raise ScriptReferenceError(
            f"case {case.sim_id!r} states {key} with {token!r}, and the case opens no "
            "geometry, so there is no boundary inventory to read the name from. Name a "
            f"geometry in the row ({GEOMETRY_VARIABLE}), or cite positions."
        )
    file_name = PurePath(str(case.geometry)).name
    try:
        names = boundary_names(case.geometry)
    except MeshReadError as unreadable:
        raise ScriptReferenceError(
            f"case {case.sim_id!r} states {key} with {token!r}, and the boundary "
            f"inventory of {file_name} could not be read: {unreadable} No name can "
            "resolve until the file reads."
        ) from unreadable
    if not names:
        raise ScriptReferenceError(
            f"case {case.sim_id!r} states {key} with {token!r}, and {file_name} carries no "
            "mesh block, so no boundary name can be read from it. A saved simulation "
            "(.fsm) carries the block; a file that does not can state its names in "
            f"{PurePath(file_name).stem}.boundaries.toml beside it (docs/mesh-inputs.md), "
            "or the row can cite positions."
        )
    raise ScriptReferenceError(
        f"case {case.sim_id!r} states {key} with {token!r}, and every name in the mesh "
        f"block of {file_name} is used more than once, so none of them can select a "
        "surface. Cite positions for this file."
    )


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
        refused by the cell the user typed rather than by the
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


# --- PFS-2015.04: the windows the run record carries for the products stage ---
#
# The reductions reach the campaign products through the workflow (the rule
# of 2026-09-08): the run stage resolves the windows off the ROW, where the
# clock and the blade count are stated, writes them on the run record, and
# the products stage reads the record alone, as it reads everything else.
# This is the consumer :meth:`ExportWindow.record` waited for since 0.8.1.

#: The three reductions the products stage writes beside the plots table,
#: in the order they are written. Raw is the plots table itself.
REDUCTION_NAMES: tuple[str, ...] = ("time_average", "phase_locked", "per_blade")

#: The run record key under which a row's PER-ROTOR reduction windows live
#: (FR-68), alias to that rotor's block. A NAME AND NOT A LITERAL, because
#: the key spans two layers: this module writes it and
#: :mod:`pyflightstream.post.products` reads it, and a string typed twice
#: in two layers is a contract nothing states (the architecture lens,
#: 2026-09-10).
ROTORS_KEY = "rotors"

#: The reductions that are PER ROTOR, and therefore the ones a per-rotor
#: block carries. The time average is not among them: it is one window of
#: the whole run, whatever turns in it.
PER_ROTOR_REDUCTIONS: tuple[str, ...] = ("phase_locked", "per_blade")

#: The two run types whose points carry a time history, and therefore the
#: only ones a reduction applies to.
_UNSTEADY_RECIPES = ("unsteady", "unsteady_rotor")


def _passages(window: tuple[int, int], period: int) -> list[tuple[int, int]]:
    """Cut an inclusive step window into successive passages of ``period`` steps.

    The arithmetic of :func:`pyflightstream.post.unsteady.passage_windows`
    on a window rather than on a series, so the two agree: from the first
    step forward, a trailing partial passage dropped rather than averaged
    against a shorter one.
    """
    first, last = window
    windows: list[tuple[int, int]] = []
    start = first
    while start + period - 1 <= last:
        windows.append((start, start + period - 1))
        start += period
    return windows


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
    passages = _passages(span, period)
    if passages:
        entry["phase_locked"] = {
            "windows": [list(item) for item in passages],
            "period_steps": period,
            "window_from": (
                f"the row's window cut into blade passages of {alias}, {period} steps each"
            ),
        }
    else:
        entry["phase_locked"] = {
            "skipped": (
                f"the window {span[0]} to {span[1]} holds {span[1] - span[0] + 1} steps, "
                f"fewer than one blade passage of {alias}, which is {period} steps"
            )
        }
    per_blade = [
        (
            last_step - (blades - index) * period + 1,
            last_step - (blades - 1 - index) * period,
        )
        for index in range(blades)
    ]
    if per_blade[0][0] < 1:
        entry["per_blade"] = {
            "skipped": (
                f"the run is {last_step} steps and {alias} has {blades} blades of "
                f"{period} steps each, needing {blades * period}, so the run holds no "
                "complete revolution of it to split by blade"
            )
        }
    else:
        entry["per_blade"] = {
            "windows": [list(item) for item in per_blade],
            "period_steps": period,
            "window_from": (
                f"the last revolution of {alias}, one window of {period} steps per blade, "
                f"{blades} blades"
            ),
        }
    return entry


def reduction_windows(case: SimCase) -> dict[str, object] | None:
    """Resolve the windows of every applicable reduction off one row, for its record.

    The window is the one the row states. Where the row states an export
    window (``WINDOW_DEGREES``, ``WINDOW_STEPS`` or ``WINDOW_REVOLUTIONS``)
    that is the time-average window, as :class:`ReductionPlan` already
    holds (one window, not two). Where it states none, a rotor row states
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

    IT NEVER RAISES for a row the builder would refuse. The record is
    built before the script, so a refusal here would abort the campaign in
    place of the ``FAILED_SCRIPT`` record the builder writes; the reason
    lands on every reduction instead, and the products stage records it.

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
    ...                "WINDOW_DEGREES": "90"},
    ... )
    >>> plan = reduction_windows(case)
    >>> plan["time_average"]["windows"], plan["per_blade"]["period_steps"]
    ([[596, 720]], 125)
    >>> plan["per_blade"]["windows"][-1]
    [596, 720]
    """
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

    # THE TIME-AVERAGE WINDOW: stated, else the last revolution, else the run.
    stated = {
        key: value
        for key in (WINDOW_DEGREES_VARIABLE, WINDOW_STEPS_VARIABLE, WINDOW_REVOLUTIONS_VARIABLE)
        if (value := _variable(case, key)) is not None
    }
    try:
        if stated:
            window = ExportWindow.from_case(case)
            span = window.window_steps()
            key, value = next(iter(stated.items()))
            window_from = f"the export window the row states: {key} {value}, {window.steps} steps"
        elif revolution is not None:
            span = (max(last_step - revolution + 1, 1), last_step)
            window_from = (
                f"the last revolution of the run, {revolution} steps: the row states its "
                f"clock as {stepping.stated_form} and no WINDOW_* key"
            )
        else:
            span = (1, last_step)
            window_from = (
                "the whole run: the row states DELTA_TIME and TIME_ITERATIONS and no "
                "WINDOW_* key, and nothing shorter is stated"
            )
    except CampaignConfigError as error:
        return _every_reduction_skipped(rotor, str(error))
    plan: dict[str, object] = {
        "time_iterations": last_step,
        "steps_per_revolution": per_revolution,
        "blades": None,
        "time_average": {"windows": [list(span)], "window_from": window_from},
    }
    if not rotor:
        return plan

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

    passages = _passages(span, period)
    if passages:
        plan["phase_locked"] = {
            "windows": [list(item) for item in passages],
            "period_steps": period,
            "window_from": f"{window_from}, cut into blade passages of {period} steps",
        }
    else:
        plan["phase_locked"] = {
            "skipped": (
                f"the window {span[0]} to {span[1]} holds {span[1] - span[0] + 1} steps, "
                f"fewer than one blade passage of {period} steps, so no complete passage "
                "can be averaged"
            )
        }
    # One window per blade over the LAST complete revolution, contiguous
    # and ending at the run's last step: :meth:`ReductionPlan.blade_windows`.
    per_blade = [
        (
            last_step - (blades - index) * period + 1,
            last_step - (blades - 1 - index) * period,
        )
        for index in range(blades)
    ]
    if per_blade[0][0] < 1:
        plan["per_blade"] = {
            "skipped": (
                f"the run is {last_step} steps and {blades} blades of {period} steps each "
                f"need {blades * period}, so it holds no complete revolution to split "
                "by blade"
            )
        }
    else:
        plan["per_blade"] = {
            "windows": [list(item) for item in per_blade],
            "period_steps": period,
            "window_from": (
                f"the last revolution of the run, one window of {period} steps per blade, "
                f"{blades} blades"
            ),
        }
    return plan


# --- the builders -------------------------------------------------------------


def _angle(case: SimCase, axis: str) -> float:
    """Return the incidence or the sideslip the row states, in degrees (FR-69).

    THE POINT FIRST, THEN THE ROW, THEN ZERO. A swept angle is the
    point's, which is what it has always been. An angle the row states in
    its FLIGHT_CONDITION and does not sweep is the row's, and until this
    release there was nowhere to write one: a row sweeping the advance
    ratio reached the solver at incidence zero, and the only record of the
    incidence was that nobody had written one (measured 2026-09-09 while
    reading the reference p001).

    THE ROW-STATED ANGLE IS USUALLY IN THE POINT ALREADY, and this
    function is what answers when it is not. The point's coordinates are
    run IDENTITY, so a held angle written in FLIGHT_CONDITION joins every
    point of the sweep, and a row spelled `ALPHA:sweep, BETA:0.0` tags its
    points exactly as the paired `AL/BE` row it was upgraded from did (see
    `SweepAxis.held`). What reaches the row and not the point is the
    advance ratio a row holds, and an angle written among the free
    variables rather than in the cell.
    """
    if axis in case.point:
        return float(case.point[axis])
    stated = _variable(case, ALPHA_VARIABLE if axis == "alpha" else BETA_VARIABLE)
    return 0.0 if stated is None else float(stated)


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
            f"resolved to is {case.geometry!r}. A mesh carries no boundary conditions, "
            "and 0.12.0 is the release that defines them for a mesh cell (PFS-2029.09.03)."
        )
    # THE INITIALISATION FLAG IS ALWAYS STATED (PFS-2030.03.01). A saved
    # simulation may carry an initialised solver, and loading it would start
    # the run from a state the row never declared; the reference scripts wrote DISABLE
    # on every open, and a preset that wants the stored state says so.
    load = case.solver.load_solver_initialization
    script.emit("OPEN", case.geometry, "ENABLE" if load else "DISABLE")
    _declare_boundaries(case, script)
    # EVERY BOUNDARY-CITING SURFACE OF THE ROW IS JUDGED HERE, at plan
    # time, against the inventory just declared (PFS-2028.00): the pproc
    # groups below, the base regions next, and the moving boundaries,
    # plots and sections where each builder resolves them.
    _refuse_a_pproc_the_geometry_shares_no_name_with(case, script)
    _detect_base_regions(case, script)


def _base_region_families(case: SimCase) -> list[str]:
    """Return the families the base-region autodetect may consider: row first, then pproc."""
    declared = _variable(case, BASE_REGIONS_VARIABLE)
    if declared is not None:
        return [token.strip() for token in str(declared).split(",") if token.strip()]
    if case.pproc is not None:
        return list(case.pproc.base_regions)
    return []


def _detect_base_regions(case: SimCase, script: Script) -> None:
    """Emit one DETECT_BASE_REGIONS_BY_SURFACE per boundary of the named families.

    PFS-2029.10, the third sentence of item #6: base region is an
    optional input naming mesh families, so the autodetect runs on those
    surfaces only. Naming none emits nothing, which is every golden and
    every recorded script; AUTO_DETECT_BASE_REGIONS, the whole-geometry
    form, is what a recipe of your own calls, and this package never
    decides on its own which surfaces have a base.
    """
    families = _base_region_families(case)
    if not families:
        return
    labels = script.entities.labels("boundaries")
    indices: list[int] = []
    for family in families:
        if not labels:
            _refuse_name_without_inventory(case, BASE_REGIONS_VARIABLE, family)
        found = _resolve_token(case, family, labels)
        if not found:
            _refuse_name_absent_from_inventory(case, BASE_REGIONS_VARIABLE, family, labels)
        indices.extend(index for index in found if index not in indices)
    for index in sorted(indices):
        script.emit("DETECT_BASE_REGIONS_BY_SURFACE", boundary_index=index)


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
    if case.inventory is not None:
        # PFS-2029.06.03: a sidecar states the order; the file's own block
        # is the authority, and the two disagreeing means one of them was
        # edited since the sidecar was written, which no run may guess at.
        sidecar_name = PurePath(str(case.geometry)).stem + ".boundaries.toml"
        if names and tuple(names) != tuple(case.inventory):
            raise CampaignConfigError(
                f"case {case.sim_id!r}: the mesh block of "
                f"{PurePath(str(case.geometry)).name} lists {', '.join(names)} and the "
                f"sidecar {sidecar_name} lists {', '.join(case.inventory)}; the two "
                "disagree, so no boundary index this run would cite can be trusted. "
                "Rewrite the sidecar from the file with `pyfs-matrix inventory "
                "<geometry>`, overwrite (CLI: --overwrite), if the file is current, or "
                "restage the file "
                "the sidecar describes."
            )
        names = tuple(case.inventory)
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
    names the case and the KEY the user typed rather than the command.

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
    # and not the two CELLS the user typed, which is this module's own
    # rule about where a matrix value is refused. The rule itself is the
    # command's: PERIODIC appends the number of copies (SRC-003 p.337).
    if mode == "PERIODIC" and copies is None:
        # THE PAIR OF FILES ALREADY KNOWS (FR-59, FR-61). The reference
        # declares the wheel's blades one per entry and the geometry
        # carries the ones this mesh holds, so the slice's repeat count is
        # the first divided by the second, and asking the ROW for it again
        # is the second home this release exists to remove. The count
        # stays the MESH's, which is FR-61's line, because the divisor is
        # read from the file the row opens.
        copies, why = _the_copies_the_sector_stands_for(case, script)
        if copies is None:
            raise CampaignConfigError(
                f"case {case.sim_id!r} declares {SYMMETRY_VARIABLE} as {symmetry!r} and "
                f"no {PERIODIC_COPIES_VARIABLE}. A periodic sector is a slice that "
                "stands for a whole number of copies of itself, and the solver cannot "
                "know how many the slice you meshed represents: a four-bladed rotor "
                f"modelled as one 90 degree sector declares "
                f"'{PERIODIC_COPIES_VARIABLE}: 4'. {why}"
            )
    if mode != "PERIODIC" and copies is not None:
        # A row declaring the count and NO symmetry at all is the likely
        # shape of this mistake, so it is spelled out rather than
        # reported as "SYMMETRY as None", which names a value the user
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


def _moment_frame(case: SimCase, script: Script) -> int | None:
    """Create the MRP frame at the reference's moment point, returning its index.

    PFS-2030.03.02. The loads table the solver writes names the frame the
    loads were analysed in, and the reference scripts say MRP; a run with no moment point
    creates nothing and the solver's reference frame stands, as before.
    Emitted right after OPEN so that, with the rotor frame after it,
    the frame indices come out as the reference scripts numbered them: MRP 2,
    ROTOR_MRP 3.
    """
    reference = case.reference
    if reference is None or reference.moment_point_m is None:
        return None
    return helpers.coordinate_frame(
        script,
        name="MRP",
        origin=reference.moment_point_m,
        x_axis=(1.0, 0.0, 0.0),
        y_axis=(0.0, 1.0, 0.0),
        label="MRP",
    )


#: THE RADICAL OF A ROTOR THAT HAS NO ALIAS. Only one path produces one: a
#: matrix converted with no workspace, where `to_campaign` reads the row and
#: never an artifact, so there is no block to take a name from. It keeps the
#: shape every other rotor frame name has rather than reviving the
#: package-level PROP_MRP, which named one propulsor because a reference
#: described one.
UNNAMED_ROTOR_RADICAL = "ROTOR"


def _the_rotor_a_flat_row_turns(case: SimCase) -> RotorBlock | None:
    """Return the one rotor a row with no MOTIONS list turns, or None.

    A row that states MOTIONS says which rotor each record moves and never
    reaches here. A row without one has to be told, and the reference is
    what tells it: exactly one rotor block means exactly one answer.

    IT ANSWERS None RATHER THAN RAISING when the reference declares
    several. Every run type asks this, including the ones that turn
    nothing, so a refusal here fired on a steady row whose reference
    happened to describe a twin. The refusal belongs to the run that
    actually needs a hub, and :func:`_refuse_an_unanswered_hub` is where
    it lives.
    """
    # `case.rotors`, NOT `case.reference`. The blocks are lifted onto the
    # case when the matrix resolves, and a case built directly carries them
    # with no reference beside them; asking for the reference here made the
    # helper answer None for every hand-built rotor case, which is a guard
    # that refuses what it was written to accept.
    if len(case.rotors) != 1:
        return None
    return next(iter(case.rotors.values()))


def _refuse_an_unanswered_hub(case: SimCase) -> None:
    """Refuse a rotor run that states no MOTIONS against a several-rotor reference.

    Raises
    ------
    CampaignConfigError
        Which rotor turns is unanswered. Naming the declared ones is the
        useful half of the refusal.
    """
    if case.motions or len(case.rotors) <= 1:
        return
    declared = ", ".join(sorted(case.rotors))
    raise CampaignConfigError(
        f"case {case.sim_id!r} runs a rotor and states no {MOTIONS_VARIABLE}, and the "
        f"reference declares more than one rotor ({declared}). Which of them turns is "
        f"what a {MOTIONS_VARIABLE} list answers: write one record per rotor that "
        f"moves, each stating {MOVING_BC_ALIAS_VARIABLE}."
    )


def _the_flat_frame_name(case: SimCase) -> str:
    """Return the citable name of the frame a row with no MOTIONS turns about.

    ``<ALIAS>_SMRP`` when the rotor is declared, which is every row that
    reached the builder through a workspace, and ``ROTOR_SMRP`` for the
    converted row that carries no block.
    """
    block = _the_rotor_a_flat_row_turns(case)
    radical = block.alias if block is not None else UNNAMED_ROTOR_RADICAL
    return f"{radical}_SMRP"


def _flat_rotor_frames(case: SimCase, index: int | None) -> dict[str, int | None]:
    """Name the flat row's rotor frame the way every other rotor frame is named.

    Returns the one entry ``{"<ALIAS>_SMRP": index}``, or nothing when the
    row turns no rotor. It replaces the literal ``ROTOR_MRP`` key that
    every frame table carried at 0.14.0, when one reference meant one
    propulsor and one name could stand for it.
    """
    return {_the_flat_frame_name(case): index}


def _rotor_frame(case: SimCase, script: Script) -> int | None:
    """Create the hub frame of the rotor a flat row turns, named for its alias.

    THERE IS NO GLOBAL ROTOR FRAME since 0.15.0 (decision of 2026-09-10). A
    reference declares one block per rotor and every frame takes that
    rotor's alias as its radical, so the frame this creates is
    ``<ALIAS>_SMRP``, the same name a MOTIONS record's hub carries. One
    rotor named two ways was the 0.14.0 shape, and it only worked because
    a reference described one propulsor.

    A row stating ROTOR_ORIGIN still overrides the block's hub.
    """
    block = _the_rotor_a_flat_row_turns(case)
    stated = _variable(case, ROTOR_ORIGIN_VARIABLE)
    if stated is not None:
        origin = _origin(case)
    elif block is not None:
        origin = block.origin
    elif case.reference is not None and case.reference.rotor_position_m is not None:
        origin = case.reference.rotor_position_m
    else:
        return None
    return helpers.coordinate_frame(
        script,
        name=_the_flat_frame_name(case),
        origin=origin,
        x_axis=(1.0, 0.0, 0.0),
        y_axis=(0.0, 1.0, 0.0),
        label="rotor",
    )


def _significant_digits(case: SimCase, script: Script) -> None:
    """Emit SET_SIGNIFICANT_DIGITS where the preset states it (PFS-2030.03.04).

    A setup-phase command, so it sits with the frames and before the
    free stream; the solver's own default prints four decimals and the reference
    presets ask for seven, which is the difference between the reference tables
    and a table that cannot be compared with them.
    """
    digits = case.solver.significant_digits
    if digits is not None:
        script.emit("SET_SIGNIFICANT_DIGITS", digits)


def _vorticity_indices(case: SimCase, script: Script) -> list[int] | None:
    """Resolve the preset's vorticity-drag FAMILIES through the opened inventory.

    PFS-2030.03.03. A family the geometry does not carry is left out, as
    the reference driver filtered the preset's list to the configuration it opened;
    a list that resolves to nothing is refused, because an empty selection
    would be read by the solver as the default and the preset asked for
    something else.
    """
    families = case.solver.vorticity_drag_families
    if families is None:
        return None
    chosen: list[int] = []
    absent: list[str] = []
    for name in families:
        try:
            chosen.append(script.resolve_boundary(name, context="vorticity_drag_boundaries"))
        except PyflightstreamError:
            absent.append(name)
    if not chosen:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the preset names vorticity drag boundaries "
            f"{', '.join(families)} and the opened geometry carries none of them "
            f"(absent: {', '.join(absent)}), so the selection would be empty. Name "
            "families the geometry carries, or drop the key so the solver integrates "
            "surface pressure on every boundary."
        )
    return sorted(chosen)


def _analysis(case: SimCase, script: Script, frame: int | None) -> None:
    """Point the analysis at the MRP frame, once the solver has started.

    The loads frame and the moments model are analysis-phase commands, so
    they follow START_SOLVER in this package's phase order; the solver
    applies them to the analysis that follows either way, and the reference
    scripts wrote them before the start with the same effect on the table.
    """
    if frame is None:
        return
    helpers.analysis_setup(script, loads_frame=frame, moments_model="PRESSURE")


def _refuse_sideslip_under_mirror(case: SimCase) -> None:
    """Refuse a nonzero sideslip under mirror symmetry, which the solver runs at zero.

    MEASURED on 26.120 (pfs0130 row 4207, 2026-09-09): a script stating
    ``SOLVER_SET_SIDESLIP -4.0`` before ``INITIALIZE_SOLVER`` and
    ``SYMMETRY MIRROR`` after it ran to completion with the log reading
    "Symmetry is mirror." and then "Side-slip angle (Deg): .000", and the
    loads export printing .000 too; the point was recorded
    FAILED_INCOMPLETE_OUTPUT because the export was evidence of another
    operating point than the row requested. A mirrored half model is a
    valid model of the full one only while the free stream lies in the
    symmetry plane; a nonzero sideslip takes it out of that plane, and the
    solver runs at zero without a word. A seat spent on that is a seat
    spent on a case the row did not state, so the row is refused before
    the solver settings are emitted, naming the cell to change
    (PFS-2005.09); the geometry and frame lines above it are already in
    the script, which the dry run discards.
    """
    beta = _angle(case, "beta")
    symmetry = _variable(case, SYMMETRY_VARIABLE)
    if symmetry is not None and symmetry.upper() == "MIRROR" and beta != 0.0:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states a sideslip of {beta:+.4f} deg at a point under "
            f"{SYMMETRY_VARIABLE}: MIRROR. A mirrored half model is a valid model of the full one "
            "only while the free stream lies in the symmetry plane; a nonzero sideslip takes it "
            "out of that plane, and the solver runs at zero sideslip whatever the script states "
            "(measured on 26.120: the log and the export print .000). Sweep the sideslip on a "
            f"full geometry with {SYMMETRY_VARIABLE}: NONE, or keep the sideslip at 0 under MIRROR."
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
    # SIDESLIP, THE REFERENCE VELOCITY AND THE VORTICITY FAMILIES ARE ALWAYS
    # STATED where the case can state them (PFS-2030.03.01, .03.03): the reference
    # scripts set the sideslip even at zero and the reference velocity
    # equal to the free stream, and a setting nobody states is a setting
    # the solver defaults, which is the silence this release removes.
    _refuse_sideslip_under_mirror(case)
    helpers.solver_settings(
        script,
        aoa=_angle(case, "alpha"),
        sideslip=_angle(case, "beta"),
        velocity=_velocity(case),
        ref_velocity=(
            solver.reference_velocity_m_per_s
            if solver.reference_velocity_m_per_s is not None
            else _velocity(case)
        ),
        vorticity_drag_boundaries=_vorticity_indices(case, script),
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
    # SYMMETRY LOADS AS STATED, the design decision of 2026-09-02 (PFS-2028.05): an
    # init-phase setting, emitted alone here as the helper asks; an absent
    # key emits nothing, so a preset written before this release is silent
    # exactly as it was.
    symmetry_loads = _row_symmetry_loads(case, solver.symmetry_loads)
    if symmetry_loads is not None:
        helpers.analysis_setup(script, symmetry_loads=symmetry_loads)


def _row_symmetry_loads(case: SimCase, from_setup: bool | None) -> bool | None:
    """Resolve the symmetry-loads flag: the ROW's when it states one (FR-66).

    The design decision of 2026-09-10. Whether the solver reports the loads of the
    meshed SECTOR or of the whole wheel is a per-row choice, because one
    preset serves a sector row and a full-wheel row. A row stating it
    OVERRIDES the preset and warns naming both files and the value used;
    a row stating nothing inherits silently, as every row written before
    this release does.

    The first decision that hour was to refuse both stating it, as the rotor
    speed is refused; it was changed the same hour, and the warning is what
    keeps the override from being silent.
    """
    stated = _variable(case, SYMMETRY_LOADS_VARIABLE)
    if stated is None:
        return from_setup
    word = str(stated).strip().upper()
    # THE ROW'S OWN VOCABULARY, which is the cell a user types: TRUE and
    # FALSE as the presets write them, and the solver's own ENABLE and
    # DISABLE, which is what `resolve_toggle` accepts one layer down.
    value = {"TRUE": True, "FALSE": False, "ENABLE": True, "DISABLE": False}.get(word)
    if value is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {SYMMETRY_LOADS_VARIABLE}: {stated!r}, which is "
            "not a yes or a no. Write true or false, or the solver's own ENABLE or "
            "DISABLE. True means the solver reports the loads of the whole wheel; false "
            "means the loads of the sector that was meshed."
        )
    if from_setup is not None and from_setup != value:
        warnings.warn(
            f"case {case.sim_id!r} states {SYMMETRY_LOADS_VARIABLE}: {value} and its setup "
            f"preset states {from_setup}. The ROW wins, and the run reports the loads of "
            f"{'the whole wheel' if value else 'the meshed sector'}.",
            PyflightstreamWarning,
            stacklevel=2,
        )
    return value


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
    steps = case.solver.wake_termination_steps
    if revolutions is not None and steps is not None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} inherits a wake termination in revolutions "
            f"({revolutions}) and in time steps ({steps}) from its solver preset, and "
            "the two can only disagree. State one."
        )
    if revolutions is None:
        return steps
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
    users were told the value "takes no decimal point" about
    characters containing no decimal point. A refusal whose whole job is
    to point at the cell someone typed cannot be wrong about what they
    typed.
    """
    if _DECIMAL.match(text):
        return "decimal"
    if any(character in text for character in r"/\.") or text.endswith("}"):
        return "name"
    return "neither"


# --- PFS-2029.07.03: the pproc artifact's definitions reach the script ------


def _inventory(script: Script) -> list[str]:
    """Return the opened geometry's boundary labels in inventory order, or nothing."""
    labels = script.entities.labels("boundaries")
    return [name for name, _ in sorted(labels.items(), key=lambda item: item[1])]


#: The frames a builder created, by the name a pproc entry cites: MRP and
#: ROTOR_MRP to an index or None, BLADE_AXIS to one index per blade family.
Frames = Mapping[str, int | None | Mapping[str, int]]


#: The row variable the command line writes its choice into, so the reader
#: can honour it without the cases layer knowing a command line exists
#: (PFS-2035.13, the design of 2026-09-10).
IGNORE_MISSING_FAMILIES_VARIABLE = "IGNORE_MISSING_FAMILIES"

#: The words that mean yes and the words that mean no, in the ONE place
#: both readers ask. The command line and the row variable used to carry a
#: copy each, in two layers, with nothing asserting the two agreed (the
#: architecture lens of 2026-09-10).
CHOICE_WORDS: Mapping[str, bool] = MappingProxyType(
    {"true": True, "yes": True, "1": True, "false": False, "no": False, "0": False}
)


def read_a_choice(word: object, *, context: str) -> bool:
    """Read a yes-or-no word, REFUSING anything outside the vocabulary.

    A word this does not know is an error and never a default. The
    permissive reading, where everything but three spellings means yes, has
    no failure mode: `--ignore-missing-families off` would have given the
    user the SKIP, which is the silence they passed the flag to escape, on
    a run that planned green and said nothing. That is the same shape as
    the incident `pyflightstream.script.toggles` records in its own module
    docstring, and this reader is built the way that one is.

    Parameters
    ----------
    word : object
        `true`, `yes`, `1`, `false`, `no` or `0`, in any case, with
        surrounding whitespace ignored. A bool passes through, so a Python
        caller may write the value it means.
    context : str
        What is being read, quoted in the refusal, so the message names the
        flag or the row key the user actually wrote.

    Raises
    ------
    ValueError
        If the word is outside the vocabulary. The message lists both
        halves of it, because a user who wrote the wrong word for NO needs
        to see the right words for NO beside the ones for yes.
    """
    if isinstance(word, bool):
        return word
    text = str(word).strip().casefold()
    if text in CHOICE_WORDS:
        return CHOICE_WORDS[text]
    yes = ", ".join(name for name, state in CHOICE_WORDS.items() if state)
    no = ", ".join(name for name, state in CHOICE_WORDS.items() if not state)
    raise ValueError(
        f"{context}: {str(word)!r} is not a yes or a no. Write one of {yes} for yes, or "
        f"one of {no} for no. A word this reader does not know is refused rather than "
        "read as the default, because reading it as the default would give you the "
        "behaviour you were trying to turn off and say nothing about it."
    )


def _ignore_missing_families(case: SimCase) -> bool:
    """Whether a family the mesh lacks is skipped (the default) or refuses.

    A PER-INVOCATION CHOICE and not a property of the row: the same matrix
    planned across a wing and a rotor wants the skip, and planned against
    the one geometry that should carry everything wants the refusal. The
    command line writes it onto the case's variables, so this layer reads a
    variable like any other and does not learn that a command line exists.

    Absent, it is TRUE, which is what every row written before this flag
    means and what PFS-2035.01 states.
    """
    stated = _variable(case, IGNORE_MISSING_FAMILIES_VARIABLE)
    if stated is None:
        return True
    try:
        return read_a_choice(
            stated, context=f"case {case.sim_id!r}: {IGNORE_MISSING_FAMILIES_VARIABLE}"
        )
    except ValueError as error:
        raise CampaignConfigError(str(error)) from None


#: The words a families entry may write that name no set of their own, so
#: a reader asking "does this name anything the geometry carries" would be
#: asking the wrong question of them. `all` is the command's own
#: every-boundary form and the two `each` words are one emission per family.
_WORDS_THAT_NAME_NO_SET = frozenset({"all", "each", "each_blade"})


def _refuse_what_the_geometry_does_not_carry(
    case: SimCase,
    selection: str | Sequence[str],
    inventory: Sequence[str],
    aliases: Mapping[str, Sequence[str]],
    expanded: Sequence[Sequence[str]],
    what: str,
    is_blade: Callable[[str], bool],
) -> None:
    """Say what the skip left out, for a run that asked to hear it (PFS-2035.13).

    THREE SILENCES, because that is how many there are and the flag is
    named after all of them. An ALIAS MEMBER no boundary answers is dropped
    inside the resolver, so an alias of six members over a mesh that
    carries five still selects five and nothing says which one went
    (PFS-2035.01). A LIST MEMBER that names nothing is dropped the same
    way, and worse, because a list aggregates into one set that is
    non-empty as soon as ONE member resolves: `["WING", "BLADE_1"]` over a
    mesh with no blade selects the wing and passes. And an ENTRY that
    selects nothing at all is left out of the products
    (PFS-2029.07.04). The first two are reported before the third, because
    they are the ones a PASSING entry hides.

    Neither is a defect at the default. The whole point of the silence is
    that one artifact serves a wing-body and an isolated rotor; what this
    function serves is the other intent, where the user believes THIS
    geometry carries every family the artifact names and wants to hear
    about it when it does not.
    """
    cited = [selection] if isinstance(selection, str) else [str(item) for item in selection]
    missing: list[str] = []
    for token in cited:
        # AN ALIAS IS ASKED FIRST, and it answers with the alias that
        # DECLARES each absent member rather than the word the entry wrote,
        # because on a nested alias those are different and the declaring
        # one is the table row the user has to edit (the interface lens).
        absent = alias_members_missing(token, inventory, aliases)
        if absent:
            missing.extend(
                f"{owner!r} names {member!r}"
                for owner, member in absent
                if f"{owner!r} names {member!r}" not in missing
            )
            continue
        # NOT AN ALIAS, so it is a boundary or a family, and a MEMBER of a
        # list has to be judged on its own. A list aggregates into one set
        # that is non-empty as soon as ONE member resolves, so a misspelled
        # member beside a good one passed in silence with the refusal asked
        # for; the QA lens measured it with a mutant that survived every
        # case in the module (2026-09-10).
        if token.strip().casefold() in _WORDS_THAT_NAME_NO_SET:
            continue
        if not select_families(token, inventory, is_blade, aliases=aliases):
            entry = f"{token!r} names nothing this geometry carries"
            if entry not in missing:
                missing.append(entry)
    declared = ", ".join(repr(name) for name in inventory) or "no boundary"
    if missing:
        told = "; ".join(missing)
        known = ", ".join(sorted(aliases)) or "none"
        raise CampaignConfigError(
            f"case {case.sim_id!r}: {what} of {_artifact_of(case)} cites what no "
            f"boundary of this geometry answers: {told}. The names this row can cite "
            f"are {known}; the geometry declares "
            f"{declared}. This run was asked for the refusal rather than the "
            "skip: ignore_missing_families (CLI: --ignore-missing-families) was given "
            "as false, so a member the mesh does not carry is an error here and not "
            "the difference between two geometries one reference serves "
            "(PFS-2035.13)."
        )
    if expanded:
        return
    known = ", ".join(sorted(aliases)) or "none"
    raise CampaignConfigError(
        f"case {case.sim_id!r}: {what} of {_artifact_of(case)} selects "
        f"{selection!r}, and this geometry carries no family of it. The names this row "
        f"can cite are {known}; the geometry declares {declared}. This "
        "run was asked for the refusal rather than the skip: ignore_missing_families "
        "(CLI: --ignore-missing-families) was given as false, so a family the mesh "
        "does not carry is an error and not a difference between geometries "
        "(PFS-2035.13)."
    )


def _selected_families(
    case: SimCase,
    selection: str | Sequence[str],
    inventory: Sequence[str],
    is_blade: Callable[[str], bool],
    what: str,
) -> list[list[str]]:
    """Expand one pproc ``families`` entry, warning when it selects nothing.

    The skip itself is the artifact's own rule, and it is what lets one
    file serve a wing-body and an isolated rotor. What the warning adds
    is the difference between a geometry that legitimately carries none
    of those families and a MISSPELLED word, which read alike from the
    script (the interface lens of 2026-09-09): both left the entry out
    and said nothing, and the user met it as a plot that is not in the
    products.
    """
    names = _the_names_a_rotor_answers_to(case)
    expanded = select_families(selection, inventory, is_blade, aliases=names)
    if not _ignore_missing_families(case):
        _refuse_what_the_geometry_does_not_carry(
            case, selection, inventory, names, expanded, what, is_blade
        )
    if not expanded:
        known = ", ".join(sorted(case.aliases)) or "none"
        warnings.warn(
            f"case {case.sim_id!r}: {what} of {_artifact_of(case)} selects "
            f"{selection!r}, and this geometry carries no family of it, so the entry is "
            f"left out. The aliases the row's setup defines are {known}; the geometry "
            f"declares {', '.join(repr(name) for name in inventory) or 'no boundary'}. "
            "That is the artifact's own rule where the geometry simply lacks the "
            "families, and a misspelling reads exactly the same way from here.",
            PyflightstreamWarning,
            stacklevel=2,
        )
    return expanded


def _the_names_a_rotor_answers_to(case: SimCase) -> dict[str, list[str]]:
    """Return the setup's aliases with each rotor's own name added to them.

    A ROTOR'S NAME IS AN ALIAS FOR ITS OWN FAMILIES, which is FR-65's
    sentence "a rotor name in that set is its own union" written where
    both readers can use it. The reference `lifters = ["LIFT_L1", "LIFT_L2"]` lists
    ROTORS rather than families, which is the natural way to write a group
    of rotors and the shape the whole per-rotor economy is for, and its
    members resolved to nothing because a rotor's name was a family name
    to nobody and sat in no alias table (the QA lens, 2026-09-10).

    ONE MAP FOR BOTH PATHS, deliberately. The expanding path and the
    common-frame path read the same words out of the same file, and the
    first fix gave the vocabulary to the expanding one alone: an entry
    written `frame = "MRP", families = ["lifters", "PUSHER"]`, which is
    how the total of the rotors in the moment frame is asked for, then
    selected NOTHING and warned that the geometry carries no family of it.

    The reference table takes precedence, so a study that gives one of these
    names a meaning of its own keeps it.
    """
    return {
        **{
            name: [*block.families_general, *block.families_blades]
            for name, block in case.rotors.items()
        },
        **case.aliases,
    }


def _the_reference_vocabulary(case: SimCase) -> list[str]:
    """Return every family name the reference's rotors declare, in their order.

    THE REFERENCE'S OWN INVENTORY, and deliberately not the mesh's. Which
    rotors an entry reaches is a property of the two FILES, so it must
    give the same answer on a steady row and a rotor row; resolving the
    entry's words against the geometry would make an entry reach a rotor
    on one row and be refused on another, and the refusal below says in so
    many words that it cannot come right on another mesh.
    """
    return [
        family
        for block in case.rotors.values()
        for family in (*block.families_general, *block.families_blades)
    ]


def _rotors_the_entry_cites(
    case: SimCase, families: str | Sequence[str]
) -> list[tuple[str, list[str]]]:
    """Return the rotors an entry reaches and WHAT OF EACH, in the reference's order.

    The second half of each pair is the families the entry cited INSIDE
    that rotor, or an empty list meaning the whole of it, which is what an
    entry naming the rotor itself asks for. Returning only the aliases
    made a partial citation emit the rotor's whole union under the name
    the user wrote: an entry asking for the hub's loads in the rotor frame
    got a plot summing hub AND blades (the QA lens, 2026-09-10).

    A selection reaches a rotor when it names the rotor itself, or when
    its members INTERSECT that rotor's families. Intersect, not
    "are a subset of": an alias spanning four lifters is a subset of no
    single block and so reached NONE of them, which is the opposite of
    what an alias over several rotors is for, and it under-emitted in
    silence because one other token in the same entry matched and stopped
    the refusal from firing. `lifters` naming four lifters reaches four
    rotors and one line of the artifact becomes four emissions, which is
    the whole economy of FR-65: the reference aircraft has nine rotors and the reference
    `[plots]` table has six lines.

    A member may be another alias, and the members are resolved through
    :func:`resolve_alias` so that a nested one is followed to the end
    rather than read as a family name that nothing carries.
    """
    if not case.rotors:
        return []
    wanted = [families] if isinstance(families, str) else list(families)
    # EVERY ROTOR IS WHAT `all` MEANS HERE, and reading it is
    # the answer to a refusal that lied: `frame = "SMRP", families = "all"`
    # is the natural way to write "every rotor, each in its own frame", and
    # it was refused saying the families reach no rotor of the reference,
    # which diagnoses a misspelling. The selectors were simply not read (the
    # interface lens, 2026-09-10). `airframe` still reaches none, and that
    # refusal is true: an airframe has no rotor.
    #
    # THE ALIAS IS ASKED FIRST, exactly as `select_families` asks it. The
    # word `blades` was a SELECTOR that decided what a blade is from a
    # pattern over the family name, and 0.15.0 refuses it; a reference that
    # DECLARES `blades` gives the word a meaning of its own and keeps it,
    # which is the migration the refusal asks a reader to make. Testing the
    # word before the table refused the very file the message tells them to
    # write.
    known_here = _the_names_a_rotor_answers_to(case)
    if any(
        str(token).strip().casefold() == "blades"
        and resolve_alias(str(token).strip(), _the_reference_vocabulary(case), known_here) is None
        for token in wanted
    ):
        warn_a_selector_that_guesses("blades")
        return [(alias, []) for alias in case.rotors]
    if any(str(token).strip().casefold() == "all" for token in wanted):
        return [(alias, []) for alias in case.rotors]
    vocabulary = _the_reference_vocabulary(case)
    known = _the_names_a_rotor_answers_to(case)
    whole: set[str] = set()
    cited: dict[str, list[str]] = {}
    for token in wanted:
        word = str(token).strip()
        folded = word.casefold()
        for name in case.rotors:
            if folded == name.casefold():
                whole.add(name)
        members = resolve_alias(word, vocabulary, known)
        if members is None:
            # NOT AN ALIAS, so it is a boundary or a family name, and it
            # is resolved the same way a member of one would be.
            members = [family for family in vocabulary if _the_same_family(family, word)]
        for name, block in case.rotors.items():
            owns = {
                family.casefold(): family
                for family in (*block.families_general, *block.families_blades)
            }
            inside = [owns[member.casefold()] for member in members if member.casefold() in owns]
            if inside:
                kept = cited.setdefault(name, [])
                kept.extend(family for family in inside if family not in kept)
    reached: list[tuple[str, list[str]]] = []
    for name in case.rotors:
        if name in whole:
            reached.append((name, []))
        elif name in cited:
            reached.append((name, cited[name]))
    return reached


def _the_same_family(family: str, word: str) -> bool:
    """Whether ``word`` names ``family`` exactly or as its family radical."""
    folded, wanted = family.casefold(), word.casefold()
    return folded == wanted or folded.rstrip("0123456789") == wanted


def _and_the_frame_it_turned_from(
    frame: str,
    families: list[str],
    label: str,
    frames: Frames,
) -> list[tuple[str, list[str], str]]:
    """One emission, or TWO when the frame it names was rotated (FR-71).

    The rule of 2026-09-10: "no posproc, se eu indicar um SMRP que foi
    rotacionado, ele escreve os outputs tanto no SMRP quanto no original".
    An entry says which rotor it is about, and the ROW's rotation decides
    whether there are two readings of it, which is the rule FR-65 already
    applies to the frame: the run's own state decides how many emissions
    an entry stands for, never a second entry written by hand.

    THE ORIGINAL IS ASKED OF `frames` AND NEVER ASSUMED. It exists only
    where this row rotated that alias, because that is the only place
    :func:`_keep_the_frame_this_alias_turns_from` created it. A rotor the
    row did not turn doubles nothing, so every artifact written before this
    release emits exactly what it emitted.

    IT DOUBLES A HUB FRAME ONLY. `<ALIAS>_RMRP` and `<ALIAS>_RMRP<k>` turn
    WITH the motion every step of an unsteady run, so "the frame it turned
    from" is not a thing they have; the hub is the one the rotation moved
    once and left there.
    """
    kept = f"{frame}{ORIGINAL_FRAME_SUFFIX}"
    if frames.get(kept) is None:
        return [(frame, families, label)]
    return [(frame, families, label), (kept, families, label)]


def _pproc_emissions(
    case: SimCase,
    frame: str,
    families: str | Sequence[str],
    inventory: Sequence[str],
    is_blade,
    what: str,
    frames: Frames,
    *,
    blades_only: bool = False,
) -> list[tuple[str, list[str], str]]:
    """Return one ``(frame, families, label)`` per emission the entry stands for (FR-65).

    ``blades_only`` is FR-75 and it is set by the SECTIONS path alone. A
    sectional CUT of a whole rotor is not a quantity: the blades lie at
    different azimuths, so one plane through the set crosses each of them
    somewhere different and the station it reports is a station of nothing. A
    rotor's total FORCE is a real quantity, so the plots path leaves it False
    and still emits the rotor beside its blades.

    ONE RULE FOR EVERY POST-PROCESSING ENTRY, which is why this takes a
    frame and a family selection rather than a plot group: a section
    distribution cites the same frame kinds and means the same thing by
    them, and a second implementation of one rule is how the two come to
    disagree.

    THE FRAME DECIDES, which is why there is no `expand` key: a reader who
    has said which frame a quantity is measured in has already said how
    many of it there are.

    * a frame the run creates or the reference declares: ONE emission over
      the whole cited set, and a rotor name in that set is its own union;
    * ``SMRP`` or ``RMRP``: one per ROTOR, in that rotor's own frame,
      labelled with the rotor's alias;
    * ``LOCAL_AXIS``: one per BLADE, in that blade's frame, labelled with
      the blade's family, PLUS one for the rotor's general families, which
      have no local axis of their own and ride the rotor's;
    * ``each``: one per family in the common frame the entry names.
    """
    # THE FRAME SELECTS THIS PATH, not the entry's arity. `each_blade` is
    # also one per blade, and it expands through the FAMILY selector as it
    # did at 0.14.0, over whatever frame the entry names; taking the rotor
    # path for it would ask a 0.14.0 artifact for rotors its reference
    # never declared.
    kind = EXPANDING_FRAMES.get(frame.strip().upper())
    if kind is None:
        return [
            emission
            for selected in _selected_families(case, families, inventory, is_blade, what)
            for emission in _and_the_frame_it_turned_from(
                frame, selected, selected[0] if selected else "", frames
            )
        ]
    rotors = _rotors_the_entry_cites(case, families)
    if not rotors and not case.rotors:
        # A REFERENCE THAT DECLARES NO ROTOR AT ALL is a CONFIGURATION with
        # no rotor, not a misspelling, and the entry is skipped the way an
        # entry whose families the mesh lacks is skipped. This is what lets
        # one post-processing artifact serve a wing, a body and a twin,
        # which is the artifact's whole economy: p001 carries the rotor
        # plots and the wing rows citing it simply do not emit them.
        #
        # The refusal below still fires where the reference DOES declare
        # rotors and the entry reaches none of them, which is the case that
        # cannot come right on another mesh.
        return []
    if not rotors:
        declared = ", ".join(sorted(case.rotors)) or "none"
        aliases = ", ".join(sorted(case.aliases)) or "none"
        raise CampaignConfigError(
            f"case {case.sim_id!r}: {what} of {_artifact_of(case)} is measured in "
            f"{frame}, which is a frame per "
            f"{'rotor' if kind == 'rotor' else 'blade'}, and its families "
            f"{families!r} reach no rotor of the reference. On a frame that expands "
            f"per rotor the families name a ROTOR, an alias whose families one rotor "
            f"owns, or 'all'; the rotors this reference declares are {declared} and "
            f"the aliases are {aliases}. A misspelling reads exactly the same way from "
            "here. That is a writing error rather than a configuration difference: "
            "unlike an entry whose families this geometry simply lacks, it cannot come "
            "right on another mesh."
        )
    carried = {name.casefold() for name in inventory}
    emissions: list[tuple[str, list[str], str]] = []
    placed = {name for name, index in frames.items() if index is not None}
    for alias, inside in rotors:
        block = case.rotors[alias]
        # AN EMPTY `inside` IS THE WHOLE ROTOR, which is what naming the
        # rotor itself asks for; anything else is the part of it the entry
        # actually cited, so an entry asking for the hub gets the hub.
        asked = {family.casefold() for family in inside}
        if kind == "rotor":
            owned = [
                family
                for family in (*block.families_general, *block.families_blades)
                if family.casefold() in carried and (not asked or family.casefold() in asked)
            ]
            if owned:
                emissions.extend(
                    _and_the_frame_it_turned_from(
                        f"{alias}_{frame.strip().upper()}", owned, alias, frames
                    )
                )
            continue
        for number, family in enumerate(block.families_blades, start=1):
            if family.casefold() in carried and (not asked or family.casefold() in asked):
                emissions.append((f"{alias}_RMRP{number}", [family], family))
        general = [
            family
            for family in block.families_general
            if family.casefold() in carried and (not asked or family.casefold() in asked)
        ]
        if general and not blades_only:
            # THE HUB AND THE SPINNER HAVE NO LOCAL AXIS OF THEIR OWN: their
            # local frame IS the rotor's, which is what makes the spinner
            # ride the hub (FR-59). One emission for them, in that frame.
            #
            # FR-75 LEAVES IT OUT OF A SECTION DISTRIBUTION, and only of that.
            # This emission is the one that cuts "the rotor as a whole", and a
            # cut of a rotor crosses its blades at different azimuths, so the
            # station it reports is a station of nothing. A licensed probe measured
            # the counts on the template's row 1003: a `LOCAL_AXIS` entry over
            # PUSHER emitted FOUR distributions, three in the blade frames and
            # a fourth in the rotor's own. The force plot keeps all four,
            # because a rotor's total force IS a quantity.
            emissions.append((f"{alias}_RMRP", general, alias))
    # A ROW THAT DOES NOT TURN THE ROTOR PLACES NONE OF ITS FRAMES, and one
    # artifact serves a steady row and a rotor row: that is the whole point
    # of the skip rule, and FR-65 draws the line where it draws every other
    # one. An entry whose families reach no rotor OF THE REFERENCE is a
    # writing error and is refused above, because it cannot come right on
    # another row; an entry whose frames this RUN did not create can, and is
    # left out, exactly as an entry whose families the geometry lacks is.
    kept = [emission for emission in emissions if emission[0] in placed]
    dropped = [emission[0] for emission in emissions if emission[0] not in placed]
    if dropped:
        # ONE WARNING PER ENTRY AND IT NAMES WHAT WENT, because the first
        # writing warned only when EVERY emission was unplaced: a row
        # turning the lifters and not the pusher dropped the pusher's
        # emissions in silence, which is the very row FR-65's paragraph is
        # about (the QA lens, 2026-09-10). A partly working entry is the
        # harder case to notice, not the easier one, because the products
        # do contain a plot by that name.
        missing = (
            "none of those frames"
            if not kept
            else f"{len(kept)} of the {len(emissions)} frames it expands over"
        )
        warnings.warn(
            f"case {case.sim_id!r}: {what} of {_artifact_of(case)} is measured in "
            f"{frame}, one per {kind}, and this run created {missing} "
            f"({', '.join(dropped)} not placed; placed: "
            f"{', '.join(sorted(placed)) or 'none'}), so "
            f"{'the entry is left out' if not kept else 'those emissions are left out'}. "
            "A row that does not turn a rotor places none of its frames, which is the "
            "same rule that lets one artifact serve a wing-body and a rotor row.",
            PyflightstreamWarning,
            stacklevel=2,
        )
    return kept


def _refuse_a_retired_frame(case: SimCase, name: str, what: str) -> None:
    """Refuse a frame citation written in the vocabulary 0.15.0 removed.

    Without this the citation falls through to "this run created no such
    frame", which is true, names the frames that DO exist, and says nothing
    about the rename: a user holding a 0.14.0 post-processing artifact is
    told their frame is missing rather than that it was replaced by a shape
    (the interface lens of the 0.15.0 release review).

    Raises
    ------
    CampaignConfigError
        The name is a retired frame spelling.
    """
    entry = retired_frame(name)
    if entry is None:
        return
    declared = ", ".join(f"{alias}_SMRP" for alias in sorted(case.rotors)) or (
        "none, because this row's reference declares no rotor"
    )
    raise CampaignConfigError(
        f"case {case.sim_id!r}: {what} cites frame {name!r}. {entry.message()} "
        f"The frames this row's rotors carry are: {declared}."
    )


def _pproc_frame(
    case: SimCase, frames: Frames, name: str, what: str, families: Sequence[str] = ()
) -> int:
    """Resolve a frame a pproc entry cites by name to the index the builder created.

    BLADE_AXIS is a frame per blade, so an entry citing it names one blade
    family at a time (``each_blade``); the family's own axis frame is the
    one returned.
    """
    # THE RETIREMENT IS ASKED FIRST, before the generic answer. A citation
    # written in the vocabulary 0.15.0 removed deserves the rename, not a
    # list of the frames that happen to exist.
    _refuse_a_retired_frame(case, name, f"{what} of the pproc artifact {case.pproc_id!r}")
    found = frames.get(name)
    if isinstance(found, Mapping):
        if len(families) != 1 or families[0] not in found:
            raise CampaignConfigError(
                f"case {case.sim_id!r}: the pproc artifact {case.pproc_id!r} cites frame "
                f"{name!r} for {what} over families {list(families)}, and that frame is "
                "one per blade. Since 0.15.0 the FRAME says how an entry expands, so "
                'write frame = "LOCAL_AXIS" over the rotor or the alias you want and it '
                "is one emission per blade, each in that blade's own axes. The spelling "
                'this replaced, families = "each_blade", is refused since 0.15.0 '
                f"(blades with an axis frame here: {', '.join(found)})."
            )
        return found[families[0]]
    if found is None:
        created = sorted(key for key, value in frames.items() if value is not None)
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the pproc artifact {case.pproc_id!r} cites frame "
            f"{name!r} for {what}, and this run created no such frame (created: "
            f"{', '.join(created) or 'none'}). MRP needs a reference artifact; a "
            "rotor's own frames need that rotor declared in the reference AND moved by "
            "this row, because a row places the frames of the rotors its motions name; "
            "and BLADE_AXIS needs the multirotor run type with a geometry carrying "
            "blade families (PFS-2029.11.03). There is no package-level rotor frame "
            "since 0.15.0: each rotor carries <ALIAS>_SMRP, <ALIAS>_RMRP and "
            "<ALIAS>_RMRP<k>."
        )
    return found


def _script_tail(
    conventions: WorkflowConventions,
    case: SimCase,
    script: Script,
    frame: int | None,
    *,
    unsteady: bool,
    frames: Frames | None = None,
) -> None:
    """Emit the four phases every run type ends with, each preceded by its raw commands.

    Init, exec, analysis and export, in the order the four builders
    always emitted them; written once so the raw commands of a setup
    (PFS-2033.01) meet each phase at one seam rather than at four copies
    of it.
    """
    _raw_commands(case, script, "init")
    _initialize(case, script)
    # THE SECTION DISTRIBUTIONS SIT HERE, between the solver being initialised
    # and being started, which is where the reference working scripts put
    # them: `SCRIPT-POLAR-3267` reads INITIALIZE_SOLVER at 12779, twelve
    # distributions at 12880, START_SOLVER at 13022, and those twelve produce
    # real cuts on a real rotor run. This package emitted them BEFORE
    # `INITIALIZE_SOLVER`, against a solver that had not initialised.
    #
    # Both positions are the `init` phase, so this is a move WITHIN a phase and
    # the script's phase guard neither permitted nor prevented it.
    if frames is not None:
        _pproc_sections(case, script, frames)
    elif case.pproc is not None and case.pproc.sections.distributions:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the pproc artifact {case.pproc_id!r} declares "
            f"{len(case.pproc.sections.distributions)} section distribution(s) and "
            "this run was built without the frames they are measured in, so not one "
            "of them would be emitted. That is a defect in the builder rather than "
            "in the artifact."
        )
    _raw_commands(case, script, "exec")
    helpers.start_solver(script)
    _raw_commands(case, script, "analysis")
    # FR-81: a STEADY row creates the probe points it exports. `NEW_PROBE_LINE`
    # is an ANALYSIS command, so this is the only position the phase order
    # allows, and it is where the reference scripts already carry `UPDATE_PROBE_POINTS`
    # and `EXPORT_PROBE_POINTS`. An unsteady row placed its vertices through the
    # fluid plots long before this point and needs nothing here.
    if frames is not None:
        _pproc_probes(case, script, frames, unsteady=unsteady, analysis=True)
    _analysis(case, script, frame)
    _raw_commands(case, script, "export")
    _export_block(conventions, case, script, unsteady=unsteady)
    script.emit("CLOSE_FLIGHTSTREAM")


#: THE SEAMS A FLAG MAY REACH, which are the three the builders open for a
#: raw entry too. A command of a later phase is part of the RUN rather than
#: of its setting up, and this package emits those itself.
FLAG_PHASES: tuple[str, ...] = ("control", "geometry", "setup")


def _the_flag_a_row_states(case: SimCase, flag: CustomFlag) -> str | None:
    """Return the value the row states for one declared flag, or None.

    The word is read CASE FOLDED, as every other row key is, so a cell
    writing `WAKE_LENGTH` reaches a flag declared `wake_length`. A row
    that states the word with an empty value states nothing: a cell
    written `wake_length:` is a half-finished edit and not a request to
    emit the command with no argument, which the emitter would refuse
    one layer down with a message about arity rather than about the row.
    """
    wanted = flag.name.strip().casefold()
    for key, value in case.variables.items():
        if key.strip().casefold() != wanted:
            continue
        text = str(value).strip()
        return text or None
    return None


def _custom_flags(case: SimCase, script: Script, phase: str) -> None:
    """Emit the declared flags this row states, before ``phase`` (PFS-2035.20).

    A flag is the command and the ROW is the value, which is what makes
    this different from a raw entry and what leaves RAW to the particular
    case: one preset declaring `wake_length = SET_WAKE_LENGTH` serves a
    sweep over the wake length, where a raw line would fix it.

    THE SAME EMIT CHECK EVERY CURATED EMISSION PASSES, which is the
    condition placed on the feature. The line is built as
    ``<command> <value>`` and emitted through :meth:`Script.emit_line`,
    so the database's grammar, version, argument and phase checks apply
    unchanged; the emitter's error is the refusal, raised again under its
    own class with the flag, the setup and the row's value named.

    WHICH PHASE. A flag with no ``before`` takes the phase its command's
    own database entry declares, which is the answer for every command
    that has one; a CONTROL command, whose phase the database leaves
    open, is emitted in the control phase unless the declaration says
    otherwise.
    """
    for flag in case.flags:
        value = _the_flag_a_row_states(case, flag)
        if value is None:
            continue
        name = flag.command
        try:
            spec = script.entry(name)
            # `Phase.CONTROL.value` AND NOT `phase`. Reading the CURRENT
            # phase here made the derived answer equal whatever seam was
            # asking, so the skip below never fired and a control command
            # went out at all three: 28 shipped commands declare phase
            # control, so the triple emission was reachable rather than
            # theoretical (the interface lens of the 0.15.0 release review).
            wanted = flag.before or (
                Phase.CONTROL.value if spec.phase is Phase.CONTROL else spec.phase.value
            )
            if wanted not in FLAG_PHASES:
                # NOT SILENTLY DROPPED. The builders open three seams,
                # and a flag whose command belongs to a later phase has
                # nowhere to go: emitting it at one of these would
                # advance the script past that phase and the order guard
                # would then refuse the phase's own commands. Said here,
                # naming the flag and the phase, rather than by the row
                # quietly not carrying it.
                raise CampaignConfigError(
                    f"the flag {flag.name!r} of setup {flag.setup!r} names {name}, "
                    f"a {wanted} command, and a flag is emitted before one of "
                    f"{', '.join(FLAG_PHASES)}. A {wanted} command is part of the "
                    "run rather than of its setting up, and this package emits "
                    "those itself; a row that needs one states it in the [[raw]] "
                    "table, which is what that table is the escape for."
                )
            if wanted != phase:
                continue
            script.emit_line(f"{name} {value}")
        except PyflightstreamError as error:
            raise type(error)(
                f"case {case.sim_id!r}: the flag {flag.name!r} of setup {flag.setup!r}, "
                f"declared as {name}, is refused by the emitter with the row's value "
                f"{value!r}: {error}"
            ) from error


def _raw_commands(case: SimCase, script: Script, phase: str) -> None:
    """Emit the setup's raw commands declared before ``phase``, in the order written.

    PFS-2033.01, the design of 2026-09-09 (design/69). Each line is split
    on whitespace, its arguments coerced to the types the command's
    database entry declares, and emitted through :meth:`Script.emit`, so
    the line passes exactly the checks every curated emission passes: a
    command the build has no evidence for, an argument of the wrong type
    or count, a phase out of order. The emitter's error is the refusal,
    raised again under its own class with the setup and the line named.
    A command whose grammar is not one line (a keyword block, a payload,
    a parameter block) is refused naming the layout, since an entry is
    one line as the solver reads it. A setup stating none emits nothing.
    """
    for entry in case.raw_commands:
        if entry.before != phase:
            continue
        # WHERE THE LINE CAME FROM, in the words that let the user find it
        # (FR-67). A file's line says the path AND the line number, because
        # the cell holds a path and the mistake is thirty lines away.
        if entry.source and entry.source != "matrix":
            where = (
                f"setup {entry.setup!r}"
                if entry.source == entry.setup
                else f"the raw file {entry.source}"
            )
        elif entry.source == "matrix":
            where = "the row's own RAW cell"
        else:
            where = f"setup {entry.setup!r}" if entry.setup else "the case's raw commands"
        name = entry.command.split()[0]
        try:
            spec = script.entry(name)
            # A command of a LATER phase than the one it is declared before
            # would advance the script past that phase, and the order guard
            # would then refuse every command of the phase itself; said here,
            # naming the setup, rather than at the first such command. The
            # layout and the argument types are the emitter's own checks.
            if (
                spec.phase is not Phase.CONTROL
                and phase in RAW_PHASES
                and RAW_PHASES.index(spec.phase.value) > RAW_PHASES.index(phase)
            ):
                raise CampaignConfigError(
                    f"{name} is a {spec.phase.value} command, and declared before {phase} it "
                    f"would put the script in its {spec.phase.value} phase before the {phase} "
                    f"commands are written, which the order guard refuses; declare it before "
                    f"{spec.phase.value}, or drop it"
                )
            script.emit_line(entry.command)
        except PyflightstreamError as error:
            raise type(error)(
                f"case {case.sim_id!r}: the raw command {entry.command!r} of {where}, declared "
                f"before {phase}, is refused by the emitter: {error}"
            ) from error


def _setup_frames(case: SimCase, script: Script) -> dict[str, int]:
    """Create the custom frames the row's setup defines, returning name to index.

    PFS-2034.01, the design of 2026-09-09 (design/69). Emitted after the
    package's own frame (MRP) so their indices stay what the reference
    scripts numbered them, and before any motion, so a rotor whose axis
    frame is one of these turns about a frame that exists. A setup that
    defines none emits nothing, which is every golden.
    """
    created: dict[str, int] = {}
    for spec in case.frames:
        created[spec.name] = helpers.coordinate_frame(
            script,
            name=spec.name,
            origin=spec.origin,
            x_axis=spec.x_axis,
            y_axis=spec.y_axis,
            label=spec.name,
        )
    return created


_AXIS_TOKEN = re.compile(r"^(?P<frame>.+)-(?P<axis>[XYZ])$")


def _rotations(
    case: SimCase,
    script: Script,
    named: Mapping[str, int | None],
    followers: Mapping[str, Sequence[int]] | None = None,
    spinning: Mapping[str, Sequence[int]] | None = None,
) -> None:
    """Rotate the mesh families the row's ``ROTATE`` records name, in the order written.

    PFS-2034.02, the design of 2026-09-09 (design/69). Each record is one
    rotation of the named families about the named axis of the named
    frame, emitted after every frame exists and before any motion is
    created, so a rotor whose axis frame is among the auxiliaries turns
    about the rotated axis with nothing else to do. The families resolve
    by NAME against the opened geometry's inventory, exact label first and
    family second, as ``MOVING_BOUNDARIES`` does (a user never writes an
    index); the frames resolve by the name the solver shows, ``named``
    being the frames the builder created so far (the package's own and
    the setup's). An auxiliary frame is turned by the same command the
    blade axes use, ``ROTATE_COORDINATE_SYSTEM``, and a frame the package
    DERIVED from an auxiliary (the blade axis frames from ``ROTOR_MRP``,
    listed in ``followers``) turns with it, because it was placed from
    that frame and would otherwise be left behind by the incidence the
    row states. A row without the variable emits nothing.

    ``spinning`` maps a frame's name to the boundaries whose motion turns
    about it (``ROTOR_MRP`` to the blades on a flat rotor row, ``ROTOR_MRP<k>``
    to record k's on a ``MOTIONS`` row). A record that turns any of those
    boundaries and does not name that frame among its auxiliaries turns
    the blades and leaves the axis they spin about where it was: a
    physics call the row may mean, so it WARNS naming the frame rather
    than refusing (PFS-2034.03).
    """
    if not case.rotations:
        return
    frames = {name: index for name, index in named.items() if index is not None}
    labels = script.entities.labels("boundaries")
    #: The aliases whose `<ALIAS>_SMRP_ORIGINAL` this row has already kept.
    #: ONE PER ALIAS is the decision of 2026-09-10 (DEC-010), so a row that
    #: rotates one alias twice keeps the state before the FIRST rotation.
    kept: set[str] = set()
    for record in case.rotations:
        # The matrix reader refused these already; a case authored in
        # Python meets the same sentence here rather than a KeyError.
        missing = [key for key in ROTATION_RECORD_KEYS if key not in record]
        if missing:
            raise CampaignConfigError(
                f"case {case.sim_id!r} states a {ROTATE_VARIABLE} record without "
                f"{', '.join(missing)}; every rotation states ANGLE and AXIS, and names "
                "what it turns."
            )
        angle = float(record["ANGLE"])
        token = record["AXIS"]
        matched = _AXIS_TOKEN.match(token)
        if matched is None:
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {ROTATE_VARIABLE} with AXIS {token!r}, which is "
                "not of the form frame-axis; write the frame's name, a hyphen and X, Y or Z "
                "(the axis letter uppercase), "
                f"as NAC-Y. The frames this case defines are {_frame_names(frames)}."
            )
        frame_name, axis = matched.group("frame"), matched.group("axis")
        frame = _rotation_frame(case, frame_name, frames, "AXIS")
        cited = _what_the_rotation_turns(case, record)
        boundaries: list[int] = []
        for name in (part.strip() for part in cited.split(",")):
            if not name:
                continue
            if not labels:
                _refuse_name_without_inventory(case, ROTATE_VARIABLE, name)
            found = _resolve_token(case, name, labels)
            if not found:
                _refuse_name_absent_from_inventory(case, ROTATE_VARIABLE, name, labels)
            boundaries.extend(index for index in found if index not in boundaries)
        if not boundaries:
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {ROTATE_VARIABLE} turning {cited!r}, "
                f"which names no boundary; name what to turn, of "
                f"{_declared_labels(labels)}."
            )
        helpers.rotate_surfaces(
            script, frame=frame, axis=axis, angle_deg=angle, boundaries=sorted(boundaries)
        )
        aux_names = [part.strip() for part in record.get("AUX_FRAMES", "").split(",")]
        aux_names = [name for name in aux_names if name]
        # EVERY FRAME THE ALIAS OWNS TURNS WITH IT (FR-71), which is what
        # retires AUX_FRAMES: a rotor's frames are placed FROM its hub, so
        # a row that turned the blades and left them behind was stating an
        # incidence the axes did not get, and the row had to list them by
        # hand to fix it. A non-rotor alias owns no frame and adds none.
        # THE FRAME THIS ALIAS TURNS FROM, kept before it turns (FR-71).
        # Once per alias: `kept` is the set of aliases already copied, so a
        # row that rotates one alias twice keeps the state before the FIRST
        # rotation and adds nothing at the second.
        _keep_the_frame_this_alias_turns_from(case, record, script, frames, kept)
        owned = _frames_the_alias_owns(case, record, frames)
        aux_names = [*owned, *(name for name in aux_names if name not in owned)]
        # Resolved BEFORE the warning below, so a misspelt auxiliary meets its
        # refusal and not an advisory about a different frame (the QA lens).
        aux_frames = [
            _rotation_frame(case, aux_name, frames, "AUX_FRAMES") for aux_name in aux_names
        ]
        # WHAT ACTUALLY TURNS, BY INDEX AND ONCE EACH. One frame has more
        # than one name -- a rotor's hub is `<ALIAS>_SMRP` and `ROTOR_MRP<k>`
        # at the same index, and `<ALIAS>_RMRP` is both a frame the alias
        # owns and a FOLLOWER of the hub -- so a list keyed on names turned
        # the same frame twice and a row asking for three degrees got six.
        # Measured on the release's own recommended spelling (the interface
        # lens, 2026-09-10).
        turning: list[int] = []
        for aux_name, aux in zip(aux_names, aux_frames, strict=True):
            for index in (aux, *((followers or {}).get(aux_name, ()))):
                if index not in turning:
                    turning.append(index)
        # ONE ADVISORY PER FRAME, and the question is whether the FRAME
        # turned rather than whether its name was typed. A rotor's hub has
        # two names in `spinning`, the alias one and the 0.14.0 one, at one
        # index, so a name-keyed walk both warned twice about one frame and
        # warned at all about a frame the alias had just turned: the
        # release's own recommended row was told the axis stayed where it
        # was, and told to fix it with a key the same release retires (all
        # three lenses, 2026-09-10).
        for axis_index, (spun_about, spun) in _axes_the_blades_spin_about(spinning, frames).items():
            turned_blades = sorted(set(boundaries) & set(spun))
            if not turned_blades or axis_index in turning:
                continue
            remedy = (
                f"turn it by its alias, which carries {spun_about} and the rest of that "
                "rotor's frames"
                if spun_about.endswith("_SMRP")
                else f"add AUX_FRAMES: {spun_about} to the record"
            )
            warnings.warn(
                f"case {case.sim_id!r} states {ROTATE_VARIABLE} turning "
                f"{_named_boundaries(turned_blades, labels)} by {angle} degrees about "
                f"{token} and does not turn {spun_about}, so the blades turn and the "
                "axis they spin about stays where it was. If the incidence is meant "
                f"for the rotor, {remedy}; if the blades alone are meant to turn, this "
                "is your call and the script does what the row says.",
                PyflightstreamWarning,
                stacklevel=3,
            )
        for index in turning:
            script.emit(
                "ROTATE_COORDINATE_SYSTEM",
                frame=index,
                rotation_frame=frame,
                rotation_axis=axis,
                angle=angle,
            )


def _axes_the_blades_spin_about(
    spinning: Mapping[str, Sequence[int]] | None, frames: Mapping[str, int]
) -> dict[int, tuple[str, Sequence[int]]]:
    """Collapse the spun-about frames to one entry per FRAME, best-named.

    `spinning` is keyed by every name a frame answers to: a rotor's hub is
    both ``<ALIAS>_SMRP`` and ``ROTOR_MRP<k>`` at one index. The advisory
    that reads it is about a FRAME, so it walks indices, and the name it
    reports is the alias one where there is one, because that is the name
    the user can act on: the alias carries the frame, and the 0.14.0
    spelling is the key this release retires.
    """
    best: dict[int, tuple[str, Sequence[int]]] = {}
    for name, spun in (spinning or {}).items():
        index = frames.get(name)
        if index is None:
            continue
        held = best.get(index)
        if held is None or (name.endswith("_SMRP") and not held[0].endswith("_SMRP")):
            best[index] = (name, spun)
    return best


def _what_the_rotation_turns(case: SimCase, record: Mapping[str, str]) -> str:
    """Return the token(s) a rotation record turns, from ALIAS or FAMILIES (FR-71).

    ``ALIAS`` since 0.15.0, ``FAMILIES`` before it, and the two are
    refused together by the reader; a case authored in Python meets the
    same sentence here. The alias is returned AS A TOKEN rather than
    expanded, because `_resolve_token` already puts the row's aliases
    between the exact label and the family, so one word resolves the same
    way here as it does in a motion.
    """
    alias = record.get(ROTATION_ALIAS_KEY)
    families = record.get(ROTATION_FAMILIES_KEY)
    if alias is not None and families is not None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states a {ROTATE_VARIABLE} record with "
            f"{ROTATION_ALIAS_KEY} and {ROTATION_FAMILIES_KEY} both; one rotation turns "
            "ONE set."
        )
    if alias is not None:
        token = alias.strip()
        declared = {*case.aliases, *case.rotors}
        if not any(name.casefold() == token.casefold() for name in declared):
            # A LIST OF DECLARED WORDS IS A DIFFERENT MISTAKE, and it is the
            # one a `FAMILIES` migration produces: the old key took a list
            # and this one does not, so the refusal that merely lists the
            # declared words reads as a bug to the person who just wrote two
            # of them (the interface lens, 2026-09-10).
            parts = [part.strip() for part in token.split(",") if part.strip()]
            folded = {name.casefold() for name in declared}
            if len(parts) > 1 and all(part.casefold() in folded for part in parts):
                raise CampaignConfigError(
                    f"case {case.sim_id!r} states {ROTATE_VARIABLE} turning "
                    f"{ROTATION_ALIAS_KEY}: {token}, which names {len(parts)} declared "
                    "words. A rotation turns ONE alias, because the frames that turn "
                    "with it are that one rotor's. Write one record per alias, "
                    "{...}, {...}, in the order you want them turned."
                )
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {ROTATE_VARIABLE} turning "
                f"{ROTATION_ALIAS_KEY}: {token}, and the reference declares no such "
                f"alias. The words it declares are "
                f"{', '.join(repr(name) for name in sorted(declared)) or 'none'}. A "
                "rotation names a set the way a motion does, so the word is one the "
                "reference owns, and a rotor among them carries its own frames."
            )
        return token
    if families is None:
        written = " / ".join(f"{key}: {value}" for key, value in record.items())
        raise CampaignConfigError(
            f"case {case.sim_id!r} states the {ROTATE_VARIABLE} record "
            f"{{{written}}}, which says how far to turn and about what, and nothing to "
            f"turn. State {ROTATION_ALIAS_KEY}: <the word the reference declares>, which "
            "is how a motion names a set too."
        )
    # THE RECORD'S OWN TEXT IS IN THE MESSAGE, and that is not decoration.
    # Built from the case id and the ledger alone, two records of one row
    # produced a byte-identical message at an identical warning-registry
    # key, so Python's default filter dropped the second and a row
    # migrating record by record was told about one of them (measured by
    # the quality lens, 2026-09-10: 1 warning where 2 were due).
    written = " / ".join(f"{key}: {value}" for key, value in record.items())
    words = sorted({*case.aliases, *case.rotors})
    raise CampaignConfigError(
        f"case {case.sim_id!r}, {ROTATE_VARIABLE} record {{{written}}}: "
        f"{refusal_text(ROW_ROTATE_FAMILIES)} It is not a rename of the key alone: the "
        f"VALUE becomes one word the reference declares, of "
        f"{', '.join(repr(name) for name in words) or 'none'}, and a families list "
        "spanning two of them becomes one record per alias."
    )


#: The suffix of the copy a rotor's hub keeps of itself, before anything
#: turned it (FR-71). It is a frame like any other to the post-processing,
#: which may cite it by name, and nothing ever rotates it.
ORIGINAL_FRAME_SUFFIX = "_ORIGINAL"


def _keep_the_frame_this_alias_turns_from(
    case: SimCase,
    record: Mapping[str, str],
    script: Script,
    # NARROWER THAN THE `Frames` ALIAS ON PURPOSE. This function only asks
    # whether the hub is placed and writes ONE index, so it takes the
    # mapping the rotation loop actually holds, which carries indices and
    # nothing else. A `dict` is invariant in its value type, so declaring
    # the wide alias here refused the caller's own dictionary.
    frames: MutableMapping[str, int],
    kept: set[str],
) -> None:
    """Create ``<ALIAS>_SMRP_ORIGINAL`` once per alias, before its first turn (FR-71).

    ONCE PER ALIAS AND NOT ONCE PER RECORD, which is the decision of
    2026-09-10 (DEC-010). The discriminator was a row that
    rotates one alias TWICE: per record would also keep the state BETWEEN
    the two rotations, and that reading is not wanted, so a second
    rotation of the same alias adds nothing and the copy still names the
    state before the row touched anything.

    WHY THE COPY IS TAKEN HERE and not where the hub is created: at the
    moment the hub is placed nothing has turned, so a copy made there and a
    copy made here are the same frame. Here is where the ROW's intent is
    known, so a row that turns NO rotor creates no copy of one, and a
    reader of the script meets the copy immediately above the rotation it
    exists to survive.

    A record naming no alias, or an alias the reference declares as no
    rotor, keeps nothing: there is no hub to copy.
    """
    alias = (record.get(ROTATION_ALIAS_KEY) or "").strip()
    if not alias:
        return
    radical = next(
        (name for name in {*case.rotors} if name.casefold() == alias.casefold()),
        None,
    )
    if radical is None or radical in kept:
        return
    hub = f"{radical}_SMRP"
    if hub not in frames:
        # The rotor has no motion on this row, so its frames were never
        # placed and there is nothing to keep a copy OF. The rotation
        # still turns the alias's boundaries; it simply turns no frame.
        return
    block = case.rotors[radical]
    frames[f"{hub}{ORIGINAL_FRAME_SUFFIX}"] = helpers.coordinate_frame(
        script,
        name=f"{hub}{ORIGINAL_FRAME_SUFFIX}",
        origin=block.origin,
        x_axis=(1.0, 0.0, 0.0),
        y_axis=(0.0, 1.0, 0.0),
        label=f"rotor_original:{radical}",
    )
    kept.add(radical)


def _frames_the_alias_owns(
    case: SimCase, record: Mapping[str, str], frames: Mapping[str, int]
) -> list[str]:
    """Return the frames the record's alias owns (FR-71).

    A rotor owns ``<ALIAS>_SMRP``, ``<ALIAS>_RMRP`` and one
    ``<ALIAS>_RMRP<k>`` per blade, which is exactly the set
    `_rotor_blade_frames` and its callers create from the block. Anything
    else owns none: a wing alias names boundaries and no frame was ever
    placed from it.

    Read off the frames THIS SCRIPT created rather than off the block, so
    a row whose rotor has no motion (and therefore no frames) turns its
    boundaries and rotates nothing that does not exist.
    """
    alias = (record.get(ROTATION_ALIAS_KEY) or "").strip()
    if not alias:
        return []
    radical = next(
        (name for name in {*case.rotors} if name.casefold() == alias.casefold()),
        None,
    )
    if radical is None:
        return []
    # THE HUB, THEN EVERYTHING ROTATING, and the second half is a prefix
    # scan because `<ALIAS>_RMRP` and `<ALIAS>_RMRP<k>` share it. Naming
    # `<ALIAS>_RMRP` in the seed as well READ as load-bearing and was not:
    # a hostile pass mutated it away and every case stayed green, and the
    # measurement said why, so the redundancy is gone rather than
    # explained (2026-09-10).
    owned = [f"{radical}_SMRP"]
    owned += sorted(name for name in frames if name.startswith(f"{radical}_RMRP"))
    return [name for name in owned if name in frames]


def _named_boundaries(indices: Sequence[int], labels: Mapping[str, int]) -> str:
    """Return the labels of ``indices`` in that order, quoted, for a message."""
    by_index = {index: name for name, index in labels.items()}
    return ", ".join(repr(by_index.get(index, str(index))) for index in indices)


def _frame_names(frames: Mapping[str, int]) -> str:
    """Return the frames a rotation may cite, by the name the solver shows, for a message."""
    return ", ".join(repr(name) for name in frames) or "none"


def _rotation_frame(case: SimCase, name: str, frames: Mapping[str, int], key: str) -> int:
    """Resolve a frame name a rotation record cites, refusing one nothing defined.

    Matched case folded, the one rule the setup already teaches by refusing
    two names that differ by case alone (the interface lens of REL-0140).
    """
    by_upper = {known.upper(): index for known, index in frames.items()}
    if name.upper() in by_upper:
        return by_upper[name.upper()]
    raise CampaignConfigError(
        f"case {case.sim_id!r} states {ROTATE_VARIABLE} with {key} naming {name!r}, and "
        f"no frame of that name exists when the rotation is emitted; the frames this case "
        f"defines are {_frame_names(frames)}. A setup preset defines one in its [[frames]] "
        "table; MRP is the package's own on every run type, and ROTOR_MRP on the rotor run "
        "types."
    )


def _the_blade_frames_under_their_rotors_names(
    case: SimCase, blade_frames: Mapping[str, int]
) -> dict[str, int]:
    """Name a flat row's per-blade frames the way a MOTIONS row names them.

    A flat row creates ``BladeAxis<k>``, one per blade family, and that is
    the name in its script and in every golden. A post-processing entry
    citing ``LOCAL_AXIS`` expands to ``<ALIAS>_RMRP<k>``, because that is
    what a rotor's blade frame is called since 0.15.0. Registering the same
    index under both names is what lets one artifact serve both row shapes;
    without it the entry resolved on a MOTIONS row and reached nothing
    here, with no refusal, which is the silence FR-65 exists against.
    """
    named: dict[str, int] = {}
    for alias, block in case.rotors.items():
        for number, family in enumerate(block.families_blades, start=1):
            index = blade_frames.get(family)
            if index is not None:
                named[f"{alias}_RMRP{number}"] = index
    return named


def _blade_indices(case: SimCase, script: Script) -> list[int]:
    """Return the boundary indices of the blade families, by the pproc's own test or the default."""
    pproc = case.pproc
    is_blade = pproc.is_blade if pproc is not None else _default_is_blade
    labels = script.entities.labels("boundaries")
    return sorted(index for name, index in labels.items() if is_blade(name))


def _blade_frames(case: SimCase, script: Script, rotor_frame: int) -> dict[str, int]:
    """Create one axis frame per blade family, turned about the rotor frame.

    PFS-2029.11.03, as the reference rotor scripts did it: a frame ``BladeAxis<k>``
    per blade family, at the rotor frame's origin with its axes,
    rotated about the rotor axis by the blade's share of a turn, so blade
    k of N sits at (k-1) * 360 / N degrees; a periodic sector meshing one
    blade gets one frame at zero. The frames are the motion's moving
    frames, so the solver turns them with the blades, and the pproc
    artifact's BLADE_AXIS entries cite them by family. A geometry with no
    blade family creates none, which is what keeps every rotor script
    without one byte for byte as it was.
    """
    pproc = case.pproc
    is_blade = pproc.is_blade if pproc is not None else _default_is_blade
    blades = [name for name in _inventory(script) if is_blade(name)]
    if not blades:
        return {}
    axis = str(_variable(case, ROTOR_AXIS_VARIABLE) or "X").upper()
    origin = (0.0, 0.0, 0.0)
    if case.reference is not None and case.reference.rotor_position_m is not None:
        origin = case.reference.rotor_position_m
    created: dict[str, int] = {}
    for number, family in enumerate(blades, start=1):
        index = helpers.coordinate_frame(
            script,
            name=f"BladeAxis{number}",
            origin=origin,
            x_axis=(1.0, 0.0, 0.0),
            y_axis=(0.0, 1.0, 0.0),
            label=f"blade_axis:{family}",
        )
        script.emit(
            "ROTATE_COORDINATE_SYSTEM",
            frame=index,
            rotation_frame=rotor_frame,
            rotation_axis=axis,
            angle=(number - 1) * 360.0 / len(blades),
        )
        created[family] = index
    return created


def _rotor_blade_frames(
    script: Script,
    rotor: RotorBlock,
    hub: int,
    radical: str,
    view: SimCase,
) -> dict[str, int]:
    """Create one frame per blade of a rotor, named from its alias (FR-62).

    ``<ALIAS>_RMRP<k>`` for blade k of the block's ``families_blades``, at
    the rotor's hub, turned about the rotor's axis by the blade's share of
    a turn measured from the ``blade1`` datum: blade k of N sits at
    ``azimuth_deg + (k - 1) * 360 / N``. The frames turn with the blades,
    so a per-blade product is read in the frame of the blade it is about.

    A BLADE THE MESH DOES NOT CARRY GETS NO FRAME, and the count is not
    reduced by its absence: a periodic sector meshing one blade of four
    creates one frame, at the datum, and the reductions still divide by
    four, because the count is the length of the list and not a property
    of the file. The returned mapping is keyed by the blade's FAMILY, as
    the flat form's is, so a pproc entry citing a blade resolves the same
    way on either.
    """
    inventory = set(_inventory(script))
    count = rotor.blade_count
    created: dict[str, int] = {}
    for number, family in enumerate(rotor.families_blades, start=1):
        if family not in inventory:
            continue
        index = helpers.coordinate_frame(
            script,
            name=f"{radical}_RMRP{number}",
            origin=rotor.origin,
            x_axis=(1.0, 0.0, 0.0),
            y_axis=(0.0, 1.0, 0.0),
            label=f"blade_axis:{family}",
        )
        script.emit(
            "ROTATE_COORDINATE_SYSTEM",
            frame=index,
            rotation_frame=hub,
            rotation_axis=rotor.axis,
            angle=rotor.blade1.azimuth_deg + (number - 1) * 360.0 / count,
        )
        created[family] = index
        created[f"{radical}_RMRP{number}"] = index
    return created


def _default_is_blade(family: str) -> bool:
    """Tell a blade family from the airframe when no pproc artifact says how."""
    return re.match(r"^Blade\d+$", family) is not None


def _pproc_plots(case: SimCase, script: Script, frames: Frames) -> None:
    """Emit the force plots and the fluid plots the pproc artifact defines.

    Force plots come one per group and parameter, in the artifact's
    order, named ``{parameter}_{group}`` as the reference plot files were, sampled
    in COEFFICIENTS for the four coefficients and NEWTONS for the six
    loads; a group whose families the geometry does not carry is left
    out, and ``all`` takes the command's own every-boundary form. Fluid
    plots come one per vertex and parameter along the probe lines, named
    ``{parameter}{n}`` with n counting vertices across the lines.
    Emitted right after the frames, before the solver settings, which is
    where the reference scripts placed them and before the solver they record.
    """
    pproc = case.pproc
    if pproc is None:
        return
    inventory = _inventory(script)
    for group in pproc.plots.groups:
        what = f"plot group {group.name!r}"
        for frame_name, families, label in _pproc_emissions(
            case, group.frame, group.families, inventory, pproc.is_blade, what, frames
        ):
            frame = _pproc_frame(case, frames, frame_name, what, families)
            name = group.name.format(family=label) if "{family}" in group.name else group.name
            # THE TWO READINGS OF ONE ROTATED HUB NEED TWO NAMES, or the
            # second plot overwrites the first under one file name and the
            # study loses the half it asked for. The suffix is the frame's
            # own, so a reader who sees the file knows which frame it is in
            # without opening it (the rule of 2026-09-10, FR-71).
            if frame_name.endswith(ORIGINAL_FRAME_SUFFIX):
                name = f"{name}{ORIGINAL_FRAME_SUFFIX}"
            indices = [script.resolve_boundary(f, context="pproc plot") for f in families]
            for short in pproc.plots.parameters:
                parameter, units = FORCE_PLOT_PARAMETERS[short]
                if indices:
                    script.emit(
                        "UNSTEADY_SOLVER_NEW_FORCE_PLOT",
                        frame=frame,
                        units=units,
                        parameter=parameter,
                        name=f"{short}_{name}",
                        boundaries=len(indices),
                        boundary_indices=indices,
                    )
                else:
                    script.emit(
                        "UNSTEADY_SOLVER_NEW_FORCE_PLOT",
                        frame=frame,
                        units=units,
                        parameter=parameter,
                        name=f"{short}_{name}",
                        boundaries=-1,
                    )


def _pproc_probes(
    case: SimCase, script: Script, frames: Frames, *, unsteady: bool, analysis: bool
) -> None:
    """Emit every `[[probes]]` entry the artifact declares (FR-77, FR-81).

    CALLED BY ALL FOUR BUILDERS, which is the fix. This lived inside
    `_pproc_plots` until 0.16.0, and `_pproc_plots` is called by the three
    UNSTEADY builders alone, so a steady row never reached the probes code at
    all. Meanwhile the export block emitted `EXPORT_PROBE_POINTS` off the row's
    OUTPUT NAMES, which know nothing about run type. Two halves that never
    agreed to be in the same place, and the reader got an export of points
    nobody made.

    THE VERTEX COUNTER RUNS ACROSS THE ENTRIES (FR-77), because the plot name
    is `{parameter}{n}` and two entries restarting at 1 would write two plots to
    one name, which the solver takes as the same plot.
    """
    pproc = case.pproc
    if pproc is None:
        return
    vertex = 0
    for probes in pproc.probes:
        # THE PHASE DECIDES WHICH ENTRIES THIS PASS EMITS, because the three
        # verbs do not share one. An entry citing a profile imports it, and
        # `PROBE_POINTS_IMPORT` is an ANALYSIS command, so it waits for the
        # analysis pass whatever the run type is. An entry drawing its own
        # lines places vertices through the fluid plots on an unsteady row,
        # which is INIT, and through the survey line on a steady one, which is
        # analysis again.
        cited = bool(probes.points_file)
        wanted = cited or not unsteady if analysis else not cited and unsteady
        if not wanted:
            # The vertex counter still advances for an entry this pass skips,
            # or the numbering would depend on which pass is running.
            vertex += 0 if cited else len(probes.lines) * probes.points
            continue
        vertex = _emit_one_probe_table(case, script, frames, probes, vertex, unsteady=unsteady)


#: FR-80. Where a cited probe profile is staged for the run to import. It is
#: per SIM and not per point, by the requirement of 2026-09-11: the probe
#: file this package writes for a simulation, and any file a user cites
#: alongside it, both belong in that simulation's `profiles/` folder.
PROBE_PROFILE_DIR = "profiles"

#: FR-91. The columns of the probe positions file, in order, and the ONE home
#: of that vocabulary. The run layer writes the file and the post layer reads
#: it, and until this existed each end spelled the five names for itself: a
#: literal header string on one side and a tuple on the other, with nothing
#: to make them disagree loudly (the architecture lens, 2026-09-11). It lives
#: here because `cases` is the deepest layer both of them already import.
PROBE_POSITION_COLUMNS: tuple[str, ...] = ("PROBE", "X", "Y", "Z", "FRAME")


def _rectangle_points(rectangle, scale: float) -> list[list[float]]:
    """Lay out the grid of a rectangular probe plane, row by row (FR-79).

    Three corners give two edge vectors from `origin`, and the grid runs along
    both with BOTH ENDS INCLUDED, so a declaration of 3 by 4 is twelve points
    and three of its corners are the three declared vertices. The order is v
    fastest within u, which is the reading order of a row of stations.
    """
    origin = list(rectangle.origin)
    edge_u = [b - a for a, b in zip(rectangle.origin, rectangle.along_u, strict=True)]
    edge_v = [b - a for a, b in zip(rectangle.origin, rectangle.along_v, strict=True)]
    out: list[list[float]] = []
    for index_u in range(rectangle.points_u):
        fraction_u = index_u / (rectangle.points_u - 1)
        for index_v in range(rectangle.points_v):
            fraction_v = index_v / (rectangle.points_v - 1)
            out.append(
                [
                    round(
                        (origin[axis] + edge_u[axis] * fraction_u + edge_v[axis] * fraction_v)
                        * scale,
                        5,
                    )
                    for axis in range(3)
                ]
            )
    return out


def _circle_points(circle, scale: float) -> list[list[float]]:
    """Lay out the polar grid of a circular probe plane (FR-79).

    `points_radial` stations from the centre to the rim INCLUDING both, and
    `points_azimuth` around. THE CENTRE APPEARS ONCE rather than once per
    azimuth: a survey that sampled its own centre eight times would weight it
    eight times in anything that averages the file.

    The two in-plane axes are built from the normal by taking the world axis
    least aligned with it, which is the standard way to get a stable basis and
    avoids the degenerate cross product a fixed choice hits when the normal
    happens to be that axis.
    """
    import math

    normal = list(circle.normal)
    length = math.sqrt(sum(value * value for value in normal))
    normal = [value / length for value in normal]
    least = min(range(3), key=lambda axis: abs(normal[axis]))
    seed = [1.0 if axis == least else 0.0 for axis in range(3)]
    first = [
        seed[1] * normal[2] - seed[2] * normal[1],
        seed[2] * normal[0] - seed[0] * normal[2],
        seed[0] * normal[1] - seed[1] * normal[0],
    ]
    span = math.sqrt(sum(value * value for value in first))
    first = [value / span for value in first]
    second = [
        normal[1] * first[2] - normal[2] * first[1],
        normal[2] * first[0] - normal[0] * first[2],
        normal[0] * first[1] - normal[1] * first[0],
    ]

    out: list[list[float]] = []
    for index_r in range(circle.points_radial):
        radius = circle.radius * index_r / (circle.points_radial - 1)
        if radius == 0.0:
            out.append([round(value * scale, 5) for value in circle.center])
            continue
        for index_a in range(circle.points_azimuth):
            angle = 2.0 * math.pi * index_a / circle.points_azimuth
            out.append(
                [
                    round(
                        (
                            circle.center[axis]
                            + radius
                            * (math.cos(angle) * first[axis] + math.sin(angle) * second[axis])
                        )
                        * scale,
                        5,
                    )
                    for axis in range(3)
                ]
            )
    return out


def _emit_one_probe_table(case, script, frames, probes, vertex: int, *, unsteady: bool) -> int:
    """Emit one `[[probes]]` entry, returning the vertex count after it."""
    if not probes.parameters:
        return vertex
    if probes.points_file:
        # FR-80: the entry cites a file the USER wrote rather than drawing its
        # own lines. The points are read by the SOLVER from the staged copy, so
        # this emits the import and nothing else: the package does not parse
        # that file to re-emit it point by point, which would make this package
        # the second author of a survey the user wrote.
        #
        # THE EMISSION IS THE ONE THAT ALREADY EXISTED. `probes.emit_probe_import`
        # has emitted `PROBE_POINTS_IMPORT` since the subpackage was written and
        # nothing under `cases/` had ever called it; a second emitter beside it
        # would be the defect rather than the feature.
        from pyflightstream.probes import emit_probe_import

        staged = f"{PROBE_PROFILE_DIR}/{probes.points_file}"
        emit_probe_import(script, staged)
        return vertex
    if not (probes.lines or probes.rectangles or probes.circles):
        return vertex
    probes = probes.model_copy(update={"frame": _the_probe_frame(case, probes.frame)})
    # A PROBE TABLE NAMES ONE ROTOR'S FRAME, and a row that does not turn
    # that rotor places it nowhere. The same rule the plots and the
    # sections already keep (FR-65): an entry this RUN cannot place is left
    # out, because one artifact serves a row that turns the pusher and a
    # row that turns only the lifters, and only one of them has a
    # PUSHER_SMRP. An entry naming a frame NO ROW could place is still
    # refused below, by `_pproc_frame`, because that cannot come right on
    # another row.
    if (
        EXPANDING_FRAMES.get(probes.frame.strip().upper()) is None
        and _ROTOR_FRAME_SPELLING.search(probes.frame.strip().upper()) is not None
        and frames.get(probes.frame) is None
    ):
        warnings.warn(
            f"case {case.sim_id!r}: the pproc artifact {case.pproc_id!r} lays its probe "
            f"lines in {probes.frame!r}, a frame of a rotor this row does not turn, so "
            "they are left out. A row places the frames of the rotors its motions name, "
            "which is the same rule that lets one artifact serve a wing-body row and a "
            "rotor row.",
            PyflightstreamWarning,
            stacklevel=2,
        )
        return vertex
    frame = _pproc_frame(case, frames, probes.frame, "the probe lines")
    scale = 1.0
    if probes.scale == "rotor_radius":
        scale = _the_radius_the_probe_lines_are_in(case, probes.frame) / 2.0
    for line in probes.lines:
        for step in range(probes.points):
            fraction = step / (probes.points - 1)
            point = [
                round((a + (b - a) * fraction) * scale, 5)
                for a, b in zip(line.start, line.end, strict=True)
            ]
            vertex += 1
            # FR-91. RECORDED BY THE LOOP THAT PLACES IT, so the position a
            # reader is given is the position the solver was given. It is
            # recorded for BOTH run types: a steady export carries its own
            # X, Y and Z and still never names the frame they are in, and a
            # table of coordinates that does not say which frame is as
            # unplaceable as one carrying none.
            script.probe_points.append(
                (vertex, float(point[0]), float(point[1]), float(point[2]), probes.frame)
            )
            if unsteady:
                for parameter in probes.parameters:
                    script.emit(
                        "UNSTEADY_SOLVER_NEW_FLUID_PLOT",
                        frame=frame,
                        parameter=parameter,
                        name=f"{parameter}{vertex}",
                        vertex=" ".join(str(value) for value in point),
                    )

        if not unsteady:
            # FR-81. A STEADY ROW CREATES THE POINTS IT EXPORTS. It has no
            # fluid plots, which is what places a vertex on an unsteady row, so
            # until 0.16.0 it emitted `EXPORT_PROBE_POINTS` and no creation verb
            # at all: the script asked the solver to export a thing nobody
            # made. WHAT THE SOLVER THEN RETURNED IS INFERRED AND NOT MEASURED,
            # and this comment used to assert it. FR-81's measurement is of the
            # EMITTED SCRIPT -- creation verbs none, export present -- which is
            # a fact about this package; what an unpaired export produces at
            # the machine is a solver behaviour no dated probe in this tree
            # covers.
            # That is the same defect as the fifty dummy surface sections, one
            # family over.
            #
            # ONE `NEW_PROBE_LINE` PER DECLARED LINE, with the point count the
            # entry states, rather than one command per vertex: the survey line
            # is what the solver's own vocabulary offers for exactly this, it
            # takes the count and the two ends, and it is verified on four
            # builds. The coordinates are scaled the same way the vertices
            # above are, so a `rotor_radius` entry lands on the same disk in
            # both run types.
            ends = [
                [round(value * scale, 5) for value in line.start]
                + [round(value * scale, 5) for value in line.end]
                for line in probes.lines
            ]
            for first_x, first_y, first_z, last_x, last_y, last_z in ends:
                script.emit(
                    "NEW_PROBE_LINE",
                    numpts=probes.points,
                    x1=first_x,
                    y1=first_y,
                    z1=first_z,
                    x2=last_x,
                    y2=last_y,
                    z2=last_z,
                )

    # FR-79: A RECTANGLE AND A CIRCLE ARE EMITTED POINT BY POINT, by the
    # decision of 2026-09-10: a rectangular or circular plane is always
    # defined point by point. The reason is TRANSPARENCY
    # rather than geometry. On the unsteady path the points reach the solver
    # one at a time whatever the shape was, so emitting a line per grid row on
    # one path and points on the other would make one declaration produce two
    # different exports, which is the thing every requirement of this release
    # is against.
    #
    # BOTH RUN TYPES REACH THIS. An unsteady row places each vertex with its
    # fluid plots; a steady row places it with `NEW_PROBE_POINT`, which is the
    # per-vertex verb beside the survey line.
    lattice: list[list[float]] = []
    for rectangle in probes.rectangles:
        lattice += _rectangle_points(rectangle, scale)
    for circle in probes.circles:
        lattice += _circle_points(circle, scale)
    for point in lattice:
        vertex += 1
        # FR-91, and the lattice reaches here for BOTH run types, so one
        # append covers a rectangle and a circle on either path.
        script.probe_points.append(
            (vertex, float(point[0]), float(point[1]), float(point[2]), probes.frame)
        )
        if unsteady:
            for parameter in probes.parameters:
                script.emit(
                    "UNSTEADY_SOLVER_NEW_FLUID_PLOT",
                    frame=frame,
                    parameter=parameter,
                    name=f"{parameter}{vertex}",
                    vertex=" ".join(str(value) for value in point),
                )
        else:
            script.emit("NEW_PROBE_POINT", x=point[0], y=point[1], z=point[2])
    return vertex


#: THE SHAPE OF A ROTOR'S FRAME NAME, used only to tell a rotor frame this
#: RUN did not create from a frame no row could create. It is deliberately
#: NOT used to say WHOSE frame a name is: `_the_rotor_whose_frame_this_is`
#: answers that by composing the names forward, because a custom frame the
#: reference declares may share a rotor's prefix and reading the shape
#: backward once scaled probe lines to the wrong disk.
_ROTOR_FRAME_SPELLING = re.compile(r"_(SMRP|RMRP\d*)$")


def _the_probe_frame(case: SimCase, stated: str) -> str:
    """Resolve an unstated probe frame to a rotor THIS ROW TURNS (FR-65).

    It was the literal ``PROP_MRP`` until 0.15.0, when a reference described
    one propulsor and one name could stand for it. A name is not enough now,
    because which hub it is depends on the row, so the default is resolved
    here and the artifact states nothing.

    WHICH ROTOR, and this is the part the first fix got wrong. It read the
    rotor a row with no MOTIONS turns, which answers None whenever the
    reference declares more than one, so the name became ``ROTOR_SMRP``, no
    builder created it, and the probe lines were DROPPED behind a warning
    saying the row does not turn that rotor when there is no rotor of that
    name at all (the interface lens of the 0.15.0 release review, on the
    round-two fix). The rotors a row TURNS are the ones its motions name, and
    the clock names which of them the row is about.

    Raises
    ------
    CampaignConfigError
        The row turns several rotors and the artifact states no frame, so
        which of them the lines are laid out in is unanswered. Naming the
        candidates is the useful half of the refusal.
    """
    if stated.strip():
        return stated.strip()
    moved = (_rotor_of(case, record) for record in case.motions)
    turning = [block.alias for block in moved if block is not None]
    if not turning:
        block = _the_rotor_a_flat_row_turns(case)
        if block is not None:
            return f"{block.alias}_SMRP"
        # A ROW THAT TURNS NOTHING lays its lines in the moment frame, which
        # is where an unstated frame put them on a rotorless run before this
        # release too.
        if not case.rotors:
            return "MRP"
        declared = ", ".join(sorted(case.rotors))
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the pproc artifact {case.pproc_id!r} states no frame "
            f"for its probe lines, and the reference declares more than one rotor "
            f"({declared}) while the row moves none of them, so there is no hub to lay "
            "them out about. Write the frame, as <ALIAS>_SMRP."
        )
    if len(set(turning)) == 1:
        return f"{turning[0]}_SMRP"
    # THE CLOCK ALREADY NAMES THE ROTOR THE ROW IS ABOUT, so a row that
    # states it has answered this question too.
    clock = str(_variable(case, CLOCK_MOTION_VARIABLE) or "").strip()
    for alias in turning:
        if alias.casefold() == clock.casefold():
            return f"{alias}_SMRP"
    raise CampaignConfigError(
        f"case {case.sim_id!r}: the pproc artifact {case.pproc_id!r} states no frame for "
        f"its probe lines and this row turns {', '.join(sorted(set(turning)))}, so which "
        "rotor's disk they are laid out over is unanswered. Write the frame in the "
        "artifact, as <ALIAS>_SMRP; an unstated frame is only an answer where one rotor "
        "turns."
    )


def _the_rotor_whose_frame_this_is(case: SimCase, frame: str) -> str | None:
    """Return the alias of the rotor that OWNS ``frame``, or None (FR-62, FR-65).

    COMPOSED FORWARD, never parsed backward. A rotor's frames are exactly
    ``<ALIAS>_SMRP``, ``<ALIAS>_RMRP`` and ``<ALIAS>_RMRP<k>``, so the
    question is answered by building those names and comparing, which is
    what `_frames_the_alias_owns` does one layer up.

    Splitting the NAME on its last underscore instead was the shape this
    replaced, and it answered PUSHER for `PUSHER_TIP`: a custom frame the
    reference declares under any name it likes (FR-72) that merely shares
    a rotor's prefix was read as that rotor's, so probe lines were scaled
    to its disk. That is the failure the caller exists to prevent,
    reintroduced one level down (the architecture lens, 2026-09-10;
    measured: PUSHER_TIP returned the pusher's 1.8 m).
    """
    wanted = frame.strip().casefold()
    for alias, block in case.rotors.items():
        owned = {f"{alias}_SMRP".casefold(), f"{alias}_RMRP".casefold()}
        owned |= {
            f"{alias}_RMRP{number}".casefold()
            for number in range(1, len(block.families_blades) + 1)
        }
        if wanted in owned:
            return alias
    return None


def _the_radius_the_probe_lines_are_in(case: SimCase, frame: str) -> float:
    """Return the diameter a probe table's ``rotor_radius`` is measured against (FR-65).

    THE ROTOR THE LINES ARE LAID OUT ON, which is the one whose frame the
    table names: the nine lines cross the disk of the rotor they are
    measured in, so `frame = "PUSHER_SMRP"` means pusher radii. That
    matters at 0.15.0 and did not before it, because the reference now
    states a diameter PER ROTOR (FR-60): one number for the whole
    configuration cannot be right for a 1.20 m lifter and a 1.80 m pusher
    at once, and reading the configuration's would have laid the reference lifter
    probes out over the pusher's disk without saying so.

    A frame that is not a rotor's falls back to the reference's own
    rotor diameter, which is what every artifact written before this
    release meant and what keeps them reading.
    """
    alias = _the_rotor_whose_frame_this_is(case, frame)
    if alias is not None:
        return case.rotors[alias].diameter_m
    diameter = None if case.reference is None else case.reference.rotor_diameter
    if diameter is None:
        declared = ", ".join(sorted(case.rotors)) or "none"
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the pproc artifact {case.pproc_id!r} lays its probe "
            f"lines out in rotor radii and names the frame {frame!r}, which is not a "
            f"rotor's, so there is no rotor to take a radius from. The rotors the "
            f"reference declares are {declared}, and each carries its own diameter_m; "
            f"name one of their frames (<ALIAS>_SMRP), or state a rotor diameter on "
            'the reference, or write the lines in metres (scale = "m").'
        )
    return diameter


def _pproc_sections(case: SimCase, script: Script, frames: Frames) -> None:
    """Emit one NEW_SURFACE_SECTION_DISTRIBUTION per pproc entry and plane.

    An entry's families are resolved through the opened inventory in the
    order the entry lists them, families the geometry does not carry
    being left out as the reference driver left them out, and an entry resolving
    to none is skipped.

    WHERE THIS IS EMITTED IS NOT THIS DOCSTRING'S TO STATE, and the sentence
    that used to state it here said the OPPOSITE of what the caller does: it
    read "emitted before the solver is initialised", which is the pre-FR-83
    station, and gave the reasoning FR-83 refutes. The station is the caller's
    fact and the call site owns it, with its measurement: `_script_tail` emits
    this between `INITIALIZE_SOLVER` and `START_SOLVER`, which is where the reference
    recorded scripts put it.
    """
    pproc = case.pproc
    if pproc is None or not pproc.sections.distributions:
        return
    inventory = _inventory(script)
    sections = pproc.sections
    for position, entry in enumerate(sections.distributions, start=1):
        # THE SAME RULE AS THE PLOTS (FR-65): a distribution measured in a
        # blade's own axes is one per blade, and one measured in a rotor's
        # is one per rotor. The reference `p010.toml` writes exactly that, over
        # `["lifters", "PUSHER"]`, and means nine distributions.
        for frame_name, families, _label in _pproc_emissions(
            case,
            entry.frame,
            entry.families,
            inventory,
            pproc.is_blade,
            f"section distribution {position}",
            frames,
            blades_only=True,  # FR-75
        ):
            frame = _pproc_frame(case, frames, frame_name, "a section distribution", families)
            indices = [script.resolve_boundary(f, context="pproc section") for f in families]
            if not indices:
                indices = list(range(1, len(inventory) + 1))
            for plane in entry.planes:
                script.emit(
                    "NEW_SURFACE_SECTION_DISTRIBUTION",
                    frame=frame,
                    plane=plane,
                    # FR-76: the entry's own where it states one, the
                    # artifact's where it does not.
                    num_sections=(entry.count if entry.count is not None else sections.count),
                    plot_direction=str(
                        entry.plot_direction
                        if entry.plot_direction is not None
                        else sections.plot_direction
                    ),
                    include_symmetry="ENABLE" if sections.include_symmetry else "DISABLE",
                    surfaces=len(indices),
                    surface_indices=indices,
                )


def _export_block(
    conventions: WorkflowConventions, case: SimCase, script: Script, *, unsteady: bool
) -> None:
    """Export what the study needs, in the order, with the updates first.

    PFS-2029.14.01 and PFS-2029.18. The names come from the row's outputs
    (rendered by the workspace) and each is paired with its verb by suffix,
    so a row that declares the full set of FR-51 gets every kind and a row
    written before this release, declaring a loads table and a log, gets
    exactly what it declared. UPDATE_ALL_SURFACE_SECTIONS,
    COMPUTE_SURFACE_SECTIONAL_LOADS and UPDATE_PROBE_POINTS precede the
    exports whenever a section, sectional-loads or probe export is asked
    for, because an export of sections nobody updated is an export of the
    previous state (the reference driver, flightstreamHorse.py:522-526). The saved
    simulation comes first among the exports, as the reference did, and a build on
    which a kind carries no row is refused by the script layer naming the
    command, which is what require_coverage already checks per workflow.

    The solver log keeps its older spelling: a row that still says which
    of its outputs is the log through LOG_OUTPUT is honoured by
    :func:`_export_log`; a row whose outputs carry a ``_log.txt`` name is
    read by suffix like every other kind.
    """
    names = list(conventions.outputs or case.outputs)
    kinds = classify_outputs(names)
    if "loads" not in kinds:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares outputs {names or 'nothing'} and none of them "
            "is a loads table (a name ending in .txt that is not one of the other "
            "export suffixes). The loads table is the export this package judges a run "
            "by, so every row leaves one; the default outputs name it {point}.txt."
        )
    if any(kind in kinds for kind in ("sections", "sectional_loads", "probes")):
        script.emit("UPDATE_ALL_SURFACE_SECTIONS")
        script.emit("COMPUTE_SURFACE_SECTIONAL_LOADS", "NEWTONS")
        script.emit("UPDATE_PROBE_POINTS")
    declared_log = _variable(case, LOG_OUTPUT_VARIABLE) is not None
    for kind, _, verb, only_unsteady in EXPORT_KINDS:
        if kind not in kinds or (only_unsteady and not unsteady):
            continue
        if kind == "log" and declared_log:
            continue
        script.emit(verb, kinds[kind])
    if declared_log:
        _export_log(conventions, case, script, claimed=(names.index(kinds["loads"]) + 1,))


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
    table, the run completes, and the assessor sends the user to look
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
        # name, and telling its writer why a NAME cannot be used here
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
    # A steady row stating an export threshold is refused there, naming
    # the time loop it lacks (PFS-2031.18); a row stating none returns.
    unsteady_export_threshold(case, conventions)
    _refuse_unregistered_keys(case, "steady")
    _raw_commands(case, script, "control")
    _custom_flags(case, script, "control")
    _raw_commands(case, script, "geometry")
    _custom_flags(case, script, "geometry")
    _open_geometry(case, script)
    _raw_commands(case, script, "setup")
    _custom_flags(case, script, "setup")
    frame = _moment_frame(case, script)
    frames: dict[str, int | None | Mapping[str, int]] = {
        "MRP": frame,
        **_flat_rotor_frames(case, None),
    }
    setup_frames = _setup_frames(case, script)
    frames.update(setup_frames)
    _rotations(case, script, {"MRP": frame, **setup_frames})
    _significant_digits(case, script)
    helpers.free_stream(script)
    _fluid(case, script)
    _settings(case, script)
    _script_tail(conventions, case, script, frame, unsteady=False, frames=frames)


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
#: ADVANCE_RATIO is NOT in this list since 0.11.0 (PFS-2029.19): the reference
#: unsteady wing-body runs stated the advance ratio of the rotor they
#: did not mesh, because it set the azimuthal step and named the point
#: (POLAR-3224_..._J+130), and the name keeps that field. The keys that
#: would turn something are still refused.
ROTORLESS_REFUSED_KEYS: tuple[str, ...] = (
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


# --- PFS-2031.18: exports that begin after a threshold the row states --------
#
# THE DESIGN OF 2026-09-08, written down as GeoversePlan design 67 and
# built here as it was drawn. The solver hands an unsteady action nothing
# about where it is in the run (RPT-041 finding 4), so the run type
# registers TWO actions, in this order: a COMMAND_LINE running a Python
# program the run layer writes, which counts its own invocations in a
# file beside itself and rewrites the second action's file; and a SCRIPT
# action pointing at that file, which the solver re-reads on every
# invocation (RPT-041 finding 1). The file is empty until the count
# reaches the threshold and carries the per-step exports from then on,
# each stamped ``_iteration=N`` by the solver (finding 3). The count is
# the step count exactly, with nothing before the first step (finding
# 2), which is what lets a count stand for a step at all.
#
# The paths are RELATIVE TO THE SIMULATION FOLDER, which is the solver's
# working directory (finding 4, the child's cwd) and the directory the
# main script's own relative exports land in on every tier-3 row. A
# relative registration line is the same on every machine, so the tier-3
# golden pins it; the run layer resolves it against the simulation folder
# when it writes the two files (PFS-2031.13), and the program derives its
# own folder from its own location, so the solver's cwd is not what the
# count depends on. Whether the SOLVER resolves an action's SCRIPT file
# name relative to its cwd is not measured (the probe used absolute
# paths); row 6002 of the tier-3 actions matrix is the measurement.

#: The names the two registration lines carry, in creation order. The
#: solver runs actions in creation order and the order cannot be changed
#: afterwards, so the counter is registered FIRST: it rewrites the file
#: before the SCRIPT action of the same step reads it.
UNSTEADY_COUNTER_ACTION = "pfs_unsteady_counter"
UNSTEADY_EXPORTS_ACTION = "pfs_unsteady_exports"
#: The program, the file it rewrites, and the count it keeps, relative to
#: the simulation folder. Under ``actions/`` and NOT under ``inputs/``:
#: ``inputs/`` is a junction to the workspace geometry library whenever
#: the geometry came from it (PFS-2029.17), and a file written there
#: would land in the library. The two are staged inputs all the same:
#: the record carries their sha256 beside the geometry's.
UNSTEADY_ACTION_PROGRAM = "actions/pfs_unsteady_actions.py"
UNSTEADY_ACTION_SCRIPT = "actions/pfs_unsteady_exports.txt"
UNSTEADY_ACTION_COUNT = "actions/pfs_unsteady_actions.count"
#: The export kinds that describe the WHOLE RUN and are therefore not
#: exported per step: a saved simulation is the full state and is the
#: size that sends every .fsm to cloud storage, the plots file already
#: carries every step, and the log is the run's own history. The per-step
#: set is :data:`~pyflightstream.cases.EXPORT_KINDS` minus these, filtered
#: by the row's outputs, which the pproc artifact's export set rendered;
#: nothing here retypes a verb or a suffix.
WHOLE_RUN_EXPORT_KINDS: tuple[str, ...] = ("simulation", "plots", "log")


@dataclass(frozen=True)
class UnsteadyExportThreshold:
    """The step the per-step exports begin on, and what they export.

    Attributes
    ----------
    stated_form : str
        ``revolutions`` or ``iterations``: the key the row wrote.
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


def _per_step_exports(conventions: WorkflowConventions, case: SimCase) -> str:
    """Return the child script text: the per-step kinds of the row's outputs.

    The names are the row's rendered outputs, the same names the
    end-of-run block exports, and the solver tells the two apart by the
    ``_iteration=N`` it stamps on an action's export (RPT-041 finding 3).
    The verbs are read off :data:`~pyflightstream.cases.EXPORT_KINDS` in
    its order, and the three update commands precede the exports whenever
    a section, sectional-loads or probe export is among them, which is the
    rule :func:`_export_block` follows for the same reason: an export of
    sections nobody updated is an export of the previous state.
    """
    names = list(conventions.outputs or case.outputs)
    kinds = {
        kind: name
        for kind, name in classify_outputs(names).items()
        if kind not in WHOLE_RUN_EXPORT_KINDS
    }
    lines: list[str] = []
    if any(kind in kinds for kind in ("sections", "sectional_loads", "probes")):
        lines += ["UPDATE_ALL_SURFACE_SECTIONS", "COMPUTE_SURFACE_SECTIONAL_LOADS NEWTONS"]
        lines.append("UPDATE_PROBE_POINTS")
    for kind, _, verb, _ in EXPORT_KINDS:
        if kind in kinds:
            lines += [verb, kinds[kind]]
    return "".join(f"{line}\n" for line in lines)


def _rotor_clock(case: SimCase) -> TimeStepping:
    """Resolve the rotor run type's clock, off the fastest rotor where the row states several."""
    if case.motions:
        speeds = [rotor_speed(_motion_view(case, record)) for record in case.motions]
        speed = max(speeds, key=lambda each: abs(each.rpm))
    else:
        speed = rotor_speed(case)
    return rotor_time_stepping(case, speed=speed)


def unsteady_export_threshold(
    case: SimCase, conventions: WorkflowConventions | None = None
) -> UnsteadyExportThreshold | None:
    """Resolve the export threshold a row states, or None when it states none.

    Called by the two unsteady builders before their first emission, so a
    refusal leaves the script as it was, and again by the run layer, which
    writes the program from it: it is a function of the case alone, so the
    two calls agree.

    Parameters
    ----------
    case : SimCase
        The case; its variables may carry ``EXPORT_UNSTEADY_AFTER_REV`` or
        ``EXPORT_UNSTEADY_AFTER_ITER``.
    conventions : WorkflowConventions, optional
        The rendered output names; defaults to the case's own.

    Returns
    -------
    UnsteadyExportThreshold or None
        None when the row states neither key, which is every row written
        before 0.13.0.

    Raises
    ------
    CampaignConfigError
        If both keys are stated, naming both; if the row names the steady
        run type, which has no time loop; if the revolutions form is
        stated on the run type that turns nothing, naming the iterations
        form that would work; if the value is not a positive number; or if
        the threshold lies beyond the run, naming both numbers.
    """
    stated = {
        key: text
        for key in (EXPORT_UNSTEADY_AFTER_REV_VARIABLE, EXPORT_UNSTEADY_AFTER_ITER_VARIABLE)
        if (text := _variable(case, key)) is not None
    }
    if not stated:
        return None
    if len(stated) == 2:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {EXPORT_UNSTEADY_AFTER_REV_VARIABLE} and "
            f"{EXPORT_UNSTEADY_AFTER_ITER_VARIABLE} both. The per-step exports begin at "
            "ONE step, stated in revolutions of the rotor or in time iterations; two "
            "statements would be two steps nobody keeps in agreement. Keep one."
        )
    key = next(iter(stated))
    workflow = select_workflow(case)
    if workflow == "steady":
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {key} and names the steady run type, which has "
            "no time loop: an unsteady solver action runs after each time step, and a "
            "steady solve has none. State the key on an unsteady run type, or drop it."
        )
    if workflow == "unsteady_rotor":
        stepping = _rotor_clock(case)
    else:
        stepping = unsteady_time_stepping(case)
    per_revolution = stepping.steps_per_revolution
    number: float
    if key == EXPORT_UNSTEADY_AFTER_REV_VARIABLE:
        number = _required_float(case, key, quantity="export threshold", unit="revolutions")
        if workflow != "unsteady_rotor" or per_revolution is None:
            hint = ""
            if per_revolution is not None:
                hint = (
                    f" This row's azimuthal clock makes {number} revolutions "
                    f"{math.ceil(number * per_revolution - 1e-9)} steps."
                )
            raise CampaignConfigError(
                f"case {case.sim_id!r} states {key} and names a run type with no rotor "
                "clock: a revolution is counted on a rotor the run turns, and this one "
                f"turns nothing. State '{EXPORT_UNSTEADY_AFTER_ITER_VARIABLE}: <steps>' "
                f"instead.{hint}"
            )
        form = "revolutions"
        first_step = math.ceil(number * per_revolution - 1e-9)
    else:
        number = _required_int(case, key, quantity="export threshold", unit="time steps")
        form = "iterations"
        first_step = int(number)
    if number <= 0:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {key} as {number}, and the threshold is the step "
            "the exports begin on, so it is a positive number. "
            f"'{EXPORT_UNSTEADY_AFTER_ITER_VARIABLE}: 1' exports from the first step."
        )
    if first_step > stepping.time_iterations:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {key} as {number}, which is step {first_step}, "
            f"and the run is {stepping.time_iterations} steps long, so no step would "
            "reach the threshold and nothing would be exported. Lower it, or lengthen "
            "the run."
        )
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
        exports=_per_step_exports(conventions or WorkflowConventions.for_case(case), case),
    )


def unsteady_action_command_line(interpreter: str = sys.executable) -> str:
    """Return the shell line the COMMAND_LINE action runs: the interpreter, then the program.

    Both quoted, because an interpreter path with a space in it is one
    argument. The interpreter is the one building the script, which is
    the one the run layer names when it writes the program, so the line
    the solver runs and the program it runs agree on which Python.
    """
    return f'"{interpreter}" "{UNSTEADY_ACTION_PROGRAM}"'


def _unsteady_actions(script: Script, threshold: UnsteadyExportThreshold | None) -> None:
    """Register the counter and the exports file, in that order, or nothing.

    The SCRIPT file is parked EMPTY: until the count reaches the threshold
    the solver must find a file with no command in it, and the run layer
    writes what is parked before the solver starts (PFS-2031.13). A build
    that does not document the action command is refused by the emitter,
    naming the command and the builds that do.
    """
    if threshold is None:
        return
    helpers.unsteady_action(
        script,
        name=UNSTEADY_COUNTER_ACTION,
        kind="COMMAND_LINE",
        filename=unsteady_action_command_line(),
    )
    helpers.unsteady_action(
        script,
        name=UNSTEADY_EXPORTS_ACTION,
        kind="SCRIPT",
        filename=UNSTEADY_ACTION_SCRIPT,
        action_script="",
    )


def _build_unsteady(case: SimCase, script: Script, conventions: WorkflowConventions) -> None:
    """Build an unsteady point of a body that does not move.

    The rotor builder without the rotor: no coordinate system, no
    motion, and a clock stated directly rather than derived from a
    speed. Both refusals run before the first emission.
    """
    _refuse_rotor_keys_on_a_rotorless_run(case)
    _refuse_wake_termination_without_a_rotor(case)
    threshold = unsteady_export_threshold(case, conventions)
    _refuse_unregistered_keys(case, "unsteady")
    _raw_commands(case, script, "control")
    _custom_flags(case, script, "control")
    _raw_commands(case, script, "geometry")
    _custom_flags(case, script, "geometry")
    _open_geometry(case, script)
    _raw_commands(case, script, "setup")
    _custom_flags(case, script, "setup")
    frame = _moment_frame(case, script)
    rotor_frame = _rotor_frame(case, script)
    rotor_frames = _flat_rotor_frames(case, rotor_frame)
    frames: dict[str, int | None | Mapping[str, int]] = {"MRP": frame, **rotor_frames}
    setup_frames = _setup_frames(case, script)
    frames.update(setup_frames)
    _rotations(case, script, {"MRP": frame, **rotor_frames, **setup_frames})
    _pproc_plots(case, script, frames)
    _pproc_probes(case, script, frames, unsteady=True, analysis=False)
    _significant_digits(case, script)
    helpers.free_stream(script)
    _fluid(case, script)
    stepping = unsteady_time_stepping(case)
    helpers.unsteady_solver(
        script,
        time_iterations=stepping.time_iterations,
        delta_time=stepping.delta_time_s,
    )
    # The wake termination in STEPS is the one this run type can state
    # (PFS-2030.03.04); the revolutions form was refused above.
    _settings(case, script, wake_termination_time_steps=case.solver.wake_termination_steps)
    _unsteady_actions(script, threshold)
    _script_tail(conventions, case, script, frame, unsteady=True, frames=frames)


def _build_unsteady_rotor(case: SimCase, script: Script, conventions: WorkflowConventions) -> None:
    """Build a blade-resolved rotor run: open, rotor frame, motion, time loop.

    The open is FIRST and only where the case names a geometry
    (:func:`_open_geometry`). It has to precede the coordinate system
    rather than merely appear somewhere: ``OPEN`` replaces the whole
    simulation state, so a frame created before it would be discarded
    with nothing said, and the rotary motion would then turn about a
    frame that no longer exists.
    """
    # Resolved before the first emission, as every refusal of a row key
    # is; a row stating no threshold pays nothing here.
    threshold = unsteady_export_threshold(case, conventions)
    _refuse_unregistered_keys(case, "unsteady_rotor")
    _raw_commands(case, script, "control")
    _custom_flags(case, script, "control")
    _raw_commands(case, script, "geometry")
    _custom_flags(case, script, "geometry")
    _open_geometry(case, script)
    _raw_commands(case, script, "setup")
    _custom_flags(case, script, "setup")
    _refuse_an_unanswered_hub(case)
    frame = _moment_frame(case, script)
    # THE ROTOR'S HUB FRAME, named <ALIAS>_SMRP for the rotor the reference
    # declares and placed at its hub, unless the row states ROTOR_ORIGIN.
    #
    # NOT ON A MOTIONS ROW. Each record creates its own rotor's hub frame,
    # under the same <ALIAS>_SMRP name, so creating one here too put ONE
    # NAME AT TWO INDICES and a pproc entry citing it resolved to whichever
    # the frame table happened to hold. The package-level frame this
    # replaced had a different name and could not collide, which is why the
    # duplicate arrived with the rename (measured on the tour's rotor row).
    rotor_frame = None if case.motions else _rotor_frame(case, script)
    if rotor_frame is None and not case.motions:
        # NOTHING SAYS WHERE THE ROTOR IS: no block, no recorded position,
        # no ROTOR_ORIGIN. The frame goes at the origin, which is what this
        # builder has always done for a row that states nothing, and the
        # NAME is the alias-shaped default rather than a package-level one.
        rotor_frame = helpers.coordinate_frame(
            script,
            name=_the_flat_frame_name(case),
            origin=(0.0, 0.0, 0.0),
            x_axis=(1.0, 0.0, 0.0),
            y_axis=(0.0, 1.0, 0.0),
            label="rotor",
        )
    setup_frames = _setup_frames(case, script)
    if case.motions:
        _rotor_motions(conventions, case, script, frame, rotor_frame, threshold, setup_frames)
        return
    # NARROWED, not asserted: the branch above raises when this is None and
    # the row states no MOTIONS, and a row that states them returned there.
    assert rotor_frame is not None
    blade_frames = _blade_frames(case, script, rotor_frame)
    rotor_frames = _flat_rotor_frames(case, rotor_frame)
    frames: dict[str, int | None | Mapping[str, int]] = {
        "MRP": frame,
        **rotor_frames,
        "BLADE_AXIS": blade_frames or None,
        # THE SAME FRAMES UNDER THEIR ROTOR'S NAMES. A flat row creates
        # BladeAxis<k>, which is what its goldens carry; a pproc entry
        # citing LOCAL_AXIS expands to <ALIAS>_RMRP<k>, and without this
        # the entry resolved on a MOTIONS row and silently on nothing here.
        # One frame, two names, which is what `named` already does for a
        # record's own hub.
        **_the_blade_frames_under_their_rotors_names(case, blade_frames),
    }
    frames.update(setup_frames)
    _rotations(
        case,
        script,
        {"MRP": frame, **rotor_frames, **setup_frames},
        followers={name: sorted(blade_frames.values()) for name in rotor_frames},
        spinning={name: _blade_indices(case, script) for name in rotor_frames},
    )
    _pproc_plots(case, script, frames)
    _pproc_probes(case, script, frames, unsteady=True, analysis=False)
    _significant_digits(case, script)
    helpers.free_stream(script)
    _fluid(case, script)
    # RESOLVED ONCE AND THREADED. The ratio was previously converted
    # twice per case, here and again for the clock, which is the saving
    # the `speed` parameter was added for and was not collecting.
    speed = rotor_speed(case)
    # The blade axis frames turn with the blades (PFS-2029.11.03); with
    # none created the motion keeps its every-frame default, as before.
    emit_rotor_motion(
        case,
        script,
        frame="rotor",
        speed=speed,
        moving_frames=sorted(blade_frames.values()) if blade_frames else "all",
    )
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
    _unsteady_actions(script, threshold)
    _script_tail(conventions, case, script, frame, unsteady=True, frames=frames)


def _refuse_one_rotor_moved_twice(case: SimCase, rotors: Sequence[RotorBlock | None]) -> None:
    """Refuse a row whose MOTIONS list names one rotor more than once.

    ONE ROTOR HAS ONE SET OF FRAMES. Two records naming one alias built
    ``<ALIAS>_SMRP`` twice, at two indices, and the name table kept the
    LAST, so the script carried the name twice and the two motions turned
    about different coordinate systems. It was masked by a label collision
    that fires only when the rotor's blade families are in the mesh, and
    that refusal names neither the alias nor the case; on a sector mesh
    carrying none of them nothing refused at all (the QA lens of the 0.15.0
    release review, measured on the emitted script).

    A ROW THAT MOVES ONE ROTOR TWICE IS ASKING FOR TWO SPEEDS FOR ONE
    THING, which is the shape this package refuses wherever a row states a
    rotor twice. If two speeds are wanted in one run, they are two rotors.

    Raises
    ------
    CampaignConfigError
        A rotor alias appears in more than one record, naming it.
    """
    seen: dict[str, int] = {}
    for block in rotors:
        if block is None:
            continue
        seen[block.alias] = seen.get(block.alias, 0) + 1
    twice = sorted(alias for alias, count in seen.items() if count > 1)
    if not twice:
        return
    raise CampaignConfigError(
        f"case {case.sim_id!r} states {MOTIONS_VARIABLE} naming "
        f"{', '.join(repr(alias) for alias in twice)} more than once. One rotor has one "
        "hub and one set of frames, so two records naming it ask for two speeds for one "
        "thing and the script would carry its frame name twice at two indices. Write one "
        "record per rotor; if two speeds are wanted in one run, they are two rotors and "
        "the reference declares two blocks."
    )


def _rotor_motions(
    conventions: WorkflowConventions,
    case: SimCase,
    script: Script,
    frame: int | None,
    rotor_frame: int | None,
    threshold: UnsteadyExportThreshold | None,
    setup_frames: Mapping[str, int],
) -> None:
    """Finish a rotor script whose row states N motions (PFS-2029.11.03).

    N records, N motions, each with its own fixed frame at its hub and its
    own moving frame attached to it by ``SET_MOTION_MOVING_FRAMES``
    (documented on every build, SRC-003 p.333, and verified on none).

    THE FRAMES TAKE THE ROTOR'S ALIAS AS THEIR RADICAL (FR-62, the design
    of 2026-09-10): ``<ALIAS>_SMRP`` at the hub, static; ``<ALIAS>_RMRP``
    turning with the motion; and ``<ALIAS>_RMRP<k>`` per blade of the
    block's ``families_blades``, turning with blade k and numbered from
    the ``blade1`` datum. A family of ``families_general`` gets no frame
    of its own: its local frame IS the rotor's, which is what makes the
    spinner ride the hub. The names a record's frames had at 0.14.0,
    ``PROP_MRP<k>`` and ``RotorAxis<k>``, do NOT resolve: they were
    positional, so a pproc entry citing one silently followed the ORDER of
    the MOTIONS list, and an entry citing one now is refused naming the
    shape to write.

    There is no package-level rotor frame. The time step follows the motion
    ``CLOCK_MOTION`` names, and the fastest rotor when a row names none
    (FR-64).
    """
    views = [_motion_view(case, record) for record in case.motions]
    rotors = [_rotor_of(case, record) for record in case.motions]
    _refuse_one_rotor_moved_twice(case, rotors)
    # A RECORD NAMING NO ROTOR takes the default radical, `ROTOR<k>`, which
    # is the alias-shaped name of an unnamed rotor. It does NOT keep the
    # 0.14.0 names: those were positional and went with the package-level
    # frame. Only a matrix converted with no workspace produces one, because
    # a record reaching the builder through a workspace names a rotor.
    radicals = [(rotor.alias if rotor is not None else None) for rotor in rotors]
    moving: list[int] = []
    hubs: list[int] = []
    blade_frames: dict[str, int] = {}
    for number, (view, rotor, radical) in enumerate(
        zip(views, rotors, radicals, strict=True), start=1
    ):
        origin = _origin(view)
        # EVERY FRAME CARRIES ITS ROTOR'S ALIAS. A record naming no rotor
        # used to fall back to ROTOR_MRP<k> and RotorAxis<k>, positional
        # names that only mean anything beside the row that made them; the
        # record that produced them is refused before this point.
        # EVERY FRAME CARRIES A RADICAL, AND IT IS THE ROTOR'S ALIAS. A
        # record naming no rotor takes the default radical and its position;
        # the positional PROP_MRP<k> and RotorAxis<k> are gone with the
        # one-propulsor assumption that made them readable.
        stem = radical or f"{UNNAMED_ROTOR_RADICAL}{number}"
        hub_name = f"{stem}_SMRP"
        moving_name = f"{stem}_RMRP"
        hubs.append(
            helpers.coordinate_frame(
                script,
                name=hub_name,
                origin=origin,
                x_axis=(1.0, 0.0, 0.0),
                y_axis=(0.0, 1.0, 0.0),
                label=f"rotor:{number}",
            )
        )
        moving.append(
            helpers.coordinate_frame(
                script,
                name=moving_name,
                origin=origin,
                x_axis=(1.0, 0.0, 0.0),
                y_axis=(0.0, 1.0, 0.0),
                label=f"rotor_moving:{number}",
            )
        )
        if rotor is not None:
            # `rotor.alias`, not `radical`: they are the same string here
            # and only this one is visibly non-None, the other having been
            # zipped out of a list that carries a None for every record
            # naming no rotor.
            blade_frames.update(_rotor_blade_frames(script, rotor, hubs[-1], rotor.alias, view))
    frames: dict[str, int | None | Mapping[str, int]] = {
        "MRP": frame,
        "BLADE_AXIS": None,
    }
    frames.update(setup_frames)
    # A record's own frames are citable by the names the solver shows
    # (<ALIAS>_SMRP, <ALIAS>_RMRP, ...), and a rotor's moving frame follows
    # its hub frame the way the blade frames follow it (PFS-2034.02).
    named: dict[str, int | None] = {"MRP": frame, **setup_frames}
    followers: dict[str, list[int]] = {}
    spinning: dict[str, list[int]] = {}
    labels = script.entities.labels("boundaries")
    for number, (hub, axis, view, radical) in enumerate(
        zip(hubs, moving, views, radicals, strict=True), start=1
    ):
        # ONE NAME PER FRAME, and it is the rotor's alias. The positional
        # PROP_MRP<k> and RotorAxis<k> stood beside it until 0.15.0 and are
        # gone: they read as a name and were an index, so a pproc entry
        # citing one silently followed the ORDER of the MOTIONS list.
        stem = radical or f"{UNNAMED_ROTOR_RADICAL}{number}"
        named[f"{stem}_SMRP"] = hub
        named[f"{stem}_RMRP"] = axis
        followers[f"{stem}_SMRP"] = [axis]
        cell = str(_variable(view, MOVING_BOUNDARIES_VARIABLE) or "")
        # Names only: a token that is not a name is the motion's own to
        # refuse or warn about, when it is emitted below.
        turning = sorted(
            {
                index
                for token in cell.split(",")
                if token.strip()
                for index in _resolve_token(case, token.strip(), labels)
            }
        )
        spinning[f"{stem}_SMRP"] = turning
    # THE BLADE FRAMES JOIN `named` BEFORE THE ROTATIONS, not after them.
    # They were merged into `frames` on the line below the call, which is
    # after `_rotations` has run, so a rotation could not cite one and,
    # once the alias carried its own frames (FR-71), could not TURN one
    # either: a row turning a rotor left its per-blade frames behind, which
    # is the same defect the release fixed one layer up for the motion.
    # ONLY THE FRAME-NAMED HALF. `_rotor_blade_frames` returns two keys per
    # blade, the frame's own `<ALIAS>_RMRP<k>` and the blade's mesh FAMILY,
    # because a pproc entry may cite either. Merging both put family names
    # into the frame namespace, so `AXIS: Blade_1-Y` resolved as a
    # coordinate system and the refusal listing "the frames this case
    # defines" taught a vocabulary that does not exist (the architecture
    # lens, 2026-09-10; measured: it was accepted).
    named.update({name: index for name, index in blade_frames.items() if "_RMRP" in name})
    _rotations(case, script, named, followers=followers, spinning=spinning)
    # The pproc entries cite a rotor's frames by the same names (the reference p001
    # of 2026-09-09: PUSHER_X in ROTOR_MRP2 while the lifters spin).
    frames.update({name: index for name, index in named.items() if index is not None})
    frames.update(blade_frames)
    _pproc_plots(case, script, frames)
    _pproc_probes(case, script, frames, unsteady=True, analysis=False)
    _significant_digits(case, script)
    helpers.free_stream(script)
    _fluid(case, script)
    speeds = [rotor_speed(view) for view in views]
    for number, (view, radical) in enumerate(zip(views, radicals, strict=True), start=1):
        # THE BLADE FRAMES TURN WITH THE BLADES, and until this line they
        # were created and then stood still: the payload carried the
        # rotor's own moving frame alone, so a per-blade product would
        # have been read in a frame that never moved. The technical
        # writing lens named the measurement rather than the outcome, and
        # the measurement said the docstring overstated (2026-09-10).
        turning = [moving[number - 1]]
        if radical:
            turning += sorted(
                {
                    index
                    for name, index in blade_frames.items()
                    if name.startswith(f"{radical}_RMRP")
                }
            )
        emit_rotor_motion(
            view,
            script,
            frame=f"rotor:{number}",
            speed=speeds[number - 1],
            moving_frames=turning,
        )
    stepping = rotor_time_stepping(case, speed=_clock_speed(case, views, speeds))
    helpers.unsteady_solver(
        script,
        time_iterations=stepping.time_iterations,
        delta_time=stepping.delta_time_s,
    )
    _settings(case, script, wake_termination_time_steps=_wake_termination(case, stepping))
    _unsteady_actions(script, threshold)
    _script_tail(conventions, case, script, frame, unsteady=True, frames=frames)


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
                f"{CLOCK_MOTION_VARIABLE}. A row that names its rotors by alias is "
                "refused without it since 0.15.0, and this release refuses it here "
                "too: the promise that the flat form was exempt until 0.17.0 was "
                "written in 0.15.0 and 0.15.0 has not shipped, so no workspace was "
                "ever told it held."
            )
        return fastest
    token = str(named).strip()
    for view, speed in zip(views, speeds, strict=True):
        owner = str(_variable(view, MOVING_BOUNDARIES_VARIABLE) or "")
        if owner.casefold() == token.casefold():
            return speed
    stated = ", ".join(str(_variable(view, MOVING_BOUNDARIES_VARIABLE) or "") for view in views)
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
    if row_ratio is not None and not (RPM_VARIABLE in record or ADVANCE_RATIO_VARIABLE in record):
        variables[ADVANCE_RATIO_VARIABLE] = row_ratio
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
        variables[ROTOR_AXIS_VARIABLE] = rotor.axis
        variables[ROTOR_ORIGIN_VARIABLE] = "{},{},{}".format(*rotor.origin)
        variables[BLADES_VARIABLE] = str(rotor.blade_count)
        if RPM_VARIABLE not in record:
            variables[RPM_SIGN_VARIABLE] = str(rotor.rpm_sign)
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


def _rotor_of(case: SimCase, record: Mapping[str, str]) -> RotorBlock | None:
    """Return the rotor a motion record names by alias, or None when it names none.

    A record citing a word the reference does not declare as a rotor is
    refused here rather than at the boundary resolver, because the
    resolver's message would be about a mesh family and the mistake is
    about a rotor.
    """
    alias = record.get(MOVING_BC_ALIAS_VARIABLE)
    if alias is None:
        return None
    token = str(alias).strip()
    rotor = case.rotors.get(token) or next(
        (block for name, block in case.rotors.items() if name.casefold() == token.casefold()),
        None,
    )
    if rotor is None:
        declared = ", ".join(sorted(case.rotors)) or "none"
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {MOVING_BC_ALIAS_VARIABLE}: {token}, and the "
            f"reference artifact declares no rotor of that name. The rotors it declares "
            f"are {declared}. A rotor is a block of the reference whose kind is rotor, "
            "and the block's name is the word a row moves."
        )
    return rotor


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
#:
#: THE ``keys`` TUPLES BELOW ARE THE ROW'S VOCABULARY (PFS-2008.02.01),
#: each key typed once and the wider run types extending the narrower:
#: ``unsteady`` reads everything ``steady`` reads plus a clock and a
#: window, ``unsteady_rotor`` everything ``unsteady`` reads plus the
#: rotor. ``VELOCITY`` is registered on all three and is unreachable from
#: a matrix row (GOAL-012): the mandatory FLIGHT_CONDITION column resolves
#: the velocity onto the case and ``_velocity`` reads that first, so the
#: key is read for a case authored in Python and nowhere else.
#: ``ADVANCE_RATIO`` is registered on all three because the point NAME
#: reads it on every case (``J<J*100>``, PFS-2029.19) and the export
#: names carry it into the script. ``LOG_OUTPUT`` is read by every
#: export block and refused on a matrix row by the reader since 0.11.0,
#: so it is reachable from Python alone, like ``VELOCITY``.
_STEADY_KEYS: tuple[str, ...] = (
    GEOMETRY_VARIABLE,
    SYMMETRY_VARIABLE,
    # FR-66: registered on every run type, because whether the solver
    # reports the sector's loads or the wheel's is a per-row choice
    # wherever a mirrored or periodic mesh is opened, not a rotor matter.
    SYMMETRY_LOADS_VARIABLE,
    # FR-69: the two angles the FLIGHT_CONDITION cell states and the
    # matrix reader puts on the case. They are registered because the key
    # guard refuses ANY variable no run type reads, so a row stating the
    # incidence it is not sweeping would reach its builder and be refused
    # as a key of no run type (the architecture lens of 2026-09-10). They
    # belong to every run type: every point has an attitude.
    ALPHA_VARIABLE,
    BETA_VARIABLE,
    # PFS-2035.13: the command line writes this one onto the case, so it
    # is registered on every run type for the same reason the two angles
    # are, and it is refused in a matrix CELL by the reader, so it stays a
    # choice of the invocation and never becomes a property of the row.
    IGNORE_MISSING_FAMILIES_VARIABLE,
    PERIODIC_COPIES_VARIABLE,
    BASE_REGIONS_VARIABLE,
    ROTATE_VARIABLE,
    VELOCITY_VARIABLE,
    ADVANCE_RATIO_VARIABLE,
    LOG_OUTPUT_VARIABLE,
)
_UNSTEADY_KEYS: tuple[str, ...] = (
    *_STEADY_KEYS,
    DELTA_TIME_VARIABLE,
    TIME_ITERATIONS_VARIABLE,
    DELTA_THETA_VARIABLE,
    REVOLUTIONS_VARIABLE,
    WINDOW_DEGREES_VARIABLE,
    WINDOW_STEPS_VARIABLE,
    WINDOW_REVOLUTIONS_VARIABLE,
    BLADES_VARIABLE,
    EXPORT_UNSTEADY_AFTER_ITER_VARIABLE,
)
_UNSTEADY_ROTOR_KEYS: tuple[str, ...] = (
    *_UNSTEADY_KEYS,
    # FR-64: which of the row's motions owns the time step.
    CLOCK_MOTION_VARIABLE,
    RPM_VARIABLE,
    RPM_SIGN_VARIABLE,
    ROTOR_AXIS_VARIABLE,
    ROTOR_ORIGIN_VARIABLE,
    ROTOR_SHEDDING_VARIABLE,
    MOVING_BOUNDARIES_VARIABLE,
    MOTIONS_VARIABLE,
    EXPORT_UNSTEADY_AFTER_REV_VARIABLE,
)

#: The converter's namespace in the case variables (``matrix_ref``,
#: ``matrix_workflow`` and the rest), written over the cell after the
#: cell is read and never by a user; :data:`WORKFLOW_KEY` is one of them.
#: THE PREFIX THE MATRIX CONVERTER PUTS ON ITS OWN KEYS, so a reader can
#: tell a key the row wrote from one the conversion added. PUBLIC because
#: `workspace.inputs` asks it whether a custom flag's name would collide
#: with one, and a private name crossing a public sibling is a layer
#: boundary crossed for a helper (the layer guard of test_digest.py).
CONVERTER_PREFIX = "matrix_"


def _refuse_unregistered_keys(case: SimCase, name: str) -> None:
    """Refuse a row stating a key the run type does not register.

    PFS-2008.02.01, measured on 2026-09-08: a one-row copy of the tier-3
    tour with ``FOO_BAR: 1`` appended planned READY on every point, and
    the run would have spent a seat on a row stating something the
    script does not carry. The refusal names the case (its ``sim_id`` is
    the matrix POL), the run type, every key outside the vocabulary with
    the run types that DO read it, and the keys this run type registers.

    CALLED BY EACH BUILDER AFTER ITS OWN REFUSALS AND BEFORE ITS FIRST
    EMISSION, not by :func:`build_script` ahead of the builder, and the
    placement is the point: a rotor key on the run type that turns
    nothing, or an export threshold on the run type with no time loop,
    is refused by the builder's own sentence, which says WHY the key
    cannot be honored there; this check is the general rule behind
    those sentences and catches what they do not name.

    A row selected through its RECIPE keeps its keys: a LEGACY row whose
    RECIPE code maps to a run type, or a case authored in Python naming
    the type as its recipe, is the recipe path, and the recipe is the
    reader of its keys (the rule of 2026-09-08, design 68). The
    converter's own ``matrix_`` keys and the workspace's
    ``ROTOR_ORIGIN_POINT`` are not the row's and are left alone.
    """
    if _workflow_cell(case) is None:
        return
    workflow = WORKFLOWS[name]
    # A FLAG'S OWN WORD IS A KEY THE ROW MAY STATE (PFS-2035.20). The
    # setup declared it, so it is registered by declaration rather than by
    # the run type's table, and refusing it here would refuse the one key
    # the preset just said the row could write.
    declared = {flag.name.strip().casefold() for flag in case.flags}
    stated = sorted(
        key
        for key in case.variables
        if not key.startswith(CONVERTER_PREFIX)
        and key != ROTOR_ORIGIN_POINT_KEY
        and key not in workflow.keys
        and key.strip().casefold() not in declared
    )
    if not stated:
        return
    described = []
    for key in stated:
        readers = [name for name, other in WORKFLOWS.items() if key in other.keys]
        described.append(
            f"{key} (a key of {', '.join(readers)})" if readers else f"{key} (a key of no run type)"
        )
    raise CampaignConfigError(
        f"case {case.sim_id!r} names the run type {workflow.name!r} and states "
        f"{', '.join(described)}, which that run type does not register. A key nothing "
        "reads would change nothing about the run while reading as though it had, so it "
        f"is refused rather than ignored. The keys {workflow.name!r} registers are: "
        f"{', '.join(sorted(workflow.keys))}. A LEGACY row keeps its own keys, because its "
        "RECIPE is their reader; docs/workspace-and-workflows.md says what each key means."
    )


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
            "NEW_SURFACE_SECTION_DISTRIBUTION",
            "INITIALIZE_SOLVER",
            "START_SOLVER",
            "UPDATE_ALL_SURFACE_SECTIONS",
            "COMPUTE_SURFACE_SECTIONAL_LOADS",
            "UPDATE_PROBE_POINTS",
            "SAVEAS",
            "EXPORT_SOLVER_ANALYSIS_SPREADSHEET",
            "EXPORT_SOLVER_ANALYSIS_TECPLOT",
            "EXPORT_ALL_SURFACE_SECTIONS",
            "EXPORT_SURFACE_SECTIONAL_LOADS",
            "EXPORT_PROBE_POINTS",
            "EXPORT_LOG",
            "CLOSE_FLIGHTSTREAM",
        ),
        builder=_build_steady,
        keys=_STEADY_KEYS,
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
            "UNSTEADY_SOLVER_NEW_FORCE_PLOT",
            "UNSTEADY_SOLVER_NEW_FLUID_PLOT",
            "NEW_SURFACE_SECTION_DISTRIBUTION",
            "INITIALIZE_SOLVER",
            "START_SOLVER",
            "UPDATE_ALL_SURFACE_SECTIONS",
            "COMPUTE_SURFACE_SECTIONAL_LOADS",
            "UPDATE_PROBE_POINTS",
            "SAVEAS",
            "EXPORT_SOLVER_ANALYSIS_SPREADSHEET",
            "EXPORT_SOLVER_ANALYSIS_TECPLOT",
            "EXPORT_ALL_SURFACE_SECTIONS",
            "EXPORT_SURFACE_SECTIONAL_LOADS",
            "EXPORT_PROBE_POINTS",
            "UNSTEADY_SOLVER_EXPORT_PLOTS",
            "EXPORT_LOG",
            "CLOSE_FLIGHTSTREAM",
        ),
        builder=_build_unsteady,
        keys=_UNSTEADY_KEYS,
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
            "UNSTEADY_SOLVER_NEW_FORCE_PLOT",
            "UNSTEADY_SOLVER_NEW_FLUID_PLOT",
            "NEW_SURFACE_SECTION_DISTRIBUTION",
            "INITIALIZE_SOLVER",
            "START_SOLVER",
            "UPDATE_ALL_SURFACE_SECTIONS",
            "COMPUTE_SURFACE_SECTIONAL_LOADS",
            "UPDATE_PROBE_POINTS",
            "SAVEAS",
            "EXPORT_SOLVER_ANALYSIS_SPREADSHEET",
            "EXPORT_SOLVER_ANALYSIS_TECPLOT",
            "EXPORT_ALL_SURFACE_SECTIONS",
            "EXPORT_SURFACE_SECTIONAL_LOADS",
            "EXPORT_PROBE_POINTS",
            "UNSTEADY_SOLVER_EXPORT_PLOTS",
            "EXPORT_LOG",
            "CLOSE_FLIGHTSTREAM",
        ),
        builder=_build_unsteady_rotor,
        keys=_UNSTEADY_ROTOR_KEYS,
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
