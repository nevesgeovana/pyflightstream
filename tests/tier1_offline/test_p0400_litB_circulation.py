"""FR-452: the recorded signed wake and circulation reconstruction.

The fine real wake gives unit lift scale and the independent Trefftz A efficiency."""
# ruff: noqa: N999 - the assigned lane name is litB.

import numpy as np
import pytest

from pyflightstream.farfield import WakeTrace, trace_forces
from tests.tier1_offline.test_p0400_litB_post import post_wake


@pytest.mark.requirement("FR-452")
def test_p0400_litb_shed_circulation_agrees_with_the_recorded_sections(tmp_path):
    row, messages, skipped = post_wake(tmp_path, "p0400_litB_wake_26125_fine.vtk.xz")
    assert not skipped, messages
    # Recorded L5, 4 deg: raw CL / near CL = 1.0169, A efficiency = 0.992.
    assert 1.0 / float(row["GAMMA_SCALE"]) == pytest.approx(1.0169, rel=0.003)
    assert float(row["E_T"]) == pytest.approx(0.992, abs=0.03)


@pytest.mark.requirement("FR-452")
def test_p0400_litb_signed_full_sheet_reconstructs_the_strip_loading():
    """FR-452: retain the recorded wake geometry and signed strip circulation."""
    edges = np.arange(-2.0, 3.0)
    gamma = np.array([1.0, 2.0, 2.0, 1.0])
    shed = -np.diff(np.r_[0.0, gamma, 0.0])
    trace = WakeTrace(edges, np.zeros(5), shed, 0, None)
    b = trace.forces(rho=1.2, v_inf=30.0)
    a = trace_forces(edges[:-1] + 0.5, np.zeros(4), gamma, rho=1.2, v_inf=30.0)
    assert b.gamma.tolist() == gamma.tolist()
    assert b.lift == pytest.approx(a.lift)
    assert b.induced_drag == pytest.approx(a.induced_drag)


@pytest.mark.requirement("FR-452")
def test_p0400_litb_either_mirror_half_gives_the_same_forces():
    negative = WakeTrace(
        np.array([-3.0, -2.0, -1.0]), np.zeros(3), np.array([-1.0, -0.5, -0.25]), 0, None
    )
    positive = WakeTrace(-negative.y[::-1], negative.z[::-1], negative.values[::-1], 0, None)
    left = negative.forces(rho=1.2, v_inf=30.0, mirror=True)
    right = positive.forces(rho=1.2, v_inf=30.0, mirror=True)
    assert left.lift == pytest.approx(right.lift)
    assert left.induced_drag == pytest.approx(right.induced_drag)
