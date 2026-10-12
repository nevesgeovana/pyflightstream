"""Results regressions for 0.40.0."""

import numpy as np
import pytest

from pyflightstream.results import VtkSurface

pytestmark = pytest.mark.requirement("P0400-RESULTS-SURFACE")


def _strip(cells: int) -> VtkSurface:
    """A strip of ``cells`` triangles over ``cells + 2`` nodes."""
    connectivity = np.array(
        [node for cell in range(cells) for node in (cell, cell + 1, cell + 2)], dtype=np.int64
    )
    return VtkSurface(
        points=np.zeros((cells + 2, 3)),
        offsets=np.arange(0, 3 * cells + 1, 3, dtype=np.int64),
        connectivity=connectivity,
    )


def test_p0400_results_topology_differs_is_linear_in_the_polygons(monkeypatch):
    """P0400-RESULTS (PFS-2101.002): np.diff runs a fixed number of times, not once per polygon."""
    mine, theirs = _strip(400), _strip(400)
    theirs.connectivity[-1] = 0  # the last polygon joins another node
    calls = []
    original = np.diff

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(np, "diff", counted)
    assert mine.topology_differs(theirs) == "polygon 400 joins other nodes"
    assert len(calls) <= 2, f"np.diff ran {len(calls)} times for 400 polygons"
