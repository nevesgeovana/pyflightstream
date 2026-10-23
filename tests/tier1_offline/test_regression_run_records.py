"""Regression coverage grouped by subject."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from pyflightstream import workspace as workspace_module
from pyflightstream.run import _rebuild, cli, collect, records
from pyflightstream.workspace import CampaignWorkspace, RunRecord
from pyflightstream.workspace.naming import RunsManifestError
from pyflightstream.workspace.record_document import read_rows as _read_record_rows
from tests.tier1_offline.test_p0320_records import (
    _local_campaign as _run_1_rebuild___local_campaign,
)
from tests.tier1_offline.test_p0320_records import (
    _lose_the_manifest as _run_1_rebuild___lose_the_manifest,
)
from tests.tier1_offline.test_p0370_s1_matrix_home import (
    grouped_workspace as _run_2_rebuild__grouped_workspace,
)
from tests.tier1_offline.test_p0370_s1_matrix_home import pyfs as _run_2_rebuild__pyfs
from tests.tier1_offline.test_p0370_s1_matrix_home import (
    the_owner_s_deletions as _run_2_rebuild__the_owner_s_deletions,
)


class TestLast6Archive:
    """Every product rebuild uses the same opt-in archive policy."""

    @staticmethod
    @pytest.mark.parametrize("archive", [False, True])
    def test_p0400_last6_collect_archives_only_when_requested(tmp_path, monkeypatch, archive):
        seen = []
        report = SimpleNamespace(
            lines=lambda: [],
            failed_lines=lambda: [],
            collected=[],
            failed=[],
            outstanding=0,
            unknown=[],
        )

        def gathered(workspace, *, post_matrix, **kwargs):
            post_matrix(workspace, None)
            return report

        monkeypatch.setattr(collect, "collect_and_post", gathered)
        monkeypatch.setattr(
            workspace_module, "post_stages", lambda: [lambda ws, **kwargs: seen.append(kwargs)]
        )
        argv = ["collect", "--workspace", str(tmp_path)] + (["--archive"] if archive else [])
        assert cli.main(argv) == 0
        assert seen[0]["archive"] is archive, "P0400-LAST6-ARCHIVE"

    @staticmethod
    def test_p0400_last6_refused_confirmation_names_the_overwrite_consequence(
        tmp_path, monkeypatch, capsys
    ):
        from tests.tier1_offline.test_post_superfile import _workspace

        workspace = _workspace(tmp_path)
        monkeypatch.setattr(cli, "_confirmed_destruction", lambda yes: False)
        assert cli.main(["post", "--workspace", str(workspace.root), "--force-overwrite"]) == 2
        refusal = capsys.readouterr().err
        assert "without an archive" in refusal, "P0400-LAST6-ARCHIVE-REFUSAL"
        assert "--archive" in refusal

    @staticmethod
    @pytest.mark.parametrize("archive", [False, True])
    def test_p0400_last6_regeneration_archives_only_when_requested(tmp_path, monkeypatch, archive):
        from pyflightstream.workspace import storage
        from tests.tier1_offline.test_goal035_storage import _shared_product_workspace

        workspace = _shared_product_workspace(tmp_path, "regenerate")
        seen = []
        monkeypatch.setattr(
            storage, "post_stages", lambda: [lambda ws, **kwargs: seen.append(kwargs)]
        )
        storage.delete_sims(
            workspace.root,
            ["3001"],
            matrix_products="regenerate",
            apply=True,
            **({"archive": True} if archive else {}),
        )
        assert seen[0]["archive"] is archive, "P0400-LAST6-REGENERATE-ARCHIVE"


class TestLast6Records:
    """The persisted threshold and stopped-step records have a shared declared type."""

    @staticmethod
    def test_p0400_last6_threshold_record_has_a_declared_type():
        annotation = str(RunRecord.model_fields["export_window"].annotation)
        assert "ExportThresholdRecord" in annotation, "P0400-LAST6-RECORD-TYPE"

    @staticmethod
    def test_p0400_last6_stopped_step_record_has_a_declared_type():
        annotation = str(RunRecord.model_fields["stopped_at"].annotation)
        assert "StoppedStepRecord" in annotation, "P0400-LAST6-STOPPED-TYPE"


def _run_1_rebuild___set_hidden(matrix: Path, value: str) -> None:
    """Write ``value`` in the HIDDEN cell of every row of a pipe-table matrix."""
    lines = matrix.read_text(encoding="utf-8").splitlines()
    header = [cell.strip() for cell in lines[0].split("|")]
    column = header.index("HIDDEN")
    out = lines[:2]
    for line in lines[2:]:
        cells = line.split("|")
        if len(cells) == len(header) and line.strip() and not line.lstrip().startswith("#"):
            width = len(cells[column])
            cells[column] = f" {value}".ljust(width)
        out.append("|".join(cells))
    matrix.write_text("\n".join(out) + "\n", encoding="utf-8")


class TestRun1Rebuild:
    """Tier 1, 0.40.0 lane run-1: ``rebuild`` reconstructs a local record's command line.

    The local campaign of the 0.32.0 records tests: one steady point run here by a stand-in
    solver whose executable is on this machine, then its runs.json lost. No solver runs.
    """

    @staticmethod
    @pytest.mark.parametrize(("hidden", "flag"), [("0", False), ("1", True)])
    def test_p0400_a_rebuilt_command_line_follows_the_rows_hidden_column(
        tmp_path, monkeypatch, hidden, flag
    ):
        """P0400-REBUILD-ARGV (PFS-2103.004): one reconstruction, from SCRIPT_ARGUMENT and HIDDEN.

        With the executable on this machine the argv was always ``-hidden``, the row's HIDDEN 0
        notwithstanding, and without it never: the record depended on the rebuilding machine.
        """
        workspace, matrix, original = _run_1_rebuild___local_campaign(tmp_path, monkeypatch)
        _run_1_rebuild___set_hidden(matrix, hidden)
        _run_1_rebuild___lose_the_manifest(workspace)
        (rebuilt,) = records.rebuild(workspace.root)["records"]
        argv = rebuilt["argv"]
        assert argv[0] == original["fs_exe"] and argv[-2] == "-script", argv
        assert ("-hidden" in argv) is flag, argv
        assert rebuilt["executor"]["argv"] == argv


def _run_2_rebuild___sims_recorded(root) -> set[str]:
    return {str(row["sim_id"]) for row in _read_record_rows(root / "runs.json")}


class TestRun2Rebuild:
    """Tier 1, 0.40.0 lane run-2: ``pyfs-matrix rebuild`` refuses a simulation whole, and alone.

    Each workspace is made by the package's own run and collect
    (``test_p0370_s1_matrix_home.py``), then ``runs.json`` and the logs are
    deleted, and rebuild is run through ``pyfs-matrix`` as she runs it.
    """

    @staticmethod
    def test_p0400_rebuild_writes_no_record_of_a_simulation_it_reports_not_recoverable(
        tmp_path, capsys
    ):
        """P0400-REBUILD-WHOLE (PFS-2103.028): one empty datapoint folder refuses the whole simulation.

        The first point's record had already been appended when the second
        point's empty folder refused the simulation, so the simulation was both
        REBUILT and NOT RECOVERABLE, and the resume took the second point as
        never run.
        """  # noqa: E501
        workspace = _run_2_rebuild__grouped_workspace(tmp_path, mode="alone")
        _run_2_rebuild__the_owner_s_deletions(workspace, run_zero=False)
        folders = sorted((workspace.sim_dir("7001") / "datapoints").iterdir())
        assert len(folders) == 2, folders
        for path in folders[-1].iterdir():
            if path.is_file():
                path.unlink()
        code, said = _run_2_rebuild__pyfs(["rebuild", "--apply"], workspace.root, capsys)
        assert "7001" in said, said
        assert "7001" not in _run_2_rebuild___sims_recorded(workspace.root), said
        assert "7003" in _run_2_rebuild___sims_recorded(workspace.root), said

    @staticmethod
    def test_p0400_rebuild_refuses_a_simulation_whose_mark_cannot_be_kept_alone(
        tmp_path, capsys, monkeypatch
    ):
        """P0400-REBUILD-MARK (PFS-2095.053): a person's mark it would lose refuses that simulation.

        keep_verdict's refusal escaped the per-simulation loop and ended the
        whole rebuild.
        """
        workspace = _run_2_rebuild__grouped_workspace(tmp_path, mode="alone")
        _run_2_rebuild__the_owner_s_deletions(workspace, run_zero=False)
        real = _rebuild.keep_verdict

        def refusing(record, row):
            if str(record.get("sim_id")) == "7001":
                raise RunsManifestError("rebuild would lose marked point(s) V0300RE120AL+020")
            return real(record, row)

        monkeypatch.setattr(_rebuild, "keep_verdict", refusing)
        code, said = _run_2_rebuild__pyfs(["rebuild", "--apply"], workspace.root, capsys)
        assert "rebuild would lose marked point(s) V0300RE120AL+020" in said, said
        assert _run_2_rebuild___sims_recorded(workspace.root) == {"7003"}, said


def _run_2_records___job_workspace(tmp_path):
    """A workspace holding one steady job of three CONVERGED points, beside other records."""
    from pyflightstream.workspace import RunStatus
    from tests.tier1_offline.test_mark_failed import _record, _workspace

    workspace = _workspace(tmp_path)
    job = _record("5001", "camp/sim_5001/sweep", RunStatus.CONVERGED)
    ran = [{"tag": tag, "status": "CONVERGED"} for tag in ("AL+000", "AL+005", "AL+010")]
    workspace.append_record(job.model_copy(update={"points_ran": ran}))
    return workspace


def _run_2_records___points_of(workspace, sim):
    return {
        point.run_id: point.status.value
        for record in workspace.read_manifest()
        if record.sim_id == sim
        for point in record.as_points()
    }


class TestRun2Records:
    """Tier 1, 0.40.0 lane run-2: the records commands, the manifests they read and archive.

    Every fixture is synthetic.
    """

    @staticmethod
    def test_p0400_from_sims_name_is_refused_in_any_case(tmp_path):
        """P0400-FROM-SIMS-FOLD (PFS-2094.033): ``--runs Sims.json`` is refused like ``sims.json``.

        On a case-insensitive file system post/<matrix>@Sims/ is the folder of the
        from-sims post.
        """
        workspace = CampaignWorkspace.init(tmp_path / "camp")
        (workspace.root / "Sims.json").write_text("[]", encoding="utf-8")
        with pytest.raises(records.RunsManifestError, match="--from-sims"):
            records.manifest_workspace(workspace.root, "Sims.json")

    @staticmethod
    def test_p0400_mark_failed_numbers_a_second_archive_within_one_stamp(tmp_path, monkeypatch):
        """P0400-ARCHIVE-FREE (PFS-2096.006): two marks in one second keep both copies of runs.json.

        The hand-built name overwrote the first copy; free_root_archive numbers
        the second ``.2``, which restore finds.
        """
        from tests.tier1_offline.test_mark_failed import _workspace

        workspace = _workspace(tmp_path)
        monkeypatch.setattr(records, "_now_stamp", lambda: "20261012-120000")
        first = workspace.manifest_path.read_bytes()
        records.mark_failed(workspace.root, ["2006"], reason="first", apply=True)
        second = workspace.manifest_path.read_bytes()
        records.mark_failed(workspace.root, ["2008"], reason="second", apply=True)
        archive = workspace.root / "archive"
        assert (archive / "runs-20261012-120000.json").read_bytes() == first
        assert (archive / "runs-20261012-120000.2.json").read_bytes() == second

    @staticmethod
    def test_p0400_mark_failed_refuses_a_named_point_no_record_holds(tmp_path):
        """P0400-MARK-UNKNOWN-POINT (PFS-2094.019): a point planned but not run is refused by name.

        The alias resolves through plan.json to a point with no record; the
        mark matched nothing and exited 0 in silence.
        """
        from tests.tier1_offline.test_mark_failed import _workspace

        workspace = _workspace(tmp_path)
        before = workspace.manifest_path.read_bytes()
        refusal = r"no record of point AL\+010 in simulation 2006"
        with pytest.raises(records.RunsManifestError, match=refusal):
            records.mark_failed(workspace.root, [], points={"2006": ["AL+010"]}, apply=True)
        assert workspace.manifest_path.read_bytes() == before

    @staticmethod
    def test_p0400_mark_failed_marks_every_point_of_a_job_marked_whole(tmp_path):
        """P0400-MARK-JOB (PFS-2103.010): each points_ran entry of a job marked whole is FAILED_MARKED.

        The post reads each point's status from its entry (as_points), so a job
        marked at its top alone kept every point CONVERGED and admitted.
        """  # noqa: E501
        from pyflightstream.post._products_campaign import _ADMITTED_WHEN_CHECKING
        from pyflightstream.workspace import RunStatus

        workspace = _run_2_records___job_workspace(tmp_path)
        entry = records.mark_failed(workspace.root, ["5001"], reason="wrong mesh", apply=True)
        points = _run_2_records___points_of(workspace, "5001")
        assert set(points.values()) == {"FAILED_MARKED"}, points
        assert RunStatus.FAILED_MARKED not in _ADMITTED_WHEN_CHECKING
        assert sorted(item["run_id"] for item in entry["marked"]) == sorted(points)
        (row,) = [r for r in workspace.read_raw_manifest() if r.get("sim_id") == "5001"]
        assert row["status"] == "FAILED_MARKED" and row["marked"]["from"] == "CONVERGED"
        assert all(e["marked"]["reason"] == "wrong mesh" for e in row["points_ran"])

    @staticmethod
    def test_p0400_mark_failed_marks_the_one_point_of_a_job_an_alias_names(tmp_path):
        """P0400-MARK-JOB (PFS-2103.009): an alias of one job point marks that entry alone.

        row_selected takes the whole job row when any of its points matches, so
        every point of the job was marked FAILED_MARKED.
        """
        workspace = _run_2_records___job_workspace(tmp_path)
        records.mark_failed(workspace.root, [], points={"5001": ["AL+005"]}, apply=True)
        assert _run_2_records___points_of(workspace, "5001") == {
            "camp/sim_5001/AL+000": "CONVERGED",
            "camp/sim_5001/AL+005": "FAILED_MARKED",
            "camp/sim_5001/AL+010": "CONVERGED",
        }
        (row,) = [r for r in workspace.read_raw_manifest() if r.get("sim_id") == "5001"]
        assert "marked" not in row  # the person judged one point, not the job

    @staticmethod
    @pytest.mark.parametrize("sims", ["2006,2007", "2006"])
    def test_p0400_mark_failed_refuses_a_bare_string_of_ids(tmp_path, sims):
        """P0400-SIMS-STRING (PFS-2089.009): a str is refused in Python terms, never iterated.

        ``"2006,2007"`` read character by character was refused as simulations
        2, 0, 6, and the message told a Python caller to write the ids comma separated.
        """
        from tests.tier1_offline.test_mark_failed import _workspace

        workspace = _workspace(tmp_path)
        with pytest.raises(records.RunsManifestError, match=r"sims takes a list of ids, e\.g\. \["):
            records.mark_failed(workspace.root, sims)
