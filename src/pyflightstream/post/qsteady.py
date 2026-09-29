"""The quasi-steady rotor's products (0.30.0): its clockings, their average and its validity.

A ``qsteady_rotor`` point is one steady solve of a periodic sector, or the
steady solves of a whole wheel at ``PASSAGE_POSITIONS`` clockings inside one
blade passage. The run leaves, beside the point's own loads export, the
point's quasi-steady record (``<point>_qsteady.json``: the case, the rotor,
each clocking and the loads export it wrote, the plan's validity record) and
one loads export per further clocking. This module reads them and writes:

* the CLOCKINGS table, ``polars/P<sim>-<ALIAS>_qs_positions.csv``: one row
  per point and clocking, the rotor's loads and each blade's at that clocking,
  the shape of the unsteady rotor's phase-locked table (one row per azimuth);
* the AVERAGE table, ``polars/P<sim>-<ALIAS>_qs_avg.csv``: one row per point,
  the mean over its clockings, the shape of the unsteady time average;
* the 1P reduced frequency of each station (``K_1P``) in the point's sections
  table, and the point's validity columns (:data:`VALIDITY_COLUMNS`) in all
  three, and in the point's row of the super file;
* for a WHEEL point, the per-point validity file
  ``<point>_qsteady_validity.json`` in its datapoint folder, beside the run's
  record (:func:`write_point_validity_file`), which carries the thrust and
  torque shares from the stations above k = 0.1.

The loads are the rotor's force in N and its moment about its HUB in N m, in
the loads frame's axes, and the thrust and torque along its shaft, each by
:func:`pyflightstream.post.products.rotor_shaft_loads`, which the product
stage hands in so that this module computes no statics of its own.

THE VALIDITY. ``k = Omega c / (2 V_rel)`` per station
(:mod:`pyflightstream.cases.qsteady`). From the sectional loads export where
the point has one: its ``Chord`` at its ``Offset``, read as the radius of a
distribution cut along the blade from the hub (a block of the rotor in the
record's layout); the shares of thrust and torque from the stations above 0.1
then take the export's ``Fx`` as the force along the shaft and ``Fz`` as the
in-plane force, each per unit span, over the stations' strips. Else the
plan's estimate from the mesh, with the shares ``NA``. The definitions page
states both and what is not measured.
"""

from __future__ import annotations

import csv
import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pyflightstream._errors import ProductError
from pyflightstream._tokens import CONTEXT_COLUMNS, NOT_APPLICABLE, POLAR_ID_COLUMN
from pyflightstream.cases.qsteady import (
    REDUCED_FREQUENCY_LIMIT,
    REDUCED_FREQUENCY_WATCH,
    record_file_name,
    reduced_frequencies,
    reduced_frequency,
    strip_lengths,
    validity_file_name,
)
from pyflightstream.post._tables import _cell, context_row, write_csv_table
from pyflightstream.results import parse_loads
from pyflightstream.workspace.inputs import qsteady_record_rotor_alias

#: The point's validity, carried by every quasi-steady product of the point.
VALIDITY_COLUMNS: tuple[str, ...] = (
    "K_1P_MIN",
    "K_1P_MAX",
    "K_1P_MEAN",
    "SPAN_PCT_K_GT_0_05",
    "SPAN_PCT_K_GT_0_1",
    "THRUST_PCT_K_GT_0_1",
    "TORQUE_PCT_K_GT_0_1",
    "K_1P_SOURCE",
)
#: The column the sections table of a quasi-steady wheel point gains per station.
STATION_COLUMN = "K_1P"
#: The six loads and the two shaft components, per rotor and per blade.
LOAD_NAMES: tuple[str, ...] = ("FX", "FY", "FZ", "MX", "MY", "MZ", "THRUST", "TORQUE")
#: The spine of the clockings table, before the validity and the loads.
POSITION_SPINE: tuple[str, ...] = (
    POLAR_ID_COLUMN,
    "REDUCTION",
    "ROTOR",
    "AZIMUTH",
    "POSITION",
    "POSITIONS",
    *CONTEXT_COLUMNS,
    "XMOM",
    "YMOM",
    "ZMOM",
)
#: The spine of the average table.
AVERAGE_SPINE: tuple[str, ...] = (
    POLAR_ID_COLUMN,
    "REDUCTION",
    "ROTOR",
    "POSITIONS",
    *CONTEXT_COLUMNS,
    "XMOM",
    "YMOM",
    "ZMOM",
)
POSITIONS_SUFFIX = "_qs_positions.csv"
AVERAGE_SUFFIX = "_qs_avg.csv"

ShaftLoads = Callable[..., Any]


def read_qsteady_record(loads_path: Path) -> dict[str, Any] | None:
    """Return the quasi-steady record the run wrote beside a point's loads export, or None.

    Raises
    ------
    ProductError
        The record is there and is not JSON of an object.
    """
    path = loads_path.with_name(Path(record_file_name(loads_path.name)).name)
    if not path.is_file():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        raise ProductError(f"the quasi-steady record {path} cannot be read: {error}") from error
    if not isinstance(record, dict):
        raise ProductError(f"the quasi-steady record {path} is not an object")
    return record


def _omega(record: Mapping[str, Any]) -> float:
    return float(record["rpm"]) * 2.0 * math.pi / 60.0


def _number(text: object) -> float | None:
    try:
        value = float(str(text))
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _read_table(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        columns = next(reader)
        return columns, [row for row in reader]


def _rewrite(path: Path, columns: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)


@dataclass(frozen=True)
class PointValidity:
    """The validity of one quasi-steady wheel point, as its products carry it."""

    values: dict[str, object]

    def cells(self) -> tuple[object, ...]:
        """Return the point's values of :data:`VALIDITY_COLUMNS`, ``None`` where not known."""
        return tuple(self.values.get(column) for column in VALIDITY_COLUMNS)


def validity_of_the_plan(record: Mapping[str, Any]) -> PointValidity:
    """Return the validity the plan estimated from the mesh, the shares not known."""
    plan = record.get("validity") or {}
    if not isinstance(plan, Mapping) or plan.get("note") or "k_min" not in plan:
        return PointValidity({})
    return PointValidity(
        {
            "K_1P_MIN": plan.get("k_min"),
            "K_1P_MAX": plan.get("k_max"),
            "K_1P_MEAN": plan.get("k_mean"),
            "SPAN_PCT_K_GT_0_05": plan.get("span_pct_k_gt_0_05"),
            "SPAN_PCT_K_GT_0_1": plan.get("span_pct_k_gt_0_1"),
            "K_1P_SOURCE": "mesh",
        }
    )


def validity_cells(validity: PointValidity) -> dict[str, str]:
    """Return the point's validity as cells of :data:`VALIDITY_COLUMNS`, ``NA`` where unknown."""
    return {
        column: _cell(value) if value is not None else NOT_APPLICABLE
        for column, value in zip(VALIDITY_COLUMNS, validity.cells(), strict=True)
    }


def write_point_validity_file(
    loads_path: Path, record: Mapping[str, Any], validity: PointValidity
) -> Path:
    """Write a wheel point's validity after the run, beside its loads export (0.30.0).

    ``<point>_qsteady_validity.json`` in the point's datapoint folder, next to
    the run's own ``<point>_qsteady.json``: the values of
    :data:`VALIDITY_COLUMNS` (``K_1P_MIN``, ``K_1P_MAX``, ``K_1P_MEAN``, the
    span above 0.05 and above 0.1, and the SHARES OF THRUST AND TORQUE from
    the stations above k = 0.1), where they come from (``K_1P_SOURCE``:
    ``sections`` after the run, ``mesh`` the plan's estimate, whose shares are
    null), and the plan's record as the run kept it. The run's record is a
    hashed input of the run and is never rewritten; this file is the post's,
    rewritten by every post.

    Returns
    -------
    Path
        The file written.
    """
    path = loads_path.with_name(Path(validity_file_name(loads_path.name)).name)
    payload = {
        "schema_version": 1,
        "run_type": record.get("run_type"),
        "case": record.get("case"),
        "rotor": record.get("rotor"),
        "rpm": record.get("rpm"),
        "run_record": Path(record_file_name(loads_path.name)).name,
        "validity": {
            column: value for column, value in zip(VALIDITY_COLUMNS, validity.cells(), strict=True)
        },
        "plan": record.get("validity"),
        "written_by": "the post stage; the run record beside it is not rewritten",
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def add_reduced_frequency_to_sections(
    path: Path, record: Mapping[str, Any], *, velocity_m_per_s: float
) -> PointValidity | None:
    """Give a wheel point's sections table ``K_1P`` per station and the point's validity.

    The stations are the rows the record's layout gives to the rotor
    (``ROTOR``); their radius is ``|Offset|`` and their chord ``Chord``. The
    point's summary is taken over the rows of the rotor's FIRST blade family
    present (``FAMILY``), or over every rotor row where the layout names no
    family, so a wheel's six blades do not count one station six times. The
    table is rewritten in place with ``K_1P`` and :data:`VALIDITY_COLUMNS`
    after its own columns; a row of no rotor reads ``NA`` in ``K_1P``.

    Returns
    -------
    PointValidity or None
        None, and the table untouched, where no row is the rotor's.
    """
    columns, rows = _read_table(path)
    index = {name: at for at, name in enumerate(columns)}
    if not {"ROTOR", "Offset", "Chord", "Fx", "Fz"} <= set(index):
        return None
    alias = qsteady_record_rotor_alias(record)
    omega = _omega(record)
    k_of_row: list[float | None] = []
    for row in rows:
        radius = _number(row[index["Offset"]])
        chord = _number(row[index["Chord"]])
        if row[index["ROTOR"]] != alias or radius is None or chord is None:
            k_of_row.append(None)
            continue
        k_of_row.append(
            reduced_frequency(
                omega_rad_s=omega,
                chord_m=chord,
                radius_m=abs(radius),
                velocity_m_per_s=velocity_m_per_s,
            )
        )
    candidates = [at for at, k in enumerate(k_of_row) if k is not None]
    if not candidates:
        return None
    families = [str(name) for name in record.get("families_blades") or []]
    present = {rows[at][index["FAMILY"]] for at in candidates} if "FAMILY" in index else set()
    first = next((family for family in families if family in present), None)
    chosen = (
        [at for at in candidates if rows[at][index["FAMILY"]] == first]
        if first is not None
        else candidates
    )
    chosen.sort(key=lambda at: abs(_number(rows[at][index["Offset"]]) or 0.0))
    radii = [abs(_number(rows[at][index["Offset"]]) or 0.0) for at in chosen]
    chords = [_number(rows[at][index["Chord"]]) or 0.0 for at in chosen]
    frequencies = reduced_frequencies(
        radii, chords, omega_rad_s=omega, velocity_m_per_s=velocity_m_per_s, source="sections"
    )
    strips = strip_lengths(radii)
    thrust = [
        (_number(rows[at][index["Fx"]]) or 0.0) * w for at, w in zip(chosen, strips, strict=True)
    ]
    torque = [
        (_number(rows[at][index["Fz"]]) or 0.0) * r * w
        for at, r, w in zip(chosen, radii, strips, strict=True)
    ]
    above = [k > REDUCED_FREQUENCY_LIMIT for k in frequencies.k]

    def share(values: Sequence[float]) -> float | None:
        total = sum(values)
        if total == 0.0:
            return None
        return 100.0 * sum(v for v, hot in zip(values, above, strict=True) if hot) / total

    validity = PointValidity(
        {
            "K_1P_MIN": frequencies.k_min,
            "K_1P_MAX": frequencies.k_max,
            "K_1P_MEAN": frequencies.k_mean,
            "SPAN_PCT_K_GT_0_05": 100.0 * frequencies.span_fraction_above(REDUCED_FREQUENCY_WATCH),
            "SPAN_PCT_K_GT_0_1": 100.0 * frequencies.span_fraction_above(REDUCED_FREQUENCY_LIMIT),
            "THRUST_PCT_K_GT_0_1": share(thrust),
            "TORQUE_PCT_K_GT_0_1": share(torque),
            "K_1P_SOURCE": "sections",
        }
    )
    tail = [_cell(value) for value in validity.cells()]
    _rewrite(
        path,
        [*columns, STATION_COLUMN, *VALIDITY_COLUMNS],
        [
            [*row, _cell(k) if k is not None else NOT_APPLICABLE, *tail]
            for row, k in zip(rows, k_of_row, strict=True)
        ],
    )
    return validity


def _view(record: Mapping[str, Any], members: Sequence[str]) -> SimpleNamespace:
    hub = record["hub_m"]
    return SimpleNamespace(
        axis_vector=tuple(float(v) for v in record["axis_vector"]),
        x_m=float(hub[0]),
        y_m=float(hub[1]),
        z_m=float(hub[2]),
        members=list(members),
    )


def _loads_of(shaft: Any) -> tuple[float | None, ...]:
    force = getattr(shaft, "force_n", None)
    moment = getattr(shaft, "moment_hub_nm", None)
    if force is None or moment is None:
        return (None,) * len(LOAD_NAMES)
    return (*force, *moment, shaft.thrust_n, shaft.torque_nm)


@dataclass(frozen=True)
class Clocking:
    """One clocking of one wheel point: where blade one is, and the loads."""

    index: int
    azimuth_deg: float
    loads: tuple[float | None, ...]


def clockings_of(
    record: Mapping[str, Any],
    folder: Path,
    *,
    reference: Any,
    density_kg_m3: float,
    shaft_loads: ShaftLoads,
) -> list[Clocking] | str:
    """Return the loads of every clocking of one point, or why they cannot be read.

    Each clocking's loads export is read where the point's own sits, and the
    rotor's and each blade's loads taken by ``shaft_loads``
    (:func:`pyflightstream.post.products.rotor_shaft_loads`) at that export's
    reference velocity and the point's density.
    """
    families = [str(name) for name in record.get("families_blades") or []]
    members = [*(str(name) for name in record.get("families_general") or []), *families]
    datum = float(record.get("blade1_azimuth_deg") or 0.0)
    found: list[Clocking] = []
    for position in record.get("positions") or []:
        path = folder / Path(str(position["loads"])).name
        if not path.is_file():
            return f"the loads export of clocking {position['index']}, {path.name}, is not on disk"
        try:
            report = parse_loads(path.read_text(encoding="utf-8", errors="replace"))
        except Exception as error:  # noqa: BLE001 -- any unreadable export is named, not raised
            return f"the loads export of clocking {position['index']}, {path.name}: {error}"
        speed = report.reference_velocity_m_s or report.freestream_velocity_m_s
        arguments = {
            "reference": reference,
            "density_kg_m3": density_kg_m3,
            "speed_m_s": speed,
            "alpha_deg": report.angle_of_attack_deg,
            "beta_deg": report.sideslip_deg,
            "analysis_frame": getattr(report, "frame", None),
        }
        values = list(
            _loads_of(shaft_loads(report.surfaces, rotor=_view(record, members), **arguments))
        )
        for family in families:
            values.extend(
                _loads_of(shaft_loads(report.surfaces, rotor=_view(record, [family]), **arguments))
            )
        found.append(
            Clocking(
                int(position["index"]),
                (datum + float(position["clocking_deg"])) % 360.0,
                tuple(values),
            )
        )
    return sorted(found, key=lambda clocking: clocking.index)


def load_columns(record: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the loads columns of a rotor's tables: the rotor's, then each blade's."""
    alias = qsteady_record_rotor_alias(record)
    families = [str(name) for name in record.get("families_blades") or []]
    return tuple(f"{name}_{owner}" for owner in (alias, *families) for name in LOAD_NAMES)


def _mean(values: Sequence[float | None]) -> float | None:
    known = [value for value in values if value is not None]
    if len(known) != len(values) or not known:
        return None
    return sum(known) / len(known)


@dataclass(frozen=True)
class WheelPoint:
    """What the two tables need of one point."""

    pol: str
    condition: Mapping[str, object]
    record: Mapping[str, Any]
    clockings: list[Clocking]
    validity: PointValidity


def write_qsteady_tables(
    positions_path: Path,
    average_path: Path,
    points: Sequence[WheelPoint],
    *,
    reference: Any,
) -> tuple[Path, Path] | None:
    """Write the clockings table and the average table of one rotor of one simulation.

    Returns None, writing nothing, where no point holds a clocking.
    """
    usable = [point for point in points if point.clockings]
    if not usable:
        return None
    columns = load_columns(usable[0].record)
    lengths = reference.as_lengths() if reference is not None else None
    moment = tuple(reference.as_moment_point().values()) if reference is not None else (None,) * 3
    position_rows = []
    average_rows = []
    for point in usable:
        context = context_row(point.condition, lengths)
        alias = qsteady_record_rotor_alias(point.record)
        count = len(point.clockings)
        for clocking in point.clockings:
            position_rows.append(
                (
                    point.pol,
                    "qsteady_position",
                    alias,
                    clocking.azimuth_deg,
                    clocking.index,
                    count,
                    *context,
                    *moment,
                    *point.validity.cells(),
                    *clocking.loads,
                )
            )
        average_rows.append(
            (
                point.pol,
                "qsteady_average",
                alias,
                count,
                *context,
                *moment,
                *point.validity.cells(),
                *(
                    _mean([clocking.loads[at] for clocking in point.clockings])
                    for at in range(len(columns))
                ),
            )
        )
    return (
        write_csv_table(
            positions_path, (*POSITION_SPINE, *VALIDITY_COLUMNS, *columns), position_rows
        ),
        write_csv_table(average_path, (*AVERAGE_SPINE, *VALIDITY_COLUMNS, *columns), average_rows),
    )
