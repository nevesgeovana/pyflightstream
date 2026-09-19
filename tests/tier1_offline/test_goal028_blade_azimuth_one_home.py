"""Where a blade is at a step has one home, `post.axes.blade_azimuth_deg`.

The release review (REL-0240 round 1, ARCH-A2) found the rule written out in
three modules, each with its own reading of the sign of `rpm` and of when the
clock is not stated. The expected values here come from the CONVENTION, worked
by hand: one revolution every `steps_per_revolution` steps, in the sense of the
sign of `rpm`, from the datum at step zero, wrapped to [0, 360).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from pyflightstream.post.axes import blade_azimuth_deg

POST = Path(__file__).parents[2] / "src" / "pyflightstream" / "post"


def test_step_must_be_named():
    with pytest.raises(TypeError, match="positional"):
        blade_azimuth_deg(10.0, 18, steps_per_revolution=72, rpm=2000.0)


@pytest.mark.parametrize(
    ("datum", "step", "per_revolution", "rpm", "expected"),
    [
        (0.0, 0, 72, 2000.0, 0.0),
        (10.0, 18, 72, 2000.0, 100.0),  # a quarter turn forward
        (10.0, 18, 72, -2000.0, 280.0),  # a quarter turn backward
        (350.0, 144, 72, 2000.0, 350.0),  # two whole revolutions
        (0.0, 73, 72, 1.0, 5.0),  # one revolution and one step of five degrees
    ],
)
def test_a_blade_turns_from_its_datum_in_the_sense_of_rpm(
    datum, step, per_revolution, rpm, expected
):
    got = blade_azimuth_deg(datum, step=step, steps_per_revolution=per_revolution, rpm=rpm)
    assert got == pytest.approx(expected, abs=1e-9)


@pytest.mark.parametrize(
    ("datum", "step", "per_revolution", "rpm"),
    [
        (None, 18, 72, 2000.0),
        (10.0, None, 72, 2000.0),
        (10.0, 18, None, 2000.0),
        (10.0, 18, 0, 2000.0),
        (10.0, 18, 72, None),
        (10.0, 18, 72, 0.0),
        (10.0, 18, 72, True),
    ],
)
def test_a_clock_that_is_not_stated_gives_no_azimuth_and_never_a_zero(
    datum, step, per_revolution, rpm
):
    assert blade_azimuth_deg(datum, step=step, steps_per_revolution=per_revolution, rpm=rpm) is None


def _modules_that_turn_a_step_into_degrees() -> set[str]:
    """The post modules holding a product `... * 360 / ...` or `... * 360.0 / ...`."""
    found = set()
    for path in sorted(POST.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)):
                continue
            left = node.left
            if not (isinstance(left, ast.BinOp) and isinstance(left.op, ast.Mult)):
                continue
            if isinstance(left.right, ast.Constant) and left.right.value in (360, 360.0):
                found.add(path.name)
    return found


def test_no_other_post_module_writes_the_rule_out_again():
    assert _modules_that_turn_a_step_into_degrees() == {"axes.py"}
