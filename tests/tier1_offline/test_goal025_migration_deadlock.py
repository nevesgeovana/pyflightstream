"""Tier 1: a 0.20.x workspace with SUBMITTED points can be migrated (0.21.1).

MEASURED ON A LIVE CLUSTER WORKSPACE, 2026-09-16. A 0.20.x workspace held
twenty-two points that had been submitted, had finished, and had every export on
disk. Neither command could move it:

    rename  refuses a SUBMITTED record whose folder would move, and says
            "collect it (pyfs-matrix collect) and rename afterwards";
    collect refused a record with no point_name, and said
            "run `pyfs-matrix rename` once ... then collect".

Each pointed at the other. And the cost was not a refusal: the WorkspaceError is
caught by the sweep and the record REWRITTEN as FAILED_INCOMPLETE_OUTPUT, so
runs that had converged would have been stamped failed and would have lost the
SUBMITTED state that lets them be collected at all.

Behind that refusal sat a second defect, which only became reachable once the
first was lifted, and which is worse because it is an AttributeError rather than
a WorkspaceError: the sweep does not catch it, so it aborts the collection of
every OTHER submitted point in the workspace. `_RecordAsCase` set its
`datapoint_name` from `record.point_name` alone, so on a 0.20.x record it was
None and the assessor fell into the branch written for a REAL case, which asks
for `condition_order`. A shim is not a case and does not have one.

Both are fixed by giving one rule one home: `_datapoint_of` answers WHICH FOLDER
THIS RECORD'S OUTPUTS ARE IN, reading the name the run recorded when it has one
and the folder its own submission block names when it does not. Nothing is
recomputed, which is what the original refusal was protecting.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from pyflightstream.run.collect import collect_once
from pyflightstream.workspace import RunStatus
from tests.tier1_offline.test_collect_stage import _no_sleep, _submitted_workspace
from tests.tier1_offline.test_goal024_profile_log import _profile_text, _work_dir

FIXTURES = Path(__file__).parent / "fixtures"
STEM = "POLAR-9001_M14AL+020BE+000J+080"
POL, JOB = "9001", "6654320"


def _a_0_20_workspace(tmp_path, *, with_native_log: bool = True):
    """A workspace in the shape 0.20.x left: no point name, the old tag folder.

    The job has FINISHED -- every declared export is on disk and the scheduler's
    own log is beside them -- and the record still reads SUBMITTED, because
    nothing has collected it. That is the state a cluster leaves.
    """
    workspace, sim = _submitted_workspace(tmp_path, declared=(f"{STEM}.txt", f"{STEM}_log.txt"))
    hpc = workspace.inputs_dir / "hpc"
    hpc.mkdir(parents=True, exist_ok=True)
    (hpc / "cluster.toml").write_text(_profile_text(), encoding="utf-8")

    work = _work_dir(workspace, sim, alpha=0.0)
    shutil.copy2(FIXTURES / "loads_steady_26.120.txt", work / f"{STEM}.txt")
    if with_native_log:
        # THE LOG THE SCHEDULER WROTE, which is the only log on a machine that
        # aborts at EXPORT_LOG. Its siblings are there too, because the pattern
        # has to tell them apart.
        shutil.copy2(FIXTURES / "log_residuals_26.120.txt", work / f"FTS{POL}.l{JOB}")
        (work / f"FTS{POL}.e{JOB}").write_text("", encoding="utf-8")
        (work / f"FTS{POL}.o{JOB}").write_text("", encoding="utf-8")

    rows = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    for row in rows:
        # WHAT MAKES IT 0.20.x: the fields this release added are simply absent.
        row.pop("point_name", None)
        row.pop("sweep_name", None)
        row["point"] = {**dict(row.get("point") or {}), "alpha": 2.0}
    workspace.manifest_path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    return workspace, work


def test_goal025_a_submitted_0_20_record_collects_in_the_folder_it_ran_in(tmp_path):
    """The deadlock is gone: a finished 0.20.x point collects, and is not failed.

    THE ASSERTION THAT MATTERS IS THE STATUS IN runs.json, not the report: the
    defect wrote FAILED_INCOMPLETE_OUTPUT to the manifest, so a test reading
    only the report's counts would have passed while the record on disk said
    the run failed.
    """
    workspace, work = _a_0_20_workspace(tmp_path)

    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)

    assert not report.failed, [outcome.detail for outcome in report.failed]
    assert len(report.collected) == 1, report
    row = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))[0]
    assert row["status"] == RunStatus.CONVERGED.value, (row["status"], row.get("error"))
    assert not row.get("error"), row["error"]
    # The scheduler's log was put where the row declared it, which is what let
    # the point settle at all.
    assert (work / f"{STEM}_log.txt").is_file()


def test_goal025_the_outputs_stay_in_the_old_folder_and_are_not_refiled(tmp_path):
    """Collected IN PLACE, under the tag folder the record itself names.

    The refusal this replaces existed to stop the outputs being filed under a
    name RECOMPUTED now, where no record of them points. That still must not
    happen: the folder is the one the record's submission block names, and the
    files do not move out of it.
    """
    workspace, work = _a_0_20_workspace(tmp_path)

    collect_once(workspace, interval=0.0, sleep=_no_sleep)

    assert work.name.startswith("DP-"), work.name
    assert (work / f"{STEM}.txt").is_file(), sorted(p.name for p in work.iterdir())
    row = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))[0]
    # The record still carries no 0.21.0 name: collecting does not invent one,
    # `pyfs-matrix rename` is what names it, and that is the documented order.
    assert not row.get("point_name")
    for output in row["outputs"]:
        assert work.name in str(output), output


def test_goal025_a_record_naming_no_folder_at_all_is_still_refused(tmp_path):
    """THE CONTROL: the refusal survives where there really is no answer.

    A point submitted before 0.18.1 names no working directory and ran in the
    simulation folder, so no datapoint folder is named for it anywhere. Lifting
    the deadlock must not lift this: without it the fix would be "accept
    everything", which is the shape this estate keeps paying for.

    ITS OUTPUTS ARE PUT IN THE SIMULATION FOLDER, which is where such a job
    wrote them. Without that the record merely WAITS -- measured, when this test
    was first written -- and a waiting record never reaches the refusal, so the
    test would have asserted nothing about the branch it names.
    """
    workspace, work = _a_0_20_workspace(tmp_path)
    sim_dir = work.parent.parent
    for name in (f"{STEM}.txt", f"{STEM}_log.txt"):
        shutil.copy2(work / f"{STEM}.txt", sim_dir / name)
    rows = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    for row in rows:
        row["submission"] = {
            key: value
            for key, value in dict(row.get("submission") or {}).items()
            if key != "working_dir"
        }
    workspace.manifest_path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")

    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)

    assert len(report.failed) == 1, report
    detail = report.failed[0].detail
    assert "names no working directory" in detail, detail
    assert "0.18.1" in detail, "the refusal says which release's records this is about"


def test_goal025_the_assessor_shim_names_the_folder_the_record_names(tmp_path):
    """The second defect, scored on its own: a shim must never reach `point_name`.

    `_RecordAsCase` is not a `SimCase` and carries no `condition_order`, so the
    assessor's branch for a real case raises AttributeError on it -- which the
    sweep does NOT catch, so one 0.20.x record would abort the collection of
    every other point in the workspace. Asserted here directly, because the
    end-to-end test above would go green again if the shim merely stopped
    raising while naming the wrong folder.
    """
    from pyflightstream.run.collect import _datapoint_of, _RecordAsCase

    workspace, work = _a_0_20_workspace(tmp_path)
    record = workspace.read_manifest()[0]

    assert record.point_name is None, "the fixture is a 0.20.x record"
    assert _datapoint_of(record) == work.name[len("DP-") :]
    assert _RecordAsCase(record).datapoint_name == _datapoint_of(record)
    assert not hasattr(_RecordAsCase(record), "condition_order"), (
        "a shim is not a case; if it grows one, the branch this guards has moved"
    )


def test_goal025_a_0_21_record_is_unchanged_by_any_of_this(tmp_path):
    """THE OTHER CONTROL: a record that DOES carry its name still names it.

    The whole fix is a fallback, and a fallback that also changes the ordinary
    path is a regression wearing a fix's clothes.
    """
    from pyflightstream.run.collect import _datapoint_of, _RecordAsCase

    workspace, _ = _submitted_workspace(tmp_path, declared=("loads.txt", "run_log.txt"))
    record = workspace.read_manifest()[0]

    assert record.point_name, "the fixture is a 0.21.0 record"
    assert _datapoint_of(record) == record.point_name
    assert _RecordAsCase(record).datapoint_name == record.point_name
