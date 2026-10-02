"""The script skeleton every builder shares: initialization, solve and tail.

:func:`_script_init` emits what every run does before it solves (the
initialization, the analysis, the sections, the FSI wiring),
:func:`_script_solve_and_export` the solve and the exports, and
:func:`_script_tail` the closing lines. A builder composes its run type
from these.
"""

from __future__ import annotations

import sys
from collections.abc import (
    Callable,
)

import pyflightstream.cases._setup_link as _setup_link
from pyflightstream.cases import (
    CampaignConfigError,
    FsiConfig,
    SimCase,
)
from pyflightstream.cases import (
    acoustics as _acoustics,
)
from pyflightstream.cases._setup_link import (
    LOADS_SELECTION_KEYS,
)
from pyflightstream.cases._unsteady_actions import (
    action_interpreter as _action_interpreter,
)
from pyflightstream.script import (
    Script,
    helpers,
)

from ._clock import (
    _rotor_clock,
)
from ._conventions import (
    WorkflowConventions,
    select_workflow,
)
from ._exports import (
    _export_block,
    _export_surface_vtk,
    _export_updates,
    surface_time_averaging,
)
from ._freestream import (
    _finish_custom_field_coverage,
    wake_end_plane,
)
from ._geometry import (
    _wake_termination_after_initialization,
    accepted_symmetry,
)
from ._motion import (
    _the_rotors_the_row_turns,
)
from ._pproc import (
    _pproc_sections,
)
from ._probes import (
    _pproc_probes,
)
from ._rows import (
    _from_metres,
    _qsteady_speed,
    _required_int,
    _the_copies_the_sector_stands_for,
    _the_isolated_rotor,
    _the_rotor_a_flat_row_turns,
    _variable,
    qsteady_case_kind,
    rotor_speed,
)
from ._solver_settings import (
    _analysis,
    _raw_commands,
)
from ._vocabulary import (
    PERIODIC_COPIES_VARIABLE,
    QSTEADY_ROTOR,
    SYMMETRY_VARIABLE,
    Frames,
)


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
        wake_termination_x=wake_end_plane(case, script),
    )


def _script_tail(
    conventions: WorkflowConventions,
    case: SimCase,
    script: Script,
    frame: int | None,
    *,
    unsteady: bool,
    frames: Frames | None = None,
    reopens_a_saved_state: bool = False,
) -> None:
    """Emit the four phases every run type ends with, each preceded by its raw commands.

    Init, exec, analysis and export, in the order the four builders
    always emitted them; written once so the raw commands of a setup
    (PFS-2033.01) meet each phase at one seam rather than at four copies
    of it.
    """
    _script_init(
        case,
        script,
        frame,
        frames=frames,
        reopens_a_saved_state=reopens_a_saved_state,
        conventions=conventions,
    )
    if case.fsi is not None and not unsteady:
        # FSI-G: A STEADY COUPLED SCRIPT ENDS AT THE ANALYSIS. It returns at once
        # in a script, so a line after it would run before it iterates (an
        # export of the rigid surface) or end it (CLOSE_FLIGHTSTREAM). The
        # exports are in the aeroelastic post-processing script and the run
        # stops the process once the solver prints that the analysis ended.
        from ..fsi_workspace import (
            emit_steady_aeroelastic_analysis,
            refuse_lines_after_steady_analysis,
        )

        emit_steady_aeroelastic_analysis(script)
        refuse_lines_after_steady_analysis(script.render())
        _finish_custom_field_coverage(case, script)
        return
    _script_solve_and_export(conventions, case, script, unsteady=unsteady, frames=frames)
    script.emit("CLOSE_FLIGHTSTREAM")
    _finish_custom_field_coverage(case, script)


def _script_init(
    case: SimCase,
    script: Script,
    frame: int | None,
    *,
    frames: Frames | None,
    reopens_a_saved_state: bool = False,
    conventions: WorkflowConventions | None = None,
    sections: bool = True,
) -> None:
    """Emit the init phase, which happens ONCE however many points follow.

    Split out of :func:`_script_tail` at 0.17.0 so a warm steady sweep can
    emit it once and then loop the solve. Nothing moved: a single-point
    build calls this and :func:`_script_solve_and_export` in the order the
    one function used, and renders the same bytes.

    It ENDS WITH THE LOADS FRAME AND THE MOMENTS MODEL since 0.27.0 (B05,
    RPT-064), which :func:`_script_solve_and_export` emitted after
    `START_SOLVER` until then; :func:`_analysis` says why the order
    decides what an unsteady row's step exports state. A steady sweep, warm
    or cold, states them here for its first point and again before each
    later point's `START_SOLVER` (:func:`build_steady_sweep`).

    FSI is wired here, after the section distributions it reads: the fixed
    wing's route on ``steady`` and ``unsteady`` (FSI-G), whose steady
    exports are the row's export block run in the aeroelastic
    post-processing script (``conventions`` names them), and the rotor's.

    ``sections`` False leaves the section distributions to the caller: a
    clocked quasi-steady wheel creates them at each clocking, in the pose that
    clocking holds (0.31.0, :func:`_build_qsteady_rotor`).
    """
    if case.fsi is not None:
        from ..fsi_workspace import validate_workspace_fsi

        validate_workspace_fsi(
            case,
            script,
            workflow=select_workflow(case),
            continuation=reopens_a_saved_state,
        )
    if frames is not None:
        # G12: THE FRAMES THIS RUN CREATED, kept on the script by name, so the
        # additional post can cite them in the saved simulation without
        # creating them again. Nothing is emitted here.
        script.frames_by_name = dict(frames)
    _raw_commands(case, script, "init")
    # G25 of 0.28.0: THE PACKAGE AVERAGES THE SURFACE, and nothing is emitted for
    # it here. SOLVER_TIME_AVERAGING hangs 26.124 (C01) and is never emitted; the
    # window's steps are exported one by one (unsteady_export_threshold) and the
    # post averages them.
    script.surface_average_window = surface_time_averaging(case)
    # THE FILE ROUTE'S WAKE TERMINATION, BETWEEN TWO INITIALISATIONS (G02, T07).
    # After a file import the detection marks nothing until the solver has
    # initialised, and the solver uses what it marked only once it initialises
    # again. The first is the final one's settings exactly, since the second
    # clears it; nothing else moves.
    detection = _wake_termination_after_initialization(case, script)
    if detection:
        _initialize(case, script)
        for command, arguments in detection:
            script.emit_after_initialization(command, *arguments)
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
        if sections:
            _pproc_sections(case, script, frames)
    elif reopens_a_saved_state:
        # A CONTINUATION EMITS NO DISTRIBUTION AND IS NOT REFUSED FOR IT
        # (0.24.0). It builds no frames because the saved simulation it reopens
        # carries them, and carries the distributions the stopped run created
        # with them; creating them again would add a second set beside the
        # first. The refusal below is for a builder that FORGOT its frames, and
        # it fired here on a builder that has none by design, so a row the wall
        # clock stopped could not be continued once its artifact declared
        # sections. That the reopened state still exports its sections is the
        # premise, and it is a solver behaviour a licensed run confirms.
        pass
    elif case.pproc is not None and case.pproc.sections.distributions:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the pproc artifact {case.pproc_id!r} declares "
            f"{len(case.pproc.sections.distributions)} section distribution(s) and "
            "this run was built without the frames they are measured in, so not one "
            "of them would be emitted. That is a defect in the builder rather than "
            "in the artifact."
        )
    coupled_surfaces: list[dict[str, object]] = []
    workflow = select_workflow(case) if case.fsi is not None else None
    if case.fsi is not None and workflow in ("steady", "unsteady"):
        coupled_surfaces = _wire_the_fixed_wing(case, script, workflow, frames, conventions)
    elif case.fsi is not None and workflow == QSTEADY_ROTOR:
        coupled_surfaces = _wire_the_quasi_steady_sector(case, script, frames, conventions)
    elif case.fsi is not None:
        from ..fsi_workspace import wire_workspace_fsi

        turning, lost = _the_rotors_the_row_turns(case)
        if lost or len(turning) > 1:
            raise CampaignConfigError("FSI requires one uniquely resolved moving rotor.")
        if turning:
            alias, _view, speed = turning[0]
            rotor = case.rotors[alias]
        else:
            flat_rotor = _the_rotor_a_flat_row_turns(case)
            if flat_rotor is None:
                raise CampaignConfigError("FSI requires one uniquely resolved rotor.")
            rotor = flat_rotor
            speed = rotor_speed(case)
        if frames is None:
            raise CampaignConfigError("FSI requires the initial blade/frame mapping.")
        wire_workspace_fsi(
            case,
            script,
            rotor=rotor,
            rpm=speed.rpm,
            delta_time_s=_rotor_clock(case).delta_time_s,
            frames=frames,
            interpreter=_action_interpreter(sys.executable),
        )
    # THE LOADS FRAME AND THE MOMENTS MODEL, LAST IN THE INIT GROUP (B05). After
    # the initialisation and the sections, which is run A of RPT-064, and before
    # the raw exec commands, which open the exec phase and would leave no init
    # position behind them.
    _analysis(case, script, frame)
    # FSI-G: the Tecplot surfaces a steady coupled run writes from its VTK are
    # exported by the post-processing script, which places no frame; the frame
    # they are in is this script's loads frame, placed just above.
    for surface in coupled_surfaces:
        script.surface_translations.append({**surface, "frame": script.loads_frame_record()})


def _wire_the_fixed_wing(
    case: SimCase,
    script: Script,
    workflow: str,
    frames: Frames | None,
    conventions: WorkflowConventions | None,
) -> list[dict[str, object]]:
    """Wire the fixed wing's coupling (FSI-G of 0.30.0), returning its steady Tecplot surfaces.

    Steady: the row's whole export block is the post-processing script's,
    after the loads the structural program reads, because nothing may follow
    ``EXECUTE_AEROELASTIC_ANALYSIS``; what the steady script cannot place
    there is refused first (:func:`_refuse_what_a_steady_coupled_run_cannot_export`).
    Unsteady: the post-processing script exports the deformed surface after
    every call, and the row's exports stay at the end of the march.
    """
    from ..fsi_workspace import DEFORMED_SURFACE_FILE, wire_fixed_wing_fsi

    if frames is None:
        raise CampaignConfigError("FSI requires the initial wing/frame mapping.")
    exports: Callable[[Script], None]
    updates: Callable[[Script], None] | None = None
    if workflow == "steady":
        _refuse_what_a_steady_coupled_run_cannot_export(case)
        exports_of = conventions or WorkflowConventions.for_case(case)
        exports, updates = _coupled_export_block(exports_of, case)
    else:

        def exports(post: Script) -> None:
            _export_surface_vtk(post, case, DEFORMED_SURFACE_FILE)

    return wire_fixed_wing_fsi(
        case,
        script,
        workflow=workflow,
        interpreter=_action_interpreter(sys.executable),
        exports=exports,
        updates=updates,
    )


def effective_fsi_config(case: SimCase) -> FsiConfig | None:
    """Return the structural configuration a point's run stages as its ``config.json``.

    The row's FSI input as resolved, except on a ``qsteady_rotor`` sector,
    whose structure turns at the speed the row turns the free stream: there
    ``omega_rad_per_s`` is the row's
    (:func:`pyflightstream.cases.fsi_workspace.quasi_steady_fsi_config`), so the
    structural solve applies the centrifugal loads at that speed. The
    builder and the run read this one function, so the nodes the script
    imports and the configuration the structural program loads describe one
    structure.

    Parameters
    ----------
    case : SimCase
        The point's case; its FSI input and run type are read.

    Returns
    -------
    FsiConfig or None
        None for a row with no FSI.
    """
    if case.fsi is None:
        return None
    if select_workflow(case) != QSTEADY_ROTOR or qsteady_case_kind(case) != "sector":
        return case.fsi
    from ..fsi_workspace import quasi_steady_fsi_config

    rotor = _the_isolated_rotor(case)
    return quasi_steady_fsi_config(case, rpm=_qsteady_speed(case, rotor).rpm, quiet=True)


def _wire_the_quasi_steady_sector(
    case: SimCase,
    script: Script,
    frames: Frames | None,
    conventions: WorkflowConventions | None,
) -> list[dict[str, object]]:
    """Wire a quasi-steady sector's coupling (0.30.0), returning its steady Tecplot surfaces.

    The structure is blade one turning at the row's speed
    (:func:`pyflightstream.cases.fsi_workspace.quasi_steady_fsi_config`); the
    route is steady, so the row's whole export block is the post-processing
    script's, after the loads the structural program reads, and what a
    steady coupled script cannot place there is refused first
    (:func:`_refuse_what_a_steady_coupled_run_cannot_export`).
    """
    from ..fsi_workspace import quasi_steady_fsi_config, wire_quasi_steady_sector_fsi

    if frames is None:
        raise CampaignConfigError("FSI requires the initial blade/frame mapping.")
    rotor = _the_isolated_rotor(case)
    config = quasi_steady_fsi_config(case, rpm=_qsteady_speed(case, rotor).rpm)
    _refuse_what_a_steady_coupled_run_cannot_export(case)
    exports_of = conventions or WorkflowConventions.for_case(case)
    exports, updates = _coupled_export_block(exports_of, case)
    return wire_quasi_steady_sector_fsi(
        case,
        script,
        config=config,
        rotor=rotor,
        interpreter=_action_interpreter(sys.executable),
        exports=exports,
        updates=updates,
    )


def _coupled_export_block(
    conventions: WorkflowConventions, case: SimCase
) -> tuple[Callable[[Script], None], Callable[[Script], None]]:
    """Return a steady coupled row's export block as the post-processing script takes it.

    Two parts, because the post-processing script updates the sections and
    computes their loads itself, once, before the loads the structural
    program reads (:func:`pyflightstream.cases.fsi_workspace.aeroelastic_post`):
    the updates the row's exports read beyond those two, which it emits
    before its first export, and the row's exports with no update of their
    own. The whole block in one piece updated the sections a second time
    after that first export, an analysis command in the export phase, so a
    coupled row with the default exports did not build (the L1 runs of
    0.30.0, both coupled routes).
    """

    def updates(post: Script) -> None:
        _export_updates(conventions, case, post, unsteady=False, sections_updated=True)

    def exports(post: Script) -> None:
        _export_block(conventions, case, post, unsteady=False, updated=True)

    return exports, updates


def _refuse_what_a_steady_coupled_run_cannot_export(case: SimCase) -> None:
    """Refuse what a steady coupled row would ask of a solve its script never starts (FSI-G).

    A steady coupled script ends at ``EXECUTE_AEROELASTIC_ANALYSIS`` and
    exports from the aeroelastic post-processing script, which the solver
    runs after every coupling iteration. The probe points, the pproc's volume
    section and the loads selections are emitted after ``START_SOLVER`` on a
    steady row, which this script never reaches, and creating them in a
    script the solver runs once per iteration would create them again on
    every pass; so they are refused here, named, rather than exported empty.
    """
    pproc = case.pproc
    stated = [
        key
        for key in (*LOADS_SELECTION_KEYS, "clear_vorticity_drag_boundaries")
        if getattr(case.solver, key) not in (None, False)
    ]
    if pproc is not None and pproc.probes:
        stated.append("the pproc's [[probes]]")
    if pproc is not None and pproc.volume_section is not None:
        stated.append("the pproc's [volume_section]")
    if stated:
        raise CampaignConfigError(
            f"case {case.sim_id!r} couples a fixed wing on a steady row (FSI-G), whose script "
            "ends at EXECUTE_AEROELASTIC_ANALYSIS and exports from the aeroelastic "
            f"post-processing script, and it states {', '.join(stated)}. Those are emitted "
            "after START_SOLVER on a steady row, which this script never reaches, and the "
            "post-processing script runs once per coupling iteration; this release does not "
            "wire them on the steady coupled route. Remove them from the row's preset or pproc."
        )


def _acoustic_setup(case: SimCase, script: Script) -> None:
    """Emit the row's acoustic setup before the clock (0.32.0, E2; cases.acoustics)."""
    _acoustics.emit_acoustic_setup(
        case, script, from_metres=lambda what: _from_metres(case, script, what)
    )


def _script_solve_and_export(
    conventions: WorkflowConventions,
    case: SimCase,
    script: Script,
    *,
    unsteady: bool,
    frames: Frames | None = None,
) -> None:
    """Emit the exec, analysis and export phases, which happen PER POINT.

    A warm steady sweep calls this once per point of the sweep, against a
    solver that was initialised once and is never cleared between them.
    That is the predecessor's steady recipe exactly, and it is why warm
    start is a sweep model rather than a flag.
    """
    _raw_commands(case, script, "exec")
    helpers.start_solver(script)
    if not unsteady:
        _setup_link.loads_selections(case, script)
        if case.solver.clear_vorticity_drag_boundaries:
            script.emit("DELETE_VORTICITY_DRAG_BOUNDARIES")
    _raw_commands(case, script, "analysis")
    # FR-81: a STEADY row creates the probe points it exports. `NEW_PROBE_LINE`
    # is an ANALYSIS command, so this is the only position the phase order
    # allows, and it is where the reference scripts already carry `UPDATE_PROBE_POINTS`
    # and `EXPORT_PROBE_POINTS`. An unsteady row placed its vertices through the
    # fluid plots long before this point and needs nothing here.
    if frames is not None:
        _pproc_probes(case, script, frames, unsteady=unsteady, analysis=True)
    # 0.32.0 (E2): the acoustic signals, computed from the march and exported.
    _acoustics.emit_acoustic_signals(
        case,
        script,
        unsteady=unsteady,
        frames=frames,
        from_metres=lambda what: _from_metres(case, script, what),
    )
    _raw_commands(case, script, "export")
    _export_block(conventions, case, script, unsteady=unsteady)
