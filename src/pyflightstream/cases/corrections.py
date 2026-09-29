"""The quasi-steady wheel's correction routes: the pproc's choice and the calibration file (0.31.0).

A quasi-steady WHEEL solves every blade once per clocking and reads its
unsteady content (0P, 1P) off the samples. Its loads carry no wake lag, so
0.31.0 ships the MACHINE that applies a correction beside the raw products,
and no correction of its own: every route is OFF by default, NOT VALIDATED,
and the choice of a recommended route and of its numbers is research's.

The routes, as the pproc's ``[qsteady_correction]`` table names them:

* ``route = "none"``, the default: nothing is corrected and nothing is written.
* ``route = "table"`` (route 4): a calibration TABLE, a discrepancy surface the
  user fitted, over the axes ``J``, ``ALPHA`` and ``K_1P``.
* ``route = "sector_offset"`` (route 2): a 0P offset calibrated from an axial
  unsteady SECTOR run at the same ``J``; the file names that run
  (``source_run_id``).
* The Theodorsen and Sears lift deficiency (route 1) is refused as a route and
  offered only as a DIAGNOSTIC (``diagnostic = "theodorsen"``): it is not
  validated against the unsteady solver, so 0.31.0 writes it beside the
  harmonics and applies it to nothing.
* A skewed-wake or dynamic-inflow model (route 3: ``dynamic_inflow``,
  ``skewed_wake``, ``pitt_peters``, ``coleman``) is refused: its double counting
  with the solver's own wake is unmeasured.

The calibration file is ``inputs/calibrations/<id>.toml``::

    route = "table"

    [[rows]]
    COMPONENT = "THRUST"
    J = 0.6
    ALPHA = 0.0
    K_1P = 0.05
    OFFSET_0P = 0.0
    GAIN_0P = 1.0
    GAIN_1P = 1.0
    PHASE_1P_DEG = 0.0

Each row names a COMPONENT (:data:`COMPONENTS`), its place on the three axes
(:data:`AXES`) and the four coefficients (:data:`COEFFICIENT_COLUMNS`). The
rows of one component form a TENSOR GRID over the axes whose values vary; an
axis with one value is constant, and constrains nothing. Inside the grid the
coefficients are interpolated multilinearly; a point OUTSIDE it is never
extrapolated (:meth:`Calibration.lookup` says so and the post names the skip).

A file that cannot be read is refused WHOLE at load by :class:`CalibrationError`,
naming the line: an unknown route, an unknown component or column, a missing
column, a duplicate row, a set of rows that is not a grid, a number that is not
finite. The model lives in the cases row so the plan validates the file a row's
pproc names before the run, and the post, which applies it, reads the same
model.

This module imports nothing from the package but the floor.
"""

from __future__ import annotations

import itertools
import math
import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from pyflightstream._digest import text_sha256
from pyflightstream._errors import PyflightstreamError

__all__ = [
    "AXES",
    "CALIBRATIONS_DIR",
    "CALIBRATION_ROUTES",
    "COEFFICIENT_COLUMNS",
    "COMPONENTS",
    "CORRECTION_ROUTES",
    "DIAGNOSTICS",
    "ROTOR_COMPONENTS",
    "ROUTE1_WORDS",
    "ROUTE3_NAMES",
    "ROW_COLUMNS",
    "SECTION_COMPONENTS",
    "Calibration",
    "CalibrationError",
    "CalibrationRow",
    "ComponentGrid",
    "Lookup",
    "QsteadyCorrectionSpec",
    "calibration_path",
    "calibration_text",
    "parse_calibration",
    "read_calibration",
    "unoffered_route",
]

#: The folder of the workspace's ``inputs/`` a calibration lives in.
CALIBRATIONS_DIR = "calibrations"
#: Every value of ``[qsteady_correction] route``.
CORRECTION_ROUTES: tuple[str, ...] = ("none", "table", "sector_offset")
#: The routes a calibration file may state: the two the one applicator applies.
CALIBRATION_ROUTES: tuple[str, ...] = ("table", "sector_offset")
#: Every value of ``[qsteady_correction] diagnostic``.
DIAGNOSTICS: tuple[str, ...] = ("none", "theodorsen")
#: A route spelled with any of these words asks route 1 (the lift deficiency).
ROUTE1_WORDS: tuple[str, ...] = ("theodorsen", "sears", "lift_deficiency", "route_1", "route1")
#: The routes 3 names, refused as corrections.
ROUTE3_NAMES: tuple[str, ...] = ("dynamic_inflow", "skewed_wake", "pitt_peters", "coleman")
#: The axes of a calibration grid: the rotor's advance ratio ``J_<alias>``, the
#: angle of attack in degrees, and the 1P reduced frequency (per station for a
#: sectional component, the point's ``K_1P_MEAN`` for a rotor component).
AXES: tuple[str, ...] = ("J", "ALPHA", "K_1P")
#: The four coefficients of a row.
COEFFICIENT_COLUMNS: tuple[str, ...] = ("OFFSET_0P", "GAIN_0P", "GAIN_1P", "PHASE_1P_DEG")
#: Every column a row states, all required.
ROW_COLUMNS: tuple[str, ...] = ("COMPONENT", *AXES, *COEFFICIENT_COLUMNS)
#: The rotor's 0P quantities a row may name: its thrust and torque (N, N m, the
#: average table's ``THRUST_<alias>`` and ``TORQUE_<alias>``), its force and hub
#: moment in the reference frame (``FX_<alias>`` .. ``MZ_<alias>``), the
#: coefficients of the rotor table (``CT_<alias>``, ``CQ_<alias>``; ``CT`` also
#: corrects the average table's ``CT_PROPELLER``, which is the same quantity),
#: the rotorcraft thrust coefficient ``CT_ROTOR`` of the average table, and the
#: rotor table's in-plane coefficients ``CN``, ``CS``, ``CMN``, ``CMS``.
ROTOR_COMPONENTS: tuple[str, ...] = (
    "THRUST",
    "TORQUE",
    "FX",
    "FY",
    "FZ",
    "MX",
    "MY",
    "MZ",
    "CT",
    "CQ",
    "CT_ROTOR",
    "CN",
    "CS",
    "CMN",
    "CMS",
)
#: The sectional load quantities, by the names the sectional loads export prints.
SECTION_COMPONENTS: tuple[str, ...] = ("Fx", "Fz", "Moment")
#: Every component a row may name.
COMPONENTS: tuple[str, ...] = (*ROTOR_COMPONENTS, *SECTION_COMPONENTS)
#: The top-level keys of a calibration file.
_TOP_KEYS: tuple[str, ...] = ("route", "source_run_id", "wheel_run_id", "description", "rows")
#: How close two axis values are before they are one grid value, relative to the
#: axis's span (absolute where the span is zero).
_GRID_TOLERANCE = 1e-9

_ROUTE1_WHY = (
    "the Theodorsen and Sears lift deficiency (route 1) is offered as a DIAGNOSTIC only, "
    'never as a correction: write diagnostic = "theodorsen" in the pproc\'s '
    "[qsteady_correction] table to write it beside the harmonics. It is not validated "
    "against the unsteady solver, so 0.31.0 offers it as a diagnostic only"
)
_ROUTE3_WHY = (
    "a skewed-wake or dynamic-inflow model (route 3) is not offered as a correction "
    "because its double counting with the solver's own wake is unmeasured"
)


class CalibrationError(PyflightstreamError, ValueError):
    """A calibration file cannot be read, or cannot be built from the runs it names.

    Raised whole at load, naming the file and the line: nothing of a file
    that is refused is applied. (The pproc's ``[qsteady_correction]`` table is
    refused by its own model, as every pproc table is.) ``path`` is the file (None for text parsed
    with no file) and ``line`` the 1-based line the refusal points at, None
    where the whole file is at fault.
    """

    def __init__(self, message: str, *, path: Path | None = None, line: int | None = None):
        super().__init__(message)
        self.path = path
        self.line = line


def _spelled(route: str) -> str:
    return re.sub(r"[\s-]+", "_", str(route).strip().lower())


def unoffered_route(route: str) -> str | None:
    """Return why ``route`` is not offered as a correction, or None where it may be.

    Route 1 in any spelling that names Theodorsen, Sears or the lift
    deficiency, and route 3 by any of its four names, each with the reason.

    Examples
    --------
    >>> unoffered_route("table") is None
    True
    >>> "DIAGNOSTIC only" in unoffered_route("Theodorsen")
    True
    >>> "double counting" in unoffered_route("pitt-peters")
    True
    """
    spelled = _spelled(route)
    if any(word in spelled for word in ROUTE1_WORDS):
        return f"route {route!r}: {_ROUTE1_WHY}"
    if spelled in ROUTE3_NAMES:
        return f"route {route!r}: {_ROUTE3_WHY}"
    return None


class QsteadyCorrectionSpec(BaseModel):
    """The ``[qsteady_correction]`` table: which correction a quasi-steady wheel's post applies.

    Every route is off by default and NOT VALIDATED. A route names a
    calibration file of ``inputs/calibrations/``; the post writes each corrected
    product beside its raw file as ``<name>_corrected.csv`` and never over it.
    Read again by ``pyfs-matrix post``, so choosing or changing a route needs no
    new run. The Theodorsen lift deficiency is a diagnostic and never a route;
    a skewed-wake or dynamic-inflow route is refused.

    Examples
    --------
    >>> QsteadyCorrectionSpec().route, QsteadyCorrectionSpec().diagnostic
    ('none', 'none')
    >>> QsteadyCorrectionSpec(route="table", file="c001").file
    'c001'
    >>> QsteadyCorrectionSpec(route="table", file="c001.toml").file
    'c001'
    """

    model_config = ConfigDict(extra="forbid")

    #: The correction applied at post: "none" (the default) applies nothing,
    #: "table" a calibration table the user fitted (route 4), "sector_offset" a
    #: 0P offset calibrated from an axial unsteady sector run (route 2). Neither
    #: is validated; route 1 is a diagnostic and route 3 is refused.
    route: Literal["none", "table", "sector_offset"] = "none"
    #: The calibration file's id, the stem of inputs/calibrations/<id>.toml;
    #: required by a route other than "none". Written with its ".toml" suffix
    #: it names the same file, and the suffix is dropped.
    file: str | None = None
    #: A diagnostic written beside the harmonics and never applied: "none" (the
    #: default) or "theodorsen", the Theodorsen and Sears functions of each
    #: station's 1P reduced frequency next to its measured 1P amplitude and phase.
    diagnostic: Literal["none", "theodorsen"] = "none"

    @field_validator("route", mode="before")
    @classmethod
    def _refuse_the_routes_not_offered(cls, value: object) -> object:
        if isinstance(value, str):
            why = unoffered_route(value)
            if why is not None:
                raise ValueError(f"[qsteady_correction] {why}")
        return value

    @field_validator("file")
    @classmethod
    def _a_file_is_an_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        # "c001.toml" names the file "c001" names: the suffix is the folder's
        # one form, so it is accepted and dropped rather than refused.
        stem = value[: -len(".toml")] if value.lower().endswith(".toml") else value
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", stem):
            raise ValueError(
                f"[qsteady_correction] file = {value!r}: name the calibration by its id, the "
                "stem of inputs/calibrations/<id>.toml (the .toml suffix may be written), "
                "with no folder"
            )
        return stem

    @model_validator(mode="after")
    def _a_route_names_its_file(self) -> QsteadyCorrectionSpec:
        if self.route != "none" and not self.file:
            raise ValueError(
                f'[qsteady_correction] route = "{self.route}" names no file: write file = '
                '"<id>" for the calibration inputs/calibrations/<id>.toml it applies'
            )
        return self


@dataclass(frozen=True)
class CalibrationRow:
    """One row of a calibration file: a component, its place on the axes, its coefficients."""

    component: str
    j: float
    alpha_deg: float
    k_1p: float
    offset_0p: float
    gain_0p: float
    gain_1p: float
    phase_1p_deg: float
    line: int | None = None

    def axis(self, name: str) -> float:
        """Return the row's value on the axis ``name`` of :data:`AXES`."""
        return {"J": self.j, "ALPHA": self.alpha_deg, "K_1P": self.k_1p}[name]

    def coefficients(self) -> tuple[float, float, float, float]:
        """Return ``(OFFSET_0P, GAIN_0P, GAIN_1P, PHASE_1P_DEG)``."""
        return (self.offset_0p, self.gain_0p, self.gain_1p, self.phase_1p_deg)


@dataclass(frozen=True)
class Lookup:
    """What a grid gives at one point: the coefficients and the cell, or why it gives none.

    ``coefficients`` is ``(OFFSET_0P, GAIN_0P, GAIN_1P, PHASE_1P_DEG)``, None
    where the point is outside the grid or states no value on an axis that
    varies; ``cell`` maps each axis to the grid values bracketing the point
    (``[low, high]``) or to the one value of a constant axis; ``reason`` says
    why there are no coefficients.
    """

    coefficients: tuple[float, float, float, float] | None
    cell: Mapping[str, list[float]]
    reason: str | None = None
    outside: bool = False


@dataclass(frozen=True)
class ComponentGrid:
    """The tensor grid of one component: the values of each axis and a row at every node."""

    component: str
    values: Mapping[str, tuple[float, ...]]
    nodes: Mapping[tuple[float, ...], CalibrationRow]

    @property
    def varying(self) -> tuple[str, ...]:
        """The axes with more than one value, in the order of :data:`AXES`."""
        return tuple(axis for axis in AXES if len(self.values[axis]) > 1)

    def lookup(self, at: Mapping[str, float | None]) -> Lookup:
        """Interpolate the coefficients multilinearly at ``at``, never outside the grid."""
        cell: dict[str, list[float]] = {}
        brackets: list[tuple[str, int, float]] = []
        for axis in AXES:
            values = self.values[axis]
            if len(values) == 1:
                cell[axis] = [values[0]]
                continue
            stated = at.get(axis)
            if stated is None or not math.isfinite(float(stated)):
                return Lookup(
                    None,
                    cell,
                    reason=f"the point states no {axis}, on which the {self.component} grid varies",
                )
            x = float(stated)
            span = values[-1] - values[0]
            tolerance = _GRID_TOLERANCE * span
            if x < values[0] - tolerance or x > values[-1] + tolerance:
                return Lookup(
                    None,
                    {**cell, axis: [values[0], values[-1]]},
                    reason=(
                        f"{axis} = {x:.6g} is outside the {self.component} grid "
                        f"[{values[0]:.6g}, {values[-1]:.6g}], and a calibration is never "
                        "extrapolated"
                    ),
                    outside=True,
                )
            x = min(max(x, values[0]), values[-1])
            index = max(0, min(len(values) - 2, _bisect(values, x)))
            low, high = values[index], values[index + 1]
            weight = (x - low) / (high - low)
            cell[axis] = [low, high]
            brackets.append((axis, index, weight))
        total = [0.0, 0.0, 0.0, 0.0]
        for corner in itertools.product((0, 1), repeat=len(brackets)):
            share = 1.0
            key: dict[str, float] = {
                axis: self.values[axis][0] for axis in AXES if len(self.values[axis]) == 1
            }
            for (axis, index, weight), side in zip(brackets, corner, strict=True):
                share *= weight if side else 1.0 - weight
                key[axis] = self.values[axis][index + side]
            if share == 0.0:
                continue
            row = self.nodes[tuple(key[axis] for axis in AXES)]
            for position, value in enumerate(row.coefficients()):
                total[position] += share * value
        return Lookup((total[0], total[1], total[2], total[3]), cell)


def _bisect(values: Sequence[float], x: float) -> int:
    """Return the index i with values[i] <= x < values[i + 1] (the last interval at the end)."""
    for index in range(len(values) - 1):
        if x < values[index + 1]:
            return index
    return len(values) - 2


@dataclass(frozen=True)
class Calibration:
    """A calibration file as read: its route, its runs, its rows and each component's grid."""

    calibration_id: str
    route: str
    rows: tuple[CalibrationRow, ...]
    grids: Mapping[str, ComponentGrid]
    sha256: str
    path: Path | None = None
    source_run_id: str | None = None
    wheel_run_id: str | None = None
    description: str | None = None
    notes: tuple[str, ...] = field(default=())

    @property
    def components(self) -> tuple[str, ...]:
        """The components the file corrects, in the order of :data:`COMPONENTS`."""
        return tuple(name for name in COMPONENTS if name in self.grids)

    def lookup(self, component: str, at: Mapping[str, float | None]) -> Lookup | None:
        """Return the grid's coefficients for ``component`` at ``at``; None where it has no rows.

        Examples
        --------
        >>> text = calibration_text("table", [
        ...     CalibrationRow("THRUST", 0.5, 0.0, 0.0, 1.0, 1.0, 1.0, 0.0),
        ...     CalibrationRow("THRUST", 0.7, 0.0, 0.0, 3.0, 1.0, 1.0, 0.0),
        ... ])
        >>> found = parse_calibration(text).lookup("THRUST", {"J": 0.6})
        >>> round(found.coefficients[0], 12), found.cell["J"]
        (2.0, [0.5, 0.7])
        """
        grid = self.grids.get(component)
        return None if grid is None else grid.lookup(at)


def calibration_path(inputs_dir: str | Path, calibration_id: str) -> Path:
    """Return ``<inputs_dir>/calibrations/<id>.toml``."""
    return Path(inputs_dir) / CALIBRATIONS_DIR / f"{calibration_id}.toml"


def read_calibration(path: str | Path) -> Calibration:
    """Read and validate a calibration file; refuse it whole with :class:`CalibrationError`."""
    target = Path(path)
    try:
        data = target.read_bytes()
    except OSError as error:
        raise CalibrationError(
            f"the calibration {target} cannot be read: {error}", path=target
        ) from error
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CalibrationError(
            f"the calibration {target} is not UTF-8 text: {error}", path=target
        ) from error
    return parse_calibration(
        text, path=target, calibration_id=target.stem, sha256=text_sha256(text)
    )


def _row_lines(text: str) -> list[int]:
    """Return the 1-based line of each ``[[rows]]`` header, in order."""
    return [
        number
        for number, line in enumerate(text.splitlines(), start=1)
        if re.match(r"^\s*\[\[\s*rows\s*\]\]", line)
    ]


def _key_line(text: str, key: str, start: int, end: int | None) -> int | None:
    """Return the 1-based line in ``[start, end)`` where ``key`` is set, or None."""
    pattern = re.compile(rf"^\s*\"?{re.escape(key)}\"?\s*=")
    for number, line in enumerate(text.splitlines(), start=1):
        if number < start or (end is not None and number >= end):
            continue
        if pattern.match(line):
            return number
    return None


def parse_calibration(
    text: str,
    *,
    path: Path | None = None,
    calibration_id: str = "<text>",
    sha256: str | None = None,
) -> Calibration:
    """Parse and validate a calibration file's text; refuse it whole, naming the line."""
    where = str(path) if path is not None else f"calibration {calibration_id!r}"

    def refuse(message: str, line: int | None) -> CalibrationError:
        at = f" line {line}" if line is not None else ""
        return CalibrationError(f"{where}{at}: {message}", path=path, line=line)

    try:
        table = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        found = re.search(r"line (\d+)", str(error))
        raise refuse(f"not TOML: {error}", int(found.group(1)) if found else None) from error
    for key in table:
        if key not in _TOP_KEYS:
            raise refuse(
                f"unknown key {key!r}; a calibration states {', '.join(_TOP_KEYS)}",
                _key_line(text, key, 1, None),
            )
    route_line = _key_line(text, "route", 1, None)
    route = table.get("route")
    if not isinstance(route, str):
        raise refuse(
            f"route must be text, one of {', '.join(CALIBRATION_ROUTES)}; it is {route!r}",
            route_line,
        )
    why = unoffered_route(route)
    if why is not None:
        raise refuse(why, route_line)
    if route not in CALIBRATION_ROUTES:
        raise refuse(
            f"unknown route {route!r}; a calibration's route is one of "
            f"{', '.join(CALIBRATION_ROUTES)}",
            route_line,
        )
    runs: dict[str, str | None] = {}
    for key in ("source_run_id", "wheel_run_id", "description"):
        stated = table.get(key)
        if stated is not None and (not isinstance(stated, str) or not stated.strip()):
            raise refuse(
                f"{key} must be non-empty text; it is {stated!r}", _key_line(text, key, 1, None)
            )
        runs[key] = stated
    if route == "sector_offset" and not runs["source_run_id"]:
        raise refuse(
            'a route "sector_offset" calibration must name source_run_id, the run id of the '
            "axial unsteady sector run its offsets were taken from",
            route_line,
        )
    stated_rows = table.get("rows")
    if not isinstance(stated_rows, list) or not stated_rows:
        raise refuse(
            "the file states no [[rows]]; a calibration is at least one row",
            _key_line(text, "rows", 1, None),
        )
    headers = _row_lines(text)
    rows: list[CalibrationRow] = []
    for position, stated in enumerate(stated_rows):
        start = headers[position] if position < len(headers) else None
        end = headers[position + 1] if position + 1 < len(headers) else None
        head = start if start is not None else _key_line(text, "rows", 1, None)
        rows.append(_row(stated, position, head, start, end, text, refuse))
    grids = _grids(rows, refuse)
    return Calibration(
        calibration_id=calibration_id,
        route=route,
        rows=tuple(rows),
        grids=grids,
        sha256=sha256 or text_sha256(text),
        path=path,
        source_run_id=runs["source_run_id"],
        wheel_run_id=runs["wheel_run_id"],
        description=runs["description"],
    )


def _row(
    stated: object,
    position: int,
    head: int | None,
    start: int | None,
    end: int | None,
    text: str,
    refuse: Any,
) -> CalibrationRow:
    label = f"row {position + 1}"
    if not isinstance(stated, Mapping):
        raise refuse(f"{label} is not a table of columns", head)

    def line_of(key: str) -> int | None:
        if start is None:
            return head
        return _key_line(text, key, start, end) or head

    for key in stated:
        if key not in ROW_COLUMNS:
            raise refuse(
                f"{label}: unknown column {key!r}; a row states {', '.join(ROW_COLUMNS)}",
                line_of(str(key)),
            )
    missing = [key for key in ROW_COLUMNS if key not in stated]
    if missing:
        raise refuse(
            f"{label}: missing column(s) {', '.join(missing)}; every row states "
            f"{', '.join(ROW_COLUMNS)}",
            head,
        )
    component = stated["COMPONENT"]
    if not isinstance(component, str) or component not in COMPONENTS:
        raise refuse(
            f"{label}: unknown component {component!r}; a component is one of "
            f"{', '.join(COMPONENTS)}",
            line_of("COMPONENT"),
        )
    numbers: dict[str, float] = {}
    for key in (*AXES, *COEFFICIENT_COLUMNS):
        value = stated[key]
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise refuse(f"{label}: {key} must be a number; it is {value!r}", line_of(key))
        if not math.isfinite(float(value)):
            raise refuse(f"{label}: {key} = {value!r} is not a finite number", line_of(key))
        numbers[key] = float(value)
    return CalibrationRow(
        component=component,
        j=numbers["J"],
        alpha_deg=numbers["ALPHA"],
        k_1p=numbers["K_1P"],
        offset_0p=numbers["OFFSET_0P"],
        gain_0p=numbers["GAIN_0P"],
        gain_1p=numbers["GAIN_1P"],
        phase_1p_deg=numbers["PHASE_1P_DEG"],
        line=head,
    )


def _distinct(values: Sequence[float]) -> tuple[float, ...]:
    ordered = sorted(values)
    span = ordered[-1] - ordered[0]
    tolerance = _GRID_TOLERANCE * span if span > 0.0 else 0.0
    kept: list[float] = []
    for value in ordered:
        if not kept or value - kept[-1] > tolerance:
            kept.append(value)
    return tuple(kept)


def _snap(value: float, grid: Sequence[float]) -> float:
    return min(grid, key=lambda node: abs(node - value))


def _grids(rows: Sequence[CalibrationRow], refuse: Any) -> dict[str, ComponentGrid]:
    grids: dict[str, ComponentGrid] = {}
    for component in COMPONENTS:
        mine = [row for row in rows if row.component == component]
        if not mine:
            continue
        values = {axis: _distinct([row.axis(axis) for row in mine]) for axis in AXES}
        nodes: dict[tuple[float, ...], CalibrationRow] = {}
        for row in mine:
            key = tuple(_snap(row.axis(axis), values[axis]) for axis in AXES)
            if key in nodes:
                raise refuse(
                    f"duplicate row: {component} at J = {key[0]:g}, ALPHA = {key[1]:g}, "
                    f"K_1P = {key[2]:g} is also stated at line {nodes[key].line}",
                    row.line,
                )
            nodes[key] = row
        expected = math.prod(len(values[axis]) for axis in AXES)
        if len(nodes) != expected:
            absent = [
                key
                for key in itertools.product(*(values[axis] for axis in AXES))
                if key not in nodes
            ]
            first = absent[0]
            raise refuse(
                f"the {component} rows are not a grid: {len(nodes)} rows over "
                + " x ".join(f"{len(values[axis])} {axis}" for axis in AXES)
                + f" values ({expected} nodes); the node J = {first[0]:g}, ALPHA = "
                f"{first[1]:g}, K_1P = {first[2]:g} is not stated (and {len(absent) - 1} "
                "more). Every combination of the values an axis takes must be a row",
                mine[-1].line,
            )
        grids[component] = ComponentGrid(component, values, nodes)
    return grids


def _number(value: float) -> str:
    """Return a TOML number that reads back to the same float."""
    text = repr(float(value))
    return text if ("." in text or "e" in text or "inf" in text or "nan" in text) else text + ".0"


def calibration_text(
    route: str,
    rows: Sequence[CalibrationRow],
    *,
    source_run_id: str | None = None,
    wheel_run_id: str | None = None,
    description: str | None = None,
) -> str:
    """Return a calibration file's text, which :func:`parse_calibration` reads back unchanged.

    Examples
    --------
    >>> row = CalibrationRow("CT", 0.6, 0.0, 0.0, 0.001, 1.0, 1.0, 0.0)
    >>> text = calibration_text("table", [row])
    >>> parse_calibration(text).rows[0].offset_0p
    0.001
    """
    lines = [f'route = "{route}"']
    for key, value in (
        ("source_run_id", source_run_id),
        ("wheel_run_id", wheel_run_id),
        ("description", description),
    ):
        if value is not None:
            escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key} = "{escaped}"')
    for row in rows:
        lines += [
            "",
            "[[rows]]",
            f'COMPONENT = "{row.component}"',
            f"J = {_number(row.j)}",
            f"ALPHA = {_number(row.alpha_deg)}",
            f"K_1P = {_number(row.k_1p)}",
            f"OFFSET_0P = {_number(row.offset_0p)}",
            f"GAIN_0P = {_number(row.gain_0p)}",
            f"GAIN_1P = {_number(row.gain_1p)}",
            f"PHASE_1P_DEG = {_number(row.phase_1p_deg)}",
        ]
    return "\n".join(lines) + "\n"
