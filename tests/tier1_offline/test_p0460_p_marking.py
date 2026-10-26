"""P0460 lane P: saved-state marking instruments, without a licensed process."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pyflightstream.qa.probes import generate_probe_script
from pyflightstream.qa.specs import PROBE_SPECS

COMMANDS = (
    "MARK_WAKE_TERMINATION_NODES",
    "AUTO_DETECT_WAKE_TERMINATION_NODES",
    "IMPORT_WAKE_EDGES_FROM_FILE",
    "CREATE_NEW_BASE_REGION",
    "SET_BASE_REGION_CP",
    "SET_BASE_REGION_TRAILING_EDGES",
    "SURFACE_COMBINE",
    "SURFACE_RENAME",
)


@pytest.mark.parametrize("command", COMMANDS)
def test_p0460_saved_marking_registered(command):
    spec = PROBE_SPECS.get(command)
    assert spec is not None
    assert "unchanged control" in spec.effect_note
    assert spec.observe is not None


@pytest.mark.parametrize(
    "command,expected",
    [
        ("MARK_WAKE_TERMINATION_NODES", "SELECT_MESH_NODE 7\nMARK_WAKE_TERMINATION_NODES"),
        ("AUTO_DETECT_WAKE_TERMINATION_NODES", "AUTO_DETECT_WAKE_TERMINATION_NODES"),
        ("IMPORT_WAKE_EDGES_FROM_FILE", "IMPORT_WAKE_EDGES_FROM_FILE RELAXED 0.0001 1"),
        ("CREATE_NEW_BASE_REGION", "CREATE_NEW_BASE_REGION 2 EMPIRICAL -0.2"),
        ("SET_BASE_REGION_CP", "SET_BASE_REGION_CP 1 CUSTOM -0.35"),
        ("SET_BASE_REGION_TRAILING_EDGES", "SET_BASE_REGION_TRAILING_EDGES -1"),
        ("SURFACE_RENAME", "SURFACE_RENAME 2 RenamedRim"),
    ],
)
def test_p0460_nested_targets_use_the_distinctive_required_arguments(tmp_path, command, expected):
    generate_probe_script(PROBE_SPECS[command], "26.125", tmp_path)
    assert expected in (tmp_path / "target.txt").read_text()


@pytest.mark.parametrize("command", COMMANDS)
@pytest.mark.parametrize("version", ["26.124", "26.125"])
def test_p0460_scripts_measure_initialization_and_control(tmp_path, command, version):
    text = generate_probe_script(PROBE_SPECS[command], version, tmp_path).render()
    text += "\n" + (tmp_path / "prepare.txt").read_text() + (tmp_path / "target.txt").read_text()
    assert "START_SOLVER" not in text
    assert "control.fsm" in text and "before.fsm" in text and "after.fsm" in text
    assert text.count("INITIALIZE_SOLVER\n") == (1 if version == "26.124" else 0)
    if version == "26.124":
        text += (tmp_path / "noinit_prepare.txt").read_text()
        assert "noinit_control.fsm" in text and "noinit_after.fsm" in text
        prepare = (tmp_path / "prepare.txt").read_text()
        assert prepare.index("INITIALIZE_SOLVER\n") < prepare.index("control.fsm")
    else:
        assert not (tmp_path / "noinit_prepare.txt").exists()


def test_p0460_combine_scripts_run_both_list_orders_from_same_save(tmp_path):
    generate_probe_script(PROBE_SPECS["SURFACE_COMBINE"], "26.125", tmp_path)
    for name, order in (("forward", "1,2"), ("reverse", "2,1")):
        script = (tmp_path / f"{name}.txt").read_text()
        assert "before.fsm" in script
        assert f"SURFACE_COMBINE 2\n{order}" in script


def test_p0460_m3_selects_and_moves_before_and_after_combine(tmp_path):
    generate_probe_script(PROBE_SPECS["SURFACE_COMBINE"], "26.124", tmp_path)
    for prefix in ("m3_init_", "m3_noinit_"):
        assert "MARK_WAKE_TERMINATION_NODES" in (tmp_path / f"{prefix}mark.txt").read_text()
        for name in ("reference_move", "move"):
            text = (tmp_path / f"{prefix}{name}.txt").read_text()
            assert "SELECT_MESH_NODE 7" in text
            assert "TRANSFORM_SELECTED_NODES 1 TRANSLATION 0.0 0.0 0.25" in text
        prepared = (tmp_path / f"{prefix}prepare.txt").read_text()
        assert ("INITIALIZE_SOLVER" in prepared) == (prefix == "m3_init_")


@pytest.mark.parametrize("command", COMMANDS)
def test_p0460_missing_files_never_verify(tmp_path, command):
    spec = PROBE_SPECS[command]
    artifacts = SimpleNamespace(workdir=tmp_path)
    assert spec.assert_effect(artifacts) is None
    assert '"effect": null' in spec.observe(artifacts)


@pytest.fixture
def saved(tmp_path):
    """Exact MESH/PHYSICS excerpts from the synthetic 26.125 marking saves."""
    data = json.loads((Path(__file__).parent / "fixtures/p0460_marking_sections.json").read_text())

    def load(command):
        for name, text in data[command].items():
            (tmp_path / f"{name}.fsm").write_text(text)
        return PROBE_SPECS[command], SimpleNamespace(workdir=tmp_path)

    return load


@pytest.mark.parametrize("command", COMMANDS)
def test_p0460_saved_excerpts_verify(tmp_path, saved, command):
    spec, artifacts = saved(command)
    expected = None if command == COMMANDS[1] else True
    assert spec.assert_effect(artifacts) is expected
    reading = json.loads(spec.observe(artifacts))["primary"]
    assert reading["effect"] is expected
    if command == COMMANDS[0]:
        assert [state["termination"] for state in reading["states"]] == [0, 1, 0]
    if command == COMMANDS[2]:
        assert [len(state["edges"]) for state in reading["states"]] == [1, 2, 1]
        assert reading["states"][1]["groups"] == ["Rim", "Rim"]
        assert [[2.0, 0.0, 1.0], 2] in reading["states"][1]["edges"]


@pytest.mark.parametrize("command", COMMANDS)
def test_p0460_changed_control_never_verifies(tmp_path, saved, command):
    spec, artifacts = saved(command)
    (tmp_path / "control.fsm").write_text((tmp_path / "after.fsm").read_text())
    assert spec.assert_effect(artifacts) is None


@pytest.mark.parametrize("command", COMMANDS)
def test_p0460_unchanged_state_never_verifies(tmp_path, saved, command):
    spec, artifacts = saved(command)
    (tmp_path / "after.fsm").write_text((tmp_path / "before.fsm").read_text())
    assert spec.assert_effect(artifacts) is not True


@pytest.mark.parametrize(
    "record", ["1\n5,\n3,", "1\n5,6,\n3,\n1,", "1\n9,\n3,\n1,", "0\njunk", "1\n5,\n99,\n1,"]
)
def test_p0460_malformed_record_is_unobservable(tmp_path, saved, record):
    spec, artifacts = saved(COMMANDS[0])
    path = tmp_path / "after.fsm"
    text = path.read_text()
    assert "1\n5,\n3,\n1,\n$MESH_END$" in text
    path.write_text(text.replace("1\n5,\n3,\n1,\n$MESH_END$", record + "\n$MESH_END$"))
    assert spec.assert_effect(artifacts) is None


@pytest.mark.parametrize("node,flag", [(3, 2), (5, 3), (7, 3)])
def test_p0460_record_identity_is_route_dependent(tmp_path, saved, node, flag):
    spec, artifacts = saved(COMMANDS[0])
    path = tmp_path / "after.fsm"
    path.write_text(
        path.read_text().replace("5,\n3,\n1,\n$MESH_END$", f"{node},\n{flag},\n1,\n$MESH_END$")
    )
    assert spec.assert_effect(artifacts) is True


@pytest.mark.parametrize("survives,same_vertex", [(True, True), (False, True), (True, False)])
def test_p0460_m3_reports_record_and_vertex_independently(tmp_path, saved, survives, same_vertex):
    spec, artifacts = saved("SURFACE_COMBINE")
    prefix = "m3_noinit_"
    if not survives:
        path = tmp_path / f"{prefix}after.fsm"
        text = path.read_text()
        head, tail = text.split("$MESH_END$")
        path.write_text("\n".join(head.rstrip().splitlines()[:-4]) + "\n0\n$MESH_END$" + tail)
    if not same_vertex:
        (tmp_path / f"{prefix}moved.fsm").write_text((tmp_path / f"{prefix}after.fsm").read_text())
    reading = json.loads(spec.observe(artifacts))["M3_without_INITIALIZE_SOLVER"]
    assert reading["record_survives"] is survives
    assert reading["same_vertex"] is same_vertex
    assert spec.assert_effect(artifacts) is True


@pytest.mark.parametrize("command", COMMANDS[:2])
def test_p0460_auto_and_mark_observe_the_same_record(tmp_path, saved, command):
    # AUTO's captured run has no record. Use MARK's measured record to exercise
    # AUTO's positive case without misrepresenting that captured outcome.
    saved(COMMANDS[0])
    spec = PROBE_SPECS[command]
    artifacts = SimpleNamespace(workdir=tmp_path)
    assert spec.assert_effect(artifacts) is True


@pytest.mark.parametrize("mutation", ["one_group", "wrong_type", "lost_first", "lost_group"])
def test_p0460_import_counts_edges_and_checks_second_type(tmp_path, saved, mutation):
    spec, artifacts = saved(COMMANDS[2])
    path = tmp_path / "after.fsm"
    text = path.read_text()
    if mutation == "one_group":
        text = text.replace("2\nRim\nRim\n1,2,", "1\nRim\n1,")
    elif mutation == "lost_group":
        text = text.replace("2\nRim\nRim\n1,2,", "1\nBody\n1,")
    else:
        rows = text.splitlines()
        at = rows.index("$MESH_START$")
        if mutation == "wrong_type":
            rows[at + 16] = "0,0,0,1,0,0,0,1,0,0,1,1,"
        else:
            rows[at + 32] = "F,F,F,F,F,F,F,F,F,F,F,F,"
            rows[at + 33] = "F,F,F,F,F,F,F,T,F,F,F,T,"
        text = "\n".join(rows) + "\n"
    path.write_text(text)
    assert spec.assert_effect(artifacts) is (mutation == "one_group")


@pytest.mark.parametrize(
    "command",
    [
        "CREATE_NEW_BASE_REGION",
        "SET_BASE_REGION_CP",
        "SET_BASE_REGION_TRAILING_EDGES",
        "SURFACE_RENAME",
    ],
)
def test_p0460_saved_boundary_identity_is_required(tmp_path, saved, command):
    spec, artifacts = saved(command)
    path = tmp_path / "after.fsm"
    text = path.read_text()
    if command == "SURFACE_RENAME":
        text = text.replace("RenamedRim", "WrongRim")
    else:
        mesh, physics = text.split("$PHYSICS_START$")
        text = mesh + "$PHYSICS_START$" + physics.replace("Rim", "Body")
    path.write_text(text)
    assert spec.assert_effect(artifacts) is False


@pytest.mark.parametrize("name", ["forward", "after"])
def test_p0460_both_combine_orders_must_retain_body(tmp_path, saved, name):
    spec, artifacts = saved("SURFACE_COMBINE")
    path = tmp_path / f"{name}.fsm"
    path.write_text(path.read_text().replace("Body", "Rim"))
    assert spec.assert_effect(artifacts) is False


def test_p0460_partial_rim_never_verifies(tmp_path, saved):
    spec, artifacts = saved("SET_BASE_REGION_TRAILING_EDGES")
    path = tmp_path / "after.fsm"
    rows = path.read_text().splitlines()
    at = rows.index("$MESH_START$")
    rows[at + 32] = "F,F,F,F,F,F,F,F,F,F,T,F,"
    rows[at + 33] = "F,F,F,F,F,F,F,F,F,F,F,F,"
    rows[at + 34] = "F,F,F,F,F,F,F,F,F,F,F,F,"
    path.write_text("\n".join(rows) + "\n")
    assert spec.assert_effect(artifacts) is False
