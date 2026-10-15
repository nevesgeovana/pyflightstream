"""Regression coverage grouped by subject."""

from __future__ import annotations

import ctypes
import inspect
import json
import typing
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream.run import LoadsAssessor, collect, matrix
from pyflightstream.run import _solver_windows as windows
from pyflightstream.run._solver_windows import WindowDiagnostic, select_owned_dialogs
from pyflightstream.run._wake_edge_verdict import (
    ACTUATOR_PROFILE_REFUSALS,
    actuator_profile_verdict,
    collected_log_texts,
)
from pyflightstream.run.collect import collect_once
from pyflightstream.run.records import mark_converged, mark_failed
from pyflightstream.workspace import RunStatus
from pyflightstream.workspace.naming import RunsManifestError
from pyflightstream.workspace.record_document import read_rows as _read_record_rows
from tests.support_helpers import no_sleep as _run_1_collect___no_sleep
from tests.support_helpers import no_sleep as _run_1_collect_logs___no_sleep
from tests.tier1_offline.test_collect_stage import (
    _submitted_workspace as _run_1_collect_logs___submitted_workspace,
)
from tests.tier1_offline.test_goal024_profile_log import LOG_TABLE as _RUN_1_COLLECT__LOG_TABLE
from tests.tier1_offline.test_goal024_profile_log import _work_dir as _run_1_collect_logs___work_dir
from tests.tier1_offline.test_goal024_profile_log import (
    _write_profile as _run_1_collect___write_profile,
)
from tests.tier1_offline.test_goal024_profile_log import (
    _write_profile as _run_1_collect_logs___write_profile,
)
from tests.tier1_offline.test_goal035_l1_defects import (
    _clocked_wheel as _run_1_assessment___clocked_wheel,
)
from tests.tier1_offline.test_goal035_l1_defects import (
    _clocked_wheel as _run_2_assessment___clocked_wheel,
)
from tests.tier1_offline.test_goal036_qsteady_record import _spoiled as _run_2_assessment___spoiled
from tests.tier1_offline.test_mark_failed import _record as _run_2_marks___record
from tests.tier1_offline.test_mark_failed import _workspace as _run_2_marks___workspace
from tests.tier1_offline.test_matrix_cli import (
    WORKFLOW_FIXTURE as _LAST6_SELECTION__WORKFLOW_FIXTURE,
)
from tests.tier1_offline.test_matrix_cli import (
    make_planned_workspace as _last6_selection__make_planned_workspace,
)
from tests.tier1_offline.test_p0350_batch_collect import _converged as _run_1_collect___converged
from tests.tier1_offline.test_p0350_batch_collect import _cumulative as _run_1_collect___cumulative
from tests.tier1_offline.test_p0350_batch_collect import _status as _run_1_collect___status
from tests.tier1_offline.test_p0350_batch_collect import _workspace as _run_1_collect___workspace
from tests.tier1_offline.test_p0370_s1_mark_converged import REASON as _RUN_1_MARK_CONVERGED__REASON
from tests.tier1_offline.test_p0370_s1_mark_converged import _rows as _run_1_mark_converged___rows
from tests.tier1_offline.test_p0370_s1_mark_converged import (
    workspace as _run_1_mark_converged__workspace,
)
from tests.tier1_offline.test_p0370_s1_matrix_home import pyfs as _run_1_mark_converged__pyfs


class TestLast6Selection:
    """Matrix selections determine build refusals and solver window mode."""

    pytestmark = pytest.mark.requirement("P0400-LAST6-SELECTION")

    @staticmethod
    @pytest.mark.parametrize("selection", [{"sims": ["7002"]}, {"points": ["7002_1"]}])
    def test_p0400_last6_unselected_silent_row_does_not_refuse_plan(tmp_path, selection):
        workspace = _last6_selection__make_planned_workspace(tmp_path)
        path = tmp_path / "selected.fs"
        path.write_text(
            _LAST6_SELECTION__WORKFLOW_FIXTURE.read_text(encoding="utf-8").replace(
                "| 26.120   |", "|          |", 1
            ),
            encoding="utf-8",
        )
        plan = matrix.plan_matrix(path, workspace, name="selected", recipes={}, **selection)
        assert {point.sim_id for point in plan.points} == {"7002"}, "P0400-LAST6-SELECT-BUILD"

    @staticmethod
    def test_p0400_last6_hidden_is_decided_by_selected_cases(tmp_path, monkeypatch):
        from pyflightstream.cases import Campaign, SimCase, SweepAxis
        from pyflightstream.workspace import CampaignWorkspace
        from pyflightstream.workspace.matrix import ResolvedMatrix

        case = SimCase(
            sim_id="7002",
            aircraft="Rig",
            recipe="steady",
            sweep=SweepAxis(type="alpha", values=[0.0]),
            variables={"matrix_hidden": True},
        )
        resolved = ResolvedMatrix(
            campaign=Campaign(
                name="selected", fs_version="26.124", fs_exe="solver.exe", sims=[case]
            )
        )
        monkeypatch.setattr(matrix, "on_a_cluster", lambda: False)
        seen = []
        monkeypatch.setattr(
            matrix, "LocalExecutor", lambda exe, **kwargs: seen.append(kwargs) or object()
        )
        path = tmp_path / "matrix.fs"
        lines = _LAST6_SELECTION__WORKFLOW_FIXTURE.read_text(encoding="utf-8").splitlines()
        cells = lines[2].split("|")
        cells[1] = " 0 "
        lines[2] = "|".join(cells)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        matrix._campaign_executor(CampaignWorkspace.init(tmp_path / "camp"), resolved, path)
        assert seen[0]["hidden"] is True, "P0400-LAST6-SELECT-HIDDEN"


class TestRun1Assessment:
    """Tier 1, 0.40.0 lane run-1: the collect's assessor (FR-434 on a quasi-steady wheel).

    The wheel fixture of the 0.30.0 tests: a log of one solve per clocking, each loads
    export written at its solve's last iteration, a requested limit of 500.
    """

    @staticmethod
    def test_p0400_a_wheel_clocking_at_its_iteration_limit_is_max_iter_reached(tmp_path):
        """P0400-WHEEL-MAX-ITER (PFS-2103.018, PFS-2103.020): two clockings, one stopped at 500.

        A one-clocking point with the same evidence is MAX_ITER_REACHED (FR-434); the clocking
        path folded the solves without FR-434 and recorded COMPLETED_MAX_ITER. The point and
        the clocking now carry MAX_ITER_REACHED, the requested limit and the note naming it.
        """
        case, sim = _run_1_assessment___clocked_wheel(tmp_path, (4.0e-5, 3.0e-6), (500, 61))
        assessment = LoadsAssessor()(case, None, sim)
        assert assessment.status is RunStatus.MAX_ITER_REACHED, assessment.error
        assert assessment.iterations_requested == 500
        verdicts = assessment.clocking_verdicts
        assert verdicts is not None
        assert [(v["index"], v["status"]) for v in verdicts] == [
            (1, "MAX_ITER_REACHED"),
            (0, "CONVERGED"),
        ]
        assert "iteration limit (500)" in str(verdicts[0]["note"])
        assert "clocking 1" in (assessment.residual_note or "")

    @staticmethod
    def test_p0400_a_wheel_short_of_its_limit_keeps_completed_max_iter(tmp_path):
        """P0400-WHEEL-MAX-ITER (PFS-2103.020): the control, a clocking unsettled at 400 of 500."""
        case, sim = _run_1_assessment___clocked_wheel(tmp_path, (4.0e-5, 3.0e-6), (400, 61))
        assessment = LoadsAssessor()(case, None, sim)
        assert assessment.status is RunStatus.COMPLETED_MAX_ITER, assessment.error
        assert assessment.iterations_requested is None


class TestRun1Collect:
    """Tier 1, 0.40.0 lane run-1: collect over the points of a grouped job (FR-369).

    Hand-built workspaces of the 0.35.0 batch collect tests; no solver runs.
    """

    @staticmethod
    def test_p0400_a_point_the_job_never_started_fails_under_export_log_false(tmp_path):
        """P0400-NOT-STARTED-NATIVE-LOG (PFS-2103.023): the job's shared log is not the point's file.

        With ``export_log = false`` the job's native log exists for every point once the job
        started, and it counted as the never-started point's own file, so FR-369 never fired.
        """  # noqa: E501
        workspace, job_dir, _ = _run_1_collect___workspace(tmp_path, "batch", written=("AL+000",))
        _run_1_collect___write_profile(workspace, _RUN_1_COLLECT__LOG_TABLE)
        own = job_dir / "sim_2006" / "datapoints" / "DP-AL+000" / "P2006-AL+000.cumulative-log.txt"
        own.unlink()
        (job_dir / "FTSmtx_b1.l3714205").write_bytes(_run_1_collect___cumulative(1).encode())
        (job_dir / "BATCH-2006-2006.end.json").write_bytes(b'{"returncode": 0}\n')
        collect_once(
            workspace,
            interval=0.0,
            sleep=_run_1_collect___no_sleep,
            assessor=_run_1_collect___converged,
        )
        second = _run_1_collect___status(workspace, "AL+020")
        assert second.status is RunStatus.FAILED_EXECUTION, second.status
        assert second.error == "the job BATCH-2006-2006 ended before this point started"
        assert _run_1_collect___status(workspace, "AL+000").status is RunStatus.CONVERGED


class TestRun1CollectLogs:
    """Tier 1, 0.40.0 lane run-1: how collect reads a point's solver log (the HPC profile's globs).

    The submitted workspace of the collect tests and a hand-written profile; no solver runs.
    Since 0.40.0 the profile reader refuses an unknown native_log placeholder when the profile
    is read (PFS-2095.026), before any point; the invalid-access cases (``{sim.missing}``,
    ``{sim[bad]}``), ordinary and grouped, and the unchanged manifest are pinned in
    ``test_p0400_integfix_run1_review.py``. This file keeps what that one does not assert.
    """

    @staticmethod
    def test_p0400_a_native_log_placeholder_no_point_fills_is_a_refusal_not_a_traceback(tmp_path):
        """P0400-NATIVE-LOG-PLACEHOLDER (PFS-2095.026): ``native_log = "FTS{Sim}.l*"``, a typo.

        The per-record collect once formatted the glob with ``{sim}`` and ``{point}`` alone and
        let the KeyError out, so collect ended in a traceback. The profile reader now refuses
        the placeholder when the profile is read, naming it and the placeholders a point fills,
        which is the remedy the reader needs.
        """
        workspace, sim = _run_1_collect_logs___submitted_workspace(
            tmp_path, declared=("loads.txt", "P9001-AL+000_log.txt")
        )
        _run_1_collect_logs___write_profile(
            workspace, '\n[log]\nexport_log = false\nnative_log = "FTS{Sim}.l*"\n'
        )
        (_run_1_collect_logs___work_dir(workspace, sim) / "loads.txt").write_text(
            "data", encoding="utf-8"
        )
        with pytest.raises(InputArtifactError) as raised:
            collect_once(workspace, interval=0.0, sleep=_run_1_collect_logs___no_sleep)
        message = str(raised.value)
        assert "native_log" in message and "{Sim}" in message, message
        assert "{sim}" in message and "{point}" in message, message


def _run_1_mark_converged___job(workspace) -> dict:
    (row,) = [
        row for row in _run_1_mark_converged___rows(workspace).values() if row["sim_id"] == "7002"
    ]
    return row


class TestRun1MarkConverged:
    """Tier 1, 0.40.0 lane run-1: mark-converged (FR-414) over the package's own grouped run.

    The workspace of the 0.37.0 tests: three rows collected without their logs, row 7002 a
    two-point steady job. No solver runs.
    """

    workspace = staticmethod(_run_1_mark_converged__workspace)

    @staticmethod
    def test_p0400_a_point_of_a_job_marked_failed_is_refused(workspace, capsys):  # noqa: F811
        # Verifies FR-414.
        """P0400-MARK-CONVERGED-JOB-MARKED (PFS-2103.031): mark-failed 7002, then one of its points.

        mark-failed marks the job's row and leaves its points' statuses, and mark-converged read
        the points only, so it replaced the person's FAILED_MARKED by a computed status.
        """
        mark_failed(workspace.root, ["7002"], reason="wrong mesh", apply=True)
        tag = _run_1_mark_converged___job(workspace)["points_ran"][0]["tag"]
        before = workspace.manifest_path.read_bytes()
        with pytest.raises(RunsManifestError, match="marked failed by a person"):
            mark_converged(
                workspace.root,
                ["7002"],
                points=[tag],
                reason=_RUN_1_MARK_CONVERGED__REASON,
                apply=True,
            )
        assert workspace.manifest_path.read_bytes() == before

    @staticmethod
    def test_p0400_a_jobs_own_failure_outlives_a_points_verdict(workspace):  # noqa: F811
        """P0400-MARK-CONVERGED-JOB-FAILURE (PFS-2103.031): the job failed, no point did.

        The row's status was recomputed from its points alone, so a job-level FAILED_EXECUTION
        no point carries became CONVERGED once the points were.
        """
        rows = _read_record_rows(workspace.manifest_path)
        for row in rows:
            if row["sim_id"] == "7002":
                row["status"] = "FAILED_EXECUTION"
        workspace._replace_manifest(rows)
        mark_converged(workspace.root, ["7002"], reason=_RUN_1_MARK_CONVERGED__REASON, apply=True)
        job = _run_1_mark_converged___job(workspace)
        assert [point["status"] for point in job["points_ran"]] == ["CONVERGED", "CONVERGED"]
        assert job["status"] == "FAILED_EXECUTION"

    @staticmethod
    def test_p0400_an_unreadable_manifest_is_a_refusal_not_a_traceback(workspace, capsys):  # noqa: F811
        """P0400-MARK-CONVERGED-UNREADABLE (PFS-2095.050): corrupt JSON, then an unknown status."""
        good = workspace.manifest_path.read_text("utf-8")
        workspace.manifest_path.write_text(good[:-20], encoding="utf-8")
        code, said = _run_1_mark_converged__pyfs(
            ["mark-converged", "--sims", "7002", "--reason", _RUN_1_MARK_CONVERGED__REASON],
            workspace.root,
            capsys,
        )
        assert code == 2 and "cannot read run records" in said, said
        from pyflightstream.workspace.record_document import decode_document

        rows = decode_document(json.loads(good))
        for row in rows:
            if row["sim_id"] == "7002":
                row["points_ran"][0]["status"] = "HALF_DONE"
                run_id, other = row["run_id"], row["points_ran"][1]["tag"]
        workspace._replace_manifest(rows)
        argv = [
            "mark-converged",
            "--sims",
            "7002",
            "--points",
            other,
            "--reason",
            _RUN_1_MARK_CONVERGED__REASON,
            "--apply",
        ]
        code, said = _run_1_mark_converged__pyfs(argv, workspace.root, capsys)
        assert code == 2 and "HALF_DONE" in said and run_id in said, said

    @staticmethod
    def test_p0400_the_preview_of_a_refused_point_does_not_suggest_apply(workspace, capsys):  # noqa: F811
        """P0400-MARK-CONVERGED-PREVIEW-HINT (PFS-2100.016): every named point is refused.

        The preview said 'run again with --apply', which then refuses. It now says that each
        refusal must be resolved first.
        """
        mark_failed(workspace.root, ["7003"], reason="wrong mesh", apply=True)
        code, said = _run_1_mark_converged__pyfs(
            ["mark-converged", "--sims", "7003", "--reason", _RUN_1_MARK_CONVERGED__REASON],
            workspace.root,
            capsys,
        )
        assert code == 0, said
        assert "run again with --apply" not in said, said
        assert "resolve each refusal" in said, said


class TestRun1ReviewWindows:
    """Exercise bounded native window reads without opening a desktop window."""

    @staticmethod
    def test_p0400_review_native_timeout_does_not_turn_a_splash_into_a_dialog(monkeypatch):
        """P0400-REVIEW-NATIVE-SPLASH: the native reader itself must preserve unread text."""
        pid = 7

        def owner(_handle, pointer):
            pointer._obj.value = pid
            return 1

        def class_name(handle, buffer, _length):
            buffer.value = "#32770" if handle == 1 else "Static"
            return len(buffer.value)

        native = SimpleNamespace(
            EnumWindows=Mock(side_effect=lambda callback, parameter: callback(1, parameter)),
            EnumChildWindows=Mock(
                side_effect=lambda handle, callback, parameter: callback(2, parameter)
            ),
            GetWindowThreadProcessId=Mock(side_effect=owner),
            IsWindowVisible=Mock(return_value=True),
            IsWindowEnabled=Mock(return_value=False),
            GetWindow=Mock(return_value=3),
            GetWindowTextW=Mock(return_value=0),
            GetClassNameW=Mock(side_effect=class_name),
            SendMessageTimeoutW=Mock(return_value=0),
        )
        monkeypatch.setattr(windows.sys, "platform", "win32")
        monkeypatch.setattr(ctypes, "WinDLL", lambda *args, **kwargs: native, raising=False)
        monkeypatch.setattr(
            ctypes, "WINFUNCTYPE", lambda *args: lambda callback: callback, raising=False
        )
        snapshots = windows._native_windows(pid)
        assert len(snapshots) == 1
        assert windows.select_owned_dialogs(pid, snapshots) == ()
        assert snapshots[0].text == ""
        native.SendMessageTimeoutW.assert_called_once()


_RUN_1_WINDOWS_AND_LOGS__UNREAD = "[control text unavailable or timed out]"


class TestRun1WindowsAndLogs:
    """Tier 1, 0.40.0 lane run-1: the window watcher's splash rule and the G06 log scan.

    Window snapshots and log files written by hand; no solver and no GUI.
    """

    @staticmethod
    def test_p0400_a_splash_whose_text_read_timed_out_still_asks_nothing():
        """P0400-SPLASH-UNREAD-TEXT (PFS-2094.017): the startup splash, its one control unread.

        The watcher wrote a placeholder into the window's text when a control read timed out,
        so the splash (class #32770, no title, one image control, no button) read as a window
        that says something and the solver was killed. What was not read is kept apart.
        """
        splash = WindowDiagnostic(
            pid=7,
            title="",
            text="",
            class_name="#32770",
            modal=True,
            controls=("Static",),
            unread=(_RUN_1_WINDOWS_AND_LOGS__UNREAD,),
        )
        assert select_owned_dialogs(7, [splash]) == ()
        # The control: a dialog with a button is a dialog, and what was not read is said.
        dialog = WindowDiagnostic(
            pid=7,
            title="",
            text="",
            class_name="#32770",
            modal=True,
            controls=("Static", "Button"),
            unread=(_RUN_1_WINDOWS_AND_LOGS__UNREAD,),
        )
        assert select_owned_dialogs(7, [dialog]) == (_RUN_1_WINDOWS_AND_LOGS__UNREAD,)

    @staticmethod
    def test_p0400_the_g06_scan_keeps_the_refusal_lines_and_not_whole_logs(tmp_path):
        """P0400-G06-SCAN-STREAMED (PFS-2101.003): a long step export and a log with the refusal.

        Every collected .txt was read whole and every text kept in memory together; only the
        lines that carry a G06 sentence, and the line after each, are kept now, and the verdict
        reads them as it read the whole text.
        """
        filler = "".join(f"step {index} residual 1.0e-3\n" for index in range(5000))
        refusal = f"{ACTUATOR_PROFILE_REFUSALS[1]}\nC:/w/prop.txt\n"
        (tmp_path / "log.txt").write_text(filler + refusal + filler, encoding="utf-8")
        (tmp_path / "step_iteration=12.txt").write_text(filler, encoding="utf-8")
        texts = collected_log_texts(tmp_path, ["log.txt", "step_iteration=12.txt"], declared=[])
        assert texts == [refusal], [len(text) for text in texts]
        assert actuator_profile_verdict(*texts) is not None


class TestRun2Assessment:
    """Tier 1, 0.40.0 lane run-2: the judgement of a quasi-steady wheel solved at several clockings.

    The wheel is the one the GOAL-035 tests build: a two-clocking point as its
    run leaves it, its record, its loads exports and its one log of two solves.
    """

    @staticmethod
    def test_p0400_a_wheel_clocking_at_its_iteration_limit_is_max_iter_reached(tmp_path):
        """P0400-QS-ITERLIMIT (PFS-2103.002): FR-434 R1 holds for a wheel's clockings.

        Clocking 0 stops at the requested 500 iterations unsettled (9e-3 against
        the limit 1e-5); the clocking path skipped the promotion and the point
        stayed COMPLETED_MAX_ITER.
        """
        case, sim = _run_2_assessment___clocked_wheel(tmp_path, (2.0e-6, 9.0e-3), rows=(500, 500))
        assessment = LoadsAssessor()(case, None, sim)
        assert assessment.status is RunStatus.MAX_ITER_REACHED, assessment.error
        assert assessment.iterations_requested == 500
        verdicts = {v["index"]: v["status"] for v in assessment.clocking_verdicts or []}
        assert sorted(verdicts.values()) == ["CONVERGED", "MAX_ITER_REACHED"], verdicts

    @staticmethod
    def test_p0400_a_wheel_whose_record_is_spoiled_is_not_converged(tmp_path):
        """P0400-QS-SPOILED-RECORD (PFS-2103.021): its log of two solves is not 'no log'.

        With the record unreadable, the log of two solves did not read as a log
        of one, so the point was recorded CONVERGED from its iteration count with
        its unsettled clocking never read.
        """
        case, sim = _run_2_assessment___clocked_wheel(tmp_path, (2.0e-6, 9.0e-3))
        (sim / "outputs" / "DP_qsteady.json").write_text(
            _run_2_assessment___spoiled("schema_version", 2)
        )
        assessment = LoadsAssessor()(case, None, sim)
        assert assessment.status is RunStatus.FAILED_INCOMPLETE_OUTPUT, assessment.status
        assert "DP_log.txt holds 2" in (assessment.error or "")


# ------------------------------------------------------- submitted extractions
def _run_2_collect___submitted_extraction(tmp_path):
    """A recorded campaign whose additional post was submitted and has not run yet."""
    from tests.tier1_offline.test_additional_post import a_recorded_campaign, extract
    from tests.tier1_offline.test_submitted_additional_post import Scheduler

    workspace, matrix = a_recorded_campaign(tmp_path, values="0.0")
    _, records = extract(workspace, matrix, Scheduler())
    (record,) = records
    assert record.status == "SUBMITTED"
    return workspace, record, workspace.sim_dir(record.sim_id) / record.working_dir


def _run_2_collect___run_the_extraction(tmp_path, workspace, record, folder):
    from tests.tier1_offline.test_additional_post import a_stub

    a_stub(tmp_path).run_script(
        workspace.sim_dir(record.sim_id) / record.script_path, working_dir=folder
    )


def _run_2_collect___no_sleep(_seconds):
    return None


class TestRun2Collect:
    """Tier 1, 0.40.0 lane run-2: the collect stage and its records.

    Every fixture is synthetic.
    """

    @staticmethod
    def test_p0400_collect_and_post_declares_the_sims_keyword_of_its_callbacks():
        """P0400-COLLECT-CALLBACKS (PFS-2095.027): the annotation states the keyword it is called with.

        ``post`` and ``post_matrix`` were annotated without ``sims`` and called
        with it under ``type: ignore``, so a callback written to the annotation
        crashed after the records were written.
        """  # noqa: E501
        hints = typing.get_type_hints(collect.collect_and_post)
        for name in ("post", "post_matrix"):
            declared = next(a for a in typing.get_args(hints[name]) if a is not type(None))
            parameters = inspect.signature(declared.__call__).parameters
            assert "sims" in parameters, name
            assert parameters["sims"].kind is inspect.Parameter.KEYWORD_ONLY, name
        source = inspect.getsource(collect)
        assert "type: ignore[call-arg]" not in source

    @staticmethod
    def test_p0400_library_post_refusal_names_the_records_already_written(tmp_path):
        """P0400-COLLECT-POST-REFUSAL (PFS-2095.052): the library names the refused stage."""
        import pytest

        from pyflightstream._errors import ProductError
        from pyflightstream.workspace import RunStatus, WorkspaceError
        from tests.tier1_offline.test_goal028_hpc_collect import (
            _loads,
            _submitted_workspace,
            _work_dir,
        )

        workspace, sim = _submitted_workspace(tmp_path, declared=("loads.txt",))
        (_work_dir(workspace, sim, alpha=2.0) / "loads.txt").write_text(_loads(2.0), "utf-8")

        def refused(ws, matrix, *, sims=None):
            raise ProductError("the probe plane lies outside the mesh")

        with pytest.raises(WorkspaceError, match="records written; the post was refused"):
            collect.collect_and_post(
                workspace, interval=0, sleep=_run_2_collect___no_sleep, post_matrix=refused
            )
        assert workspace.read_manifest()[0].status is RunStatus.CONVERGED

    @staticmethod
    def test_p0400_extraction_copy_held_open_is_a_note_not_a_failure(tmp_path, monkeypatch):
        """P0400-EXTRACTION-COPY (PFS-2103.005): the EXTRACTED row stands when the copy is held.

        Removing the private copy failed after the EXTRACTED row was written, and
        the OSError appended a FAILED_EXECUTION row over it.
        """
        from pathlib import Path

        workspace, record, folder = _run_2_collect___submitted_extraction(tmp_path)
        _run_2_collect___run_the_extraction(tmp_path, workspace, record, folder)
        real = Path.unlink

        def held(self, missing_ok=False):
            if self.name.endswith(".reopened.fsm"):
                raise PermissionError("held by another process")
            return real(self, missing_ok=missing_ok)

        monkeypatch.setattr(Path, "unlink", held)
        report = collect.collect_once(workspace, interval=0, sleep=_run_2_collect___no_sleep)
        assert len(report.collected) == 1 and not report.failed, report.lines()
        latest = workspace.read_additional()[-1]
        assert latest.status == "EXTRACTED"
        assert "could not be removed" in (latest.note or "")

    @staticmethod
    def test_p0400_extraction_of_a_compacted_simulation_is_expanded_first(tmp_path):
        """P0400-EXTRACTION-COMPACTED (PFS-2103.006): collect expands the simulation, as for a point.

        Read zipped, the original and the private copy were changed or missing,
        and the extraction was failed for good.
        """  # noqa: E501
        from pyflightstream.workspace import storage as storage_module
        from tests.tier1_offline.test_goal035_storage import _write_recipe

        workspace, record, folder = _run_2_collect___submitted_extraction(tmp_path)
        _run_2_collect___run_the_extraction(tmp_path, workspace, record, folder)
        _write_recipe(workspace, "m001", '[[compact_sims]]\nsims = "all"\n')
        storage_module.free_space(workspace.root, "m001", apply=True)
        assert not workspace.sim_dir(record.sim_id).exists(), "the fixture compacts the simulation"
        report = collect.collect_once(workspace, interval=0, sleep=_run_2_collect___no_sleep)
        assert len(report.collected) == 1 and not report.failed, report.lines()
        assert workspace.read_additional()[-1].status == "EXTRACTED"

    @staticmethod
    def test_p0400_extraction_whose_job_ended_without_outputs_ends_a_watch(tmp_path):
        """P0400-EXTRACTION-JOB-END (PFS-2085.008): the job-end rule fails a dead extraction.

        WAITING forever, it was counted outstanding and a watch never stopped.
        """
        from tests.tier1_offline.test_goal024_profile_log import _write_profile

        workspace, record, folder = _run_2_collect___submitted_extraction(tmp_path)
        _write_profile(workspace, '\n[log]\njob_end_files = ["FTS{sim}.o*"]\n')
        (folder / f"FTS{record.sim_id}.o3714205").write_text("job summary\n", encoding="utf-8")
        report = collect.collect_and_post(
            workspace, watch=True, rounds=3, interval=0, sleep=_run_2_collect___no_sleep
        )
        assert report.outstanding == 0, report.lines()
        latest = workspace.read_additional()[-1]
        assert latest.status == "FAILED_EXECUTION"
        assert f"FTS{record.sim_id}.o3714205" in (latest.error or "")
        assert "fake-23" in (latest.error or "")

    @staticmethod
    def test_p0400_a_grouped_point_missing_its_log_says_why_it_has_no_time(tmp_path):
        """P0400-MISSING-LOG-BASIS (PFS-2103.007): the nulled wall time's basis names FR-413 R2.

        wall_time_s was nulled for a RAN_MISSING_LOG point while the basis still
        said it was measured (or not) from the clock file.
        """
        from tests.tier1_offline.test_p0390_collect import _collect, _rows, _submitted

        workspace = _submitted(tmp_path, "batch", field=True)
        statuses = _collect(workspace)
        assert set(statuses.values()) == {"RAN_MISSING_LOG"}, statuses
        for row in _rows(workspace.root):
            basis = row["submission"]["job"]["wall_time_basis"]
            assert row["wall_time_s"] is None
            assert "solver log is absent" in basis and "clock file" not in basis, basis

    @staticmethod
    def test_p0400_a_watch_names_a_point_refused_without_a_record_once(tmp_path):
        """P0400-WATCH-FAILED-ONCE (PFS-2103.032): one failed outcome per point, the latest.

        A native-log refusal writes no record, so the point stays SUBMITTED; a
        watch kept going by another waiting point refused it again each sweep
        and its outcome piled up in the report.
        """

        from tests.tier1_offline.test_collect_stage import _submitted_workspace
        from tests.tier1_offline.test_goal024_profile_log import LOG_TABLE, _write_profile

        workspace, _sim = _submitted_workspace(tmp_path, declared=("loads.txt",))
        _write_profile(workspace, LOG_TABLE)
        rows = _read_record_rows(workspace.manifest_path)
        waiting = {**rows[0], "run_id": "camp/sim_9001/AL+020", "point_name": "AL+020"}
        declared = ["loads.txt", "P9001-AL+020_log.txt"]
        waiting["submission"] = {**rows[0]["submission"], "declared_outputs": declared}
        workspace._replace_manifest([rows[0], waiting])
        report = collect.collect_and_post(
            workspace, watch=True, rounds=3, interval=0, sleep=_run_2_collect___no_sleep
        )
        assert [outcome.run_id for outcome in report.failed] == ["camp/sim_9001/AL+000"], [
            outcome.detail for outcome in report.failed
        ]

    @staticmethod
    def test_p0400_collect_refuses_a_bare_string_of_sims(tmp_path):
        """P0400-SIMS-STRING (PFS-2089.009): collect refuses a str, never iterates it."""
        import pytest

        from pyflightstream.workspace import WorkspaceError
        from tests.tier1_offline.test_collect_stage import _submitted_workspace

        workspace, _sim = _submitted_workspace(tmp_path)
        for call in (collect.collect_once, collect.collect_and_post):
            with pytest.raises(WorkspaceError, match=r"sims takes a list of ids"):
                call(workspace, sims="9001", interval=0, sleep=_run_2_collect___no_sleep)

    @staticmethod
    def test_p0400_collect_refuses_an_unknown_sim_before_the_grouped_step(tmp_path):
        """P0400-COLLECT-SIMS-FIRST (PFS-2096.005): nothing is moved before --sims is refused.

        The grouped-job step moved a known simulation's points home and wrote
        its records, and only then was the unknown id refused.
        """
        import pytest

        from pyflightstream.workspace import WorkspaceError
        from tests.tier1_offline.test_p0370_s1_matrix_home import grouped_workspace

        workspace = grouped_workspace(tmp_path, mode="batch", collect=False)

        def tree():
            return sorted(
                (p.relative_to(workspace.root).as_posix(), p.stat().st_size)
                for p in workspace.root.rglob("*")
                if p.is_file() and "logs" not in p.relative_to(workspace.root).parts
            )

        before = tree()
        with pytest.raises(WorkspaceError, match="9999"):
            collect.collect_once(
                workspace, sims=["7001", "9999"], interval=0, sleep=_run_2_collect___no_sleep
            )
        assert tree() == before

    @staticmethod
    def test_p0400_a_collected_steady_job_records_its_solver_build(tmp_path):
        """P0400-SWEEP-BUILD (PFS-2103.033): a collected sweep stamps the build its points read.

        The local sweep stamped fs_build and fs_version_reported on the job; the
        collect of a submitted sweep stamped neither, so the post could not state
        the velocity convention of the job's sampled fields.
        """

        from tests.tier1_offline.test_collect_stage import _submitted_sweep
        from tests.tier1_offline.test_goal028_hpc_collect import _loads

        workspace, sim = _submitted_sweep(tmp_path)
        rows = _read_record_rows(workspace.manifest_path)
        rows[0]["fs_build"] = None
        rows[0]["fs_version_reported"] = None
        workspace._replace_manifest(rows)
        (sim / "AL+000.txt").write_text(_loads(0.0), encoding="utf-8")
        (sim / "AL+020.txt").write_text(_loads(2.0), encoding="utf-8")
        collect.collect_once(workspace, interval=0, sleep=_run_2_collect___no_sleep)
        (record,) = workspace.read_manifest()
        assert record.fs_build == "7012026", record.error
        assert record.fs_version_reported, record.error


class TestRun2Marks:
    """Tier 1, 0.40.0 lane run-2: the steady job, its descriptor, its marks and its cost.

    Every fixture is synthetic.
    """

    @staticmethod
    def test_p0400_a_local_log_named_without_the_suffix_is_written_from_the_output(tmp_path):
        """P0400-LOCAL-LOG-NAME (PFS-2103.030): the declared log is found by _declared_logs.

        On an export_log = false machine with --local, the log is written from the
        solver's captured output; a case naming it ``solver_<point>.out`` (its
        LOG_OUTPUT) was not found by the ``_log.txt`` suffix, neither written nor
        excused.
        """
        from tests.tier1_offline.test_goal031_local_run_log import _file_route_point
        from tests.tier1_offline.test_run_wake_edge_count import LOG_AROUND

        printed = LOG_AROUND.format(line="16 trailing edges imported for boundary Wing")
        record = _file_route_point(
            tmp_path,
            prints=printed,
            outputs=["loads_{point}.txt", "solver_{point}.out"],
            variables={"LOG_OUTPUT": "2"},
        )
        assert record.status is RunStatus.CONVERGED, (record.status, record.error)
        assert any(name.endswith(".out") for name in record.outputs), record.outputs

    @staticmethod
    def test_p0400_steady_job_descriptor_names_the_sweep(tmp_path):
        """P0400-JOB-DESCRIPTOR (PFS-2094.039): a steady job's descriptor names the sweep.

        The first point's case was bound for the row's clock and processors, and
        its point name went into the descriptor as the job's.
        """
        from pathlib import Path

        from tests.tier1_offline.test_goal021_swept_row import _run, _submitting
        from tests.tier1_offline.test_matrix_run import HPC_PROFILE, RECIPES, _steady_sweep_matrix

        workspace, matrix = _steady_sweep_matrix(tmp_path)
        text = "\n".join(
            line.replace('"FTS{sim}"', '"FTS{sim}_{point}"')
            for line in HPC_PROFILE.splitlines()
            if not line.startswith(("walltime ", "ncpus "))
        )
        records = _run(
            workspace,
            matrix,
            _submitting(workspace, build="26.120", text=text + "\n"),
            name="warm",
            recipes=RECIPES,
            default_fs_version="26.120",
        )
        (job,) = records
        descriptor = Path(job.submission["descriptor"]).read_text(encoding="utf-8")
        assert f"FTS5001_{job.point_name}" in descriptor, descriptor

    @staticmethod
    def test_p0400_mark_converged_judges_a_job_point_by_its_own_loads(tmp_path):
        """P0400-MARK-CONVERGED-OWN-LOADS (PFS-2103.029): a job point that collected nothing is refused.

        The check fell back to the job row's outputs, every other point's files,
        and accepted the point on the first point's loads export.
        """  # noqa: E501
        workspace = _run_2_marks___workspace(tmp_path)
        sim = workspace.sim_dir("5001")
        sim.mkdir(parents=True, exist_ok=True)
        (sim / "P5001-AL+000.txt").write_text("loads", encoding="utf-8")
        ran = [
            {"tag": "AL+000", "status": "CONVERGED", "outputs": ["P5001-AL+000.txt"]},
            {"tag": "AL+005", "status": "FAILED_INCOMPLETE_OUTPUT"},
        ]
        job = _run_2_marks___record(
            "5001", "camp/sim_5001/sweep", RunStatus.FAILED_INCOMPLETE_OUTPUT
        )
        workspace.append_record(
            job.model_copy(update={"points_ran": ran, "outputs": ["P5001-AL+000.txt"]})
        )
        entry = mark_converged(workspace.root, ["5001"], reason="read by hand", points=["AL+005"])
        assert entry["marked"] == []
        assert "loads export is not on disk" in entry["refused"]["camp/sim_5001/AL+005"]

    @staticmethod
    def test_p0400_cost_table_procs_is_the_row_s_ncpus(tmp_path):
        """P0400-COST-PROCS (PFS-2094.038): the procs column reads the row's NCPUS first.

        The script's SET_MAX_PARALLEL_THREADS comes from row_ncpus, and the
        table showed the setup's max_threads beside it.
        """
        from pyflightstream.run import estimate_point_cost
        from tests.tier1_offline.test_plan_cost import saved_simulation, steady_case

        geometry = saved_simulation(tmp_path / "wb.fsm", ["W", "B", "N"])
        case = steady_case(geometry, max_threads=8)
        case = case.model_copy(update={"variables": {**case.variables, "NCPUS": "48"}})
        assert estimate_point_cost(case, run_id="run/a", recorded=[]).processors == 48

    @staticmethod
    def test_p0400_cost_prices_a_steady_job_record_per_point(tmp_path):
        """P0400-COST-JOB (PFS-2094.015): a steady job's wall time is shared by its points.

        One record of ten points in 1000 s priced one steady point at 1000 s,
        ten times its share.
        """
        from pyflightstream.run import estimate_point_cost
        from tests.tier1_offline.test_plan_cost import recorded, saved_simulation, steady_case

        geometry = saved_simulation(tmp_path / "wb.fsm", ["W", "B", "N"])
        job = {**recorded("run/sweep", 1000.0), "points_ran": [{"tag": f"p{i}"} for i in range(10)]}
        cost = estimate_point_cost(steady_case(geometry), run_id="run/a", recorded=[job])
        assert cost.seconds == 100.0

    @staticmethod
    def test_p0400_cost_offers_no_time_for_an_unsteady_point_of_unknown_steps(tmp_path):
        """P0400-COST-UNKNOWN-STEPS (PFS-2094.016): no step count, no expected time.

        The point was priced at one time step, the per-step rate shown as its
        expected time.
        """
        from pyflightstream.run import estimate_point_cost
        from tests.tier1_offline.test_plan_cost import recorded, rotor_case, saved_simulation

        rotor = saved_simulation(tmp_path / "rotor.fsm", ["Blade1", "S", "N"])
        case = rotor_case(rotor)
        variables = {k: v for k, v in case.variables.items() if k != "REVOLUTIONS"}
        case = case.model_copy(update={"variables": variables})
        history = [recorded("run/u1", 360.0, "unsteady_rotor")]
        cost = estimate_point_cost(
            case, run_id="run/b", recorded=history, steps_by_run={"run/u1": 36}
        )
        assert cost.time_iterations is None
        assert cost.seconds is None
        assert "step count is unknown" in cost.basis
