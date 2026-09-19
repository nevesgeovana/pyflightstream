"""F05: BL fluid parameters follow the manual of the run's build.

SRC-750 and SRC-751 p.352 list all six for both fluid plots and surface
probes. SRC-003 p.347 has only the eight non-BL fluid parameters.
"""

import pytest

from pyflightstream.cases import CampaignConfigError, SimCase, SweepAxis
from pyflightstream.cases.workflows import _pproc_probes
from pyflightstream.script import CommandArgumentError, Script
from pyflightstream.workspace.inputs import resolve_pproc

BL_PARAMETERS = (
    "BL_MOMENTUM_THICKNESS",
    "BL_DISPLACEMENT_THICKNESS",
    "BL_TOTAL_THICKNESS",
    "BL_SHAPE_FACTOR",
    "BL_SKIN_FRICTION",
    "BL_TRANSITION_MARKER",
)


def probe_case(tmp_path, parameter):
    directory = tmp_path / "pproc"
    directory.mkdir(exist_ok=True)
    (directory / "p900.toml").write_text(
        f'[[probes]]\nframe = "MRP"\nparameters = ["{parameter}"]\npoints = 2\n'
        "[[probes.lines]]\nstart = [0, 0, 0]\nend = [1, 0, 0]\n",
        encoding="utf-8",
        newline="\n",
    )
    return SimCase(
        sim_id="9001",
        aircraft="Wing",
        recipe="unsteady",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        pproc=resolve_pproc(tmp_path, "p900"),
    )


@pytest.mark.parametrize("parameter", BL_PARAMETERS)
@pytest.mark.parametrize("build", ["26.121", "26.122", "26.123", "26.124"])
def test_pproc_accepts_documented_boundary_layer_parameter(tmp_path, parameter, build):
    case = probe_case(tmp_path, parameter)
    script = Script(build)
    _pproc_probes(case, script, {"MRP": 1}, unsteady=True, analysis=False)
    rendered = script.render()
    assert rendered.count("UNSTEADY_SOLVER_NEW_FLUID_PLOT\n") == 2
    assert rendered.count(f"PARAMETER {parameter}\n") == 2
    assert f"NAME {parameter}1\nVERTEX 0.0 0.0 0.0\n" in rendered
    assert f"NAME {parameter}2\nVERTEX 1.0 0.0 0.0\n" in rendered


@pytest.mark.parametrize("parameter", BL_PARAMETERS)
def test_pproc_refuses_undocumented_parameter_naming_variable_and_build(tmp_path, parameter):
    case = probe_case(tmp_path, parameter)
    script = Script("26.120")
    with pytest.raises((CampaignConfigError, CommandArgumentError)) as raised:
        _pproc_probes(case, script, {"MRP": 1}, unsteady=True, analysis=False)
    assert parameter in str(raised.value)
    assert "26.120" in str(raised.value)
    assert "UNSTEADY_SOLVER_NEW_FLUID_PLOT" in str(raised.value)
    assert not script.render().strip()
