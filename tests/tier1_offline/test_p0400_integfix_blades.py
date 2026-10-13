"""P0400-INTEGFIX-BLADES: a one-blade sector stated as periodic copies stays a valid row.

PFS-2104.011 made the rotor block the blade count and refused a ``BLADES`` that
disagrees with it. A mesh that carries ONE blade family, with the row's
``PERIODIC_COPIES`` supplying the wheel (the committed study reference says so
in its own words), states ``BLADES: 6`` beside ``PERIODIC_COPIES: 6``: that is
the same rotor counted two ways, and it was refused.
"""

from __future__ import annotations

import pytest

from pyflightstream.cases import (
    BladeDatum,
    CampaignConfigError,
    RotorBlock,
    SimCase,
    SweepAxis,
)
from pyflightstream.cases.workflows._reductions import _blade_count

_ONE_FAMILY = RotorBlock(
    alias="ROTOR",
    x_m=0.0,
    y_m=0.0,
    z_m=0.0,
    axis="X",
    diameter_m=1.0,
    families_general=[],
    families_blades=["Blade1"],
    blade1=BladeDatum(azimuth_deg=0.0, zero="Y"),
)


def _row(**stated: str) -> SimCase:
    variables = {"WORKFLOW": "unsteady_rotor", "ROTOR_AXIS": "X", "RPM": "600", **stated}
    return SimCase(
        sim_id="7001",
        aircraft="RotorRig",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="unsteady_rotor",
        variables=variables,
        point={"alpha": 0.0},
        rotors={"ROTOR": _ONE_FAMILY},
    )


def test_p0400_integfix_blades_one_family_times_the_copies_is_the_stated_count():
    """P0400-INTEGFIX-BLADES (PFS-2104.011): families x copies equal to BLADES agrees."""
    row = _row(SYMMETRY="PERIODIC", PERIODIC_COPIES="6", BLADES="6")
    assert _blade_count(row) == 6


def test_p0400_integfix_blades_a_count_that_the_copies_do_not_explain_is_still_refused():
    """P0400-INTEGFIX-BLADES (PFS-2104.011): BLADES 5 beside one family and six copies."""
    with pytest.raises(CampaignConfigError, match=r"BLADES: 5 .* 1 blade"):
        _blade_count(_row(SYMMETRY="PERIODIC", PERIODIC_COPIES="6", BLADES="5"))
    with pytest.raises(CampaignConfigError, match=r"BLADES: 6 .* 1 blade"):
        _blade_count(_row(BLADES="6"))
