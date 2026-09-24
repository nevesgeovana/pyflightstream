"""Tier 3: a custom free stream on a row (``matriz_gui.fs`` 5011 to 5014, G15, the probe T14).

Four rows on the 12_WING_PHY wing, the qa physics preset with five far-field
layers, on 26.124, each moving ONE thing against a CONSTANT control (their
scripts differ in the lines named, which the tier-1 control asserts):

* 5011 writes ``SET_FREESTREAM CUSTOM STRUCTURED`` with ``fs_uniform.txt``,
  vx = 30 m/s everywhere (the row's own ``TASmps``) and vy = vz = 0, at 4 deg,
  against 5010, the CONSTANT control at 4 deg;
* 5012 writes the same field at 0 deg, against 5013, the CONSTANT control at
  0 deg;
* 5014 writes ``fs_shear.txt``, vx = 30 + 2.5 z m/s, at 0 deg, against 5013.

WHAT THEY ANSWER, which no manual states:

(a) whether a uniform field the file states in m/s loads as the constant free
    stream it equals, which is the file read in the unit it is written in;
(b) whether the solver still turns a custom field by the row's
    ``SOLVER_SET_AOA``. At 0 deg the two free streams are one (5012 against
    5013). At 4 deg, 5011 loads as 5010 if the angle turns the field, and as
    5012 if it does not; the test prints which, and fails only when neither
    holds;
(c) whether the field reaches the solve at all: a sheared field moves the
    loads off the uniform control.

"Equal" is 1e-4 relative over a 1e-3 floor, on CL, CDi and CDo, as
``test_gui.py`` judges a disc; a solve repeated with nothing changed prints the
same digits (RPT-067's control and its three repeats).
"""

from __future__ import annotations

import hashlib

import pytest

from tests.tier3_licensed.conftest import TERMINAL_OK
from tests.tier3_licensed.freestreams import FOLDER

pytestmark = pytest.mark.needs_flightstream

MATRIX = "matriz_gui"
#: Two loads are the same within this, relative to the second.
EQUAL = 1e-4
#: The denominator's floor, so a coefficient near zero (the lift of the
#: symmetric wing at 0 deg) is judged absolutely.
FLOOR = 1e-3
#: The loads judged.
LOADS = ("CL", "CDi", "CDo")
#: Each row, its angle of attack and the field it names (None: CONSTANT).
ROWS = {
    "5010": (4.0, None),
    "5011": (4.0, "fs_uniform"),
    "5012": (0.0, "fs_uniform"),
    "5013": (0.0, None),
    "5014": (0.0, "fs_shear"),
}


def _loads(runs, pol: str) -> dict[str, float]:
    alpha, _ = ROWS[pol]
    total = runs.total(runs.one(MATRIX, pol, alpha=alpha))
    return {name: total[name] for name in LOADS}


def _gap(loads: dict[str, float], control: dict[str, float]) -> dict[str, float]:
    return {
        name: abs(loads[name] - control[name]) / max(abs(control[name]), FLOOR) for name in LOADS
    }


def _equal(loads: dict[str, float], control: dict[str, float]) -> bool:
    return max(_gap(loads, control).values()) <= EQUAL


def _said(loads: dict[str, float]) -> str:
    return ", ".join(f"{name} {value:.6g}" for name, value in loads.items())


@pytest.mark.parametrize("pol", sorted(ROWS))
def test_every_row_ran_terminal_on_26_124_with_its_free_stream(runs, pol):
    """Each point converged on 26.124 with five far-field layers, writing the free
    stream its row names, and a custom row's record hashes the field it read."""
    alpha, field = ROWS[pol]
    record = runs.one(MATRIX, pol, alpha=alpha)
    assert record.status in TERMINAL_OK, (record.status, record.error)
    assert record.fs_version_requested == "26.124"
    lines = runs.script(record).splitlines()
    assert "SOLVER_SET_FARFIELD_LAYERS 5" in lines
    if field is None:
        assert "SET_FREESTREAM CONSTANT" in lines
        return
    at = lines.index("SET_FREESTREAM CUSTOM STRUCTURED")
    assert lines[at + 1].replace("\\", "/").endswith(f"inputs/freestreams/{field}.txt")
    path = FOLDER / f"{field}.txt"
    assert record.inputs_sha256.get(path.name) == hashlib.sha256(path.read_bytes()).hexdigest()


def test_a_the_uniform_field_loads_as_its_constant_control(runs):
    """(a) 5011 against 5010: the field in m/s as written is the constant free stream."""
    custom, control = _loads(runs, "5011"), _loads(runs, "5010")
    if _equal(custom, control):
        return
    at_zero = _loads(runs, "5012")
    reading = (
        "it loads as the same field at 0 deg (5012), so the solver does NOT turn a custom "
        "field by SOLVER_SET_AOA"
        if _equal(custom, at_zero)
        else "it loads as neither the 4 deg control nor the same field at 0 deg, so the field "
        "is read otherwise than as written (its unit, its frame, or a scale)"
    )
    pytest.fail(
        f"5011 does not load as its control 5010: gap {_gap(custom, control)} over "
        f"{EQUAL} (5011: {_said(custom)}; 5010: {_said(control)}); {reading}"
    )


def test_b_whether_the_angle_of_attack_turns_a_custom_field(runs, capsys):
    """(b) at 0 deg the two free streams are one; at 4 deg, which one 5011 loads as."""
    zero, zero_control = _loads(runs, "5012"), _loads(runs, "5013")
    assert _equal(zero, zero_control), (
        f"at 0 deg the uniform field (5012) does not load as the constant free stream "
        f"(5013): gap {_gap(zero, zero_control)}, so the question below has no baseline"
    )
    four, four_control = _loads(runs, "5011"), _loads(runs, "5010")
    turned, not_turned = _equal(four, four_control), _equal(four, zero)
    if turned and not not_turned:
        answer = (
            "SOLVER_SET_AOA TURNS a custom field: 5011 at 4 deg loads as the CONSTANT "
            "control 5010 at 4 deg"
        )
    elif not_turned and not turned:
        answer = (
            "SOLVER_SET_AOA does NOT turn a custom field: 5011 at 4 deg loads as the same "
            "field at 0 deg (5012)"
        )
    else:
        pytest.fail(
            f"no single reading holds: 5011 against 5010 {_gap(four, four_control)}, against "
            f"5012 {_gap(four, zero)}; 5011 {_said(four)}"
        )
    with capsys.disabled():
        print(
            f"\nT14 (G15): {answer}. 5011: {_said(four)}; 5010: {_said(four_control)}; "
            f"5012: {_said(zero)}"
        )


def test_c_a_sheared_field_moves_the_loads_off_its_control(runs):
    """(c) 5014 against 5013: the field reached the solve."""
    sheared, control = _loads(runs, "5014"), _loads(runs, "5013")
    gap = _gap(sheared, control)
    assert max(gap.values()) > EQUAL, (
        f"the sheared field (5014) loads as its CONSTANT control (5013): {gap}, so the "
        f"field did not reach the solve (5014: {_said(sheared)})"
    )
