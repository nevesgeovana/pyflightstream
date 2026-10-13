"""P0400 script lane: the curated helpers.

One test per review finding, each named for its planning node: P0400-VTKVARS
(PFS-2085.009), P0400-VTKWAKE (PFS-2104.047), P0400-EMPTYSEL (PFS-2085.018),
P0400-AXISCASE (PFS-2095.055), P0400-ROTORUNIT (PFS-2088.010), P0400-WAKEUNITS
(PFS-2104.027), P0400-WAKEX (PFS-2104.024, the sweep axes) and P0400-EXPORTS
(PFS-2093.004, PFS-2093.011).
"""

from __future__ import annotations

import warnings

import pytest

from pyflightstream._errors import PyflightstreamWarning
from pyflightstream.script import CommandArgumentError, Script, helpers


def _rotor_frame(script: Script) -> int:
    return helpers.coordinate_frame(
        script, name="HUB", origin=(0.0, 0.0, 0.0), x_axis=(1, 0, 0), y_axis=(0, 1, 0)
    )


# --- P0400-VTKVARS (PFS-2085.009) and P0400-VTKWAKE (PFS-2104.047) -----------


@pytest.mark.parametrize("variables", ["CP", "X"])
def test_p0400_vtkvars_a_bare_variable_string_is_refused(variables):
    """P0400-VTKVARS (PFS-2085.009): the helper preserves its declared contract."""
    script = Script(version="26.124")
    with pytest.raises(CommandArgumentError, match=r"for example \["):
        helpers.export_results(script, vtk="a.vtk", vtk_variables=variables)
    assert script.render() == "\n"


def test_p0400_vtkwake_the_wake_flag_without_a_variable_selection_is_refused():
    """P0400-VTKWAKE (PFS-2104.047): the helper preserves its declared contract."""
    script = Script(version="26.124")
    with pytest.raises(CommandArgumentError, match="vtk_variables"):
        helpers.export_results(script, vtk="a.vtk", vtk_wake=True)
    assert script.render() == "\n"
    helpers.export_results(script, vtk="a.vtk", vtk_variables="all", vtk_wake=True)
    assert "SET_VTK_EXPORT_VARIABLES -1 ENABLE" in script.render().splitlines()


# --- P0400-EMPTYSEL (PFS-2085.018) ------------------------------------------


@pytest.mark.parametrize("argument", ["boundaries", "moving_frames"])
def test_p0400_emptysel_rotary_motion_refuses_an_empty_selection(argument):
    """P0400-EMPTYSEL (PFS-2085.018): the helper preserves its declared contract."""
    script = Script(version="26.124")
    frame = _rotor_frame(script)
    before = script.render()
    with pytest.raises(CommandArgumentError, match="empty sequence"):
        helpers.rotary_motion(script, frame=frame, axis="X", rpm=1200.0, **{argument: []})
    assert script.render() == before


def test_p0400_emptysel_analysis_setup_refuses_an_empty_selection():
    """P0400-EMPTYSEL (PFS-2085.018): the helper preserves its declared contract."""
    script = Script(version="26.124")
    with pytest.raises(CommandArgumentError, match="empty sequence"):
        helpers.analysis_setup(script, boundaries=[])
    assert script.render() == "\n"


# --- P0400-AXISCASE (PFS-2095.055) ------------------------------------------


@pytest.mark.parametrize("version", ["26.000", "26.124"])
def test_p0400_axiscase_a_lowercase_axis_is_read_on_every_vocabulary(version):
    """P0400-AXISCASE (PFS-2095.055): the helper preserves its declared contract."""
    lower, upper = Script(version=version), Script(version=version)
    for script, axis in ((lower, "z"), (upper, "Z")):
        helpers.rotary_motion(script, frame=_rotor_frame(script), axis=axis, rpm=600.0)
    assert lower.render() == upper.render()


# --- P0400-ROTORUNIT (PFS-2088.010) -----------------------------------------


def test_p0400_rotorunit_a_rotor_on_the_unmarked_build_is_refused_citing_the_report():
    """P0400-ROTORUNIT (PFS-2088.010, FR-101): a rotor row on 26.100 is refused by name."""
    script = Script(version="26.100")
    frame = _rotor_frame(script)
    before = script.render()
    with pytest.raises(CommandArgumentError, match="RPT-051") as caught:
        helpers.rotary_motion(script, frame=frame, axis="X", rpm=1200.0)
    assert "9.55" in str(caught.value)
    assert "unsteady_rotor" in str(caught.value)
    assert script.render() == before


def test_p0400_rotorunit_a_rotor_on_a_rotary_build_does_not_warn():
    """P0400-ROTORUNIT (PFS-2088.010): the helper preserves its declared contract."""
    script = Script(version="26.124")
    frame = _rotor_frame(script)
    with warnings.catch_warnings():
        warnings.simplefilter("error", PyflightstreamWarning)
        helpers.rotary_motion(script, frame=frame, axis="X", rpm=1200.0)


# --- P0400-WAKEUNITS (PFS-2104.027) -----------------------------------------


def test_p0400_wakeunits_points_in_another_unit_are_converted_to_the_simulations():
    """P0400-WAKEUNITS (PFS-2104.027): the helper preserves its declared contract."""
    script = Script(version="26.124")
    script.emit("SET_SIMULATION_LENGTH_UNITS", "MILLIMETER")
    helpers.mark_wake_edges(
        script,
        edge_type="STANDARD",
        tolerance=0.1,
        units="METER",
        node_file="wing.wake_nodes.txt",
        midpoints=[(1.0, -3.75, 0.0)],
    )
    assert "IMPORT_WAKE_EDGES_FROM_FILE STANDARD 0.1 MILLIMETER" in script.render().splitlines()
    rows = script.pending_input_files["wing.wake_nodes.txt"].splitlines()
    assert rows[-1] == "1000.0,-3750.0,0.0"


def test_p0400_wakeunits_points_in_the_simulations_unit_are_written_as_given():
    """P0400-WAKEUNITS (PFS-2104.027): the helper preserves its declared contract."""
    script = Script(version="26.124")
    script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
    helpers.mark_wake_edges(
        script,
        edge_type="STANDARD",
        tolerance=0.0001,
        units="METER",
        node_file="wing.wake_nodes.txt",
        midpoints=[(1.0, -3.75, 0.0)],
    )
    assert "IMPORT_WAKE_EDGES_FROM_FILE STANDARD 0.0001 METER" in script.render().splitlines()
    assert script.pending_input_files["wing.wake_nodes.txt"].splitlines()[-1] == "1.0,-3.75,0.0"


@pytest.mark.parametrize("axis", ["aoa", "beta"])
def test_p0400_wakex_an_empty_sweep_axis_is_refused(axis):
    """P0400-WAKEX (PFS-2097.010, PFS-2104.024): the helper preserves its declared contract."""
    script = Script(version="26.124")
    with pytest.raises(CommandArgumentError, match="empty sequence"):
        helpers.sweep(script, **{axis: []}, start=False)
    assert script.render() == "\n"


# --- P0400-EXPORTS (PFS-2093.004, PFS-2093.011) ------------------------------


def test_p0400_exports_export_results_refuses_a_path_the_script_exports_to():
    """P0400-EXPORTS (PFS-2093.004, PFS-2093.011): the helper preserves its declared contract."""
    script = Script(version="26.124")
    helpers.export_results(script, spreadsheet="out/loads.txt")
    with pytest.raises(CommandArgumentError, match="already exports to") as refused:
        helpers.export_results(script, tecplot="out/sub/../LOADS.txt")
    assert "from export_results" in str(refused.value)
    assert script.render().count("EXPORT_SOLVER_ANALYSIS_TECPLOT") == 0


def test_p0400_exports_one_call_naming_one_file_twice_writes_nothing():
    """P0400-EXPORTS (PFS-2093.004, PFS-2093.011): the helper preserves its declared contract."""
    script = Script(version="26.124")
    with pytest.raises(CommandArgumentError, match="are one file"):
        helpers.export_results(script, spreadsheet="a.txt", tecplot="./A.txt")
    assert script.render() == "\n"


def test_p0400_exports_the_two_export_helpers_share_one_key():
    """P0400-EXPORTS (PFS-2093.004, PFS-2093.011): export_probes keyed the raw path; one file
    through a parent folder or a case change was two keys.
    """
    script = Script(version="26.124")
    helpers.export_probes(script, "probes.txt", update=False)
    with pytest.raises(CommandArgumentError, match="from export_probes"):
        helpers.export_probes(script, "sub/../PROBES.txt", update=False)
    with pytest.raises(CommandArgumentError, match="from export_probes"):
        helpers.export_results(script, spreadsheet="Probes.txt")
    assert script.render().count("EXPORT_") == 1


def test_p0400_exports_an_action_script_and_an_input_file_never_share_a_path():
    """P0400-EXPORTS (PFS-2093.004, PFS-2093.011): the helper preserves its declared contract."""
    script = Script(version="26.124")
    helpers.mark_wake_edges(
        script,
        edge_type="STANDARD",
        tolerance=0.0001,
        units="METER",
        node_file="shared.txt",
        midpoints=[(1.0, 0.0, 0.0)],
    )
    with pytest.raises(CommandArgumentError, match="input file"):
        helpers.unsteady_action(
            script, name="post", kind="SCRIPT", filename="SHARED.txt", action_script="X\n"
        )
    other = Script(version="26.124")
    helpers.unsteady_action(
        other, name="post", kind="SCRIPT", filename="shared.txt", action_script="X\n"
    )
    with pytest.raises(CommandArgumentError, match="action script"):
        helpers.mark_wake_edges(
            other,
            edge_type="STANDARD",
            tolerance=0.0001,
            units="METER",
            node_file="shared.txt",
            midpoints=[(1.0, 0.0, 0.0)],
        )


def test_p0400_exports_direct_commands_share_the_helpers_register():
    """P0400-EXPORTS (PFS-2093.011): every EXPORT path participates at emit."""
    script = Script("26.124")
    script.emit("EXPORT_SOLVER_ANALYSIS_SPREADSHEET", "loads.txt")
    before = script.render()
    with pytest.raises(CommandArgumentError, match="already exports to"):
        script.emit("EXPORT_SOLVER_ANALYSIS_TECPLOT", "sub/../LOADS.txt")
    with pytest.raises(CommandArgumentError, match="already exports to"):
        helpers.export_probes(script, "./Loads.txt")
    assert script.render() == before


@pytest.mark.parametrize("workflow", ["unsteady_rotor", "qsteady_rotor", "steady"])
def test_p0400_rotorunit_workflow_rehearsal_refuses_speed_rows_before_emission(workflow):
    """P0400-ROTORUNIT (PFS-2088.010): plan rehearsal cannot interpret an unproved unit."""
    from pyflightstream.cases.workflows import build_script
    from tests.tier1_offline.test_workflows import qsteady_case, rotor_case, steady_case

    factories = {"unsteady_rotor": rotor_case, "qsteady_rotor": qsteady_case, "steady": steady_case}
    case = factories[workflow]()
    if workflow == "steady":
        case = case.model_copy(update={"variables": {**case.variables, "RPM": "1200"}})
    script = Script("26.100")
    with pytest.raises(CommandArgumentError, match="RPT-051"):
        build_script(case, script)
    assert script.render() == "\n"
