"""Tier 1, 0.40.0: ``pyfs-workspace geometry build`` previews and builds a body (FR-471).

P0400-GEOM-BUILD (PFS-2081.41). The solver is replaced by a runner that does
what a build's script asks of it: it writes the saved simulation and the
exported mesh into the partial folder. The saved simulation is a committed one
the solver wrote (``tests/tier3_licensed/inputs/geometries/10_WING.fsm``, a
straight wing named ``Wing`` with sixteen marked trailing-edge edges), so the
read-back, the audit, the preview and the record are judged against a file of
the solver's own.
"""

from __future__ import annotations

import json
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from pyflightstream._errors import InputArtifactError
from pyflightstream._fsm import boundary_names, surface_mesh
from pyflightstream.cases._geometry_emit import EVIDENCE_GATED
from pyflightstream.commands import CommandRegistry, Status
from pyflightstream.workspace._geometry_build import (
    GeometryBuildError,
    SolverOutcome,
    apply_geometry_build,
    plan_geometry_build,
    refuse_before_running,
)
from pyflightstream.workspace.cli import main

WING_FSM = (
    Path(__file__).resolve().parents[1] / "tier3_licensed" / "inputs" / "geometries" / "10_WING.fsm"
)

MESH_INSTRUCTION = (
    'fs_build = "26.125"\nboundaries = ["Wing"]\noutputs = ["fsm", "obj"]\n'
    '[mesh]\nfile = "src.obj"\nunits = "METER"\n[trailing_edges]\ndetect = "auto"\n'
)


def workspace(tmp_path: Path) -> Path:
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


def wing_obj(path: Path, group: str = "Wing") -> Path:
    """Write the committed wing's surface as an OBJ with one group."""
    vertices, triangles = surface_mesh(WING_FSM)
    rows = [f"v {x} {y} {z}" for x, y, z in vertices] + [f"g {group}"]
    rows += [f"f {a + 1} {b + 1} {c + 1}" for a, b, c in triangles]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def geometry(root: Path, folder: str, text: str, *, source: str | None = "src.obj") -> Path:
    """A geometry folder with its instruction and, optionally, a mesh source."""
    where = root / "inputs" / "geometries" / folder
    where.mkdir(parents=True, exist_ok=True)
    if source is not None:
        wing_obj(where / source)
    (where / f"{folder}.geometry.toml").write_text(text, encoding="utf-8")
    return where


def runner(
    saved: Path = WING_FSM, *, fail: bool = False, sliver: bool = False
) -> Callable[[Path, Path], SolverOutcome]:
    """A runner doing what the build's script asks: save the body, export its mesh.

    ``sliver`` adds a face of zero area to the export, which audit gate G1 fails.
    """

    def run(script: Path, work: Path) -> SolverOutcome:
        name = script.name.removesuffix(".build.txt")
        if not fail:
            shutil.copyfile(saved, work / f"{name}.fsm")
            mesh = wing_obj(work / f"{name}.obj")
            if sliver:
                with mesh.open("a", encoding="utf-8") as handle:
                    handle.write("f 1 1 2\n")
        return SolverOutcome(fail, 1 if fail else 0, 2.5, "solver log", "exited 1" if fail else "")

    return run


def verified_registry() -> CommandRegistry:
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


@pytest.fixture
def verified() -> CommandRegistry:
    """Every gated command verified, handed to the plan as its command database."""
    return verified_registry()


@pytest.mark.requirement("FR-471")
def test_p0400_geom_build_preview_runs_nothing_and_writes_nothing(tmp_path, capsys, monkeypatch):
    """P0400-GEOM-BUILD (PFS-2081.41): R1, the preview names the script and the names."""
    root = workspace(tmp_path)
    folder = geometry(root, "wing", MESH_INSTRUCTION)
    before = sorted(p.name for p in folder.iterdir())
    monkeypatch.chdir(folder)
    assert main(["geometry", "build"]) == 0
    out = capsys.readouterr().out
    assert "IMPORT" in out and "SAVEAS" in out and "after source: Wing" in out
    assert "preview only" in out
    assert sorted(p.name for p in folder.iterdir()) == before
    assert not folder.with_name("wing.partial").exists()


@pytest.mark.requirement("FR-471")
def test_p0400_geom_build_script_saves_after_the_export_and_the_marking(tmp_path):
    """P0400-GEOM-BUILD (PFS-2081.41): R2, the order of one build's script."""
    root = workspace(tmp_path)
    geometry(root, "wing", MESH_INSTRUCTION)
    plan = plan_geometry_build(root / "inputs" / "geometries" / "wing")
    lines = [line for line in plan.variants[0].script.text.splitlines() if line]
    order = [
        "NEW_SIMULATION",
        "IMPORT",
        "EXPORT_SURFACE_MESH OBJ -1",
        "SET_SIMULATION_LENGTH_UNITS METER",
        "SAVEAS",
        "CLOSE_FLIGHTSTREAM",
    ]
    positions = [next(i for i, line in enumerate(lines) if line.startswith(word)) for word in order]
    assert positions == sorted(positions), lines
    assert "NEW_SIMULATION" == lines[0]


@pytest.mark.requirement("FR-471")
def test_p0400_geom_build_refuses_a_command_awaiting_evidence_and_runs_nothing(tmp_path):
    """P0400-GEOM-BUILD (PFS-2081.41): R9, the evidence gate; the runner is never called."""
    root = workspace(tmp_path)
    geometry(root, "wing", MESH_INSTRUCTION)
    plan = plan_geometry_build(root / "inputs" / "geometries" / "wing")
    assert "EXPORT_SURFACE_MESH" in plan.awaiting_evidence
    called = []
    with pytest.raises(InputArtifactError, match="EXPORT_SURFACE_MESH.*licensed probe"):
        apply_geometry_build(plan, runner=lambda s, w: called.append(s))  # type: ignore
    assert not called


@pytest.mark.requirement("FR-471")
def test_p0400_geom_build_a_ccs_loft_waits_for_its_probe_on_26124_only(tmp_path):
    """P0400-GEOM-BUILD (PFS-2081.41): R9, the loft is verified on 26.125 and not on 26.124."""
    from tests.tier1_offline.test_p0400_geometry_instruction import CCS_WING, ccs_text

    root = workspace(tmp_path)
    folder = geometry(root, "wing", CCS_WING, source=None)
    (folder / "wing_sections.csv").write_text(ccs_text(), encoding="utf-8")
    on_125 = plan_geometry_build(folder, build="26.125").awaiting_evidence
    on_124 = plan_geometry_build(folder, build="26.124").awaiting_evidence
    assert "CAD_CREATE_WING_MESH_FROM_CCS" not in on_125
    assert "CAD_CREATE_WING_MESH_FROM_CCS" in on_124


@pytest.mark.requirement("FR-471")
def test_p0400_geom_build_writes_the_body_its_preview_and_its_record(tmp_path, verified):
    """P0400-GEOM-BUILD (PFS-2081.41): R3, R4, R6 and R7 on a body read back as stated."""
    root = workspace(tmp_path)
    folder = geometry(root, "wing", MESH_INSTRUCTION)
    plan = plan_geometry_build(folder, registry=verified)
    assert plan.awaiting_evidence == ()
    built = apply_geometry_build(plan, runner=runner(), package_version="0.40.0")
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


@pytest.mark.requirement("FR-471")
def test_p0400_geom_build_fails_on_other_boundaries_and_promotes_nothing(tmp_path, verified):
    """P0400-GEOM-BUILD (PFS-2081.41): R5, a saved body whose names are not the stated ones."""
    root = workspace(tmp_path)
    folder = geometry(
        root,
        "wing",
        MESH_INSTRUCTION.replace('boundaries = ["Wing"]', 'boundaries = ["Body"]').replace(
            "[trailing_edges]",
            '[[operations]]\nop = "rename"\nsurface = "Wing"\nto = "Body"\n[trailing_edges]',
        ),
    )
    plan = plan_geometry_build(folder, registry=verified)
    with pytest.raises(GeometryBuildError, match="carries the boundaries Wing.*states Body"):
        apply_geometry_build(plan, runner=runner())
    assert not (folder / "wing.fsm").exists()
    assert (folder.with_name("wing.partial") / "wing.build.txt").is_file()


@pytest.mark.requirement("FR-471")
def test_p0400_geom_build_a_failed_solver_promotes_nothing_and_keeps_the_partial_folder(
    tmp_path, verified
):
    """P0400-GEOM-BUILD (PFS-2081.41): R3 and R8, the error the command exits 3 on."""
    root = workspace(tmp_path)
    folder = geometry(root, "wing", MESH_INSTRUCTION)
    plan = plan_geometry_build(folder, registry=verified)
    with pytest.raises(GeometryBuildError, match="exited 1.*Nothing was promoted"):
        apply_geometry_build(plan, runner=runner(fail=True))
    assert not (folder / "wing.fsm").exists()
    partial = folder.with_name("wing.partial")
    assert (partial / "wing.build.txt").is_file() and (partial / "wing.build.log").is_file()


@pytest.mark.requirement("FR-471")
def test_p0400_geom_build_refuses_existing_outputs_without_overwrite(tmp_path, verified):
    """P0400-GEOM-BUILD (PFS-2081.41): R9, a second build is refused until --overwrite."""
    root = workspace(tmp_path)
    folder = geometry(root, "wing", MESH_INSTRUCTION)
    plan = plan_geometry_build(folder, registry=verified)
    apply_geometry_build(plan, runner=runner())
    with pytest.raises(InputArtifactError, match="--overwrite"):
        refuse_before_running(plan, overwrite=False, png=False)
    refuse_before_running(plan, overwrite=True, png=False)
    assert apply_geometry_build(plan, runner=runner(), overwrite=True)[0].passed


@pytest.mark.requirement("FR-471")
def test_p0400_geom_build_apply_on_an_unprobed_build_exits_2(tmp_path, capsys, monkeypatch):
    """P0400-GEOM-BUILD (PFS-2081.41): R9 at the command, before any executable is looked up."""
    root = workspace(tmp_path)
    (root / "inputs" / "executables.toml").unlink()
    folder = geometry(root, "wing", MESH_INSTRUCTION)
    monkeypatch.chdir(folder)
    assert main(["geometry", "build", "--apply"]) == 2
    err = capsys.readouterr().err
    assert "EXPORT_SURFACE_MESH" in err and "Nothing was written." in err
    assert not folder.with_name("wing.partial").exists()


@pytest.mark.requirement("FR-471")
def test_p0400_geom_build_refuses_an_instruction_outside_a_workspace(tmp_path, capsys, monkeypatch):
    """P0400-GEOM-BUILD (PFS-2081.41): R9, an instruction outside inputs/geometries."""
    folder = tmp_path / "loose"
    folder.mkdir()
    wing_obj(folder / "src.obj")
    (folder / "loose.geometry.toml").write_text(MESH_INSTRUCTION, encoding="utf-8")
    monkeypatch.chdir(folder)
    assert main(["geometry", "build"]) == 2
    assert "inputs/geometries/<folder>/" in capsys.readouterr().err


@pytest.mark.requirement("FR-471")
def test_p0400_geom_build_a_failed_audit_gate_keeps_the_files_and_says_so(tmp_path, verified):
    """P0400-GEOM-BUILD (PFS-2081.41): R8, a zero-area face fails G1; the files stay, exit 1."""
    root = workspace(tmp_path)
    folder = geometry(root, "wing", MESH_INSTRUCTION)
    plan = plan_geometry_build(folder, registry=verified)
    (built,) = apply_geometry_build(plan, runner=runner(sliver=True))
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
