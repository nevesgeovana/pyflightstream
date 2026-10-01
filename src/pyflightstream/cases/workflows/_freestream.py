"""The free stream: uniform, rotating or a custom field, and the fluid.

:func:`_free_stream` emits the uniform free stream of a row,
:func:`_the_custom_freestream` a custom field read from the workspace's
``freestream/`` files, and :func:`_fluid` the fluid properties; the body
extent the custom field must cover is measured here, and so is the
coverage check a run finishes with.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import (
    Mapping,
)
from dataclasses import (
    dataclass,
)
from pathlib import (
    Path,
)
from types import (
    MappingProxyType,
)

from pyflightstream._errors import (
    PyflightstreamWarning,
    warn,
)
from pyflightstream._fsm import (
    MeshReadError,
    saved_mesh_coordinate_unit,
    surface_mesh,
)
from pyflightstream._lengths import (
    scale,
)
from pyflightstream.cases import (
    CampaignConfigError,
    SimCase,
)
from pyflightstream.script import (
    Script,
    helpers,
)

from ._rows import (
    _angle,
    _from_metres,
    _turning_rate,
    _variable,
)
from ._timing import (
    TimeStepping,
)
from ._vocabulary import (
    _DEG_PER_S_TO_RPM,
    ADVANCE_RATIO_VARIABLE,
    ALPHA_VARIABLE,
    BETA_VARIABLE,
    FREESTREAM_DIR,
    FREESTREAM_FORMS,
    FREESTREAM_ROTATION_SIGN,
    FREESTREAM_UNITS_VARIABLE,
    FREESTREAM_VARIABLE,
    MOTIONS_VARIABLE,
    RATE_VARIABLES,
    ROTATE_VARIABLE,
    RPM_VARIABLE,
    TRANSLATE_VARIABLE,
    Frames,
)

#: What each form of a custom free-stream file is, in the words a refusal
#: ends on, so a refused user reads the form beside the line that broke it.
_FREESTREAM_FORM_TEXT: Mapping[str, str] = MappingProxyType(
    {
        "STRUCTURED": (
            "The manual's STRUCTURED form (a .txt) is a first line 'Npts Mpts', two "
            "positive integers, then Npts x Mpts rows 'x y z vx vy vz', the first index "
            "outer and the second inner, in m and m/s in the global frame."
        ),
        "UNSTRUCTURED": (
            "The manual's UNSTRUCTURED form (a .dat) is one row 'x y z vx vy vz' per "
            "vertex and no header, in m and m/s in the global frame."
        ),
    }
)

#: A number as the manual prints one: a sign, digits with a decimal point, an
#: exponent. Nothing a solver's reader might not take: no underscore, no word.
_FIELD_NUMBER = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
#: A count of the STRUCTURED header: digits, and nothing a float would carry.
_FIELD_COUNT = re.compile(r"\+?\d+")

#: The sentence both refusals of a custom field beside a body rate end on.
_ONE_FREE_STREAM = (
    "A run has one SET_FREESTREAM: the custom field its file describes (CUSTOM) or the "
    "free stream turning at a body rate (ROTATION), never both. Drop the rate, or the "
    "custom free stream."
)

#: THE FIELD IS THE FLOW'S DIRECTION, MEASURED (T14, 0.27.0). On FlightStream
#: 26.124 a uniform field of the row's own speed loaded as the CONSTANT free
#: stream at 0 deg, and at 4 deg it loaded near its own 0 deg self and far from
#: the CONSTANT free stream at 4 deg: ``SOLVER_SET_AOA`` does not turn a custom
#: field. A row stating an angle beside one would solve at the field's
#: incidence and report its own, so the angle is refused rather than written.
#: The sideslip is the same mechanism and was not measured; it is refused for
#: the same reason. The sentence every such refusal ends on.
_NO_ANGLE_BESIDE_A_FIELD = (
    "The custom field sets the flow's direction: SOLVER_SET_AOA does not turn it, measured "
    "on FlightStream 26.124 by the licensed probe T14 (RPT-071), and the sideslip, not "
    "measured, is refused for the same reason. The run would solve at the field's own "
    "incidence and report the angle the row states. Write the incidence into the field's "
    "vy and vz components, and state ALPHA and BETA as 0 in the row."
)


def _an_angle_beside_a_field(case: SimCase) -> str | None:
    """Name the non-zero incidence or sideslip a case states, swept or fixed, or None (G15).

    A SWEEP IS THE ROW'S, so an angle any of its points states refuses every
    point, the one at zero too: the warm sweep builds all of them from its
    first. A fixed angle is the one the builder writes, the point's or else the
    row's variable (:func:`_angle`). An angle written 0 is none.
    """
    sweep = case.sweep
    for axis, key in (("alpha", ALPHA_VARIABLE), ("beta", BETA_VARIABLE)):
        swept: list[float] = []
        for entry in sweep.values:
            if isinstance(entry, tuple | list):
                if sweep.type == "alpha_beta":
                    swept.append(float(entry[0 if axis == "alpha" else 1]))
            elif sweep.type == axis:
                swept.append(float(entry))
        if any(value != 0.0 for value in swept):
            return f"sweeps {key} over {', '.join(f'{value:g}' for value in swept)} deg"
        angle = _angle(case, axis)
        if angle != 0.0:
            return f"{key}: {angle:g} deg"
    return None


@dataclass(frozen=True)
class _RowFreestream:
    """The custom free stream a row states (G15), resolved and read before emission."""

    path: str
    form: str
    source_units: str | None = None
    extent: tuple[float, float, float, float] | None = None


def _read_custom_freestream(path: str, form: str) -> tuple[float, float, float, float]:
    """Read a custom free-stream file against the manual's form, or refuse naming the line (G15).

    Returns the grid's extent in the YZ plane, ``(y_min, y_max, z_min, z_max)`` in
    the file's declared units. The caller converts explicit native units before
    comparing with physical body bounds (G18).

    THE 26.124 MANUAL IS THE ONLY SOURCE of the form, and every check here is
    one of its sentences: the field varies within the YZ plane of the global
    frame, so every row states one x and at least two distinct y and two
    distinct z; a STRUCTURED file opens with ``Npts Mpts``, two positive
    integers, and holds exactly Npts x Mpts rows; every row is six numbers
    ``x y z vx vy vz``. A blank line carries nothing and is read past. Nothing
    is converted by this parser. Explicit source-unit declarations are handled
    separately; legacy files keep their bytes. RPT-082 measures the native
    METER/MILLIMETER custom-file boundary on the pinned build.

    Each refusal names the file, the line (1-based, blank lines counted) and
    what the form asks, since the file is the user's and the line is where
    they will look.
    """
    what = _FREESTREAM_FORM_TEXT[form]
    where = f"the custom free stream {path}"
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise CampaignConfigError(f"{where} cannot be read: {error}. {what}") from error
    lines = [
        (number, line.strip())
        for number, line in enumerate(text.splitlines(), start=1)
        if line.strip()
    ]
    if not lines:
        raise CampaignConfigError(f"{where} holds no row. {what}")
    header: tuple[int, int, int] | None = None
    if form == "STRUCTURED":
        (number, first), *lines = lines
        counts = first.split()
        if len(counts) != 2 or not all(
            _FIELD_COUNT.fullmatch(count) and int(count) > 0 for count in counts
        ):
            raise CampaignConfigError(
                f"{where}, line {number}: {first!r} is not 'Npts Mpts', two positive "
                f"integers. {what}"
            )
        header = (number, int(counts[0]), int(counts[1]))
    rows: list[tuple[int, list[float]]] = []
    for number, line in lines:
        tokens = line.split()
        if len(tokens) != 6:
            raise CampaignConfigError(
                f"{where}, line {number}: {line!r} is not six numbers 'x y z vx vy vz' (it "
                f"holds {len(tokens)}). {what}"
            )
        values = [float(token) if _FIELD_NUMBER.fullmatch(token) else math.nan for token in tokens]
        for token, value in zip(tokens, values, strict=True):
            if not math.isfinite(value):
                raise CampaignConfigError(
                    f"{where}, line {number}: {token!r} is not a finite number; each row is "
                    f"six finite numbers 'x y z vx vy vz'. {what}"
                )
        rows.append((number, values))
    if header is not None and len(rows) != header[1] * header[2]:
        number, npts, mpts = header
        raise CampaignConfigError(
            f"{where}, line {number}: 'Npts Mpts' = {npts} {mpts} asks for {npts * mpts} rows "
            f"and the file holds {len(rows)}. {what}"
        )
    first_number, first_values = rows[0]
    for number, values in rows[1:]:
        if values[0] != first_values[0]:
            raise CampaignConfigError(
                f"{where}, line {number}: x = {values[0]:g} where line {first_number} states "
                f"x = {first_values[0]:g}. The field varies within the YZ plane of the global "
                f"frame, so every row states the one x of that plane. {what}"
            )
    span = (
        f"lines {rows[0][0]} to {rows[-1][0]} state"
        if len(rows) > 1
        else f"line {rows[0][0]} states"
    )
    for axis, column in (("y", 1), ("z", 2)):
        distinct = {values[column] for _, values in rows}
        if len(distinct) < 2:
            raise CampaignConfigError(
                f"{where}: {span} one {axis} ({next(iter(distinct)):g}). The field varies "
                "within the YZ plane of the global frame, so its rows state at least two "
                f"distinct y and two distinct z. {what}"
            )
    ys = [values[1] for _, values in rows]
    zs = [values[2] for _, values in rows]
    return min(ys), max(ys), min(zs), max(zs)


def _body_vertices_m(case: SimCase) -> tuple[tuple[float, float, float], ...] | None:
    """Return physical mesh vertices in metres when their native unit contract is known.

    A saved simulation's measured internal mesh coordinates, or an OBJ's vertex
    lines in its ``[import]`` unit, converted to metres as ``IMPORT`` converts them
    (RPT-069). An STL or a file that does not read is not measured, and the
    coverage warning is then not given rather than guessed.
    """
    geometry = case.geometry
    if geometry is None or not Path(str(geometry)).is_file():
        return None
    suffix = Path(str(geometry)).suffix.lower()
    unit = getattr(case.mesh_import, "units", None)
    try:
        if suffix == ".fsm":
            vertices, _ = surface_mesh(geometry)
            stored_unit = saved_mesh_coordinate_unit(geometry)
            factor = scale(stored_unit, "METER") if stored_unit else None
        elif suffix == ".obj" and unit:
            vertices = tuple(
                (float(parts[1]), float(parts[2]), float(parts[3]))
                for parts in (
                    line.split()
                    for line in Path(str(geometry)).read_text(encoding="utf-8").splitlines()
                )
                if len(parts) >= 4 and parts[0] == "v"
            )
            factor = scale(str(unit), "METER")
        else:
            return None
    except (MeshReadError, OSError, UnicodeError, ValueError):
        return None
    if factor is None or not vertices:
        return None
    return tuple(
        (vertex[0] * factor, vertex[1] * factor, vertex[2] * factor) for vertex in vertices
    )


def _body_yz_extent_m(case: SimCase) -> tuple[float, float, float, float] | None:
    """Return the unmoved mesh's physical YZ bounds when its unit contract is known."""
    vertices = _body_vertices_m(case)
    if not vertices:
        return None
    return (
        min(v[1] for v in vertices),
        max(v[1] for v in vertices),
        min(v[2] for v in vertices),
        max(v[2] for v in vertices),
    )


def _how_the_row_moves_the_body(case: SimCase) -> list[str]:
    """Name what, in this row, moves the body away from where its file holds it (G18)."""
    moved = [
        key
        for key in (ROTATE_VARIABLE, TRANSLATE_VARIABLE, MOTIONS_VARIABLE)
        if _variable(case, key)
    ]
    for key, records in (
        (ROTATE_VARIABLE, case.rotations),
        (TRANSLATE_VARIABLE, case.translations),
        (MOTIONS_VARIABLE, case.motions),
    ):
        if records and key not in moved:
            moved.append(key)
    if case.recipe == "unsteady_rotor" and MOTIONS_VARIABLE not in moved:
        moved.append(MOTIONS_VARIABLE)
    operations = getattr(case.mesh_import, "operations", None) or ()
    moved += sorted({f"the import's {op.op}" for op in operations if op.op != "rename"})
    return moved


def _warn_when_the_field_misses_the_body(
    case: SimCase, stated: str, grid: tuple[float, float, float, float]
) -> None:
    """Warn when the field's grid does not cover the body's y and z extent (G18, RPT-077).

    Measured on 26.124 (RPT-077): beyond its grid the solver neither extends a field
    linearly nor holds its edge station, and what it applies there is close to the
    constant free stream the script states. A body that reaches past the grid is
    therefore loaded, silently, partly by the field and partly by something near the
    free stream. A field meant as a local gust may do exactly that, so this warns and
    does not refuse.

    A ROW THAT MOVES THE BODY IS NOT COMPARED (reading B30): the extent read here is
    the body as its file holds it, and a row's ROTATE or TRANSLATE, its rotor MOTIONS
    or its import operations place it elsewhere before the solve. Comparing the
    unmoved body said nothing about a wing translated 20 m out of the field, so such
    a row is told the coverage was not checked, and why.
    """
    y_min, y_max, z_min, z_max = grid
    moved = _how_the_row_moves_the_body(case)
    if moved:
        warn(
            f"case {case.sim_id!r}: {stated} covers y from {y_min:g} to {y_max:g} m and z from "
            f"{z_min:g} to {z_max:g} m, and the row moves the body ({', '.join(moved)}), so "
            "whether the field covers it where it is solved is not checked. Beyond its grid "
            "the solver does not extend a field (measured on FlightStream 26.124, RPT-077): "
            "make the grid reach past the body where the row places it.",
            PyflightstreamWarning,
            stacklevel=2,
        )
        return
    body = _body_yz_extent_m(case)
    if body is None:
        return
    b_y_min, b_y_max, b_z_min, b_z_max = body
    if b_y_min >= y_min and b_y_max <= y_max and b_z_min >= z_min and b_z_max <= z_max:
        return
    warn(
        f"case {case.sim_id!r}: {stated} covers y from {y_min:g} to {y_max:g} m and z from "
        f"{z_min:g} to {z_max:g} m, and the body reaches y from {b_y_min:.4g} to {b_y_max:.4g} m "
        f"and z from {b_z_min:.4g} to {b_z_max:.4g} m. Beyond its grid the solver does not "
        "extend a field, and what it applies there is close to the constant free stream "
        "(measured on FlightStream 26.124, RPT-077), so the part of the body outside the "
        "grid is not loaded by the field. Extend the grid past the body if the whole body "
        "should see it.",
        PyflightstreamWarning,
        stacklevel=2,
    )


def _the_custom_freestream(case: SimCase) -> _RowFreestream | None:
    """Resolve and read the row's custom free stream, or refuse naming why (G15).

    CALLED BEFORE THE FIRST EMISSION by every builder that writes a free
    stream, so a row whose field cannot be written is refused with nothing
    written; the plan builds every point's script, so this is the plan's
    refusal too. The statement is the case's ``freestream_profile``, the
    file's absolute path, which the workspace binds from a row's
    ``FREESTREAM`` and a case built in Python sets itself. A case stating
    neither returns None and writes the free stream it always wrote.

    Refused, each by name: the key with no resolved file; a key and a file
    of two stems; a swept body rate or a non-zero one, since each writes
    ``ROTATION`` and a run has one ``SET_FREESTREAM``; a non-zero angle of
    attack or sideslip, swept or fixed, since the field sets the flow's
    direction (T14, :data:`_NO_ANGLE_BESIDE_A_FIELD`); a file that is neither
    of the two forms the manual ties to an extension, or no longer there; and
    a file not in its form (:func:`_read_custom_freestream`).
    """
    stem = _variable(case, FREESTREAM_VARIABLE)
    path = case.freestream_profile
    if stem is None and path is None:
        if case.freestream_units or _variable(case, FREESTREAM_UNITS_VARIABLE):
            raise CampaignConfigError("FREESTREAM_UNITS requires a custom field file.")
        return None
    if path is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {FREESTREAM_VARIABLE}: {stem} and carries no resolved "
            f"file. A matrix row's {FREESTREAM_VARIABLE} is resolved against the workspace's "
            f"inputs/{FREESTREAM_DIR}/ when the row binds; a case built in Python sets "
            "freestream_profile to the file's absolute path."
        )
    file = Path(path)
    if stem is not None and stem != file.stem:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {FREESTREAM_VARIABLE}: {stem} and carries the file "
            f"{path}, whose stem is {file.stem!r}. The key names its file by the stem; state "
            "the two alike."
        )
    stated = (
        f"{FREESTREAM_VARIABLE}: {stem}" if stem is not None else f"the custom free stream {path}"
    )
    if case.sweep.type in {key for key, _ in RATE_VARIABLES}:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {stated} and sweeps {case.sweep.type}. {_ONE_FREE_STREAM}"
        )
    turning = _turning_rate(case)
    if turning is not None:
        key, _, rate = turning
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {stated} and {key}: {rate:g} deg/s. {_ONE_FREE_STREAM}"
        )
    angled = _an_angle_beside_a_field(case)
    if angled is not None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {stated} and {angled}. {_NO_ANGLE_BESIDE_A_FIELD}"
        )
    form = FREESTREAM_FORMS.get(file.suffix.lower())
    if form is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the custom free stream {path} is neither a .txt (the "
            "STRUCTURED form) nor a .dat (the UNSTRUCTURED form); the manual ties each form of "
            "SET_FREESTREAM CUSTOM to its extension."
        )
    if not file.is_file():
        raise CampaignConfigError(
            f"case {case.sim_id!r}: the custom free stream {path} is not a file. A row's "
            f"{FREESTREAM_VARIABLE} resolves to a file of inputs/{FREESTREAM_DIR}/ when the "
            "row binds, and the file is read where it lives."
        )
    grid = _read_custom_freestream(path, form)
    declaration = _variable(case, FREESTREAM_UNITS_VARIABLE)
    if declaration is not None and declaration not in {"SI", "NATIVE"}:
        raise CampaignConfigError("FREESTREAM_UNITS must be SI or NATIVE.")
    if declaration and case.freestream_units and declaration != case.freestream_units:
        raise CampaignConfigError("FREESTREAM_UNITS conflicts with freestream_units.")
    return _RowFreestream(
        path=path, form=form, source_units=declaration or case.freestream_units, extent=grid
    )


def _free_stream(
    case: SimCase, script: Script, frames: Frames, custom: _RowFreestream | None
) -> None:
    """Emit the free-stream definition: CUSTOM, CONSTANT, or ROTATION where a rate turns it.

    A ROW STATING A CUSTOM FIELD WRITES IT (G15): ``SET_FREESTREAM CUSTOM``
    with the form its file's extension states, and the file's absolute path
    on the next line, in place of ``CONSTANT``. ``custom`` is what
    :func:`_the_custom_freestream` resolved before the first emission, which
    also refused it beside a body rate. It is a required argument, so a
    builder cannot reach this line without having asked.

    A row states ONE body rate in
    deg/s, in flight-mechanics signs, and the free stream turns about the
    MOMENT REFERENCE POINT of the row's REF at that rate: it is how a run
    states a pull-up, a roll or a yaw rather than straight flight. Which axis
    of the model that is belongs to the CONFIGURATION and not to the row, so
    the reference declares it in ``[body_axes]`` and a reference declaring none
    is a configuration no row may turn.

    Every rate zero, or no rate at all, emits CONSTANT: a row written before
    this release renders exactly what it rendered before.

    The rotation is emitted with the sign of its body axis in the geometry's
    frame, ``FREESTREAM_ROTATION_SIGN``: roll and yaw are NEGATED and pitch is
    not, because forward is -x and down is -z of a frame that points aft and
    up (G13, 0.27.0; RPT-052 and RPT-060 measured the sense on 26.124).
    """
    if custom is not None:
        from ..freestream import prepare_field

        # THE OPENED SIMULATION'S UNIT IS READ BEFORE THE FIELD IS PREPARED. The
        # unit of a saved simulation is recorded on the script only when a length
        # is first converted (:func:`_from_metres`), and on a row carrying no
        # reference, frame or disc that first conversion was in `_settings`, AFTER
        # this branch: an SI field on an opened metre or millimetre `.fsm` was
        # refused as having no measured unit (GOAL-034 Q0-src-cases-3).
        if custom.source_units == "SI" or custom.extent is not None:
            _from_metres(case, script, "the custom field's coordinates and velocities")
        field = prepare_field(
            Path(custom.path),
            form=custom.form,
            source_units=custom.source_units,
            native_unit=script.simulation_length_unit,
        )
        if custom.extent is not None:
            grid = custom.extent
            if custom.source_units == "NATIVE":
                factor = _from_metres(case, script, "custom field extent")
                grid = (grid[0] / factor, grid[1] / factor, grid[2] / factor, grid[3] / factor)
            if custom.source_units is None and script.simulation_length_unit == "MILLIMETER":
                warn(
                    "Custom-field coverage is not checked: declare FREESTREAM_UNITS as SI "
                    "or NATIVE for a MILLIMETER simulation.",
                    PyflightstreamWarning,
                    stacklevel=2,
                )
            else:
                script.custom_field_extent_m = grid
                if not _how_the_row_moves_the_body(case):
                    _warn_when_the_field_misses_the_body(case, "custom free stream", grid)
        if field.payload is not None:
            existing = script.pending_input_files.get(field.path)
            if existing is not None and existing != field.payload:
                raise CampaignConfigError("The prepared custom field conflicts with another input.")
            script._pending_input_files[field.path] = field.payload
            # The provenance a user's run folder receives is the field's own:
            # what was read, how it was converted and the two digests. No
            # authoring metadata of this repository belongs in a generated
            # input (GOAL-034 Q0-src-cases-1).
            script._pending_input_files[field.path + ".provenance.json"] = (
                json.dumps(dict(field.provenance), indent=2) + "\n"
            )
        helpers.free_stream(script, "CUSTOM", filetype=custom.form, profile=field.path)
        return
    turning = _turning_rate(case)
    if turning is None:
        helpers.free_stream(script)
        return
    key, axis_name, rate = turning
    reference = case.reference
    axes = {} if reference is None else dict(reference.body_axes)
    axis = axes.get(axis_name)
    if axis is None:
        declared = ", ".join(f"{name}: {value}" for name, value in sorted(axes.items()))
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {key}: {rate:g} deg/s, and the reference "
            f"artifact its REF names declares no {axis_name} axis "
            f"({'it declares ' + declared if axes else 'it declares no [body_axes] at all'}). "
            "A mesh is built in whatever orientation its author chose, so which axis the "
            "aircraft rolls, pitches and yaws about is the configuration's to state: write "
            "'[body_axes]' in the reference artifact, with roll, pitch and yaw against X, "
            "Y or Z."
        )
    frame = frames.get("MRP")
    if not isinstance(frame, int):
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {key}: {rate:g} deg/s, and the free stream turns "
            "about the MOMENT REFERENCE POINT, which this run has no frame for: the "
            "reference artifact states no moment_point, so there is nothing to turn about. "
            "Add 'moment_point' to the reference artifact this row's REF names."
        )
    helpers.free_stream(
        script,
        "ROTATION",
        frame=frame,
        axis=axis,
        rpm=FREESTREAM_ROTATION_SIGN[axis_name] * rate * _DEG_PER_S_TO_RPM,
    )


def _fluid(case: SimCase, script: Script) -> None:
    """Emit the resolved air state, where the row resolved one.

    PFS-2025.02.05 and PFS-2027.05. A case whose row stated a flight
    condition arrives here carrying the state that condition resolved
    to, and it is emitted as the FIVE EXPLICIT FLUID PROPERTIES rather
    than as an altitude. That choice is forced rather than preferred:
    ``AIR_ALTITUDE`` has no argument for an ISA deviation, so a
    condition carrying ``dISA`` could not be expressed by it at all, and
    a density solved to meet a Reynolds number is not an atmosphere
    point in the first place. Emitting the state we computed says
    exactly what will be solved.

    A case carrying no resolved state emits NOTHING here, which is what
    keeps every case written before 0.9.0, and every hand-written
    campaign that sets no fluid, rendering exactly what it rendered
    before.
    """
    fluid = case.fluid
    if fluid is None:
        return
    # WHICH FIFTH PROPERTY depends on the build, and the emitter refuses
    # the one its build does not take. Asking rather than guessing is
    # what lets one case render on either side of the 26.100 boundary.
    fifth = helpers.fluid_fifth_property(script)
    helpers.atmosphere(
        script,
        density=fluid.density_kg_m3,
        pressure=fluid.pressure_pa,
        temperature=fluid.temperature_k,
        viscosity=fluid.viscosity_pa_s,
        specific_heat_ratio=(fluid.heat_capacity_ratio if fifth == "specific_heat_ratio" else None),
        sonic_velocity=(fluid.sonic_velocity_m_per_s if fifth == "sonic_velocity" else None),
    )


def _wake_termination(case: SimCase, stepping: TimeStepping) -> int | None:
    """Convert the preset's wake termination from revolutions to time steps.

    A rotor preset states it in revolutions, because that is the unit a
    rotor wake is thought about in, and negative counts backwards from
    the end of the run. The emitter takes STEPS. The conversion needs
    the steps per revolution, which is a property of this case's clock
    and its rotor speed and of nothing else, which is why it happens
    here rather than in the artifact model.

    Returns None where the preset states none, so a case that asks for
    nothing emits nothing.
    """
    revolutions = case.solver.wake_termination_revolutions
    steps = case.solver.wake_termination_steps
    if revolutions is not None and steps is not None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} inherits a wake termination in revolutions "
            f"({revolutions}) and in time steps ({steps}) from its solver preset, and "
            "the two can only disagree. State one."
        )
    if revolutions is None:
        return steps
    per_revolution = stepping.steps_per_revolution
    if per_revolution is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} inherits a wake termination of {revolutions} "
            "revolutions from its solver preset and states no rotor speed, so a "
            "revolution has no length in time steps here. State the rotor speed with "
            f"{ADVANCE_RATIO_VARIABLE} or {RPM_VARIABLE}, or drop the preset key."
        )
    return int(round(revolutions * per_revolution))


def _refuse_wake_termination_without_a_clock(case: SimCase) -> None:
    """Refuse a wake termination on a run type that has no clock to convert it.

    THE STEADY BUILDER USED TO DROP THIS SILENTLY. A preset stating
    ``unsteady_N_revolutions_wake`` resolved onto a steady case,
    validated, reached no emitted line, and said nothing, which is
    exactly the defect this release closes one layer up for a preset key
    that maps to no field at all. A key that maps to a field and still
    reaches no script is the same wrong answer with a longer path to it.

    Revolutions cannot be converted here rather than merely being
    unused: a steady run has no time step and no rotor speed, so there
    is no number of steps a revolution could be.
    """
    revolutions = case.solver.wake_termination_revolutions
    if revolutions is None:
        return
    raise CampaignConfigError(
        f"case {case.sim_id!r} inherits a wake termination of {revolutions} revolutions "
        "from its solver preset and is a STEADY run, which has no time loop, so there "
        "are no time steps for a revolution to become and the setting would reach no "
        "line. Drop the key from the preset this row names, or give the row a preset "
        "of its own; a steady row and a rotor row cannot share a wake termination "
        "stated in revolutions."
    )


#: A signed decimal, which is what "meant as a number" has to mean here.
_DECIMAL = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)$")


def _log_position_shape(text: str) -> str:
    """Classify a LOG_OUTPUT cell that is not a whole number.

    THE FIRST VERSION ASKED `float(text)`, which is wider than the
    message it selected: `nan`, `inf` and `1e3` all parse, so their
    users were told the value "takes no decimal point" about
    characters containing no decimal point. A refusal whose whole job is
    to point at the cell someone typed cannot be wrong about what they
    typed.
    """
    if _DECIMAL.match(text):
        return "decimal"
    if any(character in text for character in r"/\.") or text.endswith("}"):
        return "name"
    return "neither"


def _a_frame_may_move(script: Script) -> bool:
    """Say whether the motion ledger records a motion, or cannot say there is none.

    A frame an all-frame or ambiguous attachment moves carries no motion index
    and a trajectory of kind ``unknown`` (Q0 CX-5); that is not a fixed frame.
    """
    for value in script.frame_motions.values():
        trajectory = value.get("trajectory")
        kind = trajectory.get("kind") if isinstance(trajectory, Mapping) else None
        if value.get("motion_index") is not None or kind != "fixed":
            return True
    return False


def _finish_custom_field_coverage(case: SimCase, script: Script) -> None:
    """Check the final emitted placement, conservatively including full rotor sweeps."""
    grid = script.custom_field_extent_m
    if grid is None:
        return
    moved = _how_the_row_moves_the_body(case)
    if not moved and not script.surface_operations and not _a_frame_may_move(script):
        return
    from ..field_coverage import spatial_envelope

    try:
        if script.raw_flag:
            raise ValueError("raw commands can change geometry or its frames")
        vertices = _body_vertices_m(case)
        if vertices is None:
            raise ValueError("mesh coordinates or their physical units are unavailable")
        bounds, notes = spatial_envelope(
            vertices, script.surface_operations, list(script.frame_motions.values())
        )
        if moved and not script.surface_operations and not _a_frame_may_move(script):
            raise ValueError("the requested geometry change has no emitted placement record")
    except (ValueError, TypeError, KeyError) as error:
        script.custom_field_coverage = {"state": "unknown", "reason": str(error)}
        warn(
            f"case {case.sim_id!r}: custom-field coverage is not checked: {error}.",
            PyflightstreamWarning,
            stacklevel=2,
        )
        return
    covered = (
        bounds[0] >= grid[0]
        and bounds[1] <= grid[1]
        and bounds[2] >= grid[2]
        and bounds[3] <= grid[3]
    )
    script.custom_field_coverage = {
        "state": "within-grid-bounds" if covered else "envelope-exceeds-grid",
        "grid_yz_m": list(grid),
        "body_envelope_yz_m": list(bounds),
        "method": "conservative emitted-transform and full-rotary-sweep envelope",
        "limitations": notes
        + ["Grid bounds do not certify interior interpolation support or field coverage."],
    }
    if not covered:
        warn(
            f"case {case.sim_id!r}: custom field grid {grid} m does not cover the "
            f"conservative transformed-body and swept-rotor envelope {bounds} m. "
            "This may overestimate the occupied region; enlarge the grid or inspect "
            "the resolved geometry before interpreting any outside region as loaded by the field.",
            PyflightstreamWarning,
            stacklevel=2,
        )
