"""The free stream: uniform, rotating or a custom field, and the fluid.

:func:`_free_stream` emits the uniform free stream of a row,
:func:`_the_custom_freestream` a custom field read from the workspace's
``freestream/`` files, and :func:`_fluid` the fluid properties; the body
extent the custom field must cover is measured here, and so is the
coverage check a run finishes with.

THE WAKE A ROTOR ROW KEEPS (FR-321 to FR-325) is converted here too, beside
:func:`_wake_termination`: the rotor builders emit it through
:func:`settings_with_the_wake`, and the plan reads the same conversion
(:func:`planned_wake`, :func:`wake_warnings`), so the script and the plan
cannot disagree.

THE LENGTH IS WHAT MATTERS, not the count. A termination stated in steps or
revolutions keeps a different length of wake behind the rotor whenever the
rotor speed, the free-stream speed or the step angle changes, so a setup may
state ``wake_termination_length`` in rotor radii instead, and a rotor row that
states no termination at all keeps 4 radii (the default of FR-321 R4, a
recommendation the user may change). The conversion is
``n = ceil(L R Omega / (V_ax dtheta))``: R the tip radius in metres, Omega the
rotor speed in rad/s, dtheta the step angle in rad and V_ax the axial
convection speed of the wake in m/s, rounded upward so the wake kept at V_ax
is never shorter than L.

V_AX IS THE FREE-STREAM SPEED (FR-321 R3), a lower bound in forward flight,
where axial induction speeds the wake up. Near hover the free-stream speed
goes to zero and the conversion would divide by it, so a row may state a
thrust (``wake_termination_thrust_n``), whose momentum-theory induced velocity
at the disc, ``v_i = sqrt(T / (2 rho A))``, is used where it exceeds the
free-stream speed, or a revolution cap (``wake_termination_revolutions_cap``)
that bounds the converted steps (FR-323). The record names the rule used.

WHAT THIS MODULE DOES NOT DO: place the wake end plane. That is the
``wake_termination_x`` argument of ``INITIALIZE_SOLVER`` (FR-324), stated by the
setup key ``wake_termination_x_m`` and emitted by
the skeleton; this module only reads it to warn when the plane sits before the
length (FR-325 R3, R4).
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import (
    Mapping,
)
from dataclasses import (
    asdict,
    dataclass,
    replace,
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

from ._motion import (
    _clock_speed,
    _motion_view,
)
from ._rows import (
    _angle,
    _from_metres,
    _rotor_of,
    _the_rotor_a_flat_row_turns,
    _turning_rate,
    _variable,
    _velocity,
    parse_restart,
    rotor_speed,
)
from ._solver_settings import (
    _settings,
)
from ._timing import (
    TimeStepping,
    rotor_time_stepping,
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
    """Return the time steps of a rotor row's wake termination (FR-321 to FR-323).

    A rotor preset may state the termination in revolutions, in steps or as a
    length of wake in rotor radii, and the emitter takes STEPS; a row stating
    none keeps 4 radii. The conversion needs the case's clock and its rotor,
    which is why it happens at build time, in
    :func:`pyflightstream.cases.workflows._freestream.wake_termination_of`. Two of
    the three keys can only disagree, and are refused (FR-322, which the
    refusal of 0.33.0 for revolutions beside steps joins). Returns None where
    a default cannot be converted, so such a case emits nothing.
    """
    return wake_termination_of(case, stepping).steps


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
    refuse_a_wake_length(case, "is a STEADY run, which has no time loop")
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


#: The wake length a rotor row keeps when nothing states its termination, in
#: rotor radii (FR-321 R4): the recommendation of 2026-10-01, kept for
#: its computational cost; any length may be stated instead.
DEFAULT_WAKE_LENGTH_R = 4.0

#: The three keys that each state a row's whole wake termination; at most one
#: reaches a row (FR-322).
WAKE_TERMINATION_KEYS = (
    "wake_termination_length",
    "wake_termination_steps",
    "wake_termination_revolutions",
)

#: The two keys that bound a converted length near hover (FR-323); they are
#: not termination keys and are refused beside a step or revolution count.
WAKE_BOUND_KEYS = ("wake_termination_thrust_n", "wake_termination_revolutions_cap")

#: The solver's default wake end plane as measured on 26.124, downstream of the
#: rotor in rotor radii, with the case and the report that state it (FR-325 R4):
#: RPT-137 section 7 reads x/R 5.52 with the body behind the rotor and 2.08 on a
#: wheel of blades alone.
MEASURED_DEFAULT_PLANES = (
    ("a rotor with the body behind it", 5.5, "RPT-137 section 7"),
    ("a blades-only wheel", 2.1, "RPT-137 section 7"),
)

#: The rule that gave V_ax, as the record and the plan name it (FR-323 R6).
FREE_STREAM, INDUCED_VELOCITY, REVOLUTION_CAP = "free_stream", "induced_velocity", "revolution_cap"


@dataclass(frozen=True)
class WakeTermination:
    """The wake termination of one rotor point: what was stated and what the script emits.

    Attributes
    ----------
    stated_as : str
        The key that stated it, or ``default`` for the 4R default (FR-321 R4).
    length_r : float or None
        The length asked in rotor radii; None for a step or revolution count.
    steps : int or None
        The steps emitted; None where a default could not be converted (no
        rotor radius is known), which emits nothing.
    rule : str or None
        ``free_stream``, ``induced_velocity`` or ``revolution_cap`` for a length;
        None for a count.
    v_ax_m_s : float or None
        The axial convection speed used, in m/s; None where the revolution cap
        set the steps at zero free-stream speed.
    v_inf_m_s : float
        The free-stream speed of the point, in m/s.
    radius_m : float or None
        The tip radius R in metres: half the largest rotor diameter the row
        turns (its rotor block's ``diameter_m``, else the reference's
        ``rotor_diameter_m``).
    hub_x_m : float or None
        The X of that rotor's hub in metres, where its block states one.
    omega_rad_s : float
        The rotor speed of the run's clock in rad/s.
    dtheta_rad : float
        The step angle of the run's clock in rad.
    run_steps : int
        The time steps of the whole run.
    plane : float or str
        The wake end plane, ``DEFAULT`` or an X in metres (FR-324).
    downstream : int
        +1 or -1, the sense of the free stream's X component; 0 at zero speed.
    """

    stated_as: str
    length_r: float | None
    steps: int | None
    rule: str | None
    v_ax_m_s: float | None
    v_inf_m_s: float
    radius_m: float | None
    hub_x_m: float | None
    omega_rad_s: float
    dtheta_rad: float
    run_steps: int
    plane: float | str
    downstream: int

    def record(self) -> dict[str, object]:
        """Return the fields as the plan writes them (``PointPlan.wake_termination``)."""
        return asdict(self)

    def derived(self) -> dict[str, str]:
        """Return the three recorded values of a converted length (FR-321 R5), else nothing.

        They join the solver-flag snapshot's ``derived`` entries the run record
        carries, so a record says the L asked, the V_ax used with its rule, and
        the steps emitted.
        """
        if self.length_r is None or self.steps is None:
            return {}
        asked = "the default of FR-321" if self.stated_as == "default" else "stated"
        speed = "none" if self.v_ax_m_s is None else f"{self.v_ax_m_s:.6g}"
        return {
            "wake_termination_length": f"{self.length_r:g} R ({asked})",
            "wake_termination_v_ax_m_s": speed,
            "wake_termination_rule": str(self.rule),
            "wake_termination_steps": str(self.steps),
        }

    def kept_r(self, steps: float) -> float | None:
        """Return the wake length ``steps`` keep at V_ax, in radii; None where unknown."""
        if not self.radius_m or not self.v_ax_m_s or not self.omega_rad_s:
            return None
        return steps * self.v_ax_m_s * self.dtheta_rad / (self.omega_rad_s * self.radius_m)

    def count_kept_r(self) -> float | None:
        """Return the length a step or revolution count keeps over the run, in radii.

        FR-325 R2: L_kept = n V_ax dtheta / (Omega R), with n the count the run
        reaches (a negative count is the run's steps less it). None for a
        converted length, and where the length is unknown (zero free-stream
        speed, or no rotor radius known).
        """
        if self.length_r is not None or self.steps is None:
            return None
        count = self.steps if self.steps > 0 else self.run_steps + self.steps
        return self.kept_r(min(count, self.run_steps))


def _stated(case: SimCase, keys: tuple[str, ...]) -> list[tuple[str, object]]:
    return [
        (key, getattr(case.solver, key)) for key in keys if getattr(case.solver, key) is not None
    ]


def _source(case: SimCase, key: str) -> str:
    if key in case.setup_from_row:
        return "the row's VAR_NAMES_VALUES cell"
    return "the setup preset the row names"


def _refuse_two_keys(case: SimCase) -> list[tuple[str, object]]:
    """Return the termination key the row states, refusing two (FR-322) and misplaced bounds."""
    stated = _stated(case, WAKE_TERMINATION_KEYS)
    if len(stated) > 1:
        named = " and ".join(f"{key} = {value} ({_source(case, key)})" for key, value in stated)
        raise CampaignConfigError(
            f"case {case.sim_id!r} states its wake termination with {named}, and the "
            "keys can only disagree: each states the whole termination (FR-322). State one."
        )
    bounds = _stated(case, WAKE_BOUND_KEYS)
    if bounds and stated and stated[0][0] != "wake_termination_length":
        key, value = stated[0]
        raise CampaignConfigError(
            f"case {case.sim_id!r} states {bounds[0][0]} = {bounds[0][1]} beside "
            f"{key} = {value}: {' and '.join(WAKE_BOUND_KEYS)} bound a wake LENGTH "
            "converted into steps, and a count is emitted as stated (FR-323 R6). Drop "
            f"{bounds[0][0]}, or state the termination as wake_termination_length."
        )
    return stated


def refuse_a_wake_length(case: SimCase, run: str) -> None:
    """Refuse a wake length, a thrust or a cap on a run that turns no rotor in time.

    ``run`` says what the run is, in the words of the caller's refusal. A
    length is converted against a rotor's radius, speed and step angle, so a
    steady run (no time step) and a run that turns nothing (no rotor) cannot
    convert one, and a key that reaches no line is refused rather than
    dropped (FR-321 R4, FR-323).
    """
    stated = _stated(case, ("wake_termination_length", *WAKE_BOUND_KEYS))
    if not stated:
        return
    key, value = stated[0]
    raise CampaignConfigError(
        f"case {case.sim_id!r} states {key} = {value} and {run}, so there is no rotor "
        "turning in time for a wake length to be converted against: a length becomes "
        "steps from a rotor radius, a rotor speed and a step angle (FR-321). Drop the "
        "key from the preset or the row, or state wake_termination_steps where the run "
        "has a time loop."
    )


def _radius_and_hub(case: SimCase) -> tuple[float | None, float | None]:
    """Return the largest tip radius the row turns, in metres, and that rotor's hub X."""
    blocks = (
        [_rotor_of(case, record) for record in case.motions]
        if case.motions
        else [_the_rotor_a_flat_row_turns(case)]
    )
    fallback = None if case.reference is None else case.reference.rotor_diameter
    sized = [
        (block.diameter_m if block is not None else fallback, block)
        for block in blocks
        if block is not None or fallback is not None
    ]
    if not sized:
        return None, None
    diameter, block = max(sized, key=lambda pair: float(pair[0] or 0.0))
    return float(diameter or 0.0) / 2.0, None if block is None else block.x_m


def rotor_row_stepping(case: SimCase) -> TimeStepping:
    """Return the clock a rotor row's builder runs, from the motion that owns it (FR-64).

    The builder's own resolution, for a caller that has the case and not the
    script: the plan. A row stating ``MOTIONS`` takes the clock of
    ``CLOCK_MOTION``; a flat row its one rotor's.

    Raises
    ------
    CampaignConfigError
        Where the builder would refuse the row's speed or clock.
    """
    if case.motions:
        views = [_motion_view(case, record) for record in case.motions]
        speeds = [rotor_speed(view) for view in views]
        return rotor_time_stepping(case, speed=_clock_speed(case, views, speeds))
    return rotor_time_stepping(case, speed=rotor_speed(case))


def _induced(case: SimCase, radius: float, v_inf: float) -> tuple[float, str]:
    """Return V_ax and its rule for a length: v_i where a thrust is stated and exceeds V_inf."""
    thrust = case.solver.wake_termination_thrust_n
    if thrust is None:
        return v_inf, FREE_STREAM
    if case.fluid is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} states wake_termination_thrust_n = {thrust} and resolves "
            "no fluid density, so the induced velocity sqrt(T / (2 rho A)) cannot be "
            "evaluated (FR-323 R1). State the row's flight condition, or use "
            "wake_termination_revolutions_cap."
        )
    induced = math.sqrt(thrust / (2.0 * case.fluid.density_kg_m3 * math.pi * radius**2))
    return (induced, INDUCED_VELOCITY) if induced > v_inf else (v_inf, FREE_STREAM)


def _length_steps(
    case: SimCase, length: float, radius: float, clock: tuple[float, float]
) -> tuple[int, float | None, str]:
    """Convert a length into steps, with V_ax and its rule (FR-321 R2, FR-323)."""
    omega, dtheta = clock
    v_ax, rule = _induced(case, radius, abs(_velocity(case)))
    cap = case.solver.wake_termination_revolutions_cap
    capped = None if cap is None else max(1, math.floor(cap * 2.0 * math.pi / dtheta + 1e-9))
    if v_ax <= 0.0:
        if capped is None:
            raise CampaignConfigError(
                f"case {case.sim_id!r} turns a rotor at zero free-stream speed with a wake "
                f"termination of {length:g} rotor radii, and a length divided by a zero "
                "convection speed is no number of steps (FR-323 R4). State "
                "wake_termination_thrust_n (the rotor's thrust in newtons, whose induced "
                "velocity convects the wake) or wake_termination_revolutions_cap (a "
                "revolution count that bounds it)."
            )
        return capped, None, REVOLUTION_CAP
    steps = math.ceil(round(length * radius * omega / (v_ax * dtheta), 9))
    if capped is not None and steps > capped:
        return capped, v_ax, REVOLUTION_CAP
    return steps, v_ax, rule


def _count_steps(case: SimCase, key: str, value: float, stepping: TimeStepping) -> int:
    if key == "wake_termination_steps":
        return int(value)
    per_revolution = stepping.steps_per_revolution
    if per_revolution is None:
        raise CampaignConfigError(
            f"case {case.sim_id!r} inherits a wake termination of {value} "
            "revolutions from its solver preset and states no rotor speed, so a "
            "revolution has no length in time steps here. State the rotor speed with "
            f"{ADVANCE_RATIO_VARIABLE} or {RPM_VARIABLE}, or drop the preset key."
        )
    return int(round(value * per_revolution))


def _clock(stepping: TimeStepping) -> tuple[float, float]:
    """Return Omega in rad/s and dtheta in rad of the run's clock."""
    per_revolution = stepping.steps_per_revolution or 0.0
    omega = abs(stepping.rpm or 0.0) * 2.0 * math.pi / 60.0
    dtheta = 2.0 * math.pi / per_revolution if per_revolution else omega * stepping.delta_time_s
    return omega, dtheta


def _downstream(case: SimCase, v_inf: float) -> int:
    if v_inf == 0.0:
        return 0
    alpha, beta = math.radians(_angle(case, "alpha")), math.radians(_angle(case, "beta"))
    return 1 if math.cos(alpha) * math.cos(beta) >= 0.0 else -1


def wake_termination_of(case: SimCase, stepping: TimeStepping | None = None) -> WakeTermination:
    """Return the wake termination of a rotor point, converting a length into steps.

    Parameters
    ----------
    case : SimCase
        The point's case, of a run type that turns a rotor in time.
    stepping : TimeStepping, optional
        The run's clock, as the builder resolved it; resolved here when not
        given (:func:`rotor_row_stepping`).

    Returns
    -------
    WakeTermination
        The steps the script emits and what they came from. A row stating no
        termination gets the 4R default (FR-321 R4); a default with no rotor
        radius known converts nothing and emits nothing, as before 0.34.0.

    Raises
    ------
    CampaignConfigError
        Two termination keys (FR-322), a thrust or a cap beside a count
        (FR-323 R6), a length at zero free-stream speed with neither bound
        (FR-323 R4), a stated length with no rotor radius known, or
        revolutions with no rotor speed.
    """
    stated = _refuse_two_keys(case)
    stepping = stepping or rotor_row_stepping(case)
    omega, dtheta = _clock(stepping)
    v_inf = abs(_velocity(case))
    radius, hub = _radius_and_hub(case)
    key, value = stated[0] if stated else ("default", DEFAULT_WAKE_LENGTH_R)
    plane = case.solver.wake_termination_x_m
    base = WakeTermination(
        stated_as=key,
        length_r=None,
        steps=None,
        rule=None,
        v_ax_m_s=v_inf,
        v_inf_m_s=v_inf,
        radius_m=radius,
        hub_x_m=hub,
        omega_rad_s=omega,
        dtheta_rad=dtheta,
        run_steps=stepping.time_iterations,
        plane="DEFAULT" if plane is None else plane,
        downstream=_downstream(case, v_inf),
    )
    if key in ("wake_termination_steps", "wake_termination_revolutions"):
        return replace(base, steps=_count_steps(case, key, float(str(value)), stepping))
    length = float(str(value))
    if radius is None:
        if key != "default":
            raise CampaignConfigError(
                f"case {case.sim_id!r} states wake_termination_length = {length:g} and the "
                "rotor it turns has no known radius: its reference declares no rotor block "
                "with a diameter_m and states no rotor_diameter_m (FR-321 R1)."
            )
        return replace(base, length_r=length, v_ax_m_s=None)
    steps, v_ax, rule = _length_steps(case, length, radius, (omega, dtheta))
    return replace(base, length_r=length, steps=steps, rule=rule, v_ax_m_s=v_ax)


def settings_with_the_wake(case: SimCase, script: Script, stepping: TimeStepping) -> None:
    """Emit a rotor row's solver settings with its wake termination, and record the conversion.

    The rotor builders' one call: the steps of :func:`wake_termination_of`
    reach ``SET_WAKE_TERMINATION_TIME_STEPS`` through the settings emitter,
    and a converted length's three values join the solver-flag snapshot the
    run record carries (FR-321 R5).
    """
    termination = wake_termination_of(case, stepping)
    _settings(case, script, wake_termination_time_steps=termination.steps)
    extra = termination.derived()
    if extra and script.solver_setup is not None:
        derived = {**script.solver_setup.derived, **extra}
        script.solver_setup = script.solver_setup.model_copy(update={"derived": derived})


def wake_end_plane(case: SimCase, script: Script) -> str:
    """Return the ``wake_termination_x`` argument of ``INITIALIZE_SOLVER`` (FR-324).

    ``DEFAULT`` where the setup states no plane, so the script is the one
    0.33.0 wrote (R2); else the stated X in metres, written in the
    simulation's length unit as every length this package hands the solver.
    """
    plane = case.solver.wake_termination_x_m
    if plane is None or plane == "DEFAULT":
        return "DEFAULT"
    factor = _from_metres(case, script, "the wake end plane wake_termination_x_m")
    return f"{float(plane) * factor:.12g}"


def planned_wake(case: SimCase) -> WakeTermination | None:
    """Return the wake termination the builder will emit for one point, as the plan reads it.

    None for a row that turns no rotor in time, for a continuation (which
    reopens a saved state and emits no termination), and for a row the
    builder refuses: that point is BLOCKED with the builder's own reason, and
    the plan adds nothing about it. The same conversion as the builder's
    (:func:`wake_termination_of`), so the plan and the script agree.
    """
    if case.recipe != "unsteady_rotor":
        return None
    try:
        if parse_restart(case) is not None:
            return None
        return wake_termination_of(case)
    except CampaignConfigError:
        return None


def _length_warnings(row: str, wake: WakeTermination) -> list[str]:
    """FR-325 R1: a length the run's revolutions cannot reach, or a cap that cuts it."""
    if wake.length_r is None:
        return []
    if wake.steps is None:
        return [
            f"{row}: the {wake.length_r:g} R default wake termination is not converted: the "
            "rotor has no known radius (no rotor block with a diameter_m and no "
            "rotor_diameter_m on the reference), so the run keeps the solver's own "
            "termination and the plan cannot say what length it keeps (FR-325 R1)."
        ]
    per_revolution = 2.0 * math.pi / wake.dtheta_rad
    kept = wake.kept_r(min(wake.steps, wake.run_steps))
    one_revolution = wake.kept_r(per_revolution)
    if kept is None or not one_revolution:
        return [
            f"{row}: the wake termination asks L = {wake.length_r:g} R and its "
            f"{wake.steps} steps were set by the revolution cap at zero free-stream speed, "
            "so the plan cannot say what length they keep (FR-325 R1)."
        ]
    if kept >= wake.length_r * (1.0 - 1e-9):
        return []
    cause = (
        f"the revolution cap keeps {wake.steps} steps"
        if wake.rule == REVOLUTION_CAP and wake.steps < wake.run_steps
        else f"the run has {wake.run_steps / per_revolution:.3g} revolution(s)"
    )
    return [
        f"{row}: the wake termination asks L = {wake.length_r:g} R and needs "
        f"{wake.length_r / one_revolution:.3g} revolution(s) at V_ax = {wake.v_ax_m_s:.4g} m/s "
        f"({wake.rule}); {cause}, so the wake kept is about {kept:.3g} R (FR-325 R1)."
    ]


def _count_warnings(row: str, wake: WakeTermination) -> list[str]:
    """FR-325 R2: the length a count keeps, against the 4R recommendation."""
    if wake.length_r is not None or wake.steps is None:
        return []
    kept = wake.count_kept_r()
    if kept is None:
        return [
            f"{row}: the wake termination {wake.stated_as} keeps an unknown length at zero "
            "free-stream speed or with no rotor radius known; the plan cannot judge it "
            f"against the {DEFAULT_WAKE_LENGTH_R:g} R recommendation (FR-325 R2)."
        ]
    if kept >= DEFAULT_WAKE_LENGTH_R * (1.0 - 1e-9):
        return []
    return [
        f"{row}: the wake termination {wake.stated_as} ({wake.steps} steps) and the run's "
        f"{wake.run_steps} steps keep about {kept:.3g} R of wake at V_ax = "
        f"{wake.v_ax_m_s:.4g} m/s, below the {DEFAULT_WAKE_LENGTH_R:g} R recommendation "
        "(FR-325 R2). State wake_termination_length to keep a length."
    ]


def _plane_warnings(row: str, wake: WakeTermination) -> list[str]:
    """FR-325 R3 and R4: a stated plane before the length, or the solver's default plane."""
    length = DEFAULT_WAKE_LENGTH_R if wake.length_r is None else wake.length_r
    if wake.plane == "DEFAULT":
        placements = ", ".join(
            f"{ratio:g} R on {where} ({report})" for where, ratio, report in MEASURED_DEFAULT_PLANES
        )
        return [
            f"{row}: the wake end plane is the solver's DEFAULT, whose position the plan "
            f"cannot know, and it may cut the wake before L = {length:g} R: measured on "
            f"26.124 at {placements}. State wake_termination_x_m, an X in metres in the "
            "simulation's frame, to place it (FR-325 R4)."
        ]
    if wake.radius_m is None or wake.hub_x_m is None:
        unknown = "hub X" if wake.radius_m is not None else "radius"
        return [
            f"{row}: the wake end plane wake_termination_x_m = {float(wake.plane):g} m cannot be "
            f"placed against L = {length:g} R, because the rotor's {unknown} is unknown (no "
            "rotor block states it), so the plan cannot say whether the plane cuts the wake "
            "(FR-325 R3). Declare the rotor block on the reference to place it."
        ]
    offset = float(wake.plane) - wake.hub_x_m
    distance = abs(offset) if wake.downstream == 0 else offset * wake.downstream
    if distance >= length * wake.radius_m * (1.0 - 1e-9):
        return []
    return [
        f"{row}: the wake end plane wake_termination_x_m = {float(wake.plane):g} m lies "
        f"{distance / wake.radius_m:.3g} R downstream of the rotor hub, before the "
        f"L = {length:g} R the wake keeps, so the plane cuts it (FR-325 R3)."
    ]


def wake_warnings(row: str, wake: WakeTermination) -> list[str]:
    """Return the plan's warnings on one rotor point's wake (FR-325); empty where none is owed.

    ``row`` names the row and point in each message. The warnings are computed
    from the conversion alone: no solver call and no file read (R6).
    """
    return [
        *_length_warnings(row, wake),
        *_count_warnings(row, wake),
        *_plane_warnings(row, wake),
    ]
