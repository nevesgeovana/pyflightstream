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


def test_p0410_workspace_posts_exploratory_loading_noise(tmp_path):
    import csv

    from tests.tier1_offline.test_goal036_qsteady_corrections import _post_recorded, _recorded_wheel

    workspace = _recorded_wheel(
        tmp_path,
        pproc_extra="""
[noise]
exploratory = true
observers_m = [[10.0, 2.0, 2.0]]
hub_velocity_m_s = [0.0, 0.0, 0.0]
sound_speed_m_s = 340.0
samples_per_revolution = 64
orders = 0
axial_radius_m = 0.7
inplane_radius_m = 0.7
""",
    )
    manifest, folder, _ = _post_recorded(workspace)
    files = list(folder.glob("noise/*.csv"))
    assert files
    rows = list(csv.DictReader(files[0].read_text().splitlines()))
    assert len(rows) == 64
    assert all(math.isfinite(float(row["pressure_pa"])) for row in rows)
    assert max(abs(float(row["pressure_pa"])) for row in rows) > 0
    entry = manifest["products"][files[0].relative_to(folder).as_posix()]
    assert entry["validation"] == "exploratory, not validated"
    report = json.loads((folder / "noise_report.json").read_text())
    assert report["validation"] == "exploratory, not validated"
    assert report["products"][files[0].relative_to(folder).as_posix()] == entry


@pytest.mark.parametrize("axes,suffix", [("wind", "W"), ("stability", "S")])
def test_p0410_workspace_selects_polar_axes(tmp_path, axes, suffix):
    import csv

    from pyflightstream.post.products import write_campaign_products
    from tests.tier1_offline.test_post_products import _steady_workspace_with_provenance

    workspace = _steady_workspace_with_provenance(tmp_path)
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        f'[products]\npolar_axes = "{axes}"\n[groups]\n"1" = "all"\n'
    )
    write_campaign_products(workspace)
    tables = list(workspace.root.glob("post/**/polars/*.csv"))
    assert tables
    rows = list(csv.DictReader(tables[0].read_text().splitlines()))
    assert rows
    for row in rows:
        for quantity in ("CD", "CY", "CL"):
            assert float(row[quantity]) == pytest.approx(float(row[quantity + suffix]), abs=1e-5)


def test_p0410_workspace_coupling_rotates_station_forces(tmp_path):
    import numpy as np

    from pyflightstream.fsi import driver, kinematics, nodes
    from pyflightstream.fsi.state import initial_state, write_state_atomic
    from tests.tier1_offline.test_fsig_fixed_wing import (
        SPAN_M,
        _staged_run,
        _wing_loads_export,
        wing_config,
    )

    config = wing_config(self_weight=False)
    run = _staged_run(tmp_path, steady_wing_case, config)
    layout = nodes.load_node_map(run / config.node_map_file)
    slope, twist = 0.2, 0.3
    local = kinematics.encode_station_translations(
        slope * np.asarray(config.blade.station_radii_m),
        np.full(len(config.blade.station_radii_m), twist),
        np.asarray(layout.le_offset_m),
        np.asarray(layout.te_offset_m),
    )
    state = initial_state()
    state.previous_displacements = nodes.flatten_blade_translations(layout, [local]).tolist()
    write_state_atomic(state, run / "state.json")
    (run / driver.LOADS_FILE).write_text(_wing_loads_export(60, unsteady=False))
    result = driver.coupling_step(run)
    normal = 50 * math.cos(math.atan(slope)) * math.cos(twist)
    assert result.solutions[0].flap_deflection_m[-1] == pytest.approx(
        normal * SPAN_M**4 / (8 * 2e5), rel=1e-6
    )


@pytest.mark.parametrize("attachment", ["space", "body"])
def test_p0410_plan_checks_section_attachment(tmp_path, attachment):
    case = steady_wing_case(tmp_path)
    declaration = case.pproc.model_dump()
    declaration["sections"]["distributions"][0]["attach"] = attachment
    case = case.model_copy(update={"pproc": PprocSpec.model_validate(declaration)})
    campaign = Campaign(name="attached", fs_version="26.124", fs_exe=sys.executable, sims=[case])
    plan = plan_campaign(
        campaign, CampaignWorkspace.init(tmp_path / "workspace"), recipes=workflow_registry()
    )
    if attachment == "body":
        assert all(point.status == "BLOCKED" for point in plan.points)
        assert all("attach='body'" in point.error for point in plan.points)
    else:
        assert all(point.status == "READY" for point in plan.points), [p.error for p in plan.points]


def test_p0410_workspace_stages_frozen_configuration(tmp_path):
    import numpy as np

    from pyflightstream.fsi.nodes import generate_node_layout, write_fsidisp
    from pyflightstream.workspace.fsi_setup import stage_fsi_setup
    from tests.tier1_offline.test_workspace_fsi_setup import SUPPLIED

    source = tmp_path / "f001.toml"
    source.write_text(SUPPLIED)
    config = resolve_fsi_setup(source).effective
    layout = generate_node_layout(config)
    frozen = tmp_path / "frozen.txt"
    write_fsidisp(frozen, np.zeros((layout.total_nodes, 3)))
    source.write_text(
        'frozen_displacements_file = "frozen.txt"\nallow_configuration_change = true\n' + SUPPLIED
    )
    resolved = resolve_fsi_setup(source)
    stage_fsi_setup(resolved, tmp_path / "run")
    assert (tmp_path / "run/fsi_frozen_displacements.txt").read_bytes() == frozen.read_bytes()
    assert (tmp_path / "run/fsi_allow_config_change").is_file()
    frozen.write_text("changed")
    with pytest.raises(ValueError, match="changed"):
        stage_fsi_setup(resolved, tmp_path / "changed-run")


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
    from pyflightstream.cases.workflows._farfield import planar_points

    saved = case.model_copy(update={"geometry": str(tmp_path / "wing.fsm")})
    with pytest.raises(ValueError, match="wing.surface.stl"):
        planar_points(saved, pproc.probes[0], 1.0)


@pytest.mark.parametrize("morphing", ["mapped", "direct"])
def test_p0410_workspace_post_reports_structure(tmp_path, morphing):
    import shutil

    import numpy as np

    from pyflightstream._digest import file_sha256
    from pyflightstream.fsi.nodes import (
        flatten_blade_translations,
        generate_node_layout,
        write_fsidisp,
    )
    from pyflightstream.post.products import write_campaign_products
    from tests.tier1_offline.test_post_products import _steady_workspace_with_provenance

    recorded = _steady_workspace_with_provenance(tmp_path / "fixture")
    original = recorded.read_manifest()[0]
    workspace = CampaignWorkspace.init(tmp_path / "posted")
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text('[groups]\n"1"="all"\n')
    for relative in original.outputs:
        target = workspace.sim_dir(original.sim_id) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(recorded.sim_dir(original.sim_id) / relative, target)
    work = workspace.sim_dir(original.sim_id) / "structural"
    work.mkdir()
    case = steady_wing_case(tmp_path)
    config = case.fsi
    if morphing == "direct":
        config = config.model_copy(update={"morphing": "direct", "wing": None})
    (work / "config.json").write_text(config.model_dump_json())
    layout = generate_node_layout(config)
    local = np.zeros((9, 3, 3))
    for index in range(9):
        w, theta = index * 0.001, index * 0.002
        local[index, :, 1] = [
            w,
            w + layout.le_offset_m[index] * theta,
            w + layout.te_offset_m[index] * theta,
        ]
    write_fsidisp(work / "FSIDisp.txt", flatten_blade_translations(layout, [local]))
    if morphing == "direct":
        from pyflightstream.fsi.config import config_sha256
        from pyflightstream.fsi.state import FsiState, write_state_atomic

        state = FsiState(
            config_sha256=config_sha256(config),
            station_displacements_m=flatten_blade_translations(layout, [local]).tolist(),
        )
        write_state_atomic(state, work / "state.json")
        (work / "FSIDisp.txt").write_text("mesh vertex displacements are not station triads\n")
    workspace.append_record(
        original.model_copy(
            update={
                "cwd": str(work),
                "inputs_sha256": {
                    "config.json": file_sha256(work / "config.json"),
                    "fsi-provenance.json": "0" * 64,
                },
            }
        )
    )
    write_campaign_products(workspace)
    products = list(workspace.root.glob("post/**/structure/*_deflection.csv"))
    assert len(products) == 1
    import csv

    with products[0].open() as handle:
        rows = list(csv.DictReader(handle))
    assert float(rows[-1]["deflection_m"]) == pytest.approx(0.008)
    assert float(rows[-1]["twist_deg"]) == pytest.approx(math.degrees(0.016))
    polars = list(workspace.root.glob("post/**/polars/*.csv"))
    assert polars
    with polars[0].open() as handle:
        polar_rows = list(csv.DictReader(handle))
    assert float(polar_rows[0]["tip_deflection_m_blade_1"]) == pytest.approx(0.008)


def test_p0410_rotor_tip_rows_keep_run_order_and_alias(tmp_path):
    from types import SimpleNamespace

    from pyflightstream.post._structure import append_tip_columns

    table = tmp_path / "rotor.csv"
    table.write_text("PROP\nCT,CQ\n0.1,0.01\n0.2,0.02\n")
    ctx = SimpleNamespace(out=tmp_path, skipped={}, structure_tips={"second": [(0.04, 2.0)]})
    append_tip_columns(ctx, table, ["first", "second"])
    assert table.read_text().splitlines() == [
        "PROP",
        "CT,CQ,tip_deflection_m_blade_1,tip_twist_deg_blade_1",
        "0.1,0.01,NA,NA",
        "0.2,0.02,0.04,2.0",
    ]


@pytest.mark.parametrize(
    "kind,fixture,suffix,expected",
    [
        ("force_distributions", "force_distributions_26.123.txt", "_force_distributions.txt", 96),
        ("surface_values", "solver_analysis_26.123.csv", ".csv", 86),
    ],
    ids=["P0410-FORCE-TABLE", "P0410-SURFACE-TABLE"],
)
def test_p0410_workspace_posts_export_tables(tmp_path, kind, fixture, suffix, expected):
    from pathlib import Path

    from pyflightstream.post.products import write_campaign_products
    from tests.tier1_offline.test_post_products import _steady_workspace_with_provenance

    source = _steady_workspace_with_provenance(tmp_path / "source")
    record = source.read_manifest()[0]
    workspace = CampaignWorkspace.init(tmp_path / "target")
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text('[groups]\n"1"="all"\n')
    for relative in record.outputs:
        target = workspace.sim_dir(record.sim_id) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source.sim_dir(record.sim_id) / relative).read_bytes())
    relative = "outputs/point" + suffix
    fixture_path = Path(__file__).parent / "fixtures" / fixture
    (workspace.sim_dir(record.sim_id) / relative).write_bytes(fixture_path.read_bytes())
    workspace.append_record(
        record.model_copy(
            update={
                "outputs": [*record.outputs, relative],
                "fs_version_requested": "26.123",
                "package_version": "0.41.0",
            }
        )
    )
    write_campaign_products(workspace)
    tables = list(workspace.root.glob(f"post/**/tables/*_{kind}.csv"))
    assert len(tables) == 1
    assert len(tables[0].read_text().splitlines()) == expected + 1
