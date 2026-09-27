# GEOVERSE_HEADER
# file_version: "1.0.1"
# last_modified_at: "2026-09-27T22:09:28.693Z"
# last_modified_by: {provider: OpenAI, product: Codex, model: GPT-6, role: independent-reviewer}
# dependencies:
#   - ../../src/pyflightstream/run/__init__.py
#   - ../../src/pyflightstream/cases/workflows.py
# status: active
# confidentiality: public
# change_summary: "Bind the existing first/later point start regression to approved R13."
# revision_source: git
"""R13: exercise emitted sweep behavior as well as the run-layer selection."""

import pytest

from pyflightstream.cases import SimCase, SweepAxis
from pyflightstream.cases.workflows import build_steady_sweep
from pyflightstream.run import _is_cold_start
from pyflightstream.script import Script


def _points():
    return [
        SimCase(
            sim_id="5001",
            aircraft="WB",
            recipe="steady",
            sweep=SweepAxis(type="alpha", values=[alpha]),
            point={"alpha": alpha, "beta": 0.0},
            outputs=[f"loads_a{alpha:+05.1f}.txt"],
            variables={"VELOCITY": "68.058"},
        )
        for alpha in (-2.0, 0.0, 2.0)
    ]


def test_run_layer_defaults_to_cold():
    assert _is_cold_start(_points()[0]) is True


@pytest.mark.parametrize("value,expected", [("false", False), (False, False), ("true", True)])
def test_explicit_legacy_flag_is_preserved(value, expected):
    case = _points()[0]
    case.variables["COLD_START"] = value
    assert _is_cold_start(case) is expected


@pytest.mark.parametrize("option,clears", [(None, 3), (True, 3), (False, 0)])
def test_first_and_later_points_have_the_selected_start(option, clears):
    # GOAL033:capability_ids:items:R13
    script = Script("26.124")
    if option is None:
        build_steady_sweep(_points(), script)
    else:
        build_steady_sweep(_points(), script, cold=option)
    lines = script.render().splitlines()
    starts = [i for i, line in enumerate(lines) if line == "START_SOLVER"]
    resets = [i for i, line in enumerate(lines) if line == "CLEAR_SOLUTION"]
    assert len(starts) == 3
    assert len(resets) == clears
    if clears:
        previous = -1
        for start, reset in zip(starts, resets, strict=True):
            assert previous < reset < start
            previous = start
