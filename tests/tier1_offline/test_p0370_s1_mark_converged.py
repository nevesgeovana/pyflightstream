"""P0370-S1-MARK-CONVERGED (FR-414): a person's verdict of CONVERGED, its reason, an archive.

The owner's request of 2026-10-03, answered then with a standalone script that
edited ``runs.json``: a command that records her verdict on the points she
knows converged. The workspace is the package's own run of three rows, a
two-point rotor polar and a one-point unsteady polar submitted per point and a
two-point steady job, whose logs never came back, so every point is
RAN_MISSING_LOG until a person says otherwise.
"""

from __future__ import annotations

import json
import os
import time

import pytest

from pyflightstream.run.records import mark_converged
from pyflightstream.workspace import RunStatus
from pyflightstream.workspace.naming import RunsManifestError
from pyflightstream.workspace.storage import sync_workspaces
from tests.tier1_offline.test_goal035_storage import _record, _sync_pair
from tests.tier1_offline.test_p0370_s1_matrix_home import MATRIX, grouped_workspace, pyfs

REASON = "residual history read by hand: flat over the last revolution"
ROTOR = (f"{MATRIX}/sim_7001/V0300RE120AL+000", f"{MATRIX}/sim_7001/V0300RE120AL+020")


@pytest.fixture
def workspace(tmp_path):
    """Three rows run alone and collected without their logs: every point RAN_MISSING_LOG."""
    return grouped_workspace(
        tmp_path / "ws", mode="alone", logs=False, sims=("7001", "7002", "7003")
    )


def _rows(workspace) -> dict[str, dict]:
    return {row["run_id"]: row for row in json.loads(workspace.manifest_path.read_text("utf-8"))}


def test_p0370_s1_preview_writes_nothing_and_apply_marks_with_an_archive(workspace, capsys):
    """P0370-S1-MARK-CONVERGED (FR-414 R1): the preview leaves runs.json byte-equal; apply marks.

    Each marked record keeps under ``marked`` the status it had, the time, the
    reason and the verdict, and the archive holds the previous runs.json.
    """
    before = workspace.manifest_path.read_bytes()
    argv = ["mark-converged", "--sims", "7001", "--reason", REASON]
    code, said = pyfs(argv, workspace.root, capsys)
    assert code == 0, said
    assert workspace.manifest_path.read_bytes() == before
    assert said.count("would mark CONVERGED") == 2 and "(was RAN_MISSING_LOG)" in said, said
    code, said = pyfs([*argv, "--apply"], workspace.root, capsys)
    assert code == 0, said
    rows = _rows(workspace)
    for run_id in ROTOR:
        assert rows[run_id]["status"] == "CONVERGED", run_id
        marked = rows[run_id]["marked"]
        assert (marked["from"], marked["reason"], marked["verdict"]) == (
            "RAN_MISSING_LOG",
            REASON,
            "CONVERGED",
        )
        assert marked["at"], marked
    assert rows[f"{MATRIX}/sim_7003/V0300RE120AL+000"]["status"] == "RAN_MISSING_LOG"
    archived = next(line.split(": ", 1)[1] for line in said.splitlines() if "as it was" in line)
    assert (workspace.root / archived).read_bytes() == before
    code, said = pyfs([*argv, "--apply"], workspace.root, capsys)
    assert code == 0, said
    assert said.count("already CONVERGED, left as it is") == 2, said


def test_p0370_s1_points_narrow_the_mark_and_the_reason_is_required(workspace, capsys):
    """P0370-S1-MARK-CONVERGED (FR-414 R1): ``--points`` marks those alone; a reason is required."""
    code, said = pyfs(
        ["mark-converged", "--sims", "7001", "--points", "V0300RE120AL+020", "--reason", REASON]
        + ["--apply"],
        workspace.root,
        capsys,
    )
    assert code == 0, said
    rows = _rows(workspace)
    assert [rows[run_id]["status"] for run_id in ROTOR] == ["RAN_MISSING_LOG", "CONVERGED"]
    with pytest.raises(RunsManifestError, match="needs its reason"):
        mark_converged(workspace.root, ["7001"], reason="  ", apply=True)
    with pytest.raises(SystemExit):
        pyfs(["mark-converged", "--sims", "7001", "--apply"], workspace.root, capsys)


def _submitted(workspace):
    rows = json.loads(workspace.manifest_path.read_text("utf-8"))
    rows[0]["status"] = "SUBMITTED"
    workspace.manifest_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return "7001", ROTOR[0], "still SUBMITTED"


def _no_loads(workspace):
    folder = workspace.sim_dir("7003") / "datapoints" / "DP-V0300RE120AL+000"
    (folder / "V0300RE120AL+000.txt").unlink()
    return "7003", f"{MATRIX}/sim_7003/V0300RE120AL+000", "loads export is not on disk"


def _deleted(workspace):
    rows = json.loads(workspace.manifest_path.read_text("utf-8"))
    gone = [row["run_id"] for row in rows if row["sim_id"] == "7003"]
    kept = [row for row in rows if row["sim_id"] != "7003"]
    kept.append({"deleted_sim": "7003", "deleted_run_ids": gone})
    workspace.manifest_path.write_text(json.dumps(kept, indent=2), encoding="utf-8")
    return "7003", "sim_7003", "deleted by delete-sims"


def _marked_failed(workspace):
    from pyflightstream.run.records import mark_failed

    mark_failed(workspace.root, ["7003"], reason="wrong mesh", apply=True)
    return "7003", f"{MATRIX}/sim_7003/V0300RE120AL+000", "marked failed by a person"


@pytest.mark.parametrize(
    "make", [_submitted, _no_loads, _deleted, _marked_failed], ids=lambda make: make.__name__
)
def test_p0370_s1_each_refusal_names_the_point_and_writes_nothing(make, workspace, capsys):
    """P0370-S1-MARK-CONVERGED (FR-414 R2): SUBMITTED, no loads export, deleted, marked failed.

    Each class is refused by name with its reason and remedy, the preview says
    so, and applying writes nothing.
    """
    sim, who, why = make(workspace)
    before = workspace.manifest_path.read_bytes()
    argv = ["mark-converged", "--sims", sim, "--reason", REASON]
    code, said = pyfs(argv, workspace.root, capsys)
    assert code == 0, said
    assert f"refused: {who}: " in said and why in said, said
    code, said = pyfs([*argv, "--apply"], workspace.root, capsys)
    assert code == 2, said
    assert "nothing was written" in said and who in said and why in said, said
    assert workspace.manifest_path.read_bytes() == before


def test_p0370_s1_show_status_and_the_post_name_the_person_s_verdict(workspace, capsys):
    """P0370-S1-MARK-CONVERGED (FR-414 R3): show, status, post.log and products.json name it.

    The steady job's two points and the rotor polar are marked: ``show``
    prints the verdict with its reason, ``status --points`` the status each
    had, ``post.log`` names each marked point, and every product entry built
    from a marked point carries its ``marked`` field.
    """
    for sim in ("7001", "7002"):
        argv = ["mark-converged", "--sims", sim, "--reason", REASON, "--apply"]
        code, said = pyfs(argv, workspace.root, capsys)
        assert code == 0, said
    code, said = pyfs(["show", "7001_1"], workspace.root, capsys)
    assert code == 0, said
    assert REASON in said and "verdict" in said and "RAN_MISSING_LOG" in said, said
    code, said = pyfs(["status", "--points", "--sims", "7001"], workspace.root, capsys)
    assert code == 0, said
    rows = [line for line in said.splitlines() if "V0300RE120AL" in line]
    assert len(rows) == 2 and all("RAN_MISSING_LOG" in row for row in rows), said
    code, said = pyfs(["post", MATRIX], workspace.root, capsys)
    assert code == 0, said
    folder = workspace.root / "post" / MATRIX
    log = (folder / "post.log").read_text("utf-8")
    steady = [f"{MATRIX}/sim_7002/V0300RE120AL+000", f"{MATRIX}/sim_7002/V0300RE120AL+020"]
    for run_id in (*ROTOR, *steady):
        assert log.count(f"point={run_id} product=all: CONVERGED is a person's verdict") == 1
    products = json.loads((folder / "products.json").read_text("utf-8"))["products"]
    polars = {name: entry for name, entry in products.items() if name.startswith("polars/P7002")}
    assert polars, sorted(products)
    for name, entry in polars.items():
        assert set(entry["marked"]) == set(entry["runs"]) == set(steady), (name, entry)
        assert {mark["reason"] for mark in entry["marked"].values()} == {REASON}


def test_p0370_s1_rebuild_keeps_marked_steady_points(workspace, capsys):
    """P0370-S1-MARK-CONVERGED (FR-414 R4): rebuild retains nested steady-job marks."""
    from pyflightstream.workspace import RunRecord

    mark_converged(workspace.root, ["7002"], reason=REASON, apply=True)
    before = {
        point.run_id: point.marked
        for record in workspace.read_manifest()
        for point in record.as_points()
        if point.sim_id == "7002"
    }
    old = time.time() - 3600
    for path in (workspace.root / "sims").rglob("*"):
        os.utime(path, (old, old))
    code, said = pyfs(
        ["rebuild", "--all-sims", "--out", "rebuilt.json", "--apply"], workspace.root, capsys
    )
    assert code == 0, said
    rebuilt = json.loads((workspace.root / "rebuilt.json").read_text("utf-8"))
    after = {
        point.run_id: (point.status, point.marked)
        for row in rebuilt
        for point in RunRecord.model_validate(row).as_points()
        if point.sim_id == "7002"
    }
    assert after == {run_id: (RunStatus.CONVERGED, mark) for run_id, mark in before.items()}


def test_p0370_s1_later_writers_keep_the_person_s_verdict(workspace, tmp_path, capsys):
    """P0370-S1-MARK-CONVERGED (FR-414 R4): rebuild and sync never replace the verdict in silence.

    A rebuild of every simulation keeps the person's verdict over the status
    the files support and says so; a sync that prefers the other workspace
    names a marked record as a conflict and leaves it.
    """
    argv = ["mark-converged", "--sims", "7001", "--reason", REASON, "--apply"]
    code, said = pyfs(argv, workspace.root, capsys)
    assert code == 0, said
    marks = {run_id: _rows(workspace)[run_id]["marked"] for run_id in ROTOR}
    old = time.time() - 3600
    for path in (workspace.root / "sims").rglob("*"):
        os.utime(path, (old, old))
    argv = ["rebuild", "--all-sims", "--out", "rebuilt.json", "--apply"]
    code, said = pyfs(argv, workspace.root, capsys)
    assert code == 0, said
    rebuilt = json.loads((workspace.root / "rebuilt.json").read_text("utf-8"))
    for row in (row for row in rebuilt if row["run_id"] in ROTOR):
        assert (row["status"], row["marked"]) == ("CONVERGED", marks[row["run_id"]]), row
        assert any("a person's verdict is kept" in line for line in row["warnings"]), row
    main, other = _sync_pair(tmp_path, "verdict")
    marked = {"from": "COMPLETED_MAX_ITER", "at": "2026-10-05", "reason": REASON}
    main.append_record(
        _record("7004", "campo/sim_7004/AL+000").model_copy(update={"marked": marked})
    )
    other.append_record(_record("7004", "campo/sim_7004/AL+000", status=RunStatus.FAILED_EXECUTION))
    (entry,) = sync_workspaces(main.root, "runs", apply=True, prefer_other=True)
    assert [item["run_id"] for item in entry["runs"]["conflicts"]] == ["campo/sim_7004/AL+000"]
    row = json.loads(main.manifest_path.read_text("utf-8"))[0]
    assert (row["status"], row["marked"]) == ("CONVERGED", marked)
