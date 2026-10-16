"""Tier 1, 0.42.0 P2-1b: a frame's axes must define a coordinate system.

Pipeline role: guards on :class:`pyflightstream.cases.FrameSpec` and
:func:`pyflightstream.script.helpers.coordinate_frame` (SPCM-1). Each degenerate
pair is shown refused, beside controls that are accepted: lengths other than one
are directions and stay legal.
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from pyflightstream.cases import FrameSpec
from pyflightstream.script import Script, helpers
from pyflightstream.script._arg_checks import CommandArgumentError

X, Y = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
S = math.sqrt(0.5)

BAD = {
    "zero x": ((0.0, 0.0, 0.0), Y, "x_axis has zero length"),
    "zero y": (X, (0.0, 0.0, 0.0), "y_axis has zero length"),
    "parallel": (X, (3.0, 0.0, 0.0), "parallel"),
    "antiparallel": (X, (-2.0, 0.0, 0.0), "parallel"),
    "oblique": (X, (1.0, 1.0, 0.0), "not orthogonal"),
    "nearly parallel": (X, (1.0, 1e-5, 0.0), "parallel"),
    "not finite": (X, (0.0, float("nan"), 0.0), "not a finite number"),
}
GOOD = {
    "reference": (X, Y),
    "long x": ((2.0, 0.0, 0.0), Y),
    "turned": ((S, S, 0.0), (-S, S, 0.0)),
    "tilted": ((0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)),
}


@pytest.mark.parametrize("case", BAD)
def test_p0420_frame_axes_problem_names_each_degenerate_pair(case):
    x, y, said = BAD[case]
    assert said in (helpers.frame_axes_problem(x, y) or "")


@pytest.mark.parametrize("case", GOOD)
def test_p0420_frame_axes_problem_accepts_directions_of_any_length(case):
    assert helpers.frame_axes_problem(*GOOD[case]) is None


@pytest.mark.parametrize("case", BAD)
def test_p0420_frame_spec_refuses_a_degenerate_pair_naming_the_frame_and_both_vectors(case):
    """PFS-2130.018, PFS-2130.021: refused where it is written."""
    x, y, said = BAD[case]
    with pytest.raises(ValidationError) as refusal:
        FrameSpec(name="NAC", origin=(0.0, 0.0, 0.0), x_axis=x, y_axis=y)
    text = str(refusal.value)
    assert "'NAC'" in text and said in text and str(x) in text and str(y) in text


@pytest.mark.parametrize("case", GOOD)
def test_p0420_frame_spec_accepts_the_controls(case):
    x, y = GOOD[case]
    assert FrameSpec(name="NAC", origin=(0.0, 0.0, 0.0), x_axis=x, y_axis=y).x_axis == x


@pytest.mark.parametrize("case", BAD)
def test_p0420_coordinate_frame_refuses_a_degenerate_pair_and_emits_nothing(case):
    """PFS-2130.053: refused when emitted, nothing written to the script."""
    x, y, said = BAD[case]
    script = Script("26.124")
    with pytest.raises(CommandArgumentError, match="'NAC'") as refusal:
        helpers.coordinate_frame(script, name="NAC", origin=(0, 0, 0), x_axis=x, y_axis=y)
    assert said in str(refusal.value)
    assert script.num_local_frames == 0 and script.render().strip() == ""


@pytest.mark.parametrize("case", GOOD)
def test_p0420_coordinate_frame_writes_the_controls_as_given(case):
    x, y = GOOD[case]
    script = Script("26.124")
    index = helpers.coordinate_frame(script, name="NAC", origin=(0, 0, 0), x_axis=x, y_axis=y)
    assert index == 2 and script.num_local_frames == 1


def test_p0420_coordinate_frame_refuses_a_z_axis_that_is_not_the_cross_product():
    script = Script("26.124")
    with pytest.raises(CommandArgumentError, match="z_axis"):
        helpers.coordinate_frame(
            script, name="LH", origin=(0, 0, 0), x_axis=X, y_axis=Y, z_axis=(0.0, 0.0, -1.0)
        )
    helpers.coordinate_frame(
        script, name="RH", origin=(0, 0, 0), x_axis=X, y_axis=Y, z_axis=(0.0, 0.0, 1.0)
    )
