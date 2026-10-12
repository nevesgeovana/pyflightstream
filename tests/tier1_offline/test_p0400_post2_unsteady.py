"""P0400-FRAMES: the animation frame readers and the passage windows.

Each case is a frame the readers took wrongly at the 0.40.0 base: a Tecplot
zone whose keywords are separated by commas, a second zone, an auxiliary data
record, a truncated or ragged VECTORS block, a CELL_DATA section, and passage
windows over frames whose stride does not divide the passage.
"""

from __future__ import annotations

import numpy as np
import pytest

from pyflightstream.exceptions import IncompleteOutputError, MalformedOutputError
from pyflightstream.post import passage_windows, read_timestep_series
from pyflightstream.post.unsteady import TimestepSeries

_VARIABLES = 'VARIABLES = "X" "Y" "Z" "cp"'


def _frame(tmp_path, name: str, text: str):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_p0400_frames_comma_separated_solutiontime_orders_the_frames(tmp_path):
    """P0400-FRAMES: SOLUTIONTIME followed by a comma is read as a number."""
    frames = [
        _frame(
            tmp_path,
            f"f{i}.dat",
            f'{_VARIABLES}\nZONE T="f", I=1, SOLUTIONTIME={t}, STRANDID=1\n0 0 0 {v}\n',
        )
        for i, (t, v) in enumerate([(0.5, 2.0), (0.25, 1.0)])
    ]
    series = read_timestep_series(frames)
    assert series.times_s.tolist() == [0.25, 0.5]
    assert series.fields["cp"][:, 0].tolist() == [1.0, 2.0]


def test_p0400_frames_a_second_zone_is_refused_by_name(tmp_path):
    """P0400-FRAMES: a one-zone-per-sample file is refused as multi-zone, not as truncated."""
    text = (
        f'{_VARIABLES}\nZONE T="Sample 0", I=1, J=1, K=1\n0 0 0 1\n'
        'ZONE T="Sample 1", I=1, J=1, K=1\n1 0 0 2\n'
    )
    path = _frame(tmp_path, "zones.dat", text)
    with pytest.raises(MalformedOutputError, match="second ZONE"):
        read_timestep_series([path], order="given")


@pytest.mark.parametrize(
    "record", ['DATASETAUXDATA SOURCE = "a"', 'AUXDATA NOTE = "b"'], ids=["dataset", "zone"]
)
def test_p0400_frames_auxiliary_records_are_skipped(tmp_path, record):
    """P0400-FRAMES: an auxiliary name-value record is not read as a row."""
    text = f'{_VARIABLES}\n{record}\nZONE T="f" I=2\n0 0 0 1\n1 0 0 2\n'
    series = read_timestep_series([_frame(tmp_path, "aux.dat", text)], order="given")
    assert series.fields["cp"][0].tolist() == [1.0, 2.0]


def test_p0400_frames_a_text_line_is_a_malformed_output_naming_it(tmp_path):
    """P0400-FRAMES: a non-numeric data line raises the catalogued error, naming the line."""
    text = f'{_VARIABLES}\nZONE T="f" I=1\nDT=(SINGLE SINGLE)\n0 0 0 1\n'
    with pytest.raises(MalformedOutputError, match=r"DT=\(SINGLE SINGLE\)"):
        read_timestep_series([_frame(tmp_path, "text.dat", text)], order="given")


def _vtk(body: str) -> str:
    head = "# vtk DataFile Version 3.0\nt\nASCII\nDATASET POLYDATA\n"
    return head + "POINTS 2 float\n0 0 0\n1 0 0\nVERTICES 2 4\n1 0\n1 1\n" + body


def test_p0400_frames_a_truncated_vectors_block_is_incomplete(tmp_path):
    """P0400-FRAMES: a VECTORS block cut short is an IncompleteOutputError, not IndexError."""
    path = _frame(tmp_path, "cut.vtk", _vtk("POINT_DATA 2\nVECTORS u float\n1 2 3\n"))
    with pytest.raises(IncompleteOutputError, match="'u' block ends"):
        read_timestep_series([path], order="given")


def test_p0400_frames_a_ragged_vectors_line_is_malformed(tmp_path):
    """P0400-FRAMES: a vector line without three values is a MalformedOutputError."""
    path = _frame(tmp_path, "ragged.vtk", _vtk("POINT_DATA 2\nVECTORS u float\n1 2 3\n4 5\n"))
    with pytest.raises(MalformedOutputError, match="2 value"):
        read_timestep_series([path], order="given")


def test_p0400_frames_a_whole_vectors_block_is_read(tmp_path):
    """P0400-FRAMES control: a complete VECTORS block under POINT_DATA is read."""
    path = _frame(tmp_path, "ok.vtk", _vtk("POINT_DATA 2\nVECTORS u float\n1 2 3\n4 5 6\n"))
    series = read_timestep_series([path], order="given")
    assert series.fields["u"][0].tolist() == [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]


def test_p0400_frames_cell_data_is_refused(tmp_path):
    """P0400-FRAMES: CELL_DATA scalars are refused, not read as point samples."""
    body = "CELL_DATA 3\nSCALARS cp float 1\nLOOKUP_TABLE default\n1\n2\n3\n"
    with pytest.raises(MalformedOutputError, match="CELL_DATA"):
        read_timestep_series([_frame(tmp_path, "cells.vtk", _vtk(body))], order="given")


def test_p0400_frames_a_field_without_point_data_is_refused(tmp_path):
    """P0400-FRAMES: a SCALARS block not preceded by POINT_DATA n is refused."""
    body = "SCALARS cp float 1\nLOOKUP_TABLE default\n1\n2\n"
    with pytest.raises(MalformedOutputError, match="POINT_DATA 2"):
        read_timestep_series([_frame(tmp_path, "bare.vtk", _vtk(body))], order="given")


def _series(steps):
    steps = np.asarray(steps, dtype=int)
    return TimestepSeries(
        steps=steps,
        times_s=None,
        points=np.zeros((1, 3)),
        fields={"cp": np.zeros((len(steps), 1))},
        sources=(),
    )


@pytest.mark.parametrize(
    "steps", [[0, 3, 6, 9, 12, 15, 18], [0, 2, 3, 6, 8, 9]], ids=["stride", "uneven"]
)
def test_p0400_frames_passages_of_unequal_phases_are_refused(steps):
    """P0400-FRAMES: a stride that does not divide the passage, or uneven frames, is refused."""
    with pytest.raises(MalformedOutputError, match="different phases"):
        passage_windows(_series(steps), period_steps=4)


def test_p0400_frames_a_dividing_stride_keeps_its_windows():
    """P0400-FRAMES control: a stride dividing the passage cuts as before."""
    assert passage_windows(_series([0, 2, 4, 6, 8, 10]), period_steps=4) == [(0, 3), (4, 7)]
