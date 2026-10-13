"""Release review round three, REL3-001 (FR-454 R2, FR-455 R2): an odd azimuth count.

The aliasing rule refuses a harmonic order at or above half the azimuth count,
2 m_max >= n_psi. Integer division (m_max >= n_psi // 2) refused order 6 on
13 azimuths, which the numerical core resolves, and so kept a qualifying
declared lattice from being reused.
"""

from __future__ import annotations

import pytest

from pyflightstream.cases._farfield_spec import LatticeShape, LedgersSpec
from pyflightstream.cases.workflows._farfield import plan_record
from tests.tier1_offline.test_p0400_farfield_plan import _case, _script
from tests.tier1_offline.test_p0400_rfixF_layout import _states


@pytest.mark.requirement("FR-454")
def test_p0400_rfixr3_an_order_below_half_an_odd_azimuth_count_is_accepted():
    """Order 6 on 13 azimuths is below 6.5 and is accepted; on 12 azimuths it is refused."""
    LedgersSpec(rotor="R", stations=(1.0,), n_r=2, n_psi=13, m_max=6)
    with pytest.raises(ValueError, match="n_psi = 12"):
        LedgersSpec(rotor="R", stations=(1.0,), n_r=2, n_psi=12, m_max=6)


@pytest.mark.requirement("FR-455")
def test_p0400_rfixr3_the_sole_odd_azimuth_lattice_is_reused(tmp_path):
    """A sole declared 13-azimuth lattice qualifies for order 6 and is reused, not replaced."""
    declared = {"rotor": "ROTOR", "stations": [2.0], "n_r": 2, "n_psi": 13}
    case = _case(
        tmp_path,
        {"families": "all", "ledgers": {"rotor": "ROTOR", "m_max": 6}},
        probes=[{"frame": "REFERENCE", "parameters": ["VX"], "lattices": [declared]}],
    )
    script = _script(case)
    count = LatticeShape.model_validate(declared).build(1.0).point_count
    assert len(script.probe_points) == count, "laid once, the declared entry"
    (shape,) = script.farfield_layout[-1]["shapes"]
    assert (shape["kind"], shape["source"], shape["entry"]) == ("lattice", "declared", 1)
    assert _states(plan_record(case, "26.124", script), "ledgers") == {"reused"}
