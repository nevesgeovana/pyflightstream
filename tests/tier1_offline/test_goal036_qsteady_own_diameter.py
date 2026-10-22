"""Tier 1: a quasi-steady rotor row resolves J against the rotor block's own diameter."""

from __future__ import annotations

import pytest

from pyflightstream.cases import (
    BladeDatum,
    CampaignConfigError,
    ReferenceData,
    RotorBlock,
)
from pyflightstream.cases.workflows import qsteady_validity

BLOCK_DIAMETER = 2.0
TOP_LEVEL_DIAMETER = 5.0


@pytest.mark.requirement("FR-192")
def test_qsteady_advance_ratio_follows_the_block_diameter(tmp_path):
    # P0310-J-OWN-DIAMETER
    from tests.tier1_offline.test_goal035_qsteady_rotor import _blade_obj, _case, _with_obj

    case = _case(RPM=None, ADVANCE_RATIO="0.5").model_copy(
        update={
            "reference": ReferenceData(area=3.14, length=0.2, rotor_diameter=TOP_LEVEL_DIAMETER)
        }
    )
    case = _with_obj(case, _blade_obj(tmp_path / "prop.obj"), ("Blade1", "Blade2", "Blade3"))
    record = qsteady_validity(case)
    assert record is not None
    # n = V / (J D) with the block's D = 2 m: 30 / (0.5 * 2) = 30 rev/s = 1800 rev/min.
    assert record["rpm"] == pytest.approx(1800.0)
    assert record["rpm"] != pytest.approx(60.0 * 30.0 / (0.5 * TOP_LEVEL_DIAMETER))


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
    plain = qsteady_validity(_wheel(tmp_path, ("Blade1", "Blade2", "Blade3")))
    assert plain is not None and "holds no face of blade" not in str(plain.get("note"))
    renamed = _wheel(
        tmp_path,
        ("Spare", "Blade2", "Blade3"),
        operations=[{"op": "rename", "surface": "Blade1", "to": "Spare"}],
    )
    record = qsteady_validity(renamed)
    assert record is not None and "holds no face of blade Blade1" in str(record["note"])


def test_f1321_a_blade_present_under_another_letter_case_gets_its_frame(tmp_path):
    from pyflightstream.cases import PprocSpec
    from pyflightstream.cases.workflows import build_script
    from pyflightstream.script import Script
    from pyflightstream.script.entities import ScriptReferenceError

    lower = RotorBlock(
        alias="PROP",
        axis="X",
        diameter_m=2.0,
        families_blades=["blade1", "blade2", "blade3"],
        blade1=BladeDatum(azimuth_deg=0.0, zero="Y"),
    )
    pproc = PprocSpec.model_validate(
        {
            "sections": {
                "count": 1,
                "distributions": [
                    {"families": ["Blade1"], "frame": "LOCAL_AXIS", "planes": ["XZ"]}
                ],
            }
        }
    )
    case = _wheel(tmp_path, ("Blade1", "Blade2", "Blade3"), rotor=lower)
    case = case.model_copy(update={"pproc": pproc, "pproc_id": "p001"})
    script = Script("26.124")
    # The blade frames are placed first; the section that cites the lower-case family then
    # finds no such label, which is a separate refusal and not what this test is about.
    with pytest.raises(ScriptReferenceError, match="unknown mesh boundary label 'blade1'"):
        build_script(case, script)
    lines = script.render().splitlines()
    for name in ("PROP_RMRP1", "PROP_RMRP2", "PROP_RMRP3"):
        assert f"NAME {name}" in lines


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
