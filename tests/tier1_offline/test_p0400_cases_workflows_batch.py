"""P0400-CW-BATCH: a grouped job never creates a motion its instance still holds.

0.40.0 item PFS-2104.037: a two-rotor point whose every speed moves was restated
from the first rotor's SET_MOTION_ROTOR_RPM, so the second rotor's whole motion,
CREATE_NEW_MOTION included, was created again after REMOVE_INITIALIZATION.
"""

from __future__ import annotations

from pathlib import PurePosixPath

import pytest

from pyflightstream.cases import CampaignConfigError
from pyflightstream.cases.workflows._batch_script import (
    JobPoint,
    refuse_unspliceable,
    restate_anchor,
)

HEAD = ["OPEN", "/ws/g.fsm", "", "SET_SIGNIFICANT_DIGITS 7", ""]


def _motion(number: int, rpm: float) -> list[str]:
    return [
        "CREATE_NEW_MOTION ROTARY",
        f"SET_MOTION_BOUNDARIES {number} 1",
        f"SET_MOTION_ROTOR_RPM {number} {rpm}",
    ]


def _point(folder: str, *motions: list[str]) -> JobPoint:
    text = "\n".join(
        [*HEAD, *(line for motion in motions for line in motion), "SET_SOLVER_UNSTEADY", ""]
    )
    return JobPoint(
        run_id=f"mtx/sim_9901/{folder}",
        sim_id="9901",
        point_name=folder,
        text=text,
        datapoint_dir=PurePosixPath(f"/ws/sim_9901/datapoints/{folder}"),
        outputs=(),
        action_exports="",
        first_export_step=None,
        stop_text="",
        time_steps=45,
    )


def test_p0400_cw_batch_a_restated_point_that_creates_a_motion_again_is_refused():
    """P0400-CW-BATCH (PFS-2104.037): both speeds move, so rotor 2 would be created twice."""
    requirement = "P0400-CW-BATCH"
    first = _point("DP-j10", _motion(1, 1000.0), _motion(2, 2000.0))
    later = _point("DP-j12", _motion(1, 1100.0), _motion(2, 2200.0))
    with pytest.raises(CampaignConfigError, match="creates a motion\\s+again") as refusal:
        refuse_unspliceable(first, later)
    assert str(refusal.value), requirement


def test_p0400_cw_batch_one_rotor_is_still_restated_from_its_speed():
    """P0400-CW-BATCH (PFS-2104.037), control: the measured one-rotor shape is unchanged."""
    requirement = "P0400-CW-BATCH"
    first = _point("DP-j10", _motion(1, 1000.0))
    later = _point("DP-j12", _motion(1, 1100.0))
    refuse_unspliceable(first, later)
    assert restate_anchor(first, later) == "SET_MOTION_ROTOR_RPM", requirement
