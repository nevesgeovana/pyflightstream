"""Tier 1, 0.40.0 lane run-2: the pyfs-matrix command line and its query output.

Every fixture is synthetic.
"""

from __future__ import annotations

import pytest

from pyflightstream.run import _cli_query_point, cli
from pyflightstream.workspace import CampaignWorkspace


@pytest.mark.parametrize("seconds", ["0", "-1", "inf"])
def test_p0400_collect_interval_takes_seconds_above_zero(tmp_path, capsys, seconds):
    """P0400-COLLECT-INTERVAL (PFS-2081.28): --interval 0 or below is refused at parse time.

    Zero disables the settle check (both observations at one instant), and a
    negative value reached ``time.sleep`` mid-sweep.
    """
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    argv = ["collect", "--workspace", str(workspace.root), "--interval", seconds]
    assert cli.main(argv) == 2
    assert "interval (CLI: --interval) takes a number of seconds above 0" in capsys.readouterr().err


def test_p0400_query_alias_survives_a_campaign_named_sim_something():
    """P0400-QUERY-ALIAS (PFS-2094.032): the simulation is the run id's second last part.

    A workspace folder called ``sim_runs`` names the campaign, so the first
    ``sim_`` part of the run id is the campaign, not the simulation.
    """
    aliases = {("2006", "a+02.0_b+00.0"): "2006_1"}
    row = {"run_id": "sim_runs/sim_2006/a+02.0_b+00.0"}
    assert _cli_query_point._annotate(row, aliases)["run_id_alias"] == "2006_1"
    plain = {"run_id": "campaign/sim_2006/a+02.0_b+00.0"}
    assert _cli_query_point._annotate(plain, aliases)["run_id_alias"] == "2006_1"


def test_p0400_plan_refuses_the_arguments_before_writing_anything(tmp_path, capsys):
    """P0400-PLAN-ORDER (PFS-2096.023): a contradiction between two flags writes nothing.

    The setup guides were written, and then the two spellings of the
    missing-family choice refused the plan.
    """
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    before = sorted(p.relative_to(workspace.root) for p in workspace.root.rglob("*"))
    argv = [
        "plan",
        str(workspace.root / "matrix.fs"),
        "--workspace",
        str(workspace.root),
        "--setup-guidelines",
        "--fs-version",
        "26.120",
        "--no-ignore-missing-families",
        "--ignore-missing-families",
        "false",
    ]
    with pytest.raises(SystemExit) as stopped:
        cli.main(argv)
    assert stopped.value.code == 2
    assert "were both stated" in capsys.readouterr().err
    assert sorted(p.relative_to(workspace.root) for p in workspace.root.rglob("*")) == before


def test_p0400_plan_reports_a_manifest_refusal_without_a_traceback(tmp_path, capsys, monkeypatch):
    """P0400-PLAN-REFUSAL (PFS-2095.051): a WorkspaceError of read_manifest exits 2 with its text.

    It is a PyflightstreamError and neither a ValueError nor an OSError, so
    the plan let it through as a traceback, the defect ``run`` already fixed.
    """
    from pyflightstream.workspace import WorkspaceError
    from tests.tier1_offline.test_fr313_plan_geometry_warning import _planned

    workspace, matrix, _, _, _ = _planned(tmp_path, "unsteady", "clean")

    def refused(self):
        raise WorkspaceError("the recorded surface averaging window does not validate")

    monkeypatch.setattr(CampaignWorkspace, "read_manifest", refused)
    assert cli.main(["plan", str(matrix), "--workspace", str(workspace.root)]) == 2
    assert "the recorded surface averaging window does not validate" in capsys.readouterr().err


_TRIANGLE_STL = (
    "solid wing\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\n"
    "vertex 0 1 0\nendloop\nendfacet\nendsolid wing\n"
)


@pytest.mark.parametrize("clean", [False, True])
def test_p0400_inventory_reads_an_stl_as_a_raw_mesh(tmp_path, capsys, clean):
    """P0400-INVENTORY-RAW (PFS-2094.036): an STL is a raw mesh, never a saved simulation.

    write_inventory's refusal of an STL comes first: no saved-action warning,
    and no --clean run on it.
    """
    stl = tmp_path / "wing.stl"
    stl.write_text(_TRIANGLE_STL, encoding="utf-8")
    argv = ["inventory", str(stl), *(["--clean"] if clean else [])]
    assert cli.main(argv) == 2
    err = capsys.readouterr().err
    assert "carries no mesh block" in err
    assert "saved unsteady" not in err
    assert sorted(p.name for p in tmp_path.iterdir()) == ["wing.stl"]


def test_p0400_inventory_refuses_clean_on_an_obj(tmp_path, capsys):
    """P0400-INVENTORY-RAW (PFS-2094.036): --clean on an OBJ is refused, not ignored."""
    obj = tmp_path / "wing.obj"
    obj.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\ng wing\nf 1 2 3\n", encoding="utf-8")
    assert cli.main(["inventory", str(obj), "--clean"]) == 2
    assert "is a raw mesh, which carries no saved solver action" in capsys.readouterr().err
    assert sorted(p.name for p in tmp_path.iterdir()) == ["wing.obj"]
