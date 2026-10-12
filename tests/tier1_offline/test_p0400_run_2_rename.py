"""Tier 1, 0.40.0 lane run-2: ``pyfs-matrix rename``, the move to the 0.21.0 names.

The workspaces are the real ones of the GOAL-024 rename tests: a matrix run
through the campaign loop and written back into the 0.20.x shape.
"""

from __future__ import annotations

from pathlib import Path

from pyflightstream.run import records
from pyflightstream.run import rename as rename_module
from pyflightstream.run.rename import rename_workspace
from tests.tier1_offline.test_goal024_rename_command import _as_0_20, _ran, _reopened


def test_p0400_rename_takes_the_stem_of_a_lone_log_without_its_export_suffix():
    """P0400-RENAME-LONE-LOG (PFS-2096.007): a record whose only output is its log.

    ``Path.stem`` of ``<stem>_log.txt`` is ``<stem>_log``, and the move then
    wrote ``<new stem>.txt``, the name of the loads export.
    """
    stem = "POLAR-3207_M20AL+000BE+000"
    assert rename_module._stem_of([f"{stem}_log.txt"]) == stem
    assert rename_module._stem_of([f"{stem}_cp.txt"]) == stem
    assert rename_module._stem_of([f"{stem}.txt"]) == stem
    assert rename_module._stem_of([f"{stem}.txt", f"{stem}_log.txt"]) == stem


def test_p0400_rename_keeps_a_delete_sims_note_and_writes_nothing_when_nothing_moves(tmp_path):
    """P0400-RENAME-NOTES (PFS-2096.024): a note row is carried through, in its place.

    The rewritten manifest was built from the plans alone, so a manifest
    holding a delete-sims note always differed from it and lost the note.
    """
    workspace, _, _ = _ran(tmp_path)
    rows = workspace.read_raw_manifest()
    note = {
        "run_id": "deleted/sim_9999/20261012-120000",
        "deleted_sim": "9999",
        "deleted_at": "2026-10-12T12:00:00+00:00",
        "deleted_run_ids": ["named/sim_9999/M200RE230AL+000"],
        "note": "this simulation id belonged to a simulation deleted by pyfs-matrix delete-sims",
        "storage_entry": 0,
    }
    workspace._replace_manifest([rows[0], note, *rows[1:]])
    before = workspace.manifest_path.read_bytes()
    rename_workspace(_reopened(workspace))
    assert workspace.manifest_path.read_bytes() == before
    assert not list((workspace.root / "archive").glob("runs-*.json"))


def test_p0400_rename_rewrites_each_plan_entry_with_its_own_simulation_s_names(tmp_path):
    """P0400-RENAME-PLAN-PER-SIM (PFS-2096.009): two rows at two Mach share the 0.20 tags.

    One merged tag-to-name map gave every plan entry the last simulation's
    names; each entry now takes the names of its own simulation's records.
    """
    import json
    import shutil

    from pyflightstream.cases.workflows import workflow_registry
    from pyflightstream.run.matrix import run_matrix
    from pyflightstream.workspace import RunStatus
    from tests.tier1_offline.test_goal024_point_name import _matrix
    from tests.tier1_offline.test_matrix_run import RECIPES, WRITES_EVERY_EXPORT, CountingStub
    from tests.tier1_offline.test_matrix_run import converged as assess

    workspace, matrix = _matrix(
        tmp_path, condition="MACH:0.2, REmi:2.3, ALPHA:sweep", values="-2.0,0.0"
    )
    lines = matrix.read_text(encoding="utf-8").splitlines()
    second = lines[2].replace("3207", "3208", 1).replace("MACH:0.2", "MACH:0.3")
    matrix.write_text("\n".join([*lines, second]) + "\n", encoding="utf-8")
    matrix = Path(shutil.copy2(matrix, workspace.root / matrix.name))
    ran = run_matrix(
        matrix,
        workspace,
        name="named",
        default_fs_version="26.120",
        recipes=RECIPES,
        recipe_registry=workflow_registry(),
        assess=assess,
        executor=CountingStub(WRITES_EVERY_EXPORT),
    )
    assert {record.sim_id for record in ran} == {"3207", "3208"}
    assert all(record.status is RunStatus.CONVERGED for record in ran)
    plan_file = workspace.plan_dir("named") / "plan.json"
    expected = {
        entry["run_id"]: entry["sim_id"]
        for entry in json.loads(plan_file.read_text(encoding="utf-8"))["points"]
    }
    _as_0_20(workspace, mach=0.2)
    rename_workspace(_reopened(workspace))
    renamed = {
        entry["run_id"]: entry["sim_id"]
        for entry in json.loads(plan_file.read_text(encoding="utf-8"))["points"]
    }
    assert renamed == expected


def test_p0400_rename_archives_in_local_time_so_restore_takes_the_newest(tmp_path, monkeypatch):
    """P0400-RENAME-ARCHIVE (PFS-2096.008, PFS-2096.006): rename stamps as every archiver does.

    A UTC stamp sorted against the local stamps of the other archivers, so a
    later mark-failed copy lost to the rename's as the newest. The stamps are
    pinned to one moment in 2000; a UTC stamp of the real clock sorts after
    both of them.
    """
    workspace, _, _ = _ran(tmp_path)
    _as_0_20(workspace, mach=0.2)
    monkeypatch.setattr(rename_module, "_now_stamp", lambda: "20000101-000000", raising=False)
    monkeypatch.setattr(records, "_now_stamp", lambda: "20000101-000001")
    rename_workspace(_reopened(workspace))
    renamed = workspace.manifest_path.read_bytes()
    records.mark_failed(workspace.root, ["3207"], reason="wrong mesh", apply=True)
    archive = workspace.root / "archive"
    assert (archive / "runs-20000101-000000.json").is_file()
    entry = records.restore(workspace.root, "runs")
    assert entry["source"] == "archive/runs-20000101-000001.json", entry["source"]
    assert (workspace.root / entry["source"]).read_bytes() == renamed
