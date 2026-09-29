"""Tier 1: the coupled-route pieces of FSI-1 and the FSI-GUARD of 0.30.0.

Each piece is tested on its own. unsteady_rotor is refused while the rotor
morph is in debug; steady and unsteady accept FSI through the fixed-wing
route (FSI-G, ``test_fsig_fixed_wing.py``). The rotor wiring that calls
these pieces is exercised in ``test_aeroelastic_typed_setup.py`` with the
guard opened for that module.
"""

import pytest

from pyflightstream.cases import CampaignConfigError, SolverSettings
from pyflightstream.cases import fsi_workspace as ws
from pyflightstream.cases.workflows import build_script
from pyflightstream.script import Script
from tests.tier1_offline.test_aeroelastic_typed_setup import coupled_case
from tests.tier1_offline.test_g06_actuator_disc import _lines
from tests.tier1_offline.test_workflows import steady_case, unsteady_case

# --------------------------------------------------------------------------
# FSI-GUARD: which workflows accept FSI in this release.


def test_unsteady_rotor_with_fsi_is_refused_as_in_debug(tmp_path):
    case = coupled_case(tmp_path)
    script = Script("26.124")
    with pytest.raises(CampaignConfigError) as refused:
        build_script(case, script)
    assert (
        "FSI on unsteady_rotor is still in debug on this release (the morph is applied "
        "to the un-rotated blade, reported to the vendor)."
    ) in str(refused.value)
    assert "AEROELASTIC" not in script.render()
    assert "fsi_callback.py" not in script.pending_input_files


@pytest.mark.parametrize("make", [steady_case, unsteady_case], ids=["steady", "unsteady"])
def test_fixed_wing_workflows_refuse_a_rotor_blade_configuration(tmp_path, make):
    # THE EXPECTATION CHANGED BECAUSE THE OWNER CHANGED THE REQUIREMENT
    # (2026-09-28, "vamos permitir o FSI para steady, qsteady e unsteady"):
    # steady and unsteady accept FSI through the fixed-wing route, so a row
    # there is no longer refused by the guard. A rotor blade's configuration
    # (no [config.wing]) on them is refused naming what a wing states.
    case = make().model_copy(update={"fsi": coupled_case(tmp_path).fsi})
    with pytest.raises(CampaignConfigError) as refused:
        _lines(case)
    message = str(refused.value)
    assert "is a fixed wing's (FSI-G)" in message
    assert "[config.wing]" in message
    assert ws.fsi_workflow_refusal(make().variables["matrix_workflow"]) is None


def test_every_workflow_states_its_fsi_state_and_qsteady_rotor_is_a_hook():
    from pyflightstream.cases.workflows import WORKFLOWS

    # Every registered workflow is named in the table, so FSI on a new one
    # is a decision there and not an accident of the lookup.
    assert set(WORKFLOWS) <= set(ws.FSI_WORKFLOW_STATE)
    assert ws.fsi_workflow_refusal("unsteady_rotor") == ws.FSI_ROTOR_IN_DEBUG
    assert "qsteady_rotor" in (ws.fsi_workflow_refusal("qsteady_rotor") or "")
    assert "not one of them" in (ws.fsi_workflow_refusal("my_recipe") or "")


def test_no_fsi_row_is_untouched_by_the_guard(tmp_path):
    lines, _ = _lines(coupled_case(tmp_path).model_copy(update={"fsi": None}))
    assert "START_SOLVER" in lines


# --------------------------------------------------------------------------
# FSI-1 item 1: the surface list holds the solver's boundary ID.


def _declared(names):
    script = Script("26.124")
    script.declare_existing(boundaries={name: i for i, name in enumerate(names, start=1)})
    return script


@pytest.mark.parametrize("suffix, offset", [(".obj", 1), (".stl", 0)])
def test_an_imported_blade_gets_the_id_its_motion_gets(tmp_path, suffix, offset):
    # The motion cites the blade by tree position and the solver stores the
    # boundary's ID in its list: 2 for the first boundary of an OBJ import,
    # 1 for an STL one (26.124). The surface list is stored as written, so it
    # must be handed that same ID.
    case = coupled_case(tmp_path).model_copy(update={"fsi": None})
    if suffix == ".stl":
        stl = tmp_path / "blade.stl"
        stl.write_text("solid Blade1\nendsolid Blade1\n")
        case = case.model_copy(update={"geometry": str(stl)})
    lines, script = _lines(case)
    at = next(i for i, line in enumerate(lines) if line.startswith("SET_MOTION_BOUNDARIES"))
    motion_position = int(lines[at + 1])
    motion_id = motion_position + offset
    assert ws.aeroelastic_surface_ids(case, script, ["Blade1"], context="FSI blade") == [motion_id]


def test_ids_follow_the_tree_position_of_every_boundary(tmp_path):
    case = coupled_case(tmp_path)
    script = _declared(["Hub", "Blade1", "Blade2"])
    ids = ws.aeroelastic_surface_ids(case, script, ["Blade1", "Blade2", 1], context="FSI")
    assert ids == [3, 4, 2]


def test_an_unmeasured_numbering_is_refused_not_guessed(tmp_path):
    case = coupled_case(tmp_path).model_copy(update={"geometry": str(tmp_path / "saved.fsm")})
    with pytest.raises(CampaignConfigError, match="not measured"):
        ws.aeroelastic_surface_ids(case, _declared(["Blade1"]), ["Blade1"], context="FSI")


def test_the_id_of_the_last_obj_boundary_is_emitted(tmp_path):
    # The ID of an OBJ import's last boundary is one past the inventory; the
    # command database must not range check it against the tree.
    script = _declared(["Blade1"])
    script.emit("ASSIGN_AEROELASTIC_SURFACES", 1, [2])
    lines = [line for line in script.render().splitlines() if line]
    assert lines[-2:] == ["ASSIGN_AEROELASTIC_SURFACES 1", "2"]


# --------------------------------------------------------------------------
# FSI-1 item 3: the node-block frame field of the saved file.


def _saved(node_block=b"1,0,0,3,1", blocks=1):
    block = (
        b"$AEROELASTIC_START$\r\n"
        b"1,0,1,1,4\r\n"
        b" F, F,28,61\r\n"
        b"C:\\run\r\n"
        b'"python" "fsi_callback.py"\r\n' + node_block + b"\r\n"
        b" 3.2857E-02, 1.7290E-02, 4.1000E-01\r\n"
        b"$AEROELASTIC_END$\r\n"
    )
    return b"$GLOBAL_START$\r\n5\r\n$GLOBAL_END$\r\n" + block * blocks + b"$MESH_START$\r\n"


@pytest.mark.parametrize("frame", [5, 12])
def test_the_frame_patch_changes_exactly_that_field(frame):
    saved = _saved()
    patched = ws.patch_structural_node_frame(saved, frame, node_count=3)
    field = saved.index(b"1,0,0,3,1")
    assert patched[:field] == saved[:field]
    assert patched[field:].startswith(f"{frame},0,0,3,1\r\n".encode())
    assert patched[field + len(str(frame)) :] == saved[field + 1 :]
    if frame < 10:
        assert [i for i in range(len(saved)) if saved[i] != patched[i]] == [field]


@pytest.mark.parametrize(
    "saved, count",
    [
        (_saved(), 48),
        (_saved(node_block=b"C:\\elsewhere"), 3),
        (_saved(blocks=2), 3),
        (_saved(blocks=0), 3),
    ],
    ids=["other-count", "not-the-node-block", "two-blocks", "no-block"],
)
def test_the_frame_patch_refuses_a_line_that_is_not_the_node_block(saved, count):
    with pytest.raises(CampaignConfigError):
        ws.patch_structural_node_frame(saved, 5, node_count=count)


# --------------------------------------------------------------------------
# FSI-1 item 4: the morphing kernel of a beam line.


def test_the_beam_line_kernel_is_emitted_where_the_row_states_none(tmp_path):
    case = coupled_case(tmp_path)
    script = Script("26.124")
    ws.emit_aeroelastic_rbf_type(case, script)
    assert script.render().splitlines()[-1] == "AEROELASTIC_RBF_TYPE MULTI_QUADRATIC"
    assert ws.aeroelastic_rbf_type(case) == "MULTI_QUADRATIC"


def test_a_row_stating_its_kernel_keeps_it(tmp_path):
    case = coupled_case(tmp_path)
    solver = case.solver.model_copy(update={"aeroelastic_rbf_type": "WENDLAND_C2"})
    case = case.model_copy(update={"solver": solver})
    assert isinstance(case.solver, SolverSettings)
    script = Script("26.124")
    ws.emit_aeroelastic_rbf_type(case, script)
    assert "AEROELASTIC_RBF_TYPE" not in script.render()
    assert ws.aeroelastic_rbf_type(case) == "WENDLAND_C2"


# --------------------------------------------------------------------------
# FSI-1 item 5: exports after the structural call, and the steady wait.


def test_deformation_exports_run_in_the_post_script_after_the_loads():
    text = ws.aeroelastic_post_script(
        "26.124",
        surface_exports=[("EXPORT_SOLVER_ANALYSIS_TECPLOT", ("coupling-surface.dat",))],
    )
    lines = [line for line in text.splitlines() if line.strip()]
    loads = lines.index("EXPORT_SURFACE_SECTIONAL_LOADS")
    assert lines[loads + 1] == ws.LOADS_FILE
    tecplot = lines.index("EXPORT_SOLVER_ANALYSIS_TECPLOT")
    assert lines[tecplot + 1] == "coupling-surface.dat"
    assert loads < tecplot


def test_a_line_after_the_steady_analysis_is_refused():
    script = Script("26.124")
    ws.emit_steady_aeroelastic_analysis(script)
    ws.refuse_lines_after_steady_analysis(script.render())
    script.emit("CLOSE_FLIGHTSTREAM")
    with pytest.raises(CampaignConfigError, match="CLOSE_FLIGHTSTREAM"):
        ws.refuse_lines_after_steady_analysis(script.render())
    with pytest.raises(CampaignConfigError, match="must run"):
        ws.refuse_lines_after_steady_analysis("START_SOLVER\n")


def test_the_steady_wait_reads_the_completion_line():
    running = (
        'Executed FSI command: "python" "fsi_callback.py"\n'
        "Aeroelastic solver residual for FSI iteration-1 is  9.3750000E-1\n"
    )
    assert not ws.steady_aeroelastic_finished(running)
    assert ws.steady_aeroelastic_finished(running + "Aeroelastic solver run time: .02 minutes.\n")
