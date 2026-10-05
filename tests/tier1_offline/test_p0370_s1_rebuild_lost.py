"""P0370-S1-REBUILD-LOST (FR-412): ``rebuild`` makes the records a lost runs.json held.

The owner's report on 0.35.1, reproduced offline (the S1 reproduction): after
her matrix was moved to the workspace root, ``rebuild`` refused every grouped
simulation because a batch point's script names its batch folder
(``sims/batch/<matrix>_b<ID>/sim_<id>/``) and the row renders the alone
folder; with ``--apply`` the per-simulation reasons were never printed, only
"rebuild: no record was rebuilt, so there is nothing to write", which is the
"there is no record" she recalled. A simulation still in its batch folder was
never seen at all. Each workspace here is made by the package's own grouped
run and collect (``test_p0370_s1_matrix_home.py``), then ``runs.json`` and the
logs are deleted, and the commands are run through ``pyfs-matrix`` as she runs
them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.tier1_offline.test_p0370_s1_matrix_home import (
    BATCH,
    MATRIX,
    grouped_workspace,
    pyfs,
    the_owner_s_deletions,
)

#: The run ids of the owner's three points, the two of 7001 and the one of 7003.
RUN_IDS = (
    f"{MATRIX}/sim_7001/V0300RE120AL+000",
    f"{MATRIX}/sim_7001/V0300RE120AL+020",
    f"{MATRIX}/sim_7003/V0300RE120AL+000",
)


def _records(root: Path) -> dict[str, dict]:
    return {row["run_id"]: row for row in json.loads((root / "runs.json").read_text("utf-8"))}


def _posted(root: Path, capsys) -> tuple[dict, str]:
    """Post the matrix as she does and return its products manifest and its log."""
    code, said = pyfs(["post", MATRIX], root, capsys)
    assert code == 0, said
    folder = root / "post" / MATRIX
    return json.loads((folder / "products.json").read_text("utf-8")), (
        folder / "post.log"
    ).read_text("utf-8")


@pytest.mark.parametrize("mode", ["alone", "batch"])
def test_p0370_s1_rebuild_writes_the_records_of_a_lost_runs_json(mode, tmp_path, capsys):
    """P0370-S1-REBUILD-LOST (FR-412 R1a, R2, R4): per point and grouped, rebuilt and posted.

    Every point's outputs are in its datapoint folder and its log is deleted:
    each is rebuilt RAN_MISSING_LOG, never refused for the log alone (R2); a
    grouped point names its batch and its job, as collect records it (R1a);
    what only the log or the submission carried is left unstated (R4); and the
    post writes every point's products.
    """
    workspace = grouped_workspace(tmp_path / mode, mode=mode)
    the_owner_s_deletions(workspace)
    code, said = pyfs(["rebuild", "--apply"], workspace.root, capsys)
    assert code == 0, said
    assert "rebuild: 3 rebuilt, 0 refused" in said.splitlines(), said
    records = _records(workspace.root)
    assert set(records) == set(RUN_IDS), sorted(records)
    for run_id, record in records.items():
        assert record["status"] == "RAN_MISSING_LOG", (run_id, record["status"], record["error"])
        assert record["wall_time_s"] is None and record["iterations"] is None, run_id
        assert record["job_id"] is None, run_id
        assert record["warnings"][0].startswith("REBUILT"), run_id
        submission = record["submission"]
        if mode == "batch":
            assert submission["batch"] == BATCH, run_id
            job = submission["job"]
            assert (job["name"], job["dir"], job["points"]) == (
                "BATCH-7001-7003",
                f"sims/batch/{BATCH}",
                3,
            )
            assert job["order"] == RUN_IDS.index(run_id) + 1, run_id
            assert job["values"] == {}, run_id  # the scheduler's fields: never invented
        else:
            assert "job" not in (submission or {}) and "batch" not in (submission or {}), run_id
    products, log = _posted(workspace.root, capsys)
    assert set(products["provenance"]) == set(RUN_IDS), products["provenance"]
    assert not [key for key in products["skipped"] if key.startswith("runs/")], products["skipped"]
    for run_id in RUN_IDS:
        assert log.count(f"point={run_id} product=all: the recorded status is RAN_MISSING_LOG") == 1


def test_p0370_s1_a_batch_not_moved_home_is_rebuilt_from_its_folder(tmp_path, capsys):
    """P0370-S1-REBUILD-LOST (FR-412 R1b): the batch folder before it moved, then collect, post.

    ``runs.json`` was lost before the batch was collected: the simulations
    are only in ``sims/batch/<matrix>_b1/``. Each point is rebuilt from there,
    naming its batch and carrying its job entry, and left SUBMITTED for
    ``collect``, which moves it home and completes it; the rebuild itself
    writes nothing in the tree.
    """
    workspace = grouped_workspace(tmp_path / "ws", collect=False)
    the_owner_s_deletions(workspace)
    batch = workspace.root / "sims" / "batch" / BATCH
    assert (batch / "sim_7001" / "datapoints").is_dir()
    code, said = pyfs(["rebuild", "--apply"], workspace.root, capsys)
    assert code == 0, said
    assert "rebuild: 3 rebuilt, 0 refused" in said.splitlines(), said
    records = _records(workspace.root)
    assert {row["status"] for row in records.values()} == {"SUBMITTED"}, said
    for run_id, record in records.items():
        assert record["submission"]["batch"] == BATCH, run_id
        assert record["submission"]["job"]["order"] == RUN_IDS.index(run_id) + 1, run_id
        assert "collect moves them home" in record["warnings"][0], record["warnings"]
    assert (batch / "sim_7001" / "datapoints").is_dir()  # the rebuild moved nothing
    code, said = pyfs(["collect", "--no-post"], workspace.root, capsys)
    assert code == 0, said
    records = _records(workspace.root)
    assert {row["status"] for row in records.values()} == {"RAN_MISSING_LOG"}, said
    assert (workspace.root / "sims" / "sim_7001" / "datapoints").is_dir()
    products, _log = _posted(workspace.root, capsys)
    assert set(products["provenance"]) == set(RUN_IDS)


def test_p0370_s1_every_refusal_names_the_simulation_its_reason_and_its_remedy(tmp_path, capsys):
    """P0370-S1-REBUILD-LOST (FR-412 R3): the refused simulation, why, what to do, and the counts.

    One simulation's datapoint folder is emptied: it is refused by name with
    the reason in plain words and the remedy, and the summary ends with the
    count rebuilt and the count refused. With nothing to rebuild, ``--apply``
    still prints every refusal with its remedy, not only that nothing was
    written.
    """
    workspace = grouped_workspace(tmp_path / "ws")
    the_owner_s_deletions(workspace)
    emptied = workspace.root / "sims" / "sim_7003" / "datapoints" / "DP-V0300RE120AL+000"
    for path in emptied.iterdir():
        if path.is_file():
            path.unlink()
    code, said = pyfs(["rebuild"], workspace.root, capsys)
    assert code == 0, said
    line = next(text for text in said.splitlines() if text.startswith("  sim_7003:"))
    assert "NOT RECOVERABLE" in line and RUN_IDS[2] in line, line
    assert "holds no declared output, so there is no run to record" in line, line
    assert "run the point again" in line, line
    assert "rebuild: 2 rebuilt, 1 refused" in said.splitlines(), said
    for sim in ("7001",):
        folder = workspace.root / "sims" / f"sim_{sim}" / "datapoints"
        for point in folder.iterdir():
            for path in point.iterdir():
                if path.is_file():
                    path.unlink()
    code, said = pyfs(["rebuild", "--apply"], workspace.root, capsys)
    assert code == 2, said
    assert "rebuild: no record was rebuilt, so there is nothing to write" in said, said
    assert "sim_7001: NOT RECOVERABLE" in said and "sim_7003: NOT RECOVERABLE" in said, said
    assert said.count("run the point again") == 2, said
    assert "rebuild: 0 rebuilt, 2 refused" in said, said
    assert not (workspace.root / "runs.json").exists()
