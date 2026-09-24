"""Tier 1: two setup keys for two documented commands, validated by build (0.27.0, G14).

* ``vorticity_lift_model`` -> ``SET_VORTICITY_LIFT_MODEL ENABLE|DISABLE``, every
  run type, before ``INITIALIZE_SOLVER``;
* ``unsteady_viscous_coupling_iteration`` -> ``SET_UNSTEADY_VISCOUS_COUPLING_ITERATION
  <n>``, the unsteady run types only, before ``INITIALIZE_SOLVER``.

Each is validated against the command database for the row's build, so a build
that does not carry the command refuses the row at plan, naming the build. On
26.124 both commands are answered as an unrecognized name (RPT-068), and the
database records that on their 26.124 rows, so a 26.124 row stating either key is
refused naming the report instead of stopping mid-run.
"""

from __future__ import annotations

import warnings

import pytest

from pyflightstream._errors import PyflightstreamError, PyflightstreamWarning
from pyflightstream.cases import CampaignConfigError, SolverSettings
from pyflightstream.cases.workflows import build_script
from pyflightstream.commands import CommandRegistry, Status
from pyflightstream.script import Script
from pyflightstream.workspace.inputs import InputArtifactError
from tests.tier1_offline.test_rel0250_f04_advanced_setup import setup_case
from tests.tier1_offline.test_workflows import rotor_case, steady_case, unsteady_case

RPT068 = "RPT-068_two-documented-setup-commands-are-unrecognized-on-26124"
MAKERS = {"steady": steady_case, "unsteady": unsteady_case, "unsteady_rotor": rotor_case}
LIFT = "SET_VORTICITY_LIFT_MODEL"
COUPLING = "SET_UNSTEADY_VISCOUS_COUPLING_ITERATION"


def _case(tmp_path, workflow: str, body: str):
    """A row of ``workflow`` carrying the solver settings a preset ``body`` resolves to."""
    solver = setup_case(tmp_path, body).solver
    return MAKERS[workflow]().model_copy(update={"solver": solver})


def _render(case, build: str) -> list[str]:
    script = Script(build)
    build_script(case, script)
    return script.render().splitlines()


@pytest.mark.parametrize("workflow", sorted(MAKERS))
@pytest.mark.parametrize(("value", "token"), [("true", "ENABLE"), ("false", "DISABLE")])
def test_g14_vorticity_lift_model_emits_its_command_before_the_solver_is_initialised(
    tmp_path, workflow, value, token
):
    """Once, before INITIALIZE_SOLVER, on a build whose edition documents it (26.123)."""
    lines = _render(_case(tmp_path, workflow, f"vorticity_lift_model = {value}\n"), "26.123")
    assert lines.count(f"{LIFT} {token}") == 1, (workflow, token)
    assert lines.index(f"{LIFT} {token}") < lines.index("INITIALIZE_SOLVER"), workflow


@pytest.mark.parametrize("workflow", ["unsteady", "unsteady_rotor"])
@pytest.mark.parametrize("build", ["25.100", "26.000"])
def test_g14_the_coupling_iteration_emits_on_the_builds_that_document_it(tmp_path, workflow, build):
    """25.100 and 26.000 document the command and render both unsteady run types."""
    body = "unsteady_viscous_coupling_iteration = 20\n"
    lines = _render(_case(tmp_path, workflow, body), build)
    assert lines.count(f"{COUPLING} 20") == 1, (workflow, build)
    assert lines.index(f"{COUPLING} 20") < lines.index("INITIALIZE_SOLVER"), (workflow, build)


@pytest.mark.parametrize("build", ["26.100", "26.120", "26.122", "26.123", "26.124"])
def test_g14_the_coupling_iteration_is_refused_by_name_on_every_build_that_does_not_carry_it(
    tmp_path, build
):
    """Refused at plan, naming the command and the build; on 26.124, naming RPT-068."""
    case = _case(tmp_path, "unsteady", "unsteady_viscous_coupling_iteration = 20\n")
    with pytest.raises(PyflightstreamError) as raised:
        _render(case, build)
    text = str(raised.value)
    assert COUPLING in text and build in text, text
    if build == "26.124":
        assert RPT068 in text, text


@pytest.mark.parametrize("workflow", sorted(MAKERS))
def test_g14_the_vorticity_lift_model_is_refused_on_26124_naming_rpt068(tmp_path, workflow):
    """26.124 answers the name as it answers a name no edition documents (RPT-068)."""
    case = _case(tmp_path, workflow, "vorticity_lift_model = true\n")
    with pytest.raises(PyflightstreamError) as raised:
        _render(case, "26.124")
    text = str(raised.value)
    assert LIFT in text and "26.124" in text and RPT068 in text, text


def test_g14_the_26124_rows_record_the_builds_answer():
    """Both rows removed on 26.124, citing the narrative report of the run by probe_ref."""
    registry = CommandRegistry.load()
    for name in (LIFT, COUPLING):
        row = registry.commands[name].versions["26.124"]
        assert row.status is Status.REMOVED, (name, row.status)
        assert row.probe_ref and RPT068 in row.probe_ref, (name, row.probe_ref)
        assert "unrecognized command" in " ".join((row.note or "").split()), row.note


def test_g14_the_coupling_iteration_on_a_steady_row_is_refused(tmp_path):
    """A steady run has no time step for the viscous coupling to begin at."""
    case = _case(tmp_path, "steady", "unsteady_viscous_coupling_iteration = 20\n")
    with pytest.raises(CampaignConfigError) as raised:
        _render(case, "26.000")
    text = str(raised.value)
    assert "unsteady_viscous_coupling_iteration" in text and "STEADY" in text, text


def test_g14_an_iteration_below_one_is_refused_when_the_preset_is_read(tmp_path):
    with pytest.raises(InputArtifactError, match="greater than or equal to 1"):
        setup_case(tmp_path, "unsteady_viscous_coupling_iteration = 0\n")


def test_g14_a_preset_that_says_nothing_emits_neither(tmp_path):
    """The control, on every run type: neither command, on a build documenting both."""
    for workflow in sorted(MAKERS):
        lines = _render(_case(tmp_path, workflow, "iterations = 250\n"), "26.000")
        stated = [line for line in lines if line.split(" ")[0] in (LIFT, COUPLING)]
        assert stated == [], (workflow, stated)


def test_g14_the_lift_model_beside_kutta_joukowski_lift_warns_at_plan(tmp_path):
    """No edition says what the two do together, so the plan says so and blocks nothing."""
    both = _case(tmp_path, "steady", "vorticity_lift_model = true\nkutta_joukowski_lift = true\n")
    with pytest.warns(PyflightstreamWarning, match="kutta_joukowski_lift") as caught:
        lines = _render(both, "26.123")
    assert any("vorticity_lift_model" in str(w.message) for w in caught), caught
    assert f"{LIFT} ENABLE" in lines
    one = steady_case().model_copy(update={"solver": SolverSettings(vorticity_lift_model=True)})
    with warnings.catch_warnings(record=True) as quiet:
        warnings.simplefilter("always")
        _render(one, "26.123")
    assert not [w for w in quiet if "kutta_joukowski_lift" in str(w.message)], quiet
