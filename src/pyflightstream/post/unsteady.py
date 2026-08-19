"""Per-timestep field frames, read back as an ordered series.

Pipeline role: the entry point of unsteady post-processing. An unsteady
run asked to animate (``UNSTEADY_SOLVER_ANIMATION``, SRC-003 pp.347-348)
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

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from pyflightstream.results import IncompleteOutputError, MalformedOutputError

__all__ = [
    "FrameAverage",
    "TimestepSeries",
    "blade_passage_average",
    "passage_windows",
    "read_timestep_series",
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
        the first frame; every later frame must agree.
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
    """

    window: tuple[int, int]
    n_frames: int
    points: np.ndarray
    fields: dict[str, np.ndarray]
    sources: tuple[Path, ...]


def _read_tecplot_frame(text: str) -> tuple[np.ndarray, dict[str, np.ndarray], float | None]:
    """Read one Tecplot ASCII ordered POINT zone."""
    names: list[str] = []
    solution_time: float | None = None
    declared_points: int | None = None
    rows: list[list[float]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        upper = stripped.upper()
        if upper.startswith("TITLE"):
            continue
        if upper.startswith("VARIABLES"):
            names = [token for token in stripped.split('"')[1::2]]
            continue
        if upper.startswith("ZONE"):
            # The zone's declared point count, so a truncated table is
            # refused rather than returned short. Anchored so the I of a
            # longer keyword cannot match: this record carries several.
            declared = re.search(r"(?<![A-Z])I\s*=\s*(\d+)", upper)
            if declared is not None:
                declared_points = int(declared.group(1))
            if "SOLUTIONTIME" in upper:
                tail = upper.split("SOLUTIONTIME", 1)[1].lstrip(" =")
                token = tail.split()[0].strip('"').rstrip('"')
                try:
                    solution_time = float(token)
                except ValueError as error:
                    raise MalformedOutputError(
                        f"the zone record declares SOLUTIONTIME={token!r}, which is not a "
                        "number, so the frame cannot say when it was written"
                    ) from error
            continue
        rows.append([float(token) for token in stripped.split()])
    if not names or not rows:
        raise MalformedOutputError(
            "the frame carries no VARIABLES record or no data rows, so it is not a "
            "Tecplot ASCII point zone"
        )
    table = np.asarray(rows, dtype=float)
    if table.shape[1] != len(names):
        raise MalformedOutputError(
            f"the frame declares {len(names)} variables and its rows hold {table.shape[1]} columns"
        )
    # The zone's own I= against the rows that are THERE. The reader
    # ignored it until 2026-08-19, so a file cut mid-table came back
    # shorter with no refusal, and a history one step short is the worst
    # shape here: every reduction downstream averages over whatever it
    # was handed. Read here rather than at the ZONE branch because the
    # row count only exists once the loop has finished.
    if declared_points is not None and len(rows) != declared_points:
        raise IncompleteOutputError(
            f"the zone declares I={declared_points} and the frame carries {len(rows)} "
            "row(s). It is truncated, and a shorter frame read as a whole one makes "
            "every reduction over it an average of a run that did not finish writing"
        )
    points = table[:, :3]
    fields = {name: table[:, index] for index, name in enumerate(names) if index >= 3}
    return points, fields, solution_time


def _read_vtk_frame(text: str) -> tuple[np.ndarray, dict[str, np.ndarray], float | None]:
    """Read one VTK legacy ASCII polydata frame."""
    lines = [line.strip() for line in text.splitlines()]
    try:
        start = next(i for i, line in enumerate(lines) if line.upper().startswith("POINTS "))
    except StopIteration as error:
        raise MalformedOutputError(
            "the frame carries no POINTS record, so it is not VTK legacy ASCII polydata"
        ) from error
    count = int(lines[start].split()[1])
    rows = lines[start + 1 : start + 1 + count]
    # The declared count against the rows that are THERE. Without this the
    # slice simply runs out and the frame comes back short, which every
    # reduction downstream then averages over as though it were the run
    # (measured 2026-08-19: a file cut after the point block returned two
    # frames, an unmet point count and no fields at all, with no refusal).
    if len(rows) != count:
        raise IncompleteOutputError(
            f"the frame declares POINTS {count} and carries {len(rows)}. It is "
            "truncated, and a shorter frame read as a whole one makes every "
            "reduction over it an average of a run that did not finish writing"
        )
    points = np.asarray(
        [[float(token) for token in line.split()] for line in rows],
        dtype=float,
    )
    fields: dict[str, np.ndarray] = {}
    index = start + 1 + count
    while index < len(lines):
        line = lines[index]
        upper = line.upper()
        if upper.startswith("SCALARS "):
            name = line.split()[1]
            body = index + 2  # the LOOKUP_TABLE line sits between
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
            fields[name] = np.asarray(
                [float(lines[i]) for i in range(body, body + count)], dtype=float
            )
            index = body + count
            continue
        if upper.startswith("VECTORS "):
            name = line.split()[1]
            body = index + 1
            fields[name] = np.asarray(
                [[float(t) for t in lines[i].split()] for i in range(body, body + count)],
                dtype=float,
            )
            index = body + count
            continue
        index += 1
    # VTK legacy polydata has no time record: the title line is the
    # caller's own string, so reading a step out of it would be reading
    # something this library wrote rather than something the solver did.
    return points, fields, None


def _read_frame(path: Path) -> tuple[np.ndarray, dict[str, np.ndarray], float | None]:
    """Read one exported frame, in whichever of the two shapes it is."""
    text = path.read_text(encoding="utf-8")
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
        Dimensionless step count; the step axis is frame index times
        this. Default 1, which yields frame indices.

    Returns
    -------
    TimestepSeries
        The series, with the order evidence recorded on it.

    Raises
    ------
    MalformedOutputError
        If no order can be established; if a frame is in neither
        supported shape; or if a frame's variables or sample count
        disagree with the first frame's, because a series is one
        quantity over time or it is not a series.

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
    if order not in (None, "given"):
        raise MalformedOutputError(
            f"order={order!r} is not a way this reader can establish an order. The two "
            "it has are order='given', the caller declaring the sequence is already in "
            "solver order, and the default, each frame's own solution time."
        )
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


def blade_passage_average(series: TimestepSeries, *, window: tuple[int, int]) -> FrameAverage:
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
    first, last = int(window[0]), int(window[1])
    if last < first:
        raise MalformedOutputError(
            f"the window ({first}, {last}) ends before it starts; it is an inclusive "
            "(first_step, last_step) pair in solver steps"
        )
    inside = (series.steps >= first) & (series.steps <= last)
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
        series.
    """
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
    windows: list[tuple[int, int]] = []
    start = int(steps[0])
    while start + period - 1 <= int(steps[-1]):
        windows.append((start, start + period - 1))
        start += period
    return windows
