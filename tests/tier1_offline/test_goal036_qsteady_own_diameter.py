"""Tier 1: a quasi-steady rotor row resolves J against the rotor block's own diameter."""

from __future__ import annotations

import pytest

from pyflightstream.cases import (
    BladeDatum,
    CampaignConfigError,
    ReferenceData,
    RotorBlock,
    SimCase,
    SweepAxis,
)
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


# --- F5-1112: a wheel's blades are surfaces, import renames are read, case is folded ----


def _wheel(tmp_path, inventory, *, aliases=None, rotor=None, operations=None):
    from pyflightstream.cases import MeshOperation
    from tests.tier1_offline.test_goal035_qsteady_rotor import _blade_obj, _case, _with_obj

    kwargs = {} if rotor is None else {"rotor": rotor}
    case = _with_obj(_case(**kwargs), _blade_obj(tmp_path / "prop.obj"), inventory)
    if aliases:
        case = case.model_copy(update={"aliases": aliases})
    if operations:
        case = case.model_copy(
            update={
                "mesh_import": case.mesh_import.model_copy(
                    update={"operations": [MeshOperation(**each) for each in operations]}
                )
            }
        )
    return case


def test_f033_two_blade_names_for_one_surface_are_one_blade_in_a_wheel(tmp_path):
    from tests.tier1_offline.test_goal035_qsteady_rotor import _lines

    # THE CONTROL: three surfaces for three blades builds.
    _lines(_wheel(tmp_path, ("Blade1", "Blade2", "Blade3")))
    case = _wheel(tmp_path, ("Blade1", "Blade3"), aliases={"Blade2": ["Blade1"]})
    with pytest.raises(CampaignConfigError, match="same boundary as Blade1"):
        _lines(case)


def test_f071_the_chord_is_read_from_the_blade_under_its_renamed_name(tmp_path):
    from pyflightstream.cases.workflows._qsteady_rotor import _blade_stations_from_the_mesh
    from tests.tier1_offline.test_goal035_qsteady_rotor import ROTOR

    plain = _wheel(tmp_path, ("Blade1", "Blade2", "Blade3"))
    assert not isinstance(_blade_stations_from_the_mesh(plain, ROTOR), str)
    renamed = _wheel(
        tmp_path,
        ("Spare", "Blade2", "Blade3"),
        operations=[{"op": "rename", "surface": "Blade1", "to": "Spare"}],
    )
    reason = _blade_stations_from_the_mesh(renamed, ROTOR)
    assert isinstance(reason, str) and "holds no face of blade Blade1" in reason


def test_f1321_a_blade_present_under_another_letter_case_gets_its_frame(monkeypatch):
    from types import SimpleNamespace

    from pyflightstream.cases.workflows import _qsteady_rotor as module
    from pyflightstream.script import Script

    lower = RotorBlock(
        alias="PROP",
        axis="X",
        diameter_m=2.0,
        families_blades=["blade1", "blade2", "blade3"],
        blade1=BladeDatum(azimuth_deg=0.0, zero="Y"),
    )
    names: list[str] = []
    axes = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    monkeypatch.setattr(
        module, "_placement_of", lambda *a: SimpleNamespace(origin=(0.0, 0.0, 0.0), axes=axes)
    )
    monkeypatch.setattr(module, "_inventory", lambda script: ["Blade1", "Blade2", "Blade3"])
    monkeypatch.setattr(module, "_turned_about", lambda vector, shaft, angle: vector)
    monkeypatch.setattr(
        module.helpers, "coordinate_frame", lambda script, **kw: names.append(kw["name"]) or 1
    )
    monkeypatch.setattr(module, "_the_shaft_letter", lambda rotor: "X")
    created = module._qsteady_blade_frames(_case(), Script("26.124"), lower, 1)
    assert sorted(created) == ["PROP_RMRP1", "PROP_RMRP2", "PROP_RMRP3"] == sorted(names)


def test_pfs2130_002_a_qsteady_sector_derives_its_copies_from_the_isolated_rotor(tmp_path):
    from tests.tier1_offline.test_goal035_qsteady_rotor import (
        _blade_obj,
        _case,
        _lines,
        _with_obj,
    )

    case = _with_obj(
        _case(SYMMETRY="PERIODIC"), _blade_obj(tmp_path / "sector.obj", blades=1), ("Blade1",)
    )
    lines, _script = _lines(case)
    assert any("PERIODIC" in line and line.split()[-1] == "3" for line in lines), lines[-40:]
