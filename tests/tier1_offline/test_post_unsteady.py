"""Tier 1: the per-timestep reader and the blade-passage average.

Pipeline role: quality gate on PFS-2015.01, the two capabilities
``post/__init__.py`` advertised for three releases without having them.

THE REPRODUCTION. Before 2026-08-19 the post layer's own module
docstring said it "performs blade-passage averaging for unsteady runs",
and::

    from pyflightstream.post import blade_passage_average

raised ``ImportError``. Nothing in the layer read the per-timestep field
export either, although ``UNSTEADY_SOLVER_ANIMATION`` is a documented
command on every registered build.

THE FIXTURES ARE THIS PACKAGE'S OWN WRITERS, deliberately. No sample of
the vendor's animation export exists anywhere in this repository, and
inventing one would make the reader's tests agree with a guess. What the
command's own database entry does say is that its two data filetypes are
``TECPLOT_DATA`` and ``PARAVIEW_VTK`` (SRC-003 pp.347-348), and this
package writes both, so the frames these tests read are written by
``post.writers`` and the reader is held to a real round trip. What that
does NOT establish is how the solver NAMES the frames, which is why the
reader refuses to guess an order.
"""

from __future__ import annotations

import numpy as np
import pytest

from pyflightstream.exceptions import (
    IncompleteOutputError,
    MalformedOutputError,
    OutputExistsError,
    WorkspaceError,
)
from pyflightstream.post import (
    OutputProvenance,
    blade_passage_average,
    passage_windows,
    read_timestep_series,
    write_reduction,
    write_series,
)
from pyflightstream.post.writers import write_tecplot_points, write_vtk_points
from pyflightstream.script import Script, helpers

POINTS = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])


def provenance() -> OutputProvenance:
    script = Script(version="26.120")
    return OutputProvenance(
        run_id="rotor/sim_1/a+00.0",
        campaign="rotor",
        setup=helpers.solver_settings(script, velocity=30.0),
    )


def write_frames(folder, values, *, tecplot=True, solution_times=None):
    """Write one frame per value, through this package's own writers.

    ``values`` is one scalar per frame, broadcast over both probes, so a
    reduction's arithmetic is readable by eye.
    """
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for index, value in enumerate(values):
        fields = {"cp": np.array([value, value + 0.5])}
        name = f"frame_{index:03d}"
        if tecplot:
            zone = "probes"
            if solution_times is not None:
                zone = f"probes SOLUTIONTIME={solution_times[index]}"
            path, _record = write_tecplot_points(
                folder / f"{name}.dat", POINTS, fields, provenance=provenance(), zone=zone
            )
        else:
            path, _record = write_vtk_points(
                folder / f"{name}.vtk", POINTS, fields, provenance=provenance()
            )
        written.append(path)
    return written


# --- the reader -------------------------------------------------------------


def test_the_reader_takes_the_order_the_caller_declares(tmp_path):
    """A declared order is evidence; a filename pattern is not.

    ``frequency`` is counted in solver steps (SRC-003 pp.347-348), so
    the step axis is frame index times frequency and the reader never
    reads a step out of a file name.
    """
    frames = write_frames(tmp_path / "anim", [1.0, 2.0, 3.0, 4.0])
    series = read_timestep_series(frames, order="given", frequency=5)

    assert series.n_frames == 4
    assert series.steps.tolist() == [0, 5, 10, 15]
    assert series.order_evidence == "given"
    assert series.fields["cp"].shape == (4, 2)
    assert series.fields["cp"][:, 0].tolist() == [1.0, 2.0, 3.0, 4.0]
    assert series.points.shape == (2, 3)


def test_the_reader_orders_by_the_solution_time_each_frame_carries(tmp_path):
    """Order from the frame's OWN header, not from its name.

    The frames are handed over shuffled and come back in solution-time
    order, so nothing here could have come from the file names.
    """
    frames = write_frames(tmp_path / "anim", [1.0, 2.0, 3.0], solution_times=[0.2, 0.0, 0.1])
    shuffled = [frames[0], frames[1], frames[2]]
    series = read_timestep_series(shuffled)

    assert series.order_evidence == "solution time"
    assert series.times_s.tolist() == [0.0, 0.1, 0.2]
    assert series.fields["cp"][:, 0].tolist() == [2.0, 3.0, 1.0]


def test_the_reader_refuses_when_no_frame_carries_its_order(tmp_path):
    """The refusal names what it would take to settle the naming.

    A reader that fell back to sorting file names would be inventing the
    vendor's convention, and an animation read in the wrong order
    produces a plausible average of the wrong thing.
    """
    frames = write_frames(tmp_path / "anim", [1.0, 2.0], tecplot=False)

    with pytest.raises(MalformedOutputError) as refused:
        read_timestep_series(frames)

    message = str(refused.value)
    assert "order" in message
    assert "licensed" in message and "probe report" in message, (
        "the refusal must say what would settle it, or the next reader guesses again"
    )
    assert "order='given'" in message, "the refusal must name the way through"


def test_the_reader_refuses_a_frame_whose_fields_do_not_match_the_first(tmp_path):
    """A series is one quantity over time, or it is not a series."""
    folder = tmp_path / "anim"
    frames = write_frames(folder, [1.0, 2.0])
    odd, _record = write_tecplot_points(
        folder / "frame_odd.dat",
        POINTS,
        {"other": np.array([1.0, 2.0])},
        provenance=provenance(),
    )

    with pytest.raises(MalformedOutputError, match="other"):
        read_timestep_series([*frames, odd], order="given")


def test_the_reader_reads_vtk_frames_too(tmp_path):
    """Both data filetypes the command documents, not just one."""
    frames = write_frames(tmp_path / "anim", [1.0, 2.0, 3.0], tecplot=False)
    series = read_timestep_series(frames, order="given")
    assert series.fields["cp"][:, 0].tolist() == [1.0, 2.0, 3.0]


# --- the average ------------------------------------------------------------


@pytest.mark.parametrize(
    ("tecplot", "cut_to", "expected"),
    [
        # Cut after the point block: the declared count is unmet and the
        # frame carried no field at all, and the reader returned it.
        (False, 6, "POINTS"),
        # Cut inside a field block: this raised a BARE IndexError out of a
        # public function, which `except PyflightstreamError` does not
        # catch and which the FR-39 walk does not see.
        (False, 12, "block"),
        # Tecplot cut mid-table: the zone's own I= was never read, so a
        # short frame came back short.
        (True, 4, "I="),
    ],
)
def test_a_truncated_frame_is_refused_rather_than_returned_short(
    tmp_path, tecplot, cut_to, expected
):
    """The worst shape this reader can produce, and it produced three.

    A history one step short is worse than no history: every reduction
    downstream averages over whatever it was handed, and the average of a
    run that did not finish writing looks exactly like an average. All
    three truncations below were measured returning silently, or raising
    a bare standard-library error, before 2026-08-19.
    """
    folder = tmp_path / "frames"
    written = write_frames(folder, [1.0, 2.0], tecplot=tecplot)
    lines = written[0].read_text(encoding="utf-8").splitlines()
    assert len(lines) > cut_to, (
        f"the fixture is shorter than the cut, so this case truncates nothing: "
        f"{len(lines)} line(s), cutting to {cut_to}"
    )
    written[0].write_text("\n".join(lines[:cut_to]) + "\n", encoding="utf-8")

    with pytest.raises(IncompleteOutputError) as refused:
        read_timestep_series(written, order="given")
    assert expected in str(refused.value), (
        f"the refusal does not name what it measured; got {refused.value!r}"
    )


def test_the_blade_passage_average_averages_the_declared_window(tmp_path):
    """A window in solver steps, inclusive at both ends.

    Frames 1 to 3 hold cp = 2, 3, 4 at the first probe, so the mean is
    3, and the frame outside the window must not reach it.
    """
    frames = write_frames(tmp_path / "anim", [1.0, 2.0, 3.0, 4.0])
    series = read_timestep_series(frames, order="given", frequency=1)

    average = blade_passage_average(series, window=(1, 3))

    assert average.n_frames == 3
    assert average.window == (1, 3)
    assert average.fields["cp"][0] == pytest.approx(3.0)
    assert average.fields["cp"][1] == pytest.approx(3.5)


def test_the_average_refuses_a_window_holding_no_frame(tmp_path):
    """An average of nothing is a number, which is the danger."""
    frames = write_frames(tmp_path / "anim", [1.0, 2.0])
    series = read_timestep_series(frames, order="given")

    with pytest.raises(MalformedOutputError, match="no frame"):
        blade_passage_average(series, window=(40, 50))


def test_passage_windows_are_the_only_route_to_a_phase_locked_reduction(tmp_path):
    """One implementation of the average, composed rather than copied.

    PFS-2015.01 requires that no second blade-passage average exist in
    the release, so the successive passages are handed out as WINDOWS
    and each is reduced by the same function.
    """
    frames = write_frames(tmp_path / "anim", [1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    series = read_timestep_series(frames, order="given")

    windows = passage_windows(series, period_steps=2)
    assert windows == [(0, 1), (2, 3), (4, 5)]

    means = [blade_passage_average(series, window=w).fields["cp"][0] for w in windows]
    assert means == pytest.approx([1.5, 3.5, 5.5])


# --- her file rule ----------------------------------------------------------


def test_the_series_writer_refuses_an_existing_destination(tmp_path):
    """The fourth decorative refusal, and it was the newest.

    The lane found the same shape in three writers this release and then
    wrote a fourth without a case: deleting `write_series`'s
    `_refuse_existing` call left the whole suite green, measured by a QA
    pass on 2026-08-19. A refusal nothing drives is a comment.
    """
    frames = write_frames(tmp_path / "anim", [1.0, 2.0])
    series = read_timestep_series(frames, order="given")
    destination = tmp_path / "anim" / "series.csv"
    write_series(destination, series)
    first = destination.read_text(encoding="utf-8")

    with pytest.raises(OutputExistsError, match="already exists"):
        write_series(destination, series)
    assert destination.read_text(encoding="utf-8") == first, (
        "a refused write still changed the file"
    )


def test_the_series_writer_replaces_when_asked_deliberately(tmp_path):
    """The control, so the refusal is a guard and not a removed feature."""
    frames = write_frames(tmp_path / "anim", [1.0, 2.0])
    series = read_timestep_series(frames, order="given")
    destination = tmp_path / "anim" / "series.csv"
    write_series(destination, series)

    longer = read_timestep_series(write_frames(tmp_path / "anim2", [1.0, 2.0, 3.0]), order="given")
    write_series(destination, longer, overwrite=True)
    # One header plus one row per STEP: the file is a history, so a
    # frame contributes a row and its points contribute columns.
    assert len(destination.read_text(encoding="utf-8").strip().splitlines()) == 1 + 3


def test_the_series_writer_refuses_a_destination_it_read_from(tmp_path):
    """Her rule again, on the series half rather than the reduction half."""
    frames = write_frames(tmp_path / "anim", [1.0, 2.0])
    series = read_timestep_series(frames, order="given")

    with pytest.raises(WorkspaceError, match="READ from"):
        write_series(frames[0], series, overwrite=True)
    assert frames[0].read_text(encoding="utf-8").startswith("TITLE")


def test_a_reduction_never_overwrites_a_file_it_read(tmp_path):
    """Her rule of 2026-08-16, enforced at the writing seam.

    The average is pure, so nothing about it could enforce this; the
    writer is the only place a destination and a source are both in
    hand.
    """
    frames = write_frames(tmp_path / "anim", [1.0, 2.0])
    series = read_timestep_series(frames, order="given")
    average = blade_passage_average(series, window=(0, 1))
    series_file = write_series(tmp_path / "anim" / "series.csv", series)

    with pytest.raises(WorkspaceError, match="READ from"):
        write_reduction(frames[0], average, series_file=series_file, sources=frames)

    assert frames[0].read_text(encoding="utf-8").startswith("TITLE")


def test_a_reduction_refuses_to_be_written_with_no_series_beside_it(tmp_path):
    """The other half of her rule: the history keeps its own file.

    An average with no series next to it is a number nobody can audit,
    and the rule holds however the reduction is reached, so it lives
    here rather than in a workflow that a direct caller bypasses.
    """
    frames = write_frames(tmp_path / "anim", [1.0, 2.0])
    series = read_timestep_series(frames, order="given")
    average = blade_passage_average(series, window=(0, 1))
    elsewhere = write_series(tmp_path / "other" / "series.csv", series)

    with pytest.raises(WorkspaceError, match="beside"):
        write_reduction(
            tmp_path / "anim" / "mean.csv", average, series_file=elsewhere, sources=frames
        )

    assert not (tmp_path / "anim" / "mean.csv").exists()


def test_the_pair_a_caller_gets_when_the_rule_is_kept(tmp_path):
    """The ordinary case: series first, reduction beside it."""
    frames = write_frames(tmp_path / "anim", [1.0, 2.0, 3.0, 4.0])
    series = read_timestep_series(frames, order="given")
    average = blade_passage_average(series, window=(0, 3))

    series_file = write_series(tmp_path / "out" / "series.csv", series)
    reduction = write_reduction(
        tmp_path / "out" / "mean.csv", average, series_file=series_file, sources=frames
    )

    rows = series_file.read_text(encoding="utf-8").splitlines()
    assert rows[0].startswith("step,")
    assert len(rows) == 5, "the series file must hold one row per frame plus its header"

    mean_rows = reduction.read_text(encoding="utf-8").splitlines()
    assert mean_rows[0] == "field,probe,mean"
    assert any(row.startswith("cp,0,2.5") for row in mean_rows)


def test_a_reduction_refuses_an_existing_destination(tmp_path):
    """The overwrite rule of PFS-2011.02 reaches this writer too."""
    from pyflightstream.exceptions import OutputExistsError

    frames = write_frames(tmp_path / "anim", [1.0, 2.0])
    series = read_timestep_series(frames, order="given")
    average = blade_passage_average(series, window=(0, 1))
    series_file = write_series(tmp_path / "out" / "series.csv", series)
    write_reduction(tmp_path / "out" / "mean.csv", average, series_file=series_file)

    with pytest.raises(OutputExistsError, match="already exists"):
        write_reduction(tmp_path / "out" / "mean.csv", average, series_file=series_file)


# --- the docstring stops advertising what does not exist --------------------


DISCLAIMER = "WHAT THIS LAYER DOES NOT HAVE"


def test_the_layer_docstring_promises_only_what_it_has():
    """Every promise implemented or REMOVED, which is the acceptance.

    Measured rather than read: every name the docstring puts in double
    backticks has to be either something the layer actually exposes, or
    something it names after saying, in its own words, that it does not
    have it. The old docstring failed both ways at once, announcing
    ``interp_along``, ``reparametrize`` and ``trim`` as merely planned in
    a sentence a reader takes as a feature list.
    """
    import re as _re

    import pyflightstream.post as post

    text = post.__doc__ or ""
    assert DISCLAIMER in text, (
        "the docstring carries no section saying what the layer does NOT have, so any "
        "name in it reads as shipping"
    )
    head, tail = text.split(DISCLAIMER, 1)
    exposed = set(dir(post))
    promised = [
        name for name in _re.findall(r"``([A-Za-z_][A-Za-z0-9_]*)``", head) if name not in exposed
    ]
    assert not promised, (
        f"the docstring advertises {promised} before it says what the layer does not "
        f"have, and none of them is exposed; the layer must implement the promise or "
        "move it below the disclaimer"
    )
    for retired in ("interp_along", "reparametrize", "trim", "ResultArray"):
        assert retired not in head, f"{retired} is still advertised as if it shipped"
        assert retired in tail, (
            f"{retired} vanished from the docstring entirely; a reader who came looking "
            "for it now finds silence, which reads as an oversight rather than a decision"
        )
    assert "blade_passage_average" in exposed
