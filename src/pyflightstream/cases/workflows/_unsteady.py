"""The unsteady builder, and the continuation of a run that stopped on its wall clock.

:func:`_build_unsteady` builds the run type ``unsteady``;
:func:`_build_continuation` the script that resumes a run from its saved
state.
"""

from __future__ import annotations

from collections.abc import (
    Callable,
    Mapping,
)

from pyflightstream.cases import (
    CampaignConfigError,
    SimCase,
)
from pyflightstream.cases import (
    acoustics as _acoustics,
)
from pyflightstream.cases._unsteady_actions import (
    register_unsteady_actions,
)
from pyflightstream.script import (
    Script,
    helpers,
)

from ._actuator import (
    _actuator_disc,
    _the_actuator_the_row_names,
)
from ._clock import (
    UnsteadyExportThreshold,
    _refuse_rotor_keys_on_a_rotorless_run,
    _refuse_wake_termination_without_a_rotor,
    unsteady_export_threshold,
)
from ._conventions import (
    WorkflowConventions,
)
from ._frames import (
    _flat_rotor_frames,
    _moment_frame,
    _rotations,
    _rotor_frame,
    _setup_frames,
    _significant_digits,
    _translations,
)
from ._freestream import (
    _fluid,
    _free_stream,
    _the_custom_freestream,
)
from ._geometry import (
    _configuration_comment,
    _open_geometry,
)
from ._motion import (
    _optional_rotor_speed,
)
from ._pproc import (
    _pproc_plots,
)
from ._probes import (
    _normal_probes_of_a_continuation,
    _pproc_probes,
)
from ._rows import (
    _refuse_unregistered_keys,
    _require_the_averaging_window,
    continuation_of,
    rotor_speed,
    row_walltime_s,
)
from ._skeleton import (
    _acoustic_setup,
    _script_tail,
)
from ._solver_settings import (
    _custom_flags,
    _raw_commands,
    _refuse_the_loads_selections_on_a_march,
    _settings,
)
from ._timing import (
    rotor_time_stepping,
    unsteady_time_stepping,
)
from ._vocabulary import (
    COLD_START_VARIABLE,
)


def _build_continuation(
    case: SimCase,
    script: Script,
    conventions: WorkflowConventions,
    saved: str,
    iterations: int,
    *,
    threshold: UnsteadyExportThreshold | None = None,
    build: Callable[[SimCase, Script], None] | None = None,
) -> None:
    """Continue a march the wall clock stopped, from the simulation it saved.

    A MEASURED SOLVER BEHAVIOUR, and the whole shape rests on it: the
    solver DOES resume an unsteady march from a saved file, picking up
    where it stopped and running the new iteration count it is given. That
    is what makes this a CONTINUATION rather than a re-march with a better
    initial condition, and the difference is the one thing a user cannot
    see in the numbers afterwards.

    SO THE SCRIPT IS SHORT, and every line it does not emit is a line the
    saved file already carries. It opens that file with the solver
    initialization LOADED, which is the opposite of every other open this
    package writes and is the entire mechanism: `OPEN <file> ENABLE`
    restores the state, and a `DISABLE` here would silently start the run
    over from a mesh.

    NO GEOMETRY IMPORT, NO FRAMES, NO MOTIONS, NO BOUNDARY DECLARATION.
    They are in the file. Re-emitting them would either be redundant or,
    worse, replace what the stopped run actually had with what the row says
    today, which is the shape that made a recorded flight condition read
    back as a different number in a regenerated product.

    NO ``INITIALIZE_SOLVER`` AND NO ACTION REGISTRATION (FR-396, 0.35.0).
    Measured on 26.124 (RPT-134): an initialization after the ``OPEN`` clears
    the reopened solution and the march restarts at step 1, and the actions
    the saved file carries run beside any registered again, twice a step.
    :func:`~._skeleton._script_init` skips the initialization of a reopened
    state, and :func:`_the_actions_the_saved_state_runs` records the actions
    without registering them.

    THE STEP COUNT IS THE REMAINDER AND NOT THE ROW'S ORIGINAL, computed by
    :func:`restart_iterations` against the record being continued. A
    builder that passed the row's own count through would re-march the
    whole history, which is exactly what the release before this one
    refused the key to prevent.

    NO FREE STREAM EITHER, and a custom one is JUDGED all the same (G15). The
    saved file carries the free stream the stopped run solved in, and
    :func:`~pyflightstream.run.resolve_continuation` refuses a field that run
    did not read; the row's field is resolved and read here by the same
    function the full builder calls, before the first emission, so an angle,
    a body rate or a file not in its form beside it is refused on a
    continuation exactly as on a run from the mesh.
    """
    _the_custom_freestream(case)
    _acoustics.refuse_acoustics_on_a_continuation(case)
    # FR-417 R6: NORMAL PROBES ARE CREATED AFTER THE CONTINUED MARCH, as the full
    # script creates them; `build` is the row's full builder, run on a scratch.
    probes = [] if build is None else _normal_probes_of_a_continuation(case, script, build)
    _configuration_comment(case, script)
    # ENABLE, ALWAYS, and this is the one place in this package where the
    # initialisation flag is not the row's to choose: a continuation that
    # did not load the stored state would not be one.
    script.emit("OPEN", saved, "ENABLE")
    # THE TIME STEP IS THE ROW'S OWN AND IS UNCHANGED. It is the SAME row:
    # only the count of steps still owed differs, and a continuation that
    # marched the remainder at a different step would change the character
    # of the march halfway through and record nothing saying so. Derived
    # here exactly as the full builder derives it, so the two cannot drift.
    if case.recipe == "unsteady_rotor":
        clock = _optional_rotor_speed(case)
        stepping = rotor_time_stepping(
            case, speed=clock if clock is not None else rotor_speed(case)
        )
    else:
        stepping = unsteady_time_stepping(case)
    helpers.unsteady_solver(script, time_iterations=iterations, delta_time=stepping.delta_time_s)
    _the_actions_the_saved_state_runs(script, threshold, walltime=row_walltime_s(case) is not None)
    _script_tail(
        conventions,
        case,
        script,
        None,
        unsteady=True,
        reopens_a_saved_state=True,
        replayed_probes=probes,
    )


def _the_actions_the_saved_state_runs(
    script: Script, threshold: UnsteadyExportThreshold | None, *, walltime: bool
) -> None:
    """Record the row's unsteady actions on a continuation, and emit no registration (FR-396 R2).

    THE REOPENED STATE ALREADY RUNS THEM. A simulation the package saved keeps
    the unsteady solver actions its run registered, and an action a script
    registers again under the same name does not replace the saved one: the
    solver runs both. Measured on 26.124 (RPT-134, RPT-135, FR-308): a
    continuation that registered the step counter again ran it twice a step,
    24 times for 12 steps. So no ``SET_NEW_UNSTEADY_SOLVER_ACTION`` line is
    emitted here.

    THE USES ARE STILL RECORDED, exactly as :func:`register_unsteady_actions`
    records them for this row on this build, because the saved actions run
    the files the run layer stages from them: the counter program, the parked
    exports script, the wall clock and its stop script, under ``actions/`` of
    the datapoint folder, which the continuation's archive emptied. A build
    that does not document the action command is refused as it is on a run
    from the mesh.

    The saved state is taken to carry the actions this row registers: it is
    the state the package's own run of the same row saved, and every unsteady
    row has registered its counter since 0.33.0 (FR-314).
    """
    carried = Script(script.version, script.registry)
    register_unsteady_actions(carried, threshold, walltime=walltime)
    script._unsteady_actions.update((use.name, use) for use in carried.unsteady_actions)
    script._pending_action_scripts.update(carried.pending_action_scripts)


def _refuse_cold_start_on_a_march(case: SimCase, run_type: str) -> None:
    """Refuse ``COLD_START`` on an unsteady row, at plan, naming the key (G36 of 0.28.0).

    The clear is a line of the steady sweep's one script, where each point would
    otherwise start from the previous point's converged solution. Every point of
    an unsteady row is its own job and starts from no solution, so the key, true
    or false, could only ever be read as doing what it does not. A continuation is
    refused the same way: it reopens a saved state and clears nothing either.
    """
    stated = case.variables.get(COLD_START_VARIABLE)
    if stated is None or str(stated).strip() == "":
        return
    raise CampaignConfigError(
        f"case {case.sim_id!r}: {COLD_START_VARIABLE} is a key of a steady sweep over the "
        f"attitude, and this row runs {run_type}: every point of it is its own job and "
        "starts from no solution, so the key would change nothing. Remove "
        f"{COLD_START_VARIABLE} from the row."
    )


def _build_unsteady(case: SimCase, script: Script, conventions: WorkflowConventions) -> None:
    """Build an unsteady point of a body that does not move.

    The rotor builder without the rotor: no coordinate system, no
    motion, and a clock stated directly rather than derived from a
    speed. Both refusals run before the first emission.
    """
    _refuse_the_loads_selections_on_a_march(case)
    _refuse_cold_start_on_a_march(case, "unsteady")
    # A CONTINUATION IS A DIFFERENT SCRIPT, not this one with a shorter
    # march, so the branch is HERE and not further down: every line below
    # describes a run that starts from a mesh, and a continuation starts
    # from the state a stopped run saved.
    continuation = continuation_of(case)
    if continuation is not None:
        _build_continuation(
            case,
            script,
            conventions,
            *continuation,
            threshold=unsteady_export_threshold(case, conventions, version=script.version),
            build=lambda full, scratch: _build_unsteady(full, scratch, conventions),
        )
        return
    _refuse_rotor_keys_on_a_rotorless_run(case)
    _refuse_wake_termination_without_a_rotor(case)
    threshold = unsteady_export_threshold(case, conventions, version=script.version)
    _refuse_unregistered_keys(case, "unsteady")
    _require_the_averaging_window(case, "unsteady")
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
    rotor_frame = _rotor_frame(case, script)
    rotor_frames = _flat_rotor_frames(case, rotor_frame)
    frames: dict[str, int | None | Mapping[str, int]] = {"MRP": frame, **rotor_frames}
    setup_frames = _setup_frames(case, script)
    frames.update(setup_frames)
    moved = {"MRP": frame, **rotor_frames, **setup_frames}
    frames.update(_translations(case, script, moved))
    frames.update(_rotations(case, script, moved))
    _actuator_disc(case, script, frames, disc)
    _pproc_plots(case, script, frames)
    _pproc_probes(case, script, frames, unsteady=True, analysis=False)
    _significant_digits(case, script)
    _free_stream(case, script, frames, custom)
    _fluid(case, script)
    _acoustic_setup(case, script)
    stepping = unsteady_time_stepping(case)
    helpers.unsteady_solver(
        script,
        time_iterations=stepping.time_iterations,
        delta_time=stepping.delta_time_s,
    )
    # The wake termination in STEPS is the one this run type can state
    # (PFS-2030.03.04); the revolutions form was refused above.
    _settings(case, script, wake_termination_time_steps=case.solver.wake_termination_steps)
    register_unsteady_actions(script, threshold, walltime=row_walltime_s(case) is not None)
    _script_tail(conventions, case, script, frame, unsteady=True, frames=frames)
