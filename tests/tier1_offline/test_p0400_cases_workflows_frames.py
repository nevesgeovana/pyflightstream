"""P0400-CW-FRAMES: a flat rotor row's frames are placed from its hub as the script placed it.

0.40.0 items PFS-2104.004 (the ``<ALIAS>_SMRP_ORIGINAL`` copy is the hub as
placed), PFS-2104.005 (the flat row's blade frames sit at the hub, on its
basis, from the blade1 datum) and PFS-2104.034 (the hub basis keeps the sign of
``blade1.zero``).
"""

from __future__ import annotations

import pytest

from pyflightstream.cases import (
    BladeDatum,
    CampaignConfigError,
    ReferenceData,
    RotorBlock,
    SimCase,
    SweepAxis,
)
from pyflightstream.cases.matrix import _parse_rotations
from pyflightstream.cases.workflows import build_script
from pyflightstream.cases.workflows._frames import _hub_basis, _keep_the_frame_this_alias_turns_from
from pyflightstream.script import Script
from tests.support_helpers import saved_mesh_fixture

SHAFT = (1.0, 0.0, 0.1)
PUSHER = RotorBlock(
    alias="PUSHER",
    axis=SHAFT,
    rpm_sign=1,
    diameter_m=1.8,
    x_m=7.2,
    families_general=["Spinner"],
    families_blades=["Blade1", "Blade2", "Blade3"],
    blade1=BladeDatum(azimuth_deg=30.0, zero="Y"),
)


def _flat_row(tmp_path, **variables: str) -> SimCase:
    mesh = ["Spinner", "Blade1", "Blade2", "Blade3", "W"]
    case = SimCase(
        sim_id="9301",
        aircraft="WORK",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        recipe="unsteady_rotor",
        outputs=["loads_a+00.0.txt"],
        variables={
            "WORKFLOW": "unsteady_rotor",
            "VELOCITY": "30.0",
            "RPM": "1200",
            "ROTOR_AXIS": "Z",
            "DELTA_TIME": "0.0001",
            "TIME_ITERATIONS": "720",
            "LAST_REVS_AVG": "1",
            **variables,
        },
        point={"alpha": 0.0},
        geometry=str(saved_mesh_fixture(tmp_path / "w.fsm", mesh)),
        rotors={"PUSHER": PUSHER},
        aliases={"PUSHER": mesh[:4]},
        reference=ReferenceData(area=16.0, length=1.6, span_m=10.0),
    )
    case.rotations = _parse_rotations(
        {"ROTATE": "{ANGLE: 3 / AXIS: PUSHER_SMRP-Y / ALIAS: PUSHER}"}, case.sim_id
    )
    return case


def _frames(case: SimCase) -> tuple[dict[str, dict[str, float]], list[list[str]]]:
    """Each frame's EDIT_COORDINATE_SYSTEM fields by name, and every ROTATE block."""
    script = Script("26.124")
    build_script(case, script)
    lines = script.render().splitlines()
    edits: dict[str, dict[str, float]] = {}
    rotations: list[list[str]] = []
    for at, line in enumerate(lines):
        if line == "EDIT_COORDINATE_SYSTEM":
            name = lines[at + 2].split(" ", 1)[1]
            fields = dict(each.split(" ", 1) for each in lines[at + 3 : at + 15])
            edits[name] = {key: float(value) for key, value in fields.items()}
            edits[name]["FRAME"] = float(lines[at + 1].split()[1])
        elif line == "ROTATE_COORDINATE_SYSTEM":
            rotations.append(lines[at + 1 : at + 5])
    return edits, rotations


def _placement(edit: dict[str, float]) -> list[float]:
    keys = ("ORIGIN", "VECTOR_X", "VECTOR_Y", "VECTOR_Z")
    return [value for key, value in edit.items() if key.startswith(keys)]


def test_p0400_cw_frames_the_original_copy_is_the_hub_as_placed(tmp_path):
    """P0400-CW-FRAMES (PFS-2104.004): ROTOR_ORIGIN and the shaft basis reach the copy.

    It was rebuilt from the block's origin on identity axes, a frame the hub
    never was on this row.
    """
    requirement = "P0400-CW-FRAMES"
    edits, _ = _frames(_flat_row(tmp_path, ROTOR_ORIGIN="1.0,2.0,3.0"))
    hub, copy = edits["PUSHER_SMRP"], edits["PUSHER_SMRP_ORIGINAL"]
    assert (hub["ORIGIN_X"], hub["ORIGIN_Y"], hub["ORIGIN_Z"]) == (1.0, 2.0, 3.0), requirement
    assert _placement(copy) == _placement(hub)


def test_p0400_cw_frames_a_flat_rows_blade_frames_sit_at_the_hub_from_the_datum(tmp_path):
    """P0400-CW-FRAMES (PFS-2104.005): the blades turn about the hub they are named under.

    They sat at `rotor_position_m` or the origin, on identity axes, from azimuth
    zero, while being registered as the hub's `<ALIAS>_RMRP<k>`.
    """
    requirement = "P0400-CW-FRAMES"
    edits, rotations = _frames(_flat_row(tmp_path, ROTOR_ORIGIN="1.0,2.0,3.0"))
    hub = edits["PUSHER_SMRP"]
    blades = [edits[f"BladeAxis{number}"] for number in (1, 2, 3)]
    for blade in blades:
        assert _placement(blade) == _placement(hub), requirement
    turns = {
        int(rotation[0].split()[1]): rotation[1:]
        for rotation in rotations
        if rotation[1] == f"ROTATION_FRAME {int(hub['FRAME'])}" and rotation[2] != "ROTATION_AXIS Y"
    }
    assert [turns[int(blade["FRAME"])] for blade in blades] == [
        [f"ROTATION_FRAME {int(hub['FRAME'])}", "ROTATION_AXIS Z", f"ANGLE {angle}"]
        for angle in (30.0, 150.0, 270.0)
    ]


def test_p0400_cw_frames_the_hub_basis_keeps_the_sign_of_the_datum():
    """P0400-CW-FRAMES (PFS-2104.034): '-Y' measures the azimuth from the opposite side."""
    requirement = "P0400-CW-FRAMES"
    plus = _hub_basis(PUSHER)
    minus = _hub_basis(
        PUSHER.model_copy(update={"blade1": BladeDatum(azimuth_deg=30.0, zero="-Y")})
    )
    assert minus[0] == pytest.approx(tuple(-each for each in plus[0])), requirement
    assert minus[1] == pytest.approx(tuple(-each for each in plus[1]))


def test_p0400_cw_frames_an_unplaced_hub_cannot_be_copied(tmp_path):
    """P0400-CW-FRAMES (PFS-2104.004): a copy cannot guess an opened or turned hub."""
    requirement = "P0400-CW-FRAMES"
    with pytest.raises(CampaignConfigError, match="cannot state where PUSHER_SMRP") as refusal:
        _keep_the_frame_this_alias_turns_from(
            _flat_row(tmp_path),
            {"ALIAS": "PUSHER"},
            Script("26.124"),
            {"PUSHER_SMRP": 2},
            set(),
        )
    assert str(refusal.value), requirement
