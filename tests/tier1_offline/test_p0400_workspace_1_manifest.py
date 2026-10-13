"""P0400-WSMANIFEST: reading the manifest's per-point entries (0.40.0 lane workspace-1).

Each test is the regression of one planning node and fails on the code before its fix.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from pyflightstream.workspace import CampaignWorkspace
from tests.tier1_offline.test_workspace import make_record

pytestmark = pytest.mark.requirement("P0400-WSMANIFEST")


@pytest.mark.parametrize(
    ("entry", "named"),
    [
        ({"tag": "AL+000", "status": "EXPLODED"}, "status 'EXPLODED'"),
        ({"tag": 7, "status": "CONVERGED"}, "tag 7"),
    ],
    ids=["unknown-status", "tag-not-text"],
)
def test_p0400_wsmanifest_an_unreadable_points_ran_entry_is_refused_when_read(
    tmp_path, entry, named
):
    """P0400-WSMANIFEST (PFS-2093.005): the row is unreadable at read, not later in as_points."""
    workspace = CampaignWorkspace(tmp_path)
    workspace.append_record(make_record(points_ran=[{"tag": "AL+000", "status": "CONVERGED"}]))
    rows = json.loads(workspace.manifest_path.read_text(encoding="utf-8"))
    rows[0]["points_ran"] = [entry]
    workspace.manifest_path.write_text(json.dumps(rows), encoding="utf-8")
    with pytest.raises(ValidationError, match=named):
        workspace.read_manifest()


def test_p0400_wsmanifest_a_known_points_ran_entry_still_reads():
    """P0400-WSMANIFEST (PFS-2093.005): the guard refuses nothing a release writes."""
    record = make_record(points_ran=[{"tag": "AL+000", "status": "CONVERGED"}, {"tag": None}])
    assert [point.point_name for point in record.as_points()] == ["AL+000", None]
