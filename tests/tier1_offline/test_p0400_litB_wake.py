"""FR-452: the recorded signed wake and circulation reconstruction.

Read untouched solver wake exports with point scalars and both mirror halves."""
# ruff: noqa: N999 - the assigned lane name is litB.

from pathlib import Path

import numpy as np
import pytest

from pyflightstream.results.core import IncompleteOutputError, MalformedOutputError
from pyflightstream.results.wake import parse_wake_export
from tests.tier1_offline.test_house_style import RECORDED_WAKE_FIXTURES, _geometry_offenses

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.requirement("FR-17")
@pytest.mark.parametrize(
    ("cut_before", "message"),
    [
        ("# vtk", "header.*truncated"),
        ("ASCII", "header.*truncated"),
        ("DATASET", "header.*truncated"),
        ("POINTS", "POINTS.*truncated"),
        ("LINES", "LINES.*truncated"),
        ("SCALARS X", "X scalar.*truncated"),
        ("SCALARS Y", "Y scalar.*truncated"),
        ("CELL_DATA", "cell values.*truncated"),
        ("SCALARS Normalized_Vorticity", "SCALARS.*truncated"),
    ],
)
def test_p0400_litb_real_wake_truncated_at_a_block_boundary_is_incomplete(cut_before, message):
    """An empty export or a prefix of the real export cannot be a complete wake."""
    text = (FIXTURES / "p0400_litB_wake_26124.vtk").read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    cut = next(index for index, line in enumerate(lines) if line.startswith(cut_before))
    with pytest.raises(IncompleteOutputError, match=message):
        parse_wake_export("".join(lines[:cut]))


@pytest.mark.requirement("FR-452")
@pytest.mark.parametrize("build", ["26124", "26125"])
def test_p0400_litb_real_wake_preserves_both_halves(build):
    """FR-452: retain the recorded wake geometry and signed strip circulation."""
    text = (FIXTURES / f"p0400_litB_wake_{build}.vtk").read_text(encoding="utf-8")
    try:
        wake = parse_wake_export(text)
    except MalformedOutputError as error:
        pytest.fail(f"the real solver wake was refused: {error}")
    assert len(wake.lines) == 18
    starts = np.array([line[0] for line in wake.lines])
    assert np.count_nonzero(starts[:, 1] < 0) == 8
    assert np.count_nonzero(starts[:, 1] > 0) == 8
    assert np.count_nonzero(starts[:, 1] == 0) == 2
    assert all(line.shape[1] == 3 for line in wake.lines)
    collapsed = [np.ptp(line[:, 0]) == 0 for line in wake.lines]
    assert sum(collapsed) == (4 if build == "26124" else 0)
    assert np.all(wake.values[collapsed] == 0)


@pytest.mark.requirement("NFR-14")
def test_p0400_litb_real_fixture_exceptions_admit_only_the_captured_bytes():
    paths = list(RECORDED_WAKE_FIXTURES)
    assert _geometry_offenses(paths) == []
    assert _geometry_offenses(paths, read=lambda path: b"replaced") == sorted(paths)
    assert _geometry_offenses(paths, read=lambda path: None) == sorted(paths)
    assert _geometry_offenses(["examples/another_wake.vtk"]) == ["examples/another_wake.vtk"]
