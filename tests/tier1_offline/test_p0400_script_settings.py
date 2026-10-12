"""P0400 script lane: the settings helpers, their snapshot, and the relaxed trailing edge.

One test per review finding, each named for its planning node: P0400-ALTUNITS
(PFS-2085.019), P0400-WAKEX (PFS-2097.010, PFS-2104.024), P0400-FREESTREAM
(PFS-2097.016), P0400-ENUMSNAP (PFS-2103.012), P0400-FLUSH (PFS-2104.045),
P0400-REFREQUEST (PFS-2104.046), P0400-SNAPMERGE (PFS-2103.011), P0400-UNSTEADYSNAP
(PFS-2103.037) and P0400-MINCP (PFS-2104.023).
"""

from __future__ import annotations

import math

import pytest

from pyflightstream.script import CommandArgumentError, Script, ScriptOrderError, helpers
from pyflightstream.script.solver_setup import build_setup

FLUID = {
    "density": 1.2,
    "pressure": 101325.0,
    "temperature": 288.15,
    "viscosity": 1.8e-5,
    "specific_heat_ratio": 1.4,
}


# --- P0400-ALTUNITS (PFS-2085.019) ------------------------------------------


def test_p0400_altunits_an_altitude_unit_without_an_altitude_is_refused():
    """P0400-ALTUNITS (PFS-2085.019): the helper preserves its declared contract."""
    script = Script(version="26.124")
    with pytest.raises(CommandArgumentError, match="has no meaning"):
        helpers.atmosphere(script, altitude_units="FEET", **FLUID)
    assert script.render() == "\n"
    helpers.atmosphere(script, **FLUID)
    assert script.render().startswith("FLUID_PROPERTIES")


# --- P0400-WAKEX (PFS-2097.010, PFS-2104.024) --------------------------------


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, "nan", "inf", "banana"])
def test_p0400_wakex_a_wake_termination_that_is_not_a_finite_number_is_refused(value):
    """P0400-WAKEX (PFS-2097.010, PFS-2104.024): the helper preserves its declared contract."""
    script = Script(version="26.124")
    with pytest.raises(CommandArgumentError, match="wake_termination_x"):
        helpers.initialize_solver(script, wake_termination_x=value)
    assert script.render() == "\n"


@pytest.mark.parametrize(
    ("value", "token"),
    [
        ("default", "DEFAULT"),
        ("DEFAULT", "DEFAULT"),
        (12.5, "12.5"),
        (1e-05, "0.00001"),
        ("3", "3"),
    ],
)
def test_p0400_wakex_a_finite_or_default_wake_termination_renders_one_token(value, token):
    """P0400-WAKEX (PFS-2097.010, PFS-2104.024): the helper preserves its declared contract."""
    script = Script(version="26.124")
    helpers.initialize_solver(script, wake_termination_x=value)
    assert f"WAKE_TERMINATION_X {token}" in script.render().splitlines()


@pytest.mark.parametrize("surfaces", [[], [(-1, True)]])
def test_p0400_wakex_an_empty_or_all_form_per_surface_list_is_refused(surfaces):
    """P0400-WAKEX (PFS-2097.010, PFS-2104.024): the helper preserves its declared contract."""
    script = Script(version="26.124")
    script.declare_existing(boundaries=3)
    with pytest.raises(CommandArgumentError, match="surfaces"):
        helpers.initialize_solver(script, surfaces=surfaces)
    assert script.render() == "\n"


# --- P0400-FREESTREAM (PFS-2097.016) ----------------------------------------


def test_p0400_freestream_an_unknown_kind_is_refused_by_name():
    """P0400-FREESTREAM (PFS-2097.016): the helper preserves its declared contract."""
    script = Script(version="26.124")
    with pytest.raises(CommandArgumentError) as refused:
        helpers.free_stream(script, "ROTATING", frame=2, axis="X", rpm=900.0)
    message = str(refused.value)
    assert "'ROTATING'" in message
    assert all(kind in message for kind in ("CONSTANT", "ROTATION", "CUSTOM"))
    assert "takes no further input" not in message


# --- P0400-ENUMSNAP (PFS-2103.012) ------------------------------------------


def test_p0400_enumsnap_the_snapshot_records_the_member_the_script_wrote():
    """P0400-ENUMSNAP (PFS-2103.012): the helper preserves its declared contract."""
    script = Script(version="25.000")
    setup = helpers.solver_settings(script, solver_model="incompressible")
    assert "SET_SOLVER_MODEL INCOMPRESSIBLE" in script.render().splitlines()
    assert setup.flags["SET_SOLVER_MODEL"].value == "INCOMPRESSIBLE"


# --- P0400-FLUSH (PFS-2104.045) ---------------------------------------------


def test_p0400_flush_a_refused_flush_keeps_the_selection_pending():
    """P0400-FLUSH (PFS-2104.045): the helper preserves its declared contract."""
    script = Script(version="26.124")
    script.declare_existing(boundaries=2)
    helpers.solver_settings(script, vorticity_drag_boundaries=[1])
    script.emit("START_SOLVER")
    script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", "first.txt")
    with pytest.raises(ScriptOrderError):
        helpers.export_results(script, spreadsheet="second.txt")
    assert script._pending_vorticity == [1]


# --- P0400-REFREQUEST (PFS-2104.046) ----------------------------------------


@pytest.mark.parametrize("value", ["DISABLE", "false", "ENABLE", 0, 1, None])
def test_p0400_refrequest_a_non_bool_request_is_refused(value):
    """P0400-REFREQUEST (PFS-2104.046): the helper preserves its declared contract."""
    script = Script(version="26.124")
    with pytest.raises(CommandArgumentError, match="Pass True to request it"):
        helpers.solver_settings(script, disable_ref_velocity=value)
    assert "DISABLE_SOLVER_REF_VELOCITY" not in script.render()


def test_p0400_refrequest_the_snapshot_refuses_a_non_bool_request_too():
    """P0400-REFREQUEST (PFS-2104.046): the helper preserves its declared contract."""
    with pytest.raises(CommandArgumentError, match="Pass True to request it"):
        build_setup(
            version="26.124",
            passed={"disable_ref_velocity": "DISABLE"},
            minimum_cp_default_emitted=False,
        )


def test_p0400_refrequest_true_requests_it():
    """P0400-REFREQUEST (PFS-2104.046): the helper preserves its declared contract."""
    script = Script(version="26.124")
    setup = helpers.solver_settings(script, disable_ref_velocity=True)
    assert "DISABLE_SOLVER_REF_VELOCITY" in script.render().splitlines()
    assert setup.flags["DISABLE_SOLVER_REF_VELOCITY"].provenance == "explicit"


# --- P0400-SNAPMERGE (PFS-2103.011) -----------------------------------------


def test_p0400_snapmerge_a_second_call_keeps_the_flags_the_first_one_wrote():
    """P0400-SNAPMERGE (PFS-2103.011): the helper preserves its declared contract."""
    script = Script(version="26.124")
    helpers.solver_settings(script, velocity=30.0, iterations=500, disable_ref_velocity=True)
    setup = helpers.solver_settings(script, aoa=5.0)
    for command, value in (("SOLVER_SET_VELOCITY", 30.0), ("SOLVER_SET_ITERATIONS", 500)):
        record = setup.flags[command]
        assert (record.provenance, record.value, record.emitted) == ("explicit", value, True)
    assert setup.flags["DISABLE_SOLVER_REF_VELOCITY"].emitted is True
    assert setup.flags["SOLVER_SET_AOA"].value == 5.0


def test_p0400_snapmerge_a_keyword_the_second_call_passes_is_its_own_record():
    """P0400-SNAPMERGE (PFS-2103.011): the helper preserves its declared contract."""
    script = Script(version="26.124")
    script.declare_existing(boundaries=2)
    helpers.solver_settings(script, viscous_excluded=[1])
    setup = helpers.solver_settings(script, viscous_excluded=[])
    assert setup.flags["SET_VISCOUS_EXCLUDED_BOUNDARIES"].provenance != "explicit"
    assert setup.flags["DELETE_VISCOUS_EXCLUDED_BOUNDARIES"].provenance == "explicit"


# --- P0400-UNSTEADYSNAP (PFS-2103.037) --------------------------------------


def test_p0400_unsteadysnap_the_regime_unsteady_solver_wrote_is_recorded():
    """P0400-UNSTEADYSNAP (PFS-2103.037): the helper preserves its declared contract."""
    script = Script(version="26.124")
    helpers.unsteady_solver(script, time_iterations=120, delta_time=0.01)
    setup = helpers.solver_settings(script, velocity=10.0)
    record = setup.flags["SET_SOLVER_UNSTEADY"]
    assert (record.provenance, record.emitted) == ("explicit", True)
    assert record.value == {"time_iterations": 120, "delta_time": 0.01}


def test_p0400_unsteadysnap_an_existing_snapshot_is_restamped():
    """P0400-UNSTEADYSNAP (PFS-2103.037): the helper preserves its declared contract."""
    script = Script(version="26.124")
    helpers.solver_settings(script, mode="STEADY", velocity=10.0)
    helpers.unsteady_solver(script, time_iterations=120, delta_time=0.01)
    assert script.solver_setup is not None
    record = script.solver_setup.flags["SET_SOLVER_UNSTEADY"]
    assert (record.provenance, record.emitted) == ("explicit", True)
    assert script.solver_setup.flags["SET_SOLVER_STEADY"].provenance != "explicit"


# --- P0400-MINCP (PFS-2104.023) ---------------------------------------------


def test_p0400_mincp_a_second_call_does_not_write_the_default_over_an_explicit_value():
    """P0400-MINCP (PFS-2104.023): the helper preserves its declared contract."""
    script = Script(version="26.124")
    helpers.solver_settings(script, minimum_cp=-3.0, aoa=0.0)
    setup = helpers.solver_settings(script, aoa=4.0)
    lines = [line for line in script.render().splitlines() if line.startswith("SOLVER_MINIMUM_CP")]
    assert lines == ["SOLVER_MINIMUM_CP -3.0"]
    record = setup.flags["SOLVER_MINIMUM_CP"]
    assert (record.provenance, record.value, record.emitted) == ("explicit", -3.0, True)


def test_p0400_mincp_the_library_default_is_written_once():
    """P0400-MINCP (PFS-2104.023): the helper preserves its declared contract."""
    script = Script(version="26.124")
    helpers.solver_settings(script, aoa=0.0)
    setup = helpers.solver_settings(script, aoa=4.0)
    assert script.render().count("SOLVER_MINIMUM_CP") == 1
    record = setup.flags["SOLVER_MINIMUM_CP"]
    assert (record.provenance, record.emitted) == ("default", True)


def test_p0400_mincp_a_limiter_emitted_by_hand_is_not_overwritten_or_guessed():
    """P0400-MINCP (PFS-2104.023): the helper preserves its declared contract."""
    script = Script(version="26.124")
    script.emit("SOLVER_MINIMUM_CP", -7.0)
    setup = helpers.solver_settings(script, aoa=4.0)
    assert script.render().count("SOLVER_MINIMUM_CP") == 1
    record = setup.flags["SOLVER_MINIMUM_CP"]
    assert (record.provenance, record.value, record.emitted) == ("unknown", None, True)
