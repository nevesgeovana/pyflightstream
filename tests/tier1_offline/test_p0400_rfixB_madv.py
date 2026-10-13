# ruff: noqa: N999
"""Advancing Mach survives the plan, persisted run record and rotor CSV."""

import math
import warnings

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.post.products import read_csv_table, write_rotor_table
from pyflightstream.run import CampaignErrors
from pyflightstream.run.matrix import plan_matrix, run_matrix
from tests.tier1_offline.test_goal026_item06_rotor_loads import _reference, _rotor
from tests.tier1_offline.test_goal035_rotor_mach import SEA_LEVEL_SOUND, _row
from tests.tier1_offline.test_matrix_run import StubSolver, _rotor_matrix, converged, make_library


@pytest.mark.requirement("FR-176")
@pytest.mark.parametrize("radius_known", [True, False])
def test_p0400_rfixb_advancing_mach_is_numeric_through_the_workflow(tmp_path, radius_known):
    """P0400-RFIXB-MADV: edgewise 300 m/s, 1200 rpm, 1.2 m diameter, or no radius."""
    workspace = make_library(tmp_path, register_build=("26.120", "C:/fs26120/FlightStream.exe"))
    reference = workspace.inputs_dir / "references" / "r003.toml"
    if radius_known:
        reference.write_text("rotor_diameter_m = 1.2\n" + reference.read_text(), encoding="utf-8")
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = "all"\n', encoding="utf-8"
    )
    matrix = _rotor_matrix(tmp_path)
    matrix.write_text(
        matrix.read_text().replace("MACH:0.2, REmi:11.77,", "TASmps:300.0,"), encoding="utf-8"
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", PyflightstreamWarning)
        plan = plan_matrix(
            matrix,
            workspace,
            name="rotor",
            recipes={},
            recipe_registry=workflow_registry(),
            write_plan=False,
        )
        with pytest.raises(CampaignErrors):
            run_matrix(
                matrix,
                workspace,
                name="rotor",
                recipes={},
                recipe_registry=workflow_registry(),
                assess=converged,
                executor=StubSolver("pass"),
            )
    (point,) = plan.points
    (record,) = workspace.read_manifest()
    planned = next(iter(point.rotor_mach.values()))
    persisted = next(iter(record.rotor_mach.values()))
    if not radius_known:
        assert planned["mach_advancing"] is None and persisted["mach_advancing"] is None
        assert "not computed" in plan.summary()
        return
    tip = 24.0 * math.pi
    advancing = (tip + 300.0) / SEA_LEVEL_SOUND
    helical = math.hypot(tip, 300.0) / SEA_LEVEL_SOUND
    assert helical < 1.0 < advancing
    for mach in (planned, persisted):
        assert mach["mach_advancing"] == pytest.approx(advancing, rel=1e-6)
        assert mach["mach_helical"] == pytest.approx(helical, rel=1e-6)
        assert mach["mach_advancing_bound"] == "edgewise"
    assert f"M_adv {advancing:.3f}" in plan.summary() and "edgewise bound" in plan.summary()
    assert any("M_adv >= 1" in str(w.message) for w in caught)
    rotor = _rotor("Z").model_copy(update={"diameter_m": 1.2})
    csv = write_rotor_table(
        tmp_path / "rotor.csv",
        rotor=rotor,
        rows=[_row(rpm=1200.0, air=(300.0, SEA_LEVEL_SOUND))],
        reference=_reference(),
    )
    _, rows = read_csv_table(csv)
    assert float(rows[0]["MADV_PUSHER"]) == pytest.approx(advancing, abs=1e-5)
    assert float(rows[0]["MHEL_PUSHER"]) == pytest.approx(helical, abs=1e-5)


@pytest.mark.requirement("FR-176")
def test_p0400_rfixb_madv_without_resolved_air_is_na(tmp_path):
    """P0400-RFIXB-MADV: unavailable Mach stays NA while the loads row survives."""
    csv = write_rotor_table(
        tmp_path / "rotor.csv", rotor=_rotor("Z"), rows=[_row(air=None)], reference=_reference()
    )
    _, rows = read_csv_table(csv)
    assert rows[0]["MADV_PUSHER"] == "NA" and rows[0]["MHEL_PUSHER"] == "NA"
