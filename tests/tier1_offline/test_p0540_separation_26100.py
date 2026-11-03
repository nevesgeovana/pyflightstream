"""P0540-MARK: a row stating airfoil_separation on 26.100 is warned and skipped (FR-3476)."""

from __future__ import annotations

import warnings

import pytest

from pyflightstream._errors import NotApplicableWarning
from pyflightstream.script import Script, helpers
from pyflightstream.script.solver_setup import AirfoilSeparation


def _model(build: str) -> AirfoilSeparation:
    if build == "26.125":
        return AirfoilSeparation(name="W", leading_edge_type="SHARP", boundaries=[1])
    return AirfoilSeparation(name="W", boundaries=[1])


@pytest.mark.requirement("FR-3476")
def test_p0540_airfoil_separation_on_26100_is_warned_and_not_emitted():
    script = Script("26.100")
    script.declare_existing(boundaries=2)
    with pytest.warns(NotApplicableWarning) as caught:
        helpers.solver_settings(script, airfoil_separation=[_model("26.100")])
    text = str(caught[0].message)
    assert "axial_separation_families" in text
    assert "User Guide, Flow separation" in text
    assert "no separation model" in text
    assert "not claimed to give the same result" in text
    assert "CREATE_AIRFOIL_SEPARATION" not in script.render()


@pytest.mark.requirement("FR-3476")
@pytest.mark.parametrize("build", ["26.101", "26.124", "26.125"])
def test_p0540_airfoil_separation_from_26101_on_is_unchanged(build):
    script = Script(build)
    script.declare_existing(boundaries=2)
    with warnings.catch_warnings():
        warnings.simplefilter("error", NotApplicableWarning)
        helpers.solver_settings(script, airfoil_separation=[_model(build)])
    assert "CREATE_AIRFOIL_SEPARATION W 1" in script.render()


@pytest.mark.requirement("FR-3476")
def test_p0540_26100_without_airfoil_separation_is_silent():
    script = Script("26.100")
    script.declare_existing(boundaries=2)
    with warnings.catch_warnings():
        warnings.simplefilter("error", NotApplicableWarning)
        helpers.solver_settings(script, iterations=10)


@pytest.mark.requirement("FR-3476")
def test_p0540_the_26100_skip_is_a_warning_even_under_warning_refusals():
    """The skip is the behaviour: the strict option does not turn it into a refusal."""
    from pyflightstream.options import option_context

    script = Script("26.100")
    script.declare_existing(boundaries=2)
    with option_context("warning_refusals", True), pytest.warns(NotApplicableWarning):
        helpers.solver_settings(script, airfoil_separation=[_model("26.100")])
    assert "CREATE_AIRFOIL_SEPARATION" not in script.render()
