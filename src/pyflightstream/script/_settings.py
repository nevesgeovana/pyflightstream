"""The solver settings, emitted by family behind ``solver_settings`` (AD-17).

A private module of the ``script`` package since 0.34.0 (GOAL-039, work
package WP9a). :func:`pyflightstream.script.helpers.solver_settings`
keeps its signature, its defaults, its docstring and its public path, and
hands the arguments it received, unchanged, to
:func:`emit_solver_settings`, which runs the call in the three steps the
0.33.0 function ran inline:

1. every ARGUMENT refusal, on an untouched script
   (:func:`_read_arguments`): the bare labels and the boundary lists, the
   separation erase, the assignment models, the toggles, the time regime,
   the bulk model and the build it is written for, and the induced-drag
   selection, in that order, so the first refusal of a call is the one
   0.33.0 raised;
2. one emitter per family of settings, called in the order the 0.33.0
   function emitted, so the emitted lines and their order are
   byte-identical: the time regime, the runtime settings
   (:data:`RUNTIME_FAMILY`), the boundary layer
   (:data:`BOUNDARY_LAYER_FAMILY`), separation (:data:`SEPARATION_FAMILY`
   and the assignment models), convergence (:data:`CONVERGENCE_FAMILY` and
   the minimum-Cp default), and the advanced settings
   (:data:`ADVANCED_FAMILY`). A family is a table of :class:`Row`, whose
   order IS the emission order;
3. the snapshot of every flag of the three settings families
   (:func:`~pyflightstream.script.solver_setup.build_setup`), attached to
   the script.

A later setup key of the solver chapters lands as a row of its family's
table, without growing the facade.

The other helpers that set up a run moved here with it, whole and
unchanged, and are still imported from ``pyflightstream.script.helpers``,
their public path: the flow conditions (:func:`free_stream`,
:func:`fluid_fifth_property`, :func:`atmosphere`), the time regime alone
(:func:`unsteady_solver`), and the solver initialization
(:func:`initialize_solver`, which carries the wake termination plane, and
:func:`start_solver`). The deferred induced-drag selection has one home
here too: ``solver_settings`` records it and :func:`_flush_pending_vorticity`
lands it, for :func:`start_solver` and for the sweep, analysis and export
helpers that stay in ``helpers``.

Nothing here imports ``cases`` or ``workspace``, and nothing here imports
:mod:`pyflightstream.script.helpers`, which imports this module.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, NamedTuple

from pydantic import BaseModel, ValidationError

from pyflightstream.commands import CommandNotInVersionError
from pyflightstream.script import CommandArgumentError, Script
from pyflightstream.script.solver_setup import (
    LIBRARY_MINIMUM_CP,
    SEPARATION_MODELS,
    BulkSeparation,
    SolverSetup,
    build_setup,
)
from pyflightstream.script.toggles import Toggle, resolve_toggle


class Row(NamedTuple):
    """One flag of a settings family: the keyword, its command, and its form.

    ``form`` is how the keyword's value is written. ``value`` writes it as
    given, ``toggle`` writes ENABLE or DISABLE, ``flag`` writes the bare
    command when the value is true (an argument-less request), and
    ``list`` writes a boundary list: ``"all"`` as the count -1, the empty
    list as the ``erase`` command, anything else as the count and the
    index line. Every form but ``flag`` writes nothing for None.
    """

    argument: str
    command: str
    form: Literal["value", "toggle", "flag", "list"] = "value"
    erase: str = ""


#: The runtime settings and the main solver controls (SRC-003 pp.339-341).
RUNTIME_FAMILY = (
    Row("aoa", "SOLVER_SET_AOA"),
    Row("sideslip", "SOLVER_SET_SIDESLIP"),
    Row("velocity", "SOLVER_SET_VELOCITY"),
    Row("mach", "SOLVER_SET_MACH_NUMBER"),
    Row("ref_velocity", "SOLVER_SET_REF_VELOCITY"),
    Row("ref_mach", "SOLVER_SET_REF_MACH_NUMBER"),
    Row("ref_area", "SOLVER_SET_REF_AREA"),
    Row("ref_length", "SOLVER_SET_REF_LENGTH"),
    Row("iterations", "SOLVER_SET_ITERATIONS"),
    Row("convergence", "SOLVER_SET_CONVERGENCE"),
    Row("max_threads", "SET_MAX_PARALLEL_THREADS"),
    Row("forced_iterations", "SOLVER_SET_FORCED_ITERATIONS", "toggle"),
)

#: The boundary layer, viscous coupling and thin boundaries (SRC-003
#: pp.341-343). An empty list is the erase: the solver has a command for
#: it, and the count 0 with an empty index line would ask the parser to
#: read a line that carries nothing.
BOUNDARY_LAYER_FAMILY = (
    Row("boundary_layer", "SET_BOUNDARY_LAYER_TYPE"),
    Row("viscous_coupling", "SET_SOLVER_VISCOUS_COUPLING", "toggle"),
    Row(
        "viscous_excluded",
        "SET_VISCOUS_EXCLUDED_BOUNDARIES",
        "list",
        "DELETE_VISCOUS_EXCLUDED_BOUNDARIES",
    ),
    Row("surface_roughness", "SET_SURFACE_ROUGHNESS"),
    Row("thin_boundaries", "SET_THIN_BOUNDARIES", "list", "DELETE_THIN_BOUNDARIES"),
)

#: The boundary lists of the 26.100 separation family (SRC-741
#: pp.339-340), the order the snapshot and the refusals read them in.
SEPARATION_LISTS = (
    Row(
        "axial_separation_boundaries",
        "SET_AXIAL_SEPARATION_BOUNDARIES",
        "list",
        "DELETE_AXIAL_SEPARATION_BOUNDARIES",
    ),
    Row(
        "valarezo_separation_boundaries",
        "SET_VALAREZO_SEPARATION_BOUNDARIES",
        "list",
        "DELETE_VALAREZO_SEPARATION_BOUNDARIES",
    ),
    Row(
        "crossflow_separation_boundaries",
        "SET_CROSSFLOW_SEPARATION_BOUNDARIES",
        "list",
        "DELETE_CROSSFLOW_SEPARATION_BOUNDARIES",
    ),
)

#: The separation lists and the 26.100 cross-flow model; the erase and the
#: assignment models follow them (:func:`_emit_separation_models`).
SEPARATION_FAMILY = (
    *SEPARATION_LISTS,
    Row("crossflow_separation_diameter", "SET_CROSSFLOW_SEPARATION_DIAMETER"),
    Row(
        "crossflow_separation_axisymmetric",
        "SET_CROSSFLOW_SEPARATION_AXISYMMETRIC",
        "toggle",
    ),
)

#: The assignment models after the bulk model, each with its command.
ASSIGNMENT_COMMANDS = (
    ("airfoil_separation", "CREATE_AIRFOIL_SEPARATION"),
    ("axial_vortex_separation", "CREATE_AXIAL_VORTEX_SEPARATION"),
    ("cylindrical_bulk_separation", "CREATE_CYLINDRICAL_BULK_SEPARATION"),
    ("stratford_bulk_separation", "CREATE_STRATFORD_BULK_SEPARATION"),
)

#: The convergence count; the minimum-Cp limiter follows it with its
#: library default (:func:`_emit_minimum_cp`).
CONVERGENCE_FAMILY = (Row("convergence_iterations", "SET_SOLVER_CONVERGENCE_ITERATIONS"),)

#: The advanced settings (SRC-003 pp.344-346), then the commands of the
#: 26.121 edition (SRC-740) and of the three pre-26.100 editions
#: (SRC-747, SRC-749), in the order 0.33.0 emitted them.
ADVANCED_FAMILY = (
    Row("reynolds_averaged_drag", "REYNOLDS_AVERAGED_DRAG_FORCES", "toggle"),
    Row("mesh_induced_wake_velocity", "SOLVER_SET_MESH_INDUCED_WAKE_VELOCITY", "toggle"),
    Row("farfield_layers", "SOLVER_SET_FARFIELD_LAYERS"),
    Row("unsteady_pressure_and_kutta", "SOLVER_UNSTEADY_PRESSURE_AND_KUTTA", "toggle"),
    Row("wake_termination_time_steps", "SET_WAKE_TERMINATION_TIME_STEPS"),
    Row("wake_on_wake_induction", "SET_WAKE_ON_WAKE_INDUCTION", "toggle"),
    Row("additional_wake_relaxation", "ADDITIONAL_WAKE_RELAXATION_ITERATION", "toggle"),
    Row("laminar_separation", "LAMINAR_SEPARATION", "toggle"),
    Row("aeroelastic_rbf_type", "AEROELASTIC_RBF_TYPE"),
    Row("kutta_joukowski_lift", "KUTTA_JOUKOWSKI_LIFT_FORCES", "toggle"),
    Row("print_rotor_induced_velocities", "PRINT_ROTOR_INDUCED_VELOCITIES", "toggle"),
    Row("adaptive_field_grid_refinement", "SET_ADAPTIVE_FIELD_GRID_REFINEMENT", "toggle"),
    Row("rotor_induced_velocity_blending", "ROTOR_INDUCED_VELOCITY_BLENDING"),
    Row("wake_numerical_relaxation", "SET_WAKE_NUMERICAL_RELAXATION"),
    Row("jet_wake_decay_normalized_length", "SET_JET_WAKE_DECAY_NORMALIZED_LENGTH"),
    Row("jet_wake_filaments_grid_induction", "SET_JET_WAKE_FILAMENTS_GRID_INDUCTION", "toggle"),
    Row("wake_decay_constant", "SET_WAKE_DECAY_CONSTANT"),
    Row("solver_stabilization", "SOLVER_STABILIZATION"),
    Row("disable_ref_velocity", "DISABLE_SOLVER_REF_VELOCITY", "flag"),
    Row("solver_model", "SET_SOLVER_MODEL"),
    Row("valarezo_criterion", "VALAREZO_CRITERION", "toggle"),
    Row("crossflow_separation_mean_diameter", "SET_CROSSFLOW_SEPARATION_CP"),
    Row("wake_relaxation", "SET_WAKE_RELAXATION", "toggle"),
    Row("wake_streamwise_agglomeration", "SET_WAKE_STREAMWISE_AGGLOMERATION", "toggle"),
    Row(
        "adverse_gradient_boundary_layer",
        "SOLVER_SET_ADVERSE_GRADIENT_BOUNDARY_LAYER",
        "toggle",
    ),
    Row("vortex_ring_normalization", "SOLVER_VORTEX_RING_NORMALIZATION", "toggle"),
)

#: The toggles read before the first emission, in the order they are read,
#: so a value in neither vocabulary refuses on an untouched script and the
#: snapshot records booleans whichever vocabulary the caller wrote.
READ_TOGGLES = (
    "forced_iterations",
    "viscous_coupling",
    "reynolds_averaged_drag",
    "mesh_induced_wake_velocity",
    "unsteady_pressure_and_kutta",
    "wake_on_wake_induction",
    "additional_wake_relaxation",
    "crossflow_separation_axisymmetric",
    "laminar_separation",
    "kutta_joukowski_lift",
    "print_rotor_induced_velocities",
    "adaptive_field_grid_refinement",
    "jet_wake_filaments_grid_induction",
)


@dataclass(frozen=True)
class _Prepared:
    """What the argument step rendered for the emitters and the snapshot."""

    models: dict[str, list[dict[str, Any]]]
    bulk: dict[str, Any] | None
    selection: list[int] | Literal["all"] | None


# The toggle readers the curated helpers share. They live in this private
# module, which every helper of the script package may import from, rather
# than in the public `toggles` module (AD-17).


def _read(helper: str, argument: str, value: Toggle) -> bool:
    """Resolve one toggle, re-raising in the script layer's vocabulary."""
    try:
        return resolve_toggle(value, context=f"{helper}: {argument}")
    except ValueError as error:
        raise CommandArgumentError(str(error)) from error


def _optional_toggle(helper: str, argument: str, value: Toggle | None) -> bool | None:
    """Resolve an optional toggle up front, before the helper emits."""
    if value is None:
        return None
    return _read(helper, argument, value)


def _toggle(value: bool) -> str:
    """Render a resolved toggle as the solver writes it.

    Takes a bool only: every helper resolves its toggles through
    :func:`_read` or :func:`_optional_toggle` before emitting, so a
    string never reaches this function and truthiness is never the
    thing that decides a flag.
    """
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


def _as_selection(value: object) -> object:
    """Return a boundary selection as a list, leaving None and ``"all"`` alone.

    One materialisation, read by both the emission and the snapshot.
    They used to decide emptiness by two different tests over the same
    value, length on one side and equality with ``[]`` on the other, so
    an empty tuple emitted the erase and recorded the setter. A caller
    may also hand in any iterable, and an emptiness check must not
    consume it.

    Parameters
    ----------
    value : object
        A sequence of boundary indices or labels, the string ``"all"``,
        or None for a flag that was not passed.

    Returns
    -------
    object
        The same value, with a non-string sequence turned into a list.
    """
    if value is None or isinstance(value, str):
        return value
    return list(value)  # type: ignore[call-overload]


def _separation_arguments(model: object) -> dict[str, Any]:
    """Return one separation assignment as emitter keyword arguments.

    The four assignment models share a shape the database records the
    same way for each command: the fields of the model in declaration
    order, with ``boundaries`` expanded into the count-plus-index-line
    grammar. ``"all"`` becomes the count -1 and no index line, which is
    the documented way of naming every mesh boundary (SRC-003 p.341).

    Parameters
    ----------
    model : BaseModel
        One validated assignment: an
        :class:`~pyflightstream.script.solver_setup.AirfoilSeparation`,
        :class:`~pyflightstream.script.solver_setup.AxialVortexSeparation`,
        :class:`~pyflightstream.script.solver_setup.CylindricalBulkSeparation`
        or
        :class:`~pyflightstream.script.solver_setup.StratfordBulkSeparation`.

    Returns
    -------
    dict of str to object
        Keyword arguments for :meth:`~pyflightstream.script.Script.emit`.

    Raises
    ------
    CommandArgumentError
        If the assignment selects no boundary. The count-plus-index-line
        grammar would then emit the count 0 and an empty index line,
        asking the parser to read a line carrying nothing, which is the
        malformed emission the empty ``viscous_excluded`` was refused
        for. A separation model on no boundary is also not a thing the
        solver can be asked for: the model IS the assignment.
    """
    fields = model.model_dump()  # type: ignore[attr-defined]
    boundaries = fields.pop("boundaries")
    name = fields.get("name", "?")
    arguments: dict[str, Any] = {}
    for field_name, value in fields.items():
        arguments[field_name] = _toggle(value) if isinstance(value, bool) else value
    if boundaries == "all":
        arguments["num_boundaries"] = -1
    else:
        if len(boundaries) == 0:
            raise CommandArgumentError(
                f"solver_settings: the separation assignment {name!r} selects no "
                "boundary, which would emit the count 0 followed by an empty index "
                "line. Give it the boundaries it applies to, or 'all' for every mesh "
                "boundary (the -1 form of SRC-003 p.341); to create no assignment at "
                "all, leave it out of the sequence."
            )
        arguments["num_boundaries"] = len(boundaries)
        arguments["boundary_indices"] = list(boundaries)
    return arguments


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


# --- The flow conditions: the free stream and the fluid properties.


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
        stream for hover and rotor analyses), or ``CUSTOM``
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

    Raises
    ------
    CommandArgumentError
        If the arguments do not match ``kind``: CONSTANT takes none, ROTATION exactly ``frame``,
        ``axis`` and ``rpm``, CUSTOM exactly ``filetype`` and ``profile``.

    Examples
    --------
    >>> from pyflightstream.script import Script, helpers
    >>> script = Script(version="26.124")
    >>> helpers.free_stream(script)
    >>> script.render().splitlines()
    ['SET_FREESTREAM CONSTANT']
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


def fluid_fifth_property(script: Script) -> str:
    """Name the fifth ``FLUID_PROPERTIES`` argument this build takes.

    The editions state one physical fact two ways: the three pre-26.100
    builds take ``sonic_velocity`` and the later ones take
    ``specific_heat_ratio``. :func:`atmosphere` REFUSES the one its
    build does not take, which is right -- passing it would emit a
    keyword the build rejects -- but it leaves a caller holding both
    values with no way to ask which to pass without reaching into the
    script's private command view.

    So the question is answerable here, where the view belongs, and a
    caller one layer up chooses instead of guessing or catching.

    Parameters
    ----------
    script : Script
        The script whose build is asked.

    Returns
    -------
    str
        ``specific_heat_ratio`` on builds from 26.100 on, ``sonic_velocity`` before.
    """
    return (
        "specific_heat_ratio"
        if "specific_heat_ratio" in {arg.name for arg in script._view["FLUID_PROPERTIES"].args}
        else "sonic_velocity"
    )


def atmosphere(
    script: Script,
    *,
    altitude: float | None = None,
    altitude_units: str | None = None,
    density: float | None = None,
    pressure: float | None = None,
    temperature: float | None = None,
    viscosity: float | None = None,
    specific_heat_ratio: float | None = None,
    sonic_velocity: float | None = None,
) -> None:
    """Set the working fluid state (SRC-003 p.328).

    Either from a standard-atmosphere altitude (AIR_ALTITUDE) or from
    the five explicit fluid properties (FLUID_PROPERTIES); the two
    paths are mutually exclusive.

    WHICH FIVE DEPENDS ON THE BUILD, and this helper reads its script's
    version to find out rather than making the caller discover it from a
    refusal. Builds from 26.100 on derive the sonic velocity from
    temperature and specific heat ratio and take
    ``specific_heat_ratio``; the three pre-26.100 editions take
    ``sonic_velocity`` and have no specific-heat-ratio argument at all
    (SRC-749 p.286).

    Before 2026-08-10 the helper only knew the newer form, and entering
    the older grammar closed both doors at once on those builds: passing
    the five was refused by the binder for a keyword the edition does not
    have, and omitting one was refused by this helper, which quoted a
    page of a different edition at a caller who was not reading it.

    Parameters
    ----------
    script : Script
        Script under construction.
    altitude : float, optional
        Standard-atmosphere altitude, in ``altitude_units``, which is
        FEET and not the default on 25.000; see that parameter.
    altitude_units : str, optional
        ``METERS`` or ``FEET``, defaulting to ``METERS`` on the builds
        that take a units token. THE 25.000 BUILD TAKES NONE AND READS
        THE BARE NUMBER IN FEET, which its page states on the parameter
        row itself (SRC-749 p.286); the token arrives with the second
        argument at 25.100. So the same call is metres on seven builds
        and feet on one, a factor of 3.28 apart, and on that build this
        helper REQUIRES ``FEET`` rather than assuming it: a caller who
        says nothing is refused, so the boundary cannot be crossed
        silently. The default is None rather than ``METERS`` so an
        explicit pass can be told from an omission.
    density : float, optional
        Fluid density in kg/m^3.
    pressure : float, optional
        Static pressure in Pa.
    temperature : float, optional
        Static temperature in K.
    viscosity : float, optional
        Dynamic viscosity in Pa s.
    specific_heat_ratio : float, optional
        Ratio of specific heats (1.4 for air). Taken by builds from
        26.100 on; the older three have no such argument.
    sonic_velocity : float, optional
        Speed of sound in m/s. Taken by the three pre-26.100 builds,
        where it is an input rather than a derived quantity; the newer
        builds compute it from temperature and specific heat ratio and
        have no such argument.

    Raises
    ------
    CommandArgumentError
        If an altitude and fluid properties are both given, the explicit properties are incomplete
        or include the one the build does not take, or the build reads the altitude in feet and
        ``altitude_units`` is not ``FEET``.

    Examples
    --------
    >>> from pyflightstream.script import Script, helpers
    >>> script = Script(version="26.124")
    >>> helpers.atmosphere(script, altitude=1000.0)
    >>> script.render().splitlines()
    ['AIR_ALTITUDE 1000.0 METERS']
    """
    takes_ratio = "specific_heat_ratio" in {
        arg.name for arg in script._view["FLUID_PROPERTIES"].args
    }
    fifth = "specific_heat_ratio" if takes_ratio else "sonic_velocity"
    given_fifth: Any = specific_heat_ratio if takes_ratio else sonic_velocity
    unwanted = sonic_velocity if takes_ratio else specific_heat_ratio
    properties = (density, pressure, temperature, viscosity, given_fifth)

    if altitude is not None:
        if any(value is not None for value in properties) or unwanted is not None:
            raise CommandArgumentError(
                "atmosphere takes either an altitude or the five explicit fluid "
                "properties, not both: AIR_ALTITUDE already sets the whole standard "
                "atmosphere state (SRC-003 p.328)"
            )
        takes_units = "units" in {arg.name for arg in script._view["AIR_ALTITUDE"].args}
        if not takes_units:
            # THAT BUILD READS THE BARE NUMBER IN FEET and its page says
            # so on the parameter row (SRC-749 p.286). The units token
            # arrives with the second argument at 25.100, so the same
            # call means two things a factor of 3.28 apart across that
            # boundary, and neither the number nor a default can say
            # which. FEET is therefore accepted and required rather
            # than assumed: a caller who says nothing is refused, so
            # crossing the boundary cannot happen silently.
            # Normalised first. Every other token in this package is
            # matched case-insensitively, so a refusal that reads
            # altitude_units != "FEET" told a caller who asked for
            # "feet" that feet cannot be honoured, citing the page that
            # says they are.
            spelled = altitude_units.upper() if altitude_units is not None else None
            if spelled is None:
                raise CommandArgumentError(
                    f"atmosphere: FlightStream {script.version.canonical} takes "
                    "AIR_ALTITUDE with a bare value and reads it in FEET "
                    "(SRC-749 p.286), while every later build takes a units token "
                    "and this helper defaults that to METERS. Pass "
                    "altitude_units='FEET' to say you meant feet; the same call "
                    "without it means metres on the other seven builds, which is "
                    "the same altitude times 3.28"
                )
            if spelled != "FEET":
                raise CommandArgumentError(
                    f"atmosphere: FlightStream {script.version.canonical} reads "
                    f"AIR_ALTITUDE in FEET and takes no units token, so "
                    f"{altitude_units!r} cannot be emitted or honoured "
                    "(SRC-749 p.286). Convert the value, or set the fluid state "
                    "through the five explicit properties instead"
                )
            script.emit("AIR_ALTITUDE", altitude)
            return
        script.emit("AIR_ALTITUDE", altitude, altitude_units or "METERS")
        return
    if unwanted is not None:
        other = "sonic_velocity" if takes_ratio else "specific_heat_ratio"
        raise CommandArgumentError(
            f"atmosphere: FlightStream {script.version.canonical} takes {fifth} and "
            f"has no {other} argument on FLUID_PROPERTIES, so passing it would emit "
            "a keyword that build refuses. The two are the same physical fact stated "
            "the two ways the editions state it, one derived and one given"
        )
    if any(value is None for value in properties):
        raise CommandArgumentError(
            f"atmosphere without an altitude needs all five fluid properties "
            f"(density, pressure, temperature, viscosity, {fifth}) for FlightStream "
            f"{script.version.canonical}, because FLUID_PROPERTIES sets the complete "
            "fluid state"
        )
    script.emit(
        "FLUID_PROPERTIES",
        density=density,
        pressure=pressure,
        temperature=temperature,
        viscosity=viscosity,
        **{fifth: given_fifth},
    )


# --- The solver settings (SRC-003 pp.339-346).


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


def emit_solver_settings(script: Script, given: Mapping[str, Any]) -> SolverSetup:
    """Emit one ``solver_settings`` call by family and return its snapshot.

    Parameters
    ----------
    script : Script
        Script under construction.
    given : mapping of str to object
        Every keyword of :func:`pyflightstream.script.helpers.solver_settings`
        exactly as that call received it, None meaning not passed.

    Returns
    -------
    SolverSetup
        The snapshot of effective flag values and provenance, also
        attached to the script as ``script.solver_setup``.
    """
    values = dict(given)
    prepared = _read_arguments(script, values)
    _emit_time_regime(script, values)
    _emit_family(script, values, RUNTIME_FAMILY)
    _emit_family(script, values, BOUNDARY_LAYER_FAMILY)
    _emit_family(script, values, SEPARATION_FAMILY)
    _emit_separation_models(script, values, prepared)
    _emit_family(script, values, CONVERGENCE_FAMILY)
    minimum_cp_default_emitted = _emit_minimum_cp(script, values["minimum_cp"])
    _emit_family(script, values, ADVANCED_FAMILY)
    if given["vorticity_drag_boundaries"] is not None:
        script._vorticity_selection = prepared.selection
        script._pending_vorticity = prepared.selection
    passed = dict(values)
    boundary_layer, rbf_type = values["boundary_layer"], values["aeroelastic_rbf_type"]
    passed["boundary_layer"] = boundary_layer.upper() if boundary_layer is not None else None
    passed["aeroelastic_rbf_type"] = rbf_type.upper() if rbf_type is not None else None
    # The effective selection, which on a re-emission call is the one the
    # earlier call chose: the snapshot must describe the script, not just
    # this call.
    passed["vorticity_drag_boundaries"] = prepared.selection
    setup = build_setup(
        version=script.version.canonical,
        passed=passed,
        minimum_cp_default_emitted=minimum_cp_default_emitted,
        # The script's own database, never the packaged one: the snapshot
        # is a record of THIS script (PFS-2012.05).
        registry=script.registry,
    )
    script.solver_setup = setup
    return setup


def _read_arguments(script: Script, values: dict[str, Any]) -> _Prepared:
    """Run every argument refusal before the first emission, in 0.33.0's order.

    Normalizes ``values`` in place to what the emitters and the snapshot
    read: the boundary lists as lists, the separation erase, the validated
    assignment and bulk models, the toggles as booleans, the time regime
    upper-cased.
    """
    _read_boundary_lists(values)
    values["delete_separations"] = _read_delete_separations(values["delete_separations"])
    for argument, model_type in SEPARATION_MODELS.items():
        values[argument] = _read_assignments(argument, model_type, values[argument])
    for name in READ_TOGGLES:
        values[name] = _optional_toggle("solver_settings", name, values[name])
    _read_time_regime(values)
    values["bulk_separation"] = _read_bulk(values["bulk_separation"])
    # Rendering every assignment HERE, before the first emission, rather
    # than inside the emission loop. The no-boundary refusal is raised by
    # the renderer, and raising it mid-emission left the caller's script
    # holding the mode line, the scalars, the toggles and DELETE_SEPARATION
    # while the call failed. Every ARGUMENT refusal in this helper fires
    # on an untouched script, which is the property the module states
    # about its toggle reading and did not keep here. The VERSION
    # refusals still fire mid-emission, raised by `script.emit` when it
    # reaches a command the build does not carry; moving those is a
    # separate change, registered rather than claimed.
    models = {
        argument: [_separation_arguments(model) for model in values[argument]]
        for argument in SEPARATION_MODELS
    }
    bulk = values["bulk_separation"]
    rendered_bulk = _separation_arguments(bulk) if bulk is not None else None
    _refuse_bulk_form_the_build_lacks(script, rendered_bulk)
    selection = _read_vorticity_selection(script, values["vorticity_drag_boundaries"])
    return _Prepared(models=models, bulk=rendered_bulk, selection=selection)


def _read_boundary_lists(values: dict[str, Any]) -> None:
    """Refuse a bare label, then materialize every boundary list ONCE.

    The lists are read before either the emission or the snapshot reads
    them. The emitter decided emptiness by length and the snapshot by
    equality with a list literal, and the annotation is Sequence, so an
    empty TUPLE emitted the erase and recorded the setter: the manifest
    then named a command the script does not contain, which is the one
    thing the snapshot exists to prevent.
    """
    _reject_bare_label(
        "solver_settings",
        "vorticity_drag_boundaries",
        values["vorticity_drag_boundaries"],
        allows_all=True,
    )
    _reject_bare_label(
        "solver_settings", "viscous_excluded", values["viscous_excluded"], allows_all=False
    )
    _reject_bare_label(
        "solver_settings", "thin_boundaries", values["thin_boundaries"], allows_all=True
    )
    for row in SEPARATION_LISTS:
        _reject_bare_label("solver_settings", row.argument, values[row.argument], allows_all=True)
    values["viscous_excluded"] = _as_selection(values["viscous_excluded"])
    if values["thin_boundaries"] != "all":
        values["thin_boundaries"] = _as_selection(values["thin_boundaries"])
    for row in SEPARATION_LISTS:
        values[row.argument] = _as_selection(values[row.argument])


def _read_delete_separations(value: object) -> int | Literal["all"] | None:
    """Read the separation erase: a 1-based model index, or every model.

    The sentinel is read case-insensitively and the TYPE is checked before
    comparing. The first form tested ``!= "all"`` and then ``< 1``, so
    ``"ALL"`` reached the comparison and raised a bare TypeError from a
    helper whose every other refusal is didactic; the same happened for
    any other string.
    """
    if value is None:
        return None
    if isinstance(value, str):
        if value.lower() != "all":
            raise CommandArgumentError(
                "solver_settings: delete_separations takes the 1-based index of one "
                f"separation model or the string 'all', got {value!r}; "
                "the manual's -1 form for every model is spelled 'all' here "
                "(SRC-003 p.342)"
            )
        return "all"
    if not isinstance(value, int) or isinstance(value, bool):
        # The first repair split str from EVERYTHING ELSE and let the
        # rest fall into a `< 1` comparison, so a list raised
        # "'<' not supported between instances of 'list' and 'int'".
        # bool is an int in Python and is not an index, so it is
        # named here rather than accepted as 1 or refused as 0.
        raise CommandArgumentError(
            "solver_settings: delete_separations takes the 1-based index of one "
            f"separation model or the string 'all', got {type(value).__name__} "
            f"{value!r}. The solver deletes one model by index or every "
            "model at once; there is no multi-index form (SRC-003 p.342)"
        )
    if value < 1:
        raise CommandArgumentError(
            "solver_settings: delete_separations takes the 1-based index of one "
            f"separation model or the string 'all', got {value!r}; the "
            "solver numbers the models in creation order, and the manual's -1 form "
            "for every model is spelled 'all' here (SRC-003 p.342)"
        )
    return value


def _read_assignments(argument: str, model_type: Any, given: Any) -> list[Any]:
    """Validate one keyword of assignment models; None reads as no model."""
    if given is None:
        return []
    _reject_bare_label("solver_settings", argument, given, allows_all=False)
    if isinstance(given, BaseModel | Mapping):
        # One assignment, not a sequence of them. `bulk_separation`
        # takes a single model, so a caller carrying that habit
        # across wrote it here and met `object of type
        # CylindricalBulkSeparation has no len()`, a raw TypeError
        # out of the emptiness check below.
        given = [given]
    if len(given) == 0:
        # The empty sequence is the erase for the boundary-list
        # keywords of this same call, so accepting it here as a
        # silent no-op invites a caller to write it meaning the
        # opposite. The solver has no per-type erase: DELETE_SEPARATION
        # removes by index or removes everything.
        raise CommandArgumentError(
            f"solver_settings: {argument}=[] is an empty sequence of assignment "
            "models, which emits nothing. It is not the erase, unlike the empty "
            "sequence of a boundary-list keyword in this same call: the solver "
            "deletes separation models by index or all at once "
            "(DELETE_SEPARATION, SRC-003 p.342), so pass delete_separations='all' "
            f"or an index. Omit {argument} to leave the models as the script found "
            "them."
        )
    try:
        return [model_type.model_validate(item) for item in given]
    except ValidationError as error:
        fields = ", ".join(model_type.model_fields)
        raise CommandArgumentError(
            f"solver_settings: {argument} takes a sequence of "
            f"{model_type.__name__} ({fields}): {error}"
        ) from error


def _read_time_regime(values: dict[str, Any]) -> None:
    """Refuse a regime the solver lacks or unsteady arguments it does not match."""
    mode = values["mode"]
    upper_mode = mode.upper() if mode is not None else None
    if upper_mode is not None and upper_mode not in ("STEADY", "UNSTEADY"):
        raise CommandArgumentError(
            f"solver_settings mode takes STEADY or UNSTEADY, got {mode!r}: the solver "
            "time regime is one of the two (SRC-003 p.341)"
        )
    time_iterations, delta_time = values["time_iterations"], values["delta_time"]
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
    values["mode"] = upper_mode


def _read_bulk(bulk_separation: object) -> BulkSeparation | None:
    """Validate the one bulk separation model, if one was passed."""
    if bulk_separation is None:
        return None
    try:
        return BulkSeparation.model_validate(bulk_separation)
    except ValidationError as error:
        raise CommandArgumentError(
            "solver_settings: bulk_separation takes a BulkSeparation (name, "
            f"separation_type, diameter, boundaries; SRC-003 p.342): {error}"
        ) from error


def _refuse_bulk_form_the_build_lacks(script: Script, rendered: dict[str, Any] | None) -> None:
    """Refuse the four-argument bulk model on a build that documents three.

    The 26.101 grammar drops SEPARATION_TYPE (SRC-725 p.341) and
    BulkSeparation requires it, so the model cannot express that form.
    Refused HERE, naming the version and its own manual page: the binder's
    generic message says "CREATE_BULK_SEPARATION has no argument
    'separation_type'", which names an argument the caller never typed and
    cites the 26.120 page to somebody whose grammar is documented
    elsewhere.
    """
    if rendered is None or "separation_type" not in rendered:
        return
    try:
        entry = script._view["CREATE_BULK_SEPARATION"]
    except CommandNotInVersionError:
        entry = None
    if entry is not None and not any(arg.name == "separation_type" for arg in entry.args):
        raise CommandArgumentError(
            "solver_settings: bulk_separation carries separation_type, which "
            f"FlightStream {script.version.canonical} does not take: that edition "
            "documents the three-argument form, name, count and diameter "
            "(SRC-725 p.341), and the four-argument form with CYLINDRICAL or "
            "FLAT_PLATE arrived in 26.12 (SRC-003 p.342). BulkSeparation models "
            "the four-argument form, so emit the three-argument one with "
            "Script.emit('CREATE_BULK_SEPARATION', name=..., num_boundaries=..., "
            "diameter=...). Read RPT-015 first: every documented form of this "
            "command was refused on 26.120 and 26.121."
        )


def _read_vorticity_selection(script: Script, value: Any) -> list[int] | Literal["all"] | None:
    """Resolve the induced-drag selection before any emission.

    A bad label or index then leaves the script untouched; the emission
    itself is deferred to the analysis phase. Unset on the first settings
    call means the command is never emitted and the solver default
    applies; unset on a re-emission call keeps the selection the earlier
    call chose, so a per-point re-emission neither drops it from the
    script nor from the snapshot.
    """
    if value is None:
        return script._vorticity_selection
    if value == "all":
        return "all"
    # Materialize once: a computed selection may arrive as any iterable,
    # and the emptiness check must not consume it.
    items = list(value)
    _reject_empty_selection("solver_settings", "vorticity_drag_boundaries", items)
    return [
        script.resolve_boundary(
            item, context="solver_settings: argument 'vorticity_drag_boundaries'"
        )
        for item in items
    ]


def _emit_time_regime(script: Script, values: Mapping[str, Any]) -> None:
    """Emit the time regime: steady, or unsteady with its step count and size."""
    if values["mode"] == "STEADY":
        script.emit("SET_SOLVER_STEADY")
    elif values["mode"] == "UNSTEADY":
        script.emit("SET_SOLVER_UNSTEADY", values["time_iterations"], values["delta_time"])


def _emit_family(script: Script, values: Mapping[str, Any], family: tuple[Row, ...]) -> None:
    """Emit the rows of one family that were passed, in the family's order."""
    for row in family:
        value = values[row.argument]
        if row.form == "flag":
            if value:
                script.emit(row.command)
        elif value is None:
            continue
        elif row.form == "toggle":
            script.emit(row.command, _toggle(value))
        elif row.form != "list":
            script.emit(row.command, value)
        elif value == "all":
            # -1 names every mesh boundary and takes no index line
            # (SRC-003 p.343).
            script.emit(row.command, -1)
        elif len(value) == 0:
            script.emit(row.erase)
        else:
            script.emit(row.command, len(value), list(value))


def _emit_separation_models(script: Script, values: Mapping[str, Any], prepared: _Prepared) -> None:
    """Emit the separation erase, then the bulk model, then the assignments.

    The erase precedes every create, which is what FLAG_SPECS says the
    order is for: one call can clear the models an opened simulation
    carried and then build its own on a known-empty list. It used to sit
    after CREATE_BULK_SEPARATION, so passing both keywords created the
    bulk model and deleted it, while the snapshot recorded it as emitted.
    """
    delete_separations = values["delete_separations"]
    if delete_separations is not None:
        script.emit("DELETE_SEPARATION", -1 if delete_separations == "all" else delete_separations)
    if prepared.bulk is not None:
        # Through the same renderer as the other four assignment models,
        # since 2026-08-06, so the no-boundary refusal reaches it too.
        script.emit("CREATE_BULK_SEPARATION", **prepared.bulk)
    for argument, command in ASSIGNMENT_COMMANDS:
        for arguments in prepared.models[argument]:
            script.emit(command, **arguments)


def _emit_minimum_cp(script: Script, minimum_cp: object) -> bool:
    """Emit the minimum-Cp limiter, or its library default; say if the default."""
    if minimum_cp is not None:
        script.emit("SOLVER_MINIMUM_CP", minimum_cp)
        return False
    if "SOLVER_MINIMUM_CP" in script._view:
        script.emit("SOLVER_MINIMUM_CP", LIBRARY_MINIMUM_CP)
        return True
    return False


# --- The solver initialization (SRC-003 p.337) and the solver start.


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

    Examples
    --------
    >>> from pyflightstream.script import Script, helpers
    >>> script = Script(version="26.124")
    >>> helpers.initialize_solver(script, symmetry="NONE")
    >>> helpers.start_solver(script)
    >>> script.render().splitlines()[-1]
    'START_SOLVER'
    """
    script.emit("START_SOLVER")
    _flush_pending_vorticity(script)


def initialize_solver(
    script: Script,
    *,
    solver_model: str = "INCOMPRESSIBLE",
    surfaces: Sequence[tuple[int | str, Toggle]] | Literal["all"] = "all",
    wake_termination_x: float | str = "DEFAULT",
    symmetry: str = "NONE",
    periodic_copies: int | None = None,
    wall_collision_avoidance: Toggle | None = None,
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
    surfaces : sequence of (int or str, toggle) pairs or ``"all"``
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
    wall_collision_avoidance : bool or 'ENABLE' or 'DISABLE', optional
        Applies to solver models 1 to 3.

    Raises
    ------
    CommandArgumentError
        On FlightStream 25.000, whose INITIALIZE_SOLVER this helper
        cannot express: that edition takes ten arguments, spells
        symmetry SYMMETRY_TYPE with its own token set and has no
        SOLVER_MODEL, so the defaults here would bind two names it does
        not carry. Refused at entry, before anything is emitted, and the
        message points at ``script.emit`` (SRC-749 p.298).

    Examples
    --------
    >>> from pyflightstream.script import Script, helpers
    >>> script = Script(version="26.124")
    >>> helpers.initialize_solver(script, symmetry="NONE")
    >>> script.render().splitlines()[:2]
    ['INITIALIZE_SOLVER', 'SOLVER_MODEL INCOMPRESSIBLE']
    """
    # THIS HELPER CANNOT EXPRESS THE 25.000 GRAMMAR, and says so here
    # rather than letting the binder refuse a keyword the caller never
    # typed. That edition's INITIALIZE_SOLVER takes ten arguments, has
    # no SOLVER_MODEL, spells symmetry SYMMETRY_TYPE with a different
    # token set, and requires five more this helper has no parameter
    # for. The defaults below would bind two of them, so a bare call
    # died on a name the caller never wrote (SRC-749 p.298).
    if "solver_model" not in {arg.name for arg in script._view["INITIALIZE_SOLVER"].args}:
        raise CommandArgumentError(
            f"initialize_solver cannot express the INITIALIZE_SOLVER grammar of "
            f"FlightStream {script.version.canonical}: that edition takes ten "
            "arguments, spells symmetry SYMMETRY_TYPE with its own token set, and "
            "has no SOLVER_MODEL, so this helper's parameters do not map onto it "
            "(SRC-749 p.298). Emit the command directly with "
            "script.emit('INITIALIZE_SOLVER', ...), which validates against that "
            "build's own grammar"
        )
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
    wall_collision_avoidance = _optional_toggle(
        "initialize_solver", "wall_collision_avoidance", wall_collision_avoidance
    )
    arguments: dict[str, Any] = {
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
                _read("initialize_solver", "surfaces (quad mesher flag)", quad_mesher),
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
