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

from pyflightstream._errors import ProductError
from pyflightstream.results import IncompleteOutputError, MalformedOutputError

__all__ = [
    "FrameAverage",
    "TimestepSeries",
    "blade_passage_average",
    "blade_one_azimuth",
    "passage_windows",
    "phase_locked_rows",
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

    v0.23.0 item 8, the owner's reading of her own periodic case on 2026-09-17:
    "faz sentido sempre olhar a ultima janela convergida ... mesmo pro wheel,
    faz sentido olhar todas as blades na mesma janela".

    WHAT THIS REPLACES. `per_blade` averaged each blade over ITS OWN passage,
    so blade 1 came from one stretch of the history and blade 4 from another.
    Any difference between two blades then mixes a real azimuthal difference
    with a difference in WHEN they were sampled, and nothing in the file says
    which is which. One window removes the second cause entirely.

    THE AZIMUTHS ARE WRITTEN, NOT AVERAGED AWAY. The blades genuinely are at
    different azimuths at any instant, and that is a fact to record rather than
    a problem to smooth: her words, "podemos ter uma coluna que mostra a
    posição azimutal de inicio e fim de cada para a mesma janela". Each row
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
        The blade families in the rotor's own order (0.24.0). A plot is named
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
    ValueError
        If the window names no step the history holds, or the rotor carries no
        blade. Could-not-measure is never a pass.
    """
    if blades < 1:
        raise ValueError(f"the rotor carries {blades} blades, so it has no per-blade rows")
    if steps_per_revolution is not None and steps_per_revolution <= 0:
        raise ValueError(
            f"steps_per_revolution is {steps_per_revolution}, so a step count cannot be "
            "turned into an angle and no azimuth can be written"
        )
    first, last = int(window[0]), int(window[1])
    steps = np.asarray(series.steps, dtype=int)
    if not ((steps >= first) & (steps <= last)).any():
        raise ValueError(
            f"the window {window} names no step this history holds, which runs from "
            f"{int(steps[0])} to {int(steps[-1])}"
        )
    spanned = last - first
    average = blade_passage_average(series, window=(first, last))
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
            end = (start + turning * spanned * 360.0 / steps_per_revolution) % 360.0 + 0.0
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
                if name.endswith(suffix) and len(name) > len(suffix):
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

    Examples
    --------
    >>> blade_one_azimuth(3, datum_deg=10.0, sense=-1.0, steps_per_revolution=8.0)
    235.0
    """
    turning = 1.0 if sense >= 0 else -1.0
    return (float(datum_deg) + turning * float(step) * 360.0 / float(steps_per_revolution)) % (
        360.0
    ) + 0.0


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

    ``REVOLUTIONS`` is how many samples entered the means of the row's
    blade-one columns: ``revolutions`` exactly when that is a whole number.

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
        for position, family in enumerate(families):
            if position and name.endswith(f"_{family}") and len(name) > len(family) + 1:
                return (turning * position * per_revolution / count) % per_revolution
        return 0.0

    def samples(at: float) -> np.ndarray:
        """Every moment inside the revolutions asked for that is congruent to ``at``."""
        newest = at + np.floor((last - at) / per_revolution + 1e-12) * per_revolution
        moments = []
        moment = newest
        while moment > opening + tolerance:
            if moment >= steps[0] - tolerance:
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
        row: dict[str, object] = {
            "AZIMUTH": blade_one_azimuth(
                step,
                datum_deg=blade1_azimuth_deg,
                sense=turning,
                steps_per_revolution=per_revolution,
            ),
            "STEP": step,
            "REVOLUTIONS": int(len(samples(float(step)))),
        }
        for name in columns:
            values = series.fields.get(name)
            if values is None:
                continue
            moments = samples(step - offset_of(name))
            if not len(moments):
                row[name] = None
                continue
            history = np.asarray(values, dtype=float).reshape(len(steps), -1)[:, 0]
            row[name] = float(np.mean(np.interp(moments, steps, history)))
        rows.append(row)
    rows.sort(key=lambda row: float(row["AZIMUTH"]))  # type: ignore[arg-type]
    return rows
