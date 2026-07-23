"""Tier 1: the pyfs-matrix command line (convert and plan, no run)."""

import tomllib
from pathlib import Path

from pyflightstream.cases import load_campaign
from pyflightstream.cases.cli import main
from pyflightstream.workspace import CampaignWorkspace

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "matrix.fs"
REGISTRY_FIXTURE = FIXTURES / "matrix_registry.fs"
RECIPE_ARGS = [
    "--recipe",
    "003=recipes.steady_polar:build",
    "--recipe",
    "004=recipes.beta_sweep:build",
]

RECIPE_MODULE = """\
from pyflightstream.script import helpers


def build(case, script):
    helpers.free_stream(script)
    helpers.initialize_solver(script)
    helpers.solver_settings(
        script, vorticity_drag_boundaries="all", aoa=case.point.get("alpha", 0.0), velocity=30.0
    )
    helpers.start_solver(script)
    script.emit("CLOSE_FLIGHTSTREAM")
"""


def convert_args(*extra):
    return [
        "convert",
        str(FIXTURE),
        "--name",
        "matrix",
        "--fs-version",
        "26.12",
        "--fs-exe",
        "C:/fs.exe",
        *RECIPE_ARGS,
        *extra,
    ]


def test_convert_prints_the_canonical_campaign_toml(capsys):
    assert main(convert_args()) == 0
    out = capsys.readouterr().out
    data = tomllib.loads(out)
    assert data["campaign"]["name"] == "matrix"
    assert len(data["sim"]) == 6
    assert data["sim"][0]["sim_id"] == "9001"


def test_convert_writes_a_loadable_file_with_output_option(tmp_path, capsys):
    target = tmp_path / "campaign.toml"
    assert main(convert_args("-o", str(target))) == 0
    assert str(target) in capsys.readouterr().out
    campaign = load_campaign(target)
    assert [sim.sim_id for sim in campaign.sims] == [
        "9001",
        "9002",
        "9004",
        "9005",
        "9006",
        "9008",
    ]


def test_convert_reports_an_unmapped_code_didactically(capsys):
    # Only the 003 code is mapped; the 004 rows have no recipe.
    argv = [
        "convert",
        str(FIXTURE),
        "--name",
        "matrix",
        "--fs-version",
        "26.12",
        "--fs-exe",
        "C:/fs.exe",
        "--recipe",
        "003=recipes.steady_polar:build",
    ]
    assert main(argv) == 2
    assert "no recipe" in capsys.readouterr().err


def test_a_malformed_recipe_option_is_refused(capsys):
    argv = convert_args()
    argv[argv.index("003=recipes.steady_polar:build")] = "003"
    assert main(argv) == 2
    assert "CODE=module:function" in capsys.readouterr().err


def make_planned_workspace(tmp_path):
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    inputs = workspace.inputs_dir
    (inputs / "references" / "003.toml").write_text(
        "area_m2 = 10.0\nchord_m = 1.2\nspan_m = 8.0\n", encoding="utf-8"
    )
    (inputs / "setups" / "002.toml").write_text("iterations = 800\n", encoding="utf-8")
    (inputs / "groups" / "001.toml").write_text('wing = ["wing_left"]\n', encoding="utf-8")
    with open(inputs / "executables.toml", "a", encoding="utf-8") as handle:
        handle.write('"26.120" = "C:/fs26120/FlightStream.exe"\n')
    return workspace


def plan_args(workspace, recipe_reference):
    return [
        "plan",
        str(REGISTRY_FIXTURE),
        "--workspace",
        str(workspace.root),
        "--name",
        "matrix",
        "--fs-version",
        "26.120",
        "--recipe",
        f"003={recipe_reference}",
    ]


def test_plan_preflights_through_the_input_library(tmp_path, monkeypatch, capsys):
    (tmp_path / "matrix_cli_recipes.py").write_text(RECIPE_MODULE, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    workspace = make_planned_workspace(tmp_path)
    assert main(plan_args(workspace, "matrix_cli_recipes:build")) == 0
    out = capsys.readouterr().out
    assert "4 ready" in out
    assert "plan.json" in out
    assert workspace.read_manifest() == []


def test_plan_reports_a_blocked_preflight_with_exit_1(tmp_path, capsys):
    workspace = make_planned_workspace(tmp_path)
    assert main(plan_args(workspace, "no.such.module:build")) == 1
    out = capsys.readouterr().out
    assert "4 blocked" in out


def test_plan_surfaces_a_library_miss_didactically(tmp_path, capsys):
    # Build registered, but no reference/setup/group artifacts yet: the
    # first miss (the REF column) surfaces with the file to create.
    workspace = CampaignWorkspace.init(tmp_path / "empty")
    with open(workspace.inputs_dir / "executables.toml", "a", encoding="utf-8") as handle:
        handle.write('"26.120" = "C:/fs26120/FlightStream.exe"\n')
    assert main(plan_args(workspace, "matrix_cli_recipes:build")) == 2
    err = capsys.readouterr().err
    assert "matrix not planned" in err
    assert "inputs/references/003.toml" in err
