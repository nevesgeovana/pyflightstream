"""Read malformed recorded windows and continue a stopped surface average."""

import pytest
from pydantic import ValidationError

from pyflightstream.cases import CampaignConfigError
from pyflightstream.cases.windows import surface_averaging_window
from pyflightstream.post.products import _surface_export_skip
from pyflightstream.post.series import surface_export_metadata
from pyflightstream.results import frozen_time_steps
from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus, WorkspaceError
from tests.tier1_offline.test_b01_frozen_solve import _log
from tests.tier1_offline.test_goal021_inputs_absolute import _workspace
from tests.tier1_offline.test_goal021_swept_row import _restart_row, _run, _stopped, _submitting
from tests.tier1_offline.test_surface_exports import WINDOW, _record


def test_iteration_window_does_not_require_rotor_clock():
    try:
        window = surface_averaging_window(last_step=144, last_iters=54)
    except TypeError as error:
        pytest.fail(f"iteration window requires an irrelevant rotor clock: {error}")
    assert window["iterations"] == [91, 144]
    with pytest.raises(CampaignConfigError, match="rotor clock"):
        surface_averaging_window(last_step=144, last_revs=1.5)


@pytest.mark.parametrize(
    "window,field",
    [
        ({}, "iterations"),
        ({**WINDOW, "iterations": [91]}, "iterations"),
        ({**WINDOW, "iterations": [144, 91]}, "iterations"),
        ({**WINDOW, "iterations": [0, 144]}, "iterations"),
        ({**WINDOW, "iterations": [1.5, 144]}, "iterations"),
        ({**WINDOW, "steps_per_revolution": 0}, "steps_per_revolution"),
        ({**WINDOW, "iteration_unit": "inner_iterations"}, "iteration_unit"),
        ({**WINDOW, "verification": "guess"}, "verification"),
        ({**WINDOW, "last_iters": 54}, "exactly one"),
    ],
)
def test_malformed_recorded_window_is_refused_at_read(window, field):
    raw = _record().model_dump()
    raw["surface_time_averaging"] = window
    try:
        RunRecord.model_validate(raw)
    except ValidationError as error:
        assert "surface_time_averaging" in str(error)
        assert field in str(error)
    else:
        pytest.fail(f"malformed surface window accepted: {field}")


def test_continuation_preserves_recorded_surface_window(tmp_path, monkeypatch):
    workspace = _workspace(tmp_path)
    _stopped(workspace)
    original_read = CampaignWorkspace.read_manifest

    def records(self):
        records = original_read(self)
        records[0] = records[0].model_copy(
            update={
                "surface_time_averaging": dict(WINDOW),
                "stopped_at": {"step": 100},
                "export_window": {"time_iterations": 144},
            }
        )
        return records

    monkeypatch.setattr(CampaignWorkspace, "read_manifest", records)
    successor = _run(workspace, _restart_row(tmp_path), _submitting(workspace))[0]
    assert successor.status is RunStatus.SUBMITTED
    assert successor.surface_time_averaging == WINDOW, "continuation lost the recorded window"
    assert original_read(workspace)[-1].surface_time_averaging == WINDOW
    metadata = surface_export_metadata(successor)
    assert metadata == {"kind": "average", "window": WINDOW}
    assert "step 60" in _surface_export_skip(metadata, frozen_time_steps(_log(2413)))


def test_manifest_refuses_malformed_window_with_run_and_remedy(tmp_path, monkeypatch):
    raw = _record().model_dump()
    raw["surface_time_averaging"] = {**WINDOW, "iterations": [91]}
    monkeypatch.setattr(CampaignWorkspace, "read_raw_manifest", lambda self: [raw])
    try:
        CampaignWorkspace(tmp_path).read_manifest()
    except WorkspaceError as error:
        assert raw["run_id"] in str(error)
        assert "iterations" in str(error)
        assert "restore" in str(error).lower()
    except ValidationError as error:
        pytest.fail(f"raw validation error escaped manifest reader: {error}")
    else:
        pytest.fail("manifest reader accepted malformed surface window")
