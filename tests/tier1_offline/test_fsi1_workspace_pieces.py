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
from pyflightstream.cases.setup_surfaces import emit_setup_surfaces
from pyflightstream.cases.workflows import build_script
from pyflightstream.script import Script
from tests.tier1_offline.test_aeroelastic_typed_setup import coupled_case
from tests.tier1_offline.test_g06_actuator_disc import _lines
from tests.tier1_offline.test_workflows import steady_case, unsteady_case

# --------------------------------------------------------------------------
# FSI-GUARD: which workflows accept FSI in this release.


def test_unsteady_rotor_with_fsi_is_refused_as_in_debug(tmp_path):
    # P0300-FSI-GUARD
    case = coupled_case(tmp_path)
    script = Script("26.124")
    with pytest.raises(CampaignConfigError) as refused:
        build_script(case, script)
    assert (
        "FSI on unsteady_rotor is still in debug (the morph is applied "
        "to the un-rotated blade, reported to the vendor)."
    ) in str(refused.value)
    assert "AEROELASTIC" not in script.render()
    assert "fsi_callback.py" not in script.pending_input_files


@pytest.mark.requirement("FR-169")
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


@pytest.mark.requirement("FR-168")
def test_every_workflow_states_its_fsi_state_and_qsteady_rotor_accepts_it():
    from pyflightstream.cases.workflows import WORKFLOWS

    # Every registered workflow is named in the table, so FSI on a new one
    # is a decision there and not an accident of the lookup.
    assert set(WORKFLOWS) <= set(ws.FSI_WORKFLOW_STATE)
    assert ws.fsi_workflow_refusal("unsteady_rotor") == ws.FSI_ROTOR_IN_DEBUG
    # THE REQUIREMENT CHANGED, by the owner (2026-09-29, GOAL-035): FSI on a
    # qsteady_rotor sector is wired in 0.30.0 ("no qsteady_rotor, o solver
    # estrutural tem que aplicar as cargas centrifugas"); the table accepts
    # it and the builder refuses the wheel (test_goal035_qsteady_completion).
    assert ws.fsi_workflow_refusal("qsteady_rotor") is None
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
    # P0300-FSI1-SURFACE-ID
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
    # P0300-FSI1-SURFACE-ID
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
    # P0300-FSI1-NODE-FRAME
    saved = _saved()
    patched = ws.patch_structural_node_frame(saved, frame, node_count=3)
    field = saved.index(b"1,0,0,3,1")
    assert patched[:field] == saved[:field]
    assert patched[field:].startswith(f"{frame},0,0,3,1\r\n".encode())
    assert patched[field + len(str(frame)) :] == saved[field + 1 :]
    if frame < 10:
        assert [i for i in range(len(saved)) if saved[i] != patched[i]] == [field]


@pytest.mark.parametrize(
    "saved, count, match",
    [
        (_saved(), 48, "not the node block"),
        (_saved(node_block=b"C:\\elsewhere"), 3, "not the node block"),
        (_saved(blocks=2), 3, "2 aeroelastic blocks"),
        (_saved(blocks=0), 3, "0 aeroelastic blocks"),
    ],
    ids=["other-count", "not-the-node-block", "two-blocks", "no-block"],
)
def test_the_frame_patch_refuses_a_line_that_is_not_the_node_block(saved, count, match):
    # P0300-FSI1-NODE-FRAME
    with pytest.raises(CampaignConfigError, match=match):
        ws.patch_structural_node_frame(saved, 5, node_count=count)


# --------------------------------------------------------------------------
# FSI-1 item 4: the morphing kernel of a beam line.


@pytest.mark.requirement("FR-171")
def test_the_beam_line_kernel_is_emitted_where_the_row_states_none(tmp_path):
    # P0300-FSI1-BEAM-KERNEL
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
    # P0300-FSI1-EXPORT-TIMING
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
    # P0300-FSI1-STEADY-WAIT
    running = (
        'Executed FSI command: "python" "fsi_callback.py"\n'
        "Aeroelastic solver residual for FSI iteration-1 is  9.3750000E-1\n"
    )
    assert not ws.steady_aeroelastic_finished(running)
    assert ws.steady_aeroelastic_finished(running + "Aeroelastic solver run time: .02 minutes.\n")


ARMS = {
    "OBJ b (Body, Blade1, Blade2)": (
        ".obj",
        [(2, "Body"), (3, "Blade1"), (4, "Blade2")],
        [(3, "Blade1"), (4, "Blade2")],
    ),
    "OBJ c (Spinner, Rotor_A, Zeta)": (
        ".obj",
        [(2, "Spinner"), (3, "Rotor_A"), (4, "Zeta")],
        [(3, "Rotor_A"), (4, "Zeta")],
    ),
    "STL b (Body, Blade1, Blade2)": (
        ".stl",
        [(1, "Body"), (2, "Blade1"), (3, "Blade2")],
        [(2, "Blade1"), (3, "Blade2")],
    ),
    "STL c (Spinner, Rotor_A, Zeta)": (
        ".stl",
        [(1, "Spinner"), (2, "Rotor_A"), (3, "Zeta")],
        [(2, "Rotor_A"), (3, "Zeta")],
    ),
}


def _deleted_case(tmp_path, suffix, first):
    case = coupled_case(tmp_path).model_copy(update={"fsi": None, "geometry": f"mesh{suffix}"})
    solver = case.solver.model_copy(update={"delete_surfaces": [first]})
    return case.model_copy(update={"solver": solver})


def _script_after_the_deletion(case, names):
    script = Script("26.124")
    script.declare_existing(boundaries={name: i for i, name in enumerate(names, start=1)})
    script.boundary_inventory = tuple(names)
    emit_setup_surfaces(script, case)
    return script


@pytest.mark.parametrize("arm", sorted(ARMS))
def test_p0420_the_survivors_get_the_id_the_saved_mesh_keeps(tmp_path, arm):
    """PFS-2119.016: the ID of each survivor, cited by name or by its tree position now."""
    suffix, before, after = ARMS[arm]
    names = [name for _, name in before]
    case = _deleted_case(tmp_path, suffix, names[0])
    script = _script_after_the_deletion(case, names)
    survivors = [name for _, name in after]
    kept = [identity for identity, _ in after]
    assert ws.aeroelastic_surface_ids(case, script, survivors, context="FSI") == kept
    # Cited by position in the tree the deletion left (1 is the first survivor), the same IDs.
    assert ws.aeroelastic_surface_ids(case, script, [1, 2], context="FSI") == kept


def test_p0420_the_tree_position_plus_the_offset_is_not_the_id_after_a_deletion(tmp_path):
    """PFS-2119.016: the old rule gave Blade1 the ID 2 where the mesh keeps 3 (OBJ)."""
    suffix, before, after = ARMS["OBJ b (Body, Blade1, Blade2)"]
    names = [name for _, name in before]
    case = _deleted_case(tmp_path, suffix, names[0])
    script = _script_after_the_deletion(case, names)
    position = script.resolve_boundary("Blade1")
    assert position + ws.IMPORT_BOUNDARY_ID_OFFSET[suffix] == 2
    assert ws.aeroelastic_surface_ids(case, script, ["Blade1"], context="FSI") == [3]


def test_p0420_without_a_deletion_the_ids_are_the_position_rule_as_before(tmp_path):
    """PFS-2119.016 control: the undeleted route is untouched."""
    case = coupled_case(tmp_path).model_copy(update={"fsi": None, "geometry": "mesh.obj"})
    script = Script("26.124")
    script.declare_existing(boundaries={"Body": 1, "Blade1": 2, "Blade2": 3})
    assert ws.aeroelastic_surface_ids(case, script, ["Blade1", "Blade2"], context="FSI") == [3, 4]


@pytest.mark.parametrize("frame", [2.5, 3.0, True, "2"])
def test_p0430_f1301_the_frame_patch_refuses_a_non_integer_index(frame):
    with pytest.raises(CampaignConfigError, match="an integer"):
        ws.patch_structural_node_frame(_saved(), frame, node_count=3)


def test_p0430_f1302_a_truncated_aeroelastic_block_is_a_campaign_error():
    saved = _saved()
    cut = saved[: saved.index(b"$AEROELASTIC_START$") + len(b"$AEROELASTIC_START$\r\n1,0,1")]
    with pytest.raises(CampaignConfigError, match="truncated"):
        ws.patch_structural_node_frame(cut, 5, node_count=3)


def test_p0430_f1303_the_steady_order_check_ignores_comment_lines_as_the_detector_does():
    text = "EXECUTE_AEROELASTIC_ANALYSIS\n# a trailing note\n"
    assert ws.is_steady_aeroelastic_script(text)
    ws.refuse_lines_after_steady_analysis(text)


@pytest.mark.parametrize("rpm", [float("nan"), float("inf")])
def test_p0430_f044_a_non_finite_row_speed_is_refused_for_the_sector_structure(tmp_path, rpm):
    case = coupled_case(tmp_path)
    with pytest.raises(CampaignConfigError, match="finite"):
        ws.quasi_steady_fsi_config(case, rpm=rpm)
