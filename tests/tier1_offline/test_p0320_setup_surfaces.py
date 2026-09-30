"""Tier 1: package H of 0.32.0, surface removal by name and the wake-stabilization key.

FR-275 to FR-279. Round 1 on 26.124 accepted ``DELETE_SURFACES 3`` on the
four-boundary twin mesh (inventory Body, Base, Blade1, Blade2 before and
Body, Base, Blade2 after) and accepted ``SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION
1 DISABLE 1`` after an ENABLE. Every mesh here is synthetic.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyflightstream.cases import CampaignConfigError, SolverSettings
from pyflightstream.cases.workflows import build_script
from pyflightstream.script import Script
from pyflightstream.workspace.inputs import SetupArtifact
from pyflightstream.workspace.matrix import _solver_from_setup
from tests.tier1_offline.test_workflows import (
    _saved_simulation,
    rendered,
    rotor_case,
    steady_case,
)

TWIN = ["Body", "Base", "Blade1", "Blade2"]
STABILIZATION = "SET_MOTION_SLIPSTREAM_WAKE_STABILIZATION"


def _twin(tmp_path: Path) -> str:
    return str(_saved_simulation(tmp_path / "41_TWIN.fsm", TWIN))


def _built(case, build: str = "26.124") -> Script:
    script = Script(build)
    build_script(case, script)
    return script


def _with(case, **settings):
    return case.model_copy(update={"solver": SolverSettings(**settings)})


def test_delete_surfaces_by_name_emits_the_index_and_renumbers_the_inventory(tmp_path):
    """P0320-G9-DELETE-SURFACES: the round-1 shape, Blade1 removed, Blade2 moves from 4 to 3."""
    case = _with(steady_case(geometry=_twin(tmp_path)), delete_surfaces=["Blade1"])
    script = _built(case)
    lines = script.render().splitlines()
    assert "DELETE_SURFACES 3" in lines
    assert lines.index("DELETE_SURFACES 3") > lines.index("OPEN")
    assert script.boundary_inventory == ("Body", "Base", "Blade2")
    assert script.entities.labels("boundaries") == {"Body": 1, "Base": 2, "Blade2": 3}
    assert script.num_boundaries == 3


def test_a_command_after_the_removal_cites_the_new_index(tmp_path):
    """P0320-G9-DELETE-SURFACES: the motion moves Blade2, and the solver now numbers it 3."""
    geometry = _twin(tmp_path)
    kept = rotor_case(MOVING_BOUNDARIES="Blade2").model_copy(update={"geometry": geometry})
    before = rendered(kept, build="26.124").splitlines()
    after = rendered(
        _with(kept, delete_surfaces=["Blade1"]),
        build="26.124",
    ).splitlines()
    assert any(line.startswith("SET_MOTION_BOUNDARIES") for line in before)
    moved_before = next(i for i, line in enumerate(before) if line.startswith("SET_MOTION_BOUN"))
    moved_after = next(i for i, line in enumerate(after) if line.startswith("SET_MOTION_BOUN"))
    assert before[moved_before] == "SET_MOTION_BOUNDARIES 1 1"
    assert before[moved_before + 1] == "4"
    assert after[moved_after] == "SET_MOTION_BOUNDARIES 1 1"
    assert after[moved_after + 1] == "3"


def test_a_family_removes_every_member_from_the_last_so_no_index_shifts_under_it(tmp_path):
    """P0320-G9-DELETE-SURFACES: the family Blade is Blade1 and Blade2, removed 4 then 3."""
    case = _with(steady_case(geometry=_twin(tmp_path)), delete_surfaces=["Blade"])
    script = _built(case)
    lines = script.render().splitlines()
    assert lines.index("DELETE_SURFACES 4") < lines.index("DELETE_SURFACES 3")
    assert script.boundary_inventory == ("Body", "Base")


def test_a_name_the_geometry_lacks_is_refused_naming_the_key_and_the_inventory(tmp_path):
    """P0320-G9-DELETE-SURFACES refusal: a name the inventory lacks is refused, never dropped."""
    case = _with(steady_case(geometry=_twin(tmp_path)), delete_surfaces=["Canopy"])
    with pytest.raises(CampaignConfigError) as refused:
        rendered(case, build="26.124")
    message = str(refused.value)
    assert "delete_surfaces" in message and "Canopy" in message
    assert "Body" in message and "Blade2" in message


def test_removing_every_surface_is_refused(tmp_path):
    """P0320-G9-DELETE-SURFACES refusal: a mesh with no surface left is refused."""
    case = _with(
        steady_case(geometry=_twin(tmp_path)),
        delete_surfaces=["Body", "Base", "Blade"],
    )
    with pytest.raises(CampaignConfigError, match="every surface"):
        rendered(case, build="26.124")


def test_a_removal_with_no_geometry_inventory_is_refused(tmp_path):
    """P0320-G9-DELETE-SURFACES refusal: names need an inventory to resolve against."""
    case = _with(steady_case(), delete_surfaces=["Blade1"])
    with pytest.raises(CampaignConfigError, match="delete_surfaces"):
        rendered(case, build="26.124")


def test_a_setup_that_says_nothing_removes_nothing(tmp_path):
    """P0320-G9-DELETE-SURFACES control: absent is not empty, and nothing is emitted."""
    script = _built(steady_case(geometry=_twin(tmp_path)))
    assert "DELETE_SURFACES" not in script.render()
    assert script.boundary_inventory == tuple(TWIN)


def test_the_setup_key_reaches_the_solver_settings(tmp_path):
    """P0320-G9-DELETE-SURFACES and P0320-G4-WAKE-DISABLE: both keys parse from a setup table."""
    solver = _solver_from_setup(
        SetupArtifact(
            settings={"delete_surfaces": ["Blade1"], "slipstream_wake_stabilization": "DISABLE"}
        ),
        "s9xx",
    )
    assert solver.delete_surfaces == ["Blade1"]
    assert solver.slipstream_wake_stabilization is False


def test_the_wake_stabilization_disable_is_emitted_for_the_rotor_motion():
    """P0320-G4-WAKE-DISABLE: DISABLE reaches the solver, with the row's blade count."""
    case = _with(rotor_case(), slipstream_wake_stabilization=False)
    lines = rendered(case, build="26.124").splitlines()
    assert f"{STABILIZATION} 1 DISABLE 4" in lines
    assert lines.index(f"{STABILIZATION} 1 DISABLE 4") > lines.index("CREATE_NEW_MOTION ROTARY")


def test_the_wake_stabilization_disable_without_a_blade_count_states_one():
    """P0320-G4-WAKE-DISABLE: the round-1 form, the count is unread by a DISABLE."""
    row = rotor_case(BLADES=None, PERIODIC_COPIES=None, LAST_REVS_AVG="0.25")
    case = _with(row, slipstream_wake_stabilization=False)
    lines = rendered(case, build="26.124").splitlines()
    assert f"{STABILIZATION} 1 DISABLE 1" in lines


def test_the_wake_stabilization_enable_is_emitted_with_the_count():
    """P0320-G4-WAKE-DISABLE: ENABLE is the same key with the other word."""
    case = _with(rotor_case(), slipstream_wake_stabilization=True)
    lines = rendered(case, build="26.124").splitlines()
    assert f"{STABILIZATION} 1 ENABLE 4" in lines


def test_the_february_edition_takes_two_arguments():
    """P0320-G4-WAKE-DISABLE: 26.100 documents no NUM_BLADES, so none is written."""
    case = _with(rotor_case(), slipstream_wake_stabilization=False)
    lines = rendered(case, build="26.100").splitlines()
    assert f"{STABILIZATION} 1 DISABLE" in lines


def test_a_setup_that_says_nothing_emits_no_wake_stabilization():
    """P0320-G4-WAKE-DISABLE control: absent emits nothing, as every setup did before."""
    assert STABILIZATION not in rendered(rotor_case(), build="26.124")


def test_the_wake_stabilization_on_a_row_with_no_rotor_is_refused(tmp_path):
    """P0320-G4-WAKE-DISABLE refusal: a key reaching no motion is refused, not dropped."""
    case = _with(steady_case(), slipstream_wake_stabilization=False)
    with pytest.raises(CampaignConfigError, match="slipstream_wake_stabilization"):
        rendered(case, build="26.124")


def test_the_wake_stabilization_enable_without_a_blade_count_is_refused():
    """P0320-G4-WAKE-DISABLE refusal: an ENABLE needs the per-propeller blade count."""
    row = rotor_case(BLADES=None, PERIODIC_COPIES=None)
    case = _with(row, slipstream_wake_stabilization=True)
    with pytest.raises(CampaignConfigError, match="blade count"):
        rendered(case, build="26.124")


def test_the_february_edition_enable_needs_no_blade_count_because_it_takes_none():
    """P0320-G4-WAKE-DISABLE: 26.100 reads no count, so none is required."""
    row = rotor_case(BLADES=None, PERIODIC_COPIES=None)
    case = _with(row, slipstream_wake_stabilization=True)
    lines = rendered(case, build="26.100").splitlines()
    assert f"{STABILIZATION} 1 ENABLE" in lines
