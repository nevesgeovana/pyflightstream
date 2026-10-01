"""The solver settings of a row: the preset, the analysis, flags and raw commands.

:func:`_settings` emits the solver settings the row and its input library
resolve to; :func:`_analysis` the loads analysis; the custom flags and the
raw commands a row states are emitted at the phase they name.
"""

from __future__ import annotations

import math

import pyflightstream.cases._setup_link as _setup_link
from pyflightstream._atmosphere import (
    ISA,
)
from pyflightstream._errors import (
    PyflightstreamError,
    PyflightstreamWarning,
    warn,
)
from pyflightstream.cases import (
    FLAG_PHASES,
    RAW_PHASES,
    CampaignConfigError,
    CustomFlag,
    SimCase,
)
from pyflightstream.cases._setup_link import (
    LOADS_SELECTION_KEYS,
)
from pyflightstream.commands import (
    Phase,
)
from pyflightstream.script import (
    Script,
    helpers,
)

from ._geometry import (
    _setup_ports,
)
from ._rows import (
    _angle,
    _from_metres,
    _states_a_rotor_speed,
    _variable,
    _velocity,
    row_ncpus,
    row_symmetry_loads,
)
from ._vocabulary import (
    _UNSTEADY_RECIPES,
    QSTEADY_ROTOR,
    SYMMETRY_VARIABLE,
)


def _refuse_the_loads_selections_on_a_march(case: SimCase) -> None:
    """Refuse a loads selection on a row of an unsteady run type (G09).

    Emitted after the solve starts, it would reach the final export and not the
    per-step exports and plots an unsteady product is read from, which is the
    shape RPT-064 measured for the loads frame; moving it before the solve is not
    measured. In 0.27.0 they are a steady row's.
    """
    stated = [
        key
        for key in (*LOADS_SELECTION_KEYS, "clear_vorticity_drag_boundaries")
        if getattr(case.solver, key) is not None
    ]
    if not stated:
        return
    raise CampaignConfigError(
        f"case {case.sim_id!r} names the run type {case.recipe!r} and its setup states "
        f"{', '.join(stated)}. The loads selections are applied after the solve starts, "
        "and on a march that reaches only the final export, not the step exports and "
        "plots the unsteady products are read from (RPT-064 measured this for the loads "
        "frame); in 0.27.0 they are a steady row's. Drop the key from the preset this "
        "row names, or give the row a preset of its own."
    )


def _analysis(case: SimCase, script: Script, frame: int | None) -> None:
    """Point the analysis at the MRP frame and state the moments model, BEFORE the solve.

    The two init-phase lines of B05 (RPT-064), and FR-317 and FR-318 with them:
    :func:`~pyflightstream.cases._setup_link.analysis_frame_and_moments` says why
    the order decides what the step exports state, and why a row turning a rotor
    ties its moments model to its vorticity drag list. Every run type emits them
    here, from :func:`_script_init`, once the solver is initialised and the
    sections are declared.
    """
    rotor = case.recipe in ("unsteady_rotor", QSTEADY_ROTOR) or _states_a_rotor_speed(case)
    _setup_link.analysis_frame_and_moments(case, script, frame, rotor=rotor)


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


def _resolved_native_mach(case: SimCase, script: Script) -> float | None:
    """Select Mach only when it represents the same resolved physical state."""
    if case.solver.freestream_input == "velocity":
        return None
    prefix = "freestream_input='mach'"
    fluid = case.fluid
    mach = case.mach
    if fluid is None or mach is None:
        raise CampaignConfigError(
            f"{prefix} requires the resolved flight condition's Mach and fluid properties; "
            "use freestream_input='velocity' when they are unavailable"
        )
    sound = fluid.sonic_velocity_m_per_s
    if not math.isfinite(sound) or sound <= 0:
        raise CampaignConfigError(f"{prefix} requires a positive finite sound speed")
    if helpers.fluid_fifth_property(script) == "specific_heat_ratio":
        state = (fluid.heat_capacity_ratio, fluid.pressure_pa, fluid.density_kg_m3)
        if any(not math.isfinite(value) or value <= 0 for value in state):
            raise CampaignConfigError(f"{prefix} requires positive finite gas properties")
        temperature = fluid.temperature_k
        if not math.isfinite(temperature) or temperature <= 0:
            raise CampaignConfigError(f"{prefix} requires a positive finite temperature")
        native_sound = math.sqrt(state[0] * ISA.gas_constant_j_per_kg_k * temperature)
        pressure_sound = math.sqrt(state[0] * state[1] / state[2])
        if not math.isclose(sound, native_sound, rel_tol=1e-7, abs_tol=1e-9):
            raise CampaignConfigError(
                f"{prefix}: resolved sound speed disagrees with emitted temperature and gamma; "
                "use freestream_input='velocity' for independently pinned fluid properties"
            )
        if not math.isclose(sound, pressure_sound, rel_tol=1e-7, abs_tol=1e-9):
            raise CampaignConfigError(
                f"{prefix}: resolved sound speed disagrees with gamma * pressure / density; "
                "use freestream_input='velocity' to preserve an independently pinned state"
            )
    override = case.solver.sonic_velocity_m_per_s
    if override is not None and not math.isclose(override, sound, rel_tol=1e-7, abs_tol=1e-9):
        raise CampaignConfigError(f"{prefix}: sonic_velocity_m_per_s changes the sound speed")
    velocity = _velocity(case)
    values = (mach, velocity, fluid.velocity_m_per_s)
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise CampaignConfigError(f"{prefix} requires finite nonnegative Mach and velocity")
    if not (
        math.isclose(velocity, fluid.velocity_m_per_s, rel_tol=1e-7, abs_tol=1e-9)
        and math.isclose(velocity, mach * sound, rel_tol=1e-7, abs_tol=1e-9)
    ):
        raise CampaignConfigError(
            f"{prefix}: resolved velocity, Mach and fluid state are inconsistent; "
            "the native route cannot change the requested physical condition"
        )
    return mach


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
    _setup_ports(case, script)
    reference = case.reference
    native_length = _from_metres(case, script, "runtime velocity and SI reference dimensions")
    reference_scale = (
        native_length if reference is not None and reference.normalization_units == "SI" else 1.0
    )
    solver = case.solver
    native_mach = _resolved_native_mach(case, script)
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
    # BC commands retain their setup phase; late emission after solver_settings
    # would cross backwards from init and be refused by Script.
    for index, edge_type in (solver.trailing_edge_types or {}).items():
        script.emit("SET_TRAILING_EDGE_TYPE", index, edge_type)
    for index in solver.disabled_wake_trailing_edges or ():
        script.emit("DISABLE_WAKE_NODES_ON_TRAILING_EDGE", index)
    if solver.leading_edge_wake_boundaries is not None:
        boundaries = solver.leading_edge_wake_boundaries
        script.emit("DETECT_LEADING_EDGES_WAKES_BY_SURFACE", len(boundaries), boundaries)
    if solver.mark_wake_termination_nodes:
        script.emit("MARK_WAKE_TERMINATION_NODES")
    if solver.sonic_velocity_m_per_s is not None:
        script.emit("SONIC_VELOCITY", solver.sonic_velocity_m_per_s)
    for inlet in solver.delete_inlets or ():
        script.emit("DELETE_INLET", inlet)
    for outlet in solver.delete_outlets or ():
        script.emit("DELETE_OUTLET", outlet)
    for trip in solver.delete_transition_trips or ():
        script.emit("DELETE_TRANSITION_TRIP", trip)
    physics = (solver.physics_auto_trailing_edges, solver.physics_auto_wake_nodes)
    if any(value is not None for value in physics):
        if any(value is None for value in physics):
            raise CampaignConfigError(
                "physics_auto_trailing_edges and physics_auto_wake_nodes must be stated together"
            )
        script.emit("PHYSICS", *physics)
    helpers.solver_settings(
        script,
        aoa=_angle(case, "alpha"),
        sideslip=_angle(case, "beta"),
        velocity=_velocity(case) * native_length if native_mach is None else None,
        mach=native_mach,
        ref_velocity=(
            None
            if solver.reference_mach is not None or solver.disable_reference_velocity
            else (
                solver.reference_velocity_m_per_s
                if solver.reference_velocity_m_per_s is not None
                else _velocity(case)
            )
            * native_length
        ),
        ref_mach=solver.reference_mach,
        disable_ref_velocity=bool(solver.disable_reference_velocity),
        vorticity_drag_boundaries=_setup_link.vorticity_indices(case, script),
        # THE CALL SITE IS WHAT DELIVERS THIS, not the field and not the helper
        # keyword. Both of those existed already and a preset still could not ask
        # for an axial separation list, because this hand-written argument list is
        # the only path from a setup to the script.
        axial_separation_boundaries=_setup_link.axial_separation_indices(case, script),
        iterations=solver.iterations,
        convergence=solver.convergence,
        max_threads=row_ncpus(case, solver.max_threads),
        ref_area=None if reference is None else reference.area * reference_scale**2,
        ref_length=None if reference is None else reference.length * reference_scale,
        forced_iterations=solver.forced_iterations,
        boundary_layer=solver.boundary_layer,
        viscous_coupling=solver.viscous_coupling,
        viscous_excluded=solver.viscous_excluded,
        surface_roughness=solver.surface_roughness,
        thin_boundaries=solver.thin_boundaries,
        bulk_separation=solver.bulk_separation,
        airfoil_separation=solver.airfoil_separation,
        axial_vortex_separation=solver.axial_vortex_separation,
        cylindrical_bulk_separation=solver.cylindrical_bulk_separation,
        stratford_bulk_separation=solver.stratford_bulk_separation,
        delete_separations=solver.delete_separations,
        valarezo_criterion=solver.valarezo_criterion,
        valarezo_separation_boundaries=solver.valarezo_separation_boundaries,
        crossflow_separation_boundaries=solver.crossflow_separation_boundaries,
        crossflow_separation_diameter=solver.crossflow_separation_diameter,
        crossflow_separation_mean_diameter=solver.crossflow_separation_mean_diameter,
        crossflow_separation_axisymmetric=solver.crossflow_separation_axisymmetric,
        solver_model=solver.legacy_solver_model,
        convergence_iterations=solver.convergence_iterations,
        minimum_cp=solver.minimum_cp,
        farfield_layers=solver.farfield_layers,
        mesh_induced_wake_velocity=solver.mesh_induced_wake_velocity,
        unsteady_pressure_and_kutta=solver.unsteady_pressure_and_kutta,
        wake_on_wake_induction=solver.wake_on_wake_induction,
        additional_wake_relaxation=solver.additional_wake_relaxation,
        reynolds_averaged_drag=solver.reynolds_averaged_drag,
        solver_stabilization=solver.solver_stabilization,
        laminar_separation=solver.laminar_separation,
        kutta_joukowski_lift=solver.kutta_joukowski_lift,
        aeroelastic_rbf_type=solver.aeroelastic_rbf_type,
        print_rotor_induced_velocities=solver.print_rotor_induced_velocities,
        adaptive_field_grid_refinement=solver.adaptive_field_grid_refinement,
        rotor_induced_velocity_blending=solver.rotor_induced_velocity_blending,
        wake_numerical_relaxation=solver.wake_numerical_relaxation,
        wake_relaxation=solver.wake_relaxation,
        wake_decay_constant=solver.wake_decay_constant_per_m,
        wake_streamwise_agglomeration=solver.wake_streamwise_agglomeration,
        jet_wake_decay_normalized_length=solver.jet_wake_decay_normalized_length,
        jet_wake_filaments_grid_induction=solver.jet_wake_filaments_grid_induction,
        adverse_gradient_boundary_layer=solver.adverse_gradient_boundary_layer,
        vortex_ring_normalization=solver.vortex_ring_normalization,
        wake_termination_time_steps=wake_termination_time_steps,
    )
    if solver.remove_initialization:
        script.emit("REMOVE_INITIALIZATION")
    if solver.proximal_boundaries is not None:
        selected = solver.proximal_boundaries
        if selected == "all":
            count = script.entities.count("boundaries")
            if not count:
                raise CampaignConfigError("proximal_boundaries='all' requires a known inventory")
            indices = list(range(1, count + 1))
        else:
            indices = [
                script.resolve_boundary(value, context="proximal_boundaries") for value in selected
            ]
        script.emit("SOLVER_PROXIMAL_BOUNDARIES", len(indices), indices)
    _lift_and_coupling(case, script)
    # SYMMETRY LOADS AS STATED, the design decision of 2026-09-02 (PFS-2028.05): an
    # init-phase setting, emitted alone here as the helper asks; an absent
    # key emits nothing, so a preset written before this release is silent
    # exactly as it was.
    symmetry_loads = row_symmetry_loads(case, solver.symmetry_loads)
    if symmetry_loads is not None:
        helpers.analysis_setup(script, symmetry_loads=symmetry_loads)
    _setup_link.emit_setup_extras(case, script, marching=case.recipe in _UNSTEADY_RECIPES)


def _lift_and_coupling(case: SimCase, script: Script) -> None:
    """Emit the vorticity lift model and the viscous coupling step a setup states (G14).

    Both are init-phase commands, so they precede ``INITIALIZE_SOLVER`` and every
    export of a march sees them. Each emission is validated by the command
    database for the script's build, which is what refuses a build that does not
    carry the command, naming it: 26.124 answers both names as unrecognized
    (RPT-068), and the coupling step is documented by 25.000 to 26.000 alone. A
    setup that states neither emits nothing.
    """
    solver = case.solver
    if solver.vorticity_lift_model is not None:
        if solver.vorticity_lift_model and solver.kutta_joukowski_lift:
            warn(
                f"case {case.sim_id!r}: its setup states vorticity_lift_model = true and "
                "kutta_joukowski_lift = true, two routes to the lift, and no edition of "
                "the manual says what the solver does with both. The run goes ahead with "
                "both lines; state one of them false to know which lift the loads carry.",
                PyflightstreamWarning,
                stacklevel=2,
            )
        script.emit(
            "SET_VORTICITY_LIFT_MODEL", "ENABLE" if solver.vorticity_lift_model else "DISABLE"
        )
    if solver.unsteady_viscous_coupling_iteration is not None:
        script.emit(
            "SET_UNSTEADY_VISCOUS_COUPLING_ITERATION", solver.unsteady_viscous_coupling_iteration
        )


def _refuse_a_coupling_step_without_a_clock(case: SimCase) -> None:
    """Refuse the viscous coupling step on a steady row (G14): it has no time step."""
    step = case.solver.unsteady_viscous_coupling_iteration
    if step is None:
        return
    raise CampaignConfigError(
        f"case {case.sim_id!r} inherits unsteady_viscous_coupling_iteration = {step} from "
        "its solver preset and is a STEADY run, which has no time steps for the viscous "
        "coupling to begin at, so the setting would reach no line. Drop the key from the "
        "preset this row names, or give the row a preset of its own."
    )


# THE SEAMS A FLAG MAY REACH are ``FLAG_PHASES``, the three the builders open
# for a raw entry too, imported from :mod:`pyflightstream.cases`, their one
# home (AD-10). A command of a later phase is part of the RUN rather than of
# its setting up, and this package emits those itself.


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
