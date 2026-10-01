"""FR-311: collect recognises a job that ended without its solver log.

The HPC profile names, under ``[log]``, the files its scheduler writes when a
job ends (``job_end_files``); nothing of one cluster is written in the code.
Driven over recorded folders: every listed file present and no log (failed,
with the tail of the files in the record), only some present (still waiting),
the log present (collected as before), another profile's files (still
waiting), and a profile without the key (the control: 0.32.0 waited forever).

The file names ``FTS<sim>.o<id>`` and ``FTS<sim>.e<id>`` used here are the
ones of one real cluster folder (RPT-108, 2026-09-30, a job that ended with its
log); FR-311 stays pending until a folder of a job that ended without its log is
received.
"""

from __future__ import annotations

import pytest

from pyflightstream.run.collect import JOB_END_TAIL_LINES, collect_once
from pyflightstream.workspace import RunStatus
from pyflightstream.workspace.inputs import HpcProfile, InputArtifactError, read_hpc_profile
from tests.tier1_offline.test_collect_stage import _no_sleep, _submitted_workspace
from tests.tier1_offline.test_goal024_profile_log import LOG_TABLE, _work_dir, _write_profile
from tests.tier1_offline.test_goal028_hpc_collect import _loads, _log

ENDS = 'job_end_files = ["FTS{sim}.o*", "FTS{sim}.e*"]\n'
#: Twenty-six lines, the first six of which the record must not carry, the last one
#: with a byte that is not UTF-8, which the record must carry replaced rather than refuse.
ERROR_TEXT = b"".join(b"error line %d\n" % n for n in range(1, 26)) + b"bad byte \xff here\n"


def _workspace(tmp_path, table: str = LOG_TABLE + ENDS):
    workspace, sim = _submitted_workspace(tmp_path, declared=("loads.txt", "P9001-AL+000_log.txt"))
    _write_profile(workspace, table)
    work = _work_dir(workspace, sim, alpha=2.0)
    (work / "loads.txt").write_text(_loads(2.0), encoding="utf-8")
    return workspace, work


def test_fr311_every_end_file_and_no_log_records_failed_execution_with_the_tail(tmp_path):
    requirement = "FR-311"
    workspace, work = _workspace(tmp_path)
    (work / "FTS9001.o3714205").write_text("job summary\n", encoding="utf-8")
    (work / "FTS9001.e3714205").write_bytes(ERROR_TEXT)
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)
    assert [outcome.state for outcome in report.failed] == ["FAILED"], report.lines()
    record = workspace.read_manifest()[0]
    assert record.status is RunStatus.FAILED_EXECUTION, requirement
    error = record.error or ""
    assert "FTS9001.o3714205" in error and "FTS9001.e3714205" in error, error
    assert "P9001-AL+000_log.txt" in error, "the record names the log that is missing"
    # The tail is exactly the last 20 lines: the error file's 26 lines are
    # lines 1 to 25 and the undecodable one, so it starts at line 7.
    assert JOB_END_TAIL_LINES == 20
    assert "error line 7\n" in error and "error line 6\n" not in error, error
    assert "error line 25" in error, error
    assert "bad byte � here" in error, error


def test_fr311_only_some_end_files_leave_the_point_waiting(tmp_path):
    requirement = "FR-311"
    workspace, work = _workspace(tmp_path)
    (work / "FTS9001.o3714205").write_text("job summary\n", encoding="utf-8")
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)
    assert [outcome.state for outcome in report.waiting] == ["WAITING"], report.lines()
    assert workspace.read_manifest()[0].status is RunStatus.SUBMITTED, requirement


def test_fr311_the_log_present_is_collected_as_before(tmp_path):
    requirement = "FR-311"
    workspace, work = _workspace(tmp_path)
    (work / "FTS9001.o3714205").write_text("job summary\n", encoding="utf-8")
    (work / "FTS9001.e3714205").write_bytes(ERROR_TEXT)
    (work / "FTS9001.l3714205").write_text(_log(), encoding="utf-8")
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)
    assert [outcome.state for outcome in report.collected] == ["COLLECTED"], report.lines()
    assert workspace.read_manifest()[0].status is RunStatus.CONVERGED, requirement


def test_fr311_another_profile_s_patterns_do_not_match_this_cluster_s_files(tmp_path):
    requirement = "FR-311"
    other = LOG_TABLE + 'job_end_files = ["{sim}.out", "{sim}.err"]\n'
    workspace, work = _workspace(tmp_path, other)
    (work / "FTS9001.o3714205").write_text("job summary\n", encoding="utf-8")
    (work / "FTS9001.e3714205").write_bytes(ERROR_TEXT)
    collect_once(workspace, interval=0.0, sleep=_no_sleep)
    assert workspace.read_manifest()[0].status is RunStatus.SUBMITTED, requirement


def test_fr311_a_profile_without_the_key_waits_as_before_the_control(tmp_path):
    """The 0.32.0 behaviour, which nothing in the code overrides with a default pattern."""
    requirement = "FR-311"
    workspace, work = _workspace(tmp_path, LOG_TABLE)
    (work / "FTS9001.o3714205").write_text("job summary\n", encoding="utf-8")
    (work / "FTS9001.e3714205").write_bytes(ERROR_TEXT)
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)
    assert [outcome.state for outcome in report.waiting] == ["WAITING"], report.lines()
    assert workspace.read_manifest()[0].status is RunStatus.SUBMITTED, requirement
    assert HpcProfile.__dataclass_fields__["job_end_files"].default == ()


@pytest.mark.parametrize(
    "cell",
    ['job_end_files = "FTS{sim}.o*"', 'job_end_files = ["FTS{case}.o*"]', "job_end_files = [3]"],
)
def test_fr311_a_malformed_job_end_files_is_refused_naming_the_key(tmp_path, cell):
    requirement = "FR-311"
    workspace, _work = _workspace(tmp_path, LOG_TABLE + cell + "\n")
    with pytest.raises(InputArtifactError, match="job_end_files"):
        read_hpc_profile(workspace.inputs_dir / "hpc" / "h001.toml")
    assert requirement


def test_fr311_the_key_is_read_into_the_profile(tmp_path):
    requirement = "FR-311"
    workspace, _work = _workspace(tmp_path)
    profile = read_hpc_profile(workspace.inputs_dir / "hpc" / "h001.toml")
    assert profile.job_end_files == ("FTS{sim}.o*", "FTS{sim}.e*"), requirement


# ----------------------------------------------- the names of one real cluster folder
# RPT-108 records one real job folder (simulation 2013, job id 6708564): the file
# names and sizes only. The content here is synthetic, written for these tests.

REAL_NAMES = ("FTS2013.o6708564", "FTS2013.e6708564", "FTS2013.l6708564")


def _workspace_of_sim_2013(tmp_path):
    """The shared fixture moved to simulation 2013, the one the real folder came from."""
    import json
    import shutil

    workspace, work = _workspace(tmp_path)
    old = workspace.sim_dir("9001")
    new = old.parent / old.name.replace("9001", "2013")
    shutil.move(str(old), str(new))
    rows = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    for row in rows:
        row["sim_id"] = "2013"
        row["run_id"] = row["run_id"].replace("9001", "2013")
        row["submission"]["descriptor"] = row["submission"]["descriptor"].replace("9001", "2013")
    workspace.manifest_path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    return workspace, new / "datapoints" / work.name


def test_fr311_the_names_of_a_real_folder_without_a_log_record_failed_execution(tmp_path):
    requirement = "FR-311"
    workspace, work = _workspace_of_sim_2013(tmp_path)
    (work / REAL_NAMES[0]).write_text("synthetic job summary\n", encoding="utf-8")
    (work / REAL_NAMES[1]).write_bytes(ERROR_TEXT)
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)
    assert [outcome.state for outcome in report.failed] == ["FAILED"], report.lines()
    record = workspace.read_manifest()[0]
    assert record.sim_id == "2013"
    assert record.status is RunStatus.FAILED_EXECUTION, requirement
    error = record.error or ""
    assert "FTS2013.o6708564" in error and "FTS2013.e6708564" in error, error
    assert "error line 25" in error and "error line 6\n" not in error, error


def test_fr311_the_names_of_a_real_folder_with_its_log_are_collected_the_control(tmp_path):
    requirement = "FR-311"
    workspace, work = _workspace_of_sim_2013(tmp_path)
    (work / REAL_NAMES[0]).write_text("synthetic job summary\n", encoding="utf-8")
    (work / REAL_NAMES[1]).write_bytes(ERROR_TEXT)
    (work / REAL_NAMES[2]).write_text(_log(), encoding="utf-8")
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)
    assert [outcome.state for outcome in report.collected] == ["COLLECTED"], report.lines()
    assert workspace.read_manifest()[0].status is RunStatus.CONVERGED, requirement


def test_fr311_a_declared_log_present_without_a_native_match_is_not_failed(tmp_path):
    # Verifies FR-311.
    workspace, work = _workspace(tmp_path)
    (work / "FTS9001.o3714205").write_text("job summary\n", encoding="utf-8")
    (work / "FTS9001.e3714205").write_bytes(ERROR_TEXT)
    (work / "P9001-AL+000_log.txt").write_text(_log(), encoding="utf-8")
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)
    assert [outcome.state for outcome in report.collected] == ["COLLECTED"], report.lines()
    assert workspace.read_manifest()[0].status is RunStatus.CONVERGED


def test_fr311_a_point_declaring_no_log_is_never_failed_by_its_end_files(tmp_path):
    # Verifies FR-311.
    workspace, sim = _submitted_workspace(tmp_path, declared=("loads.txt",))
    _write_profile(workspace, "\n[log]\n" + ENDS)
    work = _work_dir(workspace, sim, alpha=2.0)
    (work / "loads.txt").write_text(_loads(2.0), encoding="utf-8")
    (work / "FTS9001.o3714205").write_text("job summary\n", encoding="utf-8")
    (work / "FTS9001.e3714205").write_bytes(ERROR_TEXT)
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)
    assert [outcome.state for outcome in report.collected] == ["COLLECTED"], report.lines()
    assert workspace.read_manifest()[0].status is RunStatus.CONVERGED
