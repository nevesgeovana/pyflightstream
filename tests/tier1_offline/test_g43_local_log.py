"""G43 of 0.28.0, the local run log: a banner, every point numbered as it starts, a closing
table counting points by status, and the progress of an unsteady run every N completed time
steps (default 10, ``progress_every``; CLI: ``--progress-every``).

The progress is read from the run's OWN step counter (the counter program the run writes
for a point with per-step actions rewrites `actions/pfs_unsteady_actions.count` at every
completed time step), never from what the solver prints. A stand-in solver advances that
file here as the real one would.
"""

from __future__ import annotations

import re
import sys
import warnings
from pathlib import Path

import pytest

from pyflightstream.exceptions import PyflightstreamWarning
from pyflightstream.run import LocalExecutor
from tests.tier1_offline.test_goal031_recorded_job_plan import _run
from tests.tier1_offline.test_matrix_run import (
    WRITES_EVERY_EXPORT,
    CountingStub,
    _steady_sweep_matrix,
)

ADVANCES_THE_COUNTER = (
    "import json, pathlib, sys, time\n"
    "c = pathlib.Path('actions/pfs_unsteady_actions.count')\n"
    "for i in range(1, 31):\n"
    "    c.write_text(json.dumps({'count': i}))\n"
    "    time.sleep(0.2)\n"
    "print('solver done')\n"
)


class _Advancing(LocalExecutor):
    def __init__(self, progress_every: int = 10) -> None:
        super().__init__(fs_exe=sys.executable, hidden=True, progress_every=progress_every)

    def _argv(self, script_path: Path) -> list[str]:
        return [sys.executable, "-c", ADVANCES_THE_COUNTER, str(script_path)]


def _point_folder(tmp_path: Path, *, with_program: bool = True) -> tuple[Path, Path]:
    work = tmp_path / "DP-point"
    (work / "actions").mkdir(parents=True)
    if with_program:
        (work / "actions" / "pfs_unsteady_actions.py").write_text(
            "TIME_ITERATIONS = 30\n", encoding="utf-8"
        )
    script = work / "point.txt"
    script.write_text("START_SOLVER\n", encoding="utf-8")
    return work, script


def test_g43_a_local_unsteady_run_says_its_progress_every_n_steps(tmp_path, capsys):
    work, script = _point_folder(tmp_path)
    result = _Advancing(progress_every=10).run_script(script, work, timeout_s=120)
    said = capsys.readouterr().err
    lines = re.findall(r"\[[#.]{20}\] step (\d+)/30 \(\d+%\)  \d+:\d\d:\d\d", said)
    assert len(lines) >= 2, said
    assert [int(step) for step in lines] == sorted(int(step) for step in lines), said
    assert result.return_code == 0 and "solver done" in result.stdout, result


def test_g43_progress_every_zero_says_nothing_and_a_row_without_a_counter_runs_as_before(
    tmp_path, capsys
):
    work, script = _point_folder(tmp_path / "a")
    _Advancing(progress_every=0).run_script(script, work, timeout_s=120)
    assert "step " not in capsys.readouterr().err
    work, script = _point_folder(tmp_path / "b", with_program=False)
    result = _Advancing(progress_every=10).run_script(script, work, timeout_s=120)
    assert "step " not in capsys.readouterr().err
    assert "solver done" in result.stdout


def test_g43_a_negative_cadence_is_refused():
    from pyflightstream.run import ExecutorConfigurationError

    with pytest.raises(ExecutorConfigurationError, match=r"progress_every is -1"):
        _Advancing(progress_every=-1)


def test_g43_a_local_run_has_a_banner_numbered_points_and_a_summary_table(tmp_path, capsys):
    workspace, matrix = _steady_sweep_matrix(tmp_path)
    capsys.readouterr()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", PyflightstreamWarning)
        _run(workspace, matrix, CountingStub(WRITES_EVERY_EXPORT))
    said = capsys.readouterr().err
    assert "--o--o--(_)--o--o--" in said and "campaign warm, 3 point(s) to run" in said, said
    # ONE JOB, THREE POINTS: the job's line numbers the points it runs, and the table
    # counts points, as the banner does, never the one record (reading A28).
    assert "3 point(s) in one job  (1-3 of 3)" in said, said
    assert re.search(r"\| status +\| points \|", said), said
    assert re.search(r"\| CONVERGED +\| +3 \|", said), said
    assert re.search(r"\n  3 point\(s\) in \d+:\d\d:\d\d", said), said


def test_g43_the_cadence_reaches_the_executor_of_every_build(monkeypatch, tmp_path):
    """`progress_every` (CLI: --progress-every) reaches every local executor a matrix builds,
    the campaign's own and a second row's installation, and the default passes nothing."""
    from pyflightstream.cases.workflows import workflow_registry
    from pyflightstream.run import matrix as matrix_module
    from pyflightstream.run.matrix import run_matrix
    from tests.tier1_offline.test_matrix_run import (
        RECIPES,
        StubSolver,
        converged,
        make_library,
        register,
        write_matrix,
    )

    def two_builds(root):
        workspace = make_library(root)
        register(workspace, "26.120", "C:/fs26120/FlightStream.exe")
        register(workspace, "26.123", "C:/fs26123/FlightStream.exe", version="26.123")
        row = (
            "700{n} | TestWing | MIXED | 3.10 | 0.0890 | AL | 0.0 | r003 | s002 | e001 | 003 "
            "| {build} |  0 | 1 | FSM_FILE:wing_clean / OUTPUTS: loads_{{point}}.txt"
        )
        matrix = write_matrix(
            root / "two_builds.fs",
            [row.format(n=1, build="26.120"), row.format(n=2, build="26.123")],
        )
        return workspace, matrix

    for cadence, expected in ((5, [5, 5]), (10, [None, None])):
        built = []

        def local_executor(fs_exe, hidden=True, *, forced_local=False, _built=built, **extra):
            _built.append(extra.get("progress_every"))
            return StubSolver(WRITES_EVERY_EXPORT)

        monkeypatch.setattr(matrix_module, "LocalExecutor", local_executor)
        workspace, matrix = two_builds(tmp_path / f"c{cadence}")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", PyflightstreamWarning)
            run_matrix(
                matrix,
                workspace,
                name="two",
                default_fs_version="26.120",
                recipes=RECIPES,
                recipe_registry=workflow_registry(),
                assess=converged,
                local=True,
                progress_every=cadence,
            )
        assert built == expected, (cadence, built)

    # ON A CLUSTER WHOSE PROFILE SAYS export_log = false, a run kept here carries both:
    # the machine's log decision is added beside the cadence, never in its place.
    monkeypatch.setattr(matrix_module, "on_a_cluster", lambda: True)
    monkeypatch.setattr(matrix_module, "hpc_profiles", lambda inputs: [inputs / "hpc" / "h.toml"])
    monkeypatch.setattr(matrix_module, "_exports_its_log_here", lambda workspace: False)
    for cadence, expected in (
        (0, {"progress_every": 0, "export_log": False}),
        (10, {"export_log": False}),
    ):
        extras = []

        def cluster_local(fs_exe, hidden=True, *, forced_local=False, _extras=extras, **extra):
            _extras.append(dict(extra))
            return StubSolver(WRITES_EVERY_EXPORT)

        monkeypatch.setattr(matrix_module, "LocalExecutor", cluster_local)
        workspace, matrix = two_builds(tmp_path / f"cluster{cadence}")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", PyflightstreamWarning)
            run_matrix(
                matrix,
                workspace,
                name="two",
                default_fs_version="26.120",
                recipes=RECIPES,
                recipe_registry=workflow_registry(),
                assess=converged,
                local=True,
                progress_every=cadence,
            )
        assert extras == [expected, expected], (cadence, extras)


def test_g43_a_submitting_run_with_a_failed_point_writes_no_table(tmp_path, monkeypatch):
    """The command writes no table for a run that submitted a point, and that holds when
    another point of the same call failed: the failure's error carries every record of
    the call, so the command still sees the submission (reading A28)."""
    from pyflightstream.run import CampaignErrors
    from pyflightstream.run import cli as cli_mod
    from pyflightstream.workspace import RunRecord, RunStatus

    queued = RunRecord.model_construct(run_id="m/sim_1/a", status=RunStatus.SUBMITTED, error=None)
    failed = RunRecord.model_construct(
        run_id="m/sim_1/b", status=RunStatus.FAILED_SCRIPT, error="stand-in"
    )

    def fails_after_submitting(matrix, workspace, **keywords):
        raise CampaignErrors([failed], [queued, failed])

    tables = []
    monkeypatch.setattr(cli_mod, "run_matrix", fails_after_submitting)
    monkeypatch.setattr(cli_mod, "plan_receipt_error", lambda *args, **kwargs: None)
    # The table the command would derive, stood in, so the only thing between the
    # error and the writer is the submission check this test is about.
    monkeypatch.setattr(cli_mod, "sweep_table", lambda *args, **kwargs: "a table")
    monkeypatch.setattr(cli_mod, "write_table", lambda *args, **kwargs: tables.append(args))
    matrix = tmp_path / "m.fs"
    matrix.write_text("", encoding="utf-8")
    status = cli_mod.main(["run", str(matrix), "--workspace", str(tmp_path / "ws"), "--name", "m"])
    assert status == 2
    assert tables == [], "the command wrote a table for a run that submitted a point"
