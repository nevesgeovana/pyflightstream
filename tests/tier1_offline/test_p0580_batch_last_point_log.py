"""PFS-2258 (0.58.0): the last point of a grouped job gets its log as every other point does.

Mechanism, read off the code at 12ed6f8d3. On a machine whose HPC profile
states ``export_log = false`` no point exports its log, and collect cuts every
point's log from the scheduler's own log (``native_log``, ``FTS{sim}.l*``) with
:func:`pyflightstream.results.log.split_job_log`. A segment is complete only
when a later ``Solution cleared. Initialization removed.`` line follows it, and
that line is printed by the NEXT point's ``REMOVE_INITIALIZATION`` or
``NEW_SIMULATION``. The job script ended its last point with
``CLOSE_FLIGHTSTREAM`` alone, so the last segment was never complete, and
``_batch_collect._write_log`` refused it until the job's end was proved; with
no ``job_end_files`` the last point stayed without its log while its text sat
at the end of the scheduler's log.

No real job was available to this lane. The scheduler is a stand-in that runs
the emitted job's commands in order and prints, for each, the line the solver
prints (the marker for a transition, measured on 26.124, RPT-141). No solver
runs here.
"""

from __future__ import annotations

import pytest

from pyflightstream.cases.workflows._batch_script import (
    JobPolar,
    assemble_job,
    point_transitions,
)
from pyflightstream.results.log import RESTART_MARKER, split_job_log
from tests.tier1_offline.test_p0350_batch_script import (
    BUILD,
    ROOT,
    _point,
    _same_polar,
    _without_log,
)

#: What the stand-in scheduler prints when the instance closes.
CLOSED = "FlightStream closed."


def _polars(transition: str, *, quiet: bool) -> list[JobPolar]:
    """Two points as one polar (re-initialization) or as two polars (new simulation)."""
    first, second = _same_polar()
    if transition == "refresh":
        second = _point("p9812.txt", sim="9812", folder="DP-a20")
    if quiet:
        first, second = _without_log(first), _without_log(second)
    if transition == "refresh":
        return [JobPolar("9811", (first,)), JobPolar("9812", (second,))]
    return [JobPolar("9811", (first, second))]


def _scheduler_log(text: str, targets: tuple[str, ...]) -> str:
    """The scheduler's log of a job: its commands run in order, each echoed as the solver does."""
    echo = {
        "OPEN": "Opening the geometry.",
        "INITIALIZE_SOLVER": "Following geometry is being initialized",
        "START_SOLVER": "Solver run ended.",
        "REMOVE_INITIALIZATION": RESTART_MARKER,
        "NEW_SIMULATION": RESTART_MARKER,
        "CLOSE_FLIGHTSTREAM": CLOSED,
    }
    wanted = set(targets)
    out: list[str] = []
    for line in text.splitlines():
        bare = line.strip()
        if bare in echo:
            out.append(echo[bare])
        elif bare in wanted:
            out.append(f"Exported {bare}")
    return "\n".join(out) + "\n"


@pytest.mark.parametrize("transition", ["reinit", "refresh"])
def test_p0580_pfs2258_the_last_points_scheduler_segment_ends_like_every_other(transition):
    """PFS-2258: under export_log = false every point's segment of the scheduler log is complete.

    Each point's segment holds its own exports and no other point's, and is
    closed by a marker; the last one too, without waiting for the job's end
    file. Fails at 12ed6f8d3, where the last segment ran to the close and was
    never complete, the gate that left the last point without its log.
    """
    polars = _polars(transition, quiet=True)
    job = assemble_job(polars, kind="batch", version=BUILD, job_log=None, job_dir=ROOT)
    assert "EXPORT_LOG" not in job.text
    log = _scheduler_log(job.text, job.targets)
    lines = log.splitlines()
    segments = split_job_log(log)
    points = [point for polar in polars for point in polar.points]
    assert len(segments) >= len(points)
    for order, point in enumerate(points, 1):
        segment = segments[order - 1]
        own = "\n".join(lines[segment.first_line : segment.last_line + 1])
        assert segment.complete, (order, own)
        assert f"Exported {point.datapoint_dir}/" in own, order
        others = [p for p in points if p is not point]
        assert not any(f"Exported {p.datapoint_dir}/" in own for p in others), order
        assert CLOSED not in own, order
    assert job.text.rstrip("\n").splitlines()[-1] == "CLOSE_FLIGHTSTREAM"


def test_p0580_pfs2258_a_job_whose_points_export_their_logs_keeps_the_measured_ending():
    """Control: points that export their logs end as arm A did, with no closing transition."""
    log = ROOT / "BATCH-9811-9811.job-log.txt"
    job = assemble_job(
        _polars("reinit", quiet=False), kind="batch", version=BUILD, job_log=log, job_dir=ROOT
    )
    assert job.text.endswith(f"EXPORT_LOG\n{log}\n\nCLOSE_FLIGHTSTREAM\n")
    assert job.text.count("REMOVE_INITIALIZATION") == 1


@pytest.mark.parametrize("quiet", [True, False], ids=["no-log", "log"])
@pytest.mark.parametrize(
    ("transition", "verbs"),
    [("reinit", ["REMOVE_INITIALIZATION"]), ("refresh", ["NEW_SIMULATION"])],
)
def test_p0580_pfs2258_the_closing_transition_starts_no_point(transition, verbs, quiet):
    """The transitions read off a job script, which collect's opening orders count, leave
    out the closing one: a job of two points has one, with or without the closing line."""
    job = assemble_job(
        _polars(transition, quiet=quiet), kind="batch", version=BUILD, job_log=None, job_dir=ROOT
    )
    assert point_transitions(job.text) == verbs
