"""Split a matrix's polars into batch jobs and price each job's wall clock (FR-362 to FR-364).

Private to :mod:`pyflightstream.run`. A batch job is several whole polars solved
in ONE FlightStream instance, so the questions a grouped plan asks are
arithmetic: which polars share a job, how long the job takes, and what wall
clock to ask the scheduler for. This module answers them from numbers alone
(the recorded costs, the row cells, the measured overheads), so the answers are
testable without a workspace or a solver.

THE SPLIT. Polars are grouped by ``(ncpus, fs_build, actions)``, because a job
has one processor count, one build and one set of the setup's own unsteady
solver actions (FR-405: an action survives ``NEW_SIMULATION`` and no command
withdraws one, so it would run on every later polar of the job).
Inside a group the polars stay in matrix order
and a job is a CONTIGUOUS run of them: the optimal linear partition, the one
whose longest job is shortest. A polar is never cut, and ``n`` above the polars
warns and uses only what it needs.

THE ESTIMATE. ``T = start + refresh x (polars - 1) + sum(t_point) +
reinit x (points - polars)`` with the overheads of :data:`MEASURED_OVERHEADS`.
THE WALLTIME. ``BEST`` is ``ceil_to_the_minute(1.25 x T + margin)``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache

__all__ = [
    "BEST_FACTOR",
    "MEASURED_OVERHEADS",
    "JobSplit",
    "Overheads",
    "PolarUnit",
    "best_walltime_s",
    "job_estimate",
    "job_walltime",
    "split_polars",
    "walltime_text",
]

#: The safety factor of the BEST walltime (FR-364): the estimate times this, plus the margin.
BEST_FACTOR = 1.25


@dataclass(frozen=True)
class PolarUnit:
    """One polar as the split sees it: its sim, its shape and its points' estimated seconds.

    Attributes
    ----------
    sim_id : str
        The simulation (POL) the polar belongs to.
    order : int
        Its position in the matrix, from 1; the split keeps this order.
    ncpus : int
        The processor count the row asks for.
    fs_build : str
        The build the row runs on ("" for the campaign's own).
    run_ids : tuple of str
        The pending points, in order.
    point_seconds : tuple of float or None
        The estimated seconds of each pending point, None where no recorded run gives one.
    walltime_cell_s : float or None
        The row's stated WALLTIME in seconds; None for a BEST row or a row stating none.
    walltime_cell_text : str or None
        The cell as written, for a sentence that names it.
    best : bool
        Whether the row's cell reads BEST.
    margin_s : float
        The row's walltime margin, in seconds.
    actions : tuple of (str, str, str)
        The setup's own unsteady solver actions, ``(type, name, filename)``; empty for none
        (FR-405).
    """

    sim_id: str
    order: int
    ncpus: int
    fs_build: str
    run_ids: tuple[str, ...]
    point_seconds: tuple[float | None, ...]
    walltime_cell_s: float | None
    walltime_cell_text: str | None
    best: bool
    margin_s: float
    actions: tuple[tuple[str, str, str], ...] = ()


@dataclass(frozen=True)
class Overheads:
    """What one FlightStream instance costs beyond the solve itself, in seconds.

    Attributes
    ----------
    start_s : float
        Launching the instance and opening the first polar.
    reinit_s : float
        Re-initialising the solver between two points of one polar.
    refresh_s : float
        Moving from one polar to the next inside the instance.
    basis : str
        The measurement the figures rest on, carried into the receipt.
    """

    start_s: float
    reinit_s: float
    refresh_s: float
    basis: str


#: The overheads measured on a synthetic geometry (the figure of 2026-10-02).
MEASURED_OVERHEADS = Overheads(
    start_s=2.0,
    reinit_s=0.08,
    refresh_s=2.0,
    basis=(
        "30_BLADE on 26.124, 2026-10-02: a fresh launch with no solve 1.67 s, the per-instance "
        "overhead about 2 s, the re-initialisation 0.08 s; OPEN of a production mesh not measured"
    ),
)


@dataclass(frozen=True)
class JobSplit:
    """The polars one job holds, in matrix order.

    Attributes
    ----------
    units : tuple of PolarUnit
        The polars, all of one ``(ncpus, fs_build, actions)``.
    """

    units: tuple[PolarUnit, ...]


def _weight(unit: PolarUnit) -> float:
    """Return the seconds a polar weighs in the partition: its estimates, its cell for a gap."""
    known = sum(t for t in unit.point_seconds if t is not None)
    gaps = sum(1 for t in unit.point_seconds if t is None)
    if gaps and unit.walltime_cell_s is not None:
        known += gaps * unit.walltime_cell_s
    return known if known > 0 else float(len(unit.run_ids) or 1)


def _partition(weights: Sequence[float], jobs: int) -> list[int]:
    """Return the cut indices of the optimal contiguous partition into ``jobs`` runs.

    Minimises the longest run (the classical linear partition, by dynamic programming);
    ties take the earliest cut, so the result is deterministic.

    Parameters
    ----------
    weights : sequence of float
        The polars' weights in order.
    jobs : int
        How many runs, between 1 and ``len(weights)``.

    Returns
    -------
    list of int
        The ``jobs - 1`` indices at which a new run starts.
    """
    count = len(weights)
    prefix = [0.0]
    for weight in weights:
        prefix.append(prefix[-1] + weight)

    @cache
    def best(runs: int, upto: int) -> tuple[float, int]:
        if runs == 1:
            return prefix[upto], 0
        choice = (math.inf, runs - 1)
        for cut in range(runs - 1, upto):
            longest = max(best(runs - 1, cut)[0], prefix[upto] - prefix[cut])
            if longest < choice[0]:
                choice = (longest, cut)
        return choice

    cuts: list[int] = []
    upto = count
    for runs in range(jobs, 1, -1):
        cut = best(runs, upto)[1]
        cuts.append(cut)
        upto = cut
    return sorted(cuts)


def _runs(units: Sequence[PolarUnit], jobs: int) -> list[tuple[PolarUnit, ...]]:
    """Cut one group's polars into ``jobs`` contiguous runs."""
    cuts = _partition([_weight(unit) for unit in units], jobs)
    edges = [0, *cuts, len(units)]
    return [tuple(units[a:b]) for a, b in zip(edges, edges[1:], strict=False)]


def _longest(units: Sequence[PolarUnit], jobs: int) -> float:
    """Return the longest run's weight when the group is cut into ``jobs`` runs."""
    return max(sum(_weight(unit) for unit in run) for run in _runs(units, jobs))


def split_polars(units: Sequence[PolarUnit], n: int) -> tuple[list[JobSplit], list[str]]:
    """Cut the polars into about ``n`` batch jobs (FR-362).

    Groups by ``(ncpus, fs_build, actions)`` in matrix order, gives each group at least one
    job, cuts
    each group into the optimal contiguous partition that minimises its longest job, and hands
    the remaining jobs one at a time to the group whose longest job is longest while a polar can
    still be split off. A polar is never cut.

    Parameters
    ----------
    units : sequence of PolarUnit
        The polars, in matrix order.
    n : int
        The number of jobs asked for, at least 1.

    Returns
    -------
    tuple of list of JobSplit and list of str
        The jobs in matrix order of their first polar, and the warnings: ``n`` above the polars
        (only what is needed is used) and ``n`` below the number of groups (one job per group).
    """
    groups: dict[tuple[int, str, tuple[tuple[str, str, str], ...]], list[PolarUnit]] = {}
    for unit in units:
        groups.setdefault((unit.ncpus, unit.fs_build, unit.actions), []).append(unit)
    warnings: list[str] = []
    if n > len(units):
        warnings.append(
            f"--batch {n} asks for more jobs than the {len(units)} polar(s) there are, and a polar "
            f"is never cut, so {len(units)} job(s) are planned."
        )
    if n < len(groups):
        warnings.append(
            f"--batch {n} asks for fewer jobs than the {len(groups)} group(s) of processor count, "
            "build and unsteady_solver_actions there are, and a job holds one of each, so one "
            "job per group is planned."
        )
    counts = dict.fromkeys(groups, 1)
    for _ in range(max(0, min(n, len(units)) - len(groups))):
        open_groups = [key for key, members in groups.items() if counts[key] < len(members)]
        if not open_groups:
            break
        chosen = max(open_groups, key=lambda key: _longest(groups[key], counts[key]))
        counts[chosen] += 1
    jobs = [
        JobSplit(units=run)
        for key, members in groups.items()
        for run in _runs(members, counts[key])
    ]
    jobs.sort(key=lambda job: job.units[0].order)
    return jobs, warnings


def _unestimated(split: JobSplit) -> list[str]:
    """Return the points with neither a recorded estimate nor a row cell to fall back on."""
    return [
        run_id
        for unit in split.units
        for run_id, seconds in zip(unit.run_ids, unit.point_seconds, strict=True)
        if seconds is None and unit.walltime_cell_s is None
    ]


def job_estimate(
    split: JobSplit, overheads: Overheads
) -> tuple[float | None, list[str], list[str]]:
    """Estimate one job's seconds (FR-363).

    ``T = start + refresh x (polars - 1) + sum(t_point) + reinit x (points - polars)``. A point
    with no recorded estimate takes its row's WALLTIME cell and is named as a fallback; with
    neither it is unestimated, and the job has no estimate.

    Parameters
    ----------
    split : JobSplit
        The job's polars.
    overheads : Overheads
        The instance overheads.

    Returns
    -------
    tuple of float or None, list of str and list of str
        The estimate in seconds (None when a point is unestimated), the points that took their
        row's cell, and the unestimated points.
    """
    fallback: list[str] = []
    total = 0.0
    points = 0
    for unit in split.units:
        points += len(unit.run_ids)
        for run_id, seconds in zip(unit.run_ids, unit.point_seconds, strict=True):
            if seconds is not None:
                total += seconds
            elif unit.walltime_cell_s is not None:
                total += unit.walltime_cell_s
                fallback.append(run_id)
    polars = len(split.units)
    unestimated = _unestimated(split)
    if unestimated:
        return None, fallback, unestimated
    total += overheads.start_s + overheads.refresh_s * (polars - 1)
    total += overheads.reinit_s * (points - polars)
    return total, fallback, []


def best_walltime_s(estimate_s: float, margin_s: float, factor: float = BEST_FACTOR) -> int:
    """Return the BEST walltime: ``factor x estimate + margin``, ceiled to the minute (FR-364).

    Parameters
    ----------
    estimate_s : float
        The job's estimate in seconds.
    margin_s : float
        The walltime margin in seconds.
    factor : float, optional
        The safety factor, 1.25 by default.

    Returns
    -------
    int
        Whole seconds, a multiple of 60.
    """
    return math.ceil((factor * estimate_s + margin_s) / 60.0 - 1e-9) * 60


def walltime_text(seconds: int, *, split: JobSplit | None = None) -> str:
    """Return a job's wall clock as the WALLTIME cell writes it: whole minutes, else seconds.

    Parameters
    ----------
    seconds : int
        The wall clock in seconds.
    split : JobSplit or None, optional
        Unused; kept so callers that pass the job keep working.

    Returns
    -------
    str
        ``<minutes>m`` when the seconds are whole minutes, else ``<seconds>s`` (``68s``), so a
        clock summed from the rows' own cells is written exactly and never rounded up.
    """
    del split
    return f"{seconds // 60}m" if seconds % 60 == 0 else f"{seconds}s"


def _minutes(seconds: float) -> str:
    """Return a duration in whole hours and minutes for a sentence."""
    total = int(round(seconds / 60.0))
    return f"{total // 60}h{total % 60:02d}m"


def _cells_of(split: JobSplit) -> list[PolarUnit]:
    """Return the polars of the job that state a wall clock of their own."""
    return [unit for unit in split.units if unit.walltime_cell_s is not None]


def _from_cells(
    split: JobSplit, estimate_s: float | None, max_walltime_s: float | None
) -> tuple[int | None, str, bool | None, float | None, list[str], str | None]:
    """Return the walltime of a job whose rows state cells: the SUM of its points' budgets.

    A row's WALLTIME cell is the budget of ONE of its points (it states the
    wall clock a single datapoint is given), so a job that runs several points in
    one instance asks for the sum over its points of their rows' cells. A sum above the
    profile's ``max_walltime`` is capped there with a warning suggesting a larger ``n``; one
    point's own cell above it is refused.
    """
    cells = _cells_of(split)
    warnings: list[str] = []
    too_long = [
        unit
        for unit in cells
        if max_walltime_s is not None and (unit.walltime_cell_s or 0.0) > max_walltime_s
    ]
    if too_long and max_walltime_s is not None:
        unit = too_long[0]
        return (
            None,
            "matrix",
            None,
            None,
            warnings,
            f"the WALLTIME {unit.walltime_cell_text} of row {unit.sim_id} is above the "
            f"cluster's max_walltime of {_minutes(max_walltime_s)}; write a cell the cluster "
            "grants, or BEST.",
        )
    seconds = int(sum((unit.walltime_cell_s or 0.0) * max(len(unit.run_ids), 1) for unit in cells))
    for unit in split.units:
        if unit.best and unit.walltime_cell_s is None:
            if any(value is None for value in unit.point_seconds):
                return _from_estimate(split, None, max_walltime_s)
            seconds += best_walltime_s(
                sum(value for value in unit.point_seconds if value is not None), unit.margin_s
            )
    if max_walltime_s is not None and seconds > max_walltime_s:
        warnings.append(
            f"the job's points ask {_minutes(seconds)} together, above the cluster's max_walltime "
            f"of {_minutes(max_walltime_s)}; the job asks the maximum, and a larger --batch n "
            "makes shorter jobs."
        )
        seconds = int(max_walltime_s)
        return seconds, "max_walltime", False, None, warnings, None
    if estimate_s is None or not any(
        value is not None for unit in split.units for value in unit.point_seconds
    ):
        return seconds, "matrix", None, None, warnings, None
    need = best_walltime_s(estimate_s, max(unit.margin_s for unit in split.units))
    if need <= seconds:
        return seconds, "matrix", True, None, warnings, None
    short = float(need - seconds)
    warnings.append(
        f"the job's points ask {_minutes(seconds)} together and its estimate needs {need // 60}m "
        f"(1.25 x {_minutes(estimate_s)} plus the margin), {_minutes(short)} short; the cells "
        "are kept, and a larger --batch n makes shorter jobs."
    )
    return seconds, "matrix", False, short, warnings, None


def _from_estimate(
    split: JobSplit, estimate_s: float | None, max_walltime_s: float | None
) -> tuple[int | None, str, bool | None, float | None, list[str], str | None]:
    """Return the walltime of an all-BEST job: its estimate, else the limit, else a block."""
    if estimate_s is None:
        names = ", ".join(_unestimated(split))
        if max_walltime_s is None:
            return (
                None,
                "none",
                None,
                None,
                [],
                f"no estimate for {names}, and the profile states no max_walltime to ask for; "
                "write a wall clock with its unit in those rows, or run one point of the row "
                "first so the fit has a sample.",
            )
        return (
            int(max_walltime_s),
            "max_walltime",
            None,
            None,
            [f"no estimate for {names}; the job asks the profile's max_walltime."],
            None,
        )
    wanted = best_walltime_s(estimate_s, max(unit.margin_s for unit in split.units))
    if max_walltime_s is not None and wanted > max_walltime_s:
        short = wanted - max_walltime_s
        return (
            int(max_walltime_s),
            "max_walltime",
            False,
            float(short),
            [
                f"BEST asks {wanted // 60}m, above the cluster's max_walltime of "
                f"{_minutes(max_walltime_s)}, so the job asks the limit and is {_minutes(short)} "
                "short; a larger --batch n makes shorter jobs."
            ],
            None,
        )
    return wanted, "BEST", True, None, [], None


def job_walltime(
    split: JobSplit, estimate_s: float | None, *, max_walltime_s: float | None
) -> tuple[int | None, str, bool | None, float | None, list[str], str | None]:
    """Decide the wall clock one job asks for (FR-364, FR-377).

    Every polar BEST: the job is BEST, ``ceil(1.25 x estimate + margin)`` to the minute, capped
    at ``max_walltime_s`` with a warning that suggests a larger ``n``. Otherwise the job takes
    sum of the cells per point and each BEST row's priced estimate. A cell above
    ``max_walltime_s`` is refused; a shortfall is named only with a recorded point estimate. A job
    whose rows state nothing asks for none.

    Parameters
    ----------
    split : JobSplit
        The job's polars.
    estimate_s : float or None
        The job's estimate from :func:`job_estimate`.
    max_walltime_s : float or None
        The profile's ``max_walltime`` in seconds.

    Returns
    -------
    tuple
        ``(walltime_s, source, fits, shortfall_s, warnings, refusal)``; ``source`` is one of
        ``BEST``, ``matrix``, ``max_walltime`` and ``none``; ``refusal`` is the sentence that
        blocks the plan, or None.
    """
    if _cells_of(split):
        return _from_cells(split, estimate_s, max_walltime_s)
    if all(unit.best for unit in split.units):
        return _from_estimate(split, estimate_s, max_walltime_s)
    return None, "none", None, None, [], None
