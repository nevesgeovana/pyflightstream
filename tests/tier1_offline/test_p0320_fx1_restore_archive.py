"""Tier 1: the writers of four record kinds archive the previous file (0.32.0).

P0320-RESTORE-ARCHIVE. ``restore`` (GEO-066 2.3 item 1) serves ``storage_management.json``,
``post/<matrix>/products.json``, ``plan.json`` and ``additional.json`` too, but their
writers never archived the file they rewrote, so a restore of those kinds had nothing
to bring back but its own copies. Each test writes twice through the real writer and
restores the FIRST content end to end, byte for byte, from what the writer archived.
The oracle is the archive form ``restore`` reads, named in its docstring.
"""
# The evidence line of these requirements cites this module (docs/srs/functional-requirements.md):
# FR-291, FR-292, FR-293, FR-294.

from __future__ import annotations

import json
import sys
import warnings

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import Campaign, SimCase, SweepAxis
from pyflightstream.post.products import write_campaign_products
from pyflightstream.run import plan_campaign
from pyflightstream.run.records import restore
from pyflightstream.workspace import (
    AdditionalRecord,
    CampaignWorkspace,
    RunRecord,
    RunStatus,
)
from pyflightstream.workspace.naming import archive_previous
from pyflightstream.workspace.storage import read_storage_calls, record_storage_call
from tests.tier1_offline.test_run_campaign import steady_recipe


def _extraction(name: str) -> AdditionalRecord:
    return AdditionalRecord(
        extraction_id=name,
        run_id="camp/sim_1/AL+000",
        sim_id="1",
        pproc="p",
        fsm="a.fsm",
        fsm_sha256="0" * 64,
        fs_version_requested="26.124",
        package_version="0.32.0",
        script_path="s.txt",
        script_sha256="1" * 64,
        working_dir="w",
        status="EXTRACTED",
    )


def test_p0320_restore_archive_the_storage_record(tmp_path):
    """P0320-RESTORE-ARCHIVE: a second call archives the file that held the first."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    record_storage_call(workspace.root, {"command": "first"})
    first = (workspace.root / "storage_management.json").read_bytes()
    record_storage_call(workspace.root, {"command": "second"})
    assert len(read_storage_calls(workspace.root)) == 2
    preview = restore(workspace.root, "storage")
    assert preview["source"].startswith("archive/storage_management-")
    restore(workspace.root, "storage", apply=True)
    assert (workspace.root / "storage_management.json").read_bytes() == first
    assert len(read_storage_calls(workspace.root)) == 1


def test_p0320_restore_archive_the_additional_record(tmp_path):
    """P0320-RESTORE-ARCHIVE: a second extraction archives additional.json as it stood."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    workspace.append_additional(_extraction("e1"))
    first = workspace.additional_path.read_bytes()
    workspace.append_additional(_extraction("e2"))
    assert len(workspace.read_additional()) == 2
    restore(workspace.root, "additional", apply=True)
    assert workspace.additional_path.read_bytes() == first
    assert [r.extraction_id for r in workspace.read_additional()] == ["e1"]


def _campaign(tmp_path) -> Campaign:
    geometry = tmp_path / "wing.fsm"
    geometry.write_bytes(b"geometry")
    case = SimCase(
        sim_id="1",
        aircraft="TestWing",
        mach=0.2,
        geometry=str(geometry),
        sweep=SweepAxis(type="alpha", values=[-2.0]),
        recipe="steady",
        outputs=["loads_{point}.txt"],
    )
    return Campaign(
        name="camp", fs_version="26.120", fs_exe=sys.executable, sims=[case], matrix_stem="mx"
    )


def test_p0320_restore_archive_the_plan(tmp_path):
    """P0320-RESTORE-ARCHIVE: planning again archives the plan.json it replaces."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    campaign = _campaign(tmp_path)
    plan_campaign(campaign, workspace, recipes={"steady": steady_recipe})
    plan_file = workspace.plan_dir("mx") / "plan.json"
    first = plan_file.read_bytes()
    plan_file.write_text(first.decode("utf-8").replace('"camp"', '"camp2"', 1), encoding="utf-8")
    changed = plan_file.read_bytes()
    assert changed != first
    plan_campaign(campaign, workspace, recipes={"steady": steady_recipe})
    assert plan_file.read_bytes() == first
    done = restore(workspace.root, "plan", matrix="mx", apply=True)
    assert done["stamp"] and plan_file.read_bytes() == changed


def _post_workspace(tmp_path) -> CampaignWorkspace:
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    record = RunRecord(
        run_id="camp/sim_7010/AL+000",
        sim_id="7010",
        point_name="AL+000",
        fs_version_requested="26.124",
        status=RunStatus.CONVERGED,
        recipe="steady",
        outputs=["p.txt"],
        package_version="0.32.0",
        script_sha256="",
        raw_flag=False,
    )
    sim = workspace.sim_dir(record.sim_id)
    sim.mkdir(parents=True, exist_ok=True)
    (sim / "p.txt").write_text("native export", encoding="utf-8")
    workspace.append_record(record)
    return workspace


def test_p0320_restore_archive_the_products_record_is_archived_not_removed(tmp_path):
    """P0320-RESTORE-ARCHIVE: a rebuild archives products.json before it rewrites it."""
    workspace = _post_workspace(tmp_path)
    write_campaign_products(workspace, overwrite=True)
    manifest = workspace.products_dir(None) / "products.json"
    first = manifest.read_bytes()
    manifest.write_text(json.dumps({"marker": "second", "products": {}}), encoding="utf-8")
    second = manifest.read_bytes()
    write_campaign_products(workspace, overwrite=True, archive=True)
    archived = sorted((workspace.products_dir(None) / "archive").glob("*/products.json"))
    assert [p.read_bytes() for p in archived] == [second], "the archive holds the file replaced"
    assert manifest.read_bytes() != second
    restore(workspace.root, "products", matrix="products", apply=True)
    assert manifest.read_bytes() == second
    assert first  # the first post wrote one


def test_p0320_restore_archive_a_failed_copy_warns_and_never_raises(tmp_path):
    """P0320-RESTORE-ARCHIVE: the archive is a courtesy; the writer goes on."""
    target = tmp_path / "additional.json"
    target.write_text("[]", encoding="utf-8")
    (tmp_path / "archive").write_text("a file where the folder should be", encoding="utf-8")
    with pytest.warns(PyflightstreamWarning, match="could not be archived"):
        assert archive_previous(tmp_path, target) is None
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert archive_previous(tmp_path, tmp_path / "absent.json") is None
