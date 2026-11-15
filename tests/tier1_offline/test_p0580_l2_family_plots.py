"""An unsteady row plots the six components of every family (PFS-2231, lane L2).

THE REQUIREMENT (design of the post outputs, section 4.8). An unsteady or unsteady
rotor row always declares one MRP_<family> force plot group, FX to MZ, for every
family of the opened inventory, in the global MRP frame, whether or not the pproc
asks, so the FAM files never depend on a declaration.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.parametrize((), [pytest.param(id="P0580-L2-FAMILY-PLOTS")])


def test_an_unsteady_row_plots_the_six_components_of_every_family_in_the_global_frame(tmp_path):
    """Design section 4.8: the FAM files never depend on a pproc declaration."""
    from tests.tier1_offline.test_goal028_rotor_plot_group import SIX, _case, _plots
    from tests.tier1_offline.test_rotor_by_alias import rendered

    text = rendered(_case(tmp_path, {"parameters": ["CL"]}))
    plots = _plots(text)
    families = sorted(
        {name.split("_MRP_", 1)[1] for name in plots if "_MRP_" in name and name != "FX_MRP_TOTAL"}
        - {"TOTAL"}
    )
    assert families, sorted(plots)
    for family in families:
        for part in SIX:
            block = plots.get(f"{part}_MRP_{family}")
            assert block is not None, (family, part)
            assert block["BOUNDARIES"] == "1", block
            assert block["FRAME"] == plots["FX_MRP_TOTAL"]["FRAME"]
