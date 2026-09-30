"""A sync reports the points the other workspace planned that no merged record carries (0.30.0).

A row of ten planned points recorded six on an HPC workspace, and nothing
said so. The other workspace's ``post/<stem>/plan.json`` lists what its plan
called for; after the merge, a planned point no record carries was never
attempted there. The sync entry records it per matrix and the CLI prints it.
"""
# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-175.

from __future__ import annotations

import json

from pyflightstream.run import cli as matrix_cli
from pyflightstream.workspace import storage as storage_module
from tests.tier1_offline.test_goal035_storage import _record, _sync_pair

PLANNED = [f"campo/sim_4016/J{index:02d}" for index in range(1, 11)]


def _plan(workspace, stem: str, run_ids: list[str]) -> None:
    folder = workspace.root / "post" / stem
    folder.mkdir(parents=True, exist_ok=True)
    points = [{"run_id": run_id, "sim_id": "4016", "status": "READY"} for run_id in run_ids]
    (folder / "plan.json").write_text(json.dumps({"points": points}), encoding="utf-8")


def test_sync_names_the_planned_points_no_merged_record_carries(tmp_path, capsys):
    main, other = _sync_pair(tmp_path, "plan")
    _plan(other, "hpc", PLANNED)
    for run_id in PLANNED[:6]:
        other.append_record(_record("4016", run_id))
    (entry,) = storage_module.sync_workspaces(main.root, "runs", apply=False)
    report = entry["plan_points_without_record"]
    assert report == {"hpc": {"planned": 10, "without_record": PLANNED[6:]}}
    recorded = storage_module.read_storage_calls(main.root)[-1]
    assert recorded["plan_points_without_record"] == report
    matrix_cli._print_sync(entry)
    out = capsys.readouterr().out
    assert "PLANNED WITHOUT RECORD hpc: 4 of 10 planned point(s)" in out
    assert "campo/sim_4016/J07" in out and "campo/sim_4016/J10" in out


def test_a_point_main_already_records_is_not_reported(tmp_path, capsys):
    main, other = _sync_pair(tmp_path, "planmain")
    _plan(other, "hpc", PLANNED)
    for run_id in PLANNED[:6]:
        other.append_record(_record("4016", run_id))
    for run_id in PLANNED[6:]:
        main.append_record(_record("4016", run_id))
    (entry,) = storage_module.sync_workspaces(main.root, "runs", apply=False)
    assert entry["plan_points_without_record"] == {"hpc": {"planned": 10, "without_record": []}}
    matrix_cli._print_sync(entry)
    assert "plan hpc: all 10 planned point(s) have a record" in capsys.readouterr().out


def test_an_unreadable_plan_is_named(tmp_path):
    main, other = _sync_pair(tmp_path, "planbad")
    folder = other.root / "post" / "hpc"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "plan.json").write_text("{not json", encoding="utf-8")
    (entry,) = storage_module.sync_workspaces(main.root, "runs", apply=False)
    assert "could not be read" in entry["plan_points_without_record"]["hpc"]["error"]
