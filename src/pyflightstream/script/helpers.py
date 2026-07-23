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

Entity citations by label: every parameter that cites a frame,
actuator, motion, or mesh boundary accepts the 1-based index or the
label registered at creation (``label=``) or declared through
:meth:`~pyflightstream.script.Script.declare_existing`; labels resolve
to indices at emission through the script's entity registry.

Provenance: :func:`solver_settings` is the single entry point for every
solver flag of the runtime_settings, solver_settings, and
advanced_settings families. It carries the optional induced-drag
boundary selection (``vorticity_drag_boundaries``), emits the library
minimum-Cp default when the caller does not choose one, and attaches a
:class:`~pyflightstream.script.solver_setup.SolverSetup` snapshot of
every effective flag value to the script (``script.solver_setup``) for
the run manifest. The induced-drag selection itself is an
analysis-phase command, so when it is passed its emission is deferred
and lands right after the solver starts: :func:`start_solver` (or the
first analysis or export helper call) flushes it.
"""

from __future__ import annotations

import warnings
from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import ValidationError

from pyflightstream.commands import CommandRegistry
from pyflightstream.script import CommandArgumentError, Script
from pyflightstream.script.solver_setup import (
    LIBRARY_MINIMUM_CP,
    BulkSeparation,
    SolverSetup,
    build_setup,
    with_vorticity_selection,
)


def _toggle(value: bool) -> str:
    return "ENABLE" if value else "DISABLE"


def _flush_pending_vorticity(script: Script) -> None:
    """Emit the deferred induced-drag boundary selection, if one waits.

    :func:`solver_settings` records the selection it was given but
    cannot emit it in place: SET_VORTICITY_DRAG_BOUNDARIES is an
    analysis-phase command (SRC-003 p.350) and the settings are emitted
    in the init phase, before the solver starts. The selection is
    therefore flushed by :func:`start_solver`, by :func:`sweep` right
    after SWEEPER_START, and by the first :func:`analysis_setup` or
    :func:`export_results` call that reaches the analysis phase.
    """
    pending = script._pending_vorticity
    if pending is None:
        return
    script._pending_vorticity = None
    if pending == "all":
        script.emit("SET_VORTICITY_DRAG_BOUNDARIES", -1)
    else:
        script.emit("SET_VORTICITY_DRAG_BOUNDARIES", len(pending), list(pending))


def _reject_bare_label(helper: str, argument: str, value: object, *, allows_all: bool) -> None:
    """Reject a single label string where a sequence is expected.

    A bare string would otherwise be iterated character by character,
    producing a confusing downstream error; the fix (wrapping the
    label in a list) is stated directly.
    """
    if not isinstance(value, str):
        return
    if allows_all and value == "all":
        return
    accepted = "a sequence of indices or labels"
    if allows_all:
        accepted += " or the string 'all'"
    raise CommandArgumentError(
        f"{helper}: {argument} takes {accepted}; a single entity label goes in a "
        f"list, for example [{value!r}]"
    )


def _reject_empty_selection(helper: str, argument: str, value: list[object]) -> None:
    """Reject an empty induced-drag selection, naming both ways out.

    An empty sequence would emit SET_VORTICITY_DRAG_BOUNDARIES naming
    no boundary, which is not how the solver default is expressed: the
    default is the command never being emitted at all (SRC-003 p.202).
    The realistic way to reach an empty sequence is a selection filter
    that matched nothing, so the message names that diagnosis too.
    """
    if len(value) > 0:
        return
    raise CommandArgumentError(
        f"{helper}: {argument} is an empty sequence, which would emit a selection "
        "command naming no boundary. Omit the argument (or pass None) to leave every "
        "boundary on the solver default, surface pressure integration (SRC-003 "
        "p.202); if the list was computed, the selection filter matched no boundary."
    )


def free_stream(
    script: Script,
    kind: str = "CONSTANT",
    *,
    frame: int | str | None = None,
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
    frame : int or str, optional
        ROTATION only: local coordinate system carrying the rotation
        axis, cited by index or by its creation label; it must exist
        earlier in the script.
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
    frame: int | str,
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
    label: str | None = None,
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
    frame : int or str
        Local coordinate system carrying the disc axis (index greater
        than 1, or its creation label); it must exist earlier in the
        script.
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
    label : str, optional
        Label registered for the created actuator in the script's
        entity registry, so later commands can cite it by name
        instead of by index.

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
    script.emit("CREATE_NEW_ACTUATOR", "PROPELLER", subtype=subtype, name=name, label=label)
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
    frame: int | str,
    axis: str,
    rpm: float,
    boundaries: Sequence[int | str] | Literal["all"] = "all",
    moving_frames: Sequence[int | str] | Literal["all"] | None = None,
    start_time: float | None = None,
    wake_stabilization_blades: int | None = None,
    label: str | None = None,
) -> int:
    """Create and configure one rotary motion (SRC-003 pp.332-333).

    Rotary motion is the blade-resolved alternative to the actuator
    disc surrogate (SRC-003 p.234); it requires the unsteady solver
    (see :func:`unsteady_solver`).

    Parameters
    ----------
    script : Script
        Script under construction.
    frame : int or str
        Local coordinate system of the rotation (index greater than
        1, or its creation label); it must exist earlier in the
        script.
    axis : str
        Rotor axis within ``frame``: ``X``, ``Y``, or ``Z``.
    rpm : float
        Rotor speed in rev/min.
    boundaries : sequence of int or str, or ``"all"``
        Geometry boundaries assigned to the motion, by 1-based index
        or declared boundary label; ``"all"`` selects every boundary
        (-1 form). Indices are verified against the inventory declared
        with declare_existing(boundaries=...) when one exists.
    moving_frames : sequence of int or str, ``"all"``, or None
        Local frames attached to the motion, by index or creation
        label; None attaches none.
    start_time : float, optional
        Motion start within the solver physical time, in s; a positive
        value converges a steady base flow before the motion begins.
    wake_stabilization_blades : int, optional
        Enables slipstream wake stabilization with this blade count.
    label : str, optional
        Label registered for the created motion in the script's
        entity registry, so later commands can cite it by name
        instead of by index.

    Returns
    -------
    int
        Identifier of the created motion, for later citations.
    """
    _reject_bare_label("rotary_motion", "boundaries", boundaries, allows_all=True)
    _reject_bare_label("rotary_motion", "moving_frames", moving_frames, allows_all=True)
    script.emit("CREATE_NEW_MOTION", "ROTARY", label=label)
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
    vorticity_drag_boundaries: Sequence[int | str] | Literal["all"] | None = None,
    mode: str | None = None,
    time_iterations: int | None = None,
    delta_time: float | None = None,
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
    viscous_excluded: Sequence[int | str] | None = None,
    bulk_separation: BulkSeparation | Mapping | None = None,
    convergence_iterations: int | None = None,
    minimum_cp: float | None = None,
    reynolds_averaged_drag: bool | None = None,
    mesh_induced_wake_velocity: bool | None = None,
    farfield_layers: int | None = None,
    unsteady_pressure_and_kutta: bool | None = None,
    wake_termination_time_steps: int | None = None,
    wake_on_wake_induction: bool | None = None,
    additional_wake_relaxation: bool | None = None,
    aeroelastic_rbf_type: str | None = None,
) -> SolverSetup:
    """Set the solver flags, record their provenance, and return the snapshot.

    Single entry point for every command of the runtime_settings
    (SRC-003 pp.339-340), solver_settings (pp.341-343), and
    advanced_settings (pp.344-346) families. Only the provided flags
    are emitted (plus the library minimum-Cp default, below), so the
    helper serves both the initial setup and the re-emission between
    campaign points; the returned
    :class:`~pyflightstream.script.solver_setup.SolverSetup` snapshot
    records the effective value and provenance of every flag, passed or
    not, and is attached to the script as ``script.solver_setup`` for
    the run manifest.

    Two flags have library-level behavior:

    - ``vorticity_drag_boundaries`` selects the boundaries whose
      induced drag comes from surface vorticity integration. Omitting
      it leaves this script's selection as it stands: nothing, on the
      first settings call, which is the solver default of surface
      pressure integration on every boundary (SRC-003 p.202); the
      selection of the earlier call, on a second settings call of the
      same script, since the line it emitted stays in the script. The
      selection is an analysis-phase command, so when it is passed its
      emission is deferred to the first curated call that reaches the
      analysis phase: :func:`start_solver`, :func:`sweep`,
      :func:`analysis_setup`, or :func:`export_results`. A raw
      ``script.emit("START_SOLVER")`` does not flush it.
    - ``minimum_cp`` unset emits ``SOLVER_MINIMUM_CP -100``: the
      solver's own default -20 (SRC-003 p.221) clips the suction peaks
      of rotor blades, so -100 is the library default (author decision
      of 2026-07-22, retiring the earlier reference-velocity
      workaround); pass the flag to override. The physics references
      were re-validated under this default, 30 of 30 metrics
      bit-identical (report
      PHY-26120_2026-07-23_reseed-cp100-2026-07-23). On a
      FlightStream version without the command nothing is emitted and
      the snapshot honestly records the flag as unknown.

    Parameters
    ----------
    script : Script
        Script under construction.
    vorticity_drag_boundaries : sequence of int or str, ``"all"``, or None
        Boundaries whose induced drag comes from surface vorticity
        integration, by 1-based index or declared boundary label;
        ``"all"`` selects every boundary (-1 form). The manual
        recommends the list for boundaries carrying a user-defined
        trailing-edge condition, a wing for instance, and advises
        against bluff bodies such as a tubular fuselage: a bluff body
        placed on this list reports zero induced drag, which is why
        ``"all"`` is unsafe on a mixed geometry (SRC-003 p.202). None (the
        default) emits no selection command and leaves every boundary
        on the solver's own surface pressure integration, which the
        manual also prescribes for every component in ground effect
        (SRC-003 p.202); an empty sequence is refused, because the
        solver default is expressed by omitting the argument, not by
        selecting nothing. A second settings call on the same script
        may omit the argument: the selection of the earlier call stays
        in the script and in the snapshot. There is no way to unselect
        on a script that already selected; build a fresh
        :class:`~pyflightstream.script.Script` for that.
    mode : str, optional
        Solver time regime: ``STEADY`` (SET_SOLVER_STEADY) or
        ``UNSTEADY`` (SET_SOLVER_UNSTEADY, physical time stepping,
        SRC-003 p.341).
    time_iterations : int, optional
        UNSTEADY only: number of physical time steps.
    delta_time : float, optional
        UNSTEADY only: physical time step in s. For rotary cases the
        manual recommends 8 to 12 degrees of blade rotation per step
        and at least two full rotations (SRC-003 p.210).
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
    viscous_excluded : sequence of int or str, optional
        Boundaries excluded from viscous coupling, by 1-based index
        or declared boundary label; verified against the inventory
        declared with declare_existing(boundaries=...) when one
        exists.
    bulk_separation : BulkSeparation or mapping, optional
        Bulk (bluff-body) flow-separation assignment
        (CREATE_BULK_SEPARATION, SRC-003 p.342); see
        :class:`~pyflightstream.script.solver_setup.BulkSeparation`.
    convergence_iterations : int, optional
        Iterations the solver must stay below the convergence
        threshold before convergence is declared (SRC-003 p.344).
    minimum_cp : float, optional
        Lower limiter on the pressure coefficient, dimensionless
        (SRC-003 p.345); see the library-default note above.
    reynolds_averaged_drag : bool, optional
        Toggle the Reynolds-averaged (flat plate) boundary layer
        calculations (SRC-003 p.344).
    mesh_induced_wake_velocity : bool, optional
        Toggle the mesh-induced wake velocity computation
        (SRC-003 p.344).
    farfield_layers : int, optional
        Far-field agglomeration layer count, integer between 1 and 5;
        the solver default is 3 (SRC-003 p.344).
    unsteady_pressure_and_kutta : bool, optional
        Toggle the unsteady Bernoulli and Kutta terms of the unsteady
        solver (SRC-003 p.344).
    wake_termination_time_steps : int, optional
        Time steps after which a fully faded wake vortex filament edge
        is removed (SRC-003 p.344).
    wake_on_wake_induction : bool, optional
        Toggle the wake-on-wake induced velocity computation
        (SRC-003 pp.344-345).
    additional_wake_relaxation : bool, optional
        Perform one additional wake relaxation iteration
        (SRC-003 p.345).
    aeroelastic_rbf_type : str, optional
        RBF mesh morphing algorithm of the aeroelastic coupling:
        ``WENDLAND_C2``, ``GAUSSIAN``, ``THIN_PLATE_SPLINE``,
        ``MULTI_QUADRATIC``, or ``INV_MULTI_QUADRATIC``
        (SRC-003 p.345).

    Returns
    -------
    SolverSetup
        The snapshot of effective flag values and provenance, also
        attached to the script as ``script.solver_setup``.
    """
    _reject_bare_label(
        "solver_settings", "vorticity_drag_boundaries", vorticity_drag_boundaries, allows_all=True
    )
    _reject_bare_label("solver_settings", "viscous_excluded", viscous_excluded, allows_all=False)
    upper_mode = mode.upper() if mode is not None else None
    if upper_mode is not None and upper_mode not in ("STEADY", "UNSTEADY"):
        raise CommandArgumentError(
            f"solver_settings mode takes STEADY or UNSTEADY, got {mode!r}: the solver "
            "time regime is one of the two (SRC-003 p.341)"
        )
    if upper_mode == "UNSTEADY" and (time_iterations is None or delta_time is None):
        raise CommandArgumentError(
            "solver_settings mode='UNSTEADY' needs both time_iterations and delta_time: "
            "physical time stepping is defined by the step count and the step size "
            "(SRC-003 p.341)"
        )
    if upper_mode != "UNSTEADY" and (time_iterations is not None or delta_time is not None):
        raise CommandArgumentError(
            "solver_settings: time_iterations and delta_time belong to the unsteady "
            "solver; pass mode='UNSTEADY' with them, or drop them for a steady run "
            "(SRC-003 p.341)"
        )
    bulk: BulkSeparation | None = None
    if bulk_separation is not None:
        try:
            bulk = BulkSeparation.model_validate(bulk_separation)
        except ValidationError as error:
            raise CommandArgumentError(
                "solver_settings: bulk_separation takes a BulkSeparation (name, "
                f"separation_type, diameter, boundaries; SRC-003 p.342): {error}"
            ) from error
    # Resolve the induced-drag selection before any emission, so a bad
    # label or index leaves the script untouched; the emission itself is
    # deferred to the analysis phase (see the docstring). Unset on the
    # first settings call means the command is never emitted and the
    # solver default applies; unset on a re-emission call keeps the
    # selection the earlier call chose, so a per-point re-emission
    # neither drops it from the script nor from the snapshot.
    selection: list[int] | Literal["all"] | None
    if vorticity_drag_boundaries is None:
        selection = script._vorticity_selection
    elif vorticity_drag_boundaries == "all":
        selection = "all"
    else:
        # Materialize once: a computed selection may arrive as any
        # iterable, and the emptiness check must not consume it.
        items = list(vorticity_drag_boundaries)
        _reject_empty_selection("solver_settings", "vorticity_drag_boundaries", items)
        selection = [
            script.resolve_boundary(
                item, context="solver_settings: argument 'vorticity_drag_boundaries'"
            )
            for item in items
        ]

    if upper_mode == "STEADY":
        script.emit("SET_SOLVER_STEADY")
    elif upper_mode == "UNSTEADY":
        script.emit("SET_SOLVER_UNSTEADY", time_iterations, delta_time)
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
    if bulk is not None:
        if bulk.boundaries == "all":
            script.emit(
                "CREATE_BULK_SEPARATION",
                name=bulk.name,
                separation_type=bulk.separation_type,
                num_boundaries=-1,
                diameter=bulk.diameter,
            )
        else:
            script.emit(
                "CREATE_BULK_SEPARATION",
                name=bulk.name,
                separation_type=bulk.separation_type,
                num_boundaries=len(bulk.boundaries),
                diameter=bulk.diameter,
                boundary_indices=list(bulk.boundaries),
            )
    if convergence_iterations is not None:
        script.emit("SET_SOLVER_CONVERGENCE_ITERATIONS", convergence_iterations)
    minimum_cp_default_emitted = False
    if minimum_cp is not None:
        script.emit("SOLVER_MINIMUM_CP", minimum_cp)
    elif "SOLVER_MINIMUM_CP" in CommandRegistry.load().for_version(script.version):
        script.emit("SOLVER_MINIMUM_CP", LIBRARY_MINIMUM_CP)
        minimum_cp_default_emitted = True
    if reynolds_averaged_drag is not None:
        script.emit("REYNOLDS_AVERAGED_DRAG_FORCES", _toggle(reynolds_averaged_drag))
    if mesh_induced_wake_velocity is not None:
        script.emit("SOLVER_SET_MESH_INDUCED_WAKE_VELOCITY", _toggle(mesh_induced_wake_velocity))
    if farfield_layers is not None:
        script.emit("SOLVER_SET_FARFIELD_LAYERS", farfield_layers)
    if unsteady_pressure_and_kutta is not None:
        script.emit("SOLVER_UNSTEADY_PRESSURE_AND_KUTTA", _toggle(unsteady_pressure_and_kutta))
    if wake_termination_time_steps is not None:
        script.emit("SET_WAKE_TERMINATION_TIME_STEPS", wake_termination_time_steps)
    if wake_on_wake_induction is not None:
        script.emit("SET_WAKE_ON_WAKE_INDUCTION", _toggle(wake_on_wake_induction))
    if additional_wake_relaxation is not None:
        script.emit("ADDITIONAL_WAKE_RELAXATION_ITERATION", _toggle(additional_wake_relaxation))
    if aeroelastic_rbf_type is not None:
        script.emit("AEROELASTIC_RBF_TYPE", aeroelastic_rbf_type)

    if vorticity_drag_boundaries is not None:
        script._vorticity_selection = selection
        script._pending_vorticity = selection

    passed: dict[str, object] = {
        "mode": upper_mode,
        "time_iterations": time_iterations,
        "delta_time": delta_time,
        "aoa": aoa,
        "sideslip": sideslip,
        "velocity": velocity,
        "mach": mach,
        "ref_velocity": ref_velocity,
        "ref_mach": ref_mach,
        "ref_area": ref_area,
        "ref_length": ref_length,
        "iterations": iterations,
        "convergence": convergence,
        "forced_iterations": forced_iterations,
        "max_threads": max_threads,
        "boundary_layer": boundary_layer.upper() if boundary_layer is not None else None,
        "viscous_coupling": viscous_coupling,
        "viscous_excluded": viscous_excluded,
        "bulk_separation": bulk,
        "convergence_iterations": convergence_iterations,
        "minimum_cp": minimum_cp,
        "reynolds_averaged_drag": reynolds_averaged_drag,
        "mesh_induced_wake_velocity": mesh_induced_wake_velocity,
        "farfield_layers": farfield_layers,
        "unsteady_pressure_and_kutta": unsteady_pressure_and_kutta,
        "wake_termination_time_steps": wake_termination_time_steps,
        "wake_on_wake_induction": wake_on_wake_induction,
        "additional_wake_relaxation": additional_wake_relaxation,
        "aeroelastic_rbf_type": (
            aeroelastic_rbf_type.upper() if aeroelastic_rbf_type is not None else None
        ),
        # The effective selection, which on a re-emission call is the one
        # the earlier call chose: the snapshot must describe the script,
        # not just this call.
        "vorticity_drag_boundaries": selection,
    }
    setup = build_setup(
        version=script.version.canonical,
        passed=passed,
        minimum_cp_default_emitted=minimum_cp_default_emitted,
    )
    script.solver_setup = setup
    return setup


def start_solver(script: Script) -> None:
    """Start the solver and land the deferred induced-drag selection.

    Emits START_SOLVER (SRC-003 p.338) and then the
    SET_VORTICITY_DRAG_BOUNDARIES emission that
    :func:`solver_settings` recorded, if any: the selection is an
    analysis-phase command (SRC-003 p.350) that cannot precede the
    exec phase, so pairing it with the solver start is what makes a
    selection built during the settings call actually reach the
    script. When no selection was passed nothing is flushed and the
    solver default applies, which is surface pressure integration on
    every boundary (SRC-003 p.202).

    Parameters
    ----------
    script : Script
        Script under construction.
    """
    script.emit("START_SOLVER")
    _flush_pending_vorticity(script)


def initialize_solver(
    script: Script,
    *,
    solver_model: str = "INCOMPRESSIBLE",
    surfaces: Sequence[tuple[int | str, bool]] | Literal["all"] = "all",
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
    surfaces : sequence of (int or str, bool) pairs or ``"all"``
        ``"all"`` initializes every boundary (-1 form); a sequence of
        ``(surface, quad_mesher)`` pairs initializes those surfaces
        with the quad mesher toggled per surface. Each surface is a
        1-based mesh boundary index or a boundary label declared with
        declare_existing(boundaries=...); labels resolve at emission
        and indices are verified against the declared inventory when
        one exists.
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
        # The per-surface toggles render as strings, so boundary labels
        # are resolved here rather than by the emit-level checks.
        resolved = [
            (
                script.resolve_boundary(index, context="INITIALIZE_SOLVER: argument 'surfaces'"),
                quad_mesher,
            )
            for index, quad_mesher in surfaces
        ]
        arguments["surfaces"] = len(resolved)
        arguments["surface_toggles"] = [
            f"{index},{_toggle(quad_mesher)}" for index, quad_mesher in resolved
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
        Emit SWEEPER_START after the configuration. Starting the sweep
        also lands the induced-drag selection deferred by
        :func:`solver_settings`, right after SWEEPER_START: the
        selection is an analysis-phase command, so this is its
        earliest legal position in a sweeper script.
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
        _flush_pending_vorticity(script)
    if export_spreadsheet is not None:
        script.emit("SWEEPER_EXPORT_SPREADSHEET", export_spreadsheet)


def analysis_setup(
    script: Script,
    *,
    loads_frame: int | str | None = None,
    moments_model: str | None = None,
    symmetry_loads: bool | None = None,
    load_units: str | None = None,
    boundaries: Sequence[int | str] | None = None,
    inviscid_only: bool | None = None,
    vorticity_drag_boundaries: Sequence[int | str] | Literal["all"] | None = None,
) -> None:
    """Select how loads and moments are analyzed (SRC-003 pp.350-351).

    Parameters
    ----------
    script : Script
        Script under construction.
    loads_frame : int or str, optional
        Coordinate system for evaluating loads and moments; index 1 is
        the reference frame, and created frames may be cited by their
        creation label.
    moments_model : str, optional
        ``PRESSURE`` (solver default) or ``VORTICITY``.
    symmetry_loads : bool, optional
        Include symmetry boundary loads; relevant to half-model runs.
    load_units : str, optional
        ``COEFFICIENTS``, ``NEWTONS``, ``KILO-NEWTONS``,
        ``POUND-FORCE``, or ``KILOGRAM-FORCE``.
    boundaries : sequence of int or str, optional
        Boundaries enabled in the analysis, by 1-based index or
        declared boundary label; boundaries not listed are disabled
        (SRC-003 p.351). Indices are verified against the inventory
        declared with declare_existing(boundaries=...) when one
        exists.
    inviscid_only : bool, optional
        Restrict the analysis to inviscid loads and moments.
    vorticity_drag_boundaries : sequence of int or str, ``"all"``, or None
        Deprecated here since v0.3.0: the induced-drag boundary
        selection belongs to :func:`solver_settings` and will leave
        analysis_setup in a future minor release. Passing it still
        works (with a DeprecationWarning) and replaces any selection
        deferred by :func:`solver_settings`. Boundaries whose induced
        drag comes from surface vorticity integration, by index or
        declared label; a bluff body without a user-defined
        trailing-edge condition reports zero induced drag when placed
        on this list (SRC-003 p.202). The replacement is recorded in
        ``script.solver_setup``, which is the snapshot to serialize; a
        snapshot object returned by an earlier :func:`solver_settings`
        call is frozen and keeps the state of that call.
    """
    _reject_bare_label("analysis_setup", "boundaries", boundaries, allows_all=False)
    _reject_bare_label(
        "analysis_setup", "vorticity_drag_boundaries", vorticity_drag_boundaries, allows_all=True
    )
    # Resolve this call's own selection before anything is emitted or
    # recorded, exactly as solver_settings does: a bad label must leave
    # the script, the deferred selection, and the snapshot untouched.
    chosen: list[int] | Literal["all"] | None = None
    if vorticity_drag_boundaries is not None:
        if vorticity_drag_boundaries == "all":
            chosen = "all"
        else:
            items = list(vorticity_drag_boundaries)
            _reject_empty_selection("analysis_setup", "vorticity_drag_boundaries", items)
            chosen = [
                script.resolve_boundary(
                    item, context="analysis_setup: argument 'vorticity_drag_boundaries'"
                )
                for item in items
            ]
        replaced = (
            "; this explicit call replaces the selection deferred by solver_settings"
            if script._pending_vorticity is not None
            else ""
        )
        warnings.warn(
            "analysis_setup(vorticity_drag_boundaries=...) is deprecated: the "
            "induced-drag boundary selection is a parameter of solver_settings "
            "since v0.3.0 and will leave analysis_setup in a future minor "
            f"release{replaced}",
            DeprecationWarning,
            stacklevel=2,
        )
    # symmetry_loads first: it is an init-phase setting consumed by the
    # in-solve monitors (per-step force plots), so a call mixing it
    # with the analysis-phase selections is only valid before
    # START_SOLVER; pass it alone in that position.
    if symmetry_loads is not None:
        script.emit("SET_ANALYSIS_SYMMETRY_LOADS", _toggle(symmetry_loads))
    if any(
        argument is not None
        for argument in (
            loads_frame,
            moments_model,
            load_units,
            boundaries,
            inviscid_only,
            vorticity_drag_boundaries,
        )
    ):
        # The call reaches the analysis phase: land the selection
        # deferred by solver_settings before the analysis choices,
        # unless this call carries its own, which replaces it below.
        if chosen is None:
            _flush_pending_vorticity(script)
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
    if chosen == "all":
        script.emit("SET_VORTICITY_DRAG_BOUNDARIES", -1)
    elif chosen is not None:
        script.emit("SET_VORTICITY_DRAG_BOUNDARIES", len(chosen), list(chosen))
    if chosen is not None:
        # Every emission of this call succeeded, so the script state and
        # the snapshot may now record the replacement: a failure above
        # leaves the selection solver_settings deferred still pending.
        script._pending_vorticity = None
        script._vorticity_selection = chosen
        if script.solver_setup is not None:
            script.solver_setup = with_vorticity_selection(script.solver_setup, chosen)


def export_results(
    script: Script,
    *,
    spreadsheet: str | None = None,
    tecplot: str | None = None,
    vtk: str | None = None,
    vtk_boundaries: Sequence[int | str] | Literal["all"] = "all",
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
    vtk_boundaries : sequence of int or str, or ``"all"``
        Boundaries included in the VTK export, by 1-based index or
        declared boundary label.
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
    _reject_bare_label("export_results", "vtk_boundaries", vtk_boundaries, allows_all=True)
    # Exports read the analysis state: land the induced-drag selection
    # deferred by solver_settings before the first export command.
    _flush_pending_vorticity(script)
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


def probes_from_file(script: Script, path: str, *, units: str, frame: int | str = 1) -> None:
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
    frame : int or str
        Coordinate system of the file coordinates; index 1 is the
        reference frame, and created frames may be cited by their
        creation label.
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


def coordinate_frame(
    script: Script,
    *,
    name: str,
    origin: Sequence[float],
    x_axis: Sequence[float],
    y_axis: Sequence[float],
    z_axis: Sequence[float] | None = None,
    label: str | None = None,
) -> int:
    """Create and define a local coordinate system, returning its index.

    Emits CREATE_NEW_COORDINATE_SYSTEM followed by
    EDIT_COORDINATE_SYSTEM with the origin and the three axis vectors
    in the reference frame (coordinate_systems chapter). Use it when
    the solver should carry the same plane a probe grid was
    prescribed on; probe positions themselves are always imported in
    the reference frame (frame 1), so this helper is presentation,
    not placement.

    Parameters
    ----------
    script : Script
        Script under construction.
    name : str
        Name of the new coordinate system.
    origin : sequence of float
        Frame origin in the reference frame (simulation length units).
    x_axis, y_axis : sequence of float
        Axis direction vectors in the reference frame.
    z_axis : sequence of float, optional
        Third axis; computed as the right-handed cross product of
        x_axis and y_axis when omitted.
    label : str, optional
        Label registered for the created frame in the script's entity
        registry, so later commands can cite it by name instead of by
        index. Distinct from ``name``, which is the display name
        FlightStream shows in the interface.

    Returns
    -------
    int
        Index of the created frame (the reference frame is 1; created
        local frames follow).
    """
    if z_axis is None:
        ax, ay, az = x_axis
        bx, by, bz = y_axis
        z_axis = (ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx)
    script.emit("CREATE_NEW_COORDINATE_SYSTEM", label=label)
    frame_index = script.num_local_frames + 1
    script.emit(
        "EDIT_COORDINATE_SYSTEM",
        frame=frame_index,
        name=name,
        origin_x=origin[0],
        origin_y=origin[1],
        origin_z=origin[2],
        vector_x_x=x_axis[0],
        vector_x_y=x_axis[1],
        vector_x_z=x_axis[2],
        vector_y_x=y_axis[0],
        vector_y_y=y_axis[1],
        vector_y_z=y_axis[2],
        vector_z_x=z_axis[0],
        vector_z_y=z_axis[1],
        vector_z_z=z_axis[2],
    )
    return frame_index
