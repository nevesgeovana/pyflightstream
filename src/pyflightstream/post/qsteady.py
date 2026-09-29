"""The quasi-steady rotor's products (0.30.0): its clockings, their average and its validity.

A ``qsteady_rotor`` point is one steady solve of a periodic sector, or the
steady solves of a whole wheel at ``PASSAGE_POSITIONS`` clockings inside one
blade passage. The run leaves, beside the point's own loads export, the
point's quasi-steady record (``<point>_qsteady.json``: the case, the rotor,
each clocking and the loads export it wrote, the plan's validity record) and
one loads export per further clocking. This module reads them (the record
as :class:`pyflightstream.cases.qsteady.QsteadyRecord`, through its one
reader, which the product stage calls) and writes:

* the CLOCKINGS table, ``polars/P<sim>-<ALIAS>_qs_positions.csv``: one row
  per point and clocking, the rotor's loads and each blade's at that clocking,
  the shape of the unsteady rotor's phase-locked table (one row per azimuth);
* the AVERAGE table, ``polars/P<sim>-<ALIAS>_qs_avg.csv``: one row per point,
  the mean over its clockings, the shape of the unsteady time average;
* for a WHEEL point, the loads its row of the rotor table is taken from: each
  surface's mean over the clockings (0.31.0, :func:`mean_clocking_surfaces`);
* for a WHEEL point, every clocking's rows in the point's sections table, each
  with its ``CLOCKING`` and each blade's own ``AZIMUTH`` at that clocking
  (0.31.0, :func:`add_clockings_to_sections`), the wheel exporting its section
  distributions at every clocking;
* the 1P reduced frequency of each station (``K_1P``) in the point's sections
  table, and the point's validity columns (:data:`VALIDITY_COLUMNS`) in all
  three, and in the point's row of the super file;
* for a WHEEL point, the per-point validity file
  ``<point>_qsteady_validity.json`` in its datapoint folder, beside the run's
  record (:func:`write_point_validity_file`), which carries the thrust and
  torque shares from the stations above k = 0.1;
* for a WHEEL point, the rotor state its correction routes read
  (:data:`STATE_COLUMNS`, 0.31.0, :func:`rotor_state`): the thrust
  coefficient in the rotor and the propeller conventions, the advance ratio,
  the climb and induced inflows and the wake skew, from the mean loads over
  its clockings, beside the validity columns in the average table and in the
  per-point validity file.

The loads are the rotor's force in N and its moment about its HUB in N m, in
the loads frame's axes, and the thrust and torque along its shaft, each by
:func:`pyflightstream.post.products.rotor_shaft_loads`, which the product
stage hands in so that this module computes no statics of its own.

THE VALIDITY. ``k = Omega c / (2 V_rel)`` per station
(:mod:`pyflightstream.cases.qsteady`). From the sectional loads export where
the point has one: its ``Chord`` at its ``Offset``, read as the radius of a
distribution cut along the blade from the hub (a block of the rotor in the
record's layout); the shares of thrust and torque from the stations above 0.1
then take each station's sectional force projected on the rotor's axis in the
frame its distribution was cut in (0.31.0, through
:func:`pyflightstream.post.axes.section_station_shaft_loads`), and its moment
about the axis, each per unit span, over the stations' strips. Else the
plan's estimate from the mesh, with the shares ``NA``. The definitions page
states both and what is not measured.
"""

from __future__ import annotations

import csv
import json
import math
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pyflightstream._errors import ProductError
from pyflightstream._tokens import CONTEXT_COLUMNS, NOT_APPLICABLE, POLAR_ID_COLUMN
from pyflightstream.cases.qsteady import (
    POSITION_SUFFIX,
    REDUCED_FREQUENCY_LIMIT,
    REDUCED_FREQUENCY_WATCH,
    QsteadyClocking,
    QsteadyRecord,
    glauert_induced_inflow,
    record_file_name,
    reduced_frequencies,
    reduced_frequency,
    strip_lengths,
    validity_file_name,
)
from pyflightstream.post._tables import _cell, context_row, write_csv_table
from pyflightstream.post.axes import (
    clocked_blade_azimuth_deg,
    free_stream_on_rotor_axis,
    section_station_shaft_loads,
)
from pyflightstream.results import parse_loads

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
#: A wheel point's rotor state (0.31.0), beside its validity in the average
#: table and in its validity file; the definitions page states each with its
#: equation. ``MU_ROTOR`` and not ``MU``: ``MU`` is the air's viscosity in
#: every table's condition block, and one name is one quantity in a folder.
STATE_COLUMNS: tuple[str, ...] = (
    "CT_ROTOR",
    "CT_PROPELLER",
    "MU_ROTOR",
    "LAMBDA_C",
    "LAMBDA_I",
    "CHI_DEG",
)
#: The column the sections table of a quasi-steady wheel point gains per station.
STATION_COLUMN = "K_1P"
#: The column a wheel point's sections table gains (0.31.0): the clocking each
#: row was cut at, ``i`` of ``theta_i``, 0 the point's own solve.
CLOCKING_COLUMN = "CLOCKING"
#: How far a station of a later clocking may sit from clocking 0's before the
#: post says the stations are not aligned: a thousandth of the block's largest
#: offset, the resolution the sectional loads export prints its offsets to.
STATION_TOLERANCE = 1e-3
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


def rotor_speed(record: QsteadyRecord, alias: str) -> float | None:
    """Return the speed, in rev/min and signed, a point's run turned rotor ``alias`` at.

    The row's speed as the builder resolved it and wrote it in the point's
    quasi-steady record (the free stream turns at it). None where the record
    is of another rotor. The record is read by
    :func:`pyflightstream.cases.qsteady.read_qsteady_record`, which refuses one
    that states no number.
    """
    if record.rotor_alias != str(alias):
        return None
    return float(record.rpm)


def _omega(record: QsteadyRecord) -> float:
    return float(record.rpm) * 2.0 * math.pi / 60.0


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
    """The validity of one quasi-steady wheel point, as its products carry it.

    ``notes`` (0.31.0) are what the post says about the values in its log, one
    line each: a share written ``NA`` and why.
    """

    values: dict[str, object]
    notes: tuple[str, ...] = ()

    def cells(self) -> tuple[object, ...]:
        """Return the point's values of :data:`VALIDITY_COLUMNS`, ``None`` where not known."""
        return tuple(self.values.get(column) for column in VALIDITY_COLUMNS)


def validity_of_the_plan(record: QsteadyRecord) -> PointValidity:
    """Return the validity the plan estimated from the mesh, the shares not known."""
    plan = record.validity or {}
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
    loads_path: Path,
    record: QsteadyRecord,
    validity: PointValidity,
    state: RotorState | None = None,
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
    rewritten by every post. Since 0.31.0 it carries the point's rotor state
    (``rotor_state``, the values of :data:`STATE_COLUMNS`, null where not
    known or where ``state`` is not given).

    Returns
    -------
    Path
        The file written.
    """
    path = loads_path.with_name(Path(validity_file_name(loads_path.name)).name)
    payload = {
        "schema_version": 1,
        "run_type": record.run_type,
        "case": record.case,
        "rotor": record.rotor_alias,
        "rpm": record.rpm,
        "run_record": Path(record_file_name(loads_path.name)).name,
        "validity": {
            column: value for column, value in zip(VALIDITY_COLUMNS, validity.cells(), strict=True)
        },
        "rotor_state": {
            column: (state.values.get(column) if state is not None else None)
            for column in STATE_COLUMNS
        },
        "plan": record.validity,
        "written_by": "the post stage; the run record beside it is not rewritten",
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def clocking_section_export(position: QsteadyClocking, kind: str) -> str | None:
    """Return a clocking's section export of ``kind`` as the point's record names it, or None.

    The record of a wheel that cuts sections names, per clocking, the file of
    each section export the script wrote (``section_exports``, 0.31.0), keyed
    by the export kind (``sectional_loads``, ``sections``,
    ``plot_sections_cp``). None for a kind the clocking did not export and for
    every record written before 0.31.0, whose wheel exported its sections at
    clocking 0 only.
    """
    exports = position.section_exports
    if exports is None:
        return None
    name = exports.get(kind)
    return name if name else None


def wheel_block_identity(
    record: QsteadyRecord, families: Sequence[str], clocking: int
) -> tuple[str | None, float | None]:
    """Return the ``ROTOR`` and ``AZIMUTH`` a wheel point's block of sections states (0.31.0).

    The rotor is the record's where it owns every family of the block, else
    None. A block of ONE blade states where THAT blade is at ``clocking``
    (:func:`~pyflightstream.post.axes.clocked_blade_azimuth_deg`); any other
    block of the rotor states where blade one is, which is what ``AZIMUTH``
    means in every other sections table; a block no rotor owns states none.
    """
    blades = list(record.families_blades)
    owned = {*blades, *record.families_general}
    if not families or not set(families) <= owned:
        return None, None
    blade = blades.index(families[0]) + 1 if len(families) == 1 and families[0] in blades else 1
    return record.rotor_alias, clocked_blade_azimuth_deg(
        record.blade1_azimuth_deg,
        blade=blade,
        blades=record.blades,
        clocking=clocking,
        positions=len(record.positions),
        rpm=record.rpm,
    )


@dataclass(frozen=True)
class ClockedSections:
    """What :func:`add_clockings_to_sections` could not do, for the post to say.

    ``missing`` maps a clocking to why its rows are not in the table (the post
    names each under the table); ``misaligned`` names each clocking whose
    stations are not clocking 0's (the post warns, and the rows are kept).
    """

    missing: dict[int, str]
    misaligned: list[str]


def _stations(
    rows: Sequence[Sequence[str]], index: Mapping[str, int]
) -> list[tuple[str, str, float | None]]:
    return [
        (row[index["FAMILY"]], row[index["PLANE"]], _number(row[index["Offset"]])) for row in rows
    ]


def _aligned(
    first: Sequence[tuple[str, str, float | None]], other: Sequence[tuple[str, str, float | None]]
) -> bool:
    if [station[:2] for station in first] != [station[:2] for station in other]:
        return False
    largest = max((abs(station[2] or 0.0) for station in first), default=0.0)
    return all(
        a[2] is not None and b[2] is not None and abs(a[2] - b[2]) <= STATION_TOLERANCE * largest
        for a, b in zip(first, other, strict=True)
    )


def add_clockings_to_sections(
    path: Path,
    record: QsteadyRecord,
    folder: Path,
    *,
    tabled: Callable[[Path, str], Path | None],
) -> ClockedSections:
    """Give a wheel point's sections table every clocking's rows (0.31.0).

    ``path`` is the table written from the point's own sectional loads export,
    clocking 0. Each further clocking's export, named by the point's record
    (:func:`clocking_section_export`) and read beside the point's exports in
    ``folder``, is tabled by ``tabled`` (the product stage's own writer of a
    sections table, with the point's layout and condition) and its rows are
    appended after clocking 0's, in the order of the clockings. The table gains
    :data:`CLOCKING_COLUMN` after its own columns, and ``AZIMUTH`` states each
    block's blade at that clocking, with the rotor in ``ROTOR``
    (:func:`wheel_block_identity`), on every row, clocking 0 included.

    Every clocking is cut at the same stations by construction; a clocking
    whose blocks, planes or offsets differ from clocking 0's (to
    :data:`STATION_TOLERANCE` of the largest offset) is named in the result
    and its rows are kept. A clocking whose export is not named, not on disk
    or not readable is named and left out, and the table keeps the others.
    """
    columns, rows = _read_table(path)
    index = {name: at for at, name in enumerate(columns)}
    by_clocking: dict[int, list[list[str]]] = {0: rows}
    result = ClockedSections(missing={}, misaligned=[])
    for position in sorted(record.positions, key=lambda entry: entry.index):
        clocking = position.index
        if clocking == 0:
            continue
        name = clocking_section_export(position, "sectional_loads")
        if name is None:
            result.missing[clocking] = (
                "the point's record names no sectional loads export for this clocking; a "
                "wheel run before 0.31.0 exported its sections at clocking 0 only"
            )
            continue
        export = folder / Path(name).name
        if not export.is_file():
            result.missing[clocking] = f"the sectional loads export {export.name} is not on disk"
            continue
        scratch = path.with_name(f"{path.stem}{POSITION_SUFFIX}{clocking:02d}.partial.csv")
        try:
            done = tabled(scratch, export.read_text(encoding="utf-8", errors="replace"))
            if done is None:
                result.missing[clocking] = f"{export.name} declares no section"
                continue
            more_columns, more = _read_table(done)
        except (ProductError, OSError) as error:
            result.missing[clocking] = f"{export.name}: {error}"
            continue
        finally:
            scratch.unlink(missing_ok=True)
        if more_columns != columns:
            result.missing[clocking] = (
                f"{export.name} tables to other columns than clocking 0's export"
            )
            continue
        by_clocking[clocking] = more
    stations = {"FAMILY", "PLANE", "Offset"} <= set(index)
    for clocking, more in sorted(by_clocking.items()):
        if clocking and stations and not _aligned(_stations(rows, index), _stations(more, index)):
            result.misaligned.append(
                f"clocking {clocking} is not cut at clocking 0's stations (its blocks, planes "
                "or offsets differ); its rows are tabled as exported"
            )
    written: list[list[str]] = []
    for clocking, more in sorted(by_clocking.items()):
        for row in more:
            cells = list(row)
            if {"FAMILY", "ROTOR", "AZIMUTH"} <= set(index):
                family = cells[index["FAMILY"]]
                families = [] if family in ("", NOT_APPLICABLE) else family.split("+")
                rotor, azimuth = wheel_block_identity(record, families, clocking)
                cells[index["ROTOR"]] = _cell(rotor)
                cells[index["AZIMUTH"]] = _cell(azimuth)
            written.append([*cells, str(clocking)])
    _rewrite(path, [*columns, CLOCKING_COLUMN], written)
    return result


#: The frame a section distribution is cut in that states the GEOMETRY's
#: axes: the moment reference frame the run creates, a translation of the
#: reference frame whose axes it keeps (0.31.0, the shares' projection).
GEOMETRY_SECTION_FRAMES = frozenset({"MRP"})

#: The suffix a clocking's copy of a frame carries (``<frame>_QS<ii>``): the
#: same frame turned about the shaft with the wheel.
_CLOCKING_FRAME = re.compile(rf"^(?P<frame>.+){POSITION_SUFFIX.upper()}\d{{2}}$")


def shaft_in_section_frame(record: QsteadyRecord, frame: str) -> tuple[float, float, float] | None:
    """Return the rotor's axis in the axes of section frame ``frame``, or None (0.31.0).

    A frame of the record's rotor, ``<ALIAS>_SMRP``, ``<ALIAS>_RMRP`` or a
    blade's ``<ALIAS>_RMRP<k>``, and each clocking's copy of one
    (``<frame>_QS<ii>``), is the hub frame turned about the shaft, and the hub
    frame is built with the shaft on its axis ``shaft_frame_axis`` (the
    rotor's letter, or Z of a shaft stated as a vector): in its own axes the
    rotor's axis ``axis_vector`` is that unit axis, whatever the turn. A
    frame of :data:`GEOMETRY_SECTION_FRAMES` keeps the geometry's axes, in
    which the axis is ``axis_vector`` itself. Any other frame (one a setup
    creates, a hub frame kept from before a row's rotation) is None: its axes
    are not the package's to know.
    """
    name = str(frame).strip().upper()
    clocked = _CLOCKING_FRAME.match(name)
    if clocked is not None:
        name = clocked.group("frame")
    if name in GEOMETRY_SECTION_FRAMES:
        vector = tuple(float(value) for value in record.axis_vector)
        return (vector[0], vector[1], vector[2])
    alias = str(record.rotor_alias).strip().upper()
    own = name in (f"{alias}_SMRP", f"{alias}_RMRP") or (
        name.startswith(f"{alias}_RMRP") and name[len(alias) + 5 :].isdigit()
    )
    letter = str(record.shaft_frame_axis).strip().upper()
    if not own or letter not in ("X", "Y", "Z"):
        return None
    unit = [0.0, 0.0, 0.0]
    unit["XYZ".index(letter)] = 1.0
    return (unit[0], unit[1], unit[2])


def _section_frames(layout: Sequence[Mapping[str, object]]) -> dict[tuple[str, str], str | None]:
    """Return the frame each ``(FAMILY, PLANE)`` block of a run's sections layout was cut in.

    None for a block the layout names under two frames or under none.
    """
    frames: dict[tuple[str, str], set[str]] = {}
    for block in layout:
        families = block.get("families")
        if not isinstance(families, list):
            continue
        key = ("+".join(str(family) for family in families), str(block.get("plane", "")))
        frames.setdefault(key, set()).add(str(block.get("frame", "") or ""))
    return {
        key: next(iter(names)) if len(names) == 1 and "" not in names else None
        for key, names in frames.items()
    }


def add_reduced_frequency_to_sections(
    path: Path,
    record: QsteadyRecord,
    *,
    velocity_m_per_s: float,
    layout: Sequence[Mapping[str, object]] | None = None,
) -> PointValidity | None:
    """Give a wheel point's sections table ``K_1P`` per station and the point's validity.

    The stations are the rows the record's layout gives to the rotor
    (``ROTOR``); their radius is ``|Offset|`` and their chord ``Chord``. The
    point's summary is taken over the rows of the rotor's FIRST blade family
    present (``FAMILY``), or over every rotor row where the layout names no
    family, so a wheel's six blades do not count one station six times, and
    over clocking 0's rows where the table holds every clocking
    (:data:`CLOCKING_COLUMN`, 0.31.0), the point's own solve. The
    table is rewritten in place with ``K_1P`` and :data:`VALIDITY_COLUMNS`
    after its own columns; a row of no rotor reads ``NA`` in ``K_1P``.

    THE SHARES ARE TAKEN ALONG THE ROTOR'S AXIS (0.31.0). Each station's
    sectional force, the export's ``Fx`` and ``Fz`` in the axes of the frame
    its distribution was cut in (``layout``, the run's ``sections_layout``,
    read by ``FAMILY`` and ``PLANE``), is projected on the record's
    ``axis_vector`` stated in that frame (:func:`shaft_in_section_frame`) by
    :func:`pyflightstream.post.axes.section_station_shaft_loads`: the thrust
    per unit span is the force along the axis and the torque per unit span its
    moment about the axis, from the in-plane (tangential) component at the
    station's ``Offset``. Until 0.31.0 the export's ``Fx`` was the thrust and
    ``Fz |Offset|`` the torque, which holds only for a frame whose x is the
    shaft. A caller holding no ``layout`` states that the sections are cut in
    the rotor's own frames. A share is ``NA``, with a line in
    :attr:`PointValidity.notes`, where a station's frame or plane is not one
    whose axes are known, where the total is zero, or where stations of
    opposite sign put the share outside 0 to 100 per cent: the total then has
    no sign a share of it could be read against.

    Returns
    -------
    PointValidity or None
        None, and the table untouched, where no row is the rotor's.
    """
    columns, rows = _read_table(path)
    index = {name: at for at, name in enumerate(columns)}
    if not {"ROTOR", "Offset", "Chord", "Fx", "Fz"} <= set(index):
        return None
    alias = record.rotor_alias
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
    if CLOCKING_COLUMN in index:
        candidates = [at for at in candidates if rows[at][index[CLOCKING_COLUMN]] == "0"]
    if not candidates:
        return None
    families = list(record.families_blades)
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
    notes: list[str] = []
    frame_of = _section_frames(layout) if layout is not None else None
    along: list[tuple[float, float]] = []
    projected = True
    for at, w in zip(chosen, strips, strict=True):
        row = rows[at]
        family = row[index["FAMILY"]] if "FAMILY" in index else ""
        plane = row[index["PLANE"]] if "PLANE" in index else ""
        if frame_of is None:
            frame: str | None = f"{alias}_RMRP"
        else:
            frame = frame_of.get((family, plane))
        shaft = shaft_in_section_frame(record, frame) if frame is not None else None
        station = (
            section_station_shaft_loads(
                _number(row[index["Fx"]]) or 0.0,
                _number(row[index["Fz"]]) or 0.0,
                _number(row[index["Offset"]]) or 0.0,
                plane=plane,
                shaft=shaft,
            )
            if shaft is not None
            else None
        )
        if station is None:
            why = (
                f"the run's sections layout names no one frame for block {family} {plane}"
                if frame is None
                else f"the axes of frame {frame} are not known to the post"
                if shaft is None
                else f"the force columns of a cut in plane {plane or 'NA'} are not read"
            )
            notes.append(
                f"THRUST_PCT_K_GT_0_1 and TORQUE_PCT_K_GT_0_1 read NA: {why}, so the "
                f"sectional force of rotor {alias} cannot be projected on its axis"
            )
            projected = False
            break
        along.append((station[0] * w, station[1] * w))
    above = [k > REDUCED_FREQUENCY_LIMIT for k in frequencies.k]

    def share(values: Sequence[float], name: str) -> float | None:
        total = sum(values)
        if total == 0.0:
            notes.append(f"{name} reads NA: the total over the stations of rotor {alias} is zero")
            return None
        value = 100.0 * sum(v for v, hot in zip(values, above, strict=True) if hot) / total
        if not 0.0 <= value <= 100.0:
            notes.append(
                f"{name} reads NA: the stations of rotor {alias} carry loads of opposite "
                f"sign, so the share above k = 0.1 would be {value:.5g} per cent, outside "
                "0 to 100, and the total has no sign to read it against"
            )
            return None
        return value

    thrust_share = torque_share = None
    if projected:
        thrust_share = share([pair[0] for pair in along], "THRUST_PCT_K_GT_0_1")
        torque_share = share([pair[1] for pair in along], "TORQUE_PCT_K_GT_0_1")
    validity = PointValidity(
        {
            "K_1P_MIN": frequencies.k_min,
            "K_1P_MAX": frequencies.k_max,
            "K_1P_MEAN": frequencies.k_mean,
            "SPAN_PCT_K_GT_0_05": 100.0 * frequencies.span_fraction_above(REDUCED_FREQUENCY_WATCH),
            "SPAN_PCT_K_GT_0_1": 100.0 * frequencies.span_fraction_above(REDUCED_FREQUENCY_LIMIT),
            "THRUST_PCT_K_GT_0_1": thrust_share,
            "TORQUE_PCT_K_GT_0_1": torque_share,
            "K_1P_SOURCE": "sections",
        },
        notes=tuple(notes),
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


def _view(record: QsteadyRecord, members: Sequence[str]) -> SimpleNamespace:
    hub = record.hub_m
    return SimpleNamespace(
        axis_vector=tuple(float(v) for v in record.axis_vector),
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
    """One clocking of one wheel point: where blade one is, and the loads.

    ``azimuth_deg`` is None where the record does not state where blade one
    is (the product writes ``NA``).
    """

    index: int
    azimuth_deg: float | None
    loads: tuple[float | None, ...]


def clockings_of(
    record: QsteadyRecord,
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

    Where blade one is at each clocking is the sections table's own reading
    (0.31.0), :func:`~pyflightstream.post.axes.clocked_blade_azimuth_deg`:
    ``datum + sign(rpm) * theta_i``, so a left-hand wheel's clocking turns
    blade one backwards here as it does there. Until 0.31.0 this added
    ``theta_i`` unsigned, and the two tables of one left-hand wheel disagreed.
    """
    families = list(record.families_blades)
    members = [*record.families_general, *families]
    found: list[Clocking] = []
    for position in record.positions:
        path = folder / Path(position.loads).name
        if not path.is_file():
            return f"the loads export of clocking {position.index}, {path.name}, is not on disk"
        try:
            report = parse_loads(path.read_text(encoding="utf-8", errors="replace"))
        except Exception as error:  # noqa: BLE001 -- any unreadable export is named, not raised
            return f"the loads export of clocking {position.index}, {path.name}: {error}"
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
                position.index,
                clocked_blade_azimuth_deg(
                    record.blade1_azimuth_deg,
                    blade=1,
                    blades=record.blades,
                    clocking=position.index,
                    positions=len(record.positions),
                    rpm=record.rpm,
                ),
                tuple(values),
            )
        )
    return sorted(found, key=lambda clocking: clocking.index)


#: The six components of a surface of a loads export, the ones a clocking mean
#: takes: the force and moment coefficients the rotor's statics read.
SURFACE_COMPONENTS: tuple[str, ...] = ("Cx", "Cy", "Cz", "CMx", "CMy", "CMz")


@dataclass(frozen=True)
class ClockingMean:
    """A wheel point's surfaces, each the mean of its loads over the point's clockings (0.31.0).

    ``surfaces`` holds the loads export's six components per surface, as
    coefficients by the point's own reference velocity, so the rotor table
    turns them into its coefficients by the same statics as any steady
    point's; ``clockings`` is k, the number of clockings the mean is over.
    """

    surfaces: dict[str, dict[str, float]]
    clockings: int


def mean_clocking_surfaces(
    record: QsteadyRecord, folder: Path, *, speed_m_s: float
) -> ClockingMean | str:
    """Return a wheel point's loads averaged over its clockings, or why they cannot be (0.31.0).

    The rotor table of a quasi-steady WHEEL point is the mean over its k
    clockings (0.31.0, P0310-ROTOR-MEAN), never clocking 0 alone.
    Each clocking's loads export, named by the point's record and read where
    the point's own sits, states every surface's force and moment as
    coefficients by that export's reference velocity; each is taken back to
    the point's own ``speed_m_s`` (a factor ``(V_ref,i / V_ref)^2``, the
    density being the point's at every clocking) and each surface's six
    components are averaged over the clockings by the one average of the
    clockings tables. The rotor's force and its moment about the hub are sums
    over its surfaces and a transfer linear in them, so the rotor's force and
    moment from these surfaces ARE the mean of its force and moment over the
    clockings, and every coefficient the table takes from them (``CT``,
    ``CQ``, ``CP``, ``ETA``, ``ETAW``, ``CN``, ``CS``, ``CMN``, ``CMS``) is
    of the mean loads, never a mean of per-clocking coefficients.

    A clocking whose export is not on disk or not readable, that states no
    reference velocity, is in another analysis frame than clocking 0's, or
    lists other surfaces, is the reason returned: the point is not a row,
    because a mean of the other clockings is not the point's mean.
    """
    positions = sorted(record.positions, key=lambda entry: entry.index)
    read: list[tuple[int, dict[str, dict[str, float]], float, object]] = []
    for position in positions:
        path = folder / Path(position.loads).name
        if not path.is_file():
            return f"the loads export of clocking {position.index}, {path.name}, is not on disk"
        try:
            report = parse_loads(path.read_text(encoding="utf-8", errors="replace"))
        except Exception as error:  # noqa: BLE001 -- any unreadable export is named, not raised
            return f"the loads export of clocking {position.index}, {path.name}: {error}"
        stated = report.reference_velocity_m_s
        if not isinstance(stated, int | float) or not math.isfinite(stated) or stated <= 0.0:
            return (
                f"the loads export of clocking {position.index}, {path.name}, states no "
                "reference velocity, which is what its coefficients are normalised by"
            )
        surfaces = {
            str(name): {key: float(row.get(key, 0.0) or 0.0) for key in SURFACE_COMPONENTS}
            for name, row in report.surfaces.items()
        }
        read.append((position.index, surfaces, float(stated), getattr(report, "frame", None)))
    if not read:
        return "the point's record names no clocking"
    first_index, first, _speed, first_frame = read[0]
    for index, surfaces, _stated, frame in read[1:]:
        if frame != first_frame:
            return (
                f"the loads export of clocking {index} states the analysis frame {frame!r} "
                f"and clocking {first_index}'s states {first_frame!r}"
            )
        if list(surfaces) != list(first):
            return (
                f"the loads export of clocking {index} lists other surfaces than clocking "
                f"{first_index}'s"
            )
    point_speed = float(speed_m_s)
    scale = [
        (stated / point_speed) ** 2 if point_speed > 0.0 else 1.0 for _i, _s, stated, _f in read
    ]
    meaned: dict[str, dict[str, float]] = {}
    for name in first:
        components: dict[str, float] = {}
        for key in SURFACE_COMPONENTS:
            value = _mean(
                [
                    surfaces[name][key] * factor
                    for (_i, surfaces, _v, _f), factor in zip(read, scale, strict=True)
                ]
            )
            components[key] = 0.0 if value is None else value
        meaned[name] = components
    return ClockingMean(surfaces=meaned, clockings=len(read))


@dataclass(frozen=True)
class RotorState:
    """A wheel point's rotor state (0.31.0): the values of :data:`STATE_COLUMNS`.

    ``notes`` are what the post says about them in its log, one line each: a
    value written ``NA`` and why.
    """

    values: dict[str, float | None]
    notes: tuple[str, ...] = ()

    def cells(self) -> tuple[float | None, ...]:
        """Return the values of :data:`STATE_COLUMNS`, ``None`` where not known."""
        return tuple(self.values.get(column) for column in STATE_COLUMNS)


def rotor_state(
    record: QsteadyRecord,
    clockings: Sequence[Clocking],
    *,
    density_kg_m3: float | None,
    velocity_m_s: float | None,
    alpha_deg: float,
    beta_deg: float,
) -> RotorState:
    """Return a wheel point's rotor state from the mean thrust over its clockings (0.31.0).

    ``T`` is the rotor's thrust along its axis, the mean over the clockings of
    ``THRUST_<alias>`` (the one average of the clockings tables, which is the
    thrust of the rotor table's mean loads); ``rho`` the point's density,
    ``V`` its free-stream speed, ``Omega = 2 pi |rpm| / 60``, ``n = |rpm| / 60``,
    ``R = D / 2`` and ``A = pi R^2`` of the record's rotor, and ``alpha_p`` the
    angle between the rotor's axis and the direction of flight
    (:func:`pyflightstream.post.axes.free_stream_on_rotor_axis`)::

        CT_ROTOR     = T / (rho A (Omega R)^2)
        CT_PROPELLER = T / (rho n^2 D^4)
        MU_ROTOR     = V sin(alpha_p) / (Omega R)
        LAMBDA_C     = V cos(alpha_p) / (Omega R)
        LAMBDA_I     = CT_ROTOR / (2 sqrt(MU_ROTOR^2 + (LAMBDA_C + LAMBDA_I)^2))
        CHI_DEG      = atan2(MU_ROTOR, LAMBDA_C + LAMBDA_I)   in degrees

    ``LAMBDA_I`` by :func:`pyflightstream.cases.qsteady.glauert_induced_inflow`.
    A value that cannot be taken is None with a line in :attr:`RotorState.notes`:
    a thrust not known at every clocking, a density, speed or rotor that is
    not stated, or an induced inflow that does not converge (and ``CHI_DEG``
    with it).
    """
    alias = record.rotor_alias
    notes: list[str] = []
    values: dict[str, float | None] = dict.fromkeys(STATE_COLUMNS)
    thrust = _mean([clocking.loads[LOAD_NAMES.index("THRUST")] for clocking in clockings])
    rate = abs(float(record.rpm)) / 60.0
    diameter = float(record.diameter_m)
    if thrust is None or not clockings:
        notes.append(
            f"the rotor state of rotor {alias} reads NA: its thrust is not known at every clocking"
        )
        return RotorState(values, tuple(notes))
    if density_kg_m3 is None or not density_kg_m3 > 0.0 or rate <= 0.0 or diameter <= 0.0:
        notes.append(
            f"the rotor state of rotor {alias} reads NA: the point states no density, "
            "or the rotor no speed or no diameter"
        )
        return RotorState(values, tuple(notes))
    radius = diameter / 2.0
    tip = 2.0 * math.pi * rate * radius
    ct_rotor = thrust / (density_kg_m3 * math.pi * radius**2 * tip**2)
    values["CT_ROTOR"] = ct_rotor
    values["CT_PROPELLER"] = thrust / (density_kg_m3 * rate**2 * diameter**4)
    flight = free_stream_on_rotor_axis(record.axis_vector, alpha_deg, beta_deg)
    if velocity_m_s is None or not math.isfinite(velocity_m_s) or flight is None:
        notes.append(
            f"MU_ROTOR, LAMBDA_C, LAMBDA_I and CHI_DEG of rotor {alias} read NA: the "
            "point states no free-stream speed, or the rotor no axis"
        )
        return RotorState(values, tuple(notes))
    along, across = flight
    mu = float(velocity_m_s) * across / tip
    climb = float(velocity_m_s) * along / tip
    values["MU_ROTOR"] = mu
    values["LAMBDA_C"] = climb
    induced = glauert_induced_inflow(ct_rotor, mu, climb)
    if induced is None:
        notes.append(
            f"LAMBDA_I and CHI_DEG of rotor {alias} read NA: the momentum-theory induced "
            f"inflow did not converge at CT_ROTOR {ct_rotor:.6g}, MU_ROTOR "
            f"{mu:.6g}, LAMBDA_C {climb:.6g}, which momentum theory does not describe "
            "(a rotor descending into its own wake)"
        )
        return RotorState(values, tuple(notes))
    values["LAMBDA_I"] = induced
    values["CHI_DEG"] = math.degrees(math.atan2(mu, climb + induced)) + 0.0
    return RotorState(values, tuple(notes))


def load_columns(record: QsteadyRecord) -> tuple[str, ...]:
    """Return the loads columns of a rotor's tables: the rotor's, then each blade's."""
    alias = record.rotor_alias
    families = list(record.families_blades)
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
    record: QsteadyRecord
    clockings: list[Clocking]
    validity: PointValidity
    #: The rotor state of a wheel point (0.31.0), None where not taken.
    state: RotorState | None = None


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
        alias = point.record.rotor_alias
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
                *(point.state.cells() if point.state is not None else (None,) * len(STATE_COLUMNS)),
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
        write_csv_table(
            average_path,
            (*AVERAGE_SPINE, *VALIDITY_COLUMNS, *STATE_COLUMNS, *columns),
            average_rows,
        ),
    )
