"""Tier 1: a setup family list reads each name as every cited name is read (0.40.0)."""

import pytest

from pyflightstream.cases import SimCase, SolverSettings, SweepAxis
from pyflightstream.cases._setup_link import family_indices
from pyflightstream.script import Script


@pytest.mark.parametrize(
    ("families", "expected"),
    [
        (["Hub", "Blade"], [1, 2, 3]),
        (["Hub", "blade1"], [1, 2, 3]),
        (["Blade"], [2, 3]),
        (["Hub", "rotor"], [1, 2, 3]),
    ],
)
def test_p0400_family_word_alias_and_case_variant_select_every_member(families, expected):
    """P0400-SETUP-FAMILIES (PFS-2104.028): no name of the list is dropped in silence."""
    case = SimCase(
        sim_id="9001",
        aircraft="Rotor",
        recipe="steady",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        solver=SolverSettings(analysis_families=families),
        aliases={"rotor": ["Blade"]},
    )
    script = Script("26.124")
    script.declare_existing(boundaries={"Hub": 1, "Blade1": 2, "Blade2": 3})
    indices = family_indices(
        case,
        script,
        case.solver.analysis_families,
        keyword="analysis_boundaries",
        preset_key="analysis_families",
        dropped="every boundary is analysed",
    )
    assert indices == expected
