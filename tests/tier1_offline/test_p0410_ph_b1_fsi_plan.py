"""Plan a coupled wing before spending solver time; inspect plan.json's fsi quantities."""

import json
import math
import sys

import pytest

from pyflightstream.cases import Campaign, PprocSpec
from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run import plan_campaign
from pyflightstream.workspace import CampaignWorkspace
from pyflightstream.workspace.fsi_setup import FsiSetupError, resolve_fsi_setup
from tests.tier1_offline.test_fsig_fixed_wing import steady_wing_case


@pytest.mark.parametrize("stiffness_factor", [1.0, 4.0], ids=["P0410-FSI", "P0410-FSI-STIFF"])
def test_p0410_plan_reports_station_properties_and_natural_frequencies(tmp_path, stiffness_factor):
    case = steady_wing_case(tmp_path)
    cfg = case.fsi
    cfg.blade.bending_stiffness_n_m2 = [2e5 * stiffness_factor] * 9
    campaign = Campaign(name="beam", fs_version="26.124", fs_exe=sys.executable, sims=[case])
    workspace = CampaignWorkspace.init(tmp_path / "workspace")
    result = plan_campaign(campaign, workspace, recipes=workflow_registry())
    assert all(point.status == "READY" for point in result.points), [p.error for p in result.points]
    payload = json.loads(result.plan_file.read_text())
    assessment = payload["points"][0].get("fsi", {})
    assert assessment.get("station_properties", {}).get("station_radii_m") == [
        i / 2 for i in range(9)
    ]
    # Uniform cantilever: beta_1^2 sqrt(EI/(mu L^4)), independent analytic oracle.
    expected_hz = 1.875104**2 * math.sqrt(2e5 * stiffness_factor / (3 * 4**4)) / (2 * math.pi)
    assert assessment["natural_frequencies_hz"][0] == pytest.approx(expected_hz, rel=0.02)
    assert assessment["warnings"] == []


@pytest.mark.parametrize(
    "shape",
    ["airfoil = [[0.0, 0.0], [0.5, 0.06], [1.0, 0.0], [0.5, -0.06]]", 'naca = "0012"'],
    ids=["P0410-AIRFOIL", "P0410-NACA"],
)
def test_p0410_section_shapes_resolve_through_workspace(tmp_path, shape):
    source = tmp_path / "f001.toml"
    source.write_text(
        'mode = "calculated"\nmaterial = "ti-6al-4v-grade5-annealed"\n'
        "[config]\nblade_count = 1\nomega_rad_per_s = 0.0\n"
        "[sections]\nstation_radii_m = [0.0, 0.5, 1.0]\n"
        "chord_m = [1.0, 1.0, 1.0]\ngeometric_pitch_deg = [0.0, 0.0, 0.0]\n"
        'geometry_source = "synthetic airfoil"\ntorsion_grid_cells = 16\n' + shape,
        encoding="utf-8",
    )
    try:
        result = resolve_fsi_setup(source)
    except FsiSetupError as error:
        result = None
        refusal = str(error)
    assert result is not None, refusal
    blade = result.effective.blade
    assert all(mass > 0 for mass in blade.mass_per_length_kg_per_m)
    assert max(p[0] for p in blade.section_contours_m[0]) == pytest.approx(0.25)
    assert min(p[0] for p in blade.section_contours_m[0]) == pytest.approx(-0.75)
    case = steady_wing_case(tmp_path)
    config = result.effective.model_copy(update={"wing": case.fsi.wing})
    case = case.model_copy(update={"fsi": config})
    campaign = Campaign(name="airfoil", fs_version="26.124", fs_exe=sys.executable, sims=[case])
    plan = plan_campaign(
        campaign, CampaignWorkspace.init(tmp_path / "workspace"), recipes=workflow_registry()
    )
    assert all(point.status == "READY" for point in plan.points), [p.error for p in plan.points]
    assert plan.points[0].fsi["station_properties"]["chord_m"] == [1.0, 1.0, 1.0]


def test_p0410_planar_grid_reaches_workspace_plan(tmp_path):
    from pyflightstream.script import Script

    case = steady_wing_case(tmp_path).model_copy(update={"fsi": None})
    declaration = {
        "probes": [
            {
                "frame": "REFERENCE",
                "scale": "m",
                "parameters": ["VX"],
                "grids": [
                    {
                        "frame": {"origin": [0, 0, 2], "x_axis": [1, 0, 0], "y_axis": [0, 1, 0]},
                        "u": {"start": 0, "stop": 1, "count": 2},
                        "v": {"start": 0, "stop": 1, "count": 2},
                    }
                ],
            }
        ]
    }
    try:
        pproc = PprocSpec.model_validate(declaration)
    except ValueError as error:
        pproc = None
        refusal = str(error)
    assert pproc is not None, refusal
    case = case.model_copy(update={"pproc": pproc})
    campaign = Campaign(name="grid", fs_version="26.124", fs_exe=sys.executable, sims=[case])
    plan = plan_campaign(
        campaign, CampaignWorkspace.init(tmp_path / "workspace"), recipes=workflow_registry()
    )
    assert all(point.status == "READY" for point in plan.points), [p.error for p in plan.points]
    script = Script("26.124")
    workflow_registry()["steady"](case, script)
    assert [list(point[1:4]) for point in script.probe_points] == [
        [0.0, 0.0, 2.0],
        [0.0, 1.0, 2.0],
        [1.0, 0.0, 2.0],
        [1.0, 1.0, 2.0],
    ]
    from pyflightstream.cases.workflows._planar_probes import planar_points

    saved = case.model_copy(update={"geometry": str(tmp_path / "wing.fsm")})
    with pytest.raises(ValueError, match="wing.surface.stl"):
        planar_points(saved, pproc.probes[0], 1.0)
