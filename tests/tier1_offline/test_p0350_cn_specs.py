"""Synthetic CCS probe observations, with no licensed data (FR-401).

Reproduction: call a catalog assertion on reference, modified, control and
restored OBJ exports whose group names differ but whose restored geometry
matches the reference. The restored effect must be classified from geometry.
"""

from pathlib import Path

import pytest

from pyflightstream.qa import ProbeOutcome, generate_probe_script, probe_version
from pyflightstream.qa.specs import PROBE_SPECS
from tests.tier1_offline._p0340_probe_support import artifacts_in
from tests.tier1_offline.test_qa_probes import FakeFlightStream

RESTORES = (
    "DEFAULT_CCS_FUSELAGE_MESH_SETTINGS",
    "DEFAULT_CCS_REVOLVE_MESH_SETTINGS",
    "DEFAULT_CCS_WING_MESH_SETTINGS",
    "DELETE_CCS_FUSELAGE_REFINEMENT_ZONES",
    "DELETE_CCS_REVOLVE_REFINEMENT_ZONES",
    "DELETE_CCS_WING_REFINEMENT_ZONES",
    "DELETE_CCS_WING_CONTROL_SURFACE",
)
RELAXED = ("DELETE_CCS_FUSELAGE_RELAXED_TE", "DELETE_CCS_REVOLVE_RELAXED_TE")


def obj(name, changed=False, formatted=False):
    points = "v 0 0 0\nv 1 0 0\nv 0 2 0\n"
    if formatted:
        points = "  v 0.0 -0.0 0e0\nv 1.000 0 0\nv 0 2.0 0\n"
    face = "f 1 2 3\n"
    if changed:
        points += "v 1 2 0\n"
        face += "f 2 4 3\n"
    return f"o {name}\ng {name}\n" + points + face


def meshes(folder, *, restored=False, control=True):
    for name, changed in (
        ("reference", False),
        ("variant", True),
        ("control", control),
        ("restored", restored),
    ):
        (folder / f"{name}.obj").write_text(obj(name, changed), encoding="utf-8")


@pytest.mark.parametrize("command", RESTORES)
def test_restore_matches_reference_and_differs_from_control(tmp_path, command):
    """P0350-CN (FR-401): reference restored with a changed control is verified."""
    meshes(tmp_path)
    assert PROBE_SPECS[command].assert_effect(artifacts_in(tmp_path)) is True


@pytest.mark.parametrize("command", RESTORES)
def test_restored_equal_to_control_is_not_restored(tmp_path, command):
    """P0350-CN (FR-401): a surviving modified state falsifies restoration."""
    meshes(tmp_path, restored=True)
    assert PROBE_SPECS[command].assert_effect(artifacts_in(tmp_path)) is False


@pytest.mark.parametrize("control", [False, None, "empty"])
def test_restore_requires_a_valid_changed_control(tmp_path, control):
    """P0350-CN (FR-401): missing, empty or reset controls cannot verify a restore."""
    meshes(tmp_path, control=control)
    if control is None:
        (tmp_path / "control.obj").unlink()
    if control == "empty":
        (tmp_path / "control.obj").write_text("g empty\n", encoding="utf-8")
    assert PROBE_SPECS[RESTORES[0]].assert_effect(artifacts_in(tmp_path)) is None


@pytest.mark.parametrize("formatted", [False, True])
def test_group_names_and_numeric_format_do_not_change_geometry(tmp_path, formatted):
    """P0350-CN (FR-401): OBJ names and numeric spelling do not change a mesh."""
    (tmp_path / "reference.obj").write_text(obj("reference"), encoding="utf-8")
    (tmp_path / "variant.obj").write_text(obj("variant", formatted=formatted), encoding="utf-8")
    spec = PROBE_SPECS["NEW_CCS_WING_REFINEMENT_ZONE"]
    assert spec.assert_effect(artifacts_in(tmp_path)) is None


def test_zone_mesh_change_is_observed(tmp_path):
    """P0350-CN (FR-401): changed vertices and faces verify the zone setting."""
    meshes(tmp_path)
    spec = PROBE_SPECS["NEW_CCS_WING_REFINEMENT_ZONE"]
    assert spec.assert_effect(artifacts_in(tmp_path)) is True


@pytest.mark.parametrize("text", ["", "g empty\n", "v nan 0 0\nf 1 1 1\n", "v 0 0 0\nf 0 1 1\n"])
def test_invalid_geometry_cannot_judge_a_change(tmp_path, text):
    """P0350-CN (FR-401): an empty or malformed mesh is an instrument failure."""
    meshes(tmp_path)
    (tmp_path / "variant.obj").write_text(text, encoding="utf-8")
    assert PROBE_SPECS["NEW_CCS_WING_REFINEMENT_ZONE"].assert_effect(artifacts_in(tmp_path)) is None


def test_equal_counts_do_not_hide_changed_geometry(tmp_path):
    """P0350-CN (FR-401): a coordinate change matters even when both counts agree."""
    for name in ("reference", "variant"):
        text = obj(name).replace("v 1 0 0", "v 3 0 0") if name == "variant" else obj(name)
        (tmp_path / f"{name}.obj").write_text(text, encoding="utf-8")
    assert PROBE_SPECS["NEW_CCS_WING_REFINEMENT_ZONE"].assert_effect(artifacts_in(tmp_path)) is True


@pytest.mark.parametrize("command", RESTORES)
def test_lofts_are_exported_and_cleared_as_made(tmp_path, command):
    """P0350-CN (FR-401): each loft is captured before another mutates its mesh."""
    lines = [
        line
        for line in generate_probe_script(PROBE_SPECS[command], "26.124", tmp_path)
        .render()
        .splitlines()
        if line
    ]
    lofts = [
        i
        for i, line in enumerate(lines)
        if line.startswith("CAD_CREATE_") and "_MESH_FROM_CCS" in line
    ]
    assert len(lofts) == 4
    for index, at in enumerate(lofts):
        assert lines[at + 1] == "EXPORT_SURFACE_MESH OBJ 1"
        assert (
            Path(lines[at + 2]).name
            == ("reference.obj", "variant.obj", "control.obj", "restored.obj")[index]
        )
        if index < 3:
            count = 3 if command.endswith("CONTROL_SURFACE") and index in (1, 2) else 1
            assert lines[at + 3 : at + 3 + count] == ["DELETE_SURFACES 1"] * count


@pytest.mark.parametrize(
    "command", ["NEW_CCS_WING_REFINEMENT_ZONE", "DELETE_CCS_WING_REFINEMENT_ZONES"]
)
def test_wing_zone_intersects_the_synthetic_loft_extents(tmp_path, command):
    """P0350-CN (FR-401): the zone spans the loft interior with a margin on both ends."""
    text = generate_probe_script(PROBE_SPECS[command], "26.124", tmp_path).render()
    wing = (tmp_path / "ccs3.csv").read_text(encoding="utf-8").split("Component;", 2)[1]
    ys = [
        float(value)
        for line in wing.splitlines()
        if line.startswith("CrossSection;")
        for value in line.split(";")[2::3]
    ]
    words = next(
        line.split()
        for line in text.splitlines()
        if line.startswith("NEW_CCS_WING_REFINEMENT_ZONE ")
    )
    start, end = (min(ys) + float(value) * (max(ys) - min(ys)) for value in words[1:3])
    assert min(ys) < start < end < max(ys)
    assert end - start == pytest.approx(0.8 * (max(ys) - min(ys)))
    assert int(words[3]) > 40


def saved(folder, name, marked):
    flags = ["T,", "T," if marked else "F,", "F,", "F,", "T,"]
    lines = [
        "$MESH_START$",
        "1",
        "3",
        "1",
        "2, T, T, F",
        name,
        ".5,.5,.5",
        "1",
        "1,",
        "3,",
        "1,",
        "2,",
        "3,",
        "0,",
        *flags,
        "0",
        "3",
        "0,1,0,",
        "0,0,2,",
        "0,0,0,",
        "$MESH_END$",
    ]
    (folder / f"{name}.fsm").write_text("\n".join(lines), encoding="utf-8")


@pytest.mark.parametrize("command", RELAXED)
def test_relaxed_te_judge_reads_saved_face_state(tmp_path, command):
    """P0350-CN (FR-401): identical geometry with restored face flags verifies TE deletion."""
    for name, marked in (
        ("reference", False),
        ("variant", True),
        ("control", True),
        ("restored", False),
    ):
        saved(tmp_path, name, marked)
        (tmp_path / f"{name}.obj").write_text(obj(name), encoding="utf-8")
    assert PROBE_SPECS[command].assert_effect(artifacts_in(tmp_path)) is True
    saved(tmp_path, "restored", True)
    assert PROBE_SPECS[command].assert_effect(artifacts_in(tmp_path)) is False
    (tmp_path / "control.fsm").write_text("$MESH_START$\ntruncated", encoding="utf-8")
    assert PROBE_SPECS[command].assert_effect(artifacts_in(tmp_path)) is None


@pytest.mark.parametrize("command", RELAXED)
def test_relaxed_te_spec_saves_each_loft(tmp_path, command):
    """P0350-CN (FR-401): the TE deletion instrument saves all four loft states."""
    text = generate_probe_script(PROBE_SPECS[command], "26.124", tmp_path).render()
    for name in ("reference", "variant", "control", "restored"):
        assert str(tmp_path / f"{name}.fsm") in text


def test_prelude_abort_is_not_called_environment_drift(tmp_path):
    """P0350-CN (FR-401): a missing BEGIN attributes failure to the probe prelude."""
    command = RELAXED[0]
    run = probe_version(
        "26.124",
        workroot=tmp_path,
        commands=[command],
        executor=FakeFlightStream(abort_on="NEW_CCS_FUSELAGE_RELAXED_TE"),
    )
    result = next(result for result in run.results if result.command == command)
    assert result.outcome == ProbeOutcome.UNPROBED
    assert "prelude" in result.detail
    assert "environment drifted" not in result.detail
