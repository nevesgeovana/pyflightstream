"""Tier 1, 0.40.0 lane run-2: the collect stage and its records.

Every fixture is synthetic.
"""

from __future__ import annotations

import inspect
import typing

from pyflightstream.run import collect


def test_p0400_collect_and_post_declares_the_sims_keyword_of_its_callbacks():
    """P0400-COLLECT-CALLBACKS (PFS-2095.027): the annotation states the keyword it is called with.

    ``post`` and ``post_matrix`` were annotated without ``sims`` and called
    with it under ``type: ignore``, so a callback written to the annotation
    crashed after the records were written.
    """
    hints = typing.get_type_hints(collect.collect_and_post)
    for name in ("post", "post_matrix"):
        declared = next(a for a in typing.get_args(hints[name]) if a is not type(None))
        parameters = inspect.signature(declared.__call__).parameters
        assert "sims" in parameters, name
        assert parameters["sims"].kind is inspect.Parameter.KEYWORD_ONLY, name
    source = inspect.getsource(collect)
    assert "type: ignore[call-arg]" not in source


# ------------------------------------------------------- submitted extractions


def _submitted_extraction(tmp_path):
    """A recorded campaign whose additional post was submitted and has not run yet."""
    from tests.tier1_offline.test_additional_post import a_recorded_campaign, extract
    from tests.tier1_offline.test_submitted_additional_post import Scheduler

    workspace, matrix = a_recorded_campaign(tmp_path, values="0.0")
    _, records = extract(workspace, matrix, Scheduler())
    (record,) = records
    assert record.status == "SUBMITTED"
    return workspace, record, workspace.sim_dir(record.sim_id) / record.working_dir


def _run_the_extraction(tmp_path, workspace, record, folder):
    from tests.tier1_offline.test_additional_post import a_stub

    a_stub(tmp_path).run_script(
        workspace.sim_dir(record.sim_id) / record.script_path, working_dir=folder
    )


def _no_sleep(_seconds):
    return None


def test_p0400_extraction_copy_held_open_is_a_note_not_a_failure(tmp_path, monkeypatch):
    """P0400-EXTRACTION-COPY (PFS-2103.005): the EXTRACTED row stands when the copy is held.

    Removing the private copy failed after the EXTRACTED row was written, and
    the OSError appended a FAILED_EXECUTION row over it.
    """
    from pathlib import Path

    workspace, record, folder = _submitted_extraction(tmp_path)
    _run_the_extraction(tmp_path, workspace, record, folder)
    real = Path.unlink

    def held(self, missing_ok=False):
        if self.name.endswith(".reopened.fsm"):
            raise PermissionError("held by another process")
        return real(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", held)
    report = collect.collect_once(workspace, interval=0, sleep=_no_sleep)
    assert len(report.collected) == 1 and not report.failed, report.lines()
    latest = workspace.read_additional()[-1]
    assert latest.status == "EXTRACTED"
    assert "could not be removed" in (latest.note or "")


def test_p0400_extraction_of_a_compacted_simulation_is_expanded_first(tmp_path):
    """P0400-EXTRACTION-COMPACTED (PFS-2103.006): collect expands the simulation, as for a point.

    Read zipped, the original and the private copy were changed or missing,
    and the extraction was failed for good.
    """
    from pyflightstream.workspace import storage as storage_module
    from tests.tier1_offline.test_goal035_storage import _write_recipe

    workspace, record, folder = _submitted_extraction(tmp_path)
    _run_the_extraction(tmp_path, workspace, record, folder)
    _write_recipe(workspace, "m001", '[[compact_sims]]\nsims = "all"\n')
    storage_module.free_space(workspace.root, "m001", apply=True)
    assert not workspace.sim_dir(record.sim_id).exists(), "the fixture compacts the simulation"
    report = collect.collect_once(workspace, interval=0, sleep=_no_sleep)
    assert len(report.collected) == 1 and not report.failed, report.lines()
    assert workspace.read_additional()[-1].status == "EXTRACTED"


def test_p0400_extraction_whose_job_ended_without_outputs_ends_a_watch(tmp_path):
    """P0400-EXTRACTION-JOB-END (PFS-2085.008): the job-end rule fails a dead extraction.

    WAITING forever, it was counted outstanding and a watch never stopped.
    """
    from tests.tier1_offline.test_goal024_profile_log import _write_profile

    workspace, record, folder = _submitted_extraction(tmp_path)
    _write_profile(workspace, '\n[log]\njob_end_files = ["FTS{sim}.o*"]\n')
    (folder / f"FTS{record.sim_id}.o3714205").write_text("job summary\n", encoding="utf-8")
    report = collect.collect_and_post(workspace, watch=True, rounds=3, interval=0, sleep=_no_sleep)
    assert report.outstanding == 0, report.lines()
    latest = workspace.read_additional()[-1]
    assert latest.status == "FAILED_EXECUTION"
    assert f"FTS{record.sim_id}.o3714205" in (latest.error or "")
    assert "fake-23" in (latest.error or "")


def test_p0400_a_grouped_point_missing_its_log_says_why_it_has_no_time(tmp_path):
    """P0400-MISSING-LOG-BASIS (PFS-2103.007): the nulled wall time's basis names FR-413 R2.

    wall_time_s was nulled for a RAN_MISSING_LOG point while the basis still
    said it was measured (or not) from the clock file.
    """
    from tests.tier1_offline.test_p0390_collect import _collect, _rows, _submitted

    workspace = _submitted(tmp_path, "batch", field=True)
    statuses = _collect(workspace)
    assert set(statuses.values()) == {"RAN_MISSING_LOG"}, statuses
    for row in _rows(workspace.root):
        basis = row["submission"]["job"]["wall_time_basis"]
        assert row["wall_time_s"] is None
        assert "solver log is absent" in basis and "clock file" not in basis, basis


def test_p0400_a_watch_names_a_point_refused_without_a_record_once(tmp_path):
    """P0400-WATCH-FAILED-ONCE (PFS-2103.032): one failed outcome per point, the latest.

    A native-log refusal writes no record, so the point stays SUBMITTED; a
    watch kept going by another waiting point refused it again each sweep
    and its outcome piled up in the report.
    """
    import json

    from tests.tier1_offline.test_collect_stage import _submitted_workspace
    from tests.tier1_offline.test_goal024_profile_log import LOG_TABLE, _write_profile

    workspace, _sim = _submitted_workspace(tmp_path, declared=("loads.txt",))
    _write_profile(workspace, LOG_TABLE)
    rows = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    waiting = {**rows[0], "run_id": "camp/sim_9001/AL+020", "point_name": "AL+020"}
    declared = ["loads.txt", "P9001-AL+020_log.txt"]
    waiting["submission"] = {**rows[0]["submission"], "declared_outputs": declared}
    workspace.manifest_path.write_text(json.dumps([rows[0], waiting], indent=2), "utf-8")
    report = collect.collect_and_post(workspace, watch=True, rounds=3, interval=0, sleep=_no_sleep)
    assert [outcome.run_id for outcome in report.failed] == ["camp/sim_9001/AL+000"], [
        outcome.detail for outcome in report.failed
    ]


def test_p0400_collect_refuses_a_bare_string_of_sims(tmp_path):
    """P0400-SIMS-STRING (PFS-2089.009): collect refuses a str, never iterates it."""
    import pytest

    from pyflightstream.workspace import WorkspaceError
    from tests.tier1_offline.test_collect_stage import _submitted_workspace

    workspace, _sim = _submitted_workspace(tmp_path)
    for call in (collect.collect_once, collect.collect_and_post):
        with pytest.raises(WorkspaceError, match=r"sims takes a list of ids"):
            call(workspace, sims="9001", interval=0, sleep=_no_sleep)


def test_p0400_collect_refuses_an_unknown_sim_before_the_grouped_step(tmp_path):
    """P0400-COLLECT-SIMS-FIRST (PFS-2096.005): nothing is moved before --sims is refused.

    The grouped-job step moved a known simulation's points home and wrote
    its records, and only then was the unknown id refused.
    """
    import pytest

    from pyflightstream.workspace import WorkspaceError
    from tests.tier1_offline.test_p0370_s1_matrix_home import grouped_workspace

    workspace = grouped_workspace(tmp_path, mode="batch", collect=False)

    def tree():
        return sorted(
            (p.relative_to(workspace.root).as_posix(), p.stat().st_size)
            for p in workspace.root.rglob("*")
            if p.is_file() and "logs" not in p.relative_to(workspace.root).parts
        )

    before = tree()
    with pytest.raises(WorkspaceError, match="9999"):
        collect.collect_once(workspace, sims=["7001", "9999"], interval=0, sleep=_no_sleep)
    assert tree() == before
