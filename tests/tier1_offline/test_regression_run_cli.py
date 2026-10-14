"""Regression coverage grouped by subject."""

from __future__ import annotations

import pytest

from pyflightstream.run import _cli_query_point, cli
from pyflightstream.run._cli_parsers import _build_parser, parsed
from pyflightstream.workspace import CampaignWorkspace, MeshAudit, costs, hpc
from tests.tier1_offline import test_p0350_run_id_alias as _run_1_cli_query__alias_tests
from tests.tier1_offline.test_p0390_rev38_mesh_cli import _run as _run_1_cli_mesh___run
from tests.tier1_offline.test_p0390_rev38_mesh_cli import _source as _run_1_cli_mesh___source


class TestRun1Cli:
    """Tier 1, 0.40.0 lane run-1: the ``pyfs-matrix`` parser (``_cli_parsers``), in process.

    Synthetic workspaces; no solver runs.
    """

    @staticmethod
    def test_p0400_hpc_and_cost_file_belong_to_the_command_that_named_them(tmp_path, capsys):
        """P0400-SELECTION-PER-INVOCATION (PFS-2094.008): no leak into a later in-process command.

        ``--hpc`` and ``--cost-file`` were selected by argparse's type callable and never reset,
        so a second ``main`` in the same process ran under the first one's profile.
        """
        workspace = CampaignWorkspace.init(tmp_path / "camp")
        argv = ["plan", str(tmp_path / "absent.fs"), "--workspace", str(workspace.root)]
        cli.main([*argv, "--hpc", "h9", "--cost-file", "c9"])
        capsys.readouterr()
        assert hpc._SELECTED_HPC.get() is None
        assert costs._SELECTED_COST_FILE.get() is None

    @staticmethod
    def test_p0400_restore_reads_a_matrix_path_as_rebuild_and_post_do(tmp_path):
        """P0400-MATRIX-OPTION-FORM (PFS-2094.051): ``restore --matrix`` takes a path or a stem.

        ``rebuild`` and ``post`` read ``--matrix`` as a path and take its stem; ``restore``
        passed the text through, so a path named no archived matrix.
        """
        workspace = str(tmp_path)
        for given in ("inputs/matrices/m001.fs", "m001"):
            args = parsed(
                _build_parser(), ["restore", "plan", "--matrix", given, "--workspace", workspace]
            )
            assert args.matrix == "m001"

    @staticmethod
    @pytest.mark.parametrize(
        "argv",
        [
            ["space-in-use", "--top", "-1"],
            ["space-in-use", "--top", "0"],
            ["collect", "--rounds", "0"],
        ],
    )
    def test_p0400_a_count_below_one_is_refused_naming_its_flag(tmp_path, capsys, argv):
        """P0400-COUNT-AT-LEAST-ONE (PFS-2097.009): ``--top -1`` showed all rows but one and
        mislabelled the hidden count; ``--top`` and ``--rounds`` now refuse a count below 1."""
        with pytest.raises(SystemExit) as raised:
            cli.main([*argv, "--workspace", str(tmp_path)])
        assert raised.value.code == 2
        # The parameter beside its flag (test_error_messages: no refusal names a flag alone).
        assert f"(CLI: {argv[1]}) takes a whole number of at least 1" in capsys.readouterr().err


class TestRun1CliMesh:
    """Tier 1, 0.40.0 lane run-1: ``pyfs-matrix audit-mesh``, in process.

    The synthetic panel meshes of the 0.38.0 tests; no solver runs.
    """

    @staticmethod
    def test_p0400_audit_mesh_states_the_exit_of_a_csv_it_cannot_write(
        tmp_path, capsys, monkeypatch
    ):
        """P0400-AUDIT-MESH-CSV-EXIT (PFS-2094.035): the help says what exit 2 also covers.

        The audit is written and only the --out CSV fails; the command exits 2 and names the
        audit written, and the help, which said 2 meant a refused input, now says so too.
        """
        src = _run_1_cli_mesh___source(tmp_path)

        def refuse(self, path):
            raise PermissionError(13, "Permission denied", str(path))

        monkeypatch.setattr(MeshAudit, "write_csv", refuse)
        code, _, err, _ = _run_1_cli_mesh___run(
            capsys, "audit-mesh", str(src), "--out", str(tmp_path / "a.csv")
        )
        assert code == 2 and "could not be written" in err and ".audit.json was written" in err
        with pytest.raises(SystemExit):
            cli.main(["audit-mesh", "--help"])
        help_text = " ".join(capsys.readouterr().out.split())
        assert "when the --out CSV cannot be written after the audit was" in help_text


class TestRun1CliQuery:
    """Tier 1, 0.40.0 lane run-1: the query verbs ``status`` and ``show``, in process.

    Synthetic workspaces and records; no solver runs.
    """

    @staticmethod
    def test_p0400_status_additional_refuses_the_selection_it_does_not_read(tmp_path, capsys):
        """P0400-STATUS-ADDITIONAL-SELECTION (PFS-2094.030): ``--sims`` with ``--additional``.

        The register listing read no selection and printed it whole, silently; the selection
        flags are now refused by name, and the listing alone still runs.
        """
        workspace = CampaignWorkspace.init(tmp_path / "camp")
        root = str(workspace.root)
        code = cli.main(
            ["status", "--additional", "--sims", "2006", "--failed", "--workspace", root]
        )
        err = capsys.readouterr().err
        assert code == 2 and "--sims, --failed" in err and "--additional" in err
        assert cli.main(["status", "--additional", "--workspace", root]) == 0

    @staticmethod
    def test_p0400_show_names_the_point_it_cannot_find(tmp_path, capsys):
        """P0400-SHOW-UNKNOWN-POINT (PFS-2100.005, PFS-2100.006): ``show 2006 --point NOPE``.

        The refusal read ``run (CLI: --run): '' names no effective recorded point``, naming a
        flag show does not take and an empty string. It now names the simulation and the point
        typed, and lists the simulation's points with their aliases.
        """
        workspace = CampaignWorkspace.init(tmp_path / "camp")
        for tag in ("AL+000", "AL+020"):
            workspace.append_record(
                _run_1_cli_query__alias_tests._record("2006", f"warm/sim_2006/{tag}")
            )
        root = str(workspace.root)
        code = cli.main(["show", "2006", "--point", "NOPE", "--workspace", root])
        err = capsys.readouterr().err
        assert code == 1
        assert "'2006'" in err and "'NOPE'" in err and "--run" not in err, err
        assert "AL+000 (2006_1)" in err and "AL+020 (2006_2)" in err, err
        assert cli.main(["show", "2006", "--point", "AL+020", "--workspace", root]) == 0


_RUN_2_CLI___TRIANGLE_STL = (
    "solid wing\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\n"
    "vertex 0 1 0\nendloop\nendfacet\nendsolid wing\n"
)


class TestRun2Cli:
    """Tier 1, 0.40.0 lane run-2: the pyfs-matrix command line and its query output.

    Every fixture is synthetic.
    """

    @staticmethod
    @pytest.mark.parametrize("seconds", ["0", "-1", "inf"])
    def test_p0400_collect_interval_takes_seconds_above_zero(tmp_path, capsys, seconds):
        """P0400-COLLECT-INTERVAL (PFS-2081.28): --interval 0 or below is refused at parse time.

        Zero disables the settle check (both observations at one instant), and a
        negative value reached ``time.sleep`` mid-sweep.
        """
        workspace = CampaignWorkspace.init(tmp_path / "camp")
        argv = ["collect", "--workspace", str(workspace.root), "--interval", seconds]
        assert cli.main(argv) == 2
        assert (
            "interval (CLI: --interval) takes a number of seconds above 0"
            in capsys.readouterr().err
        )

    @staticmethod
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

    @staticmethod
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

    @staticmethod
    def test_p0400_plan_reports_a_manifest_refusal_without_a_traceback(
        tmp_path, capsys, monkeypatch
    ):
        """P0400-PLAN-REFUSAL (PFS-2095.051): a WorkspaceError of read_manifest exits 2 with its text.

        It is a PyflightstreamError and neither a ValueError nor an OSError, so
        the plan let it through as a traceback, the defect ``run`` already fixed.
        """  # noqa: E501
        from pyflightstream.workspace import WorkspaceError
        from tests.tier1_offline.test_workflows import (
            _fr313_plan_geometry_warning___planned as _planned,
        )

        workspace, matrix, _, _, _ = _planned(tmp_path, "unsteady", "clean")

        def refused(self):
            raise WorkspaceError("the recorded surface averaging window does not validate")

        monkeypatch.setattr(CampaignWorkspace, "read_manifest", refused)
        assert cli.main(["plan", str(matrix), "--workspace", str(workspace.root)]) == 2
        assert "the recorded surface averaging window does not validate" in capsys.readouterr().err

    @staticmethod
    def test_p0400_collect_post_refusal_is_said_as_the_post_s_and_exits_2(
        tmp_path, capsys, monkeypatch
    ):
        """P0400-COLLECT-POST-REFUSAL (PFS-2095.052): a product refusal under collect is no traceback.

        ``post`` catches the stages' refusals; ``collect --post`` let one escape
        after the records were written. It is said as the post's own and exits 2.
        """  # noqa: E501
        from pyflightstream._errors import ProductError
        from pyflightstream.workspace import RunStatus
        from tests.tier1_offline.test_goal028_hpc_collect import (
            _loads,
            _submitted_workspace,
            _work_dir,
        )

        workspace, sim = _submitted_workspace(tmp_path, declared=("loads.txt",))
        work = _work_dir(workspace, sim, alpha=2.0)
        (work / "loads.txt").write_text(_loads(2.0), encoding="utf-8")

        def stage(ws, **keywords):
            raise ProductError("the probe plane lies outside the mesh")

        monkeypatch.setattr("pyflightstream.workspace.post_stages", lambda: [stage])
        status = cli.main(["collect", "--workspace", str(workspace.root), "--interval", "0.001"])
        assert status == 2
        err = capsys.readouterr().err
        assert "the post was refused: the probe plane lies outside the mesh" in err
        assert workspace.read_manifest()[0].status is RunStatus.CONVERGED

    @staticmethod
    @pytest.mark.parametrize("clean", [False, True])
    def test_p0400_inventory_reads_an_stl_as_a_raw_mesh(tmp_path, capsys, clean):
        """P0400-INVENTORY-RAW (PFS-2094.036): an STL is a raw mesh, never a saved simulation.

        write_inventory's refusal of an STL comes first: no saved-action warning,
        and no --clean run on it.
        """
        stl = tmp_path / "wing.stl"
        stl.write_text(_RUN_2_CLI___TRIANGLE_STL, encoding="utf-8")
        argv = ["inventory", str(stl), *(["--clean"] if clean else [])]
        assert cli.main(argv) == 2
        err = capsys.readouterr().err
        assert "carries no mesh block" in err
        assert "saved unsteady" not in err
        assert sorted(p.name for p in tmp_path.iterdir()) == ["wing.stl"]

    @staticmethod
    def test_p0400_inventory_refuses_clean_on_an_obj(tmp_path, capsys):
        """P0400-INVENTORY-RAW (PFS-2094.036): --clean on an OBJ is refused, not ignored."""
        obj = tmp_path / "wing.obj"
        obj.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\ng wing\nf 1 2 3\n", encoding="utf-8")
        assert cli.main(["inventory", str(obj), "--clean"]) == 2
        assert "is a raw mesh, which carries no saved solver action" in capsys.readouterr().err
        assert sorted(p.name for p in tmp_path.iterdir()) == ["wing.obj"]
