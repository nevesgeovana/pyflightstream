"""The steady builders: one steady point, and a steady sweep in one script.

:func:`_build_steady` builds the run type ``steady``;
:func:`build_steady_sweep` builds every point of a sweep into one script.
"""

from __future__ import annotations

from collections.abc import (
    Mapping,
    Sequence,
)

from pyflightstream.cases import (
    CampaignConfigError,
    SimCase,
)
from pyflightstream.results import (
    MalformedOutputError,
    SurfaceFrame,
)
from pyflightstream.script import (
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
    WorkflowConventions,
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
    _the_custom_freestream,
)
from ._geometry import (
    _open_geometry,
)
from ._rows import (
    _angle,
    _refuse_unregistered_keys,
)
from ._skeleton import (
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


def _build_steady(case: SimCase, script: Script, conventions: WorkflowConventions) -> None:
    """Build a steady polar point: open, free stream, settings, solve, export.

    The open is FIRST and only where the case names a geometry
    (:func:`_open_geometry`), so a case that names none emits exactly
    the lines this workflow emitted before 0.8.1.
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

    Cold starts are the default from 0.29.0 (R13): every point, including
    the first point of a reopened simulation, clears the solution before
    solving. Explicit ``cold=False`` retains the previous warm behavior.

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
    if first.fsi is not None:
        raise CampaignConfigError(
            f"case {first.sim_id!r} couples a fixed wing (FSI-G), and a steady coupled script "
            "ends at EXECUTE_AEROELASTIC_ANALYSIS, so one script cannot run a second point; "
            "each point of a coupled row is its own run."
        )
    conventions = WorkflowConventions.for_case(first)
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
            # The angles of THIS point, EMITTED DIRECTLY. Only the two:
            # the rest of the settings block was emitted once and does not
            # vary over a sweep of the incidence, and the predecessor
            # toolchain sets exactly these two per point.
            #
            # NOT THROUGH `solver_settings`, and that was a silent physics
            # change. That helper emits its own default for an argument
            # the caller omits, so a sweep whose setup states any
            # SOLVER_MINIMUM_CP other than the library default had point
            # one solved at the stated value and every point after it at
            # -100, inside ONE script where the solver keeps the last one.
            # Reproduced on a three-point sweep stating -3.0: -3.0, then
            # -100, then -100. It also replaced the setup snapshot, losing
            # the thread count and the iteration cap the first point was
            # given. Found by the independent Codex review of `main`,
            # 2026-09-13 (GEO-047-C01), and by nothing in-house.
            _refuse_sideslip_under_mirror(point_case)
            script.emit("SOLVER_SET_AOA", _angle(point_case, "alpha"))
            script.emit("SOLVER_SET_SIDESLIP", _angle(point_case, "beta"))
            # THE LOADS FRAME AND THE MOMENTS MODEL ARE RESTATED PER POINT
            # (B05). Until 0.27.0 each point stated them after its own
            # START_SOLVER; they now belong before it (RPT-064), and whether a
            # CLEAR_SOLUTION between points resets them is not measured, so
            # every point states them again rather than relying on the first.
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
            # verified on 26.120 through 26.123, takes no argument, and
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
    refuse_an_untranslatable_surface(first, script)


def refuse_an_untranslatable_surface(case: SimCase, script: Script) -> None:
    """Refuse a script whose Tecplot surface cannot be written from its VTK (G45 of 0.28.0).

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
        moved = frame.turns or any(float(value) != 0.0 for value in frame.origin)
        if moved and velocity and len(velocity) != 3:
            raise CampaignConfigError(
                f"{where}, frame {frame.index} is not the reference frame, and the pproc's "
                f"vtk_variables names {', '.join(velocity)} of the three velocity components: "
                "the solver writes each from all three, so one alone cannot be written back "
                "in the reference frame. Name VX, VY and VZ together, or none of them."
            )
