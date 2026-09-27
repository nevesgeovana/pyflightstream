# GEOVERSE_HEADER
# file_version: 1.0.1
# last_modified_at: 2026-09-27T20:59:34.949Z
# last_modified_by: OpenAI / Codex / GPT-6 / implementation-agent
# dependencies: [pyflightstream._progress, pyflightstream.results, pyflightstream.workspace]
# authority: pyflightstream
# status: active
# confidentiality: public
# change_summary: Bind existing behavioral checks to explicit release obligations.
# revision_source: git
"""Batch activity observes real operations without changing their products."""

import json

import pytest

from pyflightstream._progress import workspace_activity
from pyflightstream.results import translate_surface_exports
from pyflightstream.workspace import CampaignWorkspace
from pyflightstream.workspace.naming import PointName
from tests.tier1_offline.test_g45_tecplot_from_vtk import MRP, _solver_vtk


def _events(workspace, stage):
    return [
        event
        for line in (workspace.root / "logs/activity.log.jsonl").read_text().splitlines()
        if (event := json.loads(line))["stage"] == stage
    ]


def test_export_batch_logs_point_and_elapsed_without_rewriting_bytes(tmp_path):
    # GOAL033:logging:checks:export
    workspace = CampaignWorkspace(tmp_path / "campaign")
    source = tmp_path / "source.txt"
    source.write_bytes(b"exact exported bytes\n")
    result = workspace.collect_outputs("9001", [source], datapoint=PointName("AL+000"))
    assert (workspace.sim_dir("9001") / result[0]).read_bytes() == b"exact exported bytes\n"
    events = _events(workspace, "export")
    assert [e["event"] for e in events] == ["started", "finished"]
    assert events[-1]["duration_s"] >= 0
    assert events[-1]["sim_id"] == "9001" and events[-1]["datapoint"] == "AL+000"


def test_export_batch_failure_retains_actionable_missing_path(tmp_path):
    # GOAL033:logging:checks:case_point_stage
    workspace = CampaignWorkspace(tmp_path / "campaign")
    source = tmp_path / "missing.txt"
    with pytest.raises(Exception, match="missing.txt"):
        workspace.collect_outputs("9001", [source], datapoint=PointName("AL+000"))
    events = _events(workspace, "export")
    assert events[-1]["event"] == "failed"
    assert "missing.txt" in events[-1]["message"]
    assert events[-1]["sim_id"] == "9001"
    assert events[-1]["datapoint"] == "AL+000"
    assert events[-1]["stage"] == "export"
    assert events[-1]["duration_s"] >= 0


def test_translation_batch_records_problems_and_preserves_existing_products(tmp_path):
    # GOAL033:logging:checks:translation
    workspace = CampaignWorkspace(tmp_path / "campaign")
    work = workspace.root / "point"
    work.mkdir(parents=True)
    _solver_vtk(work / "surface.vtk", MRP)
    before = (work / "surface.vtk").read_bytes()

    @workspace_activity("post")
    def translate(workspace):
        return translate_surface_exports(
            work, [{"vtk": "surface.vtk", "dat": "surface.dat", "frame": MRP}]
        )

    assert translate(workspace)[0]["written"] == ["surface.dat"]
    product = (work / "surface.dat").read_bytes()
    assert translate(workspace)[0]["written"] == ["surface.dat"]
    assert (work / "surface.dat").read_bytes() == product
    assert (work / "surface.vtk").read_bytes() == before
    events = _events(workspace, "translation")
    assert len(events) == 4
    assert events[-1]["event"] == "finished" and events[-1]["duration_s"] >= 0
    assert events[-1]["point_folder"] == str(work)
    (work / "surface.vtk").unlink()
    assert translate(workspace)[0]["problems"]
    failure = _events(workspace, "translation")[-1]
    assert failure["event"] == "failed" and "surface.vtk" in failure["problems"][0]
    assert (work / "surface.dat").read_bytes() == product
