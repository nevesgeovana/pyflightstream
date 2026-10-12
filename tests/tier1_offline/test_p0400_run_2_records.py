"""Tier 1, 0.40.0 lane run-2: the records commands, the manifests they read and archive.

Every fixture is synthetic.
"""

from __future__ import annotations

import pytest

from pyflightstream.run import records
from pyflightstream.workspace import CampaignWorkspace


def test_p0400_from_sims_name_is_refused_in_any_case(tmp_path):
    """P0400-FROM-SIMS-FOLD (PFS-2094.033): ``--runs Sims.json`` is refused like ``sims.json``.

    On a case-insensitive file system post/<matrix>@Sims/ is the folder of the
    from-sims post.
    """
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    (workspace.root / "Sims.json").write_text("[]", encoding="utf-8")
    with pytest.raises(records.RunsManifestError, match="--from-sims"):
        records.manifest_workspace(workspace.root, "Sims.json")


def test_p0400_mark_failed_numbers_a_second_archive_within_one_stamp(tmp_path, monkeypatch):
    """P0400-ARCHIVE-FREE (PFS-2096.006): two marks in one second keep both copies of runs.json.

    The hand-built name overwrote the first copy; free_root_archive numbers
    the second ``.2``, which restore finds.
    """
    from tests.tier1_offline.test_mark_failed import _workspace

    workspace = _workspace(tmp_path)
    monkeypatch.setattr(records, "_now_stamp", lambda: "20261012-120000")
    first = workspace.manifest_path.read_bytes()
    records.mark_failed(workspace.root, ["2006"], reason="first", apply=True)
    second = workspace.manifest_path.read_bytes()
    records.mark_failed(workspace.root, ["2008"], reason="second", apply=True)
    archive = workspace.root / "archive"
    assert (archive / "runs-20261012-120000.json").read_bytes() == first
    assert (archive / "runs-20261012-120000.2.json").read_bytes() == second


def test_p0400_mark_failed_refuses_a_named_point_no_record_holds(tmp_path):
    """P0400-MARK-UNKNOWN-POINT (PFS-2094.019): a point planned but not run is refused by name.

    The alias resolves through plan.json to a point with no record; the
    mark matched nothing and exited 0 in silence.
    """
    from tests.tier1_offline.test_mark_failed import _workspace

    workspace = _workspace(tmp_path)
    before = workspace.manifest_path.read_bytes()
    refusal = r"no record of point AL\+010 in simulation 2006"
    with pytest.raises(records.RunsManifestError, match=refusal):
        records.mark_failed(workspace.root, [], points={"2006": ["AL+010"]}, apply=True)
    assert workspace.manifest_path.read_bytes() == before


def _job_workspace(tmp_path):
    """A workspace holding one steady job of three CONVERGED points, beside other records."""
    from pyflightstream.workspace import RunStatus
    from tests.tier1_offline.test_mark_failed import _record, _workspace

    workspace = _workspace(tmp_path)
    job = _record("5001", "camp/sim_5001/sweep", RunStatus.CONVERGED)
    ran = [{"tag": tag, "status": "CONVERGED"} for tag in ("AL+000", "AL+005", "AL+010")]
    workspace.append_record(job.model_copy(update={"points_ran": ran}))
    return workspace


def _points_of(workspace, sim):
    return {
        point.run_id: point.status.value
        for record in workspace.read_manifest()
        if record.sim_id == sim
        for point in record.as_points()
    }


def test_p0400_mark_failed_marks_every_point_of_a_job_marked_whole(tmp_path):
    """P0400-MARK-JOB (PFS-2103.010): each points_ran entry of a job marked whole is FAILED_MARKED.

    The post reads each point's status from its entry (as_points), so a job
    marked at its top alone kept every point CONVERGED and admitted.
    """
    from pyflightstream.post._products_campaign import _ADMITTED_WHEN_CHECKING
    from pyflightstream.workspace import RunStatus

    workspace = _job_workspace(tmp_path)
    entry = records.mark_failed(workspace.root, ["5001"], reason="wrong mesh", apply=True)
    points = _points_of(workspace, "5001")
    assert set(points.values()) == {"FAILED_MARKED"}, points
    assert RunStatus.FAILED_MARKED not in _ADMITTED_WHEN_CHECKING
    assert sorted(item["run_id"] for item in entry["marked"]) == sorted(points)
    (row,) = [r for r in workspace.read_raw_manifest() if r.get("sim_id") == "5001"]
    assert row["status"] == "FAILED_MARKED" and row["marked"]["from"] == "CONVERGED"
    assert all(e["marked"]["reason"] == "wrong mesh" for e in row["points_ran"])


def test_p0400_mark_failed_marks_the_one_point_of_a_job_an_alias_names(tmp_path):
    """P0400-MARK-JOB (PFS-2103.009): an alias of one job point marks that entry alone.

    row_selected takes the whole job row when any of its points matches, so
    every point of the job was marked FAILED_MARKED.
    """
    workspace = _job_workspace(tmp_path)
    records.mark_failed(workspace.root, [], points={"5001": ["AL+005"]}, apply=True)
    assert _points_of(workspace, "5001") == {
        "camp/sim_5001/AL+000": "CONVERGED",
        "camp/sim_5001/AL+005": "FAILED_MARKED",
        "camp/sim_5001/AL+010": "CONVERGED",
    }
    (row,) = [r for r in workspace.read_raw_manifest() if r.get("sim_id") == "5001"]
    assert "marked" not in row  # the person judged one point, not the job


@pytest.mark.parametrize("sims", ["2006,2007", "2006"])
def test_p0400_mark_failed_refuses_a_bare_string_of_ids(tmp_path, sims):
    """P0400-SIMS-STRING (PFS-2089.009): a str is refused in Python terms, never iterated.

    ``"2006,2007"`` read character by character was refused as simulations
    2, 0, 6, and the message told a Python caller to write the ids comma separated.
    """
    from tests.tier1_offline.test_mark_failed import _workspace

    workspace = _workspace(tmp_path)
    with pytest.raises(records.RunsManifestError, match=r"sims takes a list of ids, e\.g\. \["):
        records.mark_failed(workspace.root, sims)
