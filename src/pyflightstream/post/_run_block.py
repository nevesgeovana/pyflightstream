"""The canonical run block: the columns every csv of the post opens with (PFS-2231).

Every csv the post writes opens with the same columns, in the same order, so
a reader holding one file can tell which run, point and condition each row is
of, and two files of one point join on their first columns. A column that does
not apply to a row is ``NA``, never absent, so the schema is the same for every
run type. The definition of record is ``docs/definitions/the-run-block.md``;
units and sources are stated in ``products.json`` from :data:`RUN_BLOCK_SPEC`,
not in the csv.

The block is composed of fixed columns, one column per ``IDENTIFIERS`` name of
the matrix row, and per-rotor columns named by the rotor's integer id with no
underscore (``RPM0``, ``D0``). :func:`run_block_columns` gives the header for a
given set of identifiers and rotors; :func:`run_block_row` builds one row's
values from what the post already holds for the point.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pyflightstream._errors import ProductError
from pyflightstream._tokens import NOT_APPLICABLE

__all__ = [
    "IDENTIFIER_PLACEHOLDER",
    "RUN_BLOCK_SPEC",
    "RUN_TYPES",
    "RotorRunValues",
    "RunColumn",
    "run_block_columns",
    "run_block_row",
]

#: The run types a row of the block names: the workflow selected for the row.
RUN_TYPES: tuple[str, ...] = ("steady", "unsteady", "unsteady_rotor", "qsteady_rotor")

#: How :data:`RUN_BLOCK_SPEC` writes the place of the ``IDENTIFIERS`` columns.
IDENTIFIER_PLACEHOLDER = "<IDENTIFIER>"

_ROTOR = "<id>"


@dataclass(frozen=True)
class RunColumn:
    """One column of the run block, as the definitions page states it.

    Attributes
    ----------
    name : str
        The header; ``<id>`` in it is replaced by each rotor's id, and
        :data:`IDENTIFIER_PLACEHOLDER` stands for the row's identifier names.
    unit : str
        The unit, ``"-"`` for a dimensionless value or a key.
    source : str
        Where the value comes from, in words.
    """

    name: str
    unit: str
    source: str

    @property
    def per_rotor(self) -> bool:
        """Whether the column is repeated once per declared rotor."""
        return _ROTOR in self.name

    @property
    def anchor(self) -> str:
        """The anchor of the column on ``docs/definitions/the-run-block.md``."""
        if self.name == IDENTIFIER_PLACEHOLDER:
            return "identifiers"
        return self.name.replace(_ROTOR, "-id").replace("_", "-").lower()


def _column(name: str, unit: str, source: str) -> RunColumn:
    return RunColumn(name, unit, source)


#: THE BLOCK, in its order. A ``<id>`` group of consecutive columns is written
#: once per declared rotor, id ascending, the group's columns together for each
#: rotor (``J0, MTIP0, MHEL0, J1, MTIP1, MHEL1``).
RUN_BLOCK_SPEC: tuple[RunColumn, ...] = (
    _column("POL", "-", "the matrix row's polar"),
    _column("POINT_ID", "-", "1-based position of the point in its polar's sweep order"),
    _column("POINT", "-", "the point name the per-point files carry"),
    _column(IDENTIFIER_PLACEHOLDER, "as written", "the row's IDENTIFIERS pairs, in order"),
    _column("RUN_TYPE", "-", "the workflow selected for the row"),
    _column("ALPHA", "deg", "angle of attack as written"),
    _column("BETA", "deg", "sideslip as written"),
    _column("MACH", "-", "the point's Mach number"),
    _column("RE", "-", "the point's Reynolds number, in millions"),
    _column("VINF", "m/s", "free-stream speed of the point"),
    _column("VREF", "m/s", "the loads export's reference velocity"),
    _column("RPM<id>", "rev/min", "speed of rotor <id>, signed about its declared axis"),
    _column("J<id>", "-", "advance ratio rotor <id> ran at, VINF/(abs(n) D<id>)"),
    _column("MTIP<id>", "-", "tip Mach number of rotor <id>"),
    _column("MHEL<id>", "-", "helical tip Mach number of rotor <id>"),
    _column("J", "-", "advance ratio the row requested"),
    _column("J_CLOCK", "-", "advance ratio the clock rotor ran at"),
    _column("RPM_CLOCK", "rev/min", "speed of the clock rotor, with its hand"),
    _column("THRUST", "N", "thrust condition the row states"),
    _column("ALT", "m", "altitude of the resolved atmosphere"),
    _column("RHO", "kg/m^3", "density of the point"),
    _column("TEMP", "K", "temperature of the point"),
    _column("MU", "Pa s", "dynamic viscosity, in scientific notation"),
    _column("SREF", "m^2", "reference area"),
    _column("CREF", "m", "reference chord"),
    _column("BREF", "m", "reference span"),
    _column("XMOM", "m", "moment reference point x, mesh frame"),
    _column("YMOM", "m", "moment reference point y, mesh frame"),
    _column("ZMOM", "m", "moment reference point z, mesh frame"),
    _column("D<id>", "m", "diameter of rotor <id>"),
    _column("ADISC<id>", "m^2", "disc area of rotor <id>, pi D^2/4"),
    _column("PITCH<id>", "deg", "pitch of the frame R<id>"),
    _column("TOE<id>", "deg", "toe of the frame R<id>"),
    _column("FIRST_STEP", "-", "first step of the averaging window, 1-based"),
    _column("LAST_STEP", "-", "last step of the averaging window, inclusive"),
    _column("STEPS", "-", "steps in the averaging window"),
    _column("WINDOW_REVS", "-", "clock rotor revolutions the window spans"),
    _column("WINDOW_PASSAGES", "-", "clock rotor blade passages the window spans"),
)

#: The columns that are NA on a steady row whatever is stated: the window.
_WINDOW_COLUMNS = frozenset({"FIRST_STEP", "LAST_STEP", "STEPS", "WINDOW_REVS", "WINDOW_PASSAGES"})


@dataclass(frozen=True)
class RotorRunValues:
    """What one declared rotor contributes to a run block row.

    Attributes
    ----------
    rotor_id : int
        The rotor's declared id (``RotorBlock.id``).
    diameter_m : float
        The rotor's diameter.
    pitch_deg, toe_deg : float
        The pitch and toe of its frame R<id>
        (:func:`pyflightstream.post.axes.rotor_frame`).
    rpm : float or None
        The speed it turned at on this row, signed about its declared axis;
        None on a row that turns no rotor.
    mtip, mhel : float or None
        Its tip and helical Mach numbers on this row, None where not stated.
    """

    rotor_id: int
    diameter_m: float
    pitch_deg: float
    toe_deg: float
    rpm: float | None = None
    mtip: float | None = None
    mhel: float | None = None


def _rotor_ids(rotors: Sequence[RotorRunValues] | Sequence[int]) -> list[int]:
    ids = [int(r.rotor_id if isinstance(r, RotorRunValues) else r) for r in rotors]
    if any(value < 0 for value in ids) or len(set(ids)) != len(ids):
        raise ProductError(f"rotor ids {ids} must be distinct integers of zero or more")
    return sorted(ids)


def _expanded(identifiers: Sequence[str], rotor_ids: Sequence[int]) -> list[tuple[str, str]]:
    """Return ``(header, template)`` pairs in block order."""
    out: list[tuple[str, str]] = []
    index = 0
    while index < len(RUN_BLOCK_SPEC):
        spec = RUN_BLOCK_SPEC[index]
        if spec.name == IDENTIFIER_PLACEHOLDER:
            out.extend((str(name), spec.name) for name in identifiers)
            index += 1
            continue
        if not spec.per_rotor:
            out.append((spec.name, spec.name))
            index += 1
            continue
        end = index
        while end < len(RUN_BLOCK_SPEC) and RUN_BLOCK_SPEC[end].per_rotor:
            end += 1
        group = RUN_BLOCK_SPEC[index:end]
        for rotor in rotor_ids:
            out.extend((g.name.replace(_ROTOR, str(rotor)), g.name) for g in group)
        index = end
    return out


def run_block_columns(
    identifiers: Sequence[str] = (), rotor_ids: Sequence[int] = ()
) -> tuple[str, ...]:
    """Return the run block's header for a row's identifiers and the declared rotors.

    Parameters
    ----------
    identifiers : sequence of str, optional
        The ``IDENTIFIERS`` names of the matrix, in the order written.
    rotor_ids : sequence of int, optional
        The ids of the rotors the reference declares; none writes no per-rotor
        column.

    Returns
    -------
    tuple of str
        The headers, in the order of :data:`RUN_BLOCK_SPEC`.

    Raises
    ------
    ProductError
        If an identifier spells a column of the block, or a rotor id is
        negative or repeated.

    Examples
    --------
    >>> run_block_columns(("FLAP",), (0,))[:5]
    ('POL', 'POINT_ID', 'POINT', 'FLAP', 'RUN_TYPE')
    >>> (c := run_block_columns(("FLAP",), (0,)))[c.index("VREF") + 1 : c.index("J")]
    ('RPM0', 'J0', 'MTIP0', 'MHEL0')
    """
    ids = _rotor_ids(rotor_ids)
    pairs = _expanded(identifiers, ids)
    headers = [header for header, _template in pairs]
    clash = sorted({name for name in identifiers if headers.count(str(name)) > 1})
    if clash:
        raise ProductError(
            f"IDENTIFIERS names {', '.join(clash)}, which the run block already writes; "
            "rename the identifier"
        )
    return tuple(headers)


def _finite_or_na(value: object) -> object:
    if value is None or isinstance(value, bool):
        return NOT_APPLICABLE
    if isinstance(value, int | float):
        number = float(value)
        if not math.isfinite(number):
            return NOT_APPLICABLE
        return value + 0 if isinstance(value, int) else number + 0.0
    text = str(value).strip()
    return text if text else NOT_APPLICABLE


def _stated(condition: Mapping[str, object], name: str) -> object:
    for key, value in condition.items():
        if str(key).casefold() == name.casefold():
            return value
    return None


def _rotor_values(rotor: RotorRunValues, vinf: object) -> dict[str, object]:
    rpm = rotor.rpm
    advance: object = None
    if isinstance(rpm, int | float) and isinstance(vinf, int | float) and float(rpm) != 0.0:
        advance = float(vinf) / (abs(float(rpm)) / 60.0 * float(rotor.diameter_m))
    return {
        "RPM<id>": rpm,
        "J<id>": advance,
        "MTIP<id>": rotor.mtip,
        "MHEL<id>": rotor.mhel,
        "D<id>": rotor.diameter_m,
        "ADISC<id>": math.pi * float(rotor.diameter_m) ** 2 / 4.0,
        "PITCH<id>": rotor.pitch_deg,
        "TOE<id>": rotor.toe_deg,
    }


def _viscosity(value: object) -> object:
    if isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value):
        return f"{float(value):.5e}"
    return value


def run_block_row(
    *,
    pol: str,
    point_id: int,
    point: str,
    run_type: str,
    condition: Mapping[str, object],
    identifiers: Mapping[str, object] | None = None,
    rotors: Sequence[RotorRunValues] = (),
) -> dict[str, object]:
    """Return one row of the run block, keyed by header, in block order.

    Parameters
    ----------
    pol : str
        The matrix row's polar, as the matrix writes it.
    point_id : int
        1-based position of the point in its polar's sweep order.
    point : str
        The point name.
    run_type : str
        One of :data:`RUN_TYPES`.
    condition : mapping of str to object
        The point's scalar columns (``ALPHA`` to ``ZMOM`` and the window),
        matched case-folded; a column it does not state is ``NA``. A numeric
        ``MU`` is written in scientific notation as text.
    identifiers : mapping of str to object, optional
        The row's ``IDENTIFIERS`` pairs, in the order written.
    rotors : sequence of RotorRunValues, optional
        Every rotor the reference declares, whatever the row turns.

    Returns
    -------
    dict of str to object
        The values in the order of :func:`run_block_columns`; a value that does
        not exist is ``NA``. The window columns are ``NA`` on a steady row.

    Raises
    ------
    ProductError
        If ``run_type`` is not one of :data:`RUN_TYPES`, ``point_id`` is not a
        positive integer, or a column clashes as in :func:`run_block_columns`.

    Examples
    --------
    >>> [run_block_row(pol="P0001", point_id=1, point="AL+000", run_type="steady",
    ...                condition={"VINF": 40.0, "FIRST_STEP": 3})[name]
    ...  for name in ("POL", "VINF", "RHO", "FIRST_STEP")]
    ['P0001', 40.0, 'NA', 'NA']
    """
    if run_type not in RUN_TYPES:
        raise ProductError(f"run type {run_type!r} is not one of {', '.join(RUN_TYPES)}")
    if isinstance(point_id, bool) or not isinstance(point_id, int) or point_id < 1:
        raise ProductError(f"POINT_ID {point_id!r} must be a 1-based integer")
    stated_identifiers = dict(identifiers or {})
    by_id = {int(rotor.rotor_id): rotor for rotor in rotors}
    columns = run_block_columns(tuple(stated_identifiers), tuple(by_id))
    fixed: dict[str, object] = {"POL": pol, "POINT_ID": point_id, "POINT": point}
    fixed["RUN_TYPE"] = run_type
    vinf = _stated(condition, "VINF")
    per_rotor = {rotor_id: _rotor_values(rotor, vinf) for rotor_id, rotor in by_id.items()}
    templates = dict(_expanded(tuple(stated_identifiers), sorted(by_id)))
    row: dict[str, object] = {}
    for header in columns:
        template = templates[header]
        if template == IDENTIFIER_PLACEHOLDER:
            value = stated_identifiers[header]
        elif _ROTOR in template:
            rotor_id = int(header[len(template.split(_ROTOR)[0]) :])
            value = per_rotor[rotor_id][template]
        elif header in fixed:
            value = fixed[header]
        elif header in _WINDOW_COLUMNS and run_type == "steady":
            value = None
        else:
            value = _stated(condition, header)
        row[header] = _finite_or_na(_viscosity(value) if header == "MU" else value)
    return row
