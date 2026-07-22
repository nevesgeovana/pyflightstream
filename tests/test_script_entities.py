"""Tier 1: entity registry, creation labels, and boundary verification."""

import pytest

from pyflightstream.script import (
    CommandArgumentError,
    Script,
    ScriptLabelError,
    ScriptReferenceError,
    helpers,
)


def make_frame(script, label=None):
    return helpers.coordinate_frame(
        script,
        name="Disc frame",
        origin=(1.2, 0.0, 0.0),
        x_axis=(1.0, 0.0, 0.0),
        y_axis=(0.0, 1.0, 0.0),
        label=label,
    )


def test_frame_label_resolves_to_its_index_at_emission():
    script = Script(version="26.12")
    assert make_frame(script, label="disc_frame") == 2
    script.emit("SET_COORDINATE_SYSTEM_ORIGIN", "disc_frame", 1.2, 0.0, 0.0, "METER")
    assert "SET_COORDINATE_SYSTEM_ORIGIN 2 1.2 0.0 0.0 METER" in script.render()


def test_emit_level_label_on_a_creation_command():
    script = Script(version="26.12")
    script.emit("CREATE_NEW_COORDINATE_SYSTEM", label="wake_frame")
    helpers.probes_from_file(script, "C:/probes/lattice.txt", units="METER", frame="wake_frame")
    assert "FRAME 2" in script.render()


def test_actuator_label_creation_and_resolution():
    script = Script(version="26.12")
    make_frame(script, label="disc_frame")
    index = helpers.actuator_disc(
        script,
        "prop right",
        frame="disc_frame",
        axis="X",
        offset=0.0,
        r_tip=0.9,
        r_hub=0.12,
        rpm=2400.0,
        thrust=850.0,
        enable=False,
        label="prop_r",
    )
    assert index == 1
    script.emit("ENABLE_ACTUATOR", "prop_r")
    text = script.render()
    assert "SET_ACTUATOR_AXIS 1 2 X 0.0" in text
    assert "ENABLE_ACTUATOR 1" in text


def test_motion_label_creation_and_resolution():
    script = Script(version="26.12")
    make_frame(script, label="rotor_frame")
    motion_id = helpers.rotary_motion(
        script,
        frame="rotor_frame",
        axis="X",
        rpm=1200.0,
        moving_frames=["rotor_frame"],
        label="main_rotor",
    )
    assert motion_id == 1
    script.emit("SET_MOTION_ROTOR_RPM", "main_rotor", 900.0)
    text = script.render()
    assert "SET_MOTION_COORDINATE_SYSTEM 1 2" in text
    assert "SET_MOTION_MOVING_FRAMES 1 1\n2" in text
    assert "SET_MOTION_ROTOR_RPM 1 900.0" in text


def test_duplicate_label_for_the_same_kind_is_rejected():
    script = Script(version="26.12")
    make_frame(script, label="disc")
    with pytest.raises(ScriptLabelError, match="already names local coordinate system 2"):
        make_frame(script, label="disc")
    # A rejected duplicate must not have emitted the creation command.
    assert script.render().count("CREATE_NEW_COORDINATE_SYSTEM") == 1


def test_duplicate_boundary_label_is_rejected():
    script = Script(version="26.12")
    script.declare_existing(boundaries={"wing": 1})
    with pytest.raises(ScriptLabelError, match="already names mesh boundary 1"):
        script.declare_existing(boundaries={"wing": 2})


def test_unknown_boundary_label_lists_the_known_ones():
    script = Script(version="26.12")
    script.declare_existing(boundaries={"fuselage": 1, "wing": 2})
    with pytest.raises(ScriptReferenceError, match="unknown mesh boundary label 'tail'") as info:
        helpers.analysis_setup(script, boundaries=["tail"])
    assert "'fuselage' -> 1" in str(info.value)
    assert "'wing' -> 2" in str(info.value)


def test_unknown_label_message_when_none_are_registered():
    script = Script(version="26.12")
    with pytest.raises(ScriptReferenceError, match="no local coordinate system labels"):
        script.emit("SET_COORDINATE_SYSTEM_ORIGIN", "missing", 0.0, 0.0, 0.0, "METER")


def test_boundary_mapping_declares_labels_and_range():
    script = Script(version="26.12")
    assert script.num_boundaries is None
    script.declare_existing(boundaries={"fuselage": 1, "wing": 2})
    assert script.num_boundaries == 2
    assert script.resolve_boundary("wing") == 2
    helpers.analysis_setup(script, boundaries=["wing", 1])
    assert "SET_SOLVER_ANALYSIS_BOUNDARIES 2\n2,1" in script.render()


def test_boundary_index_out_of_declared_range_is_didactic():
    script = Script(version="26.12")
    script.declare_existing(boundaries={"fuselage": 1, "wing": 2})
    with pytest.raises(ScriptReferenceError, match="valid indices run 1 to 2") as info:
        helpers.analysis_setup(script, vorticity_drag_boundaries=[3])
    assert "cites mesh boundary 3" in str(info.value)
    assert "declare_existing" in str(info.value)


def test_boundary_declaration_by_count():
    script = Script(version="26.12")
    script.declare_existing(boundaries=2)
    assert script.num_boundaries == 2
    script.emit("SET_VORTICITY_DRAG_BOUNDARIES", 2, [1, 2])
    script.emit("SET_VORTICITY_DRAG_BOUNDARIES", -1)
    with pytest.raises(ScriptReferenceError, match="cites mesh boundary 3"):
        script.emit("SET_VORTICITY_DRAG_BOUNDARIES", 1, [3])


def test_boundary_count_argument_above_the_inventory_is_rejected():
    script = Script(version="26.12")
    script.declare_existing(boundaries=2)
    with pytest.raises(ScriptReferenceError, match="counts 3 mesh boundaries"):
        script.emit("SET_VORTICITY_DRAG_BOUNDARIES", 3, [1, 2, 3])


def test_undeclared_boundaries_stay_permissive():
    # The boundary total lives in the geometry file, so without a
    # declaration the builder cannot verify citations and must accept
    # them unchanged, as before the registry existed.
    script = Script(version="26.12")
    script.emit("SET_VORTICITY_DRAG_BOUNDARIES", 5, [7, 9, 11, 13, 15])
    assert "SET_VORTICITY_DRAG_BOUNDARIES 5\n7,9,11,13,15" in script.render()


def test_initialize_solver_surfaces_accept_boundary_labels():
    script = Script(version="26.12")
    script.declare_existing(boundaries={"wing": 1, "fuselage": 2, "tail": 3})
    helpers.initialize_solver(script, surfaces=[("wing", True), ("tail", False)])
    assert "SURFACES 2\n1,ENABLE\n3,DISABLE" in script.render()


def test_initialize_solver_surface_index_outside_inventory_is_rejected():
    script = Script(version="26.12")
    script.declare_existing(boundaries=2)
    with pytest.raises(ScriptReferenceError, match="valid indices run 1 to 2"):
        helpers.initialize_solver(script, surfaces=[(3, True)])


def test_a_bare_label_string_is_rejected_with_the_fix():
    script = Script(version="26.12")
    with pytest.raises(CommandArgumentError, match=r"\['wing'\]"):
        helpers.analysis_setup(script, boundaries="wing")
    with pytest.raises(CommandArgumentError, match="the string 'all'"):
        helpers.export_results(script, vtk="C:/out/a.vtk", vtk_boundaries="wing")


def test_label_on_a_non_creation_command_is_rejected():
    script = Script(version="26.12")
    with pytest.raises(CommandArgumentError, match="does not create"):
        script.emit("START_SOLVER", label="solve")


def test_deleting_an_entity_drops_its_dangling_label():
    script = Script(version="26.12")
    script.emit("CREATE_NEW_ACTUATOR", "PROPELLER", name="left prop", label="left")
    script.emit("CREATE_NEW_ACTUATOR", "PROPELLER", name="right prop", label="right")
    script.emit("DELETE_ACTUATOR", 2)
    script.emit("ENABLE_ACTUATOR", "left")
    with pytest.raises(ScriptReferenceError, match="unknown actuator label 'right'"):
        script.emit("ENABLE_ACTUATOR", "right")


def test_boundary_declarations_merge_count_and_mapping():
    script = Script(version="26.12")
    script.declare_existing(boundaries={"wing": 2})
    assert script.num_boundaries == 2
    script.declare_existing(boundaries=1)
    assert script.num_boundaries == 3
    assert script.entities.labels("boundaries") == {"wing": 2}


def test_boundary_mapping_validates_labels_and_indices():
    script = Script(version="26.12")
    with pytest.raises(ScriptLabelError, match="positive 1-based"):
        script.declare_existing(boundaries={"wing": 0})
    with pytest.raises(ScriptLabelError, match="non-empty string"):
        script.declare_existing(boundaries={"": 1})
    with pytest.raises(ValueError, match="zero or positive"):
        script.declare_existing(boundaries=-1)


def test_two_scripts_have_independent_registries():
    first = Script(version="26.12")
    second = Script(version="26.12")
    first.declare_existing(boundaries={"wing": 1})
    assert second.num_boundaries is None
    with pytest.raises(ScriptReferenceError, match="unknown mesh boundary label"):
        second.resolve_boundary("wing")
