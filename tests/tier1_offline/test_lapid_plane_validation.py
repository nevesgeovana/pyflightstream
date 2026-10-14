"""Trefftz spacing must fail during planning, while a valid three-point axis stays usable.

Reproduction: a pproc requesting variant='plane', spacing_bref=2.0 builds
one probe at the release head, then fails when plane_fields needs three points.
"""

import numpy as np
import pytest

from pyflightstream.cases.workflows import build_script
from pyflightstream.farfield import plane_fields
from pyflightstream.probes import ProbeGeometryError, farfield_plane
from pyflightstream.script import Script
from tests.tier1_offline.test_p0400_farfield_plan import _case

pytestmark = pytest.mark.requirement("FR-455")


@pytest.mark.parametrize("spacing", [1.0, 2.0])
def test_collapsed_plane_is_refused_while_building(tmp_path, spacing):
    case = _case(
        tmp_path,
        {"families": "all", "trefftz": {"variant": "plane", "spacing_bref": spacing}},
    )
    with pytest.raises(ProbeGeometryError, match="at least three points") as caught:
        build_script(case, Script("26.124"))
    message = str(caught.value)
    assert "spacing" in message
    assert "half_width" in message and "half_height" in message
    assert "reduce" in message


def test_smallest_valid_plane_still_reaches_the_integrator():
    plane = farfield_plane(
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        distance=1.0,
        half_width=1.0,
        half_height=1.0,
        spacing=1.0,
    )
    assert np.array_equal(plane.y, [-1.0, 0.0, 1.0])
    assert np.array_equal(plane.z, [-1.0, 0.0, 1.0])
    samples = plane_fields(plane.y, plane.z, {"u": np.ones((3, 3))})
    assert samples["u"].shape == (3, 3)
