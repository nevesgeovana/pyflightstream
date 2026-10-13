"""A sliver build must remain inspectable in partial storage, without promotion."""
# ruff: noqa: N999 - the assigned lane name is rfixG.

import json
from pathlib import Path

import pytest

from pyflightstream._digest import file_sha256
from pyflightstream.workspace._geometry_build import apply_geometry_build, plan_geometry_build
from pyflightstream.workspace.cli import main
from tests.tier1_offline.test_p0400_geometry_build import (
    MESH_INSTRUCTION,
    geometry,
    runner,
    verified_registry,
    workspace,
)

pytestmark = pytest.mark.requirement("P0400-RFIXG-AUDIT")


@pytest.mark.requirement("FR-471")
@pytest.mark.parametrize("overwrite", [False, True])
def test_p0400_rfixg_failed_audit_retains_outputs(tmp_path: Path, overwrite: bool) -> None:
    root = workspace(tmp_path)
    folder = geometry(root, "wing", MESH_INSTRUCTION)
    plan = plan_geometry_build(folder, registry=verified_registry())
    if overwrite:
        apply_geometry_build(plan, runner=runner())
    mesh = folder.with_name("wing_obj")
    before = {p: p.read_bytes() for base in (folder, mesh) if base.exists() for p in base.iterdir()}
    (built,) = apply_geometry_build(plan, runner=runner(sliver=True), overwrite=overwrite)
    partial = folder.with_name("wing.partial")
    assert built.folder == partial
    assert built.record == partial / "wing.build.json"
    assert not built.passed and any(g.startswith("G1") for g in built.failed_gates)
    assert {
        p: p.read_bytes() for base in (folder, mesh) if base.exists() for p in base.iterdir()
    } == before
    assert all(p.is_file() and p.is_relative_to(partial) for p in built.files)
    assert {partial / "wing.fsm", partial / "mesh/wing_obj.obj", built.record} <= set(built.files)
    record = json.loads(built.record.read_text(encoding="utf-8"))
    for item in (record["instruction"], *record["inputs"], record["script"], *record["outputs"]):
        assert file_sha256(partial / item["file"]) == item["sha256"]
    assert (partial / record["audit"]["file"]).is_file()
    assert (partial / "wing.preview.vtk").is_file()
    assert (partial / "mesh/wing_obj.te.txt").is_file()
    assert (partial / "mesh/wing_obj.boundaries.toml").is_file()


@pytest.mark.requirement("FR-471")
def test_p0400_rfixg_failed_audit_cli_exits_one(tmp_path: Path, monkeypatch, capsys) -> None:
    from pyflightstream.run import _cli_geometry

    root = workspace(tmp_path)
    folder = geometry(root, "wing", MESH_INSTRUCTION)
    plan = plan_geometry_build(folder, registry=verified_registry())
    monkeypatch.setattr(_cli_geometry, "plan_geometry_build", lambda *a, **k: plan)
    monkeypatch.setattr(_cli_geometry, "_runner", lambda executable: runner(sliver=True))
    monkeypatch.chdir(folder)
    assert main(["geometry", "build", "--apply"]) == 1
    captured = capsys.readouterr()
    assert "nothing was promoted" in captured.err.lower()
    assert str(folder.with_name("wing.partial")) in captured.out
    assert "geometry accept" not in captured.out
    assert not (folder / "wing.fsm").exists()
