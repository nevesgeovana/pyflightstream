"""Tier 1: managed campaign workspace and manifest."""

import hashlib
import json
import zipfile

import pytest

import pyflightstream
from pyflightstream.files import CampaignWorkspace, RunRecord, RunStatus, WorkspaceError
from pyflightstream.script import Script


def make_record(run_id="camp/sim_9001/a+02.0", sim_id="9001", **overrides):
    body = dict(
        run_id=run_id,
        sim_id=sim_id,
        point={"alpha": 2.0},
        fs_version_requested="26.120",
        package_version=pyflightstream.__version__,
        script_sha256="0" * 64,
        raw_flag=False,
        status=RunStatus.CONVERGED,
    )
    body.update(overrides)
    return RunRecord(**body)


def test_create_sim_builds_the_managed_subfolders(tmp_path):
    workspace = CampaignWorkspace(tmp_path)
    sim = workspace.create_sim("9001")
    assert sim == tmp_path / "sims" / "sim_9001"
    for name in ("inputs", "scripts", "raw", "parsed"):
        assert (sim / name).is_dir()


def test_sim_id_must_be_a_portable_name(tmp_path):
    workspace = CampaignWorkspace(tmp_path)
    with pytest.raises(WorkspaceError, match="letters, digits"):
        workspace.sim_dir("case 01/alpha")


def test_stage_inputs_copies_and_hashes(tmp_path):
    source = tmp_path / "wing.fsm"
    source.write_bytes(b"geometry-bytes")
    workspace = CampaignWorkspace(tmp_path / "camp")
    hashes = workspace.stage_inputs("9001", [source])
    staged = tmp_path / "camp" / "sims" / "sim_9001" / "inputs" / "wing.fsm"
    assert staged.read_bytes() == b"geometry-bytes"
    assert hashes == {"wing.fsm": hashlib.sha256(b"geometry-bytes").hexdigest()}


def test_staging_a_missing_file_is_refused(tmp_path):
    workspace = CampaignWorkspace(tmp_path)
    with pytest.raises(WorkspaceError, match="does not exist"):
        workspace.stage_inputs("9001", [tmp_path / "absent.fsm"])


def test_write_script_returns_path_and_hash(tmp_path):
    workspace = CampaignWorkspace(tmp_path)
    path, digest = workspace.write_script("9001", "point.txt", "START_SOLVER\n")
    assert path.read_text(encoding="utf-8") == "START_SOLVER\n"
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()


def test_collect_outputs_moves_declared_files_into_raw(tmp_path):
    produced = tmp_path / "loads.txt"
    produced.write_text("data", encoding="utf-8")
    workspace = CampaignWorkspace(tmp_path / "camp")
    collected = workspace.collect_outputs("9001", [produced])
    assert collected == ["raw/loads.txt"]
    assert not produced.exists()
    assert (tmp_path / "camp" / "sims" / "sim_9001" / "raw" / "loads.txt").is_file()


def test_collect_refuses_missing_declared_outputs(tmp_path):
    workspace = CampaignWorkspace(tmp_path)
    with pytest.raises(WorkspaceError, match="FAILED_INCOMPLETE_OUTPUT"):
        workspace.collect_outputs("9001", [tmp_path / "never_written.txt"])


def test_manifest_round_trip_and_unique_run_id(tmp_path):
    workspace = CampaignWorkspace(tmp_path)
    workspace.append_record(make_record())
    workspace.append_record(make_record(run_id="camp/sim_9001/a+04.0"))
    records = workspace.read_manifest()
    assert [record.run_id for record in records] == [
        "camp/sim_9001/a+02.0",
        "camp/sim_9001/a+04.0",
    ]
    with pytest.raises(WorkspaceError, match="already in the manifest"):
        workspace.append_record(make_record())
    assert not workspace.manifest_path.with_suffix(".json.tmp").exists()


def test_manifest_is_valid_json_on_disk(tmp_path):
    workspace = CampaignWorkspace(tmp_path)
    workspace.append_record(make_record(status=RunStatus.FAILED_DIVERGED, error="diverged"))
    payload = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    assert payload[0]["status"] == "FAILED_DIVERGED"
    assert payload[0]["error"] == "diverged"


def test_archive_and_clean_refuse_without_manifest_record(tmp_path):
    workspace = CampaignWorkspace(tmp_path)
    workspace.create_sim("9001")
    with pytest.raises(WorkspaceError, match="no manifest"):
        workspace.archive_sim("9001")
    workspace.append_record(make_record(sim_id="9002", run_id="camp/sim_9002/a"))
    with pytest.raises(WorkspaceError, match="no record of"):
        workspace.clean_sim("9001")


def test_archive_zips_the_recorded_sim_and_removes_the_folder(tmp_path):
    workspace = CampaignWorkspace(tmp_path)
    workspace.write_script("9001", "point.txt", "START_SOLVER\n")
    workspace.append_record(make_record())
    bundle = workspace.archive_sim("9001")
    assert bundle == tmp_path / "archive" / "sim_9001.zip"
    with zipfile.ZipFile(bundle) as archive:
        assert "scripts/point.txt" in archive.namelist()
    assert not (tmp_path / "sims" / "sim_9001").exists()


def test_clean_removes_the_recorded_sim(tmp_path):
    workspace = CampaignWorkspace(tmp_path)
    workspace.create_sim("9001")
    workspace.append_record(make_record())
    workspace.clean_sim("9001")
    assert not (tmp_path / "sims" / "sim_9001").exists()


def test_builder_to_manifest_flow_records_the_raw_flag(tmp_path):
    script = Script(version="26.12")
    script.emit("START_SOLVER")
    script.raw("SOME_UNKNOWN_COMMAND 1")
    workspace = CampaignWorkspace(tmp_path)
    _, digest = workspace.write_script("9001", "point.txt", script.render())
    workspace.append_record(
        make_record(script_sha256=digest, raw_flag=script.raw_flag, outputs=["raw/loads.txt"])
    )
    record = workspace.read_manifest()[0]
    assert record.raw_flag is True
    assert record.script_sha256 == digest
