"""The solver settings, the flight-condition state and the reference data of a case (0.34.0).

Pipeline role: describes how a case asks the solver to solve.
:class:`SolverSettings` holds every solver setting a row or a setup states and
the command each one reaches (:data:`SOLVER_SETTING_COMMANDS`);
:class:`FluidState` and :class:`PointState` hold the flight condition of a
point, keyed by :func:`point_state_key`; :class:`ReferenceData` holds the
reference quantities of the coefficients. The settings a release adds land
here, beside the ones they extend.

The cut of AD-16 (0.34.0) moved these models out of the package root, which
re-exports every one of them. The settings read the mesh operations and the
port boundaries from :mod:`pyflightstream.cases.mesh`, in that direction only,
and this module never imports the package root.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

from pyflightstream._atmosphere import ISA

# The setup keys' command table and the tables FR-319 added; its module imports
# only pydantic and the command database, so the package may import it while it loads.
from pyflightstream.cases._setup_keys import SOLVER_SETTING_COMMANDS, MomentsModel, UnsteadyAction
from pyflightstream.cases.mesh import (
    BaseRegionOperation,
    PortBoundary,
)
from pyflightstream.cases.reference_blocks import ActuatorOperation
from pyflightstream.commands import CommandRegistry
from pyflightstream.script.solver_setup import (
    AirfoilSeparation,
    AxialVortexSeparation,
    BulkSeparation,
    CylindricalBulkSeparation,
    StratfordBulkSeparation,
)
from pyflightstream.script.toggles import resolve_toggle

__all__ = [
    "FluidState",
    "ReferenceData",
    "SolverSettings",
    "SolverToggle",
    "SOLVER_SETTING_COMMANDS",
    "PointState",
    "point_state_key",
]


class ReferenceData(BaseModel):
    """Reference quantities for coefficient normalization.

    Attributes
    ----------
    area : float
        Reference area S_ref in simulation length units squared by default;
        square metres when normalization_units is SI.
    length : float
        Reference length L_ref in simulation length units by default;
        metres when normalization_units is SI.
    velocity : float, optional
        Reference velocity in m/s; None lets the recipe default it to
        the free-stream velocity (steady runs) or a characteristic
        velocity such as the rotor tip speed (SRC-003 p.201).
    rotor_diameter : float, optional
        Rotor diameter D in simulation length units, carried from
        the reference artifact's ``rotor_diameter_m``. It is the
        length an advance ratio is a ratio AGAINST: a row stating
        ``ADVANCE_RATIO`` resolves its rotor speed as
        ``n = V / (J D)``, so without this the ratio names no speed.
        None for a configuration with no rotor.
    """

    # PYFS-016. A reference area or length of zero divides every
    # coefficient by zero; a negative one flips the sign of every
    # coefficient in the report while the run looks healthy; an
    # infinite one drives them all to zero. All three were measured
    # accepted at HEAD. These are DIVISORS of the published numbers,
    # which is why the bound is a refusal rather than a warning.
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    #: Area/length basis only: native preserves the Python API; workspace REF files use SI.
    normalization_units: Literal["NATIVE", "SI"] = "NATIVE"
    area: float = Field(gt=0.0)
    length: float = Field(gt=0.0)
    velocity: float | None = Field(default=None, gt=0.0)
    rotor_diameter: float | None = Field(default=None, gt=0.0)
    #: The reference span, which the polar products scale the rolling and
    #: yawing moments to (PFS-2029.15); None keeps a case built without it.
    span_m: float | None = Field(default=None, gt=0.0)
    #: The moment reference point (x, y, z) in metres,
    #: carried from the reference artifact's ``[moment_point]``. A builder
    #: creates a coordinate system named MRP there and makes it the
    #: analysis loads frame, so moments are reported about it
    #: (PFS-2030.03.02). None for an authored case that states none, which
    #: leaves the solver's reference frame as the loads frame, as before.
    moment_point_m: tuple[float, float, float] | None = None
    #: The rotor position (x, y, z) in metres, from
    #: the reference artifact's ``[rotor.position]``. The two unsteady
    #: run types create a coordinate system named ROTOR_MRP there, which is
    #: the frame the reference probe lines and rotor plots are defined in,
    #: and the rotor run turns about it. None when the reference declares
    #: no rotor.
    rotor_position_m: tuple[float, float, float] | None = None
    #: WHICH MODEL AXIS EACH BODY RATE TURNS ABOUT (0.21.0), from the
    #: reference artifact's ``[body_axes]`` table: ``roll``, ``pitch`` and
    #: ``yaw`` to ``X``, ``Y`` or ``Z``. A mesh is built in whatever
    #: orientation its author chose, and a rotating free stream has to be
    #: given an AXIS of a frame, so the row cannot state one without the
    #: reference saying which axis is which. Empty for a reference that
    #: declares none, and a row stating a rate against such a reference is
    #: refused by name rather than guessed for.
    body_axes: dict[str, str] = Field(default_factory=dict)

    @field_validator("body_axes")
    @classmethod
    def _axes_are_three_named_axes(cls, value: dict[str, str]) -> dict[str, str]:
        """Refuse a table that names something other than one axis per rate."""
        axes = {key.strip().lower(): str(item).strip().upper() for key, item in value.items()}
        unknown = sorted(set(axes) - {"roll", "pitch", "yaw"})
        if unknown:
            raise ValueError(
                f"body_axes names {', '.join(unknown)}, and a body rate is one of roll, "
                "pitch or yaw. Write one axis for each rate the model can be given."
            )
        wrong = sorted(key for key, item in axes.items() if item not in {"X", "Y", "Z"})
        if wrong:
            raise ValueError(
                f"body_axes gives {', '.join(wrong)} an axis that is not X, Y or Z. An "
                "axis of a coordinate system is one of those three."
            )
        if len(set(axes.values())) != len(axes):
            raise ValueError(
                f"body_axes writes one axis twice ({axes}), and two body rates cannot turn "
                "about the same axis of one frame."
            )
        return axes


def _resolve_settings_toggle(value: object) -> object:
    """Resolve a settings toggle in either vocabulary, before validation.

    Runs ahead of pydantic's bool parsing, and resolves every value
    itself rather than only strings, so the settings field and the
    helper keyword it mirrors accept exactly the same thing: True and
    False, and the solver's own ENABLE and DISABLE. Pydantic's lax
    coercions (``"yes"``, ``"on"``, ``1``) are deliberately not
    accepted here, because a settings file that says ``1`` for a flag
    the solver writes as a word is more likely a mistake than an
    intent. The refusal is a ValueError, which pydantic reports as a
    ValidationError naming the field, so the message survives.
    """
    if value is None:
        return value
    return resolve_toggle(value, context="a solver settings toggle")


#: Settings toggle: a bool, or the solver's own ENABLE and DISABLE.
SolverToggle = Annotated[bool, BeforeValidator(_resolve_settings_toggle)]

#: A bare decimal number, the only text a wake end plane X is written as.
_BARE_NUMBER = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")


def _an_end_plane(value: object) -> object:
    """Return ``DEFAULT`` or a finite X in metres for ``wake_termination_x`` (FR-324 R1, R3).

    The solver's own two forms and nothing else: a bare finite number (a
    preset's TOML number, or a row cell's text), or the word ``DEFAULT``. A
    number with a unit, a distance in rotor radii, a non-finite number, an
    empty value and any other word are refused, naming the key and the forms.
    """
    if value is None:
        return None
    number: float | None = None
    if isinstance(value, int | float) and not isinstance(value, bool):
        number = float(value)
    elif isinstance(value, str) and value.strip() == "DEFAULT":
        return "DEFAULT"
    elif isinstance(value, str) and _BARE_NUMBER.match(value.strip()):
        number = float(value.strip())
    if number is None or not math.isfinite(number):
        raise ValueError(
            f"wake_termination_x takes DEFAULT or the X of the wake end plane in metres in "
            f"the simulation's reference frame, written as a bare finite number such as "
            f"2.75; got {value!r}. A number with a unit, a distance in rotor radii, a "
            "non-finite number, an empty value and any word other than DEFAULT are refused "
            "(FR-324)."
        )
    return number


class SolverSettings(BaseModel):
    """Solver runtime settings of one case.

    Runtime fields generally match the keywords of
    :func:`pyflightstream.script.helpers.solver_settings`. Geometry controls
    are applied by the workflow after import/open and before dimensional
    frames or edge detection; they must not be forwarded to a late runtime call.

    Attributes
    ----------
    iterations : int
        Solver iteration limit.
    convergence : float
        Residual threshold declaring convergence (SRC-003 p.200).
    forced_iterations : bool, optional
        Run the full iteration count regardless of convergence. The
        solver's own words are accepted too (see below).
    boundary_layer : str, optional
        The boundary layer model: ``LAMINAR``, ``TRANSITIONAL``, or
        ``TURBULENT``.
    viscous_coupling : bool, optional
        Couple the boundary layer model to the potential solution.
        The solver's own words are accepted too (see below).
    max_threads : int, optional
        Parallel core count; a row's ``NCPUS`` column wins over it.
    timeout_s : float, optional
        Wall-clock limit for one point's solver process; enforced by
        the executor, not by FlightStream.
    walltime_margin_s : float, optional
        How much of a row's ``WALLTIME`` to leave for the exports, in
        seconds; twenty minutes when unstated. It emits nothing.
    solver_model : str, optional
        The flow model the solver is initialized with, ``INCOMPRESSIBLE``,
        ``SUBSONIC_PRANDTL_GLAUERT``, ``TRANSONIC_FIELD_PANEL``,
        ``TANGENT_CONE`` or ``MODIFIED_NEWTONIAN``; an argument of
        ``INITIALIZE_SOLVER``. None leaves the emitter's own default, which
        is ``INCOMPRESSIBLE``.
    wall_collision_avoidance : bool, optional
        The wall-collision avoidance argument of ``INITIALIZE_SOLVER``, the
        other one a preset states.
    convergence_iterations : int, optional
        Iterations the residual must hold under the threshold before
        the solver calls the run converged.
    minimum_cp : float, optional
        Floor applied to the pressure coefficient.
    farfield_layers : int, optional
        Farfield layer count, 1 to 5 as the command database documents;
        every run is expected to state 5.
    mesh_induced_wake_velocity : bool, optional
        Switches the solver's mesh-induced wake velocity. This toggle
        and the four below it are advanced settings, and the solver's
        own ENABLE and DISABLE are read as well as Python booleans.
    unsteady_pressure_and_kutta : bool, optional
        Switches the unsteady Bernoulli and Kutta terms of the unsteady
        solver.
    wake_on_wake_induction : bool, optional
        Switches the wake-on-wake induced velocity computation.
    additional_wake_relaxation : bool, optional
        Asks for one additional wake relaxation iteration.
    reynolds_averaged_drag : bool, optional
        Switches the Reynolds-averaged (flat plate) boundary layer
        calculations.
    solver_stabilization : float, optional
        Stabilization strength. A preset that gates it with a separate
        ENABLE/DISABLE key resolves the pair before it arrives here:
        disabled means None, not zero.
    laminar_separation : bool, optional
        Switches laminar boundary layer separation.
    kutta_joukowski_lift : bool, optional
        Computes the inviscid lift by the Kutta-Joukowski theorem, from
        the bound circulation, instead of integrating the surface
        pressure.
    aeroelastic_rbf_type : str, optional
        The radial basis function of the aeroelastic mesh morphing.
    print_rotor_induced_velocities : bool, optional
        Prints the rotor-induced velocities to the log at every time
        step of an unsteady run.
    adaptive_field_grid_refinement : bool, optional
        Refines the field-source grid where the solution needs it; the
        manual marks it transonic only.
    rotor_induced_velocity_blending : float, optional
        Blending factor for wake stabilization, dimensionless, between
        0 and 1.
    wake_numerical_relaxation : float, optional
        Relaxation factor applied to the wake between iterations,
        dimensionless, between 0 and 1.
    wake_relaxation : bool, optional
        Relaxes the wake geometry between solver iterations.
    wake_decay_constant_per_m : float, optional
        Rate at which wake vorticity decays with distance, per metre.
    wake_streamwise_agglomeration : bool, optional
        Agglomerates wake filament edges along the streamwise direction,
        so the solver carries fewer wake elements.
    jet_wake_decay_normalized_length : float, optional
        Distance at which a jet wake decays to a tenth of its strength,
        in jet wake diameters.
    jet_wake_filaments_grid_induction : bool, optional
        Whether the jet wake filaments induce velocity on the mesh.
    adverse_gradient_boundary_layer : bool, optional
        Switches the adverse-pressure-gradient treatment of the
        boundary-layer model.
    vortex_ring_normalization : bool, optional
        Normalizes the vortex-ring strengths on the wake panels.
    wake_termination_revolutions : float, optional
        Wake termination stated in revolutions, negative counting
        backwards from the end of the run. Converted to time steps by
        the rotor builder, which is the only layer that knows how many
        steps a revolution is.
    wake_termination_steps : int, optional
        Wake termination stated in time steps, negative counting
        backwards from the end of the run, for a run type with a clock
        and no rotor.
    wake_termination_length : float, optional
        Wake termination stated as a length of wake in rotor radii (FR-321),
        converted by the rotor builder into time steps from the axial
        convection speed, the rotor speed and the step angle. A rotor row
        stating no termination keeps 4.0. At most one of this key and the
        two above reaches a row (FR-322).
    wake_termination_thrust_n : float, optional
        The rotor thrust in newtons whose momentum-theory induced velocity
        convects the wake where it exceeds the free-stream speed (FR-323).
    wake_termination_revolutions_cap : float, optional
        A revolution count the steps converted from a length never exceed
        (FR-323).
    wake_termination_x : float or 'DEFAULT', optional
        The X of the solver's wake end plane in metres in the simulation's
        reference frame, the ``wake_termination_x`` argument of
        ``INITIALIZE_SOLVER`` (FR-324); unstated writes ``DEFAULT``.
    symmetry_loads : bool, optional
        Whether the reported loads are the meshed half's or sector's or
        the whole model's; a row's ``SYMMETRY_LOADS`` column wins over it.
    significant_digits : int, optional
        How many decimals the solver prints in every export.
    reference_velocity_m_per_s : float, optional
        The velocity the coefficients are normalised on, in m/s; unstated,
        the free-stream velocity.
    vorticity_drag_families : list of str, optional
        The families whose induced drag comes from vorticity integration,
        by family name.
    axial_separation_families : list of str, optional
        The families on the axial flow separation list, by family name.
    delete_surfaces : list of str, optional
        The surfaces removed with ``DELETE_SURFACES`` after the geometry
        opens, by name, alias or family; the inventory is renumbered after
        the removal (FR-275).
    slipstream_wake_stabilization : bool, optional
        The slipstream wake stabilization of each rotor motion the row
        creates, ``SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION`` (FR-277);
        unstated, nothing is emitted.
    load_solver_initialization : bool, optional
        Whether ``OPEN`` loads the solver initialization a saved
        simulation carries; unstated, it does not.
    analysis_families : list of str, optional
        The families that enter the loads, by family name; every other
        boundary leaves the analysis.
    load_units : str, optional
        The unit the loads table prints its forces and moments in.
    inviscid_loads : bool, optional
        Reports the loads and moments without their viscous part.
    vorticity_lift_model : bool, optional
        Computes the lift from the vorticity field rather than from the
        integrated surface pressure.
    unsteady_viscous_coupling_iteration : int, optional
        The time step at which an unsteady run switches the viscous
        coupling on.

    Notes
    -----
    The toggles accept the solver's own vocabulary as well as Python
    booleans: ``viscous_coupling = 'DISABLE'`` in a settings file means
    False, the same as ``viscous_coupling = false``. A settings preset
    carried over from the solver speaks ENABLE and DISABLE, and a
    preset is often mixed (one flag in each vocabulary), so the model
    reads both and stores the bool
    (:func:`pyflightstream.script.toggles.resolve_toggle`). Any other
    string is refused by name.

    Examples
    --------
    >>> settings = SolverSettings(iterations=800, forced_iterations="ENABLE")
    >>> settings.iterations, settings.forced_iterations, settings.convergence
    (800, True, 1e-05)
    """

    # PYFS-016. Every bound below was measured ACCEPTED before it was
    # written: zero and negative iterations, a zero and a negative
    # timeout, a zero and a NaN convergence threshold, zero threads.
    # None of those describes a run that can happen, and the NaN
    # threshold is the one that does not even fail loudly: it compares
    # false against every residual, so the solver burns its whole
    # iteration budget and the run is recorded as having met a target
    # it never met.
    #
    # allow_inf_nan=False stops the NaN and infinity half; the
    # per-field bounds stop the zero and negative half. Both are
    # needed, because a numeric constraint does not reject NaN on its
    # own: every comparison against NaN is false, so ge and gt pass it.
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    #: Explicit measured simulation unit, applied after geometry and before frames.
    simulation_length_unit: Literal["METER", "MILLIMETER"] | None = None
    #: Vertex merge distance in metres; converted to the selected simulation unit.
    vertex_merge_tolerance_m: float | None = Field(default=None, ge=0)
    #: Geometric-edge bluntness threshold before detection; current command since 26.122.
    geometric_edge_bluntness_angle_deg: float | None = Field(default=None, ge=45, le=179)
    iterations: int = Field(default=500, ge=1)
    convergence: float = Field(default=1e-5, gt=0.0)
    forced_iterations: SolverToggle | None = None
    boundary_layer: str | None = None
    viscous_coupling: SolverToggle | None = None
    #: Boundary labels or 1-based indices; empty explicitly clears the selection.
    viscous_excluded: list[int | str] | None = None
    #: Equivalent sand-grain roughness in nanometres (SET_SURFACE_ROUGHNESS).
    surface_roughness: float | None = Field(default=None, ge=0)
    #: Boundary labels or indices treated as thin surfaces; all selects every boundary.
    thin_boundaries: list[int | str] | Literal["all"] | None = None
    #: Legacy bulk-separation assignment, with model type and characteristic diameter.
    bulk_separation: BulkSeparation | None = None
    #: Trailing-edge airfoil separation, with optional per-assignment Valarezo criterion.
    airfoil_separation: list[AirfoilSeparation] | None = None
    #: Axial vortex separation assignments, with body axis, frame and diameter.
    axial_vortex_separation: list[AxialVortexSeparation] | None = None
    #: Cylindrical bulk separation assignments and characteristic diameters.
    cylindrical_bulk_separation: list[CylindricalBulkSeparation] | None = None
    #: Stratford bulk separation assignments on selected boundaries.
    stratford_bulk_separation: list[StratfordBulkSeparation] | None = None
    #: Separation assignment index to delete, or all for every assignment.
    delete_separations: int | Literal["all"] | None = None
    #: Legacy global Valarezo maximum-lift criterion; newer builds use airfoil assignments.
    valarezo_criterion: SolverToggle | None = None
    #: Legacy boundary selection for the Valarezo separation criterion.
    valarezo_separation_boundaries: list[int | str] | Literal["all"] | None = None
    #: Boundary labels or indices carrying crossflow separation.
    crossflow_separation_boundaries: list[int | str] | Literal["all"] | None = None
    #: Crossflow characteristic diameter in simulation length units.
    crossflow_separation_diameter: float | None = Field(default=None, gt=0)
    #: Legacy mean diameter for the crossflow pressure criterion, in simulation units.
    crossflow_separation_mean_diameter: float | None = Field(default=None, gt=0)
    #: Whether the selected crossflow model assumes an axisymmetric body.
    crossflow_separation_axisymmetric: SolverToggle | None = None
    #: Refused in 0.29.0 on every build: SET_SOLVER_MODEL, the flow-model command
    #: only the 25.000 edition documents, is removed from 25.100 onward, and no
    #: workflow can write its INITIALIZE_SOLVER for 25.000.
    #:
    #: Distinct from :attr:`solver_model`, the INITIALIZE_SOLVER argument that
    #: replaced it. Kept so a setup stating it is refused rather than read as a
    #: setting a run applied: by the build guard naming the command on 25.100
    #: onward, and on 25.000 by the INITIALIZE_SOLVER helper, as every case is.
    legacy_solver_model: str | None = None
    #: Explicit BC overrides, emitted before runtime/init settings. RELAXED remains deferred.
    trailing_edge_types: (
        dict[Annotated[int, Field(ge=1)], Literal["STANDARD", "JET_OUTFLOW", "VORTEX_SHEDDING"]]
        | None
    ) = None
    #: One-based trailing-edge indices whose wake nodes are disabled.
    disabled_wake_trailing_edges: list[Annotated[int, Field(ge=1)]] | None = None
    #: Boundary labels or indices on which leading-edge wakes are detected.
    leading_edge_wake_boundaries: list[int | str] | None = Field(default=None, min_length=1)
    #: Explicitly mark wake termination nodes; no implicit detection is requested.
    mark_wake_termination_nodes: Literal[True] | None = None
    #: Ports selected by setup; surface identity is bound from the geometry and values from MATRIX.
    ports: tuple[PortBoundary, ...] = ()
    #: Apply the sidecar trailing-edge definition; None adapts the published legacy declaration.
    apply_trailing_edges: bool | None = None
    #: Apply the sidecar wake-termination definition; false never clears saved wake nodes.
    apply_wake_termination: bool | None = None
    #: Apply base-region detection/actions; false never clears saved base regions.
    apply_base_regions: bool | None = None
    #: Existing inlet indices to unmark, in the exact declared order.
    delete_inlets: list[Annotated[int, Field(ge=1)]] | None = Field(default=None, min_length=1)
    #: Existing outlet indices to unmark, in the exact declared order.
    delete_outlets: list[Annotated[int, Field(ge=1)]] | None = Field(default=None, min_length=1)
    #: Boundary labels/indices for proximity checking before solver initialization.
    proximal_boundaries: list[int | str] | Literal["all"] | None = Field(default=None, min_length=1)
    #: Explicitly discard saved initialization before creating the new one; no solution-clear alias.
    remove_initialization: Literal[True] | None = None
    #: Explicit named actuator actions after disc creation; omitted never clears saved discs.
    actuator_operations: list[ActuatorOperation] | None = Field(default=None, min_length=1)
    #: Ordered base-region actions after detection and before solver initialization.
    base_region_operations: list[BaseRegionOperation] | None = Field(default=None, min_length=1)
    #: Detection angle in degrees; emitted before automatic or named-boundary base detection.
    base_region_bending_angle_deg: float | None = Field(default=None, ge=0, le=90)
    #: Existing transition-trip indices to delete, in the exact declared order.
    delete_transition_trips: list[Annotated[int, Field(ge=1)]] | None = Field(
        default=None, min_length=1
    )
    #: Clear the induced-drag selection in steady analysis; conflicts with an explicit family list.
    clear_vorticity_drag_boundaries: Literal[True] | None = None

    @model_validator(mode="after")
    def _clear_drag_selection_is_unambiguous(self) -> SolverSettings:
        if self.clear_vorticity_drag_boundaries and self.vorticity_drag_families is not None:
            raise ValueError(
                "clear_vorticity_drag_boundaries cannot be combined with vorticity_drag_families"
            )
        return self

    #: Refused in 0.29.0 on every build: SONIC_VELOCITY, a legacy explicit speed
    #: of sound in metres per second, has no recorded evidence on any registered
    #: build, and 26.101 onward removed it (the solver warns and ignores it).
    #:
    #: The sound speed follows from the resolved temperature and specific-heat
    #: ratio. Kept so a setup stating it is refused by the build guard, naming the
    #: command, rather than read as a setting a run applied; with
    #: ``freestream_input = "mach"`` a differing value is refused before that.
    sonic_velocity_m_per_s: float | None = Field(default=None, gt=0)
    #: Legacy PHYSICS automatic trailing-edge detection; state with physics_auto_wake_nodes.
    physics_auto_trailing_edges: bool | None = None
    #: Legacy PHYSICS wake-node detection; state with physics_auto_trailing_edges.
    physics_auto_wake_nodes: bool | None = None
    max_threads: int | None = Field(default=None, ge=1)
    timeout_s: float | None = Field(default=None, gt=0.0)
    #: FR-98: how much of a row's WALLTIME to leave for the exports, in
    #: seconds. Twenty minutes when a setup states none.
    #:
    #: IT IS THE SETUP'S AND NOT THE ROW'S, because how long the exports
    #: take is the same question on every platform and does not vary with
    #: the row, while a wall clock does. This model FORBIDS EXTRAS, so
    #: until the field existed a setup stating it was REFUSED by name and
    #: every run was locked to the default: a documented override nobody
    #: could exercise, which is a claim the tree did not do. Found by the
    #: independent Codex review of `main`, 2026-09-13 (GEO-047-C09).
    #:
    #: IT EMITS NOTHING, which is the one field of this block that does
    #: not, and the reason is stated rather than left as an exception: it
    #: is read by the wall-clock program the run stage writes beside the
    #: script, not by a solver command.
    walltime_margin_s: float | None = Field(default=None, gt=0.0)

    # --- the settings a preset carries and nothing used to read ------
    #
    # EVERY FIELD BELOW HAS AN EMITTER, and that is the rule this block
    # is held to rather than a coincidence of the first version. Ten of
    # them are keyword arguments of
    # `pyflightstream.script.helpers.solver_settings` and two are
    # arguments of `initialize_solver`; a setting a preset can state and
    # no helper can emit does NOT get a field here, because a field
    # whose value never reaches a script is a promise the file cannot
    # keep. Those stay declared as recorded-only in the preset resolver,
    # where the reason is written beside the key.
    #
    # They are all optional and all default to None, which is what keeps
    # every campaign written before this release emitting exactly the
    # lines it emitted before: a setting nobody states is a setting
    # nobody emits, and the solver's own default stands.
    solver_model: str | None = None
    wall_collision_avoidance: SolverToggle | None = None
    convergence_iterations: int | None = Field(default=None, ge=1)
    minimum_cp: float | None = None
    farfield_layers: int | None = Field(default=None, ge=1, le=5)
    mesh_induced_wake_velocity: SolverToggle | None = None
    unsteady_pressure_and_kutta: SolverToggle | None = None
    wake_on_wake_induction: SolverToggle | None = None
    additional_wake_relaxation: SolverToggle | None = None
    reynolds_averaged_drag: SolverToggle | None = None
    solver_stabilization: float | None = Field(default=None, ge=0.0)
    #: Optional advanced settings, using the existing solver helper keywords.
    #: None emits nothing; the command database validates each stated value
    #: against the run's build before emission.
    laminar_separation: SolverToggle | None = None
    kutta_joukowski_lift: SolverToggle | None = None
    aeroelastic_rbf_type: str | None = None
    print_rotor_induced_velocities: SolverToggle | None = None
    adaptive_field_grid_refinement: SolverToggle | None = None
    rotor_induced_velocity_blending: float | None = None
    wake_numerical_relaxation: float | None = None
    wake_relaxation: SolverToggle | None = None
    wake_decay_constant_per_m: float | None = None
    wake_streamwise_agglomeration: SolverToggle | None = None
    jet_wake_decay_normalized_length: float | None = None
    jet_wake_filaments_grid_induction: SolverToggle | None = None
    adverse_gradient_boundary_layer: SolverToggle | None = None
    vortex_ring_normalization: SolverToggle | None = None
    #: Wake termination stated in REVOLUTIONS, which is the unit a rotor
    #: preset writes it in, and negative counting backwards from the end
    #: of the run. The emitter takes time STEPS, and the conversion needs
    #: the steps per revolution, which only the case's own clock knows;
    #: it is therefore done by the rotor builder and never here.
    wake_termination_revolutions: float | None = None
    #: Wake termination stated in time STEPS, the emitter's own unit, for a
    #: run type that has a clock and no rotor (PFS-2030.03.04): a
    #: revolution has no length there, so the revolutions key above is
    #: refused on it and this one is the way to say it. Negative counts
    #: backwards from the end of the run, as the solver reads it.
    wake_termination_steps: int | None = None
    #: Wake termination stated as a LENGTH of wake in rotor radii (FR-321);
    #: the rotor builder converts it, and a rotor row stating none keeps 4.0.
    wake_termination_length: float | None = Field(default=None, gt=0.0)
    #: The thrust in newtons whose induced velocity convects a length near hover (FR-323).
    wake_termination_thrust_n: float | None = Field(default=None, gt=0.0)
    #: The revolutions the steps converted from a length never exceed (FR-323).
    wake_termination_revolutions_cap: float | None = Field(default=None, gt=0.0)
    #: INITIALIZE_SOLVER's wake end plane: DEFAULT or an X in metres (FR-324).
    wake_termination_x: Annotated[
        float | Literal["DEFAULT"] | None, BeforeValidator(_an_end_plane)
    ] = None
    #: The four settings the reference scripts state and 0.10.1 did not
    #: (FR-54, PFS-2030.03.*). Each is None unless a preset states it, so a
    #: preset that says nothing emits nothing and every earlier golden holds.
    #: symmetry_loads reaches SET_ANALYSIS_SYMMETRY_LOADS AS STATED, the reference
    #: decision of 2026-09-02 (PFS-2028.05); an absent key stays silent.
    symmetry_loads: SolverToggle | None = None
    #: SET_SIGNIFICANT_DIGITS: how many decimals the solver prints in every
    #: export. The reference scripts state 7; the solver's own default prints 4.
    significant_digits: int | None = Field(default=None, ge=1)
    #: SOLVER_SET_REF_VELOCITY in m/s. None means the builders state the
    #: freestream velocity, which is what the coefficients are normalised
    #: on unless a preset says otherwise (PFS-2030.03.01).
    reference_velocity_m_per_s: float | None = Field(default=None, gt=0.0)
    #: Choose SOLVER_SET_VELOCITY (default) or SOLVER_SET_MACH_NUMBER from the same
    #: resolved flight condition; Mach requires consistent fluid and gas properties.
    freestream_input: Literal["velocity", "mach"] = "velocity"
    #: Dimensionless reference Mach for coefficient normalization; replaces the velocity choice.
    reference_mach: float | None = Field(default=None, gt=0.0, allow_inf_nan=False)
    #: Explicitly reset reference velocity to follow freestream; no implicit reset when absent.
    disable_reference_velocity: Literal[True] | None = None

    @model_validator(mode="after")
    def _one_reference_normalization(self) -> SolverSettings:
        choices = (
            self.reference_velocity_m_per_s,
            self.reference_mach,
            self.disable_reference_velocity,
        )
        if sum(value is not None for value in choices) > 1:
            raise ValueError(
                "choose one reference normalization: reference_velocity_m_per_s, "
                "reference_mach, or disable_reference_velocity"
            )
        return self

    #: SET_VORTICITY_DRAG_BOUNDARIES written as FAMILY NAMES; the builder
    #: resolves them through the opened geometry's inventory and leaves out
    #: the families the geometry does not carry, as the reference driver did
    #: (PFS-2030.03.03). An empty result is refused.
    vorticity_drag_families: list[str] | None = None
    #: SET_AXIAL_SEPARATION_BOUNDARIES written as FAMILY NAMES, resolved by the
    #: same rule as :attr:`vorticity_drag_families` and through the same
    #: function.
    #:
    #: IT WAS REACHABLE ONLY AS A HELPER KEYWORD NOBODY PASSED. `solver_settings`
    #: has taken `axial_separation_boundaries` since the helper was written and
    #: the campaign path never stated it, so no preset could ask for it: the
    #: API-only shape this release exists to catch, one level below the products.
    #:
    #: THE BUILD GUARD DECIDES WHETHER IT MAY RUN. The command is documented to
    #: 26.100 and no further, and RPT-018 measured it reported deprecated and
    #: then REFUSED by the 26.101 and 26.121 solvers. A row naming this key on a
    #: later build is refused where every unavailable command is refused, naming
    #: the build -- which is better than emitting a line the solver rejects
    #: mid-run, after the seat is spent.
    axial_separation_families: list[str] | None = None
    #: The surfaces the package removes after opening the geometry (FR-275),
    #: named by name, alias or family and never by index; the surface
    #: inventory is renumbered as the solver renumbers (probe D1, 26.124).
    delete_surfaces: list[str] | None = None
    #: The slipstream wake stabilization of each rotor motion (FR-277); None
    #: emits nothing, True is ENABLE and False is DISABLE (probe W1, 26.124).
    slipstream_wake_stabilization: SolverToggle | None = None
    #: The LOAD_SOLVER_INITIALIZATION argument of OPEN. None means DISABLE,
    #: which is what the reference scripts wrote on every open: a saved simulation
    #: may carry an initialised solver, and loading it would start the run
    #: from a state the row never declared (PFS-2030.03.01).
    load_solver_initialization: SolverToggle | None = None
    #: THE SELECTIONS OF THE LOADS ANALYSIS (G09 of 0.27.0), analysis-phase
    #: commands the builders emit after ``START_SOLVER`` and before the exports,
    #: on a STEADY row only: set after the solve starts, a march's per-step
    #: exports would not see them (the shape RPT-064 measured for the loads
    #: frame), so a row of an unsteady run type stating one is refused. None
    #: emits nothing.
    #:
    #: SET_SOLVER_ANALYSIS_BOUNDARIES written as FAMILY NAMES, resolved like
    #: :attr:`vorticity_drag_families`: the boundaries that enter the loads, every
    #: other one leaving the analysis (SRC-003 p.351). A family the geometry does
    #: not carry is left out, and a list that resolves to none is refused.
    analysis_families: list[str] | None = None
    #: SET_LOADS_AND_MOMENTS_UNITS: the unit the loads table prints, one of the
    #: tokens the command takes on the row's build. The polar and every product
    #: read coefficients, so a point exported in another unit writes no product.
    load_units: str | None = None
    #: SET_INVISCID_LOADS: the loads and moments without their viscous part.
    inviscid_loads: SolverToggle | None = None
    #: SET_VORTICITY_LIFT_MODEL (G14 of 0.27.0): lift from the vorticity field
    #: rather than from the integrated surface pressure, stated before the
    #: solver is initialised on every run type. None emits nothing. The command
    #: database decides the builds: 26.124 answers the name as an unrecognized
    #: command (RPT-068), so a row on it is refused at plan.
    vorticity_lift_model: SolverToggle | None = None
    #: SET_UNSTEADY_VISCOUS_COUPLING_ITERATION (G14 of 0.27.0): the time step at
    #: which an unsteady run switches the viscous coupling on, stated before the
    #: solver is initialised. The unsteady run types only; documented by the
    #: 25.000, 25.100 and 26.000 editions alone, so the database refuses it on
    #: every later build, naming the build.
    unsteady_viscous_coupling_iteration: int | None = Field(default=None, ge=1)
    #: SET_ANALYSIS_MOMENTS_MODEL (FR-317): PRESSURE or VORTICITY, the moments
    #: model stated before the solve; None states the default PRESSURE, except on a
    #: row turning a rotor with vorticity drag, which states VORTICITY (FR-318).
    moments_model: MomentsModel | None = None
    #: SET_NEW_UNSTEADY_SOLVER_ACTION (FR-319): actions run after every time step
    #: of an unsteady row, after the package's own. None emits nothing.
    unsteady_solver_actions: list[UnsteadyAction] | None = Field(default=None, min_length=1)

    @field_validator("load_units")
    @classmethod
    def _a_unit_the_command_takes(cls, value: str | None) -> str | None:
        # Read from the command database, as the VTK variables are, so the list
        # a refusal prints is the one the emitter would enforce.
        if value is None:
            return None
        entry = CommandRegistry.load().commands["SET_LOADS_AND_MOMENTS_UNITS"]
        allowed = [str(token) for token in entry.args[0].values or ()]
        for token in allowed:
            if token.upper() == str(value).strip().upper():
                return token
        raise ValueError(
            f"load_units = {value!r} is not one of {', '.join(allowed)} "
            f"(SET_LOADS_AND_MOMENTS_UNITS, {entry.citation})"
        )


class FluidState(BaseModel):
    """The resolved air state a case runs at (PFS-2027.05, PFS-2025.02.05).

    Every field carries its unit in its name. It is the OUTPUT of
    resolving a flight condition, and it rides on the case so that a
    builder can emit it: the resolver lives in the workspace layer,
    which a builder cannot import, so the value travels rather than the
    computation.

    ``source`` records WHICH branch produced the density, and it is not
    decoration. A density solved to meet a Reynolds number is not a
    point in any atmosphere, deliberately, and this field is what stops
    a later reader treating it as an altitude and "fixing" it into one.

    THIS IS THE RESOLVED STATE WITHOUT ITS INPUTS, and the distinction
    matters for one claim. PFS-2027.05 says a reader can RECOMPUTE the
    resolution rather than trust it; that is true of
    ``ResolvedMatrix.conditions``, which carries the condition as
    written, the altitude and the ISA deviation, and it is NOT true of
    this object, which carries none of the three. A release review found
    the recompute claim attached to the object that cannot satisfy it.
    Concretely: a ``FluidState`` cannot tell sea level at ISA+15 from an
    altitude that happens to give the same temperature. Read the
    resolved condition when the inputs matter; read this when the state
    does.
    """

    model_config = ConfigDict(extra="forbid")

    velocity_m_per_s: float
    density_kg_m3: float
    pressure_pa: float
    temperature_k: float
    viscosity_pa_s: float
    #: Legacy explicit speed of sound, metres per second, on evidenced builds only.
    sonic_velocity_m_per_s: float
    #: The ratio of specific heats, dimensionless. Carried BESIDE the
    #: sonic velocity rather than instead of it, because the solver
    #: editions state the same physical fact two ways: the three
    #: pre-26.100 builds take a sonic velocity and the later ones take
    #: this ratio. A case that travels between builds needs both.
    #:
    #: The default is the FLOOR CONSTANT and not a literal 1.4. It read
    #: ``= 1.4`` until a release review pointed out that
    #: :class:`~pyflightstream.workspace.flight_condition.ResolvedCondition`
    #: carries a comment forbidding exactly that, in the same words for
    #: the same reason: a second literal lets the two drift the moment
    #: the floor constant moves, and the two builds would then solve
    #: different gases from one case. The resolver always supplies this
    #: value, so the default is reached only by an AUTHORED campaign,
    #: which is precisely the path with no resolver to keep it honest.
    heat_capacity_ratio: float = ISA.heat_capacity_ratio
    #: WHICH branch produced the density: ``"atmosphere"`` or
    #: ``"solved-from-reynolds"``. Required, with no default, and that
    #: is deliberate. It defaulted to ``"atmosphere"`` until a release
    #: review observed that a provenance marker defaulting to one of its
    #: two real values makes an unset state ASSERT a branch rather than
    #: record that nothing established one, on the one field whose whole
    #: job is to stop an unearned claim about provenance.
    source: str
    #: The length a stated Reynolds number was measured against, in
    #: metres. None when no Reynolds number was stated.
    reference_length_m: float | None = None


class PointState(BaseModel):
    """The flow state ONE point of a swept flight condition resolved to (0.21.0).

    A row that sweeps a flow variable -- `MACH:sweep`, `REmi:sweep`, an
    altitude -- states a DIFFERENT condition at every point, and the condition
    is resolved where the reference length lives, one layer above this one. So
    each point's resolved state travels here, keyed by the point, and
    :func:`case_at_point` puts it on the case the builder is handed. A row that
    sweeps an angle or a ratio resolves once and carries none of these.

    Attributes
    ----------
    mach, velocity, reynolds : float or None
        The three the case has fields for, at this point.
    fluid : FluidState or None
        The whole resolved state, which is what a builder emits.
    flight_condition : dict
        The condition as stated for this point: the row's cell with the swept
        key at this point's value.
    flight_condition_defaults : dict
        The pins the setup supplied at this point.
    flight_condition_defaults_from : str
        Where those pins came from, in words a reader can act on.
    """

    model_config = ConfigDict(extra="forbid")

    mach: float | None = None
    velocity: float | None = None
    reynolds: float | None = None
    fluid: FluidState | None = None
    flight_condition: dict[str, float] = Field(default_factory=dict)
    flight_condition_defaults: dict[str, float] = Field(default_factory=dict)
    flight_condition_defaults_from: str = ""


def point_state_key(point: Mapping[str, float]) -> str:
    """Return the key one point's resolved state is filed under.

    The point itself, written to ten significant figures per axis and sorted,
    so the same point read from a matrix, a plan or a record finds its state.

    Parameters
    ----------
    point : mapping of str to float
        The point's coordinates.

    Returns
    -------
    str
        ``axis=value`` for each axis, sorted by axis and joined by ``|``.

    Examples
    --------
    >>> point_state_key({"beta": 0.0, "alpha": 2.0})
    'alpha=2|beta=0'
    """
    return "|".join(f"{axis}={float(value):.10g}" for axis, value in sorted(point.items()))
