"""Curated helpers for the common FlightStream workflows (SAD Section 4.3).

Pipeline role: a small, curated set of thin typed functions sitting on
top of :class:`~pyflightstream.script.Script`. Each helper only
translates its typed arguments into ``emit()`` calls, so every line
still passes the database validation, phase ordering, and
cross-reference checks of the builder. Helpers own the conditional
argument combinations the manual documents in prose (which extras each
SET_FREESTREAM type takes, when INITIALIZE_SOLVER takes per-surface
lines or a PERIODIC copy count), because the database records grammar,
not conditionality.

One generated function per command was rejected in the SAD: it would
reproduce the shape of the AGPL package, create a huge surface, and
teach nothing. The curated workflows are: free stream and atmosphere,
actuator disc (SRC-003 pp.323-324), rotary motion (pp.332-333), solver
settings (pp.339-343), solver initialization (p.337), sweeps (p.406),
analysis and export selection (pp.350-354), and probe management
(pp.362-363).
"""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from typing import Literal

from pyflightstream.script import CommandArgumentError, Script


def _toggle(value: bool) -> str:
    return "ENABLE" if value else "DISABLE"


def free_stream(
    script: Script,
    kind: str = "CONSTANT",
    *,
    frame: int | None = None,
    axis: str | None = None,
    rpm: float | None = None,
    profile: str | None = None,
    filetype: str | None = None,
) -> None:
    """Set the free-stream velocity definition (SRC-003 p.322).

    Parameters
    ----------
    script : Script
        Script under construction.
    kind : str
        ``CONSTANT`` (uniform free stream, the magnitude comes later
        from the solver settings), ``ROTATION`` (rotating frame free
        stream for hover and propeller analyses), or ``CUSTOM``
        (velocity profile imported from a file).
    frame : int, optional
        ROTATION only: local coordinate system carrying the rotation
        axis; it must exist earlier in the script.
    axis : str, optional
        ROTATION only: rotation axis of ``frame``, ``X``, ``Y``, or
        ``Z``.
    rpm : float, optional
        ROTATION only: angular velocity in rev/min.
    profile : str, optional
        CUSTOM only: path of the velocity profile file.
    filetype : str, optional
        CUSTOM only: ``STRUCTURED`` or ``UNSTRUCTURED`` profile file.
    """
    upper = kind.upper()
    rotation_given = [frame is not None, axis is not None, rpm is not None]
    custom_given = [profile is not None, filetype is not None]
    if upper == "ROTATION":
        if not all(rotation_given) or any(custom_given):
            raise CommandArgumentError(
                "SET_FREESTREAM ROTATION takes exactly frame, axis, and rpm: the rotating "
                "free stream needs the axis frame, the axis, and the angular velocity "
                "(SRC-003 p.322)"
            )
        script.emit("SET_FREESTREAM", upper, frame=frame, axis=axis, angular_velocity=rpm)
    elif upper == "CUSTOM":
        if not all(custom_given) or any(rotation_given):
            raise CommandArgumentError(
                "SET_FREESTREAM CUSTOM takes exactly filetype and profile: the imported "
                "velocity profile needs its file structure and path (SRC-003 p.322)"
            )
        script.emit("SET_FREESTREAM", upper, filetype=filetype, filename=profile)
    else:
        if any(rotation_given) or any(custom_given):
            raise CommandArgumentError(
                "SET_FREESTREAM CONSTANT takes no further input; the free-stream magnitude "
                "is a solver setting (SOLVER_SET_VELOCITY, SRC-003 p.339)"
            )
        script.emit("SET_FREESTREAM", upper)


def atmosphere(
    script: Script,
    *,
    altitude: float | None = None,
    altitude_units: str = "METERS",
    density: float | None = None,
    pressure: float | None = None,
    temperature: float | None = None,
    viscosity: float | None = None,
    specific_heat_ratio: float | None = None,
) -> None:
    """Set the working fluid state (SRC-003 p.328).

    Either from a standard-atmosphere altitude (AIR_ALTITUDE) or from
    the five explicit fluid properties (FLUID_PROPERTIES); the two
    paths are mutually exclusive. Sonic velocity is derived from
    temperature and specific heat ratio and is no longer an input.

    Parameters
    ----------
    script : Script
        Script under construction.
    altitude : float, optional
        Standard-atmosphere altitude, in ``altitude_units``.
    altitude_units : str
        ``METERS`` or ``FEET``.
    density : float, optional
        Fluid density in kg/m^3.
    pressure : float, optional
        Static pressure in Pa.
    temperature : float, optional
        Static temperature in K.
    viscosity : float, optional
        Dynamic viscosity in Pa s.
    specific_heat_ratio : float, optional
        Ratio of specific heats (1.4 for air).
    """
    properties = (density, pressure, temperature, viscosity, specific_heat_ratio)
    if altitude is not None:
        if any(value is not None for value in properties):
            raise CommandArgumentError(
                "atmosphere takes either an altitude or the five explicit fluid "
                "properties, not both: AIR_ALTITUDE already sets the whole standard "
                "atmosphere state (SRC-003 p.328)"
            )
        script.emit("AIR_ALTITUDE", altitude, altitude_units)
        return
    if any(value is None for value in properties):
        raise CommandArgumentError(
            "atmosphere without an altitude needs all five fluid properties (density, "
            "pressure, temperature, viscosity, specific_heat_ratio), because "
            "FLUID_PROPERTIES sets the complete fluid state (SRC-003 p.328)"
        )
    script.emit(
        "FLUID_PROPERTIES",
        density=density,
        pressure=pressure,
        temperature=temperature,
        viscosity=viscosity,
        specific_heat_ratio=specific_heat_ratio,
    )


def actuator_disc(
    script: Script,
    name: str,
    *,
    frame: int,
    axis: str,
    offset: float,
    r_tip: float,
    r_hub: float,
    rpm: float,
    thrust: float | None = None,
    thrust_type: str = "NEWTONS",
    profile: str | None = None,
    profile_force_unit: str = "NEWTONS",
    n_blades: int | None = None,
    swirl: float | None = None,
    enable: bool = True,
) -> int:
    """Create and configure one propeller actuator disc (SRC-003 pp.323-324).

    The disc is the linearized propeller slipstream surrogate
    (SRC-003 pp.185-187). Exactly one thrust specification is taken:
    a net ``thrust`` (ELLIPTICAL profile) or a radial force
    distribution file ``profile`` (CUSTOM profile, which also needs
    ``n_blades``).

    Parameters
    ----------
    script : Script
        Script under construction.
    name : str
        Actuator name shown in the interface.
    frame : int
        Local coordinate system carrying the disc axis (index greater
        than 1); it must exist earlier in the script.
    axis : str
        Disc axis within ``frame``: ``X``, ``Y``, or ``Z``.
    offset : float
        Disc position along the axis, in simulation length units.
    r_tip, r_hub : float
        Tip and hub radii, in simulation length units.
    rpm : float
        Rotational speed in rev/min; the sign selects the rotation
        direction about the axis.
    thrust : float, optional
        Net thrust for the ELLIPTICAL model, in ``thrust_type`` units.
    thrust_type : str
        ``COEFFICIENT``, ``NEWTONS``, or ``POUNDS``. The manual
        recommends dimensional thrust because the coefficient
        convention must match the solver formulation (SRC-003 p.187).
    profile : str, optional
        Path of the radial thrust profile file for the CUSTOM model.
    profile_force_unit : str
        Force unit used inside the profile file: ``NEWTONS``,
        ``KILO-NEWTONS``, ``POUND-FORCE``, or ``KILOGRAM-FORCE``.
    n_blades : int, optional
        Blade count; required with ``profile``.
    swirl : float, optional
        Fraction between 0 and 1 of the swirl velocity kept
        downstream; below 1 mimics a de-swirling stator
        (SRC-003 p.186).
    enable : bool
        Emit ENABLE_ACTUATOR at the end.

    Returns
    -------
    int
        Index of the created actuator, for later citations.
    """
    if (thrust is None) == (profile is None):
        raise CommandArgumentError(
            "actuator_disc takes exactly one thrust specification: a net thrust "
            "(ELLIPTICAL model) or a radial profile file (CUSTOM model) "
            "(SRC-003 pp.185-187)"
        )
    if profile is not None and n_blades is None:
        raise CommandArgumentError(
            "actuator_disc with a profile file needs n_blades, because the imported "
            "radial distribution is per blade (SRC-003 pp.323-324)"
        )
    if swirl is not None and not 0.0 <= swirl <= 1.0:
        raise CommandArgumentError(
            f"actuator_disc swirl must lie between 0 and 1, got {swirl}: it is the "
            "fraction of the swirl velocity kept downstream (SRC-003 p.186)"
        )
    subtype = "ELLIPTICAL" if thrust is not None else "CUSTOM"
    script.emit("CREATE_NEW_ACTUATOR", "PROPELLER", subtype=subtype, name=name)
    index = script.num_actuators
    script.emit("SET_ACTUATOR_AXIS", index, frame, axis, offset)
    script.emit("SET_ACTUATOR_RADIUS", index, r_tip, r_hub)
    script.emit("SET_PROP_ACTUATOR_RPM", index, rpm)
    if thrust is not None:
        script.emit("SET_PROP_ACTUATOR_THRUST", index, thrust, thrust_type)
    else:
        script.emit("SET_PROP_ACTUATOR_PROFILE", index, profile_force_unit, n_blades, profile)
    if swirl is not None:
        script.emit("SET_PROP_ACTUATOR_SWIRL", index, swirl)
    if enable:
        script.emit("ENABLE_ACTUATOR", index)
    return index


def rotary_motion(
    script: Script,
    *,
    frame: int,
    axis: str,
    rpm: float,
    boundaries: Sequence[int] | Literal["all"] = "all",
    moving_frames: Sequence[int] | Literal["all"] | None = None,
    start_time: float | None = None,
    wake_stabilization_blades: int | None = None,
) -> int:
    """Create and configure one rotary motion (SRC-003 pp.332-333).

    Rotary motion is the blade-resolved alternative to the actuator
    disc surrogate (SRC-003 p.234); it requires the unsteady solver
    (see :func:`unsteady_solver`).

    Parameters
    ----------
    script : Script
        Script under construction.
    frame : int
        Local coordinate system of the rotation (index greater than
        1); it must exist earlier in the script.
    axis : str
        Rotor axis within ``frame``: ``X``, ``Y``, or ``Z``.
    rpm : float
        Rotor speed in rev/min.
    boundaries : sequence of int or ``"all"``
        Geometry boundaries assigned to the motion; ``"all"`` selects
        every boundary (-1 form).
    moving_frames : sequence of int, ``"all"``, or None
        Local frames attached to the motion; None attaches none.
    start_time : float, optional
        Motion start within the solver physical time, in s; a positive
        value converges a steady base flow before the motion begins.
    wake_stabilization_blades : int, optional
        Enables slipstream wake stabilization with this blade count.

    Returns
    -------
    int
        Identifier of the created motion, for later citations.
    """
    script.emit("CREATE_NEW_MOTION", "ROTARY")
    motion_id = script.num_motions
    if boundaries == "all":
        script.emit("SET_MOTION_BOUNDARIES", motion_id, -1)
    else:
        script.emit("SET_MOTION_BOUNDARIES", motion_id, len(boundaries), list(boundaries))
    if moving_frames == "all":
        script.emit("SET_MOTION_MOVING_FRAMES", motion_id, -1)
    elif moving_frames is not None:
        script.emit("SET_MOTION_MOVING_FRAMES", motion_id, len(moving_frames), list(moving_frames))
    script.emit("SET_MOTION_COORDINATE_SYSTEM", motion_id, frame)
    script.emit("SET_MOTION_ROTOR_AXIS", motion_id, axis)
    script.emit("SET_MOTION_ROTOR_RPM", motion_id, rpm)
    if start_time is not None:
        script.emit("SET_MOTION_START_TIME", motion_id, start_time)
    if wake_stabilization_blades is not None:
        script.emit(
            "SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION",
            motion_id,
            "ENABLE",
            wake_stabilization_blades,
        )
    return motion_id


def unsteady_solver(script: Script, *, time_iterations: int, delta_time: float) -> None:
    """Select unsteady physical time stepping (SRC-003 p.341).

    For rotary cases the manual recommends 8 to 12 degrees of blade
    rotation per time step and at least two full rotations
    (SRC-003 p.210).

    Parameters
    ----------
    script : Script
        Script under construction.
    time_iterations : int
        Number of physical time steps.
    delta_time : float
        Physical time step in s.
    """
    script.emit("SET_SOLVER_UNSTEADY", time_iterations, delta_time)


def solver_settings(
    script: Script,
    *,
    aoa: float | None = None,
    sideslip: float | None = None,
    velocity: float | None = None,
    mach: float | None = None,
    ref_velocity: float | None = None,
    ref_mach: float | None = None,
    ref_area: float | None = None,
    ref_length: float | None = None,
    iterations: int | None = None,
    convergence: float | None = None,
    forced_iterations: bool | None = None,
    max_threads: int | None = None,
    boundary_layer: str | None = None,
    viscous_coupling: bool | None = None,
    viscous_excluded: Sequence[int] | None = None,
) -> None:
    """Set the solver runtime settings that were given (SRC-003 pp.339-343).

    Only the provided settings are emitted, so the helper serves both
    the initial setup and the re-emission between campaign points.

    Parameters
    ----------
    script : Script
        Script under construction.
    aoa : float, optional
        Angle of attack in deg, magnitude below 90.
    sideslip : float, optional
        Side-slip angle in deg, magnitude below 90.
    velocity : float, optional
        Free-stream velocity magnitude in m/s.
    mach : float, optional
        Free-stream Mach number.
    ref_velocity : float, optional
        Reference velocity in m/s for coefficient normalization; for
        rotary or hover cases use the largest characteristic velocity,
        such as the rotor tip speed (SRC-003 p.201).
    ref_mach : float, optional
        Reference Mach number.
    ref_area : float, optional
        Reference area S_ref in simulation length units squared
        (Q*S_ref force normalization, SRC-003 p.223).
    ref_length : float, optional
        Reference length L_ref in simulation length units
        (Q*S_ref*L_ref moment normalization, SRC-003 p.223).
    iterations : int, optional
        Solver iteration count.
    convergence : float, optional
        Residual threshold declaring convergence (SRC-003 p.200).
    forced_iterations : bool, optional
        Run the full iteration count regardless of convergence.
    max_threads : int, optional
        Parallel core count.
    boundary_layer : str, optional
        ``LAMINAR``, ``TRANSITIONAL``, or ``TURBULENT``; the default
        transitional model is stated valid for chord Reynolds numbers
        between 500000 and 1500000 (SRC-003 p.203).
    viscous_coupling : bool, optional
        Couple the semi-empirical boundary layer model to the
        potential flow solution (attached-flow viscosity only,
        SRC-003 pp.207-208).
    viscous_excluded : sequence of int, optional
        Boundaries excluded from viscous coupling.
    """
    scalar_commands = (
        ("SOLVER_SET_AOA", aoa),
        ("SOLVER_SET_SIDESLIP", sideslip),
        ("SOLVER_SET_VELOCITY", velocity),
        ("SOLVER_SET_MACH_NUMBER", mach),
        ("SOLVER_SET_REF_VELOCITY", ref_velocity),
        ("SOLVER_SET_REF_MACH_NUMBER", ref_mach),
        ("SOLVER_SET_REF_AREA", ref_area),
        ("SOLVER_SET_REF_LENGTH", ref_length),
        ("SOLVER_SET_ITERATIONS", iterations),
        ("SOLVER_SET_CONVERGENCE", convergence),
        ("SET_MAX_PARALLEL_THREADS", max_threads),
    )
    for command, value in scalar_commands:
        if value is not None:
            script.emit(command, value)
    if forced_iterations is not None:
        script.emit("SOLVER_SET_FORCED_ITERATIONS", _toggle(forced_iterations))
    if boundary_layer is not None:
        script.emit("SET_BOUNDARY_LAYER_TYPE", boundary_layer)
    if viscous_coupling is not None:
        script.emit("SET_SOLVER_VISCOUS_COUPLING", _toggle(viscous_coupling))
    if viscous_excluded is not None:
        script.emit(
            "SET_VISCOUS_EXCLUDED_BOUNDARIES", len(viscous_excluded), list(viscous_excluded)
        )


def initialize_solver(
    script: Script,
    *,
    solver_model: str = "INCOMPRESSIBLE",
    surfaces: Sequence[tuple[int, bool]] | Literal["all"] = "all",
    wake_termination_x: float | str = "DEFAULT",
    symmetry: str = "NONE",
    periodic_copies: int | None = None,
    wall_collision_avoidance: bool | None = None,
) -> None:
    """Initialize the solver, covering the extended forms (SRC-003 p.337).

    Parameters
    ----------
    script : Script
        Script under construction.
    solver_model : str
        ``INCOMPRESSIBLE``, ``SUBSONIC_PRANDTL_GLAUERT``,
        ``TRANSONIC_FIELD_PANEL``, ``TANGENT_CONE``, or
        ``MODIFIED_NEWTONIAN``.
    surfaces : sequence of (int, bool) pairs or ``"all"``
        ``"all"`` initializes every boundary (-1 form); a sequence of
        ``(surface_index, quad_mesher)`` pairs initializes those
        surfaces with the quad mesher toggled per surface.
    wake_termination_x : float or str
        X location of wake termination in the reference frame, or
        ``DEFAULT`` for auto-computation.
    symmetry : str
        ``NONE``, ``MIRROR``, or ``PERIODIC``. Initializing MIRROR
        with a full (non-half) model diverges instantly
        (SRC-003 p.217).
    periodic_copies : int, optional
        Number of periodic copies; required with PERIODIC symmetry
        and forbidden otherwise.
    wall_collision_avoidance : bool, optional
        Applies to solver models 1 to 3.
    """
    if (symmetry.upper() == "PERIODIC") != (periodic_copies is not None):
        raise CommandArgumentError(
            "INITIALIZE_SOLVER: PERIODIC symmetry appends the number of copies, so "
            "periodic_copies is required with PERIODIC and forbidden otherwise "
            "(SRC-003 p.337)"
        )
    if periodic_copies is not None and periodic_copies < 1:
        raise CommandArgumentError(
            f"INITIALIZE_SOLVER: periodic_copies must be a positive count, got "
            f"{periodic_copies} (SRC-003 p.337)"
        )
    arguments: dict[str, object] = {
        "solver_model": solver_model,
        "wake_termination_x": str(wake_termination_x),
        "symmetry": symmetry,
    }
    if surfaces == "all":
        arguments["surfaces"] = -1
    else:
        arguments["surfaces"] = len(surfaces)
        arguments["surface_toggles"] = [
            f"{index},{_toggle(quad_mesher)}" for index, quad_mesher in surfaces
        ]
    if periodic_copies is not None:
        arguments["symmetry_copies"] = periodic_copies
    if wall_collision_avoidance is not None:
        arguments["wall_collision_avoidance"] = _toggle(wall_collision_avoidance)
    script.emit("INITIALIZE_SOLVER", **arguments)


def sweep(
    script: Script,
    *,
    aoa: Sequence[float] | None = None,
    beta: Sequence[float] | None = None,
    velocity_file: str | None = None,
    clear_solution: bool | None = None,
    ref_velocity_same: bool | None = None,
    post_run_script: str | None = None,
    start: bool = True,
    export_spreadsheet: str | None = None,
) -> None:
    """Configure and run a Sweeper Toolbox sweep (SRC-003 p.406).

    Parameters
    ----------
    script : Script
        Script under construction.
    aoa : sequence of float, optional
        Custom angle of attack values in deg.
    beta : sequence of float, optional
        Custom side-slip values in deg.
    velocity_file : str, optional
        Path of the custom velocity list file.
    clear_solution : bool, optional
        Clear the solution between sweep runs instead of reusing it.
    ref_velocity_same : bool, optional
        Keep the reference velocity equal to the free-stream velocity
        at every sweep point.
    post_run_script : str, optional
        Script executed after each sweep point, for example a surface
        section extraction script.
    start : bool
        Emit SWEEPER_START after the configuration.
    export_spreadsheet : str, optional
        Path of the sweep results spreadsheet export.
    """
    if aoa is None and beta is None and velocity_file is None:
        raise CommandArgumentError(
            "sweep needs at least one axis (aoa, beta, or velocity_file); a sweep "
            "without values has nothing to run (SRC-003 p.406)"
        )
    if aoa is not None:
        script.emit("SWEEPER_SET_AOA_SWEEP", "CUSTOM", list(aoa))
    if beta is not None:
        script.emit("SWEEPER_SET_BETA_SWEEP", "CUSTOM", list(beta))
    if velocity_file is not None:
        script.emit("SWEEPER_SET_VELOCITY_SWEEP", "CUSTOM", velocity_file)
    if clear_solution is not None:
        script.emit("SWEEPER_CLEAR_SOLUTION", _toggle(clear_solution))
    if ref_velocity_same is not None:
        script.emit("SWEEPER_REF_VELOCITY_SAME", _toggle(ref_velocity_same))
    if post_run_script is not None:
        script.emit("SWEEPER_POST_RUN_SCRIPT", "ENABLE", post_run_script)
    if start:
        script.emit("SWEEPER_START")
    if export_spreadsheet is not None:
        script.emit("SWEEPER_EXPORT_SPREADSHEET", export_spreadsheet)


def analysis_setup(
    script: Script,
    *,
    loads_frame: int | None = None,
    moments_model: str | None = None,
    symmetry_loads: bool | None = None,
    load_units: str | None = None,
    boundaries: Sequence[int] | None = None,
    inviscid_only: bool | None = None,
    vorticity_drag_boundaries: Sequence[int] | Literal["all"] | None = None,
) -> None:
    """Select how loads and moments are analyzed (SRC-003 pp.350-351).

    Parameters
    ----------
    script : Script
        Script under construction.
    loads_frame : int, optional
        Coordinate system for evaluating loads and moments; index 1 is
        the reference frame.
    moments_model : str, optional
        ``PRESSURE`` (solver default) or ``VORTICITY``.
    symmetry_loads : bool, optional
        Include symmetry boundary loads; relevant to half-model runs.
    load_units : str, optional
        ``COEFFICIENTS``, ``NEWTONS``, ``KILO-NEWTONS``,
        ``POUND-FORCE``, or ``KILOGRAM-FORCE``.
    boundaries : sequence of int, optional
        Boundaries enabled in the analysis; boundaries not listed are
        disabled (SRC-003 p.351).
    inviscid_only : bool, optional
        Restrict the analysis to inviscid loads and moments.
    vorticity_drag_boundaries : sequence of int, ``"all"``, or None
        Boundaries whose induced drag comes from surface vorticity
        integration; boundaries without trailing-edge boundary
        conditions silently report zero induced drag (SRC-003 p.202).
    """
    # symmetry_loads first: it is an init-phase setting consumed by the
    # in-solve monitors (per-step force plots), so a call mixing it
    # with the analysis-phase selections is only valid before
    # START_SOLVER; pass it alone in that position.
    if symmetry_loads is not None:
        script.emit("SET_ANALYSIS_SYMMETRY_LOADS", _toggle(symmetry_loads))
    if loads_frame is not None:
        script.emit("SET_SOLVER_ANALYSIS_LOADS_FRAME", loads_frame)
    if moments_model is not None:
        script.emit("SET_ANALYSIS_MOMENTS_MODEL", moments_model)
    if load_units is not None:
        script.emit("SET_LOADS_AND_MOMENTS_UNITS", load_units)
    if boundaries is not None:
        script.emit("SET_SOLVER_ANALYSIS_BOUNDARIES", len(boundaries), list(boundaries))
    if inviscid_only is not None:
        script.emit("SET_INVISCID_LOADS", _toggle(inviscid_only))
    if vorticity_drag_boundaries == "all":
        script.emit("SET_VORTICITY_DRAG_BOUNDARIES", -1)
    elif vorticity_drag_boundaries is not None:
        script.emit(
            "SET_VORTICITY_DRAG_BOUNDARIES",
            len(vorticity_drag_boundaries),
            list(vorticity_drag_boundaries),
        )


def export_results(
    script: Script,
    *,
    spreadsheet: str | None = None,
    tecplot: str | None = None,
    vtk: str | None = None,
    vtk_boundaries: Sequence[int] | Literal["all"] = "all",
    vtk_variables: Sequence[str] | Literal["all"] | None = None,
    vtk_wake: bool = False,
    force_distributions: str | None = None,
) -> None:
    """Export the solver results that were requested (SRC-003 pp.352-354).

    Parameters
    ----------
    script : Script
        Script under construction.
    spreadsheet : str, optional
        Path of the loads and moments spreadsheet, the primary
        quantitative output of a steady run.
    tecplot : str, optional
        Path of the Tecplot .dat export.
    vtk : str, optional
        Path of the VTK export.
    vtk_boundaries : sequence of int or ``"all"``
        Boundaries included in the VTK export.
    vtk_variables : sequence of str, ``"all"``, or None
        Variables selected before the VTK export; None keeps the
        current selection. ``CP`` is flagged for depreciation in favor
        of ``CP_REFERENCE`` and ``CP_FREESTREAM`` (SRC-003 p.352); the
        helper warns when it is requested.
    vtk_wake : bool
        Include the wake in the VTK variable selection.
    force_distributions : str, optional
        Path of the force distribution vectors export, all boundaries.
    """
    if spreadsheet is not None:
        script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", spreadsheet)
    if tecplot is not None:
        script.emit("EXPORT_SOLVER_ANALYSIS_TECPLOT", tecplot)
    if vtk_variables == "all":
        script.emit("SET_VTK_EXPORT_VARIABLES", -1, _toggle(vtk_wake))
    elif vtk_variables is not None:
        if any(variable.upper() == "CP" for variable in vtk_variables):
            warnings.warn(
                "the CP export variable is flagged for depreciation; prefer "
                "CP_REFERENCE or CP_FREESTREAM (SRC-003 p.352)",
                stacklevel=2,
            )
        script.emit(
            "SET_VTK_EXPORT_VARIABLES", len(vtk_variables), _toggle(vtk_wake), list(vtk_variables)
        )
    if vtk is not None:
        if vtk_boundaries == "all":
            script.emit("EXPORT_SOLVER_ANALYSIS_VTK", vtk, -1)
        else:
            script.emit(
                "EXPORT_SOLVER_ANALYSIS_VTK", vtk, len(vtk_boundaries), list(vtk_boundaries)
            )
    if force_distributions is not None:
        script.emit("EXPORT_SOLVER_ANALYSIS_FORCE_DISTRIBUTIONS", force_distributions, -1)


def probe_points(
    script: Script,
    points: Sequence[tuple[float, float, float]],
    *,
    kind: str = "VOLUME",
) -> None:
    """Create individual probe points (SRC-003 p.362).

    Parameters
    ----------
    script : Script
        Script under construction.
    points : sequence of (x, y, z) triples
        Probe positions in the reference frame, simulation length
        units.
    kind : str
        ``VOLUME`` or ``SURFACE`` probes.
    """
    for x, y, z in points:
        script.emit("NEW_PROBE_POINT", kind, x, y, z)


def probe_line(
    script: Script,
    *,
    points: int,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
) -> None:
    """Create a survey line of probe points (SRC-003 p.362).

    Parameters
    ----------
    script : Script
        Script under construction.
    points : int
        Number of probe vertices between start and end.
    start, end : (x, y, z) triples
        Line ends in the reference frame, simulation length units.
    """
    script.emit("NEW_PROBE_LINE", points, *start, *end)


def probes_from_file(script: Script, path: str, *, units: str, frame: int = 1) -> None:
    """Import a probe lattice from a CSV file (SRC-003 pp.362-363).

    The file rows are X,Y,Z,TYPE with TYPE 0 for surface and 1 for
    volume probes; the first line holds the point count. This is the
    programmatic path for probe lattice generation.

    Parameters
    ----------
    script : Script
        Script under construction.
    path : str
        Probe lattice CSV path.
    units : str
        Length unit of the file coordinates (``METER``, ``INCH``, and
        the other simulation length units).
    frame : int
        Coordinate system of the file coordinates; index 1 is the
        reference frame.
    """
    script.emit("PROBE_POINTS_IMPORT", units, frame, path)


def export_probes(script: Script, path: str, *, update: bool = True) -> None:
    """Export the probe values, refreshing them first (SRC-003 pp.362-363).

    Parameters
    ----------
    script : Script
        Script under construction.
    path : str
        Export file path.
    update : bool
        Emit UPDATE_PROBE_POINTS first, so the export reflects the
        current solution; the manual instructs refreshing before
        exporting (SRC-003 p.362).
    """
    if update:
        script.emit("UPDATE_PROBE_POINTS")
    script.emit("EXPORT_PROBE_POINTS", path)
