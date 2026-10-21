"""N2/N3: append a run, resolve its definitions, and refuse unmigrated files."""

import json
from contextlib import contextmanager

import pytest
from pydantic import ValidationError

from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus, WorkspaceError


def _record(run_id="run-1", **changes):
    values = {
        "run_id": run_id,
        "sim_id": "1",
        "fs_version_requested": "26.124",
        "package_version": "0.41.0",
        "script_sha256": "a" * 64,
        "raw_flag": False,
        "status": RunStatus.CONVERGED,
        "solver_setup": {"fs_version": "26.124", "flags": {}},
        "frame_motions": {},
        "inventory": ["body"],
    }
    values.update(changes)
    return RunRecord(**values)


def _envelope(ws):
    value = json.loads(ws.manifest_path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), "Manifest must be a schema-versioned envelope"
    assert value["schema_version"] == 4
    return value


def test_p0430_rb2_supersede_refuses_unreadable_history(tmp_path):
    ws = CampaignWorkspace(tmp_path)
    assert ws.supersede_records(["run-1"]) is None
    ws.manifest_path.mkdir()
    with pytest.raises(WorkspaceError, match="cannot read run records"):
        ws.supersede_records(["run-1"])


@pytest.mark.parametrize("damage", ["geometry", "run_id", "status", "deletion"])
def test_p0430_w007_decoded_headers_cannot_be_bypassed(damage):
    """A digest-valid definition or omission must not invalidate a run header."""
    import hashlib

    from pyflightstream.workspace.record_document import decode_document, encode_rows

    doc = encode_rows([_record().model_dump(mode="json")])
    run = doc["runs"][0]
    if damage == "geometry":
        geometry = {"run_id": "forged", "status": "unknown"}
        key = hashlib.sha256(
            json.dumps(geometry, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        doc["geometries"] = {key: geometry}
        run["geometry_id"] = key
    elif damage == "deletion":
        doc["runs"] = [{"deletion": None}]
    else:
        run.setdefault("unrecorded_fields", []).append([damage])
    with pytest.raises(WorkspaceError):
        decode_document(doc)


@pytest.mark.parametrize("deletion", [None, [], "gone", {}, {"deleted_sim": None}])
def test_p0430_w007_invalid_deletion_refused(deletion):
    from pyflightstream.workspace.record_document import decode_document, encode_rows

    doc = encode_rows([])
    doc["runs"] = [{"deletion": deletion}]
    with pytest.raises(WorkspaceError):
        decode_document(doc)


def test_p0430_w007_deletion_metadata_preserved():
    from pyflightstream.workspace.record_document import decode_document, encode_rows

    row = {"deleted_sim": "7", "deleted_run_ids": ["run-7"], "reason": "cleanup"}
    assert decode_document(encode_rows([row])) == [row]


def test_p0430_w007_optional_additions_omit_only_unrecorded_values():
    keys = (
        "probe_field_layout",
        "surface_probe_layout",
        "frame_motions",
        "custom_field_coverage",
        "freestream_units",
    )
    assert not set(keys) & _record(frame_motions=None).model_dump(mode="json").keys()
    values = dict(zip(keys, [[], [], {}, {}, "METER"], strict=True))
    dumped = _record(**values).model_dump(mode="json")
    assert {key: dumped[key] for key in keys} == values


@pytest.mark.parametrize("indices", [(2,), (2, 10)])
@pytest.mark.parametrize("indexed", [False, True])
def test_p0430_w007_integer_frame_keys_survive_json(indexed, indices):
    """Two frame keys must keep one digest and absent indices across disk storage."""
    from pyflightstream.workspace.record_document import decode_document, encode_rows

    frames = {key: {"motion": "fixed"} for key in indices}
    if indexed:
        for key, frame in frames.items():
            frame["frame_index"] = key
    row = {"run_id": "run", "sim_id": "1", "status": "CONVERGED", "frame_motions": frames}
    expected = json.loads(json.dumps(row))
    doc = encode_rows([row])
    try:
        restored = decode_document(json.loads(json.dumps(doc)))
    except WorkspaceError as error:
        pytest.fail(f"encoder output cannot be decoded: {error}")
    assert restored == [expected]
    assert list(row["frame_motions"]) == list(indices)


def test_p0430_w007_non_file_history_is_refused(tmp_path):
    from pyflightstream.workspace.record_document import read_rows

    path = tmp_path / "runs.json"
    assert read_rows(path) == []
    path.mkdir()
    with pytest.raises(WorkspaceError):
        read_rows(path)


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), -1.0])
def test_p0430_w007_lock_refuses_invalid_timeout(tmp_path, timeout):
    from pyflightstream.workspace.manifest import manifest_lock

    with pytest.raises(WorkspaceError, match="timeout_s"):
        with manifest_lock(
            tmp_path / "runs.json",
            root=tmp_path,
            timeout_s=timeout,
            renew_s=5,
            stale_s=300,
            poll_s=0.001,
        ):
            pass


def test_p0410_rec_shared_definitions(tmp_path):
    ws = CampaignWorkspace(tmp_path)
    ws.append_record(_record())
    original = _envelope(ws)
    ws.append_record(_record("run-2"))
    shared = _envelope(ws)
    assert {"id", "point", "build", "status", "started_at", "finished_at", "run_folder"} <= shared[
        "runs"
    ][0].keys()
    for registry, reference in (
        ("solver_setups", "solver_setup_id"),
        ("frames", "frames_id"),
        ("geometries", "geometry_id"),
    ):
        assert len(shared[registry]) == 1
        assert shared["runs"][0][reference] == shared["runs"][1][reference]
    ws.append_record(_record("run-3", solver_setup={"fs_version": "26.125", "flags": {}}))
    changed = _envelope(ws)
    assert len(changed["solver_setups"]) == 2
    old_id = original["runs"][0]["solver_setup_id"]
    assert changed["solver_setups"][old_id] == original["solver_setups"][old_id]


def test_p0410_rec_resolved_values(tmp_path):
    ws = CampaignWorkspace(tmp_path)
    expected = _record(
        fs_version_reported="26.125",
        velocity_requested_m_s=20,
        walltime_s=100,
        wall_time_s=90,
        solver_run_time_s=80,
        started_at="2026-10-14T10:01:02+00:00",
        finished_at="2026-10-14T10:03:04+00:00",
    )
    ws.append_record(expected)
    _envelope(ws)
    assert ws.read_manifest()[0].model_dump() == expected.model_dump()


def test_p0410_rec_artifact_order(tmp_path):
    ws = CampaignWorkspace(tmp_path)
    first, second = "sims/sim_1/loads.csv", "sims/sim_1/solver.log"
    ws.append_record(
        _record(
            outputs=[first, second],
            outputs_sha256={first: "b" * 64},
            points_ran=[{"outputs": [second, first]}],
        )
    )
    run = _envelope(ws)["runs"][0]
    assert run["artifacts"] == [{"path": first, "sha256": "b" * 64}, {"path": second}]
    assert "outputs" not in run["details"]
    assert "outputs_sha256" not in run["details"]
    assert run["details"]["points_ran"][0]["artifact_indices"] == [1, 0]
    restored = ws.read_manifest()[0]
    assert restored.outputs == [first, second]
    assert restored.outputs_sha256 == {first: "b" * 64}
    assert restored.points_ran[0]["outputs"] == [second, first]


def test_p0410_rec_old_array_refused(tmp_path):
    ws = CampaignWorkspace(tmp_path)
    ws.manifest_path.write_text("[]", encoding="utf-8")
    with pytest.raises(WorkspaceError) as caught:
        ws.read_manifest()
    assert "schema_version" in str(caught.value)
    assert "pyfs-workspace migrate" in str(caught.value)


@pytest.mark.parametrize(
    "status", [RunStatus.CONVERGED, RunStatus.RAN_MISSING_LOG, RunStatus.FAILED_EXECUTION]
)
def test_p0410_rec_status_one_write(tmp_path, monkeypatch, status):
    ws = CampaignWorkspace(tmp_path)
    ws.append_record(_record(status=RunStatus.SUBMITTED))
    calls = []
    replace = ws._replace_manifest

    def counted(raw):
        calls.append(1)
        return replace(raw)

    monkeypatch.setattr(ws, "_replace_manifest", counted)
    ws.complete_submitted_record(_record(status=status))
    assert len(calls) == 1
    assert _envelope(ws)["runs"][0]["status"] == status
    assert ws.read_manifest()[0].status == status


@pytest.mark.parametrize("damage", ["digest", "reference", "artifact", "duplicate", "status"])
def test_p0410_rec_corrupt_references_are_refused(tmp_path, damage):
    ws = CampaignWorkspace(tmp_path)
    ws.append_record(_record(outputs=["loads.csv"]))
    doc = _envelope(ws)
    run = doc["runs"][0]
    if damage == "digest":
        doc["solver_setups"][run["solver_setup_id"]]["fs_version"] = "other"
    elif damage == "reference":
        run["frames_id"] = "missing"
    elif damage == "artifact":
        run["artifact_indices"] = [-1]
    elif damage == "duplicate":
        doc["runs"].append(run)
    else:
        run["status"] = "unknown"
    ws.manifest_path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(WorkspaceError, match="invalid schema_version=4"):
        ws.read_manifest()


def test_p0410_rec_distinct_invocations_and_unrecorded_fields_survive():
    from pyflightstream.workspace.record_document import decode_document, encode_rows

    row = {
        "run_id": "run",
        "sim_id": "1",
        "status": "CONVERGED",
        "argv": ["requested"],
        "executor": {"class_name": "remote", "argv": ["observed"]},
        "outputs": ["b", "a", "b"],
        "outputs_sha256": {"c": "hash"},
        "solver_setup": {"flags": {"X": {"value": 3}}},
        "frame_motions": {"1": {"motion": "fixed"}},
    }
    assert decode_document(encode_rows([row])) == [row]


def test_p0410_rec_absent_executor_arguments_stay_absent():
    from pyflightstream.workspace.record_document import decode_document, encode_rows

    row = {"run_id": "run", "sim_id": "1", "status": "CONVERGED", "executor": {}}
    assert decode_document(encode_rows([row])) == [row]


@pytest.mark.parametrize("transition", ["failed", "converged"])
def test_p0410_rec_mark_transition_replaces_manifest_once(tmp_path, monkeypatch, transition):
    from pyflightstream.run._mark_converged import mark_converged
    from pyflightstream.run.records import mark_failed

    ws = CampaignWorkspace(tmp_path)
    initial = RunStatus.SUBMITTED if transition == "failed" else RunStatus.RAN_MISSING_LOG
    ws.sim_dir("1").mkdir(parents=True, exist_ok=True)
    (ws.sim_dir("1") / "loads.txt").write_text("reviewed loads", encoding="utf-8")
    ws.append_record(_record(status=initial, outputs=["loads.txt"]))
    _envelope(ws)
    calls = []
    original = CampaignWorkspace._replace_manifest

    def counted(self, raw):
        calls.append(self.manifest_path)
        return original(self, raw)

    monkeypatch.setattr(CampaignWorkspace, "_replace_manifest", counted)
    if transition == "failed":
        mark_failed(tmp_path, ["1"], reason="Reviewed failure", apply=True)
    else:
        mark_converged(tmp_path, ["1"], reason="Reviewed convergence", apply=True)
    assert calls == [ws.manifest_path]
    expected = RunStatus.FAILED_MARKED if transition == "failed" else RunStatus.CONVERGED
    assert _envelope(ws)["runs"][0]["status"] == expected
    assert ws.read_manifest()[0].status == expected


def test_p0410_rec_show_resolves_historical_definitions(tmp_path, capsys):
    from pyflightstream.run.cli import main

    ws = CampaignWorkspace(tmp_path)
    record = _record("sample/sim_1/a", fs_build="1234")
    ws.append_record(record)
    assert main(["show", record.run_id, "--workspace", str(tmp_path), "--json"]) == 0
    document = json.loads(capsys.readouterr().out)["rows"][0]
    assert "record" in document
    assert document["record"]["solver_setup"] == record.solver_setup
    assert document["record"]["inventory"] == record.inventory
    assert document["record"]["fs_build"] == "1234"


def test_p0430_supersede_archives_the_snapshot_under_lease(tmp_path, monkeypatch):
    """A collector completes a submitted run just before supersede takes its lease."""
    ws = CampaignWorkspace(tmp_path)
    ws.append_record(_record(status=RunStatus.SUBMITTED))
    original = ws._manifest_lock

    @contextmanager
    def completion_before_acquisition(manifest=None):
        with original(manifest):
            ws._replace_manifest([_record(status=RunStatus.CONVERGED).model_dump(mode="json")])
            yield

    monkeypatch.setattr(ws, "_manifest_lock", completion_before_acquisition)
    archive = ws.supersede_records(["run-1"])
    assert archive is not None
    from pyflightstream.workspace.record_document import read_rows

    assert read_rows(archive)[0]["status"] == "CONVERGED"
    assert ws.read_raw_manifest() == []


@pytest.mark.parametrize("point", [1, "bad", [], [1], [["alpha", 2]], False])
def test_p0430_non_mapping_job_point_is_refused_at_validation(point):
    """RunRecord must refuse an invalid point before any as_points consumer reads it."""
    error = None
    try:
        _record(points_ran=[{"tag": "a", "point": point}])
    except ValidationError as caught:
        error = caught
    assert error is not None, "non-mapping point accepted by RunRecord"
    assert "points_ran" in str(error)
    assert "entry 0" in str(error)


@pytest.mark.parametrize("point", [None, {}, {"alpha": 2}])
def test_p0430_mapping_and_unknown_job_points_still_expand(point):
    record = _record(points_ran=[{"tag": "a", "point": point}])
    assert record.as_points()[0].point == (point or {})


@pytest.mark.parametrize("expired", [False, True])
def test_p0430_oversized_pid_uses_lease_age(tmp_path, monkeypatch, expired):
    """An overflowing POSIX PID probe must neither crash nor prove owner death."""
    import os
    import socket
    import sys
    from types import SimpleNamespace

    from pyflightstream.workspace.manifest import manifest_lock

    lock = tmp_path / "runs.json.lock"
    lock.write_text(
        json.dumps({"pid": 1 << 128, "host": socket.gethostname(), "token": "old"}),
        encoding="utf-8",
    )
    if expired:
        os.utime(lock, (1, 1))

    def overflowing_probe(pid, signal):
        assert pid == 1 << 128
        assert signal == 0
        raise OverflowError("Python int too large to convert to C long")

    # Exercise the POSIX PID failure on every host; arbitration is outside this unit test.
    acquired = False
    error = None
    with monkeypatch.context() as platform:
        platform.setattr(sys, "platform", "linux")
        platform.setitem(
            sys.modules,
            "fcntl",
            SimpleNamespace(flock=lambda *args: None, LOCK_EX=1, LOCK_NB=2, LOCK_UN=8),
        )
        platform.setattr(os, "kill", overflowing_probe)
        try:
            with manifest_lock(
                tmp_path / "runs.json",
                root=tmp_path,
                timeout_s=0.01,
                renew_s=60,
                stale_s=300,
                poll_s=0.001,
            ):
                acquired = True
        except (OverflowError, WorkspaceError) as caught:
            error = caught
    assert not isinstance(error, OverflowError), "PID overflow escaped lease recovery"
    assert acquired is expired
    if not expired:
        assert isinstance(error, WorkspaceError)
        assert json.loads(lock.read_text(encoding="utf-8"))["token"] == "old"
