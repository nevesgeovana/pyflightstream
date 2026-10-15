"""Regression coverage grouped by subject."""

from __future__ import annotations

import dataclasses
import hashlib
import importlib
import inspect
import json
import math
import re
import shutil
import sys
import threading
import warnings
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

import pytest
import yaml

from pyflightstream._digest import file_sha256
from pyflightstream._errors import InputArtifactError, PyflightstreamWarning
from pyflightstream._fsm import MeshReadError, boundary_names, surface_mesh
from pyflightstream.cases._geometry_emit import EVIDENCE_GATED, render_geometry_script
from pyflightstream.cases._geometry_instruction import (
    GeometryInstruction,
    MeshSource,
    source_names,
    variant_tag,
)
from pyflightstream.cases.mesh import MeshImport, MeshOperation, TrailingEdgeMarking
from pyflightstream.cases.reference_blocks import CampaignConfigError
from pyflightstream.cases.selection import resolve_alias, select_families, select_group_members
from pyflightstream.commands import CommandRegistry, Status
from pyflightstream.qa.physics import (
    PHYSICS_CASES,
    load_reference,
    update_reference,
    write_physics_report,
)
from pyflightstream.run import (
    CampaignErrors,
    _cli_geometry,
    _executors,
    _grouped,
    _rebuild_grouped,
    cli,
)
from pyflightstream.run._cli_geometry import _print_plan
from pyflightstream.run._cli_parsers import _build_parser
from pyflightstream.run.cli import main as matrix_main
from pyflightstream.run.matrix import plan_matrix
from pyflightstream.script import (
    BrokenCommandError,
    CommandArgumentError,
    Script,
    ScriptOrderError,
    helpers,
)
from pyflightstream.workspace import CampaignWorkspace, _geometry_build, _geometry_vtk
from pyflightstream.workspace import _geometry_build as build
from pyflightstream.workspace import cli as workspace_cli
from pyflightstream.workspace._geometry_build import (
    GeometryBuildError,
    SolverOutcome,
    apply_geometry_build,
    plan_geometry_build,
    refuse_before_running,
)
from pyflightstream.workspace._geometry_instruction import read_geometry_instruction
from pyflightstream.workspace._geometry_record import judge_the_row_geometry
from pyflightstream.workspace._refine import _config
from pyflightstream.workspace._settings_file import read_workspace_settings
from pyflightstream.workspace.cli import main
from pyflightstream.workspace.hpc import read_hpc_profile
from pyflightstream.workspace.matrix import resolve_matrix
from pyflightstream.workspace.record_document import encode_rows
from pyflightstream.workspace.record_document import read_rows as _read_record_rows
from tests.tier1_offline._docs_site import (
    FUNCTIONAL_REQUIREMENTS as _SWEEP_1_CONTRACTS__FUNCTIONAL_REQUIREMENTS,
)
from tests.tier1_offline.test_matrix_run import RECIPES as _RFIXG_RECORD__RECIPES
from tests.tier1_offline.test_matrix_run import make_library as _rfixg_record__make_library
from tests.tier1_offline.test_matrix_run import write_matrix as _rfixg_record__write_matrix
from tests.tier1_offline.test_p0340_run_usability import _argv as _sweep_1_cli___argv
from tests.tier1_offline.test_p0340_run_usability import (
    _two_simulations as _sweep_1_cli___two_simulations,
)
from tests.tier1_offline.test_regression_qa_tools import (
    _GAPPROBES_SPECS__QUAD_BLOCK as _RFIXR5_SWEEP__QUAD_BLOCK,
)
from tests.tier1_offline.test_regression_qa_tools import (
    _qa_physics___points as _sweep_1_contracts___points,
)
from tests.tier1_offline.test_regression_qa_tools import (
    _qa_physics___points as _sweep_1_routes___points,
)
from tests.tier1_offline.test_regression_qa_tools import (
    _qa_physics___run as _sweep_1_contracts___run,
)
from tests.tier1_offline.test_regression_qa_tools import _qa_physics___run as _sweep_1_routes___run

_GEOMETRY_BUILD__WING_FSM = (
    Path(__file__).resolve().parents[1] / "tier3_licensed" / "inputs" / "geometries" / "10_WING.fsm"
)


_GEOMETRY_BUILD__MESH_INSTRUCTION = (
    'fs_build = "26.125"\nboundaries = ["Wing"]\noutputs = ["fsm", "obj"]\n'
    '[mesh]\nfile = "src.obj"\nunits = "METER"\n[trailing_edges]\ndetect = "auto"\n'
)


def _geometry_build__workspace(tmp_path: Path) -> Path:
    """A workspace root with a geometry library and both builds registered."""
    root = tmp_path / "ws"
    (root / "inputs" / "geometries").mkdir(parents=True)
    exe = Path(sys.executable).as_posix()
    (root / "inputs" / "executables.toml").write_text(
        f'"26.125" = {{ path = "{exe}", version = "26.125" }}\n'
        f'"26.124" = {{ path = "{exe}", version = "26.124" }}\n',
        encoding="utf-8",
    )
    return root


def _geometry_build__wing_obj(path: Path, group: str = "Wing") -> Path:
    """Write the committed wing's surface as an OBJ with one group."""
    vertices, triangles = surface_mesh(_GEOMETRY_BUILD__WING_FSM)
    rows = [f"v {x} {y} {z}" for x, y, z in vertices] + [f"g {group}"]
    rows += [f"f {a + 1} {b + 1} {c + 1}" for a, b, c in triangles]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def _geometry_build__geometry(
    root: Path, folder: str, text: str, *, source: str | None = "src.obj"
) -> Path:
    """A geometry folder with its instruction and, optionally, a mesh source."""
    where = root / "inputs" / "geometries" / folder
    where.mkdir(parents=True, exist_ok=True)
    if source is not None:
        _geometry_build__wing_obj(where / source)
    (where / f"{folder}.geometry.toml").write_text(text, encoding="utf-8")
    return where


def _geometry_build__runner(
    saved: Path = _GEOMETRY_BUILD__WING_FSM, *, fail: bool = False, sliver: bool = False
) -> Callable[[Path, Path], SolverOutcome]:
    """A runner doing what the build's script asks: save the body, export its mesh.

    ``sliver`` adds a face of zero area to the export, which audit gate G1 fails.
    """

    def run(script: Path, work: Path) -> SolverOutcome:
        name = script.name.removesuffix(".build.txt")
        if not fail:
            shutil.copyfile(saved, work / f"{name}.fsm")
            mesh = _geometry_build__wing_obj(work / f"{name}.obj")
            if sliver:
                with mesh.open("a", encoding="utf-8") as handle:
                    handle.write("f 1 1 2\n")
        return SolverOutcome(fail, 1 if fail else 0, 2.5, "solver log", "exited 1" if fail else "")

    return run


def _geometry_build__verified_registry() -> CommandRegistry:
    """The command database with every gated command verified, as after the probe batch."""
    base = CommandRegistry.load()
    commands = dict(base.commands)
    for name in EVIDENCE_GATED & set(commands):
        entry = commands[name]
        versions = {
            key: status.model_copy(update={"status": Status.VERIFIED})
            for key, status in entry.versions.items()
        }
        commands[name] = entry.model_copy(update={"versions": versions})
    return CommandRegistry(commands=commands)


class TestGeometryBuild:
    """Tier 1, 0.40.0: ``pyfs-workspace geometry build`` previews and builds a body (FR-471).

    P0400-GEOM-BUILD (PFS-2081.41). The solver is replaced by a runner that does
    what a build's script asks of it: it writes the saved simulation and the
    exported mesh into the partial folder. The saved simulation is a committed one
    the solver wrote (``tests/tier3_licensed/inputs/geometries/10_WING.fsm``, a
    straight wing named ``Wing`` with sixteen marked trailing-edge edges), so the
    read-back, the audit, the preview and the record are judged against a file of
    the solver's own.
    """

    @staticmethod
    @pytest.fixture
    def verified() -> CommandRegistry:
        """Every gated command verified, handed to the plan as its command database."""
        return _geometry_build__verified_registry()

    @staticmethod
    @pytest.mark.requirement("FR-471")
    def test_p0400_geom_build_preview_runs_nothing_and_writes_nothing(
        tmp_path, capsys, monkeypatch
    ):
        """P0400-GEOM-BUILD (PFS-2081.41): R1, the preview names the script and the names."""
        root = _geometry_build__workspace(tmp_path)
        folder = _geometry_build__geometry(root, "wing", _GEOMETRY_BUILD__MESH_INSTRUCTION)
        before = sorted(p.name for p in folder.iterdir())
        monkeypatch.chdir(folder)
        assert main(["geometry", "build"]) == 0
        out = capsys.readouterr().out
        assert "IMPORT" in out and "SAVEAS" in out and "after source: Wing" in out
        assert "preview only" in out
        assert sorted(p.name for p in folder.iterdir()) == before
        assert not folder.with_name("wing.partial").exists()

    @staticmethod
    @pytest.mark.requirement("FR-471")
    def test_p0400_geom_build_script_sets_units_marks_saves_then_exports(tmp_path):
        """P0400-GEOM-BUILD (PFS-2081.41): R2, the order of one build's script."""
        root = _geometry_build__workspace(tmp_path)
        _geometry_build__geometry(root, "wing", _GEOMETRY_BUILD__MESH_INSTRUCTION)
        plan = plan_geometry_build(root / "inputs" / "geometries" / "wing")
        lines = [line for line in plan.variants[0].script.text.splitlines() if line]
        order = [
            "NEW_SIMULATION",
            "IMPORT",
            "SET_SIMULATION_LENGTH_UNITS METER",
            "DETECT_TRAILING_EDGES_BY_SURFACE",
            "SAVEAS",
            "EXPORT_SURFACE_MESH OBJ -1",
            "CLOSE_FLIGHTSTREAM",
        ]
        positions = [
            next(i for i, line in enumerate(lines) if line.startswith(word)) for word in order
        ]
        assert positions == sorted(positions), lines
        assert "NEW_SIMULATION" == lines[0]
        tail = plan.variants[0].script.text.split("SET_SIMULATION_LENGTH_UNITS", 1)[1]
        work = str(Path(plan.variants[0].script.fsm).parent)
        tail = ("SET_SIMULATION_LENGTH_UNITS" + tail).replace(work, "{work}")
        tail = tail.replace(chr(92), "/")
        golden = Path(__file__).parent / "goldens" / "p0400_geometry_build_tail.txt"
        assert tail == golden.read_text(encoding="utf-8")

    @staticmethod
    @pytest.mark.requirement("FR-471")
    def test_p0400_geom_build_refuses_a_command_awaiting_evidence_and_runs_nothing(tmp_path):
        """P0400-GEOM-BUILD (PFS-2081.41): R9, the evidence gate; the runner is never called."""
        root = _geometry_build__workspace(tmp_path)
        _geometry_build__geometry(root, "wing", _GEOMETRY_BUILD__MESH_INSTRUCTION)
        plan = plan_geometry_build(root / "inputs" / "geometries" / "wing")
        assert "EXPORT_SURFACE_MESH" in plan.awaiting_evidence
        called = []
        with pytest.raises(InputArtifactError, match="EXPORT_SURFACE_MESH.*licensed probe"):
            apply_geometry_build(plan, runner=lambda s, w: called.append(s))  # type: ignore
        assert not called

    @staticmethod
    @pytest.mark.requirement("FR-471")
    def test_p0400_geom_build_a_ccs_loft_waits_for_its_probe_on_26124_only(tmp_path):
        """P0400-GEOM-BUILD (PFS-2081.41): R9, the loft is verified on 26.125 and not on 26.124."""
        from tests.tier1_offline.test_regression_geometry_build_sweep import (
            _GEOMETRY_INSTRUCTION__CCS_WING as CCS_WING,
        )
        from tests.tier1_offline.test_regression_geometry_build_sweep import (
            _geometry_instruction__ccs_text as ccs_text,
        )

        root = _geometry_build__workspace(tmp_path)
        folder = _geometry_build__geometry(root, "wing", CCS_WING, source=None)
        (folder / "wing_sections.csv").write_text(ccs_text(), encoding="utf-8")
        on_125 = plan_geometry_build(folder, build="26.125").awaiting_evidence
        on_124 = plan_geometry_build(folder, build="26.124").awaiting_evidence
        assert "CAD_CREATE_WING_MESH_FROM_CCS" not in on_125
        assert "CAD_CREATE_WING_MESH_FROM_CCS" in on_124

    @staticmethod
    @pytest.mark.requirement("FR-471")
    def test_p0400_geom_build_writes_the_body_its_preview_and_its_record(tmp_path, verified):
        """P0400-GEOM-BUILD (PFS-2081.41): R3, R4, R6 and R7 on a body read back as stated."""
        root = _geometry_build__workspace(tmp_path)
        folder = _geometry_build__geometry(root, "wing", _GEOMETRY_BUILD__MESH_INSTRUCTION)
        plan = plan_geometry_build(folder, registry=verified)
        assert plan.awaiting_evidence == ()
        built = apply_geometry_build(
            plan, runner=_geometry_build__runner(), package_version="0.40.0"
        )
        assert [item.passed for item in built] == [True]
        for name in (
            "wing.fsm",
            "wing.boundaries.toml",
            "wing.preview.vtk",
            "wing.build.json",
            "wing.audit.json",
            "wing.build.txt",
            "wing.build.log",
        ):
            assert (folder / name).is_file(), name
        mesh = folder.with_name("wing_obj")
        assert (mesh / "wing_obj.obj").is_file() and (mesh / "wing_obj.te.txt").is_file()
        assert boundary_names(folder / "wing.fsm") == ("Wing",)
        record = json.loads((folder / "wing.build.json").read_text(encoding="utf-8"))
        assert record["schema_version"] == 1
        assert record["solver"]["build_id"] == "26.125"
        assert record["inspected"] is None
        assert {item["role"] for item in record["inputs"]} == {"instruction", "mesh"}
        assert record["outputs"][0]["boundaries"] == ["Wing"]
        assert record["outputs"][0]["trailing_edge_midpoints"] == 16
        assert record["audit"]["passed"] is True
        vtk = (folder / "wing.preview.vtk").read_text(encoding="utf-8")
        assert "SCALARS boundary int 1" in vtk and "LINES 16 48" in vtk and "\nWing" in vtk
        assert not folder.with_name("wing.partial").exists()
        mesh_record = json.loads((mesh / "wing_obj.build.json").read_text(encoding="utf-8"))
        assert mesh_record["instruction"]["file"] == "../wing/wing.geometry.toml"

    @staticmethod
    @pytest.mark.requirement("FR-471")
    def test_p0400_geom_build_fails_on_other_boundaries_and_promotes_nothing(tmp_path, verified):
        """P0400-GEOM-BUILD (PFS-2081.41): R5, a saved body whose names are not the stated ones."""
        root = _geometry_build__workspace(tmp_path)
        folder = _geometry_build__geometry(
            root,
            "wing",
            _GEOMETRY_BUILD__MESH_INSTRUCTION.replace(
                'boundaries = ["Wing"]', 'boundaries = ["Body"]'
            ).replace(
                "[trailing_edges]",
                '[[operations]]\nop = "rename"\nsurface = "Wing"\nto = "Body"\n[trailing_edges]',
            ),
        )
        plan = plan_geometry_build(folder, registry=verified)
        with pytest.raises(GeometryBuildError, match="carries the boundaries Wing.*states Body"):
            apply_geometry_build(plan, runner=_geometry_build__runner())
        assert not (folder / "wing.fsm").exists()
        assert (folder.with_name("wing.partial") / "wing.build.txt").is_file()

    @staticmethod
    @pytest.mark.requirement("FR-471")
    def test_p0400_geom_build_a_failed_solver_promotes_nothing_and_keeps_the_partial_folder(
        tmp_path, verified
    ):
        """P0400-GEOM-BUILD (PFS-2081.41): R3 and R8, the error the command exits 3 on."""
        root = _geometry_build__workspace(tmp_path)
        folder = _geometry_build__geometry(root, "wing", _GEOMETRY_BUILD__MESH_INSTRUCTION)
        plan = plan_geometry_build(folder, registry=verified)
        with pytest.raises(GeometryBuildError, match="exited 1.*Nothing was promoted"):
            apply_geometry_build(plan, runner=_geometry_build__runner(fail=True))
        assert not (folder / "wing.fsm").exists()
        partial = folder.with_name("wing.partial")
        assert (partial / "wing.build.txt").is_file() and (partial / "wing.build.log").is_file()

    @staticmethod
    @pytest.mark.requirement("FR-471")
    def test_p0400_geom_build_refuses_existing_outputs_without_overwrite(tmp_path, verified):
        """P0400-GEOM-BUILD (PFS-2081.41): R9, a second build is refused until --overwrite."""
        root = _geometry_build__workspace(tmp_path)
        folder = _geometry_build__geometry(root, "wing", _GEOMETRY_BUILD__MESH_INSTRUCTION)
        plan = plan_geometry_build(folder, registry=verified)
        apply_geometry_build(plan, runner=_geometry_build__runner())
        with pytest.raises(InputArtifactError, match="--overwrite"):
            refuse_before_running(plan, overwrite=False, png=False)
        refuse_before_running(plan, overwrite=True, png=False)
        assert apply_geometry_build(plan, runner=_geometry_build__runner(), overwrite=True)[
            0
        ].passed

    @staticmethod
    @pytest.mark.requirement("FR-471")
    def test_p0400_geom_build_apply_on_an_unprobed_build_exits_2(tmp_path, capsys, monkeypatch):
        """P0400-GEOM-BUILD (PFS-2081.41): R9 at the command, before any executable is looked up."""
        root = _geometry_build__workspace(tmp_path)
        (root / "inputs" / "executables.toml").unlink()
        folder = _geometry_build__geometry(root, "wing", _GEOMETRY_BUILD__MESH_INSTRUCTION)
        monkeypatch.chdir(folder)
        assert main(["geometry", "build", "--apply"]) == 2
        err = capsys.readouterr().err
        assert "EXPORT_SURFACE_MESH" in err and "Nothing was written." in err
        assert not folder.with_name("wing.partial").exists()

    @staticmethod
    @pytest.mark.requirement("FR-471")
    def test_p0400_geom_build_refuses_an_instruction_outside_a_workspace(
        tmp_path, capsys, monkeypatch
    ):
        """P0400-GEOM-BUILD (PFS-2081.41): R9, an instruction outside inputs/geometries."""
        folder = tmp_path / "loose"
        folder.mkdir()
        _geometry_build__wing_obj(folder / "src.obj")
        (folder / "loose.geometry.toml").write_text(
            _GEOMETRY_BUILD__MESH_INSTRUCTION, encoding="utf-8"
        )
        monkeypatch.chdir(folder)
        assert main(["geometry", "build"]) == 2
        assert "inputs/geometries/<folder>/" in capsys.readouterr().err

    @staticmethod
    @pytest.mark.requirement("FR-471")
    def test_p0400_geom_build_a_failed_audit_gate_keeps_the_files_and_says_so(tmp_path, verified):
        """P0400-GEOM-BUILD (PFS-2081.41): R8, a zero-area face fails G1; the files stay, exit 1."""
        root = _geometry_build__workspace(tmp_path)
        folder = _geometry_build__geometry(root, "wing", _GEOMETRY_BUILD__MESH_INSTRUCTION)
        plan = plan_geometry_build(folder, registry=verified)
        (built,) = apply_geometry_build(plan, runner=_geometry_build__runner(sliver=True))
        assert built.passed is False
        partial = folder.with_name("wing.partial")
        assert built.folder == partial and built.record == partial / "wing.build.json"
        record = json.loads(built.record.read_text(encoding="utf-8"))
        assert record["audit"]["passed"] is False
        assert any(gate.startswith("G1") for gate in record["audit"]["failed"]), record["audit"]
        assert not (folder / "wing.fsm").exists()
        assert not (folder / "wing.build.json").exists()
        assert not folder.with_name("wing_obj").exists()
        assert (partial / "wing.fsm").is_file()
        assert (partial / "wing.preview.vtk").is_file()
        assert (partial / "wing.build.txt").is_file()
        assert (partial / "wing.build.log").is_file()
        assert (partial / "mesh/wing_obj.obj").is_file()
        assert (partial / "mesh/wing_obj.audit.json").is_file()


def _geometry_cad___lines(
    tmp_path,
    text: str,
    files: dict[str, str] | None = None,
    *,
    build: str = "26.125",
    registry: CommandRegistry | None = None,
) -> list[str]:
    from pyflightstream.workspace._geometry_build import plan_geometry_build
    from tests.tier1_offline.test_regression_geometry_build_sweep import (
        _geometry_build__geometry as geometry,
    )
    from tests.tier1_offline.test_regression_geometry_build_sweep import (
        _geometry_build__workspace as workspace,
    )

    root = workspace(tmp_path)
    folder = geometry(root, "g", f'fs_build = "{build}"\n' + text, source=None)
    for name, content in (files or {}).items():
        (folder / name).write_text(content, encoding="utf-8")
    plan = plan_geometry_build(folder, registry=registry)
    return [line for line in plan.variants[0].script.text.splitlines() if line]


_GEOMETRY_CAD__SECTIONS = (
    'boundaries = ["WING"]\n[create]\nspline_segments = 100\n'
    '[[create.sections]]\nfile = "naca.txt"\nunits = "METER"\nchord_m = 1.0\n'
    '[[create.sections]]\nfile = "naca.txt"\nunits = "METER"\nchord_m = 0.5\ntwist_deg = -2.0\n'
    "leading_edge_m = [0.15, 2.0, 0.0]\n"
    "[create.loft]\nexport_ccs = true\n"
)


def _geometry_cad___curve_import_verified() -> CommandRegistry:
    """The committed database with the curve import marked verified on both builds.

    The route's behaviour is held on a build-agnostic golden: the import is
    broken on 26.124 and 26.125 (RPT-166), so a copy of the database stands in
    for a build on which it works.
    """
    from tests.tier1_offline._p0400_gaps_rt_support import registry_with

    base = registry_with(["CAD_CREATE_IMPORT_CURVE_TXT"], "26.125", Status.VERIFIED)
    return registry_with(["CAD_CREATE_IMPORT_CURVE_TXT"], "26.124", Status.VERIFIED, base=base)


_GEOMETRY_CAD__REFUSED = [
    (
        "bodies and sections",
        'boundaries = ["A"]\n[create]\n[[create.bodies]]\nshape = "sphere"\n'
        'center_m = [0.0, 0.0, 0.0]\nradius_m = 0.5\n[[create.sections]]\nfile = "naca.txt"\n'
        'units = "METER"\nchord_m = 1.0\n\n',
        "exactly one",
    ),
    (
        "mirror curves",
        'boundaries = ["A"]\n[create]\nmirror_curves = true\n[[create.bodies]]\n'
        'shape = "sphere"\ncenter_m = [0.0, 0.0, 0.0]\nradius_m = 0.5\n\n',
        "mirror_curves",
    ),
    ("curve drawing", 'boundaries = ["A"]\n[create]\n[[create.bodies]]\nshape = "arc"\n', "shape"),
    (
        "a radius of zero",
        'boundaries = ["A"]\n[create]\n[[create.bodies]]\nshape = "sphere"\n'
        "center_m = [0.0, 0.0, 0.0]\nradius_m = 0.0\n\n",
        "radius_m",
    ),
    (
        "a CAD op without its body",
        'boundaries = ["A"]\n[cad]\nfile = "rig.igs"\n[[cad.operations]]\nop = "mirror"\n'
        'plane = "XZ"\n\n',
        "body",
    ),
]


class TestGeometryCad:
    """Tier 1, 0.40.0: CAD bodies before conversion, and the solver-built geometry (FR-475).

    P0400-GEOM-CAD (PFS-2081.14). Offline goldens of the emitted lines: the
    commands are documented and unprobed, and the build refuses to run them until
    a licensed probe verifies them on the build; the build tests guard that gate.
    """

    @staticmethod
    @pytest.mark.requirement("FR-475")
    def test_p0400_geom_cad_body_operations_sit_between_import_and_conversion(tmp_path):
        """P0400-GEOM-CAD (PFS-2081.14): R1, every body operation, in order, in metres."""
        lines = _geometry_cad___lines(
            tmp_path,
            'boundaries = ["Wing"]\n[cad]\nfile = "rig.igs"\n'
            '[[cad.operations]]\nop = "delete_by_threshold"\naxis = "X"\nabove_m = 1.2\n'
            '[[cad.operations]]\nop = "mirror"\nbody = 1\nplane = "XZ"\n'
            '[[cad.operations]]\nop = "scale"\nbody = 1\nfactor = 0.5\n'
            '[[cad.operations]]\nop = "translate"\nbody = 1\nvector_m = [0.1, 0.0, 0.0]\n'
            '[[cad.operations]]\nop = "rotate"\nbody = 1\naxis = "Y"\nangle_deg = 2.0\n'
            '[[cad.operations]]\nop = "delete"\nbody = 2\n'
            '[trailing_edges]\ndetect = "auto"\n',
            {"rig.igs": "IGES"},
        )
        start = next(i for i, line in enumerate(lines) if line.startswith("IMPORT_CAD"))
        assert lines[start + 2 : start + 9] == [
            "CAD_BODY_SELECT_BY_THRESHOLD 1 X 1.2 ABOVE DELETE",
            "CAD_BODY_MIRROR 1 XZ",
            "CAD_BODY_SCALE 1 0.5",
            "CAD_BODY_TRANSLATE 1 0.1 0.0 0.0 METER",
            "CAD_BODY_ROTATE 1 Y 2.0",
            "CAD_BODY_DELETE 2",
            "CONVERT_CAD_TO_MESH -1",
        ]

    @staticmethod
    @pytest.mark.requirement("FR-475")
    def test_p0400_geom_cad_a_sphere_is_built_by_the_solver(tmp_path):
        """P0400-GEOM-CAD (PFS-2081.14): R2, the settings then the primitive."""
        lines = _geometry_cad___lines(
            tmp_path,
            'boundaries = ["Sphere"]\n[create]\nmerge_tolerance_pct = 1.0\n'
            "curvature_points_per_circle = 96\n\n"
            '[[create.bodies]]\nshape = "sphere"\ncenter_m = [0.0, 0.0, 0.0]\nradius_m = 0.5\n'
            "[trailing_edges]\nnone = true\n",
        )
        assert lines[1:5] == [
            "CAD_CREATE_INITIALIZE",
            "SET_CAD_CREATE_MERGE_TOLERANCE 1.0",
            "SET_CAD_CURVATURE_REFINEMENT 96",
            "CAD_CREATE_SPHERE 1 0.0 0.0 0.0 0.5",
        ]

    @staticmethod
    @pytest.mark.requirement("FR-475")
    @pytest.mark.parametrize("build", ["26.124", "26.125"])
    def test_p0400_geom_cad_the_loft_route_is_refused_where_the_curve_import_is_broken(
        tmp_path, build
    ):
        """P0400-GEOM-CAD (PFS-2081.14): the section loft is refused on 26.124 and 26.125.

        Its sections enter through CAD_CREATE_IMPORT_CURVE_TXT, recorded broken on both
        builds (RPT-166); the evidence gate names the command and the CCS route is the
        working one.
        """
        with pytest.raises(
            BrokenCommandError, match="CAD_CREATE_IMPORT_CURVE_TXT is recorded broken"
        ):
            _geometry_cad___lines(
                tmp_path,
                _GEOMETRY_CAD__SECTIONS,
                {"naca.txt": "1.0 0.0\n0.0 0.0\n1.0 0.0\n"},
                build=build,
            )

    @staticmethod
    @pytest.mark.requirement("FR-475")
    def test_p0400_geom_cad_a_wing_is_lofted_from_its_sections(tmp_path):
        """P0400-GEOM-CAD (PFS-2081.14): R2, each section placed, then the CCS loft."""
        lines = _geometry_cad___lines(
            tmp_path,
            _GEOMETRY_CAD__SECTIONS,
            {"naca.txt": "1.0 0.0\n0.0 0.0\n1.0 0.0\n"},
            registry=_geometry_cad___curve_import_verified(),
        )
        body = [
            line for line in lines if not line.startswith(("C:", "/")) and "naca.txt" not in line
        ]
        start = body.index("CAD_CREATE_INITIALIZE")
        assert body[start + 1 :][:14] == [
            "SET_CAD_CREATE_SPLINE_SEGMENTS 100",
            "CAD_CREATE_IMPORT_CURVE_TXT METER 2D 1 XZ",
            "CAD_CREATE_CURVE_SELECT 1",
            "CAD_CREATE_SCALE_CURVES 1.0 DELETE",
            "CAD_CREATE_TRANSLATE_CURVES 0.0 0.0 0.0 DELETE",
            "CAD_CREATE_CURVE_UNSELECT 1",
            "CAD_CREATE_IMPORT_CURVE_TXT METER 2D 1 XZ",
            "CAD_CREATE_CURVE_SELECT 2",
            "CAD_CREATE_SCALE_CURVES 0.5 DELETE",
            "CAD_CREATE_ROTATE_CURVES 1 Y -2.0 DELETE",
            "CAD_CREATE_TRANSLATE_CURVES 0.15 2.0 0.0 DELETE",
            "CAD_CREATE_CURVE_UNSELECT 2",
            "CAD_CREATE_CURVE_SELECT -1",
            "CAD_CREATE_CURVE_EXPORT_CCS",
        ]
        assert "CAD_CREATE_WING_MESH_FROM_CCS WING TRUE SHARP TRUE C2 C0" in lines

    @staticmethod
    @pytest.mark.requirement("FR-475")
    @pytest.mark.parametrize(
        ("label", "text", "words"),
        _GEOMETRY_CAD__REFUSED,
        ids=[c[0] for c in _GEOMETRY_CAD__REFUSED],
    )
    def test_p0400_geom_cad_refusals(tmp_path, label, text, words):
        """P0400-GEOM-CAD (PFS-2081.14): R2 and R3, refused before any solver starts."""
        with pytest.raises(InputArtifactError, match=words):
            _geometry_cad___lines(tmp_path, text, {"naca.txt": "1 0\n", "rig.igs": "IGES"})


_GEOMETRY_COMPLETE__SWEEP = (
    'fs_build = "26.125"\nboundaries = ["Body", "Base"]\n'
    '[ccs]\nfile = "wing_sections.csv"\nunits = "METER"\nkind = "wing"\ncomponent = 1\n'
    "mark_trailing_edges = false\n"
    '[[ccs.control_surfaces]]\nname = "Base"\nv0 = 0.5\nv1 = 0.9\nu0 = 0.25\nu1 = 0.25\n'
    "hinge_height = 0.5\nangle_deg = 0.0\nslot_gap_pct = 1.0\n"
    '[sweep]\ncontrol_surface = "Base"\nangle_deg = [-10.0, 0.0, 10.0]\n'
)


_GEOMETRY_COMPLETE__HEADER = (
    "POL  | HIDDEN | RUN | AIRCRAFT  | CONFIGURATION | DESCRIPTION   | FLIGHT_CONDITION"
    "                 | SWEEP_VALUES | GEOMETRY | REF  | SET  | PPROC | SYMMETRY | SYMMETRY_LOADS"
    " | NCPUS | WALLTIME | FS_BUILD | WORKFLOW | VAR_NAMES_VALUES"
)


_GEOMETRY_COMPLETE__ROW = (
    "9401 |    1   |  1  | DemoWing  | clean         | LOFTED_WING   | MACH:0.15, REmi:2.0, "
    "ALPHA:sweep | 0.0,4.0,8.0  | wing.fsm | r040 | s040 | p040  | NONE     | -              | 8"
    "     | 1h       | 26.125   | steady   | -"
)


def _geometry_complete___sweep(tmp_path):
    from tests.tier1_offline.test_regression_geometry_build_sweep import (
        _geometry_build__geometry as geometry,
    )
    from tests.tier1_offline.test_regression_geometry_build_sweep import (
        _geometry_build__workspace as workspace,
    )
    from tests.tier1_offline.test_regression_geometry_build_sweep import (
        _geometry_instruction__ccs_text as ccs_text,
    )

    root = workspace(tmp_path)
    folder = geometry(root, "wing", _GEOMETRY_COMPLETE__SWEEP, source=None)
    (folder / "wing_sections.csv").write_text(ccs_text(), encoding="utf-8")
    return root, folder


def _geometry_complete___body_runner(fail_once: str | None = None):
    """A runner saving the two-boundary body; ``fail_once`` fails that variant's first run."""
    from pyflightstream.workspace._geometry_build import SolverOutcome
    from tests.tier1_offline.test_regression_geometry_build_sweep import (
        _GEOMETRY_BUILD__WING_FSM as WING_FSM,
    )
    from tests.tier1_offline.test_regression_geometry_build_sweep import (
        _geometry_build__wing_obj as wing_obj,
    )

    failed: set[str] = set()
    lock = threading.Lock()

    def run(script: Path, work: Path) -> SolverOutcome:
        name = script.name.removesuffix(".build.txt")
        with lock:
            fail = fail_once is not None and name.endswith(fail_once) and name not in failed
            failed.add(name)
        if fail:
            return SolverOutcome(True, 1, 1.0, "licence refused", "exited 1")
        shutil.copyfile(WING_FSM.with_name("20_BODY.fsm"), work / f"{name}.fsm")
        wing_obj(work / f"{name}.obj", group="Body")
        return SolverOutcome(False, 0, 1.0, "log", "")

    return run


class TestGeometryComplete:
    """Tier 1, 0.40.0: the rest of the geometry design (FR-471 R10, FR-472 R5 to R7, FR-473 R5).

    P0400-GEOM-ROWS, P0400-GEOM-PARALLEL, P0400-GEOM-OVERLAY, P0400-GEOM-MIRROR and
    P0400-GEOM-CARRY (PFS-2081.41). The sweep is built on the committed
    solver-written ``20_BODY.fsm`` (boundaries ``Body`` and ``Base``), standing for
    a wing ``Body`` with a control surface ``Base``; the runner stands in for the
    solver as in ``test_p0400_geometry_build.py``.
    """

    @staticmethod
    @pytest.mark.requirement("FR-472")
    def test_p0400_geom_rows_one_row_per_variant_copied_from_the_template(
        tmp_path, monkeypatch, capsys
    ):
        """P0400-GEOM-ROWS (PFS-2081.41): R5, three cells set per row; matrix untouched."""
        _, folder = _geometry_complete___sweep(tmp_path)
        matrix = tmp_path / "m.fs"
        matrix.write_text(
            _GEOMETRY_COMPLETE__HEADER + "\n" + "-" * 40 + "\n" + _GEOMETRY_COMPLETE__ROW + "\n",
            encoding="utf-8",
        )
        before = matrix.read_bytes()
        monkeypatch.chdir(folder.parent)
        assert main(["geometry", "build", "wing", "--rows", "9401", "--matrix", str(matrix)]) == 0
        out = capsys.readouterr().out
        rows = [
            line.strip()
            for line in out.splitlines()
            if line.strip().startswith(("9402", "9403", "9404"))
        ]
        assert len(rows) == 3
        cells = [[cell.strip() for cell in row.split("|")] for row in rows]
        assert [c[4] for c in cells] == ["Base-100", "Base+000", "Base+100"]
        assert [c[8] for c in cells] == [
            "wing_Base-100.fsm",
            "wing_Base+000.fsm",
            "wing_Base+100.fsm",
        ]
        assert all(c[3] == "DemoWing" and c[12] == "NONE" for c in cells)
        assert matrix.read_bytes() == before

    @staticmethod
    @pytest.mark.requirement("FR-472")
    def test_p0400_geom_rows_refusals(tmp_path, monkeypatch, capsys):
        """P0400-GEOM-ROWS (PFS-2081.41): R5, a POL the matrix lacks, and --rows without --matrix."""  # noqa: E501
        _, folder = _geometry_complete___sweep(tmp_path)
        matrix = tmp_path / "m.fs"
        matrix.write_text(
            _GEOMETRY_COMPLETE__HEADER + "\n" + _GEOMETRY_COMPLETE__ROW + "\n", encoding="utf-8"
        )
        monkeypatch.chdir(folder.parent)
        assert main(["geometry", "build", "wing", "--rows", "1", "--matrix", str(matrix)]) == 2
        assert "holds no row POL 1" in capsys.readouterr().err
        assert main(["geometry", "build", "wing", "--rows", "9401"]) == 2
        assert "--matrix" in capsys.readouterr().err

    @staticmethod
    @pytest.mark.requirement("FR-472")
    def test_p0400_geom_parallel_builds_every_variant_and_reruns_a_failed_one_alone(
        tmp_path, monkeypatch
    ):
        """P0400-GEOM-PARALLEL (PFS-2081.41): R6, two at once; the refused variant runs again alone."""  # noqa: E501
        from pyflightstream.workspace._geometry_build import (
            apply_geometry_build,
            plan_geometry_build,
        )
        from tests.tier1_offline.test_regression_geometry_build_sweep import (
            TestRfixBGeometry as _TestRfixBGeometry,
        )
        from tests.tier1_offline.test_regression_geometry_build_sweep import (
            _geometry_build__verified_registry as verified_registry,
        )

        overlap_proof = (
            _TestRfixBGeometry.test_p0400_rfixb_parallel_calls_overlap_and_retry_runs_alone
        )

        overlap_proof(tmp_path, monkeypatch)
        plan = plan_geometry_build(
            "wing", cwd=tmp_path / "ws" / "inputs" / "geometries", registry=verified_registry()
        )
        with pytest.raises(InputArtifactError, match=r"parallel \(CLI: --parallel\) 3"):
            apply_geometry_build(
                plan, runner=_geometry_complete___body_runner(), parallel=3, overwrite=True
            )

    @staticmethod
    @pytest.mark.requirement("FR-472")
    def test_p0400_geom_overlay_holds_the_control_surface_of_every_variant(tmp_path):
        """P0400-GEOM-OVERLAY (PFS-2081.41): R7, one file in the base folder, tagged per variant."""
        from pyflightstream.workspace._geometry_build import (
            apply_geometry_build,
            plan_geometry_build,
        )
        from tests.tier1_offline.test_regression_geometry_build_sweep import (
            _geometry_build__verified_registry as verified_registry,
        )

        _, folder = _geometry_complete___sweep(tmp_path)
        plan = plan_geometry_build("wing", cwd=folder.parent, registry=verified_registry())
        apply_geometry_build(plan, runner=_geometry_complete___body_runner())
        text = (folder / "wing.sweep.vtk").read_text(encoding="utf-8")
        assert "SCALARS variant int 1" in text
        assert "tags 1 3 string\nBase-100\nBase+000\nBase+100" in text
        cells = int(text.split("CELL_DATA ")[1].split()[0])
        variants = text.split("LOOKUP_TABLE default\n")[1].split("\nFIELD")[0].split()
        assert len(variants) == cells and set(variants) == {"1", "2", "3"}

    @staticmethod
    @pytest.mark.requirement("FR-473")
    def test_p0400_geom_mirror_of_a_deflected_body_is_warned(tmp_path):
        """P0400-GEOM-MIRROR (PFS-2081.41): R5, MIRROR over a nonzero angle; NONE and 0 silent."""
        from pyflightstream.workspace._geometry_build import (
            apply_geometry_build,
            plan_geometry_build,
        )
        from pyflightstream.workspace._geometry_record import judge_the_row_geometry
        from tests.tier1_offline.test_regression_geometry_build_sweep import (
            _geometry_build__verified_registry as verified_registry,
        )

        _, folder = _geometry_complete___sweep(tmp_path)
        plan = plan_geometry_build("wing", cwd=folder.parent, registry=verified_registry())
        apply_geometry_build(plan, runner=_geometry_complete___body_runner())
        record = json.loads(
            (folder.parent / "wing_Base+100" / "wing_Base+100.build.json").read_text(
                encoding="utf-8"
            )
        )
        assert record["control_surfaces"] == [{"name": "Base", "angle_deg": 10.0}]

        def said(name: str, symmetry: str) -> list[str]:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                judge_the_row_geometry(
                    folder.parent / name / f"{name}.fsm",
                    "9413",
                    fs_build="26.125",
                    mesh_import=None,
                    symmetry=symmetry,
                )
            return [str(w.message) for w in caught if issubclass(w.category, PyflightstreamWarning)]

        assert any(
            "SYMMETRY MIRROR" in text and "Base at 10.0 deg" in text
            for text in said("wing_Base+100", "MIRROR")
        )
        assert not any("SYMMETRY MIRROR" in text for text in said("wing_Base+100", "NONE"))
        assert not any("SYMMETRY MIRROR" in text for text in said("wing_Base+000", "MIRROR"))

    @staticmethod
    @pytest.mark.requirement("FR-471")
    def test_p0400_geom_carry_the_runs_operations_into_the_built_mesh_sidecar(tmp_path):
        """P0400-GEOM-CARRY (PFS-2081.41): R10, from the source's sidecar, then kept by a rebuild."""  # noqa: E501
        from pyflightstream.workspace._geometry_build import (
            apply_geometry_build,
            plan_geometry_build,
        )
        from tests.tier1_offline.test_regression_geometry_build_sweep import (
            _GEOMETRY_BUILD__MESH_INSTRUCTION as MESH_INSTRUCTION,
        )
        from tests.tier1_offline.test_regression_geometry_build_sweep import (
            _geometry_build__geometry as geometry,
        )
        from tests.tier1_offline.test_regression_geometry_build_sweep import (
            _geometry_build__runner as runner,
        )
        from tests.tier1_offline.test_regression_geometry_build_sweep import (
            _geometry_build__verified_registry as verified_registry,
        )
        from tests.tier1_offline.test_regression_geometry_build_sweep import (
            _geometry_build__workspace as workspace,
        )

        root = workspace(tmp_path)
        folder = geometry(root, "wing", MESH_INSTRUCTION)
        (folder / "src.boundaries.toml").write_text(
            'boundaries = ["Wing"]\n[import]\nunits = "METER"\n'
            '[[import.operations]]\nop = "translate"\nvector = [1.0, 0.0, 0.0]\n'
            '[wake_termination]\ndetect = "auto"\n',
            encoding="utf-8",
        )
        plan = plan_geometry_build(folder, registry=verified_registry())
        (built,) = apply_geometry_build(plan, runner=runner())
        sidecar = folder.with_name("wing_obj") / "wing_obj.boundaries.toml"
        text = sidecar.read_text(encoding="utf-8")
        assert 'op = "translate"' in text and "[wake_termination]" in text
        assert 'detect = "auto"' in text.split("[trailing_edges]")[1]
        assert any("carried over the sidecar operations translate" in note for note in built.notes)
        sidecar.write_text(
            text.replace('op = "translate"', 'op = "rotate"').replace(
                "vector = [1.0, 0.0, 0.0]", 'axis = "X"\nangle_deg = 5.0'
            ),
            encoding="utf-8",
        )
        apply_geometry_build(plan, runner=runner(), overwrite=True)
        rebuilt = sidecar.read_text(encoding="utf-8")
        assert 'op = "rotate"' in rebuilt and 'op = "translate"' not in rebuilt


_GEOMETRY_INSTRUCTION__CCS_WING = (
    'fs_build = "26.125"\nboundaries = ["WING", "AIL"]\n'
    '[ccs]\nfile = "wing_sections.csv"\nunits = "METER"\nkind = "wing"\ncomponent = 1\n'
    '[[ccs.control_surfaces]]\nname = "AIL"\nv0 = 0.5\nv1 = 0.9\nu0 = 0.25\nu1 = 0.25\n'
    "hinge_height = 0.5\nangle_deg = 0.0\nslot_gap_pct = 1.0\n"
)


def _geometry_instruction__ccs_text() -> str:
    """A one-component CCS file: a symmetric airfoil at two stations."""
    points = []
    for k in range(7):
        x = 1.0 - k / 6
        points.append((x, 0.06 * math.sin(math.pi * x)))
    for k in range(1, 7):
        x = k / 6
        points.append((x, -0.06 * math.sin(math.pi * x)))
    lines = ["Aircraft;PYFS_TEST", "Units;Meter", "", "Component;CCS_WING", "LiftingSurface;true"]
    for y in (0.0, 4.0):
        lines.append("CrossSection;" + ";".join(f"{x:.4f};{y:.4f};{z:.4f}" for x, z in points))
    return "\n".join(lines) + "\n"


def _geometry_instruction__write(
    tmp_path: Path, text: str, files: dict[str, str] | None = None, name: str = "g"
) -> Path:
    folder = tmp_path / "inputs" / "geometries" / name
    folder.mkdir(parents=True, exist_ok=True)
    for file, content in (files or {}).items():
        (folder / file).write_text(content, encoding="utf-8")
    path = folder / f"{name}.geometry.toml"
    path.write_text(text, encoding="utf-8")
    return path


_GEOMETRY_INSTRUCTION__MESH = '[mesh]\nfile = "m.obj"\nunits = "METER"\n'


_GEOMETRY_INSTRUCTION__OBJ = {"m.obj": "v 0 0 0\nv 1 0 0\nv 0 1 0\ng Blade\nf 1 2 3\n"}


_GEOMETRY_INSTRUCTION__REFUSED = [
    ("no source", 'boundaries = ["A"]\n', "exactly one source table"),
    (
        "two sources",
        'boundaries = ["A"]\n' + _GEOMETRY_INSTRUCTION__MESH + '[cad]\nfile = "m.obj"\n',
        "exactly one source table",
    ),
    (
        "unknown key",
        'boundaries = ["A"]\ncolour = 1\n' + _GEOMETRY_INSTRUCTION__MESH,
        "does not read colour",
    ),
    ("a path", 'boundaries = ["A"]\n[mesh]\nfile = "sub/m.obj"\nunits = "METER"\n', "is a path"),
    (
        "absent",
        'boundaries = ["A"]\n[mesh]\nfile = "x.obj"\nunits = "METER"\n',
        "holds no such file",
    ),
    ("step", 'boundaries = ["A"]\n[cad]\nfile = "m.step"\n', "STEP is refused"),
    (
        "empty outputs",
        'boundaries = ["Blade"]\noutputs = []\n' + _GEOMETRY_INSTRUCTION__MESH,
        "outputs",
    ),
    (
        "other output",
        'boundaries = ["Blade"]\noutputs = ["stl"]\n' + _GEOMETRY_INSTRUCTION__MESH,
        "outputs",
    ),
    ("space in a name", 'boundaries = ["Bla de"]\n' + _GEOMETRY_INSTRUCTION__MESH, "whitespace"),
    ("no boundaries", _GEOMETRY_INSTRUCTION__MESH, "boundaries"),
    (
        "units OTHER",
        'boundaries = ["Blade"]\n[mesh]\nfile = "m.obj"\nunits = "OTHER"\n',
        "names no length",
    ),
    (
        "translate",
        'boundaries = ["Blade"]\n'
        + _GEOMETRY_INSTRUCTION__MESH
        + '[[operations]]\nop = "translate"\nvector = [1.0, 0.0, 0.0]\n',
        "TRANSLATE and\nROTATE|stay in the run",
    ),
    (
        "rotate",
        'boundaries = ["Blade"]\n'
        + _GEOMETRY_INSTRUCTION__MESH
        + '[[operations]]\nop = "rotate"\naxis = "X"\nangle_deg = 5.0\n',
        "stay in the run",
    ),
    (
        "names that do not follow",
        'boundaries = ["Blade", "Other"]\n'
        + _GEOMETRY_INSTRUCTION__MESH
        + '[[operations]]\nop = "rename"\nsurface = "Blade"\nto = "X"\n',
        "names",
    ),
    (
        "sweep off a wing",
        'boundaries = ["Blade"]\n'
        + _GEOMETRY_INSTRUCTION__MESH
        + '[sweep]\ncontrol_surface = "AIL"\nangle_deg = [1.0]\n',
        "sweep",
    ),
]


class TestGeometryInstruction:
    """Tier 1, 0.40.0: the geometry instruction file, read and refused (FR-470).

    P0400-GEOM-FILE (PFS-2081.41). One source table, the stated boundaries as the
    contract, the operations undone to find the names the source makes, and every
    refusal of the file itself before any solver starts. The CCS fixture is a
    synthetic symmetric airfoil lofted between two stations, never a research
    geometry.
    """

    @staticmethod
    @pytest.mark.requirement("FR-470")
    def test_p0400_geom_file_each_source_reads_with_its_defaults(tmp_path):
        """P0400-GEOM-FILE (PFS-2081.41): R1 and R2, the default outputs per source."""
        ccs = read_geometry_instruction(
            _geometry_instruction__write(
                tmp_path,
                _GEOMETRY_INSTRUCTION__CCS_WING,
                {"wing_sections.csv": _geometry_instruction__ccs_text()},
                "w",
            )
        )
        assert (ccs.kind, ccs.outputs, ccs.name) == ("ccs", ("fsm",), "w")
        mesh = read_geometry_instruction(
            _geometry_instruction__write(
                tmp_path,
                'boundaries = ["Blade"]\n' + _GEOMETRY_INSTRUCTION__MESH,
                _GEOMETRY_INSTRUCTION__OBJ,
                "m",
            )
        )
        assert (mesh.kind, mesh.outputs, mesh.fs_build) == ("mesh", ("obj",), None)
        create = read_geometry_instruction(
            _geometry_instruction__write(
                tmp_path,
                'boundaries = ["Sphere"]\n[create]\n[[create.bodies]]\nshape = "sphere"\n'
                "center_m = [0.0, 0.0, 0.0]\nradius_m = 0.5\n",
                name="s",
            )
        )
        assert (create.kind, create.outputs) == ("create", ("fsm",))

    @staticmethod
    @pytest.mark.requirement("FR-470")
    def test_p0400_geom_file_the_source_names_are_the_boundaries_with_the_operations_undone(
        tmp_path,
    ):
        """P0400-GEOM-FILE (PFS-2081.41): R3, a rename then a copy, undone in reverse."""
        text = (
            'boundaries = ["Blade1", "Blade2", "Blade3"]\n'
            + _GEOMETRY_INSTRUCTION__MESH
            + '[[operations]]\nop = "rename"\nsurface = "Blade"\nto = "Blade1"\n'
            + '[[operations]]\nop = "circular_copy"\nsurface = "Blade1"\naxis = "X"\ncount = 3\n'
            + 'angle_deg = 120.0\nnames = ["Blade2", "Blade3"]\n'
        )
        instruction = read_geometry_instruction(
            _geometry_instruction__write(tmp_path, text, _GEOMETRY_INSTRUCTION__OBJ)
        )
        assert source_names(instruction) == ["Blade"]

    @staticmethod
    @pytest.mark.requirement("FR-470")
    @pytest.mark.parametrize(
        ("label", "text", "words"),
        _GEOMETRY_INSTRUCTION__REFUSED,
        ids=[case[0] for case in _GEOMETRY_INSTRUCTION__REFUSED],
    )
    def test_p0400_geom_file_every_refusal_names_the_file(tmp_path, label, text, words):
        """P0400-GEOM-FILE (PFS-2081.41): R6, each refused before any solver starts."""
        files = dict(_GEOMETRY_INSTRUCTION__OBJ)
        files["m.step"] = "x"
        path = _geometry_instruction__write(tmp_path, text, files)
        with pytest.raises(InputArtifactError) as raised:
            read_geometry_instruction(path)
        assert str(path) in str(raised.value)
        import re

        assert re.search(words, str(raised.value)), str(raised.value)

    @staticmethod
    @pytest.mark.requirement("FR-470")
    def test_p0400_geom_file_the_ccs_table_keeps_the_sidecars_refusals(tmp_path):
        """P0400-GEOM-FILE (PFS-2081.41): R2 and R6, the REAL form and the file unit."""
        files = {"wing_sections.csv": _geometry_instruction__ccs_text()}
        real = _GEOMETRY_INSTRUCTION__CCS_WING.replace(
            "slot_gap_pct = 1.0\n", 'slot_gap_pct = 1.0\nspace = "REAL"\n'
        )
        with pytest.raises(InputArtifactError, match="REAL"):
            read_geometry_instruction(_geometry_instruction__write(tmp_path, real, files, "r"))
        file_unit = _GEOMETRY_INSTRUCTION__CCS_WING.replace('units = "METER"', 'units = "FILE"')
        with pytest.raises(InputArtifactError, match="FILE"):
            read_geometry_instruction(_geometry_instruction__write(tmp_path, file_unit, files, "f"))
        trailing = _GEOMETRY_INSTRUCTION__CCS_WING + '[trailing_edges]\ndetect = "auto"\n'
        with pytest.raises(InputArtifactError, match="mark\\s+their own"):
            read_geometry_instruction(_geometry_instruction__write(tmp_path, trailing, files, "t"))

    @staticmethod
    @pytest.mark.requirement("FR-470")
    def test_p0400_geom_file_a_second_instruction_in_one_folder_is_refused(tmp_path):
        """P0400-GEOM-FILE (PFS-2081.41): the folder holds one instruction."""
        from pyflightstream.workspace._geometry_build import locate_instruction

        path = _geometry_instruction__write(
            tmp_path,
            'boundaries = ["Blade"]\n' + _GEOMETRY_INSTRUCTION__MESH,
            _GEOMETRY_INSTRUCTION__OBJ,
        )
        (path.parent / "other.geometry.toml").write_text("x = 1\n", encoding="utf-8")
        with pytest.raises(InputArtifactError, match="holds 2 instructions"):
            locate_instruction(None, path.parent)

    @staticmethod
    def test_p0400_geom_file_the_variant_tag_keeps_tenths_and_a_sign():
        """P0400-GEOM-FILE (PFS-2081.41): the tag a sweep folder carries (FR-472)."""
        assert [variant_tag("AIL", a) for a in (-10.0, 0.0, 10.0, 2.5)] == [
            "AIL-100",
            "AIL+000",
            "AIL+100",
            "AIL+025",
        ]


def _geometry_operations___script(tmp_path, boundaries: str, operations: str) -> list[str]:
    from pyflightstream.workspace._geometry_build import plan_geometry_build
    from tests.tier1_offline.test_regression_geometry_build_sweep import (
        _geometry_build__geometry as geometry,
    )
    from tests.tier1_offline.test_regression_geometry_build_sweep import (
        _geometry_build__workspace as workspace,
    )

    root = workspace(tmp_path)
    folder = geometry(
        root,
        "rotor",
        f'fs_build = "26.125"\nboundaries = {boundaries}\n[mesh]\nfile = "src.obj"\n'
        f'units = "METER"\n\n' + operations + "[trailing_edges]\nnone = true\n",
    )
    plan = plan_geometry_build(folder)
    return [line for line in plan.variants[0].script.text.splitlines() if line]


def _geometry_operations___between(lines: list[str]) -> list[str]:
    start = lines.index("CLEAR") + 1
    end = next(i for i, line in enumerate(lines) if line.startswith("SET_SIMULATION_LENGTH_UNITS"))
    return lines[start:end]


_GEOMETRY_OPERATIONS__REFUSED = [
    (
        "names count",
        '["Wing", "W2"]',
        'op = "circular_copy"\nsurface = "Wing"\naxis = "X"\ncount = 3\nangle_deg = 120.0\n'
        'names = ["W2"]\n\n',
        "creates 2",
    ),
    (
        "solved quantity",
        '["Wing", "T"]',
        'op = "extract_faces"\nquantity = "CP"\nmin = 0.0\nname = "T"\n',
        "solved quantity",
    ),
    (
        "no range",
        '["Wing", "T"]',
        'op = "extract_faces"\nquantity = "X"\nname = "T"\n',
        "min, max or both",
    ),
    ("absent surface", '["Wing"]', 'op = "fill_holes"\nsurface = "Hub"\n', "Hub"),
    ("every surface", '["Wing"]', 'op = "fill_holes"\nsurface = "all"\n', 'no "all" form'),
]


class TestGeometryOperations:
    """Tier 1, 0.40.0: the mesh operations of the instruction file, as emitted (FR-474).

    P0400-GEOM-P1OPS (PFS-2081.13). Each kind is emitted by the typed emitter in
    the reference frame, its surface cited by its position at its own step; the
    names it states are the names after it. The commands are unprobed, so these
    are offline goldens of the emitted lines; the build refuses to run them until
    a licensed probe verifies them; the build tests guard that gate.
    """

    @staticmethod
    @pytest.mark.requirement("FR-474")
    def test_p0400_geom_p1ops_copies_cite_the_surface_and_count_the_original(tmp_path):
        """P0400-GEOM-P1OPS (PFS-2081.13): R1, circular and linear copies."""
        lines = _geometry_operations___script(
            tmp_path,
            '["Wing", "W2", "W3", "W4"]',
            '[[operations]]\nop = "circular_copy"\nsurface = "Wing"\naxis = "X"\ncount = 3\n'
            'angle_deg = 120.0\nnames = ["W2", "W3"]\n'
            '[[operations]]\nop = "linear_copy"\nsurface = "W3"\ncount = 2\nvector = [0.0, 1.0, 0.0]\n'  # noqa: E501
            'names = ["W4"]\n',
        )
        assert _geometry_operations___between(lines) == [
            "SURFACE_CIRCULAR_COPY_PASTE 1 1 1 3 120.0",
            "SURFACE_LINEAR_COPY_PASTE 3 2 1 METER 0.0 1.0 0.0",
        ]

    @staticmethod
    @pytest.mark.requirement("FR-474")
    def test_p0400_geom_p1ops_cut_fill_and_clean(tmp_path):
        """P0400-GEOM-P1OPS (PFS-2081.13): R2 and R3, the cut replaces the surface by its parts."""
        lines = _geometry_operations___script(
            tmp_path,
            '["Nose", "Body"]',
            '[[operations]]\nop = "cut"\nsurface = "Wing"\nplane = "YZ"\noffset = 0.5\n'
            'names = ["Nose", "Body"]\n'
            '[[operations]]\nop = "fill_holes"\nsurface = "Body"\n'
            '[[operations]]\nop = "delete_degenerate_faces"\n',
        )
        assert _geometry_operations___between(lines) == [
            "SURFACE_CUT_BY_PLANE",
            "FRAME 1",
            "PLANE YZ",
            "OFFSET 0.5",
            "SURFACE 1",
            "SURFACE_AUTO_HOLE_FILL 2",
            "DELETE_DEGENERATE_FACES",
        ]

    @staticmethod
    @pytest.mark.requirement("FR-474")
    def test_p0400_geom_p1ops_extract_selects_then_creates_on_consecutive_lines(tmp_path):
        """P0400-GEOM-P1OPS (PFS-2081.13): R4, a restricted extraction and a deletion."""
        lines = _geometry_operations___script(
            tmp_path,
            '["Wing", "Tip"]',
            '[[operations]]\nop = "extract_faces"\nsurface = "Wing"\nquantity = "Y"\nmin = 3.0\n'
            'name = "Tip"\n\n'
            '[[operations]]\nop = "delete_faces"\nquantity = "AREA"\nmax = 1e-9\n',
        )
        assert _geometry_operations___between(lines) == [
            "SURFACE_SELECT_BY_ID 1",
            "SURFACE_SELECT_BY_THRESHOLD",
            "FRAME 1",
            "THRESHOLD Y",
            "MIN_VALUE 3.0",
            "MAX_VALUE 0.0",
            "RANGE ABOVE_MIN",
            "SUBSET SELECTED_FACES",
            "CREATE_NEW_SURFACE_FROM_SELECTION",
            "SURFACE_SELECT_BY_THRESHOLD",
            "FRAME 1",
            "THRESHOLD AREA",
            "MIN_VALUE 0.0",
            "MAX_VALUE 1e-09",
            "RANGE BELOW_MAX",
            "SUBSET ALL_FACES",
            "DELETE_SELECTED_FACES",
        ]

    @staticmethod
    @pytest.mark.requirement("FR-474")
    def test_p0400_geom_p1ops_node_moves_are_pinned_to_the_mesh(tmp_path):
        """P0400-GEOM-P1OPS (PFS-2081.13): R5, the pin holds, and a changed mesh is refused."""
        from tests.tier1_offline.test_regression_geometry_build_sweep import (
            _geometry_build__wing_obj as wing_obj,
        )

        probe = wing_obj(tmp_path / "probe.obj")
        digest = hashlib.sha256(probe.read_bytes()).hexdigest()
        operation = (
            f'[[operations]]\nop = "transform_nodes"\nmesh_sha256 = "{digest}"\nnodes = [3, 4]\n'
            "vector = [0.0, 0.0, 0.002]\n"
        )
        lines = _geometry_operations___script(tmp_path / "a", '["Wing"]', operation)
        assert _geometry_operations___between(lines) == [
            "SELECT_MESH_NODE 3",
            "SELECT_MESH_NODE 4",
            "TRANSFORM_SELECTED_NODES 1 TRANSLATION 0.0 0.0 0.002",
        ]
        stale = operation.replace(digest, "0" * 64)
        with pytest.raises(InputArtifactError, match="pinned to the mesh sha256 0000"):
            _geometry_operations___script(tmp_path / "b", '["Wing"]', stale)

    @staticmethod
    @pytest.mark.requirement("FR-474")
    @pytest.mark.parametrize(
        ("label", "boundaries", "operation", "words"),
        _GEOMETRY_OPERATIONS__REFUSED,
        ids=[c[0] for c in _GEOMETRY_OPERATIONS__REFUSED],
    )
    def test_p0400_geom_p1ops_refusals_name_the_operation(
        tmp_path, label, boundaries, operation, words
    ):
        """P0400-GEOM-P1OPS (PFS-2081.13): R6, refused before any solver starts."""
        with pytest.raises(InputArtifactError, match=words):
            _geometry_operations___script(tmp_path, boundaries, "[[operations]]\n" + operation)


def _rfixg_record__legacy_record() -> dict:
    """The legacy record's field shape, with neutral paths and synthetic values."""
    return {
        "source": "source/body.fsm",
        "source_sha256": "a" * 64,
        "obj": "geometries/body.obj",
        "obj_sha256": "b" * 64,
        "te_file_sha256": "c" * 64,
        "f001_sha256": "d" * 64,
        "blades": 2,
        "stations": 2,
        "panels_per_side": 2,
        "faces_per_blade": 4,
        "vertices_per_blade": 4,
        "faces_total": 8,
        "te_edges_per_blade": 1,
        "blade_volume_m3": 0.001,
        "radii_m": [0.1, 0.2],
        "chord_m": [0.02, 0.01],
        "beta_deg": [20.0, 10.0],
        "struct_radii_m": [0.1, 0.2],
        "struct_chord_m": [0.02, 0.01],
        "struct_beta_deg": [20.0, 10.0],
        "pitch_axis_from_quarter_chord_in_section_m": [[0.0, 0.0], [0.0, 0.0]],
        "omega_rad_per_s": 10.0,
        "time_increment_s": 0.01,
        "rpm": 100.0,
    }


class TestRfixGRecord:
    """Planning a body with a legacy build record must give an actionable refusal."""

    pytestmark = pytest.mark.requirement("P0400-RFIXG-RECORD")

    @staticmethod
    @pytest.mark.requirement("FR-473")
    def test_p0400_rfixg_legacy_record_is_refused_by_matrix_plan(tmp_path: Path) -> None:
        workspace = _rfixg_record__make_library(
            tmp_path / "ws", register_build=("26.125", Path(sys.executable).as_posix())
        )
        folder = workspace.inputs_dir / "geometries" / "body"
        folder.mkdir()
        (folder / "body.obj").write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
        (folder / "body.boundaries.toml").write_text('boundaries = ["Body"]\n', encoding="utf-8")
        record = folder / "body.build.json"
        record.write_text(json.dumps(_rfixg_record__legacy_record()), encoding="utf-8")
        row = (
            "9401 | TestGeom | GEOM | 3.10 | 0.0890 | AL | 0.0 | r003 | s002 | e001 "
            "| 003 | 26.125 | 0 | 1 | OUTPUTS: loads_{point}.txt / VELOCITY: 30.0 / GEOMETRY: body.obj"  # noqa: E501
        )
        matrix = _rfixg_record__write_matrix(tmp_path / "matrix.fs", [row])
        with pytest.raises(InputArtifactError) as caught:
            resolve_matrix(
                matrix,
                workspace,
                name="matrix",
                fs_version="26.125",
                recipes=_RFIXG_RECORD__RECIPES,
            )
        message = str(caught.value)
        assert str(record) in message
        assert "instruction.file" in message and "missing" in message

    @staticmethod
    @pytest.mark.requirement("FR-473")
    @pytest.mark.parametrize(
        ("data", "key"),
        [
            ({"instruction": {"sha256": "a" * 64}}, "instruction.file"),
            ({"instruction": {"file": "body.toml"}}, "instruction.sha256"),
            (
                {"instruction": {"file": "body.toml", "sha256": "a" * 64}, "inputs": [{}]},
                "inputs[0].file",
            ),
        ],
    )
    def test_p0400_rfixg_incomplete_input_record_names_missing_key(
        tmp_path: Path, data, key: str
    ) -> None:
        body = tmp_path / "body.fsm"
        body.write_text("saved", encoding="utf-8")
        record = tmp_path / "body.build.json"
        record.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(InputArtifactError) as caught:
            judge_the_row_geometry(body, "9401", fs_build="26.125", mesh_import=None)
        assert str(record) in str(caught.value) and key in str(caught.value)

    @staticmethod
    @pytest.mark.requirement("FR-473")
    @pytest.mark.parametrize(
        ("data", "diagnosis"),
        [
            ([], "expected an object"),
            ({"inputs": None}, "inputs must be a list"),
            ({"instruction": {"file": "", "sha256": "a" * 64}}, "instruction.file"),
            ({"instruction": {"file": "body.toml", "sha256": 10}}, "instruction.sha256"),
        ],
    )
    def test_p0400_rfixg_uninterpretable_record_is_refused(
        tmp_path: Path, data, diagnosis: str
    ) -> None:
        body = tmp_path / "body.fsm"
        body.write_text("saved", encoding="utf-8")
        record = tmp_path / "body.build.json"
        record.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(InputArtifactError) as caught:
            judge_the_row_geometry(body, "9401", fs_build="26.125", mesh_import=None)
        assert str(record) in str(caught.value) and diagnosis in str(caught.value)


class TestRfixHGeometryOrder:
    """Render a millimetre-source build: units, edge marking, save, then OBJ export."""

    @staticmethod
    @pytest.mark.requirement("FR-471")
    @pytest.mark.parametrize("build", ["26.124", "26.125"])
    @pytest.mark.parametrize("route", ["detect", "file"])
    def test_p0400_rfixh_geometry_order(
        tmp_path: Path, build: str, route: Literal["detect", "file"]
    ):
        """P0400-RFIXH-GEOMETRY-ORDER: both marking routes precede save and export."""
        instruction = GeometryInstruction(
            name="wing",
            outputs=("fsm", "obj"),
            boundaries=("Wing",),
            kind="mesh",
            mesh=MeshSource(file="wing.obj", units="MILLIMETER"),
            trailing_edges=TrailingEdgeMarking(route=route),
        )
        script = render_geometry_script(
            instruction,
            folder=tmp_path,
            work=tmp_path / "partial",
            version=build,
            trailing_edge_points_m=((1.0, 0.0, 0.0),),
        )
        marking = (
            "IMPORT_WAKE_EDGES_FROM_FILE"
            if route == "file"
            else "AUTO_DETECT_TRAILING_EDGES"
            if build == "26.124"
            else "DETECT_TRAILING_EDGES_BY_SURFACE"
        )
        commands = script.commands
        ordered = (
            "NEW_SIMULATION",
            "IMPORT",
            "SET_SIMULATION_LENGTH_UNITS",
            marking,
            "SAVEAS",
            "EXPORT_SURFACE_MESH",
            "CLOSE_FLIGHTSTREAM",
        )
        assert [commands.index(command) for command in ordered] == sorted(
            commands.index(command) for command in ordered
        ), script.text
        assert "UNITS MILLIMETER" in script.text
        assert "SET_SIMULATION_LENGTH_UNITS METER" in script.text

    @staticmethod
    @pytest.mark.requirement("FR-471")
    def test_p0400_rfixh_mesh_export_preserves_the_current_phase():
        """P0400-RFIXH-GEOMETRY-PHASE: export works after setup and during geometry."""
        script = Script("26.124")
        script.emit("NEW_SIMULATION")
        script.emit("EXPORT_SURFACE_MESH", "OBJ", -1, "first.obj")
        script.emit("SURFACE_RENAME", 1, "Wing")
        script.emit("SET_SIMULATION_LENGTH_UNITS", "METER")
        script.emit("SAVEAS", "wing.fsm")
        script.emit("EXPORT_SURFACE_MESH", "OBJ", -1, "wing.obj")
        with pytest.raises(ScriptOrderError):
            script.emit("SURFACE_RENAME", 1, "TooLate")

    @staticmethod
    @pytest.mark.requirement("FR-471")
    @pytest.mark.parametrize("units,scale", [("METER", 1.0), ("MILLIMETER", 1000.0)])
    @pytest.mark.parametrize("outputs", ['["obj"]', '["fsm", "obj"]'])
    @pytest.mark.parametrize("marked", [False, True])
    def test_rel7_001_built_mesh_units_follow_the_export(tmp_path, units, scale, outputs, marked):
        """Build a millimetre source, then interpret the exported vertices using its sidecar."""
        import shutil
        import tomllib

        import numpy as np

        from pyflightstream._fsm import boundary_names, boundary_owners, surface_mesh
        from pyflightstream.workspace._geometry_build import (
            SolverOutcome,
            apply_geometry_build,
            plan_geometry_build,
        )
        from tests.tier1_offline.test_regression_geometry_build_sweep import (
            _GEOMETRY_BUILD__MESH_INSTRUCTION as MESH_INSTRUCTION,
        )
        from tests.tier1_offline.test_regression_geometry_build_sweep import (
            _GEOMETRY_BUILD__WING_FSM as WING_FSM,
        )
        from tests.tier1_offline.test_regression_geometry_build_sweep import (
            _geometry_build__geometry as geometry,
        )
        from tests.tier1_offline.test_regression_geometry_build_sweep import (
            _geometry_build__verified_registry as verified_registry,
        )
        from tests.tier1_offline.test_regression_geometry_build_sweep import (
            _geometry_build__workspace as workspace,
        )

        instruction = MESH_INSTRUCTION.replace('["fsm", "obj"]', outputs).replace(
            'units = "METER"', f'units = "{units}"'
        )
        saved = WING_FSM if marked else WING_FSM.with_name("20_BODY.fsm")
        if not marked:
            instruction = instruction.replace('["Wing"]', '["Body", "Base"]').replace(
                'detect = "auto"', "none = true"
            )
        folder = geometry(workspace(tmp_path), "wing", instruction)
        expected, faces = surface_mesh(saved)
        owners = boundary_owners(saved)
        names = boundary_names(saved)

        def obj_text(factor):
            lines = [f"v {x * factor} {y * factor} {z * factor}" for x, y, z in expected]
            previous = None
            for face, owner in zip(faces, owners, strict=True):
                if owner != previous:
                    lines.append(f"g {names[owner - 1]}")
                    previous = owner
                lines.append("f " + " ".join(str(i + 1) for i in face))
            return "\n".join(lines) + "\n"

        def export_metres(script, work):
            shutil.copyfile(saved, work / "wing.fsm")
            (work / "wing.obj").write_text(obj_text(1.0), encoding="utf-8")
            return SolverOutcome(False, 0, 0.0, "offline metre export", "")

        source = folder / "src.obj"
        source.write_text(obj_text(scale), encoding="utf-8")
        plan = plan_geometry_build(folder, registry=verified_registry())
        assert f"UNITS {units}" in plan.variants[0].script.text
        assert "SET_SIMULATION_LENGTH_UNITS METER" in plan.variants[0].script.text
        built = apply_geometry_build(plan, runner=export_metres)
        assert built[0].promoted
        mesh_folder = folder if outputs == '["obj"]' else folder.with_name("wing_obj")
        stem = mesh_folder.name
        sidecar = tomllib.loads((mesh_folder / f"{stem}.boundaries.toml").read_text())
        export = np.array(
            [
                [float(value) for value in line.split()[1:]]
                for line in (mesh_folder / f"{stem}.obj").read_text().splitlines()
                if line.startswith("v ")
            ]
        )
        metres_per_unit = {"METER": 1.0, "MILLIMETER": 0.001}
        imported = export * metres_per_unit[sidecar["import"]["units"]]
        np.testing.assert_allclose(imported, expected)
        assert sidecar["import"]["units"] == "METER"


class TestSweep1Cli:
    """P0400 sweep-1 CLI regressions, without a solver."""

    @staticmethod
    def test_p0400_failure_alias_caller(tmp_path, monkeypatch, capsys):
        """P0400-SWEEP-FAILURE-CALLER: the CLI gives the alias reader its workspace."""
        workspace, matrix, _ = _sweep_1_cli___two_simulations(tmp_path, monkeypatch)
        assert cli.main(_sweep_1_cli___argv("plan", workspace, matrix)) == 0
        capsys.readouterr()
        point = SimpleNamespace(
            sim_id="5002",
            run_id="warm/sim_5002/A2",
            status="FAILED_EXECUTION",
            error="synthetic failure",
        )
        error = CampaignErrors([point], records=[])
        monkeypatch.setattr(cli, "run_matrix", lambda *args, **kwargs: (_ for _ in ()).throw(error))
        roots = []
        monkeypatch.setattr(
            cli, "failure_alias_lines", lambda failures, rows, root=None: roots.append(root) or []
        )
        assert cli.main(_sweep_1_cli___argv("run", workspace, matrix)) == 2
        capsys.readouterr()
        assert roots == [workspace.root]

    @staticmethod
    def test_p0400_output_flags(tmp_path, monkeypatch):
        """P0400-SWEEP-OUTPUT-FLAGS: convert accepts --out; the old alias warns."""
        parser = _build_parser()
        options = [
            "convert",
            "matrix.fs",
            "--name",
            "warm",
            "--fs-version",
            "26.120",
            "--fs-exe",
            "solver.exe",
        ]
        monkeypatch.setattr(cli, "convert_matrix", lambda *args, **kwargs: "synthetic campaign")
        destination = tmp_path / "campaign.toml"
        args = parser.parse_args([*options, "--out", str(destination)])
        assert cli._cmd_convert(args, {}) == 0
        assert destination.read_text(encoding="utf-8") == "synthetic campaign"
        args = parser.parse_args([*options, "--output", str(destination)])
        with pytest.warns(PyflightstreamWarning, match="deprecated.*--out"):
            assert cli._cmd_convert(args, {}) == 0

    @staticmethod
    def test_p0400_fsi_out(tmp_path):
        """P0400-SWEEP-FSI-OUT: the FSI console uses the same output flag."""
        from pyflightstream.fsi.cli import main

        assert main(["init-dummy", "--node-count", "1", "--out", str(tmp_path)]) == 0
        with pytest.warns(PyflightstreamWarning, match="deprecated.*--out"):
            assert main(["init-dummy", "--node-count", "1", "--dir", str(tmp_path)]) == 0

    @staticmethod
    def test_p0400_mark_failed_words_and_points(tmp_path, capsys):
        """P0400-SWEEP-MARK-SELECT: the twins accept words and explicit point names."""
        rows = [
            {"run_id": f"warm/sim_{sim}/{point}", "sim_id": sim, "status": "CONVERGED"}
            for sim in ("1", "2")
            for point in ("A0", "A2")
        ]
        (tmp_path / "runs.json").write_text(json.dumps(encode_rows(rows)), encoding="utf-8")
        assert (
            cli.main(
                [
                    "mark-failed",
                    "--workspace",
                    str(tmp_path),
                    "--sims",
                    "1",
                    "2",
                    "--points",
                    "A2",
                    "--apply",
                ]
            )
            == 0
        )
        capsys.readouterr()
        updated = _read_record_rows(tmp_path / "runs.json")
        assert [row["status"] for row in updated] == [
            "CONVERGED",
            "FAILED_MARKED",
            "CONVERGED",
            "FAILED_MARKED",
        ]

    @staticmethod
    def test_p0400_exemption_policy_substitution():
        """P0400-SWEEP-EXEMPT-POLICY: equal counts cannot hide a changed exemption."""
        from tests.tier1_offline import test_repository_guards as guards

        check = getattr(guards, "_assert_exemption_policy", None)
        assert callable(check), "the exemption policy needs a set assertion"
        config = guards._shipped_surface_module().load_config(guards.SHIPPED_SURFACE_CONFIG)
        check(config)
        with pytest.raises(AssertionError):
            check(
                dataclasses.replace(
                    config,
                    exempt_paths=(config.exempt_paths - {"README.md"}) | {"src/accidental.py"},
                )
            )
        with pytest.raises(AssertionError):
            check(dataclasses.replace(config, exempt_trees=("guide/", "src/")))

    @staticmethod
    def test_p0400_release_architecture_section(tmp_path, monkeypatch, capsys):
        """P0400-SWEEP-RELEASE-ARCH: a tag needs its own architecture heading."""
        from scripts import check_release_published as release

        check = getattr(release, "architecture_problem", None)
        assert callable(check), "release verification must check version coverage"
        assert check("v0.39.0", "## The 0.39.0 additions and their limits") is None
        assert check("v0.39.0", "## The 0.390.0 additions\nA mention of 0.39.0 is not a section.")
        page = tmp_path / "docs/srs/architecture-srs.md"
        page.parent.mkdir(parents=True)
        page.write_text("## The 0.38.0 additions\n", encoding="utf-8")
        monkeypatch.setattr(release, "REPO", tmp_path)
        monkeypatch.setattr(release, "version_tags", lambda: ["v0.39.0"])
        monkeypatch.setattr(release, "recorded_dois", lambda: {"v0.39.0": "10.0000/synthetic"})
        monkeypatch.setattr(release, "owed_in_the_changelog", lambda: set())
        assert release.main(["v0.39.0", "--offline"]) == 1
        assert "architecture-srs.md" in capsys.readouterr().out

    @staticmethod
    def test_p0400_flagship_exports_its_assessment_log(monkeypatch):
        """P0400-SWEEP-FLAGSHIP-LOG: every built point exports the log the assessor reads."""
        import runpy
        import sys

        script = Path(__file__).resolve().parents[2] / "examples/steady_polar.py"
        monkeypatch.setattr(sys, "argv", [str(script)])
        built = runpy.run_path(str(script))
        assert "EXPORT_LOG\nsolver_a0_log.txt" in built["scripts"][-4.0].render()

    @staticmethod
    def test_p0400_examples_use_public_cli_wrapper():
        """P0400-SWEEP-EXAMPLE-API: shipped examples use the public decorator."""
        import ast

        import pyflightstream

        assert callable(getattr(pyflightstream, "cli_entrypoint", None))
        root = Path(__file__).resolve().parents[2]
        for name in (
            "boundary_layer_sections",
            "continuation_frame_recovery",
            "sampled_field_export",
            "surface_with_native_strength",
            "workspace_fsi_calibration",
        ):
            tree = ast.parse((root / "examples" / f"{name}.py").read_text(encoding="utf-8"))
            imports = [
                node.module
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
                and any(alias.name == "cli_entrypoint" for alias in node.names)
            ]
            assert imports == ["pyflightstream"]

    @staticmethod
    @pytest.mark.parametrize(
        "status", ["MAX_ITER_REACHED", "FAILED_DIVERGED", "COMPLETED_MAX_ITER"]
    )
    def test_p0400_flagship_uses_assessed_status(status):
        """P0400-SWEEP-FLAGSHIP-VERDICT: the assessor's outcome reaches the example record."""
        import ast

        from pyflightstream.workspace import RunStatus

        root = Path(__file__).resolve().parents[2]
        tree = ast.parse((root / "examples/steady_polar.py").read_text(encoding="utf-8"))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "RunRecord"
        ]
        assert len(calls) == 1
        expression = next(keyword.value for keyword in calls[0].keywords if keyword.arg == "status")
        code = compile(ast.Expression(expression), "example-record-status", "eval")
        assessed = RunStatus(status)
        assert (
            eval(
                code,
                {
                    "RunStatus": RunStatus,
                    "converged": True,
                    "assessment": SimpleNamespace(status=assessed),
                },
            )
            == assessed
        )


_SWEEP_1_CONTRACTS__ROOT = Path(__file__).resolve().parents[2]


class TestSweep1Contracts:
    """Offline contract regressions for sweep-1."""

    @staticmethod
    def test_p0400_clip_in_report(tmp_path):
        """P0400-SWEEP-CP-CLIP (FR-26): the report states the clip beside each point's numbers."""
        assert "minimum_cp" in {
            field.name for field in dataclasses.fields(_sweep_1_contracts___points()[0])
        }
        run = _sweep_1_contracts___run(
            [
                dataclasses.replace(point, minimum_cp=-20.0)
                for point in _sweep_1_contracts___points()
            ]
        )
        report, markdown = write_physics_report(run, tmp_path, date="2026-10-12")
        point = yaml.safe_load(report.read_text(encoding="utf-8"))["cases"]["PHY-01"]["points"][0]
        assert point["minimum_cp"] == -20.0
        assert "Minimum Cp clip for a0: -20.0" in markdown.read_text(encoding="utf-8")

    @staticmethod
    def test_p0400_clip_read_from_run_setup(monkeypatch):
        """P0400-SWEEP-CP-CLIP-JOIN: the run's effective clip reaches the physics point."""
        from types import SimpleNamespace

        from pyflightstream.qa import matrix
        from pyflightstream.workspace import RunStatus

        report = SimpleNamespace(total={"CL": 0.3, "CDp": 0.01}, current_iteration=300)
        monkeypatch.setattr(matrix, "parse_run_loads", lambda *args: report)
        record = SimpleNamespace(
            point={"alpha": 4.0},
            status=RunStatus.CONVERGED,
            sim_id="5001",
            run_id="warm/sim_5001/A4",
            solver_setup={"flags": {"SOLVER_MINIMUM_CP": {"value": -20.0}}},
        )
        assert getattr(matrix.point_result(None, record), "minimum_cp", None) == -20.0

    @staticmethod
    def test_p0400_cost_exclusion_authority():
        """P0400-SWEEP-COST-SET: QA and planning share one exclusion set."""
        from pyflightstream.qa.cost import _EXCLUDED_STATUSES
        from pyflightstream.run._plan import _NOT_A_COST_SAMPLE

        assert _EXCLUDED_STATUSES is _NOT_A_COST_SAMPLE

    @staticmethod
    def test_p0400_group_fit_unknown_preserved(tmp_path, monkeypatch):
        """P0400-SWEEP-FIT-UNKNOWN: no estimate is not a judgment that a job fits."""
        from tests.support_helpers import grouped_plan_fixture
        from tests.tier1_offline.test_p0350_batch_plan import _plan

        workspace, matrix = grouped_plan_fixture(tmp_path, walltimes=("30m", "30m"))
        plan = _plan(workspace, matrix)
        assert any(job.fits is None for job in plan.grouping.jobs)

    @staticmethod
    def test_p0400_manual_help_inputs():
        """P0400-SWEEP-MANUAL-HELP (FR-44): root help explains required inputs and page ranges."""
        from pyflightstream.utils.cli import _parser

        help_text = _parser().format_help()
        assert "--chapter-pages" in help_text and "table of contents" in help_text
        assert "--manual" in help_text and "--source" in help_text

    @staticmethod
    def test_p0400_manual_extra_upfront(monkeypatch, capsys):
        """P0400-SWEEP-MANUAL-EXTRA: missing PDF support precedes artifact reads."""
        import builtins

        from pyflightstream.utils.cli import main

        original = builtins.__import__

        def importing(name, *args, **kwargs):
            if name == "pypdf":
                raise ImportError("synthetic missing extra")
            return original(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", importing)
        assert (
            main(
                [
                    "coverage",
                    "--manual",
                    "absent.pdf",
                    "--source",
                    "SRC-753",
                    "--chapter-pages",
                    "1-2",
                ]
            )
            == 2
        )
        assert "pyflightstream[manual]" in capsys.readouterr().err

    @staticmethod
    def test_p0400_post_help_archive_opt_in():
        """P0400-SWEEP-POST-SIMS: selecting simulations preserves opt-in archiving."""
        parser = _build_parser()
        post = next(
            action for action in parser._actions if isinstance(action.choices, dict)
        ).choices["post"]
        help_text = " ".join(post.format_help().split())
        assert "By default, rebuilds overwrite products in place without an archive." in help_text
        assert "--archive" in help_text
        assert "keep the files a rebuild replaces" in help_text
        assert parser.parse_args(["post"]).archive is False
        assert parser.parse_args(["post", "--archive"]).archive is True

    @staticmethod
    @pytest.mark.parametrize("version", ["25.000", "25.100"])
    def test_p0400_physics_block_terminates(version):
        """P0400-SWEEP-PHYSICS-END: a keyword block closes before the next command."""
        script = Script(version)
        script.emit("PHYSICS", auto_trail_edges=True, auto_wake_nodes=True)
        assert script.render().strip().endswith("END")

    @staticmethod
    @pytest.mark.parametrize("version", ["25.000", "25.100", "26.000"])
    def test_p0400_boolean_unite_payload(version):
        """P0400-SWEEP-BOOLEAN-LINES: each body index and sign pair gets one payload line."""
        script = Script(version)
        script.emit("BOOLEAN_UNITE_MESH", 2, ["1,POSITIVE", "2,NEGATIVE"])
        assert script.render().splitlines()[1:3] == ["1,POSITIVE", "2,NEGATIVE"]

    @staticmethod
    @pytest.mark.parametrize(
        "command,arguments,filename",
        [
            ("EXPORT_VOLUME_SECTION_2D_VTK", (1, "second.vtk"), "second.vtk"),
            ("EXPORT_ALL_SURFACE_STREAMLINES", ("surface.dat",), "surface.dat"),
            ("STABILITY_TOOLBOX_EXPORT", ("coefficients.txt",), "coefficients.txt"),
        ],
    )
    def test_p0400_export_phase_order(command, arguments, filename):
        """P0400-SWEEP-EXPORT-PHASE: sibling exports can follow one another."""
        script = Script("26.124")
        script.emit(
            "CREATE_NEW_RECTANGLE_VOLUME_SECTION",
            1,
            "YZ",
            0.0,
            0,
            -1.0,
            -1.0,
            1.0,
            1.0,
            "NONE",
            0.0,
            0,
            1.0,
        )
        script.emit("EXPORT_VOLUME_SECTION_VTK", 1, "first.vtk")
        script.emit(command, *arguments)
        assert filename in script.render()

    @staticmethod
    @pytest.mark.parametrize(
        "version,command",
        [("26.122", "SET_OUTFLOW_TRAILING_EDGES"), ("26.124", "SET_OUTLET_TRAILING_EDGES")],
    )
    def test_p0400_base_region_is_not_mesh_boundary(version, command):
        """P0400-SWEEP-BASE-REGION: a base-region index is not a mesh boundary index."""
        script = Script(version)
        script.declare_existing(boundaries=1)
        script.emit(command, 2)
        assert f"{command} 2" in script.render()

    @staticmethod
    def test_p0400_changelog_fragments_folded():
        """P0400-SWEEP-CHANGELOG: the five shipped corrections belong to 0.37.0."""
        text = (_SWEEP_1_CONTRACTS__ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        release = text.split("## [0.37.0]", 1)[1].split("## [", 1)[0]
        assert "Correction recorded 2026-10-12" in release
        assert "Normalize the 26.125 pressure and viscous drag plots" in release
        assert not list((_SWEEP_1_CONTRACTS__ROOT / "changelog.d").glob("W2-*.md"))

    @staticmethod
    def test_p0400_short_factor_collision_control(tmp_path):
        """P0400-SWEEP-TAG-COLLISION: a short tag collision refuses without overwrite."""
        from pyflightstream._errors import InputArtifactError
        from pyflightstream.workspace import refine_mesh
        from tests.tier1_offline.test_p0390_taglen import _source

        source = _source(tmp_path, names=["Wing"])
        first = refine_mesh(source, factor=1.000001, out_dir=tmp_path / "levels")
        with pytest.raises(InputArtifactError, match="overwrite"):
            refine_mesh(source, factor=1.000002, out_dir=tmp_path / "levels")
        second = refine_mesh(source, factor=1.000002, out_dir=tmp_path / "levels", overwrite=True)
        assert second.folder == first.folder

    @staticmethod
    @pytest.mark.parametrize(
        "text_needed",
        [
            "6 significant digits",
            "{sim} is the first simulation",
            "FAILED_*, WALLTIME_REACHED, SUBMITTED and RAN_MISSING_LOG",
        ],
    )
    def test_p0400_doc_contracts(text_needed):
        """P0400-SWEEP-DOC-CONTRACTS: requirements state tag, cost and placeholder rules."""
        text = _SWEEP_1_CONTRACTS__FUNCTIONAL_REQUIREMENTS.read_text(encoding="utf-8")
        assert text_needed in text
        if text_needed == "6 significant digits":
            assert "Distinct exact factors can round to the same short tag" in text
            assert "Two short tags (R1) differ when the selections differ in a factor" not in text

    @staticmethod
    def test_p0400_zero_lifting_log_warning():
        """P0400-SWEEP-ZERO-WAKE: explicit zero wake and edge counts warn, never fail."""
        log = importlib.import_module("pyflightstream.results.log")
        reader = getattr(log, "lifting_log_warnings", None)
        assert callable(reader)
        assert (
            len(reader("Wake initialized. 0 strands marked for growth.\n0 trailing edges found."))
            == 2
        )
        assert (
            reader("Wake initialized. 3 strands marked for growth.\n2 trailing edges found.") == []
        )

    @staticmethod
    def test_p0400_rotor_efficiency_warns(tmp_path):
        """P0400-SWEEP-ETA-BOUND: an efficiency above one is a point-naming warning."""
        import warnings

        from pyflightstream.post.products import write_rotor_table
        from tests.tier1_offline.test_goal026_item06_rotor_loads import (
            _reference,
            _rotor,
            _surfaces,
        )
        from tests.tier1_offline.test_regression_post_rotor_acoustics import (
            _post_1_rotor_table___row as _row,
        )

        row = _row("camp/sim_1/P1", surfaces=_surfaces(Blade1={"Cz": 100.0, "CMz": 0.001}))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            written = write_rotor_table(
                tmp_path / "rotor.csv", rotor=_rotor("Z"), rows=[row], reference=_reference()
            )
        assert written is not None
        assert any(
            "camp/sim_1/P1" in str(w.message) and "exceeds 1" in str(w.message) for w in caught
        )

    @staticmethod
    @pytest.mark.parametrize("live", [True, False])
    def test_p0400_rotor_uses_own_clock(tmp_path, monkeypatch, live):
        """P0400-SWEEP-ROTOR-CLOCK: the second rotor's two-step turn is its own window."""
        from types import SimpleNamespace

        from pyflightstream.post import _rotor_plan

        table = tmp_path / "plots.txt"
        table.write_text("synthetic", encoding="utf-8")
        seen = []
        series = SimpleNamespace(steps=[1, 2, 3, 4])
        monkeypatch.setattr(_rotor_plan, "plots_table_series", lambda path: ([], series))
        monkeypatch.setattr(
            _rotor_plan, "_rotor_history_groups", lambda *args, **kwargs: (["B"], None)
        )
        monkeypatch.setattr(
            _rotor_plan,
            "blade_passage_average",
            lambda series, *, window, read_steps: (
                seen.append(window)
                or SimpleNamespace(
                    fields={f"{part}_B": [1.0] for part in _rotor_plan._PLOT_COMPONENTS}
                )
            ),
        )
        monkeypatch.setattr(_rotor_plan, "_judge_average", lambda *args, **kwargs: None)
        record = SimpleNamespace(
            reductions={
                "rotors": {
                    "slow": {"steps_per_revolution": 4},
                    "fast": {"steps_per_revolution": 2},
                },
                "time_average": {"window_from": "LAST_REVS_AVG = 1 revolution(s) of 4 steps"},
            }
        )
        ctx = SimpleNamespace(
            windows={"P1": (1, 4)},
            window=None,
            sources={"P1": ["run/P1"]},
            by_run={"run/P1": record},
            matrix_row=SimpleNamespace(variables={"LAST_REVS_AVG": "1"} if live else {}),
            plots={"P1": table},
            frozen={},
            sim_id="1",
        )
        _rotor_plan._averaged_rotor_newtons(ctx, SimpleNamespace(name="P1"), "fast", ["B"])
        assert seen == [(3, 4)]

    @staticmethod
    def test_p0400_zero_wake_reaches_post_log(tmp_path, monkeypatch):
        """P0400-SWEEP-ZERO-POST-LOG: explicit zero counts are point-naming WARNINGs."""
        import json

        from pyflightstream.post import products
        from pyflightstream.workspace import CampaignWorkspace, RunRecord, RunStatus

        workspace = CampaignWorkspace(tmp_path)
        sim = workspace.create_sim("1")
        log = sim / "P1_log.txt"
        log.write_text(
            "Wake initialized. 0 strands marked for growth.\n0 trailing edges found.\n",
            encoding="utf-8",
        )
        record = RunRecord(
            run_id="warm/sim_1/P1",
            sim_id="1",
            fs_version_requested="26.125",
            package_version="0.40.0",
            script_sha256="a" * 64,
            raw_flag=False,
            status=RunStatus.CONVERGED,
            matrix_stem="warm",
            outputs=[log.name],
        )
        workspace.append_record(record)
        monkeypatch.setattr(products, "_campaign_products", lambda *args, **kwargs: [])
        products.write_campaign_products(workspace, matrix_stem="warm")
        posted = workspace.products_dir("warm")
        text = (posted / "post.log").read_text(encoding="utf-8")
        assert text.count("WARNING") == 2
        assert (
            "warm/sim_1/P1" in text
            and "zero trailing edges" in text
            and "zero wake strands" in text
        )
        assert workspace.read_manifest()[0].status is RunStatus.CONVERGED
        data = json.loads((posted / "post.log.json").read_text(encoding="utf-8"))
        assert len(data["records"]) == 2


class TestSweep1Core:
    """Offline regressions for the remaining sweep-1 cross-file joins."""

    @staticmethod
    @pytest.mark.parametrize("filename", ["pyfs.toml", "pyfs.local.toml"])
    @pytest.mark.parametrize("key", ["console", "verbose", "log_level", "pproc_warnings"])
    def test_p0400_log_defaults_remedy(tmp_path, filename, key):
        """P0400-SWEEP-LOG-DEFAULTS (FR-436): misplaced console keys name the [log] remedy."""
        (tmp_path / filename).write_text(f'[defaults]\n{key} = "normal"\n', encoding="utf-8")
        with pytest.raises(InputArtifactError, match=r"\[log\]"):
            read_workspace_settings(tmp_path)

    @staticmethod
    @pytest.mark.parametrize("filename", ["pyfs.toml", "pyfs.local.toml"])
    @pytest.mark.parametrize("value", ["true", "false"])
    def test_p0400_acceptance_defaults_refused(tmp_path, filename, value):
        """P0400-SWEEP-ACCEPTANCE (FR-436): acceptance belongs to an entry or a typed flag."""
        (tmp_path / filename).write_text(
            f"[defaults]\naccept_unregistered_build = {value}\n", encoding="utf-8"
        )
        with pytest.raises(InputArtifactError, match="executables.local.toml"):
            read_workspace_settings(tmp_path)

    @staticmethod
    @pytest.mark.parametrize("key,value", [("fs_exe", '"solver.exe"'), ("local", "true")])
    def test_p0400_machine_defaults_local_only(tmp_path, key, value):
        """P0400-SWEEP-LOCAL-DEFAULTS (FR-436): machine choices stay in the local overlay."""
        path = tmp_path / "pyfs.toml"
        path.write_text(f"[defaults]\n{key} = {value}\n", encoding="utf-8")
        with pytest.raises(InputArtifactError, match="pyfs.local.toml"):
            read_workspace_settings(tmp_path)
        path.unlink()
        (tmp_path / "pyfs.local.toml").write_text(
            f"[defaults]\n{key} = {value}\n", encoding="utf-8"
        )
        assert key in read_workspace_settings(tmp_path).defaults

    @staticmethod
    @pytest.mark.parametrize("filename", ["pyfs.toml", "pyfs.local.toml"])
    def test_p0400_runs_default_refused(tmp_path, filename):
        """P0400-SWEEP-RUNS-DEFAULT: manifest selection is per invocation."""
        (tmp_path / filename).write_text('[defaults]\nruns = "other.json"\n', encoding="utf-8")
        with pytest.raises(InputArtifactError, match="one invocation"):
            read_workspace_settings(tmp_path)

    @staticmethod
    def test_p0400_overview_relative_path(tmp_path, monkeypatch):
        """P0400-SWEEP-OVERVIEW-RELPATH: a relative destination opens an absolute URI."""
        module = importlib.import_module("pyflightstream.overview")
        opened = []
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(module.webbrowser, "open", opened.append)
        assert module.overview(path="overview.html").is_file()
        assert opened == [(tmp_path / "overview.html").as_uri()]

    @staticmethod
    def test_p0400_uniform_tag_limit(tmp_path):
        """P0400-SWEEP-UNIFORM-TAG: every automatic tag obeys the 32 character limit."""
        from tests.tier1_offline.test_p0390_taglen import _request

        spec = _config.FamilySpec(
            factor=0.0000123456, chordwise=0.0000123456, spanwise=0.0000123456
        )
        request = _request(tmp_path, ["Wing"], over={"Wing": spec})
        assert len(_config.level_tag(request, ["Wing"])) <= _config.TAG_MAX
        assert _config.tag_selection(request, ["Wing"]) == ["Wing"]

    @staticmethod
    @pytest.mark.parametrize("route", ["group", "family", "family-list"])
    def test_p0400_numbered_boundary_exact(route):
        """P0400-SWEEP-BOUNDARY-EXACT: an absent numbered label cited alone is refused by name."""
        inventory = ["Hub2", "Hub3", "MainWing"]

        def operation(**options):
            if route == "group":
                return select_group_members(["Hub1"], inventory, **options)
            selection = "Hub1" if route == "family" else ["Hub1"]
            return select_families(selection, inventory, lambda name: False, **options)

        with pytest.raises(CampaignConfigError, match="Hub1.*Hub2.*Hub3"):
            operation()
        assert select_group_members(["Hub"], inventory) == ["Hub2", "Hub3"]
        with pytest.warns(PyflightstreamWarning, match="Hub1"):
            assert operation(strict=False) == []

    @staticmethod
    @pytest.mark.parametrize("route", ["group", "family-list", "alias", "nested-alias"])
    @pytest.mark.parametrize("strict", [True, False])
    def test_p0400_numbered_member_exact(route, strict):
        """P0400-SWEEP-BOUNDARY-EXACT: a numbered MEMBER selects its exact name, never refused.

        The decision of 2026-10-12 on PFS-2029.25: a member of a list, a group or
        an alias the geometry lacks is left to the FR-320 warning and the FR-435
        rule, and it never selects its numbered siblings.
        """
        inventory = ["Hub2", "Hub3", "MainWing"]
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            if route == "group":
                found = select_group_members(["Hub1", "MainWing"], inventory, strict=strict)
            elif route == "family-list":
                found = select_families(
                    ["Hub1", "MainWing"], inventory, lambda name: False, strict=strict
                )
            elif route == "alias":
                found = resolve_alias("hubs", inventory, {"hubs": ["Hub1", "MainWing"]})
            else:
                found = select_families(
                    "outer",
                    inventory,
                    lambda name: False,
                    {"outer": ["hubs"], "hubs": ["Hub1"]},
                    strict=strict,
                )
        expected = {"family-list": [["MainWing"]], "nested-alias": []}
        assert found == expected.get(route, ["MainWing"])

    @staticmethod
    @pytest.mark.parametrize("number", [1, 2, 3, 4, 5])
    def test_p0400_rbf_numeric_vocabulary(number):
        """P0400-SWEEP-RBF-VOCABULARY: the documented numeric options are accepted."""
        script = Script("26.124")
        script.emit("AEROELASTIC_RBF_TYPE", number)
        assert f"AEROELASTIC_RBF_TYPE {number}" in script.render()

    @staticmethod
    def test_p0400_animation_missing_anchor():
        """P0400-SWEEP-JOIN-ANCHOR: a joined value cannot attach to another keyword."""
        script = Script("26.124")
        with pytest.raises(CommandArgumentError, match="volume_sections"):
            script.emit(
                "UNSTEADY_SOLVER_ANIMATION", "ENABLE", frequency=2, volume_sections_format="VTK"
            )
        script.emit(
            "UNSTEADY_SOLVER_ANIMATION",
            "ENABLE",
            volume_sections="ENABLE",
            volume_sections_format="VTK",
        )
        assert "VOLUME_SECTIONS ENABLE VTK" in script.render()

    @staticmethod
    def test_p0400_matrix_selection_preserves_order(tmp_path, monkeypatch):
        """P0400-SWEEP-ALIAS-PLAN: matrix planning retains the full sweep's alias order."""
        from pyflightstream.run._alias import planned_in_workspace
        from pyflightstream.run._cli_print import _alias_block
        from tests.tier1_offline.test_p0340_run_usability import _names, _two_simulations

        workspace, matrix, _ = _two_simulations(tmp_path, monkeypatch)
        names = _names(workspace, matrix, "5002")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", PyflightstreamWarning)
            plan = plan_matrix(
                matrix,
                workspace,
                name="warm",
                fs_version="26.120",
                recipes={},
                sims=["5002"],
                points=[names[2]],
                ignore_missing_families=True,
            )
        assert _alias_block(plan, []) == [f"  5002_3  POL 5002 {names[2]}"]
        assert planned_in_workspace(workspace.root, [])["5002"] == names
        saved = json.loads(
            (workspace.plan_dir(matrix.stem) / "plan.json").read_text(encoding="utf-8")
        )
        assert [point["run_id"].rsplit("/", 1)[-1] for point in saved["points"]] == [names[2]]


class TestSweep1Routes:
    """Cross-file command routes and receipts for sweep-1."""

    @staticmethod
    @pytest.mark.parametrize("command", ["SOLVER_SET_AOA", "SOLVER_SET_SIDESLIP"])
    @pytest.mark.parametrize("before", [True, False])
    @pytest.mark.parametrize(
        "version",
        [
            "25.000",
            "25.100",
            "26.000",
            "26.100",
            "26.101",
            "26.120",
            "26.121",
            "26.122",
            "26.123",
            "26.124",
            "26.125",
        ],
    )
    def test_p0400_periodic_incidence_refused(command, before, version):
        """P0400-SWEEP-PERIODIC-INCIDENCE: refuse both command orders before writing."""
        script = Script(version)
        if before:
            script.emit(command, 5)
        with pytest.raises(CommandArgumentError, match="PERIODIC.*nonzero"):
            if version == "25.000":
                script.emit(
                    "INITIALIZE_SOLVER",
                    surfaces=-1,
                    wake_termination_x="DEFAULT",
                    symmetry_type="PERIODIC",
                    symmetry_periodicity=6,
                    load_frame=1,
                    proximity_avoidance="DISABLE",
                    stabilization="DISABLE",
                    stabilization_strength=0.0,
                    fast_multipole="ENABLE",
                )
            else:
                helpers.initialize_solver(script, symmetry="PERIODIC", periodic_copies=6)
            script.emit(command, 5)

    @staticmethod
    def test_p0400_old_initialization_ledgers():
        """P0400-SWEEP-OLD-INIT: the 25.000 names populate copies and loads frame."""
        script = Script("25.000")
        script.declare_existing(frames=1)
        script.emit(
            "INITIALIZE_SOLVER",
            surfaces=-1,
            wake_termination_x="DEFAULT",
            symmetry_type="PERIODIC",
            symmetry_periodicity=6,
            load_frame=2,
            proximity_avoidance="DISABLE",
            stabilization="DISABLE",
            stabilization_strength=0.0,
            fast_multipole="ENABLE",
        )
        assert script.periodic_copies == 6
        assert script.loads_frame_record()["frame"] == 2
        assert script.sets_loads_frame

    @staticmethod
    def test_p0400_26125_auto_uses_inventory():
        """P0400-SWEEP-TRAILING-COUNT: automatic detection names the known boundaries."""
        script = Script("26.125")
        script.declare_existing(boundaries=2)
        helpers.detect_every_boundary(script, "trailing_edges")
        assert "SURFACES 2\n1,2" in script.render()
        unknown = Script("26.125")
        with pytest.raises(CommandArgumentError, match="boundar"):
            helpers.detect_every_boundary(unknown, "trailing_edges")

    @staticmethod
    def test_p0400_probe_wing_counts_trailing_edges(tmp_path):
        """P0400-SWEEP-PROBE-TRAILING-COUNT: the synthetic wing declares one surface."""
        from pyflightstream.qa._spec_0400_gapkit import _units_and_edges

        script = Script("26.125")
        _units_and_edges(script, tmp_path)
        assert "SURFACES 1\n1" in script.render()

    @staticmethod
    def test_p0400_native_log_validation(tmp_path):
        """P0400-SWEEP-NATIVE-LOG: profile reading refuses an unknown placeholder."""
        path = tmp_path / "h001.toml"
        path.write_text(
            'application_id = "solver"\n[descriptor.fields]\nscript = "{script_path}"\n'
            '[submit]\ncommand = ["submit", "{descriptor_path}"]\n[log]\n'
            'native_log = "FTS{typo}.l*"\n',
            encoding="utf-8",
        )
        with pytest.raises(InputArtifactError, match="typo"):
            read_hpc_profile(path)

    @staticmethod
    def test_p0400_one_grouping_reader(tmp_path, monkeypatch):
        """P0400-SWEEP-GROUPING-READER: run and rebuild share the validated reader."""
        import pyflightstream.workspace._batches as batches

        reader = getattr(batches, "read_grouping", None)
        assert callable(reader), "grouping needs a shared workspace reader"
        calls = []
        monkeypatch.setattr(
            batches, "read_grouping", lambda path: (calls.append(path) or None, "unreadable")
        )
        workspace = CampaignWorkspace(tmp_path)
        assert _grouped._read_grouping(workspace, "warm") == (None, "unreadable")
        assert _rebuild_grouped._receipt(tmp_path, "warm") is None
        assert calls == [workspace.plan_dir("warm") / "plan.json"] * 2

    @staticmethod
    def test_p0400_submission_predicate():
        """P0400-SWEEP-SUBMITS: a grouped local wrapper is judged as running here."""

        class LocalWrapper:
            submits = False

            def bind_point(self, values, *, replace=False):
                pass

            def submission_record(self):
                return None

        predicate = getattr(_executors, "submits_jobs", None)
        assert callable(predicate), "one predicate must govern submission"
        assert not predicate(LocalWrapper())
        wrapper = LocalWrapper()
        wrapper.submits = True
        assert predicate(wrapper)

    @staticmethod
    def test_p0400_26125_pressure_reference(tmp_path):
        """P0400-SWEEP-CDP-REFERENCE: CDp has its own specs and reference, never CDi."""
        run = dataclasses.replace(
            _sweep_1_routes___run(_sweep_1_routes___points(drag="CDp")), version="26.125"
        )
        report, _ = write_physics_report(run, tmp_path, date="2026-10-12")
        try:
            destination = update_reference(
                "PHY-01",
                report,
                reason="synthetic seeding",
                references_dir=tmp_path / "refs",
                repo_root=tmp_path,
                date="2026-10-12",
            )
        except ValueError as error:
            pytest.fail(str(error))
        data = yaml.safe_load(destination.read_text(encoding="utf-8"))
        assert "CDp_a4" in data["metrics"] and "CDi_a4" not in data["metrics"]
        assert "pressure drag" in PHYSICS_CASES["PHY-01"].specs_by_name["CDp_a4"].description
        assert load_reference("PHY-01", tmp_path / "refs") is None
        pressure = load_reference("PHY-01", tmp_path / "refs", fs_version="26.125")
        assert pressure is not None and "CDp_a4" in pressure.metrics

    @staticmethod
    @pytest.mark.parametrize(
        "case_id,names",
        [
            ("PHY-01", {"CDp_a4"}),
            ("PHY-02", {"delta_CDp_a4"}),
            ("PHY-05", {"CDp", "CDv"}),
            ("SMI-01", {"CDp", "CDv"}),
            ("SMI-02", {"CDp", "CDv"}),
        ],
    )
    def test_p0400_pressure_specs_are_separate(case_id, names):
        """P0400-SWEEP-PRESSURE-SPECS: each case declares its own pressure drag bands."""
        from pyflightstream.qa.physics import SMI_CASES

        case = {**PHYSICS_CASES, **SMI_CASES}[case_id]
        assert {spec.name for spec in case.pressure_metric_specs} == names
        selected = case.specs_for_version("26.125")
        assert names <= selected.keys()
        assert all("CDi" not in name and "CDo" not in name for name in selected)
        assert not names.intersection(case.specs_for_version("26.124"))

    @staticmethod
    def test_p0400_pressure_reference_is_packaged():
        """P0400-SWEEP-CDP-PACKAGING: independent reference files enter the wheel."""
        import tomllib
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        with (root / "pyproject.toml").open("rb") as stream:
            project = tomllib.load(stream)
        assert (
            "references/pressure-drag/*.yaml"
            in project["tool"]["setuptools"]["package-data"]["pyflightstream.qa"]
        )

    @staticmethod
    def test_p0400_probe_units_required():
        """P0400-SWEEP-PROBE-UNITS: coordinates cannot acquire an implicit METER token."""
        from pyflightstream.probes import emit_probe_import

        assert (
            inspect.signature(emit_probe_import).parameters["units"].default
            is inspect.Parameter.empty
        )

    @staticmethod
    def test_p0400_refine_help_keyword():
        """P0400-SWEEP-REFINE-HELP: help names the Python out_dir keyword."""
        from pyflightstream.run._cli_parsers import _build_parser

        parser = _build_parser()
        refine = next(
            action
            for action in parser._actions
            if hasattr(action, "choices") and isinstance(action.choices, dict)
        ).choices["refine"]
        assert "out_dir" in refine.format_help()


def _geometry_group___options(run, argv: list[str], capsys) -> set[str]:
    """Return the options a command's --help lists."""
    with pytest.raises(SystemExit):
        run([*argv, "--help"])
    return set(re.findall(r"(?<![\w-])--[a-z][a-z-]*", capsys.readouterr().out))


class TestGeometryGroup:
    """Tier 1, 0.40.0: the geometry verbs of pyfs-matrix join pyfs-workspace geometry (FR-477).

    P0400-GEOM-GROUP (PFS-2081.41). The group's refine, audit, inventory and
    degenerate are the pyfs-matrix parsers and handlers; the pyfs-matrix names
    stay as aliases with the identical result and one warning.
    """

    @staticmethod
    @pytest.mark.requirement("FR-477")
    @pytest.mark.parametrize(("name", "verb"), sorted(_cli_geometry.PYFS_MATRIX_ALIASES.items()))
    def test_p0400_geom_group_each_verb_takes_the_options_of_its_pyfs_matrix_name(
        name, verb, capsys
    ):
        """P0400-GEOM-GROUP (PFS-2081.41): the group copies each pyfs-matrix parser."""
        ours = _geometry_group___options(workspace_cli.main, ["geometry", name], capsys)
        theirs = _geometry_group___options(matrix_main, [verb], capsys)
        assert ours == theirs and ours, (ours, theirs)
        assert set(_cli_geometry.matrix_parsers()) == set(
            _cli_geometry.PYFS_MATRIX_ALIASES.values()
        )

    @staticmethod
    @pytest.mark.requirement("FR-477")
    def test_p0400_geom_group_audit_gives_the_result_of_audit_mesh(tmp_path, monkeypatch, capsys):
        """P0400-GEOM-GROUP (PFS-2081.41): R1, the same audit, the alias warned once."""
        mesh = _geometry_build__wing_obj(tmp_path / "wing.obj")
        monkeypatch.chdir(tmp_path)
        assert workspace_cli.main(["geometry", "audit", str(mesh)]) == 0
        ours = (tmp_path / "wing.audit.json").read_text(encoding="utf-8")
        (tmp_path / "wing.audit.json").unlink()
        with pytest.warns(PyflightstreamWarning, match="alias of `pyfs-workspace geometry audit`"):
            assert matrix_main(["audit-mesh", str(mesh)]) == 0
        assert (tmp_path / "wing.audit.json").read_text(encoding="utf-8") == ours

    @staticmethod
    @pytest.mark.requirement("FR-477")
    def test_p0400_geom_group_inventory_writes_what_pyfs_matrix_inventory_writes(
        tmp_path, monkeypatch
    ):
        """P0400-GEOM-GROUP (PFS-2081.41): the inventory of an OBJ, through both names."""
        mesh = _geometry_build__wing_obj(tmp_path / "wing.obj")
        monkeypatch.chdir(tmp_path)
        assert workspace_cli.main(["geometry", "inventory", str(mesh)]) == 0
        ours = (tmp_path / "wing.boundaries.toml").read_text(encoding="utf-8")
        (tmp_path / "wing.boundaries.toml").unlink()
        with pytest.warns(PyflightstreamWarning, match="pyfs-matrix inventory is an alias"):
            assert matrix_main(["inventory", str(mesh)]) == 0
        assert (tmp_path / "wing.boundaries.toml").read_text(encoding="utf-8") == ours


def _geometry_migration___warnings(geometry, mesh_import=None) -> list[str]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        judge_the_row_geometry(geometry, "7001", fs_build="26.124", mesh_import=mesh_import)
    return [
        str(item.message) for item in caught if issubclass(item.category, PyflightstreamWarning)
    ]


class TestGeometryMigration:
    """Tier 1, 0.40.0: the in-row routes warn, and the converter writes the instruction (FR-476).

    P0400-GEOM-MIGRATE (PFS-2081.41). Option A of the geometry stage: a row naming
    a CCS, IGES or STL file, or a sidecar that scales, renames or mirrors, still
    plans and runs as in 0.39.0, with a warning naming the exact replacement; the
    converter writes the instruction that builds the same body.
    """

    @staticmethod
    @pytest.mark.requirement("FR-476")
    @pytest.mark.parametrize(
        ("name", "built"),
        [("wing.csv", "wing.fsm"), ("rig.igs", "rig.fsm"), ("hull.stl", "hull.obj")],
    )
    def test_p0400_geom_migrate_an_in_row_source_warns_with_the_replacement(tmp_path, name, built):
        """P0400-GEOM-MIGRATE (PFS-2081.41): R1, the converter, the build and the cell, and 0.41.0."""  # noqa: E501
        folder = tmp_path / "inputs" / "geometries" / name.split(".")[0]
        folder.mkdir(parents=True)
        geometry = folder / name
        geometry.write_text("x\n", encoding="utf-8")
        (texts,) = _geometry_migration___warnings(geometry)
        assert "POL 7001" in texts and "0.41.0 refuses" in texts
        assert f"pyfs-workspace geometry from-sidecar {name} --apply" in texts
        assert f"pyfs-workspace geometry build {folder.name} --apply" in texts
        assert f"name {built} in the GEOMETRY cell" in texts

    @staticmethod
    @pytest.mark.requirement("FR-476")
    def test_p0400_geom_migrate_sidecar_operations_warn_and_translate_does_not(tmp_path):
        """P0400-GEOM-MIGRATE (PFS-2081.41): R1, scale, rename and mirror move; translate stays."""
        geometry = tmp_path / "blade.obj"
        geometry.write_text("x\n", encoding="utf-8")
        moving = MeshImport(
            units="METER", operations=(MeshOperation(op="scale", factors=(2.0, 2.0, 2.0)),)
        )
        staying = MeshImport(
            units="METER", operations=(MeshOperation(op="translate", vector=(1.0, 0.0, 0.0)),)
        )
        assert any(
            "operations scale" in text for text in _geometry_migration___warnings(geometry, moving)
        )
        assert _geometry_migration___warnings(geometry, staying) == []
        assert _geometry_migration___warnings(tmp_path / "plain.fsm") == []

    @staticmethod
    @pytest.mark.requirement("FR-476")
    def test_p0400_geom_migrate_the_plan_of_a_ccs_row_warns_and_still_binds(tmp_path):
        """P0400-GEOM-MIGRATE (PFS-2081.41): R1, through the plan's binding."""
        from tests.tier1_offline.test_p0320_ccs import THREE, _row_case

        with pytest.warns(PyflightstreamWarning, match="0.41.0 refuses"):
            case = _row_case(tmp_path, "wing", 'kind = "wing"\ncomponent = 1\n', ["W1"], text=THREE)
        assert case.mesh_import is not None and case.mesh_import.ccs is not None

    @staticmethod
    @pytest.mark.requirement("FR-476")
    def test_p0400_geom_migrate_the_converter_writes_an_instruction_that_reads(
        tmp_path, monkeypatch, capsys
    ):
        """P0400-GEOM-MIGRATE (PFS-2081.41): R2, a raw mesh with a rename, a scale and a translate."""  # noqa: E501
        root = _geometry_build__workspace(tmp_path)
        folder = root / "inputs" / "geometries" / "blade"
        folder.mkdir()
        _geometry_build__wing_obj(folder / "blade.obj", group="naca")
        (folder / "blade.boundaries.toml").write_text(
            'boundaries = ["naca"]\n[import]\nunits = "METER"\n'
            '[[import.operations]]\nop = "rename"\nsurface = "naca"\nto = "Wing"\n'
            '[[import.operations]]\nop = "scale"\nfactors = [2.0, 2.0, 2.0]\n'
            '[[import.operations]]\nop = "translate"\nvector = [1.0, 0.0, 0.0]\n'
            '[trailing_edges]\ndetect = "auto"\n',
            encoding="utf-8",
        )
        monkeypatch.chdir(root)
        assert main(["geometry", "from-sidecar", "blade.obj", "--build", "26.125"]) == 0
        assert not (folder / "blade.geometry.toml").exists()
        assert main(["geometry", "from-sidecar", "blade.obj", "--build", "26.125", "--apply"]) == 0
        out = capsys.readouterr().out
        assert "operation 3 (translate) stay in the run" in out
        assert "name blade_ops.obj in the GEOMETRY cell" in out
        instruction = read_geometry_instruction(folder / "blade.geometry.toml")
        assert instruction.boundaries == ("Wing",)
        assert [op.op for op in instruction.operations] == ["rename", "scale"]
        assert instruction.fs_build == "26.125"
        assert main(["geometry", "from-sidecar", "blade.obj", "--apply"]) == 2

    @staticmethod
    @pytest.mark.requirement("FR-476")
    def test_p0400_geom_migrate_the_converter_reads_a_ccs_sidecar(tmp_path, monkeypatch):
        """P0400-GEOM-MIGRATE (PFS-2081.41): R2, [import.ccs] becomes [ccs]."""
        root = _geometry_build__workspace(tmp_path)
        folder = root / "inputs" / "geometries" / "wing"
        folder.mkdir()
        (folder / "wing.csv").write_text(_geometry_instruction__ccs_text(), encoding="utf-8")
        (folder / "wing.boundaries.toml").write_text(
            'boundaries = ["WING"]\n[import]\nunits = "METER"\n[import.ccs]\nkind = "wing"\n'
            "component = 1\n\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(root)
        assert main(["geometry", "from-sidecar", "wing.csv", "--build", "26.125", "--apply"]) == 0
        instruction = read_geometry_instruction(folder / "wing.geometry.toml")
        assert instruction.kind == "ccs" and instruction.ccs is not None
        assert instruction.ccs.options.component == 1

    @staticmethod
    def test_p0400_geom_migrate_the_converter_refuses_a_flat_geometry(tmp_path):
        """P0400-GEOM-MIGRATE (PFS-2081.41): R2, a flat library is migrated first."""
        from pyflightstream.workspace._geometry_convert import instruction_from_sidecar

        root = _geometry_build__workspace(tmp_path)
        (root / "inputs" / "geometries" / "flat.stl").write_text("solid x\n", encoding="utf-8")
        with pytest.raises(InputArtifactError, match="migrate-geometries"):
            instruction_from_sidecar("flat.stl", root=root)


_GEOMETRY_PLAN__INSTRUCTION = _GEOMETRY_BUILD__MESH_INSTRUCTION.replace(
    'outputs = ["fsm", "obj"]', 'outputs = ["fsm"]'
)


def _geometry_plan___judge(fsm: Path, fs_build: str = "26.125") -> list[str]:
    with pytest.warns() as caught:
        judge_the_row_geometry(fsm, "9401", fs_build=fs_build, mesh_import=None)
        import warnings

        warnings.warn("control", PyflightstreamWarning, stacklevel=1)
    return [str(item.message) for item in caught if str(item.message) != "control"]


class TestGeometryPlan:
    """Tier 1, 0.40.0: a built body is accepted, and the plan reads its record (FR-473).

    P0400-GEOM-PLAN (PFS-2081.41). The body is built through the build's own
    code with a runner standing in for the solver; the plan's judgement is the
    function the matrix binding calls for every geometry a row names, and one test
    drives it through ``resolve_matrix`` to show the binding reaches it.
    """

    @staticmethod
    @pytest.fixture
    def built(tmp_path):
        """A built, unaccepted wing: (root, folder, the built FSM)."""
        root = _geometry_build__workspace(tmp_path)
        folder = _geometry_build__geometry(root, "wing", _GEOMETRY_PLAN__INSTRUCTION)
        plan = plan_geometry_build(folder, registry=_geometry_build__verified_registry())
        apply_geometry_build(plan, runner=_geometry_build__runner())
        return root, folder, folder / "wing.fsm"

    @staticmethod
    @pytest.mark.requirement("FR-473")
    def test_p0400_geom_plan_an_unaccepted_body_is_warned_until_accepted(
        built, monkeypatch, capsys
    ):
        """P0400-GEOM-PLAN (PFS-2081.41): R1 and R3, accept silences the warning."""
        root, folder, fsm = built
        assert any(
            "never accepted" in text and "geometry accept wing" in text
            for text in _geometry_plan___judge(fsm)
        )
        monkeypatch.chdir(root)
        assert main(["geometry", "accept", "wing"]) == 0
        record = json.loads((folder / "wing.build.json").read_text(encoding="utf-8"))
        assert record["inspected"]["at"] and record["inspected"]["by"]
        assert _geometry_plan___judge(fsm) == []

    @staticmethod
    @pytest.mark.requirement("FR-473")
    def test_p0400_geom_plan_accept_refuses_a_geometry_never_built(built, monkeypatch, capsys):
        """P0400-GEOM-PLAN (PFS-2081.41): R1, a name with no record, exit 2."""
        root, _, _ = built
        monkeypatch.chdir(root)
        assert main(["geometry", "accept", "nothing"]) == 2
        assert "Nothing was written" in capsys.readouterr().err

    @staticmethod
    @pytest.mark.requirement("FR-473")
    @pytest.mark.parametrize("changed", ["wing.geometry.toml", "src.obj"])
    def test_p0400_geom_plan_refuses_a_body_whose_inputs_changed(built, changed):
        """P0400-GEOM-PLAN (PFS-2081.41): R2, the instruction or the source edited after the build."""  # noqa: E501
        _, folder, fsm = built
        with (folder / changed).open("a", encoding="utf-8") as handle:
            handle.write("\n# edited\n")
        with pytest.raises(
            InputArtifactError,
            match=f"{changed}.*Rebuild it with `pyfs-workspace geometry build wing",
        ):
            judge_the_row_geometry(fsm, "9401", fs_build="26.125", mesh_import=None)

    @staticmethod
    @pytest.mark.requirement("FR-473")
    def test_p0400_geom_plan_warns_on_a_resaved_body_a_failed_audit_and_another_build(built):
        """P0400-GEOM-PLAN (PFS-2081.41): R3, each warning names the row and the geometry."""
        _, folder, fsm = built
        record_path = folder / "wing.build.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["inspected"] = {"at": "now", "by": "tester"}
        record["audit"] = {
            "file": "wing.audit.json",
            "passed": False,
            "failed": ["G1 faces_of_zero_area"],
        }
        record_path.write_text(json.dumps(record), encoding="utf-8")
        with fsm.open("a", encoding="utf-8") as handle:
            handle.write("\n")
        texts = _geometry_plan___judge(fsm, fs_build="26.124")
        assert any("saved again" in text for text in texts)
        assert any("audit failed: G1 faces_of_zero_area" in text for text in texts)
        assert any("built on FS_BUILD 26.125" in text and "26.124" in text for text in texts)
        assert all("POL 9401" in text for text in texts)

    @staticmethod
    @pytest.mark.requirement("FR-473")
    def test_p0400_geom_plan_a_body_without_a_record_is_planned_as_before(tmp_path):
        """P0400-GEOM-PLAN (PFS-2081.41): R4, nothing is said of a GUI-saved simulation."""
        import warnings

        fsm = tmp_path / "gui.fsm"
        fsm.write_text("saved\n", encoding="utf-8")
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            judge_the_row_geometry(fsm, "1", fs_build="26.125", mesh_import=None)

    @staticmethod
    @pytest.mark.requirement("FR-473")
    def test_p0400_geom_plan_the_matrix_binding_reaches_the_judgement(built):
        """P0400-GEOM-PLAN (PFS-2081.41): the binding refuses a stale body."""
        from pyflightstream.workspace.matrix import resolve_matrix
        from tests.tier1_offline.test_matrix_run import RECIPES, make_library, write_matrix

        root, folder, fsm = built
        workspace_ = make_library(
            root.parent / "lib", register_build=("26.125", Path(sys.executable).as_posix())
        )
        target = workspace_.inputs_dir / "geometries" / "wing"
        import shutil

        shutil.copytree(folder, target)
        (target / "src.obj").write_text("changed\n", encoding="utf-8")
        row = (
            "9401 | TestGeom | GEOM | 3.10 | 0.0890 | AL | 0.0 | r003 | s002 | e001 "
            "| 003 | 26.125 |  0 | 1 | OUTPUTS: loads_{point}.txt / VELOCITY: 30.0 / GEOMETRY: wing.fsm"  # noqa: E501
        )
        matrix = write_matrix(root.parent / "m.fs", [row])
        with pytest.raises(InputArtifactError, match="src.obj"):
            resolve_matrix(matrix, workspace_, name="matrix", fs_version="26.125", recipes=RECIPES)


_GEOMETRY_SWEEP__SWEEP = (
    _GEOMETRY_INSTRUCTION__CCS_WING
    + '[sweep]\ncontrol_surface = "AIL"\nangle_deg = [-10.0, 0.0, 10.0]\n'
)


def _geometry_sweep___wing(tmp_path, text=_GEOMETRY_SWEEP__SWEEP):
    root = _geometry_build__workspace(tmp_path)
    folder = _geometry_build__geometry(root, "wing", text, source=None)
    (folder / "wing_sections.csv").write_text(_geometry_instruction__ccs_text(), encoding="utf-8")
    return root, folder


def _geometry_sweep___surface_angle(script_text: str) -> float:
    line = next(
        line for line in script_text.splitlines() if line.startswith("NEW_CCS_WING_CONTROL_SURFACE")
    )
    return float(line.split()[7])


class TestGeometrySweep:
    """Tier 1, 0.40.0: a deflection sweep builds one sibling geometry per angle (FR-472).

    P0400-GEOM-SWEEP (PFS-2081.41). Run from ``inputs/geometries/``, one
    instruction with a ``[sweep]`` renders one script per angle, each lofting the
    wing with its control surface at that angle, into ``<name>_<SURFACE><sign><ttt>``.
    """

    @staticmethod
    @pytest.mark.requirement("FR-472")
    def test_p0400_geom_sweep_one_script_per_angle_into_sibling_folders(tmp_path):
        """P0400-GEOM-SWEEP (PFS-2081.41): the tags, the folders and each script's angle."""
        root, folder = _geometry_sweep___wing(tmp_path)
        plan = plan_geometry_build("wing", cwd=folder.parent)
        assert [v.tag for v in plan.variants] == ["AIL-100", "AIL+000", "AIL+100"]
        assert [v.folder.name for v in plan.variants] == [
            "wing_AIL-100",
            "wing_AIL+000",
            "wing_AIL+100",
        ]
        assert all(v.folder.parent == folder.parent for v in plan.variants)
        assert [_geometry_sweep___surface_angle(v.script.text) for v in plan.variants] == [
            -10.0,
            0.0,
            10.0,
        ]
        assert all(v.instruction.sweep is None for v in plan.variants)

    @staticmethod
    @pytest.mark.requirement("FR-472")
    def test_p0400_geom_sweep_only_builds_the_named_variants(tmp_path):
        """P0400-GEOM-SWEEP (PFS-2081.41): R2, --only, and an unknown tag is refused."""
        _, folder = _geometry_sweep___wing(tmp_path)
        plan = plan_geometry_build("wing", cwd=folder.parent, only=("AIL+100",))
        assert [v.tag for v in plan.variants] == ["AIL+100"]
        with pytest.raises(InputArtifactError, match="AIL\\+200"):
            plan_geometry_build("wing", cwd=folder.parent, only=("AIL+200",))

    @staticmethod
    @pytest.mark.requirement("FR-472")
    def test_p0400_geom_sweep_from_inside_its_folder_is_refused(tmp_path):
        """P0400-GEOM-SWEEP (PFS-2081.41): R4, the variants never live inside the base folder."""
        _, folder = _geometry_sweep___wing(tmp_path)
        with pytest.raises(InputArtifactError, match="level above"):
            plan_geometry_build(None, cwd=folder)

    @staticmethod
    @pytest.mark.requirement("FR-472")
    @pytest.mark.parametrize(
        "angles",
        ["[]", "[1.0, 1.0]", "[1.0, 1.04]"],
        ids=["empty", "repeated", "one-tag"],
    )
    def test_p0400_geom_sweep_values_that_cannot_name_their_folders_are_refused(tmp_path, angles):
        """P0400-GEOM-SWEEP (PFS-2081.41): R4, an empty list or two values with one tag."""
        text = (
            _GEOMETRY_INSTRUCTION__CCS_WING
            + f'[sweep]\ncontrol_surface = "AIL"\nangle_deg = {angles}\n'
        )
        _, folder = _geometry_sweep___wing(tmp_path, text)
        with pytest.raises(InputArtifactError, match="angle_deg|tag"):
            plan_geometry_build("wing", cwd=folder.parent)

    @staticmethod
    @pytest.mark.requirement("FR-472")
    def test_p0400_geom_sweep_refuses_a_foreign_folder_of_a_variant_name(tmp_path):
        """P0400-GEOM-SWEEP (PFS-2081.41): R4, a foreign folder, even with --overwrite."""
        from pyflightstream.workspace._geometry_build import refuse_before_running
        from tests.tier1_offline.test_regression_geometry_build_sweep import (
            _geometry_build__verified_registry as verified_registry,
        )

        _, folder = _geometry_sweep___wing(tmp_path)
        plan = plan_geometry_build("wing", cwd=folder.parent, registry=verified_registry())
        refuse_before_running(plan, overwrite=True, png=False)
        (folder.parent / "wing_AIL+100").mkdir()
        with pytest.raises(
            InputArtifactError, match="AIL\\+100.*was not built from this instruction"
        ):
            refuse_before_running(plan, overwrite=True, png=False)

    @staticmethod
    @pytest.mark.requirement("FR-472")
    def test_p0400_geom_sweep_prints_the_matrix_cells_of_each_variant(
        tmp_path, monkeypatch, capsys
    ):
        """P0400-GEOM-SWEEP (PFS-2081.41): R3, the CONFIGURATION and GEOMETRY cells."""
        _, folder = _geometry_sweep___wing(tmp_path)
        monkeypatch.chdir(folder.parent)
        assert main(["geometry", "build", "wing"]) == 0
        out = capsys.readouterr().out
        assert "CONFIGURATION AIL-100 | GEOMETRY wing_AIL-100.fsm" in out


def _rfixb_geometry___plan(tmp_path):
    root = _geometry_build__workspace(tmp_path)
    folder = _geometry_build__geometry(root, "wing", _GEOMETRY_BUILD__MESH_INSTRUCTION)
    return build.plan_geometry_build(
        None, cwd=folder, registry=_geometry_build__verified_registry()
    )


class TestRfixBGeometry:
    """Build previews name real outputs and builds preserve folders they do not own."""

    @staticmethod
    @pytest.mark.requirement("FR-472")
    def test_p0400_rfixb_obj_preview_names_an_obj(tmp_path, capsys):
        """P0400-RFIXB-PREVIEW: an OBJ-only sweep never advertises an FSM cell."""
        _, folder = _geometry_complete___sweep(tmp_path)
        path = folder / "wing.geometry.toml"
        path.write_text('outputs = ["obj"]\n' + path.read_text(), encoding="utf-8")
        plan = build.plan_geometry_build("wing", cwd=folder.parent)
        _print_plan(plan)
        cells = [line for line in capsys.readouterr().out.splitlines() if "matrix cells:" in line]
        assert len(cells) == 3
        assert all(line.endswith(".obj") for line in cells)

    @staticmethod
    @pytest.mark.requirement("FR-471")
    @pytest.mark.parametrize("suffix", [".partial", "_obj"])
    def test_p0400_rfixb_foreign_build_destinations_survive(tmp_path, suffix):
        """P0400-RFIXB-OWNERSHIP: refusal precedes the runner, with all foreign bytes intact."""
        plan = _rfixb_geometry___plan(tmp_path)
        target = plan.path.parent.with_name("wing" + suffix)
        target.mkdir()
        sentinel = target / "irreplaceable.txt"
        sentinel.write_bytes(b"foreign evidence")
        calls = []

        def run(script, work):
            calls.append(work)
            return _geometry_build__runner()(script, work)

        with pytest.raises(InputArtifactError, match="ownership"):
            build.apply_geometry_build(plan, runner=run, overwrite=True)
        assert calls == []
        assert sentinel.read_bytes() == b"foreign evidence"

    @staticmethod
    @pytest.mark.requirement("FR-471")
    def test_p0400_rfixb_owned_partial_evidence_is_archived_and_sibling_files_kept(tmp_path):
        """P0400-RFIXB-OWNERSHIP: a retry archives the first log; overwrite keeps unrelated files."""  # noqa: E501
        plan = _rfixb_geometry___plan(tmp_path)
        with pytest.raises(build.GeometryBuildError):
            build.apply_geometry_build(plan, runner=_geometry_build__runner(fail=True))
        work = Path(plan.variants[0].script.fsm).parent
        first_log = (work / "wing.build.log").read_bytes()
        build.apply_geometry_build(plan, runner=_geometry_build__runner())
        assert (
            work.with_name(work.name + ".previous") / "wing.build.log"
        ).read_bytes() == first_log
        sibling = plan.path.parent.with_name("wing_obj")
        sentinel = sibling / "notes.txt"
        sentinel.write_bytes(b"keep")
        build.apply_geometry_build(plan, runner=_geometry_build__runner(), overwrite=True)
        assert sentinel.read_bytes() == b"keep"

    @staticmethod
    @pytest.mark.requirement("FR-472")
    def test_p0400_rfixb_parallel_calls_overlap_and_retry_runs_alone(tmp_path, monkeypatch):
        """P0400-RFIXB-PARALLEL: bounded barrier measures actual overlap and retry isolation."""
        _, folder = _geometry_complete___sweep(tmp_path)
        plan = build.plan_geometry_build(
            "wing", cwd=folder.parent, registry=_geometry_build__verified_registry()
        )
        monkeypatch.setattr(build, "_room_for_a_second_run", lambda: True)
        barrier = threading.Barrier(2, timeout=5)
        lock = threading.Lock()
        calls = Counter()
        active = 0
        maximum = 0
        overlap = []
        retry_active = []
        stand_in = _geometry_complete___body_runner(fail_once="Base-100")

        def run(script, work):
            nonlocal active, maximum
            name = script.stem
            with lock:
                calls[name] += 1
                attempt = calls[name]
                active += 1
                maximum = max(maximum, active)
                if attempt == 2:
                    retry_active.append(active)
            try:
                if attempt == 1 and not name.endswith("Base+100.build"):
                    try:
                        barrier.wait()
                        with lock:
                            overlap.append(active)
                        barrier.wait()
                    except threading.BrokenBarrierError:
                        pytest.fail("two initial solver calls did not overlap within five seconds")
                return stand_in(script, work)
            finally:
                with lock:
                    active -= 1

        built = build.apply_geometry_build(plan, runner=run, parallel=2)
        assert len(built) == 3
        assert maximum == 2 and overlap == [2, 2]
        assert retry_active == [1]
        assert calls == {
            "wing_Base-100.build": 2,
            "wing_Base+000.build": 1,
            "wing_Base+100.build": 1,
        }


class TestRfixGAudit:
    """A sliver build must remain inspectable in partial storage, without promotion."""

    pytestmark = pytest.mark.requirement("P0400-RFIXG-AUDIT")

    @staticmethod
    @pytest.mark.requirement("FR-471")
    @pytest.mark.parametrize("overwrite", [False, True])
    def test_p0400_rfixg_failed_audit_retains_outputs(tmp_path: Path, overwrite: bool) -> None:
        root = _geometry_build__workspace(tmp_path)
        folder = _geometry_build__geometry(root, "wing", _GEOMETRY_BUILD__MESH_INSTRUCTION)
        plan = plan_geometry_build(folder, registry=_geometry_build__verified_registry())
        if overwrite:
            apply_geometry_build(plan, runner=_geometry_build__runner())
        mesh = folder.with_name("wing_obj")
        before = {
            p: p.read_bytes() for base in (folder, mesh) if base.exists() for p in base.iterdir()
        }
        (built,) = apply_geometry_build(
            plan, runner=_geometry_build__runner(sliver=True), overwrite=overwrite
        )
        partial = folder.with_name("wing.partial")
        assert built.folder == partial
        assert built.record == partial / "wing.build.json"
        assert not built.passed and any(g.startswith("G1") for g in built.failed_gates)
        assert {
            p: p.read_bytes() for base in (folder, mesh) if base.exists() for p in base.iterdir()
        } == before
        assert all(p.is_file() and p.is_relative_to(partial) for p in built.files)
        assert {partial / "wing.fsm", partial / "mesh/wing_obj.obj", built.record} <= set(
            built.files
        )
        record = json.loads(built.record.read_text(encoding="utf-8"))
        for item in (
            record["instruction"],
            *record["inputs"],
            record["script"],
            *record["outputs"],
        ):
            assert file_sha256(partial / item["file"]) == item["sha256"]
        assert (partial / record["audit"]["file"]).is_file()
        assert (partial / "wing.preview.vtk").is_file()
        assert (partial / "mesh/wing_obj.te.txt").is_file()
        assert (partial / "mesh/wing_obj.boundaries.toml").is_file()

    @staticmethod
    @pytest.mark.requirement("FR-471")
    def test_p0400_rfixg_failed_audit_cli_exits_one(tmp_path: Path, monkeypatch, capsys) -> None:
        from pyflightstream.run import _cli_geometry

        root = _geometry_build__workspace(tmp_path)
        folder = _geometry_build__geometry(root, "wing", _GEOMETRY_BUILD__MESH_INSTRUCTION)
        plan = plan_geometry_build(folder, registry=_geometry_build__verified_registry())
        monkeypatch.setattr(_cli_geometry, "plan_geometry_build", lambda *a, **k: plan)
        monkeypatch.setattr(
            _cli_geometry, "_runner", lambda executable: _geometry_build__runner(sliver=True)
        )
        monkeypatch.chdir(folder)
        assert main(["geometry", "build", "--apply"]) == 1
        captured = capsys.readouterr()
        assert "nothing was promoted" in captured.err.lower()
        assert str(folder.with_name("wing.partial")) in captured.out
        assert "geometry accept" not in captured.out
        assert not (folder / "wing.fsm").exists()


def _rfixr4_sweep___overlay(folder: Path) -> tuple[list[str], list[str]]:
    text = (folder / "wing.sweep.vtk").read_text(encoding="utf-8")
    assert "SCALARS variant int 1" in text
    labels = text.split("LOOKUP_TABLE default\n")[1].split("\nFIELD")[0].split()
    tags = text.split(" string\n")[1].splitlines()
    cells = int(text.split("CELL_DATA ")[1].split()[0])
    assert len(labels) == cells and cells > 0
    return labels, tags


class TestRfixR4Sweep:
    """Offline regressions for sweep output and original angle ordinals (FR-472 R7)."""

    @staticmethod
    @pytest.fixture(autouse=True)
    def verified_cli(monkeypatch):
        """Use the existing offline verified command registry without running a solver."""
        original = _cli_geometry.plan_geometry_build

        def plan(*args, **kwargs):
            return original(*args, **kwargs, registry=_geometry_build__verified_registry())

        monkeypatch.setattr(_cli_geometry, "plan_geometry_build", plan)

    @staticmethod
    @pytest.mark.requirement("FR-472")
    def test_p0400_rfixr4_obj_sweep_overlay(tmp_path, monkeypatch):
        """P0400-RFIXR4-OBJ: OBJ-only builds replace stale overlays with every surface."""
        _, folder = _geometry_complete___sweep(tmp_path)
        instruction = folder / "wing.geometry.toml"
        instruction.write_text('outputs = ["obj"]\n' + instruction.read_text(), encoding="utf-8")
        (folder / "wing.sweep.vtk").write_text("stale overlay", encoding="utf-8")
        monkeypatch.chdir(folder.parent)
        monkeypatch.setattr(
            _cli_geometry, "_runner", lambda executable: _geometry_complete___body_runner()
        )
        assert main(["geometry", "build", "wing", "--apply", "--overwrite"]) == 0
        labels, tags = _rfixr4_sweep___overlay(folder)
        assert set(labels) == {"1", "2", "3"}
        assert tags == ["Base-100", "Base+000", "Base+100"]
        counts = [labels.count(str(number)) for number in (1, 2, 3)]
        # The committed solver-written body has 24 Base faces and 1032 Body faces.
        assert counts == [24, 24, 24]
        for tag in tags:
            variant = folder.with_name(f"wing_{tag}")
            assert (variant / f"wing_{tag}.obj").is_file()
            assert not (variant / f"wing_{tag}.fsm").exists()
            assert not variant.with_name(variant.name + ".partial").exists()

    @staticmethod
    @pytest.mark.requirement("FR-472")
    @pytest.mark.parametrize("only, expected", [("Base+100", [3]), ("Base+100,Base-100", [1, 3])])
    def test_p0400_rfixr4_only_original_ordinals(tmp_path, monkeypatch, only, expected):
        """P0400-RFIXR4-ORDINAL: --only retains original positions and angle order."""
        _, folder = _geometry_complete___sweep(tmp_path)
        monkeypatch.chdir(folder.parent)
        monkeypatch.setattr(
            _cli_geometry, "_runner", lambda executable: _geometry_complete___body_runner()
        )
        assert main(["geometry", "build", "wing", "--apply", "--only", only]) == 0
        labels, tags = _rfixr4_sweep___overlay(folder)
        assert set(labels) == {str(number) for number in expected}
        all_tags = ["Base-100", "Base+000", "Base+100"]
        assert tags == [all_tags[number - 1] for number in expected]

    @staticmethod
    @pytest.mark.requirement("FR-472")
    @pytest.mark.parametrize("failure", ["unreadable", "empty"])
    def test_p0400_rfixr4_overlay_failure_clears_stale(tmp_path, monkeypatch, capsys, failure):
        """P0400-RFIXR4-FAILURE: an incomplete overlay fails explicitly without stale output."""
        _, folder = _geometry_complete___sweep(tmp_path)
        target = folder / "wing.sweep.vtk"
        target.write_text("stale overlay", encoding="utf-8")
        monkeypatch.chdir(folder.parent)
        monkeypatch.setattr(
            _cli_geometry, "_runner", lambda executable: _geometry_complete___body_runner()
        )
        original = _geometry_vtk._surface_of

        def surface(fsm, name, obj=None):
            if "Base+000" in fsm.name:
                if failure == "unreadable":
                    raise MeshReadError("unreadable test mesh")
                return [], []
            return original(fsm, name, obj)

        monkeypatch.setattr(_geometry_vtk, "_surface_of", surface)
        assert main(["geometry", "build", "wing", "--apply", "--overwrite"]) == 3
        assert not target.exists()
        assert target.with_name(target.name + ".previous").read_text() == "stale overlay"
        assert "sweep overlay" in capsys.readouterr().err


def _rfixr5_sweep___plan(folder, only):
    return plan_geometry_build(
        folder, cwd=folder.parent, only=only, registry=_geometry_build__verified_registry()
    )


class TestRfixR5Sweep:
    """Build disjoint sweep subsets, then rebuild with and without overwrite.

    The runners use existing offline fixtures; no licensed solver is called.
    """

    @staticmethod
    @pytest.mark.requirement("FR-471", "FR-472")
    @pytest.mark.parametrize("fail", [False, True])
    def test_p0400_rfixr5_existing_overlay_refuses_disjoint_subset(tmp_path, fail):
        """P0400-RFIXR5-117: refuse before a successful or failing second runner."""
        _, folder = _geometry_complete___sweep(tmp_path)
        apply_geometry_build(
            _rfixr5_sweep___plan(folder, ("Base-100",)), runner=_geometry_complete___body_runner()
        )
        target = folder / "wing.sweep.vtk"
        before = target.read_bytes()
        calls = []

        def run(script, work):
            calls.append(script)
            if fail:
                return SolverOutcome(True, 1, 0, "failure", "exited 1")
            return _geometry_complete___body_runner()(script, work)

        try:
            apply_geometry_build(_rfixr5_sweep___plan(folder, ("Base+100",)), runner=run)
        except (InputArtifactError, GeometryBuildError) as error:
            assert isinstance(error, InputArtifactError)
            assert "--overwrite" in str(error)
        else:
            pytest.fail("existing overlay was replaced without overwrite")
        assert target.read_bytes() == before
        assert not calls

    @staticmethod
    @pytest.mark.requirement("FR-471", "FR-472")
    @pytest.mark.parametrize("failure", ["solver", "writer", "none"])
    def test_p0400_rfixr5_overwrite_retains_previous_overlay(tmp_path, monkeypatch, failure):
        """P0400-RFIXR5-117: preserve old evidence and publish only a complete overlay."""
        _, folder = _geometry_complete___sweep(tmp_path)
        target = folder / "wing.sweep.vtk"
        target.write_bytes(b"old overlay")
        previous = target.with_name(target.name + ".previous")
        previous.write_bytes(b"older overlay")

        def broken_writer(path, *args):
            path.write_bytes(b"incomplete")
            raise OSError("synthetic write failure")

        if failure == "writer":
            monkeypatch.setattr(_geometry_build, "write_sweep_vtk", broken_writer)
        run = (
            _geometry_complete___body_runner()
            if failure != "solver"
            else lambda s, w: SolverOutcome(True, 1, 0, "failure", "exited 1")
        )
        if failure == "none":
            apply_geometry_build(
                _rfixr5_sweep___plan(folder, ("Base+100",)), runner=run, overwrite=True
            )
            assert b"POLYGONS 24" in target.read_bytes()
        else:
            with pytest.raises(GeometryBuildError):
                apply_geometry_build(
                    _rfixr5_sweep___plan(folder, ("Base+100",)), runner=run, overwrite=True
                )
            assert not target.exists()
        assert previous.read_bytes() == b"older overlay"
        archived = target.with_name(target.name + ".previous.1")
        assert archived.is_file()
        assert archived.read_bytes() == b"old overlay"
        assert not list(folder.glob("*.pending*"))

    @staticmethod
    @pytest.mark.requirement("FR-472")
    @pytest.mark.parametrize("outputs", ['["obj"]', '["fsm"]'])
    def test_p0400_rfixr5_quad_overlay(tmp_path, outputs):
        """P0400-RFIXR5-118: quadrilateral fallback keeps only the named surface and ordinal."""
        _, folder = _geometry_complete___sweep(tmp_path)
        instruction = folder / "wing.geometry.toml"
        instruction.write_text(
            "outputs = "
            + outputs
            + chr(10)
            + instruction.read_text().replace('["Body", "Base"]', '["Base"]'),
            encoding="utf-8",
        )

        def run(script: Path, work: Path):
            name = script.name.removesuffix(".build.txt")
            (work / f"{name}.fsm").write_text(_RFIXR5_SWEEP__QUAD_BLOCK.replace("Wing", "Base"))
            rows = [
                "v 0 0 0",
                "v 1 0 0",
                "v 1 1 0",
                "v 0 1 0",
                "v 3 0 0",
                "v 4 0 0",
                "v 3 1 0",
                "g Body",
                "f 5 6 7",
                "g Base",
                "f 1 2 3 4",
            ]
            (work / f"{name}.obj").write_text(chr(10).join(rows) + chr(10))
            return SolverOutcome(False, 0, 0, "log", "")

        try:
            built = apply_geometry_build(_rfixr5_sweep___plan(folder, ("Base+100",)), runner=run)
        except GeometryBuildError as error:
            pytest.fail(str(error))
        assert built[0].passed
        text = (folder / "wing.sweep.vtk").read_text()
        assert "POLYGONS 1 5" in text
        assert chr(10).join(["LOOKUP_TABLE default", "3", "FIELD tags 1"]) in text
        assert text.split(" string" + chr(10))[1].splitlines() == ["Base+100"]

    @staticmethod
    @pytest.mark.requirement("FR-471")
    @pytest.mark.parametrize("suffix", [".build.log", ".build.txt", ".boundaries.toml"])
    def test_p0400_rfixr5_preflight_all_promoted_files(tmp_path, suffix):
        """P0400-SWEEP-01: an unrecorded generated file is refused before the runner."""
        _, folder = _geometry_complete___sweep(tmp_path)
        # A nonsweep base folder can contain user files without a build record.
        instruction = folder / "wing.geometry.toml"
        instruction.write_text(instruction.read_text().split("[sweep]")[0])
        target = folder / ("wing" + suffix)
        target.write_bytes(b"user evidence")
        calls = []

        def run(script, work):
            calls.append(script)
            return _geometry_complete___body_runner()(script, work)

        try:
            apply_geometry_build(_rfixr5_sweep___plan(folder, ()), runner=run)
        except InputArtifactError:
            pass
        else:
            pytest.fail("existing promoted file was not refused")
        assert not calls
        assert target.read_bytes() == b"user evidence"

    @staticmethod
    @pytest.mark.requirement("FR-471", "FR-472")
    @pytest.mark.parametrize("failure", ["solver", "overlay", "audit"])
    def test_p0400_rfixr5_sweep_failure_preserves_variant_outputs(tmp_path, monkeypatch, failure):
        """P0400-SWEEP-02: do not promote a replacement until the sweep build succeeds."""
        _, folder = _geometry_complete___sweep(tmp_path)
        apply_geometry_build(
            _rfixr5_sweep___plan(folder, ("Base-100",)), runner=_geometry_complete___body_runner()
        )
        variant = folder.with_name("wing_Base-100")
        before = {path.name: path.read_bytes() for path in variant.iterdir() if path.is_file()}

        def run(script, work):
            if failure == "solver" and "Base+100" in script.name:
                return SolverOutcome(True, 1, 0, "failure", "exited 1")
            result = _geometry_complete___body_runner()(script, work)
            if failure == "audit" and "Base+100" in script.name:
                obj = work / script.name.replace(".build.txt", ".obj")
                with obj.open("a") as handle:
                    handle.write("f 1 1 2" + chr(10))
            return result._replace(log="new build log")

        def broken_writer(*args):
            raise OSError("synthetic overlay failure")

        if failure == "overlay":
            monkeypatch.setattr(_geometry_build, "write_sweep_vtk", broken_writer)
        plan = _rfixr5_sweep___plan(folder, ("Base-100", "Base+100"))
        if failure == "audit":
            built = apply_geometry_build(plan, runner=run, overwrite=True)
            assert [item.passed for item in built] == [True, False]
            assert not (folder / "wing.sweep.vtk").exists()
        else:
            with pytest.raises(GeometryBuildError):
                apply_geometry_build(plan, runner=run, overwrite=True)
        assert {
            path.name: path.read_bytes() for path in variant.iterdir() if path.is_file()
        } == before


_RFIXR6_SWEEP__TAGS = ("Base-100", "Base+000", "Base+100")


def _rfixr6_sweep___with_outputs(folder: Path, outputs: str) -> None:
    instruction = folder / "wing.geometry.toml"
    instruction.write_text(f"outputs = {outputs}\n" + instruction.read_text(), encoding="utf-8")


def _rfixr6_sweep___plan(folder: Path, only: tuple[str, ...] = ()):
    return plan_geometry_build(
        folder, cwd=folder.parent, only=only, registry=_geometry_build__verified_registry()
    )


def _rfixr6_sweep___runner(failure: str | None = None, on: str = "Base+100"):
    """The body runner; ``failure`` fails the solver of, or the audit of, the variant ``on``."""
    body = _geometry_complete___body_runner()

    def run(script: Path, work: Path) -> SolverOutcome:
        if failure == "solver" and on in script.name:
            return SolverOutcome(True, 1, 0.0, "licence refused", "exited 1")
        outcome = body(script, work)
        if failure == "audit" and on in script.name:
            with (work / script.name.replace(".build.txt", ".obj")).open("a") as handle:
                handle.write("f 1 1 2\n")
        return outcome

    return run


def _rfixr6_sweep___resolving(record_path: Path) -> dict:
    """Return the record after checking that every file it names is beside it, as hashed."""
    record = json.loads(record_path.read_text(encoding="utf-8"))
    base = record_path.parent
    for item in (record["instruction"], *record["inputs"], record["script"], *record["outputs"]):
        path = base / item["file"]
        assert path.is_file(), f"{record_path.name} names {item['file']}, absent from {base}"
        assert file_sha256(path) == item["sha256"], path
    if record["audit"]["file"] is not None:
        audit = base / record["audit"]["file"]
        assert audit.is_file(), f"{record_path.name} names the audit {audit.name}, absent"
    return record


def _rfixr6_sweep___records_under(geometries: Path) -> list[Path]:
    return sorted(
        path for path in geometries.rglob("*.build.json") if ".previous" not in path.parent.name
    )


class TestRfixR6Sweep:
    """A geometry build is one transaction: staged, verified, then promoted whole or not at all.

    P0400-RFIXR6-SWEEP (PFS-2081.120, REL6-002; FR-471 R3, R7, R8 and FR-472). Every
    record a build leaves names files that exist beside it, wherever the build
    stopped: promoted into the geometry folders after a success, kept in the
    ``.partial`` folders after a solver, audit or overlay failure (the passing
    siblings of a failed sweep included), and absent rather than wrong after an
    interruption. The command offers ``geometry accept`` for promoted geometries
    only, and ``accept`` refuses a partial folder. The runners stand in for the
    solver on the committed fixtures; no licensed solver is called.
    """

    @staticmethod
    @pytest.mark.requirement("FR-471", "FR-472")
    @pytest.mark.parametrize("outputs", ['["fsm"]', '["obj"]', '["fsm", "obj"]'])
    @pytest.mark.parametrize("failure", ["solver", "audit", "overlay"])
    def test_p0400_rfixr6_a_failed_sweep_keeps_every_record_true_to_its_partial_folder(
        tmp_path, monkeypatch, outputs, failure
    ):
        """P0400-RFIXR6-SWEEP: nothing promoted, and each kept record resolves where it is kept."""
        _, folder = _geometry_complete___sweep(tmp_path)
        _rfixr6_sweep___with_outputs(folder, outputs)
        if failure == "overlay":

            def broken(*args):
                raise OSError("synthetic overlay failure")

            monkeypatch.setattr(_geometry_build, "write_sweep_vtk", broken)
        plan = _rfixr6_sweep___plan(folder, ("Base-100", "Base+100"))
        run = _rfixr6_sweep___runner(failure)
        if failure == "audit":
            built = apply_geometry_build(plan, runner=run)
        else:
            with pytest.raises(GeometryBuildError):
                apply_geometry_build(plan, runner=run)
        geometries = folder.parent
        for tag in ("Base-100", "Base+100"):
            assert not geometries.joinpath(f"wing_{tag}").exists(), f"{tag} was promoted"
            assert not geometries.joinpath(f"wing_{tag}_obj").exists(), f"{tag} mesh was promoted"
        assert not (folder / "wing.sweep.vtk").exists()
        kept = _rfixr6_sweep___records_under(geometries)
        expected = {"Base-100"} if failure == "solver" else {"Base-100", "Base+100"}
        assert {path.parent.name for path in kept} == {f"wing_{tag}.partial" for tag in expected}
        for record_path in kept:
            _rfixr6_sweep___resolving(record_path)
        if failure == "audit":
            assert [item.passed for item in built] == [True, False]
            assert [getattr(item, "promoted", None) for item in built] == [False, False]
            assert [item.folder.name for item in built] == [
                "wing_Base-100.partial",
                "wing_Base+100.partial",
            ]

    @staticmethod
    @pytest.mark.requirement("FR-471", "FR-472")
    @pytest.mark.parametrize("failure", ["audit", "solver"])
    def test_p0400_rfixr6_the_command_never_offers_to_accept_an_unpromoted_geometry(
        tmp_path, monkeypatch, capsys, failure
    ):
        """P0400-RFIXR6-SWEEP: the CLI names what was kept and why, and accept refuses it."""
        root, folder = _geometry_complete___sweep(tmp_path)
        original = _cli_geometry.plan_geometry_build
        monkeypatch.setattr(
            _cli_geometry,
            "plan_geometry_build",
            lambda *a, **k: original(*a, **k, registry=_geometry_build__verified_registry()),
        )
        monkeypatch.setattr(
            _cli_geometry, "_runner", lambda executable: _rfixr6_sweep___runner(failure)
        )
        monkeypatch.chdir(folder.parent)
        code = main(["geometry", "build", "wing", "--apply", "--only", "Base-100,Base+100"])
        captured = capsys.readouterr()
        text = captured.out + captured.err
        assert code == (1 if failure == "audit" else 3)
        assert "geometry accept" not in text
        if failure == "audit":
            kept = folder.parent / "wing_Base-100.partial"
            assert str(kept) in text
            assert "not promoted" in text
            assert "Base+100" in text.split("not promoted", 1)[1].splitlines()[0]
        capsys.readouterr()
        workspace = ["--workspace", str(root)]
        assert main(["geometry", "accept", "wing_Base-100.partial", *workspace]) == 2
        record = folder.parent / "wing_Base-100.partial" / "wing_Base-100.build.json"
        assert json.loads(record.read_text(encoding="utf-8"))["inspected"] is None

    @staticmethod
    @pytest.mark.requirement("FR-471", "FR-472")
    @pytest.mark.parametrize("outputs", ['["fsm"]', '["obj"]', '["fsm", "obj"]'])
    def test_p0400_rfixr6_a_built_sweep_promotes_every_record_true_to_its_folder(
        tmp_path, monkeypatch, capsys, outputs
    ):
        """P0400-RFIXR6-SWEEP: success leaves no partial folder, and accept is offered for each."""
        _, folder = _geometry_complete___sweep(tmp_path)
        _rfixr6_sweep___with_outputs(folder, outputs)
        original = _cli_geometry.plan_geometry_build
        monkeypatch.setattr(
            _cli_geometry,
            "plan_geometry_build",
            lambda *a, **k: original(*a, **k, registry=_geometry_build__verified_registry()),
        )
        monkeypatch.setattr(_cli_geometry, "_runner", lambda executable: _rfixr6_sweep___runner())
        monkeypatch.chdir(folder.parent)
        assert main(["geometry", "build", "wing", "--apply"]) == 0
        out = capsys.readouterr().out
        assert (
            "accept after inspection: pyfs-workspace geometry accept "
            + ",".join(f"wing_{tag}" for tag in _RFIXR6_SWEEP__TAGS)
            in out
        )
        geometries = folder.parent
        assert not list(geometries.glob("*.partial"))
        assert (folder / "wing.sweep.vtk").is_file()
        records = _rfixr6_sweep___records_under(geometries)
        expected = {f"wing_{tag}" for tag in _RFIXR6_SWEEP__TAGS}
        if "obj" in outputs and "fsm" in outputs:
            expected |= {f"wing_{tag}_obj" for tag in _RFIXR6_SWEEP__TAGS}
        assert {path.parent.name for path in records} == expected
        for record_path in records:
            _rfixr6_sweep___resolving(record_path)

    @staticmethod
    @pytest.mark.requirement("FR-471", "FR-472")
    def test_p0400_rfixr6_an_interrupted_promotion_leaves_no_false_record_and_recovers(
        tmp_path, monkeypatch
    ):
        """P0400-RFIXR6-SWEEP: a record is written last and the overlay after every variant."""
        _, folder = _geometry_complete___sweep(tmp_path)
        _rfixr6_sweep___with_outputs(folder, '["fsm", "obj"]')
        original = _geometry_build._move_into
        calls = []

        def interrupted(sources, destination, overwrite):
            calls.append(destination)
            if len(calls) == 2:
                raise KeyboardInterrupt("synthetic interruption during promotion")
            return original(sources, destination, overwrite)

        monkeypatch.setattr(_geometry_build, "_move_into", interrupted)
        with pytest.raises(KeyboardInterrupt):
            apply_geometry_build(_rfixr6_sweep___plan(folder), runner=_rfixr6_sweep___runner())
        geometries = folder.parent
        assert not (folder / "wing.sweep.vtk").exists(), "the overlay claims an unpromoted sweep"
        for record_path in _rfixr6_sweep___records_under(geometries):
            _rfixr6_sweep___resolving(record_path)
        assert not list(geometries.glob("*.pending*")) and not list(folder.glob("*.pending*"))
        monkeypatch.setattr(_geometry_build, "_move_into", original)
        built = apply_geometry_build(
            _rfixr6_sweep___plan(folder), runner=_rfixr6_sweep___runner(), overwrite=True
        )
        assert all(getattr(item, "promoted", True) and item.passed for item in built)
        assert (folder / "wing.sweep.vtk").is_file()
        records = _rfixr6_sweep___records_under(geometries)
        assert {path.parent.name for path in records} == {
            f"wing_{tag}{end}" for tag in _RFIXR6_SWEEP__TAGS for end in ("", "_obj")
        }
        for record_path in records:
            _rfixr6_sweep___resolving(record_path)
