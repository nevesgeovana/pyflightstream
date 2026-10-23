"""The steady builders: one steady point, and a steady sweep in one script.

:func:`_build_steady` builds the run type ``steady``;
:func:`build_steady_sweep` builds every point of a sweep into one script.
"""

from __future__ import annotations

from collections.abc import (
    Mapping,
    Sequence,
)

import pyflightstream.cases._setup_link as _setup_link
from pyflightstream.cases import (
    CampaignConfigError,
    SimCase,
    classify_outputs,
)
from pyflightstream.cases import (
    setup_surfaces as _setup_surfaces,
)
from pyflightstream.cases._unsteady_actions import (
    UNSTEADY_COUNTER_ACTION,
)
from pyflightstream.commands import (
    CommandNotInVersionError,
    CommandRegistry,
)
from pyflightstream.results import (
    MalformedOutputError,
    SurfaceFrame,
)
from pyflightstream.script import (
    MARCH_ACTIONS,
    Script,
)

from ._actuator import (
    _actuator_disc,
    _the_actuator_the_row_names,
)
from ._clock import (
    unsteady_export_threshold,
)
from ._conventions import (
    _AVERAGE_ACTION,
    BuildCapabilities,
    Workflow,
    WorkflowConventions,
    WorkflowCoverageError,
    require_coverage,
    resolve_workflow,
    select_workflow,
)
from ._exports import (
    surface_time_averaging,
)
from ._frames import (
    _flat_rotor_frames,
    _moment_frame,
    _rotations,
    _setup_frames,
    _significant_digits,
    _translations,
)
from ._freestream import (
    _finish_custom_field_coverage,
    _fluid,
    _free_stream,
    _refuse_wake_termination_without_a_clock,
    _RowFreestream,
    _the_custom_freestream,
)
from ._geometry import (
    _open_geometry,
)
from ._probes import (
    _refuse_unmeasured_normal_probes,
)
from ._rows import (
    _angle,
    _refuse_rotor_shedding,
    _refuse_unregistered_keys,
    _turning_rate,
    continuation_of,
)
from ._skeleton import (
    _refuse_a_free_body_off_the_unsteady_run,
    _script_init,
    _script_solve_and_export,
    _script_tail,
)
from ._solver_settings import (
    _analysis,
    _custom_flags,
    _raw_commands,
    _refuse_a_coupling_step_without_a_clock,
    _refuse_sideslip_under_mirror,
    _settings,
)
from ._timing import (
    march_strategy,
)
from ._vocabulary import (
    _UNSTEADY_RECIPES,
    _refuse_retired_window_keys,
)


def _build_steady(case: SimCase, script: Script, conventions: WorkflowConventions) -> None:
    """Build a steady polar point: open, free stream, settings, solve, export.

    The open is FIRST and only where the case names a geometry
    (:func:`_open_geometry`); a case naming none emits no open command.
    """
    _refuse_wake_termination_without_a_clock(case)
    _refuse_a_coupling_step_without_a_clock(case)
    # A steady row stating an export threshold is refused there, naming
    # the time loop it lacks (PFS-2031.18); a row stating none returns.
    unsteady_export_threshold(case, conventions, version=script.version)
    _refuse_unregistered_keys(case, "steady")
    disc = _the_actuator_the_row_names(case)
    custom = _the_custom_freestream(case)
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
    moved = {"MRP": frame, **setup_frames}
    frames.update(_translations(case, script, moved))
    frames.update(_rotations(case, script, moved))
    _actuator_disc(case, script, frames, disc)
    _significant_digits(case, script)
    _free_stream(case, script, frames, custom)
    _fluid(case, script)
    _settings(case, script)
    _script_tail(conventions, case, script, frame, unsteady=False, frames=frames)


def _refuse_a_free_stream_that_moves(
    first: SimCase, point_case: SimCase, custom: _RowFreestream | None
) -> None:
    """Refuse a later point of a one-script sweep whose free stream is not the first's.

    THE FREE STREAM IS EMITTED ONCE, from the first point, and a later point
    restates its two angles alone. A body-rate sweep (``pitch_rate:sweep``) or a
    custom field that changes between points was therefore solved at the first
    point's free stream under every point's name, which converges and exports.
    """
    stated = _turning_rate(point_case)
    if stated == _turning_rate(first) and _the_custom_freestream(point_case) == custom:
        return
    raise CampaignConfigError(
        f"case {point_case.sim_id!r}: point {point_case.point} of a steady sweep built as one "
        f"script turns its free stream differently from the first point {first.point} "
        f"({'body rate ' + str(stated) if stated else 'custom field or body rate'}), and one "
        "script states the free stream once, for the first point. Run each point of a swept "
        "body rate or field as its own job."
    )


def build_steady_sweep(
    point_cases: Sequence[SimCase],
    script: Script,
    *,
    cold: bool = True,
) -> None:
    """Build ONE script for every point of a steady sweep.

    FR-95: a steady row is one job. The
    shape is the predecessor toolchain's steady recipe:
    the geometry is opened once, the fluid and the solver are set once,
    the solver is initialised once, and then for each point the two
    angles are set, the solver is started and the outputs are exported.

    Cold starts are the default (R13): every point, including
    the first point of a reopened simulation, clears the solution before
    solving. Explicit ``cold=False`` selects warm behavior.

    THE ORDER MATTERS AND IT IS RECORDED: a warm sweep's result depends
    on the order its points ran in, which nothing recorded before this
    release. The points are emitted in the order given, and the run
    layer records that order with the job.

    Parameters
    ----------
    point_cases : sequence of SimCase
        One case per point, each already carrying its ``point`` and its
        ``outputs``. They differ only in those two fields and in the ATTITUDE
        of the point; everything the preamble reads is taken from the FIRST.
        A row whose sweep moves the AIR STATE never reaches here: the fluid is
        a setup command, which the solver takes before it is initialised, so
        such a row is one job per point (``_is_one_job``).
    script : Script
        The script every point is emitted into.
    cold : bool
        Clear the solution before every point; True by default. Explicit
        False retains a previous point's converged solution. Geometry and
        setup are emitted once in either mode.
    """
    if not point_cases:
        raise CampaignConfigError(
            "a steady sweep needs at least one point; a row with none is a row "
            "with nothing to run and the campaign refuses it before this."
        )
    first = point_cases[0]
    if first.fsi is not None or first.fsi_external is not None:
        raise CampaignConfigError(
            f"case {first.sim_id!r} couples a fixed wing (FSI-G), and a steady coupled script "
            "ends at EXECUTE_AEROELASTIC_ANALYSIS, so one script cannot run a second point; "
            "each point of a coupled row is its own run."
        )
    _refuse_a_free_body_off_the_unsteady_run(first)
    conventions = WorkflowConventions.for_case(first)
    _before_the_build(first, script, conventions=None, registry=None)
    _refuse_wake_termination_without_a_clock(first)
    _refuse_a_coupling_step_without_a_clock(first)
    unsteady_export_threshold(first, conventions, version=script.version)
    _refuse_unregistered_keys(first, "steady")
    # THE DISC IS THE ROW'S, emitted once with the setup: a steady sweep varies
    # the attitude between points and nothing else (G06). So is the custom
    # free stream (G15).
    disc = _the_actuator_the_row_names(first)
    custom = _the_custom_freestream(first)
    _raw_commands(first, script, "control")
    _custom_flags(first, script, "control")
    _raw_commands(first, script, "geometry")
    _custom_flags(first, script, "geometry")
    _open_geometry(first, script)
    _raw_commands(first, script, "setup")
    _custom_flags(first, script, "setup")
    frame = _moment_frame(first, script)
    frames: dict[str, int | None | Mapping[str, int]] = {
        "MRP": frame,
        **_flat_rotor_frames(first, None),
    }
    setup_frames = _setup_frames(first, script)
    frames.update(setup_frames)
    moved = {"MRP": frame, **setup_frames}
    frames.update(_translations(first, script, moved))
    frames.update(_rotations(first, script, moved))
    _actuator_disc(first, script, frames, disc)
    _significant_digits(first, script)
    _free_stream(first, script, frames, custom)
    _fluid(first, script)
    _settings(first, script)
    _script_init(first, script, frame, frames=frames)
    for index, point_case in enumerate(point_cases):
        if index:
            # A NEW POINT REOPENS THE CYCLE. The phase guard is monotonic
            # across a script and a sweep is several points in one, so the
            # rewind is stated here rather than left for the guard to
            # refuse. It stops at init: the geometry stays open and the
            # setup stays behind it.
            script.begin_point()
        if index:
            # Emit only this point's two angles directly. The remaining settings
            # stay fixed across the sweep. Calling solver_settings would emit
            # defaults for omitted arguments, overwriting the stated minimum Cp,
            # thread count and iteration cap in the retained solver state.
            _refuse_sideslip_under_mirror(point_case)
            _refuse_a_free_stream_that_moves(first, point_case, custom)
            script.emit("SOLVER_SET_AOA", _angle(point_case, "alpha"))
            script.emit("SOLVER_SET_SIDESLIP", _angle(point_case, "beta"))
            # Restate the loads frame and moments model before each point's
            # START_SOLVER (B05, RPT-064). Whether CLEAR_SOLUTION resets them is
            # unmeasured, so do not rely on the first point's settings.
            _analysis(point_case, script, frame)

        # EACH POINT EXPORTS ITS OWN NAMES, so each gets its own
        # conventions. One set for the whole sweep would have every point
        # writing the first point's file names, which is the collision the
        # per-point naming exists to prevent.
        if cold:
            # The clear the predecessor left commented out, and it is the
            # only line by which a cold sweep differs from a warm one.
            #
            # CLEAR_SOLUTION AND NOT SOLVER_CLEAR, measured rather than
            # chosen by the name: SOLVER_CLEAR is documented by the 25.000
            # edition alone and no later one prints it, so it does not
            # exist on the build this study runs. CLEAR_SOLUTION is
            # verified on 26.120 through 26.124 (CMP-26120_2026-08-08_full,
            # CMP-26121_2026-08-08_full, CMP-26122_2026-08-11_full,
            # CMP-26123_2026-08-17_full-sim, CMP-26124_2026-09-14_full-sim;
            # the settings sheet reports the iteration counter back at 0),
            # takes no argument, and
            # sits in the exec phase, which is where a point begins. It
            # clears the SOLUTION and leaves the initialisation standing,
            # which is exactly what a cold point inside an initialised
            # sweep needs.
            script.emit("CLEAR_SOLUTION")
        _script_solve_and_export(
            WorkflowConventions.for_case(point_case),
            point_case,
            script,
            unsteady=False,
            frames=frames,
        )
    script.emit("CLOSE_FLIGHTSTREAM")
    _finish_custom_field_coverage(first, script)
    _after_the_build(first, script)


def _before_the_build(
    case: SimCase,
    script: Script,
    *,
    conventions: WorkflowConventions | None,
    registry: CommandRegistry | None,
) -> Workflow:
    """Refuse what no build of ``case`` may emit, and label its march; return its workflow.

    THE CHECKS :func:`~pyflightstream.cases.workflows.build_script` RUNS BEFORE THE
    BUILDER, in one home so the steady sweep runs them too: it built through its
    own body and skipped every one, the boundary-layer dependency check among them.
    """
    _refuse_retired_window_keys(case)
    _refuse_unmeasured_normal_probes(case, script)
    _refuse_rotor_shedding(case)
    if case.pproc is not None and case.pproc.products.boundary_layer_integrals:
        names = list((conventions.outputs if conventions else None) or case.outputs)
        kinds = classify_outputs(names)
        # THE POST READS THE VTK AND THE _cp.txt SECTIONS EXPORT (PFS-2117.018): a point that
        # exports a Tecplot surface alone passed this guard and then had the product refused.
        missing = [
            what
            for kind, what in (
                ("sections", "the section-coordinate export (the _cp.txt file)"),
                ("vtk", "the VTK surface export"),
            )
            if kind not in kinds
        ]
        if missing:
            raise CampaignConfigError(
                f"case {case.sim_id!r}: boundary_layer_integrals requires {' and '.join(missing)} "
                "of the same point, and the outputs it declares do not name it. Retain the "
                "pproc's generated output dependencies: do not list the point's outputs by "
                "hand, or add the missing file to them, and plan the point again"
            )
    workflow = resolve_workflow(select_workflow(case))
    require_coverage(workflow, script.version, registry=registry)
    if case.pproc is not None and case.pproc.time_averaging is not None:
        # G25: THE PACKAGE AVERAGES THE SURFACE THE RUN WRITES AS TECPLOT, from
        # its per-step VTK exports; a point exporting no Tecplot has nothing to
        # average into one.
        names = list((conventions.outputs if conventions else None) or case.outputs)
        if select_workflow(case) in _UNSTEADY_RECIPES:
            try:
                script.entry(_AVERAGE_ACTION)
            except CommandNotInVersionError as error:
                raise CampaignConfigError(
                    f"case {case.sim_id!r}: the pproc's [time_averaging] exports the surface "
                    f"at every step of its window through an unsteady solver action, and "
                    f"FlightStream {script.version.canonical} does not carry it: {error} Run "
                    "the row on a build that does, or remove [time_averaging]."
                ) from error
        if "tecplot" not in classify_outputs(names):
            raise CampaignConfigError(
                f"case {case.sim_id!r}: the pproc's [time_averaging] asks for the surface "
                "averaged over its window, which the package writes as a Tecplot from the "
                "per-step VTK exports, and the point exports no Tecplot (its outputs "
                f"{', '.join(names) or 'name none'}). Leave tecplot on under [exports], "
                "the default, or remove [time_averaging]."
            )
        surface_time_averaging(case)
    # THE SEAM (ARCH-0200): how this case is marched on this build, decided
    # once and before the first emission, so a refusal leaves nothing written.
    script.march_strategy = march_strategy(
        case,
        capabilities=BuildCapabilities.for_build(
            script.version.canonical, registry=script.registry
        ),
        registry=registry,
    )
    return workflow


def _after_the_build(case: SimCase, script: Script) -> None:
    """Stamp and check the finished script: the steps build_script runs after the builder.

    In one home with :func:`_before_the_build`, so the steady sweep's one script
    gets them once, on its first point: the setup keys that reached nothing, the
    loads frame of every section block a boundary-layer product reads, the
    untranslatable surface and the march label.
    """
    _setup_surfaces.refuse_setup_keys_that_reached_nothing(script, case)
    if case.pproc is not None and case.pproc.products.boundary_layer_integrals:
        for block in script.section_blocks:
            block["loads_frame_index"] = script.loads_frame
    # A continuation's loads frame is its saved simulation's, which the run takes
    # from the run it continues; only an unsteady row continues one.
    if select_workflow(case) not in _UNSTEADY_RECIPES or continuation_of(case) is None:
        refuse_an_untranslatable_surface(case, script)
    # THE LABEL IS THE SCRIPT: a point recorded as marched by actions registers
    # at least one of the package's own, and one recorded as a single march
    # registers none but the step counter, which counts only on such a row
    # (FR-314). The builders emit the actions from the row, so this is where the
    # two are held together (architect lens, GOAL-023 opening round). A setup's
    # own per-step actions (FR-319) are the user's, and no label's.
    emitted = any(
        name != UNSTEADY_COUNTER_ACTION for name in _setup_link.package_actions(case, script)
    )
    if script.march_strategy is not None and emitted != (script.march_strategy == MARCH_ACTIONS):
        raise WorkflowCoverageError(
            f"internal defect: case {case.sim_id!r} on FlightStream {script.version.canonical} "
            f"was labelled {script.march_strategy!r} and its script registers "
            f"{len(script.unsteady_actions)} unsteady solver action(s). Report it; the "
            "label and the script must agree before either is recorded."
        )


def refuse_an_untranslatable_surface(case: SimCase, script: Script) -> None:
    """Refuse a script whose Tecplot surface cannot be written from its VTK (G45).

    The solver writes the VTK in the analysis loads frame (RPT-074), so the
    Tecplot is written from it by undoing that frame, which the package can do
    only where this script placed it: a frame an opened project carries, or one
    a command moved in a way the frame ledger does not follow, has no placement.
    A frame whose axes are not orthonormal is refused too, and so is a
    ``vtk_variables`` naming some of ``VX``, ``VY``, ``VZ`` and not all three
    where the loads frame is not the reference frame, since the solver writes
    each component from all three. Called at the end of every build, so a
    refusal costs no seat; a continuation is not asked, because its loads frame
    is the saved simulation's and the run takes it from the run it continues.

    Parameters
    ----------
    case : SimCase
        The point's case; its pproc ``vtk_variables`` are read.
    script : Script
        The script just built; its recorded surface translations are checked.

    Returns
    -------
    None
        Returns normally when every translation can be undone.

    Raises
    ------
    CampaignConfigError
        Naming the case, the Tecplot output and the frame.
    """
    variables = case.pproc.vtk_variables if case.pproc is not None else None
    velocity = [name for name in ("VX", "VY", "VZ") if variables and name in variables]
    for translation in script.surface_translations:
        stated = translation.get("frame")
        dat = translation.get("dat")
        assert isinstance(stated, Mapping)
        where = (
            f"case {case.sim_id!r}: its Tecplot surface {dat} is written by the package from "
            f"the VTK the solver exports in the analysis loads frame (RPT-074)"
        )
        try:
            frame = SurfaceFrame.from_record(stated)
        except MalformedOutputError as error:
            raise CampaignConfigError(
                f"{where}, and frame {stated.get('frame')} cannot be undone: {error}. Place "
                "the loads frame with the reference's frames, or set tecplot = false under "
                "the pproc's [exports]."
            ) from error
        # ONLY A TURN MIXES THE COMPONENTS: a pure translation of the origin leaves
        # each velocity component as the solver wrote it, so one alone can be written back.
        if frame.turns and velocity and len(velocity) != 3:
            raise CampaignConfigError(
                f"{where}, frame {frame.index} is not the reference frame, and the pproc's "
                f"vtk_variables names {', '.join(velocity)} of the three velocity components: "
                "the solver writes each from all three, so one alone cannot be written back "
                "in the reference frame. Name VX, VY and VZ together, or none of them."
            )
