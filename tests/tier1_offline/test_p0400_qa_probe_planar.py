"""P0400-PROBEPLAN: the planned-probe contract on degenerate arrays, and the axis spacing bound.

PFS-2095.022: verify_positions refuses non-finite rows, accepts an empty plan
against an empty export, and an empty plan survives its json round trip.
PFS-2104.016: a uniform axis never delivers an element larger than requested.
"""

from __future__ import annotations

import numpy as np
import pytest

from pyflightstream.probes import (
    AxisSpec,
    FrameDefinition,
    GeometryGateReport,
    PlanarProbeGrid,
    PlannedProbes,
)
from pyflightstream.probes.errors import ProbeGeometryError


def _plan(points: np.ndarray) -> PlannedProbes:
    grid = PlanarProbeGrid(
        frame=FrameDefinition(x_axis=(1.0, 0.0, 0.0), y_axis=(0.0, 1.0, 0.0)),
        u=AxisSpec(start=0.0, stop=1.0, count=2),
        v=AxisSpec(start=0.0, stop=1.0, count=2),
    )
    report = GeometryGateReport(
        base_total=4, base_culled=4 - len(points), refined_added=0, refined_culled=0
    )
    return PlannedProbes(grid=grid, points=points, report=report)


PLACED = np.array([[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0]])


def test_p0400_probeplan_one_nan_row_is_refused_and_named():
    """P0400-PROBEPLAN (PFS-2095.022) a NaN row never passes the tolerance check."""
    exported = PLACED.copy()
    exported[2, 1] = np.nan
    with pytest.raises(ProbeGeometryError, match="row 2"):
        _plan(PLACED).verify_positions(exported)


def test_p0400_probeplan_an_all_nan_export_is_refused():
    """P0400-PROBEPLAN (PFS-2095.022) an export of NaN only is refused, not accepted."""
    with pytest.raises(ProbeGeometryError, match="4 of 4"):
        _plan(PLACED).verify_positions(np.full_like(PLACED, np.nan))


def test_p0400_probeplan_an_empty_plan_matches_an_empty_export_after_a_round_trip():
    """P0400-PROBEPLAN (PFS-2095.022) every node culled: no argmax crash, shape kept on reload."""
    empty = _plan(np.empty((0, 3)))
    empty.verify_positions(np.empty((0, 3)))
    reloaded = PlannedProbes.from_json(empty.to_json())
    assert reloaded.points.shape == (0, 3)
    reloaded.verify_positions(np.empty((0, 3)))


@pytest.mark.parametrize(
    ("spacing", "cells"),
    [(0.7, 2), (0.4, 3), (0.5, 2), (0.1, 10), (1.5, 1)],
)
def test_p0400_probeplan_spacing_never_exceeds_the_request(spacing, cells):
    """P0400-PROBEPLAN (PFS-2104.016) the snapped element size is at most the requested one."""
    points = AxisSpec(start=0.0, stop=1.0, spacing=spacing).points()
    assert len(points) - 1 == cells
    assert float(np.max(np.diff(points))) <= min(spacing, 1.0) + 1e-12


def test_p0400_probeplan_an_exact_fit_is_not_split_by_float_noise():
    """P0400-PROBEPLAN (PFS-2104.016) 1.1 / 0.1 is 11.000000000000002 and stays 11 cells."""
    assert len(AxisSpec(start=0.0, stop=1.1, spacing=0.1).points()) == 12
