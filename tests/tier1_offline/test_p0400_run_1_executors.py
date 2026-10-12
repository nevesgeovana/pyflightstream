"""Tier 1, 0.40.0 lane run-1: the executors (descriptors, submission, the local run's log).

Synthetic profiles, scripts and stand-in programs; no solver runs.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from pyflightstream.cases import CampaignConfigError
from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run import (
    CampaignErrors,
    ExecutionResult,
    ExecutorConfigurationError,
    LocalExecutor,
    SubmittingExecutor,
    SurfaceMeshExportError,
    export_surface_mesh,
    render_descriptor,
)
from pyflightstream.run import _executors as executors
from pyflightstream.run.matrix import run_matrix
from pyflightstream.workspace import RunStatus
from pyflightstream.workspace.inputs import read_hpc_profile
from tests.tier1_offline.test_matrix_run import RECIPES, _steady_sweep_matrix, converged

VALUES = {"sim": "mtx_b1", "ncpus": 8, "fs_build": "26.124", "ratio": 0.5}


def _fields(fmt: str) -> SimpleNamespace:
    return SimpleNamespace(
        fields={
            "job_name": "FTS{sim}",
            "ncpus": "{ncpus}",
            "ratio": "{ratio}",
            "version": "{fs_build}",
            "driveg": True,
        },
        descriptor_format=fmt,
        path="h.toml",
    )


def test_p0400_json_and_toml_descriptors_write_numbers_and_booleans_bare():
    """P0400-DESCRIPTOR-TYPES (PFS-2094.009): the yaml rule of 0.35.0, in json and toml.

    json wrote ``"driveg": "true"`` and ``"ncpus": "8"``, toml ``ncpus = "8"``: the cluster
    reads a string where it expects the switch or the count. A build identifier, which reads
    as a number and is text, stays quoted (the control).
    """
    payload = json.loads(render_descriptor(_fields("json"), VALUES))
    assert payload == {
        "job_name": "FTSmtx_b1",
        "ncpus": 8,
        "ratio": 0.5,
        "version": "26.124",
        "driveg": True,
    }
    toml = render_descriptor(_fields("toml"), VALUES)
    assert "ncpus = 8\n" in toml and "ratio = 0.5\n" in toml and "driveg = true\n" in toml
    assert 'version = "26.124"\n' in toml and 'job_name = "FTSmtx_b1"\n' in toml


PROFILE = """\
application_id = "flightstream"

[descriptor]
format = "yaml"
name = "submit.yaml"

[descriptor.fields]
job_name = "FTS{sim}"

[submit]
command = COMMAND
"""


def _profile(tmp_path: Path, command: str, extra: str = ""):
    path = tmp_path / "inputs" / "hpc" / "h001.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PROFILE.replace("COMMAND", command) + extra, encoding="utf-8")
    return path


def test_p0400_a_submit_placeholder_no_run_supplies_is_refused_at_construction(tmp_path):
    """P0400-SUBMIT-PLACEHOLDERS (PFS-2094.010): ``{queue}`` in the submit command.

    It was a KeyError at the first point's submission, after earlier rows were submitted;
    it is now refused when the executor is built, naming the profile and the name.
    """
    profile = read_hpc_profile(_profile(tmp_path, '["esub", "-q", "{queue}", "{descriptor_path}"]'))
    with pytest.raises(ExecutorConfigurationError, match=r"\{queue\}"):
        SubmittingExecutor(profile, values={"fs_build": "26.120"})
    # The control: a name the run supplies is accepted.
    good = read_hpc_profile(_profile(tmp_path, '["esub", "{ncpus}", "{descriptor_path}"]'))
    SubmittingExecutor(good, values={"fs_build": "26.120"})


def test_p0400_a_point_the_submit_command_cannot_name_is_refused_by_name(tmp_path):
    """P0400-SUBMIT-PLACEHOLDERS (PFS-2094.010): ``{walltime}`` and a row that states none.

    The KeyError of the argv format left the campaign as a traceback; it is now the
    package's refusal naming the profile and what the point can supply.
    """
    profile = read_hpc_profile(_profile(tmp_path, '["esub", "--time={walltime}"]'))
    executor = SubmittingExecutor(profile, values={"fs_build": "26.120"}, submit=False)
    executor.bind_point({"sim": "5001", "point": "AL+000"}, replace=True)
    script = tmp_path / "s.txt"
    script.write_text("CLOSE_FLIGHTSTREAM\n", encoding="utf-8")
    with pytest.raises(CampaignConfigError, match="walltime") as refused:
        executor.run_script(script, tmp_path / "work")
    assert "h001.toml" in str(refused.value)


def test_p0400_a_submit_command_that_hangs_is_this_points_failure(tmp_path):
    """P0400-SUBMIT-TIMEOUT (PFS-2094.010): TimeoutExpired was not caught and ended the campaign."""
    program = Path(sys.executable).as_posix()
    command = f'["{program}", "-c", "import time; time.sleep(30)", "{{descriptor_path}}"]'
    profile = read_hpc_profile(_profile(tmp_path, command))
    executor = SubmittingExecutor(profile, values={"fs_build": "26.120"})
    executor.bind_point({"sim": "5001", "point": "AL+000"}, replace=True)
    script = tmp_path / "s.txt"
    script.write_text("CLOSE_FLIGHTSTREAM\n", encoding="utf-8")
    result = executor.run_script(script, tmp_path / "work", timeout_s=1.0)
    assert result.failed and result.timed_out
    assert "did not return within" in result.stderr


def test_p0400_a_refused_submission_is_the_rows_record_and_the_run_returns(tmp_path):
    """P0400-SUBMIT-REFUSAL-RECORDED (PFS-2094.010): a descriptor field this row cannot fill.

    The refusal raised inside run_script left the campaign loop with no record for the row,
    after earlier rows were submitted; the row is now recorded FAILED_SCRIPT, naming it,
    and run_matrix returns.
    """
    workspace, matrix = _steady_sweep_matrix(tmp_path)
    path = _profile(tmp_path / "w", '["esub", "{descriptor_path}"]')
    text = path.read_text(encoding="utf-8").replace(
        'job_name = "FTS{sim}"', 'job_name = "FTS{sim}"\nwalltime = "{walltime}"'
    )
    path.write_text(text, encoding="utf-8")
    executor = SubmittingExecutor(read_hpc_profile(path), values={"fs_build": "26.120"})
    # A campaign whose points failed ends as every such campaign does, with its records.
    with pytest.raises(CampaignErrors) as failed:
        run_matrix(
            matrix,
            workspace,
            name="cluster",
            default_fs_version="26.120",
            recipes=RECIPES,
            recipe_registry=workflow_registry(),
            assess=converged,
            executor=executor,
        )
    records = failed.value.records
    assert records and all(r.status is RunStatus.FAILED_SCRIPT for r in records), records
    assert all("walltime" in (r.error or "") for r in records)
    assert [r.run_id for r in workspace.read_manifest()] == [r.run_id for r in records]


def test_p0400_a_relative_script_is_read_from_the_working_directory(tmp_path, monkeypatch):
    """P0400-LOCAL-RELATIVE-SCRIPT (PFS-2094.011): the steady coupled check reads it as the solver.

    The check opened the relative path against this process's directory, found nothing and
    took the ordinary path, while the solver read the coupled script from its own directory.
    """
    work = tmp_path / "work"
    work.mkdir()
    (work / "coupled.txt").write_text("EXECUTE_AEROELASTIC_ANALYSIS\n", encoding="utf-8")
    seen: list[Path] = []
    monkeypatch.setattr(
        executors, "_a_steady_coupled_script", lambda path: seen.append(Path(path)) or False
    )
    monkeypatch.chdir(tmp_path)
    stub = tmp_path / "stub.py"
    stub.write_text("", encoding="utf-8")
    executor = LocalExecutor(sys.executable)
    monkeypatch.setattr(executor, "_argv", lambda script: [sys.executable, str(stub)])
    executor.run_script(Path("coupled.txt"), working_dir=work)
    assert seen == [work / "coupled.txt"]


def test_p0400_a_log_an_earlier_attempt_left_is_not_this_runs_log(tmp_path, monkeypatch):
    """P0400-STALE-SOLVER-LOG (PFS-2103.003): a planted FlightStreamLog.txt is not read.

    The file was read as this run's log whenever it existed, so an earlier attempt's text
    was quoted as this run's evidence. A log the run writes is read (the control).
    """
    work = tmp_path / "work"
    work.mkdir()
    stale = work / "FlightStreamLog.txt"
    stale.write_text("an earlier attempt's log", encoding="utf-8")
    old = time.time() - 3600
    os.utime(stale, (old, old))
    quiet = tmp_path / "quiet.py"
    quiet.write_text("", encoding="utf-8")
    writes = tmp_path / "writes.py"
    writes.write_text(
        "from pathlib import Path\nPath('FlightStreamLog.txt').write_text('this run')\n",
        encoding="utf-8",
    )
    executor = LocalExecutor(sys.executable)
    monkeypatch.setattr(executor, "_argv", lambda script: [sys.executable, str(quiet)])
    script = work / "s.txt"
    script.write_text("CLOSE_FLIGHTSTREAM\n", encoding="utf-8")
    assert executor.run_script(script, working_dir=work).log_text is None
    assert stale.read_text(encoding="utf-8") == "an earlier attempt's log", "evidence kept"
    monkeypatch.setattr(executor, "_argv", lambda script: [sys.executable, str(writes)])
    assert executor.run_script(script, working_dir=work).log_text == "this run"


class _SaysOnStdout:
    def run_script(self, script_path, working_dir, timeout_s=None) -> ExecutionResult:
        return ExecutionResult(
            return_code=3,
            wall_time_s=0.1,
            timed_out=False,
            log_text=None,
            stdout="unknown argument -scrpt",
            stderr="",
        )


def test_p0400_a_mesh_export_failure_quotes_what_the_run_printed(tmp_path):
    """P0400-MESH-EXPORT-DIAGNOSIS (PFS-2094.012): a failure before the script is accepted.

    Only stdout carries it, and the refusal quoted the log alone, so it read ``''``. It is
    now the one sentence ExecutionResult.diagnosis composes.
    """
    with pytest.raises(SurfaceMeshExportError) as refused:
        export_surface_mesh(
            tmp_path / "case.fsm", tmp_path / "pre", version="26.120", executor=_SaysOnStdout()
        )
    message = str(refused.value)
    assert "unknown argument -scrpt" in message and "return code 3" in message, message
    assert "was not written" in message
