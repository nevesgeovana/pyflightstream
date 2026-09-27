# GEOVERSE_HEADER_BEGIN
# file_version: "1.0.1"
# artifact_id: setup-standard-completeness-tests
# last_modified_at: 2026-09-27T19:56:12.025Z
# last_modified_by: {provider: OpenAI, product: Codex, model: GPT-6, role: primary-agent}
# dependencies: [pytest; pyflightstream]
# authority: pyflightstream
# status: draft
# confidentiality: public
# change_summary: Identify measured completeness and one-setting obligations for release evidence.
# revision_source: git
# GEOVERSE_HEADER_END
"""Behavioral acceptance for owner-requested complete and comparable setup files."""

import tomllib

import pytest

from pyflightstream.cases import SimCase, SolverSettings, SweepAxis
from pyflightstream.cases.workflows import _refuse_the_loads_selections_on_a_march, _settings
from pyflightstream.script import Script
from pyflightstream.workspace.setup_standards import (
    render_guidelines,
    render_standard,
    setup_standards,
)


@pytest.mark.parametrize("version", ["26.123", "26.124"])
def test_baseline_explicitly_sets_operational_boolean_controls(version):
    """GOAL033:standards:checks:complete_explicit_settings"""
    standard = next(s for s in setup_standards() if s.code == "s900")
    parsed = tomllib.loads(render_standard(standard, version))
    expected = {
        "viscous_coupling": False,
        "forced_iterations": False,
        "laminar_separation": False,
        "print_rotor_induced_velocities": False,
        "adaptive_field_grid_refinement": False,
        "wake_on_wake_induction": True,
        "mesh_induced_wake_velocity": True,
        "additional_wake_relaxation": False,
        "unsteady_pressure_and_kutta": True,
        "load_solver_initialization": False,
        "inviscid_loads": False,
    }
    for key, value in expected.items():
        assert parsed.get(key) is value, key
    case = SimCase(
        sim_id="9001",
        aircraft="Wing",
        recipe="steady",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        point={"alpha": 0.0},
        variables={"VELOCITY": "30"},
        outputs=["loads.txt"],
        solver=SolverSettings.model_validate(parsed),
    )
    script = Script(version)
    _settings(case, script)
    assert script.solver_setup.flags["SET_WAKE_ON_WAKE_INDUCTION"].value is True
    assert script.solver_setup.flags["SET_WAKE_ON_WAKE_INDUCTION"].provenance == "explicit"


def test_wake_on_wake_experiment_actually_disables_baseline_enabled_flag():
    standards = {s.code: s for s in setup_standards()}
    assert standards["s900"].settings["wake_on_wake_induction"] is True
    assert standards["s925"].settings["wake_on_wake_induction"] is False
    assert (
        tomllib.loads(render_standard(standards["s925"], "26.124"))["wake_on_wake_induction"]
        is False
    )


def test_each_study_names_a_baseline_and_changes_one_setting():
    """GOAL033:standards:checks:s9xx_single_flag"""
    standards = {s.code: s for s in setup_standards()}
    for code, standard in standards.items():
        if code < "s910":
            continue
        assert standard.baseline_code in standards, code
        baseline = standards[standard.baseline_code]
        keys = set(standard.settings) | set(baseline.settings)
        changed = [key for key in keys if standard.settings.get(key) != baseline.settings.get(key)]
        assert len(changed) == 1, (code, changed)


@pytest.mark.parametrize("code", ["s902", "s904", "s913", "s925", "s928", "s954"])
def test_unsteady_presets_do_not_inject_even_false_steady_only_load_selection(code):
    standard = next(s for s in setup_standards() if s.code == code)
    text = render_standard(standard, "26.124")
    parsed = tomllib.loads(text)
    assert "inviscid_loads" not in parsed
    assert "inviscid_loads: not applicable" in text
    case = SimCase(
        sim_id="9001",
        aircraft="Rotor",
        recipe="unsteady_rotor",
        sweep=SweepAxis(type="alpha", values=[0.0]),
        solver=SolverSettings.model_validate(parsed),
    )
    _refuse_the_loads_selections_on_a_march(case)


def test_guide_groups_physical_controls_and_explains_unknown_saved_state():
    text = render_guidelines("26.124")
    for heading in [
        "Convergence and execution",
        "Wake transport and induction",
        "Boundary layer and separation",
        "Compressibility and field resolution",
        "Loads, units and saved state",
    ]:
        assert heading in text
    assert "saved simulation" in text
    assert "19.1/L" in text
    assert "[s904](s904.toml)" in text
    assert "Valarezo" in text
