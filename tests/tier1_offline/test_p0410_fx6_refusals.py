"""Refusals describe supported remedies and retain only live catalog entries."""

import pytest

from pyflightstream import _deprecations
from pyflightstream.cases import SimCase, SweepAxis
from pyflightstream.cases.workflows import build_script
from pyflightstream.script import Script


def test_p0410_shedding_refusal_names_the_distinct_ccs_route():
    case = SimCase(
        sim_id="7001",
        aircraft="RotorRig",
        recipe="unsteady_rotor",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        variables={"ROTOR_SHEDDING": "AZIMUTH"},
    )
    with pytest.raises(ValueError) as caught:
        build_script(case, Script(version="26.124"))
    message = str(caught.value)
    assert "7001" in message and "AZIMUTH" in message
    assert "CCS_SHEDDING" in message
    assert "planned for" not in message


def test_p0410_refusal_catalog_contains_only_live_refusals():
    assert set(_deprecations.REFUSED_IN_0_15_0) == {
        _deprecations.ROW_MOVING_BOUNDARIES,
        _deprecations.ROW_ROTATE_FAMILIES,
        _deprecations.ROW_EACH_BLADE,
        _deprecations.ROW_AIRFRAME_SELECTOR,
        _deprecations.ROW_BLADES_SELECTOR,
    }
