"""The collect stage: four findings of the 0.24.0 review, each as its own assertion.

QUEUED-SWEEP-UNREPRESENTABLE
    Every point of a submitted steady sweep receives its own collected outputs,
    its own assessment and its own status, in the shape the local sweep writes.
FROZEN-NATIVE-LOG
    Readiness is established from the file the scheduler is still writing, never
    from a copy of it taken before the two observations.
COLLECT-ASSESSMENT-PARITY
    A collected point is held to the velocity the run requested, as a local
    point is, and the record keeps the conditions that were compared.
COLLECT-POST-NO-MATRIX
    ``collect --post`` rebuilds the products of the matrices whose records it
    collected.
"""

from __future__ import annotations

import json

from pyflightstream.run import cli as cli_mod
from pyflightstream.run.collect import collect_once
from pyflightstream.workspace import RunStatus
from tests.tier1_offline.test_collect_stage import (
    _no_sleep,
    _submitted_sweep,
    _submitted_workspace,
)
from tests.tier1_offline.test_goal024_profile_log import _work_dir, _write_profile
from tests.tier1_offline.test_run_campaign import FIXTURES

_ALPHA_LINE = "Angle of attack (Deg)                       2.000"
_VELOCITY_LINE = "Freestream velocity (m/s)                   30.000"


def _loads(alpha: float = 2.0, *, diverged: bool = False) -> str:
    """The recorded steady export, as the solver would print it at ``alpha``."""
    text = (FIXTURES / "loads_steady_26.120.txt").read_text(encoding="utf-8")
    assert _ALPHA_LINE in text and _VELOCITY_LINE in text
    text = text.replace(_ALPHA_LINE, f"Angle of attack (Deg)                       {alpha:.3f}")
    if diverged:
        assert "+0.0089000," in text
        text = text.replace("+0.0089000,", "NaN,")
    return text


def _log(*, rows_until: int | None = None) -> str:
    """The recorded log, renumbered to end where the steady export ends (312)."""
    text = (FIXTURES / "log_residuals_26.120.txt").read_text(encoding="utf-8")
    text = text.replace("\n1575 ", "\n312 ").replace("\n1574 ", "\n311 ")
    if rows_until is None:
        return text
    kept = []
    for line in text.splitlines(keepends=True):
        head = line.split(maxsplit=1)[0] if line.strip() else ""
        if head.isdigit() and int(head) > rows_until:
            continue
        kept.append(line)
    return "".join(kept)


# ------------------------------------------------ QUEUED-SWEEP-UNREPRESENTABLE


def _collected_sweep(tmp_path, *, second_diverged=False, assessor=None):
    workspace, sim = _submitted_sweep(tmp_path)
    (sim / "AL+000.txt").write_text(_loads(0.0), encoding="utf-8")
    (sim / "AL+020.txt").write_text(_loads(2.0, diverged=second_diverged), encoding="utf-8")
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep, assessor=assessor)
    return workspace, report


def test_every_point_of_a_collected_sweep_carries_its_own_outputs(tmp_path):
    workspace, report = _collected_sweep(tmp_path)
    assert len(report.collected) == 1, report.lines()
    job = workspace.read_manifest()[0]
    by_tag = {entry["tag"]: entry for entry in job.points_ran}
    assert by_tag["AL+000"].get("outputs") == ["datapoints/DP-AL+000/AL+000.txt"]
    assert by_tag["AL+020"].get("outputs") == ["datapoints/DP-AL+020/AL+020.txt"]
    # What the products stage reads: one record per point, none of them empty.
    points = job.as_points()
    assert [point.point_name for point in points] == ["AL+000", "AL+020"]
    assert all(point.outputs for point in points), [point.outputs for point in points]
    assert sorted(job.outputs) == sorted(
        ["datapoints/DP-AL+000/AL+000.txt", "datapoints/DP-AL+020/AL+020.txt"]
    )


def test_every_point_of_a_collected_sweep_is_assessed_on_its_own_export(tmp_path):
    workspace, _report = _collected_sweep(tmp_path)
    job = workspace.read_manifest()[0]
    assert job.status is RunStatus.CONVERGED, job.error
    for entry in job.points_ran:
        assert entry["status"] == "CONVERGED", entry
        # 312 is the iteration the recorded steady export stopped at.
        assert entry.get("iterations") == 312, entry


def test_one_bad_point_of_a_collected_sweep_does_not_speak_for_the_others(tmp_path):
    workspace, _report = _collected_sweep(tmp_path, second_diverged=True)
    job = workspace.read_manifest()[0]
    statuses = {entry["tag"]: entry["status"] for entry in job.points_ran}
    assert statuses == {"AL+000": "CONVERGED", "AL+020": "FAILED_DIVERGED"}
    # The job's headline is its worst point, and the error says which.
    assert job.status is RunStatus.FAILED_DIVERGED
    assert "AL+020" in (job.error or "")
    assert "AL+000" not in (job.error or "")
    # The healthy point keeps its evidence.
    healthy = next(point for point in job.as_points() if point.point_name == "AL+000")
    assert healthy.status is RunStatus.CONVERGED
    assert healthy.outputs == ["datapoints/DP-AL+000/AL+000.txt"]


def test_a_replaced_assessor_is_asked_about_each_point_of_a_sweep(tmp_path):
    asked: list[tuple[str | None, dict, list[str]]] = []

    def assessor(record, _sim_dir):
        asked.append((record.point_name, dict(record.point), list(record.outputs)))
        verdict = RunStatus.COMPLETED_MAX_ITER if record.point_name == "AL+020" else None
        return verdict or RunStatus.CONVERGED, None

    workspace, _report = _collected_sweep(tmp_path, assessor=assessor)
    assert asked == [
        ("AL+000", {"alpha": 0.0}, ["datapoints/DP-AL+000/AL+000.txt"]),
        ("AL+020", {"alpha": 2.0}, ["datapoints/DP-AL+020/AL+020.txt"]),
    ]
    job = workspace.read_manifest()[0]
    statuses = {entry["tag"]: entry["status"] for entry in job.points_ran}
    assert statuses == {"AL+000": "CONVERGED", "AL+020": "COMPLETED_MAX_ITER"}
    assert all(entry.get("outputs") for entry in job.points_ran)


# ----------------------------------------------------------- FROZEN-NATIVE-LOG


def _native_log_workspace(tmp_path):
    workspace, sim = _submitted_workspace(tmp_path, declared=("loads.txt", "P9001-AL+000_log.txt"))
    _write_profile(workspace)
    work = _work_dir(workspace, sim, alpha=2.0)
    (work / "loads.txt").write_text(_loads(2.0), encoding="utf-8")
    return workspace, work


def test_a_scheduler_log_still_being_written_is_not_collected(tmp_path):
    workspace, work = _native_log_workspace(tmp_path)
    native = work / "FTS9001.l3714205"
    native.write_text(_log(rows_until=2), encoding="utf-8")

    def the_job_keeps_writing(_seconds):
        native.write_text(_log(), encoding="utf-8")

    report = collect_once(workspace, interval=0.0, sleep=the_job_keeps_writing)
    assert [outcome.state for outcome in report.waiting] == ["WAITING"], report.lines()
    assert not report.collected and not report.failed, report.lines()
    assert workspace.read_manifest()[0].status is RunStatus.SUBMITTED


def test_the_log_the_run_is_judged_by_is_the_scheduler_s_final_one(tmp_path):
    workspace, work = _native_log_workspace(tmp_path)
    native = work / "FTS9001.l3714205"
    native.write_text(_log(rows_until=2), encoding="utf-8")
    collect_once(
        workspace,
        interval=0.0,
        sleep=lambda _seconds: native.write_text(_log(), encoding="utf-8"),
    )
    # The job has ended: nothing moves between the two observations now.
    report = collect_once(workspace, interval=0.0, sleep=_no_sleep)
    assert [outcome.state for outcome in report.collected] == ["COLLECTED"], report.lines()
    declared = work / "P9001-AL+000_log.txt"
    assert declared.read_text(encoding="utf-8") == _log()
    record = workspace.read_manifest()[0]
    assert record.status is RunStatus.CONVERGED, record.error
    assert record.iterations == 312


# --------------------------------------------------- COLLECT-ASSESSMENT-PARITY


def _collect_at_requested_velocity(tmp_path, requested: float):
    workspace, sim = _submitted_workspace(tmp_path, declared=("loads.txt",))
    work = _work_dir(workspace, sim, alpha=2.0)
    rows = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    rows[0]["velocity_requested_m_s"] = requested
    workspace.manifest_path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    # The recorded export prints a free-stream velocity of 30 m/s.
    (work / "loads.txt").write_text(_loads(2.0), encoding="utf-8")
    collect_once(workspace, interval=0.0, sleep=_no_sleep)
    return workspace.read_manifest()[0]


def test_a_collected_export_at_another_velocity_is_refused_as_a_local_one_is(tmp_path):
    record = _collect_at_requested_velocity(tmp_path, 80.0)
    assert record.status is RunStatus.FAILED_INCOMPLETE_OUTPUT
    assert "velocity" in (record.error or "")


def test_a_collected_export_at_the_requested_velocity_is_accepted(tmp_path):
    record = _collect_at_requested_velocity(tmp_path, 30.0)
    assert record.status is RunStatus.CONVERGED, record.error


def test_a_collected_record_keeps_the_conditions_that_were_compared(tmp_path):
    record = _collect_at_requested_velocity(tmp_path, 30.0)
    assert record.conditions, "the completed record dropped the assessed conditions"
    compared = {str(entry["axis"]) for entry in record.conditions}
    assert {"alpha", "velocity"} <= compared, record.conditions


# ------------------------------------------------------ COLLECT-POST-NO-MATRIX


def test_collect_post_rebuilds_the_matrix_whose_records_it_collected(tmp_path, monkeypatch):
    workspace, sim = _submitted_workspace(tmp_path, declared=("loads.txt",))
    work = _work_dir(workspace, sim, alpha=2.0)
    (work / "loads.txt").write_text(_loads(2.0), encoding="utf-8")
    calls: list[dict[str, object]] = []

    def stage(ws, **keywords):
        calls.append(dict(keywords))
        return []

    monkeypatch.setattr("pyflightstream.workspace.post_stages", lambda: [stage])
    status = cli_mod.main(["collect", "--workspace", str(workspace.root), "--interval", "0"])
    assert status == 0
    # The fixture's record names the matrix `matriz`.
    assert [call.get("matrix_stem") for call in calls] == ["matriz"], calls
    # A rebuild archives what it replaces, as `pyfs-matrix post` does: without
    # it the second sweep of a watch meets the first one's products and stops.
    assert calls[0].get("overwrite") is True and calls[0].get("archive") is True, calls


def test_each_collected_matrix_is_posted_once_and_a_sweep_that_collects_nothing_posts_nothing(
    tmp_path,
):
    from pyflightstream.run.collect import collect_and_post

    workspace, sim = _submitted_workspace(tmp_path, declared=("a.txt",))
    rows = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    second = {**rows[0], "run_id": "camp/sim_9001/AL+020", "point_name": "AL+020"}
    second["matrix_stem"] = "outra"
    second["submission"] = {**rows[0]["submission"], "declared_outputs": ["b.txt"]}
    third = {**rows[0], "run_id": "camp/sim_9001/AL+040", "point_name": "AL+040"}
    third["submission"] = {**rows[0]["submission"], "declared_outputs": ["c.txt"]}
    workspace.manifest_path.write_text(
        json.dumps([rows[0], second, third], indent=2) + "\n", encoding="utf-8"
    )
    for name in ("a.txt", "b.txt", "c.txt"):
        (sim / name).write_text("written by the job", encoding="utf-8")
    posted: list[str | None] = []

    def accept(_record, _sim_dir):
        return RunStatus.CONVERGED, None

    collect_and_post(
        workspace,
        interval=0.0,
        sleep=_no_sleep,
        assessor=accept,
        post_matrix=lambda _ws, stem: posted.append(stem),
    )
    # Two records of `matriz` and one of `outra`: one rebuild each, first seen first.
    assert posted == ["matriz", "outra"]

    collect_and_post(
        workspace,
        interval=0.0,
        sleep=_no_sleep,
        assessor=accept,
        post_matrix=lambda _ws, stem: posted.append(stem),
    )
    assert posted == ["matriz", "outra"], "a sweep that collected nothing rebuilt products"
