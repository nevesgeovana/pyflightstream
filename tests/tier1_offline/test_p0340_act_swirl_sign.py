"""Tier 1, 0.34.0: an actuator disc swirls the way a rotor of its rpm_sign turns (FR-331).

Pipeline role: quality gate on the disc speed the script hands the solver.

A block's ``rpm_sign`` is the hand a rotor block states, ``+1`` the right-hand
rule about the block's ``axis``. Measured on 26.124 (RPT-137), a disc handed
plus the hand times the speed swirled its wake AGAINST a rotor of the same
``rpm_sign``, and a disc handed minus swirled with it. From 0.34.0 the disc
speed line carries minus the hand times the row's magnitude, 0.33.0's line
with the other sign, and the parity script names that difference under FR-331
and nothing else.

What it checks: the emitted line for both hands, by the stated speed and by
the advance ratio, on a steady and an unsteady row; the reference block's
docstring saying the same; and the parity entry accepting the sign flip alone.
What it does NOT check: what the solver does with the line. That is RPT-137's
measurement, of one build; on another build the rule is the same and
unmeasured.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from pyflightstream.cases import ActuatorBlock, FrameSpec, SimCase
from pyflightstream.cases.workflows import build_script
from pyflightstream.script import Script
from tests.tier1_offline.test_workflows import steady_case, unsteady_case

REPO = Path(__file__).resolve().parents[2]
HUB = FrameSpec(name="HUB", origin=(1.0, 0.0, 0.0))


def _disc(rpm_sign: int) -> ActuatorBlock:
    return ActuatorBlock(
        frame="HUB", axis="X", tip_radius_m=0.5, hub_radius_m=0.1, rpm_sign=rpm_sign
    )


def _speed_lines(case: SimCase, rpm_sign: int) -> list[str]:
    case = case.model_copy(update={"frames": [HUB], "actuators": {"PROP": _disc(rpm_sign)}})
    script = Script("26.124")
    build_script(case, script)
    return [
        line for line in script.render().splitlines() if line.startswith("SET_PROP_ACTUATOR_RPM")
    ]


@pytest.mark.parametrize("make", [steady_case, unsteady_case], ids=["steady", "unsteady"])
@pytest.mark.parametrize("rpm_sign", [1, -1], ids=["plus", "minus"])
def test_p0340_act_swirl_sign_the_disc_line_carries_minus_the_hand(make, rpm_sign):
    """P0340-ACT-SWIRL-SIGN, FR-331 R2 and R3: the disc speed handed to the solver is minus
    the block's rpm_sign times the row's magnitude, so rpm_sign +1 writes -2400.0 and
    rpm_sign -1 writes 2400.0, 0.33.0's lines with the other sign."""
    lines = _speed_lines(
        make(ACTUATOR="PROP", ACTUATOR_RPM="2400", ACTUATOR_THRUST="120"), rpm_sign
    )
    assert lines == [f"SET_PROP_ACTUATOR_RPM 1 {-rpm_sign * 2400.0}"], (
        f"a disc of rpm_sign {rpm_sign:+d} at 2400 rev/min emits {lines}; the solver swirls "
        "with a rotor of the same hand when handed minus the hand (RPT-137)"
    )


@pytest.mark.parametrize("rpm_sign", [1, -1], ids=["plus", "minus"])
def test_p0340_act_swirl_sign_the_advance_ratio_route_follows_the_same_rule(rpm_sign):
    """P0340-ACT-SWIRL-SIGN, FR-331 R2: a disc turned by ADVANCE_RATIO (n = V / (J D) with
    its own diameter, 2250 rev/min at J 0.8 and 30 m/s) is handed minus its rpm_sign times
    that speed, as a disc turned by ACTUATOR_RPM is."""
    lines = _speed_lines(
        steady_case(ACTUATOR="PROP", ADVANCE_RATIO="0.8", ACTUATOR_THRUST="120"), rpm_sign
    )
    assert lines == [f"SET_PROP_ACTUATOR_RPM 1 {-rpm_sign * 2250.0}"], lines


def test_p0340_act_swirl_sign_the_block_docstring_says_the_disc_swirls_with_the_rotor():
    """P0340-ACT-SWIRL-SIGN, FR-331 R1 and R2: the reference block's docstring states that
    rpm_sign +1 is the right-hand rule about the axis and that the disc swirls as a rotor of
    that sign turns, citing FR-331 and RPT-137."""
    block = " ".join((ActuatorBlock.__doc__ or "").split())
    for fact in (
        "``+1`` is the right-hand rule about ``axis``",
        "the disc swirls as a rotor of this sign turns (FR-331, RPT-137)",
    ):
        assert fact in block, f"the ActuatorBlock docstring no longer says {fact!r}"


def _parity():
    spec = importlib.util.spec_from_file_location(
        "check_parity", REPO / "scripts" / "check_parity.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("check_parity", module)
    spec.loader.exec_module(module)
    return module


#: Three lines of a 0.33.0 disc emission, the speed line between two others.
OLD = (
    "CREATE_NEW_ACTUATOR PROPELLER ELLIPTICAL PROP\n"
    "SET_PROP_ACTUATOR_RPM 1 2400.0\n"
    "ENABLE_ACTUATOR 1\n"
)


@pytest.mark.parametrize(
    ("new", "named"),
    [
        (OLD.replace("RPM 1 2400.0", "RPM 1 -2400.0"), True),
        (
            OLD.replace("RPM 1 2400.0", "RPM 1 -2400.0") + "SET_PROP_ACTUATOR_RPM 2 -900.0\n",
            False,
        ),
        (OLD.replace("RPM 1 2400.0", "RPM 1 2500.0"), False),
        (OLD.replace("RPM 1 2400.0", "RPM 1 -2500.0"), False),
        (OLD.replace("RPM 1 2400.0", "RPM 2 -2400.0"), False),
        (
            OLD.replace("ENABLE_ACTUATOR 1", "ENABLE_ACTUATOR 2").replace(
                "RPM 1 2400.0", "RPM 1 -2400.0"
            ),
            False,
        ),
    ],
    ids=["sign-flip", "an-added-line", "magnitude", "magnitude-and-sign", "index", "another-line"],
)
def test_p0340_act_swirl_sign_parity_names_the_sign_flip_alone(new, named):
    """P0340-ACT-SWIRL-SIGN, FR-331 R4: the parity script's NAMED_DIFFERENCES ties a script
    difference to FR-331 only when every changed line is a disc speed line whose sign, and
    nothing else, flipped; a changed magnitude, index or any other line stays unnamed."""
    entry = _parity().name_difference("scripts", "P5008-x.txt", OLD, new, {"FR-331"})
    assert (entry.get("requirement") == "FR-331") is named, entry
    backwards = _parity().name_difference(
        "scripts", "P5008-x.txt", OLD.replace("2400.0", "-2400.0"), OLD, {"FR-331"}
    )
    assert backwards.get("requirement") == "FR-331", (
        "a disc of rpm_sign -1 changes from -2400.0 to 2400.0, which is the same flip",
        backwards,
    )


#: The same emission for a disc of rpm_sign -1 in 0.33.0, its speed handed negative.
OLD_MINUS = OLD.replace("RPM 1 2400.0", "RPM 1 -2400.0")


@pytest.mark.parametrize(
    ("new", "named"),
    [
        (OLD, True),
        (OLD.replace("RPM 1 2400.0", "RPM 2 2400.0"), False),
        (OLD.replace("RPM 1 2400.0", "RPM 1 2500.0"), False),
    ],
    ids=["sign-flip", "index", "magnitude"],
)
def test_p0340_act_swirl_sign_parity_minus_first_holds_index_and_magnitude(new, named):
    """P0340-ACT-SWIRL-SIGN, FR-331 R4: from a 0.33.0 disc speed handed negative, the
    flip to positive is named, and a flip that also moves the disc index or the magnitude
    stays unnamed, so the minus-first branch of the block holds the index and the speed."""
    entry = _parity().name_difference("scripts", "P5008-x.txt", OLD_MINUS, new, {"FR-331"})
    assert (entry.get("requirement") == "FR-331") is named, entry
