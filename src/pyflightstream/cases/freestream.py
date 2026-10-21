"""Prepare explicitly declared custom fields for the solver's measured file units."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path

from pyflightstream._lengths import scale
from pyflightstream.cases import CampaignConfigError

__all__ = [
    "MEASURED_FIELD_UNITS",
    "PreparedField",
    "field_rows_in_metres",
    "prepare_field",
    "prepare_rotating_field",
    "read_field_rows",
    "require_measured_unit",
]


@dataclass(frozen=True)
class PreparedField:
    """Effective solver input and the separate source/effective byte identities."""

    path: str
    payload: bytes | None
    provenance: dict[str, object]


#: The simulation length units a custom field file is measured in.
MEASURED_FIELD_UNITS = ("METER", "MILLIMETER")


def require_measured_unit(native_unit: str | None) -> str:
    """Return the simulation's unit when a custom field is measured in it, else refuse.

    The one home of the whitelist (PFS-2119.002): :func:`prepare_field`,
    :func:`field_rows_in_metres` and :func:`prepare_rotating_field` all write or
    read a field in the simulation's unit, and the solver's reading of a custom
    file is measured for the metre and the millimetre only.

    Parameters
    ----------
    native_unit : str or None
        The simulation's length unit, or None where the caller states none.

    Returns
    -------
    str
        The unit, ``METER`` or ``MILLIMETER``.

    Raises
    ------
    CampaignConfigError
        If the unit is neither ``METER`` nor ``MILLIMETER``, citing RPT-083.

    Examples
    --------
    >>> require_measured_unit("MILLIMETER")
    'MILLIMETER'
    """
    if native_unit not in MEASURED_FIELD_UNITS:
        raise CampaignConfigError(
            "A custom field is converted and written only in a unit its reading is measured "
            "in: it requires measured METER or "
            f"MILLIMETER simulation units; got {native_unit!r} "
            "(RPT-083: the solver's reading of a custom file is measured on 26.124 build "
            "8172026 for METER and MILLIMETER only)."
        )
    return native_unit


def prepare_field(
    path: Path,
    *,
    form: str,
    source_units: str | None,
    native_unit: str | None,
) -> PreparedField:
    """Convert an explicit SI declaration only; undeclared inputs retain their bytes.

    The six file columns carry global XYZ and velocity components. In the
    measured METER/MILLIMETER custom-file boundary, all six use native length
    units (seconds are unchanged). Multiplication changes representation only.
    It never rotates vectors or coordinates, and never writes the source.

    Parameters
    ----------
    path : Path
        The custom field file.
    form : str
        The field's form, ``STRUCTURED`` (a header line, then the rows) or ``UNSTRUCTURED``.
    source_units : str or None
        The row's ``FREESTREAM_UNITS``: ``SI``, ``NATIVE``, or None where the row does not declare
        it.
    native_unit : str or None
        The simulation's measured length unit, ``METER`` or ``MILLIMETER``.

    Returns
    -------
    PreparedField
        The file the solver reads (the source itself where nothing is converted, otherwise a
        converted copy and its bytes) and the provenance of both.

    Raises
    ------
    CampaignConfigError
        If ``source_units`` is not SI, NATIVE or omitted, or an SI field cannot be converted: the
        simulation unit is not measured, or the file has no header, a bad row count or grid count,
        a non-numeric value or a row of other than six finite columns.

    Examples
    --------
    >>> import tempfile
    >>> from pathlib import Path
    >>> path = Path(tempfile.mkdtemp()) / "field.dat"
    >>> with path.open("w", encoding="utf-8") as stream:
    ...     print("0 0 0 10 0 0", file=stream)
    ...     print("1 0 0 10 0 0", file=stream)
    >>> kept = prepare_field(path, form="UNSTRUCTURED", source_units=None,
    ...                      native_unit="MILLIMETER")
    >>> kept.path == str(path), kept.payload
    (True, None)
    >>> converted = prepare_field(path, form="UNSTRUCTURED", source_units="SI",
    ...                           native_unit="MILLIMETER")
    >>> converted.payload.decode().splitlines()
    ['0 0 0 10000 0 0', '1000 0 0 10000 0 0']
    """
    if source_units not in {None, "SI", "NATIVE"}:
        raise CampaignConfigError("FREESTREAM_UNITS must be SI or NATIVE, or omitted.")
    original = path.read_bytes()
    source_hash = hashlib.sha256(original).hexdigest()
    provenance: dict[str, object] = {
        "schema_version": "1.0.0",
        "source_path": str(path),
        "source_sha256": source_hash,
        "source_units": source_units or "undeclared",
        "native_length_unit": native_unit,
        "rotation_applied": False,
        "effective_sha256": source_hash,
        "effective_path": str(path),
        "hash_domain": "exact-file-bytes",
    }
    if source_units != "SI":
        return PreparedField(str(path), None, provenance)
    native_unit = require_measured_unit(native_unit)
    factor = scale("METER", native_unit)
    assert factor is not None  # The measured-unit whitelist above guarantees this.
    lines = [line.strip() for line in original.decode("utf-8").splitlines() if line.strip()]
    out = []
    expected = None
    if form == "STRUCTURED":
        if not lines:
            raise CampaignConfigError(f"Custom field {path} has no header.")
        header = lines.pop(0).split()
        expected = _grid_count(path, header)
        out.append(" ".join(header))
    elif form != "UNSTRUCTURED":
        raise CampaignConfigError(f"Unknown custom-field form {form!r}.")
    if not lines or (expected is not None and len(lines) != expected):
        raise CampaignConfigError(f"Custom field {path} has an invalid row count.")
    for line in lines:
        try:
            values = [float(value) * factor for value in line.split()]
        except ValueError as error:
            raise CampaignConfigError(f"Custom field {path} contains nonnumeric values.") from error
        if len(values) != 6 or not all(math.isfinite(value) for value in values):
            raise CampaignConfigError(f"Custom field {path} requires six finite columns.")
        out.append(" ".join(format(value, ".17g") for value in values))
    payload = ("\n".join(out) + "\n").encode("utf-8")
    effective_hash = hashlib.sha256(payload).hexdigest()
    name = f"pfs-field-{effective_hash[:24]}{path.suffix.lower()}"
    provenance.update(
        effective_sha256=effective_hash,
        effective_path=name,
        scale_from_source=factor,
        source_coordinate_units="m",
        source_velocity_units="m/s",
        evidence="RPT-083: exact 26.124 build 8172026 METER/MILLIMETER custom-file controls",
    )
    return PreparedField(name, payload, provenance)


def _grid_count(path: Path, header: list[str]) -> int:
    """Return the point count a STRUCTURED header declares (two positive integers)."""
    if len(header) != 2 or any(not v.isdigit() or int(v) <= 0 for v in header):
        raise CampaignConfigError(f"Custom field {path} requires two positive grid counts.")
    return int(header[0]) * int(header[1])


def read_field_rows(path: Path, *, form: str) -> tuple[str | None, list[list[float]]]:
    """Return a custom field's header line (STRUCTURED) and its rows of six numbers.

    The form was checked by the builder's reader before this is asked; this
    reads the numbers and refuses only what would make them unusable.

    Parameters
    ----------
    path : Path
        The custom field file.
    form : str
        The field's form, ``STRUCTURED`` (a header line, then the rows) or ``UNSTRUCTURED``.

    Returns
    -------
    tuple of (str or None, list of list of float)
        The header line (None for an unstructured field) and the rows, six numbers each, as
        written.

    Raises
    ------
    CampaignConfigError
        If the form is unknown, a structured field has no header, the file holds no row, a value is
        not numeric, or a row is not six finite columns.
    """
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    header = None
    if form == "STRUCTURED":
        if not lines:
            raise CampaignConfigError(f"Custom field {path} has no header.")
        header_parts = lines.pop(0).split()
        expected = _grid_count(path, header_parts)
        header = " ".join(header_parts)
        if not lines or len(lines) != expected:
            raise CampaignConfigError(f"Custom field {path} has an invalid row count.")
    elif form != "UNSTRUCTURED":
        raise CampaignConfigError(f"Unknown custom-field form {form!r}.")
    rows = []
    for line in lines:
        try:
            values = [float(value) for value in line.split()]
        except ValueError as error:
            raise CampaignConfigError(f"Custom field {path} contains nonnumeric values.") from error
        if len(values) != 6 or not all(math.isfinite(value) for value in values):
            raise CampaignConfigError(f"Custom field {path} requires six finite columns.")
        rows.append(values)
    if not rows:
        raise CampaignConfigError(f"Custom field {path} holds no row.")
    return header, rows


def field_rows_in_metres(
    path: Path, *, form: str, source_units: str | None, native_unit: str | None
) -> tuple[str | None, list[list[float]]]:
    """Return a custom field's rows in metres and metres per second (qsteady_rotor).

    ``SI`` and an undeclared file are read as the manual states the form, in
    metres and metres per second; ``NATIVE`` is converted from the simulation's
    measured unit. An undeclared file on a simulation whose unit is not the
    metre is refused, because nothing then says which of the two it is written
    in, and the rotational velocity the quasi-steady rotor removes from it,
    composing the relative free stream the fixed blades see, is in metres per
    second.

    Parameters
    ----------
    path : Path
        The custom field file.
    form : str
        The field's form, ``STRUCTURED`` (a header line, then the rows) or ``UNSTRUCTURED``.
    source_units : str or None
        The row's ``FREESTREAM_UNITS``: ``SI``, ``NATIVE``, or None where the row does not declare
        it.
    native_unit : str or None
        The simulation's measured length unit, ``METER`` or ``MILLIMETER``.

    Returns
    -------
    tuple of (str or None, list of list of float)
        The header line (None for an unstructured field) and the rows, positions in metres and
        velocities in metres per second.

    Raises
    ------
    CampaignConfigError
        If a NATIVE field's simulation unit is neither the metre nor the millimetre, an undeclared
        field sits on a simulation not in metres, or :func:`read_field_rows` refuses the file.
    """
    if source_units not in {None, "SI", "NATIVE"}:
        raise CampaignConfigError("FREESTREAM_UNITS must be SI or NATIVE, or omitted.")
    header, rows = read_field_rows(path, form=form)
    if source_units == "SI" and native_unit is not None:
        require_measured_unit(native_unit)
    if source_units == "NATIVE":
        native_unit = require_measured_unit(native_unit)
        factor = scale(native_unit, "METER")
        assert factor is not None  # The measured-unit whitelist above guarantees this.
        rows = [[value * factor for value in row] for row in rows]
    elif source_units is None and native_unit not in {None, "METER"}:
        raise CampaignConfigError(
            f"The custom field {path} declares no FREESTREAM_UNITS on a simulation in "
            f"{native_unit}; declare SI or NATIVE, since the rotational velocity the "
            "quasi-steady rotor removes from it (the relative free stream the fixed blades "
            "see) is in metres per second."
        )
    return header, rows


def prepare_rotating_field(
    path: Path,
    *,
    form: str,
    source_units: str | None,
    native_unit: str | None,
    hub_m: tuple[float, float, float],
    axis: tuple[float, float, float],
    omega_rad_s: float,
) -> PreparedField:
    """Write the field a blade held still meets: the user's inflow less the rotational velocity.

    The user's file is the TOTAL velocity of the air at the disc, in the global
    frame, and this composes the RELATIVE free stream the fixed blades see: the
    rotational velocity of each point is removed, never added. A blade turning
    at ``omega`` (right-hand about the unit ``axis``, signed by the rotor's
    hand) moves at ``omega axis x (p - hub)``, so the air relative to it, which
    is what a blade held still must meet, is::

        v_rel(p) = v(p) - omega axis x (p - hub)

    Computed in metres and metres per second and written in the simulation's
    unit, as :func:`prepare_field` writes an SI field. The source is never
    written; the effective file is a new one named by its own digest, and its
    provenance says what was added. The rotation is the free stream's meaning
    applied to the file (the air seen from the turning blade); no licensed run
    has compared this field with ``SET_FREESTREAM ROTATION`` yet.

    Parameters
    ----------
    path : Path
        The custom field file.
    form : str
        The field's form, ``STRUCTURED`` (a header line, then the rows) or ``UNSTRUCTURED``.
    source_units : str or None
        The row's ``FREESTREAM_UNITS``: ``SI``, ``NATIVE``, or None where the row does not declare
        it.
    native_unit : str or None
        The simulation's measured length unit, ``METER`` or ``MILLIMETER``.
    hub_m : tuple of float
        A point of the shaft, (x, y, z) in metres, in the field's frame.
    axis : tuple of float
        The shaft's direction, a unit vector in the field's frame.
    omega_rad_s : float
        The rotor's angular speed in radians per second, right-hand about ``axis`` and signed by
        the rotor's hand.

    Returns
    -------
    PreparedField
        The new field file named by its own digest, its bytes in the simulation's unit, and its
        provenance.

    Raises
    ------
    CampaignConfigError
        If the simulation's unit names no scale, or the file is refused as
        :func:`field_rows_in_metres` refuses it.
    """
    if not all(math.isfinite(v) for v in (omega_rad_s, *hub_m, *axis)):
        raise CampaignConfigError(
            "The rotating field needs a finite angular speed, hub point and axis; "
            f"got omega {omega_rad_s!r}, hub {hub_m!r}, axis {axis!r}."
        )
    header, rows = field_rows_in_metres(
        path, form=form, source_units=source_units, native_unit=native_unit
    )
    factor = 1.0 if native_unit is None else scale("METER", require_measured_unit(native_unit))
    assert factor is not None  # The measured-unit whitelist above guarantees this.
    n = axis
    out = [] if header is None else [header]
    for x, y, z, vx, vy, vz in rows:
        p = (x - hub_m[0], y - hub_m[1], z - hub_m[2])
        swept = (
            omega_rad_s * (n[1] * p[2] - n[2] * p[1]),
            omega_rad_s * (n[2] * p[0] - n[0] * p[2]),
            omega_rad_s * (n[0] * p[1] - n[1] * p[0]),
        )
        values = (x, y, z, vx - swept[0], vy - swept[1], vz - swept[2])
        out.append(" ".join(format(value * factor, ".17g") for value in values))
    original = path.read_bytes()
    payload = ("\n".join(out) + "\n").encode("utf-8")
    effective_hash = hashlib.sha256(payload).hexdigest()
    name = f"pfs-field-{effective_hash[:24]}{path.suffix.lower()}"
    provenance: dict[str, object] = {
        "schema_version": "1.0.0",
        "source_path": str(path),
        "source_sha256": hashlib.sha256(original).hexdigest(),
        "source_units": source_units or "undeclared",
        "native_length_unit": native_unit,
        "rotation_applied": True,
        "rotation": {
            "omega_rad_s": omega_rad_s,
            "hub_m": list(hub_m),
            "axis": list(axis),
            "rule": "v_rel = v - omega axis x (p - hub)",
        },
        "effective_sha256": effective_hash,
        "effective_path": name,
        "scale_from_metres": factor,
        "hash_domain": "exact-file-bytes",
    }
    return PreparedField(name, payload, provenance)
