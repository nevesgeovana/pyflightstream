"""Read untouched solver wake exports with point scalars and both mirror halves."""
# ruff: noqa: N999 - the assigned lane name is litB.

from pathlib import Path

import numpy as np
import pytest

from pyflightstream.results.core import MalformedOutputError
from pyflightstream.results.wake import parse_wake_export
from tests.tier1_offline.test_house_style import RECORDED_WAKE_FIXTURES, _geometry_offenses

pytestmark = pytest.mark.requirement("P0400-LITB-WAKE")
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("build", ["26124", "26125"])
def test_p0400_litb_real_wake_preserves_both_halves(build):
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


def test_p0400_litb_real_fixture_exceptions_admit_only_the_captured_bytes():
    paths = list(RECORDED_WAKE_FIXTURES)
    assert _geometry_offenses(paths) == []
    assert _geometry_offenses(paths, read=lambda path: b"replaced") == sorted(paths)
    assert _geometry_offenses(paths, read=lambda path: None) == sorted(paths)
    assert _geometry_offenses(["examples/another_wake.vtk"]) == ["examples/another_wake.vtk"]
