"""Per-timestep field frames, read back as an ordered series.

Pipeline role: the entry point of unsteady post-processing. An unsteady
run asked to animate (``UNSTEADY_SOLVER_ANIMATION``, FSM-26.120 pp.347-348)
writes one file every so many solver time steps into a folder, and this
module reads that folder back as a series a reduction can be taken over.
The reduction itself is pure and lives here too
(:func:`blade_passage_average`); WRITING one is
:mod:`pyflightstream.post.reductions`, deliberately a different module,
because the file rule that reduction writing has to obey is a rule about
destinations and this module has none.

ORDER COMES FROM EVIDENCE, NEVER FROM A FILE NAME. Nothing in this
repository records how the solver names its animation frames: the
command is ``documented`` on every registered build and probed on none
(``reports/compat/CMP-26120_2026-08-09_identity.md``). Sorting the names
would therefore be this library inventing a vendor convention, and an
animation read in the wrong order yields a plausible average of the
wrong thing, which is the failure nobody notices. So the reader takes
the order from one of exactly two places, and REFUSES when it has
neither:

* the caller declares that the sequence handed over is already in solver
  order (``order="given"``), which is a fact the caller has and this
  module does not;
* each frame carries its own solution time in its header, which the
  Tecplot ASCII zone record can (``SOLUTIONTIME=``), so the frames sort
  themselves.

The refusal names what would settle it: one licensed run of the export
and a committed probe report recording how the frames are named.

FREQUENCY IS COUNTED IN SOLVER STEPS, which is what the command's
``frequency`` keyword means, so the step axis of a series read in a
declared order is frame index times frequency. It is not read out of the
file and is not guessed: a caller that passes the frequency it asked the
solver for gets solver steps, and one that does not gets frame indices,
which the series says of itself.

THE TWO FRAME FORMATS are the two the command's own entry lists as data
filetypes, ``TECPLOT_DATA`` and ``PARAVIEW_VTK``. They are read here in
the shapes :mod:`pyflightstream.post.writers` writes, which is the only
form of either this repository has evidence for.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from pyflightstream._errors import ProductError
from pyflightstream.cases import FORCE_PLOT_PARAMETERS
from pyflightstream.post.axes import blade_azimuth_deg
from pyflightstream.results import IncompleteOutputError, MalformedOutputError

__all__ = [
    "FrameAverage",
    "TimestepSeries",
    "blade_passage_average",
    "blade_one_azimuth",
    "passage_windows",
    "per_blade_rows",
    "phase_locked_rows",
    "read_timestep_series",
    "revolution_drift_warnings",
]

#: What the refusal tells a reader who has frames and no order.
_NO_ORDER = (
    "no frame carries a solution time in its own header, so the order of this "
    "series cannot be established. Nothing in this repository records how the "
    "solver names its animation frames, and sorting the names would invent a "
    "vendor convention: an animation read in the wrong order gives a plausible "
    "average of the wrong thing. Pass order='given' if the sequence you handed "
    "over is already in solver order, which is a fact you have and this reader "
    "does not. Settling the naming itself needs one licensed run of "
    "UNSTEADY_SOLVER_ANIMATION and a committed probe report under reports/."
)


@dataclass(frozen=True)
class TimestepSeries:
    """One field, at every exported time step of one unsteady run.

    Attributes
    ----------
    steps : numpy.ndarray
        Solver step index of each frame, shape ``(n_frames,)``,
        dimensionless. Frame index times the ``frequency`` the caller
        passed, because the export's frequency is counted in solver
        steps.
    times_s : numpy.ndarray or None
        Solution time of each frame in seconds, when the frames carried
        one; None when the order came from the caller instead.
    points : numpy.ndarray
        Sample positions, shape ``(n_points, 3)``, in the reference
        frame of the export and in simulation length units. Taken from
        the first frame. The reader checks that every later frame holds
        the same NUMBER of samples and that sample k sits at the same
        coordinate, within ``_POINT_RTOL`` of the extent of the first
        frame, so a reduction over the series averages one place over
        time. A frame that moves its points is refused, not averaged.
    fields : dict of str to numpy.ndarray
        One entry per exported quantity, shape ``(n_frames, n_points)``
        for a scalar and ``(n_frames, n_points, 3)`` for a vector. Units
        are whatever the solver exported; nothing here rescales.
    sources : tuple of pathlib.Path
        The frame files, in the order they were read. Carried so a
        reduction taken from this series can be refused a destination
        equal to one of them.
    order_evidence : str
        How the order was established: ``given`` (the caller declared
        it) or ``solution time`` (each frame's own header). There is no
        third value, and in particular no value meaning "the file
        names looked sorted".
    """

    steps: np.ndarray
    times_s: np.ndarray | None
    points: np.ndarray
    fields: dict[str, np.ndarray]
    sources: tuple[Path, ...]
    order_evidence: str = field(default="given")

    @property
    def n_frames(self) -> int:
        """Number of exported frames in the series."""
        return int(len(self.steps))


@dataclass(frozen=True)
class FrameAverage:
    """A reduction of a :class:`TimestepSeries` over one window.

    Attributes
    ----------
    window : tuple of int
        Inclusive ``(first_step, last_step)`` in solver steps, as
        declared by the caller. Recorded so the written file can say
        what was averaged.
    n_frames : int
        How many frames fell inside the window and were averaged. A
        window holding none is refused rather than averaged, so this is
        never zero.
    points : numpy.ndarray
        Sample positions, shape ``(n_points, 3)``, unchanged from the
        series.
    fields : dict of str to numpy.ndarray
        Per-sample mean of each quantity over the window, shape
        ``(n_points,)`` for a scalar and ``(n_points, 3)`` for a vector,
        in the series' own units.
    sources : tuple of pathlib.Path
        The frame files behind the series, carried through so the
        writing seam can refuse to overwrite one of them.
    source_window : tuple of int or None
        First and last source steps actually averaged, which can lie inside
        the declared window when exports are sparse. None for manually
        constructed averages without that evidence.
    """

    window: tuple[int, int]
    n_frames: int
    points: np.ndarray
    fields: dict[str, np.ndarray]
    sources: tuple[Path, ...]
    source_window: tuple[int, int] | None = None


#: Tecplot records that carry text, not data: the title and auxiliary
#: name-value pairs (the package's own surface writer emits
#: DATASETAUXDATA). A line opening with one of them is not a row.
_TECPLOT_TEXT_RECORDS = ("TITLE", "DATASETAUXDATA", "AUXDATA")


def _zone_keywords(upper: str) -> tuple[int | None, float | None]:
    """Return the declared point count and the solution time a ZONE record states."""
    declared = re.search(r"(?<![A-Z])I\s*=\s*(\d+)", upper)
    declared_points = int(declared.group(1)) if declared is not None else None
    stated = re.search(r"SOLUTIONTIME\s*=\s*\"?([^\s,\"]*)", upper)
    if stated is None:
        return declared_points, None
    token = stated.group(1)
    try:
        value = float(token)
    except ValueError as error:
        raise MalformedOutputError(
            f"the zone record declares SOLUTIONTIME={token!r}, which is not a "
            "number, so the frame cannot say when it was written"
        ) from error
    if not math.isfinite(value):
        raise MalformedOutputError(
            f"the zone record declares SOLUTIONTIME={token!r}, which is not a finite "
            "number, so the frame cannot say when it was written and would be ordered "
            "by a value that compares with nothing"
        )
    return declared_points, value


def _read_tecplot_frame(text: str) -> tuple[np.ndarray, dict[str, np.ndarray], float | None]:
    """Read one Tecplot ASCII ordered POINT zone."""
    names: list[str] = []
    solution_time: float | None = None
    declared_points: int | None = None
    zones = 0
    rows: list[list[float]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        upper = stripped.upper()
        if upper.startswith(_TECPLOT_TEXT_RECORDS):
            continue
        if upper.startswith("VARIABLES"):
            names = [token for token in stripped.split('"')[1::2]]
            continue
        if upper.startswith("ZONE"):
            # One frame is one zone. A second zone's rows were concatenated
            # onto the first's while its I= replaced the first's, so a
            # complete multi-zone file was refused as truncated.
            zones += 1
            if zones > 1:
                raise MalformedOutputError(
                    "the frame carries a second ZONE record. A frame of this series is "
                    "one ordered zone, and reading several as one would concatenate "
                    "their rows into samples of a frame that does not exist"
                )
            # The keywords are separated by commas or whitespace (the
            # package's own probe writer uses commas), so a value ends at
            # either: read up to the next space alone it kept its comma.
            # The declared point count lets a truncated table be refused
            # rather than returned short; anchored so the I of a longer
            # keyword cannot match.
            declared_points, stated_time = _zone_keywords(upper)
            if stated_time is not None:
                solution_time = stated_time
            continue
        try:
            rows.append([float(token) for token in re.split(r"[,\s]+", stripped)])
        except ValueError as error:
            raise MalformedOutputError(
                f"the frame line {stripped[:80]!r} is neither a record this reader knows "
                "nor a row of numbers, so it is not a Tecplot ASCII point zone"
            ) from error
    if not names or not rows:
        raise MalformedOutputError(
            "the frame carries no VARIABLES record or no data rows, so it is not a "
            "Tecplot ASCII point zone"
        )
    widths = {len(row) for row in rows}
    if widths != {len(names)}:
        raise MalformedOutputError(
            f"the frame declares {len(names)} variables and its rows hold {sorted(widths)} columns"
        )
    table = np.asarray(rows, dtype=float)
    # Check the zone's declared I count against its actual rows after the
    # loop, when the row count is known. Refuse a truncated frame before
    # a downstream reduction can average an incomplete history.
    if declared_points is not None and len(rows) != declared_points:
        raise IncompleteOutputError(
            f"the zone declares I={declared_points} and the frame carries {len(rows)} "
            "row(s). It is truncated, and a shorter frame read as a whole one makes "
            "every reduction over it an average of a run that did not finish writing"
        )
    points = table[:, :3]
    fields = {name: table[:, index] for index, name in enumerate(names) if index >= 3}
    return points, fields, solution_time


def _vtk_block(lines: Sequence[str], *, width: int, what: str) -> np.ndarray:
    """Read a VTK block of ``width`` numbers per line, refusing a ragged or text line."""
    values: list[list[float]] = []
    for line in lines:
        tokens = line.split()
        try:
            values.append([float(token) for token in tokens])
        except ValueError as error:
            raise MalformedOutputError(
                f"the frame's {what!r} block holds the line {line[:80]!r}, which is not "
                "a row of numbers"
            ) from error
        if len(tokens) != width:
            raise MalformedOutputError(
                f"the frame's {what!r} block holds the line {line[:80]!r} with "
                f"{len(tokens)} value(s) where each line holds {width}"
            )
    return np.asarray(values, dtype=float).reshape(len(values), width)


def _vtk_point_count(record: str) -> int:
    """Return the count a VTK POINTS record states, refusing one that states none."""
    try:
        count = int(record.split()[1])
    except (IndexError, ValueError) as error:
        raise MalformedOutputError(
            f"the frame's POINTS record {record[:80]!r} does not state a count of "
            "points, so its table cannot be read"
        ) from error
    if count < 0:
        raise MalformedOutputError(
            f"the frame's POINTS record {record[:80]!r} states a negative count"
        )
    return count


def _read_vtk_frame(text: str) -> tuple[np.ndarray, dict[str, np.ndarray], float | None]:
    """Read one VTK legacy ASCII polydata frame."""
    lines = [line.strip() for line in text.splitlines()]
    try:
        start = next(i for i, line in enumerate(lines) if line.upper().startswith("POINTS "))
    except StopIteration as error:
        raise MalformedOutputError(
            "the frame carries no POINTS record, so it is not VTK legacy ASCII polydata"
        ) from error
    count = _vtk_point_count(lines[start])
    rows = lines[start + 1 : start + 1 + count]
    # Check the declared count against the actual rows. Refuse an incomplete
    # point or field block instead of returning a short frame for reduction.
    if len(rows) != count:
        raise IncompleteOutputError(
            f"the frame declares POINTS {count} and carries {len(rows)}. It is "
            "truncated, and a shorter frame read as a whole one makes every "
            "reduction over it an average of a run that did not finish writing"
        )
    points = _vtk_block(rows, width=3, what="POINTS")
    fields: dict[str, np.ndarray] = {}
    # The data section a field block belongs to. A SCALARS or VECTORS
    # block holds one value per point only under POINT_DATA with the
    # points' own count; under CELL_DATA it holds one per cell, and its
    # first values were read as point samples with no refusal.
    section: str | None = None
    index = start + 1 + count
    while index < len(lines):
        line = lines[index]
        upper = line.upper()
        if upper.startswith("CELL_DATA"):
            raise MalformedOutputError(
                f"the frame carries a CELL_DATA section ({line!r}). This reader takes "
                "one value per point, and a cell value read as a point sample would "
                "be a field of the wrong locations"
            )
        if upper.startswith("POINT_DATA"):
            declared = line.split()[1] if len(line.split()) > 1 else ""
            if declared != str(count):
                raise MalformedOutputError(
                    f"the frame declares POINTS {count} and {line!r}, so its point "
                    "fields do not hold one value per point"
                )
            section = "POINT_DATA"
            index += 1
            continue
        if upper.startswith(("SCALARS ", "VECTORS ")):
            name = line.split()[1]
            if section is None:
                raise MalformedOutputError(
                    f"the frame's {name!r} block is not preceded by POINT_DATA {count}, "
                    "so nothing says its values are one per point"
                )
            vector = upper.startswith("VECTORS ")
            body = index + (1 if vector else 2)  # a SCALARS block has a LOOKUP_TABLE line
            # Bounds-checked rather than indexed and hoped: an out-of-range
            # read here raised a bare IndexError out of a public function,
            # which `except PyflightstreamError` does not catch and which
            # FR-39's walk does not see, so it was neither catalogued nor
            # on the ratchet.
            if body + count > len(lines):
                raise IncompleteOutputError(
                    f"the frame declares POINTS {count} and its {name!r} block ends "
                    f"after {max(0, len(lines) - body)} value(s). It is truncated "
                    "inside a field block"
                )
            block = _vtk_block(lines[body : body + count], width=3 if vector else 1, what=name)
            fields[name] = block if vector else block[:, 0]
            index = body + count
            continue
        index += 1
    # VTK legacy polydata has no time record: the title line is the
    # caller's own string, so reading a step out of it would be reading
    # something this library wrote rather than something the solver did.
    return points, fields, None


def _read_frame(path: Path) -> tuple[np.ndarray, dict[str, np.ndarray], float | None]:
    """Read one exported frame, in whichever of the two shapes it is."""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise MalformedOutputError(
            f"{path} is not UTF-8 text ({error.reason} at byte {error.start}), so it is "
            "neither of the ASCII frame formats this reader takes"
        ) from error
    head = text.lstrip()[:64].upper()
    if head.startswith("# VTK"):
        return _read_vtk_frame(text)
    if head.startswith("TITLE") or head.startswith("VARIABLES") or head.startswith("ZONE"):
        return _read_tecplot_frame(text)
    raise MalformedOutputError(
        f"{path} opens with neither a VTK legacy header nor a Tecplot record, so it is "
        "neither of the two data filetypes UNSTEADY_SOLVER_ANIMATION writes "
        "(TECPLOT_DATA, PARAVIEW_VTK)"
    )


#: Relative departure of a gap between solution times from the median gap that the
#: reader accepts. The times are printed by the solver with limited digits, so the
#: tolerance is far above the print rounding and far below one missing frame (a
#: factor of two).
_TIME_SPACING_RTOL = 1e-3

#: Largest move of a sample between frames, relative to the larger of the first frame's
#: extent and its largest coordinate. The solver prints coordinates with limited digits,
#: so the tolerance sits well above print rounding and far below any real move.
_POINT_RTOL = 1e-5


def _refuse_irregular_times(times: Sequence[float | None], paths: Sequence[Path]) -> None:
    """Refuse duplicate or unevenly spaced solution times, naming the gap.

    Only when every frame carries a time; a series ordered by declaration alone has
    nothing to compare. The step axis of the series is frame index times frequency,
    so a frame missing from the middle (or one written twice) would move every
    later step by a whole frame while the times said otherwise.
    """
    if len(times) < 2 or any(value is None for value in times):
        return
    values = [float(value) for value in times if value is not None]
    gaps = np.diff(values)
    for index, gap in enumerate(gaps):
        if gap == 0.0:
            raise MalformedOutputError(
                f"{paths[index + 1]} and {paths[index]} both carry solution time "
                f"{values[index]!r}, so one frame is written twice or two runs are mixed"
            )
    median = float(np.median(gaps))
    for index, gap in enumerate(gaps):
        if abs(gap - median) > _TIME_SPACING_RTOL * abs(median):
            raise MalformedOutputError(
                f"the solution times are not uniformly spaced: from {paths[index]} "
                f"(t = {values[index]!r} s) to {paths[index + 1]} (t = {values[index + 1]!r} s) "
                f"the gap is {gap!r} s and the median gap is {median!r} s, so a frame is "
                "missing or repeated and the step axis (frame index times frequency) "
                "would shift every later step"
            )


def _refuse_a_bad_call(order: str | None, frequency: object) -> None:
    """Refuse an ``order`` or a ``frequency`` the reader has no meaning for (ProductError)."""
    if isinstance(frequency, bool) or not isinstance(frequency, (int, np.integer)) or frequency < 1:
        raise ProductError(
            f"frequency={frequency!r} is not a positive integer: it counts the solver "
            "time steps between exported frames (the frequency keyword of "
            "UNSTEADY_SOLVER_ANIMATION), so 1 is the smallest value that means anything"
        )
    if order not in (None, "given"):
        raise ProductError(
            f"order={order!r} is not a way this reader can establish an order. The two "
            "it has are order='given', the caller declaring the sequence is already in "
            "solver order, and the default, each frame's own solution time."
        )


def _refuse_non_finite_points(path: Path, points: np.ndarray) -> None:
    """Refuse a frame whose sample coordinates are not all finite numbers.

    A sample at a coordinate that is NaN or infinite has no place, so a mean over it is a
    mean at a place that does not exist; the frames are compared to the first one's
    coordinates and a NaN compares with nothing.
    """
    if not np.isfinite(points).all():
        worst = int(np.argmax(~np.isfinite(points).all(axis=1)))
        raise MalformedOutputError(
            f"{path} places sample {worst} at {points[worst].tolist()}, which is not a finite "
            "coordinate, so the frame has no place to average at"
        )


def _refuse_moved_points(path: Path, points: np.ndarray, first_points: np.ndarray) -> None:
    """Refuse a frame whose sample k sits elsewhere than in the first frame, naming it.

    The tolerance is :data:`_POINT_RTOL` of the larger of the first frame's extent and its
    largest coordinate. A frame is also refused (by the caller) when its sample count differs.
    """
    extent = float(np.ptp(first_points, axis=0).max()) if first_points.size else 0.0
    tolerance = _POINT_RTOL * max(extent, float(np.abs(first_points).max(initial=0.0)), 1e-12)
    moved = np.abs(points - first_points)
    if moved.size and float(moved.max()) > tolerance:
        worst = int(np.argmax(moved.max(axis=1)))
        raise MalformedOutputError(
            f"{path} places sample {worst} at {points[worst].tolist()} and the first frame "
            f"at {first_points[worst].tolist()}, a move of {float(moved.max())!r} against a "
            f"tolerance of {tolerance!r} (relative {_POINT_RTOL!r} of the first "
            "frame's extent): a series averages one place over time, so these frames "
            "are not one sampling"
        )


def read_timestep_series(
    frames: Sequence[str | Path],
    *,
    order: str | None = None,
    frequency: int = 1,
) -> TimestepSeries:
    """Read exported frames back as one ordered series.

    Parameters
    ----------
    frames : sequence of str or pathlib.Path
        The exported frame files. They may be handed over in any order
        when each carries its own solution time; when they do not, the
        sequence is the order and ``order="given"`` says so.
    order : str, optional
        ``"given"`` to declare that ``frames`` is already in solver
        order. Omitted (the default) means the order is read from each
        frame's own header, and the call is REFUSED when no frame
        carries one. There is deliberately no option that sorts file
        names.
    frequency : int
        Solver time steps between exported frames, the ``frequency``
        keyword the run passed to ``UNSTEADY_SOLVER_ANIMATION``.
        Dimensionless step count, a positive integer (a bool, a float
        or a value below 1 is refused); the step axis is frame index
        times this. Default 1, which yields frame indices.

    Returns
    -------
    TimestepSeries
        The series, with the order evidence recorded on it.

    Raises
    ------
    ProductError
        If ``order`` is not ``"given"`` or None, or ``frequency`` is not
        a positive integer. Both are mistakes of the call and not
        malformed solver output.
    MalformedOutputError
        If no order can be established; if a frame is in neither
        supported shape; if a frame's variables or sample count
        disagree with the first frame's, or a sample sits at another
        coordinate (beyond ``_POINT_RTOL``), because a series is one
        quantity over time at one set of places or it is not a series;
        or if the frames
        carry solution times and two of them are equal or the spacing
        is not uniform within a relative tolerance of
        ``_TIME_SPACING_RTOL``, because the step axis is frame index
        times frequency and a missing or repeated frame would shift
        every later step without a word; or if a solution time or a sample
        coordinate is NaN or infinite, because it has no place in an order or
        in space, or a VTK POINTS record states no count.

    Examples
    --------
    Frames written by this package's own writers, read back in the
    order they were handed over:

    >>> import numpy as np, pathlib, tempfile
    >>> from pyflightstream.post import OutputProvenance, read_timestep_series
    >>> from pyflightstream.post import write_tecplot_points
    >>> from pyflightstream.script import Script, helpers
    >>> setup = helpers.solver_settings(Script(version="26.120"), velocity=30.0)
    >>> record = OutputProvenance(run_id="rotor/sim_1/a+00.0", setup=setup)
    >>> folder = pathlib.Path(tempfile.mkdtemp())
    >>> points = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    >>> written = [
    ...     write_tecplot_points(
    ...         folder / f"frame_{i}.dat", points, {"cp": np.array([v, v])},
    ...         provenance=record,
    ...     )[0]
    ...     for i, v in enumerate([1.0, 2.0, 3.0])
    ... ]
    >>> series = read_timestep_series(written, order="given", frequency=10)
    >>> series.steps.tolist()
    [0, 10, 20]
    >>> series.fields["cp"][:, 0].tolist()
    [1.0, 2.0, 3.0]
    """
    _refuse_a_bad_call(order, frequency)
    paths = [Path(item) for item in frames]
    if not paths:
        raise MalformedOutputError(
            "no frames were given, so there is no series to read; an empty animation "
            "folder means the run exported nothing"
        )
    read = [(path, *_read_frame(path)) for path in paths]

    times = [entry[3] for entry in read]
    if order == "given":
        ordered = read
        evidence = "given"
        times_s = None
    elif all(value is not None for value in times):
        ordered = sorted(read, key=lambda entry: entry[3])  # type: ignore[arg-type,return-value]
        evidence = "solution time"
        times_s = np.asarray([entry[3] for entry in ordered], dtype=float)
    else:
        raise MalformedOutputError(_NO_ORDER)

    _refuse_irregular_times([entry[3] for entry in ordered], [entry[0] for entry in ordered])
    first_points = ordered[0][1]
    names = sorted(ordered[0][2])
    stacked: dict[str, list[np.ndarray]] = {name: [] for name in names}
    for path, points, fields, _time in ordered:
        if sorted(fields) != names:
            raise MalformedOutputError(
                f"{path} exports {sorted(fields)} and the first frame exports {names}, so "
                "these files are not frames of one series"
            )
        if points.shape != first_points.shape:
            raise MalformedOutputError(
                f"{path} holds {len(points)} samples and the first frame holds "
                f"{len(first_points)}, so the frames are not one sampling of one run"
            )
        _refuse_non_finite_points(path, points)
        _refuse_moved_points(path, points, first_points)
        for name in names:
            stacked[name].append(fields[name])

    return TimestepSeries(
        steps=np.arange(len(ordered), dtype=int) * int(frequency),
        times_s=times_s,
        points=first_points,
        fields={name: np.asarray(values) for name, values in stacked.items()},
        sources=tuple(entry[0] for entry in ordered),
        order_evidence=evidence,
    )


def blade_passage_average(
    series: TimestepSeries, *, window: tuple[int, int], read_steps: set[int] | None = None
) -> FrameAverage:
    """Average a series over one declared window of solver steps.

    The only implementation of this average in the package. A
    phase-locked reduction is this function applied once per passage,
    over the windows :func:`passage_windows` hands out, rather than a
    second averaging routine: two implementations of one average is how
    two published numbers come to disagree.

    It is PURE. It reads no file and writes none, so nothing about it
    can enforce the rule that a reduction never overwrites what it came
    from; that rule lives at the writing seam,
    :func:`pyflightstream.post.reductions.write_reduction`.

    Parameters
    ----------
    series : TimestepSeries
        The read-back frames.
    window : tuple of int, keyword-only
        Inclusive ``(first_step, last_step)`` in solver steps. Declared
        by the caller rather than derived: a blade passage is a fact
        about the rotor, not about the export.
    read_steps : set of int or None
        When supplied, collect the plotted steps used by this average.

    Returns
    -------
    FrameAverage
        Per-sample means over the frames inside the window.

    Raises
    ------
    MalformedOutputError
        If the window holds no frame, or is given backwards. An average
        of nothing is still a number, which is exactly why it is
        refused rather than returned as a NaN.
    """
    if series.n_frames == 0:
        raise MalformedOutputError("the series holds no frame")
    first, last = int(window[0]), int(window[1])
    if last < first:
        raise MalformedOutputError(
            f"the window ({first}, {last}) ends before it starts; it is an inclusive "
            "(first_step, last_step) pair in solver steps"
        )
    inside = (series.steps >= first) & (series.steps <= last)
    if read_steps is not None:
        read_steps.update(int(step) for step in series.steps[inside])
    count = int(inside.sum())
    if count == 0:
        raise MalformedOutputError(
            f"the window ({first}, {last}) holds no frame of a series running from "
            f"{int(series.steps[0])} to {int(series.steps[-1])} in steps of "
            f"{int(series.steps[1] - series.steps[0]) if len(series.steps) > 1 else 1}. "
            "An average over no frame is still a number, which is why this is refused "
            "rather than returned"
        )
    return FrameAverage(
        window=(first, last),
        n_frames=count,
        points=series.points,
        fields={name: values[inside].mean(axis=0) for name, values in series.fields.items()},
        sources=series.sources,
        source_window=(int(series.steps[inside].min()), int(series.steps[inside].max())),
    )


def passage_windows(series: TimestepSeries, *, period_steps: int) -> list[tuple[int, int]]:
    """Cut a series into successive passages of a declared period.

    The composition point for a phase-locked reduction: each window goes
    through :func:`blade_passage_average`, so the release holds one
    implementation of the average and this function holds only the
    arithmetic of where a passage starts.

    Parameters
    ----------
    series : TimestepSeries
        The read-back frames.
    period_steps : int, keyword-only
        Solver steps in one blade passage. For a rotor this is the
        caller's own conversion from RPM and blade count into steps; the
        library does not make it, because the time step is a fact of the
        run and not of the export.

    Returns
    -------
    list of tuple of int
        Inclusive ``(first_step, last_step)`` windows covering the
        series, dropping a trailing partial passage rather than
        averaging it against a shorter one.

    Raises
    ------
    MalformedOutputError
        If ``period_steps`` is not positive, or is longer than the
        series; or if the frames are not exported at one stride that
        divides ``period_steps``, because the passages would then hold
        their equally weighted frames at different phases.
    """
    if series.n_frames == 0:
        raise MalformedOutputError("the series holds no frame")
    period = int(period_steps)
    if period <= 0:
        raise MalformedOutputError(
            f"period_steps={period} is not a passage; it is the number of solver steps "
            "in one blade passage and must be at least one"
        )
    steps = series.steps
    span = int(steps[-1] - steps[0]) + 1
    if period > span:
        raise MalformedOutputError(
            f"one passage of {period} steps is longer than the {span} steps this series "
            "covers, so not one complete passage was exported"
        )
    # Each passage mean weights its frames equally, which is a time average
    # of the passage only when every passage holds the same phases: frames
    # evenly spaced, by a stride that divides the period. Otherwise the
    # passages hold different numbers of frames at different phases, and
    # their means differ by a sampling ripple that reads as unsteadiness.
    strides = {int(gap) for gap in np.diff(steps)}
    if any(stride <= 0 for stride in strides):
        raise MalformedOutputError(
            f"the frames have strides {sorted(strides)}; the export stride must be positive "
            "so each frame advances to a new solver step"
        )
    if len(strides) > 1 or (strides and period % next(iter(strides))):
        raise MalformedOutputError(
            f"the frames are exported every {sorted(strides)} step(s) and one passage is "
            f"{period} steps, so the passages would hold their frames at different "
            "phases and their means would differ by how they were sampled. Export at "
            "one stride that divides the passage"
        )
    windows: list[tuple[int, int]] = []
    start = int(steps[0])
    while start + period - 1 <= int(steps[-1]):
        windows.append((start, start + period - 1))
        start += period
    return windows


def revolution_drift_warnings(
    previous: Mapping[str, float],
    current: Mapping[str, float],
    shown: Mapping[str, str],
    *,
    limit_pct: float,
) -> list[str]:
    """Judge the last revolution of each force and moment column against its SCALE (FR-180).

    A plotted load column is named ``<parameter>_<group>`` (``FY_PROP_X``), the
    parameter one of the solver's force plot parameters. Its KIND is what the
    parameter measures (a force ``FX FY FZ``, a moment ``MX MY MZ``, a force
    coefficient ``CL CDI CDO CD``) and its GROUP is the text after the parameter:
    the columns of one kind and one group are the components of ONE load of one
    body in one frame, so an in-plane force is judged against the thrust and an
    in-plane moment against the torque. The scale is the largest magnitude among
    the PREVIOUS revolution's means of that kind and group, the revolution the
    relative drift divides by; a column warns when
    ``|mean_now - mean_prev| > limit_pct / 100 * scale``. For the column that IS
    the largest this is the relative drift of the table, unchanged; a near-zero
    component is not judged against itself, whose relative change is noise.

    ``shown`` maps each column to the name the table prints. Returns one clause
    per warned column, in column order, stating the change against the scale. A
    column that is no load, whose group has no finite nonzero mean, or whose own
    means are not numbers is never warned about.

    Parameters
    ----------
    previous : mapping of str to float
        Each column's mean over the previous revolution.
    current : mapping of str to float
        Each column's mean over the last revolution.
    shown : mapping of str to str
        Each column's name as the table prints it.
    limit_pct : float
        The drift allowed, in per cent of the scale.

    Returns
    -------
    list of str
        One clause per warned column, in column order.

    Examples
    --------
    >>> before = {"FX_P": 100.0, "FY_P": 0.02, "MACH_P1": 0.1}
    >>> names = {name: name for name in before}
    >>> after = {"FX_P": 100.1, "FY_P": 0.005, "MACH_P1": 0.2}
    >>> revolution_drift_warnings(before, after, names, limit_pct=1.0)
    []
    >>> (clause,) = revolution_drift_warnings(before, {**after, "FY_P": 2.5}, names, limit_pct=1.0)
    >>> clause.split(" (")[0]
    'column FY_P drifts +2.4800 per cent of its scale 100'
    """
    kinds: dict[str, tuple[str, str]] = {}
    largest: dict[tuple[str, str], str] = {}
    for name, value in previous.items():
        parameter, _, group = name.partition("_")
        if parameter not in FORCE_PLOT_PARAMETERS:
            continue
        measured, units = FORCE_PLOT_PARAMETERS[parameter]
        key = ("coefficient" if units == "COEFFICIENTS" else measured.split("_")[0].lower(), group)
        kinds[name] = key
        best = largest.get(key)
        if math.isfinite(value) and (best is None or abs(value) > abs(previous[best])):
            largest[key] = name
    clauses: list[str] = []
    for name, key in kinds.items():
        by = largest.get(key)
        if by is None or previous[by] == 0.0:
            continue
        scale = abs(previous[by])
        change = current[name] - previous[name]
        pct = change / scale * 100.0
        if abs(pct) > limit_pct:  # NaN compares False: a mean that is no number is quiet
            clauses.append(
                f"column {shown[name]} drifts {pct:+.4f} per cent of its scale {scale:.6g} "
                f"(the magnitude of {shown[by]}, the largest {key[0]} mean of its group in "
                f"the earlier revolution; a change of {change:+.6g})"
            )
    return clauses


def _refuse_a_gap(average: FrameAverage, first: int, last: int) -> None:
    """Refuse an average that holds fewer frames than the window it states has steps."""
    if average.n_frames != last - first + 1:
        raise ProductError(
            f"the row states steps {first} to {last} ({last - first + 1} steps) and the history "
            f"holds {average.n_frames} of them, so the columns would state a window the average "
            "was not taken over; a window with a missing step is not averaged as a whole one"
        )


def _family_of(name: str, families: Sequence[str]) -> int | None:
    """Return the index of the family a column is named for, or None.

    A column of one blade ends in ``_<family>``. Where the ends of two families overlap
    (``Blade_1`` and ``1``) the LONGEST family that fits owns the column, so a shorter
    family never takes a longer one's columns (F-212, F-165).
    """
    best: int | None = None
    for index, family in enumerate(families):
        if name.endswith(f"_{family}") and len(name) > len(family) + 1:
            if best is None or len(family) > len(families[best]):
                best = index
    return best


def per_blade_rows(
    series: TimestepSeries,
    *,
    window: tuple[int, int],
    blades: int,
    steps_per_revolution: float | None,
    blade1_azimuth_deg: float | None = 0.0,
    blade_families: Sequence[str] | None = None,
    sense: float = 1.0,
) -> list[dict[str, object]]:
    """One row per blade, every blade averaged over the SAME window.

    Item 8: the reading is the last converged window, and
    even for a wheel every blade is read over that same window.

    WHAT THIS REPLACES. `per_blade` averaged each blade over ITS OWN passage,
    so blade 1 came from one stretch of the history and blade 4 from another.
    Any difference between two blades then mixes a real azimuthal difference
    with a difference in WHEN they were sampled, and nothing in the file says
    which is which. One window removes the second cause entirely.

    THE AZIMUTHS ARE WRITTEN, NOT AVERAGED AWAY. The blades genuinely are at
    different azimuths at any instant, and that is a fact to record rather than
    a problem to smooth: a column states each blade's azimuthal position at the
    start and at the end of the shared window. Each row
    says where that blade was when the window opened and when it closed.

    THE AVERAGE IS `blade_passage_average`, over the window this is given. No
    second averaging routine is written here: two implementations of one
    average is how two published numbers come to disagree, which that
    function's own docstring says and item 16 turned on a probe that asked for
    exactly that mistake.

    Parameters
    ----------
    series : TimestepSeries
        The plots history, read back.
    window : tuple of int
        Inclusive ``(first_step, last_step)``, the one window every blade
        shares: the LAST revolutions or iterations the matrix row states,
        resolved by :func:`pyflightstream.cases.windows.averaging_span`.
    blades : int
        How many blades the rotor carries.
    steps_per_revolution : float
        Solver steps in one revolution, which turns a step count into an angle.
    blade1_azimuth_deg : float or None
        Where blade one sits at the window's first step. The other blades are
        spaced evenly from it, by ``360 / blades``. None, or no
        ``steps_per_revolution``, leaves both azimuths unstated (None), which
        a table writes as `NA`: zero is a real azimuth.
    blade_families : sequence of str, optional
        The blade families in the rotor's own order. A plot is named
        ``<parameter>_<group>`` and a group cut per blade is named for the
        blade's family, so a blade's columns are the ones ENDING in
        ``_<family>``; the row carries them with the family removed. There is
        one row per family given, which on a sector is fewer than ``blades``.
        Without it the columns are the ones PREFIXED ``Blade<n>_``.
    sense : float
        The sign of the rotor's speed: the way the azimuth grows.

    Returns
    -------
    list of dict
        One mapping per blade: ``BLADE``, ``FIRST_STEP``, ``LAST_STEP``,
        ``AZIMUTH_START``, ``AZIMUTH_END``, and that blade's own averaged
        columns with the blade prefix removed.

    Raises
    ------
    ProductError
        If the window names no step the history holds, the history misses a step inside
        the window, or the rotor carries no blade. Could-not-measure is never a pass.
    """
    if blades < 1:
        raise ProductError(f"the rotor carries {blades} blades, so it has no per-blade rows")
    if steps_per_revolution is not None and steps_per_revolution <= 0:
        raise ProductError(
            f"steps_per_revolution is {steps_per_revolution}, so a step count cannot be "
            "turned into an angle and no azimuth can be written"
        )
    first, last = int(window[0]), int(window[1])
    steps = np.asarray(series.steps, dtype=int)
    if not ((steps >= first) & (steps <= last)).any():
        held = f"runs from {int(steps[0])} to {int(steps[-1])}" if len(steps) else "holds no step"
        raise ProductError(f"the window {window} names no step this history holds, which {held}")
    spanned = last - first
    average = blade_passage_average(series, window=(first, last))
    _refuse_a_gap(average, first, last)
    spacing = 360.0 / blades

    rows: list[dict[str, object]] = []
    families = None if blade_families is None else [str(f) for f in blade_families]
    turning = 1.0 if sense >= 0 else -1.0
    for index in range(blades if families is None else len(families)):
        number = index + 1
        start: float | None = None
        end: float | None = None
        if blade1_azimuth_deg is not None and steps_per_revolution is not None:
            start = (blade1_azimuth_deg + index * spacing) % 360.0 + 0.0
            end = blade_azimuth_deg(
                start, step=spanned, steps_per_revolution=steps_per_revolution, rpm=turning
            )
        row: dict[str, object] = {
            "BLADE": number,
            "FIRST_STEP": first,
            "LAST_STEP": last,
            "AZIMUTH_START": start,
            "AZIMUTH_END": end,
        }
        # THAT BLADE'S OWN COLUMNS AND NOT THE ROTOR'S. A column named for one
        # blade belongs to one row; the prefix is dropped so the rows of two
        # blades line up under the same headings and can be compared.
        if families is not None:
            row["FAMILY"] = families[index]
            suffix = f"_{families[index]}"
            for name, values in average.fields.items():
                if _family_of(name, families) == index:
                    row[name[: -len(suffix)]] = float(values[0])
            rows.append(row)
            continue
        prefix = f"Blade{number}_"
        for name, values in average.fields.items():
            if name.startswith(prefix):
                row[name[len(prefix) :]] = float(values[0])
        rows.append(row)
    return rows


def blade_one_azimuth(
    step: float, *, datum_deg: float, sense: float, steps_per_revolution: float
) -> float:
    """Return where blade one of a rotor is at ``step``, in degrees, wrapped to one turn.

    The one convention of every table that states an azimuth:
    ``(datum + sense * step * 360 / steps_per_revolution) mod 360``, the datum
    being blade one's azimuth at step zero and ``sense`` the sign of the rotor's
    speed, all of THAT rotor.

    Parameters
    ----------
    step : float
        The time step.
    datum_deg : float
        Blade one's azimuth at step zero, in degrees.
    sense : float
        The sign of the rotor's speed.
    steps_per_revolution : float
        The rotor's clock, in steps per revolution.

    Returns
    -------
    float
        The azimuth in degrees, wrapped to one turn.

    Raises
    ------
    ProductError
        If the step, the datum and the steps per revolution do not state a clock.

    Examples
    --------
    >>> blade_one_azimuth(3, datum_deg=10.0, sense=-1.0, steps_per_revolution=8.0)
    235.0
    """
    turned = blade_azimuth_deg(
        datum_deg,
        step=step,
        steps_per_revolution=steps_per_revolution,
        rpm=1.0 if sense >= 0 else -1.0,
    )
    if turned is None:
        raise ProductError(
            f"no azimuth at step {step!r}: the datum {datum_deg!r} and the "
            f"{steps_per_revolution!r} steps per revolution do not state a clock"
        )
    return turned


def _note_read_steps(read_steps: set[int], steps: np.ndarray, moments: np.ndarray) -> None:
    """Collect the plotted steps that carry a nonzero interpolation weight at ``moments``."""
    for moment in moments:
        upper = int(np.searchsorted(steps, moment, side="left"))
        if upper == len(steps):
            read_steps.add(int(steps[-1]))
        elif upper == 0 or steps[upper] == moment:
            read_steps.add(int(steps[upper]))
        else:
            # Strictly between these steps, both weights are nonzero.
            read_steps.update((int(steps[upper - 1]), int(steps[upper])))


def _refuse_a_clock(per_revolution: float, depth: float) -> None:
    """Refuse a clock or depth that is NaN or infinite, which no step can be turned by."""
    if not (math.isfinite(per_revolution) and math.isfinite(depth)):
        raise ProductError(
            f"steps_per_revolution={per_revolution!r} and revolutions={depth!r} must "
            "both be finite numbers, or no step can be turned into an azimuth"
        )


def phase_locked_rows(
    series: TimestepSeries,
    columns: Sequence[str],
    *,
    last_step: int,
    revolutions: float,
    steps_per_revolution: float,
    blade1_azimuth_deg: float,
    sense: float = 1.0,
    blades: int = 0,
    blade_families: Sequence[str] = (),
    read_steps: set[int] | None = None,
) -> list[dict[str, object]]:
    """Return the mean AT EACH AZIMUTH across the last ``revolutions`` turns, a row per azimuth.

    THIS IS NOT A WINDOW AVERAGE, and that is the whole of it. A window average
    (:func:`blade_passage_average`) runs ALONG the history; this one runs ACROSS
    it: the sample at one azimuthal position is taken from each of the last
    ``revolutions`` revolutions, and those samples are averaged. With three
    revolutions every azimuth has three datapoints in its mean.

    THE ROWS are the azimuthal positions the rotor visits in its LAST revolution,
    one per solver step of it, sorted from 0 towards 360. ``AZIMUTH`` is where
    blade one is, by :func:`blade_one_azimuth`.

    A COLUMN OF ONE BLADE IS TABULATED BY THAT BLADE'S OWN AZIMUTH. A plot is
    named ``<parameter>_<group>`` and a group cut per blade ends in the blade's
    family, so a column ending ``_<family>`` of a family in ``blade_families`` is
    sampled where THAT blade, which sits ``position * 360 / blades`` after blade
    one, is at the row's azimuth. Two blades then line up azimuth for azimuth.
    Every other column, a rotor's total or the aircraft's, is tabulated by blade
    one's azimuth.

    BETWEEN TWO STEPS THE HISTORY IS READ LINEARLY. One revolution earlier is
    ``steps_per_revolution`` steps earlier, which is a whole step only when the
    revolution is a whole number of steps, and a blade's offset is a whole step
    only when that number divides by ``blades``. Where both hold every sample is
    a row of the history and nothing is interpolated.

    ``REVOLUTIONS`` is the FEWEST samples that entered the mean of any column of the row.
    The columns of blade one are sampled at the row's azimuth and those of the other blades
    a fraction of a revolution earlier, so at a fractional depth a shifted blade can hold
    one sample less than blade one; the row states the smaller count, never the larger.
    It is ``revolutions`` exactly when that is a whole number.

    Parameters
    ----------
    series : TimestepSeries
        The plots history, read back.
    columns : sequence of str
        The plotted columns to reduce, in order; the clock is the caller's to
        leave out.
    last_step : int
        The step the last revolution ends at.
    revolutions : float
        How many of the last revolutions enter each mean; at least one.
    steps_per_revolution : float
        Solver steps in one revolution of THIS rotor.
    blade1_azimuth_deg, sense : float
        Blade one's azimuth at step zero, and the sign of the rotor's speed.
    blades : int
        The rotor's blade count, which spaces the blades.
    blade_families : sequence of str
        The blade families in the rotor's own order, blade one first.
    read_steps : set of int or None
        Collect the plotted steps contributing to the interpolation. Every
        nonzero interpolation weight counts, without a tolerance cutoff.

    Returns
    -------
    list of dict of str to object
        One row per azimuth of the last revolution, with ``AZIMUTH``, ``REVOLUTIONS`` and the mean
        of each column.

    Raises
    ------
    ProductError
        If the depth is under one revolution, the clock is not positive, or the
        history does not cover the revolutions asked for. Could-not-measure is
        never a pass.

    Examples
    --------
    Two revolutions of four steps; the mean of steps 1 and 5, 2 and 6, and so on.

    >>> import numpy as np
    >>> history = TimestepSeries(
    ...     steps=np.arange(1, 9), times_s=None, points=np.zeros((1, 3)),
    ...     fields={"CL": np.array([1.0, 2.0, 4.0, 8.0, 3.0, 6.0, 0.0, 0.0])[:, None]},
    ...     sources=(),
    ... )
    >>> rows = phase_locked_rows(
    ...     history, ["CL"], last_step=8, revolutions=2, steps_per_revolution=4.0,
    ...     blade1_azimuth_deg=0.0,
    ... )
    >>> [(row["AZIMUTH"], row["CL"]) for row in rows]
    [(0.0, 4.0), (90.0, 2.0), (180.0, 4.0), (270.0, 2.0)]
    """
    per_revolution = float(steps_per_revolution)
    depth = float(revolutions)
    _refuse_a_clock(per_revolution, depth)
    if per_revolution <= 0:
        raise ProductError(
            f"steps_per_revolution is {steps_per_revolution}, so a step cannot be turned "
            "into an azimuth"
        )
    if depth < 1.0:
        raise ProductError(
            f"last_revolutions_avg is {depth:g}, under one revolution, so no table from 0 to "
            "360 degrees can be filled. State at least 1 under [phase_locked] in the pproc "
            "artifact"
        )
    steps = np.asarray(series.steps, dtype=float)
    last = int(last_step)
    opening = last - depth * per_revolution  # exclusive
    first_needed = int(np.floor(opening + 1e-9)) + 1
    if not len(steps) or steps[0] > max(first_needed, 1) or steps[-1] < last:
        held = f"steps {int(steps[0])} to {int(steps[-1])}" if len(steps) else "no step"
        raise ProductError(
            f"the last {depth:g} revolution(s) are steps {max(first_needed, 1)} to {last} and "
            f"the history holds {held}, so the revolutions to average across are not all there"
        )
    tolerance = 1e-9 * per_revolution
    turning = 1.0 if sense >= 0 else -1.0
    families = [str(family) for family in blade_families]
    count = int(blades) if int(blades) >= len(families) else len(families)

    def offset_of(name: str) -> float:
        """How many steps BEFORE blade one a blade's column is sampled."""
        position = _family_of(name, families)
        if position:  # None (no family) and 0 (blade one) are sampled where blade one is
            return (turning * position * per_revolution / count) % per_revolution
        return 0.0

    def samples(at: float) -> np.ndarray:
        """Every moment inside the revolutions asked for that is congruent to ``at``."""
        newest = at + np.floor((last - at) / per_revolution + 1e-12) * per_revolution
        moments = []
        moment = newest
        while moment > opening + tolerance:
            if moment < steps[0] - tolerance:
                raise ProductError(
                    f"the phase-locked sample at step {moment:g} needs interpolation "
                    f"support before the history begins at step {steps[0]:g}; "
                    "dropping it would average fewer revolutions than requested"
                )
            moments.append(moment)
            moment -= per_revolution
        return np.asarray(moments, dtype=float)

    final_revolution = [
        step
        for step in range(max(first_needed, 1), last + 1)
        if step > last - per_revolution + tolerance
    ]
    rows: list[dict[str, object]] = []
    for step in final_revolution:
        held = int(len(samples(float(step))))
        row: dict[str, object] = {
            "AZIMUTH": blade_one_azimuth(
                step,
                datum_deg=blade1_azimuth_deg,
                sense=turning,
                steps_per_revolution=per_revolution,
            ),
            "STEP": step,
            "REVOLUTIONS": held,
        }
        for name in columns:
            values = series.fields.get(name)
            if values is None:
                continue
            moments = samples(step - offset_of(name))
            row["REVOLUTIONS"] = held = min(held, len(moments))
            if not len(moments):
                row[name] = None
                continue
            history = np.asarray(values, dtype=float).reshape(len(steps), -1)[:, 0]
            if read_steps is not None:
                _note_read_steps(read_steps, steps, moments)
            row[name] = float(np.mean(np.interp(moments, steps, history)))
        rows.append(row)
    rows.sort(key=lambda row: float(row["AZIMUTH"]))  # type: ignore[arg-type]
    return rows
