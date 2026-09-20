"""Recorded surface bounds must agree with their request and rotor clock."""

import copy

import pytest

from pyflightstream.post.series import surface_export_metadata
from pyflightstream.workspace import CampaignWorkspace, WorkspaceError
from tests.tier1_offline.test_surface_exports import _record


@pytest.mark.parametrize(
    "stated,bounds,invented",
    [
        pytest.param({"last_iters": 54}, [91, 144], [1, 144], id="iterations"),
        pytest.param(
            {"last_revs": 1.5, "steps_per_revolution": 36.0},
            [91, 144],
            [1, 144],
            id="revolutions",
        ),
        pytest.param({"last_iters": 200}, [1, 144], [2, 144], id="clipped-iterations"),
        pytest.param(
            {"last_revs": 5.0, "steps_per_revolution": 36.0},
            [1, 144],
            [2, 144],
            id="clipped-revolutions",
        ),
        pytest.param(
            {"last_revs": 1.25, "steps_per_revolution": 10.0},
            [133, 144],
            [132, 144],
            id="rounded-revolutions",
        ),
    ],
)
def test_recorded_window_consistency_at_read(tmp_path, monkeypatch, stated, bounds, invented):
    # Inclusive last 54 of 144 steps is 91..144. Counts exceeding 144 clip
    # at step 1; 1.25 turns of 10 steps rounds 12.5 to 12, giving 133..144.
    window = {
        **stated,
        "iterations": bounds,
        "iteration_unit": "time_steps",
        "verification": "UNVERIFIED",
    }
    raw = _record().model_dump()
    raw["surface_time_averaging"] = window
    monkeypatch.setattr(CampaignWorkspace, "read_raw_manifest", lambda self: [raw])
    workspace = CampaignWorkspace(tmp_path)
    snapshot = copy.deepcopy(raw)
    record = workspace.read_manifest()[0]
    assert surface_export_metadata(record) == {"kind": "average", "window": window}
    assert raw == snapshot

    raw["surface_time_averaging"] = {**window, "iterations": invented}
    snapshot = copy.deepcopy(raw)
    with pytest.raises(WorkspaceError) as caught:
        surface_export_metadata(workspace.read_manifest()[0])
    message = str(caught.value)
    assert raw["run_id"] in message
    assert "surface_time_averaging" in message
    assert "iterations" in message
    for field in stated:
        assert field in message
    assert "Restore the recorded window from the original run" in message
    assert raw == snapshot, "an inconsistent recorded window must never be silently corrected"
