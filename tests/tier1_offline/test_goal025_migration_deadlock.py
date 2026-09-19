"""Tier 1: a 0.20.x workspace with SUBMITTED points can be migrated (0.21.1).

A 0.20.x workspace whose points are SUBMITTED and have finished -- every
declared export on disk, and the record still reading SUBMITTED because nothing
has collected it -- could not be migrated by either command:

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

import pytest

from pyflightstream.run.collect import _datapoint_of, collect_once
from pyflightstream.workspace import RunStatus, WorkspaceError
from tests.tier1_offline.test_collect_stage import _no_sleep, _submitted_workspace
from tests.tier1_offline.test_goal024_profile_log import _profile_text

FIXTURES = Path(__file__).parent / "fixtures"
STEM = "POLAR-9001_M14AL+020BE+000J+080"
# AN INVENTED JOB ID. The first writing copied a real one out of a
# scheduler log, which puts a workplace identifier in a public test.
POL, JOB = "9001", "1200345"

#: THE 0.20 TAG, in the scheme that release actually wrote: alpha, beta and the
#: advance ratio at one decimal. Not a 0.21.0 name, which is what makes this
#: module measure the thing it is about.
OLD_TAG = "a+02.0_b+00.0_j+00.8"


def _a_0_20_workspace(tmp_path, *, with_native_log: bool = True):
    """A workspace in the shape 0.20.x left: no point name, the old tag folder.

    The job has FINISHED -- every declared export is on disk and the scheduler's
    own log is beside them -- and the record still reads SUBMITTED, because
    nothing has collected it. That is the state a scheduler leaves behind.

    THE FOLDER IS NAMED BY THE 0.20 TAG, which is the whole point of the module
    and was the defect of its first writing: it reached for a shared helper that
    hardcodes `DP-AL+000`, a 0.21.0-STYLE name, so the old-tag folder this fix
    exists for was never once constructed and the path was unmeasured (the V&V
    lens, FIX-0211).
    """
    workspace, sim = _submitted_workspace(tmp_path, declared=(f"{STEM}.txt", f"{STEM}_log.txt"))
    hpc = workspace.inputs_dir / "hpc"
    hpc.mkdir(parents=True, exist_ok=True)
    (hpc / "cluster.toml").write_text(_profile_text(), encoding="utf-8")

    work = sim / "datapoints" / f"DP-{OLD_TAG}"
    work.mkdir(parents=True, exist_ok=True)
    shutil.copy2(FIXTURES / "loads_steady_26.120.txt", work / f"{STEM}.txt")
    if with_native_log:
        # THE LOG THE SCHEDULER WROTE, which is the only log on a machine that
        # aborts at EXPORT_LOG. Its siblings are there too, because the pattern
        # has to tell them apart.
        # RENUMBERED TO END WHERE THE EXPORT ENDS (0.24.0). The two fixtures are
        # of two runs, the export at iteration 312 and the log at 1575, and the
        # assessor now refuses a log that is not of the export beside it. What
        # this case asserts is unchanged.
        (work / f"FTS{POL}.l{JOB}").write_text(
            (FIXTURES / "log_residuals_26.120.txt")
            .read_text(encoding="utf-8")
            .replace(chr(10) + "1575 ", chr(10) + "312 ")
            .replace(chr(10) + "1574 ", chr(10) + "311 "),
            encoding="utf-8",
        )
        (work / f"FTS{POL}.e{JOB}").write_text("", encoding="utf-8")
        (work / f"FTS{POL}.o{JOB}").write_text("", encoding="utf-8")

    rows = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    for row in rows:
        # WHAT MAKES IT 0.20.x: the fields this release added are simply absent,
        # and the folder the job ran in is named by the earlier tag.
        row.pop("point_name", None)
        row.pop("sweep_name", None)
        row["submission"] = {
            **dict(row.get("submission") or {}),
            "working_dir": f"datapoints/{work.name}",
        }
        # AND THE run_id ENDS IN THE TAG, which is what 0.20.x wrote and what
        # `pyfs-matrix rename` reads a pre-0.21.0 record by. The first writing
        # left the shared fixture's 0.21.0-style tail here, so the record
        # disagreed with its own folder in a way no 0.20.x workspace does.
        row["run_id"] = f"camp/sim_{row['sim_id']}/{OLD_TAG}"
        # The loads fixture prints alpha 2.0, so the record must have REQUESTED
        # it; the collector checks the export against the point it was asked for.
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
    # THE SHAPE UNDER TEST, stated so a later edit to the fixture cannot quietly
    # turn this back into a 0.21.0 name and leave the module asserting nothing.
    assert work.name == f"DP-{OLD_TAG}", work.name
    assert "+02.0" in work.name, "the folder carries the 0.20 tag, not a point name"

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


def test_goal025_a_working_dir_that_is_not_a_datapoint_folder_is_refused_for_what_it_is(
    tmp_path,
):
    """The OTHER way there is no answer, and the refusal must not misstate which.

    `_datapoint_of` returns None for a record with no working directory AND for
    one whose working directory is not a datapoint folder at all -- which is
    what a pre-0.18.1 job that ran in the simulation folder records. The first
    writing asserted "names no working directory" for both, and `collect` writes
    that sentence into `record.error` on disk, so the manifest would have
    carried a statement the code never checked (the V&V lens, FIX-0211).
    """
    from pyflightstream.run.collect import _datapoint_of, _recorded_name

    workspace, work = _a_0_20_workspace(tmp_path)
    rows = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    for row in rows:
        # A working directory that IS named and is not a datapoint folder.
        row["submission"] = {**dict(row.get("submission") or {}), "working_dir": "."}
    workspace.manifest_path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    record = workspace.read_manifest()[0]

    assert _datapoint_of(record) is None, "this is the second way there is no answer"
    with pytest.raises(WorkspaceError) as raised:
        _recorded_name(record)

    detail = str(raised.value)
    assert "is not a datapoint folder" in detail, detail
    assert "names no working directory" not in detail, (
        "the refusal must not assert the case that did NOT hold"
    )
    # And it names the field to set, which is the fix rather than the cause.
    assert "submission.working_dir" in detail and "runs.json" in detail, detail

    # THE ARM IS UNREACHED THROUGH THE SWEEP, and saying so is the honest form.
    # `_working_dir` resolves the same field first and refuses anything whose
    # parent is not this record's own `datapoints/`, so `collect_once` never
    # arrives here. Measured, not assumed: the sweep's own refusal is the one a
    # user sees, and it is a different sentence.
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)
    seen = [outcome.detail for outcome in report.failed + report.waiting]
    assert not any("is not a datapoint folder" in text for text in seen), seen


def test_goal025_a_folder_name_that_is_not_a_point_name_does_not_abort_the_sweep(tmp_path):
    """A folder `PointName` refuses must not take the whole sweep down with it.

    Reading a folder tag into the checked `PointName` moved a value of
    unvalidated provenance into a constructor whose refusal is a
    `NamingTemplateError` -- a ValueError, NOT a `WorkspaceError`, so the
    sweep's handler does not catch it. Measured: a folder named `DP-a b`, legal
    on every filesystem this package runs on and refused because the portability
    check bars whitespace, aborted `collect_once` and left a HEALTHY 0.21.0
    point beside it uncollected (the architect lens, FIX-0211).

    THE ASSERTION IS ABOUT THE OTHER POINT, not about the bad one: the damage
    was never the raise, it was every other record in the workspace.
    """
    workspace, work = _a_0_20_workspace(tmp_path)
    bad = work.parent / "DP-a b"
    bad.mkdir(parents=True, exist_ok=True)
    shutil.copy2(work / f"{STEM}.txt", bad / f"{STEM}.txt")
    shutil.copy2(FIXTURES / "log_residuals_26.120.txt", bad / f"{STEM}_log.txt")
    # THE HEALTHY POINT NEEDS ITS OWN FOLDER: sharing the broken record's
    # working_dir makes `collect_outputs` refuse its outputs as another point's,
    # which is a different refusal than the one under test.
    good = work.parent / "DP-AL+020"
    good.mkdir(parents=True, exist_ok=True)
    shutil.copy2(work / f"{STEM}.txt", good / f"{STEM}.txt")
    shutil.copy2(FIXTURES / "log_residuals_26.120.txt", good / f"{STEM}_log.txt")
    rows = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    healthy = {
        **dict(rows[0]),
        "run_id": "camp/sim_9001/AL+020",
        "point_name": "AL+020",
        "submission": {
            **dict(rows[0].get("submission") or {}),
            "working_dir": "datapoints/DP-AL+020",
        },
    }
    broken = {
        **dict(rows[0]),
        "run_id": "camp/sim_9001/a b",
        "submission": {**dict(rows[0].get("submission") or {}), "working_dir": "datapoints/DP-a b"},
    }
    workspace.manifest_path.write_text(
        json.dumps([broken, healthy], indent=2) + "\n", encoding="utf-8"
    )

    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)

    assert len(report.collected) == 1, [outcome.detail for outcome in report.failed]
    assert report.collected[0].run_id == "camp/sim_9001/AL+020", report.collected


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


def test_goal025_a_swept_row_record_with_no_folder_at_all_does_not_abort_the_sweep(tmp_path):
    """The door the first fix did not cover, and the one that was blocking.

    A 0.20.x SUBMITTED SWEPT ROW carries neither a point name nor a working
    directory: the whole sweep was ONE job in the SIMULATION folder, and only a
    per-point submission writes a working directory. `_datapoint_of` answers
    None, `_collect_by_point` takes its multi-point branch so `_recorded_name`
    never fires, collection SUCCEEDS -- and the shim then reached the assessor
    with no name and fell into the branch written for a real case, raising
    AttributeError on `condition_order`. That is not a WorkspaceError, so the
    sweep does not catch it and the collection of every remaining point is
    abandoned (the qa lens, FIX-0211).

    ITS OWN WORKSPACE, not the per-point fixture: that one creates the datapoint
    folder and puts the export in it, so a swept row declaring the same file
    name is refused by the collision guard before the assessor is reached --
    measured, and it is why the first writing of this test scored a SURVIVING
    mutant while reading as though it covered the defect.
    """
    workspace, sim = _submitted_workspace(tmp_path, declared=(f"{STEM}.txt", f"{STEM}_log.txt"))
    hpc = workspace.inputs_dir / "hpc"
    hpc.mkdir(parents=True, exist_ok=True)
    (hpc / "cluster.toml").write_text(_profile_text(), encoding="utf-8")
    # THE SWEEP WROTE IN THE SIMULATION FOLDER, which is where such a job ran.
    shutil.copy2(FIXTURES / "loads_steady_26.120.txt", sim / f"{STEM}.txt")
    shutil.copy2(FIXTURES / "log_residuals_26.120.txt", sim / f"{STEM}_log.txt")

    rows = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    swept = dict(rows[0])
    swept.pop("point_name", None)
    swept.pop("sweep_name", None)
    swept["run_id"] = "camp/sim_9001/sweep"
    swept["point"] = {**dict(swept.get("point") or {}), "alpha": 2.0}
    swept["submission"] = {
        key: value
        for key, value in dict(swept.get("submission") or {}).items()
        if key != "working_dir"
    }
    swept["submission"]["declared_by_point"] = {
        OLD_TAG: [f"{STEM}.txt", f"{STEM}_log.txt"],
        "a+04.0_b+00.0_j+00.8": [],
    }
    swept["submission"]["points_by_tag"] = {
        OLD_TAG: {"alpha": 2.0},
        "a+04.0_b+00.0_j+00.8": {"alpha": 4.0},
    }
    workspace.manifest_path.write_text(json.dumps([swept], indent=2) + "\n", encoding="utf-8")

    record = workspace.read_manifest()[0]
    assert record.point_name is None
    assert not (record.submission or {}).get("working_dir")
    assert _datapoint_of(record) is None, "neither source names a folder: this is the shape"

    # THE ASSERTION IS THAT collect_once RETURNS. Before the fix it raised
    # AttributeError out of the sweep and took every other point with it.
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)

    assert report is not None
    assert report.collected or report.failed or report.waiting, "the record was reached"


def test_goal025_a_working_dir_naming_another_points_folder_is_not_taken(tmp_path):
    """The fallback must not make a hand-edited field an identity.

    `_working_dir` checks that the working directory is A datapoint folder of
    this simulation and never that it is THIS record's. A record carrying a
    point name is caught downstream by the trespass guard; a 0.20.x record
    without one was accepted and filed its outputs into another point's folder
    IN PLACE, because a job that ran in its own folder is allowed to record what
    is already there (the qa lens, FIX-0211).

    A 0.20.x record ends its `run_id` in the tag, so it carries its own
    cross-check, and this asserts the helper refuses to answer when the two
    disagree rather than trusting the edited field.
    """
    from pyflightstream.run.collect import _datapoint_of

    workspace, work = _a_0_20_workspace(tmp_path)
    rows = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    rows[0]["submission"] = {
        **dict(rows[0].get("submission") or {}),
        "working_dir": "datapoints/DP-a+09.0_b+00.0_j+00.8",
    }
    workspace.manifest_path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    record = workspace.read_manifest()[0]

    assert str(record.run_id).endswith(OLD_TAG), record.run_id
    assert _datapoint_of(record) is None, (
        "the record's own run_id names a different point than the edited working_dir"
    )


def test_goal025_a_recorded_name_wins_over_a_folder_that_disagrees(tmp_path):
    """THE FALLBACK CONTROL, with the fallback input PRESENT.

    The earlier control had no `working_dir` at all, so it proved the recorded
    name wins over nothing. This gives the record both, disagreeing, and asserts
    the recorded name is what answers: a fallback that can override the thing it
    falls back FROM is not a fallback.
    """
    from pyflightstream.run.collect import _datapoint_of, _RecordAsCase

    workspace, work = _a_0_20_workspace(tmp_path)
    rows = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    rows[0]["point_name"] = "AL+020"
    rows[0]["submission"] = {
        **dict(rows[0].get("submission") or {}),
        "working_dir": f"datapoints/{work.name}",
    }
    workspace.manifest_path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    record = workspace.read_manifest()[0]

    assert _datapoint_of(record) == "AL+020", "the recorded name, not the folder"
    assert _RecordAsCase(record).datapoint_name == "AL+020"
