"""The quasi-steady rotor builder: one solve per blade clocking.

:func:`_build_qsteady_rotor` builds the run type ``qsteady_rotor``: the
inflow the rotor sees, the blade stations read from the mesh, and one
steady solve per clocking position with its sections cut and deleted.
"""

from __future__ import annotations

import json
import math
from collections.abc import (
    Mapping,
    Sequence,
)
from pathlib import (
    Path,
)
from typing import (
    Literal,
)

import pyflightstream.cases._setup_link as _setup_link
from pyflightstream._errors import (
    PyflightstreamWarning,
    collecting_warnings,
    warn,
)
from pyflightstream._fsm import (
    MeshReadError,
    boundary_vertices,
    saved_mesh_coordinate_unit,
)
from pyflightstream._lengths import (
    scale,
)
from pyflightstream.cases import (
    EXPANDING_FRAMES,
    EXPORT_KINDS,
    CampaignConfigError,
    RotorBlock,
    SimCase,
    classify_outputs,
    resolve_alias,
    select_group_members,
)
from pyflightstream.cases import (
    qsteady as _qsteady,
)
from pyflightstream.script import (
    FramePlacement,
    Script,
    helpers,
)

from ._clock import (
    unsteady_export_threshold,
)
from ._conventions import (
    WorkflowConventions,
)
from ._exports import (
    _declared_export_kinds,
    _surface_export,
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
    _an_angle_beside_a_field,
    _finish_custom_field_coverage,
    _fluid,
    _refuse_wake_termination_without_a_clock,
    _RowFreestream,
    _the_custom_freestream,
)
from ._geometry import (
    _open_geometry,
)
from ._names import (
    _inventory,
    _resolve_token,
)
from ._pproc import (
    _pproc_sections,
    pproc_emissions,
)
from ._rows import (
    _ONLY_AN_ISOLATED_ROTOR,
    RAD_PER_S_PER_REV_PER_MIN,
    RotorSpeed,
    _from_metres,
    _qsteady_speed,
    _refuse_unregistered_keys,
    _required_int,
    _the_isolated_rotor,
    _variable,
    _velocity,
    qsteady_case_kind,
)
from ._skeleton import (
    _initialize,
    _script_init,
    _script_solve_and_export,
    _script_tail,
)
from ._solver_settings import (
    _analysis,
    _custom_flags,
    _raw_commands,
    _refuse_a_coupling_step_without_a_clock,
    _settings,
)
from ._vocabulary import (
    FREESTREAM_VARIABLE,
    PASSAGE_POSITIONS_VARIABLE,
    QSTEADY_ROTOR,
    ROTATE_VARIABLE,
    SYMMETRY_VARIABLE,
    TRANSLATE_VARIABLE,
    Frames,
)


def _refuse_fsi_on_a_quasi_steady_rotor(case: SimCase, kind: str) -> None:
    """Refuse FSI on a quasi-steady WHEEL; a SECTOR couples (0.30.0).

    A sector is one steady solve of one blade in a free stream turning at the
    rotor's speed, which is the route the licensed test 2 of the FSI study
    coupled (the blade static, the rotation in the free stream, the
    structure's centrifugal load at that speed): it is wired by
    :func:`_wire_the_quasi_steady_sector`. A wheel is several clockings
    averaged, and one deformed blade per clocking is not a structure's state.
    """
    if case.fsi is None and _variable(case, "FSI") is None:
        return
    if kind == "sector":
        return
    raise CampaignConfigError(
        f"case {case.sim_id!r} names the run type {QSTEADY_ROTOR} on a whole wheel and states "
        "FSI: a quasi-steady wheel with FSI is not supported. The wheel is several steady "
        "clockings averaged, and a blade deformed once per clocking is not the state of one "
        f"structure. Solve a periodic sector ({SYMMETRY_VARIABLE} PERIODIC) for FSI."
    )


def _the_inflow_varies_around_the_disc(case: SimCase) -> str | None:
    """Name what makes a quasi-steady row's inflow vary with azimuth, or None.

    A custom inflow file (the sector reads whether it varies with the radius
    alone) and a non-zero angle of attack or of sideslip, fixed or swept.
    """
    if case.freestream_profile is not None or _variable(case, FREESTREAM_VARIABLE) is not None:
        return "a custom inflow"
    return _an_angle_beside_a_field(case)


def _passage_positions(case: SimCase, kind: str) -> int:
    """Return how many clockings the row's wheel is solved in, refusing a missing count.

    A wheel whose inflow varies around the disc MUST state
    ``PASSAGE_POSITIONS``: one clocking is one instant of a load that turns with
    the blades, and the count is the row's statement of how finely the passage
    is sampled. A wheel in an axial, uniform inflow is steady in the rotating
    frame and solves once unless it states more. A sector has one position.
    """
    stated = _variable(case, PASSAGE_POSITIONS_VARIABLE)
    varies = _the_inflow_varies_around_the_disc(case)
    if kind == "sector":
        if stated is not None:
            raise CampaignConfigError(
                f"case {case.sim_id!r} names the run type {QSTEADY_ROTOR} on a periodic sector "
                f"and states {PASSAGE_POSITIONS_VARIABLE}: {stated}. A sector's inflow is the "
                "same at every azimuth, so it has one position; the key is the wheel's."
            )
        return 1
    if stated is None:
        if varies is not None:
            raise CampaignConfigError(
                f"case {case.sim_id!r} names the run type {QSTEADY_ROTOR} on a whole wheel with "
                f"{varies}, and states no {PASSAGE_POSITIONS_VARIABLE}. With an inflow that "
                "varies around the disc each blade meets a different flow at each clocking, "
                f"so the wheel is solved at k clockings inside one blade passage and averaged: "
                f"write '{PASSAGE_POSITIONS_VARIABLE}: 2' for thrust and torque, 6 or more for "
                "the in-plane loads (docs/workflow-qsteady-rotor.md, RPT-089)."
            )
        return 1
    # READ AS EVERY COUNT OF A ROW IS READ (BLADES included): a number, `2` or
    # `2.0`, with no fractional part, refused by case and key when it is not one.
    # A test of the cell's digits refused `2.0`, which every other count accepts.
    count = _required_int(
        case, PASSAGE_POSITIONS_VARIABLE, quantity="count of clockings", unit="positions"
    )
    if count < 1:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {PASSAGE_POSITIONS_VARIABLE}: {stated}, and the count "
            "of clockings inside one blade passage is a whole number, one or more."
        )
    return count


def _refuse_an_azimuthal_inflow_on_a_sector(case: SimCase) -> None:
    """Refuse an angle on a periodic sector: its inflow varies with azimuth.

    A sector stands for the wheel only where every blade meets the same flow,
    so an inflow varying with the radius alone is accepted (a custom inflow is
    read for it when the field is written) and any angle of attack or of
    sideslip is refused.
    """
    angled = _an_angle_beside_a_field(case)
    if angled is not None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} names the run type {QSTEADY_ROTOR} on a periodic sector and "
            f"{angled}. An angle makes the inflow vary with azimuth, so the blade the sector "
            "meshes no longer stands for the others; solve the whole wheel (no SYMMETRY) with "
            f"{PASSAGE_POSITIONS_VARIABLE}, or the rotor as unsteady_rotor."
        )


def _refuse_what_is_not_the_rotor(
    case: SimCase, script: Script, rotor: RotorBlock, kind: str
) -> list[int]:
    """Refuse an opened geometry holding a surface the rotor does not own; return the rotor's.

    Every boundary the geometry declares must be one of the rotor's families,
    general or blade, resolved as a row's names are (exact label, alias,
    family). A wheel carries every blade the rotor block lists; a sector at
    least one. A geometry whose boundary names are not known is not checked,
    and the build says so.

    Returns
    -------
    list of int
        The rotor's boundaries, by index; empty where the names are not known,
        which the clocking reads as every surface.
    """
    labels = script.entities.labels("boundaries")
    if not labels:
        warn(
            f"case {case.sim_id!r}: the boundary names of the opened geometry are not known, "
            f"so whether it holds a surface outside rotor {rotor.alias} is not checked. "
            f"{_ONLY_AN_ISOLATED_ROTOR}",
            PyflightstreamWarning,
            stacklevel=3,
        )
        return []
    owned: set[int] = set()
    blades_found = []
    exact = {name.casefold() for name in labels}
    ordered = [name for name, _ in sorted(labels.items(), key=lambda item: item[1])]
    for member in rotor.members:
        found = _resolve_token(case, member, labels)
        owned.update(found)
        # A BLADE IS PRESENT BY ITS OWN NAME, OR BY THE ALIAS THE ROW GIVES IT.
        # The resolver reads a token ending in a digit as its family too, so
        # `Blade3` would find `Blade1` on a mesh of two blades; a blade named
        # with its number must be a label of its own or an alias of the row that
        # selects a surface (the ownership check above resolves it the same
        # way), and only a family token (no number) is answered by the family
        # reading.
        numbered = member[-1:].isdigit()
        aliased = bool(resolve_alias(member, ordered, case.aliases)) if numbered else False
        if member in rotor.families_blades and (
            (member.casefold() in exact or aliased) if numbered else bool(found)
        ):
            blades_found.append(member)
    others = sorted(name for name, index in labels.items() if index not in owned)
    if others:
        raise CampaignConfigError(
            f"case {case.sim_id!r} names the run type {QSTEADY_ROTOR} and its geometry holds "
            f"{', '.join(others)}, which rotor {rotor.alias} does not own (its families are "
            f"{', '.join(rotor.members)}). {_ONLY_AN_ISOLATED_ROTOR}"
        )
    missing = [blade for blade in rotor.families_blades if blade not in blades_found]
    if kind == "wheel" and missing:
        raise CampaignConfigError(
            f"case {case.sim_id!r} solves the whole wheel of rotor {rotor.alias} (no "
            f"{SYMMETRY_VARIABLE}) and its geometry carries no {', '.join(missing)}. A wheel "
            "meshes every blade; a mesh of one blade is a sector: state "
            f"{SYMMETRY_VARIABLE} PERIODIC and PERIODIC_COPIES."
        )
    if kind == "sector" and not blades_found:
        raise CampaignConfigError(
            f"case {case.sim_id!r} solves a periodic sector of rotor {rotor.alias} and its "
            f"geometry carries none of its blades ({', '.join(rotor.families_blades)})."
        )
    return sorted(owned)


def _the_shaft_letter(rotor: RotorBlock) -> str:
    """Return the axis of the hub frame the rotor turns about: its letter, or Z of a shaft.

    :func:`_hub_basis` builds a vector shaft's hub frame with the shaft as its
    third axis, as :func:`_motion_view` reads it.
    """
    return rotor.axis if isinstance(rotor.axis, str) else "Z"


def _qsteady_free_stream(
    case: SimCase,
    script: Script,
    *,
    rotor_frame: int,
    rotor: RotorBlock,
    speed: RotorSpeed,
    custom: _RowFreestream | None,
    kind: str,
) -> None:
    """Write the free stream a blade held still meets: turning at the rotor's speed.

    WITHOUT A CUSTOM INFLOW, ``SET_FREESTREAM ROTATION`` in the rotor's hub
    frame, about its shaft, at its speed signed by its hand: the frame, the axis
    and the rate a rotary motion of the same rotor states (the FSI study's
    test 2 measured this form on 26.124 against the turning blade, to 0.35 per
    cent in axial force). An angle of attack is the solver setting it always
    is (measured beside the rotating free stream in the same study).

    WITH ONE, the file holds the TOTAL velocity of the air at the disc, in the
    global frame, and the package composes from it the RELATIVE free stream the
    fixed blades see, which removes the rotational velocity of each point:
    ``v_rel(p) = v(p) - Omega axis x (p - hub)``
    (:func:`pyflightstream.cases.freestream.prepare_rotating_field`), writing
    ``SET_FREESTREAM CUSTOM`` of the result, since a run has one
    ``SET_FREESTREAM``. The field lies in the YZ plane of the global frame, so
    the shaft must be the global X axis; a sector's field must vary with the
    radius alone (:func:`pyflightstream.cases.qsteady.azimuthal_variation`).
    """
    axis = _the_shaft_letter(rotor)
    if custom is None:
        helpers.free_stream(script, "ROTATION", frame=rotor_frame, axis=axis, rpm=speed.rpm)
        return
    from ..freestream import field_rows_in_metres, prepare_rotating_field

    shaft = rotor.axis_vector
    if abs(abs(shaft[0]) - 1.0) > 1e-9:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states a custom inflow on the run type {QSTEADY_ROTOR} and "
            f"rotor {rotor.alias} turns about {rotor.axis!r}. A custom field lies in the YZ "
            "plane of the global frame, so the disc it describes must lie in that plane: the "
            "shaft must be the global X axis."
        )
    _from_metres(case, script, "the custom field's coordinates and velocities")
    native = script.simulation_length_unit
    if kind == "sector":
        _, rows = field_rows_in_metres(
            Path(custom.path),
            form=custom.form,
            source_units=custom.source_units,
            native_unit=native,
        )
        why = _qsteady.azimuthal_variation(rows, hub=rotor.origin, axis=shaft)
        if why is not None:
            raise CampaignConfigError(
                f"case {case.sim_id!r} solves a periodic sector of rotor {rotor.alias} in the "
                f"custom inflow {custom.path}, and it varies with azimuth: {why}. A sector "
                "stands for the wheel only in an inflow that varies with the radius alone; "
                f"solve the whole wheel with {PASSAGE_POSITIONS_VARIABLE}."
            )
    field = prepare_rotating_field(
        Path(custom.path),
        form=custom.form,
        source_units=custom.source_units,
        native_unit=native,
        hub_m=rotor.origin,
        axis=shaft,
        omega_rad_s=speed.rpm * RAD_PER_S_PER_REV_PER_MIN,
    )
    assert field.payload is not None  # The rotating field always writes a file of its own.
    existing = script.pending_input_files.get(field.path)
    if existing is not None and existing != field.payload:
        raise CampaignConfigError("The prepared custom field conflicts with another input.")
    script._pending_input_files[field.path] = field.payload
    script._pending_input_files[field.path + ".provenance.json"] = (
        json.dumps(dict(field.provenance), indent=2) + "\n"
    )
    helpers.free_stream(script, "CUSTOM", filetype=custom.form, profile=field.path)


def _blade_stations_from_the_mesh(
    case: SimCase, rotor: RotorBlock
) -> tuple[tuple[float, ...], tuple[float, ...]] | str:
    """Return blade one's stations and chords read off the mesh, or why they cannot be.

    Read from an OBJ, whose groups name its boundaries and whose ``[import]``
    unit converts it to metres, or (0.32.0) from a saved simulation, whose
    boundary row tells each face to its boundary and whose stored coordinate
    unit is measured (:func:`pyflightstream._fsm.boundary_vertices`); and only
    where the row leaves the mesh where the file holds it. An STL names no
    boundary; for it the chords come from the sectional loads export after
    the run.
    """
    geometry = case.geometry
    if geometry is None:
        return "the row opens no geometry"
    path = Path(str(geometry))
    suffix = path.suffix.lower()
    if suffix not in (".obj", ".fsm"):
        return (
            f"the chord is read at plan time from an OBJ mesh or a saved simulation only, "
            f"and {path.name} is a {path.suffix or 'file with no extension'}"
        )
    factor: float | None
    if suffix == ".fsm":
        try:
            stored = saved_mesh_coordinate_unit(path)
        except (MeshReadError, OSError) as error:
            return f"{path.name} could not be read: {error}"
        factor = scale(stored, "METER") if stored else None
        if factor is None:
            return f"{path.name} states no length unit a metre can be read from"
    else:
        unit = getattr(case.mesh_import, "units", None)
        factor = scale(str(unit), "METER") if unit else None
        if factor is None:
            return f"{path.name} states no length unit a metre can be read from"
    moved = [key for key in (ROTATE_VARIABLE, TRANSLATE_VARIABLE) if _variable(case, key)]
    operations = getattr(case.mesh_import, "operations", None) or ()
    moved += sorted({f"the import's {op.op}" for op in operations if op.op != "rename"})
    if moved:
        return f"the row moves the mesh ({', '.join(moved)}) before the solve"
    try:
        if suffix == ".fsm":
            boundaries = boundary_vertices(path)
            if boundaries is None:
                return f"{path.name} does not tell its faces to their boundaries"
            groups = {
                name: [(x * factor, y * factor, z * factor) for x, y, z in vertices]
                for name, vertices in boundaries.items()
            }
        else:
            groups = _qsteady.obj_group_vertices(path, metres_per_unit=factor)
    except (OSError, UnicodeError, ValueError) as error:
        return f"{path.name} could not be read: {error}"
    blade = rotor.families_blades[0] if rotor.families_blades else None
    if blade is None:
        return f"rotor {rotor.alias} lists no blade"
    chosen = select_group_members([blade], list(groups), case.aliases)
    vertices = [vertex for name in chosen for vertex in groups[name]]
    if not vertices:
        return f"{path.name} holds no face of blade {blade}"
    try:
        radii, chords = _qsteady.blade_stations(vertices, hub=rotor.origin, axis=rotor.axis_vector)
    except CampaignConfigError as error:
        return str(error)
    if not radii:
        return f"blade {blade} of {path.name} is too coarse to cut into stations"
    return radii, chords


def qsteady_validity(case: SimCase, *, inflow_fft: bool = False) -> dict[str, object] | None:
    """Return the 1P reduced frequency of a quasi-steady wheel point, as the plan shows it.

    With ``inflow_fft`` (``pyfs-matrix plan --inflow-fft``), a wheel point in a
    custom inflow also carries, under ``inflow_fft``, the harmonic content of
    that inflow as one blade meets it (:func:`qsteady_inflow_fft`).

    Parameters
    ----------
    case : SimCase
        The point's case.
    inflow_fft : bool, optional
        Add the harmonic content of the custom inflow under ``inflow_fft``.
        Defaults to False.

    Returns
    -------
    dict of str to object or None
        The 1P reduced-frequency record, with ``inflow_fft`` added where
        asked and available; None for a point that carries no such record.
    """
    record = _one_per_revolution_validity(case)
    if record is not None and inflow_fft:
        harmonics = qsteady_inflow_fft(case)
        if harmonics is not None:
            record = {**record, "inflow_fft": harmonics}
    return record


def _one_per_revolution_validity(case: SimCase) -> dict[str, object] | None:
    """Return the 1P reduced frequency of a quasi-steady wheel point (:func:`qsteady_validity`).

    ``k = Omega c / (2 V_rel)`` at every station of blade one
    (:mod:`pyflightstream.cases.qsteady`), with the chord read off the mesh
    (:func:`_blade_stations_from_the_mesh`), ``Omega`` the rotor's speed and
    ``V`` the point's free-stream speed. The four values the plan shows are
    ``span_pct_k_gt_0_1`` (the per cent of the span with k above 0.1),
    ``k_min``, ``k_max`` and ``k_mean`` (weighted by span); the record adds
    the span above 0.05 and the stations.

    WHEN THE CHORD IS NOT KNOWN AT PLAN TIME, the record carries what is: the
    reduced frequency per metre of chord at the root and at the tip,
    ``Omega / (2 V_rel)``, and a ``note`` saying why the chord is not known.

    NEVER RAISES for a row the builder would refuse: the builder says why.

    Returns
    -------
    dict or None
        None for a point that is not a quasi-steady WHEEL: a sector's inflow is
        the same at every azimuth, so it has no once-per-revolution load.
    """
    if case.recipe != QSTEADY_ROTOR:
        return None
    try:
        if qsteady_case_kind(case) != "wheel":
            return None
        rotor = _the_isolated_rotor(case)
        rpm = float(_qsteady_speed(case, rotor).rpm)
        velocity = _velocity(case)
    except CampaignConfigError:
        return None
    omega = rpm * RAD_PER_S_PER_REV_PER_MIN
    base: dict[str, object] = {"rotor": rotor.alias, "rpm": rpm, "velocity_m_per_s": velocity}
    tip = rotor.diameter_m / 2.0
    tip_speed = math.hypot(velocity, omega * tip)
    if tip_speed <= 0.0:
        # NO RELATIVE FLOW ANYWHERE ON THE BLADE (no free stream and no rotation):
        # k = Omega c / (2 V_rel) is 0 / 0 at every station, so there is no time
        # scale to compare the rotation with. Said, never raised: the plan asks
        # this of every wheel point, READY or not.
        return {
            **base,
            "note": (
                f"POL {case.sim_id}: the point states no free-stream speed and no rotation, "
                "so the blade sees no relative flow and k = Omega c / (2 V_rel) is not defined"
            ),
            "k_per_chord_m_root": None,
            "k_per_chord_m_tip": None,
        }
    stations = _blade_stations_from_the_mesh(case, rotor)
    if isinstance(stations, str):
        root = math.hypot(velocity, 0.0)
        return {
            **base,
            "note": (
                f"POL {case.sim_id}: the chord is not known at plan time ({stations}); "
                "the post computes k per station from the sectional loads export"
            ),
            "k_per_chord_m_root": abs(omega) / (2.0 * root) if root > 0.0 else None,
            "k_per_chord_m_tip": abs(omega) / (2.0 * tip_speed),
        }
    radii, chords = stations
    try:
        frequencies = _qsteady.reduced_frequencies(
            radii, chords, omega_rad_s=omega, velocity_m_per_s=velocity, source="mesh"
        )
    except CampaignConfigError as error:
        return {**base, "note": f"POL {case.sim_id}: {error}"}
    return {
        **base,
        **frequencies.record(),
        "note": None,
        "radius_m": list(frequencies.radii_m),
        "chord_m": list(frequencies.chords_m),
        "k": list(frequencies.k),
    }


#: Stations of the blade read for the inflow's harmonics when the mesh gives
#: none: equal bands from this fraction of the tip radius to the tip.
_INFLOW_FFT_ROOT_FRACTION = 0.2


def qsteady_inflow_fft(case: SimCase) -> dict[str, object] | None:
    """Return the harmonic content of a quasi-steady wheel's custom inflow (``plan --inflow-fft``).

    For each station of blade one (the chord read off the mesh, as
    :func:`qsteady_validity` reads it; else equal bands from 0.2 of the tip
    radius to the tip, and no ``k_eff``), the angle-of-attack perturbation ONE
    BLADE meets over one revolution in the row's custom inflow, with the
    rotation composed, and its harmonic order ``n95``
    (:func:`pyflightstream.cases.qsteady.blade_inflow_harmonics`);
    ``k_eff = n95 k_1P`` per station; ``n_max``, the highest ``n95``; and the
    suggested ``PASSAGE_POSITIONS >= n_max / N + 1`` beside the row's own.

    nP IS COUNTED ON THE BLADE: how many times one blade meets the
    perturbation per revolution. It is not the blade-passing N P a fixed
    surface near the rotor feels, nor what a balance under the whole rotor
    measures (only the multiples of N P survive in the rotor's total, which is
    why the clockings are read against ``n_max / N``).

    NEVER RAISES for a row the builder would refuse: a point that is not a
    quasi-steady wheel with a custom inflow returns None, and a field that
    cannot be read returns a record whose ``note`` says why.

    Parameters
    ----------
    case : SimCase
        The point's case; it must be a ``qsteady_rotor`` wheel in a custom
        inflow for a record to be produced.

    Returns
    -------
    dict of str to object or None
        The harmonic record (per-station ``n95`` and ``k_eff``, ``n_max``,
        the suggested ``PASSAGE_POSITIONS`` and a ``note``); None for a point
        that is not a quasi-steady wheel with a custom inflow.
    """
    if case.recipe != QSTEADY_ROTOR:
        return None
    try:
        if qsteady_case_kind(case) != "wheel":
            return None
        custom = _the_custom_freestream(case)
        if custom is None:
            return None
        rotor = _the_isolated_rotor(case)
        rpm = float(_qsteady_speed(case, rotor).rpm)
        velocity = _velocity(case)
        stated = _variable(case, PASSAGE_POSITIONS_VARIABLE)
        declared = _passage_positions(case, "wheel") if stated is not None else None
    except CampaignConfigError:
        return None
    omega = rpm * RAD_PER_S_PER_REV_PER_MIN
    from ..freestream import field_rows_in_metres

    unit = getattr(case.mesh_import, "units", None)
    native = str(unit) if unit else None
    try:
        _, rows = field_rows_in_metres(
            Path(custom.path),
            form=custom.form,
            source_units=custom.source_units,
            native_unit=native,
        )
    except (CampaignConfigError, OSError, UnicodeError) as error:
        return {"note": f"POL {case.sim_id}: the custom inflow cannot be read: {error}"}
    stations = _blade_stations_from_the_mesh(case, rotor)
    if isinstance(stations, str):
        tip = rotor.diameter_m / 2.0
        count = _qsteady.DEFAULT_STATIONS
        low = _INFLOW_FFT_ROOT_FRACTION * tip
        width = (tip - low) / count
        radii: tuple[float, ...] = tuple(low + (i + 0.5) * width for i in range(count))
        k_1p: tuple[float, ...] | None = None
        note: str | None = (
            f"POL {case.sim_id}: the chord is not known at plan time ({stations}), so k_eff is "
            "not computed; the harmonics are read at equal bands from 0.2 R to the tip"
        )
    else:
        radii, chords = stations
        try:
            frequencies = _qsteady.reduced_frequencies(
                radii, chords, omega_rad_s=omega, velocity_m_per_s=velocity, source="mesh"
            )
        except CampaignConfigError as error:
            radii, k_1p, note = tuple(radii), None, f"POL {case.sim_id}: {error}"
        else:
            radii, k_1p, note = frequencies.radii_m, frequencies.k, None
    orders = _qsteady.blade_inflow_harmonics(
        rows, hub=rotor.origin, axis=rotor.axis_vector, omega_rad_s=omega, radii_m=radii
    )
    harmonics = _qsteady.InflowHarmonics(
        radii_m=tuple(radii),
        n95=orders,
        k_1p=k_1p,
        strips_m=_qsteady.strip_lengths(radii),
        blades=rotor.blade_count,
    )
    return {**harmonics.record(declared_positions=declared), "note": note}


def _park_the_qsteady_record(
    case: SimCase,
    script: Script,
    conventions: WorkflowConventions,
    *,
    kind: str,
    rotor: RotorBlock,
    speed: RotorSpeed,
    angles: Sequence[float],
) -> str:
    """Park the point's quasi-steady record for the run to write beside its exports.

    One JSON file per point, ``<loads stem>_qsteady.json``, in the folder the
    point runs in: the case (sector or wheel), the rotor, its speed, each
    clocking with the loads export it wrote, and the validity record of a wheel
    (:func:`qsteady_validity`). The post stage reads it; the solver never does.

    Returns
    -------
    str
        The point's own loads export, from which every clocking's is named.
    """
    names = list(conventions.outputs or case.outputs)
    kinds = classify_outputs(names)
    loads = kinds.get("loads")
    if loads is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} declares outputs {names or 'nothing'} and none of them is a "
            "loads table; every row leaves one, and each clocking of a quasi-steady wheel is "
            "named after it."
        )
    sign = 1.0 if speed.rpm >= 0.0 else -1.0
    wheel_sections = kind == "wheel" and bool(_clocking_section_exports(conventions, case, 0))
    # ONE TYPE FOR THE WRITER AND THE READERS (0.31.0): the file is the typed
    # record's own text, so what `read_qsteady_record` reads back is what was
    # written, key for key and in the same order.
    record = _qsteady.QsteadyRecord(
        case=kind,
        rotor_alias=rotor.alias,
        blades=rotor.blade_count,
        rpm=speed.rpm,
        shaft_frame_axis=_the_shaft_letter(rotor),
        hub_m=rotor.origin,
        axis_vector=rotor.axis_vector,
        diameter_m=rotor.diameter_m,
        families_general=tuple(rotor.families_general),
        families_blades=tuple(rotor.families_blades),
        blade1_azimuth_deg=rotor.blade1.azimuth_deg,
        positions=tuple(
            _qsteady.QsteadyClocking(
                index=index,
                clocking_deg=angle,
                rotated_deg=sign * angle,
                loads=loads if index == 0 else _qsteady.position_loads_name(loads, index),
                # 0.31.0: A WHEEL THAT CUTS SECTIONS EXPORTS THEM AT EVERY CLOCKING,
                # and the record names each clocking's files, so the post reads
                # the names the script wrote rather than composing them again.
                # Every other record holds no such key and keeps 0.30.0's bytes.
                section_exports=(
                    {
                        each: name
                        for each, _, name in _clocking_section_exports(conventions, case, index)
                    }
                    if wheel_sections
                    else None
                ),
            )
            for index, angle in enumerate(angles)
        ),
        validity=qsteady_validity(case),
    )
    script._pending_input_files[_qsteady.record_file_name(loads)] = record.to_text()
    return loads


#: The export kinds that read the section distributions, which a clocked wheel
#: writes at EVERY clocking since 0.31.0: the sections' Cp, their sectional
#: loads and the section Cp plot, where the row declares them.
_CLOCKED_SECTION_KINDS: frozenset[str] = frozenset(
    {"sections", "sectional_loads", "plot_sections_cp"}
)


def _clocking_section_exports(
    conventions: WorkflowConventions, case: SimCase, index: int
) -> list[tuple[str, str, str]]:
    """Return ``(kind, verb, name)`` of each section export a wheel writes at clocking ``index``.

    The kinds of :data:`_CLOCKED_SECTION_KINDS` the row declares, in the order
    :data:`~pyflightstream.cases.EXPORT_KINDS` lists them; at clocking 0 the
    point's own names, at clocking i each name with ``_qs<i>`` before its
    kind's suffix (:func:`pyflightstream.cases.qsteady.position_export_name`).
    Empty where the pproc declares no section distribution, since there is
    then nothing to cut. The one home of these names: the script writes them
    and the quasi-steady record states them for the post.
    """
    if case.pproc is None or not case.pproc.sections.distributions:
        return []
    _, kinds = _declared_export_kinds(conventions, case, unsteady=False)
    return [
        (
            kind,
            verb,
            kinds[kind]
            if index == 0
            else _qsteady.position_export_name(kinds[kind], suffix, index),
        )
        for kind, suffix, verb, _ in EXPORT_KINDS
        if kind in _CLOCKED_SECTION_KINDS and kind in kinds
    ]


def _solve_one_clocking(
    case: SimCase,
    script: Script,
    conventions: WorkflowConventions,
    loads: str,
    index: int,
) -> None:
    """Solve the wheel at clocking ``index`` and export its loads and its section distributions.

    The point's full export set is written once, at clocking 0, which is solved
    LAST so that the solver log and the loads export the run judges the point
    by are of one solve. Every other clocking exports its loads, named
    ``<loads stem>_qs<i>``, and since 0.31.0 the section exports the row
    declares (:func:`_clocking_section_exports`), after the updates they read,
    so a wheel's radial loads exist at every clocking and not at clocking 0
    alone.
    """
    helpers.start_solver(script)
    _setup_link.loads_selections(case, script)
    if case.solver.clear_vorticity_drag_boundaries:
        script.emit("DELETE_VORTICITY_DRAG_BOUNDARIES")
    sections = _clocking_section_exports(conventions, case, index)
    if sections:
        script.emit("UPDATE_ALL_SURFACE_SECTIONS")
        script.emit("COMPUTE_SURFACE_SECTIONAL_LOADS", "NEWTONS")
    script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", _qsteady.position_loads_name(loads, index))
    for kind, verb, name in sections:
        if not _surface_export(script, case, kind, name):
            script.emit(verb, name)


def _turned_about(
    vector: Sequence[float], axis: Sequence[float], angle_deg: float
) -> tuple[float, float, float]:
    """Return ``vector`` turned right-handed about the direction ``axis`` by ``angle_deg``.

    Rodrigues' rotation, the axis normalised here; each component is rounded to
    twelve decimals, so a frame turned by a whole passage reads as the axes it
    is and not as their last-bit residue.

    Examples
    --------
    >>> _turned_about((0.0, 1.0, 0.0), (1.0, 0.0, 0.0), 90.0)
    (0.0, 0.0, 1.0)
    """
    norm = math.sqrt(sum(float(value) ** 2 for value in axis))
    kx, ky, kz = (float(value) / norm for value in axis)
    vx, vy, vz = (float(value) for value in vector)
    cos, sin = math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg))
    dot = kx * vx + ky * vy + kz * vz
    cross = (ky * vz - kz * vy, kz * vx - kx * vz, kx * vy - ky * vx)
    x, y, z = (
        round(v * cos + c * sin + k * dot * (1.0 - cos), 12) + 0.0
        for v, c, k in zip((vx, vy, vz), cross, (kx, ky, kz), strict=True)
    )
    return x, y, z


def _placement_of(case: SimCase, script: Script, index: int, name: str) -> FramePlacement:
    """Return where the script placed frame ``index``, refusing a frame it cannot place.

    A clocked wheel places each of its section frames from a frame the script
    already placed, turned about the shaft; a frame whose origin or axes the
    script does not know (a turn the ledger does not follow, a frame of the
    saved simulation) cannot be turned with the blades, and a distribution
    created in it would cut the blade where RPT-091 measured it cut: outside
    its span.
    """
    placement = script.frame_placements.get(index)
    if placement is None or placement.origin is None or placement.axes is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: a quasi-steady wheel solved at several clockings creates "
            "its section distributions again at each clocking, each in its frame turned with "
            f"the blades, and the script does not know where frame {name!r} (index {index}) "
            "stands, so it cannot turn it. Cite a frame the setup places by its origin and "
            "axes, such as the rotor's <ALIAS>_SMRP or LOCAL_AXIS, or solve one clocking."
        )
    return placement


def _qsteady_blade_frames(
    case: SimCase, script: Script, rotor: RotorBlock, rotor_frame: int
) -> dict[str, int]:
    """Place ``<ALIAS>_RMRP<k>`` for each blade of a wheel the mesh carries, fixed (0.31.0).

    Blade k of N at the hub, its axes the hub frame's turned right-handed about
    the shaft by ``blade1.azimuth_deg + (k - 1) * 360 / N``, which is where the
    blade frames of a turning rotor start (:func:`_rotor_blade_frames`). They
    are written by their axes rather than by a turn of a copy, because the
    solver's sense of ``ROTATE_COORDINATE_SYSTEM`` is not stated by the manual
    and the frames of each clocking are turned from these. Nothing moves them:
    a steady run has no motion, so a ``LOCAL_AXIS`` distribution of a wheel is
    cut in a frame that holds the pose it was placed in.
    """
    hub = _placement_of(case, script, rotor_frame, f"{rotor.alias}_SMRP")
    assert hub.origin is not None and hub.axes is not None
    shaft = hub.axes["XYZ".index(_the_shaft_letter(rotor))]
    inventory = set(_inventory(script))
    created: dict[str, int] = {}
    for number, family in enumerate(rotor.families_blades, start=1):
        if family not in inventory:
            continue
        angle = rotor.blade1.azimuth_deg + (number - 1) * 360.0 / rotor.blade_count
        x_axis, y_axis, z_axis = (_turned_about(each, shaft, angle) for each in hub.axes)
        created[f"{rotor.alias}_RMRP{number}"] = helpers.coordinate_frame(
            script,
            name=f"{rotor.alias}_RMRP{number}",
            origin=hub.origin,
            x_axis=x_axis,
            y_axis=y_axis,
            z_axis=z_axis,
            label=f"blade_axis:{family}",
        )
    return created


def _section_frame_names(case: SimCase, script: Script, frames: Frames) -> list[str]:
    """Return the frames the pproc's section distributions are created in, each once.

    Read by the one expansion the distributions are emitted by
    (:func:`pproc_emissions`), so a frame is turned for a clocking exactly
    when a distribution is created in it. Its warnings are the emission's
    own, said when the distributions are created, and dropped here.
    """
    pproc = case.pproc
    if pproc is None:
        return []
    inventory = _inventory(script)
    names: list[str] = []
    with collecting_warnings():
        for position, entry in enumerate(pproc.sections.distributions, start=1):
            for name, _families, _label in pproc_emissions(
                case,
                entry.frame,
                entry.families,
                inventory,
                pproc.is_blade,
                f"section distribution {position}",
                frames,
                blades_only=True,
            ):
                if isinstance(frames.get(name), int) and name not in names:
                    names.append(name)
    return names


def _qsteady_section_frames(
    case: SimCase,
    script: Script,
    frames: dict[str, int | None | Mapping[str, int]],
    *,
    rotor: RotorBlock,
    rotor_frame: int,
    angles: Sequence[float],
    sense: float,
) -> list[Frames]:
    """Place the frames each clocking of a wheel cuts its sections in, and return them (0.31.0).

    One mapping per clocking, by index. The solver fixes a distribution's cuts
    at its creation, over the extent of its surfaces along the plane's normal
    in the pose they then hold (RPT-091, 24edb353), and a frame on a steady
    run does not turn with the surfaces. So clocking i cites each frame of its
    distributions TURNED with the wheel: the same frame placed again, its
    origin and axes turned right-handed about the shaft through the hub by
    ``sense * theta_i``, the turn ``ROTATE_SURFACE`` gives the blades, and
    held there. The blade then spans the same interval along the turned
    normal at every clocking, so every clocking is cut at the same stations.
    Clocking 0 cites the frames as placed. A wheel whose pproc cites
    ``LOCAL_AXIS`` first gets its blade frames (:func:`_qsteady_blade_frames`),
    added to ``frames``.

    Every frame is created here, in the setup phase, so no frame is placed
    after the solver initialised.
    """
    pproc = case.pproc
    if pproc is None or not pproc.sections.distributions:
        return [frames] * len(angles)
    if any(
        EXPANDING_FRAMES.get(entry.frame.strip().upper()) == "blade"
        for entry in pproc.sections.distributions
    ):
        frames.update(_qsteady_blade_frames(case, script, rotor, rotor_frame))
    if len(angles) == 1:
        return [frames]
    hub = _placement_of(case, script, rotor_frame, f"{rotor.alias}_SMRP")
    assert hub.origin is not None and hub.axes is not None
    shaft = hub.axes["XYZ".index(_the_shaft_letter(rotor))]
    placed: dict[str, FramePlacement] = {}
    for name in _section_frame_names(case, script, frames):
        index = frames[name]
        assert isinstance(index, int)
        placed[name] = _placement_of(case, script, index, name)
    by_clocking: list[Frames] = [frames]
    for position, angle in enumerate(angles[1:], start=1):
        turn = sense * angle
        turned: dict[str, int | None | Mapping[str, int]] = dict(frames)
        for name, placement in placed.items():
            assert placement.origin is not None and placement.axes is not None
            arm = [a - b for a, b in zip(placement.origin, hub.origin, strict=True)]
            origin = [
                round(a + b, 12) + 0.0
                for a, b in zip(hub.origin, _turned_about(arm, shaft, turn), strict=True)
            ]
            x_axis, y_axis, z_axis = (_turned_about(each, shaft, turn) for each in placement.axes)
            turned[name] = helpers.coordinate_frame(
                script,
                name=f"{name}{_qsteady.POSITION_SUFFIX.upper()}{position:02d}",
                origin=origin,
                x_axis=x_axis,
                y_axis=y_axis,
                z_axis=z_axis,
                label=f"qsteady_clocking:{name}:{position}",
            )
        by_clocking.append(turned)
    return by_clocking


def _delete_the_clocking_sections(script: Script) -> None:
    """Delete every surface section, so the next clocking's distributions are the only ones.

    A clocked wheel creates its distributions again at each clocking, and the
    previous clocking's would otherwise be exported beside them.
    ``DELETE_ALL_SURFACE_SECTIONS`` is an analysis command, so the point the
    next clocking opens starts at init again after it (:meth:`Script.begin_point`).
    """
    script.emit("DELETE_ALL_SURFACE_SECTIONS")
    script.begin_point()


def _cut_the_clocking_sections(
    case: SimCase, script: Script, frames: Frames, *, quiet: bool
) -> None:
    """Create a clocking's section distributions in its frames, recording only this set.

    The run records one layout for the point, and every clocking cuts the same
    distributions, so the record keeps the last set created, clocking 0's, in
    the frames the pproc names. ``quiet`` drops the emission's warnings, which
    the first clocking already said.
    """
    script.section_blocks.clear()
    if not quiet:
        _pproc_sections(case, script, frames)
        return
    with collecting_warnings():
        _pproc_sections(case, script, frames)


def _build_qsteady_rotor(case: SimCase, script: Script, conventions: WorkflowConventions) -> None:
    """Build a quasi-steady rotor point: blades held still, the free stream turning.

    THE SECTOR (``SYMMETRY PERIODIC``): the steady build of one blade in the
    rotating free stream (:func:`_qsteady_free_stream`), solved once.

    THE WHEEL (no symmetry): every blade, the same free stream, solved at each
    clocking ``theta_i = i * (360 / N) / k`` of ``PASSAGE_POSITIONS`` (k),
    which the post stage averages. The rotor's surfaces are clocked about its
    shaft in its hub frame, in the sense of its rotation, so blade one's
    azimuth advances by ``theta_i``. Every clocking is emitted after an
    initialisation, through the one door past the phase guard
    (:meth:`~pyflightstream.script.Script.emit_after_initialization`), and the
    solver is initialised again with the first initialisation's settings.
    Clocking 1 too: the solver freezes a section distribution's cut planes at
    its creation against the pose the surfaces then hold, spread over their
    extent along the plane's normal (L1, RPT-091: created at clocking 1 of a
    six-blade wheel, 30 deg, in a frame that did not turn, the 30 cuts ran from
    0.347 to 1.586 m on a blade spanning 0.41 to 1.824 m). So since 0.31.0 each
    clocking deletes the previous clocking's distributions, turns the wheel,
    initialises, and creates them again in its own frames, placed in the setup
    turned with the wheel and fixed there (:func:`_qsteady_section_frames`):
    the blade spans the same interval along every clocking's normal, and each
    clocking is cut at the same stations. The wheel returns to clocking 0 last
    and is solved there with the point's full export set, so a single clocking
    (k = 1) is the plain steady build. Clockings 1 to k - 1 export their loads,
    each named ``<loads stem>_qs<i>``
    (:func:`pyflightstream.cases.qsteady.position_loads_name`), and the section
    exports the row declares, each with ``_qs<i>`` before its suffix
    (:func:`_clocking_section_exports`).

    Every point parks its quasi-steady record (:func:`_park_the_qsteady_record`).
    """
    _refuse_wake_termination_without_a_clock(case)
    _refuse_a_coupling_step_without_a_clock(case)
    unsteady_export_threshold(case, conventions, version=script.version)
    kind = qsteady_case_kind(case)
    rotor = _the_isolated_rotor(case)
    _refuse_fsi_on_a_quasi_steady_rotor(case, kind)
    if kind == "sector":
        _refuse_an_azimuthal_inflow_on_a_sector(case)
    positions = _passage_positions(case, kind)
    speed = _qsteady_speed(case, rotor)
    _refuse_unregistered_keys(case, QSTEADY_ROTOR)
    custom = _the_custom_freestream(case)
    angles = _qsteady.clocking_angles(rotor.blade_count, positions)
    _raw_commands(case, script, "control")
    _custom_flags(case, script, "control")
    _raw_commands(case, script, "geometry")
    _custom_flags(case, script, "geometry")
    _open_geometry(case, script)
    _raw_commands(case, script, "setup")
    _custom_flags(case, script, "setup")
    surfaces = _refuse_what_is_not_the_rotor(case, script, rotor, kind)
    frame = _moment_frame(case, script)
    rotor_frame = _rotor_frame(case, script)
    assert rotor_frame is not None  # One rotor block is declared, so its hub frame is created.
    rotor_frames = _flat_rotor_frames(case, rotor_frame)
    frames: dict[str, int | None | Mapping[str, int]] = {"MRP": frame, **rotor_frames}
    setup_frames = _setup_frames(case, script)
    frames.update(setup_frames)
    moved = {"MRP": frame, **rotor_frames, **setup_frames}
    frames.update(_translations(case, script, moved))
    frames.update(_rotations(case, script, moved))
    loads = _park_the_qsteady_record(
        case, script, conventions, kind=kind, rotor=rotor, speed=speed, angles=angles
    )
    axis = _the_shaft_letter(rotor)
    sense = 1.0 if speed.rpm >= 0.0 else -1.0
    selection: Sequence[int] | Literal["all"] = surfaces or "all"
    section_frames = (
        _qsteady_section_frames(
            case,
            script,
            frames,
            rotor=rotor,
            rotor_frame=rotor_frame,
            angles=angles,
            sense=sense,
        )
        if kind == "wheel"
        else [frames] * len(angles)
    )

    def clock(angle: float, *, after_initialization: bool) -> None:
        helpers.rotate_surfaces(
            script,
            frame=rotor_frame,
            axis=axis,
            angle_deg=sense * angle,
            boundaries=selection,
            after_initialization=after_initialization,
        )

    _significant_digits(case, script)
    _qsteady_free_stream(
        case, script, rotor_frame=rotor_frame, rotor=rotor, speed=speed, custom=custom, kind=kind
    )
    _fluid(case, script)
    _settings(case, script)
    if len(angles) == 1:
        _script_tail(conventions, case, script, frame, unsteady=False, frames=frames)
        return
    # EACH CLOCKING CUTS ITS OWN SECTIONS (0.31.0): the init phase creates none,
    # and every clocking, 1 to k - 1 and then 0, deletes the previous clocking's
    # distributions, turns the wheel, initialises again and creates them in its
    # own frames, so none accumulates and each is cut over the blade's span.
    sectioned = case.pproc is not None and bool(case.pproc.sections.distributions)
    _script_init(case, script, frame, frames=frames, sections=not sectioned)
    previous = 0
    for turn, index in enumerate((*range(1, len(angles)), 0)):
        if turn:
            script.begin_point()
            if sectioned:
                _delete_the_clocking_sections(script)
        clock(angles[index] - angles[previous], after_initialization=True)
        previous = index
        _initialize(case, script)
        if sectioned:
            _cut_the_clocking_sections(case, script, section_frames[index], quiet=turn > 0)
        _analysis(case, script, frame)
        if index:
            _solve_one_clocking(case, script, conventions, loads, index)
    _script_solve_and_export(conventions, case, script, unsteady=False, frames=frames)
    script.emit("CLOSE_FLIGHTSTREAM")
    _finish_custom_field_coverage(case, script)
