"""Adversarial regressions for the run-1 release lane, without a solver."""

from __future__ import annotations

import json

import pytest

from pyflightstream.cases import CampaignConfigError
from pyflightstream.run import ExecutorConfigurationError, SubmittingExecutor, cli
from pyflightstream.run.records import mark_converged
from pyflightstream.workspace import CampaignWorkspace
from pyflightstream.workspace.inputs import read_hpc_profile
from pyflightstream.workspace.naming import RunsManifestError
from tests.tier1_offline import test_p0350_run_id_alias as alias_tests
from tests.tier1_offline.test_p0370_s1_mark_converged import REASON
from tests.tier1_offline.test_p0370_s1_mark_converged import workspace as workspace  # noqa: F401
from tests.tier1_offline.test_p0400_run_1_executors import _profile


@pytest.mark.parametrize("point", ["0", "99"])
def test_p0400_review_unknown_numeric_point_lists_choices(tmp_path, capsys, point):
    """P0400-REVIEW-SHOW: invalid numeric selections get the same useful refusal."""
    camp = CampaignWorkspace.init(tmp_path / "camp")
    for tag in ("AL+000", "AL+020"):
        camp.append_record(alias_tests._record("2006", f"warm/sim_2006/{tag}"))
    assert cli.main(["show", "2006", "--point", point, "--workspace", str(camp.root)]) == 1
    said = capsys.readouterr().err
    assert f"{point!r}" in said and "'2006'" in said
    assert "AL+000 (2006_1)" in said and "AL+020 (2006_2)" in said


def test_p0400_review_nested_submit_fields_are_checked(tmp_path):
    """P0400-REVIEW-SUBMIT: a nested unknown is refused before any row runs."""
    path = _profile(tmp_path, json.dumps(["esub", "{ncpus:{queue}}"]))
    profile = read_hpc_profile(path)
    with pytest.raises(ExecutorConfigurationError, match="submit"):
        SubmittingExecutor(profile, values={"fs_build": "26.120"})


def test_p0400_review_submit_attribute_error_is_a_point_refusal(tmp_path):
    """P0400-REVIEW-SUBMIT: a malformed attribute cannot escape the point handler."""
    path = _profile(tmp_path, json.dumps(["esub", "{ncpus.missing}"]))
    executor = SubmittingExecutor(
        read_hpc_profile(path), values={"fs_build": "26.120", "sim": "1", "ncpus": 8}, submit=False
    )
    script = tmp_path / "point.txt"
    script.write_text("CLOSE_FLIGHTSTREAM", encoding="utf-8")
    with pytest.raises(CampaignConfigError, match="submit"):
        executor.run_script(script, working_dir=tmp_path)


@pytest.mark.parametrize("broken", ["points_shape", "point_shape", "point_status", "row_status"])
def test_p0400_review_invalid_manifest_is_refused_before_writes(workspace, broken):  # noqa: F811
    """P0400-REVIEW-MANIFEST: invalid shapes or statuses never become a person's verdict."""
    rows = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    row = next(row for row in rows if row["sim_id"] == "7002")
    if broken == "points_shape":
        row["points_ran"] = "invalid"
    elif broken == "point_shape":
        row["points_ran"] = [None]
    elif broken == "point_status":
        row["points_ran"][0]["status"] = "HALF_DONE"
    else:
        row["status"] = "HALF_DONE"
    workspace.manifest_path.write_text(json.dumps(rows), encoding="utf-8")
    before = workspace.manifest_path.read_bytes()
    archives = sorted((workspace.root / "archive").glob("runs-*.json"))
    with pytest.raises(RunsManifestError, match=row["run_id"]):
        mark_converged(workspace.root, ["7002"], reason=REASON, apply=True)
    assert workspace.manifest_path.read_bytes() == before
    assert sorted((workspace.root / "archive").glob("runs-*.json")) == archives
