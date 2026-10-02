"""The batch split, the job estimate and the BEST walltime of a grouped plan (GOAL-040, FT-PLAN).

Numbers only: the split is checked against a brute-force partition oracle, the estimate against
the formula of the design to the second, and the walltime against the worked example (3 h 05 m
and a margin of 1200 s ask 252 minutes).
"""

from __future__ import annotations

import itertools

import pytest

from pyflightstream.run._batch_split import (
    MEASURED_OVERHEADS,
    JobSplit,
    PolarUnit,
    best_walltime_s,
    job_estimate,
    job_walltime,
    split_polars,
    walltime_text,
)
from tests.tier1_offline.test_p0350_batch_plan import _fixture, _plan

HOUR = 3600.0


def _unit(
    sim: str,
    order: int,
    hours: float,
    *,
    ncpus: int = 16,
    build: str = "26.124",
    points: int = 1,
    cell_s: float | None = None,
    cell_text: str | None = None,
    best: bool = True,
    seconds: tuple[float | None, ...] | None = None,
) -> PolarUnit:
    each = hours * HOUR / points
    return PolarUnit(
        sim_id=sim,
        order=order,
        ncpus=ncpus,
        fs_build=build,
        run_ids=tuple(f"m/sim_{sim}/p{i}" for i in range(points)),
        point_seconds=seconds if seconds is not None else (each,) * points,
        walltime_cell_s=cell_s,
        walltime_cell_text=cell_text,
        best=best,
        margin_s=1200.0,
    )


def _runs_of(jobs: list[JobSplit]) -> list[list[str]]:
    return [[unit.sim_id for unit in job.units] for job in jobs]


def _oracle_longest(weights: list[float], jobs: int) -> float:
    """The smallest longest-run over EVERY contiguous partition into ``jobs`` runs."""
    best = float("inf")
    for cuts in itertools.combinations(range(1, len(weights)), jobs - 1):
        edges = [0, *cuts, len(weights)]
        longest = max(sum(weights[a:b]) for a, b in zip(edges, edges[1:], strict=False))
        best = min(best, longest)
    return best


def test_p0350_split_fr362_contiguous_whole_polars_grouped_by_ncpus() -> None:
    """P0350-BATCH-SPLIT (FR-362): groups by NCPUS, contiguous runs, whole polars, optimal.

    Units of NCPUS 16, 16, 8, 16 with estimates 1, 9, 2, 3 h and n = 3: the 8-processor polar
    is a job of its own, the 16-processor group is cut into two runs of consecutive sims whose
    longest equals the brute-force optimum. A greedy longest-first split would put 2001 and 2004
    together (the 1 h and 3 h polars, skipping 2002) and fail the contiguity assertion.
    """
    units = [
        _unit("2001", 1, 1.0),
        _unit("2002", 2, 9.0),
        _unit("2003", 3, 2.0, ncpus=8),
        _unit("2004", 4, 3.0),
    ]
    jobs, warnings = split_polars(units, 3)
    assert warnings == []
    assert len(jobs) == 3
    assert sorted(tuple(unit.ncpus for unit in job.units) for job in jobs) == [
        (8,),
        (16,),
        (16, 16),
    ]
    sixteen = [job for job in jobs if job.units[0].ncpus == 16]
    assert _runs_of(sixteen) == [["2001", "2002"], ["2004"]]
    # contiguity inside the group: the sims of a job are consecutive among their group's sims
    group = ["2001", "2002", "2004"]
    for job in sixteen:
        indexes = [group.index(unit.sim_id) for unit in job.units]
        assert indexes == list(range(indexes[0], indexes[0] + len(indexes)))
    longest = max(sum(u.point_seconds[0] or 0.0 for u in job.units) for job in sixteen)
    assert longest == _oracle_longest([1 * HOUR, 9 * HOUR, 3 * HOUR], 2)
    # a polar is whole: every sim appears once
    assert sorted(unit.sim_id for job in jobs for unit in job.units) == [
        "2001",
        "2002",
        "2003",
        "2004",
    ]


def test_p0350_split_fr362_matches_the_brute_force_oracle_on_many_shapes() -> None:
    """P0350-BATCH-SPLIT (FR-362): the longest job equals the oracle's for every n of a fixture."""
    weights = [3.0, 1.0, 4.0, 1.0, 5.0, 9.0, 2.0, 6.0]
    units = [_unit(str(2000 + i), i + 1, w) for i, w in enumerate(weights)]
    for n in range(1, len(weights) + 1):
        jobs, warnings = split_polars(units, n)
        assert warnings == []
        assert len(jobs) == n
        longest = max(sum(u.point_seconds[0] or 0.0 for u in job.units) for job in jobs)
        assert longest == _oracle_longest([w * HOUR for w in weights], n)
        flat = [unit.sim_id for job in jobs for unit in job.units]
        assert flat == [unit.sim_id for unit in units]


def test_p0350_split_fr362_n_above_the_polars_warns() -> None:
    """P0350-BATCH-SPLIT (FR-362): two polars and n = 5 give two jobs and a warning."""
    jobs, warnings = split_polars([_unit("2001", 1, 1.0), _unit("2002", 2, 2.0)], 5)
    assert len(jobs) == 2
    assert len(warnings) == 1
    assert "never cut" in warnings[0]


def test_p0350_split_fr362_n_below_the_groups_warns() -> None:
    """P0350-BATCH-SPLIT (FR-362): n below the groups of NCPUS and build plans one job per group."""
    units = [
        _unit("2001", 1, 1.0),
        _unit("2002", 2, 1.0, ncpus=8),
        _unit("2003", 3, 1.0, build="26.123"),
    ]
    jobs, warnings = split_polars(units, 1)
    assert len(jobs) == 3
    assert any("one job per group" in line for line in warnings)


def test_p0350_split_fr363_estimate_and_fallback() -> None:
    """P0350-BATCH-ESTIMATE (FR-363): T is the formula to the second; fallbacks are named.

    Two polars of 3 and 2 points: T = start + refresh x 1 + sum + reinit x (5 - 2). A point with
    no estimate takes its row's cell and is named; with neither it is unestimated and the job has
    no estimate.
    """
    first = _unit("2001", 1, 0.0, points=3, seconds=(100.0, 200.0, 300.0))
    second = _unit("2002", 2, 0.0, points=2, seconds=(400.0, 500.0))
    estimate, fallback, unestimated = job_estimate(JobSplit((first, second)), MEASURED_OVERHEADS)
    assert fallback == [] and unestimated == []
    assert estimate == 2.0 + 2.0 * 1 + 1500.0 + 0.08 * 3
    gap = _unit(
        "2003", 3, 0.0, points=2, seconds=(100.0, None), cell_s=900.0, cell_text="15m", best=False
    )
    estimate, fallback, unestimated = job_estimate(JobSplit((gap,)), MEASURED_OVERHEADS)
    assert fallback == ["m/sim_2003/p1"] and unestimated == []
    assert estimate == 2.0 + 1000.0 + 0.08 * 1
    bare = _unit("2004", 4, 0.0, points=2, seconds=(100.0, None))
    estimate, fallback, unestimated = job_estimate(JobSplit((bare,)), MEASURED_OVERHEADS)
    assert estimate is None and unestimated == ["m/sim_2004/p1"]


def test_p0350_split_fr364_best_walltime() -> None:
    """P0350-BATCH-WALLTIME (FR-364, FR-377): 3 h 05 m and a 1200 s margin ask 252 minutes."""
    assert best_walltime_s(3 * HOUR + 5 * 60, 1200.0) == 252 * 60
    assert walltime_text(252 * 60) == "252m"
    # 2026-10-02: the owner's matrices state a per-datapoint WALLTIME; the job asks the sum.
    assert walltime_text(15075) == "15075s"
    unit = _unit("2001", 1, 0.0, seconds=(3 * HOUR + 5 * 60,))
    split = JobSplit((unit,))
    seconds, source, fits, short, warnings, refusal = job_walltime(
        split, 3 * HOUR + 5 * 60, max_walltime_s=None
    )
    assert (seconds, source, fits, short, warnings, refusal) == (
        15120,
        "BEST",
        True,
        None,
        [],
        None,
    )


@pytest.mark.parametrize(("cell", "cell_s"), [("68s", 68), ("4h", 14400)])
def test_p0350_split_fr364_matrix_walltime_keeps_the_cell(tmp_path, cell, cell_s):
    """P0350-BATCH-WALLTIME (FR-364): keep the stated cell; only BEST rounds to minutes."""
    unit = _unit("2001", 1, 0.0, cell_s=cell_s, cell_text=cell, best=False)
    split = JobSplit((unit,))
    seconds, source, *_ = job_walltime(split, 68.0, max_walltime_s=None)
    assert seconds == cell_s and source == "matrix"
    # 2026-10-02: the owner's matrices state a per-datapoint WALLTIME; the job asks the sum.
    assert walltime_text(seconds, split=split) == ("68s" if cell == "68s" else "240m")
    workspace, matrix = _fixture(tmp_path, walltimes=(cell,))
    (job,) = _plan(workspace, matrix, batch=1).grouping.jobs
    assert job.walltime_written == ("204s" if cell == "68s" else "720m")
    assert job.walltime_s == 3 * cell_s
    assert job.walltime_source == "matrix"
    best = JobSplit((_unit("2001", 1, 0.0, seconds=(68.0,)),))
    rounded, source, *_ = job_walltime(best, 68.0, max_walltime_s=None)
    assert rounded == 1320 and source == "BEST"
    assert walltime_text(rounded, split=best) == "22m"


def test_p0350_split_fr364_best_above_the_maximum_warns_and_suggests_a_larger_n() -> None:
    """P0350-BATCH-WALLTIME (FR-364): BEST above max_walltime warns and asks the limit."""
    split = JobSplit((_unit("2001", 1, 0.0, seconds=(3 * HOUR,)),))
    seconds, source, fits, short, warnings, refusal = job_walltime(
        split, 3 * HOUR, max_walltime_s=2 * HOUR
    )
    assert (seconds, source, fits, refusal) == (7200, "max_walltime", False, None)
    assert short == best_walltime_s(3 * HOUR, 1200.0) - 7200
    assert len(warnings) == 1 and "larger --batch n" in warnings[0]


def test_p0350_split_fr364_a_matrix_value_is_refused_above_the_maximum_and_fitted() -> None:
    """P0350-BATCH-WALLTIME (FR-364):
    a cell above max is refused; one the estimate exceeds is named."""
    cell = _unit("2001", 1, 0.0, seconds=(HOUR,), cell_s=3 * HOUR, cell_text="3h", best=False)
    split = JobSplit((cell,))
    _, _, _, _, _, refusal = job_walltime(split, HOUR, max_walltime_s=2 * HOUR)
    assert refusal is not None and "max_walltime" in refusal and "2001" in refusal
    short_cell = _unit("2001", 1, 0.0, seconds=(2 * HOUR,), cell_s=HOUR, cell_text="1h", best=False)
    seconds, source, fits, shortfall, warnings, refusal = job_walltime(
        JobSplit((short_cell,)), 2 * HOUR, max_walltime_s=None
    )
    assert (seconds, source, fits, refusal) == (3600, "matrix", False, None)
    assert shortfall == best_walltime_s(2 * HOUR, 1200.0) - 3600
    assert "1h" in warnings[0] and "short" in warnings[0]
    # control: a cell the estimate fits is not named
    roomy = _unit("2001", 1, 0.0, seconds=(HOUR,), cell_s=3 * HOUR, cell_text="3h", best=False)
    _, _, fits_roomy, _, warns, ref = job_walltime(JobSplit((roomy,)), HOUR, max_walltime_s=None)
    assert fits_roomy is True and warns == [] and ref is None


def test_p0350_split_fr364_mixed_cells_and_unestimated_best() -> None:
    """P0350-BATCH-WALLTIME (FR-364):
    mixed cells take the smallest, named; unestimated BEST asks the limit."""
    a = _unit("2001", 1, 0.0, seconds=(HOUR,), cell_s=4 * HOUR, cell_text="4h", best=False)
    b = _unit("2002", 2, 0.0, seconds=(HOUR,), cell_s=2 * HOUR, cell_text="2h", best=False)
    seconds, source, _, _, warnings, _ = job_walltime(
        JobSplit((a, b)), 2 * HOUR, max_walltime_s=None
    )
    # 2026-10-02: the owner's matrices state a per-datapoint WALLTIME; the job asks the sum.
    assert (seconds, source) == (21600, "matrix")
    assert warnings == []
    bare = JobSplit((_unit("2003", 3, 0.0, seconds=(None,)),))
    seconds, source, _, _, warnings, refusal = job_walltime(bare, None, max_walltime_s=5 * HOUR)
    assert (seconds, source, refusal) == (18000, "max_walltime", None)
    assert "m/sim_2003/p0" in warnings[0]
    _, _, _, _, _, refusal = job_walltime(bare, None, max_walltime_s=None)
    assert refusal is not None and "m/sim_2003/p0" in refusal


def test_p0350_split_fr364_matrix_walltime_sums_points_and_caps_at_maximum() -> None:
    """P0350-BATCH-WALLTIME (FR-364): a matrix cell is per datapoint; the job asks the sum"""
    units = tuple(
        PolarUnit(
            sim_id=sim,
            order=order,
            ncpus=16,
            fs_build="26.124",
            run_ids=tuple(f"m/sim_{sim}/p{i}" for i in range(points)),
            point_seconds=(HOUR,) * points,
            walltime_cell_s=hours * HOUR,
            walltime_cell_text=f"{hours}h",
            best=False,
            margin_s=1200.0,
        )
        for order, sim, points, hours in ((1, "2001", 3, 4), (2, "2002", 2, 2))
    )
    split = JobSplit(units)
    seconds, source, fits, shortfall, warnings, refusal = job_walltime(
        split, 5 * HOUR, max_walltime_s=None
    )
    assert (seconds, source, fits, shortfall, warnings, refusal) == (
        57600,
        "matrix",
        True,
        None,
        [],
        None,
    )
    assert walltime_text(seconds, split=split) == "960m"
    seconds, source, fits, shortfall, warnings, refusal = job_walltime(
        split, 5 * HOUR, max_walltime_s=10 * HOUR
    )
    assert (seconds, source, fits, shortfall, refusal) == (36000, "max_walltime", False, None, None)
    assert walltime_text(seconds, split=split) == "600m"
    assert len(warnings) == 1
    assert "max_walltime" in warnings[0] and "larger --batch n" in warnings[0]
