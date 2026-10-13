"""P0400-WSTE: trailing-edge extraction takes any integer section count (0.40.0 lane workspace-1).

Each test is the regression of one planning node and fails on the code before its fix.
"""

from __future__ import annotations

import numpy
import pytest

from pyflightstream.workspace.inputs import InputArtifactError
from pyflightstream.workspace.trailing_edges import extract_trailing_edge
from tests.tier1_offline.test_trailing_edges import _blade_file

pytestmark = pytest.mark.requirement("P0400-WSTE")

AXIS, HUB = (0.0, 0.0, 1.0), (0.0, 0.0, 0.0)


@pytest.mark.parametrize("count", [numpy.int64(8), numpy.int32(8), 8])
def test_p0400_wste_a_numpy_integer_section_count_is_an_integer(tmp_path, count):
    """P0400-WSTE (PFS-2095.061): numpy.int64(8) sections the span as 8 does."""
    path, _, _ = _blade_file(tmp_path)
    edge = extract_trailing_edge(path, axis=AXIS, hub=HUB, sections=count)
    assert edge.nodes.shape == (8, 3)


@pytest.mark.parametrize("count", [True, numpy.bool_(True), 8.0, 1])
def test_p0400_wste_a_boolean_float_or_single_count_is_still_refused(tmp_path, count):
    """P0400-WSTE (PFS-2095.061): the bool exclusion and the two-or-more floor stay."""
    path, _, _ = _blade_file(tmp_path)
    with pytest.raises(InputArtifactError, match="chordwise sections"):
        extract_trailing_edge(path, axis=AXIS, hub=HUB, sections=count)
