"""Offline regressions for sweep output and original angle ordinals (FR-472 R7)."""

# ruff: noqa: N999 - The lane contract prescribes the filename's rfixR4 spelling.

from pathlib import Path

import pytest

from pyflightstream._fsm import MeshReadError
from pyflightstream.run import _cli_geometry
from pyflightstream.workspace import _geometry_vtk
from pyflightstream.workspace.cli import main
from tests.tier1_offline.test_p0400_geometry_build import verified_registry
from tests.tier1_offline.test_p0400_geometry_complete import _body_runner, _sweep


@pytest.fixture(autouse=True)
def verified_cli(monkeypatch):
    """Use the existing offline verified command registry without running a solver."""
    original = _cli_geometry.plan_geometry_build

    def plan(*args, **kwargs):
        return original(*args, **kwargs, registry=verified_registry())

    monkeypatch.setattr(_cli_geometry, "plan_geometry_build", plan)


def _overlay(folder: Path) -> tuple[list[str], list[str]]:
    text = (folder / "wing.sweep.vtk").read_text(encoding="utf-8")
    assert "SCALARS variant int 1" in text
    labels = text.split("LOOKUP_TABLE default\n")[1].split("\nFIELD")[0].split()
    tags = text.split(" string\n")[1].splitlines()
    cells = int(text.split("CELL_DATA ")[1].split()[0])
    assert len(labels) == cells and cells > 0
    return labels, tags


@pytest.mark.requirement("FR-472")
def test_p0400_rfixr4_obj_sweep_overlay(tmp_path, monkeypatch):
    """P0400-RFIXR4-OBJ: OBJ-only builds replace stale overlays with every surface."""
    _, folder = _sweep(tmp_path)
    instruction = folder / "wing.geometry.toml"
    instruction.write_text('outputs = ["obj"]\n' + instruction.read_text(), encoding="utf-8")
    (folder / "wing.sweep.vtk").write_text("stale overlay", encoding="utf-8")
    monkeypatch.chdir(folder.parent)
    monkeypatch.setattr(_cli_geometry, "_runner", lambda executable: _body_runner())
    assert main(["geometry", "build", "wing", "--apply"]) == 0
    labels, tags = _overlay(folder)
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


@pytest.mark.requirement("FR-472")
@pytest.mark.parametrize("only, expected", [("Base+100", [3]), ("Base+100,Base-100", [1, 3])])
def test_p0400_rfixr4_only_original_ordinals(tmp_path, monkeypatch, only, expected):
    """P0400-RFIXR4-ORDINAL: --only retains original positions and angle order."""
    _, folder = _sweep(tmp_path)
    monkeypatch.chdir(folder.parent)
    monkeypatch.setattr(_cli_geometry, "_runner", lambda executable: _body_runner())
    assert main(["geometry", "build", "wing", "--apply", "--only", only]) == 0
    labels, tags = _overlay(folder)
    assert set(labels) == {str(number) for number in expected}
    all_tags = ["Base-100", "Base+000", "Base+100"]
    assert tags == [all_tags[number - 1] for number in expected]


@pytest.mark.requirement("FR-472")
@pytest.mark.parametrize("failure", ["unreadable", "empty"])
def test_p0400_rfixr4_overlay_failure_clears_stale(tmp_path, monkeypatch, capsys, failure):
    """P0400-RFIXR4-FAILURE: an incomplete overlay fails explicitly without stale output."""
    _, folder = _sweep(tmp_path)
    target = folder / "wing.sweep.vtk"
    target.write_text("stale overlay", encoding="utf-8")
    monkeypatch.chdir(folder.parent)
    monkeypatch.setattr(_cli_geometry, "_runner", lambda executable: _body_runner())
    original = _geometry_vtk._surface_of

    def surface(fsm, name):
        if "Base+000" in fsm.name:
            if failure == "unreadable":
                raise MeshReadError("unreadable test mesh")
            return [], []
        return original(fsm, name)

    monkeypatch.setattr(_geometry_vtk, "_surface_of", surface)
    assert main(["geometry", "build", "wing", "--apply"]) == 3
    assert not target.exists()
    assert "sweep overlay" in capsys.readouterr().err
