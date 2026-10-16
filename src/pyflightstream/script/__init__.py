"""The validating FlightStream script builder.

Pipeline role: turns typed Python calls into the ASCII script text the
solver executes, validating every emission against the per-version
command database before a single line reaches FlightStream. Errors
happen at build time with manual citations, because solver-side
failures are silent or cryptic.

A :class:`Script` is an ordinary object bound to one FlightStream
version; two scripts coexist safely, and there is no module-level
state. Emission is checked in order: command exists in the version,
command is not recorded broken there, argument binding and types, enum
membership, count-versus-list consistency, phase ordering, and cross
references. The ``raw()`` escape hatch bypasses validation and flags
the script for the run manifest.

A command whose per-version record is ``broken`` is refused by default
(FR-48), because a probe measured that it does not do what the manual
says, so emitting it hands the run a wrong number rather than an
error. AIR_ALTITUDE on 26.120 is the sharp case: the licensed sweeps observed
the 5000 FOOT standard density where 5000 metres was asked for, so the
METERS argument read as ignored and the altitude the script asked for
would not be the altitude solved, with nothing in the run saying so
because the script was fully validated.
Refusing to emit it is the only place that fact can still reach the
caller. :meth:`Script.allow_broken` is the recorded way through the
refusal, and the QA probe layer is its first caller, because
re-measuring a broken record is the run that can unrecord it.

Cross references (SAD Section 4.2): an :class:`EntityRegistry` counts
the local coordinate systems, actuators, and motions the script
creates, and rejects a command citing an index that does not exist
yet, because FlightStream expects auxiliary definitions before they
are referenced and fails silently otherwise. Creation commands accept
an optional ``label``, and every entity-citing argument then takes the
index or the label, so recipes can speak in configuration terms while
the library maintains the label-to-index dictionary. Entities carried
by an opened project file, including the mesh boundary inventory
(by count or by a name-to-index mapping), are declared with
:meth:`Script.declare_existing`; boundary citations are only range
checked once the inventory was declared, because the boundary total
lives in the geometry file and cannot be known statically.

The two gaps of the first cut are closed: the per-surface lines of
INITIALIZE_SOLVER when SURFACES is not -1 (``surface_toggles``) and
the PERIODIC symmetry copy count (``symmetry_copies``) are regular
database arguments now, emitted comfortably through the curated
helper layer in :mod:`pyflightstream.script.helpers` (SAD Section
4.3).

The layout of the helpers (AD-17):
:func:`pyflightstream.script.helpers.solver_settings` keeps its signature
and its path and is the facade over per-family emitters in the private
module ``script._settings``, which also holds the helpers that set up a
run (the flow conditions, the unsteady solver, the solver initialization
and start) and the toggle readers they share; the relaxed trailing edge
is the private module ``script._relaxed_te``. Only the helpers import
the two, and the helpers import every moved name, so each public path is kept.

In the workflow, emitted surface operations and frame motions also
form a provenance ledger. Geometry facts and unknown trajectory details
remain distinct; consumers may resolve timing only against exact measured
executable/build evidence. A raw emission cannot silently acquire that
proof. Command validation alone does not establish a native physical effect.

Length conventions are command-specific: frame coordinates use the native
simulation unit, while the measured unsteady fluid-plot VERTEX boundary
uses metres. The workflow converts at that boundary and retains declared
local sample coordinates for later interpretation. Existing action-based
exports remain the route for per-step surface sequences.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal

from pyflightstream._errors import PyflightstreamError
from pyflightstream.commands import (
    ArgSpec,
    ArgType,
    CommandEntry,
    CommandRegistry,
    Layout,
    ListSeparator,
    Phase,
    Status,
)
from pyflightstream.script._arg_checks import (
    CommandArgumentError,
    ScriptLineBreakError,
    _bind_line_tokens,
    _check_list,
    _check_one_line_each,
    _check_scalar,
)
from pyflightstream.script._ledger_tables import (
    _COUNT_ARG_NAMES,
    _COUNT_REFERENCE_ARGS,
    _CREATION_COMMANDS,
    _DELETION_COMMANDS,
    _FRAME_FOLLOWERS,
    _INITIALIZATION_COMMAND,
    _LOADS_FRAME_COMMAND,
    _MINIMUM_CP_COMMAND,
    _NEW_MODEL_COMMANDS,
    _REFERENCE_PLACEMENT_INDEX,
    _SURFACE_TRANSFORM_COMMANDS,
    _UNFOLLOWED_FRAME_COMMANDS,
    _VOLUME_SECTION_CREATES,
    _VOLUME_SECTION_DELETE,
    _VOLUME_SECTION_DELETE_ALL,
    LENGTH_UNIT_COMMAND,
    BrokenCommandUse,
    FramePlacement,
    UnsteadyActionUse,
    _placed_by_origin,
    _reference_kind,
)
from pyflightstream.script._ledger_tables import (
    _FOLLOWED_FRAME_COMMANDS as _FOLLOWED_FRAME_COMMANDS,
)
from pyflightstream.script._ledger_tables import (
    _FRAME_NEUTRAL_COMMANDS as _FRAME_NEUTRAL_COMMANDS,
)
from pyflightstream.script._ledger_tables import (
    _UNCOUNTED_CREATIONS as _UNCOUNTED_CREATIONS,
)
from pyflightstream.script._surface_averaging import (
    SurfaceAverageWindow,
    SurfaceAveragingWindow,
)
from pyflightstream.script.entities import (
    EntityRegistry,
    ScriptLabelError,
    ScriptReferenceError,
)
from pyflightstream.script.motion import MotionLedger
from pyflightstream.versions import FsVersion

if TYPE_CHECKING:  # annotation only: the builder core does not depend
    # on the snapshot model at import time (the reverse import, from
    # solver_setup back to here, is the one that must stay deferred)
    from pyflightstream.script.solver_setup import SolverSetup

__all__ = [
    "BrokenCommandError",
    "BrokenCommandUse",
    "CommandArgumentError",
    "EntityRegistry",
    "FramePlacement",
    "MARCH_ACTIONS",
    "MARCH_SINGLE",
    "MarchStrategy",
    "Script",
    "ScriptLabelError",
    "ScriptLineBreakError",
    "ScriptOrderError",
    "ScriptReferenceError",
    "UnsteadyActionUse",
]

#: How an unsteady script is marched on its build (GOAL-023). A closed set,
#: carried by the plan, the run record and the superfile column. The two
#: values are the words the design uses, a march by the solver's ACTIONS and a
#: SINGLE MARCH, and not a pair built for symmetry: they are written into
#: records, so they stay as they shipped.
MarchStrategy = Literal["actions", "single_march"]
#: The march that registers the solver's per-step actions, for a row asking
#: for a per-step threshold or a wall clock on a build that documents them.
MARCH_ACTIONS: MarchStrategy = "actions"
#: The march that registers no action: the plots declared before ONE solver
#: start over every time step, and every export after it.
MARCH_SINGLE: MarchStrategy = "single_march"

_ORDERED_PHASES = (
    Phase.GEOMETRY,
    Phase.SETUP,
    Phase.INIT,
    Phase.EXEC,
    Phase.ANALYSIS,
    Phase.EXPORT,
)


class ScriptOrderError(PyflightstreamError, ValueError):
    """A command was emitted after its phase had already passed.

    The script builder tracks the highest phase reached (geometry,
    setup, init, exec, analysis, export); FlightStream expects
    auxiliary definitions such as coordinate systems, actuators, and
    motions before solver initialization. Control commands are exempt,
    and a setup command that acts on an initialised solver passes
    through :meth:`Script.emit_after_initialization` alone.
    """


class BrokenCommandError(PyflightstreamError, RuntimeError):
    """A command recorded ``broken`` in the target version was emitted.

    ``broken`` is the one status backed by a probe that measured the
    command failing to do what the manual documents (CONTRIBUTING.md
    invariant 3), so the database already knows the emission is wrong
    before the solver ever sees it. Unlike a removed command, this one
    exists and the solver accepts the line: the run therefore produces
    numbers, and they are the wrong numbers, with nothing in the
    manifest to distinguish them from right ones. That is why the
    refusal happens here rather than being left to a warning.

    A ``RuntimeError`` rather than a ``ValueError`` because no argument
    is at fault: the call is well formed and the recorded state of the
    world is what refuses it, the same shape as
    :class:`~pyflightstream.workspace.WorkspaceError`.

    The refusal has an answer, deliberately, because two callers
    legitimately need the command: a probe re-measuring the record, and
    an operator who has established that the defect does not reach
    their case. :meth:`Script.allow_broken` is that answer, and it
    records what it waived (see :class:`BrokenCommandUse`).
    """


class Script:
    """One FlightStream script under construction, bound to one version.

    Parameters
    ----------
    version : str or FsVersion
        Target FlightStream version, canonical identifier (26.120); a
        vendor release name works only where it names exactly one
        registered build. Every
        emission is validated against this version's command view.
    registry : CommandRegistry, optional
        Alternative database, used by tests; defaults to the packaged
        one.

    Attributes
    ----------
    version : FsVersion
        The resolved target version.
    raw_flag : bool
        True once ``raw()`` was used; recorded in the run manifest so
        unvalidated scripts stay identifiable (FR-07).
    waived_commands : tuple of BrokenCommandUse
        Commands emitted under a :meth:`allow_broken` waiver, one entry
        per command, recorded in the run manifest for the same reason
        as ``raw_flag`` (FR-48). Empty for a script that emitted
        nothing broken, whether or not waivers were registered.
    entities : EntityRegistry
        Label-aware ledger of the frames, actuators, motions, and
        mesh boundaries the script created or declared (SAD Section
        4.2); backs the cross-reference checks and the label-to-index
        resolution of entity citations.
    solver_setup : SolverSetup or None
        Snapshot of the effective solver flags and their provenance,
        attached by
        :func:`pyflightstream.script.helpers.solver_settings` and
        serialized into the run manifest; None until a settings call
        builds it.
    registry : CommandRegistry
        The command database this script validates against, the one
        passed at construction or the packaged one. Read-only, and
        public for one reason: everything that records a per-version
        fact ABOUT this script has to read the same database the script
        used. The provenance snapshot did not, and asked the packaged
        database instead (PFS-2012.05), so a manifest could carry an
        availability, a default and an evidence sentence from a database
        no line of the script was checked against.
    """

    def __init__(self, version: str | FsVersion, registry: CommandRegistry | None = None):
        self._registry = registry or CommandRegistry.load()
        view = self._registry.for_version(version)
        self._view = view
        self.version: FsVersion = view.version
        self.raw_flag = False
        # Broken-command waivers (FR-48): the justification per command
        # name the caller allowed, and the record of the ones actually
        # emitted. Two dicts rather than one because a waiver that is
        # never exercised must leave no trace in the manifest: a recipe
        # is version portable, so a waiver written for the version where
        # the command is broken travels to the version where it is not,
        # and recording it there would report a dependency the run does
        # not have.
        self._broken_waivers: dict[str, str] = {}
        self._broken_uses: dict[str, BrokenCommandUse] = {}
        self._lines: list[str] = []
        #: How a workflow build marched this script (GOAL-023, ARCH-0200):
        #: :data:`MARCH_ACTIONS`, :data:`MARCH_SINGLE`, or None for a steady
        #: workflow or a script no workflow built. Set by
        #: ``cases.workflows.build_script`` and read by the plan and the run
        #: record.
        self.march_strategy: MarchStrategy | None = None
        self._phase_index: int | None = None
        self._phase_setter: tuple[str, int] | None = None
        # THE ONE DOOR PAST THE INIT PHASE (G02), for
        # :meth:`emit_after_initialization`: the line of the last
        # INITIALIZE_SOLVER, None before the first; the command that passed
        # the door and waits for the solver to initialise again, with its
        # line, None when nothing waits; and whether the door is open for the
        # one emission in progress.
        self._initialized_at: int | None = None
        self._reinitialization_owed: tuple[str, int] | None = None
        self._through_the_door = False
        self.entities = EntityRegistry()
        self._motion_ledger = MotionLedger()
        #: Emitted surface transforms with the frame placement at that command.
        self.surface_operations: list[dict[str, Any]] = []
        self.custom_field_extent_m: tuple[float, float, float, float] | None = None
        self.custom_field_coverage: dict[str, Any] | None = None
        self._native_solver_sha256: str | None = None
        self._native_solver_build: str | None = None
        self.solver_setup: SolverSetup | None = None
        # Induced-drag boundary selection, owned by the helpers: the
        # command is analysis phase, so the settings call records it
        # here and a later helper flushes it into the script. The
        # pending slot empties at the flush; the selection slot keeps
        # the choice this script made, so a second settings call that
        # omits the argument neither drops the line already emitted nor
        # lets the snapshot disagree with the script. Both hold
        # resolved 1-based boundary indices, never labels.
        self._pending_vorticity: list[int] | Literal["all"] | None = None
        self._vorticity_selection: list[int] | Literal["all"] | None = None
        # Whether a SOLVER_MINIMUM_CP is in the script, by any route: a later
        # settings call that omits minimum_cp then emits no library default
        # over it (PFS-2104.023). Filled by :meth:`emit`.
        self._minimum_cp_emitted = False
        # The unsteady regime unsteady_solver emitted, (time_iterations,
        # delta_time), for the snapshot of a settings call that states no mode
        # (PFS-2103.037); None while no such call ran.
        self._unsteady_regime: tuple[int, float] | None = None
        self._init_probe_and_surface_records()
        # THE ANALYSIS LOADS FRAME, as far as THIS SCRIPT set it (G45), read
        # through :attr:`loads_frame`; the reference frame until a
        # SET_SOLVER_ANALYSIS_LOADS_FRAME says otherwise, which is the solver's
        # own default (RPT-064: step exports written before the command print
        # the reference frame).
        self._loads_frame: int = _REFERENCE_PLACEMENT_INDEX
        self._sets_loads_frame: bool = False
        # THE COPIES A PERIODIC INITIALIZATION STANDS FOR, read through
        # :attr:`periodic_copies`; the solver's surface exports hold one zone
        # per copy, so the run needs the count to read them.
        self._periodic_copies: int | None = None
        self._periodic_symmetry = False
        self._incidence: dict[str, float] = {}
        #: EACH SECTION DISTRIBUTION THIS SCRIPT CREATED, in emission order: its families BY
        #: NAME, its plane, its frame and its count.
        #: Filled by the loop that emits the distribution, for the reason
        #: ``probe_points`` is. The script itself states surfaces by INDEX, so a
        #: sections table could not say which rows belong to which surface, and
        #: nothing at post can recover a name the script never wrote.
        self.section_blocks: list[dict[str, object]] = []
        #: THE FRAMES THE BUILDER CREATED, by the name a pproc entry cites (G12
        #: ``MRP`` and a rotor's frames to an index or None, and
        #: ``BLADE_AXIS`` to one index per blade family. Filled where the
        #: builder hands them to the init phase, for the reason
        #: ``section_blocks`` is filled by the loop that emits: the additional
        #: post cuts new distributions in the frames a saved simulation holds,
        #: and a distribution cites a frame by index. None for a script no run
        #: type built (a LEGACY recipe's) and for a continuation, which creates
        #: no frame.
        self.frames_by_name: dict[str, int | Mapping[str, int] | None] | None = None
        #: THE INDEX OF THE VOLUME SECTION THE BUILDER CUT FOR THE PPROC, or None
        #: while there is none (G05). Set by the builder right after its create,
        #: to the count :attr:`volume_sections` then holds, and KEPT by
        #: :meth:`emit`: a delete of a section below it moves it down one, a
        #: delete of it (or of every section) clears it. A steady sweep is one
        #: script whose points each cut the plane again, and a raw line may cut
        #: sections of its own around it, so the index the export and the next
        #: point's delete cite is the one the solver's list gives it and not 1.
        self.volume_section_index: int | None = None
        # HOW MANY VOLUME SECTIONS THIS SCRIPT HAS CUT AND NOT DELETED (G05),
        # read through :attr:`volume_sections`; filled by :meth:`emit`.
        self._volume_sections: int = 0
        # Simulation length unit set by this script, exposed through
        # simulation_length_unit. emit updates this alongside frame placements
        # so the recorded unit agrees with the emitted unit.
        self._simulation_length_unit: str | None = None
        # Saved-geometry metadata until a command sets the unit explicitly.
        self._opened_length_unit: str | None = None
        #: THE OPENED GEOMETRY'S BOUNDARY NAMES, in the solver's order, the
        #: name at position ``i`` being boundary ``i`` (R03). Filled
        #: where the workflow declares the inventory at OPEN, for the reason
        #: ``section_blocks`` is filled by the loop that emits: the names
        #: recorded cannot drift from the names the script was built over.
        #: Every name is kept, a duplicated one included, so a position
        #: still means that boundary. None for a script that opened no
        #: geometry declaring names, which includes every LEGACY recipe.
        self.boundary_inventory: tuple[str, ...] | None = None
        #: HOW MANY TRAILING-EDGE POINTS THIS SCRIPT IMPORTS, or None when it
        #: imports none (G02). Set by
        #: :func:`~pyflightstream.script.helpers.mark_wake_edges` after it
        #: emits, and summed over its calls. The run compares it with the
        #: count the solver logs as imported, because a point that matches
        #: no mesh edge is dropped in silence (RPT-061); it is kept on the
        #: SCRIPT so a continuation, which imports nothing, is never held to
        #: a count its own script did not write.
        self.wake_edge_points: int | None = None
        #: The id of the 6DOF motion a row's ``SIXDOF`` input created, or None.
        #: The trajectory export (FR-1089) names it after the march.
        self.sixdof_motion: int | None = None
        #: THE FOLDER THE SOLVER RUNS THIS SCRIPT IN, absolute, when the run
        #: layer knows it before the build, or None (G02). Set by the run: a
        #: point's ``datapoints/DP-<point>/``, or the simulation folder for a
        #: steady job of several points. A workflow names the data files it
        #: parks for the run inside it, by absolute path as it names the
        #: geometry, so each is the run's own file: never one of the input
        #: library, which a staged geometry is a link into and every
        #: simulation on the same mesh shares. None outside a run (a plan's
        #: rehearsal, a case built in Python), where such a file is named by
        #: its bare name. The script layer neither opens nor resolves it.
        self.working_dir: str | None = None
        #: Force plot groups actually emitted, with their frame, families and parameters.
        self.plot_groups: list[dict[str, object]] = []
        #: WHERE THIS SCRIPT PUT EACH COORDINATE SYSTEM (FR-100), keyed by
        #: frame index. Filled by :meth:`emit` from the commands that place a
        #: frame, for the reason ``probe_points`` is filled by the loop that
        #: emits a point: the placement recorded cannot drift from the one
        #: emitted. A translation reads it to move a frame to an ABSOLUTE
        #: origin; a frame the script did not place (one an opened project
        #: carries) has no entry, and a reader refuses it by name.
        self._frame_placements: dict[int, FramePlacement] = {
            _REFERENCE_PLACEMENT_INDEX: FramePlacement(
                origin=(0.0, 0.0, 0.0),
                axes=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
            )
        }
        # WHAT THIS SCRIPT HAS ALREADY ASKED THE SOLVER TO EXPORT, keyed
        # by the path as it was rendered, valued by the helper that asked
        # (PFS-2011.02). A script is a sequence of instructions and kept
        # no register of its own writes, so emitting two exports to one
        # path rendered two identical lines and the solver wrote one
        # file: the second silently replaced the first, and nothing in
        # the script, the record or the manifest said so.
        #
        # The register is on the SCRIPT and not on the helper because the
        # collision is between two calls, and only the script sees both.
        self._exported_paths: dict[str, str] = {}
        # UNSTEADY SOLVER ACTIONS, in creation order, and the child
        # scripts they name (PFS-2025.07). The solver runs the actions in
        # the order they were created and the order cannot be changed
        # afterwards, so a dict keyed by name preserves the only control
        # the caller has over it. The child text is parked here rather
        # than written: the script layer is text-only, and the file lands
        # through the run layer's own writer, so nothing below the run
        # layer touches a path.
        self._unsteady_actions: dict[str, UnsteadyActionUse] = {}
        self._pending_action_scripts: dict[str, str] = {}
        # DATA FILES THE SCRIPT NAMES AND THE RUN WRITES (G02, G06), keyed by
        # the path the command line names: the trailing-edge node file, as
        # text, and the actuator disc's radial thrust profile, as the bytes
        # the solver must read. Parked here for the reason the action scripts
        # are: the script layer is text-only, and the file lands through the
        # run layer's writer before the solver starts.
        self._pending_input_files: dict[str, str | bytes] = {}
        self._command_observers: list[
            Callable[[str, tuple[object, ...], dict[str, object], str, bool], None]
        ] = []
        self._emitting_line = False

    def park_input_file(self, path: str, payload: str | bytes) -> None:
        """Park an input beside the script, using the shared case-insensitive path rule.

        An identical input may be parked again. The run layer writes the parked
        payload before starting the solver.

        Parameters
        ----------
        path : str
            Relative file destination inside the point folder, without a drive,
            root or parent traversal.
        payload : str or bytes
            Text or exact bytes to stage at that destination.

        Raises
        ------
        CommandArgumentError
            If the path escapes the point folder or collides case-insensitively
            with different input content or an action script. Nothing is replaced.

        Examples
        --------
        >>> script = Script("26.124")
        >>> script.park_input_file("inputs/profile.txt", "profile data")
        >>> script.pending_input_files["inputs/profile.txt"]
        'profile data'
        """
        from pyflightstream.script._build_forms import _park_input_file

        _park_input_file(self, path, payload)

    @contextmanager
    def observe_commands(
        self,
        observer: Callable[[str, tuple[object, ...], dict[str, object], str, bool], None],
    ) -> Iterator[None]:
        """Observe accepted commands for this scope, without replacing validation.

        The callback receives name, positional arguments, keyword arguments
        (including a stated label), rendered text, and whether emit_line was
        the source. Refused commands and raw text are never observed.
        """
        self._command_observers.append(observer)
        try:
            yield
        finally:
            self._command_observers.remove(observer)

    def _init_probe_and_surface_records(self) -> None:
        """Create the empty probe and surface records the workflows fill."""
        #: WHERE THIS SCRIPT PUT EACH PROBE POINT (FR-91), one entry per
        #: point in creation order: the vertex number, its x, y and z as
        #: emitted, and the NAME of the frame they are measured in.
        #:
        #: The vertex number is the suffix an unsteady fluid plot carries
        #: in its own name, so `MACH7` in a plots export is entry 7 here.
        #: That is the join a reader of an unsteady probe table has no
        #: other way to make: the export writes the numbers and never the
        #: positions.
        #:
        #: Filled by the loop that EMITS the point, so the coordinates
        #: recorded cannot drift from the coordinates emitted. Empty for a
        #: script whose row declares no probes, and empty for one whose
        #: entry cites a user's points file, since the package does not
        #: parse a survey the user wrote.
        self.probe_points: list[tuple[int, float, float, float, str]] = []
        #: Exact sample IDs, field requests and native-to-SI conversion per entry.
        self.probe_field_layout: list[dict[str, object]] = []
        #: The far-field plane and lattice each point reads, reused or added, one
        #: ``{"point", "shapes"}`` per point the far field laid probes for (FR-455).
        self.farfield_layout: list[dict[str, Any]] = []
        #: Native surface-property plot identities, separate from off-body velocity samples.
        self.surface_probe_layout: list[dict[str, object]] = []
        #: Surface averaging window emitted by the workflow, for run provenance.
        #: Never set by a build which emits no SOLVER_TIME_AVERAGING;
        #: a continuation carries the one its stopped run recorded.
        self.surface_time_averaging: SurfaceAveragingWindow | None = None
        #: THE WINDOW THE PACKAGE AVERAGES THE SURFACE OVER (G25), set
        #: where the workflow resolves the pproc's ``[time_averaging]``. No
        #: command carries it: the run exports the surface at every step of it
        #: and the post averages those exports.
        self.surface_average_window: SurfaceAverageWindow | None = None
        #: THE TECPLOT SURFACES THE PACKAGE WRITES FROM A VTK (G45), one
        #: per Tecplot output the script exports, filled by the workflow that
        #: emits the VTK in its place, for the reason ``section_blocks`` is
        #: filled by the loop that emits: ``vtk`` and ``dat``, the two names,
        #: and ``frame``, the loads frame the VTK is written in as this script
        #: placed it (:meth:`loads_frame_record`).
        self.surface_translations: list[dict[str, object]] = []

    @property
    def unsteady_actions(self) -> tuple[UnsteadyActionUse, ...]:
        """Actions registered on this script, in creation order.

        Returns
        -------
        tuple of UnsteadyActionUse
            One record per registered action, carrying the evidence the
            command rests on for this build.
        """
        return tuple(self._unsteady_actions.values())

    @property
    def pending_action_scripts(self) -> dict[str, str]:
        """Child action scripts waiting to be written, by their filename.

        Returns
        -------
        dict of str to str
            A copy, keyed by the path the registration line names and
            valued by the text of the child script. The run layer writes
            these beside the script it renders; the script layer neither
            opens nor resolves a path.
        """
        return dict(self._pending_action_scripts)

    @property
    def pending_input_files(self) -> dict[str, str | bytes]:
        """Data files the script names, waiting to be written, by their path.

        Returns
        -------
        dict of str to str or bytes
            A copy, keyed by the path the emitted command names and valued
            by the file's content: text, written in the platform's text
            mode (the trailing-edge node file), or bytes, written exactly as
            they are (the actuator disc's radial thrust profile, whose last
            row must end the file, G06). The run layer writes these before
            the solver starts, as it writes :attr:`pending_action_scripts`;
            the script layer neither opens nor resolves a path.
        """
        return dict(self._pending_input_files)

    @property
    def registry(self) -> CommandRegistry:
        """Command database this script validates and is recorded against.

        Returns
        -------
        CommandRegistry
            The registry passed at construction, or the packaged one.

        Notes
        -----
        Exposed so that a record ABOUT this script reads the database
        the script itself used. Reaching for
        :meth:`~pyflightstream.commands.CommandRegistry.load` while a
        Script is in hand is the defect this property exists to remove:
        the two answers agree for the packaged database and differ for
        every other one, and the case where they differ is exactly the
        case a provenance record is for.
        """
        return self._registry

    @property
    def num_local_frames(self) -> int:
        """Local coordinate systems the script created or declared."""
        return self.entities.count("frames")

    @property
    def num_actuators(self) -> int:
        """Actuators the script created or declared."""
        return self.entities.count("actuators")

    @property
    def num_motions(self) -> int:
        """Motions the script created or declared."""
        return self.entities.count("motions")

    @property
    def num_boundaries(self) -> int | None:
        """Declared mesh boundary total, or None while undeclared.

        None means the boundary inventory of the loaded geometry was
        never declared, so boundary citations pass unverified: the
        boundary count lives in the geometry file and cannot be known
        statically by the builder.
        """
        return self.entities.count("boundaries")

    @property
    def waived_commands(self) -> tuple[BrokenCommandUse, ...]:
        """Commands emitted under a waiver, in the order first emitted.

        One entry per command however many times it was emitted, because
        the fields that describe the BREAKAGE are properties of the
        command, the version and the waiver, so repeating the emission
        would repeat them without adding a fact. The exception is
        ``first_line``, which is a property of one emission and keeps the
        FIRST: a script-lifetime waiver covers every later emission, and
        the reason was written for a particular one.
        :class:`BrokenCommandUse` is the single home of the field list.

        Named for what the entries ARE (PFS-2022.01.05): each is a
        waiver the recipe registered, and the former name
        ``broken_commands`` read as the commands that broke in the run,
        which is the opposite claim.
        """
        return tuple(self._broken_uses.values())

    def declare_existing(
        self,
        *,
        frames: int = 0,
        actuators: int = 0,
        motions: int = 0,
        boundaries: int | Mapping[str, int] = 0,
    ) -> None:
        """Declare auxiliary objects already present in the opened project.

        A simulation file loaded with OPEN can carry local coordinate
        systems, actuators, and motions saved earlier, and the loaded
        geometry brings its mesh boundaries; the builder cannot see
        inside those files, so scripts citing such objects declare
        them here to satisfy the cross-reference check.

        Parameters
        ----------
        frames : int
            Local coordinate systems in the project, beyond the
            reference frame (index 1), which always exists.
        actuators : int
            Actuators in the project.
        motions : int
            Motions in the project.
        boundaries : int or mapping of str to int
            Mesh boundaries of the loaded geometry: either their total
            count (zero, the default, keeps the inventory undeclared),
            or a mapping of configuration labels to 1-based boundary
            indices in geometry-tree order, for example
            ``{"fuselage": 1, "wing": 2}``. Declaring the inventory
            turns on range verification for every boundary-citing
            argument; until then those citations pass unverified,
            because the boundary total cannot be known statically.
            Labels then stand in for indices anywhere a boundary is
            cited.
        """
        for kind, extra in (("frames", frames), ("actuators", actuators), ("motions", motions)):
            self.entities.declare(kind, extra)
        self.entities.declare_boundaries(boundaries)

    def resolve_boundary(self, value: int | str, *, context: str = "boundary citation") -> int:
        """Resolve a mesh boundary citation to its 1-based index.

        A label declared through :meth:`declare_existing` resolves to
        its index; an integer passes through after the range check.
        The two bounds are independent: the upper one needs a declared
        inventory and is skipped without it, the lower one does not,
        since indices are 1-based.

        This method resolves a citation with no command attached, so it
        applies the generic all-boundaries form, -1, rather than any
        command's own. That is stated here and passed explicitly,
        because the emitter has no per-kind default: a command's
        all-form comes from its own argument, and six surface commands
        state none at all (FSM-26.120 pp.309-313). Passing -1 to
        :meth:`emit` for one of those is still refused, and correctly;
        it is this generic entry point that accepts it.

        Parameters
        ----------
        value : int or str
            Boundary index (1-based, geometry-tree order; -1 selects
            all boundaries) or a declared boundary label.
        context : str
            Prefix naming the citing location in error messages.

        Returns
        -------
        int
            The resolved boundary index.

        Raises
        ------
        ScriptReferenceError
            If the label is unknown (the message lists the declared
            labels) or the index falls outside the declared inventory.
        """
        index = self.entities.resolve("boundaries", value, context=context)
        self.entities.check_index("boundaries", index, context=context, all_sentinel=-1)
        return index

    def emit(self, name: str, /, *args: object, label: str | None = None, **kwargs: object) -> None:
        """Validate and append one command.

        Parameters
        ----------
        name : str
            Command name as in the database; positional-only, so a
            command argument may itself be called ``name`` (for
            example CREATE_NEW_ACTUATOR).
        *args, **kwargs
            Argument values, positional in database order or by
            argument name. Optional arguments may be omitted.
            Arguments citing a frame, actuator, motion, or mesh
            boundary accept the entity's label instead of its index;
            labels resolve at emission through the entity registry.
        label : str, optional
            Only on a creation command (CREATE_NEW_COORDINATE_SYSTEM and
            the two that append a frame, DUPLICATE_COORDINATE_SYSTEM and
            MIRROR_COORDINATE_SYSTEM; CREATE_NEW_ACTUATOR; CREATE_NEW_MOTION
            and the four type-specific motion creations of 25.000):
            registers this label for the created entity, so later
            commands can cite it by name instead of by index.

        Raises
        ------
        CommandNotInVersionError
            If the command does not exist in this version; the message
            carries the manual citation and successor when known.
        BrokenCommandError
            If the command's record in this version is ``broken`` and
            no :meth:`allow_broken` waiver covers it.
        CommandArgumentError
            If an argument violates the typed specification, or if
            ``label`` is given on a command that creates nothing.
        ScriptOrderError
            If the command's phase precedes the phase already reached.
        ScriptReferenceError
            If the command cites an entity index the script has not
            created or declared yet, or an unknown entity label.
        ScriptLabelError
            If ``label`` is already taken for this entity kind.
        """
        entry = self._view[name]
        # Before argument binding, on purpose. A broken record is a fact
        # about the command and not about this call, so it is the more
        # important of the two errors when both apply; refusing first
        # also lets the class guard in tests/tier1_offline/test_script.py walk the
        # whole database and emit each broken command with no arguments
        # at all, which is what makes that guard writable for commands
        # whose grammars have nothing in common.
        #
        # NOTHING IS RECORDED UNTIL THE BLOCK IS ACCEPTED (PFS-2104.019). The
        # waiver record and the phase move are computed here and committed
        # after every check below has passed, so a refused emission leaves
        # the script exactly as it found it: no waiver listed for a line
        # never written, no phase reached by a command that is not there.
        waiver = self._check_not_broken(entry)
        self._check_not_a_model_replacement(entry)
        self._check_label_applies(entry, label)
        bound = self._bind(entry, args, kwargs)
        if entry.name == _INITIALIZATION_COMMAND:
            periodic = (
                str(bound.get("symmetry", bound.get("symmetry_type", ""))).upper() == "PERIODIC"
            )
            if periodic and any(self._incidence.values()):
                raise CommandArgumentError(
                    "SYMMETRY PERIODIC refuses nonzero angle of attack or sideslip: "
                    "incidence is incompatible with rotational periodicity"
                )
        elif entry.name in {"SOLVER_SET_AOA", "SOLVER_SET_SIDESLIP"}:
            if self._periodic_symmetry and float(bound["angle"]) != 0:
                raise CommandArgumentError(
                    f"SYMMETRY PERIODIC refuses nonzero {entry.name}: incidence is "
                    "incompatible with rotational periodicity"
                )
        phase = self._check_phase(entry)
        self._check_references(entry, bound)
        block, multiline = self._render_command(entry, bound)
        exports = [
            str(bound[argument.name])
            for argument in entry.args
            if "EXPORT" in entry.name.split("_")
            and argument.type is ArgType.PATH
            and argument.name in bound
        ]
        for path in exports:
            self._refuse_export_collision(path, asker=entry.name)
        _check_one_line_each(entry, block)
        # ACCEPTED: from here on the emission is committed.
        self._commit_state(entry, bound, phase)
        self._lines.extend(block)
        if waiver is not None and entry.name not in self._broken_uses:
            # Retain the first accepted line covered by this waiver.
            self._broken_uses[entry.name] = waiver.model_copy(
                update={"first_line": block[0] if block else ""}
            )
        if multiline:
            self._lines.append("")
        for path in exports:
            self._exported_paths[path] = entry.name
        self._follow_emitted(entry, bound, block, multiline)
        self._follow_entities(entry, bound, label)
        text = "\n".join(block + ([""] if multiline else [])) + "\n"
        for observer in tuple(self._command_observers):
            observer(
                name,
                args,
                {**kwargs, **({"label": label} if label else {})},
                text,
                self._emitting_line,
            )

    def _check_not_a_model_replacement(self, entry: CommandEntry) -> None:
        """Refuse a command that discards a model this script already tracks."""
        if entry.name in _NEW_MODEL_COMMANDS and (
            self.num_local_frames
            or self.num_actuators
            or self.num_motions
            or self.num_boundaries is not None
        ):
            raise CommandArgumentError(
                f"{entry.name}: cannot replace a model whose entities this Script already "
                "tracks. Its labels, placements and loads records belong to that model. "
                "Create a new Script for the new model instead (PFS-2088.009)"
            )

    def _check_label_applies(self, entry: CommandEntry, label: str | None) -> None:
        """Refuse ``label=`` on a command that creates nothing, or a label already taken."""
        if label is None:
            return
        if entry.name not in _CREATION_COMMANDS:
            raise CommandArgumentError(
                f"{entry.name} does not create a frame, actuator, or motion, so "
                "label= does not apply; labels name script-created entities at "
                f"their creation command ({entry.citation})"
            )
        self.entities.assert_label_free(_CREATION_COMMANDS[entry.name], label)

    def _commit_state(
        self,
        entry: CommandEntry,
        bound: Mapping[str, object],
        phase: tuple[int, tuple[str, int]] | None,
    ) -> None:
        """Move the phase and the solver-state flags a command accepted by ``emit`` sets."""
        if phase is not None:
            self._phase_index, self._phase_setter = phase
        if entry.name == _MINIMUM_CP_COMMAND:
            self._minimum_cp_emitted = True
        if entry.name in _NEW_MODEL_COMMANDS:
            self.surface_operations.clear()
            self.custom_field_extent_m = None
            self.custom_field_coverage = None
            self._minimum_cp_emitted = False
            self._unsteady_regime = None
            self._incidence.clear()
            self._periodic_symmetry = False
        if entry.name == _INITIALIZATION_COMMAND:
            periodic = (
                str(bound.get("symmetry", bound.get("symmetry_type", ""))).upper() == "PERIODIC"
            )
            self._initialized_at = len(self._lines) + 1
            self._reinitialization_owed = None
            copies = bound.get("symmetry_copies", bound.get("symmetry_periodicity"))
            self._periodic_symmetry = periodic
            self._periodic_copies = (
                int(copies)  # type: ignore[call-overload]
                if periodic and copies is not None
                else None
            )
            if "load_frame" in bound:
                self._loads_frame = int(bound["load_frame"])  # type: ignore[call-overload]
                self._sets_loads_frame = True
        elif entry.name in {"SOLVER_SET_AOA", "SOLVER_SET_SIDESLIP"}:
            self._incidence[entry.name] = float(bound["angle"])  # type: ignore[arg-type]

    def _follow_emitted(
        self, entry: CommandEntry, bound: Mapping[str, object], block: list[str], multiline: bool
    ) -> None:
        """Keep every ledger in step with the block just appended to the lines."""
        line = len(self._lines) - len(block) + (0 if multiline else 1)
        if entry.name in _SURFACE_TRANSFORM_COMMANDS:
            frame_index = bound.get("frame")
            placement = (
                self.frame_placements.get(frame_index) if isinstance(frame_index, int) else None
            )
            self.surface_operations.append(
                {
                    "command": entry.name,
                    "arguments": dict(bound),
                    "length_unit": self.simulation_length_unit,
                    "frame": placement.model_dump() if placement is not None else None,
                    "boundary_count": self.num_boundaries,
                    "line": line,
                }
            )
        self._follow_frame_placement(entry.name, bound)
        self._follow_length_unit(entry.name, bound)
        self._motion_ledger.follow(
            entry.name,
            bound,
            line=line,
            next_motion=self.num_motions + 1,
        )
        if entry.name == _LOADS_FRAME_COMMAND:
            self._loads_frame = int(bound["load_frame"])  # type: ignore[call-overload]
            self._sets_loads_frame = True
        self._follow_volume_sections(entry.name, bound)

    def _follow_entities(
        self, entry: CommandEntry, bound: Mapping[str, object], label: str | None
    ) -> None:
        """Create or delete the entity a creation or deletion command names."""
        if entry.name in _CREATION_COMMANDS:
            kind = _CREATION_COMMANDS[entry.name]
            created = self.entities.create(kind, label=label)
            if kind == "frames":
                # A new frame, a copy included, is placed by no command yet.
                self._frame_placements.pop(created, None)
        elif entry.name in _DELETION_COMMANDS:
            kind, argument = _DELETION_COMMANDS[entry.name]
            self.entities.delete(kind, int(bound[argument]))  # type: ignore[call-overload]
        elif entry.name in {"DELETE_SURFACES", "SURFACE_DELETE", "SURFACE_CLEARALL"}:
            index = int(bound.get("index", bound.get("surface", -1)))  # type: ignore[call-overload]
            self.entities._delete_boundary(index)

    def bind_native_solver_identity(self, *, executable_sha256: str, build: str) -> None:
        """Bind an identity verified by the caller for exact motion-proof lookup.

        This method records evidence supplied by the executor; it does not inspect
        an executable or establish that a nominal version denotes a particular build.
        Saved runs can instead resolve timing using their actual recorded identity.
        """
        digest = executable_sha256.strip().lower()
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise CommandArgumentError("executable_sha256 must be an exact SHA-256 digest")
        if not build.strip():
            raise CommandArgumentError("build must identify the measured native executable")
        self._native_solver_sha256 = digest
        self._native_solver_build = build.strip()

    @property
    def frame_motions(self) -> dict[int, dict[str, object]]:
        """Final emitted frame geometry/motion evidence, indexed by frame.

        Read after setup emission: probe creation may precede motion attachments.
        Unknown trajectories retain their reason and partial geometric evidence.
        """
        return self._motion_ledger.snapshot(
            self._frame_placements,
            frame_count=self.num_local_frames + 1,
            boundary_count=self.entities.count("boundaries") or None,
            version=self.version.canonical,
            length_unit=self.simulation_length_unit,
            executable_sha256=self._native_solver_sha256,
            build=self._native_solver_build,
        )

    @property
    def frame_placements(self) -> Mapping[int, FramePlacement]:
        """Where this script placed each coordinate system, by frame index (FR-100).

        READ ONLY. A translation moves a frame to an absolute origin computed
        from this, so a caller writing into it would place a frame from a value
        no command emitted; it is filled by :meth:`emit` and nowhere else.
        """
        return MappingProxyType(self._frame_placements)

    def _follow_frame_placement(self, name: str, bound: Mapping[str, object]) -> None:
        """Keep :attr:`frame_placements` in step with a command just emitted (FR-100).

        A command in ``_FRAME_FOLLOWERS`` updates the placement the way its entry
        there says; a command in ``_UNFOLLOWED_FRAME_COMMANDS`` forgets the frame it
        names; anything else leaves every placement as it was. The reference frame
        is never placed by a command.
        """
        follower = _FRAME_FOLLOWERS.get(name)
        if name == "DELETE_COORDINATE_SYSTEM" and follower is not None:
            # BEFORE THE FRAME CHECK: a delete shifts the indices above whatever
            # it names, so it forgets every placement however its frame is bound.
            follower(self._frame_placements, _REFERENCE_PLACEMENT_INDEX, bound)
            return
        frame = bound.get("frame")
        if not isinstance(frame, int) or frame == _REFERENCE_PLACEMENT_INDEX:
            return
        if follower is _placed_by_origin:
            _placed_by_origin(
                self._frame_placements,
                frame,
                bound,
                simulation_unit=self.simulation_length_unit,
            )
        elif follower is not None:
            follower(self._frame_placements, frame, bound)
        elif name in _UNFOLLOWED_FRAME_COMMANDS:
            self._frame_placements[frame] = FramePlacement(origin=None, axes=None)

    @property
    def loads_frame(self) -> int:
        """The analysis loads frame, as far as THIS SCRIPT set it (G45).

        The frame of the last ``SET_SOLVER_ANALYSIS_LOADS_FRAME`` emitted, or 1,
        the reference frame, while none has been. The solver writes the VTK
        surface export in this frame (RPT-074), so the Tecplot the package
        writes from it is undone by it.

        Examples
        --------
        >>> from pyflightstream.script import Script
        >>> script = Script("26.124")
        >>> script.loads_frame
        1
        """
        return self._loads_frame

    @property
    def sets_loads_frame(self) -> bool:
        """Whether THIS SCRIPT emitted ``SET_SOLVER_ANALYSIS_LOADS_FRAME`` (G45).

        While it has not, :attr:`loads_frame` is the solver's default, the
        reference frame, for a simulation the script builds. A simulation it
        reopens keeps the loads frame it was saved with, which the script layer
        cannot read, so a continuation takes that frame from the run it
        continues.

        Examples
        --------
        >>> from pyflightstream.script import Script
        >>> Script("26.124").sets_loads_frame
        False
        """
        return self._sets_loads_frame

    @property
    def periodic_copies(self) -> int | None:
        """The copy count of the last ``INITIALIZE_SOLVER`` under PERIODIC symmetry.

        None until the script initializes, and for any other symmetry. The
        solver writes a periodic row's native Tecplot surface as one zone per
        copy, the modelled sector first (measured on 26.124), so the run reads
        that file by this count.

        Examples
        --------
        >>> from pyflightstream.script import Script
        >>> Script("26.124").periodic_copies is None
        True
        """
        return self._periodic_copies

    def loads_frame_record(self) -> dict[str, object]:
        """Return the loads frame and where this script placed it, as a run records it.

        ``frame`` is :attr:`loads_frame`; ``origin`` and ``axes`` are its
        placement in the reference frame (:attr:`frame_placements`), or None
        where this script did not place it: a frame a reopened simulation
        carries, or one a command moved in a way the ledger does not follow.
        """
        placed = self._frame_placements.get(self._loads_frame)
        return {
            "frame": self._loads_frame,
            "origin": None
            if placed is None or placed.origin is None
            else [float(value) for value in placed.origin],
            "axes": None
            if placed is None or placed.axes is None
            else [[float(value) for value in axis] for axis in placed.axes],
        }

    @property
    def simulation_length_unit(self) -> str | None:
        """The known simulation length unit (G05, G06, G32, G34).

        Prefer the last ``SET_SIMULATION_LENGTH_UNITS`` emitted. When none
        was emitted, use the saved unit explicitly recorded by the workflow
        after reading the opened file's measured header. Return None when
        neither source establishes a unit. Reading a saved unit records
        provenance without emitting a command that changes the simulation.

        Examples
        --------
        >>> from pyflightstream.script import Script
        >>> script = Script("26.124")
        >>> script.emit("SET_SIMULATION_LENGTH_UNITS", "MILLIMETER")
        >>> script.simulation_length_unit
        'MILLIMETER'
        """
        return self._simulation_length_unit or self._opened_length_unit

    def record_opened_length_unit(self, unit: str) -> None:
        """Record a decoded saved-geometry unit; an explicit command wins.

        This records measured metadata for coordinate conversion without
        emitting a command that changes the geometry.
        """
        from pyflightstream._lengths import scale

        if scale(unit, "METER") is None:
            raise CommandArgumentError(f"opened geometry unit {unit!r} names no known scale")
        self._opened_length_unit = unit

    def _follow_length_unit(self, name: str, bound: Mapping[str, object]) -> None:
        """Keep :attr:`simulation_length_unit` in step with a command just emitted."""
        if name in _NEW_MODEL_COMMANDS:
            self._simulation_length_unit = None
            self._opened_length_unit = None
        elif name == LENGTH_UNIT_COMMAND:
            self._simulation_length_unit = str(bound["units"])

    def _refuse_export_collision(self, path: str, *, asker: str) -> None:
        """Refuse an export to a file this script already exports to (PFS-2093.004).

        THE ONE CHECK OF THE EXPORT REGISTER, keyed by
        :func:`~pyflightstream._digest.one_file_key`, the key the parked action
        scripts and input files are matched by: a path through a parent folder,
        or equal but for case, is the same file where the solver writes. The
        export helpers call it before their first line, so a refusal leaves the
        script untouched, and record the path afterwards. A command emitted
        directly passes through it too, before any state is committed.

        Parameters
        ----------
        path : str
            The output path, as the command renders it.
        asker : str
            The helper or command asking, named in the remedy.

        Raises
        ------
        CommandArgumentError
            If the register already holds the file, naming the earlier call
            site.
        """
        from pyflightstream._digest import one_file_key

        key = one_file_key(path)
        for held, site in self._exported_paths.items():
            if one_file_key(held) == key:
                same = "" if held == path else f" (as {held!r}, the same file)"
                raise CommandArgumentError(
                    f"this script already exports to {path!r}{same}, from {site}. The "
                    "solver writes one file per path, so the second export would "
                    "silently replace the first and the script would carry two "
                    f"exports of one file. Give {asker} a path of its own, for "
                    "example one carrying the point or the survey name."
                )

    def _parked_file(self, path: str) -> tuple[str, str] | None:
        """Name the parked file ``path`` would replace, across both registers.

        Returns ``("action script", key)`` or ``("input file", key)`` for the
        parked path that :func:`~pyflightstream._digest.one_file_key` reads as
        the same file, or None. The two registers are written by different
        helpers, so a check on one alone let an action script and an input file
        share a path (PFS-2093.011).
        """
        from pyflightstream.script._build_forms import _parked_file

        return _parked_file(self, path)

    @property
    def volume_sections(self) -> int:
        """How many volume sections this script has cut and not deleted (G05).

        A create appends one, ``DELETE_VOLUME_SECTION`` removes one and
        ``DELETE_ALL_VOLUME_SECTIONS`` removes them all, whoever emitted the
        line, the builder or a raw line of the row. A create is taken to append
        at the end of the solver's list and a delete to close the gap, as the
        actuators and motions of this ledger are; neither is measured for
        sections. A section a saved simulation already carries is not counted:
        the script layer reads no file.

        Examples
        --------
        >>> from pyflightstream.script import Script
        >>> script = Script("26.124")
        >>> circle = (1, "YZ", 0.5, 10, 12, 0.2, 1.0, "NONE", 0.1, 1, 1.2)
        >>> script.emit("CREATE_NEW_CIRCLE_VOLUME_SECTION", *circle)
        >>> script.emit("CREATE_NEW_CIRCLE_VOLUME_SECTION", *circle)
        >>> script.emit("DELETE_VOLUME_SECTION", 1)
        >>> script.volume_sections
        1
        """
        return self._volume_sections

    def _follow_volume_sections(self, name: str, bound: Mapping[str, object]) -> None:
        """Keep :attr:`volume_sections` and :attr:`volume_section_index` in step (G05)."""
        if name in _VOLUME_SECTION_CREATES:
            self._volume_sections += 1
        elif name == _VOLUME_SECTION_DELETE:
            self._volume_sections = max(self._volume_sections - 1, 0)
            deleted, own = bound.get("index"), self.volume_section_index
            if isinstance(deleted, int) and own is not None:
                if deleted == own:
                    self.volume_section_index = None
                elif deleted < own:
                    self.volume_section_index = own - 1
        elif name == _VOLUME_SECTION_DELETE_ALL:
            self._volume_sections = 0
            self.volume_section_index = None

    def entry(self, name: str, /) -> CommandEntry:
        """Return the database entry of ``name`` on this script's build.

        The public reading of the per-version view a builder needs
        before it emits (the phase of a command, its layout): a caller
        outside this package read the private view in legacy releases, and the
        architecture lens of REL-0140 asked for the door. Raises
        :class:`~pyflightstream.commands.CommandNotInVersionError` as
        :meth:`emit` would.
        """
        return self._view[name]

    def emit_line(self, line: str, /) -> None:
        """Emit one command line as the solver reads it (PFS-2033.01).

        The line is split on whitespace; the first token is the command
        and the rest its arguments, each coerced to the type the database
        declares for its position (an int, a float, ENABLE/DISABLE or
        True/False for a bool, or the token itself for an enum, a string or
        a path), then handed to :meth:`emit`, so every check of a curated
        emission applies. A list argument takes the run of following tokens
        its element type reads, as the inline renderer writes it, so a
        sweep line such as ``SWEEPER_SET_AOA_SWEEP CUSTOM 0.0 2.0 4.0``
        round-trips. Only a command whose grammar is one line (``bare`` or
        ``inline``) is carried: a block, a payload or a parameter list is
        refused naming the layout, since the line the user wrote cannot be
        it.

        Raises
        ------
        CommandArgumentError
            If the command's layout is not one line, a token is not the
            type its position declares, or tokens are left that no argument
            reads (a value containing a space, which splits into several).
        """
        tokens = line.split()
        if not tokens:
            raise CommandArgumentError("an empty line names no command")
        name, arguments = tokens[0], tokens[1:]
        spec = self.entry(name)
        if spec.layout not in (Layout.BARE, Layout.INLINE):
            raise CommandArgumentError(
                f"{name} is a {spec.layout.value.replace('_', ' ')} and not a one-line "
                "command; a raw entry is one line as the solver reads it, and a block "
                "has no place in it. State what the block sets through the preset's own "
                "keys or the row's, or drop the entry"
            )
        bound = _bind_line_tokens(name, spec.args, arguments)
        previous = self._emitting_line
        self._emitting_line = True
        try:
            self.emit(name, **bound)
        finally:
            self._emitting_line = previous

    def raw(self, text: str) -> None:
        """Append unvalidated script text and flag the script (FR-07).

        Unvalidated text may move any frame, so every placement but the
        reference's is forgotten, as the motion ledger forgets its motions: a
        reader of :attr:`frame_placements` then refuses the frame by name
        rather than computing from geometry the text may have changed
        (PFS-2104.021).
        """
        self.raw_flag = True
        self._motion_ledger.invalidate(
            "Unvalidated raw script may change motion or frame placement."
        )
        for frame in self._frame_placements:
            if frame != _REFERENCE_PLACEMENT_INDEX:
                self._frame_placements[frame] = FramePlacement(origin=None, axes=None)
        self._lines.extend(text.splitlines())

    def allow_broken(self, name: str, /, *, reason: str) -> None:
        """Permit one command recorded ``broken`` to be emitted (FR-48).

        Registers a waiver for ``name``; a later :meth:`emit` of it then
        appends the command instead of raising
        :class:`BrokenCommandError`, and records what was waived in
        :attr:`waived_commands`, which the run manifest carries.

        Two callers legitimately need this. A tier 2 probe re-measuring
        the record cannot avoid emitting the command, since emitting it
        is the measurement; and an operator may have established that
        the recorded defect does not reach their case, which is a
        judgement no database can make for them. ``reason`` is required
        because it is the only part of the record nothing else can
        supply.

        Parameters
        ----------
        name : str
            Command name as in the database; positional-only for the
            same reason as in :meth:`emit`.
        reason : str
            Why this run may emit it anyway. Recorded verbatim in the
            manifest; a blank string is refused.

        Raises
        ------
        CommandNotInVersionError
            If the command is unknown, removed in this version, or has
            no recorded evidence for it. Checked here rather than left
            to the emission so a typo in the name fails at the waiver,
            where it was made.
        CommandArgumentError
            If ``reason`` is blank.

        Notes
        -----
        A waiver for a command that is **not** broken in this version is
        accepted and does nothing. That is deliberate: the same recipe
        is meant to run against several versions, and AIR_ALTITUDE is
        recorded broken in 26.120 and verified in 26.121, so refusing
        the unnecessary waiver would make a recipe fail on the version
        where the command is recorded working. Nothing is recorded in
        that case, so the manifest never reports a dependency the run
        did not have.
        """
        entry = self._view[name]
        if not reason.strip():
            # No manual citation here, deliberately. The manual page for the
            # command says nothing about waiver justifications; the rule is
            # this library's, from FR-48, and a refusal that cites a page
            # silent on its own rule sends the reader somewhere useless.
            raise CommandArgumentError(
                f"allow_broken({name!r}) needs a reason: the waiver is recorded in "
                "the run manifest so a later reader can tell whether the run may "
                "be trusted, and an empty justification records nothing they can "
                "use (SRS FR-48)"
            )
        self._broken_waivers[entry.name] = reason

    def comment(self, text: str) -> None:
        """Append a comment; FlightStream ignores lines starting with ``#``.

        A multi-line ``text`` becomes one comment line per physical line,
        each independently prefixed. That is a fix rather than a
        convenience: prefixing only the first line left every line after
        it as an ordinary script line, so a comment carrying a newline
        emitted an unvalidated command with ``raw_flag`` still False,
        which is the comment half of the same defect the argument checks
        above refuse. Commenting each line keeps the caller's intent (it
        is all commentary) and cannot inject.

        A blank line inside ``text`` becomes a bare ``#`` rather than an
        empty line, so the block stays visibly one comment.
        """
        lines = text.splitlines() or [""]
        self._lines.extend(f"# {line}" if line else "#" for line in lines)

    def render(self) -> str:
        """Return the complete script text, newline terminated."""
        return "\n".join(self._lines) + "\n"

    def _check_not_broken(self, entry: CommandEntry) -> BrokenCommandUse | None:
        """Refuse a command a probe measured broken, unless it was waived.

        Returns the waiver record this emission would add, or None when the
        command is not broken here. Nothing is recorded: :meth:`emit` commits
        the record once the block is accepted, so an emission refused by a
        later check leaves no waiver in the manifest (PFS-2103.035).
        """
        # Use evidence_in to record the source build alongside its report. A
        # hotfix can inherit evidence from its base release; the waiver record
        # and refusal must identify that source, not just the requested build.
        evidence = entry.evidence_in(self.version)
        if evidence is None or evidence.record.status is not Status.BROKEN:
            return None
        record = evidence.record
        observed = record.note or "a committed probe measured it not behaving as documented"
        where = (
            f"{evidence.source}, inherited by {self.version.canonical} with no probe on that build"
            if evidence.inherited
            else f"FlightStream {self.version.canonical}"
        )
        reason = self._broken_waivers.get(entry.name)
        if reason is None:
            raise BrokenCommandError(
                f"{entry.name} is recorded broken in "
                f"{where}: {observed}. The evidence is "
                f"{record.report} ({entry.citation}). Emitting it would put a "
                "command in the script that a probe measured not to work, and the "
                "solver accepts the line, so the run would return numbers that "
                "nothing marks as wrong. If this run needs the command anyway, and "
                "re-probing it is the case that does, call "
                f"Script.allow_broken({entry.name!r}, reason=...) first: the command "
                "then emits and the script and the run manifest record it, its "
                "report and your justification."
            )
        return BrokenCommandUse(
            command=entry.name,
            version=self.version.canonical,
            source_version=evidence.source,
            report=record.report,
            note=record.note,
            reason=reason,
        )

    def _bind(self, entry: CommandEntry, args: tuple, kwargs: dict) -> dict[str, object]:
        specs = entry.args
        if len(args) > len(specs):
            raise CommandArgumentError(
                f"{entry.name} takes at most {len(specs)} arguments, got {len(args)} "
                f"({entry.citation})"
            )
        bound: dict[str, object] = {}
        for spec, value in zip(specs, args, strict=False):
            bound[spec.name] = value
        known = {spec.name for spec in specs}
        for key, value in kwargs.items():
            # The measured 26.124 token is not a length unit. Preserve the
            # former keyword without broadening the later enum grammar.
            if (
                entry.name == "IMPORT_WAKE_EDGES_FROM_FILE"
                and key == "units"
                and any(spec.name == "edge_type" and spec.type is ArgType.STR for spec in specs)
            ):
                key = "edge_type"
            if key not in known:
                raise CommandArgumentError(
                    f"{entry.name} has no argument {key!r}; arguments are "
                    f"{', '.join(sorted(known)) or 'none'} ({entry.citation})"
                )
            if key in bound:
                raise CommandArgumentError(
                    f"{entry.name}: argument {key!r} given twice ({entry.citation})"
                )
            bound[key] = value
        checked: dict[str, object] = {}
        for spec in specs:
            if spec.name not in bound:
                if spec.required:
                    raise CommandArgumentError(
                        f"{entry.name} requires argument {spec.name!r} ({entry.citation})"
                    )
                continue
            value = self._resolve_labels(entry, spec, bound[spec.name])
            if spec.is_list:
                checked[spec.name] = _check_list(entry, spec, value)
            else:
                checked[spec.name] = _check_scalar(entry, spec, value)
        self._check_counts(entry, checked)
        from pyflightstream.script._build_forms import _check_bound_form

        _check_bound_form(entry, specs, checked)
        return checked

    def _resolve_labels(self, entry: CommandEntry, spec: ArgSpec, value: object) -> object:
        context = f"{entry.name}: argument {spec.name!r}"
        kind = _reference_kind(spec)
        if kind is None:
            return value
        if spec.is_list:
            if isinstance(value, Sequence) and not isinstance(value, str):
                return [
                    self.entities.resolve(kind, item, context=context, citation=entry.citation)
                    for item in value
                ]
            return value
        if isinstance(value, str):
            return self.entities.resolve(kind, value, context=context, citation=entry.citation)
        return value

    def _check_counts(self, entry: CommandEntry, bound: dict[str, object]) -> None:
        count_value: object | None = None
        for spec in entry.args:
            if spec.name in _COUNT_ARG_NAMES and spec.name in bound:
                count_value = bound[spec.name]
            elif spec.is_list and isinstance(count_value, int):
                if spec.name not in bound:
                    # An omitted optional list must agree with its explicit count. A
                    # positive count without payload makes the solver consume following
                    # commands as data. Only -1, the documented all-entities form, needs
                    # no payload; SOLVER_PROXIMAL_BOUNDARIES on 26.121 permits that form.
                    if count_value != -1:
                        raise CommandArgumentError(
                            f"{entry.name}: the declared count is {count_value} and no "
                            f"{spec.name!r} were given, so the command line would be "
                            "written with no payload under it and the solver would "
                            "read the following commands as its data. Pass the "
                            f"{count_value} values, or pass a count of -1, which is "
                            f"the documented all-entities form ({entry.citation})"
                        )
                    continue
                # -1 TAKES NO PAYLOAD, so a list under it is refused rather
                # than rendered: its lines would follow the count line and
                # the solver would read them as commands (PFS-2104.022).
                given = bound[spec.name]
                if count_value == -1 and len(given):
                    raise CommandArgumentError(
                        f"{entry.name}: the declared count is -1, the documented "
                        f"all-entities form, which takes no payload, and {spec.name!r} "
                        f"holds {len(given)} values. Their lines would follow the "
                        "count line and the solver would read them as commands. Drop "
                        f"the {spec.name!r} values to select every entity, or state "
                        f"their count to select those ({entry.citation})"
                    )
                # Only -1 is exempt as the documented all-entities count. Other
                # negative counts must not bypass the payload-length comparison.
                if count_value != -1 and count_value != len(bound[spec.name]):
                    raise CommandArgumentError(
                        f"{entry.name}: the declared count is {count_value} but "
                        f"{spec.name!r} holds {len(bound[spec.name])} values "
                        f"({entry.citation})"
                    )

    def begin_point(self) -> None:
        """Open a new POINT inside one script, rewinding the phase to init.

        FR-95. A warm steady sweep is one script holding several points,
        and each point runs the same cycle: set its condition, initialise
        if it must, start the solver, analyse, export. The phase guard is
        monotonic across a script, so the second point's
        ``SOLVER_SET_AOA``, an init command, was refused as arriving after
        the export phase the first point had already reached.

        THE REWIND STOPS AT INIT AND THAT IS THE POINT. Geometry and setup
        stay behind it, so a sweep still cannot open a second geometry or
        redefine a coordinate system halfway through, which is the half of
        the phase rule that catches real mistakes. What it allows is the
        cycle a sweep is made of, and nothing wider.

        A single-point script never calls this, so its guard is unchanged.
        """
        init = _ORDERED_PHASES.index(Phase.INIT)
        if self._phase_index is not None and self._phase_index > init:
            self._phase_index = init
            self._phase_setter = ("begin_point", len(self._lines) + 1)

    def emit_after_initialization(self, name: str, /, *args: object, **kwargs: object) -> None:
        """Emit one setup command on an initialised solver, to be initialised again (G02).

        :meth:`emit` refuses a setup command once ``INITIALIZE_SOLVER`` is
        in the script, and that is right for nearly all of them: a frame,
        a motion or a fluid is read when the solver initialises, so after
        it they come too late. A few act on what only the initialisation
        creates. On FlightStream 26.124 the wake-termination detection
        emitted right after a file import of the trailing edges marks
        nothing; emitted after an initialisation it marks the node, and
        the solver uses what it marked only once it initialises again,
        which clears the first initialisation (RPT-069, T07). The log
        reports the trailing-edge groups only during an initialisation,
        which is the inferred reason.

        THIS IS THE ONE DOOR PAST THE PHASE GUARD, AND IT IS NARROW. The
        command must be a setup command; an ``INITIALIZE_SOLVER`` must
        precede it and the solver must not have started. The phase does
        not move, so a frame or a motion after it is still refused. Until
        ``INITIALIZE_SOLVER`` is emitted again, a command of the exec phase
        or a later one, ``START_SOLVER`` first, is refused naming the
        command that waits. Every other check of :meth:`emit` applies.

        Parameters
        ----------
        name : str
            A setup command of this build's database.
        *args, **kwargs
            Its arguments, as :meth:`emit` takes them.

        Raises
        ------
        ScriptOrderError
            If ``name`` is not a setup command, if no ``INITIALIZE_SOLVER``
            precedes it, or if the solver was already started.
        CommandNotInVersionError, CommandArgumentError, ScriptReferenceError
            As :meth:`emit` raises them.

        Examples
        --------
        >>> from pyflightstream.script import Script
        >>> script = Script(version="26.124")
        >>> initialization = dict(
        ...     solver_model="INCOMPRESSIBLE", surfaces=-1,
        ...     wake_termination_x="DEFAULT", symmetry="NONE",
        ... )
        >>> script.emit("INITIALIZE_SOLVER", **initialization)
        >>> script.emit_after_initialization("AUTO_DETECT_WAKE_TERMINATION_NODES")
        >>> script.emit("INITIALIZE_SOLVER", **initialization)
        >>> script.emit("START_SOLVER")
        >>> script.render().count("INITIALIZE_SOLVER")
        2
        """
        entry = self._view[name]
        if entry.phase is not Phase.SETUP:
            raise ScriptOrderError(
                f"{name} belongs to the {entry.phase} phase, and emit_after_initialization carries "
                "a setup command past an initialised solver and nothing else. Emit it "
                "with emit(), which holds it to the phase order"
            )
        if self._initialized_at is None:
            raise ScriptOrderError(
                f"{name}: no {_INITIALIZATION_COMMAND} precedes it, so there is no "
                "initialised solver for it to act on. Emit it with emit(), before the "
                "init phase, where a setup command belongs"
            )
        init = _ORDERED_PHASES.index(Phase.INIT)
        if self._phase_index is not None and self._phase_index > init:
            setter_name, setter_line = self._phase_setter or ("", 0)
            raise ScriptOrderError(
                f"{name}: the script already reached the "
                f"{_ORDERED_PHASES[self._phase_index]} phase ({setter_name} at line "
                f"{setter_line}), so the solver ran on the initialisation at line "
                f"{self._initialized_at}. A setup command after an initialisation acts "
                f"only through a second {_INITIALIZATION_COMMAND}, emitted before the "
                "solver starts"
            )
        line = len(self._lines) + 1
        self._through_the_door = True
        try:
            self.emit(name, *args, **kwargs)
        finally:
            self._through_the_door = False
        self._reinitialization_owed = (name, line)

    def _check_phase(self, entry: CommandEntry) -> tuple[int, tuple[str, int]] | None:
        """Refuse a command whose phase has passed; return the phase it reaches.

        Returns the new phase index and its setter when the command moves the
        phase forward, or None when it does not. Nothing is moved here:
        :meth:`emit` commits the move once the block is accepted, so a command
        refused by a later check does not leave the script in a phase it never
        reached (PFS-2104.019).
        """
        if entry.phase is Phase.CONTROL:
            return None
        if self._through_the_door:
            # emit_after_initialization judged this emission, and it moves no
            # phase: the next command still meets the init phase.
            return None
        index = _ORDERED_PHASES.index(entry.phase)
        if self._reinitialization_owed is not None and index > _ORDERED_PHASES.index(Phase.INIT):
            waiting, line = self._reinitialization_owed
            raise ScriptOrderError(
                f"{entry.name} belongs to the {entry.phase} phase, and {waiting} at line {line} "
                "was emitted on an initialised solver, which uses what it marked only "
                f"once it initialises again. Emit {_INITIALIZATION_COMMAND} after it, "
                "with the settings of the first, before the solver starts"
            )
        if self._phase_index is not None and index < self._phase_index:
            setter_name, setter_line = self._phase_setter
            current = _ORDERED_PHASES[self._phase_index]
            raise ScriptOrderError(
                f"{entry.name} is a {entry.phase} command, but the script already "
                f"reached the {current} phase ({setter_name} at line {setter_line}). "
                "Auxiliary definitions such as coordinate systems, actuators, and "
                "motions must precede solver initialization; the phase order is "
                "geometry, setup, init, exec, analysis, export."
            )
        if self._phase_index is None or index > self._phase_index:
            return index, (entry.name, len(self._lines) + 1)
        return None

    def _check_references(self, entry: CommandEntry, bound: dict[str, object]) -> None:
        if entry.name == "DELETE_COORDINATE_SYSTEM" and bound.get("frame") == 1:
            raise CommandArgumentError(
                "DELETE_COORDINATE_SYSTEM: frame 1 is the reference frame and cannot "
                "be deleted. Select a local frame with an index greater than 1 "
                f"({entry.citation})"
            )
        for spec in entry.args:
            if spec.name not in bound:
                continue
            context = f"{entry.name}: argument {spec.name!r}"
            value = bound[spec.name]
            kind = _reference_kind(spec)
            if kind is not None and not spec.is_list:
                self.entities.check_index(
                    kind,
                    value,
                    context=context,
                    citation=entry.citation,
                    all_sentinel=spec.all_sentinel,
                )
            elif kind is not None and isinstance(value, Sequence) and not isinstance(value, str):
                # Each item uses the argument's declared sentinel, just like a scalar.
                # Frames and motions have no documented -1 form; surface selections
                # may instead declare zero.
                for item in value:
                    self.entities.check_index(
                        kind,
                        item,
                        context=context,
                        citation=entry.citation,
                        all_sentinel=spec.all_sentinel,
                    )
            kind = _COUNT_REFERENCE_ARGS.get(spec.name)
            if kind is not None:
                self.entities.check_boundary_count(value, context=context, citation=entry.citation)

    def _format_scalar(self, value: object) -> str:
        return str(value)

    def _list_lines(self, spec: ArgSpec, items: list) -> list[str]:
        rendered = [self._format_scalar(item) for item in items]
        if spec.separator is ListSeparator.NEWLINE:
            return rendered
        joiner = "," if spec.separator is ListSeparator.COMMA else " "
        return [joiner.join(rendered)]

    def _render_command(self, entry: CommandEntry, bound: dict) -> tuple[list[str], bool]:
        for position, spec in enumerate(entry.args):
            if spec.joins_previous and spec.name in bound:
                anchor = entry.args[position - 1]
                if anchor.name not in bound:
                    raise CommandArgumentError(
                        f"{entry.name}: {spec.name} needs {anchor.name}, the preceding "
                        f"argument it joins ({entry.citation})"
                    )
        provided = [(spec, bound[spec.name]) for spec in entry.args if spec.name in bound]
        if entry.layout is Layout.BARE:
            return [entry.name], False
        if entry.layout is Layout.INLINE:
            return self._render_inline(entry, provided)
        if entry.layout is Layout.PAYLOAD_LINES:
            return self._render_payload_lines(entry, provided)
        if entry.layout is Layout.PARAM_LINES:
            return self._render_param_lines(entry, provided)
        return self._render_keyword_block(entry, provided)

    def _render_inline(
        self, entry: CommandEntry, provided: list[tuple[ArgSpec, object]]
    ) -> tuple[list[str], bool]:
        """Render an inline command: its values on one line, own-line values after it."""
        inline_parts = [entry.name]
        tail_lines: list[str] = []
        for spec, value in provided:
            if spec.own_line:
                tail_lines.append(self._format_scalar(value))
            elif spec.is_list:
                inline_parts.append(" ".join(self._format_scalar(item) for item in value))  # type: ignore[attr-defined]
            else:
                from pyflightstream.script._build_forms import _check_inline_token

                _check_inline_token(entry, spec, value)
                inline_parts.append(self._format_scalar(value))
        return [" ".join(inline_parts), *tail_lines], bool(tail_lines)

    def _render_payload_lines(
        self, entry: CommandEntry, provided: list[tuple[ArgSpec, object]]
    ) -> tuple[list[str], bool]:
        """Render a payload-lines command: scalars inline, each list on lines after it."""
        inline_parts = [entry.name]
        tail_lines: list[str] = []
        for spec, value in provided:
            if spec.is_list:
                tail_lines.extend(self._list_lines(spec, value))  # type: ignore[arg-type]
            else:
                inline_parts.append(self._format_scalar(value))
        return [" ".join(inline_parts), *tail_lines], True

    def _render_param_lines(
        self, entry: CommandEntry, provided: list[tuple[ArgSpec, object]]
    ) -> tuple[list[str], bool]:
        """Render a param-lines command: one ``NAME value`` line per argument."""
        lines = [entry.name]
        for spec, value in provided:
            if spec.is_list:
                lines.extend(self._list_lines(spec, value))  # type: ignore[arg-type]
            elif spec.type is ArgType.PATH:
                lines.append(self._format_scalar(value))
            else:
                lines.append(f"{spec.name.upper()} {self._format_scalar(value)}")
        return lines, True

    def _render_keyword_block(
        self, entry: CommandEntry, provided: list[tuple[ArgSpec, object]]
    ) -> tuple[list[str], bool]:
        """Render a keyword-block command: values on its line first, then one keyword per line."""
        lines = [entry.name]
        for spec, value in provided:
            if spec.on_command_line:
                # The leading arguments of a keyword block that sit on the
                # command's own line (WRAPPER_EDIT_LOCAL_CONTROL, FSM-26.120
                # p.314). The schema holds them to the leading positions,
                # so lines[0] is still the command name here.
                lines[0] += f" {self._format_scalar(value)}"
            elif spec.is_list:
                lines.extend(self._list_lines(spec, value))  # type: ignore[arg-type]
            elif spec.type is ArgType.BOOL:
                # Presence keyword (FSM-26.120 p.307): True is the bare keyword
                # line, False emits nothing.
                if value:
                    lines.append(spec.name.upper())
            elif spec.joins_previous:
                lines[-1] += f" {self._format_scalar(value)}"
            else:
                lines.append(f"{spec.name.upper()} {self._format_scalar(value)}")
        if entry.terminator is not None:
            lines.append(entry.terminator)
        return lines, True
