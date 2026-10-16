"""Tier 1, 0.42.0 P2-1b: the trailing-edge file route and raw-mesh rows in a non-metre setup.

Pipeline role: guards on the trailing-edge sidecar reader and the plan (FR-42, NFR-01a); the
conversion of the file route is pinned in test_raw_mesh_conditions.
"""

from __future__ import annotations

import pytest

from pyflightstream.cases.mesh import TrailingEdgeMarking
from pyflightstream.workspace.sidecars import read_trailing_edges


def test_p0420_the_tolerance_is_stated_in_metres_in_all_three_places(tmp_path):
    """PFS-2130.013: the glossary, the docstring and the refusal all say metres."""
    from pyflightstream.workspace import sidecars

    assert "tolerance = 0.0001        # optional, in metres" in str(
        sidecars.read_raw_mesh_conditions.__doc__
    )
    with pytest.raises(Exception, match=r"tolerance = 'x'.*in metres"):
        read_trailing_edges(tmp_path / "a.boundaries.toml", {"file": "a.te.txt", "tolerance": "x"})
    with pytest.raises(ValueError, match=r"in metres"):
        TrailingEdgeMarking(route="file", points_file="a", points_m=((0, 0, 0),), tolerance=-1.0)
    key = sidecars.RAW_MESH_CONDITION_KEYS[sidecars.TRAILING_EDGES_TABLE]["tolerance"]
    assert key.values.startswith("m, > 0")


# ---------------------------------------------------------------- PFS-2127.003


def _plan(tmp_path, case):
    import sys
    import warnings

    from pyflightstream.cases import Campaign
    from pyflightstream.cases.workflows import build_script
    from pyflightstream.exceptions import PyflightstreamWarning
    from pyflightstream.run import PlanStatus, plan_campaign
    from pyflightstream.workspace import CampaignWorkspace

    campaign = Campaign(name="camp", fs_version="26.124", fs_exe=sys.executable, sims=[case])
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        plan = plan_campaign(
            campaign,
            CampaignWorkspace(tmp_path / "camp"),
            recipes={case.recipe: build_script},
            write_plan=False,
        )
    assert plan.points[0].status is PlanStatus.READY
    return [
        str(w.message)
        for w in seen
        if issubclass(w.category, PyflightstreamWarning) and "opens no geometry" in str(w.message)
    ]


def test_p0420_a_workflow_row_naming_no_geometry_is_warned_at_plan_not_refused(tmp_path):
    """PFS-2127.003: warn once, name the row and the remedy; an empty GEOMETRY: key is silent."""
    from tests.tier1_offline.test_surface_exports import _case

    case = _case(rotor=True)
    assert case.geometry is None and "GEOMETRY" not in case.variables
    said = _plan(tmp_path / "a", case)
    assert len(said) == 1 and repr(case.sim_id) in said[0] and "GEOMETRY" in said[0]
    declared = case.model_copy(update={"variables": {**case.variables, "GEOMETRY": ""}})
    assert _plan(tmp_path / "b", declared) == []
