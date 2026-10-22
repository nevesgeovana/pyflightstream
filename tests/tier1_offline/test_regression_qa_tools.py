"""Regression coverage grouped by subject."""

from __future__ import annotations

import dataclasses
import importlib.util
import io
import json
import os
import subprocess
import sys
import typing
import warnings
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import yaml

import pyflightstream.cases.workflows._exports as exports_module
import pyflightstream.cases.workflows._farfield as farfield_module
import pyflightstream.post.farfield_fields as farfield_fields
import pyflightstream.probes.geometry as gate
from pyflightstream._fsm import trailing_edge_midpoints
from pyflightstream.cases._farfield_spec import LatticeShape, LedgersSpec
from pyflightstream.commands import CommandNotInVersionError, CommandRegistry
from pyflightstream.farfield import (
    lateral_flux,
    sample_area_coverage,
    transverse_flux,
    transverse_force,
)
from pyflightstream.farfield.quadrature import ring_sample_weights
from pyflightstream.probes import (
    AxisSpec,
    FrameDefinition,
    GeometryGateReport,
    PlanarProbeGrid,
    PlannedProbes,
    RefinementBand,
    emit_probe_import,
)
from pyflightstream.probes import emit_probe_export as _qa_probe_emission__emit_probe_export
from pyflightstream.probes.errors import ProbeGeometryError
from pyflightstream.probes.geometry import OpenMeshError, apply_geometry_gate, load_surface_mesh
from pyflightstream.probes.layouts import emit_probe_export as _reach2_routes__emit_probe_export
from pyflightstream.probes.layouts import emit_probe_points, write_points_csv, write_probe_csv
from pyflightstream.qa import PROBE_SPECS as _QA_PROBES__PROBE_SPECS
from pyflightstream.qa import _spec_0400_gap as gap
from pyflightstream.qa import _spec_0400_gapkit as kit
from pyflightstream.qa import _spec_ccs_noise, compat
from pyflightstream.qa import matrix as matrix_module
from pyflightstream.qa.cli import main
from pyflightstream.qa.compat import (
    COMPAT_SCHEMA,
    ExecutableVerdict,
    apply_compat,
    classify_executable,
    write_compat_report,
)
from pyflightstream.qa.cost import cost_rows, cost_view
from pyflightstream.qa.errors import QaEvidenceError
from pyflightstream.qa.geometry import BladeSpec, WingSpec
from pyflightstream.qa.physics import (
    PHYSICS_CASES,
    PHYSICS_SCHEMA,
    CaseReference,
    CaseResult,
    PhysicsEnvironmentError,
    PhysicsRun,
    PointResult,
    ReferenceBand,
    Verdict,
    compare_metrics,
    load_reference,
    phy01_metrics,
    read_physics_report,
    update_reference,
    write_physics_report,
)
from pyflightstream.qa.probes import (
    DEFAULT_ERROR_PATTERNS,
    ProbeArtifacts,
    ProbeOutcome,
    ProbeResult,
    ProbeRun,
    ProbeSpec,
    Requires,
    _judge,
    _run_probe,
    _validate_tiers,
    dump_gained,
    fsm_gained,
    generate_probe_script,
)
from pyflightstream.qa.specs import PROBE_SPECS as _GAPPROBES_SPECS__PROBE_SPECS
from pyflightstream.run import ExecutionResult
from pyflightstream.script import CommandArgumentError, Script, helpers
from pyflightstream.versions import known_versions, resolve
from pyflightstream.workspace import RunRecord, RunStatus
from tests.tier1_offline.test_regression_farfield_interfaces import (
    _farfield_plan___case as _reach2_routes___case,
)
from tests.tier1_offline.test_regression_farfield_interfaces import (
    _farfield_plan___script as _reach2_routes___script,
)
from tests.tier1_offline.test_regression_workflow_emission import (
    _cases_workflows_probes___rendered as _reach2_routes___rendered,
)
from tests.tier1_offline.test_regression_workflow_emission import (
    _cases_workflows_probes___steady_with as _reach2_routes___steady_with,
)

_GAPPROBES_SPECS__BUILDS = ("26.124", "26.125")


#: The gap commands of the five use cases each probe settles, by capability.
_GAPPROBES_SPECS__GAP_COMMANDS = {
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
_GAPPROBES_SPECS__TRIANGLE_BLOCK = """$MESH_START$
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
_GAPPROBES_SPECS__QUAD_BLOCK = """$MESH_START$
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


def _gapprobes_specs___source(tmp_path: Path) -> Path:
    """A source probe's folder: a saved file with one marked edge and its OBJ export."""
    folder = tmp_path / "source"
    folder.mkdir()
    (folder / "saved.fsm").write_text(_GAPPROBES_SPECS__TRIANGLE_BLOCK, encoding="utf-8")
    (folder / "surface_1.obj").write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
    return folder / "saved.fsm"


def _gapprobes_specs___obj(path: Path, vertices: list[tuple[float, float, float]]) -> None:
    body = "".join(f"v {x} {y} {z}\n" for x, y, z in vertices) + "f 1 2 3\n"
    path.write_text(body, encoding="utf-8")


class TestGapprobesSpecs:
    """Tier 1: the licensed probe batch of the 0.40.0 command gaps (PFS-2081.13 to .17).

    The catalog ``pyflightstream.qa._spec_0400_gap`` holds one probe per question the
    five command-gap use cases and the geometry-stage design leave to measurement.
    These tests hold what can be held without the solver: the run order the owner
    set, a registered probe for every gap command, every script building on both
    builds, the synthetic inputs, the stand-in structural program, and the judges
    reading what a probe leaves behind.
    """

    @staticmethod
    @pytest.fixture(scope="class")
    def probes() -> tuple[gap.GapProbe, ...]:
        return gap.gap_probes()

    @staticmethod
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

    @staticmethod
    def test_every_gap_command_has_its_registered_probe(probes):
        """P0400-GAPPROBES-REGISTERED: each gap command's primary probe is the catalog entry."""
        primaries = {p.spec.command: p for p in probes if p.primary}
        assert len(primaries) == sum(1 for p in probes if p.primary)
        for capability, commands in _GAPPROBES_SPECS__GAP_COMMANDS.items():
            for command in commands:
                probe = primaries[command]
                assert probe.capability == capability, command
                assert _GAPPROBES_SPECS__PROBE_SPECS[command].command == command
                assert _GAPPROBES_SPECS__PROBE_SPECS[command].effect_note == probe.spec.effect_note
        expected = {name for names in _GAPPROBES_SPECS__GAP_COMMANDS.values() for name in names}
        assert set(primaries) == expected

    @staticmethod
    @pytest.mark.parametrize("build", _GAPPROBES_SPECS__BUILDS)
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
        fsm = _gapprobes_specs___source(tmp_path)
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
                probe.capability == "P4"
                and probe.probe_id.endswith("m")
                and probe.probe_id != "P4-04m"
            )
            assert script.raw_flag is expected, probe.probe_id
            assert not (script.raw_flag and probe.primary), probe.probe_id
            text = script.render()
            marker = f"PYFS_PROBE_BEGIN_{probe.spec.command}"
            assert marker in text, probe.probe_id
            assert probe.spec.command in text.split(marker, 1)[1], probe.probe_id
            if probe.probe_id in {"P3-03", "P3-04"}:
                opposite = "DOWNSTREAM" if probe.probe_id == "P3-03" else "UPSTREAM"
                assert f"SET_ALL_OFF_BODY_STREAMLINES_{opposite}" in text.split(marker, 1)[0]
        registered = [p for p in probes if p.probe_id == "P4-04m"][0]
        assert registered.primary
        assert not [p for p in probes if p.probe_id == "P4-04"][0].primary

    @staticmethod
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

    @staticmethod
    def test_the_box_has_its_hole_and_its_degenerate_face():
        """P0400-GAPPROBES-BOX: ten triangles with the hole, thirteen with the zero-area sliver."""
        holed = kit.box_triangles(hole=True, degenerate=False)
        sliver = kit.box_triangles(hole=False, degenerate=True)
        assert holed.shape == (10, 3, 3)
        assert sliver.shape == (13, 3, 3)
        a, b, c = sliver[-1]
        assert np.linalg.norm(np.cross(b - a, c - a)) == 0.0

    @staticmethod
    def test_the_stand_in_logs_archives_and_answers_zero_displacements(tmp_path):
        """P0400-GAPPROBES-STANDIN: one call logs, archives the loads file, writes FSIDisp per node."""  # noqa: E501
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

    @staticmethod
    def test_the_edge_reader_agrees_with_the_package_on_triangles_and_reads_quads(tmp_path):
        """P0400-GAPPROBES-QUADS: a quad loft's marked edge is read, so G-02 cannot fall to unprobed."""  # noqa: E501
        triangles = tmp_path / "tri.fsm"
        triangles.write_text(_GAPPROBES_SPECS__TRIANGLE_BLOCK, encoding="utf-8")
        read = kit.mesh_edges(triangles)
        assert read["edges"] == len(trailing_edge_midpoints(triangles)) == 1
        quads = tmp_path / "quad.fsm"
        quads.write_text(_GAPPROBES_SPECS__QUAD_BLOCK, encoding="utf-8")
        read = kit.mesh_edges(quads)
        assert read == {"edges": 1, "face_shapes": {"4": 1}, "flag_rows": 6}
        assert kit.edge_count(quads) == 1
        artifacts = SimpleNamespace(workdir=tmp_path)
        (tmp_path / "saved.fsm").write_text(_GAPPROBES_SPECS__QUAD_BLOCK, encoding="utf-8")
        assert kit.edges_kept("saved.fsm")(artifacts) is True
        unmarked = _GAPPROBES_SPECS__QUAD_BLOCK.replace("F,\nT,\n", "F,\nF,\n", 1)
        (tmp_path / "saved.fsm").write_text(unmarked, encoding="utf-8")
        assert kit.edges_kept("saved.fsm")(artifacts) is False

    @staticmethod
    def test_the_reimport_probe_writes_the_source_marks_as_its_points_file(tmp_path):
        """P0400-GAPPROBES-REIMPORT: G-05r reads the opened file's marks and imports its OBJ."""
        fsm = _gapprobes_specs___source(tmp_path)
        probe = next(p for p in gap.gap_probes() if p.probe_id == "G-05r")
        workdir = tmp_path / "probe"
        workdir.mkdir()
        text = generate_probe_script(probe.spec, "26.125", workdir, fsm=fsm).render()
        assert (workdir / "source_marks_count.txt").read_text(encoding="utf-8").strip() == "1"
        assert str(fsm.parent / "surface_1.obj") in text
        assert "IMPORT_WAKE_EDGES_FROM_FILE RELAXED" in text

    @staticmethod
    def test_cad_translation_requires_the_combined_body_to_move(tmp_path):
        """LVV-001: the two-sheet body must leave its measured z range (RPT-166)."""
        artifacts = SimpleNamespace(workdir=tmp_path)
        judge = _GAPPROBES_SPECS__PROBE_SPECS["CAD_BODY_TRANSLATE"].assert_effect
        base = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 2.0)]
        _gapprobes_specs___obj(tmp_path / "surface_1.obj", base)
        assert judge(artifacts) is None
        _gapprobes_specs___obj(tmp_path / "surface_1.obj", [(x, y, z + 0.25) for x, y, z in base])
        assert judge(artifacts) is True

    @staticmethod
    def test_the_node_judge_needs_exactly_the_one_vertex_moved_by_the_stated_step(tmp_path):
        """P0400-GAPPROBES-NODE: one vertex moved by 0.25 in z is True; none or two is unprobed."""
        base = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
        _gapprobes_specs___obj(tmp_path / "before.obj", base)
        artifacts = SimpleNamespace(workdir=tmp_path)
        judge = kit.one_vertex_moved((0.0, 0.0, 0.25))
        _gapprobes_specs___obj(tmp_path / "after.obj", [(0.0, 0.0, 0.25), *base[1:]])
        assert judge(artifacts) is True
        _gapprobes_specs___obj(tmp_path / "after.obj", base)
        assert judge(artifacts) is None
        _gapprobes_specs___obj(
            tmp_path / "after.obj", [(0.0, 0.0, 0.25), (1.0, 0.0, 0.25), base[2]]
        )
        assert judge(artifacts) is None
        # LVV-002: pairing must not silently discard an extra deletion or insertion.
        for extra_change in (
            [(0.0, 0.0, 0.25), base[2]],
            [(0.0, 0.0, 0.25), *base[1:], (2.0, 0.0, 0.0)],
        ):
            _gapprobes_specs___obj(tmp_path / "after.obj", extra_change)
            assert judge(artifacts) is None
            assert kit.one_vertex_moved(None)(artifacts) is None

    @staticmethod
    def test_the_trajectory_and_export_judges_read_numeric_rows(tmp_path):
        """P0400-GAPPROBES-EXPORTS: rows that move verify; a header alone or a still body does not."""  # noqa: E501
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

    @staticmethod
    @pytest.mark.parametrize("direction", ["UPSTREAM", "DOWNSTREAM"])
    def test_streamline_direction_requires_coordinates_on_the_requested_side(tmp_path, direction):
        """LVV-003: opposite and stationary traces cannot verify a direction setting."""
        fixture = (
            Path(__file__).parent / "fixtures" / "off_body_streamlines_26.123.txt"
        ).read_text(encoding="utf-8")
        judge = _GAPPROBES_SPECS__PROBE_SPECS[
            f"SET_ALL_OFF_BODY_STREAMLINES_{direction}"
        ].assert_effect
        artifacts = SimpleNamespace(workdir=tmp_path)
        requested = -1 if direction == "UPSTREAM" else 1
        for sign in (-requested, 0, requested):
            lines = []
            for line in fixture.splitlines():
                cells = line.strip().rstrip(",").split(",")
                if len(cells) == 10 and "E" in cells[0]:
                    cells[0] = str(-1 + sign * (float(cells[0]) - 2))
                    line = ",".join(cells) + ","
                lines.append(line)
            (tmp_path / "offbody.txt").write_text("\n".join(lines), encoding="utf-8")
            assert judge(artifacts) is (True if sign == requested else None)
        (tmp_path / "offbody.txt").write_text("3\n31\n", encoding="utf-8")
        assert judge(artifacts) is None

    @staticmethod
    def test_the_reorder_judge_reads_the_exported_spanwise_order(tmp_path):
        """P0400-GAPPROBES-CCS: sections in increasing y verify the reorder; tip first does not."""
        artifacts = SimpleNamespace(workdir=tmp_path)
        root = "CrossSection;0;0;0;1;0;0"
        tip = "CrossSection;0;2;0;1;2;0"
        (tmp_path / "curve.ccs").write_text(f"Component;W\n{root}\n{tip}\n", encoding="utf-8")
        assert kit.reordered("curve.ccs")(artifacts) is True
        (tmp_path / "curve.ccs").write_text(f"Component;W\n{tip}\n{root}\n", encoding="utf-8")
        assert kit.reordered("curve.ccs")(artifacts) is None


_QA_COMPAT__META = 'versions:\n  - canonical: "26.120"\n    alias: "26.12"\n'


_QA_COMPAT__CHAPTER = """\
STOP:
  layout: bare
  phase: control
  args: []
  manual_ref: "FSM-26.120 p.281"
  versions:
    "26.120": {status: documented, note: "FSM-26.100 p.358 documents it on this edition"}
"""


def _qa_compat___commands(folder):
    folder.mkdir(parents=True)
    (folder / "_meta.yaml").write_text(_QA_COMPAT__META, encoding="utf-8")
    (folder / "script_controls.yaml").write_text(_QA_COMPAT__CHAPTER, encoding="utf-8")
    return folder


def _qa_compat___report(root, commands):
    folder = root / "reports" / "compat"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "CMP-26120_2026-10-12.yaml"
    document = {"schema": COMPAT_SCHEMA, "fs_version": "26.120", "commands": commands}
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path


class TestQaCompat:
    """P0400-COMPAT: compat reports, promotions and the executable identity.

    PFS-2003.10.03: a probe report row shows a missing observation as missing.
    PFS-2102.032, PFS-2088.016: promotions go into the repository's own database.
    PFS-2102.030: a partial report is refused in the catalogued type.
    PFS-2102.031: a broken promotion keeps the row's edition page citation.
    PFS-2102.003: a registry with no build recorded confirms nothing.
    """

    @staticmethod
    def test_p0400_compat_a_missing_observation_reads_missing(tmp_path):
        """P0400-COMPAT (FR-01, FR-25, PFS-2003.10.03): missing observation stays missing."""
        result = ProbeResult(
            command="STOP",
            outcome=ProbeOutcome.VERIFIED,
            detail="script processing continued past the command",
            expected="the script halts at the command",
            observation=None,
        )
        run = ProbeRun(
            version="26.120",
            solver_identity=(),
            fs_exe_name="FlightStream.exe",
            package_version="0.40.0",
            results=(result,),
        )
        yaml_path, md_path = write_compat_report(run, tmp_path, date="2026-10-12")
        row = next(
            line for line in md_path.read_text(encoding="utf-8").splitlines() if "| STOP |" in line
        )
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        assert cells[3] == "the script halts at the command"
        assert cells[4] == "missing"
        body = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))["commands"]["STOP"]
        assert body["observation"] is None
        assert body["expected"] == "the script halts at the command"

    @staticmethod
    def test_p0400_compat_the_database_defaults_to_the_repository_and_never_leaves_it(tmp_path):
        """P0400-COMPAT (PFS-2102.032, PFS-2088.016) the promotion writes the tree --root names."""
        root = tmp_path / "repo"
        inside = _qa_compat___commands(root / "src" / "pyflightstream" / "commands")
        assert compat.resolve_commands_dir(root) == inside.resolve()
        outside = _qa_compat___commands(tmp_path / "elsewhere" / "commands")
        report = _qa_compat___report(root, {"STOP": {"outcome": "verified", "detail": "halted"}})
        before = (outside / "script_controls.yaml").read_text(encoding="utf-8")
        with pytest.raises(QaEvidenceError, match="not under the repository root"):
            apply_compat(report, repo_root=root, commands_dir=outside)
        assert (outside / "script_controls.yaml").read_text(encoding="utf-8") == before

    @staticmethod
    @pytest.mark.parametrize(
        "document",
        [
            {"fs_version": "26.120", "commands": None},
            {"fs_version": "26.120", "commands": {"STOP": "verified"}},
            {"commands": {"STOP": {"outcome": "verified"}}},
        ],
    )
    def test_p0400_compat_a_partial_report_is_refused_in_the_catalogued_type(tmp_path, document):
        """P0400-COMPAT (PFS-2102.030) no KeyError, TypeError or AttributeError escapes."""
        commands_dir = _qa_compat___commands(tmp_path / "commands")
        path = tmp_path / "reports" / "compat" / "CMP-26120_2026-10-12.yaml"
        path.parent.mkdir(parents=True)
        path.write_text(yaml.safe_dump({"schema": COMPAT_SCHEMA, **document}), encoding="utf-8")
        with pytest.raises(QaEvidenceError):
            apply_compat(path, repo_root=tmp_path, commands_dir=commands_dir)

    @staticmethod
    def test_p0400_compat_a_broken_promotion_keeps_the_page_citation(tmp_path):
        """P0400-COMPAT (PFS-2102.031) the edition's note survives and the measurement is added."""
        commands_dir = _qa_compat___commands(tmp_path / "commands")
        report = _qa_compat___report(
            tmp_path, {"STOP": {"outcome": "broken", "detail": "no halt observed"}}
        )
        apply_compat(report, repo_root=tmp_path, commands_dir=commands_dir)
        row = yaml.safe_load((commands_dir / "script_controls.yaml").read_text(encoding="utf-8"))
        entry = row["STOP"]["versions"]["26.120"]
        assert entry["status"] == "broken"
        assert "FSM-26.100 p.358" in entry["note"], entry["note"]
        assert "no halt observed" in entry["note"], entry["note"]
        apply_compat(report, repo_root=tmp_path, commands_dir=commands_dir)
        again = yaml.safe_load((commands_dir / "script_controls.yaml").read_text(encoding="utf-8"))
        assert again["STOP"]["versions"]["26.120"]["note"] == entry["note"], "promoted twice"

    @staticmethod
    def test_p0400_compat_a_registry_without_a_build_confirms_nothing(tmp_path, monkeypatch):
        """P0400-COMPAT (PFS-2102.003) no match is claimed against a build never recorded."""
        exe = tmp_path / "FlightStream.exe"
        exe.write_bytes(b"bytes of a solver")
        real = compat.resolve
        monkeypatch.setattr(
            compat, "resolve", lambda version: dataclasses.replace(real(version), build=None)
        )
        answer = classify_executable(
            exe,
            version="26.123",
            baseline={"26.123": {"sha256": "0" * 64}},
            printed_build="8112026",
        )
        assert answer.verdict is ExecutableVerdict.UNKNOWN
        assert "holds no build" in answer.message


_QA_COST__SHA = "a" * 64


def _qa_cost___record(
    run_id: str, *, wall_time_s: float, status=RunStatus.CONVERGED, **extra
) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        sim_id="1",
        point={"alpha_deg": 0.0},
        fs_version_requested="26.120",
        fs_build="2122026",
        fs_exe_sha256=_QA_COST__SHA,
        package_version="0.40.0",
        script_sha256="0" * 64,
        raw_flag=False,
        status=status,
        wall_time_s=wall_time_s,
        **extra,
    )


def _qa_cost___job() -> RunRecord:
    ran = [
        # A run status as the manifest writes it (PFS-2093.005 reads it at load).
        {"tag": tag, "point": {"alpha_deg": alpha}, "status": "CONVERGED"}
        for tag, alpha in (("AL+000", 0.0), ("AL+002", 2.0), ("AL+004", 4.0))
    ]
    return _qa_cost___record("c/sim_1/sweep", wall_time_s=90.0, points_ran=ran)


class TestQaCost:
    """P0400-COSTJOB: the cost view's rows and means.

    PFS-2094.002: a steady sweep JOB record is one row, labelled by its sweep, and
    its time is never shown as its first point's.
    PFS-2094.003: runs that reached no answer are kept apart from the mean that
    compare() pairs on.
    """

    @staticmethod
    def test_p0400_costjob_a_job_record_is_one_sweep_row_and_never_its_first_point():
        """P0400-COSTJOB (PFS-2094.002) the polar's time is labelled by the sweep."""
        view = cost_view([_qa_cost___job()])
        (row,) = view.rows()
        assert row["point"] == "sweep of 3 points: AL+000, AL+002, AL+004", row
        assert "alpha_deg" not in str(row["point"])
        assert view.wall_time_s(view.points[0], view.builds[0]) == pytest.approx(90.0)
        assert cost_rows([_qa_cost___job()])[0]["point"] == row["point"]

    @staticmethod
    def test_p0400_costjob_a_job_and_a_point_record_of_one_sim_are_two_rows():
        """P0400-COSTJOB (PFS-2094.002) the job does not average into the first point's cell."""
        view = cost_view([_qa_cost___job(), _qa_cost___record("c/sim_1/AL+000", wall_time_s=30.0)])
        times = {row["point"]: row[view.builds[0].label] for row in view.rows()}
        assert times == {"alpha_deg=0.0": 30.0, "sweep of 3 points: AL+000, AL+002, AL+004": 90.0}

    @staticmethod
    def test_p0400_costjob_a_failed_run_is_kept_apart_from_the_mean():
        """P0400-COSTJOB (PFS-2094.003) 10 s converged beside 2 s failed is a 10 s answer."""
        view = cost_view(
            [
                _qa_cost___record("r1", wall_time_s=10.0),
                _qa_cost___record("r2", wall_time_s=2.0, status=RunStatus.FAILED_EXECUTION),
            ]
        )
        cell = view.cell(view.points[0], view.builds[0])
        assert cell.run_count == 2
        assert cell.excluded_count == 1
        assert cell.samples == (10.0,)
        assert cell.excluded_samples == (2.0,)
        assert cell.wall_time_s == pytest.approx(10.0)

    @staticmethod
    def test_p0400_costjob_compare_pairs_on_answers_only():
        """P0400-COSTJOB (PFS-2094.003) a build that only failed has no time to an answer to pair."""  # noqa: E501
        failed_fast = RunRecord.model_validate(
            {
                **_qa_cost___record(
                    "r2", wall_time_s=1.0, status=RunStatus.FAILED_EXECUTION
                ).model_dump(),
                "fs_exe_sha256": "b" * 64,
            }
        )
        view = cost_view([_qa_cost___record("r1", wall_time_s=10.0), failed_fast])
        base, cand = view.builds
        comparison = view.compare(base, cand)
        assert comparison.paired == ()
        assert len(comparison.unpaired) == 1


_QA_MATRIX__TIER3 = Path(__file__).resolve().parents[1] / "tier3_licensed"


def _qa_matrix___record(
    run_id: str, *, status=RunStatus.CONVERGED, alpha=4.0, sha=None
) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        sim_id=run_id.split("/")[1].removeprefix("sim_"),
        point={} if alpha is None else {"alpha": alpha},
        fs_version_requested="26.120",
        fs_exe_sha256=sha,
        package_version="0.40.0",
        script_sha256="0" * 64,
        raw_flag=False,
        status=status,
        matrix_stem="matriz_physics",
    )


_QA_MATRIX__ROW = SimpleNamespace(pol="5002", description="PHY-02_full_span_baseline_at_4_deg")


def _qa_matrix___workspace(tmp_path: Path, build: str = "26.120", entry: str | None = None) -> Path:
    root = tmp_path / "ws"
    (root / "inputs").mkdir(parents=True)
    text = (_QA_MATRIX__TIER3 / "matriz_physics.fs").read_text(encoding="utf-8")
    (root / "matriz_physics.fs").write_text(
        text.replace("| 26.120   |", f"| {build:<8} |"), encoding="utf-8"
    )
    registry = entry or (_QA_MATRIX__TIER3 / "inputs" / "executables.toml").read_text(
        encoding="utf-8"
    )
    (root / "inputs" / "executables.toml").write_text(registry, encoding="utf-8")
    return root


def _qa_matrix___fake_workspace(root: Path, records: list[RunRecord]):
    return SimpleNamespace(
        root=root, read_manifest=lambda: records, manifest_path=root / "runs.json"
    )


class TestQaMatrix:
    """P0400-PHYSRUN: the physics matrix driver, its reduction, and the pyfs-qa front of it.

    PFS-2085.016: a steady point stopped at the iteration limit is not judged.
    PFS-2085.017: one report is evidence of one executable.
    PFS-2102.034: only the campaign that ran is reduced; one record per point; one point per case.
    PFS-2102.006: the report version is the one the build's registry entry declares.
    PFS-2102.007: a case that cannot be reduced is reported, and a failed reduction is post-run.
    PFS-2102.008: both drift sides are checked before either runs.
    PFS-2102.009: a record without an alpha axis is refused.
    PFS-2102.002, PFS-2102.010, PFS-2102.015: pyfs-qa refusals reach the operator without a traceback.
    """  # noqa: E501

    @staticmethod
    def test_p0400_physrun_an_unsettled_steady_point_is_not_judged():
        """P0400-PHYSRUN (PFS-2085.016) MAX_ITER_REACHED makes the case an error, not a pass."""
        records = [_qa_matrix___record("ws/sim_5002/AL+004", status=RunStatus.MAX_ITER_REACHED)]
        with pytest.raises(QaEvidenceError, match="MAX_ITER_REACHED"):
            matrix_module._points_of_row(None, _QA_MATRIX__ROW, records)

    @staticmethod
    def test_p0400_physrun_two_records_of_one_point_are_refused():
        """P0400-PHYSRUN (PFS-2102.034) a point recorded twice never reaches a fit or an unpack."""
        records = [
            _qa_matrix___record("ws/sim_5002/AL+004"),
            _qa_matrix___record("ws/sim_5002/AL+004b"),
        ]
        with pytest.raises(QaEvidenceError, match="more than one record of one point"):
            matrix_module._points_of_row(None, _QA_MATRIX__ROW, records)

    @staticmethod
    def test_p0400_physrun_only_the_campaign_that_ran_is_reduced():
        """P0400-PHYSRUN (PFS-2102.034) the run under --name and the run under the directory differ."""  # noqa: E501
        records = [
            _qa_matrix___record("ws/sim_5002/AL+004"),
            _qa_matrix___record("other/sim_5002/AL+004"),
        ]
        workspace = SimpleNamespace(read_manifest=lambda: records)
        by_row = matrix_module._records_by_row(workspace, "matriz_physics", "ws")
        assert [r.run_id for r in by_row["5002"]] == ["ws/sim_5002/AL+004"]

    @staticmethod
    def test_p0400_physrun_a_single_point_case_refuses_a_sweep():
        """P0400-PHYSRUN (PFS-2102.034) a QaEvidenceError, never a bare unpacking ValueError."""
        from pyflightstream.qa.physics import PointResult

        points = [PointResult(a, {"CL": 0.1}, 10, True, f"p{a:g}") for a in (2.0, 4.0)]
        with pytest.raises(QaEvidenceError, match="reads one point"):
            matrix_module._one_point("PHY-05", _QA_MATRIX__ROW, points)

    @staticmethod
    def test_p0400_physrun_a_record_without_alpha_is_refused():
        """P0400-PHYSRUN (PFS-2102.009) an unknown incidence is never read as 0 deg."""
        with pytest.raises(QaEvidenceError, match="no alpha axis"):
            matrix_module.point_result(None, _qa_matrix___record("ws/sim_5001/X", alpha=None))

    @staticmethod
    def test_p0400_physrun_two_executables_of_one_version_are_refused(tmp_path):
        """P0400-PHYSRUN (PFS-2085.017) both digests are named; nothing is pooled."""
        root = _qa_matrix___workspace(tmp_path)
        records = [
            _qa_matrix___record("ws/sim_5002/AL+004", sha="a" * 64),
            _qa_matrix___record("ws/sim_5003/AL+004", sha="b" * 64),
        ]
        with pytest.raises(PhysicsEnvironmentError, match="fs_exe_sha256") as refused:
            matrix_module.reduce_physics(
                _qa_matrix___fake_workspace(root, records), root / "matriz_physics.fs"
            )
        assert "a" * 64 in str(refused.value) and "b" * 64 in str(refused.value)

    @staticmethod
    def test_p0400_physrun_a_case_that_cannot_be_reduced_is_reported(tmp_path, monkeypatch):
        """P0400-PHYSRUN (PFS-2102.007) an archived loads table is the case's error, not the run's."""  # noqa: E501

        def archived(workspace, record):
            raise FileNotFoundError(f"{record.run_id}: loads table archived")

        monkeypatch.setattr(matrix_module, "parse_run_loads", archived)
        root = _qa_matrix___workspace(tmp_path)
        records = [_qa_matrix___record("ws/sim_5005/AL+000", alpha=0.0)]
        run = matrix_module.reduce_physics(
            _qa_matrix___fake_workspace(root, records), root / "matriz_physics.fs"
        )
        errors = {result.case_id: result.error for result in run.results}
        assert "FileNotFoundError" in errors["PHY-05"], errors

    @staticmethod
    def test_p0400_physrun_a_failed_reduction_says_the_matrix_ran(tmp_path, monkeypatch):
        """P0400-PHYSRUN (PFS-2102.007, PFS-2102.034) never the pre-run 'matrix not run'."""
        root = _qa_matrix___workspace(tmp_path)
        monkeypatch.setattr(matrix_module, "run_physics_matrix", lambda *a, **k: [])

        def failing(*args, **kwargs):
            raise ValueError("too many values to unpack")

        monkeypatch.setattr(matrix_module, "reduce_physics", failing)
        with pytest.raises(PhysicsEnvironmentError, match="the matrix ran"):
            matrix_module.physics_from_workspace(root)

    @staticmethod
    def test_p0400_physrun_the_report_version_is_the_declared_one(tmp_path):
        """P0400-PHYSRUN (PFS-2102.006) a build id is a name, never read as a version."""
        entry = '"main" = { path = "FlightStream.exe", version = "26.120" }\n'
        root = _qa_matrix___workspace(tmp_path, build="main", entry=entry)
        assert matrix_module.physics_build(root / "matriz_physics.fs") == "26.120"
        bare = _qa_matrix___workspace(
            tmp_path / "bare", build="main", entry='"main" = "FlightStream.exe"\n'
        )
        with pytest.raises(PhysicsEnvironmentError, match="declares no version"):
            matrix_module.physics_build(bare / "matriz_physics.fs")

    @staticmethod
    def test_p0400_physrun_both_drift_sides_are_checked_before_either_runs(tmp_path, monkeypatch):
        """P0400-PHYSRUN (PFS-2102.008) side B's typo costs no seat on side A."""

        def no_seat(*args, **kwargs):
            raise AssertionError("side a ran before side b was checked")

        monkeypatch.setattr(matrix_module, "run_physics_matrix", no_seat)
        root = _qa_matrix___workspace(tmp_path)
        workroot = tmp_path / "drift"
        with pytest.raises(PhysicsEnvironmentError, match="is not a file"):
            matrix_module.drift_from_workspace(
                root,
                "26.120",
                "26.123",
                fs_exes={"26.120": sys.executable, "26.123": str(tmp_path / "nowhere.exe")},
                workroot=workroot,
            )
        assert not workroot.exists() or not any(workroot.iterdir())
        (workroot / "b_26123").mkdir(parents=True)
        with pytest.raises(PhysicsEnvironmentError, match="already exists"):
            matrix_module.drift_from_workspace(
                root,
                "26.120",
                "26.123",
                fs_exes={"26.120": sys.executable, "26.123": sys.executable},
                workroot=workroot,
            )
        assert not (workroot / "a_26120").exists()

    @staticmethod
    def test_p0400_physrun_the_drift_pre_flight_checks_the_executables(
        tmp_path, monkeypatch, capsys
    ):
        """P0400-PHYSRUN (PFS-2102.008) pyfs-qa drift refuses before it hands over a seat."""
        from pyflightstream.qa import cli as cli_module

        monkeypatch.setattr(
            cli_module, "drift_from_workspace", lambda *a, **k: pytest.fail("a seat was spent")
        )
        root = _qa_matrix___workspace(tmp_path)
        code = main(
            [
                "drift",
                "--workspace",
                str(root),
                "--fs-versions",
                "26.120,26.123",
                "--fs-exe",
                f"26.120={sys.executable}",
                "--fs-exe",
                f"26.123={tmp_path / 'nowhere.exe'}",
                "--workroot",
                str(tmp_path / "drift"),
                "--report-dir",
                str(tmp_path / "reports"),
            ]
        )
        assert code == 2
        assert "nothing run" in capsys.readouterr().err

    @staticmethod
    def test_p0400_physrun_a_missing_executable_is_refused_without_a_traceback(tmp_path, capsys):
        """P0400-PHYSRUN (PFS-2102.002) pyfs-qa probe with a mistyped --fs-exe."""
        code = main(
            [
                "probe",
                "--fs-version",
                "26.123",
                "--fs-exe",
                str(tmp_path / "nowhere.exe"),
                "--workroot",
                str(tmp_path / "work"),
                "--report-dir",
                str(tmp_path / "reports"),
            ]
        )
        assert code == 2
        assert "nothing run" in capsys.readouterr().err

    @staticmethod
    @pytest.mark.parametrize("label", ["pilot/2", "pilot" + chr(0), "pilot" + chr(1)])
    def test_p0400_physrun_a_label_that_is_no_file_name_is_refused_before_the_run(
        tmp_path, capsys, label, monkeypatch
    ):
        """P0400-PHYSRUN (PFS-2102.015) pilot/2 is refused at the pre-flight, not at the write."""
        from pyflightstream.qa.reports import report_paths

        monkeypatch.setattr(
            "pyflightstream.qa.cli.probe_version", lambda *a, **k: pytest.fail("a seat was spent")
        )

        with pytest.raises(QaEvidenceError, match="file-name token"):
            report_paths(
                tmp_path, series="PHY", versions=["26.120"], date="2026-10-12", label="10:30"
            )
        code = main(
            [
                "probe",
                "--fs-version",
                "26.123",
                "--fs-exe",
                sys.executable,
                "--label",
                label,
                "--workroot",
                str(tmp_path / "work"),
                "--report-dir",
                str(tmp_path / "reports"),
            ]
        )
        assert code == 2
        assert "file-name token" in capsys.readouterr().err

    @staticmethod
    def test_p0400_physrun_an_unreadable_manifest_is_refused_by_pyfs_qa_cost(tmp_path, capsys):
        """P0400-PHYSRUN (PFS-2102.010) a corrupt runs.json is a refusal, not a traceback."""
        (tmp_path / "runs.json").write_text("{", encoding="utf-8")
        assert main(["cost", str(tmp_path)]) == 2
        assert "no cost read" in capsys.readouterr().err


def _qa_physics___points(alphas=(0.0, 2.0, 4.0, 6.0), drag="CDi") -> list[PointResult]:
    return [
        PointResult(
            alpha_deg=alpha,
            total={"CL": 0.0875 * alpha, drag: 0.001 + 0.0004 * alpha**2},
            iterations=300,
            converged=True,
        )
        for alpha in alphas
    ]


def _qa_physics___run(
    points: list[PointResult], *, reference: CaseReference | None = None
) -> PhysicsRun:
    metrics = phy01_metrics(points)
    return PhysicsRun(
        version="26.120",
        fs_exe_name="FlightStream.exe",
        package_version="0.40.0",
        results=(
            CaseResult(
                case_id="PHY-01",
                title=PHYSICS_CASES["PHY-01"].title,
                geometry="test wing",
                points=tuple(points),
                metrics=metrics,
                verdicts=compare_metrics(metrics, reference),
                reference=reference,
            ),
        ),
    )


def _qa_physics___seeded(tmp_path):
    refs = tmp_path / "refs"
    full, _ = write_physics_report(
        _qa_physics___run(_qa_physics___points()), tmp_path, date="2026-10-11"
    )
    update_reference(
        "PHY-01", full, "seed (test)", references_dir=refs, date="2026-10-11", repo_root=tmp_path
    )
    partial, _ = write_physics_report(
        _qa_physics___run(_qa_physics___points((0.0, 2.0, 4.0))), tmp_path, date="2026-10-12"
    )
    return refs, partial


def _qa_physics___case(case_id: str, metrics: dict[str, float]) -> CaseResult:
    return CaseResult(case_id=case_id, title=case_id, geometry="test", metrics=metrics)


def _qa_physics___physics(version: str, *results: CaseResult) -> PhysicsRun:
    return PhysicsRun(
        version=version, fs_exe_name="FlightStream.exe", package_version="0.40.0", results=results
    )


class TestQaPhysics:
    """P0400-PHYSREF: the physics reductions, judgments, report and reference updates.

    PFS-2102.035: the Markdown drag column carries the name the point's table prints.
    PFS-2085.015: a reference metric the run did not produce judges FAIL and is counted.
    PFS-2102.009: PHY-01 refuses a sweep without 4 deg or with fewer than two angles.
    PFS-2102.010: evidence YAML read failures are QaEvidenceError, and so is a reference missing a key.
    PFS-2102.011: update_reference refuses to lose a reference metric unless told to drop it.
    PFS-2102.012: update_reference records a repository-relative source path.
    PFS-2102.036: a relative band centred on zero is refused.
    """  # noqa: E501

    @staticmethod
    def test_p0400_physref_the_drag_column_is_the_one_the_table_prints(tmp_path):
        """P0400-PHYSREF (PFS-2102.035) a CDp table is printed under CDp, never as nan under CDi."""
        _, md_path = write_physics_report(
            _qa_physics___run(_qa_physics___points(drag="CDp")), tmp_path, date="2026-10-12"
        )
        markdown = md_path.read_text(encoding="utf-8")
        assert "| point | alpha (deg) | CL | CDp | iterations | converged |" in markdown
        assert "nan" not in markdown

    @staticmethod
    def test_p0400_physref_an_unproduced_reference_metric_fails_and_is_counted(tmp_path):
        """P0400-PHYSREF (PFS-2085.015) a reference metric the run lacks is a FAIL, not a silence."""  # noqa: E501
        band = ReferenceBand(value=0.35, warn=0.02, fail=0.05, kind="rel")
        reference = CaseReference(
            case_id="PHY-01",
            fs_version_basis="26.120",
            updated="2026-10-12",
            reason="test",
            metrics={"CL_a4": band, "CL_a8": band},
        )
        verdicts = compare_metrics({"CL_a4": 0.35}, reference)
        assert verdicts == {"CL_a4": Verdict.PASS, "CL_a8": Verdict.FAIL}
        run = _qa_physics___run(_qa_physics___points(), reference=reference)
        assert run.verdict_counts()["fail"] == 1
        _, md_path = write_physics_report(run, tmp_path, date="2026-10-12")
        assert "| CL_a8 | not produced | 0.35000 |" in md_path.read_text(encoding="utf-8")

    @staticmethod
    @pytest.mark.parametrize(
        ("alphas", "words"),
        [((0.0, 2.0, 6.0), "no 4 deg"), ((4.0,), "at least two angles")],
    )
    def test_p0400_physref_phy01_refuses_a_sweep_it_cannot_reduce(alphas, words):
        """P0400-PHYSREF (PFS-2102.009) no StopIteration, no slope fitted from one angle."""
        with pytest.raises(QaEvidenceError, match=words):
            phy01_metrics(_qa_physics___points(alphas))

    @staticmethod
    def test_p0400_physref_a_missing_or_broken_evidence_file_is_refused_in_the_catalogued_type(
        tmp_path,
    ):
        """P0400-PHYSREF (PFS-2102.010) no FileNotFoundError, YAMLError or KeyError escapes."""
        with pytest.raises(QaEvidenceError, match="cannot be read"):
            read_physics_report(tmp_path / "PHY-26120_2026-10-12.yaml")
        refs = tmp_path / "refs"
        refs.mkdir()
        (refs / "PHY-01.yaml").write_text("schema: [unclosed\n", encoding="utf-8")
        with pytest.raises(QaEvidenceError, match="not parsable YAML"):
            load_reference("PHY-01", refs)
        (refs / "PHY-01.yaml").write_text(
            "schema: pyflightstream-physics-reference/1\ncase: PHY-01\nmetrics: {}\n",
            encoding="utf-8",
        )
        with pytest.raises(QaEvidenceError, match="fs_version_basis"):
            load_reference("PHY-01", refs)

    @staticmethod
    def test_p0400_physref_an_update_never_loses_a_curated_metric_silently(tmp_path):
        """P0400-PHYSREF (PFS-2102.011) a report without CL_a6 is refused unless CL_a6 is dropped."""  # noqa: E501
        refs, partial = _qa_physics___seeded(tmp_path)
        with pytest.raises(QaEvidenceError, match="CL_a6"):
            update_reference(
                "PHY-01", partial, "partial (test)", references_dir=refs, repo_root=tmp_path
            )
        assert "CL_a6" in load_reference("PHY-01", refs).metrics
        update_reference(
            "PHY-01",
            partial,
            "drops 6 deg (test)",
            references_dir=refs,
            repo_root=tmp_path,
            drop=["CL_a6"],
        )
        assert "CL_a6" not in load_reference("PHY-01", refs).metrics

    @staticmethod
    def test_p0400_physref_the_source_report_is_repository_relative(tmp_path):
        """P0400-PHYSREF (PFS-2102.012) no machine path reaches a committed reference."""
        refs = tmp_path / "refs"
        reports = tmp_path / "repo" / "reports" / "physics"
        report, _ = write_physics_report(
            _qa_physics___run(_qa_physics___points()), reports, date="2026-10-12"
        )
        path = update_reference(
            "PHY-01", report, "seed (test)", references_dir=refs, repo_root=tmp_path / "repo"
        )
        stored = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert stored["source_report"] == "reports/physics/PHY-26120_2026-10-12.yaml"
        with pytest.raises(QaEvidenceError, match="outside"):
            update_reference(
                "PHY-01", report, "seed (test)", references_dir=refs, repo_root=tmp_path / "other"
            )

    @staticmethod
    def test_p0400_physref_a_relative_band_centred_on_zero_is_refused():
        """P0400-PHYSREF (PFS-2102.036) a zero-width band cannot judge; it is refused with the cause."""  # noqa: E501
        with pytest.raises(QaEvidenceError, match="kind 'abs'"):
            ReferenceBand(value=0.0, warn=0.02, fail=0.05, kind="rel")
        assert (
            ReferenceBand(value=0.0, warn=0.02, fail=0.05, kind="abs").judge(0.01) is Verdict.PASS
        )

    @staticmethod
    def test_p0400_physref_drift_reports_what_one_side_lacks():
        """P0400-PHYSREF (PFS-2102.004) a one-sided metric fails and a one-sided case aborts."""
        from pyflightstream.qa.drift import diff_runs

        run_a = _qa_physics___physics(
            "26.124",
            _qa_physics___case("PHY-01", {"CL_a4": 0.35, "CDi_a4": 0.01}),
            _qa_physics___case("PHY-05", {}),
        )
        run_b = _qa_physics___physics(
            "26.125", _qa_physics___case("PHY-01", {"CL_a4": 0.35, "CDp_a4": 0.01})
        )
        drift = diff_runs(run_a, run_b)
        by_case = {result.case_id: result for result in drift.results}
        assert by_case["PHY-01"].metrics["CDi_a4"].verdict is Verdict.FAIL
        assert by_case["PHY-01"].metrics["CDp_a4"].verdict is Verdict.FAIL
        assert by_case["PHY-01"].metrics["CL_a4"].verdict is Verdict.PASS
        assert drift.verdict_counts()["fail"] == 2
        assert "26.124 only" in by_case["PHY-05"].error

    @staticmethod
    def test_p0400_physref_drift_from_a_zero_baseline_does_not_crash():
        """P0400-PHYSREF (PFS-2102.036) a relative metric at exactly zero on side A has no band."""
        from pyflightstream.qa.drift import diff_runs

        drift = diff_runs(
            _qa_physics___physics("26.120", _qa_physics___case("PHY-01", {"CL_a4": 0.0})),
            _qa_physics___physics("26.123", _qa_physics___case("PHY-01", {"CL_a4": 0.001})),
        )
        assert drift.results[0].metrics["CL_a4"].verdict is Verdict.NO_REFERENCE


class TestQaProbeEmission:
    """P0400-PROBEEMIT: the probe import and export entry points of ``pyflightstream.probes``.

    PFS-2100.023: the import's ``units`` names the unit the csv was written in.
    PFS-2104.015: the import takes a frame label like ``helpers.probes_from_file``.
    PFS-2081.26: a refused export collision names the entry point the caller used.
    """

    @staticmethod
    def test_p0400_probeemit_units_doc_names_the_simulation_length_unit():
        """P0400-PROBEEMIT (PFS-2100.023) the units parameter says which unit the csv is in."""
        doc = emit_probe_import.__doc__ or ""
        units_section = doc.split("units : str", 1)[1].split("frame :", 1)[0]
        assert "simulation length unit" in units_section, (
            "the units parameter does not tell the reader that the csv write_probe_csv "
            "writes is in the case's simulation length unit"
        )

    @staticmethod
    def test_p0400_probeemit_import_takes_a_frame_label():
        """P0400-PROBEEMIT (PFS-2104.015) a created frame is cited by its label, as in the helper."""  # noqa: E501
        hints = typing.get_type_hints(emit_probe_import)
        assert hints["frame"] == int | str, "emit_probe_import still types frame as an index only"
        script = Script(version="26.120")
        script.emit("CREATE_NEW_COORDINATE_SYSTEM", label="wake_frame")
        emit_probe_import(script, "C:/probes/lattice.txt", units="METER", frame="wake_frame")
        assert "PROBE_POINTS_IMPORT\nUNITS METER\nFRAME 2\n" in script.render()

    @staticmethod
    def test_p0400_probeemit_collision_remedy_names_emit_probe_export():
        """P0400-PROBEEMIT (PFS-2081.26) the remedy names the function the caller called."""
        script = Script(version="26.120")
        _qa_probe_emission__emit_probe_export(script, "survey.csv")
        with pytest.raises(CommandArgumentError) as refused:
            _qa_probe_emission__emit_probe_export(script, "survey.csv", update=False)
        message = str(refused.value)
        assert "Give emit_probe_export a path" in message, message
        assert "Give export_probes" not in message, message
        assert script.render().count("EXPORT_PROBE_POINTS") == 1


_QA_PROBE_GATE__CUBE = Path(__file__).parent / "fixtures" / "cube.obj"


_QA_PROBE_GATE__BOTTOM_FACE = ("f 1 3 2", "f 1 4 3")


def _qa_probe_gate___open_box(tmp_path: Path) -> Path:
    """The unit cube with its bottom face removed: open, so containment is undefined."""
    lines = _QA_PROBE_GATE__CUBE.read_text(encoding="utf-8").splitlines()
    path = tmp_path / "open_box.obj"
    path.write_text(
        "\n".join(x for x in lines if x not in _QA_PROBE_GATE__BOTTOM_FACE) + "\n", encoding="utf-8"
    )
    return path


def _qa_probe_gate___grid(*, z: float = 0.0, band: RefinementBand | None = None) -> PlanarProbeGrid:
    return PlanarProbeGrid(
        frame=FrameDefinition(origin=(0.0, 0.0, z), x_axis=(1.0, 0.0, 0.0), y_axis=(0.0, 1.0, 0.0)),
        u=AxisSpec(start=-1.0, stop=1.0, spacing=0.5),
        v=AxisSpec(start=-1.0, stop=1.0, spacing=0.5),
        refinement=band,
    )


class TestQaProbeGate:
    """P0400-PROBEGATE: what the probe geometry gate asks of the mesh, and what it records.

    PFS-2088.007: culling without a mesh is refused rather than culling nothing.
    PFS-2097.007, PFS-2100.010: the watertight check follows ``cull``; the refusal's
    own remedy works through ``mesh_path``, and a band asks no containment without it.
    PFS-2097.008: an open mesh passed as an object is refused when the gate culls.
    PFS-2103.001: ``mesh`` and ``mesh_path`` together are refused.
    """

    @staticmethod
    @pytest.fixture(autouse=True, scope="class")
    def _optional_dependencies():
        pytest.importorskip("trimesh")

    @staticmethod
    def test_p0400_probegate_cull_without_a_mesh_is_refused():
        """P0400-PROBEGATE (PFS-2088.007) the default cull=True with no mesh refuses."""
        with pytest.raises(ProbeGeometryError, match="cull=False"):
            apply_geometry_gate(_qa_probe_gate___grid())
        assert apply_geometry_gate(_qa_probe_gate___grid(), cull=False).report.base_culled == 0

    @staticmethod
    def test_p0400_probegate_the_open_mesh_remedy_works_through_mesh_path(tmp_path):
        """P0400-PROBEGATE (PFS-2097.007, PFS-2100.010) follow the refusal's remedy and it runs."""
        box = _qa_probe_gate___open_box(tmp_path)
        with pytest.raises(OpenMeshError) as refused:
            apply_geometry_gate(_qa_probe_gate___grid(), mesh_path=box, standoff=0.1)
        assert "cull=False" in str(refused.value), str(refused.value)
        planned = apply_geometry_gate(
            _qa_probe_gate___grid(), mesh_path=box, cull=False, standoff=0.1
        )
        assert planned.report.base_culled == 0
        assert planned.report.base_standoff_culled > 0
        assert planned.report.mesh_path == str(box)

    @staticmethod
    def test_p0400_probegate_a_band_without_cull_asks_no_containment(tmp_path, monkeypatch):
        """P0400-PROBEGATE (PFS-2097.007) without culling the band flags by distance alone."""
        mesh = load_surface_mesh(_qa_probe_gate___open_box(tmp_path), require_watertight=False)

        def no_containment(mesh, points):
            raise AssertionError("containment was asked of a mesh the gate never checked")

        monkeypatch.setattr(gate, "_inside", no_containment)
        planned = apply_geometry_gate(
            _qa_probe_gate___grid(z=0.6, band=RefinementBand(distance=0.15, factor=2)),
            mesh,
            cull=False,
        )
        assert planned.report.refined_added == 16
        assert np.all(planned.points[25:, 2] == 0.6)

    @staticmethod
    def test_p0400_probegate_an_open_mesh_object_is_refused_when_culling(tmp_path):
        """P0400-PROBEGATE (PFS-2097.008) an open box passed as mesh= with cull=True refuses."""
        mesh = load_surface_mesh(_qa_probe_gate___open_box(tmp_path), require_watertight=False)
        assert not mesh.is_watertight
        with pytest.raises(OpenMeshError, match="not watertight"):
            apply_geometry_gate(_qa_probe_gate___grid(), mesh)

    @staticmethod
    def test_p0400_probegate_mesh_and_mesh_path_together_are_refused():
        """P0400-PROBEGATE (PFS-2103.001) the report never names a file the gate did not load."""
        mesh = load_surface_mesh(_QA_PROBE_GATE__CUBE)
        with pytest.raises(ProbeGeometryError, match="not both"):
            apply_geometry_gate(_qa_probe_gate___grid(), mesh, mesh_path=_QA_PROBE_GATE__CUBE)
        assert apply_geometry_gate(_qa_probe_gate___grid(), mesh).report.mesh_path is None
        assert apply_geometry_gate(
            _qa_probe_gate___grid(), mesh_path=_QA_PROBE_GATE__CUBE
        ).report.mesh_path == str(_QA_PROBE_GATE__CUBE)


def _qa_probe_planar___plan(points: np.ndarray) -> PlannedProbes:
    grid = PlanarProbeGrid(
        frame=FrameDefinition(x_axis=(1.0, 0.0, 0.0), y_axis=(0.0, 1.0, 0.0)),
        u=AxisSpec(start=0.0, stop=1.0, count=2),
        v=AxisSpec(start=0.0, stop=1.0, count=2),
    )
    report = GeometryGateReport(
        base_total=4, base_culled=4 - len(points), refined_added=0, refined_culled=0
    )
    return PlannedProbes(grid=grid, points=points, report=report)


_QA_PROBE_PLANAR__PLACED = np.array(
    [[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0]]
)


class TestQaProbePlanar:
    """P0400-PROBEPLAN: the planned-probe contract on degenerate arrays, and the axis spacing bound.

    PFS-2095.022: verify_positions refuses non-finite rows, accepts an empty plan
    against an empty export, and an empty plan survives its json round trip.
    PFS-2104.016: a uniform axis never delivers an element larger than requested.
    """

    @staticmethod
    def test_p0400_probeplan_one_nan_row_is_refused_and_named():
        """P0400-PROBEPLAN (PFS-2095.022) a NaN row never passes the tolerance check."""
        exported = _QA_PROBE_PLANAR__PLACED.copy()
        exported[2, 1] = np.nan
        with pytest.raises(ProbeGeometryError, match="row 2"):
            _qa_probe_planar___plan(_QA_PROBE_PLANAR__PLACED).verify_positions(exported)

    @staticmethod
    def test_p0400_probeplan_an_all_nan_export_is_refused():
        """P0400-PROBEPLAN (PFS-2095.022) an export of NaN only is refused, not accepted."""
        with pytest.raises(ProbeGeometryError, match="4 of 4"):
            _qa_probe_planar___plan(_QA_PROBE_PLANAR__PLACED).verify_positions(
                np.full_like(_QA_PROBE_PLANAR__PLACED, np.nan)
            )

    @staticmethod
    def test_p0400_probeplan_an_empty_plan_matches_an_empty_export_after_a_round_trip():
        """P0400-PROBEPLAN (PFS-2095.022) every node culled: no argmax crash, shape kept on reload."""  # noqa: E501
        empty = _qa_probe_planar___plan(np.empty((0, 3)))
        empty.verify_positions(np.empty((0, 3)))
        reloaded = PlannedProbes.from_json(empty.to_json())
        assert reloaded.points.shape == (0, 3)
        reloaded.verify_positions(np.empty((0, 3)))

    @staticmethod
    @pytest.mark.parametrize(
        ("spacing", "cells"),
        [
            (0.7, 2),
            (0.4, 3),
            (0.5, 2),
            (0.5 - 1e-10, 3),
            (np.nextafter(0.5, 0.0), 3),
            (0.1, 10),
            (1.5, 1),
        ],
    )
    def test_p0400_probeplan_spacing_never_exceeds_the_request(spacing, cells):
        """P0400-PROBEPLAN (PFS-2104.016) the snapped element size is at most the requested one."""
        points = AxisSpec(start=0.0, stop=1.0, spacing=spacing).points()
        assert len(points) - 1 == cells
        assert float(np.max(np.diff(points))) <= min(spacing, 1.0) + 1e-12

    @staticmethod
    def test_p0400_probeplan_an_exact_fit_is_not_split_by_float_noise():
        """P0400-PROBEPLAN (PFS-2104.016) 1.1 / 0.1 is 11.000000000000002 and stays 11 cells."""
        assert len(AxisSpec(start=0.0, stop=1.1, spacing=0.1).points()) == 12


def _qa_probes___states(before: str, after: str):
    return SimpleNamespace(saved_before=lambda: before, saved_after=lambda: after)


def _qa_probes___reached(workdir: Path) -> ProbeArtifacts:
    return ProbeArtifacts(
        workdir=workdir,
        log_before="PYFS_B",
        log_after="PYFS_E",
        begin_marker="PYFS_B",
        end_marker="PYFS_E",
        execution=ExecutionResult(
            return_code=0, wall_time_s=1.0, timed_out=False, log_text="", stdout="", stderr=""
        ),
    )


class TestQaProbes:
    """P0400-PROBEHARNESS: the tier-2 probe harness and the specifications it judges.

    PFS-2102.013: fsm_gained keeps the exponent, so a value at the wrong power of ten fails.
    PFS-2102.027: a probe that could not be built leaves a directory the next run may wipe.
    PFS-2102.033: a prelude this edition's grammar refuses downgrades its tier.
    PFS-2102.014: the settings dumps sit outside the sentinels; a missing dump is unprobed.
    PFS-2102.028: an instrument that raises makes the target unprobed, not the run fatal.
    PFS-2102.001: the deletion probes need their positive control to verify.
    PFS-2102.005: a cambered NACA code with a zero camber position is refused.
    """

    @staticmethod
    def test_p0400_probeharness_a_value_at_the_wrong_power_of_ten_is_not_found():
        """P0400-PROBEHARNESS (PFS-2102.013) 0.1 is not on a changed line holding 1.0."""
        check = fsm_gained("0.1")
        assert check(_qa_probes___states("x\n0\n", "x\n1.00000000000000000E+00\n")) is False
        assert check(_qa_probes___states("x\n0\n", "x\n1.00000000000000006E-01\n")) is True
        assert (
            fsm_gained("37")(_qa_probes___states("x\n15\n", "x\n3.70000000000000000E-01\n"))
            is False
        )

    @staticmethod
    def test_p0400_probeharness_an_unbuildable_probe_can_be_built_again(tmp_path):
        """P0400-PROBEHARNESS (PFS-2102.027) the second run on the workroot is not refused."""

        def prelude(script, workdir: Path) -> None:
            (workdir / "support.stl").write_text("solid s\nendsolid s\n", encoding="utf-8")

        def refuses(script, workdir: Path) -> None:
            raise CommandArgumentError("this edition's grammar refuses the probe's value")

        spec = ProbeSpec(
            command="PRINT",
            build_target=refuses,
            prelude=prelude,
            assert_effect=lambda artifacts: True,
            effect_note="not reached",
        )
        for _ in range(2):
            result = _run_probe(spec, resolve("26.120"), None, tmp_path, 60.0, (), None)
            assert result.outcome is ProbeOutcome.UNPROBED, result.detail

    @staticmethod
    def test_p0400_probeharness_a_refused_prelude_line_downgrades_its_tier(tmp_path):
        """P0400-PROBEHARNESS (PFS-2102.033) 25.000's AIR_ALTITUDE grammar does not end the run."""
        planned = [SimpleNamespace(requires=Requires.SOLVER)]
        failures = _validate_tiers(
            planned, resolve("25.000"), None, tmp_path, tmp_path / "x.fsm", 60.0, None
        )
        assert Requires.SOLVER in failures
        assert "cannot be emitted" in failures[Requires.SOLVER]

    @staticmethod
    @pytest.mark.parametrize("version", known_versions(), ids=str)
    @pytest.mark.parametrize("tier", [tier for tier in Requires if tier is not Requires.NONE])
    def test_p0400_probeharness_each_registered_prelude_builds_or_downgrades(
        tmp_path, version, tier
    ):
        """P0400-PROBEHARNESS (PFS-2102.033) every edition and tier reaches a verdict."""
        emitted = []

        def run_script(script_path, **kwargs):
            emitted.append(script_path.read_text(encoding="utf-8"))
            return SimpleNamespace(diagnosis=lambda: "offline instrument has no log")

        failures = _validate_tiers(
            [SimpleNamespace(requires=tier)],
            version,
            SimpleNamespace(run_script=run_script),
            tmp_path,
            tmp_path / "x.fsm",
            60.0,
            None,
        )
        assert tier in failures
        if not emitted:
            assert "cannot be emitted" in failures[tier]
        else:
            assert "prelude did not reach its sentinel" in failures[tier]

    @staticmethod
    def test_p0400_probeharness_the_dumps_bracket_the_target_from_outside(tmp_path):
        """P0400-PROBEHARNESS (PFS-2102.014) no dump line between the sentinels; no dump, no verdict."""  # noqa: E501
        command = "FLUID_PROPERTIES"
        spec = _QA_PROBES__PROBE_SPECS[command]
        assert spec.dump_state
        lines = generate_probe_script(spec, "26.120", tmp_path, fsm=tmp_path / "x.fsm").render()
        lines = lines.splitlines()
        begin = lines.index(f"PRINT PYFS_PROBE_BEGIN_{command}")
        end = lines.index(f"PRINT PYFS_PROBE_END_{command}")
        assert "OUTPUT_SETTINGS_AND_STATUS" not in lines[begin:end]
        assert lines.count("OUTPUT_SETTINGS_AND_STATUS") == 2
        missing = SimpleNamespace(dump_after=lambda: None)
        assert dump_gained("7.2531", strict=True)(missing) is None

    @staticmethod
    def test_f534_a_token_already_in_the_before_dump_verifies_nothing():
        """F-534 a token present before the target cannot show the target put it there."""
        both = SimpleNamespace(dump_before=lambda: "x 7.2531 y", dump_after=lambda: "x 7.2531 y")
        assert dump_gained("7.2531")(both) is None
        assert dump_gained("7.2531", strict=True)(both) is None
        gained = SimpleNamespace(dump_before=lambda: "x 1.0 y", dump_after=lambda: "x 7.2531 y")
        assert dump_gained("7.2531")(gained) is True

    @staticmethod
    def test_f535_a_missing_end_sentinel_is_not_a_promotable_broken(tmp_path):
        """F-535 the verdict follows its detail: grammar doubt means unprobed, never broken."""
        spec = _QA_PROBES__PROBE_SPECS["DELETE_SURFACES"]
        artifacts = _qa_probes___reached(tmp_path)
        artifacts = ProbeArtifacts(
            workdir=tmp_path,
            log_before="PYFS_B",
            log_after="no end marker here",
            begin_marker="PYFS_B",
            end_marker="PYFS_E",
            execution=artifacts.execution,
        )
        result = _judge(spec, artifacts, DEFAULT_ERROR_PATTERNS, "sha", 60.0)
        assert result.outcome is ProbeOutcome.UNPROBED, result.detail
        assert "probe grammar" in result.detail

    @staticmethod
    def test_p0400_probeharness_an_instrument_that_raises_leaves_the_target_unprobed(tmp_path):
        """P0400-PROBEHARNESS (PFS-2102.028) DELETE_SURFACES on a run whose SAVEAS wrote nothing."""
        spec = _QA_PROBES__PROBE_SPECS["DELETE_SURFACES"]
        result = _judge(spec, _qa_probes___reached(tmp_path), DEFAULT_ERROR_PATTERNS, "sha", 60.0)
        assert result.outcome is ProbeOutcome.UNPROBED, result.detail

        def raising(artifacts):
            raise RuntimeError("the reader fell over")

        other = ProbeSpec(
            command="PRINT", build_target=lambda s, w: None, assert_effect=raising, effect_note="x"
        )
        result = _judge(other, _qa_probes___reached(tmp_path), DEFAULT_ERROR_PATTERNS, "sha", 60.0)
        assert result.outcome is ProbeOutcome.UNPROBED
        assert "RuntimeError: the reader fell over" in result.detail

    @staticmethod
    def test_p0400_probeharness_a_deletion_needs_its_positive_control(tmp_path):
        """P0400-PROBEHARNESS (PFS-2102.001) absence alone verifies nothing."""
        check = _QA_PROBES__PROBE_SPECS["DELETE_VOLUME_SECTION"].assert_effect
        artifacts = SimpleNamespace(workdir=tmp_path)
        assert check(artifacts) is None, "no export at all is an instrument that proved nothing"
        (tmp_path / "vsection_2.vtk").write_text("vtk", encoding="utf-8")
        assert check(artifacts) is True, "the survivor kept index 2"
        (tmp_path / "vsection.vtk").write_text("vtk", encoding="utf-8")
        assert check(artifacts) is False, "both sections export: nothing was deleted"
        (tmp_path / "vsection_2.vtk").unlink()
        assert check(artifacts) is True, "the survivor renumbered to 1"

        observers = _QA_PROBES__PROBE_SPECS["DELETE_ALL_ACOUSTIC_OBSERVERS"].assert_effect
        path = tmp_path / _spec_ccs_noise._SIGNALS
        path.write_text("", encoding="utf-8")
        assert observers(artifacts) is None, "an empty signals file proves no deletion"
        path.write_text("Observer: PYFS_CTRL\n0.0 1.0\n", encoding="utf-8")
        assert observers(artifacts) is True
        path.write_text("Observer: PYFS_CTRL\n0.0 1.0\nObserver: PYFS_OBS1\n0.0 1.0\n", "utf-8")
        assert observers(artifacts) is False

    @staticmethod
    @pytest.mark.parametrize(
        "make", [lambda: WingSpec(naca="2012"), lambda: BladeSpec(naca="4012")]
    )
    def test_p0400_probeharness_a_cambered_section_needs_its_camber_position(make):
        """P0400-PROBEHARNESS (PFS-2102.005) refused at construction, not by a ZeroDivisionError."""
        with pytest.raises(QaEvidenceError, match="position digit 0"):
            make()
        WingSpec(naca="0012")
        WingSpec(naca="2412")


class TestQaReviewNumbers:
    """P0400-REVIEW-NUMBERS: saved-state evidence must match a whole numeric value.

    Reproduction: fsm_gained('37') must not verify a changed value of 370.
    """

    @staticmethod
    @pytest.mark.parametrize(
        ("token", "stored"),
        [
            ("37", "370"),
            ("37", "-37"),
            ("0.1", "10.1"),
            ("0.1", "0.1E+01"),
            ("0.1", "-1.00000000000000006E-01"),
            ("0.1", "1.00000000000000006E-010"),
        ],
    )
    def test_p0400_review_numbers_wrong_numeric_value_is_not_evidence(token, stored):
        artifacts = SimpleNamespace(saved_before=lambda: "old", saved_after=lambda: stored)
        assert fsm_gained(token)(artifacts) is False

    @staticmethod
    @pytest.mark.parametrize("stored", ["37", "+37", "3.70000000000000000E+01", "count=37, next=5"])
    def test_p0400_review_numbers_whole_value_still_verifies(stored):
        artifacts = SimpleNamespace(saved_before=lambda: "old", saved_after=lambda: stored)
        assert fsm_gained("37")(artifacts) is True


def _qa_review_references___report(tmp_path, case_id, metric, points, value=0.35):
    path = tmp_path / "report.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema": PHYSICS_SCHEMA,
                "fs_version": "26.120",
                "cases": {case_id: {"metrics": {metric: value}, "points": points}},
            }
        ),
        encoding="utf-8",
    )
    return path


class TestQaReviewReferences:
    """P0400-REVIEW-REFERENCES: promotion validates evidence at its own boundary.

    Reproduction: update_reference must refuse an old report with an unconverged
    steady point, and must never write a zero-centred relative band it cannot load.
    """

    @staticmethod
    @pytest.mark.parametrize(
        ("case_id", "metric", "points"),
        [
            ("PHY-01", "CL_a4", [{"converged": False}]),
            ("PHY-02", "delta_CL_a4", [{"converged": True}, {"converged": False}]),
            ("PHY-06", "delta_CL_a4", [{"converged": False}, {"converged": False}]),
        ],
    )
    def test_p0400_review_references_unconverged_steady_evidence_is_refused(
        tmp_path, case_id, metric, points
    ):
        path = _qa_review_references___report(tmp_path, case_id, metric, points)
        refs = tmp_path / "refs"
        with pytest.raises(QaEvidenceError, match="unconverged steady"):
            update_reference(case_id, path, "refresh", references_dir=refs, repo_root=tmp_path)
        assert not (refs / f"{case_id}.yaml").exists()

    @staticmethod
    def test_p0400_review_references_unsteady_completion_still_promotes(tmp_path):
        path = _qa_review_references___report(
            tmp_path, "PHY-06", "delta_CL_a4", [{"converged": True}, {"converged": False}]
        )
        refs = tmp_path / "refs"
        update_reference("PHY-06", path, "refresh", references_dir=refs, repo_root=tmp_path)
        assert load_reference("PHY-06", refs) is not None

    @staticmethod
    def test_p0400_review_references_incomplete_polar_pair_is_refused(tmp_path):
        path = _qa_review_references___report(
            tmp_path,
            "PHY-06",
            "delta_CL_a4",
            [{"converged": True}, {"converged": False}, {"converged": False}],
        )
        refs = tmp_path / "refs"
        with pytest.raises(QaEvidenceError, match="paired steady and unsteady"):
            update_reference("PHY-06", path, "refresh", references_dir=refs, repo_root=tmp_path)
        assert not (refs / "PHY-06.yaml").exists()

    @staticmethod
    def test_p0400_review_references_zero_relative_update_keeps_existing_bytes(tmp_path):
        path = _qa_review_references___report(tmp_path, "PHY-01", "CL_a4", [{"converged": True}])
        refs = tmp_path / "refs"
        target = update_reference("PHY-01", path, "seed", references_dir=refs, repo_root=tmp_path)
        before = target.read_bytes()
        path = _qa_review_references___report(
            tmp_path, "PHY-01", "CL_a4", [{"converged": True}], value=0.0
        )
        with pytest.raises(QaEvidenceError, match="relative band"):
            update_reference("PHY-01", path, "refresh", references_dir=refs, repo_root=tmp_path)
        assert target.read_bytes() == before


_REACH2_ROUTES___REQUIREMENT = "P0400-REACH2"


#: A steady entry with one line of three points and a two-by-two rectangle.
_REACH2_ROUTES___STEADY_ENTRY = {
    "frame": "REFERENCE",
    "parameters": ["VX"],
    "points": 3,
    "lines": [{"start": [1.0, -0.5, 0.0], "end": [1.0, 0.5, 0.0]}],
    "rectangles": [
        {
            "origin": [2.0, -0.5, -0.25],
            "along_u": [2.0, 0.5, -0.25],
            "along_v": [2.0, -0.5, 0.25],
            "points_u": 2,
            "points_v": 2,
        }
    ],
}


class _Reach2RoutesRotor:
    axis = "X"
    diameter_m = 2.0
    x_m, y_m, z_m = 0.5, 0.0, 0.0


def _reach2_routes___spy(monkeypatch, module, name: str, function) -> list:
    """Replace ``module.name`` by a wrapper of ``function`` that records each call."""
    calls: list = []

    def wrapper(*args, **kwargs):
        calls.append((args, kwargs))
        return function(*args, **kwargs)

    monkeypatch.setattr(module, name, wrapper, raising=False)
    return calls


def _reach2_routes___sheared_fields():
    """A lattice sampled with a sheared, crossflowing stream and one missing sample."""
    spec = LedgersSpec(rotor="R", stations=(-1.0, 0.5, 1.5), n_r=6, n_psi=16, m_max=2)
    lattice, points_m, axis = farfield_fields.rotor_lattice(spec, _Reach2RoutesRotor())
    y, z = points_m[:, 1], points_m[:, 2]
    velocity = np.column_stack([12.0 + 0.4 * y, 0.3 * z - 0.2, 0.5 + 0.25 * y * y])
    velocity[len(points_m) // 2 + 3] = np.nan
    samples = farfield_fields.ProbeSamples(points_m, velocity, 0.01 * y)
    fields = farfield_fields.lattice_samples(samples, slice(0, len(points_m)), lattice, axis, q=0.0)
    return spec, fields


_REACH2_ROUTES___ROTOR_LATTICE = {
    "rotor": "ROTOR",
    "stations": [-0.7, 0.3, 2.0],
    "n_r": 5,
    "n_psi": 24,
    "r_inner": 0.13,
}


class TestReach2Routes:
    """P0400-REACH2: the workspace route runs the public probe and far-field functions (PFS-2140.011).

    The rule of PFS-2140.011: every public capability is reached from the
    workspace. Where the route did the job with a duplicate of a public function,
    the route now calls the function, and each test pins both halves: the public
    function is what the route runs (a spy that the duplicate never called), and
    what the route produces is unchanged (the value or the text the duplicate
    produced, computed beside it).
    """  # noqa: E501

    @staticmethod
    @pytest.mark.requirement("FR-38")
    def test_p0400_reach2_the_ledger_runs_transverse_force_and_sample_coverage(monkeypatch):
        """P0400-REACH2 (PFS-2139.008): the ledger runs transverse_force and sample_area_coverage.

        The lateral columns are transverse_force's lateral term, the plane columns
        the quadrature flux difference (its plane term), and COVERAGE is
        sample_area_coverage, each value the one the ledger wrote before.
        """
        spec, fields = _reach2_routes___sheared_fields()
        forces = _reach2_routes___spy(
            monkeypatch, farfield_fields, "transverse_force", transverse_force
        )
        coverages = _reach2_routes___spy(
            monkeypatch, farfield_fields, "sample_area_coverage", sample_area_coverage
        )
        rows = farfield_fields.ledger_values(fields, spec, rho=1.2, speed=12.0, near=(3.0, 1.0))
        assert forces and coverages, (
            _REACH2_ROUTES___REQUIREMENT,
            "the ledger runs the public balances",
        )
        fy = transverse_flux(fields, 1.2, component="v")
        fz = transverse_flux(fields, 1.2, component="w")
        weights = ring_sample_weights(fields)
        finite_cells = np.isfinite(fields["u"])
        finite = (finite_cells * weights[:, None]).sum(axis=(-2, -1)) / (
            float(weights.sum()) * finite_cells.shape[-1]
        )
        assert finite.min() < 1.0, "the fixture misses a sample"
        for index, row in enumerate(rows):
            # Same fraction, summed in another order: equal to rounding, not bit for bit.
            assert row["COVERAGE"] == pytest.approx(float(finite[index]), rel=1e-12)
            if index:
                # The duplicate's arithmetic, bit for bit (NaN where a sample is missing).
                np.testing.assert_array_equal(
                    [row["FY_PLANE_N"], row["FZ_PLANE_N"]],
                    [float(fy[index] - fy[0]), float(fz[index] - fz[0])],
                )
                inlet, station = float(fields.stations[0]), float(fields.stations[index])
                np.testing.assert_array_equal(
                    [row["FY_LATERAL_N"], row["FZ_LATERAL_N"]],
                    [
                        lateral_flux(fields, rho=1.2, inlet=inlet, outlet=station, component="v"),
                        lateral_flux(fields, rho=1.2, inlet=inlet, outlet=station, component="w"),
                    ],
                )
        assert all("lateral_flux" in kwargs for _, kwargs in forces)
        assert any(np.isfinite(row.get("FZ_PLANE_N", np.nan)) for row in rows[1:])

    @staticmethod
    @pytest.mark.requirement("FR-79")
    def test_p0400_reach2_a_steady_row_creates_its_probes_through_the_script_helpers(
        tmp_path, monkeypatch
    ):
        """P0400-REACH2 (PFS-2140.001): lines and drawn points go through the public helpers.

        The script carries the lines the route wrote before, one ``NEW_PROBE_LINE``
        per declared line and one ``NEW_PROBE_POINT VOLUME`` per rectangle node.
        """
        lines_called = _reach2_routes___spy(monkeypatch, helpers, "probe_line", helpers.probe_line)
        points_called = _reach2_routes___spy(
            monkeypatch, helpers, "probe_points", helpers.probe_points
        )
        lines, _ = _reach2_routes___rendered(
            _reach2_routes___steady_with(tmp_path, _REACH2_ROUTES___STEADY_ENTRY)
        )
        assert len(lines_called) == 1 and len(points_called) == 4, _REACH2_ROUTES___REQUIREMENT
        assert lines.count("NEW_PROBE_LINE 3 1.0 -0.5 0.0 1.0 0.5 0.0") == 1
        assert [line for line in lines if line.startswith("NEW_PROBE_POINT")] == [
            "NEW_PROBE_POINT VOLUME 2.0 -0.5 -0.25",
            "NEW_PROBE_POINT VOLUME 2.0 -0.5 0.25",
            "NEW_PROBE_POINT VOLUME 2.0 0.5 -0.25",
            "NEW_PROBE_POINT VOLUME 2.0 0.5 0.25",
        ]

    @staticmethod
    @pytest.mark.requirement("FR-81")
    def test_p0400_reach2_a_steady_row_exports_its_probes_through_the_probes_home(
        tmp_path, monkeypatch
    ):
        """P0400-REACH2 (PFS-2140.001): the probe export goes through probes.emit_probe_export.

        One ``UPDATE_PROBE_POINTS`` with the other updates, then the export to the
        row's probes file, as before; the export register names the entry point.
        """
        exports_called = _reach2_routes___spy(
            monkeypatch, exports_module, "emit_probe_export", _reach2_routes__emit_probe_export
        )
        helper_called = _reach2_routes___spy(
            monkeypatch, helpers, "export_probes", helpers.export_probes
        )
        lines, script = _reach2_routes___rendered(
            _reach2_routes___steady_with(tmp_path, _REACH2_ROUTES___STEADY_ENTRY)
        )
        assert len(exports_called) == 1 and len(helper_called) == 1, _REACH2_ROUTES___REQUIREMENT
        update = lines.index("UPDATE_PROBE_POINTS")
        export = lines.index("EXPORT_PROBE_POINTS")
        assert lines[export + 1] == "point_probes.txt" and lines.count("EXPORT_PROBE_POINTS") == 1
        assert update < export and lines.count("UPDATE_PROBE_POINTS") == 1
        source = script._exported_paths["point_probes.txt"]
        assert source.startswith("emit_probe_export (called at test_regression_qa_tools.py:")
        assert source.endswith(")")

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_reach2_the_added_far_field_csv_is_written_by_write_points_csv(
        tmp_path, monkeypatch
    ):
        """P0400-REACH2 (PFS-2140.001): the staged csv of an added plane is write_points_csv's.

        The text is the one parked before, byte for byte: the count line, then one
        ``x,y,z,1`` row per point in the order the plan laid them.
        """
        written = _reach2_routes___spy(
            monkeypatch, farfield_module, "write_points_csv", write_points_csv
        )
        farfield = {"families": "all", "trefftz": {"variant": "plane", "spacing_bref": 0.25}}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            script = _reach2_routes___script(_reach2_routes___case(tmp_path, farfield))
        assert len(written) == 1, (
            _REACH2_ROUTES___REQUIREMENT,
            "the plan writes the csv through the probes home",
        )
        (name, payload), *_ = [
            (name, text)
            for name, text in script.pending_input_files.items()
            if name.startswith("farfield_probes_")
        ]
        points = [point[1:4] for point in script.probe_points]
        assert payload == f"{len(points)}\n" + "".join(f"{x},{y},{z},1\n" for x, y, z in points)
        text = script.render()
        assert text.count("PROBE_POINTS_IMPORT") == 1 and name in text

    @staticmethod
    @pytest.mark.requirement("FR-459")
    def test_p0400_reach2_write_points_csv_writes_the_same_text_to_a_stream_and_a_file(tmp_path):
        """P0400-REACH2: a text stream receives exactly the text the file holds."""
        points = np.array([[0.1 * 3, -0.0, 1e-05], [12345.6789, 2.0, -3.5]])
        stream = io.StringIO()
        assert write_points_csv(points, stream) == 2
        path = tmp_path / "points.csv"
        write_points_csv(points, path)
        assert stream.getvalue() == path.read_bytes().decode("utf-8")
        assert stream.getvalue() == "2\n0.30000000000000004,-0.0,1e-05,1\n12345.6789,2.0,-3.5,1\n"

    @staticmethod
    @pytest.mark.requirement("FR-459")
    def test_p0400_reach2_a_declared_lattice_is_emitted_by_emit_probe_points(tmp_path, monkeypatch):
        """P0400-REACH2 (PFS-2140.001): a steady reference-frame lattice, placed and rounded.

        The probes home emits one ``NEW_PROBE_POINT VOLUME`` per lattice point, on
        the rotor's hub, in the recorded order and at the recorded five-decimal
        positions, after the entry's drawn line.
        """
        emitted = _reach2_routes___spy(
            monkeypatch, farfield_module, "emit_probe_points", emit_probe_points
        )
        declared = dict(_REACH2_ROUTES___ROTOR_LATTICE, stations=[-1.3, 3.1], n_psi=20)
        entry = {
            "frame": "REFERENCE",
            "parameters": ["VX"],
            "points": 3,
            "lines": [{"start": [1.5, 0.0, 0.0], "end": [1.5, 0.3, 0.1]}],
            "lattices": [declared],
        }
        farfield = {"families": "all", "ledgers": dict(_REACH2_ROUTES___ROTOR_LATTICE, m_max=2)}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            script = _reach2_routes___script(
                _reach2_routes___case(tmp_path, farfield, probes=[entry])
            )
        assert len(emitted) == 1, (
            _REACH2_ROUTES___REQUIREMENT,
            "the declared lattice is emitted by the probes home",
        )
        placement = emitted[0][1]
        assert placement["decimals"] == 5 and placement["origin"] is not None, placement
        lines = [line for line in script.render().splitlines() if line.startswith("NEW_PROBE_")]
        count = LatticeShape.model_validate(declared).build(1.0).point_count
        assert len(lines) == 1 + count and lines[0].startswith("NEW_PROBE_LINE 3 ")
        laid = [point for point in script.probe_points if point[0] > 3][:count]
        assert lines[1:] == [f"NEW_PROBE_POINT VOLUME {x} {y} {z}" for _, x, y, z, _ in laid]

    @staticmethod
    @pytest.mark.requirement("FR-455")
    def test_p0400_reach2_a_lattice_added_alone_is_written_by_write_probe_csv(
        tmp_path, monkeypatch
    ):
        """P0400-REACH2 (PFS-2140.001): the staged csv of a lone added lattice is write_probe_csv's.

        The text is the one parked before: the count line, then the recorded
        five-decimal positions as ``x,y,z,1`` rows.
        """
        written = _reach2_routes___spy(
            monkeypatch, farfield_module, "write_probe_csv", write_probe_csv
        )
        farfield = {"families": "all", "ledgers": dict(_REACH2_ROUTES___ROTOR_LATTICE, m_max=2)}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            script = _reach2_routes___script(_reach2_routes___case(tmp_path, farfield))
        assert len(written) == 1, (
            _REACH2_ROUTES___REQUIREMENT,
            "the plan writes the lattice csv from the lattice",
        )
        (payload,) = [
            text
            for name, text in script.pending_input_files.items()
            if name.startswith("farfield_")
        ]
        points = [point[1:4] for point in script.probe_points]
        assert payload == f"{len(points)}\n" + "".join(f"{x},{y},{z},1\n" for x, y, z in points)

    @staticmethod
    def test_p0400_reach2_the_lattice_emitters_keep_their_unplaced_default(tmp_path):
        """P0400-REACH2: with no placement both emitters give the lattice's own points, unrounded."""  # noqa: E501
        lattice = LatticeShape.model_validate(_REACH2_ROUTES___ROTOR_LATTICE).build(0.7)
        plain = Script("26.124")
        assert emit_probe_points(plain, lattice) == lattice.point_count
        expected = Script("26.124")
        helpers.probe_points(
            expected, [(float(x), float(y), float(z)) for x, y, z in lattice.dimensional_points()]
        )
        assert plain.render() == expected.render()
        stream, direct = io.StringIO(), io.StringIO()
        write_probe_csv(lattice, stream)
        write_points_csv(lattice.dimensional_points(), direct)
        assert stream.getvalue() == direct.getvalue()

    @staticmethod
    @pytest.mark.requirement("FR-153")
    def test_p0400_reach2_tecplot_points_writes_one_ordered_zone_beside_the_tecplot_product(
        tmp_path, monkeypatch
    ):
        """P0400-REACH2 (FR-153, 0.40.0): ``field_formats = ["tecplot-points"]`` from the pproc.

        The workspace post writes ``<stem>_points.dat`` through write_tecplot_points,
        one ordered POINT zone of every sample, and the ``tecplot`` product beside it
        keeps one single-point zone per sample.
        """
        from pyflightstream.cases import PprocSpec
        from pyflightstream.post import probe_fields
        from pyflightstream.post.products import write_campaign_products
        from pyflightstream.post.writers import write_tecplot_points
        from pyflightstream.run._pending import _write_probe_points
        from pyflightstream.workspace import CampaignWorkspace
        from tests.tier1_offline.test_f01_probe_source import _post_workspace
        from tests.tier1_offline.test_post_products import PLOTS_HEADER

        written = _reach2_routes___spy(
            monkeypatch, probe_fields, "write_tecplot_points", write_tecplot_points
        )
        w = _post_workspace(tmp_path, monkeypatch)
        pproc = (
            '[groups]\n"1"="all"\n[products]\nplots=false\n'
            '[[probes]]\nframe="REFERENCE"\nfield_formats=["tecplot","tecplot-points"]\n'
            "rectangles=[{origin=[0,-1,-2],along_u=[0,1,-2],along_v=[0,-1,2],points_u=2,points_v=2}]\n"
        )
        (w.inputs_dir / "pproc/p001.toml").write_text(pproc, encoding="utf-8")
        assert PprocSpec.model_validate(
            {"probes": [{"frame": "REFERENCE", "field_formats": ["tecplot-points"]}]}
        ).probes[0].field_formats == ["tecplot-points"]
        positions = [
            (i, 0, y, z, "REFERENCE")
            for i, (y, z) in enumerate([(-1, -2), (-1, 2), (1, -2), (1, 2)], 1)
        ]
        relative = _write_probe_points(w.sim_dir("7001"), "7001", positions)
        history = "Time-step," + ",".join(
            f"{v}{i}" for i in range(1, 5) for v in ("VX", "VY", "VZ")
        )
        history += "\n1," + ",".join(str(v) for i in range(1, 5) for v in (10 + i, 3 + i, 5 - i))
        (w.sim_dir("7001") / "outputs/AL-020_plots.txt").write_text(
            PLOTS_HEADER + history + "\n" + "-" * 60 + "\n     Force Units: Coefficients\n",
            encoding="utf-8",
        )
        layout = {
            "entry": 1,
            "kind": "probe-field",
            "probe_ids": [1, 2, 3, 4],
            "frame": "REFERENCE",
            "native_to_m": 1,
            "formats": ["tecplot", "tecplot-points"],
            "reusable_inflow": False,
        }
        record = w.read_manifest()[0].model_copy(
            update={
                "probe_points_file": relative,
                "solver_setup": helpers.solver_settings(Script("26.124"), velocity=30).model_dump(
                    mode="json"
                ),
                "probe_field_layout": [layout],
            }
        )
        monkeypatch.setattr(CampaignWorkspace, "read_manifest", lambda self: [record])
        write_campaign_products(w)
        fields = w.root / "post/products/fields"
        (points,) = list(fields.glob("*_points.dat"))
        (per_sample,) = [path for path in fields.glob("*.dat") if path != points]
        assert len(written) == 1, (
            _REACH2_ROUTES___REQUIREMENT,
            "the post writes the zone by write_tecplot_points",
        )
        text = points.read_text(encoding="utf-8").splitlines()
        assert text[0] == 'TITLE = "Reference-frame velocity samples"'
        assert [line for line in text if line.startswith("ZONE")] == [
            'ZONE T="samples" I=4 ZONETYPE=ORDERED DATAPACKING=POINT'
        ]
        assert len(text) == 3 + 4 and "Velocity_x" in text[1]
        zones = [
            line for line in per_sample.read_text(encoding="utf-8").splitlines() if "ZONE" in line
        ]
        assert len(zones) == 4 and zones[0].startswith('ZONE T="Sample 1", I=1')
        assert (fields / (points.name + ".provenance.json")).exists()


_QA_REVIEW_PROOFS__REPO = Path(__file__).resolve().parents[2]


_QA_REVIEW_PROOFS__METRICS_SPEC = importlib.util.spec_from_file_location(
    "p0400_qa_review_architecture", _QA_REVIEW_PROOFS__REPO / "scripts" / "arch_metrics.py"
)


assert (
    _QA_REVIEW_PROOFS__METRICS_SPEC is not None
    and _QA_REVIEW_PROOFS__METRICS_SPEC.loader is not None
)


_qa_review_proofs__am = importlib.util.module_from_spec(_QA_REVIEW_PROOFS__METRICS_SPEC)


sys.modules[_QA_REVIEW_PROOFS__METRICS_SPEC.name] = _qa_review_proofs__am


_QA_REVIEW_PROOFS__METRICS_SPEC.loader.exec_module(_qa_review_proofs__am)


_QA_REVIEW_PROOFS__BASELINES = json.loads(
    (_QA_REVIEW_PROOFS__REPO / "tests" / "tier1_offline" / "architecture_baselines.json").read_text(
        encoding="utf-8"
    )
)


class TestQaReviewProofs:
    """P0400-REVIEW-PROOFS: regressions exercise entry points present before the fix.

    Reproduction: reduce two campaigns in one manifest, reduce a single-point
    case containing a sweep, and promote into the repository's own database.
    """

    @staticmethod
    def test_p0400_review_proofs_campaign_filter_reaches_the_reducer(tmp_path, monkeypatch):
        root = _qa_matrix___workspace(tmp_path)
        records = [
            _qa_matrix___record("ws/sim_5002/AL+004"),
            _qa_matrix___record("other/sim_5002/AL+004"),
        ]
        observed = []

        def reduce_case(case_id, rows, workspace, by_row, steady_rows, matrix):
            observed.extend(record.run_id for record in by_row["5002"])
            return (), {}

        monkeypatch.setattr(matrix_module, "_reduce_case", reduce_case)
        monkeypatch.setattr(matrix_module, "load_reference", lambda *args, **kwargs: None)
        matrix_module.reduce_physics(
            _qa_matrix___fake_workspace(root, records), root / "matriz_physics.fs"
        )
        assert observed
        assert set(observed) == {"ws/sim_5002/AL+004"}

    @staticmethod
    def test_p0400_review_proofs_single_point_case_refuses_through_its_caller(
        tmp_path, monkeypatch
    ):
        points = [PointResult(a, {"CL": 0.1}, 10, True, f"p{a:g}") for a in (2.0, 4.0)]
        monkeypatch.setattr(matrix_module, "_points_of_row", lambda *args: points)
        with pytest.raises(QaEvidenceError, match="reads one point"):
            matrix_module._reduce_case(
                "PHY-05", [_QA_MATRIX__ROW], None, {}, [], tmp_path / "matrix.fs"
            )

    @staticmethod
    def test_p0400_review_proofs_default_promotion_writes_the_named_repository(
        tmp_path, monkeypatch
    ):
        root = tmp_path / "repo"
        inside = _qa_compat___commands(root / "src" / "pyflightstream" / "commands")
        installed = _qa_compat___commands(tmp_path / "installed" / "commands")
        before = (installed / "script_controls.yaml").read_bytes()
        monkeypatch.setattr(compat.resources, "files", lambda package: installed)
        report = _qa_compat___report(root, {"STOP": {"outcome": "verified", "detail": "halted"}})
        compat.apply_compat(report, repo_root=root)
        assert "status: verified" in (inside / "script_controls.yaml").read_text(encoding="utf-8")
        assert (installed / "script_controls.yaml").read_bytes() == before

    @staticmethod
    @pytest.mark.parametrize(
        "relative",
        [
            "probes/geometry.py",
            "probes/planar.py",
            "qa/cli.py",
            "qa/compat.py",
            "qa/matrix.py",
            "qa/physics.py",
            "qa/probes.py",
        ],
    )
    def test_p0400_review_proofs_function_ratchets_hold_for_the_changed_modules(relative):
        source = (_QA_REVIEW_PROOFS__REPO / "src" / "pyflightstream" / relative).read_text(
            encoding="utf-8"
        )
        tree = _qa_review_proofs__am.Tree({relative: source})
        limits = {
            key: value
            for key, value in _QA_REVIEW_PROOFS__BASELINES["function_limits"].items()
            if key.startswith(relative + ":")
        }
        lengths = {
            key: value
            for key, value in _QA_REVIEW_PROOFS__BASELINES["function_lines"].items()
            if key.startswith(relative + ":")
        }
        assert _qa_review_proofs__am.function_findings(tree, lengths, limits) == []
