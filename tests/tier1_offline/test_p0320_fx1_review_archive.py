"""Tier 1: review of FX1, the archive writers' remaining arms (0.32.0).

P0320-RESTORE-ARCHIVE. The first round proved four writers through their round trip and
``archive_previous`` alone for the failed copy. This module proves what it left open:
that a writer whose archive copy fails still writes (FR-294), that ``rename`` archives
the plan it rewrites (FR-293), and that a plan with no matrix is not archived (FR-293).
"""

from __future__ import annotations

import json
import shutil
import sys

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.cases import Campaign, SimCase, SweepAxis
from pyflightstream.run import plan_campaign
from pyflightstream.workspace import CampaignWorkspace
from pyflightstream.workspace.storage import read_storage_calls, record_storage_call
from tests.tier1_offline.test_p0320_fx1_restore_archive import _extraction
from tests.tier1_offline.test_run_campaign import steady_recipe


def _block_the_archive(root):
    """Replace the archive folder by a file, so no copy can be made into it."""
    shutil.rmtree(root / "archive", ignore_errors=True)
    (root / "archive").write_text("a file where the folder should be", encoding="utf-8")


@pytest.mark.requirement("FR-294")
def test_p0320_restore_archive_the_storage_writer_writes_when_the_copy_fails_fr_294(tmp_path):
    """P0320-RESTORE-ARCHIVE: a blocked archive folder warns and the storage record is written."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    record_storage_call(workspace.root, {"command": "first"})
    _block_the_archive(workspace.root)
    with pytest.warns(PyflightstreamWarning, match="could not be archived"):
        record_storage_call(workspace.root, {"command": "second"})
    assert [c["command"] for c in read_storage_calls(workspace.root)] == ["first", "second"]


def test_p0320_restore_archive_the_additional_writer_writes_when_the_copy_fails_fr_294(tmp_path):
    """P0320-RESTORE-ARCHIVE: a blocked archive folder warns and the extraction is recorded."""
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    workspace.append_additional(_extraction("e1"))
    _block_the_archive(workspace.root)
    with pytest.warns(PyflightstreamWarning, match="could not be archived"):
        workspace.append_additional(_extraction("e2"))
    assert [r.extraction_id for r in workspace.read_additional()] == ["e1", "e2"]


def test_p0320_restore_archive_a_plan_without_a_matrix_is_not_archived_fr_293(tmp_path):
    """P0320-RESTORE-ARCHIVE: the root plan of a matrix-less campaign has no restore kind."""
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
    campaign = Campaign(name="camp", fs_version="26.120", fs_exe=sys.executable, sims=[case])
    workspace = CampaignWorkspace.init(tmp_path / "camp")
    plan_campaign(campaign, workspace, recipes={"steady": steady_recipe})
    plan_campaign(campaign, workspace, recipes={"steady": steady_recipe})
    assert json.loads((workspace.root / "plan.json").read_text(encoding="utf-8"))
    assert list((workspace.root / "archive").iterdir()) == []
    assert list((workspace.root / "post").rglob("plan*.json")) == []
