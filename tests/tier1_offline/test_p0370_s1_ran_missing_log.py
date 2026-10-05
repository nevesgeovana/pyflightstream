"""P0370-S1-RAN-MISSING-LOG (FR-413): outputs present and solver log absent is RAN_MISSING_LOG.

The owner's report on 0.35.1: collect could not complete the points whose
solver logs she had deleted. Measured offline (the S1 reproduction): a grouped
point whose cumulative log was gone was WAITING for its log forever, and a
point run alone was refused FAILED_INCOMPLETE_OUTPUT by the rebuild's collect.
Each workspace here is made by the package's own run (alone, steady job, or
``--batch``), the solver's files written by hand where the job writes them,
and the commands run through ``pyfs-matrix``.
"""

from __future__ import annotations

import contextlib
import json
import warnings
from pathlib import Path

import pytest

from pyflightstream.cases.workflows import workflow_registry
from pyflightstream.run import CampaignErrors
from pyflightstream.run.matrix import run_matrix
from tests.tier1_offline import test_p0350_batch_run as grouped_run
from tests.tier1_offline.test_p0370_s1_matrix_home import (
    MATRIX,
    grouped_workspace,
    pyfs,
    the_owner_s_deletions,
)

#: The three shapes of a point: a steady job of two points, an unsteady point
#: submitted alone, and the owner's grouped points.
KINDS = {
    "steady": {"mode": "alone", "sims": ("7002",)},
    "unsteady": {"mode": "alone"},
    "grouped": {"mode": "batch"},
}

#: The profile's ``[log]`` table naming the files its scheduler writes when a job ends.
JOB_END = '\n[log]\njob_end_files = ["{point}.e*"]\n'


def _records(root: Path) -> list[dict]:
    return json.loads((root / "runs.json").read_text("utf-8"))


def _points(rows: list[dict]) -> list[dict]:
    """Every point's entry: a steady job's ``points_ran``, else the record itself."""
    return [entry for row in rows for entry in (row.get("points_ran") or [row])]


@pytest.mark.parametrize("check_frozen", [False, True], ids=["default", "check-frozen"])
@pytest.mark.parametrize("kind", sorted(KINDS))
def test_p0370_s1_collected_and_posted_as_ran_missing_log(kind, check_frozen, tmp_path, capsys):
    """P0370-S1-RAN-MISSING-LOG (FR-413 R1, R2, R3, R7): collected, never CONVERGED, posted.

    Every output of every point is present and no log was ever written back:
    collect records RAN_MISSING_LOG with the note naming what only the log
    carries and ``wall_time_s`` null; the post writes every point's products,
    with ``--check-frozen`` too, and its log carries exactly one WARNING per
    point naming the status.
    """
    workspace = grouped_workspace(tmp_path / kind, logs=False, **KINDS[kind])
    rows = _records(workspace.root)
    for row in rows:
        assert row["status"] == "RAN_MISSING_LOG", (row["run_id"], row["status"], row["error"])
        assert row["wall_time_s"] is None and row.get("iterations") is None, row["run_id"]
    points = _points(rows)
    assert {entry["status"] for entry in points} == {"RAN_MISSING_LOG"}
    for entry in points:
        note = entry["residual_note"]
        assert "is absent" in note and "the convergence verdict" in note, note
        assert "the solver clock (wall_time_s)" in note, note
    argv = ["post", MATRIX] + (["--check-frozen"] if check_frozen else [])
    code, said = pyfs(argv, workspace.root, capsys)
    assert code == 0, said
    folder = workspace.root / "post" / MATRIX
    products = json.loads((folder / "products.json").read_text("utf-8"))
    log = (folder / "post.log").read_text("utf-8")
    assert not [key for key in products["skipped"] if key.startswith("runs/")], products["skipped"]
    assert len(products["provenance"]) == len(rows), products["provenance"]
    lines = [line for line in log.splitlines() if "RAN_MISSING_LOG" in line]
    assert len(lines) == len(points), lines
    assert all(("cannot read its freeze" in line) is check_frozen for line in lines), lines
    if kind == "steady":
        polars = [name for name in products["products"] if name.startswith("polars/P7002")]
        assert polars, sorted(products["products"])


@pytest.mark.parametrize("mode", ["alone", "batch"])
def test_p0370_s1_end_files_with_outputs_are_not_failed_execution(mode, tmp_path):
    """P0370-S1-RAN-MISSING-LOG (FR-413 R1): the job's end files and the outputs, no log.

    The profile names the files its scheduler writes when a job ends
    (``job_end_files``), each point has one beside its outputs, and no log
    came back: the point is RAN_MISSING_LOG, decided before the end files are
    read, not FAILED_EXECUTION (FR-311's job that ended without its log).
    """
    workspace = grouped_workspace(
        tmp_path / mode, mode=mode, logs=False, collect=False, profile_tail=JOB_END
    )
    for row in _records(workspace.root):
        submission = row["submission"]
        job = submission.get("job")
        sim = workspace.root / (job["dir"] if job else "sims") / f"sim_{row['sim_id']}"
        folder = sim / submission["working_dir"]
        (folder / f"{row['point_name']}.e4242").write_text("job ended\n", encoding="utf-8")
    from pyflightstream.run.collect import collect_once
    from tests.support_helpers import no_sleep

    collect_once(workspace, interval=0.0, sleep=no_sleep)
    statuses = {row["run_id"]: row["status"] for row in _records(workspace.root)}
    assert set(statuses.values()) == {"RAN_MISSING_LOG"}, statuses


def test_p0370_s1_status_show_plan_and_resume_read_a_run_that_ended(tmp_path, capsys):
    """P0370-S1-RAN-MISSING-LOG (FR-413 R4): every status reader treats it as a run that ended.

    ``status`` counts it apart from a converged point, ``show`` prints the
    status and what is unavailable, ``plan`` counts its points recorded, and
    ``run --resume`` submits nothing (its control: a point with no record is
    submitted by the same resume).
    """
    workspace = grouped_workspace(tmp_path / "ws", logs=False)
    rows = _records(workspace.root)
    rows[0]["status"] = "CONVERGED"  # one point the log of which was kept, for the count
    workspace.manifest_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    code, said = pyfs(["status"], workspace.root, capsys)
    assert code == 0, said
    assert "CONVERGED 1, RAN_MISSING_LOG 2" in said, said
    code, said = pyfs(["show", "7001_2"], workspace.root, capsys)
    assert code == 0, said
    assert "RAN_MISSING_LOG" in said and "the solver log V0300RE120AL+020_log.txt is absent" in said
    code, said = pyfs(["plan", MATRIX, "--name", MATRIX], workspace.root, capsys)
    assert code == 0, said
    assert "0 ready, 0 blocked, 3 already recorded" in said, said
    before = workspace.manifest_path.read_bytes()
    assert _resume(workspace) == []
    assert workspace.manifest_path.read_bytes() == before, "run --resume ran a point that ended"
    # The control: with one record gone, the same resume runs that point again.
    workspace.manifest_path.write_text(json.dumps(rows[:2], indent=2), encoding="utf-8")
    with contextlib.suppress(CampaignErrors):  # it fails here: the stub submits nothing
        _resume(workspace)
    assert [row["run_id"] for row in _records(workspace.root)][2:] == [rows[2]["run_id"]]


def _resume(workspace):
    """``run --resume`` of the owner's matrix, on the profile that submits through its command."""
    profile = workspace.inputs_dir / "hpc" / "h001.toml"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return run_matrix(
            workspace.root / "inputs" / "matrices" / f"{MATRIX}.fs",
            workspace,
            name=MATRIX,
            recipes={},
            recipe_registry=workflow_registry(),
            assess=grouped_run.converged,
            executor=grouped_run._submitting(profile, submit=False),
            resume=True,
        )


def test_p0370_s1_a_machine_that_exports_no_log_keeps_its_behaviour(tmp_path):
    """P0370-S1-RAN-MISSING-LOG (FR-413 R5): ``export_log = false`` declares no log, so not this.

    On such a machine the script exports no log, the scheduler writes it under
    ``native_log``, and its absence is collect's 0.36.0 wait, never
    RAN_MISSING_LOG: the rule reads the logs the script declared, not a name
    ending in ``_log.txt``.
    """
    tail = '\n[log]\nexport_log = false\nnative_log = "FTS{sim}.l*"\n'
    workspace = grouped_workspace(tmp_path / "ws", mode="alone", logs=False, profile_tail=tail)
    rows = _records(workspace.root)
    assert all(row["submission"]["declared_logs"] == [] for row in rows), rows
    assert {row["status"] for row in rows} == {"SUBMITTED"}, [row["status"] for row in rows]


def test_p0370_s1_the_three_paths_decide_the_same_status(tmp_path, capsys):
    """P0370-S1-RAN-MISSING-LOG (FR-413 R6): collect, the grouped collect and rebuild agree.

    The same files (every output, no log) fed to the collect of a point run
    alone, to the collect of a grouped point, and to the rebuild of a lost
    ``runs.json``: one status, from the one rule beneath the three.
    """
    alone = grouped_workspace(tmp_path / "alone", mode="alone", logs=False)
    # A batch still running: only the grouped collect copies a finished point home.
    grouped = grouped_workspace(tmp_path / "grouped", logs=False, ended=False)
    rebuilt = grouped_workspace(tmp_path / "rebuilt", mode="batch")
    the_owner_s_deletions(rebuilt, run_zero=False)
    code, said = pyfs(["rebuild", "--apply"], rebuilt.root, capsys)
    assert code == 0, said
    seen = {
        name: sorted({row["status"] for row in _records(workspace.root)})
        for name, workspace in (("alone", alone), ("grouped", grouped), ("rebuilt", rebuilt))
    }
    assert seen == dict.fromkeys(seen, ["RAN_MISSING_LOG"]), seen
