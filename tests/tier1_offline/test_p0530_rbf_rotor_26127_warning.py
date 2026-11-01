"""P0530-RBF-WARNING (PFS-2185.05): RBF morphing of the unsteady rotor on 26.127 is warned.

On 26.127 the solver places an RBF-morphed turning blade at its import azimuth once a non-zero
field is written; Direct DEFLECTED is the route that keeps the blade in place. A row of that
shape is emitted as always and warned once; no other build and no direct route is warned.
"""

from __future__ import annotations

import warnings

import pytest

from pyflightstream.cases import fsi_workspace as ws
from pyflightstream.script import Script
from tests.tier1_offline.test_p0520_norefusal import messages
from tests.tier1_offline.test_p0520_norefusal_direct import _direct

FRAGMENT = "places the morphed blade at its import azimuth"


def _said(tmp_path, version: str, morphing: str, workflow: str = "unsteady_rotor") -> list[str]:
    case = _direct(tmp_path, version, morphing)
    script = Script(version)
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        ws.validate_workspace_fsi(case, script, workflow=workflow, continuation=False)
    return [m for m in messages(caught) if FRAGMENT in m]


@pytest.mark.requirement("FR-3413")
def test_p0530_an_rbf_unsteady_rotor_on_26_127_is_emitted_and_warned_once(tmp_path):
    said = _said(tmp_path, "26.127", "mapped")
    assert len(said) == 1, said
    assert "Direct DEFLECTED" in said[0] and "26.127" in said[0]


@pytest.mark.requirement("FR-3413")
def test_p0530_the_same_row_on_26_125_is_not_warned_of_the_rbf_placement(tmp_path):
    assert _said(tmp_path, "26.125", "mapped") == []


@pytest.mark.requirement("FR-3413")
@pytest.mark.parametrize("morphing", ["direct", "direct_deflected"])
def test_p0530_a_direct_route_on_26_127_is_not_warned_of_the_rbf_placement(tmp_path, morphing):
    assert _said(tmp_path, "26.127", morphing) == []
