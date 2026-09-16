"""Tier 1: the HPC profile's ``[log]`` table (0.21.0, GOAL-024 arm 8).

Some machines abort at ``EXPORT_LOG``: the job runs, every other export lands,
and the log this package judges the run by never arrives, so `collect` waits
for a file nothing will ever write. That machine writes its own log beside the
run instead.

The author's decision of 2026-09-15 is that the machine says so, not the package:

* ``export_log = false`` leaves ``EXPORT_LOG`` out of the script;
* ``native_log`` names the file the scheduler writes, and `collect` copies it
  to the name the row declared, so everything downstream reads one log;
* ``export_log = false`` with no ``native_log`` is refused: it asks for a run
  with no log at all;
* several files matching ``native_log`` are refused, because which one is this
  run's log is not a guess to make about the file the run is judged by.

The stub scheduler here writes a ``.l`` file carrying real FlightStream log
lines, and the record it completes is asserted to be COLLECTED with the log's
own verdict.

This module is the evidence of FR-106.

The test names carry ``goal024_profile_log`` so the goal's checker can select
them.
"""

from __future__ import annotations

import pytest

from pyflightstream.cases import SimCase, SweepAxis
from pyflightstream.cases.workflows import EXPORT_LOG_VARIABLE, build_script
from pyflightstream.run.collect import collect_once
from pyflightstream.script import Script
from pyflightstream.workspace import RunStatus
from pyflightstream.workspace.inputs import InputArtifactError, read_hpc_profile
from tests.tier1_offline.test_collect_stage import _no_sleep, _submitted_workspace

PROFILE = """\
application_id = "flightstream"

[descriptor]
format = "yaml"
name = "submit.yaml"

[descriptor.fields]
ApplicationId = "{application_id}"
job_name      = "FTS{sim}"
workdir       = "{work_dir}"

[submit]
command = ["esub", "{descriptor_path}"]
"""

LOG_TABLE = '\n[log]\nexport_log = false\nnative_log = "FTS{sim}.l*"\n'


def _profile_text(table: str = LOG_TABLE) -> str:
    return PROFILE + table


def _write_profile(workspace, table: str = LOG_TABLE):
    """Put one HPC profile in the workspace's library and return its path."""
    directory = workspace.inputs_dir / "hpc"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "h001.toml"
    path.write_text(_profile_text(table), encoding="utf-8")
    return path


def _work_dir(workspace, sim, *, alpha=None):
    """Point the submitted record at its datapoint folder and return it.

    A submitted point runs in its own datapoint folder since 0.18.1 and its
    submission block says which; the shared fixture writes none, so this says
    it, and the collector then waits where the files are.

    ``alpha`` moves the record's point to the incidence the loads fixture was
    exported at. The collector checks the export against the point it was asked
    for -- a loads file prints the conditions the solver actually ran -- and a
    test that skipped that check would be asserting on a run this package
    would refuse.
    """
    import json

    work = sim / "datapoints" / "DP-AL+000"
    work.mkdir(parents=True, exist_ok=True)
    rows = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    for row in rows:
        row["submission"]["working_dir"] = f"datapoints/{work.name}"
        if alpha is not None:
            row["point"] = {"alpha": alpha}
    workspace.manifest_path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    return work


def _case(export_log: str | None = None) -> SimCase:
    """A steady case that declares a log among its outputs."""
    variables = {"VELOCITY": "68.058", "LOG_OUTPUT": "2"}
    if export_log is not None:
        variables[EXPORT_LOG_VARIABLE] = export_log
    return SimCase(
        sim_id="9001",
        aircraft="WB",
        recipe="steady",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        point={"alpha": 0.0},
        geometry="10_WING.fsm",
        outputs=["P9001-AL+000.txt", "P9001-AL+000_log.txt"],
        variables=variables,
    )


def _rendered(case: SimCase) -> str:
    script = Script(version="26.123")
    build_script(case, script)
    return script.render()


def test_goal024_profile_log_export_log_false_removes_the_command(tmp_path):
    """The script writes every other export and not the log."""
    with_log = _rendered(_case())
    assert "EXPORT_LOG" in with_log
    without = _rendered(_case("false"))
    assert "EXPORT_LOG" not in without, without
    # And nothing else moved: the loads export is still there.
    assert "EXPORT_SOLVER_ANALYSIS_SPREADSHEET" in without


def test_goal024_profile_log_the_row_still_declares_its_log(tmp_path):
    """What changes is who WRITES it, not whether the point has one.

    The row declares the log among its outputs either way, because that is how
    it is collected and how the run is judged; on such a machine the scheduler
    writes it and `collect` puts it there.
    """
    case = _case("false")
    assert case.outputs[-1].endswith("_log.txt")
    assert "EXPORT_LOG" not in _rendered(case)


def test_goal024_profile_log_export_log_false_with_no_native_log_is_refused(tmp_path):
    """It asks for a run with no log at all, and an unsteady run cannot be judged then."""
    path = tmp_path / "h001.toml"
    path.write_text(_profile_text("\n[log]\nexport_log = false\n"), encoding="utf-8")
    with pytest.raises(InputArtifactError) as caught:
        read_hpc_profile(path)
    message = str(caught.value)
    assert "no log at all" in message, message
    assert "native_log" in message


def test_goal024_profile_log_a_profile_saying_nothing_keeps_the_old_behaviour(tmp_path):
    """A machine that writes its log the usual way needs no table, and gets no change."""
    path = tmp_path / "h001.toml"
    path.write_text(PROFILE, encoding="utf-8")
    profile = read_hpc_profile(path)
    assert profile.export_log is True
    assert profile.native_log is None


def test_goal024_profile_log_collect_copies_the_scheduler_s_log_to_the_declared_name(tmp_path):
    """The stub scheduler's own .l file becomes the log the record names.

    The file carries real FlightStream log lines, so the run is judged by the
    log rather than by the fact that a file with the right name exists.
    """
    from tests.tier1_offline.test_run_campaign import FIXTURES

    workspace, sim = _submitted_workspace(tmp_path, declared=("loads.txt", "P9001-AL+000_log.txt"))
    _write_profile(workspace)
    # The loads fixture was exported at 2 degrees, so that is the point this
    # record ran: the collector reads the incidence off the export.
    work = _work_dir(workspace, sim, alpha=2.0)
    (work / "loads.txt").write_text(
        (FIXTURES / "loads_steady_26.120.txt").read_text(encoding="utf-8"), encoding="utf-8"
    )
    # WHAT THE SCHEDULER WROTE, under its own name.
    (work / "FTS9001.l3714205").write_text(
        (FIXTURES / "log_residuals_26.120.txt").read_text(encoding="utf-8"), encoding="utf-8"
    )

    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)

    assert not report.failed, [outcome.detail for outcome in report.failed]
    assert [outcome.state for outcome in report.collected] == ["COLLECTED"], report.waiting
    copied = work / "P9001-AL+000_log.txt"
    assert copied.is_file(), sorted(p.name for p in work.iterdir())
    assert (
        copied.read_text(encoding="utf-8").splitlines()[:1]
        == ((FIXTURES / "log_residuals_26.120.txt").read_text(encoding="utf-8").splitlines()[:1])
    )
    # THE VERDICT IS THE LOG'S: the point is judged by the file the scheduler
    # wrote and this stage copied, which is the whole of what the table buys.
    record = workspace.read_manifest()[0]
    assert record.status is RunStatus.CONVERGED, record.error
    assert record.residual is not None and record.iterations, record
    assert record.log_file_used and record.log_file_used.endswith("_log.txt"), record


def test_goal024_profile_log_several_matching_files_are_refused_by_name(tmp_path):
    """Which of them is this run's log is not a guess to make about the judging file."""
    from tests.tier1_offline.test_run_campaign import FIXTURES

    workspace, sim = _submitted_workspace(tmp_path, declared=("loads.txt", "P9001-AL+000_log.txt"))
    _write_profile(workspace)
    work = _work_dir(workspace, sim)
    (work / "loads.txt").write_text("data", encoding="utf-8")
    for tail in ("l3714205", "l3714206"):
        (work / f"FTS9001.{tail}").write_text(
            (FIXTURES / "log_residuals_26.120.txt").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)

    assert len(report.failed) == 1, report
    detail = report.failed[0].detail
    assert "matches 2 files" in detail, detail
    assert "FTS9001.l3714205" in detail and "FTS9001.l3714206" in detail


def test_goal024_profile_log_a_profile_with_no_native_log_copies_nothing(tmp_path):
    """A machine whose script writes its own log is untouched by any of this."""
    workspace, sim = _submitted_workspace(tmp_path, declared=("loads.txt", "P9001-AL+000_log.txt"))
    _write_profile(workspace, "")
    work = _work_dir(workspace, sim)
    (work / "loads.txt").write_text("data", encoding="utf-8")
    (work / "FTS9001.l3714205").write_text("the scheduler's", encoding="utf-8")

    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)

    assert not (work / "P9001-AL+000_log.txt").exists()
    assert not report.failed, [outcome.detail for outcome in report.failed]
    assert report.waiting, "the declared log has not arrived, so the point waits"


def test_goal024_profile_log_a_point_declaring_no_log_output_is_refused_by_name(tmp_path):
    """A native log with nowhere to go: the row declares no log among its outputs.

    The one refusal of this table that no test asserted on its content (the qa
    lens, 2026-09-16). It matters because the row's own declaration is what
    makes the log collected and the run judged, so a profile naming a native
    log beside a row that declares none is a silent half-configuration.
    """
    workspace, sim = _submitted_workspace(tmp_path, declared=("loads.txt", "P9001-AL+000.dat"))
    _write_profile(workspace)
    work = _work_dir(workspace, sim)
    (work / "loads.txt").write_text("data", encoding="utf-8")
    (work / "P9001-AL+000.dat").write_text("data", encoding="utf-8")
    (work / "FTS9001.l3714205").write_text("the scheduler's", encoding="utf-8")

    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)

    assert len(report.failed) == 1, report
    detail = report.failed[0].detail
    assert "_log.txt" in detail and "native log" in detail, detail
    assert "loads.txt" in detail, "the refusal names the outputs the row did declare"
