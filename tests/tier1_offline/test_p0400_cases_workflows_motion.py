"""P0400-CW-MOTION: a MOTIONS row never turns a vector shaft about global Z.

0.40.0 item PFS-2104.008: the MOTIONS builder creates the hub on the
geometry's axes while the view hands the motion the letter Z. Both the hub
and moving frame must put their third axis on the declared shaft.
"""

from __future__ import annotations

import pytest

from pyflightstream.cases.workflows import build_script
from pyflightstream.script import Script
from tests.tier1_offline.test_rotor_by_alias import PUSHER, two_rotor_case


def test_p0400_cw_motion_a_vector_shaft_on_a_motions_row_uses_its_shaft(tmp_path):
    """P0400-CW-MOTION (PFS-2104.008): local Z follows the declared vector shaft."""
    requirement = "P0400-CW-MOTION"
    case = two_rotor_case(tmp_path)
    tilted = type(PUSHER).model_validate({**PUSHER.model_dump(), "axis": (1.0, 0.0, 0.1)})
    case = case.model_copy(update={"rotors": {**case.rotors, "PUSHER": tilted}})
    script = Script("26.124")
    build_script(case, script)
    lines = script.render().splitlines()
    placements = {}
    for at, line in enumerate(lines):
        if line == "EDIT_COORDINATE_SYSTEM":
            name = lines[at + 2].split(" ", 1)[1]
            fields = dict(each.split(" ", 1) for each in lines[at + 3 : at + 15])
            placements[name] = tuple(float(fields[f"VECTOR_Z_{axis}"]) for axis in "XYZ")
    for name in ("PUSHER_SMRP", "PUSHER_RMRP"):
        assert placements[name] == pytest.approx(tilted.axis_vector), requirement


def test_p0400_cw_motion_a_letter_shaft_on_a_motions_row_still_builds(tmp_path):
    """P0400-CW-MOTION (PFS-2104.008), control: the letter path is untouched."""
    requirement = "P0400-CW-MOTION"
    script = Script("26.124")
    build_script(two_rotor_case(tmp_path), script)
    assert "SET_MOTION_ROTOR_RPM" in script.render(), requirement
