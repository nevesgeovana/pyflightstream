"""Field operations that build a custom free-stream file of ``inputs/freestreams/``.

Pipeline role: prepares an INPUT. A row's ``FREESTREAM`` key names a file of
the workspace's ``inputs/freestreams/`` by its stem, ``<stem>.txt`` in the
manual's STRUCTURED form (a first line ``Npts Mpts``, then Npts x Mpts rows)
or ``<stem>.dat`` in its UNSTRUCTURED form (one row per point, no header),
every row ``x y z vx vy vz``. The field such a file holds is often built out
of other fields: a survey written by the post (``[[probes]] reusable_inflow``,
one ``fields/<point>_field_NN.inflow.dat`` per steady point, or one
``fields/<point>_field_NN_step_<N>.inflow.dat`` per step of an unsteady one)
mirrored, moved, averaged in time, or corrected by another survey. These are
the four operations, each a pure function of its fields:

* :func:`mirror_field`, through a coordinate plane: through ``y = 0`` a row
  ``x y z vx vy vz`` becomes ``x -y z vx -vy vz``;
* :func:`move_field`, so a source point (a hub) lands on a target point: the
  coordinates are translated, the velocities are unchanged;
* :func:`subtract_fields`, point by point on one grid:
  ``result = total - (other - reference)``, with the reference a uniform
  velocity the caller MUST state (the free stream the other field was
  solved in, so that only its induced part is removed; ``(0, 0, 0)`` where
  the other field is already induced-only); two grids that are not the
  same point set are refused, naming both files;
* :func:`time_mean_fields`, the mean of per-step fields of one unsteady run
  over equally spaced steps, every step holding the same points.

UNITS: metres and metres per second, in the global frame, read and written
as the files state them. Nothing is converted, rotated or interpolated, as
the custom free stream itself is read (``FREESTREAM_UNITS`` is the row's
statement of the file's units, and it applies to the result as it applies
to any file of the folder).

:func:`write_freestream` previews by default and writes only with
``apply=True``, into ``inputs/freestreams/<stem>.<txt|dat>`` beside a
provenance record ``<stem>.provenance.json`` naming the operation, its
parameters and every input file with its sha256. It never overwrites a file
unless asked, and it refuses a result the free-stream reader would refuse
(rows not in one YZ plane, fewer than two distinct y or z, a STRUCTURED
count that does not match). ``pyfs-workspace field`` is its command line.

Examples
--------
>>> from pyflightstream.workspace.fields import Field, mirror_field, move_field
>>> survey = Field(
...     form="UNSTRUCTURED",
...     rows=((1.0, 0.5, 0.0, 30.0, 2.0, 1.0), (1.0, -0.5, 1.0, 31.0, -2.0, 0.0)),
... )
>>> mirror_field(survey, plane="y").rows[0]
(1.0, -0.5, 0.0, 30.0, -2.0, 1.0)
>>> move_field(survey, source_point_m=(1.0, 0.0, 0.0), target_point_m=(0.0, 0.0, 2.0)).rows[1]
(0.0, -0.5, 3.0, 31.0, -2.0, 0.0)
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pyflightstream._digest import file_sha256, text_sha256
from pyflightstream.cases import CampaignConfigError
from pyflightstream.cases.freestream import read_field_rows
from pyflightstream.cases.workflows import FREESTREAM_DIR, FREESTREAM_FORMS
from pyflightstream.workspace import WorkspaceError

__all__ = [
    "DEFAULT_R_BODY_M",
    "FIELD_PROVENANCE_SCHEMA",
    "FILL_AZIMUTH_TOLERANCE_RAD",
    "MIRROR_PLANES",
    "POSITION_TOLERANCE_M",
    "Field",
    "FieldWrite",
    "FluctuationReport",
    "FluctuationWrite",
    "StepField",
    "fill_interior",
    "fluctuation_extent",
    "fluctuation_report",
    "mirror_field",
    "move_field",
    "read_field",
    "read_step_fields",
    "render_field",
    "render_fluctuation",
    "step_of",
    "subtract_fields",
    "time_mean_fields",
    "write_fluctuation",
    "write_freestream",
]

#: The schema the provenance record of a written field states.
FIELD_PROVENANCE_SCHEMA = "pyfs-field-operation/1"

#: The coordinate planes a field is mirrored through, by the axis whose sign
#: changes: ``"y"`` is the plane ``y = 0``. The value is the column of that
#: coordinate; its velocity component is three columns on.
MIRROR_PLANES: Mapping[str, int] = {"x": 0, "y": 1, "z": 2}

#: Two positions closer than this, in metres, along each axis are one point:
#: the default of :func:`subtract_fields` and :func:`time_mean_fields`.
POSITION_TOLERANCE_M = 1e-6

#: The radius about the x axis, in metres, inside which :func:`fill_interior`
#: replaces a probe (the body's radius; a default the caller states again).
DEFAULT_R_BODY_M = 0.38

#: Two probes whose azimuths about the x axis differ by no more than this,
#: in radians, are on one ray for :func:`fill_interior`.
FILL_AZIMUTH_TOLERANCE_RAD = 1e-3

#: The step a per-step field names in its file name, ``..._step_<N>.inflow.dat``
#: (the post's ``write_recorded_probe_fields`` stamps it).
_STEP_IN_NAME = re.compile(r"_step_([-+0-9.eE]+?)(?:\.inflow)?\.(?:dat|txt)$")

Row = tuple[float, float, float, float, float, float]


@dataclass(frozen=True)
class Field:
    """A custom free-stream field: its form, its rows and where it came from.

    Attributes
    ----------
    form : str
        ``STRUCTURED`` or ``UNSTRUCTURED``, the two forms of the manual.
    rows : tuple of tuple of float
        One ``(x, y, z, vx, vy, vz)`` per point, in metres and metres per
        second, global frame, in the file's order.
    header : str or None
        ``"Npts Mpts"`` of a STRUCTURED field, None for an UNSTRUCTURED one.
    source : str or None
        The file the field was read from, named in every refusal.
    """

    form: str
    rows: tuple[Row, ...]
    header: str | None = None
    source: str | None = None

    @property
    def name(self) -> str:
        """The name a refusal gives this field: its file, or ``the field``."""
        return self.source or "the field"


@dataclass(frozen=True)
class StepField:
    """One per-step field of an unsteady run: the step and the field it holds."""

    step: float
    field: Field


@dataclass(frozen=True)
class FieldWrite:
    """What :func:`write_freestream` wrote, or would write in a preview.

    Attributes
    ----------
    target : Path
        ``inputs/freestreams/<stem>.txt`` or ``.dat``.
    sidecar : Path
        ``inputs/freestreams/<stem>.provenance.json``.
    field : Field
        The field written.
    provenance : dict
        The record written into the sidecar.
    applied : bool
        True when the files were written, False for a preview.
    overwritten : tuple of Path
        The files that existed and were replaced (``overwrite=True``).
    """

    target: Path
    sidecar: Path
    field: Field
    provenance: dict[str, object]
    applied: bool
    overwritten: tuple[Path, ...] = ()


@dataclass(frozen=True)
class FluctuationReport:
    """The fluctuation of per-step fields at each probe over a run's last steps.

    Attributes
    ----------
    rows : tuple of tuple of float
        One ``(x, y, z, std_vx, std_vy, std_vz, std_mag)`` per probe, in the
        first step's order: the POPULATION standard deviation (divided by the
        number of steps) of each component about its time mean, and
        ``std_mag = sqrt(std_vx^2 + std_vy^2 + std_vz^2)``. Metres and m/s.
    steps : tuple of float
        The steps the statistics span, in order.
    sources : tuple of str
        The files read, in step order.
    """

    rows: tuple[tuple[float, float, float, float, float, float, float], ...]
    steps: tuple[float, ...]
    sources: tuple[str, ...]


@dataclass(frozen=True)
class FluctuationWrite:
    """What :func:`write_fluctuation` wrote, or would write in a preview."""

    target: Path
    sidecar: Path
    provenance: dict[str, object]
    applied: bool
    overwritten: tuple[Path, ...] = ()


def read_field(path: str | Path) -> Field:
    """Read a field file; its extension states its form, as the matrix binding reads it.

    ``.txt`` is STRUCTURED and ``.dat`` UNSTRUCTURED (a post's
    ``*.inflow.dat`` is therefore UNSTRUCTURED). Every row is six finite
    numbers, and a STRUCTURED file opens with two positive counts whose
    product is its number of rows.

    Raises
    ------
    WorkspaceError
        If the extension names no form, the file cannot be read, or its
        rows are not the form's.
    """
    path = Path(path)
    form = FREESTREAM_FORMS.get(path.suffix.lower())
    if form is None:
        raise WorkspaceError(
            f"{path}: a field file's extension states its form, .txt STRUCTURED or .dat "
            f"UNSTRUCTURED; {path.suffix or 'no extension'} states neither."
        )
    try:
        header, rows = read_field_rows(path, form=form)
    except (OSError, UnicodeError, CampaignConfigError) as error:
        raise WorkspaceError(f"{path}: {error}") from error
    field = Field(
        form=form,
        rows=tuple((r[0], r[1], r[2], r[3], r[4], r[5]) for r in rows),
        header=header,
        source=str(path),
    )
    _refuse_a_wrong_count(field)
    return field


def _refuse_a_wrong_count(field: Field) -> None:
    if field.form != "STRUCTURED":
        return
    counts = (field.header or "").split()
    if len(counts) != 2 or not all(c.isdigit() and int(c) > 0 for c in counts):
        raise WorkspaceError(
            f"{field.name}: the STRUCTURED header {field.header!r} is not 'Npts Mpts', two "
            "positive integers."
        )
    expected = int(counts[0]) * int(counts[1])
    if expected != len(field.rows):
        raise WorkspaceError(
            f"{field.name}: 'Npts Mpts' = {field.header} asks for {expected} rows and the "
            f"field holds {len(field.rows)}."
        )


def _flip(value: float) -> float:
    # 0.0 - v, never -v: a zero stays 0 and is not written "-0".
    return 0.0 - value


def mirror_field(field: Field, *, plane: str) -> Field:
    """Mirror a field through the coordinate plane ``<plane> = 0``.

    The coordinate normal to the plane and the velocity component along it
    change sign; the other four columns and the row order are kept (a
    STRUCTURED grid keeps its header and its neighbours).

    Parameters
    ----------
    field : Field
        The field to mirror.
    plane : str
        ``"x"``, ``"y"`` or ``"z"``: the plane ``x = 0``, ``y = 0`` or
        ``z = 0``.

    Raises
    ------
    WorkspaceError
        If ``plane`` names none of the three.
    """
    axis = MIRROR_PLANES.get(plane.strip().lower())
    if axis is None:
        raise WorkspaceError(
            f"mirror plane {plane!r}: name the coordinate whose sign changes, x, y or z "
            "(the plane x = 0, y = 0 or z = 0)."
        )
    rows = tuple(_mirrored(row, axis) for row in field.rows)
    return Field(field.form, rows, field.header, field.source)


def _mirrored(row: Row, axis: int) -> Row:
    values = list(row)
    values[axis] = _flip(values[axis])
    values[axis + 3] = _flip(values[axis + 3])
    return (values[0], values[1], values[2], values[3], values[4], values[5])


def move_field(
    field: Field,
    *,
    source_point_m: Sequence[float],
    target_point_m: Sequence[float],
) -> Field:
    """Translate a field so its source point lands on the target point.

    Every position ``p`` becomes ``(p - source) + target``, so the source
    point itself lands on the target exactly; the velocities are unchanged,
    since a translation turns no vector. Both points are keyword-only, so
    the two cannot be swapped by position.

    Raises
    ------
    WorkspaceError
        If either point is not three finite numbers.
    """
    source = _point(source_point_m, "source point")
    target = _point(target_point_m, "target point")
    rows = tuple(
        (
            (row[0] - source[0]) + target[0],
            (row[1] - source[1]) + target[1],
            (row[2] - source[2]) + target[2],
            row[3],
            row[4],
            row[5],
        )
        for row in field.rows
    )
    return Field(field.form, rows, field.header, field.source)


def _point(values: Sequence[float], what: str) -> tuple[float, float, float]:
    numbers = [float(v) for v in values]
    if len(numbers) != 3 or not all(math.isfinite(v) for v in numbers):
        raise WorkspaceError(f"the {what} is three finite numbers, x y z; got {list(values)!r}.")
    return numbers[0], numbers[1], numbers[2]


def _cell(row: Sequence[float], tolerance_m: float) -> tuple[int, int, int]:
    return (
        round(row[0] / tolerance_m),
        round(row[1] / tolerance_m),
        round(row[2] / tolerance_m),
    )


def _same_position(a: Sequence[float], b: Sequence[float], tolerance_m: float) -> bool:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]), abs(a[2] - b[2])) <= tolerance_m


def _position_index(field: Field, tolerance_m: float) -> dict[tuple[int, int, int], list[int]]:
    """Bucket a field's rows by position, refusing two rows at one point."""
    index: dict[tuple[int, int, int], list[int]] = {}
    for number, row in enumerate(field.rows):
        cell = _cell(row, tolerance_m)
        for other in _near(index, cell):
            if _same_position(field.rows[other], row, tolerance_m):
                raise WorkspaceError(
                    f"{field.name}: rows {other + 1} and {number + 1} are one point "
                    f"({row[0]:.17g}, {row[1]:.17g}, {row[2]:.17g}) within {tolerance_m:g} m; "
                    "a field holds each point once."
                )
        index.setdefault(cell, []).append(number)
    return index


def _near(index: Mapping[tuple[int, int, int], list[int]], cell: tuple[int, int, int]) -> list[int]:
    found: list[int] = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                found.extend(index.get((cell[0] + dx, cell[1] + dy, cell[2] + dz), ()))
    return found


def _tolerance(tolerance_m: float) -> float:
    if not (math.isfinite(tolerance_m) and tolerance_m > 0):
        raise WorkspaceError(
            f"the position tolerance is a positive length in m; got {tolerance_m}."
        )
    return float(tolerance_m)


def subtract_fields(
    total: Field,
    other: Field,
    *,
    reference_m_s: Sequence[float],
    tolerance_m: float = POSITION_TOLERANCE_M,
) -> Field:
    """Subtract one field from another point by point: ``total - (other - reference)``.

    The two fields must be ONE GRID: the same number of points, each point
    of ``total`` at one point of ``other`` within ``tolerance_m`` along each
    axis, and the reverse. They are matched by position, not by row order,
    so a grid mirrored or moved onto the other's points is matched. The
    result keeps ``total``'s positions, order, form and header.

    ``reference_m_s`` is a uniform velocity, the free stream ``other`` was
    solved in: ``other - reference`` is then the velocity ``other``'s body
    induces, and the result is ``total`` with that induced velocity removed.
    It has no default: a reference left out would silently remove the free
    stream itself. State ``(0, 0, 0)`` where ``other`` is already
    induced-only (a field with its free stream taken out), and the result is
    the plain difference ``total - other``.

    Raises
    ------
    WorkspaceError
        If the grids differ (a different number of points, or a point of
        either with no point of the other), naming both fields and the
        first point that has no partner; if a field holds one point twice;
        or if the reference is not three finite numbers.
    """
    tolerance = _tolerance(tolerance_m)
    reference = _point(reference_m_s, "reference velocity")
    if len(total.rows) != len(other.rows):
        raise WorkspaceError(
            f"the grids differ: {total.name} holds {len(total.rows)} points and {other.name} "
            f"holds {len(other.rows)}. A field is subtracted point by point on one grid."
        )
    index = _position_index(other, tolerance)
    _position_index(total, tolerance)
    used: set[int] = set()
    rows: list[Row] = []
    for number, row in enumerate(total.rows, start=1):
        partner = next(
            (
                candidate
                for candidate in _near(index, _cell(row, tolerance))
                if _same_position(other.rows[candidate], row, tolerance)
            ),
            None,
        )
        if partner is None:
            raise WorkspaceError(
                f"the grids differ: point {number} of {total.name}, ({row[0]:.17g}, "
                f"{row[1]:.17g}, {row[2]:.17g}) m, is no point of {other.name} within "
                f"{tolerance:g} m. A field is subtracted point by point on one grid; mirror "
                "or move one of them onto the other's points first."
            )
        used.add(partner)
        v = other.rows[partner]
        rows.append(
            (
                row[0],
                row[1],
                row[2],
                row[3] - (v[3] - reference[0]),
                row[4] - (v[4] - reference[1]),
                row[5] - (v[5] - reference[2]),
            )
        )
    # Equal counts, each total point matched and no field holding a point
    # twice: every point of `other` is used exactly once.
    assert len(used) == len(other.rows)
    return Field(total.form, tuple(rows), total.header, total.source)


def step_of(path: str | Path) -> float | None:
    """Return the step a per-step field file names, ``..._step_<N>.inflow.dat``, or None."""
    match = _STEP_IN_NAME.search(Path(path).name)
    if match is None:
        return None
    try:
        step = float(match.group(1))
    except ValueError:
        return None
    return step if math.isfinite(step) else None


def read_step_fields(paths: Sequence[str | Path], *, last: int | None = None) -> list[StepField]:
    """Read per-step field files, ordered by the step each names, keeping the ``last`` ones.

    Raises
    ------
    WorkspaceError
        If no file is given, a file names no step, two files name one step,
        or fewer steps are on disk than ``last`` asks for.
    """
    if not paths:
        raise WorkspaceError("a time mean needs the per-step field files; none was given.")
    stamped: dict[float, Path] = {}
    for raw in paths:
        path = Path(raw)
        step = step_of(path)
        if step is None:
            raise WorkspaceError(
                f"{path}: the name states no step. A time mean reads the per-step fields "
                "of an unsteady run, <point>_field_NN_step_<N>.inflow.dat, and the step is "
                "read from the name."
            )
        if step in stamped:
            raise WorkspaceError(f"{stamped[step]} and {path} both name step {step:g}.")
        stamped[step] = path
    steps = sorted(stamped)
    if last is not None:
        if last < 1:
            raise WorkspaceError(f"last (CLI: --last) is a positive number of steps; got {last}.")
        if len(steps) < last:
            raise WorkspaceError(
                f"{len(steps)} steps were given ({steps[0]:g} to {steps[-1]:g}), fewer than the "
                f"last {last} asked for."
            )
        steps = steps[-last:]
    return [StepField(step, read_field(stamped[step])) for step in steps]


def time_mean_fields(
    fields: Sequence[StepField], *, tolerance_m: float = POSITION_TOLERANCE_M
) -> Field:
    """Average per-step fields of one unsteady run into one field.

    Every step must hold the same points in the same order (one survey of
    one run), and the steps must be equally spaced, so the arithmetic mean
    of the samples is the time mean over their span. The result keeps the
    earliest step's positions, form and header.

    Raises
    ------
    WorkspaceError
        If no step is given, two steps coincide, the spacing is not uniform
        (naming the steps), or a step's points differ from the first step's
        (naming the file and the row).
    """
    tolerance = _tolerance(tolerance_m)
    if not fields:
        raise WorkspaceError("a time mean needs at least one per-step field.")
    ordered = sorted(fields, key=lambda each: each.step)
    steps = [each.step for each in ordered]
    if len(set(steps)) != len(steps):
        raise WorkspaceError(f"the steps {steps} name one step twice.")
    gaps = [b - a for a, b in zip(steps, steps[1:], strict=False)]
    if gaps and any(abs(g - gaps[0]) > 1e-9 * max(1.0, abs(gaps[0])) for g in gaps):
        raise WorkspaceError(
            f"the steps {', '.join(f'{s:g}' for s in steps)} are not equally spaced; the mean "
            "of samples at unequal intervals is not the time mean over their span. Give "
            "every step of the span, or keep the last steps of an evenly exported run with "
            "last (CLI: --last)."
        )
    first = ordered[0].field
    for each in ordered[1:]:
        field = each.field
        if field.form != first.form or field.header != first.header:
            raise WorkspaceError(
                f"{field.name} (step {each.step:g}) is {field.form} {field.header or ''} where "
                f"{first.name} is {first.form} {first.header or ''}; one survey has one form."
            )
        if len(field.rows) != len(first.rows):
            raise WorkspaceError(
                f"{field.name} (step {each.step:g}) holds {len(field.rows)} points and "
                f"{first.name} holds {len(first.rows)}; every step of a time mean holds the "
                "same survey."
            )
        for number, (a, b) in enumerate(zip(first.rows, field.rows, strict=True), start=1):
            if not _same_position(a, b, tolerance):
                raise WorkspaceError(
                    f"{field.name} (step {each.step:g}), row {number}: the point ({b[0]:.17g}, "
                    f"{b[1]:.17g}, {b[2]:.17g}) is not row {number} of {first.name} "
                    f"({a[0]:.17g}, {a[1]:.17g}, {a[2]:.17g}) within {tolerance:g} m; every "
                    "step of a time mean holds the same survey."
                )
    count = len(ordered)
    rows = tuple(
        (
            row[0],
            row[1],
            row[2],
            math.fsum(each.field.rows[i][3] for each in ordered) / count,
            math.fsum(each.field.rows[i][4] for each in ordered) / count,
            math.fsum(each.field.rows[i][5] for each in ordered) / count,
        )
        for i, row in enumerate(first.rows)
    )
    return Field(first.form, rows, first.header, first.source)


def fluctuation_report(
    fields: Sequence[StepField], *, tolerance_m: float = POSITION_TOLERANCE_M
) -> FluctuationReport:
    """Return the per-probe fluctuation of per-step fields (0.32.0, P0320-INFLOW-FLUCTUATION).

    The steps must be consecutive integers (an evenly exported run's last
    ``K`` steps) and hold the same probes as the first step within
    ``tolerance_m``, the survey rule of :func:`time_mean_fields`. Each
    probe's time mean and population standard deviation are taken per
    component; the magnitude combines the three.

    Raises
    ------
    WorkspaceError
        If fewer than two steps are given (a steady field has no
        fluctuation), the steps are not consecutive integers, or a step's
        probes differ from the first step's (naming file and row).

    Examples
    --------
    >>> steps = [
    ...     StepField(1.0, Field("UNSTRUCTURED", ((0.0, 0.0, 0.0, 1.0, 0.0, 0.0),))),
    ...     StepField(2.0, Field("UNSTRUCTURED", ((0.0, 0.0, 0.0, 3.0, 0.0, 0.0),))),
    ... ]
    >>> fluctuation_report(steps).rows[0][3:]
    (1.0, 0.0, 0.0, 1.0)
    """
    if len(fields) < 2:
        raise WorkspaceError(
            "a steady field has no fluctuation: the report needs at least two per-step fields "
            "(give the last K steps of an unsteady run with last, CLI: --last)."
        )
    ordered = sorted(fields, key=lambda each: each.step)
    steps = [each.step for each in ordered]
    if any(s != int(s) for s in steps) or any(
        b - a != 1 for a, b in zip(steps, steps[1:], strict=False)
    ):
        raise WorkspaceError(
            f"the steps {', '.join(f'{s:g}' for s in steps)} are not consecutive integers; the "
            "fluctuation is reported over every step of a span, so give consecutive steps."
        )
    # The one survey rule (same probes, same form) is the time mean's, and it refuses first.
    time_mean_fields(ordered, tolerance_m=tolerance_m)
    count = len(ordered)
    rows = []
    for i, first in enumerate(ordered[0].field.rows):
        stds = []
        for component in (3, 4, 5):
            samples = [each.field.rows[i][component] for each in ordered]
            mean = math.fsum(samples) / count
            stds.append(math.sqrt(math.fsum((v - mean) ** 2 for v in samples) / count))
        magnitude = math.sqrt(math.fsum(v * v for v in stds))
        rows.append((first[0], first[1], first[2], stds[0], stds[1], stds[2], magnitude))
    return FluctuationReport(
        rows=tuple(rows),
        steps=tuple(steps),
        sources=tuple(each.field.name for each in ordered),
    )


def render_fluctuation(report: FluctuationReport) -> str:
    """Return the text of ``<stem>.fluctuation.csv``: ``x,y,z,std_vx,...,std_mag``, ``%.9g``."""
    lines = ["x,y,z,std_vx,std_vy,std_vz,std_mag"]
    lines.extend(",".join(format(v, ".9g") for v in row) for row in report.rows)
    return "\n".join(lines) + "\n"


def fluctuation_extent(report: FluctuationReport) -> tuple[float, float]:
    """Return the largest ``std_mag`` over the probes and its root mean square, in m/s."""
    magnitudes = [row[6] for row in report.rows]
    return max(magnitudes), math.sqrt(math.fsum(m * m for m in magnitudes) / len(magnitudes))


def fill_interior(field: Field, *, r_body_m: float = DEFAULT_R_BODY_M) -> tuple[Field, int]:
    """Fill the probes inside the body from the ray outside it (0.32.0, P0320-FILL-INTERIOR).

    Every probe with ``r < r_body_m`` (``r`` the distance from the x axis,
    ``hypot(y, z)``) takes the velocity of the probe at ``r >= r_body_m`` with
    the smallest radius on the same azimuth ray (``atan2(z, y)`` within
    :data:`FILL_AZIMUTH_TOLERANCE_RAD`). Positions never change. A probe on
    the axis itself has azimuth 0 by ``atan2``.

    Returns
    -------
    (Field, int)
        The filled field and the number of probes replaced.

    Raises
    ------
    WorkspaceError
        If ``r_body_m`` is not a positive finite radius, or an interior probe
        has no probe at ``r >= r_body_m`` on its ray (nothing is guessed).

    Examples
    --------
    >>> pair = ((0.0, 0.1, 0.0, 1.0, 0.0, 0.0), (0.0, 0.5, 0.0, 9.0, 0.0, 0.0))
    >>> filled, count = fill_interior(Field("UNSTRUCTURED", pair), r_body_m=0.38)
    >>> count, filled.rows[0][3]
    (1, 9.0)
    """
    if not math.isfinite(r_body_m) or r_body_m <= 0.0:
        raise WorkspaceError(
            f"r_body (CLI: --r-body) is a positive radius in metres about the x axis; "
            f"got {r_body_m!r}."
        )
    polar = [(math.hypot(row[1], row[2]), math.atan2(row[2], row[1])) for row in field.rows]
    outside = sorted(
        (i for i, (r, _azimuth) in enumerate(polar) if r >= r_body_m), key=lambda i: polar[i][0]
    )
    rows = list(field.rows)
    count = 0
    for i, (r, azimuth) in enumerate(polar):
        if r >= r_body_m:
            continue
        for j in outside:
            gap = abs(azimuth - polar[j][1])
            if min(gap, 2.0 * math.pi - gap) <= FILL_AZIMUTH_TOLERANCE_RAD:
                row = field.rows[i]
                rows[i] = (row[0], row[1], row[2], *field.rows[j][3:6])
                count += 1
                break
        else:
            raise WorkspaceError(
                f"{field.name}, row {i + 1}: the probe at r = {r:.6g} m, azimuth {azimuth:.6g} "
                f"rad has no point at r >= {r_body_m:g} m within "
                f"{FILL_AZIMUTH_TOLERANCE_RAD:g} rad of its azimuth to take a value from."
            )
    return Field(field.form, tuple(rows), field.header, field.source), count


def render_field(field: Field) -> str:
    """Return the file text of a field: the header of a STRUCTURED one, then its rows."""
    lines = [] if field.header is None else [field.header]
    lines.extend(" ".join(format(value, ".17g") for value in row) for row in field.rows)
    return "\n".join(lines) + "\n"


def _refuse_what_the_reader_refuses(field: Field) -> None:
    """Refuse a result the custom free-stream reader of the builder would refuse.

    The same sentences of the manual: every row states one x (the field
    varies within the YZ plane of the global frame), at least two distinct y
    and two distinct z, and a STRUCTURED file holds Npts x Mpts rows.
    """
    if field.form not in FREESTREAM_FORMS.values():
        raise WorkspaceError(f"{field.name}: {field.form!r} is not a form of the manual.")
    if not field.rows:
        raise WorkspaceError(f"{field.name}: the result holds no point.")
    _refuse_a_wrong_count(field)
    xs = {row[0] for row in field.rows}
    if len(xs) != 1:
        raise WorkspaceError(
            f"the result states {len(xs)} values of x ({min(xs):.17g} to {max(xs):.17g}); a "
            "custom free stream varies within ONE YZ plane of the global frame, so every row "
            "states the one x of that plane."
        )
    for axis, column in (("y", 1), ("z", 2)):
        if len({row[column] for row in field.rows}) < 2:
            raise WorkspaceError(
                f"the result states one {axis}; a custom free stream states at least two "
                "distinct y and two distinct z."
            )


def _check_stem(stem: str) -> str:
    text = stem.strip()
    if (
        not text
        or text != stem
        or any(ch in text for ch in '/\\:*?"<>|')
        or text.startswith(".")
        or Path(text).suffix.lower() in FREESTREAM_FORMS
    ):
        raise WorkspaceError(
            f"output stem {stem!r}: name the field by its stem, a plain file name with no "
            "folder and no extension (the form gives the extension, .txt STRUCTURED or .dat "
            "UNSTRUCTURED), as a row's FREESTREAM names it."
        )
    return text


def write_freestream(
    root: str | Path,
    stem: str,
    field: Field,
    *,
    operation: str,
    parameters: Mapping[str, object],
    inputs: Sequence[str | Path],
    apply: bool = False,
    overwrite: bool = False,
    sidecars: Mapping[str, str] | None = None,
) -> FieldWrite:
    """Write a field into ``<root>/inputs/freestreams/`` with its provenance, or preview it.

    The file is ``<stem>.txt`` for a STRUCTURED field and ``<stem>.dat``
    for an UNSTRUCTURED one; the record ``<stem>.provenance.json`` names the
    operation, its parameters, every input file with its sha256, and the
    written file's own sha256. Without ``apply`` nothing is written and the
    same refusals fire, so a preview says what ``apply`` would do.

    ``sidecars`` maps a suffix (``".fluctuation.csv"``) to the text of a file
    written beside the field as ``<stem><suffix>`` (0.32.0): each is subject
    to the same overwrite rule and is named in the record, with its sha256,
    under ``"sidecars"``.

    Raises
    ------
    WorkspaceError
        If the stem is not a plain name; if the field is not one the
        free-stream reader accepts; if the folder already holds the stem in
        the other form (one stem names one file); or if the file or its
        record exists and ``overwrite`` is not set.
    """
    name = _check_stem(stem)
    _refuse_what_the_reader_refuses(field)
    folder = Path(root) / "inputs" / FREESTREAM_DIR
    suffix = next(s for s, form in FREESTREAM_FORMS.items() if form == field.form)
    target = folder / f"{name}{suffix}"
    sidecar = folder / f"{name}.provenance.json"
    others = [
        folder / f"{name}{s}"
        for s in FREESTREAM_FORMS
        if s != suffix and (folder / f"{name}{s}").exists()
    ]
    if others:
        raise WorkspaceError(
            f"{others[0]} exists: the stem {name!r} would name two files, and the extension "
            "states the form, so one stem names one file. Choose another stem, or remove it."
        )
    extras = {folder / f"{name}{suffix_}": text for suffix_, text in (sidecars or {}).items()}
    existing = tuple(path for path in (target, sidecar, *extras) if path.exists())
    if existing and not overwrite:
        raise WorkspaceError(
            f"{', '.join(str(p) for p in existing)} exists; nothing is overwritten unless "
            "overwrite (CLI: --overwrite) is set."
        )
    text = render_field(field)
    provenance: dict[str, object] = {
        "schema": FIELD_PROVENANCE_SCHEMA,
        "operation": operation,
        "parameters": dict(parameters),
        "inputs": [{"path": str(Path(p)), "sha256": file_sha256(Path(p))} for p in inputs],
        "output": {
            "file": f"inputs/{FREESTREAM_DIR}/{target.name}",
            "form": field.form,
            "points": len(field.rows),
            "sha256": text_sha256(text),
        },
        "units": {"coordinates": "m", "velocity": "m/s", "frame": "global", "converted": False},
    }
    if extras:
        provenance["sidecars"] = [
            {"file": f"inputs/{FREESTREAM_DIR}/{path.name}", "sha256": text_sha256(extra)}
            for path, extra in extras.items()
        ]
    if apply:
        folder.mkdir(parents=True, exist_ok=True)
        # Bytes, not text: the record's sha256 is of these exact bytes, and a
        # text write would turn each newline into the platform's.
        target.write_bytes(text.encode("utf-8"))
        for path, extra in extras.items():
            path.write_bytes(extra.encode("utf-8"))
        sidecar.write_bytes((json.dumps(provenance, indent=2) + "\n").encode("utf-8"))
    return FieldWrite(target, sidecar, field, provenance, apply, existing if apply else ())


def write_fluctuation(
    root: str | Path,
    stem: str,
    report: FluctuationReport,
    *,
    parameters: Mapping[str, object],
    inputs: Sequence[str | Path],
    apply: bool = False,
    overwrite: bool = False,
) -> FluctuationWrite:
    """Write only the fluctuation report of a run's last steps, with its provenance, or preview it.

    The files are ``<root>/inputs/freestreams/<stem>.fluctuation.csv`` and
    ``<stem>.fluctuation.provenance.json`` (no field is written, so the stem
    names no free stream). The overwrite rule is :func:`write_freestream`'s.

    Raises
    ------
    WorkspaceError
        If the stem is not a plain name, or a target exists and ``overwrite``
        is not set.
    """
    name = _check_stem(stem)
    folder = Path(root) / "inputs" / FREESTREAM_DIR
    target = folder / f"{name}.fluctuation.csv"
    sidecar = folder / f"{name}.fluctuation.provenance.json"
    existing = tuple(path for path in (target, sidecar) if path.exists())
    if existing and not overwrite:
        raise WorkspaceError(
            f"{', '.join(str(p) for p in existing)} exists; nothing is overwritten unless "
            "overwrite (CLI: --overwrite) is set."
        )
    text = render_fluctuation(report)
    provenance: dict[str, object] = {
        "schema": FIELD_PROVENANCE_SCHEMA,
        "operation": "fluctuation",
        "parameters": dict(parameters),
        "inputs": [{"path": str(Path(p)), "sha256": file_sha256(Path(p))} for p in inputs],
        "output": {
            "file": f"inputs/{FREESTREAM_DIR}/{target.name}",
            "form": "CSV",
            "points": len(report.rows),
            "sha256": text_sha256(text),
        },
        "units": {"coordinates": "m", "velocity": "m/s", "frame": "global", "converted": False},
    }
    if apply:
        folder.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8"))
        sidecar.write_bytes((json.dumps(provenance, indent=2) + "\n").encode("utf-8"))
    return FluctuationWrite(target, sidecar, provenance, apply, existing if apply else ())
