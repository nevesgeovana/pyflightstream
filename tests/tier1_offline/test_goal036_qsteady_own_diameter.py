"""Tier 1: a quasi-steady rotor row resolves J against the rotor block's own diameter."""

from __future__ import annotations

import pytest

from pyflightstream.cases import BladeDatum, ReferenceData, RotorBlock, SimCase, SweepAxis
from pyflightstream.cases.workflows import QSTEADY_ROTOR, WORKFLOW_KEY
from pyflightstream.cases.workflows._rows import _qsteady_speed

BLOCK_DIAMETER = 2.0
TOP_LEVEL_DIAMETER = 5.0


def _case() -> SimCase:
    rotor = RotorBlock(
        alias="PROP",
        axis="X",
        diameter_m=BLOCK_DIAMETER,
        families_blades=["B1"],
        blade1=BladeDatum(azimuth_deg=0.0, zero="Y"),
    )
    return SimCase(
        sim_id="9001",
        aircraft="Prop",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe=QSTEADY_ROTOR,
        outputs=["DP.txt"],
        variables={WORKFLOW_KEY: QSTEADY_ROTOR, "VELOCITY": "30.0", "ADVANCE_RATIO": "0.5"},
        point={"alpha": 0.0},
        rotors={"PROP": rotor},
        reference=ReferenceData(area=3.14, length=0.2, rotor_diameter=TOP_LEVEL_DIAMETER),
    )


@pytest.mark.requirement("FR-192")
def test_qsteady_advance_ratio_follows_the_block_diameter():
    # P0310-J-OWN-DIAMETER
    case = _case()
    speed = _qsteady_speed(case, case.rotors["PROP"])
    # n = V / (J D) with the block's D = 2 m: 30 / (0.5 * 2) = 30 rev/s = 1800 rev/min.
    assert speed.diameter_m == pytest.approx(BLOCK_DIAMETER)
    assert speed.rpm == pytest.approx(1800.0)
    assert speed.rpm != pytest.approx(60.0 * 30.0 / (0.5 * TOP_LEVEL_DIAMETER))
