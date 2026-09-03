"""Tier 1: the pyfs-matrix command line (convert and plan, no run).

The module it lives in moved on 2026-08-19: `pyflightstream.cases.cli`
became `pyflightstream.run.cli`, because a command line that plans a
campaign composes the workspace input library with the campaign
pre-flight and so belongs at or above both, not two layers below them
(OPS-2007.01, and the lane determination of 2026-08-18). The console
entry point is what a user writes and it did not move: `pyfs-matrix`,
same subcommands, same flags, same output, so the FR-44 contract is
untouched and every assertion below is unchanged.
"""

import tomllib
from pathlib import Path

import pytest

from pyflightstream.cases import load_campaign
from pyflightstream.run.cli import main
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
        "26.120",
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
        "26.120",
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
    # The ids carry their kind letter since 2026-08-19 (PFS-2009.01):
    # r for a reference, s for a setup, e for the ENTRY column's groups.
    (inputs / "references" / "r003.toml").write_text(
        "area_m2 = 10.0\nchord_m = 1.2\nspan_m = 8.0\n", encoding="utf-8"
    )
    (inputs / "setups" / "s002.toml").write_text("iterations = 800\n", encoding="utf-8")
    (inputs / "pproc" / "p001.toml").write_text(
        '[groups]\nwing = ["wing_left"]\n', encoding="utf-8"
    )
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
    assert "inputs/references/r003.toml" in err


# --- PFS-2029.01 and PFS-2029.02: nothing repeated on the command line ------------

WORKFLOW_FIXTURE = FIXTURES / "workflow_rotor_matrix.fs"


def _workflow_plan_args(workspace, *extra):
    return [
        "plan",
        str(WORKFLOW_FIXTURE),
        "--workspace",
        str(workspace.root),
        "--name",
        "m",
        *extra,
    ]


def test_a_matrix_whose_rows_all_name_a_build_needs_no_fs_version(tmp_path, capsys):
    workspace = make_planned_workspace(tmp_path)
    assert main(_workflow_plan_args(workspace)) == 0
    out = capsys.readouterr().out
    assert "4 ready" in out, out


def test_a_silent_row_with_no_default_is_refused_naming_it(tmp_path, capsys):
    """The refusal that exists today, by row number and POL, with no default given."""
    text = WORKFLOW_FIXTURE.read_text(encoding="utf-8")
    silent = tmp_path / "silent.fs"
    silent.write_text(text.replace("| 26.120   |", "|          |", 1), encoding="utf-8")
    workspace = make_planned_workspace(tmp_path)
    argv = _workflow_plan_args(workspace)
    argv[1] = str(silent)
    assert main(argv) == 2
    err = capsys.readouterr().err
    assert "row 1 (POL 7001)" in err and "--fs-version" in err


def test_a_row_naming_a_registered_run_type_needs_no_workflow_option(tmp_path, capsys):
    """The three rows say steady, unsteady and unsteady_rotor, and that is the builder."""
    workspace = make_planned_workspace(tmp_path)
    assert main(_workflow_plan_args(workspace)) == 0
    assert "4 ready" in capsys.readouterr().out


def test_a_legacy_row_still_requires_its_recipe(tmp_path, capsys):
    workspace = make_planned_workspace(tmp_path)
    argv = ["plan", str(REGISTRY_FIXTURE), "--workspace", str(workspace.root), "--name", "m"]
    assert main(argv) == 2
    err = capsys.readouterr().err
    assert "LEGACY" in err and "RECIPE code '003'" in err and "--recipe" in err


def test_an_unknown_run_type_is_refused_naming_the_registered_ones(tmp_path, capsys):
    text = WORKFLOW_FIXTURE.read_text(encoding="utf-8")
    bad = tmp_path / "bad.fs"
    bad.write_text(text.replace("| unsteady_rotor |", "| hover          |", 1), encoding="utf-8")
    workspace = make_planned_workspace(tmp_path)
    argv = _workflow_plan_args(workspace)
    argv[1] = str(bad)
    assert main(argv) == 2
    err = capsys.readouterr().err
    assert "hover" in err and "steady, unsteady, unsteady_rotor" in err


# --- PFS-2029.15.03: `pyfs-matrix post` rebuilds the products with no solver -------


def test_post_reruns_from_the_manifest_without_a_solver(tmp_path, capsys):
    """The manifest and the collected exports are enough; an existing product needs --overwrite."""
    import json

    from test_post_products import LOADS

    from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus

    workspace = CampaignWorkspace.init(tmp_path / "camp")
    (workspace.inputs_dir / "pproc" / "p001.toml").write_text(
        '[groups]\n"1" = ["W", "B"]\n', encoding="utf-8"
    )
    raw = workspace.sim_dir("3207") / "raw"
    raw.mkdir(parents=True)
    (raw / "POLAR-3207_M20AL-020BE+000.txt").write_text(LOADS, encoding="utf-8")
    workspace.append_record(
        RunRecord(
            run_id="camp/sim_3207/a-02.0",
            sim_id="3207",
            point={"alpha": -2.0},
            fs_version_requested="26.120",
            package_version="0.11.0.dev0",
            script_sha256="",
            raw_flag=False,
            status=RunStatus.CONVERGED,
            outputs=["raw/POLAR-3207_M20AL-020BE+000.txt"],
            pproc="p001",
            description="STEADY_WB",
            mach=0.2,
            reference={
                "SREF": 50.0,
                "CREF": 2.526,
                "BREF": 20.0,
                "XMOM": 9.152,
                "YMOM": 0.0,
                "ZMOM": 0.0,
            },
        )
    )
    # No executables.toml entry is consulted, and no build: the manifest is the input.
    assert main(["post", "--workspace", str(workspace.root)]) == 0
    out = capsys.readouterr().out
    assert "1 product(s) written" in out
    table = workspace.root / "post" / "products" / "3207_M20_g01.csv"
    assert table.is_file()
    assert ",0.02744,0.00000,0.18744," in table.read_text(encoding="utf-8")
    manifest = json.loads((table.parent / "products.json").read_text(encoding="utf-8"))
    assert manifest["products"]["3207_M20_g01.csv"]["runs"] == ["camp/sim_3207/a-02.0"]
    # A second run refuses the existing product, and --overwrite rewrites it.
    assert main(["post", "--workspace", str(workspace.root)]) == 2
    assert "--overwrite" in capsys.readouterr().err
    assert main(["post", "--workspace", str(workspace.root), "--overwrite"]) == 0


# --- PFS-2029.03: the workspace directory names the campaign -----------------------


def test_the_workspace_directory_names_the_campaign(tmp_path, capsys):
    """`plan` from a directory named pfs0101 records campaign 'pfs0101', from the directory."""
    import json

    workspace = make_planned_workspace(tmp_path)
    root = tmp_path / "pfs0101"
    workspace.root.rename(root)
    argv = ["plan", str(WORKFLOW_FIXTURE), "--workspace", str(root)]
    assert main(argv) == 0
    plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))
    assert plan["campaign"] == "pfs0101"
    assert plan["campaign_name_from"] == "directory"
    assert all(point["run_id"].startswith("pfs0101/") for point in plan["points"])


def test_name_overrides_the_directory_and_the_record_says_so(tmp_path):
    import json

    workspace = make_planned_workspace(tmp_path)
    root = tmp_path / "pfs0101"
    workspace.root.rename(root)
    argv = ["plan", str(WORKFLOW_FIXTURE), "--workspace", str(root), "--name", "study"]
    assert main(argv) == 0
    plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))
    assert plan["campaign"] == "study"
    assert plan["campaign_name_from"] == "option"


def test_an_illegal_directory_name_is_refused_naming_the_option(tmp_path, capsys):
    workspace = make_planned_workspace(tmp_path)
    root = tmp_path / "my campaign"
    workspace.root.rename(root)
    argv = ["plan", str(WORKFLOW_FIXTURE), "--workspace", str(root)]
    with pytest.raises(SystemExit) as caught:
        main(argv)
    assert caught.value.code == 2, "a refusal of this command line exits 2, like every other"
    err = capsys.readouterr().err
    assert "--name" in err and "my campaign" in err
    # `convert` has no workspace to name a campaign after and still needs the option.
    assert (
        main(
            [
                "convert",
                str(REGISTRY_FIXTURE),
                "--fs-version",
                "26.120",
                "--fs-exe",
                "fs.exe",
                "--recipe",
                "003=m:f",
            ]
        )
        == 2
    )
    assert "--name" in capsys.readouterr().err
