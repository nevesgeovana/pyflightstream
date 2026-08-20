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

Toggles: every parameter that switches a solver flag on or off takes a
Python bool or the solver's own ``ENABLE`` and ``DISABLE`` (any case),
resolved by :func:`pyflightstream.script.toggles.resolve_toggle` before
the helper emits anything; a word in neither vocabulary is refused
naming the helper and the argument. A setup carried over from the
solver speaks that vocabulary, and a bare string is truthy in Python,
so reading it is what keeps ``'DISABLE'`` from emitting ENABLE.

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

ONE PAIR HERE EMITS NOTHING, and it is stated in the module docstring
rather than only beside itself, because the sentence above says every
helper translates typed arguments into ``emit()`` calls and this is the
exception. :func:`parse_relaxed_trailing_edge` and
:class:`RelaxedTrailingEdge` read and write the relaxed trailing-edge
COMPONENT specification, a semicolon-separated field list written where
a component is defined; no command on any registered build takes its
fields, so they take no ``script`` and produce text (SRC-751 p.85).
"""

from __future__ import annotations

import math
import re
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal

from pydantic import BaseModel, ValidationError

from pyflightstream._errors import (
    PyflightstreamDeprecationWarning,
    PyflightstreamWarning,
)
from pyflightstream.commands import CommandNotInVersionError
from pyflightstream.script import (
    CommandArgumentError,
    Script,
    ScriptReferenceError,
    UnsteadyActionUse,
)
from pyflightstream.script.solver_setup import (
    LIBRARY_MINIMUM_CP,
    SEPARATION_MODELS,
    AirfoilSeparation,
    AxialVortexSeparation,
    BulkSeparation,
    CylindricalBulkSeparation,
    SolverSetup,
    StratfordBulkSeparation,
    build_setup,
    with_vorticity_selection,
)
from pyflightstream.script.toggles import Toggle, resolve_toggle


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


def _separation_arguments(model: object) -> dict[str, object]:
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
    arguments: dict[str, object] = {}
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
    """
    takes_ratio = "specific_heat_ratio" in {
        arg.name for arg in script._view["FLUID_PROPERTIES"].args
    }
    fifth = "specific_heat_ratio" if takes_ratio else "sonic_velocity"
    given_fifth = specific_heat_ratio if takes_ratio else sonic_velocity
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
    enable: Toggle = True,
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
    enable : bool or 'ENABLE' or 'DISABLE'
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
    enable = _read("actuator_disc", "enable", enable)
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
        Enables slipstream wake stabilization with this blade count,
        which is PER PROPELLER and not a total across the motion
        (SRC-003 p.333). The February 2026 build's grammar for that
        command has two arguments and no blade count at all, so this
        argument is not emittable there. Reaching it on 26.100 does not
        arise: that build has no rotary motion to stabilize, and this
        helper is refused earlier, at the motion type it cannot name.
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
    forced_iterations: Toggle | None = None,
    max_threads: int | None = None,
    boundary_layer: str | None = None,
    viscous_coupling: Toggle | None = None,
    viscous_excluded: Sequence[int | str] | None = None,
    surface_roughness: float | None = None,
    thin_boundaries: Sequence[int | str] | Literal["all"] | None = None,
    bulk_separation: BulkSeparation | Mapping | None = None,
    airfoil_separation: Sequence[AirfoilSeparation | Mapping] | None = None,
    axial_vortex_separation: Sequence[AxialVortexSeparation | Mapping] | None = None,
    cylindrical_bulk_separation: Sequence[CylindricalBulkSeparation | Mapping] | None = None,
    stratford_bulk_separation: Sequence[StratfordBulkSeparation | Mapping] | None = None,
    delete_separations: int | Literal["all"] | None = None,
    axial_separation_boundaries: Sequence[int | str] | Literal["all"] | None = None,
    valarezo_separation_boundaries: Sequence[int | str] | Literal["all"] | None = None,
    crossflow_separation_boundaries: Sequence[int | str] | Literal["all"] | None = None,
    crossflow_separation_diameter: float | None = None,
    crossflow_separation_axisymmetric: Toggle | None = None,
    laminar_separation: Toggle | None = None,
    convergence_iterations: int | None = None,
    minimum_cp: float | None = None,
    reynolds_averaged_drag: Toggle | None = None,
    mesh_induced_wake_velocity: Toggle | None = None,
    farfield_layers: int | None = None,
    unsteady_pressure_and_kutta: Toggle | None = None,
    wake_termination_time_steps: int | None = None,
    wake_on_wake_induction: Toggle | None = None,
    additional_wake_relaxation: Toggle | None = None,
    aeroelastic_rbf_type: str | None = None,
    kutta_joukowski_lift: Toggle | None = None,
    print_rotor_induced_velocities: Toggle | None = None,
    adaptive_field_grid_refinement: Toggle | None = None,
    jet_wake_filaments_grid_induction: Toggle | None = None,
    rotor_induced_velocity_blending: float | None = None,
    wake_numerical_relaxation: float | None = None,
    jet_wake_decay_normalized_length: float | None = None,
    wake_decay_constant: float | None = None,
    solver_stabilization: float | None = None,
    disable_ref_velocity: bool = False,
    solver_model: str | None = None,
    valarezo_criterion: Toggle | None = None,
    crossflow_separation_mean_diameter: float | None = None,
    wake_relaxation: Toggle | None = None,
    wake_streamwise_agglomeration: Toggle | None = None,
    adverse_gradient_boundary_layer: Toggle | None = None,
    vortex_ring_normalization: Toggle | None = None,
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
    forced_iterations : bool or 'ENABLE' or 'DISABLE', optional
        Run the full iteration count regardless of convergence.
    max_threads : int, optional
        Parallel core count.
    boundary_layer : str, optional
        ``LAMINAR``, ``TRANSITIONAL``, or ``TURBULENT``; the default
        transitional model is stated valid for chord Reynolds numbers
        between 500000 and 1500000 (SRC-003 p.203).
    viscous_coupling : bool or 'ENABLE' or 'DISABLE', optional
        Couple the semi-empirical boundary layer model to the
        potential flow solution (attached-flow viscosity only,
        SRC-003 pp.207-208).
    surface_roughness : float, optional
        Surface roughness height in NANOMETRES, which is the manual's
        own unit and unlike every other length this helper takes
        (SRC-003 p.341). Zero states a smooth surface, so there is no
        separate toggle and the value carries the choice.
    thin_boundaries : sequence of int or str, ``"all"``, or None
        Boundaries the solver treats as thin, so both faces of a surface
        are resolved, by 1-based index or declared label
        (SRC-003 p.343). Three states, and they are all distinct: None
        leaves the solver's own list untouched, ``"all"`` emits
        SET_THIN_BOUNDARIES -1 and marks every mesh boundary thin, and
        the empty sequence emits DELETE_THIN_BOUNDARIES and erases the
        list, as on ``viscous_excluded`` below. Absent from the February
        2026 build, whose separation family is the per-mechanism one.
    viscous_excluded : sequence of int or str, optional
        Boundaries excluded from viscous coupling, by 1-based index
        or declared boundary label; verified against the inventory
        declared with declare_existing(boundaries=...) when one
        exists. The empty sequence emits
        DELETE_VISCOUS_EXCLUDED_BOUNDARIES, which is the solver's own
        way of erasing the list (SRC-003 p.341); pass None, or omit the
        flag, to leave the list as the script found it.
    bulk_separation : BulkSeparation or mapping, optional
        Bulk (bluff-body) flow-separation assignment
        (CREATE_BULK_SEPARATION, SRC-003 p.342); see
        :class:`~pyflightstream.script.solver_setup.BulkSeparation`.
        Documented on 26.101 and 26.120, and usable on 26.120 and
        26.121 only. The 26.101 grammar is three arguments
        (SRC-725 p.341) and :class:`BulkSeparation` models the
        four-argument form, so this keyword is REFUSED on that build
        with the three-argument emission named as the way through.
        26.121 is a hotfix of 26.120 and inherits the record, so the
        emitter accepts it there, although that edition documents the
        split commands ``cylindrical_bulk_separation`` and
        ``stratford_bulk_separation`` instead. Read RPT-015 before relying on any of the three: it
        found every documented form of this command refused on both
        26.120 and 26.121. 26.100 has no named separation models at all.
    airfoil_separation : sequence of AirfoilSeparation or mapping, optional
        Airfoil (trailing-edge) separation assignments, one per
        CREATE_AIRFOIL_SEPARATION emission (SRC-003 p.341).
    axial_vortex_separation : sequence of AxialVortexSeparation or mapping, optional
        Axial vortex separation assignments for slender bodies
        (CREATE_AXIAL_VORTEX_SEPARATION, SRC-003 p.342).
    cylindrical_bulk_separation : sequence of CylindricalBulkSeparation or mapping, optional
        Cylindrical bulk separation assignments (SRC-740 p.345);
        documented on 26.121.
    stratford_bulk_separation : sequence of StratfordBulkSeparation or mapping, optional
        Stratford bulk separation assignments (SRC-740 p.345);
        documented on 26.121.
    delete_separations : int or 'all', optional
        Delete one separation model by its 1-based creation index, or
        every one of them with ``"all"`` (DELETE_SEPARATION,
        SRC-003 p.342). Emitted before the four assignment flags above,
        so one call can clear what an opened simulation carried and then
        build its own models on a known-empty list.
    axial_separation_boundaries : sequence of int or str, or 'all', optional
        Boundaries on the axial flow separation list of 26.100
        (SET_AXIAL_SEPARATION_BOUNDARIES, SRC-741 p.339). The empty
        sequence emits the matching DELETE. Documented for 26.100 alone
        and refused elsewhere; RPT-018 measured this command reported
        deprecated and then refused by the 26.101 and 26.121 solvers,
        and did not run it on 26.120. What the later builds want in its
        place is a judgement rather than a measurement: the solver's
        deprecation notice leaves its replacement field empty, and
        ``axial_vortex_separation`` is the assignment model closest to
        this mechanism.
    valarezo_separation_boundaries : sequence of int or str, or 'all', optional
        Boundaries on the Valarezo maximum-lift criterion list of
        26.100 (SRC-741 p.339). The empty sequence emits the erase,
        like every other boundary-list keyword. It was REFUSED for one
        day: RPT-018 measured the name SRC-741 prints for that erase as
        unrecognised by the solver, and the working spelling could not
        be recorded until an entry was allowed to rest on a probe report
        instead of a manual page. It is recorded now, so the erase is
        emitted under the name that works. Superseded from 26.101 by the
        ``valarezo_criterion`` field of
        :class:`~pyflightstream.script.solver_setup.AirfoilSeparation`.
    crossflow_separation_boundaries : sequence of int or str, or 'all', optional
        Boundaries on the cross-flow separation list of 26.100
        (SRC-741 pp.339-340). The empty sequence emits the matching
        DELETE.
    crossflow_separation_diameter : float, optional
        Maximum diameter of the body carrying the 26.100 cross-flow
        separation model, in simulation length units (SRC-741 p.339).
        One diameter applies to the whole list, unlike the later named
        models, which carry a diameter per assignment.
    crossflow_separation_axisymmetric : bool or 'ENABLE' or 'DISABLE', optional
        Axisymmetric vortex shedding for the 26.100 cross-flow
        separation model (SRC-741 p.340).
    laminar_separation : bool or 'ENABLE' or 'DISABLE', optional
        Laminar boundary layer separation (SRC-003 p.345); the one
        member of the separation family documented unchanged across the
        four 26.1x editions. It carries no row for the three pre-26.100
        builds, so it is refused there, and the phrase used to read "all
        four editions" while eight are registered.
    convergence_iterations : int, optional
        Iterations the solver must stay below the convergence
        threshold before convergence is declared (SRC-003 p.344).
    minimum_cp : float, optional
        Lower limiter on the pressure coefficient, dimensionless
        (SRC-003 p.345); see the library-default note above.
    reynolds_averaged_drag : bool or 'ENABLE' or 'DISABLE', optional
        Toggle the Reynolds-averaged (flat plate) boundary layer
        calculations (SRC-003 p.344).
    mesh_induced_wake_velocity : bool or 'ENABLE' or 'DISABLE', optional
        Toggle the mesh-induced wake velocity computation
        (SRC-003 p.344).
    farfield_layers : int, optional
        Far-field agglomeration layer count, integer between 1 and 5;
        the solver default is 3 (SRC-003 p.344).
    unsteady_pressure_and_kutta : bool or 'ENABLE' or 'DISABLE', optional
        Toggle the unsteady Bernoulli and Kutta terms of the unsteady
        solver (SRC-003 p.344).
    wake_termination_time_steps : int, optional
        Time steps after which a fully faded wake vortex filament edge
        is removed (SRC-003 p.344).
    wake_on_wake_induction : bool or 'ENABLE' or 'DISABLE', optional
        Toggle the wake-on-wake induced velocity computation
        (SRC-003 pp.344-345).
    additional_wake_relaxation : bool or 'ENABLE' or 'DISABLE', optional
        Perform one additional wake relaxation iteration
        (SRC-003 p.345).
    aeroelastic_rbf_type : str, optional
        RBF mesh morphing algorithm of the aeroelastic coupling:
        ``WENDLAND_C2``, ``GAUSSIAN``, ``THIN_PLATE_SPLINE``,
        ``MULTI_QUADRATIC``, or ``INV_MULTI_QUADRATIC``
        (SRC-003 p.345).
    kutta_joukowski_lift : bool or 'ENABLE' or 'DISABLE', optional
        Compute the inviscid lift from the bound circulation by the
        Kutta-Joukowski theorem instead of by integrating the surface
        pressure. Changes a reported coefficient, not the flow field
        (SRC-003 p.344).
    print_rotor_induced_velocities : bool or 'ENABLE' or 'DISABLE', optional
        Write the rotor-induced velocities to the log at every time step
        of an unsteady run. A diagnostic whose output volume is
        unbounded on a long run (SRC-003 p.345).
    adaptive_field_grid_refinement : bool or 'ENABLE' or 'DISABLE', optional
        Refine the field-source grid where the solution needs it. The
        manual marks this transonic only, so on a subsonic case it has
        nothing to act on (SRC-003 p.345).
    jet_wake_filaments_grid_induction : bool or 'ENABLE' or 'DISABLE', optional
        Let the jet wake filaments induce velocity on the mesh
        (SRC-003 p.346). NOT AVAILABLE ON 26.121, where passing this
        raises rather than emitting: the build does not recognise the
        command, measured against the solver on 2026-08-08 (RPT-021).
        Documented by the 26.101 and 26.120 editions and by neither
        neighbour.
    rotor_induced_velocity_blending : float, optional
        Blending factor for wake stabilization, dimensionless, between 0
        and 1, solver default 0.25. Not available on 26.100
        (SRC-003 p.345).
    wake_numerical_relaxation : float, optional
        Relaxation factor applied to the wake between iterations,
        dimensionless, between 0 and 1, solver default 0.15. Lowering it
        steadies a wake that will not settle, at the cost of iterations.
        Not available on 26.100 (SRC-003 p.346).
    jet_wake_decay_normalized_length : float, optional
        Distance at which a jet wake decays to a tenth of its initial
        strength, in MULTIPLES OF THE JET WAKE DIAMETER rather than in
        length units. Solver default 100.0, minimum 1.0. Not available
        on 26.100 (SRC-003 p.346).
    solver_stabilization : float, optional
        Maximum level of stabilization applied to the main convergence,
        dimensionless, from 0 to 1. The manual states that 0 is the same
        as disabling it, so this is a strength and not a switch, and it
        takes intermediate values. Not available on 26.100
        (SRC-003 p.346).
    disable_ref_velocity : bool, default False
        Make the solver reference velocity track the free-stream
        velocity instead of holding what `ref_velocity` last set. The
        command takes no argument, so False is the ABSENCE of the
        request rather than a way of asking for the opposite: the solver
        has no way to be told not to do this. Documented by the 26.121
        edition alone (SRC-740 p.342).
    wake_decay_constant : float, optional
        Rate at which wake vorticity decays with distance, in units of
        1/m. The manual gives it as 19.1 divided by a characteristic
        length in METRES, so the unit is derived and is printed nowhere;
        a value computed with the length scale in other units gives a
        wake that decays orders of magnitude too fast or not at all, and
        the number itself does not reveal which. The characteristic
        length is the wing semi-span or largest fin for steady state,
        the blade radius for a rotor or propeller, and the larger of the
        two where both are present. Documented by the 26.121 edition
        alone (SRC-740 p.346).
    solver_model : str, optional
        Flow model the solver runs, one of INCOMPRESSIBLE, SUBSONIC,
        TRANSONIC and LOW_ORDER_SUPERSONIC. Documented by the 25.000
        edition alone (SRC-749 p.302), which is the last one to carry it
        as a command: the 25.100 edition drops the command and gives
        INITIALIZE_SOLVER a SOLVER_MODEL argument in the same release.
        On any build from 25.100 on, set the model there instead.
    valarezo_criterion : bool or 'ENABLE' or 'DISABLE', optional
        Enable the Valarezo pressure-difference criterion for predicting
        the onset of separation. Documented by the three pre-26.100
        editions (SRC-747 p.316) and by none after them.
    crossflow_separation_mean_diameter : float, optional
        Mean diameter of the body the cross-flow separation model
        applies to, strictly positive, in the simulation length units.
        The model needs it because the critical pressure coefficient it
        uses depends on the cross-sectional scale.

        NAMED FOR THE QUANTITY AND NOT FOR THE COMMAND, unlike its
        siblings, and deliberately: the vendor spells the command
        SET_CROSSFLOW_SEPARATION_CP, so mirroring it would put a
        keyword reading `_cp` on an argument the database itself calls
        `mean_diameter`, one screen from `minimum_cp`, which really is a
        pressure coefficient. It shipped as `crossflow_separation_cp`
        in no release. Its 26.100 counterpart is
        `crossflow_separation_diameter`, the same physical quantity
        under a command the vendor named after it. Documented by the
        three pre-26.100 editions (SRC-747 p.316).
    wake_relaxation : bool or 'ENABLE' or 'DISABLE', optional
        Enable relaxation of the wake geometry between solver
        iterations, which damps the wake movement and helps a case that
        oscillates rather than converging. Documented by the three
        pre-26.100 editions (SRC-747 p.319).
    wake_streamwise_agglomeration : bool or 'ENABLE' or 'DISABLE', optional
        Enable agglomeration of wake filament edges along the streamwise
        direction, trading wake resolution for fewer wake elements.
        Documented by the three pre-26.100 editions (SRC-747 p.318).
    adverse_gradient_boundary_layer : bool or 'ENABLE' or 'DISABLE', optional
        Enable the adverse-pressure-gradient treatment in the
        boundary-layer model, which lets the layer thicken approaching
        separation instead of following the flat-plate relation
        everywhere. Documented by the three pre-26.100 editions
        (SRC-747 p.318).
    vortex_ring_normalization : bool or 'ENABLE' or 'DISABLE', optional
        Enable normalization of the vortex-ring strengths on the wake
        panels. The page gives the switch and no definition of what the
        normalization does, so nothing further is stated here.
        Documented by the three pre-26.100 editions (SRC-747 p.318).

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
    _reject_bare_label("solver_settings", "thin_boundaries", thin_boundaries, allows_all=True)
    separation_selections = {
        "axial_separation_boundaries": axial_separation_boundaries,
        "valarezo_separation_boundaries": valarezo_separation_boundaries,
        "crossflow_separation_boundaries": crossflow_separation_boundaries,
    }
    for argument, value in separation_selections.items():
        _reject_bare_label("solver_settings", argument, value, allows_all=True)
    # Materialize every boundary selection to a list ONCE, before either
    # the emission or the snapshot reads it. The emitter decided
    # emptiness by length and the snapshot by equality with a list
    # literal, and the annotation is Sequence, so an empty TUPLE emitted
    # the erase and recorded the setter: the manifest then named a
    # command the script does not contain, which is the one thing the
    # snapshot exists to prevent.
    viscous_excluded = _as_selection(viscous_excluded)
    if thin_boundaries != "all":
        thin_boundaries = _as_selection(thin_boundaries)
    separation_selections = {
        argument: _as_selection(value) for argument, value in separation_selections.items()
    }
    axial_separation_boundaries = separation_selections["axial_separation_boundaries"]
    valarezo_separation_boundaries = separation_selections["valarezo_separation_boundaries"]
    crossflow_separation_boundaries = separation_selections["crossflow_separation_boundaries"]
    if delete_separations is not None:
        # Read the sentinel case-insensitively and check the TYPE before
        # comparing. The first form tested `!= "all"` and then `< 1`, so
        # "ALL" reached the comparison and raised a bare TypeError from
        # a helper whose every other refusal is didactic; the same
        # happened for any other string.
        if isinstance(delete_separations, str):
            if delete_separations.lower() != "all":
                raise CommandArgumentError(
                    "solver_settings: delete_separations takes the 1-based index of one "
                    f"separation model or the string 'all', got {delete_separations!r}; "
                    "the manual's -1 form for every model is spelled 'all' here "
                    "(SRC-003 p.342)"
                )
            delete_separations = "all"
        elif not isinstance(delete_separations, int) or isinstance(delete_separations, bool):
            # The first repair split str from EVERYTHING ELSE and let the
            # rest fall into a `< 1` comparison, so a list raised
            # "'<' not supported between instances of 'list' and 'int'".
            # bool is an int in Python and is not an index, so it is
            # named here rather than accepted as 1 or refused as 0.
            raise CommandArgumentError(
                "solver_settings: delete_separations takes the 1-based index of one "
                f"separation model or the string 'all', got {type(delete_separations).__name__} "
                f"{delete_separations!r}. The solver deletes one model by index or every "
                "model at once; there is no multi-index form (SRC-003 p.342)"
            )
        elif delete_separations < 1:
            raise CommandArgumentError(
                "solver_settings: delete_separations takes the 1-based index of one "
                f"separation model or the string 'all', got {delete_separations!r}; the "
                "solver numbers the models in creation order, and the manual's -1 form "
                "for every model is spelled 'all' here (SRC-003 p.342)"
            )
    given_models = {
        "airfoil_separation": airfoil_separation,
        "axial_vortex_separation": axial_vortex_separation,
        "cylindrical_bulk_separation": cylindrical_bulk_separation,
        "stratford_bulk_separation": stratford_bulk_separation,
    }
    separation_models: dict[str, list[object]] = {}
    for argument, model_type in SEPARATION_MODELS.items():
        given = given_models[argument]
        if given is None:
            separation_models[argument] = []
            continue
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
            separation_models[argument] = [model_type.model_validate(item) for item in given]
        except ValidationError as error:
            fields = ", ".join(model_type.model_fields)
            raise CommandArgumentError(
                f"solver_settings: {argument} takes a sequence of "
                f"{model_type.__name__} ({fields}): {error}"
            ) from error
    # Read every toggle before the first emission, so a value in neither
    # vocabulary refuses on an untouched script, and so the snapshot
    # records booleans whichever vocabulary the caller wrote.
    toggles = {
        "forced_iterations": forced_iterations,
        "viscous_coupling": viscous_coupling,
        "reynolds_averaged_drag": reynolds_averaged_drag,
        "mesh_induced_wake_velocity": mesh_induced_wake_velocity,
        "unsteady_pressure_and_kutta": unsteady_pressure_and_kutta,
        "wake_on_wake_induction": wake_on_wake_induction,
        "additional_wake_relaxation": additional_wake_relaxation,
        "crossflow_separation_axisymmetric": crossflow_separation_axisymmetric,
        "laminar_separation": laminar_separation,
        "kutta_joukowski_lift": kutta_joukowski_lift,
        "print_rotor_induced_velocities": print_rotor_induced_velocities,
        "adaptive_field_grid_refinement": adaptive_field_grid_refinement,
        "jet_wake_filaments_grid_induction": jet_wake_filaments_grid_induction,
    }
    read = {
        name: _optional_toggle("solver_settings", name, value) for name, value in toggles.items()
    }
    forced_iterations = read["forced_iterations"]
    viscous_coupling = read["viscous_coupling"]
    reynolds_averaged_drag = read["reynolds_averaged_drag"]
    mesh_induced_wake_velocity = read["mesh_induced_wake_velocity"]
    unsteady_pressure_and_kutta = read["unsteady_pressure_and_kutta"]
    wake_on_wake_induction = read["wake_on_wake_induction"]
    additional_wake_relaxation = read["additional_wake_relaxation"]
    crossflow_separation_axisymmetric = read["crossflow_separation_axisymmetric"]
    kutta_joukowski_lift = read["kutta_joukowski_lift"]
    print_rotor_induced_velocities = read["print_rotor_induced_velocities"]
    adaptive_field_grid_refinement = read["adaptive_field_grid_refinement"]
    jet_wake_filaments_grid_induction = read["jet_wake_filaments_grid_induction"]
    laminar_separation = read["laminar_separation"]
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
    rendered_models: dict[str, list[dict[str, object]]] = {
        argument: [_separation_arguments(model) for model in models]
        for argument, models in separation_models.items()
    }
    rendered_bulk = _separation_arguments(bulk) if bulk is not None else None
    if rendered_bulk is not None and "separation_type" in rendered_bulk:
        # The 26.101 grammar drops SEPARATION_TYPE (SRC-725 p.341) and
        # BulkSeparation requires it, so the model cannot express that
        # form. Refuse HERE, naming the version and its own manual page:
        # the binder's generic message says "CREATE_BULK_SEPARATION has
        # no argument 'separation_type'", which names an argument the
        # caller never typed and cites the 26.120 page to somebody whose
        # grammar is documented elsewhere.
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
        if len(viscous_excluded) == 0:
            # An empty exclusion list is the erase, not a SET naming no
            # boundary: the solver has a command for it (SRC-003 p.341),
            # and emitting the count 0 with an empty index line asked the
            # parser to read a line that carries nothing.
            script.emit("DELETE_VISCOUS_EXCLUDED_BOUNDARIES")
        else:
            script.emit(
                "SET_VISCOUS_EXCLUDED_BOUNDARIES", len(viscous_excluded), list(viscous_excluded)
            )
    if surface_roughness is not None:
        script.emit("SET_SURFACE_ROUGHNESS", surface_roughness)
    if thin_boundaries is not None:
        if thin_boundaries == "all":
            # -1 marks every mesh boundary thin and takes no index line
            # (SRC-003 p.343). The helper refused this form until
            # 2026-08-07, and the refusal recommended ['all'], which then
            # failed again as an unknown label.
            script.emit("SET_THIN_BOUNDARIES", -1)
        elif len(thin_boundaries) == 0:
            # The empty list is the erase, as on viscous_excluded above.
            script.emit("DELETE_THIN_BOUNDARIES")
        else:
            script.emit("SET_THIN_BOUNDARIES", len(thin_boundaries), list(thin_boundaries))
    for selection_argument, set_command, delete_command in (
        (
            "axial_separation_boundaries",
            "SET_AXIAL_SEPARATION_BOUNDARIES",
            "DELETE_AXIAL_SEPARATION_BOUNDARIES",
        ),
        (
            "valarezo_separation_boundaries",
            "SET_VALAREZO_SEPARATION_BOUNDARIES",
            "DELETE_VALAREZO_SEPARATION_BOUNDARIES",
        ),
        (
            "crossflow_separation_boundaries",
            "SET_CROSSFLOW_SEPARATION_BOUNDARIES",
            "DELETE_CROSSFLOW_SEPARATION_BOUNDARIES",
        ),
    ):
        chosen = separation_selections[selection_argument]
        if chosen is None:
            continue
        if chosen == "all":
            script.emit(set_command, -1)
        elif len(chosen) == 0:
            script.emit(delete_command)
        else:
            script.emit(set_command, len(chosen), list(chosen))
    if crossflow_separation_diameter is not None:
        script.emit("SET_CROSSFLOW_SEPARATION_DIAMETER", crossflow_separation_diameter)
    if crossflow_separation_axisymmetric is not None:
        script.emit(
            "SET_CROSSFLOW_SEPARATION_AXISYMMETRIC", _toggle(crossflow_separation_axisymmetric)
        )
    # The erase precedes every create, which is what FLAG_SPECS says the
    # order is for: one call can clear the models an opened simulation
    # carried and then build its own on a known-empty list. It used to
    # sit after CREATE_BULK_SEPARATION, so passing both keywords created
    # the bulk model and deleted it, while the snapshot recorded it as
    # emitted.
    if delete_separations is not None:
        script.emit("DELETE_SEPARATION", -1 if delete_separations == "all" else delete_separations)
    if bulk is not None:
        # Through the same renderer as the other four assignment models,
        # since 2026-08-06. It had its own block, written before the
        # renderer existed, and so it was the one assignment keyword the
        # no-boundary refusal did not reach: an empty `boundaries` still
        # emitted the count 0 and a blank index line, which is the exact
        # malformed shape that refusal was added for, one round later
        # and one keyword over.
        script.emit("CREATE_BULK_SEPARATION", **rendered_bulk)
    for argument, command in (
        ("airfoil_separation", "CREATE_AIRFOIL_SEPARATION"),
        ("axial_vortex_separation", "CREATE_AXIAL_VORTEX_SEPARATION"),
        ("cylindrical_bulk_separation", "CREATE_CYLINDRICAL_BULK_SEPARATION"),
        ("stratford_bulk_separation", "CREATE_STRATFORD_BULK_SEPARATION"),
    ):
        for arguments in rendered_models[argument]:
            script.emit(command, **arguments)
    if convergence_iterations is not None:
        script.emit("SET_SOLVER_CONVERGENCE_ITERATIONS", convergence_iterations)
    minimum_cp_default_emitted = False
    if minimum_cp is not None:
        script.emit("SOLVER_MINIMUM_CP", minimum_cp)
    elif "SOLVER_MINIMUM_CP" in script._view:
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
    if laminar_separation is not None:
        script.emit("LAMINAR_SEPARATION", _toggle(laminar_separation))
    if aeroelastic_rbf_type is not None:
        script.emit("AEROELASTIC_RBF_TYPE", aeroelastic_rbf_type)
    if kutta_joukowski_lift is not None:
        script.emit("KUTTA_JOUKOWSKI_LIFT_FORCES", _toggle(kutta_joukowski_lift))
    if print_rotor_induced_velocities is not None:
        script.emit("PRINT_ROTOR_INDUCED_VELOCITIES", _toggle(print_rotor_induced_velocities))
    if adaptive_field_grid_refinement is not None:
        script.emit("SET_ADAPTIVE_FIELD_GRID_REFINEMENT", _toggle(adaptive_field_grid_refinement))
    if rotor_induced_velocity_blending is not None:
        script.emit("ROTOR_INDUCED_VELOCITY_BLENDING", rotor_induced_velocity_blending)
    if wake_numerical_relaxation is not None:
        script.emit("SET_WAKE_NUMERICAL_RELAXATION", wake_numerical_relaxation)
    if jet_wake_decay_normalized_length is not None:
        script.emit("SET_JET_WAKE_DECAY_NORMALIZED_LENGTH", jet_wake_decay_normalized_length)
    if jet_wake_filaments_grid_induction is not None:
        script.emit(
            "SET_JET_WAKE_FILAMENTS_GRID_INDUCTION", _toggle(jet_wake_filaments_grid_induction)
        )
    if wake_decay_constant is not None:
        script.emit("SET_WAKE_DECAY_CONSTANT", wake_decay_constant)
    if solver_stabilization is not None:
        script.emit("SOLVER_STABILIZATION", solver_stabilization)
    if disable_ref_velocity:
        script.emit("DISABLE_SOLVER_REF_VELOCITY")
    if solver_model is not None:
        script.emit("SET_SOLVER_MODEL", solver_model)
    if valarezo_criterion is not None:
        script.emit("VALAREZO_CRITERION", _toggle(valarezo_criterion))
    if crossflow_separation_mean_diameter is not None:
        script.emit("SET_CROSSFLOW_SEPARATION_CP", crossflow_separation_mean_diameter)
    if wake_relaxation is not None:
        script.emit("SET_WAKE_RELAXATION", _toggle(wake_relaxation))
    if wake_streamwise_agglomeration is not None:
        script.emit("SET_WAKE_STREAMWISE_AGGLOMERATION", _toggle(wake_streamwise_agglomeration))
    if adverse_gradient_boundary_layer is not None:
        script.emit(
            "SOLVER_SET_ADVERSE_GRADIENT_BOUNDARY_LAYER", _toggle(adverse_gradient_boundary_layer)
        )
    if vortex_ring_normalization is not None:
        script.emit("SOLVER_VORTEX_RING_NORMALIZATION", _toggle(vortex_ring_normalization))

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
        "surface_roughness": surface_roughness,
        "thin_boundaries": thin_boundaries,
        "bulk_separation": bulk,
        "airfoil_separation": separation_models["airfoil_separation"],
        "axial_vortex_separation": separation_models["axial_vortex_separation"],
        "cylindrical_bulk_separation": separation_models["cylindrical_bulk_separation"],
        "stratford_bulk_separation": separation_models["stratford_bulk_separation"],
        "delete_separations": delete_separations,
        "axial_separation_boundaries": axial_separation_boundaries,
        "valarezo_separation_boundaries": valarezo_separation_boundaries,
        "crossflow_separation_boundaries": crossflow_separation_boundaries,
        "crossflow_separation_diameter": crossflow_separation_diameter,
        "crossflow_separation_axisymmetric": crossflow_separation_axisymmetric,
        "laminar_separation": laminar_separation,
        "convergence_iterations": convergence_iterations,
        "minimum_cp": minimum_cp,
        "kutta_joukowski_lift": kutta_joukowski_lift,
        "print_rotor_induced_velocities": print_rotor_induced_velocities,
        "adaptive_field_grid_refinement": adaptive_field_grid_refinement,
        "jet_wake_filaments_grid_induction": jet_wake_filaments_grid_induction,
        "rotor_induced_velocity_blending": rotor_induced_velocity_blending,
        "wake_numerical_relaxation": wake_numerical_relaxation,
        "jet_wake_decay_normalized_length": jet_wake_decay_normalized_length,
        "wake_decay_constant": wake_decay_constant,
        "solver_stabilization": solver_stabilization,
        "disable_ref_velocity": disable_ref_velocity,
        "solver_model": solver_model,
        "valarezo_criterion": valarezo_criterion,
        "crossflow_separation_mean_diameter": crossflow_separation_mean_diameter,
        "wake_relaxation": wake_relaxation,
        "wake_streamwise_agglomeration": wake_streamwise_agglomeration,
        "adverse_gradient_boundary_layer": adverse_gradient_boundary_layer,
        "vortex_ring_normalization": vortex_ring_normalization,
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
        # The script's own database, never the packaged one: the snapshot
        # is a record of THIS script (PFS-2012.05).
        registry=script.registry,
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


def sweep(
    script: Script,
    *,
    aoa: Sequence[float] | None = None,
    beta: Sequence[float] | None = None,
    velocity_file: str | None = None,
    clear_solution: Toggle | None = None,
    ref_velocity_same: Toggle | None = None,
    post_run_script: str | None = None,
    start: Toggle = True,
    export_spreadsheet: str | None = None,
) -> None:
    """Configure and run a Sweeper Toolbox sweep (SRC-003 pp.358-360).

    Covers the CUSTOM mode only, which is a SUBSET of what the four
    sweep commands document, and the shape of the subset is an accident
    of how this chapter was first read rather than a design: the
    database and this helper were both written from the worked example
    at SRC-003 p.406, which sweeps three axes in one mode. The
    reference pages give every axis the same grammar, so what is
    missing here is the UNIFORM mode on all axes, the file form on the
    two angle axes, the inline list form on velocity, and the Mach axis
    entirely (PLN-20260806-1100).

    The database no longer has that gap, so the low-level path already
    reaches the whole grammar today::

        script.emit("SWEEPER_SET_AOA_SWEEP", "UNIFORM", [-10.0, 20.0, 1.0])

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
    clear_solution : bool or 'ENABLE' or 'DISABLE', optional
        Clear the solution between sweep runs instead of reusing it.
    ref_velocity_same : bool or 'ENABLE' or 'DISABLE', optional
        Keep the reference velocity equal to the free-stream velocity
        at every sweep point.
    post_run_script : str, optional
        Script executed after each sweep point, for example a surface
        section extraction script.
    start : bool or 'ENABLE' or 'DISABLE'
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
            "without values has nothing to run (SRC-003 pp.358-359)"
        )
    clear_solution = _optional_toggle("sweep", "clear_solution", clear_solution)
    ref_velocity_same = _optional_toggle("sweep", "ref_velocity_same", ref_velocity_same)
    start = _read("sweep", "start", start)
    if aoa is not None:
        script.emit("SWEEPER_SET_AOA_SWEEP", "CUSTOM", list(aoa))
    if beta is not None:
        script.emit("SWEEPER_SET_BETA_SWEEP", "CUSTOM", list(beta))
    if velocity_file is not None:
        # BY NAME, not positionally. The velocity command used to declare
        # `filename` as its only tail, so a path was the second positional;
        # the 2026-08-06 redraft gave all four sweep axes the manual's real
        # grammar, where the inline value list comes first and the path
        # second. A positional path bound to `values` and raised, and no
        # test covered this keyword, so the whole suite stayed green.
        script.emit("SWEEPER_SET_VELOCITY_SWEEP", "CUSTOM", filename=velocity_file)
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
    symmetry_loads: Toggle | None = None,
    load_units: str | None = None,
    boundaries: Sequence[int | str] | None = None,
    inviscid_only: Toggle | None = None,
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
    symmetry_loads : bool or 'ENABLE' or 'DISABLE', optional
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
    inviscid_only : bool or 'ENABLE' or 'DISABLE', optional
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
    symmetry_loads = _optional_toggle("analysis_setup", "symmetry_loads", symmetry_loads)
    inviscid_only = _optional_toggle("analysis_setup", "inviscid_only", inviscid_only)
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
            PyflightstreamDeprecationWarning,
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
    vtk_wake: Toggle = False,
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
    vtk_wake : bool or 'ENABLE' or 'DISABLE'
        Include the wake in the VTK variable selection.
    force_distributions : str, optional
        Path of the force distribution vectors export, all boundaries.
    """
    _reject_bare_label("export_results", "vtk_boundaries", vtk_boundaries, allows_all=True)
    vtk_wake = _read("export_results", "vtk_wake", vtk_wake)
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
                PyflightstreamWarning,
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


def export_probes(script: Script, path: str, *, update: Toggle = True) -> None:
    """Export the probe values, refreshing them first (SRC-003 pp.362-363).

    Parameters
    ----------
    script : Script
        Script under construction.
    path : str
        Export file path.
    update : bool or 'ENABLE' or 'DISABLE'
        Emit UPDATE_PROBE_POINTS first, so the export reflects the
        current solution; the manual instructs refreshing before
        exporting (SRC-003 p.362).

    Raises
    ------
    CommandArgumentError
        If this script has already exported to ``path``. The solver
        writes one file per path, so two exports to one path meant the
        second silently replaced the first; the script rendered two
        identical lines and nothing anywhere recorded that only one
        survived (PFS-2011.02).

        The message names BOTH call sites, because one naming only the
        second sends the reader to the wrong line: the one they need to
        change is usually the earlier one.

    Notes
    -----
    The register lives on the :class:`~pyflightstream.script.Script`
    rather than here, because the collision is between two CALLS and
    only the script sees both.
    """
    already = script._exported_paths.get(path)
    if already is not None:
        raise CommandArgumentError(
            f"this script already exports to {path!r}, from {already}. The solver "
            "writes one file per path, so the second export would silently replace "
            f"the first and the script would carry two identical lines. Give "
            f"export_probes a path of its own, for example one carrying the point "
            "or the survey name."
        )
    if _read("export_probes", "update", update):
        script.emit("UPDATE_PROBE_POINTS")
    script.emit("EXPORT_PROBE_POINTS", path)
    script._exported_paths[path] = "export_probes"


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


#: THE AZIMUTH DATUM, as one named table (PFS-2025.04).
#:
#: Per rotor axis, the two in-plane unit vectors that fix where azimuth
#: zero points and which way azimuth grows: the DATUM first, the
#: QUADRATURE second. They are cyclic, X to (Y, Z), Y to (Z, X) and Z to
#: (X, Y), so the datum crossed with the quadrature is the rotor axis
#: itself for all three, and every blade frame comes out right-handed
#: with its third axis along the rotation.
#:
#: IT IS A PROPOSAL AND NOT A DECISION. Which in-plane direction is
#: azimuth zero is the domain expert's call, recorded as a proposal in
#: reports/RPT-036_the-azimuth-convention-proposal_2026-08-19.md; a wrong
#: datum rotates every blade frame and every phase-locked reduction keyed
#: to blade index, and produces plausible numbers rather than a failure.
#: This table exists so that settling it is ONE edit here rather than a
#: search: nothing else in the library decides where azimuth zero is.
AZIMUTH_BASIS: dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]] = {
    "X": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    "Y": ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
    "Z": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
}

#: The four angles a first blade is allowed to sit at, in deg. The
#: placement of the other blades is arithmetic, 360/N from this one, so
#: the anchor is the one measured quantity in it, and restricting it to
#: the quadrants is the author's instruction rather than a numerical
#: convenience.
BLADE_ANCHOR_ANGLES_DEG: tuple[float, ...] = (0.0, 90.0, 180.0, 270.0)

#: The sense of rotation a propeller descriptor records, viewed from
#: behind the aircraft looking forward. Declared HERE, in the layer that
#: consumes it, and imported downward by
#: :class:`pyflightstream.workspace.inputs.PropellerReference` rather
#: than restated there: the layer rule permits the higher layer to
#: import the lower one, so a second declaration held together by a test
#: would be a second home for one vocabulary. This alias was that second
#: home for one day.
RotationSense = Literal["clockwise", "counterclockwise"]

#: How a propeller's recorded sense of rotation signs the azimuth
#: increment. Counterclockwise about the rotor axis is the
#: mathematically positive sense, so blade k sits at anchor plus k times
#: 360/N; clockwise numbers the blades the other way round the disc.
#: Which of the two a descriptor's own word means, given that the
#: descriptor states its sense as seen from behind, is the same open
#: question the datum is: see RPT-036.
ROTATION_SENSE_SIGN: dict[RotationSense, float] = {
    "counterclockwise": 1.0,
    "clockwise": -1.0,
}

#: Decimal places the emitted axis components are rounded to. A cosine of
#: 90 degrees is 6.1e-17 in binary floating point, and a script line
#: carrying that number is a script line a reader cannot check by eye.
_AXIS_DECIMALS = 12


def _clean(value: float) -> float:
    """Round one axis component and normalise a negative zero away."""
    return round(value, _AXIS_DECIMALS) + 0.0


def azimuth_basis(rotor_axis: str) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Return the in-plane datum and quadrature vectors of a rotor axis.

    The single reader of :data:`AZIMUTH_BASIS`, so the convention has one
    home and changing it is one edit.

    Parameters
    ----------
    rotor_axis : str
        Rotation axis of the rotor in the reference frame: ``X``, ``Y``
        or ``Z`` (any case).

    Returns
    -------
    tuple of tuple of float
        The unit vector azimuth zero points along, then the unit vector
        90 degrees of positive azimuth from it.

    Raises
    ------
    CommandArgumentError
        If the axis is not one of the three, naming what was passed.

    Examples
    --------
    >>> from pyflightstream.script.helpers import azimuth_basis
    >>> azimuth_basis("Z")
    ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    """
    key = rotor_axis.upper() if isinstance(rotor_axis, str) else rotor_axis
    try:
        return AZIMUTH_BASIS[key]
    except (KeyError, TypeError) as error:
        raise CommandArgumentError(
            f"blade_frames: rotor_axis is {rotor_axis!r}, and a rotor axis is one of "
            f"{', '.join(sorted(AZIMUTH_BASIS))}. The axis is what fixes the plane the "
            "blades are placed in, so there is no default to fall back on"
        ) from error


def blade_frames(
    script: Script,
    *,
    hub_origin: Sequence[float],
    rotor_axis: str,
    n_blades: int,
    blade1_azimuth_deg: float,
    rotation: RotationSense,
    names: Sequence[str] | None = None,
    labels: Sequence[str] | None = None,
) -> list[int]:
    """Create one motion-following coordinate system per blade.

    Places ``n_blades`` local frames 360/N apart around the rotor disc,
    anchored on the first blade, each with its x axis along that blade's
    radial direction and its z axis along the rotor axis, so an azimuthal
    reduction afterwards has a frame per blade to reduce in. The returned
    indices are what :func:`rotary_motion` is handed as ``moving_frames``,
    which is what binds the frames to the motion and makes them follow it.

    THE PLACEMENT IS ARITHMETIC AND NOT GEOMETRY. Nothing here reads a
    mesh and nothing computes a centroid: N blades sit 360/N apart, and
    the only measured quantity is the first blade's azimuth, which must
    be one of :data:`BLADE_ANCHOR_ANGLES_DEG`.

    Parameters
    ----------
    script : Script
        Script under construction.
    hub_origin : sequence of float
        Hub position in the reference frame, in simulation length units.
        Every blade frame shares it: the frames differ in orientation and
        not in origin, because they rotate about the same hub.
    rotor_axis : str
        Rotation axis in the reference frame, ``X``, ``Y`` or ``Z``. It
        selects the in-plane pair of :data:`AZIMUTH_BASIS`.
    n_blades : int
        Blade count, at least 1.
    blade1_azimuth_deg : float
        Azimuth of the first blade, in deg, measured from the datum of
        :func:`azimuth_basis` and positive towards the quadrature vector.
        One of :data:`BLADE_ANCHOR_ANGLES_DEG`.
    rotation : {"clockwise", "counterclockwise"}
        Sense of rotation, viewed from behind the aircraft looking
        forward, the vocabulary a propeller descriptor records in its
        ``rotation`` field. It signs the azimuth increment, so it decides
        which way round the disc the blades are numbered and nothing
        else.

        REQUIRED, with no default. It carried one on the branch that
        added this function and never in a release, so no caller is
        migrating: the default was removed before shipping because the
        refusal below says there is no safe default to guess and the
        signature was making one. A wrong sense renumbers the blades,
        raises nothing, and every phase-locked reduction keyed to blade
        index inherits it.
    names : sequence of str, optional
        Display names of the created frames, one per blade; ``Blade1`` to
        ``BladeN`` by default.
    labels : sequence of str, optional
        Labels registered in the script's entity registry, one per blade,
        so later commands can cite a blade frame by name. A frame label
        and a boundary label are different entity kinds and cannot
        collide.

    Returns
    -------
    list of int
        The created frame indices, in blade order, ready to pass to
        :func:`rotary_motion` as ``moving_frames``.

    Raises
    ------
    CommandArgumentError
        If the blade count is below one, the rotor axis is not one of the
        three, the rotation sense is not one of the two, the first
        blade's azimuth is not one of the four anchors (the measured
        angle is named), or a ``names`` or ``labels`` sequence has a
        different length from the blade count. Every one of these fires
        before anything is emitted, so a refused call leaves the script
        untouched.

    Notes
    -----
    The azimuth datum this places blades against is a PROPOSAL awaiting
    the domain expert's decision (RPT-036). A wrong datum rotates every
    blade frame together, and every phase-locked reduction keyed to blade
    index with them, and it produces plausible numbers rather than an
    error, which is why it is written down where the placement is made.

    Deleting a coordinate system renumbers the frames above it downward
    (RPT-021 section 3), and this helper creates N of them per rotor. Do
    not delete a frame between this call and the citations of the indices
    it returned.

    Examples
    --------
    >>> from pyflightstream.script import Script, helpers
    >>> script = Script(version="26.120")
    >>> frames = helpers.blade_frames(
    ...     script,
    ...     hub_origin=(1.2, 0.0, 0.0),
    ...     rotor_axis="Z",
    ...     n_blades=3,
    ...     blade1_azimuth_deg=90.0,
    ...     rotation="counterclockwise",
    ... )
    >>> frames
    [2, 3, 4]
    >>> motion = helpers.rotary_motion(
    ...     script, frame=frames[0], axis="Z", rpm=2400.0, moving_frames=frames
    ... )
    """
    datum, quadrature = azimuth_basis(rotor_axis)
    if not isinstance(n_blades, int) or isinstance(n_blades, bool) or n_blades < 1:
        raise CommandArgumentError(
            f"blade_frames: n_blades is {n_blades!r}, and a rotor with {n_blades} blades "
            "has no blade to anchor the placement on. Pass the blade count of the "
            "propeller, which is at least 1"
        )
    if rotation not in ROTATION_SENSE_SIGN:
        raise CommandArgumentError(
            f"blade_frames: rotation is {rotation!r}, and the sense of rotation is "
            f"{' or '.join(sorted(ROTATION_SENSE_SIGN))}, the two words the rotation "
            "field of a propeller descriptor records. It decides which way round the "
            "disc the blades are numbered, so there is no safe default to guess. If "
            "you are holding inboard_up or inboard_down, that is the same fact in the "
            "vocabulary a datasheet prints, it is recorded separately as blade_travel, "
            "and turning it into a sense here needs the side of the aircraft this "
            "propeller is on, which this function is never told"
        )
    if float(blade1_azimuth_deg) not in BLADE_ANCHOR_ANGLES_DEG:
        anchors = ", ".join(str(angle) for angle in BLADE_ANCHOR_ANGLES_DEG)
        raise CommandArgumentError(
            f"blade_frames: the first blade was measured at {float(blade1_azimuth_deg)} "
            f"deg, and this placement anchors on one of {anchors} deg. The other blades "
            "are placed arithmetically at 360/N from that one, so an anchor off the "
            "quadrants would put every blade somewhere the convention cannot name. "
            "Rotate the mesh onto a quadrant, or record the propeller with the blade "
            "the mesh actually starts at"
        )
    if names is not None and len(names) != n_blades:
        raise CommandArgumentError(
            f"blade_frames: names carries {len(names)} name(s) for {n_blades} blades. "
            f"One display name per blade, or leave it out for Blade1 to Blade{n_blades}"
        )
    if labels is not None and len(labels) != n_blades:
        raise CommandArgumentError(
            f"blade_frames: labels carries {len(labels)} label(s) for {n_blades} blades. "
            "One registry label per blade, or leave it out to cite the frames by the "
            "indices this returns"
        )

    sign = ROTATION_SENSE_SIGN[rotation]
    spacing = 360.0 / n_blades
    created: list[int] = []
    for blade in range(n_blades):
        azimuth = math.radians(float(blade1_azimuth_deg) + sign * blade * spacing)
        cosine, sine = math.cos(azimuth), math.sin(azimuth)
        pair = list(zip(datum, quadrature, strict=True))
        radial = tuple(_clean(cosine * d + sine * q) for d, q in pair)
        tangential = tuple(_clean(-sine * d + cosine * q) for d, q in pair)
        created.append(
            coordinate_frame(
                script,
                name=names[blade] if names is not None else f"Blade{blade + 1}",
                origin=hub_origin,
                # x radial, y tangential towards growing azimuth; z is
                # left to the cross product, which is then the rotor axis
                # exactly because the basis pair is cyclic.
                x_axis=radial,
                y_axis=tangential,
                label=labels[blade] if labels is not None else None,
            )
        )
    return created


#: The mesh rotation, in the two names it goes by, newest first.
#:
#: THE ORDER CARRIES NOTHING TODAY, and saying so is the correction the
#: adversarial pass forced: this comment claimed the order was the search
#: order, and reversing the tuple broke no test, because EXACTLY ONE of
#: the two resolves on every registered build. That is the load-bearing
#: property, and it is what
#: `test_exactly_one_rotation_command_resolves_on_every_registered_build`
#: measures. The order would start mattering the day a build documented
#: both, which is why the loop takes the first that resolves rather than
#: asserting there is only one.
#:
#: They are NOT one command renamed, which the database records as its
#: own reading: SURFACE_ROTATE is a keyword block of eight arguments and
#: ROTATE_SURFACE is a payload-lines command of six, with no equivalent
#: of SPLIT_VERTICES or ADAPTIVE_MESH.
ROTATION_COMMANDS: tuple[str, ...] = ("ROTATE_SURFACE", "SURFACE_ROTATE")

#: Trailing index of a boundary label, which is what a component name is
#: the label without. ``Blade_1``, ``Blade 2`` and ``Blade3`` all carry
#: the component ``blade``.
_COMPONENT_INDEX = re.compile(r"[\s_.-]*\d+$")


def _component_of(label: str) -> str:
    """Return the component a boundary label belongs to, case-folded."""
    return _COMPONENT_INDEX.sub("", label).casefold()


def _rotation_command(script: Script) -> str:
    """Return the mesh-rotation command this script's build documents."""
    for name in ROTATION_COMMANDS:
        try:
            script._view[name]
        except CommandNotInVersionError:
            continue
        return name
    raise CommandArgumentError(
        f"rotate_surfaces: FlightStream {script.version.canonical} documents neither "
        f"{ROTATION_COMMANDS[0]} nor {ROTATION_COMMANDS[1]}, so this build has no "
        "recorded way to rotate an existing mesh. The capability is one command on "
        "every build up to 26.121 and the other from 26.122; a build carrying neither "
        "has no row for either command in this database rather than no capability"
    )


def rotate_surfaces(
    script: Script,
    *,
    frame: int | str,
    axis: str,
    angle_deg: float,
    component: str | None = None,
    boundaries: Sequence[int | str] | Literal["all"] = "all",
    detach: Toggle = False,
    split_vertices: Toggle = False,
    adaptive_mesh: Toggle = False,
) -> None:
    """Rotate existing mesh surfaces about an axis of a named frame.

    THIS ACTS ON THE MESH AND NOT ON THE GEOMETRY, which is what decides
    which command family is meant: the surface transforms, never the
    CAD-body or curve ones. The rotation is about an axis of the named
    coordinate system, so the system's origin is the point it turns
    about.

    The command is chosen from the script's own build, because the
    capability changed name at 26.122 and the two grammars are not
    interchangeable (:data:`ROTATION_COMMANDS`).

    Parameters
    ----------
    script : Script
        Script under construction.
    frame : int or str
        Coordinate system the rotation is about, by 1-based index or by
        creation label. Its origin is the point rotated about and its
        ``axis`` is the axis rotated around. An unknown label is refused
        by the emitter, naming the labels the script knows.
    axis : str
        Axis of ``frame``: ``X``, ``Y`` or ``Z``. The older command also
        documents the numeric spellings; this helper passes the token
        through, so a numeric one is refused by the emitter on the build
        whose grammar does not carry it.
    angle_deg : float
        Rotation angle in deg, about ``axis``, in the sense the solver
        applies for that command.
    component : str, optional
        Rotate every declared boundary whose label belongs to this
        component, which is the label with its trailing index removed
        and matched without regard to case. ``"Blade"`` therefore selects
        all N blades, which is the way a rotor incidence change is
        expressed. Mutually exclusive with ``boundaries``.
    boundaries : sequence of int or str, or ``"all"``
        Explicit selection, by 1-based index or declared boundary label;
        ``"all"`` is the -1 form and selects every surface.
    detach : bool or 'ENABLE' or 'DISABLE'
        Emitted as DETACH_NORMAL_TO_AXIS on the older command and as
        DETACH_VERTICES on the newer one. WHETHER THOSE ARE ONE OPTION
        RENAMED IS UNMEASURED: it is read from their position on the
        manual page and no probe has asked, which the command database
        records for the pair. Left off by default for that reason.
    split_vertices, adaptive_mesh : bool or 'ENABLE' or 'DISABLE'
        Options of the older command only. Asking for either on a build
        that documents the newer one is refused rather than dropped: a
        silently discarded mesh option produces a different mesh, on a
        build the helper chose rather than the caller.

    Raises
    ------
    CommandArgumentError
        If both ``component`` and an explicit ``boundaries`` selection
        are given, if a dropped option is asked for on the build that
        does not carry it, or if the build documents neither command.
    ScriptReferenceError
        If ``component`` matches no declared boundary label (the message
        names the component and every label declared), or if a cited
        frame or boundary label is unknown.

    Notes
    -----
    Component matching reads the boundary inventory declared with
    :meth:`~pyflightstream.script.Script.declare_existing`, because the
    boundary names live in the geometry file and the builder cannot know
    them otherwise. A script that declared no inventory has no component
    to expand and is told so.

    Examples
    --------
    >>> from pyflightstream.script import Script, helpers
    >>> script = Script(version="26.123")
    >>> script.declare_existing(frames=1, boundaries={"Blade_1": 1, "Blade_2": 2})
    >>> helpers.rotate_surfaces(script, frame=1, axis="Z", angle_deg=2.5, component="Blade")
    >>> print(script.render().strip())
    ROTATE_SURFACE 1 Z 2.5 2 DISABLE
    1,2
    """
    command = _rotation_command(script)
    detach_on = _read("rotate_surfaces", "detach", detach)
    split_on = _read("rotate_surfaces", "split_vertices", split_vertices)
    adaptive_on = _read("rotate_surfaces", "adaptive_mesh", adaptive_mesh)

    _reject_bare_label("rotate_surfaces", "boundaries", boundaries, allows_all=True)
    if component is not None and boundaries != "all":
        raise CommandArgumentError(
            f"rotate_surfaces: component={component!r} and an explicit boundaries "
            "selection were both given, and they are two answers to one question. "
            "Name the component, or list the boundaries, not both"
        )

    if command == "ROTATE_SURFACE":
        for argument, requested in (
            ("split_vertices", split_on),
            ("adaptive_mesh", adaptive_on),
        ):
            if requested:
                raise CommandArgumentError(
                    f"rotate_surfaces: {argument} was asked for, and "
                    f"{command}, which is what FlightStream "
                    f"{script.version.canonical} documents, has no equivalent of it. "
                    "The option belongs to SURFACE_ROTATE, which that build stops "
                    "printing. Emitting the rotation without it would give you a "
                    "different mesh under an argument the call still carried, so it is "
                    "refused instead. Run this rotation on a build up to 26.121, or "
                    "drop the option deliberately"
                )

    if component is not None:
        declared = script.entities.labels("boundaries")
        wanted = component.casefold()
        selection: list[int | str] = [
            index for label, index in sorted(declared.items()) if _component_of(label) == wanted
        ]
        if not selection:
            known = ", ".join(f"{label!r}" for label in sorted(declared)) or "none"
            raise ScriptReferenceError(
                f"rotate_surfaces: component {component!r} matches no declared boundary "
                f"label; declared labels are {known}. A component is a label with its "
                "trailing index removed, so 'Blade' selects Blade_1 and Blade2 alike. "
                "Declare the geometry's boundary names with declare_existing("
                "boundaries={...}) before rotating by component"
            )
    elif boundaries == "all":
        selection = []
    else:
        selection = list(boundaries)
        _reject_empty_selection("rotate_surfaces", "boundaries", list(selection))

    count = -1 if (component is None and boundaries == "all") else len(selection)
    arguments: dict[str, object] = {
        "frame": frame,
        "axis": axis,
        "angle": angle_deg,
        "surfaces": count,
    }
    if count != -1:
        arguments["surface_indices"] = selection
    if command == "ROTATE_SURFACE":
        arguments["detach_vertices"] = _toggle(detach_on)
    else:
        arguments["split_vertices"] = _toggle(split_on)
        arguments["adaptive_mesh"] = _toggle(adaptive_on)
        arguments["detach_normal_to_axis"] = _toggle(detach_on)
    script.emit(command, **arguments)


#: The action registration, and the two kinds it takes.
UNSTEADY_ACTION_COMMAND = "SET_NEW_UNSTEADY_SOLVER_ACTION"
UNSTEADY_ACTION_KINDS = ("SCRIPT", "COMMAND_LINE")


def unsteady_action(
    script: Script,
    *,
    name: str,
    kind: str,
    filename: str,
    action_script: str | None = None,
) -> UnsteadyActionUse:
    """Register an action the solver runs after each unsteady time step.

    This is what lets a section export come out mid-run instead of by
    stopping the solver and restarting it: the solver executes the
    registered action after each time step, in the order the actions
    were created.

    THE EVIDENCE IS STATED ONCE, HERE. The command is documented on the
    two newest builds and probed on none, so the returned record carries
    the status the database holds for this script's build and whether it
    was inherited. A build that does not document the command at all is
    refused by the emitter, naming the command and the build, rather
    than the workflow degrading into a run whose sections never appear.

    Parameters
    ----------
    script : Script
        Script under construction.
    name : str
        Name of the action, unique within this script. The solver
        accepts several actions and runs them in creation order, so the
        name is how a reader tells two apart.
    kind : str
        ``SCRIPT`` to run a FlightStream script, ``COMMAND_LINE`` to run
        a shell command.
    filename : str
        The path the registration line names, passed through unchanged.
        NOTHING IN EITHER MANUAL EDITION SAYS WHICH DIRECTORY THE SOLVER
        RUNS AN ACTION FROM (RPT-030), so this helper neither resolves
        nor rewrites it, and a caller choosing between a relative and an
        absolute path is choosing under that silence.
    action_script : str, optional
        Text of the child FlightStream script, parked on the script for
        the run layer to write at ``filename``. Only for ``SCRIPT``
        actions: a shell action names a command, and there is no child
        script for this library to write.

    Returns
    -------
    UnsteadyActionUse
        The record of the registration, also appended to
        :attr:`~pyflightstream.script.Script.unsteady_actions`.

    Raises
    ------
    CommandArgumentError
        If ``kind`` is not one of the two, if the name repeats one
        already registered on this script, if two actions would write
        one filename (the second would silently replace the first), or
        if a shell action is given a child script.
    CommandNotInVersionError
        If the build does not document the command. Raised by the
        emitter, so the message carries the recorded evidence of every
        build that does.

    Notes
    -----
    WHAT THE ACTION RECEIVES IS UNSTATED, on all four of the things a
    step-aware action would need: arguments, working directory, step
    index or physical time, and environment (RPT-030). An action that
    has to behave differently on different steps therefore needs state
    of its own, and the correctness of that route rests on the
    invocation count being exactly the step count, which is unstated
    too. Nothing here works around that; the silence is named so a
    caller does not design against a guarantee that was never made.

    Examples
    --------
    >>> from pyflightstream.script import Script, helpers
    >>> script = Script(version="26.123")
    >>> record = helpers.unsteady_action(
    ...     script,
    ...     name="sections",
    ...     kind="SCRIPT",
    ...     filename="actions/sections.txt",
    ...     action_script="EXPORT_SOLVER_ANALYSIS_SPREADSHEET",
    ... )
    >>> record.evidence
    'documented'
    >>> sorted(script.pending_action_scripts)
    ['actions/sections.txt']
    """
    if kind not in UNSTEADY_ACTION_KINDS:
        raise CommandArgumentError(
            f"unsteady_action: kind is {kind!r}, and an action is one of "
            f"{' or '.join(UNSTEADY_ACTION_KINDS)}: a FlightStream script the solver "
            "runs, or a shell command it runs. The two are not interchangeable, so "
            "there is no default"
        )
    if kind == "COMMAND_LINE" and action_script is not None:
        raise CommandArgumentError(
            "unsteady_action: a COMMAND_LINE action names a shell command and has no "
            "child FlightStream script, so action_script has nowhere to be written. "
            "Register the action with kind='SCRIPT' to have this library write the "
            "child script, or write the command's own file yourself"
        )
    if name in script._unsteady_actions:
        raise CommandArgumentError(
            f"unsteady_action: this script already registers an action named {name!r}. "
            "The solver runs registered actions in creation order and the order cannot "
            "be changed afterwards, so the name is the only handle a reader has on "
            "which action is which; give the second one a name of its own"
        )
    already = script._pending_action_scripts.get(filename)
    if already is not None and action_script is not None:
        raise CommandArgumentError(
            f"unsteady_action: this script already writes an action script to "
            f"{filename!r}. One path is one file, so the second would silently replace "
            "the first and both registration lines would point at whichever text won. "
            "Give this action a filename of its own"
        )

    entry = script.registry.commands.get(UNSTEADY_ACTION_COMMAND)
    evidence = entry.evidence_in(script.version) if entry is not None else None
    record = UnsteadyActionUse(
        name=name,
        kind=kind,
        filename=filename,
        evidence=str(evidence.record.status) if evidence is not None else None,
        inherited=evidence.inherited if evidence is not None else False,
    )

    # Emit BEFORE recording: a build that does not carry the command must
    # leave the script with no action registered and nothing parked, so
    # the refusal is not half applied.
    script.emit(UNSTEADY_ACTION_COMMAND, kind, name, filename)
    script._unsteady_actions[name] = record
    if action_script is not None:
        script._pending_action_scripts[filename] = action_script
    return record


#: Marking wake edges from an imported node list, and the angle
#: criterion it replaces. Named as a pair because the whole point of the
#: refusal below is that one is never silently substituted for the other.
WAKE_EDGE_IMPORT_ROUTE = "IMPORT_WAKE_EDGES_FROM_FILE"
WAKE_EDGE_ANGLE_ROUTE = "AUTO_DETECT_TRAILING_EDGES"


def mark_wake_edges(script: Script, *, edge_type: str, tolerance: float) -> str:
    """Mark wake edges from an imported node list, not by angle.

    Emits the import route INSTEAD of the angle criterion, which is what
    the route is for: auto detection marks an edge because the surface
    creases there, and a strongly twisted blade has a trailing edge that
    is not a crease. Both passes over one geometry would mark twice, so
    this replaces rather than runs beside.

    Parameters
    ----------
    script : Script
        Script under construction.
    edge_type : str
        Edge type applied to every edge the import matches: the same
        four values SET_TRAILING_EDGE_TYPE takes, so this sets for a
        whole imported file what that command sets for one edge.
    tolerance : float
        Maximum distance between a mesh edge mid-point and an imported
        node coordinate for the two to count as the same edge, in the
        simulation's own length units.

    Returns
    -------
    str
        The command emitted, for a run record that has to name the route
        it took.

    Raises
    ------
    CommandNotInVersionError
        If the build does not document the import route. The message
        names the build, the route, and the angle criterion this library
        will NOT substitute unasked: a campaign that silently fell back
        would mark a twisted blade by an angle criterion and report
        nothing about it.

    Notes
    -----
    NEITHER ARGUMENT HAS A DEFAULT HERE, deliberately. The vendor's own
    defaults live one layer up, on
    :class:`~pyflightstream.workspace.wake_edges.WakeEdgeImport`,
    together with the refusals a grammatically perfect call still needs:
    an empty node list and a tolerance of zero are both well formed and
    both mark nothing. A second copy of either the defaults or the
    refusals here is the drift this split exists to prevent.

    THIS HELPER TAKES NO PATH, because the command takes none. Both
    editions that document it print a signature and a sample call with
    two values and neither says where the node list comes from. Adding a
    path argument would be this library inventing a grammar, so the
    silence is left visible; settling it is PFS-2025.16.01's reading.

    The route is DOCUMENTED and probed on no build, while the angle
    criterion it replaces carries verified rows on three. The trade is
    deliberate and the reason is physical;
    :func:`~pyflightstream.workspace.wake_edges.evidence_notice` renders
    the sentence that says so for a given build.

    Examples
    --------
    >>> from pyflightstream.script import Script, helpers
    >>> script = Script(version="26.123")
    >>> helpers.mark_wake_edges(script, edge_type="VORTEX_SHEDDING", tolerance=0.0001)
    'IMPORT_WAKE_EDGES_FROM_FILE'
    >>> print(script.render().strip())
    IMPORT_WAKE_EDGES_FROM_FILE VORTEX_SHEDDING 0.0001
    """
    try:
        script._view[WAKE_EDGE_IMPORT_ROUTE]
    except CommandNotInVersionError as error:
        raise CommandNotInVersionError(
            f"mark_wake_edges: FlightStream {script.version.canonical} does not carry "
            f"{WAKE_EDGE_IMPORT_ROUTE}, the route this campaign marks its trailing "
            f"edges by, and this library will not fall back to {WAKE_EDGE_ANGLE_ROUTE} "
            "for you. That route marks an edge where the surface creases, which is "
            "the criterion an imported node list exists to replace on a blade whose "
            "trailing edge is not a crease, so substituting it would change the "
            f"physics in silence. Run this case on a build that documents "
            f"{WAKE_EDGE_IMPORT_ROUTE}, or ask for the angle criterion deliberately. "
            f"The database says: {error}"
        ) from error
    script.emit(WAKE_EDGE_IMPORT_ROUTE, edge_type, tolerance)
    return WAKE_EDGE_IMPORT_ROUTE


# --- PFS-2026.06: the relaxed trailing-edge specification's fifth field -------
#
# THIS PAIR EMITS NOTHING, which is the one surprise worth stating before
# the code. Every other name in this module turns typed arguments into
# `script.emit()` calls. A relaxed-Kutta trailing edge can also be
# declared as a COMPONENT parameter, written where a component is defined
# rather than in a script, and no command on any registered build takes
# its fields (the reading is recorded on SET_TRAILING_EDGE_TYPE in the
# command database, and `tests/test_wake_edges.py` pins it). So these
# read and write the specification TEXT, and take no `script`.

#: Field count of the relaxed trailing-edge component specification: what
#: the editions up to SRC-750 p.85 print, and what SRC-751 p.85 prints
#: after adding the shedding direction. The four-field form stays valid,
#: so both counts are accepted and neither is converted into the other
#: unasked.
RELAXED_TE_FIELDS_WITHOUT_DIRECTION = 4
RELAXED_TE_FIELDS_WITH_DIRECTION = 5

#: The direction the relaxed wake sheds, as the token this package takes
#: mapped to the integer the specification's fifth field carries
#: (SRC-751 p.85). AXIAL is 0 AND is the default, which is what a
#: four-field specification already means; AZIMUTH is 1 and is the new
#: control, the one a rotor case wants.
RELAXED_SHEDDING_DIRECTIONS: Mapping[str, int] = {"AXIAL": 0, "AZIMUTH": 1}

#: The reverse lookup, built once. Written from the mapping above rather
#: than typed a second time, so the two can never disagree.
_SHEDDING_BY_FIELD: Mapping[int, str] = {
    field: token for token, field in RELAXED_SHEDDING_DIRECTIONS.items()
}

#: The direction a specification that carries no fifth field means.
DEFAULT_SHEDDING_DIRECTION = "AXIAL"


def _shedding_vocabulary() -> str:
    """Render the accepted directions the way every refusal names them."""
    return " or ".join(
        f"{field} ({token})" for token, field in sorted(RELAXED_SHEDDING_DIRECTIONS.items())
    )


def resolve_shedding_direction(value: str | int, *, context: str) -> str:
    """Resolve one relaxed-wake shedding direction to its token.

    Takes either vocabulary, because the specification writes the
    integer and a caller reads the word: ``0`` and ``"AXIAL"`` are the
    same request, as are ``1`` and ``"AZIMUTH"``. Tokens are matched
    without regard to case and a numeric string is read as the integer
    it spells, which is what a matrix cell carries.

    Parameters
    ----------
    value : str or int
        The direction, as a token or as the integer the fifth field
        carries.
    context : str
        What is being resolved, prefixed to the refusal so the caller
        learns which call refused. A helper passes its own name; a
        campaign passes the case and the key.

    Returns
    -------
    str
        ``"AXIAL"`` or ``"AZIMUTH"``.

    Raises
    ------
    CommandArgumentError
        If the value is neither. The message names the value received
        and both accepted directions, because there is no third: the
        field is an integer with exactly two documented values, and a
        direction outside them would make the solver read a wake
        shedding in a direction the manual does not define.

    Examples
    --------
    >>> from pyflightstream.script import helpers
    >>> helpers.resolve_shedding_direction(1, context="rotor")
    'AZIMUTH'
    >>> helpers.resolve_shedding_direction("axial", context="rotor")
    'AXIAL'
    """
    token: str | None = None
    if isinstance(value, bool):
        # bool is an int in Python, so True would otherwise resolve to
        # AZIMUTH. A direction is not a switch, and the caller who wrote
        # True meant something this package cannot know.
        token = None
    elif isinstance(value, int):
        token = _SHEDDING_BY_FIELD.get(value)
    elif isinstance(value, str):
        text = value.strip()
        if text.upper() in RELAXED_SHEDDING_DIRECTIONS:
            token = text.upper()
        elif text.isascii() and text.isdigit():
            # ASCII DIGITS ONLY, and the guard is not decoration.
            # `int()` reads any Unicode decimal digit, so the
            # Arabic-Indic ONE resolved to AZIMUTH and a field spelled
            # in a script the manual never uses became a direction the
            # solver would shed a wake along. It also read `+1`, which
            # no tool writes and which the manual's "integer, 0 or 1"
            # does not describe. Both are accidents of the conversion
            # rather than decisions, and a refusal naming both accepted
            # values is a better answer than either.
            token = _SHEDDING_BY_FIELD.get(int(text))
    if token is None:
        raise CommandArgumentError(
            f"{context}: the relaxed wake sheds in one of two directions and "
            f"{value!r} is neither. The fifth field of the relaxed trailing-edge "
            f"component specification takes {_shedding_vocabulary()}, the axial "
            "direction being the default and the one a four-field specification "
            "already means (SRC-751 p.85). Write the integer or the word; there is "
            "no third direction to fall back to, and shedding a rotor wake the wrong "
            "way round changes the induced velocity at every blade"
        )
    return token


@dataclass(frozen=True)
class RelaxedTrailingEdge:
    """One relaxed trailing-edge component specification, read apart.

    The specification is a semicolon-separated field list written where a
    component is defined, not in a script (SRC-751 p.85). The first four
    fields are a chordwise or radial location and two spanwise or axial
    bounds; this package does not interpret them and carries them
    verbatim, because the edition that added the fifth field changed
    nothing about them.

    THE FOUR-FIELD FORM IS NOT SILENTLY WIDENED. A specification parsed
    with four fields renders with four, so an artifact written before
    26.123 stays readable by the builds that wrote it; the fifth field
    appears only where one was read or one was asked for.

    Attributes
    ----------
    fields : tuple of str
        The four leading fields, verbatim apart from the whitespace
        around each one, which is not part of a field.
    direction : str or None
        ``"AXIAL"`` or ``"AZIMUTH"`` where the specification carries the
        fifth field, and None where it carries four. None is not the
        same statement as ``"AXIAL"``: both MEAN the axial direction,
        and only one of them writes a field.

    Examples
    --------
    >>> from pyflightstream.script import helpers
    >>> edge = helpers.parse_relaxed_trailing_edge("0.5;0.1;0.9;1")
    >>> edge.direction is None
    True
    >>> edge.shedding_direction
    'AXIAL'
    >>> edge.render()
    '0.5;0.1;0.9;1'
    >>> edge.with_shedding("AZIMUTH").render()
    '0.5;0.1;0.9;1;1'
    """

    fields: tuple[str, ...]
    direction: str | None = None

    def __post_init__(self) -> None:
        """Normalise the fields and refuse a record that cannot render.

        The record is public and constructible directly, so the two
        invariants rendering rests on are checked here rather than only
        in the parser: exactly the four leading fields, and a direction
        the fifth field can spell.
        """
        object.__setattr__(self, "fields", tuple(str(field).strip() for field in self.fields))
        if len(self.fields) != RELAXED_TE_FIELDS_WITHOUT_DIRECTION:
            raise CommandArgumentError(
                f"RelaxedTrailingEdge holds the {RELAXED_TE_FIELDS_WITHOUT_DIRECTION} "
                f"leading fields of the specification and was given {len(self.fields)}: "
                f"{self.fields!r}. The shedding direction is the `direction` attribute "
                "and never a fifth entry here, so that rendering can tell a "
                "specification that states the direction from one that leaves it at the "
                "default (SRC-751 p.85)"
            )
        if self.direction is not None and self.direction not in RELAXED_SHEDDING_DIRECTIONS:
            raise CommandArgumentError(
                f"RelaxedTrailingEdge direction is {self.direction!r}, and the fifth "
                f"field of the specification takes {_shedding_vocabulary()} "
                "(SRC-751 p.85). Pass None to leave the field unwritten, which means "
                "the axial direction"
            )

    @property
    def shedding_direction(self) -> str:
        """The direction this specification MEANS, stated or defaulted.

        Returns
        -------
        str
            ``"AXIAL"`` or ``"AZIMUTH"``. A specification carrying four
            fields reads as ``"AXIAL"``, because that is the field's
            documented default (SRC-751 p.85); use :attr:`direction` to
            tell that case from one that wrote the 0.
        """
        return self.direction or DEFAULT_SHEDDING_DIRECTION

    def with_shedding(self, direction: str | int) -> RelaxedTrailingEdge:
        """Return this specification stating one shedding direction.

        Parameters
        ----------
        direction : str or int
            ``"AXIAL"``/0 or ``"AZIMUTH"``/1, resolved by
            :func:`resolve_shedding_direction`.

        Returns
        -------
        RelaxedTrailingEdge
            A new specification. Asking for the axial direction on one
            that already leaves the field unwritten returns it
            UNCHANGED, at four fields: the two say the same thing, and
            writing the 0 would hand a five-field specification to a
            build that reads four.

        Raises
        ------
        CommandArgumentError
            If the direction is neither, naming the value and both.
        """
        token = resolve_shedding_direction(direction, context="with_shedding")
        if token == DEFAULT_SHEDDING_DIRECTION and self.direction is None:
            return self
        return replace(self, direction=token)

    def render(self) -> str:
        """Return the specification as a component definition writes it.

        Returns
        -------
        str
            The fields, semicolon separated, with the direction's
            integer appended only where :attr:`direction` states one.
        """
        fields = list(self.fields)
        if self.direction is not None:
            fields.append(str(RELAXED_SHEDDING_DIRECTIONS[self.direction]))
        return ";".join(fields)


def parse_relaxed_trailing_edge(specification: str) -> RelaxedTrailingEdge:
    """Read one relaxed trailing-edge component specification.

    Accepts both shapes the editions print: the four-field form of
    SRC-750 p.85 and the five-field form SRC-751 p.85 adds, whose last
    field is the direction the relaxed wake sheds.

    Parameters
    ----------
    specification : str
        The semicolon-separated field list, as a component definition
        carries it. Whitespace around a field is not part of it.

    Returns
    -------
    RelaxedTrailingEdge
        The parsed specification, whose :attr:`~RelaxedTrailingEdge.direction`
        is None where the text carried four fields.

    Raises
    ------
    CommandArgumentError
        If the text is not a string, if it carries a field count that is
        neither of the two documented ones, if a field is blank, or if
        the fifth field is a direction the edition does not define. The
        direction refusal names the value and both accepted directions.

    Examples
    --------
    >>> from pyflightstream.script import helpers
    >>> helpers.parse_relaxed_trailing_edge("0.5; 0.1; 0.9; 1; 1").shedding_direction
    'AZIMUTH'
    """
    if not isinstance(specification, str):
        raise CommandArgumentError(
            "parse_relaxed_trailing_edge takes the specification TEXT, a "
            "semicolon-separated field list as a component definition carries it, and "
            f"was given {type(specification).__name__} {specification!r}. This is a "
            "component-file field and not a command, so there is no emitter to convert "
            "typed arguments for it (SRC-751 p.85)"
        )
    fields = [field.strip() for field in specification.split(";")]
    if len(fields) not in (RELAXED_TE_FIELDS_WITHOUT_DIRECTION, RELAXED_TE_FIELDS_WITH_DIRECTION):
        raise CommandArgumentError(
            f"parse_relaxed_trailing_edge: {specification!r} carries {len(fields)} "
            f"semicolon-separated field(s), and the relaxed trailing-edge component "
            f"specification carries {RELAXED_TE_FIELDS_WITHOUT_DIRECTION} (a chordwise "
            f"or radial location and two bounds) or "
            f"{RELAXED_TE_FIELDS_WITH_DIRECTION}, the fifth being the direction the "
            "relaxed wake sheds, which SRC-751 p.85 adds and SRC-750 p.85 does not "
            "print"
        )
    blank = [position for position, field in enumerate(fields, start=1) if not field]
    if blank:
        raise CommandArgumentError(
            f"parse_relaxed_trailing_edge: {specification!r} leaves field(s) "
            f"{', '.join(str(position) for position in blank)} blank. Every field of "
            "the specification carries a value, so a blank one is a separator too many "
            "rather than a field left at its default; the only field with a default is "
            "the fifth, and it is defaulted by leaving it OUT (SRC-751 p.85)"
        )
    if len(fields) == RELAXED_TE_FIELDS_WITHOUT_DIRECTION:
        return RelaxedTrailingEdge(fields=tuple(fields))
    direction = resolve_shedding_direction(
        fields[-1], context=f"parse_relaxed_trailing_edge: {specification!r}"
    )
    return RelaxedTrailingEdge(
        fields=tuple(fields[:RELAXED_TE_FIELDS_WITHOUT_DIRECTION]), direction=direction
    )
