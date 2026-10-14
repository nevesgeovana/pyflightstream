"""Tier 1: the licensed probe batch of the 0.40.0 command gaps (PFS-2081.13 to .17).

The catalog ``pyflightstream.qa._spec_0400_gap`` holds one probe per question the
five command-gap use cases and the geometry-stage design leave to measurement.
These tests hold what can be held without the solver: the run order the owner
set, a registered probe for every gap command, every script building on both
builds, the synthetic inputs, the stand-in structural program, and the judges
reading what a probe leaves behind.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from pyflightstream._fsm import trailing_edge_midpoints
from pyflightstream.commands import CommandNotInVersionError, CommandRegistry
from pyflightstream.qa import _spec_0400_gap as gap
from pyflightstream.qa import _spec_0400_gapkit as kit
from pyflightstream.qa.probes import generate_probe_script
from pyflightstream.qa.specs import PROBE_SPECS

BUILDS = ("26.124", "26.125")

#: The gap commands of the five use cases each probe settles, by capability.
GAP_COMMANDS = {
    "P1": (
        "SURFACE_CIRCULAR_COPY_PASTE",
        "SURFACE_LINEAR_COPY_PASTE",
        "SURFACE_CUT_BY_PLANE",
        "SURFACE_AUTO_HOLE_FILL",
        "DELETE_DEGENERATE_FACES",
        "SURFACE_SELECT_BY_ID",
        "SURFACE_SELECT_BY_THRESHOLD",
        "CREATE_NEW_SURFACE_FROM_SELECTION",
        "DELETE_SELECTED_FACES",
        "SELECT_MESH_NODE",
        "TRANSFORM_SELECTED_NODES",
    ),
    "P2": (
        "CAD_BODY_DELETE",
        "CAD_BODY_MIRROR",
        "CAD_BODY_SCALE",
        "CAD_BODY_TRANSLATE",
        "CAD_BODY_SELECT_BY_THRESHOLD",
        "SET_CAD_CREATE_MERGE_TOLERANCE",
        "SET_CAD_CREATE_SPLINE_SEGMENTS",
        "SET_CAD_CREATE_SPLINE_LOFT",
        "SET_CAD_CURVATURE_REFINEMENT",
        "CAD_CREATE_BOX",
        "CAD_CREATE_SPHERE",
        "CAD_CREATE_CYLINDER",
        "CAD_CREATE_SHEET",
        "CAD_CREATE_IMPORT_CURVE_TXT",
        "CAD_CREATE_IMPORT_CURVE_P3D",
        "CAD_CREATE_CURVE_UNSELECT",
        "CAD_CREATE_SCALE_CURVES",
        "CAD_CREATE_ROTATE_CURVES",
        "CAD_CREATE_TRANSLATE_CURVES",
        "CAD_CREATE_REORDER_CURVES",
        "CAD_CREATE_CURVE_EXPORT_CCS",
        "CAD_CREATE_CURVE_REVERSE",
        "CAD_CREATE_MIRROR_CURVES",
    ),
    "P3": (
        "NEW_OFF_BODY_STREAMTUBE",
        "SET_OFF_BODY_STREAMLINE_LENGTH",
        "SET_ALL_OFF_BODY_STREAMLINES_UPSTREAM",
        "SET_ALL_OFF_BODY_STREAMLINES_DOWNSTREAM",
        "DELETE_ALL_OFF_BODY_STREAMLINES",
        "GENERATE_ALL_SURFACE_STREAMLINES",
        "DELETE_ALL_SURFACE_STREAMLINES",
        "EXPORT_ALL_SURFACE_STREAMLINES",
    ),
    "P4": (
        "SET_MOTION_MASS_PROPERTIES",
        "SET_MOTION_GRAVITY",
        "SET_MOTION_6DOF_INITIAL_VELOCITY",
        "SET_MOTION_6DOF_INITIAL_ANGULAR_VELOCITY",
        "SET_MOTION_6DOF_ACTIVE_VARIABLES",
        "CREATE_NEW_6DOF_EXTERNAL_FORCE",
        "CREATE_NEW_6DOF_CUSTOM_FORCE",
        "SET_6DOF_MOTION_SYMMETRY_LOADS",
        "EXPORT_6DOF_TRAJECTORY",
        "CREATE_NEW_6DOF_SPRING_FORCE",
    ),
    "P5": (
        "SET_MOTION_FSI_EXECUTABLE",
        "SET_MOTION_FSI_STRUCTURAL_NODES",
        "SET_AEROELASTIC_STRUCTURAL_EXECUTION_COMMAND",
    ),
}

#: A two-triangle mesh block with one marked edge, in the layout the package reads.
TRIANGLE_BLOCK = """$MESH_START$
header
header
1
1, F, F, F
Wing
record
2
1,2,
3,3,
1,1,
2,3,
3,4,
0,0,
F,F,
T,F,
F,F,
F,F,
F,F,
0
4
0.0,1.0,0.0,1.0,
0.0,0.0,1.0,1.0,
0.0,0.0,0.0,0.0,
"""

#: One quadrilateral with its second edge (corners 2 and 3) marked: four
#: vertex-index rows and six T/F rows, the stated hypothesis of the probe reader.
QUAD_BLOCK = """$MESH_START$
header
header
1
1, F, F, F
Wing
record
1
1,
4,
1,
2,
3,
4,
0,
F,
F,
T,
F,
F,
F,
0
4
0.0,1.0,1.0,0.0,
0.0,0.0,1.0,1.0,
0.0,0.0,0.0,0.0,
"""


@pytest.fixture(scope="module")
def probes() -> tuple[gap.GapProbe, ...]:
    return gap.gap_probes()


def _source(tmp_path: Path) -> Path:
    """A source probe's folder: a saved file with one marked edge and its OBJ export."""
    folder = tmp_path / "source"
    folder.mkdir()
    (folder / "saved.fsm").write_text(TRIANGLE_BLOCK, encoding="utf-8")
    (folder / "surface_1.obj").write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
    return folder / "saved.fsm"


def test_the_batch_runs_p5_probe_a_first_then_the_capabilities_in_order(probes):
    """P0400-GAPPROBES-ORDER: P5 probe A first, then G, P1, P2, P3, P4, then the rest of P5."""
    ids = [p.probe_id for p in probes]
    assert len(ids) == len(set(ids))
    assert ids[:4] == ["P5-A0", "P5-A1", "P5-A2", "P5-A3"]
    assert all(p.stage == "first" for p in probes[:4])
    assert all(p.stage == "main" for p in probes[4:])
    order = []
    for probe in probes[4:]:
        if not order or order[-1] != probe.capability:
            order.append(probe.capability)
    assert order == ["G", "P1", "P2", "P3", "P4", "P5"]
    for probe in probes:
        assert probe.node.startswith("PFS-2081."), probe.probe_id
        if probe.opens is not None:
            source = ids.index(probe.opens)
            assert source < ids.index(probe.probe_id), probe.probe_id


def test_every_gap_command_has_its_registered_probe(probes):
    """P0400-GAPPROBES-REGISTERED: each gap command's primary probe is the catalog entry."""
    primaries = {p.spec.command: p for p in probes if p.primary}
    assert len(primaries) == sum(1 for p in probes if p.primary)
    for capability, commands in GAP_COMMANDS.items():
        for command in commands:
            probe = primaries[command]
            assert probe.capability == capability, command
            assert PROBE_SPECS[command].command == command
            assert PROBE_SPECS[command].effect_note == probe.spec.effect_note
    expected = {name for names in GAP_COMMANDS.values() for name in names}
    assert set(primaries) == expected


@pytest.mark.parametrize("build", BUILDS)
def test_every_probe_script_builds_on_both_builds(probes, build, tmp_path):
    """P0400-GAPPROBES-BUILDS: validated emission on 26.124 and 26.125, the target after BEGIN.

    Raw text is the BEFORE-the-march trajectory export of P4-04 since 0.40.0 (the
    database phase is export, RPT-166), and the after-the-march export of the other
    P4 trajectory runs, by design: each measures a placement the phase order
    refuses. Since the second
    round it is the instrument of every P4 trajectory run (the ``m`` runs, P4-06s
    and P4-11), because the export before the march holds no row (P4-04). The
    raw targets besides are the two streamtube forms (P3-01a, P3-01b). None of
    them is registered: the registered P4 probes read the saved simulation.
    """
    fsm = _source(tmp_path)
    raw_ids = {"P4-04", "P4-06s", "P4-11", "P3-01a", "P3-01b"}
    view = CommandRegistry.load().for_version(build)
    for probe in probes:
        workdir = tmp_path / build / probe.probe_id
        workdir.mkdir(parents=True)
        if probe.spec.command not in view:
            # Measured removed on this build by the batch itself (RPT-166): the
            # emitter refuses the name, which is the point of recording it.
            with pytest.raises(CommandNotInVersionError, match="removed"):
                generate_probe_script(probe.spec, build, workdir, fsm=fsm)
            continue
        script = generate_probe_script(probe.spec, build, workdir, fsm=fsm)
        expected = probe.probe_id in raw_ids or (
            probe.capability == "P4" and probe.probe_id.endswith("m") and probe.probe_id != "P4-04m"
        )
        assert script.raw_flag is expected, probe.probe_id
        assert not (script.raw_flag and probe.primary), probe.probe_id
        text = script.render()
        marker = f"PYFS_PROBE_BEGIN_{probe.spec.command}"
        assert marker in text, probe.probe_id
        assert probe.spec.command in text.split(marker, 1)[1], probe.probe_id
    registered = [p for p in probes if p.probe_id == "P4-04m"][0]
    assert registered.primary
    assert not [p for p in probes if p.probe_id == "P4-04"][0].primary


def test_the_iges_file_holds_two_sheets_in_the_fixed_layout():
    """P0400-GAPPROBES-IGES: eighty columns, five sections, two rational B-spline surfaces."""
    lines = kit.iges_two_sheets_text().splitlines()
    assert all(len(line) == 80 for line in lines)
    sections = [line[72] for line in lines]
    assert sections == sorted(sections, key="SGDPT".index)
    directory = [line for line in lines if line[72] == "D"]
    assert len(directory) == 4
    assert [line[:8].strip() for line in directory[::2]] == ["128", "128"]
    terminate = lines[-1]
    assert terminate.startswith(f"S{1:>7}G")
    assert f"D{4:>7}" in terminate


def test_the_box_has_its_hole_and_its_degenerate_face():
    """P0400-GAPPROBES-BOX: ten triangles with the hole, thirteen with the zero-area sliver."""
    holed = kit.box_triangles(hole=True, degenerate=False)
    sliver = kit.box_triangles(hole=False, degenerate=True)
    assert holed.shape == (10, 3, 3)
    assert sliver.shape == (13, 3, 3)
    a, b, c = sliver[-1]
    assert np.linalg.norm(np.cross(b - a, c - a)) == 0.0


def test_the_stand_in_logs_archives_and_answers_zero_displacements(tmp_path):
    """P0400-GAPPROBES-STANDIN: one call logs, archives the loads file, writes FSIDisp per node."""
    script = tmp_path / "fsi_standin.py"
    script.write_text(kit.fsi_standin_source(), encoding="utf-8")
    (tmp_path / "fsi_nodes.txt").write_text(
        "0.25,0.0,0.0\n0.25,1.0,0.0\n0.25,2.0,0.0\n", encoding="utf-8"
    )
    (tmp_path / "FS_SurfaceSection_Loads.txt").write_text("loads\n", encoding="utf-8")
    subprocess.run(
        [sys.executable, str(script), "extra"],
        cwd=tmp_path,
        check=True,
        timeout=60,
        env=os.environ.copy(),
    )
    displacements = (tmp_path / "FSIDisp.txt").read_text(encoding="utf-8").splitlines()
    assert displacements == ["0.000000000000e+00,0.000000000000e+00,0.000000000000e+00"] * 3
    log = (tmp_path / "fsi_standin_calls.log").read_text(encoding="utf-8")
    assert "call 1" in log and "['extra']" in log
    archived = tmp_path / "fsi_standin_calls" / "call_0001"
    assert (archived / "FS_SurfaceSection_Loads.txt").is_file()
    assert "fsi_nodes.txt" in (archived / "directory_listing.txt").read_text(encoding="utf-8")


def test_the_edge_reader_agrees_with_the_package_on_triangles_and_reads_quads(tmp_path):
    """P0400-GAPPROBES-QUADS: a quad loft's marked edge is read, so G-02 cannot fall to unprobed."""
    triangles = tmp_path / "tri.fsm"
    triangles.write_text(TRIANGLE_BLOCK, encoding="utf-8")
    read = kit.mesh_edges(triangles)
    assert read["edges"] == len(trailing_edge_midpoints(triangles)) == 1
    quads = tmp_path / "quad.fsm"
    quads.write_text(QUAD_BLOCK, encoding="utf-8")
    read = kit.mesh_edges(quads)
    assert read == {"edges": 1, "face_shapes": {"4": 1}, "flag_rows": 6}
    assert kit.edge_count(quads) == 1
    artifacts = SimpleNamespace(workdir=tmp_path)
    (tmp_path / "saved.fsm").write_text(QUAD_BLOCK, encoding="utf-8")
    assert kit.edges_kept("saved.fsm")(artifacts) is True
    unmarked = QUAD_BLOCK.replace("F,\nT,\n", "F,\nF,\n", 1)
    (tmp_path / "saved.fsm").write_text(unmarked, encoding="utf-8")
    assert kit.edges_kept("saved.fsm")(artifacts) is False


def test_the_reimport_probe_writes_the_source_marks_as_its_points_file(tmp_path):
    """P0400-GAPPROBES-REIMPORT: G-05r reads the opened file's marks and imports its OBJ."""
    fsm = _source(tmp_path)
    probe = next(p for p in gap.gap_probes() if p.probe_id == "G-05r")
    workdir = tmp_path / "probe"
    workdir.mkdir()
    text = generate_probe_script(probe.spec, "26.125", workdir, fsm=fsm).render()
    assert (workdir / "source_marks_count.txt").read_text(encoding="utf-8").strip() == "1"
    assert str(fsm.parent / "surface_1.obj") in text
    assert "IMPORT_WAKE_EDGES_FROM_FILE RELAXED" in text


def _obj(path: Path, vertices: list[tuple[float, float, float]]) -> None:
    body = "".join(f"v {x} {y} {z}\n" for x, y, z in vertices) + "f 1 2 3\n"
    path.write_text(body, encoding="utf-8")


def test_cad_translation_requires_the_combined_body_to_move(tmp_path):
    """LVV-001: the two-sheet body must leave its measured z range (RPT-166)."""
    artifacts = SimpleNamespace(workdir=tmp_path)
    judge = PROBE_SPECS["CAD_BODY_TRANSLATE"].assert_effect
    base = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 2.0)]
    _obj(tmp_path / "surface_1.obj", base)
    assert judge(artifacts) is None
    _obj(tmp_path / "surface_1.obj", [(x, y, z + 0.25) for x, y, z in base])
    assert judge(artifacts) is True


def test_the_node_judge_needs_exactly_the_one_vertex_moved_by_the_stated_step(tmp_path):
    """P0400-GAPPROBES-NODE: one vertex moved by 0.25 in z is True; none or two is unprobed."""
    base = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    _obj(tmp_path / "before.obj", base)
    artifacts = SimpleNamespace(workdir=tmp_path)
    judge = kit.one_vertex_moved((0.0, 0.0, 0.25))
    _obj(tmp_path / "after.obj", [(0.0, 0.0, 0.25), *base[1:]])
    assert judge(artifacts) is True
    _obj(tmp_path / "after.obj", base)
    assert judge(artifacts) is None
    _obj(tmp_path / "after.obj", [(0.0, 0.0, 0.25), (1.0, 0.0, 0.25), base[2]])
    assert judge(artifacts) is None


def test_the_trajectory_and_export_judges_read_numeric_rows(tmp_path):
    """P0400-GAPPROBES-EXPORTS: rows that move verify; a header alone or a still body does not."""
    artifacts = SimpleNamespace(workdir=tmp_path)
    path = tmp_path / "trajectory.txt"
    path.write_text("time, x, z\n0.0, 0.0, 0.0\n0.4, 0.0, -0.785\n", encoding="utf-8")
    assert kit.trajectory_moved("trajectory.txt")(artifacts) is True
    assert "column changes [0.4,0,-0.785]" in kit.trajectory_read("trajectory.txt")(artifacts)
    path.write_text("time, x, z\n0.0, 0.0, 0.0\n0.4, 0.0, 0.0\n", encoding="utf-8")
    assert kit.trajectory_moved("trajectory.txt")(artifacts) is None
    lines = tmp_path / "offbody.txt"
    lines.write_text("header only\n", encoding="utf-8")
    assert kit.file_rows("offbody.txt")(artifacts) is None
    assert kit.emptied("offbody.txt")(artifacts) is True
    lines.write_text("1 2 3\n", encoding="utf-8")
    assert kit.emptied("offbody.txt")(artifacts) is False
    assert kit.emptied("absent.txt")(artifacts) is None


def test_the_reorder_judge_reads_the_exported_spanwise_order(tmp_path):
    """P0400-GAPPROBES-CCS: sections in increasing y verify the reorder; tip first does not."""
    artifacts = SimpleNamespace(workdir=tmp_path)
    root = "CrossSection;0;0;0;1;0;0"
    tip = "CrossSection;0;2;0;1;2;0"
    (tmp_path / "curve.ccs").write_text(f"Component;W\n{root}\n{tip}\n", encoding="utf-8")
    assert kit.reordered("curve.ccs")(artifacts) is True
    (tmp_path / "curve.ccs").write_text(f"Component;W\n{tip}\n{root}\n", encoding="utf-8")
    assert kit.reordered("curve.ccs")(artifacts) is None
